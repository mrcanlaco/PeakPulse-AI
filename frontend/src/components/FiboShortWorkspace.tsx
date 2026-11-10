import React, { useEffect, useMemo, useState, Suspense } from 'react';
import {
  TrendingDown,
  Target,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Award,
  Activity,
  BarChart3,
  Layers,
  Lock,
  Sparkles,
  Cpu,
  Gauge,
  Database,
} from 'lucide-react';
import type { FiboHandoff, TradeSetup } from '../types';
import { useTranslation, type Language } from '../i18n/LanguageContext';

const CandlestickChart = React.lazy(() =>
  import('./CandlestickChart').then((m) => ({ default: m.CandlestickChart }))
);

interface SwingImpulseWave {
  symbol: string;
  timeframe: '4h' | '1d';
  prior_low_price: number;
  prior_low_time: string;
  prior_pump_pct: number;
  swing_high_price: number;
  swing_high_time: string;
  reversal_candle_time: string;
  reversal_candle_open: number;
  reversal_candle_close: number;
  reversal_candle_bearish: boolean;
  impulse_low_price: number;
  impulse_low_time: string;
  impulse_drop_pct: number;
  bars_since_swing_high: number;
  bars_since_impulse_low: number;
  wave_ker?: number;
  impulse_ker?: number;
  peak_ewmac_16_64?: number;
  cur_accel_4_16?: number;
  pst_pass?: boolean;
}

interface FibonacciLevels {
  level_1000: number;
  level_0886?: number;
  level_0786: number;
  level_0618: number;
  level_0500: number;
  level_0382: number;
  level_0236: number;
  level_0000: number;
  ext_1272: number;
  ext_1618: number;
  wave_range: number;
}

interface H1Confirmation {
  candle_time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  is_red_candle: boolean;
  no_gain_1h: boolean;
  price_ret_1h: number;
  touched_fibo_zone: boolean;
  max_pullback_fibo_ratio: number;
  current_fibo_ratio: number;
  cond1_bearish_pattern: boolean;
  pattern_name: string;
  pattern_name_vi: string;
  cond2_break_prev_low: boolean;
  break_description_vi: string;
  confirmed: boolean;
  confirmation_tier: 'COMBO_1_2' | 'CANDLE_PATTERN_1' | 'BREAK_STRUCTURE_2' | 'UNCONFIRMED';
  reason_vi: string;
  pullback_vol_ratio?: number;
  h1_body_ratio?: number;
}

interface FiboTradeSetup {
  entry_price: number;
  entry_zone_low: number;
  entry_zone_high: number;
  entry_zone: string;
  stop_loss: number;
  stop_loss_pct: number;
  sl_m6?: number;
  sl_m6_pct?: number;
  tp1: number;
  tp1_pct: number;
  tp2: number;
  tp2_pct: number;
  tp3: number;
  tp3_pct: number;
  rr_ratio: number;
  rr_tp1: number;
  rr_tp2: number;
  rr_tp3: number;
  rr_m6_tp1?: number;
  rr_m6_tp2?: number;
  atr_1h: number;
  conviction_tier?: string;
  recommended_risk_mult?: number;
  recommended_notional_pct?: number;
  risk_budget_pct?: number;
  max_notional_pct?: number;
  sl_within_cap?: boolean;
  max_hold_hours?: number;
}

export interface FiboShortSignalItem {
  id: string;
  symbol: string;
  higher_timeframe: '4h' | '1d';
  confirm_timeframe: '1h';
  stage: 'FIRED_CONFIRMED_SHORT' | 'ARMED_IN_FIBO_ZONE' | 'WATCHING_PULLBACK' | 'INVALIDATED';
  score: number;
  conviction_tier?: string;
  recommended_risk_mult?: number;
  signal_time: string;
  current_price: number;
  wave: SwingImpulseWave;
  fibo_levels: FibonacciLevels;
  h1_confirmation: H1Confirmation;
  trade_setup: FiboTradeSetup;
  alpha_layers?: Record<string, any>;
  eligible_milestones?: string[];
  matched_policies?: string[];
  primary_policy?: string;
  explanation_vi: string[];
  outcome?: Record<string, unknown> | null;
}

interface ShadowTrackMetric {
  track_id: string;
  label_vi: string;
  total_m1_signals: number;
  accepted_count: number;
  rejected_noise_count: number;
  active_count: number;
  closed_count: number;
  win_count: number;
  loss_count: number;
  win_rate_pct: number;
  avg_trade_return_pct: number;
  cum_nav_pnl_pct: number;
  simulated_equity: number;
  max_dd_pct: number;
  delta_nav_vs_legacy_pct: number;
}

interface ShadowSignalLedgerItem {
  id: string;
  symbol: string;
  higher_timeframe: string;
  confirmation_tier: string;
  signal_time: string;
  score: number;
  entry_price: number;
  current_price: number;
  price_move_pct: number;
  tp1: number;
  tp2: number;
  tp3: number;
  wave_ker: number;
  impulse_ker: number;
  legacy: {
    accepted: boolean;
    status: string;
    stop_loss: number;
    stop_loss_pct: number;
    notional_pct: number;
    tp1_hit: boolean;
    tp2_hit: boolean;
    tp3_hit: boolean;
    sl_hit: boolean;
    net_return_pct: number;
    nav_pnl_pct: number;
  };
  v4: {
    accepted_m6: boolean;
    accepted_sniper: boolean;
    accepted_elite_sniper: boolean;
    accepted_sniper_rr1_24h: boolean;
    primary_policy: string;
    matched_policies: string[];
    m6_rejection_reasons_vi: string[];
    sniper_rejection_reasons_vi: string[];
    rr1_rejection_reasons_vi: string[];
    status: string;
    sl_m6: number;
    sl_m6_pct: number;
    active_ratchet_sl: number;
    notional_pct: number;
    tp1_hit: boolean;
    tp2_hit: boolean;
    tp3_hit: boolean;
    sl_hit: boolean;
    be_stop_hit: boolean;
    tp1_trail_hit: boolean;
    raw_net_return_pct: number;
    m6_nav_pnl_pct: number;
    sniper_nav_pnl_pct: number;
    elite_sniper_nav_pnl_pct: number;
    sniper_rr1_nav_pnl_pct: number;
    delta_m6_vs_legacy_nav_pct: number;
    delta_sniper_vs_legacy_nav_pct: number;
  };
}

interface ShadowComparisonSummary {
  updated_at: string;
  total_fired_signals: number;
  tracks: ShadowTrackMetric[];
  signals_ledger: ShadowSignalLedgerItem[];
}

interface CandidateComparisonResponse {
  available?: boolean;
  enabled?: boolean;
  status?: string;
  generated_at?: string;
  champion_version?: string;
  challenger_version?: string;
  universe_count?: number;
  paired_count?: number;
  champion_selected?: number;
  challenger_selected?: number;
  overlap?: string[];
  challenger_only?: string[];
  champion_only?: string[];
  comparison?: {
    metrics?: Record<
      string,
      {
        precision_at_10?: number;
        event_recall?: number;
        anchor_precision?: number;
        anchor_recall?: number;
        episode_precision?: number;
        median_lead_time_minutes?: number;
        resolved?: number;
        selected_resolved?: number;
      }
    >;
  };
}

interface FiboSnapshotResponse {
  status: string;
  branch: string;
  branch_title_vi?: string;
  updated_at: string | null;
  scanned_symbols_count: number;
  total_signals: number;
  fired_count: number;
  armed_count: number;
  watching_count: number;
  policy_counts?: {
    sniper_risk: number;
    elite_sniper_risk: number;
    sniper_rr1_horizon24: number;
    m6_risk: number;
  };
  pit_universe?: {
    month: string | null;
    ranking_interval: string;
    member_count: number;
    wick_p90_max_pct: number;
    min_active_days: number;
  };
  shadow_comparison?: ShadowComparisonSummary;
  items: FiboShortSignalItem[];
}

interface BacktestSummaryStats {
  total_trades: number;
  win_count: number;
  loss_count: number;
  win_rate_pct: number;
  tp1_hit_rate_pct: number;
  tp2_hit_rate_pct: number;
  tp3_hit_rate_pct: number;
  stop_loss_rate_pct: number;
  avg_net_return_pct: number;
  median_net_return_pct: number;
  total_net_return_pct: number;
  avg_r_multiple: number;
  profit_factor: number;
  avg_hold_hours: number;
}

interface CoupledPolicyMetric {
  metric: {
    return_pct: number;
    max_dd_pct: number;
    trades: number;
    fees_pct: number;
    slippage_pct: number;
    funding_pct: number;
    gross_reference_pnl_pct: number;
    rejected?: Record<string, number>;
  };
  weekly?: {
    weeks: number;
    mean_log_return: number;
    ci95_low_1s: number;
    ci95_2s: [number, number];
  };
}

interface V421AuditData {
  version: string;
  coupled_portfolio: Record<string, Record<string, Record<string, CoupledPolicyMetric>>>;
  yearly_breakdown: Record<string, Record<string, Record<string, { return_pct: number; max_dd_pct: number; trades: number }>>>;
  ablation_milestones: Array<{
    id: string;
    label: string;
    trades_14c: number;
    win_rate_pct: number;
    net_ev_pct: number;
    pf: number;
    coupled_nav_pct: number;
    max_dd_pct: number;
  }>;
}

interface FiboBacktestResponse {
  status?: string;
  in_sample_window: {
    start_utc?: string;
    end_utc: string;
    oos_reserved_from_utc: string;
    oos_touched: boolean;
    note?: string;
  };
  symbols_tested?: string[];
  overall: BacktestSummaryStats;
  by_timeframe?: Record<string, BacktestSummaryStats>;
  by_confirmation_tier?: Record<string, BacktestSummaryStats>;
  by_symbol?: Record<string, BacktestSummaryStats>;
  recent_trades?: Array<{
    trade_id: string;
    symbol: string;
    higher_timeframe: string;
    confirmation_tier: string;
    pattern_name: string;
    entry_time: string;
    exit_time: string;
    entry_price: number;
    stop_loss: number;
    tp1: number;
    tp2: number;
    tp3: number;
    exit_price: number;
    outcome: string;
    net_return_pct: number;
    r_multiple: number;
    hold_hours: number;
    fibo_entry_ratio: number;
    impulse_drop_pct: number;
  }>;
  v4_0_21_audit?: V421AuditData;
}

interface PaperOosResponse {
  generated_at_utc?: string;
  health?: {
    code: string;
    severity: string;
    headline: string;
    detail: string;
    heartbeat_age_sec: number | null;
    engine_lag_sec: number | null;
    orders_allowed: boolean;
    live_signoff: string;
    sqlite_journal_ok?: boolean;
  };
  study?: {
    version: string;
    protocol_sha256: string;
    protocol_verified: boolean;
    start_utc: string;
    end_utc: string;
    engine_clock_utc: string;
    completed_full_weeks: number;
    target_full_weeks: number;
    remaining_full_weeks: number;
    progress_pct: number;
    membership_month: string;
    membership_count: number;
    active_signal_universe_count: number;
    pending_signals_count: number;
    open_positions_count: number;
    closed_trades_count: number;
  };
  accounts?: Array<{
    account_id: string;
    policy_id: string;
    scenario_id: string;
    gate: string;
    sizing: string;
    hours: number;
    rr_min: number | null;
    fee_bps: number;
    slippage_bps: number;
    equity: number;
    net_return_pct: number;
    max_dd_pct: number;
    accepted_trades_count?: number;
    open_positions_count: number;
    closed_trades_count: number;
    win_rate_pct: number | null;
    fees_pct: number;
    slippage_pct: number;
    funding_pct: number;
    rejected?: Record<string, number>;
    filtered?: Record<string, number>;
    open_positions?: Array<Record<string, any>>;
    closed_trades?: Array<Record<string, any>>;
    bootstrap_4w_lower_1s?: number | null;
    qualifies_final_evidence?: boolean;
  }>;
  open_positions?: Array<Record<string, any>>;
  closed_trades?: Array<Record<string, any>>;
  recent_scans?: Array<Record<string, any>>;
  pit_top50_membership?: {
    month: string | null;
    ranking_interval: string;
    eligible_contracts: number;
    members: Array<{
      rank: number;
      symbol: string;
      median_quote_volume: number;
      active_days: number;
      wick_p90_pct: number;
    }>;
  };
}

export interface FiboSummaryCounts {
  actionableCount: number;
  armedCount: number;
  shadowCount: number;
}

interface FiboShortWorkspaceProps {
  onSelectCoin?: (symbol: string, fiboHandoff?: FiboHandoff) => void;
  forcedViewMode?: 'LIVE' | 'SHADOW_COMPARE' | 'BACKTEST' | 'PAPER_OOS';
  hideModeSwitcher?: boolean;
  onSummaryChange?: (counts: FiboSummaryCounts) => void;
}

type PolicyMetaItem = { code: string; label: string; badgeCls: string; desc: string };

const getPolicyMetaByLang = (lang: Language): Record<string, PolicyMetaItem> => {
  const pick = (vi: string, en: string, zh: string, ko: string) =>
    lang === 'en' ? en : lang === 'zh' ? zh : lang === 'ko' ? ko : vi;

  return {
    reference_m6_fixed: {
      code: 'N1',
      label: pick(
        'N1 · M6 VỐN 20% (GỐC)',
        'N1 · M6 FIXED 20% (BASE)',
        'N1 · M6 固定 20% (基准)',
        'N1 · M6 고정 20% (기준)'
      ),
      badgeCls: 'bg-slate-900 text-slate-300 border-slate-700',
      desc: pick(
        'Nhánh N1 (Gốc): Lọc M6 cơ bản (H1 đóng đỏ) + Đi vốn cố định 20% NAV + Giữ 72h/120h',
        'Branch N1 (Baseline): Basic M6 filter (red H1 close) + Fixed 20% NAV sizing + Hold 72h/120h',
        '分支 N1 (基准): 基础 M6 过滤 (H1 收阴) + 固定 20% NAV 仓位 + 持仓 72h/120h',
        '브랜치 N1 (기준): 기본 M6 필터 (H1 음봉 마감) + 고정 20% NAV 비중 + 72h/120h 보유'
      ),
    },
    m6_risk: {
      code: 'N2',
      label: pick(
        'N2 · M6 RỦI RO 0.5%',
        'N2 · M6 RISK 0.5%',
        'N2 · M6 风险 0.5%',
        'N2 · M6 리스크 0.5%'
      ),
      badgeCls: 'bg-purple-950/90 text-purple-300 border-purple-500/50',
      desc: pick(
        'Nhánh N2: Lọc M6 cơ bản (H1 đóng đỏ) + SL Fibo 0.886 + Rủi ro 0.5% NAV + Giữ 72h/120h',
        'Branch N2: Basic M6 filter (red H1 close) + Fibo 0.886 SL + 0.5% NAV risk + Hold 72h/120h',
        '分支 N2: 基础 M6 过滤 (H1 收阴) + Fibo 0.886 止损 + 0.5% NAV 风险定仓 + 持仓 72h/120h',
        '브랜치 N2: 기본 M6 필터 (H1 음봉 마감) + Fibo 0.886 SL + 0.5% NAV 리스크 + 72h/120h 보유'
      ),
    },
    sniper_risk: {
      code: 'N3',
      label: pick(
        'N3 · SNIPER CHUẨN ★ LIVE',
        'N3 · SNIPER CORE ★ LIVE',
        'N3 · 标准狙击 ★ 实盘',
        'N3 · 스나이퍼 표준 ★ 라이브'
      ),
      badgeCls: 'bg-amber-950/90 text-amber-300 border-amber-500/60',
      desc: pick(
        'Nhánh N3 (Đang chạy Live & Telegram): Bắt buộc H1 phá đáy (ĐK2) + Rủi ro 0.5% NAV + Giữ 72h/120h',
        'Branch N3 (Active Live & Telegram): Mandatory H1 low break (Cond 2) + 0.5% NAV risk + Hold 72h/120h',
        '分支 N3 (当前实盘与 Telegram): 强制 H1 破前低 (条件2) + 0.5% NAV 风险 + 持仓 72h/120h',
        '브랜치 N3 (현재 라이브 & 텔레그램): H1 직전 저점 이탈 필수 (조건2) + 0.5% NAV 리스크 + 72h/120h 보유'
      ),
    },
    elite_sniper_risk: {
      code: 'N4',
      label: pick(
        'N4 · SNIPER ELITE (PST)',
        'N4 · SNIPER ELITE (PST)',
        'N4 · 精英狙击 (PST)',
        'N4 · 스나이퍼 엘리트 (PST)'
      ),
      badgeCls: 'bg-cyan-950/90 text-cyan-300 border-cyan-500/60',
      desc: pick(
        'Nhánh N4: Chuẩn Sniper N3 + Bắt buộc Carver PST gãy động lượng tại đỉnh + Rủi ro 0.5% NAV + Giữ 72h/120h',
        'Branch N4: N3 Sniper + Mandatory Carver PST peak momentum roll + 0.5% NAV risk + Hold 72h/120h',
        '分支 N4: N3 狙击标准 + 强制 Carver PST 顶部动能衰竭 + 0.5% NAV 风险 + 持仓 72h/120h',
        '브랜치 N4: N3 스나이퍼 + Carver PST 고점 모멘텀 꺾임 필수 + 0.5% NAV 리스크 + 72h/120h 보유'
      ),
    },
    sniper_horizon24: {
      code: 'N5',
      label: pick(
        'N5 · SNIPER ĐÁNH NHANH 24H',
        'N5 · SNIPER FAST 24H',
        'N5 · 狙击快进快出 24H',
        'N5 · 스나이퍼 단기 24H'
      ),
      badgeCls: 'bg-indigo-950/90 text-indigo-300 border-indigo-500/50',
      desc: pick(
        'Nhánh N5: Chuẩn Sniper N3 + Rủi ro 0.5% NAV + Đóng toàn bộ vị thế sau 24 giờ',
        'Branch N5: N3 Sniper rules + 0.5% NAV risk + Full time-exit after 24 hours',
        '分支 N5: N3 狙击标准 + 0.5% NAV 风险 + 24小时后全部平仓',
        '브랜치 N5: N3 스나이퍼 기준 + 0.5% NAV 리스크 + 24시간 후 전량 청산'
      ),
    },
    sniper_rr1_horizon24: {
      code: 'N6',
      label: pick(
        'N6 · SNIPER R:R≥1 · 24H',
        'N6 · SNIPER R:R≥1 · 24H',
        'N6 · 狙击 R:R≥1 · 24H',
        'N6 · 스나이퍼 R:R≥1 · 24H'
      ),
      badgeCls: 'bg-emerald-950/90 text-emerald-300 border-emerald-500/60',
      desc: pick(
        'Nhánh N6: Chuẩn Sniper N3 + Bắt buộc TP1 có R:R ≥ 1.0 + Đóng toàn bộ vị thế sau 24 giờ',
        'Branch N6: N3 Sniper + Mandatory TP1 R:R ≥ 1.0 + Full time-exit after 24 hours',
        '分支 N6: N3 狙击标准 + 强制 TP1 盈亏比 R:R ≥ 1.0 + 24小时后全部平仓',
        '브랜치 N6: N3 스나이퍼 + TP1 손익비 R:R ≥ 1.0 필수 + 24시간 후 전량 청산'
      ),
    },
    m4_f2_elite: {
      code: 'N0',
      label: pick(
        'N0 · CHỜ H1 PHÁ ĐÁY',
        'N0 · AWAIT H1 LOW BREAK',
        'N0 · 等待 H1 破底',
        'N0 · H1 저점 이탈 대기'
      ),
      badgeCls: 'bg-slate-900 text-slate-400 border-slate-700',
      desc: pick(
        'Đạt chuẩn sóng F1B + F2 nhưng nến H1 chỉ mới đóng đỏ (ĐK1), chờ phá đáy cấu trúc để lên N3',
        'Passed F1B + F2 wave gates with red H1 close (Cond 1); awaiting H1 low break to qualify for N3',
        '已达 F1B + F2 波段标准但 H1 仅收阴 (条件1)，等待破前低升级至 N3',
        'F1B + F2 파동 기준 충족 및 H1 음봉 마감(조건1), N3 진입을 위해 저점 이탈 대기'
      ),
    },
    watch_only: {
      code: 'M1',
      label: pick(
        'M1 · CHỈ THEO DÕI',
        'M1 · WATCH ONLY',
        'M1 · 仅观察',
        'M1 · 관망 전용'
      ),
      badgeCls: 'bg-slate-950 text-slate-400 border-slate-800',
      desc: pick(
        'Mới đạt điều kiện sóng M1 cơ bản, bị bộ lọc v4.0.21 chặn vào lệnh',
        'Basic M1 wave only; blocked from entry by v4.0.21 orthogonal filters',
        '仅达基础 M1 波段，已被 v4.0.21 过滤器拦截',
        '기본 M1 파동만 충족, v4.0.21 필터에 의해 진입 차단됨'
      ),
    },
  };
};

const formatPrice = (val: number | undefined | null): string => {
  if (val == null || !Number.isFinite(val)) return '—';
  if (val >= 1000) return val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (val >= 1) return val.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
  if (val >= 0.01) return val.toLocaleString('en-US', { minimumFractionDigits: 5, maximumFractionDigits: 5 });
  return val.toLocaleString('en-US', { minimumFractionDigits: 7, maximumFractionDigits: 7 });
};

const formatUsdCompact = (val: number | undefined | null): string => {
  if (val == null || !Number.isFinite(val)) return '—';
  if (val >= 1_000_000_000) return `$${(val / 1_000_000_000).toFixed(2)}B`;
  if (val >= 1_000_000) return `$${(val / 1_000_000_000 * 1000).toFixed(1)}M`;
  if (val >= 1_000) return `$${(val / 1_000).toFixed(0)}K`;
  return `$${val.toFixed(0)}`;
};

const formatUtcShort = (iso: string | undefined | null): string => {
  if (!iso) return '—';
  return String(iso).slice(0, 16).replace('T', ' ');
};

interface SignalGateEvaluation {
  isActionable: boolean;
  isSniperActionable: boolean;
  isPaperEligible: boolean;
  pumpPass50: boolean;
  f1ExpandedPass: boolean;
  f1ElitePass: boolean;
  f2ImpulsePass: boolean;
  h1BreakPass: boolean;
  slCapPass: boolean;
  priorPumpPct: number;
  impDropPct: number;
  waveKer: number;
  impKer: number;
  failReasonsVi: string[];
  gates: Array<{
    step: number;
    shortLabel: string;
    title: string;
    detail: string;
    passed: boolean;
  }>;
}

const evaluateSignalGateChecklist = (item: FiboShortSignalItem): SignalGateEvaluation => {
  const rawPump = Number(item.wave?.prior_pump_pct ?? 0);
  const priorPumpPct = rawPump <= 5.0 ? rawPump * 100 : rawPump;
  const rawDrop = Number(item.wave?.impulse_drop_pct ?? 0);
  const impDropPct = rawDrop < 2 ? rawDrop * 100 : rawDrop;
  const waveKer = Number(item.wave?.wave_ker ?? 0);
  const impKer = Number(item.wave?.impulse_ker ?? 0);
  const pstPass = Boolean(item.wave?.pst_pass);
  const cond2Break = Boolean(item.h1_confirmation?.cond2_break_prev_low);
  const confirmed = Boolean(item.h1_confirmation?.confirmed);
  const maxFibo = Number(item.h1_confirmation?.max_pullback_fibo_ratio ?? 0);
  const slCapPass = item.trade_setup?.sl_within_cap !== false;
  const matched = item.matched_policies || [];

  const pumpPass50 = priorPumpPct >= 5.0;
  const f1ElitePass = pstPass && waveKer >= 0.35;
  const f1ExpandedPass = f1ElitePass || waveKer >= 0.65;
  const f2ImpulsePass = impDropPct >= 6.0 && impKer >= 0.50;
  const h1BreakPass = confirmed && cond2Break && maxFibo <= 0.786 && slCapPass;

  const isSniperActionable =
    item.stage === 'FIRED_CONFIRMED_SHORT' &&
    pumpPass50 &&
    f1ExpandedPass &&
    f2ImpulsePass &&
    h1BreakPass &&
    matched.some((p) => ['sniper_rr1_horizon24', 'elite_sniper_risk', 'sniper_risk', 'sniper_horizon24'].includes(p));
  const isActionable = isSniperActionable;
  const isPaperEligible =
    isActionable && item.alpha_layers?.universe_tier === 'PIT_TOP50';

  const failReasonsVi: string[] = [];
  if (!f1ExpandedPass) {
    failReasonsVi.push(
      `Chưa gãy động lượng Carver PST & Wave KER thấp (${waveKer.toFixed(2)} < 0.65)`
    );
  }
  if (impDropPct < 6.0) {
    failReasonsVi.push(`Biên độ nhịp sập yếu (-${impDropPct.toFixed(1)}% < 6.0%)`);
  }
  if (impKer < 0.50) {
    failReasonsVi.push(`Nhịp sập giật cục, thiếu lực xả (Impulse KER ${impKer.toFixed(2)} < 0.50)`);
  }
  if (!cond2Break) {
    failReasonsVi.push('Nến H1 mới đóng đỏ (ĐK1), chưa phá đáy nến H1 trước (ĐK2)');
  }
  if (maxFibo > 0.786) {
    failReasonsVi.push(`Nhịp hồi vượt mốc Fibo 0.786 (${maxFibo.toFixed(3)})`);
  }
  if (!slCapPass) {
    failReasonsVi.push('Khoảng cách SL Mốc 6 vượt trần 12%');
  }
  if (!pumpPass50) {
    failReasonsVi.push(`Sóng tăng/hồi trước đỉnh quá nhỏ (+${priorPumpPct.toFixed(1)}% < 5.0% chuẩn v4.0.21)`);
  }

  const gates = [
    {
      step: 1,
      shortLabel: `1. Sóng +${priorPumpPct.toFixed(0)}%`,
      title: 'Cổng 1 · Sóng Bơm / Nhịp Hồi Trước Đỉnh (F1A ≥ +5%)',
      detail: `Tăng +${priorPumpPct.toFixed(1)}% trước đỉnh (${pumpPass50 ? priorPumpPct >= 50.0 ? 'Biên độ lớn ≥ 50%' : 'Đạt chuẩn sóng downtrend ≥ 5%' : 'Dưới ngưỡng +5%'})`,
      passed: pumpPass50,
    },
    {
      step: 2,
      shortLabel: '2. Carver/Wave',
      title: 'Cổng 2 · Suy Yếu Động Lượng Carver PST & Wave KER (F1B/F1C)',
      detail: `Carver PST: ${pstPass ? 'Đạt' : 'Chưa gãy'} · Wave KER: ${waveKer.toFixed(2)} (Cần PST+KER≥0.35 hoặc KER≥0.65)`,
      passed: f1ExpandedPass,
    },
    {
      step: 3,
      shortLabel: `3. Lực sập (${impKer.toFixed(2)})`,
      title: 'Cổng 3 · Độ Dứt Khoát Nhịp Sập (F2: Sập ≥ 6% & Impulse KER ≥ 0.50)',
      detail: `Biên độ sập: -${impDropPct.toFixed(1)}% (Cần ≥ 6%) · Impulse KER: ${impKer.toFixed(2)} (Cần ≥ 0.50)`,
      passed: f2ImpulsePass,
    },
    {
      step: 4,
      shortLabel: '4. H1 Phá đáy',
      title: 'Cổng 4 · H1 Đóng Đỏ Phá Đáy Cấu Trúc (ĐK2) & Trần SL ≤ 12%',
      detail: `${cond2Break ? 'Đã phá đáy H1 trước' : 'Chưa phá đáy H1 trước'} · Đỉnh hồi Fibo ${maxFibo.toFixed(3)} (≤ 0.786) · SL +${(item.trade_setup?.sl_m6_pct ?? item.trade_setup?.stop_loss_pct ?? 0).toFixed(2)}%`,
      passed: h1BreakPass,
    },
  ];

  return {
    isActionable,
    isSniperActionable,
    isPaperEligible,
    pumpPass50,
    f1ExpandedPass,
    f1ElitePass,
    f2ImpulsePass,
    h1BreakPass,
    slCapPass,
    priorPumpPct,
    impDropPct,
    waveKer,
    impKer,
    failReasonsVi,
    gates,
  };
};

export const FiboShortWorkspace: React.FC<FiboShortWorkspaceProps> = ({
  onSelectCoin,
  forcedViewMode,
  hideModeSwitcher = false,
  onSummaryChange,
}) => {
  const { language } = useTranslation();
  const tr = (vi: string, en: string, zh?: string, ko?: string): string => {
    if (language === 'en') return en;
    if (language === 'zh') return zh ?? en;
    if (language === 'ko') return ko ?? en;
    return vi;
  };
  const POLICY_META = useMemo(() => getPolicyMetaByLang(language), [language]);

  const [snapshot, setSnapshot] = useState<FiboSnapshotResponse | null>(null);
  const [backtest, setBacktest] = useState<FiboBacktestResponse | null>(null);
  const [paperOos, setPaperOos] = useState<PaperOosResponse | null>(null);
  const [candidateCompare, setCandidateCompare] = useState<CandidateComparisonResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [scanning, setScanning] = useState<boolean>(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tfFilter, setTfFilter] = useState<'ALL' | '4h' | '1d'>('ALL');
  const [stageFilter, setStageFilter] = useState<
    'ALL' | 'ACTIONABLE_ONLY' | 'FIRED_CONFIRMED_SHORT' | 'ARMED_IN_FIBO_ZONE'
  >('ALL');
  const [policyFilter, setPolicyFilter] = useState<
    'ALL' | 'sniper_rr1_horizon24' | 'elite_sniper_risk' | 'sniper_risk' | 'm6_risk'
  >('ALL');
  const [viewMode, setViewMode] = useState<'LIVE' | 'SHADOW_COMPARE' | 'BACKTEST' | 'PAPER_OOS'>(() => {
    if (forcedViewMode) return forcedViewMode;
    if (typeof window !== 'undefined') {
      const h = window.location.hash.toLowerCase();
      if (h.includes('shadow')) return 'SHADOW_COMPARE';
      if (h.includes('paper-oos')) return 'PAPER_OOS';
    }
    return 'LIVE';
  });

  useEffect(() => {
    if (forcedViewMode) {
      setViewMode(forcedViewMode);
    }
  }, [forcedViewMode]);

  useEffect(() => {
    if (forcedViewMode) return;
    const onHash = () => {
      const h = window.location.hash.toLowerCase();
      if (h.includes('shadow')) {
        setViewMode('SHADOW_COMPARE');
      } else if (h.includes('paper-oos')) {
        setViewMode('PAPER_OOS');
      }
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, [forcedViewMode]);
  const [auditWindow, setAuditWindow] = useState<'2024_2025' | '2020_2025'>('2024_2025');
  const [auditScenario, setAuditScenario] = useState<'standard_vip6' | 'stress_regular'>('standard_vip6');
  const [oosAccountFilter, setOosAccountFilter] = useState<string>('ALL');
  const [showBranchesGuide, setShowBranchesGuide] = useState<boolean>(false);
  const [chartInterval, setChartInterval] = useState<'1h' | '4h' | '1d'>('1h');
  const [chartKlines, setChartKlines] = useState<any[]>([]);

  const fetchSnapshotAndBacktest = async (mode: 'LIVE' | 'SHADOW_COMPARE' | 'BACKTEST' | 'PAPER_OOS' = viewMode) => {
    try {
      const [snapRes, btRes, paperRes, candRes] = await Promise.all([
        fetch('/api/fibo-short/snapshot'),
        mode === 'BACKTEST' || mode === 'SHADOW_COMPARE' ? fetch('/api/fibo-short/backtest') : Promise.resolve(null),
        mode === 'PAPER_OOS' || mode === 'SHADOW_COMPARE' ? fetch('/api/fibo-short/paper-oos') : Promise.resolve(null),
        mode === 'SHADOW_COMPARE' ? fetch('/api/candidates/compare') : Promise.resolve(null),
      ]);
      if (snapRes && snapRes.ok) {
        const snapData: FiboSnapshotResponse = await snapRes.json();
        setSnapshot(snapData);
        if (!selectedId && snapData.items && snapData.items.length > 0) {
          setSelectedId(snapData.items[0].id);
        }
      }
      if (btRes && btRes.ok) {
        const btData: FiboBacktestResponse = await btRes.json();
        setBacktest(btData);
      }
      if (paperRes && paperRes.ok) {
        const paperData: PaperOosResponse = await paperRes.json();
        setPaperOos(paperData);
      }
      if (candRes && candRes.ok) {
        const candData: CandidateComparisonResponse = await candRes.json();
        setCandidateCompare(candData);
      }
    } catch (err) {
      console.error('Failed to load Fibo Short workspace:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchSnapshotAndBacktest(viewMode);
    const timer = setInterval(() => {
      void fetchSnapshotAndBacktest(viewMode);
    }, 30000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewMode]);

  const triggerManualScan = async () => {
    if (scanning) return;
    setScanning(true);
    try {
      const res = await fetch('/api/fibo-short/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (res.ok) {
        const snapData: FiboSnapshotResponse = await res.json();
        setSnapshot(snapData);
        if (snapData.items && snapData.items.length > 0) {
          setSelectedId(snapData.items[0].id);
        }
      }
    } catch (e) {
      console.error('Manual Fibo scan error:', e);
    } finally {
      setScanning(false);
    }
  };

  const actionableCount = useMemo(() => {
    const items = snapshot?.items || [];
    return items.filter((item) => evaluateSignalGateChecklist(item).isActionable).length;
  }, [snapshot]);

  useEffect(() => {
    onSummaryChange?.({
      actionableCount,
      armedCount: snapshot?.armed_count ?? 0,
      shadowCount: snapshot?.shadow_comparison?.total_fired_signals ?? 0,
    });
  }, [actionableCount, snapshot, onSummaryChange]);

  const filteredOutFiredCount = useMemo(() => {
    const items = snapshot?.items || [];
    return items.filter(
      (item) => item.stage === 'FIRED_CONFIRMED_SHORT' && !evaluateSignalGateChecklist(item).isActionable
    ).length;
  }, [snapshot]);

  const filteredItems = useMemo(() => {
    const items = snapshot?.items || [];
    return items.filter((item) => {
      if (tfFilter !== 'ALL' && item.higher_timeframe !== tfFilter) return false;
      if (stageFilter === 'ACTIONABLE_ONLY') {
        if (!evaluateSignalGateChecklist(item).isActionable) return false;
      } else if (stageFilter !== 'ALL' && item.stage !== stageFilter) {
        return false;
      }
      if (policyFilter !== 'ALL') {
        const policies = item.matched_policies || [];
        if (!policies.includes(policyFilter)) return false;
      }
      return true;
    });
  }, [snapshot, tfFilter, stageFilter, policyFilter]);

  const selectedSignal = useMemo(() => {
    if (!filteredItems.length) return null;
    return filteredItems.find((i) => i.id === selectedId) || filteredItems[0];
  }, [filteredItems, selectedId]);

  useEffect(() => {
    if (!selectedSignal) {
      setChartKlines([]);
      return;
    }
    let cancelled = false;
    const loadChart = async () => {
      try {
        const res = await fetch(
          `/api/coin/${encodeURIComponent(selectedSignal.symbol)}/klines?interval=${chartInterval}&limit=120`
        );
        if (!res.ok) return;
        const payload = await res.json();
        if (!cancelled && Array.isArray(payload.klines)) {
          setChartKlines(payload.klines);
        }
      } catch (e) {
        console.error('Error loading Fibo klines:', e);
      }
    };
    loadChart();
    return () => {
      cancelled = true;
    };
  }, [selectedSignal?.symbol, chartInterval]);

  const chartTradeSetup: TradeSetup | undefined = useMemo(() => {
    if (!selectedSignal) return undefined;
    const ts = selectedSignal.trade_setup;
    const useM6Sl = ts.sl_m6 && ts.sl_m6 > ts.entry_price;
    const slPrice = useM6Sl ? ts.sl_m6! : ts.stop_loss;
    const slPct = useM6Sl ? ts.sl_m6_pct! : ts.stop_loss_pct;
    const rrVal = useM6Sl && ts.rr_m6_tp2 ? ts.rr_m6_tp2 : ts.rr_tp2;
    return {
      entryPrice: ts.entry_price,
      entryZoneLow: ts.entry_zone_low,
      entryZoneHigh: ts.entry_zone_high,
      stopLossPrice: slPrice,
      stopLossPct: slPct,
      tp1Price: ts.tp1,
      tp1Pct: ts.tp1_pct,
      tp2Price: ts.tp2,
      tp2Pct: ts.tp2_pct,
      riskRewardRatio: rrVal,
    };
  }, [selectedSignal]);

  const selectedFiboHandoff: FiboHandoff | undefined = useMemo(() => {
    if (!selectedSignal) return undefined;
    const gateEval = evaluateSignalGateChecklist(selectedSignal);
    const actionable =
      selectedSignal.stage === 'FIRED_CONFIRMED_SHORT' && gateEval.isActionable;
    const ts = selectedSignal.trade_setup;
    const useM6Sl = Boolean(ts.sl_m6 && ts.sl_m6 > ts.entry_price);
    const slPrice = useM6Sl ? ts.sl_m6! : ts.stop_loss;
    const slPct = useM6Sl ? ts.sl_m6_pct! : ts.stop_loss_pct;
    const rrVal = useM6Sl && ts.rr_m6_tp2 ? ts.rr_m6_tp2 : ts.rr_tp2;
    return {
      symbol: selectedSignal.symbol,
      higherTimeframe: selectedSignal.higher_timeframe,
      stage: selectedSignal.stage,
      isActionable: actionable,
      score: selectedSignal.score,
      signalTime: selectedSignal.signal_time,
      primaryPolicy: selectedSignal.primary_policy,
      tradeSetup: actionable
        ? {
            entry_price: ts.entry_price,
            entry_zone: ts.entry_zone,
            stop_loss: slPrice,
            stop_loss_pct: slPct,
            tp1: ts.tp1,
            tp1_pct: ts.tp1_pct,
            tp2: ts.tp2,
            tp2_pct: ts.tp2_pct,
            tp3: ts.tp3,
            tp3_pct: ts.tp3_pct,
            rr_ratio: rrVal,
            target_basis: 'Fibo Short v4.0.21 (SL 0.886)',
          }
        : null,
    };
  }, [selectedSignal]);

  const coupledTableRows = useMemo(() => {
    const cp = backtest?.v4_0_21_audit?.coupled_portfolio?.[auditWindow]?.[auditScenario];
    if (!cp) return [];
    const order = [
      'sniper_rr1_horizon24',
      'sniper_horizon24',
      'elite_sniper_risk',
      'sniper_risk',
      'm6_risk',
      'reference_m6_fixed',
    ];
    return order
      .filter((pid) => cp[pid])
      .map((pid) => {
        const entry = cp[pid];
        const m = entry.metric;
        const retDd = m.max_dd_pct > 0 ? m.return_pct / m.max_dd_pct : 0;
        return {
          id: pid,
          meta: POLICY_META[pid] || { label: pid, badgeCls: '', desc: '' },
          return_pct: m.return_pct,
          max_dd_pct: m.max_dd_pct,
          ret_dd_ratio: retDd,
          trades: m.trades,
          fees_pct: m.fees_pct,
          slippage_pct: m.slippage_pct,
          funding_pct: m.funding_pct,
          gross_pct: m.gross_reference_pnl_pct,
          ci95_low_1s: entry.weekly?.ci95_low_1s,
        };
      });
  }, [backtest, auditWindow, auditScenario, POLICY_META]);

  return (
    <div className="flex-1 min-h-0 overflow-y-auto pr-1 pb-8 space-y-4">
      {/* Top Banner: Branch Overview & 3-Tab Switcher */}
      <div className="bg-gradient-to-r from-slate-900 via-indigo-950/70 to-slate-900 border border-amber-500/30 rounded-xl p-4 shadow-lg">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wider rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center gap-1">
                <Sparkles className="w-3 h-3" />{' '}
                {tr(
                  'Chuẩn v4.0.21 · 4-Factor Orthogonal Alpha',
                  'v4.0.21 Standard · 4-Factor Orthogonal Alpha',
                  'v4.0.21 标准 · 四因子正交 Alpha',
                  'v4.0.21 표준 · 4팩터 직교 알파'
                )}
              </span>
              <span className="px-2.5 py-0.5 text-[11px] font-semibold rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 flex items-center gap-1">
                <Lock className="w-3 h-3" /> Backtest Locked ≤ 2025 • Paper OOS v1 (N1–N6)
              </span>
              {snapshot?.pit_universe?.month && (
                <span className="px-2.5 py-0.5 text-[11px] font-mono font-semibold rounded-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
                  PIT Top-50 ({snapshot.pit_universe.month}): {snapshot.pit_universe.member_count} coin · Wick p90 ≤ 3.2%
                </span>
              )}
            </div>
            <h2 className="text-base sm:text-lg font-extrabold text-slate-100 mt-1.5 flex items-center gap-2">
              <TrendingDown className="w-5 h-5 text-amber-400 shrink-0" />
              {tr(
                'Đảo Chiều Xác Nhận & Short Theo Xu Hướng Mới (Fibonacci H4/D1 → H1 · Nhánh N3 ★ Live)',
                'Confirmed Reversal & Trend-Following Short (Fibonacci H4/D1 → H1 · Branch N3 ★ Live)',
                '确认反转与顺势做空 (斐波那契 H4/D1 → H1 · 实盘分支 N3 ★)',
                '반전 확인 & 추세 추종 숏 (피보나치 H4/D1 → H1 · 라이브 브랜치 N3 ★)'
              )}
            </h2>
            <p className="text-xs text-slate-300 mt-0.5">
              {language === 'en' ? (
                <>
                  4 Orthogonal Gates: <b>F1A Prior Move ≥5%</b> + <b>F1B Carver EWMAC/Accel &amp; Wave KER</b> +{' '}
                  <b>F2 Impulse KER ≥0.50</b> + <b>F3/F4 H1 Low Break &amp; Fibo 0.886 SL (0.5% NAV Risk · Branch N3 ★ Live)</b>.
                </>
              ) : language === 'zh' ? (
                <>
                  四层独立门禁：<b>F1A 前置波段 ≥5%</b> + <b>F1B Carver EWMAC/Accel 与 Wave KER</b> +{' '}
                  <b>F2 Impulse KER ≥0.50</b> + <b>F3/F4 H1 破前低与 Fibo 0.886 止损 (0.5% NAV 风险 · N3 ★ 实盘)</b>。
                </>
              ) : language === 'ko' ? (
                <>
                  4단계 독립 필터: <b>F1A 사전 파동 ≥5%</b> + <b>F1B Carver EWMAC/Accel &amp; Wave KER</b> +{' '}
                  <b>F2 Impulse KER ≥0.50</b> + <b>F3/F4 H1 저점 이탈 &amp; Fibo 0.886 SL (0.5% NAV 리스크 · N3 ★ 라이브)</b>.
                </>
              ) : (
                <>
                  Hội tụ 4 tầng độc lập: <b>F1A Sóng bơm/hồi ≥5%</b> + <b>F1B Carver EWMAC/Accel &amp; Wave KER</b> +{' '}
                  <b>F2 Impulse KER ≥0.50</b> + <b>F3/F4 H1 Phá Đáy &amp; SL Mốc 6 Fibo 0.886 (Đi vốn rủi ro 0.5% NAV · Nhánh N3 ★ Live)</b>.
                </>
              )}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {!hideModeSwitcher && (
              <div className="inline-flex flex-wrap rounded-lg bg-slate-950 p-1 border border-slate-800 gap-1">
                <button
                  type="button"
                  onClick={() => setViewMode('LIVE')}
                  className={`px-3 py-1.5 rounded-md text-xs font-bold transition flex items-center gap-1.5 ${
                    viewMode === 'LIVE'
                      ? 'bg-amber-500 text-slate-950 shadow'
                      : 'text-slate-300 hover:text-white'
                  }`}
                >
                  <Activity className="w-3.5 h-3.5" />
                  {tr('Radar Trực Tiếp', 'Live Radar', '实时雷达', '라이브 레이더')}
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode('SHADOW_COMPARE')}
                  className={`px-3 py-1.5 rounded-md text-xs font-bold transition flex items-center gap-1.5 ${
                    viewMode === 'SHADOW_COMPARE'
                      ? 'bg-cyan-500 text-slate-950 shadow'
                      : 'text-cyan-300 hover:text-white'
                  }`}
                >
                  <Gauge className="w-3.5 h-3.5" />
                  {tr(
                    'Đối Chiếu Nhánh (M1 Cũ vs N1–N6)',
                    'Branch Compare (M1 vs N1–N6)',
                    '分支对比 (旧M1 vs N1–N6)',
                    '브랜치 비교 (구M1 vs N1–N6)'
                  )}
                  {(snapshot?.shadow_comparison?.total_fired_signals ?? 0) > 0 && (
                    <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-slate-950/80 text-cyan-300 border border-cyan-500/40">
                      {snapshot?.shadow_comparison?.total_fired_signals}
                    </span>
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode('PAPER_OOS')}
                  className={`px-3 py-1.5 rounded-md text-xs font-bold transition flex items-center gap-1.5 ${
                    viewMode === 'PAPER_OOS'
                      ? 'bg-emerald-500 text-slate-950 shadow'
                      : 'text-emerald-300 hover:text-white'
                  }`}
                >
                  <Cpu className="w-3.5 h-3.5" />
                  {tr('Paper OOS (12 TK · N1–N6)', 'Paper OOS (12 Acc · N1–N6)', 'Paper OOS (12账户 · N1–N6)', 'Paper OOS (12계좌 · N1–N6)')}
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode('BACKTEST')}
                  className={`px-3 py-1.5 rounded-md text-xs font-bold transition flex items-center gap-1.5 ${
                    viewMode === 'BACKTEST'
                      ? 'bg-amber-500 text-slate-950 shadow'
                      : 'text-slate-300 hover:text-white'
                  }`}
                >
                  <BarChart3 className="w-3.5 h-3.5" />
                  {tr('Kiểm Định v4.0.21 (≤ 2025)', 'v4.0.21 Audit (≤ 2025)', 'v4.0.21 审计 (≤ 2025)', 'v4.0.21 감사 (≤ 2025)')}
                </button>
              </div>
            )}

            <button
              type="button"
              onClick={() => setShowBranchesGuide((prev) => !prev)}
              className={`px-3 py-2 rounded-lg text-xs font-bold border flex items-center gap-1.5 shadow transition cursor-pointer ${
                showBranchesGuide
                  ? 'bg-cyan-500 text-slate-950 border-cyan-400'
                  : 'bg-slate-950 hover:bg-slate-800 text-cyan-300 border-cyan-500/40'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              {showBranchesGuide
                ? tr('Ẩn Bảng Mã N1–N6', 'Hide N1–N6 Guide', '隐藏 N1–N6 指南', 'N1–N6 가이드 숨기기')
                : tr('Bảng Mã 6 Nhánh (N1–N6)', 'N1–N6 Branch Guide', 'N1–N6 六大分支指南', 'N1–N6 6개 브랜치 가이드')}
            </button>

            <button
              type="button"
              onClick={triggerManualScan}
              disabled={scanning}
              className="px-3 py-2 rounded-lg text-xs font-bold bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white flex items-center gap-1.5 shadow transition cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${scanning ? 'animate-spin' : ''}`} />
              {scanning
                ? tr('Đang quét...', 'Scanning...', '扫描中...', '스캔 중...')
                : tr('Quét Fibo Ngay', 'Scan Fibo Now', '立即扫描 Fibo', 'Fibo 즉시 스캔')}
            </button>
          </div>
        </div>

        {/* Summary Counters */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5 mt-3.5 pt-3 border-t border-slate-800/80">
          <div className="bg-slate-950/80 border border-slate-800 rounded-lg p-2.5">
            <div className="text-[11px] text-slate-400">
              {tr('Vũ Trụ Quét Chọn Lọc', 'Screened Universe', '筛选扫描池', '선별 스캔 유니버스')}
            </div>
            <div className="text-xl font-black font-mono text-slate-100 mt-0.5">
              {snapshot?.scanned_symbols_count ?? 0}
              <span className="text-xs font-normal text-slate-400 ml-1.5">
                {tr('cặp (Blacklist ON)', 'pairs (Blacklist ON)', '交易对 (黑名单开启)', '페어 (블랙리스트 ON)')}
              </span>
            </div>
          </div>
          <div className="bg-slate-950/80 border border-emerald-500/30 rounded-lg p-2.5">
            <div className="text-[11px] text-emerald-300 font-semibold flex items-center gap-1">
              <Target className="w-3.5 h-3.5" />{' '}
              {tr('ĐỦ CHUẨN VÀO SHORT (N3+)', 'ACTIONABLE SHORT (N3+)', '达标可做空 (N3+)', '진입 가능 숏 (N3+)')}
            </div>
            <div className="text-xl font-black font-mono text-emerald-400 mt-0.5">
              {actionableCount}
              <span className="text-xs font-normal text-slate-400 ml-1.5">
                {tr(
                  `(H1 đỏ bị lọc: ${filteredOutFiredCount} · Chờ Fibo: ${snapshot?.armed_count ?? 0})`,
                  `(Filtered: ${filteredOutFiredCount} · Fibo Zone: ${snapshot?.armed_count ?? 0})`,
                  `(已拦截: ${filteredOutFiredCount} · Fibo区: ${snapshot?.armed_count ?? 0})`,
                  `(차단됨: ${filteredOutFiredCount} · Fibo존: ${snapshot?.armed_count ?? 0})`
                )}
              </span>
            </div>
          </div>
          <div className="bg-slate-950/80 border border-amber-500/30 rounded-lg p-2.5">
            <div className="text-[11px] text-amber-300 font-semibold flex items-center gap-1">
              <ShieldAlert className="w-3.5 h-3.5" /> N3 SNIPER (LIVE) / N4 ELITE
            </div>
            <div className="text-xl font-black font-mono text-amber-300 mt-0.5">
              {snapshot?.policy_counts?.sniper_risk ?? 0}
              <span className="text-xs font-normal text-cyan-300 ml-1.5">
                (N4 Elite: {snapshot?.policy_counts?.elite_sniper_risk ?? 0})
              </span>
            </div>
          </div>
          <div className="bg-slate-950/80 border border-emerald-500/30 rounded-lg p-2.5">
            <div className="text-[11px] text-emerald-300 font-semibold flex items-center gap-1">
              <Gauge className="w-3.5 h-3.5" /> N6 (RR≥1·24H) / N2 (M6)
            </div>
            <div className="text-xl font-black font-mono text-emerald-300 mt-0.5">
              {snapshot?.policy_counts?.sniper_rr1_horizon24 ?? 0}
              <span className="text-xs font-normal text-slate-400 ml-1.5">
                (N2 M6: {snapshot?.policy_counts?.m6_risk ?? 0})
              </span>
            </div>
          </div>
          <div className="bg-slate-950/80 border border-cyan-500/30 rounded-lg p-2.5">
            <div className="text-[11px] text-cyan-300 font-semibold flex items-center gap-1">
              <Award className="w-3.5 h-3.5" />{' '}
              {tr('HIỆU SUẤT v4.0.21 (24–25)', 'v4.0.21 EDGE (24–25)', 'v4.0.21 表现 (24–25)', 'v4.0.21 성과 (24–25)')}
            </div>
            <div className="text-xl font-black font-mono text-emerald-300 mt-0.5">
              +61.2%
              <span className="text-xs font-normal text-cyan-300 ml-1.5">
                (MaxDD 10.7% · 5.74x)
              </span>
            </div>
          </div>
        </div>

        {/* Collapsible 6 Shadow Branches & 2 Cost Scenarios Reference Guide */}
        {showBranchesGuide && (
          <div className="mt-4 pt-3.5 border-t border-cyan-500/30 bg-slate-950/95 rounded-xl p-4 border space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-xs font-extrabold uppercase tracking-wider text-cyan-300 flex items-center gap-1.5">
                  <Layers className="w-4 h-4 text-amber-400" />
                  {tr(
                    'Bảng Mã Nhớ Nhanh 6 Nhánh Shadow (N1 → N6) & 2 Kịch Bản Phí (6 × 2 = 12 Tài Khoản Độc Lập)',
                    'Quick Reference: 6 Shadow Branches (N1 → N6) & 2 Cost Scenarios (6 × 2 = 12 Isolated Accounts)',
                    '6大影子分支速查表 (N1 → N6) 与 2种成本场景 (6 × 2 = 12个独立账户)',
                    '6개 섀도우 브랜치 빠른 가이드 (N1 → N6) & 2개 비용 시나리오 (6 × 2 = 12개 독립 계좌)'
                  )}
                </div>
                <p className="text-[11px] text-slate-300 mt-0.5">
                  {language === 'en' ? (
                    <>
                      For easy recall, the 6 branches are coded <b>N1 through N6</b> and grouped into <b>3 pairs by filter strictness &amp; holding horizon</b>. Branch <b>N3 (Sniper Core)</b> is the active branch powering <b>Live Execution &amp; Telegram alerts</b>.
                    </>
                  ) : language === 'zh' ? (
                    <>
                      为方便记忆，6个分支编号为 <b>N1 至 N6</b> 并按过滤严格度与持仓周期分为 <b>3组配对</b>。其中 <b>N3 (标准狙击)</b> 为当前驱动 <b>实盘与 Telegram 警报</b> 的主力分支。
                    </>
                  ) : language === 'ko' ? (
                    <>
                      기억하기 쉽도록 6개 브랜치를 <b>N1부터 N6까지</b> 번호를 매기고 필터 강도 및 보유 시간별로 <b>3개 그룹</b>으로 묶었습니다. 특히 <b>N3 (스나이퍼 표준)</b> 브랜치가 현재 <b>라이브 실행 및 텔레그램 알림</b>에 사용 중입니다.
                    </>
                  ) : (
                    <>
                      Để dễ nhớ, 6 nhánh được đánh mã từ <b>N1 đến N6</b> và chia làm <b>3 cặp theo độ khắt khe &amp; thời gian giữ lệnh</b>. Đặc biệt, nhánh <b>N3 (Sniper Chuẩn)</b> là nhánh đang chạy thực tế cho <b>Live &amp; bắn tín hiệu Telegram</b>.
                    </>
                  )}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowBranchesGuide(false)}
                className="px-2.5 py-1 rounded-md text-[11px] font-mono font-bold bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 cursor-pointer"
              >
                {tr('✕ Thu gọn', '✕ Collapse', '✕ 收起', '✕ 접기')}
              </button>
            </div>

            {/* 3-Bucket Quick Memory Rule */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 text-[11px]">
              <div className="bg-slate-900/90 border border-purple-500/30 rounded-lg p-2.5">
                <div className="font-mono font-bold text-purple-300">
                  {tr(
                    'Nhóm A (N1 – N2) · M6 Cơ Bản (Giữ 72h/120h)',
                    'Group A (N1 – N2) · Basic M6 (Hold 72h/120h)',
                    'A组 (N1 – N2) · 基础 M6 (持仓 72h/120h)',
                    '그룹 A (N1 – N2) · 기본 M6 (72h/120h 보유)'
                  )}
                </div>
                <div className="text-slate-300 mt-0.5">
                  {language === 'en' ? (
                    <>
                      Passes v4.0.21 wave gates + <b>enters on any confirmed red H1 close</b> (no prior H1 low break required).<br />
                      • <b>N1:</b> Fixed 20% NAV sizing (Baseline)<br />
                      • <b>N2:</b> 0.5% NAV risk-based sizing
                    </>
                  ) : language === 'zh' ? (
                    <>
                      通过 v4.0.21 波段门禁 + <b>H1 确认收阴即入场</b> (不强制破前一根 H1 低点)。<br />
                      • <b>N1:</b> 固定 20% NAV 仓位 (基准对照组)<br />
                      • <b>N2:</b> 按 0.5% NAV 止损风险定仓
                    </>
                  ) : language === 'ko' ? (
                    <>
                      v4.0.21 파동 기준 통과 + <b>H1 음봉 마감 확인 시 진입</b> (직전 H1 저점 이탈 불필요).<br />
                      • <b>N1:</b> 고정 20% NAV 비중 (기준점)<br />
                      • <b>N2:</b> 0.5% NAV 리스크 기반 비중
                    </>
                  ) : (
                    <>
                      Đạt chuẩn sóng v4.0.21 + <b>cứ nến H1 đóng đỏ xác nhận là vào</b> (không bắt buộc phá đáy nến trước).<br />
                      • <b>N1:</b> Đi cố định 20% vốn (Mốc gốc)<br />
                      • <b>N2:</b> Đi vốn theo rủi ro 0.5% NAV
                    </>
                  )}
                </div>
              </div>
              <div className="bg-amber-950/25 border border-amber-500/50 rounded-lg p-2.5">
                <div className="font-mono font-bold text-amber-300">
                  {tr(
                    'Nhóm B (N3 ★ – N4) · Sniper Giữ Dài (72h/120h)',
                    'Group B (N3 ★ – N4) · Sniper Full Hold (72h/120h)',
                    'B组 (N3 ★ – N4) · 狙击长持 (72h/120h)',
                    '그룹 B (N3 ★ – N4) · 스나이퍼 장기 (72h/120h)'
                  )}
                </div>
                <div className="text-slate-200 mt-0.5">
                  {language === 'en' ? (
                    <>
                      Requires <b>H1 close breaking below prior H1 low (Cond 2)</b>, 0.5% NAV risk sizing.<br />
                      • <b className="text-amber-300">N3 ★ LIVE:</b> Sniper Core (Active Live &amp; Telegram branch)<br />
                      • <b className="text-cyan-300">N4:</b> Sniper Elite (Adds mandatory Carver PST peak roll)
                    </>
                  ) : language === 'zh' ? (
                    <>
                      强制要求 <b>H1 收盘跌破前一根 H1 最低价 (条件2)</b>，按 0.5% NAV 风险定仓。<br />
                      • <b className="text-amber-300">N3 ★ 实盘:</b> 标准狙击 (当前实盘与 Telegram 主力分支)<br />
                      • <b className="text-cyan-300">N4:</b> 精英狙击 (额外强制 Carver PST 顶部动能衰竭)
                    </>
                  ) : language === 'ko' ? (
                    <>
                      <b>H1 종가가 직전 H1 저점을 하향 돌파(조건2)</b> 필수, 0.5% NAV 리스크 비중.<br />
                      • <b className="text-amber-300">N3 ★ 라이브:</b> 스나이퍼 표준 (현재 라이브 &amp; 텔레그램 주력)<br />
                      • <b className="text-cyan-300">N4:</b> 스나이퍼 엘리트 (Carver PST 고점 둔화 필수 추가)
                    </>
                  ) : (
                    <>
                      Bắt buộc <b>nến H1 đóng cửa phá thủng đáy nến H1 trước (ĐK2)</b>, đi vốn rủi ro 0.5% NAV.<br />
                      • <b className="text-amber-300">N3 ★ LIVE:</b> Sniper Chuẩn (Đang dùng cho Live &amp; Telegram)<br />
                      • <b className="text-cyan-300">N4:</b> Sniper Elite (Bắt buộc thêm Carver PST gãy tại đỉnh)
                    </>
                  )}
                </div>
              </div>
              <div className="bg-slate-900/90 border border-emerald-500/30 rounded-lg p-2.5">
                <div className="font-mono font-bold text-emerald-300">
                  {tr(
                    'Nhóm C (N5 – N6) · Sniper Đánh Nhanh 24h',
                    'Group C (N5 – N6) · Sniper Fast 24h Exit',
                    'C组 (N5 – N6) · 狙击快进快出 24h',
                    '그룹 C (N5 – N6) · 스나이퍼 단기 24h 청산'
                  )}
                </div>
                <div className="text-slate-300 mt-0.5">
                  {language === 'en' ? (
                    <>
                      Same H1 low-break Sniper filter as N3, but <b>closes all positions after 24 hours</b>.<br />
                      • <b>N5:</b> Sniper Fast 24h<br />
                      • <b>N6:</b> Sniper 24h + Mandatory <b>TP1 R:R ≥ 1.0</b>
                    </>
                  ) : language === 'zh' ? (
                    <>
                      与 N3 相同的 H1 破底狙击过滤，但 <b>持仓满 24 小时全部平仓</b>。<br />
                      • <b>N5:</b> 狙击 24h 快进快出<br />
                      • <b>N6:</b> 狙击 24h + 强制 <b>TP1 盈亏比 R:R ≥ 1.0</b>
                    </>
                  ) : language === 'ko' ? (
                    <>
                      N3와 동일한 H1 저점 이탈 스나이퍼 필터를 쓰되 <b>24시간 후 전량 청산</b>.<br />
                      • <b>N5:</b> 스나이퍼 단기 24h<br />
                      • <b>N6:</b> 스나이퍼 24h + <b>TP1 손익비 R:R ≥ 1.0</b> 필수
                    </>
                  ) : (
                    <>
                      Cùng bộ lọc Sniper phá đáy H1 như N3 nhưng <b>đóng toàn bộ lệnh sau đúng 24 giờ</b>.<br />
                      • <b>N5:</b> Sniper Đánh Nhanh 24h<br />
                      • <b>N6:</b> Sniper 24h + Bắt buộc <b>TP1 có R:R ≥ 1.0</b>
                    </>
                  )}
                </div>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 text-[11px] font-mono">
                    <th className="py-2 px-2.5">{tr('Mã Nhánh (N1–N6)', 'Branch Code (N1–N6)', '分支代码 (N1–N6)', '브랜치 코드 (N1–N6)')}</th>
                    <th className="py-2 px-2.5">{tr('Điều Kiện Lọc Tín Hiệu (Entry Gate)', 'Signal Entry Gate', '信号入场门禁', '신호 진입 조건 (Entry Gate)')}</th>
                    <th className="py-2 px-2.5">{tr('Cách Đi Vốn & Trần Rủi Ro', 'Position Sizing & Risk Cap', '仓位与风险上限', '포지션 비중 & 리스크 상한')}</th>
                    <th className="py-2 px-2.5">{tr('Cắt Lỗ (SL) & Chốt Lời (TP)', 'Stop-Loss (SL) & Targets (TP)', '止损 (SL) 与止盈 (TP)', '손절 (SL) & 익절 (TP)')}</th>
                    <th className="py-2 px-2.5">{tr('Thời Gian Giữ Tối Đa (Horizon)', 'Max Holding Horizon', '最大持仓时间', '최대 보유 기간 (Horizon)')}</th>
                    <th className="py-2 px-2.5">{tr('Mục Đích & Cách Nhớ Nhanh', 'Role & Quick Recall', '核心作用与速记', '역할 & 빠른 암기 포인트')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80 text-[11px]">
                  {(
                    [
                      {
                        id: 'reference_m6_fixed',
                        gate: tr(
                          'M6 Cơ Bản: Sóng bơm/hồi ≥ 5% + (Carver PST gãy & Wave KER ≥ 0.35 hoặc Wave KER ≥ 0.65) + Nhịp sập ≥ 6% & Impulse KER ≥ 0.50 + Nến H1 đóng đỏ xác nhận.',
                          'Basic M6: Prior move ≥ 5% + (Carver PST roll & Wave KER ≥ 0.35 or Wave KER ≥ 0.65) + Impulse drop ≥ 6% & Impulse KER ≥ 0.50 + Red H1 close.',
                          '基础 M6：前置波段 ≥ 5% + (Carver PST 衰竭且 Wave KER ≥ 0.35 或 Wave KER ≥ 0.65) + 下跌波 ≥ 6% 且 Impulse KER ≥ 0.50 + H1 收阴确认。',
                          '기본 M6: 사전 파동 ≥ 5% + (Carver PST 둔화 & Wave KER ≥ 0.35 또는 Wave KER ≥ 0.65) + 하락 파동 ≥ 6% & Impulse KER ≥ 0.50 + H1 음봉 마감.'
                        ),
                        sizing: tr('Cố định 20% NAV / lệnh (Trần ≤ 12% NAV)', 'Fixed 20% NAV / trade (Cap ≤ 12% NAV)', '固定 20% NAV / 笔 (总上限 ≤ 12% NAV)', '고정 20% NAV / 건 (총 상한 ≤ 12% NAV)'),
                        horizon: '72h (H4) / 120h (D1)',
                      },
                      {
                        id: 'm6_risk',
                        gate: tr(
                          'Giống hệt N1 (M6 Cơ Bản — vào cả nến H1 đóng đỏ ĐK1 lẫn phá đáy ĐK2).',
                          'Identical to N1 (Basic M6 — enters on both Cond 1 red H1 pattern and Cond 2 low break).',
                          '与 N1 完全相同 (基础 M6 — H1 收阴形态或破底均入场)。',
                          'N1과 동일 (기본 M6 — H1 음봉 패턴 및 저점 이탈 모두 진입).'
                        ),
                        sizing: tr('Rủi ro 0.5% NAV / lệnh (Max 20% NAV · Trần ≤ 2% NAV)', '0.5% NAV risk / trade (Max 20% NAV · Cap ≤ 2% NAV)', '0.5% NAV 风险 / 笔 (最大 20% NAV · 总上限 ≤ 2% NAV)', '0.5% NAV 리스크 / 건 (최대 20% NAV · 상한 ≤ 2% NAV)'),
                        horizon: '72h (H4) / 120h (D1)',
                      },
                      {
                        id: 'sniper_risk',
                        gate: tr(
                          'M6 Cơ Bản + Bắt buộc nến H1 đóng cửa phá đáy nến H1 trước (ĐK2) + Đỉnh nhịp hồi ≤ Fibo 0.786.',
                          'Basic M6 + Mandatory H1 close below prior H1 low (Cond 2) + Max pullback ≤ Fibo 0.786.',
                          '基础 M6 + 强制 H1 收盘跌破前一根 H1 低点 (条件2) + 最大回撤 ≤ Fibo 0.786。',
                          '기본 M6 + H1 종가 직전 H1 저점 이탈 필수(조건2) + 최대 되돌림 ≤ Fibo 0.786.'
                        ),
                        sizing: tr('Rủi ro 0.5% NAV / lệnh (Max 20% NAV · Trần ≤ 2% NAV)', '0.5% NAV risk / trade (Max 20% NAV · Cap ≤ 2% NAV)', '0.5% NAV 风险 / 笔 (最大 20% NAV · 总上限 ≤ 2% NAV)', '0.5% NAV 리스크 / 건 (최대 20% NAV · 상한 ≤ 2% NAV)'),
                        horizon: '72h (H4) / 120h (D1)',
                      },
                      {
                        id: 'elite_sniper_risk',
                        gate: tr(
                          'Chuẩn N3 Sniper + Bắt buộc Carver PST gãy động lượng (ewmac_16_64 ≤ 0 tại đỉnh hoặc accel_4_16 ≤ -1.0 kèm Wave KER ≥ 0.35).',
                          'N3 Sniper + Mandatory Carver PST roll (peak ewmac_16_64 ≤ 0 or accel_4_16 ≤ -1.0 with Wave KER ≥ 0.35).',
                          'N3 狙击标准 + 强制 Carver PST 顶部动能衰竭 (ewmac_16_64 ≤ 0 或 accel_4_16 ≤ -1.0 且 Wave KER ≥ 0.35)。',
                          'N3 스나이퍼 + Carver PST 모멘텀 둔화 필수 (고점 ewmac_16_64 ≤ 0 또는 accel_4_16 ≤ -1.0 & Wave KER ≥ 0.35).'
                        ),
                        sizing: tr('Rủi ro 0.5% NAV / lệnh (Max 20% NAV · Trần ≤ 2% NAV)', '0.5% NAV risk / trade (Max 20% NAV · Cap ≤ 2% NAV)', '0.5% NAV 风险 / 笔 (最大 20% NAV · 总上限 ≤ 2% NAV)', '0.5% NAV 리스크 / 건 (최대 20% NAV · 상한 ≤ 2% NAV)'),
                        horizon: '72h (H4) / 120h (D1)',
                      },
                      {
                        id: 'sniper_horizon24',
                        gate: tr('Giống hệt N3 Sniper Chuẩn.', 'Identical to N3 Sniper Core.', '与 N3 标准狙击完全相同。', 'N3 스나이퍼 표준과 동일.'),
                        sizing: tr('Rủi ro 0.5% NAV / lệnh', '0.5% NAV risk / trade', '0.5% NAV 风险 / 笔', '0.5% NAV 리스크 / 건'),
                        horizon: tr('Đóng toàn bộ sau 24 giờ', 'Full exit after 24 hours', '24小时后全部平仓', '24시간 후 전량 청산'),
                      },
                      {
                        id: 'sniper_rr1_horizon24',
                        gate: tr(
                          'Chuẩn N5 Sniper 24h + Bắt buộc tỷ lệ R:R ngay tại TP1 ≥ 1.0 (Entry → TP1 ≥ Entry → SL 0.886).',
                          'N5 Sniper 24h + Mandatory TP1 R:R ≥ 1.0 (Entry → TP1 distance ≥ Entry → SL 0.886 distance).',
                          'N5 狙击 24h + 强制 TP1 盈亏比 R:R ≥ 1.0 (入场至 TP1 距离 ≥ 入场至 0.886 止损距离)。',
                          'N5 스나이퍼 24h + TP1 손익비 R:R ≥ 1.0 필수 (진입가→TP1 거리 ≥ 진입가→SL 0.886 거리).'
                        ),
                        sizing: tr('Rủi ro 0.5% NAV / lệnh', '0.5% NAV risk / trade', '0.5% NAV 风险 / 笔', '0.5% NAV 리스크 / 건'),
                        horizon: tr('Đóng toàn bộ sau 24 giờ', 'Full exit after 24 hours', '24小时后全部平仓', '24시간 후 전량 청산'),
                      },
                    ] as const
                  ).map((row) => {
                    const pm = POLICY_META[row.id];
                    const isLiveBranch = row.id === 'sniper_risk';
                    return (
                      <tr key={row.id} className={isLiveBranch ? 'bg-amber-950/20 hover:bg-amber-950/30' : 'hover:bg-slate-900/60'}>
                        <td className="py-2.5 px-2.5 font-mono">
                          <span className={`px-2 py-0.5 text-[10px] font-bold rounded border ${pm.badgeCls}`}>
                            {pm.label}
                          </span>
                          <div className={`text-[10px] mt-0.5 ${isLiveBranch ? 'text-amber-300 font-bold' : 'text-slate-500'}`}>
                            {row.id}
                          </div>
                        </td>
                        <td className="py-2.5 px-2.5 text-slate-200">{row.gate}</td>
                        <td className="py-2.5 px-2.5 font-mono text-emerald-300">{row.sizing}</td>
                        <td className="py-2.5 px-2.5 text-slate-300">
                          {tr(
                            'SL Fibo 0.886 (+0.25 ATR) · Chốt 50/30/20% TP1–3 · Chạm TP1 dời SL Hòa Vốn',
                            'Fibo 0.886 SL (+0.25 ATR) · Scale 50/30/20% TP1–3 · Breakeven SL at TP1',
                            'Fibo 0.886 止损 (+0.25 ATR) · 分批 50/30/20% 止盈 · 触及 TP1 移至保本',
                            'Fibo 0.886 SL (+0.25 ATR) · 50/30/20% 분할 익절 · TP1 도달 시 본절 이동'
                          )}
                        </td>
                        <td className={`py-2.5 px-2.5 font-mono font-bold ${row.id.includes('24') ? 'text-cyan-300' : 'text-amber-300'}`}>
                          {row.horizon}
                        </td>
                        <td className={`py-2.5 px-2.5 ${isLiveBranch ? 'text-amber-200 font-semibold' : 'text-slate-300'}`}>
                          {pm.desc}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1 text-[11px]">
              <div className="bg-slate-900/90 border border-emerald-500/30 rounded-lg p-2.5">
                <div className="font-mono font-bold text-emerald-300">
                  {tr(
                    'Kịch Bản Phí 1 · VIP6 (`N1-VIP6` → `N6-VIP6`)',
                    'Cost Scenario 1 · Standard VIP6 (`N1-VIP6` → `N6-VIP6`)',
                    '成本场景 1 · 标准 VIP6 (`N1-VIP6` → `N6-VIP6`)',
                    '비용 시나리오 1 · 표준 VIP6 (`N1-VIP6` → `N6-VIP6`)'
                  )}
                </div>
                <div className="text-slate-300 mt-0.5">
                  {tr(
                    'Mô phỏng khớp lệnh chuẩn: phí Taker 2.5 bps (0.025%) + trượt giá 10 bps (0.10%) mỗi lần khớp + phí Funding 8h thực tế trên Binance USD-M Futures.',
                    'Standard execution: 2.5 bps (0.025%) taker fee + 10 bps (0.10%) slippage per fill + real 8h Binance USD-M funding settlements.',
                    '标准执行假设：每次成交 2.5 bps (0.025%) 手续费 + 10 bps (0.10%) 滑点 + 币安 USD-M 真实 8h 资金费率结算。',
                    '표준 체결 가정: 체결당 테이커 수수료 2.5 bps (0.025%) + 슬리피지 10 bps (0.10%) + 바이낸스 USD-M 실제 8시간 펀딩비 정산.'
                  )}
                </div>
              </div>
              <div className="bg-slate-900/90 border border-rose-500/30 rounded-lg p-2.5">
                <div className="font-mono font-bold text-rose-300">
                  {tr(
                    'Kịch Bản Phí 2 · Stress (`N1-Stress` → `N6-Stress`)',
                    'Cost Scenario 2 · Stress Regular (`N1-Stress` → `N6-Stress`)',
                    '成本场景 2 · 高压压力测试 (`N1-Stress` → `N6-Stress`)',
                    '비용 시나리오 2 · 스트레스 테스트 (`N1-Stress` → `N6-Stress`)'
                  )}
                </div>
                <div className="text-slate-300 mt-0.5">
                  {tr(
                    'Mô phỏng chịu tải khắc nghiệt: phí Taker 5.0 bps (0.05%) + trượt giá 50 bps (0.50%) mỗi lần khớp + Funding 8h thực tế để kiểm tra sức chịu đựng của từng nhánh N1–N6.',
                    'Heavy friction stress test: 5.0 bps (0.05%) taker fee + 50 bps (0.50%) slippage per fill + real 8h funding to test N1–N6 resilience.',
                    '极端摩擦压力测试：每次成交 5.0 bps (0.05%) 手续费 + 50 bps (0.50%) 滑点 + 真实 8h 资金费率，检验 N1–N6 抗压能力。',
                    '가혹 조건 스트레스 테스트: 체결당 수수료 5.0 bps (0.05%) + 슬리피지 50 bps (0.50%) + 실제 8시간 펀딩비로 N1–N6 내구성 검증.'
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {viewMode === 'LIVE' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {/* Left Column: Signal List */}
          <div className="lg:col-span-5 bg-slate-900/90 border border-slate-800 rounded-xl p-3.5 flex flex-col max-h-[880px]">
            <div className="space-y-2 pb-3 mb-3 border-b border-slate-800">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-1">
                  {(['ALL', '4h', '1d'] as const).map((tf) => (
                    <button
                      key={tf}
                      type="button"
                      onClick={() => setTfFilter(tf)}
                      className={`px-2.5 py-1 rounded text-xs font-bold font-mono transition ${
                        tfFilter === tf
                          ? 'bg-amber-500 text-slate-950'
                          : 'bg-slate-950 text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {tf === 'ALL' ? 'H4 + D1' : tf.toUpperCase()}
                    </button>
                  ))}
                </div>

                <div className="flex flex-wrap items-center gap-1">
                  {(
                    [
                      { id: 'ALL', label: tr('Tất cả', 'All', '全部', '전체') },
                      {
                        id: 'ACTIONABLE_ONLY',
                        label: tr(
                          `✅ Đủ chuẩn vào lệnh (${actionableCount})`,
                          `✅ Actionable (${actionableCount})`,
                          `✅ 达标可入场 (${actionableCount})`,
                          `✅ 진입 가능 (${actionableCount})`
                        ),
                      },
                      {
                        id: 'FIRED_CONFIRMED_SHORT',
                        label: tr(
                          `H1 Đỏ (${snapshot?.fired_count ?? 0})`,
                          `Red H1 (${snapshot?.fired_count ?? 0})`,
                          `H1 收阴 (${snapshot?.fired_count ?? 0})`,
                          `H1 음봉 (${snapshot?.fired_count ?? 0})`
                        ),
                      },
                      {
                        id: 'ARMED_IN_FIBO_ZONE',
                        label: tr(
                          `Vùng Fibo (${snapshot?.armed_count ?? 0})`,
                          `Fibo Zone (${snapshot?.armed_count ?? 0})`,
                          `Fibo 区域 (${snapshot?.armed_count ?? 0})`,
                          `Fibo 구간 (${snapshot?.armed_count ?? 0})`
                        ),
                      },
                    ] as const
                  ).map((st) => (
                    <button
                      key={st.id}
                      type="button"
                      onClick={() => setStageFilter(st.id)}
                      className={`px-2 py-1 rounded text-[11px] font-semibold transition ${
                        stageFilter === st.id
                          ? 'bg-slate-800 text-amber-300 border border-amber-500/40'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {st.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Policy Filter Pills */}
              <div className="flex flex-wrap items-center gap-1 pt-1">
                <span className="text-[10px] font-bold uppercase text-slate-400 mr-1">
                  {tr('Nhánh:', 'Branch:', '分支:', '브랜치:')}
                </span>
                {(
                  [
                    { id: 'ALL', label: tr('Tất cả', 'All', '全部', '전체') },
                    { id: 'sniper_risk', label: tr('N3 · Sniper (LIVE)', 'N3 · Sniper (LIVE)', 'N3 · 狙击 (实盘)', 'N3 · 스나이퍼 (라이브)') },
                    { id: 'elite_sniper_risk', label: 'N4 · Elite' },
                    { id: 'sniper_rr1_horizon24', label: 'N6 · RR≥1 (24h)' },
                    { id: 'm6_risk', label: tr('N2 · M6 Cơ Bản', 'N2 · Basic M6', 'N2 · 基础 M6', 'N2 · 기본 M6') },
                  ] as const
                ).map((pol) => (
                  <button
                    key={pol.id}
                    type="button"
                    onClick={() => setPolicyFilter(pol.id)}
                    className={`px-2 py-0.5 rounded text-[10px] font-bold transition ${
                      policyFilter === pol.id
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/50'
                        : 'bg-slate-950 text-slate-400 hover:text-slate-200 border border-slate-800'
                    }`}
                  >
                    {pol.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="overflow-y-auto space-y-2.5 pr-1 flex-1">
              {loading ? (
                <div className="text-center py-12 text-slate-400 text-xs">Đang tải dữ liệu Radar Fibo...</div>
              ) : filteredItems.length === 0 ? (
                <div className="text-center py-12 px-4 text-slate-400 text-xs">
                  Chưa có tín hiệu trong bộ lọc hiện tại. Nhấn <b>"Quét Fibo Ngay"</b> để quét trực tiếp dữ liệu H4/D1 & H1 từ Binance Futures.
                </div>
              ) : (
                filteredItems.map((item) => {
                  const isSelected = selectedSignal?.id === item.id;
                  const isFired = item.stage === 'FIRED_CONFIRMED_SHORT';
                  const isArmed = item.stage === 'ARMED_IN_FIBO_ZONE';
                  const polKey = item.primary_policy || 'watch_only';
                  const polMeta = POLICY_META[polKey] || POLICY_META.watch_only;
                  const tier = item.conviction_tier || item.trade_setup.conviction_tier || 'B';
                  const notionalPct = item.trade_setup.recommended_notional_pct ?? 10.0;
                  const slM6Pct = item.trade_setup.sl_m6_pct ?? item.trade_setup.stop_loss_pct;
                  const rrM6 = item.trade_setup.rr_m6_tp2 ?? item.trade_setup.rr_tp2;
                  const univTier = item.alpha_layers?.universe_tier;
                  const pitRank = item.alpha_layers?.pit_top50_rank;
                  const gateEval = evaluateSignalGateChecklist(item);

                  return (
                    <div
                      key={item.id}
                      onClick={() => setSelectedId(item.id)}
                      className={`cursor-pointer rounded-xl p-3 border transition ${
                        isSelected
                          ? 'bg-slate-950 border-amber-400 shadow-md shadow-amber-500/10'
                          : gateEval.isActionable
                          ? 'bg-emerald-950/20 border-emerald-500/40 hover:border-emerald-400'
                          : 'bg-slate-950/60 border-slate-800/80 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-sm font-black font-mono text-slate-100">
                            {item.symbol}
                          </span>
                          <span className="px-1.5 py-0.5 text-[10px] font-bold font-mono rounded bg-indigo-950 text-indigo-300 border border-indigo-700/50">
                            {item.higher_timeframe.toUpperCase()} → H1
                          </span>
                          <span
                            className={`px-1.5 py-0.5 text-[10px] font-black font-mono rounded border ${
                              tier === 'S'
                                ? 'bg-amber-500/20 text-amber-300 border-amber-500/50'
                                : tier === 'A'
                                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50'
                                : 'bg-slate-900 text-slate-300 border-slate-700'
                            }`}
                          >
                            {item.score.toFixed(0)}đ · Hạng {tier}
                          </span>
                          {univTier === 'PIT_TOP50' && (
                            <span className="px-1.5 py-0.5 text-[9px] font-mono font-bold rounded bg-cyan-950/80 text-cyan-300 border border-cyan-700/50">
                              PIT #{pitRank}
                            </span>
                          )}
                        </div>
                        <span className="text-xs font-mono font-bold text-amber-400 shrink-0">
                          R:R 1:{rrM6.toFixed(1)}
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center justify-between gap-1.5 mt-1.5">
                        {isFired && gateEval.isActionable ? (
                          <span className="px-2 py-0.5 text-[10px] font-extrabold rounded bg-emerald-950 text-emerald-300 border border-emerald-500/70">
                            ✅ ĐỦ CHUẨN VÀO SHORT
                          </span>
                        ) : isFired ? (
                          <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-slate-900 text-amber-300/90 border border-amber-500/40">
                            ⚠️ H1 ĐỎ NHƯNG BỊ LỌC (KHÔNG VÀO)
                          </span>
                        ) : isArmed ? (
                          <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-amber-950 text-amber-300 border border-amber-700/60">
                            ⏳ ĐANG CHỜ TRONG VÙNG FIBO
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 text-[10px] font-semibold rounded bg-slate-900 text-slate-400 border border-slate-700">
                            CHỜ HỒI FIBO
                          </span>
                        )}
                        <span className={`px-2 py-0.5 text-[10px] font-bold font-mono rounded border ${polMeta.badgeCls}`}>
                          {gateEval.isActionable ? polMeta.label : '⛔ CHỈ QUAN SÁT (CHƯA ĐỦ 4 CỔNG)'}
                        </span>
                      </div>

                      {/* 4-Gate Visual Progress Bar right on card */}
                      <div className="grid grid-cols-4 gap-1 mt-2">
                        {gateEval.gates.map((g) => (
                          <div
                            key={g.step}
                            title={`${g.title}: ${g.detail}`}
                            className={`px-1.5 py-0.5 rounded text-[9px] font-mono font-bold truncate border text-center ${
                              g.passed
                                ? 'bg-emerald-950/60 text-emerald-300 border-emerald-700/50'
                                : 'bg-rose-950/40 text-rose-300/90 border-rose-800/50'
                            }`}
                          >
                            {g.passed ? '✓' : '✗'} {g.shortLabel}
                          </div>
                        ))}
                      </div>

                      <div className="grid grid-cols-4 gap-1.5 mt-2 text-[11px] font-mono">
                        <div>
                          <span className="text-slate-500 block text-[10px]">Sóng sập</span>
                          <span className="text-red-400 font-bold">
                            -{(item.wave.impulse_drop_pct * 100).toFixed(1)}%
                          </span>
                        </div>
                        <div>
                          <span className="text-slate-500 block text-[10px]">Mốc Fibo</span>
                          <span className="text-amber-300 font-bold">
                            {item.h1_confirmation.current_fibo_ratio.toFixed(3)}
                          </span>
                        </div>
                        <div>
                          <span className="text-slate-500 block text-[10px]">SL Mốc 6</span>
                          <span className="text-rose-300 font-bold">+{slM6Pct.toFixed(2)}%</span>
                        </div>
                        <div>
                          <span className="text-slate-500 block text-[10px]">Đi vốn (0.5%R)</span>
                          {gateEval.isActionable ? (
                            <span className="text-emerald-300 font-bold">{notionalPct.toFixed(1)}% NAV</span>
                          ) : (
                            <span className="text-slate-400 font-bold">0% (Đứng ngoài)</span>
                          )}
                        </div>
                      </div>

                      {isFired && !gateEval.isActionable && gateEval.failReasonsVi.length > 0 ? (
                        <div className="mt-2 pt-1.5 border-t border-slate-800/80 text-[10px] font-mono text-rose-300/90">
                          <span className="font-bold text-amber-300">Lý do lọc:</span>{' '}
                          {gateEval.failReasonsVi.slice(0, 2).join(' · ')}
                        </div>
                      ) : (
                        <div className="mt-2 pt-1.5 border-t border-slate-900 text-[11px] text-slate-300 flex items-center justify-between">
                          <span className="truncate">{item.h1_confirmation.reason_vi}</span>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Right Column: Selected Signal Detail, 4-Factor Physics, Risk Sizing & Chart */}
          <div className="lg:col-span-7 space-y-4">
            {selectedSignal ? (
              <>
                <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => onSelectCoin?.(selectedSignal.symbol, selectedFiboHandoff)}
                        className="text-lg font-black font-mono text-amber-300 hover:underline cursor-pointer"
                      >
                        {selectedSignal.symbol}
                      </button>
                      <span className="px-2 py-0.5 text-xs font-mono font-bold rounded bg-slate-950 text-slate-200 border border-slate-700">
                        Giá: {formatPrice(selectedSignal.current_price)}
                      </span>
                      <span className="px-2 py-0.5 text-xs font-mono font-bold rounded bg-indigo-950/90 text-indigo-300 border border-indigo-700/50">
                        {selectedSignal.higher_timeframe.toUpperCase()} → H1
                      </span>
                      {selectedSignal.primary_policy && (
                        <span
                          className={`px-2 py-0.5 text-xs font-mono font-bold rounded border ${
                            (POLICY_META[selectedSignal.primary_policy] || POLICY_META.watch_only).badgeCls
                          }`}
                        >
                          {(POLICY_META[selectedSignal.primary_policy] || POLICY_META.watch_only).label}
                        </span>
                      )}
                      <button
                        type="button"
                        data-testid="fibo-open-decision"
                        onClick={() => onSelectCoin?.(selectedSignal.symbol, selectedFiboHandoff)}
                        className="px-2.5 py-0.5 text-xs font-bold rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 transition cursor-pointer"
                      >
                        {selectedFiboHandoff?.isActionable ? 'Mở Biểu Đồ & Lệnh →' : 'Xem Biểu Đồ →'}
                      </button>
                    </div>

                    <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
                      {(['1h', '4h', '1d'] as const).map((iv) => (
                        <button
                          key={iv}
                          type="button"
                          onClick={() => setChartInterval(iv)}
                          className={`px-2.5 py-1 rounded text-xs font-mono font-bold transition ${
                            chartInterval === iv
                              ? 'bg-amber-500 text-slate-950'
                              : 'text-slate-400 hover:text-slate-200'
                          }`}
                        >
                          Khung {iv.toUpperCase()}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Action Verdict Banner: Make it 100% clear whether to enter or stand aside */}
                  {(() => {
                    const selEval = evaluateSignalGateChecklist(selectedSignal);
                    if (selEval.isActionable) {
                      return (
                        <div className="bg-emerald-950/50 border border-emerald-500/50 rounded-xl p-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                          <div className="text-xs text-emerald-200">
                            <div className="font-extrabold text-emerald-300 text-sm flex items-center gap-1.5">
                              <CheckCircle2 className="w-4 h-4 shrink-0" />
                              KẾT LUẬN: ĐỦ CHUẨN VÀO LỆNH SHORT ({(POLICY_META[selectedSignal.primary_policy || ''] || POLICY_META.sniper_risk).label})
                            </div>
                            <div className="text-[11px] text-emerald-200/90 mt-0.5">
                              Đã vượt qua trọn vẹn cả 4 cổng chuẩn v4.0.21 (F1A Sóng bơm/hồi ≥ 5% · F1B/C Carver/Wave · F2 Sập ≥ 6% & KER ≥ 0.50 · F3/F4 H1 Phá đáy & SL 0.886 ≤ 12%).
                            </div>
                          </div>
                          <div className="bg-slate-950/90 border border-emerald-500/40 rounded-lg px-3 py-1.5 text-right font-mono shrink-0">
                            <div className="text-[10px] text-slate-400">Đi vốn khuyến nghị (0.5%R)</div>
                            <div className="text-sm font-black text-emerald-300">
                              {(selectedSignal.trade_setup.recommended_notional_pct ?? 10).toFixed(2)}% NAV
                            </div>
                          </div>
                        </div>
                      );
                    }
                    return (
                      <div className="bg-rose-950/35 border border-rose-500/40 rounded-xl p-3 space-y-1.5">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="font-extrabold text-rose-300 text-xs sm:text-sm flex items-center gap-1.5">
                            <XCircle className="w-4 h-4 shrink-0 text-rose-400" />
                            KẾT LUẬN: ĐỨNG NGOÀI — KHÔNG VÀO LỆNH (CHỈ THEO DÕI CẤU TRÚC SÓNG)
                          </div>
                          <span className="px-2 py-0.5 rounded bg-slate-950 text-slate-300 border border-slate-700 text-[11px] font-mono font-bold">
                            Đi vốn khuyến nghị: 0% NAV
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-300">
                          Mã này {selectedSignal.stage === 'FIRED_CONFIRMED_SHORT' ? 'đã có nến H1 đóng đỏ trong vùng Fibo (chuẩn M1 cũ)' : 'đang trong quá trình hồi về vùng Fibo'}, nhưng <b>bị hệ thống v4.0.21 chặn không vào lệnh</b> vì thiếu các điều kiện bắt buộc sau:
                        </div>
                        <div className="flex flex-wrap gap-1.5 pt-0.5">
                          {selEval.failReasonsVi.map((reason, rIdx) => (
                            <span
                              key={rIdx}
                              className="px-2 py-0.5 rounded bg-rose-950/80 text-rose-200 border border-rose-700/60 text-[11px] font-mono"
                            >
                              ✗ {reason}
                            </span>
                          ))}
                        </div>
                      </div>
                    );
                  })()}

                  {/* v4.0.21 4-Factor Physics & Risk-Based Position Sizing Panel */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                    <div className="bg-slate-950/90 border border-amber-500/30 rounded-xl p-3 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-amber-300 flex items-center gap-1.5">
                          <Sparkles className="w-3.5 h-3.5" /> Điểm Hội Tụ 4 Tầng Độc Lập
                        </span>
                        <span className="text-sm font-black font-mono text-amber-300">
                          {selectedSignal.score.toFixed(1)} / 100 (Hạng {selectedSignal.conviction_tier || 'B'})
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
                        <div className="bg-slate-900/90 p-2 rounded border border-slate-800">
                          <div className="text-slate-400 text-[10px]">F1A · Sóng Bơm Trước</div>
                          <div className="text-slate-100 font-bold">
                            +{(selectedSignal.wave.prior_pump_pct * 100).toFixed(1)}% ({selectedSignal.alpha_layers?.L1_pump_exhaustion_pts ?? '—'}/25đ)
                          </div>
                        </div>
                        <div className="bg-slate-900/90 p-2 rounded border border-slate-800">
                          <div className="text-slate-400 text-[10px]">F1C & F2 · Wave/Imp KER</div>
                          <div className="text-cyan-300 font-bold">
                            W:{(selectedSignal.wave.wave_ker ?? 0).toFixed(2)} · I:{(selectedSignal.wave.impulse_ker ?? 0).toFixed(2)} ({selectedSignal.alpha_layers?.L2_wave_impulse_physics_pts ?? '—'}/30đ)
                          </div>
                        </div>
                        <div className="bg-slate-900/90 p-2 rounded border border-slate-800">
                          <div className="text-slate-400 text-[10px]">F1B · Carver EWMAC/Accel</div>
                          <div className="text-indigo-300 font-bold">
                            EW:{(selectedSignal.wave.peak_ewmac_16_64 ?? 0).toFixed(2)} · Ac:{(selectedSignal.wave.cur_accel_4_16 ?? 0).toFixed(2)} ({selectedSignal.alpha_layers?.L3_pst_momentum_collapse_pts ?? '—'}/25đ)
                          </div>
                        </div>
                        <div className="bg-slate-900/90 p-2 rounded border border-slate-800">
                          <div className="text-slate-400 text-[10px]">F3 · Vol Hồi/Sập & H1</div>
                          <div className="text-emerald-300 font-bold">
                            Vol {(selectedSignal.h1_confirmation.pullback_vol_ratio ?? 1).toFixed(2)}x ({selectedSignal.alpha_layers?.L4_fibo_h1_trigger_pts ?? '—'}/20đ)
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="bg-slate-950/90 border border-emerald-500/30 rounded-xl p-3 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-emerald-300 flex items-center gap-1.5">
                          <Gauge className="w-3.5 h-3.5" /> Quản Trị Rủi Ro & Đi Vốn v4.0.21
                        </span>
                        <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-emerald-950 text-emerald-300 border border-emerald-600/50">
                          Rủi ro 0.5% NAV / lệnh
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
                        <div className="bg-slate-900/90 p-2 rounded border border-slate-800">
                          <div className="text-slate-400 text-[10px]">Khối Lượng Khuyến Nghị</div>
                          {evaluateSignalGateChecklist(selectedSignal).isActionable ? (
                            <div className="text-emerald-300 font-black text-sm">
                              {(selectedSignal.trade_setup.recommended_notional_pct ?? 10).toFixed(2)}% NAV
                              <span className="text-[10px] text-slate-400 font-normal ml-1">(Max 20%)</span>
                            </div>
                          ) : (
                            <div className="text-slate-400 font-black text-sm">
                              0.00% NAV
                              <span className="text-[10px] text-rose-300 font-normal ml-1">
                                (Nếu đạt chuẩn: {(selectedSignal.trade_setup.recommended_notional_pct ?? 10).toFixed(1)}%)
                              </span>
                            </div>
                          )}
                        </div>
                        <div className="bg-slate-900/90 p-2 rounded border border-slate-800">
                          <div className="text-slate-400 text-[10px]">SL Mốc 6 (Fibo 0.886)</div>
                          <div className="text-rose-300 font-black text-sm">
                            {formatPrice(selectedSignal.trade_setup.sl_m6 ?? selectedSignal.trade_setup.stop_loss)}
                            <span className="text-[10px] text-rose-400 ml-1">
                              (+{(selectedSignal.trade_setup.sl_m6_pct ?? selectedSignal.trade_setup.stop_loss_pct).toFixed(2)}%)
                            </span>
                          </div>
                        </div>
                        <div className="bg-slate-900/90 p-2 rounded border border-slate-800">
                          <div className="text-slate-400 text-[10px]">R:R Chuẩn Mốc 6 (0.886)</div>
                          <div className="text-amber-300 font-bold">
                            TP1 1:{(selectedSignal.trade_setup.rr_m6_tp1 ?? selectedSignal.trade_setup.rr_tp1).toFixed(2)} · TP2 1:{(selectedSignal.trade_setup.rr_m6_tp2 ?? selectedSignal.trade_setup.rr_tp2).toFixed(2)}
                          </div>
                        </div>
                        <div className="bg-slate-900/90 p-2 rounded border border-slate-800">
                          <div className="text-slate-400 text-[10px]">Trần SL ≤ 12% & Horizon</div>
                          <div className="text-slate-200 font-bold">
                            {selectedSignal.trade_setup.sl_within_cap !== false ? (
                              <span className="text-emerald-400">ĐẠT TRẦN SL</span>
                            ) : (
                              <span className="text-red-400">VƯỢT TRẦN 12%</span>
                            )}{' '}
                            · Hold 24h/72h
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Matched Policies Badges */}
                  <div className="flex flex-wrap items-center gap-1.5 pt-1">
                    <span className="text-[10px] font-bold uppercase text-slate-400">Chính sách thỏa mãn:</span>
                    {(selectedSignal.matched_policies && selectedSignal.matched_policies.length > 0
                      ? selectedSignal.matched_policies
                      : ['watch_only']
                    ).map((pid) => {
                      const pm = POLICY_META[pid] || { label: pid, badgeCls: 'bg-slate-900 text-slate-300 border-slate-700' };
                      return (
                        <span key={pid} className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded border ${pm.badgeCls}`}>
                          {pm.label}
                        </span>
                      );
                    })}
                  </div>

                  {/* 4-Gate v4.0.21 Verification Checklist */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                    {evaluateSignalGateChecklist(selectedSignal).gates.map((g) => (
                      <div
                        key={g.step}
                        className={`rounded-lg p-2.5 flex items-start gap-2 border ${
                          g.passed
                            ? 'bg-emerald-950/20 border-emerald-700/40'
                            : 'bg-rose-950/20 border-rose-800/40'
                        }`}
                      >
                        {g.passed ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                        ) : (
                          <XCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                        )}
                        <div className="text-xs flex-1">
                          <div className="font-bold text-slate-100 flex items-center justify-between gap-1">
                            <span>{g.title}</span>
                            <span
                              className={`px-1.5 py-0.2 rounded text-[9px] font-mono font-bold ${
                                g.passed ? 'bg-emerald-950 text-emerald-300' : 'bg-rose-950 text-rose-300'
                              }`}
                            >
                              {g.passed ? 'ĐẠT' : 'CHƯA ĐẠT'}
                            </span>
                          </div>
                          <div className="text-slate-300 mt-0.5 font-mono text-[11px]">{g.detail}</div>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Trade Setup Levels */}
                  <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 pt-2">
                    <div className="bg-slate-950 border border-amber-500/40 rounded-lg p-2.5">
                      <div className="text-[10px] font-bold text-amber-300 uppercase">Entry (Short)</div>
                      <div className="text-sm font-black font-mono text-slate-100 mt-0.5">
                        {formatPrice(selectedSignal.trade_setup.entry_price)}
                      </div>
                      <div className="text-[10px] text-slate-400 font-mono">Fibo 0.5–0.618</div>
                    </div>
                    <div className="bg-slate-950 border border-red-500/40 rounded-lg p-2.5">
                      <div className="text-[10px] font-bold text-red-400 uppercase flex justify-between">
                        <span>SL Mốc 6 (0.886)</span>
                        <span>+{(selectedSignal.trade_setup.sl_m6_pct ?? selectedSignal.trade_setup.stop_loss_pct).toFixed(1)}%</span>
                      </div>
                      <div className="text-sm font-black font-mono text-red-400 mt-0.5">
                        {formatPrice(selectedSignal.trade_setup.sl_m6 ?? selectedSignal.trade_setup.stop_loss)}
                      </div>
                      <div className="text-[10px] text-slate-400 font-mono">
                        SL Đỉnh 1.0: {formatPrice(selectedSignal.trade_setup.stop_loss)}
                      </div>
                    </div>
                    <div className="bg-slate-950 border border-emerald-500/30 rounded-lg p-2.5">
                      <div className="text-[10px] font-bold text-emerald-400 uppercase flex justify-between">
                        <span>TP1 (50% vị thế)</span>
                        <span>-{selectedSignal.trade_setup.tp1_pct.toFixed(1)}%</span>
                      </div>
                      <div className="text-sm font-black font-mono text-emerald-300 mt-0.5">
                        {formatPrice(selectedSignal.trade_setup.tp1)}
                      </div>
                      <div className="text-[10px] text-slate-400 font-mono">
                        Fibo 0.0 · Dời SL về Entry
                      </div>
                    </div>
                    <div className="bg-slate-950 border border-emerald-500/50 rounded-lg p-2.5">
                      <div className="text-[10px] font-bold text-emerald-300 uppercase flex justify-between">
                        <span>TP2 (30% vị thế)</span>
                        <span>-{selectedSignal.trade_setup.tp2_pct.toFixed(1)}%</span>
                      </div>
                      <div className="text-sm font-black font-mono text-emerald-400 mt-0.5">
                        {formatPrice(selectedSignal.trade_setup.tp2)}
                      </div>
                      <div className="text-[10px] text-slate-400 font-mono">
                        Ext 1.272 · Dời SL về TP1
                      </div>
                    </div>
                    <div className="bg-slate-950 border border-emerald-400/60 rounded-lg p-2.5">
                      <div className="text-[10px] font-bold text-emerald-200 uppercase flex justify-between">
                        <span>TP3 (20% vị thế)</span>
                        <span>-{selectedSignal.trade_setup.tp3_pct.toFixed(1)}%</span>
                      </div>
                      <div className="text-sm font-black font-mono text-emerald-300 mt-0.5">
                        {formatPrice(selectedSignal.trade_setup.tp3)}
                      </div>
                      <div className="text-[10px] text-slate-400 font-mono">
                        Ext 1.618 (1:{(selectedSignal.trade_setup.rr_m6_tp2 ?? selectedSignal.trade_setup.rr_tp2).toFixed(1)})
                      </div>
                    </div>
                  </div>
                </div>

                {/* Candlestick Chart */}
                <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-3.5">
                  <Suspense fallback={<div className="h-[360px] flex items-center justify-center text-slate-400 text-xs">Đang tải biểu đồ...</div>}>
                    <CandlestickChart
                      symbol={selectedSignal.symbol}
                      data={chartKlines}
                      height={360}
                      tradeSetup={chartTradeSetup}
                      interval={chartInterval}
                      onIntervalChange={(iv) => {
                        if (iv === '1h' || iv === '4h' || iv === '1d') setChartInterval(iv);
                      }}
                    />
                  </Suspense>
                </div>

                {/* Full Fibonacci Price Ladder */}
                <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 mb-2.5 flex items-center gap-1.5">
                    <Layers className="w-4 h-4 text-amber-400" />
                    Thang Giá Fibonacci ({selectedSignal.higher_timeframe.toUpperCase()})
                  </h3>
                  <div className="grid grid-cols-2 sm:grid-cols-5 lg:grid-cols-10 gap-1.5 text-[11px] font-mono">
                    {[
                      { label: 'Fibo 1.0 (Đỉnh)', val: selectedSignal.fibo_levels.level_1000, cls: 'text-red-400 border-red-500/30' },
                      {
                        label: 'Fibo 0.886 (SL M6)',
                        val:
                          selectedSignal.fibo_levels.level_0886 ||
                          selectedSignal.fibo_levels.level_0000 + 0.886 * selectedSignal.fibo_levels.wave_range,
                        cls: 'text-rose-300 border-rose-500/50 bg-rose-950/30',
                      },
                      { label: 'Fibo 0.786', val: selectedSignal.fibo_levels.level_0786, cls: 'text-orange-300 border-slate-800' },
                      { label: 'Fibo 0.618', val: selectedSignal.fibo_levels.level_0618, cls: 'text-amber-300 border-amber-500/40 bg-amber-950/30' },
                      { label: 'Fibo 0.500', val: selectedSignal.fibo_levels.level_0500, cls: 'text-amber-300 border-amber-500/40 bg-amber-950/30' },
                      { label: 'Fibo 0.382', val: selectedSignal.fibo_levels.level_0382, cls: 'text-slate-300 border-slate-800' },
                      { label: 'Fibo 0.236', val: selectedSignal.fibo_levels.level_0236, cls: 'text-slate-400 border-slate-800' },
                      { label: 'Fibo 0.0 (TP1)', val: selectedSignal.fibo_levels.level_0000, cls: 'text-emerald-300 border-emerald-500/30' },
                      { label: 'Ext 1.272 (TP2)', val: selectedSignal.fibo_levels.ext_1272, cls: 'text-emerald-400 border-emerald-500/40' },
                      { label: 'Ext 1.618 (TP3)', val: selectedSignal.fibo_levels.ext_1618, cls: 'text-emerald-300 border-emerald-500/50' },
                    ].map((lv) => (
                      <div key={lv.label} className={`p-2 rounded-lg border bg-slate-950/80 ${lv.cls}`}>
                        <div className="text-[9px] text-slate-400">{lv.label}</div>
                        <div className="font-bold mt-0.5">{formatPrice(lv.val)}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-12 text-center text-slate-400 text-xs">
                Chọn một cặp giao dịch bên trái để xem chi tiết lưới Fibonacci, định cỡ rủi ro v4.0.21 và biểu đồ xác nhận H1.
              </div>
            )}
          </div>
        </div>
      )}

      {viewMode === 'BACKTEST' && (
        /* BACKTEST v4.0.21 MULTI-YEAR AUDIT VIEW */
        <div className="space-y-4">
          <div className="bg-emerald-950/40 border border-emerald-500/40 rounded-xl p-3.5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div className="flex items-start gap-3">
              <Lock className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
              <div className="text-xs text-emerald-200">
                <div className="font-bold text-emerald-300">
                  Kiểm Định Danh Mục Khớp Thực Tế v4.0.21 (2020–2025) • Khóa Cứng OOS 2026+
                </div>
                <p className="mt-0.5 text-emerald-200/80">
                  Khớp lệnh tại nến 5m OPEN kế tiếp (+5m delay), cộng phí sàn thực tế, trượt giá và lịch sử Funding 8h chuẩn xác. Toàn bộ dữ liệu từ 01/01/2026 trở đi bị cấm chạm tới trong backtest.
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 shrink-0">
              <div className="inline-flex rounded-lg bg-slate-950 p-1 border border-slate-800">
                <button
                  type="button"
                  onClick={() => setAuditWindow('2024_2025')}
                  className={`px-2.5 py-1 rounded text-xs font-bold font-mono transition ${
                    auditWindow === '2024_2025' ? 'bg-amber-500 text-slate-950' : 'text-slate-300'
                  }`}
                >
                  2024–2025 (2 Năm)
                </button>
                <button
                  type="button"
                  onClick={() => setAuditWindow('2020_2025')}
                  className={`px-2.5 py-1 rounded text-xs font-bold font-mono transition ${
                    auditWindow === '2020_2025' ? 'bg-amber-500 text-slate-950' : 'text-slate-300'
                  }`}
                >
                  2020–2025 (6 Năm)
                </button>
              </div>

              <div className="inline-flex rounded-lg bg-slate-950 p-1 border border-slate-800">
                <button
                  type="button"
                  onClick={() => setAuditScenario('standard_vip6')}
                  className={`px-2.5 py-1 rounded text-xs font-bold font-mono transition ${
                    auditScenario === 'standard_vip6' ? 'bg-emerald-500 text-slate-950' : 'text-slate-300'
                  }`}
                >
                  VIP6 (2.5+10 bps)
                </button>
                <button
                  type="button"
                  onClick={() => setAuditScenario('stress_regular')}
                  className={`px-2.5 py-1 rounded text-xs font-bold font-mono transition ${
                    auditScenario === 'stress_regular' ? 'bg-rose-500 text-white' : 'text-slate-300'
                  }`}
                >
                  Stress (5+50 bps)
                </button>
              </div>
            </div>
          </div>

          {/* 6-Policy Family Coupled Portfolio Table */}
          {coupledTableRows.length > 0 && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-amber-300 flex items-center gap-1.5">
                  <Award className="w-4 h-4" />
                  Bảng So Sánh 6 Chính Sách Danh Mục Coupled ({auditWindow.replace('_', '–')} ·{' '}
                  {auditScenario === 'standard_vip6' ? 'Chuẩn VIP6 25bps RT' : 'Khắc Nghiệt Stress 110bps RT'})
                </h3>
                <span className="text-[11px] font-mono text-slate-400">
                  Vũ trụ: Monthly Rolling PIT Top-50 Volume (Wick p90 ≤ 3.2%, Active ≥ 50/63d)
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-xs font-mono text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                      <th className="py-2 px-2.5">Chính Sách (Policy)</th>
                      <th className="py-2 px-2.5 text-right">Net Return</th>
                      <th className="py-2 px-2.5 text-right">Max Drawdown</th>
                      <th className="py-2 px-2.5 text-right">Return / MaxDD</th>
                      <th className="py-2 px-2.5 text-right">Số Lệnh</th>
                      <th className="py-2 px-2.5 text-right">Gross PnL</th>
                      <th className="py-2 px-2.5 text-right">Phí + Trượt</th>
                      <th className="py-2 px-2.5 text-right">Funding 8h</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {coupledTableRows.map((row) => (
                      <tr key={row.id} className="hover:bg-slate-950/60">
                        <td className="py-2.5 px-2.5">
                          <span className={`px-2 py-0.5 text-[10px] font-bold rounded border ${row.meta.badgeCls}`}>
                            {row.meta.label}
                          </span>
                          <div className="text-[10px] text-slate-400 font-sans mt-0.5">{row.meta.desc}</div>
                        </td>
                        <td
                          className={`py-2.5 px-2.5 text-right font-black text-sm ${
                            row.return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'
                          }`}
                        >
                          {row.return_pct >= 0 ? `+${row.return_pct.toFixed(2)}%` : `${row.return_pct.toFixed(2)}%`}
                        </td>
                        <td className="py-2.5 px-2.5 text-right font-bold text-rose-300">
                          {row.max_dd_pct.toFixed(2)}%
                        </td>
                        <td className="py-2.5 px-2.5 text-right font-black text-cyan-300">
                          {row.ret_dd_ratio.toFixed(2)}x
                        </td>
                        <td className="py-2.5 px-2.5 text-right text-slate-200">{row.trades}</td>
                        <td className="py-2.5 px-2.5 text-right text-emerald-300">
                          +{row.gross_pct.toFixed(2)}%
                        </td>
                        <td className="py-2.5 px-2.5 text-right text-amber-300">
                          -{(row.fees_pct + row.slippage_pct).toFixed(2)}%
                        </td>
                        <td
                          className={`py-2.5 px-2.5 text-right font-bold ${
                            row.funding_pct >= 0 ? 'text-emerald-300' : 'text-rose-400'
                          }`}
                        >
                          {row.funding_pct >= 0 ? `+${row.funding_pct.toFixed(2)}%` : `${row.funding_pct.toFixed(2)}%`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Step-by-Step Ablation Progression M1 -> M6 Sniper */}
          {backtest?.v4_0_21_audit?.ablation_milestones && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-cyan-300 mb-3 flex items-center gap-1.5">
                <Layers className="w-4 h-4" />
                 Phân Tích Đóng Góp Từng Tầng Bộ Lọc (Ablation M1 → M6 Sniper trên Benchmark 14 Coin)
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-xs font-mono text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                      <th className="py-2 px-2.5">Mốc Cải Tiến (Milestone)</th>
                      <th className="py-2 px-2.5 text-right">Số Lệnh</th>
                      <th className="py-2 px-2.5 text-right">Win Rate</th>
                      <th className="py-2 px-2.5 text-right">Kỳ Vọng Ròng / Lệnh</th>
                      <th className="py-2 px-2.5 text-right">Profit Factor</th>
                      <th className="py-2 px-2.5 text-right">Coupled NAV</th>
                      <th className="py-2 px-2.5 text-right">Coupled MaxDD</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {backtest.v4_0_21_audit.ablation_milestones.map((m) => (
                      <tr key={m.id} className="hover:bg-slate-950/60">
                        <td className="py-2 px-2.5 font-sans font-semibold text-slate-200">{m.label}</td>
                        <td className="py-2 px-2.5 text-right text-slate-300">{m.trades_14c}</td>
                        <td className="py-2 px-2.5 text-right text-emerald-400 font-bold">{m.win_rate_pct}%</td>
                        <td className="py-2 px-2.5 text-right text-emerald-300 font-bold">+{m.net_ev_pct}%</td>
                        <td className="py-2 px-2.5 text-right text-amber-300 font-bold">{m.pf}</td>
                        <td className="py-2 px-2.5 text-right text-emerald-400 font-black">+{m.coupled_nav_pct}%</td>
                        <td className="py-2 px-2.5 text-right text-rose-300 font-bold">{m.max_dd_pct}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Yearly Performance 2020..2025 */}
          {backtest?.v4_0_21_audit?.yearly_breakdown && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200 mb-3">
                Hiệu Suất Từng Năm Độc Lập (2020 → 2025 · {auditScenario === 'standard_vip6' ? 'Standard VIP6' : 'Stress Regular'})
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-xs font-mono text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                      <th className="py-2 px-2">Chính Sách</th>
                      {['2020', '2021', '2022', '2023', '2024', '2025'].map((yr) => (
                        <th key={yr} className="py-2 px-2 text-right">
                          Năm {yr}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {(['sniper_rr1_horizon24', 'elite_sniper_risk', 'sniper_risk', 'm6_risk', 'reference_m6_fixed'] as const).map(
                      (pid) => {
                        const pm = POLICY_META[pid] || { label: pid };
                        return (
                          <tr key={pid} className="hover:bg-slate-950/60">
                            <td className="py-2 px-2 font-bold text-slate-200">{pm.label}</td>
                            {['2020', '2021', '2022', '2023', '2024', '2025'].map((yr) => {
                              const cell = backtest.v4_0_21_audit?.yearly_breakdown?.[yr]?.[auditScenario]?.[pid];
                              if (!cell) return <td key={yr} className="py-2 px-2 text-right text-slate-500">—</td>;
                              return (
                                <td key={yr} className="py-2 px-2 text-right">
                                  <span className={cell.return_pct >= 0 ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                                    {cell.return_pct >= 0 ? `+${cell.return_pct.toFixed(1)}%` : `${cell.return_pct.toFixed(1)}%`}
                                  </span>
                                  <span className="block text-[10px] text-slate-500">
                                    DD {cell.max_dd_pct.toFixed(1)}% · {cell.trades}L
                                  </span>
                                </td>
                              );
                            })}
                          </tr>
                        );
                      }
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {viewMode === 'SHADOW_COMPARE' && (
        /* PARALLEL SHADOW COMPARISON: LEGACY SYSTEM VS v4.0.21 UPGRADED SYSTEM */
        <div className="space-y-4">
          {/* Header Banner */}
          <div className="bg-slate-900 border border-cyan-500/40 rounded-xl p-4">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="px-2.5 py-0.5 text-[11px] font-mono font-bold rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">
                    SHADOW PARALLEL ENGINE · LIVE 5M
                  </span>
                  <span className="px-2.5 py-0.5 text-[11px] font-mono rounded-full bg-slate-950 text-slate-300 border border-slate-800">
                    Hệ Thống Cũ (M1 Raw · Vốn 20% · SL 1.0) vs. Hệ Thống Nâng Cấp (v4.0.21 · SL 0.886 Ratchet · Risk 0.5% NAV)
                  </span>
                </div>
                <h3 className="text-sm font-bold text-slate-100 mt-2">
                  Đối Chiếu Song Song Thời Gian Thực: Hệ Thống Cũ (Baseline) vs. Hệ Thống Nâng Cấp v4.0.21
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Mọi tín hiệu xác nhận H1 phát sinh trên máy chủ MSI đều được chấm điểm và theo dõi kết quả song song trên cả 2 cơ chế: (1) Cơ chế cũ vào toàn bộ tín hiệu M1 với vốn cố định 20% NAV và SL Đỉnh 1.0 tĩnh; (2) Cơ chế nâng cấp v4.0.21 lọc nhiễu bằng 4 tầng KER/PST/H1-Break, đặt SL Mốc 6 Fibo 0.886, dịch SL về Hòa Vốn (Ratchet BE) khi chạm TP1 và đi vốn theo rủi ro 0.5% NAV.
                </p>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs font-mono shrink-0">
                <div className="bg-slate-950 border border-slate-800 rounded-lg p-2.5">
                  <div className="text-[10px] text-slate-400">Tổng Tín Hiệu M1 Đã Quét</div>
                  <div className="text-sm font-black text-slate-100 mt-0.5">
                    {snapshot?.shadow_comparison?.total_fired_signals ?? 0} lệnh
                  </div>
                </div>
                <div className="bg-slate-950 border border-slate-800 rounded-lg p-2.5">
                  <div className="text-[10px] text-slate-400">Đã Chặn Nhiễu (Sniper)</div>
                  <div className="text-sm font-black text-amber-300 mt-0.5">
                    {snapshot?.shadow_comparison?.tracks?.find((t) => t.track_id === 'sniper_risk')?.rejected_noise_count ?? 0} /{' '}
                    {snapshot?.shadow_comparison?.total_fired_signals ?? 0} lệnh
                  </div>
                </div>
                <div className="bg-slate-950 border border-slate-800 rounded-lg p-2.5 col-span-2 sm:col-span-1">
                  <div className="text-[10px] text-slate-400">Hiệu Suất TB/Lệnh &amp; Δ NAV (M6 vs Cũ)</div>
                  {(() => {
                    const legTrack = snapshot?.shadow_comparison?.tracks?.find((t) => t.track_id === 'legacy_m1_raw');
                    const sniperTrack = snapshot?.shadow_comparison?.tracks?.find((t) => t.track_id === 'sniper_risk');
                    const m6Track = snapshot?.shadow_comparison?.tracks?.find((t) => t.track_id === 'm6_risk');
                    const avgEdge = (sniperTrack?.avg_trade_return_pct ?? 0) - (legTrack?.avg_trade_return_pct ?? 0);
                    const wrEdge = (sniperTrack?.win_rate_pct ?? 0) - (legTrack?.win_rate_pct ?? 0);
                    const deltaNav = m6Track?.delta_nav_vs_legacy_pct ?? 0;
                    return (
                      <div className="mt-0.5 space-y-0.5">
                        <div className={`text-xs font-black ${avgEdge >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {avgEdge >= 0 ? `+${avgEdge.toFixed(2)}%` : `${avgEdge.toFixed(2)}%`}/lệnh · WR{' '}
                          {wrEdge >= 0 ? `+${wrEdge.toFixed(1)}%` : `${wrEdge.toFixed(1)}%`}
                        </div>
                        <div className="text-[10px] text-slate-400">
                          Δ Tổng NAV: {deltaNav >= 0 ? `+${deltaNav.toFixed(2)}%` : `${deltaNav.toFixed(2)}%`}
                        </div>
                      </div>
                    );
                  })()}
                </div>
              </div>
            </div>
          </div>

          {/* Layer 1: 5-Track Live Scanner Shadow Summary Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-cyan-300 flex items-center gap-1.5">
                <Gauge className="w-4 h-4" />
                1. Bảng Đối Chiếu Hiệu Suất 5 Nhánh Shadow Trực Tiếp (Live Scanner 5 Phút · Khởi Điểm NAV = 100.00)
              </h3>
              <span className="text-[11px] font-mono text-slate-400">
                Cập nhật lúc: {snapshot?.shadow_comparison?.updated_at ? new Date(snapshot.shadow_comparison.updated_at).toLocaleString('vi-VN') : '—'}
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono text-left border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                    <th className="py-2 px-2.5">Nhánh Hệ Thống (Shadow Track)</th>
                    <th className="py-2 px-2.5 text-right">Tín Hiệu M1</th>
                    <th className="py-2 px-2.5 text-right">Nhận Lệnh</th>
                    <th className="py-2 px-2.5 text-right">Chặn Nhiễu</th>
                    <th className="py-2 px-2.5 text-right">Đang Mở / Đóng</th>
                    <th className="py-2 px-2.5 text-right">Win Rate</th>
                    <th className="py-2 px-2.5 text-right">TB Lợi Nhuận/Lệnh</th>
                    <th className="py-2 px-2.5 text-right">Tác Động NAV</th>
                    <th className="py-2 px-2.5 text-right">MaxDD</th>
                    <th className="py-2 px-2.5 text-right">Δ Cải Thiện vs Cũ</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {(snapshot?.shadow_comparison?.tracks || []).map((tr) => {
                    const isLegacy = tr.track_id === 'legacy_m1_raw';
                    const pm = POLICY_META[tr.track_id];
                    const legTrack = snapshot?.shadow_comparison?.tracks?.find((t) => t.track_id === 'legacy_m1_raw');
                    const avgDiff = tr.avg_trade_return_pct - (legTrack?.avg_trade_return_pct ?? 0);
                    return (
                      <tr key={tr.track_id} className={isLegacy ? 'bg-rose-950/15 hover:bg-rose-950/25' : 'hover:bg-slate-950/60'}>
                        <td className="py-2.5 px-2.5 font-sans">
                          <div className="flex flex-wrap items-center gap-1.5">
                            {isLegacy ? (
                              <span className="px-1.5 py-0.5 text-[10px] font-mono font-bold rounded border bg-rose-950 text-rose-300 border-rose-500/50">
                                M1 CŨ (GỐC)
                              </span>
                            ) : pm ? (
                              <span className={`px-1.5 py-0.5 text-[10px] font-mono font-bold rounded border ${pm.badgeCls}`}>
                                {pm.label}
                              </span>
                            ) : null}
                            <span className={`font-bold ${isLegacy ? 'text-rose-300' : 'text-emerald-300'}`}>
                              {tr.label_vi}
                            </span>
                          </div>
                        </td>
                        <td className="py-2.5 px-2.5 text-right text-slate-300">{tr.total_m1_signals}</td>
                        <td className="py-2.5 px-2.5 text-right font-bold text-slate-100">{tr.accepted_count}</td>
                        <td className="py-2.5 px-2.5 text-right text-amber-300">
                          {tr.rejected_noise_count > 0 ? `${tr.rejected_noise_count} lệnh` : '0'}
                        </td>
                        <td className="py-2.5 px-2.5 text-right text-slate-300">
                          {tr.active_count} mở / {tr.closed_count} đóng
                        </td>
                        <td className="py-2.5 px-2.5 text-right font-bold text-cyan-300">
                          {tr.accepted_count > 0 ? `${tr.win_rate_pct.toFixed(1)}%` : '—'}
                        </td>
                        <td
                          className={`py-2.5 px-2.5 text-right font-bold ${
                            tr.avg_trade_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'
                          }`}
                        >
                          {tr.accepted_count > 0
                            ? tr.avg_trade_return_pct >= 0
                              ? `+${tr.avg_trade_return_pct.toFixed(2)}%`
                              : `${tr.avg_trade_return_pct.toFixed(2)}%`
                            : '—'}
                        </td>
                        <td
                          className={`py-2.5 px-2.5 text-right font-black ${
                            tr.cum_nav_pnl_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'
                          }`}
                        >
                          {tr.cum_nav_pnl_pct >= 0 ? `+${tr.cum_nav_pnl_pct.toFixed(3)}%` : `${tr.cum_nav_pnl_pct.toFixed(3)}%`}
                        </td>
                        <td className="py-2.5 px-2.5 text-right text-rose-300">{tr.max_dd_pct.toFixed(3)}%</td>
                        <td className="py-2.5 px-2.5 text-right">
                          {isLegacy ? (
                            <span className="text-slate-500 font-bold">Mốc gốc (0.000%)</span>
                          ) : (
                            <div>
                              <div className={`font-black ${tr.delta_nav_vs_legacy_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                {tr.delta_nav_vs_legacy_pct >= 0
                                  ? `+${tr.delta_nav_vs_legacy_pct.toFixed(3)}%`
                                  : `${tr.delta_nav_vs_legacy_pct.toFixed(3)}%`}
                              </div>
                              <div className={`text-[10px] ${avgDiff >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
                                TB/lệnh: {avgDiff >= 0 ? `+${avgDiff.toFixed(2)}%` : `${avgDiff.toFixed(2)}%`}
                              </div>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Layer 2: Signal-by-Signal Shadow Audit Ledger */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-amber-300 flex items-center gap-1.5">
                <Layers className="w-4 h-4" />
                2. Sổ Cái Đối Chiếu Từng Lệnh Thời Gian Thực (Signal-by-Signal Shadow Audit: Hệ Thống Cũ vs. v4.0.21)
              </h3>
              <span className="text-[11px] font-mono text-slate-400">
                So sánh trực tiếp quyết định lọc nhiễu, khoảng cách SL (1.0 vs 0.886 Ratchet), định cỡ vốn (20% vs Risk 0.5%) và PnL từng lệnh
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono text-left border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                    <th className="py-2 px-2">Coin / Khung</th>
                    <th className="py-2 px-2">Thời Gian</th>
                    <th className="py-2 px-2 text-right">Entry → Giá Live</th>
                    <th className="py-2 px-2 bg-rose-950/20 border-l border-slate-800">Hệ Thống Cũ (M1 Raw · 20% NAV)</th>
                    <th className="py-2 px-2 text-right bg-rose-950/20">PnL NAV Cũ</th>
                    <th className="py-2 px-2 bg-emerald-950/20 border-l border-slate-800">Hệ Thống Mới (v4.0.21 · Risk 0.5%)</th>
                    <th className="py-2 px-2 text-right bg-emerald-950/20">PnL NAV Mới (M6)</th>
                    <th className="py-2 px-2 text-right border-l border-slate-800">Δ Chênh Lệch</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {(snapshot?.shadow_comparison?.signals_ledger || []).map((item) => {
                    const deltaM6 = item.v4.delta_m6_vs_legacy_nav_pct;
                    return (
                      <tr key={item.id} className="hover:bg-slate-950/60">
                        <td className="py-2.5 px-2">
                          <button
                            type="button"
                            onClick={() => onSelectCoin?.(item.symbol)}
                            className="font-black text-slate-100 hover:text-amber-300 transition text-left"
                          >
                            {item.symbol}
                          </button>
                          <span className="ml-1.5 px-1.5 py-0.2 text-[10px] rounded bg-slate-800 text-slate-300">
                            {item.higher_timeframe.toUpperCase()}
                          </span>
                          <div className="text-[10px] text-slate-400 mt-0.5">
                            Wave KER: {item.wave_ker.toFixed(2)} · Imp KER: {item.impulse_ker.toFixed(2)}
                          </div>
                        </td>
                        <td className="py-2.5 px-2 text-slate-300 text-[11px]">{item.signal_time}</td>
                        <td className="py-2.5 px-2 text-right">
                          <div className="text-slate-200">
                            ${formatPrice(item.entry_price)} → <span className="font-bold text-white">${formatPrice(item.current_price)}</span>
                          </div>
                          <div className={`text-[10px] font-bold ${item.price_move_pct <= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            Biến động giá: {item.price_move_pct > 0 ? `+${item.price_move_pct.toFixed(2)}%` : `${item.price_move_pct.toFixed(2)}%`}
                          </div>
                        </td>
                        <td className="py-2.5 px-2 bg-rose-950/10 border-l border-slate-800/80">
                          <div className="flex items-center gap-1.5">
                            <span className="px-1.5 py-0.2 rounded text-[10px] bg-rose-950 text-rose-300 border border-rose-700/50">
                              {item.legacy.status}
                            </span>
                            <span className="text-[10px] text-slate-400">Vốn 20.0% NAV</span>
                          </div>
                          <div className="text-[10px] text-slate-400 mt-0.5">
                            SL 1.0: ${formatPrice(item.legacy.stop_loss)} (+{item.legacy.stop_loss_pct.toFixed(2)}%) · Lệnh:{' '}
                            <span className={item.legacy.net_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                              {item.legacy.net_return_pct >= 0 ? `+${item.legacy.net_return_pct.toFixed(2)}%` : `${item.legacy.net_return_pct.toFixed(2)}%`}
                            </span>
                          </div>
                        </td>
                        <td
                          className={`py-2.5 px-2 text-right font-bold bg-rose-950/10 ${
                            item.legacy.nav_pnl_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'
                          }`}
                        >
                          {item.legacy.nav_pnl_pct >= 0 ? `+${item.legacy.nav_pnl_pct.toFixed(3)}%` : `${item.legacy.nav_pnl_pct.toFixed(3)}%`}
                        </td>
                        <td className="py-2.5 px-2 bg-emerald-950/10 border-l border-slate-800/80 font-sans">
                          {item.v4.accepted_m6 ? (
                            <div>
                              <div className="flex flex-wrap items-center gap-1.5 font-mono">
                                <span className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-600/50">
                                  NHẬN LỆNH ({item.v4.primary_policy.toUpperCase()})
                                </span>
                                <span className="text-[10px] text-cyan-300">
                                  Vốn {item.v4.notional_pct.toFixed(1)}% NAV
                                </span>
                                <span className="text-[10px] text-slate-300">[{item.v4.status}]</span>
                              </div>
                              <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                                SL 0.886: ${formatPrice(item.v4.sl_m6)} (+{item.v4.sl_m6_pct.toFixed(2)}%) · Lệnh:{' '}
                                <span className={item.v4.raw_net_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                                  {item.v4.raw_net_return_pct >= 0 ? `+${item.v4.raw_net_return_pct.toFixed(2)}%` : `${item.v4.raw_net_return_pct.toFixed(2)}%`}
                                </span>
                              </div>
                              {!item.v4.accepted_sniper && item.v4.sniper_rejection_reasons_vi.length > 0 && (
                                <div className="text-[10px] text-amber-300/90 mt-0.5">
                                  Ghi chú Sniper: {item.v4.sniper_rejection_reasons_vi.join(' · ')}
                                </div>
                              )}
                            </div>
                          ) : (
                            <div>
                              <span className="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-amber-950 text-amber-300 border border-amber-600/50">
                                ĐÃ CHẶN NHIỄU (FILTERED OUT)
                              </span>
                              <div className="text-[10px] text-amber-200/90 mt-0.5">
                                Lý do chặn: {item.v4.m6_rejection_reasons_vi.join(' · ') || 'Không đạt chuẩn sóng v4.0.21'}
                              </div>
                            </div>
                          )}
                        </td>
                        <td
                          className={`py-2.5 px-2 text-right font-bold bg-emerald-950/10 ${
                            item.v4.m6_nav_pnl_pct > 0
                              ? 'text-emerald-400'
                              : item.v4.m6_nav_pnl_pct < 0
                              ? 'text-rose-400'
                              : 'text-slate-400'
                          }`}
                        >
                          {item.v4.accepted_m6
                            ? item.v4.m6_nav_pnl_pct >= 0
                              ? `+${item.v4.m6_nav_pnl_pct.toFixed(3)}%`
                              : `${item.v4.m6_nav_pnl_pct.toFixed(3)}%`
                            : '0.000% (An toàn)'}
                        </td>
                        <td
                          className={`py-2.5 px-2 text-right font-black border-l border-slate-800/80 ${
                            deltaM6 > 0 ? 'text-emerald-400' : deltaM6 < 0 ? 'text-rose-400' : 'text-slate-400'
                          }`}
                        >
                          {deltaM6 > 0 ? `+${deltaM6.toFixed(3)}%` : `${deltaM6.toFixed(3)}%`}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Layer 3: Paper OOS v1 (24/7) Baseline (Fixed 20%) vs 5 Upgraded v4.0.21 Policies */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-emerald-300 flex items-center gap-1.5">
                <Cpu className="w-4 h-4" />
                {tr(
                  '3. Đối Chiếu 6 Nhánh Paper OOS v1 (N1 → N6): Nhánh Gốc N1 (Vốn 20%) vs. 5 Nhánh Rủi Ro 0.5% NAV (N2–N6)',
                  '3. Paper OOS v1 6-Branch Comparison (N1 → N6): Baseline N1 (20% Fixed) vs. 5 Risk 0.5% NAV Branches (N2–N6)',
                  '3. Paper OOS v1 六大分支对比 (N1 → N6)：基准 N1 (固定 20%) vs 5大 0.5% NAV 风险分支 (N2–N6)',
                  '3. Paper OOS v1 6개 브랜치 비교 (N1 → N6): 기준 N1 (20% 고정) vs 5개 0.5% NAV 리스크 브랜치 (N2–N6)'
                )}
              </h3>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowBranchesGuide((prev) => !prev)}
                  className="px-2.5 py-1 rounded text-[11px] font-mono font-bold bg-slate-950 hover:bg-slate-800 text-cyan-300 border border-cyan-500/40 transition cursor-pointer"
                >
                  {showBranchesGuide
                    ? tr('Ẩn bảng mã N1–N6 ▲', 'Hide N1–N6 Guide ▲', '隐藏 N1–N6 指南 ▲', 'N1–N6 가이드 숨기기 ▲')
                    : tr('Bảng mã 6 nhánh (N1–N6) ▼', 'N1–N6 Branch Guide ▼', 'N1–N6 六大分支指南 ▼', 'N1–N6 6개 브랜치 가이드 ▼')}
                </button>
                <span className="text-[11px] font-mono text-slate-400">
                  {tr('Trạng thái Daemon', 'Daemon Status', '守护进程状态', '데몬 상태')}: {paperOos?.health?.code || 'OBSERVING'} ·{' '}
                  {tr('Vũ trụ PIT', 'PIT Universe', 'PIT 选币池', 'PIT 유니버스')} {paperOos?.study?.membership_month || '2026-10'} (
                  {paperOos?.study?.membership_count ?? 50} coin)
                </span>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono text-left border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                    <th className="py-2 px-2.5">{tr('Mã Nhánh (N1–N6)', 'Branch (N1–N6)', '分支 (N1–N6)', '브랜치 (N1–N6)')}</th>
                    <th className="py-2 px-2.5">{tr('Cơ Chế Quản Trị Vốn & Thoát Lệnh', 'Sizing & Exit Rules', '仓位与平仓规则', '비중 & 청산 규칙')}</th>
                    <th className="py-2 px-2.5 text-right">NAV (VIP6)</th>
                    <th className="py-2 px-2.5 text-right">Net Return (VIP6)</th>
                    <th className="py-2 px-2.5 text-right">NAV (Stress)</th>
                    <th className="py-2 px-2.5 text-right">{tr('Mở / Đóng', 'Open / Closed', '持仓 / 已平', '보유 / 종료')}</th>
                    <th className="py-2 px-2.5 text-right">{tr('Chuẩn Lịch Sử 2024–2025 (VIP6)', '2024–2025 Benchmark (VIP6)', '2024–2025 历史基准 (VIP6)', '2024–2025 벤치마크 (VIP6)')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {(['reference_m6_fixed', 'm6_risk', 'sniper_risk', 'elite_sniper_risk', 'sniper_horizon24', 'sniper_rr1_horizon24'] as const).map(
                    (pid) => {
                      const pm = POLICY_META[pid] || { label: pid, badgeCls: 'bg-slate-900 text-slate-300 border-slate-700', desc: '' };
                      const vipAcc = (paperOos?.accounts || []).find((a) => a.policy_id === pid && a.scenario_id === 'standard_vip6');
                      const strAcc = (paperOos?.accounts || []).find((a) => a.policy_id === pid && a.scenario_id === 'stress_regular');
                      const hist = backtest?.v4_0_21_audit?.coupled_portfolio?.['2024_2025']?.['standard_vip6']?.[pid]?.metric;
                      const isRef = pid === 'reference_m6_fixed';
                      return (
                        <tr key={pid} className={isRef ? 'bg-slate-950/80' : 'hover:bg-slate-950/60'}>
                          <td className="py-2.5 px-2.5">
                            <span className={`px-2 py-0.5 text-[10px] font-bold rounded border ${pm.badgeCls}`}>
                              {pm.label}
                            </span>
                          </td>
                          <td className="py-2.5 px-2.5 font-sans text-slate-300 text-[11px]">{pm.desc}</td>
                          <td className="py-2.5 px-2.5 text-right font-black text-slate-100">
                            {vipAcc ? vipAcc.equity.toFixed(4) : '100.0000'}
                          </td>
                          <td
                            className={`py-2.5 px-2.5 text-right font-bold ${
                              (vipAcc?.net_return_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                            }`}
                          >
                            {vipAcc
                              ? vipAcc.net_return_pct >= 0
                                ? `+${vipAcc.net_return_pct.toFixed(3)}%`
                                : `${vipAcc.net_return_pct.toFixed(3)}%`
                              : '+0.000%'}
                          </td>
                          <td className="py-2.5 px-2.5 text-right text-slate-300">
                            {strAcc ? strAcc.equity.toFixed(4) : '100.0000'}
                          </td>
                          <td className="py-2.5 px-2.5 text-right text-amber-300">
                            {vipAcc?.open_positions_count ?? 0} / {vipAcc?.closed_trades_count ?? 0}
                          </td>
                          <td className="py-2.5 px-2.5 text-right">
                            {hist ? (
                              <span className="text-emerald-400 font-bold">
                                +{hist.return_pct.toFixed(2)}% <span className="text-slate-400 font-normal">(MaxDD {hist.max_dd_pct.toFixed(2)}%)</span>
                              </span>
                            ) : (
                              '—'
                            )}
                          </td>
                        </tr>
                      );
                    }
                  )}
                </tbody>
              </table>
            </div>

            {/* Live Open Positions in Paper OOS v1 (Standard VIP6 Comparison) */}
            {(paperOos?.open_positions || []).length > 0 && (
              <div className="mt-4 pt-3 border-t border-slate-800/80">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5">
                  <div className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5" />
                    Chi Tiết Lệnh Đang Vào Trực Tiếp Trong Paper OOS v1 ({(paperOos?.open_positions || []).length} vị thế đang mở trên 12 tài khoản)
                  </div>
                  <button
                    type="button"
                    onClick={() => setViewMode('PAPER_OOS')}
                    className="text-[11px] font-mono font-bold text-emerald-300 hover:underline cursor-pointer"
                  >
                    Mở toàn bộ sổ lệnh 12 tài khoản Paper OOS →
                  </button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs font-mono text-left border-collapse">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                        <th className="py-1.5 px-2">Tài Khoản (Chính Sách · Kịch Bản)</th>
                        <th className="py-1.5 px-2">Coin / Khung</th>
                        <th className="py-1.5 px-2 text-right">Entry (Khớp) → Mark</th>
                        <th className="py-1.5 px-2 text-right">SL Hiệu Lực (Mốc 6)</th>
                        <th className="py-1.5 px-2 text-right">Mốc Chốt Lời (TP1 / TP2 / TP3)</th>
                        <th className="py-1.5 px-2 text-right">Quy Mô Vốn (% NAV)</th>
                        <th className="py-1.5 px-2 text-right">Rủi Ro Tối Đa SL</th>
                        <th className="py-1.5 px-2 text-right">PnL Ròng (% NAV)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {(paperOos?.open_positions || []).map((pos: Record<string, any>) => {
                        const pm = POLICY_META[pos.policy_id] || { label: pos.policy_id, badgeCls: 'bg-slate-900 text-slate-300 border-slate-700' };
                        return (
                          <tr key={`${pos.account_id}-${pos.id}`} className="hover:bg-slate-950/60">
                            <td className="py-2 px-2">
                              <span className={`px-1.5 py-0.2 text-[10px] font-bold rounded border ${pm.badgeCls}`}>
                                {pm.label}
                              </span>
                              <span className="ml-1.5 text-[10px] text-slate-400">
                                ({pos.scenario_id === 'standard_vip6' ? 'VIP6' : 'Stress'})
                              </span>
                            </td>
                            <td className="py-2 px-2">
                              <button
                                type="button"
                                onClick={() => onSelectCoin?.(pos.symbol)}
                                className="font-black text-amber-300 hover:underline"
                              >
                                {pos.symbol}
                              </button>
                              <span className="ml-1 px-1 py-0.2 text-[10px] rounded bg-slate-800 text-slate-300">
                                {String(pos.tf || '').toUpperCase()}
                              </span>
                            </td>
                            <td className="py-2 px-2 text-right">
                              <div>
                                ${formatPrice(pos.entry_price)} <span className="text-slate-500">(${formatPrice(pos.execution_price)})</span> →{' '}
                                <span className="font-bold text-white">${formatPrice(pos.mark_price)}</span>
                              </div>
                              <div className={`text-[10px] ${pos.price_move_pct <= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                Giá: {pos.price_move_pct > 0 ? `+${pos.price_move_pct.toFixed(2)}%` : `${pos.price_move_pct.toFixed(2)}%`}
                              </div>
                            </td>
                            <td className="py-2 px-2 text-right">
                              <div className="text-rose-300 font-bold">${formatPrice(pos.active_stop)}</div>
                              <div className="text-[10px] text-slate-400">
                                +{Number(pos.sl_distance_pct || 0).toFixed(2)}% ({pos.sl_ratchet_state === 'INITIAL_SL' ? 'SL 0.886 gốc' : pos.sl_ratchet_state})
                              </div>
                            </td>
                            <td className="py-2 px-2 text-right text-[11px]">
                              <span className={pos.tp1_hit ? 'text-emerald-400 font-bold' : 'text-slate-300'}>
                                TP1: ${formatPrice(pos.tp1)} {pos.tp1_hit ? '✓' : ''}
                              </span>
                              <span className="block text-[10px] text-slate-400">
                                TP2: ${formatPrice(pos.tp2)} · TP3: ${formatPrice(pos.tp3)}
                              </span>
                            </td>
                            <td className="py-2 px-2 text-right">
                              <div className="font-bold text-cyan-300">{Number(pos.reference_notional_pct || 0).toFixed(2)}% NAV</div>
                              <div className="text-[10px] text-slate-400">Còn lại: {Number(pos.remaining_pct ?? 100).toFixed(0)}%</div>
                            </td>
                            <td className="py-2 px-2 text-right">
                              <span className={Number(pos.stop_risk_pct || 0) > 1.0 ? 'text-rose-400 font-bold' : 'text-emerald-300 font-bold'}>
                                -{Number(pos.stop_risk_pct || 0).toFixed(2)}% NAV
                              </span>
                            </td>
                            <td
                              className={`py-2 px-2 text-right font-black ${
                                Number(pos.nav_pnl_pct || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                              }`}
                            >
                              {Number(pos.nav_pnl_pct || 0) >= 0
                                ? `+${Number(pos.nav_pnl_pct || 0).toFixed(3)}%`
                                : `${Number(pos.nav_pnl_pct || 0).toFixed(3)}%`}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>

          {/* Layer 4: Main Scanner Champion (pump_filter_v1) vs Challenger (candidate_filter_v2) Parallel Shadow Audit */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-violet-300 flex items-center gap-1.5">
                <Award className="w-4 h-4" />
                4. Đối Chiếu Song Song Nhánh Chính (Main Scanner): Champion `pump_filter_v1` (Cũ) vs. Challenger `candidate_filter_v2` (Mới)
              </h3>
              <span className="text-[11px] font-mono text-slate-400">
                Vũ trụ ghép cặp: {candidateCompare?.paired_count ?? 150} coin · Trạng thái: {candidateCompare?.status || 'active'}
              </span>
            </div>

            {(() => {
              const mV1 = candidateCompare?.comparison?.metrics?.['pump_filter_v1'];
              const mV2 = candidateCompare?.comparison?.metrics?.['candidate_filter_v2'];
              return (
                <div className="space-y-3">
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs font-mono text-left border-collapse">
                      <thead>
                        <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                          <th className="py-2 px-2.5">Bộ Lọc Ứng Viên (Filter Engine)</th>
                          <th className="py-2 px-2.5 text-right">Số Coin Chọn / Chu Kỳ</th>
                          <th className="py-2 px-2.5 text-right">Precision@10</th>
                          <th className="py-2 px-2.5 text-right">Anchor Precision</th>
                          <th className="py-2 px-2.5 text-right">Anchor Recall</th>
                          <th className="py-2 px-2.5 text-right">Event Recall (Bắt Đợt Xả)</th>
                          <th className="py-2 px-2.5 text-right">Lead Time Trung Vị</th>
                          <th className="py-2 px-2.5 text-right">Mẫu Đã Phân Giải</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/70">
                        <tr className="bg-rose-950/10">
                          <td className="py-2.5 px-2.5 font-sans font-bold text-rose-300">
                            Hệ Thống Cũ · Champion `pump_filter_v1`
                          </td>
                          <td className="py-2.5 px-2.5 text-right text-slate-200">
                            {candidateCompare?.champion_selected ?? 0} coin
                          </td>
                          <td className="py-2.5 px-2.5 text-right text-slate-200">
                            {mV1?.precision_at_10 != null ? `${(mV1.precision_at_10 * 100).toFixed(2)}%` : '—'}
                          </td>
                          <td className="py-2.5 px-2.5 text-right text-slate-200">
                            {mV1?.anchor_precision != null ? `${(mV1.anchor_precision * 100).toFixed(2)}%` : '—'}
                          </td>
                          <td className="py-2.5 px-2.5 text-right text-slate-200">
                            {mV1?.anchor_recall != null ? `${(mV1.anchor_recall * 100).toFixed(2)}%` : '—'}
                          </td>
                          <td className="py-2.5 px-2.5 text-right text-slate-200">
                            {mV1?.event_recall != null ? `${(mV1.event_recall * 100).toFixed(2)}%` : '—'}
                          </td>
                          <td className="py-2.5 px-2.5 text-right text-slate-200">
                            {mV1?.median_lead_time_minutes != null ? `${mV1.median_lead_time_minutes.toFixed(0)} phút` : '—'}
                          </td>
                          <td className="py-2.5 px-2.5 text-right text-slate-300">
                            {mV1?.resolved ?? 0} ({mV1?.selected_resolved ?? 0} chọn)
                          </td>
                        </tr>
                        <tr className="bg-emerald-950/10">
                          <td className="py-2.5 px-2.5 font-sans font-bold text-emerald-300">
                            Hệ Thống Nâng Cấp · Challenger `candidate_filter_v2` (Shadow)
                          </td>
                          <td className="py-2.5 px-2.5 text-right font-bold text-emerald-300">
                            {candidateCompare?.challenger_selected ?? 0} coin
                          </td>
                          <td className="py-2.5 px-2.5 text-right font-bold text-emerald-400">
                            {mV2?.precision_at_10 != null ? `${(mV2.precision_at_10 * 100).toFixed(2)}%` : '—'}
                          </td>
                          <td className="py-2.5 px-2.5 text-right font-bold text-emerald-400">
                            {mV2?.anchor_precision != null ? `${(mV2.anchor_precision * 100).toFixed(2)}%` : '—'}
                          </td>
                          <td className="py-2.5 px-2.5 text-right font-bold text-emerald-400">
                            {mV2?.anchor_recall != null ? `${(mV2.anchor_recall * 100).toFixed(2)}%` : '—'}
                          </td>
                          <td className="py-2.5 px-2.5 text-right font-black text-emerald-400">
                            {mV2?.event_recall != null ? `${(mV2.event_recall * 100).toFixed(2)}%` : '—'}
                          </td>
                          <td className="py-2.5 px-2.5 text-right font-bold text-cyan-300">
                            {mV2?.median_lead_time_minutes != null ? `${mV2.median_lead_time_minutes.toFixed(0)} phút` : '—'}
                          </td>
                          <td className="py-2.5 px-2.5 text-right text-slate-200">
                            {mV2?.resolved ?? 0} ({mV2?.selected_resolved ?? 0} chọn)
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  {candidateCompare?.challenger_only && candidateCompare.challenger_only.length > 0 && (
                    <div className="bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs">
                      <span className="text-violet-300 font-bold">
                        Ứng viên phát hiện sớm chỉ có ở Challenger V2 ({candidateCompare.challenger_only.length} coin):
                      </span>{' '}
                      <span className="font-mono text-slate-300">
                        {candidateCompare.challenger_only.slice(0, 20).join(', ')}
                      </span>
                    </div>
                  )}
                </div>
              );
            })()}
          </div>
        </div>
      )}

      {viewMode === 'PAPER_OOS' && (
        /* PAPER OOS V1 (24/7 MSI) MONITOR VIEW */
        <div className="space-y-4">
          <div className="bg-slate-900 border border-emerald-500/40 rounded-xl p-4">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`px-2.5 py-0.5 text-[11px] font-mono font-bold rounded-full border ${
                      paperOos?.health?.severity === 'ok'
                        ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                        : 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                    }`}
                  >
                    {paperOos?.health?.code || 'INITIALIZING'}
                  </span>
                  <span className="px-2.5 py-0.5 text-[11px] font-mono rounded-full bg-slate-950 text-slate-300 border border-slate-800">
                    Orders Allowed: {String(paperOos?.health?.orders_allowed ?? false)} (Paper Observer Only)
                  </span>
                  <span className="px-2.5 py-0.5 text-[11px] font-mono rounded-full bg-indigo-950 text-indigo-300 border border-indigo-700/50">
                    Protocol Verified: {paperOos?.study?.protocol_verified ? 'SHA256 OK' : 'PENDING'}
                  </span>
                </div>
                <h3 className="text-sm font-bold text-slate-100 mt-2">
                  {paperOos?.health?.headline || ' Đang tải trạng thái Paper OOS v1...'}
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">{paperOos?.health?.detail}</p>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono shrink-0">
                <div className="bg-slate-950 border border-slate-800 rounded-lg p-2.5">
                  <div className="text-[10px] text-slate-400">Tiến Độ Nghiên Cứu</div>
                  <div className="text-sm font-black text-emerald-300 mt-0.5">
                    {paperOos?.study?.completed_full_weeks ?? 0} / {paperOos?.study?.target_full_weeks ?? 104} tuần
                  </div>
                </div>
                <div className="bg-slate-950 border border-slate-800 rounded-lg p-2.5">
                  <div className="text-[10px] text-slate-400">Vũ Trụ PIT ({paperOos?.study?.membership_month || '—'})</div>
                  <div className="text-sm font-black text-cyan-300 mt-0.5">
                    {paperOos?.study?.active_signal_universe_count ?? 50} / {paperOos?.study?.membership_count ?? 50} coin
                  </div>
                </div>
                <div className="bg-slate-950 border border-slate-800 rounded-lg p-2.5">
                  <div className="text-[10px] text-slate-400">Vị Thế Đang Mở</div>
                  <div className="text-sm font-black text-amber-300 mt-0.5">
                    {paperOos?.study?.open_positions_count ?? 0} lệnh
                  </div>
                </div>
                <div className="bg-slate-950 border border-slate-800 rounded-lg p-2.5">
                  <div className="text-[10px] text-slate-400">Lệnh Đã Đóng</div>
                  <div className="text-sm font-black text-slate-100 mt-0.5">
                    {paperOos?.study?.closed_trades_count ?? 0} lệnh
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* 12 Isolated Accounts Matrix */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-emerald-300 flex items-center gap-1.5">
                <Cpu className="w-4 h-4" />
                {tr(
                  '12 Tài Khoản Paper OOS Độc Lập (6 Nhánh N1–N6 × 2 Kịch Bản Phí · Vốn Quy Đổi $10,000.00 / TK · NAV Gốc = 100)',
                  '12 Isolated Paper OOS Accounts (6 Branches N1–N6 × 2 Cost Scenarios · $10,000.00 Notional / Acc · Base NAV = 100)',
                  '12个独立 Paper OOS 账户 (6大分支 N1–N6 × 2种成本场景 · 折算 $10,000.00 / 账户 · 初始 NAV = 100)',
                  '12개 독립 Paper OOS 계좌 (6개 브랜치 N1–N6 × 2개 비용 시나리오 · 계좌당 $10,000.00 · 기준 NAV = 100)'
                )}
              </h3>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowBranchesGuide((prev) => !prev)}
                  className="px-2.5 py-1 rounded text-[11px] font-mono font-bold bg-slate-950 hover:bg-slate-800 text-cyan-300 border border-cyan-500/40 transition cursor-pointer"
                >
                  {showBranchesGuide
                    ? tr('Ẩn bảng mã N1–N6 ▲', 'Hide N1–N6 Guide ▲', '隐藏 N1–N6 指南 ▲', 'N1–N6 가이드 숨기기 ▲')
                    : tr('Bảng mã 6 nhánh (N1–N6) ▼', 'N1–N6 Branch Guide ▼', 'N1–N6 六大分支指南 ▼', 'N1–N6 6개 브랜치 가이드 ▼')}
                </button>
                <span className="text-[11px] font-mono text-slate-400">
                  {tr(
                    'Bấm vào từng dòng tài khoản (N1..N6) để lọc riêng lệnh đang vào của tài khoản đó',
                    'Click any account row (N1..N6) to filter its active & closed positions below',
                    '点击任意账户行 (N1..N6) 可单独筛选该账户的持仓与历史交易',
                    '계좌 행(N1..N6)을 클릭하면 해당 계좌의 포지션만 필터링됩니다'
                  )}
                </span>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono text-left border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                    <th className="py-2 px-2.5">{tr('Mã TK / Nhánh Chiến Thuật (N1–N6)', 'Account Code / Branch (N1–N6)', '账户代码 / 分支 (N1–N6)', '계좌 코드 / 브랜치 (N1–N6)')}</th>
                    <th className="py-2 px-2.5">{tr('Kịch Bản Phí', 'Cost Scenario', '成本场景', '비용 시나리오')}</th>
                    <th className="py-2 px-2.5 text-right">{tr('Tài Sản ($10k) / NAV', 'Equity ($10k) / NAV', '权益 ($10k) / NAV', '자산 ($10k) / NAV')}</th>
                    <th className="py-2 px-2.5 text-right">Net Return</th>
                    <th className="py-2 px-2.5 text-right">MaxDD</th>
                    <th className="py-2 px-2.5 text-right">{tr('Đang Mở', 'Open', '当前持仓', '보유 중')}</th>
                    <th className="py-2 px-2.5 text-right">{tr('Đã Khớp / Bị Lọc', 'Accepted / Filtered', '已成交 / 已拦截', '체결 / 차단')}</th>
                    <th className="py-2 px-2.5 text-right">{tr('Đã Đóng', 'Closed', '已平仓', '종료')}</th>
                    <th className="py-2 px-2.5 text-right">{tr('Phí + Trượt + Funding', 'Fees + Slip + Funding', '手续费 + 滑点 + 资金费', '수수료 + 슬리피지 + 펀딩')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {(paperOos?.accounts || []).map((acc) => {
                    const pm = POLICY_META[acc.policy_id] || {
                      code: '—',
                      label: acc.policy_id,
                      badgeCls: 'bg-slate-900 text-slate-300 border-slate-700',
                    };
                    const shortAccCode = `${pm.code}-${acc.scenario_id === 'standard_vip6' ? 'VIP6' : 'Stress'}`;
                    const isSelectedAcc = oosAccountFilter === acc.account_id;
                    const filteredCount =
                      Object.values(acc.filtered || {}).reduce((s: number, v: unknown) => s + Number(v || 0), 0) +
                      Object.values(acc.rejected || {}).reduce((s: number, v: unknown) => s + Number(v || 0), 0);
                    return (
                      <tr
                        key={acc.account_id}
                        onClick={() => setOosAccountFilter(isSelectedAcc ? 'ALL' : acc.account_id)}
                        className={`cursor-pointer transition ${
                          isSelectedAcc ? 'bg-cyan-950/40 ring-1 ring-inset ring-cyan-500/40' : 'hover:bg-slate-950/60'
                        }`}
                      >
                        <td className="py-2 px-2.5">
                          <span className="mr-1.5 px-1.5 py-0.5 text-[10px] font-black rounded bg-slate-950 text-white border border-slate-700">
                            {shortAccCode}
                          </span>
                          <span className={`px-2 py-0.5 text-[10px] font-bold rounded border ${pm.badgeCls}`}>
                            {pm.label}
                          </span>
                          {acc.open_positions && acc.open_positions.length > 0 && (
                            <span className="ml-1.5 text-[10px] text-amber-300 font-bold">
                              ({acc.open_positions.map((p) => `${p.symbol} ${String(p.tf || '').toUpperCase()}`).join(', ')})
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-2.5">
                          <span
                            className={`px-2 py-0.5 text-[10px] rounded ${
                              acc.scenario_id === 'standard_vip6'
                                ? 'bg-emerald-950 text-emerald-300 border border-emerald-700/50'
                                : 'bg-rose-950 text-rose-300 border border-rose-700/50'
                            }`}
                          >
                            {acc.scenario_id === 'standard_vip6' ? 'VIP6 (2.5+10bps)' : 'Stress (5+50bps)'}
                          </span>
                        </td>
                        <td className="py-2 px-2.5 text-right font-black text-slate-100">
                          <div>${(acc.equity * 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                          <div className="text-[10px] font-normal text-slate-400">NAV {acc.equity.toFixed(2)}</div>
                        </td>
                        <td
                          className={`py-2 px-2.5 text-right font-bold ${
                            acc.net_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'
                          }`}
                        >
                          {acc.net_return_pct >= 0 ? `+${acc.net_return_pct.toFixed(3)}%` : `${acc.net_return_pct.toFixed(3)}%`}
                        </td>
                        <td className="py-2 px-2.5 text-right text-rose-300">{acc.max_dd_pct.toFixed(3)}%</td>
                        <td className="py-2 px-2.5 text-right">
                          <span className={acc.open_positions_count > 0 ? 'px-1.5 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-500/40 font-bold' : 'text-slate-500'}>
                            {acc.open_positions_count} lệnh
                          </span>
                        </td>
                        <td className="py-2 px-2.5 text-right text-[11px]">
                          <span className="text-emerald-300">{acc.accepted_trades_count ?? acc.open_positions_count} khớp</span>
                          <span className="text-slate-500"> / </span>
                          <span className="text-slate-400">{filteredCount} lọc</span>
                        </td>
                        <td className="py-2 px-2.5 text-right text-slate-200">{acc.closed_trades_count}</td>
                        <td className="py-2 px-2.5 text-right text-slate-400">
                          {(acc.fees_pct + acc.slippage_pct - acc.funding_pct).toFixed(3)}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Detailed Live Open Positions per Account in Paper OOS v1 */}
            <div className="mt-5 pt-4 border-t border-slate-800/80">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                <div className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                  <Sparkles className="w-4 h-4" />
                  Sổ Lệnh Chi Tiết Đang Vào Cho Từng Tài Khoản ({(paperOos?.open_positions || []).length} vị thế đang mở trên 12 tài khoản)
                </div>
                <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-mono">
                  <button
                    type="button"
                    onClick={() => setOosAccountFilter('ALL')}
                    className={`px-2.5 py-1 rounded border transition ${
                      oosAccountFilter === 'ALL'
                        ? 'bg-cyan-950/80 text-cyan-300 border-cyan-500/50 font-bold'
                        : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-200'
                    }`}
                  >
                    Tất cả 12 TK ({(paperOos?.open_positions || []).length})
                  </button>
                  <button
                    type="button"
                    onClick={() => setOosAccountFilter('standard_vip6')}
                    className={`px-2.5 py-1 rounded border transition ${
                      oosAccountFilter === 'standard_vip6'
                        ? 'bg-emerald-950/80 text-emerald-300 border-emerald-500/50 font-bold'
                        : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-200'
                    }`}
                  >
                    Chuẩn VIP6 ({(paperOos?.open_positions || []).filter((p) => p.scenario_id === 'standard_vip6').length})
                  </button>
                  <button
                    type="button"
                    onClick={() => setOosAccountFilter('stress_regular')}
                    className={`px-2.5 py-1 rounded border transition ${
                      oosAccountFilter === 'stress_regular'
                        ? 'bg-rose-950/80 text-rose-300 border-rose-500/50 font-bold'
                        : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-200'
                    }`}
                  >
                    Stress Phí Cao ({(paperOos?.open_positions || []).filter((p) => p.scenario_id === 'stress_regular').length})
                  </button>
                  {oosAccountFilter !== 'ALL' && oosAccountFilter !== 'standard_vip6' && oosAccountFilter !== 'stress_regular' && (
                    <span className="px-2.5 py-1 rounded bg-amber-950/80 text-amber-300 border border-amber-500/50 font-bold">
                      Đang lọc: {oosAccountFilter}
                    </span>
                  )}
                </div>
              </div>

              {(() => {
                const allOpen = paperOos?.open_positions || [];
                const filteredPositions = allOpen.filter((pos) => {
                  if (oosAccountFilter === 'ALL') return true;
                  if (oosAccountFilter === 'standard_vip6' || oosAccountFilter === 'stress_regular') {
                    return pos.scenario_id === oosAccountFilter;
                  }
                  return pos.account_id === oosAccountFilter;
                });

                if (filteredPositions.length === 0) {
                  return (
                    <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-4 text-xs font-mono text-slate-400">
                      Tài khoản đang chọn hiện không có vị thế mở (ví dụ: <strong>Elite Sniper ≥ 75đ</strong> đã chặn tín hiệu chưa đủ chuẩn hội tụ). Bấm <strong>"Tất cả 12 TK"</strong> để xem toàn bộ vị thế đang mở.
                    </div>
                  );
                }

                return (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs font-mono text-left border-collapse">
                      <thead>
                        <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                          <th className="py-2 px-2">Tài Khoản (Chính Sách · Kịch Bản)</th>
                          <th className="py-2 px-2">Coin / Khung</th>
                          <th className="py-2 px-2">Thời Điểm Vào / Hết Hạn (UTC)</th>
                          <th className="py-2 px-2 text-right">Entry (Giá Khớp) → Mark</th>
                          <th className="py-2 px-2 text-right">SL Hiệu Lực (Mốc 6)</th>
                          <th className="py-2 px-2 text-right">Mốc Chốt Lời (TP1 / TP2 / TP3)</th>
                          <th className="py-2 px-2 text-right">Quy Mô Vốn (% NAV)</th>
                          <th className="py-2 px-2 text-right">Rủi Ro Tối Đa SL</th>
                          <th className="py-2 px-2 text-right">Chi Phí Khớp / Funding</th>
                          <th className="py-2 px-2 text-right">PnL Ròng (% NAV)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60">
                        {filteredPositions.map((pos: Record<string, any>) => {
                          const pm = POLICY_META[pos.policy_id] || { label: pos.policy_id, badgeCls: 'bg-slate-900 text-slate-300 border-slate-700' };
                          return (
                            <tr key={`${pos.account_id}-${pos.id}`} className="hover:bg-slate-950/60">
                              <td className="py-2.5 px-2">
                                <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded border ${pm.badgeCls}`}>
                                  {pm.label}
                                </span>
                                <span
                                  className={`ml-1.5 px-1.5 py-0.5 text-[10px] rounded ${
                                    pos.scenario_id === 'standard_vip6'
                                      ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-700/40'
                                      : 'bg-rose-950/80 text-rose-300 border border-rose-700/40'
                                  }`}
                                >
                                  {pos.scenario_id === 'standard_vip6' ? 'VIP6' : 'Stress'}
                                </span>
                              </td>
                              <td className="py-2.5 px-2">
                                <button
                                  type="button"
                                  onClick={() => onSelectCoin?.(pos.symbol)}
                                  className="font-black text-amber-300 hover:underline cursor-pointer"
                                >
                                  {pos.symbol}
                                </button>
                                <span className="ml-1 px-1 py-0.5 text-[10px] rounded bg-slate-800 text-slate-300">
                                  {String(pos.tf || '').toUpperCase()}
                                </span>
                                <div className="text-[10px] text-slate-500 mt-0.5">Qty: {Number(pos.qty || 0).toFixed(1)}</div>
                              </td>
                              <td className="py-2.5 px-2 text-[11px]">
                                <div className="text-slate-200">Vào: {formatUtcShort(pos.entry_utc)}</div>
                                <div className="text-[10px] text-slate-400">Hạn: {formatUtcShort(pos.deadline_utc)}</div>
                              </td>
                              <td className="py-2.5 px-2 text-right">
                                <div>
                                  ${formatPrice(pos.entry_price)} <span className="text-slate-500">(${formatPrice(pos.execution_price)})</span> →{' '}
                                  <span className="font-bold text-white">${formatPrice(pos.mark_price)}</span>
                                </div>
                                <div className={`text-[10px] ${pos.price_move_pct <= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                  Biến động giá: {pos.price_move_pct > 0 ? `+${pos.price_move_pct.toFixed(2)}%` : `${pos.price_move_pct.toFixed(2)}%`} (Lãi gộp coin: {pos.gross_trade_return_pct >= 0 ? `+${pos.gross_trade_return_pct.toFixed(2)}%` : `${pos.gross_trade_return_pct.toFixed(2)}%`})
                                </div>
                              </td>
                              <td className="py-2.5 px-2 text-right">
                                <div className="text-rose-300 font-bold">${formatPrice(pos.active_stop)}</div>
                                <div className="text-[10px] text-slate-400">
                                  +{Number(pos.sl_distance_pct || 0).toFixed(2)}% ({pos.sl_ratchet_state === 'INITIAL_SL' ? 'SL 0.886 gốc' : pos.sl_ratchet_state})
                                </div>
                              </td>
                              <td className="py-2.5 px-2 text-right text-[11px]">
                                <div className={pos.tp1_hit ? 'text-emerald-400 font-bold' : 'text-slate-200'}>
                                  TP1 (40%): ${formatPrice(pos.tp1)} {pos.tp1_hit ? '✓' : ''}
                                </div>
                                <div className="text-[10px] text-slate-400">
                                  TP2 (30%): ${formatPrice(pos.tp2)} · TP3 (30%): ${formatPrice(pos.tp3)}
                                </div>
                              </td>
                              <td className="py-2.5 px-2 text-right">
                                <div className="font-bold text-cyan-300">{Number(pos.reference_notional_pct || 0).toFixed(2)}% NAV</div>
                                <div className="text-[10px] text-slate-400">Khối lượng còn: {Number(pos.remaining_pct ?? 100).toFixed(0)}%</div>
                              </td>
                              <td className="py-2.5 px-2 text-right">
                                <span className={Number(pos.stop_risk_pct || 0) > 1.0 ? 'text-rose-400 font-bold' : 'text-emerald-300 font-bold'}>
                                  -{Number(pos.stop_risk_pct || 0).toFixed(2)}% NAV
                                </span>
                              </td>
                              <td className="py-2.5 px-2 text-right text-[10px] text-slate-400">
                                <div>Phí+Trượt: -{(Number(pos.fees_pct || 0) + Number(pos.slippage_pct || 0)).toFixed(3)}%</div>
                                <div>Funding ({pos.funding_events_count || 0} kỳ): {Number(pos.funding_pct || 0) >= 0 ? `+${Number(pos.funding_pct || 0).toFixed(4)}%` : `${Number(pos.funding_pct || 0).toFixed(4)}%`}</div>
                              </td>
                              <td
                                className={`py-2.5 px-2 text-right font-black ${
                                  Number(pos.nav_pnl_pct || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                                }`}
                              >
                                {Number(pos.nav_pnl_pct || 0) >= 0
                                  ? `+${Number(pos.nav_pnl_pct || 0).toFixed(3)}%`
                                  : `${Number(pos.nav_pnl_pct || 0).toFixed(3)}%`}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                );
              })()}
            </div>

            {/* Closed Trades History in Paper OOS v1 */}
            {(paperOos?.closed_trades || []).length > 0 && (
              <div className="mt-5 pt-4 border-t border-slate-800/80">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                  <div className="text-xs font-bold text-emerald-300 flex items-center gap-1.5">
                    <CheckCircle2 className="w-4 h-4" />
                    Lịch Sử Lệnh Đã Đóng Trong Paper OOS v1 (
                    {
                      (paperOos?.closed_trades || []).filter((tr: Record<string, unknown>) => {
                        if (oosAccountFilter === 'ALL') return true;
                        if (oosAccountFilter === 'standard_vip6' || oosAccountFilter === 'stress_regular') {
                          return tr.scenario_id === oosAccountFilter;
                        }
                        return tr.account_id === oosAccountFilter;
                      }).length
                    }{' '}
                    lệnh hoàn tất)
                  </div>
                  <span className="text-[11px] font-mono text-slate-400">
                    Đối soát đầy đủ phí khớp lệnh, độ trượt giá và Funding thực tế trên Binance USD-M
                  </span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs font-mono text-left border-collapse">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                        <th className="py-2 px-2">Tài Khoản (Chính Sách · Kịch Bản)</th>
                        <th className="py-2 px-2">Coin / Khung</th>
                        <th className="py-2 px-2">Thời Gian Vào → Đóng (UTC)</th>
                        <th className="py-2 px-2 text-right">Giá Vào → Giá Đóng</th>
                        <th className="py-2 px-2">Lý Do Thoát Lệnh</th>
                        <th className="py-2 px-2 text-right">Phí + Trượt + Funding</th>
                        <th className="py-2 px-2 text-right">PnL Ròng (% NAV)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {(paperOos?.closed_trades || [])
                        .filter((tr: Record<string, unknown>) => {
                          if (oosAccountFilter === 'ALL') return true;
                          if (oosAccountFilter === 'standard_vip6' || oosAccountFilter === 'stress_regular') {
                            return tr.scenario_id === oosAccountFilter;
                          }
                          return tr.account_id === oosAccountFilter;
                        })
                        .slice(0, 30)
                        .map((tr: Record<string, unknown>, idx: number) => {
                          const policyIdStr = String(tr.policy_id || '');
                          const pm = POLICY_META[policyIdStr] || {
                            label: policyIdStr,
                            badgeCls: 'bg-slate-900 text-slate-300 border-slate-700',
                          };
                          const pnl = Number(tr.nav_pnl_pct || 0);
                          return (
                            <tr key={`${tr.account_id}-${tr.id || idx}`} className="hover:bg-slate-950/60">
                              <td className="py-2 px-2">
                                <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded border ${pm.badgeCls}`}>
                                  {pm.label}
                                </span>
                                <span
                                  className={`ml-1.5 px-1.5 py-0.5 text-[10px] rounded ${
                                    tr.scenario_id === 'standard_vip6'
                                      ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-700/40'
                                      : 'bg-rose-950/80 text-rose-300 border border-rose-700/40'
                                  }`}
                                >
                                  {tr.scenario_id === 'standard_vip6' ? 'VIP6' : 'Stress'}
                                </span>
                              </td>
                              <td className="py-2 px-2">
                                <button
                                  type="button"
                                  onClick={() => onSelectCoin?.(String(tr.symbol || ''))}
                                  className="font-black text-amber-300 hover:underline cursor-pointer"
                                >
                                  {String(tr.symbol || '')}
                                </button>
                                <span className="ml-1 px-1 py-0.5 text-[10px] rounded bg-slate-800 text-slate-300">
                                  {String(tr.tf || '').toUpperCase()}
                                </span>
                              </td>
                              <td className="py-2 px-2 text-[11px] text-slate-300">
                                {formatUtcShort(String(tr.entry_utc || ''))} → {formatUtcShort(String(tr.exit_utc || ''))}
                              </td>
                              <td className="py-2 px-2 text-right text-slate-200">
                                ${formatPrice(Number(tr.entry_price || 0))} → <span className="font-bold text-white">${formatPrice(Number(tr.exit_mark_price || 0))}</span>
                              </td>
                              <td className="py-2 px-2">
                                <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-cyan-300 border border-slate-700">
                                  {String(tr.exit_reason || 'CLOSED')}
                                </span>
                              </td>
                              <td className="py-2 px-2 text-right text-[10px] text-slate-400">
                                -{(Number(tr.fees_pct || 0) + Number(tr.slippage_pct || 0) - Number(tr.funding_pct || 0)).toFixed(3)}%
                              </td>
                              <td
                                className={`py-2 px-2 text-right font-black ${
                                  pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
                                }`}
                              >
                                {pnl >= 0 ? `+${pnl.toFixed(3)}%` : `${pnl.toFixed(3)}%`}
                              </td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>

          {/* Active PIT Top-50 Universe Table */}
          {paperOos?.pit_top50_membership?.members && paperOos.pit_top50_membership.members.length > 0 && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-cyan-300 flex items-center gap-1.5">
                  <Database className="w-4 h-4" />
                  Vũ Trụ 50 Coin Rolling Point-in-Time ({paperOos.pit_top50_membership.month} · Lọc Trước Đầu Tháng)
                </h3>
                <span className="text-[11px] font-mono text-slate-400">
                  Điều kiện: Median 24h Quote Volume Top 50 · H4 Upper Wick p90 ≤ 3.2% · Active ≥ 50/63 ngày
                </span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-5 lg:grid-cols-10 gap-2 max-h-[320px] overflow-y-auto pr-1">
                {paperOos.pit_top50_membership.members.map((m) => (
                  <div
                    key={m.symbol}
                    onClick={() => onSelectCoin?.(m.symbol)}
                    className="bg-slate-950/80 border border-slate-800 hover:border-cyan-500/50 rounded-lg p-2 cursor-pointer transition font-mono"
                  >
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="text-cyan-400 font-bold">#{m.rank}</span>
                      <span className="text-slate-400">Wick {m.wick_p90_pct.toFixed(1)}%</span>
                    </div>
                    <div className="text-xs font-black text-slate-100 mt-0.5 truncate">{m.symbol}</div>
                    <div className="text-[10px] text-emerald-400">{formatUsdCompact(m.median_quote_volume)}/d</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
