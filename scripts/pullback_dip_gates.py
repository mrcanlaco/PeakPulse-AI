"""Countertrend entry filters inside the frozen weekly momentum source."""
from collections import Counter
import numpy as np
import pandas as pd
from pullback_trend_gates import states as trend_states

GATES=['none','counter24','counter72','dip24_shallow','dip24_deep','ema_pullback']


def states(frames):
    result=trend_states(frames)
    for coin,s in result.items():s['close24']=frames[coin].asfreq('1h').close.shift(24)
    return result


def decision(side,row,gate,atr):
    if side not in ['LONG','SHORT'] or gate not in GATES:raise ValueError('invalid_dip_gate')
    if gate=='none':return 'accepted'
    if row is None:return 'missing_state'
    d=1 if side=='LONG' else -1
    if gate=='ema_pullback':
        if not row['ema_ready'] or not all(np.isfinite(row[k]) for k in ['close','ema20','ema60']):return 'missing_state'
        allowed=d*(row['ema20']-row['ema60'])>0 and d*(row['close']-row['ema20'])<0
    else:
        n=72 if gate=='counter72' else 24
        if not row[f'ready{n}'] or not np.isfinite(row[f'ret{n}']):return 'missing_state'
        allowed=d*row[f'ret{n}']<0
        if gate in ['dip24_shallow','dip24_deep']:
            if not np.isfinite(atr) or atr<=0 or not all(np.isfinite(row[k]) and row[k]>0 for k in ['close','close24']):return 'missing_state'
            distance=-d*(row['close']-row['close24'])/atr
            allowed=allowed and (0<distance<=2 if gate=='dip24_shallow' else distance>2)
    return 'accepted' if allowed else 'dip_disagrees'


def filtered(events,state,gate):
    out=[];counts=Counter();details=[]
    for e in events:
        t=pd.Timestamp(e['at'],unit='ms',tz='UTC');f=state.get(e['symbol'])
        row=f.loc[t] if f is not None and t in f.index else None
        reason=decision(e['side'],row,gate,e['atr']);counts[reason]+=1
        details.append(dict(event_id=e['event_id'],at=e['at'],side=e['side'],reason=reason))
        if reason=='accepted':out.append(e)
    return out,dict(counts),details
