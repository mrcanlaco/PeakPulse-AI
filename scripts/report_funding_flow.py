"""Expose full and final-quarter results without selecting on the full period."""

import json
from html import escape

import pandas as pd
from compare_account_risk import ROOT,write
from prepare_flow_research import OUT

NAMES=dict(positive_carry="Funding dương + giá yếu",buyer_absorption="Lực mua không đẩy được giá",
           seller_pressure="Lực bán + phá đáy",relative_weakness="Yếu hơn BTC")
EXITS=dict(tp1_noSL="TP 1 USDT, không SL",trail_noSL="Trailing, không SL",trail_sl1_h48="Trailing + SL1 + 48h")


def number(value):
    return "Không hoàn tất" if value is None else f"{value:.2f}"


def main():
    summary=json.loads((OUT/"summary.json").read_text(encoding="utf-8"))
    verification=json.loads((OUT/"verification.json").read_text(encoding="utf-8"))
    evidence=json.loads((OUT/"flow_evidence.json").read_text(encoding="utf-8"))
    full=[r for r in summary["results"] if r["window"]=="full"]
    chart=[]
    for row in full:
        c=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet")
        indices={0,len(c)-1}
        for _,g in c.groupby((c["at"]-c["at"].iloc[0])//21600000):
            indices.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        points=[[int(r["at"]),round(r.equity,6)] for _,r in c.loc[sorted(indices)].iterrows()]
        chart.append(dict(**row,points=points,exit_label=EXITS[row["exit"]],
                          first_pause=int(c.loc[c.paused,"at"].iloc[0]) if c.paused.any() else None))
    write(OUT/"dashboard_data.json",chart)
    screening=[]
    for v in summary["validation"]:
        h=next(r for r in summary["holdout"] if r["id"]==v["id"])
        label=NAMES[v["spec"]["source"]["family"]]+f" · giữ {v['spec']['hours']}h"
        vals=[f"{v['counts']['complete']} / {h['counts']['complete']}"]
        vals += [f"{r['cases'][cost]['mean_net_return']*100:.3f}%" for r,cost in [(v,"base"),(v,"stress"),(h,"base"),(h,"stress")]]
        screening.append("<tr><td>"+escape(label)+"</td>"+"".join("<td>"+x+"</td>" for x in vals)+"</tr>")
    table=[];md_table=[]
    for spec in summary["portfolio_specs"]:
        if spec["cap"]!=5 or spec["parts"]!=3:continue
        rows=[r for r in summary["results"] if r["strategy_id"]==spec["id"]]
        get=lambda window,cost:next(r for r in rows if r["window"]==window and r["cost"]==cost)
        label=NAMES[spec["source"]["family"]]+" · "+EXITS[spec["exit"]]
        vals=[]
        for window in ["full","holdout"]:
            vals.extend(number(get(window,c)["ending_equity"]) for c in ["base","stress"])
        vals.append(" / ".join(f"{get('full',c)['max_drawdown']*100:.2f}%" for c in ["base","stress"]))
        vals.append(" / ".join(str(get("full",c)["entries"]) for c in ["base","stress"]))
        table.append("<tr><td>"+escape(label)+"</td>"+"".join("<td>"+x+"</td>" for x in vals)+"</tr>")
        md_table.append("| "+label+" | "+" | ".join(vals)+" |")
    repaired=[]
    for ident in verification["repaired_paths"]:
        r=json.loads((OUT/"runs"/f"{ident}.json").read_text(encoding="utf-8"))
        incidents=[j for j in r["journal"] if j["kind"]=="tp_unrepresentable"]
        repaired.append(dict(id=ident,ending_equity=r["ending_equity"],funding=r["funding"],
                              max_drawdown=r["sampled_max_drawdown"],open_count=len(r["open_positions"]),
                              incidents=incidents,errors=r["errors"]))
    write(OUT/"tp_hold_repair_results.json",repaired)
    repair_table="".join(f"<tr><td>{escape(r['id'])}</td><td>{number(r['ending_equity'])}</td><td>{r['funding']:.2f}</td><td>{r['max_drawdown']*100:.2f}%</td><td>{r['open_count']}</td></tr>" for r in repaired)
    style=(ROOT/"artifacts/historical_entry_search_20260925/dashboard.html").read_text(encoding="utf-8").split("<style>",1)[1].split("</style>",1)[0]
    html=r'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Funding và dòng giao dịch</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / KIỂM ĐỊNH CƠ CHẾ TÍN HIỆU</div><h1>Funding và lực mua/bán có tạo lợi thế Short?</h1><p class="muted">01/09/2025–31/05/2026 UTC · 30 coin chọn trước kỳ · vốn 500 USDT · x5 · tổng 25 USDT danh nghĩa/vị thế</p>
<div class="notice"><b>Chưa đạt 50% mỗi tháng. Các ứng viên chưa đứng vững trong kỳ kiểm tra cuối.</b><p>Có cấu hình tăng tài sản trong cả chín tháng, nhưng lại lỗ khi khởi chạy riêng ở 03–05/2026. Không chọn chiến lược chỉ vì tổng PnL đẹp. Cấu hình tài khoản thật giữ nguyên.</p></div>
<div class="cards"><div class="card">Cơ chế mới<strong>4</strong></div><div class="card">Quy tắc / phép sàng lọc<strong>32 / 96</strong></div><div class="card">Mô phỏng tài khoản<strong>144</strong></div><div class="card">Đạt mọi tháng<strong>0</strong></div></div>
<section class="panel"><h2>Bốn giả thuyết được thử</h2><div class="facts"><div><b>Funding dương + giá yếu</b><p>Tổng funding đã thanh toán trong 24 giờ đủ cao, mức gần nhất không âm; giá nằm dưới EMA20 và EMA60. Chỉ dùng funding đã xảy ra ít nhất một phút.</p><b>Lực mua không đẩy được giá</b><p>Mua chủ động chiếm ≥55% hoặc ≥60% khối lượng sáu giờ, nhưng giá không tăng và nến hiện tại giảm.</p></div><div><b>Lực bán + phá đáy</b><p>Mua chủ động chỉ chiếm ≤45% hoặc ≤40%, giá phá đáy 12 giờ trong xu hướng giảm, khối lượng tăng.</p><b>Yếu hơn BTC</b><p>Coin kém BTC ≥3 hoặc ≥6 điểm phần trăm trong 24 giờ, hồi lên EMA20 rồi giảm; lực mua chủ động giờ gần nhất không chiếm ưu thế.</p></div></div><p class="muted">Mỗi nhóm thử hai ngưỡng, có/không lọc BTC giảm và khoảng cách tín hiệu 6/24 giờ. Khối lượng đo theo coin gốc, tỷ lệ sáu giờ tính bằng tổng lượng mua chia tổng giao dịch, không lấy trung bình các tỷ lệ. Đây không phải dữ liệu open interest.</p></section>
<section class="panel"><h2>Kết quả tín hiệu trước khi áp giới hạn vốn</h2><p>09–11/2025 chọn một ứng viên mỗi nhóm; 12/2025–02/2026 chọn hai ứng viên để mô phỏng tài khoản; 03–05/2026 kiểm tra cuối. Nhóm lực mua không đẩy giá thiếu mẫu nên không được chọn tiếp. Lịch sử đã từng được nghiên cứu: đây không phải tập dữ liệu hoàn toàn chưa xem.</p><div class="scroll"><table><thead><tr><th>Nhóm / giữ giả định</th><th>Mẫu kỳ 2 / kỳ 3</th><th>Kỳ 2 · cơ sở</th><th>Kỳ 2 · cao</th><th>Kỳ 3 · cơ sở</th><th>Kỳ 3 · cao</th></tr></thead><tbody>__SCREEN__</tbody></table></div><p class="muted">Lợi suất trung bình trên danh nghĩa của từng sự kiện, không phải lợi suất tài khoản. Các sự kiện có thể chồng lấn. Không tổ hợp sàng lọc nào có cận dưới 95% dương ở cả hai mức chi phí. Khoảng tin cậy theo khối 7 ngày chưa hiệu chỉnh việc thử nhiều biến thể. Funding và yếu hơn BTC có dưới 100 sự kiện ở kỳ cuối, chưa đạt ngưỡng mẫu đã đặt.</p></section>
<section class="panel"><h2>Cùng tín hiệu, thay cách thoát và số vị thế</h2><div class="filters"><label>Nhóm<select id="family"><option value="relative_weakness">Yếu hơn BTC</option><option value="seller_pressure">Lực bán + phá đáy</option></select></label><label>Số vị thế tối đa<select id="cap"><option value="5">5 vị thế</option><option value="1">1 vị thế</option></select></label><label>Chia lệnh<select id="parts"><option value="3">Ba phần</option><option value="1">Một phần</option></select></label></div><div id="legend" class="legend"></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="So sánh đường tài sản"></svg><div id="chartStatus"></div><h2 style="margin-top:24px">Lợi suất trên tài sản đầu mỗi tháng</h2><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><p class="muted">Tài sản gồm vị thế chưa đóng, funding và phí. Mỗi đường liên tục chín tháng; không khởi tạo lại vốn đầu tháng. Giá trị 0% sau khi khóa mở mới có thể phản ánh không còn giao dịch. Mục tiêu 50% phải đạt từng tháng, không phải cả kỳ cộng lại.</p></section>
<section class="panel"><h2>So cả kỳ với ba tháng cuối · chia ba phần, tối đa 5 vị thế</h2><div class="scroll"><table><thead><tr><th>Quy tắc</th><th>9 tháng · cơ sở</th><th>9 tháng · cao</th><th>Kỳ cuối · cơ sở</th><th>Kỳ cuối · cao</th><th>DD 9 tháng · cơ sở/cao</th><th>Số vị thế · cơ sở/cao</th></tr></thead><tbody>__ACCOUNTS__</tbody></table></div><p>“Kỳ cuối” khởi chạy riêng từ 500 USDT ngày 01/03/2026; khác với đoạn cuối của tài khoản đã chạy từ tháng 09/2025 và có thể đang giữ vị thế cũ. Không cộng lợi nhuận các kỳ chạy riêng.</p><p>TP 1 USDT là mục tiêu của vị thế đủ ba phần, tỷ lệ theo phần đã khớp. Trailing kích hoạt khi giá giảm 3 ATR, hồi 1% thì thoát; không áp trần 5 USDT cho trailing. Bản SL1 + 48h có cắt lỗ và thời hạn giữ riêng để nghiên cứu.</p><p class="muted">Chi phí cơ sở: phí0,05%, trượt giá thị trường0,20% mỗi lần khớp; mức cao0,10% và0,50%. TP LIMIT dùng quy ước nghiên cứu: nến đóng vượt giá TP mới tính khớp ở giá TP, không mô phỏng hàng đợi/khớp từng phần. Thêm phần chỉ khi giá thuận chiều; tổng danh nghĩa vẫn ≤25 USDT.</p></section>
<section class="panel"><h2>Sửa trường hợp funding khiến không còn giá TP hợp lệ</h2><p>Ba đường ban đầu dừng tính khi chi phí tích lũy khiến giá TP ròng ≤0 hoặc thấp hơn bước giá. Lượt chạy lại khóa mở mới, giữ vị thế, tiếp tục tính funding và lỗ chưa chốt; nếu giá TP hợp lệ trở lại thì tiếp tục quản lý TP, không tự bật mở mới.</p><p>Giữ nguyên tín hiệu và ứng viên. __PRESERVED__ đường không gặp lỗi được xác nhận giống hệt trước sửa. Ba trường hợp dưới đây tiếp tục được tính, không xóa lỗ hoặc giả định chốt thành công:</p><div class="scroll"><table><thead><tr><th>Đường mô phỏng</th><th>Tài sản cuối</th><th>Funding toàn kỳ</th><th>DD tối đa</th><th>Còn mở</th></tr></thead><tbody>__REPAIRS__</tbody></table></div></section>
<section class="panel"><h2>Đối soát và giới hạn</h2><p>90 mẫu coin–tháng khớp trường khối lượng tổng và lượng mua chủ động với kho Binance. Đơn vị tham chiếu theo <a href="https://github.com/binance/binance-public-data#klines-1">tài liệu dữ liệu công khai Binance</a>. Nến Mark Price và funding dùng bộ lịch sử đã kiểm chứng ở lượt trước; không đọc API tài khoản riêng tư.</p><p>__TESTS__ kiểm thử đạt; __JOURNALS__ sổ đối soát, __SIGNALS__ bộ tín hiệu tái lập và không đổi khi cắt phần tương lai; __EXACT__ đường tài khoản chạy lại giống hệt.</p><p class="muted">Kho có thể thiếu hợp đồng đã hủy niêm yết; bộ lọc khối lượng/giá là ảnh chụp hiện tại; maintenance margin1% là mô hình thay thế, chưa có bậc margin lịch sử; dữ liệu5 phút và giả định trượt giá không chứng minh khớp thực. Chưa có phương án đạt mục tiêu lợi nhuận từng tháng hay đủ điều kiện chạy thật.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">144 lượt tài khoản</a> · <a href="development.json">96 phép sàng lọc</a> · <a href="verification.json">Đối soát</a> · <a href="flow_evidence.json">Dữ liệu khối lượng</a> · <a href="tp_hold_repair_results.json">Nhánh TP không hợp lệ</a> · <a href="protocol.json">Quy tắc</a></p></section></main>
<script>const all=__JSON__,colors=['#72dec7','#51a0ff','#ffbd79','#dba1f3','#ef8995','#becb7b'];const date=t=>new Date(t).toISOString().slice(0,10),num=x=>x===null?'Không hoàn tất':x.toFixed(2);function render(){let rows=all.filter(r=>r.family===document.querySelector('#family').value&&r.cap===+document.querySelector('#cap').value&&r.parts===+document.querySelector('#parts').value);const start=Date.UTC(2025,8,1),end=Date.UTC(2026,5,1),vals=rows.flatMap(r=>r.points.map(p=>p[1]));let low=Math.floor(Math.min(500,...vals)/50)*50-10,high=Math.ceil(Math.max(500,...vals)/50)*50+10;const x=t=>62+(t-start)/(end-start)*1110,y=v=>280-(v-low)/(high-low)*250;let svg='';for(let i=0;i<=5;i++){let v=low+(high-low)*i/5;svg+=`<path d="M62 ${y(v)}H1172" stroke="#2a3a51"/><text x="52" y="${y(v)+4}" text-anchor="end" fill="#a7b6cc" font-size="12">${v.toFixed(0)}</text>`}svg+=`<path d="M62 ${y(500)}H1172" stroke="#8091a9" stroke-dasharray="5 6"/>`;for(let i=0;i<=9;i++){let t=Date.UTC(2025,8+i,1);svg+=`<text x="${x(t)}" y="307" text-anchor="middle" fill="#a7b6cc" font-size="12">${date(t).slice(2,7)}</text>`}rows.forEach((r,i)=>{let d=r.points.map((p,j)=>(j?'L':'M')+x(p[0]).toFixed(2)+' '+y(p[1]).toFixed(2)).join('');svg+=`<path d="${d}" fill="none" stroke="${colors[i]}" stroke-width="1.6" ${r.cost==='stress'?'stroke-dasharray="5 3"':''}/>`});document.querySelector('#chart').innerHTML=svg;document.querySelector('#legend').innerHTML=rows.map((r,i)=>`<span><i style="background:${colors[i]}"></i>${r.exit_label} · ${r.cost==='base'?'cơ sở':'cao'}</span>`).join('');document.querySelector('#chartStatus').innerHTML=rows.map(r=>`${r.exit_label} (${r.cost==='base'?'cơ sở':'cao'}): ${num(r.ending_equity)} USDT · DD ${num(100*r.max_drawdown)}% · ${r.entries} vị thế${r.first_pause?' · khóa mở mới '+date(r.first_pause):''}`).join('<br>');document.querySelector('#monthHead').innerHTML='<tr><th>Cách thoát / chi phí</th>'+Array.from({length:9},(_,i)=>'<th>'+date(Date.UTC(2025,8+i,1)).slice(0,7)+'</th>').join('')+'</tr>';document.querySelector('#monthBody').innerHTML=rows.map(r=>'<tr><td>'+r.exit_label+' / '+(r.cost==='base'?'cơ sở':'cao')+'</td>'+Array.from({length:9},(_,i)=>{let m=r.monthly.months[i];return m?`<td class="${m.return_fraction<0?'bad':'good'}">${num(100*m.return_fraction)}%</td>`:'<td>Thiếu</td>'}).join('')+'</tr>').join('')}document.querySelectorAll('select').forEach(e=>e.addEventListener('change',render));render();</script></body></html>'''
    for k,v in dict(STYLE=style,SCREEN="".join(screening),ACCOUNTS="".join(table),REPAIRS=repair_table,
                    PRESERVED=str(verification["unaffected_account_paths_exact"]),TESTS=str(verification["unit_tests_passed"]),
                    JOURNALS=str(verification["journals_audited"]),SIGNALS=str(verification["signal_sets_reproduced"]),
                    EXACT=str(verification["full_paths_exact"]),JSON=json.dumps(chart,ensure_ascii=False,separators=(",",":"),allow_nan=False).replace("</","<\\/")).items():
        html=html.replace("__"+k+"__",v)
    (OUT/"dashboard.html").write_text(html,encoding="utf-8")
    md=["# Funding và lực mua/bán — lượt nghiên cứu04","",
        "Chưa đạt mục tiêu50% mỗi tháng. 32 quy tắc mới,96 phép sàng lọc,144 lượt tài khoản trên09/2025–05/2026. Chạy lại cùng144 lượt để sửa ba đường bị ngắt do TP không biểu diễn được; không tính thành chiến lược mới.","",
        "Vốn500USDT, x5, tổng25USDT danh nghĩa/vị thế, thử1/5 vị thế và chia1/3 phần. Bốn nhóm: funding dương khi giá yếu, lực mua không đẩy giá, lực bán phá đáy, yếu hơn BTC. Chọn bằng kỳ phát triển rồi kỳ xác nhận; không chọn theo lợi nhuận cả kỳ.","",
        "## Chia ba phần, tối đa5 vị thế","",
        "| Tín hiệu / thoát | 9 tháng cơ sở | 9 tháng cao | 3 tháng cuối cơ sở | 3 tháng cuối cao | DD9 tháng cơ sở/cao | Số vị thế cơ sở/cao |",
        "|---|---:|---:|---:|---:|---:|---:|",*md_table,"",
        "Mọi kỳ riêng khởi tạo500USDT. Ba tháng cuối khởi chạy01/03/2026, không phải trừ hai điểm trên đường tài khoản chín tháng; những vị thế đã giữ từ trước làm kết quả hai phép đo khác nhau.","",
        "Ứng viên yếu hơn BTC/giữ24h: trung bình sự kiện kỳ xác nhận +0,867% cơ sở/+0,171% cao, nhưng kỳ cuối −1,692%/−2,405%, chỉ63 mẫu. Không có bằng chứng ổn định. Nhóm lực mua không đẩy giá thiếu mẫu; không nới tiêu chuẩn chỉ để có ứng viên.","",
        "## Lỗi mô phỏng được sửa","",
        "Ba đường fixedTP ban đầu dừng vì funding khiến giá TP≤0. Nhánh nghiên cứu mới khóa mở mới và tiếp tục giữ, định giá, thanh toán funding; nếu TP hợp lệ lại thì khôi phục TP nhưng không tự bật mở mới. Mặc định của các nghiên cứu cũ được giữ.141 đường không gặp trường hợp này giống hệt trước sửa; tín hiệu và lựa chọn ứng viên giữ nguyên.","",
        "86 kiểm thử đạt;144 sổ đối soát;32 bộ tín hiệu tái lập và kiểm tra không dùng tương lai;4 đường tài khoản tái lập chính xác.90 mẫu coin–tháng khớp khối lượng cơ sở và lượng mua chủ động. [Định dạng dữ liệu Binance](https://github.com/binance/binance-public-data#klines-1).","",
        summary["protocol"]["limitations"],"",
        "[Dashboard](dashboard.html) · [Toàn bộ mô phỏng](comparison.csv) · [Đối soát](verification.json) · [Sửa nhánh TP](tp_hold_repair_results.json)"]
    (OUT/"report.md").write_text("\n".join(md),encoding="utf-8")
    print(OUT/"dashboard.html")


if __name__=="__main__":main()
