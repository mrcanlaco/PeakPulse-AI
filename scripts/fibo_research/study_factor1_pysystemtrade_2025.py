"""Testing Robert Carver's `pysystemtrade` concepts on Factor #1 (In-Sample 2024-2025):
1. `robust_vol_calc` (EWMA Volatility, span=35 with 5% rolling quantile floor):
   Normalizing prior pump by coin volatility -> `pump_vol_units = (swing_high - prior_low) / ewvol_35`
2. `ewmac(4, 16)` (Fast Trend / Overextension in volatility units at Swing High)
3. `mr_wings(4, 16)` (Carver's Mean-Reversion Wings: shorting only when fast EWMAC exceeds extreme z-score wings)
4. `ewmac(16, 64)` (Slow Macro Regime: Bear/Neutral vs Runaway Bull Trend)
5. `accel(4, 16)` (Trend Acceleration = ewmac(4,16)_t - ewmac(4,16)_{t-4} at entry/impulse)
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
    _simulate_trade_outcome,
    load_historical_1h_frame,
    resample_1h_to_htf,
    summarize_trades,
    FiboBacktestTrade,
)
from dao_vang.fibo_short.detector import evaluate_symbol_timeframe


def calc_pysystemtrade_features(htf_df: pd.DataFrame) -> pd.DataFrame:
    """Compute exact pysystemtrade features on higher-timeframe close series."""
    close = htf_df["close"].astype(float)
    price_diff = close.diff()

    # 1. robust_vol_calc (span=35, min_periods=10, 5% quantile floor over 500 bars)
    ewvol = price_diff.ewm(adjust=True, span=35, min_periods=10).std()
    ewvol = ewvol.clip(lower=1e-10)
    vol_min = ewvol.rolling(min_periods=20, window=500).quantile(0.05)
    vol_min.iloc[0] = 0.0
    vol_min = vol_min.ffill().fillna(0.0)
    robust_vol = np.maximum(ewvol, vol_min).bfill().ffill()

    # 2. ewmac(4, 16) and ewmac(8, 32) and ewmac(16, 64)
    ewma4 = close.ewm(span=4, min_periods=1).mean()
    ewma8 = close.ewm(span=8, min_periods=1).mean()
    ewma16 = close.ewm(span=16, min_periods=1).mean()
    ewma32 = close.ewm(span=32, min_periods=1).mean()
    ewma64 = close.ewm(span=64, min_periods=1).mean()

    ewmac_4_16 = (ewma4 - ewma16) / robust_vol
    ewmac_8_32 = (ewma8 - ewma32) / robust_vol
    ewmac_16_64 = (ewma16 - ewma64) / robust_vol

    # 3. mr_wings z-score of ewmac_4_16 (how many std devs is ewmac_4_16 stretched?)
    ewmac_4_16_std = ewmac_4_16.rolling(500, min_periods=15).std().bfill().ffill()
    mr_wings_z = ewmac_4_16 / ewmac_4_16_std.replace(0, np.nan)
    mr_wings_z = mr_wings_z.fillna(0.0)

    # 4. accel(4, 16) = ewmac_4_16 - ewmac_4_16.shift(4)
    accel_4_16 = ewmac_4_16 - ewmac_4_16.shift(4).fillna(0.0)

    # 5. breakout(20): 40 * (price - roll_mean) / (roll_max - roll_min)
    roll_max20 = close.rolling(20, min_periods=5).max()
    roll_min20 = close.rolling(20, min_periods=5).min()
    roll_mean20 = (roll_max20 + roll_min20) / 2.0
    denom = (roll_max20 - roll_min20).replace(0, np.nan)
    raw_bo20 = 40.0 * ((close - roll_mean20) / denom)
    breakout_20 = raw_bo20.ewm(span=5, min_periods=2).mean().fillna(0.0)

    out = htf_df.copy()
    out["robust_vol"] = robust_vol
    out["ewmac_4_16"] = ewmac_4_16
    out["ewmac_8_32"] = ewmac_8_32
    out["ewmac_16_64"] = ewmac_16_64
    out["mr_wings_z"] = mr_wings_z
    out["accel_4_16"] = accel_4_16
    out["breakout_20"] = breakout_20
    return out


def collect_trades_with_pst(frames: dict[str, pd.DataFrame], min_pump: float = 0.15) -> list[dict[str, Any]]:
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
            htf_df = calc_pysystemtrade_features(htf_df)

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
                        "ewmac_8_32": float(row["ewmac_8_32"]),
                        "ewmac_16_64": float(row["ewmac_16_64"]),
                        "mr_wings_z": float(row["mr_wings_z"]),
                        "accel_4_16": float(row["accel_4_16"]),
                        "breakout_20": float(row["breakout_20"]),
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
                cur_htf_bar = visible_htf[-1]
                if peak_bar is None or low_bar is None:
                    continue

                swing_high = sig.wave.swing_high_price
                prior_low = sig.wave.prior_low_price
                r_vol = max(1e-9, peak_bar["robust_vol"])

                # Pump amplitude in Carver Volatility Units (how many daily/4h standard deviations did price jump?)
                pump_vol_units = (swing_high - prior_low) / r_vol

                enriched.append(
                    {
                        "trade": trade_obj,
                        "symbol": symbol,
                        "tf": tf,
                        "prior_pump_pct": sig.wave.prior_pump_pct,
                        "pump_vol_units": pump_vol_units,
                        "peak_ewmac_4_16": peak_bar["ewmac_4_16"],
                        "peak_ewmac_8_32": peak_bar["ewmac_8_32"],
                        "peak_ewmac_16_64": peak_bar["ewmac_16_64"],
                        "peak_mr_wings_z": peak_bar["mr_wings_z"],
                        "peak_accel_4_16": peak_bar["accel_4_16"],
                        "cur_ewmac_4_16": cur_htf_bar["ewmac_4_16"],
                        "cur_accel_4_16": cur_htf_bar["accel_4_16"],
                        "cur_ewmac_16_64": cur_htf_bar["ewmac_16_64"],
                    }
                )

    return enriched


def show(label: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    s = summarize_trades([x["trade"] for x in items])
    print(
        f"  {label:56s} | N={s['total_trades']:4d} | WR={s['win_rate_pct']:5.2f}% | "
        f"TP1={s['tp1_hit_rate_pct']:5.2f}% | AvgNet={s['avg_net_return_pct']:+6.3f}% | "
        f"TotNet={s['total_net_return_pct']:+7.2f}% | PF={s['profit_factor']:4.2f}"
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

    items_50 = collect_trades_with_pst(frames, min_pump=0.50)
    items_15 = collect_trades_with_pst(frames, min_pump=0.15)

    report: dict[str, Any] = {}

    print("\n===============================================================================")
    print("1. CHUẨN HÓA BIÊN ĐỘ SÓNG BẰNG `robust_vol_calc` (SỐ LẦN ĐỘ LỆCH CHUẨN SIGMA)")
    print("   Thay vì chỉ dùng % cứng, đo xem cú bơm gấp bao nhiêu lần biến động chuẩn (Vol Units)")
    print("===============================================================================")
    report["vol_units_sweep"] = {}
    for vu in [4, 6, 8, 10, 12, 14, 16]:
        report["vol_units_sweep"][f">= {vu} VolUnits"] = show(
            f"Biên độ Sóng >= {vu:2d}x Độ Biến Động Chuẩn (robust_vol_calc)",
            [x for x in items_15 if x["pump_vol_units"] >= vu],
        )

    print("\n===============================================================================")
    print("2. ÁP DỤNG `mr_wings(4, 16)` & `ewmac(16, 64)` CỦA PYSYSTEMTRADE VÀO 480 LỆNH (>=50%)")
    print("===============================================================================")
    report["base_50"] = show("Gốc: Tất cả 480 lệnh có Pump >= 50%", items_50)

    print("\n--- 2A. Phân tách theo `ewmac(16, 64)` (Xu hướng vĩ mô chuẩn hóa biến động) ---")
    report["ewmac_16_64_split"] = {
        "bear_regime_lt_0": show(
            "ewmac(16, 64) <= 0 (Xu hướng lớn đang Giảm / Bear Rally)",
            [x for x in items_50 if x["peak_ewmac_16_64"] <= 0.0],
        ),
        "mod_bull_0_to_25": show(
            "0 < ewmac(16, 64) < 2.5 (Xu hướng tăng vừa phải)",
            [x for x in items_50 if 0.0 < x["peak_ewmac_16_64"] < 2.5],
        ),
        "extreme_bull_ge_25": show(
            "ewmac(16, 64) >= 2.5 (Siêu Bull Trend cực mạnh - Chặn tàu)",
            [x for x in items_50 if x["peak_ewmac_16_64"] >= 2.5],
        ),
    }

    print("\n--- 2B. Phân tách theo `mr_wings(4, 16)` (Độ căng cực đoan Z-score của EWMAC ngắn hạn) ---")
    report["mr_wings_split"] = {
        "wings_extreme_ge_15": show(
            "mr_wings Z >= 1.5 sigma (Cánh cực đoan quá mua ngắn hạn)",
            [x for x in items_50 if x["peak_mr_wings_z"] >= 1.5],
        ),
        "wings_super_ge_20": show(
            "mr_wings Z >= 2.0 sigma (Cánh cực đoan > 2 Sigma)",
            [x for x in items_50 if x["peak_mr_wings_z"] >= 2.0],
        ),
        "wings_normal_lt_15": show(
            "mr_wings Z < 1.5 sigma (Chưa tới vùng cực đoan mr_wings)",
            [x for x in items_50 if x["peak_mr_wings_z"] < 1.5],
        ),
    }

    print("\n--- 2C. Phân tách theo `accel(4, 16)` (Gia tốc sóng đã gãy âm mạnh khi vào lệnh) ---")
    report["accel_split"] = {
        "decel_strong_lt_neg1": show(
            "cur_accel(4, 16) <= -1.0 (Gia tốc tăng đã gãy sập mạnh)",
            [x for x in items_50 if x["cur_accel_4_16"] <= -1.0],
        ),
        "decel_mild_gt_neg1": show(
            "cur_accel(4, 16) > -1.0 (Gia tốc tăng chưa giảm mạnh)",
            [x for x in items_50 if x["cur_accel_4_16"] > -1.0],
        ),
    }

    print("\n--- 2D. KẾT HỢP PYSYSTEMTRADE (`pump_vol_units` + `ewmac_16_64` + `mr_wings` / `accel`) ---")
    pst_combo_1 = [
        x
        for x in items_50
        if x["peak_ewmac_16_64"] < 2.5 and (x["peak_mr_wings_z"] >= 1.8 or x["peak_ewmac_16_64"] <= 0.0)
    ]
    pst_combo_2 = [
        x
        for x in items_50
        if x["peak_ewmac_16_64"] < 2.5 and x["cur_accel_4_16"] <= -1.0 and x["pump_vol_units"] >= 8.0
    ]
    report["pst_combos"] = {
        "combo_mr_wings_and_regime": show(
            "★ PST Combo 1: (ewmac_16_64 < 2.5) & (mr_wings>=1.8 hoặc Bear)",
            pst_combo_1,
        ),
        "combo_vol_accel_regime": show(
            "★ PST Combo 2: (VolUnits>=8) & (ewmac_16_64<2.5) & (accel<=-1)",
            pst_combo_2,
        ),
    }

    Path("artifacts/fibo_trend_short/factor1_pysystemtrade_study_2025.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print("\nSaved pysystemtrade study to artifacts/fibo_trend_short/factor1_pysystemtrade_study_2025.json")


if __name__ == "__main__":
    main()
