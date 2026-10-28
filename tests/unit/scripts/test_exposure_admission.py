import sys
from pathlib import Path
import copy
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from exposure_admission import permitted,audit
from account_exposure_replay import simulate
from account_net_trailing_replay import simulate as old
from research_capacity_config import configuration

RULE=dict(market_step='0.001',step_size='0.001',min_qty=.001,market_min_qty=.001,max_qty=100000,market_max_qty=100000,min_notional=5,tick_size='0.001')


@pytest.mark.parametrize('long,short,side,allowed',[(0,0,'LONG',True),(25,0,'LONG',False),(25,0,'SHORT',True),(0,25,'SHORT',False),(100,0,'SHORT',True),(100,0,'LONG',False),(0,100,'LONG',True),(12.5,0,'SHORT',True)])
def test_bound_and_repair(long,short,side,allowed):
    assert permitted(long,short,side,25,25)==allowed


def fixture(limit=25):
    times=[0,300000,600000]
    symbols=['A','B','C','D'];points={t:dict(mark=100,execution_close=100,entry_open=100) for t in times}
    signals={0:[dict(symbol=c,event_id=c,side=s,atr=2) for c,s in zip(symbols,['LONG','LONG','SHORT','LONG'])]}
    config=configuration(5,0,20);config.max_slippage_bps=0
    policy=dict(position_notional=25,entry_parts=3,entry_mode='favorable',entry_step_atr=.25,add_expiry_hours=6,trailing=True,activation_atr=3,callback_fraction=.01,observation_minutes=5)
    if limit is not None:policy['max_net_commitment']=limit
    args=(times,signals,lambda _:points,{c:RULE for c in symbols},lambda _:[],config)
    return args,policy,points


def test_pending_parts_count_and_opposite_signal_reopens_capacity():
    args,p,points=fixture();r=simulate(*args,research_policy=p)
    assert [j['symbol'] for j in r['journal'] if j['kind']=='entry']==['A','C','D']
    assert r['exposure_checks'][1]['LONG']>24 and r['exposure_checks'][1]['allowed'] is False
    from types import SimpleNamespace
    prices={c:SimpleNamespace(get=points.get) for c in ['A','B','C','D']}
    assert audit(r,prices,25,25)==(4,1)
    broken=copy.deepcopy(r);broken['exposure_checks'][1]['LONG']-=1
    with pytest.raises(AssertionError):audit(broken,prices,25,25)


def test_disabled_exact_legacy():
    args,p,_=fixture(None)
    assert simulate(*args,research_policy=p)==old(*args,research_policy=p)


@pytest.mark.parametrize('limit',[0,-1,float('nan'),True])
def test_invalid_limit(limit):
    args,p,_=fixture(limit)
    with pytest.raises(ValueError,match='invalid_exposure_limit'):simulate(*args,research_policy=p)


def test_failed_add_releases_commitment_without_closing_position():
    from types import SimpleNamespace
    args,p,_=fixture();times=[0,300000,600000]
    points={t:dict(mark=x,execution_close=x,entry_open=x) for t,x in zip(times,[2,3,3])}
    rules={c:dict(RULE,market_step='1',step_size='1',market_min_qty=4) for c in ['A','B']}
    signals={0:[dict(symbol='A',event_id='A',side='LONG',atr=2)],600000:[dict(symbol='B',event_id='B',side='SHORT',atr=2)]}
    r=simulate(times,signals,lambda _:points,rules,lambda _:[],args[-1],research_policy=p)
    cancel=next(j for j in r['journal'] if j['kind']=='adds_cancelled')
    assert cancel['at']==300000 and cancel['qty']==2 and cancel['reason']=='add_exchange_minimum_or_precision'
    assert len(r['open_positions'])==1 and r['open_positions'][0]['symbol']=='A'
    assert r['exposure_checks'][-1]['LONG']==12
    prices={c:SimpleNamespace(get=points.get) for c in rules}
    assert audit(r,prices,25,25,rules)==(2,0)
    bad=copy.deepcopy(r);next(j for j in bad['journal'] if j['kind']=='adds_cancelled')['qty']=4
    with pytest.raises(AssertionError):audit(bad,prices,25,25,rules)


def test_marked_profile_accounts_for_partial_entries_and_exits():
    from types import SimpleNamespace
    import numpy as np
    import pandas as pd
    from exposure_profile import profile
    times=np.array([0,300000,600000,900000])
    prices={'A':SimpleNamespace(mark_times=times-300000,marks=np.array([100,110,120,130])),
            'B':SimpleNamespace(mark_times=times-300000,marks=np.array([50,50,50,50]))}
    raw=dict(journal=[dict(at=0,kind='entry',symbol='A',qty=2,side='LONG'),
        dict(at=300000,kind='entry_add',symbol='A',qty=1),
        dict(at=600000,kind='entry',symbol='B',qty=1,side='SHORT'),
        dict(at=900000,kind='trailing_exit',symbol='A',net=0)])
    p=profile(raw,pd.DataFrame({'at':times}),prices,300)
    assert p['mean_long']==pytest.approx(890/3) and p['mean_short']==pytest.approx(50/3)
    assert p['mean_abs_net']==280 and p['peak_abs_net']==330
    assert p['fraction_above_entry_bound']==pytest.approx(2/3)
