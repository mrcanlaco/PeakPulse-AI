from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
import research_v415 as v


def event():
    return {'symbol':'TESTUSDT','known_from_utc':'2025-05-15T00:00Z','entry_close_only_from':'2025-05-21T08:30Z','settlement_at':'2025-05-21T09:00Z'}


def candidate(time):return {'symbol':'TESTUSDT','entry_ts':int(pd.Timestamp(time).timestamp())}


def test_monthly_membership_retains_pre_event_history_only():
    assert v.retain_month('2025-05',event())
    assert not v.retain_month('2025-06',event())


def test_unknown_future_announcement_cannot_remove_month():
    e=event();e['known_from_utc']='2025-06-02T00:00Z'
    assert v.retain_month('2025-06',e)


def test_entry_close_only_boundary_is_enforced_before_settlement():
    assert v.allowed_entry(candidate('2025-05-21T08:29:59Z'),[event()])
    assert not v.allowed_entry(candidate('2025-05-21T08:30Z'),[event()])


def test_relaunch_restores_entry_without_old_contract_block():
    e=event();e['relaunch_at']='2025-07-01T08:00Z'
    assert not v.allowed_entry(candidate('2025-07-01T07:59:59Z'),[e])
    assert v.allowed_entry(candidate('2025-07-01T08:00Z'),[e])


def test_unknown_close_only_falls_back_to_settlement_without_invented_time():
    e=event();e['entry_close_only_from']=None
    assert v.allowed_entry(candidate('2025-05-21T08:45Z'),[e])
    assert not v.allowed_entry(candidate('2025-05-21T09:00Z'),[e])


def test_unpublished_event_and_other_contract_do_not_reject():
    e=event();e['known_from_utc']='2025-05-22T00:00Z'
    assert v.allowed_entry(candidate('2025-05-21T09:00Z'),[e])
    e=event();e['symbol']='OTHERUSDT';assert v.allowed_entry(candidate('2025-05-21T09:00Z'),[e])
