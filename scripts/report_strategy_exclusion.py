"""Paired retrospective exclusion report; never equate exclusions with manual exits."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

import pandas as pd
from plotly.offline import get_plotlyjs
from report_strategy_search import label

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "artifacts/account_strategy_without_ake_20260924"
    original = ROOT / "artifacts/account_strategy_search_20260924"
    after = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    before = json.loads((original / "summary.json").read_text(encoding="utf-8"))
    assert after["shortlist"] == before["shortlist"]
    assert after["protocol"]["excluded_symbols"] == ["AKEUSDT"]
    rows, curves, names = [], {}, {}
    for directory, summary, scenario in [
        (original, before, "Giữ AKE"),
        (out, after, "Bỏ AKE"),
    ]:
        for r in summary["results"]:
            if r["window"] != "full":
                continue
            key = scenario + r["id"]
            frame = pd.read_parquet(directory / "runs" / f"{r['id']}_equity.parquet")
            groups = frame.groupby(frame["at"] // 3600000)
            indices = sorted(
                set(groups.equity.idxmin())
                | set(groups.equity.idxmax())
                | {0, len(frame) - 1}
            )
            frame = frame.loc[indices]
            curves[key] = dict(x=frame["at"].tolist(), y=frame.equity.tolist())
            rows.append(dict(r, scenario=scenario, key=key))

    def interval(r):
        return (
            f"{500 + r['worst_pnl']:.2f}–{500 + r['best_pnl']:.2f}"
            if r["complete"]
            else "Chưa xác định"
        )

    table = []
    md = [
        "# Đảo Vàng — Giả định loại AKE",
        "",
        "168 lượt chạy mới, giữ nguyên 8 ứng viên và 4 đối chứng đã chọn. Loại 7 tín hiệu AKEUSDT, còn 158 tín hiệu; không tìm lại tham số sau khi loại coin. Vốn 500 USDT, Cross x5, khoảng 25 USDT danh nghĩa mỗi vị thế.",
        "",
        "**Đây là loại coin hồi cứu, không phải mô phỏng xử lý bằng tay.** Không phát sinh lãi/lỗ hoặc vốn cam kết từ AKE; mọi tín hiệu khác được chạy lại theo thời gian để phản ánh chỗ trống được giải phóng.",
        "",
        "Khoảng số là 4 giả định khớp TP/chi phí, không phải khoảng tin cậy. Toàn kỳ 24/06–24/09/2026; kỳ kiểm tra riêng 29/07–08/09 bắt đầu lại với 500 USDT.",
        "",
        "| Phương án | Giữ AKE, toàn kỳ | Bỏ AKE, toàn kỳ | DD lớn nhất khi bỏ AKE | Bỏ AKE, kỳ kiểm tra riêng |",
        "|---|---:|---:|---:|---:|",
    ]
    for f in after["finalists"]:
        ident = f["strategy_id"]
        names[ident] = label(f["spec"])
        b = next(x for x in before["finalists"] if x["strategy_id"] == ident)
        cells = [
            names[ident],
            interval(b["full"]),
            interval(f["full"]),
            f"{100 * f['full']['worst_dd']:.2f}%",
            interval(f["validation"]),
        ]
        table.append("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in cells) + "</tr>")
        md.append("| " + " | ".join(cells) + " |")
    caveat = "Không ứng viên nào đạt tiêu chí nghiên cứu (0/8). Các ứng viên có SL và giới hạn giữ vẫn có trường hợp lỗ ở kỳ kiểm tra riêng. Đối chứng không SL, tối đa 5 vị thế vẫn có DD hơn 25% sau khi bỏ AKE. Kết quả xử lý bằng tay cần tính cả thời điểm nhận diện, giá khớp, lỗ và phí thực tế; không thể xem phần đã loại là lỗ bằng 0 trong tài khoản thật."
    limits = "Tín hiệu chỉ đến hết 07/09; sau đó quản lý vị thế cũ. Lịch sử đã được xem trước, model huấn luyện đến 28/07 và đóng băng 06/09. MMR dùng giả định 1%, thiếu bộ lọc sàn theo thời điểm. TP chạm giá chưa chứng minh khớp; stop quan sát mỗi 5 phút có thể vượt ngưỡng. Cấu hình thật không thay đổi, live chưa bật."
    md += [
        "",
        caveat,
        "",
        limits,
        "",
        "Các tổ hợp mới có đóng toàn bộ danh mục và khóa mở mới tại DD 10%; đối chứng chỉ dừng mở mới tại DD 20%, không đóng vị thế. Số dư cuối kỳ đã tính funding, phí và định giá vị thế còn mở.",
    ]
    (out / "report.md").write_text("\n".join(md), encoding="utf-8")
    payload = json.dumps(
        dict(rows=rows, curves=curves, names=names), ensure_ascii=False, allow_nan=False
    ).replace("</", "<\\/")
    options = "".join(
        f'<option value="{k}">{escape(v)}</option>' for k, v in names.items()
    )
    html = """<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Nếu loại AKE</title>
<style>body{background:#0b1525;color:#e2e8f0;font:15px Segoe UI,Arial;max-width:1500px;margin:auto;padding:28px}h1{font-size:30px}p{line-height:1.7;color:#b9c9df}.note{background:#322325;border:1px solid #855353;padding:16px;border-radius:12px}.panel{background:#111f33;border:1px solid #30465f;border-radius:12px;padding:18px;margin:20px 0}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}th,td{padding:12px;border-bottom:1px solid #30465f;text-align:right}th:first-child,td:first-child{text-align:left}select{background:#1a2d46;color:#fff;padding:10px;max-width:100%}#chart{height:430px}a{color:#7dd3fc}</style>
<h1>Nếu loại toàn bộ AKE thì sao?</h1><p>500 USDT · Cross x5 · 168 lượt chạy mới · 7 tín hiệu AKE bị loại · Giữ nguyên 8 ứng viên + 4 đối chứng</p>
<div class="note"><b>Loại AKE hồi cứu, chưa mô phỏng xử lý bằng tay.</b><p>__CAVEAT__</p></div>
<section class="panel"><h2>So sánh trước và sau</h2><p>Toàn kỳ 24/06–24/09/2026. Kỳ kiểm tra riêng 29/07–08/09 bắt đầu lại từ 500 USDT. Khoảng số là bốn giả định khớp/chi phí, không phải khoảng tin cậy.</p><div class="scroll"><table><thead><tr><th>Phương án</th><th>Giữ AKE, toàn kỳ</th><th>Bỏ AKE, toàn kỳ</th><th>DD lớn nhất, bỏ AKE</th><th>Bỏ AKE, kỳ kiểm tra riêng</th></tr></thead><tbody>__TABLE__</tbody></table></div></section>
<section class="panel"><h2>Đường tài sản và số lệnh</h2><label>Phương án <select id="strategy">__OPTIONS__</select></label><p>Tổ hợp có SL và hạn giữ: đóng danh mục ở DD 10%. Đối chứng không hạn giữ: dừng mở mới ở DD 20%, giữ vị thế.</p><div id="chart"></div><p>Biểu đồ dùng phí cơ sở và khớp theo giá đóng nến để so sánh cùng giả định. Đường dừng khi mô phỏng không thể tiếp tục; không suy ra số dư thật khi thanh lý.</p><div class="scroll"><table><thead><tr><th>Kịch bản</th><th>Khớp TP / chi phí</th><th>Tài sản cuối</th><th>DD</th><th>Vào / đóng / còn mở</th></tr></thead><tbody id="detail"></tbody></table></div></section>
<section class="panel"><h2>Giới hạn kết quả</h2><p>__LIMITS__</p><p>Không loại thêm coin khác theo kết quả lỗ. Muốn mô phỏng phần xử lý bằng tay, cần quy tắc nhận diện và hành động tại thời điểm quan sát.</p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">Số liệu 168 lượt chạy</a> · <a href="excluded_signals.json">7 tín hiệu đã loại</a></section>
<script>__PLOTLY__</script><script>const D=__DATA__;const f=x=>x===null?'Chưa xác định':x.toLocaleString('vi-VN',{maximumFractionDigits:2,minimumFractionDigits:2});function update(){const id=document.getElementById('strategy').value;const rows=D.rows.filter(r=>r.strategy_id===id);document.getElementById('detail').innerHTML=rows.map(r=>`<tr><td>${r.scenario}</td><td>${r.fill==='close'?'Đóng nến':'Chạm giá'} / ${r.cost==='base'?'cơ sở':'cao'}</td><td>${f(r.ending_equity)}</td><td>${f(100*r.max_drawdown)}%</td><td>${r.entries} / ${r.exits} / ${r.open_count}</td></tr>`).join('');Plotly.react('chart',rows.filter(r=>r.fill==='close'&&r.cost==='base').map(r=>({x:D.curves[r.key].x,y:D.curves[r.key].y,name:r.scenario,type:'scatter',mode:'lines'})),{paper_bgcolor:'#111f33',plot_bgcolor:'#111f33',font:{color:'#b9c9df'},margin:{l:60,r:20,t:10,b:50},xaxis:{type:'date'},yaxis:{title:'USDT'},legend:{orientation:'h'}},{responsive:true,displaylogo:false});}document.getElementById('strategy').value='fixed2_sl5_h72_n1_original';document.getElementById('strategy').onchange=update;update();</script></html>"""
    for key, value in dict(
        CAVEAT=escape(caveat),
        LIMITS=escape(limits),
        TABLE="".join(table),
        OPTIONS=options,
        PLOTLY=get_plotlyjs(),
        DATA=payload,
    ).items():
        html = html.replace(f"__{key}__", value)
    (out / "dashboard.html").write_text(html, encoding="utf-8")
    print(out / "dashboard.html")


if __name__ == "__main__":
    main()
