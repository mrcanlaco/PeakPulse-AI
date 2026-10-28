import sys
from pathlib import Path
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from cross_regime_signals import decision,filtered,GATES


def row(**changes):
    return dict(dict(coverage=30,above=.6,below=.4,btc_ready=True,btc_close=110,btc_ema20=105,btc_ema60=100,btc_ret24=.01,btc_ret7=.02),**changes)


@pytest.mark.parametrize('gate',GATES[1:])
def test_bullish_direction_and_no_forced_opposite_signal(gate):
    assert decision('LONG',row(),gate)=='accepted'
    assert decision('SHORT',row(),gate)=='regime_disagrees'


def test_equal_levels_count_as_neither_and_missing_state_is_not_favorable():
    for side in ['LONG','SHORT']:
        assert decision(side,row(btc_ret7=0),'btc_week')=='regime_disagrees'
        assert decision(side,row(btc_ema20=100,btc_ema60=100),'btc_trend')=='regime_disagrees'
        assert decision(side,None,'none')=='accepted'
        assert decision(side,None,'consensus')=='missing_market_state'


def test_coverage_and_btc_requirements_are_specific_to_gate():
    assert decision('LONG',row(coverage=23),'breadth60')=='breadth_not_ready'
    assert decision('LONG',row(coverage=23),'btc_week')=='accepted'
    assert decision('LONG',row(btc_ready=False),'btc_trend')=='btc_not_ready'
    assert decision('LONG',row(btc_ready=False),'breadth60')=='accepted'


def test_consensus_requires_both_and_bearish_mirror():
    bear=row(above=.3,below=.7,btc_close=90,btc_ema20=95,btc_ema60=100,btc_ret24=-.01,btc_ret7=-.02)
    assert decision('SHORT',bear,'consensus')=='accepted'
    assert decision('SHORT',dict(bear,below=.59),'consensus')=='regime_disagrees'
    assert decision('LONG',row(above=.59),'consensus')=='regime_disagrees'


def test_filter_preserves_time_identity_score_and_rejection_not_retry():
    idx=pd.date_range('2026-01-01',periods=2,freq='1D',tz='UTC');state=pd.DataFrame([row(),row(btc_ret7=-.02)],index=idx)
    e=dict(event_id='x',symbol='X',side='LONG',at=int(idx[0].timestamp()*1000),atr=2,probability=.5)
    s=dict(e,event_id='s',side='SHORT')
    out,counts=filtered([e,s],state,'btc_week')
    assert out==[e] and counts==dict(accepted=1,regime_disagrees=1)
    assert filtered([e,s],state,'none')[0]==[e,s]
