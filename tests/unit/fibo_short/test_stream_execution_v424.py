import copy
import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
from stream_execution_v424 import SequentialPortfolio, BAR_MS, HOUR_MS

T = 1704067500000
END = T+40*24*HOUR_MS
SCENARIOS = {'standard':{'fee_bps':2.5,'slippage_bps':10.}, 'stress':{'fee_bps':5.,'slippage_bps':50.}}


def candidate(symbol='A',t=T,**overrides):
    result = {'id':f'{symbol}:{t}','symbol':symbol,'tf':'4h','wave_key':'wave',
        'decision_ts_ms':t-BAR_MS,'entry_ts_ms':t,'entry':100.,'stop':110.,
        'targets':[90.,80.,70.],'score':70.,
        'milestones':['m6_f4_expanded','m6_f4_sniper','m6_f4_elite_sniper']}
    result.update(overrides)
    return result


def engine(cost='standard',**policy):
    return SequentialPortfolio(T-BAR_MS,END,{'gate':'expanded','sizing':'fixed',**policy},
        SCENARIOS[cost] if isinstance(cost,str) else cost)


def bar(t,o=100.,high=105.,low=95.,close=100.,volume=1.):
    return {'open_time_ms':t-BAR_MS,'open':o,'high':high,'low':low,'close':close,'volume':volume}


def event(t,rate=.001,mark=100.):
    return {'funding_ts_ms':t,'funding_rate':rate,'mark_price':mark,
        'price_source':'funding_api_settlement_mark','mark_reference_ts_ms':t}


def advance(e,t,**kwargs):
    e.process(t,funding_complete_through_ms=t,**kwargs)


def finish(e):
    advance(e,END)
    return e.finish()


@pytest.mark.parametrize('name,loss',[('standard',.05),('stress',.22)])
def test_flat_horizon_roundtrip_costs_each_fill(name,loss):
    e=engine(name,hours=24)
    advance(e,T,entries=[candidate(targets=[10.,5.,1.])])
    for i in range(1,289): advance(e,T+i*BAR_MS,bars={'A':bar(T+i*BAR_MS)})
    result=finish(e)
    assert result['metric']['return_pct']==pytest.approx(-loss)
    assert result['ledger'][0]['exit_reason']=='horizon24'


def test_fixed_quantity_round_trip_price_does_not_rebalance_open_trade():
    e=engine({'fee_bps':10.,'slippage_bps':0.},hours=24)
    advance(e,T,entries=[candidate(targets=[10.,5.,1.])])
    advance(e,T+BAR_MS,bars={'A':bar(T+BAR_MS,high=100.,low=50.,close=50.)})
    assert e.positions[candidate()['id']]['qty']==pytest.approx(.2)
    assert e.equity==pytest.approx(109.98)
    for i in range(2,289): advance(e,T+i*BAR_MS,bars={'A':bar(T+i*BAR_MS)})
    assert finish(e)['curve'][-1][1]==pytest.approx(99.96)


def test_partial_exits_funding_and_json_restart_are_equivalent():
    e=engine();advance(e,T,entries=[candidate()])
    advance(e,T+BAR_MS,bars={'A':bar(T+BAR_MS,close=95.)})
    advance(e,T+2*BAR_MS,bars={'A':bar(T+2*BAR_MS,95.,96.,89.,89.)},funding=[('A',event(T+2*BAR_MS))])
    restart=SequentialPortfolio.restore(json.loads(json.dumps(e.state())))
    for obj in (e,restart):
        advance(obj,T+3*BAR_MS,bars={'A':bar(T+3*BAR_MS,89.,89.,79.,79.)},funding=[('A',event(T+3*BAR_MS,-.002,90.))])
        advance(obj,T+4*BAR_MS,bars={'A':bar(T+4*BAR_MS,79.,79.,69.,75.)},funding=[('A',event(T+4*BAR_MS,.003,80.))])
    a,b=finish(e),finish(restart)
    assert a==b
    p=a['ledger'][0]
    assert [f['qty'] for f in p['fills']]==pytest.approx([.2,.1,.06,.04])
    assert [f['remaining_qty'] for f in p['funding_events']]==pytest.approx([.2,.1,.04])
    assert p['funding']==pytest.approx(.02-.018+.0096)
    assert p['gross_reference_return']==pytest.approx(.17)
    assert p['fees']==pytest.approx((19.98+9.009+4.8048+2.8028)*.00025)


def test_stop_first_and_gap_stop_fill():
    e=engine();advance(e,T,entries=[candidate()])
    advance(e,T+BAR_MS,bars={'A':bar(T+BAR_MS,120.,130.,60.,100.)})
    p=finish(e)['ledger'][0]
    assert p['exit_reason']=='stop'
    assert p['fills'][1]['reference_price']==pytest.approx(120.)
    assert p['gross_reference_return']==pytest.approx(-.2)


def test_same_bar_partial_then_ratchet_preserves_total_turnover():
    e=engine();advance(e,T,entries=[candidate()])
    advance(e,T+BAR_MS,bars={'A':bar(T+BAR_MS,100.,105.,85.,95.)})
    p=finish(e)['ledger'][0]
    assert p['exit_reason']=='ratchet'
    assert p['fills'][1]['reference_price']==pytest.approx(95.)
    assert p['fills'][1]['qty']==pytest.approx(.2)


def test_same_timestamp_max_five_and_rejected_wave_not_consumed():
    e=engine({'fee_bps':0.,'slippage_bps':0.})
    advance(e,T,entries=[candidate(s) for s in 'ABCDEF'])
    assert len(e.positions)==5 and e.rejected['portfolio_cap']==1
    advance(e,T+BAR_MS,bars={s:bar(T+BAR_MS,high=115.) for s in 'ABCDE'},entries=[candidate('F',T+BAR_MS)])
    assert [p['symbol'] for p in e.positions.values()]==['F']
    advance(e,T+2*BAR_MS,bars={'F':bar(T+2*BAR_MS,high=115.)})
    assert finish(e)['metric']['trades']==6


def test_actual_close_controls_cooldown_without_known_exit_time():
    e=engine({'fee_bps':0.,'slippage_bps':0.})
    advance(e,T,entries=[candidate()])
    advance(e,T+BAR_MS,bars={'A':bar(T+BAR_MS,high=115.)})
    advance(e,T+2*BAR_MS,entries=[candidate(t=T+2*BAR_MS,wave_key='new')])
    assert not e.positions and e.rejected['wave_or_cooldown']==1
    advance(e,T+4*HOUR_MS,entries=[candidate(t=T+4*HOUR_MS,wave_key='new')])
    assert len(e.positions)==1


def test_funding_at_exit_precedes_exit_and_entry_funding_is_excluded():
    e=engine();advance(e,T,entries=[candidate()],funding=[('A',event(T))])
    advance(e,T+BAR_MS,bars={'A':bar(T+BAR_MS,high=115.)},funding=[('A',event(T+BAR_MS,.002))])
    advance(e,T+BAR_MS+1,funding=[('A',event(T+BAR_MS+1,.9))])
    p=finish(e)['ledger'][0]
    assert len(p['funding_events'])==1 and p['funding']==pytest.approx(.04)


def test_funding_changes_next_entry_size():
    objects=[engine(),engine()]
    for i,e in enumerate(objects):
        advance(e,T,entries=[candidate()])
        if i: advance(e,T+100,funding=[('A',event(T+100,.01))])
        advance(e,T+BAR_MS,bars={'A':bar(T+BAR_MS)},entries=[candidate('B',T+BAR_MS)])
    qty=[next(p['qty'] for p in e.positions.values() if p['symbol']=='B') for e in objects]
    assert qty[1]-qty[0]==pytest.approx(.0004)


@pytest.mark.parametrize('bad', ['paths','exit_ts_ms','gross_reference_return'])
def test_future_outcome_input_is_forbidden(bad):
    e=engine();before=e.state();c=candidate();c[bad]=0
    with pytest.raises(ValueError,match='future outcome'):
        advance(e,T,entries=[c])
    assert before==e.state()


def test_missing_bar_fails_before_mutating_state():
    e=engine();advance(e,T,entries=[candidate()]);before=e.state()
    with pytest.raises(ValueError,match='Missing required'):
        advance(e,T+2*BAR_MS,bars={'A':bar(T+2*BAR_MS)})
    assert e.state()==before


def test_missing_funding_completeness_is_not_zero_funding():
    e=engine()
    with pytest.raises(ValueError,match='Funding feed completeness'):
        e.process(T,entries=[candidate()])


def test_replayed_batch_after_restart_cannot_double_count_funding():
    e=engine();advance(e,T,entries=[candidate()]);advance(e,T+100,funding=[('A',event(T+100))])
    e=SequentialPortfolio.restore(json.loads(json.dumps(e.state())));before=e.state()
    with pytest.raises(ValueError,match='Timestamp must advance'):
        advance(e,T+100,funding=[('A',event(T+100))])
    assert e.state()==before


def test_unclosed_positions_cannot_be_force_finished_without_prices():
    e=engine();advance(e,T,entries=[candidate()])
    with pytest.raises(ValueError,match='Unclosed'):
        e.finish()


def test_zero_volume_exit_is_flagged_without_selecting_away_trade():
    e=engine();advance(e,T,entries=[candidate()])
    advance(e,T+BAR_MS,bars={'A':bar(T+BAR_MS,high=115.,volume=0.)})
    result=finish(e)
    assert result['metric']['trades']==1
    assert result['execution_issues'][0]['kind']=='zero_volume_exit'


@pytest.mark.parametrize('scenario',['standard','stress'])
def test_risk_sizing_budgets_both_entry_and_stop_execution_costs(scenario):
    e=engine(scenario,sizing='risk')
    advance(e,T,entries=[candidate()])
    p=next(iter(e.positions.values()))
    assert p['reference_notional']<=20
    assert p['stop_risk_with_execution_costs']==pytest.approx(.5)
    advance(e,T+BAR_MS,bars={'A':bar(T+BAR_MS,high=115.)})
    assert finish(e)['metric']['return_pct']==pytest.approx(-.5)


def test_funding_mark_from_the_future_is_rejected_atomically():
    e=engine();before=e.state();f=event(T);f['mark_reference_ts_ms']=T+1
    with pytest.raises(ValueError,match='Future funding mark'):
        advance(e,T,entries=[candidate()],funding=[('A',f)])
    assert e.state()==before
