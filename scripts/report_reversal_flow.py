"""Full comparison of frozen price entries with causal taker-flow filters."""
import json
from html import escape
import pandas as pd
from compare_account_risk import ROOT,write
from search_reversal_flow import OUT

GATES={"none":"Không lọc dòng giao dịch","seller":"Mua chủ động ≤50%","drop5":"Tỷ lệ mua giảm ≥5 điểm %","exhaust":"Từ ≥55% mua xuống ≤50%","absorbed":"Mua ≥55% nhưng giá đảo chiều"}


def name(p):
    return ("Có lọc 6h · " if p["source"]["mask"]==2 else "Không lọc 6h · ")+GATES[p["source"]["gate"]]+f" · ký quỹ {p['notional']/5:g} · "+("giữ không hạn" if p["holding"]=="hold" else "đóng tối đa 48h")


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));v=json.loads((OUT/"verification.json").read_text(encoding="utf-8"));findings=json.loads((OUT/"findings.json").read_text(encoding="utf-8"));counts=json.loads((OUT/"signal_counts.json").read_text())
    assert len(s["results"])==v["journals_audited"]==240
    specs={p["id"]:p for p in s["specs"]};lookup={(r["strategy_id"],r["window"],r["cost"]):r for r in s["results"]}
    num=lambda x:"Không hoàn tất" if x is None else f"{x:.2f}"
    pair=lambda i,w:" / ".join(num(lookup[(i,w,c)]["ending_equity"]) for c in ["base","stress"])
    tr=lambda xs:"<tr>"+"".join("<td>"+escape(str(x))+"</td>" for x in xs)+"</tr>"
    def cells(i):
        rs=[lookup[(i,"later",c)] for c in ["base","stress"]]
        return [name(specs[i]),pair(i,"development"),pair(i,"later"),pair(i,"year")," / ".join(str(r["entries"]) for r in rs)," / ".join(f"{r['max_drawdown']*100:.2f}%" for r in rs)]
    selected=[cells(i) for i in s["selected"]];series=[]
    for row in s["results"]:
        f=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet");ix={0,len(f)-1}
        for _,g in f.groupby((f["at"]-f["at"].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(row,points=[[int(q["at"]),round(q.equity,6)] for _,q in f.loc[sorted(ix)].iterrows()]))
    write(OUT/"dashboard_data.json",series)
    old=(ROOT/"artifacts/execution_costs_20260925/dashboard.html").read_text(encoding="utf-8");style=old.split("<style>",1)[1].split("</style>",1)[0];script=old.split("<script>",1)[1].split("</script>",1)[0]
    default=s["selected"][0] if s["selected"] else "mask2_none_n25_hold"
    options="".join(f'<option value="{p["id"]}"'+(' selected' if p["id"]==default else '')+'>'+escape(name(p))+(' · đã khóa' if p["id"] in s["selected"] else '')+'</option>' for p in s["specs"])
    countrows=[tr(["Có" if r["source_id"].startswith("mask2") else "Không",GATES[r["source_id"].split("_",1)[1]],r["input_events"],r["kept"],r["missing_flow"]]) for r in counts]
    head="<thead><tr><th>Cấu hình</th><th>9 tháng đầu</th><th>3 tháng sau</th><th>Cả năm</th><th>Vị thế vào 3 tháng</th><th>DD 3 tháng</th></tr></thead>"
    target=f"{s['target_met_rows']}/240 đường đạt 50% ở từng tháng; {s['incomplete_paths']} đường không hoàn tất."
    audit=f"{v['journals_audited']} sổ tài khoản đối soát; {v['baseline_paths_exact']} đường đối chứng khớp kết quả cũ; {v['replayed_paths_exact']} đường chạy lại khớp. Tính lại độc lập dòng giao dịch cho {v['independent_flow_events']} sự kiện; cả 10 danh sách lọc đều khớp. {v['new_archives_verified']} ZIP và {v['new_price_rows_verified']} nến giá quý sau đã xác minh; {v['funding_quantities_checked']} lần funding đối chiếu lượng nắm giữ. 64 kiểm thử đạt; hash dữ liệu/mã nguồn/live khớp."
    rules="Vốn 500 USDT, Cross x5, tối đa 5 vị thế. Danh nghĩa 25/100 USDT cho tổng ba phần tương ứng ký quỹ dự kiến 5/20 USDT. Thêm phần khi giá thuận lợi 0,25 ATR, hết hạn thêm sau 6h; trailing kích hoạt 3 ATR khung 4h và hồi 1%. Giữ không hạn không có stop-loss; phương án 48h có thể đóng lỗ, chỉ để nghiên cứu. Dừng mở mới ở DD20% vẫn giữ và định giá các vị thế cũ."
    limits="Lịch sử đã dùng thử nhiều lần, không phải dữ liệu tương lai độc lập. Bộ lọc sàn hiện tại, maintenance proxy1%, giá lấy mẫu5phút và trượt giá giả định; chưa có sổ lệnh lịch sử, danh sách có thể thiếu coin hủy niêm yết. Dữ liệu dòng giao dịch kỳ cũ đối chiếu mẫu90coin-tháng, không xác minh công khai mọi dòng cũ. Không đổi cấu hình hoặc bật live."
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Dòng giao dịch sau đảo chiều</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / KIỂM TRA LỰC MUA · LƯỢT 16</div><h1>__TITLE__</h1><p class="muted">01/09/2025–01/09/2026 UTC · 30 altcoin giữ nguyên · dữ liệu nến đã đóng · mọi vị thế mở được tính vào tài sản</p><div class="notice"><b>__TARGET__</b><p>__FINDING__</p></div><div class="cards"><div class="card">Cách lọc gồm đối chứng<strong>5</strong></div><div class="card">Cấu hình tài khoản<strong>40</strong></div><div class="card">Đường mô phỏng<strong>240</strong></div><div class="card">Kiểm thử đạt<strong>64</strong></div></div>
<section class="panel"><h2>Ứng viên khóa trước khi chạy kỳ sau trong lượt này</h2><p>Chọn theo 09/2025–05/2026, riêng từng quy mô/cách giữ lệnh: cả hai mức chi phí phải có tài sản cuối &gt;500, DD&lt;20%, hoàn tất và ≥20 vị thế đóng. Ưu tiên tháng tệ nhất tốt nhất, rồi tài sản cuối. Không lấy các cấu hình thiếu mẫu làm ứng viên. Kỳ sau đã từng được xem ở các lượt trước.</p><div class="scroll"><table>__HEAD__<tbody>__SELECTED__</tbody></table></div><p>Chỉ có __NSELECT__ nhóm đạt điều kiện chọn trong bốn nhóm quy mô/cách giữ lệnh. Được chọn để đánh giá không có nghĩa đủ điều kiện giao dịch thật.</p></section>
<section class="panel"><h2>Bộ lọc giữ lại bao nhiêu tín hiệu?</h2><p>Tổng trên bộ sự kiện lịch sử nạp vào, gồm thời gian làm ấm dữ liệu. Đây là số tín hiệu, không phải số vị thế thực sự được tài khoản nhận. Giữ nguyên sự kiện, thứ tự, điểm ưu tiên, ATR và cooldown cũ; không bổ sung sự kiện mới sau khi lọc.</p><div class="scroll"><table><thead><tr><th>Lọc 6h</th><th>Điều kiện mua chủ động</th><th>Đầu vào</th><th>Giữ lại</th><th>Thiếu flow ở đầu vào</th></tr></thead><tbody>__COUNTS__</tbody></table></div></section>
<section class="panel"><h2>Đủ 40 cấu hình</h2><p>Cặp số: cơ sở / chi phí cao. Cơ sở phí0,05% và trượt0,20%; cao phí0,10% và trượt0,50% mỗi lần khớp, funding thực. Mỗi cửa sổ bắt đầu mới500USDT; không cộng các cột với nhau.</p><div class="scroll"><table>__HEAD__<tbody>__ALL__</tbody></table></div></section>
<section class="panel"><h2>Đường tài sản và từng tháng</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Giai đoạn<select id="window"><option value="year">Cả năm · 09/2025–08/2026</option><option value="later" selected>Tài khoản mới · 06–08/2026</option><option value="development">Chọn tham số · 09/2025–05/2026</option></select></label><label>So sánh<select id="cost"><option value="stress" selected>Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản gồm lãi lỗ chưa chốt"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div></section>
<section class="panel"><h2>Quy tắc</h2><p>Tín hiệu giá gốc: nến4h trước tăng ngoài dải2độ lệch chuẩn và tăng24h ít nhất5%; nến hiện tại đóng giảm về trong dải trước. Có/không thêm lọc lợi suất6h≤0. Tỷ lệ mua tính tổng khối lượng mua chủ động chia tổng khối lượng, cùng đơn vị coin, trên4giờ đã đóng; không lấy trung bình tỷ lệ. So với4giờ ngay trước đó. Thiếu giờ hoặc volume0 được coi là thiếu dữ liệu.</p><p>Nhóm “mua≥55% nhưng giá đảo chiều” kiểm tra giả thuyết khác: mua chủ động vẫn cao nhưng không giữ được giá, không đồng nghĩa lực mua suy yếu. Các trường dữ liệu theo <a href="https://github.com/binance/binance-public-data#klines-1">Binance Public Data</a>; không suy ra vị thế mở hay tồn kho người mua từ tỷ lệ này.</p><p>__RULES__</p></section>
<section class="panel"><h2>Đối soát và giới hạn</h2><p>__AUDIT__</p><p>__LIMITS__</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">240 kết quả</a> · <a href="protocol.json">Quy tắc khóa</a> · <a href="verification.json">Đối soát</a> · <a href="flow_evidence.json">Nguồn flow</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    for k,val in dict(STYLE=style,TITLE=escape(findings["title"]),TARGET=escape(target),FINDING=escape(findings["finding"]),HEAD=head,SELECTED="".join(tr(r) for r in selected),NSELECT=str(len(selected)),COUNTS="".join(countrows),ALL="".join(tr(cells(p["id"])) for p in s["specs"]),OPTIONS=options,RULES=escape(rules),AUDIT=escape(audit),LIMITS=escape(limits),SCRIPT=script).items():html=html.replace("__"+k+"__",val)
    (OUT/"dashboard.html").write_text(html,encoding="utf-8")
    md=["# "+findings["title"],"",target,"",findings["finding"],"",rules,"","Cặp số cơ sở/chi phí cao; mỗi cửa sổ bắt đầu500USDT. Lựa chọn theo9tháng đầu,không phảiOOSnguyên vẹn.","","| Cấu hình | 9 tháng đầu | 3 tháng sau | Cả năm | Vị thế 3 tháng | DD 3 tháng |","|---|---:|---:|---:|---:|---:|",*["| "+" | ".join(r)+" |" for r in selected],"",audit,"",limits,"","Nguồn trường khối lượng: [Binance Public Data](https://github.com/binance/binance-public-data#klines-1).","","[Dashboard](dashboard.html) · [Toàn bộ kết quả](comparison.csv)"]
    (OUT/"report.md").write_text("\n".join(md),encoding="utf-8")
    write(OUT/"goal_progress.json",dict(classification="progress",goal_status="active",achieved=False,runs=240,target_passes=s["target_met_rows"],evidence=findings["finding"],next_steps=findings["next_steps"],live_config_unchanged=True));print(OUT/"dashboard.html")


if __name__=="__main__":main()
