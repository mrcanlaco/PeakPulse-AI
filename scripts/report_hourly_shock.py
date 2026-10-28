"""Audited, reproducible Long/Short hourly-shock comparison dashboard."""
import json
from html import escape
import xml.etree.ElementTree as ET
import pandas as pd
from search_hourly_shock import OUT,ROOT,read,write,sha


def label(key):
    if key=='control':return 'Đối chứng: giá 7 ngày'
    _,mode,tag=key.split('_')
    return ('Theo đà' if mode=='follow' else 'Đảo chiều')+' · thân nến '+('1,5' if tag=='a15' else '2,5')+' ATR'


def name(sp):
    return f"{label(sp['gate'])} · "+('giữ lệnh' if sp['holding']=='hold' else 'thoát 12h / 2ATR')+f" · {sp['notional']} USDT"


def main():
    s=read(OUT/'summary.json');v=read(OUT/'verification.json');signals=read(OUT/'signals.json')
    tests=ET.parse(OUT/'unit_tests.xml').getroot()
    assert not tests.findall('.//failure') and not tests.findall('.//error')
    count=len(tests.findall('.//testcase'))
    lookup={(r['strategy_id'],r['window'],r['cost']):r for r in s['results']}
    robust={(r['strategy_id'],r['cost']):r for r in s['robustness']}
    specs={sp['id']:sp for sp in s['specs']}
    selected={x['strategy_id'] for x in s['selected'] if x['strategy_id']}
    fmt=lambda x:'Không hoàn tất' if x is None else f'{x:.2f}'
    tr=lambda cells:'<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in cells)+'</tr>'
    def table(head,rows):return '<div class="scroll"><table><thead>'+tr(head)+'</thead><tbody>'+''.join(tr(r) for r in rows)+'</tbody></table></div>'
    rows=[];rolling=[]
    for sp in s['specs']:
        rs=lambda w:[lookup[(sp['id'],w,c)] for c in ['base','stress']]
        rows.append([name(sp)+(' ★' if sp['id'] in selected else ''),
            *[' / '.join(fmt(r['ending_equity']) for r in rs(w)) for w in ['development','later','year']],
            ' / '.join(str(r['entries']) for r in rs('year')),
            ' / '.join(f"{100*r['max_drawdown']:.2f}%" for r in rs('year'))])
        rr=[robust[(sp['id'],c)] for c in ['base','stress']]
        rolling.append([name(sp),' / '.join(f"{r['profitable']}/10" for r in rr),
            ' / '.join(fmt(r['worst_ending']) for r in rr),
            ' / '.join(f"{100*r['worst_drawdown']:.2f}%" for r in rr),
            ' / '.join(f"{r['nonoverlapping_profitable']}/4" for r in rr)])
    target=f"{s['target_met_rows']}/{len(s['results'])} đường đạt ≥50% trong từng tháng; {s['incomplete_paths']} đường không hoàn tất."
    findings=[]
    for selection in s['selected']:
        ident=selection['strategy_id']
        if ident is None:
            findings.append(f"{selection['reference']}: không cấu hình nào đạt tiêu chí chọn trên kỳ đầu.");continue
        sp=specs[ident];later=[lookup[(ident,'later',c)] for c in ['base','stress']]
        rr=[robust[(ident,c)] for c in ['base','stress']]
        findings.append(f"Với {sp['notional']} USDT danh nghĩa, kỳ 09/2025–05/2026 chọn {name(sp)}. Khởi chạy riêng 06–08/2026 từ 500 USDT: cuối {fmt(later[0]['ending_equity'])} / {fmt(later[1]['ending_equity'])} USDT. Có lời ở {rr[0]['profitable']}/10 và {rr[1]['profitable']}/10 mốc ba tháng; tài sản tệ nhất {fmt(rr[0]['worst_ending'])} / {fmt(rr[1]['worst_ending'])} USDT.")
    pairs=read(OUT/'paired_effect.json')
    better=sum(x['improved']>5 for x in pairs)
    findings.append(f"Trong {better}/{len(pairs)} phép so theo nguồn tín hiệu, mức vốn và chi phí, nguồn tín hiệu mới cho tài sản cuối cao hơn đối chứng ở đa số 10 mốc. Các cửa sổ chồng lấn, lịch sử đã được nghiên cứu nhiều lần; chưa phải bằng chứng tương lai mới.")
    failures=read(OUT/'incomplete_paths.json')
    if failures:findings.append(f"Có {len(failures)} đường dừng vì maintenance proxy 1%, tại {len({f['stop_event']['at'] for f in failures})} thời điểm lịch sử. Không dựng số dư cuối hay lệnh thanh lý giả.")
    else:findings.append('Không có đường chạm ngưỡng maintenance proxy trong lượt này; chưa xác minh được thanh lý lịch sử trên sàn.')
    audit=f"{count} kiểm thử đạt; {v['totals']['journals']} sổ giao dịch được đối soát; {v['totals']['baseline_paths_exact']} đối chứng khớp chính xác lượt cũ; {v['totals']['replayed_paths_exact']} đường chạy lại khớp. Kiểm tra {v['totals']['equity_states']:,} mốc tài sản và {v['totals']['capital_checks']:,} lần kiểm tra vốn. Tính độc lập cửa sổ ATR/khối lượng, thân nến, hướng và thời gian nghỉ; {v['totals']['causal_prefixes']} phép cắt dữ liệu kiểm tra tính nhân quả. Cấu hình live giữ nguyên."
    coverage=read(OUT/'coverage.json')
    candidates=[]
    for gate,es in signals.items():
        candidates.append([label(gate),len(es),sum(e['side']=='LONG' for e in es),sum(e['side']=='SHORT' for e in es)])
    series=[]
    for row in s['results']:
        raw=read(OUT/'runs'/f'{row["id"]}.json');curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet')
        ix={0,len(curve)-1}
        for _,g in curve.groupby((curve['at']-curve['at'].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        retained=sum(p['unrealized']-p['entry_fee']+p['funding'] for p in raw['open_positions'])
        if raw['ending_equity'] is not None:assert abs(500+raw['closed_trade_net']+retained-raw['ending_equity'])<1e-6
        series.append(dict(row,closed_net=raw['closed_trade_net'],retained_net=retained,fees=raw['fees'],funding=raw['funding'],
            price_pnl_after_slip=raw['ending_equity']-500+raw['fees']-raw['funding'] if raw['ending_equity'] is not None else None,
            points=[[int(p['at']),round(p.equity,6)] for _,p in curve.loc[sorted(ix)].iterrows()]))
    write(OUT/'dashboard_data.json',series)
    old=(ROOT/'artifacts/signal_priority_20260925/dashboard.html').read_text(encoding='utf-8')
    style=old.split('<style>',1)[1].split('</style>',1)[0]
    script=old.split('<script>',1)[1].split('</script>',1)[0]
    script='const spans='+json.dumps(s['protocol']['windows'])+script[script.index(',labels='):]
    extra="""function capitalRender(){const st=document.querySelector('#strategy').value,w=document.querySelector('#window').value,c=document.querySelector('#cost').value;document.querySelector('#capitalBody').innerHTML=data.filter(r=>r.strategy_id===st&&r.window===w&&(r.cost==='base'||r.cost===c)).map(r=>`<tr><td>${r.cost}</td><td>${r.candidates}</td><td>${r.entries}</td><td>${num(r.utilization.mean_positions)}</td><td>${num(r.utilization.mean_committed_margin)}</td><td>${num(r.utilization.peak_committed_margin)}</td><td>${r.margin_rejections}</td><td>${num(100*r.utilization.fraction_time_paused)}%</td><td>${num(r.closed_net)}</td><td>${num(r.retained_net)}</td><td>${r.risk_exits}</td><td>${r.time_exits}</td><td>${num(r.price_pnl_after_slip)}</td><td>${num(r.fees)}</td><td>${num(r.funding)}</td></tr>`).join('');}const chartRender=render;render=function(){chartRender();capitalRender();};"""
    script=script.replace("for(const id of ['strategy','window','cost'])",extra+"for(const id of ['strategy','window','cost'])",1)
    focus=next((x['strategy_id'] for x in s['selected'] if x['reference']=='n25' and x['strategy_id']),'hour_n25_control_hold')
    options=''.join(f'<option value="{sp["id"]}"'+(' selected' if sp['id']==focus else '')+'>'+escape(name(sp))+'</option>' for sp in s['specs'])
    periods=''.join(f'<option value="{w}"'+(' selected' if w=='later' else '')+'>'+escape({'development':'09/2025–05/2026 · kỳ chọn','later':'06–08/2026','year':'09/2025–08/2026 · cả năm'}.get(w,'Ba tháng từ '+pd.Timestamp(t[0],unit='ms',tz='UTC').strftime('%m/%Y')))+'</option>' for w,t in s['protocol']['windows'].items())
    strategy_notes='''<p>Quan sát mỗi nến 1 giờ đã đóng. Thân nến phải có độ lớn ít nhất 1,5 hoặc 2,5 ATR; ATR là trung bình True Range của 14 giờ TRƯỚC nến tín hiệu. Khối lượng USDT của nến ít nhất gấp đôi trung bình 24 giờ TRƯỚC. Nến tăng đóng ở 20% trên cùng của biên độ, nến giảm ở 20% dưới cùng. Cần 72 giờ OHLCV hợp lệ liên tiếp và tổng khối lượng 24 giờ ít nhất 2 triệu USDT.</p><p>Biến thể theo đà: Long sau nến tăng, Short sau nến giảm. Biến thể đảo chiều: ngược lại, trên cùng các thời điểm phát tín hiệu. Mỗi coin nghỉ ít nhất 6 giờ giữa hai tín hiệu trong cùng nguồn, tính trước việc nhận hay bỏ lệnh do sức chứa. Ưu tiên bằng độ lớn thân nến theo ATR nhân log(1 + tỷ lệ khối lượng). Khớp tại giá mở 5 phút kế tiếp có trượt giá; không giả định khớp trong nến tín hiệu. Đối chứng vẫn là xu hướng giá 7 ngày chờ hồi 0,5 ATR.</p><p>Cùng ví Cross 500 USDT, x5, tối đa 5 vị thế. Tổng danh nghĩa 25 USDT (ký quỹ dự kiến 5) hoặc 100 USDT (20, biến thể nghiên cứu); chia ba phần, chỉ thêm thuận giá 0,25 ATR trong 6 giờ. Trailing giá kích hoạt 3 ATR, hồi 1%. Bản giữ lệnh không stop-loss và không đóng lỗ theo tuổi lệnh. Bản thoát 12h / 2ATR bổ sung: thoát khi Mark vừa đóng đi ngược 2 ATR so với giá vốn bình quân, hoặc giữ đủ 12 giờ, điều kiện nào đến trước. ATR cố định lúc tín hiệu; ATR stop ưu tiên hơn tuổi lệnh và trailing. Khớp ở giá mở tiếp theo có trượt, có thể lỗ vượt 2 ATR; không mô phỏng một stop liên tục trên sàn. Đây là gói thoát thử nghiệm có thể chốt lỗ, chưa thay cấu hình thật.</p><p>Trước khi vào, tính cả vốn cam kết các phần chưa khớp. DD 20% khóa mở mới vĩnh viễn trong kỳ; vẫn quản lý vị thế, funding và các điều kiện thoát. Không tự bật lại, không vào lại cùng coin ngay bước vừa đóng. Toàn bộ vị thế mở được tính theo thị trường.</p>'''
    html=f'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Long/Short theo biến động và khối lượng 1 giờ</title><style>{style}</style></head><body><main><div class="eyebrow">ĐẢO VÀNG / NGHIÊN CỨU LƯỢT 39</div><h1>Đi theo đà hay đảo chiều sau nến biến động mạnh?</h1><p class="muted">18 cấu hình · 432 đường mô phỏng · 500 USDT · Cross x5 · ba phần và trailing TP</p><div class="notice"><b>{escape(target)}</b>{''.join('<p>'+escape(f)+'</p>' for f in findings)}</div>
<section class="panel"><h2>Ứng viên trước khi kiểm tra sức chứa</h2><p>30 coin có đủ 8.760 nến giờ trong năm; không thiếu nến đầu vào. Số ứng viên đã qua thời gian nghỉ 6 giờ, trước kiểm tra sức chứa và khối lượng sàn; không phải số vị thế đã mở.</p>{table(['Nguồn','Ứng viên','Long','Short'],candidates)}</section>
<section class="panel"><h2>Toàn bộ kết quả</h2><p>Cặp số cơ sở / chi phí cao, vốn đầu 500 USDT. ★ được khóa trên kỳ 09/2025–05/2026: cả hai mức chi phí có lời, DD dưới 20%, ít nhất 20 lệnh đóng và đủ dữ liệu; ưu tiên tháng tệ nhất rồi tài sản cuối. Chọn riêng từng mức vốn và đồng thời chọn nguồn tín hiệu / gói thoát. Gói 12h / 2ATR có thể đóng lỗ.</p>{table(['Nguồn và danh nghĩa','Kỳ chọn','06–08/2026','Cả năm','Số vị thế cả năm','DD cả năm'],rows)}</section>
<section class="panel"><h2>Tài sản và lợi nhuận từng tháng</h2><div class="filters"><label>Cấu hình<select id="strategy">{options}</select></label><label>Kỳ<select id="window">{periods}</select></label><label>Chi phí<select id="cost"><option value="stress">Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Đường tài sản bao gồm vị thế mở"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><div class="scroll"><table><thead>{tr(['Chi phí','Ứng viên','Vị thế vào','Vị thế TB','Vốn giữ chỗ TB','Vốn giữ chỗ đỉnh','Lần thiếu vốn','Thời gian khóa','Ròng đã đóng','Đóng góp còn mở','Thoát 2ATR','Thoát 12h','Lãi/lỗ giá sau trượt','Phí','Funding'])}</thead><tbody id="capitalBody"></tbody></table></div><p>Vốn giữ chỗ gồm ký quỹ theo Mark, các phần chưa khớp và phí dự kiến; không phải giới hạn lỗ. Tài sản cuối = 500 + ròng đã đóng + đóng góp còn mở, đã tính funding và phí. Lãi/lỗ giá sau trượt đã gồm vị thế mở; trừ phí và cộng funding bằng thay đổi tài sản. Hai mức chi phí có thể nhận các vị thế khác nhau, nên không phải cùng một chuỗi lệnh chỉ trừ thêm phí.</p></section>
<section class="panel"><h2>Độ ổn định qua 10 mốc ba tháng</h2><p>Mỗi kỳ khởi chạy riêng với 500 USDT; từ 09/2025 đến 06/2026. Chỉ bốn quý không chồng lấn. Đường không hoàn tất vẫn ở mẫu số; số dư tệ nhất chỉ tính đường hoàn tất. Không coi các cửa sổ này là các mẫu tương lai độc lập.</p>{table(['Cấu hình','Kỳ có lời','Tài sản tệ nhất','DD lớn nhất','Quý có lời'],rolling)}</section>
<section class="panel"><h2>Quy tắc và đối soát</h2>{strategy_notes}<p>{escape(audit)}</p></section><section class="panel"><h2>Giới hạn</h2><p>Phí / trượt mỗi lần khớp: cơ sở 0,05% / 0,20%; cao 0,10% / 0,50%. Funding thực, toàn bộ vị thế mở tính theo thị trường. Tập 30 coin cố định có thiên lệch sống sót; dùng bộ lọc sàn hiện tại, maintenance proxy 1%, giá 5 phút và chưa có sổ lệnh lịch sử. Chưa chứng minh khả năng khớp và thanh lý thực. Chưa đạt mục tiêu 50% mỗi tháng; chưa bật live.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">Mọi kết quả</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc khóa</a> · <a href="paired_effect.json">So với đối chứng</a></p></section></main><script>{script}</script></body></html>'''
    (OUT/'dashboard.html').write_text(html,encoding='utf-8')
    md=['# Long/Short theo biến động và khối lượng 1 giờ','',target,'',*findings,'','Cặp số cơ sở / chi phí cao. Tổng danh nghĩa của cả ba phần; không phải mỗi phần.',
        '|Cấu hình|Kỳ chọn|06–08|Cả năm|Số vị thế|DD|','|---|---:|---:|---:|---:|---:|',*['| '+' | '.join(r)+' |' for r in rows],'',audit,'',s['protocol']['limitations']]
    (OUT/'report.md').write_text('\n'.join(md),encoding='utf-8')
    write(OUT/'findings.json',dict(target=target,findings=findings))
    write(OUT/'goal_progress.json',dict(classification='progress',goal_status='active',achieved=False,runs=len(s['results']),target_passes=s['target_met_rows'],evidence=findings,live_config_unchanged=True))
    assert sha(ROOT/'configs/live.yaml')==s['protocol']['live_config_sha256']
    print(OUT/'dashboard.html')


if __name__=='__main__':main()
