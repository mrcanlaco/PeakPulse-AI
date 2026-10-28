"""Entry-only dollar exposure guard; no assertion of beta neutrality."""
import math


def permitted(long, short, side, budget, limit):
    if side not in ('LONG', 'SHORT'):
        raise ValueError('invalid_exposure_side')
    if not all(math.isfinite(x) for x in (long, short, budget, limit)) or min(long, short)<0 or min(budget, limit)<=0:
        raise ValueError('invalid_exposure_inputs')
    before=long-short
    after=before+(budget if side=='LONG' else -budget)
    return abs(after)<=limit+1e-10 or abs(after)<abs(before)-1e-10


def audit(raw, prices, budget, limit, rules=None):
    """Rebuild held quantity and unfilled commitments from financial journal."""
    active={};index=0;passed=set();rejected=0
    checks=raw.get('exposure_checks',[])
    for check in checks:
        assert index<=check['journal_index']<=len(raw['journal'])
        for j in raw['journal'][index:check['journal_index']]:
            coin=j['symbol']
            if j['kind']=='entry':
                assert j['event_id'] in passed
                active[coin]=dict(side=j['side'],qty=j['qty'],parts=1,cancel=False)
            elif j['kind']=='entry_add':
                active[coin]['qty']+=j['qty'];active[coin]['parts']+=1
            elif j['kind'] in ('trail_activated','adds_expired'):
                active[coin]['cancel']=True
            elif j['kind']=='adds_cancelled':
                assert j['reason']=='add_exchange_minimum_or_precision'
                assert rules is not None
                r=rules[coin]
                assert not (max(r['min_qty'],r['market_min_qty'])<=j['qty']<=min(r['max_qty'],r['market_max_qty']) and j['qty']*j['price']>=r['min_notional'])
                active[coin]['cancel']=True
            elif 'net' in j:del active[coin]
        index=check['journal_index']
        amounts={'LONG':0.,'SHORT':0.}
        for c,p in active.items():
            reserved=0. if p['cancel'] else (3-p['parts'])*budget/3
            amounts[p['side']]+=p['qty']*prices[c].get(check['at'])['mark']+reserved
        for side in amounts:assert abs(check[side]-amounts[side])<1e-7
        before=amounts['LONG']-amounts['SHORT']
        after=before+(1 if check['side']=='LONG' else -1)*budget
        expected=(abs(after)<=limit+1e-10) or (abs(before)-abs(after)>1e-10)
        assert check['allowed']==expected
        if expected:passed.add(check['event_id'])
        else:rejected+=1
    assert all(j['event_id'] in passed for j in raw['journal'] if j['kind']=='entry')
    assert raw['rejections'].get('exposure_imbalance',0)==rejected
    return len(checks),rejected
