"""Closed-4h trend continuation and causal market-direction gates."""
import hashlib
import itertools
import numpy as np
import pandas as pd
from short_multitimeframe_signals import features


def definitions():
    return [dict(id=f"{family}_{regime}_{mode}", family=family, regime=regime, mode=mode)
            for family, regime, mode in itertools.product(
                ["breakout", "pullback"], ["any", "breadth60_btc"], ["long", "both_trend", "hybrid"])]


def prepare(frames):
    enriched = {c: features(f) for c, f in frames.items()}
    for f in enriched.values():
        f["prior_low20"] = f.low.shift().rolling(20, min_periods=20).min()
    alts = {c:f for c,f in enriched.items() if c != "BTCUSDT"}
    eligible = pd.concat({c:f.ready for c,f in alts.items()}, axis=1).fillna(False)
    above = pd.concat({c:f.ready & f.close.gt(f.ema60) for c,f in alts.items()}, axis=1).fillna(False)
    below = pd.concat({c:f.ready & f.close.lt(f.ema60) for c,f in alts.items()}, axis=1).fillna(False)
    count = eligible.sum(axis=1)
    state = pd.DataFrame(dict(coverage=count, above=above.sum(axis=1)/count.replace(0,np.nan),
                             below=below.sum(axis=1)/count.replace(0,np.nan)))
    btc = enriched["BTCUSDT"].reindex(state.index)
    state["long_allowed"] = (count.ge(24) & state.above.ge(.6) & btc.ready.fillna(False)
                              & btc.ema20.gt(btc.ema60) & btc.close.gt(btc.ema20) & btc.ret24.gt(0))
    state["short_allowed"] = (count.ge(24) & state.below.ge(.6) & btc.ready.fillna(False)
                               & btc.ema20.lt(btc.ema60) & btc.close.lt(btc.ema20) & btc.ret24.lt(0))
    return enriched, state


def conditions(f, state, family, regime, side):
    if side not in ["LONG", "SHORT"] or family not in ["breakout", "pullback"]:
        raise ValueError("invalid_trend_rule")
    long = side == "LONG"
    trend = (f.ema20.gt(f.ema60) & f.close.gt(f.ema20) & f.ret24.gt(0)) if long else (
             f.ema20.lt(f.ema60) & f.close.lt(f.ema20) & f.ret24.lt(0))
    candle = f.close.gt(f.open) if long else f.close.lt(f.open)
    if family == "breakout":
        entry = f.close.gt(f.prior_high20) if long else f.close.lt(f.prior_low20)
        volume = f.volume_ratio.ge(1.5)
    else:
        entry = f.low.le(f.ema20) if long else f.high.ge(f.ema20)
        volume = f.volume_ratio.ge(1.)
    score = f.ret24.abs() / (f.atr/f.close)
    hit = f.ready & trend & candle & entry & volume & np.isfinite(score)
    if regime == "breadth60_btc": hit &= state[f"{side.lower()}_allowed"].reindex(f.index).fillna(False)
    elif regime != "any": raise ValueError("invalid_trend_regime")
    return hit.fillna(False), score


def generate(enriched, state, frozen_shorts):
    output = {}
    for spec in definitions():
        rows = []
        sides = ["LONG", "SHORT"] if spec["mode"] == "both_trend" else ["LONG"]
        for coin, f in enriched.items():
            if coin == "BTCUSDT": continue
            for side in sides:
                hit, score = conditions(f, state, spec["family"], spec["regime"], side)
                last = -(10**18)
                for t in f.index[hit]:
                    at = int(t.timestamp()*1000)
                    if at-last < 86400000: continue
                    last = at
                    # Identity reflects the event rule, not the portfolio mode.
                    identity = f"trend_v1:{spec['family']}:{spec['regime']}:{side}:{coin}:{at}"
                    rows.append(dict(at=at, symbol=coin, side=side, atr=float(f.at[t,"atr"]),
                        probability=float(score.at[t]), event_id=hashlib.sha256(identity.encode()).hexdigest()[:24],
                        family=spec["family"]))
        if spec["mode"] == "hybrid":
            for event in frozen_shorts:
                t = pd.Timestamp(event["at"],unit="ms",tz="UTC"); f = enriched[event["symbol"]]
                if t not in f.index: continue
                r = f.loc[t]
                if spec["regime"] == "breadth60_btc" and not bool(state.loc[t,"short_allowed"]): continue
                score = abs(r.ret24)/(r.atr/r.close)
                if not np.isfinite(score): continue
                # Keep frozen short event, ATR, cooldown; common priority scale
                # is deliberately changed for the mixed-source queue.
                rows.append(dict(event, side="SHORT", probability=float(score), family="reversal"))
        output[spec["id"]] = sorted(rows,key=lambda r:(r["at"],-r["probability"],r["symbol"],r["side"]))
    return output
