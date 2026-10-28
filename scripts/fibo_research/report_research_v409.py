"""JSON-derived dual-cost results, retained mini-alpha evidence, data requirements."""
import copy
from datetime import datetime,timezone
import gzip
import json
from pathlib import Path
import numpy as np
import pandas as pd
import research_v409 as z
from report_research_v408 import NAMES

r=z.r;ART=z.ART


def registry(result):
    prior=z.BASE/"MINI_ALPHA_REGISTRY.json";out=copy.deepcopy(r.read(prior))
    out.update(status="DUAL_EXECUTION_COSTS_HISTORICAL_FUNDING_RESEARCH_ACTIVE",parent_registry={"path":str(prior),"sha256":r.sha(prior)},
        current_results={"path":str(ART/"RESULTS.json"),"sha256":r.sha(ART/"RESULTS.json")})
    byid={e["id"]:e for e in out["entries"]}
    for aid,a,b in [("MA407-01","m6_risk","reference_m6_fixed"),("MA407-02","elite_sniper_risk","sniper_risk"),
        ("MA407-03","sniper_risk","m6_risk"),("MA407-08","sniper_rr1_horizon24","sniper_horizon24"),("MA407-09","sniper_horizon24","sniper_risk")]:
        evidence={"comparison":[a,b],"scenarios":{},"results_sha256":r.sha(ART/"RESULTS.json"),
            "qualification":"Historical reused-data comparison; funding has explicit partial mark-price proxy; no multiple-trial adjustment; risk sizing now includes specified costs."}
        for scenario in z.x.SCENARIOS:
            diff=[];annual={}
            for year,nodes in result["annual"].items():
                one,two=nodes[a][scenario],nodes[b][scenario]
                diff.extend(np.asarray(one["weekly_returns"])-np.asarray(two["weekly_returns"]))
                annual[year]={"candidate_return_pct":one["return_pct"],"baseline_return_pct":two["return_pct"],
                    "candidate_max_dd_pct":one["max_dd_pct"],"baseline_max_dd_pct":two["max_dd_pct"]}
            evidence["scenarios"][scenario]={"annual":annual,"candidate_six_year":result["fixed_policy_six_year"][a][scenario],
                "baseline_six_year":result["fixed_policy_six_year"][b][scenario],"paired_weekly_difference_ci":r.block_ci(diff)}
        byid[aid].setdefault("evidence_by_stage",{})["v409_dual_cost_historical_funding"]=evidence
        byid[aid]["status"]="DUAL_COST_HISTORICAL_FUNDING_EVIDENCE_RECORDED"
    for entry in out["entries"]:entry["usable_as_proven_alpha"]=False
    out["trial_accounting_v409"]={"prior_adaptive_signal_variants_at_least":24,"existing_signal_policies":6,"execution_scenarios":2,
        "new_signal_parameters":0,"changed_sizing_cost_assumption":True,"fresh_oos":False}
    r.save(ART/"MINI_ALPHA_REGISTRY.json",out)
    return out


def data_request():
    needed={}
    with gzip.open(ART/"LEDGERS.json.gz","rt",encoding="utf8") as f:ledgers=json.load(f)
    for node in ledgers.values():
        for trade in node["ledger"]:
            for event in trade["funding_events"]:
                if event["price_source"]=="funding_api_settlement_mark":continue
                if event["funding_rate"]==0 or event["remaining_qty"]==0:continue
                key=(trade["symbol"],event["funding_ts_ms"])
                needed[key]={"symbol":key[0],"funding_ts_ms":key[1],"timestamp_utc":pd.Timestamp(key[1],unit="ms",tz="UTC").isoformat(),
                    "current_proxy_mark":event["mark_price"],"settled_funding_rate_already_available":event["funding_rate"]}
    by_symbol={}
    for (symbol,t),event in sorted(needed.items()):by_symbol.setdefault(symbol,[]).append(event)
    out={"purpose":"Replace approximate historical settlement marks for actual simulated funding payments; do not buy duplicate OHLC or funding-rate-only data.",
        "unique_settlements":len(needed),"symbols":len(by_symbol),"events_by_symbol":by_symbol,
        "requested_fields":["exchange=Binance USD-M Futures","contract symbol and lifecycle mapping","exchange event timestamp in UTC/ms","exact settlement mark if available; otherwise recorded mark-price stream with stated cadence","coverage gaps and correction history"],
        "potential_provider":{"name":"Tardis.dev","official_source":"https://docs.tardis.dev/historical-data-details/binance-futures",
            "qualification":"Vendor documents Binance futures history from2019-11-17 and markPrice stream; warns of collection issues before2020-05-14. Exact settlement-tick coverage for these events is NOT confirmed. Request samples and gap report before purchase."},
        "purchase_authorized":False,"exact_funding_cashflow_certified":False}
    r.save(ART/"EXACT_MARK_DATA_REQUEST.json",out)
    return out


def render(result,inputs,audit,alpha,need):
    lines=["# Fibo Trend Short v4.0.9 với phí VIP6 và stress Regular","",
        "Đã chạy lại sáu cấu hình cố định trên 2020–2025 theo hai kịch bản chi phí được yêu cầu. Funding dùng sự kiện và tỷ lệ lịch sử; một phần mark price thanh toán được xấp xỉ từ giá mở cửa nến mark chính thức. Chưa cấp duyệt giao dịch thật.","",
        "## Hai kịch bản chi phí","",
        "| Kịch bản | Phí taker mỗi lần khớp | Trượt giá mỗi lần khớp | Funding |",
        "|---|---:|---:|---|",
        f"| Chuẩn VIP6 | {result['scenarios']['standard_vip6']['fee_bps']:.1f} bps | {result['scenarios']['standard_vip6']['slippage_bps']:.0f} bps | Lịch sử thực tế, có công bố giá proxy |",
        f"| Stress Regular | {result['scenarios']['stress_regular']['fee_bps']:.1f} bps | {result['scenarios']['stress_regular']['slippage_bps']:.0f} bps | Cùng lịch sử thực tế, có công bố giá proxy |","",
        "1 bp = 0,01%. Dùng phí taker USDT-M Futures, không giảm BNB hoặc hoàn phí. Đây là biểu phí chuẩn hóa cố định cho toàn kỳ, không phải lịch sử thay đổi phí hoặc cấp VIP thực của một tài khoản. Nguồn: [biểu phí Binance](https://www.binance.com/en/fee/futureFee) và [cách tính phí theo giá trị thực khớp](https://www.binance.com/en/support/faq/detail/360033544231).","",
        "Bán vào short ở giá tham chiếu giảm trượt giá; mua đóng ở giá tham chiếu cộng trượt giá. Phí tính trên khối lượng nhân giá đã trượt, mỗi lần khớp và mỗi phần thoát. Các phần thoát trong cùng nến 5 phút có thể được lưu thành nhóm có giá bình quân theo khối lượng; vì phí và trượt giá tuyến tính, tổng chi phí bằng tổng tính riêng từng phần. Không cộng trượt giá lần thứ hai vào PnL.","",
        "NAV bao gồm ngay phí, trượt giá, lãi/lỗ và funding trước khi xét lệnh tiếp theo. Khối lượng theo stop giữ mục tiêu lỗ mô hình 0,5% NAV mỗi lệnh, gồm chi phí vào và thoát tại stop; vì vậy khối lượng có thể khác giữa hai kịch bản. Điều này thay thế bộ đệm 60 bps cố định của v4.0.8. Khoảng nhảy giá qua stop vẫn có thể gây lỗ lớn hơn mô hình.","",
        "## Funding và chất lượng giá thanh toán","",
        f"Đã kiểm tra {inputs['funding_events']:,} sự kiện funding của {inputs['funding_symbols']} mã có tín hiệu, từ {inputs['raw_responses_verified']:,} phản hồi nguồn chính thức. {inputs['local_rates_matching']:,}/{inputs['local_rows_compared']:,} bản ghi trên máy khớp tỷ lệ Binance; có {inputs['local_differences']} khác biệt trong phần đối chiếu.","",
        "| Nguồn mark price trong bộ dữ liệu funding | Sự kiện |","|---|---:|"]
    for source,n in inputs["price_sources"].items():lines.append(f"| {source} | {n:,} |")
    lines.extend(["","Funding cho short = khối lượng còn mở × mark price × funding rate. Rate dương ghi thu, rate âm ghi chi; dùng timestamp từng sự kiện thay vì giả định mọi mã đều thanh toán mỗi 8 giờ. Tại timestamp trùng nhau, funding được hạch toán trước thoát lệnh cuối nến, rồi mới xét vào lệnh mới. Quy ước nến 5 phút không thể khôi phục chính xác thứ tự khớp trong nến và độ trễ thanh toán thực. [Quy tắc funding của Binance](https://www.binance.com/en/support/faq/detail/360033525031).","",
        "Khi API funding thiếu markPrice, đã tải lịch sử mark-price chính thức và dùng giá OPEN đầu giờ, cách timestamp funding không quá 15 giây. Không dùng giá đóng tương lai hoặc thay bằng funding bằng 0. Giá này là proxy gần thời điểm thanh toán, chưa được chứng nhận là đúng tick dùng trong bút toán của sàn.","",
        f"Trong các danh mục đã chạy, {audit['proxy_mark_payments']:,}/{audit['funding_payments_verified']:,} bản ghi funding theo kịch bản dùng giá proxy. Để đối soát phần proxy có phát sinh số tiền khác 0 cần {need['unique_settlements']:,} sự kiện duy nhất của {need['symbols']} mã, đã liệt kê trong `EXACT_MARK_DATA_REQUEST.json`. Các bản ghi theo kịch bản có thể trùng cùng một sự kiện thị trường.","",
        "Nguồn miễn phí đã đủ tỷ lệ và lịch sự kiện cho phép thử hiện tại. Nếu yêu cầu đối soát tiền funding chính xác tại từng tick, cần dữ liệu bổ sung theo danh sách trên. Có thể yêu cầu mẫu từ [Tardis.dev](https://docs.tardis.dev/historical-data-details/binance-futures), nơi công bố lịch sử Binance futures và luồng markPrice; họ cũng nêu vấn đề thu thập trước 14/05/2020. Chưa xác nhận nhà cung cấp đáp ứng đủ mọi sự kiện, chưa có báo giá và chưa mua dữ liệu.","",
        "## Kết quả NAV 2020–2025","",
        "Mỗi năm bắt đầu với NAV 100 và đặt lại trạng thái, ngừng vào lệnh trong 5 ngày cuối năm; tổng sáu năm nối bằng lãi kép. Các số dưới đây đã trừ phí và trượt giá, cộng/trừ funding lịch sử theo phương pháp giá nêu trên.","",
        "| Cấu hình | NAV chuẩn | MaxDD chuẩn | Lệnh chuẩn | NAV stress | MaxDD stress | Lệnh stress |",
        "|---|---:|---:|---:|---:|---:|---:|"])
    for spec in z.q.FAMILY:
        vid=spec["id"];a=result["fixed_policy_six_year"][vid]["standard_vip6"];b=result["fixed_policy_six_year"][vid]["stress_regular"]
        lines.append(f"| {NAMES[vid]} | {a['return_pct']:+.2f}% | {a['max_dd_pct']:.2f}% | {a['trades']} | {b['return_pct']:+.2f}% | {b['max_dd_pct']:.2f}% | {b['trades']} |")
    profitable=sum(m["standard_vip6"]["return_pct"]>0 for m in result["fixed_policy_six_year"].values())
    uncertain=sum(m["standard_vip6"]["weekly_ci"]["ci95_pct"][0]<=0<=m["standard_vip6"]["weekly_ci"]["ci95_pct"][1] for m in result["fixed_policy_six_year"].values())
    stress_loss=sum(m["stress_regular"]["return_pct"]<0 for m in result["fixed_policy_six_year"].values())
    lines.extend(["",f"Bản chuẩn có {profitable}/6 cấu hình dương toàn kỳ; {uncertain}/6 khoảng tin cậy lợi nhuận tuần trung bình vẫn chứa 0. Bản stress có {stress_loss}/6 cấu hình âm. Kết quả dương ở chi phí chuẩn chưa đủ để chứng minh lợi thế bền vững; stress cho biết mức nhạy với chi phí lớn hơn.","",
        "| Cấu hình | CI 95% lợi nhuận tuần trung bình chuẩn | CI 95% stress |","|---|---|---|"])
    for spec in z.q.FAMILY:
        row=result["fixed_policy_six_year"][spec["id"]]
        a=row["standard_vip6"]["weekly_ci"]["ci95_pct"];b=row["stress_regular"]["weekly_ci"]["ci95_pct"]
        lines.append(f"| {NAMES[spec['id']]} | [{a[0]:+.4f}%; {a[1]:+.4f}%] | [{b[0]:+.4f}%; {b[1]:+.4f}%] |")
    for scenario,label in [("standard_vip6","Chuẩn VIP6"),("stress_regular","Stress Regular")]:
        lines.extend(["",f"### {label} theo từng năm","","| Cấu hình | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |","|---|---:|---:|---:|---:|---:|---:|"])
        for spec in z.q.FAMILY:
            vid=spec["id"];years=" | ".join(f"{result['annual'][str(y)][vid][scenario]['return_pct']:+.2f}%" for y in range(2020,2026))
            lines.append(f"| {NAMES[vid]} | {years} |")
    lines.extend(["","## Phân rã dòng tiền danh mục","",
        "Đơn vị là % vốn đầu toàn kỳ, đã quy đổi theo NAV đầu từng năm. PnL ròng = PnL giá tham chiếu − phí − trượt giá + funding. Funding có thể mang dấu âm. Đây là phân rã kế toán của danh mục đã chạy, không phải kết quả giả định nếu bỏ funding.","",
        "| Cấu hình và kịch bản | PnL giá tham chiếu | Phí | Trượt giá | Funding | Ròng |","|---|---:|---:|---:|---:|---:|"])
    for spec in z.q.FAMILY:
        for scenario,label in [("standard_vip6","chuẩn"),("stress_regular","stress")]:
            m=result["fixed_policy_six_year"][spec["id"]][scenario]
            values=" | ".join(f"{m[k]:+.2f}" for k in ["gross_reference_pnl_pct","fees_pct","slippage_pct","funding_pct","return_pct"])
            lines.append(f"| {NAMES[spec['id']]} — {label} | {values} |")
    lines.extend(["","## Kiểm định cuốn chiếu và quyết định","",
        "Giữ sáu luật tín hiệu đã có; không dò thêm ngưỡng. Chọn từng năm dựa trên các năm trước: ít nhất hai năm và 60 lệnh, mọi năm trước dương ở bản chuẩn, tổng stress không âm, MaxDD từng năm không quá 15%, không thiếu nến thực thi. Không có cấu hình đạt thì giữ tiền. Họ cấu hình đã chịu ảnh hưởng của nghiên cứu 2024 và kết quả 2025, nên đây vẫn là kiểm tra hồi cứu; không có OOS mới hoàn toàn.","",
        "| Năm kiểm tra | Lựa chọn đã khóa |","|---|---|"])
    for year,lock in result["walk_forward_locks"].items():lines.append(f"| {year} | {NAMES.get(lock['selected'],lock['selected'])} |")
    lines.extend(["","| Chuỗi kiểm tra 2022–2025 | NAV | MaxDD | Lệnh | CI 95% lợi nhuận tuần trung bình |","|---|---:|---:|---:|---|"])
    for scenario,m in result["walk_forward_oos"].items():
        ci=m["weekly_ci"]["ci95_pct"]
        lines.append(f"| {scenario} | {m['return_pct']:+.2f}% | {m['max_dd_pct']:.2f}% | {m['trades']} | [{ci[0]:+.4f}%; {ci[1]:+.4f}%] |")
    lines.extend(["","Bootstrap khối 4 tuần, 5.000 mẫu, giữ cả tuần không giao dịch; chưa điều chỉnh cho toàn bộ các lần thử. Giữ tiền không chứng minh alpha. Thiên lệch do kho dữ liệu thiếu mã đã biến mất và mô hình khớp nến vẫn còn; không cấp duyệt giao dịch thật chỉ dựa vào kết quả này.","",
        f"Đã kiểm chứng độc lập {audit['scenario_nodes_verified']} kịch bản, {audit['scenario_trade_records']:,} bản ghi giao dịch, {audit['execution_fill_groups']:,} nhóm khớp và {audit['funding_payments_verified']:,} bút toán funding. {audit['new_tests']['tests']} kiểm thử mới qua; bảo toàn {inputs['previous_checkpoint_files_preserved']} tệp của phiên bản trước. Nhật ký giữ {len(alpha['entries'])} giả thuyết mini-alpha và thêm bằng chứng chi phí mới; chưa mục nào được gắn nhãn alpha đã chứng minh.","",
        "Nguồn: `PROTOCOL.json`, `RESULTS.json`, `LEDGERS.json.gz`, `funding/MANIFEST.json`, `INPUT_VERIFICATION.json`, `INDEPENDENT_VERIFICATION.json`, `MINI_ALPHA_REGISTRY.json`, `EXACT_MARK_DATA_REQUEST.json`. Backtest chỉ dùng quan sát đến hết 2025.",""])
    return "\n".join(lines)


def main():
    result=r.read(ART/"RESULTS.json");inputs=r.read(ART/"INPUT_VERIFICATION.json");audit=r.read(ART/"INDEPENDENT_VERIFICATION.json")
    assert inputs["all_checks_passed"] and audit["all_checks_passed"] and audit["results_sha256"]==r.sha(ART/"RESULTS.json")
    alpha=registry(result);need=data_request()
    report=render(result,inputs,audit,alpha,need);(ART/"REPORT.md").write_text(report,encoding="utf8")
    assert (ART/"REPORT.md").read_text(encoding="utf8")==render(*[r.read(ART/p) for p in ["RESULTS.json","INPUT_VERIFICATION.json","INDEPENDENT_VERIFICATION.json","MINI_ALPHA_REGISTRY.json","EXACT_MARK_DATA_REQUEST.json"]])
    r.save(ART/"REPORT_CONSISTENCY.json",{"all_passed":True,"method":"Full deterministic regeneration from versioned JSON",
        "files":{p:r.sha(ART/p) for p in ["RESULTS.json","INPUT_VERIFICATION.json","INDEPENDENT_VERIFICATION.json","MINI_ALPHA_REGISTRY.json","EXACT_MARK_DATA_REQUEST.json","REPORT.md"]}})
    r.save(ART/"PROGRESS.json",{"stage":"dual_cost_historical_funding_verified_and_documented","goal_complete":False,"fresh_oos":False,
        "data_ceiling":"2025-12-31","cost_models":z.x.SCENARIOS,"funding_price_quality":"PARTIAL_EXPLICIT_PROXY","live_signoff":"NOT_GRANTED",
        "next_action":"Use these standard/stress definitions for further research; require stronger unused-data evidence and exact-price validation before signoff."})
    policy=ART.parent/"BACKTEST_COST_STANDARD.json"
    policy_value={"status":"USER_REQUIRED","applies_to":"Fibo Trend Short research from v4.0.9 onward","scenarios":z.x.SCENARIOS,
        "unit":"bps PER FILL, including each partial exit;1bp=0.01%","venue":"Binance USDT-M Futures","liquidity":"taker","bnb_discount":False,
        "funding_required":"Signed historical event rate times remaining quantity times settlement mark. Acquire missing data; never silently use zero. Label any price proxy and provide exact-data requirements.",
        "data_ceiling":"2025-12-31 until user changes it","source_protocol":str(ART/"PROTOCOL.json"),"protocol_sha256":r.sha(ART/"PROTOCOL.json"),
        "latest_verified_report":str(ART/"REPORT.md"),"oos":"Preserve chronological locks and disclose globally reused history."}
    if policy.exists():
        assert r.read(policy)==policy_value,"Do not overwrite a different research cost standard"
    else:r.save(policy,policy_value)
    paths={str(p.relative_to(ART)):r.sha(p) for p in sorted(ART.rglob('*')) if p.is_file() and p.name!='CHECKPOINT.json'}
    r.save(ART/"CHECKPOINT.json",{"created_at_utc":datetime.now(timezone.utc).isoformat(),"files":paths,"file_count":len(paths),"goal_complete":False,
        "additional_sources":{str(p.relative_to(r.ROOT)):r.sha(p) for p in [Path(__file__),Path(__file__).with_name('verify_research_v409.py')]},
        "additional_artifacts":{str(policy):r.sha(policy)}})
    print(json.dumps({"report":str(ART/"REPORT.md"),"checkpoint_files":len(paths),"unique_proxy_settlements":need["unique_settlements"]}),flush=True)


if __name__=="__main__":main()
