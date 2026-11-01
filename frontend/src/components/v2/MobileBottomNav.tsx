import React from 'react';
import { Zap, FlaskConical, Wallet, Cpu } from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';

export type MobileTabType = 'SIGNALS' | 'SHADOW_LIVE' | 'LIVE' | 'SYSTEM';

interface MobileBottomNavProps {
  activeTab: MobileTabType;
  onSelectTab: (tab: MobileTabType) => void;
  signalCount?: number;
  selectedSymbol?: string | null;
  trackingCount?: number;
}

export const MobileBottomNav: React.FC<MobileBottomNavProps> = ({
  activeTab,
  onSelectTab,
  signalCount = 0,
  trackingCount = 0,
}) => {
  const { language, t } = useTranslation();

  const navItems: Array<{
    id: MobileTabType;
    label: string;
    icon: React.ElementType;
    badge?: string | number | null;
    badgeColor?: string;
  }> = [
    {
      id: 'SIGNALS',
      label:
        language === 'en'
          ? 'Signals'
          : language === 'zh'
            ? '信号'
            : language === 'ko'
              ? '신호'
              : 'Tín hiệu',
      icon: Zap,
      badge: signalCount > 0 ? signalCount : null,
      badgeColor: 'bg-amber-500 text-slate-950 font-black',
    },
    {
      id: 'SHADOW_LIVE',
      label: 'Shadow Live',
      icon: FlaskConical,
      badge: '12',
      badgeColor: 'bg-cyan-500 text-slate-950 font-bold',
    },
    {
      id: 'LIVE',
      label: 'Live',
      icon: Wallet,
      badge: trackingCount > 0 ? trackingCount : null,
      badgeColor: 'bg-emerald-500 text-slate-950 font-bold',
    },
    {
      id: 'SYSTEM',
      label:
        language === 'en'
          ? 'System'
          : language === 'zh'
            ? '系统'
            : language === 'ko'
              ? '시스템'
              : 'Hệ thống',
      icon: Cpu,
      badge: null,
    },
  ];

  return (
    <nav
      data-testid="mobile-bottom-nav"
      aria-label={t('mobile_nav_aria') || 'Điều hướng chính trên di động'}
      className="mobile-bottom-nav fixed left-0 right-0 z-40 bg-slate-950/95 backdrop-blur-lg border-t border-slate-800/90 px-1.5 pt-1 sm:hidden"
    >
      <div className="grid grid-cols-4 gap-1 items-center justify-around">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelectTab(item.id)}
              className={`relative flex flex-col items-center justify-center py-1.5 px-1 rounded-lg transition-all ${
                isActive
                  ? 'text-amber-400 bg-amber-500/10 font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <div className="relative">
                <Icon className={`w-4 h-4 ${isActive ? 'stroke-[2.4]' : 'stroke-[1.8]'}`} />
                {item.badge !== null && item.badge !== undefined && (
                  <span
                    className={`absolute -top-1.5 -right-3.5 px-1 min-w-[16px] h-[14px] rounded-full text-[9px] leading-[14px] text-center font-mono ${
                      item.badgeColor || 'bg-amber-500 text-slate-950 font-bold'
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </div>
              <span className="text-[10px] mt-0.5 truncate max-w-full">{item.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
