"""Reconstruct the halted shared wallet without inventing liquidation fills."""

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
    assert equity<=required
    return dict(at=stop['at'],wallet_before_halt=wallet,marked_equity=equity,maintenance_proxy=required,
        position_marked_pnl=pnl,meaning='Sampled cross-equity breach under1%proxy;no liquidation fill/real ending balance inferred.')
