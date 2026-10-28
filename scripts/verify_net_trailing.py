"""Independent signed accounting, settled-funding oracle and trigger reconstruction."""
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
from account_net_trailing_replay import simulate
from compare_account_risk import ROOT,sha,write,exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from research_directional_audit import audit_directional
from monthly_account_metrics import monthly_metrics
from directional_carry_filters import observations,filtered
from search_net_trailing import OUT,read,references,definitions,select,WINDOWS,BOUNDARIES,COSTS,DATA
from search_multitimeframe_rolling import grouped_signals


def audit_triggers(raw,curve,prices,policy,event_map,fee,slip):
    mode=policy.get('net_exit_mode','price')
    if mode=='price':return 0,0
    active={}; groups={}
    for j in raw['journal']:
        if j['kind']=='entry':active[j['symbol']]=j['event_id'];groups[j['event_id']]=[]
        groups[active[j['symbol']]].append(j)
        if 'net' in j:del active[j['symbol']]
    checks=states=0
    for key,js in groups.items():
        first=js[0]; fills=[j for j in js if j['kind'] in ['entry','entry_add']]
        exits=[j for j in js if 'net' in j]; acts=[j for j in js if j['kind']=='trail_activated']
        blocks=[j for j in js if j['kind']=='net_exit_blocked']; funding=[j for j in js if j['kind']=='funding']
        end=exits[0]['at'] if exits else int(curve['at'].iloc[-1])
        at=np.arange(first['at']+300000,end+1,300000,dtype=np.int64)
        if not len(at):assert not acts and not exits;continue
        q=prices[first['symbol']];ix=np.searchsorted(q.trade_times,at-300000)
        assert np.all(q.trade_times[ix]==at-300000)
        close=q.closes[ix]
        fi=np.searchsorted([j['at'] for j in fills],at,side='left')-1
        qty=np.cumsum([j['qty'] for j in fills])[fi]
        basis=np.cumsum([j['qty']*j['price'] for j in fills])[fi]
        entry_fee=np.cumsum([j['qty']*j['price']*fee for j in fills])[fi]
        fidx=np.searchsorted([j['at'] for j in funding],at,side='right')
        carry=np.r_[0,np.cumsum([j['amount'] for j in funding])][fidx]
        direction=1 if first['side']=='LONG' else -1
        exit_est=close*(1-direction*slip/10000)
        net=direction*(qty*exit_est-basis)-entry_fee+carry-qty*exit_est*fee
        peak=np.maximum.accumulate(net)
        if mode=='net_peak':
            activate=net>=policy['activation_net_usdt']
            retrace=net<=peak*(1-policy['net_callback_fraction'])
        else:
            threshold=first['price']+direction*policy['activation_atr']*event_map[key]['atr']
            if direction==1:
                activate=close>=threshold;price_peak=np.maximum.accumulate(np.r_[first['price'],close])[1:]
                retrace=close<=price_peak*(1-policy['callback_fraction'])
            else:
                activate=close<=threshold;price_peak=np.minimum.accumulate(np.r_[first['price'],close])[1:]
                retrace=close>=price_peak*(1+policy['callback_fraction'])
        ai=np.flatnonzero(activate)
        assert len(acts)==int(bool(len(ai)))
        if len(ai):
            k=int(ai[0]);assert acts[0]['at']==at[k] and abs(acts[0]['observed_net']-net[k])<1e-7
            assert not any(j['kind']=='entry_add' and j['at']>=at[k] for j in js)
            eligible=(np.arange(len(at))>=k)&retrace
            blocked=np.flatnonzero(eligible&(net<0))
            assert len(blocks)==int(bool(len(blocked)))
            if len(blocked):assert blocks[0]['at']==at[int(blocked[0])]
            triggers=np.flatnonzero(eligible&(net>=0))
            if len(triggers):
                t=int(triggers[0]);reference=q.get(int(at[t]))['entry_open']
                if np.isfinite(reference):
                    assert len(exits)==1 and exits[0]['at']==at[t]
                    assert abs(exits[0]['observed_net']-net[t])<1e-7
                    if mode=='net_peak':assert abs(exits[0]['net_peak']-peak[t])<1e-7
                else:
                    assert at[t]==curve['at'].iloc[-1] and not exits
                    assert next(p for p in raw['open_positions'] if p['event_id']==key)['pending_exit']=='trailing_exit'
            else:assert not exits
        else:assert not exits and not blocks
        checks+=1;states+=len(at)
    return checks,states


def funding_oracle(events,funding,saved):
    checked=0
    for e in events:
        t=e['at']-60000;hist=[x for x in funding[e['symbol']] if x[0]<=t]
        fresh=bool(hist) and t-hist[-1][0]<=8*3600000+300000
        full=fresh and funding[e['symbol']][0][0]<=t-86400000
        sign=1 if e['side']=='SHORT' else -1
        last=round(sign*hist[-1][1],12) if fresh else None
        day=round(sign*sum(x[1] for x in hist if x[0]>t-86400000),12) if full else None
        o=saved[e['event_id']]
        assert (last,day)==(o['last_receipt_rate'],o['day_receipt_rate'])
        checked+=1
    return checked


def main():
    s=read(OUT/'summary.json');p=s['protocol'];refs=references();specs={sp['id']:sp for sp in s['specs']}
    assert s['specs']==definitions(refs) and s['selected']==select(s['specs'],s['results'])
    assert read(OUT/'candidate_lock.json')['selected']==s['selected']
    assert sha(ROOT/'configs/live.yaml')==p['live_config_sha256'] and sha(RULE_PATH)==p['rules_sha256']
    assert sha(DATA/'reconciled_manifest.json')==p['data_sha256']
    for n,d in p['source_sha256'].items():assert sha(ROOT/'scripts'/n)==d
    for n,d in p['input_sha256'].items():assert sha(ROOT/n)==d
    prices,funding,_=load();rules=exchange_rules(RULE_PATH);saved=read(OUT/'observations.json');signals=read(OUT/'signals.json')
    unique={e['event_id']:e for ref in refs for e in ref['signals']}
    totals=Counter(independent_funding_events=funding_oracle(list(unique.values()),funding,saved))
    for ref in refs:
        for gate in ['none','avoid_costly','nonnegative']:
            key=ref['id']+'_'+gate;actual,counts=filtered(ref['signals'],saved,gate)
            assert actual==signals[key] and counts==read(OUT/'filter_counts.json')[key]
    for ref in refs:
        for stop in [pd.Timestamp('2025-12-01',tz='UTC'),pd.Timestamp('2026-04-01',tz='UTC'),pd.Timestamp('2026-07-01',tz='UTC')]:
            ms=int(stop.timestamp()*1000);events=[e for e in ref['signals'] if e['at']<=ms]
            prefix={c:[x for x in rows if x[0]<=ms] for c,rows in funding.items()}
            obs=observations(events,prefix)
            assert obs=={e['event_id']:saved[e['event_id']] for e in events};totals['causal_prefixes']+=1
    all_windows=dict(WINDOWS,**p['quarters'])
    for i,row in enumerate(s['results']):
        sp=specs[row['strategy_id']];_,fee,slip=next(c for c in COSTS if c[0]==row['cost'])
        raw=read(OUT/'runs'/f'{row["id"]}.json');curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet')
        a,b,c=audit_directional(raw,curve,prices,funding,fee,slip,5)
        n,m=audit_triggers(raw,curve,prices,sp['policy'],unique,fee,slip)
        totals.update(journals=1,funding=a,fills=b,states=c,net_lifecycles=n,net_decision_states=m)
        start,end=all_windows[row['window']]
        assert row['monthly']==monthly_metrics(curve.to_dict('records'),boundaries=[t for t in BOUNDARIES if start<=t<=end])
        assert row['target_met']==(raw['ending_equity'] is not None and row['monthly']['all_months_50pct'])
        assert row['ending_equity']==raw['ending_equity']
        if sp['baseline'] and row['window'] in WINDOWS:
            ref=next(r for r in refs if r['id']==sp['family']);base=Path(ref['parent'])/'runs'/f'{row["window"]}_{row["cost"]}_{ref["baseline"]}'
            assert raw==read(base.with_suffix('.json'))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(str(base)+'_equity.parquet'),check_exact=True);totals['baseline_paths_exact']+=1
        if (i+1)%40==0:print('AUDITED',i+1,flush=True)
    # One full-year base path for each new exit and family:16predeclared reruns.
    for family in [r['id'] for r in refs]:
        for exit in ['net_gate','net_peak0.5','net_peak1','net_peak2']:
            sp=specs[f'{family}_none_{exit}'];start,end=WINDOWS['year'];cost,fee,slip=COSTS[0]
            raw=simulate(list(range(start,end+1,300000)),grouped_signals(signals[family+'_none'],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(5,fee,slip),research_policy=sp['policy'])
            raw['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct';key=f'year_{cost}_{sp["id"]}'
            assert {k:v for k,v in raw.items() if k!='curve'}==read(OUT/'runs'/f'{key}.json')
            pd.testing.assert_frame_equal(pd.DataFrame(raw['curve']),pd.read_parquet(OUT/'runs'/f'{key}_equity.parquet'),check_exact=True);totals['replayed_paths_exact']+=1
    write(OUT/'verification.json',dict(totals=totals,hashes_match=True,live_config_unchanged=True,not_new_holdout=True,financially_verified=False))
    print('VERIFIED',dict(totals),flush=True)


if __name__=='__main__':main()
