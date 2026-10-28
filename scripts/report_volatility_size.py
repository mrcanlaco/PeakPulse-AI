"""Capital and capacity sensitivity of frozen momentum pullback entries."""
import json
from html import escape
import xml.etree.ElementTree as ET
import pandas as pd
from search_volatility_size import OUT,read,ROOT,sha,write

def name(sp):
    mode=f"Cố định {sp['amount']} USDT" if sp['sizing']=='fixed' else f"ATR {sp['amount']:g} USDT · vốn 25–250"
    return f"{mode} · tối đa {sp['cap']} vị thế"



def main():
    s=read(OUT/'summary.json');v=read(OUT/'verification.json');tests=ET.parse(OUT/'unit_tests.xml').getroot()
    assert not tests.findall('.//failure') and not tests.findall('.//error');count=len(tests.findall('.//testcase'))
    specs={sp['id']:sp for sp in s['specs']};look={(r['strategy_id'],r['window'],r['cost']):r for r in s['results']}
    robust={(r['strategy_id'],r['cost']):r for r in s['robustness']};selected={x['strategy_id'] for x in s['selected'] if x['strategy_id']}
    fmt=lambda x:'Không hoàn tất' if x is None else f'{x:.2f}'
    tr=lambda cells:'<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in cells)+'</tr>'
    tables=[];rolling=[]
    for sp in s['specs']:
        rs=lambda w:[look[(sp['id'],w,c)] for c in ['base','stress']]
        tables.append([name(sp)+(' ★' if sp['id'] in selected else ''),*[' / '.join(fmt(r['ending_equity']) for r in rs(w)) for w in ['development','later','year']],
            ' / '.join(str(r['entries']) for r in rs('year')),' / '.join(f"{100*r['max_drawdown']:.2f}%" for r in rs('year'))])
        rr=[robust[(sp['id'],c)] for c in ['base','stress']]
        rolling.append([name(sp),' / '.join(str(r['profitable'])+'/10' for r in rr),' / '.join(fmt(r['worst_ending']) for r in rr),
            ' / '.join(f"{100*r['worst_drawdown']:.2f}%" for r in rr),' / '.join(str(r['nonoverlapping_profitable'])+'/4' for r in rr)])
    target=f"{s['target_met_rows']}/{len(s['results'])} đường đạt ít nhất 50% trong từng tháng; {s['incomplete_paths']} đường không hoàn tất."
    choice='; '.join(name(specs[k]) for k in sorted(selected)) or 'Không có cấu hình đạt tiêu chí chọn'
    focus=next((x['strategy_id'] for x in s['selected'] if x['strategy_id']),'vol_cap5_fixed25')
    rs=[look[(focus,'later',c)] for c in ['base','stress']]
    finding=f"Lựa chọn khóa bằng 09/2025–05/2026: {choice}. {name(specs[focus])}, khởi chạy riêng 06–08 từ 500 USDT: tài sản cuối {fmt(rs[0]['ending_equity'])} / {fmt(rs[1]['ending_equity'])} USDT; {rs[0]['entries']} / {rs[1]['entries']} vị thế vào. Cần đối chiếu các tháng âm và nhiều mốc khởi chạy, không suy ra hiệu quả chỉ từ một quý có lời."
    rr=[robust[(focus,c)] for c in ['base','stress']]
    finding+=f" Trên 10 mốc ba tháng, có lời ở {rr[0]['profitable']}/10 và {rr[1]['profitable']}/10; tài sản tệ nhất {fmt(rr[0]['worst_ending'])} / {fmt(rr[1]['worst_ending'])} USDT. Các cửa sổ chồng lấn và đã được nghiên cứu, không phải 10 mẫu tương lai độc lập."
    probe='vol_cap5_atr_dollar2p5'
    annual=[look[(probe,'year',c)] for c in ['base','stress']]
    rolling_probe=[robust[(probe,c)] for c in ['base','stress']]
    finding+=f" Biến thể ATR 2,5 USDT / tối đa 5 vị thế có tài sản cả năm {fmt(annual[0]['ending_equity'])} / {fmt(annual[1]['ending_equity'])} USDT, nhưng chỉ có lời ở {rolling_probe[0]['profitable']}/10 và {rolling_probe[1]['profitable']}/10 mốc khởi chạy; kỳ tệ nhất {fmt(rolling_probe[0]['worst_ending'])} / {fmt(rolling_probe[1]['worst_ending'])} USDT. Đây là đối chiếu nghiên cứu, không phải lựa chọn mới sau khi xem kết quả."
    audit=f"{count} kiểm thử đạt; đối soát {v['totals']['journals']} sổ, {v['totals']['baseline_paths_exact']} đối chứng tài chính khớp lượt cũ và {v['totals']['replayed_paths_exact']} đường chạy lại khớp. Tái dựng {v['totals']['capital_checks']:,} lần kiểm tra vốn, gồm {v['totals']['capital_denied']:,} lần thiếu vốn, cùng {v['totals']['cancellations']:,} sự kiện hủy phần vào tiếp. Kiểm tra {v['totals']['equity_states']:,} mốc tài sản."
    failures=read(OUT/'incomplete_paths.json')
    failure_note=f"Có {len(failures)} đường dừng sớm khi tài sản chạm ngưỡng maintenance proxy 1%; sổ tiền và vị thế tại thời điểm dừng đã được tính lại. Không gán số dư cuối hoặc dựng lệnh thanh lý giả. DD vượt 100% nếu có chỉ là Mark lấy mẫu vượt qua tài sản 0 trước khi dừng mô phỏng, không phải mức lỗ thực hiện đã xác minh trên sàn."
    halt_times=sorted({f['stop_event']['at'] for f in failures})
    failure_note+=' Các đường này tập trung ở '+str(len(halt_times))+' thời điểm: '+', '.join(pd.Timestamp(t,unit='ms',tz='UTC').strftime('%d/%m/%Y %H:%M UTC') for t in halt_times)+'. Các cấu hình và kỳ chạy có thể lặp cùng biến động, không phải '+str(len(failures))+' sự kiện độc lập.'
    finding+=' '+failure_note
    series=[]
    for row in s['results']:
        raw=read(OUT/'runs'/f'{row["id"]}.json');curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet');ix={0,len(curve)-1}
        for _,g in curve.groupby((curve['at']-curve['at'].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        retained=sum(p['unrealized']-p['entry_fee']+p['funding'] for p in raw['open_positions'])
        if raw['ending_equity'] is not None:assert abs(500+raw['closed_trade_net']+retained-raw['ending_equity'])<1e-6
        series.append(dict(row,
            closed_net=raw['closed_trade_net'],retained_net=retained,fees=raw['fees'],points=[[int(p['at']),round(p.equity,6)] for _,p in curve.loc[sorted(ix)].iterrows()]))
    write(OUT/'dashboard_data.json',series)
    old=(ROOT/'artifacts/signal_priority_20260925/dashboard.html').read_text(encoding='utf-8');style=old.split('<style>',1)[1].split('</style>',1)[0];script=old.split('<script>',1)[1].split('</script>',1)[0]
    script='const spans='+json.dumps(s['protocol']['windows'])+script[script.index(',labels='):]
    extra="""function capitalRender(){const st=document.querySelector('#strategy').value,w=document.querySelector('#window').value,c=document.querySelector('#cost').value;document.querySelector('#capitalBody').innerHTML=data.filter(r=>r.strategy_id===st&&r.window===w&&(r.cost==='base'||r.cost===c)).map(r=>`<tr><td>${r.cost==='base'?'Cơ sở':'Cao'}</td><td>${r.entries}</td><td>${num(r.sizing_metrics.mean_budget)}</td><td>${num(r.sizing_metrics.mean_origin_atr_dollars)}</td><td>${num(r.utilization.mean_positions)}</td><td>${num(r.utilization.mean_committed_margin)}</td><td>${num(r.utilization.peak_committed_margin)}</td><td>${r.margin_rejections}</td><td>${num(100*r.utilization.fraction_time_paused)}%</td><td>${num(r.closed_net)}</td><td>${num(r.retained_net)}</td></tr>`).join('');}const chartRender=render;render=function(){chartRender();capitalRender();};"""
    script=script.replace("for(const id of ['strategy','window','cost'])",extra+"for(const id of ['strategy','window','cost'])",1)
    options=''.join(f'<option value="{sp["id"]}"'+(' selected' if sp['id']==focus else '')+'>'+escape(name(sp))+'</option>' for sp in s['specs'])
    periods=''.join(f'<option value="{w}"'+(' selected' if w=='later' else '')+'>'+escape({'development':'09/2025–05/2026 · kỳ chọn','year':'09/2025–08/2026 · cả năm','later':'06–08/2026'}.get(w,'Ba tháng từ '+pd.Timestamp(t[0],unit='ms',tz='UTC').strftime('%m/%Y')))+'</option>' for w,t in s['protocol']['windows'].items())
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Chia vốn theo biến động</title><style>__STYLE__</style></head><body><main><div class="eyebrow">ĐẢO VÀNG / NGHIÊN CỨU LƯỢT 33</div><h1>Chia vốn theo ATR có cải thiện lợi nhuận?</h1><p class="muted">Cố định xu hướng 7 ngày + chờ hồi 0,5 ATR · Long + Short · tài khoản 500 USDT · Cross x5</p><div class="notice"><b>__TARGET__</b><p>__FINDING__</p><p>Giữ nguyên tín hiệu, trailing và không cắt lỗ. Thử ngân sách phụ thuộc ATR của từng tín hiệu, so với ngân sách cố định. Mức ATR bằng tiền không phải giới hạn lỗ; chưa thay cấu hình live.</p></div>
<section class="panel"><h2>Toàn bộ 10 cấu hình</h2><p>Cặp số chi phí cơ sở / chi phí cao. ★ là lựa chọn khóa trước khi chạy các kỳ sau: cả hai mức chi phí có lời, DD dưới 20%, ít nhất 20 lệnh đóng, đủ dữ liệu; ưu tiên tháng tệ nhất rồi tài sản cuối. Quy mô là tổng danh nghĩa của cả ba phần, không phải mỗi phần.</p><div class="scroll"><table><thead>__HEAD__</thead><tbody>__TABLE__</tbody></table></div></section>
<section class="panel"><h2>Tài sản và các khoản lời/lỗ</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Kỳ<select id="window">__PERIODS__</select></label><label>Chi phí<select id="cost"><option value="stress">Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản gồm vị thế còn mở"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><div class="scroll"><table><thead><tr><th>Chi phí</th><th>Vị thế đã mở</th><th>Ngân sách TB</th><th>Giá trị 1 ATR TB</th><th>Vị thế TB</th><th>Vốn giữ chỗ TB</th><th>Vốn giữ chỗ tối đa</th><th>Lần thiếu vốn</th><th>Thời gian khóa mở mới</th><th>Ròng lệnh đóng</th><th>Đóng góp lệnh mở</th></tr></thead><tbody id="capitalBody"></tbody></table></div><p>Ngân sách TB tính trên vị thế được nhận; giá trị 1 ATR TB = ngân sách × ATR gốc / giá gốc, trước làm tròn và khớp từng phần, không phải số tiền có thể mất tối đa. Vốn giữ chỗ gồm ký quỹ mô phỏng theo Mark, vốn dành cho phần chưa khớp và phí dự kiến; không phải mức lỗ tối đa. Các trung bình số vị thế và vốn giữ chỗ có trọng số thời gian; nếu đường dừng sớm chỉ tính đoạn quan sát. Lần thiếu vốn tính cả vào mới và vào thêm. Tài sản = 500 + ròng lệnh đóng + đóng góp lệnh mở; các khoản ròng đã gồm phí và funding. Khi DD đạt 20%, khóa mở mới nhưng vẫn giữ vị thế và trailing. Không tự bật lại.</p></section>
<section class="panel"><h2>Thử từ 10 mốc khởi chạy</h2><p>Mỗi kỳ ba tháng có 500 USDT riêng, bắt đầu từ 09/2025 đến 06/2026. Các kỳ chồng lấn, chỉ có bốn quý không chồng lấn. Đây là lịch sử đã nghiên cứu nhiều lần, chưa phải bằng chứng tương lai mới. Kỳ không hoàn tất vẫn ở mẫu số; tài sản tệ nhất chỉ tính kỳ hoàn tất.</p><div class="scroll"><table><thead>__RHEAD__</thead><tbody>__ROLLING__</tbody></table></div></section>
<section class="panel"><h2>Quy tắc vốn và đối soát</h2><p>Cùng tín hiệu Long/Short momentum 7 ngày, chờ hồi thuận giá 0,5 ATR trong giờ thứ 1–23 sau tín hiệu gốc. Giữ ATR14 nến 4 giờ, hướng và độ ưu tiên lúc phát tín hiệu. Mọi mức vốn dùng cùng các ứng viên; không tăng vốn theo lợi nhuận hoặc nhân tuyến tính lợi nhuận cũ.</p><p>Đối chứng cố định 25 hoặc 100 USDT danh nghĩa. Biến thể ATR đặt ngân sách = mức ATR bằng tiền × giá đóng cửa gốc / ATR gốc, giới hạn 25–250 USDT; thử mức 1, 2,5 và 5 USDT. Dùng ATR14 nến 4 giờ đã đóng và giá gốc trước khi chờ hồi, khóa ngân sách cho cả ba phần, không tính lại theo biến động mới. Mức sàn/trần làm giá trị ATR thực tế khác mục tiêu. Giới hạn 5 hoặc 10 vị thế; một vị thế mỗi coin. Mỗi vị thế chia ba phần, chỉ vào thêm thuận giá 0,25 ATR và hết hạn sau 6 giờ. Trailing kích hoạt ở 3 ATR, hồi 1%; không stop-loss, không đóng lỗ theo thời gian.</p><p>Trước khi vào mới, giữ đủ chỗ cho phần hiện tại và hai phần dự kiến, kể cả phần cam kết của vị thế khác. Khi vào thêm, kiểm tra lại phần còn lại. Hết hạn, kích hoạt trailing, sai quy tắc khối lượng, thiếu vốn hoặc dừng mở mới sẽ hủy phần vào tiếp theo quy tắc đã có. Nhật ký quan sát ghi các lần kiểm tra và hủy; sổ vốn được tái dựng độc lập từ lần khớp, funding và sự kiện hủy. Giới hạn 10 không có nghĩa luôn đủ vốn để mở 10; từng vị thế giữ chỗ theo ngân sách riêng.</p><p>__AUDIT__</p></section>
<section class="panel"><h2>Giới hạn kết luận</h2><p>Phí/trượt mỗi lần khớp: cơ sở 0,05%/0,20%, cao 0,10%/0,50%. Funding thực, mọi vị thế mở được định giá. Tập 30 coin cố định, bộ lọc sàn hiện tại, maintenance proxy 1% và dữ liệu 5 phút chưa chứng minh thanh lý lịch sử hoặc khả năng khớp thật. Chưa đạt 50% mỗi tháng; chưa bật live.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">Mọi kết quả</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc khóa</a> · <a href="incomplete_paths.json">Đường không hoàn tất</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    for key,value in dict(STYLE=style,TARGET=escape(target),FINDING=escape(finding),HEAD=tr(['Cấu hình vốn','Tài sản kỳ chọn','Tài sản 06–08','Tài sản cả năm','Số vị thế cả năm','DD cả năm']),TABLE=''.join(tr(r) for r in tables),OPTIONS=options,PERIODS=periods,RHEAD=tr(['Cấu hình vốn','Kỳ có lời','Tài sản tệ nhất','DD lớn nhất','Quý có lời']),ROLLING=''.join(tr(r) for r in rolling),AUDIT=escape(audit),SCRIPT=script).items():html=html.replace('__'+key+'__',value)
    (OUT/'dashboard.html').write_text(html,encoding='utf-8')
    md=['# Chia vốn theo biến động','',target,'',finding,'','Cặp số chi phí cơ sở / cao. ★ chọn bằng kỳ đầu; các biến thể thay cách phân bổ theo ATR và giới hạn vị thế, giữ nguyên tín hiệu/cách thoát.',
        '|Cấu hình vốn|Kỳ chọn|06–08|Cả năm|Số vị thế|DD cả năm|','|---|---:|---:|---:|---:|---:|',*['| '+' | '.join(r)+' |' for r in tables],'',
        '|Cấu hình vốn|Kỳ có lời|Tệ nhất|DD lớn nhất|Quý có lời|','|---|---:|---:|---:|---:|',*['| '+' | '.join(r)+' |' for r in rolling],'',audit,'',
        'Các cửa sổ chồng lấn và đã được nghiên cứu trước. Tài sản tính cả vị thế chưa đóng. Ngân sách25–250 là danh nghĩa toàn bộ3phần; ký quỹ dự kiến5–50ởx5. ATR-dollar sizing dùng thông tin gốc, không phải stoploss hoặc giới hạnlỗ. No live changes.',s['protocol']['limitations']]
    (OUT/'report.md').write_text('\n'.join(md),encoding='utf-8');write(OUT/'findings.json',dict(target=target,finding=finding))
    write(OUT/'goal_progress.json',dict(classification='progress',goal_status='active',achieved=False,runs=len(s['results']),target_passes=s['target_met_rows'],evidence=finding,
        next_steps=['Do not assume profitableannualreturn scales linearly or that largerpositionlimits are fullyfunded.','Nextresearch must improve monthlyexpectancy under finitecapital, not optimize around a lucky historicalwindow.'],live_config_unchanged=True))
    assert sha(ROOT/'configs/live.yaml')==s['protocol']['live_config_sha256'];print(OUT/'dashboard.html')


if __name__=='__main__':main()
