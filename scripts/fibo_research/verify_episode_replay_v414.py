"""Independent boundary and provenance checks on scoped episode replay."""
import xml.etree.ElementTree as ET
from pathlib import Path
import pandas as pd
import replay_contract_episodes_v414 as replay
import verify_lifecycle_v414 as quality

e=replay.e;v=e.v;r=e.r;OUT=e.OUT


def main():
    replay.verify_sources();events={a['symbol']:a for a in r.read(OUT/'EVENTS.json')['events']}
    results=r.read(OUT/'RESULTS.json');manifest=r.read(replay.OUT/'CANDIDATE_MANIFEST.json')
    old_dir=v.ART/'expanded/history';old_manifest=r.read(old_dir/'CANDIDATE_MANIFEST.json');members=r.read(OUT/'MEMBERSHIP.json')
    assert manifest['legacy_manifest_sha256']==r.sha(old_dir/'CANDIDATE_MANIFEST.json')
    assert manifest['membership_sha256']==r.sha(OUT/'MEMBERSHIP.json')
    assert manifest['protocol_sha256']==r.sha(replay.OUT/'PROTOCOL.json')
    inputs=r.read(replay.OUT/'INPUTS.json');union=r.read(v.UNION/'DATA_MANIFEST.json')
    episode_frames={};checked_rows=0
    for label,a in inputs.items():
        s=a['symbol'];original=pd.read_parquet(union['inputs'][s]['path']);phase=a['phase']
        expected=original
        if phase=='old':expected=original.loc[original.index<pd.Timestamp(events[s]['settlement_at'])]
        if phase=='relaunched':expected=original.loc[original.index>=pd.Timestamp(events[s]['relaunch_at'])]
        p=replay.OUT/label/'history/bars_5m'/f'{s}.parquet';assert r.sha(p)==a['price_sha256'];frame=pd.read_parquet(p)
        pd.testing.assert_frame_equal(frame,expected,check_exact=True)
        assert frame.index.min()>=v.START and frame.index.max()<v.END
        assert r.sha(replay.OUT/label/'history/bars_5m/BTCUSDT.parquet')==a['btc_sha256']
        assert r.read(replay.OUT/label/'history/MEMBERSHIP.json')==members
        episode_frames[label]=frame;checked_rows+=len(frame)
    total=0;reused=0;recomputed=0;signal_invariant_checks=0;flags=[];primary=0
    for s,a in manifest['symbols'].items():
        p=Path(a['path']);assert r.sha(p)==a['sha256'];rows=v.load_rows(p);assert len(rows)==a['candidates'];total+=len(rows)
        old_path=old_dir/'candidates'/f'{s}.pkl.gz';assert r.sha(old_path)==old_manifest['symbols'][s]['sha256'];old=v.load_rows(old_path);bmap={c['id']:c for c in old}
        if a['origin']=='unchanged_legacy_candidate_objects':
            assert rows==old;reused+=len(rows)
            assert {m for m,rr in members.items() if s in {a['symbol'] for a in rr}}=={m for m,rr in r.read(old_dir/'MEMBERSHIP.json').items() if s in {a['symbol'] for a in rr}}
        else:recomputed+=len(rows)
        for c in rows:
            entry=pd.Timestamp(c['entry_ts'],unit='s',tz='UTC');assert v.START<=entry<v.END
            assert c['entry_ts']==c['decision_ts']+300
            assert s in {a['symbol'] for a in members[entry.strftime('%Y-%m')]}
            is_primary='m6_f4_elite_sniper' in c['milestones'] and entry<r.utc(f'{entry.year+1}-01-01')-pd.Timedelta(days=5)
            primary+=int(is_primary)
            if a['origin']=='unchanged_legacy_candidate_objects':continue
            label=c['contract_episode_id'];frame=episode_frames[label];phase=inputs[label]['phase']
            assert c['entry']==frame.at[entry,'open']
            assert c['stop']>c['entry']>c['targets'][0]>c['targets'][1]>c['targets'][2]>0
            if phase=='old' and c['id'] in bmap:
                # Ending the input at a later settlement must not alter earlier signals.
                for k in bmap[c['id']]:
                    if k not in ('paths','missing_execution_bars'):assert c[k]==bmap[c['id']][k],(c['id'],k)
                signal_invariant_checks+=1
            if phase=='relaunched':assert pd.Timestamp(c['decision_ts'],unit='s',tz='UTC')>=pd.Timestamp(events[s]['relaunch_at'])
            d=quality.independent_quality(c,frame,[])
            if d['horizon_truncated'] or d['entry_zero_volume'] or d['zero_volume_path_bars'] or d['missing_bars_through_modelled_exit']:
                flags.append({'id':c['id'],'symbol':s,'primary_elite_annual_eligible':is_primary,**d})
    comparison=r.read(replay.OUT/'COMPARISON.json')
    assert total==comparison['corrected_candidates'] and reused==comparison['unaffected_candidates_reused_exactly']
    test_suites=list(ET.parse(OUT/'TESTS.xml').getroot().iter('testsuite'))
    tests={k:sum(int(s.get(k,0)) for s in test_suites) for k in ('tests','errors','failures','skipped')}
    assert tests['tests']==8 and tests['errors']==tests['failures']==tests['skipped']==0
    r.save(OUT/'INDEPENDENT_VERIFICATION.json',{'all_scoped_checks_passed':True,'input_rows_checked':checked_rows,'episode_jobs_checked':len(inputs),
        'candidate_objects_checked':total,'primary_elite_candidates':primary,'unaffected_candidates_equal':reused,'recomputed_candidates':recomputed,
        'old_episode_signal_invariance_checks':signal_invariant_checks,'recomputed_candidate_quality_flags':flags,
        'tests':tests,'episode_results_sha256':r.sha(OUT/'RESULTS.json'),'replay_manifest_sha256':r.sha(replay.OUT/'CANDIDATE_MANIFEST.json'),
        'replay_comparison_sha256':r.sha(replay.OUT/'COMPARISON.json'),'post_2025_observations_loaded':0,
        'qualification':'Checks the ten registered transitions and affected membership changes, not all exchange lifecycle events or settlement prices.',
        'economic_results_evaluated':False,'fresh_oos':False,'goal_complete':False})
    print({k:a for k,a in r.read(OUT/'INDEPENDENT_VERIFICATION.json').items() if k!='recomputed_candidate_quality_flags'},flush=True)


if __name__=='__main__':main()
