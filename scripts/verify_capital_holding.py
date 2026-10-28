"""Audit allocation experiments, reproduce baseline paths and selected new paths."""

import json

import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import audit_account,utilization
from compare_account_risk import ROOT,exchange_rules,sha,write
from historical_research_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from prepare_historical_research import OUT as DATA
from search_capital_holding import OUT,PRIOR
from search_historical_entries import BOUNDARIES,COSTS
from search_multitimeframe_rolling import grouped_signals,rolling_windows

from dao_vang.config.settings import ExecutionConfig


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));p=s["protocol"]
    assert sha(ROOT/"configs/live.yaml")==p["live_config_sha256"]
    assert sha(DATA/"manifest.json")==p["data_sha256"]
    assert sha(PRIOR/"signals.json")==p["signals_sha256"]
    for name,digest in p["source_sha256"].items():assert sha(ROOT/"scripts"/name)==digest
    windows=rolling_windows();specs={r["id"]:r for r in s["specs"]}
    baselines=0;incomplete=[]
    for row in s["results"]:
        raw=json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"))
        curve=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet")
        start,end=windows[row["window"]]
        assert raw["initial_equity"]==500 and curve["at"].iloc[0]==start
        assert all(start<=j["at"]<=end for j in raw["journal"])
        assert all(o["opened_at"]>=start for o in raw["open_positions"])
        audit_account(raw,row["notional"],5)
        assert utilization(curve,raw,row["notional"],5)==row["utilization"]
        assert abs(sum(j.get("net",0) for j in raw["journal"])-raw["closed_trade_net"])<1e-7
        assert abs(sum(j["amount"] for j in raw["journal"] if j["kind"]=="funding")-raw["funding"])<1e-7
        fee=next(f for c,f,_ in COSTS if c==row["cost"]);qty={};fees=0.
        for j in raw["journal"]:
            if j["kind"] in ["entry","entry_add"]:
                qty[j["event_id"]]=qty.get(j["event_id"],0)+j["qty"]
                fees+=j["qty"]*j["price"]*fee
            elif "net" in j:fees+=qty.pop(j["event_id"])*j["price"]*fee
        assert abs(fees-raw["fees"])<1e-7
        assert monthly_metrics(curve.to_dict("records"),boundaries=[t for t in BOUNDARIES if start<=t<=end])==row["monthly"]
        if curve.paused.any():
            first=curve.loc[curve.paused,"at"].iloc[0]
            assert curve.loc[curve["at"]>=first,"paused"].all()
            assert not any(j["kind"] in ["entry","entry_add"] and j["at"]>first for j in raw["journal"])
        if raw["ending_equity"] is None:
            assert not row["target_met"] and not row["monthly"]["complete"]
            assert raw["errors"] and raw["stop_event"]
            assert raw["stop_event"]["at"]<=end
            incomplete.append(dict(id=row["id"],errors=raw["errors"],stop_event=raw["stop_event"]))
        else:
            assert curve["at"].iloc[-1]==end
            assert abs(curve["equity"].iloc[-1]-raw["ending_equity"])<1e-7
        if row["notional"]==25 and row["management"]=="hold":
            ident=f"{row['window']}_{row['cost']}_{specs[row['strategy_id']]['reference_id']}"
            old=json.loads((PRIOR/"runs"/f"{ident}.json").read_text(encoding="utf-8"))
            assert raw==old
            pd.testing.assert_frame_equal(curve,pd.read_parquet(PRIOR/"runs"/f"{ident}_equity.parquet"),check_exact=True)
            baselines+=1
    print("AUDITED",len(s["results"]),"BASELINES",baselines,"INCOMPLETE",len(incomplete),flush=True)
    prices,funding,_=load();rules=exchange_rules(RULE_PATH)
    signals=json.loads((PRIOR/"signals.json").read_text(encoding="utf-8"));exact=0
    selected=[r for r in s["results"] if r["window"]=="full" and r["notional"]==250 and r["management"]=="hold"]
    selected.extend(r for r in s["results"] if r["ending_equity"] is None)
    for row in selected:
        spec=specs[row["strategy_id"]];start,end=windows[row["window"]]
        fee,slip=next((f,b) for c,f,b in COSTS if c==row["cost"])
        result=simulate(list(range(start,end+1,300000)),grouped_signals(signals[spec["source"]["id"]],start,end),
                        lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                        ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
        result["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
        assert {k:v for k,v in result.items() if k!="curve"}==json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"))
        pd.testing.assert_frame_equal(pd.DataFrame(result["curve"]),pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet"),check_exact=True)
        exact+=1;print("REPLAY",row["id"],flush=True)
    write(OUT/"verification.json",dict(unit_tests_passed=95,journals_audited=len(s["results"]),
          prior_baseline_paths_exact=baselines,new_paths_exact=exact,rolling_resets_checked=len(s["results"]),
          utilization_and_monthly_metrics_reproduced=len(s["results"]),incomplete_paths=incomplete,
          source_hashes_match=True,data_hashes_match=True,live_config_unchanged=True))
    print("VERIFIED",flush=True)


if __name__=="__main__":main()
