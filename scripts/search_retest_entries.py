"""Batch12: first-entry retest mechanisms at frozen staged budget and exit."""

import json
import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import utilization
from compare_account_risk import ROOT, exchange_rules, sha, summarize, write
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from search_entry_allocation import OUT as PRIOR
from search_frozen_exits import DATA, WINDOWS, BOUNDARIES, COSTS, exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from short_retest_entries import definitions as timings, transform
from short_entry_guards import features
from short_guard_ablation import decisions, apply_mask
from short_event_study import outcomes, statistics
from dao_vang.config.settings import ExecutionConfig

OUT=ROOT/"artifacts/retest_entries_20260925"


def definitions(previous):
    result=[]
    for mask in [0,2]:
        for n in [25,100]:
            ref=next(s for s in previous["specs"] if s["id"]==f"mask{mask:02d}_n{n}_trail_a3_c1_f025")
            for t in timings():
                result.append(dict(id=f"mask{mask:02d}_n{n}_{t['id']}",reference_id=ref["id"],mask=mask,notional=n,timing=t,
                    policy=dict(ref["policy"]),baseline=t["id"]=="immediate"))
    return result


def select(specs,results):
    selected=[]
    for m in [0,2]:
        for n in [25,100]:
            pool=[]
            for s in specs:
                if (s["mask"],s["notional"])!=(m,n):continue
                rs=[r for r in results if r["strategy_id"]==s["id"] and r["window"]=="development"]
                if len(rs)!=2 or not all(r["ending_equity"] is not None and r["monthly"]["complete"] and r["data_complete"] and r["max_drawdown"]<.2 and r["exits"]>=20 for r in rs):continue
                pool.append((min(r["monthly"]["min_monthly_return"] for r in rs),min(r["ending_equity"] for r in rs),s["id"]))
            if pool:selected.append(max(pool)[2])
    return selected


def prepare_entries(signals,prices,enriched,window):
    start,end=WINDOWS[window];result={}
    for timing in timings():
        triggers,watch=transform(signals,prices,start,end,timing)
        observations=decisions(triggers,enriched)
        for mask in [0,2]:
            entries,guard=apply_mask(triggers,observations,mask)
            complete=not watch["counts"].get("missing_data",0) and not any(guard.get(k,0) for k in ["missing_features","stale_features"])
            value=dict(entries=entries,watch=watch,observations=observations,guard=guard,data_complete=complete)
            result[(timing["id"],mask)]=value
    return result


def main():
    OUT.mkdir(exist_ok=True)
    for folder in ["runs","entries"]:(OUT/folder).mkdir(exist_ok=True)
    old=json.loads((PRIOR/"summary.json").read_text(encoding="utf-8"));specs=definitions(old)
    assert len(specs)==48
    protocol=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),specs=specs,windows=WINDOWS,costs=COSTS,
        previous_turn_classification="progress:288 entryallocation paths, tighter0.25ATR adds improvefullyear but not consistentlylater; first-entryrisk remains.",
        hypothesis="Wait for a failed recovery after initial downside instead of immediately shorting the source event. Does causal confirmation improve marked account performance after all costs?",
        timing="12 rules:immediate,delay60min,breakdown0.5ATR,rebound0.5ATR thenfall0.25ATR controls; 8new down0.25/0.5ATR x bounce0.25/0.5ATR xTTL6/24h, thenfall0.25ATR fromrunningrecovery peak. Three distinct completed5mbars fordown,bounce,failure; freezeATR/score atsource. Runninglowbeforebounce. Oneattempt peroriginalevent; nofutureopen inpredicates. Missingbar invalidates watch. At expiry cantrigger; at assessmentend cannot. No watch from before windowstart carried in.",
        entry_guard="Evaluate mask0 orret6<=0 usinglatestcompletedhourlyfeatures atACTUALtrigger, age<1h; missingcommonfeaturedata disclosed. A rejected guard discards watch, no retry. Virtual watches reserve nofunds orslots; marketordereligibility checked ontrigger.",
        account="500USDT,x5,cap5,notional25/100 fixed,threefavorableparts0.25ATRspacing,6hexpiry,trailing3ATR/1%,activationcancelsremainingparts. NoSL/timeexit.20%DDpersistent openingpause, existinginventorycontinues. No coinexclusions, no scaledPnLshortcut,allfees/funding/openMTM.",
        selection="48specs x3windows x2cost=288paths. RunSep-May developmentfirst; lock up tooneper(mask,size) by worst-costminimumcalendar-monthreturn, thenworstendingequity, amongcomplete data/paths,DD<20% and>=20closed tradesbothcosts. No gate relaxation. Jun-Aug alreadyinspected:retrospective,notpristineOOS. Return50%EVERYmonth stays completioncriterion, not selectionscore.",
        event_diagnostics="4h/24h fixedhorizon returns oftriggeredevents; not accountreturns. Reportcensored/missing and7dayalignedcrosscoinbootstrap2000. Intervalsnotcorrected formultiplecomparisons; no confidenceclaim basedonbest interval. Screens neverselectaccountpolicy.",
        limitations=old["protocol"]["limitations"],prior_sha256=sha(PRIOR/"summary.json"),data_sha256=sha(DATA/"reconciled_manifest.json"),
        signals_sha256=sha(DATA/"evaluation/signals.json"),live_config_sha256=sha(ROOT/"configs/live.yaml"),
        source_sha256={n:sha(ROOT/"scripts"/n) for n in ["search_retest_entries.py","short_retest_entries.py","short_entry_timing.py","short_entry_guards.py","short_guard_ablation.py","account_scaled_replay.py","frozen_extension_inputs.py","monthly_account_metrics.py","capital_research_metrics.py","short_event_study.py"]})
    write(OUT/"protocol.json",protocol)
    signals=json.loads((DATA/"evaluation/signals.json").read_text(encoding="utf-8"))
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);enriched=features(frames,funding)
    results=[];screens=[];selected=[]
    for window,(start,end) in WINDOWS.items():
        cache=prepare_entries(signals,prices,enriched,window)
        for (timing,mask),item in cache.items():
            write(OUT/"entries"/f"{window}_mask{mask:02d}_{timing}.json",item)
            for h in [4,24]:
                events,counts=outcomes(item["entries"],prices,funding,start,end,h)
                screens.append(dict(window=window,timing=timing,mask=mask,hours=h,counts=counts,data_complete=item["data_complete"],
                    cases={c:statistics(events,start,end,fee,slip) for c,fee,slip in COSTS}))
        for i,spec in enumerate(specs,1):
            es=cache[(spec["timing"]["id"],spec["mask"])];groups=grouped_signals(es["entries"],start,end)
            for cost,fee,slip in COSTS:
                result=simulate(list(range(start,end+1,300000)),groups,lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                    ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
                result["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                row=summarize(result,spec["id"],spec["id"],spec["policy"],5,cost,window)
                row.update(id=f"{window}_{cost}_{spec['id']}",strategy_id=spec["id"],reference_id=spec["reference_id"],timing=spec["timing"],mask=spec["mask"],notional=spec["notional"],baseline=spec["baseline"],
                    data_complete=es["data_complete"],watch_counts=es["watch"]["counts"],guard_counts=es["guard"],
                    utilization=utilization(result["curve"],result,spec["notional"]),exit_diagnostics=exit_diagnostics(result),
                    monthly=monthly_metrics(result["curve"],boundaries=[t for t in BOUNDARIES if start<=t<=end]))
                row["target_met"]=es["data_complete"] and result["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                write(OUT/"runs"/f"{row['id']}.json",{k:v for k,v in result.items() if k!="curve"})
                pd.DataFrame(result["curve"]).to_parquet(OUT/"runs"/f"{row['id']}_equity.parquet",index=False);results.append(row)
            write(OUT/"progress.json",dict(window=window,finished=i,total=len(specs),runs=len(results)))
            if i%8==0:print(window,i,"/",len(specs),flush=True)
        if window=="development":
            selected=select(specs,results)
            write(OUT/"candidate_lock.json",dict(locked_at=pd.Timestamp.now(tz="UTC").isoformat(),selected=selected,later_not_run_in_batch=True,pristine_oos=False))
            print("LOCKED",selected,flush=True)
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    write(OUT/"screens.json",screens)
    write(OUT/"summary.json",dict(protocol=protocol,specs=specs,selected=selected,results=results,
        target_met_rows=sum(r["target_met"] for r in results),incomplete_paths=sum(r["ending_equity"] is None for r in results),
        data_incomplete_paths=sum(not r["data_complete"] for r in results),live_config_unchanged=True))
    pd.DataFrame(results).to_csv(OUT/"comparison.csv",index=False);print("COMPLETE",len(results),flush=True)


if __name__=="__main__":main()
