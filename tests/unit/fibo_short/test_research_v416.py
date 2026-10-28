from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
import research_v416 as v


def bars(n=900):
    t=pd.date_range('2024-01-01',periods=n,freq='5min',tz='UTC');price=100*np.exp(np.arange(n)*.0001)
    return pd.DataFrame({'open':price,'close':price,'volume':1.},index=t)


def test_episode_gap_cannot_supply_24h_features():
    a=bars();frame=v.assemble_views([a.iloc[:300],a.iloc[600:]])
    d=int(a.index[700].timestamp())
    assert v.method.feature_frame(frame,[d]).empty
    assert len(v.method.feature_frame(a,[d]))==1


def test_overlapping_episode_rows_are_rejected():
    a=bars()
    with pytest.raises(AssertionError):v.assemble_views([a.iloc[:600],a.iloc[500:]])


def test_no_future_features():
    a=bars();d=int(a.index[400].timestamp());old=v.method.feature_frame(a,[d])
    a.loc[a.index[400]:,'close']=1e9
    pd.testing.assert_frame_equal(old,v.method.feature_frame(a,[d]))


def test_known_close_only_and_relaunch_boundaries():
    e={'symbol':'A','known_from_utc':'2024-01-01','entry_close_only_from':'2024-01-02T08:30:00Z','settlement_at':'2024-01-02T09:00:00Z','relaunch_at':'2024-01-04T00:00:00Z'}
    assert v.eligible('A',v.r.utc('2024-01-02T08:29:59Z').timestamp(),[e])
    assert not v.eligible('A',v.r.utc('2024-01-02T08:30:00Z').timestamp(),[e])
    assert v.eligible('A',v.r.utc('2024-01-04').timestamp(),[e])


def test_zero_fill_and_settlement_quality_retained():
    a=bars();a.iloc[0,a.columns.get_loc('volume')]=0
    e={'symbol':'A','settlement_at':'2024-01-01T12:00:00Z'}
    p=v.inspect_path(a,int(a.index[0].timestamp()),[e],'A')
    assert p['status']=='COMPLETE' and p['zero_volume_entry'] and p['settlement_overlaps']==[e['settlement_at']]


def test_missing_future_path_not_rematched():
    a=bars();t=int(a.index[0].timestamp());a=a.drop(a.index[100])
    assert v.inspect_path(a,t,[],'A')['status']=='NOT_EVALUABLE'


@pytest.mark.parametrize('scenario,expected',[('standard_vip6',-.0025),('stress_regular',-.011)])
def test_costs_each_fill(scenario,expected):
    p={'entry_reference':100.,'exit_reference':100.,'entry_ts_ms':0,'exit_ts_ms':86400000}
    assert v.unit_outcome(p,[],v.x.SCENARIOS[scenario])['net_return']==pytest.approx(expected)


def test_cash_signed_funding_and_timestamp_boundary():
    p={'entry_reference':100.,'exit_reference':100.,'entry_ts_ms':0,'exit_ts_ms':86400000}
    events=[{'funding_ts_ms':t,'mark_price':100.,'funding_rate':rate,'price_source':'funding_api_settlement_mark'} for t,rate in [(0,.9),(28800000,.001),(86400000,-.002)]]
    out=v.unit_outcome(p,events,v.x.SCENARIOS['standard_vip6'])
    assert out['funding']==pytest.approx(-.001) and len(out['funding_events'])==2


def test_caliper_and_tie_ignore_future_performance():
    pool=[{'symbol':s,'momentum':m,'volatility':z,'future_return':ret} for s,m,z,ret in [('A',.02,.03,-1),('B',.01,.02,100),('C',.03,.04,50),('AA',.02,.03,50)]]
    assert v.choose_control({'momentum':.02,'volatility':.03},pool)[0]['control']['symbol']=='A'
