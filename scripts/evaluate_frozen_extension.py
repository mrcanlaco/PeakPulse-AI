"""Evaluate previously frozen candidates on Jun-Aug with fresh and carried accounts."""

import json

import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import utilization
from compare_account_risk import ROOT,exchange_rules,sha,summarize,write
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from prepare_frozen_extension import OUT,FREEZE,START,END
from search_historical_entries import COSTS
from search_multitimeframe_rolling import grouped_signals
from short_entry_guards import features
from short_guard_ablation import decisions,apply_mask
from short_multitimeframe_signals import generate

from dao_vang.config.settings import ExecutionConfig

RESULTS=OUT/"evaluation"
BOUNDARIES=[int(t.timestamp()*1000) for t in pd.date_range("2025-09-01","2026-09-01",freq="MS",tz="UTC")]
WINDOWS={"continuous_year":(BOUNDARIES[0],BOUNDARIES[-1]),"fresh_june":(int(START.timestamp()*1000),int(END.timestamp()*1000))}


def main():
    RESULTS.mkdir(exist_ok=True);(RESULTS/"runs").mkdir(exist_ok=True)
    freeze=json.loads(FREEZE.read_text(encoding="utf-8"))
    for n,d in freeze["source_sha256"].items():assert sha(ROOT/"scripts"/n)==d
    protocol=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),candidate=freeze,candidate_sha256=sha(FREEZE),windows=WINDOWS,
                  new_period=[START.isoformat(),END.isoformat()],data_manifest_sha256=sha(OUT/"reconciled_manifest.json"),
                  source_sha256={n:sha(ROOT/"scripts"/n) for n in ["frozen_extension_inputs.py","evaluate_frozen_extension.py","account_scaled_replay.py","short_guard_ablation.py","short_entry_guards.py","short_multitimeframe_signals.py"]},
                  costs=COSTS,live_config_sha256=sha(ROOT/"configs/live.yaml"),
                  comparison="Six frozen policies x2costs x2windows=24paths. FreshJune equity500 versus continuousSep2025 equity500. Continuous new-period returns use actualJune1 marked equity as baseline, no reset or artificialclose. Report whole12months and new3months separately. Endpoint actions follow shared engine conventions; previous prefix comparison excludes old terminal boundary where futurebar now exists.",
                  limitations="Later calendar period already examined under other strategies. Fixed candidate evaluation is not pristine independentOOS. Same frozen30coin universe may omit delisted contracts; current filters,1%maintenanceproxy,5m sampled exits,assumedslippage. No live promotion.")
    write(RESULTS/"protocol.json",protocol)
    prices,funding,frames=load();signals=generate(frames,[freeze["source"]])[freeze["source"]["id"]]
    observed=decisions(signals,features(frames,funding));write(RESULTS/"signals.json",signals);write(RESULTS/"observations.json",observed)
    variants={}
    for mask in [0,2,15]:
        entries,counts=apply_mask(signals,observed,mask);variants[mask]=entries;write(RESULTS/f"entries_mask{mask:02d}.json",dict(entries=entries,counts=counts))
    rules=exchange_rules(RULE_PATH);assert not set(prices)-set(rules);rows=[]
    for spec in freeze["specs"]:
        for window,(start,end) in WINDOWS.items():
            groups=grouped_signals(variants[spec["guard"]["mask"]],start,end)
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),groups,lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                           ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
                r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                row=summarize(r,spec["id"],spec["id"],spec["policy"],5,cost,window)
                row.update(id=f"{window}_{cost}_{spec['id']}",strategy_id=spec["id"],mask=spec["guard"]["mask"],notional=spec["notional"],
                           utilization=utilization(r["curve"],r,spec["notional"]),
                           monthly=monthly_metrics(r["curve"],boundaries=[t for t in BOUNDARIES if start<=t<=end]))
                begin=next((p["equity"] for p in r["curve"] if p["at"]==WINDOWS["fresh_june"][0]),None)
                new_initial=500 if window=="fresh_june" else begin
                row["new_initial_equity"]=new_initial
                row["new_period_monthly"]=monthly_metrics(r["curve"],initial=new_initial,boundaries=BOUNDARIES[-4:]) if new_initial is not None else dict(complete=False,months=[],all_months_50pct=False)
                row["new_period_pnl"]=r["ending_equity"]-new_initial if r["ending_equity"] is not None and new_initial is not None else None
                row["target_met"]=r["ending_equity"] is not None and row["new_period_monthly"]["all_months_50pct"]
                row["all_history_target_met"]=r["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                write(RESULTS/"runs"/f"{row['id']}.json",{k:v for k,v in r.items() if k!="curve"})
                pd.DataFrame(r["curve"]).to_parquet(RESULTS/"runs"/f"{row['id']}_equity.parquet",index=False);rows.append(row)
                print("PATH",len(rows),"/24",row["id"],row["ending_equity"],flush=True)
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    write(RESULTS/"summary.json",dict(protocol=protocol,results=rows,target_met_rows=sum(r["target_met"] for r in rows),live_config_unchanged=True))
    pd.DataFrame(rows).to_csv(RESULTS/"comparison.csv",index=False)


if __name__=="__main__":main()
