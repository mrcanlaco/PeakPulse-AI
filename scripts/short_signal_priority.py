"""Entry queue priorities from then-known features; preserve every source event."""
import math
from collections import Counter
import pandas as pd
from short_multitimeframe_signals import features
from short_funding_flow_signals import known_funding

RANKS=["zscore","impulse_atr","low_vol","liquidity","funding24","weak6","body_atr"]


def priorities(signal,bar,hour,funding24):
    inputs=[signal["probability"],bar.ret24,bar.atr,bar.close,bar.open,bar.volume24,hour.ret6,funding24]
    if bar.close<=0 or bar.atr<=0 or not all(math.isfinite(v) for v in inputs):
        raise ValueError("priority_features_missing")
    values=dict(zscore=signal["probability"],impulse_atr=abs(bar.ret24)/(bar.atr/bar.close),
        low_vol=-bar.atr/bar.close,liquidity=bar.volume24,funding24=round(funding24,12),
        weak6=-hour.ret6,body_atr=(bar.open-bar.close)/bar.atr)
    if bar.close<=0 or bar.atr<=0 or not all(math.isfinite(v) for v in values.values()):
        raise ValueError("priority_features_missing")
    return {k:float(v) for k,v in values.items()}


def observe(signals,frames,funding):
    four={c:features(f) for c,f in frames.items() if c!="BTCUSDT"}
    carry={c:known_funding(f.index,funding[c]) for c,f in four.items()};records=[]
    for signal in signals:
        c=signal["symbol"];t=pd.Timestamp(signal["at"],unit="ms",tz="UTC")
        if t not in four[c].index or t not in frames[c].index:
            raise ValueError("priority_closed_bar_missing")
        bar=four[c].loc[t];hour=frames[c].loc[t]
        if not bool(bar.ready) or not bool(hour.ready):raise ValueError("priority_features_not_ready")
        scores=priorities(signal,bar,hour,carry[c].at[t,"funding24"])
        records.append(dict(event_id=signal["event_id"],symbol=c,at=signal["at"],scores=scores,
            values=dict(close=float(bar.close),open=float(bar.open),atr=float(bar.atr),ret24=float(bar.ret24),
                ret6=float(hour.ret6),volume24=float(bar.volume24),known_funding24=float(carry[c].at[t,"funding24"]))))
    return records


def rank(signals,observations):
    if len(signals)!=len(observations):raise ValueError("unaligned_priority_inputs")
    output={k:[] for k in RANKS}
    for signal,obs in zip(signals,observations):
        if any(signal[k]!=obs[k] for k in ["event_id","symbol","at"]):raise ValueError("unaligned_priority_inputs")
        for key in RANKS:output[key].append(dict(signal,probability=obs["scores"][key]))
    for key in RANKS:output[key].sort(key=lambda r:(r["at"],-r["probability"],r["symbol"]))
    return output


def collisions(signals):
    counts=Counter(s["at"] for s in signals)
    return dict(events=len(signals),timestamps=len(counts),collision_timestamps=sum(n>1 for n in counts.values()),
        events_in_collisions=sum(n for n in counts.values() if n>1),maximum_candidates=max(counts.values(),default=0))
