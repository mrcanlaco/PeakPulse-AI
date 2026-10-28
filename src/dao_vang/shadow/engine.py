"""Unified Shadow Paper Trading Coordinator.
Coordinates execution of all running shadow strategies from a single lightweight engine.
"""

from __future__ import annotations
import json
import logging
import math
import threading
import time
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from .feeder import SharedMarketFeeder
from .models import (
    get_all_shadows,
    get_db_connection,
    update_shadow_status,
)

logger = logging.getLogger("shadow.engine")


class ShadowPaperCoordinator:
    """Singleton coordinator running all shadow strategies in a unified lightweight loop."""

    def __init__(self, feeder: Optional[SharedMarketFeeder] = None):
        self.feeder = feeder or SharedMarketFeeder()
        self.feeder.warm_up_from_local_storage()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.loop_interval_sec = 5.0
        self.last_candle_check = 0.0
        self.cycle_count = 0

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="ShadowCoordinatorThread")
        self.thread.start()
        logger.info("[SHADOW] Coordinator background thread started.")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        logger.info("[SHADOW] Coordinator stopped.")

    def _run_loop(self):
        # Initial live ticker fetch
        try:
            self.feeder.fetch_live_tickers()
            self.feeder.fetch_live_funding_rates()
        except Exception as exc:
            logger.warning(f"Initial feeder fetch failed: {exc}")

        while self.running:
            try:
                t0 = time.time()
                self.cycle_count += 1

                # 1. Update live prices and funding rates (respectful interval: every 15-30s)
                if t0 - self.feeder.last_ticker_fetch >= 20.0:
                    self.feeder.fetch_live_tickers()

                if t0 - self.feeder.last_funding_fetch >= 180.0:
                    self.feeder.fetch_live_funding_rates()

                # 2. Check 4H candles periodically (every 120s or near bar boundary)
                if t0 - self.last_candle_check >= 120.0:
                    self.feeder.fetch_latest_4h_candles(limit=5)
                    self.last_candle_check = t0

                # 3. Process all active shadow strategies
                self._process_active_shadows()

            except Exception as exc:
                logger.error(f"[SHADOW] Error in coordinator cycle: {exc}", exc_info=True)

            time.sleep(self.loop_interval_sec)

    def _process_active_shadows(self):
        shadows = get_all_shadows()
        if not shadows:
            return

        prices = self.feeder.prices
        funding_rates = self.feeder.funding_rates
        now = time.time()

        with get_db_connection() as conn:
            for s in shadows:
                s_id = s["id"]
                status = s["status"]
                cash = float(s["cash"])
                spec = s["spec"]
                universe = s["universe"]

                # 1. Update mark price and unrealized PnL for open positions
                active_pos_rows = conn.execute(
                    "SELECT * FROM positions WHERE shadow_id = ?", (s_id,)
                ).fetchall()

                total_unrealized = 0.0
                total_position_val = 0.0

                for pos in active_pos_rows:
                    sym = pos["symbol"]
                    side = pos["side"]
                    qty = pos["qty"]
                    entry_p = pos["entry_price"]
                    peak_p = pos["peak_price"]
                    stop_p = pos["stop_price"]

                    curr_price = prices.get(sym, entry_p if entry_p > 0 else 0.0)
                    if curr_price <= 0:
                        continue

                    # Update peak price for trailing stop
                    new_peak = max(peak_p, curr_price) if side == 1 else (min(peak_p, curr_price) if peak_p > 0 else curr_price)

                    unr_pnl = 0.0
                    unr_pct = 0.0
                    if side == 1 and qty > 0 and entry_p > 0:
                        unr_pnl = qty * (curr_price - entry_p)
                        unr_pct = (curr_price - entry_p) / entry_p * 100.0
                        total_position_val += qty * curr_price
                        total_unrealized += unr_pnl
                    elif side == -1 and qty > 0 and entry_p > 0:
                        unr_pnl = qty * (entry_p - curr_price)
                        unr_pct = (entry_p - curr_price) / entry_p * 100.0
                        total_position_val += qty * (2 * entry_p - curr_price)
                        total_unrealized += unr_pnl

                    conn.execute("""
                    UPDATE positions SET
                        mark_price = ?,
                        peak_price = ?,
                        unrealized_pnl = ?,
                        unrealized_pnl_pct = ?
                    WHERE shadow_id = ? AND symbol = ?
                    """, (curr_price, new_peak, unr_pnl, unr_pct, s_id, sym))

                total_equity = cash + total_position_val
                conn.execute("""
                UPDATE shadows SET
                    equity = ?,
                    unrealized_pnl = ?,
                    last_updated = ?
                WHERE id = ?
                """, (total_equity, total_unrealized, now, s_id))

                # If status is RUNNING, check signal triggers
                if status == "RUNNING" and self.feeder.candle_buffers_4h:
                    self._evaluate_signals_for_shadow(conn, s, prices, funding_rates)

            conn.commit()

    def _evaluate_signals_for_shadow(self, conn, shadow: dict, prices: dict, funding_rates: dict):
        """Evaluate strategy entry/exit logic causally on latest candle close."""
        s_id = shadow["id"]
        spec = shadow["spec"]
        universe = shadow["universe"]
        cash = float(shadow["cash"])
        equity = float(shadow["equity"])
        cost_rate = 0.0010  # 10 bps one way

        # Check BTC macro filter
        btc_buf = self.feeder.candle_buffers_4h.get("BTCUSDT")
        if btc_buf is None or len(btc_buf) < 100:
            return

        macro_span = 450 if "ema450" in spec.get("macro_btc_filter", "") else (500 if "ema500" in spec.get("macro_btc_filter", "") else 600)
        btc_close = btc_buf["close"].values
        btc_macro_ema = pd.Series(btc_close).ewm(span=macro_span).mean().values[-1]
        macro_ok = btc_close[-1] > btc_macro_ema

        # Market breadth
        breadth_factor = 1.0
        if spec.get("use_market_breadth", False):
            bull_c = 0
            for sym in universe:
                b = self.feeder.candle_buffers_4h.get(sym)
                if b is not None and len(b) >= 40:
                    e40 = pd.Series(b["close"].values).ewm(span=40).mean().values[-1]
                    if b["close"].values[-1] > e40:
                        bull_c += 1
            if bull_c < len(universe) / 2:
                breadth_factor = 0.70

        # Check exits
        pos_rows = conn.execute("SELECT * FROM positions WHERE shadow_id = ? AND side != 0", (s_id,)).fetchall()
        for pos in pos_rows:
            sym = pos["symbol"]
            buf = self.feeder.candle_buffers_4h.get(sym)
            if buf is None or len(buf) < 40:
                continue

            c_arr = buf["close"].values
            h_arr = buf["high"].values
            l_arr = buf["low"].values
            cp = c_arr[-1]
            entry_p = pos["entry_price"]
            peak_p = pos["peak_price"]
            qty = pos["qty"]

            # Calculate ATR14
            tr = np.maximum(h_arr[1:] - l_arr[1:], np.maximum(np.abs(h_arr[1:] - c_arr[:-1]), np.abs(l_arr[1:] - c_arr[:-1])))
            atr = float(pd.Series(tr).rolling(14).mean().iloc[-1]) if len(tr) >= 14 else (cp * 0.02)

            gain_atr = (peak_p - entry_p) / max(atr, 1e-6)
            trail_mult = float(spec.get("trail_atr_mult", 2.5))
            be_mult = float(spec.get("break_even_atr_mult", 1.5))
            tighten_mult = float(spec.get("staged_tighten_atr", 99.0))

            if gain_atr >= tighten_mult:
                stop_p = max(entry_p + 1.5 * atr, peak_p - 1.5 * atr)
            elif gain_atr >= be_mult:
                stop_p = max(entry_p, peak_p - trail_mult * atr)
            else:
                stop_p = peak_p - 2.5 * atr

            e40 = float(pd.Series(c_arr).ewm(span=40).mean().iloc[-1])
            exit_sig = (cp < stop_p) or (cp < e40) or (not macro_ok)

            if exit_sig:
                exec_price = prices.get(sym, cp)
                fee = qty * exec_price * cost_rate
                realized_pnl = qty * (exec_price - entry_p) - fee
                pnl_pct = (exec_price - entry_p) / entry_p * 100.0 if entry_p > 0 else 0.0

                # Record trade
                conn.execute("""
                INSERT INTO trades (shadow_id, symbol, side, qty, entry_price, exit_price, pnl, pnl_pct, fee, holding_hours, closed_at)
                VALUES (?, ?, 'LONG', ?, ?, ?, ?, ?, ?, ?, ?)
                """, (s_id, sym, qty, entry_p, exec_price, realized_pnl, pnl_pct, fee, (time.time() - pos["opened_at"]) / 3600.0, time.time()))

                # Update cash and clear position
                new_cash = cash + (qty * exec_price - fee)
                conn.execute("""
                UPDATE positions SET side = 0, qty = 0.0, entry_price = 0.0, peak_price = 0.0, stop_price = 0.0, unrealized_pnl = 0.0, unrealized_pnl_pct = 0.0
                WHERE shadow_id = ? AND symbol = ?
                """, (s_id, sym))

                conn.execute("""
                UPDATE shadows SET
                    cash = ?,
                    realized_pnl = realized_pnl + ?,
                    total_trades = total_trades + 1,
                    win_trades = win_trades + ?
                WHERE id = ?
                """, (new_cash, realized_pnl, 1 if realized_pnl > 0 else 0, s_id))
                cash = new_cash
                logger.info(f"[SHADOW {s_id}] Closed {sym} @ {exec_price:.2f} | PnL: ${realized_pnl:+.2f} ({pnl_pct:+.2f}%)")

        # Check entries if macro is bull
        if macro_ok:
            open_count = conn.execute("SELECT COUNT(*) FROM positions WHERE shadow_id = ? AND side != 0", (s_id,)).fetchone()[0]
            max_slots = int(spec.get("slots", 2))
            avail = max_slots - open_count
            if avail > 0:
                donch_len = int(spec.get("entry_donch_len", 30))
                cands = []
                for sym in universe:
                    # check if already open
                    pos = conn.execute("SELECT side FROM positions WHERE shadow_id = ? AND symbol = ?", (s_id, sym)).fetchone()
                    if pos and pos["side"] != 0:
                        continue

                    buf = self.feeder.candle_buffers_4h.get(sym)
                    if buf is None or len(buf) < max(donch_len + 5, 45):
                        continue

                    c_arr = buf["close"].values
                    h_arr = buf["high"].values
                    l_arr = buf["low"].values
                    cp = c_arr[-1]

                    dh = float(pd.Series(h_arr).rolling(donch_len).max().iloc[-2]) if len(h_arr) > donch_len else 1e9
                    e40 = float(pd.Series(c_arr).ewm(span=40).mean().iloc[-1])

                    if cp >= dh and cp > e40:
                        mom = float((cp / c_arr[-15] - 1.0)) if len(c_arr) >= 15 else 0.0
                        if mom > 0:
                            cands.append((sym, mom, buf))

                cands.sort(key=lambda x: x[1], reverse=True)

                for sym, score, buf in cands[:avail]:
                    exec_p = prices.get(sym, buf["close"].iloc[-1])
                    c_arr = buf["close"].values
                    h_arr = buf["high"].values
                    l_arr = buf["low"].values

                    # Volatility sizing
                    log_ret = np.log(np.maximum(c_arr[1:] / np.maximum(c_arr[:-1], 1e-8), 1e-8))
                    ann_vol = float(pd.Series(log_ret).rolling(60).std().iloc[-1] * np.sqrt(365.25 * 6)) if len(log_ret) >= 60 else 0.60
                    ann_vol = np.clip(ann_vol, 0.15, 2.50)

                    target_tv = float(spec.get("target_annual_vol", spec.get("risk_param", 0.35)))
                    v_scale = np.clip(target_tv / ann_vol, 0.20, 1.10)
                    alloc = (equity / max_slots) * v_scale * breadth_factor
                    fee = alloc * cost_rate

                    if cash >= (alloc + fee):
                        qty = alloc / exec_p
                        cash -= (alloc + fee)

                        tr = np.maximum(h_arr[1:] - l_arr[1:], np.maximum(np.abs(h_arr[1:] - c_arr[:-1]), np.abs(l_arr[1:] - c_arr[:-1])))
                        atr = float(pd.Series(tr).rolling(14).mean().iloc[-1]) if len(tr) >= 14 else (exec_p * 0.02)
                        stop_p = exec_p - 2.0 * atr

                        conn.execute("""
                        UPDATE positions SET
                            side = 1,
                            qty = ?,
                            entry_price = ?,
                            mark_price = ?,
                            peak_price = ?,
                            stop_price = ?,
                            unrealized_pnl = 0.0,
                            unrealized_pnl_pct = 0.0,
                            opened_at = ?
                        WHERE shadow_id = ? AND symbol = ?
                        """, (qty, exec_p, exec_p, exec_p, stop_p, time.time(), s_id, sym))

                        conn.execute("UPDATE shadows SET cash = ? WHERE id = ?", (cash, s_id))
                        logger.info(f"[SHADOW {s_id}] Entered LONG {sym} @ {exec_p:.2f} | Size: ${alloc:.2f} ({qty:.4f})")

    def toggle_shadow(self, shadow_id: str, action: str) -> bool:
        """action: 'RUNNING', 'PAUSED', 'FLATTEN'"""
        if action in ["RUNNING", "PAUSED", "STOPPED"]:
            return update_shadow_status(shadow_id, action)
        elif action == "FLATTEN":
            with get_db_connection() as conn:
                pos_rows = conn.execute("SELECT * FROM positions WHERE shadow_id = ? AND side != 0", (shadow_id,)).fetchall()
                shadow = conn.execute("SELECT * FROM shadows WHERE id = ?", (shadow_id,)).fetchone()
                if not shadow:
                    return False
                cash = float(shadow["cash"])
                for pos in pos_rows:
                    sym = pos["symbol"]
                    qty = float(pos["qty"])
                    entry_p = float(pos["entry_price"])
                    exec_p = self.feeder.prices.get(sym, entry_p)
                    fee = qty * exec_p * 0.0010
                    pnl = qty * (exec_p - entry_p) - fee
                    pnl_pct = (exec_p - entry_p) / entry_p * 100.0 if entry_p > 0 else 0.0

                    conn.execute("""
                    INSERT INTO trades (shadow_id, symbol, side, qty, entry_price, exit_price, pnl, pnl_pct, fee, holding_hours, closed_at)
                    VALUES (?, ?, 'FLATTEN', ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (shadow_id, sym, qty, entry_p, exec_p, pnl, pnl_pct, fee, (time.time() - pos["opened_at"]) / 3600.0, time.time()))

                    cash += (qty * exec_p - fee)
                    conn.execute("UPDATE positions SET side = 0, qty = 0, unrealized_pnl = 0 WHERE shadow_id = ? AND symbol = ?", (shadow_id, sym))

                conn.execute("UPDATE shadows SET status = 'PAUSED', cash = ?, equity = ?, unrealized_pnl = 0, last_updated = ? WHERE id = ?", (cash, cash, time.time(), shadow_id))
                conn.commit()
            return True
        return False
