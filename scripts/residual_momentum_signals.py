"""Daily momentum net of contemporaneously estimated BTC beta; research only."""
import hashlib
import itertools
import numpy as np
import pandas as pd
from short_multitimeframe_signals import features
from cross_sectional_signals import rank_state

LOOKBACKS = [24, 72, 168]
BETA_HOURS = 720


def definitions():
    return [dict(id=f'residual_{hours}h_{score}', hours=hours, score=score)
            for hours, score in itertools.product(LOOKBACKS, ['raw', 'risk_adjusted'])]


def enrich(frames):
    btc = frames['BTCUSDT'].asfreq('1h').close
    btc = btc.where(np.isfinite(btc) & btc.gt(0))
    br = np.log(btc / btc.shift())
    result = {}
    for coin, frame in frames.items():
        if coin == 'BTCUSDT':
            continue
        h = frame.asfreq('1h').copy()
        close = h.close.where(np.isfinite(h.close) & h.close.gt(0))
        ar = np.log(close / close.shift())
        b = br.reindex(h.index)
        variance = b.rolling(BETA_HOURS, min_periods=BETA_HOURS).var(ddof=1)
        beta = ar.rolling(BETA_HOURS, min_periods=BETA_HOURS).cov(b) / variance.where(variance > 1e-12)
        f = features(h)
        f = f.loc[f.index.hour == 0].copy()
        f['beta'] = beta.reindex(f.index)
        columns = ['beta']
        for hours in LOOKBACKS:
            raw = np.log(close / close.shift(hours)) - beta * np.log(btc / btc.shift(hours)).reindex(h.index)
            # Use the SAME current beta for every return in this risk sample.
            va = ar.rolling(hours, min_periods=hours).var(ddof=1)
            vb = b.rolling(hours, min_periods=hours).var(ddof=1)
            cov = ar.rolling(hours, min_periods=hours).cov(b)
            residual_variance = va + beta**2 * vb - 2 * beta * cov
            risk = np.sqrt(residual_variance.where(residual_variance > 1e-12) * hours)
            f[f'raw{hours}'] = raw.reindex(f.index)
            f[f'risk_adjusted{hours}'] = (raw / risk).reindex(f.index)
            columns.extend([f'raw{hours}', f'risk_adjusted{hours}'])
        f['eligible'] = f.ready & np.isfinite(f[columns]).all(axis=1)
        result[coin] = f
    return result


def generate(enriched, state=None, ranks=None):
    if state is None:
        state, ranks = rank_state(enriched)
    output = {}
    for sp in definitions():
        events = []
        for coin, f in enriched.items():
            rank = ranks[f'{sp["score"]}{sp["hours"]}'][coin].reindex(f.index)
            residual = f[f'raw{sp["hours"]}']
            ready = f.eligible & state.ready.reindex(f.index).fillna(False)
            for side, condition in [('LONG', rank.ge(.8) & residual.gt(0)),
                                    ('SHORT', rank.le(.2) & residual.lt(0))]:
                for t in f.index[ready & condition]:
                    at = int(t.timestamp() * 1000)
                    events.append(dict(symbol=coin, side=side, at=at, atr=float(f.at[t, 'atr']),
                        probability=float(abs(rank.at[t] - .5)),
                        event_id=hashlib.sha256(f'residual:{sp["id"]}:{coin}:{at}:{side}'.encode()).hexdigest()[:24]))
        output[sp['id']] = sorted(events, key=lambda e: (e['at'], -e['probability'], e['symbol']))
    return output
