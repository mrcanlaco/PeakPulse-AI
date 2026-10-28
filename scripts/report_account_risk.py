"""Render an offline, visibly exploratory risk comparison without changing live UI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from plotly.offline import get_plotlyjs


def render(folder):
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    rows = summary["results"]
    curves = {}
    for row in rows:
        if row["window"] != "full":
            continue
        run = json.loads(
            (folder / "runs" / f"{row['id']}.json").read_text(encoding="utf-8")
        )
        frame = pd.DataFrame(run["curve"])
        if frame.empty:
            curves[row["id"]] = dict(x=[], y=[])
            continue
        # Keep each hourly low/high, first/last and every pause transition.
        # This keeps the drawdown excursions while reducing browser payload.
        groups = frame.groupby(frame["at"] // 3600000)
        selected = set(groups.equity.idxmin()) | set(groups.equity.idxmax())
        selected |= {0, len(frame) - 1}
        selected |= set(frame.index[frame.paused.ne(frame.paused.shift())])
        thin = frame.loc[sorted(selected)]
        curves[row["id"]] = dict(x=thin["at"].tolist(), y=thin.equity.tolist())
    failures = summary.get("data_failures", {})
    regression = summary["baseline_regression"]
    payload = json.dumps(
        dict(rows=rows, curves=curves, failures=failures),
        ensure_ascii=False,
        allow_nan=False,
    ).replace("</", "<\\/")
    html = """<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Đảo Vàng · So sánh quản lý lỗ</title>
<style>
:root{font-family:Segoe UI,Arial,sans-serif;color:#e2e8f0;background:#091322}body{margin:0;padding:28px;max-width:1600px;margin:auto}h1{font-size:30px;letter-spacing:-.8px;margin:8px 0}p{line-height:1.6;color:#bac9dc}a{color:#77d7ff}.eyebrow{color:#5eead4;font-size:12px;letter-spacing:2px;font-weight:700}.notice{padding:16px 20px;background:#272212;border:1px solid #866326;border-radius:12px;color:#f6d58b;line-height:1.6}.controls{display:flex;gap:20px;flex-wrap:wrap;margin:22px 0}select{background:#15263d;color:#fff;border:1px solid #36516e;border-radius:8px;padding:10px;font-size:15px;margin-left:8px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.card{background:#122237;border:1px solid #253b55;padding:18px;border-radius:12px}.card strong{display:block;font-size:24px;color:#fff;margin-top:7px}.card span{font-size:12px;color:#a8bdd4}.panel{background:#101f32;border:1px solid #263b52;border-radius:14px;margin-top:22px;padding:18px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}th{text-align:right;background:#182b42;color:#a9c4e0}td,th{padding:12px 10px;border-bottom:1px solid #28394c}td{text-align:right}td:first-child,th:first-child{text-align:left}tr:hover{background:#1b314a}.good{color:#69e9c1}.bad{color:#ff8f93}.muted{color:#9eb1c7}h2{font-size:18px;margin:4px 0 16px}.foot{font-size:13px;color:#a6bad1}#chart{height:490px}.tag{background:#2b3549;padding:4px 9px;border-radius:8px;font-size:12px}.details{font-size:13px;line-height:1.7}button{cursor:pointer}@media(max-width:750px){body{padding:14px}.cards{grid-template-columns:repeat(2,1fr)}h1{font-size:25px}}
</style>
<div class="eyebrow">ĐẢO VÀNG / NGHIÊN CỨU RỦI RO</div><h1>Giữ được vốn có tạo ra lợi nhuận?</h1>
<p>24/06–24/09/2026 · 500 USDT · Short Cross x5 · 12 phương án × 3 giới hạn vị thế × 2 mức chi phí</p>
<div class="notice"><b>Kết quả thăm dò — chưa đủ điều kiện chạy tiền thật.</b> Tín hiệu chỉ được dựng đến 07/09; phần sau chỉ theo dõi lệnh còn mở. Model huấn luyện trùng một phần kỳ. Số liệu không chứng minh lợi nhuận ngoài mẫu. Không thay đổi cấu hình tài khoản thật.</div>
<div class="controls"><label>Tối đa<select id="cap"><option value="1">1 vị thế</option><option value="3">3 vị thế</option><option value="5" selected>5 vị thế</option></select></label><label>Chi phí<select id="cost"><option value="base">Phí 0,05% · Trượt giá 0,20%</option><option value="stress">Phí 0,10% · Trượt giá 0,50%</option></select></label><a href="comparison.csv">Tải bảng CSV</a> <a href="summary.json">Dữ liệu đối chiếu</a></div>
<div class="cards" id="cards"></div><p id="verdict"></p>
<div class="panel"><h2>Đường tài sản gồm cả lãi/lỗ chưa chốt</h2><div id="chart"></div><p class="foot">Bấm tên phương án để ẩn/hiện. Đường dừng khi thiếu dữ liệu hoặc chạm ký quỹ duy trì giả định, không kéo ngang giả tạo đến cuối kỳ. Phương án chủ động đóng hết và khóa mở mới có thể giữ đường tài sản ngang thực sự.</p></div>
<div class="panel"><h2>So sánh trên tài khoản liên tục</h2><div class="scroll"><table><thead><tr><th>Phương án</th><th>Tài sản cuối*</th><th>Lãi/lỗ*</th><th>Giảm từ đỉnh</th><th>Vào / đóng / mở</th><th>Thắng lệnh đóng</th><th>Lệnh đóng kém nhất</th><th>Giữ lâu nhất</th><th>Phí</th><th>Funding</th><th>Trạng thái</th></tr></thead><tbody id="main"></tbody></table></div><p class="foot">* Số cuối kỳ có điều kiện trên tập tín hiệu quan sát được; không phải lợi nhuận hoàn chỉnh của chiến lược cả ba tháng. “—” nghĩa là chưa xác định, không phải bằng 0. Vị thế còn mở luôn được định giá trong tài sản.</p></div>
<div class="panel"><h2>Độ nhạy theo giai đoạn · Chi phí cơ sở</h2><p class="foot">Mỗi cửa sổ bắt đầu lại từ 500 USDT và không mang vị thế sang. Không cộng ba cột để thay kết quả tài khoản liên tục; đây không phải kiểm định ngoài mẫu.</p><div class="scroll"><table><thead><tr><th>Phương án</th><th>24/06–24/07</th><th>24/07–24/08</th><th>24/08–08/09</th><th>Số giai đoạn lãi</th></tr></thead><tbody id="windows"></tbody></table></div></div>
<div class="panel details"><h2>Cách đọc kết quả</h2><p>Cắt lỗ được quan sát tại đóng nến Mark 5 phút; mua đóng tại giá mở nến giao dịch kế tiếp cộng trượt giá. Giá nhảy có thể gây lỗ vượt ngưỡng. TP chỉ là giả định khớp khi giá đóng nến đi qua giá mục tiêu, chưa kiểm tra hàng chờ/khớp từng phần. Chưa kiểm tra thanh lý và stop bên trong mỗi nến. Mức giảm trên 100% là do mẫu 5 phút vượt ngưỡng giả định, không xác nhận tài khoản thật bị âm.</p><p>Ngưỡng ký quỹ duy trì dùng giả định 1%; bộ lọc sàn và danh sách coin chưa theo từng thời điểm. Tất cả phương án vẫn khóa mở mới khi giảm 20%. Phương án đóng danh mục 10%/20% giữ khóa đến hết kỳ. Giảm nửa vốn tương ứng 2,5 USDT ký quỹ dự kiến, không tự tăng lên khi thiếu mức tối thiểu. Không loại riêng AKE khỏi tín hiệu.</p><p id="audit"></p></div>
<script>__PLOTLY__</script><script>
const data=__DATA__;const fmt=(v,n=2)=>v===null||v===undefined?'—':v.toLocaleString('vi-VN',{minimumFractionDigits:n,maximumFractionDigits:n});
const signed=v=>v===null?'—':(v>0?'+':'')+fmt(v);const cls=v=>v===null?'muted':v>=0?'good':'bad';
function update(){const cap=+document.getElementById('cap').value,cost=document.getElementById('cost').value;const rows=data.rows.filter(r=>r.window==='full'&&r.cap===cap&&r.cost===cost);const complete=rows.filter(r=>r.ending_equity!==null);const profitable=complete.filter(r=>r.pnl>0);const best=complete.reduce((a,b)=>!a||b.ending_equity>a.ending_equity?b:a,null);
document.getElementById('cards').innerHTML=[['Phương án có số cuối kỳ',complete.length+' / 12'],['Phương án cuối kỳ có lãi',profitable.length+' / 12'],['Tài sản cao nhất trong mẫu',best?fmt(best.ending_equity)+' USDT':'—'],['Giảm từ đỉnh của phương án đó',best?fmt(best.max_drawdown*100)+'%':'—']].map(([a,b])=>`<div class="card"><span>${a}</span><strong>${b}</strong></div>`).join('');
document.getElementById('verdict').textContent=best&&best.pnl>0?'Trường hợp lãi cao nhất chỉ vào '+best.entries+' lệnh, còn '+best.open_count+' lệnh mở; thời gian giữ lâu nhất '+fmt(best.max_hold_days,1)+' ngày. Không xem lãi nhỏ khi bị giữ vị thế quá lâu là bằng chứng chiến lược tốt hơn.':'Không phương án nào có số cuối kỳ vượt vốn 500 USDT ở lựa chọn này. Giảm thiệt hại chưa đủ để xác nhận lợi thế giao dịch.';
document.getElementById('main').innerHTML=rows.map(r=>`<tr><td>${r.label}</td><td>${fmt(r.ending_equity)}</td><td class="${cls(r.pnl)}">${signed(r.pnl)}</td><td>${fmt(r.max_drawdown*100)}%</td><td>${r.entries} / ${r.exits} / ${r.open_count}</td><td>${r.win_rate===null?'—':fmt(r.win_rate*100,1)+'%'}</td><td class="${cls(r.worst_closed_net)}">${signed(r.worst_closed_net)}</td><td>${fmt(r.max_hold_days,1)} ngày</td><td>${fmt(r.fees)}</td><td class="${cls(r.funding)}">${signed(r.funding)}</td><td>${r.stop_event?'Chạm MMR giả định':r.errors.length?'Lỗi dữ liệu':r.paused?'Đã khóa mở mới':'Hết kỳ quan sát'}</td></tr>`).join('');
document.getElementById('windows').innerHTML=rows.map(r=>{let w=['w1','w2','w3'].map(k=>data.rows.find(x=>x.window===k&&x.cap===cap&&x.cost==='base'&&x.policy_id===r.policy_id));return `<tr><td>${r.label}</td>${w.map(x=>`<td class="${cls(x?.pnl??null)}">${signed(x?.pnl??null)}</td>`).join('')}<td>${w.filter(x=>x&&x.pnl!==null&&x.pnl>0).length} / 3</td></tr>`}).join('');
let traces=rows.map(r=>{const c=data.curves[r.id];return {x:c.x,y:c.y,type:'scatter',mode:'lines',name:r.label,line:{width:r.policy_id==='baseline'?3:1.5},hovertemplate:'%{x|%d/%m %H:%M UTC}<br>%{y:.2f} USDT<extra>%{fullData.name}</extra>'}});
Plotly.react('chart',traces,{paper_bgcolor:'#101f32',plot_bgcolor:'#101f32',font:{color:'#bccde0'},margin:{l:60,r:15,t:15,b:100},legend:{orientation:'h',y:-.18,font:{size:11}},xaxis:{type:'date',gridcolor:'#26374c'},yaxis:{title:'USDT',gridcolor:'#26374c'},shapes:[{type:'line',xref:'paper',x0:0,x1:1,y0:500,y1:500,line:{color:'#8294af',dash:'dot',width:1}}]},{responsive:true,displaylogo:false});
}
document.getElementById('audit').textContent='Lỗi tải bổ sung: '+Object.keys(data.failures).length+'. Có kiểm tra tái lập ba cấu hình gốc và lưu checksum đầu vào. Các phương án được định trước khi chạy so sánh; kết quả vẫn mang thiên lệch do nghiên cứu trên dữ liệu đã biết.';
document.getElementById('cap').onchange=update;document.getElementById('cost').onchange=update;update();
</script></html>"""
    (folder / "dashboard.html").write_text(
        html.replace("__PLOTLY__", get_plotlyjs()).replace("__DATA__", payload),
        encoding="utf-8",
    )
    base = [r for r in rows if r["window"] == "full" and r["cost"] == "base"]
    lines = [
        "# So sánh quản lý lỗ Đảo Vàng — 24/09/2026",
        "",
        "**Thăm dò, chưa đủ điều kiện live.** 500 USDT, Short Cross x5; cùng 165 tín hiệu dựng lại. Khoảng 24/06–24/09; dữ liệu tín hiệu dừng 07/09, sau đó chỉ quản lý lệnh mở. Model huấn luyện trùng một phần kỳ. MMR giả định 1%; chưa mô phỏng intrabar, hàng chờ hoặc khớp từng phần.",
        "",
        "Phí cơ sở 0,05% mỗi chiều; trượt giá thị trường 0,20%. Stress phí 0,10%, trượt giá 0,50%. Mọi lệnh đang mở được định giá theo Mark. Stop quan sát mỗi 5 phút, khớp giá mở nến kế tiếp cộng trượt giá; có thể vượt mức lỗ đặt trước.",
        "",
    ]

    def f(value):
        return "Chưa xác định" if value is None else f"{value:.2f}"

    for cap in (1, 3, 5):
        lines += [
            f"## Tối đa {cap} vị thế",
            "",
            "| Phương án | Tài sản cuối* | PnL* | DD % | Vào/đóng/mở | PnL stress* |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for r in base:
            if r["cap"] != cap:
                continue
            stress = next(
                x
                for x in rows
                if x["window"] == "full"
                and x["cost"] == "stress"
                and x["cap"] == cap
                and x["policy_id"] == r["policy_id"]
            )
            lines.append(
                f"| {r['label']} | {f(r['ending_equity'])} | {f(r['pnl'])} | {100 * r['max_drawdown']:.2f} | {r['entries']}/{r['exits']}/{r['open_count']} | {f(stress['pnl'])} |"
            )
        lines.append("")
    lines += [
        "* Có điều kiện trên tập tín hiệu quan sát được, không phải lợi nhuận hoàn chỉnh của chiến lược ba tháng.",
        "",
        "## Kiểm tra dữ liệu và tái lập",
        "",
        f"Lỗi tải bổ sung: {len(failures)}. Tái lập cấu hình gốc: {json.dumps(regression)}.",
        "",
        "Các cửa sổ w1/w2/w3 trong comparison.csv bắt đầu lại từ 500 USDT, không mang vị thế sang. Không cộng các cửa sổ hoặc gọi đây là OOS. Không chọn thông số này để chạy live nếu chưa có kiểm định mới độc lập.",
        "",
        "Đọc docs/ACCOUNT_RISK_COMPARISON_20260924.md và protocol.json để xem toàn bộ thiết kế, giả định và checksum.",
    ]
    (folder / "report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "folder",
        type=Path,
        nargs="?",
        default=Path("artifacts/account_risk_comparison_20260924"),
    )
    render(parser.parse_args().folder)
