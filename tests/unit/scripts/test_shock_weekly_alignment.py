import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
from shock_weekly_alignment import GATES, classify, filtered


def setup(rank=.9, raw=.1, eligible=True):
    days = pd.date_range('2026-03-01', periods=3, freq='D', tz='UTC')
    state = {'X': pd.DataFrame(dict(eligible=[eligible]*3, raw168=[raw]*3,
        coverage=[30]*3, pool_ready=[True]*3, percentile=[rank]*3), index=days)}
    at = int((days[1] + pd.Timedelta(hours=11)).timestamp()*1000)
    event = dict(event_id='x', symbol='X', side='LONG', at=at, atr=1., probability=1.)
    return event, state


@pytest.mark.parametrize('rank,raw,partition',[(.9,.1,'aligned'),(.1,-.1,'opposed'),(.5,.1,'neutral')])
def test_partition_and_asof(rank,raw,partition):
    event,state=setup(rank,raw)
    assert classify(event,state)['snapshot_at']==int(pd.Timestamp('2026-03-02',tz='UTC').timestamp()*1000)
    assert [g for g in ['aligned','opposed','neutral'] if filtered([event],state,g)[0]]==[partition]
    # A later daily snapshot must not affect the 11:00 signal.
    before={g:filtered([event],state,g) for g in GATES}
    state['X'].iloc[2,state['X'].columns.get_loc('raw168')]=-999
    state['X'].iloc[2,state['X'].columns.get_loc('percentile')]=0
    assert {g:filtered([event],state,g) for g in GATES}==before


def test_rank_ineligible_is_not_neutral():
    event,state=setup(eligible=False)
    assert filtered([event],state,'none')[0]==[event]
    for gate in GATES[1:]:
        accepted,counts,_=filtered([event],state,gate)
        assert accepted==[] and counts=={'ineligible':1}


def test_missing_daily_snapshot_cannot_pass_ranked_gate():
    event,state=setup()
    state['X']=state['X'].drop(pd.Timestamp('2026-03-02',tz='UTC'))
    for gate in GATES[1:]:
        accepted,counts,_=filtered([event],state,gate)
        assert accepted==[] and counts=={'missing_state':1}


def test_short_alignment_uses_low_rank_and_negative_return():
    event,state=setup(rank=.1,raw=-.1)
    event['side']='SHORT'
    assert filtered([event],state,'aligned')[0]==[event]
    assert filtered([event],state,'sign')[0]==[event]
    assert not filtered([event],state,'opposed')[0]
