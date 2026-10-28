"""Shared offline grid runner; never imports account credentials or live client."""
import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import utilization
from compare_account_risk import write,summarize
from monthly_account_metrics import monthly_metrics
from search_frozen_exits import WINDOWS,BOUNDARIES,COSTS,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from dao_vang.config.settings import ExecutionConfig


def run_grid(out,specs,signals,prices,funding,rules,select):
    (out/"runs").mkdir(exist_ok=True);results=[];selected=[]
    for window,(start,end) in WINDOWS.items():
        groups={k:grouped_signals(v,start,end) for k,v in signals.items()}
        for i,spec in enumerate(specs,1):
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),groups[spec["source"]["id"]],lambda c:prices.get(c,{}),rules,lambda c:funding[c],ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
                r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                row=summarize(r,spec["id"],spec["id"],spec["policy"],5,cost,window)
                row.update(id=f"{window}_{cost}_{spec['id']}",strategy_id=spec["id"],baseline=spec["baseline"],source=spec["source"],notional=spec["notional"],holding=spec["holding"],utilization=utilization(r["curve"],r,spec["notional"]),exit_diagnostics=exit_diagnostics(r),monthly=monthly_metrics(r["curve"],boundaries=[t for t in BOUNDARIES if start<=t<=end]))
                row["target_met"]=r["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                write(out/"runs"/f"{row['id']}.json",{k:v for k,v in r.items() if k!="curve"});pd.DataFrame(r["curve"]).to_parquet(out/"runs"/f"{row['id']}_equity.parquet",index=False);results.append(row)
            write(out/"progress.json",dict(window=window,finished=i,total=len(specs),runs=len(results)))
            if i%8==0 or i==len(specs):print(window,i,"/",len(specs),flush=True)
        if window=="development":
            selected=select(specs,results);write(out/"candidate_lock.json",dict(selected=selected,locked_at=pd.Timestamp.now(tz="UTC").isoformat(),later_not_run_in_batch=True,pristine_oos=False));print("LOCKED",selected,flush=True)
    return results,selected
