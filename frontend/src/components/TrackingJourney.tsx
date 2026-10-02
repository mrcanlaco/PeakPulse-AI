import { useState } from 'react';
import type { TrackingWatchlistItem } from '../types';
import { formatSystemDateTime } from '../utils/time';
import { useTranslation } from '../i18n/LanguageContext';
import {
  FlaskConical,
  Bell,
  Clock3,
  TrendingDown,
  TrendingUp,
  RotateCcw,
} from 'lucide-react';

const money = (n: number | null | undefined) => n == null || !Number.isFinite(n) ? '—' : `${n.toFixed(2)} USDT`;
const pct = (n: number | null | undefined) => n == null ? '—' : `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
const input = 'mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-100 font-mono focus:border-sky-500 focus:outline-none';

export function TrackingJourney({
  item,
  onRefresh,
  onUpdate,
}: {
  item: TrackingWatchlistItem;
  onRefresh: () => void;
  onUpdate: (id: string, patch: Record<string, unknown>) => Promise<boolean>;
}) {
  const { language } = useTranslation();
  const vi = language === 'vi';
  const [side, setSide] = useState('SHORT');
  const [size, setSize] = useState('1000');
  const [fee, setFee] = useState('5');
  const [slippage, setSlippage] = useState('5');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const trade = item.paper_trade;

  const act = async (action: 'open' | 'close' | 'reconcile') => {
    setBusy(true);
    setError('');
    try {
      const res = await fetch(`/api/tracking-watchlist/${encodeURIComponent(item.id)}/paper`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          side,
          notional: Number(size),
          fee_bps: Number(fee),
          slippage_bps: Number(slippage),
        }),
      });
      if (!res.ok) {
        throw new Error(
          vi
            ? 'Chưa thực hiện được. Cần giá mới dưới 2 phút; hãy làm mới rồi thử lại.'
            : 'Unable to continue. Fresh price required; refresh and retry.'
        );
      }
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mt-2.5 space-y-2.5 border-t border-slate-800/80 pt-2.5" aria-label={vi ? 'Kiểm chứng & Giả lập' : 'Evidence & Simulation'}>
      {/* Checkpoints: 24h & 48h */}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {[24, 48].map((hours) => {
          const result = item.checkpoints?.[String(hours)];
          const isReady = result?.status === 'READY';
          const returnPct = result?.return_pct;
          const isProfit = returnPct != null && returnPct < 0; // Short orientation
          return (
            <div
              key={hours}
              data-testid={`checkpoint-${hours}`}
              className="rounded-lg border border-slate-800/90 bg-slate-900/50 p-2.5 flex flex-col justify-between"
            >
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-slate-300">
                  {vi ? `Sau ${hours} giờ` : `After ${hours} hours`}
                </span>
                {isReady && returnPct != null ? (
                  <span className={`font-mono text-xs font-bold flex items-center gap-0.5 ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {isProfit ? <TrendingDown className="w-3 h-3" /> : <TrendingUp className="w-3 h-3" />}
                    {pct(returnPct)}
                  </span>
                ) : null}
              </div>

              {isReady ? (
                <div className="mt-1 flex items-center justify-between text-[10px] text-slate-400 font-mono">
                  <span>{vi ? 'Giảm sâu' : 'Drop'}: <strong className="text-slate-200">{pct(result?.max_drop_pct)}</strong></span>
                  <span>{vi ? 'Tăng đỉnh' : 'Peak'}: <strong className="text-slate-200">{pct(result?.max_rise_pct)}</strong></span>
                </div>
              ) : (
                <div className="mt-1 text-[11px] font-medium text-amber-300/90 flex items-center gap-1">
                  <Clock3 className="w-3 h-3 text-amber-400/80 shrink-0" />
                  <span>
                    {result?.status === 'MISSING'
                      ? (vi ? 'Chưa đủ dữ liệu' : 'Insufficient data')
                      : (vi ? 'Đang theo dõi dữ liệu...' : 'Collecting market data...')}
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Paper Trading Simulation Drawer */}
      <details className="group rounded-xl border border-sky-900/40 bg-sky-950/20 overflow-hidden" data-testid="paper-journal">
        <summary className="flex items-center justify-between px-3 py-2 cursor-pointer text-xs font-semibold text-sky-200 hover:text-sky-100 hover:bg-sky-950/30 select-none transition">
          <div className="flex items-center gap-1.5">
            <FlaskConical className="w-3.5 h-3.5 text-sky-400" />
            <span>{vi ? 'Thử bằng vốn giả lập' : 'Paper trading journal'}</span>
            {trade && (
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${trade.status === 'OPEN' ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30' : 'bg-slate-800 text-slate-400 border border-slate-700'}`}>
                {trade.status === 'OPEN' ? (vi ? 'Đang mở' : 'Open') : (vi ? 'Đã đóng' : 'Closed')}
              </span>
            )}
          </div>
          <span className="text-[10px] text-sky-400/70 font-normal group-open:rotate-180 transition-transform">
            ▼
          </span>
        </summary>

        <div className="p-3 border-t border-sky-900/30 space-y-2.5">
          {!trade && !item.archived_at && (
            <form onSubmit={(e) => { e.preventDefault(); void act('open'); }} className="space-y-2.5">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <label className="text-[10px] text-slate-400 font-medium">
                  {vi ? 'Hướng giả lập' : 'Side'}
                  <select className={input} value={side} onChange={(e) => setSide(e.target.value)}>
                    <option value="SHORT">SHORT</option>
                    <option value="LONG">LONG</option>
                  </select>
                </label>
                <label className="text-[10px] text-slate-400 font-medium">
                  {vi ? 'Quy mô (USDT)' : 'Size (USDT)'}
                  <input className={input} required type="number" min="1" max="1000000" value={size} onChange={(e) => setSize(e.target.value)} />
                </label>
                <label className="text-[10px] text-slate-400 font-medium">
                  {vi ? 'Phí mỗi chiều (bps)' : 'Fee (bps)'}
                  <input className={input} required type="number" min="0" max="100" step="0.1" value={fee} onChange={(e) => setFee(e.target.value)} />
                </label>
                <label className="text-[10px] text-slate-400 font-medium">
                  {vi ? 'Trượt giá (bps)' : 'Slippage (bps)'}
                  <input className={input} required type="number" min="0" max="100" step="0.1" value={slippage} onChange={(e) => setSlippage(e.target.value)} />
                </label>
              </div>

              <div className="flex items-center justify-between pt-1">
                <span className="text-[10px] text-slate-500">
                  {vi ? 'Mô phỏng khớp giá thị trường thực tế (1 bps = 0.01%)' : 'Simulated execution at live market price'}
                </span>
                <button
                  className="px-3.5 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold text-xs transition disabled:opacity-50"
                  disabled={busy}
                  type="submit"
                >
                  {busy ? '…' : vi ? 'Mở giả lập' : 'Open paper trade'}
                </button>
              </div>
            </form>
          )}

          {trade && (
            <div className="space-y-2 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2 p-2 rounded-lg bg-slate-900/80 border border-slate-800">
                <div className="flex items-center gap-2 font-mono">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${trade.side === 'SHORT' ? 'bg-rose-500/20 text-rose-300' : 'bg-emerald-500/20 text-emerald-300'}`}>
                    {trade.side}
                  </span>
                  <span className="text-slate-200 font-semibold">{money(trade.notional)}</span>
                  <span className="text-slate-400">@ {trade.entry_price.toPrecision(7)}</span>
                </div>

                {trade.status === 'OPEN' ? (
                  <button
                    className="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition disabled:opacity-50"
                    disabled={busy}
                    onClick={() => void act('close')}
                  >
                    {busy ? '…' : vi ? 'Đóng giả lập theo giá mới' : 'Close at current price'}
                  </button>
                ) : (
                  <div className="text-right font-mono font-bold text-xs text-sky-200">
                    {vi ? 'Lãi/lỗ ròng giả lập: ' : 'Paper net P&L: '}
                    <span className={(trade.net_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                      {money(trade.net_pnl)}
                    </span>
                  </div>
                )}
              </div>

              {trade.status === 'CLOSED' && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px] text-slate-400 px-1 font-mono">
                  <div>{vi ? 'Giá đóng' : 'Exit'}: <span className="text-slate-200">{trade.exit_price?.toPrecision(7)}</span></div>
                  <div>{vi ? 'Lãi/lỗ giá' : 'Price PnL'}: <span className="text-slate-200">{money(trade.gross_pnl)}</span></div>
                  <div>{vi ? 'Tổng phí' : 'Fees'}: <span className="text-slate-200">{money(trade.fees)}</span></div>
                  <div>Funding: <span className="text-slate-200">{money(trade.funding.cashflow)}</span></div>
                </div>
              )}

              {trade.funding.status !== 'VERIFIED' && trade.status === 'CLOSED' && (
                <button
                  className="inline-flex items-center gap-1 text-[10px] text-sky-400 hover:underline"
                  disabled={busy}
                  onClick={() => void act('reconcile')}
                >
                  <RotateCcw className="w-3 h-3" />
                  {vi ? 'Đối chiếu lại funding' : 'Retry funding reconciliation'}
                </button>
              )}
            </div>
          )}

          {error && <p role="alert" className="text-xs text-rose-400">{error}</p>}
        </div>
      </details>

      {/* In-app notifications banner & Feedback buttons */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs pt-1">
        <div className="flex items-center gap-2">
          {!item.archived_at && (
            <label className="flex items-center gap-1.5 text-[11px] text-slate-400 cursor-pointer select-none">
              <input
                type="checkbox"
                className="rounded border-slate-700 bg-slate-900 text-amber-500 focus:ring-0"
                checked={item.notifications_enabled !== false}
                onChange={(e) => void onUpdate(item.id, { notifications_enabled: e.target.checked })}
              />
              {vi ? 'Thông báo trong ứng dụng' : 'In-app notifications'}
            </label>
          )}

          {item.notifications?.some((n) => !n.read) && (
            <button
              className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/30 transition"
              onClick={() => void onUpdate(item.id, { read_notifications: true })}
            >
              {vi ? 'Đánh dấu đã đọc' : 'Mark as read'}
            </button>
          )}
        </div>

        {/* Feedback pill buttons */}
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-slate-500 mr-1">{vi ? 'Đánh giá:' : 'Feedback:'}</span>
          {(['USEFUL', 'NOISY', 'UNCLEAR'] as const).map((value, i) => (
            <button
              key={value}
              aria-pressed={item.feedback === value}
              className={`px-2 py-0.5 rounded text-[10px] font-medium transition ${
                item.feedback === value
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/50 font-bold'
                  : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
              onClick={() => void onUpdate(item.id, { feedback: value })}
            >
              {(vi ? ['Hữu ích', 'Gây phiền', 'Khó hiểu'] : ['Useful', 'Noisy', 'Unclear'])[i]}
            </button>
          ))}
        </div>
      </div>

      {/* Unread notifications list if any */}
      {item.notifications?.some((n) => !n.read) && (
        <ul className="space-y-1 text-xs" aria-label={vi ? 'Thông báo theo dõi' : 'Tracking notifications'}>
          {item.notifications.filter((n) => !n.read).map((n) => (
            <li key={n.id} className="flex items-center gap-1.5 text-amber-300 text-[11px]">
              <Bell className="w-3 h-3 text-amber-400 shrink-0" />
              <span>{formatSystemDateTime(n.at)} · {n.message}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
