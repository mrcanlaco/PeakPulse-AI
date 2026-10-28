import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from account_net_trailing_replay import simulate
from account_side_quota_replay import simulate as original
from research_capacity_config import configuration

RULE=dict(market_step='0.001',step_size='0.001',min_qty=.001,market_min_qty=.001,max_qty=100000,market_max_qty=100000,min_notional=5,tick_size='0.001')


def replay(side='SHORT', mode='price', closes=(100,94,95), funding=(), opens=None, extra=None):
    times=[i*300000 for i in range(len(closes))]
    points={t:dict(mark=c,execution_close=c,entry_open=o) for t,c,o in zip(times,closes,opens or closes)}
    signals={0:[dict(symbol='X',event_id='x',side=side,atr=2)]}
    policy=dict(entry_parts=3,entry_mode='favorable',entry_step_atr=.25,add_expiry_hours=6,trailing=True,activation_atr=3,callback_fraction=.01,observation_minutes=5)
    policy.update(extra or {})
    if mode!='price': policy['net_exit_mode']=mode
    if mode=='net_peak':policy.update(activation_net_usdt=.1,net_callback_fraction=.25)
    config=configuration(5,0,20); config.max_slippage_bps=0
    args=(times,signals,lambda _:points,{'X':RULE},lambda _:list(funding),config)
    return simulate(*args,research_policy=policy),args,policy


@pytest.mark.parametrize('side,closes',[('SHORT',(100,94,95)),('LONG',(100,106,105))])
def test_price_control_exact(side,closes):
    r,args,p=replay(side,closes=closes)
    assert r==original(*args,research_policy=p)


@pytest.mark.parametrize('side,closes,rate',[('SHORT',(100,94,95),-.1),('LONG',(100,106,104),.1)])
def test_funding_loss_blocks_net_gate_but_not_price_control(side,closes,rate):
    funding=[(300000,rate,100)]
    r,_,_=replay(side,'price_net_gate',closes,funding)
    base,_,_=replay(side,'price',closes,funding)
    assert len(r['open_positions'])==1 and r['open_positions'][0]['blocked_net_exits']==1
    assert any('net' in j and j['net']<0 for j in base['journal'])
    assert r['funding']==base['funding']


@pytest.mark.parametrize('side,closes',[('SHORT',(100,98,95,97)),('LONG',(100,102,105,103))])
def test_net_peak_tracks_profit_and_cancels_pending_parts(side,closes):
    r,_,_=replay(side,'net_peak',closes)
    activated=next(j for j in r['journal'] if j['kind']=='trail_activated')
    exit=next(j for j in r['journal'] if 'net' in j)
    assert activated['at']==300000 and exit['at']==900000
    assert exit['observed_net']==pytest.approx(exit['net']) and exit['net_peak']>exit['observed_net']>0
    assert not any(j['kind']=='entry_add' for j in r['journal'])


def test_next_open_gap_can_realize_loss_despite_nonnegative_decision():
    r,_,_=replay(mode='net_peak',closes=(100,98,95,97),opens=(100,98,95,130))
    exit=next(j for j in r['journal'] if 'net' in j)
    assert exit['observed_net']>0 and exit['net']<0 and exit['price']==130


def test_funding_is_not_known_before_settlement():
    r,_,_=replay(mode='net_peak',closes=(100,100,100,100),funding=[(600000,.1,100)])
    act=next(j for j in r['journal'] if j['kind']=='trail_activated')
    assert act['at']==600000 and act['observed_net']>0


def test_terminal_gap_keeps_pending_exit_and_inventory_marked():
    r,_,_=replay(mode='net_peak',closes=(100,98,95,97),opens=(100,98,95,float('nan')))
    assert r['ending_equity'] is not None and len(r['open_positions'])==1
    assert r['open_positions'][0]['pending_exit']=='trailing_exit'


def test_negative_net_and_drawdown_pause_do_not_force_exit():
    r,_,_=replay(mode='price_net_gate',closes=(100,94,2000))
    assert r['entry_paused'] and len(r['open_positions'])==1
    assert not any('net' in j for j in r['journal'])


def test_unknown_mode_rejected():
    with pytest.raises(ValueError,match='invalid_net_exit_mode'):replay(mode='unknown')


@pytest.mark.parametrize('side,closes',[('SHORT',(100,98,95,97)),('LONG',(100,102,105,103))])
def test_independent_trigger_reconstruction_detects_corrupted_metadata(side,closes):
    from types import SimpleNamespace
    import pandas as pd
    import numpy as np
    from verify_net_trailing import audit_triggers
    r,args,p=replay(side,'net_peak',closes)
    q=SimpleNamespace(trade_times=np.array([-300000,0,300000,600000]),closes=np.array(closes),get=args[2]('X').get)
    assert audit_triggers(r,pd.DataFrame(r['curve']),{'X':q},p,{'x':dict(atr=2)},0,0)==(1,3)
    next(j for j in r['journal'] if 'net' in j)['observed_net']+=.1
    with pytest.raises(AssertionError):audit_triggers(r,pd.DataFrame(r['curve']),{'X':q},p,{'x':dict(atr=2)},0,0)
