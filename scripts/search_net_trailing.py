"""Batch24: settled-carry gates and net-PnL trailing on a finite shared account."""
import json
from collections import Counter
import pandas as pd
from account_net_trailing_replay import simulate
from directional_carry_filters import observations,filtered,FILTERS
from compare_account_risk import ROOT,sha,write,summarize,exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from capital_research_metrics import utilization
from monthly_account_metrics import monthly_metrics
from search_frozen_exits import WINDOWS,BOUNDARIES,COSTS,DATA,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals

OUT=ROOT/'artifacts/net_trailing_20260925'
REV=ROOT/'artifacts/directional_reversal_20260925'
TREND=ROOT/'artifacts/directional_trend_20260925'


def read(p):return json.loads(p.read_text(encoding='utf-8'))


def references():
    refs=[]
    for mode in ['short','long','both']:
        key=f'{mode}_mask2_n25_hold_cap5'
        sp=next(s for s in read(REV/'summary.json')['specs'] if s['id']==key)
        refs.append(dict(id=mode+'_reversal',parent=str(REV),baseline=key,policy=sp['policy'],signals=read(REV/'signals.json')[f'{mode}_mask2']))
    key='breakout_any_both_trend_n25_hold'; sp=next(s for s in read(TREND/'summary.json')['specs'] if s['id']==key)
    refs.append(dict(id='both_trend',parent=str(TREND),baseline=key,policy=sp['policy'],signals=read(TREND/'signals.json')[sp['source']['id']]))
    return refs


def definitions(refs):
    exits=[('price',{}),('net_gate',dict(net_exit_mode='price_net_gate'))]
    exits += [(f'net_peak{a:g}',dict(net_exit_mode='net_peak',activation_net_usdt=a,net_callback_fraction=.25)) for a in [.5,1,2]]
    return [dict(id=f'{ref["id"]}_{gate}_{key}',family=ref['id'],gate=gate,exit=key,
        policy=dict(ref['policy'],**extra),baseline=gate=='none' and key=='price')
        for ref in refs for gate in FILTERS for key,extra in exits]


def select(specs,results):
    selected=[]
    for family in sorted({sp['family'] for sp in specs}):
        candidates=[]
        for sp in specs:
            if sp['family']!=family:continue
            rs=[r for r in results if r['strategy_id']==sp['id'] and r['window']=='development']
            if len(rs)!=2 or any(r['ending_equity'] is None or r['ending_equity']<=500 or r['max_drawdown']>=.2
                or r['exits']<20 or not r['monthly']['complete'] for r in rs):continue
            candidates.append((min(r['monthly']['min_monthly_return'] for r in rs),min(r['ending_equity'] for r in rs),sp['id']))
        selected.append(dict(family=family,strategy_id=max(candidates)[2] if candidates else None))
    return selected


def main():
    OUT.mkdir(exist_ok=True);(OUT/'runs').mkdir(exist_ok=True)
    refs=references(); specs=definitions(refs)
    quarters={f'quarter_{i}':(BOUNDARIES[i],BOUNDARIES[i+3]) for i in [0,3,6]}
    protocol=dict(created_at=pd.Timestamp.now(tz='UTC').isoformat(),previous_turn='progress:920events,1840isolatedlifecycles,16exactcontrols,28tests. LongmeanMTMnegative;SOONprice-trailingexitnet-94.55mostlyfunding-99.13.',
        hypothesis='Known carry gates and net-PnL trailing may reduce funding leakage and trapped slots; use same500wallet,not sums of isolated events.',
        account='500USDT Crossx5,5sharedslots,25totalnotional,3favorable0.25ATRtranches/6hexpiry,onecoinposition. Persistent20%DDpause,cancelpendingadds,keepcurrentpositions/funding. NoSL/no timeexit/no loser exclusion.',
        gates='none retains frozen events exactly;avoid_costly requires signed(receipt)lastsettlement>=-0.0005 and sum24h>=-0.001;nonnegative requires both>=0. LONGreceipt=-rate,SHORTreceipt=rate. Rates rounded12decimals. Only settlements at least60s old, latest<=8h5m,full24hcoverage; missing/stale explicitly rejected only by gated variants. Preserve source cooldown/eventids/priorities,do not regenerate after filtering.',
        exits='price=original3ATR/1%;net_gate=samepriceactivation/retrace but candidateexit requires estimatednet>=0;net_peak activates at0.5/1/2USDTnet onactualfilledqty, then exitsafter25%dropfromrunningpeakprovidedestimatednet>=0. Allactivatecancelpendingadds. Estimatefromclosedtradeprice withsameassumedadverseexit slip,fees,paidfunding,entryfees. No peek atnextopen fordecision. Actualnextopen fills maygapandrealizenegativePNL. netpeaknotpricepeak;no forcedexitwhileestimatednetnegative;mayincreaseholdandlosses.',
        selection='4frozenfamilies(short/long/bothreversal,bothtrend)x3gatesx5exits=60specsx3windowsx2cost=360paths. Chooseoneperfamily onSep-May only:bothcostprofit/DD<20/20closed/complete,maxworstminmonthly thenworstending.Lock before later. Reporteveryvariant. Additional3nonoverlapquarters(Sep,Dec,Mar)onlyselected+matchingbaseline,Junealreadyinlater. ReusedhistoryNOTnewOOS.',
        target='At least50%netmarkedgrowth inEVERYconsecutivecalendarmonth,notaveragesorbestmonth.',
        limitations='Currentfilters,1%maintenanceproxywithouthistoricalbrackets,5mcloseobservations,assumedslip,noorderbook,frozenuniverse/survivorship,repeatedhistoricalselection. No livepromotion.',
        specs=specs,windows=WINDOWS,quarters=quarters,costs=COSTS,
        live_config_sha256=sha(ROOT/'configs/live.yaml'),rules_sha256=sha(RULE_PATH),data_sha256=sha(DATA/'reconciled_manifest.json'),
        input_sha256={str(p.relative_to(ROOT)):sha(p) for p in [REV/'summary.json',REV/'signals.json',TREND/'summary.json',TREND/'signals.json']},
        source_sha256={n:sha(ROOT/'scripts'/n) for n in ['account_net_trailing_replay.py','account_side_quota_replay.py','directional_carry_filters.py','search_net_trailing.py','short_funding_flow_signals.py','frozen_extension_inputs.py','monthly_account_metrics.py']})
    write(OUT/'protocol.json',protocol)
    prices,funding,_=load();rules=exchange_rules(RULE_PATH)
    unique={e['event_id']:e for ref in refs for e in ref['signals']}; obs=observations(list(unique.values()),funding)
    signals={};counts={}
    for ref in refs:
        for gate in FILTERS:
            key=ref['id']+'_'+gate;signals[key],counts[key]=filtered(ref['signals'],obs,gate)
    write(OUT/'observations.json',obs);write(OUT/'signals.json',signals);write(OUT/'filter_counts.json',counts)
    print('SIGNALS',counts,flush=True)
    results=[]
    def run(window,start,end,sp,cost,fee,slip):
        r=simulate(list(range(start,end+1,300000)),grouped_signals(signals[sp['family']+'_'+sp['gate']],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(5,fee,slip),research_policy=sp['policy'])
        r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct'
        row=summarize(r,sp['id'],sp['id'],sp['policy'],5,cost,window)
        row.update(id=f'{window}_{cost}_{sp["id"]}',strategy_id=sp['id'],family=sp['family'],gate=sp['gate'],exit=sp['exit'],baseline=sp['baseline'],notional=25,
            utilization=utilization(r['curve'],r,25,5),exit_diagnostics=exit_diagnostics(r),
            monthly=monthly_metrics(r['curve'],boundaries=[t for t in BOUNDARIES if start<=t<=end]),
            side_entries=dict(Counter(j['side'] for j in r['journal'] if j['kind']=='entry')),
            blocked_net_exit_positions=sum(j['kind']=='net_exit_blocked' for j in r['journal']),negative_exits=sum(j['net']<0 for j in r['journal'] if 'net' in j))
        row['target_met']=r['ending_equity'] is not None and row['monthly']['all_months_50pct']
        write(OUT/'runs'/f'{row["id"]}.json',{k:v for k,v in r.items() if k!='curve'});pd.DataFrame(r['curve']).to_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet',index=False)
        results.append(row)
    for window,(start,end) in WINDOWS.items():
        for i,sp in enumerate(specs):
            for cost,fee,slip in COSTS:run(window,start,end,sp,cost,fee,slip)
            if (i+1)%10==0:print(window,i+1,'/',len(specs),flush=True)
            write(OUT/'progress.json',dict(window=window,spec=i+1,runs=len(results)))
        if window=='development':
            selected=select(specs,results);write(OUT/'candidate_lock.json',dict(selected=selected,locked_at=pd.Timestamp.now(tz='UTC').isoformat(),later_not_run_in_batch=True,pristine_oos=False));print('LOCKED',selected,flush=True)
    ids={r['strategy_id'] for r in selected if r['strategy_id']}
    families={r['family'] for r in selected if r['strategy_id']}
    quarter_specs=[sp for sp in specs if sp['id'] in ids or (sp['baseline'] and sp['family'] in families)]
    for window,(start,end) in quarters.items():
        for sp in quarter_specs:
            for cost,fee,slip in COSTS:run(window,start,end,sp,cost,fee,slip)
        print(window,'COMPLETE',len(results),flush=True)
    assert sha(ROOT/'configs/live.yaml')==protocol['live_config_sha256']
    write(OUT/'summary.json',dict(protocol=protocol,specs=specs,selected=selected,quarter_specs=[sp['id'] for sp in quarter_specs],results=results,
        target_met_rows=sum(r['target_met'] for r in results),incomplete_paths=sum(r['ending_equity'] is None for r in results)))
    pd.DataFrame(results).to_csv(OUT/'comparison.csv',index=False);print('COMPLETE',len(results),flush=True)


if __name__=='__main__':main()
