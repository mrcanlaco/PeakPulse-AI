"""Registered verifier-only timestamp-unit correction, original files unchanged.

Pandas3 date_range defaults to microseconds, while source indices are ns.
Mixed-resolution get_indexer falls back to object indexing on this environment.
Align the expected regular grid's unit; all timestamps and checks are identical.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import shutil
import pandas as pd
import lifecycle_research_v414 as v
import verify_lifecycle_v414 as original
import verify_episode_replay_v414 as episode

r=v.r;OUT=v.ART/'verification_unit_amendment'


def independent_quality(c,frame,events,positive_index=None):
    entry=pd.Timestamp(c['entry_ts'],unit='s',tz='UTC');path=c['paths']['ladder'];exit=pd.Timestamp(path['exit_ts'],unit='s',tz='UTC')
    active=frame.loc[entry:exit-pd.Timedelta(nanoseconds=1)]
    expected=pd.date_range(entry,exit,freq='5min',inclusive='left').as_unit(frame.index.unit)
    missing=int((frame.index.get_indexer(expected)<0).sum())
    zero_exits=[]
    for row in path['trace']:
        if row[2]-row[3]>1e-10:
            opened=pd.Timestamp(row[0]-300,unit='s',tz='UTC')
            if frame.at[opened,'volume']==0:zero_exits.append(int(row[0]))
    if positive_index is None:positive_index=frame.index[frame.volume>0]
    i=positive_index.searchsorted(entry,side='left')-1
    last=positive_index[i] if i>=0 else None;nominal=entry+pd.Timedelta(hours=72 if c['tf']=='4h' else 120)
    flags=[]
    for event in events:
        if event['symbol']!=c['symbol']:continue
        known=pd.Timestamp(event['known_from_utc']);settle=pd.Timestamp(event['settlement_at']);close=pd.Timestamp(event['entry_close_only_from']) if event['entry_close_only_from'] else None
        if known<=entry and (entry>=settle or close is not None and entry>=close):
            flags.append({'kind':'entry_after_announced_new_position_cutoff','settlement_at':int(settle.timestamp()),'close_only_from':int(close.timestamp()) if close is not None else None,'source_url':event['source_url']})
        if known<=settle and entry<settle<=exit:flags.append({'kind':'position_path_crosses_automatic_settlement','settlement_at':int(settle.timestamp()),'source_url':event['source_url']})
    return {'entry_zero_volume':bool(frame.at[entry,'volume']==0),'zero_volume_path_bars':int(active.volume.eq(0).sum()),'zero_volume_exit_groups':zero_exits,
        'missing_bars_through_modelled_exit':missing,'horizon_truncated':path['exit_reason']=='horizon' and exit<nominal,
        'nominal_horizon_end':int(nominal.timestamp()),'modelled_exit':int(exit.timestamp()),
        'last_positive_volume_bar_before_entry':int(last.timestamp()) if last is not None else None,
        'hours_since_last_positive_volume_bar_close':(entry-last-pd.Timedelta(minutes=5)).total_seconds()/3600 if last is not None else None,
        'official_lifecycle_flags':flags}


def register():
    v.verify_sources()
    if (OUT/'PROTOCOL.json').exists():raise FileExistsError('Verifier correction already registered')
    OUT.mkdir(parents=True,exist_ok=True)
    sources=[Path(__file__),Path(original.__file__),Path(episode.__file__),v.ROOT/'tests/unit/fibo_short/test_verifier_units_v414.py']
    for p in sources:shutil.copy2(p,OUT/p.name)
    r.save(OUT/'PROTOCOL.json',{'registered_at_utc':datetime.now(timezone.utc).isoformat(),'sources':{str(p.relative_to(v.ROOT)):r.sha(p) for p in sources},
        'reason':'Profile: ten original candidate checks took14.205s,14.026s in get_indexer; mixed ns/us timestamp units trigger repeated object casts.',
        'change':'Only expected date_range is converted losslessly to the input index unit before get_indexer. All other independent checks preserved.',
        'real_sample_rule':'First and last candidate of each of the first five alphabetically sorted nonempty symbol caches; no outcome-based sample choice.',
        'original_core_source_manifest_sha256':r.sha(v.ART/'SOURCE_MANIFEST.json'),
        'original_verifier_runs':'Stopped before completion; final full checks rerun through this explicitly registered wrapper.',
        'strategy_changes':False,'data_changes':False})


def verify_sources():
    v.verify_sources();p=r.read(OUT/'PROTOCOL.json')
    for relative,h in p['sources'].items():assert r.sha(v.ROOT/relative)==h,relative
    assert p['original_core_source_manifest_sha256']==r.sha(v.ART/'SOURCE_MANIFEST.json')


def equivalence():
    verify_sources();folder=v.ART/'expanded/history';manifest=r.read(folder/'CANDIDATE_MANIFEST.json');events=r.read(v.ART/'OFFICIAL_LIFECYCLE_EVENTS.json')['events'];records=[]
    symbols=sorted(s for s,a in manifest['symbols'].items() if a['candidates'])[:5]
    for s in symbols:
        f=pd.read_parquet(folder/'bars_5m'/f'{s}.parquet');rows=v.load_rows(folder/'candidates'/f'{s}.pkl.gz');positive=f.index[f.volume>0]
        for c in [rows[0],rows[-1]]:
            assert original.independent_quality(c,f,events,positive)==independent_quality(c,f,events,positive)
            records.append(c['id'])
    r.save(OUT/'EQUIVALENCE.json',{'all_passed':True,'real_candidates':records,'count':len(records),'protocol_sha256':r.sha(OUT/'PROTOCOL.json')})
    print(f'Original and normalized verifier exactly equal on{len(records)} prespecified real candidates.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['register','equivalence','core','episodes']);args=parser.parse_args()
    if args.action=='register':register()
    elif args.action=='equivalence':equivalence()
    else:
        verify_sources();check=r.read(OUT/'EQUIVALENCE.json');assert check['all_passed'] and check['protocol_sha256']==r.sha(OUT/'PROTOCOL.json')
        original.independent_quality=independent_quality
        if args.action=='core':original.main()
        else:episode.main()
