"""Second bounded development batch. All 2025 stages remain selection-gated."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import copy
import gzip
import json
from pathlib import Path

import research_v407 as r

BASE = r.ART
ART = BASE / "round02"
VARIANTS = [
    {"id":"sniper_rr1", "rr_min":1.0},
    {"id":"sniper_stop_max10pct", "stop_max":.10},
    {"id":"sniper_4h", "tf":"4h"},
    {"id":"sniper_1d", "tf":"1d"},
    {"id":"sniper_horizon24", "hours":24},
    {"id":"sniper_rr1_horizon24", "rr_min":1.0, "hours":24},
]


def init():
    ART.mkdir(exist_ok=True)
    path = ART / "PROTOCOL.json"
    if path.exists(): raise FileExistsError("Round already registered")
    r.save(path, {"experiment":"4.0.7-round02", "registered_at_utc":datetime.now(timezone.utc).isoformat(),
        "base_protocol_sha256":r.sha(BASE / "PROTOCOL.json"), "development_evidence_sha256":r.sha(BASE / "development/RESULTS.json"),
        "data_windows":r.WINDOWS, "variants":VARIANTS, "new_variants":6, "cumulative_variants":18,
        "motivation":"Round01 sniper improved 2024 but failed H2. Development-only attribution suggests its H2 losses concentrate in TP1/stop reward ratios below 1. Test that interaction, timeframes, wide-stop exclusion, and a fixed 24h horizon. These hypotheses are adaptive to development results, not globally prespecified discoveries.",
        "selection_gates":"Same numerical gates as round01. >=40 development trades, 40bps+stress positive, 60bps+stress nonnegative, both reset halves positive, maxDD<=15%, no accepted execution gaps. Rank 60bps return-DD. Lock at most two before validation; validation needs >=20 trades and locks one before final.",
        "final_gate":"Same as round01 including lower95 weekly 4-week block-bootstrap CI>0. No retuning after final. 2025 historically reused; fresh_oos=false.",
        "execution":"Unchanged causal 5-minute delayed entry and fixed-quantity engine. 24h horizon truncates an open position at the known close without changing its prior path.",
        "2026_observations_allowed":False, "live_signoff":"NOT_GRANTED"})
    r.save(ART / "PROGRESS.json", {"stage":"registered", "goal_complete":False, "next_action":"evaluate development only"})


def truncate_path(path, deadline):
    if path["exit_ts"] <= deadline:
        return path
    trace = [tuple(s) for s in path["trace"] if s[0] <= deadline]
    if not trace or trace[-1][0] != deadline:
        raise ValueError("Missing 24-hour closing candle")
    last = list(trace[-1]); last[3]=0.; last[6]=True; trace[-1]=tuple(last)
    return {"trace":trace,"gross_return":sum(s[5] for s in trace),"exit_ts":deadline,"exit_reason":"horizon24"}


def transformed(candidates, spec):
    if spec["id"] == "reference_m6_fixed": return candidates
    selected=[]
    for c in candidates:
        if not r.passes(c,"sniper"): continue
        if "rr_min" in spec and c["rr1"] < spec["rr_min"]: continue
        if "stop_max" in spec and c["stop"]/c["entry"]-1 > spec["stop_max"]: continue
        if "tf" in spec and c["tf"] != spec["tf"]: continue
        item=c
        if "hours" in spec:
            item=dict(c); item["paths"]=dict(c["paths"])
            # Rejecting a candidate based on missing FUTURE bars would select on
            # outcomes. Raise and invalidate this variant instead of dropping it.
            item["paths"]["ladder"]=truncate_path(c["paths"]["ladder"], c["entry_ts"]+spec["hours"]*3600)
        selected.append(item)
    return selected


def evaluate(stage):
    directory=ART/stage; directory.mkdir(exist_ok=True)
    if (directory/"RESULTS.json").exists(): raise FileExistsError("Round results already frozen")
    original=r.ART
    r.ART=BASE if stage=="development" else ART
    candidates=r.load_candidates(stage)
    r.ART=original
    variants=VARIANTS
    if stage!="development":
        lock=r.read(ART/("SHORTLIST_LOCK.json" if stage=="validation" else "WINNER_LOCK.json"))
        variants=[v for v in variants if v["id"] in lock["variant_ids"]]
    variants=[{"id":"reference_m6_fixed"}]+variants
    start,end=r.WINDOWS[stage]; results={}; ledgers={}
    for spec in variants:
        vid=spec["id"]; source=transformed(candidates,spec)
        policy={"gate":"expanded","exit":"ladder","sizing":"fixed" if vid=="reference_m6_fixed" else "risk"}
        results[vid]={}
        for cost in (40,60):
            for stress in (False,True):
                key=f"{cost}bps_{'stress' if stress else 'ex_funding'}"
                out=r.portfolio(source,policy,start,end,cost,stress)
                out["weekly_ci"]=r.block_ci(out["weekly_returns"])
                ledgers[f"{vid}/{key}"]={"ledger":out.pop("ledger"),"curve":out.pop("curve")}
                results[vid][key]=out
        if stage=="development":
            halves=[]
            for a,b in [("2024-01-01","2024-07-01"),("2024-07-01","2025-01-01")]:
                o=r.portfolio(source,policy,a,b,40,True)
                halves.append({"start":a,"end":b,"return_pct":o["return_pct"],"trades":o["trades"],"max_dd_pct":o["max_dd_pct"]})
            results[vid]["reset_half_year_checks"]=halves
        a,b=results[vid]["40bps_stress"],results[vid]["60bps_stress"]
        ok=vid!="reference_m6_fixed" and a["trades"] >= (40 if stage=="development" else 20)
        ok=ok and a["return_pct"]>0 and b["return_pct"]>=0 and max(a["max_dd_pct"],b["max_dd_pct"])<=15
        ok=ok and a["accepted_missing_execution_bars"]==0 and b["accepted_missing_execution_bars"]==0
        if stage=="development": ok=ok and all(h["return_pct"]>0 for h in results[vid]["reset_half_year_checks"])
        if stage=="final_oos": ok=ok and a["weekly_ci"]["available"] and a["weekly_ci"]["ci95_pct"][0]>0
        results[vid]["qualifies"]=bool(ok)
        print(f"round02/{stage}/{vid}: N={a['trades']} NAV40={a['return_pct']:.3f}% NAV60={b['return_pct']:.3f}% DD={a['max_dd_pct']:.3f}% qualified={ok}",flush=True)
    qualified=sorted([k for k,v in results.items() if v["qualifies"]],key=lambda k:(-(results[k]["60bps_stress"]["return_pct"]-results[k]["60bps_stress"]["max_dd_pct"]),k))
    r.save(directory/"RESULTS.json", {"stage":stage,"round":2,"protocol_sha256":r.sha(ART/"PROTOCOL.json"),
          "source_sha256":r.sha(__file__),"engine_sha256":r.sha(r.__file__),"results":results,"fresh_oos":False,"live_signoff":"NOT_GRANTED"})
    with gzip.open(directory/"LEDGERS.json.gz","wt",encoding="utf8") as fh: json.dump(ledgers,fh,separators=(",",":"),allow_nan=False)
    if stage!="final_oos" and qualified:
        filename="SHORTLIST_LOCK.json" if stage=="development" else "WINNER_LOCK.json"
        if (ART/filename).exists(): raise FileExistsError("Selection already locked")
        r.save(ART/filename,{"variant_ids":qualified[:2 if stage=="development" else 1],
               "locked_at_utc":datetime.now(timezone.utc).isoformat(),"selection_results_sha256":r.sha(directory/"RESULTS.json"),
               "protocol_sha256":r.sha(ART/"PROTOCOL.json"),"unopened_next_stage":"validation" if stage=="development" else "final_oos"})
    r.save(ART/"PROGRESS.json",{"stage":stage+"_evaluated","qualified_variants":qualified,"goal_complete":False,"live_signoff":"NOT_GRANTED"})


def prepare(stage):
    r.ART=ART
    r.prepare(stage)


def worker(stage,symbol):
    r.ART=ART
    return r.collect_one(stage,symbol)


def collect(stage,workers):
    r.ART=ART; r.stage_permission(stage)
    directory=ART/stage; manifest=r.read(directory/"DATA_MANIFEST.json")
    for symbol,row in manifest["inputs"].items():
        assert r.sha(directory/"bars_5m"/f"{symbol}.parquet")==row["snapshot_sha256"]
    members=r.read(directory/"MEMBERSHIP.json")
    symbols=sorted({row["symbol"] for rows in members.values() for row in rows})
    (directory/"candidates").mkdir(exist_ok=True); results={}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        fs=[pool.submit(worker,stage,s) for s in symbols]
        for i,f in enumerate(as_completed(fs),1):
            symbol,count,skipped,digest=f.result()
            results[symbol]={"candidates":count,"rejections":skipped,"sha256":digest}
            print(f"round02/{stage}: {i}/{len(symbols)} {symbol}={count}",flush=True)
    r.save(directory/"CANDIDATE_MANIFEST.json",{"protocol_sha256":r.sha(ART/"PROTOCOL.json"),
        "source_sha256":r.sha(r.__file__),"data_manifest_sha256":r.sha(directory/"DATA_MANIFEST.json"),"symbols":results})


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("action",choices=["init","evaluate","prepare","collect"])
    parser.add_argument("--stage",choices=r.WINDOWS,default="development");parser.add_argument("--workers",type=int,default=4)
    args=parser.parse_args()
    if args.action=="init":init()
    elif args.action=="evaluate":evaluate(args.stage)
    elif args.action=="prepare":prepare(args.stage)
    else:collect(args.stage,args.workers)
