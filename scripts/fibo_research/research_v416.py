"""Expanded point-in-time universe, frozen positive-momentum matched24h study."""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import argparse, gzip, json, shutil
import numpy as np
import pandas as pd
import research_v411 as method
import research_v415 as data

r=method.r; x=method.x; f=method.f; ROOT=r.ROOT
PRIOR=data.ART; ART=ROOT/'artifacts/fibo_trend_short/research_v4_0_16'
START=method.START; END=method.END; DAY=method.DAY
sample_events=method.sample_events; choose_control=method.choose_control
paired_statistics=method.paired_statistics; unit_outcome=method.unit_outcome
SPLITS={'development_2020_2022':('2020-01-01','2023-01-01'),'validation_2023':('2023-01-01','2024-01-01'),
        'retrospective_oos_2024_2025':('2024-01-01','2026-01-01'),'all_2020_2025':('2020-01-01','2026-01-01')}


def register():
    if (ART/'PROTOCOL.json').exists():raise FileExistsError('Already registered')
    data.verify_sources();old=r.read(method.ART/'PROTOCOL.json')
    old.update(version='4.0.16',registered_at_utc=datetime.now(timezone.utc).isoformat(),
        hypothesis='MA415-U1 follow-up: identical positive-momentum cross-sectional diagnostic on the corrected expanded PIT universe.',
        adaptive_context='v415 NAV and v411 old-universe matched results already observed. No new horizon, feature, caliper, gate or outcome selection. Not fresh OOS.',
        universe='Use v415 corrected monthly membership and disjoint contract-episode bars. Known close-only periods excluded as of entry for treated and control eligibility. Features must not bridge an episode gap.',
        quality='After locking controls, audit exact288-bar path, zero-volume entry/exit/holding and settlement overlaps. No favorable rematching. Incomplete grid is NOT_EVALUABLE; zero-fill/settlement flags block qualification, with numerical results retained.',
        predecessor_protocol_sha256=r.sha(PRIOR/'NEXT_CONFIRMATION_PROTOCOL.json'),prior_v411_protocol_sha256=r.sha(method.ART/'PROTOCOL.json'))
    r.save(ART/'PROTOCOL.json',old)
    sources=[Path(__file__),ROOT/'scripts/fibo_research/verify_research_v416.py',ROOT/'scripts/fibo_research/verify_research_v411.py',
             ROOT/'tests/unit/fibo_short/test_research_v416.py',ROOT/'tests/unit/fibo_short/test_research_v411.py',
             Path(method.__file__),Path(data.__file__),Path(x.__file__),Path(f.__file__),Path(r.__file__)]
    for p in sources:
        dest=ART/'source_snapshot'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    inputs=[PRIOR/'CHECKPOINT.json',PRIOR/'DATA_MANIFEST.json',PRIOR/'CANDIDATE_MANIFEST.json',PRIOR/'MEMBERSHIP.json',PRIOR/'EVENTS.json',
            method.ART/'CHECKPOINT.json',method.ART/'PROTOCOL.json']
    r.save(ART/'SOURCE_MANIFEST.json',{'sources':{str(p):r.sha(p) for p in sources},'inputs':{str(p):r.sha(p) for p in inputs},'protocol_sha256':r.sha(ART/'PROTOCOL.json')})
    print('v416 protocol and sources frozen before matching/outcomes.',flush=True)


def verify_sources():
    m=r.read(ART/'SOURCE_MANIFEST.json');assert m['protocol_sha256']==r.sha(ART/'PROTOCOL.json')
    for group in ('sources','inputs'):
        for p,h in m[group].items():assert r.sha(p)==h,p


def assemble_views(frames):
    frame=pd.concat(frames).sort_index();stamps=r.epoch_seconds(frame.index)
    assert len(stamps) and START<=stamps[0]<=stamps[-1]<END
    assert np.all(np.diff(stamps)>0) and np.all(stamps%300==0),'Overlapping or invalid episode bars'
    return frame


def load_bars(symbol):
    views=r.read(PRIOR/'DATA_MANIFEST.json')['views'][symbol];frames=[]
    for a in views:
        assert r.sha(a['path'])==a['sha256'];frames.append(pd.read_parquet(a['path']))
    return assemble_views(frames)


def load_candidates():
    rows=[];m=r.read(PRIOR/'CANDIDATE_MANIFEST.json')
    for s,a in m['symbols'].items():
        assert r.sha(a['path'])==a['sha256']
        for c in data.v.load_rows(a['path']):
            rows.append({k:c[k] for k in ('id','symbol','tf','wave_key','score','decision_ts','entry_ts','milestones')})
    assert len(rows)==r.read(PRIOR/'CANDIDATE_AUDIT.json')['all_candidates_checked']
    return rows


def eligible(symbol,entry_ts,events):
    return data.allowed_entry({'symbol':symbol,'entry_ts':entry_ts},events)


def match():
    verify_sources()
    if (ART/'MATCHES.json').exists():raise FileExistsError('Matches already locked')
    candidates=load_candidates();sampled,rejected,raw=sample_events(candidates)
    decisions=sorted({c['decision_ts'] for c in sampled});members=r.read(PRIOR/'MEMBERSHIP.json');events=r.read(PRIOR/'EVENTS.json')['events']
    symbols=sorted({p['symbol'] for rr in members.values() for p in rr});frames=[]
    for i,s in enumerate(symbols,1):
        bars=load_bars(s);features=method.feature_frame(bars,decisions);features['symbol']=s;frames.append(features)
        if i%30==0:print(f'Past-only features {i}/{len(symbols)}',flush=True)
    features=pd.concat(frames,ignore_index=True);features.to_parquet(ART/'FEATURES.parquet',index=False)
    lookup={(p.symbol,int(p.decision_ts)):{'symbol':p.symbol,'momentum':float(p.momentum),'volatility':float(p.volatility)} for p in features.itertuples()}
    active=defaultdict(set)
    for c in raw:active[c['decision_ts']].add(c['symbol'])
    pairs=[];unmatched=[];excluded=[]
    for c in sampled:
        t=c['decision_ts'];month=pd.Timestamp(t,unit='s',tz='UTC').strftime('%Y-%m');treated=lookup.get((c['symbol'],t))
        assert eligible(c['symbol'],c['entry_ts'],events),'Unexpected disallowed treated candidate'
        if treated is None:unmatched.append({**c,'reason':'treated_past_feature_missing'});continue
        pool=[]
        for a in members[month]:
            s=a['symbol']
            if s==c['symbol'] or s in active[t] or (s,t) not in lookup or lookup[(s,t)]['momentum']<=0:continue
            if not eligible(s,c['entry_ts'],events):excluded.append({'treated_id':c['id'],'symbol':s,'entry_ts':c['entry_ts']});continue
            pool.append(lookup[(s,t)])
        chosen,reason=choose_control(treated,pool)
        if reason:unmatched.append({**c,'reason':reason});continue
        pairs.append({**c,'treated':treated,**chosen,'exit_ts':c['entry_ts']+DAY,'month':month})
    r.save(ART/'MATCHES.json',{'pairs':pairs,'unmatched':unmatched,'sampled_events':len(sampled),'raw_elite_candidates':len(raw),
        'sampling_rejections':rejected,'unmatched_reasons':dict(Counter(p['reason'] for p in unmatched)),
        'known_lifecycle_control_exclusions':excluded,'features_sha256':r.sha(ART/'FEATURES.parquet'),'protocol_sha256':r.sha(ART/'PROTOCOL.json'),
        'locked_before_outcome_evaluation_at_utc':datetime.now(timezone.utc).isoformat()})
    needs={}
    for p in pairs:
        for s in (p['symbol'],p['control']['symbol']):
            a=needs.setdefault(s,{'first_entry_ms':p['entry_ts']*1000,'last_exit_ms':p['exit_ts']*1000,'candidates':0})
            a['first_entry_ms']=min(a['first_entry_ms'],p['entry_ts']*1000);a['last_exit_ms']=max(a['last_exit_ms'],p['exit_ts']*1000);a['candidates']+=1
    for a in needs.values():a.update(start_ms=max(f.START_MS,a['first_entry_ms']-16*3600000),end_ms=min(f.LIMIT_MS-1,a['last_exit_ms']+16*3600000))
    r.save(ART/'funding/REQUIREMENTS.json',needs)
    print({'sampled':len(sampled),'pairs':len(pairs),'unmatched':len(unmatched),'funding_symbols':len(needs),'lifecycle_exclusions':len(excluded)},flush=True)


def inspect_path(bars,entry_ts,events,symbol):
    p=method.fixed_horizon_prices(bars,entry_ts)
    if p['status']!='COMPLETE':return p
    stamps=r.epoch_seconds(bars.index);i=int(np.searchsorted(stamps,entry_ts));sl=bars.iloc[i:i+288]
    crossings=[ev['settlement_at'] for ev in events if ev['symbol']==symbol and entry_ts<int(r.utc(ev['settlement_at']).timestamp())<=entry_ts+DAY]
    p.update(zero_volume_entry=bool(sl.iloc[0].volume<=0),zero_volume_exit=bool(sl.iloc[-1].volume<=0),
             zero_volume_holding_bars=int((sl.volume<=0).sum()),settlement_overlaps=crossings)
    return p


def quality():
    verify_sources();pairs=r.read(ART/'MATCHES.json')['pairs'];events=r.read(PRIOR/'EVENTS.json')['events'];requests=defaultdict(set);items=[]
    for p in pairs:
        for s in (p['symbol'],p['control']['symbol']):requests[s].add(p['entry_ts'])
    for s,times in sorted(requests.items()):
        bars=load_bars(s)
        for t in sorted(times):items.append({'symbol':s,'entry_ts':t,**inspect_path(bars,t,events,s)})
    issues=[p for p in items if p['status']!='COMPLETE' or p.get('zero_volume_entry') or p.get('zero_volume_exit') or p.get('settlement_overlaps')]
    r.save(ART/'PATH_AUDIT.json',{'all_legs':items,'issues':issues,'holding_zero_volume_legs':sum(p.get('zero_volume_holding_bars',0)>0 for p in items),
        'matches_sha256':r.sha(ART/'MATCHES.json'),'post_match_filtering':False})
    print({'unique_legs':len(items),'issues':len(issues),'holding_zero_volume_legs':sum(p.get('zero_volume_holding_bars',0)>0 for p in items)},flush=True)


def acquire_funding():
    verify_sources();needs=r.read(ART/'funding/REQUIREMENTS.json');choices=defaultdict(list);records={};pending={}
    for version in [15,12,11,10,9]:
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


def evaluate():
    verify_sources();assert not (ART/'RESULTS.json').exists()
    audit=r.read(ART/'PATH_AUDIT.json');assert audit['matches_sha256']==r.sha(ART/'MATCHES.json')
    checked=r.read(ART/'MATCH_VERIFICATION.json');assert checked['all_passed'] and checked['matches_sha256']==r.sha(ART/'MATCHES.json') and checked['path_audit_sha256']==r.sha(ART/'PATH_AUDIT.json')
    # Reuse the frozen outcome engine exactly. Only paths and immutable-source checks change.
    original=(method.ART,method.load_bars,method.verify_sources)
    try:
        method.ART=ART;method.load_bars=load_bars;method.verify_sources=verify_sources;method.evaluate()
    finally:method.ART,method.load_bars,method.verify_sources=original
    result=r.read(ART/'RESULTS.json');result['version']='4.0.16';result['path_audit_sha256']=r.sha(ART/'PATH_AUDIT.json')
    result['numerical_incremental_diagnostic_support']=result['incremental_diagnostic_support']
    result['incremental_diagnostic_support']=result['incremental_diagnostic_support'] and not audit['issues']
    result['expanded_universe']=True;result['prior_method_protocol_sha256']=r.sha(method.ART/'PROTOCOL.json');r.save(ART/'RESULTS.json',result)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['register','match','quality','funding','evaluate']);a=p.parse_args()
    {'register':register,'match':match,'quality':quality,'funding':acquire_funding,'evaluate':evaluate}[a.action]()
