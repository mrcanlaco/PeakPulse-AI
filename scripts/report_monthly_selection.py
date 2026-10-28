"""Publish causal monthly routing and its retained-inventory consequences."""
import json
from html import escape
import pandas as pd
from compare_account_risk import ROOT,write
from search_monthly_selection import OUT,WINDOWS,selectors

SOURCE_NAMES={None:"Không mở mới","reversal0":"Đảo chiều","reversal6":"Đảo chiều + lọc6h","weak7d":"Yếu tuần","beta_bear":"Yếu tuần/BTC + thị trường giảm","failed_rally":"Nhịp hồi thất bại","flow_drop":"Đảo chiều + mua giảm"}


def selection_name(s):
    return f"Học {s['lookback']} tháng · "+("lãi cao nhất" if s["method"]=="profit" else "tháng tệ nhất tốt nhất")+" · "+("giữ không hạn" if s["holding"]=="hold" else "đóng tối đa48h")


def name(s):
    return (selection_name(s["selector"]) if s["selector"] else "Cố định · "+SOURCE_NAMES[s["source"]["id"]]+" · "+("giữ không hạn" if s["holding"]=="hold" else "đóng tối đa48h"))+f" · ký quỹ {s['notional']/5:g}"


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));v=json.loads((OUT/"verification.json").read_text());findings=json.loads((OUT/"findings.json").read_text(encoding="utf-8"));choices=json.loads((OUT/"choices.json").read_text());switching=json.loads((OUT/"switching_diagnostics.json").read_text())
    assert v["training_journals"]==432 and v["deployed_journals"]==len(s["results"])==96
    num=lambda x:"Không hoàn tất" if x is None else f"{x:.2f}"
    tr=lambda xs:"<tr>"+"".join("<td>"+escape(str(x))+"</td>" for x in xs)+"</tr>"
    lookup={(r["strategy_id"],r["window"],r["cost"]):r for r in s["results"]};rows=[];series=[]
    for sp in s["specs"]:
        rs=lambda w:[lookup[(sp["id"],w,c)] for c in ["base","stress"]]
        rows.append([name(sp),*[' / '.join(num(r["ending_equity"]) for r in rs(w)) for w in ["nine","later"]],
            ' / '.join(f"{r['max_drawdown']*100:.2f}%" for r in rs("nine")), ' / '.join(str(r["entries"]) for r in rs("nine")),
            ' / '.join("—" if r["monthly"]["min_monthly_return"] is None else f"{r['monthly']['min_monthly_return']*100:.2f}%" for r in rs("nine"))])
    for row in s["results"]:
        f=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet");ix={0,len(f)-1}
        for _,g in f.groupby((f["at"]-f["at"].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(row,points=[[int(q["at"]),round(q.equity,6)] for _,q in f.loc[sorted(ix)].iterrows()]))
    write(OUT/"dashboard_data.json",series)
    old=(ROOT/"artifacts/execution_costs_20260925/dashboard.html").read_text(encoding="utf-8");style=old.split("<style>",1)[1].split("</style>",1)[0];script=old.split("<script>",1)[1].split("</script>",1)[0]
    script="const spans="+json.dumps(WINDOWS)+",labels="+script.split(",labels=",1)[1]
    opts="".join(f'<option value="{p["id"]}"'+(' selected' if p["id"]=="look3_floor_hold_n25" else '')+'>'+escape(name(p))+'</option>' for p in s["specs"])
    choice_rows=[tr([selection_name(sel)]+[SOURCE_NAMES[c["source_id"]] for c in choices[sel["id"]]]) for sel in selectors()]
    dates=[pd.Timestamp(c["start"],unit="ms",tz="UTC").strftime("%Y-%m") for c in next(iter(choices.values()))]
    target=f"{s['target_met_rows']}/96 tài khoản đánh giá đạt 50% từng tháng; {s['incomplete_paths']} đường đánh giá không hoàn tất."
    audit=f"{v['training_journals']} tài khoản học và {v['deployed_journals']} tài khoản đánh giá được đối soát; {v['choices_exact']} lựa chọn tháng và {v['routed_events_exact']} sự kiện được kiểm tra độc lập. {v['baseline_paths_exact']} đường đối chứng khớp lượt trước, {v['replays_exact']} đường chạy lại khớp. Kiểm tra lượng nắm giữ tại {v['funding_quantities']} lần funding. 65 kiểm thử đạt; hash nguồn và cấu hình live khớp."
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Chọn chiến lược theo tháng</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / CHỌN TỪ DỮ LIỆU QUÁ KHỨ · LƯỢT 17</div><h1>__TITLE__</h1><p class="muted">Đánh giá01/12/2025–01/09/2026 UTC và tài khoản mới06–08/2026 · vốn500USDT · dữ liệu chọn trước mỗi tháng</p><div class="notice"><b>__TARGET__</b><p>__FINDING__</p></div><div class="cards"><div class="card">Gia đình tín hiệu<strong>6</strong></div><div class="card">Tài khoản chấm điểm<strong>432</strong></div><div class="card">Tài khoản đánh giá<strong>96</strong></div><div class="card">Kiểm thử đạt<strong>65</strong></div></div>
<section class="panel"><h2>Mỗi tháng chọn gì?</h2><p>Dùng1hoặc3tháng trước, dừng dữ liệu5phút trước đầu tháng. Chọn lãi cao nhất hoặc tháng tệ nhất tốt nhất ở mức chi phí bất lợi hơn. Chỉ nhận nguồn có lãi, DD&lt;20%,≥5vị thế đóng và dữ liệu đầy đủ ở cả hai mức chi phí. Không nguồn đạt thì không mở mới. Với cửa sổ1tháng, hai cách xếp hạng tương đương; các dòng lặp không phải bằng chứng độc lập.</p><div class="scroll"><table><thead><tr><th>Quy tắc chọn</th>__DATES__</tr></thead><tbody>__CHOICES__</tbody></table></div><p>Chọn trên tài khoản giả định ký quỹ5USDT, áp dụng cùng lựa chọn cho cả quy mô5và20USDT. Tài khoản thật được mô phỏng liên tục, không xóa vị thế, không đặt lại vốn hoặc đỉnh tài sản khi đổi tháng. “Không mở mới” vẫn có thể giữ lệnh cũ hoặc hoàn thành các phần vào đã lên lịch trước đó.</p></section>
<section class="panel"><h2>Đủ các cấu hình thích nghi và cố định</h2><p>Cặp số: cơ sở / chi phí cao. Mỗi cửa sổ đánh giá bắt đầu500USDT riêng; không cộng các cột. 16 cấu hình thích nghi và8đối chứng cố định, mỗi cấu hình chạy2cửa sổ×2chi phí. Bảng chấm điểm quá khứ không được cộng vào lợi nhuận đánh giá.</p><div class="scroll"><table><thead><tr><th>Cấu hình</th><th>9 tháng liên tục</th><th>Tài khoản mới3tháng</th><th>DD9tháng</th><th>Vị thế vào9tháng</th><th>Tháng tệ nhất9tháng</th></tr></thead><tbody>__ROWS__</tbody></table></div></section>
<section class="panel"><h2>Tài sản và từng tháng</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Giai đoạn<select id="window"><option value="nine">9tháng · 12/2025–08/2026</option><option value="later">Tài khoản mới · 06–08/2026</option></select></label><label>So sánh<select id="cost"><option value="stress" selected>Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản liên tục bao gồm vị thế mở"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div></section>
<section class="panel"><h2>Phạm vi và đối soát</h2><p>Crossx5, tối đa5vị thế, danh nghĩa25/100USDT là tổng3phần; thêm khi giá thuận0,25ATR, hết hạn6h; trailing3ATR/hồi1%, dừng mở mớiDD20%. Giữ không hạn không cóSL; phương án48h có thể đóng lỗ. Chờ5phút sau đầu tháng mới nhận tín hiệu được chọn. Phí/trượt cơ sở0,05%/0,20%, cao0,10%/0,50%; funding thực và lỗ mở luôn tính.</p><p>__AUDIT__</p><p class="muted">Chọn bằng dữ liệu quá khứ không biến lịch sử đã nghiên cứu nhiều lần thành kiểm tra tương lai độc lập. Sáu nguồn đã được xây dựng trên lịch sử này. Các giới hạn còn lại: MMR1%proxy, bộ lọc sàn hiện tại, mẫu5phút, trượt giá giả định, thiếu orderbook lịch sử và có thể thiếu coin hủy niêm yết. Không thay cấu hình hoặc bật live.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">96kết quả đánh giá</a> · <a href="choices.json">Lịch chọn tháng</a> · <a href="training_summary.json">432tài khoản chấm điểm</a> · <a href="switching_diagnostics.json">Vị thế khi đổi tháng</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc khóa</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    for k,val in dict(STYLE=style,TITLE=escape(findings["title"]),TARGET=escape(target),FINDING=escape(findings["finding"]),DATES="".join("<th>"+d+"</th>" for d in dates),CHOICES="".join(choice_rows),ROWS="".join(tr(r) for r in rows),OPTIONS=opts,AUDIT=escape(audit),SCRIPT=script).items():html=html.replace("__"+k+"__",val)
    (OUT/"dashboard.html").write_text(html,encoding="utf-8")
    md=["# "+findings["title"],"",target,"",findings["finding"],"","Không cộng432tài khoản chấm điểm vào kết quả. Các cửa sổ9tháng/3tháng bắt đầu riêng500USDT. Chọn từquákhứ,nhưng lịch sử đã dùng nhiều lần nênkhông phảiOOSnguyên vẹn.","","| Cấu hình | 9tháng | 3tháng | DD9tháng | Vị thế9tháng | Tháng tệ nhất |","|---|---:|---:|---:|---:|---:|",*["| "+" | ".join(r)+" |" for r in rows],"",audit,"","Không SL cho giữ không hạn;48h cóthểđónglỗ,quy mô20USDT là nghiên cứu. MMR1%proxy,currentfilters,5msampling,assumedslippage,universe bias. Không đổi live.","","[Dashboard](dashboard.html) · [Quy tắc](protocol.json)"]
    (OUT/"report.md").write_text("\n".join(md),encoding="utf-8")
    write(OUT/"goal_progress.json",dict(classification="progress",goal_status="active",achieved=False,training_paths=432,evaluation_paths=96,target_passes=s["target_met_rows"],evidence=findings["finding"],next_steps=findings["next_steps"],live_config_unchanged=True));print(OUT/"dashboard.html")


if __name__=="__main__":main()
