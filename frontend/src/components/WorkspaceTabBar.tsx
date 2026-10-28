import React, { useState, useRef, useEffect, useMemo } from 'react';
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
  ChevronDown,
  Check,
  Zap,
  Settings,
  HelpCircle,
  Brain,
} from 'lucide-react';
import { CoinLink } from './CoinLink';
import { useTranslation } from '../i18n/LanguageContext';
import type { SignalItem } from '../types';
import type { MobileTabType } from './v2/MobileBottomNav';

export type WorkspaceTab =
  | 'DECISION'
  | 'RADAR'
  | 'FIBO_SHORT'
  | 'WATCHLIST'
  | 'RANKING'
  | 'MULTISCAN'
  | 'BACKTEST'
  | 'FORWARD'
  | 'AUDIT'
  | 'MARKET'
  | 'TELEMETRY'
  | 'HISTORY'
  | 'MODELS'
  | 'UPDATES'
  | 'SETTINGS';
export type TabCategory = 'TRADING' | 'LAB' | 'SYSTEM';

interface TabItemConfig {
  id: WorkspaceTab;
  labelKey: string;
  descKey?: string;
  icon: React.ElementType;
  badge?: number | string | null;
  pulse?: boolean;
  category: TabCategory;
}

interface WorkspaceTabBarProps {
  activeTab: WorkspaceTab;
  setActiveTab: (tab: WorkspaceTab) => void;
  selectedSignal: SignalItem | null;
  onSelectCandidate: (symbol: string) => void;
  trackingCount: number;
  candidateCount: number;
  signalCount?: number;
  isTelemetryActive?: boolean;
  guiVersion?: 'v1' | 'v2';
  mobileTab?: MobileTabType;
  onOpenTabHelp?: (tab?: WorkspaceTab) => void;
  isDevMode?: boolean;
}

export const WorkspaceTabBar: React.FC<WorkspaceTabBarProps> = ({
  activeTab,
  setActiveTab,
  selectedSignal,
  onSelectCandidate,
  trackingCount,
  candidateCount,
  signalCount = 0,
  isTelemetryActive = true,
  guiVersion: _guiVersion = 'v2',
  mobileTab: _mobileTab = 'RADAR',
  isDevMode = false,
  onOpenTabHelp,
}) => {
  const { language, t } = useTranslation();
  const [openDropdown, setOpenDropdown] = useState<'LAB' | 'SYSTEM' | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Tab configurations
  const tradingTabs: TabItemConfig[] = useMemo(() => [
    {
      id: 'DECISION',
      labelKey: 'ws_tab_decision',
      icon: Activity,
      category: 'TRADING',
    },
    {
      id: 'RADAR',
      labelKey: 'ws_tab_radar',
      descKey: 'ws_tab_radar_desc',
      icon: Radio,
      badge: signalCount > 0 ? signalCount : null,
      pulse: signalCount > 0,
      category: 'TRADING',
    },
    {
      id: 'FIBO_SHORT',
      labelKey: 'ws_tab_fibo_short',
      descKey: 'ws_tab_fibo_short_desc',
      icon: GitPullRequest,
      category: 'TRADING',
    },
    {
      id: 'WATCHLIST',
      labelKey: 'ws_tab_tracking',
      icon: Target,
      badge: trackingCount,
      category: 'TRADING',
    },
    {
      id: 'RANKING',
      labelKey: 'ws_tab_candidates',
      icon: BarChart3,
      badge: candidateCount,
      category: 'TRADING',
    },
    {
      id: 'MARKET',
      labelKey: 'ws_tab_market_context',
      icon: Layers,
      category: 'TRADING',
    },
  ], [trackingCount, candidateCount, signalCount]);

  const labTabs: TabItemConfig[] = useMemo(() => isDevMode ? [
    {
      id: 'MULTISCAN',
      labelKey: 'ws_tab_multiscan',
      descKey: 'ws_tab_multiscan_desc',
      icon: FlaskConical,
      category: 'LAB',
    },
    {
      id: 'BACKTEST',
      labelKey: 'ws_tab_experiments',
      descKey: 'ws_tab_experiments_desc',
      icon: ShieldCheck,
      category: 'LAB',
    },
    {
      id: 'FORWARD',
      labelKey: 'ws_tab_forward',
      descKey: 'ws_tab_forward_desc',
      icon: Lock,
      category: 'LAB',
    },
  ] : [], [isDevMode]);

  const systemTabs: TabItemConfig[] = useMemo(() => {
    const tabs: TabItemConfig[] = [
    {
      id: 'AUDIT',
      labelKey: 'ws_tab_audit',
      descKey: 'ws_tab_audit_desc',
      icon: Cpu,
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
      id: 'MODELS',
      labelKey: 'ws_tab_models',
      descKey: 'ws_tab_models_desc',
      icon: Brain,
      category: 'SYSTEM',
    },
    {
      id: 'UPDATES',
      labelKey: 'ws_tab_updates',
      descKey: 'ws_tab_updates_desc',
      icon: GitPullRequest,
      category: 'SYSTEM',
    },
    {
      id: 'SETTINGS',
      labelKey: 'ws_tab_settings',
      descKey: 'ws_tab_settings_desc',
      icon: Settings,
      category: 'SYSTEM',
    },
    ];
    return isDevMode ? tabs : tabs.filter(t => t.id === 'AUDIT' || t.id === 'HISTORY' || t.id === 'SETTINGS');
  }, [isTelemetryActive, isDevMode]);

  // Determine current active category
  const activeCategory: TabCategory = useMemo(() => {
    if (tradingTabs.some(item => item.id === activeTab)) return 'TRADING';
    if (labTabs.some(item => item.id === activeTab)) return 'LAB';
    return 'SYSTEM';
  }, [activeTab, tradingTabs, labTabs]);

  const [browsingCategory, setBrowsingCategory] = useState<TabCategory | null>(null);
  const mobileCategory = browsingCategory ?? activeCategory;

  // Close dropdown on outside click or ESC key
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpenDropdown(null);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpenDropdown(null);
      }
    };

    if (openDropdown) {
      document.addEventListener('mousedown', handleOutsideClick);
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [openDropdown]);

  // Find active item in a group for Smart Dropdown Title
  const activeLabTab = labTabs.find(item => item.id === activeTab);
  const activeSystemTab = systemTabs.find(item => item.id === activeTab);

  const handleSelectTab = (tab: WorkspaceTab) => {
    setActiveTab(tab);
    setOpenDropdown(null);
    setBrowsingCategory(null);
  };

  const handleCategorySwitch = (category: TabCategory) => {
    setBrowsingCategory(category);
    // If current tab is not in this category, default to first tab of new category
    if (category === 'TRADING' && !tradingTabs.some(item => item.id === activeTab)) {
      setActiveTab('DECISION');
    } else if (category === 'LAB' && !labTabs.some(item => item.id === activeTab)) {
      setActiveTab('MULTISCAN');
    } else if (category === 'SYSTEM' && !systemTabs.some(item => item.id === activeTab)) {
      setActiveTab('AUDIT');
    }
  };

  const currentMobileTabs = mobileCategory === 'TRADING' ? tradingTabs : mobileCategory === 'LAB' ? labTabs : systemTabs;
  return (
    <div className="border-b border-slate-800 pb-2 mb-3 min-w-0" ref={dropdownRef}>
      {/* ─────────────────────────────────────────────────────────────
          1. DESKTOP & TABLET VIEW (md and up)
      ───────────────────────────────────────────────────────────── */}
      <div className="hidden md:flex items-center justify-between gap-3 min-w-0">
        <div className="flex items-center gap-2.5 min-w-0 flex-1">
          {/* Active Coin Badge */}
          {selectedSignal && (
            <div className="flex items-center gap-1.5 text-xs font-mono shrink-0">
              <span className="text-slate-400 hidden xl:inline">{t('ranking_viewing_prefix')}</span>
              <CoinLink
                symbol={selectedSignal.symbol}
                onClick={() => onSelectCandidate(selectedSignal.symbol)}
                className="bg-amber-950/60 px-2.5 py-1 rounded-lg border border-amber-500/30 text-amber-300 font-bold hover:bg-amber-900/60 transition"
              />
            </div>
          )}

          {/* Grouped Tab Pills Bar */}
          <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-xl border border-slate-800 min-w-0 shadow-inner">
            {/* Primary Trading Tabs (Always visible directly) */}
            {tradingTabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  data-testid={'workspace-tab-' + tab.id.toLowerCase()}
                  type="button"
                  onClick={() => handleSelectTab(tab.id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 whitespace-nowrap transition-all duration-150 ${
                    isActive
                      ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20 font-bold'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{t(tab.labelKey)}</span>
                  {tab.badge !== undefined && tab.badge !== null && (typeof tab.badge === 'number' ? tab.badge > 0 : Boolean(tab.badge)) ? (
                    <span
                      className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono font-bold transition ${
                        isActive
                          ? 'bg-slate-950/90 text-amber-400'
                          : 'bg-slate-800 text-slate-300'
                      }`}
                    >
                      {tab.badge}
                    </span>
                  ) : null}
                </button>
              );
            })}

            <span aria-hidden="true" className="mx-0.5 h-4 w-px shrink-0 bg-slate-800" />

            {/* Dropdown 1: Lab & Scan */}
            {labTabs.length > 0 && (
            <div className="relative">
              <button
                data-testid="workspace-lab-menu"
                type="button"
                onClick={() => setOpenDropdown(openDropdown === 'LAB' ? null : 'LAB')}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 whitespace-nowrap transition-all duration-150 ${
                  activeLabTab
                    ? 'bg-amber-500/15 text-amber-300 border border-amber-500/40 shadow-sm shadow-amber-500/10 font-bold'
                    : openDropdown === 'LAB'
                    ? 'bg-slate-900 text-slate-200 border border-slate-700'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent'
                }`}
                title={t('ws_group_lab')}
              >
                {activeLabTab ? (
                  <>
                    <activeLabTab.icon className="w-3.5 h-3.5 text-amber-400" />
                    <span>{t(activeLabTab.labelKey)}</span>
                  </>
                ) : (
                  <>
                    <FlaskConical className="w-3.5 h-3.5 text-slate-400" />
                    <span>{t('ws_group_lab')}</span>
                  </>
                )}
                <ChevronDown
                  className={`w-3 h-3 transition-transform duration-200 ${
                    openDropdown === 'LAB' ? 'rotate-180 text-amber-400' : 'text-slate-500'
                  }`}
                />
              </button>

              {/* Lab Dropdown Menu */}
              {openDropdown === 'LAB' && (
                <div className="absolute left-0 top-full mt-1.5 w-64 bg-slate-950/95 backdrop-blur-md border border-slate-800 rounded-xl shadow-2xl p-1.5 z-50 animate-in fade-in zoom-in-95 duration-150">
                  <div className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-300 border-b border-slate-800/80 mb-1 flex items-center gap-1">
                    <FlaskConical className="w-3 h-3 text-amber-400" />
                    {t('ws_group_lab')}
                  </div>
                  {labTabs.map((tab) => {
                    const Icon = tab.icon;
                    const isSelected = activeTab === tab.id;
                    return (
                      <button
                        key={tab.id}
                        data-testid={'workspace-tab-' + tab.id.toLowerCase()}
                        type="button"
                        onClick={() => handleSelectTab(tab.id)}
                        className={`w-full text-left px-2.5 py-2 rounded-lg text-xs flex items-center justify-between gap-2 transition ${
                          isSelected
                            ? 'bg-amber-500/20 text-amber-300 font-semibold'
                            : 'text-slate-300 hover:bg-slate-900 hover:text-slate-100'
                        }`}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <Icon className={`w-4 h-4 shrink-0 ${isSelected ? 'text-amber-400' : 'text-slate-400'}`} />
                          <div className="min-w-0">
                            <div className="truncate font-medium">{t(tab.labelKey)}</div>
                            {tab.descKey && (
                              <div className="text-[10px] text-slate-300 truncate font-normal">
                                {t(tab.descKey)}
                              </div>
                            )}
                          </div>
                        </div>
                        {isSelected && <Check className="w-3.5 h-3.5 text-amber-400 shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
            )}

            {/* Dropdown 2: System & Logs */}
            <div className="relative">
              <button
                data-testid="workspace-system-menu"
                type="button"
                onClick={() => setOpenDropdown(openDropdown === 'SYSTEM' ? null : 'SYSTEM')}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 whitespace-nowrap transition-all duration-150 ${
                  activeSystemTab
                    ? 'bg-amber-500/15 text-amber-300 border border-amber-500/40 shadow-sm shadow-amber-500/10 font-bold'
                    : openDropdown === 'SYSTEM'
                    ? 'bg-slate-900 text-slate-200 border border-slate-700'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent'
                }`}
                title={t('ws_group_system')}
              >
                {activeSystemTab ? (
                  <>
                    <activeSystemTab.icon
                      className={`w-3.5 h-3.5 ${
                        activeSystemTab.id === 'TELEMETRY'
                          ? 'text-emerald-400 animate-pulse'
                          : activeSystemTab.id === 'UPDATES'
                          ? 'text-amber-400'
                          : 'text-amber-400'
                      }`}
                    />
                    <span>{t(activeSystemTab.labelKey)}</span>
                  </>
                ) : (
                  <>
                    <Cpu className="w-3.5 h-3.5 text-slate-400" />
                    <span>{t('ws_group_system')}</span>
                    {isTelemetryActive && (
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    )}
                  </>
                )}
                <ChevronDown
                  className={`w-3 h-3 transition-transform duration-200 ${
                    openDropdown === 'SYSTEM' ? 'rotate-180 text-amber-400' : 'text-slate-500'
                  }`}
                />
              </button>

              {/* System Dropdown Menu */}
              {openDropdown === 'SYSTEM' && (
                <div className="absolute right-0 sm:left-0 top-full mt-1.5 w-64 bg-slate-950/95 backdrop-blur-md border border-slate-800 rounded-xl shadow-2xl p-1.5 z-50 animate-in fade-in zoom-in-95 duration-150">
                  <div className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-300 border-b border-slate-800/80 mb-1 flex items-center justify-between">
                    <div className="flex items-center gap-1">
                      <Cpu className="w-3 h-3 text-amber-400" />
                      {t('ws_group_system')}
                    </div>
                    {isTelemetryActive && (
                      <span className="flex items-center gap-1 text-[9px] text-emerald-400 font-mono">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        LIVE
                      </span>
                    )}
                  </div>
                  {systemTabs.map((tab) => {
                    const Icon = tab.icon;
                    const isSelected = activeTab === tab.id;
                    return (
                      <button
                        key={tab.id}
                        data-testid={'workspace-tab-' + tab.id.toLowerCase()}
                        type="button"
                        onClick={() => handleSelectTab(tab.id)}
                        className={`w-full text-left px-2.5 py-2 rounded-lg text-xs flex items-center justify-between gap-2 transition ${
                          isSelected
                            ? 'bg-amber-500/20 text-amber-300 font-semibold'
                            : 'text-slate-300 hover:bg-slate-900 hover:text-slate-100'
                        }`}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <Icon
                            className={`w-4 h-4 shrink-0 ${
                              isSelected
                                ? 'text-amber-400'
                                : tab.id === 'TELEMETRY'
                                ? 'text-emerald-400'
                                : tab.id === 'UPDATES'
                                ? 'text-amber-400'
                                : 'text-slate-400'
                            } ${tab.pulse ? 'animate-pulse' : ''}`}
                          />
                          <div className="min-w-0">
                            <div className="truncate font-medium">{t(tab.labelKey)}</div>
                            {tab.descKey && (
                              <div className="text-[10px] text-slate-300 truncate font-normal">
                                {t(tab.descKey)}
                              </div>
                            )}
                          </div>
                        </div>
                        {isSelected && <Check className="w-3.5 h-3.5 text-amber-400 shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Quick Tab Help Button (Desktop) */}
        {onOpenTabHelp && (
          <button
            type="button"
            onClick={() => onOpenTabHelp(activeTab)}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold text-slate-300 bg-slate-900/90 border border-slate-700/80 hover:border-violet-500/80 hover:text-violet-200 hover:bg-violet-950/40 transition shrink-0 shadow-sm"
            title="Xem mô tả chi tiết & cơ chế hoạt động của tab này"
          >
            <HelpCircle className="w-3.5 h-3.5 text-violet-400" />
            <span className="hidden lg:inline">{language === 'en' ? 'Tab Guide' : language === 'zh' ? 'Tab 帮助' : language === 'ko' ? '탭 가이드' : 'Hướng dẫn Tab'}</span>
          </button>
        )}
      </div>

      {/* ─────────────────────────────────────────────────────────────
          2. MOBILE VIEW (under md)
          Two-Tier Layout: Category Switcher Pills + Compact Sub-tabs
      ───────────────────────────────────────────────────────────── */}
      <div className="block md:hidden space-y-2 min-w-0">
        {/* Mobile Header Row: Coin Pill + Category Segmented Bar */}
        <div className="flex items-center justify-between gap-2 min-w-0">
          {selectedSignal ? (
            <CoinLink
              symbol={selectedSignal.symbol}
              onClick={() => onSelectCandidate(selectedSignal.symbol)}
              className="bg-amber-950/60 px-2 py-0.5 rounded-lg border border-amber-500/30 text-amber-300 font-bold text-xs shrink-0"
            />
          ) : (
            <div className="text-[11px] font-bold tracking-wider text-slate-400 uppercase flex items-center gap-1 shrink-0">
              <Zap className="w-3.5 h-3.5 text-amber-400" />
              Workspace
            </div>
          )}

          {/* 3-Category Segmented Selector */}
          <div className="flex items-center bg-slate-950 p-0.5 rounded-lg border border-slate-800 text-[11px] shrink-0">
            <button
              type="button"
              onClick={() => handleCategorySwitch('TRADING')}
              className={`px-2.5 py-1 rounded-md font-semibold transition flex items-center gap-1 ${
                mobileCategory === 'TRADING'
                  ? 'bg-amber-500 text-slate-950 shadow-sm font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Zap className="w-3 h-3" />
              <span>{t('ws_group_trading')}</span>
            </button>

            {labTabs.length > 0 && (
            <button
              type="button"
              onClick={() => handleCategorySwitch('LAB')}
              className={`px-2.5 py-1 rounded-md font-semibold transition flex items-center gap-1 ${
                mobileCategory === 'LAB'
                  ? 'bg-amber-500 text-slate-950 shadow-sm font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <FlaskConical className="w-3 h-3" />
              <span>{t('ws_group_lab')}</span>
            </button>
            )}

            <button
              type="button"
              onClick={() => handleCategorySwitch('SYSTEM')}
              className={`px-2.5 py-1 rounded-md font-semibold transition flex items-center gap-1 ${
                mobileCategory === 'SYSTEM'
                  ? 'bg-amber-500 text-slate-950 shadow-sm font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Cpu className="w-3 h-3" />
              <span>{t('ws_group_system')}</span>
            </button>
          </div>
        </div>

        {/* Mobile Sub-tab Row (3-4 touch chips, fits perfectly) */}
        <div className="flex items-center gap-1.5 overflow-x-auto py-0.5 min-w-0 [&::-webkit-scrollbar]:hidden">
          {currentMobileTabs.map((tab) => {
            const Icon = tab.icon;
            const isSelected = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => handleSelectTab(tab.id)}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 whitespace-nowrap transition active:scale-95 ${
                  isSelected
                    ? 'bg-gradient-to-r from-amber-500 to-amber-400 text-slate-950 shadow-md shadow-amber-500/20 font-bold'
                    : 'bg-slate-900/90 border border-slate-800 text-slate-300 active:bg-slate-800'
                }`}
              >
                <Icon
                  className={`w-3.5 h-3.5 ${
                    isSelected
                      ? 'text-slate-950'
                      : tab.id === 'TELEMETRY'
                      ? 'text-emerald-400'
                      : tab.id === 'UPDATES'
                      ? 'text-amber-400'
                      : 'text-slate-400'
                  } ${tab.pulse && !isSelected ? 'animate-pulse' : ''}`}
                />
                <span>{t(tab.labelKey)}</span>
                {tab.badge !== undefined && tab.badge !== null && (typeof tab.badge === 'number' ? tab.badge > 0 : Boolean(tab.badge)) ? (
                  <span
                    className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono font-bold ${
                      isSelected ? 'bg-slate-950 text-amber-300' : 'bg-slate-800 text-slate-300'
                    }`}
                  >
                    {tab.badge}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>

        {/* Quick Tab Help Button (Mobile) */}
        {onOpenTabHelp && (
          <div className="flex justify-end pt-0.5">
            <button
              type="button"
              onClick={() => onOpenTabHelp(activeTab)}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium text-slate-300 bg-slate-900 border border-slate-800 hover:border-violet-500 hover:text-violet-200"
            >
              <HelpCircle className="w-3 h-3 text-violet-400" />
              <span>{language === 'en' ? 'Tab Guide' : language === 'zh' ? 'Tab 帮助' : language === 'ko' ? '탭 가이드' : 'Hướng dẫn Tab'}</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
