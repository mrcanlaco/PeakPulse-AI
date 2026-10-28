import json
from pathlib import Path

p = Path(r"D:\Quant_Backtest_2020_2026\results\multiyear_top10_audit_results.json")
with open(p, "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"Total candidates in json: {len(data)}")
for item in data:
    k = item.get("id", item.get("name", "unknown"))
    std = item.get("overall", {}).get("standard", {})
    stress = item.get("overall", {}).get("stress", {})
    sym = item.get("symbol", "")
    print(f"{k[:45]:<45} ({sym:<7}) | Std: Calmar={std.get('calmar', 0):.2f}, CAGR={std.get('cagr', 0)*100:+.2f}%, MaxDD={std.get('max_dd', 0)*100:.2f}% | Stress Calmar={stress.get('calmar', 0):.2f}")
