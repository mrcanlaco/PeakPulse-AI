"""Batch29: sampled ATR risk exits on frozen7day Long/Short entries."""
import pandas as pd
from account_net_trailing_replay import simulate
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

OUT=ROOT/'artifacts/atr_risk_20260925'
PRIOR=ROOT/'artifacts/signal_lifecycle_20260925'
SIGNALS=ROOT/'artifacts/cross_sectional_20260925/signals.json'


def definitions(previous):
    result=[]
    for old in previous['specs']:
        if old['exit']!='hold':continue
        for multiple in [None,1,2,4,8]:
            policy=dict(old['policy']);tag='hold' if multiple is None else f'atr{multiple}'
            if multiple is not None:policy['stop_atr']=multiple
            result.append(dict(old,id=old['reference']+'_'+tag,exit=tag,holding=tag,
                policy=policy,baseline=multiple is None,parent_id=old['id']))
    assert len(result)==10
    return result


def main():
    OUT.mkdir(exist_ok=True);(OUT/'runs').mkdir(exist_ok=True)
    previous=read(PRIOR/'summary.json');specs=definitions(previous);spans=windows()
    protocol=dict(created_at=pd.Timestamp.now(tz='UTC').isoformat(),previous_turn_classification='progress:288lifecyclepaths/28tests/54exactcontrols;dailyinvalidationincreasedturnoverbutallvariantsfailed50%eachmonth andbothlockedpickswerehold.',
        hypothesis='Does a price-risk boundary remove tail losses early enough to offset stopped trades and repeated transaction costs?',
        intervention='Holdcontrol vs1/2/4/8ATR. ATR14 fromclosed4h candles locked atoriginalentrysignal. At every5m step,Long stops if weightedaverageentry-lastclosedMark>=kATR;Short iflastclosedMark-weightedaverageentry>=kATR. Favorabletranchesupdateweightedentry,neverATR. Funding currentstepfirst;ATR stopbeforetrailing/adds. Actualnexttradeopen adverse slip,NOTfillattrigger,NOTcontinuous exchange stop simulation. Stopsrunwhileentrypaused;no samecoinreentryonthesameexitstep.',
        account='500USDT Crossx5,5sharedslots,3favorableparts0.25ATR/6h,25totalnotional(default5margin)or100(research20margin). Samefrozen7dayrawmomentumLong/Shortdailyentries,3ATR/1%trailing,actualfees/funding/MTM,persistent20%openingpause. StopsCANclose losingpositions and areofflinealternatives to originalnoSL;no livechanges.',
        evaluation='5exitpoliciesx2sizesx12windowsx2cost=240paths. ChooseoneexitpersizefromSep-Mayalone:bothcostprofit,DD<20%,20closed,complete,maxworstmonthlythenworstending. LockbeforeJun-Aug/rolling. All10three-monthstartsSep2025-Jun2026forEVERYpolicy;overlappinghistoricalreuse,notnewOOS.48holdcontrols exactbatch28.',
        target='Atleast50%netMTM EVERYcalendar month;notpositiveyear/window oraverage.',limitations=previous['protocol']['limitations'],
        specs=specs,windows=spans,costs=COSTS,prior_sha256=sha(PRIOR/'summary.json'),signals_sha256=sha(SIGNALS),
        data_sha256=sha(DATA/'reconciled_manifest.json'),rules_sha256=sha(RULE_PATH),live_config_sha256=sha(ROOT/'configs/live.yaml'),
        source_sha256={n:sha(ROOT/'scripts'/n) for n in ['search_atr_risk.py','account_net_trailing_replay.py','frozen_extension_inputs.py']})
    write(OUT/'protocol.json',protocol)
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH)
    signals=read(SIGNALS);results=[]
    for window,(start,end) in spans.items():
        for sp in specs:
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),grouped_signals(signals[sp['source']],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(5,fee,slip),research_policy=sp['policy'])
                r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct'
                row=summarize(r,sp['id'],sp['id'],sp['policy'],5,cost,window);sides=side_metrics(r,r['curve'])
                row.update(id=f'{window}_{cost}_{sp["id"]}',strategy_id=sp['id'],reference=sp['reference'],exit=sp['exit'],notional=sp['notional'],baseline=sp['baseline'],source=sp['source'],holding=sp['holding'],
                    utilization=utilization(r['curve'],r,sp['notional'],5),exit_diagnostics=exit_diagnostics(r),side_metrics=sides,
                    side_entries={side:rs['entries'] for side,rs in sides['sides'].items()},monthly=monthly_metrics(r['curve'],boundaries=[t for t in BOUNDARIES if start<=t<=end]),
                    risk_exits=sum(j['kind']=='atr_stop' for j in r['journal']),negative_risk_exits=sum(j['kind']=='atr_stop' and j['net']<0 for j in r['journal']),
                    risk_exit_net=sum(j['net'] for j in r['journal'] if j['kind']=='atr_stop'))
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
