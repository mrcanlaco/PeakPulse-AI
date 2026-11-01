"""Unit tests for access password authentication and endpoint protection."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from dao_vang.web.api_server import APIHandler


def test_check_auth_methods():
    handler = object.__new__(APIHandler)
    handler.headers = {}
    handler.path = "/api/status"
    handler.client_address = ("127.0.0.1", 1234)

    with patch("dao_vang.web.api_server._settings.web.access_password", "test-password"):
        # Passwords in headers, cookies and URLs are never accepted.
        assert APIHandler._check_auth(handler) is False
        handler.headers = {"X-Access-Password": "test-password"}
        assert APIHandler._check_auth(handler) is False
        handler.headers = {"Authorization": "Bearer test-password"}
        assert APIHandler._check_auth(handler) is False
        handler.headers = {"Cookie": "dao_vang_password=test-password"}
        assert APIHandler._check_auth(handler) is False
        handler.headers = {}
        handler.path = "/api/signals?token=test-password"
        assert APIHandler._check_auth(handler) is False


def test_check_auth_accepts_signed_session_cookie():
    handler = object.__new__(APIHandler)
    handler.headers = {}
    handler.path = "/api/status"
    handler.client_address = ("127.0.0.1", 1234)

    with patch("dao_vang.web.api_server._settings.web.access_password", "test-password"):
        token = APIHandler._make_session_token(handler)
        handler.headers = {"Cookie": f"dao_vang_session={token}"}
        assert APIHandler._check_auth(handler) is True


def test_verify_auth_password_success():
    handler = object.__new__(APIHandler)
    handler.wfile = MagicMock()
    handler._set_headers = MagicMock()
    handler.headers = {}
    handler.client_address = ("127.0.0.1", 1234)

    with patch("dao_vang.web.api_server._settings.web.access_password", "test-password"):
        APIHandler.verify_auth_password(handler, {"password": "test-password"})

        handler._set_headers.assert_called_once()
        args, kwargs = handler._set_headers.call_args
        assert args[0] == 200
        assert "Set-Cookie" in kwargs.get("extra_headers", {})

        written = handler.wfile.write.call_args[0][0].decode("utf-8")
        data = json.loads(written)
        assert data.get("ok") is True
        assert data.get("authenticated") is True
        assert "token" not in data
        cookie = kwargs["extra_headers"]["Set-Cookie"]
        assert "dao_vang_session=" in cookie
        assert "HttpOnly" in cookie
        assert "test-password" not in cookie


def test_verify_auth_password_failure():
    handler = object.__new__(APIHandler)
    handler.wfile = MagicMock()
    handler._set_headers = MagicMock()
    handler.headers = {}
    handler.client_address = ("127.0.0.1", 1235)

    with patch("dao_vang.web.api_server._settings.web.access_password", "test-password"):
        APIHandler.verify_auth_password(handler, {"password": "wrong"})

        handler._set_headers.assert_called_once()
        args, _ = handler._set_headers.call_args
        assert args[0] == 401

        written = handler.wfile.write.call_args[0][0].decode("utf-8")
        data = json.loads(written)
        assert data.get("ok") is False
        assert data.get("authenticated") is False


def test_verify_auth_password_fails_closed_when_unconfigured():
    handler = object.__new__(APIHandler)
    handler.wfile = MagicMock()
    handler._set_headers = MagicMock()
    handler.headers = {}
    handler.client_address = ("127.0.0.1", 1236)

    with patch("dao_vang.web.api_server._settings.web.access_password", None):
        APIHandler.verify_auth_password(handler, {"password": "anything"})

    args, _ = handler._set_headers.call_args
    assert args[0] == 503
    data = json.loads(handler.wfile.write.call_args[0][0].decode("utf-8"))
    assert data["ok"] is False


def test_verify_auth_password_rate_limits_repeated_failures():
    handler = object.__new__(APIHandler)
    handler.wfile = MagicMock()
    handler._set_headers = MagicMock()
    handler.headers = {}
    handler.client_address = ("127.0.0.1", 1237)

    with (
        patch("dao_vang.web.api_server._settings.web.access_password", "test-password"),
        patch("dao_vang.web.api_server._AUTH_FAILURES", {}),
    ):
        for _ in range(5):
            APIHandler.verify_auth_password(handler, {"password": "wrong"})
        APIHandler.verify_auth_password(handler, {"password": "wrong"})

    assert handler._set_headers.call_args.args[0] == 429


def test_public_guest_vs_admin_only_route_matrix():
    for public_path in (
        "/api/status",
        "/api/fibo-short/snapshot",
        "/api/fibo-short/paper-oos",
        "/api/execution/dashboard",
        "/api/execution/status",
        "/api/signals",
        "/api/candidates",
        "/api/scanner/telemetry",
    ):
        assert APIHandler._is_admin_only_get_path(public_path) is False

    for admin_path in (
        "/api/ai/config",
        "/api/ai/settings",
        "/api/tracking-watchlist",
        "/api/system/update-logs",
        "/api/updater/logs",
    ):
        assert APIHandler._is_admin_only_get_path(admin_path) is True


def test_auth_status_reports_guest_and_admin_roles():
    import io

    handler = object.__new__(APIHandler)
    handler.headers = {}
    handler.path = "/api/auth/status"
    handler.client_address = ("127.0.0.1", 1234)
    handler._set_headers = MagicMock()
    handler.wfile = io.BytesIO()

    with patch("dao_vang.web.api_server._settings.web.access_password", "test-password"):
        APIHandler.get_auth_status(handler)
        guest_payload = json.loads(handler.wfile.getvalue().decode("utf-8"))
        assert guest_payload["auth_required"] is False
        assert guest_payload["admin_auth_required"] is True
        assert guest_payload["authenticated"] is False
        assert guest_payload["role"] == "guest"

        token = APIHandler._make_session_token(handler)
        handler.headers = {"Cookie": f"dao_vang_session={token}"}
        handler.wfile = io.BytesIO()
        APIHandler.get_auth_status(handler)
        admin_payload = json.loads(handler.wfile.getvalue().decode("utf-8"))
        assert admin_payload["authenticated"] is True
        assert admin_payload["role"] == "admin"
