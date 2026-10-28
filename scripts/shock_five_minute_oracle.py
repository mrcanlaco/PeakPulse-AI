"""Independent vector first passage on closed-five-minute bars."""
import numpy as np


def expected(source,prices,mode):
    if mode=='immediate':return list(source)
    result=[]
    for e in source:
        q=prices[e['symbol']];origin=e['at'];targets=origin+np.arange(12)*300000-300000
        ix=np.searchsorted(q.trade_times,targets)
        assert np.all(ix<len(q.trade_times)) and np.array_equal(q.trade_times[ix],targets)
        close=q.closes[ix];assert np.isfinite(close).all() and (close>0).all()
        ref=float(close[0]);path=close[1:];signed=(path-ref)*(1 if e['side']=='LONG' else -1)
        if mode in ['pull25','pull50']:hit=signed<=-(.25 if mode=='pull25' else .5)*e['atr']
        elif mode=='break25':hit=signed>=.25*e['atr']
        elif mode=='retest50':
            touched=np.flatnonzero(signed<=-.5*e['atr'])
            if not len(touched):continue
            low=np.minimum.accumulate(np.r_[0.,signed])[1:]
            hit=(np.arange(11)>touched[0])&(signed-low>=.25*e['atr'])&(signed<=0)
        else:raise ValueError('unknown_oracle_mode')
        hits=np.flatnonzero(hit)
        if len(hits):
            k=int(hits[0]);result.append(dict(e,at=origin+(k+1)*300000,source_at=origin,reference_close=ref,trigger_close=float(path[k])))
    return sorted(result,key=lambda e:(e['at'],-e['probability'],e['symbol']))
