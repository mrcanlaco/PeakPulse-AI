"""Publish signal-edge diagnostics separately from realized account returns."""

import json
from html import escape

from compare_account_risk import ROOT
from search_event_horizons import OUT

NAMES = dict(
    acceleration="Giảm mạnh kèm khối lượng",
    failed_high="Phá đỉnh thất bại",
    breakdown="Phá đáy",
    ema_reject="Hồi EMA bị từ chối",
    failed_pump="Nhịp tăng thất bại",
    pullback="Hồi rồi giảm",
    weak_rank="Coin yếu",
    exhaustion="Tăng mạnh bị bán xuống",
)


def main():
    s = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    audit = json.loads((OUT / "long_history_audit.json").read_text(encoding="utf-8"))
    screen_rows, md_screen = [], []
    for v in s["validation"]:
        h = next(r for r in s["holdout"] if r["id"] == v["id"])
        title = NAMES[v["spec"]["source"]["family"]] + f" · {v['spec']['hours']} giờ"
        values = [
            f"{r['cases'][c]['mean_net_return'] * 100:.3f}%"
            for r, c in [
                (v, "base"),
                (v, "stress"),
                (h, "base"),
                (h, "stress"),
                (h, "low_assumed"),
            ]
        ]
        screen_rows.append(
            f"<tr><td>{escape(title)}</td><td>{v['counts']['complete']}/{h['counts']['complete']}</td>{''.join('<td>' + x + '</td>' for x in values)}</tr>"
        )
        md_screen.append(
            f"| {title} | {v['counts']['complete']}/{h['counts']['complete']} | {' | '.join(values)} |"
        )
    account_rows, md_accounts = [], []
    for spec in s["portfolio_specs"]:
        rows = [
            r
            for r in s["results"]
            if r["window"] == "full" and r["strategy_id"] == spec["id"]
        ]
        values = [r["ending_equity"] for r in rows]
        ending = (
            f"{min(values):.2f}–{max(values):.2f}"
            if all(v is not None for v in values)
            else "Không hoàn tất"
        )
        months = []
        for i in range(3):
            values = [r["monthly"]["months"][i]["return_fraction"] * 100 for r in rows]
            months.append(f"{min(values):.2f} đến {max(values):.2f}%")
        title = (
            f"{NAMES[spec['source']['source']['family']]} · {spec['source']['hours']}h · {spec['cap']} vị thế · {spec['parts']} phần · "
            + ("SL 1" if spec["policy"].get("loss_usdt") else "không SL")
        )
        count = f"{min(r['entries'] for r in rows)}–{max(r['entries'] for r in rows)}"
        account_rows.append(
            f"<tr><td>{escape(title)}</td><td>{ending}</td>{''.join('<td>' + x + '</td>' for x in months)}<td>{count}</td></tr>"
        )
        md_accounts.append(f"| {title} | {ending} | {' | '.join(months)} | {count} |")
    history_rows = []
    for r in audit["independent_checks"]:
        funding, prices = r.get("funding", {}), r.get("prices", {})
        history_rows.append(
            f"<tr><td>{r['symbol']}</td><td>{funding.get('public_rows', '—')}</td><td>{funding.get('missing_rows', '—')}/{funding.get('different_rates', '—')}</td><td>{prices.get('public_rows', '—')}</td><td>{prices.get('missing_rows', '—')}/{prices.get('differing_ohlc_rows', '—')}</td></tr>"
        )
    style = (
        (ROOT / "artifacts/monthly_target_batch01_20260925/dashboard.html")
        .read_text(encoding="utf-8")
        .split("<style>", 1)[1]
        .split("</style>", 1)[0]
    )
    html = """<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Đo lợi thế tín hiệu</title><style>__STYLE__</style>
<h1>Mục tiêu 50%/tháng · Lượt 02</h1><p>Đo lợi thế tín hiệu trước khi chỉnh TP · 500 USDT · x5 · 5 USDT ký quỹ/vị thế · Không bật live</p>
<div class="notice"><b>Chưa đạt mục tiêu. Các tín hiệu hiện tại chưa chứng minh lợi thế đủ lớn sau chi phí.</b><p>240 tổ hợp tín hiệu–thời gian giữ được sàng lọc; 96 đường tài khoản được kiểm định tiếp. Không có tổ hợp có cận dưới 95% dương ở cả mức chi phí cơ sở và cao trong tháng sàng lọc. Tăng tần suất có thể tăng lỗ: một số bản mở hơn 800 vị thế trong ba tháng vẫn giảm tài sản.</p></div>
<div class="cards"><div class="card">Quy tắc tín hiệu<strong>48</strong></div><div class="card">Thời gian giữ<strong>1 / 4 / 12 / 24 / 48h</strong></div><div class="card">Mô phỏng tài khoản<strong>96</strong></div><div class="card">Đạt 50% mọi tháng<strong>0</strong></div></div>
<section class="panel"><h2>Tín hiệu có lợi thế trước khi xét TP không?</h2><p>Bảng là lợi suất trung bình mỗi sự kiện Short giả định, tính trên danh nghĩa vị thế, không phải lợi nhuận tài khoản hay tỷ suất trên ký quỹ. Bán ở giá mở nến 5 phút tiếp theo, mua lại sau số giờ cố định, tính phí/trượt giá/funding. Các sự kiện có thể chồng lấn nên tuyệt đối không cộng chúng thành lợi nhuận tài khoản.</p><div class="scroll"><table><thead><tr><th>Nhóm / thời gian giữ</th><th>Số sự kiện tháng 2/3</th><th>Tháng 2 cơ sở</th><th>Tháng 2 chi phí cao</th><th>Tháng 3 cơ sở</th><th>Tháng 3 chi phí cao</th><th>Tháng 3 trượt giá thấp*</th></tr></thead><tbody>__SCREEN__</tbody></table></div><p>*Giả định trượt giá 0,02% mỗi chiều và phí 0,05%; chưa được xác minh bằng sổ lệnh lịch sử, không dùng để chọn ứng viên. Cơ sở: trượt giá 0,20%, phí 0,05%. Chi phí cao: 0,50%, phí 0,10%. Ngay cả khi hạ giả định trượt giá, các ứng viên giữ lại vẫn chưa có cận dưới 95% dương trong tháng cuối.</p><p>Tháng 1: 24/06–24/07; tháng 2: 24/07–24/08; tháng 3: 24/08–24/09/2026 UTC. Chọn một tổ hợp mỗi nhóm từ tháng 1 theo cận dưới khoảng ước lượng, cần ≥100 sự kiện và không thiếu giá; khóa trước tháng 2. Chọn hai tổ hợp để thử tài khoản từ tháng 2 rồi khóa trước tháng 3. Đây là lựa chọn để chẩn đoán, không có nghĩa chúng đã có lợi thế dương. Nhóm ít mẫu không được nâng lên vì vài lệnh thắng.</p><p>Khoảng ước lượng lấy mẫu lại theo cụm ngày đồng bộ giữa các coin, khối 7 ngày, 2.000 lần; chưa hiệu chỉnh thử nhiều biến thể. Sự kiện có thời điểm đóng chạm/vượt cuối kỳ được ghi là chưa đủ thời gian quan sát. Thiếu giá không được tự thay bằng giá thuận lợi. Số lượng hoàn tất/chưa đủ thời gian/thiếu dữ liệu đều lưu trong kết quả.</p></section>
<section class="panel"><h2>Mô phỏng hai ứng viên trên một tài khoản chung</h2><p>Mỗi bản bắt đầu 500 USDT, tối đa 1/5 vị thế, vào một lần/ba phần, SL không có/1 USDT theo tỷ lệ đã vào. Có đóng theo thời gian 1h hoặc 4h và TP ròng tối đa 5 USDT khi đủ phần. Vì có TP, giới hạn vốn và quy tắc sàn, các bản này khác phép đo sự kiện phía trên. “Không SL” ở bảng này vẫn có đóng theo thời gian; không phải cấu hình giữ lệnh vô hạn ban đầu.</p><div class="scroll"><table><thead><tr><th>Phương án</th><th>Tài sản cuối</th><th>Tháng 1</th><th>Tháng 2</th><th>Tháng 3</th><th>Số vị thế mở</th></tr></thead><tbody>__ACCOUNTS__</tbody></table></div><p>Khoảng số là hai giả định chi phí. Tính tháng trên tài sản đầu tháng của tài khoản chạy liên tục, không khởi tạo lại 500 USDT. Vị thế mở được định giá và funding vẫn tính. Mức 0% cuối kỳ ở một số bản xảy ra sau khi hệ thống đã khóa mở mới vì sụt giảm 20%, không phải chiến lược vừa ổn định trở lại.</p></section>
<section class="panel"><h2>Kiểm tra kho dữ liệu dài hơn</h2><p>Trong 30 coin đang nghiên cứu, 25 coin có đủ số nến 5 phút trong khoảng 01/09/2025–01/06/2026 theo kiểm kê hiện tại. Năm coin còn lại không được lấp dữ liệu giả. Đây chưa phải bộ coin lịch sử chọn trước kỳ; cần chọn lại theo thanh khoản thời điểm đó và xử lý hợp đồng mới/hủy niêm yết.</p><p>Đã tải riêng tháng 09/2025 của SOL, BNB và 1000PEPE từ kho công khai Binance, xác minh SHA-256 theo CHECKSUM và so với kho cục bộ:</p><div class="scroll"><table><thead><tr><th>Coin</th><th>Bản ghi funding</th><th>Thiếu / khác funding</th><th>Nến 5 phút</th><th>Thiếu / khác OHLC</th></tr></thead><tbody>__HISTORY__</tbody></table></div><p>Kết quả mẫu khớp; không suy rộng thành “toàn bộ kho đã được kiểm chứng”. Funding đối chiếu theo giây để chấp nhận sai lệch mili giây của lịch thanh toán; từng nguồn vẫn giữ thời điểm gốc. Mark Price liên tục, bậc maintenance margin và sổ lệnh lịch sử cần kiểm tra riêng trước backtest tài khoản dài hạn.</p></section>
<section class="panel"><h2>Trạng thái mục tiêu</h2><p>Mục tiêu vẫn là ít nhất 50% mỗi tháng sau mọi chi phí và định giá vị thế mở. Chưa đạt, chưa bật live, chưa tăng vốn mỗi vị thế. Bước tiếp theo có cơ sở hơn là mở rộng thời kỳ và tập coin theo thông tin có sẵn trước kỳ, rồi kiểm tra các cơ chế tín hiệu mới; không tiếp tục chỉ chỉnh TP trên cùng vài tháng.</p><p>87 kiểm thử đạt; 96 sổ giao dịch được đối soát; 42 bảng thống kê sự kiện và bốn đường tài khoản tái lập chính xác. Giới hạn còn nguyên: lịch sử đã xem nhiều lần, danh sách hợp đồng hiện tại có thiên lệch sống sót, MMR 1% là mô hình thay thế và giả định trượt giá chưa có sổ lệnh chứng minh.</p><a href="report.md">Báo cáo</a> · <a href="portfolio_comparison.csv">Mô phỏng tài khoản</a> · <a href="development.json">240 kết quả sàng lọc</a> · <a href="long_history_audit.json">Đối chiếu kho dữ liệu</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc</a></section></html>"""
    for key, value in dict(
        STYLE=style,
        SCREEN="".join(screen_rows),
        ACCOUNTS="".join(account_rows),
        HISTORY="".join(history_rows),
    ).items():
        html = html.replace(f"__{key}__", value)
    (OUT / "dashboard.html").write_text(html, encoding="utf-8")
    md = [
        "# Mục tiêu 50% mỗi tháng — lượt 02",
        "",
        "Mục tiêu chưa đạt. 48 quy tắc tín hiệu × năm thời gian giữ = 240 tổ hợp sàng lọc; hai ứng viên chẩn đoán tạo tổng cộng 16 cấu hình tài khoản × ba kỳ × hai mức chi phí = 96 lượt tài khoản. Không tăng vốn và không bật live.",
        "",
        "Không có tổ hợp sàng lọc đạt cận dưới 95% dương ở cả mức cơ sở và cao trong tháng phát triển. Chọn một tổ hợp mỗi nhóm để chẩn đoán tiếp, không tuyên bố chúng có lợi thế.",
        "",
        "## Lợi suất sự kiện (trên danh nghĩa, không phải tài khoản)",
        "",
        "| Nhóm / thời gian | Mẫu tháng 2/3 | T2 cơ sở | T2 cao | T3 cơ sở | T3 cao | T3 trượt giá thấp |",
        "|---|---:|---:|---:|---:|---:|---:|",
        *md_screen,
        "",
        "Các sự kiện chồng lấn không được cộng thành lợi nhuận tài khoản. Trượt giá thấp 2bps chỉ là giả định chưa xác minh. Funding tính trong (vào,ra]. Cuối kỳ chưa đủ thời gian quan sát được ghi riêng. Bootstrap cụm đồng bộ giữa coin theo khối 7 ngày, chưa hiệu chỉnh thử nhiều biến thể.",
        "",
        "## Tài khoản 500 USDT, 25 USDT danh nghĩa/vị thế",
        "",
        "| Phương án | Tài sản cuối | T1 | T2 | T3 | Mở vị thế |",
        "|---|---:|---:|---:|---:|---:|",
        *md_accounts,
        "",
        "Không SL vẫn có time exit 1h/4h và TP tối đa5USDT; không phải giữ lỗ vô hạn. Mỗi tháng dùng tài sản đầu tháng liên tục. Trường hợp cuối kỳ 0% có thể đã bị khóa mở mới do DD20%.",
        "",
        "## Kho dài hơn",
        "",
        "25/30 coin hiện tại có đủ số nến trong khoảng 2025-09-01–2026-06-01. Mẫu SOL/BNB/1000PEPE tháng09/2025: giá OHLC và funding khớp kho công khai Binance có checksum, không thiếu dòng mẫu. Không suy rộng thành kiểm chứng toàn bộ lịch sử; cần chọn universe trước kỳ, xử lý listing/delisting, kiểm chứng Mark Price và maintenance tiers.",
        "",
        s["protocol"]["limitations"],
        "",
        "87 kiểm thử; 96 sổ đối soát; 42 thống kê và bốn đường tài khoản tái lập chính xác. Cấu hình thật giữ nguyên. Mục tiêu tiếp tục, chưa hoàn thành.",
        "",
        "[Dashboard](dashboard.html) · [Mô phỏng](portfolio_comparison.csv) · [Kho dữ liệu](long_history_audit.json) · [Đối soát](verification.json)",
    ]
    (OUT / "report.md").write_text("\n".join(md), encoding="utf-8")
    print(OUT / "dashboard.html")


if __name__ == "__main__":
    main()
