from pathlib import Path
import copy
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
import research_v410 as v


def candles(n=700):
    times=pd.date_range('2024-01-01',periods=n,freq='5min',tz='UTC')
    close=100*np.exp(-np.arange(n)*.0001)
    return pd.DataFrame({'open':close,'high':close*1.001,'low':close*.999,'close':close},index=times)


def test_features_ignore_future_bars_and_require_closed_candles():
    frame=candles();decision=int(frame.index[400].timestamp())
    base=v.feature_frame(frame,[decision])
    changed=frame.copy();changed.loc[changed.index>=pd.Timestamp(decision,unit='s',tz='UTC'),'close']*=100
    pd.testing.assert_frame_equal(base,v.feature_frame(changed,[decision]))
    assert base.iloc[0].momentum==pytest.approx(-288*.0001)
    assert base.iloc[0].volatility==pytest.approx(np.sqrt(288)*.0001)


def test_past_gap_cannot_be_hidden_by_rolling_row_count():
    frame=candles();decision=int(frame.index[400].timestamp())
    assert v.feature_frame(frame.drop(frame.index[200]),[decision]).empty


def test_future_gap_does_not_change_match_features_but_invalidates_outcome():
    frame=candles();decision=int(frame.index[350].timestamp());entry=decision+300
    damaged=frame.drop(frame.index[500])
    pd.testing.assert_frame_equal(v.feature_frame(frame,[decision]),v.feature_frame(damaged,[decision]))
    assert v.fixed_horizon_prices(frame,entry)['status']=='COMPLETE'
    assert v.fixed_horizon_prices(damaged,entry)['status']=='NOT_EVALUABLE'


@pytest.mark.parametrize('offset',[0,287])
def test_entry_and_final_execution_candle_are_required(offset):
    frame=candles();entry=int(frame.index[350].timestamp())
    assert v.fixed_horizon_prices(frame.drop(frame.index[350+offset]),entry)['status']=='NOT_EVALUABLE'


def test_fixed_horizon_excludes_following_candle():
    frame=candles();entry=int(frame.index[350].timestamp())
    outcome=v.fixed_horizon_prices(frame,entry)
    assert outcome['entry_reference']==frame.iloc[350]['open']
    assert outcome['exit_reference']==frame.iloc[637]['close']
    assert outcome['exit_ts_ms']==(entry+86400)*1000


def event(t,tf='4h',wave='a',score=70):
    return {'id':f'S:{t}:{tf}','entry_ts':t,'decision_ts':t-300,'symbol':'S','tf':tf,'wave_key':wave,'score':score,'milestones':['m6_f4_elite_sniper']}


def test_sampling_has_symbol_wide_24h_cooldown_and_does_not_read_exit_path():
    t=int(pd.Timestamp('2024-01-01 00:05',tz='UTC').timestamp())
    rows=[event(t),event(t+3600,'1d','b'),event(t+86400,'1d','c'),event(t+2*86400,'4h','a')]
    selected,_,_=v.sample_events(rows)
    assert [p['entry_ts'] for p in selected]==[t,t+86400]
    altered=copy.deepcopy(rows)
    for p in altered:p['paths']={'ladder':{'exit_ts':0,'gross_return':1e9}}
    assert v.sample_events(altered)[0]==selected


def pool():
    return [{'symbol':s,'momentum':m,'volatility':w} for s,m,w in [('A',-.01,.02),('B',-.02,.03),('C',-.03,.04),('D',-.04,.05)]]


def test_matching_caliper_and_negative_momentum_are_hard_constraints():
    assert v.choose_control({'momentum':.01,'volatility':.03},pool())[1]=='treated_nonnegative_momentum'
    assert v.choose_control({'momentum':-.1,'volatility':.03},pool())[1]=='outside_fixed_caliper'
    assert v.choose_control({'momentum':-.02,'volatility':.03},pool()[:2])[1]=='fewer_than_three_negative_controls'
    chosen,reason=v.choose_control({'momentum':-.02,'volatility':.03},pool())
    assert reason is None and chosen['control']['symbol']=='B'


def test_equal_match_distance_uses_symbol_not_input_order_or_outcome():
    values=pool()+[{'symbol':'AA','momentum':-.02,'volatility':.03,'future_return':-999}]
    chosen,_=v.choose_control({'momentum':-.02,'volatility':.03},list(reversed(values)))
    assert chosen['control']['symbol']=='AA'


@pytest.mark.parametrize('scenario,expected', [('standard_vip6',-.0025),('stress_regular',-.011)])
def test_flat_roundtrip_is_per_fill_on_actual_execution_notional(scenario,expected):
    p={'entry_reference':100.,'exit_reference':100.,'entry_ts_ms':1000,'exit_ts_ms':10000}
    result=v.unit_outcome(p,[],v.x.SCENARIOS[scenario])
    assert result['net_return']==pytest.approx(expected)
    assert sum(f['qty'] for f in result['fills'])==pytest.approx(.02)


def test_signed_funding_uses_actual_mark_and_exact_event_boundaries():
    p={'entry_reference':100.,'exit_reference':80.,'entry_ts_ms':1000,'exit_ts_ms':10000}
    events=[{'funding_ts_ms':t,'funding_rate':rate,'mark_price':mark,'price_source':'funding_api_settlement_mark'}
        for t,rate,mark in [(1000,1.,100.),(1001,.001,90.),(9999,-.002,110.),(10000,.001,80.),(10001,1.,100.)]]
    result=v.unit_outcome(p,events,{'fee_bps':0.,'slippage_bps':0.})
    assert result['funding']==pytest.approx(.0009-.0022+.0008)
    assert result['net_return']==pytest.approx(.2-.0005)
    assert len(result['funding_events'])==3


def test_bootstrap_keeps_pairs_together_and_weights_events_not_week_means():
    def row(t,a):return {'entry_ts':int(pd.Timestamp(t,tz='UTC').timestamp()),'treated':{'net_return':a},'control':{'net_return':a-.001}}
    rows=[row('2024-01-02',.01),row('2024-01-02',.02),row('2024-02-06',.03)]
    stat=v.paired_statistics(rows,'2024-01-01','2025-01-01',samples=200)
    assert stat['mean_fibo_bps']==pytest.approx(200)
    assert stat['mean_difference_bps']==pytest.approx(10)
    assert stat['paired_difference_ci95_bps']==pytest.approx([10,10])
    assert stat['calendar_weeks']==53 and stat['active_weeks']==2
