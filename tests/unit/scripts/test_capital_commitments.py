import sys
from pathlib import Path
import copy
from types import SimpleNamespace
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from account_capital_trace import simulate
from account_net_trailing_replay import simulate as original
from capital_commitment_audit import audit
from research_capacity_config import configuration

RULE=dict(market_step='0.001',step_size='0.001',min_qty=.001,market_min_qty=.001,max_qty=100000,market_max_qty=100000,min_notional=5,tick_size='0.001')


def fixture(expire=False):
    times=[0,300000,6*3600000+300000,6*3600000+600000] if expire else [0,300000]
    points={t:dict(mark=100,execution_close=100,entry_open=100) for t in times}
    coins=[f'C{i}' for i in range(30)]
    events=[dict(symbol=c,event_id=c,at=0,side='LONG' if i%2 else 'SHORT',atr=2) for i,c in enumerate(coins)]
    signals={0:events}
    if expire:signals[times[2]]=[dict(e,event_id=e['event_id']+'later') for e in events[9:]]
    config=configuration(30,.0005,20)
    policy=dict(position_notional=250,entry_parts=3,entry_mode='favorable',entry_step_atr=.25,add_expiry_hours=6,trailing=True,activation_atr=3,callback_fraction=.01,observation_minutes=5)
    args=(times,signals,lambda _:points,{c:RULE for c in coins},lambda _:[],config)
    return args,policy,{c:SimpleNamespace(get=points.get) for c in coins}


@pytest.mark.parametrize('expire',[False,True])
def test_trace_preserves_financials_and_reconstructs_pending_reserves(expire):
    args,p,prices=fixture(expire);r=simulate(*args,research_policy=p)
    assert {k:v for k,v in r.items() if k!='capital_trace'}==original(*args,research_policy=p)
    assert sum(j['kind']=='entry' and j['at']==0 for j in r['journal'])==9
    checks,denied,cancels=audit(r,prices,.0005,250)
    assert checks>=30 and denied>0
    if expire:assert r['entries']>9 and cancels>=9
    else:assert r['entries']==9
    bad=copy.deepcopy(r);next(j for j in bad['capital_trace'] if j['kind']=='entry_check')['available']+=1
    with pytest.raises(AssertionError):audit(bad,prices,.0005,250)


def test_favorable_add_checks_remaining_parts_again():
    args,p,_=fixture();times=[0,300000,600000,900000]
    points={t:dict(mark=v,execution_close=v,entry_open=v) for t,v in zip(times,[100,101,102,102])}
    signals={0:[dict(symbol='X',event_id='X',side='LONG',atr=2)]}
    r=simulate(times,signals,lambda _:points,{'X':RULE},lambda _:[],args[-1],research_policy=p)
    assert sum(j['kind']=='entry_add' for j in r['journal'])==2
    assert audit(r,{'X':SimpleNamespace(get=points.get)},.0005,250)[0]==3
