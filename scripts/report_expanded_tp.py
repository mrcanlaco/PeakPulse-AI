"""Render broad TP search without presenting retrospective maxima as proven edge."""

from __future__ import annotations

import json
from html import escape

import pandas as pd
from plotly.offline import get_plotlyjs
from search_expanded_tp import OUT


def rank(f):
    v = f["validation"]
    return (
        not f["diagnostic_passed"],
        not v["complete"],
        -(v["worst_pnl"] if v["complete"] else -1e9),
        f["strategy_id"],
    )


def interval(r, field="pnl", equity=False):
    if not r["complete"]:
        return "Chưa xác định"
    add = 500 if equity else 0
    return f"{add + r['worst_' + field]:.2f}–{add + r['best_' + field]:.2f}"


def main():
    s = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    final = sorted(s["finalists"], key=rank)
    development = {
        coin: json.loads((OUT / f"development_{coin}.json").read_text(encoding="utf-8"))
        for coin in ["all_coins", "no_ake"]
    }
    rows = [r for r in s["results"] if r["window"] != "development"]
    curves = {}
    for r in rows:
        if r["window"] != "full":
            continue
        frame = pd.read_parquet(OUT / "runs" / f"{r['id']}_equity.parquet")
        if frame.empty:
            curves[r["id"]] = dict(x=[], y=[])
            continue
        groups = frame.groupby(frame["at"] // 86400000)
        indices = sorted(
            set(groups.equity.idxmin())
            | set(groups.equity.idxmax())
            | {0, len(frame) - 1}
        )
        thin = frame.loc[indices]
        curves[r["id"]] = dict(x=thin["at"].tolist(), y=thin.equity.tolist())
    defaults = {}
    for coin in ["all_coins", "no_ake"]:
        pool = [f for f in final if f["coins"] == coin and f["shortlisted"]]
        defaults[coin] = (
            pool[0]["strategy_id"]
            if pool
            else next(f["strategy_id"] for f in final if f["coins"] == coin)
        )
    payload = json.dumps(
        dict(
            finalists=final,
            rows=rows,
            curves=curves,
            defaults=defaults,
            development=development,
        ),
        ensure_ascii=False,
        allow_nan=False,
    ).replace("</", "<\\/")
    pass_count = s["diagnostic_pass_count"]
    note = (
        f"{pass_count} phương án/kịch bản đạt ngưỡng nghiên cứu trong bộ kiểm tra này. Đây vẫn là lịch sử đã xem trước, chưa phải bằng chứng giao dịch thật."
        if pass_count
        else "Chưa phương án nào đạt đủ tiêu chí nghiên cứu ở giai đoạn sau và toàn kỳ. Không chọn cấu hình chạy thật chỉ vì một kết quả có lãi."
    )
    html = """<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Mở rộng TP và chiến lược</title>
<style>body{font:15px Segoe UI,Arial;background:#0b1525;color:#e2e8f0;max-width:1540px;margin:auto;padding:26px}h1{font-size:30px}h2{font-size:21px}p{color:#b9c9df;line-height:1.7}.note{background:#34252a;border:1px solid #895c60;padding:17px;border-radius:12px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}.card,.panel{border:1px solid #30465f;background:#111f33;border-radius:12px;padding:18px}.card strong{display:block;font-size:28px;margin-top:8px}.panel{margin:20px 0}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}td,th{padding:11px;border-bottom:1px solid #30465f;text-align:right}td:first-child,th:first-child{text-align:left}select{background:#1a2d46;color:#fff;padding:10px;max-width:100%;border:1px solid #50677f;border-radius:7px}.pos{color:#65e6bf}.neg{color:#ff9393}a{color:#7dd3fc}#chart{height:430px}.foot{font-size:13px}summary{cursor:pointer}@media(max-width:700px){body{padding:12px}.cards{grid-template-columns:1fr 1fr}}</style>
<h1>Nới TP giúp tăng lãi hay chỉ giữ lệnh lâu hơn?</h1><p>500 USDT · Cross x5 · Khoảng 25 USDT danh nghĩa/lệnh · 24/06–24/09/2026</p>
<div class="note">__NOTE__<p>Giữ nguyên tài khoản thật; TP trên 5 USDT chỉ thử trong mô phỏng. Bỏ AKE là giả định biết trước coin cần tránh, không phải mô phỏng xử lý bằng tay.</p></div>
<div class="cards"><div class="card">Cấu hình<strong>660</strong></div><div class="card">Kịch bản coin<strong>2</strong></div><div class="card">Lượt mô phỏng<strong>__RUNS__</strong></div><div class="card">Đạt ngưỡng nghiên cứu<strong>__PASS__</strong></div></div>
<label>Kịch bản <select id="coins"><option value="no_ake">Bỏ toàn bộ AKE</option><option value="all_coins">Giữ toàn bộ coin, có AKE</option></select></label>
<section class="panel"><h2>Kết luận cho kịch bản đang xem</h2><p id="conclusion"></p><p>Khoảng kết quả là bốn giả định khớp/chi phí, không phải khoảng tin cậy. Tài sản cuối đã tính phí, funding và định giá vị thế còn mở. “Chưa xác định” nghĩa là mô phỏng không hoàn tất; xem lý do ở bảng chi tiết.</p></section>
<section class="panel"><h2>Chỉ thay TP: không stop-loss, tối đa 5 vị thế</h2><p>Giữ nguyên tín hiệu gốc và khóa mở mới tại DD 20%. Bảng này giúp tách ảnh hưởng của TP khỏi các biến khác. Với dòng chưa xác định, DD, số lệnh và thời gian giữ chỉ đo đến lúc mô phỏng dừng; DD thấp ở những dòng này không chứng minh ít rủi ro.</p><div class="scroll"><table><thead><tr><th>TP</th><th>Tài sản cuối toàn kỳ</th><th>DD lớn nhất</th><th>Lệnh vào</th><th>Còn mở</th><th>Giữ lâu nhất</th><th>Tài sản kỳ kiểm tra riêng</th></tr></thead><tbody id="tpgrid"></tbody></table></div></section>
<section class="panel"><h2>Ứng viên chọn từ giai đoạn đầu</h2><p>Chọn trên 24/06–29/07, khóa danh sách rồi kiểm tra 29/07–08/09. Mỗi kỳ độc lập bắt đầu từ 500 USDT; toàn kỳ là tài khoản chạy liên tục.</p><div class="scroll"><table><thead><tr><th>Phương án</th><th>Tài sản kỳ kiểm tra</th><th>Tài sản toàn kỳ</th><th>DD toàn kỳ lớn nhất</th><th>Lệnh đóng kỳ kiểm tra (ít nhất)</th><th>Đạt ngưỡng</th></tr></thead><tbody id="ranking"></tbody></table></div></section>
<section class="panel"><h2>Xem từng phương án và giả định</h2><label>Phương án <select id="strategy"></select></label><div id="chart"></div><p class="foot">Biểu đồ giữ cực trị từng ngày để dễ xem; số đo tính trên từng bước 5 phút. Đường dừng ở điểm mất điều kiện tiếp tục. Đường ngang 500 USDT là giữ tiền trong mô phỏng.</p><div class="scroll"><table><thead><tr><th>Khớp / chi phí</th><th>Tài sản cuối</th><th>PnL</th><th>DD</th><th>Vào / đóng / mở</th><th>Phí</th><th>Funding</th><th>Giữ lâu nhất</th><th>Trạng thái</th></tr></thead><tbody id="detail"></tbody></table></div><h3>Ba đoạn kiểm tra độc lập</h3><p>Mỗi đoạn bắt đầu lại từ 500 USDT; dùng chi phí cơ sở. Không cộng các cột để thay cho tài khoản liên tục.</p><div class="scroll"><table><thead><tr><th>Khớp TP</th><th>PnL 29/07–12/08</th><th>PnL 12/08–26/08</th><th>PnL 26/08–08/09</th></tr></thead><tbody id="slices"></tbody></table></div></section>
<section class="panel"><h2>Phạm vi và giới hạn</h2><p>TP cố định 0,5/1/2/3/5/8/10/15 USDT; TP 2 ATR trần 5 hoặc 10 USDT; 4 ATR trần 10 USDT. Sáu cách thoát: không SL/không hạn giữ; không SL/giữ 168h; SL 2,5/5/10 USDT; SL 5 USDT + giữ 72h + đóng danh mục DD10%. Giới hạn 1/3/5/10/không giới hạn số vị thế; hai bộ lọc tín hiệu gốc hoặc nến đã giảm. Mọi trường hợp vẫn kiểm tra vốn khả dụng, không DCA và không tăng vốn mỗi lệnh.</p><p>Bốn trường hợp: khớp theo đóng nến hoặc chạm giá TP; phí mỗi chiều 0,05%/0,10% và trượt giá 0,20%/0,50%. Chạm giá chưa chứng minh đã khớp. Khi cùng bước có rủi ro và TP, ưu tiên xử lý rủi ro; thứ tự trong nến chưa xác minh.</p><p>Chọn tối đa 10 ứng viên mỗi kịch bản bằng PnL xấu nhất giai đoạn đầu, yêu cầu đủ 4 kết quả, DD dưới 20%, ít nhất 10 lệnh đóng mỗi trường hợp. Ngoài ra kiểm tra mọi mức TP không SL tại 1/5/không giới hạn vị thế, kể cả phương án kém. Ngưỡng nghiên cứu: cả 4 trường hợp kỳ kiểm tra và toàn kỳ đều lãi, DD dưới 20%, ít nhất 20 lệnh đóng mỗi trường hợp kỳ kiểm tra. Đây không phải điều kiện đủ để bật live.</p><p>Tín hiệu chỉ đến hết 07/09; sau đó quản lý lệnh cũ. Lịch sử đã được xem trước, model huấn luyện đến 28/07 và đóng băng 06/09: không phải tập ngoài mẫu độc lập, chưa điều chỉnh thống kê cho việc thử nhiều tham số. MMR giả định 1%, bộ lọc sàn không theo từng thời điểm, chưa xác minh đầy đủ coin hủy niêm yết. Stop chỉ quan sát mỗi 5 phút nên lỗ thực tế có thể vượt ngưỡng.</p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">Toàn bộ số đo</a> · <a href="shortlist_lock.json">Danh sách đã khóa</a> · <a href="protocol.json">Tham số nghiên cứu</a></section>
<details class="panel"><summary>660 cấu hình ở giai đoạn tìm kiếm của kịch bản đang xem</summary><div class="scroll"><table><thead><tr><th>Phương án</th><th>PnL xấu nhất</th><th>DD lớn nhất</th><th>Ít nhất số lệnh đóng</th></tr></thead><tbody id="development"></tbody></table></div></details>
<script>__PLOTLY__</script><script>
const D=__DATA__;const el=id=>document.getElementById(id);const f=(x,n=2)=>x===null||x===undefined?'—':x.toLocaleString('vi-VN',{minimumFractionDigits:n,maximumFractionDigits:n});const range=r=>r.complete?f(500+r.worst_pnl)+'–'+f(500+r.best_pnl):'Chưa xác định';const sg=x=>x===null?'—':(x>0?'+':'')+f(x);const cls=x=>x===null?'':x>=0?'pos':'neg';const caseName=r=>(r.fill==='close'?'Đóng nến':'Chạm giá')+' / '+(r.cost==='base'?'cơ sở':'cao');const getRows=(id,w)=>D.rows.filter(r=>r.coins===el('coins').value&&r.strategy_id===id&&r.window===w);const span=(rows,k)=>Math.min(...rows.map(r=>r[k]))+'–'+Math.max(...rows.map(r=>r[k]));
function updateCoin(){const coin=el('coins').value;let finals=D.finalists.filter(r=>r.coins===coin);let candidates=finals.filter(r=>r.shortlisted);let best=candidates[0];let fullBest=finals.filter(r=>r.full.complete).sort((a,b)=>b.full.worst_pnl-a.full.worst_pnl)[0];el('conclusion').textContent=`${finals.filter(r=>r.diagnostic_passed).length} phương án đạt ngưỡng nghiên cứu. `+(best?`Ứng viên đứng đầu theo mức lãi/lỗ thấp nhất kỳ kiểm tra: ${best.spec.label}. Tài sản kỳ kiểm tra ${range(best.validation)} USDT; toàn kỳ ${range(best.full)} USDT.`:'Không đủ ứng viên đạt điều kiện chọn ban đầu.')+(fullBest?` Xét riêng toàn kỳ, xếp theo lợi nhuận ở giả định kém nhất thì phương án đứng đầu là ${fullBest.spec.label}: ${range(fullBest.full)} USDT, DD lớn nhất ${f(100*fullBest.full.worst_dd)}%. Kỳ kiểm tra riêng: ${range(fullBest.validation)} USDT. Đây là xếp hạng hồi cứu trong các phương án được kiểm tra tiếp.`:'');el('ranking').innerHTML=candidates.map(r=>`<tr><td>${r.spec.label}</td><td>${range(r.validation)}</td><td>${range(r.full)}</td><td>${f(100*r.full.worst_dd)}%</td><td>${r.validation.min_closed}</td><td>${r.diagnostic_passed?'Có':'Không'}</td></tr>`).join('');let anchors=finals.filter(r=>r.spec.anchor&&r.spec.cap===5).sort((a,b)=>(a.spec.policy.fixed_tp_usdt??100+a.spec.settings.atr_multiplier)-(b.spec.policy.fixed_tp_usdt??100+b.spec.settings.atr_multiplier));el('tpgrid').innerHTML=anchors.map(r=>{const rr=getRows(r.strategy_id,'full');return `<tr><td>${r.spec.label.split(' · ')[0]}</td><td>${range(r.full)}</td><td>${f(100*r.full.worst_dd)}%</td><td>${span(rr,'entries')}</td><td>${span(rr,'open_count')}</td><td>${f(r.full.max_hold_days,1)} ngày</td><td>${range(r.validation)}</td></tr>`}).join('');el('strategy').innerHTML=finals.map(r=>`<option value="${r.strategy_id}">${r.shortlisted?'Ứng viên: ':'Đối chiếu TP: '}${r.spec.label}</option>`).join('');el('strategy').value=D.defaults[coin];let dev=[...D.development[coin]].sort((a,b)=>(b.worst_pnl??-1e9)-(a.worst_pnl??-1e9));el('development').innerHTML=dev.map(r=>`<tr><td>${r.spec.label}</td><td>${sg(r.worst_pnl)}</td><td>${f(100*r.worst_dd)}%</td><td>${r.min_closed}</td></tr>`).join('');updateStrategy();}
function errorName(r){if(r.ending_equity!==null)return 'Hoàn tất';if(r.errors.some(e=>e.startsWith('maintenance_proxy')))return 'Vượt ngưỡng ký quỹ giả định';if(r.errors.some(e=>e.includes('tp')||e.includes('take_profit')))return 'Không thể biểu diễn TP';return 'Không hoàn tất: '+r.errors.join('; ');}
function updateStrategy(){const id=el('strategy').value, rows=getRows(id,'full');el('detail').innerHTML=rows.map(r=>`<tr><td>${caseName(r)}</td><td>${f(r.ending_equity)}</td><td class="${cls(r.pnl)}">${sg(r.pnl)}</td><td>${f(r.max_drawdown*100)}%</td><td>${r.entries} / ${r.exits} / ${r.open_count}</td><td>${f(r.fees)}</td><td>${sg(r.funding)}</td><td>${f(r.max_hold_days,1)} ngày</td><td>${errorName(r)}</td></tr>`).join('');Plotly.react('chart',rows.map(r=>({x:D.curves[r.id].x,y:D.curves[r.id].y,name:caseName(r),type:'scatter',mode:'lines'})),{paper_bgcolor:'#111f33',plot_bgcolor:'#111f33',font:{color:'#b9c9df'},margin:{l:60,r:20,t:10,b:80},xaxis:{type:'date',gridcolor:'#2d415b'},yaxis:{title:'USDT',gridcolor:'#2d415b'},legend:{orientation:'h',y:-.2},shapes:[{type:'line',xref:'paper',x0:0,x1:1,y0:500,y1:500,line:{color:'#ccb786',dash:'dot',width:1}}]},{responsive:true,displaylogo:false});el('slices').innerHTML=['close','bar_low'].map(fill=>`<tr><td>${fill==='close'?'Đóng nến':'Chạm giá'}</td>${['v1','v2','v3'].map(w=>{let r=getRows(id,w).find(x=>x.fill===fill);return `<td class="${cls(r.pnl)}">${sg(r.pnl)}</td>`}).join('')}</tr>`).join('');}
el('coins').onchange=updateCoin;el('strategy').onchange=updateStrategy;updateCoin();</script></html>"""
    for key, value in dict(
        NOTE=escape(note),
        RUNS=str(s["runs"]),
        PASS=str(pass_count),
        PLOTLY=get_plotlyjs(),
        DATA=payload,
    ).items():
        html = html.replace(f"__{key}__", value)
    (OUT / "dashboard.html").write_text(html, encoding="utf-8")
    md = [
        "# Mở rộng TP và tìm chiến lược — 24/09/2026",
        "",
        note,
        "",
        f"660 cấu hình × 2 kịch bản coin; {s['runs']} lượt chạy. Vốn 500 USDT, Cross x5, khoảng 25 USDT danh nghĩa mỗi vị thế. Không đổi cấu hình thật. Khoảng số là 4 giả định khớp/chi phí, không phải khoảng tin cậy.",
        "",
        "Lịch tìm kiếm: 24/06–29/07; kỳ kiểm tra: 29/07–08/09; tài khoản liên tục: 24/06–24/09. Tín hiệu chỉ đến hết 07/09.",
    ]
    for coin in ["no_ake", "all_coins"]:
        md += [
            "",
            f"## {'Bỏ AKE hồi cứu' if coin == 'no_ake' else 'Giữ tất cả coin'}",
            "",
            "| Ứng viên | Tài sản kỳ kiểm tra | Tài sản toàn kỳ | DD toàn kỳ lớn nhất | Lệnh đóng kỳ kiểm tra ít nhất | Đạt ngưỡng |",
            "|---|---:|---:|---:|---:|---|",
        ]
        for r in final:
            if r["coins"] == coin and r["shortlisted"]:
                md.append(
                    f"| {r['spec']['label']} | {interval(r['validation'], equity=True)} | {interval(r['full'], equity=True)} | {100 * r['full']['worst_dd']:.2f}% | {r['validation']['min_closed']} | {r['diagnostic_passed']} |"
                )
        md += [
            "",
            "### Chỉ thay TP, không SL, tối đa 5 vị thế",
            "",
            "| TP | Tài sản toàn kỳ | DD lớn nhất | Giữ lâu nhất | Tài sản kỳ kiểm tra |",
            "|---|---:|---:|---:|---:|",
        ]
        for r in sorted(
            final,
            key=lambda f: (
                f["spec"]["policy"].get("fixed_tp_usdt", 100),
                f["strategy_id"],
            ),
        ):
            if r["coins"] == coin and r["spec"]["anchor"] and r["spec"]["cap"] == 5:
                md.append(
                    f"| {r['spec']['label'].split(' · ')[0]} | {interval(r['full'], equity=True)} | {100 * r['full']['worst_dd']:.2f}% | {r['full']['max_hold_days']:.1f} ngày | {interval(r['validation'], equity=True)} |"
                )
    md += [
        "",
        "## Cách đánh giá và giới hạn",
        "",
        s["protocol"]["selection"],
        "",
        s["protocol"]["gate"],
        "",
        s["protocol"]["exclusion"],
        "",
        s["protocol"]["limitations"],
        "",
        "Tất cả trường hợp vẫn ghi nhận phí, funding và vị thế chưa đóng. Không xóa lệnh lỗ hoặc giả định phần can thiệp bằng tay có PnL bằng 0. Bảng xếp hạng ứng viên theo giai đoạn sau cũng chỉ phục vụ nghiên cứu; kết quả cao nhất lịch sử không chứng minh chiến lược tối ưu cho tương lai.",
    ]
    (OUT / "report.md").write_text("\n".join(md), encoding="utf-8")
    print(OUT / "dashboard.html")


if __name__ == "__main__":
    main()
