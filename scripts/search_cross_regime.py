"""Batch26: causal entry gates and monthly-start robustness of frozen picks."""
import pandas as pd
from account_net_trailing_replay import simulate
from cross_regime_signals import market,filtered,GATES
from compare_account_risk import ROOT,sha,write,summarize,exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from capital_research_metrics import utilization
from directional_capacity_metrics import side_metrics
from monthly_account_metrics import monthly_metrics
from search_side_capacity import windows
from search_frozen_exits import WINDOWS,BOUNDARIES,COSTS,DATA,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from search_net_trailing import read

OUT=ROOT/'artifacts/cross_regime_20260925'
PRIOR=ROOT/'artifacts/cross_sectional_20260925'


def definitions(previous):
    ids={x['strategy_id'] for x in previous['selected'] if x['strategy_id']}
    refs=[s for s in previous['specs'] if s['id'] in ids or s['scaled']]
    return [dict(sp,id=sp['id']+'_'+gate,reference=sp['id'],gate=gate,baseline=gate=='none') for sp in refs for gate in GATES]


def select(specs,results):
    chosen=[]
    for ref in sorted({sp['reference'] for sp in specs}):
        candidates=[]
        for sp in specs:
            if sp['reference']!=ref:continue
            rs=[r for r in results if r['strategy_id']==sp['id'] and r['window']=='development']
            if len(rs)!=2 or any(r['ending_equity'] is None or r['ending_equity']<=500 or r['max_drawdown']>=.2 or r['exits']<20 or not r['monthly']['complete'] for r in rs):continue
            candidates.append((min(r['monthly']['min_monthly_return'] for r in rs),min(r['ending_equity'] for r in rs),sp['id']))
        chosen.append(dict(reference=ref,strategy_id=max(candidates)[2] if candidates else None))
    return chosen


def main():
    OUT.mkdir(exist_ok=True);(OUT/'runs').mkdir(exist_ok=True)
    previous=read(PRIOR/'summary.json');specs=definitions(previous);spans=windows()
    protocol=dict(created_at=pd.Timestamp.now(tz='UTC').isoformat(),previous_turn='progress:390cross-sectionalpaths,41tests,24controls;7daymomentum100year969.23butfreshJune496.18/462.01. Originalsizeand100sensitivitystillfail50%eachmonth.',
        hypothesis='Directional BTC and broad-alt state may prevent wrong-side entries in weak periods; isolate entry filter from frozen source/order/exit/sizing.',
        gates='none preserves all signals;btc_week requires signedBTCclosed7dreturn>0;btc_trend requiresBTC4hEMA20>EMA60,close>EMA20,ret24>0forLong,allmirrorforShort;breadth60 requires>=60%eligiblealts above4hEMA60forLong/belowforShort;consensus requiresbtc_trendANDbreadth60. Equallevelsare neither direction. BTCready72complete4hbars;breadth>=24sameeligiblealtpoolasfrozenrankdata. Onlycloseddataatdaily00UTC. Missingstateexplicitlyrejects gatedsignals.',
        intervention='Entry-only: retain immutableeventID,time,ATR,side,priority, source dailycooldown. Neverrerank,retry,reversesideorclosepositionwhenregimechanges. Existingpendingadds/exitpolicyremainunchanged. A directionalfilterdoesnotmakeportfolio market-neutral.',
        account='Same500USDT Crossx5,5sharedslots,3favorableparts,realfees/funding/MTM,persistent20%DDpause. Frozen25notional(default5plannedmargin) and100notional(research20margin),notpertranche. Frozenhold versus168hforcedmarketexitincludinglosses;price3ATR/1%or netpeak1/4USDT as selectedprior. No configuration changes to live.',
        selection='Sixfrozenreferencepolicies x5gates=30specs x3mainwindows x2cost=180paths. Choosegate per reference fromSep-May only:bothcostprofit/DD<20/20closed/complete,maxworstminmonthlythenworstending;lockbeforelater. Then9additional3monthstartsSep2025-May2026 forselectedandall6nonecontrols;Juneislater. Reportall10starts includingfailures,overlapnotindependent. No reselectafterlater/rolling.',
        target='Atleast50%netMTM inEVERYconsecutivecalendar month. Positiveyear/average/windowdoesnotpass.',
        limitations='Reusedhistoricaldata,notfreshOOS;frozen30coins/survivorship,currentfilters,MMR1%proxywithouthistoricaltiers,assumedslip/5msampledexits/noorderbook. No livepromotion.',
        specs=specs,windows=spans,costs=COSTS,prior_sha256=sha(PRIOR/'summary.json'),signals_sha256=sha(PRIOR/'signals.json'),
        data_sha256=sha(DATA/'reconciled_manifest.json'),rules_sha256=sha(RULE_PATH),live_config_sha256=sha(ROOT/'configs/live.yaml'),
        source_sha256={n:sha(ROOT/'scripts'/n) for n in ['cross_regime_signals.py','search_cross_regime.py','account_net_trailing_replay.py','cross_sectional_signals.py','short_multitimeframe_signals.py','directional_capacity_metrics.py','frozen_extension_inputs.py']})
    write(OUT/'protocol.json',protocol)
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);state=market(frames);state.to_parquet(OUT/'market.parquet')
    source=read(PRIOR/'signals.json');signals={};counts={}
    for key in sorted({sp['source'] for sp in specs}):
        for gate in GATES:signals[key+'_'+gate],counts[key+'_'+gate]=filtered(source[key],state,gate)
    write(OUT/'signals.json',signals);write(OUT/'filter_counts.json',counts);print('FILTERS',counts,flush=True)
    results=[]
    def run(window,sp,cost,fee,slip):
        start,end=spans[window]
        r=simulate(list(range(start,end+1,300000)),grouped_signals(signals[sp['source']+'_'+sp['gate']],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(5,fee,slip),research_policy=sp['policy'])
        r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct'
        row=summarize(r,sp['id'],sp['id'],sp['policy'],5,cost,window);sides=side_metrics(r,r['curve'])
        row.update(id=f'{window}_{cost}_{sp["id"]}',strategy_id=sp['id'],reference=sp['reference'],gate=sp['gate'],notional=sp['notional'],baseline=sp['baseline'],source=sp['source'],holding=sp['holding'],
            utilization=utilization(r['curve'],r,sp['notional'],5),exit_diagnostics=exit_diagnostics(r),side_metrics=sides,
            side_entries={side:rs['entries'] for side,rs in sides['sides'].items()},monthly=monthly_metrics(r['curve'],boundaries=[t for t in BOUNDARIES if start<=t<=end]))
        row['target_met']=r['ending_equity'] is not None and row['monthly']['all_months_50pct']
        write(OUT/'runs'/f'{row["id"]}.json',{k:v for k,v in r.items() if k!='curve'});pd.DataFrame(r['curve']).to_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet',index=False);results.append(row)
    for window in WINDOWS:
        for i,sp in enumerate(specs):
            for cost,fee,slip in COSTS:run(window,sp,cost,fee,slip)
            write(OUT/'progress.json',dict(window=window,spec=i+1,runs=len(results)))
        print(window,'COMPLETE',len(results),flush=True)
        if window=='development':
            selected=select(specs,results);write(OUT/'candidate_lock.json',dict(selected=selected,locked_at=pd.Timestamp.now(tz='UTC').isoformat(),later_not_run_in_batch=True,pristine_oos=False));print('LOCKED',selected,flush=True)
    ids={c['strategy_id'] for c in selected if c['strategy_id']};rolling=[sp for sp in specs if sp['id'] in ids or sp['baseline']]
    for window in spans:
        if window in WINDOWS:continue
        for sp in rolling:
            for cost,fee,slip in COSTS:run(window,sp,cost,fee,slip)
        print(window,'COMPLETE',len(results),flush=True)
    from search_side_capacity import robustness
    robust=robustness([r for r in results if r['strategy_id'] in {sp['id'] for sp in rolling}])
    assert sha(ROOT/'configs/live.yaml')==protocol['live_config_sha256']
    write(OUT/'summary.json',dict(protocol=protocol,specs=specs,selected=selected,rolling_specs=[sp['id'] for sp in rolling],results=results,robustness=robust,
        target_met_rows=sum(r['target_met'] for r in results),incomplete_paths=sum(r['ending_equity'] is None for r in results)))
    pd.DataFrame(results).to_csv(OUT/'comparison.csv',index=False);print('COMPLETE',len(results),flush=True)


if __name__=='__main__':main()
