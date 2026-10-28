"""Shared research journal audit with independent fee/funding quantities."""
import json
import pandas as pd
from capital_research_metrics import audit_account,utilization
from execution_cost_attribution import attribute
from monthly_account_metrics import monthly_metrics
from search_frozen_exits import WINDOWS,BOUNDARIES,COSTS,exit_diagnostics


def audit_grid(out,summary,prices,funding,prior=None):
    schedule={c:{t:(rate,mark) for t,rate,mark in rows} for c,rows in funding.items()}
    specs={s["id"]:s for s in summary["specs"]};baselines=0;funding_checks=0;incomplete=[]
    for row in summary["results"]:
        raw=json.loads((out/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"));curve=pd.read_parquet(out/"runs"/f"{row['id']}_equity.parquet")
        start,end=WINDOWS[row["window"]];_,fee,slip=next(v for v in COSTS if v[0]==row["cost"])
        assert raw["initial_equity"]==500 and curve["at"].iloc[0]==start
        audit_account(raw,row["notional"]);assert utilization(curve,raw,row["notional"])==row["utilization"]
        assert exit_diagnostics(raw)==row["exit_diagnostics"]
        assert monthly_metrics(curve.to_dict("records"),boundaries=[t for t in BOUNDARIES if start<=t<=end])==row["monthly"]
        assert row["target_met"]==(raw["ending_equity"] is not None and row["monthly"]["all_months_50pct"])
        assert raw["ending_equity"]==row["ending_equity"] and raw["pnl"]==row["pnl"]
        a=attribute(raw,lambda c:prices[c])
        if raw["ending_equity"] is None:
            incomplete.append(row["id"]);assert raw["errors"] and not row["target_met"]
        else:
            assert a["complete"] and curve["at"].iloc[-1]==end
            assert abs(curve["equity"].iloc[-1]-raw["ending_equity"])<1e-7
            assert abs(a["slippage_paid"]-a["reference_turnover"]*slip/10000)<1e-6
        assert abs(sum(j.get("net",0) for j in raw["journal"])-raw["closed_trade_net"])<1e-7
        assert abs(sum(j["amount"] for j in raw["journal"] if j["kind"]=="funding")-raw["funding"])<1e-7
        qty={};active={};fees=0
        for j in raw["journal"]:
            if j["kind"]=="entry":active[j["symbol"]]=j["event_id"]
            if j["kind"] in ["entry","entry_add"]:
                qty[j["event_id"]]=qty.get(j["event_id"],0)+j["qty"];fees+=j["qty"]*j["price"]*fee
            elif j["kind"]=="funding":
                rate,mark=schedule[j["symbol"]][j["at"]];assert abs(j["amount"]-qty[active[j["symbol"]]]*rate*mark)<1e-8;funding_checks+=1
            elif "net" in j:fees+=qty.pop(j["event_id"])*j["price"]*fee;active.pop(j["symbol"])
        assert abs(fees-raw["fees"])<1e-7
        if curve.paused.any():
            first=curve.loc[curve.paused,"at"].iloc[0];assert curve.loc[curve["at"]>=first,"paused"].all()
            assert not any(j["kind"] in ["entry","entry_add"] and j["at"]>first for j in raw["journal"])
        ref=specs[row["strategy_id"]].get("reference_id")
        if ref and prior is not None:
            ident=f"{row['window']}_{row['cost']}_{ref}"
            assert raw==json.loads((prior/"runs"/f"{ident}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(prior/"runs"/f"{ident}_equity.parquet"),check_exact=True);baselines+=1
    return dict(journals_audited=len(summary["results"]),baseline_paths_exact=baselines,funding_quantities_checked=funding_checks,incomplete_paths=incomplete)
