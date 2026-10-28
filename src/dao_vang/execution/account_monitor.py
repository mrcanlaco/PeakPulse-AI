"""Live account observation with an allowlist of GET-only Binance endpoints."""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time

from dotenv import dotenv_values

from dao_vang.config.settings import ExecutionConfig
from dao_vang.scanner.instance_lock import ScannerInstanceLock

from .binance_api import BinanceExecutionClient, ExchangeError
from .contracts import utc_now
from .store import ExecutionStore


def monitor_credentials(settings):
    config = settings.account_monitor
    if config.api_key and config.api_secret:
        return config.api_key, config.api_secret
    if config.credentials_file.is_file():
        values = dotenv_values(config.credentials_file, interpolate=False)
        return (
            values.get("DAO_VANG_ACCOUNT_MONITOR__API_KEY") or "",
            values.get("DAO_VANG_ACCOUNT_MONITOR__API_SECRET") or "",
        )
    return "", ""


def monitor_store(settings, credentials=None):
    key, secret = (
        credentials if credentials is not None else monitor_credentials(settings)
    )
    # Never mix observations across keys/accounts or with execution evidence.
    identity = (
        hashlib.sha256(key.encode()).hexdigest()[:24]
        if key and secret
        else "unconfigured"
    )
    return ExecutionStore(
        settings.paths.data_dir
        / "account_monitor"
        / "live"
        / identity
        / "state.sqlite3"
    )


class BinanceAccountReader(BinanceExecutionClient):
    allowed = frozenset(
        {
            "/fapi/v1/time",
            "/fapi/v3/account",
            "/fapi/v3/positionRisk",
            "/fapi/v1/openOrders",
            "/fapi/v1/openAlgoOrders",
            "/fapi/v1/positionSide/dual",
            "/fapi/v1/multiAssetsMargin",
            "/fapi/v1/income",
        }
    )

    def __init__(self, key, secret):
        super().__init__(
            ExecutionConfig(
                environment="live",
                enabled=False,
                live_activated=False,
                live_api_key=key,
                live_api_secret=secret,
            )
        )

    def _request(self, method, endpoint, params=None, auth=True, key_only=False):
        if method != "GET" or endpoint not in self.allowed:
            raise ValueError("account_monitor_read_only")
        return super()._request(method, endpoint, params, auth, key_only)


def finite(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("invalid_account_value")
    return result


def public_error(exc):
    if isinstance(exc, ExchangeError):
        return str(exc)  # Sanitized numeric Binance code, never a signed URL.
    if isinstance(exc, ValueError) and str(exc) in {
        "monitor_credentials_missing",
        "invalid_account_value",
        "usdt_balance_missing",
    }:
        return str(exc)
    return "account_monitor_unavailable"


class AccountMonitor:
    def __init__(self, settings):
        self.settings = settings
        self.stopped = threading.Event()
        self.thread: threading.Thread | None = None
        self.client = None
        self.credential_digest = None

    def poll(self):
        if not self.settings.account_monitor.enabled:
            return False
        key, secret = monitor_credentials(self.settings)
        store = monitor_store(self.settings, (key, secret))
        with ScannerInstanceLock(store.path.parent / "observer.lock"):
            try:
                if not key or not secret:
                    raise ValueError("monitor_credentials_missing")
                digest = hashlib.sha256((key + ":" + secret).encode()).hexdigest()
                if digest != self.credential_digest:
                    self.client = BinanceAccountReader(key, secret)
                    self.credential_digest = digest
                client = self.client
                if client is None:
                    raise ValueError("monitor_credentials_missing")
                client.synchronize_clock()
                value = client._request("GET", "/fapi/v3/account")
                assets = client._request("GET", "/fapi/v1/multiAssetsMargin")
                mode = client._request("GET", "/fapi/v1/positionSide/dual")
                # Report the USDT asset explicitly, not USD-equivalent multi-asset totals.
                usdt = next((a for a in value["assets"] if a["asset"] == "USDT"), None)
                if usdt is None:
                    raise ValueError("usdt_balance_missing")
                wallet = finite(usdt["walletBalance"])
                unrealized = finite(usdt["unrealizedProfit"])
                equity = finite(usdt["marginBalance"])
                peak = max(finite(store.get("equity_peak", equity)), equity)
                account = {
                    "wallet": wallet,
                    "unrealized": unrealized,
                    "equity": equity,
                    "available": finite(usdt["availableBalance"]),
                    "peak": peak,
                    "drawdown": max(0, 1 - equity / peak) if peak > 0 else 0,
                    "maintenance_margin": finite(usdt["maintMargin"]),
                    "balance_scope": "USDT",
                    "at": utc_now().isoformat(),
                }
                positions = client.get_open_positions()
                orders = client.open_orders()
                # Only persist a coherent successfully read snapshot. GET-only,
                # no preflight mutations, orders, cancels, leverage or transfers.
                with store.connect() as db:
                    for name, payload in {
                        "account": account,
                        "positions": positions,
                        "open_orders": orders,
                        "equity_peak": peak,
                        "account_mode": {
                            "hedge": mode["dualSidePosition"],
                            "multi_assets": assets["multiAssetsMargin"],
                        },
                        "heartbeat": {"healthy": True, "at": utc_now().isoformat()},
                    }.items():
                        db.execute(
                            "INSERT OR REPLACE INTO state VALUES (?,?)",
                            (name, json.dumps(payload)),
                        )
                    db.execute(
                        "INSERT INTO journal(at,kind,payload) VALUES (?,?,?)",
                        (account["at"], "equity", json.dumps(account)),
                    )
                # Income is optional to the balance read. Preserve successful
                # balances when older-income permissions/history are unavailable.
                try:
                    now_ms = int(time.time() * 1000)
                    since = max(
                        now_ms - 7 * 86400000,
                        int(store.get("income_cursor", now_ms - 7 * 86400000)) - 60000,
                    )
                    for row in client.income(since, now_ms):
                        store.money_event(
                            f"{row['incomeType']}:{row['tranId']}:{row.get('symbol', '')}:{row.get('asset', '')}",
                            str(row["time"]),
                            row["incomeType"],
                            row,
                        )
                    store.set("income_cursor", now_ms)
                    store.set(
                        "income_health", {"healthy": True, "at": utc_now().isoformat()}
                    )
                except Exception as exc:
                    store.set(
                        "income_health",
                        {
                            "healthy": False,
                            "error": public_error(exc),
                            "at": utc_now().isoformat(),
                        },
                    )
                return True
            except Exception as exc:
                store.set(
                    "heartbeat",
                    {
                        "healthy": False,
                        "error": public_error(exc),
                        "at": utc_now().isoformat(),
                    },
                )
                return False

    def run(self):
        while not self.stopped.is_set():
            try:
                self.poll()
            except Exception:
                # Other reader owns lock, or local I/O unavailable. Never leak credentials.
                pass
            self.stopped.wait(self.settings.account_monitor.poll_seconds)

    def close(self):
        self.stopped.set()


def start_account_monitor(settings):
    if not settings.account_monitor.enabled:
        return None
    monitor = AccountMonitor(settings)
    monitor.thread = threading.Thread(
        target=monitor.run, name="binance-account-readonly", daemon=True
    )
    monitor.thread.start()
    return monitor
