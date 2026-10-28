from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
import research_v412 as v

T=int(v.r.utc('2024-01-01 00:05').timestamp())


def test_stop_only_does_not_take_profits_or_ratchet_after_price_decline():
    bars=[(T,100,105,50,50),(T+300,50,105,49,100)]
    path=v.stop_only_path(bars,100,110,T+600)
    assert path['gross_return']==pytest.approx(0) and path['exit_reason']=='horizon'
    assert [s[3] for s in path['trace']]==[1,0]
    assert [s[4] for s in path['trace']]==[110,110]
    assert sum(s[5] for s in path['trace'])==pytest.approx(0)


@pytest.mark.parametrize('opening,expected',[(100,-.10),(115,-.15)])
def test_stop_first_and_adverse_gap_fill(opening,expected):
    path=v.stop_only_path([(T,opening,120,50,90)],100,110,T+300)
    assert path['gross_return']==pytest.approx(expected) and path['exit_reason']=='stop'
    rows=v.x.execution_steps({'entry':100,'paths':{'ladder':path}})
    assert rows[-1][-1]==pytest.approx(max(110,opening))


def test_horizon_uses_final_close_and_fixed_quantity():
    path=v.stop_only_path([(T,100,105,90,95),(T+300,95,99,75,80)],100,110,T+600)
    assert path['gross_return']==pytest.approx(.2)
    assert [s[5] for s in path['trace']]==pytest.approx([.05,.15])


def test_future_data_boundary_is_labelled_not_silently_called_full_horizon():
    path=v.stop_only_path([(T,100,105,90,95)],100,110,T+900)
    assert path['exit_reason']=='data_boundary_before_horizon'
    assert v.missing_bars(np.array([T]),T,T+900)==2


def test_internal_gaps_are_counted_without_rejecting_future_outcomes():
    bars=[(T,100,105,95,99),(T+600,99,111,98,110)]
    path=v.stop_only_path(bars,100,110,T+1200)
    assert path['exit_ts']==T+900 and path['exit_reason']=='stop'
    assert v.missing_bars(np.array([T,T+600]),T,path['exit_ts'])==1


def test_arm_transformation_preserves_candidate_entry_and_baseline_quality():
    c={'id':'S','paths':{},'entry':100,'missing_execution_bars':7,
        'research_paths':{arm:{'exit_ts':T+i*300} for i,arm in enumerate(v.ARMS)},
        'research_quality':{arm:{'missing_bars':i} for i,arm in enumerate(v.ARMS)}}
    arms=[v.arm_candidates([c],a)[0] for a in v.ARMS]
    assert [a['entry'] for a in arms]==[100]*3
    assert [a['missing_execution_bars'] for a in arms]==[7,1,2]
    assert c['paths']=={}


def test_common_calendar_keeps_zero_intervals_and_last_partial_week():
    series=pd.Series([100.,110.,110.],index=pd.to_datetime(['2024-01-01','2024-01-08','2026-01-01'],utc=True))
    returns,ends=v.calendar_returns(series,'2024-01-01','2026-01-01')
    assert len(returns)==105 and returns[0]==pytest.approx(.1)
    assert np.count_nonzero(returns)==1 and ends[-1].startswith('2026-01-01')
    assert np.prod(1+returns)==pytest.approx(1.1)


def test_family_adjusted_interval_uses_same_draws_and_is_wider():
    values=np.tile(np.array([-.02,.01,.03,-.01,0.]),21)
    a=v.interval(values,alpha=.05,samples=1000);b=v.interval(values,alpha=.025,samples=1000)
    assert b['confidence_pct']==97.5 and b['ci_pct'][0]<=a['ci_pct'][0]<=a['ci_pct'][1]<=b['ci_pct'][1]
    zero=v.interval(np.zeros(105),alpha=.025,samples=100)
    assert zero['ci_pct']==[0,0]
