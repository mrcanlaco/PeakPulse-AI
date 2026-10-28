"""Batch18: more simultaneous coins under the same finite shared account."""
import json
import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import utilization
from compare_account_risk import ROOT,sha,write,summarize,exchange_rules
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from search_frozen_exits import DATA,WINDOWS,BOUNDARIES,COSTS,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals

OUT=ROOT/"artifacts/capacity_expansion_20260925"
PRIOR=ROOT/"artifacts/reversal_flow_20260925"


def definitions(previous):
    result=[]
    for mask in [0,2]:
        for n in [25,100]:
            for hold in ["hold","time48"]:
                ref=next(p for p in previous["specs"] if p["id"]==f"mask{mask}_none_n{n}_{hold}")
                for cap in [5,10,20,30]:
                    result.append(dict(id=f"mask{mask}_n{n}_{hold}_cap{cap}",source=ref["source"],notional=n,holding=hold,cap=cap,policy=dict(ref["policy"]),baseline=cap==5,reference_id=ref["id"]))
    return result


def main():
    OUT.mkdir(exist_ok=True);(OUT/"runs").mkdir(exist_ok=True)
    old=json.loads((PRIOR/"summary.json").read_text(encoding="utf-8"));specs=definitions(old)
    protocol=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),specs=specs,windows=WINDOWS,costs=COSTS,
        previous_turn_classification="progress:432training+96deployment monthlyselectionpaths audited;source switchingdidnotfixoldinventory,65tests.",
        hypothesis="Slot scarcity versus additional correlated losing inventory: increaseconcurrentcoins withsamefrozenpriceevents and finite shared capital, never linearlyscaleoldPnL.",
        capacity="5/10/20/30 simultaneouscoins,onepositionpercoin,noDCA.30isnonbindingcoin-countlimitwithin frozen30universe,NOTinfinitecapital. Margin availability andunfilledtranchereserves remainenforced. Morethan5implementedonlyinofflineSimpleNamespace; productionExecutionConfig/schema/liveYAMLunchanged.",
        account="500USDT,Crossx5,25/100notionalforTOTAL3parts(5/20margin),favorableadds0.25ATRspace,6hexpiry,trail3ATR/1%. Keep20%persistentDDopeningpause andoldpositions. HoldwithoutSL/timeexit vs48hcloseincludinglosersasresearchalternative. Currentfilters,actualfunding,allopenMTM;noautomaticcompounding/topup.",
        evaluation="2frozenreversals(mask0/ret6mask2)x2sizesx2holdingx4caps=32policiesx3windowsx2cost=192paths. Fixed5slotcontrols mustexactlymatchprior48paths. No newbestcapchosenposthoc or pristineOOSclaim. No coinremoval.",
        target="50%netMTM EVERYcalendar month,notaverage/total/bestmonth. StopopeningDD20%doesnotcapongoinglosses.",
        limitations=old["protocol"]["limitations"]+" Increasedcorrelatedexposure makesmissinghistoricalmaintenancebracketsespeciallyimportant; if1%proxybreachedstopwithoutinventingendingbalance.",
        live_config_sha256=sha(ROOT/"configs/live.yaml"),rules_sha256=sha(RULE_PATH),data_sha256=sha(DATA/"reconciled_manifest.json"),prior_sha256=sha(PRIOR/"summary.json"),signals_sha256=sha(PRIOR/"signals.json"),
        source_sha256={n:sha(ROOT/"scripts"/n) for n in ["search_capacity_expansion.py","research_capacity_config.py","account_scaled_replay.py","capital_research_metrics.py","monthly_account_metrics.py","frozen_extension_inputs.py"]})
    write(OUT/"protocol.json",protocol)
    signals=json.loads((PRIOR/"signals.json").read_text(encoding="utf-8"));signals={k:v for k,v in signals.items() if k in ["mask0_none","mask2_none"]};write(OUT/"signals.json",signals)
    prices,funding,_=load();rules=exchange_rules(RULE_PATH);assert len(prices)==30
    results=[]
    for window,(start,end) in WINDOWS.items():
        groups={k:grouped_signals(v,start,end) for k,v in signals.items()}
        for i,spec in enumerate(specs,1):
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),groups[spec["source"]["id"]],lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(spec["cap"],fee,slip),research_policy=spec["policy"])
                r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                row=summarize(r,spec["id"],spec["id"],spec["policy"],spec["cap"],cost,window)
                row.update(id=f"{window}_{cost}_{spec['id']}",strategy_id=spec["id"],source=spec["source"],notional=spec["notional"],holding=spec["holding"],baseline=spec["baseline"],utilization=utilization(r["curve"],r,spec["notional"],spec["cap"]),exit_diagnostics=exit_diagnostics(r),monthly=monthly_metrics(r["curve"],boundaries=[t for t in BOUNDARIES if start<=t<=end]),peak_positions=max(p["positions"] for p in r["curve"]),insufficient_margin=r["rejections"].get("insufficient_margin",0))
                row["target_met"]=r["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                write(OUT/"runs"/f"{row['id']}.json",{k:v for k,v in r.items() if k!="curve"});pd.DataFrame(r["curve"]).to_parquet(OUT/"runs"/f"{row['id']}_equity.parquet",index=False);results.append(row)
            write(OUT/"progress.json",dict(window=window,finished=i,total=len(specs),runs=len(results)))
            if i%8==0:print(window,i,"/",len(specs),flush=True)
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    write(OUT/"summary.json",dict(protocol=protocol,specs=specs,results=results,target_met_rows=sum(r["target_met"] for r in results),incomplete_paths=sum(r["ending_equity"] is None for r in results)))
    pd.DataFrame(results).to_csv(OUT/"comparison.csv",index=False);print("COMPLETE",len(results),flush=True)


if __name__=="__main__":main()
