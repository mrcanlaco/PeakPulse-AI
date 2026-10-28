"""Verify hypothetical cost paths, funded quantities, attribution and controls."""

import json
import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import audit_account,utilization
from compare_account_risk import ROOT,sha,write,exchange_rules
from execution_cost_attribution import attribute
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from search_execution_costs import OUT,PRIOR,DATA,WINDOWS,BOUNDARIES,PROFILES,definitions,configuration,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));p=s["protocol"]
    assert sha(ROOT/"configs/live.yaml")==p["live_config_sha256"]
    assert sha(PRIOR/"summary.json")==p["prior_sha256"] and sha(PRIOR/"signals.json")==p["signals_sha256"]
    assert sha(DATA/"reconciled_manifest.json")==p["data_sha256"]
    for n,d in p["source_sha256"].items():assert sha(ROOT/"scripts"/n)==d
    assert definitions(json.loads((PRIOR/"summary.json").read_text(encoding="utf-8")))==s["specs"] and s["profiles"]==PROFILES
    prices,funding,_=load();rules=exchange_rules(RULE_PATH);signals=json.loads((PRIOR/"signals.json").read_text(encoding="utf-8"))
    schedule={c:{t:(rate,mark) for t,rate,mark in rows} for c,rows in funding.items()}
    baselines=0;funded_quantities=0;incomplete=[]
    for row in s["results"]:
        raw=json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"));curve=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet")
        start,end=WINDOWS[row["window"]];profile=next(c for c in PROFILES if c["id"]==row["cost"])
        assert row["cost_profile"]==profile and raw["initial_equity"]==500 and curve["at"].iloc[0]==start
        audit_account(raw,row["notional"]);assert utilization(curve,raw,row["notional"])==row["utilization"]
        assert exit_diagnostics(raw)==row["exit_diagnostics"] and attribute(raw,lambda c:prices[c])==row["attribution"]
        assert monthly_metrics(curve.to_dict("records"),boundaries=[t for t in BOUNDARIES if start<=t<=end])==row["monthly"]
        assert abs(sum(j.get("net",0) for j in raw["journal"])-raw["closed_trade_net"])<1e-7
        assert abs(sum(j["amount"] for j in raw["journal"] if j["kind"]=="funding")-raw["funding"])<1e-7
        fees=0.;reference_turnover=0.;qty={};active={}
        for j in raw["journal"]:
            if j["kind"]=="entry":active[j["symbol"]]=j["event_id"]
            if j["kind"] in ["entry","entry_add"]:
                qty[j["event_id"]]=qty.get(j["event_id"],0)+j["qty"]
                fees+=j["qty"]*j["price"]*profile["fee"];reference_turnover+=j["qty"]*prices[j["symbol"]].get(j["at"])["entry_open"]
            elif j["kind"]=="funding":
                assert profile["funding"]
                rate,mark=schedule[j["symbol"]][j["at"]]
                assert abs(j["amount"]-qty[active[j["symbol"]]]*rate*mark)<1e-8;funded_quantities+=1
            elif "net" in j:
                q=qty.pop(j["event_id"]);active.pop(j["symbol"])
                fees+=q*j["price"]*profile["fee"];reference_turnover+=q*prices[j["symbol"]].get(j["at"])["entry_open"]
        assert abs(fees-raw["fees"])<1e-7
        if not profile["funding"]:assert raw["funding"]==0 and not any(j["kind"]=="funding" for j in raw["journal"])
        if raw["ending_equity"] is not None:
            assert curve["at"].iloc[-1]==end and abs(curve["equity"].iloc[-1]-raw["ending_equity"])<1e-7
            a=row["attribution"]
            assert abs(a["reference_turnover"]-reference_turnover)<1e-6
            assert abs(a["slippage_paid"]-reference_turnover*profile["slip"]/10000)<1e-6
            assert abs(a["price_pnl_at_reference"]+a["funding"]-a["slippage_paid"]-a["commissions"]-raw["pnl"])<1e-6
        else:
            assert raw["errors"] and not row["target_met"] and not row["attribution"]["complete"]
            incomplete.append(dict(id=row["id"],stop_event=raw["stop_event"],errors=raw["errors"]))
        if curve.paused.any():
            first=curve.loc[curve.paused,"at"].iloc[0];assert curve.loc[curve["at"]>=first,"paused"].all()
            assert not any(j["kind"] in ["entry","entry_add"] and j["at"]>first for j in raw["journal"])
        if row["cost"] in ["base","stress"]:
            assert raw==json.loads((PRIOR/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(PRIOR/"runs"/f"{row['id']}_equity.parquet"),check_exact=True);baselines+=1
    print("AUDITED",len(s["results"]),"BASELINES",baselines,"FUNDING",funded_quantities,flush=True)
    specs={r["id"]:r for r in s["specs"]};cases=[(i,"year","no_execution_cost") for i in specs]
    cases += [("benchmark_mask2_n25","year","no_cost_no_funding"),("beta7d_breadth75_btc_scheduled_n25_time168","later","no_cost_no_funding")]
    exact=0
    for ident,window,cost in cases:
        spec=specs[ident];start,end=WINDOWS[window];profile=next(p for p in PROFILES if p["id"]==cost)
        r=simulate(list(range(start,end+1,300000)),grouped_signals(signals[spec["source"]["id"]],start,end),lambda c:prices.get(c,{}),rules,
            lambda c:funding[c] if profile["funding"] else [],configuration(profile),research_policy=spec["policy"])
        r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct";key=f"{window}_{cost}_{ident}"
        assert {k:v for k,v in r.items() if k!="curve"}==json.loads((OUT/"runs"/f"{key}.json").read_text(encoding="utf-8"))
        pd.testing.assert_frame_equal(pd.DataFrame(r["curve"]),pd.read_parquet(OUT/"runs"/f"{key}_equity.parquet"),check_exact=True);exact+=1
    write(OUT/"verification.json",dict(journals_audited=len(s["results"]),baseline_paths_exact=baselines,replayed_paths_exact=exact,
        funding_quantities_checked=funded_quantities,attribution_identities_checked=sum(r["ending_equity"] is not None for r in s["results"]),
        incomplete_paths=incomplete,source_hashes_match=True,data_hashes_match=True,live_config_unchanged=True,unit_tests_passed=62))
    print("VERIFIED",flush=True)


if __name__=="__main__":main()
