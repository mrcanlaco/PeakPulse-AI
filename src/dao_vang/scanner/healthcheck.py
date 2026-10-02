"""Scanner liveness checks shared by Docker, the API, and monitors."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def inspect_heartbeat(
    path: Path,
    *,
    now: datetime | None = None,
    max_age_seconds: float = 900,
    snapshot_path: Path | None = None,
    stats_path: Path | None = None,
) -> dict[str, Any]:
    """Return a safe, structured scanner-health decision.

    The result deliberately excludes process IDs, paths, and exception text so
    it can be exposed by the unauthenticated readiness endpoint.
    """

    result: dict[str, Any] = {
        "healthy": False,
        "reason": "heartbeat_invalid",
        "age_seconds": None,
        "heartbeat_time": None,
        "scanner_status": None,
        "last_cycle_status": None,
    }
    try:
        heartbeat = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        result["reason"] = "heartbeat_missing"
        return result
    except (OSError, ValueError, TypeError):
        return result
    if not isinstance(heartbeat, dict):
        return result

    result["scanner_status"] = heartbeat.get("status")
    result["last_cycle_status"] = heartbeat.get("last_cycle_status")
    try:
        stamp = datetime.fromisoformat(str(heartbeat["timestamp"]))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        stamp = stamp.astimezone(timezone.utc)
        clock = now or datetime.now(timezone.utc)
        if clock.tzinfo is None:
            clock = clock.replace(tzinfo=timezone.utc)
        else:
            clock = clock.astimezone(timezone.utc)
        age = (clock - stamp).total_seconds()
    except (ValueError, TypeError, KeyError, AttributeError):
        return result

    result["age_seconds"] = round(age, 1)
    result["heartbeat_time"] = stamp.isoformat()
    if age < -60:
        result["reason"] = "heartbeat_clock_skew"
    elif age > max_age_seconds:
        result["reason"] = "heartbeat_stale"
    elif heartbeat.get("status") != "running":
        result["reason"] = "scanner_not_running"
    elif heartbeat.get("last_cycle_status") == "failed":
        result["reason"] = "last_cycle_failed"
    else:
        result["healthy"] = True
        result["reason"] = "ok"
    # Heartbeats can advance while scoring/publication repeatedly fails.
    # Production checks must verify the output as well as process liveness.
    if result["healthy"] and snapshot_path is not None:
        output = inspect_snapshot(snapshot_path, now=clock, max_age_seconds=max_age_seconds)
        result["snapshot_age_seconds"] = output["age_seconds"]
        if not output["healthy"]:
            result.update(healthy=False, reason=output["reason"])
    if result["healthy"] and stats_path is not None:
        stats = inspect_snapshot(stats_path, now=clock, max_age_seconds=max_age_seconds,
                                 rows_key="data_stats")
        if not stats["healthy"]:
            result.update(healthy=False, reason="stats_" + stats["reason"])
    return result


def inspect_snapshot(path: Path, *, now: datetime | None = None,
                     max_age_seconds: float = 900, rows_key: str = "rows") -> dict[str, Any]:
    result: dict[str, Any] = {"healthy": False, "reason": "snapshot_invalid", "age_seconds": None}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get(rows_key), list):
            return result
        stamp = datetime.fromisoformat(payload["generated_at"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        clock = now or datetime.now(timezone.utc)
        age = (clock - stamp).total_seconds()
        result["age_seconds"] = round(age, 1)
        if age < -60:
            result["reason"] = "snapshot_clock_skew"
        elif age > max_age_seconds:
            result["reason"] = "snapshot_stale"
        else:
            result.update(healthy=True, reason="ok")
        if result["healthy"] and rows_key == "data_stats":
            tables = {row.get("table"): row for row in payload[rows_key] if isinstance(row, dict)}
            for name in ("kline", "raw_timeline", "feature_results", "open_interest"):
                latest = tables.get(name, {}).get("max_time")
                if not latest:
                    result.update(healthy=False, reason="source_missing_" + name)
                    break
                source_time = datetime.fromisoformat(latest.replace("Z", "+00:00"))
                if source_time.tzinfo is None:
                    source_time = source_time.replace(tzinfo=timezone.utc)
                source_age = (clock - source_time).total_seconds()
                if source_age < -60 or source_age > max_age_seconds:
                    result.update(healthy=False, reason="source_stale_" + name)
                    break
    except FileNotFoundError:
        result["reason"] = "snapshot_missing"
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        result.update(healthy=False, reason="snapshot_invalid")
    return result


def heartbeat_is_healthy(
    path: Path,
    *,
    now: datetime | None = None,
    max_age_seconds: float = 900,
) -> bool:
    return bool(
        inspect_heartbeat(path, now=now, max_age_seconds=max_age_seconds)["healthy"]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("data_live/scanner_heartbeat.json"),
    )
    parser.add_argument("--max-age-seconds", type=float, default=900)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--stats", type=Path)
    args = parser.parse_args()
    return (
        0
        if inspect_heartbeat(
            args.path,
            max_age_seconds=args.max_age_seconds,
            snapshot_path=args.snapshot,
            stats_path=args.stats,
        )["healthy"]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
