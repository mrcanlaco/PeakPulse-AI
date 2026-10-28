"""Read-only dashboard plus durable commands; web never submits exchange orders."""

from __future__ import annotations

from datetime import datetime

from dao_vang.execution.contracts import utc_now
from dao_vang.execution.store import ExecutionStore


def execution_store(settings):
    if settings.account_monitor.enabled:
        from dao_vang.execution.account_monitor import monitor_store

        return monitor_store(settings)
    return ExecutionStore(
        settings.paths.data_dir
        / "execution"
        / settings.execution.environment
        / "state.sqlite3"
    )


def status(settings):
    store = execution_store(settings)
    heartbeat = store.get("heartbeat", {})
    try:
        age = (utc_now() - datetime.fromisoformat(heartbeat["at"])).total_seconds()
        fresh = 0 <= age <= max(60, settings.execution.poll_seconds * 3)
    except (KeyError, TypeError, ValueError):
        age, fresh = None, False
    return {
        "environment": "live"
        if settings.account_monitor.enabled
        else settings.execution.environment,
        "read_only": settings.account_monitor.enabled,
        "enabled": settings.execution.enabled and not settings.account_monitor.enabled,
        "config": {
            "capital": 500,
            "margin": 5,
            "leverage": 5,
            "margin_type": "Cross",
            "side": "Short",
            "max_positions": settings.execution.max_open_positions,
            "tp_max": 5,
            "stop_loss": False,
            "pause_drawdown": 0.2,
        },
        "healthy": bool(fresh and heartbeat.get("healthy")),
        "heartbeat_age_seconds": age,
        "heartbeat": heartbeat,
        "account": store.get("account"),
        "pause": store.get("pause", {}),
        "positions": store.get("positions", []),
        "open_orders": store.get("open_orders", []),
        "account_mode": store.get("account_mode", {}),
        "connection_error": heartbeat.get("error"),
        "income_health": store.get("income_health", {}),
        "trades": store.trades(False),
        "history": store.history(60),
        "source_health": store.get("source_health", {}),
        "live_gate": {"eligible": False, "reasons": ["account_read_only"]}
        if settings.account_monitor.enabled
        else store.get(
            "live_gate", {"eligible": False, "reasons": ["evidence_required"]}
        ),
        "manifest_id": store.get("manifest_id"),
        "financially_verified": False
        if settings.execution.environment == "simulation"
        else None,
    }


def command(settings, action, payload):
    if settings.account_monitor.enabled:
        raise ValueError("account_monitor_read_only")
    if action not in {"pause", "resume", "close"}:
        raise ValueError("unsupported_command")
    store = execution_store(settings)
    if action == "close":
        if payload.get("confirm") is not True:
            raise ValueError("manual_close_confirmation_required")
        if payload.get("trade_id") not in {t["id"] for t in store.trades()}:
            raise ValueError("active_trade_not_found")
    if not settings.execution.enabled:
        raise ValueError("execution_service_disabled")
    return {"command_id": store.enqueue(action, payload), "status": "queued"}
