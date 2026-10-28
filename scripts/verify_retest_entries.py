"""Independent watch oracle, entry prefixes and marked account audits."""

import json
import math
import numpy as np
import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import audit_account,utilization
from compare_account_risk import ROOT,exchange_rules,sha,write
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from prepare_frozen_extension import FREEZE
from search_retest_entries import OUT,PRIOR,DATA,WINDOWS,BOUNDARIES,COSTS,definitions,select,prepare_entries,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from short_retest_entries import definitions as timings,transform
from short_entry_guards import features
from short_guard_ablation import decisions,apply_mask
from short_multitimeframe_signals import generate
from short_event_study import outcomes,statistics
from dao_vang.config.settings import ExecutionConfig


def oracle(signal,quotes,end,spec):
    """Array-based earliest three-stage trigger, independent of state machine."""
    origin=signal["at"];atr=signal["atr"];anchor=quotes.get(origin,{}).get("execution_close",math.nan)
    if not all(math.isfinite(x) and x>0 for x in [anchor,atr]):return "missing_data",None
    expiry=origin+int(spec["ttl_hours"]*3600000)
    ts=list(range(origin+300000,min(expiry,end-300000)+1,300000))
    values=np.array([quotes.get(t,{}).get("execution_close",math.nan) for t in ts])
    missing=np.flatnonzero(~np.isfinite(values)|(values<=0));limit=int(missing[0]) if len(missing) else len(values)
    v=values[:limit];status="missing_data" if len(missing) else ("end_pending" if expiry>=end else "expired")
    down=np.flatnonzero(v<=anchor-spec["down_atr"]*atr)
    if not len(down):return status,None
    d=int(down[0]);after=v[d:];low=np.minimum.accumulate(after)
    bounces=np.flatnonzero(after>=low+spec["bounce_atr"]*atr)
    if not len(bounces):return status,None
    b=d+int(bounces[0]);after=v[b:];peak=np.maximum.accumulate(after)
    drops=np.flatnonzero((after[1:]<after[:-1])&(after[1:]<=peak[:-1]-spec["fall_atr"]*atr))
    if not len(drops):return status,None
    hit=b+int(drops[0])+1
    return "triggered",dict(trigger_at=ts[hit],down_at=ts[d],bounce_at=ts[b],anchor=anchor,
        recovery_low=float(np.min(v[d:b+1])),recovery_peak=float(np.max(v[b:hit])),trigger_close=float(v[hit]))


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));p=s["protocol"]
    assert sha(ROOT/"configs/live.yaml")==p["live_config_sha256"]
    assert sha(PRIOR/"summary.json")==p["prior_sha256"] and sha(DATA/"reconciled_manifest.json")==p["data_sha256"]
    assert sha(DATA/"evaluation/signals.json")==p["signals_sha256"]
    for n,d in p["source_sha256"].items():assert sha(ROOT/"scripts"/n)==d
    assert definitions(json.loads((PRIOR/"summary.json").read_text(encoding="utf-8")))==s["specs"]
    prices,funding,frames=load();enriched=features(frames,funding);rules=exchange_rules(RULE_PATH)
    freeze=json.loads(FREEZE.read_text(encoding="utf-8"));signals=generate(frames,[freeze["source"]])[freeze["source"]["id"]]
    assert signals==json.loads((DATA/"evaluation/signals.json").read_text(encoding="utf-8"))
    sources={e["event_id"]:e for e in signals};cache={};oracle_count=0;screens=json.loads((OUT/"screens.json").read_text(encoding="utf-8"));screen_count=0
    for window,(_,end) in WINDOWS.items():
        prepared=prepare_entries(signals,prices,enriched,window)
        for (timing,mask),item in prepared.items():
            saved=json.loads((OUT/"entries"/f"{window}_mask{mask:02d}_{timing}.json").read_text(encoding="utf-8"));assert item==saved
            cache[(window,timing,mask)]=saved
            for r in saved["observations"]:
                if r["status"]=="observed":assert 0<=r["at"]-r["feature_at"]<3600000
            spec=next(t for t in timings() if t["id"]==timing)
            if mask==0 and spec["mode"]=="retest":
                for e in saved["watch"]["events"]:
                    status,details=oracle(sources[e["event_id"]],prices[e["symbol"]],end,spec)
                    assert e["status"]==status
                    if details:
                        assert all(e[k]==v for k,v in details.items())
                        assert e["original_at"]<e["down_at"]<e["bounce_at"]<e["trigger_at"]<end
                    oracle_count+=1
            for h in [4,24]:
                events,counts=outcomes(item["entries"],prices,funding,*WINDOWS[window],h)
                row=next(r for r in screens if (r["window"],r["timing"],r["mask"],r["hours"])==(window,timing,mask,h))
                assert counts==row["counts"]
                assert {c:statistics(events,*WINDOWS[window],fee,slip) for c,fee,slip in COSTS}==row["cases"];screen_count+=1
    cut=BOUNDARIES[4];prefixes=0
    for timing in timings():
        es,_=transform(signals,prices,WINDOWS["year"][0],cut,timing)
        observations=decisions(es,{c:f[f.index<pd.Timestamp(cut,unit="ms",tz="UTC")] for c,f in enriched.items()})
        for mask in [0,2]:
            accepted,_=apply_mask(es,observations,mask)
            assert accepted==[e for e in cache[("year",timing["id"],mask)]["entries"] if e["at"]<cut];prefixes+=1
    print("WATCHES",oracle_count,"PREFIXES",prefixes,"SCREENS",screen_count,flush=True)
    baseline_count=0;incomplete=[]
    for row in s["results"]:
        raw=json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"));curve=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet")
        start,end=WINDOWS[row["window"]];assert raw["initial_equity"]==500 and curve["at"].iloc[0]==start
        audit_account(raw,row["notional"]);assert utilization(curve,raw,row["notional"])==row["utilization"]
        assert exit_diagnostics(raw)==row["exit_diagnostics"]
        assert monthly_metrics(curve.to_dict("records"),boundaries=[t for t in BOUNDARIES if start<=t<=end])==row["monthly"]
        assert abs(sum(j.get("net",0) for j in raw["journal"])-raw["closed_trade_net"])<1e-7
        assert abs(sum(j["amount"] for j in raw["journal"] if j["kind"]=="funding")-raw["funding"])<1e-7
        fee=next(f for c,f,_ in COSTS if c==row["cost"]);fees=0.;qty={}
        allowed={e["event_id"]:e for e in cache[(row["window"],row["timing"]["id"],row["mask"])]["entries"]}
        for j in raw["journal"]:
            if j["kind"]=="entry":assert j["at"]==allowed[j["event_id"]]["at"]
            if j["kind"] in ["entry","entry_add"]:
                qty[j["event_id"]]=qty.get(j["event_id"],0)+j["qty"];fees+=j["qty"]*j["price"]*fee
            elif "net" in j:fees+=qty.pop(j["event_id"])*j["price"]*fee
        assert abs(fees-raw["fees"])<1e-7
        if curve.paused.any():
            first=curve.loc[curve.paused,"at"].iloc[0];assert curve.loc[curve["at"]>=first,"paused"].all()
            assert not any(j["kind"] in ["entry","entry_add"] and j["at"]>first for j in raw["journal"])
        if raw["ending_equity"] is None:
            assert raw["errors"] and not row["target_met"] and not row["monthly"]["complete"]
            incomplete.append(dict(id=row["id"],stop_event=raw["stop_event"],errors=raw["errors"]))
        else:assert curve["at"].iloc[-1]==end and abs(curve["equity"].iloc[-1]-raw["ending_equity"])<1e-7
        if row["baseline"]:
            key=f"{row['window']}_{row['cost']}_{row['reference_id']}"
            assert raw==json.loads((PRIOR/"runs"/f"{key}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(PRIOR/"runs"/f"{key}_equity.parquet"),check_exact=True);baseline_count+=1
    assert select(s["specs"],s["results"])==s["selected"]==json.loads((OUT/"candidate_lock.json").read_text(encoding="utf-8"))["selected"]
    print("AUDITED",len(s["results"]),"BASELINES",baseline_count,flush=True)
    specs={r["id"]:r for r in s["specs"]};exact=0
    replay_ids=set(s["selected"])|{"mask02_n25_retest_d0.5_b0.5_ttl6","mask02_n25_retest_d0.25_b0.25_ttl24"}
    for ident in sorted(replay_ids):
        spec=specs[ident];start,end=WINDOWS["year"];es=cache[("year",spec["timing"]["id"],spec["mask"])]["entries"]
        for cost,fee,slip in COSTS:
            r=simulate(list(range(start,end+1,300000)),grouped_signals(es,start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
            r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct";key=f"year_{cost}_{ident}"
            assert {k:v for k,v in r.items() if k!="curve"}==json.loads((OUT/"runs"/f"{key}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(pd.DataFrame(r["curve"]),pd.read_parquet(OUT/"runs"/f"{key}_equity.parquet"),check_exact=True);exact+=1
    write(OUT/"verification.json",dict(journals_audited=len(s["results"]),baseline_paths_exact=baseline_count,replayed_paths_exact=exact,
        independent_watch_oracle_checked=oracle_count,entry_prefixes_exact=prefixes,event_screens_recomputed=screen_count,
        regenerated_signal_source_exact=True,locked_selection_reproduced=True,incomplete_paths=incomplete,source_hashes_match=True,data_hashes_match=True,live_config_unchanged=True))
    print("VERIFIED",flush=True)


if __name__=="__main__":main()
