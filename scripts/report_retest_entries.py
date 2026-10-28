"""Publish causal first-entry comparison and account/event distinctions."""

import json
from html import escape
import pandas as pd
from compare_account_risk import write
from search_retest_entries import OUT,PRIOR


def num(x):return "Không hoàn tất" if x is None else f"{x:.2f}"


def name(s):return f"{'Lọc 6h' if s['mask'] else 'Không lọc'} · ký quỹ {s['notional']/5:g} · {s['timing']['label']}"


def tr(v):return "<tr>"+"".join("<td>"+escape(str(x))+"</td>" for x in v)+"</tr>"


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));audit=json.loads((OUT/"verification.json").read_text(encoding="utf-8"));findings=json.loads((OUT/"findings.json").read_text(encoding="utf-8"))
    screens=json.loads((OUT/"screens.json").read_text(encoding="utf-8"));specs={p["id"]:p for p in s["specs"]}
    diagnosis=json.loads((OUT/"readiness_diagnosis.json").read_text(encoding="utf-8"))
    assert diagnosis["selection_unchanged_if_reclassified"] and diagnosis["actual_missing_price_or_feature_cases"]==0
    assert audit["journals_audited"]==len(s["results"])
    lookup={(r["strategy_id"],r["window"],r["cost"]):r for r in s["results"]}
    pair=lambda rs,key:" / ".join(num(r[key]) for r in rs)
    selected=[];mdrows=[];primary=[];eventrows=[]
    for ident in s["selected"]:
        spec=specs[ident];rs=lambda w:[lookup[(ident,w,c)] for c in ["base","stress"]]
        control=[lookup[(f"mask{spec['mask']:02d}_n{spec['notional']}_immediate","later",c)] for c in ["base","stress"]]
        values=[name(spec),pair(rs("development"),"ending_equity"),pair(rs("later"),"ending_equity"),pair(control,"ending_equity"),pair(rs("year"),"ending_equity"),f"{max(r['max_drawdown'] for r in rs('year'))*100:.2f}%"]
        selected.append(tr(values));mdrows.append("| "+" | ".join(values)+" |")
    for spec in s["specs"]:
        if spec["mask"]!=2 or spec["notional"]!=25:continue
        rs=[lookup[(spec["id"],"year",c)] for c in ["base","stress"]];later=[lookup[(spec["id"],"later",c)] for c in ["base","stress"]]
        primary.append(tr([spec["timing"]["label"],pair(rs,"ending_equity"),pair(later,"ending_equity"),
            " / ".join(str(r["entries"]) for r in rs),rs[0]["watch_counts"].get("triggered",0),rs[0]["guard_counts"].get("accepted",0),
            f"{max(r['max_drawdown'] for r in rs)*100:.2f}%"]))
    selected_event_keys={(specs[i]["mask"],specs[i]["timing"]["id"]) for i in s["selected"]}
    for r in screens:
        if r["window"]!="later" or (r["mask"],r["timing"]) not in selected_event_keys:continue
        label=next(p["timing"]["label"] for p in s["specs"] if p["timing"]["id"]==r["timing"])
        def stat(c):
            v=r["cases"][c]
            return "Không đủ" if v["mean_net_return"] is None else f"{100*v['mean_net_return']:.2f}% · [{100*v['ci95'][0]:.2f}%; {100*v['ci95'][1]:.2f}%]"
        eventrows.append(tr([("Lọc 6h" if r["mask"] else "Không lọc")+" · "+label,f"{r['hours']} giờ",r["counts"]["complete"],stat("base"),stat("stress")]))
    series=[]
    for r in s["results"]:
        f=pd.read_parquet(OUT/"runs"/f"{r['id']}_equity.parquet");ix={0,len(f)-1}
        for _,g in f.groupby((f["at"]-f["at"].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(r,points=[[int(v["at"]),round(v.equity,6)] for _,v in f.loc[sorted(ix)].iterrows()]))
    write(OUT/"dashboard_data.json",series)
    old=(PRIOR/"dashboard.html").read_text(encoding="utf-8");style=old.split("<style>",1)[1].split("</style>",1)[0];script=old.split("<script>",1)[1].split("</script>",1)[0]
    script=script.replace("cuối ${num(r.ending_equity)} USDT", "${r.ending_equity===null?'Không hoàn tất · dừng '+date(r.stop_event.at)+' tại maintenance proxy · không xác định số dư cuối':'cuối '+num(r.ending_equity)+' USDT'}")
    default=next((i for i in s["selected"] if specs[i]["mask"]==2 and specs[i]["notional"]==25),"mask02_n25_immediate")
    options="".join(f'<option value="{p["id"]}"'+(' selected' if p["id"]==default else '')+'>'+escape(name(p))+(' · đã khóa' if p["id"] in s["selected"] else '')+'</option>' for p in s["specs"])
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Điểm vào sau hồi thất bại</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / ĐIỂM VÀO ĐẦU TIÊN · LƯỢT 12</div><h1>__TITLE__</h1><p class="muted">01/09/2025–01/09/2026, UTC, không gồm ngày cuối · 500 USDT · Cross x5 · tối đa 5 vị thế · ba phần 0,25 ATR · trailing 3 ATR/hồi 1%</p><div class="notice"><b>__TARGET__</b><p>__FINDING__</p></div>
<div class="cards"><div class="card">Quy tắc điểm vào<strong>12</strong></div><div class="card">Cấu hình<strong>48</strong></div><div class="card">Đường tài khoản<strong>288</strong></div><div class="card">Kiểm thử đạt<strong>116</strong></div></div>
<section class="panel"><h2>Bốn nhóm ứng viên chọn từ giai đoạn đầu</h2><p>Chọn riêng bộ lọc/quy mô trên 09/2025–05/2026: tháng tệ nhất tốt nhất ở cả hai mức chi phí, rồi tài sản cuối. Phải đủ dữ liệu, hoàn tất, DD dưới 20% và ít nhất 20 vị thế đã đóng ở mỗi mức chi phí. Khóa trước khi chạy kỳ sau trong lượt này. Lịch sử kỳ sau đã từng được xem, không gọi là kiểm tra độc lập.</p><div class="scroll"><table><thead><tr><th>Ứng viên</th><th>9 tháng đầu</th><th>3 tháng sau</th><th>Vào ngay · 3 tháng</th><th>Cả năm</th><th>DD cả năm lớn nhất</th></tr></thead><tbody>__SELECTED__</tbody></table></div><p>Các cặp số: cơ sở / chi phí cao. Từng cửa sổ khởi chạy riêng từ 500 USDT. Cả năm giữ nguyên tài khoản, vị thế và mốc đỉnh xuyên suốt. Không cộng kết quả các tài khoản khởi chạy khác nhau.</p></section>
<section class="panel"><h2>Đủ 12 cách vào · ký quỹ 5 USDT, lọc 6h</h2><p>Tổng danh nghĩa 25 USDT cho cả ba phần. “Kích hoạt” là số lần điều kiện điểm vào xảy ra; “Qua lọc” áp dụng ret6h≤0 tại lúc kích hoạt. Số vị thế thực vào còn phụ thuộc chỗ trống, vốn, quy tắc sàn và trạng thái dừng mở mới.</p><div class="scroll"><table><thead><tr><th>Điểm vào</th><th>Tài sản cả năm</th><th>Tài sản 3 tháng sau</th><th>Vị thế vào cả năm</th><th>Kích hoạt</th><th>Qua lọc</th><th>DD cả năm lớn nhất</th></tr></thead><tbody>__PRIMARY__</tbody></table></div></section>
<section class="panel"><h2>Xem đường tài sản và từng tháng</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Giai đoạn<select id="window"><option value="year">Cả năm · 09/2025–08/2026</option><option value="later">Tài khoản mới · 06–08/2026</option><option value="development">Chọn tham số · 09/2025–05/2026</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Chi phí cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản gồm vị thế mở theo thời gian"></svg><div id="chartStatus">Đang tải dữ liệu…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><p class="muted">Đồ thị giữ đầu, cuối, đáy và đỉnh mỗi ngày; vị thế còn mở được định giá. Không thay tháng thiếu bằng lợi suất 0%.</p></section>
<section class="panel"><h2>Tín hiệu sau 4 giờ và 24 giờ · kỳ 06–08/2026</h2><p>Đây là lợi suất trên danh nghĩa của từng sự kiện nếu đóng sau thời hạn cố định, tính phí, trượt giá và funding. Không phải lợi suất tài khoản hay chiến lược trailing. Bảng nêu trung bình và khoảng bootstrap 95% theo khối 7 ngày, gom coin cùng thời điểm; chưa điều chỉnh việc thử nhiều cấu hình. Các sự kiện trùng thời gian không được coi là các giao dịch độc lập.</p><div class="scroll"><table><thead><tr><th>Quy tắc đã khóa</th><th>Thời hạn</th><th>Sự kiện đủ dữ liệu</th><th>Cơ sở: TB · khoảng 95%</th><th>Cao: TB · khoảng 95%</th></tr></thead><tbody>__EVENTS__</tbody></table></div></section>
<section class="panel"><h2>Quy tắc đã đăng ký</h2><p>Đối chứng: vào ngay; chờ 60 phút; giảm thêm 0,5 ATR; hồi lên 0,5 ATR rồi giảm lại 0,25 ATR. Tám quy tắc mới: giảm 0,25/0,5 ATR, hồi từ đáy 0,25/0,5 ATR, rồi giảm 0,25 ATR từ đỉnh hồi; thời hạn chờ 6/24 giờ. Ba bước phải ở các nến 5 phút đã đóng khác nhau. ATR và điểm xếp hạng giữ nguyên từ tín hiệu 4h ban đầu.</p><p>Chỉ kiểm tra giá đã biết. Khi đủ điều kiện mới tạo ý định vào thị trường; khớp giá mở nến tiếp theo cộng trượt giá bất lợi. Giá nhảy không được dùng để bỏ lệnh hồi tố. Mỗi sự kiện chỉ thử một lần; hết hạn, lỗi dữ liệu và chưa hết thời hạn cuối kỳ được ghi riêng. Bộ lọc 6h được kiểm tra lại tại thời điểm thực vào, không dùng giá trị cũ lúc phát tín hiệu.</p><p>Danh sách theo dõi ảo không đặt lệnh sàn, không giữ vốn/chỗ cho đến lúc kích hoạt. Không SL hoặc đóng theo giờ. Dừng mở mới khi giảm 20% từ đỉnh vẫn giữ vị thế cũ. Phí 0,05%/0,10%; trượt giá 0,20%/0,50%; funding thực. Quy mô ký quỹ 20 USDT chỉ để nghiên cứu, cấu hình live giữ nguyên.</p></section>
<section class="panel"><h2>Đối soát và giới hạn</h2><p>__AUDIT__</p><p>Bốn đường không hoàn tất đều thuộc cách chờ giảm thêm 0,5 ATR, lọc 6h, ký quỹ 20 USDT: hai mức chi phí trong kỳ phát triển và cả năm cùng chạm maintenance proxy ở tháng 11/2025 khi còn Short SOON. Không dựng số dư sau thanh lý hoặc điền tháng còn lại bằng 0%.</p><p>Nhãn cũ “stale_features” xuất hiện ở một sự kiện SOON trong các biến thể chờ 24h, ảnh hưởng 32 đường. Kiểm tra riêng xác nhận đủ 120 giờ nến, dữ liệu mới và hữu hạn; thực tế thanh khoản 24h xuống dưới ngưỡng 2 triệu USDT, không phải thiếu giá. Giữ nguyên việc loại tín hiệu, mọi lệnh/kết quả và bản khóa ứng viên. Nếu phân loại đúng nguyên nhân thì lựa chọn ứng viên vẫn không đổi; chẩn đoán và bản gốc được lưu riêng.</p><p>__LIMITS__</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">288 kết quả</a> · <a href="screens.json">Đo từng sự kiện</a> · <a href="verification.json">Đối soát</a> · <a href="readiness_diagnosis.json">Chẩn đoán thanh khoản</a> · <a href="protocol.json">Quy tắc</a> · <a href="candidate_lock.json">Bản khóa lựa chọn</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    target=f"{s['target_met_rows']}/288 đường đạt 50% từng tháng; {s['incomplete_paths']} đường dừng ở maintenance proxy. Dữ liệu bị gắn cờ đã được chẩn đoán riêng."
    audit_text=f"{audit['journals_audited']} sổ đối soát; {audit['baseline_paths_exact']} đối chứng vào ngay khớp lượt trước; {audit['replayed_paths_exact']} đường chạy lại khớp. Một cách tính độc lập xác nhận {audit['independent_watch_oracle_checked']} lần theo dõi; {audit['entry_prefixes_exact']} tập điểm vào trước ranh giới thời gian khớp; {audit['event_screens_recomputed']} bảng sự kiện tính lại. 116 kiểm thử đạt. Nguồn tín hiệu được tái tạo, hash dữ liệu/mã nguồn và cấu hình live khớp."
    limits="Giới hạn: nghiên cứu lặp trên cùng lịch sử; maintenance proxy 1% thay bậc lịch sử, bộ lọc sàn hiện tại, lấy mẫu 5 phút, chưa có orderbook, kho có thể thiếu coin hủy niêm yết. Kết quả có lời không tự xác nhận lợi thế tương lai hoặc điều kiện giao dịch thật. Không loại coin gây lỗ."
    for k,v in dict(STYLE=style,TITLE=escape(findings["title"]),TARGET=escape(target),FINDING=escape(findings["finding"]),SELECTED="".join(selected),PRIMARY="".join(primary),EVENTS="".join(eventrows),OPTIONS=options,AUDIT=escape(audit_text),LIMITS=escape(limits),SCRIPT=script).items():html=html.replace("__"+k+"__",v)
    (OUT/"dashboard.html").write_text(html,encoding="utf-8")
    md=["# "+findings["title"],"",target,"",findings["finding"],"",
        "Cặp số: cơ sở / chi phí cao; mỗi cửa sổ khởi chạy riêng từ500USDT. Các quy tắc chọn bằng09/2025–05/2026, lịch sử sau đã dùng nhiều lần.","",
        "| Ứng viên | 9 tháng đầu | 3 tháng sau | Vào ngay3tháng | Cả năm | DD cả năm |","|---|---:|---:|---:|---:|---:|",*mdrows,"",
        "Các nghiên cứu4h/24h đo lợi suất từng sự kiện trên danh nghĩa, không phải tài khoản trailing. Khoảngbootstrap7ngày chưa điều chỉnh thử nhiều cấu hình.","",
        "Bốn đường chờ giảm0,5ATR/lọc6h/ký quỹ20 chạm maintenance proxy tháng11/2025 khi cònSOON; hai mức chi phí lặp trong kỳ phát triển và cả năm. Không có số dư cuối giả định. Nhãnstale_features trên32đường do một sự kiệnSOON thanh khoản24h dưới2triệu, đã xác nhận đủ120giờ nến và đặc trưng hữu hạn/mới. Chẩn đoán không đổi giao dịch hoặc bản khóa; lựa chọn cũng không đổi khi sửa phân loại nguyên nhân.","",audit_text,"",limits,"",
        "[Dashboard](dashboard.html) · [Kết quả](comparison.csv) · [Quy tắc](protocol.json)"]
    (OUT/"report.md").write_text("\n".join(md),encoding="utf-8")
    write(OUT/"goal_progress.json",dict(classification="progress",goal_status="active",achieved=False,runs=len(s["results"]),target_passes=s["target_met_rows"],
        evidence=findings["finding"],next_steps=findings["next_steps"],live_config_unchanged=True))
    print(OUT/"dashboard.html")


if __name__=="__main__":main()
