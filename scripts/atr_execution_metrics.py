"""Gross stop-distance overshoot; not a claim of exchange-stop execution."""
import numpy as np


def stop_metrics(raw,policy,events,prices):
    active={};rows=[]
    for j in raw['journal']:
        c=j['symbol']
        if j['kind']=='entry':active[c]=dict(qty=j['qty'],basis=j['qty']*j['price'],direction=1 if j['side']=='LONG' else -1,event=j['event_id'])
        elif j['kind']=='entry_add':active[c]['qty']+=j['qty'];active[c]['basis']+=j['qty']*j['price']
        elif 'net' in j:
            p=active.pop(c)
            if j['kind']!='atr_stop':continue
            expected=p['qty']*policy['stop_atr']*events[p['event']]['atr']
            gross_loss=p['direction']*(p['basis']-p['qty']*j['price'])
            mark=prices[c].get(j['at'])['mark']
            sampled_loss=p['direction']*(p['basis']-p['qty']*mark)
            assert expected>0 and sampled_loss>=expected-1e-7
            rows.append(dict(event_id=p['event'],symbol=c,at=j['at'],expected_gross_distance_usdt=expected,
                sampled_mark_gross_loss=sampled_loss,actual_gross_loss=gross_loss,actual_net=j['net'],gross_ratio=gross_loss/expected))
    ratios=[r['gross_ratio'] for r in rows]
    return dict(count=len(rows),over_distance=sum(x>1+1e-9 for x in ratios),
        median_gross_ratio=float(np.median(ratios)) if ratios else None,max_gross_ratio=max(ratios) if ratios else None,
        max_net_loss=max((-r['actual_net'] for r in rows),default=None),
        worst_ratio_event=max(rows,key=lambda r:r['gross_ratio']) if rows else None,
        meaning='Gross realized loss / qty*k*entryATR. Excludes fees/funding in ratio; netloss includes them. Sampled Mark then adverse tradeopen; not exchange stop order simulation.')
