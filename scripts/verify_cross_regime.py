"""Independent EMA/breadth/gate oracles plus complete finite-account audits."""
from collections import Counter
import numpy as np
import pandas as pd
from account_net_trailing_replay import simulate
from compare_account_risk import ROOT,sha,write,exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from research_directional_audit import audit_directional
from cross_sectional_audit import audit_exits,audit_features
from cross_sectional_signals import enrich
from cross_regime_signals import market,GATES
from directional_capacity_metrics import side_metrics
from monthly_account_metrics import monthly_metrics
from search_cross_regime import OUT,PRIOR,read,definitions,select,WINDOWS,BOUNDARIES,COSTS,DATA
from search_multitimeframe_rolling import grouped_signals
from search_side_capacity import robustness


def ema_oracle(values,span):
    alpha=2/(span+1);average=None;weight=1.;count=0;out=[]
    for x in values:
        if average is not None:weight*=1-alpha
        if np.isfinite(x):
            count+=1
            average=float(x) if average is None else (weight*average+alpha*x)/(weight+alpha)
            weight=1.
        out.append(average if count>=span else np.nan)
    return np.asarray(out)


def market_oracle(frames,state):
    enriched=enrich(frames);snapshots=audit_features(frames,enriched);bars={}
    for coin,h in frames.items():
        b=h.resample('4h',closed='right',label='right',origin='epoch').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),volume=('quote_volume','sum'),count=('close','count'))
        b.loc[b['count'].ne(4),['open','high','low','close','volume']]=np.nan
        for span in [20,60]:b['ema'+str(span)]=ema_oracle(b.close.to_numpy(),span)
        bars[coin]=b
    for t,row in state.iterrows():
        pool=[c for c,f in enriched.items() if t in f.index and f.at[t,'eligible']]
        assert row.coverage==len(pool)
        if pool:
            above=sum(bars[c].at[t,'close']>bars[c].at[t,'ema60'] for c in pool)/len(pool)
            below=sum(bars[c].at[t,'close']<bars[c].at[t,'ema60'] for c in pool)/len(pool)
            assert abs(row.above-above)<1e-12 and abs(row.below-below)<1e-12
        else:assert np.isnan(row.above) and np.isnan(row.below)
        b=bars['BTCUSDT'];j=b.index.get_loc(t) if t in b.index else -1
        ready=False
        if j>=71:
            sample=b.iloc[j-71:j+1];tail=b.iloc[j-13:j+1]
            prev=b.close.shift(1).iloc[j-13:j+1].to_numpy()
            tr=np.maximum(tail.high-tail.low,np.maximum(np.abs(tail.high-prev),np.abs(tail.low-prev)))
            ready=sample['count'].eq(4).all() and float(np.mean(tr))>0 and b.volume.iloc[j-5:j+1].sum()>=2_000_000
        assert bool(row.btc_ready)==bool(ready)
        for key in ['close','ema20','ema60']:
            actual=b.at[t,key] if j>=0 else np.nan;saved=row['btc_'+key]
            assert (np.isnan(actual) and np.isnan(saved)) or abs(actual-saved)<1e-7
        for hours,key in [(24,'btc_ret24'),(168,'btc_ret7')]:
            h=frames['BTCUSDT'];past=t-pd.Timedelta(hours=hours)
            actual=h.at[t,'close']/h.at[past,'close']-1 if t in h.index and past in h.index else np.nan
            assert (np.isnan(actual) and np.isnan(row[key])) or abs(actual-row[key])<1e-12
    return snapshots,len(state)


def independent_filter(events,state,gate):
    result=[]
    for e in events:
        if gate=='none':result.append(e);continue
        t=pd.Timestamp(e['at'],unit='ms',tz='UTC')
        if t not in state.index:continue
        r=state.loc[t];long=e['side']=='LONG'
        btc_ready=r.btc_ready and np.isfinite([r.btc_close,r.btc_ema20,r.btc_ema60,r.btc_ret24]).all()
        trend=btc_ready and ((r.btc_close>r.btc_ema20>r.btc_ema60 and r.btc_ret24>0) if long else (r.btc_close<r.btc_ema20<r.btc_ema60 and r.btc_ret24<0))
        breadth=r.coverage>=24 and (r.above if long else r.below)>=.6
        week=r.btc_ready and np.isfinite(r.btc_ret7) and (r.btc_ret7>0 if long else r.btc_ret7<0)
        if dict(btc_week=week,btc_trend=trend,breadth60=breadth,consensus=trend and breadth)[gate]:result.append(e)
    return result


def main():
    s=read(OUT/'summary.json');p=s['protocol'];previous=read(PRIOR/'summary.json');specs={sp['id']:sp for sp in s['specs']}
    assert s['specs']==definitions(previous) and s['selected']==select(s['specs'],s['results']) and read(OUT/'candidate_lock.json')['selected']==s['selected']
    assert sha(PRIOR/'summary.json')==p['prior_sha256'] and sha(PRIOR/'signals.json')==p['signals_sha256']
    assert sha(ROOT/'configs/live.yaml')==p['live_config_sha256'] and sha(RULE_PATH)==p['rules_sha256'] and sha(DATA/'reconciled_manifest.json')==p['data_sha256']
    for n,d in p['source_sha256'].items():assert sha(ROOT/'scripts'/n)==d
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);state=pd.read_parquet(OUT/'market.parquet')
    a,b=market_oracle(frames,state);totals=Counter(feature_snapshots=a,market_states=b)
    source=read(PRIOR/'signals.json');signals=read(OUT/'signals.json')
    for key in sorted({sp['source'] for sp in s['specs']}):
        for gate in GATES:
            assert signals[key+'_'+gate]==independent_filter(source[key],state,gate);totals['independent_signal_sets']+=1
    for cutoff in [pd.Timestamp(t,tz='UTC') for t in ['2025-12-01','2026-04-01','2026-07-01']]:
        prefix=market({c:h.loc[:cutoff] for c,h in frames.items()})
        pd.testing.assert_frame_equal(prefix.loc[:cutoff],state.loc[:cutoff],check_exact=True,check_freq=False);totals['causal_prefixes']+=1
    unique={e['event_id']:e for events in signals.values() for e in events}
    for i,row in enumerate(s['results']):
        sp=specs[row['strategy_id']];_,fee,slip=next(c for c in COSTS if c[0]==row['cost']);raw=read(OUT/'runs'/f'{row["id"]}.json');curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet')
        a,b,c=audit_directional(raw,curve,prices,funding,fee,slip,5,sp['notional']);n,m,t=audit_exits(raw,curve,prices,sp['policy'],unique,fee,slip)
        totals.update(journals=1,funding=a,fills=b,equity_states=c,exit_lifecycles=n,exit_observations=m,time_exits=t)
        assert row['side_metrics']==side_metrics(raw,curve)
        start,end=p['windows'][row['window']]
        assert row['monthly']==monthly_metrics(curve.to_dict('records'),boundaries=[t for t in BOUNDARIES if start<=t<=end])
        assert row['ending_equity']==raw['ending_equity'] and row['target_met']==(raw['ending_equity'] is not None and row['monthly']['all_months_50pct'])
        if sp['baseline'] and row['window'] in WINDOWS:
            key=f'{row["window"]}_{row["cost"]}_{sp["reference"]}';assert raw==read(PRIOR/'runs'/f'{key}.json')
            pd.testing.assert_frame_equal(curve,pd.read_parquet(PRIOR/'runs'/f'{key}_equity.parquet'),check_exact=True);totals['baseline_paths_exact']+=1
        if (i+1)%40==0:print('AUDITED',i+1,flush=True)
    assert s['robustness']==robustness([r for r in s['results'] if r['strategy_id'] in s['rolling_specs']])
    # A predeclared consensus full-yearbase replay for each of six references.
    for sp in s['specs']:
        if sp['gate']!='consensus':continue
        start,end=WINDOWS['year'];cost,fee,slip=COSTS[0]
        r=simulate(list(range(start,end+1,300000)),grouped_signals(signals[sp['source']+'_'+sp['gate']],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(5,fee,slip),research_policy=sp['policy'])
        r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct';key=f'year_{cost}_{sp["id"]}'
        assert {k:v for k,v in r.items() if k!='curve'}==read(OUT/'runs'/f'{key}.json')
        pd.testing.assert_frame_equal(pd.DataFrame(r['curve']),pd.read_parquet(OUT/'runs'/f'{key}_equity.parquet'),check_exact=True);totals['replayed_paths_exact']+=1
    write(OUT/'verification.json',dict(totals=totals,hashes_match=True,live_config_unchanged=True,not_new_holdout=True,financially_verified=False));print('VERIFIED',dict(totals),flush=True)


if __name__=='__main__':main()
