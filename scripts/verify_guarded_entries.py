"""Verify entry-time causality, accounting and matched portfolio controls."""

import json

import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import audit_account,utilization
from compare_account_risk import ROOT,exchange_rules,sha,write
from historical_research_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from prepare_historical_research import OUT as DATA
from search_guarded_entries import OUT,PRIOR,entry_set
from search_historical_entries import BOUNDARIES,COSTS,SPANS
from search_multitimeframe_rolling import grouped_signals,rolling_windows
from short_entry_guards import features
from short_event_study import outcomes,statistics

from dao_vang.config.settings import ExecutionConfig


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));p=s["protocol"]
    assert sha(ROOT/"configs/live.yaml")==p["live_config_sha256"]
    assert sha(DATA/"manifest.json")==p["data_sha256"]
    assert sha(PRIOR/"signals.json")==p["signals_sha256"]
    for name,digest in p["source_sha256"].items():assert sha(ROOT/"scripts"/name)==digest
    prices,funding,frames=load();enriched=features(frames,funding)
    signals=json.loads((PRIOR/"signals.json").read_text(encoding="utf-8"))
    cut=pd.Timestamp("2026-02-01T03:25:00Z");stamp=int(cut.timestamp()*1000)
    prefix=features({c:f.loc[:cut] for c,f in frames.items()},funding)
    for coin,frame in enriched.items():pd.testing.assert_frame_equal(frame.loc[:cut],prefix[coin])
    for spec in p["specs"]:
        full,_=entry_set(signals,prices,enriched,spec,*SPANS["full"])
        truncated,_=entry_set(signals,prices,prefix,spec,SPANS["full"][0],stamp+300000)
        assert [r for r in full if r["at"]<=stamp]==truncated
    print("CAUSAL",len(p["specs"]),flush=True)
    windows=dict(SPANS,**rolling_windows());entry_checks=0;screen_checks=0;cache={}
    for row in s["validation"]+s["holdout"]+s["controls"]:
        spec=row["spec"];window=row["window"];key=(spec["id"],window)
        if key not in cache:
            es,au=entry_set(signals,prices,enriched,spec,*windows[window]);cache[key]=(es,au)
            saved=json.loads((OUT/"entries"/f"{window}_{spec['id']}.json").read_text(encoding="utf-8"))
            assert dict(entries=es,audit=au)==saved;entry_checks+=1
        es,au=cache[key]
        events,counts=outcomes(es,prices,funding,*windows[window],spec["hours"])
        assert counts==row["counts"]
        for cost,fee,slip in COSTS:
            assert statistics(events,*windows[window],fee,slip)==row["cases"][cost];screen_checks+=1
    baseline=0;specs={p["id"]:p for p in s["portfolio_specs"]}
    prior_runs=ROOT/"artifacts/capital_holding_20260925/runs"
    for row in s["results"]:
        result=json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"))
        curve=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet")
        start,end=windows[row["window"]]
        assert result["initial_equity"]==500 and curve["at"].iloc[0]==start
        audit_account(result,row["notional"],5)
        assert utilization(curve,result,row["notional"],5)==row["utilization"]
        assert abs(sum(j.get("net",0) for j in result["journal"])-result["closed_trade_net"])<1e-7
        assert abs(sum(j["amount"] for j in result["journal"] if j["kind"]=="funding")-result["funding"])<1e-7
        qty={};fees=0.;fee=next(f for c,f,_ in COSTS if c==row["cost"])
        for j in result["journal"]:
            assert start<=j["at"]<=end
            if j["kind"] in ["entry","entry_add"]:
                qty[j["event_id"]]=qty.get(j["event_id"],0)+j["qty"];fees+=j["qty"]*j["price"]*fee
            elif "net" in j:fees+=qty.pop(j["event_id"])*j["price"]*fee
        assert abs(fees-result["fees"])<1e-7
        assert all(o["opened_at"]>=start for o in result["open_positions"])
        assert monthly_metrics(curve.to_dict("records"),boundaries=[t for t in BOUNDARIES if start<=t<=end])==row["monthly"]
        if result["ending_equity"] is not None:
            assert curve["at"].iloc[-1]==end
            assert abs(curve["equity"].iloc[-1]-result["ending_equity"])<1e-7
        else:assert not row["target_met"] and not row["monthly"]["complete"] and result["errors"]
        if curve.paused.any():
            first=curve.loc[curve.paused,"at"].iloc[0]
            assert curve.loc[curve["at"]>=first,"paused"].all()
            assert not any(j["kind"] in ["entry","entry_add"] and j["at"]>first for j in result["journal"])
        if row["baseline"]:
            ident=f"{row['window']}_{row['cost']}_{row['source']}_n{row['notional']}_{row['management']}"
            assert result==json.loads((prior_runs/f"{ident}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(prior_runs/f"{ident}_equity.parquet"),check_exact=True);baseline+=1
    print("AUDITED",len(s["results"]),"BASELINES",baseline,flush=True)
    exact=0;rules=exchange_rules(RULE_PATH)
    for row in s["results"]:
        if row["baseline"] or row["window"]!="full" or row["notional"]!=100 or row["management"]!="hold":continue
        spec=specs[row["strategy_id"]];start,end=windows["full"]
        es,_=entry_set(signals,prices,enriched,spec["entry"],start,end)
        fee,slip=next((f,b) for c,f,b in COSTS if c==row["cost"])
        r=simulate(list(range(start,end+1,300000)),grouped_signals(es,start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                   ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
        r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
        assert {k:v for k,v in r.items() if k!="curve"}==json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"))
        pd.testing.assert_frame_equal(pd.DataFrame(r["curve"]),pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet"),check_exact=True)
        exact+=1
    write(OUT/"verification.json",dict(unit_tests_passed=103,entry_prefix_checks=len(p["specs"]),feature_prefix_checks=len(enriched),
        entry_sets_reproduced=entry_checks,screen_statistics_reproduced=screen_checks,journals_audited=len(s["results"]),
        prior_baseline_paths_exact=baseline,new_paths_exact=exact,source_hashes_match=True,data_hashes_match=True,live_config_unchanged=True))
    print("VERIFIED",flush=True)


if __name__=="__main__":main()
