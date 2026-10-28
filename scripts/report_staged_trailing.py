"""Interactive, offline research report for split entries and trailing exits."""

from __future__ import annotations

import json
from html import escape

import pandas as pd
from check_staged_without_stops import OUT
from plotly.offline import get_plotlyjs


def main():
    s = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    extra = json.loads((OUT / "no_stop_results.json").read_text(encoding="utf-8"))
    rows = [r for r in s["results"] if r["window"] != "development"] + extra["results"]
    specs = [
        f["spec"]
        for f in sorted(
            s["finalists"],
            key=lambda f: (not f["primary"], not f["shortlisted"], f["strategy_id"]),
        )
    ] + [
        dict(spec, label=spec["label"] + f" · KHÔNG SL/thời hạn · {spec['cap']} vị thế")
        for spec in extra["specs"]
    ]
    lookup = {spec["id"]: spec for spec in specs}
    primary = s["primary"]

    def selected(sid, window="full"):
        return [r for r in rows if r["strategy_id"] == sid and r["window"] == window]

    def value_range(rr, key="ending_equity", pct=False):
        vals = [r[key] for r in rr]
        if not vals or any(v is None for v in vals):
            return "Chưa xác định"
        factor = 100 if pct else 1
        return f"{min(vals) * factor:.2f}–{max(vals) * factor:.2f}" + (
            "%" if pct else ""
        )

    comparisons = [
        ("weak_rank_original", "Vào một lần + TP cố định, đối chứng gốc"),
        ("weak_rank_single_fixed", "Vào một lần + TP cố định, cùng bộ lọc chia lệnh"),
        ("weak_rank_favor0_5_fixed", "Chia 3 phần + TP cố định"),
        ("weak_rank_single_trail_a3_c1", "Vào một lần + trailing"),
        (primary, "Chia 3 phần + trailing — ứng viên đã khóa"),
    ]
    comparisons += [
        (
            primary + f"_nostop_n{cap}",
            f"Chia 3 + trailing, KHÔNG SL/thời hạn, tối đa {cap} vị thế",
        )
        for cap in [1, 5]
    ]
    table, md_table = [], []
    for sid, label in comparisons:
        full, hold = selected(sid), selected(sid, "holdout")
        dd = max(r["max_drawdown"] for r in full) * 100
        table.append(
            f"<tr><td>{escape(label)}</td><td>{value_range(full)}</td><td>{value_range(hold)}</td><td>{dd:.2f}%</td><td>{min(r['entries'] for r in full)}–{max(r['entries'] for r in full)}</td></tr>"
        )
        md_table.append(
            f"| {label} | {value_range(full)} | {value_range(hold)} | {dd:.2f}% |"
        )
    curves = {}
    for r in rows:
        if r["window"] != "full":
            continue
        frame = pd.read_parquet(OUT / "runs" / f"{r['id']}_equity.parquet")
        grouped = frame.groupby(frame["at"] // 3600000)
        indices = sorted(
            set(grouped.equity.idxmin())
            | set(grouped.equity.idxmax())
            | {0, len(frame) - 1}
        )
        frame = frame.loc[indices]
        curves[r["id"]] = dict(x=frame["at"].tolist(), y=frame.equity.tolist())
    payload = json.dumps(
        dict(rows=rows, specs=specs, curves=curves, primary=primary),
        ensure_ascii=False,
        allow_nan=False,
    ).replace("</", "<\\/")
    html = """<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Chia 3 phần và trailing</title>
<style>body{font:15px Segoe UI,Arial;background:#0b1525;color:#e2e8f0;max-width:1540px;margin:auto;padding:26px}h1{font-size:30px}h2{font-size:21px}p,li{color:#becce0;line-height:1.65}.notice{background:#302629;border:1px solid #87616b;padding:18px;border-radius:12px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}.card,.panel{background:#111f33;border:1px solid #30465f;border-radius:12px;padding:18px}.card strong{display:block;font-size:26px;margin-top:8px}.panel{margin:20px 0}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}th,td{padding:12px;border-bottom:1px solid #30465f;text-align:right}th:first-child,td:first-child{text-align:left}select{background:#1a2d46;color:white;border:1px solid #48647f;border-radius:7px;padding:10px;max-width:100%;margin:5px}#chart{height:420px}a{color:#7dd3fc}.foot{font-size:13px}@media(max-width:700px){body{padding:12px}.cards{grid-template-columns:1fr 1fr}}</style>
<h1>Chia 3 phần + TP trailing: có tốt hơn?</h1><p>24/06–24/09/2026 UTC · Vốn 500 USDT · Cross x5 · Tổng ký quỹ dự kiến 5 USDT/vị thế, chia ba · Chỉ mô phỏng, chưa bật live</p>
<div class="notice"><b>Chia lệnh giảm mức phơi nhiễm; trailing chưa tạo lợi thế ổn định.</b><p>Ứng viên đã khóa: tài sản toàn kỳ <b>__FULL__ USDT</b>, nhưng tháng cuối chỉ còn <b>__HOLD__ USDT</b>. Bản không stop-loss với tối đa 5 vị thế còn <b>__NOSTOP__ USDT</b> toàn kỳ. Chưa đủ điều kiện áp dụng lên tài khoản thật.</p></div>
<div class="cards"><div class="card">Cấu hình tìm kiếm<strong>204</strong></div><div class="card">Lượt mô phỏng chính<strong>1.296</strong></div><div class="card">Đối chiếu không SL/thời hạn<strong>144</strong></div><div class="card">Đạt tiêu chí chính<strong>0</strong></div></div>
<section class="panel"><h2>So sánh trên cùng nhóm tín hiệu coin yếu</h2><p>Mỗi khoảng số là bốn giả định về nhịp quan sát trailing và chi phí, không phải khoảng tin cậy. TP cố định không phụ thuộc nhịp trailing nên có kết quả trùng. Mỗi kỳ tháng bắt đầu riêng từ 500 USDT; toàn kỳ chạy liên tục. Vị thế còn mở luôn được định giá.</p><div class="scroll"><table><thead><tr><th>Phương án</th><th>Tài sản toàn kỳ</th><th>Tài sản tháng cuối</th><th>DD toàn kỳ cao nhất</th><th>Số vị thế mở trong kỳ</th></tr></thead><tbody>__COMPARE__</tbody></table></div><p>Các dòng đầu giữ SL 1 USDT khi đủ ba phần và thời hạn 48 giờ; SL giảm theo tỷ lệ phần đã vào. Dòng đối chứng gốc không lọc mức tối thiểu mỗi phần. Các dòng còn lại dùng cùng bộ lọc để tránh nhầm tác dụng của loại coin với tác dụng của chia lệnh.</p></section>
<section class="panel"><h2>Cách vào ba phần và trailing đang được thử</h2><ol><li>Tín hiệu ứng viên: thuộc 20% coin yếu nhất theo lợi suất 24 giờ trong 30 altcoin, giảm ít nhất 3%; EMA 20 giờ dưới EMA 60 giờ và giá dưới EMA 20. Quét 00/06/12/18 giờ UTC; mỗi coin cách nhau tối thiểu 24 giờ giữa các tín hiệu.</li><li>Phần đầu khoảng 8,33 USDT danh nghĩa. Phần hai khi giá đóng nến giảm thêm 0,5 ATR từ giá vào đầu; phần ba khi giảm thêm 1 ATR. Mỗi bước chỉ thêm một phần và giá quan sát phải không cao hơn giá vốn bình quân. Khoảng trống giá có thể khiến giá khớp xấu hơn.</li><li>ATR 14 giờ khóa tại lúc vào. Sau khi giá giảm 3 ATR từ lần vào đầu, bật trailing; theo dõi đáy giá và mua đóng Short khi giá hồi 1% từ đáy. Không áp trần TP tiền cố định cho bản trailing.</li><li>Ngừng thêm phần còn lại khi trailing bật, hết 6 giờ, vị thế đóng hoặc tài khoản khóa mở mới vì giảm 20% từ đỉnh. Vốn chưa dùng cho các phần được giữ chỗ. Một bộ ba phần tính là một vị thế.</li></ol><p>Ví dụ: vào đầu ở 100, ATR=2 → thêm ở mức quan sát 99 và 98; kích hoạt trailing ở 94. Nếu đáy sau đó là 90, mức hồi 1% là 90,90. Giá khớp thực tế có thể khác; trailing không đảm bảo chốt lời và không bảo vệ lệnh chưa kích hoạt.</p><p>BCH và LINK có mức tối thiểu 20 USDT/lệnh theo bản quy tắc sàn lưu tại nghiên cứu, nên mỗi phần 8,33 USDT không hợp lệ. Mô phỏng bỏ qua, không tự nâng vốn.</p><p><b>Đây là trailing do bot quan sát giá đóng mỗi 5 hoặc 15 phút, khớp tại giá mở nến 5 phút kế tiếp cộng trượt giá; chưa phải mô phỏng chính xác trailing liên tục lưu trên Binance.</b> Tham khảo <a href="https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade">API giao dịch Binance</a>. Việc đưa trailing lên sàn cần bước triển khai và kiểm định riêng.</p></section>
<section class="panel"><h2>Xem từng cấu hình</h2><label>Phương án <select id="strategy"></select></label><p id="rules"></p><div id="chart"></div><p class="foot">Biểu đồ toàn kỳ giữ cực trị theo giờ; số đo tài khoản tính mỗi 5 phút. Danh nghĩa bình quân là tổng các phần đã khớp trên mỗi vị thế, không phải mức phơi nhiễm bình quân theo thời gian.</p><label>Kỳ số liệu <select id="period"><option value="full">Toàn kỳ 24/06–24/09</option><option value="validation">Kỳ xác nhận 24/07–24/08</option><option value="holdout">Tháng cuối 24/08–24/09</option></select></label><div class="scroll"><table><thead><tr><th>Quan sát / chi phí</th><th>Tài sản cuối</th><th>DD</th><th>Mở / đóng / còn</th><th>Lượt thêm phần</th><th>Đủ 3 phần*</th><th>Danh nghĩa TB</th><th>Phí / funding</th><th>Giữ lâu nhất</th><th>Khóa mở mới</th></tr></thead><tbody id="detail"></tbody></table></div><p class="foot">*Trong các vị thế đã đóng. “Mở” đếm vị thế, không đếm từng phần. Số lệnh bán mở/thêm bằng số vị thế mở + lượt thêm phần.</p><h3>Vì sao đóng vị thế?</h3><div id="reasons"></div><h3>Khoảng ước lượng PnL/ngày tháng cuối</h3><div id="confidence"></div><p>Lấy mẫu lại theo cụm 7 ngày, 10.000 lần trên PnL tài khoản đã định giá. Các khoảng mang tính thăm dò, chưa hiệu chỉnh việc thử nhiều cấu hình; lịch sử đã được xem trước.</p></section>
<section class="panel"><h2>Kết luận từ việc bỏ stop-loss</h2><p>Với cùng ứng viên ba phần + trailing: cho phép một vị thế đưa tài khoản tới __NOONE__ USDT; nâng lên năm vị thế chỉ còn __NOSTOP__ USDT và DD tối đa __NODD__%. Có lệnh tồn tại tới __NOHOLD__ ngày. Dừng mở mới ở DD 20% giữ nguyên lệnh cũ nên tài sản vẫn có thể giảm tiếp.</p><p>Chia ba giúp hạn chế tiền vào sớm khi tín hiệu sai. Trong bản có cắt lỗ, danh nghĩa thực vào trung bình chỉ khoảng __DEPLOY__ USDT/vị thế, thấp hơn ngân sách 25 USDT; vì vậy không thể quy toàn bộ mức giảm DD cho chất lượng tín hiệu. Trailing cũng trả lại một phần lãi khi giá hồi và có thể bỏ lỡ biến động giữa hai lần quan sát.</p></section>
<section class="panel"><h2>Phương pháp và giới hạn</h2><p>204 cấu hình: bốn nguồn tín hiệu × năm cách vào (một lần; ba phần theo 15/60 phút hoặc giảm 0,25/0,5 ATR) × mười cách thoát (TP gốc hoặc chín tổ hợp kích hoạt 1/2/3 ATR và hồi 0,5/1/2%), cộng bốn đối chứng gốc. Quy tắc theo thời gian là các mốc dự kiến từ lần vào đầu; vẫn cần điều kiện giá thuận hướng. Giữ cắt lỗ và thời hạn của từng nguồn: thường SL 1 USDT/48 giờ, riêng pullback 0,50 USDT/24 giờ; mức SL theo tỷ lệ đã vào.</p><p>Chọn tối đa hai cấu hình kết hợp mỗi nhóm theo tháng phát triển 24/06–24/07: hoàn tất bốn trường hợp, DD dưới 20%, ít nhất 20 vị thế đóng. Khóa danh sách trước kỳ xác nhận, rồi khóa ứng viên chính trước tháng cuối. Đối chứng giữ nguyên; các thử nghiệm bỏ SL/thời hạn chạy bổ sung, không chọn lại ứng viên từ chúng.</p><p>Tiêu chí chính: cả bốn giả định ở kỳ xác nhận và tháng cuối đều lãi/DD dưới 20%, ít nhất 20 vị thế đóng mỗi kỳ; toàn kỳ cũng lãi/DD dưới 20%. Chưa có cấu hình đạt. Đây chưa phải nghiệm thu thống kê hay quyền bật live.</p><p>Chi phí cơ sở: phí 0,05% mỗi chiều, trượt giá 0,20%. Trường hợp cao: phí 0,10%, trượt giá 0,50%. Không có sổ lệnh lịch sử để xác minh trượt giá. Funding và Mark Price dùng bộ dữ liệu công khai Binance đã kiểm tra; dữ liệu giá kết thúc 23/09. Danh sách 30 altcoin dựa trên thanh khoản trước kỳ, nhưng bộ hợp đồng/bước giá hiện tại vẫn có thiên lệch sống sót. Không loại coin theo kết quả thua; AKE không thuộc top 30 thanh khoản trước kỳ. MMR 1% là mô hình thay thế, chưa phải thanh lý chính xác theo bậc Binance.</p><p>Đã kiểm tra 71 kiểm thử, đối soát 624 sổ kết quả, chạy lại chính xác bốn trường hợp toàn kỳ của ứng viên và khớp 32 đối chứng gốc. Cấu hình tài khoản thật giữ nguyên.</p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">Kết quả chính</a> · <a href="no_stop_comparison.csv">Bản không SL</a> · <a href="protocol.json">Quy tắc</a> · <a href="verification.json">Đối soát</a></section>
<script>__PLOTLY__</script><script>
const D=__DATA__,el=id=>document.getElementById(id),f=x=>x===null||x===undefined?'—':x.toLocaleString('vi-VN',{minimumFractionDigits:2,maximumFractionDigits:2}),cn=r=>r.observation_minutes+' phút / '+(r.cost==='base'?'cơ sở':'cao');
el('strategy').innerHTML=D.specs.map(s=>`<option value="${s.id}">${s.id===D.primary?'Đã khóa: ':''}${s.label}</option>`).join('');el('strategy').value=D.primary;
function update(){let id=el('strategy').value,s=D.specs.find(s=>s.id===id),p=s.policy,full=D.rows.filter(r=>r.strategy_id===id&&r.window==='full'),rows=D.rows.filter(r=>r.strategy_id===id&&r.window===el('period').value);el('rules').textContent=`Tối đa ${s.cap} vị thế · ${p.entry_parts||1} phần · `+(p.loss_usdt?`SL khi đủ phần ${p.loss_usdt} USDT, giảm theo tỷ lệ đã vào · giữ tối đa ${p.max_hold_hours} giờ`:'Không SL, không thời hạn đóng')+' · '+(p.trailing?`Trailing bật sau ${p.activation_atr} ATR, hồi ${p.callback_fraction*100}%`:'TP cố định');Plotly.react('chart',full.map(r=>({x:D.curves[r.id].x,y:D.curves[r.id].y,name:cn(r),type:'scatter',mode:'lines'})),{paper_bgcolor:'#111f33',plot_bgcolor:'#111f33',font:{color:'#becce0'},margin:{l:60,r:20,t:10,b:80},xaxis:{type:'date',gridcolor:'#30465f'},yaxis:{title:{text:'USDT'},gridcolor:'#30465f'},legend:{orientation:'h',y:-.2},shapes:[{type:'line',xref:'paper',x0:0,x1:1,y0:500,y1:500,line:{color:'#ddbc84',dash:'dot',width:1}}]},{responsive:true,displaylogo:false});el('detail').innerHTML=rows.map(r=>`<tr><td>${cn(r)}</td><td>${f(r.ending_equity)}</td><td>${f(r.max_drawdown*100)}%</td><td>${r.entries}/${r.exits}/${r.open_count}</td><td>${r.adds}</td><td>${r.completed_parts.filter(x=>x===3).length}/${r.exits}</td><td>${f(r.mean_deployed_notional)}</td><td>${f(r.fees)} / ${f(r.funding)}</td><td>${f(r.max_hold_days)} ngày</td><td>${r.paused?'Có':'Không'}</td></tr>`).join('');const names={loss_stop:'Cắt lỗ',time_exit:'Hết thời hạn',trailing_exit:'Trailing',tp:'TP cố định'};el('reasons').innerHTML=rows.map(r=>`<p>${cn(r)}: ${Object.entries(r.exit_reasons).map(([k,v])=>(names[k]||k)+': '+v).join(' · ')||'Chưa đóng vị thế'}${r.errors.length?' · Không hoàn tất: '+r.errors.join(', '):''}</p>`).join('');el('confidence').innerHTML=D.rows.filter(r=>r.strategy_id===id&&r.window==='holdout').map(r=>`<p>${cn(r)}: ${r.daily_bootstrap?r.daily_bootstrap.ci95_daily.map(f).join(' đến ')+' USDT/ngày':'Không xác định'}</p>`).join('');}el('strategy').onchange=update;el('period').onchange=update;update();</script></html>"""
    full = selected(primary)
    nostop = selected(primary + "_nostop_n5")
    replacements = dict(
        FULL=value_range(full),
        HOLD=value_range(selected(primary, "holdout")),
        NOSTOP=value_range(nostop),
        NOONE=value_range(selected(primary + "_nostop_n1")),
        NODD=f"{max(r['max_drawdown'] for r in nostop) * 100:.2f}",
        NOHOLD=f"{max(r['max_hold_days'] for r in nostop):.1f}",
        DEPLOY=value_range(full, "mean_deployed_notional"),
        COMPARE="".join(table),
        PLOTLY=get_plotlyjs(),
        DATA=payload,
    )
    for k, v in replacements.items():
        html = html.replace(f"__{k}__", v)
    (OUT / "dashboard.html").write_text(html, encoding="utf-8")
    md = [
        "# Chia ba phần và trailing — 25/09/2026",
        "",
        "Giả định tổng ký quỹ 5 USDT/vị thế, x5: ngân sách danh nghĩa 25 USDT chia ba, không phải 5 USDT ký quỹ mỗi phần. Vốn 500 USDT. Giai đoạn 24/06–24/09/2026 UTC. Không bật live.",
        "",
        "204 cấu hình / 1.296 lượt mô phỏng chính; 12 cấu hình bỏ SL và thời hạn / 144 lượt bổ sung. Không có cấu hình vượt tiêu chí chính.",
        "",
        f"Ứng viên khóa trước kỳ cuối: {primary}. {lookup[primary]['label']}. Toàn kỳ {replacements['FULL']} USDT; tháng cuối {replacements['HOLD']} USDT. Lãi toàn kỳ chưa chứng minh lợi thế ổn định.",
        "",
        "| Phương án | Tài sản toàn kỳ | Tháng cuối | DD cao nhất toàn kỳ |",
        "|---|---:|---:|---:|",
        *md_table,
        "",
        "Khoảng số là các giả định chi phí/quan sát, không phải khoảng tin cậy. Mỗi tháng đánh giá riêng bắt đầu với 500 USDT; toàn kỳ liên tục.",
        "",
        "## Cơ chế ứng viên",
        "",
        "Phần đầu 1/3 ngân sách; thêm lần hai và ba khi giá giảm 0,5 và 1 ATR từ lần đầu, giá quan sát không cao hơn VWAP. ATR 14 giờ khóa lúc vào. Không bình quân khi giá quan sát đi ngược. Hết 6 giờ hoặc trailing bật thì hủy phần chưa vào. Bật trailing khi giảm 3 ATR, mua đóng khi hồi 1% từ đáy quan sát; không trần TP tiền cố định.",
        "",
        "Bản nghiên cứu chính có SL 1 USDT theo tỷ lệ đã vào và thời hạn 48 giờ, tối đa một vị thế. SL không bảo đảm khớp đúng số tiền khi có khoảng trống giá. Bản không SL/thời hạn được tách riêng ở bảng.",
        "",
        f"Chia ba + trailing không SL, tối đa năm vị thế: còn {replacements['NOSTOP']} USDT, DD {replacements['NODD']}%, giữ lâu nhất {replacements['NOHOLD']} ngày. Dừng mở mới không đóng vị thế cũ. Trailing chưa bật không bảo vệ lệnh đang lỗ.",
        "",
        f"Danh nghĩa trung bình thực vào của bản chính: {replacements['DEPLOY']} USDT/vị thế, thấp hơn ngân sách 25 USDT. Giảm DD có phần do dùng ít vốn. BCH/LINK bị bỏ nếu từng phần không đạt mức tối thiểu 20 USDT trong bản quy tắc sàn hiện có; không tự tăng vốn.",
        "",
        "## Phương pháp và giới hạn",
        "",
        s["protocol"]["selection"],
        "",
        s["protocol"]["observation"],
        "",
        s["protocol"]["gate"],
        "",
        s["protocol"]["limitations"],
        "",
        "Phí cơ sở 0,05% và trượt giá 0,20%; trường hợp cao 0,10% và 0,50%. Trailing quan sát 5/15 phút, không phải trailing native liên tục Binance. Kết quả phụ thuộc nhịp quan sát, chưa có sổ lệnh lịch sử. MMR 1% là giả định thay thế; danh sách và quy tắc sàn hiện tại còn thiên lệch sống sót. Không loại coin dựa trên thua lỗ; AKE không thuộc top 30 theo thanh khoản trước kỳ. Các ngày lịch sử đã được xem trước. Khoảng bootstrap 7 ngày không hiệu chỉnh việc thử nhiều cấu hình.",
        "",
        "71 kiểm thử đạt; 624 sổ giao dịch được đối soát; bốn bản chạy toàn kỳ của ứng viên tái lập chính xác; 32 đối chứng gốc khớp nghiên cứu trước. Cấu hình thật không đổi.",
        "",
        "[Dashboard](dashboard.html) · [Kết quả chính](comparison.csv) · [Không SL](no_stop_comparison.csv) · [Đối soát](verification.json)",
        "",
        "[Tài liệu API Binance](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade)",
    ]
    (OUT / "report.md").write_text("\n".join(md), encoding="utf-8")
    print(OUT / "dashboard.html")


if __name__ == "__main__":
    main()
