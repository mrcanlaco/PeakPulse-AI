"""Publish all predeclared cost points, with no selected winning cost assumption."""
from datetime import datetime,timezone
from pathlib import Path
import research_v418 as v
r=v.r;ART=v.ART


def render(d):
    result=d['results'];check=d['verification'];lines=['# Khả năng chịu chi phí — v4.0.18','',
        '**Chưa duyệt chiến lược giao dịch thật.** Đây là kiểm tra độ nhạy chi phí của chính sách đã khóa, không phải tối ưu để chọn một mức phí cho kết quả thuận lợi.',
        '', 'Mỗi tổ hợp được chạy lại đầy đủ việc nhận lệnh, khối lượng, hạn mức danh mục, phí, trượt giá và funding. Giữ nguyên tín hiệu elite-sniper, TP 50%–30%–20%, vốn/rủi ro và danh sách coin theo thời điểm của v4.0.15.',
        '', '| Phí mỗi khớp | Trượt giá mỗi khớp | NAV 2024–2025 | MaxDD | NAV 2020–2025 | MaxDD |','|---|---:|---:|---:|---:|---:|']
    for name,cost in result['scenarios'].items():
        a=result['periods']['retrospective_oos_2024_2025'][name];b=result['periods']['all_2020_2025'][name]
        fee='VIP6 2,5 bps' if cost['fee_bps']==2.5 else 'Regular 5 bps';suffix=' **chuẩn**' if name=='vip6_slip10' else ' **stress**' if name=='regular_slip50' else ''
        lines.append(f"| {fee}{suffix} | {cost['slippage_bps']:g} bps | {a['return_pct']:+.2f}% | {a['max_dd_pct']:.2f}% | {b['return_pct']:+.2f}% | {b['max_dd_pct']:.2f}% |")
    lines += ['', 'Đây là NAV sau mọi chi phí và funding có dấu, không phải tổng lợi nhuận các lệnh. Phí/slippage áp dụng từng lần khớp, kể cả chốt từng phần, không giảm phí BNB. Trạng thái danh mục đặt lại mỗi năm và ngừng mở lệnh trong 5 ngày cuối năm, sau đó nối NAV theo vốn cuối năm trước; giữ nguyên quy ước của bản tham chiếu.',
        '', '## Các điểm đổi dấu đã quan sát','']
    for period,title in [('retrospective_oos_2024_2025','2024–2025'),('all_2020_2025','2020–2025')]:
        for tier,label in [('vip6','VIP6'),('regular','Regular')]:
            a=result['sign_diagnostics'][period][tier];changes=a['adjacent_sign_changes']
            if not changes:
                vals=[result['periods'][period][f'{tier}_slip{s}']['return_pct'] for s in (10,20,30,40,50)]
                direction='dương' if all(x>0 for x in vals) else 'không dương'
                lines.append(f'- {title}, {label}: mọi điểm trong lưới 10–50 bps đều {direction}; chưa quan sát điểm đổi dấu trong lưới này.')
            else:
                for p in changes:lines.append(f"- {title}, {label}: từ {p['left_return_pct']:+.2f}% tại {p['left_slippage_bps']:g} bps sang {p['right_return_pct']:+.2f}% tại {p['right_slippage_bps']:g} bps.")
            if not a['point_returns_monotone_nonincreasing']:lines.append(f'  Chuỗi {title}, {label} không giảm đều khi tăng chi phí; thay đổi lệnh được nhận cần được giữ trong diễn giải.')
    lines += ['', '**Không nội suy một mức hòa vốn chính xác.** Các điểm đổi dấu là mô tả kết quả của lưới đã chạy, không phải ngân sách trượt giá được bảo đảm hay lợi thế đã xác nhận thống kê.',
        '', '## Độ bất định của các mức chi phí', '', '| Kịch bản | CI 95% lợi nhuận tuần 2024–2025 | CI 95% lợi nhuận tuần 2020–2025 | Lệnh đổi so với bản chuẩn, toàn kỳ |','|---|---:|---:|---:|']
    for name,cost in result['scenarios'].items():
        a=result['periods']['retrospective_oos_2024_2025'][name]['calendar_weekly_ci95'];b=result['periods']['all_2020_2025'][name]['calendar_weekly_ci95'];n=result['admission_changes']['all_2020_2025'][name]['symmetric_difference']
        lines.append(f"| Phí {cost['fee_bps']:g} / trượt {cost['slippage_bps']:g} bps | [{a['ci_pct'][0]:+.4f}%; {a['ci_pct'][1]:+.4f}%] | [{b['ci_pct'][0]:+.4f}%; {b['ci_pct'][1]:+.4f}%] | {n} |")
    lines += ['', 'Cột lệnh đổi là tổng số lệnh chỉ có ở một trong hai danh sách; không phải chênh lệch số lượng lệnh. Bootstrap vòng theo khối 4 tuần, giữ tuần không có lệnh và các đoạn tuần ở đầu/cuối kỳ, 10.000 mẫu. Các CI chưa điều chỉnh việc kiểm tra nhiều mức chi phí hoặc toàn bộ lịch sử nghiên cứu.',
        '', '## Kiểm chứng và funding', '',
        f"Đã đối chiếu chính xác {check['exact_baseline_nodes']} tổ hợp năm–chi phí của hai bản chuẩn/stress với v4.0.15, gồm cả sổ lệnh và đường NAV. Kiểm tra độc lập toàn bộ {check['nodes']} tổ hợp, {check['scenario_trades']:,} bản ghi giao dịch, {check['fills']:,} nhóm khớp, {check['funding_payments']:,} khoản funding và {check['entry_cap_checks']:,} lần kiểm tra vốn/hạn mức khi vào lệnh. Các số đếm có lặp giữa kịch bản.",
        '',f"Có {check['tests']['tests']} kiểm thử đạt; {check['linked_periods_verified']} tổ hợp giai đoạn–chi phí được tái dựng NAV và CI độc lập. Giữ nguyên {check['previous_files_preserved']} tệp của vòng trước.",
        '',f"Dùng lại bộ funding đã kiểm chứng cho {d['inputs']['funding_symbols']} mã và {d['inputs']['candidates']:,} ứng viên; không cần tải thêm quan sát thị trường. Các khoản funding lịch sử cũ còn dùng mark OPEN thay thế được gắn nhãn. Trong lưới này có {check['proxy_funding_payments']:,} khoản proxy theo kịch bản và {check['exact_mark_unique_events_needed']:,} kỳ riêng biệt cần mark chính xác; đây không phải dữ liệu đã mua.",
        '', '**Giới hạn:** Toàn bộ dữ liệu thị trường kết thúc trước 2026. 2024–2025 đã được nghiên cứu nhiều lần nên là đánh giá hồi cứu, không phải holdout mới. Giá khớp từ nến 5 phút vẫn chưa chứng minh khả năng khớp thật, độ sâu sổ lệnh hoặc độ trễ. Funding API có dấu được giữ nguyên; các mark proxy cũ không được gọi là giá thanh toán chính xác.',
        '', '## Quyết định tiếp theo', '',
        'Giữ nguyên hai chuẩn chi phí người dùng yêu cầu. Một mức trượt giá thấp hơn làm NAV dương không đủ để duyệt chiến lược nếu mức stress chưa đạt. Bước kiểm tra tiếp theo là chạy danh mục liên tục qua ranh giới năm, giữ nguyên chính sách và hai mức chi phí, để tách ảnh hưởng của việc đặt lại trạng thái và embargo cuối năm trong báo cáo hiện tại.',
        '',f"Nhật ký hiện có {d['registry_entries']} mục, gồm kết quả độ nhạy chi phí này. Không gắn nhãn alpha đã chứng minh; yêu cầu OOS phù hợp vẫn còn mở."]
    return '\n'.join(lines)+'\n'


def main():
    v.verify_sources();full=r.read(ART/'RESULTS.json');check=r.read(ART/'INDEPENDENT_VERIFICATION.json');assert check['all_passed'] and check['results_sha256']==r.sha(ART/'RESULTS.json')
    result={k:full[k] for k in ('version','periods','scenarios','sign_diagnostics','admission_changes','fresh_oos','post_2025_observations')}
    registry=r.read(v.PRIOR/'MINI_ALPHA_REGISTRY.json');old=list(registry['entries'])
    registry['entries'].append({'id':'MA418-C1','type':'fixed_policy_cost_frontier','status':'EXECUTION_COST_SENSITIVITY_NOT_PROVEN_ALPHA','usable_as_proven_alpha':False,'fresh_oos':False,
        'sign_diagnostics':result['sign_diagnostics'],'all_grid_summaries':result['periods'],'results_sha256':r.sha(ART/'RESULTS.json')})
    assert registry['entries'][:-1]==old;registry.update(status='COST_FRONTIER_VERIFIED',last_completed_stage='fixed_policy_cost_frontier',source_registry_sha256=r.sha(v.PRIOR/'MINI_ALPHA_REGISTRY.json'),
        parent_registry={'path':str(v.PRIOR/'MINI_ALPHA_REGISTRY.json'),'sha256':r.sha(v.PRIOR/'MINI_ALPHA_REGISTRY.json')},current_results={'path':str(ART/'RESULTS.json'),'sha256':r.sha(ART/'RESULTS.json')})
    registry['trial_accounting_v418']={'new_signal_parameters':0,'fixed_cost_conditions':10,'reconciled_old_endpoints':2,'new_cost_conditions':8,'fresh_oos':False};r.save(ART/'MINI_ALPHA_REGISTRY.json',registry)
    d={'results':result,'verification':check,'inputs':r.read(ART/'INPUT_VERIFICATION.json'),'registry_entries':len(registry['entries']),'source_results_sha256':r.sha(ART/'RESULTS.json')}
    r.save(ART/'REPORT_DATA.json',d);(ART/'REPORT.md').write_text(render(r.read(ART/'REPORT_DATA.json')),encoding='utf8')
    assert (ART/'REPORT.md').read_text(encoding='utf8')==render(r.read(ART/'REPORT_DATA.json'))
    reloaded=r.read(ART/'RESULTS.json');assert r.read(ART/'REPORT_DATA.json')['results']=={k:reloaded[k] for k in result}
    r.save(ART/'REPORT_CONSISTENCY.json',{'all_passed':True,'method':'Exact verified JSON projection, deterministic rendering and UTF8 readback',
        'report_sha256':r.sha(ART/'REPORT.md'),'report_data_sha256':r.sha(ART/'REPORT_DATA.json'),'results_sha256':r.sha(ART/'RESULTS.json')})
    r.save(ART/'NEXT_CONTINUOUS_PROTOCOL.json',{'registered_at_utc':datetime.now(timezone.utc).isoformat(),
        'question':'Does the annual-reset/year-end-embargo evaluation materially differ from continuous deployment of the identical fixed policy?',
        'data':'Same corrected v415 membership, engine and all eligible elite_sniper candidates before2026; include eligible2020..2024 year-end candidates removed only by annual evaluation embargo. Keep final five-day embargo before2026 to avoid observing2026 exits.',
        'state':'One portfolio from2020-01-01 to2026-01-01, no intermediate equity, wave or cooldown resets. Apply all caps before wave/cooldown consumption, fixed open quantities and actual signed funding.',
        'costs':{'standard_vip6':v.SCENARIOS['vip6_slip10'],'stress_regular':v.SCENARIOS['regular_slip50']},
        'decomposition':'First replay continuous state with the original7614 annual-eligible candidates to isolate state reset, then continuous state with all eligible candidates to isolate annual embargo. Keep primary full continuous result; report both diagnostics and original linked baseline. No selection of a winning implementation.',
        'funding':'Verify full coverage of every newly included candidate before outcomes; download only missing intervals if practical, retain exact provenance. Do not zero-fill gaps.',
        'statistics':'Report full2020..2025 and2024..2025 marked subperiods on the continuous NAV with carried positions, no fresh reset at2024. Same common Monday4week bootstrap10000 seed412, absolute95percent and paired97.5percent differences vs annual baseline. Historical reuse and multiple testing disclosed.',
        'quality':'Audit every extra candidate path/lifecycle boundary and retain any issue. Freeze implementation before new outcomes. No signal, exit or risk optimization.',
        'fresh_oos':False,'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    r.save(ART/'GOAL_REQUIREMENTS_AUDIT.json',{'only_data_through2025':'VERIFIED','user_standard_and_stress':'EXACT_REPLAY_OF_V415','cost_frontier':'TEN_PREDECLARED_COUPLED_CONDITIONS_VERIFIED',
        'positive_full_history_stress':'NOT_ESTABLISHED','fresh_temporal_oos':'NOT_ESTABLISHED','mini_alpha_log_entries':len(registry['entries']),'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    r.save(ART/'PROGRESS.json',{'stage':'fixed_cost_frontier_verified','next_action':'Follow NEXT_CONTINUOUS_PROTOCOL.json before final research decision.','goal_complete':False})
    prior=r.read(v.PRIOR/'CHECKPOINT.json')
    for path,h in prior['files'].items():assert r.sha(v.PRIOR/path)==h,path
    for path,h in prior['additional_sources'].items():assert r.sha(v.ROOT/path)==h,path
    paths=sorted(p for p in ART.rglob('*') if p.is_file() and p.name!='CHECKPOINT.json');sources=r.read(ART/'SOURCE_MANIFEST.json')['sources'];sources[str(Path(__file__))]=r.sha(__file__)
    r.save(ART/'CHECKPOINT.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'files':{str(p.relative_to(ART)):r.sha(p) for p in paths},'file_count':len(paths),
        'additional_sources':{str(Path(p).relative_to(v.ROOT)):h for p,h in sources.items()},'previous_files_preserved':len(prior['files']),'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    for path,h in r.read(ART/'CHECKPOINT.json')['files'].items():assert r.sha(ART/path)==h,path
    print({'registry_entries':len(registry['entries']),'protected_files':len(paths)},flush=True)


if __name__=='__main__':main()
