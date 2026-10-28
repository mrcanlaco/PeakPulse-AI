from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
import research_v417 as v
import verify_research_v417 as independent
T=int(v.r.utc('2024-01-01T00:05:00Z').timestamp())


def frame(rows):
    return pd.DataFrame(rows,columns=['open','high','low','close','volume'],index=pd.to_datetime(np.arange(len(rows))*300+T,unit='s',utc=True))


def candidate():return {'id':'A:4h:1','symbol':'A','tf':'4h','entry_ts':T,'entry':100.,'stop':110.,'targets':[90.,80.,70.]}


def leg(rows):return v.build_leg(frame(rows),candidate(),'B','control',[])


@pytest.mark.parametrize('opening,expected',[(100.,-.1),(115.,-.15)])
def test_stop_priority_and_gap_are_preserved(opening,expected):
    c=candidate()
    f=frame([[100.,101.,95.,100.,1.],[opening,120.,65.,95.,1.]])
    a=v.build_leg(f,c,'A','control',[])
    assert a['paths']['ladder']['gross_return']==pytest.approx(expected)
    b=independent.independent_exits(f,a);assert b['exit_reason']=='stop'
    assert a['paths']['ladder']['gross_return']==pytest.approx(b['gross_return'])


def test_ratchet_same_bar_is_conservative():
    a=leg([[100,105,85,90,1]])
    assert a['paths']['ladder']['gross_return']==pytest.approx(.05) and a['paths']['ladder']['exit_reason']=='ratchet'
    out=v.outcome(a,[],v.SCENARIOS['standard_vip6']);assert len(out['fills'])==2
    assert out['fills'][1]['reference_price']==pytest.approx(95.)


def test_three_partial_exits_and_fixed_quantity():
    rows=[[100,101,95,96,1],[96,99,89,89,1],[89,89,79,79,1],[79,79,69,70,1]]
    a=leg(rows);assert a['paths']['ladder']['gross_return']==pytest.approx(.17)
    expected=independent.independent_exits(frame(rows),a);assert [f['fraction'] for f in expected['groups']]==pytest.approx([.5,.3,.2])
    out=v.outcome(a,[],v.SCENARIOS['stress_regular']);assert [f['qty'] for f in out['fills']]==pytest.approx([.01,.005,.003,.002])
    assert out['net_return']==pytest.approx(.17-out['fees']-out['slippage'])


def test_funding_before_same_timestamp_partial_exit():
    rows=[[100,101,95,96,1],[96,99,89,89,1],[89,89,79,79,1],[79,79,69,70,1]]
    a=leg(rows);events=[{'funding_ts_ms':(T+delta)*1000,'mark_price':100.,'funding_rate':rate,'price_source':'funding_api_settlement_mark'} for delta,rate in [(0,.9),(600,.01),(900,-.01),(1200,.01),(1500,.9)]]
    out=v.outcome(a,events,v.SCENARIOS['standard_vip6'])
    assert [e['remaining_qty'] for e in out['funding_events']]==pytest.approx([.01,.005,.002])
    assert out['funding']==pytest.approx(.01-.005+.002)


@pytest.mark.parametrize('scenario,expected',[('standard_vip6',-.0025),('stress_regular',-.011)])
def test_complete_flat_horizon_costs_per_fill(scenario,expected):
    a=leg([[100,101,99,100,1]]*(72*12));assert a['status']=='COMPLETE'
    assert v.outcome(a,[],v.SCENARIOS[scenario])['net_return']==pytest.approx(expected)


def test_truncated_horizon_is_unevaluable():
    a=leg([[100,101,99,100,1]])
    assert a['status']=='NOT_EVALUABLE' and a['quality']['horizon_truncated']


def test_missing_future_after_early_exit_is_irrelevant():
    a=leg([[100,115,95,110,1]])
    assert a['status']=='COMPLETE' and a['quality']['missing_bars']==0


def test_zero_exit_volume_flag_preserves_modeled_path():
    a=leg([[100,101,95,96,1],[96,99,89,89,0],[89,101,88,100,1]])
    assert a['status']=='COMPLETE' and a['quality']['zero_volume_exit_groups']==1


def test_control_scaling_preserves_percent_geometry():
    rows=[[100,101,95,96,1],[96,99,89,89,1],[89,89,79,79,1],[79,79,69,70,1]]
    a=leg(rows);f=frame(rows);f.loc[:,['open','high','low','close']]*=7
    b=v.build_leg(f,candidate(),'B','control',[])
    assert b['entry']==700 and b['stop']==770 and b['targets']==[630,560,490]
    assert a['paths']['ladder']['gross_return']==pytest.approx(b['paths']['ladder']['gross_return'])
