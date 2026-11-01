# DAO VANG — Development & Live Setup Guide

Complete reference for setting up local development and live production daemon environments for DAO VANG (PeakPulse AI).

---

## 1. Environment Setup

### Prerequisites
- **Python 3.12**
- **uv** (recommended) or **pip**
- **Node.js 22+** & **npm** (for Frontend Web Dashboard)

### Clone & Install
```bash
# Clone the repository
git clone https://github.com/mrcanlaco/Dao-Vang-Peak-Pulse.git
cd Dao-Vang-Peak-Pulse

# Install Python package in editable mode
pip install -e .

# Install frontend dependencies
cd frontend && npm install && cd ..
```

---

## 2. Running in Development Mode

You can run the scanner and web server locally using the provided batch scripts or CLI commands:

### Start Scanner Daemon (Dev)
```bash
# Windows
scripts\windows\run_scanner_dev.bat

# Or via CLI
dao-vang scanner run --config configs/dev.yaml
```

### Start Web Server & UI (Dev)
```bash
# Windows
scripts\windows\run_dev.bat

# Or via CLI
dao-vang web serve --host 127.0.0.1 --port 8501
```

---

## 3. Running in Live Production Mode

### Live Configuration (`configs/live.yaml`)
Ensure your live settings are properly populated:
```yaml
scanner:
  operating_mode: "production_alerting"
  poll_interval_minutes: 5
  max_coins: 150
  telegram_min_probability: 0.70

telegram:
  language: "en"  # "en" for English, "vi" for Vietnamese
```

### Launch Live Daemons
```bash
# Launch live scanner
run_scanner_live.bat

# Launch live API & web dashboard
run_live.bat
```

---

## 4. Key CLI Commands Reference

- **Collect Market Data:** `dao-vang data collect --start-timestamp <TS1> --end-timestamp <TS2>`
- **Generate Labels:** `dao-vang labels generate --db-path data/dev.duckdb`
- **Generate Features:** `dao-vang features generate --db-path data/dev.duckdb`
- **Train & Freeze Model:** `dao-vang experiment freeze --db-path data/dev.duckdb`
- **Test Telegram Alert:** `dao-vang scanner test-telegram`
