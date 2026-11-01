# Implementation Plan: Full Frontend i18n & Seamless Multilingual Toggle

## Overview
Translate and localize all user-facing strings across the entire DAO VANG Web Dashboard so that toggling between Vietnamese (`vi`) and English (`en`) seamlessly translates 100% of the UI (Navigation, Signal Feed, Main Workspace, Candlestick Chart, Action Drawer, Glossary, Watchlist, Tracking PnL, System History, Backtest Experiments, and User Guides).

---

## Architecture Decisions
1. **Centralized Strongly-Typed Translation Dictionary (`frontend/src/i18n/translations.ts`):**
   - Extend `translations.ts` with comprehensive nested or categorized key-value pairs for all components.
   - Use TypeScript `TranslationKey` to ensure build-time safety and prevent missing translation keys.
2. **React Context & Custom Hook (`useTranslation()`):**
   - Use `const { t, language, setLanguage } = useTranslation();` across all components.
   - Preserve language selection across page reloads via `localStorage.getItem('dao_vang_lang')` with fallback to browser language.
3. **Point-in-Time & Numerical Formatting:**
   - Numerical values, percentages, and currencies remain uniform (e.g. `+12.4%`, `$0.04523`), while date/time labels adapt to the selected locale (`vi` or `en`).

---

## Task List & Dependency Graph

```
Phase 1: Translation Dictionary Expansion (Foundation)
    │
    ├── Phase 2: Core Shell & Navigation Localization (App.tsx, Header.tsx, ActionDrawer.tsx)
    │       │
    │       ├── Phase 3: Live Radar & Main Workspace (SignalFeed.tsx, MainWorkspace.tsx, CandlestickChart.tsx)
    │       │
    │       ├── Phase 4: Modals & Drawers (GlossaryModal.tsx, WatchlistModal.tsx, TrackingWatchlist.tsx)
    │       │
    │       └── Phase 5: Deep Analytics & Audit Tabs (SystemHistoryTab.tsx, BacktestExperiments.tsx, ForwardTest.tsx, MultiCoinScan.tsx, GuideTab.tsx)
    │
    └── Phase 6: Build Verification & End-to-End Visual Audit
```

---

### Phase 1: Foundation — Translation Dictionary Expansion
- **Task 1: Comprehensive i18n Dictionary Expansion**
  - **Description:** Populate `translations.ts` with complete Vietnamese and English dictionaries covering all UI components, badges, table columns, tooltips, modal contents, and glossary terms.
  - **Files:** `frontend/src/i18n/translations.ts`
  - **Verification:** `npm run build` passes with zero type errors on `TranslationKey`.

---

### Phase 2: Core Shell & Navigation Localization
- **Task 2: Localize App.tsx, Header.tsx, and ActionDrawer.tsx**
  - **Description:** Replace hardcoded Vietnamese strings in root tabs, search bar placeholder, drawer settings, audio alerts, and quick actions with `t(...)`.
  - **Files:** `frontend/src/App.tsx`, `frontend/src/components/Header.tsx`, `frontend/src/components/ActionDrawer.tsx`
  - **Verification:** Verify header controls, tab switches, and action drawer controls toggle cleanly between VI and EN.

---

### Phase 3: Live Radar & Main Workspace Localization
- **Task 3: Localize SignalFeed.tsx, MainWorkspace.tsx, and CandlestickChart.tsx**
  - **Description:** Localize signal feed cards, badges (`CONFIRMED`, `EARLY WATCH`, `INVALIDATED`), action buttons, metrics bar (OI 24h, Funding, Taker Sell, RSI, Target -8%), chart timeframe headers, and technical indicator panels.
  - **Files:** `frontend/src/components/SignalFeed.tsx`, `frontend/src/components/MainWorkspace.tsx`, `frontend/src/components/CandlestickChart.tsx`
  - **Verification:** Verify signal list, candlestick chart overlays, and deep dive tabs render in selected language.

---

### Phase 4: Modals & Tracking Localization
- **Task 4: Localize GlossaryModal.tsx, WatchlistModal.tsx, and TrackingWatchlist.tsx**
  - **Description:** Localize indicator definitions, glossary entries, watchlist management actions, and PnL tracking progress tables.
  - **Files:** `frontend/src/components/GlossaryModal.tsx`, `frontend/src/components/WatchlistModal.tsx`, `frontend/src/components/TrackingWatchlist.tsx`
  - **Verification:** Open each modal and toggle language to verify instant text update.

---

### Phase 5: Deep Analytics, Backtest & Guide Tabs Localization
- **Task 5: Localize SystemHistoryTab.tsx, BacktestExperiments.tsx, ForwardTest.tsx, MultiCoinScan.tsx, and GuideTab.tsx**
  - **Description:** Localize audit logs, walk-forward fold tables, shadow test confusion matrix, multi-timeframe matrix, and user trading guide.
  - **Files:** `frontend/src/components/SystemHistoryTab.tsx`, `frontend/src/components/BacktestExperiments.tsx`, `frontend/src/components/ForwardTest.tsx`, `frontend/src/components/MultiCoinScan.tsx`, `frontend/src/components/GuideTab.tsx`
  - **Verification:** Check each tab in both languages.

---

### Phase 6: Quality Gate & Production Build
- **Task 6: Verification and Automated Build Check**
  - **Description:** Execute `tsc -b` and `npm run build` in `frontend/`, verify clean bundle output, and commit to Git.
  - **Verification:** `npm run build` succeeds with 0 errors.

---

## Risks and Mitigations
| Risk | Impact | Mitigation |
|---|---|---|
| Missing translation key causing blank UI or fallback glitch | Medium | TypeScript strict type checking on `TranslationKey` ensures all keys exist in both `vi` and `en`. |
| Text length difference causing layout breaks | Low | Use responsive flex/grid wrappers and Tailwind `truncate` / `flex-wrap` where applicable. |
| Performance overhead on language toggle | Low | React Context state change triggers fast re-render with zero network requests (client-side dictionary). |
