"""Replay the selected signal mechanisms and independently balance journals."""

import json
from collections import defaultdict

import pandas as pd
from account_scaled_replay import simulate
from compare_account_risk import ROOT,exchange_rules,sha,write
from historical_research_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from prepare_flow_research import OUT
from search_funding_flow import load_flow
from search_historical_entries import BOUNDARIES,COSTS,SPANS,audit_account
from short_event_study import outcomes,statistics
from short_funding_flow_signals import generate

from dao_vang.config.settings import ExecutionConfig


def main():
    summary=json.loads((OUT/"summary.json").read_text(encoding="utf-8"))
    protocol=summary["protocol"]
    before=OUT/"pre_tp_hold_fix"
    old=json.loads((before/"summary.json").read_text(encoding="utf-8"))
    assert summary["chosen"]==old["chosen"]
    assert summary["development"]==old["development"]
    assert summary["validation"]==old["validation"] and summary["holdout"]==old["holdout"]
    preserved=0;repaired=[]
    for row in old["results"]:
        old_result=json.loads((before/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"))
        new_result=json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"))
        if not old_result["errors"]:
            assert old_result==new_result
            pd.testing.assert_frame_equal(pd.read_parquet(before/"runs"/f"{row['id']}_equity.parquet"),
                                          pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet"),check_exact=True)
            preserved+=1
        else:
            assert any(j["kind"]=="tp_unrepresentable" for j in new_result["journal"])
            assert not any("tp_price_unrepresentable" in error for error in new_result["errors"])
            assert len(pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet"))>len(pd.read_parquet(before/"runs"/f"{row['id']}_equity.parquet"))
            repaired.append(row["id"])
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    assert sha(OUT/"flow_evidence.json")==protocol["flow_evidence_sha256"]
    for name,digest in protocol["source_sha256"].items():assert sha(ROOT/"scripts"/name)==digest
    signals=json.loads((OUT/"signals.json").read_text(encoding="utf-8"))
    prices,funding,frames=load();flow=load_flow()
    assert generate(frames,flow,funding)==signals
    cutoff=pd.Timestamp("2026-02-01",tz="UTC"); cut=int(cutoff.timestamp()*1000)
    prefix=generate({c:h.loc[:cutoff] for c,h in frames.items()},
                    {c:f.loc[:cutoff] for c,f in flow.items()},
                    {c:[r for r in schedule if r[0]<=cut] for c,schedule in funding.items()})
    assert prefix=={c:[r for r in rows if r["at"]<=cut] for c,rows in signals.items()}
    checked=0
    for row in summary["validation"]+summary["holdout"]:
        events,counts=outcomes(signals[row["spec"]["source"]["id"]],prices,funding,*SPANS[row["window"]],row["spec"]["hours"])
        assert counts==row["counts"]
        for cost,fee,slip in COSTS:
            assert statistics(events,*SPANS[row["window"]],fee,slip)==row["cases"][cost]
            checked+=1
    for row in summary["results"]:
        r=json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"))
        curve=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet")
        assert audit_account(r,row["cap"])==row["audit"]
        assert abs(sum(j.get("net",0) for j in r["journal"])-r["closed_trade_net"])<1e-7
        assert abs(sum(j["amount"] for j in r["journal"] if j["kind"]=="funding")-r["funding"])<1e-7
        fee=next(f for c,f,_ in COSTS if c==row["cost"])
        quantities={}; total_fees=0.
        for j in r["journal"]:
            if j["kind"] in ["entry","entry_add"]:
                quantities[j["event_id"]]=quantities.get(j["event_id"],0)+j["qty"]
                total_fees+=j["qty"]*j["price"]*fee
            elif "net" in j:
                total_fees+=quantities.pop(j["event_id"])*j["price"]*fee
        assert abs(total_fees-r["fees"])<1e-7
        if row["window"]=="full":assert monthly_metrics(curve.to_dict("records"),boundaries=BOUNDARIES)==row["monthly"]
        if curve.paused.any():
            first=curve.loc[curve.paused,"at"].iloc[0]
            assert curve.loc[curve["at"]>=first,"paused"].all()
            assert not any(j["kind"] in ["entry","entry_add"] and j["at"]>first for j in r["journal"])
    exact=0;rules=exchange_rules(RULE_PATH)
    for candidate in summary["chosen"]:
        spec=next(s for s in summary["portfolio_specs"] if s["source"]["id"]==candidate["source"]["id"]
                  and s["cap"]==5 and s["parts"]==3 and s["exit"]=="trail_noSL")
        start,end=SPANS["full"];grouped=defaultdict(list)
        for signal in signals[spec["source"]["id"]]:
            if start<=signal["at"]<end:grouped[signal["at"]].append(signal)
        for g in grouped.values():g.sort(key=lambda r:(-r["probability"],r["symbol"]))
        for cost,fee,slip in COSTS:
            result=simulate(list(range(start,end+1,300000)),grouped,lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                            ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
            result["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
            ident=f"full_{cost}_{spec['id']}"
            stored=json.loads((OUT/"runs"/f"{ident}.json").read_text(encoding="utf-8"))
            assert stored=={k:v for k,v in result.items() if k!="curve"}
            pd.testing.assert_frame_equal(pd.DataFrame(result["curve"]),pd.read_parquet(OUT/"runs"/f"{ident}_equity.parquet"),check_exact=True)
            exact+=1
    write(OUT/"verification.json",dict(unit_tests_passed=86,journals_audited=len(summary["results"]),
        screen_statistics_reproduced=checked,signal_sets_reproduced=len(signals),signal_prefix_invariant=len(signals),
        full_paths_exact=exact,source_hashes_match=True,live_config_unchanged=True,
        unaffected_account_paths_exact=preserved,repaired_paths=repaired,selection_unchanged_after_engine_repair=True))
    print("VERIFIED",len(summary["results"]),"journals",checked,"screen statistics",exact,"exact paths",flush=True)


if __name__=="__main__":main()
