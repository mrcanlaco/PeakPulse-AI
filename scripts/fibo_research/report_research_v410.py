"""Render the verified matched-event evidence from its frozen JSON."""
from datetime import datetime,timezone
from pathlib import Path
import research_v410 as v

r=v.r;ART=v.ART


def interval_text(stat):
    # A resample of one observed week cannot identify sampling uncertainty.
    if stat['active_weeks']<2:return 'Không suy luận: dưới 2 tuần có mẫu'
    lo,hi=stat['paired_difference_ci95_bps']
    return f'[{lo:+.2f}; {hi:+.2f}]'


def render(result,verified,coverage):
    supported=result['incremental_diagnostic_support']
    lines=['# Kiểm tra phần lợi thế của Fibo so với short theo đà giảm',
        '', '**Chưa đủ cơ sở duyệt chiến lược.** '+('Phép đối chiếu đạt điều kiện hỗ trợ chẩn đoán đã đăng ký, nhưng chưa phải bằng chứng OOS mới.' if supported else 'Phép đối chiếu chưa đạt điều kiện hỗ trợ chẩn đoán đã đăng ký.'),
        '', 'Dữ liệu chỉ thuộc giai đoạn 2020–2025. Hai phía vào cùng thời điểm, có đà giá và biến động 24 giờ trước lệnh gần nhau, giữ cùng 24 giờ với khối lượng cố định. Đây là nghiên cứu lợi nhuận từng sự kiện, không phải đường NAV danh mục. Các con số không được cộng dồn hay lãi kép để suy ra hiệu quả đầu tư.',
        '', '## Hai mức chi phí', '',
        '| Kịch bản | Phí mỗi lần khớp | Trượt giá mỗi lần khớp | Funding |',
        '|---|---:|---:|---|',
        '| Chuẩn VIP6 | 2,5 bps | 10 bps | Lịch sử thực tế, có ghi nguồn giá mark |',
        '| Stress Regular | 5 bps | 50 bps | Cùng phương pháp |',
        '', 'Phí taker USDⓈ-M được tính trên giá trị khớp sau trượt giá, chưa giảm phí BNB. Mức phí là giả định chuẩn cố định cho nghiên cứu; không mô phỏng lịch sử thay đổi cấp VIP. Một vòng giá không đổi chịu tổng chi phí 25 bps ở bản chuẩn và 110 bps ở bản stress. Nghiên cứu này chỉ có một lần vào và một lần ra; quy tắc tính phí cho mọi lần thoát từng phần vẫn áp dụng trong bộ máy danh mục v4.0.9.',
        '', '## Mẫu được đối chiếu', '',
        f"Có **{result['sampling']['raw_elite_candidates']:,}** ứng viên elite-sniper ban đầu. Sau quy tắc lấy mẫu theo wave, nghỉ 24 giờ theo từng mã và khoảng loại trừ cuối năm, còn **{result['sampling']['sampled_events']:,}** sự kiện. Ghép được **{result['matched_pairs']:,}** cặp; **{len(result['incomplete_pairs']):,}** cặp thiếu dữ liệu thực thi sau khi ghép.",
        '', '| Lý do không ghép được | Sự kiện |','|---|---:|']
    labels={'treated_nonnegative_momentum':'Đà giá 24 giờ của Fibo không âm','outside_fixed_caliper':'Không có mã đối chứng đủ gần trong giới hạn 0,5 độ lệch chuẩn',
        'fewer_than_three_negative_controls':'Có ít hơn 3 đối chứng đà giảm hợp lệ','treated_past_feature_missing':'Thiếu chuỗi giá quá khứ liên tục','degenerate_control_dispersion':'Độ phân tán đối chứng bằng không'}
    for key,count in result['sampling']['unmatched_reasons'].items():lines.append(f'| {labels.get(key,key)} | {count:,} |')
    lines += ['', 'Đối chứng thuộc danh sách top 50 thanh khoản tại tháng đó, có đà giá 24 giờ âm và không có tín hiệu elite-sniper trong bộ ứng viên tại cùng thời điểm. Không thay đối chứng theo lợi nhuận tương lai. Các đặc trưng chỉ dùng nến đã đóng trước quyết định; bộ tín hiệu Fibo kế thừa điều kiện hợp lệ của giá mở cửa khớp sau 5 phút. Vì vậy phép ghép dùng thông tin có sẵn chậm nhất lúc vào lệnh, không phải một bộ chọn chỉ dựa vào thời điểm quyết định ban đầu.',
        '', f"Giới hạn sai lệch sau chuẩn hóa lớn nhất cho đà giá và biến động: {', '.join(f'{n:.3f}' for n in result['balance']['max_abs_standardized_difference'])}. Có {result['balance']['unique_control_symbol_times']:,} tổ hợp mã–thời điểm đối chứng riêng biệt. Việc dùng lại đối chứng và các sự kiện đồng thời được giữ nguyên khi lấy mẫu bootstrap theo tuần.",
        '', '## Kết quả theo giai đoạn', '',
        '**Đơn vị: bps lợi nhuận ròng trên giá trị danh nghĩa ban đầu, trung bình mỗi sự kiện.** 100 bps = 1%. Chênh lệch dương nghĩa là Fibo tốt hơn đối chứng. Khoảng tin cậy lấy mẫu theo khối 4 tuần, 10.000 lượt, giữ nguyên từng cặp và số sự kiện mỗi tuần.',
        '', '| Giai đoạn | Chi phí | Cặp | Fibo | Đối chứng | Fibo trừ đối chứng | Khoảng tin cậy 95% của chênh lệch |',
        '|---|---|---:|---:|---:|---:|---|']
    names={'development_2020_2022':'2020–2022 tham chiếu','validation_2023':'2023 kiểm tra','retrospective_oos_2024_2025':'2024–2025 OOS hồi cứu','all_2020_2025':'Toàn bộ 2020–2025'}
    for split,label in names.items():
        for scenario,cost in [('standard_vip6','Chuẩn'),('stress_regular','Stress')]:
            s=result['results'][scenario]['splits'][split]
            if not s['available']:lines.append(f'| {label} | {cost} | 0 | — | — | — | Không đủ mẫu |');continue
            lines.append(f"| {label} | {cost} | {s['pairs']} | {s['mean_fibo_bps']:+.2f} | {s['mean_control_bps']:+.2f} | {s['mean_difference_bps']:+.2f} | {interval_text(s)} |")
    lines += ['', '## Kết quả từng năm', '', '| Năm | Chi phí | Cặp | Fibo | Đối chứng | Chênh lệch | Khoảng tin cậy 95% |', '|---|---|---:|---:|---:|---:|---|']
    for year in range(2020,2026):
        for scenario,cost in [('standard_vip6','Chuẩn'),('stress_regular','Stress')]:
            s=result['results'][scenario]['annual'][str(year)]
            if not s['available']:lines.append(f'| {year} | {cost} | 0 | — | — | — | Không đủ mẫu |');continue
            lines.append(f"| {year} | {cost} | {s['pairs']} | {s['mean_fibo_bps']:+.2f} | {s['mean_control_bps']:+.2f} | {s['mean_difference_bps']:+.2f} | {interval_text(s)} |")
    lines += ['', 'Năm 2020 chỉ có một cặp, nên không thể ước lượng bất định từ các tuần độc lập. Khoảng bootstrap suy biến trong JSON được giữ để tái lập tính toán nhưng không được diễn giải là khoảng tin cậy có ý nghĩa. Các năm ít mẫu khác cũng chỉ dùng để mô tả; quyết định chẩn đoán dựa trên giai đoạn 2024–2025 và điều kiện đã đăng ký.']
    lines += ['', '## Funding và kiểm chứng', '',
        f"Đã dùng lại dữ liệu funding đã kiểm chứng cho {coverage['reused_symbols']} mã và tải bổ sung từ Binance cho {coverage['newly_acquired_symbols']} mã. Kiểm tra lại {verified['funding_snapshot_events_verified']:,} bản ghi funding trong phạm vi các tệp dùng cho phép thử, gồm cả các sự kiện ngoài thời gian đang giữ lệnh.",
        '', f"Đã đối chiếu {verified['scenario_leg_outcomes_recomputed']:,} kết quả từng phía theo từng mức phí và {verified['scenario_funding_payments_recomputed']:,} khoản funding. Đây là số bản ghi tính toán, có lặp giữa các kịch bản, không phải số quan sát thị trường độc lập. Có {verified['nonzero_proxy_events_requiring_exact_mark']:,} sự kiện funding riêng biệt có dòng tiền khác 0 còn cần giá mark chính xác; danh sách được lưu trong EXACT_MARK_DATA_REQUEST.json.",
        '', 'Khi Binance không trả giá mark tại settlement, phép thử giữ cách dùng giá mở cửa nến mark chính thức trước timestamp funding tối đa 15 giây. Giá này là đại diện có công bố, chưa phải tick settlement được chứng nhận. Không đặt funding thiếu bằng 0. Cần xác nhận dữ liệu chính xác hoặc đo độ nhạy trước khi duyệt cuối cùng.',
        '', f"{verified['tests']['tests']} kiểm thử đạt, không lỗi và không bỏ qua. Đã tính lại {verified['past_feature_rows_recomputed']:,} dòng đặc trưng quá khứ, kiểm tra lựa chọn đối chứng và đối chiếu dòng tiền từ giá thực thi cùng nguồn funding. Giữ nguyên {verified['previous_v409_files_preserved']:,} tệp của v4.0.9. Báo cáo được kết xuất từ RESULTS.json và đối chiếu lại nguyên văn.",
        '', '## Ý nghĩa và quyết định', '',
        'Điều kiện chẩn đoán đăng ký trước là ít nhất 200 cặp đầy đủ trong 2024–2025, không thiếu cặp đã ghép và cận dưới khoảng tin cậy của chênh lệch lớn hơn 0 ở cả hai mức phí. '+('Điều kiện này đạt.' if supported else 'Điều kiện này chưa đạt.'),
        '', 'Chỉ tiêu này đo phần khác biệt giữa các mã tại cùng thời điểm, trong nhóm Fibo đang có đà giảm và có đối chứng tương đồng. Nó chưa đo giá trị của thời điểm phát tín hiệu, không bao phủ tín hiệu đảo chiều có đà giá 24 giờ dương và không kiểm chứng cơ chế stop/TP của chiến lược gốc. Các khác biệt chưa quan sát giữa hai mã vẫn có thể ảnh hưởng kết quả.',
        '', 'Chính sách elite-sniper được chọn sau khi đã thấy kết quả vòng trước; toàn bộ lịch sử và họ chiến lược cũng đã được khảo sát. Các nhãn giai đoạn chỉ mô tả trật tự thời gian hồi cứu, không tạo ra OOS chưa từng sử dụng. Khoảng tin cậy chưa điều chỉnh cho các lần thử chiến lược trước đó. Thiên lệch do vũ trụ tệp còn tồn tại cũng chưa được loại bỏ.',
        '', '**Trạng thái: nghiên cứu tiếp, chưa cấp sign-off giao dịch thật hoặc công bố chiến lược đã hoàn tất.** Kết quả chẩn đoán được lưu vào nhật ký mini-alpha cùng các kết quả bất lợi; không nâng thành alpha đã xác nhận.',
        '', 'Giả thuyết kế tiếp đã được ghi riêng trong NEXT_HYPOTHESIS.json: đối chiếu nhóm Fibo sau một nhịp tăng với lệnh short sau nhịp tăng thông thường, giữ cùng chi phí, thời gian nắm giữ và giới hạn ghép. Đây là hướng chưa thử, được chọn sau vòng này; không phải kết quả đã đạt. Không sửa tiêu chuẩn của phép thử vừa hoàn thành.',
        '', 'Nguồn dữ liệu và phương pháp chi phí: [Binance Futures fee table](https://www.binance.com/en/fee/futureFee), [Binance funding history](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History).']
    return '\n'.join(lines)+'\n'


def main():
    result=r.read(ART/'RESULTS.json');verified=r.read(ART/'INDEPENDENT_VERIFICATION.json');coverage=r.read(ART/'funding/MANIFEST.json')
    assert verified['all_checks_passed'] and verified['results_sha256']==r.sha(ART/'RESULTS.json')
    text=render(result,verified,coverage);(ART/'REPORT.md').write_text(text,encoding='utf8')
    assert (ART/'REPORT.md').read_text(encoding='utf8')==render(r.read(ART/'RESULTS.json'),r.read(ART/'INDEPENDENT_VERIFICATION.json'),r.read(ART/'funding/MANIFEST.json'))
    r.save(ART/'REPORT_CONSISTENCY.json',{'all_passed':True,'method':'Exact deterministic rerender/readback from frozen JSON',
        'results_sha256':r.sha(ART/'RESULTS.json'),'report_sha256':r.sha(ART/'REPORT.md')})
    r.save(ART/'STATISTICAL_QUALIFICATIONS.json',{'raw_results_unchanged':True,'primary_endpoint_unchanged':True,
        'conservative_display_qualification':'Periods with fewer than2 active calendar-week clusters cannot support sampling-uncertainty inference; suppress the raw degenerate bootstrap interval in the report.',
        'qualified_periods':{s:[y for y,a in p['annual'].items() if a.get('available') and a['active_weeks']<2] for s,p in result['results'].items()},
        'results_sha256':r.sha(ART/'RESULTS.json')})
    registry=r.read(v.z.ART/'MINI_ALPHA_REGISTRY.json')
    registry['status']='MATCHED_MOMENTUM_DIAGNOSTIC_RECORDED';registry['source_registry_sha256']=r.sha(v.z.ART/'MINI_ALPHA_REGISTRY.json')
    registry['entries'].append({'id':'MA410-Q2','hypothesis_vi':'Phần giá trị chọn tín hiệu Fibo vượt short theo đà giảm khi ghép cùng thời điểm, đà giá, biến động và thời gian giữ lệnh',
        'type':'conditional_cross_sectional_diagnostic_not_standalone_alpha','origin_hypothesis':'MA407-Q2',
        'status':'INCREMENTAL_DIAGNOSTIC_SUPPORT_ONLY' if result['incremental_diagnostic_support'] else 'INCREMENTAL_SUPPORT_NOT_ESTABLISHED',
        'usable_as_proven_alpha':False,'fresh_oos':False,'historical_selection_disclosed':True,
        'evidence':{s:p['splits'] for s,p in result['results'].items()},'matched_pairs':result['matched_pairs'],
        'limitations':['Cross-sectional match leaves timing contribution untested','Negative-momentum common-support subset only','Fixed24h without original stops/targets','No portfolio capital constraints','Funding mark proxy partly unresolved','Global history reused; unadjusted CI'],
        'results_sha256':r.sha(ART/'RESULTS.json')})
    r.save(ART/'MINI_ALPHA_REGISTRY.json',registry)
    r.save(ART/'PROGRESS.json',{'stage':'matched_momentum_diagnostic_verified_and_documented','goal_complete':False,'fresh_oos':False,
        'data_ceiling':'2025-12-31','incremental_diagnostic_support':result['incremental_diagnostic_support'],'live_signoff':'NOT_GRANTED',
        'next_action':'Do not tune this frozen matching design. Separately freeze and test MA410-Q2A positive-momentum reversal controls as registered in NEXT_HYPOTHESIS.json; retain historical reuse and exact-mark limitations.'})
    paths=sorted(p for p in ART.rglob('*') if p.is_file() and p.name!='CHECKPOINT.json')
    r.save(ART/'CHECKPOINT.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'files':{str(p.relative_to(ART)):r.sha(p) for p in paths},
        'file_count':len(paths),'additional_sources':{str(Path(__file__).relative_to(r.ROOT)):r.sha(__file__)},'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    print('Report, 13-entry mini-alpha registry, consistency check and checkpoint saved.',flush=True)


if __name__=='__main__':main()
