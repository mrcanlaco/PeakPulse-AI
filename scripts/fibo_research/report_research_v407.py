"""Persist both useful observations and failed mini-alpha hypotheses."""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import shutil

import numpy as np
import research_v407 as r

PAIRS = {
    "MA407-01": ("m6_risk", "reference_m6_fixed"),
    "MA407-02": ("elite_risk", "m6_risk"),
    "MA407-03": ("sniper_risk", "m6_risk"),
    "MA407-04": ("btc_weak_risk", "m6_risk"),
    "MA407-05": ("score68_risk", "m6_risk"),
    "MA407-06": ("rr1_risk", "m6_risk"),
    "MA407-07": ("tp1_risk", "m6_risk"),
}


def main(stage):
    directory = r.ART / stage
    payload = r.read(directory / "RESULTS.json")
    rows = payload["results"]
    registry = r.read(r.ART / "MINI_ALPHA_REGISTRY.json")
    for entry in registry["entries"]:
        candidate, baseline = PAIRS[entry["id"]]
        if candidate not in rows or baseline not in rows:
            continue
        a, b = rows[candidate]["40bps_stress"], rows[baseline]["40bps_stress"]
        weekly_diff = np.asarray(a["weekly_returns"])-np.asarray(b["weekly_returns"])
        evidence = {
            "stage": stage, "comparison": [candidate, baseline], "cost_bps": 40, "funding": "ADVERSE_1BP_8H",
            "candidate_return_pct": a["return_pct"], "baseline_return_pct": b["return_pct"],
            "candidate_max_dd_pct": a["max_dd_pct"], "baseline_max_dd_pct": b["max_dd_pct"],
            "candidate_trades": a["trades"], "baseline_trades": b["trades"],
            "paired_weekly_difference_ci": r.block_ci(weekly_diff),
            "qualification": rows[candidate]["qualifies"],
            "results_sha256": r.sha(directory / "RESULTS.json"),
            "inference_limit": "Exploratory matched comparison; not adjusted for all past trials; risk/cap change is not standalone alpha.",
        }
        entry.setdefault("evidence_by_stage", {})[stage] = evidence
        if entry["id"] == "MA407-01":
            entry["status"] = "RISK_CONTROL_EVIDENCE" if a["max_dd_pct"] < b["max_dd_pct"] else "NO_RISK_IMPROVEMENT"
        elif a["return_pct"] > b["return_pct"]:
            entry["status"] = "PROVISIONAL_DEVELOPMENT_OBSERVATION" if stage == "development" else "RETROSPECTIVE_OOS_OBSERVATION"
        else:
            entry["status"] = "NOT_SUPPORTED_IN_THIS_COMPARISON"
        entry["usable_as_proven_alpha"] = False
    registry["status"] = stage+"_evidence_recorded"
    registry["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    r.save(r.ART / "MINI_ALPHA_REGISTRY.json", registry)
    r.save(directory / "MINI_ALPHA_EVIDENCE.json", registry)

    with gzip.open(directory / "LEDGERS.json.gz", "rt", encoding="utf-8") as fh:
        ledgers = json.load(fh)
    for name, value in ledgers.items():
        records = value["ledger"]
        cash = sum(x["pnl"] for x in records)
        final = value["curve"][-1][1]
        assert abs(final-100-cash) < 1e-8
        assert len({x["id"] for x in records}) == len(records)
        for x in records:
            assert abs(x["notional"]*x["gross_return"]-x["fees"]+x["funding"]-x["pnl"]) < 1e-8
    protected = r.read(r.ART / "HISTORICAL_PRESERVATION.json")
    changes = [name for name, digest in protected.items() if r.sha(r.ROOT / name) != digest]
    if changes:
        raise AssertionError(f"Historical files changed: {changes}")
    data = r.read(directory / "DATA_MANIFEST.json")
    for symbol, row in data["inputs"].items():
        assert r.sha(directory / "bars_5m" / f"{symbol}.parquet") == row["snapshot_sha256"]
        assert r.utc(row["last_open"]) < r.utc(data["end_exclusive"]) <= r.LIMIT
    snapshot = directory / "source_snapshot"
    snapshot.mkdir(exist_ok=True)
    sources = [Path(r.__file__), Path(__file__), r.ROOT / "tests/unit/fibo_short/test_research_v407.py",
               r.ROOT / "scripts/fibo_research/universe_reaudit_v402_worker.py",
               r.ROOT / "scripts/fibo_research/verify_red_team_audit_2026.py",
               r.ROOT / "src/dao_vang/fibo_short/detector.py",
               r.ROOT / "src/dao_vang/fibo_short/backtest.py", r.ROOT / "src/dao_vang/config/settings.py"]
    for source in sources:
        relative = source.relative_to(r.ROOT)
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    audit = {"stage": stage, "historical_files_preserved": len(protected), "bounded_inputs_unchanged": len(data["inputs"]),
             "ledger_nodes_reconciled": len(ledgers), "all_cash_and_ids_reconciled": True,
             "max_loaded_open_time": max(v["last_open"] for v in data["inputs"].values()),
             "stage_end_exclusive": data["end_exclusive"], "post_2025_observations_loaded": 0,
             "final_oos_opened": (r.ART / "final_oos/DATA_MANIFEST.json").exists(),
             "source_sha256": {str(p.relative_to(r.ROOT)): r.sha(p) for p in sources},
             "results_sha256": r.sha(directory / "RESULTS.json"), "ledgers_sha256": r.sha(directory / "LEDGERS.json.gz")}
    r.save(directory / "VERIFICATION.json", audit)
    lines = ["# Nghiên cứu Fibo Short và sổ mini alpha", "",
        f"Giai đoạn đã đánh giá: **{stage}**, từ {data['start']} đến trước {data['end_exclusive']}. "
        "Lợi nhuận dưới đây tính trên NAV danh mục, sau chi phí và kịch bản short trả funding 1 bp mỗi 8 giờ. Chưa phê duyệt giao dịch thật.", "",
        "Dữ liệu 2025 từng được xem trong nghiên cứu lịch sử. OOS của vòng mới là phép tách theo thời gian cho quy trình hiện tại, không phải dữ liệu chưa từng được dự án sử dụng. Không nạp quan sát giá hay funding từ năm 2026.", "",
        "| Cấu hình | Lệnh ở 40 bps | NAV 40 bps % | MaxDD 40 bps % | NAV 60 bps % | MaxDD 60 bps % | Qua cổng |",
        "|---|---:|---:|---:|---:|---:|---|" ]
    for vid, row in rows.items():
        a,b = row["40bps_stress"],row["60bps_stress"]
        lines.append(f"| {vid} | {a['trades']} | {a['return_pct']:.2f} | {a['max_dd_pct']:.2f} | {b['return_pct']:.2f} | {b['max_dd_pct']:.2f} | {'Đạt' if row['qualifies'] else 'Chưa đạt'} |")
    lines += ["", "## Ghi nhận mini alpha", "",
        "Các ghi nhận được giữ lại cả khi không đạt. Cải thiện rủi ro không tự chứng minh lợi thế dự báo; các khoảng tin cậy ở đây chưa điều chỉnh cho việc thử nhiều giả thuyết.", ""]
    for entry in registry["entries"]:
        evidence = entry.get("evidence_by_stage", {}).get(stage)
        if not evidence:
            continue
        lines.append(f"- **{entry['id']}** — {entry['hypothesis_vi']}. Trạng thái: `{entry['status']}`. "
                     f"NAV {evidence['candidate_return_pct']:.2f}% so với {evidence['baseline_return_pct']:.2f}%; "
                     f"MaxDD {evidence['candidate_max_dd_pct']:.2f}% so với {evidence['baseline_max_dd_pct']:.2f}%.")
    lines += ["", "## Điều kiện thực thi và giới hạn", "",
        "Tín hiệu H1 đã đóng; vào tại giá mở nến 5 phút sau đó 5 phút. Stop được xét trước TP, stop mới kéo được kiểm tra lại cùng nến và gap qua stop dùng giá mở bất lợi hơn. Giữ khối lượng cố định sau khi vào; phí được trừ ngay lúc vào và khi đóng. Cấm vào trong 5 ngày cuối mỗi tập để tránh nhãn giao dịch vượt ranh giới.", "",
        "Nhóm risk giới hạn tổn thất stop cộng ngân sách chi phí 60 bps ở 0,5% equity/lệnh, tối đa 20% notional/lệnh, 5 vị thế và 2% stop-risk tổng. Đây là cấu hình nghiên cứu, chưa phải mức rủi ro được chấp thuận cho tài khoản thật.", "",
        "Danh sách mã phụ thuộc các tệp lịch sử còn sẵn có; chưa có registry đầy đủ cho coin hủy niêm yết. Funding là stress giả định, không phải chuỗi funding thực. Chi phí là ngân sách trên notional đầu vào; chưa mô phỏng sổ lệnh hoặc tác động thị trường. Bootstrap lấy block bốn tuần và giữ tuần không giao dịch; tuần cuối có thể là tuần lẻ.", "",
        f"Đối chiếu tiền và mã lệnh đạt trên {len(ledgers)} sổ; {len(data['inputs'])} tệp dữ liệu đã giới hạn thời gian không đổi; {len(protected)} tệp hồ sơ cũ giữ nguyên.", ""]
    (directory / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("--stage", choices=r.WINDOWS, default="development")
    main(p.parse_args().stage)
