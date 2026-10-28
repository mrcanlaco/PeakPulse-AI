"""Print clean summary tables from insample_2020_2025_by_year_study.json."""

import json
from pathlib import Path

d = json.loads(
    (Path(__file__).resolve().parents[2] / "artifacts/fibo_trend_short/insample_2020_2025_by_year_study.json").read_text(
        encoding="utf-8"
    )
)

print("=== OVERALL 6-YEAR (2020-2025) vs (2020-2023) vs (2024-2025) ===")
for k, v in d["milestones"].items():
    ov = v["overall_2020_2025"]
    p1 = v["period_2020_2023"]
    p2 = v["period_2024_2025"]
    print(
        f"{k:22s} | 2020-25: N={ov['total_trades']:5d} WR={ov['win_rate_pct']:5.2f}% Avg={ov['avg_net_return_pct']:+6.3f}% Tot={ov['total_net_return_pct']:+8.2f}% PF={ov['profit_factor']:4.2f} AvgR={ov['avg_r_multiple']:+5.2f}R DD={ov['max_drawdown_pct']:6.1f}%"
    )
    print(
        f"{'':22s} | 2020-23: N={p1['total_trades']:5d} WR={p1['win_rate_pct']:5.2f}% Avg={p1['avg_net_return_pct']:+6.3f}% Tot={p1['total_net_return_pct']:+8.2f}% PF={p1['profit_factor']:4.2f} AvgR={p1['avg_r_multiple']:+5.2f}R DD={p1['max_drawdown_pct']:6.1f}%"
    )
    print(
        f"{'':22s} | 2024-25: N={p2['total_trades']:5d} WR={p2['win_rate_pct']:5.2f}% Avg={p2['avg_net_return_pct']:+6.3f}% Tot={p2['total_net_return_pct']:+8.2f}% PF={p2['profit_factor']:4.2f} AvgR={p2['avg_r_multiple']:+5.2f}R DD={p2['max_drawdown_pct']:6.1f}%"
    )

print("\n=== CONVICTION TIERS (2020-2025) ===")
for k, v in d["conviction_tiers"].items():
    ov = v["overall_2020_2025"]
    p1 = v["period_2020_2023"]
    p2 = v["period_2024_2025"]
    print(
        f"{k:18s} | 2020-25: N={ov['total_trades']:4d} WR={ov['win_rate_pct']:5.2f}% Avg={ov['avg_net_return_pct']:+6.3f}% Tot={ov['total_net_return_pct']:+7.2f}% PF={ov['profit_factor']:4.2f} DD={ov['max_drawdown_pct']:5.1f}%"
    )
    for y in ["2020", "2021", "2022", "2023", "2024", "2025"]:
        ym = v["by_year"][y]
        print(
            f"   Year {y}: N={ym['total_trades']:3d} WR={ym['win_rate_pct']:5.2f}% Avg={ym['avg_net_return_pct']:+6.3f}% Tot={ym['total_net_return_pct']:+7.2f}% PF={ym['profit_factor']:4.2f} DD={ym['max_drawdown_pct']:5.1f}%"
        )
