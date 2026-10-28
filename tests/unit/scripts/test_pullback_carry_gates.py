import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from pullback_carry_gates import observations,filtered,decision,GATES
from pullback_carry_oracle import expected
H=3600000


def event(at,side='LONG'):
    return dict(at=at,side=side,symbol='X',event_id=str(at)+side,atr=2,reference_close=100)


def test_only_funding_at_least_sixty_seconds_old_is_used():
    rows=[(i*8*H,.0001,100) for i in range(10)]
    events=[event(40*H+offset) for offset in [0,59000,60000]]
    obs=observations(events,{'X':rows})
    assert obs[events[0]['event_id']]['last_settled']==32*H
    assert obs[events[1]['event_id']]['last_settled']==32*H
    assert obs[events[2]['event_id']]['last_settled']==40*H
    assert all(o['settlements24']==3 for o in obs.values())
    altered=[(t,999 if t>40*H else r,m) for t,r,m in rows]
    assert observations(events,{'X':altered})==obs
    assert observations(events,{'X':[r for r in rows if r[0]<=40*H]})==obs


def test_long_short_receipts_mirror_and_independent_oracle():
    rows=[(i*4*H,(i%3-1)*.0004,100) for i in range(20)]
    events=[event(60*H+60000,s) for s in ['LONG','SHORT']];obs=observations(events,{'X':rows});oracle,oo=expected(events,{'X':rows})
    a,b=obs.values();assert a['last_receipt']==-b['last_receipt'] and a['day_receipt']==-b['day_receipt']
    for gate in GATES:assert filtered(events,obs,gate)[0]==oracle[gate]
    for key,o in oo.items():assert all(obs[key][k]==v for k,v in o.items())


def test_changing_interval_counts_observed_settlements_not_three_assumed_rates():
    rows=[(t*H,.0001,100) for t in [0,8,16,20,24,28,32,36,40]]
    e=event(40*H+60000);o=observations([e],{'X':rows})[e['event_id']]
    assert o['complete'] and o['settlements24']==6 and o['day_receipt']==-.0006


@pytest.mark.parametrize('rows',[[],[(0,.001,100),(8*H,.001,100)],[(t*H,.0001,100) for t in [0,8,24,32,40]]])
def test_missing_warmup_stale_or_internal_gap_reject(rows):
    e=event(40*H+60000);o=observations([e],{'X':rows})[e['event_id']]
    assert not o['complete']
    for gate in GATES[1:]:assert decision(o,gate)=='missing_or_stale_funding'
    assert decision(o,'none')=='accepted'


@pytest.mark.parametrize('ratio,ten,twentyfive',[(0,True,True),(.1,True,True),(.10001,False,True),(.25,False,True),(.25001,False,False)])
def test_registered_ratio_thresholds(ratio,ten,twentyfive):
    o=dict(complete=True,last_receipt=-.0002,day_receipt=-.0006,projected_cost_to_activation=ratio)
    assert (decision(o,'atr10')=='accepted')==ten
    assert (decision(o,'atr25')=='accepted')==twentyfive


def test_future_invalid_rate_does_not_leak_into_past_decision():
    rows=[(i*8*H,.0001 if i<6 else float('nan'),100) for i in range(10)]
    e=event(40*H+60000);o=observations([e],{'X':rows})[e['event_id']]
    assert o['complete']
    assert observations([e],{'X':rows})==observations([e],{'X':rows[:6]})
