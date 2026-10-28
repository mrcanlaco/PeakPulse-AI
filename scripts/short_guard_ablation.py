"""Factorial decomposition of the frozen four-predicate entry guard."""

from collections import Counter

import numpy as np
import pandas as pd

COMPONENTS=[(1,"ret24_cap"),(2,"ret6_nonpositive"),(4,"funding_floor"),(8,"atr_cap")]


def definitions():
    return [dict(id=f"mask{mask:02d}",mask=mask,components=[name for bit,name in COMPONENTS if mask&bit]) for mask in range(16)]


def decisions(signals,enriched):
    result=[]
    for signal in signals:
        at=signal["at"];f=enriched.get(signal["symbol"]);t=pd.Timestamp(at,unit="ms",tz="UTC")
        index=-1 if f is None else f.index.searchsorted(t,side="right")-1
        record=dict(event_id=signal["event_id"],at=at,symbol=signal["symbol"])
        if index<0:result.append(dict(record,status="missing_features",pass_mask=None));continue
        stamp=f.index[index];r=f.iloc[index]
        if (t-stamp).total_seconds()>=3600 or not bool(r.ready):
            result.append(dict(record,status="stale_features",pass_mask=None));continue
        fields=["ret24","ret6","funding24","atr","close"]
        if not all(np.isfinite(r[k]) for k in fields):
            result.append(dict(record,status="missing_features",pass_mask=None));continue
        flags=[r.ret24<=.10,r.ret6<=0,r.funding24>=-.001,r.close>0 and 0<r.atr/r.close<=.05]
        bits=sum(bit for (bit,_),flag in zip(COMPONENTS,flags) if flag)
        result.append(dict(record,status="observed",pass_mask=bits,feature_at=int(stamp.timestamp()*1000),
                           values={k:float(r[k]) for k in fields}))
    return result


def apply_mask(signals,observations,mask):
    if mask not in range(16):raise ValueError("invalid_guard_mask")
    if len(signals)!=len(observations):raise ValueError("unaligned_guard_inputs")
    accepted=[];counts=Counter()
    for signal,r in zip(signals,observations):
        if any(signal[k]!=r[k] for k in ["event_id","at","symbol"]):raise ValueError("unaligned_guard_inputs")
        if mask==0:hit=True
        elif r["pass_mask"] is None:counts[r["status"]]+=1;continue
        else:hit=r["pass_mask"]&mask==mask
        counts["accepted" if hit else "guard_rejected"]+=1
        if hit:accepted.append(dict(signal))
    return accepted,dict(counts)
