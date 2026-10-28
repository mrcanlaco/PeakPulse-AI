"""Direct window OLS/residual sample calculations and explicit peer ranking."""
import hashlib
import numpy as np
import pandas as pd


def feature_oracle(frames):
    btc = frames['BTCUSDT'].asfreq('1h')
    output = {}
    for coin, original in frames.items():
        if coin == 'BTCUSDT':continue
        h = original.asfreq('1h')
        # Independent grouping of fully closed four-hour bars.
        bars = h.groupby(h.index.ceil('4h')).agg(high=('high','max'), low=('low','min'),
            close=('close','last'), volume=('quote_volume','sum'), count=('close','count'))
        bars.loc[bars['count'] != 4, ['high','low','close','volume']] = np.nan
        tr = np.nanmax(np.column_stack([(bars.high-bars.low).to_numpy(),
            (bars.high-bars.close.shift()).abs().to_numpy(),
            (bars.low-bars.close.shift()).abs().to_numpy()]), axis=1)
        rows = []
        for t in bars.index[bars.index.hour == 0]:
            row = dict(at=t, eligible=False, beta=np.nan, atr=np.nan)
            for n in [24,72,168]:row[f'raw{n}']=row[f'risk_adjusted{n}']=np.nan
            j = bars.index.get_loc(t)
            if j >= 13:row['atr'] = float(np.mean(tr[j-13:j+1]))
            ix = pd.date_range(t-pd.Timedelta(hours=720), t, freq='1h')
            a = h.close.reindex(ix).to_numpy();b = btc.close.reindex(ix).to_numpy()
            if not (np.isfinite(a).all() and np.isfinite(b).all() and (a>0).all() and (b>0).all()):
                rows.append(row);continue
            ar = np.log(a[1:]/a[:-1]);br = np.log(b[1:]/b[:-1])
            centered_b = br-br.mean()
            if np.dot(centered_b,centered_b)/719 <= 1e-12:
                rows.append(row);continue
            beta = float(np.dot(ar-ar.mean(),centered_b)/np.dot(centered_b,centered_b));row['beta']=beta
            for n in [24,72,168]:
                raw = float(np.log(a[-1]/a[-1-n])-beta*np.log(b[-1]/b[-1-n]))
                riskvar = float(np.var(ar[-n:]-beta*br[-n:],ddof=1))
                row[f'raw{n}']=raw
                row[f'risk_adjusted{n}']=raw/np.sqrt(n*riskvar) if riskvar>1e-12 else np.nan
            ready = j>=71 and (bars['count'].iloc[j-71:j+1]==4).all() and row['atr']>0 and bars.volume.iloc[j-5:j+1].sum()>=2_000_000
            row['eligible']=bool(ready and all(np.isfinite(row[k]) for k in row if k not in ['at','eligible']))
            rows.append(row)
        output[coin]=pd.DataFrame(rows).set_index('at')
    return output


def event_oracle(features):
    output={f'residual_{n}h_{score}':[] for n in [24,72,168] for score in ['raw','risk_adjusted']}
    dates=sorted(set().union(*(set(f.index) for f in features.values())))
    for t in dates:
        pool={coin:f.loc[t] for coin,f in features.items() if t in f.index and f.loc[t,'eligible']}
        if len(pool)<24:continue
        for ident,events in output.items():
            n=int(ident.split('_')[1][:-1]);score=ident.split('_',2)[2];key=f'{score}{n}'
            values=[r[key] for r in pool.values()]
            for coin,r in pool.items():
                value=r[key]
                rank=(sum(v<value for v in values)+(sum(v==value for v in values)-1)/2)/(len(pool)-1)
                side='LONG' if rank>=.8 and r[f'raw{n}']>0 else 'SHORT' if rank<=.2 and r[f'raw{n}']<0 else None
                if side is None:continue
                at=int(t.timestamp()*1000)
                events.append(dict(symbol=coin,side=side,at=at,atr=float(r.atr),probability=float(abs(rank-.5)),
                    event_id=hashlib.sha256(f'residual:{ident}:{coin}:{at}:{side}'.encode()).hexdigest()[:24]))
    return {key:sorted(es,key=lambda e:(e['at'],-e['probability'],e['symbol'])) for key,es in output.items()}
