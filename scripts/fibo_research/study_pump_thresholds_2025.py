from __future__ import annotations

import json
from pathlib import Path

from dao_vang.config.settings import FiboTrendShortConfig
from dao_vang.fibo_short.backtest import (
    DATA_LAKE_5M_DIR,
    IN_SAMPLE_MAX_UTC,
    SHARED_1H_DIR,
    backtest_symbol_1h_dataframe,
    load_historical_1h_frame,
    summarize_trades,
)


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

    print(f"Loading 2024-2025 In-Sample 1h data for {len(symbols)} symbols (<= {IN_SAMPLE_MAX_UTC})...")
    frames = {}
    for sym in symbols:
        try:
            df = load_historical_1h_frame(
                sym,
                start_utc="2024-01-01T00:00:00+00:00",
                end_utc=IN_SAMPLE_MAX_UTC,
                strict_in_sample=True,
            )
            if len(df) >= 200:
                frames[sym] = df
        except Exception as exc:
            print(f"Skip {sym}: {exc}")

    print(f"Loaded {len(frames)} symbols.")

    thresholds = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.65, 0.80, 1.00]
    results = {}

    for pump_thr in thresholds:
        cfg = FiboTrendShortConfig(
            min_prior_pump_pct=pump_thr,
            min_impulse_drop_pct=0.04,
            fibo_entry_min=0.500,
            fibo_entry_max=0.618,
            sl_mode="above_swing_high",
            require_both_h1_conditions=False,
        )
        all_trades = []
        for sym, df in frames.items():
            trades = backtest_symbol_1h_dataframe(sym, df, config=cfg, strict_in_sample=True)
            all_trades.extend(trades)

        all_trades.sort(key=lambda t: t.entry_time)
        overall = summarize_trades(all_trades)
        h4_trades = [t for t in all_trades if t.higher_timeframe == "4h"]
        d1_trades = [t for t in all_trades if t.higher_timeframe == "1d"]
        bs2_trades = [t for t in all_trades if t.confirmation_tier == "BREAK_STRUCTURE_2"]
        combo_trades = [t for t in all_trades if t.confirmation_tier == "COMBO_1_2"]
        cp1_trades = [t for t in all_trades if t.confirmation_tier == "CANDLE_PATTERN_1"]

        key = f">= {int(pump_thr * 100)}%"
        results[key] = {
            "pump_threshold_pct": int(pump_thr * 100),
            "overall": overall,
            "4h": summarize_trades(h4_trades),
            "1d": summarize_trades(d1_trades),
            "BREAK_STRUCTURE_2": summarize_trades(bs2_trades),
            "COMBO_1_2": summarize_trades(combo_trades),
            "CANDLE_PATTERN_1": summarize_trades(cp1_trades),
        }
        print(
            f"[Pump {key:6s}] Trades={overall['total_trades']:4d} | "
            f"WR={overall['win_rate_pct']:5.2f}% | "
            f"TP1={overall['tp1_hit_rate_pct']:5.2f}% | "
            f"AvgNet={overall['avg_net_return_pct']:+6.3f}% | "
            f"TotalNet={overall['total_net_return_pct']:+7.2f}% | "
            f"PF={overall['profit_factor']:4.2f} || "
            f"H4: Avg={results[key]['4h']['avg_net_return_pct']:+6.3f}% (PF={results[key]['4h']['profit_factor']:4.2f}, N={results[key]['4h']['total_trades']}) | "
            f"D1: Avg={results[key]['1d']['avg_net_return_pct']:+6.3f}% (PF={results[key]['1d']['profit_factor']:4.2f}, N={results[key]['1d']['total_trades']})"
        )

    out_path = Path("artifacts/fibo_trend_short/pump_amplitude_study_2025.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Saved study to {out_path}")


if __name__ == "__main__":
    main()
