"""Freeze Candidate Strategies Registry before opening Validation slice.
Strict Protocol: Frozen specifications cannot be altered once sealed.
"""

from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))

from dao_vang.research.protocol import ARTIFACTS_DIR

ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

FROZEN_REGISTRY = {
    "protocol_version": "1.0-strict-walkforward",
    "train_period": {"start": "2020-01-01 00:00:00 UTC", "end": "2023-12-31 23:59:59 UTC"},
    "validation_period": {"start": "2024-01-01 00:00:00 UTC", "end": "2025-12-31 23:59:59 UTC"},
    "test_period": {"start": "2026-01-01 00:00:00 UTC", "end": "2026-09-29 23:00:00 UTC"},
    "frozen_timestamp": "2026-10-03T19:38:00Z",
    "candidates": [
        {
            "id": "CAND-01-DONCHIAN-BALANCED",
            "family": "donchian_breakout",
            "resample": "4h",
            "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
            "macro_btc_filter": "ema200",
            "entry_signal": "donchian_20",
            "slots": 2,
            "target_annual_vol": 0.35,
            "trail_atr_mult": 2.5,
            "break_even_atr_mult": 1.5,
            "require_relative_strength": False,
            "train_metrics": {
                "cagr_pct": 66.38,
                "maxdd_pct": 13.29,
                "calmar": 4.9963
            }
        },
        {
            "id": "CAND-02-DONCHIAN-LOWDD",
            "family": "donchian_breakout",
            "resample": "4h",
            "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
            "macro_btc_filter": "ema200",
            "entry_signal": "donchian_20",
            "slots": 3,
            "target_annual_vol": 0.30,
            "trail_atr_mult": 2.0,
            "break_even_atr_mult": 1.5,
            "require_relative_strength": False,
            "train_metrics": {
                "cagr_pct": 44.16,
                "maxdd_pct": 10.36,
                "calmar": 4.2638
            }
        },
        {
            "id": "CAND-03-DONCHIAN-TIGHT",
            "family": "donchian_breakout",
            "resample": "4h",
            "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
            "macro_btc_filter": "ema200",
            "entry_signal": "donchian_20",
            "slots": 2,
            "target_annual_vol": 0.35,
            "trail_atr_mult": 2.0,
            "break_even_atr_mult": 1.5,
            "require_relative_strength": False,
            "train_metrics": {
                "cagr_pct": 56.17,
                "maxdd_pct": 12.29,
                "calmar": 4.5724
            }
        },
        {
            "id": "CAND-04-DONCHIAN-CONSERVATIVE",
            "family": "donchian_breakout",
            "resample": "4h",
            "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
            "macro_btc_filter": "ema200",
            "entry_signal": "donchian_20",
            "slots": 2,
            "target_annual_vol": 0.30,
            "trail_atr_mult": 2.5,
            "break_even_atr_mult": 1.0,
            "require_relative_strength": False,
            "train_metrics": {
                "cagr_pct": 57.94,
                "maxdd_pct": 13.43,
                "calmar": 4.3159
            }
        },
        {
            "id": "CAND-05-EMA-CROSS-MOMENTUM",
            "family": "ema_trend_cross",
            "resample": "4h",
            "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
            "macro_btc_filter": "ema200",
            "entry_signal": "ema_cross",
            "slots": 2,
            "target_annual_vol": 0.35,
            "trail_atr_mult": 2.0,
            "break_even_atr_mult": 1.5,
            "require_relative_strength": False,
            "train_metrics": {
                "cagr_pct": 71.44,
                "maxdd_pct": 16.75,
                "calmar": 4.2642
            }
        },
        {
            "id": "CAND-06-EMA-CROSS-AGGRESSIVE",
            "family": "ema_trend_cross",
            "resample": "4h",
            "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
            "macro_btc_filter": "ema200",
            "entry_signal": "ema_cross",
            "slots": 2,
            "target_annual_vol": 0.40,
            "trail_atr_mult": 2.0,
            "break_even_atr_mult": 1.5,
            "require_relative_strength": False,
            "train_metrics": {
                "cagr_pct": 79.26,
                "maxdd_pct": 18.40,
                "calmar": 4.3072
            }
        },
        {
            "id": "CAND-07-DONCHIAN-BTC-SOL",
            "family": "donchian_breakout",
            "resample": "4h",
            "universe": ["BTCUSDT", "SOLUSDT"],
            "macro_btc_filter": "ema200",
            "entry_signal": "donchian_20",
            "slots": 2,
            "target_annual_vol": 0.35,
            "trail_atr_mult": 2.5,
            "break_even_atr_mult": 1.5,
            "require_relative_strength": False,
            "train_metrics": {
                "cagr_pct": 34.66,
                "maxdd_pct": 14.44,
                "calmar": 2.4007
            }
        },
        {
            "id": "CAND-08-DONCHIAN-RELATIVE-STRENGTH",
            "family": "donchian_breakout",
            "resample": "4h",
            "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
            "macro_btc_filter": "ema200",
            "entry_signal": "donchian_20",
            "slots": 2,
            "target_annual_vol": 0.35,
            "trail_atr_mult": 2.5,
            "break_even_atr_mult": 1.5,
            "require_relative_strength": True,
            "train_metrics": {
                "cagr_pct": 52.56,
                "maxdd_pct": 20.93,
                "calmar": 2.5117
            }
        }
    ]
}

def freeze():
    json_path = ARTIFACTS_DIR / "frozen_candidates.json"
    sha_path = ARTIFACTS_DIR / "frozen_candidates.sha256"

    content = json.dumps(FROZEN_REGISTRY, indent=2)
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(content)

    sha256_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    with open(sha_path, "w", encoding="utf-8") as f:
        f.write(f"{sha256_hash}  frozen_candidates.json\n")

    print(f"[OK] Frozen {len(FROZEN_REGISTRY['candidates'])} candidates to: {json_path}")
    print(f"[OK] Sealed with SHA-256: {sha256_hash}")

if __name__ == "__main__":
    freeze()
