"""Vietnamese dashboard comparing three directions with one shared wallet."""
import json
from html import escape
from collections import defaultdict
import pandas as pd
from compare_account_risk import ROOT, write
from search_directional_reversal import OUT

MODES = {"short": "Chỉ Short", "long": "Chỉ Long", "both": "Long + Short"}


def name(s):
    return f"{MODES[s['mode']]} · {'lọc 6h' if s['mask'] == 2 else 'không lọc 6h'} · {s['cap']} chỗ · " + ("giữ không hạn" if s["holding"] == "hold" else "đóng sau 48h")


def main():
    s = json.loads((OUT/"summary.json").read_text(encoding="utf-8"))
    v = json.loads((OUT/"verification.json").read_text(encoding="utf-8"))
    assert len(s["results"]) == v["journals_audited"] == 144
    lookup = {(r["strategy_id"],r["window"],r["cost"]): r for r in s["results"]}
    num = lambda x: "Không hoàn tất" if x is None else f"{x:.2f}"
    tr = lambda xs: "<tr>" + "".join("<td>"+escape(str(x))+"</td>" for x in xs)+"</tr>"
    rows = []; highlights = []; series = []; contributions = []
    for spec in s["specs"]:
        rs = lambda w: [lookup[(spec["id"],w,c)] for c in ["base","stress"]]
        rows.append([name(spec), *[' / '.join(num(r["ending_equity"]) for r in rs(w)) for w in ["year","later"]],
            ' / '.join(f"{r['max_drawdown']*100:.2f}%" for r in rs("year")),
            ' / '.join(f"{r['side_entries'].get('LONG',0)}L + {r['side_entries'].get('SHORT',0)}S" for r in rs("year"))])
    for mode in MODES:
        ident = f"{mode}_mask2_n25_hold_cap5"
        y, q = [lookup[(ident,w,"base")] for w in ["year","later"]]
        highlights.append([MODES[mode], num(y["ending_equity"]), f"{y['max_drawdown']*100:.2f}%", y["entries"],
                           num(q["ending_equity"]), q["entries"]])
        raw = json.loads((OUT/"runs"/f"year_base_{ident}.json").read_text(encoding="utf-8"))
        totals = defaultdict(float)
        for j in raw["journal"]:
            if "net" in j: totals[(j["symbol"],j["side"])] += j["net"]
        for p in raw["open_positions"]: totals[(p["symbol"],p["side"])] += p["unrealized"]-p["entry_fee"]+p["funding"]
        contributions.append(dict(mode=mode, coin_side_net=[dict(symbol=k[0],side=k[1],net=v) for k,v in sorted(totals.items(),key=lambda kv:kv[1])],
                                  open_positions=raw["open_positions"]))
    for row in s["results"]:
        f = pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet"); ix = {0,len(f)-1}
        for _, g in f.groupby((f["at"]-f["at"].iloc[0])//86400000): ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(row,points=[[int(q["at"]),round(q.equity,6)] for _,q in f.loc[sorted(ix)].iterrows()]))
    write(OUT/"dashboard_data.json", series)
    title = "Đã có Long + Short; ghép hai chiều chưa cải thiện cả năm"
    finding = "Cùng lọc 6h, 5 chỗ và giữ không hạn: 500 USDT thành 585,00 khi chỉ Short, 482,65 khi chỉ Long, và 467,19 khi kết hợp. Riêng tài khoản mới tháng 6–8, kết hợp đạt 513,79 USDT. Một giai đoạn tốt chưa đủ để chọn chạy thật."
    target = f"{s['target_met_rows']}/144 đường đạt tăng 50% ở từng tháng; {s['incomplete_paths']} đường không hoàn tất."
    diagnosis = "Long bắt hồi sau giảm mạnh vẫn có thể giữ lệnh rất lâu: PUMP còn mở 348 ngày trong cấu hình Long có lọc 6h. Hai chiều chia sẻ chỗ nên thay đổi những tín hiệu được vào; không thể cộng kết quả hai tài khoản riêng. Trong cấu hình kết hợp có lọc 6h/5 chỗ, SOON Short đóng góp ròng −39,31 USDT, tài khoản từng giảm 33,83% và khóa mở mới. Bật thêm Long không tự loại bỏ rủi ro Short cũ."
    selection = "Khóa lựa chọn bằng dữ liệu 09/2025–05/2026 trước khi chạy phần 06–08 trong lượt này: chỉ Short không lọc 6h/5 chỗ/giữ không hạn đạt bộ lọc lựa chọn. Không có cấu hình Long hoặc kết hợp nào đồng thời có lời ở cả hai mức chi phí, DD dưới 20% và ít nhất 20 lệnh đã đóng. Dữ liệu đã dùng nghiên cứu trước đây nên đây không phải kiểm định tương lai độc lập."
    audit = (f"Đối soát độc lập {v['journals_audited']} sổ giao dịch, {v['directional_fills_checked']:,} lần khớp, "
             f"{v['funding_quantities_checked']:,} khoản funding và {v['equity_states_reconstructed']:,} mốc tài sản. "
             f"{v['baseline_paths_exact']} đường Short khớp chính xác lượt cũ; {v['independent_long_signals']} tín hiệu Long kiểm tra bằng phép tính độc lập, "
             f"{v['causal_prefixes']} so sánh khi cắt dữ liệu tương lai, {v['replayed_paths_exact']} đường chạy lại khớp. 78 kiểm thử đạt. Hash live giữ nguyên.")
    write(OUT/"findings.json", dict(title=title,finding=finding,diagnosis=diagnosis,selection=selection,contributions=contributions,
        next_steps=["Thử Long theo xu hướng thay vì chỉ bắt hồi quá bán, với cùng giới hạn vốn và dữ liệu khóa.",
                    "Kiểm tra chọn hướng theo chế độ thị trường từ nến đã đóng; đánh giá lịch sử đầy đủ và tài khoản khởi chạy ở nhiều thời điểm.",
                    "Chỉ xem là ứng viên khi kết quả ngoài giai đoạn chọn còn đứng vững sau chi phí và lỗ mở."]))
    old = (ROOT/"artifacts/execution_costs_20260925/dashboard.html").read_text(encoding="utf-8")
    style = old.split("<style>",1)[1].split("</style>",1)[0]
    script = old.split("<script>",1)[1].split("</script>",1)[0]
    script = script.replace("${r.entries} vị thế vào", "${r.entries} vị thế vào (${r.side_entries?.LONG??0} Long / ${r.side_entries?.SHORT??0} Short)")
    options = "".join(f'<option value="{p["id"]}"'+(' selected' if p["id"]=="both_mask2_n25_hold_cap5" else '')+'>'+escape(name(p))+'</option>' for p in s["specs"])
    html = '''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Long và Short</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / NGHIÊN CỨU HAI CHIỀU · LƯỢT 19</div><h1>__TITLE__</h1><p class="muted">01/09/2025–01/09/2026 UTC · 30 altcoin · một tài khoản chung 500 USDT · Cross x5</p>
<div class="notice"><b>__TARGET__</b><p>__FINDING__</p></div><div class="cards"><div class="card">Chế độ<strong>Short / Long / cả hai</strong></div><div class="card">Tổng mỗi vị thế<strong>25 USDT / 3 phần</strong></div><div class="card">Cấu hình / đường chạy<strong>24 / 144</strong></div><div class="card">Kiểm thử đạt<strong>78</strong></div></div>
<section class="panel"><h2>So sánh cùng cấu hình</h2><p>Lọc 6 giờ · tối đa 5 vị thế · không SL, không đóng theo thời gian · thêm từng phần khi giá thuận · trailing kích hoạt 3 ATR, hồi 1%. Bảng này dùng chi phí cơ sở. Hai cửa sổ khởi chạy riêng 500 USDT; kết quả 3 tháng không phải phần cuối của tài khoản 12 tháng.</p><div class="scroll"><table><thead><tr><th>Hướng</th><th>Tài sản 12 tháng</th><th>DD 12 tháng</th><th>Số vị thế 12 tháng</th><th>Tài sản 06–08/2026</th><th>Số vị thế 3 tháng</th></tr></thead><tbody>__HIGHLIGHTS__</tbody></table></div><p>__DIAGNOSIS__</p></section>
<section class="panel"><h2>Tài sản và từng tháng</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Giai đoạn<select id="window"><option value="year">Cả năm · 09/2025–08/2026</option><option value="later">Tài khoản mới · 06–08/2026</option><option value="development">09/2025–05/2026</option></select></label><label>Chi phí<select id="cost"><option value="stress" selected>Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản bao gồm vị thế Long và Short còn mở"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div></section>
<section class="panel"><h2>Toàn bộ 24 cấu hình</h2><p>Cặp số: cơ sở / chi phí cao. Danh nghĩa 25 USDT là tổng cả ba phần, tương ứng khoảng 5 USDT ký quỹ ban đầu. “10 chỗ” và “đóng 48h” là phương án nghiên cứu; đóng 48h có thể chốt lỗ.</p><div class="scroll"><table><thead><tr><th>Cấu hình</th><th>Tài sản 12 tháng</th><th>Tài sản 3 tháng</th><th>DD 12 tháng</th><th>Vị thế vào 12 tháng</th></tr></thead><tbody>__ROWS__</tbody></table></div></section>
<section class="panel"><h2>Quy tắc Long và chọn ứng viên</h2><p>Long khi nến 4h trước giảm quá biên trung bình 20 nến trừ 2 độ lệch chuẩn, lợi suất 24h trước ≤ −5%; nến hiện tại xanh và đóng trở lại trên biên đó. Short giữ nguyên quy tắc đảo chiều quá mua. Bộ lọc tùy chọn yêu cầu lợi suất 6h ≥ 0 cho Long, ≤ 0 cho Short. ATR và tín hiệu chỉ dùng nến đã đóng; không dùng giá tương lai để quyết định vào thêm.</p><p>Hai chiều xếp tín hiệu theo mức lệch chuẩn, dùng chung số dư và chỗ trống. Mỗi coin chỉ giữ một chiều; tín hiệu ngược chiều bị bỏ qua khi đang có vị thế. Không tự đảo lệnh. Tín hiệu trước bộ lọc 6h: 625 Long / 631 Short; sau lọc: 487 Long / 497 Short.</p><p>__SELECTION__</p><p>__AUDIT__</p></section>
<section class="panel"><h2>Cách đọc kết quả</h2><p>Tài sản cuối gồm phí, funding và lãi/lỗ chưa chốt. Phí/trượt cơ sở 0,05%/0,20%, mức cao 0,10%/0,50% mỗi lần khớp. Đường chi phí cao có thể khác lựa chọn/khối lượng/lúc thoát, nên không nhất thiết luôn thấp hơn đường cơ sở. Trailing mô phỏng quan sát nến đóng 5 phút, thoát ở giá mở tiếp theo cộng trượt bất lợi; không cam kết thoát đúng mức kích hoạt hoặc luôn có lãi.</p><p>Funding dương: Long trả, Short nhận; funding âm thì ngược lại, tính theo lượng thực giữ tại kỳ thanh toán. <a href="https://www.binance.com/en/academy/glossary/funding-fees">Quy tắc funding Binance</a>.</p><p>Dừng mở mới ở giảm 20% không tự đóng vị thế cũ. Kết quả còn hạn chế bởi bộ lọc sàn hiện tại, maintenance margin giả định 1% tổng danh nghĩa, thiếu bậc ký quỹ/sổ lệnh lịch sử, mẫu nến 5 phút và thiên lệch tập coin. Không đủ bằng chứng giao dịch tiền thật. Bộ thực thi live và khóa API không thay đổi; chưa bật live.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">144 kết quả</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc khóa</a> · <a href="signals.json">Tín hiệu nguồn</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    for k,value in dict(STYLE=style,TITLE=escape(title),TARGET=escape(target),FINDING=escape(finding),DIAGNOSIS=escape(diagnosis),
        HIGHLIGHTS="".join(tr(r) for r in highlights),OPTIONS=options,ROWS="".join(tr(r) for r in rows),SELECTION=escape(selection),AUDIT=escape(audit),SCRIPT=script).items():
        html = html.replace("__"+k+"__",value)
    (OUT/"dashboard.html").write_text(html,encoding="utf-8")
    md = ["# "+title,"",target,"",finding,"",diagnosis,"",selection,"",
        "Tài khoản 500 USDT, Cross x5, tổng danh nghĩa 25 USDT/3 phần; 5/10 chỗ; giữ không hạn hoặc đóng 48h. Không thay live.","",
        "Cặp số dưới đây: cơ sở / chi phí cao. Cửa sổ 12 tháng 01/09/2025–01/09/2026; 3 tháng 01/06/2026–01/09/2026, UTC, mỗi cửa sổ khởi chạy riêng 500 USDT.","",
        "| Cấu hình | Tài sản 12 tháng | Tài sản 3 tháng | DD 12 tháng | Vị thế 12 tháng |","|---|---:|---:|---:|---|",
        *["| "+" | ".join(r)+" |" for r in rows],"",audit,"",
        "Không có bằng chứng đạt 50% mỗi tháng. Kiểm định lịch sử đã dùng lặp, không phải OOS sạch. Maintenance 1% chỉ là proxy; bộ lọc sàn hiện tại, không sổ lệnh lịch sử. Giữ lỗ mở và mọi funding thực, không giả định thoát tay thuận lợi.","",
        "Long trả funding dương, nhận funding âm theo lượng giữ thực. [Binance](https://www.binance.com/en/academy/glossary/funding-fees).","",
        "[Dashboard](dashboard.html) · [Quy tắc khóa](protocol.json) · [Đối soát](verification.json)"]
    (OUT/"report.md").write_text("\n".join(md),encoding="utf-8")
    write(OUT/"goal_progress.json",dict(classification="progress",goal_status="active",achieved=False,runs=144,
        target_passes=s["target_met_rows"],evidence=finding,live_config_unchanged=True))
    print(OUT/"dashboard.html")


if __name__ == "__main__": main()
