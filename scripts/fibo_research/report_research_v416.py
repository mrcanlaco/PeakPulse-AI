"""Independent resampling check, attribution, immutable report and evidence log."""
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import gzip,json
import numpy as np
import research_v416 as v
r=v.r;ART=v.ART


def independent_statistics(rows,start,end,saved):
    # Aggregate by Python calendar dates, resample count weights rather than outcome arrays.
    lo=datetime.fromisoformat(start).replace(tzinfo=timezone.utc);hi=datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
    selected=[a for a in rows if lo.timestamp()<=a['entry_ts']<hi.timestamp()]
    if not selected:assert not saved['available'];return
    first=lo.toordinal()-lo.weekday();last=(hi.toordinal()-1);last-=datetime.fromordinal(last).weekday();n=(last-first)//7+1
    count=np.zeros(n);sums=np.zeros((n,3))
    for a in selected:
        day=datetime.fromtimestamp(a['entry_ts'],timezone.utc).toordinal();week=(day-first)//7
        treated=a['treated']['net_return'];control=a['control']['net_return'];count[week]+=1;sums[week]+=[treated,control,treated-control]
    rng=np.random.default_rng(410);starts=rng.integers(0,n,size=(10000,(n+3)//4));dist=[]
    for blocks in starts:
        indices=[(int(b)+j)%n for b in blocks for j in range(4)][:n];weight=np.bincount(indices,minlength=n);den=float(weight@count)
        if den:dist.append((weight@sums)/den*10000)
    dist=np.asarray(dist)
    assert saved['calendar_weeks']==n and saved['active_weeks']==int(np.sum(count>0)) and saved['pairs']==len(selected)
    for column,key in [(0,'fibo_ci95_bps'),(1,'control_ci95_bps'),(2,'paired_difference_ci95_bps')]:
        assert np.allclose(np.quantile(dist[:,column],[.025,.975]),saved[key],atol=1e-8,rtol=0)


def decomposition(result,ledger):
    output={};fields=['gross_reference_return','fees','slippage','funding','net_return'];checked=0
    for scenario,rows in ledger['scenarios'].items():
        output[scenario]={}
        for name,(start,end) in v.SPLITS.items():
            saved=result['results'][scenario]['splits'][name];independent_statistics(rows,start,end,saved);checked+=1
            chosen=[p for p in rows if r.utc(start).timestamp()<=p['entry_ts']<r.utc(end).timestamp()]
            if not chosen:output[scenario][name]={'available':False};continue
            means={side:{k:float(np.mean([p[side][k] for p in chosen])*10000) for k in fields} for side in ('treated','control')}
            difference={k:means['treated'][k]-means['control'][k] for k in fields};assert abs(difference['net_return']-saved['mean_difference_bps'])<1e-8
            payments=[a for p in chosen for side in ('treated','control') for a in p[side]['funding_events']];proxy=[a for a in payments if a['price_source']!='funding_api_settlement_mark']
            output[scenario][name]={'available':True,'pairs':len(chosen),'means_bps':means,'difference_bps':difference,'funding_payments':len(payments),
                'proxy_payments':len(proxy),'conditional_1pct_proxy_error_bound_bps':.01*sum(abs(a['cashflow']) for a in proxy)/len(chosen)*10000}
        for year,saved in result['results'][scenario]['annual'].items():independent_statistics(rows,f'{year}-01-01',f'{int(year)+1}-01-01',saved);checked+=1
    return {'scenarios':output,'independent_bootstrap_periods_verified':checked,
            'sensitivity_caveat':'Bound conditional on all proxy marks having relative errors <=1%; not an empirical error bound. Fixed notional event study only.'}


def render(d):
    result=d['results'];verified=d['verification'];funding=d['funding'];matched=d['matching'];diag=d['diagnostics']
    lines=['# Kiểm định phần đóng góp của Fibo — v4.0.16','',d['decision_vi'],'',
           'Giữ nguyên phương pháp ghép cặp của v4.0.11 trên vũ trụ đã sửa ở v4.0.15. Cả tín hiệu Fibo và đối chứng đều có momentum 24 giờ dương, ghép theo momentum và biến động quá khứ, cùng thời điểm vào và cùng giữ 24 giờ. Không dùng stop/TP trong phép thử này.',
           '', '**Đơn vị là bps trên notional ban đầu mỗi sự kiện; 100 bps = 1%. Đây không phải lợi nhuận NAV danh mục.**',
           '', '| Giai đoạn / chi phí | Số cặp | Fibo ròng | Đối chứng ròng | Fibo − đối chứng | CI 95% chênh lệch |','|---|---:|---:|---:|---:|---:|']
    labels={'development_2020_2022':'2020–2022','validation_2023':'2023','retrospective_oos_2024_2025':'2024–2025 hồi cứu','all_2020_2025':'2020–2025'}
    for period,label in labels.items():
        for cost,title in [('standard_vip6','chuẩn'),('stress_regular','stress')]:
            p=result['results'][cost]['splits'][period]
            if not p['available']:lines.append(f'| {label} / {title} | 0 | — | — | — | — |');continue
            lo,hi=p['paired_difference_ci95_bps'];ci=f'[{lo:+.2f}; {hi:+.2f}]' if p['active_weeks']>=2 else 'Dưới 2 tuần có sự kiện'
            lines.append(f"| {label} / {title} | {p['pairs']} | {p['mean_fibo_bps']:+.2f} | {p['mean_control_bps']:+.2f} | {p['mean_difference_bps']:+.2f} | {ci} |")
    lines += ['',d['interpretation_vi'],'','## Mẫu và chi phí','',
        f"Từ {matched['raw_elite_candidates']:,} ứng viên elite, lấy {matched['sampled_events']:,} sự kiện theo wave/cooldown đã khóa; ghép được {len(matched['pairs']):,} cặp và để nguyên {len(matched['unmatched']):,} sự kiện không ghép được. Không tìm đối chứng khác theo lợi nhuận tương lai.",
        '', '| Lý do không ghép | Số sự kiện |','|---|---:|']
    reasons={'treated_nonpositive_momentum':'Momentum 24 giờ của Fibo không dương','outside_fixed_caliper':'Không có đối chứng đủ gần theo giới hạn đã khóa','fewer_than_three_positive_controls':'Có ít hơn 3 đối chứng có momentum dương'}
    for k,n in matched['unmatched_reasons'].items():lines.append(f'| {reasons.get(k,k)} | {n} |')
    lines += ['', '| Kịch bản | Phí mỗi khớp | Trượt giá mỗi khớp |','|---|---:|---:|']
    for name,title in [('standard_vip6','VIP6 chuẩn'),('stress_regular','Regular stress')]:
        p=d['protocol']['cost_scenarios'][name];lines.append(f"| {title} | {p['fee_bps']:g} bps | {p['slippage_bps']:g} bps |")
    lines += ['', 'Không giảm phí BNB. Khối lượng cố định cho từng phía, funding thực có dấu và được tính theo khối lượng đang mở; sự kiện đúng lúc vào bị loại, đúng lúc thoát được tính.',
        '', '## Tách nguyên nhân chênh lệch trong 2024–2025','', '| Kịch bản | Do giá | Chênh lệch phí | Chênh lệch trượt giá | Do funding | Ròng |','|---|---:|---:|---:|---:|---:|']
    for name,title in [('standard_vip6','Chuẩn'),('stress_regular','Stress')]:
        p=diag['scenarios'][name]['retrospective_oos_2024_2025'];a=p['difference_bps']
        lines.append(f"| {title} | {a['gross_reference_return']:+.3f} | {a['fees']:+.3f} | {a['slippage']:+.3f} | {a['funding']:+.3f} | {a['net_return']:+.3f} |")
    primary=diag['scenarios']['standard_vip6']['retrospective_oos_2024_2025']
    sensitivity_text=(f"Toàn bộ {primary['funding_payments']:,} khoản funding của hai phía trong mẫu 2024–2025 dùng giá thanh toán từ API. Vì vậy phần giá mark thay thế ở lịch sử cũ không làm thay đổi kết quả chính này." if primary['proxy_payments']==0 else
        f"Trong mẫu 2024–2025 có {primary['funding_payments']:,} khoản funding của hai phía, {primary['proxy_payments']:,} khoản dùng mark thay thế. Nếu giả định sai số tương đối của mọi mark thay thế không quá 1%, độ nhạy tối đa của chênh lệch bình quân là {primary['conditional_1pct_proxy_error_bound_bps']:.6f} bps; đây là giả định, không phải sai số thực đã đo.")
    lines += ['', 'Dòng chênh lệch phí và trượt giá được trừ khỏi lợi nhuận. Funding được cộng có dấu.',
        '',sensitivity_text,
        '', '## Kiểm chứng và giới hạn', '',
        f"Funding bao phủ {verified['funding_symbols']} mã: dùng lại {funding['reused_symbols']}, tải mới {funding['newly_acquired_symbols']}. Đối chiếu {verified['funding_snapshot_events_verified']:,} bản ghi với {verified['raw_responses_verified']:,} phản hồi nguồn và {verified['archives_verified']} tệp kho tháng. Các giá mark OPEN ở lịch sử cũ vẫn là proxy, có nhãn và danh sách yêu cầu bổ sung giá chính xác.",
        '',f"Đã tính lại độc lập {verified['past_feature_rows_recomputed']:,} dòng đặc trưng, lựa chọn cặp, {verified['scenario_leg_outcomes_recomputed']:,} kết quả từng phía và {verified['scenario_funding_payments_recomputed']:,} khoản funding theo hai kịch bản. Có {verified['tests']['tests']} kiểm thử đạt. Đối chiếu thống kê độc lập cho {diag['independent_bootstrap_periods_verified']} giai đoạn–chi phí.",
        '',f"Kiểm tra {verified['unique_paths_recomputed']:,} đường đi riêng biệt: {verified['path_issues']} lỗi nến vào/ra, thiếu dữ liệu hoặc giao cắt settlement; {d['quality']['holding_zero_volume_legs']} đường đi có nến volume bằng 0 trong thời gian giữ. Không chứng minh được độ sâu sổ lệnh hoặc khả năng khớp thực từ nến.",
        '', 'Bootstrap khối 4 tuần trên lịch tuần chung, giữ tuần không có sự kiện, 10.000 mẫu. Phép thử so sánh lựa chọn coin khi đã biết thời điểm Fibo xuất hiện; chưa tách riêng giá trị chọn thời điểm, quản lý thoát lệnh hoặc hạn mức danh mục. Đối chứng có thể dùng lại và các lệnh có thể chồng lấn; không suy ra NAV hoặc sức chứa vốn từ phép thử.',
        '', '**OOS:** Toàn bộ dữ liệu thị trường nằm trong 2020–2025. Các năm này và họ chiến lược đã được nghiên cứu trước; nhãn 2024–2025 là đánh giá hồi cứu, không phải holdout chưa từng được nhìn thấy. Khoảng tin cậy chưa điều chỉnh toàn bộ lịch sử chọn chiến lược.',
        '', '## Quyết định tiếp theo', '',d['next_vi'],
        '',f"Nhật ký nghiên cứu hiện có {d['registry_entries']} mục. Mục mới giữ cả kết quả thuận lợi lẫn bất lợi, không gắn nhãn alpha đã chứng minh."]
    return '\n'.join(lines)+'\n'


def main():
    v.verify_sources();result=r.read(ART/'RESULTS.json');verified=r.read(ART/'INDEPENDENT_VERIFICATION.json');assert verified['all_checks_passed'] and verified['results_sha256']==r.sha(ART/'RESULTS.json')
    import recover_funding_marks_v416 as recovery
    recovery.context();recovery.engine.verify_sources()
    with gzip.open(ART/'EVENT_LEDGER.json.gz','rt',encoding='utf8') as fh:ledger=json.load(fh)
    assert result['ledger_sha256']==r.sha(ART/'EVENT_LEDGER.json.gz');diag=decomposition(result,ledger);r.save(ART/'CASH_DECOMPOSITION.json',diag)
    registry=r.read(v.PRIOR/'MINI_ALPHA_REGISTRY.json');previous=list(registry['entries']);supported=result['incremental_diagnostic_support']
    status='RELATIVE_DIAGNOSTIC_SUPPORTED_NOT_LIVE_ALPHA' if supported else 'INCREMENTAL_FIBO_SELECTION_NOT_CONFIRMED'
    registry['entries'].append({'id':'MA416-U2','type':'expanded_universe_positive_momentum_matched24h','usable_as_proven_alpha':False,'fresh_oos':False,'status':status,
        'primary':{k:a['splits']['retrospective_oos_2024_2025'] for k,a in result['results'].items()},'results_sha256':r.sha(ART/'RESULTS.json'),
        'interpretation':'Conditional cross-sectional selection diagnostic, not NAV or full-strategy test; timing and exit-policy contributions remain distinct.'})
    assert registry['entries'][:-1]==previous;registry['source_registry_sha256']=r.sha(v.PRIOR/'MINI_ALPHA_REGISTRY.json');registry['status']=status
    registry['parent_registry']={'path':str(v.PRIOR/'MINI_ALPHA_REGISTRY.json'),'sha256':registry['source_registry_sha256']}
    registry['current_results']={'path':str(ART/'RESULTS.json'),'sha256':r.sha(ART/'RESULTS.json')}
    registry['last_completed_stage']='expanded_positive_momentum_matched24h_verified'
    registry['trial_accounting_v416']={'new_signal_parameters':0,'additional_universe_diagnostic_replays':1,'prior_adaptive_signal_variants_at_least':24,
        'new_bracket_mechanism_hypothesis_proposed_after_results':True,'fresh_oos':False}
    r.save(ART/'MINI_ALPHA_REGISTRY.json',registry)
    d={'results':result,'verification':verified,'funding':r.read(ART/'funding/MANIFEST.json'),'matching':r.read(ART/'MATCHES.json'),
       'diagnostics':diag,'quality':r.read(ART/'PATH_AUDIT.json'),'protocol':r.read(ART/'PROTOCOL.json'),'registry_entries':len(registry['entries']),
       'decision_vi':'**Chưa duyệt chiến lược giao dịch thật.** '+('Phép thử đạt điều kiện hỗ trợ tương đối đã đăng ký; vẫn cần lợi thế tuyệt đối, xác nhận OOS và kiểm chứng thực thi.' if supported else 'Phép thử chưa xác nhận lợi thế chọn coin tăng thêm của tín hiệu Fibo theo tiêu chí đã đăng ký.'),
       'interpretation_vi':'Tiêu chí khóa trước gồm ít nhất 200 cặp hoàn chỉnh trong 2024–2025, không có lỗi chất lượng trọng yếu và cận dưới CI 95% chênh lệch lớn hơn 0 ở cả hai mức chi phí. Một điểm ước lượng dương riêng lẻ không đủ đạt.',
       'next_vi':'Giữ nguyên 694 cặp đã chọn để kiểm tra tương tác giữa lựa chọn coin và cơ chế TP/SL gốc. Hai phía sẽ dùng cùng khoảng cách stop/target theo phần trăm của tín hiệu Fibo, cùng quy tắc chốt từng phần và thời hạn giữ tối đa; chưa chọn tham số mới. Đây là phép thử cơ chế bổ sung được đề xuất sau khi thấy kết quả 24 giờ, không phải xác nhận OOS độc lập. Yêu cầu OOS phù hợp vẫn còn mở; không ghi wiki là OK.'}
    r.save(ART/'REPORT_DATA.json',d);(ART/'REPORT.md').write_text(render(r.read(ART/'REPORT_DATA.json')),encoding='utf8')
    assert (ART/'REPORT.md').read_text(encoding='utf8')==render(r.read(ART/'REPORT_DATA.json'))
    r.save(ART/'REPORT_CONSISTENCY.json',{'all_passed':True,'report_sha256':r.sha(ART/'REPORT.md'),'report_data_sha256':r.sha(ART/'REPORT_DATA.json'),'method':'Exact deterministic JSON rendering and UTF8 readback'})
    r.save(ART/'NEXT_MECHANISM_PROTOCOL.json',{'registered_at_utc':datetime.now(timezone.utc).isoformat(),
        'question':'Does the original exit-management rule change relative performance of Fibo-selected coins versus the already locked matched short controls?',
        'selection':'Exactly the694 v416 pairs, fixed before outcomes in this proposed experiment. No rematching, profitable-coin exclusion or caliper/horizon optimization.',
        'paths':'Fibo original entry/stop/three-target reference geometry. Transplant percentage distances from its reference entry to the contemporaneous control open. Both sides same50/30/20 partial exits, original stop-first conservative5m processing and ratchets, original72h4h/120h1d maximum hold.',
        'accounting':'Fixed1 unit reference notional per leg; same per-fill VIP6+10bps and Regular+50bps, signed historical funding on remaining quantities. Event-study returns, not portfolio NAV. Reconcile treated path against frozen original candidate.',
        'quality':'Exact complete bounded5m history, contract episodes separate, settlement and zero-volume fills disclosed. Missing future data retained as unevaluable; no favorable replacement. Audit before economic evaluation.',
        'statistics':'Same splits and calendar paired4-week bootstrap10000 seed410 as v416. Primary2024..2025 >=200 complete pairs, zero incomplete or critical-quality pairs, lower95percent paired-mean CI>0 for BOTH costs for relative diagnostic support. Report absolute returns and intervals separately; relative support alone is insufficient for a tradable alpha.',
        'data_limit':'All market observations before2026; retain source/version manifests. Freeze implementation before new bracket outcomes.',
        'adaptive_context':'Proposed after observing v415 portfolio NAV and v416 fixed24h outcomes. Additional hypothesis inspection; no claim of independent or clean temporal OOS.',
        'parent_matches_sha256':r.sha(ART/'MATCHES.json'),'parent_results_sha256':r.sha(ART/'RESULTS.json'),
        'fresh_oos':False,'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    r.save(ART/'PROGRESS.json',{'stage':'expanded_matched_diagnostic_verified','goal_complete':False,'live_signoff':'NOT_GRANTED','next_action':'Implement NEXT_MECHANISM_PROTOCOL.json without parameter search.'})
    r.save(ART/'GOAL_REQUIREMENTS_AUDIT.json',{'only_market_data_through2025':'VERIFIED','two_per_fill_costs':'VERIFIED','historical_signed_funding':'VERIFIED_WITH_EXPLICIT_OLDER_MARK_PROXIES',
        'positive_stress_portfolio_edge':'NOT_ESTABLISHED_V415_FULL_HISTORY_NEGATIVE','incremental_entry_selection':status,'credible_unseen_temporal_oos':'NOT_ESTABLISHED',
        'mini_alpha_log':'UPDATED_WITH_NEGATIVE_AND_POSITIVE_EVIDENCE','goal_complete':False,'live_signoff':'NOT_GRANTED'})
    prior=r.read(v.PRIOR/'CHECKPOINT.json')
    for p,h in prior['files'].items():assert r.sha(v.PRIOR/p)==h,p
    for p,h in prior['additional_sources'].items():assert r.sha(v.ROOT/p)==h,p
    paths=sorted(p for p in ART.rglob('*') if p.is_file() and p.name!='CHECKPOINT.json');sources=r.read(ART/'SOURCE_MANIFEST.json')['sources']
    sources.update({str(v.ROOT/p):h for p,h in r.read(recovery.OUT/'PROTOCOL.json')['sources'].items()})
    r.save(ART/'CHECKPOINT.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'files':{str(p.relative_to(ART)):r.sha(p) for p in paths},'file_count':len(paths),
        'additional_sources':{str(Path(p).relative_to(v.ROOT)):h for p,h in {**sources,str(Path(__file__)):r.sha(__file__)}.items()},'previous_files_preserved':len(prior['files']),
        'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    for p,h in r.read(ART/'CHECKPOINT.json')['files'].items():assert r.sha(ART/p)==h,p
    print({'registry_entries':len(registry['entries']),'protected_files':len(paths),'status':status},flush=True)


if __name__=='__main__':main()
