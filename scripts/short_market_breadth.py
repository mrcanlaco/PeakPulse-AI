"""Weekly relative weakness with causal broad-market state, research only."""

import hashlib
import itertools
import numpy as np
import pandas as pd
from short_multitimeframe_signals import features as four_hour_features


def definitions():
    return [dict(id=f"{rank}_{regime}_{entry}",ranking=rank,regime=regime,entry=entry,cooldown_hours=24)
            for rank,regime,entry in itertools.product(["raw7d","beta7d"],["any","breadth60","breadth75_btc"],["scheduled","pullback"])]


def enrich(frames):
    btc=frames["BTCUSDT"];br=np.log(btc.close/btc.close.shift(1));result={}
    btc_four=four_hour_features(btc)
    for coin,hourly in frames.items():
        if coin=="BTCUSDT":continue
        r=np.log(hourly.close/hourly.close.shift(1));aligned=br.reindex(hourly.index)
        variance=aligned.rolling(168,min_periods=168).var(ddof=1)
        beta=(r.rolling(168,min_periods=168).cov(aligned)/variance.where(variance>1e-12)).shift(24)
        past=np.log(hourly.close.shift(24)/hourly.close.shift(192))
        btc_past=np.log(btc.close.shift(24)/btc.close.shift(192)).reindex(hourly.index)
        f=four_hour_features(hourly)
        f["beta"]=beta.reindex(f.index);f["raw7d"]=past.reindex(f.index)
        f["btc_past7d"]=btc_past.reindex(f.index);f["beta7d"]=f.raw7d-f.beta*f.btc_past7d
        f["eligible"]=f.ready & np.isfinite(f[["beta","raw7d","beta7d","btc_past7d"]]).all(axis=1)
        f["btc_bear"]=(btc_four.ready & btc_four.ema20.lt(btc_four.ema60) & btc_four.close.lt(btc_four.ema20) & btc_four.ret24.lt(0)).reindex(f.index).fillna(False)
        result[coin]=f
    return result


def market_state(enriched,min_coverage=24):
    eligible=pd.concat({c:f.eligible for c,f in enriched.items()},axis=1).fillna(False)
    below=pd.concat({c:(f.close<f.ema60)&f.eligible for c,f in enriched.items()},axis=1).fillna(False)
    count=eligible.sum(axis=1)
    state=pd.DataFrame(dict(coverage=count,breadth_below_ema60=below.sum(axis=1)/count.replace(0,np.nan),ready=count>=min_coverage))
    ranks={key:pd.concat({c:f[key].where(f.eligible) for c,f in enriched.items()},axis=1).rank(axis=1,pct=True,ascending=True,method="average") for key in ["raw7d","beta7d"]}
    return state,ranks


def conditions(f,state,rank,spec):
    rank=rank.reindex(f.index);state=state.reindex(f.index)
    score=-f[spec["ranking"]]
    hit=(f.eligible & state.ready.fillna(False) & rank.le(.20) & score.gt(0)
         & f.ema20.lt(f.ema60) & f.close.lt(f.ema20) & f.ret24.lt(0))
    if spec["regime"]=="breadth60":hit &= state.breadth_below_ema60.ge(.60)
    elif spec["regime"]=="breadth75_btc":hit &= state.breadth_below_ema60.ge(.75)&f.btc_bear
    elif spec["regime"]!="any":raise ValueError("unknown_breadth_regime")
    if spec["entry"]=="pullback":hit &= f.high.ge(f.ema20)&f.close.lt(f.open)
    elif spec["entry"]!="scheduled":raise ValueError("unknown_breadth_entry")
    return hit.fillna(False),score


def generate(enriched,state,ranks,specs=None):
    output={}
    for spec in definitions() if specs is None else specs:
        rows=[]
        for coin,f in enriched.items():
            hit,score=conditions(f,state,ranks[spec["ranking"]][coin],spec);last=-(10**18)
            for t in f.index[hit]:
                at=int(t.timestamp()*1000)
                if at-last<spec["cooldown_hours"]*3600000:continue
                last=at
                rows.append(dict(symbol=coin,at=at,atr=float(f.at[t,"atr"]),probability=float(score.at[t]),
                    event_id=hashlib.sha256(f"breadth:{spec['id']}:{coin}:{at}".encode()).hexdigest()[:24]))
        output[spec["id"]]=sorted(rows,key=lambda s:(s["at"],-s["probability"],s["symbol"]))
    return output
