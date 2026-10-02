import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  Archive,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  Eye,
  EyeOff,
  Loader2,
  Minus,
  Pencil,
  Plus,
  RefreshCw,
  Target,
  X,
  AlertCircle,
} from 'lucide-react';
import type {
  TrackingStatus,
  TrackingWatchlistItem,
} from '../types';
import { formatSystemDateTime } from '../utils/time';
import { useTranslation, type Language } from '../i18n/LanguageContext';
import { TrackingJourney } from './TrackingJourney';

export type TrackingFilter = 'ACTIVE' | 'ALL' | TrackingStatus;
export type UpdateTrackingPayload = Record<string, unknown>;

interface TrackingWatchlistProps {
  onAddTracking?: (symbol: string) => void | Promise<boolean>;
  items: TrackingWatchlistItem[];
  isLoading: boolean;
  updatingId: string | null;
  onRefresh: () => void;
  onSelectCoin: (symbol: string) => void;
  onUpdateItem: (id: string, payload: UpdateTrackingPayload) => Promise<boolean>;
  onRemoveItem: (id: string) => Promise<boolean>;
}

interface PositionFormState {
  position_side: 'LONG' | 'SHORT';
  entry_price: string;
  quantity: string;
  notional: string;
  leverage: string;
  stop_loss: string;
  take_profit: string;
  notes: string;
}

const emptyForm: PositionFormState = {
  position_side: 'SHORT',
  entry_price: '',
  quantity: '',
  notional: '',
  leverage: '1',
  stop_loss: '',
  take_profit: '',
  notes: '',
};

const numberValue = (value: string): number | null => {
  const parsed = Number.parseFloat(value.trim());
  return Number.isFinite(parsed) ? parsed : null;
};

const formatPrice = (value: number | null | undefined): string => {
  if (value == null || !Number.isFinite(value)) return '—';
  if (Math.abs(value) >= 1) return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
  return `$${value.toFixed(6)}`;
};

const formatPercent = (value: number | null | undefined, showSign = false): string => {
  if (value == null || !Number.isFinite(value)) return '—';
  const prefix = showSign && value > 0 ? '+' : '';
  return `${prefix}${value.toFixed(2)}%`;
};

const formatMoney = (value: number | null | undefined): string => {
  if (value == null || !Number.isFinite(value)) return '$0.00';
  const prefix = value > 0 ? '+$' : value < 0 ? '-$' : '$';
  return `${prefix}${Math.abs(value).toFixed(2)}`;
};

const toPositionForm = (item: TrackingWatchlistItem): PositionFormState => ({
  position_side: item.position_side || 'SHORT',
  entry_price: item.entry_price != null ? String(item.entry_price) : item.source_price != null ? String(item.source_price) : '',
  quantity: item.quantity != null ? String(item.quantity) : '',
  notional: item.notional != null ? String(item.notional) : '',
  leverage: item.leverage != null ? String(item.leverage) : '1',
  stop_loss: item.stop_loss != null ? String(item.stop_loss) : '',
  take_profit: item.take_profit != null ? String(item.take_profit) : item.source_target_price != null ? String(item.source_target_price) : '',
  notes: item.notes || '',
});

const riskClass = (risk?: string | null): string => {
  if (!risk) return 'border-slate-700 bg-slate-800 text-slate-400';
  if (risk === 'CRITICAL') return 'border-red-600/50 bg-red-950/60 text-red-300';
  if (risk === 'HIGH') return 'border-amber-600/50 bg-amber-950/60 text-amber-300';
  if (risk === 'MEDIUM') return 'border-yellow-600/50 bg-yellow-950/60 text-yellow-300';
  return 'border-emerald-600/50 bg-emerald-950/60 text-emerald-300';
};

export const TrackingWatchlist: React.FC<TrackingWatchlistProps> = ({
  items,
  isLoading,
  updatingId,
  onRefresh,
  onSelectCoin,
  onUpdateItem,
  onRemoveItem,
  onAddTracking,
}) => {
  const { language, t } = useTranslation();
  const vi = language === 'vi';

  const [filter, setFilter] = useState<TrackingFilter>('ACTIVE');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<PositionFormState>(emptyForm);
  const [newSymbol, setNewSymbol] = useState('');
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    const key = 'dao_vang_tracking_visitor';
    const visitor = localStorage.getItem(key) || crypto.randomUUID();
    localStorage.setItem(key, visitor);
    void fetch('/api/tracking-usage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ visitor_id: visitor }),
    }).catch(() => {});
  }, []);

  const getStatusLabel = (status: TrackingStatus, lang: Language): string => {
    const map: Record<TrackingStatus, Record<string, string>> = {
      WATCHING: { vi: 'ĐANG THEO DÕI', en: 'WATCHING', zh: '观察中', ko: '관찰 중' },
      IN_POSITION: { vi: 'ĐANG VÀO LỆNH', en: 'IN POSITION', zh: '持仓中', ko: '포지션 보유' },
      CLOSED: { vi: 'ĐÃ ĐÓNG', en: 'CLOSED', zh: '已结平', ko: '종료됨' },
    };
    return map[status]?.[lang] ?? map[status]?.['en'] ?? status;
  };

  const getSignalStatusLabel = (status: string, lang: Language): string => {
    const map: Record<string, Record<string, string>> = {
      ACTIVE: { vi: 'Radar còn hiệu lực', en: t('track_status_radar_active'), zh: '雷达有效', ko: '레이더 유효' },
      HIT: { vi: 'Radar đã trúng mục tiêu', en: t('track_status_target_hit'), zh: '已达回撤目标', ko: '목표 도달' },
      MISS: { vi: 'Không đạt điều kiện mục tiêu', en: 'Target conditions not met' },
      EXPIRED: { vi: 'Hết hạn · chưa có kết quả', en: 'Expired · outcome unverified', zh: '已过期 · 结果未验证', ko: '만료 · 결과 미검증' },
      NO_SIGNAL: { vi: 'Theo dõi thủ công', en: 'Manual Track', zh: '手动跟踪', ko: '수동 추적' },
    };
    return map[status]?.[lang] ?? map[status]?.['en'] ?? status;
  };

  const stats = useMemo(() => {
    const activeItems = items.filter((item) => item.status !== 'CLOSED');
    const positionsList = items.filter((item) => item.status === 'IN_POSITION');
    return {
      total: activeItems.length,
      activeSignals: activeItems.filter((item) => item.signal_status === 'ACTIVE').length,
      positions: positionsList.length,
      attention: activeItems.filter(
        (item) =>
          item.signal_status === 'EXPIRED' ||
          (item.position_change_pct != null && item.position_change_pct < 0) ||
          item.market_data_status === 'STALE'
      ).length,
    };
  }, [items]);

  const totalPnl = useMemo(() => {
    return items
      .filter((item) => item.status === 'IN_POSITION')
      .reduce((sum, item) => sum + (item.position_pnl ?? 0), 0);
  }, [items]);

  const totalNotional = useMemo(() => {
    return items
      .filter((item) => item.status === 'IN_POSITION')
      .reduce((sum, item) => sum + (item.notional ?? (item.entry_price && item.quantity ? item.entry_price * item.quantity : 0)), 0);
  }, [items]);

  const pnlSummary = useMemo(() => {
    const activePositions = items.filter((item) => item.status === 'IN_POSITION');
    const winning = activePositions.filter((item) => (item.position_pnl ?? 0) > 0).length;
    const losing = activePositions.filter((item) => (item.position_pnl ?? 0) < 0).length;
    return { winning, losing, count: activePositions.length };
  }, [items]);

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      if (filter === 'ALL') return true;
      if (filter === 'ACTIVE') return item.status !== 'CLOSED';
      return item.status === filter;
    });
  }, [filter, items]);

  const openEditor = (item: TrackingWatchlistItem) => {
    setEditingId(item.id);
    setForm(toPositionForm(item));
  };

  const closeEditor = () => {
    setEditingId(null);
    setForm(emptyForm);
  };

  const submitPosition = async (event: React.FormEvent, item: TrackingWatchlistItem) => {
    event.preventDefault();
    const entryPrice = numberValue(form.entry_price);
    if (entryPrice == null || !Number.isFinite(entryPrice) || entryPrice <= 0) return;
    const updated = await onUpdateItem(item.id, {
      status: 'IN_POSITION',
      position_side: form.position_side,
      entry_price: entryPrice,
      quantity: numberValue(form.quantity),
      notional: numberValue(form.notional),
      leverage: numberValue(form.leverage) ?? 1,
      stop_loss: numberValue(form.stop_loss),
      take_profit: numberValue(form.take_profit),
      notes: form.notes,
    });
    if (updated) closeEditor();
  };

  const closeTracking = async (item: TrackingWatchlistItem) => {
    await onUpdateItem(item.id, { status: 'CLOSED' });
  };

  const getFilterButtons = (): Array<[TrackingFilter, string, number]> => [
    ['ACTIVE', t('track_filter_active'), stats.total],
    ['ALL', language === 'vi' ? 'Toàn bộ lịch sử' : 'All history', items.length],
    ['IN_POSITION', t('track_filter_in_pos'), stats.positions],
    ['WATCHING', t('track_filter_watching'), stats.total - stats.positions],
    ['CLOSED', t('track_filter_closed'), items.filter((i) => i.status === 'CLOSED').length],
  ];

  return (
    <div className="flex-1 min-h-0 overflow-y-auto space-y-3 pr-1">
      {/* 1. Header Toolbar */}
      <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="flex items-center gap-2 text-sm sm:text-base font-extrabold uppercase tracking-wide text-slate-100">
              <Target className="h-4 w-4 text-amber-400" />
              {vi ? 'Quản lý Vị thế & Danh mục' : 'Positions & Watchlist'}
            </h2>
            <span className="rounded-full bg-slate-800 px-2 py-0.5 font-mono text-[11px] font-bold text-amber-300">
              {stats.total}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-slate-400">
            {vi
              ? 'Theo dõi PnL trực tiếp, quản trị lệnh Short/Long & kiểm chứng tín hiệu Radar'
              : 'Live PnL tracking, position management & radar verification'}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onRefresh}
            disabled={isLoading}
            className="inline-flex h-8 items-center justify-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900/90 px-3 text-xs font-semibold text-slate-300 transition hover:border-amber-500/60 hover:text-amber-300 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            {t('track_refresh_price')}
          </button>
        </div>
      </div>

      {/* 2. Quick Add Bar */}
      {onAddTracking && (
        <form
          className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-800/90 bg-slate-900/40 p-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (!newSymbol.trim()) return;
            setAdding(true);
            void Promise.resolve(onAddTracking(newSymbol.trim().toUpperCase()))
              .then((ok) => {
                if (ok !== false) setNewSymbol('');
              })
              .finally(() => setAdding(false));
          }}
        >
          <label className="flex items-center gap-2 text-xs font-medium text-slate-300">
            <span className="whitespace-nowrap">{vi ? 'Coin muốn theo dõi' : 'Coin to follow'}</span>
            <input
              required
              pattern="[A-Za-z0-9]{2,30}"
              maxLength={30}
              placeholder="BTC, ETH, SOL…"
              value={newSymbol}
              onChange={(e) => setNewSymbol(e.target.value)}
              className="h-8 w-36 sm:w-48 rounded-lg border border-slate-700 bg-slate-950 px-2.5 font-mono text-xs text-slate-100 placeholder:text-slate-600 focus:border-amber-500 focus:outline-none"
            />
          </label>

          <div className="hidden sm:flex items-center gap-1 text-[11px] font-mono">
            {['BTC', 'ETH', 'SOL', 'DOGE'].map((sym) => (
              <button
                key={sym}
                type="button"
                onClick={() => setNewSymbol(sym)}
                className="rounded px-1.5 py-0.5 bg-slate-800/70 hover:bg-slate-700 text-slate-400 hover:text-slate-200 transition"
              >
                {sym}
              </button>
            ))}
          </div>

          <button
            disabled={adding || !newSymbol.trim()}
            className="inline-flex h-8 items-center gap-1 rounded-lg bg-amber-500 px-3 text-xs font-bold text-slate-950 transition hover:bg-amber-400 disabled:opacity-40"
          >
            <Plus className="h-3.5 w-3.5" />
            {adding ? '…' : vi ? 'Thêm coin theo dõi' : 'Follow coin'}
          </button>
        </form>
      )}

      {/* 3. KPI Summary Bar (Financial First) */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {/* Total PnL */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3 flex flex-col justify-between">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            {vi ? 'Tổng PnL (Tạm tính)' : 'Total Unrealized PnL'}
          </span>
          <div className="my-1">
            <span className={`font-mono text-xl font-black ${totalPnl > 0 ? 'text-emerald-400' : totalPnl < 0 ? 'text-rose-400' : 'text-slate-300'}`}>
              {formatMoney(totalPnl)}
            </span>
          </div>
          <span className="text-[10px] text-slate-500 font-mono">
            {pnlSummary.count > 0
              ? `${pnlSummary.winning}W - ${pnlSummary.losing}L (${pnlSummary.count} lệnh)`
              : vi ? 'Chưa mở vị thế' : 'No open trades'}
          </span>
        </div>

        {/* Positions In-Position */}
        <div className="rounded-xl border border-purple-800/40 bg-purple-950/20 p-3 flex flex-col justify-between">
          <span className="text-[10px] font-bold uppercase tracking-wider text-purple-300/80">
            {t('track_stat_in_pos')}
          </span>
          <div className="my-1 font-mono text-xl font-black text-purple-300">
            {stats.positions}
          </div>
          <span className="text-[10px] text-purple-400/80 font-mono">
            {totalNotional > 0
              ? `${vi ? 'Quy mô: ' : 'Size: '}${formatMoney(totalNotional)}`
              : vi ? 'Đang vào lệnh' : 'Active positions'}
          </span>
        </div>

        {/* Watching Radar */}
        <div className="rounded-xl border border-sky-800/40 bg-sky-950/20 p-3 flex flex-col justify-between">
          <span className="text-[10px] font-bold uppercase tracking-wider text-sky-300/80">
            {vi ? 'Đang Quan Sát' : 'Watching Setups'}
          </span>
          <div className="my-1 font-mono text-xl font-black text-sky-300">
            {stats.total - stats.positions}
          </div>
          <span className="text-[10px] text-sky-400/80 font-mono">
            {stats.activeSignals} {vi ? 'tín hiệu hiệu lực' : 'active signals'}
          </span>
        </div>

        {/* Attention Needed */}
        <div className="rounded-xl border border-amber-800/40 bg-amber-950/20 p-3 flex flex-col justify-between">
          <span className="text-[10px] font-bold uppercase tracking-wider text-amber-300/80">
            {t('track_stat_attention')}
          </span>
          <div className="my-1 font-mono text-xl font-black text-amber-300">
            {stats.attention}
          </div>
          <span className="text-[10px] text-amber-400/80 font-mono">
            {vi ? 'Hết hạn hoặc PnL âm' : 'Expired or in drawdown'}
          </span>
        </div>
      </div>

      {/* 4. Filter Navigation Pills */}
      <div className="flex items-center gap-1 overflow-x-auto rounded-xl border border-slate-800 bg-slate-950 p-1 [&::-webkit-scrollbar]:hidden">
        {getFilterButtons().map(([value, label, count]) => (
          <button
            key={value}
            type="button"
            aria-label={label}
            onClick={() => setFilter(value)}
            className={`flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
              filter === value
                ? 'bg-amber-500 text-slate-950 shadow-sm'
                : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
            }`}
          >
            <span>{label}</span>
            <span
              aria-hidden="true"
              className={`rounded-full px-1.5 py-0.2 text-[10px] font-mono ${
                filter === value ? 'bg-slate-950/20 text-slate-950' : 'bg-slate-800 text-slate-400'
              }`}
            >
              {count}
            </span>
          </button>
        ))}
      </div>

      {/* 5. Positions & Watchlist Items */}
      {isLoading && items.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-950 p-10 text-center text-xs text-slate-500">
          <Loader2 className="mx-auto mb-2 h-5 w-5 animate-spin text-amber-400" />
          {t('track_empty_desc')}
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-800 bg-slate-950/60 p-10 text-center">
          <Eye className="mx-auto mb-2 h-6 w-6 text-slate-600" />
          <div className="text-xs font-semibold text-slate-400">{t('track_empty_title')}</div>
          <div className="mt-1 text-[11px] text-slate-600">{t('track_empty_desc')}</div>
        </div>
      ) : (
        <div className="space-y-2.5">
          {filteredItems.map((item) => {
            const isUpdating = updatingId === item.id;
            const progress =
              item.signal_progress_pct == null ? 0 : Math.min(100, Math.max(0, item.signal_progress_pct));
            const positiveSignalChange = (item.signal_change_pct ?? 0) >= 0;
            const pnlValue = item.position_pnl ?? item.position_change_pct ?? 0;
            const positivePnl = pnlValue >= 0;
            const PnlIcon = pnlValue > 0 ? ArrowUpRight : pnlValue < 0 ? ArrowDownRight : Minus;

            return (
              <article
                key={item.id}
                id={`tracking-${item.id}`}
                data-testid={`tracking-${item.symbol}`}
                className="rounded-xl border border-slate-800/90 bg-slate-900/60 p-3.5 shadow-md transition hover:border-slate-700/80"
              >
                {/* Warning if price data stale */}
                {item.market_data_status !== 'FRESH' && (
                  <div
                    role="status"
                    className="mb-2.5 flex items-center gap-2 rounded-lg border border-amber-800/60 bg-amber-950/30 px-3 py-1.5 text-xs text-amber-200"
                  >
                    <AlertCircle className="h-3.5 w-3.5 shrink-0 text-amber-400" />
                    <span>
                      {vi
                        ? item.market_data_status === 'STALE'
                          ? 'Dữ liệu giá đã cũ — chưa tính lãi/lỗ hiện tại. Hãy làm mới trước khi đánh giá.'
                          : 'Chưa xác minh được giá mới — chưa tính lãi/lỗ hiện tại.'
                        : item.market_data_status === 'STALE'
                        ? 'Price data is stale. Current P&L is unavailable until refreshed.'
                        : 'A fresh price could not be verified. Current P&L is unavailable.'}
                    </span>
                  </div>
                )}

                {/* Card Header Row: Symbol, Badges & Quick Actions */}
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/70 pb-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => onSelectCoin(item.symbol)}
                      className="font-mono text-base font-black tracking-wide text-amber-300 hover:text-amber-200 hover:underline"
                    >
                      {item.symbol}
                    </button>

                    {/* Status Badge */}
                    <span
                      className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-bold ${
                        item.status === 'IN_POSITION'
                          ? 'border border-purple-700/60 bg-purple-950/60 text-purple-300'
                          : item.status === 'CLOSED'
                          ? 'border border-slate-700 bg-slate-900 text-slate-500'
                          : 'border border-amber-700/60 bg-amber-950/60 text-amber-300'
                      }`}
                    >
                      {item.status === 'IN_POSITION'
                        ? `${item.position_side || 'SHORT'}${item.leverage ? ` · ${item.leverage}x` : ''}`
                        : getStatusLabel(item.status, language)}
                    </span>

                    {/* Risk Badge */}
                    <span className={`rounded border px-1.5 py-0.5 text-[9px] font-bold ${riskClass(item.source_risk_level)}`}>
                      {item.source_risk_level || '—'}
                    </span>

                    {/* Signal Status Chip */}
                    <span className="text-[11px] text-slate-400 font-medium">
                      {getSignalStatusLabel(item.signal_status, language)}
                    </span>
                  </div>

                  {/* Right: Action Buttons */}
                  <div className="flex items-center gap-1.5">
                    {item.status === 'IN_POSITION' && (
                      <button
                        type="button"
                        onClick={() => void closeTracking(item)}
                        disabled={isUpdating}
                        className="inline-flex h-7 items-center gap-1 rounded-lg border border-emerald-800/70 bg-emerald-950/50 px-2.5 text-xs font-bold text-emerald-300 transition hover:bg-emerald-900/60 disabled:opacity-50"
                      >
                        <CheckCircle2 className="h-3 w-3" />
                        {t('track_btn_close_pos')}
                      </button>
                    )}

                    {item.status !== 'CLOSED' && (
                      <button
                        type="button"
                        onClick={() => openEditor(item)}
                        disabled={isUpdating}
                        className="inline-flex h-7 items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-2.5 text-xs font-semibold text-slate-300 transition hover:border-amber-500/60 hover:text-amber-300 disabled:opacity-50"
                      >
                        {isUpdating ? <Loader2 className="h-3 w-3 animate-spin" /> : <Pencil className="h-3 w-3" />}
                        {language === 'vi' ? 'Ghi chép vị thế' : 'Position notes'}
                      </button>
                    )}

                    {item.status === 'WATCHING' && item.paper_trade?.status !== 'OPEN' && (
                      <button
                        type="button"
                        onClick={() => void onRemoveItem(item.id)}
                        disabled={isUpdating}
                        className="inline-flex h-7 items-center gap-1 rounded-lg border border-red-900/60 bg-red-950/30 px-2.5 text-xs font-semibold text-red-300 transition hover:bg-red-950 disabled:opacity-50"
                        title={t('track_btn_unfollow')}
                      >
                        {isUpdating ? <Loader2 className="h-3 w-3 animate-spin" /> : <EyeOff className="h-3 w-3" />}
                        {t('track_btn_unfollow')}
                      </button>
                    )}

                    {item.status === 'CLOSED' && !item.archived_at && (
                      <button
                        type="button"
                        onClick={() => void onRemoveItem(item.id)}
                        disabled={isUpdating}
                        className="inline-flex h-7 items-center gap-1 rounded-lg border border-red-900/60 bg-red-950/30 px-2.5 text-xs font-semibold text-red-300 transition hover:bg-red-950 disabled:opacity-50"
                      >
                        <Archive className="h-3 w-3" />
                        {language === 'vi' ? 'Lưu trữ' : 'Archive'}
                      </button>
                    )}
                  </div>
                </div>

                {/* Metrics Grid (4 Key Columns) */}
                <div className="mt-2.5 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {/* Col 1: Current Price */}
                  <div className="rounded-lg border border-slate-800/80 bg-slate-900/70 p-2.5">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      {t('track_card_cur_price')}
                    </div>
                    <div className="mt-1 font-mono text-sm font-black text-slate-100">
                      {formatPrice(item.current_price)}
                    </div>
                    <div className={`mt-0.5 text-[11px] font-mono font-semibold ${positiveSignalChange ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {formatPercent(item.signal_change_pct, true)}
                    </div>
                  </div>

                  {/* Col 2: Entry Price / Signal Discovery Price */}
                  <div className="rounded-lg border border-slate-800/80 bg-slate-900/70 p-2.5">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      {item.status === 'IN_POSITION' ? (vi ? 'Giá Entry' : 'Entry Price') : (vi ? 'Giá phát hiện' : 'Signal Price')}
                    </div>
                    <div className="mt-1 font-mono text-sm font-black text-amber-300">
                      {formatPrice(item.status === 'IN_POSITION' ? item.entry_price : item.source_price)}
                    </div>
                    <div className="mt-0.5 text-[10px] text-slate-400 font-mono">
                      {item.status === 'IN_POSITION'
                        ? item.quantity ? `KL: ${item.quantity}` : (item.notional ? formatMoney(item.notional) : '—')
                        : `${(item.source_probability ? item.source_probability * 100 : 0).toFixed(1)}% tin cậy`}
                    </div>
                  </div>

                  {/* Col 3: Target & Progress */}
                  <div className="rounded-lg border border-slate-800/80 bg-slate-900/70 p-2.5">
                    <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      <span>{t('track_card_target_prog')}</span>
                      <span className="font-mono text-amber-300">{formatPercent(item.signal_progress_pct)}</span>
                    </div>
                    <div className="mt-1 font-mono text-sm font-black text-slate-200">
                      {formatPrice(item.source_target_price)}
                    </div>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-800">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-amber-500 to-emerald-400"
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                  </div>

                  {/* Col 4: Position PnL */}
                  <div className="rounded-lg border border-slate-800/80 bg-slate-900/70 p-2.5">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      {t('track_card_pos_pnl')}
                    </div>
                    {item.status === 'IN_POSITION' ? (
                      <>
                        <div className={`mt-0.5 flex items-center gap-1 font-mono text-sm font-black ${positivePnl ? 'text-emerald-400' : 'text-rose-400'}`}>
                          <PnlIcon className="h-3.5 w-3.5" />
                          <span>{formatPercent(item.position_change_pct, true)}</span>
                        </div>
                        <div className={`mt-0.5 text-[10px] font-mono font-semibold ${positivePnl ? 'text-emerald-400/90' : 'text-rose-400/90'}`}>
                          ROI {formatPercent(item.position_roi_pct, true)} · {formatMoney(item.position_pnl)}
                        </div>
                      </>
                    ) : (
                      <div className="mt-1 text-xs text-slate-500 font-medium">
                        {t('track_no_position')}
                      </div>
                    )}
                  </div>
                </div>

                {/* Compact Info Footer: SL/TP, Validity, Time & Reason */}
                <div className="mt-2.5 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-[11px] text-slate-400 border-t border-slate-800/60 pt-2">
                  <div className="flex flex-wrap items-center gap-3">
                    {item.status === 'IN_POSITION' && (item.stop_loss || item.take_profit) && (
                      <span className="font-mono text-slate-300">
                        {item.stop_loss && <span className="text-rose-400 mr-2">SL: {formatPrice(item.stop_loss)}</span>}
                        {item.take_profit && <span className="text-emerald-400">TP: {formatPrice(item.take_profit)}</span>}
                      </span>
                    )}
                    <span className="inline-flex items-center gap-1 text-slate-400">
                      <Clock3 className="h-3 w-3 text-sky-400" />
                      {item.validity_hours_left == null
                        ? t('feed_no_matching')
                        : item.validity_hours_left > 0
                        ? `${t('feed_left')} ${item.validity_hours_left.toFixed(1)}h`
                        : t('feed_tag_expired')}
                    </span>
                    {item.last_market_update && (
                      <span className="text-slate-500">
                        {t('col_time')} {formatSystemDateTime(item.last_market_update)}
                      </span>
                    )}
                  </div>

                  {item.source_reason && (
                    <span className="text-slate-400/90 truncate max-w-xs sm:max-w-md" title={item.source_reason}>
                      {item.source_reason}
                    </span>
                  )}
                </div>

                {/* Sub-component: Evidence & Simulation Hub */}
                <TrackingJourney item={item} onRefresh={onRefresh} onUpdate={onUpdateItem} />

                {/* Inline Position Editor Modal / Drawer */}
                {editingId === item.id && (
                  <form
                    onSubmit={(event) => void submitPosition(event, item)}
                    className="mt-3 rounded-xl border border-amber-800/60 bg-amber-950/20 p-3.5 space-y-2.5"
                  >
                    <div className="flex items-center justify-between border-b border-amber-800/40 pb-2">
                      <div className="text-xs font-bold text-amber-300 flex items-center gap-1.5">
                        <Pencil className="h-3.5 w-3.5" />
                        <span>{t('track_form_title')} {item.symbol}</span>
                      </div>
                      <button type="button" onClick={closeEditor} className="text-slate-400 hover:text-slate-200">
                        <X className="h-4 w-4" />
                      </button>
                    </div>

                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                      <label className="text-[10px] text-slate-300 font-medium">
                        {t('track_form_side')}
                        <select
                          value={form.position_side}
                          onChange={(event) => setForm((prev) => ({ ...prev, position_side: event.target.value as 'LONG' | 'SHORT' }))}
                          className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs font-mono font-bold text-slate-100"
                        >
                          <option value="SHORT">SHORT 📉</option>
                          <option value="LONG">LONG 📈</option>
                        </select>
                      </label>

                      <label className="text-[10px] text-slate-300 font-medium">
                        {t('track_form_entry')}
                        <input
                          required
                          type="number"
                          step="any"
                          min="0"
                          value={form.entry_price}
                          onChange={(event) => setForm((prev) => ({ ...prev, entry_price: event.target.value }))}
                          className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs font-mono text-slate-100"
                        />
                      </label>

                      <label className="text-[10px] text-slate-300 font-medium">
                        {t('track_form_qty')}
                        <input
                          type="number"
                          step="any"
                          min="0"
                          value={form.quantity}
                          onChange={(event) => setForm((prev) => ({ ...prev, quantity: event.target.value }))}
                          className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs font-mono text-slate-100"
                        />
                      </label>

                      <label className="text-[10px] text-slate-300 font-medium">
                        {t('track_notional_usdt')}
                        <input
                          type="number"
                          step="any"
                          min="0"
                          value={form.notional}
                          onChange={(event) => setForm((prev) => ({ ...prev, notional: event.target.value }))}
                          className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs font-mono text-slate-100"
                        />
                      </label>

                      <label className="text-[10px] text-slate-300 font-medium">
                        {t('track_form_leverage')}
                        <input
                          type="number"
                          step="any"
                          min="1"
                          value={form.leverage}
                          onChange={(event) => setForm((prev) => ({ ...prev, leverage: event.target.value }))}
                          className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs font-mono text-slate-100"
                        />
                      </label>

                      <label className="text-[10px] text-slate-300 font-medium">
                        {t('track_stop_loss_label')}
                        <input
                          type="number"
                          step="any"
                          min="0"
                          value={form.stop_loss}
                          onChange={(event) => setForm((prev) => ({ ...prev, stop_loss: event.target.value }))}
                          className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs font-mono text-slate-100"
                        />
                      </label>

                      <label className="text-[10px] text-slate-300 font-medium">
                        {t('track_take_profit_label')}
                        <input
                          type="number"
                          step="any"
                          min="0"
                          value={form.take_profit}
                          onChange={(event) => setForm((prev) => ({ ...prev, take_profit: event.target.value }))}
                          className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs font-mono text-slate-100"
                        />
                      </label>

                      <label className="text-[10px] text-slate-300 font-medium">
                        {t('track_form_notes')}
                        <input
                          value={form.notes}
                          onChange={(event) => setForm((prev) => ({ ...prev, notes: event.target.value }))}
                          placeholder="SL chặt, đợi retest..."
                          className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-100"
                        />
                      </label>
                    </div>

                    <div className="flex items-center justify-between gap-2 pt-1">
                      <span className="text-[10px] text-slate-500">
                        {t('track_form_disclaimer')}
                      </span>
                      <button
                        type="submit"
                        disabled={isUpdating}
                        className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-amber-500 px-4 text-xs font-bold text-slate-950 hover:bg-amber-400 disabled:opacity-50 transition"
                      >
                        <Activity className="h-3.5 w-3.5" />
                        {t('track_form_save')}
                      </button>
                    </div>
                  </form>
                )}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
};
