"""Reconstruct halted wallets at the maintenance-proxy breach, not liquidation fills."""
from collections import Counter
from compare_account_risk import write
from frozen_extension_inputs import load
from search_cross_regime import OUT,read,COSTS


def reconstruct(raw,fee,prices):
    wallet=500.;active={}
    for j in raw['journal']:
        coin=j['symbol']
        if j['kind'] in ['entry','entry_add']:
            if j['kind']=='entry':active[coin]=dict(qty=0.,basis=0.,direction=1 if j['side']=='LONG' else -1)
            pos=active[coin];pos['qty']+=j['qty'];pos['basis']+=j['qty']*j['price'];wallet-=j['qty']*j['price']*fee
        elif j['kind']=='funding':wallet+=j['amount']
        elif 'net' in j:
            pos=active.pop(coin);wallet+=pos['direction']*(pos['qty']*j['price']-pos['basis'])-pos['qty']*j['price']*fee
    stop=raw['stop_event'];assert stop and raw['ending_equity'] is None
    assert set(active)==set(stop['marks'])
    pnl={};required=0.
    for coin,pos in active.items():
        mark=prices[coin].get(stop['at'])['mark'];assert abs(mark-stop['marks'][coin])<1e-9
        pnl[coin]=pos['direction']*(pos['qty']*mark-pos['basis']);required+=pos['qty']*mark*.01
    equity=wallet+sum(pnl.values())
    assert abs(equity-stop['equity'])<1e-6 and abs(required-stop['maintenance_proxy'])<1e-8
    assert equity<=required and min(pnl,key=pnl.get)=='SOONUSDT'
    return dict(at=stop['at'],wallet_before_halt=wallet,marked_equity=equity,maintenance_proxy=required,
        position_marked_pnl=pnl,meaning='Sampled cross-equity breach under1%proxy;no liquidation fill/real ending balance inferred.')


def main():
    s=read(OUT/'summary.json');prices,_,_=load();rows=[]
    for r in s['results']:
        if r['ending_equity'] is not None:continue
        raw=read(OUT/'runs'/f'{r["id"]}.json');assert all(e.startswith('maintenance_proxy_breached:') for e in raw['errors'])
        _,fee,_=next(c for c in COSTS if c[0]==r['cost'])
        rows.append(dict(id=r['id'],**reconstruct(raw,fee,prices)))
    assert len(rows)==s['incomplete_paths']
    write(OUT/'failure_verification.json',dict(checked_paths=len(rows),distinct_breach_timestamps=dict(Counter(r['at'] for r in rows)),
        rows=rows,not_independent_events=True,exact_historical_liquidation_unknown=True))
    print('FAILURES VERIFIED',len(rows),flush=True)


if __name__=='__main__':main()
