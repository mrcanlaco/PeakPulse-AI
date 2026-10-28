"""Render verified data-scope findings, preserve prior evidence, and freeze next step."""
from datetime import datetime,timezone
from pathlib import Path
import universe_audit_v413 as v
import recover_universe_gaps_v413 as recovery
import complete_universe_v413 as completion

r=v.r;ART=v.ART;OUT=completion.OUT


def render(initial,manifest,check,daily,comparisons,quality,stale,delta):
    s=manifest['summary'];official=check['official_sample_validation'];rec=check['recovery_validation']
    lines=['# Kiểm định vũ trụ lịch sử 2020–2025 — v4.0.13','',
        '**Đã cải thiện và kiểm chứng phạm vi dữ liệu; chưa cấp sign-off chiến lược.** Vòng này kiểm định dữ liệu và danh sách coin theo thời điểm. Chưa tính lợi nhuận chiến lược trên vũ trụ mở rộng, chưa thay đổi quy tắc vào/thoát lệnh.',
        '',f"Bộ dữ liệu hợp nhất có **{s['symbols']:,} mã / {s['rows_5m']:,} nến 5 phút**, tăng {s['new_symbols_vs_v408']:,} mã so với bộ 250 mã v4.0.8. Các snapshot cũ được giữ nguyên.",
        '', '## Kết quả đối chiếu', '', '| Hạng mục | Kết quả |','|---|---|',
        f"| Nến trong hợp nhất ban đầu được đối chiếu độc lập | {initial['rows_5m']:,} |",
        f"| Nến trùng giữa các nguồn đã đối chiếu | {initial['overlap_rows_compared']:,}; không có xung đột |",
        '| Dựng lại danh sách vũ trụ cũ | Khớp chính xác cả 72 tháng |',
        f"| Mẫu tháng chọn trước từ các mã bổ sung | {official['samples']:,} mã; {official['rows_recompared']:,} nến khớp kho chính thức |",
        f"| Nến bổ sung ngoài mẫu tháng | {daily['extra_rows_verified']:,} nến GMT khớp {daily['daily_archives']} tệp ngày chính thức |",
        f"| Khôi phục mã bị loại do thiếu dữ liệu | {s['recovered_symbols']} mã; {rec['raw_archives_independently_reparsed']} tệp kho đã phân tích lại độc lập |",
        f"| Nến bổ sung ròng từ khôi phục vào hợp nhất ban đầu | {s['additional_rows_from_recovery']:,} |",
        '| Dữ liệu từ 2026 được dùng | 0 |',
        '', 'Các tệp tải mới đều được kiểm tra SHA256 với tệp CHECKSUM chính thức. Mẫu một tháng cho mỗi mã chỉ kiểm chứng phần được lấy mẫu, không chứng nhận mọi tháng hoặc đầy đủ lịch sử niêm yết. Các tệp nguồn cục bộ còn được kiểm tra hash, mã symbol, UTC, lưới 5 phút, OHLCV, phần trùng và khoảng trống.',
        '', '## Danh sách coin thay đổi đáng kể', '',
        f"Danh sách đủ điều kiện thay đổi ở **{s['changed_months_vs_v408']}/72 tháng** so với v4.0.8. Toàn bộ giai đoạn có {s['monthly_member_slots']:,} lượt mã–tháng và {s['unique_members']} mã từng được chọn; đây không phải số giao dịch. Riêng việc khôi phục các mã bị bỏ trước đây làm thay đổi thêm {s['changed_months_due_to_recovery']} tháng so với hợp nhất ban đầu.",
        '', '| Năm | Lượt mã–tháng ở bộ cũ | Lượt mã–tháng ở bộ hoàn thiện | Tháng thay đổi so với bộ cũ |','|---|---:|---:|---:|']
    for year in range(2020,2026):
        values=[a for month,a in delta.items() if month.startswith(str(year))]
        lines.append(f"| {year} | {sum(a['old_members'] for a in values)} | {sum(a['completed_union_members'] for a in values)} | {sum(bool(a['added_vs_old'] or a['removed_vs_old']) for a in values)} |")
    lines += ['', 'Quy tắc xếp hạng vẫn giữ nguyên: trước mỗi tháng, chỉ dùng 63 ngày quá khứ, ít nhất 50 ngày có volume dương, H4 đầy đủ với phân vị 90% của râu trên không quá 3,2%, rồi lấy 50 mã theo trung vị quote volume ngày; giữ nguyên các mã loại trừ và cách xử lý hòa hạng. Không dùng giá tương lai, không lấp giá trước khi mã xuất hiện.',
        '', '## Những khoảng trống và trạng thái giao dịch còn cần xử lý', '',
        f"Bộ hoàn thiện có {s['internal_gap_count']} khoảng trống nội bộ, tương ứng **{s['missing_bars_inside_observed_spans']:,} nến thiếu** giữa các nến quan sát. Có {s['zero_volume_rows']:,} nến volume bằng 0. Hai loại này được phân biệt rõ; không tạo giá giả và không loại cả mã theo độ đầy đủ của dữ liệu tương lai.",
        '', '| Mã khôi phục | Nến đã có trong hợp nhất ban đầu | Nến sau hợp nhất | Nến thiếu còn lại trong phạm vi quan sát |','|---|---:|---:|---:|']
    for symbol,a in sorted(comparisons.items()):lines.append(f"| {symbol} | {a['initial_rows']:,} | {a['union_rows']:,} | {quality[symbol]['missing_bars_inside_span']:,} |")
    lines += ['', f"Có **{len(stale['records'])} lượt thành viên tháng** mà nến volume dương gần nhất đã đóng cách thời điểm tái cơ cấu ít nhất 24 giờ. Đây là kiểm tra chỉ dùng thông tin đã có tại đầu tháng; chưa phải một bộ lọc chiến lược mới. Quy tắc trung vị 63 ngày có thể giữ một mã sau khi giao dịch đã dừng, nên cần kiểm tra trạng thái hợp đồng và khả năng khớp thực tế.",
        '', 'Một số kho nến tiếp tục chứa các đoạn volume bằng 0 rất dài. Không thể lấy sự hiện diện của timestamp làm bằng chứng rằng có thể mua lại vị thế short ở giá đó. Việc khớp lệnh, hủy niêm yết/đổi mã, thanh toán cuối cùng và funding quanh các thời điểm này còn phải được kiểm định trước khi diễn giải NAV mở rộng.',
        '', '## Ý nghĩa đối với chiến lược và OOS', '',
        'Phát hiện mới là rủi ro về phạm vi dữ liệu: vũ trụ cũ bỏ qua nhiều lịch sử có sẵn và làm thay đổi danh sách đủ điều kiện ở phần lớn các tháng. Chưa biết việc sửa phạm vi này sẽ tăng hay giảm lợi nhuận; vòng này không tính P&L để chọn tập mã thắng.',
        '', 'Các thư mục bổ sung đã từng xuất hiện trong hồ sơ kiểm kê của dự án khác. Vì vậy, “mới với snapshot này” không đồng nghĩa với OOS chưa từng được sử dụng. Lịch sử đến 2025 đã có quá trình nghiên cứu lặp lại; yêu cầu xác nhận OOS vẫn chưa được đáp ứng bằng một giai đoạn thời gian mới hoàn toàn.',
        '', 'Nhánh chính vẫn là elite-sniper với thang TP gốc v4.0.9 đã khóa trước khi thấy kết quả v4.0.12. Chi phí mỗi lần khớp giữ nguyên: VIP6 2,5 bps phí + 10 bps trượt giá; stress Regular 5 bps phí + 50 bps trượt giá; không giảm phí BNB. Funding lịch sử được tải và đối chiếu theo phạm vi vị thế trước khi chạy danh mục.',
        '', '## Kiểm chứng và bước tiếp theo', '',
        '18 kiểm thử dữ liệu, ranh giới thời gian và phân tích kho đạt. Đối chiếu độc lập xác nhận dữ liệu hợp nhất và xếp hạng theo thời điểm; kiểm tra tính toán dữ liệu này không thay thế kiểm định khớp lệnh hay chứng minh alpha.',
        '', 'Bước tiếp theo đã đăng ký trong NEXT_LIFECYCLE_EXECUTION_PROTOCOL.json: kiểm tra các sự kiện ngừng giao dịch/đổi hợp đồng, thu thập tín hiệu theo quy tắc đã khóa, định lượng giao dịch nào gặp khoảng trống hoặc không có giao dịch, rồi xử lý những trường hợp thực sự ảnh hưởng trước khi đánh giá danh mục mở rộng. Không chọn lại ngưỡng hoặc tập mã dựa trên lợi nhuận.',
        '', '**Chưa duyệt giao dịch thật hoặc cập nhật wiki thành OK.** Nhật ký giữ nguyên 16 mục bằng chứng cũ và bổ sung một mục về chất lượng dữ liệu; mục mới không được ghi nhận là alpha sinh lời.',
        '', 'Nguồn chính thức: [Binance Public Data — định dạng USD‑M và kiểm tra checksum](https://github.com/binance/binance-public-data). Các URL từng tệp, checksum và snapshot nằm trong hồ sơ của vòng này.']
    return '\n'.join(lines)+'\n'


def main():
    v.verify_sources();recovery.verify_sources()
    initial=r.read(ART/'DATA_SUMMARY.json');manifest=r.read(OUT/'DATA_MANIFEST.json');check=r.read(OUT/'INDEPENDENT_VERIFICATION.json')
    daily=r.read(ART/'daily_sample_reconciliation/VERIFICATION.json');comparisons=r.read(OUT/'RECOVERY_MERGE_COMPARISON.json')
    quality=r.read(OUT/'QUALITY.json');stale=r.read(OUT/'STALE_MEMBERSHIP_AUDIT.json');delta=r.read(OUT/'MEMBERSHIP_COMPARISON.json')
    assert check['all_data_reconciliation_checks_passed'] and check['data_manifest_sha256']==r.sha(OUT/'DATA_MANIFEST.json')
    assert daily['all_passed'] and daily['extra_rows_verified']==check['official_sample_validation']['local_extra_rows_not_certified_by_monthly_archive']
    args=(initial,manifest,check,daily,comparisons,quality,stale,delta)
    text=render(*args);(ART/'REPORT.md').write_text(text,encoding='utf8');assert (ART/'REPORT.md').read_text(encoding='utf8')==render(*args)
    r.save(ART/'REPORT_CONSISTENCY.json',{'all_passed':True,'method':'Exact deterministic JSON rendering and UTF8 readback',
        'report_sha256':r.sha(ART/'REPORT.md'),'completed_data_manifest_sha256':r.sha(OUT/'DATA_MANIFEST.json')})
    registry=r.read(v.PRIOR/'MINI_ALPHA_REGISTRY.json');prior=list(registry['entries'])
    registry['entries'].append({'id':'MA413-DATA1','type':'data_scope_and_tradability_evidence_not_alpha','usable_as_proven_alpha':False,'fresh_oos':False,
        'hypothesis_vi':'Thiếu lịch sử và loại cả mã vì gap có thể làm sai phạm vi vũ trụ; timestamp có dữ liệu không bảo đảm khớp được lệnh.',
        'status':'DATA_SCOPE_EXPANDED_AND_VERIFIED_EXECUTION_REVIEW_PENDING','summary':manifest['summary'],
        'performance_observed_on_expanded_universe':False,'data_manifest_sha256':r.sha(OUT/'DATA_MANIFEST.json')})
    registry['status']='DATA_SCOPE_EVIDENCE_ADDED';registry['source_registry_sha256']=r.sha(v.PRIOR/'MINI_ALPHA_REGISTRY.json')
    assert registry['entries'][:-1]==prior;r.save(ART/'MINI_ALPHA_REGISTRY.json',registry)
    r.save(ART/'NEXT_LIFECYCLE_EXECUTION_PROTOCOL.json',{'registered_at_utc':datetime.now(timezone.utc).isoformat(),'id':'MA413-LIFECYCLE1',
        'stage':'Registered before expanded-universe candidate or portfolio outcomes',
        'data_manifest_sha256':r.sha(OUT/'DATA_MANIFEST.json'),
        'primary_policy':'Frozen v409 elite-sniper original50/30/20 ladder; preserve entry gates, horizon, sizing, annual resets, costs, risk caps and wave/cooldown semantics.',
        'ordering':[
            'Inspect official historical lifecycle evidence for PIT members with stale activity, internal gaps or sustained zero-volume spans. Distinguish exchange pauses, delistings, migrations and archival gaps; do not stitch differently named or scaled contracts without evidence.',
            'Collect the same causal candidate stream on the completed union and verify old-snapshot baseline. Retain all signal rejections and quality diagnostics. Do not drop trades using future path completeness or future last-traded timestamps.',
            'Audit actual candidate entry/exit/funding paths against gaps and zero-volume bars. Quantify affected candidates before interpreting any portfolio outcome. Data presence alone does not certify fills.',
            'Resolve materially affected execution using source evidence and explicit registered rules. If settlement/tradability remains unknown, keep affected outcome qualified or uncomputed; never invent a favorable exit.',
            'Before expanded portfolio outcomes, freeze chronological evaluation and OOS labels. Report old-snapshot versus full union and new-symbol contributions under both cost scenarios, actual signed funding and full cash-coupled admissions. No winning-cohort selection or new parameter sweep.'
        ],'oos':'Historical reuse remains disclosed. Cross-sectional expansion is not automatically fresh temporal OOS. Requirement for defensible OOS remains open.',
        'post_2025_backtest_data_permitted':False,'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    r.save(ART/'GOAL_REQUIREMENTS_AUDIT.json',{'data_through_2025_only':'VERIFIED_THIS_STAGE','broader_historical_universe':'EXPANDED_OBSERVED_ROWS_VERIFIED_NOT_COMPLETE_LIFECYCLE_CERTIFICATION',
        'two_per_fill_cost_scenarios':'FROZEN_FOR_NEXT_PORTFOLIO_RUN','historical_funding':'ACQUIRE_BY_ACTUAL_CANDIDATE_RANGE_BEFORE_NEXT_PORTFOLIO_RUN',
        'fresh_temporal_oos':'NOT_ESTABLISHED','economic_and_statistical_alpha':'NOT_ESTABLISHED','mini_alpha_evidence_log':'17_ENTRIES_PRESERVING_PRIOR16',
        'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    r.save(ART/'TRANSPORT_STATUS.json',{'amendment_registered':True,'amendment_applied_to_acquisition':False,
        'reason':'Original acquisition jobs resumed fast progress and completed without interruption. Persistent-session wrapper remained unused; original frozen acquisition code produced the samples and recovery.',
        'acquisition_processes_terminal':True})
    r.save(ART/'PROGRESS.json',{'stage':'expanded_observed_universe_verified_lifecycle_execution_review_next','goal_complete':False,'live_signoff':'NOT_GRANTED',
        'completed_data_manifest_sha256':r.sha(OUT/'DATA_MANIFEST.json'),'next_action':'Follow NEXT_LIFECYCLE_EXECUTION_PROTOCOL.json; resolve tradability and gap impacts before expanded-universe outcomes.'})
    previous=r.read(v.PRIOR/'CHECKPOINT.json')
    for p,h in previous['files'].items():assert r.sha(v.PRIOR/p)==h,p
    for p,h in previous.get('additional_sources',{}).items():assert r.sha(v.ROOT/p)==h,p
    paths=sorted(p for p in ART.rglob('*') if p.is_file() and p.name!='CHECKPOINT.json')
    extra=[Path(__file__),Path(completion.__file__),v.ROOT/'scripts/fibo_research/transport_v413.py',v.ROOT/'scripts/fibo_research/reconcile_daily_sample_v413.py']
    r.save(ART/'CHECKPOINT.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'files':{str(p.relative_to(ART)):r.sha(p) for p in paths},
        'file_count':len(paths),'additional_sources':{str(p.relative_to(v.ROOT)):r.sha(p) for p in extra},'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    print(f'Universe audit report saved; {len(registry["entries"])} retained evidence entries; {len(paths)} protected files.',flush=True)


if __name__=='__main__':main()
