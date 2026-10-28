"""Publish the evidence catalogue, decision and concrete data request."""
from datetime import datetime, timezone
from pathlib import Path
import research_review_v420 as v

r = v.r
ART = v.ART


def file_link(path, label):
    return f'[{label}](<{Path(path).as_posix()}>)'


def render_catalogue(data):
    lines = ['# Danh mục bằng chứng và giả thuyết Fibo Trend Short', '',
             f"Có {data['entry_count']} mục được lưu; **{data['proven_alpha_count']} mục đủ bằng chứng để gọi là alpha đã chứng minh**. "
             'Các cải tiến về dữ liệu và quản trị rủi ro vẫn có thể tái sử dụng. '
             'Bản ghi lịch sử được giữ nguyên; bảng này bổ sung cách hiểu hiện hành.', '',
             '| Mục | Thành phần | Kết luận hiện hành |', '|---|---|---|']
    for row in data['entries']:
        lines.append(f"| {row['id']} | {row['name']} | {row['interpretation_vi']} |")
    lines += ['', '## Các thành phần đáng giữ lại', '',
              'Giữ bộ xử lý tín hiệu nhân quả, danh sách coin theo thời điểm, tách các vòng đời '
              'hợp đồng, khối lượng cố định cho vị thế đang mở, giới hạn danh mục và hạch toán '
              'chi phí từng lần khớp. Đây là nền tảng tái sử dụng cho nghiên cứu tiếp theo; '
              'việc kiểm thử đúng chưa chứng minh lợi nhuận tương lai.', '',
              'Giữ xác nhận Sniper như một giả thuyết có bằng chứng tương đối, với giới hạn rõ ràng: '
              'so sánh stress với M6 tốt hơn trên vũ trụ cũ, nhưng cả hai vẫn lỗ. '
              'Khoảng tin cậy đó chưa điều chỉnh toàn bộ các lần thử và chưa có OOS mới.', '',
              '## Các phép so sánh gần nhất của những giả thuyết ban đầu', '',
              'Bảng dưới dùng v4.0.9, tức vũ trụ cũ và hai chuẩn phí hiện hành. '
              'Không thay số liệu của từng thành phần bằng kết quả vũ trụ mở rộng chỉ mới chạy cho Elite + Sniper.', '',
              '| Mục | Kịch bản | NAV cấu hình | NAV đối chứng | MaxDD cấu hình / đối chứng | CI 95% chênh lệch tuần |',
              '|---|---|---:|---:|---:|---:|']
    for row in data['entries']:
        old = row.get('legacy_dual_cost_comparison')
        if not old:
            continue
        for scenario, a in old['scenarios'].items():
            candidate, baseline = a['candidate_six_year'], a['baseline_six_year']
            ci = a['paired_weekly_difference_ci']['ci95_pct']
            label = 'Chuẩn' if scenario == 'standard_vip6' else 'Stress'
            lines.append(f"| {row['id']} | {label} | {candidate['return_pct']:+.2f}% | {baseline['return_pct']:+.2f}% | "
                         f"{candidate['max_dd_pct']:.2f}% / {baseline['max_dd_pct']:.2f}% | [{ci[0]:+.4f}%; {ci[1]:+.4f}%] |")
    lines += ['', 'Tên cấu hình/đối chứng và toàn bộ bằng chứng nằm trong '
              + file_link(ART / 'EVIDENCE_CATALOG.json', 'danh mục JSON') + '. '
              'Mỗi mục có đường dẫn, SHA256 và JSON pointer về bản gốc; các mục dữ liệu đã '
              'được tái chạy có thêm tham chiếu sang v4.0.15. Giữ cả giả thuyết thất bại để tránh thử lại rồi quên số lần đã thử.']
    return '\n'.join(lines) + '\n'


def render_request(data):
    first = datetime.fromtimestamp(data['earliest_event_ms'] / 1000, timezone.utc).isoformat()
    last = datetime.fromtimestamp(data['latest_event_ms'] / 1000, timezone.utc).isoformat()
    lines = ['# Yêu cầu dữ liệu giá mark thanh toán funding lịch sử', '',
             f"Cần bổ sung **{data['unique_events']:,} kỳ funding của {data['symbols']} mã**, "
             f"thuộc {data['symbol_dates']:,} cặp mã–ngày. Phạm vi UTC: {first} đến {last}.", '',
             'Funding rate lịch sử đã có. Phần còn thiếu là giá mark gắn với kỳ thanh toán '
             'để thay giá OPEN đang dùng làm xấp xỉ. Chưa mua dữ liệu, chưa liên hệ nhà cung cấp và chưa xác nhận giá bán.', '',
             '| Năm | Kỳ cần giá mark chính xác |', '|---|---:|']
    for year, count in data['events_by_year'].items():
        lines.append(f'| {year} | {count:,} |')
    lines += ['', '## Nội dung cần nhà cung cấp xác nhận', '',
              'Cần mã sàn và đúng danh tính hợp đồng, timestamp thanh toán funding theo UTC '
              'đến mili giây, giá mark gắn với kỳ đó, timestamp gốc của sàn, timestamp thu thập, '
              'nguồn gốc dữ liệu và cờ khoảng trống. Mỗi kỳ trong danh sách phải được trả dữ liệu '
              'hoặc xác nhận không có; không tự điền giá qua khoảng mất dữ liệu.', '',
              'Một tick mark gần thời điểm thanh toán vẫn có thể chỉ là giá thị trường quan sát được. '
              'Nhà cung cấp cần chứng minh quan hệ với giá dùng cho thanh toán; nếu không chứng minh '
              'được, phải giữ nhãn xấp xỉ và báo độ lệch timestamp. Không thay funding đã thanh toán '
              'bằng funding dự báo trong derivative ticker.', '',
              '## Nguồn có thể kiểm tra', '',
              'Tardis công bố lưu luồng markPrice của Binance USDS-M Futures và có mẫu CSV miễn phí '
              'ngày đầu tháng. Họ cũng ghi nhận vấn đề thu thập trước 14/05/2020. '
              'Kênh fundingRate được ghi riêng từ 16/10/2026 không chứng minh phạm vi thanh toán '
              '2020–2025. [Tài liệu nhà cung cấp](https://docs.tardis.dev/historical-data-details/binance-futures).', '',
              'Bốn kỳ đã đối chiếu miễn phí trong hồ sơ cũ chỉ là kiểm tra mẫu. Trước khi mua '
              'cần nhà cung cấp xác nhận đủ danh sách yêu cầu, gửi mẫu kiểm tra timestamp/giá '
              'và báo các khoảng mất dữ liệu. Chưa thể khẳng định một gói đăng ký sẽ lấp đủ toàn bộ khoảng thiếu.', '',
              file_link(ART / 'DATA_PROCUREMENT_REQUIREMENTS.json', 'Danh sách mã, ngày và timestamp cần kiểm tra') + '.']
    return '\n'.join(lines) + '\n'


def render_review(d, wfo, check):
    facts = d['facts']
    lines = ['# Quyết định nghiên cứu Fibo Trend Short sau đối chiếu bằng chứng', '',
             '**Ứng viên chưa đủ bằng chứng để duyệt giao dịch thật.** Nền tảng tính toán đã '
             'được kiểm tra, nhưng hiệu quả dưới chi phí stress, giá trị tăng thêm của tín hiệu '
             'và xác nhận OOS vẫn chưa đạt cơ sở để kết luận chiến lược hoàn tất.', '',
             f"Vòng rà soát này giữ {d['catalogue_count']} mục trong nhật ký, không thêm giả thuyết alpha "
             'và không đọc thêm quan sát thị trường. Toàn bộ backtest được viện dẫn kết thúc ở năm 2025.', '',
             '## Bằng chứng kinh tế hiện hành', '',
             '| Phạm vi | Chuẩn VIP6 và trượt giá 10 bps | Stress Regular và trượt giá 50 bps |',
             '|---|---:|---:|']
    for period, name in [('all_2020_2025', 'NAV liên tục 2020–2025'),
                         ('retrospective_oos_2024_2025', 'NAV liên tục 2024–2025 hồi cứu')]:
        nodes = facts['continuous_portfolio']['periods'][period]
        values = [nodes[s]['all_continuous']['return_pct'] for s in v.SCENARIOS]
        lines.append(f'| {name} | {values[0]:+.2f}% | {values[1]:+.2f}% |')
    for name, key in [('Fibo trừ đối chứng, giữ 24 giờ', 'matched_24h'),
                      ('Fibo trừ đối chứng, stop và TP nguyên bản', 'matched_original_exits')]:
        values = [facts[key][s]['mean_difference_bps'] for s in v.SCENARIOS]
        lines.append(f'| {name} | {values[0]:+.2f} bps/lệnh | {values[1]:+.2f} bps/lệnh |')
    lines += ['', 'Chi phí áp dụng từng lần khớp, kể cả chốt từng phần: phí taker 2,5 bps ở '
              'bản chuẩn và 5 bps ở bản stress; không giảm phí BNB. Funding giữ đúng dấu. '
              'Hai dòng đối chứng là trung bình trên các cặp ghép trong 2024–2025, không phải NAV. '
              'CI 95% của cả bốn chênh lệch ghép đều chứa 0; CI tuần của các dòng NAV cũng chứa 0.', '',
              '## Kiểm tra chọn chiến lược bằng dữ liệu quá khứ', '',
              'Giữ đúng quy tắc đã đăng ký ở v4.0.9: ít nhất hai năm trước và 60 lệnh, '
              'mọi năm trước dương ở bản chuẩn, tổng stress không âm, MaxDD từng năm không quá '
              '15% ở cả hai mức chi phí và không thiếu nến thực thi. Đây là cổng nghiên cứu '
              'đã chọn trước vòng này, không phải ngưỡng người dùng vừa yêu cầu.', '',
              '| Năm kiểm tra | Họ 6 cấu hình cũ | Elite + Sniper trên vũ trụ đã sửa | Stress của tập năm huấn luyện đã sửa | MaxDD năm tệ nhất đã sửa |',
              '|---|---|---|---:|---:|']
    for year in ('2022', '2023', '2024', '2025'):
        a = wfo['corrected_single_policy_gate_audit'][year]['audit']['elite_sniper_risk']
        lines.append(f"| {year} | {facts['walk_forward']['original'][year]} | "
                     f"{facts['walk_forward']['corrected_single_policy'][year]} | {a['stress']['return_pct']:+.2f}% | {a['worst_annual_dd']:.2f}% |")
    lines += ['', 'Họ cấu hình cũ khớp cả bốn quyết định đã khóa. Phần vũ trụ đã sửa chỉ '
              'kiểm tra cổng của một ứng viên Elite + Sniper; chưa phải tái chạy cả họ sáu '
              'cấu hình. CASH là không đủ điều kiện giao dịch, không phải alpha hoặc lợi nhuận '
              'đã xác nhận. Việc xét từng năm chỉ dùng số liệu các năm trước không xóa ảnh hưởng '
              'của lịch sử phát triển họ cấu hình trên 2024–2025.', '',
              '## Những gì có thể tái sử dụng', '',
              'Bộ tính khối lượng và giới hạn rủi ro, tín hiệu nhân quả, dữ liệu theo thời điểm, '
              'tách vòng đời hợp đồng và hạch toán chi phí là các thành phần hữu ích. Sniper '
              'có bằng chứng cải thiện tương đối so với M6 trong stress trên vũ trụ cũ; cả hai '
              'vẫn lỗ và chưa có xác nhận mới. Không có mục nào được nâng thành alpha đã chứng minh.', '',
              file_link(ART / 'EVIDENCE_CATALOG.md', 'Danh mục đầy đủ 23 mục') + '.', '',
              '## Những phần còn mở', '',
              'Giá mark thanh toán còn cần đối chiếu cho các kỳ cũ được liệt kê trong '
              + file_link(ART / 'DATA_PROCUREMENT_REQUIREMENTS.md', 'yêu cầu dữ liệu') + '. '
              'Sửa phần này giúp độ chính xác funding; không có bằng chứng rằng nó sẽ làm chiến lược sinh lời.', '',
              'Dữ liệu 2020–2025 đã được xem nhiều lần nên không thể tái gọi là holdout mới. '
              'Phạm vi xác nhận OOS đang chờ lựa chọn của người dùng giữa đánh giá hồi cứu '
              'đến 2025 và paper trading trên quan sát phát sinh sau khi khóa mô hình. '
              'Chưa bắt đầu thu thập hoặc backtest dữ liệu tương lai.', '',
              'Trong phạm vi đã được phép, bước kiểm tra còn thiếu là tái chạy đúng họ sáu '
              'cấu hình cũ trên vũ trụ đã sửa, với hai mức chi phí và cổng chọn từ quá khứ giữ '
              'nguyên. Phải kiểm tra chất lượng thực thi và funding của các ứng viên bổ sung '
              'trước khi tính kết quả; không loại lệnh dựa vào biến động tương lai để làm đẹp NAV.', '',
              '## Kiểm chứng vòng rà soát', '',
              f"Đã kiểm tra độc lập {check['independent_yearly_selection_audits']} quyết định theo năm, "
              f"{check['policy_year_eligibility_checks']} lượt điều kiện cấu hình–năm, đối chiếu "
              f"{check['original_ex_ante_locks_reconciled']} quyết định gốc; "
              f"{check['tests']['tests']} kiểm thử chống đọc năm tương lai, thiếu lịch sử và vi phạm cổng đều đạt. "
              f"Giữ nguyên {check['previous_files_preserved']} tệp của vòng trước và cả 23 mục lịch sử. "
              'Báo cáo được kết xuất từ JSON đã đối chiếu. Đây là kiểm chứng tổng hợp và quy tắc '
              'chọn; không thay thế các kiểm toán giao dịch đã lưu ở từng vòng trước.']
    return '\n'.join(lines) + '\n'


def main():
    v.verify_sources()
    d = r.read(ART / 'REVIEW.json')
    check = r.read(ART / 'VERIFICATION.json')
    assert check['all_passed'] and check['review_sha256'] == r.sha(ART / 'REVIEW.json')
    wfo = r.read(ART / 'WALK_FORWARD_AUDIT.json')
    rendered = {
        'REPORT.md': render_review(d, wfo, check),
        'EVIDENCE_CATALOG.md': render_catalogue(r.read(ART / 'EVIDENCE_CATALOG.json')),
        'DATA_PROCUREMENT_REQUIREMENTS.md': render_request(r.read(ART / 'DATA_PROCUREMENT_REQUIREMENTS.json')),
    }
    for name, content in rendered.items():
        (ART / name).write_text(content, encoding='utf8')
        assert (ART / name).read_text(encoding='utf8') == content
    r.save(ART / 'REPORT_CONSISTENCY.json', {'all_passed': True,
        'method': 'Verified source projections and deterministic JSON-based render with UTF8 readback',
        'reports': {name: r.sha(ART / name) for name in rendered},
        'json_sources': {name: r.sha(ART / name) for name in ('REVIEW.json', 'VERIFICATION.json', 'WALK_FORWARD_AUDIT.json', 'EVIDENCE_CATALOG.json', 'DATA_PROCUREMENT_REQUIREMENTS.json')}})
    r.save(ART / 'NEXT_FIXED_FAMILY_PROTOCOL.json', {
        'registered_at_utc': datetime.now(timezone.utc).isoformat(),
        'question': 'Does the unchanged six-policy family and historical selection rule behave differently on the corrected full universe?',
        'policy_family': ['reference_m6_fixed', 'm6_risk', 'elite_sniper_risk', 'sniper_risk', 'sniper_horizon24', 'sniper_rr1_horizon24'],
        'source_family': evidence_ref(v.BASE / 'research_v4_0_9/PROTOCOL.json'),
        'data': 'Corrected v415 PIT membership and frozen raw candidate cache, with full required pre2026 paths. No new universe ranking or signal thresholds.',
        'quality': 'Before economic results, reconcile all overlapping candidates, audit original and24h paths, lifecycle, entry/exit coverage and zero-volume fills. Do not discard candidates based on future execution quality. Any accepted unresolved execution issue prevents qualification and must be reported.',
        'funding': 'Signed actual historical rates; acquire only missing pre2026 coverage, preserve and label mark proxies. Fail on missing event coverage rather than zero-filling.',
        'execution': 'Same v409 per-fill costs, fixed quantities, portfolio caps before wave/cooldown consumption. Same annual-reset and final-five-day embargo convention for direct historical-family comparison.',
        'costs': d['facts']['continuous_portfolio']['scenarios'],
        'selection': 'Unchanged v409 prior-years-only eligibility and ranking. No use of test-year results in that year selection. CASH if no eligible policy; do not relax thresholds.',
        'reconciliation': 'Elite-sniper yearly standard/stress endpoints must reproduce v415 exactly. Preserve prior versions and publish all6x6x2 nodes, including failed or invalid nodes.',
        'statistics': 'Common Monday calendar4week circular block bootstrap10000 seed412 for fixed-policy and selected paths. Retrospective reuse and multiple trials disclosed; no proof from selecting the best observed policy.',
        'new_signal_parameters': 0, 'fresh_oos': False, 'goal_complete': False, 'live_signoff': 'NOT_GRANTED'})
    r.save(ART / 'PROGRESS.json', {'stage': 'evidence_catalogue_and_past_only_selection_audited',
        'previous_goal_turn': 'PROGRESS_CONTINUOUS_PORTFOLIO_VERIFIED',
        'next_action': 'Follow NEXT_FIXED_FAMILY_PROTOCOL.json, starting with candidate-quality and funding requirements. Keep pending OOS-scope question; no future market data.',
        'goal_complete': False, 'live_signoff': 'NOT_GRANTED'})
    previous = r.read(v.PRIOR / 'CHECKPOINT.json')
    for p, h in previous['files'].items():
        assert r.sha(v.PRIOR / p) == h, p
    for p, h in previous['additional_sources'].items():
        assert r.sha(v.ROOT / p) == h, p
    paths = sorted(p for p in ART.rglob('*') if p.is_file() and p.name != 'CHECKPOINT.json')
    local_sources = [v.ROOT / 'scripts/fibo_research' / name for name in
                     ('research_review_v420.py', 'verify_research_review_v420.py', 'report_research_review_v420.py')]
    local_sources.append(v.ROOT / 'tests/unit/fibo_short/test_research_review_v420.py')
    r.save(ART / 'CHECKPOINT.json', {'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'files': {str(p.relative_to(ART)): r.sha(p) for p in paths}, 'file_count': len(paths),
        'additional_sources': {str(p.relative_to(v.ROOT)): r.sha(p) for p in local_sources},
        'previous_files_preserved': len(previous['files']), 'goal_complete': False, 'live_signoff': 'NOT_GRANTED'})
    for p, h in r.read(ART / 'CHECKPOINT.json')['files'].items():
        assert r.sha(ART / p) == h
    print({'published_reports': list(rendered), 'protected_files': len(paths)}, flush=True)


def evidence_ref(path):
    return v.evidence_ref(path)


if __name__ == '__main__':
    main()
