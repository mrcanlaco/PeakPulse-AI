"""Direct closed-price differences and independently grouped EMA gate oracle."""
import numpy as np
import pandas as pd


def expected(events,frames):
    out={g:[] for g in ['none','counter24','counter72','dip24_shallow','dip24_deep','ema_pullback']};cache={}
    for coin in {e['symbol'] for e in events}:
        prices=frames[coin].asfreq('1h').close
        groups=prices.groupby(prices.index.ceil('4h'))
        bars=groups.last().asfreq('4h').where(groups.count().asfreq('4h').eq(4))
        ready=(np.isfinite(bars)&bars.gt(0)).rolling(72,min_periods=72).sum().eq(72)
        cache[coin]=(prices,bars,ready,bars.ewm(span=20,adjust=False,min_periods=20).mean(),bars.ewm(span=60,adjust=False,min_periods=60).mean())
    for e in events:
        price,bars,ready,fast,slow=cache[e['symbol']];t=pd.Timestamp(e['at'],unit='ms',tz='UTC');d=1 if e['side']=='LONG' else -1
        out['none'].append(e)
        if t not in price.index:continue
        i=price.index.get_loc(t);p=price.iloc[i]
        for n in [24,72]:
            sample=price.iloc[max(0,i-n):i+1].to_numpy()
            if i<n or len(sample)!=n+1 or not np.isfinite(sample).all() or not (sample>0).all():continue
            adverse=d*(price.iloc[i-n]-p)
            if adverse>0:
                out[f'counter{n}'].append(e)
                if n==24 and np.isfinite(e['atr']) and e['atr']>0:
                    out['dip24_shallow' if adverse<=2*e['atr'] else 'dip24_deep'].append(e)
        k=bars.index.searchsorted(t,side='right')-1
        if k>=0 and ready.iloc[k] and np.isfinite(p) and d*(fast.iloc[k]-slow.iloc[k])>0 and d*(p-fast.iloc[k])<0:out['ema_pullback'].append(e)
    return out
