"""Cash-decomposed positive-momentum matched study; JSON-driven reporting."""
from datetime import datetime,timezone
import gzip
import json
from pathlib import Path
import numpy as np
import research_v411 as v

r=v.r;ART=v.ART
SPLITS={'development_2020_2022':('2020-01-01','2023-01-01'),'validation_2023':('2023-01-01','2024-01-01'),
    'retrospective_oos_2024_2025':('2024-01-01','2026-01-01'),'all_2020_2025':('2020-01-01','2026-01-01')}
LABELS={'development_2020_2022':'2020–2022 tham chiếu','validation_2023':'2023 kiểm tra','retrospective_oos_2024_2025':'2024–2025 OOS hồi cứu','all_2020_2025':'Toàn bộ 2020–2025'}
COSTS={'standard_vip6':'Chuẩn VIP6','stress_regular':'Stress Regular'}


def decomposition(result):
    with gzip.open(ART/'EVENT_LEDGER.json.gz','rt',encoding='utf8') as fh:ledger=json.load(fh)
    output={};fields=['gross_reference_return','fees','slippage','funding','net_return']
    for scenario,rows in ledger['scenarios'].items():
        output[scenario]={}
        for name,(start,end) in SPLITS.items():
            selected=[p for p in rows if r.utc(start).timestamp()<=p['entry_ts']<r.utc(end).timestamp()]
            if not selected:output[scenario][name]={'available':False,'pairs':0};continue
            leg={side:{k:float(np.mean([p[side][k] for p in selected])*10000) for k in fields} for side in ('treated','control')}
            difference={k:leg['treated'][k]-leg['control'][k] for k in fields}
            assert abs(difference['gross_reference_return']-difference['fees']-difference['slippage']+difference['funding']-difference['net_return'])<1e-8
            assert abs(difference['net_return']-result['results'][scenario]['splits'][name]['mean_difference_bps'])<1e-8
            events=[event for p in selected for side in ('treated','control') for event in p[side]['funding_events']]
            proxies=[event for event in events if event['price_source']!='funding_api_settlement_mark']
            proxy_abs=sum(abs(event['cashflow']) for event in proxies)
            output[scenario][name]={'available':True,'pairs':len(selected),'means_bps':leg,'paired_differences_bps':difference,
                'funding_event_records':len(events),'proxy_funding_event_records':len(proxies),'exact_mark_funding_event_records':len(events)-len(proxies),
                'hypothetical_proxy_mark_relative_error_pct':1.,'worst_case_abs_paired_mean_error_bps':.01*proxy_abs/len(selected)*10000}
    return {'scenarios':output,'unit':'bps per event on initial reference notional; not portfolio NAV',
        'sensitivity_scope':'Analytical bound conditional on assumed +/-1% proxy mark error; not a measured error or certification. Applies to fixed unit-quantity event study only.',
        'results_sha256':r.sha(ART/'RESULTS.json'),'ledger_sha256':r.sha(ART/'EVENT_LEDGER.json.gz'),
        'report_method_sha256':r.sha(ART/'REPORT_METHOD.json')}


def ci_text(s):
    if s['active_weeks']<2:return 'Không suy luận: dưới 2 tuần có mẫu'
    lo,hi=s['paired_difference_ci95_bps'];return f'[{lo:+.2f}; {hi:+.2f}]'


def rows_for_statistics(result):
    lines=[]
    for label,title in LABELS.items():
        for name,cost in COSTS.items():
            s=result['results'][name]['splits'][label]
            if not s['available']:lines.append(f'| {title} | {cost} | 0 | — | — | — | — |');continue
            lines.append(f"| {title} | {cost} | {s['pairs']} | {s['mean_fibo_bps']:+.2f} | {s['mean_control_bps']:+.2f} | {s['mean_difference_bps']:+.2f} | {ci_text(s)} |")
    return lines


def render(result,verified,coverage,diag):
    supported=result['incremental_diagnostic_support']
    lines=['# Fibo sau nhịp tăng và lệnh short thông thường','',
        '**Chưa cấp sign-off chiến lược.** '+('Phép thử đạt tiêu chí hỗ trợ chẩn đoán tương đối, nhưng chưa xác nhận alpha có thể giao dịch.' if supported else 'Phép thử chưa đạt tiêu chí xác nhận lợi thế tăng thêm của Fibo so với đối chứng.'),
        '', 'Đây là nghiên cứu ghép cặp trong giai đoạn 2020–2025: Fibo elite-sniper và một mã đối chứng đều đã tăng giá trong 24 giờ trước lệnh, vào cùng lúc, giữ cùng 24 giờ, có đà giá và biến động gần nhau. Mỗi phía có một đơn vị giá trị danh nghĩa ban đầu, khối lượng cố định, một lần vào và một lần ra. Kết quả là lợi nhuận mỗi sự kiện; không phải NAV danh mục có stop/TP, giới hạn vốn hoặc đòn bẩy.',
        '', '## Chi phí và thông tin được sử dụng', '',
        '| Kịch bản | Phí taker mỗi lần khớp | Trượt giá mỗi lần khớp | Funding |','|---|---:|---:|---|',
        '| Chuẩn VIP6 | 2,5 bps | 10 bps | Dòng tiền lịch sử, có ghi nguồn giá mark |',
        '| Stress Regular | 5 bps | 50 bps | Cùng phương pháp |',
        '', 'Phí USDⓈ-M Futures tính trên giá trị khớp sau trượt giá, chưa giảm phí BNB. Mức phí cố định theo giả định nghiên cứu; không khẳng định cấp VIP thực tế của tài khoản hay tái dựng biểu phí từng năm. Quy tắc phí áp dụng cho mọi lần khớp, kể cả thoát từng phần trong bộ máy chiến lược gốc.',
        '', 'Đặc trưng dùng 289 nến đóng liên tiếp để đo đà giá và biến động 24 giờ, không đọc nến tương lai. Vũ trụ đối chứng là top 50 thanh khoản theo từng tháng từ lịch sử trước tháng đó. Cả hai phía phải có đà giá dương; loại mã có tín hiệu elite-sniper cùng thời điểm. Bộ tín hiệu kế thừa kiểm tra gap và điều kiện giá khớp sau 5 phút, nên thông tin lựa chọn được xác định chậm nhất lúc vào lệnh. Không chọn lại đối chứng theo diễn biến sau khi vào.',
        '', '## Khả năng ghép mẫu', '',
        f"Từ {result['sampling']['raw_elite_candidates']:,} ứng viên, quy tắc lấy mẫu theo wave và nghỉ 24 giờ để lại {result['sampling']['sampled_events']:,} sự kiện. Có **{result['matched_pairs']:,} cặp** phù hợp; **{len(result['incomplete_pairs'])} cặp** thiếu dữ liệu thực thi sau khi ghép.",
        '', '| Lý do không ghép | Sự kiện |','|---|---:|']
    reasons={'treated_nonpositive_momentum':'Fibo có đà giá 24 giờ âm hoặc bằng 0','fewer_than_three_positive_controls':'Ít hơn 3 mã đối chứng tăng giá hợp lệ',
        'outside_fixed_caliper':'Không có đối chứng trong giới hạn 0,5 độ lệch chuẩn cho từng đặc trưng','treated_past_feature_missing':'Thiếu nến quá khứ liên tục','degenerate_control_dispersion':'Độ phân tán đối chứng bằng 0'}
    for key,count in result['sampling']['unmatched_reasons'].items():lines.append(f'| {reasons.get(key,key)} | {count:,} |')
    lines += ['', f"Sai lệch chuẩn hóa lớn nhất sau ghép cho đà giá và biến động lần lượt là {', '.join(f'{n:.3f}' for n in result['balance']['max_abs_standardized_difference'])}. Có {result['balance']['unique_control_symbol_times']:,} tổ hợp mã–thời điểm đối chứng khác nhau; các đối chứng dùng lại vẫn được giữ cùng tuần khi bootstrap.",
        '', '## Kết quả theo giai đoạn', '',
        '**Đơn vị: bps lợi nhuận ròng trung bình mỗi sự kiện trên giá trị danh nghĩa ban đầu; 100 bps = 1%.** Chênh lệch dương là Fibo tốt hơn đối chứng. Khoảng tin cậy được tính bằng 10.000 lượt bootstrap ghép cặp theo khối 4 tuần, giữ cả các tuần không có sự kiện.',
        '', '| Giai đoạn | Chi phí | Cặp | Fibo | Đối chứng | Chênh lệch | Khoảng tin cậy 95% của chênh lệch |',
        '|---|---|---:|---:|---:|---:|---|',*rows_for_statistics(result),
        '', '## Kết quả từng năm', '', '| Năm | Chi phí | Cặp | Fibo | Đối chứng | Chênh lệch | Khoảng tin cậy 95% |','|---|---|---:|---:|---:|---:|---|']
    for year in range(2020,2026):
        for name,cost in COSTS.items():
            s=result['results'][name]['annual'][str(year)]
            if not s['available']:lines.append(f'| {year} | {cost} | 0 | — | — | — | — |');continue
            lines.append(f"| {year} | {cost} | {s['pairs']} | {s['mean_fibo_bps']:+.2f} | {s['mean_control_bps']:+.2f} | {s['mean_difference_bps']:+.2f} | {ci_text(s)} |")
    lines += ['', 'Các giai đoạn có ít hơn hai tuần chứa sự kiện không cho phép suy luận bất định từ bootstrap. Khoảng suy biến còn trong JSON chỉ để tái lập phép tính. Các năm ít mẫu được trình bày để mô tả, không dùng chọn năm thắng.',
        '', '## Nguồn lợi nhuận trong giai đoạn 2024–2025', '',
        'Bảng dưới tách chênh lệch Fibo trừ đối chứng. Giá và funding cộng vào lợi nhuận; phí và trượt giá được trừ đi. Tất cả vẫn tính bằng bps mỗi sự kiện.',
        '', '| Chi phí | Chênh lệch do giá | Chênh lệch phí | Chênh lệch trượt giá | Chênh lệch funding | Chênh lệch ròng |','|---|---:|---:|---:|---:|---:|']
    for name,cost in COSTS.items():
        p=diag['scenarios'][name]['retrospective_oos_2024_2025']
        if not p['available']:continue
        d=p['paired_differences_bps']
        lines.append(f"| {cost} | {d['gross_reference_return']:+.3f} | {d['fees']:+.3f} | {d['slippage']:+.3f} | {d['funding']:+.3f} | {d['net_return']:+.3f} |")
    standard=diag['scenarios']['standard_vip6']['retrospective_oos_2024_2025']
    if standard['available']:
        bound=standard['worst_case_abs_paired_mean_error_bps']
        if standard['proxy_funding_event_records']==0:
            lines += ['', f"Trong riêng mẫu 2024–2025, cả {standard['funding_event_records']:,} khoản funding của hai phía đều dùng giá mark settlement từ API, không có khoản dùng giá đại diện. Vì vậy kết quả bất lợi của mẫu này không đến từ phần giá mark đại diện còn thiếu ở lịch sử cũ."]
        else:
            lines += ['', f"Nếu giả định mọi giá mark đại diện có sai số tương đối không quá ±1%, thay đổi lớn nhất của chênh lệch trung bình trong mẫu cố định này là **±{bound:.4f} bps**. Đây là phép đo độ nhạy có điều kiện, không phải bằng chứng rằng sai số thực tế nằm trong ±1%, và không áp dụng trực tiếp cho danh mục thay đổi khối lượng theo NAV."]
    lines += ['', '## Funding và đối chiếu độc lập', '',
        f"Dùng lại dữ liệu đủ phạm vi cho {coverage['reused_symbols']} mã, tải bổ sung {coverage['newly_acquired_symbols']} mã từ Binance. Kiểm tra {verified['funding_snapshot_events_verified']:,} bản ghi trong các tệp funding được dùng; đối chiếu {verified['scenario_leg_outcomes_recomputed']:,} kết quả từng phía và {verified['scenario_funding_payments_recomputed']:,} khoản funding theo các kịch bản. Các số này có lặp giữa các phép tính, không phải số quan sát thị trường độc lập.",
        '', f"Có {verified['nonzero_proxy_events_requiring_exact_mark']:,} thời điểm funding riêng biệt có dòng tiền khác 0 còn dùng giá mở cửa nến mark chính thức trước settlement tối đa 15 giây. Chưa gọi đây là giá tick settlement chính xác. Danh sách cần dữ liệu chính xác nằm trong EXACT_MARK_DATA_REQUEST.json; không bỏ funding thiếu hay tự đặt bằng 0.",
        '', f"{verified['tests']['tests']} kiểm thử đạt, không lỗi và không bỏ qua. Đã tính lại {verified['past_feature_rows_recomputed']:,} dòng đặc trưng, kiểm tra ghép cặp và tính lại tiền từ giá cùng nguồn funding. Giữ nguyên {verified['previous_v409_files_preserved']:,} tệp v4.0.9 và {verified['previous_v410_files_preserved']:,} tệp v4.0.10. Báo cáo được kết xuất và đối chiếu từ JSON.",
        '', '## Kết luận và giới hạn', '',
        'Điều kiện đăng ký trước là tối thiểu 200 cặp đầy đủ trong 2024–2025, không thiếu cặp đã ghép, cận dưới khoảng tin cậy của chênh lệch lớn hơn 0 ở cả hai mức phí. '+('Điều kiện hỗ trợ chẩn đoán này đạt.' if supported else 'Điều kiện hỗ trợ chẩn đoán này chưa đạt.'),
        '', 'Chênh lệch tương đối tốt hơn không đồng nghĩa chiến lược sinh lời. Cần đánh giá riêng lợi nhuận ròng tuyệt đối, danh mục thực thi có stop/TP và chi phí, rồi bằng chứng ngoài mẫu thích hợp. Phép ghép chỉ áp dụng cho nhóm tăng giá có đối chứng tương đồng; không đo riêng giá trị của thời điểm Fibo phát tín hiệu. Những khác biệt chưa quan sát giữa hai mã vẫn có thể ảnh hưởng kết quả.',
        '', 'Giả thuyết nhóm tăng giá được chọn sau vòng kiểm tra nhóm giảm giá; bản thân họ Fibo và lịch sử đến 2025 đã được xem trước đó. OOS ở đây là nhãn thời gian hồi cứu, không phải OOS mới chưa từng dùng. Khoảng tin cậy chưa điều chỉnh cho các lần thử chiến lược trước; thiên lệch vũ trụ tệp còn tồn tại. Không tối ưu lại giới hạn ghép, thời gian giữ hay ngưỡng thành công sau khi xem kết quả.',
        '', '**Trạng thái: chưa hoàn tất chiến lược, chưa duyệt giao dịch thật hoặc cập nhật wiki thành OK.** Bằng chứng thuận lợi và bất lợi đều được ghi trong nhật ký mini-alpha; không mục nào được nâng thành alpha đã chứng minh chỉ từ phép thử này.',
        '', 'Phép thử tiếp theo được ghi trong NEXT_EXIT_ABLATION_PROTOCOL.json: giữ tín hiệu vào lệnh và quản trị vốn, đối chiếu cách thoát lệnh hiện tại với chỉ giữ stop ban đầu và thoát toàn bộ tại TP1. Phép thử này chưa chạy; mục đích là xác định vai trò của cơ chế thoát lệnh trước khi thêm bộ lọc đầu vào.',
        '', 'Kiểm tra bốn mẫu tick mark độc lập và phạm vi gói dữ liệu trả phí được ghi trong FUNDING_DATA_ASSESSMENT.md. Các mẫu này chưa chứng nhận toàn bộ giá settlement và không thay đầu vào của phép thử đã khóa.',
        '', 'Nguồn: [Binance Futures fee table](https://www.binance.com/en/fee/futureFee), [Binance funding history](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History).']
    return '\n'.join(lines)+'\n'


def main():
    v.verify_sources();result=r.read(ART/'RESULTS.json');verified=r.read(ART/'INDEPENDENT_VERIFICATION.json');coverage=r.read(ART/'funding/MANIFEST.json')
    assert verified['all_checks_passed'] and verified['results_sha256']==r.sha(ART/'RESULTS.json')
    diag=decomposition(result);r.save(ART/'DIAGNOSTICS.json',diag)
    text=render(result,verified,coverage,diag);(ART/'REPORT.md').write_text(text,encoding='utf8')
    assert (ART/'REPORT.md').read_text(encoding='utf8')==render(r.read(ART/'RESULTS.json'),r.read(ART/'INDEPENDENT_VERIFICATION.json'),r.read(ART/'funding/MANIFEST.json'),r.read(ART/'DIAGNOSTICS.json'))
    r.save(ART/'REPORT_CONSISTENCY.json',{'all_passed':True,'method':'Deterministic render and exact readback; all component differences reconcile to frozen paired net mean',
        'results_sha256':r.sha(ART/'RESULTS.json'),'diagnostics_sha256':r.sha(ART/'DIAGNOSTICS.json'),'report_sha256':r.sha(ART/'REPORT.md')})
    registry=r.read(v.PRIOR/'MINI_ALPHA_REGISTRY.json');old_count=len(registry['entries'])
    registry['status']='POSITIVE_REVERSAL_MATCHED_DIAGNOSTIC_RECORDED';registry['source_registry_sha256']=r.sha(v.PRIOR/'MINI_ALPHA_REGISTRY.json')
    registry['entries'].append({'id':'MA411-Q2A','hypothesis_vi':'Giá trị tăng thêm của Fibo sau nhịp tăng so với lệnh short sau nhịp tăng thông thường',
        'type':'conditional_cross_sectional_diagnostic_not_standalone_alpha','origin_hypothesis':'MA410-Q2A',
        'status':'INCREMENTAL_DIAGNOSTIC_SUPPORT_ONLY' if result['incremental_diagnostic_support'] else 'INCREMENTAL_SUPPORT_NOT_ESTABLISHED',
        'usable_as_proven_alpha':False,'fresh_oos':False,'adaptive_choice_disclosed':True,
        'evidence':{s:p['splits'] for s,p in result['results'].items()},'matched_pairs':result['matched_pairs'],
        'cash_decomposition':diag['scenarios'],'results_sha256':r.sha(ART/'RESULTS.json'),
        'limitations':['Same-time cross-sectional match does not isolate timing','Positive-momentum common-support subset only','Fixed24h without original stop/TP and portfolio caps','Historical family and periods reused','CI not adjusted for past trials','Some funding marks remain explicit proxies']})
    r.save(ART/'MINI_ALPHA_REGISTRY.json',registry)
    assert registry['entries'][:old_count]==r.read(v.PRIOR/'MINI_ALPHA_REGISTRY.json')['entries']
    r.save(ART/'PROGRESS.json',{'stage':'positive_momentum_diagnostic_verified_and_documented','goal_complete':False,'fresh_oos':False,
        'data_ceiling':'2025-12-31','incremental_diagnostic_support':result['incremental_diagnostic_support'],
        'live_signoff':'NOT_GRANTED','next_action':'Run the separately registered MA411-Q3 exit-policy ablation in a new version. Reconcile original v409 baseline first; do not tune entry filters or relabel reused history as fresh OOS.'})
    r.save(ART/'GOAL_REQUIREMENTS_AUDIT.json',{'goal_complete':False,'live_signoff':'NOT_GRANTED','requirements':[
        {'requirement':'Only use historical observations through2025','status':'VERIFIED_FOR_CURRENT_RUN','evidence':['PROTOCOL.json','INDEPENDENT_VERIFICATION.json'],'post_2025_backtest_observations':0},
        {'requirement':'Evaluate outside sample','status':'INSUFFICIENT_FOR_FRESH_OOS_CLAIM','evidence':['PROTOCOL.json','RESULTS.json'],'reason':'Chronological2024-2025 comparison exists but policy family and history were already inspected.'},
        {'requirement':'Complete and substantiate the strategy','status':'NOT_ESTABLISHED','evidence':['RESULTS.json','DIAGNOSTICS.json'],'reason':'Current matched entry diagnostic fails its registered support gate. It does not replace original portfolio stop/TP evaluation.'},
        {'requirement':'Standard VIP6 and Regular stress costs per fill','status':'VERIFIED','evidence':['TESTS.xml','INDEPENDENT_VERIFICATION.json'],'scenarios':v.x.SCENARIOS},
        {'requirement':'Include historical funding and acquire missing data','status':'RATES_COVERED_MARK_PRICES_PARTIAL','evidence':['funding/MANIFEST.json','EXACT_MARK_DATA_REQUEST.json','FUNDING_DATA_ASSESSMENT.md'],'primary_2024_2025_proxy_payments':diag['scenarios']['standard_vip6']['retrospective_oos_2024_2025']['proxy_funding_event_records']},
        {'requirement':'Keep mini-alpha discoveries and adverse evidence','status':'VERIFIED','evidence':['MINI_ALPHA_REGISTRY.json'],'entries':len(registry['entries']),'prior_entries_preserved':old_count},
        {'requirement':'Preserve prior versions and reconcile report with JSON','status':'VERIFIED','evidence':['INDEPENDENT_VERIFICATION.json','REPORT_CONSISTENCY.json']},
        {'requirement':'Only prepare final OK wiki handover after approval','status':'NOT_YET_ELIGIBLE','reason':'Economic and OOS evidence remains insufficient; no OK message or wiki update has been sent.'}
    ]})
    files=sorted(p for p in ART.rglob('*') if p.is_file() and p.name!='CHECKPOINT.json')
    r.save(ART/'CHECKPOINT.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'files':{str(p.relative_to(ART)):r.sha(p) for p in files},
        'file_count':len(files),'additional_sources':{str(p.relative_to(r.ROOT)):r.sha(p) for p in [Path(__file__),r.ROOT/'scripts/fibo_research/validate_funding_sample_v411.py']},'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    print(f'Positive-momentum report and {len(registry["entries"])}-entry evidence registry saved.',flush=True)


if __name__=='__main__':main()
