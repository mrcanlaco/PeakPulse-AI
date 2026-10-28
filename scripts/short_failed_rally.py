"""Causal three-stage hourly failed rallies inside a completed 4h downtrend."""
import hashlib
import itertools
import numpy as np
import pandas as pd
from short_multitimeframe_signals import features


def definitions():
    return [dict(id=f"rally{a}_ttl{h}_{regime}",bounce_atr=a,ttl_hours=h,regime=regime,cooldown_hours=24)
            for a,h,regime in itertools.product([1,2],[6,24],["any","btc_bear"])]


def prepare(frames):
    btc=features(frames["BTCUSDT"])
    btc_bear=btc.ready & btc.ema20.lt(btc.ema60) & btc.close.lt(btc.ema20) & btc.ret24.lt(0)
    result={}
    for coin,h in frames.items():
        if coin=="BTCUSDT":continue
        f=h[["open","high","low","close","quote_volume"]].copy()
        f=f.reindex(pd.date_range(f.index.min(),f.index.max(),freq="h",tz="UTC"))
        valid=np.isfinite(f).all(axis=1)
        tr=pd.concat([f.high-f.low,(f.high-f.close.shift()).abs(),(f.low-f.close.shift()).abs()],axis=1).max(axis=1)
        f["hour_atr"]=tr.rolling(14,min_periods=14).mean()
        f["prior_low12"]=f.low.shift().rolling(12,min_periods=12).min()
        four=features(h).reindex(f.index,method="ffill")
        f["atr"]=four.atr
        f["bear"]=four.ready & four.ema20.lt(four.ema60) & four.close.lt(four.ema20) & four.ret24.lt(0)
        f["btc_bear"]=btc_bear.reindex(f.index,method="ffill").fillna(False)
        f["ready"]=valid.rolling(72,min_periods=72).sum().eq(72) & four.ready.fillna(False) & f.hour_atr.gt(0)
        result[coin]=f
    return result


def scan(coin,f,spec):
    rows=[];state=None;last=-(10**18);previous=None
    for t,r in zip(f.index,f.itertuples(index=False)):
        at=int(t.timestamp()*1000)
        contiguous=previous is not None and at-previous[0]==3600000
        finite=all(np.isfinite(getattr(r,k)) for k in ["open","low","close","hour_atr","atr","prior_low12"])
        valid=bool(r.ready) and finite
        gate=valid and bool(r.bear) and (spec["regime"]=="any" or bool(r.btc_bear))
        if spec["regime"] not in ["any","btc_bear"]:raise ValueError("unknown_regime")
        if not valid or not contiguous:state=None
        if state and (at-state["arm_at"]>spec["ttl_hours"]*3600000 or not gate):state=None
        if state:
            if state["bounce_at"] is None:
                state["low"]=min(state["low"],r.close)
                if r.close>=state["low"]+spec["bounce_atr"]*state["frozen_atr"]:
                    state["bounce_at"]=at;state["peak"]=r.close
            else:
                state["peak"]=max(state["peak"],r.close)
                if r.close<previous[1] and r.close<r.open:
                    rows.append(dict(symbol=coin,at=at,atr=float(r.atr),probability=float((state["peak"]-r.close)/state["frozen_atr"]),
                        event_id=hashlib.sha256(f"failed_rally:{spec['id']}:{coin}:{at}".encode()).hexdigest()[:24],
                        arm_at=state["arm_at"],bounce_at=state["bounce_at"],frozen_hour_atr=state["frozen_atr"],bounce_low=state["low"]))
                    last=at;state=None
        elif gate and at-last>=spec["cooldown_hours"]*3600000 and r.close<r.prior_low12:
            state=dict(arm_at=at,low=float(r.close),frozen_atr=float(r.hour_atr),bounce_at=None)
        previous=(at,float(r.low))
    return rows


def generate(prepared,specs=None):
    result={}
    for s in definitions() if specs is None else specs:
        rows=[r for c,f in prepared.items() for r in scan(c,f,s)]
        result[s["id"]]=sorted(rows,key=lambda r:(r["at"],-r["probability"],r["symbol"]))
    return result
