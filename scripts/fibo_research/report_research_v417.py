"""Predeclared secondary interaction checks and JSON-only bracket report."""
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import argparse,gzip,json
import numpy as np
import research_v417 as v
import report_research_v416 as oldreport
r=v.r;ART=v.ART


def register():
    v.verify_sources()
    if (ART/'REPORT_METHOD.json').exists():raise FileExistsError('Report method already frozen')
    r.save(ART/'REPORT_METHOD.json',{'registered_at_utc':datetime.now(timezone.utc).isoformat(),'source_sha256':r.sha(__file__),
        'old_report_source_sha256':r.sha(oldreport.__file__),'base_results_existed':(ART/'RESULTS.json').exists(),
        'primary':'Original bracket Fibo-minus-control paired mean as previously registered, unchanged.',
        'secondary':'For the identical complete paired events, calculate each leg bracket-minus24h change and the paired difference-in-differences. Same calendar4week bootstrap10000 seed410,95percent CI. Descriptive secondary mechanism diagnostic, not a new primary gate or fresh OOS; not multiplicity-adjusted.',
        'attribution':'Gross price, fees, slippage, signed funding and holding time. No best symbol/year selection.',
        'old_ledger_sha256':r.sha(v.PRIOR/'EVENT_LEDGER.json.gz')})


def analyze(result,ledger):
    m=r.read(ART/'REPORT_METHOD.json');assert m['source_sha256']==r.sha(__file__) and m['old_report_source_sha256']==r.sha(oldreport.__file__) and not m['base_results_existed']
    assert m['old_ledger_sha256']==r.sha(v.PRIOR/'EVENT_LEDGER.json.gz')
    with gzip.open(v.PRIOR/'EVENT_LEDGER.json.gz','rt',encoding='utf8') as fh:prior=json.load(fh)
    decomposition=oldreport.decomposition(result,ledger);interaction={};holding={}
    for name,rows in ledger['scenarios'].items():
        old={p['id']:p for p in prior['scenarios'][name]};paired=[];holding[name]={}
        for a in rows:
            b=old[a['id']];assert a['entry_ts']==b['entry_ts'] and a['treated_symbol']==b['treated_symbol'] and a['control_symbol']==b['control_symbol']
            paired.append({'id':a['id'],'entry_ts':a['entry_ts'],'treated':{'net_return':a['treated']['net_return']-b['treated']['net_return']},'control':{'net_return':a['control']['net_return']-b['control']['net_return']}})
        interaction[name]={label:v.prev.paired_statistics(paired,*dates) for label,dates in v.SPLITS.items()}
        for label,(start,end) in v.SPLITS.items():
            oldreport.independent_statistics(paired,start,end,interaction[name][label]);chosen=[a for a in rows if r.utc(start).timestamp()<=a['entry_ts']<r.utc(end).timestamp()]
            holding[name][label]={side:{'mean_hours':float(np.mean([a[side]['hold_hours'] for a in chosen])) if chosen else None,
                'exit_reasons':dict(Counter(a[side]['exit_reason'] for a in chosen))} for side in ('treated','control')}
    return {'decomposition':decomposition,'interaction_vs24h':interaction,'holding':holding,
        'results_sha256':r.sha(ART/'RESULTS.json'),'report_method_sha256':r.sha(ART/'REPORT_METHOD.json'),'interaction_inference':'Secondary descriptive, not multiplicity adjusted.'}


def ci(a,key):
    if a['active_weeks']<2:return 'Dưới 2 tuần có mẫu'
    low,high=a[key];return f'[{low:+.2f}; {high:+.2f}]'


def render(d):
    result=d['results'];verification=d['verification'];inputs=d['inputs'];analysis=d['analysis'];fund=d['funding']
    lines=['# Kiểm định TP/SL trên các cặp đã khóa — v4.0.17','',d['decision_vi'],'',
        'Giữ nguyên các cặp Fibo–đối chứng từ v4.0.16. Hai phía dùng cùng khoảng cách stop và ba target theo phần trăm, chốt 50%–30%–20%, cùng quy tắc dời stop và thời hạn tối đa 72/120 giờ theo khung tín hiệu. Đối chứng dùng mức giá được quy đổi từ hình dạng lệnh Fibo, không tạo tín hiệu Fibo riêng.',
        '', '**Đơn vị: bps trên notional ban đầu mỗi sự kiện; 100 bps = 1%. Các lệnh có thể chồng lấn. Đây là phép thử cơ chế, không phải NAV danh mục.**',
        '', '| Giai đoạn / chi phí | Số cặp | Fibo ròng | Đối chứng ròng | Chênh lệch | CI 95% chênh lệch |','|---|---:|---:|---:|---:|---:|']
    labels={'development_2020_2022':'2020–2022','validation_2023':'2023','retrospective_oos_2024_2025':'2024–2025 hồi cứu','all_2020_2025':'2020–2025'}
    for period,label in labels.items():
        for name,title in [('standard_vip6','chuẩn'),('stress_regular','stress')]:
            a=result['results'][name]['splits'][period]
            if not a['available']:lines.append(f'| {label} / {title} | 0 | — | — | — | — |');continue
            lines.append(f"| {label} / {title} | {a['pairs']} | {a['mean_fibo_bps']:+.2f} | {a['mean_control_bps']:+.2f} | {a['mean_difference_bps']:+.2f} | {ci(a,'paired_difference_ci95_bps')} |")
    lines += ['', 'Điều kiện hỗ trợ tương đối đã khóa: ít nhất 200 cặp hoàn chỉnh trong 2024–2025, không có cặp thiếu dữ liệu/lỗi chất lượng trọng yếu và cận dưới CI chênh lệch lớn hơn 0 ở cả hai mức chi phí. Lợi thế tương đối không đủ chứng minh lợi nhuận tuyệt đối có thể giao dịch.',
        '', '## So với giữ cố định 24 giờ', '', 'Bảng dưới dùng cùng từng cặp để so cách thoát TP/SL với giữ 24 giờ. Chênh lệch kép = thay đổi của Fibo trừ thay đổi của đối chứng. Đây là chỉ tiêu cơ chế bổ sung, không thay thế tiêu chí chính.',
        '', '| 2024–2025 | Thay đổi Fibo | Thay đổi đối chứng | Chênh lệch kép | CI 95% chênh lệch kép |','|---|---:|---:|---:|---:|']
    for name,title in [('standard_vip6','Chuẩn'),('stress_regular','Stress')]:
        a=analysis['interaction_vs24h'][name]['retrospective_oos_2024_2025']
        lines.append(f"| {title} | {a['mean_fibo_bps']:+.2f} | {a['mean_control_bps']:+.2f} | {a['mean_difference_bps']:+.2f} | {ci(a,'paired_difference_ci95_bps')} |")
    h=analysis['holding']['standard_vip6']['retrospective_oos_2024_2025']
    lines += ['',f"Thời gian giữ bình quân của Fibo: {h['treated']['mean_hours']:.2f} giờ; đối chứng: {h['control']['mean_hours']:.2f} giờ. Thời gian giữ thay đổi kéo theo funding và mức phơi nhiễm; không diễn giải chênh lệch này thành tỷ suất năm hoặc hiệu quả vốn.",
        '', '## Phân rã chênh lệch Fibo − đối chứng', '', '| 2024–2025 | Do giá | Chênh lệch phí | Chênh lệch trượt giá | Do funding | Ròng |','|---|---:|---:|---:|---:|---:|']
    for name,title in [('standard_vip6','Chuẩn'),('stress_regular','Stress')]:
        a=analysis['decomposition']['scenarios'][name]['retrospective_oos_2024_2025']['difference_bps']
        lines.append(f"| {title} | {a['gross_reference_return']:+.3f} | {a['fees']:+.3f} | {a['slippage']:+.3f} | {a['funding']:+.3f} | {a['net_return']:+.3f} |")
    lines += ['', 'Phí và trượt giá được trừ; funding được cộng có dấu. Bản chuẩn: phí taker VIP6 2,5 bps và trượt giá 10 bps mỗi khớp. Bản stress: phí Regular 5 bps và trượt giá 50 bps mỗi khớp. Tính cho cả vào và mọi lần chốt từng phần, không giảm phí BNB.',
        '', '## Kiểm chứng', '',
        f"Đã chạy lại {inputs['legs_recomputed']:,} đường đi bằng bộ kiểm tra độc lập; {inputs['treated_original_paths_exact']} đường Fibo khớp hoàn toàn với bản gốc. Có {inputs['issues']} lỗi chất lượng trọng yếu và {inputs['holding_zero_volume_legs']} đường đi có nến volume bằng 0 trong thời gian giữ.",
        '',f"Funding cho {inputs['funding_symbols']} mã: dùng lại {fund['reused_symbols']}, tải bổ sung {fund['newly_acquired_symbols']}. Đối chiếu {inputs['funding_snapshot_events_verified']:,} bản ghi với {inputs['raw_responses_verified']:,} phản hồi nguồn và {inputs['archives_verified']} tệp kho tháng.",
        '',f"Kiểm tra trực tiếp {verification['scenario_leg_outcomes']:,} kết quả từng phía, {verification['scenario_fill_groups']:,} nhóm khớp và {verification['scenario_funding_payments']:,} khoản funding ở hai kịch bản; {verification['tests']['tests']} kiểm thử đạt. Những số đếm theo kịch bản có lặp, không phải số quan sát độc lập."]
    a=analysis['decomposition']['scenarios']['standard_vip6']['retrospective_oos_2024_2025']
    lines += ['',f"Mẫu 2024–2025 có {a['funding_payments']:,} khoản funding của hai phía, {a['proxy_payments']} khoản dùng giá mark thay thế. Trong toàn bộ nghiên cứu còn {verification['exact_mark_unique_events_needed']:,} kỳ riêng biệt cần mark chính xác; giá OPEN từ nến mark cũ vẫn được gắn nhãn proxy.",
        '', 'Giá khớp là mô hình từ nến 5 phút. Khi stop và target cùng chạm, xét stop trước; khi TP kéo stop vào phạm vi nến, kiểm tra stop ngay. Funding tại cùng timestamp được tính trước nhóm thoát ở cuối nến, theo quy ước kế toán đã giữ từ v4.0.9. Thứ tự giao dịch thực trong nến, độ sâu sổ lệnh và độ trễ chưa được quan sát.',
        '', '**OOS và lựa chọn giả thuyết:** Chỉ sử dụng dữ liệu đến hết 2025. Toàn bộ giai đoạn và họ chiến lược đã được nghiên cứu; 2024–2025 là đánh giá hồi cứu. Phép thử TP/SL được đề xuất sau khi xem NAV v4.0.15 và kết quả 24 giờ v4.0.16. Bootstrap giữ lịch tuần chung, khối 4 tuần, 10.000 mẫu; chưa điều chỉnh toàn bộ lịch sử thử nghiệm.',
        '', '## Quyết định', '',d['next_vi'],
        '',f"Nhật ký nghiên cứu lưu {d['registry_entries']} mục, gồm kết quả cơ chế mới. Chưa gắn nhãn alpha đã chứng minh và chưa cấp sign-off giao dịch thật."]
    return '\n'.join(lines)+'\n'


def main():
    v.verify_sources();result=r.read(ART/'RESULTS.json');verified=r.read(ART/'INDEPENDENT_VERIFICATION.json');assert verified['all_passed'] and verified['results_sha256']==r.sha(ART/'RESULTS.json')
    with gzip.open(ART/'EVENT_LEDGER.json.gz','rt',encoding='utf8') as fh:ledger=json.load(fh)
    analysis=analyze(result,ledger);r.save(ART/'MECHANISM_ANALYSIS.json',analysis);registry=r.read(v.PRIOR/'MINI_ALPHA_REGISTRY.json');old=list(registry['entries'])
    supported=result['incremental_diagnostic_support'];status='RELATIVE_BRACKET_DIAGNOSTIC_SUPPORTED_NOT_LIVE_ALPHA' if supported else 'MATCHED_ORIGINAL_BRACKET_EDGE_NOT_CONFIRMED'
    registry['entries'].append({'id':'MA417-E1','type':'matched_original_bracket_mechanism','status':status,'usable_as_proven_alpha':False,'fresh_oos':False,
        'primary':{name:a['splits']['retrospective_oos_2024_2025'] for name,a in result['results'].items()},
        'interaction_vs24h_primary':{name:a['retrospective_oos_2024_2025'] for name,a in analysis['interaction_vs24h'].items()},
        'results_sha256':r.sha(ART/'RESULTS.json'),'mechanism_analysis_sha256':r.sha(ART/'MECHANISM_ANALYSIS.json')})
    assert registry['entries'][:-1]==old;registry.update(status=status,last_completed_stage='matched_original_bracket_verified',source_registry_sha256=r.sha(v.PRIOR/'MINI_ALPHA_REGISTRY.json'),
        parent_registry={'path':str(v.PRIOR/'MINI_ALPHA_REGISTRY.json'),'sha256':r.sha(v.PRIOR/'MINI_ALPHA_REGISTRY.json')},current_results={'path':str(ART/'RESULTS.json'),'sha256':r.sha(ART/'RESULTS.json')})
    registry['trial_accounting_v417']={'new_signal_parameters':0,'additional_mechanism_designs':1,'secondary_interaction_comparisons':True,'fresh_oos':False};r.save(ART/'MINI_ALPHA_REGISTRY.json',registry)
    d={'results':result,'verification':verified,'inputs':r.read(ART/'INPUT_VERIFICATION.json'),'funding':r.read(ART/'funding/MANIFEST.json'),'analysis':analysis,'registry_entries':len(registry['entries']),
       'decision_vi':'**Chưa duyệt giao dịch thật.** '+('Phép thử hỗ trợ tương đối cơ chế đã đăng ký; chưa đủ xác nhận lợi nhuận tuyệt đối hoặc OOS mới.' if supported else 'Chưa đạt tiêu chí xác nhận lợi thế Fibo so với đối chứng khi dùng cùng cơ chế TP/SL gốc.'),
       'next_vi':'Giữ bản gốc làm mốc nghiên cứu; không chọn lại coin hoặc tối ưu TP/SL trên các kết quả vừa thấy. Bước kế tiếp cần xác định mức chi phí tối đa mà danh mục hiện tại chịu được bằng một lưới độ nhạy đã khóa, giữ nguyên tín hiệu, quy mô rủi ro và funding. Đây là kiểm tra tính khả thi thực thi, không phải tìm tham số thắng. Yêu cầu OOS phù hợp vẫn còn mở.'}
    r.save(ART/'REPORT_DATA.json',d);(ART/'REPORT.md').write_text(render(r.read(ART/'REPORT_DATA.json')),encoding='utf8');assert (ART/'REPORT.md').read_text(encoding='utf8')==render(r.read(ART/'REPORT_DATA.json'))
    r.save(ART/'REPORT_CONSISTENCY.json',{'all_passed':True,'report_sha256':r.sha(ART/'REPORT.md'),'report_data_sha256':r.sha(ART/'REPORT_DATA.json'),'method':'Deterministic JSON render and UTF8 readback'})
    r.save(ART/'NEXT_COST_FRONTIER_PROTOCOL.json',{'registered_at_utc':datetime.now(timezone.utc).isoformat(),
        'question':'How much modeled per-fill slippage can the unchanged full-universe v415 portfolio tolerate at each fee tier?',
        'grid':'Fee2.5bps and5bps, each crossed with slippage10,20,30,40,50bps per fill. Ten fixed conditions, no signal/exit/sizing optimization.',
        'execution':'Replay full coupled admission, sizing, costs and signed historical funding, not a linear haircut to a fixed accepted ledger. Original elite_sniper risk policy and50/30/20 exits; identical v415 candidates and lifecycle membership.',
        'baseline':'Reconcile fee2.5/slip10 and fee5/slip50 exactly with v415 ledgers/metrics before interpreting new nodes.',
        'statistics':'Same pre2026 annual resets and five-day embargo,2024..2025 primary descriptive and2020..2025 full. Report all grid points, drawdown and calendar bootstrap. Do not interpolate a precise break-even or claim monotonicity because cash-dependent admissions can change.',
        'interpretation':'Execution feasibility and sensitivity only. No new tradable alpha or clean OOS from cost settings. Preserve standard/stress user endpoints prominently.',
        'post_2025_observations':0,'fresh_oos':False,'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    r.save(ART/'GOAL_REQUIREMENTS_AUDIT.json',{'through2025_only':'VERIFIED','user_costs_per_fill':'VERIFIED','historical_signed_funding':'VERIFIED_WITH_OLDER_MARK_PROXIES','matched_bracket_mechanism':status,
        'fresh_temporal_oos':'NOT_ESTABLISHED','positive_full_history_stress_portfolio':'NOT_ESTABLISHED_V415_NEGATIVE','mini_alpha_log_entries':len(registry['entries']),'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    r.save(ART/'PROGRESS.json',{'stage':'matched_original_bracket_verified','next_action':'Follow NEXT_COST_FRONTIER_PROTOCOL.json; preserve negative findings.','goal_complete':False})
    prior=r.read(v.PRIOR/'CHECKPOINT.json')
    for p,h in prior['files'].items():assert r.sha(v.PRIOR/p)==h,p
    for p,h in prior['additional_sources'].items():assert r.sha(v.ROOT/p)==h,p
    paths=sorted(p for p in ART.rglob('*') if p.is_file() and p.name!='CHECKPOINT.json');sources=r.read(ART/'SOURCE_MANIFEST.json')['sources'];sources[str(Path(__file__))]=r.sha(__file__)
    r.save(ART/'CHECKPOINT.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'file_count':len(paths),'files':{str(p.relative_to(ART)):r.sha(p) for p in paths},
        'additional_sources':{str(Path(p).relative_to(v.ROOT)):h for p,h in sources.items()},'previous_files_preserved':len(prior['files']),'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    for p,h in r.read(ART/'CHECKPOINT.json')['files'].items():assert r.sha(ART/p)==h,p
    print({'registry_entries':len(registry['entries']),'files':len(paths),'status':status},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['register','report']);{'register':register,'report':main}[p.parse_args().action]()
