"""Entry-only funding gates; observed settlements lag decisions by at least60s."""
from bisect import bisect_right
from collections import Counter
import math

GATES=['none','avoid_costly','nonnegative','atr10','atr25']
DAY=86400000
MAX_GAP=8*3600000+300000


def observations(events,funding):
    schedules={c:list(funding[c]) for c in {e['symbol'] for e in events}}
    stamps={c:[r[0] for r in rows] for c,rows in schedules.items()}
    for ts in stamps.values():
        if any(a>=b for a,b in zip(ts,ts[1:])):raise ValueError('ambiguous_funding_history')
    out={}
    for e in events:
        ts=stamps[e['symbol']];rows=schedules[e['symbol']];cut=e['at']-60000
        lo=bisect_right(ts,cut-DAY);hi=bisect_right(ts,cut)
        known=rows[max(0,lo-1):hi]
        complete=lo>0 and hi>lo and cut-ts[hi-1]<=MAX_GAP and all(b[0]-a[0]<=MAX_GAP for a,b in zip(known,known[1:])) and all(math.isfinite(r[1]) for r in known)
        sign=1 if e['side']=='SHORT' else -1
        if e['side'] not in ['LONG','SHORT']:raise ValueError('invalid_side')
        if not all(math.isfinite(e[k]) and e[k]>0 for k in ['atr','reference_close']):raise ValueError('invalid_frozen_atr_or_price')
        last=round(sign*rows[hi-1][1],12) if complete else None
        day=round(sign*sum(r[1] for r in rows[lo:hi]),12) if complete else None
        activation=3*e['atr']/e['reference_close']
        ratio=7*max(0,-day)/activation if complete else None
        out[e['event_id']]=dict(at=e['at'],symbol=e['symbol'],side=e['side'],cutoff=cut,complete=bool(complete),last_settled=ts[hi-1] if hi else None,settlements24=hi-lo,last_receipt=last,day_receipt=day,activation_fraction=activation,projected_cost_to_activation=ratio)
    return out


def decision(o,gate):
    if gate not in GATES:raise ValueError('invalid_carry_gate')
    if gate=='none':return 'accepted'
    if not o['complete']:return 'missing_or_stale_funding'
    if gate=='avoid_costly':allow=o['last_receipt']>=-.0005 and o['day_receipt']>=-.001
    elif gate=='nonnegative':allow=o['last_receipt']>=0 and o['day_receipt']>=0
    else:allow=o['projected_cost_to_activation'] <= (.1 if gate=='atr10' else .25)
    return 'accepted' if allow else 'carry_disagrees'


def filtered(events,obs,gate):
    counts=Counter();out=[]
    for e in events:
        reason=decision(obs[e['event_id']],gate);counts[reason]+=1
        if reason=='accepted':out.append(e)
    return out,dict(counts)
