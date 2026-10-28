import sys
from pathlib import Path
from types import SimpleNamespace
import copy
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from volatility_position_size import size_signals,financial_view
from account_volatility_replay import simulate
from account_capital_trace import simulate as previous
from volatility_capital_audit import audit
from research_capacity_config import configuration

RULE=dict(market_step='0.001',step_size='0.001',min_qty=.001,market_min_qty=.001,max_qty=100000,market_max_qty=100000,min_notional=5,tick_size='0.001')
POLICY=dict(position_notional=250,entry_parts=3,entry_mode='favorable',entry_step_atr=.25,add_expiry_hours=6,trailing=True,activation_atr=3,callback_fraction=.01,observation_minutes=5)


def test_size_uses_origin_price_and_atr_and_preserves_signal():
    events=[dict(symbol='A',event_id=str(i),reference_close=100,trigger_close=1,atr=a,side='LONG') for i,a in enumerate([.1,2,20])]
    old=copy.deepcopy(events);sized=size_signals(events,'atr_dollar',2.5)
    assert [e['planned_notional'] for e in sized]==[250,125,25]
    assert events==old
    changed=[dict(e,trigger_close=10000,side='SHORT') for e in events]
    assert [e['planned_notional'] for e in size_signals(changed,'atr_dollar',2.5)]==[250,125,25]
    assert size_signals(events[:1],'atr_dollar',2.5)==sized[:1]


@pytest.mark.parametrize('amount',[float('nan'),float('inf'),0,-1,251])
def test_bad_event_budget_fails_before_replay(amount):
    with pytest.raises(ValueError,match='invalid_event_notional'):
        simulate([0],{0:[dict(side='LONG',planned_notional=amount)]},None,None,None,configuration(5,.0005,20),research_policy=dict(POLICY,event_sizing=True))


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_constant_map_matches_frozen_engine_including_adds(side):
    times=[0,300000,600000,900000,22000000]
    values=[100,101,102,102,102] if side=='LONG' else [100,99,98,98,98]
    points={t:dict(mark=v,execution_close=v,entry_open=v) for t,v in zip(times,values)}
    events=[dict(symbol='X',event_id='X',side=side,atr=2,planned_notional=100)]
    args=(times,{0:events},lambda _:points,{'X':RULE},lambda _:[],configuration(5,.0005,20))
    r=simulate(*args,research_policy=dict(POLICY,event_sizing=True))
    control=previous(*args,research_policy=dict(POLICY,position_notional=100))
    assert financial_view(r)==control
    assert sum(j['kind']=='entry_add' for j in r['journal'])==2
    assert audit(r,{'X':SimpleNamespace(get=points.get)},.0005,{'X':100},rules={'X':RULE})[0]==3


def test_mixed_budgets_reserve_other_positions_and_freeze_add_size():
    times=[0,300000,600000,22000000]
    data={'A':{t:dict(mark=p,execution_close=p,entry_open=p) for t,p in zip(times,[100,101,102,102])},
          'B':{t:dict(mark=100,execution_close=100,entry_open=100) for t in times}}
    events=[dict(symbol=c,event_id=c,side='LONG',atr=2,planned_notional=b) for c,b in [('A',25),('B',250)]]
    r=simulate(times,{0:events},lambda c:data[c],{c:RULE for c in data},lambda _:[],configuration(5,.0005,20),research_policy=dict(POLICY,event_sizing=True))
    assert sum(j['qty']*j['price'] for j in r['journal'] if j['symbol']=='A' and j['kind'] in ['entry','entry_add'])<=25
    budgets={'A':25,'B':250};prices={c:SimpleNamespace(get=d.get) for c,d in data.items()}
    checks,_,cancels=audit(r,prices,.0005,budgets,rules={c:RULE for c in data})
    assert checks==4 and cancels==1
    second=r['capital_trace'][1]
    assert second['available']<495 # Includes both unfilled A tranches.
    bad=copy.deepcopy(r);bad['capital_trace'][1]['planned_notional']=25
    with pytest.raises(AssertionError):audit(bad,prices,.0005,budgets,rules={c:RULE for c in data})
