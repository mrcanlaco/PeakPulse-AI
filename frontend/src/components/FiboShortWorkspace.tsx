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
import type { TradeSetup } from '../types';

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

interface FiboShortWorkspaceProps {
  onSelectCoin?: (symbol: string) => void;
}

const POLICY_META: Record<string, { label: string; badgeCls: string; desc: string }> = {
  sniper_rr1_horizon24: {
    label: 'SNIPER RR≥1 · 24H',
    badgeCls: 'bg-emerald-950/90 text-emerald-300 border-emerald-500/60',
    desc: 'Chuẩn Sniper + R:R(TP1) ≥ 1.0 + Đóng vị thế tối đa 24h (Return/MaxDD 5.74x)',
  },
  elite_sniper_risk: {
    label: 'ELITE SNIPER · RISK',
    badgeCls: 'bg-cyan-950/90 text-cyan-300 border-cyan-500/60',
    desc: 'Chuẩn Carver PST Nghiêm Ngặt + H1 Phá Đáy + Đi vốn Risk 0.5% NAV (Return/MaxDD 4.98x)',
  },
  sniper_risk: {
    label: 'SNIPER · RISK 0.5%',
    badgeCls: 'bg-amber-950/90 text-amber-300 border-amber-500/60',
    desc: 'Chuẩn M6 Sniper + Đi vốn theo rủi ro 0.5% NAV (2020–2025: +159.35%, MaxDD 16.57%)',
  },
  sniper_horizon24: {
    label: 'SNIPER · 24H',
    badgeCls: 'bg-indigo-950/90 text-indigo-300 border-indigo-500/50',
    desc: 'Chuẩn M6 Sniper + Time-exit 24h (2024–2025: +61.36%, MaxDD 12.16%)',
  },
  m6_risk: {
    label: 'M6 EXPANDED · RISK',
    badgeCls: 'bg-purple-950/90 text-purple-300 border-purple-500/50',
    desc: 'Mốc 6 SL Fibo 0.886 + Đi vốn theo rủi ro 0.5% NAV (2020–2025: +185.49%)',
  },
  reference_m6_fixed: {
    label: 'M6 FIXED 20% (REF)',
    badgeCls: 'bg-slate-900 text-slate-300 border-slate-700',
    desc: 'Mốc 6 tham chiếu đi vốn cố định 20% NAV',
  },
  m4_f2_elite: {
    label: 'M4 ELITE WAVE',
    badgeCls: 'bg-slate-900 text-slate-400 border-slate-700',
    desc: 'Đạt chuẩn sóng F1B + F2 nhưng chờ H1 phá đáy cấu trúc',
  },
  watch_only: {
    label: 'THEO DÕI SÓNG M1',
    badgeCls: 'bg-slate-950 text-slate-400 border-slate-800',
    desc: 'Mới đạt điều kiện sóng M1 cơ bản, đang quan sát thêm',
  },
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
  const priorPumpPct = rawPump < 10 ? rawPump * 100 : rawPump;
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

  const pumpPass50 = priorPumpPct >= 50.0;
  const f1ElitePass = pstPass && waveKer >= 0.35;
  const f1ExpandedPass = f1ElitePass || waveKer >= 0.65;
  const f2ImpulsePass = impDropPct >= 6.0 && impKer >= 0.50;
  const h1BreakPass = confirmed && cond2Break && maxFibo <= 0.786 && slCapPass;

  const isActionable =
    item.stage === 'FIRED_CONFIRMED_SHORT' &&
    matched.some((p) =>
      ['sniper_rr1_horizon24', 'elite_sniper_risk', 'sniper_risk', 'sniper_horizon24', 'm6_risk'].includes(p)
    );
  const isSniperActionable =
    item.stage === 'FIRED_CONFIRMED_SHORT' &&
    matched.some((p) => ['sniper_rr1_horizon24', 'elite_sniper_risk', 'sniper_risk', 'sniper_horizon24'].includes(p));
  const isPaperEligible =
    isActionable && pumpPass50 && item.alpha_layers?.universe_tier === 'PIT_TOP50';

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
    failReasonsVi.push(`Sóng tăng trước đó nhỏ (+${priorPumpPct.toFixed(1)}% < 50% chuẩn Paper OOS)`);
  }

  const gates = [
    {
      step: 1,
      shortLabel: `1. Bơm +${priorPumpPct.toFixed(0)}%`,
      title: 'Cổng 1 · Sóng Bơm Trước Đó (F1A ≥ +50%)',
      detail: `Tăng +${priorPumpPct.toFixed(1)}% trước đỉnh (${pumpPass50 ? 'Đạt chuẩn ≥ 50% của Paper OOS' : 'Dưới ngưỡng +50% của Paper OOS'})`,
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

export const FiboShortWorkspace: React.FC<FiboShortWorkspaceProps> = ({ onSelectCoin }) => {
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
    if (typeof window !== 'undefined') {
      const h = window.location.hash.toLowerCase();
      if (h.includes('shadow')) return 'SHADOW_COMPARE';
      if (h.includes('paper-oos')) return 'PAPER_OOS';
    }
    return 'LIVE';
  });

  useEffect(() => {
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
  }, []);
  const [auditWindow, setAuditWindow] = useState<'2024_2025' | '2020_2025'>('2024_2025');
  const [auditScenario, setAuditScenario] = useState<'standard_vip6' | 'stress_regular'>('standard_vip6');
  const [oosAccountFilter, setOosAccountFilter] = useState<string>('ALL');
  const [chartInterval, setChartInterval] = useState<'1h' | '4h' | '1d'>('1h');
  const [chartKlines, setChartKlines] = useState<any[]>([]);

  const fetchSnapshotAndBacktest = async () => {
    try {
      const [snapRes, btRes, paperRes, candRes] = await Promise.all([
        fetch('/api/fibo-short/snapshot'),
        fetch('/api/fibo-short/backtest'),
        fetch('/api/fibo-short/paper-oos'),
        fetch('/api/candidates/compare'),
      ]);
      if (snapRes.ok) {
        const snapData: FiboSnapshotResponse = await snapRes.json();
        setSnapshot(snapData);
        if (!selectedId && snapData.items && snapData.items.length > 0) {
          setSelectedId(snapData.items[0].id);
        }
      }
      if (btRes.ok) {
        const btData: FiboBacktestResponse = await btRes.json();
        setBacktest(btData);
      }
      if (paperRes.ok) {
        const paperData: PaperOosResponse = await paperRes.json();
        setPaperOos(paperData);
      }
      if (candRes.ok) {
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
    fetchSnapshotAndBacktest();
    const timer = setInterval(fetchSnapshotAndBacktest, 30000);
    return () => clearInterval(timer);
  }, []);

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
  }, [backtest, auditWindow, auditScenario]);

  return (
    <div className="flex-1 min-h-0 overflow-y-auto pr-1 pb-8 space-y-4">
      {/* Top Banner: Branch Overview & 3-Tab Switcher */}
      <div className="bg-gradient-to-r from-slate-900 via-indigo-950/70 to-slate-900 border border-amber-500/30 rounded-xl p-4 shadow-lg">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wider rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center gap-1">
                <Sparkles className="w-3 h-3" /> Chuẩn v4.0.21 · 4-Factor Orthogonal Alpha
              </span>
              <span className="px-2.5 py-0.5 text-[11px] font-semibold rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 flex items-center gap-1">
                <Lock className="w-3 h-3" /> Backtest Locked ≤ 2025 • Paper OOS v1 (2026+)
              </span>
              {snapshot?.pit_universe?.month && (
                <span className="px-2.5 py-0.5 text-[11px] font-mono font-semibold rounded-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
                  PIT Top-50 ({snapshot.pit_universe.month}): {snapshot.pit_universe.member_count} coin · Wick p90 ≤ 3.2%
                </span>
              )}
            </div>
            <h2 className="text-base sm:text-lg font-extrabold text-slate-100 mt-1.5 flex items-center gap-2">
              <TrendingDown className="w-5 h-5 text-amber-400 shrink-0" />
              Đảo Chiều Xác Nhận & Short Theo Xu Hướng Mới (Fibonacci H4/D1 → H1)
            </h2>
            <p className="text-xs text-slate-300 mt-0.5">
              Hội tụ 4 tầng độc lập: <b>F1A Sóng bơm ≥50%</b> + <b>F1B Carver EWMAC/Accel & Wave KER</b> + <b>F2 Impulse KER ≥0.50</b> + <b>F3/F4 H1 Phá Đáy & SL Mốc 6 Fibo 0.886 (Đi vốn rủi ro 0.5% NAV)</b>.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
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
                Radar Trực Tiếp
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
                Đối Chiếu Shadow (Cũ vs v4.0.21)
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
                Paper OOS v1 (24/7)
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
                Kiểm Định v4.0.21 (≤ 2025)
              </button>
            </div>

            <button
              type="button"
              onClick={triggerManualScan}
              disabled={scanning}
              className="px-3 py-2 rounded-lg text-xs font-bold bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white flex items-center gap-1.5 shadow transition cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${scanning ? 'animate-spin' : ''}`} />
              {scanning ? 'Đang quét...' : 'Quét Fibo Ngay'}
            </button>
          </div>
        </div>

        {/* Summary Counters */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5 mt-3.5 pt-3 border-t border-slate-800/80">
          <div className="bg-slate-950/80 border border-slate-800 rounded-lg p-2.5">
            <div className="text-[11px] text-slate-400">Vũ Trụ Quét Chọn Lọc</div>
            <div className="text-xl font-black font-mono text-slate-100 mt-0.5">
              {snapshot?.scanned_symbols_count ?? 0}
              <span className="text-xs font-normal text-slate-400 ml-1.5">cặp (Blacklist ON)</span>
            </div>
          </div>
          <div className="bg-slate-950/80 border border-emerald-500/30 rounded-lg p-2.5">
            <div className="text-[11px] text-emerald-300 font-semibold flex items-center gap-1">
              <Target className="w-3.5 h-3.5" /> ĐỦ CHUẨN VÀO SHORT (v4.0.21)
            </div>
            <div className="text-xl font-black font-mono text-emerald-400 mt-0.5">
              {actionableCount}
              <span className="text-xs font-normal text-slate-400 ml-1.5">
                (H1 đỏ bị lọc: {filteredOutFiredCount} · Chờ Fibo: {snapshot?.armed_count ?? 0})
              </span>
            </div>
          </div>
          <div className="bg-slate-950/80 border border-amber-500/30 rounded-lg p-2.5">
            <div className="text-[11px] text-amber-300 font-semibold flex items-center gap-1">
              <ShieldAlert className="w-3.5 h-3.5" /> ĐẠT CHUẨN SNIPER / ELITE
            </div>
            <div className="text-xl font-black font-mono text-amber-300 mt-0.5">
              {snapshot?.policy_counts?.sniper_risk ?? 0}
              <span className="text-xs font-normal text-cyan-300 ml-1.5">
                (Elite: {snapshot?.policy_counts?.elite_sniper_risk ?? 0})
              </span>
            </div>
          </div>
          <div className="bg-slate-950/80 border border-emerald-500/30 rounded-lg p-2.5">
            <div className="text-[11px] text-emerald-300 font-semibold flex items-center gap-1">
              <Gauge className="w-3.5 h-3.5" /> SNIPER RR≥1 · 24H
            </div>
            <div className="text-xl font-black font-mono text-emerald-300 mt-0.5">
              {snapshot?.policy_counts?.sniper_rr1_horizon24 ?? 0}
              <span className="text-xs font-normal text-slate-400 ml-1.5">
                (M6: {snapshot?.policy_counts?.m6_risk ?? 0})
              </span>
            </div>
          </div>
          <div className="bg-slate-950/80 border border-cyan-500/30 rounded-lg p-2.5">
            <div className="text-[11px] text-cyan-300 font-semibold flex items-center gap-1">
              <Award className="w-3.5 h-3.5" /> HIỆU SUẤT v4.0.21 (24–25)
            </div>
            <div className="text-xl font-black font-mono text-emerald-300 mt-0.5">
              +61.2%
              <span className="text-xs font-normal text-cyan-300 ml-1.5">
                (MaxDD 10.7% · 5.74x)
              </span>
            </div>
          </div>
        </div>
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
                      { id: 'ALL', label: 'Tất cả' },
                      { id: 'ACTIONABLE_ONLY', label: `✅ Đủ chuẩn vào lệnh (${actionableCount})` },
                      { id: 'FIRED_CONFIRMED_SHORT', label: `H1 Đỏ (${snapshot?.fired_count ?? 0})` },
                      { id: 'ARMED_IN_FIBO_ZONE', label: `Vùng Fibo (${snapshot?.armed_count ?? 0})` },
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
                <span className="text-[10px] font-bold uppercase text-slate-400 mr-1">Chính sách:</span>
                {(
                  [
                    { id: 'ALL', label: 'Tất cả' },
                    { id: 'sniper_rr1_horizon24', label: 'Sniper RR≥1 (24h)' },
                    { id: 'elite_sniper_risk', label: 'Elite Sniper' },
                    { id: 'sniper_risk', label: 'Sniper Risk' },
                    { id: 'm6_risk', label: 'M6 Expanded' },
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
                          {gateEval.isActionable ? polMeta.label : '⛔ CHỈ QUAN SÁT (CHƯA ĐẠT M6)'}
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
                        onClick={() => onSelectCoin?.(selectedSignal.symbol)}
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
                              Đã vượt qua bộ lọc sóng Mốc 6 / Sniper. {selEval.pumpPass50 ? 'Đạt chuẩn sóng bơm ≥ 50% của Paper OOS.' : 'Lưu ý: Sóng bơm trước đó < 50% nên chỉ thuộc tín hiệu mở rộng trên Live Scanner.'}
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
                  <div className="text-[10px] text-slate-400">Chênh Lệch NAV (M6 vs Cũ)</div>
                  {(() => {
                    const m6Track = snapshot?.shadow_comparison?.tracks?.find((t) => t.track_id === 'm6_risk');
                    const delta = m6Track?.delta_nav_vs_legacy_pct ?? 0;
                    return (
                      <div className={`text-sm font-black mt-0.5 ${delta >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {delta >= 0 ? `+${delta.toFixed(3)}%` : `${delta.toFixed(3)}%`} NAV
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
                    return (
                      <tr key={tr.track_id} className={isLegacy ? 'bg-rose-950/15 hover:bg-rose-950/25' : 'hover:bg-slate-950/60'}>
                        <td className="py-2.5 px-2.5 font-sans">
                          <div className={`font-bold ${isLegacy ? 'text-rose-300' : 'text-emerald-300'}`}>
                            {tr.label_vi}
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
                        <td className="py-2.5 px-2.5 text-right font-black">
                          {isLegacy ? (
                            <span className="text-slate-500">Mốc gốc (0.000%)</span>
                          ) : (
                            <span className={tr.delta_nav_vs_legacy_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                              {tr.delta_nav_vs_legacy_pct >= 0
                                ? `+${tr.delta_nav_vs_legacy_pct.toFixed(3)}%`
                                : `${tr.delta_nav_vs_legacy_pct.toFixed(3)}%`}
                            </span>
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
                3. Đối Chiếu Daemon Paper OOS v1 (24/7): Baseline Đi Vốn Cố Định 20% (`reference_m6_fixed`) vs. 5 Chính Sách `v4.0.21`
              </h3>
              <span className="text-[11px] font-mono text-slate-400">
                Trạng thái Daemon: {paperOos?.health?.code || 'OBSERVING'} · Vũ trụ PIT {paperOos?.study?.membership_month || '2026-10'} ({paperOos?.study?.membership_count ?? 50} coin)
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono text-left border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                    <th className="py-2 px-2.5">Chính Sách (Policy)</th>
                    <th className="py-2 px-2.5">Cơ Chế Quản Trị Vốn & Thoát Lệnh</th>
                    <th className="py-2 px-2.5 text-right">NAV (VIP6)</th>
                    <th className="py-2 px-2.5 text-right">Net Return (VIP6)</th>
                    <th className="py-2 px-2.5 text-right">NAV (Stress)</th>
                    <th className="py-2 px-2.5 text-right">Mở / Đóng</th>
                    <th className="py-2 px-2.5 text-right">Chuẩn Lịch Sử 2024–2025 (VIP6)</th>
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
                12 Tài Khoản Paper OOS Độc Lập (6 Chính Sách × 2 Kịch Bản Phí · NAV Khởi Điểm = 100.00)
              </h3>
              <span className="text-[11px] font-mono text-slate-400">
                Bấm vào từng dòng tài khoản để lọc riêng lệnh đang vào của tài khoản đó
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono text-left border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                    <th className="py-2 px-2.5">Tài Khoản / Chính Sách</th>
                    <th className="py-2 px-2.5">Kịch Bản Phí</th>
                    <th className="py-2 px-2.5 text-right">NAV Hiện Tại</th>
                    <th className="py-2 px-2.5 text-right">Net Return</th>
                    <th className="py-2 px-2.5 text-right">MaxDD</th>
                    <th className="py-2 px-2.5 text-right">Đang Mở</th>
                    <th className="py-2 px-2.5 text-right">Đã Khớp / Bị Lọc</th>
                    <th className="py-2 px-2.5 text-right">Đã Đóng</th>
                    <th className="py-2 px-2.5 text-right">Phí + Trượt + Funding</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {(paperOos?.accounts || []).map((acc) => {
                    const pm = POLICY_META[acc.policy_id] || { label: acc.policy_id, badgeCls: 'bg-slate-900 text-slate-300 border-slate-700' };
                    const isSelectedAcc = oosAccountFilter === acc.account_id;
                    const filteredCount = Object.values(acc.filtered || {}).reduce((s: number, v: any) => s + Number(v || 0), 0);
                    return (
                      <tr
                        key={acc.account_id}
                        onClick={() => setOosAccountFilter(isSelectedAcc ? 'ALL' : acc.account_id)}
                        className={`cursor-pointer transition ${
                          isSelectedAcc ? 'bg-cyan-950/40 ring-1 ring-inset ring-cyan-500/40' : 'hover:bg-slate-950/60'
                        }`}
                      >
                        <td className="py-2 px-2.5">
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
                        <td className="py-2 px-2.5 text-right font-black text-slate-100">{acc.equity.toFixed(4)}</td>
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
