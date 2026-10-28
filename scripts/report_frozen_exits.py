"""Publish the exit sensitivity grid without reselecting on later results."""

import json
from html import escape

import pandas as pd
from compare_account_risk import ROOT, write
from search_frozen_exits import OUT


def num(x):
    return "Không hoàn tất" if x is None else f"{x:.2f}"


def name(spec):
    e = spec["exit"]
    exit_name = (f"Trailing {e['activation_atr']:g} ATR / hồi {e['callback_fraction']*100:g}%"
                 if e["trailing"] else f"TP {e['fixed_tp_usdt']:g} USDT")
    return f"{'Lọc 6h' if spec['mask'] else 'Không lọc'} · ký quỹ {spec['notional']/5:g} · {exit_name}"


def table_row(values):
    return "<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in values) + "</tr>"


def main():
    s = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    audit = json.loads((OUT / "verification.json").read_text(encoding="utf-8"))
    assert audit["journals_audited"] == len(s["results"]) == 384
    assert s["target_met_rows"] == 0
    by_key = {(r["strategy_id"], r["window"], r["cost"]): r for r in s["results"]}
    specs = {p["id"]: p for p in s["specs"]}
    selected_rows, mdrows, early_rows, series = [], [], [], []
    for ident in s["selected"]:
        spec = specs[ident]
        baseline = f"mask{spec['mask']:02d}_n{spec['notional']}_trail_a3_c1"
        rows = [by_key[(ident, "later", c)] for c in ["base", "stress"]]
        old = [by_key[(baseline, "later", c)] for c in ["base", "stress"]]
        annual = [by_key[(ident, "year", c)] for c in ["base", "stress"]]
        pair = lambda rs, key: " / ".join(num(r[key]) for r in rs)
        fields = [name(spec), pair(rows, "ending_equity"), pair(old, "ending_equity"),
                  pair(annual, "ending_equity"), " / ".join(str(r["entries"]) for r in rows),
                  f"{max(r['max_drawdown'] for r in annual)*100:.2f}%"]
        selected_rows.append(table_row(fields)); mdrows.append("| " + " | ".join(fields) + " |")
    for exit_id in ["trail_a0.5_c0.25", "trail_a1_c0.5", "trail_a3_c1", "tp0.5"]:
        ident = f"mask02_n25_{exit_id}"
        rs = [by_key[(ident, "year", c)] for c in ["base", "stress"]]
        early_rows.append(table_row([name(specs[ident]),
            " / ".join(num(r["ending_equity"]) for r in rs),
            " / ".join(str(r["entries"]) for r in rs),
            " / ".join(num(r["exit_diagnostics"]["closed_net"]) for r in rs),
            " / ".join(str(r["exit_diagnostics"]["negative_trailing_exits"]) for r in rs) if rs[0]["exit"]["trailing"] else "—",
            " / ".join(num(r["exit_diagnostics"]["mean_closed_filled_parts"]) for r in rs) if rs[0]["exit"]["trailing"] else "—"]))
    for r in s["results"]:
        f = pd.read_parquet(OUT / "runs" / f"{r['id']}_equity.parquet")
        ix = {0, len(f)-1}
        for _, g in f.groupby((f["at"]-f["at"].iloc[0])//86400000):
            ix.update([g.index[0], g.index[-1], g.equity.idxmin(), g.equity.idxmax()])
        series.append(dict(r, points=[[int(v["at"]), round(v.equity, 6)] for _, v in f.loc[sorted(ix)].iterrows()]))
    write(OUT / "dashboard_data.json", series)
    style = (ROOT / "artifacts/frozen_extension_20260925/evaluation/dashboard.html").read_text(encoding="utf-8").split("<style>",1)[1].split("</style>",1)[0]
    html = r'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Đo TP và trailing</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / NGHIÊN CỨU NGOẠI TUYẾN · LƯỢT 10</div><h1>Chốt nhanh hơn, nhiều lệnh hơn — lợi nhuận chưa tốt hơn</h1>
<p class="muted">01/09/2025–01/09/2026, UTC, không gồm ngày cuối · 500 USDT · Cross x5 · tối đa 5 vị thế · tổng ba phần 25 hoặc 100 USDT danh nghĩa</p>
<div class="notice"><b>0/384 đường tài khoản đạt 50% trong từng tháng.</b><p>Hạ trailing tăng vòng quay nhưng giảm số tiền kiếm được mỗi lần đóng. Với bộ lọc 6h và ký quỹ 5 USDT, trailing 0,5 ATR / hồi 0,25% vào 220–236 vị thế, cuối năm còn 510,68–520,10 USDT; trailing 3 ATR / hồi 1% vào 68–69 vị thế nhưng đạt 544,35–552,69 USDT. Đây là so sánh lịch sử đã dùng nhiều lần, chưa xác nhận hiệu quả tương lai.</p></div>
<div class="cards"><div class="card">Cấu hình<strong>64</strong></div><div class="card">Đường tài khoản<strong>384</strong></div><div class="card">Tái lập đối chứng<strong>24</strong></div><div class="card">Kiểm thử liên quan<strong>56</strong></div></div>
<section class="panel"><h2>Bốn cấu hình khóa bằng giai đoạn đầu</h2><p>Chọn riêng trong từng bộ lọc/quy mô trên 09/2025–05/2026: tối đa hóa tháng tệ nhất ở cả hai mức chi phí; dùng tài sản cuối để phân hạng khi bằng nhau. Sau đó mới chạy kỳ 06–08/2026 trong lượt này. Kỳ sau đã từng được xem ở lượt trước nên không gọi là tập kiểm tra độc lập. Các cặp số: cơ sở / chi phí cao.</p>
<div class="scroll"><table><thead><tr><th>Cấu hình khóa</th><th>3 tháng sau · từ 500</th><th>Trailing cũ cùng điều kiện · 3 tháng</th><th>Cả năm · từ 500</th><th>Vị thế vào · 3 tháng</th><th>DD cả năm lớn nhất</th></tr></thead><tbody>__SELECTED__</tbody></table></div>
<p>Hai cấu hình TP cố định được chọn vẫn lỗ ở tài khoản mới ba tháng. TP 0,5 USDT, ký quỹ 20 USDT, vào 72–75 vị thế nhưng tài sản còn 490,38–491,42 USDT. Trailing hồi 0,5% của bản không lọc cải thiện nhẹ kỳ sau, nhưng DD cả năm tới 34%; khóa mở mới 20% không dừng lỗ từ vị thế cũ.</p></section>
<section class="panel"><h2>Đo riêng tốc độ chốt · ký quỹ 5 USDT, lọc 6h</h2><p>Cả năm, cùng nguồn tín hiệu và danh sách coin. Lợi nhuận đã chốt chưa bao gồm phần vị thế còn mở; cột tài sản cuối đã tính chúng.</p><div class="scroll"><table><thead><tr><th>Cách thoát</th><th>Tài sản cuối</th><th>Vị thế đã vào</th><th>Lãi/lỗ đã chốt</th><th>Trailing đóng lỗ</th><th>Số phần đã vào TB khi trailing đóng</th></tr></thead><tbody>__EARLY__</tbody></table></div><p>Kích hoạt ở 0,5 ATR hủy phần vào tiếp theo theo quy tắc hiện có: trung bình chỉ vào một phần. Vì vậy đây là thay đổi cả thời điểm thoát lẫn khối lượng thực tế. Trailing có thể đóng lỗ sau phí, funding và trượt giá.</p></section>
<section class="panel"><h2>Xem toàn bộ cấu hình và từng tháng</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Giai đoạn<select id="window"><option value="year">Cả năm · 09/2025–08/2026</option><option value="later">Tài khoản mới · 06–08/2026</option><option value="development">Chọn tham số · 09/2025–05/2026</option></select></label></div>
<div class="legend"><span><i style="background:#62d6c2"></i>Chi phí cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản gồm vị thế mở theo thời gian"></svg><div id="chartStatus">Đang tải dữ liệu…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><p class="muted">Biểu đồ giữ đầu, cuối, đáy và đỉnh mỗi ngày. Mỗi giai đoạn khởi chạy riêng từ 500; cả năm giữ vị thế xuyên suốt. Không đặt lại đỉnh tài sản theo tháng.</p></section>
<section class="panel"><h2>Quy tắc và giới hạn đo lường</h2><p>12 trailing: kích hoạt 0,5 / 1 / 2 / 3 ATR, hồi 0,25 / 0,5 / 1%. Bốn TP tiền: 0,5 / 1 / 2 / 5 USDT. Hai bộ lọc: không lọc và lợi suất 6h ≤0. Tín hiệu là đảo chiều sau tăng quá mức trên nến 4h đã đóng; khoảng vào thêm 0,5 ATR thuận xu hướng, hết hạn 6 giờ. Không SL, không đóng theo thời gian, không loại coin đột biến.</p><p>TP tiền tính cho đủ ba phần và giảm theo phần đã khớp: TP 0,5 USDT có thể chỉ còn khoảng 0,167 USDT khi vào một phần. TP cố định bỏ qua điều kiện mục tiêu ATR tối thiểu nên có thể nhận tín hiệu khác. Mô hình LIMIT khớp khi giá đóng nến vượt mục tiêu, chưa mô phỏng hàng chờ/khớp từng phần; trailing khớp ở giá mở nến kế tiếp cộng trượt giá. Không coi hai cách thoát có độ chính xác thực thi tương đương.</p><p>Phí mỗi lần khớp: cơ sở 0,05%, cao 0,10%. Trượt giá thị trường: 0,20% và 0,50%. Funding thực và vị thế mở được tính. Vị thế ký quỹ 20 USDT chỉ là giả thuyết nghiên cứu; cấu hình tài khoản thật không thay đổi.</p><p>384 sổ đã đối soát, 16 đường đối chứng khớp đầy đủ và 8 đường khớp trước ranh giới dữ liệu; 8 đường cấu hình khóa chạy lại khớp chính xác. 56 kiểm thử liên quan đạt. Dữ liệu giá/funding và mã nguồn khớp hash; lỗ chưa chốt không bị bỏ ra ngoài kết quả.</p><p class="muted">Còn giới hạn: maintenance margin dùng proxy 1% thay bậc lịch sử, lấy mẫu 5 phút, bộ lọc sàn hiện tại, kho có thể thiếu coin hủy niêm yết, chưa có orderbook, nhiều lần tìm tham số trên cùng lịch sử. Chưa đủ bằng chứng chuyển sang tiền thật.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">384 kết quả</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc nghiên cứu</a> · <a href="candidate_lock.json">Bản khóa lựa chọn</a></p></section></main>
<script>
let data=[];const num=x=>x===null||x===undefined?'—':x.toFixed(2),date=t=>new Date(t).toISOString().slice(0,10),cost=c=>c==='base'?'Cơ sở':'Cao';
function render(){if(!data.length)return;const rows=data.filter(r=>r.strategy_id===document.querySelector('#strategy').value&&r.window===document.querySelector('#window').value),months=rows[0].monthly.months,start=months[0].start,end=months.at(-1).end,values=rows.flatMap(r=>r.points.map(p=>p[1]));let lo=Math.floor(Math.min(500,...values)/25)*25-5,hi=Math.ceil(Math.max(500,...values)/25)*25+5;const x=t=>62+(t-start)/(end-start)*1110,y=v=>280-(v-lo)/(hi-lo)*250;let svg='';
for(let i=0;i<=5;i++){let v=lo+(hi-lo)*i/5;svg+=`<path d="M62 ${y(v)}H1172" stroke="#2a3a51"/><text x="52" y="${y(v)+4}" text-anchor="end" fill="#a7b6cc" font-size="12">${v.toFixed(0)}</text>`}svg+=`<path d="M62 ${y(500)}H1172" stroke="#96a5ba" stroke-dasharray="5 6"/>`;
for(let t of [...months.map(m=>m.start),end])svg+=`<text x="${x(t)}" y="310" text-anchor="middle" fill="#a7b6cc" font-size="12">${date(t).slice(2,7)}</text>`;
for(const r of rows){let d=r.points.map((p,i)=>(i?'L':'M')+x(p[0]).toFixed(2)+' '+y(p[1]).toFixed(2)).join('');svg+=`<path d="${d}" fill="none" stroke="${r.cost==='base'?'#62d6c2':'#e6afed'}" stroke-width="1.7" ${r.cost==='stress'?'stroke-dasharray="5 3"':''}/>`}document.querySelector('#chart').innerHTML=svg;
document.querySelector('#chartStatus').innerHTML=rows.map(r=>`${cost(r.cost)}: cuối ${num(r.ending_equity)} USDT · DD ${num(r.max_drawdown*100)}% · ${r.entries} vị thế đã vào · ${r.open_count} còn mở · tuổi mở lớn nhất ${r.utilization.open_hold_max_days===null?'không còn vị thế':num(r.utilization.open_hold_max_days)+' ngày'}${r.paused?' · khóa mở mới':''}`).join('<br>');
document.querySelector('#monthHead').innerHTML='<tr><th>Chi phí</th>'+months.map(m=>'<th>'+date(m.start).slice(0,7)+'</th>').join('')+'</tr>';
document.querySelector('#monthBody').innerHTML=rows.map(r=>'<tr><td>'+cost(r.cost)+'</td>'+r.monthly.months.map(m=>`<td class="${m.return_fraction<0?'bad':'good'}">${m.return_fraction===null?'Thiếu dữ liệu':num(m.return_fraction*100)+'%'}</td>`).join('')+'</tr>').join('');}
document.querySelector('#strategy').addEventListener('change',render);document.querySelector('#window').addEventListener('change',render);fetch('dashboard_data.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{data=d;render()}).catch(e=>document.querySelector('#chartStatus').textContent='Không tải được dữ liệu: '+e.message);
</script></body></html>'''
    options = "".join(f'<option value="{p["id"]}"'+(' selected' if p["id"]=="mask02_n25_trail_a3_c1" else '')+'>'+escape(name(p))+(' · đã khóa' if p['id'] in s['selected'] else '')+'</option>' for p in s['specs'])
    for k,v in dict(STYLE=style, SELECTED="".join(selected_rows), EARLY="".join(early_rows), OPTIONS=options).items():
        html=html.replace("__"+k+"__",v)
    (OUT/"dashboard.html").write_text(html,encoding="utf-8")
    md = ["# Đo TP và trailing trên lịch sử một năm — lượt 10", "",
        "64 cấu hình × 3 giai đoạn × 2 mức chi phí = 384 đường; không đường nào đạt 50% từng tháng. Không đổi cấu hình live.", "",
        "| Cấu hình khóa | 3 tháng sau | Đối chứng cũ 3 tháng | Cả năm | Số vị thế 3 tháng | DD cả năm |",
        "|---|---:|---:|---:|---:|---:|", *mdrows, "",
        "Các cặp số là cơ sở / chi phí cao. Chọn trên 09/2025–05/2026 theo tháng tệ nhất; 06–08/2026 đã từng được xem, không phải kiểm tra độc lập. Mỗi cửa sổ bắt đầu từ 500 USDT, tối đa 5 vị thế; cả năm giữ nguyên tài khoản xuyên suốt.", "",
        "Ký quỹ 5 USDT và lọc 6h: trailing 0,5 ATR/hồi 0,25% tăng số vị thế lên 220–236 nhưng chỉ đạt 510,68–520,10. Trailing 3 ATR/hồi 1% đạt 544,35–552,69 với 68–69 vị thế. Kích hoạt sớm hủy phần chưa vào, trung bình chỉ một phần; tăng lượt giao dịch không đồng nghĩa tăng lợi nhuận.", "",
        "TP 0,5 USDT và ký quỹ 20 USDT: 72–75 vị thế trong kỳ sau, tài sản còn 490,38–491,42 dù lãi đã chốt khoảng 11,55–12,05. Lỗ vị thế mở xóa phần lãi đã chốt. TP là mục tiêu toàn bộ ba phần, giảm theo lượng thực khớp.", "",
        "LIMIT giả định khớp khi giá đóng nến qua mục tiêu, chưa xét hàng chờ/khớp từng phần; trailing dùng mở nến sau cộng trượt giá. Fixed TP bỏ qua điều kiện mục tiêu ATR tối thiểu, nên số tín hiệu hợp lệ có thể khác. Không gọi đây là bằng chứng thực thi tương đương.", "",
        "384 sổ đối soát; 16 đối chứng khớp đầy đủ, 8 prefix khớp; 8 đường khóa tái lập; 56 kiểm thử liên quan đạt. Không xóa coin đột biến hoặc lỗ đang mở.", "",
        "Giới hạn: maintenance proxy 1%, lấy mẫu 5 phút, bộ lọc sàn hiện tại, nguy cơ thiếu coin hủy niêm yết trong kho, không orderbook, nghiên cứu lặp lịch sử. Không đủ điều kiện xác nhận lợi thế tương lai.", "",
        "[Dashboard](dashboard.html) · [384 kết quả](comparison.csv) · [Đối soát](verification.json)"]
    (OUT/"report.md").write_text("\n".join(md),encoding="utf-8")
    write(OUT/"goal_progress.json",dict(classification="progress",goal_status="active",achieved=False,runs=384,target_passes=0,
        evidence="Early trailing raises turnover but lowers marked net outcome for 5USDT margin ret6 strategy; selected fixedTP loses in later fresh window despite positive realized gains. 384 journals audited; 24 baselines and8 selected full paths reproduced.",
        next_steps=["Test whether staged additions should wait for confirmation after trailing activation, with a fixed total budget and comparable exits.",
                    "Investigate new entry mechanisms using registered rules and untouched future observation; repeated historical parameter search is not independent validation."],
        live_config_unchanged=True))
    print(OUT/"dashboard.html")


if __name__=="__main__":
    main()
