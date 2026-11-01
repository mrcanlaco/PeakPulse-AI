import React from 'react';
import {
  TrendingDown, Eye, EyeOff, CheckCircle2, Zap, Send, XCircle, Loader2
} from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';
import { formatSystemTime } from '../../utils/time';
import { getRiskLabel } from '../../i18n/translations';
import { normalizeProbability, ALERT_THRESHOLD_PCT } from '../../types';
import type { CoinDetail, DeepAnalysis, SignalItem } from '../../types';

interface AiDecisionCockpitProps {
  selectedSignal?: SignalItem | null;
  displayDetail: CoinDetail;
  deepAnalysis?: DeepAnalysis | null;
  isDeepAnalyzing?: boolean;
  isSymbolTracked?: boolean;
  isSymbolInWatchlist?: boolean;
  isWatchlistUpdating?: boolean;
  onRunDeepAnalysis: (symbol: string) => void;
  onPushTelegram?: (sig: SignalItem) => void;
  onDismissSignal?: (sig: SignalItem) => void;
  onAddWatchlist?: (symbol: string) => void | Promise<boolean | void>;
  onAddTracking?: (symbol: string) => void | Promise<boolean | void>;
  onRemoveTracking?: (symbol: string) => void | Promise<boolean | void>;
}

export const AiDecisionCockpit: React.FC<AiDecisionCockpitProps> = ({
  selectedSignal,
  displayDetail,
  deepAnalysis,
  isDeepAnalyzing,
  isSymbolTracked,
  isSymbolInWatchlist,
  isWatchlistUpdating,
  onRunDeepAnalysis,
  onPushTelegram,
  onDismissSignal,
  onAddWatchlist,
  onAddTracking,
  onRemoveTracking,
}) => {
  const { language, t } = useTranslation();
  
  
  const riskLabels: Record<string, string> = {
    CRITICAL: getRiskLabel('CRITICAL', language),
    HIGH: getRiskLabel('HIGH', language),
    MEDIUM: getRiskLabel('MEDIUM', language),
    SAFE: getRiskLabel('SAFE', language),
  };


  const isDeepMatching = Boolean(deepAnalysis && (!deepAnalysis.symbol || deepAnalysis.symbol.toUpperCase() === displayDetail.symbol.toUpperCase()));
  const rawDeepProb = isDeepMatching ? (deepAnalysis?.calibrated_probability ?? deepAnalysis?.model_probability) : null;
  const deepProbabilityPct = normalizeProbability(rawDeepProb);

  const matchedSignal = selectedSignal && selectedSignal.symbol.toUpperCase() === displayDetail.symbol.toUpperCase() ? selectedSignal : null;
  const signalProbPct = normalizeProbability(matchedSignal?.probability);
  const detailProbPct = normalizeProbability(displayDetail.probability);


  const effectiveProbabilityPct = signalProbPct ?? deepProbabilityPct ?? detailProbPct;

  const twoTierLabel = (state?: string | null) => {
    if (state === 'FIRED') return t('feed_tag_fired');
    if (state === 'ARMED') return t('feed_tag_armed');
    if (state === 'WATCH') return t('ws_rec_watch_badge');
    if (state === 'NORMAL' || state === 'STANDBY') return t('ws_rec_standby_badge');
    return state || '—';
  };

  const signalState = matchedSignal?.two_tier_state;
  const passesQualityGate = effectiveProbabilityPct != null && effectiveProbabilityPct >= ALERT_THRESHOLD_PCT;
  const recommendation = passesQualityGate
    ? 'SHORT_CANDIDATE'
    : (signalState === 'FIRED' || signalState === 'ARMED' || (effectiveProbabilityPct != null && effectiveProbabilityPct >= 50))
    ? 'WATCH'
    : (isDeepMatching ? (deepAnalysis?.recommendation === 'SHORT_CANDIDATE' ? 'WATCH' : deepAnalysis?.recommendation) : null) || 'STANDBY';
  return (
    <div className="space-y-2 min-w-0">
      {/* 1. Ultra-compact AI Recommendation & Probability */}
      <div className={`rounded-xl p-2.5 border-2 shadow-sm flex items-center justify-between gap-2 ${
        recommendation === 'SHORT_CANDIDATE'
          ? 'bg-gradient-to-r from-red-950/60 to-slate-900 border-red-700/80'
          : recommendation === 'WATCH'
          ? 'bg-gradient-to-r from-amber-950/60 to-slate-900 border-amber-700/80'
          : 'bg-slate-900 border-slate-700'
      }`}>
        <div className="flex items-center gap-2">
          {recommendation === 'SHORT_CANDIDATE' ? <TrendingDown className="w-5 h-5 text-red-400" /> :
           recommendation === 'WATCH' ? <Eye className="w-5 h-5 text-amber-400" /> :
           <CheckCircle2 className="w-5 h-5 text-slate-400" />}
          <div>
            <div className={`text-sm font-black tracking-tight ${
              recommendation === 'SHORT_CANDIDATE' ? 'text-red-400' :
              recommendation === 'WATCH' ? 'text-amber-400' : 'text-slate-300'
            }`}>
              {recommendation === 'SHORT_CANDIDATE' ? t('ws_rec_short_badge') : recommendation === 'WATCH' ? t('ws_rec_watch_badge') : t('ws_rec_standby_badge')}
            </div>
            <div className="flex items-center gap-1 mt-0.5">
              <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold border uppercase ${
                displayDetail.risk_level === 'CRITICAL' ? 'bg-red-950 text-red-300 border-red-800' :
                displayDetail.risk_level === 'HIGH' ? 'bg-amber-950 text-amber-300 border-amber-800' :
                displayDetail.risk_level === 'MEDIUM' ? 'bg-yellow-950 text-yellow-300 border-yellow-800' :
                'bg-slate-800 text-slate-300 border-slate-700'
              }`}>
                {displayDetail.risk_level ? (riskLabels[displayDetail.risk_level] ?? displayDetail.risk_level) : 'N/A'}
              </span>
              {(matchedSignal || (isDeepMatching && deepAnalysis?.two_tier_analysis)) && (
                <span className="text-[9px] font-mono text-violet-400 ml-1">
                  {language === 'en' ? 'Tier score' : 'Điểm hai tầng'}: {deepAnalysis?.two_tier_analysis?.total_score ?? '—'}
                </span>
              )}
            </div>
            {selectedSignal && (
              <div className="text-[9px] font-mono text-slate-400 mt-1">
                Lúc: <strong className="text-amber-400/90">{formatSystemTime(selectedSignal.signal_time)}</strong> • Giá báo: <strong className="text-slate-300">${selectedSignal.signal_price < 1 ? selectedSignal.signal_price.toFixed(5) : selectedSignal.signal_price.toFixed(2)}</strong>
              </div>
            )}
          </div>
        </div>
        
        <div className="text-right shrink-0">
          <div className="text-[9px] text-slate-400 uppercase font-mono">{t('ws_dump_prob_title')}</div>
          <div className="text-xl sm:text-2xl font-black text-amber-400 font-mono">
            {effectiveProbabilityPct != null ? `${effectiveProbabilityPct.toFixed(1)}%` : 'N/A'}
          </div>
        </div>
      </div>

      {/* 2. Compact 2-Tier Climax Badges (No Text Walls) */}
      {(matchedSignal || (isDeepMatching && deepAnalysis?.two_tier_analysis)) && (
        <div className="grid grid-cols-2 gap-1.5">
          <div className={`p-1.5 rounded-lg border flex items-center justify-between text-[9px] font-mono ${
            matchedSignal?.two_tier_state === 'FIRED' || matchedSignal?.two_tier_state === 'ARMED' || deepAnalysis?.two_tier_analysis?.htf_state === 'ARMED'
              ? 'bg-red-950/40 border-red-800/60' : 'bg-slate-900/60 border-slate-800'
          }`}>
            <span className="text-slate-400">HTF (1)</span>
            <span className={`px-1 py-0.5 rounded font-bold ${
              matchedSignal?.two_tier_state === 'FIRED' || matchedSignal?.two_tier_state === 'ARMED' || deepAnalysis?.two_tier_analysis?.htf_state === 'ARMED'
                ? 'bg-red-900 text-red-200 animate-pulse' : 'text-slate-500'
            }`}>
              {twoTierLabel((matchedSignal?.two_tier_state === 'FIRED' || matchedSignal?.two_tier_state === 'ARMED') ? 'ARMED' : deepAnalysis?.two_tier_analysis?.htf_state)}
            </span>
          </div>
          <div className={`p-1.5 rounded-lg border flex items-center justify-between text-[9px] font-mono ${
            matchedSignal?.two_tier_state === 'FIRED' || deepAnalysis?.two_tier_analysis?.ltf_state === 'FIRED'
              ? 'bg-amber-950/40 border-amber-800/60' : 'bg-slate-900/60 border-slate-800'
          }`}>
            <span className="text-slate-400">LTF (2)</span>
            <span className={`px-1 py-0.5 rounded font-bold ${
              matchedSignal?.two_tier_state === 'FIRED' || deepAnalysis?.two_tier_analysis?.ltf_state === 'FIRED'
                ? 'bg-amber-500 text-slate-950' : 'text-slate-500'
            }`}>
              {twoTierLabel(matchedSignal?.two_tier_state === 'FIRED' ? 'FIRED' : deepAnalysis?.two_tier_analysis?.ltf_state)}
            </span>
          </div>
        </div>
      )}

      {/* 3. Ultra-compact Actions Grid */}
      <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-2 shadow-sm space-y-2">
        <div className="grid grid-cols-2 gap-2">
          {/* Re-score Button */}
          <button
            onClick={() => onRunDeepAnalysis(displayDetail.symbol)}
            disabled={isDeepAnalyzing}
            className="px-3 py-2 bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-slate-950 font-bold rounded-lg text-xs flex items-center justify-center gap-1.5 transition shadow-md shadow-amber-500/20"
          >
            {isDeepAnalyzing ? (
              <><Loader2 className="w-3.5 h-3.5 animate-spin" /> {t('refreshing')}</>
            ) : (
              <><Zap className="w-3.5 h-3.5" /> {t('ws_rescore_btn')}</>
            )}
          </button>

          {/* Telegram Send */}
          {selectedSignal ? (
            <button
              onClick={() => onPushTelegram && onPushTelegram(selectedSignal)}
              className="px-3 py-2 bg-sky-600 hover:bg-sky-500 text-white font-bold rounded-lg text-xs flex items-center justify-center gap-1.5 transition shadow-md shadow-sky-500/20"
            >
              <Send className="w-3.5 h-3.5" /> {t('ws_send_telegram_btn')}
            </button>
          ) : (
            <div className="px-3 py-2 bg-slate-900 border border-slate-800 text-slate-500 rounded-lg text-xs text-center font-mono">
              {t('cockpit_no_telegram_signal')}
            </div>
          )}

          {/* Track / Untrack Position */}
          {(onAddTracking || onRemoveTracking) && (
            <button
              onClick={() => {
                if (isSymbolTracked && onRemoveTracking) {
                  void onRemoveTracking(displayDetail.symbol);
                } else if (!isSymbolTracked && onAddTracking) {
                  void onAddTracking(displayDetail.symbol);
                }
              }}
              disabled={isWatchlistUpdating}
              className={`group/track px-3 py-2 border font-bold rounded-lg text-xs flex items-center justify-center gap-1.5 transition disabled:cursor-not-allowed disabled:opacity-70 ${
                isSymbolTracked
                  ? 'bg-sky-500/15 text-sky-300 border-sky-500/40 hover:bg-red-950/80 hover:text-red-300 hover:border-red-700/80'
                  : 'bg-slate-900 hover:bg-sky-950 text-slate-300 hover:text-sky-400 border-slate-700 hover:border-sky-800'
              }`}
              title={isSymbolTracked ? t('ws_untrack_position') : t('ws_track_position')}
            >
              {isWatchlistUpdating ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : isSymbolTracked ? (
                <>
                  <CheckCircle2 className="w-3.5 h-3.5 group-hover/track:hidden text-sky-400" />
                  <EyeOff className="w-3.5 h-3.5 hidden group-hover/track:inline text-red-400" />
                  <span className="group-hover/track:hidden">{t('ws_tracking_pos')}</span>
                  <span className="hidden group-hover/track:inline">{t('ws_untrack_position')}</span>
                </>
              ) : (
                <>
                  <Eye className="w-3.5 h-3.5" />
                  <span>{t('ws_track_position')}</span>
                </>
              )}
            </button>
          )}

          {/* Add to Scan Universe */}
          {onAddWatchlist && (
            <button
              onClick={() => void onAddWatchlist(displayDetail.symbol)}
              disabled={isWatchlistUpdating || isSymbolInWatchlist}
              className={`px-3 py-2 border font-bold rounded-lg text-xs flex items-center justify-center gap-1.5 transition disabled:cursor-not-allowed disabled:opacity-70 ${
                isSymbolInWatchlist
                  ? 'bg-amber-500/15 text-amber-300 border-amber-500/40'
                  : 'bg-slate-900 hover:bg-amber-950 text-slate-300 hover:text-amber-400 border-slate-700 hover:border-amber-800'
              }`}
            >
              {isWatchlistUpdating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : isSymbolInWatchlist ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
              {isSymbolInWatchlist ? t('ws_in_scan_universe') : t('ws_add_to_scan_universe')}
            </button>
          )}
        </div>

        {selectedSignal && onDismissSignal && (
          <button
            onClick={() => onDismissSignal(selectedSignal)}
            className="w-full mt-1 px-3 py-1.5 bg-slate-900 hover:bg-red-950/80 text-slate-400 hover:text-red-400 border border-slate-800 hover:border-red-800/80 font-bold rounded-lg text-xs flex items-center justify-center gap-1.5 transition"
          >
            <XCircle className="w-3.5 h-3.5" /> {t('ws_dismiss_btn')}
          </button>
        )}
      </div>
    </div>
  );
};
