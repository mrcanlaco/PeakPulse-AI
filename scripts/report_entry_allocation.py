"""Report matched-budget entry experiments, including failed development groups."""

import json
from html import escape

import pandas as pd
from compare_account_risk import ROOT, write
from search_entry_allocation import OUT, PRIOR

ENTRY_NAMES={"single":"Vào toàn bộ một lần", "f025":"Ba phần · giảm 0,25 ATR", "f05":"Ba phần · giảm 0,5 ATR (cũ)",
             "time30":"Ba phần · chờ 30/60 phút", "pullback":"Ba phần · chờ hồi 0,25 ATR", "keep":"Ba phần · cho vào tiếp sau kích hoạt"}


def num(x):return "Không hoàn tất" if x is None else f"{x:.2f}"


def name(spec):
    e=spec["exit"]
    return f"{'Lọc 6h' if spec['mask'] else 'Không lọc'} · ký quỹ {spec['notional']/5:g} · {ENTRY_NAMES[spec['entry']]} · trailing {e['activation_atr']:g} ATR/{e['callback_fraction']*100:g}%"


def tr(values):return "<tr>"+"".join("<td>"+escape(str(v))+"</td>" for v in values)+"</tr>"


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));audit=json.loads((OUT/"verification.json").read_text(encoding="utf-8"))
    assert audit["journals_audited"]==len(s["results"])
    specs={p["id"]:p for p in s["specs"]};lookup={(r["strategy_id"],r["window"],r["cost"]):r for r in s["results"]}
    pair=lambda rows,key:" / ".join(num(r[key]) for r in rows)
    selected=[];mdrows=[];primary=[];mdprimary=[]
    for ident in s["selected"]:
        rows=lambda w:[lookup[(ident,w,c)] for c in ["base","stress"]]
        oldid=specs[ident]["reference_id"]+"_f05"
        control=[lookup[(oldid,"later",c)] for c in ["base","stress"]]
        values=[name(specs[ident]),pair(rows("development"),"ending_equity"),pair(rows("later"),"ending_equity"),pair(control,"ending_equity"),pair(rows("year"),"ending_equity"),f"{100*max(r['max_drawdown'] for r in rows('year')):.2f}%"]
        selected.append(tr(values));mdrows.append("| "+" | ".join(values)+" |")
    for exit_id in ["trail_a3_c1","trail_a0.5_c0.25"]:
        for entry in ENTRY_NAMES:
            ident=f"mask02_n25_{exit_id}_{entry}"
            rs=[lookup[(ident,"year",c)] for c in ["base","stress"]];later=[lookup[(ident,"later",c)] for c in ["base","stress"]]
            values=[name(specs[ident]),pair(rs,"ending_equity"),pair(later,"ending_equity"),
                " / ".join(str(r["entries"]) for r in rs),
                " / ".join(f"{r['utilization']['mean_entry_notional']/25*100:.1f}%" for r in rs),
                f"{max(r['max_drawdown'] for r in rs)*100:.2f}%"]
            primary.append(tr(values));mdprimary.append("| "+" | ".join(values)+" |")
    series=[]
    for row in s["results"]:
        f=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet");ix={0,len(f)-1}
        for _,g in f.groupby((f["at"]-f["at"].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(row,points=[[int(v["at"]),round(v.equity,6)] for _,v in f.loc[sorted(ix)].iterrows()]))
    write(OUT/"dashboard_data.json",series)
    prior_html=(PRIOR/"dashboard.html").read_text(encoding="utf-8")
    style=prior_html.split("<style>",1)[1].split("</style>",1)[0]
    chart_script=prior_html.split("<script>",1)[1].split("</script>",1)[0]
    # Use configured window boundaries even when a margin breach leaves no full month.
    chart_script=chart_script.replace("start=months[0].start,end=months.at(-1).end", "start=spans[rows[0].window][0],end=spans[rows[0].window][1]")
    chart_script="const spans="+json.dumps(s["protocol"]["windows"])+";\n"+chart_script
    options="".join(f'<option value="{p["id"]}"'+(' selected' if p["id"]=="mask02_n25_trail_a3_c1_f05" else '')+'>'+escape(name(p))+(' · đã khóa' if p["id"] in s["selected"] else '')+'</option>' for p in s["specs"])
    missing=[]
    for m in [0,2]:
        for n in [25,100]:
            if not any(specs[i]["mask"]==m and specs[i]["notional"]==n for i in s["selected"]):missing.append(f"{'lọc 6h' if m else 'không lọc'}, ký quỹ {n/5:g} USDT")
    missing_text="Không chọn được bản nào qua điều kiện cho nhóm: "+"; ".join(missing)+"." if missing else "Cả bốn nhóm có ứng viên chẩn đoán; việc được chọn không đồng nghĩa đủ điều kiện giao dịch thật."
    findings=json.loads((OUT/"findings.json").read_text(encoding="utf-8"))
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · So sánh cách vào ba phần</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / THỬ NGHIỆM CÁCH VÀO VỐN · LƯỢT 11</div><h1>__TITLE__</h1><p class="muted">01/09/2025–01/09/2026, UTC, không gồm ngày cuối · vốn 500 USDT · Cross x5 · tối đa 5 vị thế · không SL hoặc đóng theo thời gian</p>
<div class="notice"><b>__TARGET__</b><p>__FINDING__</p></div>
<div class="cards"><div class="card">Cách vào vốn<strong>6</strong></div><div class="card">Cấu hình<strong>48</strong></div><div class="card">Đường tài khoản<strong>288</strong></div><div class="card">Kiểm thử đạt<strong>84</strong></div></div>
<section class="panel"><h2>Ứng viên chọn từ giai đoạn đầu</h2><p>Chọn riêng từng nhóm bộ lọc/quy mô, tối đa hóa tháng tệ nhất ở cả hai mức chi phí trong 09/2025–05/2026, rồi tài sản cuối. Bắt buộc hoàn tất và DD dưới 20% ở cả hai mức chi phí. Khóa lựa chọn trước khi chạy kỳ sau trong lượt này. Dữ liệu đã từng được nghiên cứu, không phải tập kiểm tra độc lập.</p><p><b>__MISSING__</b></p><div class="scroll"><table><thead><tr><th>Cấu hình khóa</th><th>9 tháng đầu</th><th>3 tháng sau</th><th>Cách vào cũ · 3 tháng</th><th>Cả năm</th><th>DD cả năm lớn nhất</th></tr></thead><tbody>__SELECTED__</tbody></table></div><p>Các cặp số: cơ sở / chi phí cao. Mỗi cửa sổ chạy riêng từ 500 USDT. Cả năm giữ nguyên tài khoản và vị thế xuyên suốt. Không cộng kết quả các tài khoản khởi chạy khác nhau.</p></section>
<section class="panel"><h2>So sánh đúng ký quỹ 5 USDT · bộ lọc 6 giờ</h2><p>Cùng tổng danh nghĩa 25 USDT cho toàn bộ vị thế. “Vốn đã vào” là tổng danh nghĩa trung bình thực khớp của mỗi vị thế chia cho 25 USDT, gồm cả vị thế còn mở; không phải giới hạn thua lỗ của tài khoản Cross.</p><div class="scroll"><table><thead><tr><th>Cách vào / trailing</th><th>Tài sản cả năm</th><th>Tài sản 3 tháng sau</th><th>Số vị thế cả năm</th><th>Vốn đã vào / kế hoạch</th><th>DD cả năm lớn nhất</th></tr></thead><tbody>__PRIMARY__</tbody></table></div><p>Với trailing 3 ATR, cho vào tiếp sau kích hoạt cho kết quả trùng bản cũ trong các nhóm được nêu; không có cải thiện riêng từ quy tắc này. Hai mức chi phí được mô phỏng lại đầy đủ: giá khớp thay đổi làm thay đổi điều kiện thêm phần, lượng khớp và thời điểm thoát. Vì vậy cột chi phí cao đôi khi có tài sản cuối cao hơn, không phải chi phí cao tự tạo lợi nhuận.</p></section>
<section class="panel"><h2>Xem toàn bộ cấu hình và từng tháng</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Giai đoạn<select id="window"><option value="year">Cả năm · 09/2025–08/2026</option><option value="later">Tài khoản mới · 06–08/2026</option><option value="development">Chọn tham số · 09/2025–05/2026</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Chi phí cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản gồm vị thế mở theo thời gian"></svg><div id="chartStatus">Đang tải dữ liệu…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><p class="muted">Đồ thị giữ đầu, cuối, đáy và đỉnh mỗi ngày. Tháng chưa đủ dữ liệu sau sự cố không được tính là lợi suất 0%.</p></section>
<section class="panel"><h2>Quy tắc vào lệnh và chi phí</h2><p>Sáu cách: vào toàn bộ một lần; chia ba phần khi giá giảm thêm 0,25 ATR; giảm thêm 0,5 ATR; sau 30/60 phút; chờ giảm 0,5 ATR mỗi phần rồi hồi 0,25 ATR; hoặc giữ phần chưa vào sau khi trailing đã kích hoạt. ATR đóng băng từ tín hiệu 4h. Chỉ vào thêm nếu giá đóng nến quan sát không cao hơn giá vào trung bình. Biến thể chờ hồi yêu cầu một đợt giảm/hồi mới cho phần kế tiếp.</p><p>Các lệnh khớp theo giá mở nến kế tiếp cộng trượt giá bất lợi, nên giá nhảy có thể làm giá khớp kém đi dù điều kiện quan sát hợp lệ. Không dùng giá khớp tương lai để lọc bỏ lệnh. Hết hạn thêm sau 6 giờ, một phần tối đa mỗi bước 5 phút, tổng không quá ba phần hoặc ngân sách. Thoát trailing ưu tiên trước vào thêm; dừng mở mới cũng chặn phần bổ sung.</p><p>Trailing giữ nguyên mức kích hoạt tính từ lần vào đầu và đáy quan sát; không đặt lại sau mỗi phần. Hai cấu hình: 0,5 ATR/hồi 0,25% và 3 ATR/hồi 1%. Bản mặc định hủy phần chưa vào khi kích hoạt. Bản “cho vào tiếp” giữ kế hoạch đã dự trù, không tăng tổng ngân sách.</p><p>Phí mỗi lần khớp 0,05% hoặc 0,10%; trượt giá 0,20% hoặc 0,50%. Funding thực và định giá vị thế mở. Quy mô 20 USDT ký quỹ chỉ để nghiên cứu. Một lần vào toàn bộ cũng phải đạt điều kiện tối thiểu của phần 1/3 để hạn chế khác biệt chọn coin giữa hai cách.</p></section>
<section class="panel"><h2>Đối soát và phạm vi kết luận</h2><p>__AUDIT__</p><p>__LIMITS__</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">288 kết quả</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc</a> · <a href="candidate_lock.json">Bản khóa lựa chọn</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    target=f"{s['target_met_rows']}/{len(s['results'])} đường đạt 50% trong từng tháng; {s['incomplete_paths']} đường không hoàn tất."
    audit_text=f"{audit['journals_audited']} sổ đối soát; {audit['baseline_paths_exact']} đường đối chứng khớp bản trước; {audit['replayed_paths_exact']} đường chạy lại khớp. Kiểm tra điều kiện bằng giá đã biết cho {audit['entry_adds_causally_checked']} lần vào thêm, gồm {audit['pullbacks_causally_checked']} lần chờ hồi và {audit['post_activation_adds_checked']} lần thêm sau kích hoạt. 84 kiểm thử đạt. Mã nguồn cũ và cấu hình live giữ nguyên."
    limits="Lịch sử đã được thử nhiều lần; chưa chứng minh lợi thế tương lai. Maintenance margin dùng proxy 1% thay bậc lịch sử; bộ lọc sàn hiện tại, lấy mẫu 5 phút, thiếu orderbook và nguy cơ thiếu coin hủy niêm yết trong kho. Không loại kết quả bất lợi và không bật giao dịch thật."
    replacements=dict(STYLE=style,TITLE=escape(findings["title"]),TARGET=escape(target),FINDING=escape(findings["finding"]),MISSING=escape(missing_text),
        SELECTED="".join(selected),PRIMARY="".join(primary),OPTIONS=options,AUDIT=escape(audit_text),LIMITS=escape(limits),SCRIPT=chart_script)
    for k,v in replacements.items():html=html.replace("__"+k+"__",v)
    (OUT/"dashboard.html").write_text(html,encoding="utf-8")
    md=["# "+findings["title"],"",target,"",findings["finding"],"",missing_text,"",
        "Các cặp số: cơ sở / chi phí cao. Mỗi cửa sổ bắt đầu mới từ500USDT. Lựa chọn dùng giai đoạn09/2025–05/2026; dữ liệu kỳ sau đã từng được xem.","",
        "| Cấu hình | 9 tháng đầu | 3 tháng sau | Đối chứng3tháng | Cả năm | DD cả năm |","|---|---:|---:|---:|---:|---:|",*mdrows,"",
        "## Đúng ký quỹ5USDT, lọc6giờ","","| Cấu hình | Cả năm | 3 tháng sau | Vị thế cả năm | Vốn đã vào | DD |","|---|---:|---:|---:|---:|---:|",*mdprimary,"",
        "Trailing3ATR cho phép vào tiếp sau kích hoạt trùng kết quả bản cũ ở các nhóm nêu trên. Hai mức chi phí có thể tạo lượng khớp và thời điểm khác nhau; cột chi phí cao có lúc kết quả cao hơn không phải do phí tạo lợi nhuận.","",
        audit_text,"",limits,"","[Dashboard](dashboard.html) · [Kết quả](comparison.csv) · [Quy tắc](protocol.json)"]
    (OUT/"report.md").write_text("\n".join(md),encoding="utf-8")
    write(OUT/"goal_progress.json",dict(classification="progress",goal_status="active",achieved=False,runs=len(s["results"]),target_passes=s["target_met_rows"],
        evidence=findings["finding"],next_steps=findings["next_steps"],live_config_unchanged=True))
    print(OUT/"dashboard.html")


if __name__=="__main__":main()
