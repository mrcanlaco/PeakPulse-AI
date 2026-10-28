"""Recollect affected signals using frozen detector on isolated episode files."""
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import argparse
import gzip
import pickle
import shutil
import pandas as pd
import contract_episodes_v414 as e

v=e.v;r=e.r;OUT=e.OUT/'replay'


def register():
    e.verify_sources();results=r.read(e.OUT/'RESULTS.json');assert results['independent_monthly_calculations_passed']
    if (OUT/'PROTOCOL.json').exists():raise FileExistsError('Replay already registered')
    OUT.mkdir(parents=True,exist_ok=True)
    r.save(OUT/'PROTOCOL.json',{'registered_at_utc':datetime.now(timezone.utc).isoformat(),'source_sha256':r.sha(__file__),
        'episode_results_sha256':r.sha(e.OUT/'RESULTS.json'),'membership_sha256':r.sha(e.OUT/'MEMBERSHIP.json'),
        'collector_source_sha256':r.sha(v.ROOT/'scripts/fibo_research/research_v407.py'),
        'rules':['Recompute every affected member with exactly the frozen detector and original BTC context.',
            'Run each contract episode in a separate data directory; feature and swing state start from that episode only.',
            'Recompute any other symbol whose monthly eligibility changed; reuse all unaffected candidate objects exactly.',
            'Retain lifecycle-affected paths for diagnosis. Truncated old-episode horizons are not approved settlement fills.',
            'No economic performance, threshold selection or fresh-OOS claim in this replay.'],
        'economic_results_evaluated':False,'goal_complete':False})
    shutil.copy2(__file__,OUT/Path(__file__).name)


def verify_sources():
    e.verify_sources();p=r.read(OUT/'PROTOCOL.json')
    assert p['source_sha256']==r.sha(__file__)
    assert p['episode_results_sha256']==r.sha(e.OUT/'RESULTS.json')
    assert p['membership_sha256']==r.sha(e.OUT/'MEMBERSHIP.json')
    assert p['collector_source_sha256']==r.sha(v.ROOT/'scripts/fibo_research/research_v407.py')


def job(label,symbol):
    r.ART=OUT/label;r.WINDOWS['history']=('2020-01-01','2026-01-01')
    return label,r.collect_one('history',symbol)


def run(workers):
    verify_sources();original=v.ART/'expanded/history';manifest=r.read(original/'CANDIDATE_MANIFEST.json')
    result=r.read(e.OUT/'RESULTS.json');members=r.read(e.OUT/'MEMBERSHIP.json');old_members=r.read(original/'MEMBERSHIP.json')
    affected={a['symbol'] for a in result['symbols']}&set(manifest['symbols'])
    for month in members:
        affected|={a['symbol'] for a in members[month]}^{a['symbol'] for a in old_members[month]}
    by_symbol={a['symbol']:a for a in result['symbols']};union=r.read(v.UNION/'DATA_MANIFEST.json')
    btc=original/'bars_5m/BTCUSDT.parquet';assert r.sha(btc)==r.read(original/'DATA_MANIFEST.json')['inputs']['BTCUSDT']['sha256']
    jobs=[];inputs={}
    for s in sorted(affected):
        views=by_symbol[s]['episode_views'] if s in by_symbol else [{'phase':'unchanged','path':union['inputs'][s]['path'],'sha256':union['inputs'][s]['sha256']}]
        for a in views:
            label=f'{s}__{a["phase"]}';folder=OUT/label/'history';folder.mkdir(parents=True,exist_ok=True)
            (folder/'bars_5m').mkdir(exist_ok=True);(folder/'candidates').mkdir(exist_ok=True)
            p=Path(a['path']);assert r.sha(p)==a['sha256']
            target=folder/'bars_5m'/f'{s}.parquet'
            if not target.exists():shutil.copy2(p,target)
            assert r.sha(target)==a['sha256']
            target_btc=folder/'bars_5m/BTCUSDT.parquet'
            if not target_btc.exists():shutil.copy2(btc,target_btc)
            assert r.sha(target_btc)==r.sha(btc)
            r.save(folder/'MEMBERSHIP.json',members);inputs[label]={'symbol':s,'phase':a['phase'],'price_sha256':a['sha256'],'btc_sha256':r.sha(btc)};jobs.append((label,s))
    r.save(OUT/'INPUTS.json',inputs)
    p=OUT/'COLLECTION_PROGRESS.json';progress=r.read(p) if p.exists() else {}
    for label,a in progress.items():assert r.sha(OUT/label/'history/candidates'/f'{a["symbol"]}.pkl.gz')==a['sha256']
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending=[pool.submit(job,label,s) for label,s in jobs if label not in progress]
        for future in as_completed(pending):
            label,(s,count,rejected,digest)=future.result();progress[label]={'symbol':s,'candidates':count,'rejections':rejected,'sha256':digest}
            r.save(p,progress);print(f'Episode replay {len(progress)}/{len(jobs)} {label}: {count}',flush=True)
    candidates={};comparisons=[];unchanged=0
    (OUT/'candidates').mkdir(exist_ok=True)
    for s,a in sorted(manifest['symbols'].items()):
        source=original/'candidates'/f'{s}.pkl.gz';assert r.sha(source)==a['sha256'];before=v.load_rows(source)
        if s not in affected:
            candidates[s]={'path':str(source),'sha256':a['sha256'],'candidates':len(before),'origin':'unchanged_legacy_candidate_objects'};unchanged+=len(before);continue
        after=[]
        for label,ss in jobs:
            if ss!=s:continue
            rows=v.load_rows(OUT/label/'history/candidates'/f'{s}.pkl.gz')
            for c in rows:c['contract_episode_id']=label
            after.extend(rows)
        after.sort(key=lambda c:(c['entry_ts'],c['tf']));assert len({c['id'] for c in after})==len(after)
        bmap={c['id']:c for c in before};amap={c['id']:c for c in after};shared=set(bmap)&set(amap)
        changed_fields={};changed_paths=[];equal=0
        for cid in shared:
            fields=[k for k in bmap[cid] if k not in ('paths','missing_execution_bars') and bmap[cid][k]!=amap[cid][k]]
            if fields:changed_fields[cid]=fields
            if bmap[cid]['paths']!=amap[cid]['paths']:changed_paths.append(cid)
            if {k:a for k,a in amap[cid].items() if k!='contract_episode_id'}==bmap[cid]:equal+=1
        target=OUT/'candidates'/f'{s}.pkl.gz'
        with gzip.open(target,'wb') as fh:pickle.dump(after,fh,protocol=5)
        assert v.load_rows(target)==after
        candidates[s]={'path':str(target),'sha256':r.sha(target),'candidates':len(after),'origin':'fresh_episode_replay'}
        comparisons.append({'symbol':s,'before':len(before),'after':len(after),'identical_except_identity':equal,
            'removed_ids':sorted(set(bmap)-set(amap)),'added_ids':sorted(set(amap)-set(bmap)),
            'changed_signal_fields':changed_fields,'changed_paths':sorted(changed_paths)})
    # An added member symbol with no legacy candidate file must be handled explicitly.
    assert affected<=set(manifest['symbols']),'New member requires merge-path extension; do not silently omit'
    r.save(OUT/'CANDIDATE_MANIFEST.json',{'symbols':candidates,'membership_sha256':r.sha(e.OUT/'MEMBERSHIP.json'),
        'protocol_sha256':r.sha(OUT/'PROTOCOL.json'),'legacy_manifest_sha256':r.sha(original/'CANDIDATE_MANIFEST.json')})
    r.save(OUT/'COMPARISON.json',{'symbols':comparisons,'affected_symbols':len(affected),'recomputed_episode_jobs':len(jobs),
        'legacy_candidates':sum(a['candidates'] for a in manifest['symbols'].values()),'corrected_candidates':sum(a['candidates'] for a in candidates.values()),
        'unaffected_candidates_reused_exactly':unchanged,'removed':sum(len(a['removed_ids']) for a in comparisons),
        'added':sum(len(a['added_ids']) for a in comparisons),'changed_signal_objects':sum(len(a['changed_signal_fields']) for a in comparisons),
        'changed_path_objects':sum(len(a['changed_paths']) for a in comparisons),'economic_results_evaluated':False,
        'limitations':'Corrects the ten registered lifecycle transitions only. Other delistings, automatic settlement prices and tradability remain unresolved.',
        'post_2025_observations_loaded':0,'fresh_oos':False,'goal_complete':False})
    print({k:a for k,a in r.read(OUT/'COMPARISON.json').items() if k!='symbols'},flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['register','run']);parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    if args.action=='register':register()
    else:run(args.workers)
