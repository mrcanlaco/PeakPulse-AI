"""Closed four-hour reversal/breakout hypotheses with completed daily context."""

import hashlib
import itertools

import numpy as np
import pandas as pd


def aggregate(hourly, frequency, expected):
    """Hourly index is candle CLOSE time; right-closed bins avoid look-ahead."""
    value=hourly.resample(frequency,closed="right",label="right",origin="epoch").agg(
        open=("open","first"),high=("high","max"),low=("low","min"),close=("close","last"),
        quote_volume=("quote_volume","sum"),hours=("close","count"))
    value.loc[value.hours.ne(expected),["open","high","low","close","quote_volume"]]=np.nan
    return value


def daily_features(hourly):
    d=aggregate(hourly,"24h",24)
    d["ema10"]=d.close.ewm(span=10,adjust=False,min_periods=10).mean()
    d["ema20"]=d.close.ewm(span=20,adjust=False,min_periods=20).mean()
    d["ret7"]=d.close/d.close.shift(7)-1
    d["ready"]=d.hours.eq(24).rolling(21,min_periods=21).sum().eq(21)
    d["bear"]=d.ready & d.ema10.lt(d.ema20) & d.close.lt(d.ema20) & d.ret7.lt(0)
    return d


def features(hourly):
    h=aggregate(hourly,"4h",4)
    close=h.close
    h["ema20"]=close.ewm(span=20,adjust=False,min_periods=20).mean()
    h["ema60"]=close.ewm(span=60,adjust=False,min_periods=60).mean()
    tr=pd.concat([h.high-h.low,(h.high-close.shift()).abs(),(h.low-close.shift()).abs()],axis=1).max(axis=1)
    h["atr"]=tr.rolling(14,min_periods=14).mean()
    h["ret24"]=close/close.shift(6)-1
    h["volume24"]=h.quote_volume.rolling(6,min_periods=6).sum()
    h["volume_ratio"]=h.quote_volume/h.quote_volume.shift(1).rolling(20,min_periods=20).mean()
    h["mean20"]=close.rolling(20,min_periods=20).mean()
    h["std20"]=close.rolling(20,min_periods=20).std(ddof=0)
    h["prior_high20"]=h.high.shift(1).rolling(20,min_periods=20).max()
    h["prior_high40"]=h.high.shift(1).rolling(40,min_periods=40).max()
    h["prior_low12"]=h.low.shift(1).rolling(12,min_periods=12).min()
    width=(h.high.rolling(12,min_periods=12).max()-h.low.rolling(12,min_periods=12).min())/close.rolling(12,min_periods=12).mean()
    h["prior_width"]=width.shift(1)
    h["width_q30"]=width.shift(1).rolling(60,min_periods=60).quantile(.3)
    h["width_q20"]=width.shift(1).rolling(60,min_periods=60).quantile(.2)
    h["wick"]=(h.high-pd.concat([h.open,close],axis=1).max(axis=1))/(h.high-h.low).replace(0,np.nan)
    h["ready"]=(h.hours.eq(4).rolling(72,min_periods=72).sum().eq(72)
                 & h.atr.gt(0) & h.volume24.ge(2_000_000))
    daily=daily_features(hourly)
    h["daily_bear"]=daily.bear.reindex(h.index,method="ffill").fillna(False)
    return h


def definitions():
    return [dict(id=f"{family}_{strength}_{regime}",family=family,strength=strength,regime=regime,cooldown_hours=24)
            for family,strength,regime in itertools.product(
                ["overextension_reversal","failed_breakout","daily_down_pullback","compression_break"],
                ["loose","strict"],["any","btc_daily_bear"])]


def conditions(h,spec):
    strict=spec["strength"]=="strict"
    red=h.close.lt(h.open)
    family=spec["family"]
    if family=="overextension_reversal":
        upper=h.mean20+(3 if strict else 2)*h.std20
        # The previous candle closed outside its own then-known band.
        hit=(h.close.shift(1).gt(upper.shift(1)) & h.close.le(upper.shift(1)) & red
             & h.ret24.shift(1).ge(.10 if strict else .05))
        score=(h.close.shift(1)-h.mean20.shift(1))/h.std20.shift(1).replace(0,np.nan)
    elif family=="failed_breakout":
        prior=h["prior_high40" if strict else "prior_high20"]
        hit=(h.high.gt(prior) & h.close.lt(prior) & red & h.wick.ge(.6 if strict else .4)
             & h.volume_ratio.ge(2 if strict else 1.5) & h.ret24.ge(0))
        score=(h.high-h.close)/h.atr
    elif family=="daily_down_pullback":
        hit=(h.daily_bear & h.high.ge(h.ema20) & h.close.lt(h.ema20) & red
             & h.volume_ratio.ge(1.5 if strict else 1))
        score=(h.high-h.close)/h.atr
    elif family=="compression_break":
        hit=(h.prior_width.le(h["width_q20" if strict else "width_q30"])
             & h.close.lt(h.prior_low12) & red & h.volume_ratio.ge(2 if strict else 1.5))
        score=(h.prior_low12-h.close)/h.atr*h.volume_ratio
    else:raise ValueError("unknown_multitimeframe_family")
    if spec["regime"]=="btc_daily_bear":hit &= h.btc_daily_bear
    return (hit & h.ready & np.isfinite(score)).fillna(False),score


def generate(frames,specs=None):
    specs=definitions() if specs is None else specs
    btc=daily_features(frames["BTCUSDT"])
    enriched={coin:features(h) for coin,h in frames.items() if coin!="BTCUSDT"}
    for h in enriched.values():
        h["btc_daily_bear"]=btc.bear.reindex(h.index,method="ffill").fillna(False)
    result={}
    for spec in specs:
        rows=[]
        for coin,h in enriched.items():
            hit,score=conditions(h,spec);last=-(10**18)
            for t in h.index[hit]:
                at=int(t.timestamp()*1000)
                if at-last<spec["cooldown_hours"]*3600000:continue
                last=at
                rows.append(dict(symbol=coin,at=at,atr=float(h.at[t,"atr"]),probability=float(score.at[t]),
                                 event_id=hashlib.sha256(f"multitf:{spec['id']}:{coin}:{at}".encode()).hexdigest()[:24]))
        result[spec["id"]]=sorted(rows,key=lambda s:(s["at"],-s["probability"],s["symbol"]))
    return result
