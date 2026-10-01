import { useEffect, useMemo, useRef, useState } from 'react';
import {
  createChart,
  createSeriesMarkers,
  ColorType,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
} from 'lightweight-charts';
import { Camera, ChevronDown, Filter, Maximize2, Minimize2, RotateCcw, ZoomIn, ZoomOut, Settings } from 'lucide-react';
import { formatSystemDateTime, parseSystemDate, SYSTEM_TIME_ZONE } from '../utils/time';
import { calculateEMA } from '../utils/indicators';
import { useTranslation } from '../i18n/LanguageContext';
import type { TradeSetup } from '../types';

type AlertVisibilityMode = 'hidden' | 'latest' | 'all' | 'valid';

export interface CandlestickSignalMarker {
  id?: string;
  time: string;
  probability?: number | null;
  isActive?: boolean;
  isValid?: boolean;
  episodeRole?: string | null;
  episodeTransition?: string | null;
  riskLevel?: string | null;
  tier?: string | null;
  telegramSent?: boolean;
}

interface CandlestickChartProps {
  symbol?: string;
  data: Array<{
    time: number | string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume?: number;
  }>;
  targetPrice?: number;
  height?: number;
  signalMarkers?: CandlestickSignalMarker[];
  // Kept as a fallback for callers that only have one signal.
  signalTime?: string;
  signalProbability?: number | null;
  tradeSetup?: TradeSetup | null;
  interval?: string;
  onIntervalChange?: (interval: string) => void;
}
export const CandlestickChart: React.FC<CandlestickChartProps> = ({
  symbol,
  data,
  targetPrice,
  height = 400,
  signalMarkers: signalMarkerInputs,
  signalTime,
  signalProbability,
  tradeSetup,
  interval,
  onIntervalChange,
}) => {
  const { language, t } = useTranslation();
  const chartShellRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const alertMenuRef = useRef<HTMLDivElement>(null);
  const settingsMenuRef = useRef<HTMLDivElement>(null);
  const logicalRangeRef = useRef<any>(null);
  const priceRangeRef = useRef<{ from: number; to: number } | null>(null);
  const lastKeyRef = useRef<string>('');
  const [crosshairMode, setCrosshairMode] = useState<'magnet' | 'normal' | 'hidden'>('magnet');
  const [gridVisible, setGridVisible] = useState(true);
  const [priceAutoScale, setPriceAutoScale] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [alertVisibility, setAlertVisibility] = useState<AlertVisibilityMode>('all');
  const [alertMenuOpen, setAlertMenuOpen] = useState(false);
  const [showTradeSetup, setShowTradeSetup] = useState(false);
  const [showEMA, setShowEMA] = useState(false);
  const [showVolume, setShowVolume] = useState(true);
  const [settingsMenuOpen, setSettingsMenuOpen] = useState(false);

  const getAlertVisibilityOptions = (): Array<{ value: AlertVisibilityMode; label: string; hint: string }> => {
    return [
      { value: 'hidden', label: t('chart_alert_hidden'), hint: t('chart_alert_hidden') },
      { value: 'latest', label: t('chart_alert_latest'), hint: t('chart_alert_latest') },
      { value: 'all', label: t('chart_alert_all'), hint: t('chart_alert_all') },
      { value: 'valid', label: t('chart_alert_valid'), hint: t('chart_alert_valid') },
    ];
  };

  const alertVisibilityOptions = getAlertVisibilityOptions();

  const getAlertVisibilityLabel = (mode: AlertVisibilityMode): string => {
    switch (mode) {
      case 'hidden': return t('chart_alert_hidden');
      case 'latest': return t('chart_alert_latest');
      case 'all': return t('chart_alert_all');
      case 'valid': return t('chart_alert_valid');
      default: return mode;
    }
  };

  const formatSignalTime = (time: string, compact = false): string => {
    if (/^\d{2}:\d{2}$/.test(time)) return time;

    const parsed = parseSystemDate(time);
    if (!parsed) return time;

    const locale = language === 'zh' ? 'zh-CN' : language === 'ko' ? 'ko-KR' : language === 'en' ? 'en-US' : 'vi-VN';
    return new Intl.DateTimeFormat(locale, compact ? {
      timeZone: SYSTEM_TIME_ZONE,
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    } : {
      timeZone: SYSTEM_TIME_ZONE,
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(parsed);
  };

  const allSignalMarkers = useMemo<CandlestickSignalMarker[]>(() => (
    signalMarkerInputs?.length
      ? signalMarkerInputs
      : signalTime
        ? [{ time: signalTime, probability: signalProbability }]
        : []
  ), [signalMarkerInputs, signalTime, signalProbability]);

  const visibleSignalMarkers = useMemo<CandlestickSignalMarker[]>(() => {
    if (alertVisibility === 'hidden') return [];

    const parseSignalTimestamp = (time: string): number => {
      if (/^\d{2}:\d{2}$/.test(time)) {
        const [hours, minutes] = time.split(':').map(Number);
        return hours * 60 + minutes;
      }
      const parsed = parseSystemDate(time)?.getTime() ?? Number.NaN;
      return Number.isFinite(parsed) ? parsed : Number.POSITIVE_INFINITY;
    };

    const orderedMarkers = allSignalMarkers.filter(marker => Number.isFinite(parseSignalTimestamp(marker.time))).sort((a, b) => {
      return parseSignalTimestamp(a.time) - parseSignalTimestamp(b.time);
    });

    if (alertVisibility === 'latest') return orderedMarkers.slice(-1);
    if (alertVisibility === 'valid') return orderedMarkers.filter(marker => marker.isValid);
    return orderedMarkers;
  }, [alertVisibility, allSignalMarkers]);

  const toolButtonClass = 'inline-flex h-7 shrink-0 items-center gap-1 whitespace-nowrap rounded border border-slate-700/80 bg-slate-900/90 px-2 text-[10px] font-medium text-slate-300 transition hover:border-amber-500/70 hover:bg-slate-800 hover:text-amber-300 disabled:cursor-not-allowed disabled:opacity-40';

  const applyPriceScaleMode = (autoScale: boolean) => {
    setPriceAutoScale(autoScale);
    if (autoScale) priceRangeRef.current = null;
    chartRef.current?.priceScale('right').applyOptions({ autoScale });
  };

  const adjustZoom = (factor: number) => {
    const timeScale = chartRef.current?.timeScale();
    const range = timeScale?.getVisibleLogicalRange();
    if (!timeScale || !range) return;

    const center = (range.from + range.to) / 2;
    const halfWidth = Math.max(4, ((range.to - range.from) * factor) / 2);
    timeScale.setVisibleLogicalRange({
      from: center - halfWidth,
      to: center + halfWidth,
    });
  };

  const handleResetView = () => {
    const chart = chartRef.current;
    if (!chart) return;
    priceRangeRef.current = null;
    chart.timeScale().scrollToPosition(0, false);
    chart.priceScale('right').applyOptions({ autoScale: true });
    setTimeout(() => applyPriceScaleMode(false), 50);
  };

  const handleScreenshot = () => {
    const canvas = chartRef.current?.takeScreenshot(true);
    if (!canvas) return;

    const link = document.createElement('a');
    link.download = `dao-vang-${formatSystemDateTime(new Date().toISOString()).slice(0, 10)}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
  };

  const handleFullscreen = async () => {
    if (!chartShellRef.current) return;

    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else {
        await chartShellRef.current.requestFullscreen();
      }
    } catch (error) {
      console.warn('Chart fullscreen is not available:', error);
    }
  };

  const chartHeight = isFullscreen
    ? Math.max(320, window.innerHeight - 32)
    : height;

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === chartShellRef.current);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  useEffect(() => {
    const handleOutsidePointerDown = (event: PointerEvent) => {
      if (alertMenuRef.current && !alertMenuRef.current.contains(event.target as Node)) {
        setAlertMenuOpen(false);
      }
      if (settingsMenuRef.current && !settingsMenuRef.current.contains(event.target as Node)) {
        setSettingsMenuOpen(false);
      }
    };
    document.addEventListener('pointerdown', handleOutsidePointerDown);
    return () => document.removeEventListener('pointerdown', handleOutsidePointerDown);
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    chart.applyOptions({
      crosshair: {
        mode: crosshairMode === 'magnet' ? 1 : crosshairMode === 'normal' ? 0 : 2,
      },
      grid: {
        vertLines: { visible: gridVisible },
        horzLines: { visible: gridVisible },
      },
    });
    chart.priceScale('right').applyOptions({ autoScale: priceAutoScale });
  }, [crosshairMode, gridVisible, priceAutoScale]);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    const parseTime = (time: number | string, fallbackIndex?: number): number => {
      if (typeof time === 'string') {
        if (time.match(/^\d{2}:\d{2}$/)) {
          return fallbackIndex ?? -1;
        }
        const parsed = parseSystemDate(time)?.getTime() ?? Number.NaN;
        return Number.isFinite(parsed) ? Math.floor(parsed / 1000) : Number.NaN;
      }
      return time > 1e10 ? Math.floor(time / 1000) : time;
    };

    const normalizedCandles = data.map((d, index) => ({
      sourceTime: d.time,
      time: parseTime(d.time, index),
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
      volume: d.volume || 0,
    })).filter(d =>
      Number.isFinite(d.time) &&
      [d.open, d.high, d.low, d.close].every(value => value != null && Number.isFinite(value)),
    ).sort((a, b) => a.time - b.time);

    const candleData = normalizedCandles.map(d => ({
      time: d.time as any,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    const volumeData = normalizedCandles.map(d => ({
      time: d.time as any,
      value: d.volume,
      color: d.close >= d.open ? 'rgba(38, 166, 154, 0.5)' : 'rgba(239, 83, 80, 0.5)',
    }));

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: chartHeight,
      layout: {
        background: { type: ColorType.Solid, color: '#0f172a' },
        textColor: '#94a3b8',
        fontSize: 10,
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      crosshair: {
        mode: 1,
        vertLine: { color: '#f59e0b', width: 1, style: 2 },
        horzLine: { color: '#f59e0b', width: 1, style: 2 },
      },
      rightPriceScale: {
        borderColor: '#334155',
        scaleMargins: { top: 0.1, bottom: 0.25 },
        autoScale: false,
        minimumWidth: 50,
      },
      timeScale: {
        borderColor: '#334155',
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
      handleScale: {
        axisPressedMouseMove: {
          time: true,
          price: true,
        },
        axisDoubleClickReset: {
          time: true,
          price: true,
        },
        mouseWheel: true,
        pinch: true,
      },
      trackingMode: {
        exitMode: 0,
      },
    });

    chartRef.current = chart;

    // Candlestick series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    });
    
    candleSeries.setData(candleData as any);

    // Volume series (histogram at bottom)
    if (showVolume) {
      const volumeSeries = chart.addSeries(HistogramSeries, {
        priceFormat: { type: 'volume' },
        priceScaleId: 'vol',
      });
      chart.priceScale('vol').applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 },
      });
      volumeSeries.setData(volumeData);
    }

    // EMA series
    if (showEMA) {
      const ema20Series = chart.addSeries(LineSeries, {
        color: '#facc15',
        lineWidth: 1,
        crosshairMarkerVisible: false,
      });
      // @ts-ignore - known type mismatch for lightweight-charts time
      ema20Series.setData(calculateEMA(candleData, 20));

      const ema50Series = chart.addSeries(LineSeries, {
        color: '#c084fc',
        lineWidth: 1,
        crosshairMarkerVisible: false,
      });
      // @ts-ignore
      ema50Series.setData(calculateEMA(candleData, 50));
    }

    // Trade Setup & Target Price Lines
    if (tradeSetup && showTradeSetup) {
      // Entry Line
      if (tradeSetup.entryPrice > 0) {
        candleSeries.createPriceLine({
          price: tradeSetup.entryPrice,
          color: '#f59e0b',
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: t('chart_entry_label'),
        });
      }
      // Stop Loss Line
      if (tradeSetup.stopLossPrice > 0) {
        candleSeries.createPriceLine({
          price: tradeSetup.stopLossPrice,
          color: '#ef4444',
          lineWidth: 2,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `${t('trade_stop_loss')} (+${tradeSetup.stopLossPct.toFixed(1)}%)`,
        });
      }
      // TP1 Line
      if (tradeSetup.tp1Price > 0) {
        candleSeries.createPriceLine({
          price: tradeSetup.tp1Price,
          color: '#10b981',
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `${t('trade_target_1')} (-${tradeSetup.tp1Pct.toFixed(1)}%)`,
        });
      }
      // TP2 Line
      if (tradeSetup.tp2Price > 0) {
        candleSeries.createPriceLine({
          price: tradeSetup.tp2Price,
          color: '#059669',
          lineWidth: 2,
          lineStyle: 0,
          axisLabelVisible: true,
          title: `${t('trade_target_2')} (-${tradeSetup.tp2Pct.toFixed(1)}%)`,
        });
      }
    }

    let signalMarkersApi: any = null;
    if (visibleSignalMarkers.length > 0 && normalizedCandles.length > 0) {
      const positiveSteps = normalizedCandles.slice(1).map((candle, index) =>
        Math.abs(candle.time - normalizedCandles[index].time),
      ).filter(step => step > 0);
      const sortedSteps = [...positiveSteps].sort((a, b) => a - b);
      const candleStep = sortedSteps.length > 0
        ? sortedSteps[Math.floor(sortedSteps.length / 2)]
        : 0;
      const maxMarkerDistance = candleStep > 0 ? Math.max(candleStep * 1.5, 60) : 0;

      const resolvedMarkers = visibleSignalMarkers.flatMap((signal, index) => {
        let signalTimestamp: number | undefined;

        if (/^\d{2}:\d{2}$/.test(signal.time)) {
          signalTimestamp = normalizedCandles.find(c => c.sourceTime === signal.time)?.time;
        } else {
          const parsedSignalDate = parseSystemDate(signal.time)?.getTime() ?? Number.NaN;
          const parsedSignalTime = Number.isFinite(parsedSignalDate)
            ? Math.floor(parsedSignalDate / 1000)
            : Number.NaN;
          if (Number.isFinite(parsedSignalTime)) {
            const nearest = normalizedCandles.reduce((best, candle) =>
              Math.abs(candle.time - parsedSignalTime) < Math.abs(best.time - parsedSignalTime)
                ? candle
                : best,
            );
            if (!maxMarkerDistance || Math.abs(nearest.time - parsedSignalTime) <= maxMarkerDistance) {
              signalTimestamp = nearest.time;
            }
          }
        }

        if (signalTimestamp === undefined) return [];

        const isHighConfidence = signal.tier === 'HIGH_CONFIDENCE' ||
          (signal.probability != null && signal.probability >= 41) ||
          ['HIGH', 'CAO', 'HIGH_CONFIDENCE'].includes(String(signal.riskLevel).toUpperCase());

        const tierLabel = isHighConfidence ? t('chart_distrib_label') : t('chart_watch_label');
        const probStr = signal.probability != null && Number.isFinite(signal.probability)
          ? ` · ${(signal.probability).toFixed(1)}%`
          : '';
        const probabilityText = `${formatSignalTime(signal.time, true)} · ${tierLabel}${probStr}`;

        const isFirst = signal.episodeRole === 'FIRST' || !signal.episodeRole; // Fallback for legacy signals
        const shape = isFirst ? 'arrowDown' : 'circle';
        const color = isHighConfidence
          ? (isFirst ? (signal.isActive ? '#ef4444' : '#f97316') : '#94a3b8')
          : (isFirst ? (signal.isActive ? '#f59e0b' : '#eab308') : '#94a3b8');
        const size = isFirst ? (signal.isActive ? 1.2 : 1) : 0.5;

        return [{
          id: signal.id || `${signalTimestamp}-${index}`,
          time: signalTimestamp as any,
          position: isFirst ? 'aboveBar' : 'inBar',
          shape: shape as any,
          color: color,
          text: isFirst ? probabilityText : '',
          size: size,
        }];
      }).sort((a, b) => a.time - b.time || a.id.localeCompare(b.id));

      if (resolvedMarkers.length > 0) {
        signalMarkersApi = createSeriesMarkers(candleSeries, resolvedMarkers as any, { zOrder: 'top' });
      }
    }
    const currentKey = `${symbol || ''}:${interval || ''}`;
    const isNewContext = lastKeyRef.current !== currentKey;
    if (isNewContext) {
      lastKeyRef.current = currentKey;
      logicalRangeRef.current = null;
      priceRangeRef.current = null;
    }

    if (logicalRangeRef.current && candleData.length > 0 && !isNewContext) {
      const maxIdx = candleData.length - 1;
      const { from } = logicalRangeRef.current;
      // Nếu range đã lưu nằm ngoài giới hạn data mới (ví dụ chuyển sang coin có ít nến hơn)
      if (from > maxIdx + 10) {
        chart.timeScale().scrollToPosition(0, false);
      } else {
        chart.timeScale().setVisibleLogicalRange(logicalRangeRef.current);
      }
    } else {
      chart.timeScale().scrollToPosition(0, false);
    }

    if (priceRangeRef.current && !isNewContext) {
      try {
        chart.priceScale('right').setVisibleRange(priceRangeRef.current);
      } catch (err) {
        console.warn('Failed to restore price range:', err);
      }
    }

    const container = containerRef.current;
    let syncTimeout: any;
    const syncPriceRange = () => {
      const ps = chartRef.current?.priceScale('right');
      if (!ps) return;
      const visible = ps.getVisibleRange();
      if (visible && Number.isFinite(visible.from) && Number.isFinite(visible.to)) {
        priceRangeRef.current = visible;
        try {
          ps.setVisibleRange(visible);
        } catch {}
      }
    };

    const handlePointerUp = () => {
      syncPriceRange();
      clearTimeout(syncTimeout);
      syncTimeout = setTimeout(syncPriceRange, 120);
    };

    const handleWheel = () => {
      clearTimeout(syncTimeout);
      syncTimeout = setTimeout(syncPriceRange, 150);
    };

    if (container) {
      container.addEventListener('pointerup', handlePointerUp);
      container.addEventListener('touchend', handlePointerUp);
      container.addEventListener('wheel', handleWheel, { passive: true });
    }

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (container) {
        container.removeEventListener('pointerup', handlePointerUp);
        container.removeEventListener('touchend', handlePointerUp);
        container.removeEventListener('wheel', handleWheel);
      }
      clearTimeout(syncTimeout);
      if (chartRef.current) {
        logicalRangeRef.current = chartRef.current.timeScale().getVisibleLogicalRange();
        const pr = chartRef.current.priceScale('right')?.getVisibleRange();
        if (pr && Number.isFinite(pr.from) && Number.isFinite(pr.to)) {
          priceRangeRef.current = pr;
        }
        signalMarkersApi?.detach();
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [data, symbol, interval, targetPrice, visibleSignalMarkers, chartHeight, language, showTradeSetup, showEMA, showVolume]);

  return (
    <div
      ref={chartShellRef}
      className={`relative w-full overflow-hidden bg-slate-950 ${isFullscreen ? 'h-screen p-4' : ''}`}
      style={{ ...(isFullscreen ? undefined : { height }), touchAction: 'none', overscrollBehavior: 'none' }}
    >
      <div ref={containerRef} className="w-full" style={{ height: chartHeight, touchAction: 'none', overscrollBehavior: 'none' }} />
      <div className="pointer-events-auto absolute left-2 right-2 top-2 z-20 flex max-w-[calc(100%-1rem)] items-center gap-1 overflow-x-auto rounded-md border border-slate-700/80 bg-slate-950/95 p-1 shadow-xl shadow-black/20 [&::-webkit-scrollbar]:hidden sm:left-auto sm:right-2 sm:max-w-none sm:overflow-visible">
        {interval && onIntervalChange && (
          <>
            {['1m', '5m', '15m', '1h', '4h', '1d'].map(int => {
              const active = interval === int;
              return (
                <button
                  key={int}
                  type="button"
                  onClick={() => onIntervalChange(int)}
                  className={`inline-flex h-7 shrink-0 items-center justify-center whitespace-nowrap rounded px-2.5 text-[10px] font-bold transition ${
                    active
                      ? 'border border-amber-400 bg-amber-400 text-slate-950 shadow-sm shadow-amber-400/30'
                      : 'border border-slate-700/80 bg-slate-900/90 text-slate-400 hover:border-amber-500/60 hover:bg-slate-800 hover:text-slate-200'
                  }`}
                >
                  {int}
                </button>
              );
            })}
            <div className="w-px h-4 bg-slate-700 mx-0.5 shrink-0"></div>
          </>
        )}
        <div ref={alertMenuRef} className="relative">
          <button
            type="button"
            aria-label={t('chart_filter_alerts_aria')}
            className={`${toolButtonClass} ${alertMenuOpen ? 'border-amber-500/80 text-amber-300' : ''}`}
            title={t('chart_filter_title')}
            onClick={() => setAlertMenuOpen(value => !value)}
          >
            <Filter className="h-3.5 w-3.5 text-amber-400" />
            <span>{getAlertVisibilityLabel(alertVisibility)}</span>
            <ChevronDown className={`h-3 w-3 transition-transform ${alertMenuOpen ? 'rotate-180' : ''}`} />
          </button>
          {alertMenuOpen && (
            <div className="absolute right-0 top-full z-50 mt-1 w-52 overflow-hidden rounded-lg border border-slate-700 bg-slate-900 p-1 shadow-2xl shadow-black/50">
              {alertVisibilityOptions.map(option => (
                <button
                  key={option.value}
                  type="button"
                  className={`flex w-full flex-col items-start rounded-md px-2.5 py-2 text-left transition ${
                    alertVisibility === option.value
                      ? 'bg-amber-500/15 text-amber-300'
                      : 'text-slate-300 hover:bg-slate-800 hover:text-slate-100'
                  }`}
                  onClick={() => {
                    setAlertVisibility(option.value);
                    setAlertMenuOpen(false);
                  }}
                >
                  <span className="text-[10px] font-semibold">{option.label}</span>
                  <span className="mt-0.5 text-[9px] text-slate-500">{option.hint}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div ref={settingsMenuRef} className="relative">
          <button
            type="button"
            className={`${toolButtonClass} ${settingsMenuOpen ? 'border-slate-500 text-slate-200' : 'text-slate-500'}`}
            title="Settings"
            onClick={() => setSettingsMenuOpen(value => !value)}
          >
            <Settings className="h-3.5 w-3.5" />
          </button>
          {settingsMenuOpen && (
            <div className="absolute right-0 top-full z-50 mt-1 w-48 overflow-hidden rounded-lg border border-slate-700 bg-slate-900 p-1 shadow-2xl shadow-black/50">
              <div className="flex flex-col gap-0.5">
                <button
                  type="button"
                  className={`flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left text-[10px] transition hover:bg-slate-800 ${showTradeSetup ? 'text-amber-400' : 'text-slate-300'}`}
                  onClick={() => setShowTradeSetup(v => !v)}
                >
                  <span>Trade Setup</span>
                  <span className="font-mono">{showTradeSetup ? 'ON' : 'OFF'}</span>
                </button>
                <button
                  type="button"
                  className={`flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left text-[10px] transition hover:bg-slate-800 ${showEMA ? 'text-amber-400' : 'text-slate-300'}`}
                  onClick={() => setShowEMA(v => !v)}
                >
                  <span>EMAs (20, 50)</span>
                  <span className="font-mono">{showEMA ? 'ON' : 'OFF'}</span>
                </button>
                <button
                  type="button"
                  className={`flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left text-[10px] transition hover:bg-slate-800 ${showVolume ? 'text-amber-400' : 'text-slate-300'}`}
                  onClick={() => setShowVolume(v => !v)}
                >
                  <span>Volume</span>
                  <span className="font-mono">{showVolume ? 'ON' : 'OFF'}</span>
                </button>
                <div className="my-1 border-t border-slate-700/50"></div>
                <button
                  type="button"
                  className={`flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left text-[10px] transition hover:bg-slate-800 ${crosshairMode !== 'hidden' ? 'text-amber-400' : 'text-slate-300'}`}
                  onClick={() => setCrosshairMode(mode => mode === 'magnet' ? 'normal' : mode === 'normal' ? 'hidden' : 'magnet')}
                >
                  <span>{t('chart_crosshair_title')}</span>
                  <span className="font-mono capitalize">{crosshairMode}</span>
                </button>
                <button
                  type="button"
                  className={`flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left text-[10px] transition hover:bg-slate-800 ${gridVisible ? 'text-amber-400' : 'text-slate-300'}`}
                  onClick={() => setGridVisible(v => !v)}
                >
                  <span>{t('chart_toggle_grid')}</span>
                  <span className="font-mono">{gridVisible ? 'ON' : 'OFF'}</span>
                </button>
                <button
                  type="button"
                  className={`flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left text-[10px] transition hover:bg-slate-800 ${priceAutoScale ? 'text-amber-400' : 'text-slate-300'}`}
                  onClick={() => applyPriceScaleMode(!priceAutoScale)}
                >
                  <span>{t('chart_auto_scale_btn')}</span>
                  <span className="font-mono">{priceAutoScale ? 'ON' : 'OFF'}</span>
                </button>
              </div>
            </div>
          )}
        </div>
        <button type="button" className={toolButtonClass} title={t('chart_zoom_out')} onClick={() => adjustZoom(1.35)}>
          <ZoomOut className="h-3.5 w-3.5" />
        </button>
        <button type="button" className={toolButtonClass} title={t('chart_zoom_in')} onClick={() => adjustZoom(0.7)}>
          <ZoomIn className="h-3.5 w-3.5" />
        </button>
        <button type="button" className={toolButtonClass} title={t('chart_reset')} onClick={handleResetView}>
          <RotateCcw className="h-3.5 w-3.5" />
        </button>
        <button type="button" className={toolButtonClass} title={t('chart_screenshot')} onClick={handleScreenshot}>
          <Camera className="h-3.5 w-3.5" />
        </button>
        <button type="button" className={toolButtonClass} title={t('chart_fullscreen')} onClick={handleFullscreen}>
          {isFullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
        </button>
      </div>
      {visibleSignalMarkers.length > 0 && (() => {
        const latestMarker = visibleSignalMarkers[visibleSignalMarkers.length - 1];
        const isLatestHigh = latestMarker.tier === 'HIGH_CONFIDENCE' ||
          (latestMarker.probability != null && latestMarker.probability >= 41) ||
          ['HIGH', 'CAO', 'HIGH_CONFIDENCE'].includes(String(latestMarker.riskLevel).toUpperCase());
        return (
          <div className={`pointer-events-none absolute left-2 top-12 z-10 flex items-center gap-1.5 overflow-hidden rounded-md border ${
            isLatestHigh ? 'border-red-500/50 bg-slate-950/90 shadow-red-500/10' : 'border-amber-500/40 bg-slate-950/90 shadow-black/20'
          } px-2 py-1 text-[10px] shadow-lg sm:top-2 sm:max-w-[70%] sm:gap-2`}>
            <span className={`font-bold uppercase tracking-wide shrink-0 ${isLatestHigh ? 'text-red-400' : 'text-amber-400'}`}>
              {isLatestHigh ? t('chart_distrib_alert') : t('chart_watch_alert')}
            </span>
            {latestMarker.probability != null && Number.isFinite(latestMarker.probability) && (
              <span className={`font-mono font-bold shrink-0 ${isLatestHigh ? 'text-red-400' : 'text-amber-300'}`}>
                {latestMarker.probability?.toFixed(1)}%
              </span>
            )}
            <span className="hidden sm:inline font-mono text-slate-300 truncate">
              {t('chart_latest_time')} {formatSignalTime(latestMarker.time)}
            </span>
            {visibleSignalMarkers.length > 1 && (
              <span className="hidden sm:inline font-mono font-bold text-slate-300">
                {visibleSignalMarkers.length} {t('feed_signals_count')}
              </span>
            )}
            {allSignalMarkers.length > visibleSignalMarkers.length && (
              <span className="hidden sm:inline font-mono text-slate-500">/{allSignalMarkers.length} · {getAlertVisibilityLabel(alertVisibility)}</span>
            )}
          </div>
        );
      })()}
    </div>
  );
};
