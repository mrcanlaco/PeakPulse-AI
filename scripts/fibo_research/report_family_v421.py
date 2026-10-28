"""Publish every fixed policy, chronological choices and unresolved qualifications."""
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET
import family_reconciliation_adapter_v421 as adapter

e = adapter.e
v = e.v
r = v.r
ART = v.ART
NAMES = {'reference_m6_fixed': 'M6 khối lượng cố định', 'm6_risk': 'M6 khối lượng theo stop',
         'elite_sniper_risk': 'Elite + Sniper', 'sniper_risk': 'Sniper',
         'sniper_horizon24': 'Sniper tối đa 24 giờ', 'sniper_rr1_horizon24': 'Sniper RR ≥ 1 tối đa 24 giờ'}


def render(d):
    result = d['results']
    check = d['verification']
    inputs = d['inputs']
    lines = ['# Tái kiểm tra sáu cấu hình Fibo Trend Short trên vũ trụ đã sửa', '',
             '**Chưa cấp duyệt giao dịch thật.** Vòng này giữ nguyên sáu cấu hình đã có, '
             'chạy trên danh sách coin theo thời điểm và vòng đời hợp đồng đã sửa, '
             'không dò thêm ngưỡng tín hiệu. Chỉ dùng dữ liệu thị trường đến hết 2025.', '',
             'Bản chuẩn: taker VIP6 2,5 bps và trượt giá 10 bps. Bản stress: taker Regular '
             '5 bps và trượt giá 50 bps. Tất cả tính mỗi lần khớp, kể cả thoát từng phần, '
             'không giảm phí BNB; funding lịch sử có dấu tính theo lượng còn mở.', '',
             'Biểu phí VIP6/Regular được dùng làm hai mức giả định cố định để so sánh toàn kỳ. '
             'Đây không phải bản phục dựng biểu phí hay cấp VIP thực tế của tài khoản ở từng năm lịch sử.', '',
             '## NAV toàn kỳ 2020–2025', '',
             '| Cấu hình | Chuẩn | MaxDD | Số lệnh | Stress | MaxDD | Số lệnh |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for pid, name in NAMES.items():
        a = result['fixed_policy_periods']['all_2020_2025'][pid]
        s, t = a['standard_vip6'], a['stress_regular']
        lines.append(f"| {name} | {s['return_pct']:+.2f}% | {s['max_dd_pct']:.2f}% | {s['trades']} | "
                     f"{t['return_pct']:+.2f}% | {t['max_dd_pct']:.2f}% | {t['trades']} |")
    lines += ['', 'Mỗi năm đặt lại trạng thái và ngừng mở lệnh trong 5 ngày cuối năm, '
              'sau đó nối NAV theo vốn cuối năm trước. Quy ước này giữ nguyên để đối chiếu '
              'họ cấu hình cũ. Phép kiểm tra danh mục liên tục riêng đã được lưu ở v4.0.19. '
              'Các số là lợi nhuận trên NAV sau chi phí, không phải tổng lợi nhuận lệnh.', '',
              'Cả sáu cấu hình đều âm ở bản stress toàn kỳ. Không có cấu hình nào có cận dưới '
              'CI 95% của lợi nhuận tuần toàn kỳ lớn hơn 0 ở bản chuẩn. Kết luận này không '
              'đồng nghĩa đã chứng minh lợi thế bằng 0; bằng chứng hiện có chưa đủ để xác nhận lợi thế.', '',
              '## Giai đoạn 2024–2025 hồi cứu', '',
              '| Cấu hình | Chuẩn | CI 95% trung bình tuần chuẩn | Stress | CI 95% trung bình tuần stress |',
              '|---|---:|---:|---:|---:|']
    for pid, name in NAMES.items():
        a = result['fixed_policy_periods']['retrospective_2024_2025'][pid]
        s, t = a['standard_vip6'], a['stress_regular']
        c, z = s['calendar_weekly_ci95']['ci_pct'], t['calendar_weekly_ci95']['ci_pct']
        lines.append(f"| {name} | {s['return_pct']:+.2f}% | [{c[0]:+.4f}%; {c[1]:+.4f}%] | "
                     f"{t['return_pct']:+.2f}% | [{z[0]:+.4f}%; {z[1]:+.4f}%] |")
    lines += ['', 'Bootstrap vòng theo khối 4 tuần, 10.000 mẫu, seed 412; lịch thứ Hai chung '
              'giữ cả tuần không giao dịch và các đoạn tuần ở biên. Các CI chưa điều chỉnh '
              'toàn bộ số lần thử. Dữ liệu 2024–2025 đã được xem trong lịch sử nghiên cứu; '
              'một CI dương trong bảng không tự trở thành bằng chứng OOS mới.', '',
              '## Chọn cấu hình chỉ từ những năm trước', '',
              '| Năm kiểm tra | Lựa chọn đã khóa |', '|---|---|']
    for year, lock in result['walk_forward_locks'].items():
        lines.append(f"| {year} | {NAMES.get(lock['selected'], lock['selected'])} |")
    lines += ['', 'Cổng nghiên cứu giữ nguyên: ít nhất hai năm và 60 lệnh trước đó, mọi năm '
              'trước dương ở bản chuẩn, tổng stress không âm, MaxDD từng năm không quá 15%, '
              'không thiếu nến thực thi. Lỗi thực thi được nhận trong tập huấn luyện cũng '
              'chặn xét duyệt. Không dùng chất lượng hoặc kết quả của năm kiểm tra để sửa '
              'ngược quyết định. CASH được mô hình hóa không lãi tiền mặt, không giao dịch và không phí.', '',
              '| Chuỗi chọn 2022–2025 | NAV | MaxDD | Số lệnh |', '|---|---:|---:|---:|']
    for scenario in v.SCENARIOS:
        a = result['walk_forward_oos'][scenario]['2022_2025']
        lines.append(f"| {scenario} | {a['return_pct']:+.2f}% | {a['max_dd_pct']:.2f}% | {a['trades']} |")
    lines += ['', 'CASH không chứng minh alpha. Cổng này là quy tắc nghiên cứu đã đăng ký, '
              'không có nghĩa mọi chiến lược có một năm lỗ đều vô giá trị. Kết quả hồi cứu '
              'của một họ cấu hình đã phát triển trên dữ liệu cũ không thay thế quan sát OOS mới.', '',
              '## Chất lượng thực thi và funding', '',
              f"Đã tính lại độc lập {inputs['paths']['full_paths_independently_recomputed']:,} đường thoát nguyên bản "
              f"và {inputs['paths']['h24_paths_independently_recomputed']:,} đường thoát 24 giờ. "
              f"Có {inputs['paths']['unresolved_execution_issues']} đường thoát còn gắn lỗi chất lượng đầu vào; "
              f"{check['accepted_execution_issue_records']} lượt lệnh được nhận trong các kịch bản dính lỗi đó. "
              'Ứng viên được giữ nguyên, không loại theo thông tin tương lai. Nến không có '
              'giao dịch không đủ để xác nhận giá khớp giả định; cần dữ liệu báo giá/khớp chi tiết nếu lệnh đó được sử dụng.', '',
              f"Funding đã kiểm chứng cho {inputs['funding']['segments']} giai đoạn hợp đồng của "
              f"{inputs['funding']['symbols']} mã: {inputs['funding']['unique_merged_events']:,} sự kiện, "
              f"{inputs['funding']['unique_raw_response_paths']:,} phản hồi nguồn và "
              f"{inputs['funding']['archives_verified']} tệp lưu trữ. Tải bổ sung 30 giai đoạn; "
              'BNX trước và sau tái mở được kiểm tra riêng. Mọi khoảng giữ lệnh đều có funding '
              'liên tục; khoảng nghỉ giữa hợp đồng không được điền funding 0.', '',
              f"Trong các sổ lệnh có {check['proxy_funding_payments']:,} khoản funding theo kịch bản "
              f"dùng mark OPEN thay thế; {check['exact_mark_unique_events_needed']:,} cặp mã–kỳ riêng biệt "
              'cần mark thanh toán chính xác được lưu trong `EXACT_MARK_DATA_REQUEST.json`. '
              'Funding rate là lịch sử thực; notional ở các kỳ proxy vẫn là xấp xỉ. Chưa mua dữ liệu.', '',
              '## Kiểm chứng và kết luận', '',
              f"Đã kiểm tra độc lập {check['nodes']} tổ hợp, {check['scenario_trades']:,} bản ghi giao dịch, "
              f"{check['fills']:,} nhóm khớp và {check['funding_payments']:,} khoản funding. "
              f"Cả {check['exact_v415_nodes']} tổ hợp Elite + Sniper khớp nguyên vẹn sổ lệnh và "
              'đường NAV v4.0.15. Bản sửa kiểm định chỉ chuẩn hóa kiểu chứa đường NAV giữa '
              'bộ nhớ và JSON; không thay bất kỳ giá trị hay luật giao dịch nào.', '',
              f"Có {d['tests_total']} kiểm thử đạt cho đầu vào, chọn chiến lược và lỗi so sánh JSON. "
              f"Đã tái dựng {check['periods_verified']} tổ hợp giai đoạn và {check['selection_locks']} "
              'quyết định chọn theo thời gian. Báo cáo được kết xuất từ JSON đã kiểm chứng.', '',
              f"Nhật ký có {d['registry_entries']} mục, gồm phép tái kiểm tra họ cấu hình này; "
              'không nâng mục nào thành alpha đã chứng minh. Toàn bộ cấu hình và kết quả âm '
              'được giữ lại. Chưa hoàn tất mục tiêu chiến lược có OOS được xác nhận và chưa '
              'có kết luận OK để triển khai hoặc cập nhật wiki như chiến lược đã được duyệt.']
    return '\n'.join(lines) + '\n'


def main():
    adapter.verify()
    result = r.read(ART / 'RESULTS.json')
    check = r.read(ART / 'INDEPENDENT_VERIFICATION.json')
    completion = r.read(ART / 'RECONCILIATION_ADAPTER_COMPLETION.json')
    assert check['all_passed'] and completion['all_passed']
    assert check['results_sha256'] == completion['results_sha256'] == r.sha(ART / 'RESULTS.json')
    assert completion['adapter_protocol_sha256'] == r.sha(ART / 'RECONCILIATION_ADAPTER_PROTOCOL.json')
    inputs = r.read(ART / 'INPUT_VERIFICATION.json')
    suites = list(ET.parse(ART / 'ADAPTER_TESTS.xml').getroot().iter('testsuite'))
    assert sum(int(a.get('tests',0)) for a in suites) == 1
    assert all(int(a.get(k,0)) == 0 for a in suites for k in ('errors','failures','skipped'))
    registry = r.read(v.PRIOR / 'MINI_ALPHA_REGISTRY.json')
    prior_entries = list(registry['entries'])
    entry = {'id': 'MA421-U3', 'type': 'corrected_universe_fixed_family_replay',
             'hypothesis_vi': 'Tái kiểm tra nguyên họ sáu cấu hình trên vũ trụ và vòng đời hợp đồng đã sửa.',
             'status': 'FIXED_FAMILY_REPLAY_VERIFIED_NOT_PROVEN_ALPHA', 'usable_as_proven_alpha': False,
             'fresh_oos': False, 'results_sha256': r.sha(ART / 'RESULTS.json'),
             'fixed_policy_periods': result['fixed_policy_periods'],
             'walk_forward_choices': {y: a['selected'] for y,a in result['walk_forward_locks'].items()}}
    registry['entries'].append(entry)
    assert registry['entries'][:-1] == prior_entries
    registry.update(status='FIXED_FAMILY_ON_CORRECTED_UNIVERSE_VERIFIED', last_completed_stage='corrected_fixed_family_replay',
        updated_at_utc=datetime.now(timezone.utc).isoformat(),
        parent_registry={'path': str(v.PRIOR / 'MINI_ALPHA_REGISTRY.json'), 'sha256': r.sha(v.PRIOR / 'MINI_ALPHA_REGISTRY.json')},
        source_registry_sha256=r.sha(v.PRIOR / 'MINI_ALPHA_REGISTRY.json'),
        current_results={'path': str(ART / 'RESULTS.json'), 'sha256': r.sha(ART / 'RESULTS.json')})
    registry['trial_accounting_v421'] = {'new_signal_parameters': 0, 'existing_policy_count': 6,
        'annual_cost_nodes': 72, 'historical_reinspection': True, 'fresh_oos': False}
    registry['current_review'].append({'id': entry['id'], 'current_status': entry['status'],
        'usable_as_proven_alpha': False, 'fresh_oos': False, 'source': registry['current_results']})
    for a in registry['current_review']:
        if a['id'] in ('MA407-01','MA407-02','MA407-03','MA407-08','MA407-09'):
            a['latest_fixed_family_follow_up'] = registry['current_results']
    r.save(ART / 'MINI_ALPHA_REGISTRY.json', registry)
    d = {'results': result, 'verification': check, 'inputs': inputs,
         'tests_total': inputs['tests']['tests'] + check['tests']['tests'] + 1,
         'registry_entries': len(registry['entries'])}
    r.save(ART / 'REPORT_DATA.json', d)
    (ART / 'REPORT.md').write_text(render(r.read(ART / 'REPORT_DATA.json')), encoding='utf8')
    assert (ART / 'REPORT.md').read_text(encoding='utf8') == render(r.read(ART / 'REPORT_DATA.json'))
    assert r.read(ART / 'REPORT_DATA.json')['results'] == r.read(ART / 'RESULTS.json')
    r.save(ART / 'REPORT_CONSISTENCY.json', {'all_passed': True, 'method': 'Verified complete JSON projection and deterministic UTF8 render/readback',
        'report_sha256': r.sha(ART / 'REPORT.md'), 'report_data_sha256': r.sha(ART / 'REPORT_DATA.json'), 'results_sha256': r.sha(ART / 'RESULTS.json')})
    r.save(ART / 'GOAL_REQUIREMENTS_AUDIT.json', {'only_data_through2025': 'VERIFIED', 'per_fill_standard_and_stress': 'VERIFIED',
        'signed_historical_funding_rates': 'VERIFIED', 'all_funding_marks_exact': False,
        'fixed_family_corrected_universe': 'ALL_72_NODES_VERIFIED',
        'fresh_oos': 'NOT_ESTABLISHED_SCOPE_QUESTION_PENDING', 'mini_alpha_entries': len(registry['entries']),
        'goal_complete': False, 'live_signoff': 'NOT_GRANTED'})
    r.save(ART / 'PROGRESS.json', {'stage': 'fixed_family_corrected_universe_verified',
        'next_action': 'Assess the verified full-family results against the real goal and pending OOS scope. Do not infer a fresh holdout or live approval from reused history; do not automatically relax selection thresholds.',
        'goal_complete': False, 'live_signoff': 'NOT_GRANTED'})
    prior = r.read(v.PRIOR / 'CHECKPOINT.json')
    for p,h in prior['files'].items():
        assert r.sha(v.PRIOR / p) == h
    for p,h in prior['additional_sources'].items():
        assert r.sha(v.ROOT / p) == h
    sources = dict(r.read(ART / 'SOURCE_MANIFEST.json')['sources'])
    sources.update(r.read(ART / 'ECONOMIC_PROTOCOL.json')['sources'])
    sources[str(Path(adapter.__file__))] = r.sha(adapter.__file__)
    sources[str(v.ROOT / 'tests/unit/fibo_short/test_family_reconciliation_v421.py')] = r.sha(v.ROOT / 'tests/unit/fibo_short/test_family_reconciliation_v421.py')
    sources[str(Path(__file__))] = r.sha(__file__)
    paths = sorted(p for p in ART.rglob('*') if p.is_file() and p.name != 'CHECKPOINT.json')
    r.save(ART / 'CHECKPOINT.json', {'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'files': {str(p.relative_to(ART)): r.sha(p) for p in paths}, 'file_count': len(paths),
        'additional_sources': {str(Path(p).relative_to(v.ROOT)): h for p,h in sources.items()},
        'previous_files_preserved': len(prior['files']), 'goal_complete': False, 'live_signoff': 'NOT_GRANTED'})
    for p,h in r.read(ART / 'CHECKPOINT.json')['files'].items():
        assert r.sha(ART / p) == h
    print({'protected_files': len(paths), 'registry_entries': len(registry['entries']), 'tests_total': d['tests_total']}, flush=True)


if __name__ == '__main__':
    main()
