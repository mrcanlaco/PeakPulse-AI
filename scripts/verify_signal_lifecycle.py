"""Independent historical-return, exit-decision and finite-wallet checks."""
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
from account_signal_exit_replay import simulate
from signal_lifecycle import calendar
from signal_exit_audit import audit_exits
from research_directional_audit import audit_directional
from compare_account_risk import ROOT,sha,write,exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from directional_capacity_metrics import side_metrics
from monthly_account_metrics import monthly_metrics
from search_signal_lifecycle import OUT,PRIOR,SIGNALS,read,definitions,select,BOUNDARIES,COSTS,DATA
from search_multitimeframe_rolling import grouped_signals
from search_side_capacity import robustness


def calendar_oracle(frames):
    result={};checked=0
    for coin,f in frames.items():
        if coin=='BTCUSDT':continue
        assert np.all(np.diff(f.index.as_unit('ms').asi8)==3600000)
        close=f.close.to_numpy()
        for i,t in enumerate(f.index):
            if t.hour:continue
            at=int(t.value//1000000);values={}
            for n in [24,72,168]:
                sample=close[max(0,i-n):i+1]
                valid=i>=n and np.isfinite(sample).all() and np.all(sample>0)
                values[n]=float(np.log(close[i]/close[i-n])) if valid else None
                checked+=1
            result.setdefault(at,{})[coin]=values
    return result,checked


def main():
    s=read(OUT/'summary.json');p=s['protocol'];specs={sp['id']:sp for sp in s['specs']}
    assert s['specs']==definitions(read(PRIOR/'summary.json'))
    assert s['selected']==select(s['specs'],s['results'])==read(OUT/'candidate_lock.json')['selected']
    for path,key in [(PRIOR/'summary.json','prior_sha256'),(SIGNALS,'signals_sha256'),(ROOT/'configs/live.yaml','live_config_sha256'),(RULE_PATH,'rules_sha256'),(DATA/'reconciled_manifest.json','data_sha256')]:assert sha(path)==p[key]
    for n,d in p['source_sha256'].items():assert sha(ROOT/'scripts'/n)==d
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);signals=read(SIGNALS)
    saved=read(OUT/'exit_calendar.json');states={int(t):{c:{int(n):v for n,v in values.items()} for c,values in coins.items()} for t,coins in saved.items()}
    oracle,checks=calendar_oracle(frames);assert states==oracle;totals=Counter(return_states=checks)
    for cut in ['2025-12-01','2026-04-01','2026-07-01']:
        t=pd.Timestamp(cut,tz='UTC');prefix=calendar({c:f.loc[:t] for c,f in frames.items()})
        assert prefix=={k:v for k,v in states.items() if k<=int(t.value//1000000)};totals['causal_prefixes']+=1
    unique={e['event_id']:e for events in signals.values() for e in events};failures=[]
    for i,row in enumerate(s['results']):
        sp=specs[row['strategy_id']];_,fee,slip=next(c for c in COSTS if c[0]==row['cost'])
        raw=read(OUT/'runs'/f'{row["id"]}.json');curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet')
        a,b,c=audit_directional(raw,curve,prices,funding,fee,slip,5,sp['notional']);n,m,t=audit_exits(raw,curve,prices,sp['policy'],unique,fee,slip,oracle)
        totals.update(journals=1,funding=a,fills=b,equity_states=c,exit_lifecycles=n,exit_observations=m,time_exits=t,
            signal_exits=sum(j['kind']=='signal_exit' for j in raw['journal']))
        assert row['side_metrics']==side_metrics(raw,curve)
        assert row['signal_exits']==sum(j['kind']=='signal_exit' for j in raw['journal'])
        assert row['negative_signal_exits']==sum(j['kind']=='signal_exit' and j['net']<0 for j in raw['journal'])
        start,end=p['windows'][row['window']]
        assert row['monthly']==monthly_metrics(curve.to_dict('records'),boundaries=[t for t in BOUNDARIES if start<=t<=end])
        assert row['ending_equity']==raw['ending_equity'] and row['target_met']==(raw['ending_equity'] is not None and row['monthly']['all_months_50pct'])
        control=None
        if sp['baseline']:control=PRIOR/'runs'/f'{row["window"]}_{row["cost"]}_{sp["parent_id"]}'
        elif sp['exit']=='time168' and sp['notional']==25 and row['window'] in ['development','later','year']:
            control=ROOT/'artifacts/cross_sectional_20260925/runs'/f'{row["window"]}_{row["cost"]}_momentum_168h_raw_time168_price_n25'
        if control:
            assert raw==read(Path(str(control)+'.json'))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(str(control)+'_equity.parquet'),check_exact=True);totals['baseline_paths_exact']+=1
        if raw['ending_equity'] is None:failures.append(dict(id=row['id'],errors=raw['errors'],stop_event=raw['stop_event']))
        if (i+1)%40==0:print('AUDITED',i+1,flush=True)
    assert totals['baseline_paths_exact']==54 and s['robustness']==robustness(s['results'])
    # Four predetermined full-year replays, covering bothconfirmation variants/sizes.
    for sp in s['specs']:
        if sp['exit'] not in ['sign168','sign168x2']:continue
        start,end=p['windows']['year'];cost,fee,slip=COSTS[0]
        r=simulate(list(range(start,end+1,300000)),grouped_signals(signals[sp['source']],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(5,fee,slip),research_policy=sp['policy'],exit_calendar=states)
        r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct';key=f'year_{cost}_{sp["id"]}'
        assert {k:v for k,v in r.items() if k!='curve'}==read(OUT/'runs'/f'{key}.json')
        pd.testing.assert_frame_equal(pd.DataFrame(r['curve']),pd.read_parquet(OUT/'runs'/f'{key}_equity.parquet'),check_exact=True);totals['replayed_paths_exact']+=1
    assert len(failures)==s['incomplete_paths'];write(OUT/'incomplete_paths.json',failures)
    write(OUT/'verification.json',dict(totals=totals,hashes_match=True,live_config_unchanged=True,not_new_holdout=True,financially_verified=False));print('VERIFIED',dict(totals),flush=True)


if __name__=='__main__':main()
