import React, { useState, useEffect } from 'react';
import type { SystemHistoryData } from '../types';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine,
} from 'recharts';
import {
  Database, Radar, Cpu, Activity, CheckCircle2, XCircle,
  RefreshCw, TrendingUp, Layers, Lock, Trophy, Info, Gauge, AlertTriangle,
} from 'lucide-react';
import { formatSystemDateTime, parseSystemDate } from '../utils/time';
import { useTranslation, type Language } from '../i18n/LanguageContext';
import { getModelLabel, getModelDescription, getScanModeLabel, formatAgeMinutes } from '../i18n/translations';

/* ---------- Tooltip helper ---------- */
const InfoTip: React.FC<{ text: string; className?: string }> = ({ text, className = '' }) => {
  const [show, setShow] = useState(false);
  return (
    <span
      className={`relative inline-flex ${className}`}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onClick={(e) => { e.stopPropagation(); setShow(s => !s); }}
    >
      <Info className="w-3 h-3 text-slate-500 hover:text-amber-400 cursor-help" />
      {show && (
        <span className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-1 w-56 bg-slate-950 border border-amber-500/30 rounded-md p-2 text-[10px] text-slate-200 leading-relaxed shadow-xl shadow-black/50 pointer-events-none">
          {text}
          <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-amber-500/30" />
        </span>
      )}
    </span>
  );
};

/* ---------- Stat card with tooltip + bold highlight ---------- */
interface StatCardProps {
  label: string;
  value: React.ReactNode;
  tooltip?: string;
  highlight?: boolean;
  valueClass?: string;
}
const StatCard: React.FC<StatCardProps> = ({ label, value, tooltip, highlight, valueClass = '' }) => (
  <div className={`bg-slate-900 p-2 rounded ${highlight ? 'ring-1 ring-amber-500/40' : ''}`}>
    <div className="text-[9px] text-slate-400 uppercase flex items-center gap-1">
      {label}
      {tooltip && <InfoTip text={tooltip} />}
    </div>
    <div className={`text-sm font-bold font-mono ${valueClass}`}>{value}</div>
  </div>
);

export const SystemHistoryTab: React.FC = () => {
  const { language, t } = useTranslation();

  const [data, setData] = useState<SystemHistoryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/system-history');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('network_err'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
          <RefreshCw className="w-4 h-4 animate-spin" />
          {t('tab_loading')}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 gap-3">
        <XCircle className="w-8 h-8 text-red-400" />
        <p className="text-xs text-red-400">{error}</p>
        <button onClick={fetchData} className="px-3 py-1.5 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded text-xs">
          {t('refresh')}
        </button>
      </div>
    );
  }

  if (!data) return null;

  const fmtNum = (n: number | null | undefined) => {
    if (n == null) return '—';
    const locale = language === 'zh' ? 'zh-CN' : language === 'ko' ? 'ko-KR' : language === 'en' ? 'en-US' : 'vi-VN';
    return n.toLocaleString(locale);
  };
  const fmtTime = formatSystemDateTime;
  const fmtPct = (n: number | null | undefined) => {
    if (n == null) return '—';
    return `${(n * 100).toFixed(1)}%`;
  };

  const hb = data.scanner?.heartbeat || {};
  const isOnline = hb.status === 'running';
  const lastCycle = data.scanner?.last_cycle || {};

  const signalsChart = (data.signals_per_day || []).slice().reverse().map(d => ({
    day: (d.day || '').slice(5) || d.day || '',
    signals: d.n_signals ?? 0,
    telegram: d.n_telegram ?? 0,
    hits: d.n_hit ?? 0,
  }));

  const scanChart = (data.scanner?.scan_per_day || []).slice().reverse().map(d => ({
    day: (d.day || '').slice(5) || d.day || '',
    cycles: d.n_cycles ?? 0,
    symbols: d.n_symbols ?? 0,
  }));

  const totalRows = (data.data_stats || []).reduce((s, d) => s + (d.rows || 0), 0);
  const latestDataTime = (data.data_stats || [])
    .map(d => d.max_time)
    .filter(Boolean)
    .sort()
    .pop();  const getTableTooltip = (table: string, lang: Language): string => {
    const map: Record<string, Record<string, string>> = {
      raw_timeline: {
        vi: 'Dòng thời gian nến 5m và phái sinh hợp nhất — dữ liệu thị trường gốc (OHLCV + OI + Funding).',
        en: 'Raw 5m timeline and unified derivatives (OHLCV + OI + Funding).',
        zh: '已对齐时间戳的 5 分钟 K 线与合约衍生品原始时序。',
        ko: '통합 5분봉 및 파생상품 시계열 데이터 (OHLCV + OI + Funding).',
      },
      raw_timeline_pre_quality: {
        vi: 'Dữ liệu trước khi lọc kiểm định chất lượng — ghi nhận tức thời từ Binance.',
        en: 'Pre-quality check timeline recorded in real time from Binance.',
        zh: '质量检验前的实时币安快照。',
        ko: '품질 검증 전 바이낸스 실시간 수집 데이터.',
      },
      kline: {
        vi: 'Nến 5 phút từ Binance — dữ liệu thị trường gốc (OHLCV). Mỗi dòng = 1 nến của 1 mã.',
        en: '5-minute candles from Binance (OHLCV raw market data).',
        zh: '来自币安的 5 分钟 K 线（OHLCV 原始市场数据）。',
        ko: '바이낸스 5분봉 캔들 (OHLCV 원시 시장 데이터).',
      },
      aligned_5m: {
        vi: 'Nến 5m được căn theo thời điểm dữ liệu có sẵn để hỗ trợ tính toán point-in-time và kiểm tra rò rỉ.',
        en: '5m candles aligned to data-availability timestamps for point-in-time calculations and leakage checks.',
        zh: '按数据可用时间对齐 5 分钟 K 线，用于时点计算与泄漏检查。',
        ko: '데이터 가용 시점에 맞춘 5분봉으로 point-in-time 계산과 누수 검사를 지원합니다.',
      },
      feature_results: {
        vi: 'Vector đặc trưng đã tính cho mỗi mã tại từng thời điểm — đầu vào cho mô hình AI.',
        en: 'Calculated ML feature vectors across time horizons.',
        zh: '已计算的多周期特征向量，作为 AI 模型输入。',
        ko: 'AI 모델 입력을 위한 다주기 계산 특성 벡터.',
      },
      labels: {
        vi: 'Nhãn phân phối: 1 nếu coin giảm >= mục tiêu trong khung thời gian, 0 nếu không. Dữ liệu thực tế để huấn luyện.',
        en: 'Distribution ground truth labels (1 = dump ≥ 8%, 0 = otherwise).',
        zh: '见顶派发真实标签（1 = 跌幅 ≥ 8%，0 = 否），用于模型训练。',
        ko: '분산 국면 정답 라벨 (1 = 하락 ≥ 8%, 0 = 기타).',
      },
      scan_results: {
        vi: 'Kết quả mỗi chu kỳ quét: điểm, khuyến nghị, giá, OI, funding... của mọi coin đã quét.',
        en: 'Per-cycle scan scores, indicators, and recommendations.',
        zh: '每轮扫描输出：得分、建议、价格、持仓量、费率等。',
        ko: '매 스캔 주기별 점수, 지표, 추천 결과.',
      },
      alert_history: {
        vi: 'Tín hiệu vượt ngưỡng cảnh báo đã ghi lại — kèm kết quả đúng/sai sau khi hết khung thời gian.',
        en: 'Radar alerts logged above threshold with verification outcomes.',
        zh: '超过阈值的雷达警报记录及后续验证结果。',
        ko: '임계값을 초과한 레이더 경보 이력 및 실현 결과.',
      },
      candidate_market_observations: {
        vi: 'Dữ liệu phái sinh quan sát theo thời gian thực (OI, Funding, Taker Ratio).',
        en: 'Real-time candidate market observations (OI, Funding, Taker Ratio).',
        zh: '实时衍生品观测数据（持仓量、费率、主动吃单比）。',
        ko: '실시간 파생상품 관측 데이터 (OI, Funding, Taker Ratio).',
      },
      candidate_filter_decisions: {
        vi: 'Quyết định và điểm số bộ lọc ứng viên xả mỗi chu kỳ.',
        en: 'Candidate filter decisions and scores per cycle.',
        zh: '每轮候选做空筛选决策与打分。',
        ko: '주기별 덤프 후보 필터 의사결정 및 점수.',
      },
      predictions: {
        vi: 'Dự báo xác suất phân phối từ mô hình Machine Learning.',
        en: 'Distribution probability predictions from ML model.',
        zh: '机器学习模型输出的见顶派发概率预测。',
        ko: 'ML 모델의 분산 확률 예측 결과.',
      },
      funding: {
        vi: 'Tỷ lệ funding theo thời gian — tín hiệu áp lực mua/bán trên hợp đồng tương lai.',
        en: 'Funding rate time series from Binance USD-M futures.',
        zh: '币安合约资金费率时序数据。',
        ko: '바이낸스 선물 펀딩비 시계열 데이터.',
      },
      open_interest: {
        vi: 'Dữ liệu Open Interest — số lượng vị thế đang mở.',
        en: 'Open interest snapshot time series.',
        zh: '未平仓合约量时序数据。',
        ko: '미결제약정 스냅샷 시계열 데이터.',
      },
      taker_volume: {
        vi: 'Khối lượng mua/bán chủ động — chênh lệch giữa bên mua và bên bán trên thị trường.',
        en: 'Taker buy / sell active volume metrics.',
        zh: '主动买入/卖出吃单成交量指标。',
        ko: '테이커 매수/매도 거래량 델타 지표.',
      },
    };
    return map[table]?.[lang] ?? map[table]?.['en'] ?? '';
  };

  const getPipelineSpec = () => [
    {
      table: 'raw_timeline',
      fallbackTable: 'kline',
      label: t('pipe_candle_collector'),
      expectedMin: 15,
      desc: t('pipe_candle_desc'),
    },
    {
      table: 'raw_timeline_pre_quality',
      fallbackTable: 'aligned_5m',
      label: t('pipe_aligner'),
      expectedMin: 15,
      desc: t('pipe_aligner_desc'),
    },
    {
      table: 'feature_results',
      label: t('pipe_feature'),
      expectedMin: 15,
      desc: t('pipe_feature_desc'),
    },
    {
      table: 'labels',
      label: t('pipe_label'),
      expectedMin: 20160,
      desc: t('pipe_label_desc'),
    },
    {
      table: 'scan_results',
      label: t('pipe_scanner'),
      expectedMin: 15,
      desc: t('pipe_scanner_desc'),
    },
    {
      table: data?.candidate_comparison_enabled === false ? 'open_interest' : 'candidate_market_observations',
      fallbackTable: data?.candidate_comparison_enabled === false ? undefined : 'funding',
      label: data?.candidate_comparison_enabled === false ? 'Open Interest' : t('pipe_funding') + ' & OI',
      expectedMin: 15,
      desc: t('pipe_funding_desc'),
    },
    {
      table: 'funding',
      label: t('pipe_funding'),
      // Settled funding is emitted at funding intervals, not every scan.
      expectedMin: 480,
      desc: t('pipe_funding_desc'),
    },
    {
      table: data?.candidate_comparison_enabled === false ? 'scan_results' : 'candidate_filter_decisions',
      fallbackTable: data?.candidate_comparison_enabled === false ? undefined : 'open_interest',
      label: language === 'zh' ? '候选决策' : language === 'ko' ? '후보 결정' : language === 'en' ? 'Candidate Filter' : 'Bộ Lọc Ứng Viên',
      expectedMin: 15,
      desc: language === 'zh' ? '实时做空候选筛选打分' : language === 'ko' ? '실시간 덤프 후보 필터링 및 점수화' : language === 'en' ? 'Real-time candidate dump scoring' : 'Bộ lọc và chấm điểm ứng viên xả thời gian thực',
    },
    {
      table: 'predictions',
      fallbackTable: 'taker_volume',
      label: language === 'zh' ? 'AI 预测' : language === 'ko' ? 'AI 예측' : language === 'en' ? 'AI Predictions' : 'Dự Báo AI',
      expectedMin: 15,
      desc: language === 'zh' ? '机器学习模型见顶概率预测' : language === 'ko' ? 'ML 모델 분산 확률 예측' : language === 'en' ? 'Distribution probabilities from ML model' : 'Xác suất dự báo phân phối từ mô hình AI',
    },
    {
      table: 'alert_history',
      label: t('pipe_radar_alerts'),
      expectedMin: 0,
      onDemand: true,
      desc: t('pipe_radar_alerts_desc'),
    },
  ];

  const parseTimestamp = (value: string | null | undefined): number | null => {
    return parseSystemDate(value)?.getTime() ?? null;
  };

  const computeAgeMin = (maxTime: string | null | undefined, refIso: string): number | null => {
    const dataTimestamp = parseTimestamp(maxTime);
    const referenceTimestamp = parseTimestamp(refIso);
    if (dataTimestamp == null || referenceTimestamp == null) return null;
    const diffMs = referenceTimestamp - dataTimestamp;
    return Math.max(0, Math.round(diffMs / 60000));
  };

  const fmtAge = (min: number | null) => {
    if (min == null) return '—';
    return formatAgeMinutes(min, language);
  };

  const getStatus = (ageMin: number | null, expectedMin: number, onDemand?: boolean) => {
    if (onDemand) return 'ondemand';
    if (ageMin == null) return 'gray';
    if (ageMin <= expectedMin) return 'green';
    if (ageMin <= expectedMin * 2) return 'yellow';
    return 'red';
  };

  const getStatusStyles = (lang: Language): Record<string, { dot: string; text: string; label: string; ring: string }> => {
    const labels: Record<string, Record<string, string>> = {
      green: { vi: 'MỚI', en: 'FRESH', zh: '最新', ko: '최신' },
      yellow: { vi: 'ĐANG CŨ', en: 'AGING', zh: '轻微延迟', ko: '지연' },
      red: { vi: 'QUÁ CŨ', en: 'STALE', zh: '数据过旧', ko: '오래됨' },
      gray: { vi: 'CHƯA CÓ DỮ LIỆU', en: 'NO DATA', zh: '暂无数据', ko: '데이터 없음' },
      ondemand: { vi: 'THEO SỰ KIỆN', en: 'ON DEMAND', zh: '按需触发', ko: '이벤트 기반' },
    };
    return {
      green: { dot: 'bg-emerald-400', text: 'text-emerald-400', label: labels.green[lang] || labels.green.en, ring: 'border-emerald-500/30' },
      yellow: { dot: 'bg-amber-400', text: 'text-amber-400', label: labels.yellow[lang] || labels.yellow.en, ring: 'border-amber-500/30' },
      red: { dot: 'bg-red-400', text: 'text-red-400', label: labels.red[lang] || labels.red.en, ring: 'border-red-500/40' },
      gray: { dot: 'bg-slate-500', text: 'text-slate-500', label: labels.gray[lang] || labels.gray.en, ring: 'border-slate-800' },
      ondemand: { dot: 'bg-sky-400', text: 'text-sky-400', label: labels.ondemand[lang] || labels.ondemand.en, ring: 'border-sky-500/30' },
    };
  };

  const statusStyles = getStatusStyles(language);
  const pipelineSpec = getPipelineSpec();
  const dataStatsMap = new Map((data?.data_stats || []).map(d => [d.table, d]));
  const freshnessRows = pipelineSpec.map(spec => {
    const tableData =
      data?.freshness?.[spec.table] ||
      dataStatsMap.get(spec.table) ||
      (spec.fallbackTable ? data?.freshness?.[spec.fallbackTable] || dataStatsMap.get(spec.fallbackTable) : undefined);
    const maxTime = tableData?.max_time;
    const rowCount = 'row_count' in (tableData || {}) ? (tableData as any).row_count : (tableData as any)?.rows;
    // Measure against the current report, never against an old snapshot's
    // own clock, which freezes displayed ages during scanner outages.
    const ageMin = computeAgeMin(maxTime, data?.generated_at || '');
    const status = getStatus(ageMin, spec.expectedMin, spec.onDemand);
    return {
      ...spec,
      max_time: maxTime,
      row_count: rowCount,
      ageMin,
      status,
    };
  });
  const nStale = freshnessRows.filter(r => r.status === 'red').length;
  const nAging = freshnessRows.filter(r => r.status === 'yellow').length;

  if (!data) return null;

  return (
    <div className="flex-1 overflow-y-auto space-y-4 pr-1">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
          <Activity className="w-3.5 h-3.5 text-amber-400" />
          {t('history_header_title')}
        </h3>
        <button onClick={fetchData} className="px-2 py-0.5 text-[10px] text-amber-400 border border-amber-500/30 rounded hover:bg-amber-500/10 flex items-center gap-1">
          <RefreshCw className="w-3 h-3" /> {t('refresh')}
        </button>
      </div>
      <p className="text-[11px] text-slate-400 -mt-2">
        {t('history_report_gen')} (Hà Nội, UTC+7): <span className="text-slate-200 font-mono font-bold">{fmtTime(data.generated_at)}</span>
      </p>

      {/* ===== SECTION 0: FRESHNESS HEALTH CHECK ===== */}
      <section className={`bg-slate-950 border rounded-xl p-3 ${nStale > 0 ? 'border-red-500/40' : nAging > 0 ? 'border-amber-500/30' : 'border-emerald-500/30'}`}>
        {!isOnline && (
          <div className="mb-3 p-2.5 rounded-lg bg-amber-950/40 border border-amber-800/60 text-amber-300 text-[11px] flex items-start gap-2">
            <Info className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div className="leading-relaxed">
              <strong>Máy quét Local Scanner Daemon hiện đang TẮT.</strong> Dữ liệu đường ống hiển thị mốc thời gian của lần quét trước đó nên hệ thống cảnh báo màu đỏ (&ldquo;Quá cũ / Stale&rdquo;). Để nạp nến 5m mới nhất và làm xanh toàn bộ 9 dịch vụ, hãy chạy file <code className="bg-slate-900 px-1.5 py-0.5 rounded text-amber-200 border border-amber-700/50 font-mono">run_scanner_dev.bat</code> (hoặc chạy <code className="bg-slate-900 px-1.5 py-0.5 rounded text-amber-200 border border-amber-700/50 font-mono">run_all_dev.bat</code> để bật cùng lúc cả Web + Scanner).
            </div>
          </div>
        )}

        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Gauge className="w-3.5 h-3.5 text-amber-400" />
          {t('history_freshness_title')}
          <InfoTip text={t('history_freshness_desc')} />
          {nStale > 0 ? (
            <span className="ml-auto text-[10px] text-red-400 font-bold flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> {nStale} {t('history_stale_count')}
            </span>
          ) : nAging > 0 ? (
            <span className="ml-auto text-[10px] text-amber-400 font-bold flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> {nAging} {t('history_aging_count')}
            </span>
          ) : (
            <span className="ml-auto text-[10px] text-emerald-400 font-bold flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" /> {t('history_all_fresh')}
            </span>
          )}
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
          {freshnessRows.map(r => {
            const st = statusStyles[r.status] || statusStyles.gray;
            return (
              <div key={`${r.table}:${r.label}`} className={`bg-slate-900 border ${st.ring} rounded-lg p-2`}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className={`w-2 h-2 rounded-full ${st.dot} shrink-0 ${r.status === 'red' ? 'animate-pulse' : ''}`} />
                    <span className="text-[11px] font-bold text-white truncate">{r.label}</span>
                    <InfoTip text={r.desc} />
                  </div>
                  <span className={`text-[9px] font-bold font-mono ${st.text} shrink-0`}>{st.label}</span>
                </div>
                <div className="grid grid-cols-3 gap-1 text-[10px]">
                  <div>
                    <div className="text-slate-500 uppercase text-[8px]">{t('history_col_latest')}</div>
                    <div className={`font-mono font-bold ${r.status === 'red' ? 'text-red-400' : 'text-slate-200'}`}>
                      {r.max_time ? fmtTime(r.max_time) : '—'}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500 uppercase text-[8px]">{t('history_col_age')}</div>
                    <div className={`font-mono font-bold ${st.text}`}>{fmtAge(r.ageMin)}</div>
                  </div>
                  <div>
                    <div className="text-slate-500 uppercase text-[8px]">{t('backtest_modal_total_rows')}</div>
                    <div className="text-slate-300 font-mono">{fmtNum(r.row_count)}</div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* ===== SECTION 1: DATA Stats ===== */}
      <section className="bg-slate-950 border border-slate-800 rounded-xl p-3">
        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Database className="w-3.5 h-3.5 text-sky-400" />
          {t('history_duckdb_title')}
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
          <StatCard
            label={t('history_total_rows')}
            value={fmtNum(totalRows)}
            valueClass="text-sky-400"
            highlight
          />
          <StatCard
            label={t('history_tables_count')}
            value={(data.data_stats || []).length}
            valueClass="text-slate-200"
          />
          <StatCard
            label={t('history_latest_data')}
            value={<span className="text-xs">{fmtTime(latestDataTime)}</span>}
            valueClass="text-emerald-400"
            highlight
          />
          <StatCard
            label={t('history_db_path')}
            value={<span className="text-[10px]">{data.db_path || '—'}</span>}
            valueClass="text-slate-300 truncate"
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[10px] text-slate-300 font-mono">
            <thead className="text-slate-400 uppercase border-b border-slate-800">
              <tr>
                <th className="p-1.5">{t('history_col_table')}</th>
                <th className="p-1.5">{t('backtest_modal_total_rows')}</th>
                <th className="p-1.5">{t('history_col_time_col')}</th>
                <th className="p-1.5">{t('history_col_earliest')}</th>
                <th className="p-1.5">{t('history_col_latest')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {(data.data_stats || []).map(d => {
                const isImportant = ['feature_results', 'labels', 'kline', 'aligned_5m', 'scan_results', 'alert_history'].includes(d.table);
                return (
                  <tr key={d.table} className="hover:bg-slate-900/60">
                    <td className="p-1.5 text-white">
                      <span className="flex items-center gap-1">
                        {isImportant && <span className="text-amber-400">●</span>}
                        <span className={isImportant ? 'font-bold' : ''}>{d.table}</span>
                        {getTableTooltip(d.table, language) && <InfoTip text={getTableTooltip(d.table, language)} />}
                      </span>
                    </td>
                    <td className={`p-1.5 ${isImportant ? 'text-amber-400 font-bold' : 'text-amber-400/70'}`}>{fmtNum(d.rows)}</td>
                    <td className="p-1.5 text-slate-500">{d.ts_column || '—'}</td>
                    <td className="p-1.5 text-slate-400">{d.min_time ? fmtTime(d.min_time) : '—'}</td>
                    <td className="p-1.5 text-emerald-400 font-bold">{d.max_time ? fmtTime(d.max_time) : '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* ===== SECTION 2: Scanner Activity ===== */}
      <section className="bg-slate-950 border border-slate-800 rounded-xl p-3">
        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Radar className="w-3.5 h-3.5 text-emerald-400" />
          {t('history_scanner_daemon')}
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
          <StatCard
            label={t('col_status')}
            value={
              <span className="flex items-center gap-1">
                {isOnline ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                {isOnline ? t('scanner_running') : t('scanner_stopped')}
              </span>
            }
            valueClass={isOnline ? 'text-emerald-400' : 'text-red-400'}
            highlight
          />
          <StatCard
            label={t('history_latest_cycle')}
            value={`#${lastCycle.cycle ?? '—'}`}
            valueClass="text-amber-400"
          />
          <StatCard
            label={t('history_last_scan_time')}
            value={<span className="text-xs">{fmtTime(lastCycle.last_scan_time)}</span>}
            valueClass="text-slate-200"
            highlight
          />
          <StatCard
            label={t('history_symbols_per_cycle')}
            value={fmtNum(lastCycle.n_symbols)}
            valueClass="text-sky-400"
          />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-3 text-[10px]">
          <div className="bg-slate-900 p-1.5 rounded flex items-center gap-1">
            <span className="text-slate-500">{t('history_heartbeat')}:</span>{' '}
            <span className="text-slate-300 font-mono font-bold">{fmtTime(hb.timestamp)}</span>
          </div>
          <div className="bg-slate-900 p-1.5 rounded flex items-center gap-1">
            <span className="text-slate-500">{t('history_scan_mode')}:</span>{' '}
            <span className="text-amber-400 font-mono uppercase font-bold">{getScanModeLabel(data.scanner?.scan_mode || 'volatile', language)}</span>
          </div>
          <div className="bg-slate-900 p-1.5 rounded flex items-center gap-1">
            <span className="text-slate-500">{t('history_poll_interval')}:</span>{' '}
            <span className="text-slate-300 font-mono font-bold">{hb.poll_minutes || '?'} {t('unit_minutes')}</span>
          </div>
        </div>

        {scanChart.length > 0 && (
          <div className="mt-3">
            <h5 className="text-[11px] font-bold text-slate-300 mb-1.5 flex items-center gap-1">
              <TrendingUp className="w-3 h-3 text-sky-400" />
              {t('history_daily_scan_chart')}
            </h5>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={scanChart} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="day" tick={{ fill: '#64748b', fontSize: 9 }} />
                <YAxis tick={{ fill: '#64748b', fontSize: 9 }} />
                <Tooltip
                  contentStyle={{ background: '#0f172a', border: '1px solid #334155', fontSize: 11 }}
                  labelStyle={{ color: '#fbbf24' }}
                />
                <Bar dataKey="cycles" fill="#0ea5e9" name={t('history_chart_cycles')} radius={[3, 3, 0, 0]} />
                <Bar dataKey="symbols" fill="#10b981" name={t('history_chart_symbols')} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      {/* ===== SECTION 3: AI Models Progress ===== */}
      <section className="bg-slate-950 border border-slate-800 rounded-xl p-3">
        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Cpu className="w-3.5 h-3.5 text-amber-400" />
          {t('history_ai_models_title')}
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
          <StatCard
            label={t('history_frozen_models')}
            value={(data.models || []).length}
            valueClass="text-amber-400"
          />
          <StatCard
            label={t('history_total_experiments')}
            value={data.experiments?.total ?? 0}
            valueClass="text-sky-400"
            highlight
          />
          <StatCard
            label={t('history_active_scanner_model')}
            value={<span className="text-[10px]">{data.current_scanner_model_id ? getModelLabel(data.current_scanner_model_id, language) : t('status_rules_based')}</span>}
            valueClass="text-emerald-400 truncate"
            highlight
          />
          <StatCard
            label={t('history_latest_artifact')}
            value={<span className="text-[10px]">{data.experiments?.latest?.artifact_id?.slice(-12) || '—'}</span>}
            valueClass="text-slate-300"
          />
        </div>

        {/* Models list */}
        {(data.models || []).length > 0 && (
          <div className="space-y-2">
            {(data.models || []).map(m => (
              <div key={m.model_id} className={`bg-slate-900 border rounded-lg p-2.5 ${m.is_scanner_model ? 'border-emerald-500/40 ring-1 ring-emerald-500/20' : 'border-slate-800'}`}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <Lock className="w-3 h-3 text-amber-400 shrink-0" />
                    <span className="text-xs font-bold text-white truncate">{getModelLabel(m.friendly_name || m.model_id, language)}</span>
                    {m.is_scanner_model && (
                      <span className="text-[9px] text-emerald-400 font-mono bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-500/30 flex items-center gap-0.5 shrink-0 font-bold">
                        <Trophy className="w-2.5 h-2.5" /> {t('history_active_badge')}
                      </span>
                    )}
                  </div>
                  <span className="text-[9px] text-slate-500 font-mono shrink-0">{m.label_version}</span>
                </div>
                <p className="text-[10px] text-slate-400 mb-1.5 leading-relaxed">{m.description || getModelDescription(m.friendly_name || m.model_id, language)}</p>
                <div className="grid grid-cols-3 md:grid-cols-6 gap-1.5 text-[10px]">
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{t('forward_train_size')}</div>
                    <div className="text-slate-200 font-mono font-bold">{fmtNum(m.train_size)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{t('forward_train_positives')}</div>
                    <div className="text-emerald-400 font-mono font-bold">{fmtNum(m.train_positives)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{t('forward_precision')}</div>
                    <div className="text-amber-400 font-mono font-bold">{fmtPct(m.train_precision)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{t('forward_recall')}</div>
                    <div className="text-sky-400 font-mono font-bold">{fmtPct(m.train_recall)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{t('forward_features')}</div>
                    <div className="text-slate-200 font-mono">{m.n_features}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{t('threshold')}</div>
                    <div className="text-amber-400 font-mono font-bold">{m.threshold != null ? m.threshold.toFixed(2) : "—"}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ===== SECTION 4: Radar Signals per Day ===== */}
      <section className="bg-slate-950 border border-slate-800 rounded-xl p-3">
        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Layers className="w-3.5 h-3.5 text-red-400" />
          {t('history_radar_signals_title')}
        </h4>
        {signalsChart.length > 0 ? (
          <>
            <div className="grid grid-cols-3 gap-2 mb-3">
              <StatCard
                label={t('history_total_signals')}
                value={(data.signals_per_day || []).reduce((s, d) => s + (d.n_signals || 0), 0)}
                valueClass="text-amber-400"
              />
              <StatCard
                label={t('history_tg_sent')}
                value={(data.signals_per_day || []).reduce((s, d) => s + (d.n_telegram || 0), 0)}
                valueClass="text-sky-400"
              />
              <StatCard
                label={t('history_actual_hits')}
                value={(data.signals_per_day || []).reduce((s, d) => s + (d.n_hit || 0), 0)}
                valueClass="text-emerald-400"
                highlight
              />
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={signalsChart} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="day" tick={{ fill: '#64748b', fontSize: 9 }} />
                <YAxis tick={{ fill: '#64748b', fontSize: 9 }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ background: '#0f172a', border: '1px solid #334155', fontSize: 11 }}
                  labelStyle={{ color: '#fbbf24' }}
                />
                <ReferenceLine y={0} stroke="#334155" />
                <Bar dataKey="signals" fill="#f59e0b" name={t('feed_tab_all')} radius={[3, 3, 0, 0]} />
                <Bar dataKey="telegram" fill="#0ea5e9" name="Telegram" radius={[3, 3, 0, 0]} />
                <Bar dataKey="hits" fill="#10b981" name={t('history_actual_hits')} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </>
        ) : (
          <p className="text-[11px] text-slate-500 italic">
            {t('history_no_signals')}
          </p>
        )}
      </section>
    </div>
  );
};
