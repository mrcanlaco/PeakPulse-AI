import React, { useMemo } from 'react';
import {
  Activity,
  Target,
  BarChart3,
  Layers,
  FlaskConical,
  ShieldCheck,
  Lock,
  Cpu,
  Radio,
  Clock,
  GitPullRequest,
  Zap,
  Settings,
  HelpCircle,
  Brain,
  Wallet,
  BookOpen,
  Gauge,
} from 'lucide-react';
import { CoinLink } from './CoinLink';
import { useTranslation } from '../i18n/LanguageContext';
import type { SignalItem } from '../types';
import type { MobileTabType } from './v2/MobileBottomNav';

export type WorkspaceTab =
  // 1. Tín hiệu (SIGNALS) — Tín hiệu thực tế & chi tiết phương pháp giao dịch
  | 'FIBO_SHORT'
  | 'DECISION'
  | 'MODELS'
  | 'RADAR'
  | 'RANKING'
  | 'MARKET'
  // 2. Shadow Live (SHADOW_LIVE) — Các version & các bản cải tiến giả lập thời gian thực
  | 'PAPER_OOS'
  | 'SHADOW_COMPARE'
  | 'FORWARD'
  | 'BACKTEST'
  | 'MULTISCAN'
  // 3. Live (LIVE) — Bản chạy Live nối với tài khoản thực Binance Futures
  | 'LIVE_ACCOUNT'
  | 'WATCHLIST'
  // 4. Hệ thống (SYSTEM) — Vận hành, hạ tầng, nhật ký & cài đặt
  | 'SETTINGS'
  | 'TELEMETRY'
  | 'HISTORY'
  | 'UPDATES'
  | 'AUDIT';

export type TabCategory = 'SIGNALS' | 'SHADOW_LIVE' | 'LIVE' | 'SYSTEM';

interface TabItemConfig {
  id: WorkspaceTab;
  labelKey: string;
  descKey?: string;
  icon: React.ElementType;
  badge?: number | string | null;
  pulse?: boolean;
  category: TabCategory;
}

interface PillarConfig {
  id: TabCategory;
  testId: string;
  labelVi: string;
  labelEn: string;
  labelZh: string;
  labelKo: string;
  subVi: string;
  subEn: string;
  subZh: string;
  subKo: string;
  icon: React.ElementType;
  defaultTab: WorkspaceTab;
  badge?: number | string | null;
  badgeCls?: string;
  pulseDot?: boolean;
  activeCls: string;
}

interface WorkspaceTabBarProps {
  activeTab: WorkspaceTab;
  setActiveTab: (tab: WorkspaceTab) => void;
  selectedSignal: SignalItem | null;
  activeCoinSymbol?: string | null;
  onSelectCandidate: (symbol: string) => void;
  trackingCount: number;
  candidateCount: number;
  signalCount?: number;
  fiboActionableCount?: number;
  fiboArmedCount?: number;
  fiboShadowCount?: number;
  isTelemetryActive?: boolean;
  guiVersion?: 'v1' | 'v2';
  mobileTab?: MobileTabType;
  onOpenTabHelp?: (tab?: WorkspaceTab) => void;
  isDevMode?: boolean;
}

export function getCategoryForTab(tab: WorkspaceTab): TabCategory {
  switch (tab) {
    case 'FIBO_SHORT':
    case 'DECISION':
    case 'MODELS':
    case 'RADAR':
    case 'RANKING':
    case 'MARKET':
      return 'SIGNALS';
    case 'PAPER_OOS':
    case 'SHADOW_COMPARE':
    case 'FORWARD':
    case 'BACKTEST':
    case 'MULTISCAN':
      return 'SHADOW_LIVE';
    case 'LIVE_ACCOUNT':
    case 'WATCHLIST':
      return 'LIVE';
    case 'SETTINGS':
    case 'TELEMETRY':
    case 'HISTORY':
    case 'UPDATES':
    case 'AUDIT':
      return 'SYSTEM';
  }
}

export const WorkspaceTabBar: React.FC<WorkspaceTabBarProps> = ({
  activeTab,
  setActiveTab,
  selectedSignal,
  activeCoinSymbol = null,
  onSelectCandidate,
  trackingCount,
  candidateCount,
  signalCount = 0,
  fiboActionableCount = 0,
  fiboArmedCount = 0,
  fiboShadowCount = 0,
  isTelemetryActive = true,
  isDevMode = false,
  onOpenTabHelp,
}) => {
  const { language, t } = useTranslation();

  const signalTabs: TabItemConfig[] = useMemo(
    () => [
      {
        id: 'FIBO_SHORT',
        labelKey: 'ws_tab_fibo_short',
        descKey: 'ws_tab_fibo_short_desc',
        icon: Zap,
        badge:
          fiboActionableCount > 0
            ? fiboActionableCount
            : fiboArmedCount > 0
              ? language === 'en'
                ? `${fiboArmedCount} armed`
                : language === 'zh'
                  ? `${fiboArmedCount} 待命`
                  : language === 'ko'
                    ? `${fiboArmedCount} 대기`
                    : `${fiboArmedCount} chờ`
              : null,
        pulse: fiboActionableCount > 0,
        category: 'SIGNALS',
      },
      {
        id: 'DECISION',
        labelKey: 'ws_tab_decision',
        icon: Activity,
        badge: activeCoinSymbol ? activeCoinSymbol.replace(/USDT$/i, '') : null,
        category: 'SIGNALS',
      },
      {
        id: 'MODELS',
        labelKey: 'ws_tab_models',
        descKey: 'ws_tab_models_desc',
        icon: BookOpen,
        category: 'SIGNALS',
      },
      {
        id: 'RADAR',
        labelKey: 'ws_tab_radar',
        descKey: 'ws_tab_radar_desc',
        icon: Radio,
        badge: signalCount > 0 ? signalCount : null,
        category: 'SIGNALS',
      },
      {
        id: 'RANKING',
        labelKey: 'ws_tab_candidates',
        icon: BarChart3,
        badge: candidateCount > 0 ? candidateCount : null,
        category: 'SIGNALS',
      },
      {
        id: 'MARKET',
        labelKey: 'ws_tab_market_context',
        icon: Layers,
        category: 'SIGNALS',
      },
    ],
    [fiboActionableCount, fiboArmedCount, activeCoinSymbol, signalCount, candidateCount, language]
  );

  const shadowLiveTabs: TabItemConfig[] = useMemo(() => {
    const base: TabItemConfig[] = [
      {
        id: 'PAPER_OOS',
        labelKey: 'ws_tab_paper_oos',
        descKey: 'ws_tab_paper_oos_desc',
        icon: Cpu,
        badge: '12 Acc',
        pulse: true,
        category: 'SHADOW_LIVE',
      },
      {
        id: 'SHADOW_COMPARE',
        labelKey: 'ws_tab_shadow_compare',
        descKey: 'ws_tab_shadow_compare_desc',
        icon: Gauge,
        badge: fiboShadowCount > 0 ? fiboShadowCount : null,
        category: 'SHADOW_LIVE',
      },
      {
        id: 'FORWARD',
        labelKey: 'ws_tab_forward',
        descKey: 'ws_tab_forward_desc',
        icon: Lock,
        category: 'SHADOW_LIVE',
      },
    ];
    if (isDevMode) {
      base.push(
        {
          id: 'BACKTEST',
          labelKey: 'ws_tab_experiments',
          descKey: 'ws_tab_experiments_desc',
          icon: ShieldCheck,
          category: 'SHADOW_LIVE',
        },
        {
          id: 'MULTISCAN',
          labelKey: 'ws_tab_multiscan',
          descKey: 'ws_tab_multiscan_desc',
          icon: FlaskConical,
          category: 'SHADOW_LIVE',
        }
      );
    }
    return base;
  }, [fiboShadowCount, isDevMode]);

  const liveTabs: TabItemConfig[] = useMemo(
    () => [
      {
        id: 'LIVE_ACCOUNT',
        labelKey: 'ws_tab_live_account',
        descKey: 'ws_tab_live_account_desc',
        icon: Wallet,
        badge: 'Binance',
        category: 'LIVE',
      },
      {
        id: 'WATCHLIST',
        labelKey: 'ws_tab_tracking',
        icon: Target,
        badge: trackingCount > 0 ? trackingCount : null,
        category: 'LIVE',
      },
    ],
    [trackingCount]
  );

  const systemTabs: TabItemConfig[] = useMemo(() => {
    const base: TabItemConfig[] = [
      {
        id: 'SETTINGS',
        labelKey: 'ws_tab_settings',
        descKey: 'ws_tab_settings_desc',
        icon: Settings,
        category: 'SYSTEM',
      },
      {
        id: 'TELEMETRY',
        labelKey: 'ws_tab_telemetry',
        descKey: 'ws_tab_telemetry_desc',
        icon: Radio,
        pulse: isTelemetryActive,
        category: 'SYSTEM',
      },
      {
        id: 'HISTORY',
        labelKey: 'ws_tab_history',
        descKey: 'ws_tab_history_desc',
        icon: Clock,
        category: 'SYSTEM',
      },
      {
        id: 'UPDATES',
        labelKey: 'ws_tab_updates',
        descKey: 'ws_tab_updates_desc',
        icon: GitPullRequest,
        category: 'SYSTEM',
      },
    ];
    if (isDevMode) {
      base.push({
        id: 'AUDIT',
        labelKey: 'ws_tab_audit',
        descKey: 'ws_tab_audit_desc',
        icon: Brain,
        category: 'SYSTEM',
      });
    }
    return base;
  }, [isTelemetryActive, isDevMode]);

  const activeCategory: TabCategory = getCategoryForTab(activeTab);

  const pillars: PillarConfig[] = useMemo(
    () => [
      {
        id: 'SIGNALS',
        testId: 'workspace-pillar-signals',
        labelVi: 'Tín hiệu',
        labelEn: 'Signals',
        labelZh: '交易信号',
        labelKo: '신호 & 방법론',
        subVi: 'Fibo v4.0 (N3 ★ Live)',
        subEn: 'Fibo v4.0 (N3 ★ Live)',
        subZh: 'Fibo v4.0 (N3 ★ 实盘)',
        subKo: 'Fibo v4.0 (N3 ★ 라이브)',
        icon: Zap,
        defaultTab: 'FIBO_SHORT',
        badge:
          fiboActionableCount > 0
            ? `${fiboActionableCount} N3+`
            : fiboArmedCount > 0
              ? language === 'en'
                ? `${fiboArmedCount} Armed`
                : language === 'zh'
                  ? `${fiboArmedCount} 待命`
                  : language === 'ko'
                    ? `${fiboArmedCount} 대기`
                    : `${fiboArmedCount} Chờ`
              : null,
        badgeCls:
          fiboActionableCount > 0
            ? 'bg-emerald-500 text-slate-950 font-black'
            : 'bg-amber-500/20 text-amber-300 border border-amber-500/40',
        activeCls:
          'bg-gradient-to-r from-amber-500 to-amber-400 text-slate-950 shadow-md shadow-amber-500/20 border-amber-400',
      },
      {
        id: 'SHADOW_LIVE',
        testId: 'workspace-pillar-shadow_live',
        labelVi: 'Shadow Live',
        labelEn: 'Shadow Live',
        labelZh: '影子实盘 (OOS)',
        labelKo: '섀도우 라이브',
        subVi: '6 Nhánh N1–N6 · 12 TK',
        subEn: '6 Branches N1–N6 · 12 Acc',
        subZh: '6大分支 N1–N6 · 12账户',
        subKo: '6개 브랜치 N1–N6 · 12계좌',
        icon: FlaskConical,
        defaultTab: 'PAPER_OOS',
        badge: '12 OOS',
        badgeCls: 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40',
        pulseDot: true,
        activeCls:
          'bg-gradient-to-r from-cyan-500 to-sky-400 text-slate-950 shadow-md shadow-cyan-500/20 border-cyan-400',
      },
      {
        id: 'LIVE',
        testId: 'workspace-pillar-live',
        labelVi: 'Live',
        labelEn: 'Live',
        labelZh: '实盘账户',
        labelKo: '라이브 계좌',
        subVi: 'Tài khoản Thực & Vị thế',
        subEn: 'Real Account & Positions',
        subZh: '币安实盘账户与持仓',
        subKo: '바이낸스 실계좌 & 포지션',
        icon: Wallet,
        defaultTab: 'LIVE_ACCOUNT',
        badge: trackingCount > 0 ? trackingCount : null,
        badgeCls: 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40',
        activeCls:
          'bg-gradient-to-r from-emerald-500 to-teal-400 text-slate-950 shadow-md shadow-emerald-500/20 border-emerald-400',
      },
      {
        id: 'SYSTEM',
        testId: 'workspace-system-menu',
        labelVi: 'Hệ thống',
        labelEn: 'System',
        labelZh: '系统管理',
        labelKo: '시스템',
        subVi: 'Cài đặt · Hạ tầng · Log',
        subEn: 'Settings · Telemetry · Logs',
        subZh: '系统设置 · 监控 · 日志',
        subKo: '설정 · 텔레메트리 · 로그',
        icon: Cpu,
        defaultTab: 'SETTINGS',
        pulseDot: isTelemetryActive,
        activeCls:
          'bg-gradient-to-r from-slate-200 to-slate-300 text-slate-950 shadow-md border-slate-300',
      },
    ],
    [fiboActionableCount, fiboArmedCount, trackingCount, isTelemetryActive, language]
  );

  const visibleSubTabs: TabItemConfig[] = useMemo(() => {
    switch (activeCategory) {
      case 'SIGNALS':
        return signalTabs;
      case 'SHADOW_LIVE':
        return shadowLiveTabs;
      case 'LIVE':
        return liveTabs;
      case 'SYSTEM':
        return systemTabs;
    }
  }, [activeCategory, signalTabs, shadowLiveTabs, liveTabs, systemTabs]);


  const handleSelectPillar = (pillar: PillarConfig) => {
    setActiveTab(pillar.defaultTab);
  };

  const currentSymbol = selectedSignal?.symbol || activeCoinSymbol;

  return (
    <div className="border-b border-slate-800 pb-2.5 mb-3 min-w-0 space-y-2">
      {/* ─────────────────────────────────────────────────────────────
          ROW 1: 4 TOP-LEVEL PILLARS (Tín hiệu | Shadow Live | Live | Hệ thống)
      ───────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-2 min-w-0">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5 flex-1 min-w-0 bg-slate-950/90 p-1.5 rounded-xl border border-slate-800/90 shadow-inner">
          {pillars.map((pillar) => {
            const Icon = pillar.icon;
            const isActive = activeCategory === pillar.id;
            return (
              <button
                key={pillar.id}
                data-testid={pillar.testId}
                type="button"
                onClick={() => handleSelectPillar(pillar)}
                className={`px-2.5 py-2 rounded-lg text-left transition-all duration-150 border flex items-center justify-between gap-2 min-w-0 cursor-pointer ${
                  isActive
                    ? `${pillar.activeCls} font-extrabold`
                    : 'bg-slate-900/60 hover:bg-slate-900 text-slate-300 hover:text-white border-slate-800/80'
                }`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <div
                    className={`p-1.5 rounded-md shrink-0 ${
                      isActive ? 'bg-slate-950/20 text-slate-950' : 'bg-slate-950 text-amber-400'
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs sm:text-[13px] font-bold truncate flex items-center gap-1.5">
                      <span>
                        {language === 'en'
                          ? pillar.labelEn
                          : language === 'zh'
                            ? pillar.labelZh
                            : language === 'ko'
                              ? pillar.labelKo
                              : pillar.labelVi}
                      </span>
                      {pillar.pulseDot && (
                        <span
                          className={`w-1.5 h-1.5 rounded-full shrink-0 animate-pulse ${
                            isActive ? 'bg-slate-950' : 'bg-emerald-400'
                          }`}
                        />
                      )}
                    </div>
                    <div
                      className={`hidden lg:block text-[10px] truncate font-medium ${
                        isActive ? 'text-slate-900/85' : 'text-slate-400'
                      }`}
                    >
                      {language === 'en'
                        ? pillar.subEn
                        : language === 'zh'
                          ? pillar.subZh
                          : language === 'ko'
                            ? pillar.subKo
                            : pillar.subVi}
                    </div>
                  </div>
                </div>

                {pillar.badge !== undefined && pillar.badge !== null && (
                  <span
                    className={`hidden sm:inline-flex text-[10px] px-1.5 py-0.5 rounded-full font-mono shrink-0 ${
                      isActive
                        ? 'bg-slate-950/85 text-amber-300 font-bold'
                        : pillar.badgeCls || 'bg-slate-800 text-slate-300'
                    }`}
                  >
                    {pillar.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Right Controls: Active Coin Quick Pill + Tab Help */}
        <div className="hidden md:flex items-center gap-2 shrink-0">
          {currentSymbol && (
            <CoinLink
              symbol={currentSymbol}
              onClick={() => onSelectCandidate(currentSymbol)}
              className="bg-amber-950/60 px-2.5 py-1.5 rounded-lg border border-amber-500/30 text-amber-300 text-xs font-mono font-bold hover:bg-amber-900/60 transition"
            />
          )}
          {onOpenTabHelp && (
            <button
              type="button"
              onClick={() => onOpenTabHelp(activeTab)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold text-slate-300 bg-slate-900/90 border border-slate-700/80 hover:border-violet-500/80 hover:text-violet-200 hover:bg-violet-950/40 transition shrink-0 shadow-sm cursor-pointer"
              title="Xem mô tả chi tiết & cơ chế hoạt động của mục này"
            >
              <HelpCircle className="w-3.5 h-3.5 text-violet-400" />
              <span className="hidden xl:inline">
                {language === 'en'
                  ? 'Guide'
                  : language === 'zh'
                    ? '指南'
                    : language === 'ko'
                      ? '가이드'
                      : 'Hướng dẫn'}
              </span>
            </button>
          )}
        </div>
      </div>

      {/* ─────────────────────────────────────────────────────────────
          ROW 2: SUB-TABS FOR THE ACTIVE PILLAR
      ───────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-2 min-w-0">
        <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5 min-w-0 flex-1 [&::-webkit-scrollbar]:hidden">
          {visibleSubTabs.map((tab) => {
            const Icon = tab.icon;
            const isSelected = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                data-testid={'workspace-tab-' + tab.id.toLowerCase()}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                title={tab.descKey ? t(tab.descKey) : undefined}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 whitespace-nowrap transition-all duration-150 border cursor-pointer ${
                  isSelected
                    ? 'bg-slate-800 text-amber-300 border-amber-500/50 shadow-sm shadow-amber-500/10 font-bold'
                    : 'bg-slate-950/70 text-slate-400 hover:text-slate-200 hover:bg-slate-900 border-slate-800/80'
                }`}
              >
                <Icon
                  className={`w-3.5 h-3.5 shrink-0 ${
                    isSelected
                      ? 'text-amber-400'
                      : tab.pulse
                        ? 'text-emerald-400 animate-pulse'
                        : 'text-slate-400'
                  }`}
                />
                <span>{t(tab.labelKey)}</span>
                {tab.badge !== undefined &&
                tab.badge !== null &&
                (typeof tab.badge === 'number' ? tab.badge > 0 : Boolean(tab.badge)) ? (
                  <span
                    className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono font-bold ${
                      isSelected
                        ? 'bg-amber-500/20 text-amber-200 border border-amber-400/40'
                        : 'bg-slate-800 text-slate-300'
                    }`}
                  >
                    {tab.badge}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>

        {/* Mobile Help Button */}
        {onOpenTabHelp && (
          <button
            type="button"
            onClick={() => onOpenTabHelp(activeTab)}
            className="md:hidden inline-flex items-center gap-1 px-2 py-1.5 rounded-lg text-[11px] font-semibold text-violet-300 bg-slate-950 border border-slate-800 shrink-0"
            aria-label="Hướng dẫn Tab"
          >
            <HelpCircle className="w-3.5 h-3.5 text-violet-400" />
          </button>
        )}
      </div>
    </div>
  );
};
