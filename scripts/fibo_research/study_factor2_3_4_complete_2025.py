"""Complete Stage 3.1 Review + Stage 3.2 (Factor #3) + Stage 3.3 (Factor #4)
under strict Ceteris Paribus on In-Sample 2024-2025 (<= 2025-12-31T23:59:59+00:00).
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from study_factor1_multi_repo_benchmark_2025 import calc_multi_repo_htf_features
from dao_vang.config.settings import FiboTrendShortConfig
from dao_vang.fibo_short.backtest import (
    DATA_LAKE_5M_DIR,
    IN_SAMPLE_MAX_UTC,
    SHARED_1H_DIR,
    FiboBacktestTrade,
    _simulate_trade_outcome,
    load_historical_1h_frame,
    resample_1h_to_htf,
    summarize_trades,
)
from dao_vang.fibo_short.detector import evaluate_symbol_timeframe


def simulate_custom_trade(
    future_1h: Sequence[dict[str, Any]],
    *,
    entry_price: float,
    stop_loss: float,
    tp1: float,
    tp2: float,
    tp3: float,
    w1: float = 0.50,
    w2: float = 0.30,
    w3: float = 0.20,
    fee_bps: float = 20.0,
    round_trip_fee_bps: float | None = None,
    ratchet_mode: str = "pessimistic_high",
    return_exit_meta: bool = False,
) -> Any:
    """Simulate staged exit with customizable TP weights (w1, w2, w3).

    Both `fee_bps` and `round_trip_fee_bps` are expressed in total round-trip basis points
    (e.g. 10.0 = 0.10% round-trip, 20.0 = 0.20% round-trip), matching `_simulate_trade_outcome`.
    """
    sl_risk = max(1e-9, stop_loss - entry_price)
    tp1_hit = False
    tp2_hit = False
    tp3_hit = False
    remaining_weight = 1.0
    realized_gross_pct = 0.0
    active_sl = stop_loss
    exit_price = entry_price
    exit_time = str(future_1h[0].get("open_time_str", "")) if future_1h else ""
    hold_hours = 0

    for idx, bar in enumerate(future_1h, start=1):
        b_high = float(bar["high"])
        b_low = float(bar["low"])
        b_close = float(bar["close"])
        b_time = str(bar.get("open_time_str") or bar.get("open_time", ""))
        hold_hours = idx

        if b_high >= active_sl:
            stop_fill = max(active_sl, float(bar.get("open", active_sl)))
            loss_pct = (entry_price - stop_fill) / entry_price * 100.0
            realized_gross_pct += remaining_weight * loss_pct
            exit_price = stop_fill
            exit_time = b_time
            remaining_weight = 0.0
            break

        if not tp1_hit and b_low <= tp1:
            tp1_hit = True
            gain1 = (entry_price - tp1) / entry_price * 100.0
            realized_gross_pct += w1 * gain1
            remaining_weight -= w1
            active_sl = entry_price
            exit_price = tp1
            exit_time = b_time

            if (ratchet_mode == "pessimistic_high" and b_high >= active_sl) or (
                ratchet_mode == "close_rebound" and b_close >= active_sl
            ):
                loss_pct = (entry_price - active_sl) / entry_price * 100.0
                realized_gross_pct += remaining_weight * loss_pct
                exit_price = active_sl
                exit_time = b_time
                remaining_weight = 0.0
                break

        if tp1_hit and not tp2_hit and b_low <= tp2:
            tp2_hit = True
            gain2 = (entry_price - tp2) / entry_price * 100.0
            realized_gross_pct += w2 * gain2
            remaining_weight -= w2
            active_sl = tp1
            exit_price = tp2
            exit_time = b_time

            if (ratchet_mode == "pessimistic_high" and b_high >= active_sl) or (
                ratchet_mode == "close_rebound" and b_close >= active_sl
            ):
                loss_pct = (entry_price - active_sl) / entry_price * 100.0
                realized_gross_pct += remaining_weight * loss_pct
                exit_price = active_sl
                exit_time = b_time
                remaining_weight = 0.0
                break

        if tp2_hit and not tp3_hit and b_low <= tp3:
            tp3_hit = True
            gain3 = (entry_price - tp3) / entry_price * 100.0
            realized_gross_pct += w3 * gain3
            remaining_weight = 0.0
            exit_price = tp3
            exit_time = b_time
            break

    if remaining_weight > 0.0 and future_1h:
        last_bar = future_1h[-1]
        last_close = float(last_bar["close"])
        rem_pct = (entry_price - last_close) / entry_price * 100.0
        realized_gross_pct += remaining_weight * rem_pct
        exit_price = last_close
        exit_time = str(last_bar.get("open_time_str") or last_bar.get("open_time", ""))
        hold_hours = len(future_1h)

    total_rt_bps = round_trip_fee_bps if round_trip_fee_bps is not None else fee_bps
    round_trip_fee_pct = total_rt_bps / 100.0
    net_pct = realized_gross_pct - round_trip_fee_pct
    sl_risk_pct = (sl_risk / entry_price) * 100.0
    r_mult = net_pct / sl_risk_pct if sl_risk_pct > 1e-9 else 0.0

    if tp3_hit:
        outcome = "TP3_HIT"
    elif tp2_hit:
        outcome = "TP2_HIT"
    elif tp1_hit:
        outcome = "TP1_HIT"
    elif remaining_weight == 0.0:
        outcome = "STOP_LOSS"
    else:
        outcome = "TIME_EXIT"

    if return_exit_meta:
        return outcome, realized_gross_pct, net_pct, r_mult, tp1_hit, tp2_hit, tp3_hit, exit_price, exit_time, hold_hours
    return outcome, realized_gross_pct, net_pct, r_mult, tp1_hit, tp2_hit, tp3_hit


def collect_all_factor_trades(
    frames: dict[str, pd.DataFrame],
    btc_htf: dict[str, pd.DataFrame],
    fibo_entry_min: float = 0.500,
) -> list[dict[str, Any]]:
    cfg = FiboTrendShortConfig(
        min_prior_pump_pct=0.50,
        min_impulse_drop_pct=0.04,
        fibo_entry_min=fibo_entry_min,
        fibo_entry_max=0.618,
        sl_mode="above_swing_high",
        require_both_h1_conditions=False,
    )

    enriched: list[dict[str, Any]] = []

    for symbol, df in frames.items():
        df = df.loc[df.index <= IN_SAMPLE_MAX_UTC].sort_index()
        if len(df) < 100:
            continue

        h1_records: list[dict[str, Any]] = []
        h1_close_times: list[pd.Timestamp] = []
        for open_ts, row in df.iterrows():
            close_ts = open_ts + pd.Timedelta(hours=1)
            h1_close_times.append(close_ts)
            h1_records.append(
                {
                    "open_time": int(open_ts.timestamp() * 1000),
                    "open_time_str": open_ts.isoformat(),
                    "close_time_ts": close_ts,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0.0)),
                }
            )

        for tf in ("4h", "1d"):
            htf_df = resample_1h_to_htf(df, tf)
            if len(htf_df) < 30:
                continue
            htf_df = calc_multi_repo_htf_features(htf_df)

            htf_records: list[dict[str, Any]] = []
            htf_close_times: list[pd.Timestamp] = []
            for idx_htf, (open_ts, row) in enumerate(htf_df.iterrows()):
                c_ts = pd.Timestamp(row["close_time"])
                htf_close_times.append(c_ts)
                htf_records.append(
                    {
                        "htf_idx": idx_htf,
                        "open_time": int(open_ts.timestamp() * 1000),
                        "open_time_str": open_ts.isoformat(),
                        "close_time_ts": c_ts,
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row.get("volume", 0.0)),
                        "robust_vol": float(row["robust_vol"]),
                        "ewmac_4_16": float(row["ewmac_4_16"]),
                        "ewmac_16_64": float(row["ewmac_16_64"]),
                        "accel_4_16": float(row["accel_4_16"]),
                        "vol_ratio_20": float(row["vol_ratio_20"]),
                    }
                )

            htf_by_open_str = {r["open_time_str"]: r for r in htf_records}

            htf_ptr = 0
            n_htf = len(htf_records)
            cooldown_until_epoch_h = -1
            consumed_waves: set[str] = set()
            horizon = cfg.horizon_hours if tf == "4h" else max(cfg.horizon_hours, 120)

            for idx_1h in range(24, len(h1_records) - 2):
                current_decision_ts = h1_close_times[idx_1h]
                decision_epoch_h = int(current_decision_ts.timestamp() // 3600)
                if decision_epoch_h < cooldown_until_epoch_h:
                    continue

                while htf_ptr < n_htf and htf_close_times[htf_ptr] <= current_decision_ts:
                    htf_ptr += 1

                if htf_ptr < 10:
                    continue

                start_htf = max(0, htf_ptr - cfg.swing_lookback_bars - 24)
                visible_htf = htf_records[start_htf:htf_ptr]
                visible_1h = h1_records[max(0, idx_1h - 24) : idx_1h + 1]

                sig = evaluate_symbol_timeframe(
                    symbol=symbol,
                    timeframe=tf,
                    klines_htf=visible_htf,
                    klines_1h=visible_1h,
                    config=cfg,
                )
                if sig is None or sig.stage != "FIRED_CONFIRMED_SHORT" or sig.trade_setup is None:
                    continue

                wave_key = f"{tf}:{sig.wave.swing_high_time}:{sig.wave.impulse_low_time}"
                if wave_key in consumed_waves:
                    continue

                future_slice = h1_records[idx_1h + 1 : min(len(h1_records), idx_1h + 1 + horizon)]
                if not future_slice:
                    continue

                setup = sig.trade_setup
                (
                    outcome,
                    exit_price,
                    exit_time,
                    observed_bars,
                    tp1_hit,
                    tp2_hit,
                    tp3_hit,
                    gross_pct,
                    net_pct,
                    r_mult,
                    ratcheted_sl_hit,
                    time_exit_used,
                ) = _simulate_trade_outcome(
                    future_slice,
                    entry_price=setup.entry_price,
                    stop_loss=setup.stop_loss,
                    tp1=setup.tp1,
                    tp2=setup.tp2,
                    tp3=setup.tp3,
                    return_exit_flags=True,
                )

                exit_bar_idx = max(0, min(len(future_slice) - 1, observed_bars - 1))
                exit_bar = future_slice[exit_bar_idx]
                exit_close_ts = (
                    pd.Timestamp(exit_bar["close_time_ts"])
                    if "close_time_ts" in exit_bar
                    else (pd.Timestamp(exit_time) + pd.Timedelta(hours=1))
                )
                if exit_close_ts.tzinfo is None:
                    exit_close_ts = exit_close_ts.tz_localize("UTC")
                else:
                    exit_close_ts = exit_close_ts.tz_convert("UTC")
                exit_close_epoch_h = int(exit_close_ts.timestamp() // 3600)
                real_hold_hours = max(1, exit_close_epoch_h - decision_epoch_h)

                consumed_waves.add(wave_key)
                cooldown_until_epoch_h = max(exit_close_epoch_h, decision_epoch_h + 4)

                trade_obj = FiboBacktestTrade(
                    trade_id=f"{sig.id}_{decision_epoch_h}",
                    symbol=symbol,
                    higher_timeframe=tf,
                    confirmation_tier=sig.h1_confirmation.confirmation_tier,
                    pattern_name=sig.h1_confirmation.pattern_name,
                    entry_time=current_decision_ts.isoformat(),
                    exit_time=exit_close_ts.isoformat(),
                    entry_price=setup.entry_price,
                    stop_loss=setup.stop_loss,
                    tp1=setup.tp1,
                    tp2=setup.tp2,
                    tp3=setup.tp3,
                    exit_price=exit_price,
                    outcome=outcome,
                    tp1_reached=tp1_hit,
                    tp2_reached=tp2_hit,
                    tp3_reached=tp3_hit,
                    gross_return_pct=round(gross_pct, 4),
                    net_return_pct=round(net_pct, 4),
                    r_multiple=round(r_mult, 4),
                    hold_hours=real_hold_hours,
                    fibo_entry_ratio=sig.h1_confirmation.current_fibo_ratio,
                    impulse_drop_pct=sig.wave.impulse_drop_pct,
                    prior_pump_pct=sig.wave.prior_pump_pct,
                    ratcheted_sl_hit=ratcheted_sl_hit,
                    time_exit_used=time_exit_used,
                    decision_time=current_decision_ts.isoformat(),
                )

                peak_bar = htf_by_open_str.get(sig.wave.swing_high_time)
                low_bar = htf_by_open_str.get(sig.wave.prior_low_time)
                imp_bar = htf_by_open_str.get(sig.wave.impulse_low_time)
                cur_htf_bar = visible_htf[-1]
                if peak_bar is None or low_bar is None or imp_bar is None:
                    continue

                p_idx = peak_bar["htf_idx"]
                l_idx = low_bar["htf_idx"]
                imp_idx = imp_bar["htf_idx"]
                cur_idx = cur_htf_bar["htf_idx"]

                # --- Factor #1 features ---
                wave_bars = htf_records[l_idx : p_idx + 1]
                if len(wave_bars) >= 2:
                    closes_w = np.array([b["close"] for b in wave_bars], dtype=float)
                    net_chg = abs(closes_w[-1] - closes_w[0])
                    path_chg = float(np.sum(np.abs(np.diff(closes_w))))
                    ker_wave = net_chg / path_chg if path_chg > 1e-9 else 1.0
                else:
                    ker_wave = 1.0

                pst_pass = (peak_bar["ewmac_16_64"] <= 0.0) or (cur_htf_bar["accel_4_16"] <= -1.0)
                f1_elite = pst_pass and (ker_wave >= 0.35)
                f1_expanded = f1_elite or (ker_wave >= 0.65)

                # --- Factor #2 features ---
                swing_high = sig.wave.swing_high_price
                prior_low = sig.wave.prior_low_price
                impulse_low = sig.wave.impulse_low_price
                impulse_range = max(0.0, swing_high - impulse_low)
                imp_drop_pct = (impulse_range / swing_high) * 100.0
                imp_bars = max(1, imp_idx - p_idx)
                imp_days_equiv = imp_bars * (4.0 / 24.0 if tf == "4h" else 1.0)
                imp_slice = htf_records[p_idx : imp_idx + 1]
                if len(imp_slice) >= 2:
                    closes_imp = np.array([b["close"] for b in imp_slice], dtype=float)
                    net_imp = abs(closes_imp[-1] - closes_imp[0])
                    path_imp = float(np.sum(np.abs(np.diff(closes_imp))))
                    imp_ker = net_imp / path_imp if path_imp > 1e-9 else 1.0
                else:
                    imp_ker = 1.0

                drop_only_bars = htf_records[p_idx + 1 : imp_idx + 1] or [imp_bar]
                imp_mean_vol = float(np.mean([b["volume"] for b in drop_only_bars]))

                # --- Factor #3 features (Fibonacci Pullback & H1 Confirmation) ---
                max_fibo_ratio = sig.h1_confirmation.max_pullback_fibo_ratio
                cur_fibo_ratio = sig.h1_confirmation.current_fibo_ratio

                # Pullback volume on HTF (after impulse_low up to cur_idx) and on H1 pullback leg
                recent_1h = visible_1h[-16:]
                min_1h_idx = min(range(len(recent_1h)), key=lambda i: float(recent_1h[i]["low"]))
                pb_1h_leg = recent_1h[min_1h_idx + 1 :] or [recent_1h[-1]]
                drop_1h_leg = recent_1h[: min_1h_idx + 1] or [recent_1h[0]]
                pb_1h_vol = float(np.mean([b["volume"] for b in pb_1h_leg]))
                drop_1h_vol = float(np.mean([b["volume"] for b in drop_1h_leg]))
                pullback_vol_ratio_1h = pb_1h_vol / max(1e-9, drop_1h_vol)

                pb_htf_bars = htf_records[imp_idx + 1 : cur_idx + 1]
                if pb_htf_bars:
                    pb_htf_vol = float(np.mean([b["volume"] for b in pb_htf_bars]))
                    pullback_vol_ratio_htf = pb_htf_vol / max(1e-9, imp_mean_vol)
                else:
                    pullback_vol_ratio_htf = pullback_vol_ratio_1h

                # H1 candle anatomy
                c_1h = visible_1h[-1]
                p_1h = visible_1h[-2]
                c_open = float(c_1h["open"])
                c_high = float(c_1h["high"])
                c_low = float(c_1h["low"])
                c_close = float(c_1h["close"])
                c_range = max(1e-9, c_high - c_low)
                h1_body_ratio = abs(c_close - c_open) / c_range
                h1_upper_wick_ratio = (c_high - max(c_open, c_close)) / c_range
                broke_prev_h1_low = c_close < float(p_1h["low"])
                broke_below_050 = c_close < sig.fibo_levels.level_0500

                # BTC Context
                bdf = btc_htf[tf]
                entry_ts = pd.Timestamp(trade_obj.entry_time)
                past_btc = bdf.loc[pd.to_datetime(bdf["close_time"]) <= entry_ts]
                if len(past_btc) >= 5:
                    last_btc = past_btc.iloc[-1]
                    btc_ewmac_4_16 = float(last_btc["ewmac_4_16"])
                    lb = min(len(past_btc) - 1, max(1, p_idx - l_idx))
                    btc_ret_pct = float(
                        (last_btc["close"] - past_btc.iloc[-1 - lb]["close"])
                        / past_btc.iloc[-1 - lb]["close"]
                        * 100.0
                    )
                else:
                    btc_ewmac_4_16 = 0.0
                    btc_ret_pct = 0.0

                raw_pump_pct = sig.wave.prior_pump_pct * 100.0 if sig.wave.prior_pump_pct < 10.0 else sig.wave.prior_pump_pct
                idiosyncratic_spread = raw_pump_pct - max(0.0, btc_ret_pct)

                enriched.append(
                    {
                        "trade": trade_obj,
                        "future_slice": future_slice,
                        "fibo_levels": sig.fibo_levels,
                        "atr_1h": setup.atr_1h,
                        "symbol": symbol,
                        "tf": tf,
                        "tier": sig.h1_confirmation.confirmation_tier,
                        "pattern_name": sig.h1_confirmation.pattern_name,
                        "cond1_pattern": sig.h1_confirmation.cond1_bearish_pattern,
                        "cond2_break": sig.h1_confirmation.cond2_break_prev_low,
                        "broke_prev_h1_low": broke_prev_h1_low,
                        "broke_below_050": broke_below_050,
                        # Factor 1
                        "prior_pump_pct": raw_pump_pct,
                        "ker_wave": ker_wave,
                        "pst_pass": pst_pass,
                        "f1_elite": f1_elite,
                        "f1_expanded": f1_expanded,
                        "peak_ewmac_16_64": peak_bar["ewmac_16_64"],
                        "cur_accel_4_16": cur_htf_bar["accel_4_16"],
                        "btc_ewmac_4_16": btc_ewmac_4_16,
                        "idiosyncratic_spread": idiosyncratic_spread,
                        # Factor 2
                        "imp_drop_pct": imp_drop_pct,
                        "imp_ker": imp_ker,
                        "imp_days_equiv": imp_days_equiv,
                        "imp_bars": imp_bars,
                        # Factor 3
                        "max_fibo_ratio": max_fibo_ratio,
                        "cur_fibo_ratio": cur_fibo_ratio,
                        "pullback_vol_ratio_1h": pullback_vol_ratio_1h,
                        "pullback_vol_ratio_htf": pullback_vol_ratio_htf,
                        "h1_body_ratio": h1_body_ratio,
                        "h1_upper_wick_ratio": h1_upper_wick_ratio,
                        "bars_since_imp_low": sig.wave.bars_since_impulse_low,
                    }
                )

    return enriched


def show(label: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    trades = [x["trade"] for x in items]
    s = summarize_trades(trades)
    avg_r = float(np.mean([t.r_multiple for t in trades])) if trades else 0.0
    sum_r = float(np.sum([t.r_multiple for t in trades])) if trades else 0.0
    s["avg_r"] = round(avg_r, 3)
    s["sum_r"] = round(sum_r, 2)
    print(
        f"  {label:64s} | N={s['total_trades']:3d} | WR={s['win_rate_pct']:5.2f}% | "
        f"TP1={s['tp1_hit_rate_pct']:5.2f}% | Avg={s['avg_net_return_pct']:+6.3f}% | "
        f"Tot={s['total_net_return_pct']:+7.2f}% | PF={s['profit_factor']:4.2f} | "
        f"AvgR={avg_r:+.2f}R | DD={s['max_drawdown_pct']:5.1f}%"
    )
    return s


def main() -> None:
    default_syms = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "LTCUSDT", "BCHUSDT"]
    alt_syms = [
        "1000PEPEUSDT",
        "1000BONKUSDT",
        "1000SHIBUSDT",
        "AAVEUSDT",
        "ADAUSDT",
        "1INCHUSDT",
        "ACEUSDT",
        "AKTUSDT",
    ]
    symbols = [
        s
        for s in default_syms + alt_syms
        if (SHARED_1H_DIR / f"{s}_1h.parquet").exists()
        or (DATA_LAKE_5M_DIR / f"{s}.parquet").exists()
    ]
    frames = {
        sym: load_historical_1h_frame(
            sym,
            start_utc="2024-01-01T00:00:00+00:00",
            end_utc=IN_SAMPLE_MAX_UTC,
            strict_in_sample=True,
        )
        for sym in symbols
    }

    btc_df = frames["BTCUSDT"].loc[frames["BTCUSDT"].index <= IN_SAMPLE_MAX_UTC].sort_index()
    btc_htf = {
        tf: calc_multi_repo_htf_features(resample_1h_to_htf(btc_df, tf))
        for tf in ("4h", "1d")
    }

    items_050 = collect_all_factor_trades(frames, btc_htf, fibo_entry_min=0.500)
    items_038 = collect_all_factor_trades(frames, btc_htf, fibo_entry_min=0.382)

    report: dict[str, Any] = {}

    print("\n================================================================================================================")
    print("STAGE 3.1 REVIEW — KHÓA FACTOR #2 (`imp_drop_pct >= 6%` & `imp_ker >= 0.50`) TRÊN CẢ 2 CHẾ ĐỘ & ĐA KHUNG (H4/D1)")
    print("================================================================================================================")
    f1_exp = [x for x in items_050 if x["f1_expanded"]]
    f1_eli = [x for x in items_050 if x["f1_elite"]]

    f2_exp_locked = [x for x in f1_exp if x["imp_drop_pct"] >= 6.0 and x["imp_ker"] >= 0.50]
    f2_eli_locked = [x for x in f1_eli if x["imp_drop_pct"] >= 6.0 and x["imp_ker"] >= 0.50]

    report["stage_3_1_f2_locked"] = {
        "f1_expanded_base": show("F1 Mở Rộng (Baseline trước khi lọc F2)", f1_exp),
        "f1_expanded_plus_f2": show("★ F1 Mở Rộng + F2 (`Drop >= 6%` & `imp_ker >= 0.50`)", f2_exp_locked),
        "f1_expanded_rejected_f2": show("  [Bị F2 loại bỏ] Nhịp sập zíc-zắc (`imp_ker < 0.50` hoặc `<6%`)", [x for x in f1_exp if not (x["imp_drop_pct"] >= 6.0 and x["imp_ker"] >= 0.50)]),
        "f1_elite_base": show("F1 Tinh Hoa (Baseline trước khi lọc F2)", f1_eli),
        "f1_elite_plus_f2": show("★ F1 Tinh Hoa + F2 (`Drop >= 6%` & `imp_ker >= 0.50`)", f2_eli_locked),
        "f1_elite_rejected_f2": show("  [Bị F2 loại bỏ trên Tinh Hoa] (`imp_ker < 0.50` hoặc `<6%`)", [x for x in f1_eli if not (x["imp_drop_pct"] >= 6.0 and x["imp_ker"] >= 0.50)]),
        "f2_exp_h4": show("  [Đa khung] F1 Mở Rộng + F2 trên H4", [x for x in f2_exp_locked if x["tf"] == "4h"]),
        "f2_exp_d1": show("  [Đa khung] F1 Mở Rộng + F2 trên D1", [x for x in f2_exp_locked if x["tf"] == "1d"]),
    }

    print("\n================================================================================================================")
    print("STAGE 3.2 — THỰC NGHIỆM & REVIEW FACTOR #3 (VÙNG HỒI FIBONACCI & NẾN H1 XÁC NHẬN) TRÊN NỀN F1 + F2 ĐÃ KHÓA")
    print("================================================================================================================")
    # Compare 0.382-0.500 vs 0.500-0.618 vs 0.618-0.786 using items_038 filtered by F1+F2
    f2_exp_038 = [x for x in items_038 if x["f1_expanded"] and x["imp_drop_pct"] >= 6.0 and x["imp_ker"] >= 0.50]
    print("\n--- 3A. So Sánh Vùng Chạm Fibonacci (`max_fibo_ratio`: Nông 0.382-0.500 vs Golden Pocket 0.500-0.618 vs Sâu 0.618-0.786) ---")
    report["stage_3_2_fibo_zones"] = {
        "shallow_0382_0500": show("Vùng hồi nông Fibo 0.382 – 0.500 (Chưa tới giá hòa vốn 50%)", [x for x in f2_exp_038 if 0.382 <= x["max_fibo_ratio"] < 0.500]),
        "golden_0500_0618": show("★ Vùng Golden Pocket Fibo 0.500 – 0.618", [x for x in f2_exp_locked if 0.500 <= x["max_fibo_ratio"] <= 0.618]),
        "deep_0618_0786": show("★ Vùng hồi sâu Fibo 0.618 – 0.786 (Quét thanh khoản trên 0.618)", [x for x in f2_exp_locked if 0.618 < x["max_fibo_ratio"] <= 0.786]),
        "very_deep_gt_0786": show("Vùng hồi quá sâu > 0.786 (Sát đỉnh Swing High)", [x for x in f2_exp_locked if x["max_fibo_ratio"] > 0.786]),
        "sweetspot_0500_0786": show("★ Toàn dải Bức Tường Hòa Vốn Fibo 0.500 – 0.786", [x for x in f2_exp_locked if 0.500 <= x["max_fibo_ratio"] <= 0.786]),
    }

    print("\n--- 3B. So Sánh Cơ Chế Xác Nhận H1 (`CANDLE_PATTERN_1` vs `BREAK_STRUCTURE_2` vs `COMBO_1_2`) ---")
    report["stage_3_2_h1_tiers"] = {
        "tier_pattern_only": show("Chỉ có Mẫu Hình Nến H1 (`CANDLE_PATTERN_1` đơn thuần)", [x for x in f2_exp_locked if x["tier"] == "CANDLE_PATTERN_1"]),
        "tier_break_only": show("Chỉ có Phá Vỡ Cấu Trúc H1 (`BREAK_STRUCTURE_2` đơn thuần)", [x for x in f2_exp_locked if x["tier"] == "BREAK_STRUCTURE_2"]),
        "tier_combo_1_2": show("★ Hội Tụ Kép H1 (`COMBO_1_2`: Mẫu hình nến + Phá đáy H1/Fibo 0.5)", [x for x in f2_exp_locked if x["tier"] == "COMBO_1_2"]),
        "has_cond2_break": show("★ Có Phá Vỡ Cấu Trúc H1 (`BREAK_STRUCTURE_2` HOẶC `COMBO_1_2`)", [x for x in f2_exp_locked if x["cond2_break"]]),
        "broke_prev_h1_low": show("  - Trong đó: Đóng nến H1 thủng đáy nến H1 liền trước", [x for x in f2_exp_locked if x["broke_prev_h1_low"]]),
        "broke_below_050": show("  - Trong đó: Đóng nến H1 gãy ngược xuống dưới Fibo 0.500", [x for x in f2_exp_locked if x["broke_below_050"]]),
    }

    print("\n--- 3C. Cạn Kiệt Thanh Khoản Nhịp Hồi (`pullback_vol_ratio_1h`) & Độ Đặc Thân Nến H1 (`h1_body_ratio`) ---")
    report["stage_3_2_volume_and_anatomy"] = {
        "pb_vol_dry_le_11": show("★ Volume nhịp hồi H1 cạn kiệt (<= 1.1x Volume nhịp sập)", [x for x in f2_exp_locked if x["pullback_vol_ratio_1h"] <= 1.1]),
        "pb_vol_high_gt_11": show("Volume nhịp hồi H1 bùng nổ mạnh (> 1.1x Volume nhịp sập)", [x for x in f2_exp_locked if x["pullback_vol_ratio_1h"] > 1.1]),
        "h1_body_strong_ge_045": show("Thân nến đỏ H1 dứt khoát (`h1_body_ratio >= 0.45`)", [x for x in f2_exp_locked if x["h1_body_ratio"] >= 0.45]),
        "h1_body_weak_lt_045": show("Thân nến đỏ H1 mỏng (`h1_body_ratio < 0.45`)", [x for x in f2_exp_locked if x["h1_body_ratio"] < 0.45]),
    }

    print("\n--- 3D. REVIEW GATE CHO FACTOR #3 (MA TRẬN TƯƠNG QUAN SPEARMAN) ---")
    df_f3 = pd.DataFrame(f2_exp_locked)
    df_f3["cond2_break_num"] = df_f3["cond2_break"].astype(int)
    df_f3["combo_num"] = (df_f3["tier"] == "COMBO_1_2").astype(int)
    corr_f3 = df_f3[
        [
            "max_fibo_ratio",
            "cur_fibo_ratio",
            "pullback_vol_ratio_1h",
            "cond2_break_num",
            "combo_num",
            "h1_body_ratio",
            "imp_ker",
            "ker_wave",
        ]
    ].corr(method="spearman")
    print(corr_f3.round(3).to_string())
    report["stage_3_2_f3_corr"] = corr_f3.round(3).to_dict()

    print("\n================================================================================================================")
    print("STAGE 3.3 — THỰC NGHIỆM & REVIEW FACTOR #4 (STOP LOSS, TP ALLOCATION & ĐI VỐN CONVICTION SCORE)")
    print("================================================================================================================")
    print("\n--- 4A. So Sánh Vị Trí Đặt Stop Loss (`above_swing_high 1.0` vs `above_0886` vs `above_0786`) ---")
    sl_modes: dict[str, list[dict[str, Any]]] = {
        "sl_1000_swing_high": [],
        "sl_0886_fibo": [],
        "sl_0786_fibo": [],
    }
    for x in f2_exp_locked:
        t0: FiboBacktestTrade = x["trade"]
        fibo = x["fibo_levels"]
        atr = x["atr_1h"]
        ep = t0.entry_price
        delta = fibo.wave_range
        lvl_0886 = fibo.level_0000 + 0.886 * delta

        for mode_key, base_lvl in [
            ("sl_1000_swing_high", fibo.level_1000),
            ("sl_0886_fibo", lvl_0886),
            ("sl_0786_fibo", fibo.level_0786),
        ]:
            sl_price = max(base_lvl, ep * 1.005) + 0.25 * atr
            out, g_pct, n_pct, r_m, tp1_h, tp2_h, tp3_h, ex_p, ex_t, hold_h = simulate_custom_trade(
                x["future_slice"],
                entry_price=ep,
                stop_loss=sl_price,
                tp1=t0.tp1,
                tp2=t0.tp2,
                tp3=t0.tp3,
                return_exit_meta=True,
            )
            t_mod = replace(
                t0,
                stop_loss=sl_price,
                exit_price=round(ex_p, 8),
                exit_time=ex_t,
                hold_hours=hold_h,
                outcome=out,  # type: ignore[arg-type]
                gross_return_pct=round(g_pct, 4),
                net_return_pct=round(n_pct, 4),
                r_multiple=round(r_m, 4),
                tp1_reached=tp1_h,
                tp2_reached=tp2_h,
                tp3_reached=tp3_h,
            )
            sl_modes[mode_key].append({**x, "trade": t_mod})

    report["stage_3_3_sl_modes"] = {
        "above_swing_high_1000": show("★ SL chuẩn trên đỉnh Swing High (Fibo 1.000 + 0.25 ATR)", sl_modes["sl_1000_swing_high"]),
        "above_fibo_0886": show("SL thu hẹp trên mốc Fibo 0.886 (+ 0.25 ATR)", sl_modes["sl_0886_fibo"]),
        "above_fibo_0786": show("SL chặt trên mốc Fibo 0.786 (+ 0.25 ATR)", sl_modes["sl_0786_fibo"]),
    }

    print("\n--- 4B. So Sánh Tỷ Trọng Chốt Lời Từng Phần (TP1 Fibo 0.0 / TP2 Ext 1.272 / TP3 Ext 1.618) ---")
    tp_schemes = [
        ("50_30_20", 0.50, 0.30, 0.20, "★ Phân bổ 50% TP1 / 30% TP2 / 20% TP3 (Khóa BE sớm ở đáy cũ)"),
        ("40_40_20", 0.40, 0.40, 0.20, "Phân bổ 40% TP1 / 40% TP2 / 20% TP3"),
        ("60_25_15", 0.60, 0.25, 0.15, "Phân bổ 60% TP1 / 25% TP2 / 15% TP3 (Ăn chắc nhịp test đáy)"),
        ("30_40_30", 0.30, 0.40, 0.30, "Phân bổ 30% TP1 / 40% TP2 / 30% TP3 (Nuôi sóng dài)"),
    ]
    report["stage_3_3_tp_allocations"] = {}
    for key, w1, w2, w3, label in tp_schemes:
        mod_list = []
        for x in f2_exp_locked:
            t0 = x["trade"]
            out, g_pct, n_pct, r_m, tp1_h, tp2_h, tp3_h, ex_p, ex_t, hold_h = simulate_custom_trade(
                x["future_slice"],
                entry_price=t0.entry_price,
                stop_loss=t0.stop_loss,
                tp1=t0.tp1,
                tp2=t0.tp2,
                tp3=t0.tp3,
                w1=w1,
                w2=w2,
                w3=w3,
                return_exit_meta=True,
            )
            t_mod = replace(
                t0,
                exit_price=round(ex_p, 8),
                exit_time=ex_t,
                hold_hours=hold_h,
                outcome=out,  # type: ignore[arg-type]
                gross_return_pct=round(g_pct, 4),
                net_return_pct=round(n_pct, 4),
                r_multiple=round(r_m, 4),
                tp1_reached=tp1_h,
                tp2_reached=tp2_h,
                tp3_reached=tp3_h,
            )
            mod_list.append({**x, "trade": t_mod})
        report["stage_3_3_tp_allocations"][key] = show(label, mod_list)

    print("\n--- 4C. Thang Điểm Hội Tụ 4 Nhân Tố (`0–100 Conviction Score`) & Đi Vốn Động (`Dynamic Sizing`) ---")
    # Compute full 4-Factor Orthogonal Conviction Score on all 480 trades (Mốc 1)
    for x in items_050:
        score = 0.0
        # 1. Layer 1 (F1A: Pump Exhaustion, max 15)
        if x["prior_pump_pct"] >= 100.0:
            score += 15.0
        elif x["prior_pump_pct"] >= 70.0:
            score += 11.0
        else:
            score += 7.0

        # 2. Layer 2 Wave & Impulse Physics (F1C + F2: max 35)
        if x["ker_wave"] >= 0.65:
            score += 20.0
        elif x["ker_wave"] >= 0.35:
            score += 14.0

        if x["imp_ker"] >= 0.65 and x["imp_drop_pct"] >= 6.0:
            score += 15.0
        elif x["imp_ker"] >= 0.50 and x["imp_drop_pct"] >= 6.0:
            score += 10.0

        # 3. Layer 2/3 Trend & Momentum Collapse (F1B + F1D: max 30)
        if x["peak_ewmac_16_64"] <= 0.0 and x["cur_accel_4_16"] <= -1.0:
            score += 20.0
        elif x["pst_pass"]:
            score += 14.0

        if x["btc_ewmac_4_16"] <= 0.5:
            score += 5.0
        if x["idiosyncratic_spread"] >= 60.0:
            score += 5.0

        # 4. Layer 3/4 Fibo Wall & H1 Confirmation Trigger (F3: max 20)
        if x["tier"] == "COMBO_1_2":
            score += 12.0
        elif x["cond2_break"]:
            score += 9.0
        else:
            score += 4.0

        if x["pullback_vol_ratio_1h"] <= 1.1:
            score += 8.0
        elif x["pullback_vol_ratio_1h"] <= 1.4:
            score += 4.0

        x["full_conviction_score"] = round(score, 1)

    report["stage_3_3_conviction_tiers_all480"] = {
        "reject_lt_55": show("Tier D/C (< 55 điểm — Đứng ngoài / Bỏ qua)", [x for x in items_050 if x["full_conviction_score"] < 55]),
        "tier_b_55_69": show("★ Tier B (55 – 69 điểm — Chuẩn: Đi vốn 0.75R)", [x for x in items_050 if 55 <= x["full_conviction_score"] < 70]),
        "tier_a_70_84": show("★ Tier A (70 – 84 điểm — Tinh Hoa: Đi vốn 1.25R)", [x for x in items_050 if 70 <= x["full_conviction_score"] < 85]),
        "tier_s_ge_85": show("★ Tier S (>= 85 điểm — Siêu Hội Tụ: Đi vốn 2.00R)", [x for x in items_050 if x["full_conviction_score"] >= 85]),
        "active_ge_55": show("★ Tổng hợp các lệnh đạt chuẩn (>= 55 điểm, đi vốn đều 1.0x)", [x for x in items_050 if x["full_conviction_score"] >= 55]),
    }

    # Simulate Dynamic Sizing (0.75x for Tier B, 1.25x for Tier A, 2.0x for Tier S) on locked F1+F2 universe
    active_scored = [x for x in items_050 if x["full_conviction_score"] >= 55]
    dyn_trades = []
    for x in active_scored:
        sc = x["full_conviction_score"]
        mult = 2.0 if sc >= 85 else (1.25 if sc >= 70 else 0.75)
        t0 = x["trade"]
        t_dyn = replace(
            t0,
            gross_return_pct=round(t0.gross_return_pct * mult, 4),
            net_return_pct=round(t0.net_return_pct * mult, 4),
            r_multiple=round(t0.r_multiple * mult, 4),
        )
        dyn_trades.append({**x, "trade": t_dyn})

    report["stage_3_3_dynamic_sizing"] = {
        "flat_sizing_1x": report["stage_3_3_conviction_tiers_all480"]["active_ge_55"],
        "dynamic_sizing_075_125_200": show("★ Đi vốn động theo Conviction Score (0.75x / 1.25x / 2.00x)", dyn_trades),
    }

    print("\n================================================================================================================")
    print("BẢNG TỔNG KẾT LỘ TRÌNH TIẾN HÓA 7 CẤP ĐỘ TOÀN CHIẾN LƯỢC (TỪ MỐC 0 -> FACTOR 1 -> FACTOR 2 -> FACTOR 3 -> FACTOR 4)")
    print("================================================================================================================")
    # Filter progression on locked F1 + F2 + F3 + F4
    m1_f1a = items_050
    m2_f1b = [x for x in items_050 if x["pst_pass"]]
    m3_f1_eli = [x for x in items_050 if x["f1_elite"]]
    m3_f1_exp = [x for x in items_050 if x["f1_expanded"]]
    m4_f2_eli = f2_eli_locked
    m4_f2_exp = f2_exp_locked
    m5_f3_exp = [x for x in f2_exp_locked if x["cond2_break"] and x["max_fibo_ratio"] <= 0.786]
    m5_f3_eli = [x for x in f2_eli_locked if x["cond2_break"] and x["max_fibo_ratio"] <= 0.786]

    # Mốc 6: Apply Factor #4 (SL above_0886 + Dynamic Conviction Sizing) on m5_f3_exp and m4_f2_exp
    score_by_id = {x["trade"].trade_id: x["full_conviction_score"] for x in items_050}
    m6_f4_on_f2_exp = []
    for x in sl_modes["sl_0886_fibo"]:
        sc = score_by_id.get(x["trade"].trade_id, 65.0)
        mult = 1.50 if sc >= 80 else (1.15 if sc >= 68 else 0.80)
        t0 = x["trade"]
        t_m6 = replace(
            t0,
            gross_return_pct=round(t0.gross_return_pct * mult, 4),
            net_return_pct=round(t0.net_return_pct * mult, 4),
            r_multiple=round(t0.r_multiple * mult, 4),
        )
        m6_f4_on_f2_exp.append({**x, "trade": t_m6, "full_conviction_score": sc})

    m6_f4_on_f3_exp = [x for x in m6_f4_on_f2_exp if x["cond2_break"] and x["max_fibo_ratio"] <= 0.786]

    report["cumulative_milestones"] = {
        "m1_f1a_pump50": show("Mốc 1 [F1A]: Sóng bơm >= 50%", m1_f1a),
        "m2_f1b_pst": show("Mốc 2 [+F1B]: + pysystemtrade (ewmac<=0 OR accel<=-1)", m2_f1b),
        "m3_f1c_expanded": show("Mốc 3B [+F1C Mở Rộng]: (PST & KER>=0.35) OR (KER>=0.65)", m3_f1_exp),
        "m3_f1c_elite": show("Mốc 3A [+F1C Tinh Hoa]: PST & KER >= 0.35", m3_f1_eli),
        "m4_f2_expanded": show("Mốc 4B [+F2 Mở Rộng]: + Nhịp sập >= 6% & imp_ker >= 0.50", m4_f2_exp),
        "m4_f2_elite": show("Mốc 4A [+F2 Tinh Hoa]: + Nhịp sập >= 6% & imp_ker >= 0.50", m4_f2_eli),
        "m5_f3_expanded": show("Mốc 5B [+F3 Mở Rộng]: + Fibo 0.5-0.786 & H1 Phá Cấu Trúc (ĐK2)", m5_f3_exp),
        "m5_f3_elite": show("Mốc 5A [+F3 Tinh Hoa]: + Fibo 0.5-0.786 & H1 Phá Cấu Trúc (ĐK2)", m5_f3_eli),
        "m6_f4_expanded": show("★ Mốc 6B [+F4 Toàn Diện]: F1+F2 + SL 0.886 + Đi Vốn Conviction", m6_f4_on_f2_exp),
        "m6_f4_sniper": show("★ Mốc 6A [+F4 Sniper]: F1+F2+F3 + SL 0.886 + Đi Vốn Conviction", m6_f4_on_f3_exp),
    }

    Path("artifacts/fibo_trend_short/factor2_3_4_complete_study_2025.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nSaved complete Factor 2, 3, 4 study to artifacts/fibo_trend_short/factor2_3_4_complete_study_2025.json")


if __name__ == "__main__":
    main()
