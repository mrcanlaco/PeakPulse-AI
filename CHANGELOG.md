# Changelog

All notable changes to the Đảo Vàng project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — Footer FreqPilot cho cảnh báo Telegram
- Thêm liên kết FreqPilot có UTM riêng cho cảnh báo phân phối, cảnh báo chấm điểm, tổng hợp radar và tín hiệu hai tầng `FIRED`; không thay đổi điều kiện gửi tín hiệu.
- Footer mặc định bật; đặt biến môi trường `FREQPILOT_UTM_FOOTER=0` để tắt. Cấu hình Telegram hiện vẫn chỉ nhận `vi`/`en`; hàm tạo footer có thêm bản dịch `zh`/`ko`.


### Fixed — Fibo Short v4.0.21 Downtrend Telegram Qualification & Monthly Paper OOS Rollover
- **Downtrend Sniper Telegram Qualification (`src/dao_vang/fibo_short/scanner_lane.py`, `src/dao_vang/config/settings.py`, `configs/live.yaml`, `configs/dev.yaml`)**:
  - Aligned `telegram_min_prior_pump_pct` (`0.05`) with `detector.py` `min_prior_pump_pct` (`0.05`) and restored all 4 Sniper policies (`elite_sniper_risk`, `sniper_rr1_horizon24`, `sniper_risk`, `sniper_horizon24`) so valid 4-Factor Sniper Short setups during market-wide downtrends (+8% to +29% lower-high bounces followed by >=6% impulse drops with `Impulse KER >= 0.50` and H1 structure break) are no longer suppressed as `unqualified_short`.
  - Updated `FiboStateStore.is_already_fired` so waves that initially triggered as `watch_only` (`telegram_sent == 0`) dispatch to Telegram when a subsequent H1 candle upgrades them to a qualified Sniper policy, while keeping original fired `entry_price`/`stop_loss`/`tp1..3`/`signal_time` and `outcome` strictly immutable in the shadow comparison ledger.
- **Paper OOS Monthly Universe Rollover (`scripts/fibo_research/run_paper_oos_daemon.py`)**:
  - Added graceful fallback when `OBSERVED_VIEWS.json` is absent on Linux servers so newly admitted monthly PIT Top-50 symbols (`QNTUSDT`, `AEROUSDT` in `2026-11`) warm up directly from Binance 1H klines without blocking `signal_decision` deadlines.

### Changed — Public Guest Read-Only Access & Admin Privilege Gate (`https://pulse.freqpilot.dev`)
- **2-Role Access Model (`src/dao_vang/web/api_server.py`, `frontend/src/App.tsx`, `LockScreen.tsx`, `Header.tsx`, `MainWorkspace.tsx`, `ExecutionDashboard.tsx`, `FloatingAiAssistant.tsx`)**:
  - **Public Guest (No Login Required):** Immediate read-only access to all 4 workspace pillars (`Fibo Short v4.0.21`, `Biểu đồ & Lệnh`, `Shadow Live 12 Paper OOS`, `Live Paper 10,000 USD & Binance Account Read-Only`, `Phương pháp & Kiểm toán 6 năm`, `Phiên bản & Hạ tầng`), deep-link support (`#coin=SYMBOL`), 15-second thread-safe kline response caching, and browser-local personal watchlist (`localStorage` `dao_vang_guest_tracking_watchlist_v1`) with client-side paper trade simulation.
  - **Administrator (`🔑 Admin` inline modal + signed `HttpOnly` session cookie):** Required only for AI Quant Assistant / LLM queries (`/api/ai/*`), System Configuration (`Cài đặt Hệ thống`), manual scan/watchlist mutations, Telegram dispatches, server-persisted tracking ledger, and Live execution controls (`Dừng / Bật lại / Đóng thủ công`).
### Changed — Official 2-Tier Production Deployment (`Fibo Short v4.0.21` + `V3.1 UI Radar`)
- **2-Tier Production Signal Routing (`configs/live.yaml`, `configs/dev.yaml`, `docs/PRODUCTION_DEPLOYMENT_GUIDE.md`)**:
  - Promoted **`Fibo Short v4.0.21`** (`rolling_pit_top50`, policies `elite_sniper_risk` & `sniper_rr1_horizon24`) to the **Primary Actionable Signal & Official Telegram Alert Engine**.
  - Assigned **`V3.1 Săn Đỉnh`** (`frozen_20260906_105716_bc3c369b`) to **Tier-1 Early Overheating UI Radar** (`operating_mode: shadow`, `shadow_telegram_enabled: false`) so early top-picking alerts no longer fire directly to Telegram.
  - Retained `ExecutionEngine` locked at `enabled: false, live_activated: false` while `paper_oos_v1` accumulates live forward OOS observations.
- **Production Hardening for `dao_vang.fibo_short`**:
  - Enforced `operating_mode == "research"` and `KillSwitch` blocks inside `dispatch_fibo_telegram_signal()` (double-locked in `configs/dev.yaml` with `operating_mode: research` and `fibo_trend_short.telegram_enabled: false`).
  - Wired `fibo_trend_short` cycle health into `scanner_heartbeat.json`, `inspect_heartbeat()`, and `GET/HEAD /api/ready` (`HTTP 503` with `reason: fibo_trend_short_failed` on lane failure).
  - Added thread-safe closed-candle caching (`fetch_closed_klines`) keyed by expected latest closed `H1/H4/D1` candle timestamp, cutting redundant 5-minute Binance kline REST requests by >96%.

- **Oracle Cloud (OCI) Infrastructure Cutover (`.github/workflows/deploy.yml`, `scripts/deploy_oracle_server.py`, `docs/DEPLOYMENT_ENVIRONMENT.md`)**:
  - Migrated CI/CD deployment workflow and manual deploy tooling from retired GCP (`136.110.29.208`) to **Oracle Cloud (`161.118.250.182` / `opc`, `ORACLE_SSH_KEY`, `ORACLE_HOST`, `ORACLE_USER`, `ORACLE_APP_DIR`)**.
  - Replaced hardcoded `/home/ubuntu/dao_vang` defaults across `backup_to_gdrive.sh`, `restore_from_gdrive.sh`, `install_production_cron.sh`, `prepare_runtime_permissions.sh`, and `prune_old_data.sh` with dynamic script-relative repository root resolution.
## [2.1.0] - 2026-10-16

### Added — Fibonacci Trend Short (`dao_vang.fibo_short`) & 6-Pillar Alpha Research Portal (`v4.0.0`)
- **4-Factor Orthogonal Alpha Engine (`src/dao_vang/fibo_short/`)**:
  - **Factor #1 (`L1` Macro & Prior Pump):** `Prior Pump >= 50%` (`F1A`), `pysystemtrade` multi-speed EWMAC (`8/32`, `16/64`, `32/128`) & vol-adjusted carry (`F1B`), and 5-Repo Benchmark (`KER(10) >= 0.35`, `Freqtrade squeeze <= 1.25`, `Hummingbot NATR <= 5.5%`, `VectorBT Sortino <= 0.8`) (`F1C`).
  - **Factor #2 (`L2` Impulse Quality):** `Impulse Drop >= 6%` combined with `Impulse KER >= 0.50` (`ALPHA-F2-IMPULSE-KER`) to filter out noisy overlapping drops and lock in institutional dump waves (`Mốc 4A` / `Mốc 4B`).
  - **Factor #3 (`L3` Pullback & Trigger):** H1 structural break (`Close < Low[-1]`) inside the shallow Fibonacci zone `0.236–0.786` (`ALPHA-F3-H1-BREAK-SHALLOW`) (`Mốc 5A` / `Mốc 5B`).
  - **Factor #4 (`L4` Dynamic Execution & Sizing):** Tightened structural Stop-Loss at `Fibo 0.886 + 0.25 ATR` (`ALPHA-F4A-SL0886`), Staged Exit (`40% TP1 @ Fibo 0.0 + Breakeven SL`, `30% TP2 @ Ext 1.272`, `30% TP3 @ Ext 1.618`), and Conviction Score (`0–100`) dynamic position sizing (`0.80x / 1.15x / 1.50x`) (`Mốc 6B` Toàn Diện, `Mốc 6A` Sniper Mở Rộng, `Mốc 6S` Sniper Tinh Hoa).
- **7-Year Multi-Cycle Validation (`2020–2025` IS + `2026` True Forward OOS)**:
  - Verified across 6 individual calendar years (`2020` to `2025`) and `2026` OOS (`01/2026–09/2026`).
  - `Mốc 4A` (`649` IS trades, `+2,051.5%`, `PF 2.41` + `22` OOS trades, `+98.3%`, `PF 6.60`) and `Mốc 6S` (`318` IS trades, `+807.1%`, `PF 2.09` + `11` OOS trades, `+66.6%`, `PF 7.36`) achieved **7/7 profitable calendar years (`2020–2026`)**, including the `2021` parabolic altcoin mania.
- **6-Pillar MECE Interactive Alpha Wiki (`artifacts/fibo_trend_short/fibo_alpha_research_2025.html`)**:
  - Reorganized into 6 non-overlapping pillars (`Schema v4.0.0`): (1) Executive Playbook & 3-Horizon Summary, (2) 9 Alpha Passports & Collinearity Matrix, (3) Factor Lab `F1→F4` & Visual Analogies, (4) 7-Year Cycle Analysis (`2020→2026`) & 4 Core Discoveries, (5) 14-Symbol & `H4/D1` Timeframe Anatomy, and (6) Independent AI Audit Dossier.
- **Independent AI Red-Team Audit Dossier (`artifacts/fibo_trend_short/CHATGPT_INDEPENDENT_AUDIT_DOSSIER.md`)**:
  - Complete mathematical specification, 26-parameter Degrees-of-Freedom disclosure, `0→40 bps` fee & slippage stress test (with `Break-Even Fee bps` of `162.8–202.8 bps` on 6-year IS and `472.3–551.0 bps` on 2026 OOS), and chronological portfolio concurrency & tail-risk distribution (`independent_audit_study.json`).
- **Web Dashboard & Scanner Integration**:
  - Added `FiboShortWorkspace.tsx` frontend workspace and `/api/fibo-short/*` API endpoints (`api_server.py`) plus 13 reproducible research scripts in `scripts/fibo_research/`.

### Added (Earlier Unreleased)
- `dao_vang.nostop`: no-stop-loss strategy research harness (4h panel of 116 USD-M perpetuals, causal engine with Cross liquidation, funding and liquidity-tiered costs). Train 2020–2023 / validation 2024–2025 / test 2026 enforced by SHA-256 sealed freeze and lock files; 31 locked candidates, results in `docs/NOSTOP_CANDIDATES_20261006.md`, protocol in `docs/NOSTOP_RESEARCH_PROTOCOL_20261006.md`.
- `dao_vang.nostop.shadow`: local light-weight shadow paper trading (one shared 4h feed, ~120 public kline calls per bar, deterministic replay per shadow) and a dashboard on `127.0.0.1:8890`. See `docs/NOSTOP_SHADOW.md`.

## [2.0.0-rc.2] - 2026-08-27

### Changed
- Synchronized backend, frontend, and version-history reporting on the `2.0.0-rc.2` release candidate.
- Disabled live Git updates by default and removed automatic destructive checkout recovery.
- Updated the CI frontend job to use Node 22, the lockfile cache, and `npm ci`.

### Security
- Replaced plaintext password headers, query parameters, localStorage persistence, and cookies with a short-lived signed `HttpOnly` session cookie.
- Added opt-in CORS allowlisting and baseline response security headers.
- Added login attempt throttling and fail-closed behavior when no access password is configured.

### Model contract
- The active frozen bundle remains `frozen_20260811_082824_96df7ec9` with `distribution_short_v1`, 24-hour horizon, 25 serving features, and 0.60 high-confidence / 0.45 watch thresholds.
- Bundles using `identity_v1` calibration now fail closed for alerting until a fitted calibration artifact is supplied and validated.

## [1.0.0-rc.1] - 2026-08-01

### Added
- **M1 (Raw Data Collection)**: Binance collectors for K-lines, Funding Rates, Global Accounts, and Top Accounts.
- **M2 (Data Normalization)**: DuckDB-based timeline alignment without pandas/polars.
- **M3 (Label Generation)**: Fixed-horizon, fixed-stop, and dynamic ATR labeling engine.
- **M4 (Feature Engineering)**: Price, Open Interest, Funding, and Taker features calculated via SQL.
- **M5 (Target Validation)**: Baseline rules, Logistic Regression walk-forward, calibration metrics, and leakage tests.
- **M6 (Shell Orchestration)**: CLI application using `typer` to orchestrate data, labels, features, experiments, and reports.

### Changed
- Refactored all pipelines to use pure Python + DuckDB.
- Maintained zero dependency on Pandas/Polars throughout the codebase.

### Fixed
- Fixed data leakage in target generation and timeline stitching by using deterministic `ASOF` joins and shifted metrics.
