"""Offline comparison dashboard for entry-only signed commitment limits."""
import json
from html import escape
import xml.etree.ElementTree as ET
import pandas as pd
from search_cross_exposure import OUT,read,ROOT,sha,write


def name(sp):
    family='Momentum 7 ngày · giữ lệnh' if sp['holding']=='hold' else 'Momentum 3 ngày · đóng sau 168h'
    gate={'none':'Không giới hạn lệch','net1':'Lệch ≤1 vị thế','net2':'Lệch ≤2 vị thế'}[sp['gate']]
    return f'{family} · {sp["notional"]} USDT · {gate}'


def main():
    s=read(OUT/'summary.json');v=read(OUT/'verification.json');profiles=read(OUT/'exposure_profiles.json')
    tests=ET.parse(OUT/'unit_tests.xml').getroot();assert not tests.findall('.//failure') and not tests.findall('.//error')
    count=len(tests.findall('.//testcase'));specs={sp['id']:sp for sp in s['specs']}
    robust={(r['strategy_id'],r['cost']):r for r in s['robustness']};lookup={(r['strategy_id'],r['window'],r['cost']):r for r in s['results']}
    num=lambda x:'Không hoàn tất' if x is None else f'{x:.2f}'
    tr=lambda xs:'<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in xs)+'</tr>'
    selected={x['strategy_id'] for x in s['selected'] if x['strategy_id']};table=[];rolling=[]
    for sp in s['specs']:
        cells=[name(sp)+(' ★' if sp['id'] in selected else '')]
        for window in ['development','later','year']:cells.append(' / '.join(num(lookup[(sp['id'],window,c)]['ending_equity']) for c in ['base','stress']))
        cells.append(' / '.join(f"{100*lookup[(sp['id'],'year',c)]['max_drawdown']:.2f}%" for c in ['base','stress']))
        table.append(cells)
        rs=[robust[(sp['id'],c)] for c in ['base','stress']]
        rolling.append([name(sp),' / '.join(str(r['profitable'])+'/10' for r in rs),' / '.join(num(r['worst_ending']) for r in rs),
            ' / '.join(f"{100*r['worst_drawdown']:.2f}%" for r in rs),' / '.join(str(r['nonoverlapping_profitable'])+'/4' for r in rs)])
    target=f"{s['target_met_rows']}/{len(s['results'])} đường đạt tăng ít nhất 50% trong từng tháng; {s['incomplete_paths']} đường không hoàn tất."
    focus='momentum_168h_raw_hold_price_n25_net1'
    picked=[lookup[(focus,'later',c)] for c in ['base','stress']];rr=[robust[(focus,c)] for c in ['base','stress']]
    finding=f"Momentum 7 ngày, 25 USDT danh nghĩa, giới hạn lệch một vị thế được chọn bằng kỳ 09/2025–05/2026. Khi khởi chạy riêng tháng 06–08: {num(picked[0]['ending_equity'])} / {num(picked[1]['ending_equity'])} USDT. Có lời ở {rr[0]['profitable']}/10 và {rr[1]['profitable']}/10 mốc bắt đầu; cửa sổ tệ nhất {num(rr[0]['worst_ending'])} / {num(rr[1]['worst_ending'])} USDT."
    raw=read(OUT/'runs'/f'later_base_{focus}.json')
    retained=sum(p['unrealized']-p['entry_fee']+p['funding'] for p in raw['open_positions'])
    assert abs(500+raw['closed_trade_net']+retained-raw['ending_equity'])<1e-7
    finding+=f" Với chi phí cơ sở, lệnh đã đóng lời ròng {num(raw['closed_trade_net'])}, nhưng {len(raw['open_positions'])} vị thế còn mở đóng góp {num(retained)} USDT sau funding/phí vào. Cân bằng danh nghĩa lúc vào chưa giải quyết việc giữ các vị thế thua."
    audit=f"{count} kiểm thử đạt; {v['totals']['journals']} sổ đối soát, {v['totals']['baseline_paths_exact']} đối chứng khớp chính xác lượt trước, {v['totals']['replayed_paths_exact']} đường chạy lại khớp. Tái dựng độc lập {v['totals']['exposure_decisions']:,} quyết định kiểm soát lệch, {v['totals']['fills']:,} lần khớp, {v['totals']['funding']:,} khoản funding và {v['totals']['equity_states']:,} mốc tài sản. Các số đếm dùng lặp lịch sử giữa cấu hình."
    series=[]
    for row in s['results']:
        curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet');ix={0,len(curve)-1}
        for _,g in curve.groupby((curve['at']-curve['at'].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(row,exposure_profile=profiles[row['id']],points=[[int(p['at']),round(p.equity,6)] for _,p in curve.loc[sorted(ix)].iterrows()]))
    write(OUT/'dashboard_data.json',series)
    old=(ROOT/'artifacts/signal_priority_20260925/dashboard.html').read_text(encoding='utf-8');style=old.split('<style>',1)[1].split('</style>',1)[0];script=old.split('<script>',1)[1].split('</script>',1)[0]
    script='const spans='+json.dumps(s['protocol']['windows'])+script[script.index(',labels='):]
    marker="for(const id of ['strategy','window','cost'])"
    extra="""function exposureRender(){const st=document.querySelector('#strategy').value,w=document.querySelector('#window').value,c=document.querySelector('#cost').value;document.querySelector('#exposureBody').innerHTML=data.filter(r=>r.strategy_id===st&&r.window===w&&(r.cost==='base'||r.cost===c)).map(r=>{const p=r.exposure_profile;return `<tr><td>${r.cost==='base'?'Cơ sở':'Cao'}</td><td>${r.side_entries.LONG||0} L / ${r.side_entries.SHORT||0} S</td><td>${num(p.mean_long)}</td><td>${num(p.mean_short)}</td><td>${num(p.mean_abs_net)}</td><td>${num(p.peak_abs_net)}</td><td>${p.fraction_above_entry_bound===null?'—':num(100*p.fraction_above_entry_bound)+'%'}</td><td>${r.exposure_rejected}</td></tr>`}).join('');}const originalRender=render;render=function(){originalRender();exposureRender();};"""
    script=script.replace(marker,extra+marker,1)
    options=''.join(f'<option value="{sp["id"]}"'+(' selected' if sp['id']==focus else '')+'>'+escape(name(sp))+'</option>' for sp in s['specs'])
    periods=''.join(f'<option value="{w}"'+(' selected' if w=='later' else '')+'>'+escape({'development':'09/2025–05/2026 · kỳ chọn','year':'09/2025–08/2026 · cả năm','later':'06–08/2026'}.get(w,'Ba tháng từ '+pd.Timestamp(t[0],unit='ms',tz='UTC').strftime('%m/%Y')))+'</option>' for w,t in s['protocol']['windows'].items())
    head=tr(['Cấu hình · ★ lựa chọn đã khóa','Tài sản kỳ chọn','Tài sản 06–08','Tài sản cả năm','DD cả năm'])
    rhead=tr(['Cấu hình','Mốc có lời','Tài sản tệ nhất','DD lớn nhất','Quý không chồng lấn có lời'])
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Kiểm soát lệch Long Short</title><style>__STYLE__</style></head><body><main><div class="eyebrow">ĐẢO VÀNG / NGHIÊN CỨU LƯỢT 27</div><h1>Giảm lệch Long/Short có cải thiện lợi nhuận?</h1><p class="muted">500 USDT · Cross x5 · 3 phần vào thuận giá · tối đa 5 vị thế · 25/100 USDT danh nghĩa mỗi vị thế</p><div class="notice"><b>__TARGET__</b><p>__FINDING__</p></div>
<section class="panel"><h2>So sánh toàn bộ 12 cấu hình</h2><p>Số cơ sở / chi phí cao. Tất cả cùng tín hiệu nguồn đã khóa; chỉ thay điều kiện nhận lệnh. Chọn theo kỳ đầu: cả hai mức chi phí có lời, DD dưới 20%, ít nhất 20 vị thế đóng, đủ dữ liệu; ưu tiên tháng tệ nhất rồi tài sản cuối. Các cửa sổ sau không được dùng để chọn lại.</p><div class="scroll"><table><thead>__HEAD__</thead><tbody>__TABLE__</tbody></table></div></section>
<section class="panel"><h2>Tài sản gồm các lệnh đang mở</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Kỳ<select id="window">__PERIODS__</select></label><label>Chi phí<select id="cost"><option value="stress">Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản theo thị trường"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><div class="scroll"><table><thead><tr><th>Chi phí</th><th>Lệnh vào</th><th>Long TB USDT</th><th>Short TB USDT</th><th>|Long−Short| TB</th><th>Lệch tối đa</th><th>Thời gian vượt ngưỡng vào</th><th>Tín hiệu bị chặn vì lệch</th></tr></thead><tbody id="exposureBody"></tbody></table></div><p>Danh nghĩa thực theo Mark, trung bình có trọng số thời gian, không gồm phần chưa khớp. Đây là chênh lệch số đô la, không đo beta hoặc chứng minh trung hòa rủi ro. Ngưỡng chỉ kiểm tra lúc mở vị thế: giá, lần vào tiếp hoặc lệnh thoát có thể làm danh mục vượt ngưỡng sau đó.</p></section>
<section class="panel"><h2>Khởi chạy độc lập từ 10 mốc</h2><p>Mỗi cửa sổ ba tháng bắt đầu với 500 USDT, từ 09/2025 đến 06/2026. Cửa sổ chồng lấn; chỉ có bốn quý không chồng lấn. Toàn bộ lịch sử đã từng được nghiên cứu, không phải tập tương lai mới. Tài sản tệ nhất chỉ tính đường hoàn tất; đường không hoàn tất vẫn giữ trong mẫu số 10.</p><div class="scroll"><table><thead>__RHEAD__</thead><tbody>__ROLLING__</tbody></table></div></section>
<section class="panel"><h2>Quy tắc và phạm vi</h2><p>Trước khi xét lệnh mới, tính danh nghĩa Long và Short bằng lượng đã khớp × Mark đã đóng cộng phần danh nghĩa dành cho những lần vào tiếp còn hiệu lực. Cộng toàn bộ ngân sách vị thế ứng viên vào hướng tương ứng. Chấp nhận nếu độ lệch dự kiến không quá một hoặc hai ngân sách vị thế, hoặc nếu lệnh giúp giảm tuyệt đối độ lệch hiện có. Qua bước này vẫn phải đạt điều kiện khối lượng, TP và vốn. Không tạo lệnh đối ứng nhân tạo, đổi thứ tự tín hiệu hay thử lại tín hiệu bị bỏ.</p><p>Vào ba phần khi thuận giá, trailing kích hoạt tại 3 ATR và hồi 1%. Giữ lệnh là phương án không đóng lỗ theo thời gian; phương án 168h đóng cả lệnh lỗ và được ghi riêng. Dừng mở mới ở DD 20% giữ các vị thế và không tự bật lại. Quy mô 25 USDT tương ứng khoảng 5 USDT ký quỹ; 100 USDT là thử nghiệm khoảng 20 USDT ký quỹ.</p><p>__AUDIT__</p><p>Phí/trượt mỗi lần khớp: cơ sở 0,05%/0,20%; chi phí cao 0,10%/0,50%. Funding thực và định giá mọi lệnh đang mở. Tập 30 coin cố định, bộ lọc sàn hiện tại, maintenance proxy 1% và nến 5 phút chưa chứng minh thanh lý Cross lịch sử hoặc khả năng khớp thực. Chưa đạt mục tiêu 50% từng tháng, chưa bật live.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">Mọi kết quả</a> · <a href="protocol.json">Quy tắc đã khóa</a> · <a href="verification.json">Đối soát</a> · <a href="exposure_profiles.json">Danh nghĩa theo hướng</a> · <a href="failure_verification.json">Đường không hoàn tất</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    for key,value in dict(STYLE=style,TARGET=escape(target),FINDING=escape(finding),HEAD=head,TABLE=''.join(tr(r) for r in table),OPTIONS=options,PERIODS=periods,RHEAD=rhead,ROLLING=''.join(tr(r) for r in rolling),AUDIT=escape(audit),SCRIPT=script).items():html=html.replace('__'+key+'__',value)
    (OUT/'dashboard.html').write_text(html,encoding='utf-8')
    md=['# Kiểm soát lệch Long/Short','',target,'',finding,'','Cặp số cơ sở / chi phí cao. ★ = chọn bằng kỳ đầu; không chọn lại bằng kết quả sau.',
        '|Cấu hình|Kỳ chọn|06–08|Cả năm|DD cả năm|','|---|---:|---:|---:|---:|',*['| '+' | '.join(r)+' |' for r in table],'',
        '|Cấu hình|Mốc có lời|Tệ nhất|DD lớn nhất|Quý có lời|','|---|---:|---:|---:|---:|',*['| '+' | '.join(r)+' |' for r in rolling],'',audit,'',
        'Ngưỡng chỉ áp dụng lúc vào, không tự tái cân bằng. Danh nghĩa cân bằng không đồng nghĩa trung hòa beta. 100 USDT và đóng sau168h là phương án nghiên cứu. Dữ liệu đã nghiên cứu, tập coin cố định, bộ lọc hiện tại và maintenance proxy1%; chưa đủ kết luận giao dịch thật.','',s['protocol']['target'],'',s['protocol']['limitations']]
    (OUT/'report.md').write_text('\n'.join(md),encoding='utf-8')
    write(OUT/'findings.json',dict(target=target,finding=finding))
    write(OUT/'goal_progress.json',dict(classification='progress',goal_status='active',achieved=False,runs=len(s['results']),target_passes=s['target_met_rows'],evidence=finding,
        next_steps=['Investigate entry-only exposure controls versus lifecycle-aware exits using frozen signals; preserve costs and all losing inventory.','Do not promote positive window totals or overlapping samples as50%eachmonth.'],live_config_unchanged=True))
    assert sha(ROOT/'configs/live.yaml')==s['protocol']['live_config_sha256'];print(OUT/'dashboard.html')


if __name__=='__main__':main()
