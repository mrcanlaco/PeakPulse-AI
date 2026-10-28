"""Test Suite for Shadow Paper Trading System and Web Dashboard."""

import pytest
import pandas as pd
import numpy as np
from fastapi.testclient import TestClient

from dao_vang.shadow.shared_feed import SharedMarketFeed
from dao_vang.shadow.shadow_engine import ShadowInstance, ShadowPaperManager
from dao_vang.shadow.candidates_registry import CANDIDATE_REGISTRY
from dao_vang.shadow.web_dashboard import app


@pytest.fixture
def dummy_data():
    """Tạo dữ liệu nến 1H giả lập cho ETH và BTC."""
    dates = pd.date_range("2026-01-01", periods=100, freq="h", tz="UTC")
    df_eth = pd.DataFrame({
        "open": np.linspace(3000, 3100, 100),
        "high": np.linspace(3010, 3110, 100),
        "low": np.linspace(2990, 3090, 100),
        "close": np.linspace(3005, 3105, 100),
        "volume": np.full(100, 1000.0),
    }, index=dates)
    df_btc = pd.DataFrame({
        "open": np.linspace(60000, 62000, 100),
        "high": np.linspace(60100, 62100, 100),
        "low": np.linspace(59900, 61900, 100),
        "close": np.linspace(60050, 62050, 100),
        "volume": np.full(100, 500.0),
    }, index=dates)
    return {"ETHUSDT": df_eth, "BTCUSDT": df_btc}


def test_shared_feed_singleton():
    """Kiem tra tinh chat Singleton cua SharedMarketFeed."""
    feed1 = SharedMarketFeed()
    feed2 = SharedMarketFeed()
    assert feed1 is feed2


def test_shadow_instance_execution():
    """Kiem tra tinh toan tai can bang va khau tru phi cua ShadowInstance."""
    inst = ShadowInstance(
        shadow_id="TEST_SHADOW_1",
        name="Test Shadow Bot",
        strategy_id="C01_KALMAN",
        initial_capital=10000.0,
    )

    assert inst.equity == 10000.0
    assert inst.position_qty == 0.0

    # 1. Rebalance vao vi the 50% tai gia $3000
    inst.execute_rebalance(target_pct=0.5, exec_price=3000.0, timestamp_iso="2026-10-05T00:00:00Z", fee_rate_bps=11.5)

    assert inst.position_qty > 0
    assert inst.trade_count == 1
    # Phí khấu trừ 11.5 bps
    assert inst.cash < 5050.0

    # 2. Mark-to-market khi gia tang len $3300 (+10%)
    inst.update_price_mark(current_price=3300.0, timestamp_iso="2026-10-05T01:00:00Z")
    assert inst.equity > 10000.0
    assert inst.unrealized_pnl > 0

    # 3. Dong vi the (target 0%) tai gia $3300
    inst.execute_rebalance(target_pct=0.0, exec_price=3300.0, timestamp_iso="2026-10-05T02:00:00Z")
    assert inst.position_qty == 0.0
    assert inst.realized_pnl > 0
    assert inst.win_count == 1
    assert inst.trade_count == 2


def test_candidate_registry_completeness():
    """Dam bao toan bo 20 ung vien va baseline duoc dang ky day du."""
    assert len(CANDIDATE_REGISTRY) >= 21
    assert "C01_KALMAN" in CANDIDATE_REGISTRY
    assert "C16_COMPOSITE" in CANDIDATE_REGISTRY
    assert "C10_AMIHUD" in CANDIDATE_REGISTRY
    assert "BASE_POINT72" in CANDIDATE_REGISTRY


def test_web_api_endpoints():
    """Kiem tra cac REST endpoint cua Web Dashboard."""
    client = TestClient(app)

    # 1. Test GET /api/status
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert "active_shadows_count" in data
    assert "total_equity" in data
    assert "shadows" in data

    # 2. Test GET /api/candidates
    res = client.get("/api/candidates")
    assert res.status_code == 200
    cands = res.json()
    assert len(cands) >= 21

    # 3. Test POST /api/shadows/spawn
    spawn_payload = {
        "shadow_id": "TEST_AUTO_SPAWN",
        "name": "Auto Spawn Bot",
        "strategy_id": "C01_KALMAN",
        "capital": 15000.0,
    }
    res = client.post("/api/shadows/spawn", json=spawn_payload)
    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # 4. Test POST /api/shadows/{id}/action (pause, resume, reset)
    res = client.post("/api/shadows/TEST_AUTO_SPAWN/action", json={"action": "pause"})
    assert res.status_code == 200

    res = client.post("/api/shadows/TEST_AUTO_SPAWN/action", json={"action": "resume"})
    assert res.status_code == 200

    res = client.post("/api/shadows/TEST_AUTO_SPAWN/action", json={"action": "reset"})
    assert res.status_code == 200

    # 5. Test GET / (HTML Dashboard)
    res = client.get("/")
    assert res.status_code == 200
    assert "PeakPulse AI - Shadow Paper Trading Hub" in res.text
