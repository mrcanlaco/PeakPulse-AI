"""Closed-hour momentum entry timing, actual admitted trades and retained losses."""
import json
from html import escape
import xml.etree.ElementTree as ET
import pandas as pd
from search_momentum_timing import OUT,read,ROOT,sha,write

LABELS={'immediate':'Vào ngay','pull05':'Chờ hồi 0,5 ATR','pull1':'Chờ hồi 1 ATR','retest05':'Hồi 0,5 ATR rồi xác nhận','retest1':'Hồi 1 ATR rồi xác nhận','break05':'Phá tiếp 0,5 ATR','break1':'Phá tiếp 1 ATR'}
def name(sp):return f"{sp['notional']} USDT · "+LABELS[sp['timing']]


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
    focus='momentum_168h_raw_hold_price_n25_pull05'
    rs=[look[(focus,'later',c)] for c in ['base','stress']]
    finding=f"Lựa chọn khóa bằng 09/2025–05/2026: {choice}. Chờ hồi 0,5 ATR với quy mô 25 USDT, khởi chạy riêng 06–08 từ 500 USDT: tài sản cuối {fmt(rs[0]['ending_equity'])} / {fmt(rs[1]['ending_equity'])} USDT; {rs[0]['entries']} / {rs[1]['entries']} vị thế vào. Cần đối chiếu các tháng âm và nhiều mốc khởi chạy, không suy ra hiệu quả chỉ từ một quý có lời."
    rr=[robust[(focus,c)] for c in ['base','stress']]
    finding+=f" Trên 10 mốc ba tháng, có lời ở {rr[0]['profitable']}/10 và {rr[1]['profitable']}/10; tài sản tệ nhất {fmt(rr[0]['worst_ending'])} / {fmt(rr[1]['worst_ending'])} USDT. Các cửa sổ chồng lấn và đã được nghiên cứu, không phải 10 mẫu tương lai độc lập."
    audit=f"{count} kiểm thử đạt; {v['totals']['independent_signal_sets']} bộ tín hiệu đối chiếu độc lập và {v['totals']['causal_prefixes']} kiểm tra cắt dữ liệu tương lai. Đối soát {v['totals']['journals']} sổ, {v['totals']['baseline_paths_exact']} đối chứng khớp lượt cũ, {v['totals']['replayed_paths_exact']} đường chạy lại khớp; kiểm tra {v['totals']['executed_candidates']:,} lần nhận tín hiệu vào và {v['totals']['equity_states']:,} mốc tài sản. Các số đếm dùng lặp lịch sử giữa các cấu hình."
    series=[]
    for row in s['results']:
        raw=read(OUT/'runs'/f'{row["id"]}.json');curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet');ix={0,len(curve)-1}
        for _,g in curve.groupby((curve['at']-curve['at'].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        retained=sum(p['unrealized']-p['entry_fee']+p['funding'] for p in raw['open_positions'])
        if raw['ending_equity'] is not None:assert abs(500+raw['closed_trade_net']+retained-raw['ending_equity'])<1e-6
        candidates={e['event_id']:e for e in signals[specs[row['strategy_id']]['timing']]}
        admitted=[candidates[j['event_id']] for j in raw['journal'] if j['kind']=='entry']
        waits=[(e['at']-e.get('source_at',e['at']))/3600000 for e in admitted]
        improvements=[(1 if e['side']=='LONG' else -1)*(e.get('reference_close',0)-e.get('trigger_close',0))/e['atr'] for e in admitted]
        series.append(dict(row,mean_wait_hours=sum(waits)/len(waits) if waits else None,mean_favorable_atr=sum(improvements)/len(improvements) if improvements else None,
            closed_net=raw['closed_trade_net'],retained_net=retained,fees=raw['fees'],points=[[int(p['at']),round(p.equity,6)] for _,p in curve.loc[sorted(ix)].iterrows()]))
    write(OUT/'dashboard_data.json',series)
    old=(ROOT/'artifacts/signal_priority_20260925/dashboard.html').read_text(encoding='utf-8');style=old.split('<style>',1)[1].split('</style>',1)[0];script=old.split('<script>',1)[1].split('</script>',1)[0]
    script='const spans='+json.dumps(s['protocol']['windows'])+script[script.index(',labels='):]
    extra="""function timingRender(){const st=document.querySelector('#strategy').value,w=document.querySelector('#window').value,c=document.querySelector('#cost').value;document.querySelector('#timingBody').innerHTML=data.filter(r=>r.strategy_id===st&&r.window===w&&(r.cost==='base'||r.cost===c)).map(r=>`<tr><td>${r.cost==='base'?'Cơ sở':'Cao'}</td><td>${r.candidates}</td><td>${r.entries}</td><td>${num(r.mean_wait_hours)}</td><td>${num(r.mean_favorable_atr)}</td><td>${num(r.closed_net)}</td><td>${num(r.retained_net)}</td><td>${num(r.fees)}</td><td>${num(r.funding)}</td></tr>`).join('');}const chartRender=render;render=function(){chartRender();timingRender();};"""
    script=script.replace("for(const id of ['strategy','window','cost'])",extra+"for(const id of ['strategy','window','cost'])",1)
    options=''.join(f'<option value="{sp["id"]}"'+(' selected' if sp['id']==focus else '')+'>'+escape(name(sp))+'</option>' for sp in s['specs'])
    periods=''.join(f'<option value="{w}"'+(' selected' if w=='later' else '')+'>'+escape({'development':'09/2025–05/2026 · kỳ chọn','year':'09/2025–08/2026 · cả năm','later':'06–08/2026'}.get(w,'Ba tháng từ '+pd.Timestamp(t[0],unit='ms',tz='UTC').strftime('%m/%Y')))+'</option>' for w,t in s['protocol']['windows'].items())
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Chờ điểm vào thuận lợi</title><style>__STYLE__</style></head><body><main><div class="eyebrow">ĐẢO VÀNG / NGHIÊN CỨU LƯỢT 30</div><h1>Chờ giá hồi hay chờ phá tiếp?</h1><p class="muted">Cùng tín hiệu gốc momentum 7 ngày · Long + Short · tài khoản 500 USDT · Cross x5 · tối đa 5 vị thế</p><div class="notice"><b>__TARGET__</b><p>__FINDING__</p><p>Giữ nguyên trailing và không cắt lỗ; chỉ thay điều kiện chờ trước khi vào. Chưa thay đổi cấu hình live.</p></div>
<section class="panel"><h2>Toàn bộ 14 cấu hình</h2><p>Cặp số chi phí cơ sở / chi phí cao. ★ là lựa chọn khóa trước khi chạy các kỳ sau: cả hai mức chi phí có lời, DD dưới 20%, ít nhất 20 lệnh đóng, đủ dữ liệu; ưu tiên tháng tệ nhất rồi tài sản cuối. Quy mô là tổng danh nghĩa của cả ba phần, không phải mỗi phần.</p><div class="scroll"><table><thead>__HEAD__</thead><tbody>__TABLE__</tbody></table></div></section>
<section class="panel"><h2>Tài sản và các khoản lời/lỗ</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Kỳ<select id="window">__PERIODS__</select></label><label>Chi phí<select id="cost"><option value="stress">Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản gồm vị thế còn mở"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><div class="scroll"><table><thead><tr><th>Chi phí</th><th>Tín hiệu đủ điều kiện</th><th>Vị thế được mở</th><th>Chờ TB (giờ)</th><th>Hồi TB lúc kích hoạt (ATR)</th><th>Ròng tất cả lệnh đóng</th><th>Đóng góp lệnh đang mở</th><th>Tổng phí</th><th>Funding</th></tr></thead><tbody id="timingBody"></tbody></table></div><p>Thời gian chờ và mức hồi trung bình chỉ tính tín hiệu thực sự được nhận vào. Mức hồi dương là thuận giá so với nến tín hiệu gốc, âm là phải đuổi theo giá; đây chưa phải giá khớp. Các khoản lời/lỗ tính bằng USDT. Tài sản = 500 + ròng lệnh đóng + đóng góp lệnh đang mở. Phí và funding đã nằm trong các khoản ròng, không cộng/trừ lần nữa. Khi DD đạt 20%, mở mới bị khóa vĩnh viễn trong lượt chạy; trailing vẫn quản lý vị thế. Tài sản đi ngang sau đó có thể do bot đã dừng và hết vị thế.</p></section>
<section class="panel"><h2>Thử từ 10 mốc khởi chạy</h2><p>Mỗi kỳ ba tháng có 500 USDT riêng, bắt đầu từ 09/2025 đến 06/2026. Các kỳ chồng lấn, chỉ có bốn quý không chồng lấn. Đây là lịch sử đã nghiên cứu nhiều lần, chưa phải bằng chứng tương lai mới. Kỳ không hoàn tất vẫn ở mẫu số; tài sản tệ nhất chỉ tính kỳ hoàn tất.</p><div class="scroll"><table><thead>__RHEAD__</thead><tbody>__ROLLING__</tbody></table></div></section>
<section class="panel"><h2>Quy tắc điểm vào đã khóa</h2><p>Giữ tín hiệu Long/Short, ATR14 nến 4 giờ, độ ưu tiên và giá đóng nến 1 giờ tại thời điểm gốc. Vào ngay là đối chứng. Chờ hồi yêu cầu giá đóng nến giờ sau tốt hơn giá gốc ít nhất 0,5 hoặc 1 ATR: thấp hơn cho Long, cao hơn cho Short. Xác nhận lại yêu cầu đã hồi đủ, sau đó một nến giờ khác phục hồi thuận xu hướng ít nhất 0,25 ATR từ mức bất lợi xa nhất, đồng thời giá vẫn không tệ hơn giá gốc. Chờ phá tiếp yêu cầu giá đóng đi thêm thuận xu hướng 0,5 hoặc 1 ATR.</p><p>Chỉ xét giờ thứ 1 đến 23, lần đạt đầu tiên; hết hạn trước tín hiệu ngày tiếp theo. Không cập nhật ATR, xếp hạng lại hoặc thử lại sau khi bị bộ thực thi từ chối. Tín hiệu đang chờ là ứng viên có điều kiện, không phải lệnh đang treo hay vốn đã cam kết. Khi kích hoạt vẫn phải đạt kiểm tra vốn, số vị thế và quy tắc sàn. Thiếu dữ liệu cần thiết làm bước chuẩn bị không đạt điều kiện. Khớp thật trong mô phỏng tại giá mở nến 5 phút tiếp theo với trượt giá bất lợi, không giả định khớp tại mức hồi mục tiêu.</p><p>Vẫn vào ba phần khi thuận giá, trailing kích hoạt tại 3 ATR và hồi 1%. Vốn 500 USDT, Cross x5; 25 USDT danh nghĩa tương ứng khoảng 5 USDT ký quỹ, 100 USDT là phương án nghiên cứu khoảng 20 USDT ký quỹ. Không tự nạp thêm hoặc bật lại sau khi dừng mở mới.</p><p>__AUDIT__</p></section>
<section class="panel"><h2>Giới hạn kết luận</h2><p>Phí/trượt mỗi lần khớp: cơ sở 0,05%/0,20%, cao 0,10%/0,50%. Funding thực, mọi vị thế mở được định giá. Tập 30 coin cố định, bộ lọc sàn hiện tại, maintenance proxy 1% và dữ liệu 5 phút chưa chứng minh thanh lý lịch sử hoặc khả năng khớp thật. Chưa đạt 50% mỗi tháng; chưa bật live.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">Mọi kết quả</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc khóa</a> · <a href="incomplete_paths.json">Đường không hoàn tất</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    for key,value in dict(STYLE=style,TARGET=escape(target),FINDING=escape(finding),HEAD=tr(['Điểm vào','Tài sản kỳ chọn','Tài sản 06–08','Tài sản cả năm','Số vị thế cả năm','DD cả năm']),TABLE=''.join(tr(r) for r in tables),OPTIONS=options,PERIODS=periods,RHEAD=tr(['Điểm vào','Kỳ có lời','Tài sản tệ nhất','DD lớn nhất','Quý có lời']),ROLLING=''.join(tr(r) for r in rolling),AUDIT=escape(audit),SCRIPT=script).items():html=html.replace('__'+key+'__',value)
    (OUT/'dashboard.html').write_text(html,encoding='utf-8')
    md=['# Chờ điểm vào thuận lợi','',target,'',finding,'','Cặp số chi phí cơ sở / cao. ★ chọn bằng kỳ đầu; các biến thể chỉ thay điểm vào, giữ nguyên cách thoát.',
        '|Điểm vào|Kỳ chọn|06–08|Cả năm|Số vị thế|DD cả năm|','|---|---:|---:|---:|---:|---:|',*['| '+' | '.join(r)+' |' for r in tables],'',
        '|Điểm vào|Kỳ có lời|Tệ nhất|DD lớn nhất|Quý có lời|','|---|---:|---:|---:|---:|',*['| '+' | '.join(r)+' |' for r in rolling],'',audit,'',
        'Các cửa sổ chồng lấn và đã được nghiên cứu trước. Tài sản tính cả vị thế chưa đóng. Vốn25/100 là danh nghĩa, không phải ký quỹ. No live changes.',s['protocol']['limitations']]
    (OUT/'report.md').write_text('\n'.join(md),encoding='utf-8');write(OUT/'findings.json',dict(target=target,finding=finding))
    write(OUT/'goal_progress.json',dict(classification='progress',goal_status='active',achieved=False,runs=len(s['results']),target_passes=s['target_met_rows'],evidence=finding,
        next_steps=['Test the frozen0.5ATR retracement rule across other pre-existing cross-sectional source horizons/scores, with matched immediate controls and predeclared development selection; do not select a newwinner from June-August alone.','Retain finiteaccount/cost/MTM and monthly-start checks; favorable quarter totals do not meet50%eachmonth or constitute fresh forward evidence.'],live_config_unchanged=True))
    assert sha(ROOT/'configs/live.yaml')==s['protocol']['live_config_sha256'];print(OUT/'dashboard.html')


if __name__=='__main__':main()
