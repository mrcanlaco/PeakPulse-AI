"""Batch28: momentum invalidation exits on frozen7day Long/Short entries."""
import pandas as pd
from account_signal_exit_replay import simulate
from signal_lifecycle import calendar,MODES
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

OUT=ROOT/'artifacts/signal_lifecycle_20260925'
PRIOR=ROOT/'artifacts/cross_exposure_20260925'
SIGNALS=ROOT/'artifacts/cross_sectional_20260925/signals.json'


def definitions(previous):
    result=[]
    for old in previous['specs']:
        if old['gate']!='none' or old['holding']!='hold':continue
        for exit in ['hold','time168',*MODES]:
            policy=dict(old['policy'])
            if exit=='time168':policy['max_hold_hours']=168
            elif exit in MODES:policy['signal_exit']=exit
            result.append(dict(old,id=old['reference']+'_'+exit,reference=old['reference'],exit=exit,holding=exit,
                policy=policy,baseline=exit=='hold',parent_id=old['id']))
    assert len(result)==12
    return result


def main():
    OUT.mkdir(exist_ok=True);(OUT/'runs').mkdir(exist_ok=True)
    previous=read(PRIOR/'summary.json');specs=definitions(previous);spans=windows()
    protocol=dict(created_at=pd.Timestamp.now(tz='UTC').isoformat(),previous_turn_classification='progress:288exposurepaths/33tests/96exactcontrols. Entry dollarbalancing didnot prevent retainedlosers;freshJune25net1closed+13.03/open-34.55.',
        hypothesis='Close a held momentum position when its signed historical return becomes nonpositive; test whether retiring stale trends improves turnover and netmonthlyreturn.',
        intervention='Daily00UTC only using completeclosedhourly data. Long exits if logreturn<=0;Short if>=0. Horizons24/72/168hours. sign168x2 requires two successive daily invalid readings strictly after entry. Missing anyrequiredclosedbar invalidates path; no favorablefill. Funding throughcurrenttime first,then signalexit before trailing/adds; execute actualnextopen adverse slip. Applies evenwhenDDpaused. No synthetic reverse/reentry samecoinonexitstep. Hold/time168 controls retained.',
        account='500USDT Crossx5,5sharedslots,3favorableparts0.25ATR/6h,25totalnotional(default5margin) or100(research20margin). Frozen7dayrawmomentum daily entries,3ATR/1%trailing,fees/funding/MTM,persistent20%entrypause. Newsignalexit andtime168 CANclose losing positions; offlinealternatives to originalnoSL/noagelossclose. No livechanges.',
        evaluation='6exitpolicies x2sizes x12windows x2cost=288paths. Allfrozenbeforeexecution. ChooseoneexitpersizeonSep-May alone:bothcostprofit,DD<20%,20closed,complete,maxworstmonthlythenworstending. LockbeforeJun-Aug/rolling. Ten3monthstartsSep2025-Jun2026 forEVERYpolicy; overlapping,alreadyresearchedhistory,notnewOOS.48holdcontrols exactbatch27;6time168n25maincontrols exactbatch25.',
        target='Atleast50%netMTM EVERYcalendar month;notpositiveyear/window oraverage.',limitations=previous['protocol']['limitations'],
        specs=specs,windows=spans,costs=COSTS,prior_sha256=sha(PRIOR/'summary.json'),signals_sha256=sha(SIGNALS),
        data_sha256=sha(DATA/'reconciled_manifest.json'),rules_sha256=sha(RULE_PATH),live_config_sha256=sha(ROOT/'configs/live.yaml'),
        source_sha256={n:sha(ROOT/'scripts'/n) for n in ['search_signal_lifecycle.py','account_signal_exit_replay.py','signal_lifecycle.py','account_net_trailing_replay.py','frozen_extension_inputs.py']})
    write(OUT/'protocol.json',protocol)
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);states=calendar(frames);write(OUT/'exit_calendar.json',states)
    signals=read(SIGNALS);results=[]
    for window,(start,end) in spans.items():
        for sp in specs:
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),grouped_signals(signals[sp['source']],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(5,fee,slip),research_policy=sp['policy'],exit_calendar=states)
                r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct'
                row=summarize(r,sp['id'],sp['id'],sp['policy'],5,cost,window);sides=side_metrics(r,r['curve'])
                row.update(id=f'{window}_{cost}_{sp["id"]}',strategy_id=sp['id'],reference=sp['reference'],exit=sp['exit'],notional=sp['notional'],baseline=sp['baseline'],source=sp['source'],holding=sp['holding'],
                    utilization=utilization(r['curve'],r,sp['notional'],5),exit_diagnostics=exit_diagnostics(r),side_metrics=sides,
                    side_entries={side:rs['entries'] for side,rs in sides['sides'].items()},monthly=monthly_metrics(r['curve'],boundaries=[t for t in BOUNDARIES if start<=t<=end]),
                    signal_exits=sum(j['kind']=='signal_exit' for j in r['journal']),negative_signal_exits=sum(j['kind']=='signal_exit' and j['net']<0 for j in r['journal']),
                    signal_exit_net=sum(j['net'] for j in r['journal'] if j['kind']=='signal_exit'))
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
