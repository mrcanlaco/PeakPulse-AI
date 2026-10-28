"""Stage 2: build the PDF report (matplotlib figures + reportlab layout).

Run with an ephemeral env so project dependencies stay untouched:
    uv run --no-project --with matplotlib --with reportlab --with numpy \
        python scripts/build_nostop_pdf_report.py
Input : artifacts/nostop/report/data.json   (scripts/nostop_report_data.py)
Output: artifacts/nostop/report/NoStop_Strategy_Report.pdf
"""

from __future__ import annotations

import json
import statistics as st
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_JUSTIFY  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "nostop" / "report"
FIGS = OUT / "figs"
FIGS.mkdir(parents=True, exist_ok=True)
PDF = OUT / "NoStop_Strategy_Report.pdf"
D = json.loads((OUT / "data.json").read_text(encoding="utf-8"))

NAVY, AMBER, GREEN, RED, SLATE, LIGHT = "#0b1220", "#d99a00", "#059669", "#dc2626", "#475569", "#f1f5f9"
FONT_DIR = Path("C:/Windows/Fonts")
pdfmetrics.registerFont(TTFont("Arial", str(FONT_DIR / "arial.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Bold", str(FONT_DIR / "arialbd.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Italic", str(FONT_DIR / "ariali.ttf")))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic", boldItalic="Arial-Bold")
plt.rcParams.update({"font.family": "Arial", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#94a3b8", "axes.labelcolor": SLATE, "xtick.color": SLATE, "ytick.color": SLATE})

C = D["candidates"]
SH = [c for c in C if c["shadow"]]
med = lambda xs: float(st.median(xs))  # noqa: E731
pc = lambda x, d=1: f"{x * 100:.{d}f}%"  # noqa: E731
f2 = lambda x: f"{x:.2f}"  # noqa: E731


# ============================================================================ figures
def save(fig, name):
    p = FIGS / f"{name}.png"
    fig.savefig(p, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


def fig_pipeline():
    fig, ax = plt.subplots(figsize=(9.2, 3.0))
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3.2)
    boxes = [
        (0.1, 1.9, "1. Dữ liệu 4h\n116 hợp đồng perpetual\nnến, taker-buy, funding"),
        (2.6, 1.9, "2. Nhân tố\ntaker-flow · funding\n(+ động lượng, phụ)"),
        (5.1, 1.9, "3. Xếp hạng\nhạng phần trăm trung bình\ntop K coin thanh khoản"),
        (7.6, 1.9, "4. Danh mục\nLONG q% cao nhất\nSHORT q% thấp nhất"),
        (0.1, 0.2, "5. Quy mô\nmục tiêu biến động 30%/năm\nđòn bẩy ≤ 2×"),
        (2.6, 0.2, "6. Khớp lệnh\nmở nến kế · phí 5 bps\ntrượt giá 3/8/15 bps"),
        (5.1, 0.2, "7. Giữ vị thế\nhysteresis, tái cân bằng\nmỗi 2–3 ngày"),
        (7.6, 0.2, "8. KHÔNG stop-loss\nrủi ro đuôi do kích thước\nvị thế gánh"),
    ]
    for i, (x, y, t) in enumerate(boxes):
        last = i == 7
        ax.add_patch(FancyBboxPatch((x, y), 2.3, 1.1, boxstyle="round,pad=0.03,rounding_size=0.12",
                                    fc="#fef2f2" if last else "#eff6ff", ec=RED if last else "#3b82f6", lw=1.2))
        ax.text(x + 1.15, y + 0.55, t, ha="center", va="center", fontsize=8.3, color=NAVY)
    for x in (2.4, 4.9, 7.4):
        ax.add_patch(FancyArrowPatch((x, 2.45), (x + 0.2, 2.45), arrowstyle="-|>", mutation_scale=10, color=SLATE))
    ax.add_patch(FancyArrowPatch((8.75, 1.88), (1.25, 1.35), connectionstyle="arc3,rad=0.0", arrowstyle="-|>",
                                 mutation_scale=10, color=SLATE, lw=0.8))
    for x in (2.4, 4.9, 7.4):
        ax.add_patch(FancyArrowPatch((x, 0.75), (x + 0.2, 0.75), arrowstyle="-|>", mutation_scale=10, color=SLATE))
    return save(fig, "pipeline")


def fig_rounds():
    R = D["rounds"]
    fig, ax = plt.subplots(figsize=(7.6, 3.0))
    x = np.arange(len(R))
    ax.bar(x, [r["top20_mean"] for r in R], color=AMBER, width=0.55, label="Calmar validation trung bình top 20")
    for i, r in enumerate(R):
        ax.text(i, r["top20_mean"] + 0.06, f"{r['top20_mean']:.2f}", ha="center", fontsize=8, color=NAVY)
    ax.set_xticks(x, [r["round"] for r in R])
    ax.set_ylabel("Calmar validation")
    ax2 = ax.twinx()
    ax2.plot(x, [r["val_gt1"] for r in R], "o-", color=GREEN, label="Số spec có Calmar val > 1")
    ax2.spines["right"].set_visible(True)
    ax2.set_ylabel("Số spec > 1", color=GREEN)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=7.5, frameon=False)
    ax.set_title("Mỗi vòng cải tiến: chỉ số validation (đã dùng thích nghi, xem mục 3)", fontsize=9, color=NAVY)
    return save(fig, "rounds")


def fig_equity():
    fig, ax = plt.subplots(figsize=(9.0, 3.7))
    for c in SH:
        t = [p[0] for p in c["curve"]]
        ax.plot(np.array(t) / 1000, [p[1] for p in c["curve"]], color="#cbd5e1", lw=0.6)
    t = np.array([p[0] for p in SH[0]["curve"]]) / 1000
    stack = np.array([[p[1] for p in c["curve"]] for c in SH])
    ax.plot(t, np.median(stack, axis=0), color=NAVY, lw=1.6, label="Trung vị 28 shadow")
    bt, bv = D["blend"]["curve"]
    ax.plot(np.array(bt) / 1000, bv, color=AMBER, lw=1.8, label="Gộp đều 28 shadow (mô phỏng)")
    ax.set_yscale("log")
    ax.set_ylabel("Vốn nối tiếp (log, mỗi giai đoạn bắt đầu lại từ 1)")
    ts = [datetime.fromtimestamp(x, tz=timezone.utc) for x in t]
    ax.cla()
    for c in SH:
        ax.plot([datetime.fromtimestamp(p[0] / 1000, tz=timezone.utc) for p in c["curve"]], [p[1] for p in c["curve"]],
                color="#cbd5e1", lw=0.6)
    ax.plot(ts, np.median(stack, axis=0), color=NAVY, lw=1.6, label="Trung vị 28 shadow")
    ax.plot([datetime.fromtimestamp(x / 1000, tz=timezone.utc) for x in bt], bv, color=AMBER, lw=1.8,
            label="Gộp đều 28 shadow (mô phỏng, chưa tính ràng buộc vốn)")
    ax.set_yscale("log")
    for lbl, y in (("Validation", 2024), ("Test", 2026)):
        ax.axvline(datetime(y, 1, 1, tzinfo=timezone.utc), color="#94a3b8", ls="--", lw=0.8)
        ax.text(datetime(y, 2, 1, tzinfo=timezone.utc), ax.get_ylim()[0] * 1.2, lbl, fontsize=8, color=SLATE)
    ax.set_ylabel("Vốn nối tiếp (thang log)")
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    return save(fig, "equity")


def fig_yearly():
    years = ["2020", "2021", "2022", "2023", "2024", "2025", "2026"]
    M = np.array([[c["yearly"][y] for y in years] for c in SH]) * 100
    fig, ax = plt.subplots(figsize=(7.4, 5.6))
    im = ax.imshow(np.clip(M, -60, 200), cmap="RdYlGn", vmin=-60, vmax=200, aspect="auto")
    ax.set_xticks(range(len(years)), [y if y != "2026" else "2026\n(8 tháng)" for y in years])
    ax.set_yticks(range(len(SH)), [c["id"].replace("composite-", "c-") for c in SH], fontsize=6.5)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            ax.text(j, i, f"{M[i, j]:.0f}", ha="center", va="center", fontsize=6.3, color=NAVY)
    ax.set_title("Lợi nhuận theo năm (%), 28 shadow xếp theo Calmar validation giảm dần", fontsize=9, color=NAVY)
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    for s in ax.spines.values():
        s.set_visible(False)
    return save(fig, "yearly")


def fig_scatter():
    fig, ax = plt.subplots(figsize=(5.4, 3.9))
    for c in C:
        ax.scatter(c["val_calmar"], c["test_calmar"], s=26, color=GREEN if c["shadow"] else RED, alpha=0.85)
    v = np.array([c["val_calmar"] for c in C])
    t = np.array([c["test_calmar"] for c in C])
    r = float(np.corrcoef(v, t)[0, 1])
    ax.axhline(1, color="#94a3b8", lw=0.7, ls="--")
    ax.set_xlabel("Calmar validation (dùng để chọn)")
    ax.set_ylabel("Calmar test 2026")
    ax.set_title(f"Validation không dự báo test tốt: tương quan = {r:.2f}", fontsize=9, color=NAVY)
    return save(fig, "scatter"), r


def fig_postlock():
    vals = sorted(((c["post_lock"]["return"], c["id"]) for c in SH))
    fig, ax = plt.subplots(figsize=(7.6, 3.0))
    ax.bar(range(len(vals)), [v * 100 for v, _ in vals], color=[GREEN if v > 0 else RED for v, _ in vals])
    ax.axhline(0, color=SLATE, lw=0.7)
    ax.set_xticks([])
    ax.set_ylabel("Lợi nhuận mô phỏng (%)")
    ax.set_title("01/09 → 06/10/2026 (36 ngày): Backfill ngoài mẫu (không phải forward thực sự)", fontsize=9, color=NAVY)
    return save(fig, "postlock")


def fig_beta():
    fig, ax = plt.subplots(figsize=(5.4, 3.2))
    data = [[c["beta"][s]["beta"] for c in SH] for s in ("train", "val", "test")]
    ax.boxplot(data, tick_labels=["Train", "Validation", "Test"], patch_artist=True,
               boxprops={"facecolor": "#dbeafe"}, medianprops={"color": NAVY})
    ax.axhline(0, color="#94a3b8", lw=0.7, ls="--")
    ax.set_ylabel("Beta với BTC (lợi suất ngày)")
    ax.set_title("Beta thực đo: nhỏ nhưng ngày càng âm", fontsize=9, color=NAVY)
    return save(fig, "beta")


def fig_robust():
    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    keys = [("test_calmar", "Gốc"), ("delay1", "Trễ +4h"), ("delay3", "Trễ +12h"), ("stress_test", "Chi phí ×2")]
    for i, (k, lbl) in enumerate(keys):
        v = [c[k] for c in SH]
        ax.bar(i, med(v), color=AMBER if i == 0 else "#94a3b8", width=0.55)
        ax.plot([i, i], [min(v), max(v)], color=NAVY, lw=1)
        ax.text(i + 0.32, med(v), f"{med(v):.1f}", fontsize=8, va="center", color=NAVY)
    ax.axhline(1, color=RED, lw=0.7, ls="--")
    ax.set_xticks(range(4), [k[1] for k in keys])
    ax.set_ylabel("Calmar test (trung vị, đoạn = min–max)")
    ax.set_title("Độ bền trước trễ khớp lệnh và chi phí", fontsize=9, color=NAVY)
    return save(fig, "robust")


def fig_live():
    rows = sorted(D["live"]["rows"], key=lambda r: r["ret"])
    fig, ax = plt.subplots(figsize=(7.6, 2.8))
    ax.bar(range(len(rows)), [r["ret"] * 100 for r in rows], color=[GREEN if r["ret"] > 0 else RED for r in rows])
    ax.set_xticks([])
    ax.set_ylabel("Lãi/lỗ paper (%)")
    ax.set_title(f"28 shadow đang chạy từ 06/10 12:00 UTC ({rows[0]['days']:.1f} ngày): chưa đủ dài để kết luận", fontsize=9, color=NAVY)
    return save(fig, "live")


def fig_capacity():
    a = D["adv"]
    ranks = sorted(int(k) for k in a)
    fig, ax = plt.subplots(figsize=(6.2, 3.0))
    ax.bar([str(r) for r in ranks], [a[str(r)] / 1e6 for r in ranks], color="#60a5fa")
    ax.set_yscale("log")
    for i, r in enumerate(ranks):
        ax.text(i, a[str(r)] / 1e6 * 1.15, f"${a[str(r)] / 1e6:,.0f}M", ha="center", fontsize=7.5, color=NAVY)
    ax.set_xlabel("Hạng thanh khoản (1 = cao nhất)")
    ax.set_ylabel("Khối lượng USDT/ngày (triệu, log)")
    ax.set_title("Thanh khoản theo hạng, trung bình 30 ngày", fontsize=9, color=NAVY)
    return save(fig, "capacity")


def fig_directions():
    # letters match the table in section 9: (letter, effort 1-5, value 1-5, short label) - qualitative judgement
    pts = [("A", 1.0, 5.0, "Ablation"), ("B", 1.45, 4.8, "Vòng tuân thủ"), ("C", 2.0, 4.0, "Hedge beta + trần vị thế"),
           ("D", 3.0, 4.0, "Vũ trụ theo thời điểm"), ("E", 3.0, 3.15, "Tối ưu khớp lệnh"), ("F", 2.0, 3.15, "OI / long-short"),
           ("G", 4.0, 4.0, "Sổ lệnh L2"), ("H", 4.0, 3.15, "Arbitrage funding"), ("I", 3.4, 2.7, "Stat-arb cặp"),
           ("J", 4.4, 2.7, "ML xếp hạng"), ("K", 5.0, 3.15, "Quyền chọn"), ("L", 5.4, 2.7, "Market making"),
           ("M", 2.4, 2.7, "Sleeve xu hướng")]
    fig, ax = plt.subplots(figsize=(8.2, 4.3))
    for k, e, v, name in pts:
        hi = e <= 2 and v >= 4
        ax.scatter(e, v, s=330, color=GREEN if hi else "#60a5fa", zorder=3, edgecolor="white", linewidth=1.2)
        ax.text(e, v, k, ha="center", va="center", fontsize=9, fontweight="bold", color="white", zorder=4)
        ax.text(e, v - 0.27, name, ha="center", va="top", fontsize=6.8, color=NAVY)
    ax.set_xlim(0.4, 6.0)
    ax.set_ylim(2.0, 5.5)
    ax.set_xlabel("Công sức triển khai (1 = ít, 5 = nhiều)")
    ax.set_ylabel("Giá trị kỳ vọng (1–5, nhận định định tính)")
    ax.set_title("Ma trận ưu tiên hướng phát triển (đánh giá chủ quan của tác giả)", fontsize=9, color=NAVY)
    ax.grid(alpha=0.25)
    return save(fig, "directions")


# ============================================================================ document
S = {
    "body": ParagraphStyle("body", fontName="Arial", fontSize=9.3, leading=13.2, alignment=TA_JUSTIFY, spaceAfter=4.5),
    "small": ParagraphStyle("small", fontName="Arial", fontSize=7.6, leading=10, textColor=colors.HexColor(SLATE)),
    "h1": ParagraphStyle("h1", fontName="Arial-Bold", fontSize=15, leading=19, textColor=colors.HexColor(NAVY), spaceBefore=4, spaceAfter=7, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="Arial-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#b45309"), spaceBefore=8, spaceAfter=4, keepWithNext=1),
    "bul": ParagraphStyle("bul", fontName="Arial", fontSize=9.3, leading=13, leftIndent=11, bulletIndent=1, spaceAfter=2.5, alignment=TA_JUSTIFY),
    "cell": ParagraphStyle("cell", fontName="Arial", fontSize=7.6, leading=9.6),
    "cellb": ParagraphStyle("cellb", fontName="Arial-Bold", fontSize=7.6, leading=9.6, textColor=colors.white),
    "cap": ParagraphStyle("cap", fontName="Arial-Italic", fontSize=7.8, leading=10, textColor=colors.HexColor(SLATE), spaceAfter=7),
    "warn": ParagraphStyle("warn", fontName="Arial", fontSize=9, leading=12.5, textColor=colors.HexColor("#7c2d12")),
    "kpiv": ParagraphStyle("kpiv", fontName="Arial-Bold", fontSize=16, leading=19, textColor=colors.HexColor(NAVY), alignment=1),
    "kpil": ParagraphStyle("kpil", fontName="Arial", fontSize=7.6, leading=9.4, textColor=colors.HexColor(SLATE), alignment=1),
    "title": ParagraphStyle("title", fontName="Arial-Bold", fontSize=24, leading=29, textColor=colors.white),
    "sub": ParagraphStyle("sub", fontName="Arial", fontSize=11.5, leading=16, textColor=colors.HexColor("#cbd5e1")),
}
P = lambda t, s="body": Paragraph(t, S[s])  # noqa: E731
B = lambda t: Paragraph(t, S["bul"], bulletText="•")  # noqa: E731
W = A4[0] - 36 * mm


def img(path, width=W):
    from PIL import Image as PILImage

    w, h = PILImage.open(path).size
    return Image(str(path), width=width, height=width * h / w)


def table(rows, widths, head=True, zebra=True, extra=None):
    data = [[Paragraph(str(c), S["cellb"] if (head and i == 0) else S["cell"]) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if head else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
             ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
    if head:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY)))
    if zebra:
        style += [("BACKGROUND", (0, i), (-1, i), colors.HexColor(LIGHT)) for i in range(2, len(rows), 2)]
    t.setStyle(TableStyle(style + (extra or [])))
    return t


def callout(text, color="#fff7ed", border="#f59e0b"):
    t = Table([[Paragraph(text, S["warn"])]], colWidths=[W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(color)), ("BOX", (0, 0), (-1, -1), 0.9, colors.HexColor(border)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def kpi_row(items):
    cells = [[Paragraph(v, S["kpiv"]), ] for v, _ in items]
    t = Table([[Paragraph(v, S["kpiv"]) for v, _ in items], [Paragraph(label, S["kpil"]) for _, label in items]],
              colWidths=[W / len(items)] * len(items))
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(LIGHT)), ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                           ("LINEAFTER", (0, 0), (-2, -1), 0.5, colors.white), ("TOPPADDING", (0, 0), (-1, 0), 8),
                           ("BOTTOMPADDING", (0, 1), (-1, 1), 8), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    _ = cells
    return t


def cover(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(colors.HexColor(NAVY))
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor(AMBER))
    canvas.rect(18 * mm, A4[1] - 54 * mm, 22 * mm, 2.2 * mm, fill=1, stroke=0)
    canvas.restoreState()


def later(canvas, doc):
    canvas.saveState()
    canvas.setFont("Arial", 7.5)
    canvas.setFillColor(colors.HexColor(SLATE))
    canvas.drawString(18 * mm, 10 * mm, "Chiến lược cross-sectional flow-carry long/short — kết quả thăm dò, không phải lời khuyên đầu tư")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Trang {doc.page}")
    canvas.setStrokeColor(colors.HexColor("#e2e8f0"))
    canvas.line(18 * mm, 13 * mm, A4[0] - 18 * mm, 13 * mm)
    canvas.restoreState()


def build():
    pipe = fig_pipeline()
    rounds = fig_rounds()
    eq = fig_equity()
    yearly = fig_yearly()
    scat, r_vt = fig_scatter()
    post = fig_postlock()
    beta = fig_beta()
    robust = fig_robust()
    live = fig_live()
    cap = fig_capacity()
    dirs = fig_directions()

    bl, bt = D["blend"], D["btc"]
    n = len(SH)
    mt = {s: {k: med([c[f"{s}_{k}"] for c in SH]) for k in ("calmar", "cagr", "maxdd")} for s in ("train", "val", "test")}
    sharpe = {s: med([c[f"{s}_sharpe"] for c in SH]) for s in ("train", "val", "test")}
    post_ret = [c["post_lock"]["return"] for c in SH]
    post_dd = [c["post_lock"]["max_dd"] for c in SH]
    beta_m = {s: med([c["beta"][s]["beta"] for c in SH]) for s in ("train", "val", "test")}
    live_t = D["live"]["totals"]
    live_days = D["live"]["rows"][0]["days"]
    asof = D["generated"]
    adv = D["adv"]

    story = []
    # ----- cover
    story += [Spacer(1, 62 * mm), P("Chiến lược Cross-Sectional<br/>Flow-Carry Long/Short", "title"), Spacer(1, 6),
              P("Báo cáo chiến lược không stop-loss trên hợp đồng perpetual Binance: cơ chế, bằng chứng, bối cảnh các tổ chức quant, "
                "tiềm năng trong crypto và hướng phát triển", "sub"), Spacer(1, 14 * mm)]
    story.append(callout("<b>Nhãn kết quả: THĂM DÒ.</b> Quy trình train/validation/test bị phá thích nghi (validation đã được dùng để thiết kế các vòng sau). "
                         "Đây không phải kết quả nghiệm thu và không phải lời khuyên đầu tư. Toàn bộ vận hành hiện chỉ là paper trading.",
                         color="#fef3c7", border="#f59e0b"))
    story += [Spacer(1, 10 * mm), P(f"Ngày lập: {asof} · Dự án Đảo Vàng (PeakPulse AI) · Mã nguồn: src/dao_vang/nostop", "sub"), PageBreak()]

    # ----- 1. executive summary
    story.append(P("1. Tóm tắt điều hành", "h1"))
    story.append(kpi_row([(str(D["n_locked"]), "spec đã khóa trước khi mở test 2026"), (f"{D['test_pass']}/{D['n_locked']}", "có Calmar > 1 trên test 2026"),
                          (f"{med([c['test_calmar'] for c in SH]):.1f}", "Calmar test trung vị của 28 shadow"),
                          (f"{sum(r > 0 for r in post_ret)}/{n}", "có lãi trong 36 ngày sau khi khóa"),
                          (pc(live_t['ret'], 2), f"lãi paper gộp sau {live_days:.1f} ngày chạy live")]))
    story.append(Spacer(1, 6))
    story.append(P(f"<b>Chiến lược là gì.</b> Mỗi 2–3 ngày, xếp hạng top 30–50 coin thanh khoản bằng điểm tổng hợp của vài nhân tố (cả {n} shadow đều dùng "
                   "<b>dòng lệnh taker</b> và <b>funding</b>; {m} shadow thêm động lượng giá), rồi LONG nhóm điểm cao nhất và SHORT nhóm thấp nhất với tổng "
                   "danh nghĩa hai chân bằng nhau, quy mô theo mục tiêu biến động 30%/năm. Không có stop-loss, trailing hay giảm vị thế theo lỗ. "
                   "Đây là biến thể của <i>factor investing chéo tài sản</i> mà các quỹ quant dùng trên cổ phiếu từ nhiều thập kỷ, áp vào thị trường perpetual crypto."
                   .replace("{m}", str(D["factor_usage"].get("mom", 0)))))
    story.append(P(f"<b>Bằng chứng backtest.</b> Trung vị của {n} shadow: Calmar {mt['train']['calmar']:.1f} (train 2020–23), {mt['val']['calmar']:.1f} "
                   f"(validation 2024–25), {mt['test']['calmar']:.1f} (test 2026 tám tháng, BTC {pc(bt['test']['total'])}). Còn {sum(c['delay1'] > 1 for c in SH)}/{n} "
                   f"vượt 1 khi trễ khớp lệnh 4 giờ và {sum(c['stress_test'] > 1 for c in SH)}/{n} khi chi phí gấp đôi. Không ứng viên nào bị thanh lý."))
    story.append(P(f"<b>Bằng chứng ngược chiều.</b> Khi phát lại đúng {n} spec trên 36 ngày sau khi khóa (01/09–06/10), chỉ {sum(r > 0 for r in post_ret)}/{n} có lãi, "
                   f"trung vị {pc(med(post_ret))}, MaxDD trung vị {pc(med(post_dd))}. Ngược lại, {live_days:.1f} ngày chạy live paper đầu tiên cả 28 shadow đều dương, "
                   "nhưng mẫu này quá ngắn để có ý nghĩa. Hai mẫu cùng cho thấy edge nếu có thì <b>không đều</b> theo thời gian."))
    story.append(P("<b>Tiềm năng.</b> Có cơ sở học thuật cho các nhân tố chéo và carry trong crypto và nhiều quỹ crypto dùng chiến lược trung tính thị trường, "
                   "nhưng quy mô có giới hạn thanh khoản, edge dễ bị bào mòn khi bị khai thác, và rủi ro đuôi không stop là rủi ro thật. "
                   "Mục 7–9 trình bày bối cảnh tổ chức, tiềm năng, và các hướng phát triển ưu tiên."))
    story.append(callout("<b>Kết luận thẳng thắn.</b> Đủ để tiếp tục paper trading và nghiên cứu thêm. Chưa đủ để dùng tiền thật. "
                         "Điều kiện chuyển giai đoạn nằm ở mục 10."))
    story.append(PageBreak())

    # ----- 2. strategy
    story.append(P("2. Chiến lược hoạt động như thế nào", "h1"))
    story.append(img(pipe))
    story.append(P("Hình 1. Luồng xử lý từ dữ liệu đến lệnh. Quyết định tại đóng nến t (chỉ dùng dữ liệu ≤ t), khớp tại giá mở nến t+1.", "cap"))
    story.append(P("2.1 Ba nhóm nhân tố cốt lõi", "h2"))
    story.append(table([
        ["Nhân tố", "Đo cái gì", "Chiều giao dịch", "Giả thuyết kinh tế (chưa kiểm chứng nhân quả)"],
        ["<b>Taker-flow</b><br/>(tỷ lệ taker-mua / tổng khối lượng)", "Áp lực mua/bán chủ động trong 3–14 ngày", "Áp lực mua cao → LONG",
         "Dòng lệnh chủ động lan chậm ở altcoin nên còn kéo dài vài ngày. Rủi ro: cũng có thể là dấu vết pump/dump sắp đảo chiều."],
        ["<b>Funding</b><br/>(carry của perpetual)", "Funding trung bình 3–14 ngày (hoặc z-score)", "Funding cao → SHORT, thấp/âm → LONG",
         "Funding cao phản ánh vị thế long đông. Rủi ro: thường đi cùng xu hướng tăng mạnh, chân SHORT dễ bị squeeze."],
        ["<b>Động lượng giá</b><br/>(18/28 shadow)", "Lợi suất 7–60 ngày", "Tăng mạnh → LONG", "Hành vi bầy đàn. Đứng riêng không vượt validation ở các vòng đầu."],
    ], [32 * mm, 38 * mm, 32 * mm, W - 102 * mm]))
    story.append(Spacer(1, 4))
    story.append(P("Nhân tố phụ ở một số shadow: tăng vọt khối lượng (5), độ biến động thấp (3), lottery/hiệu ứng pump 1 ngày (2), thanh khoản (4), "
                   "động lượng phần dư so với BTC (1). Điểm tổng hợp = trung bình hạng phần trăm của các nhân tố trong vũ trụ top K thanh khoản."))
    story.append(P("2.2 Xây danh mục và quản trị vị thế", "h2"))
    for t in ["<b>Vũ trụ:</b> top K = 30–50 coin theo khối lượng USDT trung bình 30 ngày, có ≥ 90 ngày lịch sử, trong 116 hợp đồng perpetual.",
              "<b>Long/short:</b> nhóm q = 15% (18/28 shadow) cao điểm nhất LONG, thấp điểm nhất SHORT, nửa tổng vị thế mỗi chân.",
              "<b>Hysteresis:</b> vị thế cũ được giữ chừng nào còn nằm trong nhóm q + 0,1–0,3; giảm vòng quay và phí.",
              "<b>Quy mô:</b> mục tiêu biến động 30%/năm ước lượng từ lợi suất quá khứ của chính danh mục giả định (không dùng PnL thực); đòn bẩy tối đa 2×.",
              "<b>Tái cân bằng:</b> mỗi 2 (10 shadow), 3 (16 shadow) hoặc 7 ngày (2 shadow), tại đóng nến 00:00 UTC.",
              "<b>Biến thể:</b> 5 shadow trung hòa theo 3 bậc thanh khoản (tier-neutral); 2 shadow dùng trọng số nghịch biến động (ivol), có thể tập trung vào vài coin."]:
        story.append(B(t))
    story.append(P("2.3 Ví dụ danh mục thật đang chạy", "h2"))
    ex = D["example"]
    rows = [["Coin", "Hướng", "Notional (USDT)", "Giá vào TB", "uPnL (USDT)"]]
    for p in ex["positions"][:12]:
        rows.append([p["symbol"], p["side"], f"{p['notional']:,.0f}", f"{p['avg_entry']:.5g}", f"{p['qty'] * (p['open_price'] - p['avg_entry']):+.1f}"])
    story.append(P(f"Shadow <b>{ex['id']}</b> ({ex['title']}) ngay sau khi chạy: vốn 10.000 USDT, gross {ex['gross']:.2f}×, net {ex['net']:+.2f}×. "
                   "Mười hai vị thế lớn nhất:"))
    story.append(table(rows, [28 * mm, 22 * mm, 36 * mm, 32 * mm, 30 * mm]))
    story.append(P("Bảng 1. Ảnh chụp danh mục (dữ liệu paper trading, giá vào là giá mở nến khi khớp mô phỏng).", "cap"))
    story.append(P("2.4 Cơ chế sinh alpha: giả thuyết và giới hạn của bằng chứng", "h2"))
    story.append(P("Các lý giải kinh tế ở trên là <b>giả thuyết</b>, chưa kiểm chứng nhân quả: dự án chưa chạy ablation (bỏ từng nhân tố khỏi spec cuối) nên chưa biết "
                   "nhân tố nào thực sự mang lợi nhuận. Bằng chứng gián tiếp trong quá trình tìm kiếm: (a) từng nhân tố đứng riêng không vượt Calmar 1 ở validation "
                   "(taker tốt nhất 0,94, funding 0,5–0,8, động lượng dưới 0,5), nhưng nhiều tổ hợp thì vượt; (b) hysteresis và vũ trụ K=40 tốt hơn trên train, "
                   "cân bằng beta và trọng số nghịch biến động kém hơn; (c) nhân tố thanh khoản đảo dấu giữa train và validation."))
    story.append(P(f"<b>Dollar-neutral không phải beta-neutral.</b> Hai chân bằng nhau về danh nghĩa tại kỳ tái cân bằng nhưng khác nhau về beta. Beta thực đo với BTC "
                   f"(lợi suất ngày, trung vị 28 shadow): train {beta_m['train']:.2f}, validation {beta_m['val']:.2f}, test {beta_m['test']:.2f}. Nhỏ nhưng ngày càng âm, "
                   "tức sổ lệnh có xu hướng lỗ khi BTC tăng."))
    story.append(CondPageBreak(90 * mm))

    # ----- 3. research process
    story.append(P("3. Quy trình nghiên cứu và cách tìm ra", "h1"))
    story.append(P(f"Đây là <b>tìm kiếm trên dữ liệu có kiểm soát</b>, không phải suy diễn từ lý thuyết trước. Tôi dựng engine mô phỏng có thanh lý Cross, funding thật và chi phí "
                   f"theo bậc thanh khoản, rồi thử khoảng 19 họ chiến lược trên train 2020–2023. Qua 6 vòng: {D['train_trials_total']:,} cấu hình train, {D['frozen_total']} spec đóng băng, "
                   f"{D['val_gt1_total']} spec qua validation (Calmar > 1), {D['n_locked']} spec được khóa, {D['test_pass']} qua test 2026."))
    story.append(img(rounds, W * 0.85))
    story.append(P("Hình 2. Chỉ số theo vòng. R1 (động lượng, funding, taker đứng riêng) không spec nào vượt 1; R2 chuyển sang tổ hợp sau khi thấy kết quả validation R1.", "cap"))
    story.append(table([["Vòng", "Cấu hình train", "Đóng băng", "Val > 1", "Val tốt nhất", "Top 20 TB"]] +
                       [[r["round"], f"{r['train_configs']:,}", r["frozen"], r["val_gt1"], f"{r['best_val']:.2f}", f"{r['top20_mean']:.2f}"] for r in D["rounds"]],
                       [20 * mm, 32 * mm, 28 * mm, 24 * mm, 30 * mm, 28 * mm]))
    story.append(Spacer(1, 6))
    story.append(P("3.1 Quy tắc dữ liệu và kiểm soát", "h2"))
    for t in ["<b>Chia dữ liệu:</b> train 2020–2023, validation 2024–2025, test 2026-01 → 2026-08. Spec đóng băng ghi SHA-256; validation chỉ chạy được cho spec đã đóng băng; test chỉ cho spec đã khóa; mọi lần truy cập được ghi nhật ký.",
              "<b>Không nhìn trước:</b> mọi họ tín hiệu có test cắt-tương-lai (trọng số các dòng trước không đổi khi bỏ dữ liệu sau). Quyết định tại đóng nến t, khớp tại mở nến t+1.",
              "<b>Không stop-loss:</b> cấm mọi thoát lệnh phụ thuộc PnL vị thế, giá vào, drawdown hay ký quỹ. Sự kiện cưỡng bức duy nhất là thanh lý Cross (ký quỹ duy trì 2%).",
              "<b>Chi phí:</b> phí 5 bps + trượt giá 3/8/15 bps theo hạng thanh khoản (top 10/top 30/còn lại) mỗi chiều, funding thực tại 00/08/16 UTC."]:
        story.append(B(t))
    story.append(callout("<b>Giới hạn quan trọng nhất của quy trình.</b> Ý tưởng R2, R5, R6 được định hướng bởi kết quả validation của vòng trước nên validation 2024–2025 "
                         "<b>không còn độc lập</b>. SHA-256 chỉ chứng minh spec không bị sửa, không ngăn rò rỉ thích nghi. Calmar validation vì vậy bị thổi phồng. "
                         f"Bằng chứng: Calmar validation và test của 31 spec chỉ tương quan yếu (r = {r_vt:.2f}). Chỉ test 2026 là ngoài mẫu, chỉ 8 tháng, "
                         "và danh sách khóa vẫn được chọn bằng validation đã nhiễm."))
    story.append(CondPageBreak(90 * mm))

    # ----- 4. backtest results
    story.append(P("4. Kết quả backtest", "h1"))
    story.append(table([
        ["Giai đoạn", "CAGR (TV)", "MaxDD (TV)", "Calmar (TV)", "Sharpe (TV)", "Gộp đều 28: Calmar", "BTC giữ: CAGR / MaxDD"],
        ["Train 2020–23", pc(mt["train"]["cagr"], 0), pc(mt["train"]["maxdd"]), f2(mt["train"]["calmar"]), f2(sharpe["train"]), f2(bl["train"]["calmar"]),
         f"{pc(bt['train']['cagr'], 0)} / {pc(bt['train']['maxdd'], 0)}"],
        ["Validation 2024–25", pc(mt["val"]["cagr"], 0), pc(mt["val"]["maxdd"]), f2(mt["val"]["calmar"]), f2(sharpe["val"]), f2(bl["val"]["calmar"]),
         f"{pc(bt['val']['cagr'], 0)} / {pc(bt['val']['maxdd'], 0)}"],
        ["Test 2026 (8 tháng)", pc(mt["test"]["cagr"], 0), pc(mt["test"]["maxdd"]), f2(mt["test"]["calmar"]), f2(sharpe["test"]), f2(bl["test"]["calmar"]),
         f"{pc(bt['test']['cagr'], 0)} / {pc(bt['test']['maxdd'], 0)}"],
    ], [34 * mm, 22 * mm, 22 * mm, 24 * mm, 22 * mm, 30 * mm, W - 154 * mm]))
    story.append(P("Bảng 2. TV = trung vị của 28 shadow. Gộp đều = trung bình lợi suất ngày của 28 sleeve, mô phỏng, chưa tính ràng buộc vốn nên lạc quan. "
                   "CAGR test quy năm từ 8 tháng nên rất nhiễu.", "cap"))
    story.append(img(eq))
    story.append(P("Hình 3. Đường vốn nối train → validation → test (log). Mỗi giai đoạn bắt đầu lại từ 1.", "cap"))
    story.append(P("4.1 Độ bền, tương quan và beta", "h2"))
    story.append(Table([[img(robust, W * 0.49), img(beta, W * 0.49)]], colWidths=[W * 0.5, W * 0.5]))
    story.append(P(f"Hình 4. Trái: độ bền (Calmar test). Phải: beta với BTC theo giai đoạn. Tương quan lợi suất ngày giữa 28 shadow trên test: trung vị {D['test_corr_median']:.2f}, "
                   f"thấp nhất {D['test_corr_min']:.2f}. Tức đây thực chất là một họ chiến lược, không phải 28 alpha độc lập.", "cap"))
    story.append(img(yearly, W * 0.88))
    story.append(P("Hình 5. Lợi nhuận theo năm của từng shadow. Năm 2020 chỉ tính từ khoảng tháng 5 vì chiến lược cần ≥ 120 ngày lịch sử (warm-up) và lúc đó vũ trụ chỉ có khoảng 30 coin; "
                   "2026 chỉ có 8 tháng. Các số rất cao ở 2020–2021 nên đọc cùng cảnh báo thiên lệch sống sót (mục 6).", "cap"))
    story.append(P("4.2 Kiểm tra mở rộng ngoài mẫu (Backfill)", "h2"))
    story.append(img(post, W * 0.85))
    story.append(P(f"Hình 6. 36 ngày ngoài tập nghiên cứu ({sum(r > 0 for r in post_ret)}/{n} spec có lãi). Dữ liệu này là lịch sử có sẵn lúc khóa nhưng nằm ngoài cửa sổ test; "
                   "mô phỏng bằng cùng mã nghiên cứu trên nến API. Mẫu quá ngắn để bác bỏ hay xác nhận.", "cap"))
    story.append(scat and Table([[img(scat, W * 0.55)]], colWidths=[W]))
    story.append(P("Hình 7. Calmar validation so với test: không có quan hệ rõ ràng, minh họa việc chọn bằng validation không dự báo được test.", "cap"))
    story.append(CondPageBreak(90 * mm))

    # ----- 5. live shadows
    story.append(P("5. Hệ thống shadow paper trading", "h1"))
    story.append(P(f"28 ứng viên có Calmar &gt; 1 ở cả ba giai đoạn đang chạy paper trading local từ 06/10/2026 12:00 UTC. Một feed nến 4h chung cho cả 28 shadow: trạng thái ổn định "
                   f"chỉ gọi khoảng 116 lệnh klines mỗi 4 giờ, một lệnh funding mỗi 8 giờ và một lệnh giá mỗi phút, không phụ thuộc số shadow. Đo thực tế: chu kỳ ~{D['live']['system']['cycle_seconds']:.0f} s, "
                   f"RAM ~{D['live']['system']['rss_mb']:.0f} MB. Mỗi shadow là phép phát lại tất định từ (spec, nến bắt đầu, bảng nến chung) bằng đúng engine và mô hình chi phí của backtest; "
                   "trang quản lý ở cổng 8890 hiển thị cơ chế, thông số, backtest theo năm, vị thế, lệnh và đường vốn từng shadow."))
    story.append(img(live, W * 0.85))
    story.append(P(f"Hình 8. Lãi/lỗ paper đến {asof} (tổng {live_t['pnl']:+,.0f} USDT trên {live_t['capital']:,.0f}, {live_days:.1f} ngày, {live_t['positions']} vị thế). "
                   "Quá sớm để kết luận. Cần ít nhất vài chục ngày forward.", "cap"))
    story.append(P("5.1 Giới hạn của paper trading", "h2"))
    for t in ["Khớp tại giá mở nến kế sau ~20 giây đồng bộ; không có hàng chờ, khớp từng phần hay tác động giá.",
              "Vũ trụ cố định 116 coin của dữ liệu nghiên cứu; coin mới niêm yết không được thêm.",
              "Shadow khởi động ngay với danh mục của quyết định gần nhất để không chờ 2–7 ngày; kết quả phát lại khớp backtest ở 4 chữ số thập phân với 5/6 ứng viên được kiểm tra, "
              "một ứng viên lệch 1 điểm % do trạng thái hysteresis khởi tạo từ cửa sổ dữ liệu ngắn hơn."]:
        story.append(B(t))
    story.append(CondPageBreak(90 * mm))

    # ----- 6. risks
    story.append(P("6. Rủi ro và hạn chế", "h1"))
    story.append(table([
        ["Rủi ro", "Bản chất", "Bằng chứng / mức độ"],
        ["Validation bị dùng thích nghi", "Ý tưởng vòng sau dựa trên validation vòng trước; thử hàng nghìn cấu hình", f"Tương quan val–test r = {r_vt:.2f}; {D['train_trials_total']:,} cấu hình train, {D['frozen_total']} spec đóng băng. Nên tính Deflated Sharpe [8]."],
        ["Thiên lệch sống sót", "Vũ trụ là 116 coin còn tồn tại cuối 2025, không có coin đã hủy niêm yết", "Chưa định lượng; có thể làm sai lệch cả hai chân."],
        ["Edge không đều", "36 ngày backfill ngoài mẫu: phần lớn spec lỗ", f"{sum(r > 0 for r in post_ret)}/{n} có lãi, trung vị {pc(med(post_ret))}."],
        ["Không stop-loss: rủi ro đuôi", "Một coin tăng 5–10× khi đang SHORT gây lỗ trực tiếp", "Vị thế lớn nhất thường 7–13% vốn (20% ở vài spec, 44% từng thấy ở spec ivol). Backtest không thanh lý lần nào nhưng vũ trụ không có coin chết."],
        ["Beta ẩn", "Cân bằng tiền không cân bằng beta", f"Beta test trung vị {beta_m['test']:.2f}; tương quan âm với BTC."],
        ["Vòng quay và chi phí", "50–140 lần vốn/năm", f"Còn {sum(c['stress_test'] > 1 for c in SH)}/{n} spec > 1 khi chi phí ×2; chưa mô phỏng tác động giá ở coin cỡ nhỏ."],
        ["Bị bào mòn / đám đông", "Nhân tố được khai thác rộng thì giảm lợi suất [6]; tổ chức cùng vị thế có thể tháo đồng loạt [5]", "Chưa đo được mức đông đúc của các nhân tố này trong crypto."],
        ["Rủi ro sàn và hạ tầng", "Cascade thanh lý, ngừng khớp, rút thanh khoản", "10/10/2025: hơn 19 tỷ USD thanh lý trong một ngày [9][11]."],
        ["Dữ liệu", "taker_buy_volume 2026 ghép từ nến 5m; chưa đối chiếu sàn từng nến", "Cần kiểm toán dữ liệu độc lập trước khi tăng vốn."],
    ], [38 * mm, 62 * mm, W - 100 * mm]))
    story.append(CondPageBreak(90 * mm))

    # ----- 7. institutional context
    story.append(P("7. Các tổ chức quant trên thế giới dùng loại chiến lược này ra sao", "h1"))
    story.append(P("Lưu ý nguồn: các quỹ lớn hiếm khi công bố chiến lược cụ thể. Phần này dựa trên công bố học thuật và khảo sát ngành đã dẫn [1]–[12], không phải tiết lộ về chiến lược của từng quỹ."))
    story.append(P("7.1 Factor investing và quant long/short trên thị trường truyền thống", "h2"))
    for t in ["<b>Động lượng và value tồn tại ở mọi lớp tài sản.</b> Asness, Moskowitz và Pedersen (AQR, 2013) ghi nhận premium động lượng và value ở tám thị trường (cổ phiếu Mỹ, Anh, châu Âu, Nhật, chỉ số, trái phiếu, tiền tệ, hàng hóa) "
              "và thấy value với momentum tương quan âm nên kết hợp cả hai gần đường biên hiệu quả hơn từng cái đơn lẻ [4].",
              "<b>Stat-arb trung tính trên cổ phiếu.</b> Avellaneda và Lee (2010) trình bày khung stat-arb bằng PCA trên cổ phiếu Mỹ như một chiến lược hệ thống trung tính thị trường [12]. Chiến lược của dự án thuộc cùng tinh thần xếp hạng chéo, nhưng bằng nhân tố dòng lệnh và carry thay vì giá tương đối.",
              "<b>Dòng lệnh dẫn giá ở khung ngắn.</b> Cont, Kukanov và Stoikov (2014) cho thấy trên cổ phiếu Mỹ, ở khoảng thời gian ngắn, thay đổi giá chủ yếu do mất cân bằng dòng lệnh tại giá chào mua/bán tốt nhất [7]. Taker-ratio theo ngày của dự án chỉ là proxy thô của khái niệm này và bằng chứng trên không trực tiếp áp cho khung nhiều ngày ở crypto.",
              "<b>Bài học đám đông.</b> Tháng 8/2007, nhiều quỹ quant long/short cổ phiếu cùng lỗ nặng trong vài ngày; Khandani và Lo cho rằng nguyên nhân là tháo vị thế đồng loạt của các danh mục xây tương tự [5]. Với dự án, hệ quả là rủi ro đông đúc cần được theo dõi, không thể chỉ nhìn backtest.",
              "<b>Alpha bị bào mòn sau công bố.</b> McLean và Pontiff ước tính lợi suất giảm khoảng 32% do giao dịch dựa trên nghiên cứu đã công bố (chênh giữa mức giảm 58% sau công bố và 26% ngoài mẫu) [6]. Nên giả định edge thực tế thấp hơn backtest."]:
        story.append(B(t))
    story.append(P("7.2 Thực hành vận hành điển hình của tổ chức", "h2"))
    story.append(P("Nhận định chung (không gắn với một quỹ cụ thể): các đội quant thường tách nghiên cứu khỏi vận hành, dùng mô hình rủi ro và mô hình chi phí giao dịch riêng, "
                   "kiểm soát đa kiểm định, đo công suất vốn, giám sát liên tục, và không tăng vốn theo backtest đơn lẻ. So sánh với dự án:"))
    story.append(table([
        ["Thực hành tổ chức", "Dự án hiện có", "Khoảng trống"],
        ["Mô hình rủi ro đa nhân tố, giới hạn phơi nhiễm", "Vol-target danh mục giả định, trần đòn bẩy 2×", "Chưa có ràng buộc beta, ngành, hay trần vị thế từng coin"],
        ["Mô hình chi phí giao dịch theo thanh khoản", "Phí + trượt giá theo 3 bậc hạng", "Chưa mô phỏng tác động giá, hàng chờ, khớp từng phần"],
        ["Kiểm soát đa kiểm định (deflated Sharpe, kiểm định ngoài mẫu thật)", "Niêm phong spec, test một lần", "Validation đã nhiễm; chưa tính Deflated Sharpe [8]"],
        ["Phân rã nguồn lợi nhuận (attribution)", "Chưa có", "Chưa ablation từng nhân tố"],
        ["Vũ trụ theo thời điểm gồm coin chết", "116 coin còn sống", "Thiên lệch sống sót"],
        ["Giám sát live, báo động", "Dashboard paper, kiểm tra lệch giờ", "Chưa có cảnh báo tự động, chưa có kill-switch cho tiền thật"],
    ], [58 * mm, 52 * mm, W - 110 * mm]))
    story.append(P("7.3 Quỹ crypto: ai đang làm gì", "h2"))
    story.append(P("Khảo sát AIMA 2025 (122 quỹ và nhà đầu tư, tổng AUM khoảng 982 tỷ USD) cho thấy [9]:"))
    for t in ["55% quỹ truyền thống có phơi nhiễm crypto (47% năm 2024); phân bổ trung bình 7% AUM; 67% dùng phái sinh crypto. Trong số quỹ truyền thống dự định tăng phơi nhiễm, 27% nêu \"alpha trung tính thị trường\" là động cơ (47% nêu đa dạng hóa).",
              "Quỹ crypto-native: chiến lược phổ biến nhất là multi-strategy (29%), trung tính thị trường (25%), long-only (24%), long/short (14%); AUM trung bình khoảng 132 triệu USD, 91% dưới 1 tỷ USD.",
              "Các báo cáo PwC/AIMA trước đó ghi nhận trung tính thị trường là chiến lược phổ biến nhất ở bản 2022 (30% số quỹ) và vẫn đứng đầu nhưng giảm còn 20% ở bản 2023 [10].",
              "Sự kiện 10/10/2025 (hơn 19 tỷ USD thanh lý trong một ngày) được báo cáo nêu như bằng chứng rủi ro đòn bẩy và hạ tầng ở phái sinh crypto [9][11]."]:
        story.append(B(t))
    story.append(P("Hàm ý: chiến lược trung tính thị trường trên phái sinh crypto là hướng được nhiều tổ chức theo đuổi, nhưng quỹ crypto trung bình nhỏ (hàng trăm triệu USD), "
                   "nên lợi thế hạn chế về quy mô là có thật. Ngưỡng vốn cao hơn sẽ gặp trần thanh khoản (mục 8)."))
    story.append(CondPageBreak(90 * mm))

    # ----- 8. potential in crypto
    story.append(P("8. Tiềm năng trong lĩnh vực crypto", "h1"))
    story.append(P("8.1 Vì sao crypto là sân chơi thuận lợi cho chiến lược chéo", "h2"))
    for t in ["<b>Nhân tố chéo có nền học thuật.</b> Liu, Tsyvinski và Wu (Journal of Finance, 2022) tìm thấy ba nhân tố (thị trường, quy mô, động lượng) giải thích lợi suất kỳ vọng chéo của tiền mã hóa và chín nhân tố tạo chiến lược long/short có ý nghĩa thống kê [1].",
              "<b>Carry lớn và biến động.</b> Schmeling, Schrimpf và Todorov (BIS, 2023) ghi nhận carry của futures crypto trung bình trên 10%/năm, có lúc tới 60%/năm, lý giải bởi nhà đầu tư nhỏ đuổi xu hướng với đòn bẩy và sự khan hiếm vốn arbitrage; carry cao dự báo sụp giá [2]. "
              "He và cộng sự cho thấy độ lệch giá của perpetual lớn hơn thị trường tiền tệ truyền thống, đồng biến giữa các coin và giảm dần theo thời gian [3].",
              "<b>Thị trường 24/7, nhiều tài sản, dữ liệu dòng lệnh công khai (taker-buy theo nến), funding công khai, chi phí giao dịch thấp.</b> Số lượng hợp đồng lớn tạo độ phân tán chéo cao.",
              "<b>Sự tham gia thể chế tăng.</b> 55% quỹ truyền thống có phơi nhiễm crypto, 71% định tăng trong 12 tháng [9]."]:
        story.append(B(t))
    story.append(P("8.2 Giới hạn quy mô: thanh khoản theo hạng", "h2"))
    story.append(Table([[img(cap, W * 0.55), P(
        f"Khối lượng USDT/ngày của coin hạng 10 khoảng ${adv['10'] / 1e6:,.0f}M, hạng 30 ${adv['30'] / 1e6:,.0f}M, hạng 40 ${adv['40'] / 1e6:,.0f}M, hạng 50 ${adv['50'] / 1e6:,.0f}M, hạng 100 ${adv['100'] / 1e6:,.0f}M. "
        f"Với vị thế lớn nhất khoảng 10% vốn trên coin hạng ~40 và giả định tham gia tối đa 1% khối lượng ngày, vốn tối đa cỡ ${0.01 * adv['40'] / 0.10 / 1e6:,.1f} triệu USD; "
        f"nếu tham gia 5% thì cỡ ${0.05 * adv['40'] / 0.10 / 1e6:,.0f} triệu USD nhưng trượt giá thực sẽ vượt giả định 8–15 bps của mô hình. "
        "Đây là ước lượng bậc độ lớn từ khối lượng, không phải năng lực khớp lệnh đã kiểm chứng.", "body")]], colWidths=[W * 0.58, W * 0.42]))
    story.append(P("Hình 9. Khối lượng theo hạng thanh khoản (dữ liệu feed đến " + D["feed_asof"][:16] + " UTC).", "cap"))
    story.append(P("8.3 Đánh giá tiềm năng", "h2"))
    story.append(table([
        ["Yếu tố", "Tích cực", "Tiêu cực"],
        ["Cơ sở lý thuyết", "Nhân tố chéo và carry có tài liệu học thuật trong crypto [1][2][3]", "Cơ chế cụ thể của taker-flow ở khung nhiều ngày chưa được kiểm chứng ở đây"],
        ["Quy mô", "Phù hợp vốn cá nhân đến vài triệu USD", "Trần thanh khoản vì vị thế dồn vào coin hạng 30–50"],
        ["Độ bền của edge", "Kết quả test 2026 và độ bền theo trễ/chi phí tốt", "36 ngày backfill ngoài mẫu phần lớn lỗ; alpha bị bào mòn khi được khai thác [6]"],
        ["Rủi ro", "Không thanh lý trong 6,7 năm backtest", "Không stop-loss; vũ trụ không có coin chết; sàn có thể cascade thanh lý [9][11]"],
        ["Vận hành", "Shadow nhẹ, dữ liệu công khai, chi phí thấp", "Chưa có kiểm soát rủi ro và giám sát cấp tổ chức"],
    ], [34 * mm, (W - 34 * mm) / 2, (W - 34 * mm) / 2]))
    story.append(CondPageBreak(90 * mm))

    # ----- 9. directions
    story.append(P("9. Các hướng phát triển khác", "h1"))
    story.append(img(dirs, W * 0.92))
    story.append(P("Hình 10. Ma trận ưu tiên. Vị trí là đánh giá định tính của tác giả, không phải số đo.", "cap"))
    story.append(table([
        ["Hướng", "Mô tả", "Dữ liệu / công sức", "Ghi chú"],
        ["<b>A. Ablation và phân bổ lợi nhuận</b>", "Bỏ từng nhân tố, đo lại; xác định nhân tố mang lợi nhuận thật", "Có sẵn; vài giờ", "Ưu tiên cao nhất. Phải chạy trên spec mới đóng băng theo giao thức tuân thủ."],
        ["<b>B. Vòng nghiên cứu tuân thủ</b>", "Chốt họ chiến lược và lưới tham số trên train, mở validation đúng một lần, dùng forward của shadow làm kiểm định độc lập", "Có sẵn; cần thời gian chờ", "Phục hồi tính độc lập của validation. Tính Deflated Sharpe [8]."],
        ["<b>C. Hedge beta BTC và trần vị thế</b>", "Thêm vị thế BTC perp để cân beta; trần mỗi coin (ví dụ 10% vốn)", "Có sẵn; vài ngày", "Không phải stop-loss nên không vi phạm nguyên tắc. Giảm rủi ro đuôi và beta ẩn."],
        ["<b>D. Vũ trụ theo thời điểm</b>", "Gồm coin hủy niêm yết, thêm coin mới niêm yết", "Cần dữ liệu lịch sử niêm yết; vài tuần", "Giảm thiên lệch sống sót."],
        ["<b>E. Tối ưu khớp lệnh</b>", "Lệnh maker, chia nhỏ (TWAP), né giờ funding", "Cần dữ liệu sổ lệnh để đánh giá", "Giảm chi phí với vòng quay 50–140×/năm."],
        ["<b>F. Nhân tố OI, long-short ratio</b>", "Open interest và tỷ lệ tài khoản long/short", "Dữ liệu chỉ từ 2024 nên không train được 2020–23", "Chỉ thử được với giao thức mới hoặc dùng forward."],
        ["<b>G. Mất cân bằng sổ lệnh (L2)</b>", "Order book imbalance khung phút–giờ, gần với bằng chứng [7]", "Cần thu thập dữ liệu L2; vài tháng", "Alpha khung ngắn, vòng quay cao, nhạy chi phí."],
        ["<b>H. Arbitrage funding / basis</b>", "Cash-and-carry, chênh lệch funding đa sàn [2][3]", "Cần tài khoản đa sàn, vốn thế chấp", "Sharpe cao theo [3] nhưng cần vốn và rủi ro thanh lý."],
        ["<b>I. Stat-arb cặp coin</b>", "Cặp đồng tích hợp, hồi quy về trung bình [12]", "Có sẵn dữ liệu; vài tuần", "Đảo chiều ngắn hạn đứng riêng thất bại ở đây; cần thận trọng."],
        ["<b>J. Xếp hạng bằng ML</b>", "Gradient boosting trên bộ nhân tố, CV có purge/embargo", "Có sẵn; vài tuần", "Dễ quá khớp; cần đa kiểm định nghiêm ngặt [8]."],
        ["<b>K. Quyền chọn / phí rủi ro biến động</b>", "Bán biến động có phòng hộ", "Cần dữ liệu Deribit", "Rủi ro đuôi lớn; công sức cao."],
        ["<b>L. Market making</b>", "Cung cấp thanh khoản", "Cần hạ tầng độ trễ thấp", "Cạnh tranh với các nhà tạo lập chuyên nghiệp; không khuyến nghị ở giai đoạn này."],
        ["<b>M. Kết hợp sleeve xu hướng</b>", "Thêm sleeve trend BTC/ETH hoặc carry thuần có tương quan thấp", "Có sẵn; vài ngày", "Bài học AQR: kết hợp các chiến lược tương quan âm cải thiện hiệu quả [4]."],
    ], [38 * mm, 54 * mm, 38 * mm, W - 130 * mm]))
    story.append(CondPageBreak(90 * mm))

    # ----- 10. roadmap
    story.append(P("10. Lộ trình khuyến nghị và điều kiện chuyển giai đoạn", "h1"))
    story.append(P("Các ngưỡng dưới đây là <b>đề xuất của tác giả</b> để bạn xem xét, không phải tiêu chuẩn ngành."))
    story.append(table([
        ["Giai đoạn", "Việc cần làm", "Điều kiện qua cổng (đề xuất)"],
        ["0. Hiện tại: paper local", "Chạy 28 shadow; thu dữ liệu forward; hoàn tất ablation (hướng A) và hedge beta + trần vị thế (hướng C)",
         "Ít nhất 90 ngày forward chia 3 cửa sổ 30 ngày; kết quả sau chi phí; không lỗi dữ liệu nghiêm trọng"],
        ["1. Đánh giá độc lập", "Vòng tuân thủ (hướng B): chốt tìm kiếm trên train, validation một lần, forward làm kiểm định; tính Deflated Sharpe",
         "Calmar &gt; 1 ở ít nhất 2 trong 3 cửa sổ forward; Deflated Sharpe dương; kết quả giữ khi chi phí ×2"],
        ["2. Demo sàn", "Chạy lệnh thật trên môi trường demo của Binance với cùng engine; đối chiếu lệch giá khớp", "Trượt giá thực ≤ giả định; không lệnh treo; đối soát vị thế đúng"],
        ["3. Tiền thật rất nhỏ", "Một số ít shadow, vốn nhỏ, tăng dần; thêm giới hạn rủi ro (trần vị thế, hedge beta)", "Mỗi mức chạy tối thiểu 14 ngày; người dùng chủ động kích hoạt"],
        ["4. Mở rộng", "Chỉ khi forward và live khớp; xem xét hướng D, E, H, M", "Không tự động nâng vốn theo backtest"],
    ], [34 * mm, 78 * mm, W - 112 * mm]))
    story.append(Spacer(1, 8))
    story.append(callout("<b>Điều không nên làm.</b> Không tăng vốn hay chuyển sang tiền thật dựa trên Calmar test 2026 hoặc Calmar validation; hai con số đó đã bị chọn lọc và "
                         "mẫu test chỉ 8 tháng. Không diễn giải 28 shadow thành 28 nguồn lợi nhuận độc lập."))
    story.append(PageBreak())

    # ----- appendix A candidates
    story.append(P("Phụ lục A. Danh sách 28 shadow", "h1"))
    rows = [["#", "ID", "Cấu hình", "Calmar<br/>tr / val / te", "CAGR/MaxDD<br/>test", "LN test", "Calmar test<br/>×2 phí", "Beta<br/>test", "Ngoài mẫu<br/>(36 ngày)"]]
    for i, c in enumerate(SH, 1):
        rows.append([i, c["id"].replace("composite-", "c-"), c["title"].replace(" · ", "<br/>"),
                     f"{c['train_calmar']:.1f} / {c['val_calmar']:.1f} / {c['test_calmar']:.1f}", f"{c['test_cagr'] * 100:.0f}% / {c['test_maxdd'] * 100:.0f}%",
                     f"{c['test_ret'] * 100:+.0f}%", f"{c['stress_test']:.1f}", f"{c['beta']['test']['beta']:.2f}", f"{c['post_lock']['return'] * 100:+.1f}%"])
    story.append(table(rows, [7 * mm, 20 * mm, W - 128 * mm, 27 * mm, 22 * mm, 14 * mm, 15 * mm, 11 * mm, 12 * mm]))
    story.append(P("Calmar = CAGR / MaxDD. Test 2026 chỉ 8 tháng. Sao chép đầy đủ tham số trong tệp artifacts/nostop/candidate_lock.json.", "cap"))
    story.append(PageBreak())

    # ----- appendix B method, refs
    story.append(P("Phụ lục B. Phương pháp tóm tắt", "h1"))
    for t in ["<b>Dữ liệu:</b> bảng nến 4h của 116 hợp đồng perpetual USDT (2020-01 → 2026-08, ghép từ nến 5m cho 2026), funding 8h thật. Vũ trụ theo thời điểm: ≥ 90 ngày lịch sử và top K thanh khoản 30 ngày.",
              "<b>Engine:</b> quyết định tại đóng nến t, khớp tại mở nến t+1, lợi suất mở→mở; funding trừ/cộng tại mốc 00/08/16 UTC; thanh lý Cross với ký quỹ duy trì 2% tại cực trị bất lợi của nến.",
              "<b>Chỉ số:</b> Calmar = CAGR / MaxDD trên đường vốn 4h; có thêm MaxDD trong nến (bảo thủ). CAGR test quy năm từ 8 tháng nên nhiễu.",
              "<b>Kiểm thử:</b> 42 test tự động cho nostop, gồm không-nhìn-trước cho mọi họ tín hiệu, khớp tính tay, vị thế lỗ không bị đóng, squeeze 25× thanh lý, dấu funding, dollar-neutral nhưng không beta-neutral.",
              "<b>Mã nguồn và tài liệu:</b> src/dao_vang/nostop/, docs/NOSTOP_RESEARCH_PROTOCOL_20261006.md, docs/NOSTOP_CANDIDATES_20261006.md, docs/NOSTOP_SHADOW.md."]:
        story.append(B(t))
    story.append(P("Tài liệu tham khảo", "h2"))
    refs = [
        "[1] Liu, Y., Tsyvinski, A., Wu, X. (2022). Common Risk Factors in Cryptocurrency. <i>Journal of Finance</i> 77(2), 1133–1177. https://doi.org/10.1111/jofi.13119 (NBER WP 25882)",
        "[2] Schmeling, M., Schrimpf, A., Todorov, K. (2023). Crypto carry. BIS Working Paper 1087. https://www.bis.org/publications/working-paper-1087-crypto-carry",
        "[3] He, S., Manela, A., Ross, O., von Wachter, V. Fundamentals of Perpetual Futures. arXiv:2212.06888. https://arxiv.org/abs/2212.06888",
        "[4] Asness, C., Moskowitz, T., Pedersen, L. H. (2013). Value and Momentum Everywhere. <i>Journal of Finance</i> 68(3), 929–985. https://doi.org/10.1111/jofi.12021",
        "[5] Khandani, A., Lo, A. (2011). What happened to the quants in August 2007? <i>Journal of Financial Markets</i> 14(1), 1–46 (NBER WP 14465). https://www.nber.org/papers/w14465",
        "[6] McLean, R. D., Pontiff, J. (2016). Does Academic Research Destroy Stock Return Predictability? <i>Journal of Finance</i> 71(1), 5–32. https://doi.org/10.1111/jofi.12365",
        "[7] Cont, R., Kukanov, A., Stoikov, S. (2014). The price impact of order book events. <i>Journal of Financial Econometrics</i> 12(1), 47–88. https://arxiv.org/abs/1011.6402",
        "[8] Bailey, D., López de Prado, M. (2014). The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality. https://doi.org/10.2139/ssrn.2460551",
        "[9] AIMA (2025). Annual Global Crypto Hedge Fund Report 2025 (7th edition). https://www.aima.org/asset/E9C6988D-C16B-49F4-B9488D2C3D6F8A18",
        "[10] PwC/AIMA (2022, 2023). 4th and 5th Annual Global Crypto Hedge Fund Report. https://www.pwc.com/gx/en/financial-services/pdf/4th-annual-global-crypto-hedge-fund-report-june-2022.pdf ; "
        "https://www.pwc.com/gx/en/new-ventures/cryptocurrency-assets/5th-annual-global-crypto-hedge-fund-report-july-2023.pdf (số liệu trích từ đoạn tóm tắt hiển thị khi tra cứu; không tải được bản PDF đầy đủ)",
        "[11] CoinDesk (2026-02-12). Binance's Richard Teng breaks down the '10/10' nightmare that rocked crypto. https://www.coindesk.com/business/2026/02/12/binance-not-alone-in-seeing-liquidations-during-oct-10-event-binance-ceo-teng-says",
        "[12] Avellaneda, M., Lee, J.-H. (2010). Statistical arbitrage in the US equities market. <i>Quantitative Finance</i> 10(7), 761–782. https://doi.org/10.1080/14697680903124632",
    ]
    for r in refs:
        story.append(Paragraph(r, S["small"]))
        story.append(Spacer(1, 2))
    story.append(Spacer(1, 6))
    story.append(P("Báo cáo này chỉ có tính thông tin và nghiên cứu, không phải lời khuyên đầu tư. Giao dịch phái sinh có đòn bẩy và không có stop-loss có thể gây mất toàn bộ vốn.", "small"))

    doc = BaseDocTemplate(str(PDF), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                          title="Chiến lược Cross-Sectional Flow-Carry Long/Short", author="Đảo Vàng")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([PageTemplate(id="cover", frames=[frame], onPage=cover, autoNextPageTemplate="later"),
                          PageTemplate(id="later", frames=[frame], onPage=later)])
    doc.build(story)
    print("wrote", PDF, PDF.stat().st_size // 1024, "KB")
    _ = KeepTogether


if __name__ == "__main__":
    build()
