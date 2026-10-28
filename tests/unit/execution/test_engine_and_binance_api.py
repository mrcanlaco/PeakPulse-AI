import json
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest

from dao_vang.config.settings import AppSettings, ExecutionConfig
from dao_vang.execution.binance_api import (
    BinanceExecutionClient,
    ExchangeError,
    format_to_step,
)
from dao_vang.execution.contracts import (
    StrategyManifest,
    TradeSignal,
    policy_contract,
    utc_now,
)
from dao_vang.execution.engine import ExecutionEngine
from dao_vang.execution.paper import PaperBroker

RULES = {
    "step_size": "0.001",
    "market_step": "0.001",
    "tick_size": "0.01",
    "min_qty": 0.001,
    "max_qty": 10000,
    "market_min_qty": 0.001,
    "market_max_qty": 10000,
    "min_notional": 5,
}


def engine_at(tmp_path, limit=1):
    settings = AppSettings(_env_file=None)
    settings.paths.data_dir = tmp_path
    settings.execution = ExecutionConfig(enabled=True, max_open_positions=limit)
    engine = ExecutionEngine(settings, tmp_path / "scanner.duckdb")
    (tmp_path / "scanner_heartbeat.json").write_text(
        json.dumps(
            {
                "timestamp": utc_now().isoformat(),
                "status": "running",
                "last_cycle_status": "success",
            }
        ),
        encoding="utf-8",
    )
    broker = PaperBroker(settings.execution, engine.store)
    broker.quote = Mock(
        return_value={
            "bid": 100.0,
            "ask": 100.01,
            "bids": [[100.0, 100]],
            "asks": [[100.01, 100]],
        }
    )
    broker.get_symbol_rules = Mock(return_value=dict(RULES))
    broker.submit = Mock(wraps=broker.submit)
    engine._api_client = broker
    engine.manifest = StrategyManifest(
        frozen_at=utc_now() - timedelta(days=1),
        model_id="test",
        label_version="test",
        threshold=0.5,
        files={"test": "hash"},
        policy=policy_contract(settings.execution),
    )
    return engine, broker


def signal_for(engine, identity="one", symbol="ABCUSDT"):
    now = utc_now()
    return TradeSignal(
        event_id=identity,
        source_id=identity,
        symbol=symbol,
        manifest_id=engine.manifest.identity,
        observed_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(minutes=4),
        reference_price=100,
        atr=2,
        eligible=True,
    )


def enter(engine, broker, identity="one", symbol="ABCUSDT"):
    result = engine._enter(signal_for(engine, identity, symbol), broker.account())
    engine.reconcile()
    return result


def test_format_to_step():
    assert format_to_step(0.12345, "0.001") == "0.123"
    assert format_to_step(10.59, "0.05") == "10.55"
    with pytest.raises(ValueError):
        format_to_step(float("nan"), ".01")


def test_only_short_entry_and_reduce_only_limit_no_stop(tmp_path):
    engine, broker = engine_at(tmp_path)
    assert enter(engine, broker) == "submitted"
    calls = broker.submit.call_args_list
    assert len(calls) == 2
    assert calls[0].args[2] == "SELL"
    assert calls[1].args[2] == "BUY"
    assert calls[1].kwargs["reduce_only"] is True
    assert calls[1].kwargs["price"] is not None
    assert float(calls[0].args[3]) * 100 <= 25
    assert engine.store.trades()[0]["status"] == "open"
    assert engine.store.trades()[0]["tp_status"] is None
    engine.reconcile()
    assert engine.store.trades()[0]["tp_status"] == "NEW"
    assert engine.store.trades()[0]["last_reconciled_at"]


def test_duplicate_coin_and_slot_limit(tmp_path):
    engine, broker = engine_at(tmp_path, 3)
    enter(engine, broker)
    assert (
        engine._enter(signal_for(engine, "two"), broker.account()) == "duplicate_symbol"
    )
    enter(engine, broker, "two", "DEFUSDT")
    enter(engine, broker, "three", "GHIUSDT")
    assert (
        engine._enter(signal_for(engine, "four", "JKLUSDT"), broker.account())
        == "position_limit"
    )


def test_exchange_minimum_never_increases_budget(tmp_path):
    engine, broker = engine_at(tmp_path)
    broker.get_symbol_rules.return_value["min_notional"] = 100
    assert enter(engine, broker) == "exchange_minimum_or_precision"
    broker.submit.assert_not_called()


def test_unknown_entry_response_reconciles_without_second_entry(tmp_path):
    engine, broker = engine_at(tmp_path)
    real_submit = broker.submit

    def ambiguous(*args, **kwargs):
        result = real_submit(*args, **kwargs)
        if args[2] == "SELL":
            raise ExchangeError(503, True)
        return result

    broker.submit = Mock(side_effect=ambiguous)
    assert enter(engine, broker) == "submitted"
    engine.reconcile()
    assert sum(c.args[2] == "SELL" for c in broker.submit.call_args_list) == 1
    assert engine.store.trades()[0]["tp_id"]


def test_restart_restores_tp_and_peak(tmp_path):
    engine, broker = engine_at(tmp_path)
    enter(engine, broker)
    engine._account()
    peak = engine.store.get("equity_peak")
    restarted = ExecutionEngine(engine.app_settings, engine.db_path, broker=broker)
    restarted.reconcile()
    assert len(broker.submit.call_args_list) == 2
    assert restarted.store.get("equity_peak") == peak


def test_drawdown_pause_survives_restart_and_preserves_tp(tmp_path):
    engine, broker = engine_at(tmp_path)
    enter(engine, broker)
    engine._account()
    broker.data["wallet"] = 400
    assert engine._account()["drawdown"] == pytest.approx(0.2)
    engine._commands()
    engine.reconcile()
    assert len(broker.open_orders()) == 1
    assert len(broker.get_open_positions()) == 1
    assert engine.store.get("pause")["paused"]
    engine.store.enqueue("resume", {})
    engine._commands()
    assert engine.store.get("pause")["paused"]
    assert engine.store.get("equity_peak") == 500
    broker.data["wallet"] = 350
    assert engine._account()["equity"] == 350


def test_pause_command_never_cancels_tp(tmp_path):
    engine, broker = engine_at(tmp_path)
    enter(engine, broker)
    engine.store.enqueue("pause", {})
    engine._commands()
    assert len(broker.open_orders()) == 1


def test_manual_close_cancel_then_reduce_only(tmp_path):
    engine, broker = engine_at(tmp_path)
    enter(engine, broker)
    trade = engine.store.trades()[0]
    engine.store.enqueue("close", {"trade_id": trade["id"], "confirm": True})
    engine._commands()  # request cancel
    engine._commands()  # confirm cancel, close exact remaining quantity
    engine.reconcile()
    assert not broker.get_open_positions()
    assert not broker.open_orders()
    assert engine.store.trades(False)[0]["status"] == "closed"
    assert broker.submit.call_args.kwargs["reduce_only"]


def test_missing_tp_blocks_new_entries(tmp_path):
    engine, broker = engine_at(tmp_path)
    enter(engine, broker)
    trade = engine.store.trades()[0]
    del broker.data["orders"][trade["tp_id"]]
    engine.reconcile()
    assert engine.store.get("pause")["reason"] == "tp_status_unknown"
    assert len(broker.submit.call_args_list) == 2


def test_expired_ineligible_and_wrong_manifest_never_trade(tmp_path):
    engine, broker = engine_at(tmp_path)
    signal = signal_for(engine)
    signal.eligible = False
    assert engine._enter(signal, broker.account()) == "ineligible"
    signal.eligible = True
    signal.expires_at = utc_now() - timedelta(seconds=1)
    assert engine._enter(signal, broker.account()) == "expired_or_future_signal"
    signal = signal_for(engine)
    signal.manifest_id = "a" * 64
    assert engine._enter(signal, broker.account()) == "manifest_mismatch"
    broker.submit.assert_not_called()


def test_environments_and_secrets_never_follow_arbitrary_url():
    config = ExecutionConfig(
        environment="demo",
        base_url="https://attacker.example",
        api_key="secret",
        api_secret="verysecret",
    )
    assert BinanceExecutionClient(config).base_url == "https://demo-fapi.binance.com"
    assert "verysecret" not in repr(config)
    assert "api_key" not in config.model_dump()
    client = BinanceExecutionClient(ExecutionConfig())
    with pytest.raises(ValueError, match="simulation_cannot"):
        client._request("POST", "/fapi/v1/order")


def test_private_live_mutations_blocked_without_activation():
    config = ExecutionConfig(
        environment="live", live_api_key="test", live_api_secret="test"
    )
    with pytest.raises(ValueError, match="live_not_activated"):
        BinanceExecutionClient(config).submit("ABCUSDT", "id", "SELL", 1)


def test_rule_fetch_failures_never_use_fallback():
    client = BinanceExecutionClient(ExecutionConfig())
    with patch.object(client, "_request", side_effect=ExchangeError(429)):
        with pytest.raises(ExchangeError):
            client.get_symbol_rules("ABCUSDT")


def test_only_order_not_found_is_treated_as_absent():
    client = BinanceExecutionClient(ExecutionConfig(environment="demo"))
    with patch.object(client, "_request", side_effect=ExchangeError(-2013)):
        assert client.order("ABCUSDT", "id") is None
    with patch.object(client, "_request", side_effect=ExchangeError(503, True)):
        with pytest.raises(ExchangeError):
            client.order("ABCUSDT", "id")


def test_snapshot_roundtrip_preserves_journal_and_detects_tampering(tmp_path):
    from dao_vang.execution.archive import capture_runtime, restore_runtime

    engine, broker = engine_at(tmp_path / "data")
    enter(engine, broker)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.json").write_text('{"v":1}')
    capture_runtime(tmp_path / "data", artifacts, tmp_path / "snapshot")
    restore_runtime(tmp_path / "snapshot", tmp_path / "restored")
    from dao_vang.execution.store import ExecutionStore

    restored = ExecutionStore(
        tmp_path / "restored/data/execution/simulation/state.sqlite3"
    )
    assert restored.trades() == engine.store.trades()
    (tmp_path / "snapshot/artifacts/model.json").write_text("changed")
    with pytest.raises(ValueError, match="checksum"):
        restore_runtime(tmp_path / "snapshot", tmp_path / "bad")


def test_poll_end_to_end_is_idempotent_and_disabled_engine_never_calls_broker(tmp_path):
    engine, broker = engine_at(tmp_path)
    signal = signal_for(engine)
    with (
        patch.object(broker, "sync"),
        patch.object(engine, "load_manifest", return_value=engine.manifest),
        patch("dao_vang.execution.engine.scanner_signals", return_value=[signal]),
    ):
        engine.poll_signals()
        engine.poll_signals()
    assert engine.store.get("heartbeat")["healthy"]
    assert len(broker.submit.call_args_list) == 2
    assert len(engine.store.trades()) == 1
    engine.settings.enabled = False
    with patch.object(broker, "preflight") as preflight:
        engine.poll_signals()
        preflight.assert_not_called()


def test_partial_tp_retains_remaining_limit_and_never_opens_long(tmp_path):
    engine, broker = engine_at(tmp_path)
    enter(engine, broker)
    trade = engine.store.trades()[0]
    order = broker.data["orders"][trade["tp_id"]]
    quantity = float(order["origQty"]) / 2
    order.update(status="PARTIALLY_FILLED", executedQty=str(quantity))
    broker.data["positions"]["ABCUSDT"]["positionAmt"] += quantity
    broker.data["fills"][order["orderId"]] = [
        {
            "id": "partial",
            "qty": str(quantity),
            "price": order["price"],
            "commission": "0.001",
            "commissionAsset": "USDT",
            "time": int(utc_now().timestamp() * 1000),
        }
    ]
    engine.reconcile()
    engine.reconcile()
    assert len(broker.submit.call_args_list) == 2
    current = engine.store.trades()[0]
    assert current["remaining_qty"] == pytest.approx(quantity)
    assert len(current["exit_fills"]) == 1


def test_restore_install_pauses_and_can_rollback_complete_state(tmp_path):
    from dao_vang.execution.archive import (
        capture_runtime,
        install_runtime,
        rollback_runtime,
    )

    engine, broker = engine_at(tmp_path / "data")
    enter(engine, broker)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    capture_runtime(tmp_path / "data", artifacts, tmp_path / "snapshot")
    engine.store.set("equity_peak", 555)
    install_runtime(
        tmp_path / "snapshot", tmp_path / "data", artifacts, tmp_path / "rollback"
    )
    assert engine.store.get("pause")["reason"] == "restored_requires_review"
    rollback_runtime(tmp_path / "rollback", tmp_path / "data", artifacts)
    assert engine.store.get("equity_peak") == 555


def test_stop_loss_triggers_and_closes_trade(tmp_path):
    engine, broker = engine_at(tmp_path)
    engine.settings.enable_stop_loss = True
    engine.settings.sl_max_loss_usdt = 5.0
    enter(engine, broker)
    trade = engine.store.trades()[0]
    assert trade["status"] == "open"

    # Price pumps violently from 100 to 130
    broker.data["positions"]["ABCUSDT"]["markPrice"] = 130.0
    # First reconcile: detects SL, cancels active TP order
    engine.reconcile()
    trade = engine.store.trades()[0]
    assert "stop_loss" in trade.get("auto_close_pending", "")

    # Second reconcile: TP is now CANCELED, submits market BUY reduce_only
    engine.reconcile()
    trade = engine.store.trades()[0]
    assert trade.get("close_id") is not None
    assert "stop_loss" in trade.get("auto_close_reason", "")
    last_call = broker.submit.call_args_list[-1]
    assert last_call.args[2] == "BUY"
    assert last_call.kwargs["reduce_only"] is True


def test_trailing_tp_triggers_and_locks_profit(tmp_path):
    engine, broker = engine_at(tmp_path)
    engine.settings.enable_trailing_tp = True
    engine.settings.trailing_trigger_atr = 1.5
    engine.settings.trailing_callback_atr = 1.0
    enter(engine, broker)  # Entry at 100, ATR=2.0

    # Price drops strongly to 95 (favorable drop = 5.0 > 1.5 * 2.0 = 3.0 ATR)
    broker.data["positions"]["ABCUSDT"]["markPrice"] = 95.0
    engine.reconcile()
    trade = engine.store.trades()[0]
    assert trade["min_favorable_price"] == 95.0
    assert trade.get("auto_close_pending") is None

    # Price bounces back to 97.2 (bounce = 2.2 > 1.0 * 2.0 = 2.0 ATR callback)
    broker.data["positions"]["ABCUSDT"]["markPrice"] = 97.2
    engine.reconcile()
    trade = engine.store.trades()[0]
    assert "trailing_tp_locked" in trade.get("auto_close_pending", "")

    # Reconcile again to execute close after TP cancellation
    engine.reconcile()
    trade = engine.store.trades()[0]
    assert "trailing_tp_locked" in trade.get("auto_close_reason", "")
    assert trade.get("close_id") is not None


def test_max_hold_hours_exits(tmp_path):
    import time

    engine, broker = engine_at(tmp_path)
    engine.settings.max_hold_hours = 24
    enter(engine, broker)
    trade = engine.store.trades()[0]

    # Simulate 25 hours elapsed
    trade["entry_time_ms"] = int((time.time() - 25 * 3600) * 1000)
    engine.store.trade(trade)

    engine.reconcile()
    trade = engine.store.trades()[0]
    assert "max_hold_hours" in trade.get("auto_close_pending", "")

    engine.reconcile()
    trade = engine.store.trades()[0]
    assert "max_hold_hours" in trade.get("auto_close_reason", "")
    assert trade.get("close_id") is not None


def test_price_confirmation_guard_rejects_pumping_asset(tmp_path):
    engine, broker = engine_at(tmp_path)
    engine.settings.require_price_confirmation = True

    # Current ask is 105.0, reference price is 100.0 (5% higher, pump in progress)
    broker.quote.return_value = {
        "bid": 104.9,
        "ask": 105.0,
        "bids": [[104.9, 100]],
        "asks": [[105.0, 100]],
    }
    sig = signal_for(engine, "pump_test", "ABCUSDT")
    sig.reference_price = 100.0

    result = engine._enter(sig, broker.account())
    assert result == "price_not_confirmed_down"
    assert len(engine.store.trades()) == 0

