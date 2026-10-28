"""Complete Strict Walk-Forward Pipeline (Train 2020-2023 -> Val 2024-2025 -> Test 2026).
Enforces:
1. Freeze Specs on Train with SHA-256
2. Validation on frozen candidates only
3. Lock Champion before opening Test
4. Evaluate Test 2026 & Full Period 2020-2026
5. Goal check: Full CAGR / MaxDD > 3.0
"""

from __future__ import annotations
import hashlib
import json
import math
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))

from dao_vang.research.protocol import (
    ARTIFACTS_DIR,
    TRAIN_START,
    TRAIN_END,
    VAL_START,
    VAL_END,
    TEST_START,
    TEST_END,
    FULL_START,
    FULL_END,
    CALMAR_GOAL_THRESHOLD,
)
from dao_vang.research.data_loader import load_universe, slice_universe
from dao_vang.research.walkforward_engine import (
    prepare_multiasset_features,
    simulate_candidate,
    compute_metrics,
)

ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

# Candidate specs developed strictly on Train (2020-2023)
CANDIDATE_SPECS = [
    {
        "id": "CAND-01-EMA450-TR25-BE10-TV36",
        "family": "macro_regime_donchian",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_btc_filter": "ema450",
        "entry_signal": "donchian_30",
        "slots": 2,
        "target_annual_vol": 0.36,
        "trail_atr_mult": 2.5,
        "break_even_atr_mult": 1.0,
        "tighten_atr_mult": 99.0,
    },
    {
        "id": "CAND-02-EMA450-TR20-BE10-TV36",
        "family": "macro_regime_donchian",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_btc_filter": "ema450",
        "entry_signal": "donchian_30",
        "slots": 2,
        "target_annual_vol": 0.36,
        "trail_atr_mult": 2.0,
        "break_even_atr_mult": 1.0,
        "tighten_atr_mult": 99.0,
    },
    {
        "id": "CAND-03-EMA600-TR20-BE10-TV32",
        "family": "macro_regime_donchian",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_btc_filter": "ema600",
        "entry_signal": "donchian_30",
        "slots": 2,
        "target_annual_vol": 0.32,
        "trail_atr_mult": 2.0,
        "break_even_atr_mult": 1.0,
        "tighten_atr_mult": 99.0,
    },
    {
        "id": "CAND-04-EMA450-TR25-BE15-TV36",
        "family": "macro_regime_donchian",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_btc_filter": "ema450",
        "entry_signal": "donchian_30",
        "slots": 2,
        "target_annual_vol": 0.36,
        "trail_atr_mult": 2.5,
        "break_even_atr_mult": 1.5,
        "tighten_atr_mult": 99.0,
    },
    {
        "id": "CAND-05-EMA450-TR25-BE10-TV32",
        "family": "macro_regime_donchian",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_btc_filter": "ema450",
        "entry_signal": "donchian_30",
        "slots": 2,
        "target_annual_vol": 0.32,
        "trail_atr_mult": 2.5,
        "break_even_atr_mult": 1.0,
        "tighten_atr_mult": 99.0,
    },
    {
        "id": "CAND-06-EMA600-TR25-BE10-TV32",
        "family": "macro_regime_donchian",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_btc_filter": "ema600",
        "entry_signal": "donchian_30",
        "slots": 2,
        "target_annual_vol": 0.32,
        "trail_atr_mult": 2.5,
        "break_even_atr_mult": 1.0,
        "tighten_atr_mult": 99.0,
    },
    {
        "id": "CAND-07-EMA600-TR20-BE10-TV36",
        "family": "macro_regime_donchian",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_btc_filter": "ema600",
        "entry_signal": "donchian_30",
        "slots": 2,
        "target_annual_vol": 0.36,
        "trail_atr_mult": 2.0,
        "break_even_atr_mult": 1.0,
        "tighten_atr_mult": 99.0,
    },
    {
        "id": "CAND-08-EMA450-TR20-BE10-TV32",
        "family": "macro_regime_donchian",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_btc_filter": "ema450",
        "entry_signal": "donchian_30",
        "slots": 2,
        "target_annual_vol": 0.32,
        "trail_atr_mult": 2.0,
        "break_even_atr_mult": 1.0,
        "tighten_atr_mult": 99.0,
    },
]


def evaluate_yearly(nav_series: pd.Series) -> list[dict]:
    years = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
    records = []
    for y in years:
        sub = nav_series.loc[f"{y}-01-01":f"{y}-12-31"]
        if len(sub) < 30:
            continue
        tot, cagr, maxdd, calmar = compute_metrics(sub)
        daily = sub.resample("1D").last().dropna()
        rets = daily.pct_change().dropna().to_numpy()
        sharpe = float(np.mean(rets) / np.std(rets, ddof=1) * math.sqrt(365.25)) if len(rets) > 5 and np.std(rets) > 1e-8 else 0.0

        records.append({
            "year": y,
            "total_return_pct": round(tot * 100, 2),
            "cagr_pct": round(cagr * 100, 2),
            "maxdd_pct": round(maxdd * 100, 2),
            "calmar": round(calmar, 3),
            "sharpe": round(sharpe, 3),
        })
    return records


def run_pipeline():
    print("=" * 80)
    print("   STRICT WALK-FORWARD RESEARCH PIPELINE (2020 - 2026)")
    print("=" * 80)

    # 1. LOAD DATA
    universe = load_universe()

    # 2. PHASE 1: EVALUATE & FREEZE SPECS ON TRAIN (2020-2023)
    print("\n[PHASE 1] Evaluating & Freezing Candidates on Train (2020-2023)...")
    train_data = slice_universe(universe, TRAIN_START, TRAIN_END)
    train_timeline, train_features = prepare_multiasset_features(train_data, resample_freq="4h")

    # Ensure ema450 exists
    for s in universe.keys():
        c = train_features[s]["close"]
        train_features[s]["ema450"] = pd.Series(c).shift(1).ewm(span=450).mean().to_numpy()

    frozen_candidates = []
    for c in CANDIDATE_SPECS:
        nav_tr, stats_tr = simulate_candidate(train_timeline, train_features, c)
        c_copy = dict(c)
        c_copy["train_metrics"] = {
            "cagr_pct": stats_tr["cagr_pct"],
            "maxdd_pct": stats_tr["maxdd_pct"],
            "calmar": stats_tr["calmar"],
        }
        frozen_candidates.append(c_copy)
        print(f"  {c['id']:<35} | Train CAGR={stats_tr['cagr_pct']:6.2f}% | MaxDD={stats_tr['maxdd_pct']:5.2f}% | Calmar={stats_tr['calmar']:6.3f}")

    registry = {
        "protocol_version": "3.0-strict-walkforward",
        "train_period": {"start": str(TRAIN_START), "end": str(TRAIN_END)},
        "validation_period": {"start": str(VAL_START), "end": str(VAL_END)},
        "test_period": {"start": str(TEST_START), "end": str(TEST_END)},
        "frozen_timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
        "candidates": frozen_candidates,
    }

    json_path = ARTIFACTS_DIR / "frozen_candidates.json"
    sha_path = ARTIFACTS_DIR / "frozen_candidates.sha256"
    content = json.dumps(registry, indent=2)
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(content)
    sha256_frozen = hashlib.sha256(content.encode("utf-8")).hexdigest()
    with open(sha_path, "w", encoding="utf-8") as f:
        f.write(f"{sha256_frozen}  frozen_candidates.json\n")
    print(f"[OK] Frozen {len(frozen_candidates)} candidates sealed with SHA-256: {sha256_frozen}")

    # 3. PHASE 2: VALIDATION ON FROZEN CANDIDATES (2024-2025)
    print("\n[PHASE 2] Running Validation on Frozen Candidates (2024-2025)...")
    val_data = slice_universe(universe, VAL_START, VAL_END)
    val_timeline, val_features = prepare_multiasset_features(val_data, resample_freq="4h")
    for s in universe.keys():
        c = val_features[s]["close"]
        val_features[s]["ema450"] = pd.Series(c).shift(1).ewm(span=450).mean().to_numpy()

    val_results = []
    for c in frozen_candidates:
        nav_val, stats_val = simulate_candidate(val_timeline, val_features, c)
        daily_val = nav_val.resample("1D").last().dropna()
        rets_val = daily_val.pct_change().dropna().to_numpy()
        sharpe_val = float(np.mean(rets_val) / np.std(rets_val, ddof=1) * math.sqrt(365.25)) if len(rets_val) > 5 and np.std(rets_val) > 1e-8 else 0.0

        res_item = {
            "id": c["id"],
            "train_calmar": c["train_metrics"]["calmar"],
            "val_total_return_pct": stats_val["total_return_pct"],
            "val_cagr_pct": stats_val["cagr_pct"],
            "val_maxdd_pct": stats_val["maxdd_pct"],
            "val_calmar": stats_val["calmar"],
            "val_sharpe": round(sharpe_val, 3),
            "spec": c,
        }
        val_results.append(res_item)
        print(f"  {c['id']:<35} | Val CAGR={stats_val['cagr_pct']:6.2f}% | MaxDD={stats_val['maxdd_pct']:5.2f}% | Calmar={stats_val['calmar']:6.3f} | Sharpe={sharpe_val:5.2f}")

    val_results.sort(key=lambda x: x["val_calmar"], reverse=True)
    champion = val_results[0]
    runner_up = val_results[1]
    print(f"\n[WINNER] Selected Champion on Validation: {champion['id']}")
    print(f"  Val Calmar: {champion['val_calmar']:.3f} | Val CAGR: {champion['val_cagr_pct']:.2f}% | Val MaxDD: {champion['val_maxdd_pct']:.2f}%")

    val_out = ARTIFACTS_DIR / "validation_results.json"
    with open(val_out, "w", encoding="utf-8") as f:
        json.dump({"timestamp": pd.Timestamp.now(tz="UTC").isoformat(), "ranked": val_results, "champion": champion["id"]}, f, indent=2)

    # 4. PHASE 3: CANDIDATE LOCK BEFORE TEST
    print("\n[PHASE 3] Locking Champion Candidate before opening Test 2026...")
    lock_payload = {
        "lock_version": "3.0-candidate-lock",
        "lock_timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
        "champion_candidate": champion,
        "runner_up_candidate": runner_up,
    }
    lock_file = ARTIFACTS_DIR / "candidate_lock.json"
    lock_sha = ARTIFACTS_DIR / "candidate_lock.sha256"
    content_lock = json.dumps(lock_payload, indent=2)
    with open(lock_file, "w", encoding="utf-8") as f:
        f.write(content_lock)
    sha256_lock = hashlib.sha256(content_lock.encode("utf-8")).hexdigest()
    with open(lock_sha, "w", encoding="utf-8") as f:
        f.write(f"{sha256_lock}  candidate_lock.json\n")
    print(f"[OK] Candidate Lock sealed with SHA-256: {sha256_lock}")

    # 5. PHASE 4: OPEN TEST 2026 & FULL CYCLE (2020-2026)
    print("\n[PHASE 4] Opening Test 2026 & Running Full-Cycle Evaluation (2020-2026)...")
    full_data = slice_universe(universe, FULL_START, FULL_END)
    full_timeline, full_features = prepare_multiasset_features(full_data, resample_freq="4h")
    for s in universe.keys():
        c = full_features[s]["close"]
        full_features[s]["ema450"] = pd.Series(c).shift(1).ewm(span=450).mean().to_numpy()

    all_evaluations = []
    print("\n" + "=" * 90)
    print("   FINAL EVALUATION RESULTS ACROSS TRAIN, VAL, TEST 2026 & FULL PERIOD")
    print("=" * 90)

    for c in frozen_candidates:
        is_champ = bool(c["id"] == champion["id"])
        nav_full, stats_full = simulate_candidate(full_timeline, full_features, c)

        nav_tr = nav_full.loc[TRAIN_START:TRAIN_END]
        nav_v = nav_full.loc[VAL_START:VAL_END]
        nav_te = nav_full.loc[TEST_START:TEST_END]

        _, tr_cagr, tr_dd, tr_cal = compute_metrics(nav_tr)
        _, val_cagr, val_dd, val_cal = compute_metrics(nav_v)
        _, te_cagr, te_dd, te_cal = compute_metrics(nav_te)
        tot_ret, f_cagr, f_dd, f_cal = compute_metrics(nav_full)

        daily_f = nav_full.resample("1D").last().dropna()
        rets_f = daily_f.pct_change().dropna().to_numpy()
        sharpe_f = float(np.mean(rets_f) / np.std(rets_f, ddof=1) * math.sqrt(365.25)) if len(rets_f) > 5 and np.std(rets_f) > 1e-8 else 0.0

        yearly = evaluate_yearly(nav_full)
        is_goal = bool(f_cal >= CALMAR_GOAL_THRESHOLD)

        rec = {
            "id": c["id"],
            "is_locked_champion": is_champ,
            "train": {"cagr_pct": round(tr_cagr * 100, 2), "maxdd_pct": round(tr_dd * 100, 2), "calmar": round(tr_cal, 3)},
            "validation": {"cagr_pct": round(val_cagr * 100, 2), "maxdd_pct": round(val_dd * 100, 2), "calmar": round(val_cal, 3)},
            "test_2026": {"cagr_pct": round(te_cagr * 100, 2), "maxdd_pct": round(te_dd * 100, 2), "calmar": round(te_cal, 3)},
            "full_period_2020_2026": {
                "total_return_pct": round(tot_ret * 100, 2),
                "cagr_pct": round(f_cagr * 100, 2),
                "maxdd_pct": round(f_dd * 100, 2),
                "calmar": round(f_cal, 3),
                "sharpe": round(sharpe_f, 3),
                "win_rate_pct": stats_full["win_rate_pct"],
                "profit_factor": stats_full["profit_factor"],
                "total_trades": stats_full["total_trades"],
                "total_fees_usdt": stats_full["total_fees_usdt"],
                "total_funding_usdt": stats_full["total_funding_usdt"],
                "final_equity_usdt": stats_full["final_equity_usdt"],
            },
            "yearly_breakdown": yearly,
            "is_goal_qualified": is_goal,
            "spec": c,
        }
        all_evaluations.append(rec)

        champ_tag = " [LOCKED CHAMPION]" if is_champ else ""
        qual_tag = " -> UNG VIEN /GOAL QUALIFIED" if is_goal else ""
        print(f"\n{c['id']}{champ_tag}:")
        print(f"  * Train (2020-2023): CAGR = {tr_cagr*100:6.2f}% | MaxDD = {tr_dd*100:5.2f}% | Calmar = {tr_cal:6.3f}")
        print(f"  * Val   (2024-2025): CAGR = {val_cagr*100:6.2f}% | MaxDD = {val_dd*100:5.2f}% | Calmar = {val_cal:6.3f}")
        print(f"  * Test  (2026 OOS) : CAGR = {te_cagr*100:6.2f}% | MaxDD = {te_dd*100:5.2f}% | Calmar = {te_cal:6.3f}")
        print(f"  * FULL  (2020-2026): CAGR = {f_cagr*100:6.2f}% | MaxDD = {f_dd*100:5.2f}% | CALMAR = {f_cal:6.3f}{qual_tag}")

        if is_champ:
            eq_df = pd.DataFrame({"nav": nav_full})
            eq_df.to_parquet(ARTIFACTS_DIR / "champion_equity_curve.parquet")

    full_eval_file = ARTIFACTS_DIR / "full_evaluation_results.json"
    with open(full_eval_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
            "goal_threshold": CALMAR_GOAL_THRESHOLD,
            "evaluations": all_evaluations
        }, f, indent=2)

    print("\n" + "=" * 90)
    print(f"[OK] Full evaluation saved to: {full_eval_file}")
    print("=" * 90)


if __name__ == "__main__":
    run_pipeline()
