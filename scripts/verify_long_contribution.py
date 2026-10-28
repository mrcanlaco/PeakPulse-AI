"""Verify the mechanism control separately from the predeclared main batch."""
import json
import pandas as pd
from account_side_quota_replay import simulate
from check_long_contribution import OUT,PARENT,REFERENCE
from compare_account_risk import ROOT,sha,write,exchange_rules
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from research_directional_audit import audit_directional
from search_side_capacity import windows,BOUNDARIES,COSTS
from search_multitimeframe_rolling import grouped_signals


def main():
    s=json.loads((OUT/"summary.json").read_text());p=s["protocol"]
    assert sha(PARENT/"summary.json")==p["parent_sha256"] and sha(PARENT/"signals.json")==p["signals_sha256"]
    assert sha(ROOT/"configs/live.yaml")==p["live_config_sha256"] and sha(RULE_PATH)==p["rules_sha256"]
    for n,d in p["source_sha256"].items():assert sha(ROOT/"scripts"/n)==d
    parent=json.loads((PARENT/"summary.json").read_text());sp=next(x for x in parent["specs"] if x["id"]==REFERENCE)
    source=json.loads((PARENT/"signals.json").read_text())[sp["source"]["id"]]
    signals=json.loads((OUT/"signals.json").read_text());assert signals==[r for r in source if r["side"]=="SHORT"]
    assert sp["policy"]==p["policy"] and p["policy"]["side_caps"]==dict(LONG=2,SHORT=3)
    prices,funding,_=load();rules=exchange_rules(RULE_PATH);fc=fills=states=0
    for row in s["results"]:
        start,end=windows()[row["window"]];_,fee,slip=next(c for c in COSTS if c[0]==row["cost"])
        raw=json.loads((OUT/"runs"/f"{row['id']}.json").read_text());curve=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet")
        assert curve["at"].iloc[0]==start and curve["at"].iloc[-1]==end and raw["initial_equity"]==500 and curve.positions.max()<=3
        assert all(j["side"]=="SHORT" for j in raw["journal"])
        assert raw["ending_equity"]==row["ending_equity"] and not raw["errors"]
        a,b,c=audit_directional(raw,curve,prices,funding,fee,slip,5,25);fc+=a;fills+=b;states+=c
        assert row["monthly"]==monthly_metrics(curve.to_dict("records"),boundaries=[t for t in BOUNDARIES if start<=t<=end])
        both=next(r for r in parent["results"] if r["strategy_id"]==REFERENCE and r["window"]==row["window"] and r["cost"]==row["cost"])
        assert abs(row["comparison"]["hybrid_minus_control"]-(both["ending_equity"]-row["ending_equity"]))<1e-8
    exact=0
    for window in ["year","later","roll_2025_12"]:
        start,end=windows()[window]
        for cost,fee,slip in COSTS:
            r=simulate(list(range(start,end+1,300000)),grouped_signals(signals,start,end),lambda c:prices.get(c,{}),rules,
                lambda c:funding[c],configuration(5,fee,slip),research_policy=p["policy"])
            r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct";key=f"{window}_{cost}_short_only3"
            assert {k:v for k,v in r.items() if k!="curve"}==json.loads((OUT/"runs"/f"{key}.json").read_text())
            pd.testing.assert_frame_equal(pd.DataFrame(r["curve"]),pd.read_parquet(OUT/"runs"/f"{key}_equity.parquet"),check_exact=True);exact+=1
    write(OUT/"verification.json",dict(journals_audited=24,replayed_paths_exact=exact,funding_quantities_checked=fc,
        directional_fills_checked=fills,equity_states_reconstructed=states,hashes_match=True,live_config_unchanged=True,
        diagnostic_after_parent_results=True,not_independent_holdout=True))
    print("VERIFIED",flush=True)


if __name__=="__main__":main()
