import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Bot,
  Check,
  Copy,
  HelpCircle,
  Loader2,
  Lock,
  MessageCircle,
  Send,
  Settings,
  Sparkles,
  Trash2,
  User,
  X,
} from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';
import type {
  AiAskRequest,
  AiAskResponse,
  ChatMessage,
  CoinDetail,
  DeepAnalysis,
  LlmConfig,
  SignalItem,
  SystemStatus,
} from '../../types';
import { normalizeProbability } from '../../types';
import { LlmConfigModal } from './LlmConfigModal';
import { MarkdownRenderer } from './MarkdownRenderer';
import {
  LLM_CONFIG_CHANGED_EVENT,
  hasStoredLlmConfig,
  readStoredLlmConfig,
  saveStoredLlmConfig,
} from '../../utils/llm';

interface FloatingAiAssistantProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  activeTab: string;
  guiVersion: 'v1' | 'v2';
  coinDetail: CoinDetail | null;
  selectedSignal: SignalItem | null;
  deepAnalysis: DeepAnalysis | null;
  candidatesCount: number;
  signalCount: number;
  trackingCount: number;
  activeScanModes: string[];
  selectedModelKey: string;
  scannerModelId: string;
  status: SystemStatus | null;
  hasMobileActionBar?: boolean;
  isAdmin?: boolean;
  onRequireAdmin?: (reason?: string) => void;
}

const DEFAULT_SYMBOL = 'BTCUSDT';

function formatPrice(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—';
  if (value < 0.001) return value.toFixed(6);
  if (value < 1) return value.toFixed(5);
  if (value < 10) return value.toFixed(4);
  return value.toFixed(2);
}

function timestamp(): string {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export const FloatingAiAssistant = ({
  open,
  onOpenChange,
  activeTab,
  guiVersion,
  coinDetail,
  selectedSignal,
  deepAnalysis,
  candidatesCount,
  signalCount,
  trackingCount,
  activeScanModes,
  selectedModelKey,
  scannerModelId,
  status,
  hasMobileActionBar = false,
  isAdmin = false,
  onRequireAdmin,
}: FloatingAiAssistantProps) => {
  const { language } = useTranslation();
  const isEn = language === 'en';
  const isZh = language === 'zh';
  const isKo = language === 'ko';

  const symbol = coinDetail?.symbol || selectedSignal?.symbol || DEFAULT_SYMBOL;
  const currentPrice = coinDetail?.current_price ?? selectedSignal?.signal_price ?? null;
  const probability = coinDetail?.probability != null
    ? normalizeProbability(coinDetail.probability)
    : normalizeProbability(selectedSignal?.probability);
  const riskLevel = coinDetail?.risk_level || selectedSignal?.risk_level || 'N/A';
  const metrics = useMemo<Record<string, unknown>>(() => coinDetail?.metrics || ({
    oi_change_24h: selectedSignal?.oi_change_24h || 'N/A',
    taker_sell_ratio: selectedSignal?.taker_sell_ratio ?? null,
    funding_rate: selectedSignal?.funding_rate || 'N/A',
    rsi_15m: null,
    volume_delta_24h: 'N/A',
  }), [
    coinDetail?.metrics,
    selectedSignal?.funding_rate,
    selectedSignal?.oi_change_24h,
    selectedSignal?.taker_sell_ratio,
  ]);

  const tradeSetup = useMemo(() => {
    const setup = selectedSignal?.trade_setup;
    if (!setup || Object.keys(setup).length === 0) return undefined;
    return {
      entry_price: setup.entry_price,
      entry_zone: setup.entry_zone,
      stop_loss: setup.stop_loss,
      stop_loss_pct: setup.stop_loss_pct,
      tp1: setup.tp1,
      tp1_pct: setup.tp1_pct,
      tp2: setup.tp2,
      tp2_pct: setup.tp2_pct,
      rr_ratio: setup.rr_ratio,
    };
  }, [selectedSignal?.trade_setup]);

  const [llmConfig, setLlmConfig] = useState<LlmConfig>(() => readStoredLlmConfig());

  const tabLabel = useMemo(() => {
    const labels: Record<string, string> = isEn
      ? {
          DECISION: 'Decision Center', RADAR: 'Signal Radar', WATCHLIST: 'Tracking',
          RANKING: 'Candidate Ranking', MARKET: 'Market Context', MULTISCAN: 'Multi-Scan',
          BACKTEST: 'Backtest Experiments', FORWARD: 'Forward Test', AUDIT: 'Model Audit',
          TELEMETRY: 'Telemetry', HISTORY: 'System History', MODELS: 'Models',
          UPDATES: 'Updates', SETTINGS: 'System Settings',
        }
      : isZh
        ? {
            DECISION: '决策中心', RADAR: '信号雷达', WATCHLIST: '跟踪列表', RANKING: '候选排名',
            MARKET: '市场环境', MULTISCAN: '多币扫描', BACKTEST: '回测实验', FORWARD: '前向测试',
            AUDIT: '模型审计', TELEMETRY: '运行监控', HISTORY: '系统历史', MODELS: '模型',
            UPDATES: '更新', SETTINGS: '系统设置',
          }
        : isKo
          ? {
              DECISION: '의사결정 센터', RADAR: '시그널 레이더', WATCHLIST: '트래킹', RANKING: '후보 랭킹',
              MARKET: '시장 컨텍스트', MULTISCAN: '멀티 스캔', BACKTEST: '백테스트', FORWARD: '포워드 테스트',
              AUDIT: '모델 감사', TELEMETRY: '텔레메트리', HISTORY: '시스템 기록', MODELS: '모델',
              UPDATES: '업데이트', SETTINGS: '시스템 설정',
            }
          : {
              DECISION: 'Trung tâm quyết định', RADAR: 'Radar tín hiệu', WATCHLIST: 'Đang theo dõi',
              RANKING: 'Xếp hạng ứng viên', MARKET: 'Bối cảnh thị trường', MULTISCAN: 'Quét đa coin',
              BACKTEST: 'Thí nghiệm backtest', FORWARD: 'Forward test', AUDIT: 'Kiểm định mô hình',
              TELEMETRY: 'Giám sát vận hành', HISTORY: 'Lịch sử hệ thống', MODELS: 'Mô hình',
              UPDATES: 'Cập nhật', SETTINGS: 'Cài đặt hệ thống',
            };
    return labels[activeTab] || activeTab;
  }, [activeTab, isEn, isZh, isKo]);

  const appContext = useMemo<Record<string, unknown>>(() => ({
    language,
    active_tab: activeTab,
    active_tab_label: tabLabel,
    gui_version: guiVersion,
    active_scan_modes: activeScanModes,
    selected_model_key: selectedModelKey || null,
    scanner_model_id: scannerModelId || status?.model_id || status?.model_version || null,
    scanner_status: status?.scanner_status || 'UNKNOWN',
    dashboard_counts: {
      active_signals: signalCount,
      candidates: candidatesCount,
      tracked_positions: trackingCount,
    },
    assistant_scope: 'Trả lời câu hỏi về tính năng Đảo Vàng AI Radar, cách dùng màn hình hiện tại và dữ liệu coin đang mở.',
  }), [
    activeScanModes,
    activeTab,
    candidatesCount,
    guiVersion,
    language,
    scannerModelId,
    selectedModelKey,
    signalCount,
    status?.model_id,
    status?.model_version,
    status?.scanner_status,
    tabLabel,
    trackingCount,
  ]);

  const requestContext = useMemo<NonNullable<AiAskRequest['context']>>(() => ({
    current_price: currentPrice ?? undefined,
    signal_price: selectedSignal?.signal_price ?? undefined,
    probability: probability ?? undefined,
    risk_level: riskLevel,
    trade_setup: tradeSetup,
    attribution_method: coinDetail?.attribution_method || 'none',
    feature_drivers: coinDetail?.feature_drivers || [],
    metrics,
    btc_regime: deepAnalysis?.btc_regime || 'NEUTRAL',
    parabolic_pump: deepAnalysis?.pump_analysis?.detected || false,
    app_context: {
      ...appContext,
      llm_provider: llmConfig.provider,
      llm_model_id: llmConfig.modelId || 'antigravity/gemini-3.7-flash-tiered',
    },
  }), [
    appContext,
    coinDetail?.attribution_method,
    coinDetail?.feature_drivers,
    currentPrice,
    deepAnalysis?.btc_regime,
    deepAnalysis?.pump_analysis?.detected,
    llmConfig.modelId,
    llmConfig.provider,
    metrics,
    probability,
    riskLevel,
    selectedSignal?.signal_price,
    tradeSetup,
  ]);

  const welcomeContent = isZh
    ? `👋 你好！我是 **Đảo Vàng AI Radar** 应用助手。当前位于 **${tabLabel}**，正在查看 **${symbol}**。你可以询问功能、模型、指标或当前页面的操作方式。`
    : isKo
      ? `👋 안녕하세요! **Đảo Vàng AI Radar** 앱 어시스턴트입니다. 현재 **${tabLabel}**에서 **${symbol}**을(를) 보고 있습니다. 기능, 모델, 지표 또는 화면 사용법을 물어보세요.`
      : isEn
        ? `👋 Hi! I’m the **Đảo Vàng AI Radar** app assistant. You’re on **${tabLabel}**, with **${symbol}** in context. Ask about features, models, metrics, or how to use this screen.`
        : `👋 Xin chào! Tôi là trợ lý của ứng dụng **Đảo Vàng AI Radar**. Bạn đang ở **${tabLabel}**, với **${symbol}** trong ngữ cảnh. Hãy hỏi về tính năng, mô hình, chỉ số hoặc cách dùng màn hình này.`;

  const [internalIsOpen, setInternalIsOpen] = useState(false);
  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>(() => [{
    id: 'floating-welcome',
    role: 'assistant',
    content: welcomeContent,
    timestamp: timestamp(),
    providerUsed: 'Trợ lý Đảo Vàng AI Radar',
  }]);
  const [inputQuestion, setInputQuestion] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const isOpen = open ?? internalIsOpen;
  const setOpen = useCallback((nextOpen: boolean) => {
    if (open === undefined) setInternalIsOpen(nextOpen);
    onOpenChange?.(nextOpen);
  }, [onOpenChange, open]);

  useEffect(() => {
    const handleConfigChange = (event: Event) => {
      const nextConfig = (event as CustomEvent<LlmConfig>).detail;
      if (nextConfig) setLlmConfig(nextConfig);
    };
    window.addEventListener(LLM_CONFIG_CHANGED_EVENT, handleConfigChange);
    return () => window.removeEventListener(LLM_CONFIG_CHANGED_EVENT, handleConfigChange);
  }, []);

  // When the operator has not saved a browser override, inherit the model
  // configured by the server so a deployment-level model change is respected.
  useEffect(() => {
    if (!isAdmin || hasStoredLlmConfig()) return undefined;
    let cancelled = false;
    fetch('/api/ai/config', { cache: 'no-store' })
      .then((response) => (response.ok ? response.json() : null))
      .then((data: Partial<LlmConfig> | null) => {
        if (cancelled || !data) return;
        setLlmConfig((previous) => ({
          ...previous,
          provider: data.provider || previous.provider,
          modelId: data.modelId || previous.modelId,
          baseUrl: data.baseUrl || previous.baseUrl,
          enabled: data.enabled ?? previous.enabled,
        }));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [isAdmin]);

  useEffect(() => {
    if (!isOpen) return;
    inputRef.current?.focus();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !chatContainerRef.current) return;
    chatContainerRef.current.scrollTo({
      top: chatContainerRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [isLoading, isOpen, messages]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && isOpen && !isConfigModalOpen) {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isConfigModalOpen, isOpen, setOpen]);

  const quickPrompts = useMemo(() => {
    if (isZh) {
      return [
        { label: '🧭 应用有哪些功能？', prompt: '请介绍 Đảo Vàng AI Radar 应用的主要功能和完整使用流程。' },
        { label: '📚 解释当前页面', prompt: `请解释当前的 ${tabLabel} 页面应该如何使用，以及关键字段代表什么。` },
        { label: '🧠 当前模型如何工作？', prompt: '当前 Đảo Vàng AI Radar 使用什么模型？概率、风险等级和信号是如何得到的？' },
        { label: '📊 分析当前币种', prompt: `请结合当前数据分析 ${symbol}，并说明最重要的风险依据。` },
      ];
    }
    if (isKo) {
      return [
        { label: '🧭 앱 기능은 무엇인가요?', prompt: 'Đảo Vàng AI Radar 앱의 주요 기능과 전체 사용 흐름을 설명해 주세요.' },
        { label: '📚 현재 화면 설명', prompt: `현재 ${tabLabel} 화면을 어떻게 사용하는지, 주요 필드의 의미를 설명해 주세요.` },
        { label: '🧠 모델은 어떻게 작동하나요?', prompt: '현재 Đảo Vàng AI Radar 모델과 확률, 위험 등급, 시그널 산출 방식을 설명해 주세요.' },
        { label: '📊 현재 코인 분석', prompt: `현재 데이터로 ${symbol}을 분석하고 핵심 리스크 근거를 알려 주세요.` },
      ];
    }
    if (isEn) {
      return [
        { label: '🧭 What can this app do?', prompt: 'Explain Đảo Vàng AI Radar’s main features and the recommended end-to-end workflow.' },
        { label: '📚 Explain this screen', prompt: `Explain how to use the current ${tabLabel} screen and what its key fields mean.` },
        { label: '🧠 How does the model work?', prompt: 'What model is Đảo Vàng AI Radar using now, and how are probability, risk, and signals produced?' },
        { label: '📊 Analyze current coin', prompt: `Analyze ${symbol} using the current context and explain the most important risk evidence.` },
      ];
    }
    return [
      { label: '🧭 Ứng dụng có tính năng gì?', prompt: 'Hãy giới thiệu các tính năng chính của Đảo Vàng AI Radar và quy trình sử dụng từ đầu đến cuối.' },
      { label: '📚 Giải thích màn hình này', prompt: `Hãy giải thích cách dùng màn hình ${tabLabel} hiện tại và ý nghĩa các trường quan trọng.` },
      { label: '🧠 Mô hình hoạt động thế nào?', prompt: 'Đảo Vàng AI Radar đang dùng mô hình nào? Xác suất, mức rủi ro và tín hiệu được tạo ra như thế nào?' },
      { label: '📊 Phân tích coin hiện tại', prompt: `Hãy phân tích ${symbol} theo dữ liệu hiện tại và giải thích các bằng chứng rủi ro quan trọng nhất.` },
    ];
  }, [isEn, isKo, isZh, symbol, tabLabel]);

  const handleSaveConfig = (newConfig: LlmConfig) => {
    setLlmConfig(newConfig);
    saveStoredLlmConfig(newConfig);
  };

  const handleCopyMessage = async (id: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedId(id);
      window.setTimeout(() => setCopiedId(null), 1800);
    } catch {
      // Clipboard permissions are optional; the chat remains usable without it.
    }
  };

  const handleSendQuestion = async (overrideQuestion?: string) => {
    if (!isAdmin) {
      onRequireAdmin?.(
        isEn
          ? 'Admin login is required to query the AI Quant Assistant (LLM).'
          : 'Tính năng Trợ lý AI Định lượng (LLM) dành riêng cho Quản trị viên. Vui lòng đăng nhập Admin để sử dụng.'
      );
      return;
    }
    const question = (overrideQuestion ?? inputQuestion).trim();
    if (!question || isLoading) return;
    const userMessage: ChatMessage = {
      id: `floating-user-${Date.now()}`,
      role: 'user',
      content: question,
      timestamp: timestamp(),
    };
    const history = messages
      .filter((message): message is ChatMessage & { role: 'user' | 'assistant' } => (
        (message.role === 'user' || message.role === 'assistant')
        && message.id !== 'floating-welcome'
        && !message.isError
      ))
      .slice(-8)
      .map((message) => ({ role: message.role, content: message.content }));

    setMessages((previous) => [...previous, userMessage]);
    setInputQuestion('');
    setIsLoading(true);

    try {
      const payload: AiAskRequest = {
        question,
        symbol,
        context: requestContext,
        llm_config: llmConfig,
        history,
      };
      const response = await fetch('/api/ai/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json() as Partial<AiAskResponse> & { error?: string };
      if (!response.ok) {
        throw new Error(data.error || `HTTP ${response.status}`);
      }

      setMessages((previous) => [...previous, {
        id: `floating-bot-${Date.now()}`,
        role: 'assistant',
        content: data.answer || (isEn ? 'No answer was returned.' : 'Không nhận được câu trả lời từ máy chủ.'),
        timestamp: timestamp(),
        providerUsed: data.provider && data.model ? `${data.provider} · ${data.model}` : 'Trợ lý Đảo Vàng AI Radar',
      }]);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Network error';
      setMessages((previous) => [...previous, {
        id: `floating-error-${Date.now()}`,
        role: 'assistant',
        content: `⚠️ ${isEn ? 'Could not process the question:' : 'Không thể xử lý câu hỏi:'} ${message}`,
        timestamp: timestamp(),
        isError: true,
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const modelLabel = llmConfig.modelId || 'antigravity/gemini-3.7-flash-tiered';
  const contextStatus = `${tabLabel} · ${symbol} · ${modelLabel}`;

  return (
    <>
      <div className={`fixed right-2 z-[45] flex flex-col items-end gap-3 sm:right-5 sm:bottom-5 ${
        guiVersion === 'v2'
          ? hasMobileActionBar ? 'mobile-ai-anchor-actions' : 'mobile-ai-anchor-nav'
          : 'mobile-ai-anchor-default'
      }`}>
        {isOpen ? (
          <section
            role="dialog"
            aria-label={isEn ? 'Đảo Vàng AI Radar assistant' : 'Trợ lý Đảo Vàng AI Radar'}
            className="flex h-[min(640px,calc(100dvh-9.5rem))] w-[min(420px,calc(100vw-1rem))] flex-col overflow-hidden rounded-2xl border border-amber-500/30 bg-slate-950/95 shadow-2xl shadow-black/50 backdrop-blur-2xl sm:h-[min(680px,calc(100vh-2.5rem))] sm:w-[420px]"
          >
            <div className="flex items-center justify-between gap-3 border-b border-slate-800/90 bg-slate-900/90 px-3.5 py-3">
              <div className="flex min-w-0 items-center gap-2.5">
                <div className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-amber-300 via-amber-500 to-orange-600 text-slate-950 shadow-lg shadow-amber-500/20">
                  <Bot className="h-5 w-5" />
                  <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-slate-900 bg-emerald-400" />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 truncate text-xs font-bold text-slate-100 sm:text-sm">
                    <span>{isEn ? 'Đảo Vàng AI Radar Assistant' : isZh ? 'Đảo Vàng AI Radar 应用助手' : isKo ? 'Đảo Vàng AI Radar 앱 어시스턴트' : 'Trợ lý Đảo Vàng AI Radar'}</span>
                    <span className="rounded border border-cyan-500/25 bg-cyan-500/10 px-1.5 py-0.5 font-mono text-[9px] font-bold text-cyan-300">LIVE</span>
                  </div>
                  <p className="truncate text-[10px] text-slate-400">
                    {isEn ? 'Features, workflow & live context' : isZh ? '功能、流程与实时上下文' : isKo ? '기능, 워크플로 및 실시간 컨텍스트' : 'Tính năng, quy trình & dữ liệu thời gian thực'}
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <button
                  type="button"
                  onClick={() => setIsConfigModalOpen(true)}
                  className="rounded-lg border border-slate-700 bg-slate-800/80 p-2 text-slate-300 transition hover:border-amber-500/50 hover:text-amber-300"
                  aria-label={isEn ? 'Configure AI model' : 'Cấu hình mô hình AI'}
                  title={isEn ? 'Configure AI model' : 'Cấu hình mô hình AI'}
                >
                  <Settings className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-800 hover:text-slate-100"
                  aria-label={isEn ? 'Minimize assistant' : 'Thu nhỏ trợ lý'}
                  title={isEn ? 'Minimize' : 'Thu nhỏ'}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="border-b border-slate-800/80 bg-slate-950/70 px-3.5 py-2.5">
              <div className="flex items-center gap-2 text-[10px] text-slate-400">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
                <span className="truncate" title={contextStatus}>{contextStatus}</span>
              </div>
              <div className="mt-1 flex gap-1.5 overflow-x-auto whitespace-nowrap [&::-webkit-scrollbar]:hidden">
                <span className="rounded-md border border-slate-800 bg-slate-900 px-1.5 py-0.5 font-mono text-[9px] text-slate-500">{signalCount} {isEn ? 'signals' : isZh ? '信号' : isKo ? '시그널' : 'tín hiệu'}</span>
                <span className="rounded-md border border-slate-800 bg-slate-900 px-1.5 py-0.5 font-mono text-[9px] text-slate-500">{candidatesCount} {isEn ? 'candidates' : isZh ? '候选' : isKo ? '후보' : 'ứng viên'}</span>
                <span className="rounded-md border border-slate-800 bg-slate-900 px-1.5 py-0.5 font-mono text-[9px] text-slate-500">{activeScanModes.join(' + ') || '—'}</span>
                {currentPrice != null && <span className="rounded-md border border-sky-500/20 bg-sky-500/10 px-1.5 py-0.5 font-mono text-[9px] text-sky-300">${formatPrice(currentPrice)}</span>}
                {probability != null && <span className="rounded-md border border-amber-500/20 bg-amber-500/10 px-1.5 py-0.5 font-mono text-[9px] text-amber-300">{probability.toFixed(1)}%</span>}
              </div>
            </div>

            <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
              <div className="shrink-0">
                <div className="mb-1.5 flex items-center gap-1 text-[10px] font-mono uppercase text-slate-500">
                  <HelpCircle className="h-3 w-3 text-amber-400" />
                  <span>{isEn ? 'Quick questions' : isZh ? '快捷提问' : isKo ? '빠른 질문' : 'Câu hỏi gợi ý'}</span>
                </div>
                <div className="flex gap-1.5 overflow-x-auto pb-1 [&::-webkit-scrollbar]:hidden">
                  {quickPrompts.map((prompt) => (
                    <button
                      key={prompt.label}
                      type="button"
                      onClick={() => void handleSendQuestion(prompt.prompt)}
                      disabled={isLoading}
                      className="shrink-0 rounded-full border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-left text-[10px] text-slate-300 transition hover:border-amber-500/50 hover:bg-amber-500/10 hover:text-amber-200 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {prompt.label}
                    </button>
                  ))}
                </div>
              </div>

              <div ref={chatContainerRef} aria-live="polite" className="min-h-0 flex-1 space-y-3 overflow-y-auto rounded-xl border border-slate-800/80 bg-slate-950/80 p-2.5 sm:p-3">
                {messages.map((message) => {
                  const isUser = message.role === 'user';
                  return (
                    <div key={message.id} className={`flex items-start gap-2 ${isUser ? 'justify-end' : 'justify-start'}`}>
                      {!isUser && (
                        <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-300">
                          <Sparkles className="h-3.5 w-3.5" />
                        </div>
                      )}
                      <div className={`max-w-[88%] rounded-xl px-3 py-2.5 text-xs leading-relaxed ${
                        isUser
                          ? 'rounded-tr-none bg-gradient-to-r from-amber-500 to-amber-400 text-slate-950'
                          : message.isError
                            ? 'rounded-tl-none border border-rose-800/80 bg-rose-950/60 text-rose-200'
                            : 'rounded-tl-none border border-slate-800 bg-slate-900/95 text-slate-200'
                      }`}>
                        {!isUser && message.providerUsed && (
                          <div className="mb-2 flex items-center justify-between gap-2 border-b border-slate-800 pb-1.5 text-[9px]">
                            <span className="truncate font-mono font-semibold text-amber-300">{message.providerUsed}</span>
                            <button
                              type="button"
                              onClick={() => void handleCopyMessage(message.id, message.content)}
                              className="flex shrink-0 items-center gap-1 text-slate-500 transition hover:text-slate-200"
                              aria-label={isEn ? 'Copy answer' : 'Sao chép câu trả lời'}
                            >
                              {copiedId === message.id ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                            </button>
                          </div>
                        )}
                        {isUser ? <div className="whitespace-pre-wrap font-medium">{message.content}</div> : <MarkdownRenderer content={message.content} />}
                        <div className={`mt-1.5 text-right font-mono text-[9px] ${isUser ? 'text-slate-800' : 'text-slate-500'}`}>{message.timestamp}</div>
                      </div>
                      {isUser && (
                        <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg border border-slate-700 bg-slate-800 text-slate-300">
                          <User className="h-3.5 w-3.5" />
                        </div>
                      )}
                    </div>
                  );
                })}
                {isLoading && (
                  <div className="flex items-start gap-2">
                    <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-300">
                      <Sparkles className="h-3.5 w-3.5 animate-pulse" />
                    </div>
                    <div className="flex items-center gap-2 rounded-xl rounded-tl-none border border-slate-800 bg-slate-900 px-3 py-2.5 text-[10px] text-slate-400">
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-400" />
                      <span>{isEn ? 'Reading app context…' : isZh ? '正在读取应用上下文…' : isKo ? '앱 컨텍스트를 읽는 중…' : 'Đang đọc ngữ cảnh ứng dụng…'}</span>
                    </div>
                  </div>
                )}
              </div>

              <div className="flex shrink-0 items-end gap-2">
                <div className="relative min-w-0 flex-1">
                  <textarea
                    ref={inputRef}
                    value={inputQuestion}
                    onChange={(event) => setInputQuestion(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        void handleSendQuestion();
                      }
                    }}
                    rows={2}
                    placeholder={isEn ? 'Ask about the app or current context…' : isZh ? '询问应用或当前上下文…' : isKo ? '앱 또는 현재 컨텍스트에 대해 질문하세요…' : 'Hỏi về ứng dụng hoặc dữ liệu hiện tại…'}
                    className="w-full resize-none rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 pr-2 text-xs leading-relaxed text-slate-100 placeholder-slate-500 transition focus:border-amber-500 focus:outline-none"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => void handleSendQuestion()}
                  disabled={!inputQuestion.trim() || isLoading}
                  className="flex h-[58px] shrink-0 items-center justify-center rounded-xl bg-amber-500 px-3.5 text-slate-950 shadow-md shadow-amber-500/20 transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
                  aria-label={isEn ? 'Send question' : 'Gửi câu hỏi'}
                >
                  <Send className="h-4 w-4" />
                </button>
              </div>
              <div className="flex items-center justify-between gap-2 px-0.5 text-[9px] text-slate-600">
                <span className="truncate">{isEn ? 'Enter to send · Shift+Enter for newline' : 'Enter để gửi · Shift+Enter để xuống dòng'}</span>
                <button
                  type="button"
                  onClick={() => setMessages((previous) => previous.filter((message) => message.id === 'floating-welcome'))}
                  disabled={messages.length <= 1 || isLoading}
                  className="flex shrink-0 items-center gap-1 text-slate-500 transition hover:text-rose-300 disabled:cursor-not-allowed disabled:opacity-40"
                  title={isEn ? 'Clear conversation' : 'Xóa hội thoại'}
                >
                  <Trash2 className="h-3 w-3" />
                  <span>{isEn ? 'Clear' : 'Xóa'}</span>
                </button>
              </div>
            </div>
          </section>
        ) : (
          <button
            data-testid="floating-ai-button"
            type="button"
            onClick={() => {
              if (!isAdmin && onRequireAdmin) {
                onRequireAdmin(
                  isEn
                    ? 'Admin login is required to use the AI Quant Assistant (LLM).'
                    : 'Tính năng Trợ lý AI Định lượng (LLM) dành riêng cho Quản trị viên. Vui lòng đăng nhập Admin để sử dụng.'
                );
                return;
              }
              setOpen(true);
            }}
            aria-expanded={false}
            aria-label={isEn ? 'Open Đảo Vàng AI Radar assistant' : 'Mở Trợ lý Đảo Vàng AI Radar'}
            className="group relative flex h-14 w-14 items-center justify-center rounded-full border border-amber-300/70 bg-gradient-to-br from-amber-300 via-amber-500 to-orange-600 text-slate-950 shadow-xl shadow-amber-950/50 transition hover:scale-105 hover:shadow-amber-500/30 focus:outline-none focus:ring-2 focus:ring-amber-300 focus:ring-offset-2 focus:ring-offset-slate-950 cursor-pointer"
          >
            {isAdmin && <span className="absolute inset-0 rounded-full bg-amber-400/30 animate-ping" />}
            <span className="relative flex h-full w-full items-center justify-center rounded-full">
              <MessageCircle className="h-6 w-6" />
              {isAdmin ? (
                <span className="absolute right-2 top-2 h-2.5 w-2.5 rounded-full border-2 border-orange-500 bg-emerald-400" />
              ) : (
                <span className="absolute -right-0.5 -top-0.5 flex h-5 w-5 items-center justify-center rounded-full border border-amber-400/80 bg-slate-950 text-amber-300 shadow">
                  <Lock className="h-2.5 w-2.5" />
                </span>
              )}
            </span>
            <span className="pointer-events-none absolute bottom-full right-0 mb-2 w-max max-w-[240px] translate-y-1 rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-[10px] font-medium text-slate-200 opacity-0 shadow-xl transition group-hover:translate-y-0 group-hover:opacity-100">
              {!isAdmin
                ? isEn
                  ? 'AI Assistant (Admin Login Required)'
                  : 'Trợ lý AI Định lượng (Cần đăng nhập Admin)'
                : isEn
                  ? 'Ask Đảo Vàng AI Radar'
                  : isZh
                    ? '询问 Đảo Vàng AI Radar 助手'
                    : isKo
                      ? 'Đảo Vàng AI Radar 어시스턴트에게 질문'
                      : 'Hỏi Trợ lý Đảo Vàng AI Radar'}
            </span>
          </button>
        )}
      </div>

      <LlmConfigModal
        isOpen={isConfigModalOpen}
        onClose={() => setIsConfigModalOpen(false)}
        config={llmConfig}
        onSaveConfig={handleSaveConfig}
      />
    </>
  );
};
