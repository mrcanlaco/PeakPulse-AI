import json
from unittest.mock import patch

import pytest

from dao_vang.config.settings import AccountMonitorConfig, AppSettings
from dao_vang.execution.account_credentials import save_credentials
from dao_vang.execution.account_monitor import (
    AccountMonitor,
    BinanceAccountReader,
    monitor_credentials,
    monitor_store,
)
from dao_vang.execution.binance_api import ExchangeError
from dao_vang.execution.engine import ExecutionEngine
from dao_vang.web.execution_api import command
from dao_vang.web.execution_dashboard import dashboard


def settings_at(tmp_path):
    settings = AppSettings(_env_file=None)
    settings.paths.data_dir = tmp_path
    settings.account_monitor = AccountMonitorConfig(
        enabled=True,
        api_key="K" * 64,
        api_secret="S" * 64,
        credentials_file=tmp_path / ".env.binance-readonly",
    )
    return settings


def replies(_client, method, endpoint, *args, **kwargs):
    assert method == "GET"
    if endpoint == "/fapi/v1/time":
        return {"serverTime": 0}
    if endpoint == "/fapi/v3/account":
        return {
            "assets": [
                {
                    "asset": "USDT",
                    "walletBalance": "100",
                    "unrealizedProfit": "-2",
                    "marginBalance": "98",
                    "availableBalance": "90",
                    "maintMargin": "1",
                }
            ]
        }
    if endpoint == "/fapi/v1/multiAssetsMargin":
        return {"multiAssetsMargin": True}
    if endpoint == "/fapi/v1/positionSide/dual":
        return {"dualSidePosition": True}
    if endpoint == "/fapi/v3/positionRisk":
        return [
            {
                "symbol": "ABCUSDT",
                "positionSide": side,
                "positionAmt": qty,
                "markPrice": "100",
                "entryPrice": "100",
                "unRealizedProfit": "-1",
            }
            for side, qty in [("LONG", "1"), ("SHORT", "-1")]
        ]
    if endpoint == "/fapi/v1/openOrders":
        return [{"orderId": 1, "symbol": "ABCUSDT", "side": "BUY"}]
    if endpoint == "/fapi/v1/income":
        return [
            {
                "incomeType": "COMMISSION",
                "tranId": 1,
                "symbol": "ABCUSDT",
                "asset": "USDT",
                "income": "-0.02",
                "time": 10,
            },
            {
                "incomeType": "FUNDING_FEE",
                "tranId": 2,
                "symbol": "ABCUSDT",
                "asset": "USDT",
                "income": "0.01",
                "time": 20,
            },
        ]
    raise AssertionError(endpoint)


def test_read_only_adapter_blocks_every_mutation_even_if_activation_is_changed():
    reader = BinanceAccountReader("K" * 64, "S" * 64)
    reader.config.live_activated = True
    with patch("urllib.request.urlopen") as network:
        for method in ("POST", "PUT", "DELETE", "PATCH"):
            with pytest.raises(ValueError, match="read_only"):
                reader._request(method, "/fapi/v1/order")
        with pytest.raises(ValueError, match="read_only"):
            reader._request("GET", "/sapi/v1/asset/transfer")
        with pytest.raises(ValueError, match="read_only"):
            reader.listen_key("POST")
        network.assert_not_called()


def test_monitor_reads_real_mode_without_changing_it_and_preserves_hedge_positions(
    tmp_path,
):
    settings = settings_at(tmp_path)
    observer = AccountMonitor(settings)
    with patch(
        "dao_vang.execution.binance_api.BinanceExecutionClient._request", new=replies
    ):
        assert observer.poll()
        assert observer.poll()
    result = dashboard(settings)
    assert result["read_only"] and result["environment"] == "live"
    assert result["account"]["equity"] == 98
    assert result["account"]["peak"] == 98  # Never seed the real account with 500.
    assert result["account_mode"] == {"hedge": True, "multi_assets": True}
    assert len(result["unmanaged_positions"]) == 2
    assert result["open_orders"][0]["orderId"] == 1
    assert result["totals"]["recorded_fees"] == 0.02
    assert result["totals"]["recorded_funding"] == 0.01
    assert not result["enabled"] and not result["live_gate"]["eligible"]
    assert result["progress"]["independent_events"] == 0
    assert "K" * 64 not in json.dumps(result) and "S" * 64 not in json.dumps(result)
    assert not (tmp_path / "execution" / "live").exists()


def test_monitor_blocks_ui_commands_and_executor_even_if_enabled(tmp_path):
    settings = settings_at(tmp_path)
    settings.execution.enabled = True
    settings.execution.live_activated = True
    for action in ("pause", "resume", "close"):
        with pytest.raises(ValueError, match="read_only"):
            command(settings, action, {"confirm": True})
    engine = ExecutionEngine(settings, tmp_path / "scanner.duckdb")
    with pytest.raises(ValueError, match="read_only"):
        engine.connect()
    assert engine._enter(None, None) == "account_monitor_read_only"
    assert monitor_store(settings).commands() == []


def test_failed_connection_retains_last_balance_but_not_healthy_and_sanitizes_errors(
    tmp_path,
):
    settings = settings_at(tmp_path)
    observer = AccountMonitor(settings)
    with patch(
        "dao_vang.execution.binance_api.BinanceExecutionClient._request", new=replies
    ):
        assert observer.poll()
    with patch(
        "dao_vang.execution.binance_api.BinanceExecutionClient._request",
        side_effect=RuntimeError("secret signed URL"),
    ):
        assert not observer.poll()
    result = dashboard(settings)
    assert result["account"]["equity"] == 98
    assert not result["healthy"]
    assert result["connection_error"] == "account_monitor_unavailable"
    assert "secret signed URL" not in json.dumps(result)


def test_missing_keys_and_rotated_account_never_show_previous_account(tmp_path):
    settings = settings_at(tmp_path)
    old = monitor_store(settings)
    old.set("account", {"equity": 123})
    settings.account_monitor.api_key = "Z" * 64
    assert monitor_store(settings).path != old.path
    assert dashboard(settings)["account"] is None
    settings.account_monitor.api_key = None
    settings.account_monitor.api_secret = None
    assert not AccountMonitor(settings).poll()
    assert dashboard(settings)["connection_error"] == "monitor_credentials_missing"


def test_optional_income_error_does_not_hide_successful_account_read(tmp_path):
    settings = settings_at(tmp_path)

    def fetch(client, method, endpoint, *args, **kwargs):
        if endpoint == "/fapi/v1/income":
            raise ExchangeError(-2015)
        return replies(client, method, endpoint, *args, **kwargs)

    with patch(
        "dao_vang.execution.binance_api.BinanceExecutionClient._request", new=fetch
    ):
        assert AccountMonitor(settings).poll()
    result = dashboard(settings)
    assert result["healthy"] and result["account_fresh"]
    assert not result["income_health"]["healthy"]
    assert result["totals"]["recorded_fees"] is None


def test_credential_file_private_roundtrip_and_no_overwrite(tmp_path):
    settings = settings_at(tmp_path)
    settings.account_monitor.api_key = None
    settings.account_monitor.api_secret = None
    path = settings.account_monitor.credentials_file
    save_credentials(path, "K" * 64, "S" * 64)
    assert monitor_credentials(settings) == ("K" * 64, "S" * 64)
    with pytest.raises(ValueError, match="exists"):
        save_credentials(path, "X" * 64, "Y" * 64)
    with pytest.raises(ValueError, match="hmac"):
        save_credentials(path, "line\nbreak", "S" * 64, replace=True)
    assert not list(tmp_path.glob(".binance-private-*"))
