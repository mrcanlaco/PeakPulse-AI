"""Finite OOS feasibility review from frozen pre-2026 NAV, not new alpha search.

Normal-theory power is a planning approximation. Empirical circular-block
variance is not a guarantee of future stationarity or valid tail calibration.
No market download, future observation, order, or paper service is started.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'artifacts/fibo_trend_short'
PRIOR = BASE / 'research_v4_0_25'
ART = BASE / 'research_v4_0_26'
SOURCE = Path(__file__)
TEST = ROOT / 'tests/unit/fibo_short/test_oos_planning_v426.py'
LIMIT = pd.Timestamp('2026-01-01T00:00:00Z')
NORM = NormalDist()
LABELS = {
    'reference_m6_fixed': 'M6 khối lượng cố định',
    'm6_risk': 'M6 khối lượng theo stop',
    'elite_sniper_risk': 'Elite + Sniper',
    'sniper_risk': 'Sniper',
    'sniper_horizon24': 'Sniper tối đa 24 giờ',
    'sniper_rr1_horizon24': 'Sniper RR ≥ 1 tối đa 24 giờ',
}
REFERENCES = {
    'normal_power': 'https://www.itl.nist.gov/div898/handbook/prc/section2/prc222.htm',
    'multiplicity': 'https://www.itl.nist.gov/div898/handbook/prc/section4/prc473.htm',
}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')


def weekly_log_returns(curve, start, end):
    """Only complete Monday-to-Monday weeks; no synthetic partial week."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if start.tz is None or end.tz is None or end > LIMIT or start >= end:
        raise ValueError('UTC-aware historical interval through 2025 required')
    arr = np.asarray(curve, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 2 or not np.isfinite(arr).all():
        raise ValueError('Finite timestamp/NAV curve required')
    if (np.diff(arr[:, 0]) < 0).any() or (arr[:, 1] <= 0).any():
        raise ValueError('Ordered positive NAV required')
    if arr[-1, 0] > LIMIT.timestamp()*1000:
        raise ValueError('Post-2025 curve forbidden')
    grid = pd.date_range(start, end, freq='W-MON', normalize=True)
    stamps = grid.as_unit('ms').asi8
    if len(stamps) < 2 or arr[0, 0] > stamps[0] or arr[-1, 0] < stamps[-1]:
        raise ValueError('Insufficient covered complete weeks')
    idx = np.searchsorted(arr[:, 0], stamps, side='right')-1
    nav = arr[idx, 1]
    return np.diff(np.log(nav)), [t.isoformat() for t in grid]


def block_sigma(values, weeks):
    """SD per sqrt(week) implied by circular sums of length weeks."""
    a = np.asarray(values, dtype=float)
    if a.ndim != 1 or len(a) < 2 or not np.isfinite(a).all() or not 1 <= weeks <= len(a):
        raise ValueError('Finite weekly series and valid block length required')
    centered = a-a.mean()
    sums = np.zeros(len(a))
    for lag in range(weeks):
        sums += np.roll(centered, -lag)
    return math.sqrt(float(np.mean(sums*sums))/weeks)


def power_plan(sigma, annual_effect, horizon, claims=1, alpha=.05, target_power=.8):
    if sigma <= 0 or annual_effect <= 0 or horizon <= 0 or claims < 1:
        raise ValueError('Positive planning inputs required')
    delta = math.log1p(annual_effect)/52
    critical = NORM.inv_cdf(1-alpha/claims)
    required = math.ceil(((critical+NORM.inv_cdf(target_power))*sigma/delta)**2)
    power = NORM.cdf(math.sqrt(horizon)*delta/sigma-critical)
    return {'required_weeks_normal_approx': required, 'power_at_horizon': power}


def prior_check():
    cp = read(PRIOR/'CHECKPOINT.json')
    for name, value in cp['files'].items():
        assert sha(PRIOR/name) == value, name
    for name, value in cp['additional_sources'].items():
        assert sha(ROOT/name) == value, name
    return cp


def register():
    prior_check()
    if (ART/'PROTOCOL.json').exists():
        raise FileExistsError('Planning protocol already registered')
    z = read(PRIOR/'VERIFICATION.json')
    assert z['all_passed'] and not z['fresh_oos'] and z['post2025_observations'] == 0
    parent = Path(z['attempt_path'])/'execution/PROTOCOL.json'
    inputs = [PRIOR/'CHECKPOINT.json', PRIOR/'VERIFICATION.json', PRIOR/'MINI_ALPHA_REGISTRY.json',
              BASE/'research_v4_0_21/RESULTS.json', BASE/'research_v4_0_21/EXACT_MARK_DATA_REQUEST.json',
              BASE/'BACKTEST_COST_STANDARD.json', parent]
    save(ART/'PROTOCOL.json', {
        'registered_at_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'OOS feasibility and explicit completion review, not strategy optimization or a new OOS result.',
        'sources': {str(p): sha(p) for p in (SOURCE, TEST)},
        'inputs': {str(p): sha(p) for p in inputs},
        'policies': list(LABELS), 'scenarios': read(parent)['scenarios'],
        'windows': {'all_2020_2025': ['2020-01-01T00:00:00Z', '2026-01-01T00:00:00Z'],
                    'recent_2024_2025': ['2024-01-01T00:00:00Z', '2026-01-01T00:00:00Z']},
        'annual_effect_scenarios': [.05, .10, .15], 'horizon_weeks': [13, 26, 52, 104, 156],
        'block_weeks': [1, 4, 8], 'claim_counts': [1, 12], 'alpha': .05, 'target_power': .8,
        'method': 'Complete Monday weeks, log NAV returns. sigma=sqrt(mean(circular_block_sum(centered_returns)^2)/block_length). One-sided normal power with alpha/claim_count. No estimated historical mean used as a projected edge.',
        'planning_only': True, 'data_ceiling': '2025-12-31', 'post2025_observations': 0,
        'limitations': ['Stationarity, approximately normal sample means and stable variance are assumptions.',
                       'Blocks are a sensitivity grid, not validated future dependence lengths.',
                       'Estimated variance uncertainty and regime change are not included in the normal calculation.',
                       'The six-year curves have annual state resets and five-day entry embargo; operational differences may alter future variance.',
                       'Multiple-test adjustment does not repair historical adaptive reuse. These are not post-selection p-values.',
                       'No horizon or positive outcome automatically grants live trading sign-off.'],
        'references': REFERENCES, 'fresh_oos': False, 'goal_complete': False,
    })


def verify_protocol():
    p = read(ART/'PROTOCOL.json')
    for group in ('sources', 'inputs'):
        for path, digest in p[group].items():
            assert sha(path) == digest, path
    return p


def run():
    p = verify_protocol(); prior_check()
    if (ART/'RESULTS.json').exists():
        raise FileExistsError('Planning results already exist')
    v = read(PRIOR/'VERIFICATION.json'); folder = Path(v['attempt_path'])/'execution'
    old = read(BASE/'research_v4_0_21/RESULTS.json')
    data = []; source_files = {}; reconciled = 0
    for policy in p['policies']:
        for scenario in p['scenarios']:
            curve = []; capital = 100.
            for year in range(2020, 2026):
                receipt_path = folder/f'YEAR_{year}.json'
                assert sha(receipt_path) == v['year_receipts'][str(year)]['sha256']
                receipt = read(receipt_path)
                name = str(Path('nodes')/f'{year}_{policy}_{scenario}.json.gz')
                path = folder/name; assert sha(path) == receipt['node_files'][name]
                source_files[str(path)] = sha(path)
                with gzip.open(path, 'rt', encoding='utf8') as fh:
                    node = json.load(fh)
                assert not node['execution_issues']
                curve.extend((t, nav*capital/100) for t, nav in node['curve'])
                capital *= node['curve'][-1][1]/100
                reconciled += 1
            assert abs((capital-100)-old['fixed_policy_periods']['all_2020_2025'][policy][scenario]['return_pct']) < 1e-8
            for label, (start, end) in p['windows'].items():
                values, grid = weekly_log_returns(curve, start, end)
                rows = []
                for block in p['block_weeks']:
                    sigma = block_sigma(values, block)
                    for effect in p['annual_effect_scenarios']:
                        for claims in p['claim_counts']:
                            rows.append({'block_weeks': block, 'sigma_log_per_sqrt_week': sigma,
                                'assumed_annual_geometric_effect_pct': effect*100, 'claims': claims,
                                'required_weeks_normal_approx': power_plan(sigma, effect, 52, claims)['required_weeks_normal_approx'],
                                'power_by_horizon': {str(n): power_plan(sigma, effect, n, claims)['power_at_horizon'] for n in p['horizon_weeks']}})
                data.append({'policy': policy, 'scenario': scenario, 'window': label,
                    'complete_weeks': len(values), 'first_monday': grid[0], 'last_monday': grid[-1],
                    'weekly_log_returns': values.tolist(), 'planning': rows})
    results = {'protocol_sha256': sha(ART/'PROTOCOL.json'), 'source_nodes': source_files,
        'reconciled_nodes': reconciled, 'series': data, 'new_signal_parameters': 0,
        'fresh_oos': False, 'post2025_observations': 0, 'goal_complete': False, 'live_signoff': 'NOT_GRANTED'}
    save(ART/'RESULTS.json', results)
    print({'reconciled_nodes': reconciled, 'series': len(data), 'planning_rows': sum(len(a['planning']) for a in data)}, flush=True)


def draft(p):
    return {
        'status': 'DRAFT_NOT_ACTIVATED', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope_decision_required': 'Fresh prospective paper observations after freeze, or retrospective walk-forward through 2025 only.',
        'authorized_market_data_ceiling_for_backtest': '2025-12-31',
        'market_observations_after_2025_read': False, 'paper_started': False, 'orders_allowed': False,
        'strategy_family': p['policies'], 'source_checkpoint': {'path': str(PRIOR/'CHECKPOINT.json'), 'sha256': sha(PRIOR/'CHECKPOINT.json')},
        'scenarios': p['scenarios'], 'per_fill': True, 'bnb_discount': False,
        'allocation': 'Separate virtual NAV per policy and cost scenario; never sum twelve observer accounts into one portfolio.',
        'selection': 'No switching to the best observed strategy. Historical prior-years gate remains CASH. Observer hypotheses do not override that gate or authorize allocation.',
        'start_utc': None, 'end_utc': None, 'horizon_selection': 'Lock one fixed horizon before the first scored observation; the power table is illustrative, not an approved duration.',
        'warmup': 'Any post-2025 warmup, if later authorized, must be labelled unscored and excluded from OOS; start scoring only after freeze and readiness.',
        'endpoints': {'unit': 'Full calendar-week log NAV change including unrealized positions, fees, slippage and signed realized funding.',
                      'family': 'Six fixed policies times two cost scenarios = twelve predeclared claims. Alpha family 0.05; no additional result-selected endpoints.',
                      'statistics': 'One final assessment at the fixed horizon. Paired calendar blocks across accounts. Normal power calculations are planning only, not the final inferential procedure.',
                      'cost_interpretation': 'Report standard performance and stress degradation separately. The user required stress testing, not a universal rule that stress must always profit.',
                      'failures': 'Retain failed and inconclusive outcomes; no early success stopping or horizon extension because results are almost significant.'},
        'activation_prerequisites': ['Resolve user OOS scope.', 'Fix the start, duration, inferential method and economic decision criterion before collecting scored observations.',
            'Implement and verify fresh monthly PIT selection, current contract lifecycle capture and event-time data completeness; v425 only verified a cached historical schedule.',
            'Verify live quote/funding adapters, idempotent receipts, restart and missing-data handling with synthetic inputs; v425 is not an operational live feed certification.',
            'Archive exact input and source hashes; changes after activation create a separately labelled experiment.'],
        'data_quality': 'Missing data is an incident, never a zero return or silently dropped losing observation. Pause admissions, preserve open-state obligations, report the affected interval and mark conclusions inconclusive if required valuation/funding cannot be reconstructed.',
        'funding': 'Use realized signed rate and settlement mark on remaining quantity. Any substitute mark stays explicitly approximate and blocks exact-funding certification.',
        'acceptance': 'Positive statistical evidence alone does not certify execution capacity or grant live sign-off. No orders or automatic promotion.',
    }


def ranges(result, policy, scenario, effect=10.):
    rows = [a for s in result['series'] if s['policy'] == policy and s['scenario'] == scenario
            for a in s['planning'] if a['claims'] == 12 and a['assumed_annual_geometric_effect_pct'] == effect]
    return {'weeks_min': min(a['required_weeks_normal_approx'] for a in rows),
            'weeks_max': max(a['required_weeks_normal_approx'] for a in rows),
            'power52_min': min(a['power_by_horizon']['52'] for a in rows),
            'power52_max': max(a['power_by_horizon']['52'] for a in rows)}


def render(data):
    lines = ['# Kế hoạch xác nhận OOS cho Fibo Trend Short', '',
        '**Chưa có bằng chứng để duyệt chiến lược. Kế hoạch OOS chưa được kích hoạt.** '
        'Backtest tiếp tục giới hạn đến hết 2025. Vòng này chỉ dùng các đường NAV đã lưu để ước lượng quy mô quan sát cần thiết; không tối ưu thêm tín hiệu.', '',
        '## Quy mô mẫu theo giả định lợi thế', '',
        'Bảng dưới giả định lợi thế tăng trưởng ròng 10%/năm, mức phát hiện mục tiêu 80% và xét đồng thời 12 kết luận '
        '(6 cấu hình × 2 mức chi phí). Đây là giả định để lập kế hoạch, không phải dự báo lợi nhuận. '
        'Khoảng số liệu phản ánh hai cửa sổ lịch sử 2020–2025 và 2024–2025, cùng độ dài khối 1, 4 và 8 tuần.', '',
        '| Cấu hình | Tuần ước lượng ở bản chuẩn | Tuần ước lượng ở bản stress | Khả năng phát hiện sau 52 tuần ở bản chuẩn |',
        '|---|---:|---:|---:|']
    for pid, label in LABELS.items():
        a, b = data['planning_summary'][pid]['standard_vip6'], data['planning_summary'][pid]['stress_regular']
        lines.append(f"| {label} | {a['weeks_min']}–{a['weeks_max']} | {b['weeks_min']}–{b['weeks_max']} | {a['power52_min']*100:.1f}–{a['power52_max']*100:.1f}% |")
    lines += ['', 'Các con số dùng xấp xỉ chuẩn với phương sai suy ra từ khối lợi nhuận tuần lịch sử. '
        'Thay đổi chế độ thị trường, sai số ước lượng phương sai và phụ thuộc kéo dài hơn khối có thể làm chúng sai. '
        'Đường NAV lịch sử còn dùng quy ước đặt lại trạng thái mỗi năm. Không thể diễn giải số tuần này là thời gian chắc chắn chứng minh được alpha. '
        f"Công thức lập kế hoạch theo [NIST]({REFERENCES['normal_power']}); phân bổ sai số cho nhiều kết luận theo [Bonferroni]({REFERENCES['multiplicity']}).", '',
        'Bộ JSON giữ đầy đủ giả định lợi thế 5%, 10%, 15%/năm; các mốc 13, 26, 52, 104, 156 tuần; '
        'và trường hợp một hoặc 12 kết luận. Không chọn kết quả thuận lợi nhất để làm ngưỡng duyệt.', '',
        '## Những gì đã đạt và còn thiếu', '',
        f"Đã đối chiếu {data['reconciled_nodes']} đường NAV với hồ sơ v4.0.25, giữ đúng hai mức phí từng lần khớp. "
        'Bản chuẩn dùng phí taker 2,5 bps cộng trượt giá 10 bps; bản stress dùng 5 bps cộng 50 bps, không giảm phí BNB.', '',
        f"Nhật ký giữ nguyên {data['registry_entries']} mục nghiên cứu, {data['proven_alpha_entries']} mục được xác nhận là alpha. "
        'Các thành phần quản trị rủi ro và các phép kiểm tra âm vẫn được lưu để tái sử dụng.', '',
        f"Funding rate lịch sử đã có; {data['exact_mark_unique_events']:,} kỳ của {data['exact_mark_symbols']} mã "
        'còn cần giá mark thanh toán chính xác. Danh sách đầy đủ nằm trong EXACT_MARK_DATA_REQUEST.json của v4.0.21. '
        'Thay thế các giá xấp xỉ này chưa được chứng minh sẽ làm chiến lược có lợi thế.', '',
        '## Phương án OOS chờ quyết định phạm vi', '',
        'Dự thảo giữ nguyên sáu cấu hình và hai mức chi phí, mỗi cấu hình có tài khoản mô phỏng riêng. '
        'Phải chốt ngày bắt đầu, thời hạn và cách kết luận trước quan sát được chấm điểm; không chọn cấu hình thắng sau khi xem kết quả, '
        'không dừng sớm chỉ vì vừa có lãi. Cổng chọn chiến lược lịch sử vẫn là CASH.', '',
        'Luồng dữ liệu mới còn cần lịch chọn coin PIT cập nhật, danh tính hợp đồng, báo giá thực thi và funding đúng thời điểm. '
        'Bản v4.0.25 xác nhận phát lại lịch sử với lịch coin đã lưu, chưa chứng nhận các bộ phận trực tuyến này.', '',
        'Phạm vi OOS mới vẫn chờ lựa chọn của người dùng: quan sát paper phát sinh sau khi khóa mô hình, '
        'hoặc chỉ đánh giá walk-forward hồi cứu đến hết 2025. Lựa chọn thứ hai không tạo ra holdout chưa từng được xem. '
        'Chưa đọc dữ liệu thị trường sau 2025, chưa chạy paper trading và chưa đặt lệnh.', '']
    return '\n'.join(lines)


def publish():
    p = verify_protocol(); prior_check(); result = read(ART/'RESULTS.json')
    assert result['protocol_sha256'] == sha(ART/'PROTOCOL.json')
    for path, digest in result['source_nodes'].items():
        assert sha(path) == digest
    suites = list(ET.parse(ART/'TESTS.xml').getroot().iter('testsuite'))
    tests = {k: sum(int(s.get(k, 0)) for s in suites) for k in ('tests', 'errors', 'failures', 'skipped')}
    assert tests['tests'] >= 5 and tests['errors'] == tests['failures'] == tests['skipped'] == 0
    registry = read(PRIOR/'MINI_ALPHA_REGISTRY.json')
    request = read(BASE/'research_v4_0_21/EXACT_MARK_DATA_REQUEST.json')
    economic = read(BASE/'research_v4_0_21/RESULTS.json')
    records = [a['selected'] for a in economic['walk_forward_locks'].values()]
    assert records == ['CASH']*4
    data = {'reconciled_nodes': result['reconciled_nodes'], 'tests': tests,
        'planning_summary': {pid: {s: ranges(result, pid, s) for s in p['scenarios']} for pid in LABELS},
        'registry_entries': len(registry['entries']),
        'proven_alpha_entries': sum(bool(a['usable_as_proven_alpha']) for a in registry['entries']),
        'exact_mark_unique_events': request['unique_events'],
        'exact_mark_symbols': len({a['symbol'] for a in request['events']}),
        'results_sha256': sha(ART/'RESULTS.json'), 'fresh_oos': False, 'goal_complete': False,
        'requirements': {'pre2026_backtest': 'VERIFIED_FOR_REPORTED_RUNS',
            'dual_per_fill_costs': 'VERIFIED', 'funding': 'HISTORICAL_RATES_WITH_LABELLED_MARK_PROXIES',
            'mini_alpha_registry': 'PRESERVED_NONE_PROVEN', 'fresh_oos': 'MISSING_SCOPE_PENDING',
            'validated_trading_edge': 'NOT_ESTABLISHED', 'paper_operational_service': 'NOT_STARTED_NOT_CERTIFIED'},
        'live_signoff': 'NOT_GRANTED'}
    save(ART/'REPORT_DATA.json', data)
    save(ART/'OOS_DRAFT.json', draft(p))
    registry['oos_planning_v426'] = {'path': str(ART/'REPORT_DATA.json'), 'sha256': sha(ART/'REPORT_DATA.json'), 'new_alpha_entries': 0}
    save(ART/'MINI_ALPHA_REGISTRY.json', registry)
    assert registry['entries'] == read(PRIOR/'MINI_ALPHA_REGISTRY.json')['entries']
    (ART/'REPORT.md').write_text(render(data), encoding='utf8')
    assert (ART/'REPORT.md').read_text(encoding='utf8') == render(read(ART/'REPORT_DATA.json'))
    save(ART/'REPORT_CONSISTENCY.json', {'all_passed': True, 'report_sha256': sha(ART/'REPORT.md'), 'report_data_sha256': sha(ART/'REPORT_DATA.json')})
    save(ART/'PROGRESS.json', {'stage': 'oos_sample_feasibility_reviewed_draft_not_active',
        'next_action': 'Resolve the pending OOS scope before fresh market observations. Do not repeat historical parameter searches to relabel reused data as confirmation.',
        'goal_complete': False, 'live_signoff': 'NOT_GRANTED'})
    files = {str(a.relative_to(ART)): sha(a) for a in ART.rglob('*') if a.is_file() and a.name != 'CHECKPOINT.json'}
    save(ART/'CHECKPOINT.json', {'files': files, 'sources': p['sources'], 'previous_checkpoint_sha256': sha(PRIOR/'CHECKPOINT.json'), 'goal_complete': False})
    print({'protected_files': len(files), 'registry_entries': len(registry['entries']), 'proven_alpha_entries': data['proven_alpha_entries'], 'elite_planning': data['planning_summary']['elite_sniper_risk']}, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=['register', 'run', 'publish'])
    globals()[parser.parse_args().action]()
