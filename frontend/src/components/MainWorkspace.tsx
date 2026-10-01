import React, { lazy, Suspense, useState, useEffect, useMemo, useRef } from 'react';
import type { SignalItem, CoinDetail, CandidateCoin, CandidateRefreshStatus, ModelAudit, MarketOverviewData, ScannerTelemetry, DeepAnalysis, CandlePoint, TrackingWatchlistItem, TradeSetup, FilterTag, SignalSort, TelegramFilter } from '../types';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid, AreaChart, Area, ComposedChart
} from 'recharts';
import {
  Activity, BarChart3,
  ArrowUpRight, ArrowDownRight, CheckCircle2, Radio, Terminal, Send, Clock, Play, Loader2, LineChart as LineChartIcon, RefreshCw, HelpCircle, Eye, EyeOff
} from 'lucide-react';
import { WorkspaceTabBar, type WorkspaceTab } from './WorkspaceTabBar';
import { ErrorBoundary } from './ErrorBoundary';

import type { CandlestickSignalMarker } from './CandlestickChart';
import { DecisionHeader } from './DecisionCenter/DecisionHeader';
import { TradeSetupCard } from './DecisionCenter/TradeSetupCard';
import { TradeSetupCardV2 } from './v2/TradeSetupCardV2';
import { AiDecisionCockpit } from './DecisionCenter/AiDecisionCockpit';
import { FeatureDriversAccordion } from './DecisionCenter/FeatureDriversAccordion';
import { AiExecutiveBriefing } from './DecisionCenter/AiExecutiveBriefing';
import { CoinLink } from './CoinLink';
import { formatSystemTime, parseSystemDate } from '../utils/time';
import { getCoinMarketCapInfo, getMarketCapBadgeConfig, getMarketCapSourceLabel } from '../utils/sectors';
import { useTranslation } from '../i18n/LanguageContext';
import {
  getRiskLabel,
  getScanModeLabel,
  getExecutionStatusLabel,
  getScannerStatusLabel,
} from '../i18n/translations';

const ModelAuditPanel = lazy(() =>
  import('./ModelAuditPanel').then(({ ModelAuditPanel: component }) => ({ default: component }))
);
const SignalFeed = lazy(() =>
  import('./SignalFeed').then(({ SignalFeed: component }) => ({ default: component }))
);
const MultiCoinScan = lazy(() =>
  import('./MultiCoinScan').then(({ MultiCoinScan: component }) => ({ default: component }))
);
const BacktestExperiments = lazy(() =>
  import('./BacktestExperiments').then(({ BacktestExperiments: component }) => ({ default: component }))
);
const ForwardTest = lazy(() =>
  import('./ForwardTest').then(({ ForwardTest: component }) => ({ default: component }))
);
const SystemHistoryTab = lazy(() =>
  import('./SystemHistoryTab').then(({ SystemHistoryTab: component }) => ({ default: component }))
);
const VersionHistoryTab = lazy(() =>
  import('./VersionHistoryTab').then(({ VersionHistoryTab: component }) => ({ default: component }))
);
const ModelsDocTab = lazy(() => import('./ModelsDocTab'));
const V3ResearchPanel = lazy(() => import('./V3ResearchPanel').then(m => ({ default: m.V3ResearchPanel })));
const TrackingWatchlist = lazy(() =>
  import('./TrackingWatchlist').then(({ TrackingWatchlist: component }) => ({ default: component }))
);
const SystemSettingsTab = lazy(() =>
  import('./SystemSettingsTab').then(({ SystemSettingsTab: component }) => ({ default: component }))
);
const CandlestickChart = lazy(() =>
  import('./CandlestickChart').then(({ CandlestickChart: component }) => ({ default: component }))
);

interface MainWorkspaceProps {
  signals: SignalItem[];
  selectedSignal: SignalItem | null;
  coinDetail: CoinDetail | null;
  candidates: CandidateCoin[];
  isRefreshingCandidates: boolean;
  candidateRefreshStatus: CandidateRefreshStatus;
  onRefreshCandidates: () => void | Promise<void>;
  auditData: ModelAudit | null;
  marketData: MarketOverviewData | null;
  telemetryData: ScannerTelemetry | null;
  onSelectCandidate: (symbol: string) => void;
  onPushTelegram: (sig: SignalItem) => void;
  onTriggerManualScan: () => void;
  isTriggeringScan: boolean;
  scanTriggeredSuccess: string | null;
  deepAnalysis: DeepAnalysis | null;
  isDeepAnalyzing: boolean;
  onRunDeepAnalysis: (symbol: string) => void;
  onDismissSignal?: (sig: SignalItem) => void;
  onAddWatchlist?: (symbol: string) => void | Promise<boolean>;
  isSymbolInWatchlist?: boolean;
  onAddTracking?: (symbol: string) => void | Promise<boolean>;
  onRemoveTrackingSymbol?: (symbol: string) => void | Promise<boolean>;
  isSymbolTracked?: boolean;
  isWatchlistUpdating?: boolean;
  trackingItems: TrackingWatchlistItem[];
  isTrackingLoading: boolean;
  trackingUpdatingId?: string | null;
  onRefreshTracking: () => void;
  onSelectTrackingCoin: (symbol: string) => void;
  onUpdateTracking: (id: string, patch: Record<string, unknown>) => Promise<boolean>;
  onRemoveTracking: (id: string) => Promise<boolean>;
  activeTab: WorkspaceTab;
  setActiveTab: (tab: WorkspaceTab) => void;
  onOpenOrderModal?: () => void;
  onOpenCoinSelector?: () => void;
  onSelectSignal?: (sig: SignalItem) => void;
  onTrackSignal?: (sig: SignalItem) => void;
  onUntrackSignal?: (sig: SignalItem) => void;
  isSignalTracked?: (sig: SignalItem) => boolean;
  audioAlertEnabled?: boolean;
  activeFilterTag?: FilterTag;
  setActiveFilterTag?: (tag: FilterTag) => void;
  signalSort?: SignalSort;
  setSignalSort?: (sort: SignalSort) => void;
  telegramFilter?: TelegramFilter;
  setTelegramFilter?: (filter: TelegramFilter) => void;
  filteredSignals?: SignalItem[];
  guiVersion?: 'v1' | 'v2';
  onSelectGuiVersion?: (version: 'v1' | 'v2') => void;
  threshold?: number;
  setThreshold?: (val: number) => void;
  activeScanModes?: string[];
  onOpenWatchlistModal?: () => void;
  onOpenTabHelp?: (tab?: WorkspaceTab) => void;
  onLogout?: () => void;
  onOpenAiAssistant?: () => void;
  isDevMode?: boolean;
  setIsDevMode?: (val: boolean) => void;
}

export const MainWorkspace: React.FC<MainWorkspaceProps> = ({
  signals,
  selectedSignal,
  coinDetail,
  candidates,
  isRefreshingCandidates,
  candidateRefreshStatus,
  onRefreshCandidates,
  auditData,
  marketData,
  telemetryData,
  onSelectCandidate,
  onPushTelegram,
  onTriggerManualScan,
  isTriggeringScan,
  scanTriggeredSuccess,
  deepAnalysis,
  isDeepAnalyzing,
  onRunDeepAnalysis,
  onDismissSignal,
  onAddWatchlist,
  isSymbolInWatchlist = false,
  onAddTracking,
  onRemoveTrackingSymbol,
  isSymbolTracked = false,
  isWatchlistUpdating = false,
  trackingItems,
  isTrackingLoading,
  trackingUpdatingId = null,
  onRefreshTracking,
  onSelectTrackingCoin,
  onUpdateTracking,
  onRemoveTracking,
  activeTab,
  setActiveTab,
  onOpenOrderModal,
  onOpenCoinSelector,
  onSelectSignal,
  onTrackSignal,
  onUntrackSignal,
  isSignalTracked,
  audioAlertEnabled = true,
  activeFilterTag = 'ALL',
  setActiveFilterTag,
  signalSort = 'NEWEST',
  setSignalSort,
  telegramFilter = 'ALL',
  setTelegramFilter,
  filteredSignals,
  guiVersion = 'v2',
  onSelectGuiVersion,
  threshold,
  setThreshold,
  activeScanModes,
  onOpenWatchlistModal,
  onOpenTabHelp,
  onLogout,
  onOpenAiAssistant,
  isDevMode = false,
  setIsDevMode,
}) => {

  const { language, t } = useTranslation();  
  const riskLabels: Record<string, string> = {
    CRITICAL: getRiskLabel('CRITICAL', language),
    HIGH: getRiskLabel('HIGH', language),
    MEDIUM: getRiskLabel('MEDIUM', language),
    SAFE: getRiskLabel('SAFE', language),
  };
  const championLabel = 'V1';
  const candidateRefreshMessage: Record<Exclude<CandidateRefreshStatus, 'idle'>, string> = {
    queued: language === 'vi' ? 'Đã gửi yêu cầu quét. Bảng sẽ tự cập nhật khi snapshot mới sẵn sàng.' : language === 'zh' ? '扫描请求已排队，新快照就绪后列表会自动更新。' : language === 'ko' ? '스캔 요청이 대기열에 추가되었습니다. 새 스냅샷이 준비되면 자동으로 갱신됩니다.' : 'Scan requested. The table will update when a fresh snapshot is ready.',
    updated: language === 'vi' ? 'Đã cập nhật bảng ứng viên V1 bằng snapshot mới.' : language === 'zh' ? 'V1 候选榜已更新为最新快照。' : language === 'ko' ? 'V1 후보 목록이 최신 스냅샷으로 갱신되었습니다.' : 'The V1 candidate table is now up to date.',
    timeout: language === 'vi' ? 'Scanner chưa hoàn tất trong thời gian chờ. Bảng vẫn tự đồng bộ mỗi 30 giây.' : language === 'zh' ? '扫描器未在等待时间内完成；列表仍会每 30 秒自动同步。' : language === 'ko' ? '대기 시간 내 스캔이 완료되지 않았습니다. 목록은 30초마다 계속 동기화됩니다.' : 'The scan did not finish within the wait window. The table still syncs every 30 seconds.',
    error: language === 'vi' ? 'Không thể gửi yêu cầu làm mới. Vui lòng kiểm tra trạng thái Scanner.' : language === 'zh' ? '无法提交刷新请求，请检查扫描器状态。' : language === 'ko' ? '새로고침 요청을 보낼 수 없습니다. 스캐너 상태를 확인하세요.' : 'The refresh request failed. Check the scanner status.',
  };
  const [decisionSubTab, setDecisionSubTab] = useState<'TRADE' | 'AI'>('TRADE');
  const [isChartHidden, setIsChartHidden] = useState(false);
  const [localCountdown, setLocalCountdown] = useState<number | null>(telemetryData?.next_scan_in_seconds ?? null);

  useEffect(() => {
    setLocalCountdown(telemetryData?.next_scan_in_seconds ?? null);
  }, [telemetryData?.next_scan_in_seconds]);

  useEffect(() => {
    if (activeTab !== 'TELEMETRY') return;
    const timer = setInterval(() => {
      setLocalCountdown(prev => (prev != null && prev > 0) ? prev - 1 : prev);
    }, 1000);
    return () => clearInterval(timer);
  }, [activeTab]);
  const executionStatusLabels: Record<string, string> = {
    'ALERT FIRED': getExecutionStatusLabel('ALERT FIRED', language),
    COMPLETED: getExecutionStatusLabel('COMPLETED', language),
    RUNNING: getExecutionStatusLabel('RUNNING', language),
    SENT: getExecutionStatusLabel('SENT', language),
    FAILED: getExecutionStatusLabel('FAILED', language),
  };
  const scannerStatusLabels: Record<string, string> = {
    ONLINE: getScannerStatusLabel('ONLINE', language),
    OFFLINE: getScannerStatusLabel('OFFLINE', language),
  };
  const scanModeLabels: Record<string, string> = {
    volatile: getScanModeLabel('volatile', language),
    gainers: getScanModeLabel('gainers', language),
    losers: getScanModeLabel('losers', language),
    volume: getScanModeLabel('volume', language),
    all: getScanModeLabel('all', language),
    manual: getScanModeLabel('manual', language),
  };
  const [chartCoin, setChartCoin] = useState<string | null>(null);
  const [chartData, setChartData] = useState<any[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [listingRefreshing, setListingRefreshing] = useState(false);
  const [candleInterval, setCandleInterval] = useState('4h');
  const [candleDataOverride, setCandleDataOverride] = useState<CandlePoint[] | null>(null);
  useEffect(() => {
    if (!isDevMode) {
      const devTabs = ['MULTISCAN', 'BACKTEST', 'FORWARD', 'TELEMETRY', 'MODELS', 'UPDATES'];
      if (devTabs.includes(activeTab)) {
        setActiveTab('RADAR');
      }
    }
  }, [isDevMode, activeTab, setActiveTab]);

  const filteredCandidates = candidates;
  const hasStaleCandidateData = candidates.some((candidate) => candidate.is_stale);
  const visibleDataIsStale = hasStaleCandidateData;

  const candleCacheRef = useRef<Map<string, CandlePoint[]>>(new Map());

  // Reset interval to default 4h when coin changes.
  useEffect(() => {
    setCandleInterval('4h');
    setCandleDataOverride(null);
  }, [coinDetail?.symbol]);

  // Fetch candles for selected interval. The 5m view can use the enriched
  // coinDetail candles; other intervals are fetched from the chart endpoint.
  useEffect(() => {
    const symbol = coinDetail?.symbol;
    if (!symbol) return;
    if (candleInterval === '5m') {
      setCandleDataOverride(null);
      return;
    }
    const cacheKey = `${symbol}:${candleInterval}`;
    if (candleCacheRef.current.has(cacheKey)) {
      setCandleDataOverride(candleCacheRef.current.get(cacheKey)!);
      return;
    }
    const controller = new AbortController();
    // Do not keep displaying candles from the previous interval/coin while
    // the new series is loading; markers would otherwise be snapped against
    // the wrong time grid for a short period.
    setCandleDataOverride([]);
    const load = async () => {
      try {
        const res = await fetch(`/api/coin/${symbol}/chart?interval=${candleInterval}`, {
          signal: controller.signal,
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        const mapped: CandlePoint[] = (json.klines || []).map((k: any) => ({
          time: k.time_str,
          time_iso: k.time,
          price: k.close,
          open: k.open,
          high: k.high,
          low: k.low,
          close: k.close,
          volume: k.volume,
          oi: 0,
          funding: null,
          taker_ratio: 0.5,
          is_signal_point: false,
        }));
        candleCacheRef.current.set(cacheKey, mapped);
        setCandleDataOverride(mapped);
      } catch (err) {
        if ((err as DOMException).name !== 'AbortError') {
          console.error('Candle interval fetch error:', err);
        }
      }
    };
    load();
    return () => controller.abort();
  }, [coinDetail?.symbol, candleInterval]);

  const candleData = candleInterval === '5m'
    ? (candleDataOverride || coinDetail?.chart_data || [])
    : (candleDataOverride || []);

  const formattedCandleData = useMemo(() => {
    return candleData.map(c => ({
      time: c.time_iso || c.time,
      open: c.open || c.price,
      high: c.high || c.price,
      low: c.low || c.price,
      close: c.close || c.price,
      volume: c.volume || 0,
    }));
  }, [candleData]);

  // When a signal from RADAR is selected, keep its decision fields in sync
  // while preserving live market metrics from coinDetail (especially funding).
  // Fallback to selectedSignal or first candidate if coinDetail has not loaded yet.
  const displayDetail: CoinDetail | null = useMemo(() => {
    if (!coinDetail) {
      if (selectedSignal) {
        return {
          symbol: selectedSignal.symbol,
          name: selectedSignal.name || selectedSignal.symbol,
          market_cap_usd: selectedSignal.market_cap_usd,
          market_cap_str: selectedSignal.market_cap_str,
          market_cap_tier: selectedSignal.market_cap_tier,
          market_cap_source: selectedSignal.market_cap_source,
          market_cap_is_estimate: selectedSignal.market_cap_is_estimate,
          market_cap_updated_at: selectedSignal.market_cap_updated_at,
          current_price: selectedSignal.signal_price,
          chart_source: 'api',
          probability: selectedSignal.probability * 100,
          risk_level: selectedSignal.risk_level,
          target_drawdown: 0.05,
          target_price: selectedSignal.target_price,
          signal_timestamp: selectedSignal.signal_time,
          chart_data: [],
          metrics: {
            oi_change_24h: selectedSignal.oi_change_24h ?? 'N/A',
            taker_sell_ratio: selectedSignal.taker_sell_ratio ?? null,
            funding_rate: selectedSignal.funding_rate ?? 'N/A',
            funding_rate_source: 'signal_snapshot',
            rsi_15m: null,
            volume_delta_24h: 'N/A',
          },
          attribution_method: 'none',
          feature_drivers: [],
        };
      }
      if (candidates && candidates.length > 0) {
        const c = candidates[0];
        return {
          symbol: c.symbol,
          name: c.symbol,
          market_cap_usd: c.market_cap_usd,
          market_cap_str: c.market_cap_str,
          market_cap_tier: c.market_cap_tier,
          market_cap_source: c.market_cap_source,
          market_cap_is_estimate: c.market_cap_is_estimate,
          market_cap_updated_at: c.market_cap_updated_at,
          current_price: c.price,
          chart_source: 'api',
          probability: c.score || 0,
          risk_level: c.risk || 'MEDIUM',
          target_drawdown: 0.05,
          target_price: c.price * 0.95,
          signal_timestamp: null,
          chart_data: [],
          metrics: {
            oi_change_24h: c.oi_24h ?? 'N/A',
            taker_sell_ratio: c.taker_ratio ?? null,
            funding_rate: c.funding ?? 'N/A',
            funding_rate_source: 'signal_snapshot',
            rsi_15m: null,
            volume_delta_24h: c.volume_24h ?? 'N/A',
          },
          attribution_method: 'none',
          feature_drivers: [],
        };
      }
      return null;
    }
    if (!selectedSignal || selectedSignal.symbol !== coinDetail.symbol) return coinDetail;
    return {
      ...coinDetail,
      probability: selectedSignal.probability * 100,
      risk_level: selectedSignal.risk_level,
      target_price: selectedSignal.target_price > 0 ? selectedSignal.target_price : coinDetail.target_price,
      signal_timestamp: selectedSignal.signal_time,
      score_source: 'signal' as const,
      metrics: {
        ...(coinDetail.metrics || {}),
        oi_change_24h: selectedSignal.oi_change_24h ?? coinDetail.metrics?.oi_change_24h ?? 'N/A',
        // The selected signal contains a historical scanner snapshot. Keep
        // the detail panel on the live Binance value from coinDetail.
        funding_rate: coinDetail.metrics?.funding_rate ?? 'N/A',
        taker_sell_ratio: selectedSignal.taker_sell_ratio ?? coinDetail.metrics?.taker_sell_ratio ?? null,
      },
    };
  }, [coinDetail, selectedSignal, candidates]);

  const decisionContainerRef = useRef<HTMLDivElement>(null);
  const prevDecisionSymbolRef = useRef<string | null>(null);

  // Reset scroll to top ONLY when coin actually changes to a different symbol
  useEffect(() => {
    if (activeTab === 'DECISION') {
      const currentSymbol = displayDetail?.symbol || null;
      if (currentSymbol && currentSymbol !== prevDecisionSymbolRef.current) {
        prevDecisionSymbolRef.current = currentSymbol;
        if (decisionContainerRef.current) {
          decisionContainerRef.current.scrollTop = 0;
        }
        window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
      }
    }
  }, [displayDetail?.symbol, activeTab]);

  // Chỉ tính tradeSetup và vẽ lên biểu đồ khi coin ĐANG CÓ TÍN HIỆU CẢNH BÁO thực sự (FIRED / ARMED)
  const hasActiveSignal = useMemo(() => {
    if (!displayDetail) return false;
    const isSelectedMatched = Boolean(selectedSignal && selectedSignal.symbol.toUpperCase() === displayDetail.symbol.toUpperCase());
    const hasMatchingSignalInFeed = signals.some(s => s.symbol.toUpperCase() === displayDetail.symbol.toUpperCase());
    const hasAlertFlag = Boolean(displayDetail.has_alert);
    return isSelectedMatched || hasMatchingSignalInFeed || hasAlertFlag;
  }, [displayDetail, selectedSignal, signals]);

  // Compute trade setup levels (Entry, SL, TP1, TP2, R:R) only when an active signal exists
  const tradeSetup: TradeSetup | null = useMemo(() => {
    if (!displayDetail || displayDetail.current_price <= 0) return null;
    if (!hasActiveSignal) return null;

    const matchedSig = selectedSignal && selectedSignal.symbol.toUpperCase() === displayDetail.symbol.toUpperCase() ? selectedSignal : null;
    const ts = matchedSig?.trade_setup;
    
    // Strict requirement: Backend MUST provide a valid trade setup. No frontend fabrication.
    if (!ts || !ts.entry_price || !ts.stop_loss || !ts.tp1 || !ts.tp2) return null;

    const entry = ts.entry_price;
    const sl = ts.stop_loss;
    const tp1 = ts.tp1;
    const tp2 = ts.tp2;

    const slPct = ts.stop_loss_pct || Math.max(0.1, ((sl - entry) / entry) * 100);
    const tp1Pct = ts.tp1_pct || (((entry - tp1) / entry) * 100);
    const tp2Pct = ts.tp2_pct || (((entry - tp2) / entry) * 100);
    const riskRewardRatio = ts.rr_ratio || (slPct > 0 ? Number((tp2Pct / slPct).toFixed(1)) : 2.5);

    return {
      entryPrice: entry,
      entryZoneLow: entry * 0.995,
      entryZoneHigh: entry * 1.005,
      stopLossPrice: sl,
      stopLossPct: slPct,
      tp1Price: tp1,
      tp1Pct: tp1Pct,
      tp2Price: tp2,
      tp2Pct: tp2Pct,
      riskRewardRatio,
    };
  }, [displayDetail, selectedSignal, hasActiveSignal]);
  // The radar can emit several alerts for the same coin. Keep all of them
  // available to the chart; selectedSignal only represents the card currently
  // focused in the feed.
  const chartSignalMarkers = useMemo<CandlestickSignalMarker[]>(() => {
    if (!displayDetail) return [];

    const coinSignals: CandlestickSignalMarker[] = signals
      .filter(signal => signal.symbol === displayDetail.symbol)
      .map(signal => {
        const prob = signal.probability * 100;
        const isHigh = prob >= 41 || ['HIGH', 'CAO', 'HIGH_CONFIDENCE'].includes(String(signal.risk_level).toUpperCase());
        return {
          id: signal.id,
          time: signal.signal_time,
          probability: prob,
          isActive: selectedSignal?.id === signal.id,
          isValid: signal.validity_hours_left > 0,
          episodeRole: signal.episode_role,
          episodeTransition: signal.episode_transition,
          riskLevel: signal.risk_level,
          tier: isHigh ? 'HIGH_CONFIDENCE' : 'WATCH',
          telegramSent: signal.telegram_sent,
        };
      });

    if (
      selectedSignal &&
      selectedSignal.symbol === displayDetail.symbol &&
      !coinSignals.some(signal => signal.id === selectedSignal.id)
    ) {
      const prob = selectedSignal.probability * 100;
      const isHigh = prob >= 41 || ['HIGH', 'CAO', 'HIGH_CONFIDENCE'].includes(String(selectedSignal.risk_level).toUpperCase());
      coinSignals.push({
        id: selectedSignal.id,
        time: selectedSignal.signal_time,
        probability: prob,
        isActive: true,
        isValid: selectedSignal.validity_hours_left > 0,
        riskLevel: selectedSignal.risk_level,
        tier: isHigh ? 'HIGH_CONFIDENCE' : 'WATCH',
        telegramSent: selectedSignal.telegram_sent,
      });
    }

    if (
      coinSignals.length === 0 &&
      displayDetail.signal_timestamp &&
      Boolean(displayDetail.has_alert)
    ) {
      const prob = displayDetail.probability;
      const isHigh = (prob != null && prob >= 41) || ['HIGH', 'CAO', 'HIGH_CONFIDENCE'].includes(String(displayDetail.risk_level).toUpperCase());
      coinSignals.push({
        id: `${displayDetail.symbol}-${displayDetail.signal_timestamp}`,
        time: displayDetail.signal_timestamp,
        probability: displayDetail.probability,
        isActive: true,
        isValid: true,
        riskLevel: displayDetail.risk_level,
        tier: isHigh ? 'HIGH_CONFIDENCE' : 'WATCH',
      });
    }

    return coinSignals.sort((a, b) => {
      const aTime = parseSystemDate(a.time)?.getTime() ?? Number.NaN;
      const bTime = parseSystemDate(b.time)?.getTime() ?? Number.NaN;
      return aTime - bTime;
    });
  }, [displayDetail, selectedSignal, signals]);

  const handleShowCoinChart = async (symbol: string) => {
    setChartCoin(symbol);
    setChartLoading(true);
    setChartData([]);
    try {
      const res = await fetch(`/api/coin/${symbol}/chart`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setChartData(json.klines || []);
    } catch (err) {
      console.error('Fetch klines error:', err);
    } finally {
      setChartLoading(false);
    }
  };

  const handleRefreshListing = async () => {
    setListingRefreshing(true);
    try {
      await fetch('/api/listing/refresh', { method: 'POST' });
      // Trigger parent refresh — reload market data
      window.location.reload();
    } catch (err) {
      console.error('Listing refresh error:', err);
    } finally {
      setListingRefreshing(false);
    }
  };


  const [showV3, setShowV3] = useState(false);
  if (showV3) return <div className="bg-slate-900/80 border border-slate-800 rounded-xl lg:h-full overflow-hidden">
    <ErrorBoundary fallbackTitle="V3 research unavailable"><Suspense fallback={<p className="p-4 text-slate-400">Loading v3…</p>}>
      <V3ResearchPanel onClose={() => setShowV3(false)} />
    </Suspense></ErrorBoundary>
  </div>;

  return (
    <div
      data-testid="main-workspace"
      className="bg-slate-900/80 border border-slate-800 rounded-xl p-2.5 sm:p-3.5 flex flex-col h-auto lg:h-full overflow-visible lg:overflow-hidden relative"
    >

      {/* Real-time Scanning Progress Overlay Banner */}
      {isTriggeringScan && (
        <div className="absolute inset-0 z-40 bg-slate-950/90 backdrop-blur-sm flex flex-col items-center justify-center p-6 text-center">
          <div className="w-12 h-12 rounded-2xl bg-amber-500/20 border border-amber-500/50 flex items-center justify-center mb-3 text-amber-400">
            <Loader2 className="w-7 h-7 animate-spin" />
          </div>
          <h3 className="text-base font-bold text-slate-100 uppercase tracking-wider mb-1">
            {t('scan_triggering_banner_prefix')} {scanModeLabels[telemetryData?.active_scan_mode || ''] ?? telemetryData?.active_scan_mode?.toUpperCase()})
          </h3>
          <p className="text-xs text-amber-400">{language === 'vi' ? 'Đang gửi yêu cầu đến bộ quét…' : 'Sending request to the scanner…'}</p>
        </div>
      )}

      {/* Workspace Tab Bar (Grouped & Responsive for Desktop + Mobile) */}
      <button
        type="button"
        onClick={() => setShowV3(true)}
        data-testid="open-v3-research"
        className="self-start mb-2 px-2.5 py-1 border border-amber-500/40 bg-amber-500/10 rounded-lg text-[11px] font-semibold text-amber-300 hover:bg-amber-500/20 flex items-center gap-1.5 transition"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
        <span>{language === 'vi' ? 'Thử nghiệm V3 · Champion (Pump ≥25% + Đảo chiều)' : 'V3 Champion · (Pump ≥25% + Reversal)'}</span>
      </button>
      <WorkspaceTabBar
        isDevMode={isDevMode}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        selectedSignal={selectedSignal}
        onSelectCandidate={onSelectCandidate}
        trackingCount={trackingItems.filter(item => item.status !== 'CLOSED').length}
        candidateCount={candidates.length}
        signalCount={signals.length}
        isTelemetryActive={telemetryData ? telemetryData.scanner_engine_status !== 'ERROR' : false}
        onOpenTabHelp={onOpenTabHelp}
      />
      <Suspense
        fallback={(
          <div
            role="status"
            className="flex-1 min-h-[240px] flex items-center justify-center text-xs text-slate-400"
          >
            {language === 'zh'
              ? '正在加载工作区…'
              : language === 'ko'
                ? '작업 공간을 불러오는 중…'
                : language === 'vi'
                  ? 'Đang tải không gian làm việc…'
                  : 'Loading workspace…'}
          </div>
        )}
      >
      {/* TAB: RADAR SIGNAL FEED */}
      {activeTab === 'RADAR' && (
        <div className="flex-1 overflow-hidden h-full min-h-[500px]">
          <SignalFeed
            signals={filteredSignals || signals}
            allSignals={signals}
            selectedSignalId={selectedSignal?.id || null}
            onSelectSignal={onSelectSignal || ((sig: SignalItem) => onSelectCandidate(sig.symbol))}
            onGoToDecision={(sig: SignalItem) => {
              if (onSelectSignal) onSelectSignal(sig);
              else onSelectCandidate(sig.symbol);
              setActiveTab('DECISION');
            }}
            onOpenOrderModal={onOpenOrderModal}
            onPushTelegram={onPushTelegram}
            onTrackSignal={onTrackSignal}
            onUntrackSignal={onUntrackSignal}
            isSignalTracked={isSignalTracked}
            audioAlertEnabled={audioAlertEnabled}
            onDismissSignal={onDismissSignal}
            activeFilterTag={activeFilterTag}
            setActiveFilterTag={setActiveFilterTag || (() => {})}
            signalSort={signalSort}
            setSignalSort={setSignalSort || (() => {})}
            telegramFilter={telegramFilter}
            setTelegramFilter={setTelegramFilter || (() => {})}
          />
        </div>
      )}

      {activeTab === 'WATCHLIST' && (
        <TrackingWatchlist
          onAddTracking={onAddTracking}
          items={trackingItems}
          isLoading={isTrackingLoading}
          updatingId={trackingUpdatingId}
          onRefresh={onRefreshTracking}
          onSelectCoin={onSelectTrackingCoin}
          onUpdateItem={onUpdateTracking}
          onRemoveItem={onRemoveTracking}
        />
      )}

      {/* TAB 1: DECISION CENTER */}
      {activeTab === 'DECISION' && (
        <div ref={decisionContainerRef} className="flex-1 overflow-y-auto space-y-3 pr-1">
          {displayDetail ? (
            <div className="space-y-3">
              {/* 1. Quick Header (Search + Top 5 Candidates + Live Ticker) */}
              <DecisionHeader
                symbol={displayDetail.symbol}
                name={displayDetail.name}
                currentPrice={displayDetail.current_price}
                chartSource={displayDetail.chart_source}
                selectedSignal={selectedSignal}
                candidates={candidates}
                onSelectCandidate={onSelectCandidate}
                isDeepAnalyzing={isDeepAnalyzing}
                onOpenCoinSelector={onOpenCoinSelector}
                probability={displayDetail.probability ?? selectedSignal?.probability}
                riskLevel={displayDetail.risk_level ?? selectedSignal?.risk_level}
                tradeSetup={selectedSignal?.trade_setup}
                onOpenTabHelp={onOpenTabHelp ? () => onOpenTabHelp('DECISION') : undefined}
                displayDetail={displayDetail}
                high24h={candleData.length > 0 ? Math.max(...candleData.map(c => c.high || c.price)) : undefined}
                low24h={candleData.length > 0 ? Math.min(...candleData.map(c => c.low || c.price)) : undefined}
                change24h={
                  candleData.length >= 2 && candleData[0].close > 0
                    ? ((candleData[candleData.length - 1].close / candleData[0].close - 1) * 100)
                    : undefined
                }
              />
              {/* 2. Sub-Tabs Header (Desktop) */}
              <div className="hidden lg:flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2">
                <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setDecisionSubTab('TRADE')}
                  className={`px-4 py-1.5 rounded-t-lg text-xs font-bold transition-colors ${
                    decisionSubTab === 'TRADE' ? 'bg-slate-800 text-amber-400 border-b-2 border-amber-400' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                  }`}
                >
                  {language === 'en' ? 'Order Setup' : 'Kế Hoạch Lệnh'}
                </button>
                <button
                  type="button"
                  onClick={() => setDecisionSubTab('AI')}
                  className={`px-4 py-1.5 rounded-t-lg text-xs font-bold transition-colors ${
                    decisionSubTab === 'AI' ? 'bg-slate-800 text-amber-400 border-b-2 border-amber-400' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                  }`}
                >
                  {language === 'en' ? 'AI Deep Analysis' : 'Phân Tích AI'}
                </button>
              </div>
                <button
                  type="button"
                  onClick={() => setIsChartHidden(!isChartHidden)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors border flex items-center gap-1.5 ${
                    isChartHidden ? 'bg-amber-500/20 text-amber-300 border-amber-500/50 shadow-sm shadow-amber-500/20' : 'bg-slate-900 text-slate-400 hover:text-slate-200 hover:bg-slate-800 border-slate-700'
                  }`}
                >
                  {isChartHidden ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                  {isChartHidden ? (language === 'en' ? 'Show Chart' : 'Hiện Biểu Đồ') : (language === 'en' ? 'Hide Chart' : 'Ẩn Biểu Đồ')}
                </button>
              </div>

              {/* 3. Main Split-View Grid (Chart + Active Tab Content) */}
              <div className={`grid grid-cols-1 ${isChartHidden ? '' : 'lg:grid-cols-12'} gap-3 items-start min-w-0`}>
                {/* LEFT COLUMN (65% width on LG): Candlestick Chart ALWAYS visible */}
                {!isChartHidden && (
                  <div data-testid="decision-chart-column" className="lg:col-span-8 space-y-3 min-w-0">
                    {/* Candlestick Chart Card */}
                    <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-2.5 sm:p-3.5 min-w-0 shadow-lg lg:sticky lg:top-0 z-10">

                    {/* Candlestick chart (TradingView lightweight-charts) */}
                    <CandlestickChart
                      symbol={displayDetail?.symbol}
                      data={formattedCandleData}
                      targetPrice={displayDetail.target_price}
                      signalMarkers={chartSignalMarkers}
                      tradeSetup={tradeSetup}
                      interval={candleInterval}
                      onIntervalChange={setCandleInterval}
                      height={380}
                    />

                    {/* OI + Funding Sub Chart (hiển thị dưới biểu đồ nến khi có dữ liệu) */}
                    {(() => {
                      const hasOi = candleData.some(c => (c.oi || 0) !== 0);
                      const hasFunding = candleData.some(c => (c.funding || 0) !== 0);
                      return hasOi || hasFunding ? (
                        <div className="mt-3 bg-slate-950/90 border border-slate-800 rounded-xl p-3 shadow-lg">
                          <div className="text-[10px] font-bold text-slate-300 mb-2 uppercase">{t('ws_oi_funding_title')}</div>
                          <div className="h-32 w-full">
                            <ResponsiveContainer width="100%" height="100%">
                              <ComposedChart data={candleData}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                <XAxis dataKey="time" stroke="#64748b" fontSize={9} interval={Math.max(0, Math.floor(candleData.length / 8))} />
                                <YAxis yAxisId="oi" stroke="#06b6d4" fontSize={9} domain={['auto', 'auto']} />
                                <YAxis yAxisId="funding" orientation="right" stroke="#f59e0b" fontSize={9} domain={['auto', 'auto']} />
                                <Tooltip
                                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', fontSize: '11px' }}
                                />
                                <ReferenceLine yAxisId="funding" y={0} stroke="#334155" strokeDasharray="2 2" />
                                <Line yAxisId="oi" type="monotone" dataKey="oi" stroke="#06b6d4" strokeWidth={1.5} dot={false} name={t('metric_oi_24h')} />
                                <Line yAxisId="funding" type="monotone" dataKey="funding" stroke="#f59e0b" strokeWidth={1} dot={false} name={t('metric_funding')} />
                              </ComposedChart>
                            </ResponsiveContainer>
                          </div>
                        </div>
                      ) : null;
                    })()}
                    </div>
                  </div>
                )}

                {/* RIGHT COLUMN (35% width on LG): Dynamic Content based on Active Sub-Tab */}
                <div data-testid="decision-summary-column" className={`${isChartHidden ? '' : 'lg:col-span-4'} space-y-3 min-w-0`}>
                  {/* Sub-Tabs Header (Mobile) */}
                  <div className="lg:hidden flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setDecisionSubTab('TRADE')}
                        className={`px-4 py-1.5 rounded-t-lg text-xs font-bold transition-colors ${
                          decisionSubTab === 'TRADE' ? 'bg-slate-800 text-amber-400 border-b-2 border-amber-400' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                        }`}
                      >
                        {language === 'en' ? 'Order Setup' : 'Kế Hoạch Lệnh'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setDecisionSubTab('AI')}
                        className={`px-4 py-1.5 rounded-t-lg text-xs font-bold transition-colors ${
                          decisionSubTab === 'AI' ? 'bg-slate-800 text-amber-400 border-b-2 border-amber-400' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                        }`}
                      >
                        {language === 'en' ? 'AI Deep Analysis' : 'Phân Tích AI'}
                      </button>
                    </div>
                    <button
                      type="button"
                      onClick={() => setIsChartHidden(!isChartHidden)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors border flex items-center gap-1.5 ${
                        isChartHidden ? 'bg-amber-500/20 text-amber-300 border-amber-500/50 shadow-sm shadow-amber-500/20' : 'bg-slate-900 text-slate-400 hover:text-slate-200 hover:bg-slate-800 border-slate-700'
                      }`}
                    >
                      {isChartHidden ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                      {isChartHidden ? (language === 'en' ? 'Show Chart' : 'Hiện Biểu Đồ') : (language === 'en' ? 'Hide Chart' : 'Ẩn Biểu Đồ')}
                    </button>
                  </div>
                  {decisionSubTab === 'TRADE' && (
                    <>

                      {/* Trade Setup Card (V2 Interactive / V1 Classic) */}
                      {guiVersion === 'v2' ? (
                        <TradeSetupCardV2
                          symbol={displayDetail.symbol}
                          currentPrice={displayDetail.current_price}
                          signalPrice={selectedSignal?.signal_price}
                          targetPrice={displayDetail.target_price}
                          peakPrice={deepAnalysis?.pump_analysis?.peak_price}
                          invalidationPrice={tradeSetup?.stopLossPrice}
                          tradeSetup={selectedSignal?.trade_setup}
                          selectedSignal={selectedSignal}
                          onOpenOrderModal={onOpenOrderModal}
                        />
                      ) : (
                        <TradeSetupCard
                          currentPrice={displayDetail.current_price}
                          signalPrice={selectedSignal?.signal_price}
                          targetPrice={displayDetail.target_price}
                          peakPrice={deepAnalysis?.pump_analysis?.peak_price}
                          invalidationPrice={tradeSetup?.stopLossPrice}
                          tradeSetup={selectedSignal?.trade_setup}
                        />
                      )}
                      {/* AI Decision Cockpit */}
                      <AiDecisionCockpit
                        selectedSignal={selectedSignal}
                        displayDetail={displayDetail}
                        deepAnalysis={deepAnalysis}
                        isDeepAnalyzing={isDeepAnalyzing}
                        isSymbolTracked={isSymbolTracked}
                        isSymbolInWatchlist={isSymbolInWatchlist}
                        isWatchlistUpdating={isWatchlistUpdating}
                        onRunDeepAnalysis={onRunDeepAnalysis}
                        onPushTelegram={onPushTelegram}
                        onDismissSignal={onDismissSignal}
                        onAddWatchlist={onAddWatchlist ? ((s: string) => onAddWatchlist(s)) : undefined}
                        onAddTracking={onAddTracking ? ((s: string) => onAddTracking(s)) : undefined}
                        onRemoveTracking={onRemoveTrackingSymbol ? ((s: string) => onRemoveTrackingSymbol(s)) : undefined}
                      />
                    </>
                  )}

                  {decisionSubTab === 'AI' && (
                    <>
                      {/* Weighted score components and 8-component breakdown */}
                      <FeatureDriversAccordion
                        featureDrivers={displayDetail.feature_drivers}
                        deepAnalysis={deepAnalysis}
                      />

                      {/* Executive AI Briefing Bar */}
                      <ErrorBoundary fallbackTitle="Lỗi hiển thị Bản tin AI">
                        <AiExecutiveBriefing
                          displayDetail={displayDetail}
                          selectedSignal={selectedSignal}
                          deepAnalysis={deepAnalysis}
                          tradeSetup={tradeSetup}
                          onOpenAiChat={onOpenAiAssistant}
                        />
                      </ErrorBoundary>
                    </>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="p-12 text-center text-slate-500 bg-slate-950/60 border border-slate-800 rounded-xl">
              <Activity className="w-8 h-8 text-amber-400/60 mx-auto mb-2 animate-pulse" />
              <p className="text-sm text-slate-400 font-medium">
                {t('decision_select_prompt')}
              </p>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: CANDIDATE SELL RANKING TABLE */}
      {activeTab === 'RANKING' && (
        <div data-testid="candidate-ranking" className="flex-1 overflow-y-auto pr-1 space-y-3">
          {/* Header Banner */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3 sm:p-3.5 shadow-md">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2.5 mb-2.5">
              <div className="flex items-center gap-2">
                <div className="p-1.5 rounded-lg bg-violet-600/20 text-violet-300 border border-violet-500/30">
                  <BarChart3 className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-xs font-bold text-slate-200 flex items-center gap-2 uppercase tracking-wider">
                    <span>{t('ranking_title_full') || 'Bảng Xếp Hạng Top Coin Xả'}</span>
                    <span className="rounded-full bg-violet-950 border border-violet-700/80 px-2 py-0.2 text-[9px] font-bold text-violet-300">
                      {language === 'en' ? `${championLabel} Official` : language === 'zh' ? `${championLabel} 主版本` : language === 'ko' ? `${championLabel} 주 버전` : `${championLabel} Bản chính`}
                    </span>
                  </h3>
                  <p className="text-[11px] text-slate-400">
                    {language === 'zh'
                      ? '按实时配置监测 Binance Futures 范围，筛选高位滞涨与动能衰竭候选标的'
                      : language === 'ko'
                      ? '실시간 설정의 Binance Futures 범위에서 고점 분산과 모멘텀 소진 후보를 선별'
                      : 'Sàng lọc phạm vi Binance Futures theo cấu hình live để tìm ứng viên tăng nóng và cạn động lượng.'}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {onOpenTabHelp && (
                  <button
                    type="button"
                    onClick={() => onOpenTabHelp('RANKING')}
                    className="inline-flex items-center gap-1 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-[10px] font-medium text-slate-300 transition hover:border-violet-500/60 hover:text-violet-300 shadow-sm"
                    title="Xem hướng dẫn chi tiết về cơ chế & chỉ số Bảng Ứng Viên"
                  >
                    <HelpCircle className="h-3 w-3 text-violet-400" />
                    <span>{language === 'en' ? 'Guide' : language === 'zh' ? '功能说明' : language === 'ko' ? '도움말' : 'Hướng dẫn'}</span>
                  </button>
                )}
                <span className="text-[10px] text-slate-400 font-mono hidden sm:inline">{t('ranking_sorted_by_risk')}</span>
                <button
                  type="button"
                  data-testid="candidate-refresh"
                  onClick={() => onRefreshCandidates()}
                  disabled={isRefreshingCandidates}
                  className="inline-flex items-center gap-1 rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1 text-[10px] font-bold text-slate-300 transition hover:border-violet-500/60 hover:text-violet-300 active:scale-95 disabled:cursor-not-allowed disabled:opacity-60 shadow-sm"
                  title={t('ranking_refresh_tooltip')}
                >
                  <RefreshCw className={`h-3 w-3 ${isRefreshingCandidates ? 'animate-spin text-amber-400' : ''}`} />
                  <span>{isRefreshingCandidates ? t('ranking_scanning_status') : t('refresh')}</span>
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between gap-2 text-[11px]">
              <span className="inline-flex items-center gap-1.5 rounded-lg border border-violet-700/70 bg-violet-950/50 px-2.5 py-1 font-bold text-violet-200">
                👑 V1 · {language === 'vi' ? 'Bản chính duy nhất' : 'Single official version'}
              </span>
              <span className="font-mono text-[10px] text-slate-500">
                {candidates.length} {language === 'vi' ? 'ứng viên' : 'candidates'}
              </span>
            </div>
          </div>

          {candidateRefreshStatus !== 'idle' && (
            <div
              role="status"
              data-testid="candidate-refresh-status"
              className={`rounded-xl border px-3 py-2.5 text-xs ${
                candidateRefreshStatus === 'updated'
                  ? 'border-emerald-700/70 bg-emerald-950/40 text-emerald-200'
                  : candidateRefreshStatus === 'error'
                    ? 'border-red-700/70 bg-red-950/50 text-red-200'
                    : 'border-amber-700/70 bg-amber-950/40 text-amber-200'
              }`}
            >
              {candidateRefreshMessage[candidateRefreshStatus]}
            </div>
          )}

          {visibleDataIsStale && (
            <div role="alert" className="rounded-xl border border-red-700/70 bg-red-950/50 px-3 py-2.5 text-xs text-red-200">
              <span className="font-bold">⚠ {language === 'vi' ? 'Dữ liệu đã cũ.' : 'Stale data.'}</span>{' '}
              {language === 'vi'
                ? 'Scanner chưa xuất bản snapshot mới trong giới hạn an toàn. Chỉ dùng để tham khảo; thao tác vào lệnh đã bị khóa.'
                : 'The scanner has not published a fresh snapshot within the safety window. Trading actions are disabled.'}
            </div>
          )}

          {/* MAIN CANDIDATE TABLE (HIỂN THỊ NGAY TRÊN CÙNG) */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1040px] text-left text-xs text-slate-300">
                <thead className="bg-slate-900 border-b border-slate-800 text-slate-400 font-mono text-[10px] uppercase">
                  <tr>
                    <th className="p-2.5">{t('col_coin')}</th>
                    <th className="p-2.5">{language === 'zh' ? '筛选源 & 阶段' : language === 'ko' ? '필터링 출처 및 단계' : t('ranking_col_source_stage')}</th>
                    <th className="p-2.5">{t('col_price')}</th>
                    <th className="p-2.5">{t('col_score')}</th>
                    <th className="p-2.5">{language === 'zh' ? '风险等级' : language === 'ko' ? '위험 등급' : t('ranking_col_risk_tier')}</th>
                    <th className="p-2.5">{t('metric_oi_24h')}</th>
                    <th className="p-2.5">{t('metric_funding')}</th>
                    <th className="p-2.5">{t('metric_taker_sell')}</th>
                    <th className="p-2.5">{t('metric_volume_24h')}</th>
                    <th className="p-2.5">{language === 'vi' ? 'Bất thường' : language === 'zh' ? '异常' : language === 'ko' ? '이상 징후' : 'Anomalies'}</th>
                    <th className="p-2.5 text-right">{t('col_action')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {filteredCandidates.length === 0 && (
                    <tr>
                      <td colSpan={11} className="p-8 text-center font-sans text-slate-500">
                        {isRefreshingCandidates
                          ? t('candidate_filter_pipeline_loading') : t('candidate_empty_segment_notice')}
                      </td>
                    </tr>
                  )}
                  {filteredCandidates.map((c, i) => {
                    const candidateCapInfo = getCoinMarketCapInfo(c.symbol, c);
                    const candidateCapBadge = getMarketCapBadgeConfig(
                      candidateCapInfo.market_cap_tier,
                      candidateCapInfo.market_cap_str,
                      language,
                      candidateCapInfo.market_cap_is_estimate,
                    );
                    const hasCandidateMarketCap = candidateCapInfo.market_cap_usd > 0
                      && candidateCapInfo.market_cap_tier !== 'UNKNOWN';
                    const stageName = c.stage || 'PUMP_CANDIDATE';
                    const hasLiveSignal = signals.some(
                      (signal) => signal.symbol === c.symbol && signal.validity_hours_left > 0,
                    );
                    const canEnterTrade = Boolean(c.alertable && hasLiveSignal && !c.is_stale);

                    return (
                      <tr key={c.symbol} className={`hover:bg-slate-900/60 transition group ${c.is_stale ? 'opacity-60' : ''}`}>
                        <td className="p-2.5 font-bold text-white flex items-center gap-2">
                          <span className="text-slate-500 font-normal text-[10px]">#{i + 1}</span>
                          <CoinLink
                            symbol={c.symbol}
                            onClick={() => onSelectCandidate(c.symbol)}
                            className="text-xs group-hover:text-amber-300 font-bold"
                          />
                          {hasCandidateMarketCap && (
                            <span
                              data-testid={`candidate-market-cap-${c.symbol}`}
                              className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] font-bold ${candidateCapBadge.className}`}
                              title={`${t('metric_market_cap', 'Market Cap')}: ${candidateCapInfo.market_cap_str} · ${getMarketCapSourceLabel(candidateCapInfo.market_cap_source, language)}`}
                            >
                              <span>{candidateCapBadge.icon}</span>
                              <span>{candidateCapBadge.label}</span>
                            </span>
                          )}
                        </td>
                        <td className="p-2.5">
                          <span className="inline-flex items-center gap-1 rounded border border-violet-800 bg-violet-950 px-1.5 py-0.5 text-[9px] font-bold text-violet-300">
                            👑{' '}
                            {stageName}
                          </span>
                        </td>
                        <td className="p-2.5 text-amber-400 font-bold">{c.price > 0 ? `$${c.price < 1 ? c.price.toFixed(5) : c.price.toFixed(2)}` : '—'}</td>
                        <td className="p-2.5">
                          <div>
                            <span className="font-bold text-red-400">{c.score.toFixed(1)} {language === 'zh' ? '分' : language === 'ko' ? '점' : t('unit_points')}</span>
                            <span className={`block text-[9px] ${c.alertable ? 'text-emerald-400' : 'text-slate-500'}`}>
                              {getRiskLabel(c.recommendation || 'WAIT', language)}
                              {c.calibrated_probability != null ? ` · ML ${(c.calibrated_probability * 100).toFixed(1)}%` : ''}
                            </span>
                            <span className="block text-[9px] text-slate-500">
                              {c.data_quality_score != null ? `${language === 'vi' ? 'Dữ liệu' : 'Data'} ${(c.data_quality_score * 100).toFixed(0)}% · ` : ''}{c.age}
                            </span>
                          </div>
                        </td>
                        <td className="p-2.5">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            c.risk === 'CRITICAL' ? 'bg-red-950 text-red-400 border border-red-800' :
                            c.risk === 'HIGH' ? 'bg-amber-950 text-amber-400 border border-amber-800' :
                            c.risk === 'MEDIUM' ? 'bg-yellow-950 text-yellow-300 border border-yellow-800' :
                            'bg-emerald-950 text-emerald-400 border border-emerald-800'
                          }`}>
                            {riskLabels[c.risk] ?? c.risk}
                          </span>
                        </td>
                        <td className="p-2.5 text-red-400">{c.oi_24h}</td>
                        <td className="p-2.5 text-amber-300">{c.funding}</td>
                        <td className="p-2.5">{`${(c.taker_ratio * 100).toFixed(1)}%`}</td>
                        <td className="p-2.5 text-slate-400">{c.volume_24h}</td>
                        <td className="p-2.5">
                          <div className="flex max-w-[190px] flex-wrap items-center gap-1">
                            {c.anomalies && c.anomalies.length > 0 ? c.anomalies.slice(0, 3).map((anomaly) => (
                              <span
                                key={anomaly.code}
                                className={`rounded px-1.5 py-0.2 text-[8px] font-bold uppercase tracking-tight ${
                                  anomaly.severity === 'extreme'
                                    ? 'border border-rose-600/70 bg-rose-950 text-rose-300'
                                    : anomaly.severity === 'high'
                                    ? 'border border-amber-600/70 bg-amber-950 text-amber-300'
                                    : 'border border-slate-700 bg-slate-800 text-slate-300'
                                }`}
                                title={anomaly.explanation || anomaly.title}
                              >
                                {anomaly.title}
                              </span>
                            )) : (
                              <span className="text-[9px] text-slate-600">—</span>
                            )}
                          </div>
                        </td>
                        <td className="p-2.5 text-right">
                          <button
                            type="button"
                            data-testid={`candidate-action-${c.symbol}`}
                            onClick={() => {
                              onSelectCandidate(c.symbol);
                              setActiveTab('DECISION');
                              if (canEnterTrade && onOpenOrderModal) {
                                window.setTimeout(onOpenOrderModal, 0);
                              }
                            }}
                            className={`px-2.5 py-1 font-bold rounded text-[10px] transition shadow-sm ${
                              canEnterTrade
                                ? 'bg-red-500/20 hover:bg-red-500/30 border border-red-500/50 text-red-300 active:scale-95'
                                : 'bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/40 text-amber-300 active:scale-95'
                            }`}
                            title={c.is_stale
                              ? (language === 'vi' ? 'Mở dữ liệu tham khảo; giao dịch bị khóa vì snapshot đã cũ.' : 'Open for reference; trading is blocked because the snapshot is stale.')
                              : undefined}
                          >
                            {canEnterTrade
                              ? (language === 'vi' ? 'Vào lệnh' : 'Trade')
                              : (language === 'vi' ? 'Phân tích' : 'Analyze')}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

      </div>
    )}
      {/* TAB 2.5: MULTI-COIN SCAN */}
      {activeTab === 'MULTISCAN' && (
        <MultiCoinScan onSelectCoin={onSelectCandidate} />
      )}

      {/* TAB 2.6: BACKTEST EXPERIMENTS */}
      {activeTab === 'BACKTEST' && (
        <BacktestExperiments onSelectCoin={onSelectCandidate} />
      )}

      {/* TAB 2.7: FORWARD TEST */}
      {activeTab === 'FORWARD' && (
        <ForwardTest />
      )}

      {/* TAB 3: SCANNER TELEMETRY & LOGS */}
      {activeTab === 'TELEMETRY' && telemetryData && (
        <div className="flex-1 overflow-y-auto space-y-3 pr-1">
          {/* Header Controls & Live Status Cards */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-3">
              <div>
                <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
                  <Radio className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
                  {t('sys_telemetry_title')}
                </h3>
                <p className="text-[11px] text-slate-400">
                  {language === 'zh' ? '监控扫描频率、Binance API 延迟及后台守护进程执行日志' : language === 'ko' ? '스캔 주기, 바이낸스 API 지연 시간 및 백그라운드 작업 로그 모니터링' : t('telemetry_subtitle_desc')}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {onOpenTabHelp && (
                  <button
                    type="button"
                    onClick={() => onOpenTabHelp('TELEMETRY')}
                    className="px-2.5 py-1.5 bg-slate-900 border border-slate-700 hover:border-violet-500 text-slate-300 hover:text-violet-200 font-medium rounded-lg text-xs flex items-center gap-1.5 transition"
                    title="Xem hướng dẫn chi tiết về Hạ tầng & Giám sát Hệ thống"
                  >
                    <HelpCircle className="w-3.5 h-3.5 text-violet-400" />
                    <span>{language === 'zh' ? '功能说明' : language === 'ko' ? '도움말' : 'Hướng dẫn'}</span>
                  </button>
                )}
                <button
                  data-testid="scanner-trigger"
                  onClick={onTriggerManualScan}
                  disabled={isTriggeringScan}
                  className="px-3.5 py-1.5 bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-500 hover:to-emerald-400 text-slate-950 font-bold rounded-lg text-xs flex items-center gap-1.5 transition shadow-lg shadow-emerald-500/20 disabled:opacity-50"
                >
                <Play className="w-3.5 h-3.5 fill-current" />
                {isTriggeringScan ? t('telemetry_scanning_coins_progress').replace('{count}', '48') : t('telemetry_manual_scan_btn')}
              </button>
            </div>
          </div>

          {scanTriggeredSuccess && (
            <div className="p-2.5 mb-3 bg-emerald-950/90 border border-emerald-800 text-emerald-300 text-xs rounded-lg flex items-center gap-2 font-mono">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>{scanTriggeredSuccess}</span>
            </div>
          )}

            {/* Live Metrics Grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">{t('telemetry_engine_status')}</div>
                <div className="text-sm font-bold text-emerald-400 font-mono mt-0.5 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                  {scannerStatusLabels[telemetryData.scanner_engine_status] ?? telemetryData.scanner_engine_status}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">
                  {`${t('telemetry_interval_prefix')} ${telemetryData.poll_interval_minutes} ${t('telemetry_cycles_unit')}`}
                </div>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">{t('telemetry_next_scan_countdown')}</div>
                <div className="text-sm font-bold text-amber-400 font-mono mt-0.5 flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  {localCountdown != null
                    ? (language === 'zh'
                      ? `~${Math.floor(localCountdown / 60)}分 ${localCountdown % 60}秒`
                      : language === 'ko'
                      ? `~${Math.floor(localCountdown / 60)}분 ${localCountdown % 60}초`
                      : language === 'en'
                      ? `~${Math.floor(localCountdown / 60)}m ${localCountdown % 60}s`
                      : `~${Math.floor(localCountdown / 60)} phút ${localCountdown % 60} giây`)
                    : (t('metric_insufficient_data'))}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">
                  {t('telemetry_mode_prefix')}{scanModeLabels[telemetryData.active_scan_mode] ?? telemetryData.active_scan_mode.toUpperCase()}
                </div>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">{t('telemetry_binance_latency')}</div>
                <div className="text-sm font-bold text-sky-400 font-mono mt-0.5">
                  {telemetryData.average_api_latency_ms} ms
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">{t('telemetry_binance_usdm')}</div>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">{t('telemetry_scanned_alerts')}</div>
                <div className="text-sm font-bold text-slate-100 font-mono mt-0.5">
                  {telemetryData.scanned_pairs_count} {t('telemetry_pairs_unit')} / <span className="text-red-400">{telemetryData.signals_triggered_count} {t('telemetry_alerts_unit')}</span>
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">
                  {`${t('telemetry_excluded_prefix')} ${telemetryData.stablecoins_excluded_count ?? 'N/A'} ${t('telemetry_stablecoins_unit')}`}
                </div>
              </div>
            </div>

            {/* Model + Runtime Info */}
            <div className="mt-2.5 grid grid-cols-2 md:grid-cols-4 gap-2 text-[10px] font-mono">
              <div className="bg-slate-900/60 px-2 py-1.5 rounded border border-slate-800">
                <span className="text-slate-500">{t('telemetry_model_prefix')}</span>
                <span className="text-cyan-400">{telemetryData.model_id || (t('metric_insufficient_data'))}</span>
              </div>
              <div className="bg-slate-900/60 px-2 py-1.5 rounded border border-slate-800">
                <span className="text-slate-500">{t('telemetry_cycle_prefix')}</span>
                <span className="text-amber-400">{telemetryData.cycle ?? (t('metric_insufficient_data'))}</span>
              </div>
              <div className="bg-slate-900/60 px-2 py-1.5 rounded border border-slate-800">
                <span className="text-slate-500">{t('telemetry_max_coins_prefix')}</span>
                <span className="text-slate-300">{telemetryData.max_coins ?? (t('metric_insufficient_data'))}</span>
              </div>
              <div className="bg-slate-900/60 px-2 py-1.5 rounded border border-slate-800">
                <span className="text-slate-500">{t('telemetry_latest_scan_prefix')}</span>
                <span className="text-slate-300">{telemetryData.last_scan_timestamp ? formatSystemTime(telemetryData.last_scan_timestamp) : (t('metric_insufficient_data'))}</span>
              </div>
            </div>
          </div>

          {/* Real-time Execution Logs */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
            <h4 className="text-xs font-bold text-slate-200 mb-2 flex items-center gap-1.5 uppercase font-mono">
              <Terminal className="w-3.5 h-3.5 text-amber-400" />
              {`${t('telemetry_realtime_logs_title')} ${telemetryData.logs.length} ${t('telemetry_records_count')}`}
            </h4>

            <div className="overflow-x-auto border border-slate-800 rounded-lg max-h-72 overflow-y-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-900 border-b border-slate-800 text-slate-400 text-[10px] uppercase sticky top-0">
                  <tr>
                    <th className="p-2">{t('col_timestamp')}</th>
                    <th className="p-2">{t('col_coin')}</th>
                    <th className="p-2">{t('telemetry_col_step')}</th>
                    <th className="p-2">{t('col_status')}</th>
                    <th className="p-2">{t('telemetry_col_duration')}</th>
                    <th className="p-2">{t('telemetry_col_details')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-[11px]">
                  {telemetryData.logs.map((log, i) => (
                    <tr key={i} className="hover:bg-slate-900/60 transition">
                      <td className="p-2 text-slate-400 font-bold">{log.timestamp}</td>
                      <td className="p-2"><CoinLink symbol={log.symbol} onClick={() => onSelectCandidate(log.symbol)} /></td>
                      <td className="p-2 text-slate-300">{log.step}</td>
                      <td className="p-2">
                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                          log.status === 'ALERT FIRED' ? 'bg-red-950 text-red-400 border border-red-800' :
                          log.status === 'COMPLETED' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' :
                          log.status === 'RUNNING' ? 'bg-sky-950 text-sky-400 border border-sky-800 animate-pulse' :
                          'bg-slate-800 text-slate-400'
                        }`}>
                          {executionStatusLabels[log.status] ?? log.status}
                        </span>
                      </td>
                      <td className="p-2 text-amber-400">{log.duration_ms != null ? `${log.duration_ms}ms` : '—'}</td>
                      <td className="p-2 text-slate-400">{log.details}</td>
                    </tr>
                  ))}
                  {telemetryData.logs.length === 0 && (
                    <tr>
                      <td colSpan={6} className="p-6 text-center text-slate-500 text-[11px]">
                        {t('telemetry_no_logs_yet')}
                        <br />
                        <span className="text-[10px]">{t('telemetry_latest_scan_prefix')}{telemetryData.last_scan_timestamp || (t('metric_insufficient_data'))}</span>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Telegram Audit Logs */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
            <h4 className="text-xs font-bold text-slate-200 mb-2 flex items-center gap-1.5 uppercase font-mono">
              <Send className="w-3.5 h-3.5 text-sky-400" />
              {t('telemetry_dispatch_audit_title')}
            </h4>

            <div className="overflow-x-auto border border-slate-800 rounded-lg">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-900 border-b border-slate-800 text-slate-400 text-[10px] uppercase">
                  <tr>
                    <th className="p-2">{t('col_timestamp')}</th>
                    <th className="p-2">{t('col_coin')}</th>
                    <th className="p-2">{t('col_score')}</th>
                    <th className="p-2">{t('col_channel')}</th>
                    <th className="p-2">{t('col_outcome')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-[11px]">
                  {telemetryData.telegram_dispatches.map((tlog, i) => (
                    <tr key={i} className="hover:bg-slate-900/60 transition">
                      <td className="p-2 text-slate-400">{tlog.timestamp}</td>
                      <td className="p-2"><CoinLink symbol={tlog.symbol} onClick={() => onSelectCandidate(tlog.symbol)} /></td>
                      <td className="p-2 font-bold text-red-400">{tlog.risk_score}</td>
                      <td className="p-2 text-sky-400">{tlog.channel}</td>
                      <td className="p-2 text-emerald-400 font-bold">{executionStatusLabels[tlog.status] ?? tlog.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: MODEL AUDIT & VALIDATION MATRIX */}
      {activeTab === 'AUDIT' && auditData && <ModelAuditPanel audit={auditData} />}

      {/* TAB 5: MARKET OVERVIEW */}
      {/* TAB 5: MARKET OVERVIEW & ALPHA LAB */}
      {activeTab === 'MARKET' && marketData && (
        <div className="flex-1 overflow-y-auto space-y-3.5 pr-1">
          {/* Header Banner */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5 shadow-md">
            <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <div className="p-1.5 rounded-lg bg-sky-500/20 text-sky-400 border border-sky-500/30">
                  <Activity className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                    <span>{language === 'en' ? 'Market Climate & Binance Intelligence' : language === 'zh' ? '宏观市场气候与币安智能分析' : language === 'ko' ? '시장 환경 및 바이낸스 인텔리전스' : 'Khí Hậu Thị Trường & Tổng Quan Binance'}</span>
                    <span className="px-2 py-0.2 rounded bg-sky-950 border border-sky-700/80 font-mono text-[9px] text-sky-300 font-bold">
                      Live {marketData.binance_listing?.all_coins ?? marketData.binance_listing_total ?? 'N/A'} Coins
                    </span>
                  </h3>
                  <p className="text-[11px] text-slate-400">
                    {language === 'zh'
                      ? '监测宏观市场结构、Alpha Lab 风控过滤器、币安现货/合约全币种分布及 24h 涨跌动能'
                      : language === 'ko'
                      ? '거시적 시장 구조, 알파 랩 리스크 필터, 바이낸스 현물/선물 분포 및 24시간 변동성 모니터링'
                      : 'Giám sát cấu trúc thị trường vĩ mô, bộ lọc rủi ro Alpha Lab, phân bổ Spot/Futures Binance và top biến động 24h.'}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {onOpenTabHelp && (
                  <button
                    type="button"
                    onClick={() => onOpenTabHelp('MARKET')}
                    className="px-2 py-1 bg-slate-900 border border-slate-700 hover:border-violet-500 text-slate-300 hover:text-violet-200 font-medium rounded-md text-[10px] flex items-center gap-1 transition shadow-sm"
                    title="Xem hướng dẫn chi tiết về Thị trường"
                  >
                    <HelpCircle className="w-3 h-3 text-violet-400" />
                    <span>{language === 'en' ? 'Guide' : language === 'zh' ? '功能说明' : language === 'ko' ? '도움말' : 'Hướng dẫn'}</span>
                  </button>
                )}
                <span className="text-[10px] text-slate-400 hidden sm:inline font-mono">
                  {marketData.binance_listing?.date ? `${t('market_updated_prefix')}${marketData.binance_listing.date}` : ''}
                </span>
                <button
                  onClick={handleRefreshListing}
                  disabled={listingRefreshing}
                  className="px-2.5 py-1 text-[10px] font-bold text-amber-300 border border-amber-500/40 bg-amber-500/10 rounded-md hover:bg-amber-500/20 active:scale-95 transition disabled:opacity-50 flex items-center gap-1"
                >
                  <RefreshCw className={`h-3 w-3 ${listingRefreshing ? 'animate-spin' : ''}`} />
                  <span>{listingRefreshing ? t('market_binance_scanning') : t('market_binance_rescan_btn')}</span>
                </button>
              </div>
            </div>

            {/* 1. Macro Climate & Alpha Lab Cards (4 Cards) */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 mb-3.5">
              {/* Card 1: Market Regime */}
              <div className="bg-slate-900/90 p-2.5 rounded-lg border border-slate-800 space-y-1">
                <div className="text-[10px] text-slate-400 font-medium flex items-center justify-between">
                  <span>Chế độ thị trường (Regime)</span>
                  <span className={marketData.macro_climate?.available ? "h-2 w-2 rounded-full bg-emerald-400 animate-pulse" : "h-2 w-2 rounded-full bg-slate-600"} />
                </div>
                <div className="text-sm sm:text-base font-black text-emerald-400 font-mono mt-0.5 truncate">
                  {marketData.macro_climate?.regime || 'UNKNOWN'}
                </div>
                <div className="text-[10px] text-emerald-300/90 font-medium truncate">
                  {marketData.macro_climate?.regime_label_vi || 'Chưa có dữ liệu thời gian thực'}
                </div>
              </div>

              {/* Card 2: ADX Trend Strength */}
              <div className="bg-slate-900/90 p-2.5 rounded-lg border border-slate-800 space-y-1">
                <div className="text-[10px] text-slate-400 font-medium flex items-center justify-between">
                  <span>Độ mạnh xu hướng (ADX)</span>
                  <span className="text-[9px] font-mono text-cyan-400 font-bold">&gt; 25 Xu hướng mạnh</span>
                </div>
                <div className="text-sm sm:text-base font-black text-cyan-300 font-mono mt-0.5">
                  {marketData.macro_climate?.adx ?? 'N/A'}
                </div>
                <div className="text-[10px] text-slate-400 font-mono">
                  BB Width: {marketData.macro_climate?.bb_width ?? 'N/A'}
                </div>
              </div>

              {/* Card 3: Meta-Labeling Guard */}
              <div className="bg-slate-900/90 p-2.5 rounded-lg border border-slate-800 space-y-1">
                <div className="text-[10px] text-slate-400 font-medium flex items-center justify-between">
                  <span>Meta-Labeling Guard</span>
                  <span className="text-[9px] font-mono text-violet-400 font-bold">Lớp 2 ML</span>
                </div>
                <div className="text-sm sm:text-base font-black text-violet-300 font-mono mt-0.5">
                  {marketData.macro_climate?.meta_labeling || 'UNKNOWN'}
                </div>
                <div className="text-[10px] text-violet-300/90 font-medium">
                  {marketData.macro_climate?.meta_labeling ? 'Theo cấu hình scanner' : 'Chưa có dữ liệu từ API'}
                </div>
              </div>

              {/* Card 4: Drift Guardian */}
              <div className="bg-slate-900/90 p-2.5 rounded-lg border border-slate-800 space-y-1">
                <div className="text-[10px] text-slate-400 font-medium flex items-center justify-between">
                  <span>Drift Guardian</span>
                  <span className="text-[9px] font-mono text-emerald-400 font-bold">Rolling 7d</span>
                </div>
                <div className="text-sm sm:text-base font-black text-emerald-400 font-mono mt-0.5">
                  {marketData.macro_climate?.drift_guardian || 'UNKNOWN'}
                </div>
                <div className="text-[10px] text-slate-400 font-mono">
                  {marketData.macro_climate?.drift_guardian ? 'Trạng thái do API cung cấp' : 'Chưa có dữ liệu từ API'}
                </div>
              </div>
            </div>

            {/* 2. Binance Listing Breakdown (5 cards + 3 chips) */}
            {marketData.binance_listing && (
              <div className="border-t border-slate-800/80 pt-3 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase font-mono">
                    <BarChart3 className="w-3.5 h-3.5 text-amber-400" />
                    <span>Cấu Trúc Niêm Yết Toàn Bộ Sàn Binance ({marketData.binance_listing.all_coins} Coin)</span>
                  </span>
                  <div className="flex items-center gap-1.5 text-[10px] font-mono">
                    <span className="px-2 py-0.5 rounded bg-slate-900 text-amber-300 border border-slate-800">Chỉ Spot: <strong>{marketData.binance_listing.spot_only}</strong></span>
                    <span className="px-2 py-0.5 rounded bg-slate-900 text-sky-300 border border-slate-800">Chỉ Futures: <strong>{marketData.binance_listing.futures_only}</strong></span>
                    <span className="px-2 py-0.5 rounded bg-slate-900 text-emerald-300 border border-slate-800">Cả hai: <strong>{marketData.binance_listing.both}</strong></span>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                  <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
                    <div className="text-[9px] text-slate-400 uppercase font-semibold">{t('market_spot')}</div>
                    <div className="text-lg font-black text-amber-400 font-mono mt-0.5">{marketData.binance_listing.spot_coins.toLocaleString()}</div>
                    <div className="text-[9px] text-slate-500 font-mono">{marketData.binance_listing.spot_usdt_pairs} {t('market_usdt_pairs_unit')}</div>
                  </div>
                  <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
                    <div className="text-[9px] text-slate-400 uppercase font-semibold">USD-M Futures</div>
                    <div className="text-lg font-black text-sky-400 font-mono mt-0.5">{marketData.binance_listing.usdm_coins.toLocaleString()}</div>
                    <div className="text-[9px] text-slate-500 font-mono">{marketData.binance_listing.usdm_usdt_pairs} {t('market_usdt_pairs_unit')}</div>
                  </div>
                  <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
                    <div className="text-[9px] text-slate-400 uppercase font-semibold">COIN-M Futures</div>
                    <div className="text-lg font-black text-purple-400 font-mono mt-0.5">{marketData.binance_listing.coinm_coins.toLocaleString()}</div>
                    <div className="text-[9px] text-slate-500 font-mono">{marketData.binance_listing.coinm_symbols} {t('market_symbols_unit')}</div>
                  </div>
                  <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
                    <div className="text-[9px] text-slate-400 uppercase font-semibold">{t('market_futures')}</div>
                    <div className="text-lg font-black text-emerald-400 font-mono mt-0.5">{marketData.binance_listing.futures_coins.toLocaleString()}</div>
                    <div className="text-[9px] text-slate-500 font-mono">{t('market_at_least_1_futures')}</div>
                  </div>
                  <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
                    <div className="text-[9px] text-slate-400 uppercase font-semibold">{t('market_total_binance')}</div>
                    <div className="text-lg font-black text-white font-mono mt-0.5">{marketData.binance_listing.all_coins.toLocaleString()}</div>
                    <div className="text-[9px] text-slate-500 font-mono">{t('market_spot_futures_union')}</div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* 3. Dual Market Movers: Top Gainers vs Top Losers 24h */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {/* Top Gainers (Ứng viên bơm tạo đỉnh) */}
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5 shadow-md">
              <div className="flex items-center justify-between mb-2 border-b border-slate-800 pb-1.5">
                <h4 className="text-xs font-bold text-emerald-400 flex items-center gap-1.5 uppercase font-mono">
                  <ArrowUpRight className="w-4 h-4" />
                  <span>Top Coin Tăng Giá Mạnh 24h ({marketData.top_gainers.length})</span>
                </h4>
                <span className="text-[10px] text-slate-400 font-mono">Ứng viên Bơm Tạo Đỉnh</span>
              </div>
              <div className="space-y-1 text-xs max-h-[380px] overflow-y-auto pr-1">
                {marketData.top_gainers.map((g, i) => (
                  <div
                    key={i}
                    onClick={() => handleShowCoinChart(g.symbol)}
                    className="flex justify-between items-center bg-slate-900/80 p-2 rounded-lg cursor-pointer hover:bg-slate-800 hover:border-emerald-500/40 border border-slate-800/60 transition group"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-slate-500 text-[10px] font-mono w-4 text-right">#{i + 1}</span>
                      <CoinLink symbol={g.symbol} onClick={() => onSelectCandidate(g.symbol)} className="font-bold text-xs group-hover:text-emerald-300" />
                      <span className="text-slate-400 text-[10px] font-mono">${g.price > 0 ? (g.price < 1 ? g.price.toFixed(5) : g.price.toFixed(2)) : '—'}</span>
                    </div>
                    <div className="flex items-center gap-2.5 font-mono">
                      <span className="text-slate-400 text-[10px]">
                        {g.volume_24h ? `$${(g.volume_24h / 1e6).toFixed(1)}M` : ''}
                      </span>
                      <span className="font-bold text-emerald-400 bg-emerald-950/80 px-2 py-0.5 rounded border border-emerald-800/60 text-xs">
                        {g.change}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Top Losers (Đợt xả đang diễn ra) */}
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5 shadow-md">
              <div className="flex items-center justify-between mb-2 border-b border-slate-800 pb-1.5">
                <h4 className="text-xs font-bold text-red-400 flex items-center gap-1.5 uppercase font-mono">
                  <ArrowDownRight className="w-4 h-4" />
                  <span>Top Coin Giảm Giá Mạnh 24h ({marketData.top_losers.length})</span>
                </h4>
                <span className="text-[10px] text-slate-400 font-mono">Sóng Xả Tiếp Diễn</span>
              </div>
              <div className="space-y-1 text-xs max-h-[380px] overflow-y-auto pr-1">
                {marketData.top_losers.map((l, i) => (
                  <div
                    key={i}
                    onClick={() => handleShowCoinChart(l.symbol)}
                    className="flex justify-between items-center bg-slate-900/80 p-2 rounded-lg cursor-pointer hover:bg-slate-800 hover:border-red-500/40 border border-slate-800/60 transition group"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-slate-500 text-[10px] font-mono w-4 text-right">#{i + 1}</span>
                      <CoinLink symbol={l.symbol} onClick={() => onSelectCandidate(l.symbol)} className="font-bold text-xs group-hover:text-red-300" />
                      <span className="text-slate-400 text-[10px] font-mono">${l.price > 0 ? (l.price < 1 ? l.price.toFixed(5) : l.price.toFixed(2)) : '—'}</span>
                    </div>
                    <div className="flex items-center gap-2.5 font-mono">
                      <span className="text-slate-400 text-[10px]">
                        {l.volume_24h ? `$${(l.volume_24h / 1e6).toFixed(1)}M` : ''}
                      </span>
                      <span className="font-bold text-red-400 bg-red-950/80 px-2 py-0.5 rounded border border-red-800/60 text-xs">
                        {l.change}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* 4. Listing Evolution Chart */}
          {marketData.binance_listing_history && marketData.binance_listing_history.length >= 2 && (
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5 shadow-md">
              <div className="flex items-center justify-between mb-2 border-b border-slate-800 pb-1.5">
                <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase font-mono">
                  <LineChartIcon className="w-3.5 h-3.5 text-amber-400" />
                  <span>Biểu Đồ Lịch Sử Tăng Trưởng Niêm Yết ({marketData.binance_listing_history.length} Ngày)</span>
                </h4>
                <span className="text-[10px] text-slate-400 font-mono">Spot vs USD-M vs COIN-M</span>
              </div>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={marketData.binance_listing_history}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="date" stroke="#64748b" fontSize={9} />
                  <YAxis stroke="#64748b" fontSize={9} domain={['auto', 'auto']} />
                  <Tooltip
                    contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 11 }}
                    labelStyle={{ color: '#94a3b8' }}
                  />
                  <Line type="monotone" dataKey="spot_coins" stroke="#f59e0b" strokeWidth={2} dot={false} name={t('market_spot')} />
                  <Line type="monotone" dataKey="usdm_coins" stroke="#0ea5e9" strokeWidth={2} dot={false} name="USD-M" />
                  <Line type="monotone" dataKey="coinm_coins" stroke="#a855f7" strokeWidth={2} dot={false} name="COIN-M" />
                  <Line type="monotone" dataKey="futures_coins" stroke="#10b981" strokeWidth={2} dot={false} name={t('market_futures')} />
                  <Line type="monotone" dataKey="all_coins" stroke="#e2e8f0" strokeWidth={2} dot={false} name={t('market_total_binance')} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {/* Coin Chart Modal — click gainers/losers to view 72h chart */}
      {chartCoin && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => setChartCoin(null)}>
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-2xl w-full p-5" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-slate-200 flex items-center gap-1.5">
                <LineChartIcon className="w-4 h-4 text-amber-400" />
                {`${t('market_chart_72h_title')} — ${chartCoin}`}
              </h3>
              <button onClick={() => setChartCoin(null)} className="p-1 text-slate-400 hover:text-slate-200 text-xs">
                {t('market_chart_close_btn')}
              </button>
            </div>
            {chartLoading ? (
              <div className="h-[300px] flex items-center justify-center text-xs text-slate-400">
                {t('market_chart_loading')}
              </div>
            ) : chartData.length === 0 ? (
              <div className="h-[300px] flex items-center justify-center text-xs text-slate-500">
                {t('market_chart_error')}
              </div>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="time_str" stroke="#64748b" fontSize={9} interval={6} />
                    <YAxis stroke="#64748b" fontSize={10} domain={['auto', 'auto']} />
                    <Tooltip
                      contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 11 }}
                      labelStyle={{ color: '#94a3b8' }}
                      formatter={(v: any) => [`$${Number(v).toFixed(6)}`, t('chart_close_price')]}
                    />
                    <Area type="monotone" dataKey="close" stroke="#f59e0b" strokeWidth={2} fill="url(#priceGradient)" />
                  </AreaChart>
                </ResponsiveContainer>
                <div className="mt-2 grid grid-cols-4 gap-2 text-[10px]">
                  <div className="bg-slate-950 p-1.5 rounded text-center">
                    <div className="text-slate-500">{t('market_chart_current_price')}</div>
                    <div className="text-amber-400 font-mono font-bold">${chartData[chartData.length - 1]?.close.toFixed(6)}</div>
                  </div>
                  <div className="bg-slate-950 p-1.5 rounded text-center">
                    <div className="text-slate-500">{t('market_chart_72h_high')}</div>
                    <div className="text-emerald-400 font-mono">${Math.max(...chartData.map(k => k.high)).toFixed(6)}</div>
                  </div>
                  <div className="bg-slate-950 p-1.5 rounded text-center">
                    <div className="text-slate-500">{t('market_chart_72h_low')}</div>
                    <div className="text-red-400 font-mono">${Math.min(...chartData.map(k => k.low)).toFixed(6)}</div>
                  </div>
                  <div className="bg-slate-950 p-1.5 rounded text-center">
                    <div className="text-slate-500">{t('ws_stat_change')}</div>
                    <div className={`font-mono font-bold ${chartData[chartData.length - 1]?.close >= chartData[0]?.close ? 'text-emerald-400' : 'text-red-400'}`}>
                      {((chartData[chartData.length - 1]?.close / chartData[0]?.close - 1) * 100).toFixed(2)}%
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* TAB: SYSTEM HISTORY & DATA */}
      {activeTab === 'HISTORY' && (
        <ErrorBoundary fallbackTitle="Lỗi hiển thị Lịch sử & Dữ liệu">
          <SystemHistoryTab />
        </ErrorBoundary>
      )}

      {/* TAB: MODELS ARCHITECTURE & EVALUATION HISTORY */}
      {activeTab === 'MODELS' && (
        <ErrorBoundary fallbackTitle="Lỗi hiển thị Tài liệu Models & Đánh giá">
          <ModelsDocTab />
        </ErrorBoundary>
      )}

      {/* TAB: VERSION UPDATES & GITHUB TIMELINE */}
      {activeTab === 'UPDATES' && (
        <ErrorBoundary fallbackTitle="Lỗi hiển thị Cập nhật Phiên bản">
          <VersionHistoryTab />
        </ErrorBoundary>
      )}

      {/* TAB: SYSTEM SETTINGS & LLM CONFIG */}
      {activeTab === 'SETTINGS' && (
        <ErrorBoundary fallbackTitle="Lỗi hiển thị Cấu hình Hệ thống">
          <SystemSettingsTab
            isDevMode={isDevMode}
            setIsDevMode={setIsDevMode}
            guiVersion={guiVersion}
            onSelectGuiVersion={onSelectGuiVersion}
            threshold={threshold}
            setThreshold={setThreshold}
            activeScanModes={activeScanModes}
            onOpenWatchlistModal={onOpenWatchlistModal}
            onLogout={onLogout}
          />
        </ErrorBoundary>
      )}
      </Suspense>
    </div>
  );
};
