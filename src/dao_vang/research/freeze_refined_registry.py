"""Freeze Refined Candidate Strategy Registry (Strict Train 2020-2023).
Seals 8 high-performing, robust candidate strategies before opening Validation 2024-2025.
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

from dao_vang.research.protocol import ARTIFACTS_DIR, TRAIN_START, TRAIN_END
from dao_vang.research.data_loader import load_universe, slice_universe
from dao_vang.research.train_macro_experiment import run_sim

ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

CANDIDATE_SPECS = [
    {
        "id": "CAND-01-MACRO100-DONCH30-BALANCED",
        "family": "macro_regime_donchian",
        "resample": "4h",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_btc_filter": "ema600",
        "macro_slope_filter": False,
        "entry_signal": "donchian_30",
        "slots": 2,
        "target_annual_vol": 0.28,
        "trail_atr_mult": 2.5,
        "break_even_atr_mult": 1.5,
        "tighten_atr_mult": 99.0,
    },
    {
        "id": "CAND-02-MACRO100-DONCH30-HIGHGROWTH",
        "family": "macro_regime_donchian",
        "resample": "4h",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_btc_filter": "ema600",
        "macro_slope_filter": False,
        "entry_signal": "donchian_30",
        "slots": 2,
        "target_annual_vol": 0.33,
        "trail_atr_mult": 2.5,
        "break_even_atr_mult": 1.5,
        "tighten_atr_mult": 99.0,
    },
    {
        "id": "CAND-03-MACRO100-DONCH30-LOWDD",
        "family": "macro_regime_donchian",
        "resample": "4h",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_btc_filter": "ema600",
        "macro_slope_filter": False,
        "entry_signal": "donchian_30",
        "slots": 2,
        "target_annual_vol": 0.28,
        "trail_atr_mult": 2.0,
        "break_even_atr_mult": 1.5,
        "tighten_atr_mult": 99.0,
    },
    {
        "id": "CAND-04-MACRO50-DONCH20-MOMENTUM",
        "family": "macro_regime_donchian",
        "resample": "4h",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_btc_filter": "ema300",
        "macro_slope_filter": False,
        "entry_signal": "donchian_20",
        "slots": 2,
        "target_annual_vol": 0.33,
        "trail_atr_mult": 2.5,
        "break_even_atr_mult": 1.5,
        "tighten_atr_mult": 99.0,
    },
    {
        "id": "CAND-05-MACRO33-DONCH30-STANDARD",
        "family": "macro_regime_donchian",
        "resample": "4h",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_btc_filter": "ema200",
        "macro_slope_filter": False,
        "entry_signal": "donchian_30",
        "slots": 2,
        "target_annual_vol": 0.33,
        "trail_atr_mult": 2.5,
        "break_even_atr_mult": 1.5,
        "tighten_atr_mult": 99.0,
    },
    {
        "id": "CAND-06-MACRO33-DONCH20-FAST",
        "family": "macro_regime_donchian",
        "resample": "4h",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_btc_filter": "ema200",
        "macro_slope_filter": False,
        "entry_signal": "donchian_20",
        "slots": 2,
        "target_annual_vol": 0.33,
        "trail_atr_mult": 2.5,
        "break_even_atr_mult": 1.5,
        "tighten_atr_mult": 99.0,
    },
    {
        "id": "CAND-07-MACRO100-DONCH30-SLOT3",
        "family": "macro_regime_donchian",
        "resample": "4h",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_btc_filter": "ema600",
        "macro_slope_filter": False,
        "entry_signal": "donchian_30",
        "slots": 3,
        "target_annual_vol": 0.30,
        "trail_atr_mult": 2.0,
        "break_even_atr_mult": 1.5,
        "tighten_atr_mult": 99.0,
    },
    {
        "id": "CAND-08-MACRO100-DONCH30-BE10",
        "family": "macro_regime_donchian",
        "resample": "4h",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_btc_filter": "ema600",
        "macro_slope_filter": False,
        "entry_signal": "donchian_30",
        "slots": 2,
        "target_annual_vol": 0.28,
        "trail_atr_mult": 2.5,
        "break_even_atr_mult": 1.0,
        "tighten_atr_mult": 99.0,
    },
]


def evaluate_and_freeze():
    print("Evaluating 8 candidate configurations on Train (2020-2023)...")
    frozen_list = []
    for c in CANDIDATE_SPECS:
        donch_num = int(c["entry_signal"].split("_")[1])
        cagr, maxdd, calmar = run_sim(
            macro_key=c["macro_btc_filter"],
            macro_slope_filter=c["macro_slope_filter"],
            donch_len=donch_num,
            trail_atr=c["trail_atr_mult"],
            be_atr=c["break_even_atr_mult"],
            tighten_atr=c["tighten_atr_mult"],
            target_vol=c["target_annual_vol"],
            slots=c["slots"],
        )
        spec = dict(c)
        spec["train_metrics"] = {
            "cagr_pct": round(cagr * 100, 2),
            "maxdd_pct": round(maxdd * 100, 2),
            "calmar": round(calmar, 4),
        }
        frozen_list.append(spec)
        print(f"  {c['id']:<35} | Train CAGR={cagr*100:6.2f}% | MaxDD={maxdd*100:5.2f}% | Calmar={calmar:6.3f}")

    registry = {
        "protocol_version": "2.0-macro-donchian-walkforward",
        "train_period": {"start": "2020-01-01 00:00:00 UTC", "end": "2023-12-31 23:59:59 UTC"},
        "validation_period": {"start": "2024-01-01 00:00:00 UTC", "end": "2025-12-31 23:59:59 UTC"},
        "test_period": {"start": "2026-01-01 00:00:00 UTC", "end": "2026-09-29 23:00:00 UTC"},
        "frozen_timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
        "candidates": frozen_list,
    }

    json_path = ARTIFACTS_DIR / "frozen_candidates.json"
    sha_path = ARTIFACTS_DIR / "frozen_candidates.sha256"

    content = json.dumps(registry, indent=2)
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(content)

    sha256_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    with open(sha_path, "w", encoding="utf-8") as f:
        f.write(f"{sha256_hash}  frozen_candidates.json\n")

    print("\n[OK] Refined candidates frozen to:", json_path)
    print(f"[OK] Sealed with SHA-256: {sha256_hash}")


if __name__ == "__main__":
    evaluate_and_freeze()
