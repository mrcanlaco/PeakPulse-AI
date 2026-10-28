import json
from datetime import timedelta
from unittest.mock import patch

import pytest

from dao_vang.config.settings import AppSettings, ExecutionConfig
from dao_vang.execution.contracts import (
    StrategyManifest,
    TradeSignal,
    policy_contract,
    utc_now,
)
from dao_vang.web.execution_api import execution_store
from dao_vang.web.execution_dashboard import dashboard


def setup_store(tmp_path, environment="simulation"):
    settings = AppSettings(_env_file=None)
    settings.paths.data_dir = tmp_path
    settings.execution = ExecutionConfig(enabled=False, environment=environment)
    return settings, execution_store(settings)


def equity(store, at, amount):
    value = {
        "at": at.isoformat(),
        "wallet": 500,
        "equity": amount,
        "available": amount - 5,
        "unrealized": amount - 500,
        "peak": 500,
        "drawdown": 1 - amount / 500,
    }
    store.set("account", value)
    with patch("dao_vang.execution.store.utc_now", return_value=at):
        store.record("equity", value)


def test_empty_dashboard_is_not_a_fabricated_500_dollar_account(tmp_path):
    settings, store = setup_store(tmp_path, "live")
    settings.execution.live_api_key = "never-expose-key"
    settings.execution.live_api_secret = "never-expose-secret"
    with patch(
        "dao_vang.execution.binance_api.BinanceExecutionClient._request",
        side_effect=AssertionError("must not call Binance"),
    ):
        result = dashboard(settings)
    assert result["account"] is None
    assert result["totals"]["recorded_fees"] is None
    assert result["equity_curve"] == []
    assert not result["account_fresh"]
    assert not result["live_gate"]["eligible"]
    assert result["source"] == "binance_live_reconciled"
    assert "never-expose" not in json.dumps(result)
    assert not store.commands()


def test_totals_do_not_double_count_income_commissions_and_include_open_losses(
    tmp_path,
):
    settings, store = setup_store(tmp_path)
    now = utc_now()
    equity(store, now - timedelta(hours=4), 500)
    equity(store, now, 400)
    store.set("heartbeat", {"at": now.isoformat(), "healthy": True})
    store.set(
        "positions",
        [
            {
                "symbol": "ABCUSDT",
                "positionAmt": "-1",
                "markPrice": "200",
                "unRealizedProfit": "-100",
            },
            {
                "symbol": "OTHERUSDT",
                "positionAmt": "1",
                "markPrice": "1",
                "unRealizedProfit": "0",
            },
        ],
    )
    store.trade(
        {"id": "open", "symbol": "ABCUSDT", "status": "open", "entry_price": 100}
    )
    store.trade(
        {"id": "closed", "symbol": "ABCUSDT", "status": "closed", "net_pnl": 1.2}
    )
    store.money_event(
        "fill1", "1", "fill", {"commissionAsset": "USDT", "commission": "0.02"}
    )
    store.money_event(
        "fill1", "1", "fill", {"commissionAsset": "USDT", "commission": "0.02"}
    )
    store.money_event(
        "commission", "1", "COMMISSION", {"asset": "USDT", "income": "-0.02"}
    )
    store.money_event(
        "funding1", "1", "FUNDING_FEE", {"asset": "USDT", "income": "0.12"}
    )
    store.money_event(
        "funding2", "2", "FUNDING_FEE", {"asset": "USDT", "income": "-0.3"}
    )
    result = dashboard(settings, "24h")
    assert result["account_fresh"]
    assert result["totals"]["recorded_fees"] == pytest.approx(0.02)
    assert result["totals"]["recorded_funding"] == pytest.approx(-0.18)
    assert result["totals"]["closed_net_pnl"] == 1.2
    assert result["totals"]["equity_change"] == -100
    assert result["trades"][0]["unrealized"] == -100
    assert result["unmanaged_positions"][0]["symbol"] == "OTHERUSDT"
    assert len(result["equity_curve"]) == 2
    assert result["equity_curve"][-1]["equity"] == 400
    assert result["equity_curve"][-1]["drawdown"] == pytest.approx(0.2)


def test_progress_is_manifest_scoped_deduplicated_and_stops_at_last_account(tmp_path):
    settings, store = setup_store(tmp_path)
    now = utc_now()
    frozen = now - timedelta(days=10)
    manifest = StrategyManifest(
        frozen_at=frozen,
        model_id="m",
        label_version="v",
        threshold=0.5,
        files={"model": "a" * 64},
        policy=policy_contract(settings.execution),
    )
    settings.execution.manifest_path = tmp_path / "manifest.json"
    settings.execution.manifest_path.write_text(
        manifest.model_dump_json(), encoding="utf-8"
    )
    store.set("manifest_id", manifest.identity)
    equity(store, frozen - timedelta(days=1), 500)
    first = frozen + timedelta(days=1)
    equity(store, first, 500)
    equity(store, first + timedelta(days=7), 490)
    for source, event, hours, eligible, mid in [
        ("one", "episode1", 0, True, manifest.identity),
        ("repeat", "episode1", 6, True, manifest.identity),
        ("overlap", "episode2", 1, True, manifest.identity),
        ("reject", "episode3", 24, False, manifest.identity),
        ("old", "episode4", 48, True, "b" * 64),
        ("next", "episode5", 168, True, manifest.identity),
    ]:
        at = first + timedelta(hours=hours)
        store.signal(
            TradeSignal(
                source_id=source,
                event_id=event,
                manifest_id=mid,
                symbol="ABCUSDT",
                observed_at=at,
                expires_at=at + timedelta(minutes=5),
                reference_price=100,
                atr=2,
                eligible=eligible,
            )
        )
    result = dashboard(settings)
    assert result["progress"]["observed_days"] == 7
    assert result["progress"]["independent_events"] == 2
    assert result["progress"]["time_windows"] == 2
    assert not result["account_fresh"]
    assert not result["progress"]["observation_continuity_verified"]
    assert not result["live_gate"]["eligible"]


def test_chart_period_and_bucket_limits_are_enforced(tmp_path):
    settings, store = setup_store(tmp_path)
    now = utc_now().replace(minute=0, second=0, microsecond=0)
    for hour in range(48):
        equity(store, now - timedelta(hours=48 - hour), 500 + hour)
    with patch("dao_vang.web.execution_dashboard.utc_now", return_value=now):
        result = dashboard(settings, "24h")
    assert len(result["equity_curve"]) == 24
    with pytest.raises(ValueError, match="period"):
        dashboard(settings, "all")
