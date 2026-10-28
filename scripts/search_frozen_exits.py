"""Batch10: retrospective exit/turnover sensitivity on the verified full year."""

import json

import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import utilization
from compare_account_risk import ROOT,exchange_rules,sha,summarize,write
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from prepare_frozen_extension import OUT as DATA,FREEZE
from search_historical_entries import COSTS
from dao_vang.config.settings import ExecutionConfig
from search_multitimeframe_rolling import grouped_signals

OUT=ROOT/"artifacts/frozen_exit_search_20260925"
PRIOR=DATA/"evaluation"
BOUNDARIES=[int(t.timestamp()*1000) for t in pd.date_range("2025-09-01","2026-09-01",freq="MS",tz="UTC")]
WINDOWS=dict(development=(BOUNDARIES[0],BOUNDARIES[9]),later=(BOUNDARIES[9],BOUNDARIES[-1]),year=(BOUNDARIES[0],BOUNDARIES[-1]))


def definitions(freeze):
    exits=[dict(id=f"trail_a{a:g}_c{c:g}",trailing=True,activation_atr=a,callback_fraction=c/100)
           for a in [.5,1,2,3] for c in [.25,.5,1]]
    exits += [dict(id=f"tp{p:g}",trailing=False,fixed_tp_usdt=p) for p in [.5,1,2,5]]
    specs=[]
    for mask in [0,2]:
        for n in [25,100]:
            reference=next(p for p in freeze["specs"] if p["guard"]["mask"]==mask and p["notional"]==n)
            for exit in exits:
                policy=dict(reference["policy"])
                for key in ["activation_atr","callback_fraction","trailing","fixed_tp_usdt"]:policy.pop(key,None)
                policy.update({k:v for k,v in exit.items() if k!="id"})
                specs.append(dict(id=f"mask{mask:02d}_n{n}_{exit['id']}",mask=mask,notional=n,exit=exit,policy=policy,
                                  baseline=exit["id"]=="trail_a3_c1"))
    return specs


def exit_diagnostics(result):
    exits=[j for j in result["journal"] if "net" in j]
    activated=[j for j in result["journal"] if j["kind"]=="trail_activated"]
    trailed=[j for j in exits if j["kind"]=="trailing_exit"]
    return dict(activations=len(activated),trailing_exits=len(trailed),negative_trailing_exits=sum(j["net"]<0 for j in trailed),
                all_exits=len(exits),closed_net=sum(j["net"] for j in exits),
                mean_exit_net=sum(j["net"] for j in exits)/len(exits) if exits else None,
                still_open_unactivated=sum(not p["trail_active"] for p in result["open_positions"]),
                mean_closed_filled_parts=sum(j.get("filled_parts",0) for j in trailed)/len(trailed) if trailed else None)


def main():
    OUT.mkdir(exist_ok=True);(OUT/"runs").mkdir(exist_ok=True)
    freeze=json.loads(FREEZE.read_text(encoding="utf-8"));specs=definitions(freeze)
    protocol=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),specs=specs,windows=WINDOWS,costs=COSTS,
        previous_turn="progress: frozenJun-Aug evaluation underperformedno-filter, allfreshAugustreturnsnegative; inventory persisted219days.",
        changes="Frozen4h overextension source, masks0/2,notional25/100,total3parts,cap5,equity500,x5.12trailingexits activation0.5/1/2/3ATR xcallback0.25/0.5/1percent;4fixednetTP0.5/1/2/5USDT. NoSL/timeexit.64specs x3windows x2cost=384paths. All candidateorders recomputed, no linearPnl scaling.",
        interaction="Earlytrailingactivation cancels future entryparts by existingpolicy; outcome can include smallerfilledsize. FixedTP monetarytarget is plannedfor3parts and scaled byactualfilledparts. Same exchangeeligibility/ATRminimumtarget calculationexceptfixedTP bypassesATRtargetminimum; disclose changed eligiblefills. LIMIT fixedTP usesclosedpricecross and fills atlimit, no orderbookqueue/partialfill; trailing buysnextopenplusadverseslip. Not a clean liveexecution comparison.",
        chronology="All64specs runSep-May first. Lock one per(mask,notional) by highest worst-costminimumcalendar-monthreturn, then worst-costendingequity, among completepaths. Negativecandidates allowed onlyfor diagnosis. Then runalllockedandnonlocked choices onJun-Augandfullyear forcomplete sensitivity, never reselectonlater. Jun-Augwas already inspected; laterresultsare retrospective,not new pristineOOS.",
        target="Atleast50% netmarkedgrowth inEACH consecutivecalendar month. Report full12months andfreshJun3months separately; profitabletotal orhighwinrate is insufficient.",
        limitations="Repeatedhistoricaltesting,currentfilters,1%maintenanceproxy,5msampling,noorderbook,warehouse survivorship. No livepromotion or guarantee.",
        candidate_sha256=sha(FREEZE),signals_sha256=sha(PRIOR/"signals.json"),data_sha256=sha(DATA/"reconciled_manifest.json"),
        live_config_sha256=sha(ROOT/"configs/live.yaml"),source_sha256={n:sha(ROOT/"scripts"/n) for n in ["search_frozen_exits.py","account_scaled_replay.py","frozen_extension_inputs.py","capital_research_metrics.py","monthly_account_metrics.py"]})
    write(OUT/"protocol.json",protocol)
    prices,funding,_=load();rules=exchange_rules(RULE_PATH);assert not set(prices)-set(rules)
    variants={m:json.loads((PRIOR/f"entries_mask{m:02d}.json").read_text(encoding="utf-8"))["entries"] for m in [0,2]}
    groups={(m,w):grouped_signals(variants[m],start,end) for m in variants for w,(start,end) in WINDOWS.items()}
    results=[];selected=[]
    for window,(start,end) in WINDOWS.items():
        for i,spec in enumerate(specs,1):
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),groups[(spec["mask"],window)],lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                           ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
                r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                row=summarize(r,spec["id"],spec["id"],spec["policy"],5,cost,window)
                row.update(id=f"{window}_{cost}_{spec['id']}",strategy_id=spec["id"],mask=spec["mask"],notional=spec["notional"],exit=spec["exit"],baseline=spec["baseline"],
                           utilization=utilization(r["curve"],r,spec["notional"]),exit_diagnostics=exit_diagnostics(r),
                           monthly=monthly_metrics(r["curve"],boundaries=[t for t in BOUNDARIES if start<=t<=end]))
                row["target_met"]=r["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                write(OUT/"runs"/f"{row['id']}.json",{k:v for k,v in r.items() if k!="curve"})
                pd.DataFrame(r["curve"]).to_parquet(OUT/"runs"/f"{row['id']}_equity.parquet",index=False);results.append(row)
            if i%8==0:print(window,i,"/",len(specs),flush=True)
            write(OUT/"progress.json",dict(window=window,finished=i,total=len(specs),runs=len(results)))
        if window=="development":
            for mask in [0,2]:
                for n in [25,100]:
                    candidates=[]
                    for spec in specs:
                        if spec["mask"]!=mask or spec["notional"]!=n:continue
                        rs=[r for r in results if r["strategy_id"]==spec["id"]]
                        if len(rs)!=2 or any(r["ending_equity"] is None or not r["monthly"]["complete"] for r in rs):continue
                        candidates.append((min(r["monthly"]["min_monthly_return"] for r in rs),min(r["ending_equity"] for r in rs),spec["id"]))
                    if candidates:selected.append(max(candidates)[2])
            write(OUT/"candidate_lock.json",dict(locked_at=pd.Timestamp.now(tz="UTC").isoformat(),selected=selected,later_not_evaluated_in_this_batch=True,
                caveat="Laterhistoryhasalreadybeenexaminedinotherbatches; thisisretrospectiveresearch."))
            print("LOCKED",selected,flush=True)
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    write(OUT/"summary.json",dict(protocol=protocol,specs=specs,selected=selected,results=results,target_met_rows=sum(r["target_met"] for r in results),live_config_unchanged=True))
    pd.DataFrame(results).to_csv(OUT/"comparison.csv",index=False);print("COMPLETE",len(results),flush=True)


if __name__=="__main__":main()
