"""Coin-local confirmation at the first pullback trigger; closed observations only."""
from collections import Counter
import numpy as np
import pandas as pd
from short_multitimeframe_signals import aggregate

GATES=['none','ret24','ret72','ema_trend','trend_ret24','persistence5']


def states(frames):
    result={}
    for coin,original in frames.items():
        hourly=original.asfreq('1h').copy()
        valid=np.isfinite(hourly.close)&hourly.close.gt(0)
        h=aggregate(hourly,'4h',4)
        finite=np.isfinite(h.close)&h.close.gt(0)&h.hours.eq(4)
        h['ema20']=h.close.ewm(span=20,adjust=False,min_periods=20).mean()
        h['ema60']=h.close.ewm(span=60,adjust=False,min_periods=60).mean()
        h['ema_ready']=finite.rolling(72,min_periods=72).sum().eq(72)
        # Only carry the most recent CLOSED 4h feature to intermediate hours.
        s=h[['ema20','ema60','ema_ready']].reindex(hourly.index,method='ffill')
        s['ema_ready']=s.ema_ready.eq(True)&valid
        s['close']=hourly.close
        for n in [24,72]:
            s[f'ret{n}']=np.log(hourly.close/hourly.close.shift(n))
            s[f'ready{n}']=valid.rolling(n+1,min_periods=n+1).sum().eq(n+1)
        daily_changes=pd.concat([np.log(hourly.close.shift(24*i)/hourly.close.shift(24*(i+1))) for i in range(7)],axis=1)
        s['positive_days']=daily_changes.gt(0).sum(axis=1)
        s['negative_days']=daily_changes.lt(0).sum(axis=1)
        s['ready168']=valid.rolling(169,min_periods=169).sum().eq(169)
        result[coin]=s
    return result


def decision(side,row,gate):
    if side not in ['LONG','SHORT'] or gate not in GATES:raise ValueError('invalid_trend_gate')
    if gate=='none':return 'accepted'
    if row is None:return 'missing_state'
    direction=1 if side=='LONG' else -1
    if gate in ['ret24','ret72','trend_ret24']:
        n=72 if gate=='ret72' else 24
        if not row[f'ready{n}'] or not np.isfinite(row[f'ret{n}']):return 'missing_state'
    if gate in ['ema_trend','trend_ret24']:
        if not row['ema_ready'] or not all(np.isfinite(row[k]) for k in ['close','ema20','ema60']):return 'missing_state'
    if gate=='persistence5':
        if not row['ready168']:return 'missing_state'
        allowed=row['positive_days' if side=='LONG' else 'negative_days']>=5
    elif gate in ['ret24','ret72']:allowed=direction*row[gate]>0
    else:
        allowed=direction*(row['close']-row['ema20'])>0 and direction*(row['ema20']-row['ema60'])>0
        if gate=='trend_ret24':allowed=allowed and direction*row['ret24']>0
    return 'accepted' if allowed else 'trend_disagrees'


def filtered(events,state,gate):
    out=[];counts=Counter();details=[]
    for e in events:
        t=pd.Timestamp(e['at'],unit='ms',tz='UTC');f=state.get(e['symbol'])
        row=f.loc[t] if f is not None and t in f.index else None
        reason=decision(e['side'],row,gate);counts[reason]+=1
        details.append(dict(event_id=e['event_id'],at=e['at'],side=e['side'],reason=reason))
        if reason=='accepted':out.append(e)
    return out,dict(counts),details
