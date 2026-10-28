"""Continuous-state portfolio and explicit year-end embargo attribution."""
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
import argparse,gzip,json,pickle,shutil
import numpy as np
import pandas as pd
import research_v418 as old
import research_v416 as data
import verify_lifecycle_fast_v414 as quality

r=old.r;x=old.x;b=old.b;source=old.source;f=data.f;ROOT=old.ROOT;PRIOR=old.ART;ART=ROOT/'artifacts/fibo_trend_short/research_v4_0_19'
SCENARIOS=x.SCENARIOS;ARMS=['annual_eligible_continuous','all_continuous'];START='2020-01-01';END='2026-01-01'
SPLITS={'development_context_2020_2023':('2020-01-01','2024-01-01'),'retrospective_oos_2024_2025':('2024-01-01','2026-01-01'),'all_2020_2025':(START,END)}


def annual_eligible(c):
    t=pd.Timestamp(c['entry_ts'],unit='s',tz='UTC');return t<r.utc(f'{t.year+1}-01-01')-pd.Timedelta(days=5)


def register():
    source.verify_sources()
    if (ART/'PROTOCOL.json').exists():raise FileExistsError('Already frozen')
    p=r.read(PRIOR/'NEXT_CONTINUOUS_PROTOCOL.json');p.update(version='4.0.19',registered_at_utc=datetime.now(timezone.utc).isoformat(),
        parent_protocol_sha256=r.sha(PRIOR/'NEXT_CONTINUOUS_PROTOCOL.json'),arms=ARMS,splits=SPLITS,
        subperiod_boundary='NAV at start/end uses state after all events at that exact timestamp. Include subsequent cash events through end. Carry-in positions remain open; subperiod entries are not the source of all subperiod PnL.',
        source_overlap='Any replacement funding snapshot must match every overlapping v415 event exactly before outcomes. No silent funding-data revision.')
    r.save(ART/'PROTOCOL.json',p)
    sources=[Path(__file__),ROOT/'scripts/fibo_research/verify_research_v419.py',ROOT/'tests/unit/fibo_short/test_research_v419.py',
        ROOT/'scripts/fibo_research/verify_research_v416.py',ROOT/'scripts/fibo_research/verify_research_v417.py',ROOT/'tests/unit/fibo_short/test_execution_v409.py',
        Path(old.__file__),Path(data.__file__),Path(quality.__file__),Path(x.__file__),Path(b.statistics.__file__),Path(f.__file__)]
    for path in sources:
        dest=ART/'source_snapshot'/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    inputs=[PRIOR/'CHECKPOINT.json',PRIOR/'NEXT_CONTINUOUS_PROTOCOL.json',b.ART/'CHECKPOINT.json',b.ART/'CANDIDATE_MANIFEST.json',b.ART/'PRIMARY_CANDIDATES.pkl.gz',b.ART/'funding/MANIFEST.json']
    r.save(ART/'SOURCE_MANIFEST.json',{'sources':{str(p):r.sha(p) for p in sources},'inputs':{str(p):r.sha(p) for p in inputs},'protocol_sha256':r.sha(ART/'PROTOCOL.json')})
    print('Continuous state and embargo decomposition frozen.',flush=True)


def verify_sources():
    source.verify_sources();p=r.read(ART/'SOURCE_MANIFEST.json');assert p['protocol_sha256']==r.sha(ART/'PROTOCOL.json')
    for group in ('sources','inputs'):
        for path,h in p[group].items():assert r.sha(path)==h,path


def prepare():
    verify_sources()
    if (ART/'CANDIDATE_AUDIT.json').exists():raise FileExistsError('Prepared inputs already frozen')
    baseline={c['id']:c for c in source.load_candidates()};all_rows=[];extra=[];reconciled=0;manifest=r.read(b.ART/'CANDIDATE_MANIFEST.json');members=r.read(b.ART/'MEMBERSHIP.json');events=r.read(b.ART/'EVENTS.json')['events'];checks=[];issues=[]
    for s,a in manifest['symbols'].items():
        assert r.sha(a['path'])==a['sha256']
        for c in data.data.v.load_rows(a['path']):
            if not r.passes(c,'elite_sniper'):continue
            assert r.utc(START).timestamp()<=c['entry_ts']<r.utc(END).timestamp()-5*86400
            all_rows.append(c)
            if annual_eligible(c):assert c==baseline[c['id']];reconciled+=1
            else:assert c['id'] not in baseline;extra.append(c)
    assert reconciled==len(baseline) and {c['id'] for c in all_rows}==set(baseline)|{c['id'] for c in extra}
    for s in sorted({c['symbol'] for c in extra}):
        frame=data.load_bars(s)
        for c in (c for c in extra if c['symbol']==s):
            t=pd.Timestamp(c['entry_ts'],unit='s',tz='UTC');assert s in {a['symbol'] for a in members[t.strftime('%Y-%m')]} and data.data.allowed_entry(c,events)
            applicable=[e for e in events if e['symbol']==s and (not e.get('relaunch_at') or t<r.utc(e['relaunch_at']))]
            a=quality.independent_quality(c,frame,applicable);record={'id':c['id'],'symbol':s,'entry_utc':t.isoformat(),**a};checks.append(record)
            used=frame.loc[t:pd.Timestamp(c['paths']['ladder']['exit_ts'],unit='s',tz='UTC')-pd.Timedelta(nanoseconds=1)]
            rawbars=[(int(ts),*map(float,row)) for ts,row in zip(r.epoch_seconds(used.index),used[['open','high','low','close']].to_numpy())]
            assert r.simulate_path(rawbars,c['entry'],c['stop'],c['targets'])==c['paths']['ladder']
            if any(a[k] for k in ('entry_zero_volume','zero_volume_exit_groups','missing_bars_through_modelled_exit','horizon_truncated','official_lifecycle_flags')):issues.append(record)
    with gzip.open(ART/'EXTRA_CANDIDATES.pkl.gz','wb') as fh:pickle.dump(extra,fh,protocol=5)
    needs={}
    for c in all_rows:
        s=c['symbol'];a=needs.setdefault(s,{'first_entry_ms':c['entry_ts']*1000,'last_exit_ms':c['paths']['ladder']['exit_ts']*1000,'candidates':0})
        a['first_entry_ms']=min(a['first_entry_ms'],c['entry_ts']*1000);a['last_exit_ms']=max(a['last_exit_ms'],c['paths']['ladder']['exit_ts']*1000);a['candidates']+=1
    for a in needs.values():a.update(start_ms=max(f.START_MS,a['first_entry_ms']-16*3600000),end_ms=min(f.LIMIT_MS-1,a['last_exit_ms']+16*3600000))
    r.save(ART/'funding/REQUIREMENTS.json',needs)
    r.save(ART/'CANDIDATE_AUDIT.json',{'baseline_exact':reconciled,'all_candidates':len(all_rows),'extra_candidates':len(extra),'extra':checks,'issues':issues,
        'extra_sha256':r.sha(ART/'EXTRA_CANDIDATES.pkl.gz'),'parent_candidate_manifest_sha256':r.sha(b.ART/'CANDIDATE_MANIFEST.json'),'post_2025_observations':0})
    print({'baseline':reconciled,'all':len(all_rows),'extra':len(extra),'issues':len(issues),'funding_symbols':len(needs)},flush=True)


def load_candidates(arm='all_continuous'):
    raw=source.load_candidates();a=r.read(ART/'CANDIDATE_AUDIT.json');assert not a['issues'] and a['extra_sha256']==r.sha(ART/'EXTRA_CANDIDATES.pkl.gz')
    assert len(raw)==a['baseline_exact']
    if arm=='annual_eligible_continuous':return raw
    assert arm=='all_continuous'
    with gzip.open(ART/'EXTRA_CANDIDATES.pkl.gz','rb') as fh:raw+=pickle.load(fh)
    assert len(raw)==a['all_candidates'];return raw


def load_funding():
    m=r.read(ART/'funding/MANIFEST.json');assert m['all_passed'] and m['requirements_sha256']==r.sha(ART/'funding/REQUIREMENTS.json');oldm=r.read(b.ART/'funding/MANIFEST.json');out={};overlap=0
    for s,a in m['symbols'].items():
        assert r.sha(a['path'])==a['sha256'];frame=pd.read_parquet(a['path']);ts=frame.funding_ts_ms.to_numpy();n=a['requirements']
        assert f.START_MS<=ts[0]<=n['first_entry_ms']<=n['last_exit_ms']<=ts[-1]<f.LIMIT_MS and np.all(np.diff(ts)>0)
        relevant=ts[(ts>=n['first_entry_ms']-8*3600000-15000)&(ts<=n['last_exit_ms']+8*3600000+15000)];assert len(relevant)>1 and np.diff(relevant).max()<=8*3600000+15000
        if s in oldm['symbols']:
            prev=oldm['symbols'][s];assert r.sha(prev['path'])==prev['sha256'];oldframe=pd.read_parquet(prev['path']);lo=max(ts[0],oldframe.funding_ts_ms.min());hi=min(ts[-1],oldframe.funding_ts_ms.max())
            left=frame.loc[frame.funding_ts_ms.between(lo,hi)].reset_index(drop=True);right=oldframe.loc[oldframe.funding_ts_ms.between(lo,hi)].reset_index(drop=True)
            pd.testing.assert_frame_equal(left,right,check_exact=True,check_dtype=False);overlap+=len(left)
        out[s]={'times':ts,'events':frame.to_dict('records')}
    return out,overlap


def fingerprint():return {'protocol_sha256':r.sha(ART/'PROTOCOL.json'),'source_manifest_sha256':r.sha(ART/'SOURCE_MANIFEST.json'),'candidate_audit_sha256':r.sha(ART/'CANDIDATE_AUDIT.json'),'funding_manifest_sha256':r.sha(ART/'funding/MANIFEST.json')}


def ledger(arm,scenario):
    with gzip.open(ART/'runs'/f'{arm}_{scenario}.json.gz','rt',encoding='utf8') as fh:return json.load(fh)


def run_node(raw,prepared,fund,arm,scenario):
    folder=ART/'runs';folder.mkdir(exist_ok=True);key=f'{arm}_{scenario}';receipt=folder/f'{key}.json';path=folder/f'{key}.json.gz';fp=fingerprint()
    if receipt.exists():
        a=r.read(receipt);assert all(a[k]==x for k,x in fp.items()) and a['ledger_sha256']==r.sha(path);return a['metric']
    metric=x.portfolio(raw,{'gate':'elite_sniper','sizing':'risk'},START,END,SCENARIOS[scenario],fund,prepared);detail={'ledger':metric.pop('ledger'),'curve':metric.pop('curve')};metric['curve_values']=[p[1] for p in detail['curve']]
    with gzip.open(path,'wt',encoding='utf8') as fh:json.dump(detail,fh,separators=(',',':'),allow_nan=False)
    r.save(receipt,{'metric':metric,'ledger_sha256':r.sha(path),**fp});print(f'{arm}/{scenario}: {metric["return_pct"]:+.4f}%, DD{metric["max_dd_pct"]:.4f}%, N={metric["trades"]}',flush=True);return metric


def marked_window(curve,start,end):
    a=int(r.utc(start).timestamp()*1000);c=int(r.utc(end).timestamp()*1000);arr=np.asarray(curve);assert np.all(np.diff(arr[:,0])>=0)
    i=np.searchsorted(arr[:,0],a,side='right')-1;j=np.searchsorted(arr[:,0],c,side='right')-1;assert i>=0 and j>=i
    points=[(a,float(arr[i,1])),*[(int(t),float(v)) for t,v in arr[i+1:j+1] if a<t<=c]]
    if points[-1][0]!=c:points.append((c,float(arr[j,1])))
    values=np.asarray([v for t,v in points]);series=pd.Series(values,index=pd.to_datetime([t for t,v in points],unit='ms',utc=True)).groupby(level=0).last()
    weekly,grid=b.statistics.calendar_returns(series,start,end)
    return {'start_nav':float(values[0]),'end_nav':float(values[-1]),'return_pct':float((values[-1]/values[0]-1)*100),'max_dd_pct':float(np.max(1-values/np.maximum.accumulate(values))*100),
        'calendar_weekly_ci95':b.statistics.interval(weekly)},weekly,grid


def baseline_curve(scenario):
    cash=100.;points=[]
    for y in range(2020,2026):
        node=b.ledger(y,scenario);points.extend((t,value*cash/100) for t,value in node['curve']);cash*=node['curve'][-1][1]/100
    return points


def evaluate():
    verify_sources();check=r.read(ART/'INPUT_VERIFICATION.json');assert check['all_passed'] and all(check[k]==a for k,a in fingerprint().items())
    assert not (ART/'RESULTS.json').exists();fund,_=load_funding();raw=load_candidates();prepared={c['id']:x.execution_steps(c) for c in raw};metrics={}
    for arm in ARMS:
        candidates=raw if arm=='all_continuous' else [c for c in raw if annual_eligible(c)]
        metrics[arm]={s:run_node(candidates,prepared,fund,arm,s) for s in SCENARIOS}
    periods={};differences={};carry={};accepted_extra={};extra_ids={a['id'] for a in r.read(ART/'CANDIDATE_AUDIT.json')['extra']}
    for label,(start,end) in SPLITS.items():
        periods[label]={};differences[label]={};carry[label]={}
        for scenario in SCENARIOS:
            base,weekly,grid=marked_window(baseline_curve(scenario),start,end);periods[label][scenario]={'annual_reset_baseline':base};differences[label][scenario]={};carry[label][scenario]={}
            for arm in ARMS:
                node=ledger(arm,scenario);value,returns,gg=marked_window(node['curve'],start,end);assert gg==grid;periods[label][scenario][arm]=value
                differences[label][scenario][arm+'_minus_annual']=b.statistics.interval(returns-weekly,alpha=.025)
                lo=int(r.utc(start).timestamp()*1000);hi=int(r.utc(end).timestamp()*1000)
                carry[label][scenario][arm]={'entered_in_period':sum(lo<=p['entry_ts_ms']<hi for p in node['ledger']),
                    'carried_in_ids':[p['id'] for p in node['ledger'] if p['entry_ts_ms']<lo<p['exit_ts_ms']],
                    'carried_out_ids':[p['id'] for p in node['ledger'] if p['entry_ts_ms']<hi<p['exit_ts_ms']]}
            _,a,_=marked_window(ledger(ARMS[0],scenario)['curve'],start,end);_,c,_=marked_window(ledger(ARMS[1],scenario)['curve'],start,end)
            differences[label][scenario]['all_minus_annual_eligible_continuous']=b.statistics.interval(c-a,alpha=.025)
    for scenario in SCENARIOS:accepted_extra[scenario]=[p['id'] for p in ledger('all_continuous',scenario)['ledger'] if p['id'] in extra_ids]
    r.save(ART/'RESULTS.json',{'version':'4.0.19','metrics':metrics,'periods':periods,'paired_differences':differences,'carry':carry,'accepted_year_end_extra':accepted_extra,
        'scenarios':SCENARIOS,'post_2025_observations':0,'fresh_oos':False,'goal_complete':False,'live_signoff':'NOT_GRANTED',**fingerprint()})
    print({'primary':periods['retrospective_oos_2024_2025'],'full':periods['all_2020_2025'],'accepted_extra':accepted_extra},flush=True)


def acquire_funding():
    verify_sources();needs=r.read(ART/'funding/REQUIREMENTS.json');choices=defaultdict(list);records={};pending={}
    for version in [15,17,16,12,11,10,9]:
        root=ROOT/f'artifacts/fibo_trend_short/research_v4_0_{version}'
        for s,a in r.read(root/'funding/MANIFEST.json')['symbols'].items():
            path=Path(a['path']) if 'path' in a else root/'funding/snapshots'/f'{s}.parquet';choices[s].append((root,path,a.get('record',a)))
    for s,n in needs.items():
        for root,p,a in choices[s]:
            if not a['gaps_over_8h'] and not a['local_differences_ms'] and a['first_event_ms']<=n['first_entry_ms']<=n['last_exit_ms']<=a['last_event_ms']:
                assert r.sha(p)==a['sha256'];records[s]={'mode':'reuse_verified','source_root':str(root),'path':str(p),'sha256':a['sha256'],'record':a,'requirements':n};break
        if s not in records:pending[s]=n
    r.save(ART/'funding/ACQUISITION_PLAN.json',{'reused':sorted(records),'new':sorted(pending),'requirements_sha256':r.sha(ART/'funding/REQUIREMENTS.json')})
    print(f'Funding: {len(records)} reused, {len(pending)} new bounded downloads.',flush=True)
    f.ART=ART;errors={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(f.fetch_symbol,s,n):s for s,n in pending.items()}
        for future in as_completed(jobs):
            s=jobs[future]
            try:
                _,a=future.result();assert not any(a[k] for k in ('gaps_over_8h','left_edge_uncovered','right_edge_uncovered','local_differences_ms'))
                records[s]={'mode':'new_official_download','source_root':str(ART),'path':str(ART/'funding/snapshots'/f'{s}.parquet'),'sha256':a['sha256'],'record':a,'requirements':needs[s]}
                print(f'Funding {len(records)}/{len(needs)} {s}',flush=True)
            except Exception as exc:errors[s]=str(exc);print(f'Funding issue {s}: {exc}',flush=True)
    r.save(ART/'funding/MANIFEST.json',{'symbols':records,'errors':errors,'all_passed':not errors and len(records)==len(needs),
        'requirements_sha256':r.sha(ART/'funding/REQUIREMENTS.json'),'reused_symbols':len(needs)-len(pending),'newly_acquired_symbols':len(pending)-len(errors)})
    if errors:raise RuntimeError(errors)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['register','prepare','funding','evaluate']);{'register':register,'prepare':prepare,'funding':acquire_funding,'evaluate':evaluate}[p.parse_args().action]()
