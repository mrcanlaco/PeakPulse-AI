"""Final Evaluation Runner: Test 2026 and Full Period (2020-2026).
Strict Protocol: Only evaluates candidates locked prior to opening Test data.
Checks acceptance gate: Full Period CAGR / MaxDD > 3.0 (Ứng viên /goal).
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


def verify_candidate_lock() -> dict:
    lock_file = ARTIFACTS_DIR / "candidate_lock.json"
    sha_file = ARTIFACTS_DIR / "candidate_lock.sha256"

    with open(lock_file, "r", encoding="utf-8") as f:
        content = f.read()

    actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    with open(sha_file, "r", encoding="utf-8") as f:
        expected_hash = f.read().split()[0].strip()

    if actual_hash != expected_hash:
        raise ValueError(f"Lock integrity check failed! Expected {expected_hash}, got {actual_hash}")

    print(f"[OK] Candidate Lock verified: {actual_hash}")
    return json.loads(content)


def evaluate_yearly(nav_series: pd.Series) -> list[dict]:
    """Calculate year-by-year performance metrics."""
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


def run_full_evaluation():
    lock_data = verify_candidate_lock()
    champion_info = lock_data["champion_candidate"]
    champion_id = champion_info["id"]

    frozen_file = ARTIFACTS_DIR / "frozen_candidates.json"
    with open(frozen_file, "r", encoding="utf-8") as f:
        frozen_data = json.load(f)

    print("\nLoading full multi-year market data (2020-2026)...")
    universe = load_universe()
    full_data = slice_universe(universe, FULL_START, FULL_END)

    timeline, features = prepare_multiasset_features(full_data, resample_freq="4h")
    print(f"Full timeline: {len(timeline)} bars ({timeline[0]} to {timeline[-1]})\n")

    print("=" * 90)
    print("   FULL-CYCLE WALK-FORWARD EVALUATION REPORT (2020 - 2026)")
    print("=" * 90)

    all_evaluations = []

    for c in frozen_data["candidates"]:
        is_locked_champion = bool(c["id"] == champion_id)

        nav_full, stats_full = simulate_candidate(
            timeline=timeline,
            features=features,
            candidate_spec=c,
        )

        nav_train = nav_full.loc[TRAIN_START:TRAIN_END]
        nav_val = nav_full.loc[VAL_START:VAL_END]
        nav_test = nav_full.loc[TEST_START:TEST_END]

        _, tr_cagr, tr_dd, tr_cal = compute_metrics(nav_train)
        _, val_cagr, val_dd, val_cal = compute_metrics(nav_val)
        _, test_cagr, test_dd, test_cal = compute_metrics(nav_test)
        tot_ret, full_cagr, full_dd, full_cal = compute_metrics(nav_full)

        daily_full = nav_full.resample("1D").last().dropna()
        rets_full = daily_full.pct_change().dropna().to_numpy()
        full_sharpe = float(np.mean(rets_full) / np.std(rets_full, ddof=1) * math.sqrt(365.25)) if len(rets_full) > 5 and np.std(rets_full) > 1e-8 else 0.0

        yearly = evaluate_yearly(nav_full)
        is_goal_qualified = bool(full_cal >= CALMAR_GOAL_THRESHOLD)

        eval_record = {
            "id": c["id"],
            "is_locked_champion": is_locked_champion,
            "train": {
                "cagr_pct": round(tr_cagr * 100, 2),
                "maxdd_pct": round(tr_dd * 100, 2),
                "calmar": round(tr_cal, 3),
            },
            "validation": {
                "cagr_pct": round(val_cagr * 100, 2),
                "maxdd_pct": round(val_dd * 100, 2),
                "calmar": round(val_cal, 3),
            },
            "test_2026": {
                "cagr_pct": round(test_cagr * 100, 2),
                "maxdd_pct": round(test_dd * 100, 2),
                "calmar": round(test_cal, 3),
            },
            "full_period_2020_2026": {
                "total_return_pct": round(tot_ret * 100, 2),
                "cagr_pct": round(full_cagr * 100, 2),
                "maxdd_pct": round(full_dd * 100, 2),
                "calmar": round(full_cal, 3),
                "sharpe": round(full_sharpe, 3),
                "win_rate_pct": stats_full["win_rate_pct"],
                "profit_factor": stats_full["profit_factor"],
                "total_trades": stats_full["total_trades"],
                "total_fees_usdt": stats_full["total_fees_usdt"],
                "total_funding_usdt": stats_full["total_funding_usdt"],
                "final_equity_usdt": stats_full["final_equity_usdt"],
            },
            "yearly_breakdown": yearly,
            "is_goal_qualified": is_goal_qualified,
            "spec": c,
        }
        all_evaluations.append(eval_record)

        champ_tag = " [LOCKED CHAMPION]" if is_locked_champion else ""
        qual_tag = " -> UNG VIEN /GOAL QUALIFIED" if is_goal_qualified else ""
        print(f"\n{c['id']}{champ_tag}:")
        print(f"  * Train (2020-2023): CAGR = {tr_cagr*100:6.2f}% | MaxDD = {tr_dd*100:5.2f}% | Calmar = {tr_cal:6.3f}")
        print(f"  * Val   (2024-2025): CAGR = {val_cagr*100:6.2f}% | MaxDD = {val_dd*100:5.2f}% | Calmar = {val_cal:6.3f}")
        print(f"  * Test  (2026 OOS) : CAGR = {test_cagr*100:6.2f}% | MaxDD = {test_dd*100:5.2f}% | Calmar = {test_cal:6.3f}")
        print(f"  * FULL  (2020-2026): CAGR = {full_cagr*100:6.2f}% | MaxDD = {full_dd*100:5.2f}% | CALMAR = {full_cal:6.3f}{qual_tag}")

        if is_locked_champion:
            eq_df = pd.DataFrame({"nav": nav_full})
            eq_df.to_parquet(ARTIFACTS_DIR / "champion_equity_curve.parquet")

    out_json = ARTIFACTS_DIR / "full_evaluation_results.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({
            "evaluation_timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
            "goal_calmar_threshold": CALMAR_GOAL_THRESHOLD,
            "evaluations": all_evaluations,
        }, f, indent=2)

    print("\n" + "=" * 90)
    print(f"[OK] Full evaluation saved to: {out_json}")
    print("=" * 90)


if __name__ == "__main__":
    run_full_evaluation()
