"""Capacity sensitivity with finite capital and explicit incomplete paths."""
import json
from html import escape
import pandas as pd
from compare_account_risk import ROOT,write
from search_capacity_expansion import OUT


def name(s):
    return ("Đảo chiều + lọc6h" if s["source"]["mask"]==2 else "Đảo chiều")+f" · tối đa{s['cap']}coin · ký quỹ{s['notional']/5:g} · "+("giữ không hạn" if s["holding"]=="hold" else "đóng tối đa48h")


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));v=json.loads((OUT/"verification.json").read_text());f=json.loads((OUT/"findings.json").read_text(encoding="utf-8"))
    assert len(s["results"])==v["journals_audited"]==192
    num=lambda x:"Không hoàn tất" if x is None else f"{x:.2f}"
    tr=lambda xs:"<tr>"+"".join("<td>"+escape(str(x))+"</td>" for x in xs)+"</tr>"
    lookup={(r["strategy_id"],r["window"],r["cost"]):r for r in s["results"]};rows=[];series=[]
    for spec in s["specs"]:
        rs=lambda w:[lookup[(spec["id"],w,c)] for c in ["base","stress"]]
        rows.append([name(spec),*[' / '.join(num(r["ending_equity"]) for r in rs(w)) for w in ["year","later"]],
            ' / '.join(f"{r['max_drawdown']*100:.2f}%" for r in rs("year")),
            ' / '.join(str(r["entries"]) for r in rs("year")),
            ' / '.join(str(r["peak_positions"]) for r in rs("year")),
            ' / '.join(str(r["insufficient_margin"]) for r in rs("year"))])
    for row in s["results"]:
        frame=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet");ix={0,len(frame)-1}
        for _,g in frame.groupby((frame["at"]-frame["at"].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(row,points=[[int(q["at"]),round(q.equity,6)] for _,q in frame.loc[sorted(ix)].iterrows()]))
    write(OUT/"dashboard_data.json",series)
    old=(ROOT/"artifacts/execution_costs_20260925/dashboard.html").read_text(encoding="utf-8");style=old.split("<style>",1)[1].split("</style>",1)[0];script=old.split("<script>",1)[1].split("</script>",1)[0]
    options="".join(f'<option value="{p["id"]}"'+(' selected' if p["id"]=="mask2_n25_hold_cap30" else '')+'>'+escape(name(p))+'</option>' for p in s["specs"])
    target=f"{s['target_met_rows']}/192 đường đạt50% ở từng tháng; {s['incomplete_paths']} đường không hoàn tất."
    audit=f"{v['journals_audited']} sổ đối soát; {v['baseline_paths_exact']} đường5chỗ khớp lượt trước; {v['replayed_paths_exact']} đường tăng chỗ chạy lại khớp. {v['funding_quantities_checked']} lần funding kiểm tra lượng giữ; {v['independent_entry_capital_conditions']} lần vào kiểm tra độc lập điều kiện vốn cần thiết. 63 kiểm thử đạt; hash dữ liệu/mã nguồn/bộ lọc sàn/live khớp."
    stops=[]
    for r in v["incomplete_paths"]:
        at=r["stop_event"].get("at") if r["stop_event"] else None
        stops.append(tr([r["id"],"Không có" if at is None else pd.Timestamp(at,unit="ms",tz="UTC").isoformat(),str(r["errors"])]))
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Mở rộng số vị thế</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / GIỚI HẠN SỐ COIN · LƯỢT 18</div><h1>__TITLE__</h1><p class="muted">01/09/2025–01/09/2026 UTC · tài khoản chung500USDT · Crossx5 · giữ nguyên30altcoin và tín hiệu</p><div class="notice"><b>__TARGET__</b><p>__FINDING__</p></div><div class="cards"><div class="card">Giới hạn đồng thời<strong>5/10/20/30</strong></div><div class="card">Cấu hình<strong>32</strong></div><div class="card">Đường tài khoản<strong>192</strong></div><div class="card">Kiểm thử đạt<strong>63</strong></div></div>
<section class="panel"><h2>So sánh đầy đủ</h2><p>Cặp số: cơ sở / chi phí cao. Tài sản cuối tính lỗ mở, phí, funding. Mỗi cửa sổ bắt đầu riêng500USDT. Danh nghĩa25/100USDT là tổng cả ba phần, tương ứng ký quỹ dự kiến5/20USDT. Giữ một vị thế mỗi coin; không DCA. 30chỗ chỉ không còn giới hạn số coin trong danh sách30, không đồng nghĩa vô hạn vốn.</p><div class="scroll"><table><thead><tr><th>Cấu hình</th><th>Tài sản12tháng</th><th>Tài sản3tháng sau</th><th>DD12tháng</th><th>Vị thế vào12tháng</th><th>Đồng thời cao nhất</th><th>Từ chối thiếu ký quỹ</th></tr></thead><tbody>__ROWS__</tbody></table></div></section>
<section class="panel"><h2>Tài sản và từng tháng</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Giai đoạn<select id="window"><option value="year">Cả năm · 09/2025–08/2026</option><option value="later">Tài khoản mới · 06–08/2026</option><option value="development">09/2025–05/2026</option></select></label><label>So sánh<select id="cost"><option value="stress" selected>Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản bao gồm vị thế mở"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div></section>
<section class="panel"><h2>Đường không hoàn tất</h2><p>Không gán tài sản cuối hoặc lợi suất0% cho phần sau khi dữ liệu/mô hình không còn đủ điều kiện. Nếu chạm maintenance proxy thì dừng mô phỏng; đó không phải số dư thanh lý chính xác trên Binance.</p><div class="scroll"><table><thead><tr><th>Đường</th><th>Thời điểmUTC</th><th>Lý do</th></tr></thead><tbody>__STOPS__</tbody></table></div></section>
<section class="panel"><h2>Quy tắc giữ nguyên và giới hạn</h2><p>Hai nguồn đảo chiều có/không lọc6h, ba phần thêm khi giá thuận0,25ATR, hết hạn thêm6h. Trailing kích hoạt3ATR/hồi1%. Dừng mở mới ởDD20% giữ vị thế cũ, nên lỗ có thể tăng tiếp. Giữ không hạn không cóSL; biến thể48h có thể đóng lỗ. Tăng số chỗ và ký quỹ20USDT chỉ là nghiên cứu, không thay giới hạn live.</p><p>Ký quỹ khả dụng phải đủ cho vị thế hiện hữu, các phần vào chưa khớp và phí dự phòng. Mức30coin không bỏ qua kiểm tra vốn. Phí/trượt cơ sở0,05%/0,20%, cao0,10%/0,50% mỗi lần khớp.</p><p>__AUDIT__</p><p class="muted">Lịch sử đã dùng thử nhiều lần; không phải dữ liệu tương lai độc lập. Bộ lọc sàn hiện tại, MMR1%proxy thay bậc lịch sử, mẫu5phút và trượt giá giả định; thiếu sổ lệnh lịch sử và có thể thiếu coin hủy niêm yết. MMRproxy đặc biệt hạn chế kết luận khi tăng nhiều vị thế cùng hướng. Không bật live.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">192kết quả</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc khóa</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    for k,val in dict(STYLE=style,TITLE=escape(f["title"]),TARGET=escape(target),FINDING=escape(f["finding"]),ROWS="".join(tr(r) for r in rows),OPTIONS=options,STOPS="".join(stops) if stops else '<tr><td colspan="3">Không có đường bị dừng vì thiếu dữ liệu hoặc chạm proxy trong lượt này.</td></tr>',AUDIT=escape(audit),SCRIPT=script).items():html=html.replace("__"+k+"__",val)
    (OUT/"dashboard.html").write_text(html,encoding="utf-8")
    md=["# "+f["title"],"",target,"",f["finding"],"","Cặp số: cơ sở/chi phí cao. Mỗi cửa sổ khởi chạy riêng500USDT, tính cả vị thế mở. 30coin không phải vô hạn vốn;48h có thể đóng lỗ.","","| Cấu hình |12tháng|3tháng|DD12tháng|Vị thế12tháng|Đồng thời tối đa|Thiếu ký quỹ|","|---|---:|---:|---:|---:|---:|---:|",*["| "+" | ".join(r)+" |" for r in rows],"",audit,"","Lịch sử dùng lặp,currentfilters,MMR1%proxy,5msampling,assumedslippage,universe bias. Không thay live.","","[Dashboard](dashboard.html) · [Quy tắc](protocol.json)"]
    (OUT/"report.md").write_text("\n".join(md),encoding="utf-8")
    write(OUT/"goal_progress.json",dict(classification="progress",goal_status="active",achieved=False,runs=192,target_passes=s["target_met_rows"],evidence=f["finding"],next_steps=f["next_steps"],live_config_unchanged=True));print(OUT/"dashboard.html")


if __name__=="__main__":main()
