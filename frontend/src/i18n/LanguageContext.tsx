import React, { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import { translations, type Language, type TranslationKey } from './translations';

export type { Language, TranslationKey } from './translations';

export interface LanguageOption {
  code: Language;
  label: string;
  nativeLabel: string;
  flag: string;
}

export const LANGUAGES: LanguageOption[] = [
  { code: 'vi', label: 'Tiếng Việt', nativeLabel: 'Tiếng Việt', flag: '🇻🇳' },
  { code: 'en', label: 'English', nativeLabel: 'English', flag: '🇬🇧' },
  { code: 'zh', label: 'Chinese', nativeLabel: '简体中文', flag: '🇨🇳' },
  { code: 'ko', label: 'Korean', nativeLabel: '한국어', flag: '🇰🇷' },
];

interface LanguageContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  toggleLanguage: () => void;
  t: (key: TranslationKey | (string & {}), fallback?: string) => string;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

const STORAGE_KEY = 'dao_vang_app_language';

export const LanguageProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [language, setLanguageState] = useState<Language>(() => {
    const saved = localStorage.getItem(STORAGE_KEY) as Language | null;
    if (saved && (saved === 'en' || saved === 'vi' || saved === 'zh' || saved === 'ko')) {
      return saved;
    }
    return 'vi';
  });

  const setLanguage = (lang: Language) => {
    setLanguageState(lang);
    localStorage.setItem(STORAGE_KEY, lang);
  };

  const toggleLanguage = () => {
    const order: Language[] = ['vi', 'en', 'zh', 'ko'];
    const currentIndex = order.indexOf(language);
    const nextIndex = (currentIndex + 1) % order.length;
    setLanguage(order[nextIndex]);
  };

  useEffect(() => {
    document.documentElement.lang = language;
    if (typeof window === 'undefined' || typeof document === 'undefined') return undefined;
    let cancelled = false;
    let observer: MutationObserver | null = null;
    let rafId: number | null = null;

    void import('./domLocalizer').then(({ applyDomLocalization }) => {
      if (cancelled) return;
      applyDomLocalization(document.body, language);
      if (language !== 'vi') {
        observer = new MutationObserver(() => {
          if (rafId !== null) return;
          rafId = window.requestAnimationFrame(() => {
            rafId = null;
            if (!cancelled) applyDomLocalization(document.body, language);
          });
        });
        observer.observe(document.body, {
          childList: true,
          subtree: true,
        });
      }
    });

    return () => {
      cancelled = true;
      if (rafId !== null) window.cancelAnimationFrame(rafId);
      observer?.disconnect();
    };
  }, [language]);

  const t = (key: TranslationKey | (string & {}), fallback?: string): string => {
    const langDict = (translations[language] || translations.vi) as Record<string, string>;
    if (key in langDict) {
      return langDict[key];
    }
    const viDict = translations.vi as Record<string, string>;
    if (key in viDict) {
      return viDict[key];
    }
    const enDict = translations.en as Record<string, string>;
    if (key in enDict) {
      return enDict[key];
    }
    return fallback ?? key;
  };

  return (
    <LanguageContext.Provider value={{ language, setLanguage, toggleLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  );
};

export const useTranslation = () => {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useTranslation must be used within a LanguageProvider');
  }
  return context;
};
