"""JSON-driven portfolio exit comparison and retained component evidence."""
from datetime import datetime,timezone
from pathlib import Path
import research_v412 as v

r=v.r;ART=v.ART
NAMES={'original_elite_ladder':'Thang TP hiện tại','elite_initial_stop_only':'Chỉ giữ stop ban đầu','elite_full_tp1':'Thoát toàn bộ tại TP1'}
PERIODS={'reference_2020_2022':'2020–2022 tham chiếu','validation_2023':'2023 kiểm tra','retrospective_2024_2025':'2024–2025 hồi cứu','all_2020_2025':'Toàn bộ 2020–2025'}
COSTS={'standard_vip6':'Chuẩn VIP6','stress_regular':'Stress Regular'}


def ci_text(stat):
    low,high=stat['ci_pct'];return f'[{low:+.4f}; {high:+.4f}]'


def findings(result):
    primary=result['comparisons']['retrospective_2024_2025']
    intervals=[primary[s][a]['paired_calendar_weekly_interval']['ci_pct'] for s in v.SCENARIOS for a in v.ARMS[1:]]
    stress=result['periods']['retrospective_2024_2025']['stress_regular']
    full=result['comparisons']['all_2020_2025']
    return {
        'primary_all_four_difference_intervals_include_zero':all(lo<=0<=hi for lo,hi in intervals),
        'primary_all_three_stress_returns_negative':all(stress[a]['return_pct']<0 for a in v.ARMS),
        'full_history_original_minus_initial_stop_intervals_positive_both_costs':all(full[s]['elite_initial_stop_only']['paired_calendar_weekly_interval']['ci_pct'][0]>0 for s in v.SCENARIOS),
        'full_history_original_minus_full_tp1_intervals_include_zero_both_costs':all((lambda ci:ci[0]<=0<=ci[1])(full[s]['elite_full_tp1']['paired_calendar_weekly_interval']['ci_pct']) for s in v.SCENARIOS),
        'global_selection_adjusted':False,'fresh_temporal_oos':False,'live_signoff':'NOT_GRANTED'
    }


def render(result,verified,baseline,funding):
    interpretation=findings(result)
    assert all(interpretation[k] for k in interpretation if k.startswith(('primary_','full_history_')))
    lines=['# Vai trò của cách thoát lệnh trong danh mục Fibo', '',
        '**Chưa cấp sign-off chiến lược.** Đã đối chiếu ba cách thoát lệnh trên cùng dòng tín hiệu elite-sniper, giữ nguyên quản trị vốn và tính đầy đủ hai mức chi phí cùng funding. Nhánh gốc tái tạo chính xác kết quả v4.0.9 trước khi đánh giá các nhánh mới.',
        '', '## Điều rút ra từ phép thử', '',
        'Trong giai đoạn chính 2024–2025, cả bốn khoảng tin cậy của chênh lệch giữa các cách thoát đều chứa 0; cả ba nhánh đều có NAV stress âm. Chưa có bằng chứng đủ rõ để thay chính sách thoát hiện tại.',
        '', 'Trên toàn bộ 2020–2025, thang TP hiện tại tốt hơn việc chỉ giữ stop ban đầu ở cả hai mức chi phí, với khoảng tin cậy chênh lệch nằm trên 0. Đây là bằng chứng bổ sung trên lịch sử đã được sử dụng, không phải xác nhận OOS mới. Chênh lệch giữa thang TP hiện tại và thoát hết tại TP1 vẫn có khoảng tin cậy chứa 0 ở cả hai mức chi phí.',
        '', 'Chưa thể tách riêng tác dụng của chốt từng phần và dời stop: nhánh chỉ giữ stop ban đầu thay đổi đồng thời cả hai, cùng thời gian chiếm vốn và tập lệnh thực thi. Kết quả được lưu như bằng chứng về chính sách thoát tổng thể.',
        '', '## Thiết kế được giữ cố định', '',
        '| Nhánh | Cách thoát |','|---|---|',
        '| Thang TP hiện tại | Chốt 50% / 30% / 20%, giữ nguyên các bước dời stop |',
        '| Chỉ giữ stop ban đầu | Không chốt TP hay dời stop; thoát ở stop ban đầu hoặc hết thời gian giữ |',
        '| Thoát toàn bộ tại TP1 | Thoát hết tại TP1 hoặc stop ban đầu, nếu chưa chạm thì hết thời gian giữ |',
        '', 'Thời gian giữ tối đa vẫn là 72 giờ với tín hiệu H4 và 120 giờ với tín hiệu D1. Tín hiệu, thang điểm, vũ trụ theo từng tháng, độ trễ vào 5 phút, mức rủi ro 0,5% NAV mỗi lệnh, trần danh nghĩa 20% mỗi lệnh, giới hạn 5 vị thế, tổng danh nghĩa và tổng rủi ro danh mục đều giữ nguyên. Stop được ưu tiên khi cùng nến chạm stop và TP; gap bất lợi được tính vào giá khớp.',
        '', 'Chi phí **mỗi lần khớp**, kể cả chốt từng phần: bản chuẩn VIP6 là phí taker 2,5 bps cộng trượt giá 10 bps; bản stress Regular là 5 bps cộng 50 bps. Chưa giảm phí BNB. Funding dùng mức settlement lịch sử, dấu thu/chi của vị thế short và khối lượng còn mở tại từng timestamp.',
        '', 'Danh mục bắt đầu bằng tiền mặt mỗi đầu năm, không nhận lệnh trong 5 ngày cuối năm. Các đường NAV năm được nối bằng vốn cuối năm trước; đây không phải mô phỏng giữ nguyên vị thế xuyên giao thừa. Giá trị khởi đầu là 100. Dữ liệu thị trường chỉ đến hết 2025.',
        '', '## Kết quả danh mục', '',
        '| Giai đoạn | Chi phí | Cách thoát | NAV ròng | MaxDD | Lệnh | Khoảng tin cậy 95% của lợi nhuận tuần |',
        '|---|---|---|---:|---:|---:|---|']
    for period,title in PERIODS.items():
        for scenario,cost in COSTS.items():
            for arm,name in NAMES.items():
                a=result['periods'][period][scenario][arm]
                lines.append(f"| {title} | {cost} | {name} | {a['return_pct']:+.2f}% | {a['max_dd_pct']:.2f}% | {a['trades']} | {ci_text(a['calendar_weekly_ci95'])}% |")
    lines += ['', 'Các khoảng tin cậy tuần sử dụng chung mốc thứ Hai và hai biên giai đoạn, giữ cả tuần không giao dịch và các khoảng ngắn ở biên. Không suy ra lợi nhuận kỳ vọng dương chỉ từ NAV tổng dương.',
        '', '## So sánh cách thoát trong giai đoạn 2024–2025', '',
        'Chênh lệch dưới đây bằng **thang TP hiện tại trừ phương án thay thế**, tính bằng điểm phần trăm lợi nhuận tuần. Khoảng hoàn toàn âm ủng hộ phương án thay thế; khoảng hoàn toàn dương ủng hộ thang TP hiện tại.',
        '', '| Chi phí | Phương án thay thế | Chênh lệch tuần trung bình | Khoảng tin cậy 97,5% |','|---|---|---:|---|']
    for scenario,cost in COSTS.items():
        for arm in v.ARMS[1:]:
            a=result['comparisons']['retrospective_2024_2025'][scenario][arm]['paired_calendar_weekly_interval']
            lines.append(f"| {cost} | {NAMES[arm]} | {a['mean_weekly_pct']:+.4f}% | {ci_text(a)}% |")
    lines += ['', 'Mức 97,5% điều chỉnh Bonferroni cho hai phép so sánh đã đăng ký trong từng kịch bản chi phí, với 10.000 lượt bootstrap theo khối 4 tuần, seed 412. Điều này không điều chỉnh toàn bộ các lần thử chiến lược trước đây; hai kịch bản chi phí đều được công bố.',
        '', '## Thay đổi lệnh được nhận', '',
        'Cách thoát ảnh hưởng thời gian chiếm vốn, wave và thời gian nghỉ, nên cùng dòng tín hiệu có thể dẫn đến tập lệnh thực thi khác nhau. Bảng sau mô tả ảnh hưởng trong 2024–2025; đây là so sánh toàn bộ chính sách thoát và tương tác danh mục, không phải chỉ đổi giá thoát trên một tập lệnh đã chọn sẵn.',
        '', '| Chi phí | Phương án | Chung với nhánh gốc | Chỉ nhánh gốc nhận | Chỉ phương án nhận |','|---|---|---:|---:|---:|']
    for scenario,cost in COSTS.items():
        for arm in v.ARMS[1:]:
            a=result['admission_changes']['retrospective_2024_2025'][scenario][arm]
            lines.append(f"| {cost} | {NAMES[arm]} | {a['shared_with_original']} | {a['only_original']} | {a['only_alternative']} |")
    lines += ['', '## Nguồn lợi nhuận và chi phí trong 2024–2025', '',
        'Các thành phần được tính trên NAV ban đầu 100 và nối theo vốn mỗi năm: lợi nhuận giá trừ phí, trừ trượt giá, cộng funding bằng lợi nhuận ròng.',
        '', '| Chi phí | Cách thoát | Do giá | Phí | Trượt giá | Funding | Ròng |','|---|---|---:|---:|---:|---:|---:|']
    for scenario,cost in COSTS.items():
        for arm,name in NAMES.items():
            a=result['periods']['retrospective_2024_2025'][scenario][arm]
            lines.append(f"| {cost} | {name} | {a['gross_reference_pnl_pct']:+.2f}% | {a['fees_pct']:.2f}% | {a['slippage_pct']:.2f}% | {a['funding_pct']:+.2f}% | {a['return_pct']:+.2f}% |")
    lines += ['', '## Kết quả từng năm', '',
        '| Năm | Cách thoát | NAV chuẩn | DD chuẩn | Lệnh chuẩn | NAV stress | DD stress | Lệnh stress |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for year in range(2020,2026):
        for arm,name in NAMES.items():
            a=result['annual'][str(year)][arm]['standard_vip6'];b=result['annual'][str(year)][arm]['stress_regular']
            lines.append(f"| {year} | {name} | {a['return_pct']:+.2f}% | {a['max_dd_pct']:.2f}% | {a['trades']} | {b['return_pct']:+.2f}% | {b['max_dd_pct']:.2f}% | {b['trades']} |")
    lines += ['', '## Kiểm chứng và giới hạn dữ liệu', '',
        f"Nhánh gốc khớp hoàn toàn {baseline['nodes_exactly_equal']} tổ hợp năm–chi phí của v4.0.9: chỉ tiêu, đường NAV, từng giao dịch, lần khớp và funding. {baseline['overlapping_funding_records_exactly_equal']:,} bản ghi funding trùng phạm vi cũng khớp nguồn cũ.",
        '', f"Đã dùng lại dữ liệu funding đủ phạm vi cho {funding['reused_symbols']} mã và tải bổ sung cho {funding['newly_acquired_symbols']} mã. Mức funding được lấy từ lịch sử chính thức; giá mark settlement thiếu vẫn dùng giá mở cửa nến mark có công bố. Danh sách dòng tiền cần xác minh giá chính xác được giữ trong EXACT_MARK_DATA_REQUEST.json.",
        '', f"{verified['tests']['tests']} kiểm thử đạt. Đã đối chiếu {verified['scenario_nodes']} tổ hợp danh mục, {verified['scenario_trade_records']:,} bản ghi giao dịch, {verified['fill_groups']:,} nhóm khớp và {verified['funding_payments']:,} khoản funding. Đã kiểm tra lại vốn trước mỗi lần vào, wave, thời gian nghỉ và các trần vị thế cho {verified['entry_cap_and_equity_checks']:,} lần nhận lệnh. Số bản ghi có lặp giữa các nhánh và kịch bản, không phải số quan sát độc lập.",
        '', ('Không có khoảng trống nến thực thi trên các đường giao dịch được nhận trong phép thử.' if verified['complete_execution_coverage'] else f"Có {len(verified['accepted_execution_issues'])} bản ghi lệnh được nhận gặp khoảng trống dữ liệu. Không loại các lệnh này theo kết quả tương lai; các kết quả liên quan chưa đủ điều kiện xác nhận chất lượng thực thi."),
        '', 'Mô hình xác định thực thi và thứ tự funding theo nến 5 phút; chưa tái dựng từng tick hay độ trễ thanh toán thực tế. Phí và trượt giá là các giả định đã thống nhất. Vũ trụ dựa trên các tệp sẵn có vẫn có nguy cơ thiên lệch do thiếu mã đã hủy niêm yết.',
        '', '## Quyết định nghiên cứu', '',
        'Các nhánh, hai phép so sánh và cách tính chi phí đã được khóa trước khi chạy nhánh mới. Tuy nhiên, họ chiến lược và lịch sử đến 2025 đã được khảo sát ở các vòng trước; giai đoạn 2024–2025 là đánh giá hồi cứu, không phải OOS mới chưa từng dùng. Một cách thoát tốt hơn cách khác chỉ là bằng chứng về thành phần chiến lược, chưa tự chứng minh alpha sinh lời.',
        '', '**Tiếp tục nghiên cứu; chưa duyệt giao dịch thật hoặc cập nhật wiki thành OK.** Mọi kết quả đều được giữ trong nhật ký mini-alpha; không nâng một nhánh chỉ vì nó ít thua hơn hay có NAV dương trong một giai đoạn được chọn sau.',
        '', 'Kiểm kê riêng phần metadata phát hiện 383 mã có lịch sử giao với 2020–2025 nhưng chưa nằm trong bộ 250 mã của v4.0.8; trong đó 143 mã có quan sát trước 2024. Chưa đọc giá hay dùng các mã bổ sung trong kết quả của vòng này. NEXT_UNIVERSE_AUDIT_PROTOCOL.json chốt bước đối chiếu nguồn, khoảng trống và vũ trụ theo thời điểm trước khi đánh giá mở rộng. Kiểm kê này chưa chứng nhận dữ liệu đầy đủ hoặc OOS mới.',
        '', 'Nguồn phương pháp chi phí và dữ liệu: [Biểu phí Binance Futures](https://www.binance.com/en/fee/futureFee), [Lịch sử funding Binance](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History).']
    return '\n'.join(lines)+'\n'


def main():
    v.verify_sources();result=r.read(ART/'RESULTS.json');verified=r.read(ART/'INDEPENDENT_VERIFICATION.json');baseline=r.read(ART/'BASELINE_RECONCILIATION.json');funding=r.read(ART/'funding/MANIFEST.json')
    assert verified['all_accounting_checks_passed'] and verified['results_sha256']==r.sha(ART/'RESULTS.json')
    text=render(result,verified,baseline,funding);(ART/'REPORT.md').write_text(text,encoding='utf8')
    assert (ART/'REPORT.md').read_text(encoding='utf8')==render(r.read(ART/'RESULTS.json'),r.read(ART/'INDEPENDENT_VERIFICATION.json'),r.read(ART/'BASELINE_RECONCILIATION.json'),r.read(ART/'funding/MANIFEST.json'))
    r.save(ART/'REPORT_CONSISTENCY.json',{'all_passed':True,'method':'Exact deterministic rerender and readback from JSON',
        'results_sha256':r.sha(ART/'RESULTS.json'),'report_sha256':r.sha(ART/'REPORT.md')})
    r.save(ART/'INTERPRETATION.json',{'results_sha256':r.sha(ART/'RESULTS.json'),**findings(result)})
    registry=r.read(v.PRIOR/'MINI_ALPHA_REGISTRY.json')
    old_count=len(registry['entries']);registry['status']='EXIT_POLICY_COMPONENT_EVIDENCE_RECORDED';registry['source_registry_sha256']=r.sha(v.PRIOR/'MINI_ALPHA_REGISTRY.json')
    for i,arm in enumerate(v.ARMS[1:],1):
        primary={s:result['comparisons']['retrospective_2024_2025'][s][arm] for s in v.SCENARIOS}
        registry['entries'].append({'id':f'MA412-Q3-{i}','hypothesis_vi':f'Ảnh hưởng của {NAMES[arm].lower()} so với thang TP hiện tại',
            'type':'exit_policy_and_portfolio_interaction_not_standalone_alpha','status':'COMPONENT_EVIDENCE_RECORDED',
            'usable_as_proven_alpha':False,'fresh_oos':False,'primary_comparisons':primary,
            'interpretation':findings(result),
            'comparisons_by_period':{p:{s:result['comparisons'][p][s][arm] for s in v.SCENARIOS} for p in result['periods']},
            'period_evidence':{p:{s:{a:result['periods'][p][s][a] for a in (v.ARMS[0],arm)} for s in v.SCENARIOS} for p in result['periods']},
            'admission_changes':{p:{s:result['admission_changes'][p][s][arm] for s in v.SCENARIOS} for p in result['periods']},
            'results_sha256':r.sha(ART/'RESULTS.json')})
    r.save(ART/'MINI_ALPHA_REGISTRY.json',registry)
    assert registry['entries'][:old_count]==r.read(v.PRIOR/'MINI_ALPHA_REGISTRY.json')['entries']
    r.save(ART/'PROGRESS.json',{'stage':'exit_policy_ablation_verified_and_documented','goal_complete':False,'fresh_oos':False,
        'complete_execution_coverage':verified['complete_execution_coverage'],'data_ceiling':'2025-12-31','live_signoff':'NOT_GRANTED',
        'next_action':'Audit the additional historical data and frozen PIT universe scope under NEXT_UNIVERSE_AUDIT_PROTOCOL.json before further signal tuning. Keep original elite-sniper ladder as the preregistered primary portfolio for expanded-universe replication.'})
    paths=sorted(p for p in ART.rglob('*') if p.is_file() and p.name!='CHECKPOINT.json')
    r.save(ART/'CHECKPOINT.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'files':{str(p.relative_to(ART)):r.sha(p) for p in paths},
        'file_count':len(paths),'additional_sources':{str(Path(__file__).relative_to(r.ROOT)):r.sha(__file__)},'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    print(f'Exit-policy report and {len(registry["entries"])} evidence entries saved.',flush=True)


if __name__=='__main__':main()
