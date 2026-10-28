"""Account monitoring from the reconciler's durable records; no exchange calls."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta

from dao_vang.execution.contracts import StrategyManifest, utc_now

from .execution_api import execution_store, status


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def timestamp(value):
    try:
        result = datetime.fromisoformat(value)
        return result if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def dashboard(settings, period="7d"):
    if period not in {"24h", "7d", "30d"}:
        raise ValueError("invalid_dashboard_period")
    now = utc_now()
    days = {"24h": 1, "7d": 7, "30d": 30}[period]
    start = now - timedelta(days=days)
    bucket = {"24h": 300, "7d": 3600, "30d": 14400}[period]
    result = status(settings)
    store = execution_store(settings)
    account_at = timestamp((result["account"] or {}).get("at"))
    age = (now - account_at).total_seconds() if account_at else None
    result["account_fresh"] = age is not None and 0 <= age <= max(
        60, settings.execution.poll_seconds * 3
    )
    result["account_age_seconds"] = age
    result["generated_at"] = now.isoformat()
    result["period"] = period
    result["source"] = (
        "binance_live_read_only"
        if result["read_only"]
        else {
            "simulation": "paper_market_observations",
            "demo": "binance_demo_reconciled",
            "live": "binance_live_reconciled",
        }[settings.execution.environment]
    )
    manifest = None
    try:
        if settings.execution.manifest_path and not result["read_only"]:
            manifest = StrategyManifest.model_validate_json(
                settings.execution.manifest_path.read_text(encoding="utf-8")
            )
            if manifest.identity != result["manifest_id"]:
                manifest = None
    except (OSError, ValueError):
        pass
    with store.connect() as db:
        # Bound the response size. Last observed equity per bucket is not a
        # continuous mark path; preserve the bucket's worst observed drawdown.
        chart = db.execute(
            """
            SELECT j.payload, b.worst_drawdown FROM journal j JOIN (
                SELECT MAX(seq) last_seq, MAX(json_extract(payload,'$.drawdown')) worst_drawdown
                FROM journal WHERE kind='equity' AND at>=?
                GROUP BY CAST(strftime('%s',at) AS INTEGER) / ?
            ) b ON j.seq=b.last_seq ORDER BY j.seq
        """,
            (start.isoformat(), bucket),
        ).fetchall()
        result["equity_curve"] = [
            {
                "at": item.get("at"),
                "equity": number(item.get("equity")),
                "drawdown": number(row[1]),
            }
            for row in chart
            for item in [json.loads(row[0])]
        ]
        # Ledger fills and income commissions overlap. Use fill commissions
        # only, and retain unknown coverage rather than summing both sources.
        fees = db.execute("""SELECT COUNT(*), SUM(CAST(json_extract(payload,'$.commission') AS REAL))
            FROM ledger WHERE kind='fill' AND json_extract(payload,'$.commissionAsset')='USDT'""").fetchone()
        if result["read_only"]:
            fees = db.execute("""SELECT COUNT(*), -SUM(CAST(json_extract(payload,'$.income') AS REAL))
                FROM ledger WHERE kind='COMMISSION' AND json_extract(payload,'$.asset')='USDT'""").fetchone()
        funding = db.execute("""SELECT COUNT(*), SUM(CAST(json_extract(payload,'$.income') AS REAL))
            FROM ledger WHERE kind='FUNDING_FEE' AND json_extract(payload,'$.asset')='USDT'""").fetchone()
        first = db.execute(
            "SELECT payload FROM journal WHERE kind='equity' ORDER BY seq LIMIT 1"
        ).fetchone()
        first_account = json.loads(first[0]) if first else {}
        first_current = db.execute(
            "SELECT payload FROM journal WHERE kind='equity' AND at>=? ORDER BY seq LIMIT 1",
            (manifest.frozen_at.isoformat() if manifest else now.isoformat(),),
        ).fetchone()
        signals = db.execute(
            "SELECT payload,status FROM signals WHERE json_extract(payload,'$.manifest_id')=? ORDER BY json_extract(payload,'$.observed_at')",
            (result["manifest_id"],),
        ).fetchall()
        recent = db.execute(
            "SELECT payload,status FROM signals ORDER BY rowid DESC LIMIT 25"
        ).fetchall()
        commands = db.execute(
            "SELECT id,at,action,status FROM commands ORDER BY at DESC LIMIT 20"
        ).fetchall()
        activity = db.execute(
            "SELECT seq,at,kind,payload FROM journal WHERE kind NOT IN ('equity','trade','user_stream','user_stream_event') ORDER BY seq DESC LIMIT 40"
        ).fetchall()
    trades = result["trades"]
    closed = [t for t in trades if t["status"] == "closed"]
    profits = [number(t.get("net_pnl")) for t in closed]
    verified_profits = [p for p in profits if p is not None]
    initial = number(first_account.get("equity"))
    current = number((result["account"] or {}).get("equity"))
    result["totals"] = {
        "recorded_fees": number(fees[1]),
        "recorded_funding": number(funding[1]),
        "fill_count": fees[0],
        "funding_count": funding[0],
        "closed_count": len(closed),
        "wins": sum(p > 0 for p in verified_profits),
        "closed_net_pnl": sum(verified_profits)
        if len(verified_profits) == len(closed) and closed
        else None,
        "equity_change": current - initial
        if current is not None and initial is not None
        else None,
        "observed_since": first_account.get("at"),
    }
    positions = {p["symbol"]: p for p in result["positions"]}
    for trade in trades:
        position = (
            positions.get(trade["symbol"])
            if trade["status"] not in {"closed", "rejected"}
            else None
        )
        mark = number((position or {}).get("markPrice"))
        qty = number((position or {}).get("positionAmt"))
        entry = number(trade.get("entry_price"))
        unrealized = number((position or {}).get("unRealizedProfit"))
        if (
            unrealized is None
            and mark is not None
            and qty is not None
            and entry is not None
        ):
            unrealized = qty * (mark - entry)
        trade.update(
            mark_price=mark,
            unrealized=unrealized,
            liquidation_price=number((position or {}).get("liquidationPrice")),
        )
    active = [t for t in trades if t["status"] not in {"closed", "rejected"}]
    result["unmanaged_positions"] = [
        {
            "symbol": p["symbol"],
            "quantity": number(p.get("positionAmt")),
            "unrealized": number(p.get("unRealizedProfit")),
            "mark_price": number(p.get("markPrice")),
            "side": p.get("positionSide", "BOTH"),
            "entry_price": number(p.get("entryPrice")),
            "margin_asset": p.get("marginAsset", "USDT"),
        }
        for p in result["positions"]
        if p["symbol"] not in {t["symbol"] for t in active}
    ]
    result["trades"] = (
        active
        + sorted(
            [t for t in trades if t not in active],
            key=lambda t: t.get("closed_at", t.get("created_at", "")),
            reverse=True,
        )[:100]
    )
    result["trade_history_truncated"] = len(trades) > len(result["trades"])
    result["commands"] = [dict(row) for row in commands]
    # Explicit allowlist: account monitoring never serializes key material.
    result["activity"] = [
        {
            "seq": row["seq"],
            "at": row["at"],
            "kind": row["kind"],
            "reason": json.loads(row["payload"]).get("reason")
            or json.loads(row["payload"]).get("status"),
        }
        for row in activity
    ]
    result["recent_signals"] = [
        {
            "event_id": s.get("event_id"),
            "symbol": s.get("symbol"),
            "at": s.get("observed_at"),
            "eligible": s.get("eligible"),
            "decision": row["status"],
            "reasons": s.get("reasons", []),
        }
        for row in recent
        for s in [json.loads(row["payload"])]
    ]
    observed_start = (
        timestamp(json.loads(first_current[0]).get("at")) if first_current else None
    )
    # Wall-clock time since a dead worker is not observation progress.
    observed_end = account_at
    seen, last_coin, windows = set(), {}, set()
    if manifest and observed_start and observed_end:
        for row in signals:
            s = json.loads(row["payload"])
            at = timestamp(s.get("observed_at"))
            if (
                not s.get("eligible")
                or not at
                or not observed_start <= at <= observed_end
            ):
                continue
            if s["event_id"] in seen or (
                s["symbol"] in last_coin
                and at - last_coin[s["symbol"]] < timedelta(hours=4)
            ):
                continue
            seen.add(s["event_id"])
            last_coin[s["symbol"]] = at
            windows.add((at - observed_start).days // 7)
    result["progress"] = {
        "manifest_loaded": manifest is not None,
        "observed_days": max(0, (observed_end - observed_start).total_seconds() / 86400)
        if manifest and observed_start and observed_end
        else 0,
        "independent_events": len(seen),
        "time_windows": len(windows),
        "required_days": 28,
        "required_events": 100,
        "required_windows": 3,
        "observation_continuity_verified": False,
        "stage": settings.execution.environment,
        "max_positions": settings.execution.max_open_positions,
        "note": "Observation counters are not acceptance of financial evidence.",
    }
    result["setup"] = {
        "credentials_present": settings.execution.environment == "simulation"
        or bool(
            settings.execution.live_api_key and settings.execution.live_api_secret
            if settings.execution.environment == "live"
            else settings.execution.api_key and settings.execution.api_secret
        ),
        "manifest_loaded": manifest is not None,
        "worker_enabled": settings.execution.enabled,
        "account_observed": result["account"] is not None,
    }
    if result["read_only"]:
        from dao_vang.execution.account_monitor import monitor_credentials

        key, secret = monitor_credentials(settings)
        result["setup"].update(
            credentials_present=bool(key and secret),
            worker_enabled=True,
            manifest_loaded=False,
        )
        result["progress"].update(
            observed_days=0, independent_events=0, time_windows=0, stage="read_only"
        )
    result.pop("history", None)
    return result
