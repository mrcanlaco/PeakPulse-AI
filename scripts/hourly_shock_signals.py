"""Closed-hour price/volume shocks: continuation versus reversal, offline only."""
import hashlib
import numpy as np
import pandas as pd


def definitions():
    return [dict(id=f'shock_{mode}_{tag}', mode=mode, threshold=threshold)
            for tag,threshold in [('a15',1.5),('a25',2.5)] for mode in ['follow','fade']]


def prepare(frames):
    result={}
    for coin,frame in frames.items():
        if coin=='BTCUSDT':continue
        h=frame.asfreq('1h').copy()
        columns=['open','high','low','close','quote_volume']
        valid=np.isfinite(h[columns]).all(axis=1)&h[columns].gt(0).all(axis=1)
        valid &= h.high.ge(h[['open','close','low']].max(axis=1)) & h.low.le(h[['open','close']].min(axis=1))
        tr=pd.concat([h.high-h.low,(h.high-h.close.shift()).abs(),(h.low-h.close.shift()).abs()],axis=1).max(axis=1)
        h['atr']=tr.shift().rolling(14,min_periods=14).mean()
        prior_volume=h.quote_volume.shift().rolling(24,min_periods=24).mean()
        h['volume_ratio']=h.quote_volume/prior_volume.where(prior_volume>0)
        h['shock']=(h.close-h.open)/h.atr.where(h.atr>0)
        h['close_location']=(h.close-h.low)/(h.high-h.low).where(h.high>h.low)
        h['priority']=h.shock.abs()*np.log1p(h.volume_ratio)
        h['ready']=(valid.rolling(72,min_periods=72).sum().eq(72)
                    & h.quote_volume.rolling(24,min_periods=24).sum().ge(2_000_000)
                    & np.isfinite(h[['atr','volume_ratio','shock','close_location','priority']]).all(axis=1))
        result[coin]=h
    return result


def generate(enriched):
    output={}
    for sp in definitions():
        events=[]
        for coin,h in enriched.items():
            upward=h.shock.ge(sp['threshold']) & h.close_location.ge(.8)
            downward=h.shock.le(-sp['threshold']) & h.close_location.le(.2)
            hit=h.ready & h.volume_ratio.ge(2) & (upward|downward)
            last=-(10**18)
            for t in h.index[hit]:
                at=int(t.timestamp()*1000)
                if at-last<6*3600000:continue
                last=at
                side='LONG' if bool(upward.loc[t])==(sp['mode']=='follow') else 'SHORT'
                events.append(dict(at=at,symbol=coin,side=side,atr=float(h.at[t,'atr']),
                    probability=float(h.at[t,'priority']),
                    event_id=hashlib.sha256(f'hourly_shock:{sp["id"]}:{coin}:{at}:{side}'.encode()).hexdigest()[:24]))
        output[sp['id']]=sorted(events,key=lambda e:(e['at'],-e['probability'],e['symbol']))
    return output
