from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
import research_v411 as v
import research_v410 as previous


def pool():
    return [{'symbol':s,'momentum':m,'volatility':w} for s,m,w in [('A',.01,.02),('B',.02,.03),('C',.03,.04),('D',.04,.05)]]


@pytest.mark.parametrize('momentum',[-.01,0.])
def test_reversal_study_requires_strictly_positive_treated_momentum(momentum):
    assert v.choose_control({'momentum':momentum,'volatility':.03},pool())[1]=='treated_nonpositive_momentum'


def test_positive_matching_uses_same_fixed_caliper_and_tie_rule():
    treated={'momentum':.02,'volatility':.03}
    chosen,reason=v.choose_control(treated,pool())
    assert reason is None and chosen['control']['symbol']=='B'
    assert v.choose_control({'momentum':.10,'volatility':.03},pool())[1]=='outside_fixed_caliper'
    assert v.choose_control(treated,pool()[:2])[1]=='fewer_than_three_positive_controls'
    values=pool()+[{'symbol':'AA',**treated,'future_profit':-100}]
    assert v.choose_control(treated,list(reversed(values)))[0]['control']['symbol']=='AA'


def test_degenerate_features_do_not_create_false_matches():
    values=[{'symbol':s,'momentum':.01,'volatility':.03} for s in 'ABC']
    assert v.choose_control({'momentum':.01,'volatility':.03},values)[1]=='degenerate_control_dispersion'


def test_old_negative_group_is_preserved_and_is_distinct_from_new_group():
    negative=[{**p,'momentum':-p['momentum']} for p in pool()]
    chosen,_=previous.choose_control({'momentum':-.02,'volatility':.03},negative)
    assert chosen['control']['symbol']=='B'
    assert previous.choose_control({'momentum':.02,'volatility':.03},pool())[0] is None


@pytest.mark.parametrize('name,expected',[('standard_vip6',-.0025),('stress_regular',-.011)])
def test_both_user_cost_scenarios_remain_per_fill(name,expected):
    p={'entry_reference':100.,'exit_reference':100.,'entry_ts_ms':1000,'exit_ts_ms':10000}
    assert v.unit_outcome(p,[],v.x.SCENARIOS[name])['net_return']==pytest.approx(expected)


def test_feature_reuse_cannot_be_contaminated_by_future_outcomes():
    times=pd.date_range('2024-01-01',periods=700,freq='5min',tz='UTC')
    p=100*np.exp(np.arange(700)*.0001);frame=pd.DataFrame({'open':p,'close':p},index=times)
    d=int(times[400].timestamp());first=v.feature_frame(frame,[d])
    frame.loc[times[400]:,'close']=1e9
    pd.testing.assert_frame_equal(first,v.feature_frame(frame,[d]))
    assert first.iloc[0].momentum==pytest.approx(.0288)
