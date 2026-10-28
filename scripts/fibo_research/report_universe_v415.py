"""Publish verified full-universe economics without claiming clean temporal OOS."""
from datetime import datetime,timezone
from pathlib import Path
import xml.etree.ElementTree as ET
import evaluate_universe_resolved_v415 as resolved
import funding_sensitivity_v415 as sensitivity
import recover_funding_marks_v415 as recovery

b=resolved.base;v=b.v;r=b.r;ART=b.ART


def render(d):
    result=d['results'];check=d['verification'];source=d['inputs'];correction=d['membership'];sens=d['sensitivity']
    lines=['# Kết quả vũ trụ mở rộng 2020–2025 — v4.0.15','',d['decision_vi'],'',d['interpretation_vi'],
        '', '| Giai đoạn | Chuẩn VIP6: NAV | MaxDD | Stress Regular: NAV | MaxDD |','|---|---:|---:|---:|---:|']
    for key,label in [('retrospective_oos_2024_2025','2024–2025 — đánh giá hồi cứu'),('all_2020_2025','2020–2025 — toàn kỳ')]:
        standard=result['periods'][key]['standard_vip6']['corrected_expanded'];stress=result['periods'][key]['stress_regular']['corrected_expanded']
        lines.append(f"| {label} | {standard['return_pct']:+.2f}% | {standard['max_dd_pct']:.2f}% | {stress['return_pct']:+.2f}% | {stress['max_dd_pct']:.2f}% |")
    lines += ['', '## Theo từng năm', '', '| Năm | Chuẩn | Stress | Số lệnh chuẩn / stress |','|---|---:|---:|---:|']
    for year,node in result['annual'].items():
        a=node['standard_vip6'];c=node['stress_regular'];lines.append(f"| {year} | {a['return_pct']:+.2f}% | {c['return_pct']:+.2f}% | {a['trades']} / {c['trades']} |")
    lines += ['',d['portfolio_semantics_vi'],'','## Đối chiếu với bộ dữ liệu cũ','', '| Giai đoạn / chi phí | Bộ cũ | Vũ trụ mở rộng | Chênh lệch NAV |','|---|---:|---:|---:|']
    for key,label in [('retrospective_oos_2024_2025','2024–2025'),('all_2020_2025','2020–2025')]:
        for scenario,title in [('standard_vip6','chuẩn'),('stress_regular','stress')]:
            a=result['periods'][key][scenario];old=a['old_snapshot']['return_pct'];new=a['corrected_expanded']['return_pct']
            lines.append(f"| {label} / {title} | {old:+.2f}% | {new:+.2f}% | {new-old:+.2f} điểm % |")
    lines += ['',d['universe_interpretation_vi'],'', '## Độ bất định và OOS','', '| 2024–2025 | Lợi nhuận tuần bình quân | CI 95% theo lịch tuần đã đăng ký | CI 97,5% chênh lệch tuần mở rộng − cũ |','|---|---:|---:|---:|']
    for scenario,label in [('standard_vip6','Chuẩn'),('stress_regular','Stress')]:
        a=result['periods']['retrospective_oos_2024_2025'][scenario]['corrected_expanded']['calendar_weekly_ci95'];c=result['paired_comparisons']['retrospective_oos_2024_2025'][scenario]['expanded_minus_old']
        lines.append(f"| {label} | {a['mean_weekly_pct']:+.4f}% | [{a['ci_pct'][0]:+.4f}%; {a['ci_pct'][1]:+.4f}%] | [{c['ci_pct'][0]:+.4f}%; {c['ci_pct'][1]:+.4f}%] |")
    lines += ['',d['inference_vi'],'',d['oos_vi'],'','## Chi phí và funding','', '| Kịch bản | Phí taker mỗi lần khớp | Trượt giá mỗi lần khớp |','|---|---:|---:|---:|']
    for scenario,label in [('standard_vip6','Chuẩn VIP6'),('stress_regular','Stress Regular')]:
        a=result['scenarios'][scenario];lines.append(f"| {label} | {a['fee_bps']:g} bps | {a['slippage_bps']:g} bps |")
    lines += ['',d['cost_vi'],
        '',f"Đã đối chiếu funding cho **{source['funding_symbols']} mã**, gồm {source['funding_events']:,} bản ghi lịch sử từ {source['raw_api_responses_verified']:,} phản hồi API và {source['official_mark_archives_independently_parsed']} tệp mark-price tháng. {d['funding_acquisition']['reused']} mã dùng lại snapshot đã kiểm chứng; {d['funding_acquisition']['new_rest']} mã tải mới bằng REST; {d['funding_acquisition']['archive_recovered']} mã bổ sung mark price từ kho chính thức. {source['overlapping_v409_funding_records_equal']:,} bản ghi trùng với v4.0.9 khớp hoàn toàn.",
        '',f"Trong bộ nguồn, {source['funding_price_sources']['funding_api_settlement_mark']:,} bản ghi có mark thanh toán từ API; {source['funding_price_sources']['official_mark_candle_open_proxy']:,} bản ghi dùng OPEN của nến mark-price giờ từ API và {source['funding_price_sources'].get('official_mark_archive_open_proxy',0):,} bản ghi dùng OPEN từ kho tháng. Các OPEN này là giá thay thế, không phải giá thanh toán chính xác. Chỉ lấy OPEN trước kỳ funding tối đa 15 giây; không dùng giá đóng tương lai.",
        '',f"Trong các giao dịch được chấp nhận, có {check['funding_payments']:,} khoản funding ở hai kịch bản, trong đó {check['proxy_funding_payments']:,} khoản dùng mark thay thế. Danh sách cần mark chính xác còn {check['exact_mark_unique_events_needed']:,} kỳ riêng biệt. Các khoản funding của lệnh được chấp nhận trong **2024–2025 đều có mark thanh toán từ API**, không dùng proxy.",
        '', '## Kiểm tra độ nhạy với mark price thay thế', '', '| Giai đoạn / kịch bản | Cơ sở | Proxy bất lợi 1% | Proxy bất lợi 5% |','|---|---:|---:|---:|']
    for period,label in [('retrospective_oos_2024_2025','2024–2025'),('all_2020_2025','2020–2025')]:
        for scenario,title in [('standard_vip6','chuẩn'),('stress_regular','stress')]:
            base=result['periods'][period][scenario]['corrected_expanded']['return_pct'];one=sens['levels']['1%']['periods'][period][scenario]['return_pct'];five=sens['levels']['5%']['periods'][period][scenario]['return_pct']
            lines.append(f"| {label} / {title} | {base:+.3f}% | {one:+.3f}% | {five:+.3f}% |")
    lines += ['',d['sensitivity_vi'],'','## Kiểm tra dữ liệu và sổ giao dịch','',
        f"Sửa {correction['changed_months']} tháng còn giữ mã đã đóng hợp đồng; sau sửa không còn thành viên tháng bị cờ dừng giao dịch từ ít nhất 24 giờ trước đó. Việc sửa này giữ nguyên {source['signals_unchanged_vs_v414']:,} ứng viên của v4.0.14. Năm đường đi TLM chạm vùng sàng lọc trước ngày đóng hợp đồng được kiểm tra theo mốc chính thức: tất cả đã thoát trước giờ thanh toán; không xóa giao dịch nào.",
        '',f"Kiểm tra độc lập xác nhận {check['nodes']} tổ hợp năm–chi phí, {check['scenario_trades']:,} bản ghi giao dịch, {check['fills']:,} nhóm khớp, {check['entry_cap_checks']:,} lần kiểm tra vốn/hạn mức khi vào lệnh và toàn bộ dòng tiền funding. Có {d['tests']['tests']} kiểm thử mới đạt. Các kịch bản nhạy cảm bổ sung có {sens['scenario_nodes_checked']} tổ hợp và {sens['funding_payments_checked']:,} khoản funding được đối chiếu dòng tiền.",
        '',d['execution_limits_vi'],'','## Quyết định nghiên cứu','',d['next_decision_vi'],
        '',f"Nhật ký MINI_ALPHA_REGISTRY.json giữ nguyên {d['registry_previous_entries']} mục cũ và bổ sung một mục về kết quả vũ trụ mở rộng, phân loại là bằng chứng mô tả; chưa công nhận alpha đã chứng minh.",
        '', 'Nguồn dữ liệu: [Binance funding-rate history](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History), [Binance Public Data và checksum](https://github.com/binance/binance-public-data). URL, payload và checksum cụ thể nằm trong manifest funding; mốc hợp đồng có nguồn trong EVENTS.json.']
    return '\n'.join(lines)+'\n'


def main():
    resolved.verify_sources();sensitivity.verify_sources();recovery.verify_sources()
    result=r.read(ART/'RESULTS.json');check=r.read(ART/'INDEPENDENT_VERIFICATION.json');inputs=r.read(ART/'INPUT_VERIFICATION.json');sens=r.read(sensitivity.OUT/'RESULTS.json')
    assert check['all_accounting_checks_passed'] and check['results_sha256']==r.sha(ART/'RESULTS.json') and inputs['all_passed']
    assert sens['independent_cash_checks_passed'] and sens['baseline_results_sha256']==r.sha(ART/'RESULTS.json')
    assert sens['protocol_sha256']==r.sha(sensitivity.OUT/'PROTOCOL.json')
    exposure=r.read(ART/'FUNDING_EXPOSURE.json')
    for year in [2024,2025]:
        for scenario in b.SCENARIOS:assert exposure['annual'][f'{year}/{scenario}']['proxy_funding_payments']==0
    suites=[]
    for p in [ART/'TESTS.xml',recovery.OUT/'TESTS.xml',sensitivity.OUT/'TESTS.xml']:suites.extend(ET.parse(p).getroot().iter('testsuite'))
    tests={k:sum(int(a.get(k,0)) for a in suites) for k in ('tests','errors','failures','skipped')};assert tests['tests']==13 and tests['errors']==tests['failures']==tests['skipped']==0
    funding=r.read(ART/'funding/MANIFEST.json');modes=[a['mode'] for a in funding['symbols'].values()];registry=r.read(v.PRIOR/'MINI_ALPHA_REGISTRY.json');prior=list(registry['entries'])
    d={'results':result,'verification':check,'inputs':inputs,'membership':r.read(ART/'MEMBERSHIP_CORRECTION.json'),'sensitivity':sens,'tests':tests,'registry_previous_entries':len(prior),
       'funding_acquisition':{'reused':modes.count('reuse_verified'),'new_rest':modes.count('new_official_download'),'archive_recovered':modes.count('official_archive_mark_recovery')},
       'decision_vi':'**Chưa duyệt Fibo Trend Short thành chiến lược giao dịch thật.** Kết quả cải thiện trên vũ trụ đầy đủ hơn, nhưng chưa chứng minh lợi thế ổn định sau chi phí stress và chưa có OOS thời gian mới hoàn toàn.',
       'interpretation_vi':'Đây là lợi nhuận NAV danh mục sau phí, trượt giá và funding lịch sử. Chính sách tín hiệu, thang TP và giới hạn rủi ro đã khóa từ trước; không chọn tham số mới theo kết quả vừa thấy.',
       'portfolio_semantics_vi':'Giữ cách đánh giá đã đăng ký: trạng thái danh mục được đặt lại đầu mỗi năm, ngừng mở lệnh trong 5 ngày cuối năm, rồi nối NAV theo vốn cuối năm trước. Khối lượng của vị thế đang mở được giữ cố định; chi phí và funding đi vào vốn trước khi xét lệnh tiếp theo. Vì vậy số lệnh giữa hai kịch bản chi phí có thể khác nhau.',
       'universe_interpretation_vi':'Nguồn dữ liệu mở rộng từ 250 lên 637 mã, trong đó 244 mã từng nằm trong danh sách đủ điều kiện sau sửa vòng đời hợp đồng. Cải thiện so với bộ cũ đến từ phạm vi dữ liệu và danh sách theo thời điểm; riêng bốn thay thế thành viên tháng ở v4.0.15 không làm đổi ứng viên so với v4.0.14. Không quy cải thiện lợi nhuận cho một thay đổi không làm đổi giao dịch.',
       'inference_vi':'Dùng lưới thứ Hai chung, giữ các đoạn tuần ở đầu/cuối kỳ; bootstrap vòng theo khối 4 tuần, 10.000 mẫu. Cả CI tuyệt đối lẫn CI chênh lệch đều chứa 0. Chỉ tiêu weekly_ci cũ vẫn được giữ để đối chiếu, nhưng quyết định dùng calendar_weekly_ci95 đã đăng ký trước; không chọn cách chia tuần cho kết quả thuận lợi hơn. Các khoảng tin cậy chưa điều chỉnh toàn bộ lịch sử thử nghiệm chiến lược.',
       'oos_vi':'2024–2025 là phần đánh giá theo thời gian hồi cứu, đã được sử dụng trong các vòng nghiên cứu trước. Nó không phải OOS chưa từng được nhìn thấy. Mở rộng coin hoặc chia lại dữ liệu đến 2025 không xóa việc sử dụng trước đó. Yêu cầu OOS mới, đáng tin cậy vẫn chưa được thỏa mãn; toàn bộ quan sát thị trường của lần chạy này nằm trước năm 2026.',
       'cost_vi':'Tính phí và trượt giá cho từng lần khớp, kể cả thoát từng phần; không giảm phí BNB. Funding có dấu: short nhận khi rate dương và trả khi rate âm, trên khối lượng còn mở tại sự kiện. Không mặc định funding thiếu bằng 0.',
       'sensitivity_vi':'Đã đăng ký trước khi xem kết quả: giảm mark proxy khi short nhận funding, tăng khi phải trả, ở mức 1% và 5%. Mỗi trường hợp chạy lại cả quy mô vị thế, hạn mức, phí, funding và chấp nhận lệnh. Đây là kịch bản giả định bất lợi, không phải biên sai số đã được đo. Giá thanh toán API giữ nguyên; độ nhạy không thay thế dữ liệu chính xác.',
       'execution_limits_vi':'Giá khớp vẫn là mô hình từ nến 5 phút với thứ tự stop/TP bảo thủ; chưa có kiểm chứng sổ lệnh, độ sâu, độ trễ hay thanh lý nội nến. Nến volume bằng 0 trong thời gian giữ được ghi rõ; không có ứng viên chính vào hoặc thoát trên nến volume bằng 0, thiếu nến hay bị cắt trước hạn. Lịch sự kiện được kiểm tra theo các trường hợp đã nêu, chưa phải cơ sở dữ liệu đầy đủ mọi sự kiện của sàn.',
       'next_decision_vi':'Giữ chính sách hiện tại làm bản tham chiếu nghiên cứu, chưa chuyển sang giao dịch thật hoặc ghi wiki là OK. Bước kiểm định tiếp theo cần đo phần đóng góp riêng của tín hiệu Fibo so với đối chứng đơn giản trên cùng vũ trụ, giữ nguyên chi phí và quy tắc chọn mẫu trước khi xem kết quả. Chỉ ghi nhận alpha nếu có bằng chứng vượt đối chứng và xác nhận OOS phù hợp; không tiếp tục quét tham số chỉ để làm đẹp lịch sử.'}
    r.save(ART/'REPORT_DATA.json',d);text=render(r.read(ART/'REPORT_DATA.json'));(ART/'REPORT.md').write_text(text,encoding='utf8');assert (ART/'REPORT.md').read_text(encoding='utf8')==render(r.read(ART/'REPORT_DATA.json'))
    r.save(ART/'REPORT_CONSISTENCY.json',{'all_passed':True,'method':'Exact deterministic rendering from JSON and UTF8 readback','report_sha256':r.sha(ART/'REPORT.md'),'report_data_sha256':r.sha(ART/'REPORT_DATA.json')})
    registry['entries'].append({'id':'MA415-U1','type':'expanded_universe_fixed_policy_comparison','usable_as_proven_alpha':False,'fresh_oos':False,
        'hypothesis_vi':'Danh sách coin dựa trên lịch sử đầy đủ hơn có thể cải thiện khả năng khai thác phía short; điểm ước lượng cần được so với đối chứng và độ bất định.',
        'status':'POINT_ESTIMATES_IMPROVED_CONFIDENCE_INTERVALS_INCLUDE_ZERO_FULL_PERIOD_STRESS_NEGATIVE',
        'primary':result['periods']['retrospective_oos_2024_2025'],'full_history':result['periods']['all_2020_2025'],
        'paired_comparisons':result['paired_comparisons'],'results_sha256':r.sha(ART/'RESULTS.json'),'sensitivity_results_sha256':r.sha(sensitivity.OUT/'RESULTS.json')})
    assert registry['entries'][:-1]==prior;registry['source_registry_sha256']=r.sha(v.PRIOR/'MINI_ALPHA_REGISTRY.json');registry['status']='EXPANDED_UNIVERSE_ECONOMIC_EVIDENCE_ADDED';r.save(ART/'MINI_ALPHA_REGISTRY.json',registry)
    r.save(ART/'NEXT_CONFIRMATION_PROTOCOL.json',{'registered_at_utc':datetime.now(timezone.utc).isoformat(),'primary_question':'Does the frozen Fibo entry add value relative to simple matched short entries in the same expanded PIT universe?',
        'scope':'Port the already registered positive-momentum matched24h experiment of v411 to corrected pre2026 universe; same sample cadence, positivity, matching features, calipers and minimum controls. Freeze before new matched outcomes.',
        'restrictions':'No outcome-driven threshold changes, no winning-symbol filters, both per-fill costs, historical signed funding, matched observation completeness disclosed without favorable rematching.',
        'interpretation':'Incremental entry diagnostic, not portfolio NAV or clean temporal OOS. New universe has now been economically observed; disclose selection history.',
        'oos_requirement':'Remains open. Do not call reused2020..2025 a fresh holdout. Prospective evidence would require genuinely unobserved data under an agreed scope.',
        'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    r.save(ART/'GOAL_REQUIREMENTS_AUDIT.json',{'market_observations_through2025':'VERIFIED','full_universe_lifecycle_membership':'KNOWN_EVENTS_CORRECTED_NO_STALE_MONTHLY_MEMBERS',
        'costs_per_fill_and_partial_exits':'VERIFIED_TWO_SCENARIOS','historical_funding_rates':'181_SYMBOLS_VERIFIED','exact_funding_marks':'EXACT_ACCEPTED2024_2025_4569_UNIQUE_OLDER_EVENTS_STILL_PROXY',
        'economic_accounting':'12_BASE_AND24_SENSITIVITY_NODES_VERIFIED','stress_economic_edge':'FULL2020_2025_NEGATIVE','statistical_edge':'INTERVALS_INCLUDE_ZERO',
        'fresh_temporal_oos':'NOT_ESTABLISHED','evidence_registry_entries':len(registry['entries']),'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    r.save(ART/'PROGRESS.json',{'stage':'expanded_universe_dual_cost_funding_results_verified','goal_complete':False,'next_action':'Follow NEXT_CONFIRMATION_PROTOCOL.json; retain negative full-history stress finding.'})
    previous=r.read(v.PRIOR/'CHECKPOINT.json')
    for p,h in previous['files'].items():assert r.sha(v.PRIOR/p)==h,p
    for p,h in previous.get('additional_sources',{}).items():assert r.sha(v.ROOT/p)==h,p
    extras=[Path(__file__),v.ROOT/'scripts/fibo_research/verify_universe_v415.py',Path(b.__file__),Path(resolved.__file__),Path(sensitivity.__file__),Path(recovery.__file__),v.ROOT/'tests/unit/fibo_short/test_funding_archive_v415.py',v.ROOT/'tests/unit/fibo_short/test_funding_sensitivity_v415.py']
    paths=sorted(p for p in ART.rglob('*') if p.is_file() and p.name!='CHECKPOINT.json')
    r.save(ART/'CHECKPOINT.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'files':{str(p.relative_to(ART)):r.sha(p) for p in paths},'file_count':len(paths),
        'additional_sources':{str(p.relative_to(v.ROOT)):r.sha(p) for p in extras},'previous_files_preserved':len(previous['files']),'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    for p,h in r.read(ART/'CHECKPOINT.json')['files'].items():assert r.sha(ART/p)==h,p
    print(f'Full-universe report saved; {len(registry["entries"])} evidence entries; {len(paths)} protected files.',flush=True)


if __name__=='__main__':main()
