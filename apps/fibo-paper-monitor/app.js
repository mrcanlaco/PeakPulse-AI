'use strict';
const $ = id => document.getElementById(id);
let data = null, selected = 'elite_sniper_risk', range = 'all', tab = 'positions', fetching = false, chartSeries = [];
let refreshTimer = null, failures = 0, offline = false;
const REFRESH_MS = 60000;
const number = (n, digits=2) => Number.isFinite(n) ? n.toLocaleString('vi-VN', {minimumFractionDigits:digits,maximumFractionDigits:digits}) : '—';
const pct = n => `${n>0?'+':''}${number(n)}%`;
const tone = n => n>1e-8?'positive':n< -1e-8?'negative':'neutral';
const timeVN = (t, full=false) => !t ? '—' : new Intl.DateTimeFormat('vi-VN', {timeZone:'Asia/Ho_Chi_Minh',day:full?'2-digit':undefined,month:full?'2-digit':undefined,year:full?'numeric':undefined,hour:'2-digit',minute:'2-digit',second:full?undefined:'2-digit',hour12:false}).format(t);
const dateVN = t => new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',year:'numeric'}).format(t);
const escapeHTML = value => String(value??'—').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const text = (id,value) => {$(id).textContent=value;};
function account(scenario,policy=selected){return data.accounts.find(a=>a.policy===policy&&a.scenario===scenario);}
function returnText(id,n){text(id,pct(n));$(id).className=tone(n);}
function renderHealth(){
  if(offline)return;
  document.body.classList.remove('stale');
  text('autoRefresh',document.hidden?'Tạm nghỉ khi tab ẩn':'Tiết kiệm · cập nhật mỗi 60 giây');
  const stateName={ARMED:'Chờ thời điểm bắt đầu',OBSERVING:'Đang ghi nhận OOS',ERROR_RETRYING:'Đang xử lý sự cố',HORIZON_COMPLETE_AWAITING_REVIEW:'Đến hạn kiểm định cuối kỳ'}[data.status]||data.status;
  text('phase',stateName);text('lastUpdate',`Đồng bộ lúc ${timeVN(data.server_time_ms)} · giờ Việt Nam`);
  const health={healthy:'Kết nối ổn định',delayed:'Dữ liệu cập nhật chậm',error:'Cần kiểm tra sự cố'}[data.health];
  $('connection').className='live-badge'+(data.health==='healthy'?'':data.health==='error'?' error':' warning');
  $('connection').innerHTML=`<i></i>${health}`;
  $('alert').hidden=data.health==='healthy';text('alert',data.error|| (data.health==='error'?'Có sự cố trọng yếu cần kiểm tra. Xem mục Hoạt động & sự cố.':'Heartbeat hoặc dữ liệu bị chậm. Số liệu bên dưới là bản ghi gần nhất, chưa phản ánh đầy đủ hiện tại.'));
  text('healthText',health);$('healthText').className='health-status'+(data.health==='healthy'?'':` health-${data.health==='error'?'error':'warning'}`);
  $('healthDot').style.background=data.health==='healthy'?'var(--mint)':data.health==='error'?'var(--danger)':'var(--amber)';
  text('heartbeat',`${Math.round(data.heartbeat_age_seconds)} giây trước`);text('lastBar',timeVN(data.last_bar_ms));text('lastSignal',timeVN(data.last_signal_ms));
  text('criticalCount',data.critical_count);text('missedCount',data.opportunity_count);
}
function render(){
  if(!data) return;
  renderHealth();
  const s=account('standard_vip6'), t=account('stress_regular');
  if(!$('policy').options.length) $('policy').innerHTML=data.policies.map(p=>`<option value="${escapeHTML(p.id)}">${escapeHTML(p.name)}</option>`).join('');
  $('policy').value=selected;
  text('standardNav',number(s.nav));text('stressNav',number(t.nav));returnText('standardReturn',s.return_pct);returnText('stressReturn',t.return_pct);
  for(const [id,c] of [['standardCost',data.scenarios.standard_vip6],['stressCost',data.scenarios.stress_regular]]) text(id,`Phí ${number(c.fee_bps,1)} + trượt ${number(c.slippage_bps,0)} bps / lần khớp`);
  text('positionsCount',`${s.positions.length} / ${t.positions.length}`);text('positionBreakdown','Chuẩn / Stress · hai tài khoản riêng');text('closedCount',`Đã đóng ${s.closed} / ${t.closed} lệnh`);
  $('weeks').innerHTML=`${data.completed_full_weeks}<small> / ${data.full_weeks} tuần</small>`;
  $('progressFill').style.width=`${Math.min(100,data.completed_full_weeks/data.full_weeks*100)}%`;
  text('endDate',`Đánh giá cuối kỳ · ${dateVN(data.end_ms)}`);
  text('universeCount',`${data.membership?.members.length??0} mã · ${data.accounts.length} tài khoản`);text('criticalCount',data.critical_count);text('missedCount',data.opportunity_count);
  text('journalRevision',`Đã kiểm tra đến bản ghi ${data.verified_journal_revision}`);
  text('drawdown',`MaxDD toàn kỳ: ${number(s.max_dd_pct)}% / ${number(t.max_dd_pct)}%`);
  text('chartNote',s.accepted+t.accepted===0?'Chưa có giao dịch · NAV giữ ở mức khởi tạo.':'Chuẩn / Stress · cập nhật theo các mốc hạch toán.');
  $('comparison').innerHTML=data.policies.map(p=>{const a=account('standard_vip6',p.id),b=account('stress_regular',p.id);return `<tr class="${selected===p.id?'selected':''}"><td><button class="row-name" data-policy="${escapeHTML(p.id)}">${escapeHTML(p.name)}</button></td><td class="${tone(a.return_pct)}">${pct(a.return_pct)}</td><td class="${tone(b.return_pct)}">${pct(b.return_pct)}</td><td>${number(a.max_dd_pct)}% / ${number(b.max_dd_pct)}%</td><td>${a.closed} / ${b.closed}</td></tr>`;}).join('');
  text('protocolSummary',`Bắt đầu ${timeVN(data.start_ms,true)}. Kết thúc ${timeVN(data.end_ms,true)}. ${data.full_weeks} tuần lịch đầy đủ; một lần kết luận thống kê cuối kỳ, điều chỉnh cho 12 tài khoản. Thời hạn không bảo đảm đủ bằng chứng về alpha.`);
  text('protocolHash',`Bản khóa: ${data.protocol_sha256}`);
  renderChart();renderDetail();
}
function renderChart(){
  const s=account('standard_vip6'),t=account('stress_regular');
  const end=Math.max(data.start_ms+60000, data.last_bar_ms);
  const begin=range==='all'?data.start_ms:Math.max(data.start_ms,end-Number(range)*3600000);
  function points(a){let previous=[data.start_ms,100], result=[];for(const p of a.curve){if(p[0]<begin){previous=p;continue;}if(p[0]<=end)result.push(p);}if(!result.length||result[0][0]>begin)result.unshift([begin,previous[1]]);if(result.at(-1)[0]<end)result.push([end,a.nav]);return result;}
  chartSeries=[points(s),points(t)];
  const values=chartSeries.flat().map(p=>p[1]);let lo=Math.min(100,...values), hi=Math.max(100,...values);const pad=Math.max(.1,(hi-lo)*.18);lo-=pad;hi+=pad;
  const width=Math.max(280,Math.round($('chart').getBoundingClientRect().width)),mobile=width<500,height=mobile?230:270;
  $('chart').setAttribute('viewBox',`0 0 ${width} ${height}`);
  const X=mobile?48:66,Y=19,W=width-X-20,H=height-59;const x=t=>X+(t-begin)/(end-begin)*W,y=v=>Y+(hi-v)/(hi-lo)*H;
  const grid=Array.from({length:5},(_,i)=>{const value=hi-(hi-lo)*i/4,py=y(value);return `<line x1="${X}" x2="${X+W}" y1="${py}" y2="${py}" stroke="#253343" stroke-dasharray="3 5"/><text x="${X-12}" y="${py+4}" text-anchor="end">${number(value)}</text>`;}).join('');
  const labels=Array.from({length:4},(_,i)=>{const at=begin+(end-begin)*i/3;const label=(end-begin)>86400000?`${new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit'}).format(at)}${mobile?'':' '+timeVN(at).slice(0,5)}`:timeVN(at).slice(0,5);return `<text x="${x(at)}" y="${height-12}" text-anchor="${i===0?'start':i===3?'end':'middle'}">${label}</text>`;}).join('');
  const paths=chartSeries.map((ps,i)=>`<path d="${ps.map((p,j)=>`${j?'L':'M'}${x(p[0]).toFixed(2)},${y(p[1]).toFixed(2)}`).join(' ')}" fill="none" stroke="${i?'#ecb974':'#58ddbc'}" stroke-width="${i?2:2.8}" ${i?'stroke-dasharray="7 5"':''}/>`).join('');
  $('chart').innerHTML=`${grid}<line x1="${X}" x2="${X+W}" y1="${y(100)}" y2="${y(100)}" stroke="#556576" stroke-dasharray="2 5"/>${labels}${paths}<line id="crosshair" y1="${Y}" y2="${Y+H}" stroke="#697e91" stroke-dasharray="3 3" visibility="hidden"/><rect x="${X}" y="${Y}" width="${W}" height="${H}" fill="transparent" id="chartHit"/>`;
  $('chartHit').addEventListener('pointermove',e=>{
    const rect=$('chart').getBoundingClientRect();const px=Math.max(X,Math.min(X+W,(e.clientX-rect.left)/rect.width*width));const at=begin+(px-X)/W*(end-begin);
    const nearest=chartSeries.map(ps=>{let found=ps[0];for(const p of ps){if(p[0]>at)break;found=p;}return found;});
    const line=$('crosshair');line.setAttribute('x1',px);line.setAttribute('x2',px);line.setAttribute('visibility','visible');
    $('chartTooltip').hidden=false;$('chartTooltip').innerHTML=`${timeVN(at,true)}<br><span class="positive">Chuẩn ${number(nearest[0][1])}</span> · <span>Stress ${number(nearest[1][1])}</span>`;
  });
  $('chartHit').addEventListener('pointerleave',()=>{$('chartTooltip').hidden=true;$('crosshair').setAttribute('visibility','hidden');});
}
function empty(title,description){return `<div class="empty"><div class="empty-symbol">⌁</div><strong>${title}</strong><p>${description}</p></div>`;}
function table(headers,rows){return `<div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;}
const reasonName=r=>({stop:'Dừng lỗ',ratchet:'Dời stop',tp1:'Chốt lời 1',tp2:'Chốt lời 2',tp3:'Chốt lời 3',horizon:'Hết thời hạn',horizon24:'Hết 24 giờ',late_signal:'Tín hiệu quá hạn',membership_not_ready:'Danh mục chưa sẵn sàng',late_signal_no_reconstruction:'Bỏ qua tín hiệu quá hạn'}[r]||r||'—');
function renderDetail(){
  const a=account($('scenario').value);let html='';
  document.querySelector('.scenario-filter').hidden=tab==='activity'||tab==='universe';
  if(tab==='positions'){
    html=!a.positions.length?empty('Chưa có vị thế đang mở','Hệ thống chờ tín hiệu đáp ứng các điều kiện đã khóa. Không phát sinh lệnh cũng là một kết quả quan sát.'):
      table(['Coin / khung','Thời điểm vào','Giá tham chiếu vào','Giá gần nhất','Còn lại','PnL ròng · NAV'],a.positions.map(p=>`<tr><td>${escapeHTML(p.symbol)} · ${escapeHTML(p.tf)}</td><td>${timeVN(p.entry_ts_ms,true)}</td><td>${number(p.entry,6)}</td><td>${number(p.mark,6)}</td><td>${number(p.rem*100,0)}%</td><td class="${tone(p.pnl)}">${number(p.pnl,4)}</td></tr>`));
  }else if(tab==='trades'){
    html=!a.trades.length?empty('Chưa có lệnh đóng','Giao dịch hoàn tất sẽ xuất hiện tại đây, kèm phí, trượt giá và funding đã hạch toán.'):
      table(['Coin / khung','Vào lệnh','Đóng lệnh','Lý do','PnL ròng · NAV','Funding · NAV'],a.trades.map(p=>`<tr><td>${escapeHTML(p.symbol)} · ${escapeHTML(p.tf)}</td><td>${timeVN(p.entry_ts_ms,true)}</td><td>${timeVN(p.exit_ts_ms,true)}</td><td>${escapeHTML(reasonName(p.exit_reason))}</td><td class="${tone(p.pnl)}">${number(p.pnl,4)}</td><td class="${tone(p.funding)}">${number(p.funding,4)}</td></tr>`));
    html+=`<p class="detail-note">Tối đa 100 lệnh gần nhất của tài khoản đang chọn. Lũy kế: phí ${number(a.costs.fees,4)} · trượt giá ${number(a.costs.slippage,4)} · funding ${number(a.costs.funding,4)} đơn vị NAV; gồm cả vị thế đang mở.</p>`;
  }else if(tab==='activity'){
    const rows=[...data.timeline.map(e=>({...e,message:e.kind==='activation'?'Khóa nghiên cứu, sẵn sàng ghi nhận OOS.':`Quét H1: ${e.proposals} đề xuất, ${e.rejections} trường hợp bị loại.`,error:false})),...data.critical_incidents.map(e=>({...e,message:`Sự cố: ${e.symbol||''} ${reasonName(e.reason||e.kind)}`,error:true})),...data.opportunity_incidents.map(e=>({...e,message:`Bỏ lỡ: ${reasonName(e.reason||e.kind)}`,error:true}))].sort((a,b)=>(b.timestamp_ms||0)-(a.timestamp_ms||0)).slice(0,80);
    html=`<div class="activity-list">${rows.map(e=>`<div class="activity-item ${e.error?'error':''}"><time>${timeVN(e.timestamp_ms,true)}</time><span>${escapeHTML(e.message)}</span></div>`).join('')}</div><p class="detail-note">Hiển thị tối đa 80 hoạt động gần nhất; số đề xuất chưa phải số lệnh được chấp nhận.</p>`;
  }else{
    const m=data.membership;
    html=!m?empty('Chưa có danh mục có hiệu lực','Đang chờ nguồn danh mục được ghi nhận.'):`<p class="detail-note">Danh mục tháng ${escapeHTML(m.month)} · có hiệu lực ${timeVN(m.effective_from_ms,true)}. Xếp hạng từ 63 ngày quá khứ.</p>`+table(['#','Hợp đồng','Khối lượng ngày trung vị · USDT','Ngày hoạt động','Râu nến H4 · P90'],m.members.map((p,i)=>`<tr><td>${i+1}</td><td>${escapeHTML(p.symbol)}</td><td>${number(p.median_quote_volume,0)}</td><td>${p.active_days}</td><td>${number(p.wick_p90_pct)}%</td></tr>`));
  }
  $('detailContent').innerHTML=html;
}
async function getJSON(url){const response=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(12000)});const result=await response.json();if(!response.ok)throw new Error(result.error||'Không đọc được dữ liệu.');return result;}
function scheduleRefresh(){clearTimeout(refreshTimer);if(!document.hidden)refreshTimer=setTimeout(()=>refresh(),Math.min(300000,REFRESH_MS*2**Math.min(failures,3)));}
async function refresh(force=false){
  clearTimeout(refreshTimer);
  if(fetching||document.hidden)return;fetching=true;$('refresh').disabled=true;
  try{
    const pulse=data&&!force?await getJSON('/api/pulse'):null;
    if(!data||force||pulse.revision!==data.revision){data=await getJSON('/api/dashboard');offline=false;render();}
    else{Object.assign(data,pulse);offline=false;renderHealth();}
    failures=0;
  }
  catch(error){offline=true;document.body.classList.add('stale');$('connection').className='live-badge error';$('connection').innerHTML='<i></i>Mất kết nối dữ liệu';$('alert').hidden=false;text('alert',`Không thể cập nhật: ${error.message} ${data?'Các số liệu còn hiển thị thuộc lần đọc trước.':''}`);text('healthText','Chưa xác nhận được trạng thái hiện tại');$('healthText').className='health-status health-error';$('healthDot').style.background='var(--danger)';text('autoRefresh','Đang chờ kết nối lại');}
  finally{if(offline)failures++;fetching=false;$('refresh').disabled=false;scheduleRefresh();}
}
$('policy').addEventListener('change',e=>{selected=e.target.value;render();});$('scenario').addEventListener('change',renderDetail);$('refresh').addEventListener('click',()=>refresh(true));
document.querySelector('.range-group').addEventListener('click',e=>{if(!e.target.dataset.range)return;range=e.target.dataset.range;document.querySelectorAll('[data-range]').forEach(b=>b.classList.toggle('active',b.dataset.range===range));if(data)renderChart();});
$('comparison').addEventListener('click',e=>{const button=e.target.closest('[data-policy]');if(button){selected=button.dataset.policy;render();}});
document.querySelector('.tabs').addEventListener('click',e=>{if(!e.target.dataset.tab)return;tab=e.target.dataset.tab;document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.tab===tab)));if(data)renderDetail();});
document.addEventListener('visibilitychange',()=>{clearTimeout(refreshTimer);if(document.hidden)text('autoRefresh','Tạm nghỉ khi tab ẩn');else refresh();});
refresh();
window.addEventListener('resize',()=>{if(data)requestAnimationFrame(renderChart);});
