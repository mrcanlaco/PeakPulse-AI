import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from shock_range_gates import states,filtered,GATES
from shock_range_oracle import expected


def fixture(side='LONG'):
    ix=pd.date_range('2025-08-01',periods=101,freq='1h',tz='UTC')
    h=pd.DataFrame(dict(open=100.,high=110.,low=90.,close=100.,quote_volume=120000.),index=ix)
    t=ix[90];h.loc[t,['high','low','close']]=[115.,85.,112. if side=='LONG' else 88.]
    e=dict(at=int(t.timestamp()*1000),symbol='X',side=side,atr=2.,probability=2.,event_id='x')
    return [e],{'X':h},t


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_current_candle_excluded_and_direct_oracle(side):
    es,frames,t=fixture(side);s=states(frames);oracle=expected(es,frames)
    for gate in GATES:assert filtered(es,s,gate)[0]==oracle[gate]
    assert filtered(es,s,'break24')[0]==filtered(es,s,'break72')[0]==es
    assert s['X'].loc[t,'high24']==110 and s['X'].loc[t,'low24']==90


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_equal_boundary_is_nonbreak_and_partitions_are_exhaustive(side):
    es,frames,t=fixture(side);frames['X'].loc[t,'close']=110 if side=='LONG' else 90;s=states(frames)
    for n in [24,72]:
        assert not filtered(es,s,f'break{n}')[0]
        assert filtered(es,s,f'nonbreak{n}')[0]==es


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_old_extreme_only_changes_seventy_two_hour_classification(side):
    es,frames,t=fixture(side);frames['X'].loc[t-pd.Timedelta(hours=50),'high' if side=='LONG' else 'low']=120 if side=='LONG' else 80
    s=states(frames)
    assert filtered(es,s,'break24')[0]==es and filtered(es,s,'nonbreak72')[0]==es


@pytest.mark.parametrize('damage',['missing','nan','negative','malformed'])
def test_missing_or_invalid_prior_bar_is_not_classified_as_nonbreak(damage):
    es,frames,t=fixture();h=frames['X'];at=t-pd.Timedelta(hours=2)
    if damage=='missing':frames['X']=h.drop(at)
    elif damage=='nan':h.loc[at,'high']=np.nan
    elif damage=='negative':h.loc[at,'low']=-1
    else:h.loc[at,'high']=95
    s=states(frames)
    for gate in GATES[1:]:
        emitted,count,_=filtered(es,s,gate)
        assert not emitted and count=={'missing_state':1}


def test_future_mutation_does_not_change_prefix_or_frozen_events():
    es,frames,t=fixture();s=states(frames);prefix=states({'X':frames['X'].loc[:t]})
    pd.testing.assert_frame_equal(s['X'].loc[:t],prefix['X'])
    before=[dict(e) for e in es];frames['X'].loc[frames['X'].index>t,['high','low','close']]=[999,1,500]
    after=states(frames)
    for gate in GATES:assert filtered(es,s,gate)==filtered(es,after,gate)
    assert es==before
