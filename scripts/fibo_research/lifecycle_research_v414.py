"""Frozen signal replay and tradability audit on the expanded pre-2026 universe."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from collections import Counter
from datetime import datetime,timezone
import argparse
import gzip
import pickle
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
import research_v408 as q
import execution_v409 as x

r=q.r;ROOT=r.ROOT;ART=ROOT/'artifacts/fibo_trend_short/research_v4_0_14'
PRIOR=ROOT/'artifacts/fibo_trend_short/research_v4_0_13'
UNION=PRIOR/'completed_union'
START=r.utc('2020-01-01');END=r.utc('2026-01-01')


def freeze():
    if (ART/'SOURCE_MANIFEST.json').exists():raise FileExistsError('Already frozen')
    ART.mkdir(parents=True,exist_ok=True)
    protocol=r.read(PRIOR/'NEXT_LIFECYCLE_EXECUTION_PROTOCOL.json')
    protocol.update(version='4.0.14-lifecycle-research',registered_at_utc=datetime.now(timezone.utc).isoformat(),
        scopes={'baseline':'Exact frozen v408 data and monthly membership, freshly recompute every old PIT member and compare every candidate field/path.',
                'expanded':'Frozen v413 completed union and original causal monthly ranking; same collector and detector, no new signal/exit/risk thresholds.'},
        data_loading='Copy hash-verified bounded snapshots for PIT members and BTC context. No observations outside2020..2025. Do not merge differently named contracts.',
        diagnostic_rules={
            'entry_zero_volume':'Scheduled entry5m bar has volume0; diagnostic only, never silently delete future-known unfilled orders.',
            'exit_zero_volume':'Any quantity-reducing5m trace group has volume0 in its corresponding bar; flag assumed turnover.',
            'path_zero_volume':'Any zero-volume bar while a candidate position is modelled open; distinguish mark-only bars from exit groups.',
            'missing':'Count expected grid cells through actual exit; a horizon exit earlier than the nominal72h/120h also flags truncation.',
            'official_lifecycle':'Flag entries after published close-only/delist times and paths crossing automatic settlement. Use conservative known-from dates; distinguish undocumented close-only time from known settlement.',
            'selection':'Retain every candidate and flag. Main candidate counts also apply original elite-sniper gate and5-day annual entry embargo; no portfolio admission or P&L selection yet.'},
        baseline_requirement='Every recomputed baseline candidate including both exit paths must equal the v408 candidate cache exactly before interpreting expanded flags.',
        economic_results_in_this_stage=False,
        cost_scenarios=x.SCENARIOS,
        funding='Actual historical funding to be acquired for resulting valid execution ranges before portfolio outcomes. No missing event inferred zero.',
        fresh_oos=False,goal_complete=False,live_signoff='NOT_GRANTED')
    r.save(ART/'PROTOCOL.json',protocol)
    events=[
        {'symbol':'EOSUSDT','known_from_utc':'2025-05-15T00:00:00Z','entry_close_only_from':'2025-05-21T08:30:00Z','settlement_at':'2025-05-21T09:00:00Z',
         'published_date':'2025-05-14','source_url':'https://www.binance.com/en/support/announcement/detail/1e89a9ca957c4b0ca7502e60b993e201','kind':'token_swap_rebrand','successor_symbol':'AUSDT','ratio_spot_only':'1 EOS = 1 A'},
        {'symbol':'COCOSUSDT','known_from_utc':'2023-05-19T00:00:00Z','entry_close_only_from':'2023-05-25T08:30:00Z','settlement_at':'2023-05-25T09:00:00Z',
         'published_date':'2023-05-18','source_url':'https://www.binance.com/en/support/announcement/detail/45852dc155b641bc9e1c23bc41d8ded6','kind':'token_swap_rebrand','successor_symbol':'COMBOUSDT','ratio_spot_only':'1 COCOS = 1 COMBO'},
        {'symbol':'DODOUSDT','known_from_utc':'2022-05-19T00:00:00Z','entry_close_only_from':None,'settlement_at':'2022-05-27T09:00:00Z',
         'published_date':'2022-05-18','source_url':'https://www.binance.com/fr/support/announcement/detail/d1cb959677034c45b5149f1d998ae2b1','kind':'perpetual_delisting','successor_symbol':None},
        {'symbol':'BZRXUSDT','known_from_utc':'2021-12-18T00:00:00Z','entry_close_only_from':None,'settlement_at':'2021-12-19T02:00:00Z',
         'published_date':'2021-12-16','updated_date':'2021-12-17','source_url':'https://www.binance.com/en/support/announcement/detail/dff27dc6bcbb432c902bcbea5e24ddfa','kind':'token_swap_redenomination','successor_symbol':'OOKIUSDT','ratio_spot_only':'1 BZRX = 10 OOKI'},
        {'symbol':'AKROUSDT','known_from_utc':'2022-05-27T00:00:00Z','entry_close_only_from':None,'settlement_at':'2022-05-27T07:00:00Z',
         'published_date':'2022-05-26','source_url':'https://www.binance.com/en/support/announcement/detail/185001cde1614f0e8987c4d39aca8639','kind':'postponed_perpetual_delisting','successor_symbol':None,
         'supersedes':'Original2022-05-26 09:00 UTC automatic-settlement date in the DODO/AKRO announcement'}
    ]
    r.save(ART/'OFFICIAL_LIFECYCLE_EVENTS.json',{'events':events,'read_on_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'Initial primary-source records for four stale members plus AKRO amendment. Not a comprehensive historical exchangeInfo database.',
        'known_from_policy':'Conservative midnight UTC after the publication/update date, since displayed publication clock timezone may vary.',
        'rates_not_stitched':'Spot token conversion ratios never convert or join perpetual position history.',
        'settlement_price':'Not inferred from these announcements; material affected positions require price/source verification.'})
    sources=[Path(__file__),ROOT/'scripts/fibo_research/verify_lifecycle_v414.py',ROOT/'tests/unit/fibo_short/test_lifecycle_v414.py',Path(x.__file__)]
    sources += [ROOT/p for p in r.read(q.ART/'SOURCE_MANIFEST.json')]
    sources=list(dict.fromkeys(sources))
    for p in sources:
        target=ART/'source_snapshot'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    r.save(ART/'SOURCE_MANIFEST.json',{'sources':{str(p.relative_to(ROOT)):r.sha(p) for p in sources},
        'protocol_sha256':r.sha(ART/'PROTOCOL.json'),'lifecycle_sha256':r.sha(ART/'OFFICIAL_LIFECYCLE_EVENTS.json'),
        'v413_checkpoint_sha256':r.sha(PRIOR/'CHECKPOINT.json'),'expanded_data_manifest_sha256':r.sha(UNION/'DATA_MANIFEST.json'),
        'baseline_data_manifest_sha256':r.sha(q.ART/'history/DATA_MANIFEST.json'),'baseline_candidate_manifest_sha256':r.sha(q.ART/'history/CANDIDATE_MANIFEST.json')})
    r.save(ART/'PROGRESS.json',{'stage':'signal_replay_and_lifecycle_audit_registered','goal_complete':False})


def verify_sources():
    m=r.read(ART/'SOURCE_MANIFEST.json')
    for path,digest in m['sources'].items():assert r.sha(ROOT/path)==digest,path
    for key,path in [('protocol_sha256',ART/'PROTOCOL.json'),('lifecycle_sha256',ART/'OFFICIAL_LIFECYCLE_EVENTS.json'),
        ('v413_checkpoint_sha256',PRIOR/'CHECKPOINT.json'),('expanded_data_manifest_sha256',UNION/'DATA_MANIFEST.json'),
        ('baseline_data_manifest_sha256',q.ART/'history/DATA_MANIFEST.json'),('baseline_candidate_manifest_sha256',q.ART/'history/CANDIDATE_MANIFEST.json')]:assert m[key]==r.sha(path),str(path)


def prepare():
    verify_sources()
    for scope in ['baseline','expanded']:
        folder=ART/scope/'history';folder.mkdir(parents=True,exist_ok=True)
        if (folder/'DATA_MANIFEST.json').exists():continue
        source_folder=q.ART/'history' if scope=='baseline' else UNION
        membership=r.read(source_folder/'MEMBERSHIP.json');source=r.read(source_folder/'DATA_MANIFEST.json')
        symbols=sorted({'BTCUSDT'}|{a['symbol'] for rows in membership.values() for a in rows});inputs={}
        for symbol in symbols:
            item=source['inputs'][symbol]
            path=source_folder/'bars_5m'/f'{symbol}.parquet' if scope=='baseline' else Path(item['path'])
            digest=item['snapshot_sha256'] if scope=='baseline' else item['sha256'];assert r.sha(path)==digest
            target=folder/'bars_5m'/f'{symbol}.parquet';target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():shutil.copy2(path,target)
            assert r.sha(target)==digest
            inputs[symbol]={'sha256':digest,'source':str(path)}
        r.save(folder/'MEMBERSHIP.json',membership)
        r.save(folder/'DATA_MANIFEST.json',{'inputs':inputs,'source_manifest_sha256':r.sha(ART/'SOURCE_MANIFEST.json'),
            'source_data_manifest_sha256':r.sha(source_folder/'DATA_MANIFEST.json'),'membership_sha256':r.sha(folder/'MEMBERSHIP.json'),
            'scope':scope,'post_2025_observations':0})
        print(f'{scope}: {len(symbols)} bounded snapshots prepared.',flush=True)


def worker(scope,symbol):
    r.ART=ART/scope;r.WINDOWS['history']=('2020-01-01','2026-01-01')
    return r.collect_one('history',symbol)


def load_rows(path):
    with gzip.open(path,'rb') as fh:return pickle.load(fh)


def collect(scope,workers):
    verify_sources();folder=ART/scope/'history';data=r.read(folder/'DATA_MANIFEST.json')
    assert data['source_manifest_sha256']==r.sha(ART/'SOURCE_MANIFEST.json')
    assert data['membership_sha256']==r.sha(folder/'MEMBERSHIP.json')
    if scope=='expanded':assert r.read(ART/'BASELINE_RECONCILIATION.json')['all_passed']
    for symbol,item in data['inputs'].items():assert r.sha(folder/'bars_5m'/f'{symbol}.parquet')==item['sha256']
    members=r.read(folder/'MEMBERSHIP.json');symbols=sorted({a['symbol'] for rows in members.values() for a in rows})
    (folder/'candidates').mkdir(exist_ok=True);path=folder/'COLLECTION_PROGRESS.json'
    fingerprint={'data_manifest_sha256':r.sha(folder/'DATA_MANIFEST.json'),'source_manifest_sha256':r.sha(ART/'SOURCE_MANIFEST.json')}
    progress=r.read(path) if path.exists() else {'symbols':{},**fingerprint}
    assert all(progress[k]==val for k,val in fingerprint.items())
    for symbol,item in progress['symbols'].items():assert r.sha(folder/'candidates'/f'{symbol}.pkl.gz')==item['sha256']
    pending=[s for s in symbols if s not in progress['symbols']]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(worker,scope,s) for s in pending]
        for future in as_completed(futures):
            symbol,count,rejections,digest=future.result();progress['symbols'][symbol]={'candidates':count,'rejections':rejections,'sha256':digest}
            r.save(path,progress);print(f'{scope} signals {len(progress["symbols"])}/{len(symbols)} {symbol}: {count}',flush=True)
    r.save(folder/'CANDIDATE_MANIFEST.json',progress)
    if scope=='baseline':
        old=r.read(q.ART/'history/CANDIDATE_MANIFEST.json');total=0
        assert set(old['symbols'])==set(progress['symbols'])
        for symbol,item in old['symbols'].items():
            source=q.ART/'history/candidates'/f'{symbol}.pkl.gz';assert r.sha(source)==item['sha256']
            a=load_rows(source);b=load_rows(folder/'candidates'/f'{symbol}.pkl.gz');assert a==b,symbol
            assert item['rejections']==progress['symbols'][symbol]['rejections'];total+=len(a)
        r.save(ART/'BASELINE_RECONCILIATION.json',{'all_passed':True,'symbols_exactly_equal':len(symbols),'candidates_exactly_equal':total,
            'scope':'Every candidate field, signal score, milestone, rejection count and both full paths recomputed exactly; prior portfolio baseline was separately reconciled in v412.',
            'baseline_candidate_manifest_sha256':r.sha(folder/'CANDIDATE_MANIFEST.json'),'original_candidate_manifest_sha256':r.sha(q.ART/'history/CANDIDATE_MANIFEST.json')})


def annual_eligible(c):
    year=r.utc(pd.Timestamp(c['entry_ts'],unit='s',tz='UTC')).year
    return c['entry_ts']<int(r.utc(f'{year+1}-01-01').timestamp())-5*86400


def inspect_path(c,frame,events,context=None):
    if context is None:
        ts=r.epoch_seconds(frame.index);vol=frame.volume.to_numpy();positive=ts[vol>0]
    else:ts,vol,positive=context
    entry=c['entry_ts'];path=c['paths']['ladder'];exit=path['exit_ts']
    a=int(np.searchsorted(ts,entry));b=int(np.searchsorted(ts,exit));assert a<len(ts) and ts[a]==entry
    active=ts[a:b];zero=vol[a:b]==0
    expected_end=entry+(72 if c['tf']=='4h' else 120)*3600
    expected_bars=(exit-entry)//300
    assert expected_bars>=len(active) and (exit-entry)%300==0
    exit_groups=[]
    for close,mark,before,after,stop,delta,done in path['trace']:
        if before-after<=1e-10:continue
        index=np.searchsorted(ts,close-300);assert index<len(ts) and ts[index]==close-300
        if vol[index]==0:exit_groups.append(int(close))
    index=np.searchsorted(positive,entry,side='left')-1;last_positive=int(positive[index]) if index>=0 else None
    lifecycle=[]
    for event in events:
        if event['symbol']!=c['symbol']:continue
        known=int(r.utc(event['known_from_utc']).timestamp());settle=int(r.utc(event['settlement_at']).timestamp())
        close_only=int(r.utc(event['entry_close_only_from']).timestamp()) if event['entry_close_only_from'] else None
        if known<=entry and (entry>=settle or (close_only is not None and entry>=close_only)):
            lifecycle.append({'kind':'entry_after_announced_new_position_cutoff','settlement_at':settle,'close_only_from':close_only,'source_url':event['source_url']})
        if known<=settle and entry<settle<=exit:
            lifecycle.append({'kind':'position_path_crosses_automatic_settlement','settlement_at':settle,'source_url':event['source_url']})
    return {'entry_zero_volume':bool(vol[a]==0),'zero_volume_path_bars':int(zero.sum()),'zero_volume_exit_groups':exit_groups,
        'missing_bars_through_modelled_exit':int(expected_bars-len(active)),
        'horizon_truncated':path['exit_reason']=='horizon' and exit<expected_end,
        'nominal_horizon_end':expected_end,'modelled_exit':exit,
        'last_positive_volume_bar_before_entry':last_positive,
        'hours_since_last_positive_volume_bar_close':(entry-last_positive-300)/3600 if last_positive is not None else None,
        'official_lifecycle_flags':lifecycle}


def audit():
    verify_sources();folder=ART/'expanded/history';manifest=r.read(folder/'CANDIDATE_MANIFEST.json');events=r.read(ART/'OFFICIAL_LIFECYCLE_EVENTS.json')['events']
    assert manifest['source_manifest_sha256']==r.sha(ART/'SOURCE_MANIFEST.json')
    all_count=0;elite_count=0;flags=[];elite_flags=[];annual=Counter();symbols=set();funding_ranges={};by_symbol={}
    for symbol,item in sorted(manifest['symbols'].items()):
        path=folder/'candidates'/f'{symbol}.pkl.gz';assert r.sha(path)==item['sha256'];rows=load_rows(path)
        frame=pd.read_parquet(folder/'bars_5m'/f'{symbol}.parquet')
        assert frame.index.min()>=START and frame.index.max()<END
        times=r.epoch_seconds(frame.index);volumes=frame.volume.to_numpy();context=(times,volumes,times[volumes>0])
        records=[]
        for c in rows:
            d=inspect_path(c,frame,events,context);is_elite=r.passes(c,'elite_sniper') and annual_eligible(c)
            all_count+=1;record={'id':c['id'],'symbol':symbol,'tf':c['tf'],'entry_ts':c['entry_ts'],'primary_elite_annual_eligible':is_elite,**d}
            affected=d['entry_zero_volume'] or d['zero_volume_path_bars'] or d['missing_bars_through_modelled_exit'] or d['horizon_truncated'] or d['official_lifecycle_flags']
            if affected:flags.append(record);records.append(record)
            if is_elite:
                elite_count+=1;symbols.add(symbol);annual[str(pd.Timestamp(c['entry_ts'],unit='s',tz='UTC').year)]+=1
                if affected:elite_flags.append(record)
                lower=(c['entry_ts']-16*3600)*1000;upper=(d['modelled_exit']+16*3600)*1000
                current=funding_ranges.setdefault(symbol,{'start_ms':max(int(START.timestamp()*1000),lower),'end_ms':min(int(END.timestamp()*1000)-1,upper)})
                current['start_ms']=min(current['start_ms'],max(int(START.timestamp()*1000),lower));current['end_ms']=max(current['end_ms'],min(int(END.timestamp()*1000)-1,upper))
        if records:by_symbol[symbol]=records
    def summary(records):
        return {'candidates_with_any_flag':len(records),'symbols_with_flags':len({x['symbol'] for x in records}),
            'entry_zero_volume':sum(x['entry_zero_volume'] for x in records),'any_zero_volume_path':sum(x['zero_volume_path_bars']>0 for x in records),
            'zero_volume_exit':sum(bool(x['zero_volume_exit_groups']) for x in records),
            'missing_bars_in_path':sum(x['missing_bars_through_modelled_exit']>0 for x in records),
            'truncated_horizon':sum(x['horizon_truncated'] for x in records),'official_lifecycle_affected':sum(bool(x['official_lifecycle_flags']) for x in records)}
    result={'all_candidates':all_count,'primary_elite_candidates':elite_count,'primary_symbols':len(symbols),'primary_candidates_by_year':dict(sorted(annual.items())),
        'all_candidate_quality':summary(flags),'primary_quality':summary(elite_flags),'flags':flags,'primary_flags':elite_flags,
        'candidate_manifest_sha256':r.sha(folder/'CANDIDATE_MANIFEST.json'),'source_manifest_sha256':r.sha(ART/'SOURCE_MANIFEST.json'),
        'economic_results_evaluated':False,'fresh_oos':False,'post_2025_observations_loaded':0,'goal_complete':False,'live_signoff':'NOT_GRANTED'}
    r.save(ART/'LIFECYCLE_CANDIDATE_AUDIT.json',result);r.save(ART/'FUNDING_REQUIREMENTS.json',{'symbols':funding_ranges,
        'status':'Provisional ranges from frozen paths; material lifecycle corrections may change them. Acquire and verify before portfolio results.',
        'candidate_manifest_sha256':r.sha(folder/'CANDIDATE_MANIFEST.json')})
    print({k:value for k,value in result.items() if k not in ('flags','primary_flags')},flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','prepare','baseline','expanded','audit']);parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    if args.action=='freeze':freeze()
    elif args.action=='prepare':prepare()
    elif args.action=='audit':audit()
    else:collect(args.action,args.workers)
