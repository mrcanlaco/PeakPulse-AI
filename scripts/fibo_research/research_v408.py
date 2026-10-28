"""2020-2025 point-in-time universe and retrospective expanding-window audit.

Six frozen existing policies; no new threshold search. Historical reuse is
disclosed. 2026 observations are forbidden even when files contain them.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import pickle
import shutil

import numpy as np
import pandas as pd
import research_v407 as r
from research_round02_v407 import transformed
from dao_vang.fibo_short.backtest import PRE2024_5M_DIR

ROOT=r.ROOT
ART=ROOT/"artifacts/fibo_trend_short/research_v4_0_8"
START=r.utc("2020-01-01")
END=r.utc("2026-01-01")
JOIN=r.utc("2024-01-01")
FAMILY=[
    {"id":"reference_m6_fixed","gate":"expanded","sizing":"fixed","exit":"ladder"},
    {"id":"m6_risk","gate":"expanded","sizing":"risk","exit":"ladder"},
    {"id":"elite_sniper_risk","gate":"elite_sniper","sizing":"risk","exit":"ladder"},
    {"id":"sniper_risk","gate":"sniper","sizing":"risk","exit":"ladder"},
    {"id":"sniper_horizon24","gate":"expanded","sizing":"risk","exit":"ladder","hours":24},
    {"id":"sniper_rr1_horizon24","gate":"expanded","sizing":"risk","exit":"ladder","hours":24,"rr_min":1.},
]


def initialize():
    ART.mkdir(parents=True,exist_ok=True)
    if (ART/"PROTOCOL.json").exists():raise FileExistsError("Do not overwrite a registered protocol")
    r.save(ART/"PROTOCOL.json",{
        "version":"4.0.8-research", "registered_at_utc":datetime.now(timezone.utc).isoformat(),
        "user_requirement":"Use the longer history beginning in 2020; do not backtest observations after 2025; retain OOS and all mini-alpha evidence.",
        "observation_window":{"start_inclusive":START.isoformat(),"end_exclusive":END.isoformat()},
        "sources":{"pre2024":str(PRE2024_5M_DIR),"from2024":str(r.LAKE)},
        "data_contract":"Select pre-2024 source rows in [2020,2024) and recent source rows in [2024,2026) with parquet predicate filters. Merge observed history only. Do not backfill listing dates. Reject conflicting duplicates and invalid OHLCV.",
        "universe":"At each calendar month, rank available symbols using only prior 63 days, >=50 active days, H4 wick p90<=3.2%, median quote volume top50, same fixed exclusions. Early months may have fewer than50 symbols. Available-file survivorship bias remains.",
        "family":FAMILY,"new_parameter_variants":0,"all_prior_variant_trials_at_least":24,
        "annual_comparison":"Run all six frozen policies for each year 2020..2025, reset equity/state at Jan1 and embargo entries for5days before year end. Identical 5-minute delayed entry, fixed quantities and risk constraints as v407. Report each year and linked annual returns.",
        "costs_bps":[40,60],"funding":"Adverse synthetic short1bp/8h. Not historical funding.",
        "walk_forward":{"initial_train_years":[2020,2021],"test_years":[2022,2023,2024,2025],
            "selection":"For each test year, inspect earlier-year results only. Exclude fixed reference. Require >=60 prior trades total, >0 aggregate40bps return, >=0 aggregate60bps return, >0 return in EACH prior year at40bps, each year maxDD<=15% at both costs, no accepted execution gaps. Rank by aggregate60bps return minus linked60bps MaxDD, ties by ID. If no policy qualifies, select CASH. Write immutable selection lock BEFORE computing the test-year results.",
            "oos_assembly":"Link only each year's selected-policy NAV, or flat100 for CASH. Also retain fixed-policy comparisons without selecting by test results.",
            "success":"Do not call CASH-only selection or positive in-sample returns strategy completion. Economic/statistical evidence, execution robustness, historical reuse and gaps remain explicit."},
        "reuse_disclosure":"The policy family was previously developed using2024 and examined on2025. This expanding-window replay is retrospective and cannot erase that global reuse; it is NOT a globally untouched historical OOS. It tests chronological selection mechanics and regime robustness.",
        "hard_2026_data_ban":True,"live_signoff":"NOT_GRANTED"})
    previous=ROOT/"artifacts/fibo_trend_short/research_v4_0_7/CHECKPOINT_AFTER_ROUND03.json"
    r.save(ART/"PRESERVED_PREVIOUS_CHECKPOINT.json",{"path":str(previous),"sha256":r.sha(previous)})
    sources=[Path(__file__),ROOT/"scripts/fibo_research/research_v407.py",ROOT/"scripts/fibo_research/research_round02_v407.py",
        ROOT/"scripts/fibo_research/universe_reaudit_v402_worker.py",ROOT/"scripts/fibo_research/verify_red_team_audit_2026.py",
        ROOT/"src/dao_vang/fibo_short/detector.py",ROOT/"src/dao_vang/fibo_short/backtest.py",ROOT/"src/dao_vang/config/settings.py",
        ROOT/"tests/unit/fibo_short/test_research_v408.py"]
    for source in sources:
        target=ART/"source_snapshot"/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    r.save(ART/"SOURCE_MANIFEST.json",{str(p.relative_to(ROOT)):r.sha(p) for p in sources})
    r.save(ART/"PROGRESS.json",{"stage":"protocol_registered","goal_complete":False,"next_action":"prepare six-year bounded dataset"})


def load_segment(path,start,end):
    start,end=r.utc(start),r.utc(end)
    if start<START or end>END or start>=end:raise ValueError("Invalid or post-2025 data range")
    cols=["open_time","open","high","low","close","volume","quote_volume"]
    df=pd.read_parquet(path,columns=cols,filters=[("open_time",">=",start),("open_time","<",end)])
    df["open_time"]=pd.to_datetime(df.open_time,utc=True)
    if len(df) and not ((df.open_time>=start)&(df.open_time<end)).all():raise AssertionError("Source range breach")
    return df


def validate_frame(parts):
    if not parts:return pd.DataFrame()
    df=pd.concat(parts,ignore_index=True)
    if df.empty:return df.set_index("open_time")
    dup=df.loc[df.duplicated("open_time",keep=False)]
    if len(dup) and (dup.groupby("open_time").nunique()>1).any().any():raise ValueError("Conflicting duplicate candles")
    df=df.drop_duplicates("open_time").set_index("open_time").sort_index()
    assert df.index.min()>=START and df.index.max()<END
    assert np.isfinite(df.to_numpy()).all()
    assert (df.low>0).all() and (df.high>=df.low).all()
    assert (df.high+1e-12>=df[["open","close"]].max(axis=1)).all()
    assert (df.low-1e-12<=df[["open","close"]].min(axis=1)).all()
    assert (df[["volume","quote_volume"]]>=0).all().all()
    return df


def prepare():
    directory=ART/"history"
    if (directory/"DATA_MANIFEST.json").exists():raise FileExistsError("Dataset already prepared")
    (directory/"bars_5m").mkdir(parents=True,exist_ok=True)
    symbols=sorted({p.stem for base in (PRE2024_5M_DIR,r.LAKE) for p in base.glob("*USDT.parquet")})
    months=pd.date_range(START,END-pd.Timedelta(days=1),freq="MS")
    membership={m.strftime("%Y-%m"):[] for m in months};inputs={};skipped=[]
    coverage={str(y):{"symbols_with_bars":0,"complete_hours":0} for y in range(2020,2026)}
    for i,symbol in enumerate(symbols,1):
        parts=[];sources=[]
        for base,start,end in [(PRE2024_5M_DIR,START,JOIN),(r.LAKE,JOIN,END)]:
            path=base/f"{symbol}.parquet"
            if path.exists():
                part=load_segment(path,start,end);parts.append(part)
                sources.append({"path":str(path),"selected_rows":len(part),"start":start.isoformat(),"end_exclusive":end.isoformat()})
        df=validate_frame(parts)
        if df.empty:skipped.append({"symbol":symbol,"reason":"no_rows_through2025"});continue
        hourly=r.h1_frame(df)
        if len(hourly)<200:skipped.append({"symbol":symbol,"reason":"under200_complete_hours"});continue
        path=directory/"bars_5m"/f"{symbol}.parquet";df.to_parquet(path)
        inputs[symbol]={"snapshot_sha256":r.sha(path),"sources":sources,"rows_5m":len(df),"complete_hours":len(hourly),
                        "first_open":df.index.min().isoformat(),"last_open":df.index.max().isoformat()}
        for y in range(2020,2026):
            n=int(np.sum(hourly.index.year==y))
            if n:coverage[str(y)]["symbols_with_bars"]+=1;coverage[str(y)]["complete_hours"]+=n
        for ym,row in r.monthly_rows(symbol,hourly,months).items():membership[ym].append(row)
        if i%30==0:print(f"2020-2025 bounded dataset {i}/{len(symbols)}",flush=True)
    selected={m:sorted(rows,key=lambda x:(-x["median_quote_volume"],x["symbol"]))[:50] for m,rows in membership.items()}
    r.save(directory/"MEMBERSHIP.json",selected)
    for y in range(2020,2026):
        sizes=[len(rows) for month,rows in selected.items() if month.startswith(str(y))]
        sy={row["symbol"] for month,rows in selected.items() if month.startswith(str(y)) for row in rows}
        coverage[str(y)].update(distinct_monthly_members=len(sy),minimum_monthly_members=min(sizes),maximum_monthly_members=max(sizes))
    r.save(directory/"DATA_MANIFEST.json",{"start":START.isoformat(),"end_exclusive":END.isoformat(),"inputs":inputs,"skipped":skipped,
        "yearly_coverage":coverage,"protocol_sha256":r.sha(ART/"PROTOCOL.json"),"membership_sha256":r.sha(directory/"MEMBERSHIP.json"),"post_2025_observations_loaded":0})
    r.save(ART/"PROGRESS.json",{"stage":"six_year_data_prepared","goal_complete":False,"yearly_coverage":coverage,"next_action":"collect causal signals and fixed execution paths"})
    print(json.dumps(coverage),flush=True)


def setup_context():
    r.ART=ART;r.WINDOWS["history"]=("2020-01-01","2026-01-01")


def verify_sources():
    for relative,digest in r.read(ART/"SOURCE_MANIFEST.json").items():
        if r.sha(ROOT/relative)!=digest:raise AssertionError(f"Frozen source changed: {relative}")


def worker(symbol):
    setup_context()
    return r.collect_one("history",symbol)


def collect(workers):
    verify_sources()
    directory=ART/"history";metadata=r.read(directory/"DATA_MANIFEST.json")
    assert metadata["protocol_sha256"]==r.sha(ART/"PROTOCOL.json")
    assert metadata["membership_sha256"]==r.sha(directory/"MEMBERSHIP.json")
    for symbol,record in metadata["inputs"].items():assert r.sha(directory/"bars_5m"/f"{symbol}.parquet")==record["snapshot_sha256"]
    members=r.read(directory/"MEMBERSHIP.json")
    symbols=sorted({row["symbol"] for rows in members.values() for row in rows})
    (directory/"candidates").mkdir(exist_ok=True)
    # Completed per-symbol manifests allow safe resume after interruption.
    resume_path=directory/"COLLECTION_PROGRESS.json"
    fingerprint={"protocol_sha256":r.sha(ART/"PROTOCOL.json"),"source_manifest_sha256":r.sha(ART/"SOURCE_MANIFEST.json"),"data_manifest_sha256":r.sha(directory/"DATA_MANIFEST.json")}
    progress=r.read(resume_path) if resume_path.exists() else {"symbols":{},**fingerprint}
    assert all(progress[k]==v for k,v in fingerprint.items()),"Changed collection dependencies"
    results=progress["symbols"]
    for symbol,row in results.items():assert r.sha(directory/"candidates"/f"{symbol}.pkl.gz")==row["sha256"]
    pending=[s for s in symbols if s not in results]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(worker,s) for s in pending]
        for f in as_completed(futures):
            symbol,count,rejections,digest=f.result()
            results[symbol]={"candidates":count,"rejections":rejections,"sha256":digest}
            r.save(resume_path,{"symbols":results,"completed":len(results),"total":len(symbols),**fingerprint})
            print(f"Six-year signals {len(results)}/{len(symbols)} {symbol}={count}",flush=True)
    r.save(directory/"CANDIDATE_MANIFEST.json",{"symbols":results,"protocol_sha256":r.sha(ART/"PROTOCOL.json"),"source_sha256":r.sha(__file__),"data_manifest_sha256":r.sha(directory/"DATA_MANIFEST.json")})


def linked_summary(nodes,cost):
    equity=100.;curve=[100.];trades=0;gaps=0
    for node in nodes:
        value=node[f"{cost}bps_stress"]
        curve.extend(equity*np.asarray(value["curve_values"])[1:]/100)
        equity*=1+value["return_pct"]/100
        trades+=value["trades"];gaps+=value["accepted_missing_execution_bars"]
    values=np.asarray(curve);dd=float(np.max(1-values/np.maximum.accumulate(values))*100)
    return {"return_pct":equity-100,"max_dd_pct":dd,"trades":trades,"accepted_missing_execution_bars":gaps}


def choose_from_past(annual,test_year):
    past=[str(y) for y in range(2020,test_year)]
    if len(past)<2 or any(y not in annual for y in past):raise ValueError("Need complete earlier years")
    scores=[];audit={}
    for spec in FAMILY:
        vid=spec["id"]
        if vid=="reference_m6_fixed":continue
        nodes=[annual[y][vid] for y in past]
        a,b=linked_summary(nodes,40),linked_summary(nodes,60)
        positive_years=all(n["40bps_stress"]["return_pct"]>0 for n in nodes)
        annual_dd=max(n[f"{c}bps_stress"]["max_dd_pct"] for n in nodes for c in (40,60))
        ok=a["trades"]>=60 and a["return_pct"]>0 and b["return_pct"]>=0 and positive_years and annual_dd<=15 and a["accepted_missing_execution_bars"]==b["accepted_missing_execution_bars"]==0
        audit[vid]={"train_40bps":a,"train_60bps":b,"all_prior_years_positive":positive_years,"max_annual_dd":annual_dd,"eligible":bool(ok)}
        if ok:scores.append((b["return_pct"]-b["max_dd_pct"],vid))
    scores.sort(key=lambda x:(-x[0],x[1]))
    return {"test_year":test_year,"training_years":past,"selected":scores[0][1] if scores else "CASH","audit":audit,"selection_uses_test_year":False}


def evaluate():
    verify_sources()
    setup_context();candidates=r.load_candidates("history")
    if (ART/"RESULTS.json").exists():raise FileExistsError("Six-year results already frozen")
    annual={};locks={};ledgers={}
    sources={s["id"]:transformed(candidates,s) if "hours" in s else candidates for s in FAMILY}
    for year in range(2020,2026):
        completed=ART/f"YEAR_{year}.json"
        ledger_path=ART/f"YEAR_{year}_LEDGERS.json.gz"
        if year>=2022:
            lock=choose_from_past(annual,year)
            p=ART/f"LOCK_TEST_{year}.json"
            if p.exists():
                saved=r.read(p)
                assert all(saved[k]==v for k,v in lock.items()),"Selection changed on resume"
                assert saved["protocol_sha256"]==r.sha(ART/"PROTOCOL.json")
                lock=saved
            else:
                lock["locked_at_utc"]=datetime.now(timezone.utc).isoformat()
                lock["protocol_sha256"]=r.sha(ART/"PROTOCOL.json")
                r.save(p,lock)
            locks[str(year)]=lock
        if completed.exists():
            saved=r.read(completed)
            assert saved["candidate_manifest_sha256"]==r.sha(ART/"history/CANDIDATE_MANIFEST.json")
            assert saved["ledger_sha256"]==r.sha(ledger_path)
            annual[str(year)]=saved["results"]
            with gzip.open(ledger_path,"rt",encoding="utf8") as f:ledgers.update(json.load(f))
            continue
        annual[str(year)]={}
        for spec in FAMILY:
            vid=spec["id"];row={}
            for cost in (40,60):
                result=r.portfolio(sources[vid],spec,f"{year}-01-01",f"{year+1}-01-01",cost,True)
                result["weekly_ci"]=r.block_ci(result["weekly_returns"])
                ledgers[f"{year}/{vid}/{cost}"]={"ledger":result.pop("ledger"),"curve":result.pop("curve")}
                result["curve_values"]=[v for _,v in ledgers[f"{year}/{vid}/{cost}"]["curve"]]
                row[f"{cost}bps_stress"]=result
            annual[str(year)][vid]=row
            a=row["40bps_stress"]
            print(f"{year}/{vid}: N={a['trades']} NAV={a['return_pct']:.3f}% DD={a['max_dd_pct']:.3f}%",flush=True)
        # Stage checkpoint is written only after the complete year's replay.
        with gzip.open(ledger_path,"wt",encoding="utf8") as f:
            json.dump({k:v for k,v in ledgers.items() if k.startswith(f"{year}/")},f,separators=(",",":"),allow_nan=False)
        r.save(completed,{"results":annual[str(year)],"ledger_sha256":r.sha(ledger_path),"candidate_manifest_sha256":r.sha(ART/"history/CANDIDATE_MANIFEST.json")})
    oos={}
    for cost in (40,60):
        selected=[];weeks=[]
        for year in range(2022,2026):
            choice=locks[str(year)]["selected"]
            if choice=="CASH":
                empty={"return_pct":0.,"max_dd_pct":0.,"trades":0,"accepted_missing_execution_bars":0,"curve_values":[100.,100.]}
                selected.append({f"{cost}bps_stress":empty})
                weeks.extend([0.]*len(annual[str(year)]["m6_risk"][f"{cost}bps_stress"]["weekly_returns"]))
            else:
                selected.append(annual[str(year)][choice]);weeks.extend(annual[str(year)][choice][f"{cost}bps_stress"]["weekly_returns"])
        oos[str(cost)]=linked_summary(selected,cost)|{"weekly_ci":r.block_ci(weeks)}
    r.save(ART/"RESULTS.json",{"annual":annual,"walk_forward_locks":locks,"walk_forward_oos":oos,
        "fixed_policy_six_year":{s["id"]:{str(cost):linked_summary([annual[str(y)][s["id"]] for y in range(2020,2026)],cost) for cost in (40,60)} for s in FAMILY},
        "fresh_oos":False,"global_historical_reuse_disclosed":True,"post_2025_observations_loaded":0,"live_signoff":"NOT_GRANTED"})
    with gzip.open(ART/"LEDGERS.json.gz","wt",encoding="utf8") as f:json.dump(ledgers,f,separators=(",",":"),allow_nan=False)
    r.save(ART/"PROGRESS.json",{"stage":"six_year_frozen_policy_and_walk_forward_evaluated","goal_complete":False,"next_action":"independent verification and mini-alpha registry update","live_signoff":"NOT_GRANTED"})


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=["init","prepare","collect","evaluate"]);p.add_argument("--workers",type=int,default=4);a=p.parse_args()
    if a.action=="init":initialize()
    elif a.action=="prepare":prepare()
    elif a.action=="collect":collect(a.workers)
    else:evaluate()
