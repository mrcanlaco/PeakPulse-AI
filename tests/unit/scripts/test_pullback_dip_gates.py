import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from pullback_dip_gates import states,filtered,decision,GATES
from pullback_dip_oracle import expected


def fixture():
    t=pd.date_range('2025-01-01',periods=700,freq='1h',tz='UTC')
    p=100*np.exp(np.arange(700)*.0003+.045*np.sin(np.arange(700)/14))
    frame=pd.DataFrame(dict(open=p,high=p*1.002,low=p*.998,close=p,quote_volume=1e6),index=t)
    events=[dict(symbol='X',event_id=str(i)+side,at=int(t[i].value//1000000),side=side,atr=2,probability=.5) for i in range(360,650,5) for side in ['LONG','SHORT']]
    return {'X':frame},events


def test_oracle_and_shallow_deep_partition_cover_only_countertrend():
    f,e=fixture();s=states(f);oracle=expected(e,f)
    for gate in GATES:assert filtered(e,s,gate)[0]==oracle[gate]
    ids=lambda g:{x['event_id'] for x in oracle[g]}
    assert ids('dip24_shallow').isdisjoint(ids('dip24_deep'))
    assert ids('dip24_shallow')|ids('dip24_deep')==ids('counter24')
    for gate in GATES[1:]:assert oracle[gate]


@pytest.mark.parametrize('side',['LONG','SHORT'])
@pytest.mark.parametrize('distance',[0,1,2,2.001])
def test_signed_thresholds_and_exact_two_atr_boundary(side,distance):
    d=1 if side=='LONG' else -1;close=100-d*distance*2
    row=dict(close=close,close24=100,ret24=np.log(close/100),ready24=True)
    assert (decision(side,row,'dip24_shallow',2)=='accepted')==(0<distance<=2)
    assert (decision(side,row,'dip24_deep',2)=='accepted')==(distance>2)
    assert (decision(side,row,'counter24',2)=='accepted')==(distance>0)


@pytest.mark.parametrize('hour',[500,501,502,503])
def test_prefixes_exclude_unclosed_four_hour_candle(hour):
    f,e=fixture();t=f['X'].index[hour];events=[x for x in e if x['at']<=t.value//1000000]
    full=states(f);prefix=states({'X':f['X'].loc[:t]})
    altered=f['X'].copy();altered.loc[altered.index>t,'close']=1e8
    changed=states({'X':altered})
    for g in GATES:assert filtered(events,full,g)==filtered(events,prefix,g)==filtered(events,changed,g)


def test_missing_hours_or_invalid_atr_cannot_be_favorable_assumptions():
    f,e=fixture();event=e[0];t=pd.Timestamp(event['at'],unit='ms',tz='UTC')
    f['X']=f['X'].drop(t-pd.Timedelta(hours=1));s=states(f)
    for g in ['counter24','counter72','dip24_shallow','dip24_deep']:assert filtered([event],s,g)[1]=={'missing_state':1}
    for g in GATES:assert filtered(e,s,g)[0]==expected(e,f)[g]
    row=dict(close=98,close24=100,ret24=np.log(.98),ready24=True)
    for a in [0,-1,float('nan')]:assert decision('LONG',row,'dip24_shallow',a)=='missing_state'


def test_ema_requires_main_direction_but_price_on_opposite_side():
    row=dict(close=99,ema20=100,ema60=90,ema_ready=True)
    assert decision('LONG',row,'ema_pullback',2)=='accepted'
    assert decision('SHORT',row,'ema_pullback',2)=='dip_disagrees'
    row.update(close=101,ema60=110)
    assert decision('SHORT',row,'ema_pullback',2)=='accepted'
    row['close']=100
    assert decision('SHORT',row,'ema_pullback',2)=='dip_disagrees'
