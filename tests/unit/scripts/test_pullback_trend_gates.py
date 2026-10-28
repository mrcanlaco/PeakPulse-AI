import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from pullback_trend_gates import states,decision,filtered,GATES
from pullback_trend_oracle import expected


def fixture(direction=1):
    t=pd.date_range('2025-01-01',periods=600,freq='1h',tz='UTC');p=100*np.exp(direction*np.arange(600)*.001)
    f=pd.DataFrame(dict(open=p,high=p*1.002,low=p*.998,close=p,quote_volume=1e6),index=t)
    events=[dict(symbol='X',event_id=str(i)+side,at=int(t[i].value//1000000),side=side,atr=2,probability=.5) for i in [400,401,402,403,404,500] for side in ['LONG','SHORT']]
    return {'X':f},events


@pytest.mark.parametrize('direction',[1,-1])
def test_both_sides_mirror_and_oracle_agrees(direction):
    frames,events=fixture(direction);state=states(frames);oracle=expected(events,frames)
    for gate in GATES:
        actual=filtered(events,state,gate)[0];assert actual==oracle[gate]
        if gate!='none':assert len(actual)==6 and all(e['side']==('LONG' if direction==1 else 'SHORT') for e in actual)


@pytest.mark.parametrize('hour',[400,401,402,403])
def test_future_partial_four_hour_candles_cannot_change_decisions(hour):
    frames,events=fixture();cut=frames['X'].index[hour];old=states(frames)
    prefix=states({'X':frames['X'].loc[:cut]})
    limited=[e for e in events if e['at']<=cut.value//1000000]
    for gate in GATES:assert filtered(limited,old,gate)==filtered(limited,prefix,gate)
    changed=frames['X'].copy();changed.loc[changed.index>cut,'close']=1e10
    for gate in GATES:assert filtered(limited,old,gate)==filtered(limited,states({'X':changed}),gate)


def test_missing_hour_rejects_required_window_without_filling():
    frames,events=fixture();t=frames['X'].index[400]
    frames['X']=frames['X'].drop(frames['X'].index[399]);state=states(frames)
    e=[x for x in events if x['at']==t.value//1000000 and x['side']=='LONG']
    for gate in ['ret24','ret72','trend_ret24','persistence5']:
        assert filtered(e,state,gate)[1]=={'missing_state':1}
    assert filtered(e,state,'none')[0]==e
    for gate in GATES:assert filtered(events,state,gate)[0]==expected(events,frames)[gate]


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_zero_trend_does_not_pass(side):
    row=dict(ready24=True,ready72=True,ready168=True,ema_ready=True,close=100,ema20=100,ema60=100,ret24=0,ret72=0,positive_days=0,negative_days=0)
    for gate in GATES[1:]:assert decision(side,row,gate)=='trend_disagrees'


def test_first_trigger_is_discarded_not_delayed_or_relabelled():
    frames,events=fixture();long=[e for e in events if e['side']=='LONG'];short=[e for e in events if e['side']=='SHORT']
    actual=filtered(long+short,states(frames),'ret24')[0]
    assert actual==long
    assert all(a is b for a,b in zip(actual,long))
