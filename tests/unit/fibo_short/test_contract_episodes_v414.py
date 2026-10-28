from pathlib import Path
import sys
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
import contract_episodes_v414 as e


def event():
    return {'symbol':'TESTUSDT','known_from_utc':'2025-02-01T00:00Z','close_only_from':'2025-03-01T00:00Z',
        'settlement_at':'2025-03-01T00:30Z','relaunch_at':'2025-03-15T00:00Z'}


def frame():
    index=pd.date_range('2025-01-01','2025-06-01',freq='5min',inclusive='left',tz='UTC')
    return pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.,'volume':1.,'quote_volume':100.},index=index).rename_axis('open_time')


def test_inactive_interval_excluded_and_relaunch_included_without_rescaling():
    f=frame();f.loc[f.index>=pd.Timestamp(event()['relaunch_at']),'close']=90.
    parts=e.split_observed(f,event());old=parts[0][1];new=parts[1][1]
    assert old.index.max()==pd.Timestamp('2025-03-01T00:25Z')
    assert new.index.min()==pd.Timestamp('2025-03-15T00:00Z')
    assert new.close.eq(90).all() and old.close.eq(100).all()


def test_new_contract_cannot_borrow_old_contract_active_days():
    rows=e.episode_monthly(frame(),event())
    assert '2025-03' not in rows and '2025-04' not in rows and '2025-05' not in rows
    assert rows['2025-06']['active_days']==63


def test_cutoff_is_not_applied_before_announcement_is_known():
    a=event();a['known_from_utc']='2025-03-02T00:00Z'
    c={'entry_ts':int(pd.Timestamp('2025-03-01T00:00Z').timestamp()),'paths':{'ladder':{'exit_ts':int(pd.Timestamp('2025-03-01T01:00Z').timestamp())}}}
    state=e.candidate_state(c,a);assert not state['entry_blocked_by_known_event'] and not state['crosses_known_automatic_settlement']


def test_relaunched_contract_does_not_inherit_old_delisting_rejection():
    a=event();t=int(pd.Timestamp(a['relaunch_at']).timestamp());c={'entry_ts':t,'paths':{'ladder':{'exit_ts':t+3600}}}
    state=e.candidate_state(c,a)
    assert state['phase']=='relaunched' and not state['entry_blocked_by_known_event'] and state['requires_indicator_reset_comparison']


def test_position_spanning_settlement_is_retained_and_flagged():
    t=int(pd.Timestamp(event()['settlement_at']).timestamp());c={'entry_ts':t-300,'paths':{'ladder':{'exit_ts':t}}}
    assert e.candidate_state(c,event())['crosses_known_automatic_settlement']
    assert c['paths']['ladder']['exit_ts']==t


def test_data_after_2025_is_rejected():
    f=frame().iloc[:2].copy();f.index+=pd.Timedelta(days=365)
    with pytest.raises(ValueError,match='Forbidden'):e.split_observed(f,event())


def test_reversed_lifecycle_dates_are_rejected():
    a=event();a['relaunch_at']='2025-02-01T00:00Z'
    with pytest.raises(ValueError,match='out of order'):e.split_observed(frame(),a)


def test_official_registry_keeps_identity_changes_and_postponement():
    records={a['symbol']:a for a in e.records()}
    assert len(records)==10
    assert records['PUMPUSDT']['old_underlying']=='PumpBTC' and records['PUMPUSDT']['new_underlying']=='Pump.fun'
    assert records['LITUSDT']['old_underlying']=='Litentry' and records['LITUSDT']['new_underlying']=='Lighter Protocol'
    assert pd.Timestamp(records['MAVIAUSDT']['relaunch_at'])==pd.Timestamp('2025-03-26T17:00Z')
    assert records['CVCUSDT']['close_only_from'] is None
