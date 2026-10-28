"""Vector first-passage oracle for delayed momentum candidates."""
import numpy as np
import pandas as pd


def expected(source,frames,mode):
    if mode=='immediate':return list(source)
    threshold=.5 if mode.endswith('05') else 1.
    result=[]
    for e in source:
        h=frames[e['symbol']];t=pd.Timestamp(e['at'],unit='ms',tz='UTC');i=h.index.get_loc(t)
        reference=float(h.close.iloc[i]);window=h.close.iloc[i+1:i+24]
        assert len(window)==23 and np.isfinite(window).all() and (window>0).all()
        assert np.all(window.index.as_unit('ms').asi8==e['at']+np.arange(1,24)*3600000)
        signed=(window.to_numpy()-reference)*(1 if e['side']=='LONG' else -1)
        if mode.startswith('pull'):eligible=signed<=-threshold*e['atr']
        elif mode.startswith('break'):eligible=signed>=threshold*e['atr']
        else:
            touched=np.flatnonzero(signed<=-threshold*e['atr'])
            if not len(touched):continue
            low=np.minimum.accumulate(np.r_[0.,signed])[1:]
            eligible=(np.arange(23)>touched[0])&(signed-low>=.25*e['atr'])&(signed<=0)
        hits=np.flatnonzero(eligible)
        if not len(hits):continue
        k=int(hits[0]);result.append(dict(e,at=e['at']+(k+1)*3600000,source_at=e['at'],reference_close=reference,trigger_close=float(window.iloc[k])))
    return sorted(result,key=lambda e:(e['at'],-e['probability'],e['symbol']))
