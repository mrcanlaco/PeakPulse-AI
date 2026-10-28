"""Causal short hypotheses using known funding, trade flow and BTC-relative weakness."""

import hashlib
import itertools

import numpy as np
import pandas as pd


def definitions():
    return [dict(id=f"{family}_{level}_{regime}_h{cooldown}", family=family,
                 strength=level, regime=regime, cooldown_hours=cooldown)
            for family,level,regime,cooldown in itertools.product(
                ["positive_carry", "buyer_absorption", "seller_pressure", "relative_weakness"],
                ["loose", "strict"], ["any", "btc_bear"], [6,24])]


def known_funding(index, schedule):
    """Only settlements >=60s old. No use of next funding rate or interval."""
    stamps = np.array([r[0] for r in schedule], dtype=np.int64)
    rates = np.array([r[1] for r in schedule], dtype=float)
    if len(stamps) and (np.any(np.diff(stamps) <= 0) or not np.isfinite(rates).all()):
        raise ValueError("ambiguous_funding_history")
    result = pd.DataFrame(index=index, columns=["last_funding", "funding24"], dtype=float)
    if not len(stamps):
        return result
    times = index.as_unit("ms").asi8 - 60000
    right = np.searchsorted(stamps, times, side="right")
    left = np.searchsorted(stamps, times-86400000, side="right")
    totals = np.r_[0, np.cumsum(rates)]
    good = (right>0) & (times-stamps[np.maximum(right-1,0)] <= 8*3600000+300000)
    result.loc[good,"last_funding"] = rates[right[good]-1]
    full = good & (stamps[0] <= times-86400000)
    result.loc[full,"funding24"] = totals[right[full]]-totals[left[full]]
    return result


def enrich(frames, flow, funding):
    btc = frames["BTCUSDT"]
    btc_bear = btc.ready & btc.close.lt(btc.ema60) & btc.ret24.lt(0)
    result = {}
    for coin,frame in frames.items():
        if coin == "BTCUSDT":
            continue
        h = frame.copy()
        h["buy6"] = flow[coin].buy_fraction6.reindex(h.index)
        h["buy1"] = flow[coin].buy_fraction1.reindex(h.index)
        h["volume_ratio"] = h.quote_volume / h.quote_volume.shift(1).rolling(24,min_periods=24).mean()
        h["prior_low12"] = h.low.shift(1).rolling(12,min_periods=12).min()
        h["relative24"] = h.ret24 - btc.ret24.reindex(h.index)
        h["btc_bear"] = btc_bear.reindex(h.index).fillna(False)
        h["btc_ready"] = btc.ready.reindex(h.index).fillna(False)
        known = known_funding(h.index, funding[coin])
        h["last_funding"], h["funding24"] = known.last_funding,known.funding24
        result[coin] = h
    return result


def conditions(h, spec):
    strict = spec["strength"] == "strict"
    bearish = h.close < h.open
    downtrend = h.ema20.lt(h.ema60) & h.close.lt(h.ema20)
    family = spec["family"]
    if family == "positive_carry":
        hit = downtrend & bearish & h.last_funding.ge(0) & h.funding24.ge(0.001 if strict else 0.0003)
        score = h.funding24
    elif family == "buyer_absorption":
        hit = h.buy6.ge(0.60 if strict else 0.55) & h.ret6.le(0) & bearish & h.close.lt(h.ema20)
        score = h.buy6 - 0.5 - h.ret6
    elif family == "seller_pressure":
        hit = (h.buy6.le(0.40 if strict else 0.45) & h.ret6.lt(0) & downtrend
               & h.close.lt(h.prior_low12) & h.volume_ratio.ge(1.5 if strict else 1.0))
        score = (0.5-h.buy6)*h.volume_ratio
    elif family == "relative_weakness":
        hit = (downtrend & bearish & h.btc_ready & h.relative24.le(-0.06 if strict else -0.03)
               & h.high.ge(h.ema20) & h.buy1.le(0.50))
        score = -h.relative24
    else:
        raise ValueError("unknown_funding_flow_family")
    if spec["regime"] == "btc_bear":
        hit &= h.btc_bear
    hit &= h.ready
    return hit.fillna(False), score


def generate(frames, flow, funding, specs=None):
    enriched = enrich(frames, flow, funding)
    output = {}
    for spec in definitions() if specs is None else specs:
        signals = []
        for coin,h in enriched.items():
            hit,score = conditions(h,spec)
            last = -(10**18)
            for t in h.index[hit]:
                at = int(t.timestamp()*1000)
                if at-last < spec["cooldown_hours"]*3600000:
                    continue
                last=at
                signals.append(dict(symbol=coin, at=at, atr=float(h.at[t,"atr"]),
                                    probability=float(score.at[t]),
                                    event_id=hashlib.sha256(f"flow:{spec['id']}:{coin}:{at}".encode()).hexdigest()[:24]))
        output[spec["id"]] = sorted(signals,key=lambda s:(s["at"],-s["probability"],s["symbol"]))
    return output
