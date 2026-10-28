"""Resolve early-episode readiness using causal per-decision history guards."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib
from pathlib import Path
import xml.etree.ElementTree as ET
import pandas as pd
import verify_signal_readiness_v422 as old

r = old.r
ROOT = old.ROOT
ART = old.ART.parent / 'research_v4_0_23'
TARGET = ROOT / 'scripts/fibo_research/signal_snapshot_v423.py'


def generated_source():
    s = (ROOT / 'scripts/fibo_research/signal_snapshot_v422.py').read_text(encoding='utf8')
    replacements = {
        '    if len(df_1h) < 100:': '    # The first eligible decision index is 24; future file length is irrelevant.\n    if len(df_1h) < 25:',
        '        if len(htf_df) < 30:': '        # Match the existing per-decision htf_ptr >= 10 condition.\n        if len(htf_df) < 10:',
        '    if not hourly.index[-24:].equals(expected):': '    if not hourly.index[-24:].as_unit("ns").equals(expected.as_unit("ns")):',
    }
    for before, after in replacements.items():
        assert s.count(before) == 1
        s = s.replace(before, after, 1)
    return s.replace('Signal equations/configuration are extracted from the frozen v402 batch',
        'Per-decision history checks replace whole-file length checks.\nSignal equations/configuration are extracted from the frozen v402 batch', 1)


def generate():
    assert not TARGET.exists(), 'Do not overwrite generated source'
    TARGET.write_text(generated_source(), encoding='utf8')
    print(TARGET, flush=True)


def preserve():
    old.preserve_previous()
    p = r.read(old.ART / 'CHECKPOINT_FAILED.json')
    for name, digest in p['files'].items():
        assert r.sha(old.ART / name) == digest
    for name, digest in p['additional_sources'].items():
        assert r.sha(ROOT / name) == digest
    return p


def register():
    prior = preserve()
    assert not (ART / 'PROTOCOL.json').exists()
    assert TARGET.read_text(encoding='utf8') == generated_source()
    p = r.read(old.ART / 'PROTOCOL.json')
    sources = {str(ROOT / k): h for k, h in prior['additional_sources'].items()}
    for path in (TARGET, Path(__file__), ROOT / 'tests/unit/fibo_short/test_signal_snapshot_v423.py'):
        sources[str(path)] = r.sha(path)
    r.save(ART / 'PROTOCOL.json', {'version': '4.0.23', 'registered_at_utc': datetime.now(timezone.utc).isoformat(),
        'parent_failed_checkpoint_sha256': r.sha(old.ART / 'CHECKPOINT_FAILED.json'),
        'sources': sources, 'cases': p['cases'], 'btc_view': p['btc_view'],
        'tests_sha256': r.sha(ART / 'TESTS.xml'),
        'changes': ['Use >=25 H1 and >=10 HTF already implied by the existing decision loop, instead of checking future whole-file length >=100/>=30.',
            'Compare time grids by exact instants normalized to ns.', 'Keep every signal formula, parameter and original case unchanged.'],
        'reference': 'Original batch collector on the complete frozen contract view through2025. Future values appear only in the historical comparator, never the closed-only signal component.',
        'non_claims': ['Sampled signal parity is not exhaustive candidate or portfolio parity.',
            'No new NAV result, no prospective data, no fresh OOS, no live approval.'],
        'new_strategy_variants': 0, 'signal_parameter_changes': 0,
        'post2025_observations_permitted': False, 'goal_complete': False})
    print({'registered_cases': len(p['cases']), 'sources': len(sources)}, flush=True)


def verify_sources():
    p = r.read(ART / 'PROTOCOL.json')
    assert p['parent_failed_checkpoint_sha256'] == r.sha(old.ART / 'CHECKPOINT_FAILED.json')
    for path, digest in p['sources'].items():
        assert r.sha(path) == digest, path
    assert p['tests_sha256'] == r.sha(ART / 'TESTS.xml')
    return p


def run():
    p = verify_sources()
    signal = importlib.import_module('signal_snapshot_v423')
    fingerprint = r.sha(ART / 'PROTOCOL.json')
    output = ART / 'CASE_RESULTS.json'
    data = r.read(output) if output.exists() else {'protocol_sha256': fingerprint, 'cases': {}}
    assert data['protocol_sha256'] == fingerprint
    btc = old.load_hours(p['btc_view'], old.END)
    full_btc = old.btc_context(btc)
    for case in p['cases']:
        if case['id'] in data['cases']:
            continue
        t = r.utc(case['as_of'])
        full = old.load_hours(case['view'], old.END)
        closed = full.loc[full.index+pd.Timedelta(hours=1) <= t]
        closed_btc = btc.loc[btc.index+pd.Timedelta(hours=1) <= t]
        context = old.btc_context(closed_btc)
        current = signal.closed_signal_snapshots(case['symbol'], closed, context, as_of=t)
        original = old.collect_symbol_milestones_v402(case['symbol'], full, full_btc,
            entry_start_ts=t-pd.Timedelta(hours=1), entry_end_ts=t-pd.Timedelta(hours=1))['raw_candidates']
        assert old.clean(current) == old.clean(original), case['id']
        for anchor in case['historical_anchors']:
            old.compare_anchor(anchor, current)
        try:
            signal.closed_signal_snapshots(case['symbol'], full, context, as_of=t)
        except ValueError as error:
            assert 'future H1' in str(error)
        else:
            raise AssertionError('Future market data accepted')
        data['cases'][case['id']] = {'as_of': t.isoformat(), 'roles': case['roles'], 'symbol': case['symbol'],
            'contract_phase': case['view']['phase'], 'signals': old.clean(current),
            'signals_count': len(current), 'anchors_checked': len(case['historical_anchors']),
            'closed_h1': len(closed), 'closed_htf': {tf: len(r.resample_1h_to_htf(closed, tf)) for tf in ('4h', '1d')},
            'reference_equal': True, 'future_injection_rejected': True,
            'max_h1_close_utc': (closed.index[-1]+pd.Timedelta(hours=1)).isoformat()}
        r.save(output, data)
        print(f"Causal signal parity {len(data['cases'])}/{len(p['cases'])}: {case['id']} ({len(current)} signals)", flush=True)
    suites = list(ET.parse(ART / 'TESTS.xml').getroot().iter('testsuite'))
    tests = {k: sum(int(a.get(k,0)) for a in suites) for k in ('tests','errors','failures','skipped')}
    assert tests['tests'] >= 15 and tests['errors'] == tests['failures'] == tests['skipped'] == 0
    rows = list(data['cases'].values())
    result = {'all_passed': True, 'cases': len(rows), 'positive_cases': sum(a['signals_count'] > 0 for a in rows),
        'zero_signal_cases': sum(a['signals_count'] == 0 for a in rows), 'signals_compared': sum(a['signals_count'] for a in rows),
        'archived_candidate_anchors': sum(a['anchors_checked'] for a in rows),
        'by_year': dict(Counter(a['as_of'][:4] for a in rows)),
        'by_timeframe': dict(Counter(s['tf'] for a in rows for s in a['signals'])),
        'early_episode_case': data['cases']['BNXUSDT:1677297600'],
        'tests': tests, 'protocol_sha256': fingerprint, 'case_results_sha256': r.sha(output),
        'post2025_observations': 0, 'fresh_oos': False, 'prospective_started': False,
        'goal_complete': False, 'live_signoff': 'NOT_GRANTED'}
    r.save(ART / 'VERIFICATION.json', result)
    print({k: x for k,x in result.items() if k != 'early_episode_case'}, flush=True)


def render(d):
    v = d['verification']
    return f'''# Tín hiệu theo thời gian thực: xác nhận trên dữ liệu đóng nến

**Phần phát hiện tín hiệu đã khớp mẫu lịch sử; chiến lược chưa được duyệt và chưa có OOS mới.**

Đã tách phát hiện tín hiệu khỏi mô phỏng kết quả tương lai. Bộ phát hiện chỉ nhận nến H1 đã đóng cùng ngữ cảnh BTC có sẵn tại thời điểm quyết định. Giá tín hiệu vẫn là giá tham chiếu; đây chưa phải giá khớp lệnh sau 5 phút.

## Hai lỗi được phát hiện và sửa

1. Độ phân giải thời gian ns/us làm phép so sánh chỉ mục chặn tín hiệu dù các thời điểm bằng nhau. Đã chuẩn hóa so sánh về ns, không làm tròn mất dữ liệu lệch lưới.
2. Kiểm tra độ dài cả tệp trong bộ backtest không phù hợp với lịch sử có sẵn khi chạy trực tuyến. Tại BNX ngày 25/02/2023 04:00 UTC, chỉ có 61 H1 và 15 H4; bộ backtest đầy đủ vẫn phát hiện tín hiệu do nhìn thấy độ dài tệp tương lai. Bản mới dùng mức lịch sử đã có trong vòng quyết định cũ: chỉ số H1 từ 24 và ít nhất 10 HTF đã đóng. Các công thức, ngưỡng, điểm số và giá mục tiêu giữ nguyên.

Vòng v4.0.22 đã dừng ở lỗi BNX này. Bằng chứng và các nguồn cũ được giữ nguyên; không bỏ trường hợp thất bại khỏi mẫu.

## Kết quả xác nhận

- {v['cases']} thời điểm thuộc 2020–2025: {v['positive_cases']} có tín hiệu, {v['zero_signal_cases']} không có tín hiệu; tổng {v['signals_compared']} tín hiệu khớp mọi trường với bộ backtest đầy đủ.
- {v['archived_candidate_anchors']} ứng viên đã lưu khớp, gồm cả BNX trước và sau mở lại. Mẫu chọn theo thời gian/danh tính hợp đồng, không theo lợi nhuận.
- {v['cases']} lần chèn dữ liệu tương lai bị từ chối; {v['tests']['tests']} kiểm thử đạt.
- Không dùng quan sát sau 2025, không tính lại NAV và không tạo biến thể chiến lược mới. Đây là kiểm chứng trên mẫu, chưa phải đối chiếu toàn bộ lịch sử hoặc danh mục.

Điểm gọi đã kiểm chứng: `signal_snapshot_v423.closed_signal_snapshots`. Không dùng wrapper v4.0.22 làm thành phần trực tuyến.

## Bước còn lại

Cần nối tín hiệu này với chọn coin theo thời điểm, vòng đời hợp đồng, nhận giá khớp, trạng thái danh mục liên tục và funding theo sự kiện. Sẽ kiểm chứng luồng xử lý tuần tự bằng dữ liệu đến 2025 trước. Phạm vi paper trading bằng quan sát phát sinh mới vẫn chờ lựa chọn của người dùng; chưa khởi chạy thu thập mới.

Hai kịch bản phí mỗi lần khớp giữ nguyên: VIP6 2,5 bps + trượt giá 10 bps; Regular 5 bps + trượt giá 50 bps, kể cả thoát từng phần. Funding dùng tỷ lệ lịch sử thực và phải công bố giá thanh toán thay thế nếu có.

Nhật ký giữ {d['registry_entries']} mục nghiên cứu; chưa ghi nhận thêm alpha. Sửa lỗi vận hành không chứng minh lợi thế kinh tế và không biến dữ liệu 2020–2025 đã xem thành holdout mới.
'''


def publish():
    p = verify_sources()
    previous = preserve()
    result = r.read(ART / 'VERIFICATION.json')
    assert result['all_passed'] and result['case_results_sha256'] == r.sha(ART / 'CASE_RESULTS.json')
    registry = r.read(old.OLD / 'MINI_ALPHA_REGISTRY.json')
    registry['signal_readiness_v423'] = {'path': str(ART / 'VERIFICATION.json'),
        'sha256': r.sha(ART / 'VERIFICATION.json'), 'new_alpha_entries': 0,
        'scope': '32 historical timestamps, not exhaustive portfolio parity or fresh OOS'}
    r.save(ART / 'MINI_ALPHA_REGISTRY.json', registry)
    assert registry['entries'] == r.read(old.OLD / 'MINI_ALPHA_REGISTRY.json')['entries']
    data = {'verification': result, 'registry_entries': len(registry['entries'])}
    r.save(ART / 'REPORT_DATA.json', data)
    (ART / 'REPORT.md').write_text(render(data), encoding='utf8')
    assert (ART / 'REPORT.md').read_text(encoding='utf8') == render(r.read(ART / 'REPORT_DATA.json'))
    r.save(ART / 'REPORT_CONSISTENCY.json', {'all_passed': True,
        'report_sha256': r.sha(ART / 'REPORT.md'), 'data_sha256': r.sha(ART / 'REPORT_DATA.json'),
        'verification_sha256': r.sha(ART / 'VERIFICATION.json')})
    r.save(ART / 'PROGRESS.json', {'stage': 'closed_signal_sample_parity_verified_with_early_episode_fix',
        'next_action': 'Build and replay a sequential execution state machine without future path inputs, against frozen through2025 ledgers. Do not start prospective collection before OOS scope is resolved.',
        'goal_complete': False, 'live_signoff': 'NOT_GRANTED'})
    paths = sorted(a for a in ART.rglob('*') if a.is_file() and a.name != 'CHECKPOINT.json')
    r.save(ART / 'CHECKPOINT.json', {'files': {str(a.relative_to(ART)): r.sha(a) for a in paths},
        'additional_sources': {str(Path(a).relative_to(ROOT)): h for a,h in p['sources'].items()},
        'previous_failed_stage_files_preserved': len(previous['files']), 'goal_complete': False})
    print({'protected_files': len(paths), 'registry_entries': len(registry['entries'])}, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=('generate','register','run','publish'))
    globals()[p.parse_args().command]()
