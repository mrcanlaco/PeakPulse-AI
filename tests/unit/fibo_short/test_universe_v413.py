import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
import universe_audit_v413 as v
import verify_universe_v413 as verify


def frame(periods=12,start='2025-01-01',volume=1.):
    return pd.DataFrame({'open_time':pd.date_range(start,periods=periods,freq='5min',tz='UTC'),
        'open':100.,'high':101.,'low':99.,'close':100.,'volume':volume,'quote_volume':100*volume})


def test_bounded_parquet_read_excludes_2026_before_materialization(tmp_path):
    raw=frame(periods=3,start='2025-12-31 23:55');p=tmp_path/'TESTUSDT.parquet';raw.to_parquet(p,index=False)
    selected=v.bounded_read(p);assert len(selected)==1 and selected.open_time.max()<v.END
    with pytest.raises(ValueError):v.bounded_read(p,end='2026-01-02')


def test_identical_duplicates_merge_once_and_conflicts_visible():
    a=v.normalize(frame());b=a.copy();merged,comparisons=v.merge_frames([('first',a),('second',b)])
    assert len(merged)==12 and comparisons[0]['overlapping_rows']==12 and comparisons[0]['conflicting_rows']==0
    b.iloc[3,b.columns.get_loc('volume')]=2
    _,comparisons=v.merge_frames([('first',a),('conflict',b)])
    assert comparisons[0]['conflicting_rows']==1 and len(comparisons[0]['examples'])==1


def test_within_source_conflicting_duplicate_fails():
    raw=frame();bad=raw.iloc[[0]].copy();bad['close']=100.5
    with pytest.raises(ValueError,match='Conflicting'):v.normalize(pd.concat([raw,bad]))


@pytest.mark.parametrize('kind',['off_grid','nan','bad_ohlc','negative_volume','inconsistent_volume'])
def test_bad_input_fails(kind):
    raw=frame()
    if kind=='off_grid':raw.loc[0,'open_time']+=pd.Timedelta(milliseconds=1)
    if kind=='nan':raw.loc[0,'high']=np.nan
    if kind=='bad_ohlc':raw.loc[0,'low']=102.
    if kind=='negative_volume':raw.loc[0,'volume']=-1.
    if kind=='inconsistent_volume':raw.loc[0,'volume']=0.
    with pytest.raises(ValueError):v.normalize(raw)


def test_missing_bars_and_zero_volume_are_distinct_and_not_filled():
    raw=frame();raw.loc[2:4,['volume','quote_volume']]=0.;raw=raw.drop(index=8)
    normalized=v.normalize(raw);quality=v.quality(normalized)
    assert len(normalized)==11 and quality['missing_bars_inside_span']==1
    assert quality['zero_volume_rows']==3 and quality['maximum_zero_volume_run_bars']==3


def test_contract_identity_and_close_duration(tmp_path):
    raw=frame();raw['symbol']='OTHERUSDT';raw['close_time']=raw.open_time+pd.Timedelta(milliseconds=299999)
    p=tmp_path/'TESTUSDT.parquet';raw.to_parquet(p,index=False)
    with pytest.raises(AssertionError,match='symbol'):v.bounded_read(p,with_identity=True)
    raw['symbol']='TESTUSDT';raw['close_time']+=pd.Timedelta(milliseconds=1);raw.to_parquet(p,index=False)
    with pytest.raises(AssertionError,match='close time'):v.bounded_read(p,with_identity=True)


def test_independent_monthly_matches_and_future_prices_do_not_change_past_membership():
    raw=frame(periods=90*288,start='2024-11-01');norm=v.normalize(raw)
    production=v.r.monthly_rows('TESTUSDT',v.r.h1_frame(norm),v.MONTHS)
    independent=verify.independent_monthly('TESTUSDT',raw);verify.check_row(production,independent)
    changed=raw.copy();future=changed.open_time>=v.r.utc('2025-01-01')
    changed.loc[future,['high','volume','quote_volume']]*=100
    after=verify.independent_monthly('TESTUSDT',changed)
    assert after['2025-01']==independent['2025-01']
    assert '2024-12' not in independent  # Fewer than 50 active days.


def test_incomplete_hour_does_not_inflate_daily_volume_or_wick():
    raw=frame(periods=63*288,start='2024-10-30');raw=raw.drop(index=9)
    raw.loc[0,'quote_volume']=1e12
    p=v.r.monthly_rows('TESTUSDT',v.r.h1_frame(v.normalize(raw)),v.MONTHS)
    verify.check_row(p,verify.independent_monthly('TESTUSDT',raw))


def test_alphabetic_tie_ranking():
    rows=[{'2025-01':{'symbol':s,'median_quote_volume':1.,'active_days':63,'wick_p90_pct':1.}} for s in ['ZUSDT','AUSDT']]
    assert [x['symbol'] for x in v.rank(rows)['2025-01']]==['AUSDT','ZUSDT']
