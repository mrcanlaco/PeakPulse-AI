"""Account, fixed-side allocation, frozen baseline and start-window audits."""
import json
import xml.etree.ElementTree as ET
import pandas as pd
from account_side_quota_replay import simulate
from capital_research_metrics import audit_account,utilization
from compare_account_risk import ROOT,sha,write,exchange_rules
from directional_capacity_metrics import side_metrics
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from research_directional_audit import audit_directional
from search_side_capacity import OUT,PRIOR,DATA,ORIGINAL_WINDOWS,BOUNDARIES,COSTS,REFERENCES,definitions,select,windows,robustness,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));p=s["protocol"]
    assert sha(ROOT/"configs/live.yaml")==p["live_config_sha256"] and sha(RULE_PATH)==p["rules_sha256"]
    assert sha(DATA/"reconciled_manifest.json")==p["data_sha256"] and sha(PRIOR/"summary.json")==p["prior_sha256"] and sha(PRIOR/"signals.json")==p["signals_sha256"]
    for name,digest in p["source_sha256"].items():assert sha(ROOT/"scripts"/name)==digest
    previous=json.loads((PRIOR/"summary.json").read_text(encoding="utf-8"));assert definitions(previous)==s["specs"]
    assert select(s["specs"],s["results"])==s["selected"]==json.loads((OUT/"candidate_lock.json").read_text())["selected"]
    assert robustness(s["results"])==s["robustness"]
    spans=windows();assert {k:list(v) for k,v in spans.items()}==p["windows"]
    roll=[v for k,v in spans.items() if k=="later" or k.startswith("roll_")]
    assert len(roll)==len(set(roll))==10
    for start,end in roll:
        a=pd.Timestamp(start,unit="ms",tz="UTC");b=pd.Timestamp(end,unit="ms",tz="UTC")
        assert a.day==1 and b==a+pd.DateOffset(months=3)
    tests=ET.parse(ROOT/"tmp/side_capacity_tests.xml").getroot().find("testsuite")
    assert tests is not None and int(tests.attrib["tests"])==89 and int(tests.attrib["failures"])==int(tests.attrib["errors"])==0
    signals=json.loads((OUT/"signals.json").read_text(encoding="utf-8"));original=json.loads((PRIOR/"signals.json").read_text(encoding="utf-8"))
    assert signals=={k:original[k] for k in {sp["source"]["id"] for sp in s["specs"]}}
    prices,funding,_=load();rules=exchange_rules(RULE_PATH);specs={sp["id"]:sp for sp in s["specs"]}
    baselines=fc=fills=curve_states=quota_checks=0;incomplete=[]
    for i,row in enumerate(s["results"],1):
        sp=specs[row["strategy_id"]];start,end=spans[row["window"]];_,fee,slip=next(c for c in COSTS if c[0]==row["cost"])
        raw=json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"));curve=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet")
        assert raw["initial_equity"]==500 and raw["max_positions"]==5 and curve["at"].iloc[0]==start
        assert row["policy"]==sp["policy"]
        audit_account(raw,sp["notional"]);assert utilization(curve,raw,sp["notional"])==row["utilization"]
        assert exit_diagnostics(raw)==row["exit_diagnostics"]
        assert side_metrics(raw,curve,sp["policy"].get("side_caps"))==row["side_metrics"]
        assert monthly_metrics(curve.to_dict("records"),boundaries=[t for t in BOUNDARIES if start<=t<=end])==row["monthly"]
        assert row["target_met"]==(raw["ending_equity"] is not None and row["monthly"]["all_months_50pct"])
        a,b,c=audit_directional(raw,curve,prices,funding,fee,slip,5,sp["notional"]);fc+=a;fills+=b;curve_states+=c
        active={};caps=sp["policy"].get("side_caps")
        for j in raw["journal"]:
            if j["kind"]=="entry":
                assert j["symbol"] not in active;active[j["symbol"]]=j["side"]
                if caps is not None:
                    assert sum(side==j["side"] for side in active.values())<=caps[j["side"]];quota_checks+=1
            elif j["kind"]=="entry_add":assert active[j["symbol"]]==j["side"]
            elif "net" in j:assert active.pop(j["symbol"])==j["side"]
        if raw["ending_equity"] is None:
            assert raw["errors"] and not row["target_met"];incomplete.append(dict(id=row["id"],errors=raw["errors"],stop_event=raw["stop_event"]))
        else:assert curve["at"].iloc[-1]==end and abs(curve.equity.iloc[-1]-raw["ending_equity"])<1e-8
        if curve.paused.any():
            first=curve.loc[curve.paused,"at"].iloc[0];assert curve.loc[curve["at"]>=first,"paused"].all()
            assert not any(j["kind"] in ["entry","entry_add"] and j["at"]>first for j in raw["journal"])
        if sp["baseline"] and row["window"] in ORIGINAL_WINDOWS:
            ref=f"{row['window']}_{row['cost']}_{sp['reference_id']}"
            assert raw==json.loads((PRIOR/"runs"/f"{ref}.json").read_text(encoding="utf-8")),row["id"]
            pd.testing.assert_frame_equal(curve,pd.read_parquet(PRIOR/"runs"/f"{ref}_equity.parquet"),check_exact=True);baselines+=1
        if i%64==0:print("AUDIT",i,"/",len(s["results"]),flush=True)
    # Verify denominators independently, including failed starts.
    for rob in s["robustness"]:
        rows=[r for r in s["results"] if r["strategy_id"]==rob["strategy_id"] and r["cost"]==rob["cost"] and (r["window"].startswith("roll_") or r["window"]=="later")]
        assert rob["windows"]==len(rows)==10
        assert rob["complete"]==sum(r["ending_equity"] is not None for r in rows)
        assert rob["profitable"]==sum(r["ending_equity"] is not None and r["ending_equity"]>500 for r in rows)
    cases={(r["strategy_id"],"later") for r in s["selected"] if r["strategy_id"]}
    cases|={(REFERENCES[0]+"_L1S4","year"),(REFERENCES[1]+"_L4S1","roll_2025_11")}
    exact=0
    for ident,window in sorted(cases):
        sp=specs[ident];start,end=spans[window]
        for cost,fee,slip in COSTS:
            r=simulate(list(range(start,end+1,300000)),grouped_signals(signals[sp["source"]["id"]],start,end),lambda c:prices.get(c,{}),rules,
                lambda c:funding[c],configuration(5,fee,slip),research_policy=sp["policy"])
            r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct";key=f"{window}_{cost}_{ident}"
            assert {k:v for k,v in r.items() if k!="curve"}==json.loads((OUT/"runs"/f"{key}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(pd.DataFrame(r["curve"]),pd.read_parquet(OUT/"runs"/f"{key}_equity.parquet"),check_exact=True);exact+=1
    write(OUT/"verification.json",dict(journals_audited=len(s["results"]),baseline_paths_exact=baselines,replayed_paths_exact=exact,
        quota_entry_checks=quota_checks,funding_quantities_checked=fc,directional_fills_checked=fills,equity_states_reconstructed=curve_states,
        incomplete_paths=incomplete,distinct_rolling_windows=10,robustness_summaries_checked=len(s["robustness"]),
        hashes_match=True,live_config_unchanged=True,unit_tests_passed=89,junit_sha256=sha(ROOT/"tmp/side_capacity_tests.xml")))
    print("VERIFIED",flush=True)


if __name__=="__main__":main()
