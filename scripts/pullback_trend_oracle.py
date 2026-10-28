"""Separate indexed-return and 4h grouping oracle for entry confirmations."""
import numpy as np
import pandas as pd


def expected(events,frames):
    cache={};out={g:[] for g in ['none','ret24','ret72','ema_trend','trend_ret24','persistence5']}
    for coin in {e['symbol'] for e in events}:
        h=frames[coin].asfreq('1h');close=h.close
        groups=close.groupby(close.index.ceil('4h'))
        bars=groups.last().asfreq('4h').where(groups.count().asfreq('4h').eq(4))
        ready=bars.notna()&np.isfinite(bars)&bars.gt(0)
        cache[coin]=(close,bars,ready.rolling(72,min_periods=72).sum().eq(72),bars.ewm(span=20,adjust=False,min_periods=20).mean(),bars.ewm(span=60,adjust=False,min_periods=60).mean())
    for e in events:
        close,bars,ready,fast,slow=cache[e['symbol']];t=pd.Timestamp(e['at'],unit='ms',tz='UTC');d=1 if e['side']=='LONG' else -1
        out['none'].append(e)
        if t not in close.index:continue
        i=close.index.get_loc(t);p=close.iloc[i];flags={}
        for n in [24,72,168]:
            sample=close.iloc[max(0,i-n):i+1].to_numpy()
            flags[n]=i>=n and len(sample)==n+1 and np.isfinite(sample).all() and (sample>0).all()
        r24=flags[24] and d*np.log(p/close.iloc[i-24])>0
        r72=flags[72] and d*np.log(p/close.iloc[i-72])>0
        if r24:out['ret24'].append(e)
        if r72:out['ret72'].append(e)
        k=bars.index.searchsorted(t,side='right')-1
        trend=k>=0 and ready.iloc[k] and np.isfinite(p) and d*(p-fast.iloc[k])>0 and d*(fast.iloc[k]-slow.iloc[k])>0
        if trend:out['ema_trend'].append(e)
        if trend and r24:out['trend_ret24'].append(e)
        if flags[168] and sum(d*np.log(close.iloc[i-24*j]/close.iloc[i-24*(j+1)])>0 for j in range(7))>=5:out['persistence5'].append(e)
    return out
