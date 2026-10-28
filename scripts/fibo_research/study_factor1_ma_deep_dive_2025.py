"""Deep-dive Ceteris Paribus study on Factor #1:
What does 'Prior Pump >= 50%' actually mean?
Dissecting:
1. Wick-to-Wick Pump vs Distance above Moving Average Value Zone (SMA20, SMA50, EMA50)
2. Wick-to-Wick Pump vs Distance above Prior Consolidation Base (Median Close of prior base)
3. Pump Duration (1-2 bars 'overnight spike' vs multi-bar sustained wave >= 4-6 bars)
4. MA Regime at Swing High (EMA20 > EMA50 true uptrend expansion vs bear bounce)

Strictly In-Sample: 2024-01-01 -> 2025-12-31 (OOS 2026+ untouched).
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

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


def compute_ema(values: list[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (span + 1.0)
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1.0 - alpha) * out[-1])
    return out


def collect_enriched_trades(frames: dict[str, pd.DataFrame], min_pump: float = 0.20) -> list[dict[str, Any]]:
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

            htf_records: list[dict[str, Any]] = []
            htf_close_times: list[pd.Timestamp] = []
            closes_all = [float(r["close"]) for _, r in htf_df.iterrows()]
            ema20_all = compute_ema(closes_all, 20)
            ema50_all = compute_ema(closes_all, 50)

            for idx_htf, (open_ts, row) in enumerate(htf_df.iterrows()):
                c_ts = pd.Timestamp(row["close_time"])
                htf_close_times.append(c_ts)
                # SMA20 and SMA50 up to idx_htf (Point-in-time)
                c_slice_20 = closes_all[max(0, idx_htf - 19) : idx_htf + 1]
                c_slice_50 = closes_all[max(0, idx_htf - 49) : idx_htf + 1]
                # Base median close before the immediate 5-bar spike: [idx_htf - 30 : idx_htf - 3]
                base_slice = closes_all[max(0, idx_htf - 30) : max(1, idx_htf - 2)]
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
                        "sma20": sum(c_slice_20) / len(c_slice_20),
                        "sma50": sum(c_slice_50) / len(c_slice_50),
                        "ema20": ema20_all[idx_htf],
                        "ema50": ema50_all[idx_htf],
                        "base_median_close": statistics.median(base_slice) if base_slice else float(row["close"]),
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

                # Look up HTF bar at Swing High and Prior Low
                peak_bar = htf_by_open_str.get(sig.wave.swing_high_time)
                low_bar = htf_by_open_str.get(sig.wave.prior_low_time)
                if peak_bar is None or low_bar is None:
                    continue

                swing_high = sig.wave.swing_high_price
                sma20 = peak_bar["sma20"]
                sma50 = peak_bar["sma50"]
                ema20 = peak_bar["ema20"]
                ema50 = peak_bar["ema50"]
                base_median = peak_bar["base_median_close"]

                # 1. Distance of Swing High above SMA50 (Value Zone Overextension)
                dist_above_sma50_pct = (swing_high - sma50) / sma50 if sma50 > 0 else 0.0
                dist_above_sma20_pct = (swing_high - sma20) / sma20 if sma20 > 0 else 0.0
                dist_above_ema50_pct = (swing_high - ema50) / ema50 if ema50 > 0 else 0.0

                # 2. Pump vs Median Base Close (ignores single-bar downward liquidity wick)
                pump_vs_base_median_pct = (swing_high - base_median) / base_median if base_median > 0 else 0.0

                # 3. Duration of pump in HTF bars (from prior_low bar to swing_high bar)
                pump_bars = max(0, peak_bar["htf_idx"] - low_bar["htf_idx"])

                # 4. Close-to-Close pump (Peak bar close/high vs Prior Low bar close, removing bottom wick)
                low_bar_body_bottom = min(low_bar["open"], low_bar["close"])
                body_pump_pct = (swing_high - low_bar_body_bottom) / low_bar_body_bottom if low_bar_body_bottom > 0 else 0.0

                # 5. MA alignment at peak
                ema20_above_ema50 = ema20 > ema50

                enriched.append(
                    {
                        "trade": trade_obj,
                        "tf": tf,
                        "prior_pump_pct": sig.wave.prior_pump_pct,
                        "dist_above_sma50_pct": dist_above_sma50_pct,
                        "dist_above_sma20_pct": dist_above_sma20_pct,
                        "dist_above_ema50_pct": dist_above_ema50_pct,
                        "pump_vs_base_median_pct": pump_vs_base_median_pct,
                        "body_pump_pct": body_pump_pct,
                        "pump_bars": pump_bars,
                        "ema20_above_ema50": ema20_above_ema50,
                    }
                )

    return enriched


def print_bucket(label: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    trades = [x["trade"] for x in items]
    s = summarize_trades(trades)
    print(
        f"  {label:48s} | N={s['total_trades']:4d} | WR={s['win_rate_pct']:5.2f}% | "
        f"TP1={s['tp1_hit_rate_pct']:5.2f}% | AvgNet={s['avg_net_return_pct']:+6.3f}% | "
        f"TotNet={s['total_net_return_pct']:+7.2f}% | PF={s['profit_factor']:4.2f} | MaxDD={s['max_drawdown_pct']:5.1f}%"
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
    frames = {}
    for sym in symbols:
        df = load_historical_1h_frame(
            sym,
            start_utc="2024-01-01T00:00:00+00:00",
            end_utc=IN_SAMPLE_MAX_UTC,
            strict_in_sample=True,
        )
        if len(df) >= 200:
            frames[sym] = df

    items_50 = collect_enriched_trades(frames, min_pump=0.50)
    items_all = collect_enriched_trades(frames, min_pump=0.20)

    report: dict[str, Any] = {}

    print("\n=====================================================================")
    print("PHẦN 1: TRONG 480 LỆNH 'SÓNG TĂNG >= 50%' (WICK-TO-WICK), CÓ BAO NHIÊU LÀ")
    print("        TĂNG THẬT SO VỚI ĐƯỜNG MA50 / VÙNG GIÁ NỀN VS CHỈ GIẬT RÂU?")
    print("=====================================================================")
    report["base_50"] = print_bucket("Tất cả lệnh có Wick Pump >= 50% (Gốc)", items_50)

    print("\n--- 1A. Chia theo Độ Cao của Đỉnh so với Đường SMA50 (Swing High vs SMA50) ---")
    b_ma_low = [x for x in items_50 if x["dist_above_sma50_pct"] < 0.25]
    b_ma_mid = [x for x in items_50 if 0.25 <= x["dist_above_sma50_pct"] < 0.40]
    b_ma_high = [x for x in items_50 if x["dist_above_sma50_pct"] >= 0.40]
    b_ma_30plus = [x for x in items_50 if x["dist_above_sma50_pct"] >= 0.30]
    report["ma50_split_in_50pump"] = {
        "under_25pct_above_sma50": print_bucket("Đỉnh chỉ cách SMA50 < 25% (Giật từ đáy/Hồi về MA)", b_ma_low),
        "25_to_40pct_above_sma50": print_bucket("Đỉnh vượt SMA50 từ 25% -> 40%", b_ma_mid),
        "over_30pct_above_sma50": print_bucket("Đỉnh vượt xa SMA50 >= 30% (Bứt thoát vùng giá)", b_ma_30plus),
        "over_40pct_above_sma50": print_bucket("Đỉnh vượt xa SMA50 >= 40% (Quá mua cực đại)", b_ma_high),
    }

    print("\n--- 1B. Chia theo Giá Đỉnh so với Vùng Giá Nền Trung Vị (Median Close 30 nến trước) ---")
    b_base_fake = [x for x in items_50 if x["pump_vs_base_median_pct"] < 0.30]
    b_base_real35 = [x for x in items_50 if x["pump_vs_base_median_pct"] >= 0.35]
    b_base_real50 = [x for x in items_50 if x["pump_vs_base_median_pct"] >= 0.50]
    report["median_base_split_in_50pump"] = {
        "fake_wick_under_30pct_base": print_bucket("So với Vùng Nền < 30% (Ảo giác do râu đáy quét sâu)", b_base_fake),
        "real_over_35pct_base": print_bucket("Tăng thật so với Vùng Nền >= 35%", b_base_real35),
        "real_over_50pct_base": print_bucket("Tăng thật so với Vùng Nền >= 50%", b_base_real50),
    }

    print("\n--- 1C. Chia theo Thời Gian Xây Sóng (Tăng ngày trước-ngày sau 1-3 nến vs Sóng bền >= 4 nến) ---")
    b_dur_1_3 = [x for x in items_50 if x["pump_bars"] <= 3]
    b_dur_4_10 = [x for x in items_50 if 4 <= x["pump_bars"] <= 10]
    b_dur_11_24 = [x for x in items_50 if x["pump_bars"] >= 11]
    b_dur_4plus = [x for x in items_50 if x["pump_bars"] >= 4]
    report["duration_split_in_50pump"] = {
        "spike_1_3_bars": print_bucket("Bơm dựng đứng ngắn hạn (1 - 3 nến HTF)", b_dur_1_3),
        "wave_4_10_bars": print_bucket("Sóng tăng trung hạn (4 - 10 nến HTF)", b_dur_4_10),
        "wave_11_24_bars": print_bucket("Sóng tăng kéo dài (11 - 24 nến HTF)", b_dur_11_24),
        "wave_4plus_bars": print_bucket("Sóng tăng có cấu trúc (>= 4 nến HTF)", b_dur_4plus),
    }

    print("\n--- 1D. Chia theo Cấu Trúc Hai Đường MA (EMA20 vs EMA50 tại Đỉnh) ---")
    b_ema_bull = [x for x in items_50 if x["ema20_above_ema50"]]
    b_ema_bear = [x for x in items_50 if not x["ema20_above_ema50"]]
    report["ema_regime_in_50pump"] = {
        "ema20_above_ema50": print_bucket("EMA20 > EMA50 (Đỉnh của xu hướng tăng thật)", b_ema_bull),
        "ema20_below_ema50": print_bucket("EMA20 <= EMA50 (Đỉnh hồi trong xu hướng giảm)", b_ema_bear),
    }

    print("\n=====================================================================")
    print("PHẦN 2: QUÉT TRỰC TIẾP ĐỘ GIÃN CÁCH SO VỚI ĐƯỜNG SMA50 / VÙNG NỀN")
    print("        (THAY VÌ ĐO RÂU NẾN ĐƠN THUẦN)")
    print("=====================================================================")
    report["sma50_overextension_sweep"] = {}
    for ma_thr in [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60]:
        sub = [x for x in items_all if x["dist_above_sma50_pct"] >= ma_thr]
        report["sma50_overextension_sweep"][f">= {int(ma_thr*100)}%"] = print_bucket(
            f"Swing High vượt trên SMA50 >= {int(ma_thr*100)}%", sub
        )

    print("\n--- Kết hợp: (Wick Pump >= 50%) + (Đỉnh vượt SMA50 >= 30%) + (Tăng >= 4 nến) ---")
    combo_true_wave = [
        x
        for x in items_50
        if x["dist_above_sma50_pct"] >= 0.30 and x["pump_vs_base_median_pct"] >= 0.35 and x["pump_bars"] >= 4
    ]
    combo_fake_wave = [x for x in items_50 if x not in combo_true_wave]
    report["true_vs_fake_50pump"] = {
        "true_structural_pump": print_bucket("★ SÓNG TĂNG THẬT (Vượt SMA50>=30% & Nền>=35% & >=4 nến)", combo_true_wave),
        "fake_or_shallow_pump": print_bucket("✗ SÓNG ẢO / GIẬT RÂU (Bị loại bỏ)", combo_fake_wave),
    }

    # Breakdown of true_structural_pump by H4 and D1
    print("\n--- Chi tiết SÓNG TĂNG THẬT theo H4 và D1 ---")
    report["true_structural_by_tf"] = {
        "4h": print_bucket("  -> Khung H4 (Sóng Tăng Thật)", [x for x in combo_true_wave if x["tf"] == "4h"]),
        "1d": print_bucket("  -> Khung D1 (Sóng Tăng Thật)", [x for x in combo_true_wave if x["tf"] == "1d"]),
    }

    out_file = Path("artifacts/fibo_trend_short/factor1_ma_structure_study_2025.json")
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved detailed Factor #1 MA structure study to {out_file}")


if __name__ == "__main__":
    main()
