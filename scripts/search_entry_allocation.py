"""Batch11: matched planned capital, six entry mechanisms and two exits."""

import json

import pandas as pd
from account_entry_replay import simulate
from capital_research_metrics import utilization
from compare_account_risk import ROOT, exchange_rules, sha, summarize, write
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from search_frozen_exits import OUT as PRIOR, DATA, WINDOWS, BOUNDARIES, COSTS, exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from dao_vang.config.settings import ExecutionConfig

OUT=ROOT/"artifacts/entry_allocation_20260925"


def definitions(previous):
    modes=[("single",dict(entry_parts=1,entry_mode="single")),
           ("f025",dict(entry_parts=3,entry_mode="favorable",entry_step_atr=.25)),
           ("f05",dict(entry_parts=3,entry_mode="favorable",entry_step_atr=.5)),
           ("time30",dict(entry_parts=3,entry_mode="time",entry_interval_minutes=30)),
           ("pullback",dict(entry_parts=3,entry_mode="pullback",entry_step_atr=.5,pullback_atr=.25)),
           ("keep",dict(entry_parts=3,entry_mode="favorable",entry_step_atr=.5,cancel_adds_on_trail_activation=False))]
    result=[]
    for old in previous["specs"]:
        if old["exit"]["id"] not in ["trail_a0.5_c0.25","trail_a3_c1"]:continue
        for entry,params in modes:
            result.append(dict(id=f"{old['id']}_{entry}",reference_id=old["id"],entry=entry,exit=old["exit"],
                               mask=old["mask"],notional=old["notional"],policy=dict(old["policy"],**params),baseline=entry=="f05"))
    return result


def select(specs,rows):
    """Lock by development only; select nothing if no complete, DD<20% pair."""
    selected=[]
    for mask in [0,2]:
        for n in [25,100]:
            pool=[]
            for s in specs:
                if (s["mask"],s["notional"])!=(mask,n):continue
                rs=[r for r in rows if r["strategy_id"]==s["id"] and r["window"]=="development"]
                if len(rs)!=2 or not all(r["ending_equity"] is not None and r["monthly"]["complete"] and r["max_drawdown"]<.2 for r in rs):continue
                pool.append((min(r["monthly"]["min_monthly_return"] for r in rs),min(r["ending_equity"] for r in rs),s["id"]))
            if pool:selected.append(max(pool)[2])
    return selected


def main():
    OUT.mkdir(exist_ok=True);(OUT/"runs").mkdir(exist_ok=True)
    old=json.loads((PRIOR/"summary.json").read_text(encoding="utf-8"));specs=definitions(old)
    assert len(specs)==48
    protocol=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),specs=specs,windows=WINDOWS,costs=COSTS,
        previous_turn_classification="progress:384 exit paths audited. Early activation reduced exposure to onepart and raised turnover without reaching50% monthly.",
        hypothesis="Is first-fill timing or under-allocation responsible? Compare six entry mechanisms at the same planned notional and existing exit thresholds. Full account replay including path-dependent positions and capital.",
        entries="single fullsize; 3parts after favorable0.25ATR; favorable0.5ATR baseline; after30/60minutes only if observedclose<=averageentry; pullback after favorable0.5ATR perpart then rebound0.25ATR, stillclose<=averageentry, reset observedlow after eachadd; favorable0.5ATR keeping pendingadds after trailing activation. Sixhour expiry, oneadd per5m, no more than3parts. Signals and frozenATR unchanged. Actual nextopen gaps may be adverse; never filter based on future price.",
        exits="Two existing sampled trailing regimes: activation0.5ATR/callback0.25%, activation3ATR/callback1%. Default cancels pendingadds onactivation; keep variant preserves them until expiry, pause or exit. Same-step exit takes priority. Activation price and trailing low are not reset after adds. NoSL/timeexit.",
        budget="equity500,x5,cap5,plannednotional25/100 (margin5/20). Singleentry requires1/3 quantity admissible initially to matchsplitselection. Reserve pendingtranches.20%DDpause persists; no auto-resume. Actualfilledsizes differ bydesign. No DCAabove observedaverage; no increasing totalbudget.",
        chronology="48specs x3windows x2cost=288paths. Run development first, lock up toone per(mask,size) by worst-cost minimumcalendar-monthreturn thenworstendingequity; requirecompleteandDD<20%inbothcosts. Negative return candidates are diagnostic, not approved strategies. Laterhistory alreadyseen; never claim cleanOOS or select onlater results.",
        target="Atleast50% netmarked growth in EVERY consecutivecalendar month, not total or average. Allopeninventory counted, no exclusions.",
        limitations=old["protocol"]["limitations"],prior_sha256=sha(PRIOR/"summary.json"),data_sha256=sha(DATA/"reconciled_manifest.json"),
        input_hashes={str(m):sha(DATA/"evaluation"/f"entries_mask{m:02d}.json") for m in [0,2]},live_config_sha256=sha(ROOT/"configs/live.yaml"),
        source_sha256={n:sha(ROOT/"scripts"/n) for n in ["account_scaled_replay.py","account_entry_replay.py","search_entry_allocation.py","frozen_extension_inputs.py","monthly_account_metrics.py","capital_research_metrics.py"]},
        tests=dict(passed=84,command="pytest tests/unit/scripts/test_account_entry_replay.py tests/unit/scripts/test_account_scaled_replay.py tests/unit/scripts/test_account_backtest_replay.py tests/unit/scripts/test_capital_research_metrics.py -q"))
    write(OUT/"protocol.json",protocol)
    prices,funding,_=load();rules=exchange_rules(RULE_PATH)
    entries={m:json.loads((DATA/"evaluation"/f"entries_mask{m:02d}.json").read_text(encoding="utf-8"))["entries"] for m in [0,2]}
    groups={(m,w):grouped_signals(entries[m],start,end) for m in entries for w,(start,end) in WINDOWS.items()}
    results=[];selected=[]
    for window,(start,end) in WINDOWS.items():
        for i,spec in enumerate(specs,1):
            for cost,fee,slip in COSTS:
                result=simulate(list(range(start,end+1,300000)),groups[(spec["mask"],window)],lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                                ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
                result["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                row=summarize(result,spec["id"],spec["id"],spec["policy"],5,cost,window)
                row.update(id=f"{window}_{cost}_{spec['id']}",strategy_id=spec["id"],reference_id=spec["reference_id"],entry=spec["entry"],
                    mask=spec["mask"],notional=spec["notional"],exit=spec["exit"],baseline=spec["baseline"],utilization=utilization(result["curve"],result,spec["notional"]),
                    exit_diagnostics=exit_diagnostics(result),monthly=monthly_metrics(result["curve"],boundaries=[t for t in BOUNDARIES if start<=t<=end]))
                row["target_met"]=result["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                write(OUT/"runs"/f"{row['id']}.json",{k:v for k,v in result.items() if k!="curve"})
                pd.DataFrame(result["curve"]).to_parquet(OUT/"runs"/f"{row['id']}_equity.parquet",index=False);results.append(row)
            write(OUT/"progress.json",dict(window=window,finished=i,total=len(specs),runs=len(results)))
            if i%8==0:print(window,i,"/",len(specs),flush=True)
        if window=="development":
            selected=select(specs,results)
            write(OUT/"candidate_lock.json",dict(locked_at=pd.Timestamp.now(tz="UTC").isoformat(),selected=selected,later_not_run_in_batch=True,pristine_oos=False))
            print("LOCKED",selected,flush=True)
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    write(OUT/"summary.json",dict(protocol=protocol,specs=specs,selected=selected,results=results,target_met_rows=sum(r["target_met"] for r in results),
        incomplete_paths=sum(r["ending_equity"] is None for r in results),live_config_unchanged=True))
    pd.DataFrame(results).to_csv(OUT/"comparison.csv",index=False)
    print("COMPLETE",len(results),flush=True)


if __name__=="__main__":main()
