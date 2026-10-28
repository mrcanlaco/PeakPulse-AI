"""Replay the frozen V3 Champion cohort against local normalized market data.

This is a bounded retrospective audit, not a new holdout experiment.  The
cohort is read from ``artifacts/v3_scout_deep_dive.json`` and is therefore the
same 23 signal rows used by the historical scout report.  Source timestamps
end at ``HH:04:59.999``; they are normalized to the next five-minute boundary
before calling the compact V3 engine.

The audit is deliberately conservative around missing data:

* complete paths are sent to :func:`evaluate_dual`;
* a partial path is also sent when it has at least one contiguous bar, so an
  early target/stop can be shown, but its evidence remains ineligible;
* a signal with no first forward bar is explicitly excluded as
  ``excluded_missing_klines``;
* local funding rows may be replayed, but they do not make an outcome eligible
  without an explicit coverage attestation.  No attestation is inferred from
  a file's min/max timestamps.

The default roots include the current normalized snapshot and the local live
normalized snapshot.  The latter is recorded separately in the artifact and
can be omitted with ``--kline-root``/``--funding-root`` when an exact primary
root-only audit is desired.  No network access or writes to the source data
are performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import duckdb


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from dao_vang.labels.dual_outcomes_v3 import POST_STOP_VERSION, evaluate_dual
from dao_vang.labels.engine_v3 import Bar, Funding
from dao_vang.labels.specs.distribution_short_v3 import SPEC


UTC = timezone.utc
STEP = timedelta(minutes=SPEC.bar_minutes)
EXPECTED_BARS = int(SPEC.horizon_hours * 60 / SPEC.bar_minutes)
DEFAULT_SOURCE = REPO_ROOT / "artifacts" / "v3_scout_deep_dive.json"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "v3_compact_replay_champion_audit_20260915.json"
DEFAULT_REPORT = REPO_ROOT / "docs" / "V3_COMPACT_REPLAY_20260915.md"
DEFAULT_KLINE_ROOTS = (
    REPO_ROOT / "data" / "normalized" / "klines",
    REPO_ROOT / "data_live" / "normalized" / "klines",
)
DEFAULT_FUNDING_ROOTS = (
    REPO_ROOT / "data" / "normalized" / "funding",
    REPO_ROOT / "data_live" / "normalized" / "funding",
)


def _parse_time(value: str | datetime) -> datetime:
    """Parse a timezone-aware timestamp and return it in UTC."""

    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timestamp must be timezone-aware: {value!r}")
    return parsed.astimezone(UTC)


def _normalise_boundary(value: datetime) -> datetime:
    """Round source jitter to the nearest exact five-minute UTC boundary."""

    value = _parse_time(value)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    step_count = int(((value - epoch).total_seconds() / STEP.total_seconds()) + 0.5)
    return epoch + step_count * STEP


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(UTC).isoformat()


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sql_quote(path: Path) -> str:
    return "'" + str(path.resolve()).replace("\\", "/").replace("'", "''") + "'"


def _read_parquet_relation(paths: Iterable[Path]) -> str:
    quoted = ",".join(_sql_quote(path) for path in paths)
    return f"read_parquet([{quoted}], union_by_name=true)"


def _source_events(source_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    champion = payload.get("champion")
    if not isinstance(champion, dict):
        raise ValueError("source artifact has no champion section")
    raw_events = champion.get("signals_detail")
    if not isinstance(raw_events, list) or len(raw_events) != 23:
        raise ValueError(f"expected exactly 23 champion events, found {len(raw_events or [])}")

    events: list[dict[str, Any]] = []
    required = {"symbol", "feature_time", "entry_price", "label_value"}
    for index, raw in enumerate(raw_events, start=1):
        if not isinstance(raw, dict) or not required.issubset(raw):
            raise ValueError(f"champion event {index} is missing required fields")
        source_time = str(raw["feature_time"])
        signal_time = _normalise_boundary(_parse_time(source_time))
        events.append(
            {
                "event_id": index,
                "symbol": str(raw["symbol"]),
                "source_feature_time": source_time,
                "signal_time": signal_time,
                "horizon_time": signal_time + timedelta(hours=SPEC.horizon_hours),
                "entry_price": float(raw["entry_price"]),
                "legacy_entry1_label": int(raw["label_value"]),
                "fold": raw.get("fold"),
                "score": raw.get("score"),
                "threshold": raw.get("threshold"),
                "source_fields": {
                    key: raw[key]
                    for key in (
                        "price_ret_24h",
                        "distance_from_high_24h",
                        "funding_rate_raw",
                        "funding_percentile_30d",
                        "funding_change_8h",
                        "oi_change_4h",
                        "taker_buy_ratio",
                    )
                    if key in raw
                },
            }
        )
    return payload, events


class LocalData:
    """Small read-only per-symbol cache over explicitly listed parquet files."""

    def __init__(self, roots: tuple[Path, ...], kind: str) -> None:
        self.roots = tuple(root.resolve() for root in roots)
        self.kind = kind
        self._paths: dict[str, list[tuple[int, Path]]] = {}
        self._rows: dict[str, list[dict[str, Any]]] = {}
        self._conn = duckdb.connect(":memory:")

    def close(self) -> None:
        self._conn.close()

    def paths_for(self, symbol: str) -> list[tuple[int, Path]]:
        if symbol not in self._paths:
            discovered: list[tuple[int, Path]] = []
            for priority, root in enumerate(self.roots):
                if not root.exists():
                    continue
                # File names are scan_<id>_<symbol>.parquet.  Exact suffix
                # matching avoids BUSDT matching BBUSDT and 4USDT matching
                # 1000* variants.
                discovered.extend(
                    (priority, path)
                    for path in sorted(root.rglob(f"*_{symbol}.parquet"))
                    if path.is_file()
                )
            self._paths[symbol] = discovered
        return self._paths[symbol]

    def rows_for(self, symbol: str) -> list[dict[str, Any]]:
        if symbol in self._rows:
            return self._rows[symbol]
        paths_with_priority = self.paths_for(symbol)
        if not paths_with_priority:
            self._rows[symbol] = []
            return []

        # Query each root independently so the primary root can win a
        # conflicting duplicate timestamp while retaining secondary coverage.
        rows: list[dict[str, Any]] = []
        for priority in range(len(self.roots)):
            paths = [path for p, path in paths_with_priority if p == priority]
            if not paths:
                continue
            relation = _read_parquet_relation(paths)
            if self.kind == "klines":
                query = f"""
                    SELECT symbol, interval, close_time, open, high, low, close,
                           quality_status
                    FROM {relation}
                    WHERE symbol = ? AND interval = '5m'
                """
            else:
                query = f"""
                    SELECT symbol, funding_time, funding_rate, mark_price,
                           quality_status
                    FROM {relation}
                    WHERE symbol = ?
                """
            for row in self._conn.execute(query, [symbol]).fetchall():
                if self.kind == "klines":
                    rows.append(
                        {
                            "priority": priority,
                            "source_time": row[2],
                            "open": row[3],
                            "high": row[4],
                            "low": row[5],
                            "close": row[6],
                            "quality_status": row[7],
                        }
                    )
                else:
                    rows.append(
                        {
                            "priority": priority,
                            "source_time": row[1],
                            "rate": row[2],
                            "mark_price": row[3],
                            "quality_status": row[4],
                        }
                    )
        self._rows[symbol] = rows
        return rows


def _dedupe_bars(rows: list[dict[str, Any]]) -> tuple[dict[datetime, Bar], dict[str, Any]]:
    bars: dict[datetime, Bar] = {}
    source_rows = len(rows)
    invalid_quality = 0
    invalid_ohlc = 0
    duplicate_times = 0
    conflicting_times = 0
    for row in rows:
        if str(row.get("quality_status") or "") != "valid":
            invalid_quality += 1
            continue
        try:
            timestamp = _normalise_boundary(row["source_time"])
            candidate = Bar(
                timestamp,
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
            )
            candidate.validate()
        except (TypeError, ValueError, OverflowError):
            invalid_ohlc += 1
            continue
        existing = bars.get(timestamp)
        if existing is not None:
            duplicate_times += 1
            if (existing.open, existing.high, existing.low, existing.close) != (
                candidate.open,
                candidate.high,
                candidate.low,
                candidate.close,
            ):
                conflicting_times += 1
            # Rows are read root-priority order; primary data remains first.
            continue
        bars[timestamp] = candidate
    return bars, {
        "source_rows": source_rows,
        "valid_rows": len(bars),
        "invalid_quality_rows": invalid_quality,
        "invalid_ohlc_rows": invalid_ohlc,
        "duplicate_normalized_times": duplicate_times,
        "conflicting_normalized_times": conflicting_times,
    }


def _dedupe_funding(rows: list[dict[str, Any]]) -> tuple[dict[datetime, Funding], dict[str, Any]]:
    funding: dict[datetime, Funding] = {}
    invalid_quality = 0
    invalid_rows = 0
    duplicate_times = 0
    conflicting_times = 0
    for row in rows:
        if str(row.get("quality_status") or "") != "valid":
            invalid_quality += 1
            continue
        try:
            timestamp = _normalise_boundary(row["source_time"])
            candidate = Funding(timestamp, float(row["rate"]), float(row["mark_price"]))
            if candidate.mark_price <= 0:
                raise ValueError("non-positive mark price")
        except (TypeError, ValueError, OverflowError):
            invalid_rows += 1
            continue
        existing = funding.get(timestamp)
        if existing is not None:
            duplicate_times += 1
            if (existing.rate, existing.mark_price) != (candidate.rate, candidate.mark_price):
                conflicting_times += 1
            continue
        funding[timestamp] = candidate
    return funding, {
        "source_rows": len(rows),
        "valid_rows": len(funding),
        "invalid_quality_rows": invalid_quality,
        "invalid_rows": invalid_rows,
        "duplicate_normalized_times": duplicate_times,
        "conflicting_normalized_times": conflicting_times,
    }


def _attestations(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("funding attestation must be an object keyed by symbol")
    result: dict[str, dict[str, Any]] = {}
    for symbol, raw in payload.items():
        if not isinstance(raw, dict) or "through" not in raw:
            raise ValueError(f"funding attestation for {symbol} must include through")
        through = _parse_time(str(raw["through"]))
        start = _parse_time(str(raw["from"])) if raw.get("from") else None
        result[str(symbol)] = {"through": through, "from": start, "source": raw.get("source")}
    return result


def _coverage_record(
    *,
    event: dict[str, Any],
    bar_map: dict[datetime, Bar],
    bar_stats: dict[str, Any],
    path_count: int,
) -> tuple[list[Bar], dict[str, Any]]:
    signal_time = event["signal_time"]
    horizon_time = event["horizon_time"]
    expected_times = [signal_time + STEP * index for index in range(1, EXPECTED_BARS + 1)]
    first_gap: datetime | None = None
    prefix: list[Bar] = []
    for timestamp in expected_times:
        candidate = bar_map.get(timestamp)
        if candidate is None:
            first_gap = timestamp
            break
        prefix.append(candidate)
    complete = len(prefix) == EXPECTED_BARS
    observed_window = [timestamp for timestamp in bar_map if signal_time < timestamp <= horizon_time]
    window_first = min(observed_window) if observed_window else None
    window_last = max(observed_window) if observed_window else None
    missing_count = EXPECTED_BARS - len(prefix) if not complete else 0
    if not prefix:
        status = "missing_first_forward_bar"
        exclusion = "missing_price_path"
    elif complete:
        status = "complete_48h_price_path"
        exclusion = None
    else:
        status = "partial_price_path"
        exclusion = "price_path_incomplete"
    coverage = {
        **bar_stats,
        "path_files": path_count,
        "expected_bars": EXPECTED_BARS,
        "contiguous_prefix_bars": len(prefix),
        "missing_bar_count_after_prefix": missing_count,
        "complete_48h": complete,
        "first_gap": _iso(first_gap),
        "observed_window_first": _iso(window_first),
        "observed_window_last": _iso(window_last),
        "coverage_status": status,
        "exclusion_reason": exclusion,
    }
    return prefix, coverage


def _funding_record(
    *,
    event: dict[str, Any],
    funding_map: dict[datetime, Funding],
    funding_stats: dict[str, Any],
    path_count: int,
    attestation: dict[str, Any] | None,
) -> tuple[list[Funding], dict[str, Any], datetime | None]:
    signal_time = event["signal_time"]
    horizon_time = event["horizon_time"]
    window = [
        funding_map[timestamp]
        for timestamp in sorted(funding_map)
        if signal_time < timestamp <= horizon_time
    ]
    observed = [funding.timestamp for funding in window]
    attested_through = attestation.get("through") if attestation else None
    attested_from = attestation.get("from") if attestation else None
    eligible = bool(
        attested_through is not None
        and attested_through >= horizon_time
        and (attested_from is None or attested_from <= signal_time)
    )
    if eligible:
        funding_status = "eligible_attested"
        coverage_through = horizon_time
    elif window:
        funding_status = "rows_present_no_attestation"
        coverage_through = None
    else:
        funding_status = "no_rows"
        coverage_through = None
    record = {
        **funding_stats,
        "path_files": path_count,
        "window_rows": len(window),
        "window_first": _iso(min(observed) if observed else None),
        "window_last": _iso(max(observed) if observed else None),
        "attestation_supplied": attestation is not None,
        "attested_from": _iso(attested_from),
        "attested_through": _iso(attested_through),
        "funding_status": funding_status,
        "funding_eligible": eligible,
    }
    return window, record, coverage_through


def _excluded_actual(reason: str) -> dict[str, Any]:
    return {
        "contract": SPEC.version,
        "contract_checksum": SPEC.checksum,
        "mode": "compact_policy",
        "status": "excluded_missing_klines",
        "exclusion_reason": reason,
        "eligible": False,
        "label": None,
    }


def _excluded_post_stop(reason: str, horizon_time: datetime) -> dict[str, Any]:
    return {
        "version": POST_STOP_VERSION,
        "contract": SPEC.version,
        "contract_checksum": SPEC.checksum,
        "status": "not_evaluated",
        "exclusion_reason": reason,
        "stop_time": None,
        "frozen_average_entry": None,
        "frozen_target_price": None,
        "target_time": None,
        "target_price": None,
        "horizon_time": horizon_time,
        "observed_bars": 0,
        "target_after_stop": None,
    }


def _event_result(
    *,
    event: dict[str, Any],
    klines: LocalData,
    funding: LocalData,
    attestations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    symbol = event["symbol"]
    bar_rows = klines.rows_for(symbol)
    bar_map, bar_stats = _dedupe_bars(bar_rows)
    prefix, price_coverage = _coverage_record(
        event=event,
        bar_map=bar_map,
        bar_stats=bar_stats,
        path_count=len(klines.paths_for(symbol)),
    )
    funding_rows = funding.rows_for(symbol)
    funding_map, funding_stats = _dedupe_funding(funding_rows)
    attestation = attestations.get(symbol)
    funding_window, funding_coverage, funding_through = _funding_record(
        event=event,
        funding_map=funding_map,
        funding_stats=funding_stats,
        path_count=len(funding.paths_for(symbol)),
        attestation=attestation,
    )

    if not prefix:
        actual = _excluded_actual("missing_price_path")
        post_stop = _excluded_post_stop("missing_price_path", event["horizon_time"])
        evaluated = False
        replay_status = "excluded_missing_klines"
        paired_eligible = False
        actual_win = None
    else:
        result = evaluate_dual(
            signal_time=event["signal_time"],
            signal_price=event["entry_price"],
            bars=prefix,
            funding=funding_window,
            funding_coverage_through=funding_through,
        )
        actual = result.actual.to_dict()
        post_stop = result.post_stop.to_dict()
        evaluated = True
        paired_eligible = bool(result.paired_evidence_eligible and price_coverage["complete_48h"])
        actual_win = result.actual_win
        replay_status = "complete_evaluation" if price_coverage["complete_48h"] else "partial_early_exit_or_incomplete"

    return {
        "event_id": event["event_id"],
        "symbol": symbol,
        "source_feature_time": event["source_feature_time"],
        "signal_time": event["signal_time"],
        "horizon_time": event["horizon_time"],
        "entry_price": event["entry_price"],
        "legacy_entry1_label": event["legacy_entry1_label"],
        "fold": event["fold"],
        "score": event["score"],
        "threshold": event["threshold"],
        "source_fields": event["source_fields"],
        "price_coverage": price_coverage,
        "funding_coverage": funding_coverage,
        "evaluated": evaluated,
        "replay_status": replay_status,
        "actual_status": actual.get("status"),
        "actual_win": actual_win,
        "actual_eligible": bool(actual.get("eligible", False) and price_coverage["complete_48h"]),
        "post_stop_status": post_stop.get("status"),
        "paired_evidence_eligible": paired_eligible,
        "actual": actual,
        "post_stop": post_stop,
    }


def _summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    actual_statuses = Counter(str(event["actual_status"]) for event in events)
    post_stop_statuses = Counter(str(event["post_stop_status"]) for event in events)
    coverage_statuses = Counter(str(event["price_coverage"]["coverage_status"]) for event in events)
    return {
        "event_count": len(events),
        "evaluated_count": sum(bool(event["evaluated"]) for event in events),
        "complete_price_path_count": sum(bool(event["price_coverage"]["complete_48h"]) for event in events),
        "partial_price_path_count": sum(event["price_coverage"]["coverage_status"] == "partial_price_path" for event in events),
        "excluded_missing_klines_count": sum(event["replay_status"] == "excluded_missing_klines" for event in events),
        "actual_eligible_count": sum(bool(event["actual_eligible"]) for event in events),
        "funding_eligible_count": sum(bool(event["funding_coverage"]["funding_eligible"]) for event in events),
        "price_only_status_count": sum(
            bool(event["evaluated"] and not event["funding_coverage"]["funding_eligible"])
            for event in events
        ),
        "paired_evidence_eligible_count": sum(bool(event["paired_evidence_eligible"]) for event in events),
        "legacy_entry1_label_count": sum(event["legacy_entry1_label"] == 1 for event in events),
        "actual_status_counts": dict(sorted(actual_statuses.items())),
        "post_stop_status_counts": dict(sorted(post_stop_statuses.items())),
        "coverage_status_counts": dict(sorted(coverage_statuses.items())),
        "retrospective_recycled_cohort": True,
        "improvement_claim_supported": False,
    }


def build_artifact(
    *,
    source_path: Path,
    source_payload: dict[str, Any],
    events: list[dict[str, Any]],
    kline_roots: tuple[Path, ...],
    funding_roots: tuple[Path, ...],
    attestation_path: Path | None,
) -> dict[str, Any]:
    return {
        "artifact_version": "v3_compact_replay_champion_audit_v1",
        "generated_at": datetime.now(UTC),
        "source_artifact": str(source_path.resolve()),
        "source_artifact_sha256": _sha256(source_path),
        "source_section": "champion.signals_detail",
        "source_champion_summary": {
            key: source_payload.get("champion", {}).get(key)
            for key in ("rows", "signals", "true_positives", "precision", "conservative_ev")
        },
        "scope": {
            "description": "Bounded recycled retrospective diagnostic; not an untouched holdout",
            "event_count": len(events),
            "signal_time_convention": "source HH:04:59.999 rounded to the next exact 5-minute UTC boundary",
            "entry_price": "source entry_price; no replacement by first kline close",
            "compact_policy": {
                "version": SPEC.version,
                "checksum": SPEC.checksum,
                "target": SPEC.target,
                "stop": SPEC.stop,
                "offsets": list(SPEC.offsets),
                "notional_weights": list(SPEC.notional_weights),
                "horizon_hours": SPEC.horizon_hours,
                "scale_in_hours": SPEC.scale_in_hours,
                "bar_minutes": SPEC.bar_minutes,
            },
            "post_stop_version": POST_STOP_VERSION,
            "source_contract_compatibility_note": "entry1 labels in the source artifact remain legacy diagnostics and are not reused as compact outcomes",
        },
        "data_sources": {
            "kline_roots": [str(root.resolve()) for root in kline_roots],
            "funding_roots": [str(root.resolve()) for root in funding_roots],
            "funding_attestation": str(attestation_path.resolve()) if attestation_path else None,
            "network_used": False,
        },
        "summary": _summary(events),
        "events": events,
    }


def _md_cell(value: Any) -> str:
    text = "—" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def write_report(path: Path, artifact: dict[str, Any]) -> None:
    summary = artifact["summary"]
    lines = [
        "# V3 compact Champion replay audit — 2026-09-15",
        "",
        "> Bounded retrospective diagnostic on the recycled 23-event Champion cohort. This is not an untouched holdout and does not support an improvement claim.",
        "",
        "## Contract and provenance",
        "",
        f"- Source: `{artifact['source_section']}` from `{artifact['source_artifact']}` (SHA-256 `{artifact['source_artifact_sha256']}`).",
        f"- Signal boundary: source `HH:04:59.999` rounded to the next exact five-minute UTC close; the source `entry_price` is retained.",
        f"- Compact policy: `{SPEC.version}` / checksum `{SPEC.checksum}`; target `{SPEC.target:.0%}`, stop `{SPEC.stop:.0%}`, offsets `{list(SPEC.offsets)}`, weights `{list(SPEC.notional_weights)}`, horizon `{SPEC.horizon_hours}h`.",
        f"- Post-stop diagnostic: `{POST_STOP_VERSION}`. A target after a real stop is descriptive and never changes `actual_win`.",
        "- Funding eligibility is false unless an explicit attestation covers `[signal_time, signal_time + 48h]`; local rows alone are not treated as an attestation.",
        "- The artifact hashes the source cohort JSON. Parquet inputs are recorded by root path and are not content-hashed in this bounded audit.",
        "",
        "## Coverage summary",
        "",
        f"- Events: **{summary['event_count']}**; complete 48h price paths: **{summary['complete_price_path_count']}**; evaluated rows: **{summary['evaluated_count']}**.",
        f"- Partial paths: **{summary['partial_price_path_count']}**; explicitly excluded for missing first forward kline: **{summary['excluded_missing_klines_count']}**.",
        f"- Funding-eligible rows: **{summary['funding_eligible_count']}**; actual-eligible rows: **{summary['actual_eligible_count']}**; paired-evidence eligible: **{summary['paired_evidence_eligible_count']}**.",
        f"- The six complete rows are price-only statuses (**{summary['price_only_status_count']}**): labels remain null and no net return is reported because no explicit funding attestation was supplied.",
        f"- Actual statuses: `{json.dumps(summary['actual_status_counts'], sort_keys=True)}`.",
        f"- Post-stop statuses: `{json.dumps(summary['post_stop_status_counts'], sort_keys=True)}`.",
        "",
        "The primary `data/normalized/klines` snapshot contains no June/July windows for this cohort. The configured run also includes the readable local `data_live/normalized/klines` snapshot as a secondary parquet source; event-level path counts aggregate all configured parquet roots and do not attribute rows to one root. Archive CSV files are not used by this replay. Missing windows are not counted as failures or wins.",
        "",
        "## Event-level audit",
        "",
        "| # | Symbol | Source feature time | Normalized signal | Entry | Price coverage | Bars/prefix | Funding | Actual | Post-stop | Eligible |",
        "|---:|---|---|---|---:|---|---:|---|---|---|---:|",
    ]
    for event in artifact["events"]:
        coverage = event["price_coverage"]
        funding = event["funding_coverage"]
        lines.append(
            "| "
            + " | ".join(
                _md_cell(value)
                for value in (
                    event["event_id"],
                    event["symbol"],
                    event["source_feature_time"],
                    _iso(event["signal_time"]),
                    event["entry_price"],
                    coverage["coverage_status"],
                    f"{coverage['contiguous_prefix_bars']}/{coverage['expected_bars']}",
                    f"{funding['funding_status']} ({funding['window_rows']})",
                    event["actual_status"],
                    event["post_stop_status"],
                    "yes" if event["actual_eligible"] else "no",
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "- `legacy_entry1_label` is retained only for row identity and compatibility auditing; it is not a compact weighted-average outcome.",
            "- `actual_status` and `post_stop_status` are separate. A post-stop target cannot turn a stopped trade into a win.",
            "- A partial early target/stop, if present, is shown but remains ineligible because the full price path is not covered. An event with no first forward bar is explicitly excluded as missing data.",
            "- This report is diagnostic evidence about local coverage and engine behavior. It must not be read as a claim that V3 improved precision, EV, or promotion eligibility.",
            "",
            f"Replay artifact: `{artifact.get('replay_output', 'artifacts/v3_compact_replay_champion_audit_20260915.json')}`.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _resolve_roots(values: list[str] | None, defaults: tuple[Path, ...]) -> tuple[Path, ...]:
    raw = [Path(value) for value in values] if values else list(defaults)
    return tuple((value if value.is_absolute() else REPO_ROOT / value).resolve() for value in raw)


def run(
    *,
    source_path: Path = DEFAULT_SOURCE,
    output_path: Path = DEFAULT_OUTPUT,
    report_path: Path = DEFAULT_REPORT,
    kline_roots: tuple[Path, ...] = DEFAULT_KLINE_ROOTS,
    funding_roots: tuple[Path, ...] = DEFAULT_FUNDING_ROOTS,
    attestation_path: Path | None = None,
) -> dict[str, Any]:
    source_path = source_path.resolve()
    source_payload, source_events = _source_events(source_path)
    attestations = _attestations(attestation_path)
    kline_data = LocalData(kline_roots, "klines")
    funding_data = LocalData(funding_roots, "funding")
    try:
        events = [
            _event_result(
                event=event,
                klines=kline_data,
                funding=funding_data,
                attestations=attestations,
            )
            for event in source_events
        ]
    finally:
        kline_data.close()
        funding_data.close()

    artifact = build_artifact(
        source_path=source_path,
        source_payload=source_payload,
        events=events,
        kline_roots=kline_roots,
        funding_roots=funding_roots,
        attestation_path=attestation_path,
    )
    output_path = output_path.resolve()
    artifact["replay_output"] = str(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False, default=_json_default) + "\n",
        encoding="utf-8",
    )
    write_report(report_path.resolve(), artifact)
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--kline-root",
        action="append",
        help="normalized kline root; repeat to include multiple local roots",
    )
    parser.add_argument(
        "--funding-root",
        action="append",
        help="normalized funding root; repeat to include multiple local roots",
    )
    parser.add_argument(
        "--funding-attestation",
        type=Path,
        help="optional JSON object of symbol -> {from?, through, source?}; never inferred",
    )
    args = parser.parse_args(argv)
    source = args.source if args.source.is_absolute() else REPO_ROOT / args.source
    output = args.output if args.output.is_absolute() else REPO_ROOT / args.output
    report = args.report if args.report.is_absolute() else REPO_ROOT / args.report
    attestation = None
    if args.funding_attestation:
        attestation = (
            args.funding_attestation
            if args.funding_attestation.is_absolute()
            else REPO_ROOT / args.funding_attestation
        )
    artifact = run(
        source_path=source,
        output_path=output,
        report_path=report,
        kline_roots=_resolve_roots(args.kline_root, DEFAULT_KLINE_ROOTS),
        funding_roots=_resolve_roots(args.funding_root, DEFAULT_FUNDING_ROOTS),
        attestation_path=attestation,
    )
    summary = artifact["summary"]
    print(
        "replayed="
        f"{summary['event_count']} evaluated={summary['evaluated_count']} "
        f"complete={summary['complete_price_path_count']} "
        f"excluded_missing={summary['excluded_missing_klines_count']} "
        f"funding_eligible={summary['funding_eligible_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
