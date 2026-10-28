"""Monthly equity target progress: show failures and keep the goal unachieved."""

import json
from html import escape

import pandas as pd
from plotly.offline import get_plotlyjs
from search_monthly_target import NAMES, OUT, ROOT


def label(spec):
    source = spec["source"]
    exits = dict(
        tp05="TP 0,50 / SL 0,50 / 12h",
        tp1="TP 1 / SL 1 / 24h",
        atr2="TP 2 ATR / SL 1 / 24h",
        trail2="Trailing 2 ATR, hồi 1% / SL 1 / 48h",
        nostop="TP 1 / không SL, không thời hạn",
    )
    return f"{NAMES[spec['family']]} · {'BTC giảm' if source['regime'] == 'btc_bear' else 'Không lọc BTC'} · cách {source['cooldown_hours']}h · {exits[spec['exit']]} · {spec['cap']} vị thế · {spec['parts']} phần"


def main():
    s = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    benchmark = json.loads(
        (OUT / "prior_monthly_benchmarks.json").read_text(encoding="utf-8")
    )
    rows = [r for r in s["results"] if r["window"] == "full"]
    specs = [
        dict(
            f["spec"],
            display=label(f["spec"]),
            primary=f["primary"],
            selected=f["selected"],
        )
        for f in sorted(
            s["finalists"],
            key=lambda f: (not f["primary"], not f["selected"], f["spec"]["id"]),
        )
    ]
    cards = []
    md_rows = []
    for spec in specs:
        rr = [r for r in rows if r["strategy_id"] == spec["id"]]
        months = []
        for i in range(3):
            values = [
                r["monthly"]["months"][i]["return_fraction"] * 100
                for r in rr
                if r["monthly"]["complete"]
            ]
            months.append(
                f"{min(values):.2f} đến {max(values):.2f}%"
                if len(values) == 2
                else "Không hoàn tất"
            )
        endings = [r["ending_equity"] for r in rr]
        ending = (
            f"{min(endings):.2f}–{max(endings):.2f}"
            if all(x is not None for x in endings)
            else "Không hoàn tất"
        )
        cards.append(
            f"<tr><td>{escape(spec['display'])}</td>{''.join('<td>' + m + '</td>' for m in months)}<td>{ending}</td></tr>"
        )
        md_rows.append(f"| {spec['display']} | {' | '.join(months)} | {ending} |")
    curves = {}
    for row in rows:
        f = pd.read_parquet(OUT / "runs" / f"{row['id']}_equity.parquet")
        grouped = f.groupby(f["at"] // 3600000)
        indices = sorted(
            set(grouped.equity.idxmin())
            | set(grouped.equity.idxmax())
            | {0, len(f) - 1}
        )
        f = f.loc[indices]
        curves[row["id"]] = dict(x=f["at"].tolist(), y=f.equity.tolist())
    benchmark_table = []
    for row in benchmark:
        if row["observation_minutes"] != 5:
            continue
        months = [
            f"{m['return_fraction'] * 100:.2f}%" for m in row["monthly"]["months"]
        ]
        benchmark_table.append(
            f"<tr><td>{escape(row['label'])} · {'cơ sở' if row['cost'] == 'base' else 'cao'}</td>{''.join('<td>' + m + '</td>' for m in months)}<td>{row['ending_equity']:.2f}</td></tr>"
        )
    data = json.dumps(
        dict(rows=rows, specs=specs, curves=curves, primary=s["primary"]),
        ensure_ascii=False,
        allow_nan=False,
    ).replace("</", "<\\/")
    old = (ROOT / "artifacts/short_entry_search_20260925/dashboard.html").read_text(
        encoding="utf-8"
    )
    style = old.split("<style>", 1)[1].split("</style>", 1)[0]
    html = """<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Mục tiêu 50% mỗi tháng</title><style>__STYLE__ #monthly{height:330px}</style>
<h1>Nghiên cứu mục tiêu 50% mỗi tháng</h1><p>Lượt mở rộng 01 · 24/06–24/09/2026 UTC · Vốn 500 USDT · x5 · 5 USDT ký quỹ/vị thế · Tối đa 1 hoặc 5 vị thế</p>
<div class="notice"><b>Mục tiêu chưa đạt. Chưa có chiến lược đủ bằng chứng để bật live.</b><p>264 cấu hình mới, 612 lượt mô phỏng. Không có phương án đạt 50% ở cả ba tháng. Ứng viên khóa trước tháng cuối là hồi EMA rồi bị từ chối, trailing sau 2 ATR/hồi 1%, chia ba, tối đa một vị thế; tài khoản toàn kỳ còn 486,70–497,06 USDT. Mục tiêu nghiên cứu vẫn đang mở, cấu hình thật không đổi.</p></div>
<div class="cards"><div class="card">Điểm xuất phát<strong>500 USDT</strong></div><div class="card">Mốc tháng 1<strong>750</strong></div><div class="card">Mốc tháng 2<strong>1.125</strong></div><div class="card">Mốc tháng 3<strong>1.687,50</strong></div></div>
<section class="panel"><h2>Mục tiêu được đo thế nào?</h2><p>Lợi nhuận tháng = tài sản cuối tháng / tài sản đầu tháng − 1, sau phí và funding, định giá cả các lệnh chưa đóng. Không cộng riêng lãi đã chốt, không bỏ vị thế lỗ và không coi tổng ba tháng đạt 50% là đạt 50% mỗi tháng.</p><p>Ba khoảng tháng liên tiếp: 24/06–24/07, 24/07–24/08, 24/08–24/09. Tài khoản chạy liên tục; các tháng sau không quay lại 500 USDT. Mốc tính là trạng thái tài khoản tại ranh giới 5 phút, sau xử lý bước mô phỏng. Đạt mốc lịch sử chưa đủ chứng minh khả năng lặp lại trong tương lai.</p><p>Với TP ròng 0,50 USDT, riêng mục tiêu +250 USDT tháng đầu cần 500 lệnh thắng nếu không có lệnh lỗ. TP ròng 5 USDT cần 50 lệnh thắng cùng giả định. Đây là phép tính về quy mô mục tiêu, không phải dự báo số lệnh có thể thực hiện. Ngân sách hiện tại tối đa 125 USDT danh nghĩa ban đầu cho năm vị thế; bản chia phần thường dùng ít hơn.</p></section>
<section class="panel"><h2>Bốn nhóm tín hiệu mới</h2><ul><li><b>Phá đỉnh thất bại:</b> vượt đỉnh 24 giờ trước nhưng đóng nến trở lại dưới đỉnh, nến giảm và khối lượng ít nhất bằng trung bình 24 giờ trước.</li><li><b>Tăng mạnh bị bán xuống:</b> tăng ít nhất 10% trong 6 giờ, râu trên ít nhất 50% nến, nến giảm, biên độ ít nhất 2 ATR và khối lượng ít nhất 1,5 lần trung bình trước đó.</li><li><b>Hồi EMA rồi bị từ chối:</b> EMA 20 dưới EMA 60, giá chạm EMA 20 nhưng đóng dưới nó, nến giảm và lợi suất 24 giờ âm.</li><li><b>Giảm mạnh kèm khối lượng:</b> xu hướng giảm, đóng dưới đáy 12 giờ trước, biên độ ≥1,5 ATR, khối lượng ≥1,5 lần và giá đóng trong 25% dưới của nến.</li></ul><p>Mỗi nhóm thử không lọc BTC hoặc chỉ khi BTC giảm; tín hiệu cùng coin cách ít nhất 6/24 giờ. Vào một lần hoặc ba phần, tối đa 1/5 vị thế, bốn cách thoát. Giữ thêm tám đối chứng không SL/thời hạn. Cần 120 giờ dữ liệu đủ và thanh khoản 24 giờ ≥2 triệu USDT. Không dùng dữ liệu tương lai để chọn tín hiệu.</p></section>
<section class="panel"><h2>Lợi nhuận từng tháng của các cấu hình giữ lại</h2><p>Khoảng số là hai giả định chi phí, không phải khoảng tin cậy. SL/time exit của từng cấu hình được nêu trong tên; SL tiền giảm theo tỷ lệ phần đã vào và có thể vượt mức khi khớp thực tế. Danh sách gồm sáu ứng viên qua vòng phát triển và tám đối chứng không SL. Nhóm tăng mạnh bị bán xuống không đủ 20 vị thế đóng trong tháng phát triển để chọn ứng viên, vẫn giữ đối chứng cho minh bạch.</p><div class="scroll"><table><thead><tr><th>Quy tắc</th><th>Tháng 1</th><th>Tháng 2</th><th>Tháng 3</th><th>Tài sản cuối (USDT)</th></tr></thead><tbody>__TABLE__</tbody></table></div></section>
<section class="panel"><h2>Xem đường tài sản và khoảng cách tới mục tiêu</h2><select id="strategy" aria-label="Phương án"></select><div id="monthly"></div><div id="chart"></div><div class="scroll"><table><thead><tr><th>Chi phí</th><th>Tài sản cuối</th><th>DD</th><th>Mở / đóng / còn</th><th>Danh nghĩa TB</th><th>Phí / funding</th><th>Giữ lâu nhất</th></tr></thead><tbody id="detail"></tbody></table></div><p id="description"></p><p>Phí cơ sở 0,05% mỗi chiều, trượt giá 0,20%; trường hợp cao 0,10% và 0,50%. Funding theo lịch sử. Biểu đồ toàn kỳ giữ cực trị theo giờ, số đo tính mỗi 5 phút; trailing lấy mẫu 5 phút, chưa mô phỏng chính xác trailing liên tục trên Binance.</p></section>
<section class="panel"><h2>Đối chiếu lại những ứng viên cũ theo từng tháng</h2><p>Các dòng sau đều quan sát trailing mỗi 5 phút; cùng đường tài sản đã chạy trước, chỉ tính lại lợi nhuận tháng liên tiếp. Không chọn lại ứng viên cũ theo bảng này.</p><div class="scroll"><table><thead><tr><th>Phương án / chi phí</th><th>Tháng 1</th><th>Tháng 2</th><th>Tháng 3</th><th>Tài sản cuối</th></tr></thead><tbody>__BENCHMARK__</tbody></table></div></section>
<section class="panel"><h2>Bằng chứng hiện có và phần việc còn lại</h2><p>Trong tháng phát triển, ngay cả kết quả cao nhất của 264 cấu hình mới cũng chỉ lãi 8,41 USDT (1,68%). Đây là kết quả được chọn sau khi nhìn toàn bộ tháng phát triển, không phải lợi nhuận có thể kỳ vọng. Tăng số lần giao dịch chưa giải quyết được thiếu lợi thế sau chi phí.</p><p>Đã giữ khóa lựa chọn: tối đa hai cấu hình mỗi nhóm theo PnL thấp nhất ở hai giả định, DD dưới 20%, ít nhất 20 vị thế đóng; chọn ứng viên theo tháng xác nhận trước khi chạy tháng cuối. Lượt này không có cấu hình đạt 50% ở mọi tháng. Thử nhiều cấu hình trên cùng lịch sử có thể <a href="https://sdm.lbl.gov/oapapers/ssrn-id2507040-bailey.pdf">khớp quá mức dữ liệu</a>; không coi việc tìm được một kết quả đẹp là bằng chứng đầy đủ.</p><p>83 kiểm thử đạt, 16 tập tín hiệu tái lập và kiểm tra cắt dữ liệu tương lai, 31 tập đặc trưng có checksum, 84 sổ kết quả được đối soát, hai đường tài sản ứng viên tái lập chính xác. Cấu hình thật không thay đổi. Dữ liệu đã dùng nhiều lần, danh sách hợp đồng hiện tại có thiên lệch sống sót; chưa có sổ lệnh và bậc maintenance margin lịch sử. Mô phỏng dùng MMR 1%; xem <a href="https://www.binance.com/en/support/faq/detail/360033525271">cơ chế thanh lý Binance</a> để phân biệt với thanh lý thực tế.</p><p>Hướng tiếp theo: kiểm tra giới hạn quy mô và tần suất, cải thiện tín hiệu theo trạng thái thị trường, mở rộng thời kỳ dữ liệu và kiểm tra tương lai độc lập. Không tăng vốn hoặc bật live chỉ để đạt con số mục tiêu trong báo cáo.</p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">Tất cả lượt chạy</a> · <a href="protocol.json">Quy tắc nghiên cứu</a> · <a href="verification.json">Đối soát</a> · <a href="goal_progress.json">Tiến trình mục tiêu</a></section>
<script>__PLOTLY__</script><script>
const D=__DATA__,el=id=>document.getElementById(id),f=x=>x===null||x===undefined?'—':x.toLocaleString('vi-VN',{minimumFractionDigits:2,maximumFractionDigits:2}),cn=r=>r.cost==='base'?'Cơ sở':'Cao';el('strategy').innerHTML=D.specs.map(s=>`<option value="${s.id}">${s.primary?'Đã khóa: ':''}${s.display}</option>`).join('');el('strategy').value=D.primary;
function update(){const rows=D.rows.filter(r=>r.strategy_id===el('strategy').value);const common={paper_bgcolor:'#111f33',plot_bgcolor:'#111f33',font:{color:'#becce0'},margin:{l:60,r:20,t:20,b:60},legend:{orientation:'h',y:-.2}};Plotly.react('monthly',rows.map(r=>({x:['24/06–24/07','24/07–24/08','24/08–24/09'],y:r.monthly.months.map(m=>m.return_fraction*100),type:'bar',name:cn(r)})),{...common,barmode:'group',yaxis:{title:{text:'% / tháng'},range:[Math.min(-5,...rows.flatMap(r=>r.monthly.months.map(m=>m.return_fraction*100)))-2,55],gridcolor:'#30465f'},shapes:[{type:'line',xref:'paper',x0:0,x1:1,y0:50,y1:50,line:{color:'#eab54f',dash:'dash'}}],annotations:[{xref:'paper',x:1,y:50,text:'Mục tiêu +50%',showarrow:false,yshift:12,font:{color:'#eab54f'}}]},{responsive:true,displaylogo:false});Plotly.react('chart',rows.map(r=>({x:D.curves[r.id].x,y:D.curves[r.id].y,type:'scatter',mode:'lines',name:cn(r)})),{...common,xaxis:{type:'date',gridcolor:'#30465f'},yaxis:{title:{text:'USDT'},gridcolor:'#30465f'}},{responsive:true,displaylogo:false});el('detail').innerHTML=rows.map(r=>`<tr><td>${cn(r)}</td><td>${f(r.ending_equity)}</td><td>${f(r.max_drawdown*100)}%</td><td>${r.entries}/${r.exits}/${r.open_count}</td><td>${f(r.mean_deployed_notional)}</td><td>${f(r.fees)} / ${f(r.funding)}</td><td>${f(r.max_hold_days)} ngày</td></tr>`).join('');el('description').textContent=rows.map(r=>cn(r)+': '+r.source_events+' tín hiệu, '+r.adds+' lần thêm phần; '+(r.paused?'đã khóa mở mới':'chưa khóa mở mới')+'.').join(' ');}el('strategy').onchange=update;update();</script></html>"""
    for key, value in dict(
        STYLE=style,
        TABLE="".join(cards),
        BENCHMARK="".join(benchmark_table),
        PLOTLY=get_plotlyjs(),
        DATA=data,
    ).items():
        html = html.replace(f"__{key}__", value)
    (OUT / "dashboard.html").write_text(html, encoding="utf-8")
    md = [
        "# Mục tiêu 50% mỗi tháng — lượt 01",
        "",
        "Mục tiêu chưa đạt, tiếp tục nghiên cứu. Vốn 500 USDT, x5, ngân sách 25 USDT danh nghĩa/vị thế, tối đa 1/5 vị thế. 264 cấu hình, 612 lượt mô phỏng; không thay cấu hình thật.",
        "",
        "50% mỗi tháng trên tài sản đầu tháng nghĩa là 500 → 750 → 1125 → 1687,50 USDT. Tính cả phí, funding và định giá vị thế mở. Bảng dùng tài khoản liên tục, ba khoảng 24/06–24/07–24/08–24/09/2026 UTC.",
        "",
        "| Quy tắc | Tháng 1 | Tháng 2 | Tháng 3 | Tài sản cuối |",
        "|---|---:|---:|---:|---:|",
        *md_rows,
        "",
        "Khoảng là hai giả định chi phí, không phải khoảng tin cậy. Những dòng không SL là đối chứng, không phải chiến lược được chọn. Sáu ứng viên chính và tám đối chứng giữ lại; nhóm exhaustion không đủ mẫu để có ứng viên.",
        "",
        "Ứng viên được khóa trước tháng cuối: hồi EMA rồi bị từ chối, không lọc BTC, cooldown24h, trailing2ATR/1%, SL1USDT theo tỷ lệ đã vào, thời hạn48h, một vị thế, ba phần. Kết quả toàn kỳ 486,70–497,06 USDT. Chưa có bằng chứng đáp ứng mục tiêu.",
        "",
        "## Quy mô cần thiết",
        "",
        "+250 USDT tháng đầu cần 500 lệnh thắng nếu mỗi lệnh lời ròng 0,50 và không có lệnh lỗ; hoặc 50 lệnh thắng ròng 5 USDT với cùng giả định. Đây chỉ là phép tính quy mô, không phải cam kết tần suất hoặc tỷ lệ thắng. Kết quả tháng phát triển cao nhất toàn bộ cấu hình là +8,41 USDT; không được gọi là kết quả ngoài mẫu.",
        "",
        "## Phương pháp",
        "",
        s["protocol"]["selection"],
        "",
        s["protocol"]["execution"],
        "",
        s["protocol"]["limitations"],
        "",
        "83 kiểm thử đạt; 16 tập tín hiệu tái lập/prefix invariance, 31 tập đặc trưng có checksum; 84 sổ được đối soát; hai đường ứng viên tái lập chính xác. Các tháng đã được xem nhiều lần; không chứng minh 50%/tháng tương lai.",
        "",
        "Mục tiêu còn mở. Bước tiếp theo: giới hạn quy mô/tần suất, tín hiệu theo trạng thái thị trường, dữ liệu dài hơn và đánh giá tương lai. Giữ nguyên tài khoản thật.",
        "",
        "[Dashboard](dashboard.html) · [Lượt chạy](comparison.csv) · [Quy tắc](protocol.json) · [Đối soát](verification.json)",
        "",
        "[Nghiên cứu khớp quá mức backtest](https://sdm.lbl.gov/oapapers/ssrn-id2507040-bailey.pdf) · [Thanh lý Binance](https://www.binance.com/en/support/faq/detail/360033525271)",
    ]
    (OUT / "report.md").write_text("\n".join(md), encoding="utf-8")
    print(OUT / "dashboard.html")


if __name__ == "__main__":
    main()
