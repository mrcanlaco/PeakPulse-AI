"""Open TEST 2026 for the locked candidates and build the final ranked table."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .data import OUT_DIR
from .engine import split_range
from .lab import Lab
from .registry import load_lock, record_access


def main() -> None:
    lock = load_lock()
    lab = Lab()
    ids = [s["id"] for s in lock["specs"]]
    record_access("test", ids, "final test open")
    order = json.loads((OUT_DIR / "locked_order.json").read_text())
    rows = []
    for s in lock["specs"]:
        spec = {"family": s["family"], "params": s["params"]}
        row = {"id": s["id"], "family": s["family"], "params": json.dumps(s["params"], sort_keys=True)}
        for split in ("train", "val", "test"):
            m, _ = lab.run(spec, split)
            for k in ("cagr", "maxdd", "calmar", "maxdd_intra", "calmar_intra", "total_return",
                      "sharpe", "gross_avg", "turnover_per_year", "ruined", "pos_years", "month_win"):
                row[f"{split}_{k}"] = m[k]
        ms, _ = lab.run(spec, "test", stress=True)
        row["test_stress_calmar"] = ms["calmar"]
        row["test_stress_total_return"] = ms["total_return"]
        mv, _ = lab.run(spec, "val", stress=True)
        row["val_stress_calmar"] = mv["calmar"]
        rows.append(row)
    df = pd.DataFrame(rows)
    df["val_rank"] = df.id.map({sid: i + 1 for i, sid in enumerate(order)})
    df = df.sort_values("val_calmar", ascending=False)
    df.to_csv(OUT_DIR / "final_results.csv", index=False)
    df.to_parquet(OUT_DIR / "final_results.parquet")

    k0, k1 = split_range(lab.panel, "test")
    btc = lab.panel.close[:, lab.ctx.btc]
    bh = btc[k1] / btc[k0] - 1
    print(f"BTC buy&hold over test: {bh:.1%}")
    cols = ["id", "train_calmar", "val_calmar", "test_calmar", "test_cagr", "test_maxdd",
            "test_total_return", "test_stress_calmar", "val_stress_calmar", "test_ruined"]
    print(df[cols].round(3).to_string())
    n_t = int((df.test_calmar > 1).sum())
    n_all = int(((df.train_calmar > 1) & (df.val_calmar > 1) & (df.test_calmar > 1)).sum())
    print(f"\ntest Calmar>1: {n_t}/{len(df)} | train&val&test >1: {n_all}")
    print("test total return >0:", int((df.test_total_return > 0).sum()), "/", len(df))
    print("median test total return:", round(float(np.median(df.test_total_return)), 4))


if __name__ == "__main__":
    main()
