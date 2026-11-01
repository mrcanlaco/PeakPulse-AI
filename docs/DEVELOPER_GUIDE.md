# 🛠️ DAO VANG Developer Guide & Contribution Playbook

Welcome to the **DAO VANG (PeakPulse AI)** Developer Guide! This playbook outlines standard workflows for setting up your environment, writing features, adding data collectors, and ensuring code quality.

---

## ⚡ 1. Quick Environment Setup

### Backend (Python 3.12)
We recommend using [`uv`](https://docs.astral.sh/uv/) for instant dependency management:
```bash
# Clone the repository
git clone https://github.com/mrcanlaco/Dao-Vang-Peak-Pulse.git
cd Dao-Vang-Peak-Pulse

# Install all backend dependencies and dev tools
uv sync --all-extras --dev

# Activate the virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### Frontend (Node.js 18+ & npm)
```bash
cd frontend
npm install
cd ..
```

---

## 🚀 2. Running the System Locally

### Run in Development Mode:
```bash
# Option A: Run via batch scripts (Windows)
.\scripts\windows\run_dev.bat

# Option B: Run via individual commands
# 1. Start Web API backend on port 8000
python -m dao_vang.web.run --port 8000

# 2. Start Frontend Vite dev server on port 5173
cd frontend && npm run dev
```

---

## 🧩 3. How to Add a New Data Collector

All data collectors inherit from the base contract or follow the standard collector pattern in `src/dao_vang/data/collectors/`:

1. **Create Collector File:** `src/dao_vang/data/collectors/my_collector.py`
2. **Implement Data Retrieval & Schema Normalization:**
   ```python
   from datetime import datetime
   from dao_vang.config.settings import AppSettings
   from dao_vang.data.collectors.binance_client import BinanceClient
   from dao_vang.data.manifests.models import CollectionManifest

   class MyCustomCollector:
       def __init__(self, client: BinanceClient, settings: AppSettings) -> None:
           self.client = client
           self.settings = settings

       def collect(self, start_time: datetime, end_time: datetime, run_id: str) -> CollectionManifest:
           # 1. Query raw data from exchange client
           # 2. Write raw partition to DuckDB / Parquet
           # 3. Return CollectionManifest with rows_raw and status
           ...
   ```
3. **Register Unit Tests:** Add test cases in `tests/unit/data/collectors/test_my_collector.py`.

---

## 📈 4. How to Add a New Feature Builder

Features in DAO VANG must be calculated point-in-time. Add a leakage regression test for every new source or join because the existing safeguards are not a blanket guarantee.

1. **Create Feature Builder:** `src/dao_vang/features/builders/my_feature.py`
2. **Implement Feature Computation:**
   ```python
   import pandas as pd

   class MyFeatureBuilder:
       def build_features(self, df: pd.DataFrame) -> pd.DataFrame:
           # df contains point-in-time sorted time series (close_time)
           # Example: 12-period rolling ratio
           df["my_custom_feature"] = df["close"].pct_change(12)
           return df
   ```
3. **Register in Registry:** Add your builder class to `src/dao_vang/features/registry.py`.
4. **Add Unit Tests:** Verify point-in-time calculation in `tests/unit/features/test_my_feature.py`.

---

## 🤖 5. How to Customize Scoring or Add Rules

Scoring combines ML model probabilities and deterministic market signals:

- **Location:** `src/dao_vang/scoring/distribution_scorer.py`
- **Rule Adjustments:** Adjust weights, thresholds, or weighted component logic in `DistributionScorer.calculate_score()`.
- **BTC Context:** Update BTC correlation / market trend weighting in `src/dao_vang/scoring/btc_context.py`.

---

## 🎨 6. How to Modify or Add Frontend Components

1. **Component Location:** `frontend/src/components/`
2. **Design Tokens:** Use TailwindCSS utility classes aligned with our dark futuristic palette (`slate-950`, `amber-400`, `emerald-400`, `red-400`).
3. **State Management:** Keep the 30-second API polling snapshots synced through `MainWorkspace.tsx` and custom React hooks.
4. **Typecheck & Build:**
   ```bash
   cd frontend
   npm run build
   ```

---

## ✅ 7. Quality Assurance & Local Verification

Before submitting a Pull Request, run the full verification suite:

```bash
# 1. Run full dev verification script
python scripts/dev_check.py

# Or run individual tools:
uv run ruff check .          # Linting and formatting
uv run pyright               # Strict type checking
.\.venv\Scripts\pytest.exe   # All unit, integration & leakage tests
```

---

## 📜 8. Git & Pull Request Guidelines

- **Branch Naming:** `feat/your-feature-name` or `fix/your-bug-description`.
- **Commit Messages:** Follow Conventional Commits:
  - `feat(collector): add Bybit open interest endpoint`
  - `fix(scanner): resolve cooldown timer on duplicate alerts`
  - `docs(arch): update pipeline diagram with regime classifier`
- **Always Keep Tests Green:** PRs with failing tests or typecheck errors will not pass CI gates.
