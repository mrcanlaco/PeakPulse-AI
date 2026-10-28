"""Daily cross-sectional momentum/reversal from completed hourly and4h bars."""
import hashlib
import itertools
import numpy as np
import pandas as pd
from short_multitimeframe_signals import features as four_hour_features

LOOKBACKS=[24,72,168]


def definitions():
    return [dict(id=f'{mode}_{hours}h_{score}',mode=mode,hours=hours,score=score)
        for mode,hours,score in itertools.product(['momentum','reversion'],LOOKBACKS,['raw','risk_adjusted'])]


def enrich(frames):
    result={}
    for coin,h in frames.items():
        if coin=='BTCUSDT':continue
        f=four_hour_features(h); f=f.loc[f.index.hour==0].copy()
        r=np.log(h.close/h.close.shift(1))
        columns=[]
        for hours in LOOKBACKS:
            raw=np.log(h.close/h.close.shift(hours))
            risk=r.rolling(hours,min_periods=hours).std(ddof=1)*np.sqrt(hours)
            f[f'raw{hours}']=raw.reindex(f.index)
            f[f'risk_adjusted{hours}']=(raw/risk.where(risk>1e-12)).reindex(f.index)
            columns.extend([f'raw{hours}',f'risk_adjusted{hours}'])
        f['eligible']=f.ready & np.isfinite(f[columns]).all(axis=1)
        result[coin]=f
    return result


def rank_state(enriched):
    eligible=pd.concat({coin:f.eligible for coin,f in enriched.items()},axis=1).fillna(False)
    coverage=eligible.sum(axis=1)
    state=pd.DataFrame(dict(coverage=coverage,ready=coverage>=24))
    ranks={}
    for hours,score in itertools.product(LOOKBACKS,['raw','risk_adjusted']):
        values=pd.concat({coin:f[f'{score}{hours}'].where(f.eligible) for coin,f in enriched.items()},axis=1)
        # Symmetric endpoints0/1, average ties; equal scores do not become extrema.
        ranks[f'{score}{hours}']=(values.rank(axis=1,method='average')-1).div((coverage-1).where(coverage>1),axis=0)
    return state,ranks


def generate(enriched,state,ranks,specs=None):
    output={}
    for sp in definitions() if specs is None else specs:
        rows=[]
        for coin,f in enriched.items():
            rank=ranks[f'{sp["score"]}{sp["hours"]}'][coin].reindex(f.index)
            raw=f[f'raw{sp["hours"]}']
            ready=f.eligible & state.ready.reindex(f.index).fillna(False)
            winners=rank.ge(.80)&raw.gt(0);losers=rank.le(.20)&raw.lt(0)
            for side,condition in [('LONG',winners if sp['mode']=='momentum' else losers),
                                   ('SHORT',losers if sp['mode']=='momentum' else winners)]:
                for t in f.index[ready&condition]:
                    at=int(t.timestamp()*1000)
                    rows.append(dict(symbol=coin,side=side,at=at,atr=float(f.at[t,'atr']),probability=float(abs(rank.at[t]-.5)),
                        event_id=hashlib.sha256(f'cross:{sp["id"]}:{coin}:{at}:{side}'.encode()).hexdigest()[:24]))
        output[sp['id']]=sorted(rows,key=lambda r:(r['at'],-r['probability'],r['symbol']))
    return output
