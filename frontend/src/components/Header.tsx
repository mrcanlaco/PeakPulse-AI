import React, { useState, useRef, useEffect } from 'react';
import type { SystemStatus, ModelChoice } from '../types';
import type { MobileTabType } from './v2/MobileBottomNav';
import { useTranslation, LANGUAGES, type LanguageOption } from '../i18n/LanguageContext';
import {
  ChevronDown,
  ChevronLeft,
  Cpu,
  Eye,
  Globe,
  HelpCircle,
  RefreshCw,
  Search,
  Sliders,
  Target,
  Check,
  Sparkles,
  Scale,
  GitPullRequest,
  Settings,
  Radio,
  Lock,
} from 'lucide-react';
import {
  getRiskLabel,
  getScanModeLabel,
  
  
} from '../i18n/translations';
import { PwaInstallButton } from './PwaInstallButton';

interface HeaderProps {
  status: SystemStatus | null;
  searchTerm: string;
  setSearchTerm: (val: string) => void;
  selectedRiskFilter: string;
  setSelectedRiskFilter: (val: string) => void;
  threshold: number;
  setThreshold: (val: number) => void;
  onRefresh: () => void;
  isRefreshing: boolean;
  onOpenGlossary: () => void;
  onOpenWatchlistModal: () => void;
  onOpenTracking: () => void;
  onOpenModelComparison?: () => void;
  onOpenUpdates?: () => void;
  onOpenSettings?: () => void;
  onOpenCoinSelector?: () => void;
  onOpenRadar?: () => void;
  onLogout?: () => void;
  trackingCount: number;
  activeScanMode: string;
  autoTelegramEnabled: boolean;
  onGoHome?: () => void;
  availableModels?: ModelChoice[];
  selectedModelKey?: string;
  onSelectModel?: (key: string) => void;
  scannerModelId?: string;
  guiVersion?: 'v1' | 'v2';
  onSelectGuiVersion?: (version: 'v1' | 'v2') => void;
  mobileTab?: MobileTabType;
  onBackToRadar?: () => void;
  activeCoinSymbol?: string | null;
  activeCoinPrice?: number | null;
  activeCoinProbability?: number | null;
  activeCoinRisk?: string | null;
  signalCount?: number;
}

export const Header: React.FC<HeaderProps> = ({
  status,
  searchTerm: _searchTerm,
  setSearchTerm: _setSearchTerm,
  selectedRiskFilter,
  setSelectedRiskFilter,
  threshold,
  setThreshold,
  onRefresh,
  isRefreshing,
  onOpenGlossary,
  onOpenWatchlistModal,
  onOpenTracking,
  onOpenModelComparison,
  onOpenUpdates,
  onOpenSettings,
  onOpenCoinSelector,
  onOpenRadar,
  onLogout,
  trackingCount,
  activeScanMode,
  autoTelegramEnabled: _autoTelegramEnabled,
  onGoHome,
  guiVersion = 'v2',
  onSelectGuiVersion,
  mobileTab = 'RADAR',
  onBackToRadar,
  activeCoinSymbol = null,
  activeCoinPrice = null,
  activeCoinProbability = null,
  activeCoinRisk: _activeCoinRisk = null,
  signalCount = 0,
}) => {
  const { language, setLanguage, t } = useTranslation();
    const [langDropdownOpen, setLangDropdownOpen] = useState(false);
  const [moreToolsDropdownOpen, setMoreToolsDropdownOpen] = useState(false);
  const [updateAvailable, setUpdateAvailable] = useState(false);
  const [commitsBehind, setCommitsBehind] = useState(0);

  const searchInputRef = useRef<HTMLInputElement>(null);

  const isMobileAnalysis = guiVersion === 'v2' && mobileTab === 'ANALYSIS' && Boolean(activeCoinSymbol);

  const formatPrice = (p?: number | null) => {
    if (p == null || p <= 0) return '—';
    if (p < 0.001) return p.toFixed(6);
    if (p < 1) return p.toFixed(5);
    if (p < 10) return p.toFixed(4);
    return p.toFixed(2);
  };

  const probPct = activeCoinProbability != null ? (activeCoinProbability <= 1 ? activeCoinProbability * 100 : activeCoinProbability) : null;

  useEffect(() => {
    let isMounted = true;
    const checkUpdate = async () => {
      try {
        const res = await fetch('/api/system/update-status');
        if (res.ok) {
          const json = await res.json();
          if (isMounted) {
            setUpdateAvailable(Boolean(json.update_available));
            setCommitsBehind(Number(json.commits_behind || 0));
          }
        }
      } catch {
        // silent
      }
    };
    checkUpdate();
    const interval = setInterval(checkUpdate, 60000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Keyboard shortcut '/' to focus search input
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement).tagName)) return;
      if (e.key === '/' || (e.ctrlKey && e.key === 'k') || (e.metaKey && e.key === 'k')) {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

      const currentLangObj = LANGUAGES.find((l) => l.code === language) || LANGUAGES[0];

  const scanLabel = activeScanMode
    .split(' + ')
    .map((mode) => getScanModeLabel(mode, language))
    .join(' + ');

  const watchlistButton = (
    <button
      type="button"
      onClick={onOpenWatchlistModal}
      className="inline-flex max-w-[120px] lg:max-w-[160px] items-center gap-1.5 rounded-lg bg-gradient-to-r from-amber-500 to-amber-600 px-2 py-1 text-xs font-bold text-slate-950 shadow-md shadow-amber-500/15 transition hover:from-amber-400 hover:to-amber-500 active:scale-95 shrink-0"
      title={t('select_coins_to_scan')}
    >
      <Target className="h-3.5 w-3.5 shrink-0 stroke-[2.5]" />
      <span className="hidden sm:inline truncate whitespace-nowrap text-[11px] font-mono font-bold uppercase">
        {scanLabel}
      </span>
    </button>
  );

  return (
    <header className="sticky top-0 z-50 border-b border-slate-800/90 bg-slate-950/95 px-3 py-2 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1750px] flex-col gap-2">
        {/* =========================================================
            1. MOBILE VIEW (under md)
        ========================================================= */}
        {isMobileAnalysis ? (
          /* Mobile Coin Analysis Bar */
          <div className="flex md:hidden items-center justify-between gap-2 min-w-0">
            {/* Back to Radar Button */}
            <button
              type="button"
              onClick={onBackToRadar || onGoHome}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-amber-500/15 border border-amber-500/40 text-amber-300 hover:bg-amber-500/25 active:scale-95 transition text-xs font-bold shrink-0 shadow-sm"
              title={t('mobile_nav_radar')}
            >
              <ChevronLeft className="w-4 h-4 text-amber-400 stroke-[2.5]" />
              <span>{t('mobile_nav_radar')}</span>
              {signalCount > 0 && (
                <span className="px-1 min-w-[15px] h-[15px] flex items-center justify-center text-[9px] font-mono font-bold rounded-full bg-red-500 text-white ml-0.5">
                  {signalCount}
                </span>
              )}
            </button>

            {/* Center: Coin Ticker & Live Price & AI Prob Badge */}
            <button
              type="button"
              onClick={onOpenCoinSelector}
              className="flex items-center gap-1.5 min-w-0 justify-center flex-1 py-1 px-2 rounded-lg bg-slate-900/90 border border-slate-800 hover:border-amber-500/40 active:scale-95 transition"
              title={t('coin_selector_title')}
            >
              <span className="font-black text-amber-400 font-mono text-sm tracking-tight truncate">
                {activeCoinSymbol}
              </span>
              <ChevronDown className="w-3 h-3 text-amber-400" />
              <span className="text-xs font-mono font-bold text-slate-100 shrink-0">
                ${formatPrice(activeCoinPrice)}
              </span>
              {probPct !== null && (
                <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold font-mono border shrink-0 ${
                  probPct >= 70
                    ? 'bg-red-950 text-red-300 border-red-800'
                    : probPct >= 50
                    ? 'bg-amber-950 text-amber-300 border-amber-800'
                    : 'bg-slate-800 text-slate-300 border-slate-700'
                }`}>
                  {probPct.toFixed(0)}%
                </span>
              )}
            </button>

            {/* Right: Quick actions (Refresh, Language) */}
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                type="button"
                onClick={onRefresh}
                disabled={isRefreshing}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-700 bg-slate-800 text-slate-300 active:scale-95 transition disabled:opacity-50"
                title={t('refresh')}
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin text-amber-400' : ''}`} />
              </button>

              {/* Language Selector */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setLangDropdownOpen((o) => !o)}
                  className="inline-flex h-8 items-center justify-center gap-1 rounded-lg border border-amber-500/30 bg-slate-800 px-2 text-xs font-bold text-amber-300 active:scale-95"
                  title={t('language_toggle')}
                >
                  <span className="text-sm leading-none">{currentLangObj.flag}</span>
                </button>
                {langDropdownOpen && (
                  <>
                    <button
                      type="button"
                      aria-label="Close language dropdown"
                      className="fixed inset-0 z-40 h-full w-full cursor-default"
                      onClick={() => setLangDropdownOpen(false)}
                    />
                    <div className="absolute right-0 top-full z-50 mt-1 w-40 rounded-xl border border-slate-700 bg-slate-900 p-1.5 shadow-2xl backdrop-blur-md">
                      {LANGUAGES.map((item: LanguageOption) => (
                        <button
                          type="button"
                          key={item.code}
                          onClick={() => {
                            setLanguage(item.code);
                            setLangDropdownOpen(false);
                          }}
                          className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-xs font-semibold transition ${
                            language === item.code
                              ? 'bg-amber-500/20 text-amber-300 font-bold border border-amber-500/40'
                              : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <span className="text-base leading-none">{item.flag}</span>
                            <span>{item.nativeLabel}</span>
                          </div>
                          {language === item.code && <Check className="w-3.5 h-3.5 text-amber-400" />}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        ) : (
          /* Mobile Radar View Header (When browsing radar signals) */
          <div className="flex md:hidden items-center justify-between gap-2 min-w-0">
            <div
              role="button"
              tabIndex={0}
              onClick={onGoHome}
              className="flex items-center gap-2 cursor-pointer shrink-0"
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500 to-amber-700 text-sm font-bold text-slate-950 shadow-md shadow-amber-500/20">
                🪙
              </div>
              <div>
                <div className="text-[9px] font-semibold uppercase tracking-wider text-amber-400/80 leading-none">
                  {t('app_subtitle')}
                </div>
                <h1 className="text-sm font-black tracking-wide text-amber-300 leading-tight">
                  RADAR
                </h1>
              </div>
            </div>

            <div className="flex items-center gap-1.5 shrink-0">
              {watchlistButton}
              {/* Language Selector */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setLangDropdownOpen((o) => !o)}
                  className="inline-flex h-8 items-center justify-center gap-1 rounded-lg border border-amber-500/30 bg-slate-800 px-2 text-xs font-bold text-amber-300 active:scale-95"
                  title={t('language_toggle')}
                >
                  <span className="text-sm leading-none">{currentLangObj.flag}</span>
                </button>
                {langDropdownOpen && (
                  <>
                    <button
                      type="button"
                      aria-label="Close language dropdown"
                      className="fixed inset-0 z-40 h-full w-full cursor-default"
                      onClick={() => setLangDropdownOpen(false)}
                    />
                    <div className="absolute right-0 top-full z-50 mt-1 w-40 rounded-xl border border-slate-700 bg-slate-900 p-1.5 shadow-2xl backdrop-blur-md">
                      {LANGUAGES.map((item: LanguageOption) => (
                        <button
                          type="button"
                          key={item.code}
                          onClick={() => {
                            setLanguage(item.code);
                            setLangDropdownOpen(false);
                          }}
                          className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-xs font-semibold transition ${
                            language === item.code
                              ? 'bg-amber-500/20 text-amber-300 font-bold border border-amber-500/40'
                              : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <span className="text-base leading-none">{item.flag}</span>
                            <span>{item.nativeLabel}</span>
                          </div>
                          {language === item.code && <Check className="w-3.5 h-3.5 text-amber-400" />}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
              <button
                type="button"
                onClick={onRefresh}
                disabled={isRefreshing}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-700 bg-slate-800 text-slate-300 active:scale-95"
                title={t('refresh')}
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin text-amber-400' : ''}`} />
              </button>
            </div>
          </div>
        )}

        {/* =========================================================
            2. DESKTOP UNIFIED 1-ROW PRO HEADER (md and up)
        ========================================================= */}
        <div className="hidden md:flex items-center justify-between gap-2 xl:gap-3 min-w-0">
          {/* Left Zone: Brand + Coin Selector + AI Model + Scan Preset */}
          <div className="flex items-center gap-2 min-w-0 shrink">
            {/* Brand Logo & Name */}
            <div
              role="button"
              tabIndex={0}
              onClick={onGoHome}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onGoHome?.();
                }
              }}
              className="group flex items-center gap-2 cursor-pointer select-none shrink-0"
              title={t('go_home')}
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-amber-500 to-amber-700 text-sm font-bold text-slate-950 shadow-md shadow-amber-500/20 group-hover:scale-105 transition">
                🪙
              </div>
              <div className="hidden xl:block">
                <div className="text-[8px] font-semibold uppercase tracking-[0.16em] text-amber-400/80 leading-none">
                  {t('app_subtitle')}
                </div>
                <h1 className="text-sm font-black tracking-wide text-amber-300 group-hover:text-amber-200 leading-tight">
                  RADAR
                </h1>
              </div>
            </div>

            {/* Binance-style Coin Selector Trigger Button */}
            {activeCoinSymbol && (
              <button
                type="button"
                onClick={onOpenCoinSelector}
                className="inline-flex items-center gap-1.5 rounded-xl border border-amber-500/30 bg-slate-900/90 hover:bg-slate-800 hover:border-amber-400 px-2.5 py-1 text-xs font-bold text-slate-100 shadow-md active:scale-95 transition group cursor-pointer shrink-0"
                title={t('coin_selector_title')}
              >
                <div className="flex items-center gap-1">
                  <span className="font-black text-amber-400 font-mono text-sm tracking-tight group-hover:text-amber-300">
                    {activeCoinSymbol}
                  </span>
                  <span className="hidden xl:inline text-[9px] px-1 py-0.2 rounded bg-slate-800 text-slate-400 font-mono">
                    {t('coin_badge_perpetual')}
                  </span>
                  <ChevronDown className="w-3.5 h-3.5 text-amber-400 group-hover:translate-y-0.5 transition" />
                </div>
                <div className="h-3.5 w-px bg-slate-700 mx-0.5" />
                <span className="font-mono text-xs font-bold text-white">
                  ${formatPrice(activeCoinPrice)}
                </span>
                {probPct !== null && (
                  <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold font-mono border ${
                    probPct >= 70
                      ? 'bg-red-950 text-red-300 border-red-800'
                      : probPct >= 50
                      ? 'bg-amber-950 text-amber-300 border-amber-800'
                      : 'bg-slate-800 text-slate-300 border-slate-700'
                  }`}>
                    {probPct.toFixed(0)}%
                  </span>
                )}
              </button>
            )}

            {/* AI Model Selector */}
            <div className="relative shrink-0">
              <div
                className="inline-flex max-w-[140px] lg:max-w-[195px] items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-[11px] font-bold text-emerald-300 cursor-default shadow-sm"
                title={language === 'en' ? 'Official 2-Tier Engine: Fibo Short v4.0.21 (Primary Actionable & Telegram) + V3.1 ML (Early UI Radar)' : language === 'zh' ? '双层引擎：Fibo Short v4.0.21（主交易信号）+ V3.1（早期雷达）' : language === 'ko' ? '2계층 엔진: Fibo Short v4.0.21 (공식 신호) + V3.1 (조기 레이더)' : 'Kiến trúc 2 tầng: Fibo Short v4.0.21 (Tín hiệu hành động & Telegram chính thức) + V3.1 ML (Radar quét sớm trên UI)'}
              >
                <Cpu className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
                <span className="truncate">Fibo v4.0 · Radar V3.1</span>
                <span className="text-emerald-400 animate-pulse" title={t('online_247')}>●</span>
              </div>
            </div>

            {/* Target Scan Watchlist Button */}
            {watchlistButton}
          </div>

          {/* Quick Search Trigger Button (Opens CoinSelectorModal) */}
          <div className="hidden xl:flex items-center justify-center min-w-0 shrink">
            <button
              type="button"
              onClick={onOpenCoinSelector}
              className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-slate-900/80 hover:bg-slate-800 border border-slate-800 hover:border-amber-500/40 text-slate-400 hover:text-slate-200 text-xs font-mono transition cursor-pointer"
              title={t('search_placeholder')}
            >
              <Search className="w-3.5 h-3.5 text-amber-400" />
              <span className="truncate max-w-[140px]">{t('search_placeholder')}</span>
              <kbd className="px-1.5 py-0.2 text-[9px] bg-slate-800 border border-slate-700 rounded text-slate-400 font-sans font-semibold">
                /
              </kbd>
            </button>
          </div>

          {/* Right Zone: Primary Actions + More Tools Menu + Language */}
          <div className="flex items-center gap-1.5 shrink-0">
            {/* Live 24/7 Status Badge */}
            {(status?.scanner_status === 'ONLINE' || status?.scanner_status === 'ACTIVE') && (
              <span className="hidden 2xl:inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                </span>
                <span>Live 24/7</span>
              </span>
            )}

            {/* Radar Tab Quick Button */}
            {onOpenRadar && (
              <button
                type="button"
                onClick={onOpenRadar}
                className="relative inline-flex h-8 items-center justify-center gap-1.5 rounded-lg border border-red-500/40 bg-red-500/15 px-2.5 text-xs font-bold text-red-300 shadow-sm transition hover:bg-red-500/25 active:scale-95 shrink-0"
                title={t('ws_tab_radar')}
              >
                <Radio className="h-3.5 w-3.5 text-red-400" />
                <span className="hidden xl:inline">{t('ws_tab_radar')}</span>
                {signalCount > 0 && (
                  <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-black text-white animate-pulse">
                    {signalCount}
                  </span>
                )}
              </button>
            )}

            {/* Tracking Watchlist Quick Button */}
            <button
              type="button"
              onClick={onOpenTracking}
              data-testid="open-tracking"
              className="relative inline-flex h-8 items-center justify-center gap-1.5 rounded-lg border border-violet-500/40 bg-violet-950/40 px-2.5 text-xs font-bold text-violet-300 shadow-sm transition hover:bg-violet-900/60 hover:border-violet-500 active:scale-95 shrink-0"
              title="Xem danh sách vị thế đang mở và quản lý PnL / SL / TP"
            >
              <Eye className="h-3.5 w-3.5 text-violet-400" />
              <span>{t('ws_tab_tracking')}</span>
              {trackingCount > 0 && (
                <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-violet-600 px-1 text-[10px] font-black text-white shadow-sm">
                  {trackingCount}
                </span>
              )}
            </button>
            {/* Refresh Button */}
            <button
              type="button"
              onClick={onRefresh}
              disabled={isRefreshing}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-700 bg-slate-800 text-slate-300 transition hover:bg-slate-700 active:scale-95 disabled:opacity-50 shrink-0"
              title={t('refresh')}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin text-amber-400' : ''}`} />
            </button>

            {/* More Tools & System Settings Dropdown */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setMoreToolsDropdownOpen((v) => !v)}
                className={`inline-flex h-8 items-center justify-center gap-1 rounded-lg border px-2 text-xs font-bold shadow-sm transition active:scale-95 ${
                  updateAvailable
                    ? 'border-emerald-500/60 bg-emerald-950/60 text-emerald-300 hover:bg-emerald-900/60'
                    : 'border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700'
                }`}
                title="Công cụ & Hệ thống"
              >
                <Settings className={`w-3.5 h-3.5 ${updateAvailable ? 'text-emerald-400' : 'text-slate-400'}`} />
                {updateAvailable && (
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                )}
                <ChevronDown className="w-2.5 h-2.5 text-slate-400" />
              </button>

              {moreToolsDropdownOpen && (
                <>
                  <button
                    type="button"
                    aria-label="Close tools dropdown"
                    className="fixed inset-0 z-40 h-full w-full cursor-default"
                    onClick={() => setMoreToolsDropdownOpen(false)}
                  />
                  <div className="absolute right-0 top-full z-50 mt-1.5 w-60 rounded-xl border border-slate-700 bg-slate-900/95 p-1.5 shadow-2xl backdrop-blur-md divide-y divide-slate-800">
                    <div className="py-1 space-y-0.5">
                      {/* Version & Updates */}
                      {onOpenUpdates && (
                        <button
                          type="button"
                          onClick={() => {
                            onOpenUpdates();
                            setMoreToolsDropdownOpen(false);
                          }}
                          className="flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800 hover:text-white transition"
                        >
                          <div className="flex items-center gap-2">
                            <GitPullRequest className={`w-3.5 h-3.5 ${updateAvailable ? 'text-emerald-400' : 'text-amber-400'}`} />
                            <span>{updateAvailable ? `Cập nhật (${commitsBehind})` : 'Nhật ký phiên bản'}</span>
                          </div>
                          {updateAvailable && (
                            <span className="text-[9px] bg-emerald-950 text-emerald-300 border border-emerald-700 px-1.5 py-0.2 rounded font-bold">
                              Mới
                            </span>
                          )}
                        </button>
                      )}

                      {/* A/B Engine Comparison */}
                      {onOpenModelComparison && (
                        <button
                          type="button"
                          onClick={() => {
                            onOpenModelComparison();
                            setMoreToolsDropdownOpen(false);
                          }}
                          className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800 hover:text-white transition"
                        >
                          <Scale className="w-3.5 h-3.5 text-violet-400" />
                          <span>So sánh A/B Engine</span>
                        </button>
                      )}

                      {/* Glossary */}
                      <button
                        type="button"
                        onClick={() => {
                          onOpenGlossary();
                          setMoreToolsDropdownOpen(false);
                        }}
                        className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800 hover:text-white transition"
                      >
                        <HelpCircle className="w-3.5 h-3.5 text-amber-400" />
                        <span>{t('glossary')}</span>
                      </button>

                      {/* Settings & LLM Config */}
                      {onOpenSettings && (
                        <button
                          type="button"
                          onClick={() => {
                            onOpenSettings();
                            setMoreToolsDropdownOpen(false);
                          }}
                          className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800 hover:text-white transition"
                        >
                          <Settings className="w-3.5 h-3.5 text-amber-400" />
                          <span>Cài đặt & LLM API</span>
                        </button>
                      )}
                    </div>

                    {/* Quick Filters (Threshold & Risk) */}
                    <div className="py-2 px-2.5 space-y-2 bg-slate-950/40 rounded-lg my-1">
                      <div className="text-[10px] font-bold uppercase text-slate-400">
                        {t('settings')}
                      </div>
                      <div className="flex items-center justify-between gap-2 text-xs">
                        <span className="text-slate-300 font-medium flex items-center gap-1">
                          <Sliders className="w-3 h-3 text-amber-400 shrink-0" />
                          <span>Ngưỡng cảnh báo:</span>
                        </span>
                        <div className="flex items-center gap-1.5 font-mono text-amber-400 font-bold text-[11px]">
                          <span>{(threshold * 100).toFixed(0)}%</span>
                          <input
                            type="range"
                            min="0.10"
                            max="0.85"
                            step="0.05"
                            value={threshold}
                            onChange={(e) => setThreshold(parseFloat(e.target.value))}
                            className="w-16 cursor-pointer accent-amber-500"
                            aria-label="Alert threshold"
                          />
                        </div>
                      </div>
                      <div className="flex items-center justify-between gap-2 text-xs">
                        <span className="text-slate-300 font-medium">{t('ranking_col_risk_tier')}:</span>
                        <select
                          value={selectedRiskFilter}
                          onChange={(e) => setSelectedRiskFilter(e.target.value)}
                          className="bg-slate-800 border border-slate-700 rounded px-1.5 py-0.5 text-[11px] font-mono text-slate-200 focus:outline-none focus:border-amber-500 cursor-pointer"
                          aria-label="Filter conviction level"
                        >
                          <option value="ALL">{t('risk_all')}</option>
                          <option value="CRITICAL">🟣 {getRiskLabel('CRITICAL', language)}</option>
                          <option value="HIGH">🟠 {getRiskLabel('HIGH', language)}</option>
                          <option value="MEDIUM">🟡 {getRiskLabel('MEDIUM', language)}</option>
                          <option value="SAFE">⚪ {getRiskLabel('SAFE', language)}</option>
                        </select>
                      </div>
                    </div>

                    <div className="py-1 space-y-0.5">
                      {/* GUI Version Switcher */}
                      {onSelectGuiVersion && (
                        <button
                          type="button"
                          onClick={() => {
                            onSelectGuiVersion(guiVersion === 'v1' ? 'v2' : 'v1');
                            setMoreToolsDropdownOpen(false);
                          }}
                          className="flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800 hover:text-white transition"
                        >
                          <div className="flex items-center gap-2">
                            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                            <span>Giao diện: <strong>{guiVersion === 'v2' ? 'V2 Pro' : 'V1 Classic'}</strong></span>
                          </div>
                        </button>
                      )}

                      {/* Lock / Logout */}
                      {onLogout && (
                        <button
                          type="button"
                          onClick={() => {
                            onLogout();
                            setMoreToolsDropdownOpen(false);
                          }}
                          className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs text-red-400 hover:bg-red-950/40 hover:text-red-300 transition"
                        >
                          <Lock className="w-3.5 h-3.5 text-red-400" />
                          <span>{t('auth_logout')}</span>
                        </button>
                      )}

                      {/* PWA Install */}
                      <div className="px-1 py-1">
                        <PwaInstallButton />
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>

            {/* 4-Language Dropdown */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setLangDropdownOpen((o) => !o)}
                className="inline-flex h-8 items-center justify-center gap-1 rounded-lg border border-amber-500/30 bg-slate-800 px-2 text-xs font-bold text-amber-300 shadow-sm transition hover:border-amber-400 hover:bg-slate-700 active:scale-95"
                title={t('language_toggle')}
              >
                <Globe className="h-3 w-3 text-amber-400" />
                <span className="text-xs">{currentLangObj.flag}</span>
                <span className="font-mono text-[10px] uppercase font-bold">{currentLangObj.code}</span>
                <ChevronDown className="h-2.5 w-2.5 text-slate-400" />
              </button>

              {langDropdownOpen && (
                <>
                  <button
                    type="button"
                    aria-label="Close language dropdown"
                    className="fixed inset-0 z-40 h-full w-full cursor-default"
                    onClick={() => setLangDropdownOpen(false)}
                  />
                  <div className="absolute right-0 top-full z-50 mt-1 w-44 rounded-xl border border-slate-700 bg-slate-900 p-1.5 shadow-2xl backdrop-blur-md">
                    <div className="mb-1 border-b border-slate-800 px-2.5 py-1 text-[10px] font-bold uppercase text-slate-400 flex items-center gap-1.5">
                      <Globe className="w-3 h-3 text-amber-400" />
                      {t('language_toggle')}
                    </div>
                    {LANGUAGES.map((item: LanguageOption) => (
                      <button
                        type="button"
                        key={item.code}
                        onClick={() => {
                          setLanguage(item.code);
                          setLangDropdownOpen(false);
                        }}
                        className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-xs font-semibold transition ${
                          language === item.code
                            ? 'bg-amber-500/20 text-amber-300 font-bold border border-amber-500/40'
                            : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-base leading-none">{item.flag}</span>
                          <span>{item.nativeLabel}</span>
                        </div>
                        {language === item.code && <Check className="w-3.5 h-3.5 text-amber-400" />}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>

            {/* Top Bar Lock / Logout Button */}
            {onLogout && (
              <button
                type="button"
                onClick={onLogout}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-700/80 bg-slate-800 text-slate-400 shadow-sm transition hover:border-red-500/50 hover:bg-red-950/30 hover:text-red-400 active:scale-95 cursor-pointer"
                title={t('auth_logout')}
                aria-label={t('auth_logout')}
              >
                <Lock className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;

