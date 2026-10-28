"""Filter already-frozen signals using settled funding, lagged at least60s."""
from collections import Counter
import math
import pandas as pd
from short_funding_flow_signals import known_funding

FILTERS=['none','avoid_costly','nonnegative']


def observations(events,funding):
    result={}
    for coin in sorted({e['symbol'] for e in events}):
        xs=[e for e in events if e['symbol']==coin]
        idx=pd.to_datetime(sorted({e['at'] for e in xs}),unit='ms',utc=True)
        f=known_funding(idx,funding[coin])
        for e in xs:
            at=pd.Timestamp(e['at'],unit='ms',tz='UTC'); row=f.loc[at]
            sign=1 if e['side']=='SHORT' else -1
            last=float(row.last_funding); day=float(row.funding24)
            result[e['event_id']]=dict(symbol=coin,side=e['side'],at=e['at'],
                last_receipt_rate=round(sign*last,12) if math.isfinite(last) else None,
                day_receipt_rate=round(sign*day,12) if math.isfinite(day) else None)
    return result


def decision(o,key):
    if key=='none':return 'accepted'
    if key not in FILTERS:raise ValueError('unknown_carry_filter')
    last,day=o['last_receipt_rate'],o['day_receipt_rate']
    if last is None or day is None:return 'missing_or_stale_funding'
    if key=='avoid_costly':return 'accepted' if last>=-.0005 and day>=-.001 else 'costly_known_carry'
    return 'accepted' if last>=0 and day>=0 else 'negative_known_carry'


def filtered(events,obs,key):
    counts=Counter(decision(obs[e['event_id']],key) for e in events)
    return [e for e in events if decision(obs[e['event_id']],key)=='accepted'],dict(counts)
