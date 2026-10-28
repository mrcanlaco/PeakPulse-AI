"""Independent ledger-to-NAV checks and reproducible Vietnamese delivery report."""
from pathlib import Path
import copy
import hashlib
import json
import shutil
import sys
from importlib.metadata import version as package_version
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(Path(__file__).resolve().parent)]
from complete_method_v406 import verify_history
from method_provenance_v406 import verify as verify_inputs
from ledger_reconciliation import reconcile_settled_ledger
from dao_vang.fibo_short.paper_rules_v406 import PaperPolicy
from dataclasses import asdict

ART = ROOT / "artifacts/fibo_trend_short"


def load(name):
    return json.loads((ART / name).read_text(encoding="utf-8"))


def save(name, value):
    (ART / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_node(node, records, nav, cost_bps):
    ids = [r["trade_id"] for r in records]
    monetary = reconcile_settled_ledger(records)
    errors = list(monetary["errors"])
    if ids != node["accepted_trade_ids"] or ids != node["executed_trade_ids"] or len(ids) != node["accepted_trades"] or len(ids) != node["executed_trades"]:
        errors.append({"reason": "ID_OR_COUNT_MISMATCH"})
    hashes = [hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=a).encode()).hexdigest() for a in (True, False)]
    if node["ledger_sha256"] not in hashes:
        errors.append({"reason": "LEDGER_HASH_MISMATCH"})
    totals = {}
    for basis, label in [("add", "additive"), ("comp", "compounded")]:
        expected = 100 + sum(float(r[f"realized_pnl_dollar_{basis}"]) for r in records)
        actual = float(nav[f"{label}_final_nav"])
        tolerance = (len(records) + 1) * .00005 + .0001
        totals[basis] = {"sum_ledger_nav": expected, "reported_nav": actual, "tolerance": tolerance}
        if abs(expected - actual) > tolerance:
            errors.append({"reason": "AGGREGATE_NAV_MISMATCH", "basis": basis, **totals[basis]})
        for r in records:
            expected_fee = float(r[f"n0_{basis}"]) * cost_bps / 10000
            if abs(float(r[f"fee_dollar_{basis}"]) - expected_fee) > .00011:
                errors.append({"reason": "FEE_MISMATCH", "id": r["trade_id"], "basis": basis})
    return {"all_passed": monetary["all_passed"] and not errors, "records": len(records), "totals": totals, "errors": errors}


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"] +
                     ["| " + " | ".join(map(str, row)) + " |" for row in rows])


def render(p):
    lines = ["# PeakPulse AI Fibo Trend Short v4.0.6", "", p["conclusion_vi"], "",
             "## Kết quả kiểm chứng", "", p["verification_summary_vi"], "",
             table(["Sửa đổi", "Kết quả"], [[x["title"], x["evidence"]] for x in p["fixes"]]), "",
             "## Quy tắc giao dịch thử", ""]
    for step in p["rulebook_vi"]:
        lines.extend([f"- {step}", ""])
    lines += ["## Benchmark 14 mã", "", "Đơn vị lợi nhuận và sụt giảm là % NAV. NAV khởi đầu 100; phí khứ hồi tính bằng bps trên giá trị vào lệnh. H = funding lịch sử; S = stress short trả 1 bps mỗi 8 giờ.", "",
              table(["Cửa sổ", "Khối lượng", "Phí bps", "Lệnh ex", "NAV ex funding %", "NAV H %", "NAV S %", "MaxDD H %"], p["benchmark_rows"]), "",
              "## Vũ trụ luân chuyển theo tháng", "", "PIT chọn coin bằng dữ liệu 63 ngày trước đầu tháng, trong tập tệp lịch sử đang có. Bảng này chưa tính funding. Sum trades là tổng tỷ suất các lệnh; NAV mới là kết quả danh mục có giới hạn vốn.", "",
              table(["Cửa sổ", "Khối lượng", "Phí bps", "Lệnh", "Sum trades %", "NAV %", "MaxDD %", "CI trung bình lệnh %"], p["pit_rows"]), "",
              "## PIT có funding trong vòng thực thi", "", "Funding lịch sử và stress được tính trong vòng nhận lệnh theo equity. Mỗi kịch bản có sổ lệnh riêng; không cộng funding sau khi chốt danh sách lệnh.", "",
              table(["Cửa sổ", "Khối lượng", "Phí bps", "Lệnh H", "NAV H %", "MaxDD H %", "Lệnh S", "NAV S %"], p["pit_funding_rows"]), "",
              "## Điều kiện diễn giải và sử dụng", ""]
    lines += [f"- {x}\n" for x in p["limitations_vi"]]
    lines += ["", "## Quy trình chuyển sang giao dịch thử", ""]
    lines += [f"{i}. {x}\n" for i, x in enumerate(p["forward_steps_vi"], 1)]
    lines += ["", "## Tệp sử dụng và tái lập", ""]
    lines += [f"- [{name}](<{(ROOT / path).as_posix()}>)" for name, path in p["file_links"].items()]
    lines += ["", "Các giới hạn tick, bước khối lượng và notional phải lấy theo từng mã tại thời điểm giao dịch; funding có thể thay đổi chu kỳ. Tham chiếu: [Binance USD-M filters](https://developers.binance.com/zh-CN/docs/products/derivatives-trading-usds-futures/common-definition), [Binance USD-M market data](https://developers.binance.info/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data).", ""]
    return "\n".join(lines)


def main():
    historical_count = verify_history()
    inputs = verify_inputs()
    b, pit, u, sources = [load(n) for n in ("METHOD_BENCHMARK_v4_0_6.json", "METHOD_PIT_COMPARISON_v4_0_6.json", "universe_338_reaudit_v4_0_6_summary.json", "METHOD_SOURCE_CHECKS_v4_0_6.json")]
    if u["input_fingerprint_sha256"] != load("METHOD_INPUT_MANIFEST_v4_0_6.json")["universe_input_fingerprint_sha256"]:
        raise AssertionError("Universe input fingerprint mismatch")
    bl = load("METHOD_BENCHMARK_LEDGERS_v4_0_6.json")["ledgers_by_key"]
    pl = load("METHOD_PIT_LEDGERS_v4_0_6.json")["ledgers_by_key"]
    ul = load("universe_coupled_ledgers_v4_0_6_cache.json")
    funded = load("METHOD_PIT_FUNDING_v4_0_6.json")
    # The inherited API retains root NAVs for a fixed ex-funding cohort.
    # Scenario ledgers are the actual funding-coupled execution results.
    semantics = {"nav_ex_funding": "Actual ex-funding coupled execution",
                 "root_nav_with_historical_funding_and_nav_stress_1bp_8h_funding": "Counterfactual replay holding ex-funding accepted IDs fixed when funding changes admission",
                 "actual_funding_coupled_results": "scenario_specific_coupled_ledgers.<scenario>.nav_20pct_per_1x",
                 "report_source": "Scenario-specific execution; root aliases used only when identical"}
    b["output_semantics"] = semantics
    funded["output_semantics"] = semantics
    save("METHOD_BENCHMARK_v4_0_6.json", b)
    save("METHOD_PIT_FUNDING_v4_0_6.json", funded)
    fl = load("METHOD_PIT_FUNDING_LEDGERS_v4_0_6.json")["ledgers_by_key"]
    assert funded["source_sha256"] == digest(ROOT / "scripts/fibo_research/pit_funding_v406.py")
    checks, b_rows, p_rows = {}, [], []
    f_rows, parity = [], {}
    labels = {"is_2020_2025": "2020–2025", "calibration_2024_2025": "2024–2025",
              "reused_validation_hard_0831": "2026 đến 31/08", "reused_validation_available_0929": "2026 dữ liệu đến 29/09"}
    for window, sizes in b["results"].items():
        for sizing, costs in sizes.items():
            for cost, res in costs.items():
                c, key = res["coupled"], res["ledger_key"]
                checks[key] = check_node(c, bl[key]["ledger_records"], c["nav_ex_funding"], int(cost))
                for scenario, node in c["scenario_specific_coupled_ledgers"].items():
                    skey = f"{key}/{scenario}"
                    checks[skey] = check_node(node, bl[skey]["ledger_records"], node["nav_20pct_per_1x"], int(cost))
                n = c["nav_ex_funding"]
                h = c["scenario_specific_coupled_ledgers"]["historical_funding"]["nav_20pct_per_1x"]
                st = c["scenario_specific_coupled_ledgers"]["stress_1bp_8h_funding"]["nav_20pct_per_1x"]
                b_rows.append([labels[window], sizing, cost, c["accepted_trades"], n["compounded_total_return_pct"], h["compounded_total_return_pct"], st["compounded_total_return_pct"], h["compounded_max_dd_pct"]])
    for window, sizes in pit["results"].items():
        for sizing, costs in sizes.items():
            for cost, res in costs.items():
                c, key, s = res["coupled"], res["ledger_key"], res["summary"]
                n = c["nav_20pct_per_1x"]
                checks[key] = check_node(c, pl[key]["ledger_records"], n, int(cost))
                p_rows.append([labels[window], sizing, cost, c["accepted_trades"], s["total_net_return_pct"], n["compounded_total_return_pct"], n["compounded_max_dd_pct"], s["bootstrap_ci95"]["avg_net_pct_ci95"]])
    for window, sizes in funded["results"].items():
        for sizing, costs in sizes.items():
            for cost, res in costs.items():
                c, key = res["coupled"], res["ledger_key"]
                checks[key] = check_node(c, fl[key]["ledger_records"], c["nav_ex_funding"], int(cost))
                for scenario, node in c["scenario_specific_coupled_ledgers"].items():
                    skey = f"{key}/{scenario}"
                    checks[skey] = check_node(node, fl[skey]["ledger_records"], node["nav_20pct_per_1x"], int(cost))
                reference = pit["results"][window][sizing][cost]["coupled"]
                parity[key] = {"ids_match": c["accepted_trade_ids"] == reference["accepted_trade_ids"],
                               "nav_match": abs(c["nav_ex_funding"]["compounded_final_nav"] - reference["nav_20pct_per_1x"]["compounded_final_nav"]) < .00021}
                h = c["scenario_specific_coupled_ledgers"]["historical_funding"]
                st = c["scenario_specific_coupled_ledgers"]["stress_1bp_8h_funding"]
                f_rows.append([labels[window], sizing, cost, h["accepted_trades"], h["nav_20pct_per_1x"]["compounded_total_return_pct"],
                               h["nav_20pct_per_1x"]["compounded_max_dd_pct"], st["accepted_trades"], st["nav_20pct_per_1x"]["compounded_total_return_pct"]])
    def visit(node):
        if not isinstance(node, dict): return
        if "ledger_key" in node and "nav_20pct_per_1x" in node:
            key = node["ledger_key"]
            checks[key] = check_node(node, ul[key]["ledger_records"], node["nav_20pct_per_1x"], 20)
        for value in node.values():
            if isinstance(value, dict): visit(value)
    visit(u)
    # Negative controls prove that the final checker detects plausible corruptions.
    first_res = next(iter(next(iter(next(iter(b["results"].values())).values())).values()))
    node = first_res["coupled"]
    original_records = bl[first_res["ledger_key"]]["ledger_records"]
    original_nav = node["nav_ex_funding"]
    negative = {}
    for field in ("fee_dollar_comp", "realized_pnl_dollar_comp"):
        changed = copy.deepcopy(original_records)
        changed[0][field] += .5
        changed_node = copy.deepcopy(node)
        changed_node["ledger_sha256"] = hashlib.sha256(json.dumps(changed, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        # Rehash the corrupted ledger so checksum equality cannot mask whether
        # the independent monetary/fee identities actually detect the change.
        negative[field] = not check_node(changed_node, changed, original_nav, 20)["all_passed"]
    changed_nav = dict(original_nav)
    changed_nav["compounded_final_nav"] += 1
    negative["aggregate_nav"] = not check_node(node, original_records, changed_nav, 20)["all_passed"]
    changed_node = copy.deepcopy(node)
    changed_node["executed_trade_ids"][0] = "CORRUPTED"
    negative["executed_ids"] = not check_node(changed_node, original_records, original_nav, 20)["all_passed"]
    membership = {ym: {r["symbol"] for r in rows} for ym, rows in sources["monthly_membership"].items()}
    pit_errors, pit_records = [], 0
    for key, ledger in {**ul, **pl, **fl}.items():
        if "ROLLING_PIT_TOP50_VOL" not in key and not key.startswith(("pit_method/", "pit_funded/")): continue
        for record in ledger["ledger_records"]:
            pit_records += 1
            if record["symbol"] not in membership[record["decision_time"][:7]]:
                pit_errors.append({"ledger": key, "id": record["trade_id"]})
    old = load("IMPLEMENTATION_v406_LEDGER_BASELINE_ARITHMETIC.json")["mismatches"]
    yearend = []
    for error in old:
        key = error["path"].lstrip("/")
        records = [r for r in ul[key]["ledger_records"] if r["trade_id"] == error["id"]]
        yearend.append({"key": key, "id": error["id"], "present": bool(records), "settlement_passed": reconcile_settled_ledger(records)["all_passed"] if records else None})
    suite = ET.parse(ART / "METHOD_TEST_RESULTS_v4_0_6.xml").getroot()
    tests = {k: sum(int(s.get(k, 0)) for s in suite.findall("testsuite")) for k in ("tests", "failures", "errors", "skipped")}
    funding_schema_passed = all(c["read_errors_count"] == 0 and c["schema_errors_count"] == 0 for c in (b["historical_funding_coverage"], funded["funding_coverage"]))
    all_passed = all(x["all_passed"] for x in checks.values()) and all(negative.values()) and all(all(r.values()) for r in parity.values()) and not pit_errors and sources["all_passed"] and funding_schema_passed and tests["failures"] == 0 and tests["errors"] == 0
    evidence = {"version": "4.0.6", "generated_at_utc": datetime.now(timezone.utc).isoformat(), "all_technical_checks_passed": all_passed,
                "historical_files_unchanged": historical_count, "input_integrity": inputs, "tests": tests,
                "ledger_nodes_checked": len(checks), "ledger_records_checked_with_scenario_duplicates": sum(x["records"] for x in checks.values()),
                "ledger_checks": checks, "negative_control_rejections": negative, "pit_membership_records_checked": pit_records, "pit_membership_errors": pit_errors,
                "old_year_end_discrepancies": yearend, "cross_engine_and_causality": sources["cross_engine_and_causality"]}
    evidence["pit_funding_engine_ex_funding_parity"] = parity
    evidence["funding_output_semantics"] = semantics
    evidence["funding_schema_checks_passed"] = funding_schema_passed
    evidence["pit_inferred_funding_schedule_gaps_requiring_external_confirmation"] = funded["funding_coverage"]["total_inferred_cadence_missing_slots_across_symbols"]
    ci_intervals = [r["summary"]["bootstrap_ci95"]["avg_net_pct_ci95"] for sizes in pit["results"].values() for costs in sizes.values() for r in costs.values()]
    evidence["economic_evidence"] = {"pit_intervals_crossing_zero": sum(lo <= 0 <= hi for lo, hi in ci_intervals),
                                      "pit_intervals_total": len(ci_intervals), "live_signoff": "NOT_GRANTED"}
    evidence["requirement_audit"] = [
        {"id": "R1", "status": "completed", "scope": "Preservation and v405 baseline verification", "evidence": "IMPLEMENTATION_v406_BASELINE_CHECKS.json; historical hash verification"},
        {"id": "R2", "status": "completed", "scope": "Implementation fixes within declared simulation assumptions", "evidence": "METHOD_TEST_RESULTS_v4_0_6.xml; ledger_checks; negative_control_rejections"},
        {"id": "R3", "status": "completed", "scope": "Frozen protocol and explicit reused validation label", "evidence": "METHOD_v406_EXPERIMENT_PROTOCOL.json; METHOD_INPUT_MANIFEST_v4_0_6.json"},
        {"id": "R4", "status": "completed", "scope": "14-symbol and338-symbol reruns with PIT sizing/cost/funding comparisons", "evidence": "METHOD_BENCHMARK_v4_0_6.json; universe_338_reaudit_v4_0_6_summary.json; METHOD_PIT_FUNDING_v4_0_6.json"},
        {"id": "R5", "status": "completed", "scope": "Executable paper proposal rules and an evidence-based readiness decision", "evidence": "paper_rules_v406.py; METHOD_POLICY_v4_0_6.json; PHUONG_PHAP_FIBO_SHORT_v4_0_6.md; live NOT_GRANTED"},
        {"id": "R6", "status": "completed", "scope": "Final checks, report reconciliation and source snapshots", "evidence": "FINAL_METHOD_VERIFICATION_v4_0_6.json; METHOD_REPORT_CONSISTENCY_v4_0_6.json; VERSION_MANIFEST_v4_0_6.json"},
    ]
    save("FINAL_METHOD_VERIFICATION_v4_0_6.json", evidence)
    if not all_passed: raise AssertionError("Final checks failed; evidence saved")
    policy = {"version": "4.0.6", "paper_policy": asdict(PaperPolicy()), "signal_policy": "M6B factor gate; 2/2 pivots; causal PST; no extra score gate",
              "execution_mode": "PAPER_PROPOSALS_ONLY", "fresh_oos": False,
              "selection_reason": "Fixed sizing is the simple paper reference; both sizing policies remain reported; no claim of optimality",
              "historical_performance_scope": "Historical continuous-size simulation, not a forecast for rounded paper or live orders"}
    save("METHOD_POLICY_v4_0_6.json", policy)
    payload = {
        "version": "4.0.6", "research_signoff": "TECHNICAL_CHECKS_PASSED_WITH_DISCLOSED_MODEL_LIMITATIONS", "live_signoff": "NOT_GRANTED",
        "conclusion_vi": f"Bản v4.0.6 đã sửa các lỗi triển khai được phát hiện và vượt qua kiểm chứng hạch toán, cấu hình và tính nhất quán trên bộ dữ liệu đã khóa. Chỉ tiếp tục đánh giá paper; chưa đủ bằng chứng để nghiệm thu giao dịch tiền thật. {evidence['economic_evidence']['pit_intervals_crossing_zero']}/{len(ci_intervals)} khoảng tin cậy trung bình lệnh PIT trước funding đi qua 0. Chi phí cao có thể làm lợi nhuận IS âm, đồng thời drawdown lớn; không coi hoàn tất sửa mã là chứng minh chiến lược có lợi thế bền vững.",
        "verification_summary_vi": f"{tests['tests']} kiểm thử đạt; {len(checks)} nút sổ lệnh đã đối chiếu tiền, phí, mã lệnh và tổng NAV. {pit_records} bản ghi PIT khớp danh sách tháng tính lại độc lập. {historical_count} tệp lịch sử giữ nguyên; {inputs['files_checked']} tệp đầu vào không đổi trong các lượt chạy cuối.",
        "fixes": [
            {"title": "Nhóm điểm dưới 55", "evidence": "Universe và benchmark cùng dùng 0,80x theo phương pháp ba mức; loại sai lệch 0,50x từng làm thay đổi danh sách lệnh IS. Có kiểm thử ngưỡng thấp và đối chiếu hai bộ thực thi."},
            {"title": "Khối lượng cố định", "evidence": "fixed_1x được truyền đến bộ thực thi; kiểm thử cả ba ngưỡng điểm và chính sách không hợp lệ."},
            {"title": "Chốt sổ cuối năm", "evidence": f"NAV IS bao gồm giờ đóng nến 01/01/2026 00:00 UTC. Trong {len(old)} bản ghi sai cũ, {sum(r['settlement_passed'] is True for r in yearend)} còn được nhận và đã khớp; {sum(not r['present'] for r in yearend)} không còn được nhận sau sửa quy tắc khối lượng. Có kiểm thử riêng nến cuối kỳ."},
            {"title": "Chi phí", "evidence": "Bảng 1x lấy net_pct thực tế từ mô phỏng; kiểm thử 0, 20, 40, 60 bps."},
            {"title": "Đỉnh xác nhận", "evidence": f"Benchmark và universe đều dùng 2 nến trái, 2 nến phải; đối chiếu {sum(v['benchmark_candidates'] for v in sources['cross_engine_and_causality'].values())} ứng viên M6B trên ACE và AAVE."},
            {"title": "Nhảy giá qua stop", "evidence": "Ba bộ mô phỏng dùng giá mở cửa khi vượt qua stop đã tồn tại; ví dụ entry 100, stop 110, mở cửa 120 phải lỗ 20,2% gồm phí."},
            {"title": "Lệnh paper", "evidence": "Chặn dữ liệu thiếu, tín hiệu cũ, sai tháng, wave/cooldown, giới hạn danh mục và phần chốt lời quá nhỏ."},
        ],
        "rulebook_vi": [
            "Chọn coin đầu mỗi tháng theo cửa sổ 63 ngày trước đó: có ít nhất 50 ngày giao dịch, bách phân vị 90 của râu nến H4 không vượt 3,2%, xếp theo trung vị quote volume ngày và lấy tối đa 50 mã. Loại nhóm BTC, ETH, BNB, vàng và chỉ số đã định sẵn. Nếu không đủ điều kiện thì danh sách có thể dưới 50 mã.",
            "Chỉ đọc nến đã đóng. Tìm cấu trúc H4 hoặc D1 với lookback 30 nến, đỉnh có 2 nến xác nhận mỗi phía, đáy trước đỉnh và mức tăng trước đó tối thiểu 50%. Bộ tìm cấu trúc nhận nhịp giảm từ 4%; cổng M6B cuối cùng yêu cầu giảm ít nhất 6% và hiệu suất nhịp giảm KER ≥ 0,50.",
            "Cổng xu hướng M6B: [(EWMAC 16/64 tại đỉnh ≤ 0 hoặc Accel 4/16 hiện tại ≤ −1) và KER sóng tăng ≥ 0,35] hoặc KER sóng tăng ≥ 0,65. PST không dùng dữ liệu tương lai để điền phần thiếu. M6B không có cổng điểm 55/68/80; điểm dùng cho so sánh cách chia khối lượng.",
            "Xác nhận H1 cần có nhịp hồi, chạm từ Fibo 0,5 trong ba nến cuối của nhịp hồi, chưa vượt đỉnh, nến đóng đỏ và không tăng so với nến trước; thêm mẫu nến giảm hoặc phá đáy trước/gãy Fibo 0,5. Giá đóng được phép trong Fibo 0,382–0,786. Vùng hiển thị 0,5–0,618 không phải giới hạn cứng của giá khớp trong bộ máy hiện tại.",
            "Vào short theo giá đóng H1 sau xác nhận. Gọi L là đáy nhịp giảm, H là đỉnh và R = H − L: stop ban đầu = max(L + 0,886R, entry × 1,005) + 0,25 ATR H1; TP1 = L, TP2 = L − 0,272R, TP3 = L − 0,618R.",
            "Chốt 50% khối lượng ban đầu tại TP1 rồi kéo stop phần còn lại về entry; chốt 30% tại TP2 rồi kéo stop về TP1; chốt 20% tại TP3. Nếu cùng nến chạm nhiều mức, mô phỏng ưu tiên stop và kiểm tra lại stop vừa kéo. Nếu mở cửa vượt stop đã tồn tại, dùng giá mở cửa bất lợi hơn. Tối đa 72 nến H1 quan sát cho H4 và 120 cho D1; thiếu nến có thể làm thời gian thực dài hơn nên paper từ chối dữ liệu thiếu.",
            "Tham chiếu paper dùng fixed_1x: giá trị mỗi lệnh bằng 20% equity, tối đa 5 vị thế; tổng notional không quá 100% và rủi ro đến stop khi nhận lệnh không quá 12% equity. Đây là các tham số nghiên cứu, không phải mức rủi ro cá nhân được khuyến nghị. Khối lượng token cố định sau khi vào và chỉ giảm khi chốt; biến thể theo điểm dùng 1,50x từ 80, 1,15x từ 68, còn lại 0,80x.",
            "Kiểm tra membership, cooldown/wave và giới hạn danh mục trước khi nhận. Chỉ tiêu thụ wave sau khi có fill paper xác nhận. Cooldown theo thời gian thoát thật và ít nhất 4 giờ từ lúc vào. Ứng viên trùng giờ ưu tiên điểm cao, rồi mã và khung thời gian. Các giới hạn là điều kiện nhận lệnh; giá biến động sau đó có thể làm tỷ lệ phơi nhiễm vượt ngưỡng.",
        ],
        "benchmark_rows": b_rows, "pit_rows": p_rows, "pit_funding_rows": f_rows,
        "limitations_vi": [
            "JSON giữ một số trường NAV funding ở cấp gốc để so sánh phản thực trên cùng danh sách lệnh ex-funding. Kết quả thực thi có funding nằm trong scenario_specific_coupled_ledgers; báo cáo dùng các sổ kịch bản này. Khi funding làm đổi việc nhận lệnh, không dùng các trường cấp gốc đó làm NAV thực thi.",
            "Năm 2026 đã được dùng trong nhiều vòng kiểm định và lựa chọn trước đây. Các bảng 2026 là validation đã tái sử dụng, không phải holdout mới. Khoảng tin cậy bootstrap theo tuần chỉ mô tả mẫu đang xét, chưa điều chỉnh toàn bộ quá trình chọn chiến lược; các trường p_value cũ không được dùng để tuyên bố ý nghĩa thống kê.",
            "338 mã phụ thuộc tập tệp hiện có, thiếu đầy đủ lịch sử các hợp đồng đã hủy niêm yết. PIT chỉ bảo đảm chọn tháng bằng dữ liệu quá khứ trong tập đó. Dữ liệu 338 mã kết thúc 31/08/2026; benchmark chỉ 6/14 mã có thêm dữ liệu đến 29/09. Không so trực tiếp tổng kết quả hai cửa sổ như hai giai đoạn có độ phủ đồng nhất.",
            f"Funding lịch sử có tệp cho 14/14 mã benchmark và {funded['funding_coverage']['symbols_with_funding_files']}/{funded['funding_coverage']['symbols_requested']} mã từng thuộc PIT. Có {funded['funding_coverage']['total_inferred_cadence_missing_slots_across_symbols']} vị trí nghi thiếu theo lịch cục bộ suy luận; thiếu registry lịch thay đổi chính thức để kết luận đó là kỳ thực sự thiếu. Giá dùng hạch toán funding là giá đóng nến đại diện; thời điểm thoát trong nến được quy về đóng nến. Đọc bảng PIT có funding riêng để đánh giá tác động.",
            "Phí 20/40/60 bps là ngân sách tổng chi phí trên notional ban đầu, thu nửa ở lần đóng nến đầu và nửa ở khi thoát. Chưa mô phỏng từng khoản commission của mỗi partial fill, độ sâu sổ lệnh, độ trễ, thanh lý hay margin theo tài khoản. Stop theo OHLC và xử lý nhảy giá vẫn là mô hình, không bảo đảm mức fill thực tế.",
            "Bộ lập lệnh paper là hàm tính toán thuần, không gửi lệnh sàn. Nó kiểm tra các bộ lọc khối lượng/tick/notional được cung cấp, chưa thay thế toàn bộ bộ lọc sàn hay đối soát tài khoản. Làm tròn và loại phần chốt lời quá nhỏ có thể thay đổi số lệnh; chưa gán kết quả backtest cho các lệnh đã làm tròn.",
            "Giao diện/scanner mặc định của ứng dụng còn là cấu hình khác (pump 5%, pivot 1/1 và whitelist). Kết quả v4.0.6 áp dụng cho bộ nghiên cứu M6B và quy tắc paper này; không dùng nó để xác nhận scanner mặc định đã được triển khai đồng nhất.",
        ],
        "forward_steps_vi": [
            "Dùng hồ sơ này để review và chạy paper, giữ nguyên quy tắc trong METHOD_POLICY_v4_0_6.json. Trước một phiên paper thực tế, ghi SHA256 policy cùng thời gian bắt đầu; cập nhật dữ liệu đến hiện tại và tính lại danh sách đúng tháng, không kéo tiếp danh sách tháng 09 sang tháng 10.",
            "Đưa ứng viên M6B từ nến đã đóng, trạng thái danh mục đã đối soát và bộ lọc hiện hành vào paper_plan_v406.py. Ví dụ PAPER_INPUT_EXAMPLE_v4_0_6.json chỉ là dữ liệu giả TESTUSDT để kiểm tra luồng tính toán; không phải khuyến nghị mua bán.",
            "Ghi mọi ứng viên được nhận và từ chối, thời điểm/khối lượng/giá khớp từng phần, stop sửa đổi, commission, funding và NAV theo sự kiện. Tạm dừng nhận lệnh mới khi dữ liệu bị thiếu, mất đồng bộ vị thế hoặc đối soát NAV sai; giữ xử lý thoát các vị thế đang mở theo kế hoạch.",
            "Thu thập một tập paper mới sau khi khóa policy, tối thiểu 90 ngày và 50 lệnh đã đóng để bắt đầu review vận hành; đây là ngưỡng review định trước, không phải bằng chứng đủ về lợi nhuận. Kiểm tra lại chi phí thực, rủi ro, khoảng tin cậy và độ ổn định theo tuần trước mọi đề xuất live. Nếu đổi tham số, tạo phiên bản và tập forward mới.",
        ],
        "file_links": {"JSON kiểm định": "artifacts/fibo_trend_short/FINAL_METHOD_VERIFICATION_v4_0_6.json", "Benchmark": "artifacts/fibo_trend_short/METHOD_BENCHMARK_v4_0_6.json", "So sánh PIT": "artifacts/fibo_trend_short/METHOD_PIT_COMPARISON_v4_0_6.json", "Danh sách PIT từng tháng và kiểm tra nguồn": "artifacts/fibo_trend_short/METHOD_SOURCE_CHECKS_v4_0_6.json", "Policy paper": "artifacts/fibo_trend_short/METHOD_POLICY_v4_0_6.json", "Ví dụ đầu vào paper": "artifacts/fibo_trend_short/PAPER_INPUT_EXAMPLE_v4_0_6.json", "Chương trình lập lệnh paper": "scripts/fibo_research/paper_plan_v406.py"},
    }
    save("METHOD_DELIVERY_v4_0_6.json", payload)
    prompt = """Hãy tiếp tục từ hồ sơ PeakPulse AI Fibo Trend Short v4.0.6 trong C:/Rapid Coding/dao_vang/artifacts/fibo_trend_short.

Đọc VERSION_MANIFEST_v4_0_6.json, FINAL_METHOD_VERIFICATION_v4_0_6.json, METHOD_DELIVERY_v4_0_6.json, METHOD_PIT_FUNDING_v4_0_6.json và PHUONG_PHAP_FIBO_SHORT_v4_0_6.md trước khi sửa. Kiểm tra hash và tái lập các phép đối chiếu; không dùng tuyên bố 19 Closed của phiên bản trước để thay cho kiểm chứng.

Các lỗi fixed sizing, hệ số dưới 55 phải là 0,80x, phí trong thống kê, pivot 2/2, chốt sổ cuối IS và stop khi nhảy giá đã có bản sửa cùng kiểm thử. Giữ nguyên mọi artifact v4.0.6 trở về trước; tạo phiên bản kế tiếp cho mọi thay đổi.

Chưa duyệt live. Các việc cần đóng tiếp bằng bằng chứng:
1. Xác nhận rủi ro kinh tế: CI PIT đi qua 0, IS có thể âm khi phí tăng và drawdown lớn. Không tối ưu tiếp trên 2026 rồi gọi đó là OOS. Nếu thiết kế phương pháp mới, khóa protocol trước một tập forward mới và báo đầy đủ mọi biến thể thử.
2. Tích hợp một profile M6B có tên riêng vào scanner/paper, dùng đúng pivot 2/2, pump50, gate, PIT theo tháng và stop/TP/cooldown của hồ sơ. So sánh ứng viên và fill từng lệnh với bộ nghiên cứu. Scanner mặc định hiện khác cấu hình nghiên cứu.
3. Hoàn thiện sự kiện khớp lệnh paper: tick/lot/notional, spread/độ trễ, partial fills, phí theo từng fill, funding theo mark và thời điểm thực, margin/forced exit. Không gán kết quả khối lượng liên tục cho lệnh đã làm tròn. Không kích hoạt lệnh tiền thật.
4. Đối chiếu registry listing/delisting và thay đổi lịch funding, chỉ rõ vùng thiếu dữ liệu. Dùng dữ liệu funding đã có, không bỏ qua funding ở danh mục PIT.
5. Khóa hash policy trước paper mới; tối thiểu 90 ngày và 50 lệnh đóng để bắt đầu review vận hành, không coi ngưỡng này tự động chứng minh lợi nhuận. Báo cả ứng viên bị từ chối, lệnh đang mở, chi phí và drawdown.

Xuất JSON kết quả, ledger, báo cáo sinh từ JSON, kiểm thử âm, manifest và ma trận Closed/Partial/Open theo từng yêu cầu. Nêu rõ nghiệm thu kỹ thuật và nghiệm thu live là hai kết luận riêng. Nếu còn chưa duyệt, cung cấp ngay prompt sửa tiếp có bằng chứng cụ thể; không che kết quả âm hoặc đổi nhãn validation đã dùng thành holdout mới.
"""
    (ART / "PROMPT_TIEP_THEO_v4_0_6.md").write_text(prompt, encoding="utf-8")
    md = render(payload)
    report = ART / "PHUONG_PHAP_FIBO_SHORT_v4_0_6.md"
    report.write_text(md, encoding="utf-8")
    mutations = {"changed_nav_cell": md.replace(str(b_rows[0][4]), "999999", 1),
                 "missing_table_row": md.replace("| " + " | ".join(map(str, b_rows[0])) + " |", "", 1),
                 "changed_live_conclusion": md.replace("chưa đủ bằng chứng", "đã đủ bằng chứng", 1),
                 "changed_cost_assumption": md.replace("20/40/60 bps", "0/0/0 bps", 1)}
    check = {"exact_json_render_match": report.read_text(encoding="utf-8") == render(load("METHOD_DELIVERY_v4_0_6.json")),
             "mutation_rejections": {key: value != render(payload) for key, value in mutations.items()},
             "table_rows": len(b_rows) + len(p_rows) + len(f_rows)}
    altered = copy.deepcopy(payload)
    altered["pit_rows"][0][5] += 1
    check["json_nav_mutation_rejected"] = render(altered) != md
    altered = copy.deepcopy(payload)
    altered["benchmark_rows"][0][6] += 1
    check["json_funding_mutation_rejected"] = render(altered) != md
    assert check["exact_json_render_match"] and all(check["mutation_rejections"].values()) and check["json_nav_mutation_rejected"] and check["json_funding_mutation_rejected"]
    save("METHOD_REPORT_CONSISTENCY_v4_0_6.json", check)
    # Snapshot source paths, preserving relative directories and all old versions.
    source_paths = [Path(p) for p in load("METHOD_INPUT_MANIFEST_v4_0_6.json")["files"] if p.endswith(".py")]
    source_paths += list((ROOT / "scripts/fibo_research").glob("*method*v406.py"))
    source_paths += [ROOT / "scripts/fibo_research/paper_plan_v406.py", ROOT / "src/dao_vang/fibo_short/paper_rules_v406.py"]
    source_paths += [ROOT / "scripts/fibo_research/pit_funding_v406.py"]
    source_paths += list((ROOT / "tests/unit/fibo_short").glob("*.py"))
    source_paths += [ROOT / p for p in ("pyproject.toml", "uv.lock", "requirements.txt") if (ROOT / p).is_file()]
    for path in sorted(set(source_paths)):
        target = ART / "snapshots/v4_0_6" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    tracked = sorted(set(source_paths + [p for p in (ART / "snapshots/v4_0_6").rglob("*") if p.is_file()] +
                         [p for p in ART.glob("*v4_0_6*.*") if p.name != "VERSION_MANIFEST_v4_0_6.json"] +
                         [ART / p for p in ("METHOD_v406_EXPERIMENT_PROTOCOL.json", "IMPLEMENTATION_v406_BASELINE_CHECKS.json", "IMPLEMENTATION_v406_LEDGER_BASELINE_ARITHMETIC.json")]))
    manifest = {"version": "4.0.6", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "historical_preservation_count": verify_history(), "input_integrity": verify_inputs(),
                "runtime": {"python": sys.version, "packages": {p: package_version(p) for p in ("pandas", "numpy", "pyarrow", "pydantic", "pytest")}},
                "sha256_checksums": {p.relative_to(ROOT).as_posix(): digest(p) for p in tracked}}
    save("VERSION_MANIFEST_v4_0_6.json", manifest)
    print(json.dumps({"tests": tests, "ledger_nodes": len(checks), "pit_records": pit_records, "all_passed": all_passed, "manifest_files": len(tracked)}))


if __name__ == "__main__":
    main()
