"""Batch33: frozen-origin ATR dollar sizing with finite shared capital."""
import pandas as pd
from account_volatility_replay import simulate
from volatility_position_size import size_signals
from compare_account_risk import ROOT,sha,write,summarize,exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from capital_research_metrics import utilization
from directional_capacity_metrics import side_metrics
from monthly_account_metrics import monthly_metrics
from search_side_capacity import windows,robustness
from search_frozen_exits import BOUNDARIES,COSTS,DATA,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from search_net_trailing import read
from search_cross_regime import select

OUT=ROOT/'artifacts/volatility_size_20260925'
PRIOR=ROOT/'artifacts/pullback_capacity_20260925'
TIMING_PRIOR=ROOT/'artifacts/momentum_timing_20260925'
SIGNALS=PRIOR/'signals.json'


def definitions(previous):
    assert previous['selected']==[dict(reference='frozen_pull05',strategy_id='pull05_cap5_n25')]
    old=next(sp for sp in previous['specs'] if sp['id']=='pull05_cap5_n25');result=[]
    for cap in [5,10]:
        for mode,amount in [('fixed',25),('fixed',100),('atr_dollar',1),('atr_dollar',2.5),('atr_dollar',5)]:
            budget=amount if mode=='fixed' else 250
            key=mode+str(amount).replace('.','p')
            result.append(dict(old,id=f'vol_cap{cap}_{key}',reference='frozen_pull05',cap=cap,notional=budget,
                sizing=mode,amount=amount,sizing_key=key,
                policy=dict(old['policy'],position_notional=budget,event_sizing=True),baseline=mode=='fixed'))
    return result


def main():
    OUT.mkdir(exist_ok=True);(OUT/'runs').mkdir(exist_ok=True)
    previous=read(PRIOR/'summary.json');specs=definitions(previous);spans=windows()
    protocol=dict(created_at=pd.Timestamp.now(tz='UTC').isoformat(),previous_turn_classification='progress:288finitecapitalpaths/41tests/96capitalfixturesandcontrolchecks;7proxyhaltsat2times;zero50%monthlypasses.',
        hypothesis='Can equalizing frozen-origin ATR dollar exposure improve monthly expectancy and reduce concentration enough to approach50%netMTM eachmonth?',
        intervention='Samefrozen7daymomentumLongShort,pullback0.5ATR,3favorableparts,3ATR/1%trailing,noSL/noageclose. Budgetsfixed25/100controls vs ATR-dollar1/2.5/5: totalnotional=clip(amount*originalclosedprice/originalATR,25,250). OriginalATR14closed4h and originalclosedhourprice, not triggerprice/futurefill;lockbeforewaiting. Floor25/cap250 alter actualATRdollar exposure. Thisisnot lossatrisk/stoploss. No scalingwithaccountgrowth. Eachtrancheusesfrozenbudget/3 andchecksactualfilters;noauto-upsizing.',
        account='500USDT sharedCrossx5,5or10positions,onecoinoneposition,persistent20%DDopeningpause,keepheldMTM/fundingandtrail,noautoresume. Pendingtranchesreservedusingeachownbudget. Variable25to250notionalmeans5to50plannedmargin;offlinealternativeonly,nolivechanges.',
        evaluation='10specsx12windowsx2cost=240paths. ChooseoneglobalpolicyonSep-May:bothcostprofit/DD<20/20closed/complete,maxworstmonthlythenworstending. Lockbeforelater/rolling. All10three-monthstartsforallscales;overlappinghistorynotfreshOOS.96fixedsizecontrols exactpriorfinancialoutputsafteronlyremovingobservationalsizingmetadata.',
        target='Atleast50%netMTM EVERYcalendar month;notpositiveyear/window oraverage.',limitations=previous['protocol']['limitations'],
        specs=specs,windows=spans,costs=COSTS,prior_sha256=sha(PRIOR/'summary.json'),signals_sha256=sha(SIGNALS),
        data_sha256=sha(DATA/'reconciled_manifest.json'),rules_sha256=sha(RULE_PATH),live_config_sha256=sha(ROOT/'configs/live.yaml'),
        source_sha256={n:sha(ROOT/'scripts'/n) for n in ['search_volatility_size.py','account_volatility_replay.py','volatility_position_size.py','account_capital_trace.py','frozen_extension_inputs.py']})
    write(OUT/'protocol.json',protocol)
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH)
    source=read(SIGNALS);all_signals={sp['sizing_key']:size_signals(source,sp['sizing'],sp['amount']) for sp in specs};write(OUT/'signals.json',all_signals);results=[]
    for window,(start,end) in spans.items():
        for sp in specs:
            signals=all_signals[sp['sizing_key']]
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),grouped_signals([e for e in signals if e.get('source_at',e['at'])>=start],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(sp['cap'],fee,slip),research_policy=sp['policy'])
                r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct'
                row=summarize(r,sp['id'],sp['id'],sp['policy'],sp['cap'],cost,window);sides=side_metrics(r,r['curve'])
                row.update(id=f'{window}_{cost}_{sp["id"]}',strategy_id=sp['id'],reference=sp['reference'],exit=sp['exit'],notional=sp['notional'],baseline=sp['baseline'],source=sp['source'],holding=sp['holding'],timing=sp['timing'],cap=sp['cap'],sizing=sp['sizing'],amount=sp['amount'],
                    utilization=utilization(r['curve'],r,sp['notional'],sp['cap']),exit_diagnostics=exit_diagnostics(r),side_metrics=sides,
                    side_entries={side:rs['entries'] for side,rs in sides['sides'].items()},monthly=monthly_metrics(r['curve'],boundaries=[t for t in BOUNDARIES if start<=t<=end]),
                    margin_rejections=r['rejections'].get('insufficient_margin',0)+r['rejections'].get('add_insufficient_margin',0),candidates=sum(start<=e.get('source_at',e['at']) and e['at']<end for e in signals))
                entered={j['event_id'] for j in r['journal'] if j['kind']=='entry'}
                allocations=[e['planned_notional'] for e in signals if e['event_id'] in entered]
                risks=[e['planned_notional']*e['atr']/e['reference_close'] for e in signals if e['event_id'] in entered]
                row['sizing_metrics']=dict(mean_budget=sum(allocations)/len(allocations) if allocations else None,min_budget=min(allocations,default=None),max_budget=max(allocations,default=None),mean_origin_atr_dollars=sum(risks)/len(risks) if risks else None,floor_entries=sum(v==25 for v in allocations),cap_entries=sum(v==250 for v in allocations))
                row['target_met']=r['ending_equity'] is not None and row['monthly']['all_months_50pct']
                write(OUT/'runs'/f'{row["id"]}.json',{k:v for k,v in r.items() if k!='curve'});pd.DataFrame(r['curve']).to_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet',index=False);results.append(row)
            write(OUT/'progress.json',dict(window=window,runs=len(results)))
        print(window,'COMPLETE',len(results),flush=True)
        if window=='development':
            selected=select(specs,results);write(OUT/'candidate_lock.json',dict(selected=selected,locked_at=pd.Timestamp.now(tz='UTC').isoformat(),later_not_run_in_batch=True,pristine_oos=False));print('LOCKED',selected,flush=True)
    assert sha(ROOT/'configs/live.yaml')==protocol['live_config_sha256']
    write(OUT/'summary.json',dict(protocol=protocol,specs=specs,selected=selected,results=results,robustness=robustness(results),
        target_met_rows=sum(r['target_met'] for r in results),incomplete_paths=sum(r['ending_equity'] is None for r in results)))
    pd.DataFrame(results).to_csv(OUT/'comparison.csv',index=False);print('COMPLETE',len(results),flush=True)


if __name__=='__main__':main()
