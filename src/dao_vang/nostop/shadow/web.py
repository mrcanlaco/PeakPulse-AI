"""Local dashboard for the shadows: stdlib HTTP server, one self-contained HTML page."""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .feed import BAR_MS
from .store import DATA_DIR, Store, describe_spec

STALE_AFTER_MS = BAR_MS + 10 * 60 * 1000


def _live_delta(state: dict, prices: dict) -> float:
    """PnL accrued since the last bar open, from the latest mark prices (display only)."""
    d = 0.0
    for p in state.get("positions", []):
        px = prices.get(p["symbol"])
        if px and p["open_price"] > 0:
            d += p["notional"] * (px / p["open_price"] - 1.0)
    return d


def overview(store: Store, now_ms: int | None = None) -> dict:
    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    system = store.read_json("system.json")
    pr = store.read_json("prices.json")
    prices = pr.get("prices", {})
    rows = []
    tot_eq = tot_cap = tot_day = 0.0
    n_pos = 0
    for sh in store.shadows():
        st = store.read_state(sh["id"])
        cap = float(sh["capital"])
        if st:
            live = _live_delta(st, prices) if sh["status"] == "running" else 0.0
            eq = st["equity"] + live
            pnl = eq - cap
            row = {
                "equity": round(eq, 2),
                "pnl": round(pnl, 2),
                "ret": pnl / cap,
                "pnl_today": round(st["pnl_today"] + live, 2),
                "max_dd": st["max_dd"],
                "n_positions": st["n_positions"],
                "gross": st["gross"],
                "net": st["net"],
                "days": st["days"],
                "asof_ts": st["asof_ts"],
                "error": st.get("error", ""),
                "stale": sh["status"] == "running" and now_ms - st["asof_ts"] > STALE_AFTER_MS,
            }
        else:
            row = {"equity": cap, "pnl": 0.0, "ret": 0.0, "pnl_today": 0.0, "max_dd": 0.0,
                   "n_positions": 0, "gross": 0.0, "net": 0.0, "days": 0.0, "asof_ts": 0,
                   "error": "", "stale": False}
        row.update({"id": sh["id"], "desc": describe_spec(sh["spec"]), "status": sh["status"], "capital": cap,
                    "start_ms": sh["start_ms"], "research": sh.get("research", {})})
        rows.append(row)
        if sh["status"] != "stopped":
            tot_eq += row["equity"]
            tot_cap += cap
            tot_day += row["pnl_today"]
            n_pos += row["n_positions"]
    by = {"running": 0, "paused": 0, "stopped": 0}
    for r in rows:
        by[r["status"]] += 1
    return {
        "now": now_ms,
        "counts": by,
        "totals": {"equity": round(tot_eq, 2), "capital": tot_cap,
                   "pnl": round(tot_eq - tot_cap, 2),
                   "ret": (tot_eq / tot_cap - 1.0) if tot_cap else 0.0,
                   "pnl_today": round(tot_day, 2), "positions": n_pos},
        "system": system,
        "prices_ts": pr.get("ts", 0),
        "shadows": rows,
    }


def detail(store: Store, sid: str) -> dict | None:
    sh = next((s for s in store.shadows() if s["id"] == sid), None)
    if sh is None:
        return None
    st = store.read_state(sid) or {}
    prices = store.read_json("prices.json").get("prices", {})
    for p in st.get("positions", []):
        px = prices.get(p["symbol"], p["open_price"])
        p["price"] = px
        p["upnl"] = round(p["notional"] * (px / p["open_price"] - 1.0), 2) if p["open_price"] > 0 else 0.0
        p["upnl_entry"] = (
            round(p["qty"] * (px - p["avg_entry"]), 2) if p.get("avg_entry") else 0.0
        )
    return {"shadow": sh, "state": st, "profile": store.read_profile(sid)}


class Handler(BaseHTTPRequestHandler):
    store: Store

    def log_message(self, format, *args):  # noqa: A002 - quiet access log
        return

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/":
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif path == "/api/overview":
            self._json(overview(self.store))
        elif m := re.fullmatch(r"/api/shadow/([A-Za-z0-9_\-\.]+)", path):
            d = detail(self.store, m.group(1))
            self._json(d, 200) if d else self._json({"error": "unknown shadow"}, 404)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):  # noqa: N802
        m = re.fullmatch(r"/api/shadow/([A-Za-z0-9_\-\.\*]+)/(pause|resume|stop)", self.path)
        if not m:
            return self._json({"error": "not found"}, 404)
        sid, action = m.groups()
        status = {"pause": "paused", "resume": "running", "stop": "stopped"}[action]
        ok = self.store.set_status(sid, status)
        self._json({"ok": ok}, 200 if ok else 404)


def make_server(host: str, port: int, data_dir: Path = DATA_DIR) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"store": Store(data_dir)})
    return ThreadingHTTPServer((host, port), handler)


def serve_in_thread(host: str, port: int, data_dir: Path = DATA_DIR) -> ThreadingHTTPServer:
    srv = make_server(host, port, data_dir)
    threading.Thread(target=srv.serve_forever, daemon=True, name="shadow-web").start()
    return srv


PAGE = r"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>No-Stop Shadow Manager</title>
<style>
:root{--bg:#020617;--card:#0f172a;--line:#1e293b;--txt:#e2e8f0;--mut:#94a3b8;--amb:#fbbf24;--grn:#34d399;--red:#f87171}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:13px/1.4 system-ui,Segoe UI,sans-serif}
header{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:12px 18px;border-bottom:1px solid var(--line)}
h1{font-size:16px;margin:0;color:var(--amb)}.pill{padding:2px 9px;border-radius:99px;border:1px solid var(--line);color:var(--mut)}
.pill b{color:var(--txt)}main{padding:14px 18px;max-width:1500px;margin:auto}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-bottom:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.card .l{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.04em}.card .v{font-size:20px;font-weight:600;margin-top:2px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}
th,td{padding:6px 9px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--mut);font-weight:500;cursor:pointer;user-select:none;position:sticky;top:0;background:#111c33}
td:nth-child(1),th:nth-child(1),td:nth-child(2),th:nth-child(2){text-align:left}
tbody tr{cursor:pointer}tbody tr:hover{background:#16233f}tbody tr.sel{background:#1b2a4a}
.pos{color:var(--grn)}.neg{color:var(--red)}.mut{color:var(--mut)}
.badge{padding:1px 7px;border-radius:5px;font-size:11px}.running{background:#064e3b;color:var(--grn)}
.paused{background:#422006;color:var(--amb)}.stopped{background:#3f1d1d;color:var(--red)}.stale{background:#5b1d1d;color:#fecaca}
button{background:#1e293b;border:1px solid #334155;color:var(--txt);border-radius:5px;padding:2px 8px;cursor:pointer;font-size:12px}
button:hover{border-color:var(--amb)}.row{display:grid;grid-template-columns:3fr 2fr;gap:12px;margin-top:14px}
.panel td,.panel th{padding:4px 7px;font-size:12px}.panel table{border:0}
@media(max-width:1000px){.row{grid-template-columns:1fr}}
.panel{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px;overflow:auto}
.panel h3{margin:0 0 8px;font-size:13px;color:var(--amb)}canvas{width:100%;height:240px;display:block}
.sys{margin-top:14px;color:var(--mut);font-size:12px;display:flex;flex-wrap:wrap;gap:14px}
.wrap{max-height:56vh;overflow:auto;border-radius:8px}
</style></head><body>
<header><h1>No-Stop Shadow Manager</h1>
<span class="pill">running <b id="c_run">0</b></span><span class="pill">paused <b id="c_pau">0</b></span>
<span class="pill">stopped <b id="c_stp">0</b></span><span class="pill" id="p_feed">feed -</span>
<span class="pill" id="p_api">API -</span><span class="pill" id="p_mem">RAM -</span>
<span style="flex:1"></span><button onclick="act('*','pause')">Pause all</button><button onclick="act('*','resume')">Resume all</button></header>
<main>
<div class="cards">
<div class="card"><div class="l">Tổng vốn mô phỏng</div><div class="v" id="t_eq">-</div></div>
<div class="card"><div class="l">Lãi/lỗ tổng</div><div class="v" id="t_pnl">-</div></div>
<div class="card"><div class="l">Lãi/lỗ hôm nay (UTC)</div><div class="v" id="t_day">-</div></div>
<div class="card"><div class="l">Shadow lãi / lỗ</div><div class="v" id="t_wl">-</div></div>
<div class="card"><div class="l">Vị thế đang mở</div><div class="v" id="t_pos">-</div></div></div>
<div class="wrap"><table id="tbl"><thead><tr>
<th data-k="id">Shadow</th><th data-k="status">Trạng thái</th><th data-k="equity">Vốn (USDT)</th><th data-k="pnl">Lãi/lỗ</th>
<th data-k="ret">%</th><th data-k="pnl_today">Hôm nay</th><th data-k="max_dd">MaxDD</th><th data-k="n_positions">Vị thế</th>
<th data-k="gross">Gross</th><th data-k="days">Ngày</th><th data-k="rv">Calmar val</th><th data-k="rt">Calmar test</th><th></th>
</tr></thead><tbody></tbody></table></div>
<div class="row"><div class="panel"><h3 id="d_title">Chọn một shadow</h3><canvas id="cv"></canvas><div class="mut" id="d_meta"></div></div>
<div class="panel"><h3>Vị thế hiện tại</h3><div id="d_pos" class="mut">-</div></div></div>
<div class="panel" style="margin-top:12px"><h3>Lệnh gần nhất</h3><div id="d_tr" class="mut">-</div></div>
<div class="panel" id="prof" style="margin-top:12px"><h3>Mô tả chiến lược &amp; backtest</h3><div id="p_body" class="mut">Chọn một shadow ở bảng để xem cơ chế, thông số và kết quả backtest.</div></div>
<div class="sys" id="sys"></div></main>
<script>
let DATA=null,SEL=null,SORT={k:'ret',d:-1};
const $=s=>document.querySelector(s);
const fmt=(x,d=2)=>Number(x).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
const sgn=x=>x>0?'pos':(x<0?'neg':'mut');
const pct=x=>(x>=0?'+':'')+fmt(x*100,2)+'%';
const money=x=>(x>=0?'+':'')+fmt(x,2);
const ago=ms=>{if(!ms)return '-';const m=Math.round((Date.now()-ms)/60000);return m<90?m+' phút trước':fmt(m/60,1)+' giờ trước'};
async function act(id,a){await fetch('/api/shadow/'+encodeURIComponent(id)+'/'+a,{method:'POST'});load()}
function val(r,k){if(k=='rv')return r.research.val_calmar??-9;if(k=='rt')return r.research.test_calmar??-9;return r[k]}
function render(){
 const d=DATA;if(!d)return;const t=d.totals,s=d.system||{};
 $('#c_run').textContent=d.counts.running;$('#c_pau').textContent=d.counts.paused;$('#c_stp').textContent=d.counts.stopped;
 $('#t_eq').textContent=fmt(t.equity);$('#t_pnl').innerHTML='<span class="'+sgn(t.pnl)+'">'+money(t.pnl)+' ('+pct(t.ret)+')</span>';
 $('#t_day').innerHTML='<span class="'+sgn(t.pnl_today)+'">'+money(t.pnl_today)+'</span>';$('#t_pos').textContent=t.positions;
 const w=d.shadows.filter(r=>r.status!='stopped'&&r.pnl>0).length,l=d.shadows.filter(r=>r.status!='stopped'&&r.pnl<0).length;
 $('#t_wl').innerHTML='<span class="pos">'+w+'</span> / <span class="neg">'+l+'</span>';
 const lag=s.feed_last_bar_ms?Math.round((d.now-s.feed_last_bar_ms)/60000):null;
 $('#p_feed').innerHTML='feed: nến '+(s.feed_last_bar_ms?new Date(s.feed_last_bar_ms).toISOString().slice(5,16)+'Z':'-')+' · <b>'+(lag==null?'-':lag+'p')+'</b>';
 $('#p_api').innerHTML='API weight/phút: <b>'+(s.api_used_weight_1m??'-')+'</b> · lỗi <b>'+(s.api_errors??0)+'</b>';
 $('#p_mem').innerHTML='RAM <b>'+(s.rss_mb??'-')+' MB</b> · chu kỳ <b>'+(s.cycle_seconds??'-')+'s</b>';
 const rows=[...d.shadows].sort((a,b)=>{const x=val(a,SORT.k),y=val(b,SORT.k);return (x>y?1:x<y?-1:0)*SORT.d});
 $('#tbl tbody').innerHTML=rows.map(r=>{const st=r.stale?'stale':r.status;
  return '<tr data-id="'+r.id+'" class="'+(r.id==SEL?'sel':'')+'"><td title="'+r.desc+'">'+r.id.replace('composite-','c-')+'<div class="mut" style="font-size:11px;max-width:330px;overflow:hidden;text-overflow:ellipsis">'+r.desc+'</div></td>'
  +'<td><span class="badge '+st+'">'+(r.stale?'STALE':r.status)+'</span></td><td>'+fmt(r.equity)+'</td>'
  +'<td class="'+sgn(r.pnl)+'">'+money(r.pnl)+'</td><td class="'+sgn(r.ret)+'">'+pct(r.ret)+'</td>'
  +'<td class="'+sgn(r.pnl_today)+'">'+money(r.pnl_today)+'</td><td>'+fmt(r.max_dd*100,1)+'%</td><td>'+r.n_positions+'</td>'
  +'<td>'+fmt(r.gross,2)+'</td><td>'+fmt(r.days,1)+'</td><td class="mut">'+(r.research.val_calmar!=null?fmt(r.research.val_calmar):'-')+'</td>'
  +'<td class="mut">'+(r.research.test_calmar!=null?fmt(r.research.test_calmar):'-')+'</td><td>'
  +(r.status=='running'?'<button onclick="event.stopPropagation();act(\''+r.id+'\',\'pause\')">Pause</button>':'<button onclick="event.stopPropagation();act(\''+r.id+'\',\'resume\')">Resume</button>')+'</td></tr>'}).join('');
 document.querySelectorAll('#tbl tbody tr').forEach(tr=>tr.onclick=()=>{SEL=tr.dataset.id;render();loadDetail()});
 const calls=Object.entries(s.api_calls||{}).map(([k,v])=>k.replace('/fapi/v1/','')+': '+v).join(' · ');
 $('#sys').innerHTML='<span>Nến trong bộ nhớ: '+(s.feed_bars??'-')+' × '+(s.feed_symbols??'-')+' coin</span><span>Gọi API từ khi chạy: '+calls+'</span>'
  +'<span>Lệch giờ máy so với sàn: '+(s.clock_offset_ms??'-')+' ms</span><span>Giá mark cập nhật: '+ago(d.prices_ts)+'</span>'
  +(Object.keys(s.feed_skipped||{}).length?'<span class="neg">Coin lỗi dữ liệu: '+Object.keys(s.feed_skipped).join(', ')+'</span>':'')
  +(s.last_error?'<span class="neg">Lỗi: '+s.last_error+'</span>':'');
}
document.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{const k=th.dataset.k;SORT=SORT.k==k?{k,d:-SORT.d}:{k,d:-1};render()});
async function load(){try{DATA=await (await fetch('/api/overview')).json();render();if(SEL)loadDetail()}catch(e){}}
async function loadDetail(){if(!SEL)return;const d=await (await fetch('/api/shadow/'+encodeURIComponent(SEL))).json();if(!d.shadow)return;
 const st=d.state||{};$('#d_title').textContent=d.shadow.id+' · '+d.shadow.desc;
 $('#d_meta').innerHTML=st.equity?('Bắt đầu '+new Date(st.start_ts).toISOString().slice(0,16)+'Z · vốn '+fmt(st.capital,0)+' · phí '+fmt(st.fees)+' · funding '+money(st.funding)+' · đã chốt '+money(st.realized)+' · net exposure '+fmt(st.net,2)+(st.error?' · <span class="neg">'+st.error+'</span>':'')):'Chưa có dữ liệu (đợi chu kỳ nến tiếp theo)';
 draw(st.curve||[],st.capital||1);
 const P=st.positions||[];$('#d_pos').innerHTML=P.length?'<table><thead><tr><th>Coin</th><th>Hướng</th><th>Notional</th><th>Giá vào TB</th><th>Giá</th><th>uPnL</th></tr></thead><tbody>'
  +P.map(p=>'<tr><td>'+p.symbol+'</td><td class="'+(p.side=='LONG'?'pos':'neg')+'">'+p.side+'</td><td>'+fmt(p.notional)+'</td><td>'+fmt(p.avg_entry,5)+'</td><td>'+fmt(p.price,5)+'</td><td class="'+sgn(p.upnl_entry)+'">'+money(p.upnl_entry)+'</td></tr>').join('')+'</tbody></table>':'Không có vị thế';
 const T=st.trades||[];$('#d_tr').innerHTML=T.length?'<table><thead><tr><th>Giờ (UTC)</th><th>Coin</th><th>Lệnh</th><th>Notional</th><th>Giá</th><th>Phí</th></tr></thead><tbody>'
  +T.slice(0,25).map(t=>'<tr><td>'+new Date(t.t).toISOString().slice(5,16)+'</td><td>'+t.symbol+'</td><td class="'+(t.side=='BUY'?'pos':'neg')+'">'+t.side+'</td><td>'+fmt(t.notional)+'</td><td>'+fmt(t.price,5)+'</td><td>'+fmt(t.fee,3)+'</td></tr>').join('')+'</tbody></table>':'Chưa có lệnh';renderProfile(d.profile);}
function draw(c,cap){const cv=$('#cv'),r=cv.getBoundingClientRect(),dpr=window.devicePixelRatio||1;cv.width=r.width*dpr;cv.height=240*dpr;
 const x=cv.getContext('2d');x.scale(dpr,dpr);const W=r.width,H=240;x.clearRect(0,0,W,H);if(c.length<2){x.fillStyle='#94a3b8';x.fillText('Chưa đủ dữ liệu',12,20);return}
 const ys=c.map(p=>p[1]).concat([cap]),lo=Math.min(...ys),hi=Math.max(...ys),pad=(hi-lo)*.1||1,t0=c[0][0],t1=c[c.length-1][0];
 const X=t=>30+(W-40)*(t-t0)/Math.max(t1-t0,1),Y=v=>H-22-(H-34)*(v-(lo-pad))/(hi-lo+2*pad);
 x.strokeStyle='#334155';x.setLineDash([4,4]);x.beginPath();x.moveTo(30,Y(cap));x.lineTo(W-10,Y(cap));x.stroke();x.setLineDash([]);
 x.strokeStyle=c[c.length-1][1]>=cap?'#34d399':'#f87171';x.lineWidth=1.6;x.beginPath();c.forEach((p,i)=>i?x.lineTo(X(p[0]),Y(p[1])):x.moveTo(X(p[0]),Y(p[1])));x.stroke();
 x.fillStyle='#94a3b8';x.font='11px system-ui';x.fillText(fmt(hi),2,12);x.fillText(fmt(lo),2,H-8);x.fillText(new Date(t0).toISOString().slice(0,10),30,H-6);x.fillText(new Date(t1).toISOString().slice(0,10),W-72,H-6)}
function renderProfile(p){
 const el=$('#p_body');
 if(!p){el.innerHTML='Chưa có mô tả. Chạy: python -m dao_vang.nostop.shadow profiles';return}
 const B=p.backtest,names={train:'Train 2020–2023',val:'Validation 2024–2025',test:'Test 2026 (01→08)'};
 const f=(x,d=2)=>x==null?'-':fmt(x,d),pc=x=>x==null?'-':fmt(x*100,1)+'%';
 const mech=p.mechanism.map(l=>l.startsWith('  •')?'<li style="margin-left:18px">'+l.slice(4)+'</li>':'<p style="margin:5px 0;color:#e2e8f0">'+l+'</p>').join('');
 const rat=p.rationale?p.rationale.map(l=>'<li style="margin:5px 0;color:#e2e8f0">'+l+'</li>').join(''):'';
 const par=p.params.map(r=>'<tr><td style="text-align:left">'+r.name+'</td><td style="text-align:left"><b>'+r.value+'</b></td><td class="mut" style="text-align:left;white-space:normal">'+r.meaning+'</td></tr>').join('');
 const rows=['train','val','test'].map(k=>{const b=B[k];return '<tr><td style="text-align:left">'+names[k]+'</td><td>'+pc(b.cagr)+'</td><td>'+pc(b.maxdd)+'</td><td><b>'+f(b.calmar)+'</b></td><td>'+f(b.calmar_intra)+'</td><td>'+pc(b.total_return)+'</td><td>'+f(b.sharpe)+'</td><td>'+b.pos_years+'</td><td>'+pc(b.month_win)+'</td><td>'+f(b.gross_avg)+'</td><td>'+f(b.turnover_per_year,0)+'×</td></tr>'}).join('');
 const y_rows=(p.yearly_stats||[]).map(y=>'<tr><td style="text-align:left">'+y.year+(y.year==2026?' (8 th.)':'')+'</td><td class="'+sgn(y.ret)+'">'+(y.ret>0?'+':'')+pc(y.ret)+'</td><td>'+pc(y.maxdd)+'</td><td><b>'+f(y.calmar)+'</b></td></tr>').join('');
 const R=p.robustness,S=p.stress,pl=p.post_lock;
 el.innerHTML='<div style="margin-bottom:8px"><span class="pill">Sinh ra ở vòng <b>'+p.origin_round+'</b></span> <span class="pill">Hạng khi khóa (theo Calmar val) <b>#'+p.lock_rank+'</b></span> <span class="pill" style="border-color:#fbbf24;color:#fbbf24">Thăm dò: validation đã dùng thích nghi, chưa nghiệm thu</span></div>'
 +'<h4 style="margin:8px 0 2px;color:#fbbf24">Cơ chế</h4>'+mech
 +'<h4 style="margin:8px 0 2px;color:#fbbf24">Lý do sinh lời (Alpha Rationale)</h4><ul style="margin:0;padding-left:16px">'+rat+'</ul>'
 +'<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:10px" class="pgrid"><div><h4 style="margin:0 0 4px;color:#fbbf24">Thông số</h4><table><thead><tr><th style="text-align:left">Tên</th><th style="text-align:left">Giá trị</th><th style="text-align:left">Ý nghĩa</th></tr></thead><tbody>'+par+'</tbody></table></div>'
 +'<div><h4 style="margin:0 0 4px;color:#fbbf24">Backtest (spec đã khóa)</h4><table><thead><tr><th style="text-align:left">Giai đoạn</th><th>CAGR</th><th>MaxDD</th><th>Calmar</th><th>Calmar intrabar</th><th>Tổng LN</th><th>Sharpe</th><th>Năm dương</th><th>Tháng thắng</th><th>Gross TB</th><th>Vòng quay/năm</th></tr></thead><tbody>'+rows+'</tbody></table>'
 +'<div class="mut" style="margin:8px 0 4px;color:#fbbf24;font-weight:600">Hiệu suất theo năm</div><table><thead><tr><th style="text-align:left">Năm</th><th>Return</th><th>MaxDD</th><th>Calmar</th></tr></thead><tbody>'+y_rows+'</tbody></table>'
 +'<div class="mut" style="margin:8px 0 2px">Độ bền và rủi ro</div><ul style="margin:0;padding-left:16px">'
 +'<li>Chi phí gấp đôi: Calmar val <b>'+f(S.val_calmar)+'</b>, test <b>'+f(S.test_calmar)+'</b> (lợi nhuận test '+pc(S.test_total_return_2x_cost)+')</li>'
 +'<li>Trễ khớp lệnh +4h: Calmar test <b>'+f(R.test_delay1_calmar)+'</b>; +12h: <b>'+f(R.test_delay3_calmar)+'</b></li>'
 +'<li>Vị thế đơn lớn nhất (trung vị): <b>'+pc(p.max_single_weight_median)+'</b> vốn; không có stop-loss nên coin tăng đột biến khi đang SHORT gây lỗ trực tiếp</li>'
 +(p.btc_beta?'<li>Beta thực đo với BTC (lợi suất ngày, backtest): train <b>'+f(p.btc_beta.train.beta)+'</b> (corr '+f(p.btc_beta.train.corr)+'), val <b>'+f(p.btc_beta.val.beta)+'</b> (corr '+f(p.btc_beta.val.corr)+'), test <b>'+f(p.btc_beta.test.beta)+'</b> (corr '+f(p.btc_beta.test.corr)+'). Cân bằng tiền không bảo đảm beta bằng 0.</li>':'')
 +(pl?'<li>Mở rộng ngoài mẫu ('+pl.start.slice(0,10)+' → lúc khóa, '+fmt(pl.days,0)+' ngày, backfill lịch sử): <b class="'+sgn(pl.return)+'">'+(pl.return>=0?'+':'')+fmt(pl.return*100,1)+'%</b>, MaxDD '+pc(pl.max_dd)+'</li>':'')
 +'<li>Backtest dùng 116 coin còn tồn tại cuối 2025 (thiên lệch sống sót); Calmar test quy năm từ 8 tháng nên rất nhiễu</li></ul></div></div>'
 +'<h4 style="margin:12px 0 2px;color:#fbbf24">Đường vốn backtest nối train → val → test (thang log, mỗi giai đoạn bắt đầu lại từ 1)</h4><canvas id="cv2"></canvas>';
 drawLog(p.curve,p.split_starts);
}
function drawLog(c,sp){const cv=$('#cv2');if(!cv)return;const r=cv.getBoundingClientRect(),dpr=window.devicePixelRatio||1,H=220;cv.width=r.width*dpr;cv.height=H*dpr;
 const x=cv.getContext('2d');x.scale(dpr,dpr);const W=r.width;x.clearRect(0,0,W,H);if(c.length<2)return;
 const ys=c.map(p=>Math.log(p[1])),lo=Math.min(...ys),hi=Math.max(...ys),t0=c[0][0],t1=c[c.length-1][0];
 const X=t=>30+(W-40)*(t-t0)/Math.max(t1-t0,1),Y=v=>H-22-(H-34)*(Math.log(v)-lo)/Math.max(hi-lo,1e-9);
 x.strokeStyle='#334155';x.setLineDash([3,4]);for(const k of ['val','test']){if(sp[k]){x.beginPath();x.moveTo(X(sp[k]),8);x.lineTo(X(sp[k]),H-22);x.stroke();x.fillStyle='#94a3b8';x.fillText(k=='val'?'validation':'test',X(sp[k])+3,18)}}x.setLineDash([]);
 x.strokeStyle='#fbbf24';x.lineWidth=1.5;x.beginPath();c.forEach((p,i)=>i?x.lineTo(X(p[0]),Y(p[1])):x.moveTo(X(p[0]),Y(p[1])));x.stroke();
 x.fillStyle='#94a3b8';x.font='11px system-ui';x.fillText('×'+fmt(Math.exp(hi),1),2,12);x.fillText('×'+fmt(Math.exp(lo),1),2,H-8);x.fillText(new Date(t0).toISOString().slice(0,10),30,H-6);x.fillText(new Date(t1).toISOString().slice(0,10),W-72,H-6)}
load();setInterval(load,10000);
</script></body></html>"""
