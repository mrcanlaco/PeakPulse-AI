"""Batch30: hourly retracement/retest/breakout timing of frozen7day signals."""
import pandas as pd
from account_net_trailing_replay import simulate
from momentum_entry_timing import transform,MODES
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

OUT=ROOT/'artifacts/momentum_timing_20260925'
PRIOR=ROOT/'artifacts/atr_risk_20260925'
SIGNALS=ROOT/'artifacts/cross_sectional_20260925/signals.json'


def definitions(previous):
    result=[]
    for old in previous['specs']:
        if old['exit']!='hold':continue
        for timing in MODES:
            result.append(dict(old,id=old['reference']+'_'+timing,timing=timing,
                baseline=timing=='immediate',parent_id=old['id']))
    assert len(result)==14
    return result


def main():
    OUT.mkdir(exist_ok=True);(OUT/'runs').mkdir(exist_ok=True)
    previous=read(PRIOR/'summary.json');specs=definitions(previous);spans=windows()
    protocol=dict(created_at=pd.Timestamp.now(tz='UTC').isoformat(),previous_turn_classification='progress:240ATRriskpaths/25tests/48controls. NoATRstop improvedrobustnetreturn;bothlockedpicksremainedhold.',
        hypothesis='An immediate daily momentum entry may chase short-term extremes. Compare waitingfor retracement, confirmedretest, orcontinuation while keepingpositions/exits/sizingfrozen.',
        intervention='Originclosedhourlyprice andoriginATR14closed4h frozen. Inspectonlynext1..23completedhourlycloses;expirebefore24h/newdailyorigin. pull05/pull1 require signedpricechange<=-0.5/-1ATR. retest05/retest1 requirethatpullbackthenonaseparatelaterhour >=0.25ATRrecoveryfromrunningadverseextreme,stillno worse thanoriginclose. break05/break1 require signedpricechange>=0.5/1ATR. Longsign+1/Short-1. Firsthitonly,no retry;retainoriginaleventID/ATR/rankpriority andside;nointrabarassumedfill. Actualnext5mopenadverseslip. Originalsignal is not reranked orrefreshed duringwait. Internal missingcandidateprice failsdatagate;terminalunfinishedwaitexplicitlycensored.',
        account='Same500USDT Crossx5,5sharedslots,onecoinposition,3favorableparts0.25ATR/6hexpiryfromactualentry,25totalnotional(default5margin)or100(research20margin). 3ATR/1%trailing,noSL/noageclose,actualfees/funding/MTM,persistent20%entrypause. Waitingsignalsareconditionalcandidates,notorders/reservedmargin;normalcapacity/capitalchecksapplyattrigger. No livechanges.',
        evaluation='7entrytimingsx2sizesx12windowsx2cost=336paths. OriginseventsrestrictedSep2025-Aug2026;eachwindowrequiresorigin>=startandtrigger<end. ChooseonetimingpersizefromSep-Mayalone:bothcostprofit/DD<20/20closed/complete,maxworstmonthlythenworstending. Lockbeforelater/rolling. All10three-monthstartsforeachpolicy;overlapping reusedhistory,notnewOOS.48immediatecontrols exactbatch29.',
        target='Atleast50%netMTM EVERYcalendar month;notpositiveyear/window oraverage.',limitations=previous['protocol']['limitations'],
        specs=specs,windows=spans,costs=COSTS,prior_sha256=sha(PRIOR/'summary.json'),signals_sha256=sha(SIGNALS),
        data_sha256=sha(DATA/'reconciled_manifest.json'),rules_sha256=sha(RULE_PATH),live_config_sha256=sha(ROOT/'configs/live.yaml'),
        source_sha256={n:sha(ROOT/'scripts'/n) for n in ['search_momentum_timing.py','momentum_entry_timing.py','account_net_trailing_replay.py','frozen_extension_inputs.py']})
    write(OUT/'protocol.json',protocol)
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH)
    origins=[e for e in read(SIGNALS)['momentum_168h_raw'] if BOUNDARIES[0]<=e['at']<BOUNDARIES[-1]]
    signals={};counts={};diagnostics={}
    for mode in MODES:
        signals[mode],counts[mode],diagnostics[mode]=transform(origins,frames,mode)
        assert not counts[mode].get('data_error') and not counts[mode].get('right_censored'),counts[mode]
    write(OUT/'signals.json',signals);write(OUT/'origin_signals.json',origins);write(OUT/'timing_counts.json',counts);write(OUT/'timing_diagnostics.json',diagnostics)
    print('TIMINGS',counts,flush=True);results=[]
    for window,(start,end) in spans.items():
        for sp in specs:
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),grouped_signals([e for e in signals[sp['timing']] if e.get('source_at',e['at'])>=start],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(5,fee,slip),research_policy=sp['policy'])
                r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct'
                row=summarize(r,sp['id'],sp['id'],sp['policy'],5,cost,window);sides=side_metrics(r,r['curve'])
                row.update(id=f'{window}_{cost}_{sp["id"]}',strategy_id=sp['id'],reference=sp['reference'],exit=sp['exit'],notional=sp['notional'],baseline=sp['baseline'],source=sp['source'],holding=sp['holding'],timing=sp['timing'],
                    utilization=utilization(r['curve'],r,sp['notional'],5),exit_diagnostics=exit_diagnostics(r),side_metrics=sides,
                    side_entries={side:rs['entries'] for side,rs in sides['sides'].items()},monthly=monthly_metrics(r['curve'],boundaries=[t for t in BOUNDARIES if start<=t<=end]),
                    candidates=sum(start<=e.get('source_at',e['at']) and e['at']<end for e in signals[sp['timing']]))
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
