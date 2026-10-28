import sys
from pathlib import Path
import pandas as pd
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from momentum_entry_timing import transform,HOUR
from momentum_timing_audit import expected


def fixture(side='LONG',prices=None):
    values=prices or [100]*24
    f=pd.DataFrame({'close':values},index=pd.to_datetime(np.arange(len(values))*HOUR,unit='ms',utc=True))
    return [dict(symbol='X',event_id='x',side=side,at=0,atr=2,probability=.5)],{'X':f}


@pytest.mark.parametrize('side,values',[('LONG',[100,99,99.6]),('SHORT',[100,101,100.4])])
def test_retest_needs_distinct_recovery_close(side,values):
    source,frames=fixture(side,values);events,c,r=transform(source,frames,'retest05')
    assert c=={'emitted':1} and events[0]['at']==2*HOUR
    assert events[0]['atr']==2 and events[0]['event_id']=='x' and events[0]['source_at']==0
    assert r[0]['favorable_atr']==pytest.approx(.2)


@pytest.mark.parametrize('mode,side,value',[('pull05','LONG',99),('pull05','SHORT',101),('break05','LONG',101),('break05','SHORT',99)])
def test_first_touch_only_uses_closed_price(mode,side,value):
    source,frames=fixture(side,[100,value,200]);events,c,_=transform(source,frames,mode)
    assert events[0]['at']==HOUR and c=={'emitted':1}
    frames['X'].iloc[-1,0]=1
    assert transform(source,frames,mode)[0]==events


def test_retest_does_not_chase_above_reference_and_uses_new_extreme():
    source,frames=fixture(prices=[100,99,98,98.3,100.2,99.9]);events,_,_=transform(source,frames,'retest05')
    assert events[0]['at']==5*HOUR


def test_expiration_before_next_daily_signal():
    source,frames=fixture(prices=[100]*24+[90]);events,c,_=transform(source,frames,'pull1')
    assert not events and c=={'expired':1}


def test_internal_missing_data_is_not_silently_skipped():
    source,frames=fixture(prices=[100,float('nan'),98]);events,c,_=transform(source,frames,'pull1')
    assert not events and c=={'data_error':1}


def test_prefix_emissions_stable_and_unfinished_wait_not_expired():
    source,frames=fixture(prices=[100,100,99,99.6]);full=transform(source,frames,'retest05')[0]
    early=transform(source,{'X':frames['X'].iloc[:3]},'retest05')
    assert early[0]==[e for e in full if e['at']<=2*HOUR] and early[1]=={'right_censored':1}


def test_immediate_exact_and_keeps_source_immutable():
    source,frames=fixture();events,c,r=transform(source,frames,'immediate')
    assert events==source and events[0] is not source[0] and c=={'emitted':1} and r==[]


@pytest.mark.parametrize('side',['LONG','SHORT'])
@pytest.mark.parametrize('mode',['immediate','pull05','pull1','retest05','retest1','break05','break1'])
def test_vector_oracle_agrees_on_first_passage_for_both_sides(side,mode):
    move=np.array([0,-.4,-1.1,-2.2,-2,-1.6,.3,1.1,2.3]+[0]*15)
    source,frames=fixture(side,(100+(move if side=='LONG' else -move)).tolist())
    assert transform(source,frames,mode)[0]==expected(source,frames,mode)
