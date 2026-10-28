"""Expose every sizing/holding result, including incomplete margin-proxy paths."""

import json
from html import escape

import pandas as pd
from compare_account_risk import ROOT,write
from search_capital_holding import OUT

NAMES={"seller_pressure":"Lực bán + phá đáy","overextension_reversal":"Tăng quá xa rồi quay đầu 4h"}
EXITS={"hold":"Trailing, không SL/đóng theo giờ","time24":"Trailing + đóng sau 24h",
       "time72":"Trailing + đóng sau 72h","risk4pct_time72":"Trailing + SL 4% danh nghĩa + 72h"}


def money(v):return "Không hoàn tất" if v is None else f"{v:.2f}"


def label(s):return f"{NAMES[s['source']['family']]} · ký quỹ {s['margin']:g} USDT · {EXITS[s['management']]}"


def main():
    summary=json.loads((OUT/"summary.json").read_text(encoding="utf-8"))
    audit=json.loads((OUT/"verification.json").read_text(encoding="utf-8"))
    specs={s["id"]:s for s in summary["specs"]};series=[]
    for r in summary["results"]:
        if r["window"]!="full":continue
        frame=pd.read_parquet(OUT/"runs"/f"{r['id']}_equity.parquet")
        ix={0,len(frame)-1}
        for _,g in frame.groupby((frame["at"]-frame["at"].iloc[0])//21600000):
            ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(r,points=[[int(v["at"]),round(v.equity,6)] for _,v in frame.loc[sorted(ix)].iterrows()],
                           first_pause=int(frame.loc[frame.paused,"at"].iloc[0]) if frame.paused.any() else None))
    aggregate=[];table=[];mdrows=[]
    for s in specs.values():
        rows=[r for r in summary["results"] if r["strategy_id"]==s["id"]]
        full={r["cost"]:r for r in rows if r["window"]=="full"}
        rolling=[r for r in rows if r["window"]!="full"]
        values=[r["ending_equity"] for r in rolling if r["ending_equity"] is not None]
        missing=sum(r["ending_equity"] is None for r in rolling)
        a=dict(id=s["id"],label=label(s),positive_rolling=sum(v>500 for v in values),rolling_count=len(rolling),
               incomplete=missing,min_complete_equity=min(values),max_complete_equity=max(values),
               worst_drawdown=max(r["max_drawdown"] for r in rows),full={c:r["ending_equity"] for c,r in full.items()})
        aggregate.append(a)
        fields=[label(s),money(full["base"]["ending_equity"]),money(full["stress"]["ending_equity"]),
                f"{a['min_complete_equity']:.2f}–{a['max_complete_equity']:.2f}",f"{a['positive_rolling']}/14",
                str(missing),f"{100*a['worst_drawdown']:.2f}%"]
        table.append("<tr>"+"".join("<td>"+escape(v)+"</td>" for v in fields)+"</tr>")
        mdrows.append("| "+" | ".join(fields)+" |")
    write(OUT/"allocation_summary.json",aggregate)
    data=dict(full=series,results=summary["results"],specs=list(specs.values()))
    write(OUT/"dashboard_data.json",data)
    style=(ROOT/"artifacts/historical_entry_search_20260925/dashboard.html").read_text(encoding="utf-8").split("<style>",1)[1].split("</style>",1)[0]
    html=r'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Vốn và thời gian giữ lệnh</title><style>__STYLE__
select{max-width:100%;min-width:260px}td{font-variant-numeric:tabular-nums}.danger{color:#ffb6c4}#chart{width:100%;min-height:230px}a{color:#62d6c2}
</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / KIỂM TRA QUY MÔ VÀ VỐN MẮC KẸT</div><h1>Nhiều vốn hơn chưa tạo ra lợi thế ổn định</h1>
<p class="muted">01/09/2025–01/06/2026 (không gồm ngày cuối), UTC · vốn 500 USDT · Short, x5, tối đa 5 vị thế · vào 3 phần thuận xu hướng</p>
<div class="notice"><b>0/512 đường tài khoản đạt 50% trong từng tháng liên tiếp.</b><p>Tăng lên 20 USDT ký quỹ có đường dài kết thúc ở 780–821 USDT, nhưng khởi chạy tháng 11 chịu sụt giảm khoảng 92%. Tăng lên 50 USDT có hai trường hợp vượt ngưỡng maintenance margin giả định. Không thể chọn đường dài đẹp nhất để suy ra vận hành ổn định.</p><span class="pill">Nghiên cứu mô phỏng · Cấu hình live giữ nguyên</span></div>
<div class="cards"><div class="card">Biến thể<strong>32</strong></div><div class="card">Đường tài khoản<strong>512</strong></div><div class="card">Tái lập đối chứng cũ<strong>32</strong></div><div class="card">Đường không hoàn tất<strong>2</strong></div></div>
<section class="panel"><h2>Điểm nghẽn thực tế của mức 5 USDT</h2><p>Hai chiến lược giữ vô thời hạn có ký quỹ cam kết trung bình chỉ 11–15 USDT cho toàn tài khoản, trong khi cả năm chỗ giao dịch bị chiếm khoảng 64–74% thời gian. Nhiều vị thế chỉ khớp một phần rồi nằm lại; vị thế lâu nhất ở cuối kỳ đã giữ 108–127 ngày.</p><p>Ký quỹ cam kết gồm ký quỹ theo giá đánh dấu, phần vốn dành cho các đợt chưa khớp và phí dự phòng. Đây không phải giới hạn lỗ của tài khoản Cross.</p><p>Với tín hiệu lực bán, đóng sau 24h tăng số vị thế từ 73–90 lên 312–408 trong chín tháng, nhưng tài sản cuối kỳ giảm từ 565,50–568,11 xuống 483,47–507,97 USDT. Tăng số lệnh chưa giải quyết được lợi thế sau chi phí.</p></section>
<section class="panel"><h2>Xem một phương án</h2><label>Chiến lược, vốn và cách thoát<select id="strategy">__OPTIONS__</select></label>
<p class="muted">Tổng danh nghĩa chia cho cả ba phần, không phải cho mỗi phần. Ký quỹ 5 / 10 / 20 / 50 USDT tương ứng 25 / 50 / 100 / 250 USDT danh nghĩa. Mức lớn hơn chỉ là giả thuyết nghiên cứu.</p>
<div class="legend"><span><i style="background:#62d6c2"></i>Chi phí cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div>
<svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản chín tháng sau chi phí và định giá vị thế mở"></svg><div id="chartStatus"></div>
<div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div>
<h3>Mức sử dụng vốn và chỗ giao dịch — cả chín tháng</h3><div class="scroll"><table><thead><tr><th>Chi phí</th><th>Ký quỹ TB</th><th>Thời gian đủ 5 vị thế</th><th>Thời gian khóa mở mới</th><th>Danh nghĩa đã vào / vốn</th><th>Trung vị giữ lệnh đã đóng</th><th>Lệnh còn mở lâu nhất</th></tr></thead><tbody id="utilization"></tbody></table></div>
<h3>Khởi chạy tài khoản mới vào bảy ngày khác nhau</h3><p>Mỗi trường hợp bắt đầu riêng 500 USDT và chạy ba tháng. Các kỳ chồng lấn và hai mức chi phí không phải những mẫu thống kê độc lập. Luôn tính lỗ chưa chốt.</p>
<div class="scroll"><table><thead><tr><th>Tháng bắt đầu</th><th>Chi phí</th><th>Tài sản cuối kỳ</th><th>Sụt giảm từ đỉnh</th><th>Số vị thế đã vào</th><th>Còn mở</th><th>Trạng thái</th></tr></thead><tbody id="rolling"></tbody></table></div><p id="stopDetails" class="danger"></p></section>
<section class="panel"><h2>Toàn bộ 32 phương án</h2><p>Khoảng ba tháng chỉ tính đường hoàn tất; cột không hoàn tất giữ riêng những đường vượt ngưỡng margin. Sụt giảm lớn nhất lấy trên toàn bộ ngày bắt đầu và hai mức chi phí, kể cả thời điểm vượt ngưỡng.</p>
<div class="scroll"><table><thead><tr><th>Quy tắc</th><th>9 tháng cơ sở</th><th>9 tháng cao</th><th>Khoảng cuối kỳ 3 tháng hoàn tất</th><th>Kỳ 3 tháng có lời</th><th>Không hoàn tất</th><th>DD lớn nhất</th></tr></thead><tbody>__TABLE__</tbody></table></div></section>
<section class="panel"><h2>Quy tắc và giới hạn</h2><p>Giữ hai bộ tín hiệu từ lượt trước: lực bán + phá đáy; và tăng quá xa rồi quay đầu trên khung 4h. Trailing kích hoạt theo 3 ATR, hồi 1%; chia ba phần, thêm khi giá đi thuận 0,5 ATR, hết hạn thêm sau 6h. Thử bốn cách quản lý: giữ không SL; đóng sau 24h; đóng sau 72h; hoặc SL bằng 4% tổng danh nghĩa kèm đóng sau 72h. Ngưỡng SL tỷ lệ với phần đã khớp, không bảo đảm lỗ thực tế đúng ngưỡng khi giá nhảy. Đóng theo giờ có thể chốt lỗ; đây là biến thể nghiên cứu khác cấu hình không cắt lỗ ban đầu.</p>
<p>Giảm 20% từ đỉnh sẽ khóa mở mới, tiếp tục giữ và quản lý vị thế cũ; không tự bật lại. Mức 20% không phải trần thua lỗ. Tăng quy mô có thể đổi điều kiện lệnh tối thiểu, tín hiệu được phép giao dịch, thứ tự chiếm chỗ và thời điểm khóa mở mới, nên kết quả không tăng tuyến tính.</p>
<p>Chi phí cơ sở: phí 0,05%, trượt giá 0,20% mỗi lần khớp thị trường; chi phí cao: 0,10% và 0,50%. Funding theo lịch sử thực; lợi nhuận bao gồm lãi/lỗ vị thế mở. Không loại coin gây lỗ. Các số liệu đều tính bằng USDT.</p>
<p>512 sổ giao dịch, phí, funding, ngân sách, giới hạn vị thế, khởi tạo 500 USDT và thống kê tháng được đối soát. 32 đường đối chứng cũ tái lập chính xác; sáu đường mới tái lập, gồm cả hai đường vượt ngưỡng. 95 kiểm thử đạt.</p>
<p class="muted">Lịch sử đã được dùng nghiên cứu nhiều lần; chưa phải xác nhận độc lập ngoài mẫu. Danh sách kho có thể thiếu coin hủy niêm yết. Dùng bộ lọc sàn hiện tại, không có bậc maintenance margin lịch sử; mức 1% chỉ là mô hình thay thế. Giá lấy mẫu 5 phút có thể bỏ qua thời điểm chạm ngưỡng nội nến; tài sản âm ở mẫu vượt ngưỡng không phải số dư thanh lý thực tế của Binance. Không suy diễn số dư cuối kỳ cho hai đường không hoàn tất. Chưa đủ điều kiện chuyển giao dịch thật.</p>
<p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">512 kết quả</a> · <a href="allocation_summary.json">So sánh 32 phương án</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc đã khóa</a></p></section></main>
<script>const data=__JSON__;const num=v=>v===null||v===undefined?'—':v.toFixed(2),fmt=t=>new Date(t).toISOString().slice(0,10),cost=c=>c==='base'?'Cơ sở':'Cao';
function render(){const id=document.querySelector('#strategy').value,rows=data.full.filter(r=>r.strategy_id===id),rolling=data.results.filter(r=>r.strategy_id===id&&r.window!=='full');
let values=rows.flatMap(r=>r.points.map(p=>p[1])),lo=Math.floor(Math.min(500,...values)/50)*50-10,hi=Math.ceil(Math.max(500,...values)/50)*50+10,start=Date.UTC(2025,8,1),end=Date.UTC(2026,5,1);const x=t=>62+(t-start)/(end-start)*1110,y=v=>280-(v-lo)/(hi-lo)*250;let svg='';
for(let i=0;i<=5;i++){let v=lo+(hi-lo)*i/5;svg+=`<path d="M62 ${y(v)}H1172" stroke="#2a3a51"/><text x="52" y="${y(v)+4}" text-anchor="end" fill="#a7b6cc" font-size="12">${v.toFixed(0)}</text>`}svg+=`<path d="M62 ${y(500)}H1172" stroke="#96a5ba" stroke-dasharray="5 6"/>`;
for(let i=0;i<=9;i++){let t=Date.UTC(2025,8+i,1);svg+=`<text x="${x(t)}" y="307" text-anchor="middle" fill="#a7b6cc" font-size="12">${fmt(t).slice(2,7)}</text>`}for(const r of rows){let d=r.points.map((p,i)=>(i?'L':'M')+x(p[0]).toFixed(2)+' '+y(p[1]).toFixed(2)).join('');svg+=`<path d="${d}" fill="none" stroke="${r.cost==='base'?'#62d6c2':'#e6afed'}" stroke-width="1.7" ${r.cost==='stress'?'stroke-dasharray="5 3"':''}/>`}document.querySelector('#chart').innerHTML=svg;
document.querySelector('#chartStatus').innerHTML=rows.map(r=>`${cost(r.cost)}: cuối ${num(r.ending_equity)} USDT · DD ${num(r.max_drawdown*100)}% · ${r.entries} vị thế đã vào · ${r.open_count} còn mở${r.first_pause?' · khóa mở mới từ '+fmt(r.first_pause):''}`).join('<br>');
document.querySelector('#monthHead').innerHTML='<tr><th>Chi phí</th>'+Array.from({length:9},(_,i)=>'<th>'+fmt(Date.UTC(2025,8+i,1)).slice(0,7)+'</th>').join('')+'</tr>';
document.querySelector('#monthBody').innerHTML=rows.map(r=>'<tr><td>'+cost(r.cost)+'</td>'+Array.from({length:9},(_,i)=>{let m=r.monthly.months.find(m=>m.start===Date.UTC(2025,8+i,1));return m&&m.return_fraction!==undefined?`<td class="${m.return_fraction<0?'bad':'good'}">${num(m.return_fraction*100)}%</td>`:'<td>Thiếu</td>'}).join('')+'</tr>').join('');
document.querySelector('#utilization').innerHTML=rows.map(r=>{let u=r.utilization;return `<tr><td>${cost(r.cost)}</td><td>${num(u.mean_committed_margin)}</td><td>${num(u.fraction_time_all_slots_used*100)}%</td><td>${num(u.fraction_time_paused*100)}%</td><td>${num(u.entry_turnover_multiple)}x</td><td>${num(u.closed_hold_median_days)} ngày</td><td>${num(u.open_hold_max_days)} ngày</td></tr>`}).join('');
document.querySelector('#rolling').innerHTML=rolling.map(r=>`<tr><td>${r.window.replace('start_','').replace('_','-')}</td><td>${cost(r.cost)}</td><td class="${r.ending_equity===null||r.ending_equity<500?'bad':'good'}">${r.ending_equity===null?'Không hoàn tất':num(r.ending_equity)}</td><td>${num(r.max_drawdown*100)}%</td><td>${r.entries}</td><td>${r.open_count}</td><td>${r.ending_equity===null?'Vượt ngưỡng margin giả định':r.paused?'Đã khóa mở mới':'Hoàn tất'}</td></tr>`).join('');
document.querySelector('#stopDetails').textContent=rolling.filter(r=>r.stop_event).map(r=>`${r.window.replace('start_','')} / ${cost(r.cost)}: dừng mô phỏng tại ${new Date(r.stop_event.at).toISOString()}, tài sản tại mẫu ${num(r.stop_event.equity)}, maintenance giả định ${num(r.stop_event.maintenance_proxy)} USDT. Không xác định số dư cuối kỳ.`).join(' ');}
document.querySelector('#strategy').addEventListener('change',render);render();</script></body></html>'''
    options="".join(f'<option value="{escape(s["id"])}">{escape(label(s))}</option>' for s in specs.values())
    for key,value in dict(STYLE=style,TABLE="".join(table),OPTIONS=options,JSON=json.dumps(data,ensure_ascii=False,separators=(",",":"),allow_nan=False).replace("</","<\\/")).items():html=html.replace("__"+key+"__",value)
    (OUT/"dashboard.html").write_text(html,encoding="utf-8")
    md=["# Quy mô vốn và thời gian giữ vị thế — lượt 06","",
        "512 mô phỏng, 32 cấu hình, từ 01/09/2025 đến trước 01/06/2026 UTC và bảy cửa sổ ba tháng khởi tạo riêng 500 USDT. Không có trường hợp đạt tăng ít nhất 50% trong từng tháng. 510 đường hoàn tất, hai đường vượt ngưỡng margin giả định nên không có số dư cuối kỳ.","",
        "Giữ hai bộ tín hiệu cũ, ba phần thuận xu hướng, trailing 3 ATR/hồi 1%, x5, tối đa năm vị thế. Thử ký quỹ 5/10/20/50 USDT, bốn cách giữ/thoát. Đây là kiểm tra quy mô và quản lý vị thế, không phải phát hiện bộ tín hiệu mới.","",
        "## Kết quả chính","",
        "- Ký quỹ cam kết trung bình chỉ 11–15 USDT ở cấu hình 5 USDT/vị thế, nhưng đủ năm chỗ trong 64–74% thời gian. Vị thế mở lâu nhất 108–127 ngày. Ký quỹ không phải giới hạn thua lỗ Cross.",
        "- Lực bán/giữ/trailing, ký quỹ 20 USDT: chín tháng 500 → 779,89–821,09. Nhưng khởi chạy 11/2025 chỉ còn 384,27–387,86 cuối kỳ và sụt giảm lớn nhất 91,02–91,87%; khởi chạy 03/2026 còn 459,25–469,73. Không phải lợi thế ổn định.",
        "- Cùng tín hiệu ở ký quỹ 5 USDT, đóng sau 24h tăng số vị thế từ 73–90 lên 312–408, nhưng cuối chín tháng chỉ 483,47–507,97. Chi phí làm mất phần lớn lợi nhuận.",
        "- Ký quỹ 50 USDT, lực bán/giữ không SL, khởi chạy 11/2025: cả hai mức chi phí vượt ngưỡng margin giả định khi giữ Short SOON. Không gán số dư cuối kỳ hoặc xem đây là giá thanh lý Binance chính xác.",
        "- Không có tháng hoàn tất nào đạt 50% trong lượt này; tháng cao nhất khoảng 48,33%, vẫn không đạt tiêu chí và được chọn sau khi xem nhiều kết quả.","",
        "## Toàn bộ biến thể","",
        "| Quy tắc | 9 tháng cơ sở | 9 tháng cao | Khoảng cuối kỳ 3 tháng hoàn tất | Kỳ 3 tháng có lời | Không hoàn tất | DD lớn nhất mọi kỳ |",
        "|---|---:|---:|---:|---:|---:|---:|",*mdrows,"",
        "Bảy kỳ chồng lấn, hai mức chi phí; 14 kết quả không phải 14 mẫu độc lập. Khoảng kết quả chỉ cho đường hoàn tất, phải đọc kèm số đường thiếu. Tăng quy mô đổi cả điều kiện lệnh tối thiểu và danh sách khớp, không chỉ nhân lợi nhuận.","",
        "## Kiểm chứng và giới hạn","",
        f"{audit['unit_tests_passed']} kiểm thử đạt; {audit['journals_audited']} sổ, phép tính phí/funding/ngân sách và tháng đối soát. {audit['prior_baseline_paths_exact']} đường đối chứng cũ và {audit['new_paths_exact']} đường mới tái lập chính xác, gồm hai đường không hoàn tất. Hash cấu hình live giữ nguyên.","",
        "Lịch sử đã nghiên cứu nhiều lần, chưa phải ngoài mẫu độc lập. Có thể thiếu coin hủy niêm yết; bộ lọc sàn hiện tại, thiếu bậc maintenance lịch sử và orderbook. Maintenance 1% là proxy. Mẫu giá 5 phút có thể bỏ lỡ thời điểm chạm ngưỡng, nên mẫu equity âm không phải số dư thanh lý thực. Dừng mở mới ở DD20% vẫn để lệnh cũ lỗ tiếp. Đóng theo giờ/SL chỉ là biến thể nghiên cứu, khác cấu hình ban đầu.","",
        "[Dashboard](dashboard.html) · [512 kết quả](comparison.csv) · [Đối soát](verification.json) · [Quy tắc](protocol.json)"]
    (OUT/"report.md").write_text("\n".join(md),encoding="utf-8")
    write(OUT/"goal_progress.json",dict(classification="progress",goal_status="active",achieved=False,
         runs=512,scenarios=32,target_passes=0,incomplete_paths=2,
         contribution="Measured capital/slot occupancy, tested sizing and time exits with full portfolio replays; falsified simple sizing/turnover solution across starting dates.",
         next_steps=["Research causal entry filters for adverse short squeezes without retrospective coin exclusion.",
                     "Separate signal event edge from position-slot occupancy; preregister new rules before viewing new evaluation data.",
                     "Obtain independent later data and historical maintenance tiers before considering financial verification."],
         live_config_unchanged=True))
    print(OUT/"dashboard.html")


if __name__=="__main__":main()
