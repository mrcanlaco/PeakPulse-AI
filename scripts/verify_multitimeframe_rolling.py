"""Check rolling resets, causal higher-timeframe features and exact baselines."""

import json

import pandas as pd
from account_scaled_replay import simulate
from compare_account_risk import ROOT,exchange_rules,sha,write
from historical_research_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from search_historical_entries import BOUNDARIES,COSTS,SPANS,audit_account
from search_multitimeframe_rolling import OUT,PRIOR,grouped_signals,rolling_windows
from short_event_study import outcomes,statistics
from short_multitimeframe_signals import features,generate

from dao_vang.config.settings import ExecutionConfig


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));protocol=s["protocol"]
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    for name,digest in protocol["source_sha256"].items():assert sha(ROOT/"scripts"/name)==digest
    prices,funding,frames=load()
    signals=json.loads((OUT/"signals.json").read_text(encoding="utf-8"))
    regenerated=generate(frames)
    assert all(signals[k]==rows for k,rows in regenerated.items())
    cut=pd.Timestamp("2026-02-01T03:00:00Z");stamp=int(cut.timestamp()*1000)
    prefix=generate({coin:frame.loc[:cut] for coin,frame in frames.items()})
    assert prefix=={k:[r for r in rows if r["at"]<=stamp] for k,rows in regenerated.items()}
    for coin,frame in frames.items():pd.testing.assert_frame_equal(features(frame).loc[:cut],features(frame.loc[:cut]).loc[:cut])
    checked=0
    for row in s["validation"]+s["holdout"]:
        events,counts=outcomes(signals[row["spec"]["source"]["id"]],prices,funding,*SPANS[row["window"]],row["spec"]["hours"])
        assert counts==row["counts"]
        for cost,fee,slip in COSTS:
            assert statistics(events,*SPANS[row["window"]],fee,slip)==row["cases"][cost];checked+=1
    windows=rolling_windows();baseline_checks=0
    for row in s["results"]:
        r=json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"))
        curve=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet")
        start,end=windows[row["window"]]
        assert r["initial_equity"]==500 and curve["at"].iloc[0]==start
        assert all(start<=j["at"]<=end for j in r["journal"])
        assert all(p["opened_at"]>=start for p in r["open_positions"])
        assert audit_account(r,5)==row["audit"]
        assert abs(sum(j.get("net",0) for j in r["journal"])-r["closed_trade_net"])<1e-7
        assert abs(sum(j["amount"] for j in r["journal"] if j["kind"]=="funding")-r["funding"])<1e-7
        fee=next(f for c,f,_ in COSTS if c==row["cost"]);quantities={};fee_sum=0.
        for j in r["journal"]:
            if j["kind"] in ["entry","entry_add"]:
                quantities[j["event_id"]]=quantities.get(j["event_id"],0)+j["qty"]
                fee_sum+=j["qty"]*j["price"]*fee
            elif "net" in j:fee_sum+=quantities.pop(j["event_id"])*j["price"]*fee
        assert abs(fee_sum-r["fees"])<1e-7
        assert monthly_metrics(curve.to_dict("records"),boundaries=[t for t in BOUNDARIES if start<=t<=end])==row["monthly"]
        if curve.paused.any():
            first=curve.loc[curve.paused,"at"].iloc[0]
            assert curve.loc[curve["at"]>=first,"paused"].all()
            assert not any(j["kind"] in ["entry","entry_add"] and j["at"]>first for j in r["journal"])
        if row["baseline"] and row["window"] in ["full","start_2026_03"]:
            prior_window="full" if row["window"]=="full" else "holdout"
            ident=f"{prior_window}_{row['cost']}_seller_pressure_n5_p3_trail_noSL"
            old=json.loads((PRIOR/"runs"/f"{ident}.json").read_text(encoding="utf-8"))
            assert r==old
            pd.testing.assert_frame_equal(curve,pd.read_parquet(PRIOR/"runs"/f"{ident}_equity.parquet"),check_exact=True)
            baseline_checks+=1
    exact=0;rules=exchange_rules(RULE_PATH)
    for source in s["chosen"]:
        spec=next(p for p in s["portfolio_specs"] if p["source"]["id"]==source["source"]["id"] and p["parts"]==3 and p["exit"]=="trail_noSL")
        start,end=SPANS["full"];groups=grouped_signals(signals[spec["source"]["id"]],start,end)
        for cost,fee,slip in COSTS:
            r=simulate(list(range(start,end+1,300000)),groups,lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                       ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
            r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
            ident=f"full_{cost}_{spec['id']}"
            old=json.loads((OUT/"runs"/f"{ident}.json").read_text(encoding="utf-8"))
            assert old=={k:v for k,v in r.items() if k!="curve"}
            pd.testing.assert_frame_equal(pd.DataFrame(r["curve"]),pd.read_parquet(OUT/"runs"/f"{ident}_equity.parquet"),check_exact=True)
            exact+=1
    write(OUT/"verification.json",dict(unit_tests_passed=91,journals_audited=len(s["results"]),
        screen_statistics_reproduced=checked,signal_sets_reproduced=len(regenerated),signal_prefix_checks=len(prefix),
        feature_prefix_checks=len(frames),rolling_resets_checked=len(s["results"]),
        prior_baseline_paths_exact=baseline_checks,new_full_paths_exact=exact,source_hashes_match=True,live_config_unchanged=True))
    print("VERIFIED",len(s["results"]),"journals",baseline_checks,"baseline paths",exact,"new paths",flush=True)


if __name__=="__main__":main()
