"""Complete known lifecycle membership corrections and fund the expanded policy.

No new signal/exit/risk thresholds; preserve all pre-2026 historical evidence.
"""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor,ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
import argparse
import gzip
import pickle
import shutil
import numpy as np
import pandas as pd
import contract_episodes_v414 as e
import replay_contract_episodes_v414 as replay
import verify_lifecycle_fast_v414 as independent
import funding_v409 as funding

v=e.v;r=e.r;u=e.u;ROOT=v.ROOT;PRIOR=v.ART;ART=ROOT/'artifacts/fibo_trend_short/research_v4_0_15'


def retain_month(month,event):
    t=r.utc(month+'-01');known=r.utc(event['known_from_utc']);cut=r.utc(event['entry_close_only_from'] or event['settlement_at'])
    return t<known or t<cut


def allowed_entry(c,events):
    t=r.utc(pd.Timestamp(c['entry_ts'],unit='s',tz='UTC'))
    for ev in events:
        if ev['symbol']!=c['symbol'] or t<r.utc(ev['known_from_utc']):continue
        cut=r.utc(ev['entry_close_only_from'] or ev['settlement_at'])
        if t>=cut and (not ev.get('relaunch_at') or t<r.utc(ev['relaunch_at'])):return False
    return True


def freeze():
    replay.verify_sources();independent.verify_sources()
    if (ART/'SOURCE_MANIFEST.json').exists():raise FileExistsError('Already frozen')
    ART.mkdir(parents=True,exist_ok=True)
    old_events=r.read(PRIOR/'OFFICIAL_LIFECYCLE_EVENTS.json')['events']
    events=old_events+[{'symbol':a['symbol'],'known_from_utc':a['known_from_utc'],'entry_close_only_from':a['close_only_from'],
        'settlement_at':a['settlement_at'],'relaunch_at':a['relaunch_at'],'source_url':a['settlement_source']} for a in r.read(e.OUT/'EVENTS.json')['events']]
    r.save(ART/'EVENTS.json',{'events':events,'scope':'15 verified transitions inherited from v414, not a complete historical exchangeInfo catalog.',
        'initial_five':old_events,'parent_initial_events_sha256':r.sha(PRIOR/'OFFICIAL_LIFECYCLE_EVENTS.json'),'parent_ten_events_sha256':r.sha(e.OUT/'EVENTS.json')})
    r.save(ART/'PROTOCOL.json',{'version':'4.0.15','registered_at_utc':datetime.now(timezone.utc).isoformat(),
        'primary_policy':'Frozen elite_sniper gate, original50/30/20 ladder, risk sizing and caps from execution_v409; no parameter sweep.',
        'membership':'Continue v414 episode resets, remove announced closed contracts from monthly eligibility, rerank the full637-symbol pool using unchanged63day/50active-day/3.2percent wick/top50 rules.',
        'data':'Only2020..2025 bounded snapshots; preserve originals and prices, no interpolation, no joining successor assets.',
        'execution':'Recollect affected symbols on isolated episode data. Enforce known close-only entry gate before wave/cooldown consumption. Retain and globally flag incomplete/settlement/zero-fill paths, never delete by future outcomes.',
        'boundary_diagnostic':'Compare every candidate with long-zero spans and observed end-of-activity, including a conservative24h preceding buffer. Diagnostic only; cannot itself establish delisting or act as a filter.',
        'zero_volume':'Flat zero-volume holding bars retain observed last-traded mark. Primary zero-volume entries/exits, missing5m bars or truncated horizons block the new economic run pending explicit resolution; holding-bar flags remain disclosed.',
        'funding':'Use verified historical snapshots when full required range is covered; otherwise download bounded Binance REST history. Exact API settlement marks preferred; explicitly retain old mark-OPEN proxies. Missing coverage or unexplained lifecycle jumps block economic evaluation.',
        'scenarios':v.x.SCENARIOS,'primary_evaluation':'2024..2025 fixed policy, with2020..2023 development/context and full2020..2025 supplementary, all historically reused. Compare old snapshot and corrected expanded universe without choosing a winner.',
        'oos':'No fresh temporal OOS claim from reused2020..2025. Any new out-of-time procedure must disclose prior reuse; final fresh-OOS requirement remains open.',
        'fresh_oos':False,'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    sources=[Path(__file__),ROOT/'tests/unit/fibo_short/test_research_v415.py',Path(funding.__file__),Path(v.x.__file__),Path(e.__file__),Path(replay.__file__),Path(independent.__file__)]
    for p in sources:
        target=ART/'source_snapshot'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    r.save(ART/'SOURCE_MANIFEST.json',{'sources':{str(p.relative_to(ROOT)):r.sha(p) for p in sources},'protocol_sha256':r.sha(ART/'PROTOCOL.json'),
        'events_sha256':r.sha(ART/'EVENTS.json'),'parent_checkpoint_sha256':r.sha(PRIOR/'CHECKPOINT.json'),
        'union_manifest_sha256':r.sha(v.UNION/'DATA_MANIFEST.json'),'parent_candidate_manifest_sha256':r.sha(replay.OUT/'CANDIDATE_MANIFEST.json')})


def verify_sources():
    replay.verify_sources();independent.verify_sources();m=r.read(ART/'SOURCE_MANIFEST.json')
    for p,h in m['sources'].items():assert r.sha(ROOT/p)==h,p
    for k,p in [('protocol_sha256',ART/'PROTOCOL.json'),('events_sha256',ART/'EVENTS.json'),('parent_checkpoint_sha256',PRIOR/'CHECKPOINT.json'),
        ('union_manifest_sha256',v.UNION/'DATA_MANIFEST.json'),('parent_candidate_manifest_sha256',replay.OUT/'CANDIDATE_MANIFEST.json')]:assert r.sha(p)==m[k],p


def prepare():
    verify_sources()
    if (ART/'DATA_MANIFEST.json').exists():raise FileExistsError('Data already prepared')
    union=r.read(v.UNION/'DATA_MANIFEST.json');initial=r.read(v.PRIOR/'history/DATA_MANIFEST.json');monthly={};views={s:[{'phase':'unchanged',**a}] for s,a in union['inputs'].items()}
    for s,h in initial['symbol_audit_sha256'].items():
        p=v.PRIOR/'symbol_audits'/f'{s}.json';assert r.sha(p)==h;monthly[s]=r.read(p)['monthly_rows']
    for a in r.read(e.OUT/'RESULTS.json')['symbols']:
        monthly[a['symbol']]=a['corrected_monthly_rows'];views[a['symbol']]=a['episode_views']
    assert u.rank(monthly.values())==r.read(e.OUT/'MEMBERSHIP.json')
    diagnostics=[];events=r.read(ART/'EVENTS.json')['initial_five']
    for ev in events:
        s=ev['symbol'];item=union['inputs'][s];p=Path(item['path']);assert r.sha(p)==item['sha256'];frame=pd.read_parquet(p);settle=r.utc(ev['settlement_at'])
        # An observed later relaunch needs an explicit new identity, never a blanket deletion.
        if (frame.loc[frame.index>settle,'volume']>0).any():raise ValueError(f'Unregistered later active episode: {s}')
        trimmed=frame.loc[frame.index<settle];raw=r.monthly_rows(s,r.h1_frame(trimmed),u.MONTHS)
        direct=e.independent.independent_monthly(s,trimmed.reset_index());e.independent.check_row(raw,direct)
        monthly[s]={m:a for m,a in raw.items() if retain_month(m,ev)}
        target=ART/'episode_bars'/f'{s}__old.parquet';target.parent.mkdir(exist_ok=True);trimmed.to_parquet(target)
        pd.testing.assert_frame_equal(pd.read_parquet(target),trimmed,check_exact=True)
        views[s]=[{'phase':'old','path':str(target),'sha256':r.sha(target),'rows':len(trimmed)}]
        diagnostics.append({'symbol':s,'settlement_at':ev['settlement_at'],'excluded_inactive_rows':len(frame)-len(trimmed),'active_rows_after_settlement':int(frame.loc[frame.index>=settle,'volume'].gt(0).sum())})
    members=u.rank(monthly.values());old=r.read(e.OUT/'MEMBERSHIP.json');delta={};changed=set(ev['symbol'] for ev in events)
    for m,rr in members.items():
        before={a['symbol'] for a in old[m]};after={a['symbol'] for a in rr};added=sorted(after-before);removed=sorted(before-after)
        delta[m]={'added':added,'removed':removed};changed.update(added);changed.update(removed)
    r.save(ART/'MEMBERSHIP.json',members)
    selected={a['symbol'] for rows in members.values() for a in rows};previous_members=set(r.read(replay.OUT/'CANDIDATE_MANIFEST.json')['symbols'])
    affected=sorted(changed&(selected|previous_members));stale=[]
    for s in sorted(selected):
        p=Path(union['inputs'][s]['path']);assert r.sha(p)==union['inputs'][s]['sha256'];frame=pd.read_parquet(p);positive=frame.index[frame.volume>0]
        for m,rr in members.items():
            if s not in {a['symbol'] for a in rr}:continue
            t=r.utc(m+'-01');i=positive.searchsorted(t-pd.Timedelta(minutes=5),side='right')-1;last=positive[i] if i>=0 else None
            age=(t-last-pd.Timedelta(minutes=5)).total_seconds()/3600 if last is not None else None
            if age is None or age>=24:stale.append({'symbol':s,'month':m,'hours_since_last_positive_close':age,'last_open':last.isoformat() if last is not None else None})
    r.save(ART/'DATA_MANIFEST.json',{'views':views,'affected_symbols':affected,'selected_symbols':sorted(selected),'membership_sha256':r.sha(ART/'MEMBERSHIP.json'),
        'union_manifest_sha256':r.sha(v.UNION/'DATA_MANIFEST.json'),'protocol_sha256':r.sha(ART/'PROTOCOL.json')})
    r.save(ART/'MEMBERSHIP_CORRECTION.json',{'delta':delta,'changed_months':sum(bool(a['added'] or a['removed']) for a in delta.values()),
        'affected_symbols':affected,'member_slots':sum(map(len,members.values())),'unique_members':len(selected),'remaining_stale_member_months':stale,
        'lifecycle_rows':diagnostics,'baseline_v414_membership_exact':True,'independent_monthly_checks_passed':True})
    print(r.read(ART/'MEMBERSHIP_CORRECTION.json'),flush=True)


def worker(label,s):
    r.ART=ART/'replay'/label;r.WINDOWS['history']=('2020-01-01','2026-01-01')
    return label,r.collect_one('history',s)


def collect(workers):
    verify_sources();data=r.read(ART/'DATA_MANIFEST.json');members=r.read(ART/'MEMBERSHIP.json');events=r.read(ART/'EVENTS.json')['events'];old=r.read(replay.OUT/'CANDIDATE_MANIFEST.json')
    assert data['membership_sha256']==r.sha(ART/'MEMBERSHIP.json');jobs=[];btc=PRIOR/'expanded/history/bars_5m/BTCUSDT.parquet'
    assert r.sha(btc)==r.read(PRIOR/'expanded/history/DATA_MANIFEST.json')['inputs']['BTCUSDT']['sha256']
    for s in data['affected_symbols']:
        for a in data['views'][s]:
            label=f'{s}__{a["phase"]}';folder=ART/'replay'/label/'history';folder.mkdir(parents=True,exist_ok=True)
            (folder/'bars_5m').mkdir(exist_ok=True);(folder/'candidates').mkdir(exist_ok=True)
            source=Path(a['path']);assert r.sha(source)==a['sha256'];dest=folder/'bars_5m'/f'{s}.parquet'
            if not dest.exists():shutil.copy2(source,dest)
            assert r.sha(dest)==a['sha256']
            b=folder/'bars_5m/BTCUSDT.parquet'
            if not b.exists():shutil.copy2(btc,b)
            assert r.sha(b)==r.sha(btc);r.save(folder/'MEMBERSHIP.json',members);jobs.append((label,s))
    p=ART/'COLLECTION_PROGRESS.json';progress=r.read(p) if p.exists() else {}
    for label,a in progress.items():assert r.sha(ART/'replay'/label/'history/candidates'/f'{a["symbol"]}.pkl.gz')==a['sha256']
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(worker,label,s) for label,s in jobs if label not in progress]
        for future in as_completed(futures):
            label,(s,n,reject,h)=future.result();progress[label]={'symbol':s,'candidates':n,'rejections':reject,'sha256':h};r.save(p,progress)
            print(f'Lifecycle membership replay {len(progress)}/{len(jobs)} {label}: {n}',flush=True)
    manifest={};rejected=[];delta=[];(ART/'candidates').mkdir(exist_ok=True)
    for s in sorted(set(old['symbols'])|set(data['selected_symbols'])):
        item=old['symbols'].get(s);before=[]
        if item:
            assert r.sha(item['path'])==item['sha256'];before=v.load_rows(item['path'])
        if s not in data['affected_symbols']:
            assert item;manifest[s]={**item,'mode':'reuse_v414_verified'};continue
        after=[]
        for label,ss in jobs:
            if ss!=s:continue
            rows=v.load_rows(ART/'replay'/label/'history/candidates'/f'{s}.pkl.gz')
            for c in rows:
                if not allowed_entry(c,events):rejected.append({'id':c['id'],'reason':'known_contract_close_only'});continue
                after.append({**c,'contract_episode_id':label})
        after.sort(key=lambda c:(c['entry_ts'],c['tf']));assert len({c['id'] for c in after})==len(after)
        a={c['id']:c for c in before};b={c['id']:c for c in after};common=set(a)&set(b)
        changed=[cid for cid in common if {k:val for k,val in a[cid].items() if k!='contract_episode_id'}!={k:val for k,val in b[cid].items() if k!='contract_episode_id'}]
        delta.append({'symbol':s,'before':len(before),'after':len(after),'added':sorted(set(b)-set(a)),'removed':sorted(set(a)-set(b)),'changed':sorted(changed)})
        target=ART/'candidates'/f'{s}.pkl.gz'
        with gzip.open(target,'wb') as fh:pickle.dump(after,fh,protocol=5)
        assert v.load_rows(target)==after
        manifest[s]={'path':str(target),'sha256':r.sha(target),'candidates':len(after),'mode':'fresh_replay'}
    r.save(ART/'CANDIDATE_MANIFEST.json',{'symbols':manifest,'membership_sha256':r.sha(ART/'MEMBERSHIP.json'),'protocol_sha256':r.sha(ART/'PROTOCOL.json')})
    r.save(ART/'CANDIDATE_COMPARISON.json',{'symbols':delta,'known_close_only_rejections':rejected,'before':sum(a['candidates'] for a in old['symbols'].values()),
        'after':sum(a['candidates'] for a in manifest.values()),'new_candidates':sum(len(a['added']) for a in delta),'removed_candidates':sum(len(a['removed']) for a in delta),
        'changed_candidates':sum(len(a['changed']) for a in delta),'economic_results_evaluated':False})
    print({k:a for k,a in r.read(ART/'CANDIDATE_COMPARISON.json').items() if k!='symbols'},flush=True)


def audit():
    verify_sources();manifest=r.read(ART/'CANDIDATE_MANIFEST.json');members=r.read(ART/'MEMBERSHIP.json');events=r.read(ART/'EVENTS.json')['events']
    union=r.read(v.UNION/'DATA_MANIFEST.json');quality=r.read(v.UNION/'QUALITY.json');issues=[];flags=[];boundary=[];selected=[];needs={};years=Counter();checked=0
    for s,a in sorted(manifest['symbols'].items()):
        assert r.sha(a['path'])==a['sha256'];rows=v.load_rows(a['path'])
        if not rows:continue
        p=Path(union['inputs'][s]['path']);assert r.sha(p)==union['inputs'][s]['sha256'];frame=pd.read_parquet(p);positive=frame.index[frame.volume>0]
        spans=[('observed_long_zero',r.utc(z['start'])-pd.Timedelta(days=1),r.utc(z['end'])+pd.Timedelta(minutes=5)) for z in quality[s]['zero_volume_runs'] if z['bars']>=288]
        last=r.utc(quality[s]['last_positive_volume'])
        if last+pd.Timedelta(days=1)<v.END:spans.append(('observed_activity_end',last-pd.Timedelta(days=1),v.END))
        for c in rows:
            checked+=1;entry=pd.Timestamp(c['entry_ts'],unit='s',tz='UTC');exit=pd.Timestamp(c['paths']['ladder']['exit_ts'],unit='s',tz='UTC')
            assert v.START<=entry<exit<=v.END and c['entry_ts']==c['decision_ts']+300
            assert c['entry']==frame.at[entry,'open'] and allowed_entry(c,events)
            assert s in {a['symbol'] for a in members[entry.strftime('%Y-%m')]}
            # Inspect only the event relevant to this episode, never an old delisting after relaunch.
            applicable=[ev for ev in events if ev['symbol']==s and (not ev.get('relaunch_at') or entry<r.utc(ev['relaunch_at']))]
            d=independent.independent_quality(c,frame,applicable,positive);primary=r.passes(c,'elite_sniper') and v.annual_eligible(c)
            if any(d[k] for k in ['entry_zero_volume','zero_volume_path_bars','zero_volume_exit_groups','missing_bars_through_modelled_exit','horizon_truncated','official_lifecycle_flags']):flags.append({'id':c['id'],'symbol':s,'primary':primary,**d})
            for kind,lo,hi in spans:
                if entry<hi and exit>=lo:boundary.append({'id':c['id'],'symbol':s,'primary':primary,'kind':kind,'entry':entry.isoformat(),'exit':exit.isoformat(),'diagnostic_boundary':lo.isoformat()})
            if not primary:continue
            selected.append(c);years[str(entry.year)]+=1
            if any(d[k] for k in ['entry_zero_volume','zero_volume_exit_groups','missing_bars_through_modelled_exit','horizon_truncated','official_lifecycle_flags']):issues.append({'id':c['id'],'symbol':s,**d})
            n=needs.setdefault(s,{'first_entry_ms':c['entry_ts']*1000,'last_exit_ms':c['paths']['ladder']['exit_ts']*1000,'candidates':0})
            n['first_entry_ms']=min(n['first_entry_ms'],c['entry_ts']*1000);n['last_exit_ms']=max(n['last_exit_ms'],c['paths']['ladder']['exit_ts']*1000);n['candidates']+=1
    for n in needs.values():n['start_ms']=max(funding.START_MS,n['first_entry_ms']-16*3600000);n['end_ms']=min(funding.LIMIT_MS-1,n['last_exit_ms']+16*3600000)
    for s in needs:
        relevant=[c for c in selected if c['symbol']==s]
        for ev in events:
            if ev['symbol']==s and ev.get('relaunch_at'):
                phases={c['entry_ts']>=int(r.utc(ev['relaunch_at']).timestamp()) for c in relevant}
                assert len(phases)<=1,f'Multiple funding episodes require distinct acquisition: {s}'
    r.save(ART/'CANDIDATE_AUDIT.json',{'all_candidates_checked':checked,'primary_candidates':len(selected),'primary_by_year':dict(years),'primary_symbols':len(needs),
        'primary_execution_issues':issues,'quality_flags':flags,'observed_lifecycle_boundary_overlaps':boundary,
        'primary_boundary_overlaps':sum(a['primary'] for a in boundary),'post_2025_observations_loaded':0,'fresh_oos':False,'goal_complete':False,
        'candidate_manifest_sha256':r.sha(ART/'CANDIDATE_MANIFEST.json')})
    r.save(ART/'funding/REQUIREMENTS.json',needs)
    with gzip.open(ART/'PRIMARY_CANDIDATES.pkl.gz','wb') as fh:pickle.dump(selected,fh,protocol=5)
    print({'all':checked,'primary':len(selected),'funding_symbols':len(needs),'execution_issues':len(issues),'boundary_overlaps':len(boundary),'primary_boundary_overlaps':sum(a['primary'] for a in boundary)},flush=True)


def acquire_funding(workers):
    verify_sources();needs=r.read(ART/'funding/REQUIREMENTS.json');choices={};records={};pending={}
    for version in [12,11,10,9]:
        root=ROOT/f'artifacts/fibo_trend_short/research_v4_0_{version}';manifest=r.read(root/'funding/MANIFEST.json')
        for s,a in manifest['symbols'].items():
            path=Path(a['path']) if 'path' in a else root/'funding/snapshots'/f'{s}.parquet';record=a.get('record',a)
            choices.setdefault(s,[]).append((root,path,record))
    for s,n in needs.items():
        for root,p,a in choices.get(s,[]):
            if not a['gaps_over_8h'] and not a['local_differences_ms'] and a['first_event_ms']<=n['first_entry_ms']<=n['last_exit_ms']<=a['last_event_ms']:
                assert r.sha(p)==a['sha256'];records[s]={'mode':'reuse_verified','source_root':str(root),'path':str(p),'sha256':a['sha256'],'record':a,'requirements':n};break
        if s not in records:pending[s]=n
    r.save(ART/'funding/ACQUISITION_PLAN.json',{'total_symbols':len(needs),'reused_symbols':sorted(records),'download_symbols':sorted(pending),'requirements_sha256':r.sha(ART/'funding/REQUIREMENTS.json')})
    print(f'Funding plan: {len(records)} reused, {len(pending)} fresh bounded queries.',flush=True)
    funding.ART=ART;errors={}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(funding.fetch_symbol,s,n):s for s,n in pending.items()}
        for future in as_completed(futures):
            s=futures[future]
            try:
                _,a=future.result()
                assert not a['gaps_over_8h'] and not a['left_edge_uncovered'] and not a['right_edge_uncovered'] and not a['local_differences_ms'],'Incomplete funding or local mismatch'
                records[s]={'mode':'new_official_download','source_root':str(ART),'path':str(ART/'funding/snapshots'/f'{s}.parquet'),'sha256':a['sha256'],'record':a,'requirements':needs[s]}
                print(f'Funding {len(records)}/{len(needs)} {s}',flush=True)
            except Exception as exc:errors[s]=str(exc);print(f'Funding unresolved {s}: {exc}',flush=True)
            r.save(ART/'funding/PROGRESS.json',{'completed':len(records),'total':len(needs),'errors':errors})
    r.save(ART/'funding/MANIFEST.json',{'symbols':records,'errors':errors,'all_passed':not errors and len(records)==len(needs),
        'requirements_sha256':r.sha(ART/'funding/REQUIREMENTS.json'),'price_proxy_disclosure':'Old API missing marks retain the explicitly labelled official mark1h OPEN proxy; not exact settlement ticks.'})
    if errors:raise RuntimeError(f'Funding unresolved: {errors}')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','prepare','collect','audit','funding']);parser.add_argument('--workers',type=int,default=4);a=parser.parse_args()
    if a.action in ('collect','funding'):{'collect':collect,'funding':acquire_funding}[a.action](a.workers)
    else:{'freeze':freeze,'prepare':prepare,'audit':audit}[a.action]()
