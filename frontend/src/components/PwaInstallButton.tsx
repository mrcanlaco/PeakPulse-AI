import React, { useState, useEffect } from 'react';
import { Download, Smartphone, X, Share, PlusSquare, Check } from 'lucide-react';
import { useTranslation } from '../i18n/LanguageContext';
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

export const PwaInstallButton: React.FC<{ className?: string }> = ({ className = '' }) => {
  const { language } = useTranslation();
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isStandalone, setIsStandalone] = useState(false);
  const [isIos, setIsIos] = useState(false);
  const [showIosModal, setShowIosModal] = useState(false);
  const [installedSuccessfully, setInstalledSuccessfully] = useState(false);

  useEffect(() => {
    // Check if app is running in standalone mode (already installed PWA)
    const isStandaloneMode = window.matchMedia('(display-mode: standalone)').matches || (window.navigator as any).standalone === true;
    setIsStandalone(isStandaloneMode);

    // Detect iOS
    const userAgent = window.navigator.userAgent.toLowerCase();
    const isIosDevice = /iphone|ipad|ipod/.test(userAgent);
    setIsIos(isIosDevice);

    // Listen for beforeinstallprompt on Android / Chromium Desktop
    const handleBeforeInstallPrompt = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);

    // Listen for appinstalled
    window.addEventListener('appinstalled', () => {
      setDeferredPrompt(null);
      setIsStandalone(true);
      setInstalledSuccessfully(true);
      setTimeout(() => setInstalledSuccessfully(false), 4000);
    });

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
    };
  }, []);

  const handleInstallClick = async () => {
    if (isIos) {
      setShowIosModal(true);
      return;
    }

    if (deferredPrompt) {
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      if (outcome === 'accepted') {
        setDeferredPrompt(null);
        setInstalledSuccessfully(true);
      }
    } else {
      // Fallback instruction modal
      setShowIosModal(true);
    }
  };

  if (installedSuccessfully) {
    return (
      <span className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/40 bg-emerald-950/80 px-2.5 py-1.5 text-xs font-bold text-emerald-300 animate-in fade-in">
        <Check className="h-3.5 w-3.5 text-emerald-400" />
        <span>
          {language === 'en' ? 'Installed' : language === 'zh' ? '已安装' : language === 'ko' ? '설치됨' : 'Đã Cài Đặt'}
        </span>
      </span>
    );
  }

  // If already installed and running standalone, do not clutter header
  if (isStandalone) {
    return null;
  }

  return (
    <>
      <button
        type="button"
        onClick={handleInstallClick}
        className={`inline-flex items-center gap-1.5 rounded-lg border border-sky-500/40 bg-gradient-to-r from-sky-950/80 to-slate-900 px-2.5 py-1.5 text-xs font-bold text-sky-300 shadow-sm transition hover:border-sky-400 hover:bg-sky-900/50 active:scale-95 ${className}`}
        title={
          language === 'en'
            ? 'Install PWA App on mobile/desktop'
            : language === 'zh'
              ? '将 PWA 应用安装到手机/电脑'
              : language === 'ko'
                ? '모바일/데스크톱에 PWA 앱 설치'
                : 'Cài đặt App PWA lên điện thoại/máy tính'
        }
      >
        <Download className="h-3.5 w-3.5 text-sky-400 stroke-[2.5]" />
        <span className="hidden sm:inline">
          {language === 'en' ? 'Install PWA' : language === 'zh' ? '安装应用' : language === 'ko' ? '앱 설치' : 'Cài App PWA'}
        </span>
        <span className="sm:hidden">App</span>
      </button>

      {/* iOS & Manual Installation Instruction Modal */}
      {showIosModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-sm animate-in fade-in">
          <div className="w-full max-w-sm rounded-2xl border border-slate-700 bg-slate-900 p-5 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500/20 border border-amber-500/40 text-amber-400">
                  <Smartphone className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-100">Cài Đặt Đảo Vàng PWA</h3>
                  <p className="text-[11px] text-slate-400">Trải nghiệm như ứng dụng Native</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowIosModal(false)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs text-slate-300">
              <div className="flex items-start gap-3 rounded-xl bg-slate-950/70 p-3 border border-slate-800">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-sky-500/20 text-sky-400 font-bold text-xs">
                  1
                </div>
                <div>
                  <span className="font-semibold text-slate-200 block mb-0.5">Mở menu trình duyệt:</span>
                  <span className="text-[11px] text-slate-400 flex items-center gap-1">
                    Bấm biểu tượng <Share className="h-3.5 w-3.5 text-sky-400 inline" /> (Share trên Safari) hoặc <b>⋮</b> (Chrome).
                  </span>
                </div>
              </div>

              <div className="flex items-start gap-3 rounded-xl bg-slate-950/70 p-3 border border-slate-800">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-400 font-bold text-xs">
                  2
                </div>
                <div>
                  <span className="font-semibold text-slate-200 block mb-0.5">Thêm vào Màn hình chính:</span>
                  <span className="text-[11px] text-slate-400 flex items-center gap-1">
                    Chọn <PlusSquare className="h-3.5 w-3.5 text-emerald-400 inline" /> <b>"Thêm vào MH chính"</b> (Add to Home Screen).
                  </span>
                </div>
              </div>

              <div className="flex items-start gap-3 rounded-xl bg-slate-950/70 p-3 border border-slate-800">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-amber-500/20 text-amber-400 font-bold text-xs">
                  3
                </div>
                <div>
                  <span className="font-semibold text-slate-200 block mb-0.5">Trải nghiệm mượt mà:</span>
                  <span className="text-[11px] text-slate-400">
                    Mở app từ Màn hình chính với tốc độ siêu tốc, không bị che bởi thanh địa chỉ.
                  </span>
                </div>
              </div>
            </div>

            <button
              type="button"
              onClick={() => setShowIosModal(false)}
              className="w-full rounded-xl bg-amber-500 py-2 text-center text-xs font-black text-slate-950 hover:bg-amber-400 transition shadow-md shadow-amber-500/20"
            >
              Đã hiểu
            </button>
          </div>
        </div>
      )}
    </>
  );
};
