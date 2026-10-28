"""Reconcile bounded inputs, retrospective selection and independent cash events."""
import argparse
from collections import defaultdict
import gzip
import json
import pickle
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import research_v408 as q

r=q.r
ART=q.ART


def close(a,b,tol=1e-8):
    if not np.allclose(a,b,atol=tol,rtol=0):raise AssertionError(f"Reconciliation mismatch: {a} != {b}")


def inputs():
    q.verify_sources()
    old=r.read(ART/"PRESERVED_PREVIOUS_CHECKPOINT.json")
    from pathlib import Path
    previous=Path(old["path"])
    assert r.sha(previous)==old["sha256"]
    prior=r.read(previous)
    for relative,digest in prior["files"].items():assert r.sha(previous.parent/relative)==digest,relative
    protected=r.read(previous.parent/"HISTORICAL_PRESERVATION.json")
    for relative,digest in protected.items():assert r.sha(r.ROOT/relative)==digest,relative
    folder=ART/"history";manifest=r.read(folder/"DATA_MANIFEST.json")
    assert manifest["protocol_sha256"]==r.sha(ART/"PROTOCOL.json")
    assert manifest["membership_sha256"]==r.sha(folder/"MEMBERSHIP.json")
    months=pd.date_range(q.START,q.END-pd.Timedelta(days=1),freq="MS")
    recomputed={m.strftime("%Y-%m"):[] for m in months}
    total=0;count=0
    for symbol,record in manifest["inputs"].items():
        path=folder/"bars_5m"/f"{symbol}.parquet"
        assert r.sha(path)==record["snapshot_sha256"],symbol
        f=pd.read_parquet(path)
        assert len(f)==record["rows_5m"] and f.index.is_unique and f.index.is_monotonic_increasing
        assert f.index.min()>=q.START and f.index.max()<q.END
        assert f.index.min().isoformat()==record["first_open"] and f.index.max().isoformat()==record["last_open"]
        assert np.isfinite(f.to_numpy()).all() and (f.low>0).all()
        assert (f.high>=f.low).all() and (f[["volume","quote_volume"]]>=0).all().all()
        assert (f.high+1e-12>=f[["open","close"]].max(axis=1)).all()
        assert (f.low-1e-12<=f[["open","close"]].min(axis=1)).all()
        total+=len(f);count+=1
        h=r.h1_frame(f)
        assert len(h)==record["complete_hours"]
        if symbol not in r.EXCLUDE:
            # Rebuild the calendar candidates from each historical prefix.
            # This deliberately never calls monthly_rows().
            daily=h.quote_volume.resample("1D").sum()
            h4=r.resample_1h_to_htf(h,"4h")
            for month in months:
                lower=month-pd.Timedelta(days=63)
                d=daily[(daily.index>=lower)&(daily.index<month)]
                d=d[d>0]
                bars=h4[(h4.index>=lower)&(h4.close_time<=month)]
                if len(d)<50 or len(bars)<10:continue
                wick=(bars.high-bars[["open","close"]].max(axis=1))/bars.close*100
                p90=float(np.quantile(wick,.9))
                if p90>3.2:continue
                recomputed[month.strftime("%Y-%m")].append({"symbol":symbol,"median_quote_volume":float(np.median(d)),"active_days":len(d),"wick_p90_pct":p90})
        if count%40==0:print(f"Independent input/PIT check {count}/{len(manifest['inputs'])}",flush=True)
    expected=r.read(folder/"MEMBERSHIP.json");checks=0
    for month,rows in recomputed.items():
        top=sorted(rows,key=lambda x:(-x["median_quote_volume"],x["symbol"]))[:50]
        assert [x["symbol"] for x in top]==[x["symbol"] for x in expected[month]],month
        for a,b in zip(top,expected[month]):
            assert a["active_days"]==b["active_days"]
            close(a["median_quote_volume"],b["median_quote_volume"])
            close(a["wick_p90_pct"],b["wick_p90_pct"])
            checks+=1
    output={"all_checks_passed":True,"bounded_snapshots":count,"bars_5m":total,"monthly_rankings":len(months),"monthly_members_verified":checks,
        "previous_checkpoint_files_preserved":len(prior["files"]),"older_files_preserved":len(protected),"post_2025_observations_loaded":0,
        "data_manifest_sha256":r.sha(folder/"DATA_MANIFEST.json"),"source_manifest_sha256":r.sha(ART/"SOURCE_MANIFEST.json")}
    r.save(ART/"INPUT_VERIFICATION.json",output)
    print(json.dumps(output),flush=True)


def results():
    q.verify_sources();q.setup_context()
    verified=r.read(ART/"INPUT_VERIFICATION.json")
    assert verified["all_checks_passed"]
    assert verified["data_manifest_sha256"]==r.sha(ART/"history/DATA_MANIFEST.json")
    assert verified["source_manifest_sha256"]==r.sha(ART/"SOURCE_MANIFEST.json")
    summary=r.read(ART/"RESULTS.json")
    assert not summary["fresh_oos"] and summary["global_historical_reuse_disclosed"]
    membership=r.read(ART/"history/MEMBERSHIP.json")
    all_candidates=r.load_candidates("history")
    candidates={c["id"]:c for c in all_candidates}
    assert len(candidates)==len(all_candidates)
    for c in candidates.values():
        assert c["entry_ts"]==c["decision_ts"]+300
        t=pd.Timestamp(c["entry_ts"],unit="s",tz="UTC")
        assert q.START<=t<q.END
        decision=pd.Timestamp(c["decision_ts"],unit="s",tz="UTC")
        assert c["symbol"] in {x["symbol"] for x in membership[decision.strftime("%Y-%m")]}
        assert c["stop"]>c["entry"]>c["targets"][0]>c["targets"][1]>c["targets"][2]>0
        for path in c["paths"].values():
            trace=path["trace"]
            assert trace and trace[-1][0]==path["exit_ts"]<=int(q.END.timestamp())
            assert trace[-1][3]==0 and trace[-1][6]
            assert all(c["entry_ts"]<x[0]<=path["exit_ts"] for x in trace)
            close(sum(x[5] for x in trace),path["gross_return"])
    transformed={s["id"]:{c["id"]:c for c in q.transformed(all_candidates,s)} if "hours" in s else candidates for s in q.FAMILY}
    with gzip.open(ART/"LEDGERS.json.gz","rt",encoding="utf8") as f:ledgers=json.load(f)
    count=0;records=0
    for key,node in ledgers.items():
        year,vid,cost=key.split("/");cost=int(cost)
        metric=summary["annual"][year][vid][f"{cost}bps_stress"]
        rows=node["ledger"];curve=np.asarray(node["curve"],dtype=float)
        a=int(r.utc(f"{year}-01-01").timestamp());b=int(r.utc(f"{int(year)+1}-01-01").timestamp())
        events=defaultdict(float);events[a]=0.;events[b]=0.
        assert len({p["id"] for p in rows})==len(rows)==metric["trades"]
        assert (np.diff(curve[:,0])>=0).all() and curve[0,0]==a and curve[-1,0]==b
        for trade in rows:
            c=transformed[vid][trade["id"]];path=c["paths"]["ladder"]
            assert a<=trade["entry_ts"]<b-5*86400 and trade["exit_ts"]<=b
            assert trade["entry_ts"]==c["entry_ts"] and trade["exit_ts"]==path["exit_ts"]
            close(trade["qty"]*trade["entry"],trade["notional"])
            close(trade["fees"],trade["notional"]*cost/10000)
            close(trade["gross_return"],path["gross_return"])
            expected_funding=0.
            events[trade["entry_ts"]]-=trade["fees"]/2
            for t,mark,rem_start,rem_end,stop,delta,done in path["trace"]:
                funding=-trade["qty"]*rem_start*mark*.0001 if t%(8*3600)==0 and trade["entry_ts"]<t else 0.
                expected_funding+=funding
                events[t]+=trade["notional"]*delta+funding-(trade["fees"]/2 if done else 0.)
            close(trade["funding"],expected_funding)
            close(trade["pnl"],trade["notional"]*path["gross_return"]-trade["fees"]+expected_funding)
            if vid!="reference_m6_fixed":
                risk=trade["qty"]*(trade["stop"]-trade["entry"])+.006*trade["notional"]
                assert risk<=.005*trade["equity_at_entry"]+1e-8
        # Independent additive cash events reconstruct every observed timestamp.
        times=sorted(events);cash=100+np.cumsum([events[t] for t in times])
        observed=pd.Series(curve[:,1],index=curve[:,0]).groupby(level=0).last()
        assert times==observed.index.tolist()
        close(cash,observed.to_numpy())
        close(cash[-1]-100,metric["return_pct"])
        close(100+sum(x["pnl"] for x in rows),cash[-1])
        close(np.max(1-curve[:,1]/np.maximum.accumulate(curve[:,1]))*100,metric["max_dd_pct"])
        close(sum(x["fees"] for x in rows),metric["fees_pct_initial"])
        close(sum(x["funding"] for x in rows),metric["funding_pct_initial"])
        assert sum(x["missing_execution_bars"] for x in rows)==metric["accepted_missing_execution_bars"]
        close(curve[:,1],metric["curve_values"])
        count+=1;records+=len(rows)
    locks={}
    for year in range(2022,2026):
        computed=q.choose_from_past(summary["annual"],year)
        lock=r.read(ART/f"LOCK_TEST_{year}.json")
        assert all(lock[k]==v for k,v in computed.items())
        assert lock==summary["walk_forward_locks"][str(year)]
        locks[str(year)]=lock["selected"]
    for cost in (40,60):
        for vid,aggregate in summary["fixed_policy_six_year"].items():
            nodes=[summary["annual"][str(y)][vid] for y in range(2020,2026)]
            calculated=q.linked_summary(nodes,cost)
            assert calculated==aggregate[str(cost)]
        nav=100.;curve=[100.];trades=0;weeks=[]
        for year in range(2022,2026):
            choice=locks[str(year)]
            if choice=="CASH":
                weeks.extend([0.]*len(summary["annual"][str(year)]["m6_risk"][f"{cost}bps_stress"]["weekly_returns"]))
                continue
            node=summary["annual"][str(year)][choice][f"{cost}bps_stress"]
            curve.extend(nav*np.asarray(node["curve_values"])[1:]/100)
            nav*=1+node["return_pct"]/100
            trades+=node["trades"];weeks.extend(node["weekly_returns"])
        out=summary["walk_forward_oos"][str(cost)]
        close(out["return_pct"],nav-100)
        close(out["max_dd_pct"],np.max(1-np.asarray(curve)/np.maximum.accumulate(curve))*100)
        assert trades==out["trades"] and out["weekly_ci"]==r.block_ci(weeks)
    test_counts=defaultdict(int)
    for filename in ("ALL_TESTS.xml","CONTRACT_TESTS.xml"):
        for suite in ET.parse(ART/filename).getroot().iter("testsuite"):
            for k in ("tests","failures","errors","skipped"):test_counts[k]+=int(suite.attrib.get(k,0))
    assert test_counts["failures"]==test_counts["errors"]==test_counts["skipped"]==0
    out={"all_checks_passed":True,"input_verification_sha256":r.sha(ART/"INPUT_VERIFICATION.json"),"results_sha256":r.sha(ART/"RESULTS.json"),
        "ledgers_sha256":r.sha(ART/"LEDGERS.json.gz"),"causal_candidates_checked":len(candidates),"ledger_nodes_verified":count,
        "scenario_trade_records_verified":records,"chronological_locks":locks,"tests":dict(test_counts),
        "post_2025_observations_loaded":0,"fresh_oos":False,"live_signoff":"NOT_GRANTED","goal_complete":False}
    r.save(ART/"INDEPENDENT_VERIFICATION.json",out)
    print(json.dumps(out),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=["inputs","results"]);a=p.parse_args()
    inputs() if a.action=="inputs" else results()
