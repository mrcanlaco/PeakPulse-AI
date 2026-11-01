# 🏛️ DAO VANG (PeakPulse AI) — System Architecture

Welcome to the **DAO VANG (PeakPulse AI)** architectural documentation. This document provides an end-to-end technical overview of how the system ingests data, engineers features, calibrates predictive models, scans live cryptocurrency futures, and delivers signals to users.

---

## 🧭 1. Core Architectural Tenets

1. **Point-in-Time Safeguards:**
   - Feature calculations and inference are designed to consume only information available at or before each candle timestamp $t$.
   - Time-series joins use DuckDB `as-of` matching, while leakage audits and regression tests protect this contract. These controls reduce risk; they are not an absolute guarantee for every future data source or model revision.
2. **Deterministic Data & Query Engine:**
   - Powered by **DuckDB** and **Apache Parquet** for reproducible columnar storage and queries. Throughput depends on dataset size, hardware, and query shape and must be measured for each release environment.
3. **Frozen Model Bundles & Out-of-fold Calibration:**
   - Inference models are versioned and serialized with checksums. Calibration artifacts and metrics are attached to a specific bundle; no calibration threshold is claimed unless a version-linked evaluation report supports it.
4. **Human-in-the-Loop (Analytical Radar, No Auto-Trading):**
   - The platform serves as an early-warning signal radar. It does not execute automatic market orders.

5. **Two-Tier Production Signal Architecture (`V3.1 Radar` + `Fibo Short v4.0.21`):**
   - **Tier 1 (Early Overheating Radar — UI Only):** The Frozen LightGBM V3.1 model + `DistributionScorer` scans 5m derivatives data to surface overheated pumps and funding exhaustion on the `RADAR` / `WATCHLIST` tabs (`shadow_telegram_enabled: false`).
   - **Tier 2 (Primary Actionable Signal Engine — Telegram & `FIBO_SHORT` Tab):** `dao_vang.fibo_short` (`v4.0.21`) evaluates closed `H4/D1 -> H1` structural reversals across the monthly `rolling_pit_top50` universe and dispatches official Telegram setups (`elite_sniper_risk` and `sniper_rr1_horizon24`) with hard structural stop-loss (`Fibo 0.886`), 3-stage ratcheted exits, and `0.5% NAV` risk sizing. See [`docs/PRODUCTION_DEPLOYMENT_GUIDE.md`](PRODUCTION_DEPLOYMENT_GUIDE.md).
---

## 🔄 2. End-to-End Dataflow & Pipeline

```mermaid
flowchart TD
    subgraph DataIngestion["1. Data Ingestion & Storage"]
        BinanceAPI["Binance USD-M Futures REST"]
        Collectors["Data Collectors (Klines, OI, Funding, Taker, Ratios)"]
        DuckDBStorage[("DuckDB & Parquet Storage")]
        BinanceAPI --> Collectors --> DuckDBStorage
    end

    subgraph FeatureLabel["2. Features & Ground Truth"]
        DuckDBStorage --> FeatureRegistry["Feature Registry & Builders"]
        DuckDBStorage --> LabelEngine["Label Engine (Distribution 8% drop / MAE <= 4%)"]
        FeatureRegistry --> FeatureMatrix["Point-in-Time Feature Matrix"]
    end

    subgraph MLValidation["3. ML Training & Validation"]
        FeatureMatrix --> WFValidation["Walk-Forward Splitter & Leakage Audits"]
        LabelEngine --> WFValidation
        WFValidation --> ModelTraining["Model Training & Versioned Calibration"]
        ModelTraining --> FrozenBundle[("Frozen Model Bundle")]
    end

    subgraph LiveDaemon["4. 24/7 Live Scanner Daemon"]
        LiveScan["Live 5m Cycle Scanner"]
        CandFilter["Candidate Filter v2 & Pump Filter"]
        Scorer["Distribution Scorer & BTC Context Scorer"]
        AnomalyRadar["Independent Market Anomaly Radar"]
        OutcomeTracker["PnL & Empirical Precision Tracker"]
        
        LiveScan --> CandFilter
        CandFilter --> Scorer
        CandFilter --> AnomalyRadar
        FrozenBundle -.-> Scorer
        Scorer --> OutcomeTracker
    end

    subgraph Delivery["5. Signal Delivery & UI"]
        Scorer -->|Configured serving gate passed| TelegramBot["Telegram Alert Bot (VI/EN)"]
        Scorer --> HttpServer["ThreadingHTTPServer REST API"]
        AnomalyRadar --> HttpServer
        HttpServer --> ReactUI["React 19 + TypeScript + Vite Web Dashboard"]
    end
```

---

## 📂 3. Source Code Organization (`src/dao_vang/`)

The backend follows a **Modular Monolith** pattern organized cleanly by domain and functionality:

| Module Directory | Responsibility | Key Classes / Entrypoints |
| :--- | :--- | :--- |
| [`domain/`](../src/dao_vang/domain/) | Core domain types, enumerations, error definitions, and timezone-aware datetime helpers. | `DistributionEvent`, `MarketRegime`, `AppError` |
| [`config/`](../src/dao_vang/config/) | Pydantic v2 settings loading from `.env` and `configs/live.yaml`. | `AppSettings`, `get_settings()` |
| [`logging/`](../src/dao_vang/logging/) | Structured JSON/Console logging with automated sensitive secret redaction. | `get_logger()`, `redact_secrets()` |
| [`data/`](../src/dao_vang/data/) | Ingestion clients (Binance USD-M, Binance Agent OS token data, optional CoinGecko price cross-reference), schemas, data quality validation, and DuckDB storage. | `BinanceClient`, `KlinesCollector`, `DuckDBStorage` |
| [`features/`](../src/dao_vang/features/) | Point-in-time feature builders for Price, Open Interest, Funding Rate, Taker Volume, and Top Trader Ratios. | `FeatureRegistry`, `PriceFeatureBuilder`, `OIFeatureBuilder` |
| [`labels/`](../src/dao_vang/labels/) | Ground-truth labeling engine (identifying distribution tops: $\ge 8\%$ drop within 6-24h, MAE $\le 4\%$). | `LabelEngineV1`, `DistributionShortSpec` |
| [`baselines/`](../src/dao_vang/baselines/) | Rule-based heuristics and logistic regression baseline models for performance comparison. | `RuleBasedBaseline`, `LogisticBaseline` |
| [`validation/`](../src/dao_vang/validation/) | Walk-forward validation, embargo splitting, data leakage audits, and Brier / ECE calibration metrics. | `WalkForwardSplitter`, `LeakageAuditor`, `CalibrationMetrics` |
| [`experiments/`](../src/dao_vang/experiments/) | ML training runner, forward testing, ablation studies, and automated self-learning feedback loops. | `ExperimentRunner`, `SelfLearningDaemon` |
| [`scoring/`](../src/dao_vang/scoring/) | Live scoring engine combining frozen-model probabilities, BTC context, and evidence explanations. | `DistributionScorer`, `BTCContextScorer`, `EvidenceGenerator` |
| [`scanner/`](../src/dao_vang/scanner/) | 24/7 background scanner daemon, pump pattern detector, independent Market Anomaly Radar, Candidate Filter v2, watchlist manager, and signal outcome tracking. | `ScannerDaemon`, `PumpFilter`, `MarketAnomaly`, `TrackingWatchlist`, `CandidateFilterV2` |
| [`alerts/`](../src/dao_vang/alerts/) | Telegram alert delivery manager, bilingual message formatting (Vietnamese/English), and alert dedup store. | `TelegramAlertManager`, `AlertStore` |
| [`fibo_short/`](../src/dao_vang/fibo_short/) | Official primary actionable short-signal engine (`v4.0.21`): 4-factor `H4/D1 -> H1` Fibonacci structural reversal detector, closed-candle cache, rolling PIT Top-50 universe loader, parallel shadow comparison store, and Telegram dispatcher. | `evaluate_symbol_timeframe()`, `run_cycle()`, `FiboStateStore` |
| [`execution/`](../src/dao_vang/execution/) | Isolated execution, paper simulation, account read-only monitor, and snapshot archiving engine (fail-closed `live_activated: false` in production). | `ExecutionEngine`, `PaperBroker`, `AccountMonitor` |
| [`alpha_lab/`](../src/dao_vang/alpha_lab/) | Research modules for Triple Barrier evaluation, optional Meta-Labeling, Market Regime classification, and Drift Guardian. A module's presence does not mean it is enabled in live serving. | `AlphaBacktester`, `DriftGuardian`, `RegimeClassifier` |
| [`reports/`](../src/dao_vang/reports/) | HTML / Markdown summary report generator for backtest benchmarks and live operational audits. | `ReportGenerator` |
| [`web/`](../src/dao_vang/web/) | Custom threaded HTTP server providing REST endpoints and static frontend files. | `api_server.py`, `run.py` |
| [`cli/`](../src/dao_vang/cli/) | Typer CLI commands for manual data collection, backtesting, scanning, and model training. | `main.py` (`dao-vang`) |

---

## 💻 4. Frontend Architecture (`frontend/`)

The Web Dashboard is built with **React 19 + TypeScript + Vite**:

- **`src/components/MainWorkspace.tsx`**: Main trading cockpit containing interactive candlestick charts, live metrics (OI 24h, Funding, Taker Sell %, RSI), risk ratings, and deep analysis accordion.
- **`src/components/Sidebar.tsx`**: Navigation menu for Dashboard, Live Scanner, Signals Feed, Watchlist, Alpha Lab, and System Settings.
- **`src/components/SignalFeed.tsx`**: Polling-refreshed signal stream with hit/miss outcome badges, lead-time stats, and quick filtering.
- **`src/components/WatchlistPanel.tsx`**: Polling-refreshed watchlist tracking symbols under accumulation/distribution observation.
- **`src/components/AlphaLab.tsx`**: Visual research workbench for running Triple Barrier backtests, regime audits, and model feature-importance analysis.

---

## 🗄️ 5. Storage & Database Schema

DAO VANG utilizes a dual storage strategy:
1. **DuckDB Database (`dev.duckdb` / `live.duckdb`):**
   - Tables: `kline`, `open_interest`, `funding_rate`, `taker_ratio`, `top_position_ratio`, `scan_results`, `tracked_signals`, `alerts_sent`.
2. **Apache Parquet Files (`data/` / `data_live/`):**
   - Partitioned by `symbol/year/month` for high-throughput immutable historical storage.

---

## 🛡️ 6. Security & Operational Isolation

- **Separate Data Environments:** Development and production paths are configured independently. The current container stack mounts production data at `/app/data_live` and exposes the web service on port `8000`.
- **Credential Protection:** All tokens (Telegram API keys, webhooks) are loaded via environment variables and sanitized in all log outputs by `redact_secrets`.
- **Runtime Isolation:** The production containers run as a non-root UID/GID, expose liveness/readiness checks, and disable in-app self-updates. Releases are applied through the CI/CD pipeline.
