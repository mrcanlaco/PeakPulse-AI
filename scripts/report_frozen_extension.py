"""Report the frozen candidate on later calendar months, including carry inventory."""

import json
from html import escape

import pandas as pd
from compare_account_risk import ROOT,write
from evaluate_frozen_extension import RESULTS
from prepare_frozen_extension import OUT

NAMES={0:"Không lọc",2:"Chỉ lọc lợi suất 6h ≤0",15:"Đủ bốn điều kiện"}


def money(x):return "Không hoàn tất" if x is None else f"{x:.2f}"


def tr(fields):return "<tr>"+"".join("<td>"+escape(str(v))+"</td>" for v in fields)+"</tr>"


def main():
    s=json.loads((RESULTS/"summary.json").read_text(encoding="utf-8"));audit=json.loads((RESULTS/"verification.json").read_text(encoding="utf-8"))
    fresh=[];carry=[];mdrows=[];series=[]
    for spec in s["protocol"]["candidate"]["specs"]:
        rows=[r for r in s["results"] if r["strategy_id"]==spec["id"]]
        name=NAMES[spec["guard"]["mask"]]+f" · ký quỹ {spec['notional']/5:g} USDT"
        f={r["cost"]:r for r in rows if r["window"]=="fresh_june"}
        c={r["cost"]:r for r in rows if r["window"]=="continuous_year"}
        fields=[name,money(f["base"]["ending_equity"]),money(f["stress"]["ending_equity"]),
                f"{max(r['max_drawdown'] for r in f.values())*100:.2f}%",f"{f['base']['entries']} / {f['stress']['entries']}",f"{f['base']['open_count']} / {f['stress']['open_count']}"]
        fresh.append(tr(fields));mdrows.append("| "+" | ".join(fields)+" |")
        open_ages=[r["utilization"]["open_hold_max_days"] for r in c.values() if r["utilization"]["open_hold_max_days"] is not None]
        carry.append(tr([name," / ".join(money(c[k]["new_initial_equity"]) for k in ["base","stress"]),
                         " / ".join(money(c[k]["ending_equity"]) for k in ["base","stress"]),
                         " / ".join(money(c[k]["new_period_pnl"]) for k in ["base","stress"]),
                         " / ".join(str(c[k]["open_count"]) for k in ["base","stress"]),
                         f"{max(open_ages):.1f} ngày" if open_ages else "Không còn vị thế mở"]))
    for row in s["results"]:
        f=pd.read_parquet(RESULTS/"runs"/f"{row['id']}_equity.parquet");ix={0,len(f)-1}
        for _,g in f.groupby((f["at"]-f["at"].iloc[0])//21600000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(row,points=[[int(v["at"]),round(v.equity,6)] for _,v in f.loc[sorted(ix)].iterrows()]))
    write(RESULTS/"dashboard_data.json",series)
    style=(ROOT/"artifacts/guard_ablation_20260925/dashboard.html").read_text(encoding="utf-8").split("<style>",1)[1].split("</style>",1)[0]
    html=r'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Kiểm tra ứng viên đã khóa</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / KIỂM TRA GIAI ĐOẠN SAU · LƯỢT 09</div><h1>Bộ lọc 6 giờ chưa tốt hơn đối chứng trong kỳ mới</h1><p class="muted">Đánh giá 01/06–01/09/2026 (không gồm ngày cuối), UTC · giữ nguyên 30 coin · x5 · ba phần thuận xu hướng · trailing 3 ATR / hồi 1%</p>
<div class="notice"><b>0/24 đường tài khoản đạt 50% trong từng tháng mới.</b><p>Ứng viên lọc 6 giờ có lời nhẹ nhưng kém bản không lọc, ở cả hai mức quy mô và chi phí. Bộ bốn điều kiện lỗ nhẹ. Tất cả tài khoản bắt đầu tháng 6 đều lỗ trong tháng 8. Không nâng ứng viên lên giao dịch thật.</p><span class="pill">Giữ nguyên quy tắc đã khóa · Không chỉnh theo kỳ mới</span></div>
<div class="cards"><div class="card">Cấu hình đã khóa<strong>6</strong></div><div class="card">Đường tài khoản<strong>24</strong></div><div class="card">Lịch sử cũ tái lập<strong>12</strong></div><div class="card">Kiểm thử đạt<strong>114</strong></div></div>
<section class="panel"><h2>Tài khoản mới 500 USDT từ tháng 6</h2><p>Danh nghĩa mỗi vị thế là 25 hoặc 100 USDT, chia cho cả ba phần; mức ký quỹ 20 USDT là giả thuyết nghiên cứu. Hai cột kết quả tương ứng phí/trượt giá cơ sở và mức cao. Kết quả gồm funding, phí và định giá vị thế mở.</p><div class="scroll"><table><thead><tr><th>Cấu hình</th><th>Cuối tháng 8 · cơ sở</th><th>Cuối tháng 8 · cao</th><th>DD lớn nhất hai chi phí</th><th>Vị thế đã vào cơ sở/cao</th><th>Còn mở cơ sở/cao</th></tr></thead><tbody>__FRESH__</tbody></table></div><p>Ở ký quỹ 5 USDT, ứng viên vào 21 vị thế trong ba tháng, cuối kỳ còn năm vị thế; lâu nhất 66,8 ngày. Lợi nhuận ba tháng không chứng minh từng tháng có lời.</p></section>
<section class="panel"><h2>Nếu giữ nguyên tài khoản và vị thế từ tháng 9/2025</h2><p>Đường này bắt đầu với 500 USDT từ 01/09/2025. Cột đầu là tài sản thực đã định giá tại 01/06/2026, không đặt lại về 500. Các cặp số là cơ sở / chi phí cao. Chỉ cột “Lãi/lỗ ba tháng mới” phản ánh phần tăng giảm trong 06–08/2026.</p><div class="scroll"><table><thead><tr><th>Cấu hình</th><th>Tài sản đầu tháng 6</th><th>Tài sản đầu tháng 9</th><th>Lãi/lỗ ba tháng mới</th><th>Còn mở</th><th>Tuổi vị thế mở lớn nhất</th></tr></thead><tbody>__CARRY__</tbody></table></div><p>Với ứng viên 6 giờ, vị thế lâu nhất đã giữ 219 ngày. Ở ký quỹ 5 USDT, ba tháng mới chỉ thêm khoảng 3,11–5,55 USDT. Đối chứng không lọc ở quy mô 20 USDT đã khóa mở mới từ kỳ trước; không tự bật lại khi chuyển tháng.</p></section>
<section class="panel"><h2>Xem đường tài sản và từng tháng</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Cách khởi chạy<select id="window"><option value="fresh_june">Bắt đầu mới 500 USDT · 06–08/2026</option><option value="continuous_year">Giữ tài khoản cũ · 09/2025–08/2026</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Chi phí cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản theo thời gian, gồm vị thế mở"></svg><div id="chartStatus"></div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><p class="muted">Biểu đồ giữ biến động cực trị mỗi khoảng 6 giờ. Khi chọn tài khoản cũ, lợi suất tháng nối tiếp đúng tài sản kỳ trước; không coi lợi nhuận cả năm là lợi nhuận ba tháng mới.</p></section>
<section class="panel"><h2>Khoảng thiếu dữ liệu đã được xử lý thế nào?</h2><p>Kho cục bộ thiếu tổng 214.272 nến giao dịch trong kỳ trên 31 mã kể cả BTC. Dùng 93 file tháng chính thức của Binance, đủ 821.376 nến; mọi giá và khối lượng định giá có mặt ở cả hai nguồn đều khớp. Không nội suy hoặc tạo nến giả.</p><p>File giá đánh dấu theo tháng thiếu ngày 29/06/2026 ở 30 coin. Đã lấy 8.640 nến thực từ API công khai, kiểm tra cả nến giáp ranh với file tháng. Tổng dữ liệu cuối gồm 794.880 nến đánh dấu và 11.580 bản ghi funding với giá đánh dấu tại lúc thanh toán. Báo cáo thiếu ban đầu được giữ nguyên.</p><p>273 file ZIP đã kiểm tra checksum; 24 sổ giao dịch đối soát. Quy tắc và danh sách coin khớp bản khóa trước khi lấy dữ liệu mới. 12 đường tài khoản cũ khớp chính xác trước ranh giới tháng 6; bốn đường ứng viên tái lập. 114 kiểm thử đạt, có kiểm tra không tính funding trùng ở ranh giới và không dùng dữ liệu tương lai.</p></section>
<section class="panel"><h2>Phạm vi kết luận</h2><p>Giữ ba biến thể đã khóa: không lọc, chỉ ret6h≤0, đủ bốn điều kiện. Không tìm lại tham số trên 06–08/2026. Giai đoạn này từng được nghiên cứu với chiến lược khác nên không gọi là lịch sử hoàn toàn chưa từng sử dụng. Tín hiệu gốc, thứ tự ưu tiên, ba phần, TP trailing và điều kiện dừng mở mới giữ nguyên.</p><p>Cơ sở: phí 0,05% / trượt giá 0,20%; mức cao: 0,10% / 0,50% mỗi lần khớp thị trường. Funding thực và lãi/lỗ vị thế mở đã tính. Không SL hoặc đóng theo giờ; DD20% chỉ dừng mở mới, không giới hạn lỗ cũ ở20%.</p><p class="muted">Còn giới hạn danh sách kho có thể thiếu coin hủy niêm yết, bộ lọc sàn hiện tại, maintenance1% thay bậc lịch sử, lấy mẫu5 phút và chưa có orderbook. Dữ liệu đầy đủ hơn không đồng nghĩa mô phỏng thanh lý chính xác hoặc lợi nhuận tương lai được xác nhận. Cấu hình live giữ nguyên.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">24 kết quả</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc đánh giá đã khóa</a> · <a href="../reconciled_manifest.json">Dữ liệu sau đối soát</a> · <a href="../manifest.json">Báo cáo thiếu ban đầu</a></p></section></main>
<script>const data=__JSON__,num=x=>x===null?'Không hoàn tất':x.toFixed(2),date=t=>new Date(t).toISOString().slice(0,10),cost=c=>c==='base'?'Cơ sở':'Cao';
function render(){const rows=data.filter(r=>r.strategy_id===document.querySelector('#strategy').value&&r.window===document.querySelector('#window').value),months=rows[0].monthly.months,start=months[0].start,end=months[months.length-1].end,values=rows.flatMap(r=>r.points.map(p=>p[1]));let lo=Math.floor(Math.min(500,...values)/25)*25-5,hi=Math.ceil(Math.max(500,...values)/25)*25+5;const x=t=>62+(t-start)/(end-start)*1110,y=v=>280-(v-lo)/(hi-lo)*250;let svg='';
for(let i=0;i<=5;i++){let v=lo+(hi-lo)*i/5;svg+=`<path d="M62 ${y(v)}H1172" stroke="#2a3a51"/><text x="52" y="${y(v)+4}" text-anchor="end" fill="#a7b6cc" font-size="12">${v.toFixed(0)}</text>`}svg+=`<path d="M62 ${y(500)}H1172" stroke="#96a5ba" stroke-dasharray="5 6"/>`;
for(let t of [...months.map(m=>m.start),end])svg+=`<text x="${x(t)}" y="310" text-anchor="middle" fill="#a7b6cc" font-size="12">${date(t).slice(2,7)}</text>`;
for(const r of rows){let d=r.points.map((p,i)=>(i?'L':'M')+x(p[0]).toFixed(2)+' '+y(p[1]).toFixed(2)).join('');svg+=`<path d="${d}" fill="none" stroke="${r.cost==='base'?'#62d6c2':'#e6afed'}" stroke-width="1.7" ${r.cost==='stress'?'stroke-dasharray="5 3"':''}/>`}document.querySelector('#chart').innerHTML=svg;
document.querySelector('#chartStatus').innerHTML=rows.map(r=>`${cost(r.cost)}: cuối ${num(r.ending_equity)} USDT · lãi/lỗ riêng 06–08/2026 ${num(r.new_period_pnl)} · DD toàn đường ${num(r.max_drawdown*100)}% · ${r.entries} vị thế đã vào · ${r.open_count} còn mở${r.paused?' · đã khóa mở mới':''}`).join('<br>');
document.querySelector('#monthHead').innerHTML='<tr><th>Chi phí</th>'+months.map(m=>'<th>'+date(m.start).slice(0,7)+'</th>').join('')+'</tr>';
document.querySelector('#monthBody').innerHTML=rows.map(r=>'<tr><td>'+cost(r.cost)+'</td>'+r.monthly.months.map(m=>`<td class="${m.return_fraction<0?'bad':'good'}">${num(m.return_fraction*100)}%</td>`).join('')+'</tr>').join('');}
document.querySelector('#strategy').addEventListener('change',render);document.querySelector('#window').addEventListener('change',render);render();</script></body></html>'''
    options="".join(f'<option value="{p["id"]}"'+(' selected' if p["id"]=="mask02_n25" else '')+'>'+escape(NAMES[p["guard"]["mask"]]+f" · ký quỹ {p['notional']/5:g} USDT")+'</option>' for p in s["protocol"]["candidate"]["specs"])
    for k,v in dict(STYLE=style,FRESH="".join(fresh),CARRY="".join(carry),OPTIONS=options,JSON=json.dumps(series,ensure_ascii=False,separators=(",",":"),allow_nan=False).replace("</","<\\/")).items():html=html.replace("__"+k+"__",v)
    (RESULTS/"dashboard.html").write_text(html,encoding="utf-8")
    md=["# Ứng viên đã khóa trên giai đoạn06–08/2026 — lượt09","",
        "0/24 đường đạt50% trong từng tháng mới. Bộ lọc6h vẫn lời nhẹ nhưng kém đối chứng không lọc ở cả hai quy mô và mức chi phí; bộ4điều kiện lỗ. Không chỉnh lại ngưỡng sau khi xem kết quả này.","",
        "| Cấu hình | Cuối kỳ cơ sở | Cuối kỳ cao | DD lớn nhất | Vị thế đã vào | Còn mở |","|---|---:|---:|---:|---:|---:|",*mdrows,"",
        "Ứng viên ký quỹ5USDT, tài khoản mới500: tháng6 +2,64–3,02%, tháng7 −0,23 đến+0,03%, tháng8 −1,60 đến−1,57%; cuối kỳ503,80–507,15. Cả21 vị thế đã vào, năm còn mở, lâu nhất66,8ngày. So với không lọc, tài sản cuối thấp hơn và DD cao hơn.","",
        "Nếu tiếp tục tài khoản từ09/2025, ký quỹ5USDT: cuối12tháng544,35–552,69; riêng06–08chỉ thêm3,11–5,55. Còn5vị thế, lâu nhất219ngày. Không đồng nhất lợi nhuận12tháng với lợi nhuận3tháng mới.","",
        "Dữ liệu:273ZIP checksum;821.376nến giao dịch (31mã gồmBTC),794.880nến Mark (30coin),11.580funding.214.272nến thiếu cục bộ được thay bằng dữ liệu công khai thực; giá chung hai nguồn khớp.8.640nến Mark thiếu trong archive ngày29/6 được bổ sung từREST, kiểm tra nến giáp ranh. Giữmanifestthiếu ban đầu, không nội suy.","",
        f"{audit['unit_tests_passed']} kiểm thử;{audit['journals_audited']} sổ đối soát;{audit['old_account_prefixes_exact']} đường cũ khớp chính xác trước tháng6;{audit['new_paths_exact']} đường mới tái lập. Hashứng viên và cấu hìnhlive giữ nguyên.","",
        s["protocol"]["limitations"],"",
        "[Dashboard](dashboard.html) · [24 kết quả](comparison.csv) · [Đối soát](verification.json) · [Dữ liệu](../reconciled_manifest.json)"]
    (RESULTS/"report.md").write_text("\n".join(md),encoding="utf-8")
    write(RESULTS/"goal_progress.json",dict(classification="progress",goal_status="active",achieved=False,runs=24,target_passes=0,
        evidence="Frozenret6 candidate profitable but underperforms nofilter in laterJun-Aug atbothsizes/costs. Fullguard loses. Carryinventory extends to219days. Verified273archives and restored8640actualMarkbars without syntheticfill.",
        next_steps=["Reassess whether ret6 guard improves regime-specific risk rather than stable edge; do not retune on this evaluation window and claim independent validation.",
                    "Investigate inventory turnover and event frequency on combinedyear under predeclared policies; retain costs and adverse regimes.",
                    "Seek different economically motivated signal/exit mechanism if required monthly growth remains unsupported."],live_config_unchanged=True))
    print(RESULTS/"dashboard.html")


if __name__=="__main__":main()
