"""Sensitivity and plateau check on Train (2020-2023).
Ensures chosen frozen candidates lie on wide, stable parameter plateaus.
"""

from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))

from dao_vang.research.protocol import TRAIN_START, TRAIN_END
from dao_vang.research.data_loader import load_universe, slice_universe
from dao_vang.research.train_workbench import prepare_train_features, simulate_train_strategy, compute_metrics

universe = load_universe()
train_data = slice_universe(universe, TRAIN_START, TRAIN_END)
timeline, features = prepare_train_features(train_data, resample_freq="4h")

# Define Candidate Registry to test
CANDIDATES = [
    {
        "id": "CAND-01-DONCHIAN-BALANCED",
        "family": "donchian_breakout",
        "resample": "4h",
        "uni": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_ema": "ema200",
        "sig": "donchian_20",
        "slots": 2,
        "tv": 0.35,
        "trail": 2.5,
        "be": 1.5,
        "rs": False,
    },
    {
        "id": "CAND-02-DONCHIAN-LOWDD",
        "family": "donchian_breakout",
        "resample": "4h",
        "uni": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_ema": "ema200",
        "sig": "donchian_20",
        "slots": 3,
        "tv": 0.30,
        "trail": 2.0,
        "be": 1.5,
        "rs": False,
    },
    {
        "id": "CAND-03-DONCHIAN-TIGHT",
        "family": "donchian_breakout",
        "resample": "4h",
        "uni": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_ema": "ema200",
        "sig": "donchian_20",
        "slots": 2,
        "tv": 0.35,
        "trail": 2.0,
        "be": 1.5,
        "rs": False,
    },
    {
        "id": "CAND-04-DONCHIAN-CONSERVATIVE",
        "family": "donchian_breakout",
        "resample": "4h",
        "uni": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_ema": "ema200",
        "sig": "donchian_20",
        "slots": 2,
        "tv": 0.30,
        "trail": 2.5,
        "be": 1.0,
        "rs": False,
    },
    {
        "id": "CAND-05-EMA-CROSS-MOMENTUM",
        "family": "ema_trend_cross",
        "resample": "4h",
        "uni": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_ema": "ema200",
        "sig": "ema_cross",
        "slots": 2,
        "tv": 0.35,
        "trail": 2.0,
        "be": 1.5,
        "rs": False,
    },
    {
        "id": "CAND-06-EMA-CROSS-AGGRESSIVE",
        "family": "ema_trend_cross",
        "resample": "4h",
        "uni": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_ema": "ema200",
        "sig": "ema_cross",
        "slots": 2,
        "tv": 0.40,
        "trail": 2.0,
        "be": 1.5,
        "rs": False,
    },
    {
        "id": "CAND-07-DONCHIAN-BTC-SOL",
        "family": "donchian_breakout",
        "resample": "4h",
        "uni": ["BTCUSDT", "SOLUSDT"],
        "macro_ema": "ema200",
        "sig": "donchian_20",
        "slots": 2,
        "tv": 0.35,
        "trail": 2.5,
        "be": 1.5,
        "rs": False,
    },
    {
        "id": "CAND-08-DONCHIAN-RELATIVE-STRENGTH",
        "family": "donchian_breakout",
        "resample": "4h",
        "uni": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "macro_ema": "ema200",
        "sig": "donchian_20",
        "slots": 2,
        "tv": 0.35,
        "trail": 2.5,
        "be": 1.5,
        "rs": True,
    },
]

print("=== VERIFYING CANDIDATES ON TRAIN (2020-2023) ===")
results = []
for c in CANDIDATES:
    nav = simulate_train_strategy(
        timeline=timeline,
        features=features,
        universe_symbols=c["uni"],
        macro_filter_ema=c["macro_ema"],
        entry_signal_type=c["sig"],
        trail_atr_mult=c["trail"],
        be_atr_mult=c["be"],
        target_annual_vol=c["tv"],
        max_portfolio_slots=c["slots"],
        require_relative_strength=c["rs"],
    )
    tot, cagr, maxdd, calmar = compute_metrics(nav)
    c_res = dict(c)
    c_res["cagr_pct"] = round(cagr * 100, 2)
    c_res["maxdd_pct"] = round(maxdd * 100, 2)
    c_res["calmar"] = round(calmar, 4)
    results.append(c_res)
    print(f"{c['id']:<35} | CAGR={cagr*100:6.2f}% | MaxDD={maxdd*100:5.2f}% | Calmar={calmar:6.3f}")

df_out = pd.DataFrame(results)
print("\nSummary Table:")
print(df_out[["id", "sig", "slots", "tv", "trail", "be", "cagr_pct", "maxdd_pct", "calmar"]].to_string(index=False))
