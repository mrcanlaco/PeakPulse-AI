# Task List: Full Application Localization (i18n)

## Phase 1: Foundation (Dictionary)
- [ ] **Task 1: Expand `translations.ts` dictionary**
  - [ ] Add comprehensive UI keys for all tabs, workspace metrics, deep-dive views, and chart overlays.
  - [ ] Add glossary terms, watchlist actions, tracking statuses, and guide content in `vi` and `en`.
  - [ ] Ensure strict TypeScript type alignment (`TranslationKey`).

## Phase 2: Core Shell & Navigation
- [ ] **Task 2.1: Localize `Header.tsx` and `App.tsx`**
  - [ ] Localize search placeholder, quick filter pills, main navigation tabs, status toasts, and error states.
- [ ] **Task 2.2: Localize `ActionDrawer.tsx`**
  - [ ] Localize automation settings, audio alerts toggle, Telegram test push, and threshold sliders.

## Phase 3: Live Radar & Main Workspace
- [ ] **Task 3.1: Localize `SignalFeed.tsx`**
  - [ ] Localize table columns, sort dropdown, signal badges (`CONFIRMED`, `EARLY WATCH`, `INVALIDATED`), and action buttons.
- [ ] **Task 3.2: Localize `MainWorkspace.tsx` and `CandlestickChart.tsx`**
  - [ ] Localize chart headers, timeframe toggles, metric cards (OI 24h, Funding, Taker Sell, RSI, Target -8%), deep-dive tabs, and technical indicator panels.

## Phase 4: Modals & Tracking
- [ ] **Task 4.1: Localize `GlossaryModal.tsx`**
  - [ ] Complete bilingual definitions for all quant finance & ML terms.
- [ ] **Task 4.2: Localize `WatchlistModal.tsx` and `TrackingWatchlist.tsx`**
  - [ ] Localize watchlist modal controls and PnL tracking progress metrics.

## Phase 5: Deep Analytics & Guides
- [ ] **Task 5.1: Localize `SystemHistoryTab.tsx` and `MultiCoinScan.tsx`**
  - [ ] Localize audit log filters, telemetry cards, and multi-timeframe matrix headers.
- [ ] **Task 5.2: Localize `BacktestExperiments.tsx`, `ForwardTest.tsx`, and `GuideTab.tsx`**
  - [ ] Localize backtest fold summaries, calibration charts, and user trading guide.

## Phase 6: Quality Gate & Build
- [ ] **Task 6: Full Verification**
  - [ ] Run `npm run build` (`tsc -b && vite build`) to ensure 0 type errors.
  - [ ] Test language toggle between VI and EN.
  - [ ] Commit and push to Git.
