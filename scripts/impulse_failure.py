"""Frozen signal-candle invalidation using completed hourly trade closes."""
import math
import pandas as pd

HOUR=3600000
MODES={'open1':('open',1),'open2':('open',2),'extreme1':('extreme',1),'extreme2':('extreme',2)}


def context(events,frames):
    result={}
    for e in events:
        at=e.get('source_at',e['at']);t=pd.Timestamp(at,unit='ms',tz='UTC')
        row=frames[e['symbol']].loc[t]
        values={k:float(row[k]) for k in ['open','high','low','close']}
        if not all(math.isfinite(v) and v>0 for v in values.values()):raise ValueError('missing_impulse_candle')
        if not values['low']<=min(values['open'],values['close'])<=max(values['open'],values['close'])<=values['high']:
            raise ValueError('invalid_impulse_candle')
        result[e['event_id']]=dict(at=at,symbol=e['symbol'],side=e['side'],**values)
    return result


def invalidation(prices,source,opened,at,mode):
    if mode not in MODES:raise ValueError('invalid_impulse_exit_mode')
    field,count=MODES[mode]
    if at%HOUR or at-(count-1)*HOUR<=opened:return None
    if source['side'] not in ['LONG','SHORT']:raise ValueError('invalid_impulse_side')
    long=source['side']=='LONG'
    boundary=source['open'] if field=='open' else source['low' if long else 'high']
    stamps=[at-lag*HOUR for lag in reversed(range(count))];closes=[]
    for t in stamps:
        point=prices.get(t,{})
        value=point.get('execution_close',math.nan)
        if not math.isfinite(value) or value<=0:raise ValueError(f'missing_impulse_exit_close:{source["symbol"]}:{t}')
        closes.append(value)
    hit=all(v<boundary for v in closes) if long else all(v>boundary for v in closes)
    if hit:
        return dict(impulse_mode=mode,impulse_boundary=boundary,hourly_times=stamps,hourly_closes=closes)
    return None
