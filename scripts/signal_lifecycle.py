"""Daily closed-data momentum invalidation, separate from entry selection."""
import math
import numpy as np

DAY=86400000
MODES={'sign24':(24,1),'sign72':(72,1),'sign168':(168,1),'sign168x2':(168,2)}


def calendar(frames):
    out={}
    for coin,h in frames.items():
        if coin=='BTCUSDT':continue
        close=h.close.where(np.isfinite(h.close)&h.close.gt(0))
        for hours in [24,72,168]:
            ret=np.log(close/close.shift(hours)).where(close.rolling(hours+1,min_periods=hours+1).count().eq(hours+1))
            for t,value in ret.loc[ret.index.hour==0].items():
                at=int(t.value//1000000)
                out.setdefault(at,{}).setdefault(coin,{})[hours]=float(value) if np.isfinite(value) else None
    return out


def invalidated(states,at,coin,side,opened,mode):
    if mode not in MODES:raise ValueError('invalid_signal_exit_mode')
    if at%DAY or at<=opened:return False
    hours,count=MODES[mode]
    values=[]
    for lag in range(count):
        t=at-lag*DAY
        if t<=opened:return False
        v=states.get(t,{}).get(coin,{}).get(hours)
        if v is None or not math.isfinite(v):raise ValueError(f'missing_signal_exit_data:{coin}:{t}:{hours}')
        values.append(v)
    direction=1 if side=='LONG' else -1
    return all(direction*v<=0 for v in values)
