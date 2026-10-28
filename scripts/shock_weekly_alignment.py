"""Entry-only gates for frozen hourly shocks versus the latest closed daily rank."""
from collections import Counter

import numpy as np
import pandas as pd

from cross_sectional_signals import enrich, rank_state


GATES = ['none', 'sign', 'aligned', 'opposed', 'neutral']


def states(frames):
    enriched = enrich(frames)
    daily, ranks = rank_state(enriched)
    state = {}
    for coin, frame in enriched.items():
        item = frame[['eligible', 'raw168']].copy()
        item['coverage'] = daily.coverage.reindex(item.index)
        item['pool_ready'] = daily.ready.reindex(item.index).fillna(False)
        item['percentile'] = ranks['raw168'][coin].reindex(item.index)
        state[coin] = item
    return state


def classify(event, state):
    if event['side'] not in ('LONG', 'SHORT'):
        raise ValueError('invalid_side')
    # The 00:00 UTC snapshot is made from the hourly candle closed at 00:00.
    # A later hourly signal may use it; no next-day rank is consulted.
    t = pd.Timestamp(event['at'], unit='ms', tz='UTC').floor('D')
    frame = state.get(event['symbol'])
    row = frame.loc[t] if frame is not None and t in frame.index else None
    if row is None or not bool(row.pool_ready) or not np.isfinite(row.raw168):
        return dict(reason='missing_state', snapshot_at=int(t.timestamp()*1000))
    if not bool(row.eligible):
        return dict(reason='ineligible', snapshot_at=int(t.timestamp()*1000),
                    raw168=float(row.raw168), coverage=int(row.coverage))
    if not np.isfinite(row.percentile):
        return dict(reason='missing_state', snapshot_at=int(t.timestamp()*1000))
    raw = float(row.raw168)
    rank = float(row.percentile)
    weekly_side = 'LONG' if rank >= .8 and raw > 0 else 'SHORT' if rank <= .2 and raw < 0 else None
    sign_matches = raw > 0 if event['side'] == 'LONG' else raw < 0
    return dict(reason='ready', snapshot_at=int(t.timestamp()*1000),
                raw168=raw, percentile=rank, coverage=int(row.coverage),
                weekly_side=weekly_side, sign_matches=bool(sign_matches))


def filtered(events, state, gate):
    if gate not in GATES:
        raise ValueError('invalid_gate')
    accepted = []
    counts = Counter()
    decisions = []
    for event in events:
        d = classify(event, state)
        if gate == 'none':
            reason = 'accepted'
        elif d['reason'] != 'ready':
            reason = d['reason']
        else:
            side = d['weekly_side']
            passed = (d['sign_matches'] if gate == 'sign' else
                      side == event['side'] if gate == 'aligned' else
                      side is not None and side != event['side'] if gate == 'opposed' else
                      side is None)
            reason = 'accepted' if passed else 'other_partition'
        counts[reason] += 1
        decisions.append({**d, 'event_id': event['event_id'], 'at': event['at'],
                          'symbol': event['symbol'], 'side': event['side'],
                          'gate': gate, 'reason': reason})
        if reason == 'accepted':
            accepted.append(event)
    return accepted, dict(counts), decisions
