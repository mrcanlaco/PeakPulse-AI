"""Frozen retracement applied to matched cross-sectional source families."""
import json
from html import escape
import xml.etree.ElementTree as ET
import pandas as pd
from search_cross_pullback import OUT,read,ROOT,sha,write

LABELS={'immediate':'Vào ngay','pull05':'Chờ hồi 0,5 ATR'}
def name(sp):
    mode,hours,score=sp['source'].split('_',2)
    horizon={'24h':'1 ngày','72h':'3 ngày','168h':'7 ngày'}[hours]
    return ('Theo xu hướng' if mode=='momentum' else 'Đảo chiều')+' · '+horizon+' · '+('Lợi suất' if score=='raw' else 'Điều chỉnh biến động')+' · '+LABELS[sp['timing']]


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
    paired=read(OUT/'paired_effect.json');paired_map={(r['source'],r['cost']):r for r in paired};pair_rows=[]
    for source in sorted({sp['source'] for sp in s['specs']}):
        rs=[paired_map[(source,c)] for c in ['base','stress']]
        title=name(next(sp for sp in s['specs'] if sp['source']==source and sp['timing']=='pull05'))
        pair_rows.append([title,' / '.join(str(r['improved'])+'/10' for r in rs),' / '.join(str(r['worsened'])+'/10' for r in rs),
            ' / '.join(fmt(r['median_difference']) for r in rs),' / '.join(fmt(r['worst_difference']) for r in rs)])
    target=f"{s['target_met_rows']}/{len(s['results'])} đường đạt ít nhất 50% trong từng tháng; {s['incomplete_paths']} đường không hoàn tất."
    choice='; '.join(name(specs[k]) for k in sorted(selected)) or 'Không có cấu hình đạt tiêu chí chọn'
    focus=next((x['strategy_id'] for x in s['selected'] if x['reference']=='momentum' and x['strategy_id']),'momentum_168h_raw_hold_price_n25_pull05')
    rs=[look[(focus,'later',c)] for c in ['base','stress']]
    finding=f"Lựa chọn khóa bằng 09/2025–05/2026: {choice}. {name(specs[focus])}, khởi chạy riêng 06–08 từ 500 USDT: tài sản cuối {fmt(rs[0]['ending_equity'])} / {fmt(rs[1]['ending_equity'])} USDT; {rs[0]['entries']} / {rs[1]['entries']} vị thế vào. Cần đối chiếu các tháng âm và nhiều mốc khởi chạy, không suy ra hiệu quả chỉ từ một quý có lời."
    rr=[robust[(focus,c)] for c in ['base','stress']]
    finding+=f" Trên 10 mốc ba tháng, có lời ở {rr[0]['profitable']}/10 và {rr[1]['profitable']}/10; tài sản tệ nhất {fmt(rr[0]['worst_ending'])} / {fmt(rr[1]['worst_ending'])} USDT. Các cửa sổ chồng lấn và đã được nghiên cứu, không phải 10 mẫu tương lai độc lập."
    families=[]
    for mode,label in [('momentum','Theo xu hướng'),('reversion','Đảo chiều')]:
        cases=[r for r in s['results'] if r['mode']==mode and r['timing']=='pull05' and r['window']=='year']
        assert len(cases)==12
        profitable=sum(r['ending_equity'] is not None and r['ending_equity']>500 for r in cases)
        families.append(f'{label}: {profitable}/12 trường hợp cả năm có lời (6 nguồn × 2 mức chi phí)')
    finding+=' '+'; '.join(families)+'. Có lời cả năm không có nghĩa là mọi tháng có lời.'
    audit=f"{count} kiểm thử đạt; {v['totals']['independent_signal_sets']} bộ tín hiệu đối chiếu độc lập và {v['totals']['causal_prefixes']} kiểm tra cắt dữ liệu tương lai. Đối soát {v['totals']['journals']} sổ, {v['totals']['baseline_paths_exact']} đối chứng khớp lượt cũ, {v['totals']['replayed_paths_exact']} đường chạy lại khớp; kiểm tra {v['totals']['executed_candidates']:,} lần nhận tín hiệu vào và {v['totals']['equity_states']:,} mốc tài sản. Các số đếm dùng lặp lịch sử giữa các cấu hình."
    series=[]
    for row in s['results']:
        raw=read(OUT/'runs'/f'{row["id"]}.json');curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet');ix={0,len(curve)-1}
        for _,g in curve.groupby((curve['at']-curve['at'].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        retained=sum(p['unrealized']-p['entry_fee']+p['funding'] for p in raw['open_positions'])
        if raw['ending_equity'] is not None:assert abs(500+raw['closed_trade_net']+retained-raw['ending_equity'])<1e-6
        candidates={e['event_id']:e for e in signals[specs[row['strategy_id']]['source']+'_'+specs[row['strategy_id']]['timing']]}
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
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Chờ hồi trên nhiều nhóm tín hiệu</title><style>__STYLE__</style></head><body><main><div class="eyebrow">ĐẢO VÀNG / NGHIÊN CỨU LƯỢT 31</div><h1>Chờ hồi có hiệu quả với những nhóm tín hiệu nào?</h1><p class="muted">12 nhóm tín hiệu theo xu hướng và đảo chiều · Long + Short · tài khoản 500 USDT · Cross x5 · tối đa 5 vị thế</p><div class="notice"><b>__TARGET__</b><p>__FINDING__</p><p>Giữ nguyên trailing và không cắt lỗ; chỉ thay điều kiện chờ trước khi vào. Chưa thay đổi cấu hình live.</p></div>
<section class="panel"><h2>Toàn bộ 24 cấu hình</h2><p>Cặp số chi phí cơ sở / chi phí cao. ★ là lựa chọn khóa trước khi chạy các kỳ sau: cả hai mức chi phí có lời, DD dưới 20%, ít nhất 20 lệnh đóng, đủ dữ liệu; ưu tiên tháng tệ nhất rồi tài sản cuối. Quy mô là tổng danh nghĩa của cả ba phần, không phải mỗi phần.</p><div class="scroll"><table><thead>__HEAD__</thead><tbody>__TABLE__</tbody></table></div></section>
<section class="panel"><h2>Tài sản và các khoản lời/lỗ</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Kỳ<select id="window">__PERIODS__</select></label><label>Chi phí<select id="cost"><option value="stress">Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản gồm vị thế còn mở"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><div class="scroll"><table><thead><tr><th>Chi phí</th><th>Tín hiệu đủ điều kiện</th><th>Vị thế được mở</th><th>Chờ TB (giờ)</th><th>Hồi TB lúc kích hoạt (ATR)</th><th>Ròng tất cả lệnh đóng</th><th>Đóng góp lệnh đang mở</th><th>Tổng phí</th><th>Funding</th></tr></thead><tbody id="timingBody"></tbody></table></div><p>Thời gian chờ và mức hồi trung bình chỉ tính tín hiệu thực sự được nhận vào. Mức hồi dương là thuận giá so với nến tín hiệu gốc, âm là phải đuổi theo giá; đây chưa phải giá khớp. Các khoản lời/lỗ tính bằng USDT. Tài sản = 500 + ròng lệnh đóng + đóng góp lệnh đang mở. Phí và funding đã nằm trong các khoản ròng, không cộng/trừ lần nữa. Khi DD đạt 20%, mở mới bị khóa vĩnh viễn trong lượt chạy; trailing vẫn quản lý vị thế. Tài sản đi ngang sau đó có thể do bot đã dừng và hết vị thế.</p></section>
<section class="panel"><h2>Thử từ 10 mốc khởi chạy</h2><p>Mỗi kỳ ba tháng có 500 USDT riêng, bắt đầu từ 09/2025 đến 06/2026. Các kỳ chồng lấn, chỉ có bốn quý không chồng lấn. Đây là lịch sử đã nghiên cứu nhiều lần, chưa phải bằng chứng tương lai mới. Kỳ không hoàn tất vẫn ở mẫu số; tài sản tệ nhất chỉ tính kỳ hoàn tất.</p><div class="scroll"><table><thead>__RHEAD__</thead><tbody>__ROLLING__</tbody></table></div></section>
<section class="panel"><h2>So từng cặp chờ hồi và vào ngay</h2><p>Chênh lệch = tài sản khi chờ hồi trừ tài sản khi vào ngay, cùng nguồn tín hiệu và mốc khởi chạy. Số dương là cải thiện; không đồng nghĩa tài khoản có lời. Cặp số cơ sở / chi phí cao. Cả hai cách vẫn phải qua giới hạn vị thế nên tập lệnh thực nhận có thể khác nhau; đây không chỉ là tác động của giá khớp tốt hơn. Các cửa sổ chồng lấn.</p><div class="scroll"><table><thead>__PAIRHEAD__</thead><tbody>__PAIRS__</tbody></table></div></section><section class="panel"><h2>Quy tắc tín hiệu và điểm vào</h2><p>Tín hiệu nguồn giữ nguyên từ lượt kiểm định trước: lợi suất 24, 72 hoặc 168 giờ, xếp hạng trực tiếp hoặc chia theo biến động. Theo xu hướng mua nhóm mạnh, bán nhóm yếu; đảo chiều làm ngược lại. Bộ chọn dùng nến đã đóng, cùng tập coin và điều kiện dữ liệu như đối chứng. Lượt này không thêm hay tối ưu lại các ngưỡng nguồn.</p><p>Hai cách vào: vào ngay, hoặc chờ giá đóng nến 1 giờ sau tốt hơn giá gốc ít nhất 0,5 ATR — thấp hơn cho Long, cao hơn cho Short. ATR14 nến 4 giờ, hướng, mã tín hiệu và độ ưu tiên đều giữ tại thời điểm gốc. Xét giờ thứ 1 đến 23, lần đạt đầu tiên; hết hạn trước tín hiệu ngày tiếp theo. Không xếp hạng lại hoặc thử lại sau khi bị bộ thực thi từ chối. Tín hiệu đang chờ là ứng viên có điều kiện, không phải lệnh đã gửi hoặc vốn đã cam kết.</p><p>Khi kích hoạt vẫn phải qua kiểm tra vốn, số vị thế và quy tắc sàn. Thiếu dữ liệu cần thiết làm bước chuẩn bị không đạt điều kiện. Khớp trong mô phỏng tại giá mở nến 5 phút tiếp theo cộng trượt bất lợi, không giả định khớp tại mức giá hồi mục tiêu.</p><p>Vẫn vào ba phần khi thuận giá, trailing kích hoạt tại 3 ATR và hồi 1%. Vốn 500 USDT, Cross x5; 25 USDT danh nghĩa tương ứng khoảng 5 USDT ký quỹ, lượt này giữ quy mô 25 USDT cho mọi cấu hình. Không tự nạp thêm hoặc bật lại sau khi dừng mở mới.</p><p>__AUDIT__</p></section>
<section class="panel"><h2>Giới hạn kết luận</h2><p>Phí/trượt mỗi lần khớp: cơ sở 0,05%/0,20%, cao 0,10%/0,50%. Funding thực, mọi vị thế mở được định giá. Tập 30 coin cố định, bộ lọc sàn hiện tại, maintenance proxy 1% và dữ liệu 5 phút chưa chứng minh thanh lý lịch sử hoặc khả năng khớp thật. Chưa đạt 50% mỗi tháng; chưa bật live.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">Mọi kết quả</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc khóa</a> · <a href="incomplete_paths.json">Đường không hoàn tất</a> · <a href="paired_effect.json">Đối chiếu từng cặp</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    for key,value in dict(STYLE=style,TARGET=escape(target),FINDING=escape(finding),HEAD=tr(['Điểm vào','Tài sản kỳ chọn','Tài sản 06–08','Tài sản cả năm','Số vị thế cả năm','DD cả năm']),TABLE=''.join(tr(r) for r in tables),OPTIONS=options,PERIODS=periods,RHEAD=tr(['Điểm vào','Kỳ có lời','Tài sản tệ nhất','DD lớn nhất','Quý có lời']),ROLLING=''.join(tr(r) for r in rolling),AUDIT=escape(audit),SCRIPT=script,PAIRHEAD=tr(['Nguồn tín hiệu','Cải thiện','Xấu đi','Chênh lệch trung vị USDT','Chênh lệch tệ nhất USDT']),PAIRS=''.join(tr(r) for r in pair_rows)).items():html=html.replace('__'+key+'__',value)
    (OUT/'dashboard.html').write_text(html,encoding='utf-8')
    md=['# Chờ hồi trên nhiều nhóm tín hiệu','',target,'',finding,'','Cặp số chi phí cơ sở / cao. ★ chọn bằng kỳ đầu; các biến thể chỉ thay điểm vào, giữ nguyên cách thoát.',
        '|Điểm vào|Kỳ chọn|06–08|Cả năm|Số vị thế|DD cả năm|','|---|---:|---:|---:|---:|---:|',*['| '+' | '.join(r)+' |' for r in tables],'',
        '|Điểm vào|Kỳ có lời|Tệ nhất|DD lớn nhất|Quý có lời|','|---|---:|---:|---:|---:|',*['| '+' | '.join(r)+' |' for r in rolling],'','|Nguồn tín hiệu|Cải thiện|Xấu đi|Trung vị chênh lệch|Tệ nhất|','|---|---:|---:|---:|---:|',*['| '+' | '.join(r)+' |' for r in pair_rows],'',audit,'',
        'Các cửa sổ chồng lấn và đã được nghiên cứu trước. Tài sản tính cả vị thế chưa đóng. Quy mô 25 USDT là danh nghĩa, tương ứng khoảng 5 USDT ký quỹ. No live changes.',s['protocol']['limitations']]
    (OUT/'report.md').write_text('\n'.join(md),encoding='utf-8');write(OUT/'findings.json',dict(target=target,finding=finding))
    write(OUT/'goal_progress.json',dict(classification='progress',goal_status='active',achieved=False,runs=len(s['results']),target_passes=s['target_met_rows'],evidence=finding,
        next_steps=['Use matched-source comparisons to isolate mechanism-specific entry improvement before changing sizing/exits.','Evaluate shortlistedfrozenrules with source-complementarity/capacity and eventually independentforwarddata; quarterprofit doesnotmeet50%eachmonth.'],live_config_unchanged=True))
    assert sha(ROOT/'configs/live.yaml')==s['protocol']['live_config_sha256'];print(OUT/'dashboard.html')


if __name__=='__main__':main()
