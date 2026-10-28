"""Evidence consolidation and causal selection audit; no new strategy optimization."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import json
import numpy as np
import research_v419 as v

r = v.r
ROOT = v.ROOT
ART = ROOT / 'artifacts/fibo_trend_short/research_v4_0_20'
PRIOR = v.ART
BASE = PRIOR.parent
SCENARIOS = ('standard_vip6', 'stress_regular')

# Editorial interpretation, kept separate from the immutable historical entries.
NOTES = {
    'MA407-01': ('Risk control', 'Giữ bộ giới hạn vốn và sizing theo stop để nghiên cứu tiếp; giảm drawdown không tự tạo alpha.', 'CONTROL_COMPONENT'),
    'MA407-02': ('Elite gate', 'Điểm ước lượng cải thiện khi thêm Elite vào Sniper; CI so sánh còn chứa 0 ở cả hai mức chi phí.', 'UNCONFIRMED_SIGNAL'),
    'MA407-03': ('Sniper confirmation', 'Sniper giảm lỗ so với M6 ở bản stress; CI tương đối dương chưa điều chỉnh nhiều lần thử, trong khi cả hai vẫn lỗ.', 'RELATIVE_EVIDENCE_ONLY'),
    'MA407-04': ('BTC regime', 'Chỉ có bằng chứng phát triển ban đầu với chuẩn phí cũ; chưa được xác nhận bằng hai chuẩn chi phí hiện hành.', 'DEVELOPMENT_ONLY'),
    'MA407-05': ('Score 68', 'Chỉ có bằng chứng phát triển ban đầu với chuẩn phí cũ; chưa xác nhận giá trị tăng thêm ngoài các cổng hiện tại.', 'DEVELOPMENT_ONLY'),
    'MA407-06': ('TP1 risk reward', 'Không đạt trong phép so sánh ban đầu; lưu giả thuyết và kết quả âm.', 'UNSUPPORTED_IN_TESTED_SCOPE'),
    'MA407-07': ('Full TP1 exit', 'Đã có đối chiếu thoát lệnh ở v4.0.12; chưa có ưu thế chắc chắn trong giai đoạn 2024–2025.', 'EXIT_ABLATION_UNCONFIRMED'),
    'MA407-08': ('Sniper RR interaction', 'Điểm ước lượng tăng khi thêm RR vào giới hạn giữ 24 giờ; CI tương đối còn chứa 0 và stress vẫn âm.', 'UNCONFIRMED_INTERACTION'),
    'MA407-09': ('24 hour holding', 'Giới hạn 24 giờ không cải thiện kết quả stress sáu năm so với Sniper nguyên bản; holdout 2025 đã được dùng.', 'NO_CONFIRMED_HORIZON_BENEFIT'),
    'MA407-10': ('Timeframe ablation', 'Tách H4 và D1 không vượt cổng phát triển trong vòng đã thử.', 'FAILED_DEVELOPMENT_GATE'),
    'MA407-11': ('Stop distance filter', 'Ngưỡng stop 10% không vượt cổng phát triển trong vòng đã thử.', 'FAILED_DEVELOPMENT_GATE'),
    'MA407-12': ('Past known funding filter', 'Kết quả phát triển hỗn hợp; chỉ được dùng funding đã công bố ở thời điểm quyết định. Chưa có OOS mới.', 'DEVELOPMENT_ONLY'),
    'MA410-Q2': ('Negative momentum control', 'Không xác nhận giá trị chọn coin tăng thêm của Fibo trong phép ghép đối chứng đà giảm.', 'MATCHED_EDGE_UNCONFIRMED'),
    'MA411-Q2A': ('Positive momentum control', 'Không xác nhận giá trị tăng thêm trong vũ trụ cũ; có tái kiểm tra mở rộng ở v4.0.16.', 'MATCHED_EDGE_UNCONFIRMED'),
    'MA412-Q3-1': ('Stop only exit', 'Thang TP tốt hơn stop-only ở điểm ước lượng toàn kỳ, nhưng khác biệt 2024–2025 chưa chắc chắn; hiệu ứng gồm thay đổi vốn và lệnh nhận.', 'RELATIVE_EXIT_EVIDENCE_ONLY'),
    'MA412-Q3-2': ('Full TP1 comparison', 'Thoát toàn bộ TP1 và thang TP chưa khác biệt chắc chắn trong 2024–2025.', 'EXIT_ABLATION_UNCONFIRMED'),
    'MA413-DATA1': ('Universe coverage', 'Vũ trụ mở rộng đã được tái chạy kinh tế ở v4.0.15. Bằng chứng sửa phạm vi dữ liệu, không phải alpha.', 'REPLAY_COMPLETED_IN_V415'),
    'MA414-DATA2': ('Contract lifecycle', 'Các sự kiện hợp đồng đã ghi nhận được cô lập và tái chạy ở v4.0.15; không chứng nhận danh mục sự kiện sàn là đầy đủ tuyệt đối.', 'REPLAY_COMPLETED_IN_V415'),
    'MA415-U1': ('Expanded universe', 'Điểm ước lượng tốt hơn trên vũ trụ mở rộng; CI còn chứa 0 và stress toàn kỳ âm.', 'EDGE_UNCONFIRMED'),
    'MA416-U2': ('Matched 24 hour selection', 'Ghép đối chứng cùng thời điểm, momentum dương và biến động không xác nhận lợi thế chọn Fibo.', 'MATCHED_EDGE_UNCONFIRMED'),
    'MA417-E1': ('Matched original exits', 'Dùng stop và thang TP nguyên bản cho cả hai phía vẫn chưa xác nhận lợi thế chọn Fibo.', 'MATCHED_EDGE_UNCONFIRMED'),
    'MA418-C1': ('Execution cost sensitivity', 'Chi phí là giới hạn quan trọng; toàn kỳ đổi dấu giữa các điểm trượt giá 30 và 40 bps đã chạy. Không suy ra một ngưỡng hòa vốn được bảo đảm.', 'EXECUTION_DIAGNOSTIC'),
    'MA419-C2': ('Continuous portfolio', 'Đặt lại trạng thái năm không giải thích stress âm; thêm hai lệnh cuối năm chỉ làm kết quả giảm nhẹ.', 'EXECUTION_DIAGNOSTIC'),
}


def past_summary(nodes, scenario):
    equity = 100.0
    points = [100.0]
    for node in nodes:
        a = node[scenario]
        points.extend(equity / 100 * np.asarray(a['curve_values'])[1:])
        equity *= 1 + a['return_pct'] / 100
    a = np.asarray(points)
    return {'return_pct': equity - 100,
            'max_dd_pct': float(np.max(1 - a / np.maximum.accumulate(a)) * 100),
            'trades': sum(p[scenario]['trades'] for p in nodes),
            'missing_bars': sum(p[scenario]['accepted_missing_execution_bars'] for p in nodes)}


def select_from_past(annual, year, policy_ids):
    years = [str(y) for y in range(2020, year)]
    if len(years) < 2 or any(y not in annual for y in years):
        raise ValueError('At least two complete earlier years are required')
    audit = {}
    qualified = []
    for pid in policy_ids:
        if pid == 'reference_m6_fixed':
            continue
        nodes = [annual[y][pid] for y in years]
        standard = past_summary(nodes, SCENARIOS[0])
        stress = past_summary(nodes, SCENARIOS[1])
        worst_dd = max(n[s]['max_dd_pct'] for n in nodes for s in SCENARIOS)
        rules = {
            'at_least_60_trades': standard['trades'] >= 60,
            'every_prior_standard_year_positive': all(n[SCENARIOS[0]]['return_pct'] > 0 for n in nodes),
            'linked_stress_nonnegative': stress['return_pct'] >= 0,
            'worst_annual_dd_at_most15': worst_dd <= 15,
            'no_accepted_missing_execution_bars': standard['missing_bars'] == stress['missing_bars'] == 0,
        }
        eligible = all(rules.values())
        audit[pid] = {'standard': standard, 'stress': stress, 'worst_annual_dd': worst_dd,
                      'rules': rules, 'failed_rules': [k for k, value in rules.items() if not value],
                      'eligible': eligible}
        if eligible:
            qualified.append((stress['return_pct'] - stress['max_dd_pct'], pid))
    qualified.sort(key=lambda p: (-p[0], p[1]))
    return {'test_year': year, 'training_years': years,
            'selected': qualified[0][1] if qualified else 'CASH', 'audit': audit,
            'uses_test_year_metrics': False, 'fresh_oos': False}


def locations():
    paths = [PRIOR / name for name in ('CHECKPOINT.json', 'MINI_ALPHA_REGISTRY.json', 'RESULTS.json',
             'INDEPENDENT_VERIFICATION.json', 'EXACT_MARK_DATA_REQUEST.json', 'REPORT_CONSISTENCY.json')]
    for number in (9, 12, 15, 16, 17, 18):
        paths += [BASE / f'research_v4_0_{number}' / name for name in ('RESULTS.json', 'INDEPENDENT_VERIFICATION.json', 'PROTOCOL.json')]
    paths += [BASE / 'research_v4_0_9' / f'LOCK_TEST_{year}.json' for year in range(2022, 2026)]
    paths += [BASE / 'research_v4_0_11/funding_tick_spotcheck' / name for name in ('RESULTS.json', 'VERIFICATION.json')]
    paths += [BASE / 'research_v4_0_15' / name for name in ('CANDIDATE_AUDIT.json', 'MEMBERSHIP_CORRECTION.json')]
    paths += [ROOT / 'scripts/fibo_research' / name for name in
              ('research_review_v420.py', 'verify_research_review_v420.py', 'research_v409.py', 'research_v408.py')]
    paths += [ROOT / 'tests/unit/fibo_short/test_research_review_v420.py']
    return paths


def register():
    if (ART / 'PROTOCOL.json').exists():
        raise FileExistsError('Review protocol already registered')
    v.verify_sources()
    r.save(ART / 'PROTOCOL.json', {
        'version': '4.0.20-evidence-review', 'registered_at_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Consolidate all 23 records, independently audit past-only selection, and specify missing data and OOS evidence.',
        'no_new_signal_variants': True, 'new_market_observations': 0, 'data_end_exclusive': '2026-01-01',
        'walk_forward_scope': 'Reconstruct the v409 six-policy selector from prior years only and reconcile original locks. Apply exactly its eligibility rules to the single corrected v415 elite_sniper policy as a descriptive gate audit, not a rerun of the entire corrected family.',
        'selection_thresholds_origin': 'Unchanged v409 protocol; no relaxation after seeing outcomes.',
        'catalogue': 'Preserve all historical entries; current interpretation and supersession pointers are separate. Do not count review paperwork as another mini-alpha.',
        'oos': 'Retrospective replay cannot undo global historical reuse. Prospective route remains a pending user-scope decision; do not consume future observations.',
        'funding_procurement': 'Group already identified missing settlement marks by contract/date. Candidate vendor coverage is not certified by documentation or four free samples.',
        'goal_complete': False, 'live_signoff': 'NOT_GRANTED'})
    r.save(ART / 'SOURCE_MANIFEST.json', {'files': {str(p): r.sha(p) for p in locations()},
                                       'protocol_sha256': r.sha(ART / 'PROTOCOL.json')})


def verify_sources():
    manifest = r.read(ART / 'SOURCE_MANIFEST.json')
    assert manifest['protocol_sha256'] == r.sha(ART / 'PROTOCOL.json')
    for path, digest in manifest['files'].items():
        assert r.sha(path) == digest, path


def evidence_ref(path, pointer=''):
    return {'path': str(path), 'sha256': r.sha(path), 'json_pointer': pointer}


def build():
    verify_sources()
    if (ART / 'REVIEW.json').exists():
        raise FileExistsError('Review already generated')
    source = {n: r.read(BASE / f'research_v4_0_{n}/RESULTS.json') for n in (9, 12, 15, 16, 17, 18, 19)}
    for n, result in source.items():
        check = r.read(BASE / f'research_v4_0_{n}/INDEPENDENT_VERIFICATION.json')
        assert check['results_sha256'] == r.sha(BASE / f'research_v4_0_{n}/RESULTS.json')
        assert any(check.get(k) is True for k in ('all_passed', 'all_checks_passed', 'all_accounting_checks_passed'))
        assert result['fresh_oos'] is False
    policies = list(source[9]['annual']['2020'])
    old = {str(year): select_from_past(source[9]['annual'], year, policies) for year in range(2022, 2026)}
    updated_annual = {y: {'elite_sniper_risk': value} for y, value in source[15]['annual'].items()}
    updated = {str(year): select_from_past(updated_annual, year, ['elite_sniper_risk']) for year in range(2022, 2026)}
    r.save(ART / 'WALK_FORWARD_AUDIT.json', {
        'historical_family_reconstruction': old, 'corrected_single_policy_gate_audit': updated,
        'historical_source': evidence_ref(BASE / 'research_v4_0_9/RESULTS.json', '/annual'),
        'corrected_source': evidence_ref(BASE / 'research_v4_0_15/RESULTS.json', '/annual'),
        'scope': 'Corrected audit covers one fixed policy; no claim that all six were rerun on the corrected universe.',
        'fresh_oos': False, 'new_ex_ante_locks': False})
    registry = r.read(PRIOR / 'MINI_ALPHA_REGISTRY.json')
    assert set(NOTES) == {p['id'] for p in registry['entries']}
    catalogue = []
    for i, entry in enumerate(registry['entries']):
        title, note, state = NOTES[entry['id']]
        latest = entry.get('evidence_by_stage', {}).get('v409_dual_cost_historical_funding')
        item = {'id': entry['id'], 'name': title, 'hypothesis_vi': entry.get('hypothesis_vi', title),
                'historical_status': entry['status'], 'current_status': state, 'interpretation_vi': note,
                'usable_as_proven_alpha': False, 'fresh_oos': False,
                'source': evidence_ref(PRIOR / 'MINI_ALPHA_REGISTRY.json', f'/entries/{i}')}
        if latest:
            item['legacy_dual_cost_comparison'] = latest
        catalogue.append(item)
    for item in catalogue:
        if item['id'] in ('MA413-DATA1', 'MA414-DATA2'):
            item['follow_up_evidence'] = [evidence_ref(BASE / 'research_v4_0_15' / name)
                                          for name in ('CANDIDATE_AUDIT.json', 'MEMBERSHIP_CORRECTION.json', 'INDEPENDENT_VERIFICATION.json')]
        if item['id'] == 'MA407-07':
            item['follow_up_evidence'] = [evidence_ref(BASE / 'research_v4_0_12/RESULTS.json', '/comparisons')]
    registry['current_review'] = catalogue
    registry.update(status='EVIDENCE_REVIEWED_NO_PROVEN_ALPHA', last_completed_stage='evidence_and_oos_readiness_review',
                    updated_at_utc=datetime.now(timezone.utc).isoformat(),
                    parent_registry=evidence_ref(PRIOR / 'MINI_ALPHA_REGISTRY.json'),
                    source_registry_sha256=r.sha(PRIOR / 'MINI_ALPHA_REGISTRY.json'),
                    current_results=evidence_ref(PRIOR / 'RESULTS.json'))
    registry['trial_accounting_v420'] = {'new_signal_parameters': 0, 'new_market_observations': 0,
                                        'new_alpha_entries': 0, 'descriptive_single_policy_gate_audit': True}
    r.save(ART / 'MINI_ALPHA_REGISTRY.json', registry)
    r.save(ART / 'EVIDENCE_CATALOG.json', {'entries': catalogue, 'entry_count': len(catalogue),
                                         'proven_alpha_count': sum(a['usable_as_proven_alpha'] for a in catalogue)})
    need = r.read(PRIOR / 'EXACT_MARK_DATA_REQUEST.json')
    symbol_dates = defaultdict(list)
    years = Counter()
    for e in need['events']:
        dt = datetime.fromtimestamp(e['funding_ts_ms'] / 1000, timezone.utc)
        assert dt.year <= 2025
        symbol_dates[(e['symbol'], dt.strftime('%Y-%m-%d'))].append(e['funding_ts_ms'])
        years[str(dt.year)] += 1
    request = {
        'source': evidence_ref(PRIOR / 'EXACT_MARK_DATA_REQUEST.json'),
        'unique_events': len(need['events']), 'symbols': len({e['symbol'] for e in need['events']}),
        'symbol_dates': len(symbol_dates), 'events_by_year': dict(sorted(years.items())),
        'earliest_event_ms': min(e['funding_ts_ms'] for e in need['events']),
        'latest_event_ms': max(e['funding_ts_ms'] for e in need['events']),
        'requested_fields': ['exchange', 'symbol', 'contract_identity_or_episode', 'funding_timestamp_utc_ms',
                             'settlement_mark_price', 'raw_exchange_event_timestamp', 'capture_timestamp', 'provenance', 'gap_flags'],
        'acceptance': ['Cover each requested event or label it unavailable explicitly.',
                       'Distinguish settlement-associated mark from latest observed websocket mark and candle OPEN.',
                       'No future ticks or forward-filled prices across an unreported outage.',
                       'Keep official realized funding rates; derivative ticker indicative rates must not overwrite settlements.',
                       'Require sample validation, timestamp semantics, and gap report before treating a supplier as sufficient.'],
        'candidate_provider': {
            'name': 'Tardis.dev', 'coverage_verified_for_full_request': False, 'price_verified': False,
            'documentation_url': 'https://docs.tardis.dev/historical-data-details/binance-futures',
            'documentation_checked_on': '2026-10-18',
            'qualification': 'Historical markPrice stream is a candidate source. Vendor discloses collection issues before2020-05-14. Its separately recorded fundingRate channel starts2026-10-16 and does not establish2020..2025 settlement coverage.',
            'free_sample_scope': 'First calendar day CSV datasets are public; existing four-event spotcheck does not certify the complete request.',
            'local_spotcheck': evidence_ref(BASE / 'research_v4_0_11/funding_tick_spotcheck/VERIFICATION.json')},
        'purchase_made': False, 'supplier_contacted': False,
        'rows': [{'symbol': s, 'date_utc': d, 'funding_timestamps_ms': ts}
                 for (s, d), ts in sorted(symbol_dates.items())],
    }
    r.save(ART / 'DATA_PROCUREMENT_REQUIREMENTS.json', request)
    latest = source[19]
    facts = {
        'continuous_portfolio': {key: latest[key] for key in ('periods', 'scenarios')},
        'matched_24h': {s: source[16]['results'][s]['splits']['retrospective_oos_2024_2025'] for s in SCENARIOS},
        'matched_original_exits': {s: source[17]['results'][s]['splits']['retrospective_oos_2024_2025'] for s in SCENARIOS},
        'cost_sign_diagnostics': source[18]['sign_diagnostics'],
        'walk_forward': {'original': {y: a['selected'] for y, a in old.items()},
                         'corrected_single_policy': {y: a['selected'] for y, a in updated.items()}},
    }
    requirements = [
        {'requirement': 'Backtest uses only market observations through2025', 'status': 'VERIFIED_FOR_REPORTED_RUNS', 'evidence': evidence_ref(PRIOR / 'INDEPENDENT_VERIFICATION.json')},
        {'requirement': 'User standard/stress costs on every fill', 'status': 'VERIFIED', 'evidence': evidence_ref(PRIOR / 'RESULTS.json', '/scenarios')},
        {'requirement': 'Actual signed historical funding', 'status': 'RATES_VERIFIED_MARKS_PARTIALLY_APPROXIMATE', 'evidence': evidence_ref(ART / 'DATA_PROCUREMENT_REQUIREMENTS.json')},
        {'requirement': 'OOS', 'status': 'RETROSPECTIVE_ONLY_FRESH_OOS_NOT_ESTABLISHED', 'evidence': evidence_ref(ART / 'WALK_FORWARD_AUDIT.json')},
        {'requirement': 'Retain reusable mini-alpha discoveries and failures', 'status': '23_RECORDS_RECONCILED_NONE_PROVEN', 'evidence': evidence_ref(ART / 'EVIDENCE_CATALOG.json')},
        {'requirement': 'Complete a validated trading strategy', 'status': 'NOT_ESTABLISHED', 'evidence': evidence_ref(PRIOR / 'RESULTS.json', '/periods')},
    ]
    r.save(ART / 'OOS_READINESS.json', {
        'requirements': requirements, 'fresh_oos_available_with_current_evidence': False,
        'pending_scope_question': 'Fresh prospective paper observations after a model lock, or retrospective walk-forward only through2025?',
        'prospective_started': False, 'post2025_data_authorized_by_this_review': False,
        'review_controls': ['Freeze model, cost scenarios and decision rules before new observations.',
                            'Declare endpoints and evaluation horizon before monitoring; do not stop when results first turn positive.',
                            'Keep rejected hypotheses and all costs visible; any redesign consumes a new validation stage.',
                            'Separate selection contribution, exit contribution, risk sizing and portfolio NAV.'],
        'goal_complete': False, 'live_signoff': 'NOT_GRANTED'})
    r.save(ART / 'REVIEW.json', {'version': '4.0.20-evidence-review', 'facts': facts,
        'catalogue_count': len(catalogue), 'proven_alpha_count': 0,
        'decision': 'RESEARCH_CANDIDATE_NOT_VALIDATED_FOR_LIVE', 'new_market_observations': 0,
        'new_signal_parameters': 0, 'fresh_oos': False, 'goal_complete': False, 'live_signoff': 'NOT_GRANTED'})
    print({'entries': len(catalogue), 'wfo': facts['walk_forward'], 'funding_events': request['unique_events'],
           'funding_symbols': request['symbols'], 'symbol_dates': request['symbol_dates']}, flush=True)


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['register', 'build'])
    {'register': register, 'build': build}[p.parse_args().action]()
