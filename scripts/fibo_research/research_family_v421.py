"""Frozen six-policy replay inputs, contract-specific funding and path quality."""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from types import FunctionType
import argparse
import gzip
import pickle
import shutil
import numpy as np
import pandas as pd
import research_v419 as previous
import research_v408 as family
import verify_research_v417 as independent
import verify_research_v416 as provenance

r = previous.r
x = previous.x
f = previous.f
data = previous.data
source = previous.source
ROOT = previous.ROOT
BASE = previous.ART.parent
PRIOR = BASE / 'research_v4_0_20'
ART = BASE / 'research_v4_0_21'
FAMILY = family.FAMILY
SCENARIOS = x.SCENARIOS


def phase_for(candidate, views):
    t = r.utc(pd.Timestamp(candidate['entry_ts'], unit='s', tz='UTC'))
    matches = [a for a in views if r.utc(a['first_open']) <= t <= r.utc(a['last_open'])]
    if len(matches) != 1:
        raise ValueError('Candidate must belong to exactly one observed contract view')
    return matches[0]


def audit_path(c, path, frame, events, horizon_hours, stamps=None):
    t = c['entry_ts']
    end = path['exit_ts']
    if stamps is None:
        stamps = r.epoch_seconds(frame.index)
    first = int(np.searchsorted(stamps, t))
    last = int(np.searchsorted(stamps, end))
    used = stamps[first:last]
    nominal = t + horizon_hours * 3600
    exit_stamps = [p[0] - 300 for p in path['trace'] if p[2] - p[3] > 1e-10]
    zero_exits = []
    missing_exits = []
    for ts in exit_stamps:
        i = int(np.searchsorted(stamps, ts))
        if i >= len(stamps) or stamps[i] != ts:
            missing_exits.append(ts + 300)
        elif frame.iloc[i].volume <= 0:
            zero_exits.append(ts + 300)
    return {
        'entry_zero_volume': bool(first >= len(stamps) or stamps[first] != t or frame.iloc[first].volume <= 0),
        'zero_volume_holding_bars': int((frame.iloc[first:last].volume <= 0).sum()),
        'zero_volume_exit_groups': zero_exits,
        'missing_exit_bars': missing_exits,
        'missing_bars': int((end - t) // 300 - len(used)),
        'grid_is_contiguous': bool(np.array_equal(used, np.arange(t, end, 300))),
        'horizon_truncated': path['exit_reason'] in ('horizon', 'horizon24') and end < nominal,
        'settlement_overlaps': [e['settlement_at'] for e in events if e['symbol'] == c['symbol']
                                and t < r.utc(e['settlement_at']).timestamp() <= end],
        'entry_allowed_by_known_lifecycle': bool(data.data.allowed_entry(c, events)),
    }


def issues(q):
    return bool(q['entry_zero_volume'] or q['zero_volume_exit_groups'] or q['missing_exit_bars']
                or q['missing_bars'] or not q['grid_is_contiguous'] or q['horizon_truncated']
                or q['settlement_overlaps'] or not q['entry_allowed_by_known_lifecycle'])


def funding_segments(rows, views):
    needs = {}
    for c in rows:
        if not previous.annual_eligible(c):
            continue
        a = phase_for(c, views[c['symbol']])
        key = c['symbol'] + '__' + a['phase']
        entry = c['entry_ts'] * 1000
        end = c['paths']['ladder']['exit_ts'] * 1000
        n = needs.setdefault(key, {'symbol': c['symbol'], 'phase': a['phase'],
            'first_entry_ms': entry, 'last_exit_ms': end, 'candidates': 0,
            'view_first_open': a['first_open'], 'view_last_open': a['last_open']})
        n['first_entry_ms'] = min(entry, n['first_entry_ms'])
        n['last_exit_ms'] = max(end, n['last_exit_ms'])
        n['candidates'] += 1
    for n in needs.values():
        n.update(start_ms=max(f.START_MS, n['first_entry_ms'] - 16 * 3600000),
                 end_ms=min(f.LIMIT_MS - 1, n['last_exit_ms'] + 16 * 3600000))
    return needs


def bounded_views():
    views = r.read(previous.b.ART / 'DATA_MANIFEST.json')['views']
    for symbol, items in views.items():
        for a in items:
            assert r.sha(a['path']) == a['sha256']
            index = pd.read_parquet(a['path'], columns=[]).index
            assert len(index) and index.is_unique and index.is_monotonic_increasing
            assert r.utc('2020-01-01') <= index[0] <= index[-1] < r.utc('2026-01-01')
            for key, value in [('first_open', index[0]), ('last_open', index[-1])]:
                if key in a:
                    assert r.utc(a[key]) == value
                a[key] = value.isoformat()
    return views


def merge_funding(frames):
    table = pd.concat(frames, ignore_index=True)
    assert table.funding_ts_ms.between(f.START_MS, f.LIMIT_MS - 1).all()
    assert np.isfinite(table[['funding_rate', 'mark_price']].to_numpy()).all() and (table.mark_price > 0).all()
    duplicates = table.loc[table.duplicated('funding_ts_ms', keep=False)]
    if len(duplicates) and (duplicates.groupby('funding_ts_ms').nunique(dropna=False) > 1).any().any():
        raise ValueError('Conflicting funding observations across snapshots')
    table = table.drop_duplicates('funding_ts_ms').sort_values('funding_ts_ms').reset_index(drop=True)
    return {'times': table.funding_ts_ms.to_numpy(), 'events': table.to_dict('records')}


def coverage(pack, entry_ms, exit_ms):
    stamps = pack['times']
    assert len(stamps) and stamps[0] <= entry_ms < exit_ms <= stamps[-1]
    left = max(0, np.searchsorted(stamps, entry_ms, side='right') - 1)
    right = min(len(stamps), np.searchsorted(stamps, exit_ms, side='left') + 1)
    assert np.all(np.diff(stamps[left:right]) <= 8 * 3600000 + 15000), 'Gap across held position'


def register():
    source.verify_sources()
    if (ART / 'PROTOCOL.json').exists():
        raise FileExistsError('Already registered')
    protocol = r.read(PRIOR / 'NEXT_FIXED_FAMILY_PROTOCOL.json')
    assert set(protocol['policy_family']) == {s['id'] for s in FAMILY}
    protocol.update(version='4.0.21', registered_at_utc=datetime.now(timezone.utc).isoformat(),
        parent_protocol_sha256=r.sha(PRIOR / 'NEXT_FIXED_FAMILY_PROTOCOL.json'),
        input_quality_scope='Audit every full and24h sniper path. Keep quality flags separate from candidate eligibility. Actual acceptance is evaluated later.',
        funding_episode_rule='Use distinct acquisition ranges per observed contract phase. Merge only exact overlapping observations. Require continuous funding through every candidate holding interval; inactive gaps between non-overlapping phases are not zero-filled.',
        implementation_freeze='This manifest freezes input preparation/acquisition/verification. Economic execution and verification will be frozen separately before new portfolio results.')
    r.save(ART / 'PROTOCOL.json', protocol)
    paths = [Path(__file__), ROOT / 'scripts/fibo_research/verify_family_inputs_v421.py',
             ROOT / 'tests/unit/fibo_short/test_family_inputs_v421.py', Path(family.__file__),
             ROOT / 'scripts/fibo_research/research_round02_v407.py', Path(x.__file__), Path(f.__file__),
             Path(independent.__file__), Path(provenance.__file__), Path(data.__file__)]
    for p in paths:
        dest = ART / 'source_snapshot' / p.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)
    inputs = [PRIOR / 'CHECKPOINT.json', PRIOR / 'NEXT_FIXED_FAMILY_PROTOCOL.json']
    inputs += [previous.b.ART / name for name in ('CANDIDATE_MANIFEST.json', 'CANDIDATE_AUDIT.json',
               'DATA_MANIFEST.json', 'EVENTS.json', 'MEMBERSHIP.json', 'PRIMARY_CANDIDATES.pkl.gz')]
    r.save(ART / 'SOURCE_MANIFEST.json', {'sources': {str(p): r.sha(p) for p in paths},
        'inputs': {str(p): r.sha(p) for p in inputs}, 'protocol_sha256': r.sha(ART / 'PROTOCOL.json')})


def verify_sources():
    source.verify_sources()
    saved = r.read(ART / 'SOURCE_MANIFEST.json')
    assert saved['protocol_sha256'] == r.sha(ART / 'PROTOCOL.json')
    for group in ('sources', 'inputs'):
        for path, digest in saved[group].items():
            assert r.sha(path) == digest, path


def prepare():
    verify_sources()
    if (ART / 'PATH_MANIFEST.json').exists():
        raise FileExistsError('Inputs already frozen')
    manifest = r.read(previous.b.ART / 'CANDIDATE_MANIFEST.json')
    views = bounded_views()
    r.save(ART / 'OBSERVED_VIEWS.json', views)
    events = r.read(previous.b.ART / 'EVENTS.json')['events']
    members = r.read(previous.b.ART / 'MEMBERSHIP.json')
    expected_elite = {c['id']: c for c in source.load_candidates()}
    progress_path = ART / 'PREPARATION_PROGRESS.json'
    progress = r.read(progress_path) if progress_path.exists() else {'symbols': {}}
    assert all(a['source_sha256'] == manifest[s]['sha256'] for s, a in progress['symbols'].items())
    for s, item in sorted(manifest['symbols'].items()):
        if s in progress['symbols']:
            a = progress['symbols'][s]
            assert all(r.sha(ART / a[k]) == a[k + '_sha256'] for k in ('paths', 'audit'))
            continue
        assert r.sha(item['path']) == item['sha256']
        rows = data.data.v.load_rows(item['path'])
        shortened = family.transformed(rows, next(a for a in FAMILY if a['id'] == 'sniper_horizon24'))
        h24 = {c['id']: c for c in shortened}
        checks = []
        if rows:
            frame = data.load_bars(s)
            stamps = r.epoch_seconds(frame.index)
            for c in rows:
                t = pd.Timestamp(c['entry_ts'], unit='s', tz='UTC')
                assert c['decision_ts'] + 300 == c['entry_ts'] and c['entry'] == frame.at[t, 'open']
                assert s in {a['symbol'] for a in members[t.strftime('%Y-%m')]}
                phase_for(c, views[s])
                for mode, value in [('full', c)] + ([('h24', h24[c['id']])] if c['id'] in h24 else []):
                    horizon = 24 if mode == 'h24' else (72 if c['tf'] == '4h' else 120)
                    q = audit_path(value, value['paths']['ladder'], frame, events, horizon, stamps)
                    checks.append({'id': c['id'], 'mode': mode, 'annual_eligible': previous.annual_eligible(c),
                                   'quality': q, 'has_execution_issue': issues(q)})
        folder = ART / 'prepared'
        folder.mkdir(exist_ok=True)
        path = folder / f'{s}.pkl.gz'
        with gzip.open(path, 'wb') as fh:
            pickle.dump({'full': rows, 'h24': shortened}, fh, protocol=5)
        audit = folder / f'{s}.json'
        r.save(audit, checks)
        progress['symbols'][s] = {'source_sha256': item['sha256'], 'paths': str(path.relative_to(ART)),
            'paths_sha256': r.sha(path), 'audit': str(audit.relative_to(ART)), 'audit_sha256': r.sha(audit),
            'full_count': len(rows), 'h24_count': len(shortened)}
        r.save(progress_path, progress)
        print(f'Input paths {len(progress["symbols"])}/{len(manifest["symbols"])} {s}: {len(rows)} full, {len(shortened)} short', flush=True)
    all_rows = []
    all_short = []
    checks = []
    for s, a in progress['symbols'].items():
        with gzip.open(ART / a['paths'], 'rb') as fh:
            pack = pickle.load(fh)
        all_rows.extend(pack['full'])
        all_short.extend(pack['h24'])
        checks.extend(r.read(ART / a['audit']))
    found_elite = {c['id']: c for c in all_rows if r.passes(c, 'elite_sniper') and previous.annual_eligible(c)}
    assert found_elite == expected_elite
    needs = funding_segments(all_rows, views)
    r.save(ART / 'funding/REQUIREMENTS.json', needs)
    counts = {}
    for spec in FAMILY:
        selected = family.transformed(all_rows, spec) if 'hours' in spec else [c for c in all_rows if r.passes(c, spec['gate'])]
        selected = [c for c in selected if previous.annual_eligible(c)]
        counts[spec['id']] = {'candidates': len(selected), 'symbols': len({c['symbol'] for c in selected}),
                              'years': dict(Counter(str(pd.Timestamp(c['entry_ts'], unit='s', tz='UTC').year) for c in selected))}
    r.save(ART / 'PATH_MANIFEST.json', {'symbols': progress['symbols'], 'all_full': len(all_rows), 'all_h24': len(all_short),
        'elite_baseline_candidates_exact': len(found_elite), 'policies': counts,
        'quality_issues': [a for a in checks if a['has_execution_issue']],
        'holding_zero_volume_flags': [a for a in checks if a['quality']['zero_volume_holding_bars']],
        'funding_segments': len(needs), 'funding_symbols': len({n['symbol'] for n in needs.values()}),
        'source_manifest_sha256': r.sha(ART / 'SOURCE_MANIFEST.json'), 'post2025_observations': 0})
    print({'policies': counts, 'issues': sum(a['has_execution_issue'] for a in checks), 'funding_segments': len(needs)}, flush=True)


def load_paths():
    manifest = r.read(ART / 'PATH_MANIFEST.json')
    assert manifest['source_manifest_sha256'] == r.sha(ART / 'SOURCE_MANIFEST.json')
    out = {'full': [], 'h24': []}
    for a in manifest['symbols'].values():
        assert r.sha(ART / a['paths']) == a['paths_sha256']
        with gzip.open(ART / a['paths'], 'rb') as fh:
            pack = pickle.load(fh)
        for mode in out:
            out[mode].extend(pack[mode])
    return out


def fetch_segment(key, n):
    root = ART / 'funding_segments' / key
    # Isolate only the function's output root; shared get_json/throttle retain
    # their one process-wide request limiter. Frozen original globals stay intact.
    fetch = FunctionType(f.fetch_symbol.__code__, {**vars(f), 'ART': root}, name='fetch_segment_symbol')
    _, record = fetch(n['symbol'], n)
    assert not any(record[k] for k in ('gaps_over_8h', 'left_edge_uncovered', 'right_edge_uncovered', 'local_differences_ms'))
    return {'symbol': n['symbol'], 'phase': n['phase'], 'mode': 'new_bounded_official_download',
            'path': str(root / 'funding/snapshots' / f'{n["symbol"]}.parquet'),
            'sha256': record['sha256'], 'record': record, 'requirements': n}


def acquire_funding():
    verify_sources()
    needs = r.read(ART / 'funding/REQUIREMENTS.json')
    choices = defaultdict(list)
    for number in (19, 17, 16, 15, 12, 11, 10, 9):
        root = BASE / f'research_v4_0_{number}'
        for s, item in r.read(root / 'funding/MANIFEST.json')['symbols'].items():
            path = Path(item['path']) if 'path' in item else root / 'funding/snapshots' / f'{s}.parquet'
            choices[s].append((path, item.get('record', item)))
    records = {}
    pending = {}
    for key, n in needs.items():
        for path, a in choices[n['symbol']]:
            if not a['gaps_over_8h'] and not a['local_differences_ms'] and a['first_event_ms'] <= n['first_entry_ms'] <= n['last_exit_ms'] <= a['last_event_ms']:
                assert r.sha(path) == a['sha256']
                records[key] = {'symbol': n['symbol'], 'phase': n['phase'], 'mode': 'reuse_verified',
                                'path': str(path), 'sha256': a['sha256'], 'record': a, 'requirements': n}
                break
        if key not in records:
            pending[key] = n
    r.save(ART / 'funding/ACQUISITION_PLAN.json', {'reused': sorted(records), 'new': sorted(pending),
        'requirements_sha256': r.sha(ART / 'funding/REQUIREMENTS.json')})
    print(f'Funding {len(records)} reused segments; {len(pending)} new bounded downloads.', flush=True)
    errors = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(fetch_segment, key, n): key for key, n in pending.items()}
        for future in as_completed(jobs):
            key = jobs[future]
            try:
                records[key] = future.result()
                print(f'Funding {len(records)}/{len(needs)} {key}', flush=True)
            except Exception as exc:
                errors[key] = str(exc)
                print(f'Funding unresolved {key}: {exc}', flush=True)
            r.save(ART / 'funding/PROGRESS.json', {'completed': len(records), 'total': len(needs), 'errors': errors})
    r.save(ART / 'funding/MANIFEST.json', {'segments': records, 'errors': errors, 'all_passed': not errors and len(records) == len(needs),
        'requirements_sha256': r.sha(ART / 'funding/REQUIREMENTS.json')})
    if errors:
        raise RuntimeError(errors)


def load_funding():
    manifest = r.read(ART / 'funding/MANIFEST.json')
    assert manifest['all_passed'] and not manifest['errors']
    assert manifest['requirements_sha256'] == r.sha(ART / 'funding/REQUIREMENTS.json')
    groups = defaultdict(list)
    for key, a in manifest['segments'].items():
        assert r.sha(a['path']) == a['sha256']
        frame = pd.read_parquet(a['path'])
        pack = merge_funding([frame])
        coverage(pack, a['requirements']['first_entry_ms'], a['requirements']['last_exit_ms'])
        groups[a['symbol']].append(frame)
    out = {s: merge_funding(frames) for s, frames in groups.items()}
    for c in load_paths()['full']:
        if previous.annual_eligible(c):
            coverage(out[c['symbol']], c['entry_ts'] * 1000, c['paths']['ladder']['exit_ts'] * 1000)
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['register', 'prepare', 'funding'])
    {'register': register, 'prepare': prepare, 'funding': acquire_funding}[p.parse_args().action]()
