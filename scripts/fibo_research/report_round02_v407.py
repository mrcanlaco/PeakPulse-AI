"""Verify and render all completed stages without reading unopened data."""
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import shutil
import research_v407 as r
from research_round02_v407 import ART, BASE


def main():
    report=["# Fibo Short v4.0.7 và các mini alpha", "",
        "Nhánh nghiên cứu chỉ dùng quan sát đến hết 2025. Phát triển trên 2024, chọn ứng viên trên tháng 1 đến tháng 6 năm 2025, kiểm định cuối trên tháng 7 đến tháng 12 năm 2025. Mỗi giai đoạn chỉ được mở khi lựa chọn đã khóa.", "",
        "Dữ liệu 2025 từng được dự án sử dụng trong nghiên cứu trước. OOS dưới đây là tách theo thời gian của quy trình mới, không phải dữ liệu hoàn toàn chưa từng được xem. Chưa phê duyệt giao dịch thật.", ""]
    evidence={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"stages":{},"live_signoff":"NOT_GRANTED","goal_complete":False}
    registry=r.read(BASE/"MINI_ALPHA_REGISTRY.json")
    for stage in r.WINDOWS:
        d=ART/stage
        if not (d/"RESULTS.json").exists(): continue
        data_dir=BASE/stage if stage=="development" else d
        payload=r.read(d/"RESULTS.json"); rows=payload["results"]
        with gzip.open(d/"LEDGERS.json.gz","rt",encoding="utf8") as f: ledgers=json.load(f)
        reconciliation=[]
        for name,node in ledgers.items():
            entries=node["ledger"]; ending=node["curve"][-1][1]
            assert len({x["id"] for x in entries})==len(entries)
            assert abs(ending-100-sum(x["pnl"] for x in entries))<1e-8
            for x in entries:
                assert abs(x["notional"]*x["gross_return"]-x["fees"]+x["funding"]-x["pnl"])<1e-8
                assert x["entry_ts"]<int(r.utc(r.WINDOWS[stage][1]).timestamp())
                assert x["exit_ts"]<=int(r.utc(r.WINDOWS[stage][1]).timestamp())
            reconciliation.append(name)
        data=r.read(data_dir/"DATA_MANIFEST.json")
        for sym,row in data["inputs"].items():
            assert r.sha(data_dir/"bars_5m"/f"{sym}.parquet")==row["snapshot_sha256"]
            assert r.utc(row["last_open"])<r.utc(data["end_exclusive"])<=r.LIMIT
        evidence["stages"][stage]={"ledger_nodes":len(reconciliation),"cash_and_ids_passed":True,
            "bounded_input_files_unchanged":len(data["inputs"]),"last_loaded_open":max(x["last_open"] for x in data["inputs"].values()),
            "results_sha256":r.sha(d/"RESULTS.json"),"ledgers_sha256":r.sha(d/"LEDGERS.json.gz"),
            "qualified_variants":[k for k,v in rows.items() if v["qualifies"]]}
        report += [f"## {stage}", "", "Lợi nhuận là thay đổi NAV danh mục; funding stress giả định short trả 1 bp mỗi 8 giờ. Chi phí khứ hồi 40 hoặc 60 bps trên notional đầu vào.", "",
            "| Cấu hình | Lệnh 40 bps | NAV 40 bps % | MaxDD 40 bps % | NAV 60 bps % | MaxDD 60 bps % | Qua cổng |",
            "|---|---:|---:|---:|---:|---:|---|"]
        for vid,row in rows.items():
            a,b=row["40bps_stress"],row["60bps_stress"]
            report.append(f"| {vid} | {a['trades']} | {a['return_pct']:.2f} | {a['max_dd_pct']:.2f} | {b['return_pct']:.2f} | {b['max_dd_pct']:.2f} | {'Đạt' if row['qualifies'] else 'Chưa đạt'} |")
            ci=a["weekly_ci"]
            if vid!="reference_m6_fixed" and ci["available"]:
                evidence["stages"][stage].setdefault("weekly_ci95_pct",{})[vid]=ci["ci95_pct"]
        if stage=="final_oos":
            for vid,row in rows.items():
                if vid=="reference_m6_fixed": continue
                ci=row["40bps_stress"]["weekly_ci"]
                if ci["available"]:
                    low,high=ci["ci95_pct"]
                    report += ["",f"Ứng viên `{vid}` có khoảng tin cậy 95% của lợi nhuận trung bình tuần từ {low:.4f}% đến {high:.4f}%. "
                               +("Khoảng này chứa 0 nên không vượt cổng xác nhận lợi thế đã đăng ký." if low<=0<=high else "Đối chiếu kết quả này với toàn bộ điều kiện đã đăng ký trước khi kết luận.")]
        report += ["", "Khoảng tin cậy dùng bootstrap block bốn tuần trên lợi nhuận danh mục theo tuần, gồm tuần không giao dịch. Kết quả phát triển chịu ảnh hưởng chọn lựa nhiều mô hình; không diễn giải khoảng tin cậy này thành xác suất chiến lược chắc chắn sinh lời.", ""]
        for item in registry["entries"]:
            matching={vid:rows[vid] for vid in item["variants"] if vid in rows}
            if matching:
                item.setdefault("evidence_by_stage",{})[f"round02_{stage}"]=matching
                if stage=="validation": item["status"]="PASSED_VALIDATION_PENDING_FINAL" if any(v["qualifies"] for v in matching.values()) else "FAILED_VALIDATION_GATE"
                if stage=="final_oos": item["status"]="PASSED_RETROSPECTIVE_FINAL_GATE" if any(v["qualifies"] for v in matching.values()) else "FAILED_FINAL_GATE"
                item["usable_as_proven_alpha"]=False
    historical=r.read(BASE/"HISTORICAL_PRESERVATION.json")
    assert all(r.sha(r.ROOT/k)==v for k,v in historical.items())
    evidence["historical_files_preserved"]=len(historical)
    evidence["final_oos_opened"]=(ART/"final_oos/DATA_MANIFEST.json").exists()
    evidence["post_2025_observations_loaded"]=0
    if (ART/"final_oos/RESULTS.json").exists():
        final=r.read(ART/"final_oos/RESULTS.json")["results"]
        passed=[k for k,v in final.items() if v["qualifies"]]
        evidence["statistical_signoff"]="RETROSPECTIVE_GATE_PASSED_PENDING_ROBUSTNESS" if passed else "NOT_GRANTED_FINAL_GATE_FAILED"
    else:
        evidence["statistical_signoff"]="NOT_GRANTED_FINAL_OOS_NOT_EVALUATED"
    report += ["## Mini alpha được lưu", "",
        "Sổ lưu cả giả thuyết có triển vọng và giả thuyết thất bại. Khối lượng theo stop là kiểm soát rủi ro; nó không tự tạo lợi thế dự báo. Bộ lọc phá đáy H1 và giới hạn giữ lệnh 24 giờ phải được đánh giá theo đúng giai đoạn ghi kèm.", "",
        "| Mã | Giả thuyết | Trạng thái |", "|---|---|---|"]
    for entry in registry["entries"]:
        report.append(f"| {entry['id']} | {entry['hypothesis_vi']} | {entry['status']} |")
    report += ["", "## Giới hạn còn lại", "",
        f"Bảng kết quả ở trên thuộc hai vòng đầu với 18 cấu hình. Sổ mini alpha toàn nhánh hiện ghi {registry.get('cumulative_variant_count',18)} cấu hình đã thử. Việc chọn ứng viên có thể làm kết quả phát triển lạc quan. Quy tắc không được chỉnh lại bằng kết quả kiểm định cuối. Vũ trụ chỉ gồm mã có tệp lịch sử sẵn có, chưa khôi phục đầy đủ mã hủy niêm yết.", "",
        "Mô phỏng vào sau tín hiệu 5 phút, xử lý stop trước TP trên nến 5 phút, giữ nguyên khối lượng và đối chiếu từng dòng tiền. Funding hiện là stress giả định; chưa đối chiếu đầy đủ funding lịch sử, sổ lệnh, tác động thị trường và điều kiện thực thi thật. Không có lệnh thật nào được gửi.", "",
        f"Đã bảo toàn {len(historical)} tệp hồ sơ cũ. Kết luận thống kê hiện tại: `{evidence['statistical_signoff']}`.", ""]
    r.save(BASE/"MINI_ALPHA_REGISTRY.json",registry)
    r.save(ART/"VERIFICATION.json",evidence)
    (ART/"REPORT.md").write_text("\n".join(report),encoding="utf8")
    snapshot=ART/"source_snapshot"
    for path in [Path(r.__file__),Path(__file__),r.ROOT/"scripts/fibo_research/research_round02_v407.py",r.ROOT/"tests/unit/fibo_short/test_research_v407.py"]:
        target=snapshot/path.relative_to(r.ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    r.save(ART/"ARTIFACT_MANIFEST.json",{str(p.relative_to(ART)):r.sha(p) for p in ART.rglob("*") if p.is_file() and p.name!="ARTIFACT_MANIFEST.json"})
    print(json.dumps(evidence,ensure_ascii=False))


if __name__=="__main__":main()
