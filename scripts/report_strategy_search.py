"""Publish staged-search results with selection and execution uncertainty visible."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

import pandas as pd
from plotly.offline import get_plotlyjs

ROOT = Path(__file__).resolve().parents[1]


def label(spec):
    tp = {
        "fixed0_5": "0,5 USDT",
        "fixed1": "1 USDT",
        "fixed2": "2 USDT",
        "atr2": "2 ATR",
    }[spec["tp"]]
    entry = {
        "original": "tín hiệu gốc",
        "down_bar": "nến đã giảm",
        "down_bar_nonnegative_funding": "nến giảm + funding không âm",
    }[spec["entry"]]
    return f"TP {tp} · {'không SL' if spec['loss'] is None else 'SL ' + str(spec['loss']) + ' USDT'} · {str(spec['hours']) + 'h' if spec['hours'] else 'không hạn giữ'} · {spec['cap']} vị thế · {entry}"


def main():
    out = ROOT / "artifacts/account_strategy_search_20260924"
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    development = json.loads(
        (out / "development_summary.json").read_text(encoding="utf-8")
    )
    finalists = summary["finalists"]
    candidates = [r for r in finalists if not r["spec"]["control"]]
    chosen = candidates[0] if candidates else None
    definitions = summary["protocol"]["variants"]
    names = {s["id"]: label(s) for s in definitions}
    rows = summary["results"]
    curves = {}
    for row in rows:
        if row["window"] != "full":
            continue
        frame = pd.read_parquet(out / "runs" / f"{row['id']}_equity.parquet")
        groups = frame.groupby(frame["at"] // 3600000)
        indices = sorted(
            set(groups.equity.idxmin())
            | set(groups.equity.idxmax())
            | {0, len(frame) - 1}
        )
        thin = frame.loc[indices]
        curves[row["id"]] = dict(x=thin["at"].tolist(), y=thin.equity.tolist())
    payload = json.dumps(
        dict(
            finalists=finalists,
            rows=[r for r in rows if r["window"] != "development"],
            names=names,
            curves=curves,
            default=chosen["strategy_id"] if chosen else finalists[0]["strategy_id"],
        ),
        ensure_ascii=False,
        allow_nan=False,
    ).replace("</", "<\\/")

    def money(v):
        return "Chưa xác định" if v is None else f"{v:.2f}"

    def interval(r):
        return (
            "Chưa xác định"
            if not r["complete"]
            else f"{500 + r['worst_pnl']:.2f}–{500 + r['best_pnl']:.2f}"
        )

    dev_sorted = sorted(
        development,
        key=lambda r: (
            not r["complete"],
            -(r["worst_pnl"] if r["worst_pnl"] is not None else -1e9),
        ),
    )
    grid = (
        "<table><thead><tr><th>Phương án</th><th>Nhóm</th><th>PnL xấu nhất giai đoạn đầu</th><th>DD lớn nhất</th><th>Ít nhất số lệnh đóng</th></tr></thead><tbody>"
        + "".join(
            f"<tr><td>{escape(names[r['strategy_id']])}</td><td>{'Đối chứng' if r['spec']['control'] else 'Tổ hợp mới'}</td><td>{money(r['worst_pnl'])}</td><td>{100 * r['worst_dd']:.2f}%</td><td>{r['min_closed']}</td></tr>"
            for r in dev_sorted
        )
        + "</tbody></table>"
    )
    options = "".join(
        f'<option value="{r["strategy_id"]}">{escape(names[r["strategy_id"]])}</option>'
        for r in finalists
    )
    html = """<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Tìm chiến lược</title>
<style>body{font-family:Segoe UI,Arial;background:#0b1525;color:#e2e8f0;padding:25px;max-width:1550px;margin:auto}h1{font-size:30px}p{line-height:1.65;color:#b9c9df}h2{font-size:19px}.notice{background:#342021;border:1px solid #9b5554;color:#ffd0c5;padding:18px;border-radius:12px;line-height:1.7}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}.card{padding:18px;border:1px solid #30465f;border-radius:12px;background:#13243a}.card strong{display:block;font-size:27px;margin-top:8px}.card span{font-size:13px;color:#aac0d8}.panel{border:1px solid #2d415b;background:#111f33;border-radius:13px;margin:20px 0;padding:17px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}td,th{padding:12px 10px;text-align:right;border-bottom:1px solid #2d415b}td:first-child,th:first-child{text-align:left}th{color:#9bbbd9}select{padding:10px;background:#1a2d46;color:#fff;border-radius:8px;border:1px solid #49617d;max-width:100%}a{color:#7dd3fc}.pos{color:#65e6bf}.neg{color:#ff9393}.foot{font-size:13px;color:#adbed4}#chart{height:450px}.eyebrow{color:#67e8d1;font-size:12px;letter-spacing:2px;font-weight:bold}@media(max-width:750px){.cards{grid-template-columns:1fr 1fr}body{padding:12px}}</style>
<div class="eyebrow">ĐẢO VÀNG / TÌM VÀ KIỂM TRA CHIẾN LƯỢC</div><h1>Có phương án nào giữ được lợi thế qua thời gian?</h1>
<p>500 USDT · Cross x5 · Giữ toàn bộ coin, có AKE · Mỗi coin một vị thế · Không DCA</p>
<div class="notice"><b>Chưa có ứng viên vượt qua tiêu chí nghiên cứu đặt trước.</b> Những phương án tốt ở giai đoạn đầu đều có trường hợp lỗ ở giai đoạn sau. Chưa có chiến lược đủ bằng chứng chạy live. Không sửa cấu hình tài khoản thật.</div>
<div class="cards"><div class="card"><span>Cấu hình đã thử</span><strong>148</strong></div><div class="card"><span>Ứng viên khóa trước kiểm tra sau</span><strong>8</strong></div><div class="card"><span>Lượt mô phỏng và đối soát</span><strong>760</strong></div><div class="card"><span>Ứng viên đạt tiêu chí</span><strong>0 / 8</strong></div></div>
<div class="panel"><h2>8 ứng viên và 4 cấu hình đối chứng</h2><p class="foot">Tài sản bắt đầu là 500 USDT ở mỗi giai đoạn. Khoảng hiển thị là kết quả của 4 giả định khớp/chi phí, <b>không phải khoảng tin cậy</b>. Các đối chứng giúp so sánh, không nằm trong nhóm được chọn.</p><div class="scroll"><table><thead><tr><th>Phương án</th><th>Nhóm</th><th>Tài sản giai đoạn sau</th><th>Tài sản toàn kỳ</th><th>DD toàn kỳ lớn nhất</th><th>Lệnh đóng giai đoạn sau (ít nhất)</th></tr></thead><tbody id="ranking"></tbody></table></div></div>
<div class="panel"><h2>Xem từng phương án</h2><label>Phương án <select id="strategy">__OPTIONS__</select></label><p id="policy"></p><div id="chart"></div><p class="foot">Đường ngang 500 USDT là đối chứng giữ tiền trong mô phỏng, không tính lãi tiền gửi. Các đường khác là tài khoản liên tục 24/06–24/09. Đường dừng khi mô phỏng mất điều kiện tiếp tục.</p><div class="scroll"><table><thead><tr><th>Khớp / chi phí</th><th>Tài sản cuối</th><th>PnL</th><th>DD</th><th>Vào / đóng / còn mở</th><th>Phí</th><th>Funding</th></tr></thead><tbody id="detail"></tbody></table></div></div>
<div class="panel"><h2>Kiểm tra ba đoạn của giai đoạn sau</h2><p class="foot">Bắt đầu lại từ 500 USDT ở mỗi đoạn, dùng phí cơ sở. Không cộng các cột để thay tài khoản liên tục.</p><div class="scroll"><table><thead><tr><th>Giả định khớp</th><th>PnL 29/07–12/08</th><th>PnL 12/08–26/08</th><th>PnL 26/08–08/09</th></tr></thead><tbody id="slices"></tbody></table></div></div>
<div class="panel"><h2>Cách chọn ứng viên và giới hạn</h2><p>Tìm trên 24/06–29/07: 144 tổ hợp và 4 đối chứng. Xét kết quả xấu nhất trong 4 trường hợp: giá đóng nến hoặc chạm TP trong nến, phí 0,05%/0,10% mỗi chiều, trượt giá 0,20%/0,50%. Chỉ chọn tổ hợp có đủ kết quả, DD dưới 20% và ít nhất 10 lệnh đóng trong từng trường hợp. Khóa tối đa 8 kết quả giao dịch khác nhau trước khi chạy 29/07–08/09.</p><p>Tổ hợp mới gồm TP 0,5/1/2 USDT hoặc 2 ATR; cắt lỗ 2,5/5 USDT; giữ tối đa 24/72 giờ; 1/3/5 vị thế; vào theo tín hiệu gốc, nến đã giảm, hoặc nến giảm kèm funding gần nhất không âm. Tất cả tổ hợp mới đóng danh mục và khóa mở mới khi giảm 10%; đối chứng giữ quy tắc khóa mở mới 20%.</p><p>Tiêu chí nghiên cứu: cả 4 trường hợp giai đoạn sau đều lãi, DD dưới 20%, ít nhất 20 lệnh đóng mỗi trường hợp; cả 4 trường hợp toàn kỳ cũng lãi và DD dưới 20%. Đạt tiêu chí này vẫn chưa đồng nghĩa đủ điều kiện live.</p><p>Dữ liệu đã được xem ở các nghiên cứu trước. Model huấn luyện đến 28/07, đóng băng 06/09; không có tập ngoài mẫu chưa từng đụng đến, không có tuyên bố độ tin cậy đã điều chỉnh việc tìm nhiều tham số. Tín hiệu chỉ đến hết 07/09; phần sau quản lý lệnh cũ. MMR giả định 1%, bộ lọc sàn chưa theo từng thời điểm.</p><p>Giả định chạm TP không chứng minh lệnh đã khớp. Các lệnh cắt lỗ chỉ quan sát theo Mark 5 phút và khớp giá mở nến kế tiếp cộng trượt giá; không bảo đảm mức lỗ chính xác. Khi đồng thời có tín hiệu rủi ro và chạm TP, mô phỏng ưu tiên xử lý rủi ro, chưa biết thứ tự trong nến.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">Toàn bộ số đo</a> · <a href="shortlist_lock.json">Danh sách khóa trước kiểm tra sau</a></p></div>
<details class="panel"><summary>Xem toàn bộ 148 phương án ở giai đoạn tìm kiếm</summary><div class="scroll">__GRID__</div></details>
<script>__PLOTLY__</script><script>
const D=__DATA__;const f=(x,n=2)=>x===null||x===undefined?'—':x.toLocaleString('vi-VN',{minimumFractionDigits:n,maximumFractionDigits:n});const sg=x=>x===null?'—':(x>0?'+':'')+f(x);const cl=x=>x===null?'':x>=0?'pos':'neg';const range=r=>r.complete?f(500+r.worst_pnl)+'–'+f(500+r.best_pnl):'Chưa xác định';const caseName=r=>(r.fill==='close'?'Đóng nến':'Chạm giá')+' / '+(r.cost==='base'?'cơ sở':'chi phí cao');
document.getElementById('ranking').innerHTML=D.finalists.map(r=>`<tr><td>${D.names[r.strategy_id]}</td><td>${r.spec.control?'Đối chứng':'Ứng viên'}</td><td>${range(r.validation)}</td><td>${range(r.full)}</td><td>${f(r.full.worst_dd*100)}%</td><td>${r.validation.min_closed}</td></tr>`).join('');
function update(){const id=document.getElementById('strategy').value;let spec=D.finalists.find(x=>x.strategy_id===id).spec;document.getElementById('policy').textContent=spec.control?'Cấu hình đối chứng, giữ quy tắc khóa mở mới khi giảm 20%.':'Tổ hợp nghiên cứu: thêm đóng toàn bộ danh mục và khóa mở mới khi giảm 10%. Chỉ mô phỏng.';let rows=D.rows.filter(r=>r.window==='full'&&r.strategy_id===id);document.getElementById('detail').innerHTML=rows.map(r=>`<tr><td>${caseName(r)}</td><td>${f(r.ending_equity)}</td><td class="${cl(r.pnl)}">${sg(r.pnl)}</td><td>${f(100*r.max_drawdown)}%</td><td>${r.entries} / ${r.exits} / ${r.open_count}</td><td>${f(r.fees)}</td><td>${sg(r.funding)}</td></tr>`).join('');let traces=rows.map(r=>({x:D.curves[r.id].x,y:D.curves[r.id].y,name:caseName(r),type:'scatter',mode:'lines'}));Plotly.react('chart',traces,{paper_bgcolor:'#111f33',plot_bgcolor:'#111f33',font:{color:'#b9c9df'},margin:{l:55,r:15,t:10,b:80},xaxis:{type:'date',gridcolor:'#2d415b'},yaxis:{title:'USDT',gridcolor:'#2d415b'},legend:{orientation:'h',y:-.2},shapes:[{type:'line',xref:'paper',x0:0,x1:1,y0:500,y1:500,line:{color:'#c6b37f',dash:'dot',width:1}}]},{responsive:true,displaylogo:false});document.getElementById('slices').innerHTML=['close','bar_low'].map(fill=>`<tr><td>${fill==='close'?'Đóng nến':'Chạm giá'}</td>${['v1','v2','v3'].map(w=>{let r=D.rows.find(x=>x.strategy_id===id&&x.window===w&&x.fill===fill&&x.cost==='base');return `<td class="${cl(r.pnl)}">${sg(r.pnl)}</td>`}).join('')}</tr>`).join('');}
document.getElementById('strategy').value=D.default;document.getElementById('strategy').onchange=update;update();</script></html>"""
    (out / "dashboard.html").write_text(
        html.replace("__OPTIONS__", options)
        .replace("__GRID__", grid)
        .replace("__PLOTLY__", get_plotlyjs())
        .replace("__DATA__", payload),
        encoding="utf-8",
    )
    report = [
        "# Tìm chiến lược Đảo Vàng — 24/09/2026",
        "",
        "**Chưa có ứng viên đạt tiêu chí nghiên cứu. Không thay đổi cấu hình live.** 148 phương án (144 tổ hợp + 4 đối chứng), 8 ứng viên được khóa trước giai đoạn sau, 760 lượt chạy và đối soát. Giữ AKE và toàn bộ bộ coin, vốn 500 USDT, Cross x5, không DCA. Có cả phí/funding/lãi lỗ chưa chốt.",
        "",
        "Tìm ứng viên 24/06–29/07; kiểm tra 29/07–08/09; kiểm tra tài khoản liên tục 24/06–24/09. Bốn trường hợp là hai giả định khớp TP × hai mức chi phí. Các khoảng số dưới đây là độ nhạy theo giả định, không phải khoảng tin cậy.",
        "",
        "| Phương án | Tài sản giai đoạn sau | Tài sản toàn kỳ | DD toàn kỳ lớn nhất | Lệnh đóng giai đoạn sau (ít nhất) |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in finalists:
        report.append(
            f"| {names[r['strategy_id']]}{' (đối chứng)' if r['spec']['control'] else ''} | {interval(r['validation'])} | {interval(r['full'])} | {100 * r['full']['worst_dd']:.2f}% | {r['validation']['min_closed']} |"
        )
    report += [
        "",
        "## Cấu hình và tiêu chí",
        "",
        "TP cố định 0,5/1/2 USDT hoặc 2 ATR, stop lỗ 2,5/5 USDT, giữ 24/72 giờ, 1/3/5 vị thế, ba bộ lọc vào. Mọi tổ hợp mới có đóng danh mục tại mức giảm 10% và khóa mở mới đến hết kỳ; đối chứng giữ khóa mở mới 20% mà không đóng danh mục.",
        "",
        "Chọn bằng PnL xấu nhất giai đoạn đầu, chỉ xét hoàn tất 4 trường hợp, DD<20%, >=10 lệnh đóng mỗi trường hợp. Khóa 8 phương án khác nhau trước khi xem giai đoạn sau; không chọn theo lợi nhuận toàn kỳ. Tiêu chí nghiên cứu tiếp: 4 trường hợp giai đoạn sau đều lãi, DD<20%, >=20 lệnh đóng; 4 trường hợp toàn kỳ cũng đều lãi, DD<20%. Chưa phương án nào đạt.",
        "",
        "Bộ lọc nến giảm chỉ dùng hai nến đã đóng tại thời điểm tín hiệu. Funding chỉ dùng kỳ đã công bố ít nhất 60 giây trước đó và không quá 8h5m. Không đọc giá mở nến kế tiếp để quyết định lọc.",
        "",
        "## Diễn giải và giới hạn",
        "",
        "Ứng viên được giữ để nghiên cứu là TP 2 USDT, stop 5 USDT, thời hạn 72 giờ, tối đa 1 vị thế, tín hiệu gốc, đóng danh mục ở DD 10%. Đây là ứng viên ít yếu nhất ở giai đoạn sau trong nhóm đã chọn, không phải chiến lược tối ưu đã chứng minh. Nó có thể tốt hơn ở toàn kỳ nhưng đổi dấu PnL khi thay giả định khớp/chi phí ở giai đoạn sau. Đối chứng giữ tiền là 500 USDT, PnL=0 và DD=0 trong mô phỏng.",
        "",
        "Giai đoạn sau cũng đã được xem ở nghiên cứu trước; model huấn luyện đến 28/07 và đóng băng 06/09. Không gọi đây là OOS chưa từng đụng đến hoặc độ tin cậy đã điều chỉnh tìm nhiều tham số. Số tín hiệu chỉ đến 07/09; phần còn lại quản lý lệnh cũ. MMR giả định 1%, thiếu quy tắc sàn lịch sử; TP chạm giá chưa có xác nhận hàng chờ/khớp từng phần. Lệnh stop quan sát mỗi 5 phút nên có thể vượt ngưỡng.",
        "",
        "shortlist_lock.json lưu thứ hạng phát triển và thời điểm khóa trước khi chạy kiểm tra. protocol.json lưu toàn bộ tham số và checksum. comparison.csv lưu cả kết quả kém; các sổ lệnh và đường tài sản của ứng viên/đối chứng được lưu trong runs.",
    ]
    (out / "report.md").write_text("\n".join(report), encoding="utf-8")


if __name__ == "__main__":
    main()
