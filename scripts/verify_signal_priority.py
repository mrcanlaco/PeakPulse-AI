"""Causal feature audit, event-preserving queues and exact prior account controls."""
import json
import math
import xml.etree.ElementTree as ET
import pandas as pd
from account_side_quota_replay import simulate
from capital_research_metrics import audit_account,utilization
from compare_account_risk import ROOT,sha,write,exchange_rules
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from research_directional_audit import audit_directional
from search_signal_priority import OUT,PRIOR,SOURCE,DATA,BOUNDARIES,COSTS,definitions,select,windows,robustness,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from short_multitimeframe_signals import features
from short_signal_priority import RANKS,observe,rank,collisions


def main():
    s=json.loads((OUT/"summary.json").read_text());p=s["protocol"]
    assert sha(ROOT/"configs/live.yaml")==p["live_config_sha256"] and sha(RULE_PATH)==p["rules_sha256"]
    assert sha(DATA/"reconciled_manifest.json")==p["data_sha256"] and sha(PRIOR/"summary.json")==p["prior_sha256"] and sha(SOURCE)==p["signals_sha256"]
    for n,d in p["source_sha256"].items():assert sha(ROOT/"scripts"/n)==d
    assert definitions(json.loads((PRIOR/"summary.json").read_text()))==s["specs"]
    assert select(s["specs"],s["results"])==s["selected"]==json.loads((OUT/"candidate_lock.json").read_text())["selected"]
    assert robustness(s["results"])==s["robustness"]
    tests=ET.parse(ROOT/"tmp/signal_priority_tests.xml").getroot().find("testsuite")
    assert int(tests.attrib["tests"])==95 and int(tests.attrib["failures"])==int(tests.attrib["errors"])==0
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);frozen=json.loads(SOURCE.read_text())["short_mask2"]
    observations=observe(frozen,frames,funding);signals=rank(frozen,observations)
    assert observations==json.loads((OUT/"observations.json").read_text()) and signals==json.loads((OUT/"signals.json").read_text())
    assert collisions(frozen)==p["collisions"]
    four={c:features(f) for c,f in frames.items() if c!="BTCUSDT"}
    for event,obs in zip(frozen,observations):
        c=event["symbol"];t=pd.Timestamp(event["at"],unit="ms",tz="UTC");bars=four[c].loc[:t];hour=frames[c].loc[:t]
        rs=list(bars.tail(15).itertuples());bar=rs[-1];atr=sum(max(b.high-b.low,abs(b.high-a.close),abs(b.low-a.close)) for a,b in zip(rs,rs[1:]))/14
        assert len(rs)==15 and math.isclose(atr,event["atr"],rel_tol=1e-12,abs_tol=1e-9)
        ret24=bars.close.iloc[-1]/bars.close.iloc[-7]-1;ret6=hour.close.iloc[-1]/hour.close.iloc[-7]-1
        asof=event["at"]-60000
        known=[(at,rate) for at,rate,mark in funding[c] if at<=asof]
        assert known and asof-known[-1][0]<=8*3600000+300000 and known[0][0]<=asof-86400000
        carry=round(math.fsum(rate for at,rate in known if at>asof-86400000),12)
        expected=dict(zscore=event["probability"],impulse_atr=abs(ret24)/(atr/bar.close),low_vol=-atr/bar.close,
            liquidity=math.fsum(bars.quote_volume.iloc[-6:]),funding24=carry,weak6=-ret6,body_atr=(bar.open-bar.close)/atr)
        for k,v in expected.items():assert math.isclose(v,obs["scores"][k],rel_tol=1e-11,abs_tol=1e-10),(c,t,k,v,obs["scores"][k])
    fixed={r["event_id"]:{k:v for k,v in r.items() if k!="probability"} for r in frozen}
    changes={}
    for key,rows in signals.items():
        assert {r["event_id"]:{k:v for k,v in r.items() if k!="probability"} for r in rows}==fixed
        assert len(rows)==len(fixed)==497
        assert rows==sorted(rows,key=lambda r:(r["at"],-r["probability"],r["symbol"]))
        base_groups=grouped_signals(frozen,-10**18,10**18);new_groups=grouped_signals(rows,-10**18,10**18)
        changes[key]=sum([r["event_id"] for r in base_groups[t]]!=[r["event_id"] for r in new_groups[t]] for t in base_groups)
    assert signals["zscore"]==frozen
    prefixes=0
    for cut in ["2025-11-15 13:00","2026-03-01 17:00","2026-07-15 10:00"]:
        t=pd.Timestamp(cut,tz="UTC");ms=int(t.timestamp()*1000);events=[e for e in frozen if e["at"]<=ms]
        obs=observe(events,{c:f.loc[:t] for c,f in frames.items()},{c:[r for r in rows if r[0]<=ms] for c,rows in funding.items()})
        for key,rows in rank(events,obs).items():
            assert rows==[r for r in signals[key] if r["at"]<=ms];prefixes+=1
    print("SIGNALS",len(frozen),"PREFIXES",prefixes,"REORDERED",changes,flush=True)
    specs={sp["id"]:sp for sp in s["specs"]};baselines=fc=fills=states=0;incomplete=[]
    for i,row in enumerate(s["results"],1):
        sp=specs[row["strategy_id"]];start,end=windows()[row["window"]];_,fee,slip=next(c for c in COSTS if c[0]==row["cost"])
        raw=json.loads((OUT/"runs"/f"{row['id']}.json").read_text());curve=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet")
        assert curve["at"].iloc[0]==start and raw["initial_equity"]==500 and curve.positions.max()<=sp["cap"]
        audit_account(raw,25,sp["cap"]);assert utilization(curve,raw,25,sp["cap"])==row["utilization"]
        assert exit_diagnostics(raw)==row["exit_diagnostics"]
        assert row["monthly"]==monthly_metrics(curve.to_dict("records"),boundaries=[t for t in BOUNDARIES if start<=t<=end])
        assert row["target_met"]==(raw["ending_equity"] is not None and row["monthly"]["all_months_50pct"])
        assert all(j["side"]=="SHORT" for j in raw["journal"])
        a,b,c=audit_directional(raw,curve,prices,funding,fee,slip,sp["cap"],25);fc+=a;fills+=b;states+=c
        if raw["ending_equity"] is None:
            assert raw["errors"];incomplete.append(dict(id=row["id"],errors=raw["errors"],stop_event=raw["stop_event"]))
        else:assert curve["at"].iloc[-1]==end and abs(curve.equity.iloc[-1]-raw["ending_equity"])<1e-8
        if curve.paused.any():
            first=curve.loc[curve.paused,"at"].iloc[0];assert curve.loc[curve["at"]>=first,"paused"].all()
            assert not any(j["kind"] in ["entry","entry_add"] and j["at"]>first for j in raw["journal"])
        if sp["baseline"]:
            root=PRIOR if sp["cap"]==5 else PRIOR/"long_contribution_control"
            key=f"{row['window']}_{row['cost']}_"+("short_control" if sp["cap"]==5 else "short_only3")
            assert raw==json.loads((root/"runs"/f"{key}.json").read_text()),row["id"]
            pd.testing.assert_frame_equal(curve,pd.read_parquet(root/"runs"/f"{key}_equity.parquet"),check_exact=True);baselines+=1
        if i%56==0:print("AUDIT",i,"/",len(s["results"]),flush=True)
    cases={(r["strategy_id"],"later") for r in s["selected"] if r["strategy_id"]}
    cases|={("funding24_cap5","year"),("low_vol_cap3","roll_2025_11")}
    exact=0
    for ident,window in sorted(cases):
        sp=specs[ident];start,end=windows()[window]
        for cost,fee,slip in COSTS:
            r=simulate(list(range(start,end+1,300000)),grouped_signals(signals[sp["ranking"]],start,end),lambda c:prices.get(c,{}),rules,
                lambda c:funding[c],configuration(5,fee,slip),research_policy=sp["policy"])
            r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct";key=f"{window}_{cost}_{ident}"
            assert {k:v for k,v in r.items() if k!="curve"}==json.loads((OUT/"runs"/f"{key}.json").read_text())
            pd.testing.assert_frame_equal(pd.DataFrame(r["curve"]),pd.read_parquet(OUT/"runs"/f"{key}_equity.parquet"),check_exact=True);exact+=1
    write(OUT/"verification.json",dict(journals_audited=len(s["results"]),baseline_paths_exact=baselines,replayed_paths_exact=exact,
        independent_event_features=497,causal_prefixes=prefixes,reordered_timestamps=changes,
        funding_quantities_checked=fc,directional_fills_checked=fills,equity_states_reconstructed=states,
        incomplete_paths=incomplete,hashes_match=True,live_config_unchanged=True,unit_tests_passed=95,
        junit_sha256=sha(ROOT/"tmp/signal_priority_tests.xml")))
    print("VERIFIED",flush=True)


if __name__=="__main__":main()
