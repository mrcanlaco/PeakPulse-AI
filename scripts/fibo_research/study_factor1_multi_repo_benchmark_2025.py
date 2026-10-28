"""Benchmark Factor #1 enhancements from prominent quantitative repositories
referenced in conversation 71e09d4a-85d2-4a32-ac7f-d04b42beb69f and local research:

1. `pst-group/pysystemtrade` (Robert Carver):
   - Baseline Factor #1 benchmark: `ewmac(16,64) <= 0` OR `accel(4,16) <= -1.0`
2. `microsoft/qlib` (Alpha158 Statistical Wave Factors):
   - `RSQR(14)`: R-squared of linear regression on prices during the prior wave
   - `RESI(14)`: Regression residual at Peak normalized by volatility
   - `WVMA(14)`: Volume-weighted price volatility
3. `Linus-Ma/crypto-factor-research` (AF-0127 & AF-0133 Exhaustion Factors):
   - `EXH_02` (`upper_wick_ratio` at Swing High): `(high - max(open, close)) / (high - low)`
   - `pump_velocity_pct_per_day`: `(prior_pump_pct * 100) / pump_days_equiv`
4. `QuantConnect/Lean` & `perp-quant-lab` (AF-0172):
   - `KER` (Kaufman Efficiency Ratio of the pump leg): net price change / sum of absolute bar-to-bar changes ("air pocket" vs "staircase support")
   - `BB_pct_b` (Bollinger Band %B extension at Swing High)
5. `freqtrade-strategies` / `vectorbt` (AF-0165 Volume & RSI Exhaustion):
   - `vol_climax_ratio`: Swing High Volume / SMA20(Volume)
   - `pullback_vol_ratio`: Mean Bounce Volume / Mean Pump Volume
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

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


def calc_multi_repo_htf_features(htf_df: pd.DataFrame) -> pd.DataFrame:
    """Compute HTF indicators from pysystemtrade, Qlib Alpha158, QuantConnect/Lean, and Freqtrade."""
    close = htf_df["close"].astype(float)
    open_p = htf_df["open"].astype(float)
    high = htf_df["high"].astype(float)
    low = htf_df["low"].astype(float)
    vol = htf_df["volume"].astype(float).clip(lower=0.0)

    # --- 1. pysystemtrade (Carver) unified with detector.compute_canonical_pst_series ---
    from dao_vang.fibo_short.detector import compute_canonical_pst_series

    r_vol_list, ew4_16_list, ew16_64_list, accel_list = compute_canonical_pst_series(
        close.tolist(),
        use_bfill=False,
    )
    robust_vol = pd.Series(r_vol_list, index=htf_df.index, dtype="float64")
    ewmac_4_16 = pd.Series(ew4_16_list, index=htf_df.index, dtype="float64")
    ewmac_16_64 = pd.Series(ew16_64_list, index=htf_df.index, dtype="float64")
    accel_4_16 = pd.Series(accel_list, index=htf_df.index, dtype="float64")

    # --- 2. Microsoft Qlib Alpha158: Rolling RSQR(14) & RESI(14) & WVMA(14) ---
    win = 14
    x = np.arange(win, dtype=float)
    x_mean = x.mean()
    x_dev = x - x_mean
    s_xx = np.sum(x_dev**2)

    rsqr_vals = np.full(len(close), np.nan)
    resi_vals = np.full(len(close), np.nan)
    close_arr = close.to_numpy()
    high_arr = high.to_numpy()
    rvol_arr = robust_vol.to_numpy()

    for i in range(win - 1, len(close_arr)):
        y = close_arr[i - win + 1 : i + 1]
        y_mean = y.mean()
        y_dev = y - y_mean
        s_yy = np.sum(y_dev**2)
        if s_yy <= 1e-18:
            rsqr_vals[i] = 0.0
            resi_vals[i] = 0.0
            continue
        s_xy = np.sum(x_dev * y_dev)
        r2 = (s_xy**2) / (s_xx * s_yy)
        slope = s_xy / s_xx
        intercept = y_mean - slope * x_mean
        fitted_last = intercept + slope * (win - 1)
        resi_vals[i] = (high_arr[i] - fitted_last) / max(1e-9, rvol_arr[i])
        rsqr_vals[i] = float(np.clip(r2, 0.0, 1.0))

    abs_ret_vol = close.pct_change().abs().fillna(0.0) * vol
    wvma_14 = (
        abs_ret_vol.rolling(14, min_periods=5).std()
        / abs_ret_vol.rolling(14, min_periods=5).mean().replace(0, np.nan)
    ).fillna(0.0)

    # --- 3. Linus-Ma / crypto-factor-research: Upper Wick Ratio (`EXH_02`) ---
    candle_range = (high - low).replace(0, np.nan)
    body_top = np.maximum(open_p, close)
    upper_wick_ratio = ((high - body_top) / candle_range).fillna(0.0).clip(0.0, 1.0)

    # --- 4. QuantConnect / Lean: Bollinger %B (20, 2) & RSI(14) ---
    sma20 = close.rolling(20, min_periods=5).mean()
    std20 = close.rolling(20, min_periods=5).std().replace(0, np.nan)
    bb_upper = sma20 + 2.0 * std20
    bb_lower = sma20 - 2.0 * std20
    bb_pct_b = ((high - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)).fillna(0.5)

    delta = close.diff()
    gain = delta.clip(lower=0.0).ewm(alpha=1 / 14, min_periods=5).mean()
    loss = (-delta.clip(upper=0.0)).ewm(alpha=1 / 14, min_periods=5).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi_14 = (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)

    # --- 5. Volume Climax Ratio (Vol / SMA20_Vol) ---
    vol_sma20 = vol.rolling(20, min_periods=5).mean().replace(0, np.nan)
    vol_ratio_20 = (vol / vol_sma20).fillna(1.0)

    out = htf_df.copy()
    out["robust_vol"] = robust_vol
    out["ewmac_4_16"] = ewmac_4_16
    out["ewmac_16_64"] = ewmac_16_64
    out["accel_4_16"] = accel_4_16
    out["qlib_rsqr_14"] = pd.Series(rsqr_vals, index=htf_df.index).fillna(0.5)
    out["qlib_resi_14"] = pd.Series(resi_vals, index=htf_df.index).fillna(0.0)
    out["qlib_wvma_14"] = wvma_14
    out["upper_wick_ratio"] = upper_wick_ratio
    out["bb_pct_b"] = bb_pct_b
    out["rsi_14"] = rsi_14
    out["vol_ratio_20"] = vol_ratio_20
    return out


def collect_enriched_trades(frames: dict[str, pd.DataFrame], min_pump: float = 0.50) -> list[dict[str, Any]]:
    cfg = FiboTrendShortConfig(
        min_prior_pump_pct=min_pump,
        min_impulse_drop_pct=0.04,
        fibo_entry_min=0.500,
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
                        "qlib_rsqr_14": float(row["qlib_rsqr_14"]),
                        "qlib_resi_14": float(row["qlib_resi_14"]),
                        "qlib_wvma_14": float(row["qlib_wvma_14"]),
                        "upper_wick_ratio": float(row["upper_wick_ratio"]),
                        "bb_pct_b": float(row["bb_pct_b"]),
                        "rsi_14": float(row["rsi_14"]),
                        "vol_ratio_20": float(row["vol_ratio_20"]),
                    }
                )

            htf_by_open_str = {r["open_time_str"]: r for r in htf_records}

            htf_ptr = 0
            n_htf = len(htf_records)
            cooldown_until_idx = -1
            consumed_waves: set[str] = set()
            horizon = cfg.horizon_hours if tf == "4h" else max(cfg.horizon_hours, 120)

            for idx_1h in range(24, len(h1_records) - 2):
                if idx_1h < cooldown_until_idx:
                    continue

                current_decision_ts = h1_close_times[idx_1h]
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
                    hold_hours,
                    tp1_hit,
                    tp2_hit,
                    tp3_hit,
                    gross_pct,
                    net_pct,
                    r_mult,
                ) = _simulate_trade_outcome(
                    future_slice,
                    entry_price=setup.entry_price,
                    stop_loss=setup.stop_loss,
                    tp1=setup.tp1,
                    tp2=setup.tp2,
                    tp3=setup.tp3,
                )

                consumed_waves.add(wave_key)
                cooldown_until_idx = idx_1h + max(4, hold_hours)

                trade_obj = FiboBacktestTrade(
                    trade_id=f"{sig.id}_{idx_1h}",
                    symbol=symbol,
                    higher_timeframe=tf,
                    confirmation_tier=sig.h1_confirmation.confirmation_tier,
                    pattern_name=sig.h1_confirmation.pattern_name,
                    entry_time=sig.signal_time,
                    exit_time=exit_time,
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
                    hold_hours=hold_hours,
                    fibo_entry_ratio=sig.h1_confirmation.current_fibo_ratio,
                    impulse_drop_pct=sig.wave.impulse_drop_pct,
                    prior_pump_pct=sig.wave.prior_pump_pct,
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

                pump_bars = max(1, p_idx - l_idx)
                pump_days_equiv = pump_bars * (4.0 / 24.0 if tf == "4h" else 1.0)
                # Note: sig.wave.prior_pump_pct is already in percentage (e.g. 58.5 for 58.5%) or decimal?
                # Wait: let's check both! If < 10, it's decimal; in detector.py prior_pump_pct = round(prior_pump_pct * 100.0, 2)
                raw_pct = sig.wave.prior_pump_pct if sig.wave.prior_pump_pct >= 5.0 else sig.wave.prior_pump_pct * 100.0
                pump_velocity_per_day = raw_pct / max(0.1667, pump_days_equiv)

                wave_bars = htf_records[l_idx : p_idx + 1]
                if len(wave_bars) >= 2:
                    closes_w = np.array([b["close"] for b in wave_bars], dtype=float)
                    net_chg = abs(closes_w[-1] - closes_w[0])
                    path_chg = float(np.sum(np.abs(np.diff(closes_w))))
                    ker_wave = net_chg / path_chg if path_chg > 1e-9 else 1.0
                else:
                    ker_wave = 1.0

                cluster_end = min(p_idx + 1, imp_idx)
                cluster_bars = htf_records[max(l_idx, p_idx - 1) : cluster_end + 1]
                peak_cluster_wick = max((b["upper_wick_ratio"] for b in cluster_bars), default=peak_bar["upper_wick_ratio"])
                peak_cluster_vol_ratio = max((b["vol_ratio_20"] for b in cluster_bars), default=peak_bar["vol_ratio_20"])

                pump_mean_vol = float(np.mean([b["volume"] for b in wave_bars])) if wave_bars else 1.0
                bounce_bars = htf_records[imp_idx : cur_idx + 1]
                bounce_mean_vol = float(np.mean([b["volume"] for b in bounce_bars])) if bounce_bars else pump_mean_vol
                pullback_vol_ratio = bounce_mean_vol / max(1e-9, pump_mean_vol)

                pst_pass = (peak_bar["ewmac_16_64"] <= 0.0) or (cur_htf_bar["accel_4_16"] <= -1.0)

                enriched.append(
                    {
                        "trade": trade_obj,
                        "symbol": symbol,
                        "tf": tf,
                        "tier": sig.h1_confirmation.confirmation_tier,
                        "prior_pump_pct": raw_pct,
                        "pump_bars": pump_bars,
                        "pump_days_equiv": pump_days_equiv,
                        "pump_velocity_per_day": pump_velocity_per_day,
                        "pst_pass": pst_pass,
                        "peak_ewmac_16_64": peak_bar["ewmac_16_64"],
                        "cur_accel_4_16": cur_htf_bar["accel_4_16"],
                        "qlib_rsqr_14": peak_bar["qlib_rsqr_14"],
                        "qlib_resi_14": peak_bar["qlib_resi_14"],
                        "qlib_wvma_14": peak_bar["qlib_wvma_14"],
                        "peak_wick": peak_bar["upper_wick_ratio"],
                        "peak_cluster_wick": peak_cluster_wick,
                        "ker_wave": ker_wave,
                        "peak_bb_pct_b": peak_bar["bb_pct_b"],
                        "peak_rsi_14": peak_bar["rsi_14"],
                        "peak_vol_ratio_20": peak_bar["vol_ratio_20"],
                        "peak_cluster_vol_ratio": peak_cluster_vol_ratio,
                        "pullback_vol_ratio": pullback_vol_ratio,
                    }
                )

    return enriched


def show(label: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    s = summarize_trades([x["trade"] for x in items])
    print(
        f"  {label:66s} | N={s['total_trades']:3d} | WR={s['win_rate_pct']:5.2f}% | "
        f"TP1={s['tp1_hit_rate_pct']:5.2f}% | Avg={s['avg_net_return_pct']:+6.3f}% | "
        f"Tot={s['total_net_return_pct']:+7.2f}% | PF={s['profit_factor']:4.2f} | DD={s['max_drawdown_pct']:5.1f}%"
    )
    return s


def full_breakdown(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "overall": summarize_trades([x["trade"] for x in items]),
        "4h": summarize_trades([x["trade"] for x in items if x["tf"] == "4h"]),
        "1d": summarize_trades([x["trade"] for x in items if x["tf"] == "1d"]),
        "BREAK_STRUCTURE_2": summarize_trades([x["trade"] for x in items if x["tier"] == "BREAK_STRUCTURE_2"]),
        "COMBO_1_2": summarize_trades([x["trade"] for x in items if x["tier"] == "COMBO_1_2"]),
        "CANDLE_PATTERN_1": summarize_trades([x["trade"] for x in items if x["tier"] == "CANDLE_PATTERN_1"]),
    }


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

    items = collect_enriched_trades(frames, min_pump=0.50)
    pst_items = [x for x in items if x["pst_pass"]]

    report: dict[str, Any] = {}

    print("\n======================================================================================================")
    print("1. ĐỐI CHIẾU ĐỘC LẬP 4 KHO CHIẾN LƯỢC TRÊN TẬP GỐC SÓNG >= 50% (480 LỆNH)")
    print("======================================================================================================")
    report["standalone_repos_on_480"] = {
        "raw_50pct": show("Mốc 1: Raw Pump >= 50% (Chưa lọc)", items),
        "pst_benchmark": show("Repo A (`pysystemtrade`): ewmac_16_64 <= 0 OR accel_4_16 <= -1.0", pst_items),
        "lean_ker_ge_060": show("Repo B (`QuantConnect/Lean`): KER >= 0.60 (Sóng bơm thẳng Air-Pocket)", [x for x in items if x["ker_wave"] >= 0.60]),
        "lean_ker_ge_035": show("Repo B (`QuantConnect/Lean`): KER >= 0.35 (Không phải sóng bò zíc-zắc)", [x for x in items if x["ker_wave"] >= 0.35]),
        "lean_ker_lt_035": show("Repo B (`QuantConnect/Lean`): KER < 0.35 (Sóng bò xây nền zíc-zắc)", [x for x in items if x["ker_wave"] < 0.35]),
        "freqtrade_vol_climax_ge_20": show("Repo C (`freqtrade` / `vectorbt`): Volume Đỉnh >= 2.0x SMA20 (Climax)", [x for x in items if x["peak_vol_ratio_20"] >= 2.0]),
        "qlib_rsqr14_lt_065": show("Repo D (`microsoft/qlib`): RSQR(14) < 0.65 (Không phải trend mượt)", [x for x in items if x["qlib_rsqr_14"] < 0.65]),
        "qlib_resi14_lt_15": show("Repo D (`microsoft/qlib`): RESI(14) < 1.5 sigma (Không phá vỡ kênh)", [x for x in items if x["qlib_resi_14"] < 1.5]),
        "cryptofactor_wick_ge_035": show("Repo E (`crypto-factor-research`): Râu trên cụm đỉnh EXH_02 >= 35%", [x for x in items if x["peak_cluster_wick"] >= 0.35]),
        "cryptofactor_vel_ge_8pct": show("Repo E (`crypto-factor-research`): Tốc độ bơm >= 8%/ngày (Spike nhanh)", [x for x in items if x["pump_velocity_per_day"] >= 8.0]),
        "cryptofactor_vel_lt_8pct": show("Repo E (`crypto-factor-research`): Tốc độ bơm < 8%/ngày (Bò chậm)", [x for x in items if x["pump_velocity_per_day"] < 8.0]),
    }

    print("\n======================================================================================================")
    print("2. GIẢI PHẪU SỰ KẾT HỢP ĐỘT PHÁ: `pysystemtrade` + `QuantConnect/Lean KER` + `Volume Climax`")
    print("======================================================================================================")
    pst_ker_pass = [x for x in pst_items if x["ker_wave"] >= 0.35]
    pst_ker_reject = [x for x in pst_items if x["ker_wave"] < 0.35]

    # Rescue branch: what if pst_pass is False (Bull trend), BUT the wave is an extreme Air-Pocket Climax
    # (KER >= 0.60 AND (peak_vol_ratio_20 >= 2.0 OR pump_velocity_per_day >= 10.0))?
    non_pst_air_pocket_climax = [
        x
        for x in items
        if (not x["pst_pass"]) and (x["ker_wave"] >= 0.60 and x["peak_vol_ratio_20"] >= 1.8)
    ]
    non_pst_ker_65 = [
        x
        for x in items
        if (not x["pst_pass"]) and (x["ker_wave"] >= 0.65)
    ]

    combo_pst_ker35_plus_climax = [
        x
        for x in items
        if (x["pst_pass"] and x["ker_wave"] >= 0.35)
        or (x["ker_wave"] >= 0.60 and x["peak_vol_ratio_20"] >= 1.8)
    ]
    combo_pst_ker35_plus_ker65 = [
        x
        for x in items
        if (x["pst_pass"] and x["ker_wave"] >= 0.35)
        or (x["ker_wave"] >= 0.65)
    ]

    report["synergy_analysis"] = {
        "pst_only_201": show("Mốc 2B (`pysystemtrade` gốc): 201 lệnh", pst_items),
        "pst_ker_lt_035_rejected": show("  ├─ 71 lệnh trong PST bị loại do KER < 0.35 (Sóng bò xây nhiều nền)", pst_ker_reject),
        "pst_ker_ge_035_kept": show("  └─ ★ 130 lệnh PST đạt KER >= 0.35 (Sóng bơm ít nền hỗ trợ)", pst_ker_pass),
        "non_pst_air_pocket_climax": show("Nhánh cứu thêm ngoài PST: KER >= 0.60 & Vol Đỉnh >= 1.8x SMA20", non_pst_air_pocket_climax),
        "non_pst_ker_65": show("Nhánh cứu thêm ngoài PST: KER >= 0.65 (Siêu Air-Pocket dựng đứng)", non_pst_ker_65),
        "combo_pst_ker35_plus_climax": show("★ TỔ HỢP MỞ RỘNG 1: (PST & KER>=0.35) OR (KER>=0.60 & Vol>=1.8x)", combo_pst_ker35_plus_climax),
        "combo_pst_ker35_plus_ker65": show("★ TỔ HỢP MỞ RỘNG 2: (PST & KER>=0.35) OR (KER>=0.65)", combo_pst_ker35_plus_ker65),
    }

    print("\n======================================================================================================")
    print("3. QUÉT ĐỘ NHẠY NGƯỠNG `KER` TRÊN TẬP `pysystemtrade` (KIỂM TRA TÍNH BỀN VỮNG KHÔNG OVERFIT)")
    print("======================================================================================================")
    report["ker_sensitivity_on_pst"] = {}
    for ker_thr in [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]:
        subset = [x for x in pst_items if x["ker_wave"] >= ker_thr]
        report["ker_sensitivity_on_pst"][f"KER >= {ker_thr:.2f}"] = show(
            f"PST + KER >= {ker_thr:.2f}", subset
        )

    print("\n======================================================================================================")
    print("4. CHI TIẾT THEO KHUNG GIỜ (H4 vs D1) & NẾN H1 CHO 2 CẤU HÌNH MẠNH NHẤT")
    print("======================================================================================================")
    print("--- Cấu hình A: Tinh hoa `PST + KER >= 0.35` (130 lệnh) ---")
    show("  H4 (PST + KER >= 0.35)", [x for x in pst_ker_pass if x["tf"] == "4h"])
    show("  D1 (PST + KER >= 0.35)", [x for x in pst_ker_pass if x["tf"] == "1d"])
    show("  BREAK_STRUCTURE_2 (PST + KER >= 0.35)", [x for x in pst_ker_pass if x["tier"] == "BREAK_STRUCTURE_2"])
    show("  COMBO_1_2 (PST + KER >= 0.35)", [x for x in pst_ker_pass if x["tier"] == "COMBO_1_2"])
    show("  CANDLE_PATTERN_1 (PST + KER >= 0.35)", [x for x in pst_ker_pass if x["tier"] == "CANDLE_PATTERN_1"])

    print("--- Cấu hình B: Mở rộng `(PST & KER >= 0.35) OR (KER >= 0.60 & Vol >= 1.8x)` ---")
    show("  H4 (Tổ hợp Mở rộng 1)", [x for x in combo_pst_ker35_plus_climax if x["tf"] == "4h"])
    show("  D1 (Tổ hợp Mở rộng 1)", [x for x in combo_pst_ker35_plus_climax if x["tf"] == "1d"])
    show("  BREAK_STRUCTURE_2 (Tổ hợp Mở rộng 1)", [x for x in combo_pst_ker35_plus_climax if x["tier"] == "BREAK_STRUCTURE_2"])
    show("  COMBO_1_2 (Tổ hợp Mở rộng 1)", [x for x in combo_pst_ker35_plus_climax if x["tier"] == "COMBO_1_2"])
    show("  CANDLE_PATTERN_1 (Tổ hợp Mở rộng 1)", [x for x in combo_pst_ker35_plus_climax if x["tier"] == "CANDLE_PATTERN_1"])

    report["champion_breakdowns"] = {
        "pst_ker35": full_breakdown(pst_ker_pass),
        "combo_pst_ker35_plus_climax": full_breakdown(combo_pst_ker35_plus_climax),
        "combo_pst_ker35_plus_ker65": full_breakdown(combo_pst_ker35_plus_ker65),
    }

    Path("artifacts/fibo_trend_short/factor1_multi_repo_study_2025.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print("\nSaved detailed multi-repo benchmark to artifacts/fibo_trend_short/factor1_multi_repo_study_2025.json")


if __name__ == "__main__":
    main()
