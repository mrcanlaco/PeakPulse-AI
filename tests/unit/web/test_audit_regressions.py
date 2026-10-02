"""Regression checks for issues found in the local/GCP audit."""
import http.client
import io
import json
import threading
from contextlib import closing
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from unittest.mock import MagicMock

import pytest

from dao_vang.scanner.healthcheck import heartbeat_is_healthy
from dao_vang.web import api_server as api
from dao_vang.web.dismissals import SignalDismissals


@pytest.fixture
def web(tmp_path, monkeypatch):
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html>Dashboard</html>", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("outside-dist-sentinel", encoding="utf-8")
    monkeypatch.setattr(api, "DIST_DIR", dist)
    monkeypatch.setattr(api._settings.web, "access_password", "audit-password")
    monkeypatch.setattr(api._settings.web, "public_url", "http://localhost")
    monkeypatch.setattr(api, "_AUTH_FAILURES", {})
    monkeypatch.setattr(api, "_dismissals", SignalDismissals(tmp_path / "dismissals.json"))
    snapshot = tmp_path / "candidate_snapshot.json"
    snapshot.write_text(json.dumps({"rows": [], "generated_at": datetime.now(timezone.utc).isoformat()}))
    monkeypatch.setattr(api, "CANDIDATE_SNAPSHOT_PATH", snapshot)
    stats = tmp_path / "system_data_stats.json"
    stats.write_text(json.dumps({"data_stats": [
        {"table": name, "max_time": datetime.now(timezone.utc).isoformat()}
        for name in ("kline", "raw_timeline", "feature_results", "open_interest")
    ], "generated_at": datetime.now(timezone.utc).isoformat()}))
    monkeypatch.setattr(api, "SYSTEM_STATS_PATH", stats)
    server = ThreadingHTTPServer(("127.0.0.1", 0), api.APIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def call(port, path, *, method="GET", body=None, headers=None):
    with closing(http.client.HTTPConnection("127.0.0.1", port, timeout=3)) as connection:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read(), dict(response.getheaders())


@pytest.mark.parametrize("path", [
    "/%2e%2e/%2e%2e/pyproject.toml",
    "/../../pyproject.toml",
    "/..%5c..%5cpyproject.toml",
    "/%00",
])
def test_static_cannot_escape_frontend(web, path):
    status, body, _ = call(web, path)
    assert status == 404
    assert b"outside-dist-sentinel" not in body


def test_spa_and_missing_asset(web):
    assert call(web, "/")[0] == 200
    assert call(web, "/dashboard")[0] == 200
    assert call(web, "/assets/missing.js")[0] == 404


@pytest.mark.parametrize("body", [b"{", b"[]", b"null", b'"string"', b"\xff"])
def test_invalid_login_body_returns_json_error(web, body):
    status, response, _ = call(web, "/api/auth/verify", method="POST", body=body)
    assert status == 400
    assert "error" in json.loads(response)


@pytest.mark.parametrize("length,expected", [("bad", 400), ("-1", 400), ("1048577", 413)])
def test_request_body_limits(web, length, expected):
    status, _, _ = call(web, "/api/auth/verify", method="POST", body=b"", headers={"Content-Length": length})
    assert status == expected


def test_unicode_password_and_protected_endpoint(web, monkeypatch):
    monkeypatch.setattr(api._settings.web, "access_password", "mật-khẩu-đảo-vàng")
    status, _, headers = call(web, "/api/auth/verify", method="POST",
                              body=json.dumps({"password": "mật-khẩu-đảo-vàng"}))
    assert status == 200
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    status, body, _ = call(web, "/api/auth/status", headers={"Cookie": cookie})
    assert status == 200
    assert json.loads(body)["authenticated"]
    assert call(web, "/api/watchlist/add", method="POST", body="{}")[0] == 401


def test_readiness_requires_fresh_successful_scanner_heartbeat(
    web,
    monkeypatch,
    tmp_path,
):
    heartbeat_path = tmp_path / "scanner_heartbeat.json"
    monkeypatch.setattr(api, "HEARTBEAT_PATH", heartbeat_path)
    monkeypatch.setattr(
        api,
        "_disk_readiness",
        lambda path: {
            "healthy": True,
            "status": "ok",
            "reason": "ok",
            "used_percent": 50.0,
            "free_bytes": 10 * 1024**3,
        },
    )

    status, body, _ = call(web, "/api/ready")
    assert status == 503
    assert json.loads(body)["checks"]["scanner"]["reason"] == "heartbeat_missing"
    assert call(web, "/api/ready", method="HEAD")[0] == 503

    heartbeat = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "last_cycle_status": "ok",
    }
    heartbeat_path.write_text(json.dumps(heartbeat), encoding="utf-8")
    status, body, _ = call(web, "/api/ready")
    assert status == 200
    assert json.loads(body)["status"] == "ok"
    assert call(web, "/api/ready", method="HEAD")[0] == 200

    api.CANDIDATE_SNAPSHOT_PATH.write_text(json.dumps({"rows": [], "generated_at":
        (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()}))
    status, body, _ = call(web, "/api/ready")
    assert status == 503
    assert json.loads(body)["checks"]["scanner"]["reason"] == "snapshot_stale"

    heartbeat["last_cycle_status"] = "failed"
    heartbeat_path.write_text(json.dumps(heartbeat), encoding="utf-8")
    status, body, _ = call(web, "/api/ready")
    assert status == 503
    assert json.loads(body)["checks"]["scanner"]["reason"] == "last_cycle_failed"
    assert call(web, "/api/ready", method="HEAD")[0] == 503


def test_readiness_fails_when_disk_space_is_critical(web, monkeypatch, tmp_path):
    heartbeat_path = tmp_path / "scanner_heartbeat.json"
    heartbeat_path.write_text(
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "running",
                "last_cycle_status": "ok",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(api, "HEARTBEAT_PATH", heartbeat_path)
    monkeypatch.setattr(
        api,
        "_disk_readiness",
        lambda path: {
            "healthy": False,
            "status": "error",
            "reason": "disk_space_critical",
            "used_percent": 95.0,
            "free_bytes": 1024,
        },
    )

    status, body, _ = call(web, "/api/ready")
    assert status == 503
    disk = json.loads(body)["checks"]["disk"]
    assert disk["reason"] == "disk_space_critical"


def test_klines_route_has_handler_and_bounded_limit(web, monkeypatch):
    from dao_vang.data.collectors import binance_client
    client = MagicMock()
    client.get.return_value = [[1_700_000_000_000, "1", "2", "0.5", "1.5", "100"]]
    monkeypatch.setattr(binance_client, "BinanceClient", lambda: client)
    monkeypatch.setattr(api.APIHandler, "_check_auth", lambda self: True)
    status, body, _ = call(web, "/api/coin/BTCUSDT/klines?interval=5m&limit=99999")
    assert status == 200
    assert len(json.loads(body)["klines"]) == 1
    assert client.get.call_args.args[1]["limit"] == 1500


def test_legacy_shap_route_fails_closed_without_fabricated_values(
    web,
    monkeypatch,
):
    monkeypatch.setattr(api.APIHandler, "_check_auth", lambda self: True)

    status, body, _ = call(web, "/api/coin/BTCUSDT/shap")

    assert status == 501
    payload = json.loads(body)
    assert payload["available"] is False
    assert payload["attribution_method"] == "none"
    assert payload["reason"] == "shap_not_computed"
    assert "values" not in payload


def test_component_drivers_are_weighted_scores_not_shap_values():
    drivers = api._component_feature_drivers(
        [
            {
                "name": "funding_spike",
                "weighted_score": 15,
                "explanation": "Measured component explanation",
            },
            {"name": "invalid", "weighted_score": "not-a-number"},
        ]
    )

    assert drivers[0] == {
        "feature": "Funding Spike",
        "impact_score": 0.15,
        "description": "Measured component explanation",
    }
    assert drivers[1]["impact_score"] == 0.0


def test_audit_does_not_invent_metrics(monkeypatch):
    store = MagicMock()
    store.stats.return_value = {"n_judged": 0, "total": 0, "hit_rate": None}
    store.precision_by_risk_level.return_value = {}
    store.lead_time_stats.return_value = {}
    monkeypatch.setattr(api, "_alert_store", store)
    monkeypatch.setattr(api, "_read_json", lambda path: {})
    handler = object.__new__(api.APIHandler)
    handler._set_headers = MagicMock()
    handler.wfile = io.BytesIO()
    handler.get_audit()
    payload = json.loads(handler.wfile.getvalue())
    assert not payload["has_enough_data"]
    assert all(value is None for value in payload["metrics"].values())
    assert payload["precision_by_risk_level"] == {}
    assert payload["lead_time"]["mean_hours"] is None
    assert not payload["validation_checks"]["point_in_time_verified"]
    assert payload["quality_gates"] == {}


def test_audit_preserves_measured_zero_and_failed_gates(monkeypatch):
    store = MagicMock()
    store.stats.return_value = {"n_judged": 0, "total": 10, "hit_rate": None}
    store.precision_by_risk_level.return_value = {"CAO": {"n_judged": 10, "n_hit": 0, "precision": 0.0}}
    store.lead_time_stats.return_value = {"mean_hours": 0.0}
    monkeypatch.setattr(api, "_alert_store", store)
    monkeypatch.setattr(api, "_read_json", lambda path: {
        "quality_gates": {"precision_gte_0_35": False},
        "regime_performance": {"NO_SAMPLES": {"precision": 0.8, "samples": 0}},
        "stress_test_events": [{"pass": True, "samples": 0}],
    })
    handler = object.__new__(api.APIHandler)
    handler._set_headers = MagicMock()
    handler.wfile = io.BytesIO()
    handler.get_audit()
    payload = json.loads(handler.wfile.getvalue())
    assert payload["metrics"]["precision"] == 0.0
    assert payload["sample_size"] == 10
    assert payload["has_enough_data"]
    assert payload["lead_time"]["mean_hours"] == 0.0
    assert payload["quality_gates"]["precision_gte_0_35"] is False
    assert payload["regime_performance"] == {}
    assert payload["stress_test_events"] == []


def test_ai_config_fails_closed_when_settings_cannot_load(monkeypatch):
    def fail_to_load_settings():
        raise RuntimeError("invalid settings")

    monkeypatch.setattr("dao_vang.config.settings.AppSettings", fail_to_load_settings)
    handler = object.__new__(api.APIHandler)
    handler._set_headers = MagicMock()
    handler.wfile = io.BytesIO()

    handler.get_ai_config()

    payload = json.loads(handler.wfile.getvalue())
    assert payload["provider"] == "unavailable"
    assert payload["enabled"] is False
    assert payload["hasApiKey"] is False
    assert payload["modelId"] == ""
    assert payload["baseUrl"] == ""
    assert payload["error"] == "settings_unavailable"


def test_dismissal_survives_restart_and_normalizes_timezone(tmp_path):
    path = tmp_path / "dismissals.json"
    SignalDismissals(path).dismiss("BTCUSDT", "2026-09-11T07:00:00+07:00")
    store = SignalDismissals(path)
    rows = [
        {"symbol": "BTCUSDT", "signal_time": "2026-09-11T00:00:00Z"},
        {"symbol": "ETHUSDT", "signal_time": "2026-09-11T00:00:00Z"},
    ]
    assert store.filter(rows) == rows[1:]


def test_dismiss_does_not_write_scanner_database(web, monkeypatch):
    monkeypatch.setattr(api.APIHandler, "_check_auth", lambda self: True)
    store = MagicMock()
    monkeypatch.setattr(api, "_alert_store", store)
    status, _, _ = call(web, "/api/alerts/dismiss", method="POST",
        body=json.dumps({"symbol": "BTCUSDT", "signal_time": "2026-09-11T00:00:00Z"}))
    assert status == 200
    store.dismiss.assert_not_called()
    assert api._dismissals.filter([{"symbol": "BTCUSDT", "signal_time": "2026-09-11T00:00:00Z"}]) == []


@pytest.mark.parametrize("age,status,cycle,expected", [
    (0, "running", "ok", True), (901, "running", "ok", False),
    (-61, "running", "ok", False), (0, "stopped", "ok", False),
    (0, "degraded", "failed", False), (0, "running", "failed", False),
])
def test_scanner_health_rejects_stale_or_failed_heartbeat(tmp_path, age, status, cycle, expected):
    now = datetime.now(timezone.utc)
    path = tmp_path / "heartbeat.json"
    path.write_text(json.dumps({"timestamp": (now - timedelta(seconds=age)).isoformat(),
                               "status": status, "last_cycle_status": cycle}), encoding="utf-8")
    assert heartbeat_is_healthy(path, now=now) is expected
