"""Freeze ATR-dollar sizing at the original signal, before the entry wait."""
import math


def size_signals(signals, mode, amount, lower=25., upper=250.):
    if mode not in ('fixed', 'atr_dollar'):
        raise ValueError('invalid_sizing_mode')
    if not math.isfinite(amount) or amount <= 0 or not 0 < lower <= upper:
        raise ValueError('invalid_sizing_parameters')
    out=[]
    for event in signals:
        if mode == 'fixed':
            budget=amount
        else:
            price=event['reference_close'];atr=event['atr']
            if not all(math.isfinite(x) and x > 0 for x in (price,atr)):
                raise ValueError('invalid_origin_volatility')
            budget=min(upper,max(lower,amount/(atr/price)))
        out.append(dict(event,planned_notional=budget))
    return out


def financial_view(raw):
    """Remove only observational metadata for fixed-size regression checks."""
    import copy
    result=copy.deepcopy(raw)
    for p in result['open_positions']:p.pop('planned_notional',None)
    for t in result['capital_trace']:
        t.pop('planned_notional',None);t.pop('event_id',None)
    return result
