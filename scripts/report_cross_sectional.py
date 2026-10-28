"""Relative-strength research, separating original size and sizing alternatives."""
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from html import escape
import pandas as pd
from compare_account_risk import ROOT,write,sha
from search_cross_sectional import OUT,read

CONTROL_NAMES={'short_reversal_none_price':'Đối chứng Short đảo chiều',
    'both_reversal_none_net_peak1':'Đối chứng Long+Short đảo chiều / lãi ròng1',
    'both_trend_none_price':'Đối chứng Long+Short theo xu hướng',
    'both_trend_avoid_costly_price':'Đối chứng theo xu hướng / lọc funding'}


def name(sp):
    if sp['baseline']:return CONTROL_NAMES[sp['reference']]
    mode,hours,score=sp['source'].split('_',2)
    text=('Theo xu hướng' if mode=='momentum' else 'Đảo chiều')+' · '+hours+' · '+('Lợi suất' if score=='raw' else 'Điều chỉnh biến động')
    return text+' · '+('Giữ lệnh' if sp['holding']=='hold' else 'Đóng sau168h')+' · '+('Trailing giá' if sp['exit']=='price' else 'Trailing ròng')+f' · {sp["notional"]} USDT'


def main():
    s=read(OUT/'summary.json');v=read(OUT/'verification.json');specs={sp['id']:sp for sp in s['specs']}
    tree=ET.parse(OUT/'unit_tests.xml').getroot();tests=len(tree.findall('.//testcase'));assert not tree.findall('.//failure') and not tree.findall('.//error')
    look={(r['strategy_id'],r['window'],r['cost']):r for r in s['results']};selected={r['strategy_id'] for r in s['selected'] if r['strategy_id']}
    num=lambda x:'Không hoàn tất' if x is None else f'{x:.2f}'
    tr=lambda xs:'<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in xs)+'</tr>'
    rows=[];picked=[];quarters=[];selected_text=[]
    for sp in s['specs']:
        rs=lambda w:[look[(sp['id'],w,c)] for c in ['base','stress']]
        row=[name(sp),*[' / '.join(num(r['ending_equity']) for r in rs(w)) for w in ['development','later','year']],
            ' / '.join(f"{100*r['max_drawdown']:.2f}%" for r in rs('year')),
            ' / '.join(str(r['entries']) for r in rs('year')),
            ' / '.join(str(r['time_exits']) for r in rs('year')),
            ' / '.join(str(r['open_count']) for r in rs('year'))]
        rows.append(row)
        if sp['id'] in selected or sp['scaled'] or sp['baseline']:picked.append(row)
        if sp['id'] in s['quarter_specs']:
            windows=['quarter_0','quarter_3','quarter_6','later']
            quarters.append([name(sp),*[' / '.join(num(r['ending_equity']) for r in rs(w)) for w in windows],
                ' / '.join(str(sum(look[(sp['id'],w,c)]['ending_equity'] is not None and look[(sp['id'],w,c)]['ending_equity']>500 for w in windows))+'/4' for c in ['base','stress'])])
    for choice in s['selected']:
        key=choice['strategy_id'];label=('Theo xu hướng' if choice['mode']=='momentum' else 'Đảo chiều')+' / '+choice['holding']
        if key is None:selected_text.append(label+': không ứng viên đạt điều kiện giai đoạn chọn.');continue
        rs=[look[(key,'later',c)] for c in ['base','stress']]
        selected_text.append(name(specs[key])+': ba tháng06–08 kết thúc '+' / '.join(num(r['ending_equity']) for r in rs)+' USDT.')
    total=len(s['results']);target=f"{s['target_met_rows']}/{total} đường đạt tăng50% trong từng tháng; {s['incomplete_paths']} đường không hoàn tất."
    time_pick=next((r['strategy_id'] for r in s['selected'] if r['mode']=='momentum' and r['holding']=='time168' and r['strategy_id']),None)
    if time_pick:
        hold=time_pick.replace('_time168_','_hold_');a=look[(hold,'year','base')];b=look[(time_pick,'year','base')]
        diagnosis=(f"Cùng bộ tín hiệu {specs[time_pick]['source']}, danh nghĩa25 USDT và trailing giá: thêm thời hạn168h làm số vị thế đã vào cả năm từ {a['entries']} lên {b['entries']}, "
            f"nhưng tài sản cuối kỳ từ {num(a['ending_equity'])} thành {num(b['ending_equity'])} USDT. Có nhiều lệnh hơn không tự tạo lợi thế sau chi phí; các lệnh đóng lỗ theo thời gian vẫn được tính đầy đủ.")
    else:diagnosis='Không có ứng viên theo xu hướng với thời hạn168h đạt điều kiện chọn; không nâng quy mô cho nhóm này.'
    scaled_results=[r for r in s['results'] if r['scaled'] and r['window']=='later']
    scaled_note='; '.join(name(specs[key])+': '+ ' / '.join(num(look[(key,'later',c)]['ending_equity']) for c in ['base','stress'])+' USDT' for key in dict.fromkeys(r['strategy_id'] for r in scaled_results)) or 'Không có ứng viên đủ điều kiện để thử quy mô lớn hơn.'
    contributions=[];contribution_rows=[]
    momentum_hold=next((c['strategy_id'] for c in s['selected'] if c['mode']=='momentum' and c['holding']=='hold' and c['strategy_id']),None)
    if momentum_hold:
        for key in [momentum_hold,momentum_hold.replace('_n25','_n100')]:
            if key not in specs:continue
            for cost in ['base','stress']:
                raw=read(OUT/'runs'/f'year_{cost}_{key}.json');net=defaultdict(float);carry=defaultdict(float)
                for j in raw['journal']:
                    if 'net' in j:net[(j['symbol'],j['side'])]+=j['net']
                    if j['kind']=='funding':carry[(j['symbol'],j['side'])]+=j['amount']
                for pos in raw['open_positions']:net[(pos['symbol'],pos['side'])]+=pos['unrealized']-pos['entry_fee']+pos['funding']
                assert raw['pnl'] is not None and abs(sum(net.values())-raw['pnl'])<1e-6
                groups=[dict(symbol=c,side=side,net=value,funding=carry[(c,side)]) for (c,side),value in sorted(net.items(),key=lambda x:-x[1])]
                contributions.append(dict(strategy_id=key,cost=cost,window='year',pnl=raw['pnl'],groups=groups))
                for g in groups[:3]:contribution_rows.append([str(specs[key]['notional'])+' USDT',cost,g['symbol'],g['side'],num(g['net']),num(g['funding'])])
    write(OUT/'contributions.json',contributions)
    audit=(f"{tests} kiểm thử đạt; {v['totals']['feature_snapshots']:,} ảnh chụp dữ liệu coin/ngày và {v['totals']['rank_cells']:,} ô thứ hạng tính lại độc lập; "
        f"tái tạo {v['totals']['independent_signals']:,} tín hiệu của12bộ, {v['totals']['causal_prefixes']} lần cắt dữ liệu tương lai. "
        f"{v['totals']['journals']} sổ đối soát, {v['totals']['baseline_paths_exact']} đối chứng khớp toàn bộ lượt cũ, {v['totals']['replayed_paths_exact']} đường chạy lại khớp. "
        f"Kiểm tra thứ tự kích hoạt/thoát của {v['totals']['exit_lifecycles']:,} vòng đời tại {v['totals']['exit_observations']:,} thời điểm; "
        f"{v['totals']['time_exits']:,} lần đóng theo thời gian, {v['totals']['fills']:,} lần khớp, {v['totals']['funding']:,} khoản funding, {v['totals']['equity_states']:,} mốc tài sản. Các số đếm chồng lấn giữa cấu hình, không phải mẫu thị trường độc lập.")
    series=[]
    for row in s['results']:
        curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet');ix={0,len(curve)-1}
        for _,g in curve.groupby((curve['at']-curve['at'].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(row,points=[[int(p['at']),round(p.equity,6)] for _,p in curve.loc[sorted(ix)].iterrows()]))
    write(OUT/'dashboard_data.json',series)
    old=(ROOT/'artifacts/signal_priority_20260925/dashboard.html').read_text(encoding='utf-8');style=old.split('<style>',1)[1].split('</style>',1)[0];script=old.split('<script>',1)[1].split('</script>',1)[0]
    script='const spans='+json.dumps(dict(s['protocol']['windows'],**s['protocol']['quarters']))+script[script.index(',labels='):]
    script=script.replace('const values=rows.flatMap',"if(!rows.length){document.querySelector('#chart').innerHTML='';document.querySelector('#chartStatus').textContent='Quý này chỉ kiểm tra ứng viên đã khóa và các đối chứng. Chọn kỳ cả năm hoặc06–08 để xem cấu hình này.';document.querySelector('#monthHead').innerHTML='';document.querySelector('#monthBody').innerHTML='';return;}const values=rows.flatMap")
    default=time_pick or next(iter(selected),'control_short_reversal_none_price')
    options=''.join(f'<option value="{sp["id"]}"'+(' selected' if sp['id']==default else '')+'>'+escape(name(sp))+'</option>' for sp in s['specs'])
    periods=''.join(f'<option value="{key}"'+(' selected' if key=='later' else '')+'>'+label+'</option>' for key,label in [('development','Chọn:09/2025–05/2026'),('later','06–08/2026'),('year','Cả năm09/2025–08/2026'),('quarter_0','09–11/2025'),('quarter_3','12/2025–02/2026'),('quarter_6','03–05/2026')])
    header='<tr>'+''.join('<th>'+h+'</th>' for h in ['Cấu hình / danh nghĩa mỗi vị thế','Tài sản kỳ chọn','Tài sản06–08','Tài sản cả năm','DD cả năm','Vị thế đã vào','Đóng theo thời gian','Còn mở'])+'</tr>'
    qheader='<tr>'+''.join('<th>'+h+'</th>' for h in ['Cấu hình','09–11/2025','12/2025–02/2026','03–05/2026','06–08/2026','Quý có lời'])+'</tr>'
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Sức mạnh tương đối Long Short</title><style>__STYLE__</style></head><body><main><div class="eyebrow">ĐẢO VÀNG / XẾP HẠNG TƯƠNG ĐỐI · LƯỢT25</div><h1>Long và Short theo sức mạnh tương đối</h1><p class="muted">500 USDT chung · Cross x5 · tối đa5 vị thế · mỗi coin một vị thế · cùng30 coin · tín hiệu mới mỗi ngày</p><div class="notice"><b>__TARGET__</b><p>__DIAGNOSIS__</p></div>
<div class="cards"><div class="card">Bộ tín hiệu mới<strong>12</strong></div><div class="card">Cấu hình mới25 USDT<strong>48</strong></div><div class="card">Đối chứng cũ<strong>4</strong></div><div class="card">Đường chạy / kiểm thử<strong>__RUNS__ / __TESTS__</strong></div></div>
<section class="panel"><h2>Ứng viên đã khóa trước giai đoạn tháng6–8</h2><p>Chọn một ứng viên cho mỗi hướng tiếp cận và cách giữ lệnh, chỉ bằng09/2025–05/2026: cả hai mức chi phí có lời, DD&lt;20%, ít nhất20 vị thế đóng, đường đầy đủ. Ưu tiên tháng tệ nhất rồi tài sản cuối. Không đổi lựa chọn sau khi xem kỳ sau. Cặp số: cơ sở / chi phí cao.</p><ul>__PICKS__</ul><div class="scroll"><table><thead>__HEADER__</thead><tbody>__PICKED__</tbody></table></div></section>
<section class="panel"><h2>Quy mô100 USDT là phép thử riêng</h2><p>Các ứng viên đã chọn được thử tổng danh nghĩa100 USDT/vị thế, khoảng20 USDT ký quỹ ởx5; tài khoản vẫn500 USDT. Đây khác với mức25 danh nghĩa/5 ký quỹ ban đầu. Lệnh, bộ lọc sàn, khối lượng, phí, funding và lỗ mở đều tính lại. Nếu dùng trailing ròng thì ngưỡng kích hoạt tăng từ1 lên4 USDT, không lấy PnL ở mức nhỏ nhân bốn. Kết quả quy mô lớn không được dùng để chọn lại tín hiệu.</p><p>__SCALED__</p></section>
<section class="panel"><h2>Tài sản và lợi suất từng tháng</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Kỳ<select id="window">__PERIODS__</select></label><label>Chi phí<select id="cost"><option value="stress">Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản gồm các vị thế còn mở"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div></section>
<section class="panel"><h2>Bốn quý không chồng lấn</h2><p>Mỗi quý bắt đầu riêng500 USDT. Ba quý đầu nằm trong giai đoạn chọn nên không phải dữ liệu kiểm định mới. Bảng gồm ứng viên25/100 USDT đã khóa và bốn đối chứng; có lời cả quý vẫn có thể có tháng âm.</p><div class="scroll"><table><thead>__QHEADER__</thead><tbody>__QUARTERS__</tbody></table></div></section>
<section class="panel"><h2>Lợi nhuận theo coin của ứng viên theo xu hướng giữ lệnh</h2><p>Ba đóng góp lớn nhất cho từng mức danh nghĩa và chi phí trong cả năm, tính cả vị thế mở. Funding là một thành phần đã nằm trong lãi/lỗ ròng, không cộng thêm lần nữa. Đây chỉ là phân rã kết quả, không loại coin hay chọn lại chiến lược theo lợi nhuận đã thấy.</p><div class="scroll"><table><thead><tr><th>Danh nghĩa</th><th>Chi phí</th><th>Coin</th><th>Hướng</th><th>Đóng góp ròng USDT</th><th>Funding USDT</th></tr></thead><tbody>__CONTRIBUTIONS__</tbody></table></div><p><a href="contributions.json">Xem mọi đóng góp dương và âm</a></p></section>
<section class="panel"><h2>Mọi cấu hình, bao gồm trường hợp thua lỗ</h2><div class="scroll"><table><thead>__HEADER__</thead><tbody>__ALL__</tbody></table></div></section>
<section class="panel"><h2>Cách chọn coin và thoát lệnh</h2><p>Mỗi00:00UTC, tính lợi suất log trong24/72/168 giờ từ nến đóng. So sánh xếp hạng lợi suất thuần với lợi suất chia cho độ lệch chuẩn lợi suất giờ×căn bậc hai số giờ. Cần dữ liệu liên tục, ATR14 trên nến4h, khối lượng24h ít nhất2 triệu USDT và ít nhất24/30 coin đủ điều kiện.</p><p>Nhóm20% mạnh nhất phải có lợi suất dương; nhóm20% yếu nhất phải âm. Theo xu hướng: Long nhóm mạnh, Short nhóm yếu. Đảo chiều: đảo hai hướng. Các coin đồng điểm dùng thứ hạng trung bình; điểm ưu tiên là độ lệch khỏi giữa bảng xếp hạng, không phải xác suất thắng. Không xếp hạng lại để thay coin bị từ chối vì quy tắc sàn. Hai hướng dùng chung vốn và chỗ, không đảm bảo cân bằng hay trung hòa thị trường.</p><p>Mỗi vị thế vào ba phần khi giá thuận0,25ATR, hết hạn thêm sau6h. So sánh trailing giá3ATR/1% với trailing lãi ròng1 USDT/giảm25% từ đỉnh, chỉ phát lệnh khi ước tính ròng không âm. Lệnh khớp tại mở nến sau với trượt bất lợi nên vẫn có thể lỗ.</p><p><b>“Đóng sau168h” là biến thể khác yêu cầu không tự đóng lỗ:</b> hết tuổi lệnh thì thoát bằng giá thị trường, kể cả đang lỗ hoặc tài khoản đã dừng mở mới. Đóng theo tuổi có ưu tiên trước trailing. Tín hiệu cùng coin ngay tại bước vừa đóng vẫn bị bỏ qua. Biến thể “giữ lệnh” tiếp tục giữ lỗ, không stop-loss. Mọi vị thế chưa đóng đều được định giá cuối kỳ, không giả vờ đã thoát.</p><p>__AUDIT__</p></section>
<section class="panel"><h2>Giới hạn và tài khoản thật</h2><p>Mục tiêu50% mỗi tháng chưa đạt. Đây là lịch sử đã dùng nhiều lần, tập coin cố định có thể thiên lệch; dùng bộ lọc sàn hiện tại, maintenance proxy1%, giả định phí/trượt và quan sát5 phút, thiếu bậc ký quỹ và sổ lệnh lịch sử. Phí/trượt cơ sở0,05%/0,20%; cao0,10%/0,50% mỗi lần khớp. Kết quả thiếu không được coi là tài khoản sống sót. Chưa bật live và không sửa cấu hình tài khoản thật.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">Toàn bộ kết quả</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc khóa</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    for key,val in dict(STYLE=style,TARGET=escape(target),DIAGNOSIS=escape(diagnosis),RUNS=str(total),TESTS=str(tests),PICKS=''.join('<li>'+escape(x)+'</li>' for x in selected_text),
        HEADER=header,PICKED=''.join(tr(r) for r in picked),SCALED=escape(scaled_note),OPTIONS=options,PERIODS=periods,QHEADER=qheader,QUARTERS=''.join(tr(r) for r in quarters),ALL=''.join(tr(r) for r in rows),AUDIT=escape(audit),SCRIPT=script,CONTRIBUTIONS=''.join(tr(r) for r in contribution_rows)).items():html=html.replace('__'+key+'__',val)
    for a,b in [('tối đa5','tối đa 5'),('cùng30','cùng 30'),('mới25','mới 25'),('tháng6','tháng 6'),('bằng09','bằng 09'),('nhất20','nhất 20'),('Quy mô100','Quy mô 100'),('nghĩa100','nghĩa 100'),('khoảng20','khoảng 20'),('ởx5','ở x5'),('vẫn500','vẫn 500'),('mức25','mức 25'),('từ1 lên4','từ 1 lên 4'),('riêng500','riêng 500'),('Mỗi00','Mỗi 00'),('trong24','trong 24'),('nhất2','nhất 2'),('nhất24','nhất 24'),('Nhóm20','Nhóm 20'),('nhóm20','nhóm 20'),('sau168','sau 168'),('sau6h','sau 6h'),('thuận0','thuận 0'),('giá3ATR','giá 3 ATR'),('ròng1','ròng 1'),('giảm25','giảm 25'),('tiêu50','tiêu 50'),('proxy1','proxy 1'),('sát5','sát 5'),('sở0','sở 0'),('cao0','cao 0')]:html=html.replace(a,b)
    (OUT/'dashboard.html').write_text(html,encoding='utf-8')
    md=['# Long/Short theo sức mạnh tương đối','',target,'',diagnosis,'',*selected_text,'',
        '## Quy mô100USDT: nghiên cứu ngoài cấu hình ban đầu','',scaled_note,'',
        'Cặp số cơ sở / chi phí cao. Cùng500USDT; có đóng sau168h là biến thể cho phép chốt lỗ theo thời gian.',
        '| Cấu hình |Kỳ chọn|06–08|Cả năm|DD năm|Vào|Đóng theo tuổi|Mở|','|---|---:|---:|---:|---:|---:|---:|---:|',
        *['| '+' | '.join(r)+' |' for r in rows],'',audit,'',s['protocol']['limitations'],'',
        'Chưa đạt mục tiêu50%từngtháng, chưa bật live.','[Dashboard](dashboard.html) · [Quy tắc](protocol.json) · [Đối soát](verification.json)']
    (OUT/'report.md').write_text('\n'.join(md),encoding='utf-8')
    write(OUT/'findings.json',dict(target=target,diagnosis=diagnosis,selected_later=selected_text,scaled_later=scaled_note))
    write(OUT/'goal_progress.json',dict(classification='progress',goal_status='active',achieved=False,runs=total,target_passes=s['target_met_rows'],
        evidence=diagnosis,selected_later=selected_text,scaled_later=scaled_note,next_steps=['Diagnose shared-wallet side exposure and regime dependence of frozen cross-sectional candidates before increasing the parameter search.',
        'Preserve50%netMTM eachmonth criterion and require fresh locked forward evidence before any live decision.'],live_config_unchanged=True))
    assert sha(ROOT/'configs/live.yaml')==s['protocol']['live_config_sha256']
    print(OUT/'dashboard.html')


if __name__=='__main__':main()
