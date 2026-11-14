import React from 'react';
import { Flame, ChevronDown, CheckCircle2, XCircle, Clock, Send, Activity, ExternalLink } from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';
import type { CandidateCoin, SignalItem, SignalTradeSetup, RiskLevel } from '../../types';
import { normalizeProbability } from '../../types';
import { getRiskLabel } from '../../i18n/translations';
import { getCoinExternalUrl } from '../../utils/cmc';
import { getCoinMarketCapInfo, getMarketCapBadgeConfig, getMarketCapSourceLabel } from '../../utils/sectors';

interface DecisionHeaderProps {
  symbol: string;
  displayDetail?: any;
  high24h?: number;
  low24h?: number;
  change24h?: number;
  name: string;
  currentPrice: number;
  chartSource?: 'db' | 'api';
  selectedSignal?: SignalItem | null;
  candidates: CandidateCoin[];
  onSelectCandidate: (symbol: string) => void;
  isDeepAnalyzing?: boolean;
  onOpenCoinSelector?: () => void;
  probability?: number | null;
  riskLevel?: RiskLevel | string | null;
  tradeSetup?: SignalTradeSetup | null;
  onOpenTabHelp?: () => void;
}

export const DecisionHeader: React.FC<DecisionHeaderProps> = ({
  symbol,
  name,
  currentPrice,
  selectedSignal,
  candidates,
  onSelectCandidate,
  isDeepAnalyzing,
  onOpenCoinSelector,
  displayDetail,
  high24h,
  low24h,
  change24h,
  probability,
  riskLevel,
}) => {
  const { language, t } = useTranslation();

  // Top 5 Hot Candidates for quick 1-click bar
  const topCandidates = [...candidates]
    .sort((a, b) => (b.score || 0) - (a.score || 0))
    .slice(0, 5);

  const probabilityPct = normalizeProbability(probability);
  const stateLabel = selectedSignal?.two_tier_state === 'FIRED'
    ? t('feed_tag_fired')
    : selectedSignal?.two_tier_state === 'ARMED'
      ? t('feed_tag_armed')
      : t('ws_rec_watch_badge');
  const localizedRisk = riskLevel ? getRiskLabel(riskLevel, language) : null;

  const displayMarketCap = displayDetail ? getCoinMarketCapInfo(symbol, displayDetail) : null;
  const marketCapBadge = displayMarketCap
    ? getMarketCapBadgeConfig(
        displayMarketCap.market_cap_tier,
        displayMarketCap.market_cap_str,
        language,
        displayMarketCap.market_cap_is_estimate,
      )
    : null;
  const marketCapSourceLabel = displayMarketCap
    ? getMarketCapSourceLabel(displayMarketCap.market_cap_source, language)
    : '';

  const metrics = displayDetail?.metrics;
  const oiChange = metrics?.oi_change_24h || '—';
  const fundingRate = metrics?.funding_rate || '—';
  const takerSellRatio = metrics?.taker_sell_ratio;
  const rsi15m = metrics?.rsi_15m;
  const volume24h = metrics?.volume_delta_24h || '—';


  // 3. Exact Two-Tier State
  return (
    <div className="bg-gradient-to-r from-slate-950 via-slate-900/90 to-slate-950 border border-slate-800 rounded-xl p-2.5 sm:p-3.5 shadow-md min-w-0">
      {/* ================= 1. MOBILE VIEW (< sm): BINANCE MOBILE STYLE ================= */}
      <div className="sm:hidden space-y-2">
        {/* Top line: Symbol, Coin Name, CMC, Badges */}
        <div className="flex items-center justify-between gap-1.5 min-w-0">
          <div className="flex items-center gap-1.5 min-w-0">
            <button
              type="button"
              onClick={onOpenCoinSelector}
              className="w-6 h-6 rounded-md bg-gradient-to-br from-amber-500/20 to-amber-600/10 border border-amber-500/40 flex items-center justify-center shrink-0 active:scale-95 cursor-pointer"
              title={t('coin_selector_title')}
            >
              <span className="text-amber-400 font-black text-[10px] font-mono">
                {symbol.replace('USDT', '').slice(0, 3)}
              </span>
            </button>

            <button
              type="button"
              onClick={onOpenCoinSelector}
              className="flex items-center gap-0.5 text-sm font-black text-white hover:text-amber-300 tracking-tight transition"
              title={t('coin_selector_title')}
            >
              <span>{symbol}</span>
              <ChevronDown className="w-3.5 h-3.5 text-amber-400" />
            </button>

            <span className="text-[10px] text-slate-400 truncate max-w-[85px]">({name})</span>

            <a
              href={getCoinExternalUrl(symbol, displayDetail)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-0.5 px-1 py-0.2 text-[9px] font-bold text-blue-400 bg-blue-950/60 border border-blue-800/50 rounded"
              title={language === 'vi' ? 'Xem trên CoinMarketCap' : 'View on CoinMarketCap'}
            >
              <span>CMC</span>
              <ExternalLink className="w-2 h-2 opacity-70" />
            </a>
          </div>

          {/* Status badge */}
          <div className="flex items-center gap-1 shrink-0">
            {selectedSignal?.outcome_status === 'TARGET_HIT' && (
              <span className="px-1.5 py-0.5 text-[9px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-800 rounded flex items-center gap-0.5">
                <CheckCircle2 className="w-2.5 h-2.5" /> {t('ws_hit_status')}
              </span>
            )}
            {['STOPPED_OUT', 'FAILED', 'EXPIRED'].includes(selectedSignal?.outcome_status || '') && (
              <span className="px-1.5 py-0.5 text-[9px] font-bold bg-red-950 text-red-400 border border-red-800 rounded flex items-center gap-0.5">
                <XCircle className="w-2.5 h-2.5" /> {t('ws_missed_status')}
              </span>
            )}
            {selectedSignal?.outcome_status === 'ACTIVE' && (
              <span className="px-1.5 py-0.5 text-[9px] font-bold bg-slate-900 text-slate-400 border border-slate-700 rounded flex items-center gap-0.5">
                <Clock className="w-2.5 h-2.5" /> {t('ws_pending_status')}
              </span>
            )}
            {selectedSignal?.telegram_sent && (
              <span className="px-1.5 py-0.5 text-[9px] font-bold bg-sky-950 text-sky-400 border border-sky-800 rounded flex items-center gap-0.5">
                <Send className="w-2.5 h-2.5" /> TG
              </span>
            )}
          </div>
        </div>

        {/* Binance Mobile Split View: Left Price vs Right 2-Col Key-Value Stats */}
        <div className="flex items-stretch justify-between gap-2 pt-0.5">
          {/* Left Column: Price & 24h Change */}
          <div className="min-w-0 shrink-0 flex flex-col justify-center pr-1 max-w-[42%]">
            <div className="text-xl font-black text-emerald-400 font-mono tracking-tight leading-tight truncate">
              ${currentPrice > 0 ? (currentPrice < 1 ? currentPrice.toFixed(5) : currentPrice.toFixed(4)) : '—'}
            </div>
            <div className="flex items-center gap-1 mt-0.5 flex-wrap">
              {change24h != null && !Number.isNaN(change24h) && (
                <span
                  className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-bold border ${
                    change24h >= 0
                      ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                      : 'bg-red-500/15 text-red-400 border-red-500/30'
                  }`}
                >
                  {change24h >= 0 ? '+' : ''}{change24h.toFixed(2)}%
                </span>
              )}
              {isDeepAnalyzing && (
                <span className="text-[9px] text-amber-400/90 font-mono animate-pulse flex items-center gap-0.5">
                  <Activity className="w-2.5 h-2.5 animate-spin" />
                </span>
              )}
            </div>
          </div>

          {/* Right Column: Binance Mobile 4-row 2-col Clean Key-Value Stats */}
          <div className="grid grid-cols-2 gap-x-2.5 gap-y-1 text-[9px] font-mono flex-1 border-l border-slate-800/80 pl-2">
            {/* Row 1 */}
            <div className="flex items-center justify-between gap-1 min-w-0">
              <span className="text-slate-500 font-sans truncate">
                {language === 'en' ? '24h High' : language === 'zh' ? '24h 最高' : language === 'ko' ? '24h 고가' : '24h Cao'}
              </span>
              <span className="text-emerald-400 font-bold truncate">
                {high24h ? (high24h < 1 ? high24h.toFixed(4) : high24h.toFixed(3)) : '—'}
              </span>
            </div>
            <div className="flex items-center justify-between gap-1 min-w-0">
              <span className="text-slate-500 font-sans truncate">
                {language === 'en' ? '24h OI' : language === 'zh' ? '24h 持仓' : language === 'ko' ? '24h 미결제' : 'HĐ Mở'}
              </span>
              <span className={`font-bold truncate ${oiChange.startsWith('+') ? 'text-emerald-400' : oiChange.startsWith('-') ? 'text-red-400' : 'text-slate-300'}`}>
                {oiChange}
              </span>
            </div>

            {/* Row 2 */}
            <div className="flex items-center justify-between gap-1 min-w-0">
              <span className="text-slate-500 font-sans truncate">
                {language === 'en' ? '24h Low' : language === 'zh' ? '24h 最低' : language === 'ko' ? '24h 저가' : '24h Thấp'}
              </span>
              <span className="text-red-400 font-bold truncate">
                {low24h ? (low24h < 1 ? low24h.toFixed(4) : low24h.toFixed(3)) : '—'}
              </span>
            </div>
            <div className="flex items-center justify-between gap-1 min-w-0">
              <span className="text-slate-500 font-sans truncate">Funding</span>
              <span className="text-amber-400 font-bold truncate">{fundingRate}</span>
            </div>

            {/* Row 3 */}
            <div className="flex items-center justify-between gap-1 min-w-0">
              <span className="text-slate-500 font-sans truncate">
                {language === 'en' ? '24h Vol' : language === 'zh' ? '24h 成交额' : language === 'ko' ? '24h 거래대금' : 'KL 24h'}
              </span>
              <span className="text-slate-300 font-bold truncate">{volume24h}</span>
            </div>
            <div className="flex items-center justify-between gap-1 min-w-0">
              <span className="text-slate-500 font-sans truncate">Taker</span>
              <span className={`font-bold truncate ${takerSellRatio != null && takerSellRatio > 0.55 ? 'text-red-400' : takerSellRatio != null && takerSellRatio < 0.45 ? 'text-emerald-400' : 'text-slate-300'}`}>
                {takerSellRatio != null ? `${(takerSellRatio * 100).toFixed(1)}%` : '—'}
              </span>
            </div>

            {/* Row 4 */}
            <div className="flex items-center justify-between gap-1 min-w-0">
              <span className="text-slate-500 font-sans truncate">
                {language === 'en' ? 'MCap' : language === 'zh' ? '市值' : language === 'ko' ? '시가총액' : 'Vốn Hóa'}
              </span>
              <a
                href={getCoinExternalUrl(symbol, displayDetail)}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-300 font-bold hover:underline truncate"
                title={displayMarketCap ? `${displayMarketCap.market_cap_str} (${marketCapSourceLabel})` : undefined}
              >
                {displayMarketCap ? `${displayMarketCap.market_cap_is_estimate ? '≈' : ''}${displayMarketCap.market_cap_str}` : '—'}
              </a>
            </div>
            <div className="flex items-center justify-between gap-1 min-w-0">
              <span className="text-slate-500 font-sans truncate">RSI 15m</span>
              <span className={`font-bold truncate ${rsi15m == null ? 'text-slate-500' : rsi15m > 70 ? 'text-red-400' : rsi15m < 30 ? 'text-emerald-400' : 'text-amber-300'}`}>
                {rsi15m != null ? rsi15m.toFixed(1) : '—'}
              </span>
            </div>
          </div>
        </div>

        {/* Mobile Slim Decision Bar (Required by tests & user for quick signal check) */}
        <div className="flex items-center justify-between text-[9px] pt-1.5 mt-0.5 border-t border-slate-800/60 font-mono">
          <div className="flex items-center gap-1 min-w-0 truncate">
            <span className="text-slate-500 uppercase tracking-wider font-sans">
              {language === 'en'
                ? 'Current decision'
                : language === 'zh'
                  ? '当前决策'
                  : language === 'ko'
                    ? '현재 판단'
                    : 'Quyết định hiện tại'}
              :
            </span>
            <span className="font-black text-amber-300 truncate">{stateLabel}</span>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {localizedRisk && (
              <span className="rounded bg-red-950/80 border border-red-800/60 px-1 py-0.2 text-[8px] font-bold text-red-300 font-sans">
                {localizedRisk}
              </span>
            )}
            <span className="font-mono text-xs font-black text-amber-400">
              {probabilityPct != null ? `${probabilityPct.toFixed(1)}%` : 'N/A'}
            </span>
          </div>
        </div>
      </div>

      {/* ================= 2. DESKTOP VIEW (sm+): WIDE GRID LAYOUT ================= */}
      <div className="hidden sm:flex flex-col xl:flex-row xl:items-center justify-between gap-3 min-w-0">
        {/* Left: Ticker info & Price */}
        <div className="flex items-center gap-3 min-w-0 shrink-0">
          <button
            type="button"
            onClick={onOpenCoinSelector}
            className="w-10 h-10 sm:w-11 sm:h-11 rounded-xl bg-gradient-to-br from-amber-500/20 to-amber-600/10 border border-amber-500/40 hover:border-amber-400 flex items-center justify-center shrink-0 shadow-inner group transition active:scale-95 cursor-pointer"
            title={t('coin_selector_title')}
          >
            <span className="text-amber-400 group-hover:text-amber-300 font-black text-sm sm:text-base tracking-tight font-mono">
              {symbol.replace('USDT', '').slice(0, 3)}
            </span>
          </button>

          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-0.5">
              <button
                type="button"
                onClick={onOpenCoinSelector}
                className="group flex items-center gap-1 text-base sm:text-lg font-black text-white hover:text-amber-300 tracking-tight transition"
                title={t('coin_selector_title')}
              >
                <span>{symbol}</span>
                <ChevronDown className="w-4 h-4 text-amber-400 group-hover:translate-y-0.5 transition" />
              </button>
              <span className="text-xs font-normal text-slate-400">({name})</span>
              <a
                href={getCoinExternalUrl(symbol, displayDetail)}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-bold text-blue-400 hover:text-blue-200 bg-blue-950/60 hover:bg-blue-900/60 border border-blue-800/50 rounded-md transition shadow-sm group cursor-pointer"
                title={language === 'vi' ? 'Xem trên CoinMarketCap' : 'View on CoinMarketCap'}
              >
                <span>CMC</span>
                <ExternalLink className="w-2.5 h-2.5 opacity-70 group-hover:opacity-100" />
              </a>

              {/* Status Badges */}
              {selectedSignal?.outcome_status === 'TARGET_HIT' && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-800 rounded-md flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> {t('ws_hit_status')}
                </span>
              )}
              {['STOPPED_OUT', 'FAILED', 'EXPIRED'].includes(selectedSignal?.outcome_status || '') && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold bg-red-950 text-red-400 border border-red-800 rounded-md flex items-center gap-1">
                  <XCircle className="w-3 h-3" /> {t('ws_missed_status')}
                </span>
              )}
              {selectedSignal?.outcome_status === 'ACTIVE' && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold bg-slate-900 text-slate-400 border border-slate-700 rounded-md flex items-center gap-1">
                  <Clock className="w-3 h-3" /> {t('ws_pending_status')}
                </span>
              )}
              {selectedSignal?.telegram_sent && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold bg-sky-950 text-sky-400 border border-sky-800 rounded-md flex items-center gap-1">
                  <Send className="w-3 h-3" /> Telegram
                </span>
              )}
            </div>

            {/* Live Price, 24h Change & Indicator */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-2xl sm:text-3xl font-black text-emerald-400 font-mono tracking-tight">
                ${currentPrice > 0 ? (currentPrice < 1 ? currentPrice.toFixed(5) : currentPrice.toFixed(4)) : '—'}
              </span>
              {change24h != null && !Number.isNaN(change24h) && (
                <span
                  className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono font-bold border ${
                    change24h >= 0
                      ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                      : 'bg-red-500/15 text-red-400 border-red-500/30'
                  }`}
                  title={
                    language === 'en'
                      ? '24h Price Change'
                      : language === 'zh'
                        ? '24小时涨跌幅'
                        : language === 'ko'
                          ? '24시간 가격 변동'
                          : 'Biến động giá 24h'
                  }
                >
                  {change24h >= 0 ? '+' : ''}{change24h.toFixed(2)}%
                </span>
              )}
              {isDeepAnalyzing && (
                <span className="text-[10px] text-amber-400/90 font-mono animate-pulse flex items-center gap-1">
                  <Activity className="w-3 h-3 animate-spin" /> {t('refreshing')}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Right: Comprehensive Market Metrics Grid (Desktop) */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5 sm:gap-2 text-[10px] font-mono min-w-0">
          {/* 1. Market Cap */}
          <a
            href={getCoinExternalUrl(symbol, displayDetail)}
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col justify-center px-2.5 py-1.5 bg-slate-900/90 hover:bg-slate-800 border border-slate-800 hover:border-blue-500/60 rounded-lg transition group min-w-[100px]"
            title={
              displayMarketCap
                ? `${t('metric_market_cap', 'Vốn Hóa')}: ${displayMarketCap.market_cap_str} · ${displayMarketCap.market_cap_tier} (${marketCapSourceLabel})`
                : t('metric_market_cap', 'Vốn Hóa')
            }
          >
            <div className="flex items-center justify-between text-[9px] font-sans text-slate-400 uppercase tracking-wider">
              <span>{t('metric_market_cap', 'Vốn Hóa')}</span>
              <ExternalLink className="w-2.5 h-2.5 opacity-60 group-hover:opacity-100 text-blue-400 transition" />
            </div>
            <div className="flex items-center gap-1 font-bold text-blue-300 truncate">
              <span>
                {displayMarketCap ? `${displayMarketCap.market_cap_is_estimate ? '≈' : ''}${displayMarketCap.market_cap_str}` : '—'}
              </span>
              {displayMarketCap?.market_cap_tier && (
                <span className="text-[9px] px-1 rounded bg-blue-950/80 text-blue-300 border border-blue-800/40">
                  {marketCapBadge?.icon} {displayMarketCap.market_cap_tier}
                </span>
              )}
            </div>
          </a>

          {/* 2. Open Interest (24h) */}
          <div className="flex flex-col justify-center px-2.5 py-1.5 bg-slate-900/90 border border-slate-800 rounded-lg min-w-[100px]">
            <span className="text-[9px] font-sans text-slate-400 uppercase tracking-wider truncate">
              {t('metric_oi_24h', 'HĐ Mở 24h')}
            </span>
            <span
              className={`font-bold truncate ${
                oiChange.startsWith('+') ? 'text-emerald-400' : oiChange.startsWith('-') ? 'text-red-400' : 'text-slate-200'
              }`}
              title={oiChange}
            >
              {oiChange}
            </span>
          </div>

          {/* 3. Funding Rate */}
          <div className="flex flex-col justify-center px-2.5 py-1.5 bg-slate-900/90 border border-slate-800 rounded-lg min-w-[100px]">
            <span className="text-[9px] font-sans text-slate-400 uppercase tracking-wider truncate">
              {t('metric_funding', 'Funding Rate')}
            </span>
            <span className="text-amber-400 font-bold truncate" title={fundingRate}>
              {fundingRate}
            </span>
          </div>

          {/* 4. Taker Sell Ratio */}
          <div className="flex flex-col justify-center px-2.5 py-1.5 bg-slate-900/90 border border-slate-800 rounded-lg min-w-[100px]">
            <span className="text-[9px] font-sans text-slate-400 uppercase tracking-wider truncate">
              {t('metric_taker_sell', 'Taker Sell')}
            </span>
            <span
              className={`font-bold truncate ${
                takerSellRatio != null && takerSellRatio > 0.55
                  ? 'text-red-400'
                  : takerSellRatio != null && takerSellRatio < 0.45
                  ? 'text-emerald-400'
                  : 'text-slate-200'
              }`}
            >
              {takerSellRatio != null ? `${(takerSellRatio * 100).toFixed(1)}%` : '—'}
            </span>
          </div>

          {/* 5. RSI (15M) */}
          <div className="flex flex-col justify-center px-2.5 py-1.5 bg-slate-900/90 border border-slate-800 rounded-lg min-w-[100px]">
            <span className="text-[9px] font-sans text-slate-400 uppercase tracking-wider truncate">
              {t('metric_rsi_15m', 'RSI (15M)')}
            </span>
            <span
              className={`font-bold truncate ${
                rsi15m == null ? 'text-slate-500' : rsi15m > 70 ? 'text-red-400' : rsi15m < 30 ? 'text-emerald-400' : 'text-amber-300'
              }`}
            >
              {rsi15m != null ? rsi15m.toFixed(1) : '—'}
            </span>
          </div>

          {/* 6. 24h High */}
          <div className="flex flex-col justify-center px-2.5 py-1.5 bg-slate-900/90 border border-slate-800 rounded-lg min-w-[100px]">
            <span className="text-[9px] font-sans text-slate-400 uppercase tracking-wider truncate">
              {language === 'en' ? '24h High' : language === 'zh' ? '24h 最高价' : language === 'ko' ? '24h 고가' : 'Giá cao 24h'}
            </span>
            <span className="text-emerald-400 font-bold truncate">
              {high24h ? (high24h < 1 ? high24h.toFixed(5) : high24h.toFixed(4)) : '—'}
            </span>
          </div>

          {/* 7. 24h Low */}
          <div className="flex flex-col justify-center px-2.5 py-1.5 bg-slate-900/90 border border-slate-800 rounded-lg min-w-[100px]">
            <span className="text-[9px] font-sans text-slate-400 uppercase tracking-wider truncate">
              {language === 'en' ? '24h Low' : language === 'zh' ? '24h 最低价' : language === 'ko' ? '24h 저가' : 'Giá thấp 24h'}
            </span>
            <span className="text-red-400 font-bold truncate">
              {low24h ? (low24h < 1 ? low24h.toFixed(5) : low24h.toFixed(4)) : '—'}
            </span>
          </div>

          {/* 8. 24h Volume */}
          <div className="flex flex-col justify-center px-2.5 py-1.5 bg-slate-900/90 border border-slate-800 rounded-lg min-w-[100px]">
            <span className="text-[9px] font-sans text-slate-400 uppercase tracking-wider truncate">
              {language === 'en' ? '24h Vol' : language === 'zh' ? '24h 成交额' : language === 'ko' ? '24h 거래대금' : 'Khối lượng 24h'}
            </span>
            <span className="text-slate-200 font-bold truncate" title={volume24h}>
              {volume24h}
            </span>
          </div>
        </div>
      </div>

      {/* Bottom: Hot Candidates Chips for fast 1-click switching */}
      {topCandidates.length > 0 && (
        <div className="hidden sm:flex items-center gap-1.5 overflow-x-auto max-w-full pt-3 mt-3 border-t border-slate-800/50 shrink-0">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1 shrink-0">
            <Flame className="w-3 h-3 text-orange-400" />
            {t('decision_hot_coins')}:
          </span>
          {topCandidates.map((c) => {
            const isSelected = c.symbol === symbol;
            return (
              <button
                key={c.symbol}
                type="button"
                onClick={() => onSelectCandidate(c.symbol)}
                className={`px-2 py-1 rounded-md text-xs font-mono font-bold shrink-0 transition border flex items-center gap-1.5 active:scale-95 ${
                  isSelected
                    ? 'bg-amber-500 text-slate-950 border-amber-400 shadow-sm shadow-amber-500/30 font-extrabold'
                    : 'bg-slate-900/90 text-slate-300 border-slate-700/80 hover:border-amber-500/50 hover:text-amber-300'
                }`}
                title={`${t('decision_switch_to')} ${c.symbol}`}
              >
                <span>{c.symbol.replace('USDT', '')}</span>
                <span className={`text-[10px] ${isSelected ? 'text-slate-950 font-black' : 'text-amber-400 font-bold'}`}>
                  {c.score?.toFixed(0)}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

