"""Test Universe selection on Train (2020-2023).
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
from dao_vang.research.walkforward_engine import (
    prepare_multiasset_features,
    simulate_candidate,
)

universe = load_universe()
train_data = slice_universe(universe, TRAIN_START, TRAIN_END)
timeline, features = prepare_multiasset_features(train_data, resample_freq="4h")

# Ensure ema450 and ema500 exist
for s in universe.keys():
    c = features[s]["close"]
    features[s]["ema450"] = pd.Series(c).shift(1).ewm(span=450).mean().to_numpy()
    features[s]["ema500"] = pd.Series(c).shift(1).ewm(span=500).mean().to_numpy()

uni_options = {
    "btc_eth_sol_bnb": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
    "btc_sol_bnb": ["BTCUSDT", "SOLUSDT", "BNBUSDT"],
    "btc_eth_sol": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    "btc_sol": ["BTCUSDT", "SOLUSDT"],
}

print("Testing Universes on Train (2020-2023)...")
records = []
for u_name, u_syms in uni_options.items():
    for macro in ["ema450", "ema600"]:
        for trail in [2.0, 2.5]:
            for be in [1.0, 1.5]:
                for tv in [0.32, 0.36]:
                    spec = {
                        "id": f"{u_name}_{macro}_tr{trail}_be{be}_tv{tv}",
                        "universe": u_syms,
                        "macro_btc_filter": macro,
                        "entry_signal": "donchian_30",
                        "trail_atr_mult": trail,
                        "break_even_atr_mult": be,
                        "tighten_atr_mult": 99.0,
                        "target_annual_vol": tv,
                        "slots": 2,
                    }
                    nav, stats = simulate_candidate(timeline, features, spec)
                    records.append({
                        "uni": u_name,
                        "macro": macro,
                        "trail": trail,
                        "be": be,
                        "tv": tv,
                        "cagr": stats["cagr_pct"],
                        "maxdd": stats["maxdd_pct"],
                        "calmar": stats["calmar"],
                        "wr": stats["win_rate_pct"],
                        "pf": stats["profit_factor"],
                    })

df_res = pd.DataFrame(records).sort_values("calmar", ascending=False)
print(df_res.head(15).to_string(index=False))
