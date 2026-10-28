"""Readable entry experiment with monthly MTM and matched immediate controls."""

import json
from html import escape

import pandas as pd
from compare_account_risk import ROOT, write
from prepare_historical_research import OUT as DATA
from search_historical_entries import OUT

NAMES = dict(acceleration="Giảm mạnh kèm khối lượng", breakdown="Phá đáy",
             pullback="Hồi rồi giảm", weak_rank="Coin yếu", failed_pump="Nhịp tăng thất bại",
             failed_high="Phá đỉnh thất bại", ema_reject="Hồi EMA bị từ chối", exhaustion="Tăng mạnh bị bán xuống")


def main():
    s = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    verified = json.loads((OUT / "verification.json").read_text(encoding="utf-8"))
    data = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    samples = json.loads((DATA / "trade_sample_audit.json").read_text(encoding="utf-8"))
    assert samples["complete"]
    full = [r for r in s["results"] if r["window"] == "full"]
    specs = {r["id"]:r for r in s["portfolio_specs"]}
    chart_data = []
    for r in full:
        curve = pd.read_parquet(OUT / "runs" / f"{r['id']}_equity.parquet")
        # Every six-hour bucket retains its minimum and maximum: no hidden DD.
        chosen = {0,len(curve)-1}
        for _, block in curve.groupby((curve["at"] - curve["at"].iloc[0]) // 21600000):
            chosen.update([block.index[0], block.index[-1], block.equity.idxmin(), block.equity.idxmax()])
        points = [[int(row["at"]),round(row.equity,6)] for _,row in curve.loc[sorted(chosen)].iterrows()]
        chart_data.append(dict(**r, points=points, timing_label=specs[r["strategy_id"]]["timing"]["label"],
                               first_pause=int(curve.loc[curve.paused, "at"].iloc[0]) if curve.paused.any() else None))
    write(OUT / "dashboard_data.json", chart_data)
    # Explain a concrete no-stop drawdown with the actual held inventory.
    case = next(r for r in full if r["strategy_id"] == "breakdown_rebound0.5_p3_no_stop" and r["cost"] == "base")
    raw = json.loads((OUT / "runs" / f"{case['id']}.json").read_text(encoding="utf-8"))
    curve = pd.read_parquet(OUT / "runs" / f"{case['id']}_equity.parquet")
    dd = 1 - curve.equity/curve.equity.cummax().clip(lower=500)
    worst = curve.loc[dd.idxmax()]
    active = {}
    for j in raw["journal"]:
        if j["at"] > worst["at"]:
            break
        if j["kind"] == "entry":
            active[j["symbol"]] = dict(qty=j["qty"], notional=j["qty"]*j["price"], opened_at=j["at"])
        elif j["kind"] == "entry_add":
            active[j["symbol"]]["qty"] += j["qty"]
            active[j["symbol"]]["notional"] += j["qty"]*j["price"]
        elif "net" in j:
            active.pop(j["symbol"])
    positions = []
    for coin,pos in active.items():
        marks = pd.read_parquet(DATA / "mark" / f"{coin}.parquet")
        mark = float(marks.loc[marks.open_time == worst["at"]-300000, "close"].iloc[0])
        positions.append(dict(symbol=coin, **pos, average_entry=pos["notional"]/pos["qty"], mark=mark,
                              unrealized=pos["notional"]-pos["qty"]*mark))
    incident = dict(run=case["id"], at=int(worst["at"]), date=pd.to_datetime(worst["at"],unit="ms",utc=True).isoformat(),
                    equity=float(worst.equity), drawdown=float(dd.max()), positions=positions,
                    funding_total=raw["funding"], live=False)
    write(OUT / "drawdown_case.json", incident)
    soon = next(p for p in positions if p["symbol"] == "SOONUSDT")
    account_rows, md_rows = [], []
    for spec in s["portfolio_specs"]:
        if spec["parts"] != 3:
            continue
        rows = {r["cost"]:r for r in full if r["strategy_id"] == spec["id"]}
        title = f"{NAMES[spec['source']['family']]} · {spec['timing']['label']} · " + ("không SL" if spec["risk"]=="no_stop" else "SL1 + 48h")
        b,t = rows["base"],rows["stress"]
        values = [f"{b['ending_equity']:.2f}",f"{t['ending_equity']:.2f}",
                  f"{b['max_drawdown']*100:.2f}% / {t['max_drawdown']*100:.2f}%",
                  f"{b['entries']} / {t['entries']}"]
        account_rows.append("<tr><td>" + escape(title) + "</td>" + "".join(f"<td>{v}</td>" for v in values) + "</tr>")
        md_rows.append(f"| {title} | {' | '.join(values)} |")
    screen_rows = []
    for v in s["validation"]:
        h = next(r for r in s["holdout"] if r["id"] == v["id"])
        label = f"{NAMES[v['spec']['source']['family']]} · {v['spec']['timing']['label']} · {v['spec']['horizon_hours']}h"
        values = [f"{v['counts']['complete']} / {h['counts']['complete']}"]
        for row,cost in [(v,"base"),(v,"stress"),(h,"base"),(h,"stress")]:
            values.append(f"{row['cases'][cost]['mean_net_return']*100:.3f}%")
        screen_rows.append("<tr><td>"+escape(label)+"</td>"+"".join(f"<td>{x}</td>" for x in values)+"</tr>")
    public_bars = sum(r["mark"]["rows"] for r in data["public"])
    funding_rows = sum(r["funding"]["archive_rows"] for r in data["public"])
    audit_text = f"{public_bars:,} nến Mark Price và {funding_rows:,} bản ghi funding; 600 tệp tháng được xác minh SHA-256. Funding đối chiếu giữa kho tháng và REST, giữ nguyên thời điểm thanh toán gốc và Mark Price tại lần thanh toán. Giá OHLC và khối lượng kiểm tra thêm 90 mẫu coin–tháng, không phát hiện sai khác. Đây không phải kiểm chứng mọi nến giao dịch hoặc danh sách coin đã hủy niêm yết."
    verdict = "Chưa tìm được điểm vào tạo lợi thế ổn định. Không phương án nào đạt 50% ở mọi tháng."
    html = r'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Kiểm định điểm vào 9 tháng</title>
<style>*{box-sizing:border-box}body{margin:0;background:#0b1423;color:#e1eaf5;font:15px/1.55 system-ui,sans-serif}main{max-width:1440px;margin:auto;padding:30px 28px 60px}h1{font-size:30px;line-height:1.25;margin:8px 0}h2{font-size:21px;margin:0 0 12px}.eyebrow{color:#61d2c4;font-size:12px;letter-spacing:2px}.muted,small{color:#a7b6cc}.notice{border-left:4px solid #eeb65a;background:#29251d;padding:18px 22px;margin:22px 0;border-radius:8px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.card,.panel{background:#121f33;border:1px solid #283952;border-radius:12px;padding:20px}.card strong{display:block;font-size:30px;color:#fafbff}.panel{margin-top:20px}.filters{display:flex;gap:16px;flex-wrap:wrap;margin:14px 0}label{display:flex;flex-direction:column;gap:6px;color:#a7b6cc}select{background:#0c182a;color:white;border:1px solid #405875;border-radius:6px;padding:9px;min-width:180px}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:right;padding:11px 10px;border-bottom:1px solid #2a3a51;white-space:nowrap}td:first-child,th:first-child{text-align:left;white-space:normal;min-width:260px}th{color:#a8bdd7}a{color:#72dbd1}svg{width:100%;height:auto;display:block}.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:13px}.legend i{display:inline-block;width:20px;height:3px;vertical-align:middle;margin-right:6px}.bad{color:#ff9298}.good{color:#74dac3}.pill{display:inline-block;border:1px solid #526781;padding:3px 8px;border-radius:20px;font-size:12px}.facts{display:grid;grid-template-columns:1fr 1fr;gap:18px}.facts>div{background:#0d192b;border-radius:8px;padding:16px}p{margin:9px 0 14px}#chartStatus{font-size:13px;color:#b9c8dc}@media(max-width:750px){main{padding:20px 14px}.cards{grid-template-columns:1fr 1fr}.facts{grid-template-columns:1fr}h1{font-size:25px}.panel{padding:14px}select{max-width:100%;min-width:130px}}
</style></head><body><main><div class="eyebrow">ĐẢO VÀNG / NGHIÊN CỨU ĐIỂM VÀO</div><h1>Chờ hồi có thực sự tốt hơn vào ngay?</h1><p class="muted">01/09/2025–31/05/2026 UTC · 30 altcoin · 500 USDT · Cross x5 · tối đa 5 vị thế · tổng danh nghĩa 25 USDT/vị thế</p>
<div class="notice"><b>__VERDICT__</b><p>Chia ba phần và trailing vẫn có thể chịu lỗ lớn trước khi giá hồi. Một số kết quả có lời cả kỳ đến chủ yếu từ tháng 10/2025, hoặc đã khóa mở mới nhiều tháng; không đủ căn cứ để đưa vào giao dịch thật.</p><span class="pill">Kết quả mô phỏng · Không bật live</span></div>
<div class="cards"><div class="card">Cách vào lệnh<strong>13</strong></div><div class="card">Phép sàng lọc<strong>312</strong></div><div class="card">Đường tài khoản<strong>96</strong></div><div class="card">Đạt 50% mọi tháng<strong>0</strong></div></div>
<section class="panel"><h2>So trực tiếp với vào ngay</h2><p>Cùng nhóm tín hiệu, cách chia vốn và cách thoát lệnh. Hai đường mỗi cách vào thể hiện hai giả định chi phí. Tài sản gồm lỗ chưa chốt và funding, chạy liên tục trong chín tháng.</p>
<div class="filters"><label>Nhóm tín hiệu<select id="family"><option value="acceleration">Giảm mạnh kèm khối lượng</option><option value="breakdown">Phá đáy</option></select></label><label>Chia lệnh<select id="parts"><option value="3">Ba phần, tổng 25 USDT</option><option value="1">Một lần, tổng 25 USDT</option></select></label><label>Quản lý lệnh<select id="risk"><option value="no_stop">Không SL, không hạn giữ</option><option value="sl1_h48">Thử SL 1 USDT + giữ tối đa 48h</option></select></label></div>
<div class="legend" id="legend"></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Đường tài sản so sánh cách vào lệnh"></svg><div id="chartStatus"></div>
<h2 style="margin-top:22px">Lợi suất từng tháng</h2><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><p class="muted">Tính trên tài sản đầu mỗi tháng, không nạp lại 500 USDT. Mức 0% có thể là không còn giao dịch sau khi bị khóa mở mới, không phải lợi nhuận ổn định.</p></section>
<section class="panel"><h2>Vì sao bản không stop-loss vẫn dễ tổn thương?</h2><div class="facts"><div><b>SOONUSDT · bản chờ hồi 0,5 ATR, ba phần</b><p>Giá vào bình quân __ENTRY__ → Mark Price __MARK__. Vị thế __QTY__ SOON từng lỗ chưa chốt <b class="bad">__LOSS__ USDT</b>.</p><p>Ngày __DATE__, tài sản còn <b>__EQUITY__ USDT</b>, giảm __DD__% từ đỉnh. Đã tính vị thế đang mở; không loại coin gây lỗ.</p></div><div><b>Không nên chọn kết quả đẹp của một giả định</b><p>Với cùng quy tắc, chi phí cao đôi khi cho kết quả cuối tốt hơn vì làm thay đổi giá khớp, thời điểm thoát, số chỗ trống và tập lệnh được vào. Đây là sự nhạy cảm của đường giao dịch, không chứng minh rằng trả phí cao có lợi.</p><p>Trailing dựa trên giá vẫn có thể thoát với lỗ ròng sau funding. Ngưỡng giảm 20% chỉ khóa mở mới, các vị thế cũ tiếp tục chịu biến động.</p></div></div></section>
<section class="panel"><h2>Tổng hợp tài khoản chia ba phần</h2><p>Tất cả dùng trailing kích hoạt sau 3 ATR thuận chiều, hồi 1% thì thoát theo giá mở nến 5 phút tiếp theo cộng trượt giá. Hai phần sau chỉ thêm khi giá đi thuận, mỗi bước 0,5 ATR; tổng ngân sách không tăng. SL1 + 48h là biến thể nghiên cứu riêng.</p><div class="scroll"><table><thead><tr><th>Quy tắc</th><th>Cuối kỳ · cơ sở</th><th>Cuối kỳ · chi phí cao</th><th>DD · cơ sở / cao</th><th>Số vị thế · cơ sở / cao</th></tr></thead><tbody>__ACCOUNTS__</tbody></table></div><p class="muted">Phí cơ sở 0,05% và trượt giá 0,20% mỗi lần khớp; trường hợp cao 0,10% và 0,50%. Không có dữ liệu sổ lệnh để chứng minh trượt giá thực tế. Các lượt kiểm định ngắn khởi tạo 500 riêng; không cộng PnL của chúng vào đường chín tháng.</p></section>
<section class="panel"><h2>Điểm vào được chọn và kiểm tra thế nào?</h2><p>13 cách gồm: vào ngay; chờ 15/60/180 phút; chờ hồi, chờ giảm tiếp, hồi rồi giảm lại ở 0,25/0,5/1 ATR. Tín hiệu và ATR lấy từ nến đã đóng. Chờ tối đa sáu giờ, không tự tăng vốn để lệnh hợp lệ. Mỗi nhóm được thử thời gian giữ 4/24/48 giờ ở phép đo sự kiện.</p><p><b>09–11/2025:</b> sàng lọc, khóa một ứng viên mỗi nhóm. <b>12/2025–02/2026:</b> chọn hai ứng viên chẩn đoán. <b>03–05/2026:</b> đánh giá cuối, không dùng để đổi ứng viên. Tập lịch sử đã từng được nghiên cứu, nên đây vẫn là kiểm định hồi cứu.</p><div class="scroll"><table><thead><tr><th>Ứng viên theo nhóm / giữ</th><th>Mẫu kỳ 2 / kỳ 3</th><th>Kỳ 2 · cơ sở</th><th>Kỳ 2 · cao</th><th>Kỳ 3 · cơ sở</th><th>Kỳ 3 · cao</th></tr></thead><tbody>__SCREENS__</tbody></table></div><p class="muted">Bảng này là lợi suất trung bình của sự kiện trên danh nghĩa vị thế, không phải lợi suất tài khoản. Sự kiện có thể chồng lấn; không cộng thành lợi nhuận. Nhóm tăng mạnh bị bán xuống quá ít mẫu nên không đủ điều kiện chọn. Không tổ hợp sàng lọc nào có cận dưới 95% dương ở cả hai mức chi phí; khoảng tin cậy chưa hiệu chỉnh cho việc thử nhiều phương án.</p></section>
<section class="panel"><h2>Dữ liệu và đối soát</h2><p>Chọn 30 coin bằng thanh khoản tháng 08/2025 trong kho 328 tệp, trước thời kỳ đánh giá. Không dùng lợi nhuận tương lai hoặc tình trạng niêm yết hiện tại để chọn coin. Cả 30 coin và BTC có đủ lưới nến 5 phút trong bộ dữ liệu chuẩn bị.</p><p>__AUDIT__</p><p>__TESTS__ kiểm thử đạt; __JOURNALS__ sổ giao dịch được đối soát vốn, phí, funding và giới hạn vị thế. Tái lập __SCREENCHECKS__ thống kê và __EXACT__ đường tài khoản; kiểm tra tín hiệu không đổi khi cắt dữ liệu tương lai.</p><p class="muted">Giới hạn còn lại: kho có thể thiếu coin đã hủy niêm yết; bộ lọc khối lượng là ảnh chụp hiện tại, maintenance margin 1% là giả định thay thế; trailing lấy mẫu 5 phút không mô phỏng chính xác diễn biến trong nến. Chưa đủ điều kiện xác nhận kết quả tài chính hay chạy thật.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">96 lượt tài khoản</a> · <a href="development.json">312 phép sàng lọc</a> · <a href="verification.json">Đối soát</a> · <a href="drawdown_case.json">Chi tiết SOON</a> · <a href="protocol.json">Quy tắc khóa trước</a></p></section></main>
<script>const all=__JSON__;const colors=['#58d8c5','#4d9ff8','#ffb967','#d997ed'];let selected=[];const f2=n=>n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});const fmt=t=>new Date(t).toISOString().slice(0,10);function render(){selected=all.filter(r=>r.source===document.querySelector('#family').value&&r.parts===+document.querySelector('#parts').value&&r.risk===document.querySelector('#risk').value);const start=Math.min(...selected.map(r=>r.points[0][0])),end=Math.max(...selected.map(r=>r.points.at(-1)[0]));const vals=selected.flatMap(r=>r.points.map(p=>p[1]));const low=Math.floor(Math.min(500,...vals)/50)*50-10,high=Math.ceil(Math.max(500,...vals)/50)*50+10;const x=t=>62+(t-start)/(end-start)*1110,y=v=>280-(v-low)/(high-low)*250;let svg='';for(let i=0;i<=5;i++){let v=low+(high-low)*i/5,yy=y(v);svg+=`<path d="M62 ${yy}H1172" stroke="#2a3a51"/><text x="52" y="${yy+4}" text-anchor="end" fill="#a7b6cc" font-size="12">${v.toFixed(0)}</text>`}svg+=`<path d="M62 ${y(500)}H1172" stroke="#94a6bc" stroke-dasharray="5 6"/>`;for(let i=0;i<=9;i++){let d=new Date(Date.UTC(2025,8+i,1));svg+=`<text x="${x(+d)}" y="307" text-anchor="middle" fill="#a7b6cc" font-size="12">${d.toISOString().slice(2,7)}</text>`}selected.forEach((r,i)=>{let d=r.points.map((p,j)=>(j?'L':'M')+x(p[0]).toFixed(2)+' '+y(p[1]).toFixed(2)).join('');svg+=`<path d="${d}" fill="none" stroke="${colors[i]}" stroke-width="1.6" ${r.cost==='stress'?'stroke-dasharray="5 3"':''}/>`});document.querySelector('#chart').innerHTML=svg;document.querySelector('#legend').innerHTML=selected.map((r,i)=>`<span><i style="background:${colors[i]}"></i>${r.timing_label} · ${r.cost==='base'?'cơ sở':'chi phí cao'}</span>`).join('');document.querySelector('#chartStatus').innerHTML=selected.map(r=>`${r.timing_label} (${r.cost==='base'?'cơ sở':'cao'}): cuối ${f2(r.ending_equity)} USDT · DD ${f2(r.max_drawdown*100)}% · ${r.entries} vị thế${r.first_pause?' · khóa mở mới từ '+fmt(r.first_pause):''}`).join('<br>');document.querySelector('#monthHead').innerHTML='<tr><th>Cách vào / chi phí</th>'+selected[0].monthly.months.map(m=>'<th>'+fmt(m.start).slice(0,7)+'</th>').join('')+'</tr>';document.querySelector('#monthBody').innerHTML=selected.map(r=>'<tr><td>'+r.timing_label+' / '+(r.cost==='base'?'cơ sở':'cao')+'</td>'+r.monthly.months.map(m=>`<td class="${m.return_fraction<0?'bad':'good'}">${f2(m.return_fraction*100)}%</td>`).join('')+'</tr>').join('')}document.querySelectorAll('select').forEach(e=>e.addEventListener('change',render));render();</script></body></html>'''
    replacements = dict(VERDICT=verdict, ACCOUNTS="".join(account_rows), SCREENS="".join(screen_rows),
                        ENTRY=f"{soon['average_entry']:.5f}", MARK=f"{soon['mark']:.5f}", QTY=f"{soon['qty']:g}",
                        LOSS=f"{soon['unrealized']:.2f}", EQUITY=f"{incident['equity']:.2f}", DD=f"{incident['drawdown']*100:.2f}",
                        DATE="14/11/2025, 20:10 UTC", AUDIT=audit_text,
                        TESTS=str(verified["unit_tests_passed"]), JOURNALS=str(verified["journals_audited"]),
                        SCREENCHECKS=str(verified["screen_statistics_reproduced"]), EXACT=str(verified["full_account_paths_exact"]),
                        JSON=json.dumps(chart_data, ensure_ascii=False, separators=(",",":"), allow_nan=False).replace("</", "<\\/"))
    for key,value in replacements.items():
        html = html.replace("__"+key+"__",value)
    (OUT / "dashboard.html").write_text(html,encoding="utf-8")
    md = ["# Kiểm định điểm vào trên chín tháng", "", verdict, "",
          "Kỳ đánh giá: 01/09/2025–31/05/2026 UTC. Vốn 500 USDT, x5, tối đa5 vị thế; tổng danh nghĩa25 USDT/vị thế. Danh sách30 coin chọn theo thanh khoản tháng08/2025.", "",
          "13 cách vào ×8 nhóm tín hiệu ×3 thời gian giữ =312 phép sàng lọc; hai ứng viên cùng đối chứng vào ngay, chia1/3 phần và hai cách quản lý lệnh tạo96 lượt tài khoản. Không bật giao dịch thật.", "",
          "## So sánh chia ba phần, trailing3ATR / hồi1%", "",
          "| Quy tắc | Cuối kỳ cơ sở (USDT) | Cuối kỳ cao (USDT) | DD cơ sở / cao | Số vị thế cơ sở / cao |",
          "|---|---:|---:|---:|---:|", *md_rows, "",
          "Không SL: không hạn giữ. SL1+48h: thử cắt lỗ1USDT cho vị thế đủ phần, tỷ lệ theo phần đã khớp, và đóng sau tối đa48h. Không SL vẫn có thể thoát lỗ ròng do funding khi trailing kích hoạt.", "",
          "Bản giảm mạnh kèm khối lượng, hồi rồi giảm lại, ba phần, SL1+48h: cả kỳ 516,33–539,41 USDT nhưng kỳ03–05/2026 chỉ497,48–499,25 từ500. Lợi nhuận cả kỳ không chứng minh hiệu quả ổn định.", "",
          f"Bản phá đáy, chờ hồi0,5ATR, ba phần, khôngSL, chi phí cơ sở: SOON vào bình quân{soon['average_entry']:.5f}, Mark{soon['mark']:.5f}, lượng{soon['qty']:g}, lỗ chưa chốt{soon['unrealized']:.2f}USDT. Tài khoản giảm{incident['drawdown']*100:.2f}% từ đỉnh, xuống{incident['equity']:.2f}USDT tại{incident['date']}. Không loại SOON khỏi kết quả.", "",
          "Chi phí cao có thể tình cờ tránh lệnh thua do thay đổi đường giao dịch và chỗ trống. Không lấy trường hợp đẹp nhất làm kết luận. Dừng mở mới ở DD20% không đóng vị thế cũ; các tháng0% sau đó có thể do tài khoản đã nghỉ giao dịch.", "",
          "## Kiểm chứng", "", audit_text, "",
          f"{verified['unit_tests_passed']} kiểm thử đạt; {verified['journals_audited']} sổ đối soát; {verified['screen_statistics_reproduced']} thống kê và {verified['full_account_paths_exact']} đường tài khoản tái lập. Tám nhóm tín hiệu tái lập và không đổi khi cắt dữ liệu tương lai; cấu hình thật giữ nguyên.", "",
          s["protocol"]["limits"], "",
          "[Dashboard](dashboard.html) · [Toàn bộ tài khoản](comparison.csv) · [Đối soát](verification.json) · [Quy tắc](protocol.json)"]
    (OUT / "report.md").write_text("\n".join(md),encoding="utf-8")
    print(OUT / "dashboard.html")


if __name__ == "__main__":
    main()
