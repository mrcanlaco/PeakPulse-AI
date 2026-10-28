"""Entry-only partitions by closed signal price versus strictly previous ranges."""
from collections import Counter
import numpy as np
import pandas as pd

GATES=['none','break24','nonbreak24','break72','nonbreak72']


def states(frames):
    out={}
    for coin,frame in frames.items():
        if coin=='BTCUSDT':continue
        h=frame.asfreq('1h');cols=['high','low','close']
        valid=np.isfinite(h[cols]).all(axis=1)&h[cols].gt(0).all(axis=1)&h.high.ge(h.close)&h.low.le(h.close)
        f=pd.DataFrame(dict(close=h.close),index=h.index)
        for n in [24,72]:
            f[f'high{n}']=h.high.shift().rolling(n,min_periods=n).max()
            f[f'low{n}']=h.low.shift().rolling(n,min_periods=n).min()
            f[f'ready{n}']=valid.shift().rolling(n,min_periods=n).sum().eq(n)&np.isfinite(h.close)&h.close.gt(0)
        out[coin]=f
    return out


def filtered(events,state,gate):
    if gate not in GATES:raise ValueError('invalid_range_gate')
    out=[];counts=Counter();records=[]
    for e in events:
        if e['side'] not in ['LONG','SHORT']:raise ValueError('invalid_range_side')
        record=dict(event_id=e['event_id'],at=e['at'],side=e['side'])
        if gate=='none':reason='accepted'
        else:
            n=24 if gate.endswith('24') else 72;t=pd.Timestamp(e['at'],unit='ms',tz='UTC')
            f=state.get(e['symbol']);r=f.loc[t] if f is not None and t in f.index else None
            if r is None or not r[f'ready{n}'] or not np.isfinite([r.close,r[f'high{n}'],r[f'low{n}']]).all():reason='missing_state'
            else:
                long=e['side']=='LONG';boundary=float(r[f'high{n}' if long else f'low{n}']);value=float(r.close)
                breakout=value>boundary if long else value<boundary
                wanted=breakout if gate.startswith('break') else not breakout
                reason='accepted' if wanted else 'other_partition'
                record.update(boundary=boundary,closed_price=value,breakout=bool(breakout),
                    signed_distance_atr=(1 if long else -1)*(value-boundary)/e['atr'])
        counts[reason]+=1;record['reason']=reason;records.append(record)
        if reason=='accepted':out.append(e)
    return out,dict(counts),records
