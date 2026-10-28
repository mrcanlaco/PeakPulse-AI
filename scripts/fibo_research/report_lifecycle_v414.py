"""Render the verified lifecycle diagnosis and preserve the research evidence."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET
import contract_episodes_v414 as e
import replay_contract_episodes_v414 as replay
import verify_lifecycle_fast_v414 as fast

v=e.v;r=e.r;ART=v.ART


def render(d):
    a=d['legacy_audit'];s=d['episodes']['summary'];c=d['replay'];verification=d['verification'];episode_check=d['episode_verification']
    lines=['# Kiểm định lịch sử hợp đồng 2020–2025 — v4.0.14','',d['decision_vi'],'',
        f"Đã tái tính chính xác {d['baseline']['candidates_exactly_equal']:,} tín hiệu trên {d['baseline']['symbols_exactly_equal']} mã của bộ nền. Trên vũ trụ mở rộng, thu thập lại {a['all_candidates']:,} tín hiệu, gồm {a['primary_elite_candidates']:,} tín hiệu elite-sniper qua điều kiện ngày vào lệnh trong năm. Đây là số ứng viên, không phải số lệnh được danh mục chấp nhận.",
        '', '## Kiểm tra khả năng giao dịch trước khi tính NAV', '', '| Dấu hiệu trong đường đi mô phỏng cũ | Mọi ứng viên | Elite-sniper đủ điều kiện năm |','|---|---:|---:|']
    labels={'candidates_with_any_flag':'Có ít nhất một cờ kiểm tra','entry_zero_volume':'Nến dự kiến vào lệnh có volume bằng 0','any_zero_volume_path':'Có nến volume bằng 0 khi vị thế đang mở','zero_volume_exit':'Có nhóm thoát lệnh trên nến volume bằng 0','missing_bars_in_path':'Thiếu nến trên đường đi tới lúc thoát','truncated_horizon':'Đường đi kết thúc trước hạn giữ tối đa vì hết dữ liệu','official_lifecycle_affected':'Bị tác động bởi 5 sự kiện đã đăng ký ban đầu'}
    for key,label in labels.items():lines.append(f"| {label} | {a['all_candidate_quality'][key]:,} | {a['primary_quality'][key]:,} |")
    z=d['zero_volume']['summary']
    lines += ['',d['quality_interpretation_vi'],
        '',f"Ở nhóm elite-sniper, các cờ này liên quan {z['primary_unique_symbol_time_zero_bars']} nến duy nhất theo mã–thời điểm. Toàn bộ {z['candidate_zero_bar_observations']:,} lượt nến volume bằng 0 trên các đường đi được kiểm tra có OHLC phẳng; số lượt không phẳng là {z['nonflat_zero_bar_observations']}. Một nến có thể nằm trong nhiều ứng viên chồng lấn, nên không coi các lượt này là quan sát độc lập.",
        '', '## Sửa nhận dạng hợp đồng và khởi tạo lại lịch sử', '',
        f"Đối chiếu thông báo chính thức giải thích được cả {s['gaps_explained_by_inactive_lifecycle']} khoảng trống / {s['missing_cells_inside_inactive_intervals']:,} ô thời gian: chúng nằm sau thanh toán hợp đồng cũ và trước giờ mở hợp đồng mới. Không bổ sung nến giả vào những khoảng này. {s['inactive_observed_rows']:,} nến còn tồn tại trong khoảng ngừng giao dịch được giữ trong nguồn gốc và tách khỏi các bản lịch sử hợp đồng dùng để tính chỉ báo.",
        '', '| Mã | Thanh toán hợp đồng cũ (UTC) | Mở hợp đồng mới (UTC) | Nhận dạng |','|---|---|---|---|']
    for event in d['events']['events']:
        label=f"{event['old_underlying']} → {event['new_underlying']}" if event['old_underlying']!=event['new_underlying'] else 'Niêm yết lại; khởi tạo lịch sử mới'
        lines.append(f"| {event['symbol']} | [{event['settlement_at']}]({event['settlement_source']}) | [{event['relaunch_at']}]({event['launch_source']}) | {label} |")
    lines += ['',d['identity_interpretation_vi'],
        '',f"Đã ghi {s['episode_views']} bản dữ liệu riêng, giữ nguyên giá gốc và kiểm tra đọc lại từng dòng. Có {s['inactive_positive_volume_rows']} nến volume dương mở đúng thời điểm thanh toán; chúng được đánh dấu cần giải thích, không dùng làm bằng chứng khớp lệnh thông thường sau khi hợp đồng đã dừng.",
        '',f"Việc sửa ranh giới làm thay đổi danh sách ở {s['months_changed']}/72 tháng; tổng lượt mã–tháng giữ ở {s['member_slots_after']:,}. Các ngưỡng 63 ngày / 50 ngày có giao dịch / râu trên 3,2% / top-50 không đổi."]
    for month,delta in d['episodes']['membership_delta'].items():
        if delta['added'] or delta['removed']:lines.append(f"- {month}: loại {', '.join(delta['removed'])}; thêm {', '.join(delta['added'])}.")
    lines += ['',f"Đã chạy lại bộ phát tín hiệu gốc trong {c['recomputed_episode_jobs']} ngữ cảnh dữ liệu riêng trên {c['affected_symbols']} mã liên quan. Các mã còn lại giữ nguyên chính xác {c['unaffected_candidates_reused_exactly']:,} ứng viên. Sau sửa, có {c['corrected_candidates']:,} ứng viên: thêm {c['added']}, bỏ {c['removed']}, {c['changed_signal_objects']} ứng viên chung thay đổi trường tín hiệu và {c['changed_path_objects']} ứng viên chung thay đổi đường đi thoát lệnh. Những thay đổi này chưa được diễn giải thành lợi nhuận.",
        '',d['scope_limitation_vi'],
        '', '## Chi phí, funding và OOS', '', '| Phiên bản | Phí taker mỗi lần khớp | Trượt giá mỗi lần khớp |','|---|---:|---:|']
    for key,label in [('standard_vip6','Chuẩn VIP6'),('stress_regular','Stress Regular')]:
        cost=d['costs'][key];lines.append(f"| {label} | {cost['fee_bps']:g} bps | {cost['slippage_bps']:g} bps |")
    lines += ['',d['cost_funding_vi'],'',d['oos_vi'],'','## Xác minh và việc còn mở','',
        f"{verification['tests']['tests']+episode_check['tests']['tests']+d['verifier_amendment']['tests']['tests']} kiểm thử đạt; kiểm tra độc lập xác nhận {verification['expanded_candidates_independently_checked']:,} đường đi ứng viên, các ranh giới dữ liệu, xếp hạng tháng sau sửa và nguồn của từng phần tính lại. Đã kiểm tra giữ nguyên {verification['previous_v413_files_preserved']:,} tệp của v4.0.13. Các kiểm tra này xác nhận những hạng mục đã nêu, không chứng nhận toàn bộ khả năng giao dịch.",
        '',f"Bộ đối chiếu dùng phần bổ sung chuẩn hóa đơn vị timestamp để tránh chuyển đổi chậm trong pandas. {d['verifier_amendment']['equivalence']['count']} ứng viên thực được chọn theo quy tắc định trước cho kết quả giống hệt bộ đối chiếu cũ; thêm 6 kiểm thử ranh giới thời gian đạt. Phần bổ sung giữ nguyên dữ liệu và mọi kiểm tra nội dung. Mã nguồn cũ được bảo toàn; các lượt kiểm tra chậm ban đầu đã dừng và được chạy lại đầy đủ bằng bộ đã đăng ký.",
        '',d['next_action_vi'],'',d['decision_vi']]
    return '\n'.join(lines)+'\n'


def main():
    replay.verify_sources()
    fast.verify_sources();equivalence=r.read(fast.OUT/'EQUIVALENCE.json');assert equivalence['all_passed'] and equivalence['count']==10
    suites=list(ET.parse(fast.OUT/'TESTS.xml').getroot().iter('testsuite'))
    unit_tests={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','errors','failures','skipped')}
    assert unit_tests['tests']==6 and unit_tests['errors']==unit_tests['failures']==unit_tests['skipped']==0
    check=r.read(ART/'INDEPENDENT_VERIFICATION.json');ec=r.read(e.OUT/'INDEPENDENT_VERIFICATION.json')
    assert check['all_passed'] and ec['all_scoped_checks_passed']
    assert check['candidate_audit_sha256']==r.sha(ART/'LIFECYCLE_CANDIDATE_AUDIT.json')
    assert ec['episode_results_sha256']==r.sha(e.OUT/'RESULTS.json')
    assert ec['replay_manifest_sha256']==r.sha(replay.OUT/'CANDIDATE_MANIFEST.json')
    assert ec['replay_comparison_sha256']==r.sha(replay.OUT/'COMPARISON.json')
    audit=r.read(ART/'LIFECYCLE_CANDIDATE_AUDIT.json');legacy={k:a for k,a in audit.items() if k not in ('flags','primary_flags')}
    for key,rows in [('all_candidate_quality',audit['flags']),('primary_quality',audit['primary_flags'])]:
        direct={'candidates_with_any_flag':len(rows),'symbols_with_flags':len({a['symbol'] for a in rows}),
            'entry_zero_volume':len([a for a in rows if a['entry_zero_volume']]),
            'any_zero_volume_path':len([a for a in rows if a['zero_volume_path_bars']>0]),
            'zero_volume_exit':len([a for a in rows if a['zero_volume_exit_groups']]),
            'missing_bars_in_path':len([a for a in rows if a['missing_bars_through_modelled_exit']>0]),
            'truncated_horizon':len([a for a in rows if a['horizon_truncated']]),
            'official_lifecycle_affected':len([a for a in rows if a['official_lifecycle_flags']])}
        assert direct==audit[key],key
    episodes=r.read(e.OUT/'RESULTS.json');comparison=r.read(replay.OUT/'COMPARISON.json')
    zero=r.read(ART/'ZERO_VOLUME_DIAGNOSTIC.json');assert zero['candidate_audit_sha256']==r.sha(ART/'LIFECYCLE_CANDIDATE_AUDIT.json')
    assert zero['summary']['flagged_candidates']==len(audit['flags'])
    d={'baseline':r.read(ART/'BASELINE_RECONCILIATION.json'),'legacy_audit':legacy,'zero_volume':zero,'episodes':episodes,'events':r.read(e.OUT/'EVENTS.json'),
       'verifier_amendment':{'protocol_sha256':r.sha(fast.OUT/'PROTOCOL.json'),'tests':unit_tests,'equivalence':equivalence,'runner':str(Path(fast.__file__))},
       'replay':comparison,'verification':check,'episode_verification':{k:a for k,a in ec.items() if k!='recomputed_candidate_quality_flags'},'costs':v.x.SCENARIOS,
       'decision_vi':'**Chưa cấp sign-off chiến lược hoặc cho phép cập nhật wiki thành OK.**',
       'quality_interpretation_vi':'Các cờ có thể trùng nhau. Volume bằng 0 trên nến giá không tự chứng minh sổ lệnh không có thanh khoản; cũng không chứng minh có thể khớp ở giá nến. Giữ mọi ứng viên để truy nguyên, không loại giao dịch dựa trên đường giá tương lai. Bảng sự kiện ban đầu chỉ có 5 sự kiện, không phải lịch niêm yết đầy đủ.',
       'identity_interpretation_vi':'Ticker không phải mã định danh hợp đồng ổn định: PUMPUSDT chuyển từ PumpBTC sang Pump.fun; LITUSDT chuyển từ Litentry sang Lighter; BNX có hợp đồng mới sau đổi đơn vị token. Giá, chỉ báo, wave/cooldown và funding phải gắn với đúng lần tồn tại của hợp đồng. Không nối giá bằng tỷ lệ đổi token spot.',
       'scope_limitation_vi':'Phần sửa này chỉ bao phủ 10 lần chuyển hợp đồng đã có bằng chứng. Các lần hủy niêm yết khác, sự kiện xảy ra sau khi tái niêm yết, giá thanh toán thực tế và điều kiện thị trường pre-market vẫn cần kiểm tra. Đường đi cũ bị cắt tại ranh giới hợp đồng chỉ là chẩn đoán, không phải giá thoát thực tế đã được xác nhận.',
       'cost_funding_vi':'Tính cho từng lần khớp, kể cả thoát từng phần; chưa giảm phí BNB. Funding dùng tỷ lệ có dấu, khối lượng còn mở và mark price đúng kỳ thanh toán. Phạm vi funding trong vòng này còn tạm tính; phải cập nhật theo lịch sử hợp đồng và đường đi đã sửa trước khi tải/đối chiếu và tính NAV mới. Dữ liệu thiếu không được mặc định bằng 0; các mark price thay thế phải công bố riêng.',
       'oos_vi':'Chỉ dùng quan sát thị trường 2020–2025. Lịch sử này đã được sử dụng qua nhiều vòng nghiên cứu; chạy lại hoặc mở rộng tập coin không tạo thành OOS thời gian mới. Yêu cầu OOS đáng tin cậy và lợi thế sinh lời sau stress vẫn còn mở.',
       'next_action_vi':'Tiếp theo: hoàn tất lịch hủy niêm yết cho các mã có cờ ảnh hưởng thực tế; đối chiếu giá thanh toán và funding theo hợp đồng; kiểm tra nến không giao dịch và các đợt gián đoạn chung của sàn. Chỉ chạy danh mục mở rộng sau khi chốt xử lý khớp lệnh. Giữ nguyên chính sách đã đăng ký và ghi nhận cả kết quả âm.'}
    r.save(ART/'REPORT_DATA.json',d);text=render(r.read(ART/'REPORT_DATA.json'));(ART/'REPORT.md').write_text(text,encoding='utf8')
    assert (ART/'REPORT.md').read_text(encoding='utf8')==render(r.read(ART/'REPORT_DATA.json'))
    r.save(ART/'REPORT_CONSISTENCY.json',{'all_passed':True,'method':'Exact deterministic rendering from REPORT_DATA.json and UTF8 readback',
        'report_sha256':r.sha(ART/'REPORT.md'),'report_data_sha256':r.sha(ART/'REPORT_DATA.json')})
    registry=r.read(v.PRIOR/'MINI_ALPHA_REGISTRY.json');prior=list(registry['entries'])
    registry['entries'].append({'id':'MA414-DATA2','type':'contract_identity_and_execution_evidence_not_alpha','usable_as_proven_alpha':False,'fresh_oos':False,
        'hypothesis_vi':'Ticker tái sử dụng và lịch sử sau thanh toán có thể làm sai chỉ báo, điều kiện lịch sử và giao dịch giả định.',
        'status':'TEN_TRANSITIONS_CORRECTED_AND_REPLAYED_FULL_LIFECYCLE_AND_ECONOMICS_PENDING','episode_summary':episodes['summary'],
        'signal_comparison':{k:a for k,a in comparison.items() if k!='symbols'},'primary_legacy_quality':audit['primary_quality'],
        'episode_results_sha256':r.sha(e.OUT/'RESULTS.json'),'candidate_audit_sha256':r.sha(ART/'LIFECYCLE_CANDIDATE_AUDIT.json')})
    assert registry['entries'][:-1]==prior
    registry['source_registry_sha256']=r.sha(v.PRIOR/'MINI_ALPHA_REGISTRY.json');registry['status']='CONTRACT_IDENTITY_EVIDENCE_ADDED'
    r.save(ART/'MINI_ALPHA_REGISTRY.json',registry)
    primary_flags=audit['primary_flags'];all_symbols=Counter(a['symbol'] for a in primary_flags)
    r.save(ART/'NEXT_EXECUTION_PROTOCOL.json',{'registered_at_utc':datetime.now(timezone.utc).isoformat(),
        'primary_policy':'Frozen elite-sniper original50/30/20 ladder, annual5day embargo, execution-coupled sizing/caps/cooldown, both per-fill costs.',
        'priority_legacy_flag_symbols':dict(all_symbols.most_common()),
        'lifecycle':'Extend official event coverage for candidate-affected and stale-member symbols; retain publication/version evidence and distinguish reusable tickers.',
        'execution':'Resolve automatic-settlement prices and event ordering, pre-market transitions, zero-volume entry/exit groups and common venue outages before portfolio outcomes. Never use future completeness to pick winning trades.',
        'funding':'Refresh candidate ranges after full lifecycle correction; acquire actual signed rates/marks by instrument episode. Disclose missing exact marks and request paid data only if needed.',
        'evaluation':'Compare fixed old snapshot versus corrected full universe under identical policies; preserve all outcomes. No new threshold sweep to manufacture profit.',
        'oos':'No claim of fresh temporal OOS from reused2020..2025. Establish an independently defensible holdout before final approval.',
        'post_2025_backtest_data_permitted':False,'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    r.save(ART/'GOAL_REQUIREMENTS_AUDIT.json',{'data_through_2025_only':'VERIFIED_THIS_STAGE','baseline_replay':'EXACT',
        'contract_identity':'TEN_TRANSITIONS_CORRECTED_AND_REPLAYED_OTHERS_PENDING','execution_and_settlement':'REMAIN_OPEN',
        'cost_scenarios':'PER_FILL_CONFIRMED_AND_PRESERVED','funding':'REFRESH_BY_CORRECTED_EPISODE_BEFORE_NEW_NAV',
        'fresh_temporal_oos':'NOT_ESTABLISHED','economic_alpha_after_stress':'NOT_ESTABLISHED','evidence_registry_entries':len(registry['entries']),
        'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    r.save(ART/'PROGRESS.json',{'stage':'baseline_and_expanded_lifecycle_audit_verified_ten_contract_transitions_corrected',
        'goal_complete':False,'live_signoff':'NOT_GRANTED','next_action':'Complete NEXT_EXECUTION_PROTOCOL.json before evaluating expanded portfolio returns.'})
    previous=r.read(v.PRIOR/'CHECKPOINT.json')
    for p,h in previous['files'].items():assert r.sha(v.PRIOR/p)==h,p
    for p,h in previous.get('additional_sources',{}).items():assert r.sha(v.ROOT/p)==h,p
    paths=sorted(p for p in ART.rglob('*') if p.is_file() and p.name!='CHECKPOINT.json')
    extras=[Path(__file__),v.ROOT/'scripts/fibo_research/verify_episode_replay_v414.py',v.ROOT/'scripts/fibo_research/zero_volume_diagnostic_v414.py',Path(replay.__file__),Path(e.__file__),Path(fast.__file__),v.ROOT/'tests/unit/fibo_short/test_contract_episodes_v414.py',v.ROOT/'tests/unit/fibo_short/test_verifier_units_v414.py']
    checkpoint={'created_at_utc':datetime.now(timezone.utc).isoformat(),'files':{str(p.relative_to(ART)):r.sha(p) for p in paths},
        'file_count':len(paths),'additional_sources':{str(p.relative_to(v.ROOT)):r.sha(p) for p in extras},'goal_complete':False,'live_signoff':'NOT_GRANTED'}
    r.save(ART/'CHECKPOINT.json',checkpoint)
    for p,h in r.read(ART/'CHECKPOINT.json')['files'].items():assert r.sha(ART/p)==h,p
    print(f'Lifecycle audit saved; {len(registry["entries"])} evidence entries; {len(paths)} protected files.',flush=True)


if __name__=='__main__':main()
