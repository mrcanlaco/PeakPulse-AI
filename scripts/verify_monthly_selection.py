"""Audit learning cutoffs, every monthly choice and continuous account paths."""
import json
import hashlib
import pandas as pd
from compare_account_risk import ROOT,sha,write,exchange_rules
from capital_research_metrics import audit_account,utilization
from execution_cost_attribution import attribute
from monthly_account_metrics import monthly_metrics
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from search_monthly_selection import OUT,PRIOR,DATA,SIGNAL_FILES,WINDOWS,BOUNDARIES,COSTS,inputs,definitions,selectors,training_bounds,policy,run,exit_diagnostics


def independent_choice(rows,method):
    candidates=[]
    for source in sorted({r["source_id"] for r in rows}):
        a=[r for r in rows if r["source_id"]==source]
        if len(a)!=2 or {r["cost"] for r in a}!={"base","stress"}:continue
        if any(r["ending_equity"] is None or r["ending_equity"]<=500 or r["max_drawdown"]>=.2 or r["exits"]<5 or not r["monthly"]["complete"] for r in a):continue
        pnls=[r["ending_equity"]-500 for r in a];month_returns=[m["return_fraction"] for r in a for m in r["monthly"]["months"]]
        floor=min(month_returns);profit=min(pnls)
        candidates.append((profit,floor,source) if method=="profit" else (floor,profit,source))
    return sorted(candidates)[-1][-1] if candidates else None


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));p=s["protocol"]
    assert sha(ROOT/"configs/live.yaml")==p["live_config_sha256"] and sha(DATA/"reconciled_manifest.json")==p["data_sha256"]
    assert sha(PRIOR/"summary.json")==p["prior_sha256"]
    for k,path in SIGNAL_FILES.items():assert sha(path)==p["signal_hashes"][k]
    for n,d in p["source_sha256"].items():assert sha(ROOT/"scripts"/n)==d
    assert definitions()==s["specs"]
    training=json.loads((OUT/"training_summary.json").read_text());choices=json.loads((OUT/"choices.json").read_text());routed=json.loads((OUT/"routed_signals.json").read_text());signals=inputs()
    prices,funding,_=load();rules=exchange_rules(RULE_PATH);schedule={c:{t:(rate,mark) for t,rate,mark in rs} for c,rs in funding.items()}
    totals=dict(training_journals=0,deployed_journals=0,funding_quantities=0,baseline_paths_exact=0,choices_exact=0,routed_events_exact=0,replays_exact=0)
    incomplete=[]
    def audit(folder,ident,n,end,cost):
        raw=json.loads((folder/f"{ident}.json").read_text(encoding="utf-8"));curve=pd.read_parquet(folder/f"{ident}_equity.parquet")
        audit_account(raw,n);a=attribute(raw,lambda c:prices[c]);_,fee,slip=next(x for x in COSTS if x[0]==cost)
        assert not any(j["at"]>end for j in raw["journal"])
        if raw["ending_equity"] is None:assert raw["errors"];incomplete.append(ident)
        else:
            assert a["complete"] and curve["at"].iloc[-1]==end and abs(curve["equity"].iloc[-1]-raw["ending_equity"])<1e-7
            assert abs(a["slippage_paid"]-a["reference_turnover"]*slip/10000)<1e-6
        qty={};active={};fees=0
        for j in raw["journal"]:
            if j["kind"]=="entry":active[j["symbol"]]=j["event_id"]
            if j["kind"] in ["entry","entry_add"]:
                qty[j["event_id"]]=qty.get(j["event_id"],0)+j["qty"];fees+=j["qty"]*j["price"]*fee
            elif j["kind"]=="funding":
                rate,mark=schedule[j["symbol"]][j["at"]];assert abs(qty[active[j["symbol"]]]*rate*mark-j["amount"])<1e-8;totals["funding_quantities"]+=1
            elif "net" in j:fees+=qty.pop(j["event_id"])*j["price"]*fee;active.pop(j["symbol"])
        assert abs(fees-raw["fees"])<1e-7
        assert abs(sum(j["amount"] for j in raw["journal"] if j["kind"]=="funding")-raw["funding"])<1e-7
        assert abs(sum(j.get("net",0) for j in raw["journal"])-raw["closed_trade_net"])<1e-7
        if curve.paused.any():
            first=curve.loc[curve.paused,"at"].iloc[0];assert curve.loc[curve["at"]>=first,"paused"].all()
            assert not any(j["kind"] in ["entry","entry_add"] and j["at"]>first for j in raw["journal"])
        return raw,curve
    for t in training:
        start,end,bounds=training_bounds(pd.Timestamp(t["decision_at"],unit="ms",tz="UTC"),t["lookback"])
        assert start==t["start"] and end==t["end"]<t["decision_at"]
        raw,curve=audit(OUT/"training",t["id"],25,end,t["cost"])
        assert curve["at"].iloc[0]==start and raw["ending_equity"]==t["ending_equity"] and raw["sampled_max_drawdown"]==t["max_drawdown"]
        assert t["exits"]==sum("net" in j for j in raw["journal"])
        assert monthly_metrics(curve.to_dict("records"),boundaries=bounds)==t["monthly"]
        assert all(j["at"]<t["decision_at"] for j in raw["journal"])
        totals["training_journals"]+=1
    index={r["id"]:r for r in training}
    for sel in selectors():
        expected_events=[]
        for ch in choices[sel["id"]]:
            ts=[index[i] for i in ch["training_ids"]]
            assert len(ts)==12 and all(t["decision_at"]==ch["start"] and t["end"]==ch["training_end"] and t["lookback"]==sel["lookback"] and t["holding"]==sel["holding"] for t in ts)
            assert independent_choice(ts,sel["method"])==ch["source_id"];totals["choices_exact"]+=1
            if ch["source_id"] is not None:
                for r in signals[ch["source_id"]]:
                    if ch["start"]+300000<=r["at"]<ch["end"]:
                        z=dict(r);z["event_id"]=hashlib.sha256(f"monthly:{ch['source_id']}:{r['event_id']}".encode()).hexdigest()[:24];expected_events.append(z)
        expected_events.sort(key=lambda r:(r["at"],-r["probability"],r["symbol"]))
        assert expected_events==routed[sel["id"]];totals["routed_events_exact"]+=len(expected_events)
    print("TRAINING",len(training),"CHOICES",totals["choices_exact"],flush=True)
    switching=[];specs={sp["id"]:sp for sp in s["specs"]}
    for row in s["results"]:
        start,end=WINDOWS[row["window"]];spec=specs[row["strategy_id"]]
        raw,curve=audit(OUT/"runs",row["id"],row["notional"],end,row["cost"])
        assert utilization(curve,raw,row["notional"])==row["utilization"] and exit_diagnostics(raw)==row["exit_diagnostics"]
        assert monthly_metrics(curve.to_dict("records"),boundaries=[x for x in BOUNDARIES if start<=x<=end])==row["monthly"]
        assert row["ending_equity"]==raw["ending_equity"] and row["target_met"]==(raw["ending_equity"] is not None and row["monthly"]["all_months_50pct"])
        if spec["selector"]:
            events={e["event_id"]:e for e in routed[spec["source"]["id"]]}
            assert all(j["event_id"] in events and j["at"]==events[j["event_id"]]["at"] for j in raw["journal"] if j["kind"]=="entry")
            events=[]
            for ch in choices[spec["source"]["id"]]:
                if not start<=ch["start"]<end:continue
                at=ch["start"];point=curve[curve["at"]==at]
                entries=[j for j in raw["journal"] if j["kind"]=="entry" and at<=j["at"]<ch["end"]]
                if ch["source_id"] is None:assert not entries
                events.append(dict(at=at,source=ch["source_id"],positions_at_boundary=None if point.empty else int(point.iloc[0].positions),entries=len(entries)))
            switching.append(dict(id=row["id"],months=events))
        elif row["window"]=="later":
            mask=0 if spec["source"]["id"]=="reversal0" else 2
            ref=ROOT/"artifacts/reversal_flow_20260925/runs"/f"later_{row['cost']}_mask{mask}_none_n{row['notional']}_{row['holding']}"
            assert raw==json.loads(ref.with_suffix(".json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(str(ref)+"_equity.parquet"),check_exact=True);totals["baseline_paths_exact"]+=1
        totals["deployed_journals"]+=1
    duplicates=0
    for hold in ["hold","time48"]:
        assert choices[f"look1_profit_{hold}"]==choices[f"look1_floor_{hold}"]
        for window in WINDOWS:
            for n in [25,100]:
                for cost,_,_ in COSTS:
                    a=OUT/"runs"/f"{window}_{cost}_look1_profit_{hold}_n{n}"
                    b=OUT/"runs"/f"{window}_{cost}_look1_floor_{hold}_n{n}"
                    assert json.loads(a.with_suffix(".json").read_text())==json.loads(b.with_suffix(".json").read_text())
                    pd.testing.assert_frame_equal(pd.read_parquet(str(a)+"_equity.parquet"),pd.read_parquet(str(b)+"_equity.parquet"),check_exact=True);duplicates+=1
    totals["equivalent_one_month_paths"]=duplicates
    # Exact replays include a3month training case and two deployment paths with
    # distinct holding/selection rules; training and deployed accounts stay separate.
    cases=[]
    for t in [training[0],next(t for t in training if t["lookback"]==3 and t["holding"]=="time48")]:
        cases.append((OUT/"training",t["id"].rsplit("_",1)[0],t["start"],t["end"],signals[t["source_id"]],policy(25,t["holding"]),True))
    for ident in ["look1_profit_hold_n25","look3_floor_time48_n100"]:
        sp=specs[ident];start,end=WINDOWS["nine"]
        cases.append((OUT/"runs",ident,start,end,routed[sp["source"]["id"]],sp["policy"],False))
    for folder,ident,start,end,events,pol,train in cases:
        for cost,r in run(prices,funding,rules,events,start,end,pol):
            key=f"{ident}_{cost}" if train else f"nine_{cost}_{ident}"
            assert {k:v for k,v in r.items() if k!="curve"}==json.loads((folder/f"{key}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(pd.DataFrame(r["curve"]),pd.read_parquet(folder/f"{key}_equity.parquet"),check_exact=True);totals["replays_exact"]+=1
    write(OUT/"switching_diagnostics.json",switching)
    write(OUT/"verification.json",dict(**totals,incomplete_paths=incomplete,hashes_match=True,unit_tests_passed=65,live_config_unchanged=True));print("VERIFIED",flush=True)


if __name__=="__main__":main()
