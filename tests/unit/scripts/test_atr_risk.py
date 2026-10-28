import sys
from pathlib import Path
import copy
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from account_net_trailing_replay import simulate
from atr_exit_audit import audit_exits
from atr_execution_metrics import stop_metrics
from research_capacity_config import configuration

RULE=dict(market_step='0.001',step_size='0.001',min_qty=.001,market_min_qty=.001,max_qty=100000,market_max_qty=100000,min_notional=5,tick_size='0.001')


def replay(side,marks,closes=None,opens=None,stop=1,pause=.2):
    times=[i*300000 for i in range(len(marks))];closes=closes or [100]*len(times);opens=opens or closes
    points={t:dict(mark=m,execution_close=c,entry_open=o) for t,m,c,o in zip(times,marks,closes,opens)}
    signals={0:[dict(symbol='X',event_id='x',side=side,atr=2)]}
    policy=dict(entry_parts=3,entry_mode='favorable',entry_step_atr=.25,add_expiry_hours=6,trailing=True,activation_atr=3,callback_fraction=.01,observation_minutes=5)
    if stop:policy['stop_atr']=stop
    config=configuration(5,0,20);config.max_slippage_bps=0;config.entry_pause_drawdown=pause
    r=simulate(times,signals,lambda _:points,{'X':RULE},lambda _:[],config,research_policy=policy)
    q=SimpleNamespace(trade_times=np.array(times)-300000,closes=np.array(closes),mark_times=np.array(times)-300000,marks=np.array(marks),get=points.get)
    return r,policy,{'X':q},{'x':signals[0][0]}


@pytest.mark.parametrize('side,marks,opens',[('LONG',[100,99,98],[100,100,90]),('SHORT',[100,101,102],[100,100,110])])
def test_mark_threshold_and_actual_gap_fill(side,marks,opens):
    r,p,quotes,events=replay(side,marks,opens=opens)
    stop=next(j for j in r['journal'] if j['kind']=='atr_stop')
    assert stop['at']==600000 and stop['price']==opens[-1] and stop['net']<0
    assert audit_exits(r,pd.DataFrame(r['curve']),quotes,p,events,0,0)[2]==1
    m=stop_metrics(r,p,events,quotes)
    assert m['count']==m['over_distance']==1 and m['max_gross_ratio']==pytest.approx(5)
    broken=copy.deepcopy(r);next(j for j in broken['journal'] if j['kind']=='atr_stop')['at']=300000
    with pytest.raises(AssertionError):audit_exits(broken,pd.DataFrame(r['curve']),quotes,p,events,0,0)


@pytest.mark.parametrize('side,closes,marks',[('LONG',[100,101,100,100],[100,101,100,98.3]),('SHORT',[100,99,100,100],[100,99,100,101.7])])
def test_weighted_entry_after_favorable_add_sets_stop_distance(side,closes,marks):
    r,p,quotes,events=replay(side,marks,closes)
    assert sum(j['kind']=='entry_add' for j in r['journal'])==1
    stop=next(j for j in r['journal'] if j['kind']=='atr_stop')
    assert stop['at']==900000
    assert audit_exits(r,pd.DataFrame(r['curve']),quotes,p,events,0,0)[2]==1


def test_stop_precedes_same_step_trailing_trigger():
    r,p,quotes,events=replay('LONG',[100,106,97],[100,106,104],[100,106,103])
    assert [j['kind'] for j in r['journal']]==['entry','trail_activated','atr_stop']
    assert audit_exits(r,pd.DataFrame(r['curve']),quotes,p,events,0,0)[2]==1


def test_terminal_missing_execution_price_keeps_pending_marked_position():
    r,p,quotes,events=replay('SHORT',[100,102],opens=[100,float('nan')])
    assert r['ending_equity'] is not None and r['open_positions'][0]['pending_exit']=='atr_stop'
    assert audit_exits(r,pd.DataFrame(r['curve']),quotes,p,events,0,0)[2]==0


def test_entry_pause_does_not_disable_risk_exit_or_resume():
    r,_,_,_=replay('LONG',[100,99,98],opens=[100,100,98],pause=.0001)
    assert r['entry_paused'] and not r['open_positions'] and r['entries']==1
    assert any(j['kind']=='atr_stop' for j in r['journal'])


def test_control_holds_same_adverse_move_without_forced_close():
    r,p,quotes,events=replay('LONG',[100,99,98],stop=None)
    assert len(r['open_positions'])==1 and not any('net' in j for j in r['journal'])
    assert audit_exits(r,pd.DataFrame(r['curve']),quotes,p,events,0,0)[2]==0
