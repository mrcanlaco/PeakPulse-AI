"""Net trailing and settled carry sensitivity, with all failed variants retained."""
import json
import xml.etree.ElementTree as ET
from html import escape
import pandas as pd
from compare_account_risk import ROOT,write,sha
from search_net_trailing import OUT,read

FAMILIES=dict(short_reversal='Short đảo chiều',long_reversal='Long đảo chiều',both_reversal='Long + Short đảo chiều',both_trend='Long + Short phá vỡ theo xu hướng')
GATES=dict(none='Không lọc',avoid_costly='Tránh funding đắt',nonnegative='Funding đang không âm')
EXITS=dict(price='Trailing giá 3ATR / 1%',net_gate='Trailing giá + kiểm tra lãi ròng',net_peak0_5='Lãi ròng 0,5 USDT',net_peak1='Lãi ròng 1 USDT',net_peak2='Lãi ròng 2 USDT')


def name(sp):return FAMILIES[sp['family']]+' · '+GATES[sp['gate']]+' · '+EXITS[sp['exit'].replace('.','_')]


def main():
    s=read(OUT/'summary.json');v=read(OUT/'verification.json');specs={sp['id']:sp for sp in s['specs']}
    tree=ET.parse(OUT/'unit_tests.xml').getroot();n_tests=len(tree.findall('.//testcase'))
    assert not tree.findall('.//failure') and not tree.findall('.//error')
    look={(r['strategy_id'],r['window'],r['cost']):r for r in s['results']}
    num=lambda x:'Không hoàn tất' if x is None else f'{x:.2f}'
    tr=lambda xs:'<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in xs)+'</tr>'
    all_rows=[];selected_rows=[];quarter_rows=[];selected={r['strategy_id'] for r in s['selected'] if r['strategy_id']}
    for sp in s['specs']:
        rs=lambda w:[look[(sp['id'],w,c)] for c in ['base','stress']]
        row=[name(sp),*[' / '.join(num(r['ending_equity']) for r in rs(w)) for w in ['development','later','year']],
            ' / '.join(f"{100*r['max_drawdown']:.2f}%" for r in rs('year')),
            ' / '.join(str(r['entries']) for r in rs('year')),
            ' / '.join(str(r['open_count']) for r in rs('year')),
            ' / '.join(num(r['funding']) for r in rs('year'))]
        all_rows.append(row)
        if sp['id'] in selected or sp['baseline']:selected_rows.append(row)
        if sp['id'] in s['quarter_specs']:
            windows=['quarter_0','quarter_3','quarter_6','later']
            pairs=[rs(w) for w in windows]
            quarter_rows.append([name(sp),*[' / '.join(num(r['ending_equity']) for r in pair) for pair in pairs],
                ' / '.join(str(sum(look[(sp['id'],w,c)]['ending_equity'] is not None and look[(sp['id'],w,c)]['ending_equity']>500 for w in windows))+'/4' for c in ['base','stress'])])
    picked=[]
    for choice in s['selected']:
        if choice['strategy_id'] is None:
            picked.append(FAMILIES[choice['family']]+': không cấu hình nào đạt điều kiện chọn trên giai đoạn đầu.');continue
        sp=specs[choice['strategy_id']];a,b=[look[(sp['id'],'later',c)] for c in ['base','stress']]
        picked.append(name(sp)+f": 06–08/2026 kết thúc {num(a['ending_equity'])} / {num(b['ending_equity'])} USDT.")
    total=len(s['results']);target=f"{s['target_met_rows']}/{total} đường đạt tăng 50% trong từng tháng; {s['incomplete_paths']} đường không hoàn tất."
    baseline=look[('both_reversal_none_price','year','base')]
    gate=look[('both_reversal_none_net_gate','year','base')]
    diagnosis=(f"Chỉ thêm điều kiện lãi ròng không âm cho trailing giá của Long + Short đảo chiều: cả năm từ {num(baseline['ending_equity'])} "
        f"thành {num(gate['ending_equity'])} USDT; {gate['blocked_net_exit_positions']} vị thế từng bị chặn thoát vì ước tính lãi ròng âm, "
        f"cuối kỳ còn {gate['open_count']} vị thế, funding {gate['funding']:.2f} USDT. Chặn ghi nhận lỗ không đồng nghĩa loại bỏ khoản lỗ đó.")
    negatives=sum(r['negative_exits'] for r in s['results'] if r['exit']!='price')
    audit=(f"{n_tests} kiểm thử; {v['totals']['journals']} sổ đối soát; {v['totals']['baseline_paths_exact']} đối chứng khớp toàn bộ lượt cũ; "
        f"{v['totals']['replayed_paths_exact']} đường chạy lại khớp; tính lại funding đã biết cho {v['totals']['independent_funding_events']} sự kiện, "
        f"{v['totals']['causal_prefixes']} phép cắt dữ liệu tương lai. Tái dựng độc lập điều kiện kích hoạt/thoát cho {v['totals']['net_lifecycles']:,} vòng đời "
        f"tại {v['totals']['net_decision_states']:,} thời điểm; đối soát {v['totals']['funding']:,} khoản funding, {v['totals']['fills']:,} lần khớp, "
        f"{v['totals']['states']:,} mốc tài sản. Các số đếm chồng lấn giữa cấu hình, không phải mẫu độc lập.")
    series=[]
    for row in s['results']:
        curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet');ix={0,len(curve)-1}
        for _,g in curve.groupby((curve['at']-curve['at'].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(row,points=[[int(p['at']),round(p.equity,6)] for _,p in curve.loc[sorted(ix)].iterrows()]))
    write(OUT/'dashboard_data.json',series)
    old=(ROOT/'artifacts/signal_priority_20260925/dashboard.html').read_text(encoding='utf-8');style=old.split('<style>',1)[1].split('</style>',1)[0]
    script=old.split('<script>',1)[1].split('</script>',1)[0]
    script='const spans='+json.dumps(dict(s['protocol']['windows'],**s['protocol']['quarters']))+script[script.index(',labels='):]
    # Extra quarters exist only for locked candidates and their matched baselines.
    script=script.replace('const values=rows.flatMap',"if(!rows.length){document.querySelector('#chart').innerHTML='';document.querySelector('#chartStatus').textContent='Quý này chỉ chạy cấu hình đã chọn và đối chứng tương ứng; hãy chọn cả năm hoặc 06–08 để xem mọi biến thể.';document.querySelector('#monthHead').innerHTML='';document.querySelector('#monthBody').innerHTML='';return;}const values=rows.flatMap")
    default=next((r['strategy_id'] for r in s['selected'] if r['family']=='both_reversal' and r['strategy_id']),'both_reversal_none_price')
    options=''.join(f'<option value="{sp["id"]}"'+(' selected' if sp['id']==default else '')+'>'+escape(name(sp))+'</option>' for sp in s['specs'])
    periods=''.join(f'<option value="{key}"'+(' selected' if key=='later' else '')+'>'+label+'</option>' for key,label in [('development','Chọn:09/2025–05/2026'),('later','06–08/2026'),('year','Cả năm09/2025–08/2026'),('quarter_0','09–11/2025'),('quarter_3','12/2025–02/2026'),('quarter_6','03–05/2026')])
    header='<tr>'+''.join('<th>'+x+'</th>' for x in ['Cấu hình','Tài sản giai đoạn chọn','Tài sản 06–08','Tài sản cả năm','DD cả năm','Lệnh vào cả năm','Còn mở cuối năm','Funding cả năm'])+'</tr>'
    qheader='<tr>'+''.join('<th>'+x+'</th>' for x in ['Cấu hình','09–11/2025','12/2025–02/2026','03–05/2026','06–08/2026','Quý có lời'])+'</tr>'
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Funding và trailing lãi ròng</title><style>__STYLE__</style></head><body><main><div class="eyebrow">ĐẢO VÀNG / LONG & SHORT · LƯỢT 24</div><h1>Funding và trailing theo lợi nhuận ròng</h1><p class="muted">500 USDT · Cross x5 · tối đa5 vị thế · tổng25 USDT danh nghĩa/vị thế · 3 phần · khôngSL/không đóng theo thời gian</p><div class="notice"><b>__TARGET__</b><p>__DIAGNOSIS__</p></div>
<div class="cards"><div class="card">Nhóm tín hiệu<strong>4</strong></div><div class="card">Lọc funding × cách thoát<strong>3 × 5</strong></div><div class="card">Cấu hình / đường chạy<strong>60 / __RUNS__</strong></div><div class="card">Kiểm thử đạt<strong>__TESTS__</strong></div></div>
<section class="panel"><h2>Lựa chọn trước giai đoạn tháng6–8</h2><p>Chỉ chọn bằng09/2025–05/2026: cả hai mức chi phí có lời, DD&lt;20%, ít nhất20 vị thế đã đóng, đường đầy đủ. Ưu tiên tháng tệ nhất tốt hơn, sau đó tài sản cuối. Lịch sử đã được nghiên cứu nhiều lần; đây không phải mẫu tương lai mới. Cặp số: cơ sở / chi phí cao.</p><ul>__PICKED__</ul><div class="scroll"><table><thead>__HEADER__</thead><tbody>__SELECTED__</tbody></table></div></section>
<section class="panel"><h2>Tài sản gồm mọi vị thế còn mở</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Kỳ<select id="window">__PERIODS__</select></label><label>Chi phí<select id="cost"><option value="stress">Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản tính cả lỗ chưa chốt"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div></section>
<section class="panel"><h2>Bốn quý không chồng lấn</h2><p>Mỗi quý bắt đầu lại với500 USDT. Chỉ chạy bổ sung ba quý đầu cho cấu hình đã chọn và đối chứng tương ứng; quý cuối đã có ở kỳ06–08. Các quý đầu nằm trong giai đoạn chọn, không phải kiểm định độc lập. Có lời cả quý vẫn có thể có tháng âm.</p><div class="scroll"><table><thead>__QHEADER__</thead><tbody>__QUARTERS__</tbody></table></div></section>
<section class="panel"><h2>Toàn bộ60 cấu hình</h2><div class="scroll"><table><thead>__HEADER__</thead><tbody>__ALL__</tbody></table></div></section>
<section class="panel"><h2>Quy tắc được kiểm tra</h2><p>Ba bộ lọc: giữ nguyên; tránh chi phí funding đang cao (tỷ lệ thu vào ở kỳ gần nhất≥−0,05% và tổng24h≥−0,10%); chỉ nhận khi cả hai tỷ lệ thu vào không âm. Long đổi dấu tỷ lệ funding, Short giữ dấu. Dùng khoản đã thanh toán ít nhất60 giây trước tín hiệu, kiểm tra độ mới và đủ24h dữ liệu. Không dự đoán được funding tương lai, không bỏ riêng coin từng gây lỗ. Không tái tạo tín hiệu/cooldown sau khi lọc.</p><p>Năm cách thoát: trailing giá3ATR/1% gốc; cùng trailing giá nhưng yêu cầu lãi ròng ước tính≥0; ba trailing lợi nhuận ròng kích hoạt tại0,5/1/2 USDT trên lượng thực khớp và thoát khi giảm25% từ đỉnh lãi ròng, đồng thời lãi ước tính≥0. Kích hoạt thì hủy các phần vào thêm còn chờ. Ước tính gồm phí vào, phí thoát, trượt giá bất lợi và funding đã trả/nhận. Chỉ dùng nến đóng, sau đó khớp mở nến kế tiếp.</p><p>Giá nhảy vẫn có thể khiến lệnh thực thoát âm: ghi nhận __NEGATIVE__ lượt thoát âm trong các biến thể kiểm tra lãi ròng, đếm chồng lấn giữa cấu hình. Khi ước tính âm, các biến thể này tiếp tục giữ vị thế; lỗ và funding vẫn được ghi nhận. Đây không phải bảo đảm hòa vốn, giới hạn lỗ hay cơ chế tự động cứu tài khoản.</p><p>__AUDIT__</p></section>
<section class="panel"><h2>Giới hạn kết luận</h2><p>Mục tiêu50% từng tháng chưa đạt. Bộ lọc sàn hiện tại, maintenance proxy1%, dữ liệu sổ lệnh/bậc ký quỹ lịch sử chưa đủ, tập coin cố định có thể thiên lệch. Phí/trượt cơ sở0,05%/0,20%, cao0,10%/0,50% mỗi lần khớp. Đường chưa hoàn tất không được coi như tài khoản sống sót. Chưa bật live; cấu hình tài khoản thật giữ nguyên.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">Toàn bộ kết quả</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc khóa</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    for key,val in dict(STYLE=style,TARGET=escape(target),DIAGNOSIS=escape(diagnosis),RUNS=str(total),TESTS=str(n_tests),PICKED=''.join('<li>'+escape(x)+'</li>' for x in picked),
        HEADER=header,SELECTED=''.join(tr(r) for r in selected_rows),OPTIONS=options,PERIODS=periods,QHEADER=qheader,QUARTERS=''.join(tr(r) for r in quarter_rows),
        ALL=''.join(tr(r) for r in all_rows),NEGATIVE=str(negatives),AUDIT=escape(audit),SCRIPT=script).items():html=html.replace('__'+key+'__',val)
    for a,b in [('tối đa5','tối đa 5'),('tổng25','tổng 25'),('khôngSL','không SL'),('tháng6','tháng 6'),
                ('bằng09/','bằng 09/'),('nhất20','nhất 20'),('lại với500','lại với 500'),('có ở kỳ06','có ở kỳ 06'),
                ('bộ60','bộ 60'),('giá3ATR','giá 3 ATR'),('tại0,5','tại 0,5'),('giảm25%','giảm 25%'),
                ('trước tín hiệu,','trước tín hiệu,'),('tiêu50%','tiêu 50%'),('proxy1%','proxy 1%'),
                ('sở0,05%','sở 0,05%'),('cao0,10%','cao 0,10%'),('nhất60 giây','nhất 60 giây'),('đủ24h','đủ 24h')]:
        html=html.replace(a,b)
    (OUT/'dashboard.html').write_text(html,encoding='utf-8')
    md=['# Funding và trailing lãi ròng','',target,'',diagnosis,'',*picked,'',
        'Cặp số cơ sở / chi phí cao. Chọn trên09/2025–05/2026; báo cáo mọi biến thể, không coi lịch sử đã dùng là OOS mới.','',
        '| Cấu hình |Giai đoạn chọn|06–08|Cả năm|DD năm|Vào|Mở|Funding|','|---|---:|---:|---:|---:|---:|---:|---:|',
        *['| '+' | '.join(r)+' |' for r in all_rows],'',audit,'',s['protocol']['limitations'],'',
        'Không bật live. Net gate có thể giữ lỗ lâu hơn; nhảy giá có thể làm thoát âm dù ước tính trước đó không âm.',
        '[Dashboard](dashboard.html) · [Quy tắc](protocol.json) · [Đối soát](verification.json)']
    (OUT/'report.md').write_text('\n'.join(md),encoding='utf-8')
    write(OUT/'findings.json',dict(target=target,diagnosis=diagnosis,selected_later=picked))
    write(OUT/'goal_progress.json',dict(classification='progress',goal_status='active',achieved=False,runs=total,target_passes=s['target_met_rows'],
        evidence=diagnosis,selected_later=picked,next_steps=['Use shared-account evidence to decide whether funding gates/net exits improve weak months rather than only moving losses into open inventory.',
        'Any candidate needs newly frozen forward evaluation; no repeated historical sweep proves50%eachmonth.'],live_config_unchanged=True))
    assert sha(ROOT/'configs/live.yaml')==s['protocol']['live_config_sha256']
    print(OUT/'dashboard.html')


if __name__=='__main__':main()
