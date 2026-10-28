"""Compare TP policies and disclose sensitivity to assumed limit fills."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from plotly.offline import get_plotlyjs

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "artifacts/account_tp_research_20260924"
    rows, curves = [], {}
    for fill, folder in [("close", out), ("bar_low", Path(str(out) + "_touch"))]:
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        assert len(summary["results"]) == 220
        for r in summary["results"]:
            row = dict(r, fill=fill, id=fill + ":" + r["id"])
            rows.append(row)
            if r["window"] != "full":
                continue
            frame = pd.read_parquet(folder / "runs" / f"{r['id']}_equity.parquet")
            groups = frame.groupby(frame["at"] // 3600000)
            indexes = sorted(
                set(groups.equity.idxmin())
                | set(groups.equity.idxmax())
                | {0, len(frame) - 1}
            )
            short = frame.loc[indexes]
            curves[row["id"]] = dict(x=short["at"].tolist(), y=short.equity.tolist())
    data = json.dumps(
        dict(rows=rows, curves=curves), ensure_ascii=False, allow_nan=False
    ).replace("</", "<\\/")
    html = """<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Thử nghiệm TP</title>
<style>body{font-family:Segoe UI,Arial;background:#0b1525;color:#e2e8f0;padding:25px;max-width:1550px;margin:auto}h1{font-size:30px}p{line-height:1.65;color:#b9c9df}h2{font-size:19px}.notice{background:#302817;border:1px solid #8c692c;color:#f0d79f;padding:17px;border-radius:12px;line-height:1.6}.controls{display:flex;flex-wrap:wrap;gap:15px;margin:22px 0}select{padding:10px;background:#1a2d46;color:#fff;border-radius:8px;border:1px solid #49617d}.panel{border:1px solid #2d415b;background:#111f33;border-radius:13px;margin:20px 0;padding:17px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}td,th{padding:12px 10px;text-align:right;border-bottom:1px solid #2d415b}td:first-child,th:first-child{text-align:left}th{color:#9bbbd9}a{color:#7dd3fc}.pos{color:#65e6bf}.neg{color:#ff9393}.foot{font-size:13px;color:#adbed4}#chart{height:500px}.eyebrow{color:#67e8d1;font-size:12px;letter-spacing:2px;font-weight:bold}</style>
<div class="eyebrow">ĐẢO VÀNG / NGHIÊN CỨU TP</div><h1>TP nhỏ hơn có làm tài khoản tốt hơn?</h1><p>500 USDT · Cross x5 · Không stop-loss · Khóa mở mới khi giảm 20% · 11 cách đặt TP · 440 lượt mô phỏng và kiểm tra giai đoạn</p>
<div class="notice"><b>Chưa có thông số đủ điều kiện triển khai live.</b> Hai cách giả định khớp LIMIT có thể cho kết quả khác nhau rõ rệt. Chạm giá trong nến chưa chứng minh đã khớp; chưa biết thứ tự khớp, funding, thanh lý và hàng chờ. Model huấn luyện trùng một phần kỳ; loại AKE là giả định sau khi biết kết quả.</div>
<div class="controls"><label>Coin <select id="coins"><option value="all_coins">Giữ cả AKE</option><option value="no_ake">Loại toàn bộ AKE</option></select></label><label>Vị thế <select id="cap"><option value="5">Tối đa 5</option><option value="57">Không giới hạn</option></select></label><label>Khớp TP <select id="fill"><option value="close">Giá đóng nến đi qua TP</option><option value="bar_low">Giả định khớp khi chạm trong nến</option></select></label><label>Chi phí <select id="cost"><option value="base">Phí 0,05% · Trượt giá 0,20%</option><option value="stress">Phí 0,10% · Trượt giá 0,50%</option></select></label></div>
<p id="verdict"></p><div class="panel"><h2>Giá trị tài khoản, gồm lệnh còn mở</h2><div id="chart"></div><p class="foot">Bấm tên phương án để ẩn/hiện. Đường dừng khi vi phạm ký quỹ duy trì giả định hoặc không thể tính TP hợp lệ; không nối ngang giả tạo đến cuối kỳ.</p></div>
<div class="panel"><h2>So sánh toàn kỳ 24/06–24/09/2026*</h2><div class="scroll"><table><thead><tr><th>TP ròng / chính sách</th><th>Tài sản cuối</th><th>Lãi/lỗ</th><th>Giảm từ đỉnh</th><th>Vào / TP / mở</th><th>Giữ lệnh đóng (trung vị)</th><th>Giữ lâu nhất</th><th>Funding</th><th>Trạng thái</th></tr></thead><tbody id="results"></tbody></table></div></div>
<div class="panel"><h2>Độ nhạy theo giai đoạn · Chi phí cơ sở</h2><p class="foot">Mỗi cửa sổ bắt đầu lại với 500 USDT, không mang vị thế sang. Đây là so sánh giai đoạn, không phải bằng chứng ngoài mẫu; không cộng các cột để thay tài khoản liên tục.</p><div class="scroll"><table><thead><tr><th>TP</th><th>PnL 24/06–24/07</th><th>PnL 24/07–24/08</th><th>PnL 24/08–08/09</th></tr></thead><tbody id="windows"></tbody></table></div></div>
<div class="panel"><h2>Giới hạn cần đọc cùng số liệu</h2><p>* Tín hiệu chỉ được dựng đến hết 07/09; sau đó chỉ quản lý lệnh cũ. Mọi vị thế còn mở được định giá. “—” nghĩa là chưa xác định, không phải tài sản bằng 0. MMR dùng giả định 1%; mức giảm trên 100% có thể do mẫu 5 phút vượt ngưỡng, không xác nhận tài khoản thật bị âm.</p><p>Với giả định chạm giá, dùng TP đã có trước nến, không lấy funding cuối nến để thay đổi lệnh ngược về quá khứ. Funding vẫn tính đến cuối nến; thời điểm khớp và thứ tự sự kiện chưa được xác minh. Không xem đây là lợi nhuận có thể thực thi hoặc một giới hạn trên chính xác.</p><p>Mục tiêu tiền được khóa lúc vào lệnh. Funding âm tích lũy có thể khiến mục tiêu này không còn đạt được dù giá về 0; mô phỏng dừng và không giả định một lần TP để làm đẹp kết quả. Thay TP cũng có thể thay số tín hiệu đạt điều kiện, không bảo đảm cùng danh sách lệnh.</p><p><a href="report.md">Báo cáo tổng hợp</a> · <a href="combined_comparison.csv">Tải tất cả số đo</a></p></div>
<script>__PLOTLY__</script><script>
const D=__DATA__;const f=(x,n=2)=>x===null||x===undefined?'—':x.toLocaleString('vi-VN',{minimumFractionDigits:n,maximumFractionDigits:n});const sg=x=>x===null?'—':(x>0?'+':'')+f(x);const cl=x=>x===null?'':x>=0?'pos':'neg';
function update(){let coins=document.getElementById('coins').value,cap=+document.getElementById('cap').value,fill=document.getElementById('fill').value,cost=document.getElementById('cost').value;let rows=D.rows.filter(r=>r.window==='full'&&r.coins===coins&&r.cap===cap&&r.fill===fill&&r.cost===cost);let complete=rows.filter(r=>r.pnl!==null);document.getElementById('verdict').textContent=complete.length+' / 11 phương án có thể tính đến cuối kỳ; '+complete.filter(r=>r.pnl>0).length+' phương án có lãi. Kết quả phụ thuộc giả định khớp đang chọn; không tự động chọn phương án lãi cao nhất để chạy thật.';
document.getElementById('results').innerHTML=rows.map(r=>`<tr><td>${r.label}</td><td>${f(r.ending_equity)}</td><td class="${cl(r.pnl)}">${sg(r.pnl)}</td><td>${f(r.max_drawdown*100)}%</td><td>${r.entries} / ${r.tp} / ${r.open_count}</td><td>${f(r.median_closed_hours,1)} giờ</td><td>${f(r.max_hold_days,1)} ngày</td><td class="${cl(r.funding)}">${sg(r.funding)}</td><td>${r.stop_event?'Chạm MMR giả định':r.errors.some(x=>x.startsWith('tp_price_unrepresentable'))?'TP không còn khả thi':r.errors.length?'Lỗi dữ liệu':r.paused?'Đã khóa mở mới':'Hết kỳ quan sát'}</td></tr>`).join('');
document.getElementById('windows').innerHTML=rows.map(r=>`<tr><td>${r.label}</td>${['w1','w2','w3'].map(w=>{let x=D.rows.find(z=>z.window===w&&z.coins===coins&&z.cap===cap&&z.fill===fill&&z.cost==='base'&&z.policy_id===r.policy_id);return `<td class="${cl(x.pnl)}">${sg(x.pnl)}</td>`}).join('')}</tr>`).join('');
Plotly.react('chart',rows.map(r=>({x:D.curves[r.id].x,y:D.curves[r.id].y,type:'scatter',mode:'lines',name:r.label,line:{width:r.policy_id==='atr2'?3:1.4}})),{paper_bgcolor:'#111f33',plot_bgcolor:'#111f33',font:{color:'#b9c9df'},margin:{l:55,r:15,t:10,b:105},xaxis:{type:'date',gridcolor:'#2d415b'},yaxis:{title:'USDT',gridcolor:'#2d415b'},legend:{orientation:'h',y:-.2,font:{size:11}}},{responsive:true,displaylogo:false});}
['coins','cap','fill','cost'].forEach(id=>document.getElementById(id).onchange=update);update();</script></html>"""
    (out / "dashboard.html").write_text(
        html.replace("__PLOTLY__", get_plotlyjs()).replace("__DATA__", data),
        encoding="utf-8",
    )
    pd.DataFrame(rows).to_csv(out / "combined_comparison.csv", index=False)
    report = [
        "# Thử nghiệm TP Đảo Vàng — 24/09/2026",
        "",
        "11 chính sách TP × 2 giới hạn vị thế × giữ/bỏ AKE × 2 mức chi phí × 2 giả định khớp, cùng kiểm tra ba cửa sổ: 440 lượt. Vẫn 500 USDT, Cross x5, không stop-loss, khóa mở mới khi giảm 20%. Không thay đổi live.",
        "",
        "Hai giả định: close chỉ khớp khi giá đóng nến đi qua TP; bar_low giả định TP đang nằm sẵn được khớp khi giá chạm trong nến, không có xác minh hàng chờ/thứ tự sự kiện. Không giả định bar_low là kết quả có thể giao dịch thật hoặc luôn tốt hơn close.",
        "",
        "Dữ liệu tín hiệu chỉ đến 07/09, phần sau định giá/quản lý lệnh cũ. Model huấn luyện trùng một phần kỳ; loại AKE là hậu nghiệm. Ngưỡng ký quỹ duy trì giả định 1%. Mọi vị thế mở được tính vào tài sản; chưa xác định không phải bằng 0.",
        "",
    ]

    def fmt(x):
        return "Chưa xác định" if x is None else f"{x:.2f}"

    for cap in (5, 57):
        report += [
            f"## {'Tối đa 5 vị thế' if cap == 5 else 'Không giới hạn vị thế'} — tài sản cuối, phí cơ sở",
            "",
            "| TP | Giữ AKE, đóng nến | Giữ AKE, chạm giá | Bỏ AKE, đóng nến | Bỏ AKE, chạm giá |",
            "|---|---:|---:|---:|---:|",
        ]
        policies = [
            r
            for r in rows
            if r["window"] == "full"
            and r["cap"] == cap
            and r["coins"] == "all_coins"
            and r["fill"] == "close"
            and r["cost"] == "base"
        ]
        for r in policies:
            values = []
            for coins, fill in [
                ("all_coins", "close"),
                ("all_coins", "bar_low"),
                ("no_ake", "close"),
                ("no_ake", "bar_low"),
            ]:
                v = next(
                    x
                    for x in rows
                    if x["window"] == "full"
                    and x["cap"] == cap
                    and x["coins"] == coins
                    and x["fill"] == fill
                    and x["cost"] == "base"
                    and x["policy_id"] == r["policy_id"]
                )
                values.append(fmt(v["ending_equity"]))
            report.append("| " + r["label"] + " | " + " | ".join(values) + " |")
        report.append("")
    report += [
        "## Cách diễn giải",
        "",
        "TP nhỏ có thể tăng số lệnh và thay đổi vị thế nào được vào tiếp theo, nhưng không chặn lỗ ở lệnh chưa đạt TP. TP 0,5 USDT cho lệnh AKE ngày 15/07 là ví dụ phụ thuộc đường giá trong nến: giá thấp đã chạm nhưng giá đóng chưa đi qua. Do đó kết luận từ mô phỏng đóng nến cần được đọc cùng phép thử chạm giá.",
        "",
        "Khi funding âm làm giá TP cần thiết không còn dương, kết quả dừng với tp_price_unrepresentable. Không xếp những lượt này vào nhóm an toàn chỉ vì đường tài sản ngắn có DD thấp. Việc chọn thông số từ cùng dữ liệu mang thiên lệch lựa chọn, chưa đủ bằng chứng triển khai.",
        "",
        "Các file protocol.json và validation.json trong hai thư mục close/touch lưu cấu hình, checksum và đối soát. comparison.csv ghi mọi phương án; combined_comparison.csv gộp hai giả định. Không tự sửa cấu hình tài khoản thật.",
    ]
    (out / "report.md").write_text("\n".join(report), encoding="utf-8")


if __name__ == "__main__":
    main()
