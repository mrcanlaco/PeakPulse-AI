"""Candidate Lock before opening Test 2026 slice.
Locks the champion candidate selected strictly from the frozen registry via Validation 2024-2025.
"""

from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))

from dao_vang.research.protocol import ARTIFACTS_DIR


def lock_champion():
    val_file = ARTIFACTS_DIR / "validation_results.json"
    with open(val_file, "r", encoding="utf-8") as f:
        val_data = json.load(f)

    ranked = val_data["ranked_candidates"]
    champion = ranked[0]
    runner_up = ranked[1]

    lock_payload = {
        "lock_version": "1.0-strict-candidate-lock",
        "lock_timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
        "selection_criteria": "Highest Calmar Ratio on Validation (2024-2025) strictly from frozen candidates",
        "champion_candidate": {
            "id": champion["id"],
            "family": champion["family"],
            "train_calmar": champion["train_calmar"],
            "val_calmar": champion["val_calmar"],
            "val_cagr_pct": champion["val_cagr_pct"],
            "val_maxdd_pct": champion["val_maxdd_pct"],
            "spec": champion["spec"],
        },
        "runner_up_candidate": {
            "id": runner_up["id"],
            "family": runner_up["family"],
            "val_calmar": runner_up["val_calmar"],
            "val_cagr_pct": runner_up["val_cagr_pct"],
            "val_maxdd_pct": runner_up["val_maxdd_pct"],
            "spec": runner_up["spec"],
        },
    }

    lock_file = ARTIFACTS_DIR / "candidate_lock.json"
    sha_file = ARTIFACTS_DIR / "candidate_lock.sha256"

    content = json.dumps(lock_payload, indent=2)
    with open(lock_file, "w", encoding="utf-8") as f:
        f.write(content)

    sha256_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    with open(sha_file, "w", encoding="utf-8") as f:
        f.write(f"{sha256_hash}  candidate_lock.json\n")

    print(f"[OK] Locked Champion Strategy: {champion['id']}")
    print(f"[OK] Saved to: {lock_file}")
    print(f"[OK] Sealed with SHA-256: {sha256_hash}")


if __name__ == "__main__":
    lock_champion()
