"""Direct numpy window oracle, independent of rolling feature implementation."""
import hashlib
import numpy as np


def expected(frames):
    output={f'shock_{mode}_{tag}':[] for tag in ['a15','a25'] for mode in ['follow','fade']}
    observations=0
    for coin,original in frames.items():
        if coin=='BTCUSDT':continue
        h=original.asfreq('1h');values=h[['open','high','low','close','quote_volume']].to_numpy()
        for tag,threshold in [('a15',1.5),('a25',2.5)]:
            last=-(10**18)
            for i in range(71,len(h)):
                recent=values[i-71:i+1]
                if not np.isfinite(recent).all() or not (recent>0).all():continue
                o,hi,lo,c,v=recent.T
                if np.any(hi<np.maximum.reduce([o,c,lo])) or np.any(lo>np.minimum(o,c)):continue
                if sum(v[-24:])<2_000_000:continue
                old=values[i-14:i];prev=values[i-15:i-1,3]
                atr=float(np.mean(np.maximum.reduce([old[:,1]-old[:,2],abs(old[:,1]-prev),abs(old[:,2]-prev)])))
                if atr<=0 or hi[-1]<=lo[-1]:continue
                volume=float(v[-1]/np.mean(values[i-24:i,4]))
                shock=float((c[-1]-o[-1])/atr)
                where=float((c[-1]-lo[-1])/(hi[-1]-lo[-1]))
                observations+=1
                if volume<2 or abs(shock)<threshold:continue
                if not ((shock>0 and where>=.8) or (shock<0 and where<=.2)):continue
                at=int(h.index[i].timestamp()*1000)
                if at-last<6*3600000:continue
                last=at
                for mode in ['follow','fade']:
                    side='LONG' if (shock>0)==(mode=='follow') else 'SHORT';ident=f'shock_{mode}_{tag}'
                    output[ident].append(dict(at=at,symbol=coin,side=side,atr=atr,
                        probability=float(abs(shock)*np.log1p(volume)),
                        event_id=hashlib.sha256(f'hourly_shock:{ident}:{coin}:{at}:{side}'.encode()).hexdigest()[:24]))
    return {key:sorted(es,key=lambda e:(e['at'],-e['probability'],e['symbol'])) for key,es in output.items()},observations
