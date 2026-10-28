"""Report start-date sensitivity alongside continuously marked monthly returns."""

import json
from html import escape

import pandas as pd
from compare_account_risk import ROOT,write
from search_multitimeframe_rolling import OUT,rolling_windows

NAMES=dict(failed_breakout="Phá đỉnh thất bại 4h",overextension_reversal="Tăng quá xa rồi quay đầu 4h",
           compression_break="Phá vỡ sau co hẹp",daily_down_pullback="Hồi trong xu hướng giảm ngày",
           seller_pressure="Đối chứng: lực bán + phá đáy")
EXITS=dict(tp2_noSL="TP 2 USDT, không SL",trail_noSL="Trailing, không SL",trail_sl1_h72="Trailing + SL1 + 72h")


def label(spec):
    return f"{NAMES[spec['source']['family']]} · {spec['parts']} phần · {EXITS[spec['exit']]}"


def money(value):return "Không hoàn tất" if value is None else f"{value:.2f}"


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"))
    audit=json.loads((OUT/"verification.json").read_text(encoding="utf-8"))
    windows=rolling_windows();rolling=[w for w in windows if w!="full"]
    specs={p["id"]:p for p in s["portfolio_specs"]}
    full=[r for r in s["results"] if r["window"]=="full"]
    series=[]
    for r in full:
        frame=pd.read_parquet(OUT/"runs"/f"{r['id']}_equity.parquet")
        indices={0,len(frame)-1}
        for _,g in frame.groupby((frame["at"]-frame["at"].iloc[0])//21600000):
            indices.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        points=[[int(row["at"]),round(row.equity,6)] for _,row in frame.loc[sorted(indices)].iterrows()]
        series.append(dict(r,label=label(specs[r["strategy_id"]]),points=points,
                           first_pause=int(frame.loc[frame.paused,"at"].iloc[0]) if frame.paused.any() else None))
    write(OUT/"dashboard_data.json",dict(full=series,results=s["results"],windows=windows))
    aggregate=[];table=[];mdrows=[];heat=[]
    for spec in s["portfolio_specs"]:
        rows=[r for r in s["results"] if r["strategy_id"]==spec["id"]]
        ending=[r for r in rows if r["window"]=="full"]
        varied=[r for r in rows if r["window"]!="full"]
        values=[r["ending_equity"] for r in varied if r["ending_equity"] is not None]
        all_complete=len(values)==len(varied)
        summary=dict(strategy_id=spec["id"],parts=spec["parts"],label=label(spec),
                     full_end={r["cost"]:r["ending_equity"] for r in ending},
                     rolling_complete=all_complete,positive_rolling_runs=sum(v>500 for v in values),
                     rolling_runs=len(varied),rolling_min=min(values) if values else None,
                     rolling_max=max(values) if values else None,
                     all_rolling_months_target=all(r["target_met"] for r in varied))
        aggregate.append(summary)
        if spec["parts"]!=3:continue
        vals=[money(summary["full_end"]["base"]),money(summary["full_end"]["stress"]),
              f"{money(summary['rolling_min'])}–{money(summary['rolling_max'])}",
              f"{summary['positive_rolling_runs']}/{summary['rolling_runs']}",
              " / ".join(f"{r['max_drawdown']*100:.2f}%" for r in ending)]
        table.append("<tr><td>"+escape(label(spec))+"</td>"+"".join("<td>"+v+"</td>" for v in vals)+"</tr>")
        mdrows.append("| "+label(spec)+" | "+" | ".join(vals)+" |")
        for cost in ["base","stress"]:
            cells=[]
            for window in rolling:
                row=next(r for r in rows if r["window"]==window and r["cost"]==cost)
                value=row["ending_equity"]
                text="Thiếu" if value is None else f"{(value/500-1)*100:+.2f}%"
                background="#47262f" if value is None or value<500 else "#153c39"
                cells.append(f'<td style="background:{background}">{text}</td>')
            heat.append("<tr><td>"+escape(label(spec))+" / "+("cơ sở" if cost=="base" else "cao")+"</td>"+"".join(cells)+"</tr>")
    write(OUT/"rolling_summary.json",aggregate)
    screens=[]
    for v in s["validation"]:
        h=next(r for r in s["holdout"] if r["id"]==v["id"])
        vals=[f"{v['counts']['complete']} / {h['counts']['complete']}"]
        vals.extend(f"{r['cases'][c]['mean_net_return']*100:+.3f}%" for r,c in [(v,"base"),(v,"stress"),(h,"base"),(h,"stress")])
        screens.append("<tr><td>"+NAMES[v["spec"]["source"]["family"]]+f" · giữ{v['spec']['hours']}h</td>"+"".join("<td>"+x+"</td>" for x in vals)+"</tr>")
    options="".join(f'<option value="{escape(p["id"])}">{escape(label(p))}</option>' for p in s["portfolio_specs"] if p["parts"]==3)
    style=(ROOT/"artifacts/historical_entry_search_20260925/dashboard.html").read_text(encoding="utf-8").split("<style>",1)[1].split("</style>",1)[0]
    html=r'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Khung 4h/ngày và ngày bắt đầu</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / ĐỘ ỔN ĐỊNH THEO THỜI GIAN</div><h1>Đổi khung tín hiệu và ngày bắt đầu</h1><p class="muted">09/2025–05/2026 UTC · 500 USDT · x5 · tối đa5 vị thế · tổng25 USDT danh nghĩa/vị thế · không tăng vốn theo lợi nhuận</p>
<div class="notice"><b>Chưa có chiến lược đạt 50% mỗi tháng.</b><p>Nhóm tăng quá xa rồi quay đầu, ba phần và trailing có lời ở12/14 trường hợp kỳ bắt đầu–chi phí, nhưng vẫn có kỳ lỗ. Tổng chín tháng chỉ tăng khoảng4,4–5,1%. Số lần có lời không thay thế mức lợi nhuận và rủi ro từng tháng.</p><span class="pill">Mô phỏng nghiên cứu · Chưa bật live</span></div>
<div class="cards"><div class="card">Quy tắc khung4h/ngày<strong>16</strong></div><div class="card">Phép sàng lọc<strong>48</strong></div><div class="card">Đường tài khoản<strong>208</strong></div><div class="card">Ngày bắt đầu thử lại<strong>7</strong></div></div>
<section class="panel"><h2>Hiệu quả thay đổi khi bắt đầu muộn hơn</h2><p>Mỗi ô dưới đây là lợi suất của một tài khoản mới500 USDT chạy ba tháng liên tiếp. Bảy ngày bắt đầu từ01/09/2025 đến01/03/2026; mỗi ngày thử hai mức chi phí. Các kỳ chồng lấn, không phải14 thử nghiệm độc lập.</p><div class="scroll"><table><thead><tr><th>Chia ba phần / chi phí</th>__ROLLHEAD__</tr></thead><tbody>__HEAT__</tbody></table></div><p class="muted">Màu xanh chỉ có nghĩa kết thúc ba tháng trên500 USDT; không có nghĩa đạt50% mỗi tháng hoặc đủ điều kiện giao dịch thật. Không chọn bỏ những ngày bắt đầu bị lỗ.</p></section>
<section class="panel"><h2>Cả chín tháng và khoảng kết quả khi đổi ngày bắt đầu</h2><div class="scroll"><table><thead><tr><th>Quy tắc · ba phần</th><th>9 tháng cơ sở</th><th>9 tháng cao</th><th>Khoảng cuối kỳ3 tháng</th><th>Kỳ3 tháng có lời</th><th>DD9 tháng cơ sở/cao</th></tr></thead><tbody>__TABLE__</tbody></table></div><p>Đối chứng lực bán giữ nguyên quy tắc từ lượt trước. Hai đường chín tháng và hai đường khởi chạy03/2026 tái lập chính xác kết quả cũ. Các ứng viên mới được chọn theo kỳ phát triển/xác nhận, trước khi xem kết quả cuối và bảy ngày bắt đầu.</p></section>
<section class="panel"><h2>Đường tài sản và lợi suất từng tháng</h2><div class="filters"><label>Phương án chia ba phần<select id="strategy">__OPTIONS__</select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Chi phí cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Đường tài sản chín tháng"></svg><div id="chartStatus"></div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><p class="muted">Đường chín tháng giữ nguyên các vị thế cũ qua mỗi tháng, luôn tính funding và lỗ chưa chốt. Một kỳ mới500 USDT không có các vị thế đã vào trước ngày bắt đầu, nên kết quả có thể khác đoạn tương ứng của đường dài.</p></section>
<section class="panel"><h2>Các tín hiệu mới</h2><div class="facts"><div><b>Tăng quá xa rồi quay đầu</b><p>Nến4h trước đóng trên dải trung bình20 nến +2/3 độ lệch chuẩn, tăng24h trước ≥5/10%; nến hiện tại giảm và quay xuống dưới dải đã biết.</p><b>Phá đỉnh thất bại</b><p>Giá vượt đỉnh20/40 nến4h rồi đóng dưới đỉnh, râu trên≥40/60%, khối lượng≥1,5/2 lần mức trung bình trước đó.</p></div><div><b>Hồi trong xu hướng giảm ngày</b><p>Dùng ngày đã đóng: EMA10 dướiEMA20 và lợi suất7 ngày âm. Nến4h hồi lênEMA20 rồi giảm, khối lượng đủ lớn.</p><b>Phá vỡ sau co hẹp</b><p>Biên dao động12 nến nằm trong nhóm hẹp nhất30/20% lịch sử60 nến trước; giá phá đáy với khối lượng tăng.</p></div></div><p>Hai mức ngưỡng, có/không lọc BTC giảm trên khung ngày; một tín hiệu mỗi coin cách nhau ít nhất24h. Chỉ dùng nến đã đóng. ATR14 được tính trên4h trong lượt này, khác ATR1h ở các lượt trước.</p></section>
<section class="panel"><h2>Tách giai đoạn chọn và giai đoạn đánh giá</h2><p>09–11/2025 sàng lọc48 tổ hợp, khóa một ứng viên mỗi nhóm. 12/2025–02/2026 chọn hai ứng viên chẩn đoán. 03–05/2026 đánh giá cuối. Do tần suất4h thấp, ngưỡng50 sự kiện được đặt trước cho sàng lọc khám phá; không thay thế điều kiện100 sự kiện của đánh giá trước chạy thật.</p><div class="scroll"><table><thead><tr><th>Ứng viên / giữ giả định</th><th>Mẫu kỳ2/kỳ3</th><th>Kỳ2 cơ sở</th><th>Kỳ2 cao</th><th>Kỳ3 cơ sở</th><th>Kỳ3 cao</th></tr></thead><tbody>__SCREENS__</tbody></table></div><p class="muted">Đây là lợi suất trung bình mỗi sự kiện trên danh nghĩa, không phải lợi nhuận tài khoản. Sự kiện có thể chồng lấn. Hai tổ hợp có cận dưới95% dương ở kỳ sàng lọc nhưng không đủ để xác nhận chiến lược; các khoảng tin cậy chưa hiệu chỉnh thử nhiều tổ hợp. Tập lịch sử đã từng được nghiên cứu.</p></section>
<section class="panel"><h2>Điều kiện mô phỏng và đối soát</h2><p>Thử một/ba phần; TP2 USDT khôngSL, trailing3ATR/hồi1% khôngSL, hoặc trailing kèmSL1USDT và giữ tối đa72h. SL và mục tiêu tiền tỷ lệ theo phần đã khớp. Hai phần sau chỉ thêm khi giá đi thuận0,5ATR, hết hạn sau6h. Không dùng thêm vốn để gỡ lỗ.</p><p>Giảm20% từ đỉnh hoặc TP không còn giá hợp lệ: khóa mở mới, giữ và tiếp tục định giá vị thế hiện hữu. Cơ sở: phí0,05%/trượt giá thị trường0,20%; mức cao0,10%/0,50% mỗi lần khớp. TP LIMIT dùng quy ước nến đóng vượt mức giá, chưa mô phỏng khớp từng phần hay hàng đợi.</p><p>__TESTS__ kiểm thử đạt; __JOURNALS__ sổ đối soát và kiểm tra khởi tạo riêng500 USDT; __SIGNALS__ bộ tín hiệu cùng31 bộ đặc trưng không đổi khi cắt dữ liệu tương lai giữa nến4h; bốn đường đối chứng cũ và bốn đường ứng viên mới tái lập chính xác.</p><p class="muted">Giới hạn: danh sách kho có thể thiếu coin hủy niêm yết, bộ lọc sàn hiện tại, maintenance margin1% thay cho bậc lịch sử, giả định trượt giá và lấy mẫu5 phút. Không có kết luận đảm bảo lợi nhuận hoặc xác minh thanh lý chính xác. Cấu hình tài khoản thật giữ nguyên.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">208 lượt tài khoản</a> · <a href="rolling_summary.json">Tổng hợp ngày bắt đầu</a> · <a href="development.json">48 phép sàng lọc</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc khóa trước</a></p></section></main>
<script>const all=__JSON__;const fmt=t=>new Date(t).toISOString().slice(0,10),num=x=>x===null?'Không hoàn tất':x.toFixed(2);function render(){let rows=all.filter(r=>r.strategy_id===document.querySelector('#strategy').value),start=Date.UTC(2025,8,1),end=Date.UTC(2026,5,1),values=rows.flatMap(r=>r.points.map(p=>p[1]));let lo=Math.floor(Math.min(500,...values)/50)*50-10,hi=Math.ceil(Math.max(500,...values)/50)*50+10;const x=t=>62+(t-start)/(end-start)*1110,y=v=>280-(v-lo)/(hi-lo)*250;let svg='';for(let i=0;i<=5;i++){let v=lo+(hi-lo)*i/5;svg+=`<path d="M62 ${y(v)}H1172" stroke="#2a3a51"/><text x="52" y="${y(v)+4}" text-anchor="end" fill="#a7b6cc" font-size="12">${v.toFixed(0)}</text>`}svg+=`<path d="M62 ${y(500)}H1172" stroke="#96a5ba" stroke-dasharray="5 6"/>`;for(let i=0;i<=9;i++){let t=Date.UTC(2025,8+i,1);svg+=`<text x="${x(t)}" y="307" text-anchor="middle" fill="#a7b6cc" font-size="12">${fmt(t).slice(2,7)}</text>`}rows.forEach(r=>{let d=r.points.map((p,i)=>(i?'L':'M')+x(p[0]).toFixed(2)+' '+y(p[1]).toFixed(2)).join('');svg+=`<path d="${d}" fill="none" stroke="${r.cost==='base'?'#62d6c2':'#e6afed'}" stroke-width="1.7" ${r.cost==='stress'?'stroke-dasharray="5 3"':''}/>`});document.querySelector('#chart').innerHTML=svg;document.querySelector('#chartStatus').innerHTML=rows.map(r=>`${r.cost==='base'?'Cơ sở':'Chi phí cao'}: cuối ${num(r.ending_equity)} USDT · DD ${num(100*r.max_drawdown)}% · ${r.entries} vị thế · còn mở ${r.open_count}${r.first_pause?' · khóa mở mới '+fmt(r.first_pause):''}`).join('<br>');document.querySelector('#monthHead').innerHTML='<tr><th>Chi phí</th>'+Array.from({length:9},(_,i)=>'<th>'+fmt(Date.UTC(2025,8+i,1)).slice(0,7)+'</th>').join('')+'</tr>';document.querySelector('#monthBody').innerHTML=rows.map(r=>'<tr><td>'+(r.cost==='base'?'Cơ sở':'Cao')+'</td>'+Array.from({length:9},(_,i)=>{let m=r.monthly.months[i];return m?`<td class="${m.return_fraction<0?'bad':'good'}">${num(100*m.return_fraction)}%</td>`:'<td>Thiếu</td>'}).join('')+'</tr>').join('')}document.querySelector('#strategy').addEventListener('change',render);render();</script></body></html>'''
    values=dict(STYLE=style,ROLLHEAD="".join("<th>"+w.replace("start_","").replace("_","-")+"</th>" for w in rolling),
                HEAT="".join(heat),TABLE="".join(table),SCREENS="".join(screens),OPTIONS=options,
                TESTS=str(audit["unit_tests_passed"]),JOURNALS=str(audit["journals_audited"]),SIGNALS=str(audit["signal_sets_reproduced"]),
                JSON=json.dumps(series,ensure_ascii=False,separators=(",",":"),allow_nan=False).replace("</","<\\/"))
    for k,v in values.items():html=html.replace("__"+k+"__",v)
    (OUT/"dashboard.html").write_text(html,encoding="utf-8")
    md=["# Khung4h/ngày và độ nhạy ngày bắt đầu — lượt05","",
        "Chưa đạt mục tiêu50% mỗi tháng.16 quy tắc mới,48 phép sàng lọc,208 lượt tài khoản, gồm bảy kỳ ba tháng khởi chạy riêng và đường chín tháng. Mọi kỳ bắt đầu500USDT; giữ25USDT danh nghĩa/vị thế,x5,tối đa5 vị thế.","",
        "| Quy tắc | 9 tháng cơ sở | 9 tháng cao | Khoảng cuối kỳ3 tháng | Kỳ3 tháng có lời | DD9 tháng cơ sở/cao |",
        "|---|---:|---:|---:|---:|---:|",*mdrows,"",
        "Tăng quá xa rồi quay đầu/ba phần/trailing: cuối chín tháng521,96–525,50USDT; có lời12/14 trường hợp ngày bắt đầu–chi phí. Nhưng khởi chạy03/2026 chỉ488,26–489,09USDT, và kỳ lỗ vẫn còn. Bảy kỳ chồng lấn nên14 kết quả không phải14 mẫu độc lập.","",
        "Đường dài giữ vị thế qua tháng, còn kỳ khởi chạy lại không kế thừa lệnh cũ. Không chọn lại ngày bắt đầu để đạt lợi nhuận. Không thay mục tiêu50% mỗi tháng bằng tỷ lệ số kỳ có lời.","",
        "Nhóm phá đỉnh thất bại khôngSL giảm hơn64% từ đỉnh trong đường dài. Nhóm đảo chiều tăng quá xa vẫn còn5 vị thế cuối kỳ; thời gian giữ lớn nhất khoảng127 ngày. Rủi ro/vốn mắc kẹt chưa được giải quyết bằng đổi khung thời gian.","",
        "91 kiểm thử đạt;208 sổ và khởi tạo tài khoản đối soát;16 bộ tín hiệu và31 bộ đặc trưng kiểm tra không dùng tương lai; bốn đường đối chứng và bốn đường ứng viên tái lập chính xác.","",
        s["protocol"]["limitations"],"",
        "[Dashboard](dashboard.html) · [Toàn bộ kết quả](comparison.csv) · [Tổng hợp ngày bắt đầu](rolling_summary.json) · [Đối soát](verification.json)"]
    (OUT/"report.md").write_text("\n".join(md),encoding="utf-8")
    print(OUT/"dashboard.html")


if __name__=="__main__":main()
