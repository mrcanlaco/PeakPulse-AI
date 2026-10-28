"""Dashboard separating entry-timing selection, controls and final evaluation."""

import json
from html import escape

import pandas as pd
from plotly.offline import get_plotlyjs
from search_short_entries import OUT, PRIOR
from short_entry_timing import definitions


def main():
    s = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    verification = json.loads((OUT / "verification.json").read_text(encoding="utf-8"))
    pairs = json.loads((OUT / "paired_entry_prices.json").read_text(encoding="utf-8"))
    audits = json.loads((OUT / "entry_watches.json").read_text(encoding="utf-8"))
    development = json.loads(
        (OUT / "development_summary.json").read_text(encoding="utf-8")
    )
    primary = next(f for f in s["finalists"] if f["primary"])
    rows = [r for r in s["results"] if r["window"] != "development"] + s[
        "no_stop_results"
    ]
    specs = [
        f["spec"]
        for f in sorted(
            s["finalists"], key=lambda f: (not f["primary"], f["strategy_id"])
        )
    ] + s["no_stop_specs"]

    def matched(sid, window):
        return [r for r in rows if r["strategy_id"] == sid and r["window"] == window]

    def span(rr, key="ending_equity"):
        vals = [r[key] for r in rr]
        return (
            f"{min(vals):.2f}–{max(vals):.2f}"
            if vals and all(v is not None for v in vals)
            else "Chưa xác định"
        )

    ids = [
        "weak_rank_immediate_fixed",
        "weak_rank_delay15_fixed",
        "weak_rank_delay180_fixed",
        "weak_rank_immediate_trailing",
        "weak_rank_delay180_trailing",
    ]
    labels = [
        "Vào ngay + TP cố định",
        "Chờ 15 phút + TP cố định (ứng viên thay thế đã khóa)",
        "Chờ 3 giờ + TP cố định",
        "Vào ngay + trailing",
        "Chờ 3 giờ + trailing",
    ]
    comparison, md_rows = [], []
    for sid, label in zip(ids, labels):
        vals = [span(matched(sid, w)) for w in ["validation", "holdout", "full"]]
        dd = max(r["max_drawdown"] for r in matched(sid, "full")) * 100
        comparison.append(
            f"<tr><td>{escape(label)}</td>{''.join('<td>' + v + '</td>' for v in vals)}<td>{dd:.2f}%</td></tr>"
        )
        md_rows.append(f"| {label} | {' | '.join(vals)} | {dd:.2f}% |")
    no_stop = []
    for spec in s["no_stop_specs"]:
        full = matched(spec["id"], "full")
        no_stop.append(
            f"<tr><td>{escape(spec['timing']['label'])} · {spec['cap']} vị thế</td><td>{span(full)}</td><td>{span(matched(spec['id'], 'holdout'))}</td><td>{max(r['max_drawdown'] for r in full) * 100:.2f}%</td><td>{max(r['max_hold_days'] for r in full):.1f} ngày</td></tr>"
        )
    curves = {}
    for row in rows:
        if row["window"] != "full":
            continue
        frame = pd.read_parquet(OUT / "runs" / f"{row['id']}_equity.parquet")
        grouped = frame.groupby(frame["at"] // 3600000)
        indices = sorted(
            set(grouped.equity.idxmin())
            | set(grouped.equity.idxmax())
            | {0, len(frame) - 1}
        )
        frame = frame.loc[indices]
        curves[row["id"]] = dict(x=frame["at"].tolist(), y=frame.equity.tolist())
    payload = json.dumps(
        dict(
            rows=rows,
            specs=specs,
            all_specs=s["protocol"]["variants"],
            primary=s["primary"],
            finalists=s["finalists"],
            development=development,
            timings=definitions(),
            audits=audits,
            curves=curves,
        ),
        ensure_ascii=False,
        allow_nan=False,
    ).replace("</", "<\\/")
    old_html = (PRIOR / "dashboard.html").read_text(encoding="utf-8")
    style = old_html.split("<style>", 1)[1].split("</style>", 1)[0]
    html = """<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Thử điểm vào</title><style>__STYLE__</style>
<h1>Thử điểm vào: vào ngay hay chờ thêm?</h1><p>24/06–24/09/2026 UTC · 500 USDT · Cross x5 · Tổng ký quỹ 5 USDT chia ba · Nghiên cứu, chưa bật live</p>
<div class="notice"><b>Chưa có điểm vào mới tốt hơn một cách ổn định.</b><p>Trong các phương án thay thế, chờ 15 phút + TP cố định được chọn trước khi xem tháng cuối. Tài sản toàn kỳ: <b>__FULL__ USDT</b>; tháng cuối: <b>__HOLD__ USDT</b>. Đối chứng vào ngay vẫn tốt hơn. Chờ 3 giờ + trailing lãi trong tháng cuối nhưng tháng xác nhận vẫn có trường hợp lỗ; chưa thể gọi là chiến lược tốt nhất.</p></div>
<div class="cards"><div class="card">Cách chọn điểm vào<strong>13</strong></div><div class="card">Cấu hình chính<strong>104</strong></div><div class="card">Lượt mô phỏng, gồm không SL<strong>716</strong></div><div class="card">Đạt tiêu chí chính<strong>0</strong></div></div>
<section class="panel"><h2>So sánh trên cùng nhóm tín hiệu coin yếu</h2><p>Cùng tổng danh nghĩa 25 USDT chia ba, tối đa một vị thế; có SL theo tỷ lệ đã vào (1 USDT khi đủ ba phần), thời hạn 48 giờ. Mỗi tháng được đánh giá riêng từ 500 USDT; toàn kỳ chạy liên tục và định giá cả vị thế còn mở. Khoảng số phản ánh giả định chi phí và quan sát, không phải khoảng tin cậy.</p><div class="scroll"><table><thead><tr><th>Điểm vào / cách thoát</th><th>24/07–24/08</th><th>24/08–24/09</th><th>Toàn kỳ</th><th>DD toàn kỳ cao nhất</th></tr></thead><tbody>__COMPARE__</tbody></table></div><p>Chờ 3 giờ không đồng nghĩa luôn có giá Short tốt hơn. Chờ 15 phút cho giá vào đầu thấp hơn đối chứng trung bình khoảng 0,22–0,27% trên 79–84 sự kiện thực vào ở cả hai bản. Chỉ 30–31 sự kiện trong số đó có giá Short cao hơn. Đây là so sánh giá trên tập giao nhau, không phải ước lượng lợi nhuận nhân quả; các sự kiện chỉ khớp ở một bản được lưu riêng.</p></section>
<section class="panel"><h2>13 quy tắc đã thử</h2><ul><li>Vào ngay; hoặc chờ cố định 15, 60, 180 phút.</li><li>Chờ hồi lên 0,25 / 0,5 / 1 ATR từ giá khi có tín hiệu rồi vào Short.</li><li>Chờ giảm tiếp 0,25 / 0,5 / 1 ATR để xác nhận đà giảm.</li><li>Chờ hồi lên 0,25 / 0,5 / 1 ATR, sau đó giảm lại ít nhất 0,25 ATR từ đỉnh quan sát; phải có một nến đã đóng trước đó để xác nhận nhịp hồi.</li></ul><p>Giá tham chiếu là giá đóng nến khi phát tín hiệu; ATR và điểm xếp hạng giữ nguyên từ lúc đó. Chờ tối đa 6 giờ, không đủ điều kiện thì bỏ qua. Quy tắc kiểm tra giá đóng mỗi 5 phút, khớp ở giá mở nến kế tiếp cộng trượt giá; không giả định mua/bán đúng đỉnh đáy trong nến. Các mục chờ là điều kiện theo dõi nội bộ, chưa phải lệnh đặt trên sàn, nên chưa giữ chỗ; khi kích hoạt mới kiểm tra vốn và số vị thế. Nếu hết chỗ thì bỏ, không thử lại tín hiệu đó.</p><p>Sau phần đầu, hai phần còn lại giữ nguyên quy tắc giảm thêm 0,5 và 1 ATR từ lần khớp đầu; không thêm khi giá quan sát cao hơn giá vốn bình quân. Giữ nguyên TP gốc hoặc trailing bật sau 3 ATR/hồi 1%, không tối ưu lại cách thoát trong lượt tìm điểm vào này.</p></section>
<section class="panel"><h2>Không giấu tín hiệu không vào được</h2><label>Nhóm tín hiệu <select id="family"><option value="weak_rank">Coin yếu hơn nhóm</option><option value="breakdown">Phá đáy trong xu hướng giảm</option><option value="pullback">Hồi lên rồi giảm lại</option><option value="failed_pump">Nhịp tăng thất bại</option></select></label><label>Cách thoát <select id="exit"><option value="fixed">TP cố định</option><option value="trailing">Trailing</option></select></label><div class="scroll"><table><thead><tr><th>Quy tắc vào</th><th>Đủ điều kiện / tín hiệu toàn kỳ</th><th>Hết hạn / còn chờ cuối kỳ</th><th>PnL tháng phát triển (USDT)</th><th>Tài sản tháng xác nhận</th><th>Tài sản tháng cuối</th></tr></thead><tbody id="timings"></tbody></table></div><p>Đủ điều kiện theo giá chưa đồng nghĩa tài khoản đã mở được vị thế: vẫn có thể bị chặn bởi số vị thế, vốn, bước khối lượng hoặc mục tiêu quá nhỏ. “Không vào vòng sau” nghĩa là cấu hình không được chọn từ tháng phát triển; không chạy lại toàn bộ lịch sử để chọn kết quả đẹp nhất.</p></section>
<section class="panel"><h2>Kết quả từng cấu hình được giữ lại</h2><label>Phương án <select id="strategy"></select></label><p id="rules"></p><div id="chart"></div><p class="foot">Đường tài sản toàn kỳ, giữ cực trị theo giờ. Chi phí cơ sở: phí 0,05%/chiều, trượt giá 0,20%; trường hợp cao: 0,10% và 0,50%. Trailing quan sát mỗi 5/15 phút; bản TP cố định có đường trùng nhau.</p><label>Kỳ số liệu <select id="period"><option value="full">Toàn kỳ</option><option value="validation">Tháng xác nhận</option><option value="holdout">Tháng cuối</option></select></label><div class="scroll"><table><thead><tr><th>Quan sát / chi phí</th><th>Tài sản</th><th>DD</th><th>Mở / đóng / còn</th><th>Thêm phần</th><th>Danh nghĩa TB/vị thế</th><th>Phí / funding</th><th>Giữ lâu nhất</th></tr></thead><tbody id="detail"></tbody></table></div><p id="watch"></p><div id="reasons"></div><h3>Khoảng ước lượng 95% PnL/ngày tháng cuối</h3><div id="confidence"></div><p class="foot">Bootstrap theo cụm 7 ngày, 10.000 lần. Khoảng thăm dò chưa hiệu chỉnh việc thử nhiều phương án; không phải bảo đảm lợi nhuận.</p></section>
<section class="panel"><h2>Bỏ SL và thời hạn: chờ 15 phút so với vào ngay</h2><p>Giữ cùng tín hiệu, chia ba phần, TP cố định của ứng viên. Đây là đối chiếu bổ sung sau lựa chọn, không dùng để chọn lại chiến lược. Có tài khoản giảm ít hơn đối chứng nhưng vẫn lỗ; giá trị cuối kỳ bao gồm các lệnh chưa đóng.</p><div class="scroll"><table><thead><tr><th>Điểm vào / giới hạn</th><th>Tài sản toàn kỳ</th><th>Tài sản tháng cuối</th><th>DD toàn kỳ cao nhất</th><th>Giữ lâu nhất</th></tr></thead><tbody>__NOSTOP__</tbody></table></div><p>Dừng mở mới khi giảm 20% từ đỉnh vẫn giữ nguyên các vị thế cũ. Kết quả nhạy với chi phí vì phí/trượt giá làm thay đổi thời điểm đóng, phần được thêm và tín hiệu được nhận sau đó; “chi phí cao” không nhất thiết cho số dư thấp hơn ở mọi đường mô phỏng.</p></section>
<section class="panel"><h2>Cách chọn và giới hạn</h2><p>104 cấu hình = bốn nhóm tín hiệu × 13 điểm vào × hai cách thoát. 416 lượt tháng phát triển; chọn tối đa hai ứng viên khác “vào ngay” mỗi nhóm/cách thoát, yêu cầu đủ bốn trường hợp, DD dưới 20%, ít nhất 20 vị thế đóng. Thực tế 13 ứng viên qua vòng phát triển và tám đối chứng vào ngay được giữ lại. Khóa trước tháng xác nhận; chọn ứng viên thay thế theo PnL thấp nhất trong bốn giả định và cùng điều kiện mẫu/DD, rồi khóa trước tháng cuối. Đối chứng vẫn tốt hơn ứng viên thay thế; không vì tên “ứng viên chính” mà tự động thay chiến lược.</p><p>668 lượt chính và 48 lượt bỏ SL/thời hạn. Đạt tiêu chí nếu cả tháng xác nhận, tháng cuối và toàn kỳ đều lãi/DD dưới 20% ở mọi giả định, mỗi tháng ít nhất 20 vị thế đóng. Không có cấu hình đạt. Chờ 3 giờ + trailing được nêu như kết quả thăm dò, chưa có bằng chứng đủ ổn định.</p><p>Cùng 30 coin theo thanh khoản trước kỳ, không loại coin theo kết quả thua. AKE không nằm trong tập top 30 này. Danh sách hợp đồng và bước khối lượng hiện tại còn thiên lệch sống sót; thiếu lịch sử sổ lệnh và bậc maintenance margin chính xác (mô phỏng dùng 1%). Trailing chỉ quan sát giá đóng theo nhịp, chưa tương đương trailing liên tục Binance. Funding/Mark Price giữ nguyên bộ dữ liệu đã kiểm chứng. Hạn chế ATR và bộ lọc không được cập nhật trong thời gian chờ là một phần của quy tắc đang thử.</p><p>Các tháng này đã được xem trước ở nhiều lượt nghiên cứu; không coi là dữ liệu ngoài mẫu hoàn toàn mới. 79 kiểm thử đạt; tái lập 208 bộ theo dõi tín hiệu và kiểm tra cắt bỏ dữ liệu tương lai không đổi quyết định trước đó; đối soát 300 sổ kết quả, tái lập chính xác bốn đường tài sản ứng viên và 92 trường hợp đối chứng. Cấu hình thật không đổi.</p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">Kết quả chi tiết</a> · <a href="paired_entry_prices.json">So sánh giá vào cùng sự kiện</a> · <a href="entry_watches.json">Tín hiệu chờ/hết hạn</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc đã khóa</a></section>
<script>__PLOTLY__</script><script>
const D=__DATA__,el=id=>document.getElementById(id),f=x=>x===null||x===undefined?'—':x.toLocaleString('vi-VN',{minimumFractionDigits:2,maximumFractionDigits:2}),cn=r=>r.observation_minutes+' phút / '+(r.cost==='base'?'cơ sở':'cao'),range=(x,equity=true)=>x&&x.complete?f((equity?500:0)+x.worst_pnl)+'–'+f((equity?500:0)+x.best_pnl):'Không vào vòng sau';
el('strategy').innerHTML=D.specs.map(s=>`<option value="${s.id}">${s.id===D.primary?'Ứng viên thay thế đã khóa: ':''}${s.label}</option>`).join('');el('strategy').value=D.primary;
function update(){let id=el('strategy').value,s=D.specs.find(s=>s.id===id),p=s.policy,full=D.rows.filter(r=>r.strategy_id===id&&r.window==='full'),rows=D.rows.filter(r=>r.strategy_id===id&&r.window===el('period').value);el('rules').textContent=s.timing.label+` · ${s.cap} vị thế · tổng 25 USDT danh nghĩa chia ba · `+(p.loss_usdt?`SL ${p.loss_usdt} USDT khi đủ phần, tối đa ${p.max_hold_hours} giờ`:'Không SL, không thời hạn');Plotly.react('chart',full.map(r=>({x:D.curves[r.id].x,y:D.curves[r.id].y,name:cn(r),type:'scatter',mode:'lines'})),{paper_bgcolor:'#111f33',plot_bgcolor:'#111f33',font:{color:'#becce0'},margin:{l:60,r:20,t:10,b:80},xaxis:{type:'date',gridcolor:'#30465f'},yaxis:{title:{text:'USDT'},gridcolor:'#30465f'},legend:{orientation:'h',y:-.2},shapes:[{type:'line',xref:'paper',x0:0,x1:1,y0:500,y1:500,line:{color:'#ddbc84',dash:'dot',width:1}}]},{responsive:true,displaylogo:false});el('detail').innerHTML=rows.map(r=>`<tr><td>${cn(r)}</td><td>${f(r.ending_equity)}</td><td>${f(r.max_drawdown*100)}%</td><td>${r.entries}/${r.exits}/${r.open_count}</td><td>${r.adds}</td><td>${f(r.mean_deployed_notional)}</td><td>${f(r.fees)} / ${f(r.funding)}</td><td>${f(r.max_hold_days)} ngày</td></tr>`).join('');let w=rows[0];el('watch').textContent=`Tín hiệu gốc: ${w.source_events}; đủ điều kiện vào: ${w.watch_counts.triggered||0}; hết hạn: ${w.watch_counts.expired||0}; còn chờ cuối kỳ: ${w.watch_counts.end_pending||0}; thiếu dữ liệu: ${w.watch_counts.missing_data||0}.`;const names={loss_stop:'Cắt lỗ',time_exit:'Hết thời hạn',trailing_exit:'Trailing',tp:'TP cố định'};el('reasons').innerHTML=rows.map(r=>`<p>${cn(r)}: ${Object.entries(r.exit_reasons).map(([k,v])=>(names[k]||k)+': '+v).join(' · ')} · ${r.paused?'Đã khóa mở mới':'Chưa khóa mở mới'}</p>`).join('');el('confidence').innerHTML=D.rows.filter(r=>r.strategy_id===id&&r.window==='holdout').map(r=>`<p>${cn(r)}: ${r.daily_bootstrap?r.daily_bootstrap.ci95_daily.map(f).join(' đến ')+' USDT/ngày':'Không xác định'}</p>`).join('');}
function timingTable(){let family=el('family').value,exit=el('exit').value;el('timings').innerHTML=D.timings.map(t=>{let spec=D.all_specs.find(s=>s.family===family&&s.exit===exit&&s.timing.id===t.id),dev=D.development.find(r=>r.strategy_id===spec.id),fin=D.finalists.find(r=>r.strategy_id===spec.id),a=D.audits[['full',spec.signal_id,t.id].join('|')];return `<tr><td>${t.label}</td><td>${a.counts.triggered||0}/${a.source_events}</td><td>${a.counts.expired||0}/${a.counts.end_pending||0}</td><td>${range(dev,false)}</td><td>${range(fin?.validation)}</td><td>${range(fin?.holdout)}</td></tr>`}).join('');}el('strategy').onchange=update;el('period').onchange=update;el('family').onchange=timingTable;el('exit').onchange=timingTable;update();timingTable();</script></html>"""
    for k, v in dict(
        STYLE=style,
        FULL=span(matched(s["primary"], "full")),
        HOLD=span(matched(s["primary"], "holdout")),
        COMPARE="".join(comparison),
        NOSTOP="".join(no_stop),
        PLOTLY=get_plotlyjs(),
        DATA=payload,
    ).items():
        html = html.replace(f"__{k}__", v)
    (OUT / "dashboard.html").write_text(html, encoding="utf-8")
    md = [
        "# Thử các điểm vào Short — 25/09/2026",
        "",
        "500 USDT, Cross x5; tổng ký quỹ 5 USDT/vị thế, chia ba. 13 cách chọn điểm vào × bốn nhóm tín hiệu × hai cách thoát = 104 cấu hình. 668 lượt chính và 48 lượt không SL/thời hạn. Không bật live.",
        "",
        "Chưa có điểm vào mới tốt hơn ổn định. Ứng viên thay thế được khóa trước tháng cuối là chờ 15 phút + TP cố định; đối chứng vào ngay vẫn tốt hơn. Chờ ba giờ + trailing có tháng cuối dương nhưng tháng xác nhận vẫn có trường hợp âm. Không chọn lại theo tháng cuối.",
        "",
        "| Phương án, có SL/48 giờ | 24/07–24/08 | 24/08–24/09 | Toàn kỳ 24/06–24/09 | DD toàn kỳ |",
        "|---|---:|---:|---:|---:|",
        *md_rows,
        "",
        "Khoảng là tài sản cuối kỳ theo các giả định chi phí/quan sát, không phải khoảng tin cậy. Mỗi tháng khởi đầu 500 USDT riêng; toàn kỳ liên tục. Tính cả lỗ/lãi vị thế mở.",
        "",
        "## Giá vào và tín hiệu không khớp",
        "",
        "Trên các sự kiện được cả hai bản thực vào, chờ 15 phút có giá Short thấp hơn trung bình 0,22–0,27% (79–84 sự kiện, chỉ 30–31 có giá cao hơn). Không quy toàn bộ chênh lệch PnL cho giá vào vì danh mục, phần thêm và cách thoát có thể khác.",
        "",
        "Ví dụ nhóm coin yếu có 465 sự kiện toàn kỳ. Chờ hồi 0,5 ATR: 284 sự kiện kích hoạt, 178 hết hạn, ba còn chờ cuối kỳ. Chờ hồi rồi giảm lại ở ngưỡng 0,5 ATR: 267 kích hoạt, 195 hết hạn, ba còn chờ. Kích hoạt chỉ là đủ điều kiện giá, vẫn phải qua giới hạn tài khoản.",
        "",
        "## Bản không stop-loss và không thời hạn",
        "",
        "Giữ TP cố định của ứng viên và chia ba: chờ 15 phút, tối đa một vị thế: tài sản toàn kỳ 485,33–518,34 USDT. Tối đa năm vị thế: 458,96–487,18 USDT. Chưa tạo lợi nhuận ổn định dù một số đường mô phỏng cải thiện so với vào ngay. Đây là thử bổ sung, không lựa chọn lại ứng viên.",
        "",
        "## Quy tắc và giới hạn",
        "",
        s["protocol"]["timing"],
        "",
        s["protocol"]["capital"],
        "",
        s["protocol"]["controls"],
        "",
        s["protocol"]["selection"],
        "",
        s["protocol"]["gate"],
        "",
        s["protocol"]["limitations"],
        "",
        "Phí cơ sở 0,05%/chiều và trượt giá 0,20%; trường hợp cao 0,10% và 0,50%. Phí thay đổi đường đi của tài khoản, không chỉ trừ một khoản cuối kỳ; chi phí cao có thể vô tình đổi thứ tự lệnh và cho kết quả tốt hơn, không phải bằng chứng về lợi thế. Trailing lấy mẫu 5/15 phút, chưa phải native liên tục. MMR dùng proxy 1%; còn thiên lệch sống sót do bộ hợp đồng hiện tại. Lịch sử đã xem trước; không phải holdout chưa từng sử dụng.",
        "",
        f"Kiểm tra: {verification['unit_tests_passed']} tests; {verification['journals_audited']} sổ; {verification['watch_sets_reproduced']} tập theo dõi tái lập và prefix invariance; bốn đường tài sản ứng viên tái lập chính xác; {verification['original_regressions']} đối chứng cũ khớp. Cấu hình thật không đổi.",
        "",
        "[Dashboard](dashboard.html) · [Kết quả](comparison.csv) · [Giá vào cùng sự kiện](paired_entry_prices.json) · [Tín hiệu](entry_watches.json) · [Đối soát](verification.json)",
    ]
    (OUT / "report.md").write_text("\n".join(md), encoding="utf-8")
    assert primary["strategy_id"] == pairs["primary"]
    print(OUT / "dashboard.html")


if __name__ == "__main__":
    main()
