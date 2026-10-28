import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from directional_carry_filters import observations,filtered,decision


def test_funding_sign_changes_with_direction_and_future_row_is_ignored():
    schedule=[(t,.0001,100) for t in range(0,48*3600000,8*3600000)]
    events=[dict(event_id=s,symbol='X',side=s,at=24*3600000+60000) for s in ['LONG','SHORT']]
    a=observations(events,{'X':schedule})
    b=observations(events,{'X':schedule[:4]})
    assert a==b and a['LONG']['last_receipt_rate']==-.0001
    assert a['SHORT']['day_receipt_rate']==.0003
    keep,counts=filtered(events,a,'nonnegative')
    assert keep==[events[1]] and counts==dict(negative_known_carry=1,accepted=1)


def test_sixty_second_delay_staleness_and_no_imputed_history():
    events=[dict(event_id=str(t),symbol='X',side='SHORT',at=t) for t in [0,59999,60000,24*3600000+60000]]
    a=observations(events,{'X':[(0,.01,100)]})
    assert a['59999']['last_receipt_rate'] is None
    assert a['60000']['last_receipt_rate']==.01 and a['60000']['day_receipt_rate'] is None
    assert a[str(24*3600000+60000)]['last_receipt_rate'] is None
    assert filtered(events,a,'none')[0]==events
    assert filtered(events,a,'avoid_costly')[0]==[]


@pytest.mark.parametrize('last,day,accepted',[(-.0005,-.001,True),(-.00050001,0,False),(0,-.00100001,False),(0,0,True)])
def test_cost_gate_boundaries(last,day,accepted):
    assert (decision(dict(last_receipt_rate=last,day_receipt_rate=day),'avoid_costly')=='accepted')==accepted
