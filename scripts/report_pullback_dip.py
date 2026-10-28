"""Capital and capacity sensitivity of frozen momentum pullback entries."""
import json
from html import escape
import xml.etree.ElementTree as ET
import pandas as pd
from search_pullback_dip import OUT,read,ROOT,sha,write

LABELS={'none':'Không lọc thêm','counter24':'Điều chỉnh ngược 24 giờ','counter72':'Điều chỉnh ngược 72 giờ','dip24_shallow':'Điều chỉnh 24 giờ ≤ 2 ATR','dip24_deep':'Điều chỉnh 24 giờ > 2 ATR','ema_pullback':'Hồi qua EMA20, EMA20/60 giữ hướng'}

def name(sp):return f"{LABELS[sp['gate']]} · {sp['notional']} USDT danh nghĩa"


def closed_attribution(raw,fee):
    active={};closed=[]
    for j in raw['journal']:
        coin=j['symbol']
        if j['kind']=='entry':active[coin]=dict(symbol=coin,side=j['side'],event_id=j['event_id'],opened_at=j['at'],qty=0.,basis=0.,fees=0.,funding=0.)
        if j['kind'] in ['entry','entry_add']:
            p=active[coin];p['qty']+=j['qty'];p['basis']+=j['qty']*j['price'];p['fees']+=j['qty']*j['price']*fee
        elif j['kind']=='funding':active[coin]['funding']+=j['amount']
        elif 'net' in j:
            p=active.pop(coin);gross=(1 if p['side']=='LONG' else -1)*(p['qty']*j['price']-p['basis']);p['fees']+=p['qty']*j['price']*fee
            assert abs(gross-p['fees']+p['funding']-j['net'])<1e-7
            closed.append(dict(p,closed_at=j['at'],gross=gross,net=j['net'],held_days=(j['at']-p['opened_at'])/86400000))
    assert abs(sum(t['net'] for t in closed)-raw['closed_trade_net'])<1e-7
    return closed



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
    focus=next((x['strategy_id'] for x in s['selected'] if x['reference']=='n25' and x['strategy_id']),'dip_n25_none')
    rs=[look[(focus,'later',c)] for c in ['base','stress']]
    finding=f"Lựa chọn khóa bằng 09/2025–05/2026: {choice}. {name(specs[focus])}, khởi chạy riêng 06–08 từ 500 USDT: tài sản cuối {fmt(rs[0]['ending_equity'])} / {fmt(rs[1]['ending_equity'])} USDT; {rs[0]['entries']} / {rs[1]['entries']} vị thế vào. Cần đối chiếu các tháng âm và nhiều mốc khởi chạy, không suy ra hiệu quả chỉ từ một quý có lời."
    rr=[robust[(focus,c)] for c in ['base','stress']]
    finding+=f" Trên 10 mốc ba tháng, có lời ở {rr[0]['profitable']}/10 và {rr[1]['profitable']}/10; tài sản tệ nhất {fmt(rr[0]['worst_ending'])} / {fmt(rr[1]['worst_ending'])} USDT. Các cửa sổ chồng lấn và đã được nghiên cứu, không phải 10 mẫu tương lai độc lập."
    control='dip_n25_none';cr=[look[(control,'later',c)] for c in ['base','stress']];cb=[robust[(control,c)] for c in ['base','stress']]
    finding+=f" Đối chứng cùng 25 USDT không lọc thêm: kỳ 06–08 đạt {fmt(cr[0]['ending_equity'])} / {fmt(cr[1]['ending_equity'])} USDT, có lời ở {cb[0]['profitable']}/10 và {cb[1]['profitable']}/10 mốc. Kết quả từng quý và từng tháng cần được đọc cùng kết quả cả năm."
    paired=read(OUT/'paired_effect.json')
    weaker=sum(x['worsened']>5 for x in paired)
    finding+=f" Trong {weaker}/{len(paired)} phép so theo bộ lọc, mức vốn và chi phí, bộ lọc kém đối chứng ở đa số 10 mốc khởi chạy. Sự thay đổi số vị thế được nhận là một phần của kết quả tài khoản, không phải phép đo riêng chất lượng từng tín hiệu."
    deep='dip_n25_dip24_deep';dy=[look[(deep,'year',c)] for c in ['base','stress']];dl=[look[(deep,'later',c)] for c in ['base','stress']]
    finding+=f" Nhóm điều chỉnh sâu hơn 2 ATR ở quy mô 25 USDT: kỳ 06–08 đạt {fmt(dl[0]['ending_equity'])} / {fmt(dl[1]['ending_equity'])} USDT, nhưng cả năm chỉ còn {fmt(dy[0]['ending_equity'])} / {fmt(dy[1]['ending_equity'])} USDT; DD cả năm {100*dy[0]['max_drawdown']:.2f}% / {100*dy[1]['max_drawdown']:.2f}%. Vì vậy không thể chọn nhóm này chỉ từ quý có lời."
    diagnostic_path=OUT/'runs/year_base_dip_n25_dip24_deep.json'
    attributed=closed_attribution(read(diagnostic_path),s['protocol']['costs'][0][1])
    worst=min(attributed,key=lambda t:t['net'])
    cost_note=f"Trong đường cả năm, nhịp sâu >2 ATR, 25 USDT, chi phí cơ sở: vị thế {worst['side']} {worst['symbol']} giữ {worst['held_days']:.2f} ngày. Chênh lệch giá đem lại {worst['gross']:.2f} USDT, funding {worst['funding']:.2f} USDT, phí {worst['fees']:.4f} USDT; kết quả ròng {worst['net']:.2f} USDT. Trailing theo giá có thể đóng một giao dịch âm ròng sau chi phí nắm giữ. Đây là đối soát một trường hợp đã xảy ra trong mô phỏng, không loại coin này khỏi mẫu."
    write(OUT/'cost_diagnostic.json',dict(source_run=diagnostic_path.name,source_sha256=sha(diagnostic_path),closed=attributed,worst=worst,explanation=cost_note))
    finding+=' '+cost_note
    audit=f"{count} kiểm thử đạt; đối soát {v['totals']['journals']} sổ, {v['totals']['baseline_paths_exact']} đối chứng tài chính khớp lượt cũ và {v['totals']['replayed_paths_exact']} đường chạy lại khớp. Tái dựng {v['totals']['capital_checks']:,} lần kiểm tra vốn, gồm {v['totals']['capital_denied']:,} lần thiếu vốn, cùng {v['totals']['cancellations']:,} sự kiện hủy phần vào tiếp. Kiểm tra {v['totals']['equity_states']:,} mốc tài sản."
    audit+=f" Đối chiếu {v['totals']['independent_signal_sets']} bộ tín hiệu bằng công thức độc lập và {v['totals']['causal_prefixes']} lần cắt dữ liệu tại giờ chưa đóng nến 4 giờ."
    failures=read(OUT/'incomplete_paths.json')
    failure_note='Không có đường mô phỏng dừng vì thiếu tài sản đảm bảo trong lượt này; điều này không xác minh được thanh lý lịch sử trên sàn.'
    if failures:
        halt_times=sorted({f['stop_event']['at'] for f in failures})
        failure_note=f"{len(failures)} đường dừng vì ngưỡng maintenance proxy 1%, tại {len(halt_times)} thời điểm; không phải các sự kiện độc lập. Không dựng lệnh thanh lý hoặc số dư cuối."
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
    extra="""function capitalRender(){const st=document.querySelector('#strategy').value,w=document.querySelector('#window').value,c=document.querySelector('#cost').value;document.querySelector('#capitalBody').innerHTML=data.filter(r=>r.strategy_id===st&&r.window===w&&(r.cost==='base'||r.cost===c)).map(r=>`<tr><td>${r.cost==='base'?'Cơ sở':'Cao'}</td><td>${r.candidates}</td><td>${r.entries}</td><td>${num(r.utilization.mean_positions)}</td><td>${num(r.utilization.mean_committed_margin)}</td><td>${num(r.utilization.peak_committed_margin)}</td><td>${r.margin_rejections}</td><td>${num(100*r.utilization.fraction_time_paused)}%</td><td>${num(r.closed_net)}</td><td>${num(r.retained_net)}</td></tr>`).join('');}const chartRender=render;render=function(){chartRender();capitalRender();};"""
    script=script.replace("for(const id of ['strategy','window','cost'])",extra+"for(const id of ['strategy','window','cost'])",1)
    options=''.join(f'<option value="{sp["id"]}"'+(' selected' if sp['id']==focus else '')+'>'+escape(name(sp))+'</option>' for sp in s['specs'])
    periods=''.join(f'<option value="{w}"'+(' selected' if w=='later' else '')+'>'+escape({'development':'09/2025–05/2026 · kỳ chọn','year':'09/2025–08/2026 · cả năm','later':'06–08/2026'}.get(w,'Ba tháng từ '+pd.Timestamp(t[0],unit='ms',tz='UTC').strftime('%m/%Y')))+'</option>' for w,t in s['protocol']['windows'].items())
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Độ sâu nhịp điều chỉnh tại điểm vào</title><style>__STYLE__</style></head><body><main><div class="eyebrow">ĐẢO VÀNG / NGHIÊN CỨU LƯỢT 35</div><h1>Nhịp điều chỉnh ngược hướng có cho điểm vào tốt hơn?</h1><p class="muted">Cố định xu hướng 7 ngày + chờ hồi 0,5 ATR · Long + Short · tài khoản 500 USDT · Cross x5</p><div class="notice"><b>__TARGET__</b><p>__FINDING__</p><p>Giữ hướng theo xu hướng tuần; chỉ chọn thêm các nhịp điều chỉnh ngắn hạn ngược hướng lệnh tại lần chạm điều kiện hồi đầu tiên. Tách nhịp nông/sâu bằng ATR đã khóa ở tín hiệu gốc. Nếu không đạt, bỏ tín hiệu; không chờ thêm hoặc chọn đáy/đỉnh sau khi biết kết quả. Giữ trailing, không cắt lỗ; chưa thay cấu hình live.</p></div>
<section class="panel"><h2>Sàng lọc ứng viên trong cả năm</h2><p>Tổng ứng viên chạm điều kiện hồi là 2.211. Đây là số tín hiệu trước kiểm tra sức chứa và khối lượng sàn, không phải số vị thế đã mở.</p><div class="scroll"><table><thead><tr><th>Bộ lọc</th><th>Giữ lại</th><th>Long</th><th>Short</th><th>Không đạt điều kiện nhịp hồi</th><th>Thiếu dữ liệu</th></tr></thead><tbody id="gateBody">__GATES__</tbody></table></div></section><section class="panel"><h2>Toàn bộ 12 cấu hình</h2><p>Cặp số chi phí cơ sở / chi phí cao. ★ là lựa chọn riêng cho từng mức vốn, khóa trước khi chạy các kỳ sau: cả hai mức chi phí có lời, DD dưới 20%, ít nhất 20 lệnh đóng, đủ dữ liệu; ưu tiên tháng tệ nhất rồi tài sản cuối. Quy mô là tổng danh nghĩa của cả ba phần, không phải mỗi phần.</p><div class="scroll"><table><thead>__HEAD__</thead><tbody>__TABLE__</tbody></table></div></section>
<section class="panel"><h2>Tài sản và các khoản lời/lỗ</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Kỳ<select id="window">__PERIODS__</select></label><label>Chi phí<select id="cost"><option value="stress">Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản gồm vị thế còn mở"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><div class="scroll"><table><thead><tr><th>Chi phí</th><th>Ứng viên trong kỳ</th><th>Vị thế đã mở</th><th>Vị thế TB</th><th>Vốn giữ chỗ TB</th><th>Vốn giữ chỗ tối đa</th><th>Lần thiếu vốn</th><th>Thời gian khóa mở mới</th><th>Ròng lệnh đóng</th><th>Đóng góp lệnh mở</th></tr></thead><tbody id="capitalBody"></tbody></table></div><p>Vốn giữ chỗ gồm ký quỹ mô phỏng theo Mark, vốn dành cho phần chưa khớp và phí dự kiến; không phải mức lỗ tối đa. Trung bình có trọng số thời gian; nếu đường dừng sớm chỉ tính đoạn quan sát. Lần thiếu vốn tính cả vào mới và vào thêm. Tài sản = 500 + ròng lệnh đóng + đóng góp lệnh mở; các khoản ròng đã gồm phí và funding. Khi DD đạt 20%, khóa mở mới nhưng vẫn giữ vị thế và trailing. Không tự bật lại.</p></section>
<section class="panel"><h2>Thử từ 10 mốc khởi chạy</h2><p>Mỗi kỳ ba tháng có 500 USDT riêng, bắt đầu từ 09/2025 đến 06/2026. Các kỳ chồng lấn, chỉ có bốn quý không chồng lấn. Đây là lịch sử đã nghiên cứu nhiều lần, chưa phải bằng chứng tương lai mới. Kỳ không hoàn tất vẫn ở mẫu số; tài sản tệ nhất chỉ tính kỳ hoàn tất.</p><div class="scroll"><table><thead>__RHEAD__</thead><tbody>__ROLLING__</tbody></table></div></section>
<section class="panel"><h2>Quy tắc tín hiệu, vốn và đối soát</h2><p>Bộ lọc điều chỉnh 24/72 giờ yêu cầu lợi suất log ngược hướng lệnh: Long chờ giá giảm, Short chờ giá tăng trong khoảng tương ứng, đủ toàn bộ 25/73 giá đóng cửa giờ. Nhịp 24 giờ được chia thành hai nhóm rời nhau: độ dịch chuyển ngược hướng lớn hơn 0 và không quá 2 ATR; hoặc lớn hơn 2 ATR. ATR là ATR14 nến 4 giờ tại tín hiệu gốc, không cập nhật theo dữ liệu mới. Hai nhóm hợp lại đúng bằng bộ lọc điều chỉnh 24 giờ; giá không đổi bị loại.</p><p>Bộ lọc EMA hồi yêu cầu EMA20/EMA60 vẫn theo hướng lệnh nhưng giá đóng cửa giờ hiện tại đã qua phía ngược lại của EMA20. Chỉ dùng EMA của nến 4 giờ đã đóng, đủ 72 nến liên tiếp; Long/Short đối xứng. Đây là điều kiện vào thêm, không đảo hướng giao dịch gốc.</p><p>Cùng tín hiệu Long/Short momentum 7 ngày, chờ hồi thuận giá 0,5 ATR trong giờ thứ 1–23 sau tín hiệu gốc. Giữ ATR14 nến 4 giờ, hướng và độ ưu tiên lúc phát tín hiệu. Mọi mức vốn dùng cùng các ứng viên; không tăng vốn theo lợi nhuận hoặc nhân tuyến tính lợi nhuận cũ.</p><p>Cố định tổng danh nghĩa mỗi vị thế 25 hoặc 100 USDT, tương ứng khoảng 5 hoặc 20 USDT ký quỹ dự kiến ở x5; 100 là phương án nghiên cứu tăng vốn. Giới hạn 5 vị thế; một vị thế mỗi coin. Mỗi vị thế chia ba phần, chỉ vào thêm thuận giá 0,25 ATR và hết hạn sau 6 giờ. Trailing kích hoạt ở 3 ATR, hồi 1%; không stop-loss, không đóng lỗ theo thời gian.</p><p>Trước khi vào mới, giữ đủ chỗ cho phần hiện tại và hai phần dự kiến, kể cả phần cam kết của vị thế khác. Khi vào thêm, kiểm tra lại phần còn lại. Hết hạn, kích hoạt trailing, sai quy tắc khối lượng, thiếu vốn hoặc dừng mở mới sẽ hủy phần vào tiếp theo quy tắc đã có. Nhật ký quan sát ghi các lần kiểm tra và hủy; sổ vốn được tái dựng độc lập từ lần khớp, funding và sự kiện hủy. Bộ lọc không đóng các vị thế đã giữ hoặc thay đổi điều kiện vào các phần tiếp theo.</p><p>__AUDIT__</p></section>
<section class="panel"><h2>Giới hạn kết luận</h2><p>Phí/trượt mỗi lần khớp: cơ sở 0,05%/0,20%, cao 0,10%/0,50%. Funding thực, mọi vị thế mở được định giá. Tập 30 coin cố định, bộ lọc sàn hiện tại, maintenance proxy 1% và dữ liệu 5 phút chưa chứng minh thanh lý lịch sử hoặc khả năng khớp thật. Chưa đạt 50% mỗi tháng; chưa bật live.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">Mọi kết quả</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc khóa</a> · <a href="incomplete_paths.json">Đường không hoàn tất</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    counts=read(OUT/'gate_counts.json')
    gate_rows=[[LABELS[g],len(es),sum(e['side']=='LONG' for e in es),sum(e['side']=='SHORT' for e in es),counts[g].get('dip_disagrees',0),counts[g].get('missing_state',0)] for g,es in signals.items()]
    for key,value in dict(GATES=''.join(tr(r) for r in gate_rows),STYLE=style,TARGET=escape(target),FINDING=escape(finding),HEAD=tr(['Cấu hình vốn','Tài sản kỳ chọn','Tài sản 06–08','Tài sản cả năm','Số vị thế cả năm','DD cả năm']),TABLE=''.join(tr(r) for r in tables),OPTIONS=options,PERIODS=periods,RHEAD=tr(['Cấu hình vốn','Kỳ có lời','Tài sản tệ nhất','DD lớn nhất','Quý có lời']),ROLLING=''.join(tr(r) for r in rolling),AUDIT=escape(audit),SCRIPT=script).items():html=html.replace('__'+key+'__',value)
    (OUT/'dashboard.html').write_text(html,encoding='utf-8')
    md=['# Độ sâu nhịp điều chỉnh tại điểm vào','',target,'',finding,'','Cặp số chi phí cơ sở / cao. ★ chọn bằng kỳ đầu; các biến thể lọc nhịp điều chỉnh ngắn hạn tại điểm vào, giữ nguyên thời điểm ứng viên và cách thoát.',
        '|Cấu hình vốn|Kỳ chọn|06–08|Cả năm|Số vị thế|DD cả năm|','|---|---:|---:|---:|---:|---:|',*['| '+' | '.join(r)+' |' for r in tables],'',
        '|Cấu hình vốn|Kỳ có lời|Tệ nhất|DD lớn nhất|Quý có lời|','|---|---:|---:|---:|---:|',*['| '+' | '.join(r)+' |' for r in rolling],'',audit,'',
        'Các cửa sổ chồng lấn và đã được nghiên cứu trước. Tài sản tính cả vị thế chưa đóng. Quy mô25/100 là danh nghĩa toàn bộ3phần; ký quỹ dự kiến5/20ởx5. Kiểm tra độ dịch chuyển ngược hướng tại giờ chạm hồi đầu tiên bằng dữ liệu đã đóng; không trì hoãn/tái chọn ứng viên bị loại. No live changes.',s['protocol']['limitations']]
    (OUT/'report.md').write_text('\n'.join(md),encoding='utf-8');write(OUT/'findings.json',dict(target=target,finding=finding))
    write(OUT/'goal_progress.json',dict(classification='progress',goal_status='active',achieved=False,runs=len(s['results']),target_passes=s['target_met_rows'],evidence=finding,
        next_steps=['Test entry filters using only funding already settled before the decision, relative to the frozen ATR move; future realized funding must never determine entry eligibility. The diagnosed deep-pullback SOON short had positive gross price PnL but negative net after91days of carry.','Keep identical wallet, costs and held-position valuation; no after-the-fact coin exclusions or treating reused history as new holdout.'],live_config_unchanged=True))
    assert sha(ROOT/'configs/live.yaml')==s['protocol']['live_config_sha256'];print(OUT/'dashboard.html')


if __name__=='__main__':main()
