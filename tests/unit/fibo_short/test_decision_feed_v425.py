import copy
from pathlib import Path
import sys
import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
from decision_feed_v425 import DecisionFeed

T=pd.Timestamp('2025-01-15T12:00:00Z')
DUE=T+pd.Timedelta(minutes=5)


def snapshot():
    return {'symbol':'A','tf':'4h','decision_time':T.isoformat(),'wave_key':'w',
        'sl_m6':110.,'tp1':90.,'tp2':80.,'tp3':70.,'full_conviction_score':70.,
        'eligible_milestones':['m6_f4_expanded','m6_f4_sniper']}


def history():return pd.date_range(T-pd.Timedelta(hours=24),periods=24,freq='h')


def feed(events=(),membership=None):
    return DecisionFeed(membership or {'2025-01':[{'symbol':'A'}]},events,
        '2025-01-01T00:00:00Z','2026-01-01T00:00:00Z')


def quote(price=100.):return {'symbol':'A','open_time_ms':int(DUE.timestamp()*1000),'open':price}


def test_entry_uses_observed_open_not_signal_reference():
    f=feed();s=snapshot();s['entry_price']=103.
    cid=f.signal(s,as_of=T,past_hour_opens=history())
    result=f.entry_open(cid,as_of=DUE,quote=quote(100.))
    assert result['entry']==100. and result['decision_ts']+300==result['entry_ts']
    assert not f.pending


def test_future_month_membership_does_not_change_current_decision():
    first=feed(membership={'2025-01':[{'symbol':'A'}],'2025-02':[{'symbol':'B'}]})
    second=feed(membership={'2025-01':[{'symbol':'A'}],'2025-02':[]})
    assert first.signal(snapshot(),as_of=T,past_hour_opens=history())==second.signal(snapshot(),as_of=T,past_hour_opens=history())


def test_announced_closure_between_signal_and_entry_is_enforced_at_entry():
    event={'symbol':'A','known_from_utc':(T+pd.Timedelta(minutes=1)).isoformat(),
        'entry_close_only_from':(T+pd.Timedelta(minutes=3)).isoformat(),'settlement_at':(T+pd.Timedelta(hours=1)).isoformat()}
    f=feed([event]);cid=f.signal(snapshot(),as_of=T,past_hour_opens=history())
    assert cid is not None and f.entry_open(cid,as_of=DUE,quote=quote()) is None
    assert f.counts['known_close_only_or_settlement']==1


def test_future_announcement_cannot_remove_current_entry():
    event={'symbol':'A','known_from_utc':(DUE+pd.Timedelta(days=1)).isoformat(),
        'entry_close_only_from':T.isoformat(),'settlement_at':DUE.isoformat()}
    f=feed([event]);cid=f.signal(snapshot(),as_of=T,past_hour_opens=history())
    assert f.entry_open(cid,as_of=DUE,quote=quote()) is not None


def test_missing_quote_is_recorded_without_looking_for_later_fill():
    f=feed();cid=f.signal(snapshot(),as_of=T,past_hour_opens=history())
    assert f.entry_open(cid,as_of=DUE,quote=None) is None
    assert f.counts['missing_scheduled_entry_quote']==1 and not f.pending


def test_future_ohlc_in_entry_quote_is_rejected_without_consuming_pending():
    f=feed();cid=f.signal(snapshot(),as_of=T,past_hour_opens=history());q=quote();q['close']=80.
    with pytest.raises(ValueError,match='future OHLC'):f.entry_open(cid,as_of=DUE,quote=q)
    assert cid in f.pending


def test_gap_invalidated_ladder_is_not_an_entry():
    f=feed();cid=f.signal(snapshot(),as_of=T,past_hour_opens=history())
    assert f.entry_open(cid,as_of=DUE,quote=quote(111.)) is None
    assert f.counts['gap_invalidated_ladder']==1


def test_missing_or_future_past_hour_cannot_support_signal():
    f=feed()
    assert f.signal(snapshot(),as_of=T,past_hour_opens=history()[:-1]) is None
    g=feed()
    with pytest.raises(ValueError,match='Future or unclosed'):
        g.signal(snapshot(),as_of=T,past_hour_opens=history()+pd.Timedelta(hours=1))


def test_duplicate_signal_cannot_be_scheduled_twice():
    f=feed();f.signal(snapshot(),as_of=T,past_hour_opens=history())
    with pytest.raises(ValueError,match='Duplicate signal'):
        f.signal(snapshot(),as_of=T,past_hour_opens=history())


def test_every_year_has_the_same_five_day_entry_embargo():
    f=DecisionFeed({'2024-12':[{'symbol':'A'}]},[],'2020-01-01T00:00:00Z','2026-01-01T00:00:00Z')
    t=pd.Timestamp('2024-12-27T00:00:00Z');s=snapshot();s['decision_time']=t.isoformat()
    h=pd.date_range(t-pd.Timedelta(hours=24),periods=24,freq='h')
    assert f.signal(s,as_of=t,past_hour_opens=h) is None
    assert f.counts['outside_annual_entry_window']==1
