"""Full frozen family and past-only selection on corrected pre2026 inputs."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import gzip
import json
import numpy as np
import research_family_v421 as v
import research_review_v420 as selection
import research_v419 as calendar

r = v.r
ART = v.ART
SPLITS = {'development_context_2020_2023': ('2020-01-01', '2024-01-01'),
          'retrospective_2024_2025': ('2024-01-01', '2026-01-01'),
          'all_2020_2025': ('2020-01-01', '2026-01-01')}


def register():
    v.verify_sources()
    check = r.read(ART / 'INPUT_VERIFICATION.json')
    assert check['all_passed']
    if (ART / 'ECONOMIC_PROTOCOL.json').exists():
        raise FileExistsError('Economic implementation already frozen')
    sources = [Path(__file__), Path(selection.__file__), Path(calendar.__file__),
               v.ROOT / 'scripts/fibo_research/verify_family_results_v421.py',
               v.ROOT / 'tests/unit/fibo_short/test_family_selection_v421.py']
    r.save(ART / 'ECONOMIC_PROTOCOL.json', {
        'registered_at_utc': datetime.now(timezone.utc).isoformat(),
        'parent_protocol_sha256': r.sha(ART / 'PROTOCOL.json'),
        'input_verification_sha256': r.sha(ART / 'INPUT_VERIFICATION.json'),
        'sources': {str(p): r.sha(p) for p in sources},
        'selection': 'Unchanged v409 economic rules and ranking implemented by independently checked v420 selector. Additionally any accepted unresolved execution issue in prior training years makes a policy unqualified. Current-year quality affects current result validity, never retroactively changes its earlier selection.',
        'all_nodes_retained': True, 'cash_return_assumption': 'No interest, no trades or fees for a cash year.',
        'statistics': 'v419 marked_window calendar intervals, 4week circular block10000 seed412. Absolute95percent; exploratory and not globally multiple-trial-adjusted.',
        'fixed_splits': SPLITS, 'wfo_splits': {'retrospective_selected_2022_2025': ['2022-01-01', '2026-01-01'],
                                            'retrospective_selected_2024_2025': ['2024-01-01', '2026-01-01']},
        'new_signal_parameters': 0, 'fresh_oos': False, 'goal_complete': False, 'live_signoff': 'NOT_GRANTED'})


def fingerprint():
    return {name: r.sha(ART / path) for name, path in [
        ('economic_protocol_sha256', 'ECONOMIC_PROTOCOL.json'), ('input_verification_sha256', 'INPUT_VERIFICATION.json'),
        ('path_manifest_sha256', 'PATH_MANIFEST.json'), ('funding_manifest_sha256', 'funding/MANIFEST.json')]}


def verify_sources():
    v.verify_sources()
    p = r.read(ART / 'ECONOMIC_PROTOCOL.json')
    assert p['parent_protocol_sha256'] == r.sha(ART / 'PROTOCOL.json')
    assert p['input_verification_sha256'] == r.sha(ART / 'INPUT_VERIFICATION.json')
    for path, digest in p['sources'].items():
        assert r.sha(path) == digest, path


def policy_source(pack, spec):
    if 'hours' in spec:
        return [c for c in pack['h24'] if c['rr1'] >= spec.get('rr_min', 0)]
    return pack['full']


def choose(annual, year):
    chosen = selection.select_from_past(annual, year, [s['id'] for s in v.FAMILY])
    ranked = []
    for pid, audit in chosen['audit'].items():
        valid = all(annual[y][pid][s]['execution_qualified'] for y in chosen['training_years'] for s in v.SCENARIOS)
        audit['rules']['no_unresolved_accepted_execution_issues'] = valid
        audit['failed_rules'] = [k for k, val in audit['rules'].items() if not val]
        audit['eligible'] = all(audit['rules'].values())
        if audit['eligible']:
            ranked.append((audit['stress']['return_pct'] - audit['stress']['max_dd_pct'], pid))
    ranked.sort(key=lambda a: (-a[0], a[1]))
    chosen['selected'] = ranked[0][1] if ranked else 'CASH'
    return chosen


def ledger(year, pid, scenario):
    with gzip.open(ART / 'runs' / f'{year}_{pid}_{scenario}.json.gz', 'rt', encoding='utf8') as fh:
        return json.load(fh)


def run_node(candidates, steps, funding, year, spec, scenario, flagged):
    key = f'{year}_{spec["id"]}_{scenario}'
    folder = ART / 'runs'
    folder.mkdir(exist_ok=True)
    path = folder / f'{key}.json.gz'
    receipt = folder / f'{key}.json'
    fp = fingerprint()
    if receipt.exists():
        saved = r.read(receipt)
        assert all(saved[k] == val for k, val in fp.items()) and saved['ledger_sha256'] == r.sha(path)
        return saved['metric']
    metric = v.x.portfolio(candidates, spec, f'{year}-01-01', f'{year+1}-01-01', v.SCENARIOS[scenario], funding, steps)
    detail = {name: metric.pop(name) for name in ('ledger', 'curve')}
    mode = 'h24' if 'hours' in spec else 'full'
    bad = [p['id'] for p in detail['ledger'] if (p['id'], mode) in flagged]
    metric.update(curve_values=[a[1] for a in detail['curve']], accepted_execution_issue_ids=bad,
                  execution_qualified=not bad)
    if spec['id'] == 'elite_sniper_risk':
        old = v.previous.b.ledger(year, scenario)
        assert detail == old, 'Elite-sniper changed from v415'
    with gzip.open(path, 'wt', encoding='utf8') as fh:
        json.dump(detail, fh, separators=(',', ':'), allow_nan=False)
    r.save(receipt, {'metric': metric, 'ledger_sha256': r.sha(path), **fp})
    print(f'{key}: NAV {metric["return_pct"]:+.3f}%, DD {metric["max_dd_pct"]:.3f}%, N={metric["trades"]}, quality issues={len(bad)}', flush=True)
    return metric


def evaluate():
    verify_sources()
    assert not (ART / 'RESULTS.json').exists()
    funding = v.load_funding()
    pack = v.load_paths()
    flags = {(a['id'], a['mode']) for a in r.read(ART / 'PATH_MANIFEST.json')['quality_issues']}
    annual = {}
    locks = {}
    for year in range(2020, 2026):
        if year >= 2022:
            lock = choose(annual, year)
            path = ART / f'LOCK_TEST_{year}.json'
            if path.exists():
                saved = r.read(path)
                assert all(saved[k] == val for k, val in lock.items())
                assert all(saved[k] == val for k, val in fingerprint().items())
            else:
                saved = {**lock, **fingerprint(), 'locked_at_utc': datetime.now(timezone.utc).isoformat()}
                r.save(path, saved)
            locks[str(year)] = saved
        annual[str(year)] = {}
        lo = int(r.utc(f'{year}-01-01').timestamp())
        hi = int(r.utc(f'{year+1}-01-01').timestamp())-5*86400
        year_pack = {mode: [c for c in rows if lo <= c['entry_ts'] < hi] for mode, rows in pack.items()}
        steps = {mode: {c['id']: v.x.execution_steps(c) for c in rows} for mode, rows in year_pack.items()}
        for spec in v.FAMILY:
            rows = policy_source(year_pack, spec)
            mode = 'h24' if 'hours' in spec else 'full'
            annual[str(year)][spec['id']] = {s: run_node(rows, steps[mode], funding, year, spec, s, flags) for s in v.SCENARIOS}
        del steps, year_pack
    del pack, funding
    periods = {label: {} for label in SPLITS}
    for spec in v.FAMILY:
        pid = spec['id']
        for label in periods:
            periods[label][pid] = {}
        for scenario in v.SCENARIOS:
            curve = link_curves([ledger(year, pid, scenario)['curve'] for year in range(2020, 2026)])
            for label, (start, end) in SPLITS.items():
                metric, _, _ = calendar.marked_window(curve, start, end)
                years = range(int(start[:4]), int(end[:4]))
                metric.update(trades=sum(annual[str(y)][pid][scenario]['trades'] for y in years),
                    execution_qualified=all(annual[str(y)][pid][scenario]['execution_qualified'] for y in years))
                periods[label][pid][scenario] = metric
    selected = {}
    for scenario in v.SCENARIOS:
        nodes = []
        for year in range(2022, 2026):
            pid = locks[str(year)]['selected']
            if pid == 'CASH':
                nodes.append([(int(r.utc(f'{year}-01-01').timestamp()*1000), 100.),
                              (int(r.utc(f'{year+1}-01-01').timestamp()*1000), 100.)])
            else:
                nodes.append(ledger(year, pid, scenario)['curve'])
        curve = link_curves(nodes)
        selected[scenario] = {}
        for startyear in (2022, 2024):
            metric, _, _ = calendar.marked_window(curve, f'{startyear}-01-01', '2026-01-01')
            active = [(str(y), locks[str(y)]['selected']) for y in range(startyear, 2026) if locks[str(y)]['selected'] != 'CASH']
            metric.update(trades=sum(annual[y][pid][scenario]['trades'] for y, pid in active),
                          execution_qualified=all(annual[y][pid][scenario]['execution_qualified'] for y, pid in active))
            selected[scenario][f'{startyear}_2025'] = metric
    compact = {y: {pid: {s: {k: value for k, value in metric.items() if k not in ('curve_values', 'weekly_returns', 'weekly_ci')}
                          for s, metric in node.items()} for pid, node in yy.items()} for y, yy in annual.items()}
    r.save(ART / 'RESULTS.json', {'version': '4.0.21', 'annual': compact, 'fixed_policy_periods': periods,
        'walk_forward_locks': locks, 'walk_forward_oos': selected, 'scenarios': v.SCENARIOS,
        'fresh_oos': False, 'post2025_observations': 0, 'goal_complete': False, 'live_signoff': 'NOT_GRANTED', **fingerprint()})
    print({'selected': {y: a['selected'] for y, a in locks.items()}, 'full_fixed': periods['all_2020_2025']}, flush=True)


def link_curves(curves):
    points = []
    cash = 100.0
    for curve in curves:
        scale = cash / 100
        points.extend((t, value * scale) for t, value in curve)
        cash = curve[-1][1] * scale
    return points


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['register', 'evaluate'])
    {'register': register, 'evaluate': evaluate}[p.parse_args().action]()
