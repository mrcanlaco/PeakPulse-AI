import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from shock_five_minute_entry import transform,MODES
from shock_five_minute_oracle import expected


def fixture(side='LONG',path=None):
    path=path or [100,99.7,99.3,99.,99.3,100.3,100,100,100,100,100,100]
    path=np.array(path,dtype=float)
    if side=='SHORT':path=200-path
    q=SimpleNamespace(trade_times=np.arange(len(path))*300000-300000,closes=path)
    e=dict(at=0,symbol='X',side=side,atr=1.,probability=2.,event_id='event')
    return [e],{'X':q}


@pytest.mark.parametrize('side',['LONG','SHORT'])
@pytest.mark.parametrize('mode',list(MODES))
def test_first_passage_and_retest_match_independent_oracle(side,mode):
    es,qs=fixture(side);actual,counts,records=transform(es,qs,mode)
    assert actual==expected(es,qs,mode) and counts=={'emitted':1}
    if mode=='immediate':assert actual==es
    else:
        at={'pull25':300000,'pull50':600000,'retest50':1200000,'break25':1500000}[mode]
        assert actual[0]['at']==at and actual[0]['source_at']==0
        assert all(actual[0][k]==es[0][k] for k in ['atr','probability','event_id','side'])


def test_no_fill_at_minute_sixty_or_intrabarlows():
    es,qs=fixture(path=[100]*12+[98])
    actual,counts,_=transform(es,qs,'pull50')
    assert not actual and counts=={'expired':1}


def test_retest_requires_distinct_closed_bar_and_remains_below_origin():
    es,qs=fixture(path=[100,99.,100.2]+[100.2]*9)
    actual,counts,_=transform(es,qs,'retest50')
    assert not actual and counts=={'expired':1}


def test_missing_bar_is_data_error_not_a_favorable_fill():
    es,qs=fixture();q=qs['X'];q.trade_times=np.delete(q.trade_times,1);q.closes=np.delete(q.closes,1)
    actual,counts,_=transform(es,qs,'pull50')
    assert not actual and counts=={'data_error':1}


def test_truncated_or_asof_observation_is_pending_and_causal():
    es,qs=fixture()
    actual,counts,_=transform(es,qs,'retest50',asof=900000)
    assert not actual and counts=={'right_censored':1}
    actual,counts,_=transform(es,qs,'retest50',asof=1200000)
    assert actual[0]['at']==1200000 and counts=={'emitted':1}
    qs['X'].closes[5:]=150
    assert transform(es,qs,'retest50',asof=1200000)[0]==actual


def test_invalid_mode_and_origin_do_not_silently_disappear():
    es,qs=fixture()
    with pytest.raises(ValueError):transform(es,qs,'unknown')
    qs['X'].closes[0]=np.nan
    with pytest.raises(ValueError,match='missing_origin'):transform(es,qs,'pull50')
