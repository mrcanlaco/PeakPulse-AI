"""Batch31: frozen0.5ATR retracement across all cross-sectional source families."""
import pandas as pd
from account_net_trailing_replay import simulate
from momentum_entry_timing import transform
TIMINGS=["immediate","pull05"]
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

OUT=ROOT/'artifacts/cross_pullback_20260925'
PRIOR=ROOT/'artifacts/cross_sectional_20260925'
TIMING_PRIOR=ROOT/'artifacts/momentum_timing_20260925'
SIGNALS=ROOT/'artifacts/cross_sectional_20260925/signals.json'


def definitions(previous):
    result=[]
    for old in previous['specs']:
        if old['mode'] not in ['momentum','reversion'] or old['holding']!='hold' or old['exit']!='price' or old['notional']!=25:continue
        for timing in TIMINGS:
            result.append(dict(old,id=old['id']+'_'+timing,timing=timing,reference=old['mode'],
                baseline=timing=='immediate',parent_id=old['id']))
    assert len(result)==24 and len({sp['source'] for sp in result})==12
    return result


def main():
    OUT.mkdir(exist_ok=True);(OUT/'runs').mkdir(exist_ok=True)
    previous=read(PRIOR/'summary.json');specs=definitions(previous);spans=windows()
    protocol=dict(created_at=pd.Timestamp.now(tz='UTC').isoformat(),previous_turn_classification='progress:336timingpaths/42tests/48controls. Preselected7dayrawmomentum25pull05 profitable10/10base and9/10stressrollingquarters,butnegativeindividualmonths;not50%monthly.',
        hypothesis='Does the pre-existing0.5ATR favorable retracement generalize across daily cross-sectional momentum/reversion and24/72/168hour raw/riskadjusted rankings?',
        intervention='Exactlyfrozen immediate vs pull05: originclosedhourlyreference andoriginATR14closed4h;observeonly1..23subsequentclosedhours,firstsignedpricechange<=-0.5ATR,expirebefore24h. Longsign+1,Short-1. Retainoriginalside/rankpriority/eventID/ATR. No rerank/retry/intrabarfill;actualnext5mopenadverseslip. Underlying12sources arefrozenbatch25; notretrained/reselected eventrules.',
        account='Same500USDT Crossx5,5sharedslots,onecoinposition,25totalnotional/about5margin,3favorableparts0.25ATR/6hfromactualentry,3ATR/1%trailing,noSL/noageclose. Realfunding/fees/MTM,persistent20%entrypause. Waitingcandidatesdonotreserveorders/margin;capital/precision/slotchecksattrigger. No livechanges.',
        evaluation='12sourcesx2timingsx12windowsx2cost=576paths. Chooseone(source,timing)permomentum/reversionfamily usingSep-Mayalone:bothcostprofit/DD<20/20closed/complete,maxworstmonthlythenworstending. Lockbeforelater/rolling. All10three-monthstartsforeverypolicy,overlappingreusedhistory,notnewOOS. 114uniqueoldcontrols:48batch30raw7daypaths plus66otherimmediatemainpathsfrombatch25.',
        target='Atleast50%netMTM EVERYcalendar month;notpositiveyear/window oraverage.',limitations=previous['protocol']['limitations'],
        specs=specs,windows=spans,costs=COSTS,prior_sha256=sha(PRIOR/'summary.json'),timing_prior_sha256=sha(TIMING_PRIOR/'summary.json'),signals_sha256=sha(SIGNALS),
        data_sha256=sha(DATA/'reconciled_manifest.json'),rules_sha256=sha(RULE_PATH),live_config_sha256=sha(ROOT/'configs/live.yaml'),
        source_sha256={n:sha(ROOT/'scripts'/n) for n in ['search_cross_pullback.py','momentum_entry_timing.py','account_net_trailing_replay.py','frozen_extension_inputs.py']})
    write(OUT/'protocol.json',protocol)
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH)
    source=read(SIGNALS);origins={key:[e for e in source[key] if BOUNDARIES[0]<=e['at']<BOUNDARIES[-1]] for key in sorted({sp['source'] for sp in specs})}
    signals={};counts={};diagnostics={}
    for key,events in origins.items():
        for mode in TIMINGS:
            ident=key+'_'+mode
            signals[ident],counts[ident],diagnostics[ident]=transform(events,frames,mode)
            assert not counts[ident].get('data_error') and not counts[ident].get('right_censored'),counts[ident]
    write(OUT/'signals.json',signals);write(OUT/'origin_signals.json',origins);write(OUT/'timing_counts.json',counts);write(OUT/'timing_diagnostics.json',diagnostics)
    print('TIMINGS',counts,flush=True);results=[]
    for window,(start,end) in spans.items():
        for sp in specs:
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),grouped_signals([e for e in signals[sp['source']+'_'+sp['timing']] if e.get('source_at',e['at'])>=start],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(5,fee,slip),research_policy=sp['policy'])
                r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct'
                row=summarize(r,sp['id'],sp['id'],sp['policy'],5,cost,window);sides=side_metrics(r,r['curve'])
                row.update(id=f'{window}_{cost}_{sp["id"]}',strategy_id=sp['id'],reference=sp['reference'],exit=sp['exit'],notional=sp['notional'],baseline=sp['baseline'],source=sp['source'],holding=sp['holding'],timing=sp['timing'],mode=sp['mode'],
                    utilization=utilization(r['curve'],r,sp['notional'],5),exit_diagnostics=exit_diagnostics(r),side_metrics=sides,
                    side_entries={side:rs['entries'] for side,rs in sides['sides'].items()},monthly=monthly_metrics(r['curve'],boundaries=[t for t in BOUNDARIES if start<=t<=end]),
                    candidates=sum(start<=e.get('source_at',e['at']) and e['at']<end for e in signals[sp['source']+'_'+sp['timing']]))
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
