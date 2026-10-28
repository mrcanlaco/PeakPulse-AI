"""Comprehensive Independent Verification & Recalculation Script for the Red-Team Audit of
PeakPulse AI — Fibo Trend Short v4.0.0.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parents[1]
SRC_DIR = ROOT_DIR / "src"
for p in (str(SCRIPT_DIR), str(SRC_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from study_factor1_multi_repo_benchmark_2025 import calc_multi_repo_htf_features
from study_oos_2026_all_7_milestones import load_1h_for_oos
from dao_vang.config.settings import FiboTrendShortConfig
from dao_vang.fibo_short.backtest import (
    DATA_LAKE_5M_DIR,
    IN_SAMPLE_MAX_UTC,
    OOS_START_UTC,
    SHARED_1H_DIR,
    FiboBacktestTrade,
    _simulate_trade_outcome,
    load_historical_1h_frame,
    resample_1h_to_htf,
    summarize_trades,
)
from dao_vang.fibo_short.detector import (
    build_fibo_trade_setup,
    compute_atr,
    compute_fibonacci_levels,
    compute_orthogonal_conviction_score,
    detect_htf_reversal_wave,
    evaluate_h1_confirmation,
    evaluate_symbol_timeframe,
)


def calc_htf_features_no_bfill(df_htf: pd.DataFrame) -> pd.DataFrame:
    """Strictly causal HTF feature computation WITHOUT .bfill() (keeps min_periods=1 on EMAs to isolate .bfill() vs .ffill())."""
    from dao_vang.fibo_short.detector import compute_canonical_pst_series

    df = df_htf.copy()
    close = df["close"].astype(float)
    volume = df["volume"].astype(float).clip(lower=0.0)

    r_vol_list, ew4_16_list, ew16_64_list, accel_list = compute_canonical_pst_series(
        close.tolist(),
        use_bfill=False,
    )
    df["robust_vol"] = pd.Series(r_vol_list, index=df.index, dtype="float64")
    df["ewmac_4_16"] = pd.Series(ew4_16_list, index=df.index, dtype="float64")
    df["ewmac_16_64"] = pd.Series(ew16_64_list, index=df.index, dtype="float64")
    df["accel_4_16"] = pd.Series(accel_list, index=df.index, dtype="float64")

    vol_ma20 = volume.rolling(20, min_periods=5).mean()
    df["vol_ratio_20"] = (volume / vol_ma20.replace(0, np.nan)).fillna(1.0)
    return df


def calc_htf_features_with_bfill(df_htf: pd.DataFrame) -> pd.DataFrame:
    """Counterpart to calc_htf_features_no_bfill differing ONLY by use_bfill=True on raw_vol."""
    from dao_vang.fibo_short.detector import compute_canonical_pst_series

    df = df_htf.copy()
    close = df["close"].astype(float)
    volume = df["volume"].astype(float).clip(lower=0.0)

    r_vol_list, ew4_16_list, ew16_64_list, accel_list = compute_canonical_pst_series(
        close.tolist(),
        use_bfill=True,
    )
    df["robust_vol"] = pd.Series(r_vol_list, index=df.index, dtype="float64")
    df["ewmac_4_16"] = pd.Series(ew4_16_list, index=df.index, dtype="float64")
    df["ewmac_16_64"] = pd.Series(ew16_64_list, index=df.index, dtype="float64")
    df["accel_4_16"] = pd.Series(accel_list, index=df.index, dtype="float64")

    vol_ma20 = volume.rolling(20, min_periods=5).mean()
    df["vol_ratio_20"] = (volume / vol_ma20.replace(0, np.nan)).fillna(1.0)
    return df


def _resolve_bar_close_time_str(
    bar: dict[str, Any],
    fallback_entry_ts: pd.Timestamp | None,
    bar_idx_1based: int,
) -> str:
    """Return the exact UTC close timestamp ISO string of a 1h bar (open_time + 1h)."""
    if "close_time_ts" in bar and bar["close_time_ts"] is not None:
        ts = pd.Timestamp(bar["close_time_ts"])
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return ts.isoformat()
    raw_open = bar.get("open_time_str") or bar.get("open_time")
    if raw_open:
        try:
            ts_open = pd.Timestamp(raw_open)
            if ts_open.tzinfo is None:
                ts_open = ts_open.tz_localize("UTC")
            return (ts_open + pd.Timedelta(hours=1)).isoformat()
        except Exception:
            pass
    if fallback_entry_ts is not None:
        return (fallback_entry_ts + pd.Timedelta(hours=bar_idx_1based)).isoformat()
    return ""


def simulate_trade_v2(
    future_bars: list[dict[str, Any]],
    *,
    entry_price: float,
    stop_loss: float,
    tp1: float,
    tp2: float,
    tp3: float,
    w1: float = 0.50,
    w2: float = 0.30,
    w3: float = 0.20,
    round_trip_fee_bps: float = 20.0,
    ratchet_mode: Literal["legacy_bug", "close_rebound", "pessimistic_high"] = "pessimistic_high",
    entry_timestamp_utc: str | pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Unified, single-source trade & bar-by-bar MTM simulator."""
    risk_distance = max(entry_price * 0.002, stop_loss - entry_price)
    risk_pct = (risk_distance / entry_price) * 100.0

    fallback_entry_ts: pd.Timestamp | None = None
    if entry_timestamp_utc is not None:
        fallback_entry_ts = pd.Timestamp(entry_timestamp_utc)
        if fallback_entry_ts.tzinfo is None:
            fallback_entry_ts = fallback_entry_ts.tz_localize("UTC")
    elif future_bars:
        raw0 = future_bars[0].get("open_time_str") or future_bars[0].get("open_time")
        if raw0:
            try:
                fallback_entry_ts = pd.Timestamp(raw0)
                if fallback_entry_ts.tzinfo is None:
                    fallback_entry_ts = fallback_entry_ts.tz_localize("UTC")
            except Exception:
                fallback_entry_ts = None

    tp1_hit = False
    tp2_hit = False
    tp3_hit = False
    ratcheted_sl_hit = False

    remaining_weight = 1.0
    realized_gross_pct = 0.0
    prev_total_gross_pct = 0.0
    active_sl = stop_loss
    exit_price = entry_price
    exit_time = str(future_bars[0].get("open_time_str", "")) if future_bars else ""
    exit_close_time = _resolve_bar_close_time_str(future_bars[0], fallback_entry_ts, 1) if future_bars else ""
    hold_hours = 0

    half_fee_pct = (round_trip_fee_bps / 100.0) * 0.5
    exit_fee_charged = False
    bar_trace: list[dict[str, Any]] = []

    n_bars = len(future_bars)
    for idx, bar in enumerate(future_bars, start=1):
        b_high = float(bar["high"])
        b_low = float(bar["low"])
        b_close = float(bar["close"])
        b_time = str(bar.get("open_time_str") or bar.get("open_time", ""))
        b_close_time = _resolve_bar_close_time_str(bar, fallback_entry_ts, idx)
        hold_hours = idx
        rem_w_start = remaining_weight
        closed_this_bar = False

        # 1. Check active SL before new TP touches on this bar
        if b_high >= active_sl:
            # A short stop cannot fill below the first available opening price
            # when the market gaps through an already active stop.
            stop_fill = max(active_sl, float(bar.get("open", active_sl)))
            loss_pct = ((entry_price - stop_fill) / entry_price) * 100.0
            realized_gross_pct += remaining_weight * loss_pct
            exit_price = stop_fill
            exit_time = b_time
            exit_close_time = b_close_time
            remaining_weight = 0.0
            if tp1_hit:
                ratcheted_sl_hit = True
            closed_this_bar = True

        # 2. Check TP1
        if not closed_this_bar and not tp1_hit and b_low <= tp1:
            tp1_hit = True
            gain1 = ((entry_price - tp1) / entry_price) * 100.0
            realized_gross_pct += w1 * gain1
            remaining_weight -= w1
            active_sl = entry_price  # Ratchet SL to Breakeven
            exit_price = tp1
            exit_time = b_time
            exit_close_time = b_close_time

            if ratchet_mode == "pessimistic_high" and b_high >= active_sl:
                loss_pct = ((entry_price - active_sl) / entry_price) * 100.0
                realized_gross_pct += remaining_weight * loss_pct
                exit_price = active_sl
                exit_time = b_time
                exit_close_time = b_close_time
                remaining_weight = 0.0
                ratcheted_sl_hit = True
                closed_this_bar = True
            elif ratchet_mode == "close_rebound" and b_close >= active_sl:
                loss_pct = ((entry_price - active_sl) / entry_price) * 100.0
                realized_gross_pct += remaining_weight * loss_pct
                exit_price = active_sl
                exit_time = b_time
                exit_close_time = b_close_time
                remaining_weight = 0.0
                ratcheted_sl_hit = True
                closed_this_bar = True

        # 3. Check TP2
        if not closed_this_bar and tp1_hit and not tp2_hit and b_low <= tp2:
            tp2_hit = True
            gain2 = ((entry_price - tp2) / entry_price) * 100.0
            realized_gross_pct += w2 * gain2
            remaining_weight -= w2
            active_sl = tp1  # Ratchet SL to TP1
            exit_price = tp2
            exit_time = b_time
            exit_close_time = b_close_time

            if ratchet_mode == "pessimistic_high" and b_high >= active_sl:
                loss_pct = ((entry_price - active_sl) / entry_price) * 100.0
                realized_gross_pct += remaining_weight * loss_pct
                exit_price = active_sl
                exit_time = b_time
                exit_close_time = b_close_time
                remaining_weight = 0.0
                ratcheted_sl_hit = True
                closed_this_bar = True
            elif ratchet_mode == "close_rebound" and b_close >= active_sl:
                loss_pct = ((entry_price - active_sl) / entry_price) * 100.0
                realized_gross_pct += remaining_weight * loss_pct
                exit_price = active_sl
                exit_time = b_time
                exit_close_time = b_close_time
                remaining_weight = 0.0
                ratcheted_sl_hit = True
                closed_this_bar = True

        # 4. Check TP3
        if not closed_this_bar and tp2_hit and not tp3_hit and b_low <= tp3:
            tp3_hit = True
            gain3 = ((entry_price - tp3) / entry_price) * 100.0
            realized_gross_pct += w3 * gain3
            remaining_weight = 0.0
            exit_price = tp3
            exit_time = b_time
            exit_close_time = b_close_time
            closed_this_bar = True

        # 5. Check Time Exit on final bar of horizon
        time_exit_this_bar = False
        if not closed_this_bar and idx == n_bars and remaining_weight > 1e-6:
            rem_ret = ((entry_price - b_close) / entry_price) * 100.0
            realized_gross_pct += remaining_weight * rem_ret
            exit_price = b_close
            exit_time = b_time
            exit_close_time = b_close_time
            remaining_weight = 0.0
            closed_this_bar = True
            time_exit_this_bar = True

        unrealized_pct = remaining_weight * (((entry_price - b_close) / entry_price) * 100.0) if remaining_weight > 1e-6 else 0.0
        cur_total_gross_pct = realized_gross_pct + unrealized_pct
        delta_gross_pct = cur_total_gross_pct - prev_total_gross_pct
        prev_total_gross_pct = cur_total_gross_pct

        bar_fee_pct = 0.0
        if idx == 1:
            bar_fee_pct += half_fee_pct
        if closed_this_bar and not exit_fee_charged:
            bar_fee_pct += half_fee_pct
            exit_fee_charged = True

        bar_trace.append(
            {
                "bar_idx": idx - 1,
                "open_time_str": b_time,
                "close_time_str": b_close_time,
                "close_price": b_close,
                "rem_weight_start": rem_w_start,
                "rem_weight_end": remaining_weight,
                "active_sl_end": active_sl,
                "delta_gross_pct": delta_gross_pct,
                "bar_fee_pct": bar_fee_pct,
                "closed_this_bar": closed_this_bar,
                "time_exit_this_bar": time_exit_this_bar,
            }
        )

        if closed_this_bar:
            break

    time_exit_used = bool(bar_trace and bar_trace[-1]["time_exit_this_bar"])
    fee_pct = round_trip_fee_bps / 100.0
    net_pct = realized_gross_pct - fee_pct
    r_multiple = net_pct / risk_pct if risk_pct > 1e-6 else 0.0

    if tp3_hit:
        legacy_outcome = "TP3_HIT"
    elif tp2_hit:
        legacy_outcome = "TP2_HIT"
    elif tp1_hit:
        legacy_outcome = "TP1_HIT"
    elif remaining_weight == 0.0 and not time_exit_used:
        legacy_outcome = "STOP_LOSS"
    else:
        legacy_outcome = "TIME_EXIT"

    if tp3_hit:
        detailed_outcome = "TP3_FULL"
    elif tp2_hit and ratcheted_sl_hit:
        detailed_outcome = "TP2_THEN_SL_AT_TP1"
    elif tp2_hit and time_exit_used:
        detailed_outcome = "TP2_THEN_TIME_EXIT"
    elif tp1_hit and ratcheted_sl_hit:
        detailed_outcome = "TP1_THEN_SL_AT_BE"
    elif tp1_hit and time_exit_used:
        detailed_outcome = "TP1_THEN_TIME_EXIT"
    elif not tp1_hit and not time_exit_used:
        detailed_outcome = "INITIAL_STOP_LOSS"
    else:
        detailed_outcome = "NO_TP_TIME_EXIT"

    observed_bars = int(hold_hours)
    real_hold_hours = observed_bars
    exit_close_epoch_h = int(fallback_entry_ts.timestamp() // 3600) + max(1, observed_bars)
    if exit_close_time:
        try:
            ec_ts = pd.Timestamp(exit_close_time)
            if ec_ts.tzinfo is None:
                ec_ts = ec_ts.tz_localize("UTC")
            else:
                ec_ts = ec_ts.tz_convert("UTC")
            exit_close_epoch_h = int(ec_ts.timestamp() // 3600)
            real_hold_hours = max(
                observed_bars,
                max(1, int(round((ec_ts - fallback_entry_ts).total_seconds() / 3600.0))),
            )
        except Exception:
            pass

    return {
        "outcome": legacy_outcome,
        "detailed_outcome": detailed_outcome,
        "terminal_outcome": detailed_outcome,
        "exit_price": round(exit_price, 8),
        "exit_time": exit_time,
        "exit_close_time": exit_close_time,
        "exit_close_epoch_h": exit_close_epoch_h,
        "observed_bars": observed_bars,
        "real_hold_hours": real_hold_hours,
        "hold_hours": real_hold_hours,
        "tp1_hit": tp1_hit,
        "tp2_hit": tp2_hit,
        "tp3_hit": tp3_hit,
        "ratcheted_sl_hit": ratcheted_sl_hit,
        "time_exit_used": time_exit_used,
        "gross_pct": realized_gross_pct,
        "net_pct": net_pct,
        "r_mult": r_multiple,
        "bar_trace": bar_trace,
    }


def collect_candidates_and_run_modes(
    frames: dict[str, pd.DataFrame],
    btc_htf: dict[str, pd.DataFrame],
    *,
    entry_start_ts: pd.Timestamp,
    entry_end_ts: pd.Timestamp,
    strict_prior_low_before_peak: bool = False,
    no_bfill: bool = False,
    swing_right_bars: int = 1,
    swing_left_bars: int = 2,
    lookback_bars: int = 30,
) -> list[dict[str, Any]]:
    """Collect EVERY raw candidate signal (without applying Mốc 1 cooldown/consumed_waves yet),
    so we can evaluate both:
    - Mode A: Subset filtering after Mốc 1 cooldown/consumed_waves
    - Mode B: Standalone Independent Execution per configuration (cooldown & consumed_waves applied only when that config fires!)
    """
    cfg = FiboTrendShortConfig(
        swing_lookback_bars=lookback_bars,
        swing_pivot_left_bars=swing_left_bars,
        swing_pivot_right_bars=swing_right_bars,
        conviction_mult_c=0.80,  # M6 research policy has three sizing bands, including score <55.
        min_prior_pump_pct=0.50,
        min_impulse_drop_pct=0.04,
        fibo_entry_min=0.500,
        fibo_entry_max=0.618,
        sl_mode="above_swing_high",
        require_both_h1_conditions=False,
    )

    all_raw_signals: list[dict[str, Any]] = []

    for symbol, df in frames.items():
        df = df.sort_index()
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
            htf_df = calc_htf_features_no_bfill(htf_df) if no_bfill else calc_htf_features_with_bfill(htf_df)

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
            horizon = cfg.horizon_hours if tf == "4h" else max(cfg.horizon_hours, 120)
            idx_arr = df.index
            bdf = btc_htf[tf]
            btc_close_times = pd.to_datetime(bdf["close_time"])

            cached_htf_ptr = -1
            cached_wave = None

            for idx_1h in range(24, len(h1_records) - 2):
                current_decision_ts = h1_close_times[idx_1h]
                while htf_ptr < n_htf and htf_close_times[htf_ptr] <= current_decision_ts:
                    htf_ptr += 1

                bar_open_ts = idx_arr[idx_1h]
                if bar_open_ts < entry_start_ts or bar_open_ts > entry_end_ts:
                    continue
                if htf_ptr < 10:
                    continue

                start_htf = max(0, htf_ptr - cfg.swing_lookback_bars - 24)
                visible_htf = htf_records[start_htf:htf_ptr]

                if htf_ptr != cached_htf_ptr:
                    cached_htf_ptr = htf_ptr
                    cached_wave = detect_htf_reversal_wave(symbol, visible_htf, tf, cfg)
                if cached_wave is None:
                    continue

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

                future_slice = h1_records[idx_1h + 1 : min(len(h1_records), idx_1h + 1 + horizon)]
                if not future_slice:
                    continue

                peak_bar = htf_by_open_str.get(sig.wave.swing_high_time)
                low_bar = htf_by_open_str.get(sig.wave.prior_low_time)
                imp_bar = htf_by_open_str.get(sig.wave.impulse_low_time)
                cur_htf_bar = visible_htf[-1]
                if peak_bar is None or low_bar is None or imp_bar is None:
                    continue

                p_idx = peak_bar["htf_idx"]
                l_idx = low_bar["htf_idx"]
                imp_idx = imp_bar["htf_idx"]

                if strict_prior_low_before_peak and l_idx >= p_idx:
                    continue

                # Check if Swing High has >= 2 right bars in visible_htf if requested
                if swing_right_bars >= 2:
                    vis_p_idx = next((i for i, b in enumerate(visible_htf) if b["open_time_str"] == sig.wave.swing_high_time), -1)
                    if vis_p_idx < 2 or vis_p_idx > len(visible_htf) - 3:
                        continue
                    pk_h = visible_htf[vis_p_idx]["high"]
                    if not (
                        pk_h >= visible_htf[vis_p_idx - 1]["high"]
                        and pk_h >= visible_htf[vis_p_idx - 2]["high"]
                        and pk_h >= visible_htf[vis_p_idx + 1]["high"]
                        and pk_h >= visible_htf[vis_p_idx + 2]["high"]
                    ):
                        continue

                wave_bars = htf_records[l_idx : p_idx + 1]
                if len(wave_bars) >= 2:
                    closes_w = np.array([b["close"] for b in wave_bars], dtype=float)
                    net_chg = abs(closes_w[-1] - closes_w[0])
                    path_chg = float(np.sum(np.abs(np.diff(closes_w))))
                    ker_wave = net_chg / path_chg if path_chg > 1e-9 else 0.0
                else:
                    ker_wave = 0.0

                pst_pass = (peak_bar["ewmac_16_64"] <= 0.0) or (cur_htf_bar["accel_4_16"] <= -1.0)
                f1_elite = pst_pass and (ker_wave >= 0.35)
                f1_expanded = f1_elite or (ker_wave >= 0.65)

                swing_high = sig.wave.swing_high_price
                impulse_low = sig.wave.impulse_low_price
                impulse_range = max(0.0, swing_high - impulse_low)
                imp_drop_pct = (impulse_range / swing_high) * 100.0
                imp_slice = htf_records[p_idx : imp_idx + 1]
                if len(imp_slice) >= 2:
                    closes_imp = np.array([b["close"] for b in imp_slice], dtype=float)
                    net_imp = abs(closes_imp[-1] - closes_imp[0])
                    path_imp = float(np.sum(np.abs(np.diff(closes_imp))))
                    imp_ker = net_imp / path_imp if path_imp > 1e-9 else 0.0
                else:
                    imp_ker = 0.0

                recent_1h = visible_1h[-16:]
                min_1h_idx = min(range(len(recent_1h)), key=lambda i: float(recent_1h[i]["low"]))
                pb_1h_leg = recent_1h[min_1h_idx + 1 :] or [recent_1h[-1]]
                drop_1h_leg = recent_1h[: min_1h_idx + 1] or [recent_1h[0]]
                pb_1h_vol = float(np.mean([b["volume"] for b in pb_1h_leg]))
                drop_1h_vol = float(np.mean([b["volume"] for b in drop_1h_leg]))
                pullback_vol_ratio_1h = pb_1h_vol / max(1e-9, drop_1h_vol)

                past_btc = bdf.loc[btc_close_times <= current_decision_ts]
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

                raw_pump_pct = (
                    sig.wave.prior_pump_pct * 100.0
                    if sig.wave.prior_pump_pct < 10.0
                    else sig.wave.prior_pump_pct
                )
                idiosyncratic_spread = raw_pump_pct - max(0.0, btc_ret_pct)

                # Legacy inline BTC-spread score kept ONLY in legacy_btc_spread_score for audit comparison
                legacy_score = 0.0
                if raw_pump_pct >= 100.0:
                    legacy_score += 15.0
                elif raw_pump_pct >= 70.0:
                    legacy_score += 11.0
                else:
                    legacy_score += 7.0
                if ker_wave >= 0.65:
                    legacy_score += 20.0
                elif ker_wave >= 0.35:
                    legacy_score += 14.0
                if imp_ker >= 0.65 and imp_drop_pct >= 6.0:
                    legacy_score += 15.0
                elif imp_ker >= 0.50 and imp_drop_pct >= 6.0:
                    legacy_score += 10.0
                if peak_bar["ewmac_16_64"] <= 0.0 and cur_htf_bar["accel_4_16"] <= -1.0:
                    legacy_score += 20.0
                elif pst_pass:
                    legacy_score += 14.0
                if btc_ewmac_4_16 <= 0.5:
                    legacy_score += 5.0
                if idiosyncratic_spread >= 60.0:
                    legacy_score += 5.0
                if sig.h1_confirmation.confirmation_tier == "COMBO_1_2":
                    legacy_score += 12.0
                elif sig.h1_confirmation.cond2_break_prev_low:
                    legacy_score += 9.0
                else:
                    legacy_score += 4.0
                if pullback_vol_ratio_1h <= 1.1:
                    legacy_score += 8.0
                elif pullback_vol_ratio_1h <= 1.4:
                    legacy_score += 4.0

                # Canonical 4-Factor Orthogonal Conviction Score (100% unified with detector.py)
                canonical_score, conviction_tier, canonical_mult, alpha_layers = compute_orthogonal_conviction_score(
                    prior_pump_pct=sig.wave.prior_pump_pct,
                    impulse_drop_pct=sig.wave.impulse_drop_pct,
                    fibo_retrace_ratio=sig.h1_confirmation.max_pullback_fibo_ratio,
                    wave_ker=ker_wave,
                    impulse_ker=imp_ker,
                    peak_ewmac_16_64=float(peak_bar["ewmac_16_64"]),
                    cur_accel_4_16=float(cur_htf_bar["accel_4_16"]),
                    confirmation_tier=sig.h1_confirmation.confirmation_tier,
                    pullback_vol_ratio=sig.h1_confirmation.pullback_vol_ratio,
                    h1_body_ratio=sig.h1_confirmation.h1_body_ratio,
                    config=cfg,
                )

                wave_key = f"{tf}:{sig.wave.swing_high_time}:{sig.wave.impulse_low_time}"
                decision_time_str = current_decision_ts.isoformat()
                all_raw_signals.append(
                    {
                        "symbol": symbol,
                        "tf": tf,
                        "idx_1h": idx_1h,
                        "wave_key": wave_key,
                        "sig": sig,
                        "setup": sig.trade_setup,
                        "fibo_levels": sig.fibo_levels,
                        "atr_1h": sig.trade_setup.atr_1h,
                        "future_slice": future_slice,
                        "year": int(current_decision_ts.year),
                        "signal_candle_open_time": h1_records[idx_1h]["open_time_str"],
                        "decision_time": decision_time_str,
                        "l_idx": l_idx,
                        "p_idx": p_idx,
                        "imp_idx": imp_idx,
                        "same_bar_low_high": (l_idx == p_idx),
                        "prior_pump_pct": raw_pump_pct,
                        "ker_wave": ker_wave,
                        "pst_pass": pst_pass,
                        "f1_elite": f1_elite,
                        "f1_expanded": f1_expanded,
                        "imp_drop_pct": imp_drop_pct,
                        "imp_ker": imp_ker,
                        "cond2_break": sig.h1_confirmation.cond2_break_prev_low,
                        "max_fibo_ratio": sig.h1_confirmation.max_pullback_fibo_ratio,
                        "pullback_vol_ratio_1h": sig.h1_confirmation.pullback_vol_ratio,
                        "h1_body_ratio": sig.h1_confirmation.h1_body_ratio,
                        "full_conviction_score": canonical_score,
                        "detector_score": sig.score,
                        "conviction_tier": conviction_tier,
                        "recommended_risk_mult": canonical_mult,
                        "legacy_btc_spread_score": round(legacy_score, 1),
                    }
                )

    return all_raw_signals


def passes_milestone_gate(cand: dict[str, Any], milestone: str) -> bool:
    if milestone == "m1_f1a_pump50":
        return True
    if milestone == "m2_f1b_pst":
        return bool(cand["pst_pass"])
    if milestone == "m3_f1c_expanded":
        return bool(cand["f1_expanded"])
    if milestone == "m3_f1c_elite":
        return bool(cand["f1_elite"])
    if milestone == "m4_f2_expanded":
        return bool(cand["f1_expanded"] and cand["imp_drop_pct"] >= 6.0 and cand["imp_ker"] >= 0.50)
    if milestone == "m4_f2_elite":
        return bool(cand["f1_elite"] and cand["imp_drop_pct"] >= 6.0 and cand["imp_ker"] >= 0.50)
    if milestone in ("m5_f3_expanded", "m6_f4_sniper"):
        return bool(
            cand["f1_expanded"]
            and cand["imp_drop_pct"] >= 6.0
            and cand["imp_ker"] >= 0.50
            and cand["cond2_break"]
            and cand["max_fibo_ratio"] <= 0.786
        )
    if milestone in ("m5_f3_elite", "m6_f4_elite_sniper"):
        return bool(
            cand["f1_elite"]
            and cand["imp_drop_pct"] >= 6.0
            and cand["imp_ker"] >= 0.50
            and cand["cond2_break"]
            and cand["max_fibo_ratio"] <= 0.786
        )
    if milestone == "m6_f4_expanded":
        return bool(cand["f1_expanded"] and cand["imp_drop_pct"] >= 6.0 and cand["imp_ker"] >= 0.50)
    if milestone == "score_ge_55_1x":
        return bool(cand["full_conviction_score"] >= 55.0)
    if milestone == "score_ge_68_1x":
        return bool(cand["full_conviction_score"] >= 68.0)
    if milestone == "score_ge_80_1x":
        return bool(cand["full_conviction_score"] >= 80.0)
    raise ValueError(f"Unknown milestone: {milestone}")


def _resolve_candidate_decision_ts(c: dict[str, Any]) -> pd.Timestamp:
    """Resolve real UTC decision timestamp for a candidate dictionary."""
    if "decision_ts" in c and isinstance(c["decision_ts"], pd.Timestamp):
        ts = c["decision_ts"]
    else:
        sig = c.get("sig")
        d_str = str(c.get("decision_time") or (sig.signal_time if sig is not None else c.get("entry_time", "")))
        ts = pd.Timestamp(d_str)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def execute_configuration(
    raw_candidates: list[dict[str, Any]],
    milestone: str,
    *,
    execution_mode: Literal["subset_from_m1", "standalone_independent"] = "standalone_independent",
    ratchet_mode: Literal["legacy_bug", "close_rebound", "pessimistic_high"] = "pessimistic_high",
    fix_m6_exit_fields: bool = True,
    round_trip_fee_bps: float = 20.0,
    reset_at_oos_boundary: bool = True,
    sizing_mode: Literal["conviction_150_115_080", "fixed_1x"] = "conviction_150_115_080",
) -> list[dict[str, Any]]:
    """Run either Subset-from-Mốc-1 or Standalone Independent execution for a milestone.

    Chronological ordering and cooldown tracking use real UTC timestamps (`decision_epoch_h`),
    making execution 100% invariant to local DataFrame starting index (`idx_1h`) offsets.
    When `reset_at_oos_boundary=True` (default), cooldown and consumed waves reset across the
    `2026-01-01T00:00:00+00:00` IS/OOS boundary so OOS evaluation is invariant to whether IS
    candidates were concatenated into `raw_candidates`.
    """
    if sizing_mode not in ("conviction_150_115_080", "fixed_1x"):
        raise ValueError(f"Unsupported sizing_mode: {sizing_mode!r}")
    oos_boundary_epoch_h = int(pd.Timestamp("2026-01-01T00:00:00+00:00").timestamp() // 3600)

    by_sym_tf: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for c in raw_candidates:
        by_sym_tf.setdefault((c["symbol"], c["tf"]), []).append(c)

    selected: list[dict[str, Any]] = []
    is_m6 = milestone.startswith("m6_")

    for (sym, tf), c_list in by_sym_tf.items():
        c_list.sort(key=lambda x: (int(_resolve_candidate_decision_ts(x).timestamp() // 3600), int(x.get("idx_1h", 0))))
        cooldown_until_epoch_h = -1
        consumed_waves: set[str] = set()
        in_oos_regime = False

        for c in c_list:
            idx_1h = int(c.get("idx_1h", 0))
            wave_key = c["wave_key"]
            sig = c["sig"]
            decision_ts = _resolve_candidate_decision_ts(c)
            decision_ts_str = decision_ts.isoformat()
            decision_epoch_h = int(decision_ts.timestamp() // 3600)

            if reset_at_oos_boundary and not in_oos_regime and decision_epoch_h >= oos_boundary_epoch_h:
                in_oos_regime = True
                cooldown_until_epoch_h = -1
                consumed_waves = set()

            if execution_mode == "standalone_independent":
                # Filter by milestone gate BEFORE checking/consuming cooldown & wave!
                if not passes_milestone_gate(c, milestone):
                    continue
                if decision_epoch_h < cooldown_until_epoch_h or wave_key in consumed_waves:
                    continue
            else:
                # Subset from Mốc 1: Mốc 1 consumes wave & sets cooldown first
                if decision_epoch_h < cooldown_until_epoch_h or wave_key in consumed_waves:
                    continue

            setup = c["setup"]
            fibo = c["fibo_levels"]
            atr = c["atr_1h"]
            ep = setup.entry_price

            # Base simulation (SL 1.000)
            sim_base = simulate_trade_v2(
                c["future_slice"],
                entry_price=ep,
                stop_loss=setup.stop_loss,
                tp1=setup.tp1,
                tp2=setup.tp2,
                tp3=setup.tp3,
                round_trip_fee_bps=round_trip_fee_bps,
                ratchet_mode=ratchet_mode,
                entry_timestamp_utc=decision_ts,
            )

            # Mốc 6 simulation (SL 0.886 + 0.25 ATR)
            lvl_0886 = fibo.level_0000 + 0.886 * fibo.wave_range
            sl_0886 = max(lvl_0886, ep * 1.005) + 0.25 * atr
            sim_m6 = simulate_trade_v2(
                c["future_slice"],
                entry_price=ep,
                stop_loss=sl_0886,
                tp1=setup.tp1,
                tp2=setup.tp2,
                tp3=setup.tp3,
                round_trip_fee_bps=round_trip_fee_bps,
                ratchet_mode=ratchet_mode,
                entry_timestamp_utc=decision_ts,
            )

            active_sim = sim_m6 if is_m6 else sim_base
            used_hold_hours = (
                active_sim["hold_hours"]
                if (not is_m6 or fix_m6_exit_fields)
                else sim_base["hold_hours"]
            )
            used_exit_time = (
                (active_sim.get("exit_close_time") or active_sim["exit_time"])
                if (not is_m6 or fix_m6_exit_fields)
                else (sim_base.get("exit_close_time") or sim_base["exit_time"])
            )
            used_exit_price = (
                active_sim["exit_price"]
                if (not is_m6 or fix_m6_exit_fields)
                else sim_base["exit_price"]
            )

            used_exit_ts = pd.Timestamp(used_exit_time)
            if used_exit_ts.tzinfo is None:
                used_exit_ts = used_exit_ts.tz_localize("UTC")
            else:
                used_exit_ts = used_exit_ts.tz_convert("UTC")
            used_exit_epoch_h = int(used_exit_ts.timestamp() // 3600)

            if execution_mode == "standalone_independent":
                consumed_waves.add(wave_key)
                cooldown_until_epoch_h = max(
                    used_exit_epoch_h,
                    decision_epoch_h + max(4, int(used_hold_hours)),
                )
            else:
                # In subset mode, Mốc 1 always sets cooldown using sim_base real exit_close_time
                m1_exit_str = str(sim_base.get("exit_close_time") or sim_base["exit_time"])
                m1_exit_ts = pd.Timestamp(m1_exit_str)
                if m1_exit_ts.tzinfo is None:
                    m1_exit_ts = m1_exit_ts.tz_localize("UTC")
                else:
                    m1_exit_ts = m1_exit_ts.tz_convert("UTC")
                m1_exit_epoch_h = int(m1_exit_ts.timestamp() // 3600)
                consumed_waves.add(wave_key)
                cooldown_until_epoch_h = max(
                    m1_exit_epoch_h,
                    decision_epoch_h + max(4, int(sim_base["hold_hours"])),
                )
                if not passes_milestone_gate(c, milestone):
                    continue

            sc = float(c["full_conviction_score"])
            mult = (
                (1.50 if sc >= 80 else (1.15 if sc >= 68 else 0.80))
                if is_m6 and sizing_mode == "conviction_150_115_080"
                else 1.0
            )

            t_obj = FiboBacktestTrade(
                trade_id=f"{sig.id}_{decision_epoch_h}",
                symbol=sym,
                higher_timeframe=tf,
                confirmation_tier=sig.h1_confirmation.confirmation_tier,
                pattern_name=sig.h1_confirmation.pattern_name,
                entry_time=decision_ts_str,
                exit_time=used_exit_time,
                entry_price=ep,
                stop_loss=sl_0886 if is_m6 else setup.stop_loss,
                tp1=setup.tp1,
                tp2=setup.tp2,
                tp3=setup.tp3,
                exit_price=used_exit_price,
                outcome=active_sim["outcome"],  # type: ignore[arg-type]
                tp1_reached=active_sim["tp1_hit"],
                tp2_reached=active_sim["tp2_hit"],
                tp3_reached=active_sim["tp3_hit"],
                gross_return_pct=round(active_sim["gross_pct"] * mult, 4),
                net_return_pct=round(active_sim["net_pct"] * mult, 4),
                r_multiple=round(active_sim["r_mult"] * mult, 4),
                hold_hours=used_hold_hours,
                fibo_entry_ratio=sig.h1_confirmation.current_fibo_ratio,
                impulse_drop_pct=sig.wave.impulse_drop_pct,
                prior_pump_pct=sig.wave.prior_pump_pct,
                terminal_outcome=active_sim["detailed_outcome"],
                ratcheted_sl_hit=active_sim["ratcheted_sl_hit"],
                time_exit_used=active_sim["time_exit_used"],
                decision_time=decision_ts_str,
            )

            selected.append(
                {
                    **c,
                    "trade": t_obj,
                    "sim": active_sim,
                    "sim_base": sim_base,
                    "sim_m6": sim_m6,
                    "raw_gross_pct": active_sim["gross_pct"],
                    "pos_mult": mult,
                }
            )

    return selected


def run_standalone_config(
    raw_candidates: list[dict[str, Any]],
    milestone: str,
    *,
    ratchet_mode: Literal["legacy_bug", "close_rebound", "pessimistic_high"] = "pessimistic_high",
    round_trip_fee_bps: float = 20.0,
    recalc_m6_exit: bool = True,
    sizing_mode: str = "conviction_150_115_080",
    reset_at_oos_boundary: bool = True,
) -> list[dict[str, Any]]:
    return execute_configuration(
        raw_candidates,
        milestone,
        execution_mode="standalone_independent",
        ratchet_mode=ratchet_mode,
        fix_m6_exit_fields=recalc_m6_exit,
        round_trip_fee_bps=round_trip_fee_bps,
        reset_at_oos_boundary=reset_at_oos_boundary,
        sizing_mode=sizing_mode,
    )


def compute_time_weighted_concurrency_and_nav(
    items: list[dict[str, Any]],
    window_start_utc: str,
    window_end_utc: str,
    *,
    base_notional_weight: float = 0.20,
    max_concurrent_cap: int = 5,
    max_total_notional_frac: float | None = None,
    max_total_sl_risk_frac: float | None = None,
    funding_bps_per_8h: float = 0.0,
    funding_lookup: dict[str, dict[int, float]] | None = None,
    round_trip_fee_bps: float = 20.0,
) -> dict[str, Any]:
    """Compute:
    1. Uncapped Concurrency vs Accepted (Post-Cap) Concurrency (Entry-Sampled & Time-Weighted Hourly).
    2. Chronological Hour-by-Hour Fixed-Quantity Mark-to-Market Account NAV curve:
       - Position quantity Q0 = N0 / entry_price is fixed at entry and only reduced by TP1/TP2 partial closes.
       - Compounding only scales the initial dollar notional N0 of newly opened trades using current NAV at entry.
       - Real-timestamp slot occupancy `[t_in, t_out)` using actual `exit_close_time` (never releasing slots early across missing-bar gaps).
       - Equity-relative notional & SL-risk caps evaluated against live open positions and current account equity at entry hour.
       - Deterministic candidate ordering `(entry_ts, -full_conviction_score, symbol, higher_timeframe, trade_id)` invariant to input permutation.
       - Variable-cadence historical funding settlement (`bar_close_epoch_h in sym_funding_map`, supporting 8h, 4h, 2h, and 1h exchange schedules) and 8h synthetic stress funding (`epoch_hour % 8 == 0`, i.e., 00:00, 08:00, 16:00 UTC).
    """
    t_start = pd.Timestamp(window_start_utc)
    if t_start.tzinfo is None:
        t_start = t_start.tz_localize("UTC")
    t_end = pd.Timestamp(window_end_utc)
    if t_end.tzinfo is None:
        t_end = t_end.tz_localize("UTC")

    if not items:
        return {
            "entry_sampled_avg": 0.0,
            "entry_sampled_p95": 0.0,
            "max_concurrent": 0,
            "time_weighted_avg_all_hours": 0.0,
            "time_weighted_avg_active_hours": 0.0,
            "time_weighted_p95_all_hours": 0.0,
            "time_weighted_p95_active_hours": 0.0,
            "active_hours_pct": 0.0,
            "executed_trade_ids": [],
            "uncapped_concurrency": {
                "max_concurrent": 0,
                "time_weighted_avg": 0.0,
                "p95_hourly": 0.0,
            },
            "accepted_concurrency": {
                "entry_sampled_avg": 0.0,
                "entry_sampled_p95": 0.0,
                "max_concurrent": 0,
                "time_weighted_avg_all_hours": 0.0,
                "time_weighted_avg": 0.0,
                "p95_hourly": 0.0,
                "time_weighted_avg_active_hours": 0.0,
                "peak_open_notional_frac": 0.0,
                "max_notional_frac": 0.0,
                "peak_equity_relative_notional_frac": 0.0,
                "peak_mark_to_market_notional_frac": 0.0,
                "peak_open_sl_risk_frac": 0.0,
                "max_sl_risk_frac": 0.0,
                "passive_mtm_notional_cap_breach_hours": 0,
                "passive_mtm_sl_risk_cap_breach_hours": 0,
            },
            "nav_simulation_20pct_notional_per_1x": {
                "max_concurrent_cap": max_concurrent_cap,
                "max_total_notional_frac": max_total_notional_frac,
                "max_total_sl_risk_frac": max_total_sl_risk_frac,
                "executed_trades": 0,
                "skipped_due_to_cap": 0,
                "skipped_total_cap": 0,
                "skipped_due_to_slot_cap": 0,
                "skipped_concurrency_cap": 0,
                "skipped_due_to_notional_cap": 0,
                "skipped_notional_cap": 0,
                "skipped_due_to_sl_risk_cap": 0,
                "skipped_sl_risk_cap": 0,
                "additive_nav_final": 100.0,
                "additive_final_nav": 100.0,
                "additive_nav_total_return_pct": 0.0,
                "additive_total_return_pct": 0.0,
                "additive_nav_max_dd_pct_pts": 0.0,
                "additive_nav_max_dd_rel_pct": 0.0,
                "additive_max_dd_pct": 0.0,
                "compounded_nav_final": 100.0,
                "compounded_final_nav": 100.0,
                "compounded_nav_total_return_pct": 0.0,
                "compounded_total_return_pct": 0.0,
                "compounded_nav_max_dd_rel_pct": 0.0,
                "compounded_max_dd_pct": 0.0,
                "historical_funding_events_matched": 0,
                "historical_funding_events_matched_8h": 0,
                "historical_funding_events_matched_off_8h": 0,
                "historical_funding_events_missing": 0,
                "historical_funding_net_pct_of_initial_nav": 0.0,
                "stress_funding_events_charged": 0,
                "stress_funding_net_pct_of_initial_nav": 0.0,
            },
        }

    def _candidate_sort_key(x: dict[str, Any]) -> tuple[int, float, str, str, str]:
        t_obj = x["trade"]
        t_in = pd.Timestamp(t_obj.entry_time)
        if t_in.tzinfo is None:
            t_in = t_in.tz_localize("UTC")
        epoch_s = int(t_in.timestamp())
        sc = float(x.get("full_conviction_score", getattr(t_obj, "conviction_score", 0.0)))
        return (
            epoch_s,
            -sc,
            str(getattr(t_obj, "symbol", "")),
            str(getattr(t_obj, "higher_timeframe", "")),
            str(getattr(t_obj, "trade_id", "")),
        )

    chrono_items = sorted(items, key=_candidate_sort_key)

    # Build hourly grid from t_start to t_end
    hourly_index = pd.date_range(start=t_start.floor("h"), end=t_end.ceil("h"), freq="1h", tz="UTC")
    n_hours = len(hourly_index)
    grid_start_epoch_h = int(hourly_index[0].timestamp() // 3600)
    active_counts = np.zeros(n_hours, dtype=int)

    # Pre-resolve single-source simulation trace and real exit timestamp for each trade
    prepared_candidates: list[dict[str, Any]] = []
    candidates_by_entry_h: dict[int, list[dict[str, Any]]] = {}
    events: list[tuple[pd.Timestamp, int]] = []

    for x in chrono_items:
        t = x["trade"]
        t_in = pd.Timestamp(t.entry_time)
        if t_in.tzinfo is None:
            t_in = t_in.tz_localize("UTC")

        sim = x.get("sim")
        if sim is None or "bar_trace" not in sim:
            sim = simulate_trade_v2(
                x.get("future_slice", []),
                entry_price=float(t.entry_price),
                stop_loss=float(t.stop_loss),
                tp1=float(t.tp1),
                tp2=float(t.tp2),
                tp3=float(t.tp3),
                round_trip_fee_bps=float(x.get("round_trip_fee_bps", round_trip_fee_bps)),
                entry_timestamp_utc=t_in,
            )

        bar_trace = sim.get("bar_trace", [])
        hold_h = max(1, int(sim.get("hold_hours", 0)) if int(sim.get("hold_hours", 0)) > 0 else max(1, len(bar_trace), int(getattr(t, "hold_hours", 1))))

        # Resolve real timestamp exit t_out from sim["exit_close_time"] and bar_trace close_time_str
        t_out = t_in + pd.Timedelta(hours=hold_h)
        raw_exit_close = sim.get("exit_close_time") or getattr(t, "exit_time", "")
        if raw_exit_close:
            try:
                cand_out = pd.Timestamp(raw_exit_close)
                if cand_out.tzinfo is None:
                    cand_out = cand_out.tz_localize("UTC")
                if cand_out > t_in:
                    t_out = max(t_out, cand_out)
            except Exception:
                pass

        i0 = max(0, int(t_in.timestamp() // 3600) - grid_start_epoch_h)
        steps_by_close_h: dict[int, dict[str, Any]] = {}
        max_step_h = i0 + hold_h
        for b_step in bar_trace:
            b_idx = int(b_step["bar_idx"])
            h_idx = i0 + b_idx + 1
            c_str = b_step.get("close_time_str", "")
            if c_str:
                try:
                    c_ts = pd.Timestamp(c_str)
                    if c_ts.tzinfo is None:
                        c_ts = c_ts.tz_localize("UTC")
                    cand_h = int(c_ts.timestamp() // 3600) - grid_start_epoch_h
                    if cand_h > i0:
                        h_idx = cand_h
                except Exception:
                    pass
            steps_by_close_h[h_idx] = b_step
            if h_idx > max_step_h:
                max_step_h = h_idx

        out_epoch_h = int(t_out.timestamp() // 3600) - grid_start_epoch_h
        i1_excl_unclamped = max(i0 + 1, max_step_h, out_epoch_h)
        i1_excl = min(n_hours, i1_excl_unclamped)
        t_out_real = hourly_index[0] + pd.Timedelta(hours=i1_excl_unclamped)

        events.append((t_in, +1))
        events.append((t_out_real, -1))

        if i1_excl > i0 and i0 < n_hours:
            active_counts[i0:i1_excl] += 1

        if i0 < n_hours:
            prep = {
                "item": x,
                "trade": t,
                "sim": sim,
                "i0": i0,
                "i1_excl": i1_excl,
                "steps_by_close_h": steps_by_close_h,
            }
            prepared_candidates.append(prep)
            candidates_by_entry_h.setdefault(i0, []).append(prep)

    # Exits (-1) processed before entries (+1) at identical timestamps
    events.sort(key=lambda e: (e[0], e[1]))
    cur_c = 0
    max_c = 0
    entry_samples: list[int] = []
    for _, d in events:
        cur_c += d
        if cur_c > max_c:
            max_c = cur_c
        if d == +1:
            entry_samples.append(cur_c)

    active_only = active_counts[active_counts > 0]

    # Single-Pass Chronological Hour-by-Hour Portfolio Accounting State Machine
    add_hourly_dollar_pnl = np.zeros(n_hours, dtype=float)
    comp_hourly_dollar_pnl = np.zeros(n_hours, dtype=float)

    slot_occupancy = np.zeros(n_hours, dtype=int)
    static_notional_occupancy = np.zeros(n_hours, dtype=float)
    notional_occupancy = np.zeros(n_hours, dtype=float)
    mark_notional_occupancy = np.zeros(n_hours, dtype=float)
    sl_risk_occupancy = np.zeros(n_hours, dtype=float)
    static_sl_risk_occupancy = np.zeros(n_hours, dtype=float)

    skipped_due_to_cap = 0
    skipped_due_to_slot_cap = 0
    skipped_due_to_notional_cap = 0
    skipped_due_to_sl_risk_cap = 0
    executed_under_cap = 0
    executed_trade_ids: list[str] = []
    accepted_entry_samples: list[int] = []

    hist_funding_matched = 0
    hist_funding_matched_8h = 0
    hist_funding_matched_off_8h = 0
    hist_funding_missing = 0
    hist_funding_dollar_total = 0.0
    stress_funding_events_charged = 0
    stress_funding_dollar_total = 0.0

    cur_add_equity = 100.0
    cur_comp_equity = 100.0
    open_positions: list[dict[str, Any]] = []

    for h in range(n_hours):
        bar_close_epoch_h = grid_start_epoch_h + h
        is_8h_settlement = (bar_close_epoch_h % 8) == 0

        # Step 1: Process bar closes and variable-cadence funding settlements at hour h for open positions
        for p in open_positions:
            ep = p["entry_price"]
            sym_funding_map = p["sym_funding_map"]
            if h in p["steps_by_close_h"]:
                b_step = p["steps_by_close_h"][h]
                w_rem_start = float(b_step["rem_weight_start"])
                close_p = float(b_step["close_price"])
                price_ratio = close_p / max(1e-9, ep)

                hist_fund_pct_of_n0 = 0.0
                if funding_lookup is not None and w_rem_start > 1e-6:
                    if sym_funding_map is not None and bar_close_epoch_h in sym_funding_map:
                        r_fund = float(sym_funding_map[bar_close_epoch_h])
                        hist_fund_pct_of_n0 = (r_fund * 100.0) * w_rem_start * price_ratio
                        hist_funding_matched += 1
                        if is_8h_settlement:
                            hist_funding_matched_8h += 1
                        else:
                            hist_funding_matched_off_8h += 1
                        hist_funding_dollar_total += p["n0_add"] * (hist_fund_pct_of_n0 / 100.0)
                    elif is_8h_settlement:
                        hist_funding_missing += 1

                stress_fund_pct_of_n0 = 0.0
                if funding_bps_per_8h != 0.0 and is_8h_settlement and w_rem_start > 1e-6:
                    stress_fund_pct_of_n0 = -(funding_bps_per_8h / 100.0) * w_rem_start * price_ratio
                    stress_funding_events_charged += 1
                    stress_funding_dollar_total += p["n0_add"] * (stress_fund_pct_of_n0 / 100.0)

                delta_pct_of_n0 = (
                    float(b_step["delta_gross_pct"])
                    - float(b_step["bar_fee_pct"])
                    + hist_fund_pct_of_n0
                    + stress_fund_pct_of_n0
                )

                add_hourly_dollar_pnl[h] += p["n0_add"] * (delta_pct_of_n0 / 100.0)
                comp_hourly_dollar_pnl[h] += p["n0_comp"] * (delta_pct_of_n0 / 100.0)

                p["rem_weight"] = float(b_step["rem_weight_end"])
                p["active_sl"] = float(b_step.get("active_sl_end", p["active_sl"]))
                p["last_mark_price"] = close_p
            elif h > p["i0"] and h < p["i1_excl"] and p["rem_weight"] > 1e-6:
                # Missing-bar gap hour while position remains open: settle funding if applicable
                w_rem_gap = p["rem_weight"]
                price_ratio_gap = p["last_mark_price"] / max(1e-9, ep)
                gap_fund_pct_of_n0 = 0.0
                if funding_lookup is not None:
                    if sym_funding_map is not None and bar_close_epoch_h in sym_funding_map:
                        r_fund = float(sym_funding_map[bar_close_epoch_h])
                        gap_fund_pct_of_n0 += (r_fund * 100.0) * w_rem_gap * price_ratio_gap
                        hist_funding_matched += 1
                        if is_8h_settlement:
                            hist_funding_matched_8h += 1
                        else:
                            hist_funding_matched_off_8h += 1
                        hist_funding_dollar_total += p["n0_add"] * ((r_fund * 100.0) * w_rem_gap * price_ratio_gap / 100.0)
                    elif is_8h_settlement:
                        hist_funding_missing += 1
                if funding_bps_per_8h != 0.0 and is_8h_settlement:
                    s_pct = -(funding_bps_per_8h / 100.0) * w_rem_gap * price_ratio_gap
                    gap_fund_pct_of_n0 += s_pct
                    stress_funding_events_charged += 1
                    stress_funding_dollar_total += p["n0_add"] * (s_pct / 100.0)
                if gap_fund_pct_of_n0 != 0.0:
                    add_hourly_dollar_pnl[h] += p["n0_add"] * (gap_fund_pct_of_n0 / 100.0)
                    comp_hourly_dollar_pnl[h] += p["n0_comp"] * (gap_fund_pct_of_n0 / 100.0)

        cur_add_equity = max(1e-9, 100.0 + float(np.sum(add_hourly_dollar_pnl[: h + 1])))
        cur_comp_equity = max(1e-9, 100.0 + float(np.sum(comp_hourly_dollar_pnl[: h + 1])))

        # Step 2: Release positions that closed at or before hour h (before evaluating new entries at hour h)
        open_positions = [p for p in open_positions if p["i1_excl"] > h and p["rem_weight"] > 1e-6]

        # Step 3: Evaluate candidate entries arriving at hour h in deterministic order
        for prep in candidates_by_entry_h.get(h, []):
            x = prep["item"]
            t = prep["trade"]
            mult = float(x.get("pos_mult", 1.0))
            notional_frac = base_notional_weight * mult
            ep = float(t.entry_price)
            sl = float(t.stop_loss)
            sl_dist_frac = max(0.0, (sl - ep) / max(1e-9, ep))
            trade_sl_risk_frac = notional_frac * sl_dist_frac

            # 1. Check slot cap at entry hour h
            if len(open_positions) >= max_concurrent_cap:
                skipped_due_to_cap += 1
                skipped_due_to_slot_cap += 1
                continue

            # 2. Check equity-relative total notional cap at entry hour h (if enabled)
            if max_total_notional_frac is not None:
                open_static_notional_frac = sum(p["notional_frac"] * p["rem_weight"] for p in open_positions)
                open_entry_notional_frac_eq = sum(p["n0_comp"] * p["rem_weight"] for p in open_positions) / cur_comp_equity
                open_mark_notional_frac_eq = sum(
                    p["n0_comp"] * p["rem_weight"] * (p["last_mark_price"] / max(1e-9, p["entry_price"]))
                    for p in open_positions
                ) / cur_comp_equity
                effective_open_notional_frac = max(
                    open_static_notional_frac,
                    open_entry_notional_frac_eq,
                    open_mark_notional_frac_eq,
                )
                if effective_open_notional_frac + notional_frac > max_total_notional_frac + 1e-9:
                    skipped_due_to_cap += 1
                    skipped_due_to_notional_cap += 1
                    continue

            # 3. Check equity-relative total SL risk cap at entry hour h (if enabled)
            if max_total_sl_risk_frac is not None:
                open_static_sl_risk = sum(
                    p["notional_frac"] * p["rem_weight"] * max(0.0, (p["active_sl"] - p["entry_price"]) / max(1e-9, p["entry_price"]))
                    for p in open_positions
                )
                open_eq_sl_risk = sum(
                    ((p["n0_comp"] / max(1e-9, p["entry_price"])) * p["rem_weight"])
                    * max(0.0, p["active_sl"] - p["entry_price"], p["active_sl"] - p["last_mark_price"])
                    for p in open_positions
                ) / cur_comp_equity
                effective_open_sl_risk = max(open_static_sl_risk, open_eq_sl_risk)
                if effective_open_sl_risk + trade_sl_risk_frac > max_total_sl_risk_frac + 1e-9:
                    skipped_due_to_cap += 1
                    skipped_due_to_sl_risk_cap += 1
                    continue

            # Accept trade and immediately reserve slot, notional, and SL risk in open_positions
            executed_under_cap += 1
            tid_str = str(getattr(t, "trade_id", f"{getattr(t, 'symbol', 'SYM')}_{h}_{executed_under_cap}"))
            executed_trade_ids.append(tid_str)
            n0_add = 100.0 * notional_frac
            n0_comp = cur_comp_equity * notional_frac
            open_positions.append(
                {
                    "trade": t,
                    "symbol": t.symbol,
                    "i0": h,
                    "i1_excl": prep["i1_excl"],
                    "entry_price": ep,
                    "active_sl": sl,
                    "last_mark_price": ep,
                    "rem_weight": 1.0,
                    "notional_frac": notional_frac,
                    "n0_add": n0_add,
                    "n0_comp": n0_comp,
                    "steps_by_close_h": prep["steps_by_close_h"],
                    "sym_funding_map": funding_lookup.get(t.symbol) if funding_lookup is not None else None,
                }
            )
            accepted_entry_samples.append(len(open_positions))

        # Step 4: Record live portfolio occupancy at hour h
        slot_occupancy[h] = len(open_positions)
        if open_positions:
            static_notional_occupancy[h] = sum(p["notional_frac"] * p["rem_weight"] for p in open_positions)
            notional_occupancy[h] = sum(p["n0_comp"] * p["rem_weight"] for p in open_positions) / cur_comp_equity
            mark_notional_occupancy[h] = sum(
                p["n0_comp"] * p["rem_weight"] * (p["last_mark_price"] / max(1e-9, p["entry_price"]))
                for p in open_positions
            ) / cur_comp_equity
            static_sl_risk_occupancy[h] = sum(
                p["notional_frac"] * p["rem_weight"] * max(0.0, (p["active_sl"] - p["entry_price"]) / max(1e-9, p["entry_price"]))
                for p in open_positions
            )
            sl_risk_occupancy[h] = sum(
                ((p["n0_comp"] / max(1e-9, p["entry_price"])) * p["rem_weight"])
                * max(0.0, p["active_sl"] - p["entry_price"], p["active_sl"] - p["last_mark_price"])
                for p in open_positions
            ) / cur_comp_equity

    additive_nav = 100.0 + np.cumsum(add_hourly_dollar_pnl)
    add_peak = np.maximum.accumulate(additive_nav)
    add_dd_pct_pts = float(np.max(add_peak - additive_nav))
    add_dd_rel_pct = float(np.max((add_peak - additive_nav) / np.maximum(1e-9, add_peak) * 100.0))

    comp_nav = 100.0 + np.cumsum(comp_hourly_dollar_pnl)
    comp_peak = np.maximum.accumulate(comp_nav)
    comp_dd_rel_pct = float(np.max((comp_peak - comp_nav) / np.maximum(1e-9, comp_peak) * 100.0))

    accepted_active_only = slot_occupancy[slot_occupancy > 0]
    passive_notional_breach_h = (
        int(np.sum(mark_notional_occupancy > (max_total_notional_frac + 1e-9)))
        if max_total_notional_frac is not None
        else 0
    )
    passive_sl_risk_breach_h = (
        int(np.sum(sl_risk_occupancy > (max_total_sl_risk_frac + 1e-9)))
        if max_total_sl_risk_frac is not None
        else 0
    )

    return {
        "entry_sampled_avg": round(float(np.mean(entry_samples)), 2) if entry_samples else 0.0,
        "entry_sampled_p95": round(float(np.percentile(entry_samples, 95)), 1) if entry_samples else 0.0,
        "max_concurrent": int(max_c),
        "time_weighted_avg_all_hours": round(float(np.mean(active_counts)), 3),
        "time_weighted_p95_all_hours": round(float(np.percentile(active_counts, 95)), 2),
        "time_weighted_avg_active_hours": round(float(np.mean(active_only)), 2) if len(active_only) > 0 else 0.0,
        "time_weighted_p95_active_hours": round(float(np.percentile(active_only, 95)), 1) if len(active_only) > 0 else 0.0,
        "active_hours_pct": round(len(active_only) / max(1, n_hours) * 100.0, 2),
        "executed_trade_ids": executed_trade_ids,
        "uncapped_concurrency": {
            "max_concurrent": int(max_c),
            "time_weighted_avg": round(float(np.mean(active_counts)), 3),
            "p95_hourly": round(float(np.percentile(active_counts, 95)), 2),
        },
        "accepted_concurrency": {
            "entry_sampled_avg": round(float(np.mean(accepted_entry_samples)), 2) if accepted_entry_samples else 0.0,
            "entry_sampled_p95": round(float(np.percentile(accepted_entry_samples, 95)), 1) if accepted_entry_samples else 0.0,
            "max_concurrent": int(np.max(slot_occupancy)) if n_hours > 0 else 0,
            "time_weighted_avg_all_hours": round(float(np.mean(slot_occupancy)), 3),
            "time_weighted_avg": round(float(np.mean(slot_occupancy)), 3),
            "p95_hourly": round(float(np.percentile(slot_occupancy, 95)), 2) if n_hours > 0 else 0.0,
            "time_weighted_avg_active_hours": round(float(np.mean(accepted_active_only)), 2) if len(accepted_active_only) > 0 else 0.0,
            "peak_open_notional_frac": round(float(np.max(static_notional_occupancy)), 4) if n_hours > 0 else 0.0,
            "max_notional_frac": round(float(np.max(static_notional_occupancy)), 4) if n_hours > 0 else 0.0,
            "peak_equity_relative_notional_frac": round(float(np.max(notional_occupancy)), 4) if n_hours > 0 else 0.0,
            "peak_mark_to_market_notional_frac": round(float(np.max(mark_notional_occupancy)), 4) if n_hours > 0 else 0.0,
            "peak_open_sl_risk_frac": round(float(np.max(static_sl_risk_occupancy)), 4) if n_hours > 0 else 0.0,
            "max_sl_risk_frac": round(float(np.max(sl_risk_occupancy)), 4) if n_hours > 0 else 0.0,
            "passive_mtm_notional_cap_breach_hours": passive_notional_breach_h,
            "passive_mtm_sl_risk_cap_breach_hours": passive_sl_risk_breach_h,
        },
        "nav_simulation_20pct_notional_per_1x": {
            "max_concurrent_cap": max_concurrent_cap,
            "max_total_notional_frac": max_total_notional_frac,
            "max_total_sl_risk_frac": max_total_sl_risk_frac,
            "executed_trades": executed_under_cap,
            "skipped_due_to_cap": skipped_due_to_cap,
            "skipped_total_cap": skipped_due_to_cap,
            "skipped_due_to_slot_cap": skipped_due_to_slot_cap,
            "skipped_concurrency_cap": skipped_due_to_slot_cap,
            "skipped_due_to_notional_cap": skipped_due_to_notional_cap,
            "skipped_notional_cap": skipped_due_to_notional_cap,
            "skipped_due_to_sl_risk_cap": skipped_due_to_sl_risk_cap,
            "skipped_sl_risk_cap": skipped_due_to_sl_risk_cap,
            "additive_nav_final": round(float(additive_nav[-1]), 4),
            "additive_final_nav": round(float(additive_nav[-1]), 4),
            "additive_nav_total_return_pct": round(float(additive_nav[-1] - 100.0), 2),
            "additive_total_return_pct": round(float(additive_nav[-1] - 100.0), 2),
            "additive_nav_max_dd_pct_pts": round(add_dd_pct_pts, 2),
            "additive_nav_max_dd_rel_pct": round(add_dd_rel_pct, 2),
            "additive_max_dd_pct": round(add_dd_rel_pct, 2),
            "compounded_nav_final": round(float(comp_nav[-1]), 4),
            "compounded_final_nav": round(float(comp_nav[-1]), 4),
            "compounded_nav_total_return_pct": round(float(comp_nav[-1] - 100.0), 2),
            "compounded_total_return_pct": round(float(comp_nav[-1] - 100.0), 2),
            "compounded_nav_max_dd_rel_pct": round(comp_dd_rel_pct, 2),
            "compounded_max_dd_pct": round(comp_dd_rel_pct, 2),
            "historical_funding_events_matched": hist_funding_matched,
            "historical_funding_events_matched_8h": hist_funding_matched_8h,
            "historical_funding_events_matched_off_8h": hist_funding_matched_off_8h,
            "historical_funding_events_missing": hist_funding_missing,
            "historical_funding_net_pct_of_initial_nav": round(hist_funding_dollar_total, 3),
            "stress_funding_events_charged": stress_funding_events_charged,
            "stress_funding_net_pct_of_initial_nav": round(stress_funding_dollar_total, 3),
        },
    }


compute_portfolio_nav_and_concurrency = compute_time_weighted_concurrency_and_nav



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
    symbols = default_syms + alt_syms

    results: dict[str, Any] = {}

    # 1. Item 1.1 Toy Example
    toy_bars = [
        {"open": 100.0, "high": 105.0, "low": 89.0, "close": 102.0, "open_time_str": "2025-01-01T01:00:00+00:00"},
        {"open": 99.0, "high": 99.0, "low": 69.0, "close": 72.0, "open_time_str": "2025-01-01T02:00:00+00:00"},
    ]
    leg_toy = _simulate_trade_outcome(
        toy_bars, entry_price=100.0, stop_loss=110.0, tp1=90.0, tp2=80.0, tp3=70.0, fee_bps=10.0
    )
    results["item_1_1_toy"] = {
        "legacy_engine": {
            "outcome": leg_toy[0],
            "exit_price": leg_toy[1],
            "exit_time": leg_toy[2],
            "hold_hours": leg_toy[3],
            "gross_pct": leg_toy[7],
            "net_pct": leg_toy[8],
        },
        "fixed_pessimistic_high": simulate_trade_v2(
            toy_bars, entry_price=100.0, stop_loss=110.0, tp1=90.0, tp2=80.0, tp3=70.0,
            round_trip_fee_bps=10.0, ratchet_mode="pessimistic_high"
        ),
        "fixed_close_rebound": simulate_trade_v2(
            toy_bars, entry_price=100.0, stop_loss=110.0, tp1=90.0, tp2=80.0, tp3=70.0,
            round_trip_fee_bps=10.0, ratchet_mode="close_rebound"
        ),
    }

    # 2. Load 2020-2025 IS and 2026 OOS frames & check data end dates (Item 3.3)
    is_frames: dict[str, pd.DataFrame] = {}
    oos_frames: dict[str, pd.DataFrame] = {}
    data_coverage: dict[str, Any] = {}
    for sym in symbols:
        df_is = load_historical_1h_frame(
            sym,
            start_utc="2020-01-01T00:00:00+00:00",
            end_utc="2025-12-31T23:59:59+00:00",
            strict_in_sample=True,
        )
        df_oos = load_1h_for_oos(sym)
        is_frames[sym] = df_is
        oos_frames[sym] = df_oos
        src_type = "1h_shared" if (SHARED_1H_DIR / f"{sym}_1h.parquet").exists() else "5m_resampled"
        data_coverage[sym] = {
            "source": src_type,
            "is_start": str(df_is.index.min()),
            "is_end": str(df_is.index.max()),
            "oos_end": str(df_oos.index.max()),
            "oos_bars_2026": int((df_oos.index >= OOS_START_UTC).sum()),
        }
    results["item_3_3_data_coverage"] = data_coverage

    btc_is = is_frames["BTCUSDT"].sort_index()
    btc_htf_is = {tf: calc_multi_repo_htf_features(resample_1h_to_htf(btc_is, tf)) for tf in ("4h", "1d")}
    btc_htf_is_nobfill = {tf: calc_htf_features_no_bfill(resample_1h_to_htf(btc_is, tf)) for tf in ("4h", "1d")}

    btc_oos = oos_frames["BTCUSDT"].sort_index()
    btc_htf_oos = {tf: calc_multi_repo_htf_features(resample_1h_to_htf(btc_oos, tf)) for tf in ("4h", "1d")}
    btc_htf_oos_nobfill = {tf: calc_htf_features_no_bfill(resample_1h_to_htf(btc_oos, tf)) for tf in ("4h", "1d")}

    print("Collecting raw candidates across 2020-2025 IS and 2026 OOS...")
    cands_is_legacy = collect_candidates_and_run_modes(
        is_frames,
        btc_htf_is,
        entry_start_ts=pd.Timestamp("2020-01-01T00:00:00+00:00"),
        entry_end_ts=pd.Timestamp("2025-12-31T23:59:59+00:00"),
        strict_prior_low_before_peak=False,
        no_bfill=False,
    )
    cands_is_nobfill = collect_candidates_and_run_modes(
        is_frames,
        btc_htf_is_nobfill,
        entry_start_ts=pd.Timestamp("2020-01-01T00:00:00+00:00"),
        entry_end_ts=pd.Timestamp("2025-12-31T23:59:59+00:00"),
        strict_prior_low_before_peak=False,
        no_bfill=True,
    )
    cands_is_strict_clean = collect_candidates_and_run_modes(
        is_frames,
        btc_htf_is_nobfill,
        entry_start_ts=pd.Timestamp("2020-01-01T00:00:00+00:00"),
        entry_end_ts=pd.Timestamp("2025-12-31T23:59:59+00:00"),
        strict_prior_low_before_peak=True,
        no_bfill=True,
    )

    cands_oos_legacy = collect_candidates_and_run_modes(
        oos_frames,
        btc_htf_oos,
        entry_start_ts=OOS_START_UTC,
        entry_end_ts=pd.Timestamp("2026-10-01T00:00:00+00:00"),
        strict_prior_low_before_peak=False,
        no_bfill=False,
    )
    cands_oos_strict_clean = collect_candidates_and_run_modes(
        oos_frames,
        btc_htf_oos_nobfill,
        entry_start_ts=OOS_START_UTC,
        entry_end_ts=pd.Timestamp("2026-10-01T00:00:00+00:00"),
        strict_prior_low_before_peak=True,
        no_bfill=True,
    )

    # Item 2.4: Check if .bfill() changes ANY candidate or feature in 2020-2025 or 2026 OOS
    bfill_diff_count = 0
    if len(cands_is_legacy) == len(cands_is_nobfill):
        for a, b in zip(cands_is_legacy, cands_is_nobfill):
            if (
                a["pst_pass"] != b["pst_pass"]
                or abs(a["full_conviction_score"] - b["full_conviction_score"]) > 1e-6
            ):
                bfill_diff_count += 1
    else:
        bfill_diff_count = abs(len(cands_is_legacy) - len(cands_is_nobfill))

    results["item_2_4_bfill_impact"] = {
        "raw_candidates_with_bfill": len(cands_is_legacy),
        "raw_candidates_without_bfill": len(cands_is_nobfill),
        "trades_or_scores_changed_by_bfill": bfill_diff_count,
    }

    # Item 2.2: Count how many Mốc 1 trades had l_idx == p_idx (prior_low on same bar as swing_high)
    m1_legacy_is = execute_configuration(
        cands_is_legacy,
        "m1_f1a_pump50",
        execution_mode="subset_from_m1",
        ratchet_mode="legacy_bug",
        fix_m6_exit_fields=False,
        round_trip_fee_bps=10.0,
    )
    same_bar_lp_m1_is = sum(1 for x in m1_legacy_is if x["same_bar_low_high"])
    m1_legacy_oos = execute_configuration(
        cands_oos_legacy,
        "m1_f1a_pump50",
        execution_mode="subset_from_m1",
        ratchet_mode="legacy_bug",
        fix_m6_exit_fields=False,
        round_trip_fee_bps=10.0,
    )
    same_bar_lp_m1_oos = sum(1 for x in m1_legacy_oos if x["same_bar_low_high"])
    results["item_2_2_same_bar_low_high"] = {
        "m1_is_total": len(m1_legacy_is),
        "m1_is_same_bar_low_high_count": same_bar_lp_m1_is,
        "m1_oos_total": len(m1_legacy_oos),
        "m1_oos_same_bar_low_high_count": same_bar_lp_m1_oos,
    }

    # Compare Pre-Fix vs Post-Fix across Key Milestones (Mốc 1, Mốc 4A, Mốc 6B, Mốc 6A, Mốc 6S)
    key_milestones = [
        "m1_f1a_pump50",
        "m4_f2_elite",
        "m6_f4_expanded",
        "m6_f4_sniper",
        "m6_f4_elite_sniper",
    ]

    comparison_table: dict[str, Any] = {}
    for ms in key_milestones:
        default_bps = 20.0 if ms.startswith("m6_") else 10.0

        # 1. Legacy Reported (Subset from M1 + legacy_bug ratchet + unfixed M6 exit + default_bps)
        is_leg = execute_configuration(
            cands_is_legacy,
            ms,
            execution_mode="subset_from_m1",
            ratchet_mode="legacy_bug",
            fix_m6_exit_fields=False,
            round_trip_fee_bps=default_bps,
        )
        oos_leg = execute_configuration(
            cands_oos_legacy,
            ms,
            execution_mode="subset_from_m1",
            ratchet_mode="legacy_bug",
            fix_m6_exit_fields=False,
            round_trip_fee_bps=default_bps,
        )

        # 2. Subset from M1 + Fixed Ratchet (Pessimistic High) + Fixed M6 Exit + Unified 20 bps
        is_sub_fix_pess = execute_configuration(
            cands_is_strict_clean,
            ms,
            execution_mode="subset_from_m1",
            ratchet_mode="pessimistic_high",
            fix_m6_exit_fields=True,
            round_trip_fee_bps=20.0,
        )
        oos_sub_fix_pess = execute_configuration(
            cands_oos_strict_clean,
            ms,
            execution_mode="subset_from_m1",
            ratchet_mode="pessimistic_high",
            fix_m6_exit_fields=True,
            round_trip_fee_bps=20.0,
        )

        # 3. Standalone Independent Execution + Fixed Ratchet (Pessimistic High) + Fixed M6 Exit + Unified 20 bps
        is_ind_fix_pess = execute_configuration(
            cands_is_strict_clean,
            ms,
            execution_mode="standalone_independent",
            ratchet_mode="pessimistic_high",
            fix_m6_exit_fields=True,
            round_trip_fee_bps=20.0,
        )
        oos_ind_fix_pess = execute_configuration(
            cands_oos_strict_clean,
            ms,
            execution_mode="standalone_independent",
            ratchet_mode="pessimistic_high",
            fix_m6_exit_fields=True,
            round_trip_fee_bps=20.0,
        )

        # 4. Standalone Independent Execution + Close-Rebound Ratchet + Unified 20 bps
        is_ind_fix_close = execute_configuration(
            cands_is_strict_clean,
            ms,
            execution_mode="standalone_independent",
            ratchet_mode="close_rebound",
            fix_m6_exit_fields=True,
            round_trip_fee_bps=20.0,
        )
        oos_ind_fix_close = execute_configuration(
            cands_oos_strict_clean,
            ms,
            execution_mode="standalone_independent",
            ratchet_mode="close_rebound",
            fix_m6_exit_fields=True,
            round_trip_fee_bps=20.0,
        )

        # Granular outcome breakdown on Standalone Fixed (Pessimistic High)
        det_outcomes_is: dict[str, int] = {}
        for x in is_ind_fix_pess:
            k = x["sim"]["detailed_outcome"]
            det_outcomes_is[k] = det_outcomes_is.get(k, 0) + 1

        det_outcomes_oos: dict[str, int] = {}
        for x in oos_ind_fix_pess:
            k = x["sim"]["detailed_outcome"]
            det_outcomes_oos[k] = det_outcomes_oos.get(k, 0) + 1

        # Concurrency & NAV on IS (2020-2025) and OOS (2026)
        conc_nav_is = compute_time_weighted_concurrency_and_nav(
            is_ind_fix_pess,
            "2020-01-01T00:00:00+00:00",
            "2025-12-31T23:59:59+00:00",
        )
        conc_nav_oos = compute_time_weighted_concurrency_and_nav(
            oos_ind_fix_pess,
            "2026-01-01T00:00:00+00:00",
            "2026-09-29T23:59:59+00:00",
        )

        # Separated 2020-2023 vs 2024-2025 vs 2026 OOS at 20 bps and 40 bps (on both Legacy Subset and Standalone Fixed)
        def _period_fee_stats(item_list: list[dict[str, Any]], bps: float) -> dict[str, Any]:
            if not item_list:
                return {"n": 0, "wr": 0.0, "pf": 0.0, "tot_net": 0.0, "be_bps": 0.0}
            rg = np.array([float(x["raw_gross_pct"]) for x in item_list], dtype=float)
            pm = np.array([float(x["pos_mult"]) for x in item_list], dtype=float)
            net_v = (rg - bps / 100.0) * pm
            gp = float(np.sum(net_v[net_v > 0]))
            gl = abs(float(np.sum(net_v[net_v <= 0])))
            pf = gp / gl if gl > 1e-9 else (99.9 if gp > 0 else 0.0)
            be_bps = float(np.sum(rg * pm) / np.sum(pm) * 100.0) if np.sum(pm) > 0 else 0.0
            return {
                "n": len(item_list),
                "wr": round(float(np.mean(net_v > 0) * 100.0), 2),
                "pf": round(pf, 2),
                "tot_net": round(float(np.sum(net_v)), 2),
                "be_bps": round(be_bps, 1),
            }

        leg_20_23 = [x for x in is_leg if 2020 <= x["year"] <= 2023]
        leg_24_25 = [x for x in is_leg if 2024 <= x["year"] <= 2025]
        ind_20_23 = [x for x in is_ind_fix_pess if 2020 <= x["year"] <= 2023]
        ind_24_25 = [x for x in is_ind_fix_pess if 2024 <= x["year"] <= 2025]

        by_year_40bps_leg = {
            str(y): _period_fee_stats([x for x in is_leg if x["year"] == y], 40.0)
            for y in range(2020, 2026)
        }
        by_year_40bps_leg["2026_oos"] = _period_fee_stats(oos_leg, 40.0)

        by_year_40bps_ind = {
            str(y): _period_fee_stats([x for x in is_ind_fix_pess if x["year"] == y], 40.0)
            for y in range(2020, 2026)
        }
        by_year_40bps_ind["2026_oos"] = _period_fee_stats(oos_ind_fix_pess, 40.0)

        comparison_table[ms] = {
            "is_2020_2025": {
                "legacy_subset": summarize_trades([x["trade"] for x in is_leg]),
                "subset_fixed_pessimistic_20bps": summarize_trades([x["trade"] for x in is_sub_fix_pess]),
                "standalone_fixed_pessimistic_20bps": summarize_trades([x["trade"] for x in is_ind_fix_pess]),
                "standalone_fixed_close_rebound_20bps": summarize_trades([x["trade"] for x in is_ind_fix_close]),
                "detailed_outcomes_standalone": det_outcomes_is,
                "concurrency_and_nav_standalone": conc_nav_is,
            },
            "oos_2026": {
                "legacy_subset": summarize_trades([x["trade"] for x in oos_leg]),
                "subset_fixed_pessimistic_20bps": summarize_trades([x["trade"] for x in oos_sub_fix_pess]),
                "standalone_fixed_pessimistic_20bps": summarize_trades([x["trade"] for x in oos_ind_fix_pess]),
                "standalone_fixed_close_rebound_20bps": summarize_trades([x["trade"] for x in oos_ind_fix_close]),
                "detailed_outcomes_standalone": det_outcomes_oos,
                "concurrency_and_nav_standalone": conc_nav_oos,
            },
            "stress_2020_2023_vs_calib_2024_2025": {
                "legacy_2020_2023_20bps": _period_fee_stats(leg_20_23, 20.0),
                "legacy_2020_2023_40bps": _period_fee_stats(leg_20_23, 40.0),
                "legacy_2024_2025_20bps": _period_fee_stats(leg_24_25, 20.0),
                "legacy_2024_2025_40bps": _period_fee_stats(leg_24_25, 40.0),
                "standalone_fixed_2020_2023_20bps": _period_fee_stats(ind_20_23, 20.0),
                "standalone_fixed_2020_2023_40bps": _period_fee_stats(ind_20_23, 40.0),
                "standalone_fixed_2024_2025_20bps": _period_fee_stats(ind_24_25, 20.0),
                "standalone_fixed_2024_2025_40bps": _period_fee_stats(ind_24_25, 40.0),
                "by_year_40bps_legacy": by_year_40bps_leg,
                "by_year_40bps_standalone_fixed": by_year_40bps_ind,
            },
        }

    results["milestones_recalculation"] = comparison_table

    out_file = ROOT_DIR / "artifacts" / "fibo_trend_short" / "red_team_audit_recalculation_2026.json"
    out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved complete audit verification & recalculation to {out_file}")


if __name__ == "__main__":
    main()
