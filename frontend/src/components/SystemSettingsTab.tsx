import React, { useState } from 'react';
import {
  Settings, Key, Cpu, Globe, CheckCircle2,
  AlertTriangle, Loader2, Eye, EyeOff, Sparkles, RefreshCw,
  Sliders, ShieldCheck, Zap, Check,
  Bot, Server, Lock
} from 'lucide-react';
import { useTranslation, LANGUAGES } from '../i18n/LanguageContext';
import type { LlmConfig, LlmProvider } from '../types';

interface SystemSettingsTabProps {
  guiVersion?: 'v1' | 'v2';
  onSelectGuiVersion?: (version: 'v1' | 'v2') => void;
  threshold?: number;
  setThreshold?: (val: number) => void;
  activeScanModes?: string[];
  onOpenWatchlistModal?: () => void;
  onLogout?: () => void;
  isDevMode?: boolean;
  setIsDevMode?: (val: boolean) => void;
}

const STORAGE_CONFIG_KEY = 'dao_vang_llm_config';

const PROVIDER_OPTIONS: { id: LlmProvider; name: string; icon: string; defaultModel: string; placeholderUrl?: string; desc: string; badge?: string }[] = [
  {
    id: 'openai',
    name: 'OpenAI / AI Proxy (Mặc Định)',
    icon: '🟢',
    defaultModel: 'antigravity/gemini-3.7-flash-tiered',
    placeholderUrl: 'https://proxy-ai.comaygiauco.com/v1',
    desc: 'Mô hình chuẩn mặc định của hệ thống: Gemini 3.7 Flash Tiered tốc độ cao',
    badge: 'Mặc Định',
  },
  {
    id: 'gemini',
    name: 'Google Gemini',
    icon: '✨',
    defaultModel: 'gemini-1.5-flash',
    desc: 'Tốc độ phản hồi cực nhanh, nhận thức ngữ cảnh tốt',
    badge: 'Khuyên Dùng',
  },
  {
    id: 'deepseek',
    name: 'DeepSeek AI',
    icon: '🐳',
    defaultModel: 'deepseek-chat',
    placeholderUrl: 'https://api.deepseek.com',
    desc: 'Chi phí cực thấp, hiệu năng định lượng và suy luận sâu vượt trội',
    badge: 'Tiết Kiệm',
  },
  {
    id: 'claude',
    name: 'Anthropic Claude',
    icon: '🟣',
    defaultModel: 'claude-3-5-haiku-20241022',
    desc: 'Văn phong tự nhiên, sắc sảo, đánh giá rủi ro tài chính chuyên sâu',
  },
  {
    id: 'ollama',
    name: 'Local / Ollama / Custom LLM',
    icon: '💻',
    defaultModel: 'llama3.2',
    placeholderUrl: 'http://localhost:11434/v1',
    desc: 'Chạy offline bảo mật 100% trên GPU/máy chủ riêng không phụ thuộc internet',
    badge: 'Bảo Mật',
  },
];

export const SystemSettingsTab: React.FC<SystemSettingsTabProps> = ({
  guiVersion = 'v2',
  onSelectGuiVersion,
  threshold = 0.70,
  setThreshold,
  activeScanModes = ['volatile'],
  onOpenWatchlistModal,
  onLogout,
  isDevMode = false,
  setIsDevMode,
}) => {
  const { language, setLanguage, t } = useTranslation();
  const isEn = language === 'en';
  const isZh = language === 'zh';
  const isKo = language === 'ko';

  // LLM Config state
  const [llmConfig, setLlmConfig] = useState<LlmConfig>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_CONFIG_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as Partial<LlmConfig>;
        // Migrate older browser state without retaining a plaintext API key.
        const safeConfig = { ...parsed, apiKey: '' } as LlmConfig;
        localStorage.setItem(STORAGE_CONFIG_KEY, JSON.stringify(safeConfig));
        return safeConfig;
      }
    } catch {
      // fallback
    }
    return {
      provider: 'openai',
      apiKey: '',
      modelId: 'antigravity/gemini-3.7-flash-tiered',
      baseUrl: 'https://proxy-ai.comaygiauco.com/v1',
      enabled: true,
    };
  });

  const [provider, setProvider] = useState<LlmProvider>(llmConfig.provider || 'openai');
  const [apiKey, setApiKey] = useState<string>(llmConfig.apiKey || '');
  const [modelId, setModelId] = useState<string>(llmConfig.modelId || 'antigravity/gemini-3.7-flash-tiered');
  const [baseUrl, setBaseUrl] = useState<string>(llmConfig.baseUrl || 'https://proxy-ai.comaygiauco.com/v1');
  const [enabled, setEnabled] = useState<boolean>(llmConfig.enabled !== false);
  const [showKey, setShowKey] = useState<boolean>(false);

  const [testing, setTesting] = useState<boolean>(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<boolean>(false);
  const [clearedCache, setClearedCache] = useState<boolean>(false);

  // Auto-fetch default server AI config if fields are empty
  React.useEffect(() => {
    if (!apiKey) {
      fetch('/api/ai/config')
        .then((res) => res.json())
        .then((data) => {
          if (data && data.provider) {
            if (data.provider) setProvider(data.provider);
            if (data.modelId) setModelId(data.modelId);
            if (data.baseUrl) setBaseUrl(data.baseUrl);
          }
        })
        .catch(() => {});
    }
  }, [apiKey]);

  const currentProviderMeta = PROVIDER_OPTIONS.find(p => p.id === provider) || PROVIDER_OPTIONS[0];

  const handleSelectProvider = (newProvider: LlmProvider) => {
    setProvider(newProvider);
    const meta = PROVIDER_OPTIONS.find(p => p.id === newProvider);
    if (meta) {
      if (!modelId || PROVIDER_OPTIONS.some(p => p.defaultModel === modelId)) {
        setModelId(meta.defaultModel);
      }
      if (meta.placeholderUrl) {
        setBaseUrl(meta.placeholderUrl);
      } else {
        setBaseUrl('');
      }
    }
    setTestResult(null);
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch('/api/ai/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: 'Kiểm tra kết nối API. Hãy phản hồi ngắn gọn xác nhận hoạt động bình thường.',
          symbol: 'BTCUSDT',
          context: { current_price: 95000, probability: 75 },
          llm_config: {
            provider,
            apiKey: apiKey.trim(),
            modelId: modelId.trim() || currentProviderMeta.defaultModel,
            baseUrl: baseUrl.trim(),
            enabled: true,
          },
        }),
      });
      const data = await res.json();
      if (res.ok && data.answer) {
        setTestResult({
          success: true,
          message: isZh ? `连接成功！响应模型: ${data.model} (${data.provider})` : isKo ? `연결 성공! 응답 모델: ${data.model} (${data.provider})` : isEn ? `Connected successfully! Responded model: ${data.model} (${data.provider})` : `Kết nối thành công! Mô hình phản hồi: ${data.model} (${data.provider})`,
        });
      } else {
        setTestResult({
          success: false,
          message: data.error || (isEn ? 'Failed to connect. Please check API Key or Base URL.' : 'Không thể kết nối. Vui lòng kiểm tra lại API Key hoặc Endpoint.'),
        });
      }
    } catch (err: any) {
      setTestResult({
        success: false,
        message: err.message || (isEn ? 'Network error occurred.' : 'Lỗi kết nối mạng.'),
      });
    } finally {
      setTesting(false);
    }
  };

  const handleSaveConfig = () => {
    const updated: LlmConfig = {
      provider,
      apiKey: apiKey.trim(),
      modelId: modelId.trim() || currentProviderMeta.defaultModel,
      baseUrl: baseUrl.trim(),
      enabled,
    };
    setLlmConfig(updated);
    try {
      localStorage.setItem(STORAGE_CONFIG_KEY, JSON.stringify({ ...updated, apiKey: '' }));
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (e) {
      console.error('Failed to save LLM config', e);
    }
  };

  const handleResetDefaults = async () => {
    try {
      const res = await fetch('/api/ai/config');
      const data = await res.json();
      if (data && data.provider) {
        setProvider(data.provider || 'openai');
        setApiKey('');
        setModelId(data.modelId || 'antigravity/gemini-3.7-flash-tiered');
        setBaseUrl(data.baseUrl || 'https://proxy-ai.comaygiauco.com/v1');
        setEnabled(true);
        setTestResult(null);
        return;
      }
    } catch {}
    setProvider('openai');
    setApiKey('');
    setModelId('antigravity/gemini-3.7-flash-tiered');
    setBaseUrl('https://proxy-ai.comaygiauco.com/v1');
    setEnabled(true);
    setTestResult(null);
  };

  const handleClearAppCache = () => {
    try {
      sessionStorage.clear();
      setClearedCache(true);
      setTimeout(() => setClearedCache(false), 3000);
    } catch (e) {
      console.error('Failed to clear cache', e);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto space-y-4 pr-1">
      <a href="#account" className="block rounded-xl border border-sky-700/40 bg-sky-950/20 p-4 text-sm text-sky-200 hover:bg-sky-900/20">Mở trang Tài khoản & giao dịch →</a>
      {/* Header Banner */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-slate-950/80 border border-slate-800 rounded-xl shadow-lg">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-amber-600 to-amber-400 text-slate-950 flex items-center justify-center font-bold shadow-md">
            <Settings className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm sm:text-base font-bold text-slate-100 uppercase tracking-wide flex items-center gap-2">
              <span>{isZh ? '系统与 AI 语言模型配置中心' : isKo ? '시스템 및 AI 언어 모델 설정 센터' : isEn ? 'SYSTEM & AI LLM CONFIGURATION CENTER' : 'CẤU HÌNH HỆ THỐNG & TRỢ LÝ AI (LLM SETTINGS)'}</span>
              <span className="text-[10px] font-mono font-bold text-amber-400 px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/30">
                PRO CONFIG
              </span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {isZh ? '管理 AI 模型 API 密钥、多模型调度、雷达预警阈值与系统偏好' : isKo ? 'AI 모델 API 키 관리, 멀티 모델 연동, 레이더 경보 임계값 및 시스템 설정' : isEn ? 'Manage AI API keys, multi-model providers, radar alert thresholds, and system preferences' : 'Quản lý API Key LLM, chuyển đổi mô hình AI, cài đặt ngưỡng cảnh báo radar & tùy chỉnh giao diện'}
            </p>
          </div>
        </div>

        {saveSuccess && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-950 border border-emerald-600 text-emerald-300 text-xs font-bold animate-in fade-in">
            <Check className="w-4 h-4" />
            <span>{isEn ? 'Saved successfully!' : 'Đã lưu cấu hình thành công!'}</span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* LEFT COLUMN: LLM & AI PROVIDER CONFIGURATION (8 cols) */}
        <div className="lg:col-span-8 space-y-4">
          {/* Card 1: AI Provider & API Key */}
          <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-4 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <div className="flex items-center gap-2">
                <Bot className="w-4 h-4 text-amber-400" />
                <h3 className="text-xs sm:text-sm font-bold text-slate-100 uppercase tracking-wide">
                  {isZh ? '1. AI 语言模型配置 (LLM Providers)' : isKo ? '1. AI 언어 모델 연동 설정 (LLM Providers)' : isEn ? '1. AI Assistant & LLM Provider API' : '1. Cấu Hình API Trợ Lý AI (LLM Providers)'}
                </h3>
              </div>
              <label className="flex items-center gap-2 cursor-pointer text-xs font-medium text-slate-300">
                <span>{isEn ? 'Enable AI Analysis' : 'Kích hoạt Trợ lý AI'}</span>
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(e) => setEnabled(e.target.checked)}
                  className="rounded border-slate-700 text-amber-500 focus:ring-amber-500 bg-slate-900 w-4 h-4"
                />
              </label>
            </div>

            {/* Server Default AI Info Banner */}
            <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/25 flex items-start gap-2.5 text-xs">
              <Sparkles className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <div className="text-slate-300 leading-relaxed text-[11px]">
                <span className="font-semibold text-amber-300">Model Mặc Định Máy Chủ: </span>
                Hệ thống máy chủ đã được cấu hình sẵn <strong>Gemini 3.7 Flash Tiered</strong>. Người dùng có thể hỏi đáp AI trực tiếp mà không cần cấu hình key, hoặc nhập cấu hình bên dưới để sử dụng key cá nhân riêng.
              </div>
            </div>

            {/* Provider Options Grid */}
            <div className="space-y-2">
              <label className="block text-[11px] font-bold text-slate-300 uppercase tracking-wider">
                {isZh ? '选择 AI 提供商 (Select Provider)' : isKo ? 'AI 제공자 선택 (Select Provider)' : isEn ? 'Select AI Provider' : 'Chọn Nhà Cung Cấp Mô Hình (Provider)'}
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {PROVIDER_OPTIONS.map((opt) => {
                  const isSelected = provider === opt.id;
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => handleSelectProvider(opt.id)}
                      className={`flex items-start gap-2.5 p-3 rounded-xl border text-left transition ${
                        isSelected
                          ? 'border-amber-500 bg-amber-500/10 ring-1 ring-amber-500/40 text-amber-200 shadow-md'
                          : 'border-slate-800 bg-slate-900/60 text-slate-300 hover:border-slate-700 hover:bg-slate-800/60'
                      }`}
                    >
                      <span className="text-xl shrink-0 mt-0.5">{opt.icon}</span>
                      <div className="min-w-0 flex-1">
                        <div className="font-bold text-xs flex items-center justify-between gap-1">
                          <span className="truncate">{opt.name}</span>
                          {opt.badge && (
                            <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 font-normal">

                              {opt.badge}
                            </span>
                          )}
                        </div>
                        <div className="text-[10px] text-slate-400 mt-1 leading-normal line-clamp-2">{opt.desc}</div>
                      </div>
                      {isSelected && <CheckCircle2 className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* API Key Input */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                  <Key className="w-3.5 h-3.5 text-amber-400" />
                  <span>{isZh ? 'API 密钥 (API Key)' : isKo ? 'API 키 (API Key)' : isEn ? 'API Key' : 'Khóa API (API Key)'}</span>
                </label>
                <span className="text-[10px] text-slate-500">
                  {isZh ? '🔒 密钥仅加密保存在本地浏览器，绝不上传' : isKo ? '🔒 브라우저 로컬 저장소에만 안전 보관' : isEn ? '🔒 Stored locally in your browser only' : '🔒 Chỉ lưu cục bộ trong trình duyệt, bảo mật 100%'}
                </span>
              </div>
              <div className="relative">
                <input
                  type={showKey ? 'text' : 'password'}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={provider === 'ollama' ? (isEn ? 'Optional for local Ollama' : 'Không bắt buộc với Ollama local') : `Nhập ${currentProviderMeta.name} API Key...`}
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 pr-10 text-slate-200 font-mono text-xs focus:outline-none focus:border-amber-500 transition shadow-inner"
                />
                <button
                  type="button"
                  onClick={() => setShowKey(!showKey)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 p-1"
                >
                  {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Model ID & Base URL Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="block text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                  <Cpu className="w-3.5 h-3.5 text-sky-400" />
                  <span>{isZh ? '模型名称 (Model ID)' : isKo ? '모델 ID (Model ID)' : isEn ? 'Model ID' : 'Mã Mô Hình (Model ID)'}</span>
                </label>
                <input
                  type="text"
                  value={modelId}
                  onChange={(e) => setModelId(e.target.value)}
                  placeholder={currentProviderMeta.defaultModel}
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2 text-slate-200 font-mono text-xs focus:outline-none focus:border-amber-500 transition shadow-inner"
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                  <Globe className="w-3.5 h-3.5 text-violet-400" />
                  <span>{isZh ? '自定义接口地址 (Base URL)' : isKo ? '사용자 정의 URL (Base URL)' : isEn ? 'Custom Base URL' : 'Địa Chỉ API Riêng (Base URL)'}</span>
                </label>
                <input
                  type="text"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder={currentProviderMeta.placeholderUrl || (isEn ? 'Default official endpoint' : 'Mặc định nhà cung cấp')}
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2 text-slate-200 font-mono text-xs focus:outline-none focus:border-amber-500 transition shadow-inner"
                />
              </div>
            </div>

            {/* Test Connection Output */}
            {testResult && (
              <div
                className={`p-3.5 rounded-xl border flex items-start gap-2.5 text-xs ${
                  testResult.success
                    ? 'bg-emerald-950/70 border-emerald-700 text-emerald-200'
                    : 'bg-rose-950/70 border-rose-700 text-rose-200'
                }`}
              >
                {testResult.success ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                )}
                <div className="leading-relaxed">{testResult.message}</div>
              </div>
            )}

            {/* Actions Bar */}
            <div className="flex flex-wrap items-center justify-between gap-2.5 pt-3 border-t border-slate-800/80">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleTestConnection}
                  disabled={testing}
                  className="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold rounded-xl text-xs flex items-center gap-1.5 transition border border-slate-700 shadow-sm disabled:opacity-50"
                >
                  {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-400" /> : <Sparkles className="w-3.5 h-3.5 text-amber-400" />}
                  <span>{testing ? (isEn ? 'Testing API...' : 'Đang thử kết nối...') : (isZh ? '测试 API 连接' : isKo ? 'API 연결 테스트' : isEn ? 'Test Connection' : 'Kiểm Tra Kết Nối API')}</span>
                </button>

                <button
                  type="button"
                  onClick={handleResetDefaults}
                  className="px-3 py-2 text-slate-400 hover:text-slate-200 text-xs flex items-center gap-1 transition"
                  title={isEn ? 'Reset to default' : 'Đặt lại mặc định'}
                >
                  <RefreshCw className="w-3 h-3" />
                  <span>{isEn ? 'Reset' : 'Mặc định'}</span>
                </button>
              </div>

              <button
                type="button"
                onClick={handleSaveConfig}
                className="px-5 py-2 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold rounded-xl text-xs flex items-center gap-1.5 transition shadow-lg shadow-amber-500/20"
              >
                <Check className="w-4 h-4" />
                <span>{isZh ? '保存 AI 配置' : isKo ? 'AI 설정 저장' : isEn ? 'Save AI Config' : 'Lưu Cấu Hình AI'}</span>
              </button>
            </div>
          </div>

          {/* Card 2: Built-in Engine Architecture Info */}
          <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4 shadow-xl space-y-2.5">
            <div className="flex items-center gap-2 text-xs font-bold text-sky-400 uppercase tracking-wide">
              <Server className="w-4 h-4 text-sky-400" />
              <span>{isZh ? '内置定量摘要引擎（LLM 备用）' : isKo ? '내장 정량 요약 엔진 (LLM 대체)' : isEn ? 'Built-in Quantitative Summary (LLM Fallback)' : 'Bộ Tóm Tắt Định Lượng Tích Hợp (Dự Phòng LLM)'}</span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              {isZh
                ? '当外部 LLM 未配置或暂不可用时，系统会根据当前市场指标、交易设置和加权评分分项生成确定性摘要。评分分项不是 SHAP，也不代表因果归因。'
                : isKo
                ? '외부 LLM이 설정되지 않았거나 일시적으로 사용할 수 없으면 현재 시장 지표, 트레이드 설정 및 가중 점수 항목을 기반으로 결정론적 요약을 생성합니다. 점수 항목은 SHAP 또는 인과 귀속이 아닙니다.'
                : isEn
                ? 'When the external LLM is not configured or temporarily unavailable, Đảo Vàng AI Radar produces a deterministic summary from current market metrics, trade setup data and weighted score components. Components are not SHAP or causal attribution.'
                : 'Khi LLM ngoài chưa được cấu hình hoặc tạm thời không khả dụng, hệ thống tạo bản tóm tắt xác định từ chỉ số thị trường, Trade Setup và các thành phần điểm có trọng số hiện có. Các thành phần này không phải SHAP hay quy kết nhân quả.'}
            </p>
          </div>
        </div>

        {/* RIGHT COLUMN: RADAR & SYSTEM PREFERENCES (4 cols) */}
        <div className="lg:col-span-4 space-y-4">
          {/* Card 3: Alert & Radar Thresholds */}
          <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-4 shadow-xl space-y-3.5">
            <div className="flex items-center gap-2 border-b border-slate-800/80 pb-3">
              <Sliders className="w-4 h-4 text-amber-400" />
              <h3 className="text-xs sm:text-sm font-bold text-slate-100 uppercase tracking-wide">
                {isZh ? '2. 雷达预警阈值' : isKo ? '2. 레이더 경보 설정' : isEn ? '2. Radar Alert Threshold' : '2. Ngưỡng Cảnh Báo Radar'}
              </h3>
            </div>

            {/* Threshold Slider */}
            {setThreshold && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-300 font-medium">{isEn ? 'Probability Threshold' : 'Ngưỡng xác suất xả AI'}:</span>
                  <span className="font-mono font-bold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
                    {(threshold * 100).toFixed(0)}%
                  </span>
                </div>
                <input
                  type="range"
                  min="0.50"
                  max="0.95"
                  step="0.05"
                  value={threshold}
                  onChange={(e) => setThreshold(parseFloat(e.target.value))}
                  className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-amber-500"
                />
                <div className="flex justify-between text-[10px] text-slate-500 font-mono">
                  <span>50% (Nhạy cảm)</span>
                  <span>70% (Chuẩn)</span>
                  <span>95% (Chắc chắn)</span>
                </div>
              </div>
            )}

            {/* Active Scan Modes */}
            <div className="space-y-1.5 pt-2 border-t border-slate-800/80">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">{isEn ? 'Active Scan Modes' : 'Chế độ quét hiện tại'}:</span>
                <span className="font-mono text-xs text-sky-400 font-bold uppercase">
                  {activeScanModes.join(', ')}
                </span>
              </div>
              {onOpenWatchlistModal && (
                <button
                  type="button"
                  onClick={onOpenWatchlistModal}
                  className="w-full mt-1.5 py-1.5 px-3 bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition"
                >
                  <Zap className="w-3.5 h-3.5 text-amber-400" />
                  <span>{isZh ? '配置扫描清单 (Watchlist)' : isKo ? '스캔 프리셋 관리' : isEn ? 'Configure Scan Modes' : 'Tùy chỉnh chế độ quét'}</span>
                </button>
              )}
            </div>
          </div>

          {/* Card 4: GUI Version & Language Settings */}
          <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-4 shadow-xl space-y-3.5">
            <div className="flex items-center gap-2 border-b border-slate-800/80 pb-3">
              <ShieldCheck className="w-4 h-4 text-violet-400" />
              <h3 className="text-xs sm:text-sm font-bold text-slate-100 uppercase tracking-wide">
                {isZh ? '3. 界面与语言偏好' : isKo ? '3. 인터페이스 및 언어' : isEn ? '3. Display & Language' : '3. Giao Diện & Ngôn Ngữ'}
              </h3>
            </div>

            {/* GUI Version Toggle */}
            {onSelectGuiVersion && (
              <div className="space-y-1.5">
                <label className="block text-[11px] font-bold text-slate-300 uppercase tracking-wider">
                  {isEn ? 'Workspace Layout Version' : 'Phiên bản giao diện Workspace'}
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => onSelectGuiVersion('v2')}
                    className={`py-2 px-3 rounded-lg border text-xs font-bold flex items-center justify-center gap-1.5 transition ${
                      guiVersion === 'v2'
                        ? 'border-amber-500 bg-amber-500/10 text-amber-300'
                        : 'border-slate-800 bg-slate-900 text-slate-400 hover:bg-slate-800'
                    }`}
                  >
                    <span>V2 (Pro Modern)</span>
                    {guiVersion === 'v2' && <Check className="w-3.5 h-3.5" />}
                  </button>
                  <button
                    type="button"
                    onClick={() => onSelectGuiVersion('v1')}
                    className={`py-2 px-3 rounded-lg border text-xs font-bold flex items-center justify-center gap-1.5 transition ${
                      guiVersion === 'v1'
                        ? 'border-amber-500 bg-amber-500/10 text-amber-300'
                        : 'border-slate-800 bg-slate-900 text-slate-400 hover:bg-slate-800'
                    }`}
                  >
                    <span>V1 (Classic 3-Col)</span>
                    {guiVersion === 'v1' && <Check className="w-3.5 h-3.5" />}
                  </button>
                </div>
              </div>
            )}

            {/* Language Selection */}
            <div className="space-y-1.5 pt-2 border-t border-slate-800/80">
              <label className="block text-[11px] font-bold text-slate-300 uppercase tracking-wider">
                {isEn ? 'Interface Language' : 'Ngôn ngữ hiển thị'}
              </label>
              <div className="grid grid-cols-2 gap-1.5">
                {LANGUAGES.map((lang) => (
                  <button
                    key={lang.code}
                    type="button"
                    onClick={() => setLanguage(lang.code)}
                    className={`py-1.5 px-2 rounded-lg border text-xs flex items-center justify-between transition ${
                      language === lang.code
                        ? 'border-amber-500 bg-amber-500/10 text-amber-300 font-bold'
                        : 'border-slate-800 bg-slate-900 text-slate-400 hover:bg-slate-800'
                    }`}
                  >
                    <span>{lang.flag} {lang.label}</span>
                    {language === lang.code && <Check className="w-3 h-3" />}
                  </button>
                ))}
              </div>
            </div>

            {/* Access Security & Logout */}
            <div className="pt-3 border-t border-slate-800/80 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-xs font-bold text-slate-300">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                  <span>{t('auth_status_title')}</span>
                </div>
                <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                  PROTECTED
                </span>
              </div>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                {t('auth_status_desc')}
              </p>
              {onLogout && (
                <button
                  type="button"
                  onClick={onLogout}
                  className="w-full mt-1.5 py-2 px-3 bg-red-950/30 hover:bg-red-950/50 border border-red-500/30 hover:border-red-500/50 text-red-300 hover:text-red-200 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer"
                >
                  <Lock className="w-3.5 h-3.5 text-red-400" />
                  <span>{t('auth_logout')}</span>
                </button>
              )}
            </div>

            {/* Local Storage & Cache Reset */}
            <div className="pt-2 border-t border-slate-800/80">
              <button
                type="button"
                onClick={handleClearAppCache}
                className="w-full py-2 px-3 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-slate-200 rounded-lg text-xs flex items-center justify-center gap-1.5 transition"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>{clearedCache ? 'Đã xóa bộ nhớ tạm' : 'Xóa Local Storage & Cache'}</span>
              </button>
            </div>
          </div>

          {/* Developer Mode */}
          <div className="bg-slate-950/50 p-4 rounded-xl border border-slate-800/80 mt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-purple-500/10 rounded-lg">
                <Server className="w-5 h-5 text-purple-400" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-semibold text-slate-200">Developer Mode</h3>
                <p className="text-xs text-slate-400 mt-1 line-clamp-2">
                  {isEn ? 'Enable advanced system tools (Backtest, Forward Test, Multiscan, Models, Telemetry) in the workspace tabs.' : isZh ? '启用高级系统工具（回测、前向测试、多重扫描、模型、遥测）。' : isKo ? '작업 공간 탭에서 고급 시스템 도구(백테스트, 포워드 테스트, 다중 스캔, 모델, 원격 측정)를 활성화합니다.' : 'Hiển thị các công cụ hệ thống nâng cao (Backtest, Forward Test, Multiscan, Models, Telemetry) trên thanh tab làm việc.'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsDevMode?.(!isDevMode)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-slate-900 ${
                  isDevMode ? 'bg-purple-500' : 'bg-slate-700'
                }`}
                role="switch"
                aria-checked={isDevMode}
              >
                <span className="sr-only">Toggle Developer Mode</span>
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                    isDevMode ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
};
