"""Empirical Study:
1. Reference comparison with Conversation `a1e6ca7d-d365-45e3-8ce0-30c01d6eeca7`
   (`crypto_pysystemtrade/data_adapter.py` & `crypto_factor_statarb_v3_1_vi.md`):
   - Point-in-Time Dynamic Universe (Warmup >= 63d, Rolling 30d Quote Volume Top-K, 5 Crypto Sectors)
   - Zero In-Sample PnL Selection Bias vs Static IS-PnL Whitelist
2. Deep evaluation of Circulating Market Cap (`Price * Circulating Supply`),
   Fully Diluted Valuation (`FDV`), Float Ratio (`Circulating / Total Supply`),
   and Speculative Futures Turnover (`Daily Futures Vol / Circulating Market Cap`)
   across all 338 Binance USD-M Perpetual symbols (IS 2024-2025 -> OOS 2026).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ARTIFACTS_DIR = ROOT_DIR / "artifacts" / "fibo_trend_short"
STUDY_JSON = ARTIFACTS_DIR / "coin_universe_study_2026.json"
CG_CACHE_JSON = ARTIFACTS_DIR / "coingecko_marketcap_cache.json"
OUT_JSON = ARTIFACTS_DIR / "marketcap_and_pit_universe_study_2026.json"


def fetch_or_load_coingecko_markets() -> list[dict]:
    if CG_CACHE_JSON.exists():
        data = json.loads(CG_CACHE_JSON.read_text(encoding="utf-8"))
        if len(data) >= 500:
            return data

    all_cg: list[dict] = []
    for page in range(1, 6):
        try:
            r = httpx.get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": 250,
                    "page": page,
                },
                timeout=15.0,
            )
            if r.status_code == 200:
                batch = r.json()
                if isinstance(batch, list):
                    all_cg.extend(batch)
            time.sleep(0.9)
        except Exception as exc:
            print(f"Warning page {page}: {exc}")
    CG_CACHE_JSON.write_text(json.dumps(all_cg, indent=2), encoding="utf-8")
    return all_cg


def eval_group(name: str, sub: list[dict]) -> dict:
    is_n = sum(p["is_2024_2025"]["m6_f4_expanded"]["total_trades"] for p in sub)
    is_net = round(sum(p["is_2024_2025"]["m6_f4_expanded"]["total_net_return_pct"] for p in sub), 2)
    is4_n = sum(p["is_2024_2025"]["m4_f2_elite"]["total_trades"] for p in sub)
    is4_net = round(sum(p["is_2024_2025"]["m4_f2_elite"]["total_net_return_pct"] for p in sub), 2)

    oos_n = sum(p["oos_2026"]["m6_f4_expanded"]["total_trades"] for p in sub)
    oos_net = round(sum(p["oos_2026"]["m6_f4_expanded"]["total_net_return_pct"] for p in sub), 2)
    oos4_n = sum(p["oos_2026"]["m4_f2_elite"]["total_trades"] for p in sub)
    oos4_net = round(sum(p["oos_2026"]["m4_f2_elite"]["total_net_return_pct"] for p in sub), 2)
    oos6s_n = sum(p["oos_2026"]["m6_f4_elite_sniper"]["total_trades"] for p in sub)
    oos6s_net = round(sum(p["oos_2026"]["m6_f4_elite_sniper"]["total_net_return_pct"] for p in sub), 2)

    active_oos_coins = [p for p in sub if p["oos_2026"]["m6_f4_expanded"]["total_trades"] > 0]
    pos_oos_coins = [p for p in active_oos_coins if p["oos_2026"]["m6_f4_expanded"]["total_net_return_pct"] > 0]
    coin_win_breadth_oos = round(len(pos_oos_coins) / len(active_oos_coins) * 100.0, 1) if active_oos_coins else 0.0

    print(
        f"{name:56s} | {len(sub):3d} mã | "
        f"IS M6B: N={is_n:4d}, Net={is_net:+8.1f}% | "
        f"OOS M6B: N={oos_n:3d}, Net={oos_net:+7.1f}% (Breadth {coin_win_breadth_oos:4.1f}%) | "
        f"OOS M4A: N={oos4_n:3d}, Net={oos4_net:+7.1f}%"
    )
    return {
        "group_name": name,
        "coin_count": len(sub),
        "is_m6b_trades": is_n,
        "is_m6b_net_pct": is_net,
        "is_m4a_trades": is4_n,
        "is_m4a_net_pct": is4_net,
        "oos_m6b_trades": oos_n,
        "oos_m6b_net_pct": oos_net,
        "oos_m6b_coin_breadth_pct": coin_win_breadth_oos,
        "oos_m4a_trades": oos4_n,
        "oos_m4a_net_pct": oos4_net,
        "oos_m6s_trades": oos6s_n,
        "oos_m6s_net_pct": oos6s_net,
    }


def main() -> None:
    all_cg = fetch_or_load_coingecko_markets()
    print(f"Loaded {len(all_cg)} CoinGecko market cap & supply records.")

    cg_map: dict[str, dict] = {}
    for item in all_cg:
        sym = str(item.get("symbol", "")).upper()
        if sym not in cg_map or (item.get("market_cap") or 0) > (cg_map[sym].get("market_cap") or 0):
            cg_map[sym] = item

    d = json.loads(STUDY_JSON.read_text(encoding="utf-8"))
    profs: list[dict] = d["symbol_profiles"]

    matched = 0
    for p in profs:
        raw_sym = p["symbol"].replace("USDT", "")
        base_sym = raw_sym[4:] if raw_sym.startswith("1000") else raw_sym
        cg = cg_map.get(base_sym) or cg_map.get(raw_sym)
        if cg and (cg.get("market_cap") or 0) > 0:
            matched += 1
            mcap = float(cg["market_cap"])
            fdv = float(cg.get("fully_diluted_valuation") or mcap)
            circ = float(cg.get("circulating_supply") or 0.0)
            tot = float(cg.get("total_supply") or cg.get("max_supply") or circ)
            float_ratio = min(1.0, circ / tot) if tot > 0 else 1.0
            turnover_pct = (p["median_daily_qvol_usd"] / mcap) * 100.0 if mcap > 0 else 0.0
            mcap_rank = int(cg.get("market_cap_rank") or 999)
        else:
            mcap = 0.0
            fdv = 0.0
            circ = 0.0
            tot = 0.0
            float_ratio = 1.0
            turnover_pct = 999.0 if p["median_daily_qvol_usd"] > 0 else 0.0
            mcap_rank = 9999

        p["mcap_usd"] = round(mcap, 0)
        p["fdv_usd"] = round(fdv, 0)
        p["circulating_supply"] = circ
        p["total_supply"] = tot
        p["float_ratio"] = round(float_ratio, 3)
        p["futures_to_mcap_turnover_pct"] = round(turnover_pct, 2)
        p["mcap_rank"] = mcap_rank

    print(f"Matched {matched}/{len(profs)} Binance Futures symbols with Circulating Supply & Market Cap.\n")

    results: dict[str, list[dict]] = {
        "market_cap_tiers": [],
        "float_ratio_tiers": [],
        "squeeze_risk_turnover_tiers": [],
        "methodology_comparison": [],
    }

    print("========================================================================================================================")
    print("1. GIẢI PHẪU THEO VỐN HÓA LƯU HÀNH (CIRCULATING MARKET CAP = GIÁ x TỔNG CUNG LƯU HÀNH, ĐÃ LOẠI G1 BTC/ETH/BNB/PAXG)")
    print("========================================================================================================================")
    non_g1 = [p for p in profs if p["archetype"] != "G1_STORE_OF_VALUE_MAJOR"]
    results["market_cap_tiers"].append(
        eval_group("MC1: Large-Cap Altcoins (MCap >= $2.0B: SOL, XRP, DOGE, LINK...)", [p for p in non_g1 if p["mcap_usd"] >= 2_000_000_000])
    )
    results["market_cap_tiers"].append(
        eval_group("MC2: Upper Mid-Cap ($500M <= MCap < $2.0B: WIF, PENDLE, INJ...)", [p for p in non_g1 if 500_000_000 <= p["mcap_usd"] < 2_000_000_000])
    )
    results["market_cap_tiers"].append(
        eval_group("MC3: Lower Mid-Cap ($150M <= MCap < $500M: BOME, ORDI, GMT...)", [p for p in non_g1 if 150_000_000 <= p["mcap_usd"] < 500_000_000])
    )
    results["market_cap_tiers"].append(
        eval_group("MC4: Small-Cap ($50M <= MCap < $150M)", [p for p in non_g1 if 50_000_000 <= p["mcap_usd"] < 150_000_000])
    )
    results["market_cap_tiers"].append(
        eval_group("MC5: Micro-Cap / Unranked (< $50M — Cung lưu hành quá nhỏ)", [p for p in non_g1 if p["mcap_usd"] < 50_000_000])
    )
    results["market_cap_tiers"].append(
        eval_group("★ TỔNG HỢP: MCap >= $150M (Đủ Cung Lưu Hành Chống Làm Giá)", [p for p in non_g1 if p["mcap_usd"] >= 150_000_000])
    )
    results["market_cap_tiers"].append(
        eval_group("✗ TỔNG HỢP: MCap < $150M (Cung Lưu Hành Nhỏ -> Bẫy Đội Lái)", [p for p in non_g1 if p["mcap_usd"] < 150_000_000])
    )

    print("\n========================================================================================================================")
    print("2. GIẢI PHẪU TỶ LỆ CUNG LƯU HÀNH / TỔNG CUNG (FLOAT RATIO = CIRCULATING / TOTAL SUPPLY) TRÊN NHÓM MCap >= $150M")
    print("========================================================================================================================")
    mc_150m = [p for p in non_g1 if p["mcap_usd"] >= 150_000_000]
    results["float_ratio_tiers"].append(
        eval_group("Float Cao (Circulating/Total >= 75%: Meme & L1 Đã Phân Phối Đều)", [p for p in mc_150m if p["float_ratio"] >= 0.75])
    )
    results["float_ratio_tiers"].append(
        eval_group("Float Trung Bình (40% <= Circulating/Total < 75%: Có Lịch Unlock)", [p for p in mc_150m if 0.40 <= p["float_ratio"] < 0.75])
    )
    results["float_ratio_tiers"].append(
        eval_group("Low-Float / High-FDV (Circulating/Total < 40%: VC Unlock Nặng)", [p for p in mc_150m if p["float_ratio"] < 0.40])
    )

    print("\n========================================================================================================================")
    print("3. PHÁT HIỆN QUAN TRỌNG: TỶ SỐ SQUEEZE RISK = (FUTURES VOL / CIRCULATING MARKET CAP) & THANH KHOẢN SỔ LỆNH")
    print("========================================================================================================================")
    results["squeeze_risk_turnover_tiers"].append(
        eval_group("An Toàn & Sâu: MCap >= $150M & Futures Vol >= $5M/d & Wick <= 3.5%", [
            p for p in non_g1
            if p["mcap_usd"] >= 150_000_000 and p["median_daily_qvol_usd"] >= 5_000_000 and p["wick_toxicity_p90_pct"] <= 3.5
        ])
    )
    results["squeeze_risk_turnover_tiers"].append(
        eval_group("Siêu Thanh Khoản: MCap >= $250M & Futures Vol >= $10M/d & Wick <= 3.5%", [
            p for p in non_g1
            if p["mcap_usd"] >= 250_000_000 and p["median_daily_qvol_usd"] >= 10_000_000 and p["wick_toxicity_p90_pct"] <= 3.5
        ])
    )
    results["squeeze_risk_turnover_tiers"].append(
        eval_group("Bẫy Cornered Float: MCap < $150M NHƯNG Vol Futures Đầu Cơ Cao", [
            p for p in non_g1
            if p["mcap_usd"] < 150_000_000 and p["median_daily_qvol_usd"] >= 3_000_000
        ])
    )
    results["squeeze_risk_turnover_tiers"].append(
        eval_group("Bẫy Thanh Khoản Mỏng: MCap < $150M & Futures Vol < $3M/d", [
            p for p in non_g1
            if p["mcap_usd"] < 150_000_000 and p["median_daily_qvol_usd"] < 3_000_000
        ])
    )

    print("\n========================================================================================================================")
    print("4. ĐỐI CHIẾU 4 PHƯƠNG PHÁP XÂY DỰNG UNIVERSE (BAO GỒM PHƯƠNG PHÁP a1e6ca7d & KẾT HỢP MARKET CAP EX-ANTE)")
    print("========================================================================================================================")
    # Method 1: Unfiltered 338
    results["methodology_comparison"].append(
        eval_group("M0: Toàn bộ 338 Coin Không Lọc (Unfiltered Baseline)", profs)
    )

    # Method 2: Pure a1e6ca7d Point-in-Time Rule (Age >= 63d, Top 50 by Quote Volume, Wick <= 3.2%, Excl G1 — ZERO IS PnL!)
    pit_vol_sorted = sorted(
        [p for p in non_g1 if p["is_active_days"] >= 63 and p["wick_toxicity_p90_pct"] <= 3.2],
        key=lambda x: x["median_daily_qvol_usd"],
        reverse=True,
    )
    results["methodology_comparison"].append(
        eval_group("M1 (Chuẩn a1e6ca7d PIT): Top-50 Vol + Age>=63d + Wick<=3.2% (0% PnL Bias)", pit_vol_sorted[:50])
    )

    # Method 3: Pure Ex-Ante Market Cap + Liquidity + Archetype Rule (ZERO IS PnL Bias! MCap >= $150M + Vol >= $5M + Age >= 63d + G2/G4)
    pure_mcap_structural = [
        p for p in non_g1
        if p["mcap_usd"] >= 150_000_000
        and p["median_daily_qvol_usd"] >= 5_000_000
        and p["is_active_days"] >= 63
        and p["wick_toxicity_p90_pct"] <= 3.5
        and p["archetype"] in ("G2_LIQUID_L1_L2_DEFI", "G4_LIQUID_MEME_RETAIL")
    ]
    results["methodology_comparison"].append(
        eval_group("M2 (Pure Ex-Ante MCap+Liq+G2/G4): MCap>=$150M & Vol>=$5M (0% PnL Bias)", pure_mcap_structural)
    )

    # Method 4: Hybrid Optimal (a1e6ca7d PIT + Market Cap >= $150M + Structural Alignment IS >= 0)
    hybrid_optimal_s = [
        p for p in non_g1
        if (p["mcap_usd"] >= 150_000_000 or p["archetype"] == "G4_LIQUID_MEME_RETAIL")
        and p["median_daily_qvol_usd"] >= 5_000_000
        and p["is_active_days"] >= 63
        and p["wick_toxicity_p90_pct"] <= 3.6
        and p["archetype"] in ("G2_LIQUID_L1_L2_DEFI", "G4_LIQUID_MEME_RETAIL")
        and (
            (p["is_2024_2025"]["m6_f4_expanded"]["total_net_return_pct"] >= 15.0 and p["is_2024_2025"]["m6_f4_expanded"]["profit_factor"] >= 1.35)
            or (p["archetype"] == "G4_LIQUID_MEME_RETAIL" and p["is_2024_2025"]["m6_f4_expanded"]["total_net_return_pct"] >= 0.0)
        )
    ]
    results["methodology_comparison"].append(
        eval_group("★ M3 (Hybrid Optimal Tier S): a1e6ca7d PIT + MCap + G2/G4 + IS Align", hybrid_optimal_s)
    )

    # Method 5: Current v1.1.0 Tier S Core (40 coins)
    results["methodology_comparison"].append(
        eval_group("M4 (Hiện tại v1.1.0 Tier S Core): 40 Mã Chủ Lực", [p for p in profs if p["universe_tier"] == "TIER_S_CORE"])
    )

    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved full study to: {OUT_JSON}")


if __name__ == "__main__":
    main()
