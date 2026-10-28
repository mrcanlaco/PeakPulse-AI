"""Direct timestamp-window high/low oracle, independent of rolling gates."""
import numpy as np
import pandas as pd


def expected(events,frames):
    output={k:[] for k in ['none','break24','nonbreak24','break72','nonbreak72']}
    for e in events:
        output['none'].append(e)
        t=pd.Timestamp(e['at'],unit='ms',tz='UTC');h=frames[e['symbol']]
        for n in [24,72]:
            stamps=pd.date_range(t-pd.Timedelta(hours=n),t-pd.Timedelta(hours=1),freq='1h')
            prior=h.reindex(stamps)[['high','low','close']].to_numpy()
            if not np.isfinite(prior).all() or not (prior>0).all():continue
            if not (prior[:,0]>=prior[:,2]).all() or not (prior[:,1]<=prior[:,2]).all():continue
            close=float(h.loc[t,'close']) if t in h.index else np.nan
            if not np.isfinite(close) or close<=0:continue
            hit=close>max(prior[:,0]) if e['side']=='LONG' else close<min(prior[:,1])
            output[f'{"break" if hit else "nonbreak"}{n}'].append(e)
    return output
