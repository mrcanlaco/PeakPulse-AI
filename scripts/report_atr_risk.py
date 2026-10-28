"""Sampled ATR risk-exit results with costs, retained inventory and drawdowns."""
import json
from html import escape
import xml.etree.ElementTree as ET
import pandas as pd
from search_atr_risk import OUT,read,ROOT,sha,write

LABELS={'hold':'Không cắt lỗ','atr1':'Cắt lỗ 1 ATR','atr2':'Cắt lỗ 2 ATR','atr4':'Cắt lỗ 4 ATR','atr8':'Cắt lỗ 8 ATR'}
def name(sp):return f"{sp['notional']} USDT · "+LABELS[sp['exit']]


def main():
    s=read(OUT/'summary.json');v=read(OUT/'verification.json');execution=read(OUT/'stop_execution.json');tests=ET.parse(OUT/'unit_tests.xml').getroot()
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
    focus='momentum_168h_raw_hold_price_n25_atr2'
    rs=[look[(focus,'year',c)] for c in ['base','stress']]
    finding=f"Lựa chọn khóa bằng 09/2025–05/2026: {choice}. Với cắt lỗ tại 2 ATR, quy mô 25 USDT, tài sản cả năm là {fmt(rs[0]['ending_equity'])} / {fmt(rs[1]['ending_equity'])} USDT, tương ứng {rs[0]['entries']} / {rs[1]['entries']} vị thế vào."
    audit=f"{count} kiểm thử đạt; đối soát {v['totals']['journals']} sổ, {v['totals']['baseline_paths_exact']} đối chứng khớp lượt cũ và {v['totals']['replayed_paths_exact']} đường chạy lại khớp. Kiểm tra độc lập {v['totals']['exit_lifecycles']:,} vòng đời thoát, {v['totals']['risk_exits']:,} lần cắt lỗ theo ATR, {v['totals']['funding']:,} khoản funding và {v['totals']['equity_states']:,} mốc tài sản. Các số đếm dùng lặp lịch sử giữa các cấu hình."
    series=[]
    for row in s['results']:
        raw=read(OUT/'runs'/f'{row["id"]}.json');curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet');ix={0,len(curve)-1}
        for _,g in curve.groupby((curve['at']-curve['at'].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        retained=sum(p['unrealized']-p['entry_fee']+p['funding'] for p in raw['open_positions'])
        if raw['ending_equity'] is not None:assert abs(500+raw['closed_trade_net']+retained-raw['ending_equity'])<1e-6
        series.append(dict(row,stop_execution=execution[row['id']],closed_net=raw['closed_trade_net'],retained_net=retained,fees=raw['fees'],points=[[int(p['at']),round(p.equity,6)] for _,p in curve.loc[sorted(ix)].iterrows()]))
    write(OUT/'dashboard_data.json',series)
    old=(ROOT/'artifacts/signal_priority_20260925/dashboard.html').read_text(encoding='utf-8');style=old.split('<style>',1)[1].split('</style>',1)[0];script=old.split('<script>',1)[1].split('</script>',1)[0]
    script='const spans='+json.dumps(s['protocol']['windows'])+script[script.index(',labels='):]
    extra="""function exitsRender(){const st=document.querySelector('#strategy').value,w=document.querySelector('#window').value,c=document.querySelector('#cost').value;document.querySelector('#exitBody').innerHTML=data.filter(r=>r.strategy_id===st&&r.window===w&&(r.cost==='base'||r.cost===c)).map(r=>`<tr><td>${r.cost==='base'?'Cơ sở':'Cao'}</td><td>${r.risk_exits}</td><td>${r.negative_risk_exits}</td><td>${num(r.risk_exit_net)}</td><td>${num(r.closed_net)}</td><td>${num(r.retained_net)}</td><td>${num(r.fees)}</td><td>${num(r.funding)}</td><td>${r.stop_execution.over_distance}</td><td>${num(r.stop_execution.max_gross_ratio)}</td></tr>`).join('');}const chartRender=render;render=function(){chartRender();exitsRender();};"""
    script=script.replace("for(const id of ['strategy','window','cost'])",extra+"for(const id of ['strategy','window','cost'])",1)
    options=''.join(f'<option value="{sp["id"]}"'+(' selected' if sp['id']==focus else '')+'>'+escape(name(sp))+'</option>' for sp in s['specs'])
    periods=''.join(f'<option value="{w}"'+(' selected' if w=='year' else '')+'>'+escape({'development':'09/2025–05/2026 · kỳ chọn','year':'09/2025–08/2026 · cả năm','later':'06–08/2026'}.get(w,'Ba tháng từ '+pd.Timestamp(t[0],unit='ms',tz='UTC').strftime('%m/%Y')))+'</option>' for w,t in s['protocol']['windows'].items())
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Giới hạn lỗ theo ATR</title><style>__STYLE__</style></head><body><main><div class="eyebrow">ĐẢO VÀNG / NGHIÊN CỨU LƯỢT 29</div><h1>Cắt lỗ theo ATR có cải thiện lợi nhuận?</h1><p class="muted">Cùng điểm vào momentum 7 ngày · Long + Short · tài khoản 500 USDT · Cross x5 · tối đa 5 vị thế</p><div class="notice"><b>__TARGET__</b><p>__FINDING__</p><p>Các biến thể mới có thể đóng lệnh lỗ. Đây là thử nghiệm riêng với yêu cầu giữ lệnh không thời hạn ban đầu; chưa thay đổi cấu hình live.</p></div>
<section class="panel"><h2>Toàn bộ 10 cấu hình</h2><p>Cặp số chi phí cơ sở / chi phí cao. ★ là lựa chọn khóa trước khi chạy các kỳ sau: cả hai mức chi phí có lời, DD dưới 20%, ít nhất 20 lệnh đóng, đủ dữ liệu; ưu tiên tháng tệ nhất rồi tài sản cuối. Quy mô là tổng danh nghĩa của cả ba phần, không phải mỗi phần.</p><div class="scroll"><table><thead>__HEAD__</thead><tbody>__TABLE__</tbody></table></div></section>
<section class="panel"><h2>Tài sản và các khoản lời/lỗ</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Kỳ<select id="window">__PERIODS__</select></label><label>Chi phí<select id="cost"><option value="stress">Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản gồm vị thế còn mở"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><div class="scroll"><table><thead><tr><th>Chi phí</th><th>Thoát theo ATR</th><th>Trong đó lỗ</th><th>Ròng nhóm cắt lỗ ATR</th><th>Ròng tất cả lệnh đóng</th><th>Đóng góp lệnh đang mở</th><th>Tổng phí</th><th>Funding</th><th>Số lần vượt khoảng cách</th><th>Lỗ do giá / mức dự kiến lớn nhất</th></tr></thead><tbody id="exitBody"></tbody></table></div><p>Các khoản lời/lỗ là USDT. Cột cuối là tỷ lệ lỗ do giá thực khớp chia cho khối lượng × số ATR × ATR lúc vào, chưa gồm phí/funding; lớn hơn 1 nghĩa là vượt khoảng cách dự kiến. Số lần vượt không tính phí/funding. Tài sản = 500 + ròng lệnh đóng + đóng góp lệnh đang mở. Phí và funding đã nằm trong các khoản ròng, không cộng/trừ lần nữa. Khi DD đạt 20%, mở mới bị khóa vĩnh viễn trong lượt chạy; các quy tắc thoát vẫn quản lý vị thế. Tài sản đi ngang sau đó có thể do bot đã dừng và hết vị thế.</p></section>
<section class="panel"><h2>Thử từ 10 mốc khởi chạy</h2><p>Mỗi kỳ ba tháng có 500 USDT riêng, bắt đầu từ 09/2025 đến 06/2026. Các kỳ chồng lấn, chỉ có bốn quý không chồng lấn. Đây là lịch sử đã nghiên cứu nhiều lần, chưa phải bằng chứng tương lai mới. Kỳ không hoàn tất vẫn ở mẫu số; tài sản tệ nhất chỉ tính kỳ hoàn tất.</p><div class="scroll"><table><thead>__RHEAD__</thead><tbody>__ROLLING__</tbody></table></div></section>
<section class="panel"><h2>Quy tắc cắt lỗ đã khóa</h2><p>ATR14 được tính từ nến 4 giờ đã đóng tại tín hiệu vào, giữ cố định suốt vị thế. Khoảng cách cắt lỗ là 1, 2, 4 hoặc 8 ATR tính từ giá vốn bình quân của lượng đã khớp. Những phần vào thêm thuận giá làm đổi giá vốn bình quân, không tính lại ATR. Long thoát khi Mark thấp hơn giá vốn đủ khoảng cách; Short thoát khi Mark cao hơn đủ khoảng cách.</p><p>Mỗi 5 phút kiểm tra Mark của nến đã đóng, tính funding đến hiện tại trước rồi xét cắt lỗ, trailing và vào thêm. Nếu điều kiện cắt lỗ và trailing cùng xảy ra, ưu tiên cắt lỗ. Khớp tại giá mở nến giao dịch tiếp theo cộng trượt bất lợi, không khớp giả ngay ngưỡng. Đây là kiểm tra giá lấy mẫu, không phải mô phỏng lệnh stop trên sàn hoạt động liên tục; gap có thể làm lỗ vượt khoảng cách dự kiến. Ngưỡng thanh lý mô phỏng vẫn được kiểm tra trước xử lý thoát. Không tự đảo hướng hoặc vào lại cùng coin tại bước vừa thoát.</p><p>Vẫn vào ba phần khi thuận giá, trailing kích hoạt tại 3 ATR và hồi 1%. Vốn 500 USDT, Cross x5; 25 USDT danh nghĩa tương ứng khoảng 5 USDT ký quỹ, 100 USDT là phương án nghiên cứu khoảng 20 USDT ký quỹ. Không tự nạp thêm hoặc bật lại sau khi dừng mở mới.</p><p>__AUDIT__</p></section>
<section class="panel"><h2>Giới hạn kết luận</h2><p>Phí/trượt mỗi lần khớp: cơ sở 0,05%/0,20%, cao 0,10%/0,50%. Funding thực, mọi vị thế mở được định giá. Tập 30 coin cố định, bộ lọc sàn hiện tại, maintenance proxy 1% và dữ liệu 5 phút chưa chứng minh thanh lý lịch sử hoặc khả năng khớp thật. Chưa đạt 50% mỗi tháng; chưa bật live.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">Mọi kết quả</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc khóa</a> · <a href="incomplete_paths.json">Đường không hoàn tất</a> · <a href="stop_execution.json">Chi tiết vượt ngưỡng</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    for key,value in dict(STYLE=style,TARGET=escape(target),FINDING=escape(finding),HEAD=tr(['Cách thoát','Tài sản kỳ chọn','Tài sản 06–08','Tài sản cả năm','Số vị thế cả năm','DD cả năm']),TABLE=''.join(tr(r) for r in tables),OPTIONS=options,PERIODS=periods,RHEAD=tr(['Cách thoát','Kỳ có lời','Tài sản tệ nhất','DD lớn nhất','Quý có lời']),ROLLING=''.join(tr(r) for r in rolling),AUDIT=escape(audit),SCRIPT=script).items():html=html.replace('__'+key+'__',value)
    (OUT/'dashboard.html').write_text(html,encoding='utf-8')
    md=['# Giới hạn lỗ theo ATR','',target,'',finding,'','Cặp số chi phí cơ sở / cao. ★ chọn bằng kỳ đầu; các biến thể mới đóng cả lệnh lỗ.',
        '|Cách thoát|Kỳ chọn|06–08|Cả năm|Số vị thế|DD cả năm|','|---|---:|---:|---:|---:|---:|',*['| '+' | '.join(r)+' |' for r in tables],'',
        '|Cách thoát|Kỳ có lời|Tệ nhất|DD lớn nhất|Quý có lời|','|---|---:|---:|---:|---:|',*['| '+' | '.join(r)+' |' for r in rolling],'',audit,'',
        'Các cửa sổ chồng lấn và đã được nghiên cứu trước. Tài sản tính cả vị thế chưa đóng. Vốn25/100 là danh nghĩa, không phải ký quỹ. Không thay cấu hình live.',s['protocol']['limitations']]
    (OUT/'report.md').write_text('\n'.join(md),encoding='utf-8');write(OUT/'findings.json',dict(target=target,finding=finding))
    write(OUT/'goal_progress.json',dict(classification='progress',goal_status='active',achieved=False,runs=len(s['results']),target_passes=s['target_met_rows'],evidence=finding,
        next_steps=['Compare verified entry expectancy and turnover costs before enlarging risk; ATR stops alone are not proof of50%monthly.','Subsequent research must isolate a distinct entry or sizing hypothesis, retain full MTM and test all monthly-start paths.'],live_config_unchanged=True))
    assert sha(ROOT/'configs/live.yaml')==s['protocol']['live_config_sha256'];print(OUT/'dashboard.html')


if __name__=='__main__':main()
