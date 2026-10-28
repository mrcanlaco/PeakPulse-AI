"""Lock the final candidate list BEFORE test 2026 is opened.

Rule (fixed here, before any test access):
  pool   = every frozen spec (rounds R1..R6) with validation Calmar > 1 and no ruin
  step 1 = rank by validation Calmar (desc); greedy keep if |corr| < 0.85 versus all kept
           (daily returns, train + validation)  ->  take the first 30
  step 2 = diversifiers: add the best pool member of each mechanism not yet represented
           (mkt_flow timing, liquidity-tier-neutral composite, long-only regime composite)
"""

from __future__ import annotations

import json

import pandas as pd

from dao_vang.nostop.lab import Lab
from dao_vang.nostop.registry import ROUNDS_DIR, load_frozen, lock_candidates, spec_id

CORR_MAX = 0.85
TOP_N = 30


def mechanism(spec: dict) -> str:
    p = spec["params"]
    if spec["family"] == "mkt_flow":
        return "mkt_flow"
    if spec["family"] == "composite" and p.get("tier_neutral"):
        return "tier_neutral"
    if spec["family"] == "composite" and p.get("mode") == "long":
        return "long_regime"
    return spec["family"] + ":" + p.get("mode", "")


def main() -> None:
    lab = Lab()
    rows, specs = [], {}
    for d in sorted(ROUNDS_DIR.iterdir()):
        vp = d / "val_results.parquet"
        if not vp.exists():
            continue
        v = pd.read_parquet(vp)
        v["round"] = d.name
        rows.append(v)
        for s in load_frozen(d.name)["specs"]:
            specs[s["id"]] = {"family": s["family"], "params": s["params"]}
    allv = pd.concat(rows, ignore_index=True)
    pool = allv[(allv.val_calmar > 1) & (~allv.val_ruined.astype(bool))].sort_values(
        "val_calmar", ascending=False
    )
    print("frozen total:", len(allv), "| val>1:", len(pool))
    dr = {
        sid: pd.concat([lab.daily(specs[sid], "train"), lab.daily(specs[sid], "val")])
        for sid in pool["id"]
    }
    kept: list[str] = []
    for sid in pool["id"]:
        if all(abs(dr[sid].corr(dr[o])) < CORR_MAX for o in kept):
            kept.append(sid)
        if len(kept) >= TOP_N:
            break
    have = {mechanism(specs[s]) for s in kept}
    extra = []
    for sid in pool["id"]:
        m = mechanism(specs[sid])
        if m in ("mkt_flow", "tier_neutral", "long_regime") and m not in have and sid not in kept:
            extra.append(sid)
            have.add(m)
    final = kept + extra
    print("kept by rule:", len(kept), "| diversifiers:", [(e, mechanism(specs[e])) for e in extra])
    sel = [specs[s] for s in final]
    path = lock_candidates(
        sel,
        f"top{TOP_N} by validation Calmar (|corr|<{CORR_MAX}) + mechanism diversifiers; "
        f"pool {len(pool)} of {len(allv)} frozen",
    )
    print("locked", len(final), "->", path)
    tbl = allv.set_index("id").loc[final][["round", "train_calmar", "val_calmar", "val_cagr", "val_maxdd"]]
    tbl["mechanism"] = [mechanism(specs[s]) for s in final]
    print(tbl.round(3).to_string())
    json.dump(final, open(ROUNDS_DIR.parent / "locked_order.json", "w"))
    assert spec_id(sel[0]) == final[0]


if __name__ == "__main__":
    main()
