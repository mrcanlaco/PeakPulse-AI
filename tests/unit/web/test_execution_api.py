import io
import json
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest

from dao_vang.config.settings import AppSettings, ExecutionConfig
from dao_vang.execution.contracts import utc_now
from dao_vang.web.api_server import APIHandler
from dao_vang.web.execution_api import command, execution_store, status


def settings_at(tmp_path):
    settings = AppSettings(_env_file=None)
    settings.paths.data_dir = tmp_path
    settings.execution = ExecutionConfig(enabled=True)
    return settings


def handler(path, body=None):
    instance = object.__new__(APIHandler)
    instance.path = path
    instance.headers = {}
    instance.wfile = io.BytesIO()
    instance._set_headers = Mock()
    instance._check_auth = Mock(return_value=True)
    instance._read_json_body = Mock(return_value=body or {})
    instance._send_unauthorized = Mock()
    return instance


def test_status_excludes_secrets_and_marks_stale_account(tmp_path):
    settings = settings_at(tmp_path)
    settings.execution.api_key = "secret"
    store = execution_store(settings)
    store.set(
        "heartbeat",
        {"at": (utc_now() - timedelta(minutes=5)).isoformat(), "healthy": True},
    )
    result = status(settings)
    assert not result["healthy"]
    assert "secret" not in json.dumps(result)
    assert not result["live_gate"]["eligible"]


def test_commands_do_not_call_exchange_and_require_close_confirmation(tmp_path):
    settings = settings_at(tmp_path)
    store = execution_store(settings)
    store.trade({"id": "one", "symbol": "ABCUSDT", "status": "open"})
    assert command(settings, "pause", {})["status"] == "queued"
    assert store.trades()[0]["status"] == "open"
    with pytest.raises(ValueError, match="confirmation"):
        command(settings, "close", {"trade_id": "one"})
    assert (
        command(settings, "close", {"trade_id": "one", "confirm": True})["status"]
        == "queued"
    )
    with pytest.raises(ValueError):
        command(settings, "activate-live", {})


def test_execution_endpoints_require_auth_and_reject_foreign_origin(tmp_path):
    settings = settings_at(tmp_path)
    instance = handler("/api/execution/pause")
    instance._check_auth.return_value = False
    with patch("dao_vang.web.api_server._settings", settings):
        APIHandler.do_POST(instance)
    instance._send_unauthorized.assert_called_once()
    assert not execution_store(settings).commands()
    instance = handler("/api/execution/pause")
    instance.headers = {"Origin": "https://foreign.example"}
    with patch("dao_vang.web.api_server._settings", settings):
        APIHandler.do_POST(instance)
    assert instance._set_headers.call_args.args[0] == 403
    assert not execution_store(settings).commands()


def test_authenticated_status_and_pause_are_integrated(tmp_path):
    settings = settings_at(tmp_path)
    with patch("dao_vang.web.api_server._settings", settings):
        get = handler("/api/execution/status")
        APIHandler._do_GET(get)
        assert json.loads(get.wfile.getvalue())["environment"] == "simulation"
        post = handler("/api/execution/pause")
        APIHandler.do_POST(post)
        assert post._set_headers.call_args.kwargs["content_length"] > 0
        assert post._set_headers.call_args.args[0] == 202
    assert execution_store(settings).commands()[0]["action"] == "pause"


def test_dashboard_route_requires_auth_and_validates_period(tmp_path):
    settings = settings_at(tmp_path)
    with patch("dao_vang.web.api_server._settings", settings):
        get = handler("/api/execution/dashboard?period=30d")
        get._check_auth.return_value = False
        APIHandler._do_GET(get)
        get._send_unauthorized.assert_called_once()
        assert not get.wfile.getvalue()
        invalid = handler("/api/execution/dashboard?period=all")
        APIHandler._do_GET(invalid)
        assert invalid._set_headers.call_args.args[0] == 400
        valid = handler("/api/execution/dashboard?period=24h")
        APIHandler._do_GET(valid)
        result = json.loads(valid.wfile.getvalue())
        assert result["period"] == "24h"
        assert result["account"] is None
    assert not execution_store(settings).commands()
