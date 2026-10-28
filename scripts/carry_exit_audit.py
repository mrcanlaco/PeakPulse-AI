"""Independent first accrued-carry or trailing trigger from settled cash flows."""
import numpy as np

def audit_exits(raw,curve,prices,policy,event_map,fee,slip):
    """Reconstruct first trailing/age trigger from actual fills and paid funding."""
    active={};groups={}
    for j in raw['journal']:
        if j['kind']=='entry':active[j['symbol']]=j['event_id'];groups[j['event_id']]=[]
        groups[active[j['symbol']]].append(j)
        if 'net' in j:del active[j['symbol']]
    checked=states=time_exits=0
    for key,js in groups.items():
        first=js[0];q=prices[first['symbol']];fills=[j for j in js if j['kind'] in ['entry','entry_add']]
        funding=[j for j in js if j['kind']=='funding'];acts=[j for j in js if j['kind']=='trail_activated'];exits=[j for j in js if 'net' in j]
        observed_end=exits[0]['at'] if exits else int(curve['at'].iloc[-1])
        deadline=first['at']+int(policy['max_hold_hours']*3600000) if policy.get('max_hold_hours') else float('inf')
        deadline_reason='time_exit'
        if policy.get('carry_exit_fraction') is not None:
            stamps=np.arange(first['at']+300000,observed_end+1,300000,dtype=np.int64)
            idx=np.searchsorted([j['at'] for j in funding],stamps-60000,side='right')
            known=np.r_[0,np.cumsum([j['amount'] for j in funding])][idx]
            cap=policy['position_notional']*policy['carry_exit_fraction']
            hit=np.flatnonzero(known<=-cap+1e-12)
            if len(hit) and int(stamps[hit[0]])<deadline:
                deadline=int(stamps[hit[0]]);deadline_reason='carry_exit'
                if exits and exits[0]['at']==deadline and exits[0]['kind']=='carry_exit':
                    assert abs(exits[0]['known_funding']-known[hit[0]])<1e-9
                    assert exits[0]['funding_limit']==cap and exits[0]['observation_cutoff']==deadline-60000
        # Scheduled close takes priority; there is no trailing observation then.
        limit=min(observed_end,deadline-300000)
        at=np.arange(first['at']+300000,limit+1,300000,dtype=np.int64)
        mode=policy.get('net_exit_mode','price');assert mode in ['price','net_peak']
        trailing_at=None
        if len(at):
            ix=np.searchsorted(q.trade_times,at-300000);assert np.all(q.trade_times[ix]==at-300000);close=q.closes[ix]
            fi=np.searchsorted([j['at'] for j in fills],at,side='left')-1
            qty=np.cumsum([j['qty'] for j in fills])[fi];basis=np.cumsum([j['qty']*j['price'] for j in fills])[fi]
            fees=np.cumsum([j['qty']*j['price']*fee for j in fills])[fi]
            fidx=np.searchsorted([j['at'] for j in funding],at,side='right');carry=np.r_[0,np.cumsum([j['amount'] for j in funding])][fidx]
            direction=1 if first['side']=='LONG' else -1;indicative=close*(1-direction*slip/10000)
            net=direction*(qty*indicative-basis)-fees+carry-qty*indicative*fee
            if mode=='net_peak':
                peak=np.maximum.accumulate(net);activation=net>=policy['activation_net_usdt'];retraced=net<=peak*(1-policy['net_callback_fraction'])
            else:
                threshold=first['price']+direction*policy['activation_atr']*event_map[key]['atr']
                if direction==1:
                    activation=close>=threshold;peak=np.maximum.accumulate(np.r_[first['price'],close])[1:];retraced=close<=peak*(1-policy['callback_fraction'])
                else:
                    activation=close<=threshold;peak=np.minimum.accumulate(np.r_[first['price'],close])[1:];retraced=close>=peak*(1+policy['callback_fraction'])
            ai=np.flatnonzero(activation);assert len(acts)==int(bool(len(ai)))
            if len(ai):
                k=int(ai[0]);assert acts[0]['at']==at[k]
                assert not any(j['kind']=='entry_add' and j['at']>=at[k] for j in js)
                condition=(np.arange(len(at))>=k)&retraced
                if mode=='net_peak':
                    assert abs(acts[0]['observed_net']-net[k])<1e-7
                    condition &= net>=0
                hit=np.flatnonzero(condition)
                if len(hit):
                    z=int(hit[0]);trailing_at=int(at[z])
                    if exits and exits[0]['at']==trailing_at and mode=='net_peak':
                        assert abs(exits[0]['observed_net']-net[z])<1e-7
                        assert abs(exits[0]['net_peak']-peak[z])<1e-7
            states+=len(at)
        else:assert not acts
        reason='trailing_exit' if trailing_at is not None else deadline_reason if deadline<=observed_end else None
        trigger=trailing_at if trailing_at is not None else deadline if reason else None
        if trigger is None:assert not exits
        elif np.isfinite(q.get(int(trigger))['entry_open']):
            assert len(exits)==1 and exits[0]['at']==trigger and exits[0]['kind']==reason
            time_exits+=reason=='carry_exit'
        else:
            assert trigger==curve['at'].iloc[-1] and not exits
            assert next(p for p in raw['open_positions'] if p['event_id']==key)['pending_exit']==reason
        checked+=1
    return checked,states,time_exits
