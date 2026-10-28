"""Batch32: finite capital scaling of the frozen preselected pullback source."""
import pandas as pd
from account_capital_trace import simulate
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

OUT=ROOT/'artifacts/pullback_capacity_20260925'
PRIOR=ROOT/'artifacts/cross_pullback_20260925'
TIMING_PRIOR=ROOT/'artifacts/momentum_timing_20260925'
SIGNALS=PRIOR/'signals.json'


def definitions(previous):
    selected=next(x['strategy_id'] for x in previous['selected'] if x['reference']=='momentum')
    assert selected=='momentum_168h_raw_hold_price_n25_pull05'
    old=next(sp for sp in previous['specs'] if sp['id']==selected);result=[]
    for cap in [5,10,20,30]:
        for notional in [25,100,250]:
            result.append(dict(old,id=f'pull05_cap{cap}_n{notional}',reference='frozen_pull05',cap=cap,notional=notional,
                policy=dict(old['policy'],position_notional=notional),baseline=cap==5 and notional in [25,100]))
    return result


def main():
    OUT.mkdir(exist_ok=True);(OUT/'runs').mkdir(exist_ok=True)
    previous=read(PRIOR/'summary.json');specs=definitions(previous);spans=windows()
    protocol=dict(created_at=pd.Timestamp.now(tz='UTC').isoformat(),previous_turn_classification='progress:576crosspullbackpaths/42tests/114controls. Prespecified7dayrawmomentum25pull05 remainedselected;all50%monthlytargetsfailed.',
        hypothesis='Can finite-account capital deployment scale the frozen pullback edge toward50%monthly without losing monthly-start robustness?',
        intervention='Samefrozen Long/Short7dayrawmomentumsource,0.5ATR favorable wait1..23closedhours,3favorableparts,3ATR/1%trailing,noSL/noageclose. Cross5leverageunchanged. Onlymaxpositions5/10/20/30 andtotalpositionnotional25/100/250 vary;plannedmargin5/20/50respectively. Notionaltotalacrossall3parts,notperpart;notlinearPnLscaling. Enginechecksactualquantity/fees/funding/currentmarkedcapitalpluspendingtranchecommittedcapital. Cancellations andeverymargincheckobservedwithoutchangingfinanciallogic.',
        account='500USDT oneCrosswallet,onepositionpercoin,persistent20%entrypause,noautomaticresume,nocapitalinjection,nolivechanges. Openinglimitnotmandatoryfills;insufficientmarginrejectsentries/adds. ExistingpositionsstillMTM/fundingafterpause;CrossMMR1%proxycaninvalidatepath. Extra capacity/largersizes offlinealternatives,notoriginal5margin/5positions.',
        evaluation='4capacitiesx3budgetsx12windowsx2cost=288paths. ChoosescaleonSep-Mayalone:bothcostprofit,DD<20,20closed,complete,maxworstmonthlythenworstending. Lockbeforelater/rolling. All10three-monthstartsforeachscale;overlappinghistoricalreuse,notnewOOS.48cap5/25or100controls exactpriorfinancialoutputs afterremovingobservationaltrace.',
        target='Atleast50%netMTM EVERYcalendar month;notpositiveyear/window oraverage.',limitations=previous['protocol']['limitations'],
        specs=specs,windows=spans,costs=COSTS,prior_sha256=sha(PRIOR/'summary.json'),timing_prior_sha256=sha(TIMING_PRIOR/'summary.json'),signals_sha256=sha(SIGNALS),
        data_sha256=sha(DATA/'reconciled_manifest.json'),rules_sha256=sha(RULE_PATH),live_config_sha256=sha(ROOT/'configs/live.yaml'),
        source_sha256={n:sha(ROOT/'scripts'/n) for n in ['search_pullback_capacity.py','account_capital_trace.py','account_net_trailing_replay.py','frozen_extension_inputs.py']})
    write(OUT/'protocol.json',protocol)
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH)
    signals=read(SIGNALS)['momentum_168h_raw_pull05'];write(OUT/'signals.json',signals);results=[]
    for window,(start,end) in spans.items():
        for sp in specs:
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),grouped_signals([e for e in signals if e.get('source_at',e['at'])>=start],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(sp['cap'],fee,slip),research_policy=sp['policy'])
                r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct'
                row=summarize(r,sp['id'],sp['id'],sp['policy'],sp['cap'],cost,window);sides=side_metrics(r,r['curve'])
                row.update(id=f'{window}_{cost}_{sp["id"]}',strategy_id=sp['id'],reference=sp['reference'],exit=sp['exit'],notional=sp['notional'],baseline=sp['baseline'],source=sp['source'],holding=sp['holding'],timing=sp['timing'],cap=sp['cap'],
                    utilization=utilization(r['curve'],r,sp['notional'],sp['cap']),exit_diagnostics=exit_diagnostics(r),side_metrics=sides,
                    side_entries={side:rs['entries'] for side,rs in sides['sides'].items()},monthly=monthly_metrics(r['curve'],boundaries=[t for t in BOUNDARIES if start<=t<=end]),
                    margin_rejections=r['rejections'].get('insufficient_margin',0)+r['rejections'].get('add_insufficient_margin',0),candidates=sum(start<=e.get('source_at',e['at']) and e['at']<end for e in signals))
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
