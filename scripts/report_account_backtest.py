"""Publish the offline account diagnostic with visible qualification limits."""

from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def timestamp(value):
    if value is None:
        return "—"
    return pd.to_datetime(value, unit="ms", utc=True).strftime("%d/%m/%Y %H:%M UTC")


def render(folder):
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    runs = [
        json.loads((folder / f"positions_{cap}.json").read_text(encoding="utf-8"))
        for cap in (1, 3, 5)
    ]
    coverage = report["coverage"]
    rows = []
    for r in runs:
        curve = r["curve"]
        stop = r.get("stop_event")
        rows.append(
            {
                "Giới hạn vị thế": r["max_positions"],
                "Đã vào": r["entries"],
                "Đã TP": r["tp_exits"],
                "Còn mở lúc dừng": len(r["open_positions"]),
                "Tài sản cuối 3 tháng": f"{r['ending_equity']:.2f}"
                if r["ending_equity"] is not None
                else "Chưa xác định",
                "Giảm từ đỉnh (mẫu 5 phút)": f"{r['sampled_max_drawdown']:.2%}",
                "Dừng do": (
                    "Chạm ngưỡng thanh lý ước tính"
                    if stop
                    else ", ".join(r["errors"]) or "Hết kỳ"
                ),
                "Thời điểm dừng": timestamp(
                    stop["at"] if stop else curve[-1]["at"] if curve else None
                ),
                "Phí đã tính": f"{r['fees']:.4f}",
                "Funding ròng đã tính": f"{r['funding']:.4f}",
            }
        )
    table = pd.DataFrame(rows)
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.07,
        subplot_titles=(
            "Tổng tài sản gồm lãi/lỗ chưa chốt (USDT)",
            "Giảm từ đỉnh (%)",
            "Số vị thế đang mở",
        ),
    )
    colors = ["#2563eb", "#d97706", "#7c3aed"]
    for r, color in zip(runs, colors):
        frame = pd.DataFrame(r["curve"])
        if frame.empty:
            continue
        x = pd.to_datetime(frame["at"], unit="ms", utc=True)
        peaks = frame.equity.cummax().clip(lower=500)
        for row, y in [
            (1, frame.equity),
            (2, 100 * (1 - frame.equity / peaks)),
            (3, frame.positions),
        ]:
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y,
                    mode="lines",
                    name=f"Tối đa {r['max_positions']} vị thế",
                    legendgroup=str(r["max_positions"]),
                    showlegend=row == 1,
                    line=dict(color=color, width=1.6),
                ),
                row=row,
                col=1,
            )
        paused = frame[frame.paused]
        if not paused.empty:
            point = paused.iloc[0]
            fig.add_trace(
                go.Scatter(
                    x=[pd.to_datetime(point["at"], unit="ms", utc=True)],
                    y=[point.equity],
                    mode="markers",
                    marker=dict(symbol="x", size=11, color=color),
                    name=f"Khóa mở mới: {r['max_positions']} vị thế",
                    showlegend=False,
                ),
                row=1,
                col=1,
            )
    fig.add_hline(y=500, line_dash="dot", line_color="#94a3b8", row=1, col=1)
    fig.add_hline(y=20, line_dash="dash", line_color="#dc2626", row=2, col=1)
    fig.update_layout(
        template="plotly_white",
        height=870,
        margin=dict(l=65, r=30, t=65, b=45),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.08),
    )
    fig.update_xaxes(range=report["window"])
    chart = fig.to_html(
        full_html=False,
        include_plotlyjs=True,
        config={"displaylogo": False, "responsive": True},
    )
    note = (
        "Đây là mô phỏng sơ bộ trên tín hiệu dựng lại. Không phải kết quả giao dịch thật hoặc "
        "bằng chứng lợi nhuận ngoài mẫu. Đường biểu đồ dừng khi dữ liệu hoặc giả định thanh lý "
        "không cho phép tiếp tục; không kéo ngang đến cuối kỳ và không coi số dư thiếu là 0."
    )
    limits = [
        f"Model hiện tại huấn luyện đến {coverage['model']['train_cutoff']}, đóng băng {coverage['model']['freeze_time']}; trùng một phần kỳ kiểm tra.",
        f"Có {coverage['candidate_rows']:,} dòng ứng viên; {coverage['usable_candidate_rows']:,} đủ dữ liệu theo bộ kiểm tra; {coverage['signal_events']} sự kiện được chọn.",
        f"Nguồn metrics gốc kết thúc {coverage['metrics']['max']}. Những ngày thiếu dữ liệu không được xem là không có tín hiệu.",
        "Bộ dựng tín hiệu theo coin tăng giá và ngưỡng model chưa tái hiện đầy đủ bộ lọc pump, danh sách coin được giữ lại và lịch sử episode của scanner.",
        "Funding lấy từ lịch sử Binance có phân trang và lưu checksum. Phí giả định 0,05% mỗi chiều, trượt giá vào lệnh 0,20%; chưa xác nhận bậc phí tài khoản.",
        (
            "Định giá dùng Mark Price lịch sử của Binance."
            if coverage.get("mark_prices_used")
            else "Định giá tạm dùng giá đóng nến giao dịch."
        )
        + " TP giả định khớp khi giá đóng nến giao dịch đi qua mức LIMIT. Chưa mô phỏng hàng chờ/khớp từng phần bằng L2.",
        "Ngưỡng ký quỹ duy trì 1% là giả định kiểm tra. Chạm ngưỡng này làm dừng mô phỏng; không xác nhận giá thanh lý hoặc tài sản sau thanh lý thực tế tại Binance.",
        "Dùng quy tắc khối lượng/giá từ snapshot sàn hiện có. Danh sách coin theo từng thời điểm, dữ liệu hủy niêm yết và bậc ký quỹ lịch sử chưa được xác minh đầy đủ.",
        "Mẫu 5 phút có thể nhảy qua ngưỡng thanh lý, tạo mức giảm tính toán vượt 100%. Đây không phải xác nhận tài khoản thực bị âm; mô phỏng dừng và để trống tài sản cuối kỳ.",
    ]
    warehouse_audit = folder.parent / "warehouse_catalog_audit.json"
    sample_audit = folder.parent / "warehouse_sample_comparison.json"
    if warehouse_audit.exists() and sample_audit.exists():
        catalog = json.loads(warehouse_audit.read_text(encoding="utf-8-sig"))
        samples = json.loads(sample_audit.read_text(encoding="utf-8"))
        limits.insert(
            2,
            f"Đã tra danh mục kho Tardis/Drive của người dùng: {catalog['symbols']} mã xuất hiện trong kỳ, dữ liệu gốc đến {catalog['last_day']}. Đầu vào mô hình được dựng lại từ dữ liệu nến và phái sinh; chưa chạy mô phỏng toàn bộ L2.",
        )
        limits.insert(
            3,
            f"Đã khôi phục và kiểm tra checksum hai file trades AKE/HOT ngày 01/08: {sum(s['trades'] for s in samples):,} giao dịch, 576 nến; OHLC khớp hoàn toàn với Parquet trong kho chính.",
        )
    table_html = table.to_html(index=False, border=0)
    html = f"""<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Đảo Vàng · Backtest tài khoản 500 USDT</title><style>
body{{font:16px/1.6 system-ui,sans-serif;color:#17263d;background:#f4f7fb;margin:0}}main{{max-width:1240px;margin:36px auto;padding:0 24px}}
h1{{font-size:32px;line-height:1.2;margin:14px 0}}h2{{font-size:21px;margin-top:30px}}.muted{{color:#526175}}
.badge{{display:inline-block;border-radius:6px;padding:5px 12px;background:#fff0c2;color:#805900;font-weight:700}}
.box{{padding:20px 24px;background:white;border-radius:12px;margin:20px 0;border:1px solid #dfe6ef}}
.scroll{{overflow:auto}}table{{border-collapse:collapse;min-width:1080px;font-size:14px}}th,td{{padding:12px 14px;border-bottom:1px solid #dfe6ef;text-align:left}}
th{{background:#eff4fa;white-space:normal}}li{{margin:8px 0}}code{{font-size:13px}}a{{color:#2563eb}}</style><main>
<span class="badge">SƠ BỘ · CHƯA ĐỦ ĐIỀU KIỆN NGHIỆM THU</span><h1>Đảo Vàng · Tài khoản 500 USDT</h1>
<p class="muted">24/06–23/09/2026 UTC · Short · Cross x5 · khoảng 5 USDT ký quỹ/lệnh · không stop-loss</p>
<div class="box"><b>Quy tắc tài khoản</b><p>TP = 2 × ATR14 của nến 1 giờ đã đóng; mục tiêu ròng 0,50–5 USDT, khóa tại lúc vào.
Không DCA. Khi tổng tài sản giảm 20% từ đỉnh: dừng mở mới, vẫn giữ vị thế và TP. Không tự bật lại.</p><p>{escape(note)}</p></div>
<h2>So sánh giới hạn vị thế</h2><div class="box scroll">{table_html}</div>
<div class="box">{chart}</div><h2>Phạm vi và giới hạn dữ liệu</h2><div class="box"><ul>{"".join("<li>" + escape(x) + "</li>" for x in limits)}</ul></div>
<p class="muted">Tài khoản thật vẫn ở chế độ theo dõi. Backtest không đặt lệnh và không dùng API key giao dịch.</p>
<p><a href="report.json">Báo cáo JSON</a> · <a href="equity_1.csv">Đường tài sản 1 vị thế</a> · <a href="equity_3.csv">3 vị thế</a> · <a href="equity_5.csv">5 vị thế</a></p>
</main></html>"""
    (folder / "dashboard.html").write_text(html, encoding="utf-8")
    headers = list(rows[0])
    md = (
        "| "
        + " | ".join(headers)
        + " |\n| "
        + " | ".join(["---"] * len(headers))
        + " |\n"
    )
    md += "\n".join(
        "| " + " | ".join(str(row[h]) for h in headers) + " |" for row in rows
    )
    text = f"# Backtest sơ bộ tài khoản Đảo Vàng — 24/09/2026\n\n{note}\n\n"
    text += (
        "Kỳ yêu cầu: **24/06/2026 00:00–24/09/2026 00:00 UTC** (92 ngày). Vốn 500 USDT, Short Cross x5, khoảng 25 USDT danh nghĩa/vị thế, không DCA/stop-loss, TP ATR14 × 2, mục tiêu ròng 0,50–5 USDT.\n\n"
        + md
        + "\n\n"
    )
    text += "## Giới hạn nghiệm thu\n\n" + "\n".join("- " + v for v in limits) + "\n\n"
    text += "Dữ liệu bổ sung: [Binance Funding Rate History và Mark Price Klines](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data). Các phản hồi đã được lưu cùng checksum trong thư mục kết quả.\n\n"
    text += "## Lệnh còn mở khi mô phỏng dừng\n\n"
    for r in runs:
        text += f"### Tối đa {r['max_positions']} vị thế\n\n"
        for p in r["open_positions"]:
            text += f"- {p['symbol']}: vào {timestamp(p['opened_at'])}, giá {p['entry']:.8g}, lượng {p['qty']:g}; định giá cuối đã ghi {p['last_mark']:.8g}, PnL chưa chốt {p['unrealized']:.2f} USDT; giữ {p['held_days']:.2f} ngày.\n"
        stop = r.get("stop_event")
        if stop:
            text += f"\nChạm ngưỡng MMR giả định lúc {timestamp(stop['at'])}: tài sản mẫu {stop['equity']:.2f} USDT, MMR giả định {stop['maintenance_proxy']:.2f} USDT. Không suy ra số dư sau thanh lý.\n"
        text += "\n"
    (folder / "report.md").write_text(text, encoding="utf-8")
    print(table.to_string(index=False))
    print(folder / "dashboard.html")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    render(parser.parse_args().folder)
