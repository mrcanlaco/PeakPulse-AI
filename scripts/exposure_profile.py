"""Observed marked exposure diagnostics for frozen replay outputs."""

def profile(raw,curve,prices,limit):
    """Time-weighted actual marked exposures; pending commitments excluded."""
    import numpy as np
    at=curve['at'].to_numpy();long=np.zeros(len(at));short=np.zeros(len(at));active={}
    def segment(coin,p,end):
        lo,hi=np.searchsorted(at,[p['since'],end])
        if hi<=lo:return
        q=prices[coin];ix=np.searchsorted(q.mark_times,at[lo:hi]-300000)
        assert np.all(q.mark_times[ix]==at[lo:hi]-300000)
        (long if p['side']=='LONG' else short)[lo:hi]+=p['qty']*q.marks[ix]
    for j in raw['journal']:
        c=j['symbol']
        if j['kind']=='entry':active[c]=dict(qty=j['qty'],side=j['side'],since=j['at'])
        elif j['kind']=='entry_add':
            segment(c,active[c],j['at']);active[c]['qty']+=j['qty'];active[c]['since']=j['at']
        elif 'net' in j:segment(c,active.pop(c),j['at'])
    for c,p in active.items():segment(c,p,int(at[-1])+1)
    w=np.diff(at,append=at[-1]);duration=w.sum();net=long-short
    avg=lambda x:float(np.dot(x,w)/duration) if duration else None
    return dict(mean_long=avg(long),mean_short=avg(short),mean_gross=avg(long+short),
        mean_abs_net=avg(np.abs(net)),peak_abs_net=float(np.abs(net).max()),
        fraction_above_entry_bound=avg(np.abs(net)>limit) if limit else None,
        meaning='Actual marked dollars; excludes pending commitments. Entry bound not continuously enforced. Not beta neutral.')
