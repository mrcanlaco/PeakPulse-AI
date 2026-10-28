from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
import research_v419 as v


def stamp(s):return int(v.r.utc(s).timestamp())


def candidate(t,cid):
    path=v.r.simulate_path([(t,100,101,99,100),(t+300,100,101,98,99)],100,110,[90,80,70])
    return {'id':cid,'symbol':'S','tf':'4h','wave_key':'same_wave','score':80.,'entry_ts':t,'entry':100.,'stop':110.,'paths':{'ladder':path},
        'milestones':['m6_f4_elite_sniper'],'missing_execution_bars':0}


def test_wave_state_is_not_reset_at_new_year():
    a=candidate(stamp('2020-12-31T23:55:00Z'),'A');b=candidate(stamp('2021-01-04T23:55:00Z'),'B')
    fund={'S':{'times':np.array([],dtype='int64'),'events':[]}}
    result=v.x.portfolio([a,b],{'gate':'elite_sniper','sizing':'risk'},'2020-01-01','2021-01-11',v.SCENARIOS['standard_vip6'],fund)
    assert [p['id'] for p in result['ledger']]==['A'] and result['rejected']['wave_or_cooldown']==1
    filtered=v.x.portfolio([c for c in [a,b] if v.annual_eligible(c)],{'gate':'elite_sniper','sizing':'risk'},'2020-01-01','2021-01-11',v.SCENARIOS['standard_vip6'],fund)
    assert [p['id'] for p in filtered['ledger']]==['B']


def test_funding_accrues_on_position_carried_across_new_year():
    c=candidate(stamp('2020-12-31T23:55:00Z'),'A');t=stamp('2021-01-01')*1000
    fund={'S':{'times':np.array([t]),'events':[{'funding_ts_ms':t,'mark_price':100.,'funding_rate':.001,'price_source':'funding_api_settlement_mark'}]}}
    result=v.x.portfolio([c],{'gate':'elite_sniper','sizing':'risk'},'2020-01-01','2021-01-11',v.SCENARIOS['standard_vip6'],fund)
    p=result['ledger'][0]
    assert p['entry_ts_ms']<t<p['exit_ts_ms']
    assert p['funding_events'][0]['remaining_qty']==p['qty'] and p['funding']==pytest.approx(p['qty']*.1)


@pytest.mark.parametrize('t,expected',[('2020-12-26T23:59:59Z',True),('2020-12-27',False),('2020-12-31',False),('2021-01-01',True)])
def test_annual_embargo_exact_boundary(t,expected):
    assert v.annual_eligible({'entry_ts':stamp(t)})==expected


def test_marked_subperiod_uses_carried_nav_after_same_time_events():
    raw=[('2023-12-31',100),('2024-01-01',110),('2024-01-01',105),('2024-01-02',120),('2024-01-03',115)]
    curve=[(stamp(t)*1000,a) for t,a in raw]
    metric,weekly,_=v.marked_window(curve,'2024-01-01','2024-01-03')
    assert metric['start_nav']==105 and metric['end_nav']==115
    assert metric['return_pct']==pytest.approx((115/105-1)*100)
    assert metric['max_dd_pct']==pytest.approx((1-115/120)*100)
    assert np.prod(1+weekly)==pytest.approx(115/105)


def test_marked_subperiod_does_not_look_forward_to_next_event():
    curve=[(stamp('2024-01-01')*1000,100),(stamp('2024-01-03')*1000,120),(stamp('2024-01-05')*1000,90)]
    metric,_,_=v.marked_window(curve,'2024-01-02','2024-01-04')
    assert metric['start_nav']==100 and metric['end_nav']==120 and metric['return_pct']==pytest.approx(20)
