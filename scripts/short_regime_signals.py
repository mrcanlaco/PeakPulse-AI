"""New causal hourly price/volume short hypotheses for the 50% research goal."""

import hashlib
import itertools


def definitions():
    return [
        dict(
            id=f"{family}_{regime}_h{hours}",
            family=family,
            regime=regime,
            cooldown_hours=hours,
        )
        for family, regime, hours in itertools.product(
            ["failed_high", "exhaustion", "ema_reject", "acceleration"],
            ["any", "btc_bear"],
            [6, 24],
        )
    ]


def features(h):
    f = h.copy()
    f["prior_high24"] = h.high.shift(1).rolling(24, min_periods=24).max()
    f["prior_low12"] = h.low.shift(1).rolling(12, min_periods=12).min()
    f["volume_ratio"] = (
        h.quote_volume / h.quote_volume.shift(1).rolling(24, min_periods=24).mean()
    )
    f["range_atr"] = (h.high - h.low) / h.atr
    f["close_location"] = (h.close - h.low) / (h.high - h.low).where(h.high > h.low)
    return f


def conditions(f, family):
    bearish = f.close < f.open
    downtrend = (f.ema20 < f.ema60) & (f.close < f.ema20)
    if family == "failed_high":
        hit = (
            (f.high > f.prior_high24)
            & (f.close < f.prior_high24)
            & bearish
            & f.volume_ratio.ge(1)
        )
        score = (f.high - f.close) / f.atr
    elif family == "exhaustion":
        hit = (
            f.ret6.ge(0.10)
            & f.wick.ge(0.5)
            & bearish
            & f.volume_ratio.ge(1.5)
            & f.range_atr.ge(2)
        )
        score = f.ret6 * f.volume_ratio
    elif family == "ema_reject":
        hit = downtrend & (f.high >= f.ema20) & bearish & f.ret24.lt(0)
        score = -f.ret24
    elif family == "acceleration":
        hit = (
            downtrend
            & (f.close < f.prior_low12)
            & f.volume_ratio.ge(1.5)
            & f.range_atr.ge(1.5)
            & f.close_location.le(0.25)
        )
        score = f.range_atr * f.volume_ratio
    else:
        raise ValueError("unknown_signal_family")
    return (hit & f.ready).fillna(False), score


def generate(frames, specs=None):
    specs = specs or definitions()
    enriched = {coin: features(h) for coin, h in frames.items() if coin != "BTCUSDT"}
    btc = frames["BTCUSDT"]
    btc_bear = btc.ready & btc.close.lt(btc.ema60) & btc.ret24.lt(0)
    output = {}
    for spec in specs:
        rows = []
        for coin, h in enriched.items():
            hit, score = conditions(h, spec["family"])
            if spec["regime"] == "btc_bear":
                hit &= btc_bear.reindex(h.index).fillna(False)
            last = -(10**18)
            for timestamp in h.index[hit]:
                at = int(timestamp.timestamp() * 1000)
                if at - last < spec["cooldown_hours"] * 3600000:
                    continue
                last = at
                rows.append(
                    dict(
                        symbol=coin,
                        at=at,
                        atr=float(h.at[timestamp, "atr"]),
                        probability=float(score.at[timestamp]),
                        event_id=hashlib.sha256(
                            f"regime:{spec['id']}:{coin}:{at}".encode()
                        ).hexdigest()[:24],
                    )
                )
        output[spec["id"]] = sorted(
            rows, key=lambda s: (s["at"], -s["probability"], s["symbol"])
        )
    return output
