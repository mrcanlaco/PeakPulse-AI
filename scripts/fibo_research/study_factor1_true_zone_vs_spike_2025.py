"""Precise dissection of Factor #1 ('Prior Pump >= 50%'):
1. Is the bottom a TRUE VALUE ZONE (SMA10/SMA20 of closes around prior_low) or just a 1-candle liquidity wick?
2. Is the move a 1-3 bar 'overnight spike' (ngày trước sang ngày sau) or a multi-bar wave? (Separated by D1 and H4)
3. At the Swing High, what is the relation to Moving Averages (MA20, MA50, MA100, MA200)?
   - Case A: Macro Bear Trend Bounce (EMA20 <= EMA50 or Price below MA100/MA200, bouncing >=50% into MA resistance then breaking down)
   - Case B: Moderate Overextension above MA50
   - Case C: Runaway Bull Trend (Price far above MA50/MA100 with all MAs stacked bullishly)
"""

from __future__ import annotations

import json
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


def collect_trades_with_ma_context(frames: dict[str, pd.DataFrame], min_pump: float = 0.50) -> list[dict[str, Any]]:
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
            ema100_all = compute_ema(closes_all, 100)
            ema200_all = compute_ema(closes_all, 200)

            for idx_htf, (open_ts, row) in enumerate(htf_df.iterrows()):
                c_ts = pd.Timestamp(row["close_time"])
                htf_close_times.append(c_ts)
                # 7-bar SMA of closes around this bar (strictly point-in-time up to idx_htf)
                c_slice_7 = closes_all[max(0, idx_htf - 6) : idx_htf + 1]
                c_slice_20 = closes_all[max(0, idx_htf - 19) : idx_htf + 1]
                c_slice_50 = closes_all[max(0, idx_htf - 49) : idx_htf + 1]
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
                        "sma7": sum(c_slice_7) / len(c_slice_7),
                        "sma20": sum(c_slice_20) / len(c_slice_20),
                        "sma50": sum(c_slice_50) / len(c_slice_50),
                        "ema20": ema20_all[idx_htf],
                        "ema50": ema50_all[idx_htf],
                        "ema100": ema100_all[idx_htf],
                        "ema200": ema200_all[idx_htf],
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

                if htf_ptr < 6:
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
                if peak_bar is None or low_bar is None:
                    continue

                swing_high = sig.wave.swing_high_price
                prior_low = sig.wave.prior_low_price

                # A. True Zone vs Wick at the Bottom:
                # Compare Swing High against the 7-bar SMA of closes AT THE LOW BAR (the value zone before the pump started)
                base_zone_ma_at_low = low_bar["sma7"]
                pump_from_low_zone_ma = (
                    (swing_high - base_zone_ma_at_low) / base_zone_ma_at_low if base_zone_ma_at_low > 0 else 0.0
                )
                # Also compare Swing High against the Close of the Low Bar (not its lower wick)
                pump_from_low_close = (
                    (swing_high - low_bar["close"]) / low_bar["close"] if low_bar["close"] > 0 else 0.0
                )
                # Wick distortion ratio: how far was prior_low below the base_zone_ma_at_low?
                bottom_wick_distortion = (
                    (base_zone_ma_at_low - prior_low) / base_zone_ma_at_low if base_zone_ma_at_low > 0 else 0.0
                )

                # B. Pump Duration (number of HTF candles from low_bar to peak_bar)
                pump_bars = max(1, peak_bar["htf_idx"] - low_bar["htf_idx"])

                # C. Moving Average Context at Peak and Entry
                peak_vs_ema50 = (swing_high - peak_bar["ema50"]) / peak_bar["ema50"]
                peak_vs_ema200 = (swing_high - peak_bar["ema200"]) / peak_bar["ema200"]
                ema20_gt_ema50 = peak_bar["ema20"] > peak_bar["ema50"]
                ema50_gt_ema200 = peak_bar["ema50"] > peak_bar["ema200"]

                enriched.append(
                    {
                        "trade": trade_obj,
                        "tf": tf,
                        "wick_pump_pct": sig.wave.prior_pump_pct,
                        "pump_from_low_zone_ma": pump_from_low_zone_ma,
                        "pump_from_low_close": pump_from_low_close,
                        "bottom_wick_distortion": bottom_wick_distortion,
                        "pump_bars": pump_bars,
                        "peak_vs_ema50": peak_vs_ema50,
                        "peak_vs_ema200": peak_vs_ema200,
                        "ema20_gt_ema50": ema20_gt_ema50,
                        "ema50_gt_ema200": ema50_gt_ema200,
                    }
                )

    return enriched


def show(label: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    s = summarize_trades([x["trade"] for x in items])
    print(
        f"  {label:54s} | N={s['total_trades']:4d} | WR={s['win_rate_pct']:5.2f}% | "
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

    items = collect_trades_with_ma_context(frames, min_pump=0.50)

    print("\n==========================================================================")
    print("CÂU HỎI 1: TĂNG TỪ 'VÙNG GIÁ NỀN' (MA TẠI ĐÁY) HAY CHỈ TỪ 1 RÂU NẾN QUÉT SÂU?")
    print("==========================================================================")
    show("Tổng 480 lệnh có Wick-to-Wick Pump >= 50%", items)
    show(
        "1A. Tăng THẬT từ Vùng Giá Nền (Đỉnh vs MA7_Đáy >= 45%)",
        [x for x in items if x["pump_from_low_zone_ma"] >= 0.45],
    )
    show(
        "1B. Tăng VỪA từ Vùng Giá Nền (Đỉnh vs MA7_Đáy: 30% -> 45%)",
        [x for x in items if 0.30 <= x["pump_from_low_zone_ma"] < 0.45],
    )
    show(
        "1C. Ảo giác Râu Đáy (Wick>=50% nhưng so với MA7_Đáy < 30%)",
        [x for x in items if x["pump_from_low_zone_ma"] < 0.30],
    )

    print("\n==========================================================================")
    print("CÂU HỎI 2: TĂNG 'NGÀY TRƯỚC SANG NGÀY SAU' (1-3 NẾN) HAY SÓNG DÀI NHIỀU NẾN?")
    print("==========================================================================")
    for tf_label, tf_code in [("TOÀN BỘ (H4 + D1)", None), ("RIÊNG KHUNG D1 (1 nến = 1 ngày)", "1d"), ("RIÊNG KHUNG H4 (1 nến = 4 giờ)", "4h")]:
        print(f"\n--- {tf_label} ---")
        sub = items if tf_code is None else [x for x in items if x["tf"] == tf_code]
        show("  Tăng sốc 1 - 3 nến (Ngày trước sang ngày sau)", [x for x in sub if x["pump_bars"] <= 3])
        show("  Tăng 4 - 8 nến (Sóng ngắn)", [x for x in sub if 4 <= x["pump_bars"] <= 8])
        show("  Tăng 9 - 15 nến (Sóng trung bình)", [x for x in sub if 9 <= x["pump_bars"] <= 15])
        show("  Tăng 16 - 24 nến (Sóng xây nền dài)", [x for x in sub if x["pump_bars"] >= 16])

    print("\n==========================================================================")
    print("CÂU HỎI 3: VỊ THẾ ĐỈNH SO VỚI CÁC ĐƯỜNG MA LỚN (EMA20 / EMA50 / EMA200)")
    print("==========================================================================")
    q3_a = show(
        "3A. Bear Market Rally (EMA20 <= EMA50: Hồi >=50% trong Trend Giảm)",
        [x for x in items if not x["ema20_gt_ema50"]],
    )
    q3_b = show(
        "3B. Bull Overextension vừa phải (EMA20 > EMA50 & vượt EMA50 < 35%)",
        [x for x in items if x["ema20_gt_ema50"] and x["peak_vs_ema50"] < 0.35],
    )
    q3_d = show(
        "3D. Bull Overextension cao (EMA20 > EMA50 & vượt EMA50: 35% -> 50%)",
        [x for x in items if x["ema20_gt_ema50"] and 0.35 <= x["peak_vs_ema50"] < 0.50],
    )
    q3_c = show(
        "3C. Runaway Bull Trend (EMA20 > EMA50 & Đỉnh vượt xa EMA50 >= 50%)",
        [x for x in items if x["ema20_gt_ema50"] and x["peak_vs_ema50"] >= 0.50],
    )

    # Combined Alpha Filter on Factor #1:
    # Keep waves >= 50% that are NOT Runaway Bull Trend (i.e. exclude EMA20>EMA50 & peak_vs_ema50>=50%)
    # AND have wave duration in the sweet spot (D1: 1-8 bars OR EMA20<=EMA50; H4: >= 9 bars)
    filtered_alpha = [
        x
        for x in items
        if not (x["ema20_gt_ema50"] and x["peak_vs_ema50"] >= 0.50)
        and ((x["tf"] == "4h" and x["pump_bars"] >= 9) or (x["tf"] == "1d" and (x["pump_bars"] <= 8 or not x["ema20_gt_ema50"])))
    ]
    excluded_noise = [x for x in items if x not in filtered_alpha]
    print("\n==========================================================================")
    print("TỔNG HỢP LỌC FACTOR #1 BẰNG MA & THỜI GIAN SÓNG")
    print("==========================================================================")
    f_keep = show("★ Giữ lại (Đúng cấu trúc MA + Đúng độ dài sóng)", filtered_alpha)
    f_drop = show("✗ Loại bỏ (Chặn tàu Bull Run vượt EMA50>=50% / Sóng D1 rề rà)", excluded_noise)

    out_data = {
        "q1_bottom_zone_ma": {
            "all_50": summarize_trades([x["trade"] for x in items]),
            "wick_rebound_under_30pct_ma7": summarize_trades([x["trade"] for x in items if x["pump_from_low_zone_ma"] < 0.30]),
            "mid_zone_30_45pct_ma7": summarize_trades([x["trade"] for x in items if 0.30 <= x["pump_from_low_zone_ma"] < 0.45]),
            "true_zone_over_45pct_ma7": summarize_trades([x["trade"] for x in items if x["pump_from_low_zone_ma"] >= 0.45]),
        },
        "q2_duration_d1": {
            "1_3_days": summarize_trades([x["trade"] for x in items if x["tf"] == "1d" and x["pump_bars"] <= 3]),
            "4_8_days": summarize_trades([x["trade"] for x in items if x["tf"] == "1d" and 4 <= x["pump_bars"] <= 8]),
            "9_15_days": summarize_trades([x["trade"] for x in items if x["tf"] == "1d" and 9 <= x["pump_bars"] <= 15]),
            "16_24_days": summarize_trades([x["trade"] for x in items if x["tf"] == "1d" and x["pump_bars"] >= 16]),
        },
        "q2_duration_h4": {
            "1_8_bars_h4": summarize_trades([x["trade"] for x in items if x["tf"] == "4h" and x["pump_bars"] <= 8]),
            "9_15_bars_h4": summarize_trades([x["trade"] for x in items if x["tf"] == "4h" and 9 <= x["pump_bars"] <= 15]),
            "16_24_bars_h4": summarize_trades([x["trade"] for x in items if x["tf"] == "4h" and x["pump_bars"] >= 16]),
        },
        "q3_ma_regime": {
            "bear_rally_ema20_le_ema50": q3_a,
            "bull_mod_under_35pct_ema50": q3_b,
            "bull_high_35_50pct_ema50": q3_d,
            "runaway_bull_over_50pct_ema50": q3_c,
        },
        "synthesized_filter": {
            "kept": f_keep,
            "dropped": f_drop,
        },
    }
    Path("artifacts/fibo_trend_short/factor1_ma_deep_dive_2025.json").write_text(
        json.dumps(out_data, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
