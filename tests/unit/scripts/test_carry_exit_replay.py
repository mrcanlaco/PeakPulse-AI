import sys
from pathlib import Path
from types import SimpleNamespace
import copy
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from account_carry_exit_replay import simulate
from account_capital_trace import simulate as prior
from carry_exit_audit import audit_exits
from capital_commitment_audit import audit
from research_capacity_config import configuration

RULE=dict(market_step='0.001',step_size='0.001',min_qty=.001,market_min_qty=.001,max_qty=100000,market_max_qty=100000,min_notional=5,tick_size='0.001')
POLICY=dict(position_notional=25,entry_parts=3,entry_mode='favorable',entry_step_atr=.25,add_expiry_hours=6,trailing=True,activation_atr=3,callback_fraction=.01,observation_minutes=5)


def run(side='SHORT',rate=-.04,prices=None,policy=None,signals=None,terminal=False):
    times=[0,300000,600000,900000]
    vals=prices or [100,100,101,101]
    points={t:dict(mark=v,execution_close=v,entry_open=float('nan') if terminal and t==600000 else v) for t,v in zip(times,vals)}
    if terminal:times=times[:3]
    e=dict(symbol='X',event_id='a',at=0,side=side,atr=2)
    events=signals or {0:[e]}
    p=dict(POLICY,carry_exit_fraction=.01) if policy is None else policy
    args=(times,events,lambda _:points,{'X':RULE},lambda _:[(300000,rate,100)],configuration(5,.0005,20))
    r=simulate(*args,research_policy=p)
    q=SimpleNamespace(get=points.get,trade_times=np.array([t-300000 for t in times]),closes=np.array([points[t]['execution_close'] for t in times]))
    assert audit_exits(r,pd.DataFrame(r['curve']),{'X':q},p,{'a':e},.0005,20)[0]==1
    audit(r,{'X':q},.0005,25,rules={'X':RULE})
    return r,args,p


@pytest.mark.parametrize('side,rate',[('SHORT',-.04),('LONG',.04)])
def test_waits_sixty_seconds_and_can_close_at_net_loss(side,rate):
    r,_,_=run(side,rate)
    exits=[j for j in r['journal'] if 'net' in j]
    assert len(exits)==1 and exits[0]['kind']=='carry_exit' and exits[0]['at']==600000
    assert exits[0]['net']<0 and exits[0]['funding_limit']==.25
    assert r['entries']==1 and not r['open_positions']


def test_none_policy_is_bit_exact_old_engine():
    r,args,p=run(policy=POLICY)
    assert r==prior(*args,research_policy=p)


def test_same_step_reentry_is_blocked_and_remaining_adds_do_not_execute():
    e=dict(symbol='X',event_id='a',at=0,side='SHORT',atr=2)
    r,_,_=run(signals={0:[e],600000:[dict(e,event_id='b',at=600000)]})
    assert r['rejections']['same_step_risk_exit']==1
    assert not any(j['kind']=='entry_add' for j in r['journal'])


def test_terminal_missing_open_keeps_marked_inventory():
    r,_,_=run(terminal=True)
    assert not any('net' in j for j in r['journal'])
    assert r['open_positions'][0]['pending_exit']=='carry_exit' and r['ending_equity'] is not None


def test_prior_positive_funding_offsets_later_negative_receipts():
    r,args,p=run(rate=.04)
    assert not any(j['kind']=='carry_exit' for j in r['journal'])
    # Two settlements leave net carry zero, even though the second is costly.
    times,signals,prices,rules,_,config=args
    r=simulate(times,signals,prices,rules,lambda _:[(100000,.04,100),(300000,-.04,100)],config,research_policy=p)
    assert not any(j['kind']=='carry_exit' for j in r['journal'])
    assert abs(r['funding'])<1e-9


def test_carry_trigger_runs_while_drawdown_opening_pause_remains_latched():
    r,_,_=run(prices=[100,1400,101,101])
    assert r['entry_paused'] and r['ending_equity'] is not None
    assert any(j['kind']=='carry_exit' for j in r['journal'])
    assert r['curve'][-1]['paused']


def test_carry_has_priority_over_simultaneous_trailing_activation():
    r,_,_=run(prices=[100,100,90,90])
    assert not any(j['kind']=='trail_activated' for j in r['journal'])
    assert any(j['kind']=='carry_exit' for j in r['journal'])


def test_maintenance_breach_precedes_any_attempt_to_rescue_with_carry_exit():
    times=[0,300000,600000]
    points={t:dict(mark=v,execution_close=v,entry_open=v) for t,v in zip(times,[100,8000,100])}
    e=dict(symbol='X',event_id='a',at=0,side='SHORT',atr=2)
    r=simulate(times,{0:[e]},lambda _:points,{'X':RULE},lambda _:[(100000,-.04,100)],configuration(5,.0005,20),research_policy=dict(POLICY,carry_exit_fraction=.01))
    assert r['ending_equity'] is None and r['stop_event']['at']==300000
    assert not any(j['kind']=='carry_exit' for j in r['journal'])


def test_new_position_does_not_inherit_old_funding_loss():
    times=list(range(0,1500000,300000));points={t:dict(mark=100,execution_close=100,entry_open=100) for t in times}
    e=dict(symbol='X',event_id='a',at=0,side='SHORT',atr=2)
    r=simulate(times,{0:[e],900000:[dict(e,event_id='b',at=900000)]},lambda _:points,{'X':RULE},lambda _:[(300000,-.04,100)],configuration(5,.0005,20),research_policy=dict(POLICY,carry_exit_fraction=.01))
    assert r['entries']==2
    p=r['open_positions'][0]
    assert p['event_id']=='b' and p['funding']==p['funding_known']==0 and p['funding_pending']==[]


@pytest.mark.parametrize('value',[0,-.01,float('nan'),float('inf'),.11])
def test_invalid_fraction_fails(value):
    with pytest.raises(ValueError,match='invalid_carry_exit_fraction'):
        simulate([],{},None,None,None,configuration(5,.0005,20),research_policy=dict(POLICY,carry_exit_fraction=value))
