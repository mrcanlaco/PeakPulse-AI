import type { CandidateCoin, SignalItem, TrackingWatchlistItem } from '../types';

const GUEST_TRACKING_STORAGE_KEY = 'dao_vang_guest_tracking_watchlist_v1';

export interface GuestAddTrackingPayload {
  source_prediction_id?: string | null;
  source_reason?: string;
  symbol: string;
  source?: 'radar' | 'manual';
  source_signal_time?: string | null;
  source_probability?: number | null;
  source_risk_level?: string | null;
  source_price?: number | null;
  source_target_price?: number | null;
  source_invalidation_time?: string | null;
}

export function loadGuestTrackingItems(): TrackingWatchlistItem[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(GUEST_TRACKING_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (item): item is TrackingWatchlistItem =>
        Boolean(item && typeof item === 'object' && typeof (item as TrackingWatchlistItem).id === 'string')
    );
  } catch {
    return [];
  }
}

export function saveGuestTrackingItems(items: TrackingWatchlistItem[]): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(GUEST_TRACKING_STORAGE_KEY, JSON.stringify(items));
  } catch {
    // Ignore storage quota errors in private browsing
  }
}

export function normalizeGuestSymbol(raw: string): string {
  const cleaned = raw.trim().toUpperCase().replace(/[^A-Z0-9_-]/g, '');
  if (!cleaned) return '';
  return cleaned.endsWith('USDT') ? cleaned : `${cleaned}USDT`;
}

export function addGuestTrackingItem(
  payload: GuestAddTrackingPayload,
  existingItems: TrackingWatchlistItem[]
): { items: TrackingWatchlistItem[]; item: TrackingWatchlistItem } {
  const symbol = normalizeGuestSymbol(payload.symbol);
  const nowIso = new Date().toISOString();
  const existingActive = existingItems.find(
    (entry) =>
      entry.status !== 'CLOSED' &&
      entry.symbol.toUpperCase() === symbol &&
      (entry.source_signal_time === (payload.source_signal_time ?? null) || !payload.source_signal_time)
  );

  if (existingActive) {
    const updated: TrackingWatchlistItem = {
      ...existingActive,
      source_reason: payload.source_reason ?? existingActive.source_reason,
      source_probability: payload.source_probability ?? existingActive.source_probability,
      source_risk_level: payload.source_risk_level ?? existingActive.source_risk_level,
      source_price: payload.source_price ?? existingActive.source_price,
      source_target_price: payload.source_target_price ?? existingActive.source_target_price,
      updated_at: nowIso,
    };
    const nextItems = existingItems.map((entry) => (entry.id === existingActive.id ? updated : entry));
    saveGuestTrackingItems(nextItems);
    return { items: nextItems, item: updated };
  }

  const newItem: TrackingWatchlistItem = {
    id: `guest-${symbol}-${Date.now()}`,
    symbol,
    source: payload.source || 'manual',
    source_prediction_id: payload.source_prediction_id ?? null,
    source_reason: payload.source_reason || '',
    source_signal_time: payload.source_signal_time ?? null,
    source_probability: payload.source_probability ?? null,
    source_risk_level: payload.source_risk_level ?? null,
    source_price: payload.source_price ?? null,
    source_target_price: payload.source_target_price ?? null,
    source_invalidation_time: payload.source_invalidation_time ?? null,
    status: 'WATCHING',
    position_side: 'SHORT',
    entry_price: payload.source_price ?? null,
    take_profit: payload.source_target_price ?? null,
    notes: '',
    created_at: nowIso,
    updated_at: nowIso,
    signal_status: payload.source === 'radar' ? 'ACTIVE' : 'NO_SIGNAL',
    notifications_enabled: true,
    notifications: [],
    checkpoints: {
      '24': { status: 'PENDING' },
      '48': { status: 'PENDING' },
    },
    paper_trade: null,
    current_price: payload.source_price ?? null,
    current_probability: payload.source_probability ?? null,
    current_risk_level: payload.source_risk_level ?? null,
    market_data_status: 'FRESH',
    last_market_update: nowIso,
  };

  const nextItems = [newItem, ...existingItems];
  saveGuestTrackingItems(nextItems);
  return { items: nextItems, item: newItem };
}

export function updateGuestTrackingItem(
  id: string,
  patch: Record<string, unknown>,
  existingItems: TrackingWatchlistItem[]
): { items: TrackingWatchlistItem[]; item: TrackingWatchlistItem | null } {
  const target = existingItems.find((entry) => entry.id === id);
  if (!target) return { items: existingItems, item: null };

  const nowIso = new Date().toISOString();
  const nextNotifications =
    patch.read_notifications === true && Array.isArray(target.notifications)
      ? target.notifications.map((n) => ({ ...n, read: true }))
      : target.notifications;

  const updated: TrackingWatchlistItem = {
    ...target,
    ...(typeof patch.status === 'string'
      ? { status: patch.status as TrackingWatchlistItem['status'] }
      : {}),
    ...(typeof patch.notes === 'string' ? { notes: patch.notes } : {}),
    ...(typeof patch.position_side === 'string'
      ? { position_side: patch.position_side as 'LONG' | 'SHORT' }
      : {}),
    ...(patch.entry_price !== undefined ? { entry_price: patch.entry_price as number | null } : {}),
    ...(patch.quantity !== undefined ? { quantity: patch.quantity as number | null } : {}),
    ...(patch.notional !== undefined ? { notional: patch.notional as number | null } : {}),
    ...(patch.leverage !== undefined ? { leverage: patch.leverage as number | null } : {}),
    ...(patch.stop_loss !== undefined ? { stop_loss: patch.stop_loss as number | null } : {}),
    ...(patch.take_profit !== undefined ? { take_profit: patch.take_profit as number | null } : {}),
    ...(typeof patch.notifications_enabled === 'boolean'
      ? { notifications_enabled: patch.notifications_enabled }
      : {}),
    ...(patch.feedback !== undefined
      ? { feedback: patch.feedback as TrackingWatchlistItem['feedback'] }
      : {}),
    ...(patch.paper_trade !== undefined
      ? { paper_trade: patch.paper_trade as TrackingWatchlistItem['paper_trade'] }
      : {}),
    notifications: nextNotifications,
    updated_at: nowIso,
  };

  const nextItems = existingItems.map((entry) => (entry.id === id ? updated : entry));
  saveGuestTrackingItems(nextItems);
  return { items: nextItems, item: updated };
}

export function removeGuestTrackingItem(
  id: string,
  existingItems: TrackingWatchlistItem[]
): TrackingWatchlistItem[] {
  const nowIso = new Date().toISOString();
  const nextItems = existingItems.map((entry) =>
    entry.id === id
      ? { ...entry, status: 'CLOSED' as const, archived_at: nowIso, updated_at: nowIso }
      : entry
  );
  saveGuestTrackingItems(nextItems);
  return nextItems;
}

export function enrichGuestTrackingItems(
  items: TrackingWatchlistItem[],
  signals: SignalItem[],
  candidates: CandidateCoin[]
): TrackingWatchlistItem[] {
  if (items.length === 0) return items;
  const nowIso = new Date().toISOString();
  const signalMap = new Map<string, SignalItem>();
  for (const sig of signals) {
    const sym = sig.symbol.toUpperCase();
    if (!signalMap.has(sym)) signalMap.set(sym, sig);
  }
  const candMap = new Map<string, CandidateCoin>();
  for (const cand of candidates) {
    candMap.set(cand.symbol.toUpperCase(), cand);
  }

  return items.map((item) => {
    const sym = item.symbol.toUpperCase();
    const sig = signalMap.get(sym);
    const cand = candMap.get(sym);
    const livePrice = cand?.price ?? sig?.signal_price ?? item.current_price ?? item.source_price ?? null;
    const liveProb =
      sig?.probability ??
      cand?.calibrated_probability ??
      cand?.model_probability ??
      item.current_probability ??
      item.source_probability ??
      null;
    const liveRisk = cand?.risk ?? sig?.risk_level ?? item.current_risk_level ?? item.source_risk_level ?? null;

    let signalChangePct = item.signal_change_pct ?? null;
    if (livePrice != null && item.source_price != null && item.source_price > 0) {
      signalChangePct = Number((((livePrice - item.source_price) / item.source_price) * 100).toFixed(2));
    }

    let positionPnl = item.position_pnl ?? null;
    let positionRoiPct = item.position_roi_pct ?? null;
    const refEntry = item.entry_price ?? item.source_price ?? null;
    if (livePrice != null && refEntry != null && refEntry > 0) {
      const sideMult = item.position_side === 'LONG' ? 1 : -1;
      const movePct = ((livePrice - refEntry) / refEntry) * 100 * sideMult;
      const lev = item.leverage && item.leverage > 0 ? item.leverage : 1;
      positionRoiPct = Number((movePct * lev).toFixed(2));
      if (item.notional && item.notional > 0) {
        positionPnl = Number(((item.notional * movePct) / 100).toFixed(2));
      }
    }

    return {
      ...item,
      current_price: livePrice,
      current_probability: liveProb,
      current_risk_level: liveRisk,
      signal_change_pct: signalChangePct,
      position_pnl: positionPnl,
      position_roi_pct: positionRoiPct,
      market_data_status: cand || sig ? 'FRESH' : item.market_data_status || 'STALE',
      last_market_update: cand || sig ? nowIso : item.last_market_update,
    };
  });
}
