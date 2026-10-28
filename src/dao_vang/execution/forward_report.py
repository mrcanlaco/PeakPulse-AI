"""Export observed account paths without upgrading simulated financial evidence."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from .contracts import StrategyManifest, utc_now


def export_forward(store, manifest: StrategyManifest):
    with store.connect() as db:
        raw_equity = [
            json.loads(row[0])
            for row in db.execute(
                "SELECT payload FROM journal WHERE kind='equity' ORDER BY seq"
            )
        ]
        raw_signals = [
            json.loads(row[0])
            for row in db.execute("SELECT payload FROM signals ORDER BY rowid")
        ]
        incidents = db.execute(
            "SELECT count(*) FROM journal WHERE kind='reconcile_error'"
        ).fetchone()[0]
        transfers = db.execute(
            "SELECT count(*) FROM ledger WHERE kind='TRANSFER'"
        ).fetchone()[0]
    equity = [
        row
        for row in raw_equity
        if datetime.fromisoformat(row["at"]) >= manifest.frozen_at
    ]
    if not equity:
        return {
            "manifest_id": manifest.identity,
            "kind": "forward_observed",
            "financially_verified": False,
            "source_verified": False,
            "status": "waiting_for_account_observations",
            "events": [],
            "daily_equity": [],
        }
    start = datetime.fromisoformat(equity[0]["at"])
    last = datetime.fromisoformat(equity[-1]["at"])
    day, index, daily = start, 0, []
    gaps = []
    while day <= last:
        while (
            index + 1 < len(equity)
            and datetime.fromisoformat(equity[index + 1]["at"]) <= day
        ):
            index += 1
        observed_at = datetime.fromisoformat(equity[index]["at"])
        if (day - observed_at).total_seconds() > 60:
            gaps.append(day.isoformat())
        daily.append(
            {
                "at": day.isoformat(),
                "equity": equity[index]["equity"],
                "observed_at": observed_at.isoformat(),
            }
        )
        day += timedelta(days=1)
    end = datetime.fromisoformat(daily[-1]["at"])
    events, seen, last_coin = [], set(), {}
    excluded = 0
    for signal in sorted(raw_signals, key=lambda r: r["observed_at"]):
        at = datetime.fromisoformat(signal["observed_at"])
        if (
            not signal.get("eligible")
            or signal["manifest_id"] != manifest.identity
            or not start <= at <= end
        ):
            continue
        if signal["event_id"] in seen or (
            signal["symbol"] in last_coin
            and at - last_coin[signal["symbol"]] < timedelta(hours=4)
        ):
            excluded += 1
            continue
        seen.add(signal["event_id"])
        last_coin[signal["symbol"]] = at
        events.append(
            {
                k: signal[k]
                for k in (
                    "event_id",
                    "source_id",
                    "symbol",
                    "observed_at",
                    "manifest_id",
                )
            }
        )
    max_dd = max(row["drawdown"] for row in equity)
    return {
        "manifest_id": manifest.identity,
        "kind": "forward_observed",
        "financially_verified": False,
        "source_verified": False,
        "status": "requires_financial_and_source_attestation",
        "generated_at": utc_now().isoformat(),
        "started_at": start.isoformat(),
        "ended_at": end.isoformat(),
        "frozen_at": manifest.frozen_at.isoformat(),
        "events": events,
        "excluded_overlapping_observations": excluded,
        "daily_equity": daily,
        "daily_gaps": gaps,
        "intraday_max_drawdown": max_dd,
        "critical_incidents": incidents,
        "external_cashflows": transfers,
        "open_positions_marked": not gaps,
        "live_stages": {},
        "limitations": [
            "sampled_equity_not_continuous_mark",
            "paper_fills_not_exchange_fills",
            "margin_tier_and_liquidation_evidence_required",
        ],
    }
