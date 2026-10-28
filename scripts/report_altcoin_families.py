"""Report new short hypotheses, locked selection and execution-cost limits."""

from __future__ import annotations

import json
from html import escape

import pandas as pd
from plotly.offline import get_plotlyjs
from prepare_altcoin_search import OUT
from search_altcoin_families import FAMILY_NAMES


def interval(r):
    return (
        f"{500 + r['worst_pnl']:.2f}–{500 + r['best_pnl']:.2f}"
        if r["complete"]
        else "Chưa xác định"
    )


def main():
    s = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    sensitivity = json.loads(
        (OUT / "cost_sensitivity.json").read_text(encoding="utf-8")
    )
    finalists = sorted(
        s["finalists"],
        key=lambda f: (
            not f["primary"],
            not f["shortlisted"],
            -(f["validation"]["worst_pnl"] if f["validation"]["complete"] else -1e9),
        ),
    )
    rows = [r for r in s["results"] if r["window"] != "development"]
    primary = next(f for f in finalists if f["primary"])
    curves = {}
    for r in rows:
        if r["window"] != "full":
            continue
        f = pd.read_parquet(OUT / "runs" / f"{r['id']}_equity.parquet")
        g = f.groupby(f["at"] // 3600000)
        indices = sorted(
            set(g.equity.idxmin()) | set(g.equity.idxmax()) | {0, len(f) - 1}
        )
        f = f.loc[indices]
        curves[r["id"]] = dict(x=f["at"].tolist(), y=f.equity.tolist())
    payload = json.dumps(
        dict(
            finalists=finalists,
            rows=rows,
            curves=curves,
            primary=s["primary"],
            sensitivity=sensitivity["results"],
        ),
        ensure_ascii=False,
        allow_nan=False,
    ).replace("</", "<\\/")
    family_rows = []
    for family, title in FAMILY_NAMES.items():
        group = [
            f for f in finalists if f["spec"]["family"] == family and f["shortlisted"]
        ]
        if group:
            best = group[0]
            family_rows.append(
                f"<tr><td>{escape(title)}</td><td>{interval(best['validation'])}</td><td>{interval(best['holdout'])}</td><td>{interval(best['full'])}</td><td>{'Có' if best['diagnostic_passed'] else 'Không'}</td></tr>"
            )
    html = """<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Chiến lược Short mới</title>
<style>body{font:15px Segoe UI,Arial;background:#0b1525;color:#e2e8f0;max-width:1540px;margin:auto;padding:26px}h1{font-size:30px}h2{font-size:21px}p,li{color:#b9c9df;line-height:1.7}.notice{background:#302629;border:1px solid #87616b;padding:18px;border-radius:12px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}.card,.panel{background:#111f33;border:1px solid #30465f;border-radius:12px;padding:18px}.card strong{display:block;font-size:27px;margin-top:8px}.panel{margin:20px 0}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}th,td{padding:12px;border-bottom:1px solid #30465f;text-align:right}th:first-child,td:first-child{text-align:left}select{background:#1a2d46;color:white;border:1px solid #48647f;border-radius:7px;padding:10px;max-width:100%}#chart{height:420px}a{color:#7dd3fc}.pos{color:#65e6bf}.neg{color:#ff9393}.foot{font-size:13px}@media(max-width:700px){body{padding:12px}.cards{grid-template-columns:1fr 1fr}}</style>
<h1>Short altcoin: thay cách tìm tín hiệu</h1><p>30 altcoin chọn theo thanh khoản trước kỳ thử · Vốn 500 USDT · Cross x5 · Khoảng 25 USDT danh nghĩa mỗi lệnh</p>
<div class="notice"><b>Có ứng viên lãi rất mỏng toàn kỳ; chưa có phương án vượt đầy đủ tiêu chí.</b><p>Ứng viên khóa trước kỳ cuối: Short coin yếu, TP 3 ATR, SL 1 USDT, giữ tối đa 48 giờ, một vị thế. Toàn kỳ: __FULL__ USDT. Kỳ kiểm tra cuối: __HOLD__ USDT. Cấu hình thật giữ nguyên, chưa bật live.</p></div>
<div class="cards"><div class="card">Cấu hình mới<strong>320</strong></div><div class="card">Lượt kiểm tra chính<strong>__RUNS__</strong></div><div class="card">Đo độ nhạy trượt giá<strong>30</strong></div><div class="card">Đạt tiêu chí nghiên cứu<strong>__PASS__</strong></div></div>
<section class="panel"><h2>So sánh bốn nhóm chiến lược</h2><p>Mỗi nhóm hiển thị ứng viên được xếp cao nhất theo kỳ xác nhận, trước khi xem kỳ cuối. Mỗi kỳ độc lập bắt đầu lại với 500 USDT; toàn kỳ là tài khoản chạy liên tục. Khoảng số là bốn giả định khớp/chi phí, không phải khoảng tin cậy.</p><div class="scroll"><table><thead><tr><th>Nhóm</th><th>24/07–24/08</th><th>24/08–24/09</th><th>Toàn kỳ 24/06–24/09</th><th>Đạt tiêu chí</th></tr></thead><tbody>__FAMILIES__</tbody></table></div></section>
<section class="panel"><h2>Quy tắc cụ thể của ứng viên đã khóa</h2><ol><li>Trong 30 altcoin đã chọn, nằm trong 20% coin giảm mạnh nhất 24 giờ; bản thân giảm ít nhất 3%.</li><li>EMA 20 giờ dưới EMA 60 giờ; giá đóng nến dưới EMA 20. Kiểm tra vào các mốc 00/06/12/18 giờ UTC.</li><li>Cần 120 giờ nến đầy đủ và thanh khoản 24 giờ tối thiểu 2 triệu USDT. Mỗi coin cách nhau ít nhất 24 giờ giữa các sự kiện tín hiệu; ưu tiên coin giảm mạnh hơn nếu cùng lúc.</li><li>Một vị thế, khoảng 25 USDT danh nghĩa. Mục tiêu ròng dựa trên 3 ATR 14 giờ, tối thiểu 0,50 và trần 5 USDT; khóa tại khi vào lệnh.</li><li>Cắt lỗ dự kiến 1 USDT hoặc đóng sau 48 giờ; quan sát mỗi 5 phút nên lỗ có thể vượt ngưỡng. Không DCA. Dừng mở mới khi tài sản giảm 20% từ đỉnh.</li></ol><p>Đây là quy tắc nghiên cứu, chưa được áp dụng lên tài khoản thật. Không dùng model cũ hay danh sách 165 tín hiệu cũ.</p></section>
<section class="panel"><h2>Kết quả chi tiết</h2><label>Phương án <select id="strategy"></select></label><div id="chart"></div><p class="foot">Biểu đồ tài khoản liên tục; giữ cực trị theo giờ, số đo tính mỗi 5 phút. Vị thế cuối kỳ được định giá, không loại lệnh đang lỗ. Đường dừng khi mô phỏng không hoàn tất.</p><div class="scroll"><table><thead><tr><th>Khớp / chi phí</th><th>Tài sản cuối</th><th>DD</th><th>Vào / đóng / mở</th><th>Phí</th><th>Funding</th><th>Giữ lâu nhất</th><th>Trạng thái</th></tr></thead><tbody id="detail"></tbody></table></div><h3>Đánh giá kỳ cuối 24/08–24/09</h3><div class="scroll"><table><thead><tr><th>Khớp / chi phí</th><th>Tài sản cuối</th><th>Lệnh đóng</th><th>Khoảng 95% PnL/ngày (USDT)</th></tr></thead><tbody id="holdout"></tbody></table></div><p>Khoảng ước lượng lấy mẫu lại theo cụm 7 ngày, có tính định giá vị thế mở. Chỉ mang tính thăm dò, chưa hiệu chỉnh việc thử nhiều phương án. Khoảng còn chứa 0 nghĩa là chưa loại trừ được khả năng không có lợi thế.</p></section>
<section class="panel"><h2>Ứng viên chính nhạy với trượt giá thế nào?</h2><p>Giữ phí 0,05% mỗi chiều và nguyên quy tắc đã khóa; chỉ thay trượt giá. Các mức thấp là giả định, chưa có dữ liệu sổ lệnh lịch sử chứng minh khả năng đạt. Bảng này không thay đổi kết quả nghiệm thu ban đầu.</p><div class="scroll"><table><thead><tr><th>Trượt giá giả định</th><th>Tài sản kỳ xác nhận</th><th>Tài sản kỳ cuối</th><th>Tài sản toàn kỳ</th></tr></thead><tbody id="costs"></tbody></table></div></section>
<section class="panel"><h2>Cách tìm và những giới hạn còn lại</h2><p>Chọn 30 altcoin theo khối lượng giao dịch 17–23/06 trước khi bắt đầu; không loại coin theo kết quả lỗ. Loại BTC, ETH, stablecoin và hợp đồng cổ phiếu/hàng hóa. Tuy nhiên danh sách sàn và bước giá/khối lượng dùng bản hiện tại nên còn thiên lệch sống sót.</p><p>320 cấu hình gồm 32 cách tạo/lọc tín hiệu × 5 cách thoát × 1 hoặc 5 vị thế. Giai đoạn tìm kiếm 24/06–24/07 chọn tối đa hai ứng viên mỗi nhóm, yêu cầu bốn trường hợp hoàn tất, DD dưới 20%, ít nhất 20 lệnh đóng. Khóa danh sách trước kỳ xác nhận; khóa ứng viên chính trước kỳ cuối. Bốn đối chứng không stop-loss được giữ dù kết quả kém.</p><p>Tiêu chí: cả bốn trường hợp ở kỳ xác nhận và kỳ cuối đều lãi, DD dưới 20%, ít nhất 20 lệnh đóng mỗi kỳ; toàn kỳ cũng phải lãi/DD dưới 20%. Phí cơ sở 0,05%, trượt giá 0,20%; phí cao 0,10%, trượt giá 0,50%. TP chạm giá trong nến chưa chứng minh khớp thật; ưu tiên thoát rủi ro nếu cùng bước. MMR dùng giả định 1%, chưa phải thanh lý chính xác của Binance.</p><p>Lịch sử đã từng được xem ở các nghiên cứu trước; không gọi đây là dữ liệu ngoài mẫu hoàn toàn mới. Tín hiệu mới dùng giá đến hết 23/09, không phụ thuộc dữ liệu đặc trưng cũ dừng ở 07/09. Funding và Mark Price được đối chiếu dữ liệu công khai Binance.</p><p>Giả thuyết tham khảo nghiên cứu <a href="https://www.nber.org/papers/w24877">momentum tiền mã hóa</a> và <a href="https://www.nber.org/papers/w25882">yếu tố rủi ro tiền mã hóa</a>; các nghiên cứu đó không chứng minh phiên bản Short này có lời. Cách tách giai đoạn nhằm hạn chế <a href="https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf">khớp quá mức lịch sử</a>. Cách tính chi phí tham khảo <a href="https://www.binance.com/en/support/faq/detail/360033525031">funding của Binance</a>.</p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">Toàn bộ kết quả chính</a> · <a href="cost_sensitivity.json">Độ nhạy chi phí</a> · <a href="protocol.json">Quy tắc nghiên cứu</a> · <a href="universe.json">30 coin và cách chọn</a></section>
<script>__PLOTLY__</script><script>
const D=__DATA__,el=id=>document.getElementById(id),f=x=>x===null||x===undefined?'—':x.toLocaleString('vi-VN',{minimumFractionDigits:2,maximumFractionDigits:2}),cn=r=>(r.fill==='close'?'Đóng nến':'Chạm giá')+' / '+(r.cost==='base'?'cơ sở':'cao');
el('strategy').innerHTML=D.finalists.map(r=>`<option value="${r.strategy_id}">${r.primary?'Đã khóa: ':r.shortlisted?'Ứng viên: ':'Không SL: '}${r.spec.label}</option>`).join('');el('strategy').value=D.primary;
function update(){let id=el('strategy').value,rows=D.rows.filter(r=>r.strategy_id===id&&r.window==='full');Plotly.react('chart',rows.map(r=>({x:D.curves[r.id].x,y:D.curves[r.id].y,name:cn(r),type:'scatter',mode:'lines'})),{paper_bgcolor:'#111f33',plot_bgcolor:'#111f33',font:{color:'#b9c9df'},margin:{l:60,r:20,t:10,b:80},xaxis:{type:'date',gridcolor:'#2d415b'},yaxis:{title:'USDT',gridcolor:'#2d415b'},legend:{orientation:'h',y:-.2},shapes:[{type:'line',xref:'paper',x0:0,x1:1,y0:500,y1:500,line:{color:'#ccb786',dash:'dot',width:1}}]},{responsive:true,displaylogo:false});el('detail').innerHTML=rows.map(r=>`<tr><td>${cn(r)}</td><td>${f(r.ending_equity)}</td><td>${f(r.max_drawdown*100)}%</td><td>${r.entries}/${r.exits}/${r.open_count}</td><td>${f(r.fees)}</td><td>${f(r.funding)}</td><td>${f(r.max_hold_days)} ngày</td><td>${r.ending_equity===null?'Không hoàn tất':'Hoàn tất'}</td></tr>`).join('');el('holdout').innerHTML=D.rows.filter(r=>r.strategy_id===id&&r.window==='holdout').map(r=>`<tr><td>${cn(r)}</td><td>${f(r.ending_equity)}</td><td>${r.exits}</td><td>${r.daily_bootstrap?r.daily_bootstrap.ci95_daily.map(f).join(' đến '):'Chưa xác định'}</td></tr>`).join('');}
el('strategy').onchange=update;update();el('costs').innerHTML=[2,5,10,20,50].map(b=>`<tr><td>${b} bps (${f(b/100)}%)</td>${['validation','holdout','full'].map(w=>{let rr=D.sensitivity.filter(r=>r.slippage_bps===b&&r.window===w);return `<td>${rr.every(r=>r.ending_equity!==null)?f(Math.min(...rr.map(r=>r.ending_equity)))+'–'+f(Math.max(...rr.map(r=>r.ending_equity))):'Chưa xác định'}</td>`}).join('')}</tr>`).join('');</script></html>"""
    for k, v in dict(
        FULL=interval(primary["full"]),
        HOLD=interval(primary["holdout"]),
        RUNS=str(s["runs"]),
        PASS=str(s["diagnostic_pass_count"]),
        FAMILIES="".join(family_rows),
        PLOTLY=get_plotlyjs(),
        DATA=payload,
    ).items():
        html = html.replace(f"__{k}__", v)
    (OUT / "dashboard.html").write_text(html, encoding="utf-8")
    md = [
        "# Mở rộng chiến lược Short altcoin — 25/09/2026",
        "",
        "320 cấu hình mới trên 30 altcoin, 1.424 lượt kiểm tra chính và 30 lượt đo trượt giá. Vốn 500 USDT, Cross x5, khoảng 25 USDT danh nghĩa. Không dùng model/sự kiện cũ, không loại coin vì đã biết kết quả thua.",
        "",
        f"Ứng viên khóa trước kỳ cuối: **{primary['spec']['label']}**. Toàn kỳ {interval(primary['full'])} USDT; kỳ xác nhận {interval(primary['validation'])}; kỳ cuối {interval(primary['holdout'])}. Chưa có phương án đạt đủ tiêu chí. Khoảng số là giả định khớp/chi phí, không phải khoảng tin cậy.",
        "",
        "| Phương án | Kỳ xác nhận 24/07–24/08 | Kỳ cuối 24/08–24/09 | Toàn kỳ 24/06–24/09 | DD toàn kỳ |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in finalists:
        md.append(
            f"| {r['spec']['label']} | {interval(r['validation'])} | {interval(r['holdout'])} | {interval(r['full'])} | {100 * r['full']['worst_dd']:.2f}% |"
        )
    md += [
        "",
        "## Độ nhạy trượt giá của ứng viên đã khóa",
        "",
        "Giữ phí 0,05% mỗi chiều. Mức trượt giá thấp chỉ là giả định chưa xác minh, không phải kết quả thực thi. Không thay đổi tiêu chí nghiệm thu.",
        "",
        "| Trượt giá | Tài sản kỳ cuối | Tài sản toàn kỳ |",
        "|---|---:|---:|",
    ]
    for slip in [2, 5, 10, 20, 50]:
        cells = []
        for period in ["holdout", "full"]:
            values = [
                r["ending_equity"]
                for r in sensitivity["results"]
                if r["slippage_bps"] == slip and r["window"] == period
            ]
            cells.append(
                f"{min(values):.2f}–{max(values):.2f}"
                if all(v is not None for v in values)
                else "Chưa xác định"
            )
        md.append(f"| {slip} bps | {' | '.join(cells)} |")
    md += [
        "",
        "## Quy tắc và giới hạn",
        "",
        s["protocol"]["rules"],
        "",
        s["protocol"]["selection"],
        "",
        s["protocol"]["gate"],
        "",
        s["protocol"]["limitations"],
        "",
        "Tín hiệu mới dùng nến giá đến hết 23/09. Lịch sử đã được xem trước, không có tuyên bố holdout hoàn toàn độc lập. Khoảng ước lượng PnL theo cụm 7 ngày vẫn chứa 0; chưa đủ bằng chứng lợi thế. Nguồn dữ liệu và checksum lưu trong cache/data_evidence.json; danh sách ứng viên và lựa chọn trước kỳ cuối nằm ở shortlist_lock.json và primary_lock.json. Cấu hình thật giữ nguyên.",
        "",
        "## Nguồn tham khảo",
        "",
        "- [Momentum tiền mã hóa — Liu & Tsyvinski](https://www.nber.org/papers/w24877)",
        "- [Các yếu tố rủi ro tiền mã hóa](https://www.nber.org/papers/w25882)",
        "- [Xác suất khớp quá mức backtest](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)",
        "- [Funding Binance](https://www.binance.com/en/support/faq/detail/360033525031)",
        "",
        "Các tài liệu cung cấp giả thuyết/phương pháp; không chứng minh các cấu hình trong báo cáo có thể tạo lợi nhuận tương lai.",
    ]
    (OUT / "report.md").write_text("\n".join(md), encoding="utf-8")
    print(OUT / "dashboard.html")


if __name__ == "__main__":
    main()
