export type Trade = {
  id: string; symbol: string; status: string; created_at: string; closed_at?: string;
  entry_price?: number; remaining_qty?: number; filled_qty?: number; target: number;
  tp_price?: number; funding?: number; entry_fee?: number; exit_fee?: number;
  net_pnl?: number; unrealized?: number | null; mark_price?: number | null;
  liquidation_price?: number | null; entry_id?: string; tp_id?: string;
  tp_status?: string; last_reconciled_at?: string;
  signal?: { event_id?: string; manifest_id?: string };
};
export type TradingSnapshot = {
  read_only?: boolean; connection_error?: string;
  account_mode?: { hedge?: boolean; multi_assets?: boolean };
  income_health?: { healthy?: boolean; error?: string };
  open_orders?: { orderId: number; symbol: string; side: string; type: string; price: string; origQty: string; executedQty: string; status: string }[];
  environment: 'simulation' | 'demo' | 'live'; enabled: boolean; healthy: boolean;
  account_fresh: boolean; account_age_seconds: number | null; generated_at: string;
  config: { max_positions: number }; account: {
    equity: number; wallet: number; available: number; unrealized: number;
    peak: number; drawdown: number; at: string; maintenance_margin?: number;
  } | null;
  pause: { paused?: boolean; reason?: string }; trades: Trade[]; manifest_id: string | null;
  live_gate: { eligible: boolean; reasons: string[] }; source_health: { healthy?: boolean };
  equity_curve: { at: string; equity: number | null; drawdown: number | null }[];
  totals: { recorded_fees: number | null; recorded_funding: number | null; closed_count: number;
    wins: number; closed_net_pnl: number | null; equity_change: number | null; observed_since: string | null };
  progress: { manifest_loaded: boolean; observed_days: number; independent_events: number;
    time_windows: number; required_days: number; required_events: number; required_windows: number };
  setup: { credentials_present: boolean; manifest_loaded: boolean; worker_enabled: boolean; account_observed: boolean };
  activity: { seq: number; at: string; kind: string; reason?: string }[];
  commands: { id: string; at: string; action: string; status: string }[];
  recent_signals: { event_id: string; symbol: string; at: string; eligible: boolean; decision: string; reasons: string[] }[];
  trade_history_truncated: boolean;
  unmanaged_positions: { symbol: string; quantity: number | null; unrealized: number | null; mark_price: number | null; entry_price?: number | null; side?: string; margin_asset?: string }[];
};

const messages: Record<string, string> = {
  user_paused: 'Bạn đã dừng mở lệnh mới', drawdown_20_percent: 'Tài sản giảm 20% từ đỉnh',
  live_gate_failed: 'Chưa đạt điều kiện tiền thật', live_not_activated: 'Chưa kích hoạt tiền thật',
  evidence_required: 'Chưa có báo cáo nghiệm thu', pinned_evidence_required: 'Thiếu báo cáo đã xác minh',
  financial_evidence_unverified: 'Chưa xác minh kết quả sau chi phí', source_unverified: 'Chưa xác minh nguồn dữ liệu',
  forward_period_too_short: 'Chưa đủ 28 ngày quan sát', independent_events_insufficient: 'Chưa đủ 100 sự kiện độc lập',
  positive_lower_confidence_bound_required: 'Chưa chứng minh lợi thế với độ tin cậy 95%',
  net_equity_not_positive: 'Tài sản ròng chưa cao hơn vốn ban đầu', drawdown_gate_failed: 'Mức giảm tài sản chưa đạt yêu cầu',
  service_error: 'Dịch vụ gặp lỗi; cần kiểm tra', reconciliation_required: 'Cần đối soát với sàn',
  tp_status_unknown: 'Chưa xác minh trạng thái TP', restored_requires_review: 'Cần kiểm tra sau phục hồi',
  unmanaged_position: 'Có vị thế ngoài sổ của bot', scanner_source_unavailable: 'Nguồn tín hiệu chưa sẵn sàng',
  open: 'Đang mở', closed: 'Đã đóng', rejected: 'Bị từ chối', intent: 'Đã lưu ý định', submitted: 'Đã gửi lệnh',
  pending: 'Đang chờ', done: 'Đã xử lý', paused: 'Dừng mở mới', signal_decision: 'Xử lý tín hiệu',
  command_result: 'Kết quả thao tác', reconcile_error: 'Lỗi đối soát', user_resumed: 'Bật lại mở mới',
  pause: 'Dừng mở mới', resume: 'Bật lại', close: 'Đóng thủ công',
  NEW: 'Đang chờ khớp', PARTIALLY_FILLED: 'Khớp một phần', FILLED: 'Đã khớp',
  CANCELED: 'Đã hủy', EXPIRED: 'Đã hết hạn', REJECTED: 'Sàn từ chối',
  account_read_only: 'Chỉ theo dõi tài khoản, giao dịch đang tắt',
  monitor_credentials_missing: 'Chưa nhập khóa API Binance thật trên máy',
  'binance_error_-2015': 'Khóa API, quyền đọc Futures hoặc IP chưa được Binance chấp nhận',
  'binance_error_-1021': 'Đồng hồ máy lệch so với Binance; cần đồng bộ thời gian',
  'binance_error_-1022': 'Binance chưa chấp nhận chữ ký; kiểm tra API Secret HMAC',
  account_monitor_unavailable: 'Chưa đọc được tài khoản; kiểm tra kết nối',
};
export const explainTrading = (value?: string) => !value ? '—' : messages[value] ?? value;
export const tradingMoney = (value?: number | null) => value == null || !Number.isFinite(value) ? '—' : `${value.toFixed(2)} USDT`;
export const tradingTime = (value?: string | null) => value ? new Date(value).toLocaleString('vi-VN') : 'Chưa có';
