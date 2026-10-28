import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from account_net_trailing_replay import simulate
from research_capacity_config import configuration
from cross_sectional_audit import audit_exits

RULE=dict(market_step='0.001',step_size='0.001',min_qty=.001,market_min_qty=.001,max_qty=100000,market_max_qty=100000,min_notional=5,tick_size='0.001')


def fixture(closes=(100,99,90),mode='price',deadline=1/6,terminal_missing=False):
    times=[i*300000 for i in range(len(closes))]
    points={t:dict(mark=p,execution_close=p,entry_open=p) for t,p in zip(times,closes)}
    if terminal_missing:points[times[-1]]['entry_open']=float('nan')
    event=dict(symbol='X',event_id='x',side='SHORT',atr=2)
    policy=dict(entry_parts=3,entry_mode='favorable',entry_step_atr=.25,trailing=True,activation_atr=3,callback_fraction=.01,observation_minutes=5,max_hold_hours=deadline)
    if mode=='net_peak':policy.update(net_exit_mode=mode,activation_net_usdt=.2,net_callback_fraction=.25)
    config=configuration(5,0,20);config.max_slippage_bps=0
    r=simulate(times,{0:[event]},lambda _:points,{'X':RULE},lambda _:[],config,research_policy=policy)
    q=SimpleNamespace(trade_times=np.array(times)-300000,closes=np.array(closes),get=points.get)
    return r,pd.DataFrame(r['curve']),{'X':q},policy,{'x':event}


@pytest.mark.parametrize('mode',['price','net_peak'])
def test_time_expiry_precedes_new_trailing_activation(mode):
    args=fixture(mode=mode);r=args[0]
    assert any(j['kind']=='time_exit' for j in r['journal'])
    assert not any(j['kind']=='trail_activated' for j in r['journal'])
    assert audit_exits(*args,0,0)==(1,1,1)


def test_time_exit_keeps_realized_loss_and_terminal_missing_open_stays_marked():
    args=fixture(closes=(100,101,102));r=args[0]
    assert next(j for j in r['journal'] if j['kind']=='time_exit')['net']<0
    assert audit_exits(*args,0,0)==(1,1,1)
    pending=fixture(closes=(100,101,102),terminal_missing=True)
    assert pending[0]['open_positions'][0]['pending_exit']=='time_exit'
    assert audit_exits(*pending,0,0)==(1,1,0)


def test_trailing_can_exit_before_age_limit_and_corrupt_kind_fails_oracle():
    args=fixture(closes=(100,90,92,93),deadline=.25);r=args[0]
    j=next(j for j in r['journal'] if 'net' in j)
    assert j['kind']=='trailing_exit' and audit_exits(*args,0,0)[2]==0
    j['kind']='time_exit'
    with pytest.raises(AssertionError):audit_exits(*args,0,0)
