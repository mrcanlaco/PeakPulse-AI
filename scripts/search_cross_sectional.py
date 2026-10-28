"""Batch25: daily Long/Short relative strength plus a locked sizing sensitivity."""
from collections import Counter
import pandas as pd
from account_net_trailing_replay import simulate
from cross_sectional_signals import definitions as source_specs,enrich,rank_state,generate
from compare_account_risk import ROOT,sha,write,summarize,exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from capital_research_metrics import utilization
from monthly_account_metrics import monthly_metrics
from search_frozen_exits import WINDOWS,BOUNDARIES,COSTS,DATA,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from search_net_trailing import read

OUT=ROOT/'artifacts/cross_sectional_20260925'
PRIOR=ROOT/'artifacts/net_trailing_20260925'
CONTROLS=['short_reversal_none_price','both_reversal_none_net_peak1','both_trend_none_price','both_trend_avoid_costly_price']


def definitions(previous):
    base=next(s for s in previous['specs'] if s['id']=='short_reversal_none_price')['policy']
    specs=[]
    for source in source_specs():
        for holding in ['hold','time168']:
            for exit in ['price','net1']:
                policy=dict(base)
                if holding=='time168':policy['max_hold_hours']=168
                if exit=='net1':policy.update(net_exit_mode='net_peak',activation_net_usdt=1,net_callback_fraction=.25)
                specs.append(dict(id=f'{source["id"]}_{holding}_{exit}_n25',source=source['id'],mode=source['mode'],holding=holding,
                    exit=exit,policy=policy,notional=25,baseline=False,scaled=False))
    for key in CONTROLS:
        sp=next(s for s in previous['specs'] if s['id']==key)
        specs.append(dict(id='control_'+key,source='control_'+sp['family']+'_'+sp['gate'],mode='control',holding='hold',exit=sp['exit'],
            policy=dict(sp['policy']),notional=25,baseline=True,scaled=False,reference=key))
    return specs


def select(specs,results):
    chosen=[]
    for mode in ['momentum','reversion']:
        for hold in ['hold','time168']:
            candidates=[]
            for sp in specs:
                if sp['mode']!=mode or sp['holding']!=hold:continue
                rs=[r for r in results if r['strategy_id']==sp['id'] and r['window']=='development']
                if len(rs)!=2 or any(r['ending_equity'] is None or r['ending_equity']<=500 or r['max_drawdown']>=.2 or r['exits']<20 or not r['monthly']['complete'] for r in rs):continue
                candidates.append((min(r['monthly']['min_monthly_return'] for r in rs),min(r['ending_equity'] for r in rs),sp['id']))
            chosen.append(dict(mode=mode,holding=hold,strategy_id=max(candidates)[2] if candidates else None))
    return chosen


def scaling(specs,selected):
    output=[]
    for choice in selected:
        if choice['strategy_id'] is None:continue
        sp=next(s for s in specs if s['id']==choice['strategy_id']);policy=dict(sp['policy'],position_notional=100)
        if policy.get('net_exit_mode')=='net_peak':policy['activation_net_usdt']*=4
        output.append(dict(sp,id=sp['id'].replace('_n25','_n100'),policy=policy,notional=100,scaled=True,reference=sp['id']))
    return output


def main():
    OUT.mkdir(exist_ok=True)
    for folder in ['runs','features']:(OUT/folder).mkdir(exist_ok=True)
    previous=read(PRIOR/'summary.json');specs=definitions(previous)
    quarters={f'quarter_{i}':(BOUNDARIES[i],BOUNDARIES[i+3]) for i in [0,3,6]}
    protocol=dict(created_at=pd.Timestamp.now(tz='UTC').isoformat(),previous_turn='progress:396funding/nettrailpaths,36tests,24exactcontrols. All60variants have negativeJun-Augmonth;nettrailingreducesDDbutdoesnotestablish50%monthly.',
        hypothesis='Daily cross-sectional winners/losers may capture a different edge than isolated band reversals. Compare continuation and contrarian direction, raw and volatility-normalized ranks.',
        features='At00:00UTC only:closedhourly logreturn over24/72/168h;normalizedscore=logreturn/(sampleSDofhourlylogreturns over samewindow*sqrt(hours)). Allsixscores finite,SD>1e-12,andclosed4hready72bars/ATR14/2m24hturnover. Commoneligiblepool>=24of30frozencoins. No futureuniverse/filterreplacement.',
        ranks='Average-tie percentile (rank-1)/(eligiblecount-1),symmetric0/1. Winnersrank>=.8 andrawreturn>0;losersrank<=.2 andrawreturn<0. MomentumLongwinners/Shortlosers;reversionLonglosers/Shortwinners. Eachcoincanonlyhaveonesidepersource/day. Priorityabs(percentile-.5),coinascendingties. No rerankingafterexchangeorderrejection. Sidecountsneednotbalance;notmarket-neutral andnotpairedatomicexecution.',
        account='500USDT Crossx5,5sharedslots,onecoinposition,25totalnotional(about5margin),3favorable0.25ATRparts/6hexpiry,realfees/funding/5mMark,20%persistentopeningpause. Neverrollpeak/resetpause. Originals keep losing positions;time168alternative exitsafter168h includinglosses withadverse nextopen. Same-stepcoinreentryafterexitremainsrejected;not fullportfolio rebalancing.',
        exits='Originalprice3ATR/1% ornetpeak1USDT/25%callback withestimatednet>=0 atclosedprice afterfees/funding/slip. Activation cancels pendingparts. Actualnextopenmaygap. Timeexit haspriority overtrailing andcancloseloss evenwhenaccountpaused. Target-profitminimum/ATR/exchangeeligibilityremain unchanged.',
        selection='12sources x2holding x2exits=48new25notional specs +4frozencontrols=52 x3windows x2cost=312mainpaths. Selectoneper(mode,holding)onlyonSep-May:bothcostending>500,DD<20%,20closed,complete;maxworstminmonthlythenworstending. LockbeforeJun-Aug. Reportall. No candidateifnonepass.',
        sizing='Only selected25USDTspecs get100USDTtotalnotional/about20margin sensitivity;netactivation scales1to4USDT,priceATRunchanged. Recompute actualorders/filters/fees/funding/sharedaccount,notlinearPnL. Samefrozenevents. Notdefault/live configuration. Run3windows2cost then3additionalnonoverlapquarters forselected25/100andfourcontrols;Junequarteralreadyinlater. No reselectionusing sizing/later/quarters.',
        target='At least50%netMTM growth inEVERYconsecutivecalendar month,notaverage,bestmonthorpositiveyear.',
        limitations='Repeatedhistoricalsearch,notnewOOS;fixeduniverse/survivorship;currentexchangefilters;1%MMRproxywithoutrealhistoricalbrackets;5msampledexits/assumedslip/noorderbook. No livepromotion.',
        specs=specs,windows=WINDOWS,quarters=quarters,costs=COSTS,
        live_config_sha256=sha(ROOT/'configs/live.yaml'),rules_sha256=sha(RULE_PATH),data_sha256=sha(DATA/'reconciled_manifest.json'),
        prior_sha256=sha(PRIOR/'summary.json'),prior_signals_sha256=sha(PRIOR/'signals.json'),
        source_sha256={n:sha(ROOT/'scripts'/n) for n in ['cross_sectional_signals.py','search_cross_sectional.py','account_net_trailing_replay.py','frozen_extension_inputs.py','short_multitimeframe_signals.py','monthly_account_metrics.py']})
    write(OUT/'protocol.json',protocol)
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);enriched=enrich(frames);state,ranks=rank_state(enriched);signals=generate(enriched,state,ranks)
    for coin,f in enriched.items():f.to_parquet(OUT/'features'/f'{coin}.parquet')
    state.to_parquet(OUT/'market.parquet')
    for key,r in ranks.items():r.to_parquet(OUT/f'ranks_{key}.parquet')
    old_signals=read(PRIOR/'signals.json')
    for sp in specs:
        if sp['baseline']:signals[sp['source']]=old_signals[sp['source'].removeprefix('control_')]
    write(OUT/'signals.json',signals);print('SIGNALS',{k:len(v) for k,v in signals.items()},flush=True)
    results=[]
    def run(window,start,end,sp,cost,fee,slip):
        raw=simulate(list(range(start,end+1,300000)),grouped_signals(signals[sp['source']],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(5,fee,slip),research_policy=sp['policy'])
        raw['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct'
        row=summarize(raw,sp['id'],sp['id'],sp['policy'],5,cost,window)
        row.update(id=f'{window}_{cost}_{sp["id"]}',strategy_id=sp['id'],source=sp['source'],mode=sp['mode'],holding=sp['holding'],exit=sp['exit'],notional=sp['notional'],baseline=sp['baseline'],scaled=sp['scaled'],
            utilization=utilization(raw['curve'],raw,sp['notional'],5),exit_diagnostics=exit_diagnostics(raw),
            monthly=monthly_metrics(raw['curve'],boundaries=[t for t in BOUNDARIES if start<=t<=end]),
            side_entries=dict(Counter(j['side'] for j in raw['journal'] if j['kind']=='entry')),
            time_exits=sum(j['kind']=='time_exit' for j in raw['journal']),negative_time_exits=sum(j['kind']=='time_exit' and j['net']<0 for j in raw['journal']))
        row['target_met']=raw['ending_equity'] is not None and row['monthly']['all_months_50pct']
        write(OUT/'runs'/f'{row["id"]}.json',{k:v for k,v in raw.items() if k!='curve'});pd.DataFrame(raw['curve']).to_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet',index=False)
        results.append(row)
    for window,(start,end) in WINDOWS.items():
        for i,sp in enumerate(specs):
            for cost,fee,slip in COSTS:run(window,start,end,sp,cost,fee,slip)
            if (i+1)%8==0:print(window,i+1,'/',len(specs),flush=True)
            write(OUT/'progress.json',dict(window=window,spec=i+1,runs=len(results)))
        if window=='development':
            selected=select(specs,results);scaled=scaling(specs,selected)
            write(OUT/'candidate_lock.json',dict(selected=selected,scaled_specs=scaled,locked_at=pd.Timestamp.now(tz='UTC').isoformat(),later_not_run_in_batch=True,pristine_oos=False));print('LOCKED',selected,flush=True)
    for window,(start,end) in WINDOWS.items():
        for sp in scaled:
            for cost,fee,slip in COSTS:run(window,start,end,sp,cost,fee,slip)
    selected_ids={x['strategy_id'] for x in selected if x['strategy_id']}
    quarter_specs=[sp for sp in specs if sp['id'] in selected_ids or sp['baseline']]+scaled
    for window,(start,end) in quarters.items():
        for sp in quarter_specs:
            for cost,fee,slip in COSTS:run(window,start,end,sp,cost,fee,slip)
        print(window,'COMPLETE',len(results),flush=True)
    assert sha(ROOT/'configs/live.yaml')==protocol['live_config_sha256']
    write(OUT/'summary.json',dict(protocol=protocol,specs=specs+scaled,selected=selected,quarter_specs=[sp['id'] for sp in quarter_specs],results=results,
        target_met_rows=sum(r['target_met'] for r in results),incomplete_paths=sum(r['ending_equity'] is None for r in results)))
    pd.DataFrame(results).to_csv(OUT/'comparison.csv',index=False);print('COMPLETE',len(results),flush=True)


if __name__=='__main__':main()
