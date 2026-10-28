"""Entry-only market gates applied to immutable daily cross-sectional signals."""
from collections import Counter
import numpy as np
import pandas as pd
from cross_sectional_signals import enrich
from short_multitimeframe_signals import features

GATES=['none','btc_week','btc_trend','breadth60','consensus']


def market(frames):
    daily=enrich(frames)
    eligible=pd.concat({c:f.eligible for c,f in daily.items()},axis=1).fillna(False)
    above=pd.concat({c:f.eligible&f.close.gt(f.ema60) for c,f in daily.items()},axis=1).fillna(False)
    below=pd.concat({c:f.eligible&f.close.lt(f.ema60) for c,f in daily.items()},axis=1).fillna(False)
    count=eligible.sum(axis=1)
    state=pd.DataFrame(dict(coverage=count,above=above.sum(axis=1)/count.replace(0,np.nan),below=below.sum(axis=1)/count.replace(0,np.nan)))
    btc=features(frames['BTCUSDT']).reindex(state.index)
    state['btc_ready']=btc.ready.fillna(False)
    for key in ['close','ema20','ema60','ret24']:state['btc_'+key]=btc[key]
    state['btc_ret7']=(frames['BTCUSDT'].close/frames['BTCUSDT'].close.shift(168)-1).reindex(state.index)
    return state


def decision(side,row,gate):
    if side not in ['LONG','SHORT'] or gate not in GATES:raise ValueError('invalid_regime_input')
    if gate=='none':return 'accepted'
    if row is None:return 'missing_market_state'
    long=side=='LONG'
    if gate in ['btc_week','btc_trend','consensus']:
        needed=['btc_ret7'] if gate=='btc_week' else ['btc_close','btc_ema20','btc_ema60','btc_ret24']
        if not row['btc_ready'] or not all(np.isfinite(row[k]) for k in needed):return 'btc_not_ready'
    if gate in ['breadth60','consensus']:
        if row['coverage']<24 or not np.isfinite(row['above']) or not np.isfinite(row['below']):return 'breadth_not_ready'
    if gate=='btc_week':allow=row['btc_ret7']>0 if long else row['btc_ret7']<0
    else:
        trend=(row['btc_ema20']>row['btc_ema60'] and row['btc_close']>row['btc_ema20'] and row['btc_ret24']>0) if long else (row['btc_ema20']<row['btc_ema60'] and row['btc_close']<row['btc_ema20'] and row['btc_ret24']<0)
        breadth=row['above' if long else 'below']>=.6
        allow=trend if gate=='btc_trend' else breadth if gate=='breadth60' else trend and breadth
    return 'accepted' if allow else 'regime_disagrees'


def filtered(events,state,gate):
    output=[];counts=Counter()
    for e in events:
        t=pd.Timestamp(e['at'],unit='ms',tz='UTC');row=state.loc[t] if t in state.index else None
        reason=decision(e['side'],row,gate);counts[reason]+=1
        if reason=='accepted':output.append(e)
    return output,dict(counts)
