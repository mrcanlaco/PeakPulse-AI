import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from hourly_shock_signals import prepare,generate
from hourly_shock_oracle import expected


def fixture():
    index=pd.date_range('2025-08-01',periods=200,freq='1h',tz='UTC')
    h=pd.DataFrame(dict(open=100.,high=100.1,low=99.9,close=100.,quote_volume=120000.),index=index)
    for i,body in [(80,.7),(82,-.7),(88,-.7),(100,.4),(140,.7),(152,-.7),(190,.7)]:
        h.iloc[i]=[100,100+max(body,0)+.01,100+min(body,0)-.01,100+body,720000]
    return {'X':h}


def test_matches_independent_first_shock_windows_and_six_hour_cooldown():
    frames=fixture();actual=generate(prepare(frames));oracle,_=expected(frames)
    for key,events in actual.items():
        assert [e['event_id'] for e in events]==[e['event_id'] for e in oracle[key]]
        for a,b in zip(events,oracle[key]):
            assert a['atr']==pytest.approx(b['atr']) and a['probability']==pytest.approx(b['probability'])
        assert len(events)>=3
        assert all(b['at']-a['at']>=21600000 for a,b in zip(events,events[1:]))
        assert int(frames['X'].index[82].timestamp()*1000) not in {e['at'] for e in events}


def test_follow_and_fade_share_times_atr_priority_but_opposite_sides():
    out=generate(prepare(fixture()))
    for tag in ['a15','a25']:
        for a,b in zip(out[f'shock_follow_{tag}'],out[f'shock_fade_{tag}']):
            assert a['side']!=b['side'] and a['event_id']!=b['event_id']
            assert all(a[k]==b[k] for k in ['symbol','at','atr','probability'])


def test_atr_and_relative_volume_exclude_current_shock():
    frames=fixture();h=frames['X'];t=h.index[80];f=prepare(frames)['X']
    assert f.loc[t,'atr']==pytest.approx(.2) and f.loc[t,'volume_ratio']==pytest.approx(6.)
    h.loc[t,['high','close']]=[120.01,120]
    changed=prepare(frames)['X']
    assert changed.loc[t,'atr']==f.loc[t,'atr']


@pytest.mark.parametrize('kind',['missing','nan','zero','invalid_high'])
def test_bad_recent_hour_blocks_entry(kind):
    frames=fixture();h=frames['X'];t=h.index[75];event=h.index[80]
    if kind=='missing':frames['X']=h.drop(t)
    elif kind=='nan':h.loc[t,'close']=np.nan
    elif kind=='zero':h.loc[t,'quote_volume']=0
    else:h.loc[t,'high']=99
    assert not prepare(frames)['X'].loc[event,'ready']


def test_wick_and_low_volume_reject_incomplete_shock():
    frames=fixture();h=frames['X'];t=h.index[80]
    h.loc[t,'high']=105
    assert int(t.timestamp()*1000) not in {e['at'] for e in generate(prepare(frames))['shock_follow_a15']}
    h.loc[t,'high']=100.71;h.loc[t,'quote_volume']=120000
    assert int(t.timestamp()*1000) not in {e['at'] for e in generate(prepare(frames))['shock_follow_a15']}


def test_future_data_does_not_change_past_and_mirror_is_symmetric():
    frames=fixture();h=frames['X'];t=h.index[142];full=generate(prepare(frames))
    prefix=generate(prepare({'X':h.loc[:t]}))
    for key in full:assert prefix[key]==[e for e in full[key] if e['at']<=int(t.timestamp()*1000)]
    mirror=h.copy();mirror['open']=200-h.open;mirror['close']=200-h.close;mirror['high']=200-h.low;mirror['low']=200-h.high
    out=generate(prepare({'X':mirror}))
    for key in full:
        assert len(full[key])==len(out[key])
        for a,b in zip(full[key],out[key]):
            assert a['at']==b['at'] and a['side']!=b['side']
            assert a['atr']==pytest.approx(b['atr'])


@pytest.mark.parametrize('side',['LONG','SHORT'])
@pytest.mark.parametrize('stop_wins',[False,True])
def test_combined_twelve_hour_exit_and_atr_stop_priority(side,stop_wins):
    from types import SimpleNamespace
    from account_capital_trace import simulate
    from atr_exit_audit import audit_exits
    from research_capacity_config import configuration
    times=list(range(0,12*3600000+1,300000));end=times[-1]
    direction=1 if side=='LONG' else -1
    points={t:dict(mark=100.,execution_close=100.,entry_open=100.) for t in times}
    points[end]=dict(mark=100-direction*(4 if stop_wins else 1),execution_close=100.,entry_open=100-direction*7)
    signal=dict(symbol='X',event_id='x',at=0,side=side,atr=2.)
    signals={0:[signal],end:[dict(signal,at=end,event_id='repeat')]}
    rule=dict(market_step='0.001',step_size='0.001',min_qty=.001,market_min_qty=.001,max_qty=100000,market_max_qty=100000,min_notional=5,tick_size='0.001')
    policy=dict(position_notional=25,entry_parts=3,entry_mode='favorable',entry_step_atr=.25,add_expiry_hours=6,trailing=True,activation_atr=3,callback_fraction=.01,observation_minutes=5,stop_atr=2,max_hold_hours=12)
    config=configuration(5,0,20);config.max_slippage_bps=0
    raw=simulate(times,signals,lambda _:points,{'X':rule},lambda _:[],config,research_policy=policy)
    exits=[j for j in raw['journal'] if 'net' in j]
    assert len(exits)==1 and exits[0]['at']==end and exits[0]['net']<0
    assert exits[0]['kind']==('atr_stop' if stop_wins else 'time_exit')
    assert exits[0]['price']==points[end]['entry_open'] and raw['entries']==1
    quotes=SimpleNamespace(trade_times=np.array(times)-300000,closes=np.array([points[t]['execution_close'] for t in times]),
        mark_times=np.array(times)-300000,marks=np.array([points[t]['mark'] for t in times]),get=points.get)
    assert audit_exits(raw,pd.DataFrame(raw['curve']),{'X':quotes},policy,{'x':signal},0,0)[0]==1
