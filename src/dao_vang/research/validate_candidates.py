"""Validation Runner for Frozen Candidates (2024-01-01 to 2025-12-31).
Strict Protocol: Only evaluates candidates registered in frozen_candidates.json.
Verifies SHA-256 seal before reading. No parameter modifications allowed.
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

from dao_vang.research.protocol import ARTIFACTS_DIR, VAL_START, VAL_END
from dao_vang.research.data_loader import load_universe, slice_universe
from dao_vang.research.walkforward_engine import (
    prepare_multiasset_features,
    simulate_candidate,
    compute_metrics,
)


def verify_frozen_checksum() -> dict:
    json_path = ARTIFACTS_DIR / "frozen_candidates.json"
    sha_path = ARTIFACTS_DIR / "frozen_candidates.sha256"

    with open(json_path, "r", encoding="utf-8") as f:
        content = f.read()

    actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    with open(sha_path, "r", encoding="utf-8") as f:
        expected_hash = f.read().split()[0].strip()

    if actual_hash != expected_hash:
        raise ValueError(f"Integrity check failed! Expected {expected_hash}, got {actual_hash}")

    print(f"[OK] Checksum verified: {actual_hash}")
    return json.loads(content)


def run_validation():
    registry = verify_frozen_checksum()
    candidates = registry["candidates"]

    print(f"\nLoading market data for Validation ({VAL_START} to {VAL_END})...")
    universe = load_universe()
    val_data = slice_universe(universe, VAL_START, VAL_END)

    timeline, features = prepare_multiasset_features(val_data, resample_freq="4h")
    print(f"Validation timeline: {len(timeline)} bars ({timeline[0]} to {timeline[-1]})\n")

    val_results = []
    print("=" * 80)
    print("   VALIDATION RESULTS ON FROZEN CANDIDATES (2024-2025)")
    print("=" * 80)

    for c in candidates:
        nav, stats = simulate_candidate(
            timeline=timeline,
            features=features,
            candidate_spec=c,
        )

        daily_nav = nav.resample("1D").last().dropna()
        daily_ret = daily_nav.pct_change().dropna().to_numpy()
        sharpe = float((np.mean(daily_ret) / np.std(daily_ret, ddof=1) * math.sqrt(365.25))) if len(daily_ret) > 5 and np.std(daily_ret) > 1e-8 else 0.0

        res_item = {
            "id": c["id"],
            "family": c["family"],
            "train_calmar": c["train_metrics"]["calmar"],
            "val_total_return_pct": stats["total_return_pct"],
            "val_cagr_pct": stats["cagr_pct"],
            "val_maxdd_pct": stats["maxdd_pct"],
            "val_calmar": stats["calmar"],
            "val_sharpe": round(sharpe, 3),
            "win_rate_pct": stats["win_rate_pct"],
            "profit_factor": stats["profit_factor"],
            "total_trades": stats["total_trades"],
            "spec": c,
        }
        val_results.append(res_item)
        print(f"{c['id']:<38} | Val CAGR={stats['cagr_pct']:6.2f}% | MaxDD={stats['maxdd_pct']:5.2f}% | Calmar={stats['calmar']:6.3f} | Sharpe={sharpe:5.2f}")

    # Rank by validation Calmar
    val_results.sort(key=lambda x: x["val_calmar"], reverse=True)
    champion = val_results[0]
    runner_up = val_results[1]

    print("\n" + "=" * 80)
    print(f"   CHAMPION CANDIDATE SELECTED ON VALIDATION: {champion['id']}")
    print(f"   Val Calmar: {champion['val_calmar']:.3f} | Val CAGR: {champion['val_cagr_pct']:.2f}% | Val MaxDD: {champion['val_maxdd_pct']:.2f}% | Sharpe: {champion['val_sharpe']:.2f}")
    print(f"   RUNNER UP: {runner_up['id']}")
    print(f"   Val Calmar: {runner_up['val_calmar']:.3f} | Val CAGR: {runner_up['val_cagr_pct']:.2f}% | Val MaxDD: {runner_up['val_maxdd_pct']:.2f}%")
    print("=" * 80)

    out_file = ARTIFACTS_DIR / "validation_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "validation_timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
            "ranked_candidates": val_results,
            "champion_selected": champion["id"],
        }, f, indent=2)

    print(f"[OK] Saved validation results to: {out_file}")


if __name__ == "__main__":
    run_validation()
