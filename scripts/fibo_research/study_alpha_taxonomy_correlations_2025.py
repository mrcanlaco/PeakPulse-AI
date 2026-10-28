"""Compute empirical correlation, overlap (Jaccard similarity), and orthogonal vs redundant
combination metrics across surface indicators on the 480 trades (Pump >= 50%, In-Sample 2024-2025).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from study_factor1_multi_repo_benchmark_2025 import collect_enriched_trades
from dao_vang.fibo_short.backtest import (
    DATA_LAKE_5M_DIR,
    IN_SAMPLE_MAX_UTC,
    SHARED_1H_DIR,
    load_historical_1h_frame,
    summarize_trades,
)


def jaccard(mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    inter = int(np.sum(mask_a & mask_b))
    union = int(np.sum(mask_a | mask_b))
    return round(inter / union * 100.0, 1) if union > 0 else 0.0


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
    df = pd.DataFrame(
        [
            {
                "ker_wave": x["ker_wave"],
                "pump_velocity_per_day": x["pump_velocity_per_day"],
                "inv_duration_days": 1.0 / max(0.25, x["pump_days_equiv"]),
                "pump_days_equiv": x["pump_days_equiv"],
                "qlib_rsqr_14": x["qlib_rsqr_14"],
                "peak_ewmac_16_64": x["peak_ewmac_16_64"],
                "cur_accel_4_16": x["cur_accel_4_16"],
                "peak_vol_ratio_20": x["peak_vol_ratio_20"],
                "peak_cluster_wick": x["peak_cluster_wick"],
                "net_return_pct": x["trade"].net_return_pct,
            }
            for x in items
        ]
    )

    corr = df[
        [
            "ker_wave",
            "pump_velocity_per_day",
            "inv_duration_days",
            "qlib_rsqr_14",
            "peak_ewmac_16_64",
            "cur_accel_4_16",
            "peak_vol_ratio_20",
            "peak_cluster_wick",
        ]
    ].corr(method="spearman")

    print("=== SPEARMAN RANK CORRELATION MATRIX ACROSS SURFACE INDICATORS (480 TRADES) ===")
    print(corr.round(3).to_string())

    # Binary signal masks
    m_ker60 = (df["ker_wave"] >= 0.60).to_numpy()
    m_ker35 = (df["ker_wave"] >= 0.35).to_numpy()
    m_vel8 = (df["pump_velocity_per_day"] >= 8.0).to_numpy()
    m_short_dur = (df["pump_days_equiv"] <= 8.0).to_numpy()
    m_bear = (df["peak_ewmac_16_64"] <= 0.0).to_numpy()
    m_accel = (df["cur_accel_4_16"] <= -1.0).to_numpy()
    m_pst = m_bear | m_accel
    m_vol20 = (df["peak_vol_ratio_20"] >= 2.0).to_numpy()

    print("\n=== OVERLAP (JACCARD %) BETWEEN SAME-MECHANISM vs CROSS-MECHANISM SIGNALS ===")
    print(f"1. Cùng cơ chế 'Khoảng Không Thanh Khoản' (Velocity >= 8%/ngày vs Duration <= 8 ngày): {jaccard(m_vel8, m_short_dur)}%")
    print(f"2. Cùng cơ chế 'Khoảng Không Thanh Khoản' (KER >= 0.60 vs Velocity >= 8%/ngày):        {jaccard(m_ker60, m_vel8)}%")
    print(f"3. Cùng cơ chế 'Khoảng Không Thanh Khoản' (KER >= 0.35 vs Duration <= 8 ngày):         {jaccard(m_ker35, m_short_dur)}%")
    print(f"4. Khác cơ chế (Chế độ Bear ewmac<=0 vs Gia tốc gãy accel<=-1):                        {jaccard(m_bear, m_accel)}%")
    print(f"5. Khác cơ chế (PST Xu hướng/Gia tốc vs KER >= 0.35 Khoảng không thanh khoản):         {jaccard(m_pst, m_ker35)}%")
    print(f"6. Khác cơ chế (PST Xu hướng/Gia tốc vs Volume Climax >= 2.0x):                        {jaccard(m_pst, m_vol20)}%")

    print("\n=== SO SÁNH KẾT HỢP TRÙNG LẶP (CÙNG TẦNG CƠ CHẾ) vs KẾT HỢP TRỰC GIAO (KHÁC TẦNG CƠ CHẾ) ===")
    for name, cond in [
        ("Đơn lẻ: Velocity >= 8%/ngày", m_vel8),
        ("Kết hợp Trùng lặp (Cùng cơ chế): Velocity >= 8% AND Duration <= 8 ngày", m_vel8 & m_short_dur),
        ("Kết hợp Trùng lặp (Cùng cơ chế): KER >= 0.60 AND Velocity >= 8%/ngày", m_ker60 & m_vel8),
        ("Đơn lẻ: PST (ewmac<=0 OR accel<=-1)", m_pst),
        ("★ Kết hợp Trực giao (Khác cơ chế): PST AND KER >= 0.35", m_pst & m_ker35),
        ("★ Kết hợp Trực giao (Khác cơ chế): PST AND KER >= 0.40", m_pst & (df["ker_wave"] >= 0.40).to_numpy()),
    ]:
        sub = [items[i]["trade"] for i in range(len(items)) if cond[i]]
        s = summarize_trades(sub)
        print(
            f"  {name:72s} | N={s['total_trades']:3d} | WR={s['win_rate_pct']:5.2f}% | "
            f"Avg={s['avg_net_return_pct']:+6.3f}% | Tot={s['total_net_return_pct']:+7.2f}% | PF={s['profit_factor']:4.2f} | DD={s['max_drawdown_pct']:5.1f}%"
        )


if __name__ == "__main__":
    main()
