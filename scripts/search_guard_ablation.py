"""Batch08: all16 subsets of the frozen guard, no retrospective coin exclusions."""

import json

import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import utilization
from compare_account_risk import ROOT,exchange_rules,sha,summarize,write
from historical_research_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from prepare_historical_research import OUT as DATA
from search_historical_entries import BOUNDARIES,COSTS,SPANS
from search_multitimeframe_rolling import grouped_signals,rolling_windows
from short_entry_guards import features
from short_guard_ablation import definitions,decisions,apply_mask
from short_event_study import outcomes,statistics

from dao_vang.config.settings import ExecutionConfig

OUT=ROOT/"artifacts/guard_ablation_20260925"
PRIOR=ROOT/"artifacts/guarded_entries_20260925"
SIGNALS=ROOT/"artifacts/multitimeframe_rolling_20260925/signals.json"


def main():
    OUT.mkdir(exist_ok=True);(OUT/"runs").mkdir(exist_ok=True)
    old=json.loads((PRIOR/"summary.json").read_text(encoding="utf-8"))
    source=next(p for p in old["portfolio_specs"] if p["id"]=="overextension_reversal_immediate_anti_squeeze_n25_hold")
    specs=[dict(id=f"{d['id']}_n{n}",guard=d,notional=n,policy=dict(source["policy"],position_notional=n))
           for d in definitions() for n in [25,100]]
    protocol=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),source=source,specs=specs,costs=COSTS,windows=rolling_windows(),
        previous_turn="progress:96screens/256paths found improved full guard but no50%eachmonth, remaining long-held inventory.",
        question="Identify contribution and interaction of the four frozen entry predicates; not a new threshold search or a new independent holdout.",
        masks="All16 subsets:bit1 ret24<=10%;bit2 ret6<=0;bit4 actual settled24h funding>=-0.1%;bit8 0<ATR1h/close<=5%. Hourly closed data age<1h, funding known only after60s. Mask0 preserves no-guard control; all nonzero masks require common complete feature set to isolate predicates. Missing/stale data disclosed, never filled favorably. Mask15 must exactly reproduce prior guard.",
        replay="Frozen4h overextension source, immediate entry,3parts0.5ATR favorable steps/6h add expiry, trailing3sourceATR/1%callback, no SL/no time exit.500equity,cap5,x5,notional25 or100 total per episode. Persistent20%DD opening pause, MTM/funding continue. Current1%maintenance proxy, unrepresentableTP pause_hold.32policies x8windows x2cost=512full-account paths. No compounding, no live changes.",
        analysis="Report all subsets, paired full-minus-leave-one-out, singleton-minus-none and factorial mean inclusion differences across8matched subsets at fixedwindow/size/cost. These are deterministic backtest contrasts, not causal market estimates or independent statistical samples; positions compete for slots and path can change. Event4/24/72h screens at3nonoverlappingperiods accompany actualaccount results. Do not select a new live winner from same examined history.",
        target="At least50% marked net equity growth EACH consecutive month, not total period, average or only profitable3month windows.",
        limitations="Repeatedly inspected history, overlapping rolling starts, warehouse survivorship risk, current filters, no historic maintenance tiers/orderbook,5m sampled exits; no financially verified/live eligibility.",
        data_sha256=sha(DATA/"manifest.json"),signals_sha256=sha(SIGNALS),live_config_sha256=sha(ROOT/"configs/live.yaml"),
        source_sha256={n:sha(ROOT/"scripts"/n) for n in ["search_guard_ablation.py","short_guard_ablation.py","short_entry_guards.py","short_funding_flow_signals.py","account_scaled_replay.py","capital_research_metrics.py","short_event_study.py"]})
    write(OUT/"protocol.json",protocol)
    prices,funding,frames=load();enriched=features(frames,funding)
    signals=json.loads(SIGNALS.read_text(encoding="utf-8"))[source["entry"]["source"]["id"]]
    observations=decisions(signals,enriched);write(OUT/"observations.json",observations)
    variants={};screen=[]
    for d in definitions():
        entries,counts=apply_mask(signals,observations,d["mask"]);variants[d["mask"]]=entries
        write(OUT/f"entries_{d['id']}.json",dict(entries=entries,counts=counts))
        for window in ["development","validation","holdout"]:
            for hours in [4,24,72]:
                es,cs=outcomes(entries,prices,funding,*SPANS[window],hours)
                cases={c:statistics(es,*SPANS[window],fee,slip) for c,fee,slip in COSTS}
                screen.append(dict(mask=d["mask"],window=window,hours=hours,counts=cs,cases=cases))
    write(OUT/"screens.json",screen)
    rules=exchange_rules(RULE_PATH);assert not set(prices)-set(rules)
    results=[]
    for i,spec in enumerate(specs,1):
        for window,(start,end) in rolling_windows().items():
            groups=grouped_signals(variants[spec["guard"]["mask"]],start,end)
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),groups,lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                           ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
                r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                row=summarize(r,spec["id"],spec["id"],spec["policy"],5,cost,window)
                row.update(id=f"{window}_{cost}_{spec['id']}",strategy_id=spec["id"],mask=spec["guard"]["mask"],notional=spec["notional"],
                           utilization=utilization(r["curve"],r,spec["notional"]),
                           monthly=monthly_metrics(r["curve"],boundaries=[t for t in BOUNDARIES if start<=t<=end]))
                row["target_met"]=r["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                write(OUT/"runs"/f"{row['id']}.json",{k:v for k,v in r.items() if k!="curve"})
                pd.DataFrame(r["curve"]).to_parquet(OUT/"runs"/f"{row['id']}_equity.parquet",index=False);results.append(row)
        write(OUT/"progress.json",dict(finished=i,total=len(specs),runs=len(results)));print("POLICY",i,"/",len(specs),flush=True)
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    write(OUT/"summary.json",dict(protocol=protocol,specs=specs,results=results,target_met_rows=sum(r["target_met"] for r in results),live_config_unchanged=True))
    pd.DataFrame(results).to_csv(OUT/"comparison.csv",index=False);print("COMPLETE",len(results),flush=True)


if __name__=="__main__":main()
