"""Frozen three-arm exit-policy experiment on the original coupled portfolio."""
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import argparse
import gzip
import json
from pathlib import Path
import pickle
import shutil

import numpy as np
import pandas as pd
import research_v411 as prev

r=prev.r;z=prev.z;q=prev.q;x=prev.x;f=prev.f
ART=r.ROOT/'artifacts/fibo_trend_short/research_v4_0_12'
PRIOR=prev.ART
ARMS=['original_elite_ladder','elite_initial_stop_only','elite_full_tp1']
SCENARIOS=x.SCENARIOS


def freeze():
    if (ART/'SOURCE_MANIFEST.json').exists():raise FileExistsError('Already frozen')
    ART.mkdir(parents=True,exist_ok=True)
    protocol=r.read(PRIOR/'NEXT_EXIT_ABLATION_PROTOCOL.json')
    protocol.update(version='4.0.12-research',status='FROZEN_BEFORE_NEW_PATHS_AND_OUTCOMES',
        source_frozen_at_utc=datetime.now(timezone.utc).isoformat(),scenarios=SCENARIOS,
        incomplete_paths='Keep future gaps visible. Stop-only closes at last observed price if the holding horizon is truncated, labels data_boundary_before_horizon and counts missing bars. Such accepted paths block complete-data claims; never drop or rematch based on future gaps.',
        calendar_inference='Join annually reset NAV curves by prior terminal NAV. Sample common Monday boundaries plus period endpoints; retain zero-return intervals and partial edge weeks. Primary intervals are97.5%, paired four-week circular blocks,10000 draws,seed412. Annual-grid v409 CI is retained for baseline equality; calendar CI is reported separately.',
        funding_reuse='Reuse a verified full-range snapshot from v409,v410,v411 where possible. All selected snapshot records overlapping v409 must agree exactly with its timestamp stream, rates, prices and provenance before baseline replay.',
        prior_hypothesis_sha256=r.sha(PRIOR/'NEXT_EXIT_ABLATION_PROTOCOL.json'))
    r.save(ART/'PROTOCOL.json',protocol)
    sources=[Path(__file__),r.ROOT/'scripts/fibo_research/verify_research_v412.py',r.ROOT/'tests/unit/fibo_short/test_research_v412.py',
        Path(z.__file__),Path(x.__file__),Path(f.__file__),Path(q.__file__),Path(r.__file__),Path(prev.__file__)]
    for p in sources:
        target=ART/'source_snapshot'/p.relative_to(r.ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    r.save(ART/'SOURCE_MANIFEST.json',{'sources':{str(p.relative_to(r.ROOT)):r.sha(p) for p in sources},
        'protocol_sha256':r.sha(ART/'PROTOCOL.json'),'prior_checkpoint_sha256':r.sha(PRIOR/'CHECKPOINT.json'),
        'v409_checkpoint_sha256':r.sha(z.ART/'CHECKPOINT.json'),'candidate_manifest_sha256':r.sha(q.ART/'history/CANDIDATE_MANIFEST.json'),
        'data_manifest_sha256':r.sha(q.ART/'history/DATA_MANIFEST.json')})
    r.save(ART/'PROGRESS.json',{'stage':'exit_ablation_protocol_frozen','goal_complete':False})


def verify_sources():
    s=r.read(ART/'SOURCE_MANIFEST.json')
    for path,digest in s['sources'].items():assert r.sha(r.ROOT/path)==digest,path
    for key,path in [('protocol_sha256',ART/'PROTOCOL.json'),('prior_checkpoint_sha256',PRIOR/'CHECKPOINT.json'),
        ('v409_checkpoint_sha256',z.ART/'CHECKPOINT.json'),('candidate_manifest_sha256',q.ART/'history/CANDIDATE_MANIFEST.json'),
        ('data_manifest_sha256',q.ART/'history/DATA_MANIFEST.json')]:assert s[key]==r.sha(path),str(path)


def stop_only_path(bars,entry,stop,horizon_end):
    if not stop>entry>0 or not bars:raise ValueError('Invalid stop-only trade')
    trace=[];previous=0.;reason='horizon';realized=0.
    for i,(opened,o,high,low,close) in enumerate(bars):
        done=high>=stop or i==len(bars)-1
        if high>=stop:price=max(stop,o);reason='stop'
        elif done:
            price=close;reason='horizon' if opened+300==horizon_end else 'data_boundary_before_horizon'
        if done:realized=(entry-price)/entry;total=realized
        else:total=(entry-close)/entry
        trace.append((int(opened+300),float(close),1.,0. if done else 1.,float(stop),float(total-previous),bool(done)))
        previous=total
        if done:break
    return {'trace':trace,'gross_return':float(realized),'exit_reason':reason,'exit_ts':trace[-1][0]}


def missing_bars(epochs,entry,end):
    used=epochs[(epochs>=entry)&(epochs<end)]
    return int((end-entry)//300-len(used))


def prepare():
    verify_sources()
    if (ART/'PATH_MANIFEST.json').exists():raise FileExistsError('Paths already prepared')
    q.setup_context();all_candidates=r.load_candidates('history');selected=[];excluded=Counter()
    for c in all_candidates:
        if not r.passes(c,'elite_sniper'):excluded['not_elite_sniper']+=1;continue
        year=pd.Timestamp(c['entry_ts'],unit='s',tz='UTC').year
        if c['entry_ts']>=int(r.utc(f'{year+1}-01-01').timestamp())-5*86400:excluded['year_end_entry_embargo']+=1;continue
        selected.append(c)
    grouped=defaultdict(list)
    for c in selected:grouped[c['symbol']].append(c)
    manifest={};requirements={};issues=[]
    for i,(symbol,items) in enumerate(sorted(grouped.items()),1):
        frame=prev.load_bars(symbol);epochs=r.epoch_seconds(frame.index);prices=frame[['open','high','low','close']].to_numpy()
        output=[]
        for c in items:
            start=c['entry_ts'];end=start+(72 if c['tf']=='4h' else 120)*3600
            assert end<=int(q.END.timestamp())
            left=np.searchsorted(epochs,start);right=np.searchsorted(epochs,end)
            assert epochs[left]==start
            bars=[(int(t),*map(float,p)) for t,p in zip(epochs[left:right],prices[left:right])]
            path=stop_only_path(bars,c['entry'],c['stop'],end)
            paths={ARMS[0]:c['paths']['ladder'],ARMS[1]:path,ARMS[2]:c['paths']['tp1']}
            quality={}
            for arm,p in paths.items():
                expected=end if p['exit_reason'] in ('horizon','data_boundary_before_horizon') else p['exit_ts']
                gap=missing_bars(epochs,start,expected)
                quality[arm]={'missing_bars':gap,'nominal_horizon_end':end,'horizon_truncated':p['exit_reason'] in ('horizon','data_boundary_before_horizon') and p['exit_ts']<end}
                if gap:issues.append({'id':c['id'],'arm':arm,**quality[arm]})
            output.append({**c,'research_paths':paths,'research_quality':quality})
        path=ART/'paths'/f'{symbol}.pkl.gz';path.parent.mkdir(exist_ok=True)
        with gzip.open(path,'wb') as fh:pickle.dump(output,fh,protocol=5)
        manifest[symbol]={'sha256':r.sha(path),'candidates':len(output)}
        first=min(c['entry_ts'] for c in output)*1000
        last=max(p['exit_ts'] for c in output for p in c['research_paths'].values())*1000
        requirements[symbol]={'first_entry_ms':first,'last_exit_ms':last,'start_ms':max(f.START_MS,first-16*3600000),
            'end_ms':min(f.LIMIT_MS-1,last+16*3600000),'candidates':len(output)}
        if i%20==0:print(f'Exit paths {i}/{len(grouped)} symbols',flush=True)
    r.save(ART/'PATH_MANIFEST.json',{'symbols':manifest,'raw_source_candidates':len(all_candidates),'selected_candidates':len(selected),
        'excluded':dict(excluded),'future_path_quality_issues':issues,'protocol_sha256':r.sha(ART/'PROTOCOL.json')})
    r.save(ART/'funding/REQUIREMENTS.json',requirements)
    r.save(ART/'PROGRESS.json',{'stage':'all_three_exit_paths_prepared','goal_complete':False,'future_path_issues':len(issues)})
    print(json.dumps({'candidates':len(selected),'symbols':len(grouped),'future_path_issues':len(issues)}),flush=True)


def load_candidates():
    meta=r.read(ART/'PATH_MANIFEST.json');out=[]
    assert meta['protocol_sha256']==r.sha(ART/'PROTOCOL.json')
    for symbol,item in meta['symbols'].items():
        path=ART/'paths'/f'{symbol}.pkl.gz';assert r.sha(path)==item['sha256']
        with gzip.open(path,'rb') as fh:rows=pickle.load(fh)
        assert len(rows)==item['candidates'];out.extend(rows)
    return out


def arm_candidates(candidates,arm):
    return [{**c,'paths':{'ladder':c['research_paths'][arm]},
        'missing_execution_bars':c['missing_execution_bars'] if arm==ARMS[0] else c['research_quality'][arm]['missing_bars']} for c in candidates]


def acquire_funding():
    verify_sources();needed=r.read(ART/'funding/REQUIREMENTS.json')
    prior_manifests=[(PRIOR,r.read(PRIOR/'funding/MANIFEST.json')),(prev.PRIOR,r.read(prev.PRIOR/'funding/MANIFEST.json'))]
    old=r.read(z.ART/'funding/MANIFEST.json');records={};pending={}
    for symbol,need in needed.items():
        choices=[]
        for root,manifest in prior_manifests:
            if symbol in manifest['symbols']:
                item=manifest['symbols'][symbol];choices.append((str(root),Path(item['path']),item['record']))
        if symbol in old['symbols']:choices.append((str(z.ART),z.ART/'funding/snapshots'/f'{symbol}.parquet',old['symbols'][symbol]))
        for root,path,record in choices:
            if not record['gaps_over_8h'] and not record['local_differences_ms'] and record['first_event_ms']<=need['first_entry_ms'] and record['last_event_ms']>=need['last_exit_ms']:
                assert r.sha(path)==record['sha256']
                records[symbol]={'mode':'reuse_verified','source_root':root,'path':str(path),'sha256':record['sha256'],'record':record,'requirements':need};break
        if symbol not in records:pending[symbol]=need
    f.ART=ART;errors={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(f.fetch_symbol,s,n):s for s,n in pending.items()}
        for future in as_completed(futures):
            symbol=futures[future]
            try:
                _,record=future.result()
                assert not record['gaps_over_8h'] and not record['left_edge_uncovered'] and not record['right_edge_uncovered'] and not record['local_differences_ms']
                records[symbol]={'mode':'new_official_download','source_root':str(ART),'path':str(ART/'funding/snapshots'/f'{symbol}.parquet'),
                    'sha256':record['sha256'],'record':record,'requirements':needed[symbol]}
                print(f'Funding complete {len(records)}/{len(needed)} {symbol}',flush=True)
            except Exception as exc:errors[symbol]=str(exc);print(f'Funding issue {symbol}: {exc}',flush=True)
    r.save(ART/'funding/MANIFEST.json',{'symbols':records,'all_passed':not errors and len(records)==len(needed),'errors':errors,
        'requirements_sha256':r.sha(ART/'funding/REQUIREMENTS.json'),'reused_symbols':len(needed)-len(pending),'newly_acquired_symbols':len(pending)-len(errors)})
    if errors:raise RuntimeError(errors)
    print(json.dumps({'symbols':len(records),'reused':len(needed)-len(pending),'new':len(pending)}),flush=True)


def load_funding():
    meta=r.read(ART/'funding/MANIFEST.json');assert meta['all_passed'] and meta['requirements_sha256']==r.sha(ART/'funding/REQUIREMENTS.json')
    out={};overlap=0
    for symbol,item in meta['symbols'].items():
        assert r.sha(item['path'])==item['sha256']
        frame=pd.read_parquet(item['path']);ts=frame.funding_ts_ms.to_numpy();need=item['requirements']
        assert f.START_MS<=ts[0]<=need['first_entry_ms']<=need['last_exit_ms']<=ts[-1]<f.LIMIT_MS
        assert np.all(np.diff(ts)>0) and np.isfinite(frame[['funding_rate','mark_price']]).all().all() and (frame.mark_price>0).all()
        prior=pd.read_parquet(z.ART/'funding/snapshots'/f'{symbol}.parquet')
        lo=max(prior.funding_ts_ms.min(),ts[0]);hi=min(prior.funding_ts_ms.max(),ts[-1])
        a=frame.loc[frame.funding_ts_ms.between(lo,hi)].reset_index(drop=True)
        b=prior.loc[prior.funding_ts_ms.between(lo,hi)].reset_index(drop=True)
        pd.testing.assert_frame_equal(a,b,check_exact=True,check_dtype=False)
        overlap+=len(a);out[symbol]={'times':ts,'events':frame.to_dict('records')}
    return out,overlap


def fingerprint():
    return {name:r.sha(ART/path) for name,path in [('protocol_sha256','PROTOCOL.json'),('source_manifest_sha256','SOURCE_MANIFEST.json'),
        ('path_manifest_sha256','PATH_MANIFEST.json'),('funding_manifest_sha256','funding/MANIFEST.json')]}


def run_node(candidates,prepared,arm,year,scenario,funding):
    folder=ART/'runs';folder.mkdir(exist_ok=True)
    key=f'{year}_{arm}_{scenario}';summary=folder/f'{key}.json';ledger=folder/f'{key}.json.gz';fp=fingerprint()
    if summary.exists():
        saved=r.read(summary);assert all(saved[k]==val for k,val in fp.items()) and saved['ledger_sha256']==r.sha(ledger)
        return saved['metric']
    result=x.portfolio(candidates,{'gate':'elite_sniper','sizing':'risk'},f'{year}-01-01',f'{year+1}-01-01',SCENARIOS[scenario],funding,prepared)
    detailed={'ledger':result.pop('ledger'),'curve':result.pop('curve')};result['curve_values']=[p[1] for p in detailed['curve']]
    with gzip.open(ledger,'wt',encoding='utf8') as fh:json.dump(detailed,fh,separators=(',',':'),allow_nan=False)
    r.save(summary,{'metric':result,'ledger_sha256':r.sha(ledger),**fp})
    print(f'{year}/{arm}/{scenario}: {result["return_pct"]:+.3f}%, DD {result["max_dd_pct"]:.3f}%, N={result["trades"]}',flush=True)
    return result


def node_ledger(year,arm,scenario):
    with gzip.open(ART/'runs'/f'{year}_{arm}_{scenario}.json.gz','rt',encoding='utf8') as fh:return json.load(fh)


def baseline():
    verify_sources();funding,overlap=load_funding();candidates=arm_candidates(load_candidates(),ARMS[0]);prepared={c['id']:x.execution_steps(c) for c in candidates}
    original=r.read(z.ART/'RESULTS.json');count=0
    for year in range(2020,2026):
        with gzip.open(z.ART/f'YEAR_{year}_LEDGERS.json.gz','rt',encoding='utf8') as fh:prior=json.load(fh)
        for scenario in SCENARIOS:
            metric=run_node(candidates,prepared,ARMS[0],year,scenario,funding)
            expected=original['annual'][str(year)]['elite_sniper_risk'][scenario]
            assert metric==expected,f'Original metric mismatch: {year}/{scenario}'
            assert node_ledger(year,ARMS[0],scenario)==prior[f'{year}/elite_sniper_risk/{scenario}'],f'Original ledger mismatch: {year}/{scenario}'
            count+=1
    r.save(ART/'BASELINE_RECONCILIATION.json',{'all_passed':True,'nodes_exactly_equal':count,'overlapping_funding_records_exactly_equal':overlap,
        'v409_results_sha256':r.sha(z.ART/'RESULTS.json'),'scope':'All metrics, complete curves and trade/fill/funding ledgers match v409 elite-sniper exactly.',**fingerprint()})
    print('Original v409 baseline matched exactly across all12 nodes.',flush=True)


def linked_curve(years,arm,scenario):
    points=[];capital=100.
    for year in years:
        curve=np.asarray(node_ledger(year,arm,scenario)['curve'],dtype=float)
        points.extend((int(t),float(value*capital/100)) for t,value in curve)
        capital*=curve[-1,1]/100
    series=pd.Series([p[1] for p in points],index=pd.to_datetime([p[0] for p in points],unit='ms',utc=True)).groupby(level=0).last().sort_index()
    return series


def calendar_returns(series,start,end):
    start=r.utc(start);end=r.utc(end)
    grid=pd.DatetimeIndex([start,end]).union(pd.date_range(start,end,freq='W-MON')).sort_values()
    values=series.reindex(series.index.union(grid)).sort_index().ffill().loc[grid]
    assert not values.isna().any()
    return values.pct_change().iloc[1:].to_numpy(),[p.isoformat() for p in grid[1:]]


def interval(values,alpha=.05,samples=10000):
    values=np.asarray(values,dtype=float);rng=np.random.default_rng(412)
    starts=rng.integers(0,len(values),size=(samples,(len(values)+3)//4))
    idx=((starts[:,:,None]+np.arange(4))%len(values)).reshape(samples,-1)[:,:len(values)]
    means=values[idx].mean(axis=1)*100
    return {'mean_weekly_pct':float(values.mean()*100),'ci_pct':np.quantile(means,[alpha/2,1-alpha/2]).tolist(),
        'confidence_pct':(1-alpha)*100,'intervals':len(values),'block_weeks':4,'draws':samples,'seed':412,'global_selection_adjusted':False}


def evaluate():
    verify_sources();baseline_check=r.read(ART/'BASELINE_RECONCILIATION.json')
    assert baseline_check['all_passed'] and all(baseline_check[k]==val for k,val in fingerprint().items())
    if (ART/'RESULTS.json').exists():raise FileExistsError('Results already frozen')
    funding,_=load_funding();raw=load_candidates();annual={str(y):{} for y in range(2020,2026)}
    for arm in ARMS:
        candidates=arm_candidates(raw,arm);prepared={c['id']:x.execution_steps(c) for c in candidates}
        for year in range(2020,2026):
            annual[str(year)][arm]={s:run_node(candidates,prepared,arm,year,s,funding) for s in SCENARIOS}
    periods={'reference_2020_2022':list(range(2020,2023)),'validation_2023':[2023],'retrospective_2024_2025':[2024,2025],'all_2020_2025':list(range(2020,2026))}
    summaries={};comparisons={};admissions={}
    for name,years in periods.items():
        summaries[name]={};comparisons[name]={};admissions[name]={}
        for scenario in SCENARIOS:
            returns={};grids={};summaries[name][scenario]={}
            for arm in ARMS:
                summary=z.linked([annual[str(y)][arm] for y in years],scenario)
                returns[arm],grids[arm]=calendar_returns(linked_curve(years,arm,scenario),f'{years[0]}-01-01',f'{years[-1]+1}-01-01')
                summary['calendar_weekly_ci95']=interval(returns[arm]);summaries[name][scenario][arm]=summary
            assert all(grids[a]==grids[ARMS[0]] for a in ARMS)
            comparisons[name][scenario]={other:{'difference':'original ladder minus alternative','paired_calendar_weekly_interval':interval(returns[ARMS[0]]-returns[other],alpha=.025)} for other in ARMS[1:]}
            trades={arm:{p['id'] for y in years for p in node_ledger(y,arm,scenario)['ledger']} for arm in ARMS}
            admissions[name][scenario]={arm:{'shared_with_original':len(trades[arm]&trades[ARMS[0]]),'only_original':len(trades[ARMS[0]]-trades[arm]),'only_alternative':len(trades[arm]-trades[ARMS[0]])} for arm in ARMS[1:]}
    r.save(ART/'RESULTS.json',{'version':'4.0.12','annual':annual,'periods':summaries,'comparisons':comparisons,'admission_changes':admissions,
        'arms':ARMS,'scenarios':SCENARIOS,'fresh_oos':False,'goal_complete':False,'live_signoff':'NOT_GRANTED','post_2025_backtest_observations':0,
        'baseline_reconciliation_sha256':r.sha(ART/'BASELINE_RECONCILIATION.json'),**fingerprint()})
    r.save(ART/'PROGRESS.json',{'stage':'exit_policy_comparison_evaluated','goal_complete':False,'next_action':'independent path, funding and NAV reconciliation'})
    print(json.dumps({'primary':summaries['retrospective_2024_2025'],'comparisons':comparisons['retrospective_2024_2025']}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','prepare','funding','baseline','evaluate']);args=parser.parse_args()
    {'freeze':freeze,'prepare':prepare,'funding':acquire_funding,'baseline':baseline,'evaluate':evaluate}[args.action]()
