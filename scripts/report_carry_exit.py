"""Capital and capacity sensitivity of frozen momentum pullback entries."""
import json
from html import escape
import xml.etree.ElementTree as ET
import pandas as pd
from search_carry_exit import OUT,read,ROOT,sha,write,DIAG
from report_pullback_dip import closed_attribution

REFS={'normal25':'Nguồn gốc · 25 USDT','counter100':'Hồi 24h + lọc carry · 100 USDT','deep25':'Hồi sâu >2 ATR · 25 USDT · chẩn đoán'}

def name(sp):
    rule='Giữ như cũ' if sp['carry_fraction'] is None else f"Đóng khi funding âm {sp['notional']*sp['carry_fraction']:g} USDT ({sp['carry_fraction']*100:g}%)"
    return REFS[sp['reference']]+' · '+rule



def main():
    s=read(OUT/'summary.json');v=read(OUT/'verification.json');signals=read(OUT/'signals.json');tests=ET.parse(OUT/'unit_tests.xml').getroot()
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
    focus=next((x['strategy_id'] for x in s['selected'] if x['reference']=='normal25' and x['strategy_id']),'fexit_normal25_hold')
    rs=[look[(focus,'later',c)] for c in ['base','stress']]
    finding=f"Lựa chọn khóa bằng 09/2025–05/2026: {choice}. {name(specs[focus])}, khởi chạy riêng 06–08 từ 500 USDT: tài sản cuối {fmt(rs[0]['ending_equity'])} / {fmt(rs[1]['ending_equity'])} USDT; {rs[0]['entries']} / {rs[1]['entries']} vị thế vào. Cần đối chiếu các tháng âm và nhiều mốc khởi chạy, không suy ra hiệu quả chỉ từ một quý có lời."
    rr=[robust[(focus,c)] for c in ['base','stress']]
    finding+=f" Trên 10 mốc ba tháng, có lời ở {rr[0]['profitable']}/10 và {rr[1]['profitable']}/10; tài sản tệ nhất {fmt(rr[0]['worst_ending'])} / {fmt(rr[1]['worst_ending'])} USDT. Các cửa sổ chồng lấn và đã được nghiên cứu, không phải 10 mẫu tương lai độc lập."
    control=look[('fexit_deep25_hold','year','base')];capped=look[('fexit_deep25_f010','year','base')]
    finding+=f" Nhóm chẩn đoán hồi sâu 25 USDT, chi phí cơ sở: ngân sách funding âm 0,25 USDT đưa tài sản cả năm từ {fmt(control['ending_equity'])} lên {fmt(capped['ending_equity'])}, DD từ {100*control['max_drawdown']:.2f}% xuống {100*capped['max_drawdown']:.2f}%. Đây là giảm thiệt hại trong kỳ này, chưa đạt lợi nhuận dương cả năm hoặc mục tiêu mỗi tháng."
    target_event=read(DIAG/'cost_diagnostic.json')['worst']['event_id'];diagnostic=[]
    for mode in ['hold','f005','f010','f020']:
        for cost,fee,slip in s['protocol']['costs']:
            run_id=f'year_{cost}_fexit_deep25_{mode}';raw=read(OUT/'runs'/f'{run_id}.json')
            admitted=any(j['kind']=='entry' and j['event_id']==target_event for j in raw['journal'])
            trade=next((t for t in closed_attribution(raw,fee) if t['event_id']==target_event),None)
            diagnostic.append(dict(run=run_id,mode=mode,cost=cost,admitted=admitted,closed_trade=trade))
    write(OUT/'diagnostic_trade.json',dict(event_id=target_event,comparisons=diagnostic,note='One previously diagnosed event. If not admitted, no hypothetical trade is inserted. Whole-wallet outcomes remain authoritative.'))
    diag_rows=[]
    for d in diagnostic:
        t=d['closed_trade'];status='Đã đóng' if t else 'Còn mở' if d['admitted'] else 'Không vào sự kiện này'
        label='Giữ như cũ' if d['mode']=='hold' else {'f005':'Funding âm 0,125 USDT','f010':'Funding âm 0,25 USDT','f020':'Funding âm 0,50 USDT'}[d['mode']]
        diag_rows.append([label,d['cost'],status,*([fmt(t[k]) for k in ['held_days','gross','funding','net']] if t else ['—']*4)])
    audit=f"{count} kiểm thử đạt; đối soát {v['totals']['journals']} sổ, {v['totals']['baseline_paths_exact']} đối chứng tài chính khớp lượt cũ và {v['totals']['replayed_paths_exact']} đường chạy lại khớp. Tái dựng {v['totals']['capital_checks']:,} lần kiểm tra vốn, gồm {v['totals']['capital_denied']:,} lần thiếu vốn, cùng {v['totals']['cancellations']:,} sự kiện hủy phần vào tiếp. Kiểm tra {v['totals']['equity_states']:,} mốc tài sản."
    failures=read(OUT/'incomplete_paths.json')
    failure_note='Không có đường dừng vì thiếu tài sản đảm bảo trong lượt này; chưa xác minh thanh lý lịch sử trên sàn.'
    if failures:
        halt_times=sorted({f['stop_event']['at'] for f in failures})
        failure_note=f"{len(failures)} đường dừng theo maintenance proxy 1%, tại {len(halt_times)} mốc; các đường không độc lập. Không giả lập số dư cuối hay khớp thanh lý. DD trên100% phản ánh bước Mark lấy mẫu đã vượt qua0, không phải số lỗ thực hiện đã xác minh."
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
    extra="""function capitalRender(){const st=document.querySelector('#strategy').value,w=document.querySelector('#window').value,c=document.querySelector('#cost').value;document.querySelector('#capitalBody').innerHTML=data.filter(r=>r.strategy_id===st&&r.window===w&&(r.cost==='base'||r.cost===c)).map(r=>`<tr><td>${r.cost==='base'?'Cơ sở':'Cao'}</td><td>${r.entries}</td><td>${r.carry_diagnostics.count}</td><td>${r.carry_diagnostics.negative}</td><td>${num(r.carry_diagnostics.total_net)}</td><td>${num(r.carry_diagnostics.worst_net)}</td><td>${num(r.utilization.mean_positions)}</td><td>${num(r.utilization.mean_committed_margin)}</td><td>${num(r.utilization.peak_committed_margin)}</td><td>${r.margin_rejections}</td><td>${num(100*r.utilization.fraction_time_paused)}%</td><td>${num(r.closed_net)}</td><td>${num(r.retained_net)}</td></tr>`).join('');}const chartRender=render;render=function(){chartRender();capitalRender();};"""
    script=script.replace("for(const id of ['strategy','window','cost'])",extra+"for(const id of ['strategy','window','cost'])",1)
    options=''.join(f'<option value="{sp["id"]}"'+(' selected' if sp['id']==focus else '')+'>'+escape(name(sp))+'</option>' for sp in s['specs'])
    periods=''.join(f'<option value="{w}"'+(' selected' if w=='later' else '')+'>'+escape({'development':'09/2025–05/2026 · kỳ chọn','year':'09/2025–08/2026 · cả năm','later':'06–08/2026'}.get(w,'Ba tháng từ '+pd.Timestamp(t[0],unit='ms',tz='UTC').strftime('%m/%Y')))+'</option>' for w,t in s['protocol']['windows'].items())
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Giới hạn funding trong thời gian giữ lệnh</title><style>__STYLE__</style></head><body><main><div class="eyebrow">ĐẢO VÀNG / NGHIÊN CỨU LƯỢT 37</div><h1>Đóng vị thế khi funding âm tích lũy vượt ngân sách?</h1><p class="muted">Cố định ba nguồn ứng viên · thay quy tắc thoát do funding · Long + Short · tài khoản 500 USDT · Cross x5</p><div class="notice"><b>__TARGET__</b><p>__FINDING__</p><p>Biến thể nghiên cứu này CÓ THỂ CHỐT LỖ: đóng toàn bộ vị thế khi funding âm ròng tích lũy vượt ngân sách. Khác cấu hình gốc không tự đóng lỗ. Chỉ mô phỏng, chưa thay cấu hình live. Giữ quy tắc cũ là đối chứng riêng.</p></div>
<section class="panel"><h2>Toàn bộ 12 cấu hình</h2><p>Cặp số chi phí cơ sở / chi phí cao. ★ là lựa chọn theo từng nguồn, khóa trước khi chạy các kỳ sau: cả hai mức chi phí có lời, DD dưới 20%, ít nhất 20 lệnh đóng, đủ dữ liệu; ưu tiên tháng tệ nhất rồi tài sản cuối. Quy mô là tổng danh nghĩa của cả ba phần, không phải mỗi phần.</p><div class="scroll"><table><thead>__HEAD__</thead><tbody>__TABLE__</tbody></table></div></section>
<section class="panel"><h2>Tài sản và các khoản lời/lỗ</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Kỳ<select id="window">__PERIODS__</select></label><label>Chi phí<select id="cost"><option value="stress">Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản gồm vị thế còn mở"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><div class="scroll"><table><thead><tr><th>Chi phí</th><th>Vị thế đã mở</th><th>Thoát do funding</th><th>Trong đó đóng lỗ</th><th>Ròng các lệnh thoát funding</th><th>Lệnh thoát funding tệ nhất</th><th>Vị thế TB</th><th>Vốn giữ chỗ TB</th><th>Vốn giữ chỗ tối đa</th><th>Lần thiếu vốn</th><th>Thời gian khóa mở mới</th><th>Ròng lệnh đóng</th><th>Đóng góp lệnh mở</th></tr></thead><tbody id="capitalBody"></tbody></table></div><p>Vốn giữ chỗ gồm ký quỹ mô phỏng theo Mark, vốn dành cho phần chưa khớp và phí dự kiến; không phải mức lỗ tối đa. Trung bình có trọng số thời gian; nếu đường dừng sớm chỉ tính đoạn quan sát. Lần thiếu vốn tính cả vào mới và vào thêm. Tài sản = 500 + ròng lệnh đóng + đóng góp lệnh mở; các khoản ròng đã gồm phí và funding. Khi DD đạt 20%, khóa mở mới nhưng vẫn giữ vị thế và trailing. Không tự bật lại.</p></section>
<section class="panel"><h2>Thử từ 10 mốc khởi chạy</h2><p>Mỗi kỳ ba tháng có 500 USDT riêng, bắt đầu từ 09/2025 đến 06/2026. Các kỳ chồng lấn, chỉ có bốn quý không chồng lấn. Đây là lịch sử đã nghiên cứu nhiều lần, chưa phải bằng chứng tương lai mới. Kỳ không hoàn tất vẫn ở mẫu số; tài sản tệ nhất chỉ tính kỳ hoàn tất.</p><div class="scroll"><table><thead>__RHEAD__</thead><tbody>__ROLLING__</tbody></table></div></section>
<section class="panel"><h2>Quy tắc vốn và đối soát</h2><p>Cùng tín hiệu Long/Short momentum 7 ngày, chờ hồi thuận giá 0,5 ATR trong giờ thứ 1–23 sau tín hiệu gốc. Giữ ATR14 nến 4 giờ, hướng và độ ưu tiên lúc phát tín hiệu. Mọi mức vốn dùng cùng các ứng viên; không tăng vốn theo lợi nhuận hoặc nhân tuyến tính lợi nhuận cũ. Chỉ so quy tắc thoát với đối chứng cùng nguồn và cùng mức vốn.</p><p>Giữ tổng danh nghĩa 25 hoặc 100 USDT theo nguồn, tương ứng ký quỹ dự kiến 5 hoặc 20 USDT ở x5; tối đa 5 vị thế. Hai nguồn đã được chọn ở lượt trước là nguồn gốc 25 USDT và nguồn hồi 24 giờ có lọc funding đắt ở 100 USDT. Thêm nguồn hồi sâu hơn 2 ATR ở 25 USDT để kiểm tra trường hợp SOON, được ghi rõ là nhóm chẩn đoán chưa được chọn để sử dụng. Mỗi vị thế chia ba phần, chỉ vào thêm thuận giá 0,25 ATR và hết hạn sau 6 giờ. Trailing kích hoạt ở 3 ATR, hồi 1%. Đối chứng giữ như cũ; biến thể đóng khi funding âm ròng tích lũy đạt 0,5%, 1% hoặc 2% danh nghĩa dự kiến cả vị thế. Với 25 USDT, ngưỡng là 0,125 / 0,25 / 0,50 USDT; với 100 USDT là 0,50 / 1 / 2 USDT. Ngưỡng cố định, không đổi theo số phần đã khớp, tài sản hoặc ATR mới. Khoản funding nhận trước đó bù trừ khoản trả; không cộng riêng tất cả các khoản âm.</p><p>Trước khi vào mới, giữ đủ chỗ cho phần hiện tại và hai phần dự kiến, kể cả phần cam kết của vị thế khác. Khi vào thêm, kiểm tra lại phần còn lại. Hết hạn, kích hoạt trailing, sai quy tắc khối lượng, thiếu vốn hoặc dừng mở mới sẽ hủy phần vào tiếp theo quy tắc đã có. Nhật ký quan sát ghi các lần kiểm tra và hủy; sổ vốn được tái dựng độc lập từ lần khớp, funding và sự kiện hủy. Kiểm tra funding mỗi 5 phút, chỉ dùng khoản đã thanh toán ít nhất 60 giây trước đó. Đóng ở giá mở cửa kế tiếp cộng trượt giá bất lợi, trước trailing và trước vào phần tiếp theo. Vẫn kiểm tra thiếu tài sản đảm bảo trước khi thử đóng; không giả định có thể cứu một tài khoản đã chạm ngưỡng này. Ngưỡng funding không giới hạn lỗ do giá; một lần thanh toán có thể vượt ngân sách.</p><p>__AUDIT__</p></section>
<section class="panel"><h2>Giới hạn kết luận</h2><p>Phí/trượt mỗi lần khớp: cơ sở 0,05%/0,20%, cao 0,10%/0,50%. Funding thực, mọi vị thế mở được định giá. Tập 30 coin cố định, bộ lọc sàn hiện tại, maintenance proxy 1% và dữ liệu 5 phút chưa chứng minh thanh lý lịch sử hoặc khả năng khớp thật. Chưa đạt 50% mỗi tháng; chưa bật live.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">Mọi kết quả</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc khóa</a> · <a href="incomplete_paths.json">Đường không hoàn tất</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    diagnostic_panel='<section class="panel"><h2>Đối chiếu sự kiện Short SOON gây lỗ funding</h2><p>Cùng sự kiện đã chẩn đoán ở nhóm hồi sâu 25 USDT. Nếu tài khoản không nhận sự kiện trong một biến thể, không chèn thêm giao dịch giả định. PnL ròng còn tính phí vào và ra; thay đổi điểm đóng có thể thay đổi cả danh mục về sau.</p><div class="scroll"><table><thead>'+tr(['Quy tắc','Chi phí','Trạng thái','Ngày giữ','Lãi/lỗ theo giá','Funding','Ròng sau phí'])+'</thead><tbody id="diagnosticBody">'+''.join(tr(r) for r in diag_rows)+'</tbody></table></div></section>'
    html=html.replace('<section class="panel"><h2>Thử từ 10 mốc khởi chạy</h2>',diagnostic_panel+'<section class="panel"><h2>Thử từ 10 mốc khởi chạy</h2>')
    for key,value in dict(STYLE=style,TARGET=escape(target),FINDING=escape(finding),HEAD=tr(['Cấu hình vốn','Tài sản kỳ chọn','Tài sản 06–08','Tài sản cả năm','Số vị thế cả năm','DD cả năm']),TABLE=''.join(tr(r) for r in tables),OPTIONS=options,PERIODS=periods,RHEAD=tr(['Cấu hình vốn','Kỳ có lời','Tài sản tệ nhất','DD lớn nhất','Quý có lời']),ROLLING=''.join(tr(r) for r in rolling),AUDIT=escape(audit),SCRIPT=script).items():html=html.replace('__'+key+'__',value)
    (OUT/'dashboard.html').write_text(html,encoding='utf-8')
    md=['# Giới hạn funding trong thời gian giữ lệnh','',target,'',finding,'','Cặp số chi phí cơ sở / cao. ★ chọn bằng kỳ đầu; các biến thể giữ nguồn ứng viên, thêm quy tắc thoát vì funding có thể chốt lỗ; không áp dụng live.',
        '|Cấu hình vốn|Kỳ chọn|06–08|Cả năm|Số vị thế|DD cả năm|','|---|---:|---:|---:|---:|---:|',*['| '+' | '.join(r)+' |' for r in tables],'',
        '|Cấu hình vốn|Kỳ có lời|Tệ nhất|DD lớn nhất|Quý có lời|','|---|---:|---:|---:|---:|',*['| '+' | '.join(r)+' |' for r in rolling],'',audit,'',
        'Các cửa sổ chồng lấn và đã được nghiên cứu trước. Tài sản tính cả vị thế chưa đóng. Quy mô25/100 là danh nghĩa toàn bộ3phần, ký quỹ dự kiến5/20ởx5. Biến thể fundingexit có thể đóng lỗ; ngưỡng không giới hạn tổng PnL. Funding chỉ dùng sau60giây, khớp nextopen và vẫn kiểm tra Cross trước. No live changes.',s['protocol']['limitations']]
    (OUT/'report.md').write_text('\n'.join(md),encoding='utf-8');write(OUT/'findings.json',dict(target=target,finding=finding))
    write(OUT/'goal_progress.json',dict(classification='progress',goal_status='active',achieved=False,runs=len(s['results']),target_passes=s['target_met_rows'],evidence=finding,
        next_steps=['Account for total price-plus-carry loss and the capital released by exits; a funding budget alone is not a total-loss cap.','Nextresearch must improve monthlyexpectancy under finitecapital, not optimize around a lucky historicalwindow.'],live_config_unchanged=True))
    assert sha(ROOT/'configs/live.yaml')==s['protocol']['live_config_sha256'];print(OUT/'dashboard.html')


if __name__=='__main__':main()
