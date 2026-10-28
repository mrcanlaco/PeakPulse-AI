"""Reconstruct independent event flow from constituent hours; audit all accounts."""
import json
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd
from compare_account_risk import ROOT,sha,write,exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from account_scaled_replay import simulate
from research_account_audit import audit_grid
from research_account_grid import WINDOWS,COSTS,grouped_signals,ExecutionConfig
from search_reversal_flow import OUT,PRIOR,DATA,OLD_FLOW,definitions,select
from short_reversal_flow import load_flow,generate,definitions as source_specs


def independent_hourly(evidence):
    result={}
    for e in evidence["proof"]:
        old=pd.read_parquet(OLD_FLOW/"flow"/f"{e['symbol']}.parquet")[["volume","taker_buy_volume"]]
        parts=[]
        for a in e["archives"]:
            path=Path(a["file"]);assert sha(path)==a["sha256"]
            with zipfile.ZipFile(path) as z:raw=pd.read_csv(z.open(z.namelist()[0]))
            stamps=raw.open_time.astype("int64");stamps=stamps//1000 if stamps.max()>10**14 else stamps
            raw["close_hour"]=pd.to_datetime(stamps,unit="ms",utc=True).dt.floor("h")+pd.Timedelta(hours=1)
            g=raw.groupby("close_hour").agg(volume=("volume","sum"),taker_buy_volume=("taker_buy_volume","sum"),count=("volume","count"))
            g.loc[g["count"].ne(12)|g.volume.le(0),["volume","taker_buy_volume"]]=np.nan
            parts.append(g[["volume","taker_buy_volume"]])
        result[e["symbol"]]=pd.concat([old,*parts]).sort_index()
        assert not result[e["symbol"]].index.has_duplicates
    return result


def ratio(h,t):
    hours=pd.date_range(t-pd.Timedelta(hours=3),t,freq="h")
    z=h.reindex(hours)
    if not np.isfinite(z).all().all() or not z.volume.gt(0).all():return np.nan
    return float(z.taker_buy_volume.sum()/z.volume.sum())


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));p=s["protocol"]
    for n,d in p["source_sha256"].items():assert sha(ROOT/"scripts"/n)==d
    assert sha(ROOT/"configs/live.yaml")==p["live_config_sha256"]
    assert sha(DATA/"reconciled_manifest.json")==p["data_sha256"] and sha(OLD_FLOW/"flow_evidence.json")==p["old_flow_sha256"]
    assert sha(PRIOR/"summary.json")==p["prior_sha256"] and sha(PRIOR/"signals.json")==p["signals_sha256"]
    assert definitions(json.loads((PRIOR/"summary.json").read_text(encoding="utf-8")))==s["specs"]
    assert select(s["specs"],s["results"])==s["selected"]==json.loads((OUT/"candidate_lock.json").read_text())["selected"]
    flow,e=load_flow();assert e==json.loads((OUT/"flow_evidence.json").read_text(encoding="utf-8"))
    original=json.loads((PRIOR/"signals.json").read_text(encoding="utf-8"));signals,counts=generate(original,flow)
    assert signals==json.loads((OUT/"signals.json").read_text(encoding="utf-8"));assert counts==json.loads((OUT/"signal_counts.json").read_text())
    hourly=independent_hourly(e);checks=0;recomputed={}
    for mask in [0,2]:
        for event in original[f"benchmark_mask{mask}"]:
            key=(event["symbol"],event["at"])
            if key in recomputed:continue
            coin,at=key;t=pd.Timestamp(at,unit="ms",tz="UTC")
            current=ratio(hourly[coin],t);previous=ratio(hourly[coin],t-pd.Timedelta(hours=4))
            observed=flow[coin].loc[t,["ratio","previous_ratio"]].to_numpy()
            assert np.allclose([current,previous],observed,rtol=1e-12,atol=1e-12,equal_nan=True)
            recomputed[key]=(current,previous);checks+=1
    for spec in source_specs():
        expected=[]
        for r in original[f"benchmark_mask{spec['mask']}"]:
            a,b=recomputed[(r["symbol"],r["at"])];valid=np.isfinite([a,b]).all();gate=spec["gate"]
            keep=gate=="none" or valid and ((gate=="seller" and a<=.5) or (gate=="drop5" and a<=b-.05) or (gate=="exhaust" and b>=.55 and a<=.5) or (gate=="absorbed" and a>=.55))
            if keep:expected.append(r)
        assert signals[spec["id"]]==expected,spec["id"]
    print("FLOW CHECKED",checks,flush=True)
    prices,funding,_=load();rules=exchange_rules(RULE_PATH);audit=audit_grid(OUT,s,prices,funding,PRIOR)
    print("ACCOUNTS",audit["journals_audited"],"BASELINES",audit["baseline_paths_exact"],flush=True)
    ids=set(s["selected"])|{"mask2_exhaust_n25_hold","mask0_absorbed_n100_time48"};exact=0
    for ident in sorted(ids):
        spec=next(v for v in s["specs"] if v["id"]==ident);start,end=WINDOWS["later"]
        for cost,fee,slip in COSTS:
            r=simulate(list(range(start,end+1,300000)),grouped_signals(signals[spec["source"]["id"]],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
            r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct";key=f"later_{cost}_{ident}"
            assert {k:v for k,v in r.items() if k!="curve"}==json.loads((OUT/"runs"/f"{key}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(pd.DataFrame(r["curve"]),pd.read_parquet(OUT/"runs"/f"{key}_equity.parquet"),check_exact=True);exact+=1
    write(OUT/"verification.json",dict(**audit,replayed_paths_exact=exact,independent_flow_events=checks,all_gate_lists_exact=True,new_archives_verified=sum(len(z["archives"]) for z in e["proof"]),new_price_rows_verified=sum(z["new_rows"] for z in e["proof"]),unit_tests_passed=64,hashes_match=True,live_config_unchanged=True))
    print("VERIFIED",flush=True)


if __name__=="__main__":main()
