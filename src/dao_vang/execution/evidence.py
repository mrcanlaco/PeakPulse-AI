"""Promotion gates are observations, never a successful build or demo fill."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np

from .contracts import utc_now


def evaluate_evidence(report: dict, manifest_id: str, max_positions: int = 1) -> dict:
    failures = []

    def require(condition, reason):
        if not condition:
            failures.append(reason)

    require(report.get("manifest_id") == manifest_id, "manifest_mismatch")
    require(report.get("kind") == "forward_observed", "requires_forward_observed")
    require(report.get("financially_verified") is True, "financial_evidence_unverified")
    require(report.get("source_verified") is True, "source_unverified")
    require(not report.get("daily_gaps"), "account_observation_gaps")
    try:
        start, end, frozen = [
            datetime.fromisoformat(report[k])
            for k in ("started_at", "ended_at", "frozen_at")
        ]
        require(
            all(t.tzinfo is not None for t in (start, end, frozen)), "timezone_required"
        )
        require(
            start >= frozen and (end - start).total_seconds() >= 28 * 86400,
            "forward_period_too_short",
        )
        require(end <= utc_now(), "future_evidence")
        events = report["events"]
        require(
            len({e["event_id"] for e in events}) == len(events) >= 100,
            "independent_events_insufficient",
        )
        require(
            len({e["source_id"] for e in events}) == len(events),
            "duplicate_source_events",
        )
        last_by_symbol = {}
        occupied_windows = set()
        for event in sorted(events, key=lambda e: e["observed_at"]):
            at = datetime.fromisoformat(event["observed_at"])
            require(
                start <= at <= end and event["manifest_id"] == manifest_id,
                "event_outside_frozen_contract",
            )
            symbol = event["symbol"]
            if symbol in last_by_symbol:
                require(
                    (at - last_by_symbol[symbol]).total_seconds() >= 4 * 3600,
                    "overlapping_event_cluster",
                )
            last_by_symbol[symbol] = at
            occupied_windows.add((at - start).days // 7)
        require(len(occupied_windows) >= 3, "event_time_windows_insufficient")
        # Daily, whole-portfolio PnL blocks preserve simultaneous coin dependence.
        windows = report["daily_equity"]
        times = [datetime.fromisoformat(r["at"]) for r in windows]
        values = np.asarray([r["equity"] for r in windows], dtype=float)
        require(
            len(values) >= 29 and np.isfinite(values).all(),
            "equity_observations_missing",
        )
        require(
            all((b - a).total_seconds() == 86400 for a, b in zip(times, times[1:])),
            "equity_daily_gap",
        )
        require(times[0] == start and times[-1] == end, "equity_window_mismatch")
        require(abs(float(values[0]) - 500) < 0.01, "initial_equity_mismatch")
        require(values[-1] > 500, "net_equity_not_positive")
        drawdown = 1 - values / np.maximum.accumulate(values)
        require(
            float(max(drawdown)) < 0.20
            and report.get("intraday_max_drawdown", 1) < 0.20,
            "drawdown_gate_failed",
        )
        pnl = np.diff(values)
        blocks = [pnl[i : i + 7] for i in range(0, len(pnl) - 6)]
        require(len(pnl) // 7 >= 3, "time_windows_insufficient")
        rng = np.random.default_rng(500)
        if blocks:
            means = [
                np.concatenate(
                    [
                        blocks[i]
                        for i in rng.integers(
                            0, len(blocks), size=math.ceil(len(pnl) / 7)
                        )
                    ]
                )[: len(pnl)].mean()
                for _ in range(2000)
            ]
            lower = float(np.quantile(means, 0.025))
        else:
            lower = float("-inf")
        require(lower > 0, "positive_lower_confidence_bound_required")
        require(report.get("critical_incidents") == 0, "critical_incidents")
        require(report.get("external_cashflows") == 0, "external_cashflows")
        require(report.get("open_positions_marked") is True, "unrealized_pnl_missing")
        if max_positions > 1:
            stages = report.get("live_stages", {})
            for stage in [1] if max_positions == 3 else [1, 3]:
                value = stages.get(str(stage), {})
                require(
                    value.get("days", 0) >= 14
                    and value.get("closed_trades", 0) >= 20
                    and value.get("critical_incidents") == 0
                    and value.get("net_equity_change", -1) > 0
                    and value.get("max_drawdown", 1) < 0.20
                    and value.get("open_positions_marked") is True,
                    f"live_stage_{stage}_incomplete",
                )
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
        failures.append("evidence_malformed")
        lower = None
    return {
        "eligible": not failures,
        "reasons": sorted(set(failures)),
        "lower_daily_pnl_95": lower
        if lower is not None and math.isfinite(lower)
        else None,
    }


def live_gate(config, manifest_id: str) -> dict:
    if not config.live_activated:
        return {"eligible": False, "reasons": ["live_not_activated"]}
    if not config.evidence_path or not config.evidence_sha256:
        return {"eligible": False, "reasons": ["pinned_evidence_required"]}
    try:
        raw = Path(config.evidence_path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != config.evidence_sha256:
            raise ValueError("evidence_checksum_mismatch")
        return evaluate_evidence(
            json.loads(raw), manifest_id, config.max_open_positions
        )
    except (OSError, ValueError):
        return {"eligible": False, "reasons": ["evidence_unreadable_or_changed"]}
