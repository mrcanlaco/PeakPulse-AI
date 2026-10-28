"""Test Staged Profit Trailing on Train (2020-2023) using exact walkforward engine.
Strictly Train-only optimization.
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

print("Exploring Staged Trailing Stop & Profit Protection on Train (2020-2023)...")

results = []
for macro_k in ["ema600", "ema450"]:
    for donch in ["donchian_30", "donchian_20"]:
        for trail in [2.0, 2.5]:
            for be in [1.0, 1.5]:
                for tighten_trigger in [2.5, 3.0, 3.5, 99.0]:
                    for tv in [0.28, 0.32, 0.36]:
                        for slots in [2, 3]:
                            spec = {
                                "id": f"TEST_{macro_k}_{donch}_tr{trail}_be{be}_tg{tighten_trigger}_tv{tv}_s{slots}",
                                "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
                                "macro_btc_filter": macro_k,
                                "entry_signal": donch,
                                "trail_atr_mult": trail,
                                "break_even_atr_mult": be,
                                "tighten_atr_mult": tighten_trigger,
                                "target_annual_vol": tv,
                                "slots": slots,
                            }
                            # Need to ensure ema450 is precalculated if selected
                            if macro_k not in features["BTCUSDT"]:
                                for s in spec["universe"]:
                                    c = features[s]["close"]
                                    features[s]["ema450"] = pd.Series(c).shift(1).ewm(span=450).mean().to_numpy()

                            nav, stats = simulate_candidate(timeline, features, spec)
                            results.append({
                                "macro": macro_k,
                                "donch": donch,
                                "trail": trail,
                                "be": be,
                                "tighten": tighten_trigger,
                                "tv": tv,
                                "slots": slots,
                                "cagr": stats["cagr_pct"],
                                "maxdd": stats["maxdd_pct"],
                                "calmar": stats["calmar"],
                                "trades": stats["total_trades"],
                                "wr": stats["win_rate_pct"],
                                "pf": stats["profit_factor"],
                            })

df_res = pd.DataFrame(results).sort_values("calmar", ascending=False)
print("Top 20 Configurations on Train (2020-2023):")
print(df_res.head(20).to_string(index=False))
