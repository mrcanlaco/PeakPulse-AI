"""Vietnamese finite-account versus isolated-event diagnostic dashboard."""
from collections import Counter
from html import escape
import json
import xml.etree.ElementTree as ET
import pandas as pd
from diagnose_signal_opportunities import OUT, read, statistics
from compare_account_risk import ROOT, write, sha

LABELS=dict(short='Chỉ Short · điểm gốc',long='Chỉ Long · đảo chiều',both='Long + Short · đảo chiều',short_impulse='Chỉ Short · ưu tiên động lượng/ATR')
REASONS=dict(accepted='Được vào',same_coin='Coin đang có vị thế',full_capacity='Hết chỗ',drawdown_paused='Đã dừng mở mới vì DD',exchange_minimum_or_precision='Không đạt quy tắc sàn',target_below_minimum='TP dự kiến quá nhỏ')


def main():
    s=read(OUT/'summary.json'); v=read(OUT/'verification.json'); outcomes=read(OUT/'outcomes.json')
    tests=ET.parse(OUT/'unit_tests.xml').getroot().findall('.//testcase')
    assert len(tests)==28 and not ET.parse(OUT/'unit_tests.xml').getroot().findall('.//failure')
    assert not ET.parse(OUT/'unit_tests.xml').getroot().findall('.//error')
    num=lambda x:'—' if x is None else f'{x:.2f}'
    tr=lambda xs:'<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in xs)+'</tr>'
    table=lambda heads,rows:'<div class="scroll"><table><thead><tr>'+''.join('<th>'+escape(h)+'</th>' for h in heads)+'</tr></thead><tbody>'+''.join(tr(r) for r in rows)+'</tbody></table></div>'
    look={(r['strategy'],r['window'],r['cost']):r for r in s['portfolios']}
    overall=[]
    for r in s['isolated']:
        n=r['evaluated_entries']; states=r['states']
        overall.append([r['side'],'Cơ sở' if r['cost']=='base' else 'Cao',r['events'],n,states.get('not_entered',0),states.get('incomplete',0),states.get('closed',0),states.get('open',0),
            f"{100*r['positive_mtm']/n:.1f}%" if n else '—',num(r['mean_net_usdt']),num(r['p05_net_usdt']),num(r['worst_net_usdt']),r['open_over30days']])
    comparisons=[]
    for st,label in LABELS.items():
        year=[look[(st,'year',c)] for c in ['base','stress']]; later=[look[(st,'later',c)] for c in ['base','stress']]
        comparisons.append([label,' / '.join(num(r['ending_equity']) for r in year),
            ' / '.join(f"{r['max_drawdown']*100:.2f}%" for r in year),' / '.join(str(r['entries']) for r in year),
            ' / '.join(num(r['ending_equity']) for r in later)])
    series=[]
    for pr in s['portfolios']:
        curve=pd.read_parquet(OUT/'portfolios'/f'{pr["id"]}_equity.parquet'); raw=read(OUT/'portfolios'/f'{pr["id"]}.json')
        ix={0,len(curve)-1}
        for _,g in curve.groupby((curve['at']-curve['at'].iloc[0])//86400000): ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(pr,strategy_id=pr['strategy'],open_count=len(raw['open_positions']),paused=raw['entry_paused'],
            side_entries=dict(Counter(j['side'] for j in raw['journal'] if j['kind']=='entry')),
            utilization=dict(open_hold_max_days=max((p['held_days'] for p in raw['open_positions']),default=None)),
            points=[[int(r['at']),round(r.equity,6)] for _,r in curve.loc[sorted(ix)].iterrows()]))
    write(OUT/'dashboard_data.json',series)
    cohort=[]
    for month in pd.date_range('2025-09-01','2026-08-01',freq='MS',tz='UTC'):
        for side in ['LONG','SHORT']:
            rs=[r for r in outcomes if r['side']==side and r['cost']=='base' and month.value//1000000<=r['at']<(month+pd.DateOffset(months=1)).value//1000000]
            a=statistics(rs)
            cohort.append([month.strftime('%Y-%m'),side,a['events'],a['evaluated_entries'],a['states'].get('closed',0),a['states'].get('open',0),num(a['mean_net_usdt'])])
    lifecycle=[]
    for side in ['LONG','SHORT']:
        for state,label in [('closed','Đã đóng'),('open','Còn mở')]:
            rs=[r for r in outcomes if r['cost']=='base' and r['side']==side and r['state']==state]
            lifecycle.append([side,label,len(rs),sum(r['net_mtm']>0 for r in rs),num(sum(r['net_mtm'] for r in rs)/len(rs))])
    worst=min((r for r in outcomes if r['cost']=='base' and r['net_mtm'] is not None),key=lambda r:r['net_mtm'])
    tail=(f"Lệnh riêng lẻ tệ nhất là {worst['side']} {worst['symbol']}, vào {pd.Timestamp(worst['at'],unit='ms',tz='UTC').strftime('%d/%m/%Y %H:%M UTC')}, "
        f"giữ {worst['held_days']:.2f} ngày, trạng thái {worst['state']}, lãi/lỗ ròng {worst['net_mtm']:.2f} USDT; "
        f"funding {worst['funding']:.2f} USDT. Trailing theo giá có thể thoát khi giá thuận nhưng vẫn lỗ ròng sau funding. "
        "Đây là một ví giả định riêng, không phải một khoản lỗ phát sinh trên tài khoản thật.")
    base=next(r for r in s['isolated'] if r['side']=='SHORT' and r['cost']=='base')
    long=next(r for r in s['isolated'] if r['side']=='LONG' and r['cost']=='base')
    both=look[('both','year','base')]; short=look[('short','year','base')]
    finding=(f"Trong tài khoản chung, phối hợp đảo chiều Long + Short chỉ nhận {both['entries']}/{both['decisions']} tín hiệu, "
        f"kết thúc {both['ending_equity']:.2f} USDT; {both['admission_counts'].get('drawdown_paused',0)} tín hiệu bị chặn khi đã dừng mở mới vì giảm tài sản. "
        f"Chỉ Short nhận {short['entries']} lệnh, kết thúc {short['ending_equity']:.2f} USDT. Đây là cơ chế cụ thể khiến thêm hướng giao dịch không tự làm tăng lợi nhuận.")
    diagnostic=(f"Khi mỗi tín hiệu có ví giả định riêng, Short có {base['evaluated_entries']} lệnh đủ điều kiện, "
        f"lãi/lỗ trung bình đến cuối kỳ {base['mean_net_usdt']:.2f} USDT/lệnh, {base['states'].get('open',0)} còn mở; "
        f"Long có {long['evaluated_entries']} lệnh, trung bình {long['mean_net_usdt']:.2f} USDT/lệnh, {long['states'].get('open',0)} còn mở. "
        "Số này đã tính phí, funding và lỗ mở, nhưng không phải lợi suất tài khoản. Thời gian quan sát khác nhau; các lệnh chồng lấn, dùng nhiều ví độc lập và có thể giữ vốn nhiều tháng.")
    old=(ROOT/'artifacts/signal_priority_20260925/dashboard.html').read_text(encoding='utf-8')
    style=old.split('<style>',1)[1].split('</style>',1)[0]
    script=old.split('<script>',1)[1].split('</script>',1)[0]
    script='const spans='+json.dumps(s['protocol']['windows'])+script[script.index(',labels='):]
    script+='''
const groups=__GROUPS__,reasons=__REASONS__;
const originalRender=render;render=function(){originalRender();const st=document.querySelector('#strategy').value,w=document.querySelector('#window').value,c=document.querySelector('#cost').value;
document.querySelector('#groupBody').innerHTML=groups.filter(g=>g.portfolio===w+'_base_'+st||(c==='stress'&&g.portfolio===w+'_stress_'+st)).map(g=>`<tr><td>${g.portfolio.includes('_base_')?'Cơ sở':'Cao'}</td><td>${g.side}</td><td>${reasons[g.category]??g.category}</td><td>${g.events}</td><td>${g.evaluated_entries}</td><td>${g.states.open??0}</td><td>${num(g.mean_net_usdt)}</td><td>${num(g.p05_net_usdt)}</td><td>${g.snapshot_any_loser_older30d}</td></tr>`).join('');};
'''.replace('__GROUPS__',json.dumps(s['groups'],ensure_ascii=False)).replace('__REASONS__',json.dumps(REASONS,ensure_ascii=False))
    # Listeners already hold originalRender: refresh the admission table too.
    script+="for(const id of ['strategy','window','cost'])document.querySelector('#'+id).addEventListener('change',()=>render());"
    options=''.join(f'<option value="{k}"'+(' selected' if k=='both' else '')+'>'+escape(label)+'</option>' for k,label in LABELS.items())
    audit=(f"28 kiểm thử đạt; {v['totals']['exact_controls']} đường tài khoản khớp toàn bộ kết quả cũ; "
        f"{v['totals']['decisions']:,} quyết định được kiểm tra trạng thái vị thế; "
        f"{v['totals']['journals']:,} sổ đối soát, {v['totals']['funding']:,} khoản funding, "
        f"{v['totals']['fills']:,} lần khớp và {v['totals']['states']:,} mốc tài sản được tái dựng. "
        f"Chạy lại độc lập {v['totals']['replayed_singletons']} đường đơn lẻ khớp đầy đủ. Đây không phải số mẫu thị trường độc lập.")
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Tín hiệu và chỗ bị giữ</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / LONG & SHORT · CHẨN ĐOÁN LƯỢT 23</div><h1>Thêm tín hiệu, nhưng tài khoản có vào được không?</h1><p class="muted">01/09/2025 → 01/09/2026 UTC · 500 USDT · Cross x5 · tổng 25 USDT/vị thế · 3 phần · trailing 3 ATR / 1%</p>
<div class="notice"><b>Chưa đạt mục tiêu 50% từng tháng. Chưa bật live.</b><p>__FINDING__</p></div>
<div class="cards"><div class="card">Tín hiệu trong kỳ<strong>920</strong></div><div class="card">Long / Short<strong>462 / 458</strong></div><div class="card">Đường tài khoản đối chứng<strong>16</strong></div><div class="card">Ví riêng × 2 mức chi phí<strong>1.840</strong></div></div>
<section class="panel"><h2>Tài khoản chung: kết quả vẫn tính mọi vị thế chưa đóng</h2><p>Cặp số là cơ sở / chi phí cao. Mỗi cửa sổ khởi chạy riêng 500 USDT. Đây là các cấu hình đã khóa từ lượt trước, được chạy lại để giải thích nguyên nhân; không chọn một chiến lược mới theo kết quả lần này.</p>__COMPARISONS__</section>
<section class="panel"><h2>Đường tài sản và lý do bỏ qua tín hiệu</h2><div class="filters"><label>Chiến lược<select id="strategy">__OPTIONS__</select></label><label>Kỳ<select id="window"><option value="year">Cả năm 09/2025–08/2026</option><option value="later">3 tháng 06–08/2026</option></select></label><label>Chi phí<select id="cost"><option value="stress">Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản tài khoản chung"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div>
<h3>Nếu xét riêng từng tín hiệu đã nhận/bỏ qua</h3><p>Mỗi sự kiện trong bảng sau có một ví giả định riêng. “Đủ điều kiện” chỉ gồm những lệnh vượt quy tắc sàn/TP và có kết quả đầy đủ; lệnh không thể vào vẫn giữ trong cột tín hiệu. Lãi/lỗ TB gồm cả lỗ đang mở, không phải tiền tài khoản đã bỏ lỡ. Nhóm có thể khác nhau về thời điểm, coin và thời gian theo dõi.</p><div class="scroll"><table><thead><tr><th>Chi phí</th><th>Hướng</th><th>Quyết định trong tài khoản</th><th>Tín hiệu</th><th>Đủ điều kiện riêng</th><th>Còn mở riêng</th><th>Lãi/lỗ TB USDT</th><th>Phân vị 5%</th><th>Khi đó có lệnh lỗ &gt;30 ngày</th></tr></thead><tbody id="groupBody"></tbody></table></div><p>Nhóm “coin đang có vị thế” được ưu tiên phân loại khi đồng thời hết chỗ. Kiểm tra vị thế ngay trước từng tín hiệu, kể cả lệnh đã nhận trước đó trong cùng thời điểm. Không tự thử lại tín hiệu bị bỏ.</p></section>
<section class="panel"><h2>Chẩn đoán riêng toàn bộ 920 tín hiệu</h2><p>__DIAGNOSTIC__</p>__ISOLATED__<p>Tỷ lệ dương tính trên mọi lệnh đủ điều kiện, gồm cả vị thế đang mở. Phân vị 5% và lệnh tệ nhất giúp thấy phần đuôi lỗ. Vị thế mở chỉ định giá, chưa trừ một khoản phí thoát giả định ở cuối kỳ; không giả vờ đã đóng. Không được cộng các ví riêng thành lợi nhuận của một tài khoản hữu hạn.</p></section>
<section class="panel"><h2>Chốt lời và lỗ đang treo</h2><p>Chỉ chi phí cơ sở, ví riêng từng tín hiệu. Đếm riêng lệnh đóng sẽ che mất những lệnh lỗ vẫn đang giữ.</p>__LIFECYCLE__<p>__TAIL__</p></section>
<section class="panel"><h2>Tháng xuất hiện tín hiệu và thời gian theo dõi</h2><p>Chỉ chi phí cơ sở. Lệnh đầu kỳ được quan sát lâu hơn lệnh cuối kỳ; “còn mở” là quan sát chưa kết thúc, không phải thua/lãi đã chốt. Tất cả kết thúc định giá ngày 01/09/2026. Trung bình trong bảng không phải lợi suất tháng.</p>__COHORT__</section>
<section class="panel"><h2>Kiểm chứng và giới hạn</h2><p>__AUDIT__</p><p>500 USDT riêng cho mỗi phép đo lẻ làm thay đổi ràng buộc tài khoản: không bị các coin khác chiếm chỗ, dùng vốn hoặc gây dừng mở mới. Việc hủy phần vào thêm sau DD có thể khác tài khoản chung. Bảng không chứng minh có thể thực hiện đồng thời mọi tín hiệu hay loại bỏ vị thế đang lỗ.</p><p>Dữ liệu lịch sử đã dùng nhiều lần; chưa phải mẫu tương lai độc lập. Bộ lọc sàn hiện tại, maintenance proxy 1%, thiếu bậc ký quỹ/sổ lệnh lịch sử và thiên lệch tập coin vẫn giới hạn kết luận. Trailing quan sát nến đóng 5 phút, khớp mở nến sau với trượt bất lợi. Phí/trượt cơ sở 0,05%/0,20%; cao 0,10%/0,50% mỗi lần khớp. Không SL, không tự đóng lỗ theo thời gian. Cấu hình tài khoản thật giữ nguyên.</p><p><a href="report.md">Báo cáo</a> · <a href="outcomes.csv">Toàn bộ kết quả riêng lẻ</a> · <a href="summary.json">Số liệu nhóm và tài khoản</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc đo</a></p></section>
</main><script>__SCRIPT__</script></body></html>'''
    compheads=['Cấu hình','Tài sản cả năm','DD cả năm','Vị thế đã vào','Tài sản 06–08']
    isoheads=['Hướng','Chi phí','Tín hiệu','Đủ điều kiện, đủ dữ liệu','Không vào','Thiếu kết quả','Đã đóng','Còn mở','MTM dương','TB USDT/lệnh','Phân vị 5%','Tệ nhất','Mở >30 ngày']
    for k,value in dict(STYLE=style,FINDING=escape(finding),DIAGNOSTIC=escape(diagnostic),OPTIONS=options,AUDIT=escape(audit),SCRIPT=script,
        COMPARISONS=table(compheads,comparisons),ISOLATED=table(isoheads,overall),COHORT=table(['Tháng tín hiệu','Hướng','Tín hiệu','Đủ điều kiện','Đóng','Mở','TB USDT/lệnh'],cohort),
        LIFECYCLE=table(['Hướng','Trạng thái','Số lệnh','Lãi/lỗ dương','TB USDT/lệnh'],lifecycle),TAIL=escape(tail)).items(): html=html.replace('__'+k+'__',value)
    (OUT/'dashboard.html').write_text(html,encoding='utf-8')
    md=['# Long/Short: hiệu quả tín hiệu và giới hạn tài khoản','',finding,'',diagnostic,'',
        'Cặp số cơ sở / chi phí cao; 500 USDT mỗi tài khoản, x5,25 USDT tổng danh nghĩa,3 phần,trailing3ATR/1%.',
        '| '+' | '.join(compheads)+' |','|'+'|'.join(['---']*len(compheads))+'|',*['| '+' | '.join(map(str,r))+' |' for r in comparisons],'',
        '## Ví giả định riêng từng sự kiện, không cộng thành tài khoản','| '+' | '.join(isoheads)+' |','|'+'|'.join(['---']*len(isoheads))+'|',*['| '+' | '.join(map(str,r))+' |' for r in overall],'',
        tail,'',audit,'',s['protocol']['limitations'],'','Không kích hoạt live. Mục tiêu 50% trong từng tháng chưa đạt.','',
        '[Dashboard](dashboard.html) · [Toàn bộ kết quả](outcomes.csv) · [Đối soát](verification.json)']
    (OUT/'report.md').write_text('\n'.join(md),encoding='utf-8')
    write(OUT/'findings.json',dict(finding=finding,diagnostic=diagnostic,tail=tail))
    write(OUT/'goal_progress.json',dict(classification='progress',goal_status='active',achieved=False,
        existing_portfolio_controls=16,isolated_diagnostics=len(outcomes),new_strategy_candidates=0,target_passes=0,
        evidence=finding+' '+diagnostic,next_steps=['Use admission and censored-lifecycle evidence to design a causal entry/exit intervention; keep shared account and all open losses.',
        'Any selected change needs a newly locked forward observation period; reused historical results cannot establish the monthly target.'],live_config_unchanged=True))
    assert sha(ROOT/'configs/live.yaml')==s['protocol']['live_config_sha256']
    print(OUT/'dashboard.html')


if __name__=='__main__':main()
