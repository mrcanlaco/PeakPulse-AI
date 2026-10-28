"""Independent event-driven paths and funding provenance for the fixed family."""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import gzip
import pickle
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import research_family_v421 as v

r = v.r
ART = v.ART


def paths():
    v.verify_sources()
    manifest = r.read(ART / 'PATH_MANIFEST.json')
    original = r.read(v.previous.b.ART / 'CANDIDATE_MANIFEST.json')
    events = r.read(v.previous.b.ART / 'EVENTS.json')['events']
    counts = Counter()
    flagged = []
    for symbol, a in sorted(manifest['symbols'].items()):
        assert r.sha(ART / a['paths']) == a['paths_sha256'] and r.sha(ART / a['audit']) == a['audit_sha256']
        with gzip.open(ART / a['paths'], 'rb') as fh:
            pack = pickle.load(fh)
        assert r.sha(original['symbols'][symbol]['path']) == a['source_sha256']
        with gzip.open(original['symbols'][symbol]['path'], 'rb') as fh:
            before = pickle.load(fh)
        assert pack['full'] == before
        expected_ids = {c['id'] for c in before if r.passes(c, 'sniper')}
        assert {c['id'] for c in pack['h24']} == expected_ids
        if not before:
            continue
        frame = v.data.load_bars(symbol)
        stamps = r.epoch_seconds(frame.index)
        volume = frame.volume.to_numpy()
        saved = {(a['id'], a['mode']): a for a in r.read(ART / a['audit'])}
        for mode, candidates in pack.items():
            for c in candidates:
                start = c['entry_ts']
                horizon = 24 if mode == 'h24' else 72 if c['tf'] == '4h' else 120
                deadline = start + horizon * 3600
                lo, hi = np.searchsorted(stamps, [start, deadline])
                fresh = v.independent.independent_exits(frame.iloc[lo:hi], {**c, 'horizon_end': deadline})
                old = c['paths']['ladder']
                assert fresh is not None
                assert np.allclose(np.asarray(fresh['trace']), np.asarray(old['trace']), atol=1e-8, rtol=0), (c['id'], mode)
                assert abs(fresh['gross_return'] - old['gross_return']) < 1e-8 and fresh['exit_ts'] == old['exit_ts']
                assert fresh['exit_reason'] == ('horizon' if old['exit_reason'] == 'horizon24' else old['exit_reason'])
                end = fresh['exit_ts']
                j = np.searchsorted(stamps, end)
                used = stamps[lo:j]
                zero = [p['timestamp_ms'] // 1000 for p in fresh['groups']
                        if volume[np.searchsorted(stamps, p['timestamp_ms'] // 1000 - 300)] <= 0]
                expected = {'entry_zero_volume': bool(volume[lo] <= 0),
                            'zero_volume_holding_bars': int(np.count_nonzero(volume[lo:j] <= 0)),
                            'zero_volume_exit_groups': zero, 'missing_exit_bars': [],
                            'missing_bars': int((end - start) // 300 - len(used)),
                            'grid_is_contiguous': bool(len(used) == (end - start) // 300 and used[0] == start and np.all(np.diff(used) == 300)),
                            'horizon_truncated': fresh['exit_reason'] == 'horizon' and end < deadline,
                            'settlement_overlaps': [e['settlement_at'] for e in events if e['symbol'] == symbol
                                                   and start < r.utc(e['settlement_at']).timestamp() <= end],
                            'entry_allowed_by_known_lifecycle': True}
                for e in events:
                    if e['symbol'] != symbol or e.get('relaunch_at') and start >= r.utc(e['relaunch_at']).timestamp():
                        continue
                    if r.utc(e['known_from_utc']).timestamp() <= start:
                        cutoff = r.utc(e['entry_close_only_from'] or e['settlement_at']).timestamp()
                        if start >= cutoff:
                            expected['entry_allowed_by_known_lifecycle'] = False
                record = saved[(c['id'], mode)]
                assert expected == record['quality'], (c['id'], mode, expected, record)
                failure = bool(expected['entry_zero_volume'] or zero or expected['missing_bars'] or not expected['grid_is_contiguous']
                               or expected['horizon_truncated'] or expected['settlement_overlaps'] or not expected['entry_allowed_by_known_lifecycle'])
                assert failure == record['has_execution_issue']
                if failure:
                    flagged.append(record)
                counts[mode] += 1
        print(f'Independent paths {symbol}: full={counts["full"]}, h24={counts["h24"]}', flush=True)
    assert counts['full'] == manifest['all_full'] and counts['h24'] == manifest['all_h24']
    key = lambda a: (a['id'], a['mode'])
    assert sorted(flagged, key=key) == sorted(manifest['quality_issues'], key=key)
    r.save(ART / 'PATH_VERIFICATION.json', {'all_passed': True, 'full_paths_independently_recomputed': counts['full'],
        'h24_paths_independently_recomputed': counts['h24'], 'unresolved_execution_issues': len(flagged),
        'quality_issues_are_retained_not_filtered': True, 'path_manifest_sha256': r.sha(ART / 'PATH_MANIFEST.json')})
    print({'all_path_checks_passed': True, **dict(counts), 'quality_issues': len(flagged)}, flush=True)


def funding():
    v.verify_sources()
    manifest = r.read(ART / 'funding/MANIFEST.json')
    assert manifest['all_passed'] and not manifest['errors']
    counts = Counter()
    sources = Counter()
    raw_paths = set()
    snapshots = set()
    checked = {}
    for key, item in sorted(manifest['segments'].items()):
        # Reuse the independent raw-response verifier on one segment at a time.
        # Its output path is isolated; every prior snapshot remains immutable.
        scratch = ART / 'funding_verification' / key
        r.save(scratch / 'funding/REQUIREMENTS.json', {item['symbol']: item['requirements']})
        r.save(scratch / 'funding/MANIFEST.json', {'symbols': {item['symbol']: item}, 'all_passed': True, 'errors': {},
            'requirements_sha256': r.sha(scratch / 'funding/REQUIREMENTS.json')})
        v.provenance.v = v
        v.provenance.ART = scratch
        frames, record = v.provenance.funding()
        checked[key] = record
        for k in ('funding_snapshot_events_verified', 'raw_responses_verified', 'archives_verified'):
            counts[k] += record[k]
        sources.update(record['funding_price_sources'])
        root = Path(item['path']).parents[2]
        raw_paths.update(str(root / p) for p in item['record']['raw_responses'])
        snapshots.add(item['path'])
        v.coverage(v.merge_funding([frames[item['symbol']]]), item['requirements']['first_entry_ms'], item['requirements']['last_exit_ms'])
    merged = v.load_funding()
    overlaps = {}
    for version in (9, 15):
        prior_root = v.BASE / f'research_v4_0_{version}'
        old_manifest = r.read(prior_root / 'funding/MANIFEST.json')
        overlap = 0
        for symbol, old_item in old_manifest['symbols'].items():
            if symbol not in merged:
                continue
            old_path = Path(old_item['path']) if 'path' in old_item else prior_root / 'funding/snapshots' / f'{symbol}.parquet'
            assert r.sha(old_path) == old_item['sha256']
            old_frame = pd.read_parquet(old_path).set_index('funding_ts_ms')
            new_frame = pd.DataFrame(merged[symbol]['events']).set_index('funding_ts_ms')
            common = old_frame.index.intersection(new_frame.index).sort_values()
            pd.testing.assert_frame_equal(old_frame.loc[common], new_frame.loc[common], check_exact=True, check_dtype=False)
            overlap += len(common)
        overlaps[str(version)] = overlap
    rows = [c for c in v.load_paths()['full'] if v.previous.annual_eligible(c)]
    for c in rows:
        stamps = merged[c['symbol']]['times']
        lo = np.searchsorted(stamps, c['entry_ts'] * 1000, side='right') - 1
        hi = np.searchsorted(stamps, c['paths']['ladder']['exit_ts'] * 1000, side='left')
        assert lo >= 0 and hi < len(stamps) and np.diff(stamps[lo:hi + 1]).max(initial=0) <= 28815000
    result = {'all_passed': True, 'segments': len(checked), 'symbols': len(merged),
        'candidate_holding_intervals_covered': len(rows), **dict(counts), 'funding_price_sources': dict(sources),
        'unique_raw_response_paths': len(raw_paths), 'unique_snapshot_paths': len(snapshots),
        'unique_merged_events': sum(len(a['events']) for a in merged.values()),
        'exact_overlap_events_by_prior_version': overlaps,
        'funding_manifest_sha256': r.sha(ART / 'funding/MANIFEST.json')}
    r.save(ART / 'FUNDING_VERIFICATION.json', result)
    print(result, flush=True)


def finish():
    v.verify_sources()
    paths = r.read(ART / 'PATH_VERIFICATION.json')
    fund = r.read(ART / 'FUNDING_VERIFICATION.json')
    assert paths['all_passed'] and fund['all_passed']
    assert paths['path_manifest_sha256'] == r.sha(ART / 'PATH_MANIFEST.json')
    assert fund['funding_manifest_sha256'] == r.sha(ART / 'funding/MANIFEST.json')
    suites = list(ET.parse(ART / 'TESTS.xml').getroot().iter('testsuite'))
    tests = {k: sum(int(a.get(k, 0)) for a in suites) for k in ('tests', 'errors', 'failures', 'skipped')}
    assert tests['tests'] >= 5 and tests['errors'] == tests['failures'] == tests['skipped'] == 0
    checkpoint = r.read(v.PRIOR / 'CHECKPOINT.json')
    for p, h in checkpoint['files'].items():
        assert r.sha(v.PRIOR / p) == h
    for p, h in checkpoint['additional_sources'].items():
        assert r.sha(v.ROOT / p) == h
    r.save(ART / 'INPUT_VERIFICATION.json', {'all_passed': True, 'paths': paths, 'funding': fund, 'tests': tests,
        'previous_files_preserved': len(checkpoint['files']), 'source_manifest_sha256': r.sha(ART / 'SOURCE_MANIFEST.json'),
        'post2025_observations': 0, 'goal_complete': False, 'live_signoff': 'NOT_GRANTED',
        'qualification': 'Input identities and calculations verified. Known quality issues remain and must be checked against every accepted portfolio ledger.'})
    print({'inputs_verified': True, 'quality_issues_retained': paths['unresolved_execution_issues'], 'tests': tests}, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['paths', 'funding', 'finish'])
    {'paths': paths, 'funding': funding, 'finish': finish}[p.parse_args().action]()
