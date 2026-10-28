"""Publish all failed-rally variants, not just ex-post winners."""
import json
from html import escape
import pandas as pd
from compare_account_risk import ROOT,write
from search_failed_rally import OUT


def name(s):
    src=s["source"]
    source="Đảo chiều + lọc 6h (đối chứng)" if s["baseline"] else f"Hồi {src['bounce_atr']} ATR giờ · chờ {src['ttl_hours']}h · "+("BTC giảm" if src["regime"]=="btc_bear" else "không lọc BTC")
    return source+f" · ký quỹ {s['notional']/5:g} · "+("giữ không hạn" if s["holding"]=="hold" else "đóng tối đa 48h")


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));v=json.loads((OUT/"verification.json").read_text(encoding="utf-8"));findings=json.loads((OUT/"findings.json").read_text(encoding="utf-8"))
    assert len(s["results"])==v["journals_audited"]==204
    specs={p["id"]:p for p in s["specs"]};lookup={(r["strategy_id"],r["window"],r["cost"]):r for r in s["results"]}
    num=lambda n:"Không hoàn tất" if n is None else f"{n:.2f}"
    pair=lambda ident,w:" / ".join(num(lookup[(ident,w,c)]["ending_equity"]) for c in ["base","stress"])
    tr=lambda values:"<tr>"+"".join("<td>"+escape(str(x))+"</td>" for x in values)+"</tr>"
    def cells(ident):
        rs=[lookup[(ident,"later",c)] for c in ["base","stress"]]
        return [name(specs[ident]),pair(ident,"development"),pair(ident,"later"),pair(ident,"year")," / ".join(str(r["entries"]) for r in rs)," / ".join(f"{100*r['max_drawdown']:.2f}%" for r in rs)]
    selected=[cells(i) for i in s["selected"]];allrows=[cells(p["id"]) for p in s["specs"]];series=[]
    for row in s["results"]:
        f=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet");ix={0,len(f)-1}
        for _,g in f.groupby((f["at"]-f["at"].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(row,points=[[int(q["at"]),round(q.equity,6)] for _,q in f.loc[sorted(ix)].iterrows()]))
    write(OUT/"dashboard_data.json",series)
    prior=(ROOT/"artifacts/execution_costs_20260925/dashboard.html").read_text(encoding="utf-8")
    style=prior.split("<style>",1)[1].split("</style>",1)[0];script=prior.split("<script>",1)[1].split("</script>",1)[0]
    default=next((i for i in s["selected"] if specs[i]["notional"]==25 and specs[i]["holding"]=="hold"),"benchmark_mask2_n25")
    options="".join(f'<option value="{p["id"]}"'+(' selected' if p["id"]==default else '')+'>'+escape(name(p))+(' · đã khóa' if p["id"] in s["selected"] else '')+'</option>' for p in s["specs"])
    heading="<thead><tr><th>Cấu hình</th><th>9 tháng đầu</th><th>3 tháng sau</th><th>Cả năm</th><th>Vị thế vào 3 tháng</th><th>DD 3 tháng</th></tr></thead>"
    target=f"{s['target_met_rows']}/204 đường đạt 50% ở từng tháng; {s['incomplete_paths']} đường không hoàn tất."
    audit=f"{v['journals_audited']} sổ đối soát, {v['baseline_paths_exact']} đối chứng khớp lượt trước, {v['replayed_paths_exact']} đường chạy lại khớp. Kiểm tra độc lập {v['independent_signals']} tín hiệu, {v['independent_atr_samples']} mẫu ATR; {v['causal_prefixes']} lần kiểm tra cắt bỏ dữ liệu tương lai. {v['funding_quantities_checked']} lần funding đối chiếu lượng nắm giữ. 66 kiểm thử đạt; hash dữ liệu/mã nguồn/cấu hình live khớp."
    rules="500 USDT, Cross x5, tối đa 5 vị thế; danh nghĩa 25/100 USDT là tổng cả ba phần, tương ứng ký quỹ dự kiến 5/20 USDT. Vào thêm khi giá thuận lợi 0,25 ATR, hết hạn thêm sau 6h. Trailing kích hoạt sau 3 ATR khung 4h, hồi 1% thì mua đóng. Giữ không hạn không có stop-loss; biến thể 48h có thể đóng lỗ. Dừng mở mới khi DD20%, giữ vị thế cũ và tiếp tục tính lỗ."
    limitations="Lịch sử đã dùng nghiên cứu nhiều lần, không phải kiểm tra tương lai độc lập. MMR1% là proxy, thiếu bậc maintenance lịch sử; dùng bộ lọc sàn hiện tại, mẫu 5 phút và trượt giá giả định, chưa có sổ lệnh lịch sử; danh sách coin có thể thiếu coin hủy niêm yết. Kết quả không chứng minh lợi nhuận tương lai. Không đổi live."
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Nhịp hồi thất bại</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / ĐIỂM VÀO SAU NHỊP HỒI · LƯỢT 15</div><h1>__TITLE__</h1><p class="muted">01/09/2025–01/09/2026 UTC · 30 altcoin giữ nguyên · tính phí, funding và toàn bộ vị thế mở</p><div class="notice"><b>__TARGET__</b><p>__FINDING__</p></div>
<div class="cards"><div class="card">Nguồn mới<strong>8</strong></div><div class="card">Cấu hình có đối chứng<strong>34</strong></div><div class="card">Đường tài khoản<strong>204</strong></div><div class="card">Kiểm thử đạt<strong>66</strong></div></div>
<section class="panel"><h2>Ứng viên khóa từ 9 tháng đầu</h2><p>Chọn riêng theo quy mô/cách giữ lệnh, phải hoàn tất ở cả hai mức chi phí, DD&lt;20% và ít nhất 20 vị thế đã đóng. Ưu tiên tháng tệ nhất tốt nhất, rồi tài sản cuối. Khóa trước khi chạy kỳ sau trong lượt này; dữ liệu đã từng được xem. Số cặp là cơ sở / chi phí cao. Mỗi cửa sổ bắt đầu lại từ 500 USDT, không cộng các cột với nhau.</p><div class="scroll"><table>__HEAD__<tbody>__SELECTED__</tbody></table></div></section>
<section class="panel"><h2>Tất cả biến thể, gồm cả cấu hình lỗ</h2><p>Cơ sở: phí 0,05% và trượt giá 0,20% mỗi lần khớp. Chi phí cao: 0,10% và 0,50%. Funding dùng lịch sử thực. Ký quỹ 20 USDT và đóng sau 48h là phương án nghiên cứu riêng.</p><div class="scroll"><table>__HEAD__<tbody>__ALL__</tbody></table></div></section>
<section class="panel"><h2>Đường tài sản và lợi suất từng tháng</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Giai đoạn<select id="window"><option value="year">Cả năm · 09/2025–08/2026</option><option value="later" selected>Tài khoản mới · 06–08/2026</option><option value="development">Chọn tham số · 09/2025–05/2026</option></select></label><label>So sánh<select id="cost"><option value="stress" selected>Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản gồm cả vị thế đang mở"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div></section>
<section class="panel"><h2>Điểm vào ba bước</h2><p>1. Nến giờ đóng dưới đáy 12 nến trước, trong xu hướng giảm khung 4h (EMA20&lt;EMA60, giá dưới EMA20, lợi suất 24h âm). 2. Trên nến sau, chờ giá đóng hồi 1 hoặc 2 ATR giờ so với giá đóng thấp nhất kể từ lúc bắt đầu; ATR giờ khóa lúc bắt đầu. 3. Trên một nến sau nữa, giá đóng giảm dưới đáy nến giờ trước mới phát tín hiệu và vào theo giá mở kế tiếp.</p><p>Chờ tối đa 6 hoặc 24 giờ. Mất xu hướng hoặc thiếu dữ liệu thì hủy chờ. Tùy biến thể có yêu cầu BTC cùng giảm. Mỗi coin cách tín hiệu ít nhất 24 giờ; không giả định thứ tự cao/thấp trong cùng nến. ATR dùng cho TP vẫn là ATR khung 4h đã đóng.</p><p>__RULES__</p></section>
<section class="panel"><h2>Đối soát và giới hạn</h2><p>__AUDIT__</p><p>__LIMITS__</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">204 kết quả</a> · <a href="protocol.json">Quy tắc khóa</a> · <a href="verification.json">Đối soát</a> · <a href="candidate_lock.json">Ứng viên khóa</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    for k,val in dict(STYLE=style,TITLE=escape(findings["title"]),TARGET=escape(target),FINDING=escape(findings["finding"]),HEAD=heading,SELECTED="".join(tr(r) for r in selected),ALL="".join(tr(r) for r in allrows),OPTIONS=options,RULES=escape(rules),AUDIT=escape(audit),LIMITS=escape(limitations),SCRIPT=script).items():html=html.replace("__"+k+"__",val)
    (OUT/"dashboard.html").write_text(html,encoding="utf-8")
    md=["# "+findings["title"],"",target,"",findings["finding"],"",rules,"","Cặp số: cơ sở / chi phí cao. Mỗi cửa sổ bắt đầu 500 USDT. Chọn theo 9 tháng đầu; kỳ sau không phải dữ liệu chưa từng xem.","","| Cấu hình | 9 tháng đầu | 3 tháng sau | Cả năm | Vị thế 3 tháng | DD 3 tháng |","|---|---:|---:|---:|---:|---:|",*["| "+" | ".join(r)+" |" for r in selected],"",audit,"",limitations,"","[Dashboard](dashboard.html) · [Toàn bộ kết quả](comparison.csv)"]
    (OUT/"report.md").write_text("\n".join(md),encoding="utf-8")
    write(OUT/"goal_progress.json",dict(classification="progress",goal_status="active",achieved=False,runs=204,target_passes=s["target_met_rows"],evidence=findings["finding"],next_steps=findings["next_steps"],live_config_unchanged=True))
    print(OUT/"dashboard.html")


if __name__=="__main__":main()
