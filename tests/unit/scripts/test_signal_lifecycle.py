import sys
from pathlib import Path
import pytest
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from signal_lifecycle import calendar,invalidated,DAY
from account_signal_exit_replay import simulate
from account_net_trailing_replay import simulate as old
from research_capacity_config import configuration

RULE=dict(market_step='0.001',step_size='0.001',min_qty=.001,market_min_qty=.001,max_qty=100000,market_max_qty=100000,min_notional=5,tick_size='0.001')


def fixture(side='LONG',mode='sign168',opens=None,missing=False):
    times=[0,DAY,DAY+300000];points={t:dict(mark=100,execution_close=100,entry_open=o) for t,o in zip(times,opens or [100,90,90])}
    states={} if missing else {DAY:{'X':{168:-.1 if side=='LONG' else .1}}}
    signals={0:[dict(symbol='X',event_id='x',side=side,atr=2)],DAY:[dict(symbol='X',event_id='again',side=side,atr=2)]}
    config=configuration(5,.0005,20)
    policy=dict(entry_parts=3,entry_mode='favorable',entry_step_atr=.25,add_expiry_hours=6,trailing=True,activation_atr=3,callback_fraction=.01,observation_minutes=5)
    if mode:policy['signal_exit']=mode
    args=(times,signals,lambda _:points,{'X':RULE},lambda _:[(DAY,.001,100)],config)
    return args,policy,states


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_disabled_exact(side):
    args,p,states=fixture(side,None)
    assert simulate(*args,research_policy=p,exit_calendar=states)==old(*args,research_policy=p)


@pytest.mark.parametrize('side,opens',[('LONG',[100,90,90]),('SHORT',[100,110,110])])
def test_losing_exit_after_funding_at_actual_adverse_open_and_no_same_step_reentry(side,opens):
    args,p,states=fixture(side,opens=opens);r=simulate(*args,research_policy=p,exit_calendar=states)
    j=next(j for j in r['journal'] if j['kind']=='signal_exit')
    assert j['net']<0 and j['price']==pytest.approx(opens[1]*(.998 if side=='LONG' else 1.002))
    assert r['entries']==1 and r['rejections']['same_step_risk_exit']==1
    assert [j['kind'] for j in r['journal']][:3]==['entry','funding','signal_exit']


def test_missing_exit_data_invalidates_instead_of_keeping_profitable_path():
    args,p,states=fixture(missing=True);r=simulate(*args,research_policy=p,exit_calendar=states)
    assert r['ending_equity'] is None and r['errors'][0].startswith('missing_signal_exit_data:')


def test_terminal_missing_open_keeps_marked_inventory():
    args,p,states=fixture(opens=[100,90,float('nan')]);states[DAY]={'X':{168:.1}}
    # Move last observation onto next daily close.
    times=[0,DAY,2*DAY];points={t:dict(mark=100,execution_close=100,entry_open=o) for t,o in zip(times,[100,100,float('nan')])}
    states[2*DAY]={'X':{168:-.1}};signals={0:args[1][0]}
    r=simulate(times,signals,lambda _:points,args[3],lambda _:[],args[-1],research_policy=p,exit_calendar=states)
    assert r['ending_equity'] is not None and r['open_positions'][0]['pending_exit']=='signal_exit'


def test_two_confirmations_must_both_follow_entry_and_be_consecutive():
    s={t:{'X':{168:v}} for t,v in [(0,-.1),(DAY,-.1),(2*DAY,.1),(3*DAY,-.1),(4*DAY,-.1)]}
    assert not invalidated(s,DAY,'X','LONG',0,'sign168x2')
    assert not invalidated(s,3*DAY,'X','LONG',0,'sign168x2')
    assert invalidated(s,4*DAY,'X','LONG',0,'sign168x2')
    assert not invalidated(s,4*DAY+300000,'X','LONG',0,'sign168x2')


def test_calendar_closed_window_missing_bar_and_future_prefix():
    ix=pd.date_range('2025-01-01',periods=300,freq='h',tz='UTC');f=pd.DataFrame({'close':np.exp(np.arange(300)/1000)},index=ix)
    full=calendar({'X':f});cut=ix[240];at=int(cut.value//1000000)
    assert full[at]['X'][168]==pytest.approx(.168)
    assert calendar({'X':f.loc[:cut]})=={k:v for k,v in full.items() if k<=at}
    f.loc[ix[200],'close']=np.nan
    assert calendar({'X':f})[at]['X'][168] is None


def test_daily_zero_return_invalidates_both_directions():
    for side in ['LONG','SHORT']:assert invalidated({DAY:{'X':{24:0.}}},DAY,'X',side,0,'sign24')


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_independent_first_exit_oracle_rejects_corrupted_exit_kind(side):
    from types import SimpleNamespace
    import copy
    from signal_exit_audit import audit_exits
    args,p,states=fixture(side);times=list(range(0,DAY+300001,300000))
    points={t:dict(mark=100,execution_close=100,entry_open=100) for t in times}
    signals={0:args[1][0]}
    r=simulate(times,signals,lambda _:points,args[3],lambda _:[],args[-1],research_policy=p,exit_calendar=states)
    quotes={'X':SimpleNamespace(trade_times=np.array(times)-300000,closes=np.full(len(times),100.),get=points.get)}
    values=audit_exits(r,pd.DataFrame(r['curve']),quotes,p,{'x':signals[0][0]},.0005,20,states)
    assert values[0]==1
    corrupted=copy.deepcopy(r);next(j for j in corrupted['journal'] if j['kind']=='signal_exit')['kind']='trailing_exit'
    with pytest.raises(AssertionError):audit_exits(corrupted,pd.DataFrame(r['curve']),quotes,p,{'x':signals[0][0]},.0005,20,states)
