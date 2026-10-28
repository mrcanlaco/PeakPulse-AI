import copy
import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from impulse_failure import invalidation,context,HOUR,MODES
from account_impulse_exit_replay import simulate
from account_capital_trace import simulate as control
from impulse_exit_audit import audit_exits
from research_capacity_config import configuration

RULE=dict(market_step='0.001',step_size='0.001',min_qty=.001,market_min_qty=.001,max_qty=100000,market_max_qty=100000,min_notional=5,tick_size='0.001')


def candle(side='LONG'):
    return dict(at=0,symbol='X',side=side,open=100.,high=104.2 if side=='LONG' else 101.,low=99. if side=='LONG' else 95.8,close=104. if side=='LONG' else 96.)


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_strict_open_and_extreme_boundary_and_consecutive_confirmation(side):
    c=candle(side);direction=1 if side=='LONG' else -1
    q={HOUR:dict(execution_close=100.),2*HOUR:dict(execution_close=100-direction*.5),3*HOUR:dict(execution_close=100-direction*.5)}
    assert invalidation(q,c,0,HOUR,'open1') is None
    assert invalidation(q,c,0,2*HOUR,'open1')
    assert invalidation(q,c,0,2*HOUR,'open2') is None
    assert invalidation(q,c,0,3*HOUR,'open2')
    assert invalidation(q,c,0,3*HOUR,'extreme1') is None
    q[3*HOUR]['execution_close']=100-direction*1.1
    assert invalidation(q,c,0,3*HOUR,'extreme1')


def test_only_closed_hours_after_entry_and_missing_observation_fails():
    c=candle();q={HOUR:dict(execution_close=90.)}
    assert invalidation({},c,0,300000,'open1') is None
    assert invalidation(q,c,HOUR,HOUR,'open1') is None
    assert invalidation(q,c,0,HOUR,'open2') is None
    with pytest.raises(ValueError,match='missing_impulse'):invalidation(q,c,0,2*HOUR,'open2')
    with pytest.raises(ValueError,match='invalid_impulse_exit_mode'):invalidation(q,c,0,HOUR,'unknown')


def fixture(side,mode,missing_terminal=False,pause=.2):
    times=list(range(0,2*HOUR+1,300000));direction=1 if side=='LONG' else -1
    start=104 if side=='LONG' else 96
    q={t:dict(mark=start,execution_close=start,entry_open=start) for t in times}
    for t in times[12:]:q[t]=dict(mark=100-direction*2,execution_close=100-direction*2,entry_open=100-direction*5)
    if missing_terminal:q[2*HOUR]['entry_open']=float('nan')
    e=dict(at=0,symbol='X',side=side,event_id='x',atr=2.)
    signals={0:[e],2*HOUR:[dict(e,at=2*HOUR,event_id='again')]}
    contexts={'x':candle(side),'again':candle(side)}
    p=dict(position_notional=25,entry_parts=3,entry_mode='favorable',entry_step_atr=.25,add_expiry_hours=6,trailing=True,activation_atr=3,callback_fraction=.01,observation_minutes=5)
    if mode:p['impulse_exit']=mode
    config=configuration(5,0,20);config.max_slippage_bps=0;config.entry_pause_drawdown=pause
    args=(times,signals,lambda _:q,{'X':RULE},lambda _:[],config)
    quotes=SimpleNamespace(trade_times=np.array(times)-300000,closes=np.array([q[t]['execution_close'] for t in times]),get=q.get)
    return args,p,contexts,{'X':quotes},{'x':e,'again':dict(e,event_id='again')}


@pytest.mark.parametrize('side',['LONG','SHORT'])
@pytest.mark.parametrize('mode',list(MODES))
def test_hourly_invalidation_actual_gap_fill_and_oracle(side,mode):
    args,p,c,quotes,events=fixture(side,mode)
    raw=simulate(*args,research_policy=p,impulse_context=c)
    first=next(j for j in raw['journal'] if j['kind']=='impulse_exit')
    assert first['at']==(2 if mode.endswith('2') else 1)*HOUR
    assert first['price']==(95 if side=='LONG' else 105) and first['net']<0
    assert audit_exits(raw,pd.DataFrame(raw['curve']),quotes,p,events,0,0,c)[2]>=1
    broken=copy.deepcopy(raw);next(j for j in broken['journal'] if j['kind']=='impulse_exit')['hourly_closes'][0]+=1
    with pytest.raises(AssertionError):audit_exits(broken,pd.DataFrame(raw['curve']),quotes,p,events,0,0,c)
    if mode.endswith('2'):assert raw['entries']==1


def test_missing_terminal_open_keeps_pending_marked_position():
    args,p,c,quotes,events=fixture('LONG','open2',missing_terminal=True)
    raw=simulate(*args,research_policy=p,impulse_context=c)
    assert raw['open_positions'][0]['pending_exit']=='impulse_exit'
    assert audit_exits(raw,pd.DataFrame(raw['curve']),quotes,p,events,0,0,c)[2]==0


def test_pause_still_runs_exit_and_hold_control_is_exact():
    args,p,c,quotes,events=fixture('LONG','open2',pause=.0001)
    raw=simulate(*args,research_policy=p,impulse_context=c)
    assert raw['entry_paused'] and not raw['open_positions'] and raw['entries']==1
    args,p,c,_,_=fixture('LONG',None)
    assert simulate(*args,research_policy=p,impulse_context=c)==control(*args,research_policy=p)


def test_context_is_frozen_at_source_candle_and_inconsistent_context_rejected():
    t=pd.Timestamp(0,unit='ms',tz='UTC');h=pd.DataFrame([candle(),dict(candle(),open=200,high=220,low=195,close=215)],index=[t,t+pd.Timedelta(hours=1)])
    e=dict(at=300000,source_at=0,symbol='X',side='LONG',event_id='x')
    assert context([e],{'X':h})['x']==candle()
    args,p,c,_,_=fixture('LONG','open1');c['x']['side']='SHORT'
    with pytest.raises(ValueError,match='missing_or_inconsistent'):simulate(*args,research_policy=p,impulse_context=c)


@pytest.mark.parametrize('mode,reason',[('open1','impulse_exit'),('open2','trailing_exit')])
def test_first_hour_exit_priority_against_already_activated_trailing(mode,reason):
    args,p,c,_,events=fixture('LONG',mode)
    points=args[2]('X');points[HOUR-300000]=dict(mark=111.,execution_close=111.,entry_open=111.)
    raw=simulate(*args,research_policy=p,impulse_context=c)
    closed=next(j for j in raw['journal'] if 'net' in j)
    assert closed['at']==HOUR and closed['kind']==reason


def test_hourly_failure_cannot_rescue_prior_cross_breach():
    args,p,c,_,_=fixture('SHORT','open1')
    points=args[2]('X');points[HOUR]=dict(mark=10000.,execution_close=10000.,entry_open=10000.)
    raw=simulate(*args,research_policy=p,impulse_context=c)
    assert raw['ending_equity'] is None and raw['stop_event']['at']==HOUR
    assert not any(j['kind']=='impulse_exit' for j in raw['journal'])
