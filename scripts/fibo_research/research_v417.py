"""Matched original-bracket mechanism test with fixed unit notional per leg."""
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
import argparse,gzip,json,pickle,shutil
import numpy as np
import pandas as pd
import research_v416 as prev

r=prev.r;x=prev.x;f=prev.f;ROOT=prev.ROOT;PRIOR=prev.ART;ART=ROOT/'artifacts/fibo_trend_short/research_v4_0_17'
SPLITS=prev.SPLITS;SCENARIOS=x.SCENARIOS


def register():
    prev.verify_sources()
    if (ART/'PROTOCOL.json').exists():raise FileExistsError('Already frozen')
    protocol=r.read(PRIOR/'NEXT_MECHANISM_PROTOCOL.json')
    protocol.update(version='4.0.17',registered_at_utc=datetime.now(timezone.utc).isoformat(),cost_scenarios=SCENARIOS,
        parent_protocol_sha256=r.sha(PRIOR/'NEXT_MECHANISM_PROTOCOL.json'),
        holding_path_quality='Audit actual holding path through terminal bar; missing bars after a valid early exit are irrelevant. An observed final close before nominal horizon is truncated, never a valid forced horizon exit.',
        funding_event_order='Use remaining quantity immediately BEFORE each bar close; funding at the same timestamp precedes grouped exit fills. Same5m aggregation convention as v409; intrabar settlement order is not directly observed.',
        incomplete='Keep every matched pair. If either leg has incomplete path, no economic pair outcome; count missing separately and block diagnostic support. Zero-volume fill/settlement issues retain modeled outcomes but block support.')
    r.save(ART/'PROTOCOL.json',protocol)
    sources=[Path(__file__),ROOT/'scripts/fibo_research/verify_research_v417.py',ROOT/'tests/unit/fibo_short/test_research_v417.py',
             ROOT/'scripts/fibo_research/verify_research_v416.py',ROOT/'scripts/fibo_research/report_research_v416.py',
             Path(prev.__file__),Path(x.__file__),Path(f.__file__),Path(r.__file__)]
    for p in sources:
        dest=ART/'source_snapshot'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    inputs=[PRIOR/'CHECKPOINT.json',PRIOR/'MATCHES.json',PRIOR/'NEXT_MECHANISM_PROTOCOL.json',prev.PRIOR/'DATA_MANIFEST.json',prev.PRIOR/'CANDIDATE_MANIFEST.json',prev.PRIOR/'EVENTS.json']
    r.save(ART/'SOURCE_MANIFEST.json',{'sources':{str(p):r.sha(p) for p in sources},'inputs':{str(p):r.sha(p) for p in inputs},'protocol_sha256':r.sha(ART/'PROTOCOL.json')})
    print('Matched original-bracket protocol frozen.',flush=True)


def verify_sources():
    m=r.read(ART/'SOURCE_MANIFEST.json');assert m['protocol_sha256']==r.sha(ART/'PROTOCOL.json')
    for group in ('sources','inputs'):
        for p,h in m[group].items():assert r.sha(p)==h,p


def originals():
    needed={p['id'] for p in r.read(PRIOR/'MATCHES.json')['pairs']};out={}
    for s,a in r.read(prev.PRIOR/'CANDIDATE_MANIFEST.json')['symbols'].items():
        assert r.sha(a['path'])==a['sha256']
        for c in prev.data.v.load_rows(a['path']):
            if c['id'] in needed:out[c['id']]=c
    assert set(out)==needed
    return out


def build_leg(frame,c,symbol,side,events):
    t=c['entry_ts'];end=t+(72 if c['tf']=='4h' else 120)*3600;assert end<=prev.END
    stamps=r.epoch_seconds(frame.index);i=int(np.searchsorted(stamps,t));j=int(np.searchsorted(stamps,end))
    result={'id':c['id'],'symbol':symbol,'side':side,'tf':c['tf'],'entry_ts':t,'horizon_end':end}
    if i==len(stamps) or stamps[i]!=t:return {**result,'status':'NOT_EVALUABLE','reason':'missing_scheduled_entry'}
    entry=float(frame.iloc[i]['open']);scale=entry/c['entry']
    stop=c['stop'] if side=='treated' else c['stop']*scale
    targets=c['targets'] if side=='treated' else [p*scale for p in c['targets']]
    if side=='treated':assert entry==c['entry']
    bars=[(int(ts),*map(float,row)) for ts,row in zip(stamps[i:j],frame.iloc[i:j][['open','high','low','close']].to_numpy())]
    path=r.simulate_path(bars,entry,stop,targets,'ladder');used=frame.iloc[i:int(np.searchsorted(stamps,path['exit_ts']))]
    expected_end=end if path['exit_reason']=='horizon' else path['exit_ts'];missing=int((expected_end-t)//300-len(used))
    truncated=path['exit_reason']=='horizon' and path['exit_ts']<end
    quality={'missing_bars':missing,'horizon_truncated':truncated,'zero_volume_entry':bool(used.iloc[0].volume<=0),
        'zero_volume_exit_groups':sum(bool(used.iloc[k].volume<=0) for k,row in enumerate(path['trace']) if row[2]>row[3]),
        'zero_volume_holding_bars':int((used.volume<=0).sum()),
        'settlement_overlaps':[e['settlement_at'] for e in events if e['symbol']==symbol and t<r.utc(e['settlement_at']).timestamp()<=path['exit_ts']]}
    if side=='treated':assert path==c['paths']['ladder'],'Treated path differs from frozen original'
    return {**result,'status':'NOT_EVALUABLE' if missing or truncated else 'COMPLETE','entry':entry,'stop':stop,'targets':targets,'paths':{'ladder':path},'quality':quality}


def prepare():
    verify_sources()
    if (ART/'PATH_MANIFEST.json').exists():raise FileExistsError('Paths already frozen')
    pairs=r.read(PRIOR/'MATCHES.json')['pairs'];source=originals();events=r.read(prev.PRIOR/'EVENTS.json')['events'];requests=defaultdict(list);legs={};issues=[]
    for p in pairs:
        for side,s in [('treated',p['symbol']),('control',p['control']['symbol'])]:requests[s].append((p['id'],side))
    for n,(s,items) in enumerate(sorted(requests.items()),1):
        frame=prev.load_bars(s)
        for cid,side in items:
            leg=build_leg(frame,source[cid],s,side,events);key=f'{cid}/{side}';legs[key]=leg;q=leg.get('quality',{})
            if leg['status']!='COMPLETE' or q.get('zero_volume_entry') or q.get('zero_volume_exit_groups') or q.get('settlement_overlaps'):issues.append({'key':key,'status':leg['status'],'quality':q})
        if n%30==0:print(f'Original bracket paths {n}/{len(requests)} symbols',flush=True)
    path=ART/'PATHS.pkl.gz'
    with gzip.open(path,'wb') as fh:pickle.dump(legs,fh,protocol=5)
    needed={}
    for leg in legs.values():
        if leg['status']!='COMPLETE':continue
        s=leg['symbol'];a=needed.setdefault(s,{'first_entry_ms':leg['entry_ts']*1000,'last_exit_ms':leg['paths']['ladder']['exit_ts']*1000,'candidates':0})
        a['first_entry_ms']=min(a['first_entry_ms'],leg['entry_ts']*1000);a['last_exit_ms']=max(a['last_exit_ms'],leg['paths']['ladder']['exit_ts']*1000);a['candidates']+=1
    for a in needed.values():a.update(start_ms=max(f.START_MS,a['first_entry_ms']-16*3600000),end_ms=min(f.LIMIT_MS-1,a['last_exit_ms']+16*3600000))
    r.save(ART/'PATH_MANIFEST.json',{'path_sha256':r.sha(path),'matches_sha256':r.sha(PRIOR/'MATCHES.json'),'protocol_sha256':r.sha(ART/'PROTOCOL.json'),
        'pairs':len(pairs),'legs':len(legs),'treated_original_paths_exact':len(pairs),'issues':issues,'holding_zero_volume_legs':sum(a.get('quality',{}).get('zero_volume_holding_bars',0)>0 for a in legs.values())})
    r.save(ART/'funding/REQUIREMENTS.json',needed)
    print({'pairs':len(pairs),'legs':len(legs),'issues':len(issues),'funding_symbols':len(needed)},flush=True)


def load_paths():
    m=r.read(ART/'PATH_MANIFEST.json');assert m['path_sha256']==r.sha(ART/'PATHS.pkl.gz') and m['matches_sha256']==r.sha(PRIOR/'MATCHES.json')
    with gzip.open(ART/'PATHS.pkl.gz','rb') as fh:return pickle.load(fh)


def acquire_funding():
    verify_sources();needs=r.read(ART/'funding/REQUIREMENTS.json');choices=defaultdict(list);records={};pending={}
    for version in [16,15,12,11,10,9]:
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


def outcome(leg,events,scenario):
    assert leg['status']=='COMPLETE';qty=1/leg['entry'];path=leg['paths']['ladder'];steps=x.execution_steps(leg)
    fills=[{**x.fill('SELL',leg['entry'],qty,**scenario),'timestamp_ms':leg['entry_ts']*1000}]
    for t,mark,before,after,active,delta,done,closed,price in steps:
        if closed>1e-10:fills.append({**x.fill('BUY',price,qty*closed,**scenario),'timestamp_ms':t})
    times=np.array([a[0] for a in path['trace']])*1000;payments=[]
    for ev in events:
        if not leg['entry_ts']*1000<ev['funding_ts_ms']<=path['exit_ts']*1000:continue
        i=int(np.searchsorted(times,ev['funding_ts_ms'],side='left'))-1;rem=path['trace'][i][3] if i>=0 else 1.
        payments.append({**ev,'remaining_qty':qty*rem,'cashflow':qty*rem*ev['mark_price']*ev['funding_rate']})
    fees=sum(a['fee'] for a in fills);slip=sum(a['slippage_cost'] for a in fills);fund=sum(a['cashflow'] for a in payments)
    net=fills[0]['notional']-sum(a['notional'] for a in fills[1:])-fees+fund
    assert abs(net-(path['gross_return']-fees-slip+fund))<1e-9
    return {'net_return':net,'gross_reference_return':path['gross_return'],'fees':fees,'slippage':slip,'funding':fund,'qty':qty,
        'fills':fills,'funding_events':payments,'proxy_payments':sum(a['price_source']!='funding_api_settlement_mark' for a in payments),
        'exit_ts':path['exit_ts'],'exit_reason':path['exit_reason'],'hold_hours':(path['exit_ts']-leg['entry_ts'])/3600}


def evaluate():
    verify_sources();assert not (ART/'RESULTS.json').exists();check=r.read(ART/'INPUT_VERIFICATION.json')
    assert check['all_passed'] and check['path_manifest_sha256']==r.sha(ART/'PATH_MANIFEST.json') and check['funding_manifest_sha256']==r.sha(ART/'funding/MANIFEST.json')
    meta=r.read(ART/'funding/MANIFEST.json');assert meta['all_passed'];fund={}
    for s,a in meta['symbols'].items():
        assert r.sha(a['path'])==a['sha256'];frame=pd.read_parquet(a['path']);fund[s]=(frame.funding_ts_ms.to_numpy(),frame)
    legs=load_paths();pairs=r.read(PRIOR/'MATCHES.json')['pairs'];complete={name:[] for name in SCENARIOS};incomplete=[]
    for p in pairs:
        a=legs[p['id']+'/treated'];b=legs[p['id']+'/control']
        if a['status']!='COMPLETE' or b['status']!='COMPLETE':incomplete.append({'id':p['id'],'entry_ts':p['entry_ts'],'treated_status':a['status'],'control_status':b['status']});continue
        values={}
        for side,leg in [('treated',a),('control',b)]:
            ts,frame=fund[leg['symbol']];left=leg['entry_ts']*1000;right=leg['paths']['ladder']['exit_ts']*1000
            assert ts[0]<=left<=right<=ts[-1];lo=np.searchsorted(ts,left,side='right');hi=np.searchsorted(ts,right,side='right')
            nearby=ts[max(0,lo-1):min(len(ts),hi+1)];assert np.max(np.diff(nearby))<=8*3600000+15000
            events=frame.iloc[lo:hi].to_dict('records');values[side]={name:outcome(leg,events,scenario) for name,scenario in SCENARIOS.items()}
        for name in SCENARIOS:complete[name].append({'id':p['id'],'entry_ts':p['entry_ts'],'treated_symbol':a['symbol'],'control_symbol':b['symbol'],'treated':values['treated'][name],'control':values['control'][name]})
    results={name:{'splits':{label:prev.paired_statistics(rows,*dates) for label,dates in SPLITS.items()},
        'annual':{str(y):prev.paired_statistics(rows,f'{y}-01-01',f'{y+1}-01-01') for y in range(2020,2026)}} for name,rows in complete.items()}
    issues=r.read(ART/'PATH_MANIFEST.json')['issues'];support=not incomplete and not issues and all(a['splits']['retrospective_oos_2024_2025'].get('pairs',0)>=200 and a['splits']['retrospective_oos_2024_2025']['paired_difference_ci95_bps'][0]>0 for a in results.values())
    p=ART/'EVENT_LEDGER.json.gz'
    with gzip.open(p,'wt',encoding='utf8') as fh:json.dump({'scenarios':complete,'incomplete':incomplete},fh,separators=(',',':'),allow_nan=False)
    r.save(ART/'RESULTS.json',{'version':'4.0.17','results':results,'matched_pairs':len(pairs),'incomplete_pairs':incomplete,'quality_issues':issues,'incremental_diagnostic_support':support,
        'fresh_oos':False,'goal_complete':False,'post_2025_observations':0,'live_signoff':'NOT_GRANTED','ledger_sha256':r.sha(p),
        'path_manifest_sha256':r.sha(ART/'PATH_MANIFEST.json'),'protocol_sha256':r.sha(ART/'PROTOCOL.json'),'funding_manifest_sha256':r.sha(ART/'funding/MANIFEST.json')})
    print({'primary':{k:a['splits']['retrospective_oos_2024_2025'] for k,a in results.items()},'support':support},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['register','prepare','funding','evaluate']);a=p.parse_args();{'register':register,'prepare':prepare,'funding':acquire_funding,'evaluate':evaluate}[a.action]()
