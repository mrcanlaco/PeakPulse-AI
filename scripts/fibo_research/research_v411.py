"""Pre-registered matched event study; no portfolio or fresh-OOS claims."""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import argparse
import gzip
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import research_v409 as z

r=z.r; q=z.q; x=z.x; f=z.f
ART=r.ROOT/'artifacts/fibo_trend_short/research_v4_0_11'
PRIOR=r.ROOT/'artifacts/fibo_trend_short/research_v4_0_10'
START=int(q.START.timestamp()); END=int(q.END.timestamp()); DAY=86400
FEATURES=['momentum','volatility']


def freeze():
    if (ART/'SOURCE_MANIFEST.json').exists():raise FileExistsError('Source already frozen')
    paths=[Path(__file__),r.ROOT/'scripts/fibo_research/verify_research_v411.py',
           r.ROOT/'tests/unit/fibo_short/test_research_v411.py',Path(x.__file__),Path(f.__file__),Path(q.__file__),Path(r.__file__)]
    for path in paths:
        target=ART/'source_snapshot'/path.relative_to(r.ROOT)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    r.save(ART/'SOURCE_MANIFEST.json',{'sources':{str(p.relative_to(r.ROOT)):r.sha(p) for p in paths},
        'protocol_sha256':r.sha(ART/'PROTOCOL.json'),'v409_checkpoint_sha256':r.sha(z.ART/'CHECKPOINT.json'),
        'v410_checkpoint_sha256':r.sha(PRIOR/'CHECKPOINT.json'),'prior_hypothesis_sha256':r.sha(PRIOR/'NEXT_HYPOTHESIS.json'),
        'data_manifest_sha256':r.sha(q.ART/'history/DATA_MANIFEST.json'),
        'candidate_manifest_sha256':r.sha(q.ART/'history/CANDIDATE_MANIFEST.json'),
        'membership_sha256':r.sha(q.ART/'history/MEMBERSHIP.json')})


def verify_sources():
    manifest=r.read(ART/'SOURCE_MANIFEST.json')
    assert manifest['protocol_sha256']==r.sha(ART/'PROTOCOL.json')
    assert manifest['v409_checkpoint_sha256']==r.sha(z.ART/'CHECKPOINT.json')
    assert manifest['v410_checkpoint_sha256']==r.sha(PRIOR/'CHECKPOINT.json')
    assert manifest['prior_hypothesis_sha256']==r.sha(PRIOR/'NEXT_HYPOTHESIS.json')
    for path,digest in manifest['sources'].items():assert r.sha(r.ROOT/path)==digest,path
    for key,name in [('data_manifest_sha256','DATA_MANIFEST.json'),('candidate_manifest_sha256','CANDIDATE_MANIFEST.json'),('membership_sha256','MEMBERSHIP.json')]:
        assert manifest[key]==r.sha(q.ART/'history'/name)


def load_bars(symbol):
    path=q.ART/'history/bars_5m'/f'{symbol}.parquet'
    expected=r.read(q.ART/'history/DATA_MANIFEST.json')['inputs'][symbol]['snapshot_sha256']
    assert r.sha(path)==expected
    frame=pd.read_parquet(path)
    ts=r.epoch_seconds(frame.index)
    assert len(ts) and START<=ts.min() and ts.max()<END
    assert np.all(np.diff(ts)>0) and np.all(ts%300==0)
    return frame


def feature_frame(bars,decisions):
    stamps=r.epoch_seconds(bars.index)
    close=bars['close'].astype(float)
    logs=np.log(close).diff()
    valid=pd.Series(np.r_[False,np.diff(stamps)==300],index=bars.index).rolling(288).sum()==288
    result=pd.DataFrame({'decision_ts':stamps+300,'momentum':np.log(close/close.shift(288)).to_numpy(),
        'volatility':np.sqrt(logs.pow(2).rolling(288).sum()).to_numpy(),'valid':valid.to_numpy()})
    result=result[result.decision_ts.isin(decisions)&result.valid].drop(columns='valid').dropna()
    assert np.isfinite(result[FEATURES].to_numpy()).all()
    return result


def sample_events(candidates):
    raw=sorted((c for c in candidates if r.passes(c,'elite_sniper')),key=lambda c:(c['entry_ts'],-c['score'],c['symbol'],c['tf']))
    sampled=[];rejections=Counter();waves=set();cooldown={};year=None
    for c in raw:
        y=pd.Timestamp(c['entry_ts'],unit='s',tz='UTC').year
        assert 2020<=y<=2025 and c['entry_ts']==c['decision_ts']+300
        if y!=year:year=y;waves=set();cooldown={}
        if c['entry_ts']>=int(r.utc(f'{y+1}-01-01').timestamp())-5*DAY:
            rejections['year_end_embargo']+=1;continue
        wave=(c['symbol'],c['tf'],c['wave_key'])
        if wave in waves or c['entry_ts']<cooldown.get(c['symbol'],0):
            rejections['wave_or_24h_cooldown']+=1;continue
        waves.add(wave);cooldown[c['symbol']]=c['entry_ts']+DAY
        sampled.append({k:c[k] for k in ('id','symbol','tf','wave_key','score','decision_ts','entry_ts')})
    return sampled,dict(rejections),raw


def choose_control(treated,pool):
    if treated['momentum']<=0:return None,'treated_nonpositive_momentum'
    if len(pool)<3:return None,'fewer_than_three_positive_controls'
    values=np.array([[p[k] for k in FEATURES] for p in pool]);sd=values.std(axis=0)
    if np.any(sd<=1e-12):return None,'degenerate_control_dispersion'
    target=np.array([treated[k] for k in FEATURES]);diff=(values-target)/sd
    selected=[]
    for i,p in enumerate(pool):
        if np.max(np.abs(diff[i]))<=.5:
            selected.append((float(np.sum(diff[i]**2)),p['symbol'],i))
    if not selected:return None,'outside_fixed_caliper'
    distance,_,i=min(selected)
    return {'control':pool[i], 'control_pool_size':len(pool),'feature_sd':sd.tolist(),
            'standardized_difference':diff[i].tolist(),'squared_distance':distance},None


def match():
    verify_sources()
    if (ART/'MATCHES.json').exists():raise FileExistsError('Matching already frozen')
    q.setup_context();candidates=r.load_candidates('history')
    sampled,rejected,raw=sample_events(candidates)
    decisions=sorted({c['decision_ts'] for c in sampled})
    membership=r.read(q.ART/'history/MEMBERSHIP.json')
    symbols=sorted({v['symbol'] for rows in membership.values() for v in rows})
    previous=r.read(PRIOR/'MATCHES.json');checkpoint=r.read(PRIOR/'CHECKPOINT.json')
    assert r.sha(PRIOR/'MATCHES.json')==checkpoint['files']['MATCHES.json']
    assert r.sha(PRIOR/'FEATURES.parquet')==previous['features_sha256']==checkpoint['files']['FEATURES.parquet']
    previous_events={p['id']:{k:p[k] for k in sampled[0]} for p in previous['pairs']+previous['unmatched']}
    assert previous_events=={p['id']:p for p in sampled}
    assert previous['raw_elite_candidates']==len(raw) and previous['sampling_rejections']==rejected
    features=pd.read_parquet(PRIOR/'FEATURES.parquet')
    assert set(features.decision_ts)<=set(decisions) and set(features.symbol)<=set(symbols)
    shutil.copy2(PRIOR/'FEATURES.parquet',ART/'FEATURES.parquet')
    print(f'Reused {len(features)} verified past feature rows; sampling unchanged.',flush=True)
    lookup={(v.symbol,int(v.decision_ts)):{'symbol':v.symbol,'momentum':float(v.momentum),'volatility':float(v.volatility)} for v in features.itertuples()}
    active=defaultdict(set)
    for c in raw:active[c['decision_ts']].add(c['symbol'])
    pairs=[];unmatched=[]
    for c in sampled:
        t=c['decision_ts'];ym=pd.Timestamp(t,unit='s',tz='UTC').strftime('%Y-%m')
        treated=lookup.get((c['symbol'],t))
        if treated is None:unmatched.append({**c,'reason':'treated_past_feature_missing'});continue
        members=[p['symbol'] for p in membership[ym]];assert c['symbol'] in members
        pool=[lookup[(s,t)] for s in members if s!=c['symbol'] and s not in active[t] and (s,t) in lookup and lookup[(s,t)]['momentum']>0]
        result,reason=choose_control(treated,pool)
        if reason:unmatched.append({**c,'reason':reason});continue
        pairs.append({**c,'treated':treated,**result,'exit_ts':c['entry_ts']+DAY,'month':ym})
    r.save(ART/'MATCHES.json',{'pairs':pairs,'unmatched':unmatched,'sampled_events':len(sampled),'raw_elite_candidates':len(raw),
        'sampling_rejections':rejected,'unmatched_reasons':dict(Counter(c['reason'] for c in unmatched)),
        'features_sha256':r.sha(ART/'FEATURES.parquet'),'protocol_sha256':r.sha(ART/'PROTOCOL.json'),
        'locked_before_outcome_evaluation_at_utc':datetime.now(timezone.utc).isoformat()})
    need={}
    for p in pairs:
        for symbol in (p['symbol'],p['control']['symbol']):
            n=need.setdefault(symbol,{'first_entry_ms':p['entry_ts']*1000,'last_exit_ms':p['exit_ts']*1000,'candidates':0})
            n['first_entry_ms']=min(n['first_entry_ms'],p['entry_ts']*1000);n['last_exit_ms']=max(n['last_exit_ms'],p['exit_ts']*1000);n['candidates']+=1
    for n in need.values():n.update(start_ms=max(f.START_MS,n['first_entry_ms']-16*3600000),end_ms=min(f.LIMIT_MS-1,n['last_exit_ms']+16*3600000))
    r.save(ART/'funding/REQUIREMENTS.json',need)
    r.save(ART/'PROGRESS.json',{'stage':'past_only_matches_locked','goal_complete':False,'matched_pairs':len(pairs),'unmatched_events':len(unmatched),'next_action':'verify funding coverage then evaluate locked pairs'})
    print(json.dumps({'matched_pairs':len(pairs),'unmatched':len(unmatched),'reasons':dict(Counter(c['reason'] for c in unmatched)),'funding_symbols':len(need)}),flush=True)


def acquire_funding():
    verify_sources();need=r.read(ART/'funding/REQUIREMENTS.json')
    old=r.read(z.ART/'funding/MANIFEST.json');recent=r.read(PRIOR/'funding/MANIFEST.json');records={};pending={}
    for symbol,n in need.items():
        choices=[]
        if symbol in recent['symbols']:
            item=recent['symbols'][symbol];choices.append(('reuse_verified_v410',Path(item['path']),item['record']))
        if symbol in old['symbols']:choices.append(('reuse_verified_v409',z.ART/'funding/snapshots'/f'{symbol}.parquet',old['symbols'][symbol]))
        for mode,path,prior in choices:
            if not prior['gaps_over_8h'] and not prior['local_differences_ms'] and prior['first_event_ms']<=n['first_entry_ms'] and prior['last_event_ms']>=n['last_exit_ms']:
                assert r.sha(path)==prior['sha256']
                records[symbol]={'mode':mode,'path':str(path),'sha256':prior['sha256'],'record':prior,'requirements':n}
                break
        if symbol not in records:pending[symbol]=n
    f.ART=ART
    errors={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(f.fetch_symbol,s,n):s for s,n in pending.items()}
        for future in as_completed(futures):
            symbol=futures[future]
            try:
                _,record=future.result()
                if record['gaps_over_8h'] or record['left_edge_uncovered'] or record['right_edge_uncovered'] or record['local_differences_ms']:
                    raise ValueError('Unresolved funding coverage or source mismatch')
                records[symbol]={'mode':'new_official_download','path':str(ART/'funding/snapshots'/f'{symbol}.parquet'),
                    'sha256':record['sha256'],'record':record,'requirements':need[symbol]}
                print(f'Funding acquired {len(records)}/{len(need)} {symbol}',flush=True)
            except Exception as exc:errors[symbol]=str(exc);print(f'Funding issue {symbol}: {exc}',flush=True)
    manifest={'symbols':records,'errors':errors,'all_passed':not errors and len(records)==len(need),
        'requirements_sha256':r.sha(ART/'funding/REQUIREMENTS.json'),'reused_symbols':sum(p['mode'].startswith('reuse_verified_') for p in records.values()),
        'reused_by_source':dict(Counter(p['mode'] for p in records.values() if p['mode'].startswith('reuse_verified_'))),
        'newly_acquired_symbols':sum(p['mode']=='new_official_download' for p in records.values()),
        'funding_price_quality':'PARTIAL_EXPLICIT_PROXY','post_2025_observations':0}
    r.save(ART/'funding/MANIFEST.json',manifest)
    if not manifest['all_passed']:raise RuntimeError(f'Funding acquisition incomplete: {errors}')
    print(json.dumps({k:v for k,v in manifest.items() if k!='symbols'}),flush=True)


def fixed_horizon_prices(bars,entry_ts):
    exit_ts=entry_ts+DAY;stamps=r.epoch_seconds(bars.index)
    i=int(np.searchsorted(stamps,entry_ts));j=int(np.searchsorted(stamps,exit_ts))
    if j-i!=288 or i==len(stamps) or stamps[i]!=entry_ts or stamps[j-1]!=exit_ts-300 or not np.all(np.diff(stamps[i:j])==300):
        return {'status':'NOT_EVALUABLE','reason':'incomplete_fixed_horizon_execution_grid','observed_bars':j-i}
    return {'status':'COMPLETE','entry_ts_ms':entry_ts*1000,'exit_ts_ms':exit_ts*1000,
        'entry_reference':float(bars.iloc[i]['open']),'exit_reference':float(bars.iloc[j-1]['close']),'observed_bars':288}


def unit_outcome(prices,events,scenario):
    qty=1/prices['entry_reference']
    enter=x.fill('SELL',prices['entry_reference'],qty,**scenario)
    leave=x.fill('BUY',prices['exit_reference'],qty,**scenario)
    payments=[{**event,'remaining_qty':qty,'cashflow':qty*event['mark_price']*event['funding_rate']} for event in events
        if prices['entry_ts_ms']<event['funding_ts_ms']<=prices['exit_ts_ms']]
    funding=sum(e['cashflow'] for e in payments)
    fees=enter['fee']+leave['fee'];slippage=enter['slippage_cost']+leave['slippage_cost']
    gross=1-qty*prices['exit_reference'];net=enter['notional']-leave['notional']-fees+funding
    assert abs(net-(gross-fees-slippage+funding))<1e-10
    return {'net_return':net,'gross_reference_return':gross,'fees':fees,'slippage':slippage,'funding':funding,
        'qty':qty,'fills':[{**enter,'timestamp_ms':prices['entry_ts_ms']},{**leave,'timestamp_ms':prices['exit_ts_ms']}],
        'funding_events':payments,'proxy_payments':sum(e['price_source']!='funding_api_settlement_mark' for e in payments)}


def paired_statistics(rows,start,end,samples=10000):
    start=r.utc(start);end=r.utc(end)
    selected=[v for v in rows if start.timestamp()<=v['entry_ts']<end.timestamp()]
    if not selected:return {'available':False,'pairs':0}
    first=start.normalize()-pd.Timedelta(days=start.weekday())
    last=(end-pd.Timedelta(seconds=1)).normalize();last-=pd.Timedelta(days=last.weekday())
    weeks=pd.date_range(first,last,freq='7D');sums=np.zeros((len(weeks),3));counts=np.zeros(len(weeks))
    for row in selected:
        i=int((pd.Timestamp(row['entry_ts'],unit='s',tz='UTC')-first).total_seconds()//(7*DAY))
        a=row['treated']['net_return'];b=row['control']['net_return']
        sums[i]+=np.array([a,b,a-b]);counts[i]+=1
    n=len(selected);means=sums.sum(axis=0)/n
    rng=np.random.default_rng(410);starts=rng.integers(0,len(weeks),size=(samples,(len(weeks)+3)//4))
    indices=((starts[:,:,None]+np.arange(4))%len(weeks)).reshape(samples,-1)[:,:len(weeks)]
    totals=counts[indices].sum(axis=1);valid=totals>0
    distribution=sums[indices].sum(axis=1)[valid]/totals[valid,None]
    return {'available':True,'pairs':n,'calendar_weeks':len(weeks),'active_weeks':int(np.sum(counts>0)),
        'mean_fibo_bps':float(means[0]*10000),'mean_control_bps':float(means[1]*10000),'mean_difference_bps':float(means[2]*10000),
        'paired_difference_ci95_bps':(np.quantile(distribution[:,2],[.025,.975])*10000).tolist(),
        'fibo_ci95_bps':(np.quantile(distribution[:,0],[.025,.975])*10000).tolist(),
        'control_ci95_bps':(np.quantile(distribution[:,1],[.025,.975])*10000).tolist(),
        'bootstrap_samples':samples,'nonempty_bootstrap_draws':int(valid.sum()),'block_weeks':4,'selection_adjusted':False}


def evaluate():
    verify_sources()
    if (ART/'RESULTS.json').exists():raise FileExistsError('Results already frozen')
    match=r.read(ART/'MATCHES.json');manifest=r.read(ART/'funding/MANIFEST.json')
    assert manifest['all_passed'] and manifest['requirements_sha256']==r.sha(ART/'funding/REQUIREMENTS.json')
    pairs=match['pairs'];requests=defaultdict(set)
    for p in pairs:
        for symbol in (p['symbol'],p['control']['symbol']):requests[symbol].add(p['entry_ts'])
    cache={}
    for i,(symbol,entries) in enumerate(sorted(requests.items()),1):
        bars=load_bars(symbol);meta=manifest['symbols'][symbol];assert r.sha(meta['path'])==meta['sha256']
        funding=pd.read_parquet(meta['path']);stamps=funding.funding_ts_ms.to_numpy()
        assert np.all(np.diff(stamps)>0) and f.START_MS<=stamps[0]<=stamps[-1]<f.LIMIT_MS
        for t in entries:
            price=fixed_horizon_prices(bars,t)
            if price['status']!='COMPLETE':cache[(symbol,t)]=price;continue
            a=t*1000;b=(t+DAY)*1000
            assert stamps[0]<=a and stamps[-1]>=b
            lo=np.searchsorted(stamps,a,side='right');hi=np.searchsorted(stamps,b,side='right')
            around=stamps[max(0,lo-1):min(len(stamps),hi+1)]
            assert np.max(np.diff(around))<=8*3600000+15000,'Funding gap in holding period'
            events=funding.iloc[lo:hi].to_dict('records')
            cache[(symbol,t)]={**price,'symbol':symbol,'scenarios':{name:unit_outcome(price,events,scenario) for name,scenario in x.SCENARIOS.items()}}
        if i%25==0:print(f'Fixed24h outcomes {i}/{len(requests)} symbols',flush=True)
    complete={name:[] for name in x.SCENARIOS};incomplete=[]
    for p in pairs:
        t=p['entry_ts'];a=cache[(p['symbol'],t)];b=cache[(p['control']['symbol'],t)]
        if a['status']!='COMPLETE' or b['status']!='COMPLETE':
            incomplete.append({'id':p['id'],'entry_ts':t,'treated_status':a['status'],'control_status':b['status']});continue
        for name in x.SCENARIOS:
            complete[name].append({'id':p['id'],'entry_ts':t,'treated_symbol':p['symbol'],'control_symbol':p['control']['symbol'],
                'treated':a['scenarios'][name],'control':b['scenarios'][name]})
    splits={'development_2020_2022':('2020-01-01','2023-01-01'),'validation_2023':('2023-01-01','2024-01-01'),
        'retrospective_oos_2024_2025':('2024-01-01','2026-01-01'),'all_2020_2025':('2020-01-01','2026-01-01')}
    results={name:{'splits':{label:paired_statistics(rows,*dates) for label,dates in splits.items()},
        'annual':{str(y):paired_statistics(rows,f'{y}-01-01',f'{y+1}-01-01') for y in range(2020,2026)}} for name,rows in complete.items()}
    supported=not incomplete and all(v['splits']['retrospective_oos_2024_2025'].get('pairs',0)>=200 and
        v['splits']['retrospective_oos_2024_2025']['paired_difference_ci95_bps'][0]>0 for v in results.values())
    path=ART/'EVENT_LEDGER.json.gz'
    with gzip.open(path,'wt',encoding='utf8') as out:json.dump({'scenarios':complete,'incomplete':incomplete},out,separators=(',',':'),allow_nan=False)
    sd=np.array([p['standardized_difference'] for p in pairs])
    balance={'mean_standardized_control_minus_fibo':sd.mean(axis=0).tolist() if len(sd) else [],
        'max_abs_standardized_difference':np.abs(sd).max(axis=0).tolist() if len(sd) else [],
        'features':FEATURES,'control_reuse_counts':dict(Counter((p['control']['symbol'] for p in pairs))),
        'unique_control_symbol_times':len({(p['control']['symbol'],p['entry_ts']) for p in pairs})}
    r.save(ART/'RESULTS.json',{'version':'4.0.11','results':results,'matched_pairs':len(pairs),'incomplete_pairs':incomplete,
        'sampling':{k:match[k] for k in ('sampled_events','raw_elite_candidates','sampling_rejections','unmatched_reasons')},
        'balance':balance,'incremental_diagnostic_support':supported,'fresh_oos':False,'goal_complete':False,
        'post_2025_backtest_observations':0,'live_signoff':'NOT_GRANTED','protocol_sha256':r.sha(ART/'PROTOCOL.json'),
        'matches_sha256':r.sha(ART/'MATCHES.json'),'ledger_sha256':r.sha(path),'funding_manifest_sha256':r.sha(ART/'funding/MANIFEST.json')})
    r.save(ART/'PROGRESS.json',{'stage':'matched_event_study_evaluated','goal_complete':False,'next_action':'independent verification and mini-alpha log'})
    print(json.dumps({'matched_pairs':len(pairs),'incomplete_pairs':len(incomplete),'primary':{k:v['splits']['retrospective_oos_2024_2025'] for k,v in results.items()},'incremental_diagnostic_support':supported}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','match','funding','evaluate']);args=parser.parse_args()
    {'freeze':freeze,'match':match,'funding':acquire_funding,'evaluate':evaluate}[args.action]()
