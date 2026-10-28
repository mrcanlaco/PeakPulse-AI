"""Stage 1 of the PDF report: collect every number the report quotes into one JSON file.

Run with the project venv:  .venv/Scripts/python.exe scripts/nostop_report_data.py
Output: artifacts/nostop/report/data.json   (read by scripts/build_nostop_pdf_report.py)
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from dao_vang.nostop.data import OUT_DIR
from dao_vang.nostop.engine import metrics, simulate, split_range
from dao_vang.nostop.lab import Lab
from dao_vang.nostop.registry import ROUNDS_DIR, load_lock
from dao_vang.nostop.shadow.binance import PublicClient
from dao_vang.nostop.shadow.feed import SharedFeed
from dao_vang.nostop.shadow.store import DATA_DIR, Store

OUT = OUT_DIR / "report"
OUT.mkdir(parents=True, exist_ok=True)


def rounds_table() -> list[dict]:
    rows = []
    for d in sorted(ROUNDS_DIR.iterdir()):
        vp = d / "val_results.parquet"
        if not vp.exists():
            continue
        v = pd.read_parquet(vp).sort_values("val_calmar", ascending=False)
        n = json.loads((d / "n_trials.json").read_text())["train_configs"]
        rows.append({"round": d.name, "train_configs": n, "frozen": len(v),
                     "val_gt1": int((v.val_calmar > 1).sum()), "best_val": float(v.val_calmar.max()),
                     "top20_mean": float(v.val_calmar.head(20).mean())})
    return rows


def main() -> None:
    lab = Lab()
    fin = pd.read_csv(OUT_DIR / "final_results.csv").set_index("id")
    rob = pd.read_csv(OUT_DIR / "robustness.csv").set_index("id")
    prof = json.loads((DATA_DIR / "profiles.json").read_text(encoding="utf-8"))
    lock = {s["id"]: s for s in load_lock()["specs"]}
    passing = [i for i in fin.index if fin.loc[i, "train_calmar"] > 1 and fin.loc[i, "val_calmar"] > 1
               and fin.loc[i, "test_calmar"] > 1]
    data: dict = {"generated": time.strftime("%Y-%m-%d %H:%M"), "rounds": rounds_table()}

    # ---- table of the 28 shadows -------------------------------------------------
    rows = []
    for sid in fin.sort_values("val_calmar", ascending=False).index:
        p = prof[sid]
        r = fin.loc[sid]
        rows.append({
            "id": sid, "shadow": sid in passing, "title": p["title"], "round": p["origin_round"],
            "ivol": lock[sid]["params"].get("wt") == "ivol", "tier": bool(lock[sid]["params"].get("tier_neutral")),
            "factors": lock[sid]["params"].get("factors", lock[sid]["family"]),
            "train_calmar": float(r.train_calmar), "val_calmar": float(r.val_calmar), "test_calmar": float(r.test_calmar),
            "train_cagr": float(r.train_cagr), "val_cagr": float(r.val_cagr), "test_cagr": float(r.test_cagr),
            "train_maxdd": float(r.train_maxdd), "val_maxdd": float(r.val_maxdd), "test_maxdd": float(r.test_maxdd),
            "test_ret": float(r.test_total_return), "test_sharpe": float(r.test_sharpe),
            "val_sharpe": float(r.val_sharpe), "train_sharpe": float(r.train_sharpe),
            "stress_test": float(r.test_stress_calmar), "delay1": float(rob.loc[sid, "test_delay1_calmar"]),
            "delay3": float(rob.loc[sid, "test_delay3_calmar"]),
            "turn_test": float(r.test_turnover_per_year), "gross_test": float(r.test_gross_avg),
            "beta": {k: p["btc_beta"][k] for k in ("train", "val", "test")},
            "max_w": p["max_single_weight_median"],
            "post_lock": p.get("post_lock"),
            "yearly": {str(y["year"]): y["ret"] for y in p["yearly_stats"]},
            "yearly_dd": {str(y["year"]): y["maxdd"] for y in p["yearly_stats"]},
            "curve": p["curve"],
        })
    data["candidates"] = rows

    # ---- equal-weight blend of the 28 (daily returns) ----------------------------
    daily = {}
    for split in ("train", "val", "test"):
        daily[split] = pd.DataFrame({sid: lab.daily({"family": lock[sid]["family"], "params": lock[sid]["params"]}, split)
                                     for sid in passing}).fillna(0.0)
    blend = {}
    chain_t, chain_v, last = [], [], 1.0
    for split in ("train", "val", "test"):
        ret = daily[split].mean(axis=1)
        eq = (1 + ret).cumprod()
        yrs = len(ret) / 365.25
        cagr = float(eq.iloc[-1] ** (1 / yrs) - 1)
        dd = float((1 - eq / eq.cummax()).max())
        sh = float(ret.mean() / ret.std() * np.sqrt(365.25))
        blend[split] = {"cagr": cagr, "maxdd": dd, "calmar": cagr / dd, "sharpe": sh, "total": float(eq.iloc[-1] - 1)}
        e2 = eq * last
        chain_t += [int(t.value // 1_000_000) for t in e2.index[::3]]
        chain_v += [float(v) for v in e2.values[::3]]
        last = float(e2.iloc[-1])
    blend["curve"] = [chain_t, chain_v]
    allret = pd.concat([daily[s].mean(axis=1) for s in ("train", "val", "test")])
    blend["yearly"] = {str(y): float((1 + g).prod() - 1) for y, g in allret.groupby(allret.index.year)}
    tc = daily["test"].corr().values
    data["test_corr_median"] = float(np.median(tc[np.triu_indices(len(tc), 1)]))
    data["test_corr_min"] = float(tc[np.triu_indices(len(tc), 1)].min())
    data["blend"] = blend

    # ---- BTC buy-and-hold context -------------------------------------------------
    btc = {}
    for split in ("train", "val", "test"):
        k0, k1 = split_range(lab.panel, split)
        px = lab.panel.close[k0:k1 + 1, lab.ctx.btc]
        yrs = (k1 - k0 + 1) / (6 * 365.25)
        cagr = float((px[-1] / px[0]) ** (1 / yrs) - 1)
        dd = float((1 - px / np.maximum.accumulate(px)).max())
        btc[split] = {"cagr": cagr, "maxdd": dd, "total": float(px[-1] / px[0] - 1)}
    data["btc"] = btc

    # ---- live feed: ADV by liquidity rank, example portfolio, shadows -------------
    feed = SharedFeed(DATA_DIR, PublicClient())
    feed.load()
    panel, _ = feed.panel()
    qv = pd.DataFrame(panel.qvol).rolling(180, min_periods=30).mean().iloc[-2].to_numpy() * 6
    order = np.sort(qv[np.isfinite(qv)])[::-1]
    data["adv"] = {str(r): float(order[r - 1]) for r in (1, 5, 10, 20, 30, 40, 50, 70, 100) if r <= len(order)}
    data["feed_asof"] = str(panel.index[-1])

    st = Store(DATA_DIR)
    ov = json.loads(urllib.request.urlopen("http://127.0.0.1:8890/api/overview", timeout=10).read())
    data["live"] = {"totals": ov["totals"], "counts": ov["counts"], "now": ov["now"],
                    "system": {k: ov["system"].get(k) for k in ("cycles", "rss_mb", "cycle_seconds", "api_used_weight_1m",
                                                               "api_calls", "feed_symbols", "feed_bars")},
                    "rows": [{"id": s["id"], "ret": s["ret"], "pnl": s["pnl"], "pos": s["n_positions"], "gross": s["gross"],
                              "days": s["days"]} for s in ov["shadows"]]}
    example = "composite-3db01c74"
    state = st.read_state(example) or {}
    data["example"] = {"id": example, "title": prof[example]["title"], "positions": state.get("positions", [])[:14],
                       "equity": state.get("equity"), "gross": state.get("gross"), "net": state.get("net")}

    # ---- counts quoted in the text ------------------------------------------------
    fu = {}
    for sid in passing:
        for t in {x.rstrip("0123456789.") for x in lock[sid]["params"]["factors"].split("+")}:
            fu[t] = fu.get(t, 0) + 1
    data["factor_usage"] = fu
    data["n_passing"] = len(passing)
    data["n_locked"] = len(fin)
    data["test_pass"] = int((fin.test_calmar > 1).sum())
    data["frozen_total"] = int(sum(r["frozen"] for r in data["rounds"]))
    data["val_gt1_total"] = int(sum(r["val_gt1"] for r in data["rounds"]))
    data["train_trials_total"] = int(sum(r["train_configs"] for r in data["rounds"]))

    (OUT / "data.json").write_text(json.dumps(data), encoding="utf-8")
    print("wrote", OUT / "data.json", "| passing", len(passing), "| blend", {k: round(v["calmar"], 2) for k, v in blend.items() if k in ("train", "val", "test")})
    _ = (metrics, simulate, Path)


if __name__ == "__main__":
    main()
