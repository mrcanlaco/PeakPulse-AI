from pathlib import Path
import sys
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
import lifecycle_research_v414 as v
import verify_lifecycle_v414 as independent


def data(volumes=(1.,0.,0.),minutes=(0,5,10),reason='horizon'):
    start=pd.Timestamp('2025-01-01T00:00Z');index=pd.DatetimeIndex([start+pd.Timedelta(minutes=n) for n in minutes])
    frame=pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.,'volume':volumes,'quote_volume':[100*x for x in volumes]},index=index)
    ts=int(start.timestamp());trace=[(int(t.timestamp())+300,100.,1.,0. if i==len(index)-1 else 1.,110.,0.,i==len(index)-1) for i,t in enumerate(index)]
    c={'id':'TESTUSDT:4h:'+str(ts),'symbol':'TESTUSDT','tf':'4h','entry_ts':ts,'paths':{'ladder':{'exit_ts':trace[-1][0],'exit_reason':reason,'trace':trace}}}
    return c,frame


def test_zero_volume_marks_and_exit_turnover_are_distinct():
    c,frame=data();quality=v.inspect_path(c,frame,[])
    assert quality['entry_zero_volume'] is False and quality['zero_volume_path_bars']==2
    assert quality['zero_volume_exit_groups']==[c['paths']['ladder']['exit_ts']]
    assert quality['horizon_truncated'] is True


def test_missing_bar_is_counted_without_removing_candidate():
    c,frame=data(volumes=(1.,1.),minutes=(0,10))
    before=dict(c);quality=v.inspect_path(c,frame,[])
    assert quality['missing_bars_through_modelled_exit']==1 and quality['zero_volume_path_bars']==0
    assert c==before


def test_entry_zero_volume_does_not_infer_positive_liquidity_from_later_bar():
    c,frame=data(volumes=(0.,1.,1.));quality=v.inspect_path(c,frame,[])
    assert quality['entry_zero_volume'] and quality['last_positive_volume_bar_before_entry'] is None


def test_last_positive_activity_uses_only_bars_before_entry():
    c,frame=data(volumes=(1.,1.,1.));old=frame.iloc[[0]].copy();old.index-=pd.Timedelta(hours=2)
    frame=pd.concat([old,frame]);quality=v.inspect_path(c,frame,[])
    assert quality['last_positive_volume_bar_before_entry']==c['entry_ts']-7200
    assert quality['hours_since_last_positive_volume_bar_close']==pytest.approx(115/60)


def test_known_close_only_boundary_and_automatic_settlement():
    c,frame=data();event={'symbol':'TESTUSDT','known_from_utc':'2024-12-30T00:00Z','entry_close_only_from':'2025-01-01T00:00Z','settlement_at':'2025-01-01T00:10Z','source_url':'https://www.binance.com/test'}
    kinds={x['kind'] for x in v.inspect_path(c,frame,[event])['official_lifecycle_flags']}
    assert kinds=={'entry_after_announced_new_position_cutoff','position_path_crosses_automatic_settlement'}


def test_unpublished_or_other_contract_event_does_not_block_entry():
    c,frame=data();event={'symbol':'TESTUSDT','known_from_utc':'2025-01-02T00:00Z','entry_close_only_from':'2025-01-01T00:00Z','settlement_at':'2025-01-01T00:10Z','source_url':'https://www.binance.com/test'}
    assert v.inspect_path(c,frame,[event])['official_lifecycle_flags']==[]
    event.update(known_from_utc='2024-12-30T00:00Z',symbol='OTHERUSDT')
    assert v.inspect_path(c,frame,[event])['official_lifecycle_flags']==[]


def test_stop_exit_before_nominal_horizon_is_not_truncated():
    c,frame=data(reason='stop');assert not v.inspect_path(c,frame,[])['horizon_truncated']


def test_annual_entry_embargo_boundary():
    t=int(pd.Timestamp('2025-12-27T00:00Z').timestamp())
    assert v.annual_eligible({'entry_ts':t-1})
    assert not v.annual_eligible({'entry_ts':t})


def test_cached_context_matches_uncached_audit():
    c,frame=data();ts=v.r.epoch_seconds(frame.index);vol=frame.volume.to_numpy()
    assert v.inspect_path(c,frame,[])==v.inspect_path(c,frame,[],(ts,vol,ts[vol>0]))


def test_separate_timestamp_grid_verifier_matches_gap_and_zero_diagnostics():
    c,frame=data(volumes=(0.,0.),minutes=(0,10))
    assert v.inspect_path(c,frame,[])==independent.independent_quality(c,frame,[])
