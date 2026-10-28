"""Render the six-year audit and append evidence without rewriting old records."""
import copy
from collections import defaultdict
from datetime import datetime,timezone
import gzip
import json
from pathlib import Path
import numpy as np
import research_v408 as q

r=q.r;ART=q.ART
PRIOR=r.ROOT/"artifacts/fibo_trend_short/research_v4_0_7"
NAMES={"reference_m6_fixed":"M6, khối lượng cố định", "m6_risk":"M6, khối lượng theo stop",
       "elite_sniper_risk":"Elite + Sniper", "sniper_risk":"Sniper",
       "sniper_horizon24":"Sniper, tối đa 24 giờ", "sniper_rr1_horizon24":"Sniper + RR≥1, tối đa 24 giờ"}


def diagnostics(result):
    with gzip.open(ART/"LEDGERS.json.gz","rt",encoding="utf8") as f:ledgers=json.load(f)
    out={"selection_use":False,"fresh_oos":False,"fixed_policies":{}}
    for spec in q.FAMILY:
        vid=spec["id"];out["fixed_policies"][vid]={}
        for cost in (40,60):
            scale=1.;coins=defaultdict(float);weeks=[];positive=[]
            for year in range(2020,2026):
                metric=result["annual"][str(year)][vid][f"{cost}bps_stress"]
                for trade in ledgers[f"{year}/{vid}/{cost}"]["ledger"]:coins[trade["symbol"]]+=scale*trade["pnl"]
                scale*=1+metric["return_pct"]/100
                weeks.extend(metric["weekly_returns"])
                if metric["return_pct"]>0:positive.append(year)
            total=result["fixed_policy_six_year"][vid][str(cost)]["return_pct"]
            assert abs(sum(coins.values())-total)<1e-8
            ranked=sorted(coins.items(),key=lambda x:(-x[1],x[0]))
            out["fixed_policies"][vid][str(cost)]={"weekly_ci":r.block_ci(weeks),"profitable_years":positive,
                "coin_pnl_contribution_pct_initial":dict(ranked),"top3_coins":ranked[:3],
                "pnl_contribution_excluding_top3_pct":total-sum(x[1] for x in ranked[:3]),
                "qualification":"Attribution only. Excluding coin contributions is not a counterfactual rerun: admission, sizing and compounding would change."}
    r.save(ART/"DIAGNOSTICS.json",out)
    return out


def registry(result):
    original=PRIOR/"MINI_ALPHA_REGISTRY.json"
    out=copy.deepcopy(r.read(original))
    out.update(status="SIX_YEAR_RETROSPECTIVE_EXTENSION_RESEARCH_ACTIVE_NO_SIGNOFF",data_ceiling="2025-12-31",fresh_oos=False,
               parent_registry={"path":str(original),"sha256":r.sha(original)},
               current_results={"path":str(ART/"RESULTS.json"),"sha256":r.sha(ART/"RESULTS.json")})
    pairs=[("MA407-01","m6_risk","reference_m6_fixed"),
           ("MA407-02","elite_sniper_risk","sniper_risk"),
           ("MA407-03","sniper_risk","m6_risk"),
           ("MA407-08","sniper_rr1_horizon24","sniper_horizon24"),
           ("MA407-09","sniper_horizon24","sniper_risk")]
    byid={e["id"]:e for e in out["entries"]}
    for aid,candidate,baseline in pairs:
        evidence={"comparison":[candidate,baseline],"cost_bps":40,"funding":"ADVERSE_1BP_8H","annual":{},"results_sha256":r.sha(ART/"RESULTS.json")}
        differences=[]
        for year,yearly in result["annual"].items():
            a=yearly[candidate]["40bps_stress"];b=yearly[baseline]["40bps_stress"]
            difference=np.asarray(a["weekly_returns"])-np.asarray(b["weekly_returns"])
            differences.extend(difference)
            evidence["annual"][year]={"candidate_return_pct":a["return_pct"],"baseline_return_pct":b["return_pct"],
                "candidate_max_dd_pct":a["max_dd_pct"],"baseline_max_dd_pct":b["max_dd_pct"],"candidate_trades":a["trades"],"baseline_trades":b["trades"],
                "paired_weekly_difference_ci":r.block_ci(difference)}
        evidence["six_year_aggregate"]={"candidate":result["fixed_policy_six_year"][candidate],"baseline":result["fixed_policy_six_year"][baseline]}
        evidence["paired_weekly_difference_ci"]=r.block_ci(differences)
        evidence["years_with_higher_return"]=sum(x["candidate_return_pct"]>x["baseline_return_pct"] for x in evidence["annual"].values())
        evidence["inference_limit"]="Retrospective extension of an already selected policy family; no global multiple-testing correction. A relative improvement is not evidence of absolute profitability. Annual state resets and 5-day embargo apply."
        entry=byid[aid]
        entry.setdefault("evidence_by_stage",{})["six_year_2020_2025"]=evidence
        entry["status_before_six_year_extension"]=entry["status"]
        entry["status"]="SIX_YEAR_RETROSPECTIVE_COMPARISON_RECORDED"
    for entry in out["entries"]:entry["usable_as_proven_alpha"]=False
    out["six_year_evidence_appended_to"]=[x[0] for x in pairs]
    out["trial_accounting"]={"prior_adaptive_variants_at_least":24,"new_parameter_variants":0,"existing_policies_replayed":6,"annual_scenario_nodes":72,
        "qualification":"Reusing configurations on additional years is another inspection of evidence, even though it adds no new parameter settings."}
    r.save(ART/"MINI_ALPHA_REGISTRY.json",out)
    return out


def render(result,inputs,verification,alpha,diagnostic):
    lines=["# Fibo Trend Short — kiểm tra mở rộng 2020–2025 (v4.0.8 research)","",
        "**Trạng thái: đã hoàn thành phép thử sáu năm; chưa cấp duyệt chiến lược để giao dịch thật.**",
        "",
        "Phạm vi dữ liệu: từ 01/01/2020 đến hết 31/12/2025. Không nạp quan sát năm 2026 để chạy backtest. Báo cáo này được kết xuất từ các tệp JSON cùng phiên bản; số lợi nhuận là thay đổi NAV danh mục sau chi phí, không phải tổng phần trăm của các lệnh.","",
        "## Phạm vi và cách so sánh","",
        "Sáu cấu hình đã có được cố định trước phép thử. Mỗi cấu hình chạy từng năm với NAV đầu năm 100, đặt lại trạng thái vị thế/wave/cooldown; chỉ tiêu sáu năm nối theo lãi kép các năm đó. Ngừng nhận lệnh mới trong 5 ngày cuối mỗi năm để tránh kết quả lệnh vượt ranh giới. Đây không phải một mô phỏng giữ nguyên trạng thái giao dịch xuyên suốt ngày giao năm.","",
        "Tín hiệu sử dụng nến đã đóng; mô phỏng vào ở giá mở cửa nến 5 phút sau quyết định. Khối lượng lệnh đã mở được giữ cố định. Hai mức chi phí khứ hồi là 40 và 60 bps; cả hai cộng funding bất lợi giả định cho short 1 bp mỗi 8 giờ. Funding này là kịch bản stress, không phải chuỗi funding thực tế. Mô phỏng vẫn dùng OHLC 5 phút, chưa mô phỏng sổ lệnh hoặc tác động của quy mô vốn.","",
        "Danh sách coin được chọn từng tháng bằng 63 ngày quá khứ, ít nhất 50 ngày có thanh khoản, lọc râu nến và xếp hạng trung vị khối lượng tiền giao dịch; lấy tối đa 50 mã. Không tạo dữ liệu trước khi coin xuất hiện. Thiên lệch do kho dữ liệu chỉ giữ các mã còn có tệp vẫn là một giới hạn chưa được loại bỏ.","",
        "| Năm | Mã có dữ liệu trong năm | Mã từng được chọn | Số thành viên/tháng nhỏ nhất–lớn nhất |",
        "|---|---:|---:|---:|"]
    for year,row in inputs["yearly_coverage"].items():
        lines.append(f"| {year} | {row['symbols_with_bars']} | {row['distinct_monthly_members']} | {row['minimum_monthly_members']}–{row['maximum_monthly_members']} |")
    lines.extend(["","‘Có dữ liệu’ không có nghĩa là có đủ cả năm. Đầu 2020 chưa đủ 50 ngày quá khứ nên một số tháng không giao dịch. Từ 2024, chỉ báo được khởi tạo từ lịch sử trước đó; vì vậy không kỳ vọng kết quả khớp một phép thử bắt đầu khởi tạo vào 2024. Đánh giá trọn năm 2025 cũng khác phép thử đặt lại trạng thái giữa hai nửa năm.","",
        "## Sáu cấu hình cố định","",
        "Lợi nhuận NAV theo năm và tổng nối sáu năm; đơn vị %. Mọi cột năm dùng chi phí 40 bps + funding stress.","",
        "| Cấu hình | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | Tổng 40 bps | Tổng 60 bps | MaxDD 40 bps |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for spec in q.FAMILY:
        vid=spec["id"];full=result["fixed_policy_six_year"][vid]
        years=" | ".join(f"{result['annual'][str(y)][vid]['40bps_stress']['return_pct']:+.2f}" for y in range(2020,2026))
        lines.append(f"| {NAMES[vid]} | {years} | {full['40']['return_pct']:+.2f} | {full['60']['return_pct']:+.2f} | {full['40']['max_dd_pct']:.2f} |")
    lines.extend(["","| Cấu hình | Số năm dương ở 40 bps | CI 95% lợi nhuận tuần trung bình toàn kỳ, 40 bps |","|---|---:|---|"])
    for spec in q.FAMILY:
        vid=spec["id"];node=diagnostic["fixed_policies"][vid]["40"];ci=node["weekly_ci"]["ci95_pct"]
        lines.append(f"| {NAMES[vid]} | {len(node['profitable_years'])}/6 | [{ci[0]:+.4f}%; {ci[1]:+.4f}%] |")
    lines.extend(["","Bảng trên là so sánh hồi cứu, không dùng để chọn cấu hình tốt nhất sau khi xem năm kiểm tra. Một tổng lợi nhuận dương có thể tập trung vào vài năm và không đủ để xác nhận lợi thế.","",
        "## Kiểm định cuốn chiếu","",
        "Mỗi năm kiểm tra chỉ được chọn cấu hình dựa trên các năm trước: có ít nhất hai năm huấn luyện và 60 lệnh, mỗi năm huấn luyện dương ở 40 bps, tổng ở 60 bps không âm, drawdown từng năm không quá 15%, không có khoảng trống dữ liệu thực thi ở lệnh nhận. Xếp hạng bằng lợi nhuận tổng 60 bps trừ MaxDD tổng 60 bps. Nếu không cấu hình nào đạt thì giữ tiền (CASH). Khóa lựa chọn được lưu trước khi tính kết quả năm kiểm tra.","",
        "| Năm kiểm tra | Các năm dùng chọn | Lựa chọn đã khóa | Lệnh | NAV 40 bps | NAV 60 bps |",
        "|---|---|---|---:|---:|---:|"])
    for year,lock in result["walk_forward_locks"].items():
        vid=lock["selected"]
        n=0 if vid=="CASH" else result["annual"][year][vid]["40bps_stress"]["trades"]
        a=0 if vid=="CASH" else result["annual"][year][vid]["40bps_stress"]["return_pct"]
        b=0 if vid=="CASH" else result["annual"][year][vid]["60bps_stress"]["return_pct"]
        lines.append(f"| {year} | {', '.join(lock['training_years'])} | {NAMES.get(vid,vid)} | {n} | {a:+.2f}% | {b:+.2f}% |")
    lines.extend(["","| Chuỗi kiểm tra 2022–2025 | NAV nối | MaxDD | Lệnh | CI 95% lợi nhuận tuần trung bình |","|---|---:|---:|---:|---|"])
    for cost,out in result["walk_forward_oos"].items():
        ci=out["weekly_ci"]["ci95_pct"]
        lines.append(f"| {cost} bps + funding stress | {out['return_pct']:+.2f}% | {out['max_dd_pct']:.2f}% | {out['trades']} | [{ci[0]:+.4f}%; {ci[1]:+.4f}%] |")
    lines.extend(["","CI dùng bootstrap khối 4 tuần, 5.000 mẫu, bao gồm tuần không giao dịch và tuần cuối không đủ 7 ngày. CI chưa điều chỉnh cho toàn bộ các lần thử cấu hình; nếu chuỗi chỉ giữ tiền thì CI bằng 0 không phải bằng chứng có alpha.","",
        "**OOS chưa từng đụng tới: không.** Họ cấu hình đã được phát triển trên 2024 và xem kết quả 2025 ở các vòng trước. Các khóa cuốn chiếu bảo vệ việc lựa chọn cục bộ theo thời gian trong phép chạy này, nhưng không xóa được thông tin tương lai đã ảnh hưởng đến việc hình thành họ cấu hình. Vì vậy đây là kiểm tra hồi cứu độ bền qua nhiều giai đoạn; không đổi nhãn dữ liệu cũ thành OOS mới.","",
        "## Nhật ký mini-alpha","",
        f"Giữ nguyên {len(alpha['entries'])} giả thuyết đã ghi, kể cả giả thuyết thất bại; bổ sung đối chiếu sáu năm vào {len(alpha['six_year_evidence_appended_to'])} mục. Chưa mục nào được gắn nhãn alpha đã chứng minh.","",
        "| So sánh | Số năm lợi nhuận tốt hơn mốc đối chiếu | CI 95% chênh lệch lợi nhuận tuần trung bình |","|---|---:|---|"])
    for entry in alpha["entries"]:
        evidence=entry.get("evidence_by_stage",{}).get("six_year_2020_2025")
        if not evidence:continue
        a,b=evidence["comparison"];ci=evidence["paired_weekly_difference_ci"]["ci95_pct"]
        lines.append(f"| {NAMES[a]} so với {NAMES[b]} | {evidence['years_with_higher_return']}/6 | [{ci[0]:+.4f}%; {ci[1]:+.4f}%] |")
    lines.extend(["","Các so sánh phản ánh toàn bộ chính sách danh mục, gồm thay đổi số lệnh được nhận sau giới hạn vị thế; chúng không tách riêng tác động nhân quả của một chỉ báo. Quy mô theo stop là kiểm soát rủi ro, không tự nó là alpha.","",
        "## Kiểm chứng và quyết định","",
        f"- {verification['tests']['tests']} kiểm thử qua; {verification['tests']['failures']} thất bại, {verification['tests']['errors']} lỗi, {verification['tests']['skipped']} bỏ qua.",
        f"- {verification['causal_candidates_checked']:,} ứng viên đã kiểm tra ranh giới quyết định/vào lệnh và tư cách trong danh sách tháng.",
        f"- {verification['ledger_nodes_verified']} kịch bản danh mục, {verification['scenario_trade_records_verified']:,} bản ghi giao dịch theo kịch bản đã đối chiếu khối lượng, phí, funding stress, PnL, đường NAV và drawdown. Đây không phải số giao dịch độc lập.",
        "- Tất cả bảng xếp hạng tháng được tính lại từ dữ liệu quá khứ; dữ liệu và tệp lịch sử được kiểm chứng bằng SHA256.",
        "- Không cấp duyệt giao dịch thật. Mở rộng lịch sử làm rõ độ bền và điểm yếu; không thay thế dữ liệu kiểm tra chưa dùng, funding thực, dữ liệu mã hủy niêm yết hoặc kiểm tra khớp lệnh thực tế.","",
        "Nguồn cùng thư mục: `PROTOCOL.json`, `history/DATA_MANIFEST.json`, `history/MEMBERSHIP.json`, `RESULTS.json`, `LEDGERS.json.gz`, `LOCK_TEST_*.json`, `MINI_ALPHA_REGISTRY.json`, `DIAGNOSTICS.json`, `INPUT_VERIFICATION.json`, `INDEPENDENT_VERIFICATION.json`. Phân bổ đóng góp PnL theo coin trong DIAGNOSTICS là phân tích kế toán, không phải chạy lại chiến lược sau khi loại coin tốt nhất. Các báo cáo phiên bản cũ được giữ nguyên.",""])
    return "\n".join(lines)


def main():
    result=r.read(ART/"RESULTS.json");inputs=r.read(ART/"history/DATA_MANIFEST.json");verification=r.read(ART/"INDEPENDENT_VERIFICATION.json")
    assert verification["all_checks_passed"] and verification["results_sha256"]==r.sha(ART/"RESULTS.json")
    diagnostic=diagnostics(result)
    alpha=registry(result)
    content=render(result,inputs,verification,alpha,diagnostic)
    (ART/"REPORT.md").write_text(content,encoding="utf8")
    assert (ART/"REPORT.md").read_text(encoding="utf8")==render(r.read(ART/"RESULTS.json"),r.read(ART/"history/DATA_MANIFEST.json"),r.read(ART/"INDEPENDENT_VERIFICATION.json"),r.read(ART/"MINI_ALPHA_REGISTRY.json"),r.read(ART/"DIAGNOSTICS.json"))
    r.save(ART/"REPORT_CONSISTENCY.json",{"all_passed":True,"method":"Deterministic full-document regeneration from versioned JSON; every displayed number is derived from those files.",
        "source_hashes":{p:r.sha(ART/p) for p in ["RESULTS.json","history/DATA_MANIFEST.json","INDEPENDENT_VERIFICATION.json","MINI_ALPHA_REGISTRY.json","DIAGNOSTICS.json","REPORT.md"]},
        "renderer_sha256":r.sha(__file__)})
    r.save(ART/"PROGRESS.json",{"stage":"six_year_extension_verified_and_documented","goal_complete":False,"data_ceiling":"2025-12-31",
        "fresh_oos":False,"post_2025_observations_loaded":0,"mini_alpha_entries":len(alpha["entries"]),"live_signoff":"NOT_GRANTED",
        "next_action":"Assess six-year failure modes without reclassifying reused history as fresh OOS; prioritize missing historical universe and execution evidence before further adaptive parameter search."})
    files={str(p.relative_to(ART)):r.sha(p) for p in sorted(ART.rglob("*")) if p.is_file() and p.name!="CHECKPOINT.json"}
    r.save(ART/"CHECKPOINT.json",{"created_at_utc":datetime.now(timezone.utc).isoformat(),"file_count":len(files),"files":files,
        "additional_sources":{str(p.relative_to(r.ROOT)):r.sha(p) for p in [Path(__file__),Path(__file__).with_name("verify_research_v408.py")]},"goal_complete":False})
    print(json.dumps({"report":str(ART/"REPORT.md"),"checkpoint_files":len(files),"mini_alpha_entries":len(alpha["entries"])}))


if __name__=="__main__":main()
