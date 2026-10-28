"""FastAPI Web Server for PeakPulse Quantitative Shadow Supervisor.
Serves real-time dashboard and provides RESTful control endpoints for all shadow trading bots.
"""

from __future__ import annotations
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from .engine import ShadowPaperCoordinator
from .models import (
    get_all_shadows,
    get_db_connection,
    get_market_quotes,
    init_db,
    register_shadow,
    update_shadow_status,
)

logger = logging.getLogger("shadow.server")

# Path references
SHADOW_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SHADOW_DIR.parents[2]
CATALOG_PATH = PROJECT_DIR / "artifacts" / "walkforward_2020_2026" / "top20_candidates_catalog.json"
DASHBOARD_HTML_PATH = SHADOW_DIR / "dashboard.html"

# Global FastAPI App
app = FastAPI(title="PeakPulse Shadow Supervisor", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Coordinator Instance
coordinator: Optional[ShadowPaperCoordinator] = None


def get_coordinator() -> ShadowPaperCoordinator:
    global coordinator
    if coordinator is None:
        coordinator = ShadowPaperCoordinator()
        coordinator.start()
    return coordinator


def seed_candidates_from_catalog():
    """Populate 20 quantitative candidates into SQLite state database if empty."""
    init_db()
    existing = get_all_shadows()
    if len(existing) >= 21:
        return

    if not CATALOG_PATH.exists():
        logger.warning(f"Catalog file not found at {CATALOG_PATH}")
        return

    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    candidates = data.get("top20_candidates", [])
    universe = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "AVAXUSDT", "NEARUSDT", "DOGEUSDT"]

    for cand in candidates:
        cand_id = cand["candidate_id"]
        params = cand["params"]
        full = cand["full_period"]
        train = cand["train"]
        val = cand["validation"]
        test = cand["test_2026"]

        spec = {
            "macro_btc_filter": params.get("macro", "ema600"),
            "entry_donch_len": params.get("donch", 40),
            "exit_ema": params.get("exit", "ema40"),
            "trail_atr_mult": params.get("trail", 2.5),
            "break_even_atr_mult": params.get("be", 1.5),
            "staged_tighten_atr": params.get("tighten", 99.0),
            "risk_mode": params.get("risk_mode", "vol_target"),
            "risk_param": params.get("risk_param", 0.35),
            "target_annual_vol": params.get("risk_param", 0.35),
            "use_market_breadth": params.get("breadth", True),
            "slots": 2,
            "metrics": {
                "train_cagr": train.get("cagr_pct", 0.0),
                "train_maxdd": train.get("maxdd_pct", 0.0),
                "train_calmar": train.get("calmar", 0.0),
                "val_cagr": val.get("cagr_pct", 0.0),
                "val_maxdd": val.get("maxdd_pct", 0.0),
                "val_calmar": val.get("calmar", 0.0),
                "test_cagr": test.get("cagr_pct", 0.0),
                "test_maxdd": test.get("maxdd_pct", 0.0),
                "test_calmar": test.get("calmar", 0.0),
                "full_cagr": full.get("cagr_pct", 0.0),
                "full_maxdd": full.get("maxdd_pct", 0.0),
                "full_calmar": full.get("calmar", 0.0),
                "sharpe": full.get("sharpe", 0.0),
                "win_rate": full.get("win_rate_pct", 0.0),
                "profit_factor": full.get("profit_factor", 0.0),
            },
        }

        register_shadow(
            shadow_id=cand_id,
            name=f"Shadow {cand_id}",
            family="Donchian-Trend-VolTarget",
            universe=universe,
            spec=spec,
            initial_capital=10_000.0,
            calmar_benchmark=full.get("calmar", 0.0),
            cagr_benchmark=full.get("cagr_pct", 0.0),
            maxdd_benchmark=full.get("maxdd_pct", 0.0),
            initial_status="RUNNING",  # Default RUNNING per user confirmation
        )
    logger.info(f"Seeded {len(candidates)} candidates from catalog into DB.")

    # Register Candidate 21: ALPHA-21_DUAL_FRONTIER_CONVEX
    spec_21 = {
        "macro_btc_filter": "ema500",
        "entry_donch_len": 30,
        "exit_ema": "ema40",
        "trail_atr_mult": 2.5,
        "break_even_atr_mult": 1.5,
        "staged_tighten_atr": 99.0,
        "risk_mode": "vol_target",
        "risk_param": 0.34,
        "target_annual_vol": 0.34,
        "use_market_breadth": True,
        "adaptive_breadth_convex": True,
        "slots": 2,
        "metrics": {
            "train_calmar": 2.429,
            "val_calmar": 2.940,
            "test_cagr": 33.01,
            "full_cagr": 42.17,
            "full_maxdd": 18.81,
            "full_calmar": 3.420,
            "sharpe": 1.72,
            "win_rate": 39.5,
            "profit_factor": 2.35,
        },
    }
    register_shadow(
        shadow_id="ALPHA-21_DUAL_FRONTIER_CONVEX",
        name="Dual-Engine Agile Convex (Frontier-07 + Alpha-01)",
        family="Dual-Engine-Convex-Breadth",
        universe=universe,
        spec=spec_21,
        initial_capital=10_000.0,
        calmar_benchmark=3.420,
        cagr_benchmark=42.17,
        maxdd_benchmark=18.81,
        initial_status="RUNNING",
    )
    logger.info("Registered Candidate 21: ALPHA-21_DUAL_FRONTIER_CONVEX into DB.")


@app.on_event("startup")
def startup_event():
    seed_candidates_from_catalog()
    get_coordinator()


@app.on_event("shutdown")
def shutdown_event():
    global coordinator
    if coordinator is not None:
        coordinator.stop()


# ------------------ REST APIs ------------------ #

@app.get("/", response_class=HTMLResponse)
def index():
    if not DASHBOARD_HTML_PATH.exists():
        raise HTTPException(status_code=404, detail="Dashboard template not found")
    return HTMLResponse(content=DASHBOARD_HTML_PATH.read_text(encoding="utf-8"))


@app.get("/api/status")
def get_status():
    coord = get_coordinator()
    shadows = get_all_shadows()

    total_equity = sum(s["equity"] for s in shadows)
    total_cash = sum(s["cash"] for s in shadows)
    total_realized_pnl = sum(s["realized_pnl"] for s in shadows)
    total_unrealized_pnl = sum(s["unrealized_pnl"] for s in shadows)
    total_trades = sum(s["total_trades"] for s in shadows)
    total_wins = sum(s["win_trades"] for s in shadows)

    active_shadows_count = sum(1 for s in shadows if s["status"] == "RUNNING")
    paused_shadows_count = sum(1 for s in shadows if s["status"] in ["PAUSED", "STOPPED"])

    active_positions_count = 0
    with get_db_connection() as conn:
        active_positions_count = conn.execute("SELECT COUNT(*) FROM positions WHERE side != 0").fetchone()[0]

    initial_capital_total = sum(s["initial_capital"] for s in shadows)
    total_realized_pct = (total_realized_pnl / initial_capital_total * 100.0) if initial_capital_total > 0 else 0.0
    win_rate = (total_wins / total_trades * 100.0) if total_trades > 0 else 0.0

    # BTC Regime determination
    btc_regime = "NEUTRAL"
    btc_buf = coord.feeder.candle_buffers_4h.get("BTCUSDT")
    if btc_buf is not None and len(btc_buf) >= 100:
        c_arr = btc_buf["close"].values
        import pandas as pd
        span = 600
        ema_val = pd.Series(c_arr).ewm(span=span).mean().iloc[-1]
        btc_regime = "BULLISH" if c_arr[-1] > ema_val else "BEARISH"

    feeder_stats = coord.feeder.get_stats()

    return {
        # Core keys
        "feeder_status": "Active (0% Load)",
        "btc_regime": btc_regime,
        "btc_macro_regime": btc_regime,
        "total_equity": total_equity,
        "total_cash": total_cash,
        "total_realized_pnl": total_realized_pnl,
        "total_unrealized_pnl": total_unrealized_pnl,
        "total_realized_pct": total_realized_pct,
        "active_positions_count": active_positions_count,
        "active_shadows_count": active_shadows_count,
        "running_count": active_shadows_count,
        "paused_shadows_count": paused_shadows_count,
        "paused_count": paused_shadows_count,
        "total_shadows_count": len(shadows),
        "total_count": len(shadows),
        "total_trades": total_trades,
        "global_total_trades": total_trades,
        "total_wins": total_wins,
        "win_rate": win_rate,
        "global_win_rate": win_rate,
        "api_call_count": feeder_stats.get("api_call_count", 0),
    }


@app.get("/api/shadows")
def list_shadows():
    shadows = get_all_shadows()
    out = []
    for s in shadows:
        spec = s.get("spec", {})
        metrics = spec.get("metrics", {})
        out.append({
            "id": s["id"],
            "name": s["name"],
            "family": s["family"],
            "status": s["status"],
            "universe": s.get("universe", []),
            "initial_capital": s["initial_capital"],
            "cash": s["cash"],
            "equity": s["equity"],
            "realized_pnl": s["realized_pnl"],
            "unrealized_pnl": s["unrealized_pnl"],
            "total_trades": s["total_trades"],
            "win_trades": s["win_trades"],
            "calmar_benchmark": s.get("calmar_benchmark", 0.0),
            "cagr_benchmark": s.get("cagr_benchmark", 0.0),
            "maxdd_benchmark": s.get("maxdd_benchmark", 0.0),
            "active_positions": s.get("active_positions", []),
            "spec": spec,
            "metrics": {
                "full_calmar": s.get("calmar_benchmark", 0.0),
                "full_cagr": s.get("cagr_benchmark", 0.0),
                "full_maxdd": s.get("maxdd_benchmark", 0.0),
                "val_calmar": metrics.get("val_calmar", 0.0),
                "val_cagr": metrics.get("val_cagr", 0.0),
                "test_cagr": metrics.get("test_cagr", 0.0),
                "sharpe": metrics.get("sharpe", 0.0),
                "win_rate": metrics.get("win_rate", 0.0),
            }
        })
    return out


@app.get("/api/market")
def get_market():
    coord = get_coordinator()
    quotes = coord.feeder.get_all_quotes()
    # If feeder memory empty, fallback to DB
    if not quotes:
        quotes = get_market_quotes()
    return quotes


@app.get("/api/trades")
def get_recent_trades():
    with get_db_connection() as conn:
        rows = conn.execute("""
        SELECT * FROM trades ORDER BY closed_at DESC LIMIT 50
        """).fetchall()
        return [dict(r) for r in rows]


class ActionPayload(BaseModel):
    action: str  # 'RUNNING', 'PAUSED', 'FLATTEN'


@app.post("/api/shadows/{shadow_id}/action")
def shadow_action(shadow_id: str, payload: ActionPayload):
    coord = get_coordinator()
    success = coord.toggle_shadow(shadow_id, payload.action)
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to apply {payload.action} on shadow {shadow_id}")
    return {"status": "success", "shadow_id": shadow_id, "action": payload.action}


@app.post("/api/shadows/control-all")
def control_all(payload: ActionPayload):
    coord = get_coordinator()
    shadows = get_all_shadows()
    results = {}
    for s in shadows:
        s_id = s["id"]
        res = coord.toggle_shadow(s_id, payload.action)
        results[s_id] = res
    return {"status": "success", "action": payload.action, "results": results}
