# DAO VANG (PeakPulse AI) — Project Context

## What this project does

Cryptocurrency futures short-signal radar. Scans 150+ Binance USD-M futures every 5 minutes,
scores distribution risk (0–100), delivers alerts via Telegram + React dashboard,
and optionally executes trades via an isolated Execution Engine (Testnet paper-trading first).

---

## Architecture — pipeline flow

```
Binance REST
  ├─ [Tier 1: Early Overheating Radar — UI Only]
  │    → Collectors (klines/OI/funding/taker/ratios) → DuckDB + Parquet
  │    → Feature builders (point-in-time, zero lookahead)
  │    → Frozen model bundle V3.1 (LightGBM + isotonic) + DistributionScorer (0-100)
  │    → React UI (RADAR / WATCHLIST tabs; shadow_telegram_enabled: false)
  └─ [Tier 2: Official Actionable Signal Engine — Telegram & FIBO_SHORT Tab]
       → Closed-Candle Cache (H1 / H4 / D1) + Rolling PIT Top-50 Universe
       → 4-Factor Fibo Short v4.0.21 (elite_sniper_risk & sniper_rr1_horizon24)
       → Official Telegram Alerts (Entry, SL 0.886, TP1/2/3, 0.5% NAV risk) + React UI
       → Parallel Shadow Comparison + paper_oos_v1 (ExecutionEngine locked live_activated: false)
```

### Key module map

| Path | Responsibility |
|---|---|
| `src/dao_vang/config/settings.py` | `AppSettings` via Pydantic v2 + env vars |
| `src/dao_vang/data/collectors/` | Per-metric Binance collectors |
| `src/dao_vang/data/storage/duckdb.py` | DuckDB query layer |
| `src/dao_vang/features/builder.py` | Point-in-time feature assembly |
| `src/dao_vang/features/builders/` | Per-signal builders (price, OI, funding) |
| `src/dao_vang/scoring/distribution_scorer.py` | Composite 0-100 score (rule components) |
| `src/dao_vang/scoring/frozen_inference.py` | Frozen model serving, fail-closed |
| `src/dao_vang/scanner/daemon.py` | `ScannerDaemon` — 24/7 main loop |
| `src/dao_vang/scanner/candidate_filter_v2.py` | Pre-filter before model scoring |
| `src/dao_vang/scanner/pump_filter.py` | Pump pattern pre-filter |
| `src/dao_vang/scanner/anomalies.py` | Independent anomaly radar (0-100) |
| `src/dao_vang/scanner/outcomes.py` | Empirical precision/PnL tracking |
| `src/dao_vang/alerts/telegram.py` | Telegram delivery + dedup |
| `src/dao_vang/fibo_short/` | Official Tier-2 Primary Short Signal Engine (`v4.0.21`, H4/D1 → H1) |
| `src/dao_vang/execution/` | Isolated Auto-Trading Execution Engine |
| `src/dao_vang/web/api_server.py` | ThreadingHTTPServer REST API |
| `src/dao_vang/validation/` | Walk-forward splitter, leakage auditor |
| `src/dao_vang/experiments/` | Training runner, forward test, self-learning |
| `frontend/src/` | React 19 + TypeScript + Vite dashboard |

---

## Environments

| Env | DB | Ports | Mode |
|---|---|---|---|
| Dev | `data/dev.duckdb` | API: 8000, UI: 5173 | `research` — no Telegram sends |
| Live | `data_live/live.duckdb` | API: 8001 | `live` — real alerts |

Do not mix `data/` and `data_live/` paths. Never write to `data_live/` during research/testing.

---

## Build, run, and test commands

```bash
# Install / sync dependencies (Python 3.12, uv)
uv sync --all-extras --dev

# Run dev (Windows batch — starts API on :8000 + Vite on :5173)
.\run_dev.bat

# Run API backend only
python -m dao_vang.web.run --port 8000

# Run scanner only
python -m dao_vang.cli.main scan

# Backend tests (full suite)
uv run pytest

# Specific test path
uv run pytest tests/unit/scoring/

# Linting
uv run ruff check .

# Type checking (only these files are gated in CI)
uv run pyright src/dao_vang/config/settings.py src/dao_vang/scoring/frozen_inference.py src/dao_vang/updater/manager.py src/dao_vang/web/version_history.py

# Frontend
cd frontend && npm ci && npm run build
```

---

## Non-negotiable correctness rules

### 1. Zero lookahead bias — absolute
- Feature builders consume only data at or before candle close timestamp `t`.
- DuckDB time-series joins use `as-of` matching (strictly `<=`). Never use `>=` on future rows.
- Walk-forward splits use embargo gaps. Test fold labels must **never** reach threshold selection
  (enforced in `tests/qa/test_release_gates.py::test_threshold_helper_never_receives_test_labels`).

### 2. Frozen model bundles — immutable in production
- `scanner.frozen_model_id` in config points to a locked artifact directory.
- `frozen_inference.py` verifies SHA-256 checksums before scoring. **Never bypass checksum verification.**
- Raw model probabilities must pass calibration gate before alerting (`calibrator_unvalidated_identity`
  reason code = not alertable).
- Self-learning (`self_learning.enabled`) creates challenger models only; it never overwrites
  `scanner.frozen_model_id`. That key is changed only by an explicit human decision.

### 3. Scoring fail-closed
- Stale snapshots (`max_feature_age_minutes = 10`) → `alertable = False`.
- Invalid quality status → `alertable = False`.
- `FrozenInferenceError` propagation must not be swallowed silently.

### 4. Telegram rate limits — always enforce
- `global_daily_alert_limit = 15`, `coin_daily_alert_limit = 2`.
- `cooldown_minutes = 120` per coin before re-alert.
- `operating_mode: research` must never send real Telegram messages.
- `shadow_telegram_enabled` in research mode sends to a labelled shadow channel only.
- Any code path that calls `TelegramNotifier` must check `_mode_allows_tier()` first.

### 5. Candidate comparison challenger — audit only
- The challenger in `candidate_comparison` logs outcomes only. It must never trigger Telegram sends.

### 6. Auto-trading safety — isolated execution
- `ScannerDaemon` must **never** execute trades directly. It only produces `alertable = True` signals.
- `ExecutionEngine` runs as a completely decoupled component, reading signals from the database or via webhook.
- **Paper-trading first:** Auto-trading must strictly use `paper_trading=True` on Binance Testnet before any live deployment. Live API keys are prohibited until paper trading logic is fully validated.


### 7. Low-cap Universe Selection (Pump & Dump Target)
- **Strict Criteria**: The project exclusively targets mid-to-low cap coins susceptible to massive distribution pumps (50-300%).
- **Volume Constraint (Binance)**: Minimum 24h volume of **$5,000,000** to guarantee liquidity and prevent extreme spread/slippage.
- **Market Cap Constraint (CoinGecko)**: Strictly between **$10,000,000 and $1,000,000,000**. Coins exceeding $1B (e.g., BTC, ETH, SOL) are "dinosaur" large-caps and must be excluded. Micro-caps under $10M are discarded as dead or purely manipulated wash-trading.
- **Generation**: Always use `scripts/generate_true_lowcap_universe.py` to cross-reference Binance USD-M active perpetuals with CoinGecko market caps before downloading backtest data.

---

## Data schemas and generated artifacts

- `data/` and `data_live/` — DuckDB + Parquet. Do not hand-edit.
- `artifacts/` — frozen model bundles, self-learning runs, reports. Do not hand-edit model files.
- `frontend/dist/` — Vite build output. Generated; do not edit.
- `data/watchlist.json`, `data/scanner_kill_switch.json` — runtime state files, not source.

---

## Adding new code — conventions

### New data collector
1. Create `src/dao_vang/data/collectors/my_collector.py`
2. Implement `collect(start_time, end_time, run_id) -> CollectionManifest`
3. Register in `daemon.py` `_COLLECTORS` list
4. Test in `tests/unit/data/collectors/test_my_collector.py`

### New feature builder
1. Create `src/dao_vang/features/builders/my_feature.py`
2. Implement `build_features(df: pd.DataFrame) -> pd.DataFrame` using only past data
3. Register in `src/dao_vang/features/registry.py`
4. Unit test must verify point-in-time correctness (no shift-forward)

### New scoring component
- Add function to `scoring/distribution_scorer.py` returning `ScoreComponent`
- Add to `compute_distribution_score()` component list
- Do not alter threshold logic in `frozen_inference.py` without re-calibrating the bundle

### Frontend
- Dark palette: `slate-950`, `amber-400`, `emerald-400`, `red-400` (TailwindCSS)
- API polling interval: 30s in `MainWorkspace.tsx`
- All new endpoints: add to `api_server.py` + matching TypeScript type in `frontend/src/types.ts`

---

## CI gates (must pass before merge)

1. `uv run ruff check .` — zero errors
2. `uv run pyright` on gated files (see above) — zero errors
3. `uv run pytest` — all tests green, including `tests/qa/test_release_gates.py`
4. `cd frontend && npm run build` — zero TypeScript errors

---

## Config loading

- Backend: Pydantic v2 `AppSettings`, reads `.env` and `configs/live.yaml` (or `configs/dev.yaml`).
- Sensitive keys (Telegram token, etc.) via env vars prefixed `DAO_VANG_TELEGRAM__`.
- Never commit `.env` or `configs/live.yaml`.
- Example: `configs/default.example.yaml`.
