"""Independent entry-rank and exit-time oracles for cross-sectional research."""
import hashlib
from collections import defaultdict
import numpy as np
import pandas as pd


def audit_features(frames,enriched):
    checks=0
    for coin,f in enriched.items():
        h=frames[coin];ms=h.index.as_unit('ms').asi8;step=3600000
        assert np.all(np.diff(ms)==step)
        close=h.close.to_numpy();high=h.high.to_numpy();low=h.low.to_numpy();volume=h.quote_volume.to_numpy()
        for t,row in f.iterrows():
            i=(t.value//1000000-int(ms[0]))//step
            ready=(0<=i<len(close) and i>=287 and np.isfinite(close[i-287:i+1]).all())
            if ready:
                tr=[]
                for j in range(13,-1,-1):
                    end=i-4*j;top=np.max(high[end-3:end+1]);bottom=np.min(low[end-3:end+1]);prev=close[end-4]
                    tr.append(max(top-bottom,abs(top-prev),abs(bottom-prev)))
                atr=float(np.mean(tr));ready=atr>0 and np.sum(volume[i-23:i+1])>=2_000_000
                for n in [24,72,168]:
                    prices=close[i-n:i+1];r=np.log(prices[1:]/prices[:-1]);value=np.log(prices[-1]/prices[0]);risk=r.std(ddof=1)*np.sqrt(n)
                    ready=ready and np.isfinite(risk) and risk>1e-12 and np.isfinite(value)
                    if np.isfinite(value):assert abs(row[f'raw{n}']-value)<1e-10
                    if risk>1e-12:assert abs(row[f'risk_adjusted{n}']-value/risk)<1e-8
                assert abs(row.atr-atr)<1e-8
            assert bool(row.eligible)==bool(ready)
            checks+=1
    return checks


def audit_ranks_and_signals(enriched,state,ranks,specs,signals):
    expected=defaultdict(list);rank_checks=0
    for t in state.index:
        pool={c:f.loc[t] for c,f in enriched.items() if t in f.index and f.at[t,'eligible']}
        assert state.at[t,'coverage']==len(pool) and bool(state.at[t,'ready'])==(len(pool)>=24)
        for n in [24,72,168]:
            for key in ['raw','risk_adjusted']:
                values={c:row[f'{key}{n}'] for c,row in pool.items()}
                percentile={c:(sum(v<x for v in values.values())+(sum(v==x for v in values.values())-1)/2)/(len(values)-1) for c,x in values.items()} if len(values)>1 else {}
                for c in enriched:
                    v=ranks[f'{key}{n}'].at[t,c]
                    if c not in percentile:assert pd.isna(v)
                    else:assert abs(v-percentile[c])<1e-12
                    rank_checks+=1
                if len(pool)<24:continue
                for c,pct in percentile.items():
                    raw=pool[c][f'raw{n}'];winner=pct>=.8 and raw>0;loser=pct<=.2 and raw<0
                    if not winner and not loser:continue
                    for mode in ['momentum','reversion']:
                        sp=f'{mode}_{n}h_{key}';side='LONG' if (winner and mode=='momentum') or (loser and mode=='reversion') else 'SHORT'
                        at=int(t.value//1000000)
                        expected[sp].append(dict(at=at,symbol=c,side=side,atr=float(pool[c].atr),probability=abs(pct-.5),event_id=hashlib.sha256(f'cross:{sp}:{c}:{at}:{side}'.encode()).hexdigest()[:24]))
    count=0
    for sp in specs:
        es=sorted(expected[sp['id']],key=lambda e:(e['at'],-e['probability'],e['symbol']))
        assert es==signals[sp['id']]
        assert len({(e['symbol'],e['at']) for e in es})==len(es)
        count+=len(es)
    return rank_checks,count


def audit_exits(raw,curve,prices,policy,event_map,fee,slip):
    """Reconstruct first trailing/age trigger from actual fills and paid funding."""
    active={};groups={}
    for j in raw['journal']:
        if j['kind']=='entry':active[j['symbol']]=j['event_id'];groups[j['event_id']]=[]
        groups[active[j['symbol']]].append(j)
        if 'net' in j:del active[j['symbol']]
    checked=states=time_exits=0
    for key,js in groups.items():
        first=js[0];q=prices[first['symbol']];fills=[j for j in js if j['kind'] in ['entry','entry_add']]
        funding=[j for j in js if j['kind']=='funding'];acts=[j for j in js if j['kind']=='trail_activated'];exits=[j for j in js if 'net' in j]
        observed_end=exits[0]['at'] if exits else int(curve['at'].iloc[-1])
        deadline=first['at']+int(policy['max_hold_hours']*3600000) if policy.get('max_hold_hours') else float('inf')
        # Scheduled close takes priority; there is no trailing observation then.
        limit=min(observed_end,deadline-300000)
        at=np.arange(first['at']+300000,limit+1,300000,dtype=np.int64)
        mode=policy.get('net_exit_mode','price');assert mode in ['price','net_peak']
        trailing_at=None
        if len(at):
            ix=np.searchsorted(q.trade_times,at-300000);assert np.all(q.trade_times[ix]==at-300000);close=q.closes[ix]
            fi=np.searchsorted([j['at'] for j in fills],at,side='left')-1
            qty=np.cumsum([j['qty'] for j in fills])[fi];basis=np.cumsum([j['qty']*j['price'] for j in fills])[fi]
            fees=np.cumsum([j['qty']*j['price']*fee for j in fills])[fi]
            fidx=np.searchsorted([j['at'] for j in funding],at,side='right');carry=np.r_[0,np.cumsum([j['amount'] for j in funding])][fidx]
            direction=1 if first['side']=='LONG' else -1;indicative=close*(1-direction*slip/10000)
            net=direction*(qty*indicative-basis)-fees+carry-qty*indicative*fee
            if mode=='net_peak':
                peak=np.maximum.accumulate(net);activation=net>=policy['activation_net_usdt'];retraced=net<=peak*(1-policy['net_callback_fraction'])
            else:
                threshold=first['price']+direction*policy['activation_atr']*event_map[key]['atr']
                if direction==1:
                    activation=close>=threshold;peak=np.maximum.accumulate(np.r_[first['price'],close])[1:];retraced=close<=peak*(1-policy['callback_fraction'])
                else:
                    activation=close<=threshold;peak=np.minimum.accumulate(np.r_[first['price'],close])[1:];retraced=close>=peak*(1+policy['callback_fraction'])
            ai=np.flatnonzero(activation);assert len(acts)==int(bool(len(ai)))
            if len(ai):
                k=int(ai[0]);assert acts[0]['at']==at[k]
                assert not any(j['kind']=='entry_add' and j['at']>=at[k] for j in js)
                condition=(np.arange(len(at))>=k)&retraced
                if mode=='net_peak':
                    assert abs(acts[0]['observed_net']-net[k])<1e-7
                    condition &= net>=0
                hit=np.flatnonzero(condition)
                if len(hit):
                    z=int(hit[0]);trailing_at=int(at[z])
                    if exits and exits[0]['at']==trailing_at and mode=='net_peak':
                        assert abs(exits[0]['observed_net']-net[z])<1e-7
                        assert abs(exits[0]['net_peak']-peak[z])<1e-7
            states+=len(at)
        else:assert not acts
        reason='trailing_exit' if trailing_at is not None else 'time_exit' if deadline<=observed_end else None
        trigger=trailing_at if trailing_at is not None else deadline if reason else None
        if trigger is None:assert not exits
        elif np.isfinite(q.get(int(trigger))['entry_open']):
            assert len(exits)==1 and exits[0]['at']==trigger and exits[0]['kind']==reason
            time_exits+=reason=='time_exit'
        else:
            assert trigger==curve['at'].iloc[-1] and not exits
            assert next(p for p in raw['open_positions'] if p['event_id']==key)['pending_exit']==reason
        checked+=1
    return checked,states,time_exits
