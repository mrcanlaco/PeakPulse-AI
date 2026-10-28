from copy import deepcopy
from pathlib import Path
import sqlite3
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
from paper_state_v1 import Journal, new_state, step
from paper_runner_v1 import validate_entry_receipt, funding_rows, Observer
import paper_runner_v1 as runner
from stream_execution_v424 import BAR_MS, HOUR_MS

T = 1736942700000  # 2025-01-15 12:05 UTC


def setup():
    p = {'start_ms': T, 'end_ms': T+20*24*HOUR_MS, 'protocol_sha256':'frozen',
         'family':[{'id':'risk','sizing':'risk','gate':'expanded'}],
         'scenarios':{'standard':{'fee_bps':2.5,'slippage_bps':10.},'stress':{'fee_bps':5.,'slippage_bps':50.}}}
    return new_state(p)


def entry():
    return {'id':'A:4h:'+str(T//1000),'symbol':'A','tf':'4h','wave_key':'w','decision_ts_ms':T-BAR_MS,
            'entry_ts_ms':T,'entry':100.,'stop':110.,'targets':[90.,80.,70.], 'score':80.,'milestones':['m6_f4_expanded']}


def test_exactly_once_journal_and_snapshot_tamper_detection(tmp_path):
    path=tmp_path/'paper.db';j=Journal(path);state=setup()
    assert j.commit(0,'initial',state,{'kind':'initial'})
    assert not j.commit(0,'initial',state,{'kind':'initial'})
    assert j.verify()['events']==1
    with pytest.raises(ValueError,match='Conflicting'):
        j.commit(0,'initial',state,{'kind':'changed'})
    j.db.execute("UPDATE snapshot SET payload=? WHERE id=1", ('{}',));j.db.commit()
    with pytest.raises(AssertionError):j.verify()


def test_all_accounts_advance_atomically_and_resume_partial_funding(tmp_path):
    state=setup();original=deepcopy(state)
    active,events=step(state,T,[entry()],{},[])
    assert state==original
    assert len(active['accounts'])==2
    j=Journal(tmp_path/'paper.db');j.commit(0,'enter',active,events)
    _,restored=j.load()
    before=deepcopy(restored)
    with pytest.raises(ValueError,match='Missing required execution bar'):
        step(restored,T+BAR_MS,[],{},[])
    assert restored==before
    bar={'open_time_ms':T,'open':100.,'high':101.,'low':89.,'close':90.,'volume':1.}
    funding=[('A',{'funding_ts_ms':T+BAR_MS,'funding_rate':.001,'mark_price':95.,'price_source':'funding_api_settlement_mark'})]
    resumed,result=step(restored,T+BAR_MS,[],{'A':bar},funding)
    direct,_=step(active,T+BAR_MS,[],{'A':bar},funding)
    assert resumed==direct
    assert all(len(v['closed_trades'])==1 for v in result.values())
    assert all(v==1 for v in resumed['closed_trades'].values())


def test_stale_writer_and_future_entry_receipts_are_rejected(tmp_path):
    j=Journal(tmp_path/'paper.db');state=setup();j.commit(0,'initial',state,{})
    with pytest.raises(ValueError,match='stale'):
        j.commit(0,'new',state,{})
    validate_entry_receipt(T-BAR_MS,T,T-60000,T+60000)
    with pytest.raises(ValueError,match='sealed'):
        validate_entry_receipt(T-BAR_MS,T,T-59999,T+1)
    with pytest.raises(ValueError,match='late'):
        validate_entry_receipt(T-BAR_MS,T,T-60000,T+60001)
    with pytest.raises(ValueError,match='late'):
        validate_entry_receipt(T-BAR_MS,T,T-60000,T-1)


def test_signed_funding_requires_exact_positive_mark_and_time():
    row={'symbol':'A','fundingTime':T+1,'fundingRate':'-0.001','markPrice':'99'}
    parsed=funding_rows('A',[row],T,T+15000)
    assert parsed[0][1][1]['funding_rate']==-.001
    for changed in ({**row,'markPrice':''},{**row,'fundingTime':T+20000},{**row,'symbol':'B'}):
        with pytest.raises(ValueError):funding_rows('A',[changed],T,T+15000)


def test_restart_retries_uncommitted_signal_before_next_bar():
    obj=Observer.__new__(Observer)
    state={'last_signal_ms':T-300000-3600000,'last_bar_ms':T-300000}
    class FakeJournal:
        def load(self):return 1,state
    obj.j=FakeJournal();obj.p={'end_ms':T+20*24*HOUR_MS};obj.last_verification=float('inf')
    calls=[];obj.signal=lambda t:calls.append(t);obj.status=lambda:None
    obj.bar=lambda t:(_ for _ in ()).throw(AssertionError('Advanced before pending signal'))
    assert obj.tick() and calls==[T-300000]


def observer_fixture(tmp_path, monkeypatch, *, late=False, missing_mark=False):
    monkeypatch.setattr(runner.d,'ART',tmp_path)
    runner.d.save(tmp_path/'hourly/A.json',{'onboard_ms':0})
    state=setup(); candidate=entry()
    metadata={k:v for k,v in candidate.items() if k not in ('entry','decision_ts_ms','entry_ts_ms')}
    metadata.update(decision_ts=(T-BAR_MS)//1000,entry_ts=T//1000)
    state['pending'][str(T)]=[{'metadata':metadata,'decision_recorded_ms':T-60000}]
    # Expected settlement is known before the entry; actual exchange timestamp
    # is one millisecond after the bar boundary.
    state['funding_due']['A']=[T+1]
    obj=Observer.__new__(Observer);obj.p={'start_ms':T,'end_ms':T+20*24*HOUR_MS,'protocol_sha256':'frozen'}
    obj.offset=0;obj.now=lambda:T+(61000 if late else 25000)
    obj.j=Journal(tmp_path/'paper.db');obj.j.commit(0,'initial',state,{})
    def request(endpoint,params=None,**kwargs):
        receipt={'path':'synthetic','sha256':'synthetic','received_ms':obj.now()}
        if endpoint=='exchangeInfo':value={'symbols':[{'symbol':'A','status':'TRADING','onboardDate':0,'deliveryDate':T+30*24*HOUR_MS}]}
        elif endpoint=='premiumIndex':value=[{'symbol':'A','nextFundingTime':T+8*HOUR_MS}]
        elif endpoint=='klines':value=[[T,'100','100','100','100','1',T+BAR_MS-1,'100']]
        elif endpoint=='ticker/bookTicker':value={'symbol':'A','bidPrice':'99.99','askPrice':'100.01'}
        elif endpoint=='fundingRate':value=[{'symbol':'A','fundingTime':T+1,'fundingRate':'.001','markPrice':'' if missing_mark else '100'}]
        else:raise AssertionError(endpoint)
        return value,receipt
    monkeypatch.setattr(runner.d,'request',request)
    return obj


def test_runner_orders_entry_and_millisecond_funding_and_seals_state(tmp_path,monkeypatch):
    obj=observer_fixture(tmp_path,monkeypatch);obj.bar(T)
    revision,state=obj.j.load();assert revision==2
    assert all(a['clock']==T+1 for a in state['accounts'].values())
    for a in state['accounts'].values():
        position=next(iter(a['positions'].values()))
        assert len(position['funding_events'])==1 and position['funding']>0
    assert obj.j.verify()['all_passed']
    assert str(T) not in state['pending']


def test_runner_rejects_late_entry_without_backfilling(tmp_path,monkeypatch):
    obj=observer_fixture(tmp_path,monkeypatch,late=True);obj.bar(T)
    _,state=obj.j.load()
    assert all(not a['positions'] and a['equity']==100 for a in state['accounts'].values())
    event=__import__('json').loads(obj.j.db.execute('SELECT payload FROM events WHERE seq=2').fetchone()[0])
    assert 'late' in event['entry_rejections'][0]['reason']
    assert state['opportunity_incidents']


def test_runner_missing_exact_funding_does_not_commit_entry(tmp_path,monkeypatch):
    obj=observer_fixture(tmp_path,monkeypatch,missing_mark=True)
    old=obj.j.load()
    with pytest.raises(ValueError,match='funding settlement'):obj.bar(T)
    assert obj.j.load()==old and obj.j.verify()['events']==1


def test_hourly_lineage_preserves_inputs_and_rejects_rewritten_history(tmp_path,monkeypatch):
    monkeypatch.setattr(runner.d,'ART',tmp_path)
    path=tmp_path/'hourly/A.json'
    meta={'symbol':'A','cutoff_ms':1000,'sources':[{'path':'raw1','sha256':'a'}],'rows':1}
    runner.d.save(path,meta);first=runner.capture_lineage('A')
    assert runner.capture_lineage('A')==first
    meta.update(cutoff_ms=2000,rows=2);meta['sources'].append({'path':'raw2','sha256':'b'})
    runner.d.save(path,meta);second=runner.capture_lineage('A')
    saved=runner.d.read(second['path'])
    assert saved['previous']==first and saved['new_sources']==[{'path':'raw2','sha256':'b'}]
    assert runner.d.sha(first['path'])==first['sha256']
    meta['sources'][0]['sha256']='changed';runner.d.save(path,meta)
    with pytest.raises(RuntimeError,match='rewritten'):runner.capture_lineage('A')


def test_inactive_member_does_not_block_other_signals_or_reuse_new_identity(tmp_path,monkeypatch):
    monkeypatch.setattr(runner.d,'ART',tmp_path)
    members={'members':[{'symbol':s} for s in ('A','B','C')],
             'contracts':{s:{'onboardDate':0} for s in ('A','B','C')}}
    contracts={'A':{'status':'TRADING','onboardDate':0},'B':{'status':'SETTLING','onboardDate':0},
               'C':{'status':'TRADING','onboardDate':100}}
    active,issues=runner.signal_universe(members,contracts)
    assert active==['A','BTCUSDT']
    assert issues==[{'symbol':'B','reason':'currently_inactive_contract','critical':False},
                    {'symbol':'C','reason':'contract_identity_changed','critical':True}]
