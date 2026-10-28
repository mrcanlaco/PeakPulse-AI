import { lazy, Suspense, useState, useEffect, useRef } from 'react';
import { Header } from './components/Header';
import { LockScreen } from './components/LockScreen';
import type { MobileTabType } from './components/v2/MobileBottomNav';
import type { WorkspaceTab } from './components/WorkspaceTabBar';
import type {
  SignalItem, CoinDetail, CandidateCoin, CandidateRefreshStatus, ModelAudit, MarketOverviewData, SystemStatus, FilterTag, SignalSort, TelegramFilter, AutomationSettings, ScannerTelemetry, WatchlistPreset, DeepAnalysis, ModelChoice, ModelsData, TrackingWatchlistItem
} from './types';
import { isSignalFired, isSignalArmed } from './types';
import { parseSystemDate } from './utils/time';
import { clearStoredPassword, checkAuthStatus, logoutAuth } from './utils/auth';
import { useTranslation, type Language } from './i18n/LanguageContext';

// Keep the authenticated shell small. Charts, modals, and secondary controls
// are loaded only after the lock screen has been cleared.
const MainWorkspace = lazy(() => import('./components/MainWorkspace').then(({ MainWorkspace: component }) => ({ default: component })));
const GlossaryModal = lazy(() => import('./components/GlossaryModal').then(({ GlossaryModal: component }) => ({ default: component })));
const WatchlistModal = lazy(() => import('./components/WatchlistModal').then(({ WatchlistModal: component }) => ({ default: component })));
const ModelComparisonModal = lazy(() => import('./components/ModelComparisonModal').then(({ ModelComparisonModal: component }) => ({ default: component })));
const TabHelpModal = lazy(() => import('./components/TabHelpModal').then(({ TabHelpModal: component }) => ({ default: component })));
const CoinSelectorModal = lazy(() => import('./components/CoinSelectorModal').then(({ CoinSelectorModal: component }) => ({ default: component })));
const MobileBottomNav = lazy(() => import('./components/v2/MobileBottomNav').then(({ MobileBottomNav: component }) => ({ default: component })));
const StickyActionBar = lazy(() => import('./components/v2/StickyActionBar').then(({ StickyActionBar: component }) => ({ default: component })));
const OrderExecutionModal = lazy(() => import('./components/v2/OrderExecutionModal').then(({ OrderExecutionModal: component }) => ({ default: component })));
const FloatingAiAssistant = lazy(() => import('./components/DecisionCenter/FloatingAiAssistant').then(({ FloatingAiAssistant: component }) => ({ default: component })));
export function App() {
  const { language, t } = useTranslation();

  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isAuthChecking, setIsAuthChecking] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    checkAuthStatus()
      .then((authStatus) => {
        if (cancelled) return;
        setIsAuthenticated(authStatus.authenticated);
        if (!authStatus.authenticated) clearStoredPassword();
      })
      .finally(() => {
        if (!cancelled) setIsAuthChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handleAuthError = () => {
      setIsAuthenticated(false);
      setAuthError(t('auth_session_expired'));
    };
    window.addEventListener('dao_vang_auth_error', handleAuthError);
    return () => window.removeEventListener('dao_vang_auth_error', handleAuthError);
  }, [t]);

  const handleLogout = () => {
    void logoutAuth();
    setIsAuthenticated(false);
    setAuthError(null);
  };

  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [signals, setSignals] = useState<SignalItem[]>([]);
  const [candidates, setCandidates] = useState<CandidateCoin[]>([]);
  const [auditData, setAuditData] = useState<ModelAudit | null>(null);
  const [marketData, setMarketData] = useState<MarketOverviewData | null>(null);
  const [telemetryData, setTelemetryData] = useState<ScannerTelemetry | null>(null);
  const [watchlistPresets, setWatchlistPresets] = useState<WatchlistPreset[]>([]);
  const [availableModels, setAvailableModels] = useState<ModelChoice[]>([]);
  const [selectedModelKey, setSelectedModelKey] = useState<string>('two_tier_climax');
  const [scannerModelId, setScannerModelId] = useState<string>('');

  const [activeScanModes, setActiveScanModes] = useState<string[]>(['volatile']);
  const [manualWatchlist, setManualWatchlist] = useState<string[]>([]);
  const [trackingItems, setTrackingItems] = useState<TrackingWatchlistItem[]>([]);
  const [isTrackingLoading, setIsTrackingLoading] = useState(false);
  const [trackingUpdatingId, setTrackingUpdatingId] = useState<string | null>(null);
  const [isWatchlistModalOpen, setIsWatchlistModalOpen] = useState(false);
  const [watchlistPendingAction, setWatchlistPendingAction] = useState<string | null>(null);
  const [watchlistFeedback, setWatchlistFeedback] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);
  const [isDevMode, setIsDevMode] = useState<boolean>(() => {
    try {
      const stored = localStorage.getItem('peakpulse_dev_mode');
      return stored ? JSON.parse(stored) : false;
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem('peakpulse_dev_mode', JSON.stringify(isDevMode));
    } catch {
      // ignore
    }
  }, [isDevMode]);


  useEffect(() => {
    if (!watchlistFeedback) return undefined;
    const timeoutId = window.setTimeout(() => setWatchlistFeedback(null), 5000);
    return () => window.clearTimeout(timeoutId);
  }, [watchlistFeedback]);

  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(null);
  const [selectedSignal, setSelectedSignal] = useState<SignalItem | null>(null);
  const [coinDetail, setCoinDetail] = useState<CoinDetail | null>(null);
  const [deepAnalysis, setDeepAnalysis] = useState<DeepAnalysis | null>(null);
  const [isDeepAnalyzing, setIsDeepAnalyzing] = useState(false);

  const [searchTerm, setSearchTerm] = useState('');
  const [selectedRiskFilter, setSelectedRiskFilter] = useState('ALL');
  const [activeFilterTag, setActiveFilterTag] = useState<FilterTag>('ACTIVE');
  const [signalSort, setSignalSort] = useState<SignalSort>('NEWEST');
  const [telegramFilter, setTelegramFilter] = useState<TelegramFilter>('ALL');
  const [threshold, setThreshold] = useState(0.25);

  const [automationSettings] = useState<AutomationSettings>({
    autoTelegramPush: true,
    autoPushThreshold: 0.80,
    audioAlertEnabled: true,
    webhookUrl: ''
  });

  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isRefreshingCandidates, setIsRefreshingCandidates] = useState(false);
  const [candidateRefreshStatus, setCandidateRefreshStatus] = useState<CandidateRefreshStatus>('idle');
  const [loadingStep, setLoadingStep] = useState<string | null>(null);
  const [isTriggeringScan, setIsTriggeringScan] = useState(false);
  const [scanTriggeredSuccess, setScanTriggeredSuccess] = useState<string | null>(null);
  const [isGlossaryOpen, setIsGlossaryOpen] = useState(false);
  const [telegramSentSuccess, setTelegramSentSuccess] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>(() => {
    if (typeof window !== 'undefined') {
      const h = window.location.hash.toLowerCase();
      if (h.includes('fibo') || h.includes('shadow') || h.includes('paper-oos')) return 'FIBO_SHORT';
      if (window.location.hash.includes('coin=')) return 'DECISION';
      if (window.innerWidth < 768) return 'RADAR';
    }
    return 'DECISION';
  });

  useEffect(() => {
    const onHash = () => {
      const h = window.location.hash.toLowerCase();
      if (h.includes('fibo') || h.includes('shadow') || h.includes('paper-oos')) {
        setActiveTab('FIBO_SHORT');
      }
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  // GUI Version: 'v1' (Classic 3-column) | 'v2' (Pro Mobile / Binance-OKX Style)
  const [guiVersion, setGuiVersion] = useState<'v1' | 'v2'>(() => {
    try {
      const saved = localStorage.getItem('dao_vang_gui_version');
      if (saved === 'v1' || saved === 'v2') return saved;
      if (typeof window !== 'undefined' && window.location.hash.includes('v1')) return 'v1';
      return 'v2';
    } catch {
      return 'v2';
    }
  });

  const handleSelectGuiVersion = (version: 'v1' | 'v2') => {
    setGuiVersion(version);
    try {
      localStorage.setItem('dao_vang_gui_version', version);
    } catch {
      // Ignore localStorage errors
    }
  };

  const [mobileTab, setMobileTab] = useState<MobileTabType>(() => {
    if (typeof window !== 'undefined' && window.location.hash.includes('coin=')) {
      return 'ANALYSIS';
    }
    return 'RADAR';
  });

  useEffect(() => {
    if (activeTab === 'RADAR') {
      setMobileTab('RADAR');
    } else if (activeTab === 'DECISION') {
      setMobileTab('ANALYSIS');
    } else if (activeTab === 'WATCHLIST') {
      setMobileTab('TRACKING');
    } else {
      setMobileTab('TOOLS');
    }
  }, [activeTab]);
  const [isOrderModalOpen, setIsOrderModalOpen] = useState(false);
  const [isModelComparisonOpen, setIsModelComparisonOpen] = useState(false);
  const [isTabHelpModalOpen, setIsTabHelpModalOpen] = useState(false);
  const [isCoinSelectorOpen, setIsCoinSelectorOpen] = useState(false);
  const [isFloatingAiAssistantOpen, setIsFloatingAiAssistantOpen] = useState(false);
  const getStepText = (stepKey: string, _lang: Language) => {
    return t(`loading_${stepKey}`);
  };

  const fetchJsonOr = async <T,>(url: string, fallback: T): Promise<T> => {
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) return fallback;
      return await res.json() as T;
    } catch {
      return fallback;
    }
  };

  const loadSignals = async (): Promise<SignalItem[] | null> => {
    try {
      const res = await fetch('/api/signals?status=all&dedup=1', { cache: 'no-store' });
      if (!res.ok) return null;
      const payload = await res.json() as unknown;
      return Array.isArray(payload) ? payload as SignalItem[] : null;
    } catch {
      return null;
    }
  };

  const loadTrackingWatchlist = async (): Promise<TrackingWatchlistItem[] | null> => {
    try {
      const res = await fetch('/api/tracking-watchlist', { cache: 'no-store' });
      if (!res.ok) return null;
      const payload = await res.json() as unknown;
      return Array.isArray(payload) ? payload as TrackingWatchlistItem[] : null;
    } catch {
      return null;
    }
  };

  const refreshTrackingWatchlist = async () => {
    setIsTrackingLoading(true);
    try {
      const freshItems = await loadTrackingWatchlist();
      if (freshItems) setTrackingItems(freshItems);
      else setWatchlistFeedback({ type: 'error', message: language === 'vi' ? 'Chưa tải được dữ liệu mới. Danh sách đang hiển thị là lần tải trước.' : 'Unable to refresh. Showing the previous snapshot.' });
    } finally {
      setIsTrackingLoading(false);
    }
  };

  const loadCandidates = async (): Promise<CandidateCoin[]> => {
    const res = await fetchJsonOr<CandidateCoin[] | null>('/api/candidates', null);
    return Array.isArray(res) ? res : [];
  };

  const handleRefreshCandidates = async () => {
    setIsRefreshingCandidates(true);
    setCandidateRefreshStatus('idle');
    try {
      const beforeFingerprint = candidates
        .map((candidate) => `${candidate.symbol}:${candidate.scan_time || ''}`)
        .join('|');
      const res = await fetch('/api/candidates/refresh', { method: 'POST' });
      if (!res.ok) throw new Error(`Candidate refresh HTTP ${res.status}`);
      setCandidateRefreshStatus('queued');

      const telemetry = await fetchJsonOr<ScannerTelemetry | null>('/api/scanner/telemetry', null);
      if (!telemetry || telemetry.scanner_engine_status === 'OFFLINE') {
        setCandidates(await loadCandidates());
        setCandidateRefreshStatus('queued');
        return;
      }

      // A scan runs in a separate daemon and can take 1-2 minutes. Keep the
      // spinner truthful and wait for a different snapshot instead of
      // immediately presenting the pre-scan cache as a successful refresh.
      const deadline = Date.now() + 150_000;
      let receivedFreshSnapshot = false;
      while (Date.now() < deadline) {
        await new Promise(resolve => window.setTimeout(resolve, 2_000));
        const freshCandidates = await loadCandidates();
        const freshFingerprint = freshCandidates
          .map((candidate) => `${candidate.symbol}:${candidate.scan_time || ''}`)
          .join('|');
        if (freshFingerprint !== beforeFingerprint) {
          setCandidates(freshCandidates);
          receivedFreshSnapshot = true;
          break;
        }
      }
      setCandidates(await loadCandidates());
      setCandidateRefreshStatus(receivedFreshSnapshot ? 'updated' : 'timeout');
    } catch (err) {
      console.error('Candidate ranking refresh error:', err);
      setCandidateRefreshStatus('error');
    } finally {
      setIsRefreshingCandidates(false);
    }
  };

  // Fetch initial data & telemetry with progress tracking
  const fetchData = async () => {
    setIsRefreshing(true);
    setLoadingStep(getStepText('init', language));
    try {
      setLoadingStep(getStepText('s1', language));
      const statusRes = await fetchJsonOr<SystemStatus | null>('/api/status', null);

      setLoadingStep(getStepText('s2', language));
      const sigRes = await loadSignals();

      setLoadingStep(getStepText('s3', language));
      const candRes = await loadCandidates().catch(() => []);

      setLoadingStep(getStepText('s4', language));
      const auditRes = await fetchJsonOr<ModelAudit | null>('/api/audit', null);

      setLoadingStep(getStepText('s5', language));
      const mktRes = await fetchJsonOr<MarketOverviewData | null>('/api/market', null);

      setLoadingStep(getStepText('s6', language));
      const wlRes = await fetchJsonOr<{
        active_scan_mode?: string;
        active_scan_modes?: string[];
        manual_watchlist?: string[];
        presets?: WatchlistPreset[];
      } | null>('/api/watchlist', null);

      const trackingRes = await fetchJsonOr<TrackingWatchlistItem[]>('/api/tracking-watchlist', trackingItems);

      setLoadingStep(getStepText('s7', language));
      const telemRes = await fetchJsonOr<ScannerTelemetry | null>('/api/scanner/telemetry', null);

      setLoadingStep(getStepText('s8', language));
      const modelsRes = await fetchJsonOr<ModelsData | null>('/api/models', null);

      setStatus(statusRes);
      if (sigRes !== null) setSignals(sigRes);
      setCandidates(candRes);
      setAuditData(auditRes);
      setMarketData(mktRes);
      setTelemetryData(telemRes);
      setTrackingItems(trackingRes);
      if (modelsRes) {
        setAvailableModels(modelsRes.models);
        setScannerModelId(modelsRes.current_scanner_model_id || '');
        const currentKey = modelsRes.models.find(
          (m) => m.frozen_model_id === modelsRes.current_scanner_model_id
        )?.key;
        if (currentKey) setSelectedModelKey(currentKey);
      }
      if (wlRes) {
        const modes = Array.isArray(wlRes.active_scan_modes) && wlRes.active_scan_modes.length > 0
          ? wlRes.active_scan_modes
          : (wlRes.active_scan_mode || 'volatile').split(',').map((mode) => mode.trim()).filter(Boolean);
        setActiveScanModes(modes.length > 0 ? modes : ['volatile']);
        setManualWatchlist(wlRes.manual_watchlist || []);
        if (wlRes.presets) setWatchlistPresets(wlRes.presets);
      }

      const hashSymbol = typeof window !== 'undefined'
        ? (new URLSearchParams(window.location.hash.slice(1)).get('coin')?.toUpperCase() || null)
        : null;

      if (sigRes && sigRes.length > 0 && !activeCoin.current && !hashSymbol) {
        setSelectedSignalId(sigRes[0].id);
        setSelectedSignal(sigRes[0]);
        fetchCoinDetail(sigRes[0].symbol);
        handleRunDeepAnalysis(sigRes[0].symbol);
      } else if (candRes && candRes.length > 0 && !activeCoin.current && !hashSymbol) {
        fetchCoinDetail(candRes[0].symbol);
        handleRunDeepAnalysis(candRes[0].symbol);
      }
    } catch (err) {
      console.error("Error loading API data:", err);
    } finally {
      setIsRefreshing(false);
      setLoadingStep(null);
    }
  };

  const coinDetailCache = useRef<Map<string, CoinDetail>>(new Map());
  const deepAnalysisCache = useRef<Map<string, DeepAnalysis>>(new Map());

  const activeCoin = useRef<string | null>(null);
  const detailRequest = useRef(0);
  const analysisRequest = useRef(0);

  const fetchCoinDetail = async (symbol: string) => {
    activeCoin.current = symbol;
    const requestId = ++detailRequest.current;
    setCoinDetail(coinDetailCache.current.get(symbol) ?? null);
    if (coinDetailCache.current.has(symbol)) {
      setCoinDetail(coinDetailCache.current.get(symbol)!);
    }
    try {
      const res = await fetch(`/api/coin/${encodeURIComponent(symbol)}`);
      if (!res.ok) return;
      const data = await res.json();
      if (data && !data.error && data.metrics) {
        coinDetailCache.current.set(symbol, data);
        if (activeCoin.current === symbol && requestId === detailRequest.current) setCoinDetail(data);
      }
    } catch (err) {
      console.error(`Error loading detail for ${symbol}:`, err);
    }
  };

  useEffect(() => {
    if (!isAuthenticated) return;
    fetchData();

    const timer = setInterval(async () => {
      const freshSignals = await loadSignals();
      if (freshSignals !== null) setSignals(freshSignals);
      try {
        const freshTracking = await loadTrackingWatchlist();
        if (freshTracking) setTrackingItems(freshTracking);
      } catch {
        // keep previous snapshot
      }
      try {
        const telemRes = await fetchJsonOr<ScannerTelemetry | null>('/api/scanner/telemetry', null);
        if (telemRes) setTelemetryData(telemRes);
      } catch {}
      try {
        setCandidates(await loadCandidates());
      } catch {
        // keep previous snapshot
      }
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [isAuthenticated]);

  // Defer protected requests until login; URLSearchParams decodes Unicode symbols.
  useEffect(() => {
    if (!isAuthenticated) return;
    const loadHashCoin = () => {
      const symbol = new URLSearchParams(window.location.hash.slice(1)).get('coin')?.trim().toUpperCase();
      if (!symbol || !/^[\p{L}\p{N}_-]+$/u.test(symbol)) return;
      setSelectedSignalId(null);
      setSelectedSignal(null);
      setDeepAnalysis(null);
      setActiveTab('DECISION');
      void fetchCoinDetail(symbol);
      void handleRunDeepAnalysis(symbol);
    };
    loadHashCoin();
    window.addEventListener('hashchange', loadHashCoin);
    return () => window.removeEventListener('hashchange', loadHashCoin);
    // The handlers only write state and use refs for request ordering.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated]);

  const handleSelectSignal = (sig: SignalItem) => {
    setSelectedSignalId(sig.id);
    setSelectedSignal(sig);
    setDeepAnalysis(null);
    setActiveTab('DECISION');
    if (guiVersion === 'v2') {
      setMobileTab('ANALYSIS');
    }
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    fetchCoinDetail(sig.symbol);
    handleRunDeepAnalysis(sig.symbol);
  };

  const handleSelectCandidate = (symbol: string) => {
    const existingSig = signals.find(s => s.symbol === symbol);
    if (existingSig) {
      handleSelectSignal(existingSig);
      return;
    }
    setSelectedSignalId(null);
    setSelectedSignal(null);
    setDeepAnalysis(null);
    setActiveTab('DECISION');
    if (guiVersion === 'v2') {
      setMobileTab('ANALYSIS');
    }
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    fetchCoinDetail(symbol);
    handleRunDeepAnalysis(symbol);
  };

  const handlePushTelegram = async (sig: SignalItem) => {
    try {
      const response = await fetch('/api/telegram/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: sig.symbol, probability: sig.probability })
      });
      const result = await response.json();
      if (!response.ok || result.status !== 'success') throw new Error(result.message || t('network_err'));
      const successMsg = t('toast_telegram_sent').replace('{symbol}', sig.symbol);
      setTelegramSentSuccess(successMsg);
      setTimeout(() => setTelegramSentSuccess(null), 4000);
    } catch (err) {
      setWatchlistFeedback({ type: "error", message: err instanceof Error ? err.message : t("network_err") });
      console.error("Telegram push error:", err);
    }
  };

  const handleDismissSignal = async (sig: SignalItem) => {
    try {
      const response = await fetch('/api/alerts/dismiss', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: sig.symbol, signal_time: sig.signal_time })
      });
      if (!response.ok) throw new Error((await response.json()).error || t("network_err"));
      setSignals(prev => prev.filter(s => s.id !== sig.id));
      if (selectedSignalId === sig.id) {
        setSelectedSignalId(null);
        setSelectedSignal(null);
        setCoinDetail(null);
        setDeepAnalysis(null);
      }
    } catch (err) {
      setWatchlistFeedback({ type: "error", message: err instanceof Error ? err.message : t("network_err") });
      console.error("Error dismissing signal:", err);
    }
  };

  const handleTriggerManualScan = async () => {
    setIsTriggeringScan(true);
    setScanTriggeredSuccess(null);
    try {
      const res = await fetch('/api/scanner/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force: true })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || t('network_err'));
      const successMsg = t('toast_scan_triggered');
      setScanTriggeredSuccess(successMsg);
      await fetchData();
      setTimeout(() => setScanTriggeredSuccess(null), 6000);
    } catch (err) {
      setWatchlistFeedback({ type: "error", message: err instanceof Error ? err.message : t("network_err") });
      console.error("Error triggering manual scan:", err);
    } finally {
      setIsTriggeringScan(false);
    }
  };

  const handleAddManualCoin = async (symbol: string): Promise<boolean> => {
    const nextSymbol = symbol.trim().toUpperCase();
    if (!nextSymbol) return false;

    setWatchlistPendingAction(`add:${nextSymbol}`);
    setWatchlistFeedback(null);
    try {
      const res = await fetch('/api/watchlist/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: nextSymbol })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || t('error_failed_to_add'));

      setManualWatchlist(data.manual_watchlist || [...manualWatchlist, nextSymbol]);
      const successMsg = t('toast_watchlist_added').replace('{symbol}', nextSymbol);
      setWatchlistFeedback({ type: 'success', message: successMsg });
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : t('error_failed_to_add');
      setWatchlistFeedback({ type: 'error', message });
      console.error("Error adding manual coin:", err);
      return false;
    } finally {
      setWatchlistPendingAction(null);
    }
  };

  const handleRemoveManualCoin = async (symbol: string): Promise<boolean> => {
    setWatchlistPendingAction(`remove:${symbol}`);
    setWatchlistFeedback(null);
    try {
      const res = await fetch('/api/watchlist/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || t('error_failed_to_remove'));

      setManualWatchlist(data.manual_watchlist || manualWatchlist.filter((item) => item !== symbol));
      const successMsg = t('toast_watchlist_removed').replace('{symbol}', symbol);
      setWatchlistFeedback({ type: 'success', message: successMsg });
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : t('error_failed_to_remove');
      setWatchlistFeedback({ type: 'error', message });
      console.error("Error removing manual coin:", err);
      return false;
    } finally {
      setWatchlistPendingAction(null);
    }
  };

  const addTrackingItem = async (payload: {
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
  }): Promise<boolean> => {
    const symbol = payload.symbol.trim().toUpperCase();
    if (!symbol) return false;
    setWatchlistPendingAction(`tracking:add:${symbol}`);
    setWatchlistFeedback(null);
    try {
      const res = await fetch('/api/tracking-watchlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...payload, symbol }),
      });
      const data = await res.json().catch(() => ({})) as { item?: TrackingWatchlistItem; error?: string };
      if (!res.ok || !data.item) throw new Error(data.error || `Tracking HTTP ${res.status}`);
      setTrackingItems(prev => {
        const exists = prev.some(item => item.id === data.item?.id);
        return exists ? prev.map(item => item.id === data.item?.id ? data.item! : item) : [data.item!, ...prev];
      });
      const successMsg = t('toast_tracking_added').replace('{symbol}', symbol);
      setWatchlistFeedback({ type: 'success', message: successMsg });
      setActiveTab('WATCHLIST');
      if (guiVersion === 'v2') setMobileTab('TRACKING');
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : t('error_failed_to_update_tracking');
      setWatchlistFeedback({ type: 'error', message });
      console.error('Tracking watchlist add error:', err);
      return false;
    } finally {
      setWatchlistPendingAction(null);
    }
  };

  const handleTrackSignal = (sig: SignalItem) => addTrackingItem({
    source_prediction_id: sig.id.startsWith('prediction-') ? sig.id.slice('prediction-'.length) : null,
    source_reason: sig.trigger_pattern_vi || sig.trigger_pattern || '',
    symbol: sig.symbol,
    source: 'radar',
    source_signal_time: sig.signal_time,
    source_probability: sig.probability,
    source_risk_level: sig.risk_level,
    source_price: sig.signal_price,
    source_target_price: sig.target_price,
    source_invalidation_time: sig.invalidation_time,
  });

  const handleUntrackSignal = async (sig: SignalItem) => {
    const item = trackingItems.find(
      t => t.status !== 'CLOSED' && t.symbol === sig.symbol && (t.source_signal_time === sig.signal_time || !t.source_signal_time)
    ) || trackingItems.find(t => t.status !== 'CLOSED' && t.symbol === sig.symbol);
    if (item) {
      return await removeTrackingItem(item.id);
    }
    return false;
  };

  const handleTrackCurrentCoin = (symbol: string) => {
    const signal = selectedSignal?.symbol === symbol ? selectedSignal : signals.find(item => item.symbol === symbol);
    return addTrackingItem(signal ? {
      source_prediction_id: signal.id.startsWith('prediction-') ? signal.id.slice('prediction-'.length) : null,
      source_reason: signal.trigger_pattern_vi || signal.trigger_pattern || '',
      symbol,
      source: 'radar',
      source_signal_time: signal.signal_time,
      source_probability: signal.probability,
      source_risk_level: signal.risk_level,
      source_price: signal.signal_price,
      source_target_price: signal.target_price,
      source_invalidation_time: signal.invalidation_time,
    } : { symbol, source: 'manual' });
  };

  const handleUntrackCurrentCoin = async (symbol: string) => {
    const cleanSymbol = symbol.trim().toUpperCase();
    const items = trackingItems.filter(
      item => item.status !== 'CLOSED' && item.symbol === cleanSymbol
    );
    if (items.length === 0) return false;
    let allOk = true;
    for (const it of items) {
      const ok = await removeTrackingItem(it.id);
      if (!ok) allOk = false;
    }
    return allOk;
  };

  const updateTrackingItem = async (id: string, patch: Record<string, unknown>): Promise<boolean> => {
    setTrackingUpdatingId(id);
    try {
      const res = await fetch(`/api/tracking-watchlist/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      });
      const data = await res.json().catch(() => ({})) as { item?: TrackingWatchlistItem; error?: string };
      if (!res.ok || !data.item) throw new Error(data.error || `Tracking HTTP ${res.status}`);
      setTrackingItems(prev => prev.map(item => item.id === id ? { ...item, ...data.item! } : item));
      const successMsg = t('toast_tracking_updated');
      setWatchlistFeedback({ type: 'success', message: successMsg });
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : t('error_failed_to_update_tracking');
      setWatchlistFeedback({ type: 'error', message });
      console.error('Tracking watchlist update error:', err);
      return false;
    } finally {
      setTrackingUpdatingId(null);
    }
  };

  const removeTrackingItem = async (id: string): Promise<boolean> => {
    setTrackingUpdatingId(id);
    try {
      const res = await fetch(`/api/tracking-watchlist/${encodeURIComponent(id)}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`Tracking HTTP ${res.status}`);
      setTrackingItems(prev => prev.map(item => item.id === id
        ? { ...item, status: 'CLOSED', archived_at: new Date().toISOString() }
        : item));
      const successMsg = t('toast_tracking_removed');
      setWatchlistFeedback({ type: 'success', message: successMsg });
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : t('error_failed_to_remove_tracking');
      setWatchlistFeedback({ type: 'error', message });
      console.error('Tracking watchlist remove error:', err);
      return false;
    } finally {
      setTrackingUpdatingId(null);
    }
  };

  const handleChangeScanModes = async (modes: string[]): Promise<boolean> => {
    const normalizedModes = Array.from(new Set(modes.map((mode) => mode.trim().toLowerCase()).filter(Boolean)));
    if (normalizedModes.length === 0) return false;

    const previousModes = activeScanModes;
    setWatchlistPendingAction('modes');
    setWatchlistFeedback(null);
    setActiveScanModes(normalizedModes);
    try {
      const res = await fetch('/api/watchlist/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ modes: normalizedModes })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || t('error_failed_to_change_scan_mode'));
      const confirmedModes = Array.isArray(data.active_scan_modes) && data.active_scan_modes.length > 0
        ? data.active_scan_modes
        : normalizedModes;
      setActiveScanModes(confirmedModes);
      const mode = confirmedModes.join(' + ');
      const successMsg = t('toast_scan_mode_changed').replace('{mode}', String(data.active_scan_mode || mode).toUpperCase());
      setWatchlistFeedback({ type: 'success', message: successMsg });
      return true;
    } catch (err) {
      setActiveScanModes(previousModes);
      const message = err instanceof Error ? err.message : t('error_failed_to_change_scan_mode');
      setWatchlistFeedback({ type: 'error', message });
      console.error("Error updating scan mode:", err);
      return false;
    } finally {
      setWatchlistPendingAction(null);
    }
  };

  const handleRunDeepAnalysis = async (symbol: string) => {
    const requestId = ++analysisRequest.current;
    setDeepAnalysis(deepAnalysisCache.current.get(symbol) ?? null);
    if (deepAnalysisCache.current.has(symbol)) {
      setDeepAnalysis(deepAnalysisCache.current.get(symbol)!);
    }
    setIsDeepAnalyzing(true);
    try {
      const res = await fetch(`/api/coin/${encodeURIComponent(symbol)}/deep-analysis`);
      const data = await res.json();
      if (!res.ok || data.error || data.symbol !== symbol) return;
      deepAnalysisCache.current.set(symbol, data);
      if (activeCoin.current === symbol && requestId === analysisRequest.current) setDeepAnalysis(data);
    } catch (err) {
      console.error(`Deep analysis error for ${symbol}:`, err);
    } finally {
      if (requestId === analysisRequest.current) setIsDeepAnalyzing(false);
    }
  };

  const filteredSignals = signals.filter(sig => {
    const matchesSearch = sig.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          sig.name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesRisk = selectedRiskFilter === 'ALL' || sig.risk_level === selectedRiskFilter;
    const matchesThreshold = sig.probability >= threshold;
    const matchesTelegram = telegramFilter === 'ALL'
      || (telegramFilter === 'SENT' ? sig.telegram_sent === true : sig.telegram_sent !== true);

    let matchesTag = true;
    if (activeFilterTag === 'FIRED') {
      matchesTag = isSignalFired(sig) && sig.validity_hours_left > 0;
    } else if (activeFilterTag === 'ARMED') {
      matchesTag = isSignalArmed(sig) && sig.validity_hours_left > 0;
    } else if (activeFilterTag === 'HOT_RISK') {
      matchesTag = sig.probability >= 0.75 && sig.validity_hours_left > 0;
    } else if (activeFilterTag === 'EXPIRING') {
      matchesTag = sig.validity_hours_left > 0 && sig.validity_hours_left <= 2.0;
    } else if (activeFilterTag === 'VOLUME_SPIKE') {
      matchesTag = Boolean(sig.is_volume_spike || sig.taker_sell_ratio < 0.42);
    } else if (activeFilterTag === 'ANOMALY') {
      matchesTag = Boolean((sig.anomaly_count ?? sig.anomalies?.length ?? 0) > 0);
    } else if (activeFilterTag === 'ACTIVE') {
      matchesTag = sig.validity_hours_left > 0;
    } else if (activeFilterTag === 'EXPIRED') {
      matchesTag = sig.validity_hours_left <= 0;
    } else if (activeFilterTag === 'RESOLVED') {
      matchesTag = sig.hit != null;
    }

    return matchesSearch && matchesRisk && matchesThreshold && matchesTelegram && matchesTag;
  }).sort((a, b) => {
    const aTime = parseSystemDate(a.event_time || a.signal_time)?.getTime() ?? Number.NaN;
    const bTime = parseSystemDate(b.event_time || b.signal_time)?.getTime() ?? Number.NaN;
    const safeTime = (value: number) => Number.isFinite(value) ? value : 0;

    if (signalSort === 'NEWEST') return safeTime(bTime) - safeTime(aTime);
    if (signalSort === 'EXPIRING_SOON') return a.validity_hours_left - b.validity_hours_left;
    if (signalSort === 'LARGEST_DRAWDOWN') return Math.abs(b.target_drawdown || 0) - Math.abs(a.target_drawdown || 0);
    if (signalSort === 'HIGHEST_RISK') {
      const riskRank: Record<SignalItem['risk_level'], number> = {
        CRITICAL: 4,
        HIGH: 3,
        MEDIUM: 2,
        SAFE: 1,
      };
      return riskRank[b.risk_level] - riskRank[a.risk_level] || b.probability - a.probability;
    }
    return b.probability - a.probability;
  });

  const activeScanMode = activeScanModes.join(' + ');

  if (isAuthChecking) {
    return <div className="min-h-screen bg-[#07090E]" aria-label="Checking authentication" />;
  }

  if (!isAuthenticated) {
    return (
      <LockScreen
        initialError={authError}
        onAuthenticated={() => {
          setIsAuthenticated(true);
          setAuthError(null);
          fetchData();
        }}
      />
    );
  }

  const showMobileActionBar = guiVersion === 'v2'
    && Boolean(coinDetail || selectedSignal)
    && mobileTab === 'ANALYSIS';

  return (
    <Suspense fallback={<div className="min-h-screen bg-[#080c14]" aria-label="Loading dashboard" />}>
      <div className="min-h-screen bg-[#080c14] text-slate-100 flex flex-col font-sans">
      
      {/* Slim Top Loading Progress Bar (Fixed, non-shifting) */}
      {loadingStep && (
        <div className="fixed top-0 left-0 right-0 z-[100] h-0.5 bg-gradient-to-r from-amber-500 via-yellow-400 to-amber-600 animate-pulse pointer-events-none shadow-[0_0_8px_rgba(245,158,11,0.6)]" />
      )}

      {/* Header */}
      <Header
        status={status}
        searchTerm={searchTerm}
        setSearchTerm={setSearchTerm}
        selectedRiskFilter={selectedRiskFilter}
        setSelectedRiskFilter={setSelectedRiskFilter}
        threshold={threshold}
        setThreshold={setThreshold}
        onRefresh={fetchData}
        isRefreshing={isRefreshing}
        onOpenGlossary={() => setIsGlossaryOpen(true)}
        onOpenWatchlistModal={() => setIsWatchlistModalOpen(true)}
        onOpenTracking={() => {
          setActiveTab('WATCHLIST');
          if (guiVersion === 'v2') setMobileTab('TRACKING');
        }}
        onOpenCoinSelector={() => setIsCoinSelectorOpen(true)}
        onOpenRadar={() => {
          setActiveTab('RADAR');
          if (guiVersion === 'v2') setMobileTab('RADAR');
        }}
        onLogout={handleLogout}
        trackingCount={trackingItems.filter(item => item.status !== 'CLOSED').length}
        activeScanMode={activeScanMode}
        autoTelegramEnabled={automationSettings.autoTelegramPush}
        onGoHome={() => {
          setActiveTab('DECISION');
          if (guiVersion === 'v2') setMobileTab('ANALYSIS');
          setSelectedSignal(null);
          setSelectedSignalId(null);
          setCoinDetail(null);
          setDeepAnalysis(null);
          window.location.hash = '';
        }}
        availableModels={availableModels}
        selectedModelKey={selectedModelKey}
        onSelectModel={setSelectedModelKey}
        scannerModelId={scannerModelId}
        guiVersion={guiVersion}
        onSelectGuiVersion={handleSelectGuiVersion}
        onOpenModelComparison={() => setIsModelComparisonOpen(true)}
        onOpenUpdates={() => setActiveTab('UPDATES')}
        onOpenSettings={() => setActiveTab('SETTINGS')}
        mobileTab={mobileTab}
        onBackToRadar={() => {
          setMobileTab('RADAR');
          setActiveTab('RADAR');
        }}
        activeCoinSymbol={selectedSignal?.symbol || coinDetail?.symbol || (candidates.length > 0 ? candidates[0].symbol : null)}
        activeCoinPrice={coinDetail?.current_price || selectedSignal?.signal_price || (candidates.length > 0 ? candidates[0].price : null)}
        activeCoinProbability={selectedSignal?.probability || coinDetail?.probability || null}
        activeCoinRisk={selectedSignal?.risk_level || coinDetail?.risk_level || null}
        signalCount={signals.length}
      />

      {/* Main Workspace Layout - Full 12 columns by default (or 9 cols if Action Drawer open) */}
      {trackingItems.some(item => item.notifications?.some(n => !n.read)) && activeTab !== 'WATCHLIST' && <button
        data-testid="tracking-notifications"
        className="mx-auto mt-2 rounded-lg border border-amber-600 bg-amber-950/40 px-4 py-2 text-sm text-amber-200"
        onClick={() => { setActiveTab('WATCHLIST'); if (guiVersion === 'v2') setMobileTab('TRACKING'); }}
      >{language === 'vi' ? 'Thông báo coin theo dõi' : 'Tracked coin notifications'} · {trackingItems.reduce((count, item) => count + (item.notifications?.filter(n => !n.read).length || 0), 0)}</button>}
      {/* Main Workspace Layout - Full 100% Width */}
      <main className={`flex-1 max-w-[1750px] w-full mx-auto p-2.5 sm:p-3.5 block overflow-visible ${
        guiVersion === 'v2'
          ? showMobileActionBar
            ? 'mobile-content-with-actions sm:pb-3.5'
            : 'mobile-content-with-nav sm:pb-3.5'
          : ''
      }`}>
        {/* Main Workspace & Charts */}
        <div className="min-w-0 w-full h-auto lg:min-h-[calc(100vh-120px)] block">
          <MainWorkspace
            signals={signals}
            selectedSignal={selectedSignal}
            coinDetail={coinDetail}
            candidates={candidates}
            isRefreshingCandidates={isRefreshingCandidates}
            candidateRefreshStatus={candidateRefreshStatus}
            onRefreshCandidates={handleRefreshCandidates}
            auditData={auditData}
            marketData={marketData}
            telemetryData={telemetryData}
            onSelectCandidate={handleSelectCandidate}
            onPushTelegram={handlePushTelegram}
            onTriggerManualScan={handleTriggerManualScan}
            isTriggeringScan={isTriggeringScan}
            scanTriggeredSuccess={scanTriggeredSuccess}
            deepAnalysis={deepAnalysis}
            isDeepAnalyzing={isDeepAnalyzing}
            onRunDeepAnalysis={handleRunDeepAnalysis}
            onDismissSignal={handleDismissSignal}
            onAddWatchlist={handleAddManualCoin}
            isSymbolInWatchlist={Boolean(coinDetail?.symbol && manualWatchlist.includes(coinDetail.symbol.toUpperCase()))}
            onAddTracking={handleTrackCurrentCoin}
            onRemoveTrackingSymbol={handleUntrackCurrentCoin}
            isSymbolTracked={Boolean(coinDetail?.symbol && trackingItems.some(item => item.status !== 'CLOSED' && item.symbol === coinDetail.symbol.toUpperCase()))}
            isWatchlistUpdating={watchlistPendingAction !== null}
            trackingItems={trackingItems}
            isTrackingLoading={isTrackingLoading}
            trackingUpdatingId={trackingUpdatingId}
            onRefreshTracking={refreshTrackingWatchlist}
            onSelectTrackingCoin={handleSelectCandidate}
            onUpdateTracking={updateTrackingItem}
            onRemoveTracking={removeTrackingItem}
            activeTab={activeTab}
            setActiveTab={setActiveTab}
            onOpenOrderModal={() => setIsOrderModalOpen(true)}
            onOpenCoinSelector={() => setIsCoinSelectorOpen(true)}
            onSelectSignal={handleSelectSignal}
            onTrackSignal={handleTrackSignal}
            onUntrackSignal={handleUntrackSignal}
            isSignalTracked={(sig) => trackingItems.some(item => item.status !== 'CLOSED' && item.symbol === sig.symbol && (item.source_signal_time === sig.signal_time || !item.source_signal_time))}
            audioAlertEnabled={automationSettings.audioAlertEnabled}
            activeFilterTag={activeFilterTag}
            setActiveFilterTag={setActiveFilterTag}
            signalSort={signalSort}
            setSignalSort={setSignalSort}
            telegramFilter={telegramFilter}
            setTelegramFilter={setTelegramFilter}
            filteredSignals={filteredSignals}
            guiVersion={guiVersion}
            onSelectGuiVersion={handleSelectGuiVersion}
            threshold={threshold}
            setThreshold={setThreshold}
            activeScanModes={activeScanModes}
            onOpenWatchlistModal={() => setIsWatchlistModalOpen(true)}
            onOpenTabHelp={() => setIsTabHelpModalOpen(true)}
            onLogout={handleLogout}
            onOpenAiAssistant={() => setIsFloatingAiAssistantOpen(true)}
            isDevMode={isDevMode}
            setIsDevMode={setIsDevMode}
          />
        </div>
      </main>

      <FloatingAiAssistant
        open={isFloatingAiAssistantOpen}
        onOpenChange={setIsFloatingAiAssistantOpen}
        activeTab={activeTab}
        guiVersion={guiVersion}
        coinDetail={coinDetail}
        selectedSignal={selectedSignal}
        deepAnalysis={deepAnalysis}
        candidatesCount={candidates.length}
        signalCount={signals.length}
        trackingCount={trackingItems.filter(item => item.status !== 'CLOSED').length}
        activeScanModes={activeScanModes}
        selectedModelKey={selectedModelKey}
        scannerModelId={scannerModelId}
        status={status}
        hasMobileActionBar={showMobileActionBar}
      />

      {/* GUI V2 Mobile Bottom Navigation Bar */}
      {guiVersion === 'v2' && (
        <MobileBottomNav
          activeTab={mobileTab}
          onSelectTab={(tab) => {
            setMobileTab(tab);
            if (tab === 'RADAR') {
              setActiveTab('RADAR');
            } else if (tab === 'ANALYSIS') {
              setActiveTab('DECISION');
            } else if (tab === 'ORDER') {
              setIsOrderModalOpen(true);
            } else if (tab === 'TRACKING') {
              setActiveTab('WATCHLIST');
            } else if (tab === 'TOOLS') {
              if (activeTab === 'DECISION' || activeTab === 'WATCHLIST' || activeTab === 'RADAR') {
                setActiveTab('RANKING');
              }
            }
          }}
          signalCount={filteredSignals.length}
          selectedSymbol={coinDetail?.symbol || selectedSignal?.symbol || null}
          trackingCount={trackingItems.filter(item => item.status !== 'CLOSED').length}
        />
      )}

      {/* GUI V2 Sticky Action Bar (Mobile when coin selected) */}
      {showMobileActionBar && (
        <StickyActionBar
          symbol={coinDetail?.symbol || selectedSignal?.symbol || ''}
          currentPrice={coinDetail?.current_price || selectedSignal?.signal_price || 0}
          probability={deepAnalysis?.calibrated_probability ?? selectedSignal?.probability ?? coinDetail?.probability}
          riskLevel={selectedSignal?.risk_level || coinDetail?.risk_level}
          onOpenOrderModal={() => setIsOrderModalOpen(true)}
          onTrackPosition={handleTrackCurrentCoin}
          onUntrackPosition={handleUntrackCurrentCoin}
          isSymbolTracked={Boolean((coinDetail?.symbol || selectedSignal?.symbol) && trackingItems.some(item => item.status !== 'CLOSED' && item.symbol === (coinDetail?.symbol || selectedSignal?.symbol)?.toUpperCase()))}
          isTrackingLoading={isTrackingLoading}
          onPushTelegram={() => selectedSignal && handlePushTelegram(selectedSignal)}
        />
      )}

      {/* GUI V2 Order Execution & Risk Management Modal */}
      {(coinDetail || selectedSignal) && (
        <OrderExecutionModal
          isOpen={isOrderModalOpen}
          onClose={() => setIsOrderModalOpen(false)}
          symbol={coinDetail?.symbol || selectedSignal?.symbol || ''}
          currentPrice={coinDetail?.current_price || selectedSignal?.signal_price || 0}
          signalPrice={selectedSignal?.signal_price}
          targetPrice={coinDetail?.target_price || selectedSignal?.target_price}
          peakPrice={deepAnalysis?.pump_analysis?.peak_price}
          probability={deepAnalysis?.calibrated_probability ?? selectedSignal?.probability ?? coinDetail?.probability}
          riskLevel={selectedSignal?.risk_level || coinDetail?.risk_level}
          onTrackPosition={handleTrackCurrentCoin}
          onUntrackPosition={handleUntrackCurrentCoin}
          isSymbolTracked={Boolean((coinDetail?.symbol || selectedSignal?.symbol) && trackingItems.some(item => item.status !== 'CLOSED' && item.symbol === (coinDetail?.symbol || selectedSignal?.symbol)?.toUpperCase()))}
          isTrackingLoading={isTrackingLoading}
          tradeSetup={selectedSignal?.trade_setup}
        />
      )}

      {/* Binance Futures Style Coin Selector Popover/Modal */}
      <CoinSelectorModal
        isOpen={isCoinSelectorOpen}
        onClose={() => setIsCoinSelectorOpen(false)}
        currentSymbol={coinDetail?.symbol || selectedSignal?.symbol || (candidates.length > 0 ? candidates[0].symbol : '')}
        onSelectCoin={handleSelectCandidate}
        signals={signals}
        candidates={candidates}
        marketData={marketData}
        manualWatchlist={manualWatchlist}
        trackingItems={trackingItems}
        onToggleWatchlist={async (sym) => {
          if (manualWatchlist.includes(sym)) {
            return await handleRemoveManualCoin(sym);
          } else {
            return await handleAddManualCoin(sym);
          }
        }}
      />

      {/* Glossary Modal */}
      <GlossaryModal
        isOpen={isGlossaryOpen}
        onClose={() => setIsGlossaryOpen(false)}
      />

      {/* A/B Engine Comparison Benchmark Modal */}
      <ModelComparisonModal
        isOpen={isModelComparisonOpen}
        onClose={() => setIsModelComparisonOpen(false)}
      />

      {/* Tab Mechanism & Operations Help Modal */}
      <TabHelpModal
        isOpen={isTabHelpModalOpen}
        onClose={() => setIsTabHelpModalOpen(false)}
        activeTab={activeTab}
      />
      {/* Watchlist Preset Modal */}
      <WatchlistModal
        isOpen={isWatchlistModalOpen}
        onClose={() => setIsWatchlistModalOpen(false)}
        activeScanMode={activeScanMode}
        activeScanModes={activeScanModes}
        setActiveScanModes={handleChangeScanModes}
        manualWatchlist={manualWatchlist}
        onAddManualCoin={handleAddManualCoin}
        onRemoveManualCoin={handleRemoveManualCoin}
        presets={watchlistPresets}
        onSelectCoin={handleSelectCandidate}
        pendingAction={watchlistPendingAction}
        feedback={watchlistFeedback}
      />

      {watchlistFeedback && !isWatchlistModalOpen && (
        <div
          role="status"
          className={`fixed bottom-4 left-3 right-3 sm:left-auto sm:right-4 sm:max-w-sm z-[60] rounded-xl border px-4 py-3 text-xs shadow-2xl backdrop-blur-md ${
            watchlistFeedback.type === 'success'
              ? 'border-emerald-500/40 bg-emerald-950/95 text-emerald-200'
              : 'border-red-500/40 bg-red-950/95 text-red-200'
          }`}
        >
          {watchlistFeedback.message}
        </div>
      )}

      {telegramSentSuccess && (
        <div
          role="status"
          className="fixed bottom-4 left-3 right-3 sm:left-auto sm:right-4 sm:max-w-sm z-[60] rounded-xl border border-emerald-500/40 bg-emerald-950/95 text-emerald-200 px-4 py-3 text-xs shadow-2xl backdrop-blur-md"
        >
          {telegramSentSuccess}
        </div>
      )}

      </div>
    </Suspense>
  );
}

export default App;
