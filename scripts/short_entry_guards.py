"""Entry-time guards from completed hourly bars and already settled funding."""

from collections import Counter

import numpy as np
import pandas as pd
from short_funding_flow_signals import known_funding


def definitions():
    return ["none","nonnegative_carry","anti_squeeze","trend_confirmation"]


def features(frames,funding):
    result={};btc=frames["BTCUSDT"]
    for coin,h in frames.items():
        if coin=="BTCUSDT":continue
        f=h[["close","atr","ret6","ret24","ema20","ema60","ready"]].copy()
        f["funding24"]=known_funding(f.index,funding[coin]).funding24
        f["btc_ret24"]=btc.ret24.reindex(f.index)
        f["btc_ready"]=btc.ready.reindex(f.index).fillna(False)
        result[coin]=f
    return result


def filter_entries(entries,enriched,guard):
    if guard not in definitions():raise ValueError("unknown_guard")
    accepted=[];records=[]
    for signal in entries:
        at=signal["at"]
        record=dict(event_id=signal["event_id"],at=at,symbol=signal["symbol"])
        if guard=="none":
            accepted.append(dict(signal));records.append(dict(record,status="accepted"));continue
        f=enriched.get(signal["symbol"])
        timestamp=pd.Timestamp(at,unit="ms",tz="UTC")
        index=-1 if f is None else f.index.searchsorted(timestamp,side="right")-1
        if index<0:
            records.append(dict(record,status="missing_features"));continue
        t=f.index[index];row=f.iloc[index]
        # Hourly close at t is available at t; do not carry stale data beyond its hour.
        if (timestamp-t).total_seconds()>=3600 or not bool(row.ready):
            records.append(dict(record,status="stale_features"));continue
        fields={"nonnegative_carry":["funding24"],
                "anti_squeeze":["funding24","ret6","ret24","atr","close"],
                "trend_confirmation":["ret6","ema20","ema60","btc_ret24"]}[guard]
        if not all(np.isfinite(row[k]) for k in fields):
            records.append(dict(record,status="missing_features"));continue
        if guard=="nonnegative_carry":hit=row.funding24>=0
        elif guard=="anti_squeeze":
            hit=(row.close>0 and row.ret24<=.10 and row.ret6<=0
                 and row.funding24>=-.001 and 0<row.atr/row.close<=.05)
        else:hit=bool(row.btc_ready) and row.btc_ret24<0 and row.ema20<row.ema60 and row.ret6<0
        records.append(dict(record,status="accepted" if hit else "guard_rejected",feature_at=int(t.timestamp()*1000)))
        if hit:accepted.append(dict(signal))
    return accepted,dict(counts=dict(Counter(r["status"] for r in records)),events=records)
