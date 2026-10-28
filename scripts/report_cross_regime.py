"""Entry-regime gates, side occupancy and all monthly-start outcomes."""
import json
import xml.etree.ElementTree as ET
from html import escape
import pandas as pd
from compare_account_risk import ROOT,write,sha
from search_cross_regime import OUT,read

GATES=dict(none='Không lọc',btc_week='BTC7 ngày',btc_trend='Xu hướng BTC4h',breadth60='Độ rộng60%',consensus='BTC + độ rộng')


def name(sp):
    mode,hours,score=sp['source'].split('_',2)
    return ('Theo xu hướng' if mode=='momentum' else 'Đảo chiều')+' · '+hours+' · '+('Lợi suất' if score=='raw' else 'Điều chỉnh biến động')+' · '+('Giữ lệnh' if sp['holding']=='hold' else 'Đóng sau168h')+f' · {sp["notional"]} USDT · '+GATES[sp['gate']]


def main():
    s=read(OUT/'summary.json');v=read(OUT/'verification.json');specs={sp['id']:sp for sp in s['specs']}
    failure_audit=read(OUT/'failure_verification.json');assert failure_audit['checked_paths']==s['incomplete_paths']
    tree=ET.parse(OUT/'unit_tests.xml').getroot();tests=len(tree.findall('.//testcase'));assert not tree.findall('.//failure') and not tree.findall('.//error')
    look={(r['strategy_id'],r['window'],r['cost']):r for r in s['results']};selected={c['strategy_id'] for c in s['selected'] if c['strategy_id']}
    robust={(r['strategy_id'],r['cost']):r for r in s['robustness']}
    num=lambda x:'Không hoàn tất' if x is None else f'{x:.2f}'
    tr=lambda xs:'<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in xs)+'</tr>'
    rows=[];picked=[];starts=[]
    for sp in s['specs']:
        rs=lambda w:[look[(sp['id'],w,c)] for c in ['base','stress']]
        row=[name(sp),*[' / '.join(num(r['ending_equity']) for r in rs(w)) for w in ['development','later','year']],
            ' / '.join(f"{r['max_drawdown']*100:.2f}%" for r in rs('year')),
            ' / '.join(f"{r['side_entries'].get('LONG',0)}L + {r['side_entries'].get('SHORT',0)}S" for r in rs('year'))]
        rows.append(row)
        if sp['id'] in selected or sp['baseline']:picked.append(row)
        if sp['id'] in s['rolling_specs']:
            robs=[robust[(sp['id'],c)] for c in ['base','stress']]
            starts.append([name(sp),' / '.join(str(r['profitable'])+'/10' for r in robs),
                ' / '.join(num(r['worst_ending']) for r in robs),' / '.join(num(r['best_ending']) for r in robs),
                ' / '.join(f"{100*r['worst_drawdown']:.2f}%" for r in robs),
                ' / '.join(str(r['nonoverlapping_profitable'])+'/4' for r in robs)])
    selected_gate_counts={gate:sum(specs[key]['gate']==gate for key in selected) for gate in GATES}
    finding=(f"Có {len(selected)}/{len(s['selected'])} cấu hình tham chiếu đạt điều kiện chọn; trong số này {selected_gate_counts['none']} giữ nguyên không lọc. "
        "Bộ lọc chỉ thay điều kiện vào, không đóng vị thế khi thị trường đổi chiều. Lợi nhuận của cả năm vẫn cần kiểm tra lại từ nhiều mốc bắt đầu.")
    total=len(s['results']);target=f"{s['target_met_rows']}/{total} đường đạt tăng50% trong từng tháng; {s['incomplete_paths']} đường không hoàn tất."
    failures=[]
    for row in s['results']:
        if row['ending_equity'] is None:
            raw=read(OUT/'runs'/f'{row["id"]}.json')
            failures.append(dict(id=row['id'],errors=raw['errors'],stop_event=raw['stop_event']))
    write(OUT/'incomplete_paths.json',failures)
    dates=sorted({pd.Timestamp(f['stop_event']['at'],unit='ms',tz='UTC').strftime('%d/%m/%Y') for f in failures if f['stop_event']})
    failure_note=(f"{len(failures)} đường dừng khi vi phạm ngưỡng maintenance mô phỏng, cùng đợt biến động SOON ngày "+', '.join(dates)+
        f". Các cấu hình/cửa sổ dùng lặp một đoạn lịch sử, không phải {len(failures)} sự cố độc lập. Không suy diễn số dư thanh lý thực tế từ ngưỡng proxy 1%. DD vượt 100% ở bước cuối phản ánh Mark mô phỏng nhảy qua mức tài sản 0 trước khi dừng, không phải tài khoản thật đã thực hiện mức lỗ đó.") if failures else 'Không có đường bị dừng sớm.'
    focus='momentum_168h_raw_hold_price_n100_none';r=[robust[(focus,c)] for c in ['base','stress']]
    diagnosis=(f"Theo xu hướng7 ngày,100 USDT danh nghĩa, không lọc: có lời ở {r[0]['profitable']}/10 cửa sổ ba tháng với chi phí cơ sở "
        f"và {r[1]['profitable']}/10 với chi phí cao. Tài sản cửa sổ tệ nhất {num(r[0]['worst_ending'])} / {num(r[1]['worst_ending'])} USDT; "
        f"drawdown lớn nhất {100*r[0]['worst_drawdown']:.2f}% / {100*r[1]['worst_drawdown']:.2f}%. Mỗi cửa sổ khởi chạy riêng500 USDT; các cửa sổ chồng lấn, không phải10 mẫu độc lập.")
    audit=(f"{tests} kiểm thử đạt; tính lại EMA và độ rộng tại {v['totals']['market_states']} thời điểm, kiểm tra {v['totals']['feature_snapshots']:,} trạng thái coin/ngày; "
        f"{v['totals']['independent_signal_sets']} bộ tín hiệu đối chiếu độc lập, {v['totals']['causal_prefixes']} phép cắt dữ liệu tương lai. "
        f"{v['totals']['journals']} sổ giao dịch đối soát; {v['totals']['baseline_paths_exact']} đối chứng khớp lượt cũ; {v['totals']['replayed_paths_exact']} đường chạy lại khớp. "
        f"Kiểm tra {v['totals']['exit_lifecycles']:,} vòng đời/{v['totals']['exit_observations']:,} thời điểm thoát, {v['totals']['fills']:,} lần khớp, "
        f"{v['totals']['funding']:,} khoản funding và {v['totals']['equity_states']:,} mốc tài sản. Số đếm chồng lấn giữa các cấu hình.")
    series=[]
    for row in s['results']:
        curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet');ix={0,len(curve)-1}
        for _,g in curve.groupby((curve['at']-curve['at'].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(row,points=[[int(p['at']),round(p.equity,6)] for _,p in curve.loc[sorted(ix)].iterrows()]))
    write(OUT/'dashboard_data.json',series)
    old=(ROOT/'artifacts/signal_priority_20260925/dashboard.html').read_text(encoding='utf-8');style=old.split('<style>',1)[1].split('</style>',1)[0];script=old.split('<script>',1)[1].split('</script>',1)[0]
    script='const spans='+json.dumps(s['protocol']['windows'])+script[script.index(',labels='):]
    script=script.replace('const values=rows.flatMap',"if(!rows.length){document.querySelector('#chart').innerHTML='';document.querySelector('#chartStatus').textContent='Cửa sổ bổ sung chỉ chạy lựa chọn đã khóa và đối chứng; chọn cả năm hoặc06–08 để xem cấu hình này.';document.querySelector('#monthHead').innerHTML='';document.querySelector('#monthBody').innerHTML='';return;}const values=rows.flatMap")
    marker="for(const id of ['strategy','window','cost'])"
    extra="""function sideExposure(){const st=document.querySelector('#strategy').value,w=document.querySelector('#window').value,c=document.querySelector('#cost').value;const rows=data.filter(r=>r.strategy_id===st&&r.window===w&&(r.cost==='base'||r.cost===c));document.querySelector('#sideBody').innerHTML=rows.flatMap(r=>['LONG','SHORT'].map(side=>{const x=r.side_metrics.sides[side];return `<tr><td>${r.cost==='base'?'Cơ sở':'Cao'}</td><td>${side}</td><td>${x.entries}</td><td>${num(x.mean_positions)}</td><td>${num(x.total_contribution)}</td><td>${num(100*r.side_metrics.fraction_time_both_sides)}%</td></tr>`})).join('');}const chartRender=render;render=function(){chartRender();sideExposure();};"""
    script=script.replace(marker,extra+marker,1)
    options=''.join(f'<option value="{sp["id"]}"'+(' selected' if sp['id']==focus else '')+'>'+escape(name(sp))+'</option>' for sp in s['specs'])
    periods=''.join(f'<option value="{w}"'+(' selected' if w=='later' else '')+'>'+escape({'development':'Chọn09/2025–05/2026','year':'Cả năm09/2025–08/2026','later':'06–08/2026'}.get(w,'Ba tháng từ '+pd.Timestamp(t[0],unit='ms',tz='UTC').strftime('%m/%Y')))+'</option>' for w,t in s['protocol']['windows'].items())
    head='<tr>'+''.join('<th>'+x+'</th>' for x in ['Cấu hình','Tài sản kỳ chọn','Tài sản06–08','Tài sản cả năm','DD cả năm','Số lệnh theo hướng'])+'</tr>'
    rolling_head='<tr>'+''.join('<th>'+x+'</th>' for x in ['Cấu hình','Cửa sổ có lời','Tài sản tệ nhất','Tài sản tốt nhất','DD lớn nhất','Quý không chồng lấn có lời'])+'</tr>'
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Bộ lọc thị trường Long Short</title><style>__STYLE__</style></head><body><main><div class="eyebrow">ĐẢO VÀNG / ĐIỀU KIỆN THỊ TRƯỜNG · LƯỢT26</div><h1>Bộ lọc thị trường có cải thiện điểm vào không?</h1><p class="muted">500 USDT chung · Cross x5 · cùng tín hiệu đã khóa · 25/100 USDT danh nghĩa mỗi vị thế</p><div class="notice"><b>__TARGET__</b><p>__FINDING__</p><p>__DIAGNOSIS__</p></div>
<div class="cards"><div class="card">Cấu hình tham chiếu<strong>6</strong></div><div class="card">Bộ lọc kể cả đối chứng<strong>5</strong></div><div class="card">Cấu hình / đường chạy<strong>30 / __RUNS__</strong></div><div class="card">Kiểm thử đạt<strong>__TESTS__</strong></div></div>
<section class="panel"><h2>Lựa chọn khóa bằng giai đoạn đầu</h2><p>Chọn riêng cho từng cấu hình tham chiếu bằng09/2025–05/2026: cả hai mức chi phí có lời, DD&lt;20%, ít nhất20 vị thế đóng và đầy đủ dữ liệu; ưu tiên tháng tệ nhất rồi tài sản cuối. Không chọn lại bằng các cửa sổ sau. Cặp số cơ sở / chi phí cao. Bảng gồm các lựa chọn và đối chứng không lọc.</p><div class="scroll"><table><thead>__HEAD__</thead><tbody>__PICKED__</tbody></table></div></section>
<section class="panel"><h2>Tài sản, tháng lời/lỗ và vị thế theo hướng</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Kỳ<select id="window">__PERIODS__</select></label><label>Chi phí<select id="cost"><option value="stress">Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản gồm vị thế còn mở"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><div class="scroll"><table><thead><tr><th>Chi phí</th><th>Hướng</th><th>Lệnh vào</th><th>Vị thế trung bình theo thời gian</th><th>Đóng góp ròng USDT</th><th>Thời gian đồng thời giữ hai hướng</th></tr></thead><tbody id="sideBody"></tbody></table></div><p>Đóng góp ròng gồm lệnh đã đóng và vị thế đang mở sau chi phí/funding. Giữ đồng thời hai hướng không đồng nghĩa trung hòa rủi ro; số vị thế không đo được mức cân bằng danh nghĩa hay beta.</p></section>
<section class="panel"><h2>Khởi chạy từ10 mốc khác nhau</h2><p>Cửa sổ ba tháng bắt đầu mỗi tháng từ09/2025 đến06/2026, mỗi cửa sổ500 USDT. Có bốn quý không chồng lấn, nhưng ba quý đầu đã nằm trong giai đoạn chọn; toàn bộ vẫn là lịch sử đã nghiên cứu. Tài sản tệ nhất/tốt nhất chỉ tính đường hoàn tất; cửa sổ bị dừng vẫn giữ trong mẫu số10.</p><div class="scroll"><table><thead>__RHEAD__</thead><tbody>__STARTS__</tbody></table></div><p>__FAILURES__ <a href="incomplete_paths.json">Xem mọi đường bị dừng</a>.</p></section>
<section class="panel"><h2>Toàn bộ30 cấu hình</h2><div class="scroll"><table><thead>__HEAD__</thead><tbody>__ROWS__</tbody></table></div></section>
<section class="panel"><h2>Thay đổi đúng một điều kiện vào lệnh</h2><p>Không lọc giữ nguyên mọi tín hiệu. BTC7 ngày cho Long khi lợi suất BTC7 ngày dương và Short khi âm. Xu hướng BTC4h yêu cầu EMA20&gt;EMA60, giá đóng&gt;EMA20 và lợi suất24h dương cho Long; đảo cả ba bất đẳng thức cho Short. Độ rộng60% yêu cầu ít nhất60% coin đủ điều kiện ở trên EMA60 nến4h cho Long, ở dưới cho Short. Bộ lọc kết hợp cần cả xu hướng BTC lẫn độ rộng cùng đồng thuận. Các giá bằng nhau không được tính vào hướng tăng/giảm.</p><p>Tất cả dùng dữ liệu đã đóng tại00:00UTC, tối thiểu24 coin đủ điều kiện khi xét độ rộng. Giữ nguyên thời điểm, ATR, coin, hướng, thứ tự ưu tiên và mã tín hiệu. Không đổi hướng hoặc đóng vị thế khi bộ lọc đổi trạng thái; không thử lại tín hiệu đã bỏ qua.</p><p>Cấu hình25 USDT danh nghĩa tương ứng khoảng5 USDT ký quỹ ởx5;100 USDT là phương án nghiên cứu khoảng20 USDT ký quỹ. Cả hai cùng tài khoản500 và tối đa5 vị thế. Vẫn vào ba phần khi thuận giá, giữ các lệnh thua và tính funding; dừng mở mới ở DD20% không tự bật lại. Riêng cấu hình đã khóa có thời hạn168h được đóng cả lệnh lỗ, khác yêu cầu giữ lệnh không thời hạn ban đầu.</p><p>__AUDIT__</p></section>
<section class="panel"><h2>Giới hạn kết luận</h2><p>Chưa đạt50% từng tháng; chưa bật live. Dữ liệu đã dùng lặp, tập coin cố định có thể thiên lệch; bộ lọc sàn hiện tại, maintenance proxy1%, giả định phí/trượt và nến5 phút chưa thay thế sổ lệnh/bậc ký quỹ lịch sử. Phí/trượt cơ sở0,05%/0,20%, cao0,10%/0,50% mỗi lần khớp. Không thay cấu hình tài khoản thật.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">Toàn bộ kết quả</a> · <a href="filter_counts.json">Số tín hiệu qua bộ lọc</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc khóa</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    for k,val in dict(STYLE=style,TARGET=escape(target),FINDING=escape(finding),DIAGNOSIS=escape(diagnosis),RUNS=str(total),TESTS=str(tests),HEAD=head,PICKED=''.join(tr(r) for r in picked),OPTIONS=options,PERIODS=periods,RHEAD=rolling_head,STARTS=''.join(tr(r) for r in starts),ROWS=''.join(tr(r) for r in rows),AUDIT=escape(audit),SCRIPT=script,FAILURES=escape(failure_note)).items():html=html.replace('__'+k+'__',val)
    html=html.replace('Xem mọi đường bị dừng</a>.','Xem mọi đường bị dừng</a> · <a href="failure_verification.json">Đối soát tại thời điểm dừng</a>.')
    for a,b in [('tăng50','tăng 50'),('bằng09','bằng 09'),('nhất20','nhất 20'),('từ10','từ 10'),('từ09','từ 09'),('đến06','đến 06'),('sổ500','sổ 500'),('số10','số 10'),('bộ30','bộ 30'),('BTC7','BTC 7'),('BTC4h','BTC 4h'),('rộng60','rộng 60'),('nhất60','nhất 60'),('tại00','tại 00'),('thiểu24','thiểu 24'),('hình25','hình 25'),('khoảng5','khoảng 5'),('ởx5','ở x5'),('khoảng20','khoảng 20'),('khoản500','khoản 500'),('đa5','đa 5'),('hạn168','hạn 168'),('đạt50','đạt 50'),('proxy1','proxy 1'),('nến5','nến 5'),('sở0','sở 0'),('cao0','cao 0')]:html=html.replace(a,b)
    (OUT/'dashboard.html').write_text(html,encoding='utf-8')
    md=['# Bộ lọc thị trường và độ bền theo mốc khởi chạy','',target,'',finding,'',diagnosis,'',
        'Cặp số cơ sở / chi phí cao; mỗi cửa sổ500USDT. Cửa sổ chồng lấn, không độc lập. Quy mô100 danh nghĩa và đóng theo168h là các phương án nghiên cứu ngoài mặc định.',
        '| Cấu hình |Có lời|Tệ nhất|Tốt nhất|DD lớn nhất|Quý có lời|','|---|---:|---:|---:|---:|---:|',*['| '+' | '.join(r)+' |' for r in starts],'',failure_note,'',audit,'',s['protocol']['limitations'],'',
        '[Dashboard](dashboard.html) · [Mọi kết quả](comparison.csv) · [Đối soát](verification.json)']
    (OUT/'report.md').write_text('\n'.join(md),encoding='utf-8')
    write(OUT/'findings.json',dict(target=target,finding=finding,diagnosis=diagnosis))
    write(OUT/'goal_progress.json',dict(classification='progress',goal_status='active',achieved=False,runs=total,target_passes=s['target_met_rows'],evidence=finding+' '+diagnosis,
        next_steps=['Use monthly-start robustness to distinguish concentrated historical gains from repeatable exposure; do not promote annual gains as50%monthly.',
        'Test a distinct paired/exposure-aware hypothesis only with a preregistered finite-account protocol and retained losing inventory.'],live_config_unchanged=True))
    assert sha(ROOT/'configs/live.yaml')==s['protocol']['live_config_sha256'];print(OUT/'dashboard.html')


if __name__=='__main__':main()
