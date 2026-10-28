import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from shock_weekly_direction import MODES,transform


def sample(raw=.1,rank=.9,eligible=True):
    t=pd.Timestamp('2026-04-03T00:00:00Z')
    state={'X':pd.DataFrame(dict(eligible=[eligible],raw168=[raw],coverage=[30],
                               pool_ready=[True],percentile=[rank]),index=[t])}
    event=dict(at=int((t+pd.Timedelta(hours=3)).timestamp()*1000),symbol='X',
               side='SHORT',atr=2.,probability=3.,event_id='frozen_shock')
    return event,state


@pytest.mark.parametrize('mode,side',[
    ('weekly_sign','LONG'),('anti_sign','SHORT'),
    ('weekly_extreme','LONG'),('anti_extreme','SHORT')])
def test_daily_direction_changes_only_the_side_and_id(mode,side):
    e,s=sample();out,counts,decisions=transform([e],s,mode)
    assert counts=={'accepted':1} and len(out)==1
    assert out[0]['side']==side and out[0]['event_id']!=e['event_id']
    assert out[0]['origin_event_id']==e['event_id']
    assert all(out[0][k]==e[k] for k in ['at','symbol','atr','probability'])
    assert decisions[0]['snapshot_at']<e['at']
    assert transform([e],s,mode)[0]==out


@pytest.mark.parametrize('mode',MODES)
def test_ineligible_coin_does_not_get_daily_direction(mode):
    e,s=sample(eligible=False)
    out,counts,_=transform([e],s,mode)
    assert out==[] and counts=={'ineligible':1}


def test_nonextreme_has_sign_but_no_extreme_direction():
    e,s=sample(rank=.5)
    assert transform([e],s,'weekly_sign')[0]
    assert transform([e],s,'anti_sign')[0]
    for mode in ['weekly_extreme','anti_extreme']:
        assert transform([e],s,mode)[1]=={'no_direction':1}


def test_future_daily_value_cannot_change_current_choice():
    e,s=sample()
    before={m:transform([e],s,m) for m in MODES}
    tomorrow=pd.Timestamp('2026-04-04T00:00:00Z')
    s['X'].loc[tomorrow]=[True,-1.,30,True,.1]
    assert {m:transform([e],s,m) for m in MODES}==before
