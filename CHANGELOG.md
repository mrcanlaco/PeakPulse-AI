# Changelog

All notable changes to the Đảo Vàng project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
