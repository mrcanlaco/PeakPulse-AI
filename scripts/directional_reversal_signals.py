"""Causal Long mirror of the frozen 4h overextension reversal, offline only."""
import hashlib
import numpy as np
from short_multitimeframe_signals import features
from short_entry_guards import features as guard_features
from short_guard_ablation import decisions


def long_conditions(h):
    lower = h.mean20 - 2 * h.std20
    score = (h.mean20.shift() - h.close.shift()) / h.std20.shift().replace(0, np.nan)
    hit = (h.close.shift().lt(lower.shift()) & h.close.ge(lower.shift())
           & h.close.gt(h.open) & h.ret24.shift().le(-.05)
           & h.ready & np.isfinite(score))
    return hit.fillna(False), score


def generate(frames, funding, shorts):
    longs = []
    for coin, hourly in frames.items():
        if coin == "BTCUSDT":
            continue
        h = features(hourly)
        hit, score = long_conditions(h)
        last = -(10**18)
        for stamp in h.index[hit]:
            at = int(stamp.timestamp() * 1000)
            if at - last < 24 * 3600000:
                continue
            last = at
            longs.append(dict(symbol=coin, at=at, side="LONG", atr=float(h.at[stamp, "atr"]),
                              probability=float(score.at[stamp]),
                              event_id=hashlib.sha256(f"long_reversal_v1:{coin}:{at}".encode()).hexdigest()[:24]))
    longs.sort(key=lambda s: (s["at"], -s["probability"], s["symbol"]))
    # Match the frozen short guard's finite/fresh-data eligibility; reverse
    # only the ret6 predicate. The known funding is a readiness check, no
    # optimistic assumption about unknown future carry.
    observations = decisions(longs, guard_features(frames, funding))
    filtered = [s for s, obs in zip(longs, observations)
                if obs["status"] == "observed" and obs["values"]["ret6"] >= 0]
    result = {}
    for mask, events in [(0, longs), (2, filtered)]:
        result[f"long_mask{mask}"] = events
        result[f"short_mask{mask}"] = [dict(s, side="SHORT") for s in shorts[f"mask{mask}_none"]]
        result[f"both_mask{mask}"] = sorted(events + result[f"short_mask{mask}"],
            key=lambda s: (s["at"], -s["probability"], s["symbol"], s["side"]))
    return result, observations
