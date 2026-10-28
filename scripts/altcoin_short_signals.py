"""Causal hourly short hypotheses, built from completed candles only."""

from __future__ import annotations

import hashlib
import itertools
import json
from bisect import bisect_right

import duckdb
import numpy as np
import pandas as pd
from prepare_altcoin_search import OUT, SOURCE


def hourly_features(raw):
    raw = raw.sort_values("open_time").set_index("open_time")
    h = raw.resample("1h", closed="left", label="right").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        quote_volume=("quote_volume", "sum"),
        bars=("close", "count"),
    )
    h.loc[h.bars != 12, ["open", "high", "low", "close", "quote_volume"]] = np.nan
    c = h.close
    h["ema20"] = c.ewm(span=20, adjust=False, min_periods=20).mean()
    h["ema60"] = c.ewm(span=60, adjust=False, min_periods=60).mean()
    tr = pd.concat(
        [h.high - h.low, (h.high - c.shift()).abs(), (h.low - c.shift()).abs()], axis=1
    ).max(axis=1)
    h["atr"] = tr.rolling(14, min_periods=14).mean()
    h["ret24"] = c / c.shift(24) - 1
    h["ret6"] = c / c.shift(6) - 1
    h["prior_close"] = c.shift()
    h["prior_ema20"] = h.ema20.shift()
    h["low24"] = h.low.shift().rolling(24, min_periods=24).min()
    h["low48"] = h.low.shift().rolling(48, min_periods=48).min()
    h["wick"] = (h.high - pd.concat([h.open, c], axis=1).max(axis=1)) / (
        h.high - h.low
    ).replace(0, np.nan)
    h["volume24"] = h.quote_volume.rolling(24, min_periods=24).sum()
    h["ready"] = (
        (h.bars.eq(12).rolling(120, min_periods=120).sum() == 120)
        & h.atr.gt(0)
        & h.volume24.ge(2_000_000)
    )
    return h


def definitions():
    return [
        dict(
            id=f"{family}_{strength}_{btc}_{funding}",
            family=family,
            strength=strength,
            btc=btc,
            funding=funding,
        )
        for family, strength, btc, funding in itertools.product(
            ["breakdown", "pullback", "weak_rank", "failed_pump"],
            ["loose", "strict"],
            ["any", "bear"],
            ["any", "nonnegative"],
        )
    ]


def conditions(h, spec):
    strict = spec["strength"] == "strict"
    trend = (h.ema20 < h.ema60) & (h.close < h.ema20)
    if spec["family"] == "breakdown":
        hit = trend & (h.close < h["low48" if strict else "low24"])
        score = -h.ret24
    elif spec["family"] == "pullback":
        hit = trend & (h.prior_close >= h.prior_ema20) & (h.close < h.open)
        if strict:
            hit &= h.ret24 < -0.03
        score = -h.ret24
    elif spec["family"] == "weak_rank":
        hit = (
            trend
            & (h.weak_rank <= (0.10 if strict else 0.20))
            & (h.ret24 <= (-0.06 if strict else -0.03))
            & (h.index.hour % 6 == 0)
        )
        score = -h.ret24
    else:
        hit = (
            (h.ret24 >= (0.10 if strict else 0.05))
            & (h.close < h.open)
            & (h.close < h.prior_close)
            & (h.wick >= (0.5 if strict else 0.3))
        )
        score = h.ret24
    hit &= h.ready
    if spec["btc"] == "bear":
        hit &= h.btc_bear.fillna(False)
    if spec["funding"] == "nonnegative":
        hit &= h.known_funding.ge(0)
    return hit.fillna(False), score


def generate(frames, funding, specs=None):
    specs = specs or definitions()
    ranks = pd.concat(
        {s: f.ret24.where(f.ready) for s, f in frames.items() if s != "BTCUSDT"}, axis=1
    ).rank(axis=1, pct=True, ascending=True)
    btc = frames["BTCUSDT"]
    btc_bear = btc.ready & (btc.close < btc.ema60) & (btc.ret24 < 0)
    enriched = {}
    for symbol, frame in frames.items():
        if symbol == "BTCUSDT":
            continue
        h = frame.copy()
        h["weak_rank"] = ranks[symbol]
        h["btc_bear"] = btc_bear.reindex(h.index).fillna(False)
        settlements = funding[symbol]
        stamps = [x[0] for x in settlements]
        known = []
        for t in h.index:
            at = int(t.timestamp() * 1000)
            i = bisect_right(stamps, at - 60000) - 1
            known.append(
                settlements[i][1]
                if i >= 0 and at - stamps[i] <= 8 * 3600000 + 300000
                else np.nan
            )
        h["known_funding"] = known
        enriched[symbol] = h
    output = {}
    for spec in specs:
        signals = []
        for symbol, h in enriched.items():
            hit, score = conditions(h, spec)
            last = -(10**18)
            for t in h.index[hit]:
                at = int(t.timestamp() * 1000)
                if at - last < 24 * 3600000:
                    continue
                last = at
                signals.append(
                    dict(
                        symbol=symbol,
                        at=at,
                        atr=float(h.at[t, "atr"]),
                        probability=float(score.at[t]),
                        event_id=hashlib.sha256(
                            f"{spec['id']}:{symbol}:{at}".encode()
                        ).hexdigest()[:24],
                    )
                )
        output[spec["id"]] = sorted(
            signals, key=lambda s: (s["at"], -s["probability"], s["symbol"])
        )
    return output


def load_frames(symbols):
    db = duckdb.connect(str(SOURCE / "working.duckdb"), read_only=True)
    db.execute("SET timezone='UTC'")
    frames, raw_audit = {}, {}
    for symbol in [*symbols, "BTCUSDT"]:
        raw = db.execute(
            "SELECT open_time,open,high,low,close,quote_volume FROM prices WHERE symbol=? ORDER BY open_time",
            [symbol],
        ).df()
        extra = OUT / "cache/trade_prices" / f"{symbol}.json"
        if extra.exists():
            rows = json.loads(extra.read_text(encoding="utf-8"))["rows"]
            add = pd.DataFrame(
                [
                    dict(
                        open_time=pd.Timestamp(int(r[0]), unit="ms", tz="UTC"),
                        open=float(r[1]),
                        high=float(r[2]),
                        low=float(r[3]),
                        close=float(r[4]),
                        quote_volume=float(r[7]),
                    )
                    for r in rows
                ]
            )
            if len(add):
                raw = (
                    pd.concat([raw, add])
                    .drop_duplicates("open_time", keep="first")
                    .sort_values("open_time")
                )
        assert not raw.open_time.duplicated().any()
        frames[symbol] = hourly_features(raw)
        raw_audit[symbol] = dict(
            bars_5m=len(raw),
            hours=len(frames[symbol]),
            ready_hours=int(frames[symbol].ready.sum()),
        )
    db.close()
    return frames, raw_audit
