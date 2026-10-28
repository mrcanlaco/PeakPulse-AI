"""Closed-hour retracement/retest/breakout entries; frozen origin ATR and rank."""
from collections import Counter
import math
import pandas as pd

HOUR=3600000
MODES={'immediate':('immediate',0),'pull05':('pull',.5),'pull1':('pull',1),
       'retest05':('retest',.5),'retest1':('retest',1),'break05':('break',.5),'break1':('break',1)}


def transform(source,frames,mode):
    if mode not in MODES:raise ValueError('invalid_entry_timing_mode')
    family,multiple=MODES[mode];result=[];records=[];counts=Counter()
    for e in source:
        if family=='immediate':result.append(dict(e));counts['emitted']+=1;continue
        f=frames[e['symbol']];origin=e['at'];t=pd.Timestamp(origin,unit='ms',tz='UTC')
        ref=float(f.at[t,'close']) if t in f.index else math.nan
        if not math.isfinite(ref) or ref<=0:raise ValueError('missing_origin_closed_price')
        atr=e['atr'];assert math.isfinite(atr) and atr>0
        direction=1 if e['side']=='LONG' else -1;trough=0.;armed=None;status='expired';trigger=None
        for hours in range(1,24):
            at=origin+hours*HOUR;t=pd.Timestamp(at,unit='ms',tz='UTC')
            if t>f.index[-1]:status='right_censored';break
            price=float(f.at[t,'close']) if t in f.index else math.nan
            if not math.isfinite(price) or price<=0:status='data_error';break
            z=direction*(price-ref);trough=min(trough,z)
            if armed is None and z<=-multiple*atr:armed=at
            hit=(family=='pull' and z<=-multiple*atr) or (family=='break' and z>=multiple*atr)
            if family=='retest':hit=armed is not None and at>armed and z>=trough+.25*atr and z<=0
            if hit:
                trigger=at;status='emitted'
                result.append(dict(e,at=at,source_at=origin,reference_close=ref,trigger_close=price))
                break
        counts[status]+=1
        records.append(dict(event_id=e['event_id'],source_at=origin,symbol=e['symbol'],side=e['side'],status=status,
            triggered_at=trigger,wait_hours=(trigger-origin)/HOUR if trigger else None,
            favorable_atr=-direction*(price-ref)/atr if trigger else None))
    return sorted(result,key=lambda e:(e['at'],-e['probability'],e['symbol'])),dict(counts),records
