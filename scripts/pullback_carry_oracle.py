"""Direct past-only funding window oracle, without cumulative sums or bisect."""
import math


def expected(events,funding):
    out={g:[] for g in ['none','avoid_costly','nonnegative','atr10','atr25']};observed={}
    for e in events:
        cutoff=e['at']-60000;left=cutoff-86400000
        past=[r for r in funding[e['symbol']] if r[0]<=cutoff]
        before=[r for r in past if r[0]<=left];window=[r for r in past if r[0]>left]
        checked=([before[-1]] if before else [])+window
        complete=bool(before and window and cutoff-window[-1][0]<=29100000 and all(checked[i+1][0]-checked[i][0]<=29100000 for i in range(len(checked)-1)) and all(math.isfinite(r[1]) for r in checked))
        sign=-1 if e['side']=='LONG' else 1
        last=round(sign*window[-1][1],12) if complete else None
        day=round(sign*math.fsum(r[1] for r in window),12) if complete else None
        ratio=7*max(0,-day)/(3*e['atr']/e['reference_close']) if complete else None
        observed[e['event_id']]=dict(complete=complete,last_receipt=last,day_receipt=day,projected_cost_to_activation=ratio)
        out['none'].append(e)
        if not complete:continue
        if last>=-.0005 and day>=-.001:out['avoid_costly'].append(e)
        if last>=0 and day>=0:out['nonnegative'].append(e)
        for limit,gate in [(.1,'atr10'),(.25,'atr25')]:
            if ratio<=limit:out[gate].append(e)
    return out,observed
