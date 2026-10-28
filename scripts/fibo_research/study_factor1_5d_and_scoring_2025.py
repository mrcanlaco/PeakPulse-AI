"""Test the remaining orthogonal dimensions of Factor #1 on the 480 trades (Pump >= 50%, 2024-2025):
1. Dimension 2 (Volume Profile Anatomy along the wave):
   - `top_vol_share`: Volume in the top 1/3 of the wave (near Swing High) vs mean wave volume
   - `vol_climax_peak`: Peak cluster volume / SMA20(volume)
2. Dimension 3 (Cross-Sectional / BTC Market Context):
   - `btc_ewmac_16_64` at the time the coin forms its Swing High / Entry
   - `excess_pump_vs_btc`: Coin's prior_pump_pct minus BTC's return over the exact same window (Idiosyncratic Pump vs Beta Pump)
3. Dimension 5 (Asset Class DNA):
   - High-Beta Altcoins vs Institutional Majors (BTC, ETH, SOL, BNB)
4. Orthogonal 4-Layer Alpha Scoring System (0 -> 100 points):
   - Convert binary filters into an additive, non-collinear Multi-Layer Alpha Score and test performance by Score Tier (Tier C < 50, Tier B 50-69, Tier A 70-84, Tier S >= 85).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from study_factor1_multi_repo_benchmark_2025 import (
    calc_multi_repo_htf_features,
    collect_enriched_trades,
)
from dao_vang.fibo_short.backtest import (
    DATA_LAKE_5M_DIR,
    IN_SAMPLE_MAX_UTC,
    SHARED_1H_DIR,
    load_historical_1h_frame,
    resample_1h_to_htf,
    summarize_trades,
)


def show(label: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    s = summarize_trades([x["trade"] for x in items])
    print(
        f"  {label:66s} | N={s['total_trades']:3d} | WR={s['win_rate_pct']:5.2f}% | "
        f"TP1={s['tp1_hit_rate_pct']:5.2f}% | Avg={s['avg_net_return_pct']:+6.3f}% | "
        f"Tot={s['total_net_return_pct']:+7.2f}% | PF={s['profit_factor']:4.2f} | DD={s['max_drawdown_pct']:5.1f}%"
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

    # Precompute BTC 4h and 1d features for Cross-Sectional / Beta context
    btc_df = frames["BTCUSDT"].loc[frames["BTCUSDT"].index <= IN_SAMPLE_MAX_UTC].sort_index()
    btc_htf: dict[str, pd.DataFrame] = {}
    for tf in ("4h", "1d"):
        bdf = resample_1h_to_htf(btc_df, tf)
        bdf = calc_multi_repo_htf_features(bdf)
        btc_htf[tf] = bdf

    items = collect_enriched_trades(frames, min_pump=0.50)

    # Enrich each trade with BTC Cross-Sectional Context & Asset DNA & 4-Layer Score
    majors = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"}
    for x in items:
        tf = x["tf"]
        bdf = btc_htf[tf]
        entry_ts = pd.Timestamp(x["trade"].entry_time)
        # Find latest closed BTC HTF bar at or before entry_ts
        past_btc = bdf.loc[pd.to_datetime(bdf["close_time"]) <= entry_ts]
        if len(past_btc) >= 5:
            last_btc = past_btc.iloc[-1]
            btc_ewmac_16_64 = float(last_btc["ewmac_16_64"])
            btc_ewmac_4_16 = float(last_btc["ewmac_4_16"])
            lb = min(len(past_btc) - 1, max(1, int(x["pump_bars"])))
            btc_ret_pct = float((last_btc["close"] - past_btc.iloc[-1 - lb]["close"]) / past_btc.iloc[-1 - lb]["close"] * 100.0)
        else:
            btc_ewmac_16_64 = 0.0
            btc_ewmac_4_16 = 0.0
            btc_ret_pct = 0.0

        x["btc_ewmac_16_64"] = btc_ewmac_16_64
        x["btc_ewmac_4_16"] = btc_ewmac_4_16
        x["btc_ret_pct"] = btc_ret_pct
        x["idiosyncratic_spread_pct"] = x["prior_pump_pct"] - max(0.0, btc_ret_pct)
        x["is_major"] = x["symbol"] in majors

        # Compute 4-Layer Orthogonal Conviction Score (0 -> 100 points)
        # Layer 1 (Crowd Euphoria Amplitude): max 20 pts
        if x["prior_pump_pct"] >= 100.0:
            s_l1 = 20
        elif x["prior_pump_pct"] >= 70.0:
            s_l1 = 15
        else:
            s_l1 = 10

        # Layer 3 (Macro Regime & Cross-Sectional Context): max 30 pts
        s_l3 = 0
        if x["peak_ewmac_16_64"] <= 0.0:
            s_l3 += 22  # Bear Market Rally on coin
        elif x["peak_ewmac_16_64"] < 2.0:
            s_l3 += 8
        if x["btc_ewmac_4_16"] <= 0.5:
            s_l3 += 8  # BTC is not in a parabolic surge

        # Layer 2A (Microstructure Air-Pocket Vacuum & Volume Climax): max 30 pts
        s_l2_vac = 0
        if x["ker_wave"] >= 0.60:
            s_l2_vac += 24
        elif x["ker_wave"] >= 0.40:
            s_l2_vac += 18
        elif x["ker_wave"] >= 0.35:
            s_l2_vac += 14
        if x["peak_vol_ratio_20"] >= 1.8:
            s_l2_vac += 6

        # Layer 2B (Momentum Deceleration at Entry): max 20 pts
        s_l2_decel = 0
        if x["cur_accel_4_16"] <= -1.5:
            s_l2_decel += 20
        elif x["cur_accel_4_16"] <= -1.0:
            s_l2_decel += 16
        elif x["cur_accel_4_16"] <= -0.3:
            s_l2_decel += 6

        x["alpha_score_f1"] = s_l1 + s_l3 + s_l2_vac + s_l2_decel

    print("\n======================================================================================================")
    print("1. KIỂM ĐỊNH CHIỀU SỐ 3: TƯƠNG QUAN CHÉO VỚI BTC (IDIOSYNCRATIC PUMP vs BTC BULL SURGE)")
    print("======================================================================================================")
    show("BTC đang yếu / đi ngang (btc_ewmac_4_16 <= 0.5) khi Altcoin bơm", [x for x in items if x["btc_ewmac_4_16"] <= 0.5])
    show("BTC đang tăng nóng (btc_ewmac_4_16 > 0.5) khi Altcoin bơm", [x for x in items if x["btc_ewmac_4_16"] > 0.5])
    show("Bơm cô lập vượt trội BTC >= 60% (Idiosyncratic Spread >= 60%)", [x for x in items if x["idiosyncratic_spread_pct"] >= 60.0])
    show("Bơm theo thị trường chung (Idiosyncratic Spread < 60%)", [x for x in items if x["idiosyncratic_spread_pct"] < 60.0])

    print("\n======================================================================================================")
    print("2. KIỂM ĐỊNH CHIỀU SỐ 5: PHÂN TÁCH NHÓM COIN (HIGH-BETA ALTCOINS vs MAJOR COINS)")
    print("======================================================================================================")
    show("Nhóm Major Coins (BTC, ETH, SOL, BNB) có sóng >= 50%", [x for x in items if x["is_major"]])
    show("Nhóm Altcoin / Meme có sóng >= 50%", [x for x in items if not x["is_major"]])
    show("Nhóm Major Coins sau khi lọc PST + KER >= 0.35", [x for x in items if x["is_major"] and x["pst_pass"] and x["ker_wave"] >= 0.35])
    show("Nhóm Altcoin sau khi lọc PST + KER >= 0.35", [x for x in items if (not x["is_major"]) and x["pst_pass"] and x["ker_wave"] >= 0.35])

    print("\n======================================================================================================")
    print("3. HỆ THỐNG CHẤM ĐIỂM HỘI TỤ 4 TẦNG (ORTHOGONAL ALPHA SCORE 0 -> 100 CHO FACTOR #1)")
    print("======================================================================================================")
    report_scores = {}
    for label, lo, hi in [
        ("Hạng D (< 35 điểm): Sóng tăng bền vững / Nhiễu (Cấm Short)", 0, 34),
        ("Hạng C (35 – 49 điểm): Hội tụ yếu (Đứng ngoài)", 35, 49),
        ("Hạng B (50 – 64 điểm): Hội tụ Cơ bản (Vào 0.5R – 1.0R)", 50, 64),
        ("★ Hạng A (65 – 79 điểm): Hội tụ Mạnh (Vào 1.0R – 1.5R)", 65, 79),
        ("🏆 Hạng S (>= 80 điểm): Siêu Hội Tụ 4 Tầng (Vào 2.0R)", 80, 200),
        ("🔥 Tổng hợp giao dịch (Hạng B + A + S: Score >= 50)", 50, 200),
        ("⚡ Tinh hoa giao dịch (Hạng A + S: Score >= 65)", 65, 200),
    ]:
        sub = [x for x in items if lo <= x["alpha_score_f1"] <= hi]
        report_scores[label] = show(label, sub)

    Path("artifacts/fibo_trend_short/factor1_scoring_study_2025.json").write_text(
        json.dumps(report_scores, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nSaved 4-Layer Scoring study to artifacts/fibo_trend_short/factor1_scoring_study_2025.json")


if __name__ == "__main__":
    main()
