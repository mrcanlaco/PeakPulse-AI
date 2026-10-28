"""Robustness diagnostics for the LOCKED candidates (no new selection):
execution delay (+1 / +3 bars), cost stress, Sharpe, month stats, pairwise correlation."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .data import OUT_DIR
from .engine import metrics, simulate, split_range
from .lab import Lab
from .registry import load_lock


def delayed(W: np.ndarray, reb: np.ndarray, bars: int):
    W2 = np.zeros_like(W)
    r2 = np.zeros_like(reb)
    W2[bars:] = W[:-bars]
    r2[bars:] = reb[:-bars]
    return W2, r2


def main() -> None:
    lock = load_lock()
    lab = Lab()
    rows = []
    daily = {}
    for s in lock["specs"]:
        spec = {"family": s["family"], "params": s["params"]}
        W, reb = lab.weights(spec)
        row = {"id": s["id"]}
        for split in ("val", "test"):
            k0, k1 = split_range(lab.panel, split)
            for bars in (0, 1, 3):
                Wd, rd = (W, reb) if bars == 0 else delayed(W, reb, bars)
                res = simulate(lab.panel, Wd, rd, k0, k1, lab.cost)
                m = metrics(res)
                row[f"{split}_delay{bars}_calmar"] = m["calmar"]
                row[f"{split}_delay{bars}_ret"] = m["total_return"]
                if bars == 0:
                    row[f"{split}_sharpe"] = m["sharpe"]
                    row[f"{split}_monthwin"] = m["month_win"]
                    row[f"{split}_turn"] = m["turnover_per_year"]
                    row[f"{split}_gross"] = m["gross_avg"]
                    daily[(s["id"], split)] = lab.daily(spec, split)
        rows.append(row)
    df = pd.DataFrame(rows).set_index("id")
    df.to_csv(OUT_DIR / "robustness.csv")
    pd.set_option("display.width", 250)
    print(df.round(2).to_string())
    print("\nmedian test calmar by delay:", {b: round(float(df[f"test_delay{b}_calmar"].median()), 2) for b in (0, 1, 3)})
    print("pass(>1) test by delay:", {b: int((df[f"test_delay{b}_calmar"] > 1).sum()) for b in (0, 1, 3)})
    tc = pd.DataFrame({i: daily[(i, "test")] for i in df.index}).corr()
    off = tc.values[np.triu_indices(len(tc), 1)]
    print("test daily corr: median %.2f, min %.2f, max %.2f" % (np.median(off), off.min(), off.max()))
    json.dump({"test_corr_median": float(np.median(off))}, open(OUT_DIR / "robustness_meta.json", "w"))


if __name__ == "__main__":
    main()
