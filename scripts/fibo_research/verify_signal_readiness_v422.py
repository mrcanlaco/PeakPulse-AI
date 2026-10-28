"""Historical closed-prefix parity; no future-market collection or paper launch."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import pickle
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import research_family_v421 as prior
import signal_snapshot_v422 as signal
import build_signal_snapshot_v422 as build
from universe_reaudit_v402_worker import collect_symbol_milestones_v402

r = prior.r
ROOT = prior.ROOT
OLD = prior.ART
ART = OLD.parent / 'research_v4_0_22'
END = r.utc('2026-01-01')
OUTCOME_FIELDS = {'sim_std', 'sim_m6', 'sim_std_0831', 'sim_m6_0831'}


def preserve_previous():
    checkpoint = r.read(OLD / 'CHECKPOINT.json')
    for name, digest in checkpoint['files'].items():
        assert r.sha(OLD / name) == digest, name
    for name, digest in checkpoint['additional_sources'].items():
        assert r.sha(ROOT / name) == digest, name
    return checkpoint


def selected_cases():
    """Sample on time/contract identity only, never on PnL or accepted trades."""
    manifest = r.read(OLD / 'PATH_MANIFEST.json')
    views = r.read(OLD / 'OBSERVED_VIEWS.json')
    rows = []
    for spec in manifest['symbols'].values():
        p = OLD / spec['paths']
        assert r.sha(p) == spec['paths_sha256']
        with gzip.open(p, 'rb') as f:
            pack = pickle.load(f)
        rows.extend({k: a for k, a in c.items() if k != 'paths'} for c in pack['full']
                    if prior.previous.annual_eligible(c))
    rows.sort(key=lambda c: (c['decision_ts'], c['symbol'], c['tf']))
    cases = {}
    def add(c, role, probe_hours=0):
        decision = pd.Timestamp(c['decision_ts'], unit='s', tz='UTC') + pd.Timedelta(hours=probe_hours)
        view = prior.phase_for(c, views[c['symbol']])
        assert decision + pd.Timedelta(hours=3) <= END
        assert decision + pd.Timedelta(hours=3) <= r.utc(view['last_open']) + pd.Timedelta(minutes=5)
        key = c['symbol'] + ':' + str(int(decision.timestamp()))
        case = cases.setdefault(key, {'id': key, 'symbol': c['symbol'], 'as_of': decision.isoformat(),
                'view': view, 'roles': [], 'historical_anchors': []})
        case['roles'].append(role)
        if not probe_hours and c not in case['historical_anchors']:
            case['historical_anchors'].append(c)
    for year in range(2020, 2026):
        yearly = [c for c in rows if pd.Timestamp(c['decision_ts'], unit='s').year == year]
        for tf in ('4h', '1d'):
            cell = [c for c in yearly if c['tf'] == tf]
            assert cell
            add(cell[0], f'{year}_{tf}_first')
            add(cell[-1], f'{year}_{tf}_last')
        add(yearly[0], f'{year}_fixed_offset_probe', probe_hours=37)
    for phase in ('old', 'relaunched'):
        cell = [c for c in rows if c.get('contract_episode_id') == 'BNXUSDT__' + phase]
        assert cell
        add(cell[0], 'BNX_' + phase)
    return list(cases.values()), views['BTCUSDT'][0]


def register():
    previous = preserve_previous()
    assert not (ART / 'PROTOCOL.json').exists(), 'Already registered'
    assert Path(signal.__file__).read_text(encoding='utf8') == build.render()
    cases, btc = selected_cases()
    sources = {str(ROOT / name): digest for name, digest in previous['additional_sources'].items()}
    for p in (Path(__file__), Path(signal.__file__), Path(build.__file__),
              ROOT / 'tests/unit/fibo_short/test_signal_snapshot_v422.py'):
        sources[str(p)] = r.sha(p)
    protocol = {'version': '4.0.22', 'registered_at_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Verify closed-bar signal extraction before prospective execution integration.',
        'previous_checkpoint_sha256': r.sha(OLD / 'CHECKPOINT.json'), 'sources': sources,
        'cases': cases, 'btc_view': btc, 'tests_sha256': r.sha(ART / 'TESTS.xml'),
        'sampling': 'First and last annual-eligible candidate per year/timeframe, first BNX candidate in each identity, and fixed +37h probes from first annual candidate. Never sample on PnL.',
        'comparisons': ['Closed-only snapshot at final H1 versus batch reference with three later hours.',
            'All non-outcome signal fields must match exactly; compare archived candidate anchors separately.',
            'Unmodified batch collector at final closed H1 emits no signal because it reserves two future hours.',
            'Wrapper must reject future candles and future BTC context, not silently use them.'],
        'scope': 'Selected historical timestamps only, not exhaustive replay, latency proof or OOS performance.',
        'parameter_changes': 0, 'new_strategy_variants': 0, 'post2025_market_data_permitted': False,
        'prospective_started': False, 'fresh_oos': False, 'goal_complete': False}
    r.save(ART / 'PROTOCOL.json', protocol)
    print({'registered_cases': len(cases), 'sources': len(sources)}, flush=True)


def verify_sources():
    p = r.read(ART / 'PROTOCOL.json')
    assert p['previous_checkpoint_sha256'] == r.sha(OLD / 'CHECKPOINT.json')
    for name, digest in p['sources'].items():
        assert r.sha(name) == digest, name
    assert p['tests_sha256'] == r.sha(ART / 'TESTS.xml')
    return p


def load_hours(view, end):
    assert end <= END
    assert r.sha(view['path']) == view['sha256']
    f = pd.read_parquet(view['path'], filters=[('open_time', '<', end)])
    assert len(f) and f.index.min() >= r.utc('2020-01-01') and f.index.max() < end <= END
    return r.h1_frame(f)


def btc_context(hourly):
    return {tf: r.calc_htf_features_no_bfill(r.resample_1h_to_htf(hourly, tf)) for tf in ('4h', '1d')}


def clean(rows):
    out = []
    for row in rows:
        a = {k: val for k, val in row.items() if k not in OUTCOME_FIELDS}
        a['decision_ts'] = a['decision_ts'].isoformat()
        out.append(a)
    return sorted(out, key=lambda a: (a['symbol'], a['tf'], a['decision_time']))


def compare_anchor(c, snapshots):
    a = next(s for s in snapshots if s['tf'] == c['tf'])
    assert a['symbol'] == c['symbol'] and a['wave_key'] == c['wave_key']
    assert a['eligible_milestones'] == c['milestones']
    assert int(pd.Timestamp(a['decision_time']).timestamp()) == c['decision_ts']
    assert np.allclose([a['entry_price'], a['sl_m6'], a['tp1'], a['tp2'], a['tp3'], a['full_conviction_score']],
                       [c['signal_entry'], c['stop'], *c['targets'], c['score']], atol=1e-12, rtol=0)


def run():
    p = verify_sources()
    fingerprint = r.sha(ART / 'PROTOCOL.json')
    done_path = ART / 'CASE_RESULTS.json'
    results = r.read(done_path) if done_path.exists() else {'protocol_sha256': fingerprint, 'cases': {}}
    assert results['protocol_sha256'] == fingerprint
    for case in p['cases']:
        if case['id'] in results['cases']:
            continue
        t = r.utc(case['as_of'])
        h = load_hours(case['view'], t + pd.Timedelta(hours=3))
        b = load_hours(p['btc_view'], t + pd.Timedelta(hours=3))
        closed_h = h.loc[h.index + pd.Timedelta(hours=1) <= t]
        closed_b = b.loc[b.index + pd.Timedelta(hours=1) <= t]
        context = btc_context(closed_b)
        current = signal.closed_signal_snapshots(case['symbol'], closed_h, context, as_of=t)
        args = {'entry_start_ts': t-pd.Timedelta(hours=1), 'entry_end_ts': t-pd.Timedelta(hours=1)}
        original = collect_symbol_milestones_v402(case['symbol'], h, btc_context(b), **args)['raw_candidates']
        assert clean(current) == clean(original), case['id']
        tail = collect_symbol_milestones_v402(case['symbol'], closed_h, context, **args)['raw_candidates']
        assert tail == [], 'Negative control: historical collector should skip its final two H1 rows'
        for c in case['historical_anchors']:
            compare_anchor(c, current)
        try:
            signal.closed_signal_snapshots(case['symbol'], h, context, as_of=t)
        except ValueError as err:
            assert 'future H1' in str(err)
        else:
            raise AssertionError('Future H1 was accepted')
        results['cases'][case['id']] = {'roles': case['roles'], 'as_of': t.isoformat(),
            'contract_phase': case['view']['phase'], 'signals': clean(current),
            'signals_count': len(current), 'anchors_checked': len(case['historical_anchors']),
            'batch_reference_equal': True, 'original_tail_signal_count': len(tail),
            'future_injection_rejected': True, 'closed_hours': len(closed_h),
            'max_h1_close_utc': (closed_h.index[-1]+pd.Timedelta(hours=1)).isoformat()}
        r.save(done_path, results)
        print(f"Signal parity {len(results['cases'])}/{len(p['cases'])}: {case['id']} ({len(current)} signals)", flush=True)
    suites = list(ET.parse(ART / 'TESTS.xml').getroot().iter('testsuite'))
    tests = {k: sum(int(a.get(k, 0)) for a in suites) for k in ('tests', 'errors', 'failures', 'skipped')}
    assert tests['tests'] == 6 and tests['errors'] == tests['failures'] == tests['skipped'] == 0
    all_cases = list(results['cases'].values())
    verification = {'all_passed': True, 'cases': len(all_cases),
        'positive_cases': sum(a['signals_count'] > 0 for a in all_cases),
        'zero_signal_cases': sum(a['signals_count'] == 0 for a in all_cases),
        'signals_compared': sum(a['signals_count'] for a in all_cases),
        'archived_candidate_anchors': sum(a['anchors_checked'] for a in all_cases),
        'by_year': dict(Counter(a['as_of'][:4] for a in all_cases)),
        'by_timeframe': dict(Counter(s['tf'] for a in all_cases for s in a['signals'])),
        'contract_phases': sorted({a['contract_phase'] for a in all_cases}),
        'future_injections_rejected': sum(a['future_injection_rejected'] for a in all_cases),
        'case_results_sha256': r.sha(done_path), 'protocol_sha256': fingerprint, 'tests': tests,
        'post2025_observations': 0, 'fresh_oos': False, 'prospective_started': False,
        'scope': p['scope'], 'goal_complete': False, 'live_signoff': 'NOT_GRANTED'}
    r.save(ART / 'VERIFICATION.json', verification)
    print(verification, flush=True)


def report_text(d):
    v = d['verification']
    return f'''# Chuẩn bị xác nhận OOS: tín hiệu chỉ dùng nến đã đóng

**Đã xác nhận phần phát hiện tín hiệu trên mẫu lịch sử; chưa khởi chạy paper trading và chưa duyệt chiến lược.**

Bộ thu thập backtest cũ dành hai dòng H1 cuối cho mô phỏng sau tín hiệu nên không thể dùng nguyên trạng để phát hiện tín hiệu tại nến vừa đóng. Thành phần mới giữ nguyên công thức và cấu hình, bỏ phần tính kết quả tương lai, và đánh giá ngay trên nến H1 cuối đã đóng. Giá trong bản ghi là giá tham chiếu tín hiệu; lệnh khớp sau 5 phút vẫn là một bước khác.

Đã đối chiếu {v['cases']} thời điểm từ 2020 đến 2025: {v['positive_cases']} thời điểm có tín hiệu, {v['zero_signal_cases']} thời điểm không có tín hiệu, tổng {v['signals_compared']} tín hiệu. Mọi trường tín hiệu khớp bộ thu thập lịch sử; {v['archived_candidate_anchors']} ứng viên đã lưu cũng khớp. Mẫu gồm H4, D1 và hai giai đoạn hợp đồng BNX. Chọn mẫu theo thời gian và danh tính hợp đồng, không theo lợi nhuận.

Đã từ chối {v['future_injections_rejected']} lần chèn nến tương lai trong kiểm định. Cả {v['tests']['tests']} kiểm thử đạt, gồm nến chưa đóng, ngữ cảnh BTC tương lai, thiếu nến và bảo toàn đầu vào. Phép kiểm tra dùng nguồn 5 phút đã chặn trước 2026. Đây là kiểm tra trên mẫu, chưa phải đối chiếu toàn bộ lịch sử hay kiểm chứng độ trễ vận hành.

## Phần còn thiếu để có OOS thực sự

- Dữ liệu 2020–2025 đã được xem qua nhiều vòng; việc tách tín hiệu không làm chúng trở thành holdout mới.
- Chưa khởi tạo thu thập mới hoặc dùng quan sát sau 2025. Phạm vi paper trading tương lai vẫn chờ lựa chọn của người dùng.
- Cần nối thành phần này với danh sách coin theo thời điểm, kiểm tra vòng đời hợp đồng, nhận giá khớp sau 5 phút, trạng thái danh mục liên tục và funding được quan sát tại thời điểm phát sinh. Việc đối chiếu tín hiệu chưa chứng minh các bước này đã hoạt động trực tuyến.
- Trước khi quan sát kết quả mới, phải khóa mô hình, nguồn dữ liệu, thời gian đánh giá và tiêu chí thống kê; mọi sửa luật sau đó tạo một phiên bản nghiên cứu mới.

Giữ hai kịch bản phí mỗi lần khớp: VIP6 2,5 bps + trượt giá 10 bps; Regular 5 bps + trượt giá 50 bps, kể cả thoát từng phần. Funding dùng tỷ lệ thực và lượng còn mở; thiếu giá thanh toán phải công bố. Không có kết quả lợi nhuận mới trong vòng này.

Nhật ký giữ nguyên {d['registry_entries']} mục nghiên cứu, chưa ghi nhận thêm alpha. V4.0.21 và toàn bộ kết quả âm được giữ nguyên. Kết quả đầy đủ nằm trong `VERIFICATION.json` và `CASE_RESULTS.json`.
'''


def publish():
    verify_sources()
    previous = preserve_previous()
    v = r.read(ART / 'VERIFICATION.json')
    assert v['all_passed'] and v['case_results_sha256'] == r.sha(ART / 'CASE_RESULTS.json')
    registry = r.read(OLD / 'MINI_ALPHA_REGISTRY.json')
    registry['signal_readiness_v422'] = {'path': str(ART / 'VERIFICATION.json'),
        'sha256': r.sha(ART / 'VERIFICATION.json'), 'new_alpha_entries': 0,
        'prospective_started': False, 'fresh_oos': False}
    r.save(ART / 'MINI_ALPHA_REGISTRY.json', registry)
    assert r.read(ART / 'MINI_ALPHA_REGISTRY.json')['entries'] == r.read(OLD / 'MINI_ALPHA_REGISTRY.json')['entries']
    d = {'verification': v, 'registry_entries': len(registry['entries'])}
    r.save(ART / 'REPORT_DATA.json', d)
    (ART / 'REPORT.md').write_text(report_text(d), encoding='utf8')
    assert (ART / 'REPORT.md').read_text(encoding='utf8') == report_text(r.read(ART / 'REPORT_DATA.json'))
    r.save(ART / 'REPORT_CONSISTENCY.json', {'all_passed': True,
        'report_sha256': r.sha(ART / 'REPORT.md'), 'data_sha256': r.sha(ART / 'REPORT_DATA.json'),
        'verification_sha256': r.sha(ART / 'VERIFICATION.json')})
    r.save(ART / 'PROGRESS.json', {'stage': 'sampled_closed_bar_signal_parity_verified',
        'next_action': 'Integrate a sequential paper execution component using only through-2025 replay for verification; prospective start and fresh-OOS scope remain undecided.',
        'goal_complete': False, 'live_signoff': 'NOT_GRANTED'})
    paths = sorted(p for p in ART.rglob('*') if p.is_file() and p.name != 'CHECKPOINT.json')
    r.save(ART / 'CHECKPOINT.json', {'files': {str(p.relative_to(ART)): r.sha(p) for p in paths},
        'additional_sources': {str(Path(p).relative_to(ROOT)): h for p, h in r.read(ART / 'PROTOCOL.json')['sources'].items()},
        'previous_files_preserved': len(previous['files']), 'goal_complete': False})
    print({'protected_files': len(paths), 'registry_entries': len(registry['entries'])}, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('register', 'run', 'publish'))
    globals()[parser.parse_args().command]()
