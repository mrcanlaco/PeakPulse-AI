"""Audit the frozen V3 cohort against the annual cached market inputs.

This command is deliberately an input audit, not a backtest.  It reads the
frozen V3 reference/replay artifacts and the annual price/funding manifests,
verifies their recorded hashes and ranges, and retains one result for every
lane row.  It never downloads data, mutates a source artifact, changes a
threshold, or evaluates an outcome.

The annual funding cache is treated as an attestation only when the manifest,
artifact checksum, requested range, row-provenance sidecar, and actual raw
settlements all agree.  A regular settlement cadence is a diagnostic inside
that decision; cadence by itself can never make an input eligible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Reuse the canonical price normalizer used to publish the annual cache.  The
# audit adds stricter duplicate/range checks around it; normalization is not a
# substitute for those checks.
from scripts.annual_profit_prices import normalize_price_frame  # noqa: E402

UTC = timezone.utc
BAR_INTERVAL_MS = 5 * 60 * 1000
BAR_INTERVAL = timedelta(minutes=5)
HORIZON = timedelta(hours=48)
FUNDING_INTERVAL = timedelta(hours=4)
FUNDING_TOLERANCE = BAR_INTERVAL
FUNDING_ALIGNMENT_TOLERANCE_MS = 50
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")

PRICE_COLUMNS = (
    "symbol",
    "open_time",
    "close_time",
    "open",
    "high",
    "low",
    "close",
)
FUNDING_COLUMNS = ("symbol", "funding_time", "funding_rate", "mark_price")

DEFAULT_REFERENCE = REPO_ROOT / "artifacts" / "v3_six_month_20260915" / "oos_reference_events.json"
DEFAULT_PRICE_REPLAY = REPO_ROOT / "artifacts" / "v3_six_month_20260915" / "oos_price_replay.json"
DEFAULT_DATA_MANIFEST = REPO_ROOT / "artifacts" / "annual_profit_20260918" / "data" / "manifest.json"
DEFAULT_FUNDING_ROOT = REPO_ROOT / "artifacts" / "annual_profit_20260918" / "data" / "funding"
DEFAULT_PRICE_MANIFEST = REPO_ROOT / "artifacts" / "annual_profit_20260918" / "prices" / "price_manifest.json"
DEFAULT_PRICE_ROOT = REPO_ROOT / "artifacts" / "annual_profit_20260918" / "prices" / "klines" / "5m"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "v3_improvement_20260922" / "input_audit_final"


class AuditInputError(RuntimeError):
    """Raised when the frozen inputs cannot be loaded at all."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _parse_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = pd.Timestamp(value).to_pydatetime()
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timestamp is not timezone-aware: {value!r}")
    return parsed.astimezone(UTC)


def _epoch_ms(value: Any) -> int:
    return int(round(_parse_utc(value).timestamp() * 1000))


def _strict_provider_int(value: Any) -> int | None:
    """Return an integer-valued JSON field without coercing unknown values."""

    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def _iso_ms(value: Any) -> str:
    parsed = _parse_utc(value)
    return parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _iso_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _json_load(path: Path, role: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditInputError(f"cannot load {role}: {path}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AuditInputError(f"{role} must be a JSON object: {path}")
    return payload


def _resolve_path(raw: Any, base: Path) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate


def _input_digest(role: str, path: Path, expected_sha256: str | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "role": role,
        "path": str(path),
        "exists": path.is_file(),
        "expected_sha256": expected_sha256,
        "actual_sha256": None,
        "sha256_match": False if expected_sha256 else None,
        "status": "missing" if not path.is_file() else "pending",
    }
    if not path.is_file():
        return record
    try:
        actual = sha256_file(path)
    except OSError as exc:
        record.update({"status": "unreadable", "error": str(exc)})
        return record
    record["actual_sha256"] = actual
    if expected_sha256 is None:
        record.update({"status": "hashed", "sha256_match": None})
    elif not SHA256_RE.fullmatch(str(expected_sha256)):
        record.update({"status": "invalid_expected_sha256", "sha256_match": False})
    else:
        matched = actual.lower() == str(expected_sha256).lower()
        record.update({"status": "verified" if matched else "sha256_mismatch", "sha256_match": matched})
    return record


def _manifest_path_check(
    role: str,
    raw_path: Any,
    base: Path,
    expected_sha256: Any,
) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    path = _resolve_path(raw_path, base)
    record: dict[str, Any] = {
        "role": role,
        "declared_path": raw_path,
        "resolved_path": str(path) if path else None,
        "expected_sha256": expected_sha256,
        "actual_sha256": None,
        "sha256_match": False,
    }
    if path is None:
        reasons.append(f"{role}_path_missing")
        return record, reasons
    if not isinstance(expected_sha256, str) or not SHA256_RE.fullmatch(expected_sha256):
        reasons.append(f"{role}_sha256_missing_or_invalid")
        record["status"] = "invalid_expected_sha256"
        return record, reasons
    if not path.is_file():
        reasons.append(f"{role}_artifact_missing")
        record["status"] = "missing"
        return record, reasons
    try:
        actual = sha256_file(path)
    except OSError as exc:
        reasons.append(f"{role}_artifact_unreadable")
        record.update({"status": "unreadable", "error": str(exc)})
        return record, reasons
    matched = actual.lower() == expected_sha256.lower()
    record.update({"actual_sha256": actual, "sha256_match": matched, "status": "verified" if matched else "sha256_mismatch"})
    if not matched:
        reasons.append(f"{role}_sha256_mismatch")
    return record, reasons


def _source_snapshot_sha256(records: Sequence[Mapping[str, Any]]) -> str:
    entries = [
        {
            "file_name": str(record.get("file_name") or ""),
            "file_sha256": str(record.get("file_sha256") or ""),
            "symbol": str(record.get("symbol") or ""),
        }
        for record in sorted(records, key=lambda item: str(item.get("file_name") or ""))
    ]
    return _canonical_sha256(entries)


def _funding_row_sha256(symbol: str, funding_time_ms: int, rate: float, mark_price: float) -> str:
    return _canonical_sha256(
        {
            "funding_rate": float(rate).hex(),
            "funding_time_ms": int(funding_time_ms),
            "mark_price": float(mark_price).hex(),
            "symbol": str(symbol).strip().upper(),
        }
    )


def _rounded_bar_ms(timestamp_ms: int) -> int:
    return ((int(timestamp_ms) + BAR_INTERVAL_MS // 2) // BAR_INTERVAL_MS) * BAR_INTERVAL_MS


def _timestamp_series_ms(series: pd.Series) -> tuple[pd.Series, np.ndarray]:
    parsed = pd.to_datetime(series, utc=True, errors="coerce")
    valid = ~parsed.isna()
    values = np.full(len(parsed), np.iinfo(np.int64).min, dtype=np.int64)
    if bool(valid.any()):
        backing = parsed.array.asi8
        unit = getattr(parsed.array, "unit", "ns")
        if unit == "s":
            scaled = backing.astype(np.int64, copy=False) * 1_000
        elif unit == "ms":
            scaled = backing.astype(np.int64, copy=False)
        elif unit == "us":
            scaled = backing.astype(np.int64, copy=False) // 1_000
        else:
            scaled = backing.astype(np.int64, copy=False) // 1_000_000
        values[valid.to_numpy()] = scaled[valid.to_numpy()]
    return parsed, values


def _protocol_document_digest(
    path: Path,
    expected_sha256: str,
) -> dict[str, Any]:
    """Check a reviewed Markdown document with a narrowly scoped line-ending rule.

    Binary and structured artifacts continue to use :func:`sha256_file` directly.
    This exception is intentionally limited to the protocol Markdown document and
    replaces only CRLF byte pairs with LF; it does not strip whitespace, alter
    lone CR bytes, decode/re-encode text, or apply any other normalization.
    """

    record: dict[str, Any] = {
        "path": str(path),
        "expected_sha256": expected_sha256,
        "raw_sha256": None,
        "normalized_sha256": None,
        "raw_sha256_match": False,
        "normalized_sha256_match": False,
        "sha256_match": False,
        "normalization_method": "none",
        "status": "missing" if not path.is_file() else "pending",
    }
    if not path.is_file():
        return record
    try:
        raw = path.read_bytes()
    except OSError as exc:
        record.update({"status": "unreadable", "error": str(exc)})
        return record

    raw_sha = hashlib.sha256(raw).hexdigest()
    record["raw_sha256"] = raw_sha
    record["raw_sha256_match"] = raw_sha.lower() == expected_sha256.lower()
    # The reviewed equivalence is byte-level CRLF -> LF only.  UTF-8 validation
    # makes this a Markdown text check rather than an accidental binary rewrite.
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        if record["raw_sha256_match"]:
            record.update({"sha256_match": True, "normalization_method": "byte_exact", "status": "verified"})
            return record
        record.update({"status": "sha256_mismatch", "error": f"protocol document is not UTF-8: {exc}"})
        return record
    normalized = raw.replace(b"\r\n", b"\n")
    normalized_sha = hashlib.sha256(normalized).hexdigest()
    record["normalized_sha256"] = normalized_sha
    record["normalized_sha256_match"] = normalized_sha.lower() == expected_sha256.lower()
    if record["raw_sha256_match"]:
        record.update({"sha256_match": True, "normalization_method": "byte_exact", "status": "verified"})
    elif record["normalized_sha256_match"]:
        record.update({
            "sha256_match": True,
            "normalization_method": "crlf_to_lf",
            "status": "verified_equivalent",
        })
    else:
        record["status"] = "sha256_mismatch"
    return record


def _new_event_bar_result(event: Mapping[str, Any]) -> dict[str, Any]:
    signal_ms = _epoch_ms(event["signal_time_utc"])
    horizon_ms = _epoch_ms(_parse_utc(event["signal_time_utc"]) + HORIZON)
    return {
        "signal_time_utc": _iso_ms(event["signal_time_utc"]),
        "horizon_time_utc": _iso_ms(_parse_utc(event["signal_time_utc"]) + HORIZON),
        "entry_bar_available": False,
        "entry_bar_valid": False,
        "entry_close": None,
        "expected_forward_bar_count": int((horizon_ms - signal_ms) // BAR_INTERVAL_MS),
        "valid_forward_bar_count": 0,
        "missing_forward_bar_count": int((horizon_ms - signal_ms) // BAR_INTERVAL_MS),
        "missing_forward_bar_times_utc": [],
        "price_path_ready": False,
        "reasons": [],
    }


def _price_manifest_configuration_check(manifest: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    config = manifest.get("configuration")
    requested = manifest.get("requested_ranges")
    checks: dict[str, Any] = {
        "manifest_status": manifest.get("status"),
        "manifest_version": manifest.get("manifest_version"),
        "configuration_sha256": manifest.get("configuration_sha256"),
        "configuration_sha256_match": False,
        "requested_ranges": requested,
        "bar_interval_ms": config.get("bar_interval_ms") if isinstance(config, Mapping) else None,
        "price_root_declared": manifest.get("price_root"),
    }
    if manifest.get("status") != "complete":
        reasons.append("price_manifest_not_complete")
    if not isinstance(config, Mapping):
        reasons.append("price_manifest_configuration_missing")
    else:
        expected_hash = manifest.get("configuration_sha256")
        if isinstance(expected_hash, str) and SHA256_RE.fullmatch(expected_hash):
            checks["configuration_sha256_actual"] = _canonical_sha256(config)
            checks["configuration_sha256_match"] = checks["configuration_sha256_actual"].lower() == expected_hash.lower()
            if not checks["configuration_sha256_match"]:
                reasons.append("price_manifest_configuration_sha256_mismatch")
        else:
            reasons.append("price_manifest_configuration_sha256_missing_or_invalid")
        if config.get("bar_interval_ms") != BAR_INTERVAL_MS:
            reasons.append("price_manifest_bar_interval_mismatch")
    if not isinstance(requested, Mapping):
        reasons.append("price_manifest_requested_ranges_missing")
    else:
        for name in ("warmup_start_utc", "cutoff_utc_exclusive"):
            try:
                _epoch_ms(requested[name])
            except (KeyError, TypeError, ValueError, OverflowError):
                reasons.append(f"price_manifest_{name}_invalid")
    return checks, reasons


def _price_event_summary(
    event: Mapping[str, Any],
    normalized_close_ms: np.ndarray,
    close_by_signal: Mapping[int, float],
    common_reasons: Sequence[str],
    range_check: Mapping[str, Any],
) -> dict[str, Any]:
    result = _new_event_bar_result(event)
    reasons = list(dict.fromkeys([*common_reasons, *range_check.get("reasons", [])]))
    signal_ms = _epoch_ms(event["signal_time_utc"])
    horizon_ms = _epoch_ms(_parse_utc(event["signal_time_utc"]) + HORIZON)
    expected_forward = list(range(signal_ms + BAR_INTERVAL_MS, horizon_ms + 1, BAR_INTERVAL_MS))
    available = set(int(value) for value in normalized_close_ms.tolist())
    entry_available = signal_ms in available
    missing = [value for value in expected_forward if value not in available]
    result.update(
        {
            "entry_bar_available": entry_available,
            "entry_bar_valid": entry_available and not reasons,
            "entry_close": close_by_signal.get(signal_ms),
            "entry_boundary_utc": _iso_ms(datetime.fromtimestamp(signal_ms / 1000, UTC)),
            "valid_forward_bar_count": len(expected_forward) - len(missing),
            "missing_forward_bar_count": len(missing),
            "missing_forward_bar_times_utc": [_iso_ms(datetime.fromtimestamp(value / 1000, UTC)) for value in missing],
            "reasons": reasons,
        }
    )
    if not entry_available:
        result["reasons"].append("missing_entry_bar")
    if missing:
        result["reasons"].append("missing_forward_price_bars")
    result["reasons"] = list(dict.fromkeys(result["reasons"]))
    result["price_path_ready"] = not result["reasons"]
    return result


def _audit_price_symbol(
    symbol: str,
    events: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    manifest_path: Path,
    price_root: Path,
    common_manifest_reasons: Sequence[str],
) -> dict[str, Any]:
    entry = (manifest.get("symbols") or {}).get(symbol)
    result: dict[str, Any] = {
        "symbol": symbol,
        "manifest_entry_present": isinstance(entry, Mapping),
        "manifest_status": entry.get("status") if isinstance(entry, Mapping) else None,
        "manifest_path": str(manifest_path),
        "declared_price_root": manifest.get("price_root"),
        "cli_price_root": str(price_root),
        "artifact": {},
        "coverage": {},
        "validation": {"status": "failed", "reasons": []},
        "events": {},
    }
    reasons = list(common_manifest_reasons)
    if not isinstance(entry, Mapping):
        reasons.append("price_manifest_symbol_entry_missing")
        result["validation"]["reasons"] = list(dict.fromkeys(reasons))
        for event in events:
            event_result = _new_event_bar_result(event)
            event_result["reasons"] = list(dict.fromkeys(reasons + ["price_symbol_audit_failed"]))
            result["events"][event["event_id"]] = event_result
        return result

    output_path = _resolve_path(entry.get("output_path"), manifest_path.parent)
    result["artifact"]["declared_path"] = entry.get("output_path")
    result["artifact"]["resolved_path"] = str(output_path) if output_path else None
    result["artifact"]["expected_sha256"] = entry.get("output_sha256")
    if entry.get("status") != "ready":
        reasons.append("price_manifest_symbol_not_ready")
    if output_path is None:
        reasons.append("price_output_path_missing")
    elif not output_path.is_file():
        reasons.append("price_output_artifact_missing")
    expected_sha = entry.get("output_sha256")
    if not isinstance(expected_sha, str) or not SHA256_RE.fullmatch(expected_sha):
        reasons.append("price_output_sha256_missing_or_invalid")
    elif output_path is not None and output_path.is_file():
        try:
            actual_sha = sha256_file(output_path)
        except OSError as exc:
            actual_sha = None
            result["artifact"]["error"] = str(exc)
            reasons.append("price_output_artifact_unreadable")
        result["artifact"]["actual_sha256"] = actual_sha
        result["artifact"]["sha256_match"] = actual_sha is not None and actual_sha.lower() == expected_sha.lower()
        if not result["artifact"]["sha256_match"]:
            reasons.append("price_output_sha256_mismatch")

    coverage = entry.get("coverage")
    audit = coverage.get("after_backfill_audit") if isinstance(coverage, Mapping) else None
    if not isinstance(audit, Mapping):
        audit = None
        reasons.append("price_manifest_coverage_missing")
    result["coverage"] = {
        "entry": coverage,
        "after_backfill_audit": audit,
    }
    output_columns = entry.get("output_columns")
    if not isinstance(output_columns, list) or not output_columns:
        reasons.append("price_manifest_output_columns_missing")

    open_ms = np.empty(0, dtype=np.int64)
    normalized_close_ms = np.empty(0, dtype=np.int64)
    close_by_signal: dict[int, float] = {}
    if not reasons and output_path is not None:
        try:
            frame = pd.read_parquet(output_path)
            result["validation"]["row_count"] = int(len(frame))
            result["validation"]["columns"] = list(frame.columns)
            if list(frame.columns) != output_columns:
                reasons.append("price_output_columns_mismatch")
            if not set(PRICE_COLUMNS).issubset(frame.columns):
                reasons.append("price_output_required_columns_missing")
            if not reasons:
                parsed_open, open_ms = _timestamp_series_ms(frame["open_time"])
                parsed_close, close_ms = _timestamp_series_ms(frame["close_time"])
                if bool(parsed_open.isna().any()):
                    reasons.append("price_output_invalid_open_time")
                if bool(parsed_close.isna().any()):
                    reasons.append("price_output_invalid_close_time")
                if not reasons:
                    if bool(pd.Series(open_ms).duplicated().any()):
                        reasons.append("price_output_duplicate_open_time")
                    if bool((open_ms % BAR_INTERVAL_MS != 0).any()):
                        reasons.append("price_output_unaligned_open_time")
                    expected_close = open_ms + BAR_INTERVAL_MS - 1
                    if bool((close_ms != expected_close).any()):
                        reasons.append("price_output_close_time_rule_mismatch")
                    symbols = frame["symbol"].astype("string").str.upper()
                    if bool(symbols.isna().any()) or bool((symbols != symbol.upper()).any()):
                        reasons.append("price_output_symbol_mismatch")
                    values = frame[["open", "high", "low", "close"]].apply(
                        pd.to_numeric, errors="coerce"
                    ).to_numpy(dtype=float)
                    bad = ~np.isfinite(values).all(axis=1)
                    bad |= (values <= 0).any(axis=1)
                    bad |= values[:, 1] < np.maximum(values[:, 0], values[:, 2])
                    bad |= values[:, 2] > np.minimum(values[:, 0], values[:, 3])
                    if bool(bad.any()):
                        reasons.append("price_output_invalid_ohlc")
                if not reasons:
                    # Run the repository's canonical validator as a final
                    # schema/normalization check.  Duplicates were rejected
                    # above before this helper's duplicate-collapse policy.
                    normalized = normalize_price_frame(frame, symbol)
                    _, normalized_open = _timestamp_series_ms(normalized["open_time"])
                    _, raw_close_ms = _timestamp_series_ms(normalized["close_time"])
                    normalized_close = pd.to_numeric(normalized["close"], errors="coerce").to_numpy(dtype=float)
                    normalized_close_ms = raw_close_ms + 1
                    close_by_signal = {
                        int(timestamp): float(close)
                        for timestamp, close in zip(normalized_close_ms.tolist(), normalized_close.tolist())
                    }
                    open_ms = normalized_open
                    result["validation"]["normalized_row_count"] = int(len(normalized))
        except Exception as exc:
            reasons.append(f"price_output_validation_error:{type(exc).__name__}")
            result["validation"]["error"] = str(exc)

    result["validation"]["reasons"] = list(dict.fromkeys(reasons))
    result["validation"]["status"] = "ok" if not reasons else "failed"
    result["validation"]["observed_open_time_min_utc"] = (
        _iso_ms(datetime.fromtimestamp(int(open_ms.min()) / 1000, UTC)) if len(open_ms) else None
    )
    result["validation"]["observed_open_time_max_utc"] = (
        _iso_ms(datetime.fromtimestamp(int(open_ms.max()) / 1000, UTC)) if len(open_ms) else None
    )

    for event in events:
        range_reasons: list[str] = []
        range_payload: dict[str, Any] = {}
        signal_ms = _epoch_ms(event["signal_time_utc"])
        horizon_ms = _epoch_ms(_parse_utc(event["signal_time_utc"]) + HORIZON)
        if audit is None:
            range_reasons.append("price_manifest_coverage_missing")
        else:
            range_payload = {
                key: audit.get(key)
                for key in (
                    "requested_range_start_ms",
                    "requested_cutoff_ms",
                    "coverage_start_ms",
                    "coverage_end_exclusive_ms",
                    "missing_bar_count",
                    "internal_missing_bar_count",
                    "leading_missing_bar_count",
                    "trailing_missing_bar_count",
                )
            }
            try:
                requested_start = int(audit["requested_range_start_ms"])
                requested_end = int(audit["requested_cutoff_ms"])
                coverage_start = int(audit["coverage_start_ms"])
                coverage_end = int(audit["coverage_end_exclusive_ms"])
                if requested_start > signal_ms or requested_end <= horizon_ms:
                    range_reasons.append("price_manifest_requested_range_does_not_cover_event")
                if coverage_start > signal_ms or coverage_end <= horizon_ms:
                    range_reasons.append("price_manifest_actual_coverage_does_not_cover_event")
                if int(audit.get("missing_bar_count", -1)) != 0:
                    range_reasons.append("price_manifest_reports_missing_bars")
            except (KeyError, TypeError, ValueError):
                range_reasons.append("price_manifest_coverage_range_invalid")
        range_payload["reasons"] = range_reasons
        event_result = _price_event_summary(event, normalized_close_ms, close_by_signal, reasons, range_payload)
        result["events"][event["event_id"]] = event_result
    return result


def _validate_data_manifest_identity(manifest: Mapping[str, Any], manifest_path: Path) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    audit = manifest.get("audit")
    universe = manifest.get("universe")
    funding = manifest.get("funding")
    checks: dict[str, Any] = {
        "protocol": manifest.get("protocol"),
        "manifest_status": funding.get("status") if isinstance(funding, Mapping) else None,
        "manifest_path": str(manifest_path),
        "audit_source_snapshot_sha256": audit.get("source_snapshot_sha256") if isinstance(audit, Mapping) else None,
        "universe_sha256": universe.get("sha256") if isinstance(universe, Mapping) else None,
        "protocol_document_sha256": manifest.get("protocol_document_sha256"),
        "source_snapshot_sha256_match": False,
        "universe_sha256_match": False,
        "protocol_document_sha256_match": False,
    }
    if not isinstance(audit, Mapping) or not isinstance(audit.get("files"), list):
        reasons.append("data_manifest_audit_files_missing")
    else:
        for record in audit["files"]:
            if not isinstance(record, Mapping) or not isinstance(record.get("file_sha256"), str) or not SHA256_RE.fullmatch(record.get("file_sha256", "")):
                reasons.append("data_manifest_file_sha256_missing_or_invalid")
                break
        expected_snapshot = audit.get("source_snapshot_sha256")
        actual_snapshot = _source_snapshot_sha256(audit["files"])
        checks["source_snapshot_sha256_actual"] = actual_snapshot
        if not isinstance(expected_snapshot, str) or not SHA256_RE.fullmatch(expected_snapshot):
            reasons.append("data_manifest_source_snapshot_sha256_missing_or_invalid")
        else:
            checks["source_snapshot_sha256_match"] = actual_snapshot.lower() == expected_snapshot.lower()
            if not checks["source_snapshot_sha256_match"]:
                reasons.append("data_manifest_source_snapshot_sha256_mismatch")
    if not isinstance(universe, Mapping):
        reasons.append("data_manifest_universe_missing")
    else:
        universe_path = _resolve_path(universe.get("path"), manifest_path.parent)
        expected_universe_sha = universe.get("sha256")
        checks["universe_path"] = str(universe_path) if universe_path else None
        if universe_path is None or not isinstance(expected_universe_sha, str) or not SHA256_RE.fullmatch(expected_universe_sha):
            reasons.append("data_manifest_universe_sha256_missing_or_invalid")
        elif not universe_path.is_file():
            reasons.append("data_manifest_universe_artifact_missing")
        else:
            actual_universe_sha = sha256_file(universe_path)
            checks["universe_sha256_actual"] = actual_universe_sha
            checks["universe_sha256_match"] = actual_universe_sha.lower() == expected_universe_sha.lower()
            if not checks["universe_sha256_match"]:
                reasons.append("data_manifest_universe_sha256_mismatch")
    document_path = _resolve_path(manifest.get("protocol_document"), REPO_ROOT)
    expected_document_sha = manifest.get("protocol_document_sha256")
    checks["protocol_document_path"] = str(document_path) if document_path else None
    if document_path is None or not isinstance(expected_document_sha, str) or not SHA256_RE.fullmatch(expected_document_sha):
        reasons.append("data_manifest_protocol_document_sha256_missing_or_invalid")
    elif not document_path.is_file():
        reasons.append("data_manifest_protocol_document_missing")
    else:
        document_digest = _protocol_document_digest(document_path, expected_document_sha)
        checks.update(
            {
                "protocol_document_sha256_actual": document_digest.get("raw_sha256"),
                "protocol_document_sha256_raw": document_digest.get("raw_sha256"),
                "protocol_document_sha256_normalized": document_digest.get("normalized_sha256"),
                "protocol_document_sha256_raw_match": document_digest.get("raw_sha256_match"),
                "protocol_document_sha256_normalized_match": document_digest.get("normalized_sha256_match"),
                "protocol_document_sha256_match": document_digest.get("sha256_match"),
                "protocol_document_digest_method": document_digest.get("normalization_method"),
                "protocol_document_digest_status": document_digest.get("status"),
            }
        )
        if not document_digest.get("sha256_match"):
            reasons.append("data_manifest_protocol_document_sha256_mismatch")
    if not isinstance(funding, Mapping) or not isinstance(funding.get("requested_window"), Mapping):
        reasons.append("data_manifest_funding_requested_window_missing")
    return checks, list(dict.fromkeys(reasons))


def _frame_funding_rows(frame: pd.DataFrame, symbol: str) -> tuple[np.ndarray, dict[int, tuple[float, float]], list[str]]:
    reasons: list[str] = []
    if list(frame.columns) != list(FUNDING_COLUMNS):
        reasons.append("funding_output_columns_mismatch")
        return np.empty(0, dtype=np.int64), {}, reasons
    parsed, times = _timestamp_series_ms(frame["funding_time"])
    if bool(parsed.isna().any()):
        reasons.append("funding_output_invalid_time")
    if getattr(frame["funding_time"].dtype, "tz", None) is None:
        reasons.append("funding_output_timezone_missing")
    if bool(pd.Series(times).duplicated().any()):
        reasons.append("funding_output_duplicate_time")
    symbols = frame["symbol"].astype("string").str.upper()
    if bool(symbols.isna().any()) or bool((symbols != symbol.upper()).any()):
        reasons.append("funding_output_symbol_mismatch")
    rates = pd.to_numeric(frame["funding_rate"], errors="coerce").to_numpy(dtype=float)
    marks = pd.to_numeric(frame["mark_price"], errors="coerce").to_numpy(dtype=float)
    if bool((~np.isfinite(rates)).any()):
        reasons.append("funding_output_invalid_rate")
    if bool((~np.isfinite(marks) | (marks <= 0)).any()):
        reasons.append("funding_output_invalid_mark_price")
    rows: dict[int, tuple[float, float]] = {}
    if not reasons:
        rows = {int(timestamp): (float(rate), float(mark)) for timestamp, rate, mark in zip(times.tolist(), rates.tolist(), marks.tolist())}
    return times, rows, reasons


def _cadence_check(
    times_ms: Sequence[int],
    signal_ms: int,
    horizon_ms: int,
    *,
    provider_coverage_certified: bool = False,
) -> dict[str, Any]:
    window = sorted(int(value) for value in times_ms if signal_ms < int(value) <= horizon_ms)
    result: dict[str, Any] = {
        "settlement_count": len(window),
        "first_settlement_utc": _iso_ms(datetime.fromtimestamp(window[0] / 1000, UTC)) if window else None,
        "last_settlement_utc": _iso_ms(datetime.fromtimestamp(window[-1] / 1000, UTC)) if window else None,
        "maximum_gap_seconds": None,
        "first_gap_seconds": None,
        "last_gap_seconds": None,
        "ok": False,
        "reason": None,
        "not_sufficient_alone": True,
        "diagnostic_only": True,
        "diagnostic_applicable": bool(provider_coverage_certified),
        "provider_coverage_certified": bool(provider_coverage_certified),
        "used_for_funding_readiness": False,
    }
    if not window:
        result["reason"] = "no_settlements"
        return result
    result["first_gap_seconds"] = (window[0] - signal_ms) / 1000
    result["last_gap_seconds"] = (horizon_ms - window[-1]) / 1000
    gaps = [later - earlier for earlier, later in zip(window, window[1:])]
    result["maximum_gap_seconds"] = max(gaps) / 1000 if gaps else 0.0
    limit_ms = int((FUNDING_INTERVAL + FUNDING_TOLERANCE).total_seconds() * 1000)
    if window[0] - signal_ms > limit_ms:
        result["reason"] = "first_settlement_gap"
    elif any(gap > limit_ms for gap in gaps):
        result["reason"] = "settlement_gap"
    elif horizon_ms - window[-1] > limit_ms:
        result["reason"] = "last_settlement_gap"
    else:
        result["ok"] = True
    return result


def _funding_extraction_provenance_check(
    entry: Mapping[str, Any],
    requested_payload: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Validate the completion evidence emitted by ``annual_profit_data``.

    The downloader declares completeness from terminal pagination state, not from
    an observed settlement interval.  Keep that distinction explicit here so a
    provider with an eight-hour schedule is not rejected by a four-hour guess.
    """

    reasons: list[str] = []
    provenance = entry.get("provenance") if isinstance(entry.get("provenance"), Mapping) else {}
    page_provenance = entry.get("page_provenance")
    completion_basis = entry.get("completion_basis")
    requested_start = _strict_provider_int(requested_payload.get("start_ms"))
    requested_end_exclusive = _strict_provider_int(requested_payload.get("end_exclusive_ms"))
    api_end = requested_end_exclusive - 1 if requested_end_exclusive is not None else None
    if (
        requested_start is None
        or requested_end_exclusive is None
        or requested_start >= requested_end_exclusive
    ):
        reasons.append("funding_provider_requested_range_invalid")

    checks: dict[str, Any] = {
        "transport_status": entry.get("transport_status"),
        "final_page_status": entry.get("final_page_status"),
        "completion_basis": completion_basis,
        "page_count": entry.get("page_count"),
        "request_count": entry.get("request_count"),
        "page_provenance_count": len(page_provenance) if isinstance(page_provenance, list) else None,
        "pagination_rule": provenance.get("pagination"),
        "end_time_policy": provenance.get("end_time_policy"),
        "page_chain_certified": False,
        "terminal_evidence_certified": False,
        "complete_request_certified": False,
        "schedule_certified": False,
    }

    expected_pagination = "startTime = greatest returned fundingTime + 1ms"
    expected_end_policy = "fixed API endTime = requested exclusive end - 1ms"
    if provenance.get("pagination") != expected_pagination:
        reasons.append("funding_provider_pagination_policy_missing_or_mismatch")
    if provenance.get("end_time_policy") != expected_end_policy:
        reasons.append("funding_provider_end_time_policy_missing_or_mismatch")

    known_completion_bases = {
        "empty_terminal_page",
        "page_shorter_than_limit",
        "end_time_reached",
        "requested_end_bound",
        "checksum_verified_monthly_archives",
    }
    if not isinstance(completion_basis, str) or not completion_basis:
        reasons.append("funding_provider_completion_basis_missing")
    elif completion_basis not in known_completion_bases:
        reasons.append("funding_provider_completion_basis_unknown")

    page_count = _strict_provider_int(entry.get("page_count"))
    request_count = _strict_provider_int(entry.get("request_count"))
    if page_count is None or request_count is None:
        reasons.append("funding_provider_page_counts_invalid")
    else:
        if page_count < 0 or request_count < 0:
            reasons.append("funding_provider_page_counts_invalid")
        if request_count < page_count:
            reasons.append("funding_provider_request_count_invalid")

    is_archive_completion = completion_basis == "checksum_verified_monthly_archives"
    if is_archive_completion:
        if entry.get("transport_status") != "archive_fallback":
            reasons.append("funding_provider_archive_transport_not_fallback")
        if entry.get("final_page_status") != "complete_archives":
            reasons.append("funding_provider_archive_terminal_status_mismatch")
        archive = entry.get("archive_fallback")
        if not isinstance(archive, Mapping):
            reasons.append("funding_provider_archive_completion_evidence_missing")
        else:
            if archive.get("status") != "complete":
                reasons.append("funding_provider_archive_not_complete")
            archive_errors = archive.get("errors")
            if not isinstance(archive_errors, list) or archive_errors:
                reasons.append("funding_provider_archive_errors_present_or_unknown")
            if archive.get("checksum_verified") is not True:
                reasons.append("funding_provider_archive_checksum_not_verified")
            archive_count = _strict_provider_int(archive.get("archive_count"))
            missing_month_count = _strict_provider_int(archive.get("missing_month_count"))
            if archive_count is None or archive_count < 1:
                reasons.append("funding_provider_archive_count_invalid")
            if missing_month_count != 0:
                reasons.append("funding_provider_archive_missing_months")
            archive_window = archive.get("requested_window")
            try:
                archive_start = _epoch_ms(archive_window["start_utc"])
                archive_end = _epoch_ms(archive_window["end_exclusive_utc"])
                if (
                    requested_start is None
                    or requested_end_exclusive is None
                    or archive_start != requested_start
                    or archive_end != requested_end_exclusive
                ):
                    reasons.append("funding_provider_archive_requested_range_mismatch")
            except (KeyError, TypeError, ValueError, OverflowError):
                reasons.append("funding_provider_archive_requested_range_invalid")
        checks["page_chain_certified"] = True
    else:
        if entry.get("transport_status") != "success":
            reasons.append("funding_provider_transport_not_success")
        if entry.get("final_page_status") not in {"complete", "empty_response"}:
            reasons.append("funding_provider_terminal_page_not_complete")
        if page_count is not None and page_count < 1:
            reasons.append("funding_provider_page_count_invalid")
        if not isinstance(page_provenance, list) or page_count is None or len(page_provenance) != page_count:
            reasons.append("funding_provider_page_provenance_incomplete")

        parsed_pages: list[dict[str, Any] | None] = []
        page_limit = _strict_provider_int(provenance.get("page_limit"))
        if page_limit is None or not 1 <= page_limit <= 1000:
            reasons.append("funding_provider_page_limit_missing_or_invalid")

        attempts_total = 0
        attempts_complete = True
        if isinstance(page_provenance, list):
            for position, raw_page in enumerate(page_provenance, start=1):
                if not isinstance(raw_page, Mapping):
                    reasons.append("funding_provider_page_provenance_invalid")
                    parsed_pages.append(None)
                    attempts_complete = False
                    continue

                page_number = _strict_provider_int(raw_page.get("page"))
                if page_number != position:
                    reasons.append("funding_provider_page_index_mismatch")

                if raw_page.get("transport_status") != "success":
                    reasons.append("funding_provider_page_transport_not_success")
                status_code = _strict_provider_int(raw_page.get("status_code"))
                if status_code != 200:
                    reasons.append("funding_provider_page_status_code_invalid")

                attempts = _strict_provider_int(raw_page.get("attempts"))
                if attempts is None or attempts < 1:
                    reasons.append("funding_provider_page_attempts_invalid")
                    attempts_complete = False
                else:
                    attempts_total += attempts

                limit = _strict_provider_int(raw_page.get("limit"))
                if limit is None or not 1 <= limit <= 1000:
                    reasons.append("funding_provider_page_limit_invalid")
                    limit = None
                elif page_limit is not None and limit != page_limit:
                    reasons.append("funding_provider_page_limit_mismatch")

                response_count = _strict_provider_int(raw_page.get("response_count"))
                if response_count is None:
                    reasons.append("funding_provider_page_response_count_missing_or_invalid")
                elif limit is not None and not 0 <= response_count <= limit:
                    reasons.append("funding_provider_page_response_count_out_of_range")

                page_start = _strict_provider_int(raw_page.get("requested_start_ms"))
                page_end = _strict_provider_int(raw_page.get("requested_end_ms"))
                if page_start is None:
                    reasons.append("funding_provider_page_start_missing")
                if page_end is None:
                    reasons.append("funding_provider_page_end_missing")
                if api_end is not None and page_end is not None and page_end != api_end:
                    reasons.append("funding_provider_page_end_policy_mismatch")
                if (
                    requested_start is not None
                    and api_end is not None
                    and page_start is not None
                    and (page_start < requested_start or page_start > api_end)
                ):
                    reasons.append("funding_provider_page_requested_range_invalid")
                if page_start is not None and page_end is not None and page_start > page_end:
                    reasons.append("funding_provider_page_requested_range_invalid")

                minimum = _strict_provider_int(raw_page.get("min_raw_time_ms"))
                maximum = _strict_provider_int(raw_page.get("max_raw_time_ms"))
                if response_count == 0:
                    if minimum is not None or maximum is not None:
                        reasons.append("funding_provider_empty_page_range_mismatch")
                elif response_count is not None and response_count > 0:
                    if minimum is None or maximum is None:
                        reasons.append("funding_provider_page_raw_range_missing_or_invalid")
                    elif minimum > maximum:
                        reasons.append("funding_provider_page_raw_range_invalid")
                    elif (
                        page_start is None
                        or api_end is None
                        or minimum < page_start
                        or maximum > api_end
                    ):
                        reasons.append("funding_provider_page_raw_range_out_of_request")

                parsed_pages.append(
                    {
                        "page": page_number,
                        "requested_start_ms": page_start,
                        "requested_end_ms": page_end,
                        "limit": limit,
                        "attempts": attempts,
                        "response_count": response_count,
                        "min_raw_time_ms": minimum,
                        "max_raw_time_ms": maximum,
                    }
                )

        if request_count is not None and attempts_complete and isinstance(page_provenance, list):
            if request_count != attempts_total:
                reasons.append("funding_provider_request_count_mismatch")

        if parsed_pages and parsed_pages[0] is not None and requested_start is not None:
            if parsed_pages[0]["requested_start_ms"] != requested_start:
                reasons.append("funding_provider_first_page_start_mismatch")

        for previous, current in zip(parsed_pages, parsed_pages[1:]):
            if previous is None or current is None:
                reasons.append("funding_provider_page_chain_incomplete")
                continue
            previous_count = previous["response_count"]
            previous_limit = previous["limit"]
            previous_max = previous["max_raw_time_ms"]
            current_start = current["requested_start_ms"]
            if previous_count == 0:
                reasons.append("funding_provider_page_chain_after_empty_terminal")
            elif (
                previous_count is not None
                and previous_limit is not None
                and previous_count < previous_limit
            ):
                reasons.append("funding_provider_page_chain_after_short_terminal")
            elif previous_max is None:
                reasons.append("funding_provider_page_cursor_missing")
            elif api_end is not None and previous_max >= api_end:
                reasons.append("funding_provider_page_chain_after_end_terminal")
            elif current_start != previous_max + 1:
                reasons.append("funding_provider_page_cursor_mismatch")
                if (
                    current_start is not None
                    and previous["requested_start_ms"] is not None
                    and current_start <= previous["requested_start_ms"]
                ):
                    reasons.append("funding_provider_page_pagination_non_progress")

        last_page = parsed_pages[-1] if parsed_pages else None
        if completion_basis == "empty_terminal_page":
            if entry.get("final_page_status") != "empty_response":
                reasons.append("funding_provider_terminal_status_mismatch")
            if (
                last_page is None
                or last_page["response_count"] != 0
                or last_page["min_raw_time_ms"] is not None
                or last_page["max_raw_time_ms"] is not None
            ):
                reasons.append("funding_provider_terminal_empty_evidence_mismatch")
        elif completion_basis == "page_shorter_than_limit":
            if entry.get("final_page_status") != "complete":
                reasons.append("funding_provider_terminal_status_mismatch")
            if (
                last_page is None
                or last_page["response_count"] is None
                or last_page["limit"] is None
                or last_page["response_count"] <= 0
                or last_page["response_count"] >= last_page["limit"]
                or last_page["max_raw_time_ms"] is None
                or api_end is None
                or last_page["max_raw_time_ms"] >= api_end
            ):
                reasons.append("funding_provider_terminal_short_page_evidence_mismatch")
        elif completion_basis == "end_time_reached":
            if entry.get("final_page_status") != "complete":
                reasons.append("funding_provider_terminal_status_mismatch")
            if (
                last_page is None
                or last_page["response_count"] is None
                or last_page["response_count"] <= 0
                or last_page["max_raw_time_ms"] is None
                or api_end is None
                or last_page["max_raw_time_ms"] != api_end
            ):
                reasons.append("funding_provider_terminal_end_bound_evidence_mismatch")
        elif completion_basis == "requested_end_bound":
            if entry.get("final_page_status") != "complete":
                reasons.append("funding_provider_terminal_status_mismatch")
            resume = entry.get("resume")
            resume_start = _strict_provider_int(resume.get("resume_start_ms")) if isinstance(resume, Mapping) else None
            prefix_end = _strict_provider_int(resume.get("prefix_end_exclusive_ms")) if isinstance(resume, Mapping) else None
            if (
                not isinstance(resume, Mapping)
                or resume.get("used_existing_provenance") is not True
                or requested_end_exclusive is None
                or resume_start != requested_end_exclusive
                or prefix_end != requested_end_exclusive
            ):
                reasons.append("funding_provider_requested_end_bound_evidence_missing")
            last_is_empty = (
                last_page is not None
                and last_page["response_count"] == 0
                and last_page["min_raw_time_ms"] is None
                and last_page["max_raw_time_ms"] is None
            )
            last_is_short = (
                last_page is not None
                and last_page["response_count"] is not None
                and last_page["limit"] is not None
                and 0 < last_page["response_count"] < last_page["limit"]
                and last_page["max_raw_time_ms"] is not None
                and api_end is not None
                and last_page["max_raw_time_ms"] < api_end
            )
            last_is_end = (
                last_page is not None
                and last_page["response_count"] is not None
                and last_page["response_count"] > 0
                and last_page["max_raw_time_ms"] is not None
                and api_end is not None
                and last_page["max_raw_time_ms"] == api_end
            )
            if not (last_is_empty or last_is_short or last_is_end):
                reasons.append("funding_provider_requested_end_bound_terminal_evidence_missing")

        checks["page_chain_certified"] = not reasons

    checks["terminal_evidence_certified"] = not reasons
    checks["complete_request_certified"] = not reasons
    return checks, list(dict.fromkeys(reasons))


def _audit_funding_symbol(
    symbol: str,
    events: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    manifest_path: Path,
    funding_root: Path,
    common_manifest_reasons: Sequence[str],
) -> dict[str, Any]:
    funding = manifest.get("funding") if isinstance(manifest.get("funding"), Mapping) else {}
    entry = (funding.get("symbols") or {}).get(symbol) if isinstance(funding, Mapping) else None
    result: dict[str, Any] = {
        "symbol": symbol,
        "manifest_entry_present": isinstance(entry, Mapping),
        "manifest_status": entry.get("status") if isinstance(entry, Mapping) else None,
        "coverage_status": entry.get("coverage_status") if isinstance(entry, Mapping) else None,
        "manifest_path": str(manifest_path),
        "declared_funding_root": str(funding_root),
        "artifact": {},
        "requested_window": {},
        "provenance": {},
        "validation": {"status": "failed", "reasons": []},
        "events": {},
    }
    reasons = list(common_manifest_reasons)
    if not isinstance(entry, Mapping):
        reasons.append("funding_manifest_symbol_entry_missing")
        result["validation"]["reasons"] = list(dict.fromkeys(reasons))
        for event in events:
            result["events"][event["event_id"]] = _funding_event_summary(
                event, np.empty(0, dtype=np.int64), {}, reasons, {}, False, False
            )
        return result

    if entry.get("status") != "complete":
        reasons.append("funding_manifest_symbol_not_complete")
    if entry.get("coverage_status") != "complete":
        reasons.append("funding_manifest_coverage_not_complete")
    if entry.get("data_status") != "present":
        reasons.append("funding_manifest_data_not_present")
    if int(entry.get("invalid_record_count", 0) or 0) != 0:
        reasons.append("funding_manifest_invalid_records")
    if int(entry.get("duplicate_timestamp_conflict_count", 0) or 0) != 0:
        reasons.append("funding_manifest_duplicate_conflict")
    if int(entry.get("mark_price_conflict_count", 0) or 0) != 0:
        reasons.append("funding_manifest_mark_price_conflict")
    if entry.get("errors"):
        reasons.append("funding_manifest_has_errors")
    if entry.get("schema") != list(FUNDING_COLUMNS):
        reasons.append("funding_manifest_schema_missing_or_mismatch")

    top_requested = funding.get("requested_window") if isinstance(funding, Mapping) else None
    requested = entry.get("requested_window")
    requested_payload: dict[str, Any] = {"entry": requested, "top_level": top_requested, "match": False, "reasons": []}
    try:
        if not isinstance(requested, Mapping) or not isinstance(top_requested, Mapping):
            raise ValueError("requested window missing")
        entry_start = _strict_provider_int(requested.get("start_ms"))
        entry_end = _strict_provider_int(requested.get("end_exclusive_ms"))
        api_end = _strict_provider_int(requested.get("api_end_time_ms_inclusive"))
        if entry_start is None or entry_end is None or api_end is None:
            raise ValueError("requested window fields must be integers")
        top_start = _epoch_ms(top_requested["start_utc"])
        top_end = _epoch_ms(top_requested["end_exclusive_utc"])
        requested_payload.update({"start_ms": entry_start, "end_exclusive_ms": entry_end, "top_start_ms": top_start, "top_end_ms": top_end})
        requested_payload["match"] = entry_start == top_start and entry_end == top_end
        if not requested_payload["match"]:
            requested_payload["reasons"].append("funding_entry_requested_window_mismatch")
            reasons.append("funding_entry_requested_window_mismatch")
        if api_end != entry_end - 1:
            requested_payload["reasons"].append("funding_api_end_policy_mismatch")
            reasons.append("funding_api_end_policy_mismatch")
    except (KeyError, TypeError, ValueError, OverflowError):
        requested_payload["reasons"].append("funding_requested_window_invalid")
        reasons.append("funding_requested_window_invalid")
    result["requested_window"] = requested_payload
    extraction_checks, extraction_reasons = _funding_extraction_provenance_check(entry, requested_payload)
    result["provenance"]["extraction"] = extraction_checks
    reasons.extend(extraction_reasons)

    artifact_path = _resolve_path(entry.get("artifact_path"), manifest_path.parent)
    expected_artifact_sha = entry.get("artifact_sha256")
    result["artifact"].update({
        "declared_path": entry.get("artifact_path"),
        "resolved_path": str(artifact_path) if artifact_path else None,
        "expected_sha256": expected_artifact_sha,
    })
    if artifact_path is None:
        reasons.append("funding_artifact_path_missing")
    elif not artifact_path.is_file():
        reasons.append("funding_artifact_missing")
    if not isinstance(expected_artifact_sha, str) or not SHA256_RE.fullmatch(expected_artifact_sha):
        reasons.append("funding_artifact_sha256_missing_or_invalid")
    elif artifact_path is not None and artifact_path.is_file():
        try:
            actual = sha256_file(artifact_path)
        except OSError as exc:
            actual = None
            result["artifact"]["error"] = str(exc)
            reasons.append("funding_artifact_unreadable")
        result["artifact"]["actual_sha256"] = actual
        result["artifact"]["sha256_match"] = actual is not None and actual.lower() == expected_artifact_sha.lower()
        if not result["artifact"]["sha256_match"]:
            reasons.append("funding_artifact_sha256_mismatch")

    sidecar_path = _resolve_path(entry.get("row_provenance_artifact_path"), manifest_path.parent)
    expected_sidecar_sha = entry.get("row_provenance_artifact_sha256")
    result["provenance"].update({
        "source": (entry.get("provenance") or {}).get("source") if isinstance(entry.get("provenance"), Mapping) else None,
        "endpoint": (entry.get("provenance") or {}).get("endpoint") if isinstance(entry.get("provenance"), Mapping) else None,
        "page_count": entry.get("page_count"),
        "request_count": entry.get("request_count"),
        "declared_sidecar_path": entry.get("row_provenance_artifact_path"),
        "resolved_sidecar_path": str(sidecar_path) if sidecar_path else None,
        "expected_sidecar_sha256": expected_sidecar_sha,
        "sidecar_sha256": None,
        "sidecar_sha256_match": False,
    })
    sidecar: Mapping[str, Any] | None = None
    if sidecar_path is None:
        reasons.append("funding_row_provenance_path_missing")
    elif not sidecar_path.is_file():
        reasons.append("funding_row_provenance_missing")
    if not isinstance(expected_sidecar_sha, str) or not SHA256_RE.fullmatch(expected_sidecar_sha):
        reasons.append("funding_row_provenance_sha256_missing_or_invalid")
    elif sidecar_path is not None and sidecar_path.is_file():
        try:
            actual_sidecar_sha = sha256_file(sidecar_path)
            result["provenance"]["sidecar_sha256"] = actual_sidecar_sha
            result["provenance"]["sidecar_sha256_match"] = actual_sidecar_sha.lower() == expected_sidecar_sha.lower()
            if not result["provenance"]["sidecar_sha256_match"]:
                reasons.append("funding_row_provenance_sha256_mismatch")
            loaded_sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            if isinstance(loaded_sidecar, Mapping):
                sidecar = loaded_sidecar
            else:
                reasons.append("funding_row_provenance_not_object")
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            reasons.append("funding_row_provenance_unreadable")
            result["provenance"]["error"] = str(exc)

    frame = None
    times = np.empty(0, dtype=np.int64)
    row_values: dict[int, tuple[float, float]] = {}
    artifact_hash_ok = bool(result["artifact"].get("sha256_match"))
    if artifact_hash_ok and artifact_path is not None:
        try:
            frame = pd.read_parquet(artifact_path)
            result["validation"]["row_count"] = int(len(frame))
            times, row_values, frame_reasons = _frame_funding_rows(frame, symbol)
            reasons.extend(frame_reasons)
        except Exception as exc:
            reasons.append(f"funding_output_validation_error:{type(exc).__name__}")
            result["validation"]["error"] = str(exc)
    if sidecar is None and not reasons:
        reasons.append("funding_row_provenance_unavailable")
    if sidecar is not None:
        if sidecar.get("format") != "annual_profit_funding_row_provenance_v1":
            reasons.append("funding_row_provenance_format_mismatch")
        if sidecar.get("symbol") != symbol:
            reasons.append("funding_row_provenance_symbol_mismatch")
        side_rows = sidecar.get("rows")
        if not isinstance(side_rows, list):
            reasons.append("funding_row_provenance_rows_missing")
        else:
            result["provenance"]["sidecar_row_count"] = len(side_rows)
            if sidecar.get("row_count") != len(side_rows):
                reasons.append("funding_row_provenance_row_count_mismatch")
            if entry.get("row_provenance_count") != len(side_rows):
                reasons.append("funding_manifest_provenance_count_mismatch")
            if len(times) != len(side_rows):
                reasons.append("funding_artifact_sidecar_count_mismatch")
            side_by_time: dict[int, Mapping[str, Any]] = {}
            for side_row in side_rows:
                if not isinstance(side_row, Mapping):
                    reasons.append("funding_row_provenance_invalid_row")
                    continue
                try:
                    row_time = int(side_row["funding_time_ms"])
                    row_hash = str(side_row["source_row_sha256"])
                    if not SHA256_RE.fullmatch(row_hash):
                        raise ValueError("invalid row hash")
                    if row_time in side_by_time:
                        reasons.append("funding_row_provenance_duplicate_time")
                    side_by_time[row_time] = side_row
                except (KeyError, TypeError, ValueError):
                    reasons.append("funding_row_provenance_invalid_row")
            if row_values and side_by_time:
                for row_time, (rate, mark) in row_values.items():
                    side_row = side_by_time.get(row_time)
                    if side_row is None:
                        reasons.append("funding_row_provenance_missing_time")
                        continue
                    computed = _funding_row_sha256(symbol, row_time, rate, mark)
                    if computed.lower() != str(side_row.get("source_row_sha256")).lower():
                        reasons.append("funding_row_provenance_row_hash_mismatch")
                for side_time in side_by_time:
                    if side_time not in row_values:
                        reasons.append("funding_row_provenance_extra_time")

    declared_range = entry.get("range")
    result["validation"]["declared_range"] = declared_range
    if not isinstance(declared_range, Mapping):
        reasons.append("funding_manifest_range_missing")
    elif row_values:
        try:
            declared_count = int(declared_range["row_count"])
            declared_first = _epoch_ms(declared_range["first_funding_time_utc"])
            declared_last = _epoch_ms(declared_range["last_funding_time_utc"])
            actual_first = int(times.min())
            actual_last = int(times.max())
            if declared_count != len(row_values) or declared_first != actual_first or declared_last != actual_last:
                reasons.append("funding_manifest_range_mismatch")
        except (KeyError, TypeError, ValueError, OverflowError):
            reasons.append("funding_manifest_range_invalid")

    # The funding snapshot is an internal provenance chain.  It must point at
    # the same frozen universe and protocol document that this audit loaded.
    snapshot = entry.get("snapshot")
    data_audit = manifest.get("audit") if isinstance(manifest.get("audit"), Mapping) else {}
    data_universe = manifest.get("universe") if isinstance(manifest.get("universe"), Mapping) else {}
    if not isinstance(snapshot, Mapping):
        reasons.append("funding_snapshot_provenance_missing")
    else:
        for field, expected in (
            ("source_snapshot_sha256", data_audit.get("source_snapshot_sha256")),
            ("universe_sha256", data_universe.get("sha256")),
            ("protocol_document_sha256", manifest.get("protocol_document_sha256")),
        ):
            if not isinstance(snapshot.get(field), str) or not SHA256_RE.fullmatch(snapshot.get(field, "")):
                reasons.append(f"funding_snapshot_{field}_missing_or_invalid")
            elif expected and snapshot.get(field).lower() != str(expected).lower():
                reasons.append(f"funding_snapshot_{field}_mismatch")
        audit_files = data_audit.get("files") if isinstance(data_audit, Mapping) else None
        if isinstance(audit_files, list):
            matching_source = next((item for item in audit_files if item.get("symbol") == symbol), None)
            if matching_source is None:
                reasons.append("funding_snapshot_source_symbol_missing")
            elif snapshot.get("source_file_sha256") != matching_source.get("file_sha256"):
                reasons.append("funding_snapshot_source_file_sha256_mismatch")

    result["validation"]["reasons"] = list(dict.fromkeys(reasons))
    result["validation"]["status"] = "ok" if not reasons else "failed"
    result["validation"]["observed_row_count"] = int(len(row_values))
    result["validation"]["observed_first_utc"] = _iso_ms(datetime.fromtimestamp(int(times.min()) / 1000, UTC)) if len(times) else None
    result["validation"]["observed_last_utc"] = _iso_ms(datetime.fromtimestamp(int(times.max()) / 1000, UTC)) if len(times) else None

    for event in events:
        event_horizon = _epoch_ms(_parse_utc(event["signal_time_utc"]) + HORIZON)
        requested_covers = bool(
            requested_payload.get("match")
            and int(requested_payload.get("top_start_ms", 2**63 - 1)) <= _epoch_ms(event["signal_time_utc"])
            and int(requested_payload.get("top_end_ms", -1)) > event_horizon
        )
        manifest_backed = bool(not reasons and requested_covers)
        result["events"][event["event_id"]] = _funding_event_summary(
            event,
            times,
            row_values,
            reasons,
            requested_payload,
            requested_covers,
            manifest_backed,
        )
    return result


def _funding_event_summary(
    event: Mapping[str, Any],
    times: np.ndarray,
    row_values: Mapping[int, tuple[float, float]],
    common_reasons: Sequence[str],
    requested: Mapping[str, Any],
    requested_covers: bool,
    manifest_backed: bool,
) -> dict[str, Any]:
    signal_ms = _epoch_ms(event["signal_time_utc"])
    horizon_ms = _epoch_ms(_parse_utc(event["signal_time_utc"]) + HORIZON)
    raw_times = [
        int(value)
        for value in times.tolist()
        if signal_ms < int(value) <= horizon_ms + FUNDING_ALIGNMENT_TOLERANCE_MS
    ]
    normalized = [
        _rounded_bar_ms(value)
        for value in raw_times
        if abs(_rounded_bar_ms(value) - value) <= FUNDING_ALIGNMENT_TOLERANCE_MS
        and signal_ms < _rounded_bar_ms(value) <= horizon_ms
    ]
    alignment_bad = len(raw_times) - len(normalized)
    normalized_duplicates = len(normalized) - len(set(normalized))
    cadence = _cadence_check(
        normalized,
        signal_ms,
        horizon_ms,
        provider_coverage_certified=manifest_backed,
    )
    reasons = list(common_reasons)
    requested_reasons = list(requested.get("reasons", []))
    reasons.extend(requested_reasons)
    if not requested_covers and "funding_request_does_not_cover_event" not in reasons:
        reasons.append("funding_request_does_not_cover_event")
    if not raw_times:
        reasons.append("funding_no_settlements")
    if alignment_bad:
        reasons.append("funding_timestamp_not_5m_boundary")
    if normalized_duplicates:
        reasons.append("funding_duplicate_normalized_settlement")
    reasons = list(dict.fromkeys(reasons))
    raw_coverage = manifest_backed and bool(raw_times) and alignment_bad == 0 and normalized_duplicates == 0
    return {
        "funding_requested_range_covers_event": bool(requested_covers),
        "settlement_rows_in_window": len(raw_times),
        "first_settlement_utc": cadence["first_settlement_utc"],
        "last_settlement_utc": cadence["last_settlement_utc"],
        "settlement_times_utc": [_iso_ms(datetime.fromtimestamp(value / 1000, UTC)) for value in raw_times],
        "normalized_settlement_times_utc": [
            _iso_ms(datetime.fromtimestamp(value / 1000, UTC)) for value in sorted(set(normalized))
        ],
        "normalized_settlement_count": len(set(normalized)),
        "normalized_duplicate_count": normalized_duplicates,
        "unaligned_settlement_count": alignment_bad,
        "cadence_heuristic": cadence,
        "cadence_diagnostic_reason": cadence["reason"],
        "cadence_diagnostic_reasons": (
            []
            if not cadence["diagnostic_applicable"] or cadence["ok"]
            else [f"funding_cadence_{cadence['reason'] or 'not_verified'}"]
        ),
        "raw_funding_coverage_certified": raw_coverage,
        "funding_input_ready": raw_coverage,
        "financial_outcome_eligible": None,
        "financial_outcome_status": "not_computed",
        "reasons": reasons,
    }


def _reference_score_summary(event: Mapping[str, Any], reference: Mapping[str, Any]) -> dict[str, Any]:
    model = event.get("model_provenance") if isinstance(event.get("model_provenance"), Mapping) else {}
    source = event.get("source") if isinstance(event.get("source"), Mapping) else {}
    pit = event.get("pit") if isinstance(event.get("pit"), Mapping) else {}
    caveats = [
        "persisted calibrated fold OOS score is retained as provenance, not a compact weighted-average outcome probability",
        "per-fold model artifact hashes were not persisted",
        "label_contract is legacy Entry-1 48h and is not a compact execution outcome",
        "the six-month export is retrospective recycled OOS, not an untouched holdout",
    ]
    return {
        "score": event.get("score"),
        "raw_score": event.get("raw_score"),
        "score_field": model.get("score_field"),
        "score_kind": model.get("score_kind"),
        "fold": event.get("fold"),
        "fold_threshold": event.get("fold_threshold"),
        "threshold_is_row_fold_threshold": model.get("threshold_is_row_fold_threshold"),
        "selection_threshold": model.get("selection_threshold"),
        "post_confirmation_score_floor": model.get("post_confirmation_score_floor"),
        "fold_model_hash_available": model.get("fold_model_hash_available"),
        "fold_model_sha256": model.get("fold_model_sha256"),
        "source_artifact": source.get("artifact"),
        "source_sha256": source.get("sha256"),
        "source_key": source.get("source_key"),
        "pit_exact_join_matched": pit.get("exact_join_matched"),
        "label_contract": event.get("label_contract"),
        "caveats": caveats,
        "not_used_for_input_eligibility": True,
        "reference_model_provenance_status": reference.get("model_provenance", {}).get("fold_model_hash_note") if isinstance(reference.get("model_provenance"), Mapping) else None,
    }


def _identity_record(event: Mapping[str, Any], *, replay: bool = False) -> dict[str, Any]:
    def normalized_time(value: Any) -> str | None:
        try:
            return _iso_ms(value) if value is not None else None
        except (TypeError, ValueError, OverflowError):
            return str(value) if value is not None else None

    if replay:
        return {
            "lane": event.get("lane"),
            "event_id": event.get("event_id"),
            "source_event_id": event.get("source_event_id"),
            "source_episode_id": event.get("source_episode_id"),
            "symbol": event.get("symbol"),
            "feature_time_utc": normalized_time(event.get("feature_time_utc")),
            "signal_time_utc": normalized_time(event.get("signal_time_utc")),
            "fold": event.get("fold"),
            "score": event.get("source_score", event.get("score")),
            "raw_score": event.get("source_raw_score", event.get("raw_score")),
        }
    return {
        "lane": event.get("lane"),
        "event_id": event.get("event_id"),
        "source_event_id": event.get("source_event_id"),
        "source_episode_id": event.get("source_episode_id"),
        "symbol": event.get("symbol"),
        "feature_time_utc": normalized_time(event.get("feature_time_utc")),
        "signal_time_utc": normalized_time(event.get("signal_time_utc")),
        "fold": event.get("fold"),
        "score": event.get("score"),
        "raw_score": event.get("raw_score"),
    }


def _frozen_identity(reference: Mapping[str, Any], replay: Mapping[str, Any], reference_path: Path, replay_path: Path) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    reference_events = reference.get("events")
    replay_events = replay.get("events")
    if not isinstance(reference_events, list):
        raise AuditInputError("reference artifact events must be a list")
    if not isinstance(replay_events, list):
        raise AuditInputError("price replay artifact events must be a list")
    reference_ids = [event.get("event_id") for event in reference_events if isinstance(event, Mapping)]
    replay_ids = [event.get("event_id") for event in replay_events if isinstance(event, Mapping)]
    if len(reference_events) != len(reference_ids) or any(not value for value in reference_ids):
        reasons.append("reference_event_identity_missing")
    if len(replay_events) != len(replay_ids) or any(not value for value in replay_ids):
        reasons.append("replay_event_identity_missing")
    if len(reference_ids) != len(set(reference_ids)):
        reasons.append("reference_event_id_duplicate")
    if len(replay_ids) != len(set(replay_ids)):
        reasons.append("replay_event_id_duplicate")
    ref_by_id = {event.get("event_id"): event for event in reference_events if isinstance(event, Mapping)}
    replay_by_id = {event.get("event_id"): event for event in replay_events if isinstance(event, Mapping)}
    if set(ref_by_id) != set(replay_by_id):
        reasons.append("reference_replay_event_id_set_mismatch")
    identity_mismatches: list[str] = []
    for event_id in sorted(set(ref_by_id) & set(replay_by_id)):
        if _identity_record(ref_by_id[event_id]) != _identity_record(replay_by_id[event_id], replay=True):
            identity_mismatches.append(str(event_id))
    if identity_mismatches:
        reasons.append("reference_replay_event_identity_mismatch")
    source_rows = [event for event in reference_events if isinstance(event, Mapping)]
    source_to_lanes: dict[str, set[str]] = defaultdict(set)
    for event in source_rows:
        source_to_lanes[str(event.get("source_event_id"))].add(str(event.get("lane")))
    overlaps = sorted(source_id for source_id, lanes in source_to_lanes.items() if len(lanes) > 1)
    lane_counts = Counter(str(event.get("lane")) for event in source_rows)
    identity_rows = sorted((_identity_record(event) for event in source_rows), key=lambda value: (str(value.get("lane")), str(value.get("event_id"))))
    replay_identity_rows = sorted((_identity_record(event, replay=True) for event in replay_events if isinstance(event, Mapping)), key=lambda value: (str(value.get("lane")), str(value.get("event_id"))))
    source_declared_overlap = (reference.get("coverage") or {}).get("source_events_in_both_lanes") if isinstance(reference.get("coverage"), Mapping) else None
    if source_declared_overlap is not None and int(source_declared_overlap) != len(overlaps):
        reasons.append("reference_declared_overlap_count_mismatch")
    replay_declared_overlap = (replay.get("coverage") or {}).get("source_events_in_both_lanes") if isinstance(replay.get("coverage"), Mapping) else None
    if replay_declared_overlap is not None and int(replay_declared_overlap) != len(overlaps):
        reasons.append("replay_declared_overlap_count_mismatch")
    identity = {
        "reference_artifact": str(reference_path),
        "reference_artifact_sha256": sha256_file(reference_path),
        "price_replay_artifact": str(replay_path),
        "price_replay_artifact_sha256": sha256_file(replay_path),
        "reference_event_count": len(reference_events),
        "replay_event_count": len(replay_events),
        "lane_counts": dict(sorted(lane_counts.items())),
        "unique_source_event_count": len(source_to_lanes),
        "source_event_overlap_count": len(overlaps),
        "overlapping_source_event_ids": overlaps,
        "reference_event_identity_sha256": _canonical_sha256(identity_rows),
        "replay_event_identity_sha256": _canonical_sha256(replay_identity_rows),
        "reference_replay_identity_match": not identity_mismatches and set(ref_by_id) == set(replay_by_id),
        "identity_mismatch_event_ids": identity_mismatches,
        "reasons": list(dict.fromkeys(reasons)),
    }
    return identity, list(dict.fromkeys(reasons))


def _replay_link(reference_event: Mapping[str, Any], replay_event: Mapping[str, Any] | None) -> dict[str, Any]:
    if replay_event is None:
        return {"present": False, "reasons": ["replay_event_missing"]}
    def numeric_equal(left: Any, right: Any) -> bool:
        try:
            return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False

    checks = {
        "lane": reference_event.get("lane") == replay_event.get("lane"),
        "source_event_id": reference_event.get("source_event_id") == replay_event.get("source_event_id"),
        "source_episode_id": reference_event.get("source_episode_id") == replay_event.get("source_episode_id"),
        "symbol": reference_event.get("symbol") == replay_event.get("symbol"),
        "signal_time": _identity_record(reference_event).get("signal_time_utc") == _identity_record(replay_event, replay=True).get("signal_time_utc"),
        "feature_time": _identity_record(reference_event).get("feature_time_utc") == _identity_record(replay_event, replay=True).get("feature_time_utc"),
        "score": numeric_equal(reference_event.get("score"), replay_event.get("source_score")),
        "raw_score": numeric_equal(reference_event.get("raw_score"), replay_event.get("source_raw_score")),
    }
    reasons = [f"replay_link_{key}_mismatch" for key, value in checks.items() if not value]
    return {"present": True, "checks": checks, "ok": not reasons, "reasons": reasons}


def _resolve_reference_sources(reference: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = reference.get("source") if isinstance(reference.get("source"), Mapping) else {}
    records: list[dict[str, Any]] = []
    for key, expected_key in (("oos_csv", "oos_csv_sha256"), ("timing_lock_json", "timing_lock_sha256")):
        raw = source.get(key)
        path = _resolve_path(raw, REPO_ROOT) if isinstance(raw, str) else None
        expected = source.get(expected_key)
        record = _input_digest(f"frozen_source.{key}", path or Path(str(raw or "")), expected if isinstance(expected, str) else None)
        records.append(record)
    return records


def build_audit(
    *,
    reference_path: Path = DEFAULT_REFERENCE,
    price_replay_path: Path = DEFAULT_PRICE_REPLAY,
    data_manifest_path: Path = DEFAULT_DATA_MANIFEST,
    funding_root: Path = DEFAULT_FUNDING_ROOT,
    price_manifest_path: Path = DEFAULT_PRICE_MANIFEST,
    price_root: Path = DEFAULT_PRICE_ROOT,
) -> dict[str, Any]:
    reference_path = Path(reference_path)
    price_replay_path = Path(price_replay_path)
    data_manifest_path = Path(data_manifest_path)
    funding_root = Path(funding_root)
    price_manifest_path = Path(price_manifest_path)
    price_root = Path(price_root)
    reference = _json_load(reference_path, "frozen reference artifact")
    replay = _json_load(price_replay_path, "frozen price replay artifact")
    data_manifest = _json_load(data_manifest_path, "annual data manifest")
    price_manifest = _json_load(price_manifest_path, "annual price manifest")

    identity, identity_reasons = _frozen_identity(reference, replay, reference_path, price_replay_path)
    reference_digest = _input_digest("frozen_reference_artifact", reference_path)
    replay_digest = _input_digest("frozen_price_replay_artifact", price_replay_path)
    data_digest = _input_digest("annual_data_manifest", data_manifest_path)
    price_digest = _input_digest("annual_price_manifest", price_manifest_path)
    reference_source_digests = _resolve_reference_sources(reference)
    input_digests = [reference_digest, replay_digest, data_digest, price_digest, *reference_source_digests]
    for source_digest in reference_source_digests:
        if source_digest.get("status") != "verified":
            identity_reasons.append(f"{source_digest['role']}_not_verified")
    reference_source = reference.get("source") if isinstance(reference.get("source"), Mapping) else {}
    declared_oos_sha = reference_source.get("oos_csv_sha256")
    event_source_hashes = {
        str((event.get("source") or {}).get("sha256"))
        for event in reference.get("events", [])
        if isinstance(event, Mapping) and isinstance(event.get("source"), Mapping)
    }
    if isinstance(declared_oos_sha, str) and event_source_hashes and event_source_hashes != {declared_oos_sha}:
        identity_reasons.append("reference_event_source_sha256_mismatch")

    declared_reference_hash = (replay.get("source") or {}).get("reference_artifact_sha256") if isinstance(replay.get("source"), Mapping) else None
    if declared_reference_hash and declared_reference_hash.lower() != str(reference_digest.get("actual_sha256", "")).lower():
        identity_reasons.append("replay_declared_reference_artifact_sha256_mismatch")
    declared_reference_path = (replay.get("source") or {}).get("reference_artifact") if isinstance(replay.get("source"), Mapping) else None

    price_manifest_checks, price_manifest_reasons = _price_manifest_configuration_check(price_manifest)
    data_manifest_checks, data_manifest_reasons = _validate_data_manifest_identity(data_manifest, data_manifest_path)

    events = reference.get("events")
    if not isinstance(events, list):
        raise AuditInputError("reference artifact events must be a list")
    replay_by_id = {item.get("event_id"): item for item in replay.get("events", []) if isinstance(item, Mapping)}
    events_by_symbol: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for event in events:
        if not isinstance(event, Mapping):
            continue
        symbol = str(event.get("symbol") or "")
        events_by_symbol[symbol].append(event)

    price_symbols: dict[str, dict[str, Any]] = {}
    funding_symbols: dict[str, dict[str, Any]] = {}
    for symbol, symbol_events in sorted(events_by_symbol.items()):
        price_symbols[symbol] = _audit_price_symbol(
            symbol,
            symbol_events,
            price_manifest,
            price_manifest_path,
            price_root,
            price_manifest_reasons,
        )
        funding_symbols[symbol] = _audit_funding_symbol(
            symbol,
            symbol_events,
            data_manifest,
            data_manifest_path,
            funding_root,
            data_manifest_reasons,
        )

    source_id_counts = Counter(str(event.get("source_event_id")) for event in events if isinstance(event, Mapping))
    source_id_lanes: dict[str, set[str]] = defaultdict(set)
    for event in events:
        if isinstance(event, Mapping):
            source_id_lanes[str(event.get("source_event_id"))].add(str(event.get("lane")))

    event_records: list[dict[str, Any]] = []
    exclusion_counts: Counter[str] = Counter()
    global_identity_reasons = list(dict.fromkeys(identity_reasons))
    for row_index, event in enumerate(events):
        if not isinstance(event, Mapping):
            event_records.append({"row_index": row_index, "event_valid": False, "exclusions": ["event_not_object"]})
            exclusion_counts["event_not_object"] += 1
            continue
        event_id = str(event.get("event_id"))
        symbol = str(event.get("symbol") or "")
        price_event = price_symbols[symbol]["events"].get(event_id, _new_event_bar_result(event))
        funding_event = funding_symbols[symbol]["events"].get(
            event_id,
            _funding_event_summary(
                event,
                np.empty(0, dtype=np.int64),
                {},
                ["funding_symbol_audit_missing"],
                {},
                False,
                False,
            ),
        )
        replay_link = _replay_link(event, replay_by_id.get(event_id))
        reasons = list(dict.fromkeys([
            *global_identity_reasons,
            *price_event.get("reasons", []),
            *funding_event.get("reasons", []),
            *replay_link.get("reasons", []),
        ]))
        for reason in reasons:
            exclusion_counts[reason] += 1
        event_records.append(
            {
                "row_index": row_index,
                "lane_event_key": f"{event.get('lane')}::{event_id}",
                "lane": event.get("lane"),
                "event_id": event_id,
                "source_event_id": event.get("source_event_id"),
                "source_episode_id": event.get("source_episode_id"),
                "symbol": symbol,
                "feature_time_utc": event.get("feature_time_utc"),
                "signal_time_utc": event.get("signal_time_utc"),
                "horizon_time_utc": _iso_ms(_parse_utc(event["signal_time_utc"]) + HORIZON),
                "source_event_occurrence_count": int(source_id_counts[str(event.get("source_event_id"))]),
                "source_event_overlaps_lanes": len(source_id_lanes[str(event.get("source_event_id"))]) > 1,
                "reference": {
                    "accepted": event.get("accepted"),
                    "champion_gate_accepted": (event.get("champion_gate") or {}).get("accepted") if isinstance(event.get("champion_gate"), Mapping) else None,
                    "reason": event.get("reason"),
                    "label_value": event.get("label_value"),
                    "label_contract": event.get("label_contract"),
                    "fold": event.get("fold"),
                    "source": event.get("source"),
                },
                "reference_score_provenance": _reference_score_summary(event, reference),
                "frozen_replay_link": replay_link,
                "prior_replay_diagnostic": {
                    "replay_status": replay_by_id.get(event_id, {}).get("replay_status") if replay_by_id.get(event_id) else None,
                    "prior_price_path_resolved": replay_by_id.get(event_id, {}).get("price_path_resolved") if replay_by_id.get(event_id) else None,
                    "prior_compact_financial_outcome_eligible": replay_by_id.get(event_id, {}).get("compact_financial_outcome_eligible") if replay_by_id.get(event_id) else None,
                    "prior_compact_funding_eligibility": replay_by_id.get(event_id, {}).get("compact_funding_eligibility") if replay_by_id.get(event_id) else None,
                    "not_used_for_current_eligibility": True,
                },
                "price": price_event,
                "funding": funding_event,
                "eligibility": {
                    "global_identity_verified": not global_identity_reasons,
                    "exact_entry_bar": bool(price_event.get("entry_bar_valid")),
                    "valid_48h_price_path": bool(price_event.get("price_path_ready")),
                    "manifest_backed_raw_funding": bool(funding_event.get("raw_funding_coverage_certified")),
                    "financial_replay_input_ready": bool(
                        not global_identity_reasons
                        and price_event.get("price_path_ready")
                        and funding_event.get("funding_input_ready")
                        and replay_link.get("ok", False)
                    ),
                    "financial_outcome_eligible": None,
                    "financial_outcome_status": "not_computed",
                },
                "exclusions": reasons,
            }
        )

    lane_counts = Counter(str(item.get("lane")) for item in event_records)
    lane_summary: dict[str, Any] = {}
    for lane in sorted(lane_counts):
        lane_rows = [item for item in event_records if item.get("lane") == lane]
        lane_summary[lane] = {
            "event_rows": len(lane_rows),
            "exact_entry_bar": sum(item["eligibility"]["exact_entry_bar"] for item in lane_rows),
            "valid_48h_price_path": sum(item["eligibility"]["valid_48h_price_path"] for item in lane_rows),
            "manifest_backed_raw_funding": sum(item["eligibility"]["manifest_backed_raw_funding"] for item in lane_rows),
            "financial_replay_input_ready": sum(item["eligibility"]["financial_replay_input_ready"] for item in lane_rows),
            "exclusion_counts": dict(sorted(Counter(reason for item in lane_rows for reason in item["exclusions"]).items())),
        }
    price_ready = sum(item["eligibility"]["valid_48h_price_path"] for item in event_records)
    funding_manifest_backed = sum(item["eligibility"]["manifest_backed_raw_funding"] for item in event_records)
    funding_ready = sum(bool(item["funding"].get("funding_input_ready")) for item in event_records)
    funding_range_covers = sum(bool(item["funding"].get("funding_requested_range_covers_event")) for item in event_records)
    funding_rows_present = sum(int(item["funding"].get("settlement_rows_in_window", 0) or 0) > 0 for item in event_records)
    funding_cadence_ok = sum(bool((item["funding"].get("cadence_heuristic") or {}).get("ok")) for item in event_records)
    replay_ready = sum(item["eligibility"]["financial_replay_input_ready"] for item in event_records)
    source_ids_overlap = sorted(source_id for source_id, lanes in source_id_lanes.items() if len(lanes) > 1)

    blockers: list[dict[str, Any]] = []
    for code, reason_set, scope in (
        ("frozen_identity", identity_reasons, "cohort"),
        ("price_manifest", price_manifest_reasons, "annual price manifest"),
        ("data_manifest", data_manifest_reasons, "annual data manifest"),
    ):
        for reason in sorted(set(reason_set)):
            detail = None
            if reason == "data_manifest_protocol_document_sha256_mismatch":
                detail = (
                    "Recorded protocol document SHA256 "
                    f"{data_manifest_checks.get('protocol_document_sha256')} does not match local "
                    f"{data_manifest_checks.get('protocol_document_sha256_actual')} at "
                    f"{data_manifest_checks.get('protocol_document_path')}."
                )
            blocker = {"code": reason, "scope": scope, "severity": "blocking"}
            if detail:
                blocker["detail"] = detail
            blockers.append(blocker)
    partial_symbols = sorted(
        symbol for symbol, item in funding_symbols.items() if item.get("manifest_status") != "complete" or item.get("coverage_status") != "complete"
    )
    if partial_symbols:
        blockers.append({
            "code": "partial_funding_symbols",
            "scope": "symbols",
            "severity": "blocking_for_affected_events",
            "symbols": partial_symbols,
            "detail": "Funding entries are partial or non-complete; actual rows are retained diagnostically but cannot certify financial replay input.",
        })
    blockers.append({
        "code": "financial_outcomes_not_computed",
        "scope": "all events",
        "severity": "informational",
        "detail": "This artifact audits inputs only; no fills, exits, costs, funding cash flow, labels, or profit are computed.",
    })

    report = {
        "artifact": "v3_replay_input_audit",
        "artifact_version": "v3_replay_input_audit_v1",
        "generated_at_utc": _iso_datetime(datetime.now(UTC)),
        "status": "completed",
        "scope": {
            "offline_only": True,
            "downloads_performed": False,
            "source_artifacts_mutated": False,
            "thresholds_or_selection_changed": False,
            "real_alerts_sent": False,
            "profit_computed": False,
        },
        "inputs": {
            "sha256s": input_digests,
            "declared_replay_reference_artifact": declared_reference_path,
            "declared_replay_reference_artifact_sha256": declared_reference_hash,
            "manifest_checks": {
                "price": price_manifest_checks,
                "data": data_manifest_checks,
            },
        },
        "frozen_cohort": identity,
        "reference_score_provenance": {
            "status": "retained_as_provenance_only",
            "artifact_model_provenance": reference.get("model_provenance"),
            "source": reference.get("source"),
            "caveats": [
                "No per-fold model hashes were persisted in the source CSV.",
                "The score is a persisted calibrated fold OOS score, not a compact weighted-average outcome probability.",
                "Legacy Entry-1 labels and price_ret_24h are not compact outcome labels.",
                "The cohort is retrospective recycled OOS, not an untouched holdout.",
                "Reference score provenance is never used to certify price or funding coverage.",
            ],
        },
        "summary": {
            "lane_event_rows": len(event_records),
            "unique_source_event_ids": len(source_id_lanes),
            "overlapping_source_event_id_count": len(source_ids_overlap),
            "overlapping_source_event_ids": source_ids_overlap,
            "symbols": len(events_by_symbol),
            "exact_entry_bar_count": sum(item["eligibility"]["exact_entry_bar"] for item in event_records),
            "valid_48h_price_path_count": price_ready,
            "funding_requested_range_covers_count": funding_range_covers,
            "funding_settlement_rows_present_count": funding_rows_present,
            "funding_cadence_heuristic_ok_count": funding_cadence_ok,
            "manifest_backed_raw_funding_count": funding_manifest_backed,
            "funding_input_ready_count": funding_ready,
            "financial_replay_input_ready_count": replay_ready,
            "financial_outcome_computed_count": 0,
            "exclusion_counts": dict(sorted(exclusion_counts.items())),
            "lane_counts": dict(sorted(lane_counts.items())),
            "lane_summary": lane_summary,
        },
        "symbols": {
            symbol: {
                "price": price_symbols[symbol],
                "funding": funding_symbols[symbol],
            }
            for symbol in sorted(events_by_symbol)
        },
        "events": event_records,
        "blockers": blockers,
        "caveats": [
            "Manifest-backed funding provenance certifies this local cached-input audit only; it is not a live-fill guarantee or independent contract-identity attestation.",
            "A partial funding manifest entry is not upgraded by observed cadence or by the presence of rows.",
            "Overlapping lane rows remain separate observations even when source_event_id is shared.",
            "The previous price replay's outcomes and withheld-funding flags are historical diagnostics, not current eligibility decisions.",
        ],
        "next_stage_adapter": {
            "required_event_key": "lane_event_key",
            "source_identity_key": "source_event_id",
            "preserve_overlapping_source_ids": True,
            "eligible_input_field": "eligibility.financial_replay_input_ready",
            "price_artifact_field": "price.artifact.resolved_path",
            "funding_artifact_field": "symbols.<symbol>.funding.artifact.resolved_path",
            "funding_provenance_field": "symbols.<symbol>.funding.provenance.resolved_sidecar_path",
            "revalidate_before_engine": True,
            "outcome_contract_to_apply": "distribution_short_v3_policy_48h",
            "outcome_contract_checksum": "c3fb230c415dce4e60aa0992eacbd0a15ecfb7292a3b6809dff5c1ec17dd5b08",
            "must_not_use": [
                "reference score as a probability",
                "legacy label_value as compact outcome",
                "prior replay actual_outcome or compact_financial_outcome_eligible",
                "new thresholding or selector changes",
            ],
        },
    }
    report["frozen_cohort"]["reasons"] = list(dict.fromkeys(identity_reasons))
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# V3 replay input audit — 2026-09-22",
        "",
        "Offline audit only. No profit, fills, exits, costs, funding cash flow, or alerts were computed.",
        "",
        f"- Cohort: **{summary['lane_event_rows']} lane rows**, **{summary['unique_source_event_ids']} unique source IDs**, **{summary['overlapping_source_event_id_count']} source IDs overlap lanes**.",
        f"- Exact entry bars: **{summary['exact_entry_bar_count']}/{summary['lane_event_rows']}**; complete 48h price paths: **{summary['valid_48h_price_path_count']}/{summary['lane_event_rows']}**.",
        f"- Funding request ranges cover **{summary['funding_requested_range_covers_count']}/{summary['lane_event_rows']}** rows; actual settlement rows are present for **{summary['funding_settlement_rows_present_count']}/{summary['lane_event_rows']}**; cadence diagnostic passes for **{summary['funding_cadence_heuristic_ok_count']}/{summary['lane_event_rows']}**.",
        f"- Manifest-backed raw funding coverage: **{summary['manifest_backed_raw_funding_count']}/{summary['lane_event_rows']}**; strict funding-input ready: **{summary['funding_input_ready_count']}/{summary['lane_event_rows']}**.",
        f"- Strict financial-replay inputs ready: **{summary['financial_replay_input_ready_count']}/{summary['lane_event_rows']}**. Financial outcomes computed: **0**.",
        "",
        "## Lane counts",
        "",
        "| Lane | Rows | Entry | 48h price | Raw funding | Replay inputs |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for lane, item in summary["lane_summary"].items():
        lines.append(
            f"| `{lane}` | {item['event_rows']} | {item['exact_entry_bar']} | {item['valid_48h_price_path']} | {item['manifest_backed_raw_funding']} | {item['financial_replay_input_ready']} |"
        )
    lines.extend([
        "",
        "## Event-level exclusion counts",
        "",
        f"Each count is the number of lane rows carrying the reason, shown as `reason rows / {summary['lane_event_rows']} lane rows`. Reasons may overlap on the same row, so these counts do not sum to unique excluded rows.",
        "",
        "| Exclusion reason | Reason rows / lane rows |",
        "|---|---:|",
    ])
    exclusion_counts = summary.get("exclusion_counts", {})
    if exclusion_counts:
        for reason, count in sorted(exclusion_counts.items()):
            lines.append(f"| `{reason}` | {count}/{summary['lane_event_rows']} |")
    else:
        lines.append(f"| None recorded | 0/{summary['lane_event_rows']} |")
    lines.extend([
        "",
        "## Blocking exclusions",
        "",
    ])
    blocking = [item for item in report["blockers"] if item.get("severity") != "informational"]
    if blocking:
        for item in blocking:
            suffix = f" ({', '.join(item['symbols'])})" if item.get("symbols") else ""
            lines.append(f"- `{item['code']}`{suffix}: {item.get('detail', 'input validation failed.')}")
    else:
        lines.append("- None at the artifact/manifest level.")
    lines.extend([
        "",
        "## Important caveats",
        "",
        "- The annual cache supplies local manifest-backed checksums, requested ranges, and row-provenance sidecars; this is input provenance, not a live-fill guarantee or independent contract-identity attestation.",
        "- Partial funding entries remain excluded even when observed rows look cadence-regular.",
        "- Reference scores are provenance only: no per-fold model hashes, legacy Entry-1 label contract, and retrospective recycled OOS cohort.",
        "- Overlapping lane rows are retained separately; the adapter must not deduplicate them by `source_event_id`.",
        "",
        "## Next-stage adapter",
        "",
        "Use `lane_event_key` for row identity, retain `source_event_id` for source grouping, gate on `eligibility.financial_replay_input_ready`, revalidate the cached hashes before loading bars/funding, and recompute the frozen `distribution_short_v3_policy_48h` outcome. Do not reuse the prior replay outcome or score as a probability.",
        "",
    ])
    return "\n".join(lines)


def write_outputs(report: Mapping[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "input_audit.json"
    markdown_path = output_dir / "input_audit.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--price-replay", type=Path, default=DEFAULT_PRICE_REPLAY)
    parser.add_argument("--data-manifest", type=Path, default=DEFAULT_DATA_MANIFEST)
    parser.add_argument("--funding-root", type=Path, default=DEFAULT_FUNDING_ROOT)
    parser.add_argument("--price-manifest", type=Path, default=DEFAULT_PRICE_MANIFEST)
    parser.add_argument("--price-root", type=Path, default=DEFAULT_PRICE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = build_audit(
            reference_path=args.reference,
            price_replay_path=args.price_replay,
            data_manifest_path=args.data_manifest,
            funding_root=args.funding_root,
            price_manifest_path=args.price_manifest,
            price_root=args.price_root,
        )
        json_path, markdown_path = write_outputs(report, args.output_dir)
    except AuditInputError as exc:
        print(f"AUDIT INPUT ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": report["status"],
                "events": report["summary"]["lane_event_rows"],
                "price_ready": report["summary"]["valid_48h_price_path_count"],
                "funding_input_ready": report["summary"]["funding_input_ready_count"],
                "financial_replay_input_ready": report["summary"]["financial_replay_input_ready_count"],
                "financial_outcomes_computed": report["summary"]["financial_outcome_computed_count"],
                "json": str(json_path),
                "markdown": str(markdown_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
