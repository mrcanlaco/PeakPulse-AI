"""Independent selection arithmetic and exact source-to-review reconciliation."""
from collections import Counter
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import research_review_v420 as v

r = v.r
ART = v.ART


def independent_audit(annual, year, ids):
    audit = {}
    scores = []
    for pid in ids:
        if pid == 'reference_m6_fixed':
            continue
        past = [annual[str(y)][pid] for y in range(2020, year)]
        std_count = sum(p['standard_vip6']['trades'] for p in past)
        stress_return = (math.prod(1 + p['stress_regular']['return_pct'] / 100 for p in past) - 1) * 100
        positive = all(p['standard_vip6']['return_pct'] > 0 for p in past)
        worst = max(p[s]['max_dd_pct'] for p in past for s in v.SCENARIOS)
        missing = sum(p[s]['accepted_missing_execution_bars'] for p in past for s in v.SCENARIOS)
        eligible = std_count >= 60 and positive and stress_return >= 0 and worst <= 15 and missing == 0
        # Independent peak scan of capital-linked paths, used only for the ranking.
        scale = 1.0
        peak = 100.0
        dd = 0.0
        for p in past:
            for nav in p['stress_regular']['curve_values'][1:]:
                marked = nav * scale
                peak = max(peak, marked)
                dd = max(dd, 100 * (1 - marked / peak))
            scale *= 1 + p['stress_regular']['return_pct'] / 100
        if eligible:
            scores.append((stress_return - dd, pid))
        audit[pid] = {'eligible': eligible, 'stress_return': stress_return, 'worst_dd': worst,
                      'std_trades': std_count, 'positive': positive, 'missing': missing}
    scores.sort(key=lambda a: (-a[0], a[1]))
    return scores[0][1] if scores else 'CASH', audit


def source_pointer(ref):
    assert r.sha(ref['path']) == ref['sha256']
    value = r.read(ref['path'])
    for token in ref.get('json_pointer', '').split('/')[1:]:
        token = token.replace('~1', '/').replace('~0', '~')
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def main():
    v.verify_sources()
    review = r.read(ART / 'REVIEW.json')
    catalogue = r.read(ART / 'EVIDENCE_CATALOG.json')
    current_registry = r.read(ART / 'MINI_ALPHA_REGISTRY.json')
    previous_registry = r.read(v.PRIOR / 'MINI_ALPHA_REGISTRY.json')
    assert current_registry['entries'] == previous_registry['entries']
    assert current_registry['current_review'] == catalogue['entries']
    assert len(catalogue['entries']) == len(previous_registry['entries']) == review['catalogue_count'] == 23
    assert len({p['id'] for p in catalogue['entries']}) == 23
    for entry in catalogue['entries']:
        original = source_pointer(entry['source'])
        assert original['id'] == entry['id'] and original['status'] == entry['historical_status']
        assert original['usable_as_proven_alpha'] is False and entry['usable_as_proven_alpha'] is False
        assert entry['fresh_oos'] is False
        if 'legacy_dual_cost_comparison' in entry:
            assert entry['legacy_dual_cost_comparison'] == original['evidence_by_stage']['v409_dual_cost_historical_funding']
        for ref in entry.get('follow_up_evidence', []):
            source_pointer(ref)
    wfo = r.read(ART / 'WALK_FORWARD_AUDIT.json')
    historical = source_pointer(wfo['historical_source'])
    corrected = source_pointer(wfo['corrected_source'])
    corrected = {y: {'elite_sniper_risk': row} for y, row in corrected.items()}
    eligible_checks = 0
    for label, annual in [('historical_family_reconstruction', historical),
                          ('corrected_single_policy_gate_audit', corrected)]:
        for year in range(2022, 2026):
            actual = wfo[label][str(year)]
            expected, audit = independent_audit(annual, year, list(annual['2020']))
            assert actual['selected'] == expected
            assert actual['training_years'] == [str(y) for y in range(2020, year)]
            assert not actual['uses_test_year_metrics']
            for pid, independent in audit.items():
                saved = actual['audit'][pid]
                assert saved['eligible'] == independent['eligible']
                assert saved['standard']['trades'] == independent['std_trades']
                assert np.allclose([saved['stress']['return_pct'], saved['worst_annual_dd']],
                                   [independent['stress_return'], independent['worst_dd']], atol=1e-9, rtol=0)
                eligible_checks += 1
            if label == 'historical_family_reconstruction':
                lock = r.read(v.BASE / f'research_v4_0_9/LOCK_TEST_{year}.json')
                assert lock['selected'] == expected
                assert lock['training_years'] == actual['training_years']
                for pid, a in audit.items():
                    assert lock['audit'][pid]['eligible'] == a['eligible']
    facts = review['facts']
    newest = r.read(v.PRIOR / 'RESULTS.json')
    assert facts['continuous_portfolio'] == {k: newest[k] for k in ('periods', 'scenarios')}
    for number, key in [(16, 'matched_24h'), (17, 'matched_original_exits')]:
        parent = r.read(v.BASE / f'research_v4_0_{number}/RESULTS.json')
        assert facts[key] == {s: parent['results'][s]['splits']['retrospective_oos_2024_2025'] for s in v.SCENARIOS}
    assert facts['cost_sign_diagnostics'] == r.read(v.BASE / 'research_v4_0_18/RESULTS.json')['sign_diagnostics']
    assert facts['walk_forward']['original'] == {y: a['selected'] for y, a in wfo['historical_family_reconstruction'].items()}
    assert facts['walk_forward']['corrected_single_policy'] == {y: a['selected'] for y, a in wfo['corrected_single_policy_gate_audit'].items()}
    request = r.read(ART / 'DATA_PROCUREMENT_REQUIREMENTS.json')
    source = source_pointer(request['source'])
    expected = {(p['symbol'], p['funding_ts_ms']) for p in source['events']}
    actual = [(row['symbol'], ts) for row in request['rows'] for ts in row['funding_timestamps_ms']]
    assert len(actual) == len(set(actual)) == request['unique_events'] == source['unique_events']
    assert set(actual) == expected
    assert request['symbols'] == len({p[0] for p in expected})
    assert request['symbol_dates'] == len(request['rows'])
    by_year = Counter()
    for row in request['rows']:
        for ts in row['funding_timestamps_ms']:
            date = v.datetime.fromtimestamp(ts / 1000, v.timezone.utc)
            assert date.strftime('%Y-%m-%d') == row['date_utc'] and date.year <= 2025
            by_year[str(date.year)] += 1
    assert dict(by_year) == request['events_by_year']
    assert not request['purchase_made'] and not request['supplier_contacted']
    assert not request['candidate_provider']['coverage_verified_for_full_request']
    readiness = r.read(ART / 'OOS_READINESS.json')
    for a in readiness['requirements']:
        source_pointer(a['evidence'])
    assert review['proven_alpha_count'] == catalogue['proven_alpha_count'] == 0
    assert not review['fresh_oos'] and not review['goal_complete'] and review['live_signoff'] == 'NOT_GRANTED'
    assert not readiness['prospective_started'] and not readiness['post2025_data_authorized_by_this_review']
    suites = list(ET.parse(ART / 'TESTS.xml').getroot().iter('testsuite'))
    tests = {k: sum(int(a.get(k, 0)) for a in suites) for k in ('tests', 'errors', 'failures', 'skipped')}
    assert tests['tests'] == 5 and tests['errors'] == tests['failures'] == tests['skipped'] == 0
    old = r.read(v.PRIOR / 'CHECKPOINT.json')
    for path, digest in old['files'].items():
        assert r.sha(v.PRIOR / path) == digest, path
    for path, digest in old['additional_sources'].items():
        assert r.sha(v.ROOT / path) == digest, path
    result = {'all_passed': True, 'historical_registry_entries_preserved': 23,
              'independent_yearly_selection_audits': 8, 'policy_year_eligibility_checks': eligible_checks,
              'original_ex_ante_locks_reconciled': 4, 'funding_events_grouped_exactly': len(expected),
              'new_alpha_entries': 0, 'previous_files_preserved': len(old['files']), 'tests': tests,
              'review_sha256': r.sha(ART / 'REVIEW.json'), 'goal_complete': False, 'live_signoff': 'NOT_GRANTED'}
    r.save(ART / 'VERIFICATION.json', result)
    print(result, flush=True)


if __name__ == '__main__':
    main()
