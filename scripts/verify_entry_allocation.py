"""Verify capital, causal additions, unchanged baseline and replay selection."""

import json
import math

import pandas as pd
from account_entry_replay import simulate
from capital_research_metrics import audit_account, utilization
from compare_account_risk import ROOT, exchange_rules, sha, write
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from search_entry_allocation import OUT, PRIOR, DATA, WINDOWS, BOUNDARIES, COSTS, definitions, select, exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from dao_vang.config.settings import ExecutionConfig


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));p=s["protocol"]
    assert sha(ROOT/"configs/live.yaml")==p["live_config_sha256"]
    assert sha(PRIOR/"summary.json")==p["prior_sha256"] and sha(DATA/"reconciled_manifest.json")==p["data_sha256"]
    for n,d in p["source_sha256"].items():assert sha(ROOT/"scripts"/n)==d
    for m,d in p["input_hashes"].items():assert sha(DATA/"evaluation"/f"entries_mask{int(m):02d}.json")==d
    old=json.loads((PRIOR/"summary.json").read_text(encoding="utf-8"));assert definitions(old)==s["specs"]
    prices,funding,_=load();rules=exchange_rules(RULE_PATH)
    entries={m:json.loads((DATA/"evaluation"/f"entries_mask{m:02d}.json").read_text(encoding="utf-8"))["entries"] for m in [0,2]}
    signal_map={m:{e["event_id"]:e for e in es} for m,es in entries.items()}
    specs={sp["id"]:sp for sp in s["specs"]};baselines=0;checked_adds=0;pullbacks=0;post_activation_adds=0;incomplete=[]
    for row in s["results"]:
        raw=json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"));curve=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet")
        policy=specs[row["strategy_id"]]["policy"];start,end=WINDOWS[row["window"]]
        assert raw["initial_equity"]==500 and curve["at"].iloc[0]==start
        audit_account(raw,row["notional"]);assert utilization(curve,raw,row["notional"])==row["utilization"]
        assert exit_diagnostics(raw)==row["exit_diagnostics"]
        assert monthly_metrics(curve.to_dict("records"),boundaries=[t for t in BOUNDARIES if start<=t<=end])==row["monthly"]
        assert abs(sum(j.get("net",0) for j in raw["journal"])-raw["closed_trade_net"])<1e-7
        assert abs(sum(j["amount"] for j in raw["journal"] if j["kind"]=="funding")-raw["funding"])<1e-7
        active={};fees=0.;fee=next(f for c,f,_ in COSTS if c==row["cost"])
        for j in raw["journal"]:
            assert start<=j["at"]<=end
            if j["kind"]=="entry":
                active[j["event_id"]]=dict(qty=j["qty"],notional=j["qty"]*j["price"],first=j["price"],last=j["at"],opened=j["at"],parts=1,active=False,low=j["price"])
                fees+=j["qty"]*j["price"]*fee
            elif j["kind"]=="trail_activated":active[j["event_id"]]["active"]=True
            elif j["kind"]=="entry_add":
                state=active[j["event_id"]];point=prices[j["symbol"]].get(j["at"]);observed=point["execution_close"]
                atr=signal_map[row["mask"]][j["event_id"]]["atr"]
                assert math.isfinite(observed) and observed<=state["notional"]/state["qty"]+1e-9
                assert j["at"]>state["last"] and j["at"]-state["opened"]<=policy.get("add_expiry_hours",6)*3600000
                assert state["parts"]<3 and j["at"]<end
                if state["active"]:
                    assert not policy.get("cancel_adds_on_trail_activation",True);post_activation_adds+=1
                if policy["entry_mode"]=="time":
                    assert j["at"]-state["opened"]>=state["parts"]*policy["entry_interval_minutes"]*60000
                elif policy["entry_mode"]=="pullback":
                    low=min([state["low"]]+[prices[j["symbol"]].get(t)["execution_close"] for t in range(state["last"]+300000,j["at"]+1,300000)])
                    assert low<=state["first"]-state["parts"]*policy["entry_step_atr"]*atr+1e-9
                    assert observed>=low+policy["pullback_atr"]*atr-1e-9
                    state["low"]=observed;pullbacks+=1
                else:assert observed<=state["first"]-state["parts"]*policy["entry_step_atr"]*atr+1e-9
                state["qty"]+=j["qty"];state["notional"]+=j["qty"]*j["price"];state["parts"]+=1;state["last"]=j["at"]
                fees+=j["qty"]*j["price"]*fee;checked_adds+=1
            elif "net" in j:fees+=active.pop(j["event_id"])["qty"]*j["price"]*fee
        assert abs(fees-raw["fees"])<1e-7
        if curve.paused.any():
            first=curve.loc[curve.paused,"at"].iloc[0]
            assert curve.loc[curve["at"]>=first,"paused"].all()
            assert not any(j["kind"] in ["entry","entry_add"] and j["at"]>first for j in raw["journal"])
        if raw["ending_equity"] is None:
            assert raw["errors"] and not row["target_met"] and not row["monthly"]["complete"]
            incomplete.append(dict(id=row["id"],stop_event=raw["stop_event"],errors=raw["errors"]))
        else:assert curve["at"].iloc[-1]==end and abs(curve["equity"].iloc[-1]-raw["ending_equity"])<1e-7
        if row["baseline"]:
            ident=f"{row['window']}_{row['cost']}_{row['reference_id']}"
            assert raw==json.loads((PRIOR/"runs"/f"{ident}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(PRIOR/"runs"/f"{ident}_equity.parquet"),check_exact=True);baselines+=1
    assert select(s["specs"],s["results"])==s["selected"]==json.loads((OUT/"candidate_lock.json").read_text(encoding="utf-8"))["selected"]
    print("AUDITED",len(s["results"]),"BASELINES",baselines,"ADDS",checked_adds,"PULLBACKS",pullbacks,flush=True)
    replay_ids=set(s["selected"])|{"mask02_n25_trail_a3_c1_pullback","mask02_n25_trail_a0.5_c0.25_keep"}
    exact=0
    for ident in sorted(replay_ids):
        spec=specs[ident];start,end=WINDOWS["year"]
        for cost,fee,slip in COSTS:
            result=simulate(list(range(start,end+1,300000)),grouped_signals(entries[spec["mask"]],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                            ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
            result["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
            key=f"year_{cost}_{ident}"
            assert {k:v for k,v in result.items() if k!="curve"}==json.loads((OUT/"runs"/f"{key}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(pd.DataFrame(result["curve"]),pd.read_parquet(OUT/"runs"/f"{key}_equity.parquet"),check_exact=True);exact+=1
    write(OUT/"verification.json",dict(journals_audited=len(s["results"]),baseline_paths_exact=baselines,entry_adds_causally_checked=checked_adds,
        pullbacks_causally_checked=pullbacks,post_activation_adds_checked=post_activation_adds,replayed_paths_exact=exact,locked_selection_reproduced=True,
        incomplete_paths=incomplete,unit_tests_passed=p["tests"]["passed"],source_hashes_match=True,data_hashes_match=True,live_config_unchanged=True))
    print("VERIFIED",flush=True)


if __name__=="__main__":main()
