"""Publish full replay cost sensitivity and same-fill accounting separately."""

import json
from html import escape
import pandas as pd
from compare_account_risk import ROOT,write
from search_execution_costs import OUT,PROFILES,WINDOWS


def name(p):
    family=("Đảo chiều + lọc 6h" if p["id"].startswith("benchmark") else "Yếu tuần, không lọc thị trường" if p["id"].startswith("raw7d") else "Yếu tuần/BTC + thị trường giảm")
    return family+f" · ký quỹ {p['notional']/5:g} · "+("đóng tối đa 7 ngày" if p["holding"]=="time168" else "giữ không hạn")


def num(x):return "Không hoàn tất" if x is None else f"{x:.2f}"
def tr(values):return "<tr>"+"".join("<td>"+escape(str(v))+"</td>" for v in values)+"</tr>"


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));v=json.loads((OUT/"verification.json").read_text(encoding="utf-8"));findings=json.loads((OUT/"findings.json").read_text(encoding="utf-8"))
    assert v["journals_audited"]==len(s["results"])==126
    lookup={(r["strategy_id"],r["window"],r["cost"]):r for r in s["results"]};summary=[];decomposition=[];mdrows=[];series=[]
    for spec in s["specs"]:
        vals=[name(spec)]+[num(lookup[(spec["id"],w,c)]["ending_equity"]) for w in ["year","later"] for c in ["base","no_execution_cost","no_cost_no_funding"]]
        summary.append(tr(vals));mdrows.append("| "+" | ".join(vals)+" |")
        if spec["notional"]==25:
            for w in ["year","later"]:
                r=lookup[(spec["id"],w,"base")];a=r["attribution"]
                decomposition.append(tr([name(spec),"12 tháng" if w=="year" else "3 tháng sau",
                    *[num(a[k]) for k in ["price_pnl_at_reference","funding","slippage_paid","commissions","net_marked_pnl"]]]))
    for row in s["results"]:
        f=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet");ix={0,len(f)-1}
        for _,g in f.groupby((f["at"]-f["at"].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(row,points=[[int(q["at"]),round(q.equity,6)] for _,q in f.loc[sorted(ix)].iterrows()]))
    write(OUT/"dashboard_data.json",series)
    style=(ROOT/"artifacts/market_breadth_20260925/dashboard.html").read_text(encoding="utf-8").split("<style>",1)[1].split("</style>",1)[0]
    options="".join(f'<option value="{p["id"]}">'+escape(name(p))+'</option>' for p in s["specs"])
    costs="".join(f'<option value="{p["id"]}"'+(' selected' if p["id"]=="no_execution_cost" else '')+'>'+escape(p["label"])+'</option>' for p in PROFILES)
    html=r'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Tách lợi thế và chi phí</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / GIÁ, FUNDING VÀ CHI PHÍ · LƯỢT 14</div><h1>__TITLE__</h1><p class="muted">01/09/2025–01/09/2026, UTC, không gồm ngày cuối · 500 USDT · Cross x5 · tối đa 5 vị thế · cùng tín hiệu và chính sách đã khóa</p><div class="notice"><b>__TARGET__</b><p>__FINDING__</p></div>
<div class="cards"><div class="card">Chiến lược/quy mô giữ nguyên<strong>6</strong></div><div class="card">Giả định chi phí<strong>7</strong></div><div class="card">Đường tài khoản<strong>126</strong></div><div class="card">Kiểm thử đạt<strong>62</strong></div></div>
<section class="panel"><h2>Mô phỏng lại toàn bộ khi đổi chi phí</h2><p>Các cột đều là tài sản cuối từ 500 USDT. Cơ sở: phí 0,05% và trượt giá 0,20% mỗi lần khớp. “Không phí/trượt” vẫn giữ funding thực; “bỏ cả funding” là giả định để tách tác động. Mỗi cửa sổ chạy riêng; không cộng tài sản các cửa sổ.</p><div class="scroll"><table><thead><tr><th>Chiến lược</th><th>Cả năm · cơ sở</th><th>Cả năm · không phí/trượt</th><th>Cả năm · bỏ cả funding</th><th>3 tháng · cơ sở</th><th>3 tháng · không phí/trượt</th><th>3 tháng · bỏ cả funding</th></tr></thead><tbody>__SUMMARY__</tbody></table></div><p>Đổi chi phí có thể làm đổi điều kiện vào, lượng khớp, chỗ trống và thời điểm dừng mở mới. Kết quả không nhất thiết tăng đều khi chi phí giảm. Kịch bản không chi phí không phải mức lợi nhuận tối đa của mọi chiến lược hoặc mọi đường giao dịch.</p></section>
<section class="panel"><h2>Tách lãi/lỗ trên đúng các lần khớp cơ sở · ký quỹ 5 USDT</h2><p>Công thức: <b>lãi/lỗ do giá + funding − trượt giá − phí = lãi/lỗ tài khoản</b>. Cột do giá dùng giá mở nến tham chiếu và lượng khớp thực, vị thế mở dùng Mark cuối kỳ. Đây là phép đối soát trên cùng giao dịch, không phải chạy lại chiến lược. Không tự tính phí thoát cho vị thế chưa đóng.</p><div class="scroll"><table><thead><tr><th>Chiến lược</th><th>Kỳ</th><th>Do giá</th><th>Funding nhận/trả</th><th>Trượt giá</th><th>Phí</th><th>Lãi/lỗ sau tất cả</th></tr></thead><tbody>__DECOMP__</tbody></table></div></section>
<section class="panel"><h2>So sánh từng mức chi phí với cơ sở</h2><div class="filters"><label>Chiến lược<select id="strategy">__OPTIONS__</select></label><label>Giai đoạn<select id="window"><option value="year">Cả năm · 09/2025–08/2026</option><option value="later">Tài khoản mới · 06–08/2026</option><option value="development">09/2025–05/2026</option></select></label><label>Giả định chi phí<select id="cost">__COSTS__</select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Giả định được chọn</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="So sánh tài sản gồm vị thế mở theo thời gian"></svg><div id="chartStatus">Đang tải dữ liệu…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><p class="muted">Giữ đỉnh/đáy từng ngày trên biểu đồ. Không biến tháng thiếu thành lợi suất 0%. Không phí, không funding hoặc trượt giá thấp đều là giả định chưa xác nhận bằng dữ liệu thực thi.</p></section>
<section class="panel"><h2>Quy tắc và giới hạn</h2><p>Giữ nguyên ba nguồn: đảo chiều/lọc6h; yếu tuần không lọc thị trường; yếu tuần điều chỉnh BTC kèm ≥75% coin dưới EMA60 và BTC giảm. Hai mức danh nghĩa25/100USDT, tương ứng ký quỹ5/20USDT; ba phần0,25ATR, trailing3ATR/hồi1%, khóa mở mới20%DD. Nguồn thứ ba thêm đóng tối đa7ngày, bao gồm lỗ; chỉ là phương án nghiên cứu.</p><p>Bảy giả định: bỏ phí/trượt/funding; bỏ phí/trượt và giữ funding; phí0,05% và trượt0/1/5/20bps; phí0,10% và trượt50bps. 1bps=0,01%. Mỗi cấu hình mô phỏng lại đầy đủ, không nhân tuyến tính lợi nhuận hoặc lựa chọn mức chi phí để làm đẹp báo cáo.</p><p>__AUDIT__</p><p class="muted">Chưa có độ sâu sổ lệnh lịch sử để xác nhận trượt giá thấp. MMR1% là proxy thay bậc lịch sử; bộ lọc sàn hiện tại, lấy mẫu5phút, kho có thể thiếu coin hủy niêm yết, lịch sử đã thử nhiều lần. Lợi nhuận giả định không chứng minh lợi thế tương lai. Không đổi cấu hình live.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">126 kết quả</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc</a></p></section></main>
<script>const spans=__SPANS__,labels=__LABELS__;let data=[];const num=x=>x===null||x===undefined?'—':x.toFixed(2),date=t=>new Date(t).toISOString().slice(0,10);
function render(){if(!data.length)return;const chosen=document.querySelector('#cost').value,w=document.querySelector('#window').value,rows=data.filter(r=>r.strategy_id===document.querySelector('#strategy').value&&r.window===w&&(r.cost==='base'||r.cost===chosen)),[start,end]=spans[w],months=[];for(let d=new Date(start);d.getTime()<end;d.setUTCMonth(d.getUTCMonth()+1))months.push(d.getTime());
const values=rows.flatMap(r=>r.points.map(p=>p[1]));let lo=Math.floor(Math.min(500,...values)/25)*25-5,hi=Math.ceil(Math.max(500,...values)/25)*25+5;const x=t=>62+(t-start)/(end-start)*1110,y=v=>280-(v-lo)/(hi-lo)*250;let svg='';
for(let i=0;i<=5;i++){let v=lo+(hi-lo)*i/5;svg+=`<path d="M62 ${y(v)}H1172" stroke="#2a3a51"/><text x="52" y="${y(v)+4}" text-anchor="end" fill="#a7b6cc" font-size="12">${v.toFixed(0)}</text>`}svg+=`<path d="M62 ${y(500)}H1172" stroke="#96a5ba" stroke-dasharray="5 6"/>`;
for(const t of [...months,end])svg+=`<text x="${x(t)}" y="310" text-anchor="middle" fill="#a7b6cc" font-size="12">${date(t).slice(2,7)}</text>`;
for(const r of rows){let d=r.points.map((p,i)=>(i?'L':'M')+x(p[0]).toFixed(2)+' '+y(p[1]).toFixed(2)).join('');svg+=`<path d="${d}" fill="none" stroke="${r.cost==='base'?'#62d6c2':'#e6afed'}" stroke-width="1.7" ${r.cost!=='base'?'stroke-dasharray="5 3"':''}/>`}document.querySelector('#chart').innerHTML=svg;
document.querySelector('#chartStatus').innerHTML=rows.map(r=>`${labels[r.cost]}: ${r.ending_equity===null?'Không hoàn tất · dừng '+date(r.stop_event?.at??r.points.at(-1)[0]):'cuối '+num(r.ending_equity)+' USDT'} · DD ${num(r.max_drawdown*100)}% · ${r.entries} vị thế vào · ${r.open_count} còn mở · tuổi mở lớn nhất ${r.utilization.open_hold_max_days===null?'không còn vị thế':num(r.utilization.open_hold_max_days)+' ngày'}${r.paused?' · khóa mở mới':''}`).join('<br>');
document.querySelector('#monthHead').innerHTML='<tr><th>Chi phí</th>'+months.map(t=>'<th>'+date(t).slice(0,7)+'</th>').join('')+'</tr>';
document.querySelector('#monthBody').innerHTML=rows.map(r=>'<tr><td>'+labels[r.cost]+'</td>'+months.map(t=>{const m=r.monthly.months.find(v=>v.start===t);return m?`<td class="${m.return_fraction<0?'bad':'good'}">${num(m.return_fraction*100)}%</td>`:'<td>Không đủ dữ liệu</td>'}).join('')+'</tr>').join('');}
for(const id of ['strategy','window','cost'])document.querySelector('#'+id).addEventListener('change',render);fetch('dashboard_data.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{data=d;render()}).catch(e=>document.querySelector('#chartStatus').textContent='Không tải được dữ liệu: '+e.message);
</script></body></html>'''
    target=f"{s['target_met_rows']}/126 đường đạt 50% từng tháng; {s['incomplete_paths']} đường không hoàn tất."
    audit=f"{v['journals_audited']} sổ đối soát; {v['baseline_paths_exact']} đường cơ sở/chi phí cao khớp lượt trước; {v['replayed_paths_exact']} đường không phí chạy lại khớp. Kiểm tra lượng vị thế tại {v['funding_quantities_checked']} lần funding và {v['attribution_identities_checked']} phép tách lãi/lỗ đầy đủ. 62 kiểm thử đạt; nguồn dữ liệu/mã nguồn và cấu hình live khớp hash."
    for k,val in dict(STYLE=style,TITLE=escape(findings["title"]),TARGET=escape(target),FINDING=escape(findings["finding"]),SUMMARY="".join(summary),DECOMP="".join(decomposition),OPTIONS=options,COSTS=costs,AUDIT=escape(audit),SPANS=json.dumps(WINDOWS),LABELS=json.dumps({p["id"]:p["label"] for p in PROFILES},ensure_ascii=False)).items():html=html.replace("__"+k+"__",val)
    (OUT/"dashboard.html").write_text(html,encoding="utf-8")
    md=["# "+findings["title"],"",target,"",findings["finding"],"",
        "| Chiến lược | Năm cơ sở | Năm không phí/trượt | Năm bỏ cả funding | 3tháng cơ sở | 3tháng không phí/trượt | 3tháng bỏ cả funding |","|---|---:|---:|---:|---:|---:|---:|",*mdrows,"",
        "Mỗi cửa sổ khởi chạy riêng500USDT. Mô phỏng lại toàn bộ có thể đổi lượng khớp, điều kiện vào và trạng thái dừng; lợi nhuận không nhất thiết tăng khi giảm chi phí. Zero cost không phải trần toán học của mọi chiến lược. Phép tách chi phí giữ cùng lượng/thời điểm khớp chỉ là đối soát kế toán.","",audit,"",
        "Không có lịch sử orderbook chứng minh mức trượt thấp. MMR1%proxy,currentfilters,5msampling,survivorship và lịch sử nghiên cứu lặp còn hạn chế. Không thay live.","",
        "[Dashboard](dashboard.html) · [126 kết quả](comparison.csv) · [Quy tắc](protocol.json)"]
    (OUT/"report.md").write_text("\n".join(md),encoding="utf-8")
    write(OUT/"goal_progress.json",dict(classification="progress",goal_status="active",achieved=False,runs=126,target_passes=s["target_met_rows"],evidence=findings["finding"],next_steps=findings["next_steps"],live_config_unchanged=True))
    print(OUT/"dashboard.html")


if __name__=="__main__":main()
