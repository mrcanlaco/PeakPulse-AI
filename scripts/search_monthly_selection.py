"""Batch17: past-only monthly source selection; no reset of deployed inventory."""
import json
import itertools
from functools import lru_cache
import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import utilization
from compare_account_risk import ROOT,write,sha,summarize,exchange_rules
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from monthly_strategy_selection import choose,route,bounded_prices
from prepare_altcoin_search import RULE_PATH
from prepare_frozen_extension import OUT as DATA
from search_frozen_exits import COSTS,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from dao_vang.config.settings import ExecutionConfig

OUT=ROOT/"artifacts/monthly_selection_20260925"
PRIOR=ROOT/"artifacts/market_breadth_20260925"
SIGNAL_FILES={"breadth":PRIOR/"signals.json","rally":ROOT/"artifacts/failed_rally_20260925/signals.json","flow":ROOT/"artifacts/reversal_flow_20260925/signals.json"}
SOURCES={"reversal0":("breadth","benchmark_mask0"),"reversal6":("breadth","benchmark_mask2"),"weak7d":("breadth","raw7d_any_scheduled"),"beta_bear":("breadth","beta7d_breadth75_btc_scheduled"),"failed_rally":("rally","rally1_ttl6_any"),"flow_drop":("flow","mask0_drop5")}
DATES=pd.date_range("2025-12-01","2026-09-01",freq="MS",tz="UTC")
BOUNDARIES=[int(t.timestamp()*1000) for t in DATES]
WINDOWS=dict(nine=(BOUNDARIES[0],BOUNDARIES[-1]),later=(BOUNDARIES[6],BOUNDARIES[-1]))


def inputs():
    saved={k:json.loads(p.read_text(encoding="utf-8")) for k,p in SIGNAL_FILES.items()}
    return {k:saved[file][name] for k,(file,name) in SOURCES.items()}


@lru_cache(maxsize=4)
def policy(n,hold):
    old=json.loads((PRIOR/"summary.json").read_text(encoding="utf-8"))
    p=dict(next(s["policy"] for s in old["specs"] if s["id"]==f"benchmark_mask2_n{n}"))
    if hold=="time48":p["max_hold_hours"]=48
    return p


def selectors():
    return [dict(id=f"look{look}_{method}_{hold}",lookback=look,method=method,holding=hold) for look,method,hold in itertools.product([1,3],["profit","floor"],["hold","time48"])]


def definitions():
    specs=[]
    for selector in selectors():
        for n in [25,100]:specs.append(dict(id=f"{selector['id']}_n{n}",source=dict(id=selector["id"]),selector=selector,notional=n,holding=selector["holding"],policy=policy(n,selector["holding"]),baseline=False))
    for src,n,hold in itertools.product(["reversal0","reversal6"],[25,100],["hold","time48"]):
        specs.append(dict(id=f"static_{src}_n{n}_{hold}",source=dict(id=src),selector=None,notional=n,holding=hold,policy=policy(n,hold),baseline=True))
    return specs


def training_bounds(t,look):
    start=t-pd.DateOffset(months=look)
    ms=lambda x:int(x.timestamp()*1000)
    end=ms(t)-300000
    boundaries=[ms(x) for x in pd.date_range(start,t,freq="MS")][:-1]+[end]
    return ms(start),end,boundaries


def run(prices,funding,rules,signals,start,end,p):
    # Restrict access rather than just claiming that the replay ignores future.
    known={c:[r for r in rs if r[0]<=end] for c,rs in funding.items()}
    for cost,fee,slip in COSTS:
        r=simulate(list(range(start,end+1,300000)),grouped_signals(signals,start,end),bounded_prices(prices,end),rules,lambda c:known[c],ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=p)
        r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
        yield cost,r


def save_result(folder,ident,r):
    write(folder/f"{ident}.json",{k:v for k,v in r.items() if k!="curve"})
    pd.DataFrame(r["curve"]).to_parquet(folder/f"{ident}_equity.parquet",index=False)


def main():
    OUT.mkdir(exist_ok=True)
    for folder in ["training","runs"]:(OUT/folder).mkdir(exist_ok=True)
    specs=definitions();sels=selectors()
    p=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),specs=specs,selectors=sels,sources=SOURCES,windows=WINDOWS,
        previous_turn_classification="progress:240flowablationpaths audited;selectedfilterloseslater;64tests.",
        hypothesis="Adapt signalfamily to recent marked performance; stopnewentries ifnonepasses. Selection canneverremoveoldinventory orresetDDpeak.",
        training="For eachcalendar decisionDec2025throughAug2026:6frozenfamilies,1or3precedingcalendar months,500USDT/notional25/cap5;bothbase/stresscosts,holdor48hexit. Endtraining5minutesbeforedecision. Boundedpriceaccess rejectsanyfuturetime,fundingtruncated. Alltrainingopenpositionsmarked,notdropped. 9x6x2lookbacksx2holdsx2cost=432trainingpaths.",
        selection="Atmonthlyboundary chooseprofit(maxworstcostnetMTMPnL) orfloor(maxworstcostminimumtrainingmonthlyreturn),othermetricastiebreak,thenstablelexicalsourceid. Needcomplete,ending>500,DD<20%,>=5closed BOTHcosts. Elsecash/noNEWentriesforthatmonth. Finaltrainingmonthends5minutesearly. No tuning gatesafterresults. Bothdeployednotional25/100usetheSAMEselectiontrainedat25;100isresearchsizingstress,not separatelyoptimized.",
        routing="Reservefirst5minutesafterboundary fordecision;routeonlychosenfamilysignalsfromstart+5mininclusive toendexclusive. Preservefeatures/scores/order,namespaceeventidentitybysource. Deployedaccountsimulatedcontinuously:oldpositions/TP/funding/peak/pausecarriedacrossmonths;changingfamilydoesnotcloseinventory. Existingpendingaddskeeporiginal6hrules.",
        account="500USDT,Crossx5,cap5,3favorableparts0.25ATR,6hexpiry,trail3ATR/1%,20%persistentpause. HoldwithoutSL;48hexitincludinglosersresearchalternative. 16adaptive+8staticcontrols,2windows(ninemonthsDec-Aug;freshJun-Aug),2cost=96deployedpaths. No retrospective coin exclusions.",
        target="50% netmarkedgrowth EVERY calendar month,notbest/total/average. Past-onlyroutingdoesnotmakepreviouslyreusedhistorypristineOOS;poolitselfdevelopedonthishistory. Researchonly,needfreshfutureevidence.",
        limitations="Repeatedresearch and poolselectionbias,currentfilters,MMR1%proxy,5msampling,assumedslippage/noorderbook,possibleuniverse survivorship.",
        live_config_sha256=sha(ROOT/"configs/live.yaml"),data_sha256=sha(DATA/"reconciled_manifest.json"),prior_sha256=sha(PRIOR/"summary.json"),signal_hashes={k:sha(v) for k,v in SIGNAL_FILES.items()},source_sha256={n:sha(ROOT/"scripts"/n) for n in ["monthly_strategy_selection.py","search_monthly_selection.py","account_scaled_replay.py","frozen_extension_inputs.py","monthly_account_metrics.py","capital_research_metrics.py"]})
    write(OUT/"protocol.json",p);prices,funding,_=load();rules=exchange_rules(RULE_PATH);signals=inputs();training=[];choices={s["id"]:[] for s in sels}
    for dt,nextdt in zip(DATES,DATES[1:]):
        for look,hold in itertools.product([1,3],["hold","time48"]):
            start,end,bounds=training_bounds(dt,look);rs=[]
            for source,entries in signals.items():
                for cost,r in run(prices,funding,rules,entries,start,end,policy(25,hold)):
                    ident=f"{dt.strftime('%Y%m')}_look{look}_{hold}_{source}_{cost}"
                    row=dict(id=ident,source_id=source,cost=cost,decision_at=int(dt.timestamp()*1000),start=start,end=end,lookback=look,holding=hold,
                        ending_equity=r["ending_equity"],max_drawdown=r["sampled_max_drawdown"],exits=sum("net" in j for j in r["journal"]),monthly=monthly_metrics(r["curve"],boundaries=bounds))
                    save_result(OUT/"training",ident,r);training.append(row);rs.append(row)
            for sel in sels:
                if sel["lookback"]==look and sel["holding"]==hold:
                    choices[sel["id"]].append(dict(start=int(dt.timestamp()*1000),end=int(nextdt.timestamp()*1000),training_end=end,source_id=choose(rs,sel["method"]),training_ids=[r["id"] for r in rs]))
        write(OUT/"training_summary.json",training);write(OUT/"choices.json",choices);print("DECISION",dt.strftime("%Y-%m"),"TRAINED",len(training),flush=True)
    combined=dict(signals)
    for sel in sels:combined[sel["id"]]=route(signals,choices[sel["id"]])
    write(OUT/"routed_signals.json",combined);rows=[]
    for window,(start,end) in WINDOWS.items():
        for i,spec in enumerate(specs,1):
            for cost,r in run(prices,funding,rules,combined[spec["source"]["id"]],start,end,spec["policy"]):
                row=summarize(r,spec["id"],spec["id"],spec["policy"],5,cost,window)
                row.update(id=f"{window}_{cost}_{spec['id']}",strategy_id=spec["id"],source=spec["source"],notional=spec["notional"],holding=spec["holding"],baseline=spec["baseline"],utilization=utilization(r["curve"],r,spec["notional"]),exit_diagnostics=exit_diagnostics(r),monthly=monthly_metrics(r["curve"],boundaries=[t for t in BOUNDARIES if start<=t<=end]))
                row["target_met"]=r["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                save_result(OUT/"runs",row["id"],r);rows.append(row)
            if i%8==0:print(window,i,"/",len(specs),flush=True)
    assert sha(ROOT/"configs/live.yaml")==p["live_config_sha256"]
    write(OUT/"summary.json",dict(protocol=p,specs=specs,results=rows,target_met_rows=sum(r["target_met"] for r in rows),incomplete_paths=sum(r["ending_equity"] is None for r in rows),training_paths=len(training)))
    pd.DataFrame(rows).to_csv(OUT/"comparison.csv",index=False);print("COMPLETE",len(rows),flush=True)


if __name__=="__main__":main()
