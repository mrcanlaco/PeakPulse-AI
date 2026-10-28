import { useCallback, useEffect, useRef, useState } from 'react';
import { Activity, ArrowLeft, CheckCircle2, Circle, Clock3, RefreshCw, ShieldAlert, Wallet } from 'lucide-react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { explainTrading as explain, tradingMoney as money, tradingTime as date, type TradingSnapshot } from './tradingTypes';

const panel = 'rounded-2xl border border-slate-800 bg-slate-950/80';
const button = 'rounded-lg border border-slate-700 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed';

export function ExecutionDashboard({ onClose }: { onClose?: () => void }) {
  const [data, setData] = useState<TradingSnapshot | null>(null);
  const [period, setPeriod] = useState('7d');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [closing, setClosing] = useState<string | null>(null);
  const [tab, setTab] = useState<'positions' | 'history' | 'signals' | 'activity'>('positions');
  const [clock, setClock] = useState(Date.now());
  const request = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    try {
      const response = await fetch(`/api/execution/dashboard?period=${period}`, { signal: controller.signal });
      if (!response.ok) throw new Error(response.status === 401 ? 'Phiên đăng nhập đã hết hạn.' : `Không đọc được tài khoản (${response.status}).`);
      const snapshot = await response.json() as TradingSnapshot;
      if (!snapshot.totals || !snapshot.progress || !snapshot.setup || !Array.isArray(snapshot.trades) || !Array.isArray(snapshot.equity_curve)) throw new Error('Dữ liệu tài khoản chưa sẵn sàng.');
      setData(snapshot); setError(''); setClock(Date.now());
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Mất kết nối');
    } finally { if (!controller.signal.aborted) setLoading(false); }
  }, [period]);
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 10000);
    const ticker = window.setInterval(() => setClock(Date.now()), 1000);
    return () => { request.current?.abort(); window.clearInterval(timer); window.clearInterval(ticker); };
  }, [refresh]);
  const command = async (action: string, tradeId?: string) => {
    setBusy(true); setNotice('');
    try {
      const response = await fetch(`/api/execution/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(tradeId ? { trade_id: tradeId, confirm: true } : {}) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Không gửi được yêu cầu');
      setNotice('Đã xếp hàng yêu cầu. Xem kết quả xử lý trong Nhật ký.'); setClosing(null);
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : 'Lỗi thao tác'); }
    finally { setBusy(false); }
  };
  const active = data?.trades.filter(t => !['closed', 'rejected'].includes(t.status)) ?? [];
  const history = data?.trades.filter(t => ['closed', 'rejected'].includes(t.status)) ?? [];
  const age = data?.account?.at ? Math.max(0, (clock - Date.parse(data.account.at)) / 1000) : null;
  const stale = !data?.healthy || !data?.account_fresh || age == null || age > 60 || !!error;
  const environment = data ? { live: 'TIỀN THẬT', demo: 'BINANCE DEMO', simulation: 'MÔ PHỎNG' }[data.environment] : 'CHƯA XÁC ĐỊNH';
  const actionable = !data?.read_only && !!data?.enabled && data.healthy && !stale && !busy;
  const metrics = [
    { label: data?.read_only ? 'Tài sản USDT' : 'Tổng tài sản', value: money(data?.account?.equity), hint: 'Bao gồm lãi/lỗ chưa chốt', accent: true },
    { label: 'Số dư khả dụng', value: money(data?.account?.available), hint: `Số dư ví: ${money(data?.account?.wallet)}` },
    { label: 'Lãi/lỗ chưa chốt', value: money(data?.account?.unrealized), hint: data?.read_only ? `${data.unmanaged_positions.length} vị thế trên tài khoản` : `${active.length}/${data?.config.max_positions ?? 1} vị thế bot`, signed: data?.account?.unrealized },
    { label: 'Giảm từ đỉnh', value: data?.account ? `${(data.account.drawdown * 100).toFixed(2)}%` : '—', hint: `Đỉnh tài sản: ${money(data?.account?.peak)}` },
  ];
  return <section aria-label="Giao dịch tự động" data-testid="trading-dashboard" className="min-w-0 space-y-5 p-3 sm:p-5 text-sm text-slate-300">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div>
        {onClose && <button onClick={onClose} className="mb-3 flex items-center gap-1.5 text-xs text-slate-400 hover:text-white"><ArrowLeft size={14} /> Về ứng dụng</button>}
        <div className="flex items-center gap-3"><span className="rounded-xl bg-amber-400/10 p-2.5 text-amber-300"><Wallet size={24} /></span><div><p className="text-[10px] tracking-[.2em] text-slate-500 uppercase">Đảo Vàng · Binance USDⓈ-M</p><h1 className="text-xl sm:text-2xl font-semibold text-white">Tài khoản & giao dịch</h1></div></div>
        <p className="mt-3 text-xs text-slate-400">{data?.read_only ? 'Chỉ đọc Binance thật · Không đặt/hủy lệnh · Không đổi ký quỹ hoặc đòn bẩy' : 'Vốn cấu hình 500 USDT · Cross x5 · chỉ Short · khoảng 5 USDT ký quỹ/vị thế'}</p>
      </div>
      <div className="space-y-2 sm:text-right"><span data-testid="trading-environment" className={`inline-flex rounded-full border px-3 py-1 text-[10px] font-bold tracking-wider ${data?.environment === 'live' ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300' : 'border-amber-500/40 bg-amber-500/10 text-amber-300'}`}>{environment}{data?.read_only ? ' · CHỈ ĐỌC' : ''}</span>
        <p className="text-xs text-slate-400">{!data?.account ? 'Chưa kết nối dữ liệu tài khoản' : stale ? 'Dữ liệu cũ · cần đối soát' : 'Dữ liệu tài khoản đang cập nhật'}</p>
        <button onClick={() => void refresh()} disabled={loading} className={`${button} inline-flex items-center gap-2`}><RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Làm mới</button>
      </div>
    </header>
    {error && <p role="alert" className="rounded-xl border border-rose-800/50 bg-rose-950/30 p-3 text-rose-300">{error} Dữ liệu còn hiển thị là lần nhận trước; các thao tác đóng/bật lại bị khóa.</p>}
    {notice && <p role="status" className="rounded-xl bg-sky-950/40 p-3 text-sky-300">{notice}</p>}
    {!data?.account && <div className={`${panel} p-5`} data-testid="trading-empty"><h2 className="font-semibold text-white">Chưa có dữ liệu tài khoản</h2><p className="mt-2 text-sm text-slate-400">Số dư sẽ xuất hiện sau khi kết nối tài khoản được xác minh. Trang này không kích hoạt giao dịch hoặc tự đặt lệnh.</p><div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-xs">{data && [[data.read_only ? 'Chế độ theo dõi đã bật' : 'Dịch vụ đã bật', data.setup.worker_enabled], [data.read_only ? 'Chỉ đọc, không yêu cầu chiến lược' : 'Chiến lược đã nạp', data.read_only || data.setup.manifest_loaded], [data.environment === 'simulation' ? 'Mô phỏng không cần khóa API' : 'Khóa API đã cấu hình', data.setup.credentials_present]].map(([label, ok]) => <span key={String(label)} className={`flex items-center gap-1.5 ${ok ? 'text-emerald-400' : 'text-slate-500'}`}>{ok ? <CheckCircle2 size={14} /> : <Circle size={14} />}{label}</span>)}</div></div>}
    {data?.account && stale && !error && <p role="status" className="rounded-xl border border-amber-700/40 bg-amber-950/20 p-3 text-amber-200">Bản ghi tài khoản đã cũ hoặc chưa xác minh độ mới. Cập nhật gần nhất: {date(data.account.at)}. Đây không phải số dư thời gian thực.</p>}
    {data?.read_only && <div className="rounded-xl border border-sky-800/40 bg-sky-950/20 p-4 text-xs text-sky-200" data-testid="readonly-connection">{data.account_fresh && data.healthy ? "Đã kết nối tài khoản Binance thật · Giao dịch tự động TẮT." : explain(data.connection_error) !== "—" ? explain(data.connection_error) : "Đang chờ lần đọc tài khoản đầu tiên."}<p className="mt-2 text-slate-400">Chỉ theo dõi tài sản USDT. Giữ nguyên mọi lệnh/vị thế đang có trên sàn. Mốc đỉnh tính từ lúc bắt đầu theo dõi, không phải lịch sử toàn tài khoản.</p></div>}
    <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">{metrics.map(m => <article key={m.label} className={`${panel} p-4 ${m.accent ? 'border-amber-700/40 bg-gradient-to-br from-amber-950/20 to-slate-950' : ''}`}><p className="text-xs text-slate-400">{m.label}</p><p className={`mt-2 break-words text-lg sm:text-2xl font-semibold tabular-nums ${m.signed != null ? m.signed < 0 ? 'text-rose-300' : 'text-emerald-300' : 'text-slate-100'}`}>{m.value}</p><p className="mt-2 text-[11px] text-slate-500">{m.hint}</p></article>)}</div>
    <div className="grid xl:grid-cols-[minmax(0,1.65fr)_minmax(300px,1fr)] gap-4">
      <article className={`${panel} min-w-0 p-4`}>
        <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold text-white">Đường tài sản</h2><p className="text-xs text-slate-500 mt-1">{data?.environment === 'live' ? 'Tài sản USDT từ Binance thật' : data?.environment === 'demo' ? 'Từ tài khoản Binance Demo' : 'Từ tài khoản mô phỏng'} · USDT</p></div><div className="flex gap-1">{[['24h', '24 giờ'], ['7d', '7 ngày'], ['30d', '30 ngày']].map(([key, label]) => <button key={key} aria-pressed={period === key} onClick={() => setPeriod(key)} className={`px-2.5 py-1.5 text-xs rounded-lg ${period === key ? 'bg-slate-700 text-white' : 'text-slate-400 hover:bg-slate-800'}`}>{label}</button>)}</div></div>
        <div className="h-56 mt-4" data-testid="equity-chart">{data && data.equity_curve.length > 1 ? <ResponsiveContainer width="100%" height="100%"><LineChart data={data.equity_curve} margin={{ left: -10, right: 8, top: 5, bottom: 5 }}><CartesianGrid stroke="#1e293b" strokeDasharray="3 3" /><XAxis dataKey="at" tickFormatter={v => new Date(v).toLocaleString('vi-VN', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })} minTickGap={40} stroke="#64748b" fontSize={10} /><YAxis domain={['auto', 'auto']} stroke="#64748b" fontSize={10} /><Tooltip labelFormatter={v => date(String(v))} formatter={v => [money(Number(v)), 'Tổng tài sản']} contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 10, fontSize: 12 }} /><Line type="linear" dataKey="equity" stroke="#fbbf24" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} /></LineChart></ResponsiveContainer> : <div className="h-full flex flex-col items-center justify-center gap-2 text-slate-500"><Activity size={30} className="text-slate-700" /><p>Chưa đủ điểm dữ liệu để vẽ biểu đồ</p></div>}</div>
        <p className="text-[10px] text-slate-500">Điểm cuối mỗi khoảng quan sát; không tái dựng biến động giữa các lần ghi. Thời gian theo thiết bị.</p>
        <div className="mt-4 grid grid-cols-3 gap-2 border-t border-slate-800 pt-4">{[['Lãi/lỗ lệnh đã đóng', money(data?.totals.closed_net_pnl)], ['Phí đã ghi nhận', money(data?.totals.recorded_fees)], ['Funding đã ghi nhận', money(data?.totals.recorded_funding)]].map(([label, value]) => <div key={label}><p className="text-[10px] text-slate-500">{label}</p><p className="mt-1 text-xs sm:text-sm text-slate-200 break-words">{value}</p></div>)}</div><p className="text-[10px] text-slate-500 mt-2">Tổng từ sổ của môi trường này, không chỉ khung biểu đồ. “—” nghĩa là chưa có bản ghi; chưa xác nhận toàn bộ lịch sử Binance.</p>
      </article>
      <article className={`${panel} p-4 space-y-4`}>
        {data?.read_only ? <><h2 className="font-semibold text-white">Kết nối tài khoản thật</h2><p className="rounded-lg bg-sky-500/10 p-3 text-sky-200">CHỈ ĐỌC · Auto trading chưa bật</p><p className="text-xs text-slate-400">Đọc số dư, vị thế và lệnh chờ mỗi 15 giây. Không gửi lệnh vào/thoát, không hủy TP, không đổi chế độ tài khoản.</p><dl className="space-y-3 text-xs"><div><dt className="text-slate-500">Chế độ vị thế trên sàn</dt><dd className="mt-1 text-slate-200">{data.account_mode?.hedge == null ? "Chưa đọc được" : data.account_mode.hedge ? "Hedge" : "One-way"}</dd></div><div><dt className="text-slate-500">Chế độ tài sản trên sàn</dt><dd className="mt-1 text-slate-200">{data.account_mode?.multi_assets == null ? "Chưa đọc được" : data.account_mode.multi_assets ? "Multi-Assets · các thẻ chỉ hiển thị USDT" : "Single-Asset"}</dd></div><div><dt className="text-slate-500">Lần đọc thành công</dt><dd className="mt-1 text-slate-200">{date(data.account?.at)}</dd></div></dl><p className="text-xs text-slate-500">Dữ liệu tài khoản cá nhân không được tính thành bằng chứng hiệu quả của bot. Các điều kiện chạy thật chưa được mở khóa.</p></> : <>
        <div className="flex justify-between items-center"><h2 className="font-semibold text-white">Tiến trình vận hành</h2><Clock3 size={16} className="text-slate-500" /></div>
        <div className="flex gap-1 text-[10px]">{[['simulation', '1. Quan sát'], ['demo', '2. Demo'], ['live', '3. Tiền thật']].map(([key, label]) => <span key={key} className={`flex-1 rounded-lg p-2 text-center ${data?.environment === key ? 'bg-amber-500/15 text-amber-300 border border-amber-600/30' : 'bg-slate-900 text-slate-500'}`}>{label}</span>)}</div>
        <p className="text-xs text-slate-400">Môi trường đang cấu hình; Demo và quan sát có thể chạy song song.</p>
        {[
          ['Thời gian có bản ghi', data?.progress.observed_days ?? 0, 28, 'ngày'],
          ['Sự kiện độc lập', data?.progress.independent_events ?? 0, 100, 'tín hiệu'],
          ['Cửa sổ thời gian', data?.progress.time_windows ?? 0, 3, 'cửa sổ'],
        ].map(([label, current, required, unit]) => <div key={String(label)}><div className="flex justify-between text-xs mb-2 gap-2"><span className="text-slate-400">{label}</span><span className="text-slate-200">{Number(current).toFixed(unit === 'ngày' ? 1 : 0)}/{required} {unit}</span></div><div role="progressbar" aria-label={String(label)} aria-valuenow={Number(current)} aria-valuemin={0} aria-valuemax={Number(required)} className="h-1.5 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-amber-400" style={{ width: `${Math.min(100, Number(current) / Number(required) * 100)}%` }} /></div></div>)}
        <p className="text-[11px] text-slate-500">Theo phiên bản chiến lược hiện tại. Thời gian là khoảng giữa các bản ghi; chưa chứng nhận dữ liệu liên tục hoặc lợi nhuận.</p>
        <div className="border-t border-slate-800 pt-3"><p className={`text-xs font-semibold ${data?.live_gate.eligible ? 'text-emerald-300' : 'text-amber-300'}`}>{data?.live_gate.eligible ? 'Báo cáo đã qua bộ kiểm tra' : 'Chưa đủ điều kiện tiền thật'}</p><ul className="mt-2 space-y-1 text-xs text-slate-400">{data?.live_gate.reasons.slice(0, 5).map(reason => <li key={reason}>• {explain(reason)}</li>)}</ul><p className="mt-2 text-[11px] text-slate-500">Cần nghiệm thu hiệu quả sau chi phí, mức giảm tài sản và cận dưới tin cậy 95% &gt; 0.</p></div>
        </>}
      </article>
    </div>
    {!data?.read_only && <div className={`${panel} p-4 flex flex-wrap justify-between items-center gap-4`}><div><p className="font-medium text-slate-100">Mở lệnh mới: {!data?.enabled ? 'Chưa bật' : data.pause.paused ? 'Đã dừng' : !data.healthy || stale ? 'Chưa xác minh trạng thái' : 'Theo điều kiện chiến lược'}</p><p className="text-xs text-slate-400 mt-1">{data?.pause.paused ? explain(data.pause.reason) : 'Theo dõi tài khoản không tự kích hoạt bot.'} Dừng mở mới giữ vị thế và TP.</p></div><div className="flex gap-2"><button disabled={busy || !data?.enabled} onClick={() => void command('pause')} className={`${button} border-amber-700/50 text-amber-300`}>Dừng mở mới</button><button disabled={!actionable || !data?.pause.paused || (data.account?.drawdown ?? 1) >= .2} onClick={() => void command('resume')} className={button}>Bật lại mở mới</button></div></div>}
    <article className={`${panel} overflow-hidden`}>
      <div role="tablist" aria-label="Chi tiết giao dịch" className="flex overflow-x-auto border-b border-slate-800 px-2">{[['positions', `Vị thế (${data?.read_only ? data.unmanaged_positions.length : active.length})`], ['history', `Lịch sử (${data?.totals.closed_count ?? 0})`], ['signals', 'Tín hiệu'], ['activity', 'Nhật ký']].map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key as typeof tab)} className={`whitespace-nowrap px-4 py-3 text-xs font-medium border-b-2 ${tab === key ? 'border-amber-400 text-amber-300' : 'border-transparent text-slate-400'}`}>{label}</button>)}</div>
      <div role="tabpanel" className="p-4 space-y-3">
        {tab === 'positions' && data?.read_only && <div className="space-y-3 text-xs"><h3 className="font-semibold text-slate-200">Lệnh chờ trên Binance ({data.open_orders?.length ?? 0})</h3>{!data.open_orders?.length && <p className="text-slate-500">{data.account ? 'Không có lệnh chờ thông thường trong lần đọc gần nhất.' : 'Chưa đọc được lệnh chờ.'}</p>}{data.open_orders?.map(order => <p key={order.orderId} className="text-slate-300 break-words">{order.symbol} · {order.side} · {order.type} · Giá {order.price} · {order.executedQty}/{order.origQty} · {explain(order.status)}</p>)}{data.account && !data.unmanaged_positions.length && <p className="text-slate-500">Không có vị thế đang mở trong lần đọc gần nhất.</p>}<p className="text-slate-500">Lệnh điều kiện/algo không nằm trong danh sách lệnh thông thường này.</p>{data.income_health?.healthy === false && <p className="text-amber-200">Phí/funding chưa cập nhật: {explain(data.income_health.error)}</p>}</div>}
        {tab === 'positions' && !!data?.unmanaged_positions.length && <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 p-3 text-xs text-amber-200"><p className="font-semibold">{data.read_only ? "Vị thế hiện có trên Binance · chỉ xem" : "Vị thế ngoài sổ của bot · cần kiểm tra"}</p>{data.unmanaged_positions.map(p => <p key={`${p.symbol}-${p.side}`} className="mt-2">{p.symbol} · {p.side === "BOTH" ? (p.quantity ?? 0) < 0 ? "SHORT" : "LONG" : p.side} · Khối lượng: {p.quantity ?? "—"} · Chưa chốt: {money(p.unrealized).replace("USDT", p.margin_asset ?? "USDT")}</p>)}<p className="mt-2">Được tính trong tài sản tài khoản; không có thao tác đóng tự động tại đây.</p></div>}
        {tab === 'positions' && <>{!active.length && !data?.read_only && <p className="py-8 text-center text-slate-500">Chưa có vị thế được bot quản lý.</p>}{active.map(trade => <article key={trade.id} className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-2"><strong className="text-white">{trade.symbol}</strong><span className="rounded bg-rose-500/10 px-2 py-0.5 text-[10px] text-rose-300">SHORT · x5</span><span className="text-xs text-slate-500">{explain(trade.status)}</span></div><p className={trade.unrealized != null && trade.unrealized < 0 ? 'text-rose-300' : 'text-slate-200'}>Chưa chốt: {money(trade.unrealized)}</p></div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">{[['Giá khớp', trade.entry_price ?? 'Đang đối soát'], ['Giá đánh dấu', trade.mark_price ?? '—'], ['Khối lượng còn lại', trade.remaining_qty ?? '—'], ['Giá TP dự kiến', trade.tp_price ?? 'Chưa xác minh'], ['Mục tiêu ròng', money(trade.target)], ['Funding', money(trade.funding)], ['Thời điểm vào', date(trade.created_at)], ['Đã giữ', trade.created_at ? `${Math.max(0, (clock - Date.parse(trade.created_at)) / 3600000).toFixed(1)} giờ` : '—']].map(([label, value]) => <div key={String(label)}><p className="text-slate-500">{label}</p><p className="mt-1 text-slate-200 break-words">{value}</p></div>)}</div>
          <p className="text-xs text-slate-400">TP: {trade.tp_status ? explain(trade.tp_status) : 'Chưa xác minh'} · Đối soát gần nhất: {date(trade.last_reconciled_at)}</p>
          <details className="text-xs text-slate-500"><summary className="cursor-pointer">Nguồn tín hiệu & đối soát</summary><div className="mt-2 space-y-1 break-all"><p>Sự kiện: {trade.signal?.event_id ?? 'Chưa có'}</p><p>Lệnh vào: {trade.entry_id ?? 'Chưa có'}</p><p>Lệnh TP: {trade.tp_id ?? 'Chưa có'} · Có mã lệnh không đồng nghĩa đã được sàn xác nhận.</p><p>Phiên bản: {trade.signal?.manifest_id ?? 'Chưa có'}</p></div></details>
          {closing === trade.id ? <div className="rounded-lg bg-rose-950/30 p-3 space-y-3"><p className="text-xs text-rose-200">Đóng thị trường có thể chốt lỗ và phát sinh phí. Xác nhận đóng {trade.symbol}?</p><div className="flex gap-3"><button disabled={!actionable} onClick={() => void command('close', trade.id)} className={`${button} bg-rose-900 border-rose-700`}>Xác nhận đóng</button><button disabled={busy} onClick={() => setClosing(null)} className={button}>Hủy</button></div></div> : <button disabled={!actionable} onClick={() => setClosing(trade.id)} className="text-xs text-rose-300 disabled:opacity-40">Đóng thủ công</button>}
        </article>)}</>}
        {tab === 'history' && <>{!history.length ? <p className="py-8 text-center text-slate-500">{data?.read_only ? "Chế độ chỉ đọc chưa nhập lịch sử khớp lệnh; không tạo giao dịch bot từ lịch sử tài khoản." : "Chưa có giao dịch đã kết thúc."}</p> : <div className="overflow-x-auto"><table className="w-full text-xs text-left whitespace-nowrap"><thead className="text-slate-500"><tr>{['Coin', 'Kết quả', 'Giá vào', 'Lãi/lỗ ròng', 'Funding', 'Kết thúc'].map(h => <th key={h} className="p-3 font-medium">{h}</th>)}</tr></thead><tbody>{history.map(t => <tr key={t.id} className="border-t border-slate-800"><td className="p-3 font-semibold text-slate-100">{t.symbol}</td><td className="p-3">{explain(t.status)}</td><td className="p-3">{t.entry_price ?? '—'}</td><td className={`p-3 ${(t.net_pnl ?? 0) < 0 ? 'text-rose-300' : 'text-emerald-300'}`}>{money(t.net_pnl)}</td><td className="p-3">{money(t.funding)}</td><td className="p-3">{date(t.closed_at)}</td></tr>)}</tbody></table></div>}{data?.trade_history_truncated && <p className="text-xs text-slate-500">Hiển thị 100 giao dịch kết thúc gần nhất; tổng tài khoản vẫn tính toàn bộ sổ.</p>}</>}
        {tab === 'signals' && <>{!data?.recent_signals.length && <p className="py-8 text-center text-slate-500">Chưa ghi nhận tín hiệu giao dịch.</p>}{data?.recent_signals.map((s, i) => <div key={`${s.event_id}-${i}`} className="border-b border-slate-800 pb-3 text-xs"><div className="flex justify-between gap-2"><strong className="text-slate-100">{s.symbol}</strong><span className="text-slate-500">{date(s.at)}</span></div><p className="mt-2 break-words">{explain(s.decision)}{s.reasons.length ? ` · ${s.reasons.map(explain).join(', ')}` : ''}</p></div>)}</>}
        {tab === 'activity' && <><h3 className="font-medium text-slate-200 text-xs">Yêu cầu điều khiển</h3>{!data?.commands.length && <p className="text-xs text-slate-500">Chưa có yêu cầu.</p>}{data?.commands.map(c => <p key={c.id} className="text-xs break-words">{date(c.at)} · {explain(c.action)} · <span className={c.status.startsWith('failed') ? 'text-rose-300' : 'text-sky-300'}>{explain(c.status)}</span></p>)}<h3 className="font-medium text-slate-200 text-xs pt-3">Nhật ký vận hành</h3>{!data?.activity.length && <p className="text-xs text-slate-500">Chưa có sự kiện vận hành.</p>}{data?.activity.map(item => <p key={item.seq} className="text-xs text-slate-400 break-words">{date(item.at)} · {explain(item.kind)}{item.reason ? ` · ${explain(item.reason)}` : ''}</p>)}</>}
      </div>
    </article>
    <footer className="space-y-3 pb-4"><p className="flex items-start gap-2 rounded-xl border border-amber-900/40 bg-amber-950/20 p-3 text-xs text-amber-200/80"><ShieldAlert size={17} className="shrink-0" />{data?.read_only ? "Đang kết nối tài khoản thật để theo dõi. Quyền giao dịch của ứng dụng vẫn tắt; các lệnh đã có trên Binance giữ nguyên." : "Không đặt stop-loss. Cross có thể sử dụng toàn bộ số dư Futures; dừng mở mới ở mức giảm 20% không giới hạn tổng thua lỗ ở 20%."}</p><p className="text-[10px] text-slate-500">Tự làm mới mỗi 10 giây · Tài khoản ghi nhận: {date(data?.account?.at)} · Dịch vụ: {data?.healthy ? 'Đang hoạt động' : 'Chưa xác minh'} · Nguồn tín hiệu: {data?.source_health.healthy ? 'Đang cập nhật' : 'Chưa xác minh'}</p></footer>
  </section>;
}
