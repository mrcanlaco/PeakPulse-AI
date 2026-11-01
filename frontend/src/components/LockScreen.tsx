import React, { useState, useRef, useEffect } from 'react';
import {
  Lock,
  KeyRound,
  ShieldCheck,
  Eye,
  EyeOff,
  Sparkles,
  AlertCircle,
  ArrowRight,
  ShieldAlert,
  Loader2,
  CheckCircle2,
  Globe,
  X,
} from 'lucide-react';
import { useTranslation, LANGUAGES, type LanguageOption } from '../i18n/LanguageContext';
import { verifyPassword } from '../utils/auth';

interface LockScreenProps {
  onAuthenticated: () => void;
  initialError?: string | null;
  onClose?: () => void;
  reasonMessage?: string | null;
}

export const LockScreen: React.FC<LockScreenProps> = ({
  onAuthenticated,
  initialError = null,
  onClose,
  reasonMessage = null,
}) => {
  const { language, setLanguage, t } = useTranslation();
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(initialError);
  const [isSuccess, setIsSuccess] = useState(false);
  const [isLangOpen, setIsLangOpen] = useState(false);
  const langRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    if (initialError) {
      setError(initialError);
    }
  }, [initialError]);

  useEffect(() => {
    if (!onClose) return undefined;
    const handleEsc = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (langRef.current && !langRef.current.contains(event.target as Node)) {
        setIsLangOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!password.trim() || isLoading) return;

    setIsLoading(true);
    setError(null);

    const result = await verifyPassword(password.trim());
    setIsLoading(false);

    if (result.ok) {
      setIsSuccess(true);
      setTimeout(() => {
        onAuthenticated();
      }, 400);
    } else {
      setError(result.error || t('auth_wrong_password'));
      inputRef.current?.select();
    }
  };

  return (
    <div
      data-testid="admin-login-modal"
      onClick={() => onClose?.()}
      className={`fixed inset-0 z-[9999] flex flex-col items-center justify-center text-slate-100 overflow-hidden select-none px-4 ${
        onClose ? 'bg-slate-950/80 backdrop-blur-md' : 'bg-[#07090E]'
      }`}
    >
      {/* Background ambient lighting */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-amber-500/10 rounded-full blur-[140px] pointer-events-none" />
      <div className="absolute bottom-10 left-1/3 w-[400px] h-[400px] bg-emerald-500/5 rounded-full blur-[120px] pointer-events-none" />

      {/* Language Selector in Top Right */}
      <div className="absolute top-4 right-4 z-50" ref={langRef}>
        <button
          type="button"
          onClick={() => setIsLangOpen(!isLangOpen)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900/80 border border-slate-800 hover:border-amber-500/40 text-xs text-slate-300 hover:text-amber-400 transition-all backdrop-blur-md cursor-pointer"
        >
          <Globe className="w-3.5 h-3.5 text-amber-400" />
          <span>{LANGUAGES.find((l) => l.code === language)?.label || 'Tiếng Việt'}</span>
        </button>

        {isLangOpen && (
          <div className="absolute right-0 mt-1.5 w-40 rounded-xl bg-slate-900/95 border border-slate-800 shadow-2xl py-1 backdrop-blur-xl z-50 animate-in fade-in zoom-in-95 duration-150">
            {LANGUAGES.map((l: LanguageOption) => (
              <button
                key={l.code}
                type="button"
                onClick={() => {
                  setLanguage(l.code);
                  setIsLangOpen(false);
                }}
                className={`w-full text-left px-3 py-2 text-xs flex items-center justify-between hover:bg-slate-800/70 transition-colors cursor-pointer ${
                  language === l.code ? 'text-amber-400 font-semibold bg-amber-500/10' : 'text-slate-300'
                }`}
              >
                <span>{l.label}</span>
                {language === l.code && <CheckCircle2 className="w-3.5 h-3.5 text-amber-400" />}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Main Card */}
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md relative z-10 animate-in fade-in zoom-in-95 duration-300"
      >
        <div className="relative rounded-2xl bg-slate-900/95 border border-amber-500/30 p-7 sm:p-8 shadow-[0_0_50px_-12px_rgba(245,158,11,0.25)] backdrop-blur-2xl">
          {onClose && (
            <button
              type="button"
              data-testid="admin-login-close"
              onClick={onClose}
              aria-label="Close Admin Login"
              className="absolute right-4 top-4 inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-700/80 bg-slate-800/80 text-slate-400 hover:border-slate-600 hover:text-white transition cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          )}
          <div className="text-center mb-6">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-amber-500/20 via-slate-800 to-amber-950/40 border border-amber-500/40 shadow-inner mb-4">
              <Lock className="w-8 h-8 text-amber-400 animate-pulse" />
            </div>

            <div className="flex items-center justify-center gap-1.5 text-xs font-semibold text-amber-400 tracking-wider uppercase mb-1">
              <Sparkles className="w-3.5 h-3.5" />
              <span>ĐẢO VÀNG AI RADAR</span>
            </div>

            <h1 className="text-xl sm:text-2xl font-black tracking-tight text-white">
              {t('auth_screen_title')}
            </h1>

            <p className="text-xs text-slate-400 mt-2 leading-relaxed max-w-xs mx-auto">
              {t('auth_screen_subtitle')}
            </p>
          </div>
          {reasonMessage && (
            <div className="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3.5 py-2.5 text-xs text-amber-200 leading-relaxed">
              {reasonMessage}
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5 flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <KeyRound className="w-3.5 h-3.5 text-amber-400" />
                  {t('auth_password_label')}
                </span>
                <span className="text-[10px] text-slate-500">{t('auth_password_hint')}</span>
              </label>

              <div className="relative">
                <input
                  data-testid="login-password"
                  ref={inputRef}
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    if (error) setError(null);
                  }}
                  placeholder={t('auth_password_placeholder')}
                  disabled={isLoading || isSuccess}
                  autoComplete="current-password"
                  className={`w-full px-4 py-3 pr-11 rounded-xl bg-slate-950/90 border text-sm text-white placeholder-slate-500 focus:outline-none transition-all ${
                    error
                      ? 'border-red-500/80 focus:border-red-500 focus:ring-1 focus:ring-red-500/50'
                      : 'border-slate-700/80 focus:border-amber-500 focus:ring-1 focus:ring-amber-500/50 hover:border-slate-600'
                  }`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  tabIndex={-1}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 transition-colors p-1 cursor-pointer"
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>

            {/* Error Message */}
            {error && (
              <div className="flex items-start gap-2 p-3 rounded-xl bg-red-950/40 border border-red-500/30 text-red-300 text-xs animate-in fade-in duration-200">
                <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                <span className="leading-snug">{error}</span>
              </div>
            )}

            {/* Submit Button */}
            <button
              data-testid="login-submit"
              type="submit"
              disabled={!password.trim() || isLoading || isSuccess}
              className={`w-full py-3 px-4 rounded-xl font-bold text-sm tracking-wide transition-all flex items-center justify-center gap-2 shadow-lg cursor-pointer ${
                isSuccess
                  ? 'bg-emerald-600 text-white shadow-emerald-500/30'
                  : password.trim() && !isLoading
                  ? 'bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 shadow-amber-500/25 hover:shadow-amber-500/40 active:scale-[0.99]'
                  : 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700/50'
              }`}
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>{t('auth_verifying')}</span>
                </>
              ) : isSuccess ? (
                <>
                  <CheckCircle2 className="w-4 h-4" />
                  <span>{t('auth_success')}</span>
                </>
              ) : (
                <>
                  <span>{t('auth_unlock_button')}</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="mt-3 w-full rounded-xl border border-slate-700/80 bg-slate-800/60 py-2.5 px-4 text-xs font-semibold text-slate-300 hover:bg-slate-800 hover:text-white transition cursor-pointer"
            >
              {language === 'en'
                ? 'Continue browsing as Guest (Read-Only)'
                : language === 'zh'
                  ? '继续以访客模式浏览（只读）'
                  : language === 'ko'
                    ? '게스트 모드로 계속 보기 (읽기 전용)'
                    : 'Tiếp tục xem chế độ Khách (Read-Only)'}
            </button>
          )}

          {/* Security Features Badge / Explanation */}
          <div className="mt-6 pt-5 border-t border-slate-800/80">
            <div className="flex items-start gap-2.5 text-[11px] text-slate-400">
              <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              <span>{t('auth_remember_note')}</span>
            </div>
            <div className="flex items-start gap-2.5 text-[11px] text-slate-500 mt-2">
              <ShieldAlert className="w-4 h-4 text-amber-500/70 shrink-0 mt-0.5" />
              <span>{t('auth_quota_protection_note')}</span>
            </div>
          </div>
        </div>

        {/* Footer info */}
        <div className="text-center mt-4 text-[11px] text-slate-500">
          Đảo Vàng AI Radar © 2026 • Hệ thống phân tích định lượng
        </div>
      </div>
    </div>
  );
};
