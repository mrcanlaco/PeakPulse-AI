"""Round driver: TRAIN sweep -> plateau smoothing -> selection -> FREEZE -> VALIDATE.

    python -m dao_vang.nostop.rounds train  R1
    python -m dao_vang.nostop.rounds freeze R1
    python -m dao_vang.nostop.rounds val    R1
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

from . import grids as G
from .lab import Lab, sweep
from .registry import ROUNDS_DIR, freeze_round, frozen_ids, load_frozen, spec_id

TRAIN_GATE = {
    "calmar": 1.0,
    "smooth": 0.8,
    "pos_years_min": 3,
    "calmar_intra": 0.7,
    "cagr": 0.10,
}
TOP_PER_GROUP = 3
CORR_MAX = 0.90


def _rd(name: str):
    d = ROUNDS_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def flatten(sid: str, m: dict) -> dict:
    keys = ("cagr", "maxdd", "calmar", "maxdd_intra", "calmar_intra", "total_return", "sharpe",
            "gross_avg", "turnover_per_year", "ruined", "pos_years", "n_years", "month_win")
    row = {"id": sid}
    if "error" in m:
        row["error"] = m["error"]
        return row
    row.update({k: m[k] for k in keys})
    for y, v in m["yearly"].items():
        row[f"y{y}"] = v
    return row


def train_sweep(name: str, specs: list[dict]) -> pd.DataFrame:
    stripped = [G.strip(s) for s in specs]
    res = sweep(stripped, "train")
    rows = []
    for s in specs:
        sid = spec_id(s)
        r = flatten(sid, res[sid])
        r.update({"family": s["family"], "group": s["_group"], "idx": json.dumps(s["_idx"]),
                  "params": json.dumps(s["params"], sort_keys=True)})
        rows.append(r)
    df = pd.DataFrame(rows)
    df.to_parquet(_rd(name) / "train_sweep.parquet")
    return df


def smooth_scores(df: pd.DataFrame) -> pd.Series:
    """Mean clipped Calmar over a point and its +-1-step neighbours (one axis at a time)."""
    out = pd.Series(np.nan, index=df.index)
    for _, g in df.groupby("group"):
        idxs = {tuple(json.loads(i)): k for k, i in zip(g.index, g["idx"])}
        cal = g["calmar"].clip(-2, 5).where(~g["ruined"].astype(bool), -2.0)
        for key, k in idxs.items():
            vals = [cal.loc[k]]
            for ax in range(len(key)):
                for d in (-1, 1):
                    nb = list(key)
                    nb[ax] += d
                    j = idxs.get(tuple(nb))
                    if j is not None:
                        vals.append(cal.loc[j])
            out.loc[k] = float(np.mean(vals))
    return out


def select(df: pd.DataFrame, specs_by_id: dict[str, dict], lab: Lab, min_pos_years: int | None = None) -> list[dict]:
    df = df.copy()
    df["smooth"] = smooth_scores(df)
    ok = df[
        (df.calmar > TRAIN_GATE["calmar"])
        & (df.smooth > TRAIN_GATE["smooth"])
        & (df.pos_years >= (min_pos_years or TRAIN_GATE["pos_years_min"]))
        & (df.calmar_intra > TRAIN_GATE["calmar_intra"])
        & (df.cagr > TRAIN_GATE["cagr"])
        & (~df.ruined.astype(bool))
    ]
    chosen: list[dict] = []
    for _, g in ok.groupby("group"):
        cand = g.sort_values("smooth", ascending=False).head(12)
        kept: list[tuple[str, pd.Series]] = []
        for sid in cand["id"]:
            d = lab.daily(G.strip(specs_by_id[sid]), "train")
            if all(abs(d.corr(o)) < CORR_MAX for _, o in kept):
                kept.append((sid, d))
            if len(kept) >= TOP_PER_GROUP:
                break
        chosen += [G.strip(specs_by_id[sid]) for sid, _ in kept]
    return chosen


def cmd_train(name: str) -> None:
    specs = G.expand(G.GRID_SETS[name])
    print(f"{name}: {len(specs)} train configs")
    df = train_sweep(name, specs)
    df["smooth"] = smooth_scores(df)
    df.to_parquet(_rd(name) / "train_sweep.parquet")
    best = df.sort_values("smooth", ascending=False).groupby("group").head(1)
    print(best[["group", "id", "calmar", "smooth", "cagr", "maxdd", "pos_years"]].to_string())
    (_rd(name) / "n_trials.json").write_text(json.dumps({"train_configs": len(specs)}))


MOMENTUM_TOKENS = ("mom", "resid")
PRICE_FAMILIES = {"xs_mom", "ts_mom_basket", "btc_trend", "resid_mom"}
FLOW_FAMILIES = {"taker", "tchg", "fz", "funding_xs", "composite"}
TREND_FAMILIES = {"xs_mom", "ts_mom_basket", "btc_trend"}


def _is_price_driven(spec: dict) -> bool:
    if spec["family"] in PRICE_FAMILIES:
        return True
    if spec["family"] == "composite":
        return any(t.startswith(MOMENTUM_TOKENS) for t in spec["params"]["factors"].split("+"))
    return False


def greedy_blends(lab: Lab, pool: list[dict], tag: str, sizes=(2, 3, 4, 5, 6)) -> list[dict]:
    """Forward-select sleeves that maximise TRAIN Calmar of the equal-weight daily-return
    blend, then emit the exact blend specs (re-simulated by the engine, not approximated)."""
    if len(pool) < 2:
        return []
    daily = pd.DataFrame({spec_id(s): lab.daily(s, "train") for s in pool}).fillna(0.0)

    def calmar_of(ret: pd.Series) -> float:
        eq = (1 + ret).cumprod()
        yrs = len(ret) / 365.25
        cagr = eq.iloc[-1] ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1.0
        dd = (1 - eq / eq.cummax()).max()
        return cagr / dd if dd > 1e-9 else 0.0

    by_id = {spec_id(s): s for s in pool}
    standalone = {c: calmar_of(daily[c]) for c in daily.columns}
    chosen = [max(standalone, key=lambda k: standalone[k])]
    out: list[dict] = []
    while len(chosen) < max(sizes):
        best, best_v = None, -9.0
        for c in daily.columns:
            if c in chosen:
                continue
            v = calmar_of(daily[chosen + [c]].mean(axis=1))
            if v > best_v:
                best, best_v = c, v
        if best is None:
            break
        chosen.append(best)
        if len(chosen) in sizes:
            parts = [by_id[c] for c in chosen]
            out.append({"family": "blend",
                        "params": {"parts": parts, "tv": 0.3, "max_lev": 2.0, "tag": tag}})
    return out


def _pool(lab: Lab, rounds: list[str]) -> list[dict]:
    """Train-gated, correlation-filtered pool of single sleeves from all sweeps so far."""
    frames, by_id = [], {}
    for r in rounds:
        sp = G.expand(G.GRID_SETS[r])
        by_id.update({spec_id(s): s for s in sp})
        d = pd.read_parquet(_rd(r) / "train_sweep.parquet")
        d["smooth"] = smooth_scores(d)
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    ok = df[(df.calmar > 1.0) & (df.smooth > 0.8) & (df.pos_years >= 3)
            & (df.calmar_intra > 0.7) & (~df.ruined.astype(bool))]
    ok = ok.sort_values("smooth", ascending=False).head(120)
    kept: list[tuple[str, pd.Series]] = []
    for sid in ok["id"]:
        d = lab.daily(G.strip(by_id[sid]), "train")
        if all(abs(d.corr(o)) < 0.92 for _, o in kept):
            kept.append((sid, d))
        if len(kept) >= 40:
            break
    return [G.strip(by_id[sid]) for sid, _ in kept]


def cmd_freeze(name: str) -> None:
    specs = G.expand(G.GRID_SETS[name])
    by_id = {spec_id(s): s for s in specs}
    df = pd.read_parquet(_rd(name) / "train_sweep.parquet")
    lab = Lab()
    chosen = select(df, by_id, lab, min_pos_years=4 if name != "R1" else None)
    already = frozen_ids()
    chosen = [s for s in chosen if spec_id(s) not in already]
    blends: list[dict] = []
    if name == "R2":  # greedy blends overfit train (R2 validation: 0/19 passed); not repeated
        rounds = sorted(r for r in G.GRID_SETS if r <= name)
        pool = _pool(lab, rounds)
        print(f"blend pool: {len(pool)} sleeves")
        pools = {
            "all": pool,
            "no_price": [s for s in pool if not _is_price_driven(s)],
            "flow_carry": [s for s in pool if s["family"] in FLOW_FAMILIES and not _is_price_driven(s)],
            "trend": [s for s in pool if s["family"] in TREND_FAMILIES],
        }
        for tag, p in pools.items():
            b = greedy_blends(lab, p, tag)
            print(f"  pool {tag}: {len(p)} sleeves -> {len(b)} blends")
            blends += b
        blends = [b for b in blends if spec_id(b) not in already]
    allspecs = chosen + blends
    n_trials = json.loads((_rd(name) / "n_trials.json").read_text())["train_configs"]
    path = freeze_round(name, allspecs, {"gate": TRAIN_GATE, "train_configs": n_trials,
                                         "top_per_group": TOP_PER_GROUP, "corr_max": CORR_MAX,
                                         "n_blends": len(blends)})
    by_fam = defaultdict(int)
    for s in allspecs:
        by_fam[s["family"]] += 1
    print(f"frozen {len(allspecs)} specs -> {path}\n{dict(by_fam)}")


def cmd_val(name: str) -> pd.DataFrame:
    fz = load_frozen(name)
    specs = [{"family": s["family"], "params": s["params"]} for s in fz["specs"]]
    res = sweep(specs, "val")
    tr = sweep(specs, "train")
    rows = []
    for s in specs:
        sid = spec_id(s)
        r = flatten(sid, res[sid])
        r = {("val_" + k if k != "id" else k): v for k, v in r.items()}
        t = flatten(sid, tr[sid])
        r.update({"train_calmar": t.get("calmar"), "train_cagr": t.get("cagr"),
                  "train_maxdd": t.get("maxdd"), "family": s["family"],
                  "params": json.dumps(s["params"], sort_keys=True)})
        rows.append(r)
    df = pd.DataFrame(rows).sort_values("val_calmar", ascending=False)
    df.to_parquet(_rd(name) / "val_results.parquet")
    show = df[["id", "train_calmar", "val_calmar", "val_cagr", "val_maxdd", "val_calmar_intra",
               "val_pos_years", "val_ruined"]]
    print(show.to_string())
    n_pass = int(((df.val_calmar > 1.0) & (~df.val_ruined.astype(bool))).sum())
    print(f"\n{name}: validation Calmar>1 and not ruined: {n_pass}/{len(df)}")
    return df


if __name__ == "__main__":
    cmd, rnd = sys.argv[1], sys.argv[2]
    {"train": cmd_train, "freeze": cmd_freeze, "val": cmd_val}[cmd](rnd)
