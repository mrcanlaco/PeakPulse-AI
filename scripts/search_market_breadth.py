"""Batch13: weekly weakness and market breadth versus frozen reversal controls."""

import json
import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import utilization
from compare_account_risk import ROOT,exchange_rules,sha,summarize,write
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from search_entry_allocation import OUT as PRIOR
from search_frozen_exits import DATA,WINDOWS,BOUNDARIES,COSTS,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from short_market_breadth import definitions as source_specs,enrich,market_state,generate
from short_event_study import outcomes,statistics
from dao_vang.config.settings import ExecutionConfig

OUT=ROOT/"artifacts/market_breadth_20260925"


def definitions(previous):
    specs=[]
    for n in [25,100]:
        base=next(s for s in previous["specs"] if s["id"]==f"mask02_n{n}_trail_a3_c1_f025")
        for source in source_specs():
            for holding in ["hold","time168"]:
                policy=dict(base["policy"])
                if holding=="time168":policy["max_hold_hours"]=168
                specs.append(dict(id=f"{source['id']}_n{n}_{holding}",source=source,notional=n,holding=holding,policy=policy,baseline=False))
        for mask in [0,2]:
            ref=next(s for s in previous["specs"] if s["id"]==f"mask{mask:02d}_n{n}_trail_a3_c1_f025")
            specs.append(dict(id=f"benchmark_mask{mask}_n{n}",source=dict(id=f"benchmark_mask{mask}",ranking="reversal",regime="any" if mask==0 else "ret6",entry="immediate"),notional=n,holding="hold",policy=dict(ref["policy"]),baseline=True,reference_id=ref["id"]))
    return specs


def select(specs,rows):
    chosen=[]
    for n in [25,100]:
        for holding in ["hold","time168"]:
            pool=[]
            for s in specs:
                if s["baseline"] or (s["notional"],s["holding"])!=(n,holding):continue
                rs=[r for r in rows if r["strategy_id"]==s["id"] and r["window"]=="development"]
                if len(rs)!=2 or not all(r["ending_equity"] is not None and r["monthly"]["complete"] and r["max_drawdown"]<.2 and r["exits"]>=20 for r in rs):continue
                pool.append((min(r["monthly"]["min_monthly_return"] for r in rs),min(r["ending_equity"] for r in rs),s["id"]))
            if pool:chosen.append(max(pool)[2])
    return chosen


def main():
    OUT.mkdir(exist_ok=True)
    for folder in ["runs","features"]:(OUT/folder).mkdir(exist_ok=True)
    previous=json.loads((PRIOR/"summary.json").read_text(encoding="utf-8"));specs=definitions(previous);assert len(specs)==52
    protocol=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),specs=specs,windows=WINDOWS,costs=COSTS,
        previous_turn_classification="progress:288 firstentrypaths reject three-stage retest as stable edge; allfour selected lateraccounts lose.",
        hypothesis="Momentum and marketstate instead of more precise reversal timing. Short lagging altcoins when breadth weakens; compare raw weeklyperformance with beta-adjusted performance.",
        literature=[dict(url="https://www.nber.org/papers/w25882",scope="Market,size,momentum as cryptocurrency cross-sectional factors; does not validate this short-only Futures implementation or50% monthly."),dict(url="https://www.nber.org/papers/w24877",scope="Cryptocurrency time-series momentum evidence; inspiration only, not claimed replication.")],
        weekly_score="At each completed4hbar: raw logreturn fromt-192h tot-24h. Beta estimated from168hourly logreturn pairs endingt-24h, cov/var(ddof1),var>1e-12. beta7d=raw7d-beta*BTCsameperiodreturn. No intercept subtracted. Commoneligible universe has4hready72bars,ATR>0,24hquotevolume>=2m andfinitebothscores/beta. No beta clipping or future ranks.",
        market_state="Require>=24 of frozen30altcoins eligible. Rank raw7d orbeta7d ascending,average ties,pctrank<=20%,score<0. Breadth=fractioneligibleclosedbelow4hEMA60. Regimes:any;breadth>=60%;breadth>=75%AND BTC4hready/EMA20<EMA60/close<EMA20/ret24<0.",
        entry="At4hclosedbar: altEMA20<EMA60,close<EMA20,ret24<0. Scheduled orpullback(high>=EMA20 andclose<open). Percoin24h cooldown. Probabilityfield isscore only,not calibrated probability. Exact same frozen30coinuniverse, no coin removal.",
        account="500equity,x5,cap5,notional25/100fixed,three favorableparts0.25ATRspace/6hexpiry,trail3ATR/1%,20%persistentDDopeningpause. Two holdingpolicies:noSL/no time exit, orhypothetical168hmarketexit includinglosers. Timeexit is researchalternative tooriginal indefiniteholding; neverchange live. Reservependingparts,fees,funding andopenMTM. Currentfilters; no linearPnl scaling.",
        selection="48newpolicies plus4 frozenreversal controls=52specs x3windows x2cost=312paths. DevelopmentSep-May first; selectnewoneper(size,holding),complete/DD<20%/>=20closed eachcost, highest worst-costminimumcalendar-monthreturn thenendingequity. Laterhistoryalreadyinspected,notpristineOOS. No gate relaxation or coinexclusion.",
        event_diagnostics="4h/24h returns after signals; 7dayalignedcrosscoinblockbootstrap2000,notmultiple-testadjusted. Not accountreturns orselectioncriterion.",
        target="50%netmarkedgrowth inEVERYconsecutivecalendar month, not bestmonth,totaloraverage. No livepromotion basedonhistoricalfit.",
        limitations="Repeatedhistoricaltesting and frozen warehouse universe survivorship; currentexchangefilters,MMR1%proxy rather thanh istoricalbrackets,5msampling andassumedslippage/noorderbook. Research only.",
        prior_sha256=sha(PRIOR/"summary.json"),data_sha256=sha(DATA/"reconciled_manifest.json"),live_config_sha256=sha(ROOT/"configs/live.yaml"),
        benchmark_hashes={str(m):sha(DATA/"evaluation"/f"entries_mask{m:02d}.json") for m in [0,2]},
        source_sha256={n:sha(ROOT/"scripts"/n) for n in ["search_market_breadth.py","short_market_breadth.py","short_multitimeframe_signals.py","account_scaled_replay.py","frozen_extension_inputs.py","short_event_study.py","monthly_account_metrics.py","capital_research_metrics.py"]})
    write(OUT/"protocol.json",protocol)
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);enriched=enrich(frames);state,ranks=market_state(enriched);signals=generate(enriched,state,ranks)
    for coin,f in enriched.items():f.to_parquet(OUT/"features"/f"{coin}.parquet")
    state.to_parquet(OUT/"market.parquet")
    for m in [0,2]:signals[f"benchmark_mask{m}"]=json.loads((DATA/"evaluation"/f"entries_mask{m:02d}.json").read_text(encoding="utf-8"))["entries"]
    write(OUT/"signals.json",signals)
    results=[];screens=[];selected=[]
    for window,(start,end) in WINDOWS.items():
        groups={sid:grouped_signals(es,start,end) for sid,es in signals.items()}
        for sid,es in signals.items():
            for h in [4,24]:
                events,counts=outcomes(es,prices,funding,start,end,h)
                screens.append(dict(source_id=sid,window=window,hours=h,counts=counts,cases={c:statistics(events,start,end,fee,slip) for c,fee,slip in COSTS}))
        for i,spec in enumerate(specs,1):
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),groups[spec["source"]["id"]],lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                    ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
                r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                row=summarize(r,spec["id"],spec["id"],spec["policy"],5,cost,window)
                row.update(id=f"{window}_{cost}_{spec['id']}",strategy_id=spec["id"],source=spec["source"],notional=spec["notional"],holding=spec["holding"],baseline=spec["baseline"],reference_id=spec.get("reference_id"),
                    utilization=utilization(r["curve"],r,spec["notional"]),exit_diagnostics=exit_diagnostics(r),
                    monthly=monthly_metrics(r["curve"],boundaries=[t for t in BOUNDARIES if start<=t<=end]))
                row["target_met"]=r["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                write(OUT/"runs"/f"{row['id']}.json",{k:v for k,v in r.items() if k!="curve"})
                pd.DataFrame(r["curve"]).to_parquet(OUT/"runs"/f"{row['id']}_equity.parquet",index=False);results.append(row)
            write(OUT/"progress.json",dict(window=window,finished=i,total=len(specs),runs=len(results)))
            if i%8==0 or i==len(specs):print(window,i,"/",len(specs),flush=True)
        if window=="development":
            selected=select(specs,results)
            write(OUT/"candidate_lock.json",dict(locked_at=pd.Timestamp.now(tz="UTC").isoformat(),selected=selected,later_not_run_in_batch=True,pristine_oos=False))
            print("LOCKED",selected,flush=True)
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    write(OUT/"screens.json",screens)
    write(OUT/"summary.json",dict(protocol=protocol,specs=specs,selected=selected,results=results,target_met_rows=sum(r["target_met"] for r in results),incomplete_paths=sum(r["ending_equity"] is None for r in results),live_config_unchanged=True))
    pd.DataFrame(results).to_csv(OUT/"comparison.csv",index=False);print("COMPLETE",len(results),flush=True)


if __name__=="__main__":main()
