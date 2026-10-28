"""First closed-five-minute entry triggers during the hour after a frozen shock."""
from bisect import bisect_left
from collections import Counter
import math

STEP=300000
MODES={'immediate':('immediate',0.),'pull25':('pull',.25),'pull50':('pull',.5),
       'retest50':('retest',.5),'break25':('break',.25)}


def closed_price(q,at):
    i=bisect_left(q.trade_times,at-STEP)
    if i>=len(q.trade_times) or q.trade_times[i]!=at-STEP:return math.nan
    return float(q.closes[i])


def transform(source,prices,mode,*,asof=None):
    if mode not in MODES:raise ValueError('invalid_five_minute_entry_mode')
    family,multiple=MODES[mode];events=[];counts=Counter();records=[]
    for e in source:
        origin=e['at']
        if asof is not None and origin>asof:continue
        if family=='immediate':events.append(dict(e));counts['emitted']+=1;continue
        q=prices[e['symbol']];ref=closed_price(q,origin)
        if not math.isfinite(ref) or ref<=0:raise ValueError('missing_origin_closed_price')
        atr=e['atr']
        if not math.isfinite(atr) or atr<=0:raise ValueError('invalid_origin_atr')
        direction=1 if e['side']=='LONG' else -1
        deadline=int(q.trade_times[-1])+STEP
        if asof is not None:deadline=min(deadline,asof)
        status='expired';trigger=None;price=None;low=0.;armed=None
        # The minute60 close is NOT eligible: the timing hypothesis expires then.
        for k in range(1,12):
            at=origin+k*STEP
            if at>deadline:status='right_censored';break
            price=closed_price(q,at)
            if not math.isfinite(price) or price<=0:status='data_error';break
            signed=direction*(price-ref);low=min(low,signed)
            if armed is None and signed<=-multiple*atr:armed=at
            hit=(family=='pull' and signed<=-multiple*atr) or (family=='break' and signed>=multiple*atr)
            if family=='retest':hit=armed is not None and at>armed and signed>=low+.25*atr and signed<=0
            if hit:
                trigger=at;status='emitted'
                events.append(dict(e,at=at,source_at=origin,reference_close=ref,trigger_close=price));break
        counts[status]+=1
        records.append(dict(event_id=e['event_id'],source_at=origin,symbol=e['symbol'],side=e['side'],status=status,
            triggered_at=trigger,wait_minutes=(trigger-origin)/60000 if trigger is not None else None,
            favorable_atr=-direction*(price-ref)/atr if trigger is not None else None))
    return sorted(events,key=lambda e:(e['at'],-e['probability'],e['symbol'])),dict(counts),records
