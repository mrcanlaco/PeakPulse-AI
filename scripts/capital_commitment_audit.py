"""Full pending-tranche reserve checks reconstructed from journal plus cancels."""


def audit(raw,prices,fee,budget,leverage=5,rules=None,slip=20):
    active={};wallet=500.;index=0;checks=0;denied=0;cancels=0
    for trace in raw['capital_trace']:
        assert index<=trace['journal_index']<=len(raw['journal'])
        for j in raw['journal'][index:trace['journal_index']]:
            coin=j['symbol']
            if j['kind']=='entry':active[coin]=dict(qty=0.,basis=0.,parts=0,cancel=False,side=j['side'],opened=j['at'])
            if j['kind'] in ['entry','entry_add']:
                p=active[coin];p['qty']+=j['qty'];p['basis']+=j['qty']*j['price'];p['parts']+=1
                wallet-=j['qty']*j['price']*fee
            elif j['kind']=='funding':wallet+=j['amount']
            elif 'net' in j:
                p=active.pop(coin);direction=1 if p['side']=='LONG' else -1
                wallet+=direction*(p['qty']*j['price']-p['basis'])-p['qty']*j['price']*fee
        index=trace['journal_index'];coin=trace['symbol']
        if trace['kind']=='cancel':
            assert coin in active and not active[coin]['cancel']
            assert trace['reason'] in ['drawdown_pause','trail_activation','expiry','exchange_minimum_or_precision','insufficient_margin']
            if trace['reason']=='expiry':assert trace['at']-active[coin]['opened']>6*3600000
            elif trace['reason']=='trail_activation':
                j=raw['journal'][index];assert j['kind']=='trail_activated' and j['symbol']==coin and j['at']==trace['at']
            elif trace['reason']=='drawdown_pause':assert raw['entry_paused']
            elif trace['reason']=='exchange_minimum_or_precision':
                from decimal import Decimal,ROUND_FLOOR
                assert rules is not None;r=rules[coin];reference=prices[coin].get(trace['at'])['entry_open']
                qty=budget/3/(reference*(1+slip/10000))
                for step in [r['market_step'],r['step_size']]:qty=float((Decimal(str(qty))/Decimal(str(step))).to_integral_value(rounding=ROUND_FLOOR)*Decimal(str(step)))
                price=reference*(1+slip/10000 if active[coin]['side']=='LONG' else 1-slip/10000)
                assert not (max(r['min_qty'],r['market_min_qty'])<=qty<=min(r['max_qty'],r['market_max_qty']) and qty*price>=r['min_notional'])
            elif trace['reason']=='insufficient_margin':
                assert prior_check['kind']=='add_check' and prior_check['symbol']==coin and not prior_check['accepted'] and prior_check['at']==trace['at']
            active[coin]['cancel']=True;cancels+=1;continue
        marks={c:prices[c].get(trace['at'])['mark'] for c in active}
        equity=wallet+sum((1 if p['side']=='LONG' else -1)*(p['qty']*marks[c]-p['basis']) for c,p in active.items())
        reserved=0.
        for c,p in active.items():
            pending=0. if p['cancel'] else (3-p['parts'])*budget/3
            if trace['kind']=='add_check' and c==coin:pending=0.
            reserved+=p['qty']*marks[c]/leverage+pending/leverage+2*fee*pending
        if trace['kind']=='add_check':
            p=active[coin];assert not p['cancel'] and p['parts']<3
            future=(3-p['parts']-1)*budget/3
        else:
            assert trace['kind']=='entry_check' and coin not in active
            future=2*budget/3
        required=trace['qty']*trace['price']/leverage+2*trace['qty']*trace['price']*fee+future/leverage+2*fee*future
        available=equity-reserved
        assert abs(trace['available']-available)<1e-6 and abs(trace['required']-required)<1e-7
        if abs(available-required)>1e-6:assert trace['accepted']==(available>=required)
        checks+=1;denied+=not trace['accepted']
        prior_check=trace
    return checks,denied,cancels
