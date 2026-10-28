"""Publish the frozen continuous-portfolio comparison without promoting an alpha."""
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import research_v419 as v

r = v.r
ART = v.ART
LABELS = {
    'annual_reset_baseline': 'Tham chiếu đặt lại mỗi năm',
    'annual_eligible_continuous': 'Liên tục, danh sách lệnh cũ',
    'all_continuous': 'Liên tục, bỏ embargo giữa các năm',
}


def projection(result):
    keys = ('version', 'periods', 'paired_differences', 'carry',
            'accepted_year_end_extra', 'scenarios', 'post_2025_observations',
            'fresh_oos', 'goal_complete', 'live_signoff')
    out = {k: result[k] for k in keys}
    # The canonical calendar intervals are in periods. Retain the engine's legacy
    # weekly_ci only in the original result, rather than silently mixing methods.
    out['metrics'] = {arm: {scenario: {k: a for k, a in metric.items()
                                      if k not in ('curve_values', 'weekly_ci')}
                            for scenario, metric in node.items()}
                      for arm, node in result['metrics'].items()}
    return out


def admission_diagnostics(result):
    audit = {}
    for scenario in v.SCENARIOS:
        baseline = [p['id'] for year in range(2020, 2026)
                    for p in v.b.ledger(year, scenario)['ledger']]
        continuous = v.ledger('annual_eligible_continuous', scenario)['ledger']
        full = v.ledger('all_continuous', scenario)['ledger']
        old_ids = {p['id'] for p in continuous}
        full_ids = {p['id'] for p in full}
        assert old_ids == set(baseline) and len(old_ids) == len(baseline)
        assert full_ids - old_ids == set(result['accepted_year_end_extra'][scenario])
        assert not old_ids - full_ids
        carry = {}
        for year in range(2021, 2026):
            t = int(r.utc(f'{year}-01-01').timestamp() * 1000)
            carry[str(year)] = [p['id'] for p in full
                               if p['entry_ts_ms'] < t < p['exit_ts_ms']]
        audit[scenario] = {
            'annual_vs_same_candidates_ids_exact': True,
            'added_ids': sorted(full_ids - old_ids),
            'removed_ids': sorted(old_ids - full_ids),
            'positions_strictly_across_year_boundary': carry,
        }
    return audit


def render(d):
    result = d['results']
    check = d['verification']
    inputs = d['inputs']
    rows = [
        '# Danh mục liên tục 2020–2025 — v4.0.19', '',
        '**Chưa duyệt giao dịch thật; nghiên cứu lợi thế và OOS chưa hoàn tất.** '
        'Vòng này đã xác nhận hạch toán danh mục liên tục và ảnh hưởng của việc '
        'ngừng mở lệnh cuối mỗi năm. Đây là kiểm tra chính sách đã khóa, không có tham số tín hiệu mới.', '',
        'Chạy một danh mục từ 2020-01-01 đến trước 2026-01-01, giữ vốn, wave và cooldown '
        'qua các năm. Chỉ giữ embargo 5 ngày cuối năm 2025 để mọi đường thoát kết thúc '
        'trước 2026. Không dùng quan sát thị trường năm 2026.', '',
        '## Chi phí đã chốt', '',
        '| Kịch bản | Phí taker mỗi khớp | Trượt giá bất lợi mỗi khớp |',
        '|---|---:|---:|',
    ]
    for scenario, cost in result['scenarios'].items():
        label = 'Chuẩn VIP6' if scenario == 'standard_vip6' else 'Stress Regular'
        rows.append(f"| {label} | {cost['fee_bps']:g} bps | {cost['slippage_bps']:g} bps |")
    rows += ['', 'Đây là hai giả định phí cố định cho toàn bộ giai đoạn, không phải '
             'lịch sử cấp VIP của một tài khoản. Không giảm phí BNB. Phí tính trên '
             'notional thực khớp; trượt giá áp dụng vào giá mua/bán theo chiều bất lợi '
             'ở từng lần vào và thoát, kể cả chốt từng phần. Funding có dấu tính '
             'trên khối lượng còn mở tại từng kỳ; không thay funding thiếu bằng 0.', '',
             '## NAV sau phí, trượt giá và funding', '',
             '| Cách chạy | Kịch bản | 2020–2025 | MaxDD | 2024–2025 hồi cứu | MaxDD |',
             '|---|---|---:|---:|---:|---:|']
    for arm, name in LABELS.items():
        for scenario in result['scenarios']:
            full = result['periods']['all_2020_2025'][scenario][arm]
            recent = result['periods']['retrospective_oos_2024_2025'][scenario][arm]
            label = 'Chuẩn' if scenario == 'standard_vip6' else 'Stress'
            rows.append(f"| {name} | {label} | {full['return_pct']:+.2f}% | "
                        f"{full['max_dd_pct']:.2f}% | {recent['return_pct']:+.2f}% | {recent['max_dd_pct']:.2f}% |")
    rows += ['', 'NAV của giai đoạn 2024–2025 dùng vốn thực còn lại tại đầu giai đoạn; '
             'không đặt lại thành 100. MaxDD giữ cả các thay đổi NAV trong cùng timestamp. '
             'Mốc biên giai đoạn lấy NAV sau mọi sự kiện đúng timestamp đó.', '',
             '## Ảnh hưởng của đặt lại trạng thái và embargo', '',
             f"Đối chiếu nguyên vẹn {inputs['annual_candidates']:,} ứng viên cũ; "
             f"bổ sung {inputs['extra_paths_independently_recomputed']} ứng viên bị embargo cuối năm, "
             f"thành {inputs['all_candidates']:,} ứng viên. Tất cả ứng viên bổ sung thuộc cuối năm 2020. "
             'Đường giá thoát của từng ứng viên được tính lại độc lập trước khi chạy kinh tế.', '',
             'Giữ danh sách ứng viên cũ và chạy liên tục cho đúng cùng tập lệnh được nhận '
             'như bản đặt lại mỗi năm; chênh lệch NAV chỉ ở sai số số thực. Sau khi bỏ '
             'embargo giữa các năm, các lệnh cũ vẫn được giữ và có thêm:', '']
    for scenario, audit in d['admission_diagnostics'].items():
        label = 'Chuẩn' if scenario == 'standard_vip6' else 'Stress'
        full = result['periods']['all_2020_2025'][scenario]
        delta = full['all_continuous']['return_pct'] - full['annual_reset_baseline']['return_pct']
        ids = ', '.join(f'`{cid}`' for cid in audit['added_ids'])
        rows.append(f'- {label}: {ids}. Thay đổi lợi nhuận toàn kỳ {delta:+.4f} điểm phần trăm.')
    carried = sum(len(ids) for audit in d['admission_diagnostics'].values()
                  for ids in audit['positions_strictly_across_year_boundary'].values())
    rows += ['', f'Trong mẫu lệnh được nhận có {carried} lượt vị thế đi qua đúng giao thừa '
             '(đếm lặp giữa kịch bản). Kiểm thử mô phỏng riêng xác nhận giữ trạng thái '
             'wave và hạch toán funding khi vị thế đi qua năm mới. Kết quả thực nghiệm '
             'không chứng minh mọi tình huống chuyển năm của dữ liệu tương lai.', '',
             '## Độ bất định của bản liên tục đầy đủ', '',
             '| Giai đoạn | Kịch bản | Trung bình tuần | CI 95% trung bình tuần |',
             '|---|---|---:|---:|']
    for period, name in [('all_2020_2025', '2020–2025'),
                         ('retrospective_oos_2024_2025', '2024–2025')]:
        for scenario in result['scenarios']:
            a = result['periods'][period][scenario]['all_continuous']['calendar_weekly_ci95']
            label = 'Chuẩn' if scenario == 'standard_vip6' else 'Stress'
            rows.append(f"| {name} | {label} | {a['mean_weekly_pct']:+.4f}% | "
                        f"[{a['ci_pct'][0]:+.4f}%; {a['ci_pct'][1]:+.4f}%] |")
    rows += ['', 'Cả bốn khoảng tin cậy đều chứa 0. Dùng lịch thứ Hai chung, giữ tuần '
             'không có lệnh và các đoạn tuần ở biên; bootstrap vòng theo khối 4 tuần, '
             '10.000 mẫu, seed 412. JSON giữ đầy đủ cả 18 so sánh cặp với CI 97,5%. '
             'Các khoảng tin cậy chưa điều chỉnh toàn bộ số lần thử trong lịch sử nghiên cứu.', '',
             '## Kiểm chứng và chất lượng funding', '',
             f"Kiểm tra độc lập {check['nodes']} lượt danh mục, {check['scenario_trades']:,} "
             f"bản ghi giao dịch, {check['fills']:,} nhóm khớp, {check['funding_payments']:,} "
             f"khoản funding và {check['entry_cap_checks']:,} lần kiểm tra vốn/hạn mức. "
             f"Đã tái dựng {check['marked_subperiods_verified']} tổ hợp giai đoạn–danh mục và "
             f"{check['paired_comparisons_verified']} so sánh cặp. Số đếm có lặp giữa các kịch bản.", '',
             f"Có {check['tests']['tests']} kiểm thử đạt, 0 lỗi/thất bại/bỏ qua. "
             f"Giữ nguyên {check['previous_files_preserved']} tệp đã khóa của vòng trước cùng mã nguồn liên quan.", '',
             f"Dùng funding đã xác minh của {inputs['funding_symbols']} mã; "
             f"{inputs['funding_snapshot_events_verified']:,} bản ghi trùng chính xác bộ v4.0.15. "
             f"Đối chiếu {inputs['raw_responses_verified']:,} phản hồi API và "
             f"{inputs['archives_verified']} tệp lưu trữ nguồn; không cần tải thêm dữ liệu cho vòng này.", '',
             f"Giá trị mark lịch sử cũ còn thiếu được gắn nhãn giá OPEN thay thế: "
             f"{check['proxy_funding_payments']:,} khoản funding theo kịch bản; "
             f"{check['exact_mark_unique_events_needed']:,} cặp mã–kỳ riêng biệt cần mark thanh toán "
             'chính xác nằm trong `EXACT_MARK_DATA_REQUEST.json`. Funding rate là dữ liệu lịch sử; '
             'notional thanh toán ở các kỳ proxy vẫn là xấp xỉ. Chưa mua dữ liệu. '
             'Các nhóm khớp tại cùng nến có thể gộp nhiều lần thoát theo khối lượng; '
             'đây không phải log khớp thật của sàn.', '',
             '## Kết luận nghiên cứu', '',
             'Bỏ việc đặt lại năm và embargo giữa các năm không khắc phục kết quả stress âm '
             'toàn kỳ. Lợi nhuận dương của bản chuẩn và giai đoạn 2024–2025 là bằng chứng '
             'mô tả cần giữ lại, nhưng CI hiện tại chưa xác nhận lợi thế khác 0. '
             'Stress là kịch bản người dùng yêu cầu đánh giá; các điều kiện duyệt lợi thế '
             'là đánh giá nghiên cứu, không phải lời bảo đảm sinh lời.', '',
             '2020–2025 đã được xem qua nhiều vòng; 2024–2025 là kiểm tra thời gian hồi cứu, '
             'không thể gọi là holdout mới. Nến 5 phút chưa xác nhận độ sâu sổ lệnh, '
             'độ trễ hay khả năng khớp với quy mô vốn thật. Chưa có quyết định mở rộng '
             'ngoài trần dữ liệu 2025 và chưa bắt đầu paper trading dữ liệu tương lai.', '',
             f"Nhật ký có {d['registry_entries']} mục bằng chứng/giả thuyết, giữ cả kết quả âm. "
             'Mục mới về ranh giới năm không được gắn nhãn alpha đã chứng minh. '
             'Bước tiếp theo là tổng hợp bằng chứng, phân biệt các thành phần tái sử dụng được '
             'với những giả thuyết chưa được xác nhận, và chốt phạm vi xác nhận OOS. '
             'Không gửi kết luận OK để triển khai hoặc lưu wiki như một chiến lược đã được duyệt.']
    return '\n'.join(rows) + '\n'


def main():
    v.verify_sources()
    full = r.read(ART / 'RESULTS.json')
    check = r.read(ART / 'INDEPENDENT_VERIFICATION.json')
    assert check['all_passed'] and check['results_sha256'] == r.sha(ART / 'RESULTS.json')
    inputs = r.read(ART / 'INPUT_VERIFICATION.json')
    assert check['input_verification_sha256'] == r.sha(ART / 'INPUT_VERIFICATION.json')
    audit = admission_diagnostics(full)
    extra = r.read(ART / 'CANDIDATE_AUDIT.json')['extra']
    assert all(a['entry_utc'].startswith('2020-12-') for a in extra)
    for scenario in v.SCENARIOS:
        for period in full['periods'].values():
            a, b = period[scenario]['annual_reset_baseline'], period[scenario]['annual_eligible_continuous']
            assert np.allclose([a['return_pct'], a['max_dd_pct']],
                               [b['return_pct'], b['max_dd_pct']], atol=1e-8, rtol=0)
    r.save(ART / 'ADMISSION_DIAGNOSTICS.json', audit)
    registry = r.read(v.PRIOR / 'MINI_ALPHA_REGISTRY.json')
    old = list(registry['entries'])
    result = projection(full)
    registry['entries'].append({
        'id': 'MA419-C2', 'type': 'year_boundary_execution_diagnostic_not_alpha',
        'status': 'CONTINUOUS_STATE_VERIFIED_STRESS_EDGE_NOT_ESTABLISHED',
        'usable_as_proven_alpha': False, 'fresh_oos': False,
        'periods': result['periods'], 'admission_diagnostics': audit,
        'results_sha256': r.sha(ART / 'RESULTS.json'),
    })
    assert registry['entries'][:-1] == old
    registry.update(status='CONTINUOUS_PORTFOLIO_VERIFIED',
                    last_completed_stage='continuous_portfolio_year_boundary',
                    updated_at_utc=datetime.now(timezone.utc).isoformat(),
                    source_registry_sha256=r.sha(v.PRIOR / 'MINI_ALPHA_REGISTRY.json'),
                    parent_registry={'path': str(v.PRIOR / 'MINI_ALPHA_REGISTRY.json'),
                                     'sha256': r.sha(v.PRIOR / 'MINI_ALPHA_REGISTRY.json')},
                    current_results={'path': str(ART / 'RESULTS.json'), 'sha256': r.sha(ART / 'RESULTS.json')})
    registry['trial_accounting_v419'] = {'new_signal_parameters': 0,
        'continuous_arms': 2, 'cost_conditions': 2, 'fresh_oos': False,
        'qualification': 'Additional inspection of reused historical evidence, not fresh validation.'}
    r.save(ART / 'MINI_ALPHA_REGISTRY.json', registry)
    d = {'results': result, 'verification': check, 'inputs': inputs,
         'admission_diagnostics': audit, 'registry_entries': len(registry['entries']),
         'source_results_sha256': r.sha(ART / 'RESULTS.json')}
    r.save(ART / 'REPORT_DATA.json', d)
    (ART / 'REPORT.md').write_text(render(r.read(ART / 'REPORT_DATA.json')), encoding='utf8')
    assert (ART / 'REPORT.md').read_text(encoding='utf8') == render(r.read(ART / 'REPORT_DATA.json'))
    assert r.read(ART / 'REPORT_DATA.json')['results'] == projection(r.read(ART / 'RESULTS.json'))
    r.save(ART / 'REPORT_CONSISTENCY.json', {
        'all_passed': True, 'method': 'Exact verified JSON projection, deterministic rendering and UTF8 readback',
        'report_sha256': r.sha(ART / 'REPORT.md'), 'report_data_sha256': r.sha(ART / 'REPORT_DATA.json'),
        'results_sha256': r.sha(ART / 'RESULTS.json')})
    r.save(ART / 'GOAL_REQUIREMENTS_AUDIT.json', {
        'only_data_through2025': 'VERIFIED', 'per_fill_standard_and_stress': 'VERIFIED',
        'continuous_execution': 'VERIFIED_WITH_INDEPENDENT_CASH_CAP_RECONSTRUCTION',
        'historical_funding_rates': 'VERIFIED_SIGNED_RATES',
        'all_funding_marks_exact': False, 'exact_mark_unique_events_needed': check['exact_mark_unique_events_needed'],
        'positive_full_history_stress': 'NOT_ESTABLISHED',
        'fresh_temporal_oos': 'NOT_ESTABLISHED_SCOPE_QUESTION_PENDING',
        'mini_alpha_log_entries': len(registry['entries']),
        'goal_complete': False, 'live_signoff': 'NOT_GRANTED'})
    r.save(ART / 'PROGRESS.json', {
        'stage': 'continuous_portfolio_year_boundary_verified',
        'next_action': 'Consolidate the evidence and reusable components without another adaptive parameter search; retain the pending OOS-scope question and data ceiling.',
        'goal_complete': False, 'live_signoff': 'NOT_GRANTED'})
    prior = r.read(v.PRIOR / 'CHECKPOINT.json')
    for path, h in prior['files'].items():
        assert r.sha(v.PRIOR / path) == h, path
    for path, h in prior['additional_sources'].items():
        assert r.sha(v.ROOT / path) == h, path
    paths = sorted(p for p in ART.rglob('*') if p.is_file() and p.name != 'CHECKPOINT.json')
    sources = r.read(ART / 'SOURCE_MANIFEST.json')['sources']
    sources[str(Path(__file__))] = r.sha(__file__)
    r.save(ART / 'CHECKPOINT.json', {
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'files': {str(p.relative_to(ART)): r.sha(p) for p in paths}, 'file_count': len(paths),
        'additional_sources': {str(Path(p).relative_to(v.ROOT)): h for p, h in sources.items()},
        'previous_files_preserved': len(prior['files']), 'goal_complete': False, 'live_signoff': 'NOT_GRANTED'})
    for path, h in r.read(ART / 'CHECKPOINT.json')['files'].items():
        assert r.sha(ART / path) == h, path
    print({'registry_entries': len(registry['entries']), 'protected_files': len(paths),
           'admission_diagnostics': audit}, flush=True)


if __name__ == '__main__':
    main()
