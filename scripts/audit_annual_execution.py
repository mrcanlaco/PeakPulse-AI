"""Offline execution-feasibility audit for the frozen annual-profit baseline.

The audit is deliberately narrower than a backtest.  It reads the already
executed legs, derives the requested quantity from each leg's recorded margin
and the leverage in the frozen trial definitions, then checks the quantity
against a supplied Binance USD-M ``exchangeInfo`` snapshot.  It never changes
the baseline, reruns account capital, drops trades, or makes a P&L claim.

Typical invocation::

    .venv/Scripts/python.exe -X utf8 scripts/audit_annual_execution.py \
        --exchange-info artifacts/annual_execution_20260918/exchange_info_current.json \
        --output-dir artifacts/annual_execution_20260918

The three baseline inputs default to the canonical annual-profit artifact.
The exchange-info path is explicit because the snapshot is an external input;
there is no network access in this module.  Existing audit results are not
overwritten unless ``--force`` is supplied.  ``-o`` is an alias for
``--output-dir``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from decimal import ROUND_FLOOR, Decimal, InvalidOperation, localcontext
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE_DIR = ROOT / "artifacts" / "annual_profit_20260918" / "backtest_utf8"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "annual_execution_20260918"
DEFAULT_EXECUTED_LEGS = DEFAULT_BASELINE_DIR / "executed_leg_details.jsonl"
DEFAULT_ACCOUNTS = DEFAULT_BASELINE_DIR / "accounts.json"
DEFAULT_TRIAL_DEFINITIONS = DEFAULT_BASELINE_DIR / "trial_definitions.json"
DEFAULT_PROTOCOL = ROOT / "docs" / "ANNUAL_PROFIT_PROTOCOL_20260918.md"
DEFAULT_FINDINGS = ROOT / "docs" / "ANNUAL_PROFIT_MECHANISM_FINDINGS_20260918.md"

AUDIT_JSON = "annual_execution_audit.json"
LEG_JSONL = "annual_execution_leg_audit.jsonl"
REPORT_MD = "annual_execution_report.md"
RAW_SNAPSHOT = "exchange_info_raw.json"
RAW_PROVENANCE = "exchange_info_raw.provenance.json"

STATUS_FEASIBLE = "feasible"
STATUS_REJECTED = "rejected"
STATUS_UNKNOWN = "unknown"
STATUSES = (STATUS_FEASIBLE, STATUS_REJECTED, STATUS_UNKNOWN)


class AuditInputError(ValueError):
    """Raised when an audit input is malformed or cannot be trusted."""


class OutputExistsError(FileExistsError):
    """Raised when an audit result would overwrite an existing result."""


def _decimal(value: Any, field: str, *, positive: bool = False) -> Decimal:
    """Convert JSON scalar values to finite Decimal values without float noise."""

    if isinstance(value, bool) or value is None:
        raise AuditInputError(f"{field} must be a finite decimal value")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise AuditInputError(f"{field} must be a finite decimal value") from exc
    if not result.is_finite() or (positive and result <= 0):
        qualifier = "positive finite" if positive else "finite"
        raise AuditInputError(f"{field} must be {qualifier}; got {value!r}")
    return result


def _filter_decimal(value: Any) -> Decimal | None:
    """Parse a filter scalar; invalid filter scalars become ``None``."""

    if isinstance(value, bool) or value is None:
        return None
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return result if result.is_finite() else None


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def floor_to_step(value: Decimal | str | int | float, step: Decimal | str | int | float) -> Decimal:
    """Floor a non-negative quantity to a strictly positive decimal step.

    ``Decimal`` is used throughout, including for scientific-notation steps.
    The caller gets a Decimal on the original decimal grid; no binary floating
    point rounding is involved.
    """

    quantity = _decimal(value, "quantity")
    step_value = _decimal(step, "step", positive=True)
    if quantity < 0:
        raise AuditInputError(f"quantity must be non-negative; got {value!r}")
    precision = max(
        50,
        len(quantity.as_tuple().digits) + len(step_value.as_tuple().digits) + 20,
    )
    with localcontext() as context:
        context.prec = precision
        units = (quantity / step_value).to_integral_value(rounding=ROUND_FLOOR)
        return +(units * step_value)


def _lcm(left: int, right: int) -> int:
    return abs(left * right) // math.gcd(left, right)


def compatible_step(steps: Sequence[Decimal | str | int | float]) -> Decimal:
    """Return the smallest decimal quantity step compatible with all steps.

    LOT_SIZE and MARKET_LOT_SIZE are both enforced.  A common multiple is used
    rather than flooring sequentially, because sequential flooring can produce
    a value that satisfies one fractional grid but not the other.
    """

    if not steps:
        raise AuditInputError("at least one quantity step is required")
    fractions = [
        Fraction(_decimal(step, "step", positive=True))
        for step in steps
    ]
    denominator = 1
    for item in fractions:
        denominator = _lcm(denominator, item.denominator)
    scaled = [item.numerator * (denominator // item.denominator) for item in fractions]
    numerator = scaled[0]
    for item in scaled[1:]:
        numerator = _lcm(numerator, item)
    common = Fraction(numerator, denominator)
    precision = max(50, len(str(abs(common.numerator))) + len(str(common.denominator)) + 20)
    with localcontext() as context:
        context.prec = precision
        return +(Decimal(common.numerator) / Decimal(common.denominator))


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_label(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _read_json(path: Path) -> tuple[bytes, Any]:
    if not path.is_file():
        raise AuditInputError(f"input file does not exist: {path}")
    try:
        payload = path.read_bytes()
        return payload, json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditInputError(f"cannot read valid UTF-8 JSON from {path}: {exc}") from exc


def _source_file(path: Path, *, payload: bytes | None = None) -> dict[str, Any]:
    if payload is None:
        payload = path.read_bytes()
    return {
        "path": _path_label(path),
        "bytes": len(payload),
        "sha256": _sha256_bytes(payload),
    }


def _load_exchange_info_provenance(
    exchange_path: Path, snapshot_sha256: str
) -> tuple[dict[str, Any] | None, bytes | None, Path | None]:
    """Load the adjacent provenance sidecar when the supplied snapshot has one."""

    sidecar = exchange_path.with_suffix(".provenance.json")
    if not sidecar.exists():
        return None, None, None
    payload, data = _read_json(sidecar)
    if not isinstance(data, dict):
        raise AuditInputError(f"exchange-info provenance must contain an object: {sidecar}")
    declared_hash = data.get("sha256")
    if declared_hash is not None and declared_hash != snapshot_sha256:
        raise AuditInputError(
            f"exchange-info provenance hash does not match snapshot: {sidecar}"
        )
    if "retrieved_at_utc" in data:
        _validated_iso_timestamp(
            data["retrieved_at_utc"], "exchange-info provenance.retrieved_at_utc"
        )
    return data, payload, sidecar


def _utc_iso_from_epoch_ms(value: Any, field: str) -> str:
    number = _decimal(value, field)
    if number != number.to_integral_value():
        raise AuditInputError(f"{field} must be an integer millisecond timestamp")
    try:
        timestamp = datetime.fromtimestamp(float(number) / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise AuditInputError(f"{field} is outside the supported timestamp range") from exc
    return timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _validated_iso_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise AuditInputError(f"{field} must be an ISO timestamp")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuditInputError(f"{field} is not an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise AuditInputError(f"{field} must include a timezone")
    # Keep the supplied precision while normalising the UTC spelling.
    return text[:-6] + "Z" if text.endswith("+00:00") else text


def _snapshot_timestamp(
    path: Path,
    snapshot: Mapping[str, Any],
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Preserve verified embedded exchange time and retrieval provenance."""

    result: dict[str, Any] = {
        "retrieved_at_utc": None,
        "retrieval_timestamp_source": "unavailable",
    }
    if "serverTime" in snapshot:
        result["server_time_ms"] = int(_decimal(snapshot["serverTime"], "serverTime"))
        result["server_time_utc"] = _utc_iso_from_epoch_ms(
            snapshot["serverTime"], "serverTime"
        )

    if provenance is not None and "retrieved_at_utc" in provenance:
        result["retrieved_at_utc"] = _validated_iso_timestamp(
            provenance["retrieved_at_utc"], "exchange-info provenance.retrieved_at_utc"
        )
        result["retrieval_timestamp_source"] = "exchange_info_provenance.json"

    embedded_keys = (
        "retrievedAt",
        "retrieved_at",
        "retrievalTimestamp",
        "retrieval_timestamp",
        "downloadedAt",
        "downloaded_at",
    )
    for key in embedded_keys:
        if result["retrieved_at_utc"] is not None:
            break
        if key not in snapshot:
            continue
        value = snapshot[key]
        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            result["retrieved_at_utc"] = _utc_iso_from_epoch_ms(value, key)
        elif isinstance(value, str):
            result["retrieved_at_utc"] = _validated_iso_timestamp(value, f"snapshot {key}")
        else:
            raise AuditInputError(f"snapshot {key} must be an epoch-millisecond or ISO timestamp")
        result["retrieval_timestamp_source"] = f"exchange_info.{key}"
        break
    return result


def _load_trial_definitions(path: Path) -> tuple[dict[str, dict[str, Any]], bytes]:
    payload, data = _read_json(path)
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict) and isinstance(data.get("trials"), list):
        records = data["trials"]
    else:
        raise AuditInputError(
            f"{path} must contain a trial-definition list or an object with a trials list"
        )

    definitions: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise AuditInputError(f"trial definition {index} is not an object")
        trial_id = record.get("trial_id")
        if not isinstance(trial_id, str) or not trial_id:
            raise AuditInputError(f"trial definition {index} has no trial_id")
        leverage = _decimal(record.get("leverage"), f"{trial_id}.leverage", positive=True)
        normalized = dict(record)
        normalized["leverage_decimal"] = leverage
        if trial_id in definitions:
            previous = definitions[trial_id]["leverage_decimal"]
            if previous != leverage:
                raise AuditInputError(f"trial {trial_id} has conflicting leverage definitions")
            raise AuditInputError(f"duplicate trial definition: {trial_id}")
        definitions[trial_id] = normalized
    if not definitions:
        raise AuditInputError(f"{path} contains no trial definitions")
    return definitions, payload


def _load_accounts(path: Path) -> tuple[dict[str, Any], bytes]:
    payload, data = _read_json(path)
    if not isinstance(data, dict):
        raise AuditInputError(f"{path} must contain an account object")
    if "trials" in data and not isinstance(data["trials"], list):
        raise AuditInputError(f"{path}.trials must be a list when present")
    metadata = {
        key: data[key]
        for key in (
            "artifact",
            "artifact_version",
            "snapshot_id",
            "status",
            "trial_count",
            "strategy_count",
            "all_40_trials_included",
            "protocol_sha256",
        )
        if key in data
    }
    return metadata, payload


def _symbol_index(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    symbols = snapshot.get("symbols")
    if not isinstance(symbols, list):
        raise AuditInputError("exchange-info snapshot must contain a symbols list")
    result: dict[str, dict[str, Any]] = {}
    for index, symbol in enumerate(symbols):
        if not isinstance(symbol, dict):
            raise AuditInputError(f"exchange-info symbol {index} is not an object")
        name = symbol.get("symbol")
        if not isinstance(name, str) or not name:
            raise AuditInputError(f"exchange-info symbol {index} has no symbol name")
        if name in result:
            raise AuditInputError(f"exchange-info contains duplicate symbol: {name}")
        result[name] = symbol
    return result


def _parse_lot_filter(filter_data: Any, name: str) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(filter_data, dict):
        return None, f"invalid_filter:{name}"
    values = {key: _filter_decimal(filter_data.get(key)) for key in ("minQty", "maxQty", "stepSize")}
    if any(value is None for value in values.values()):
        return None, f"invalid_filter:{name}"
    minimum = values["minQty"]
    maximum = values["maxQty"]
    step = values["stepSize"]
    assert minimum is not None and maximum is not None and step is not None
    if minimum < 0 or maximum <= 0 or step <= 0:
        return None, f"invalid_filter:{name}"
    if Fraction(minimum) % Fraction(step) != 0:
        return None, f"unsupported_shifted_grid:{name}"
    if minimum > maximum:
        return None, f"invalid_filter:{name}"
    return {
        "min_qty": minimum,
        "max_qty": maximum,
        "step_size": step,
    }, None


def _parse_min_notional(filter_data: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(filter_data, dict):
        return None, "invalid_filter:MIN_NOTIONAL"
    raw = filter_data.get("notional")
    if raw is None:
        raw = filter_data.get("minNotional")
    notional = _filter_decimal(raw)
    if notional is None or notional <= 0:
        return None, "invalid_filter:MIN_NOTIONAL"
    apply_to_market = filter_data.get("applyToMarket")
    if apply_to_market is not None and not isinstance(apply_to_market, bool):
        return None, "invalid_filter:MIN_NOTIONAL"
    return {"notional": notional, "apply_to_market": apply_to_market}, None


def _filter_map(symbol_entry: Mapping[str, Any]) -> tuple[dict[str, Any], set[str], str | None]:
    filters = symbol_entry.get("filters")
    if not isinstance(filters, list):
        return {}, set(), "invalid_filter_list"
    result: dict[str, Any] = {}
    duplicates: set[str] = set()
    for item in filters:
        if not isinstance(item, dict):
            return {}, set(), "invalid_filter_list"
        filter_type = item.get("filterType")
        if not isinstance(filter_type, str):
            return {}, set(), "invalid_filter_list"
        if filter_type in result:
            duplicates.add(filter_type)
        result[filter_type] = item
    return result, duplicates, None


def _public_lot_filter(parsed: dict[str, Any] | None, reason: str | None) -> dict[str, Any]:
    if parsed is None:
        return {"status": STATUS_UNKNOWN, "reason": reason or "unknown_filter"}
    return {
        "status": "valid",
        "min_qty": _decimal_text(parsed["min_qty"]),
        "max_qty": _decimal_text(parsed["max_qty"]),
        "step_size": _decimal_text(parsed["step_size"]),
        "min_qty_active": parsed["min_qty"] != 0,
        "max_qty_active": parsed["max_qty"] != 0,
    }


def _public_min_notional(parsed: dict[str, Any] | None, reason: str | None) -> dict[str, Any]:
    if parsed is None:
        return {"status": STATUS_UNKNOWN, "reason": reason or "unknown_filter"}
    return {
        "status": "valid",
        "min_notional": _decimal_text(parsed["notional"]),
        "apply_to_market": parsed["apply_to_market"],
        "price_proxy": "entry_price",
    }


def _unique_append(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def audit_leg(
    leg: Mapping[str, Any],
    leverage: Decimal | str | int | float,
    symbol_entry: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Audit one executed leg against one exchange-info symbol entry.

    ``margin_usd`` is intentionally read from the leg as-is.  For a hedge this
    means the recorded half margin is used directly; this function never splits
    it again.  A missing symbol or missing/invalid required filter returns an
    explicit ``unknown`` status, never a pass.
    """

    if not isinstance(leg, Mapping):
        raise AuditInputError("executed leg must be an object")
    symbol = leg.get("symbol")
    if not isinstance(symbol, str) or not symbol:
        raise AuditInputError("executed leg has no symbol")
    entry_price = _decimal(leg.get("entry_price"), f"{symbol}.entry_price", positive=True)
    margin = _decimal(leg.get("margin_usd"), f"{symbol}.margin_usd")
    if margin < 0:
        raise AuditInputError(f"{symbol}.margin_usd must be non-negative")
    leverage_value = _decimal(leverage, f"{symbol}.leverage", positive=True)
    raw_notional = margin * leverage_value
    raw_quantity = raw_notional / entry_price

    result: dict[str, Any] = {
        "status": STATUS_UNKNOWN,
        "symbol": symbol,
        "direction": leg.get("direction"),
        "entry_price": _decimal_text(entry_price),
        "mark_price_proxy": {
            "kind": "entry_price",
            "value": _decimal_text(entry_price),
            "note": "MIN_NOTIONAL uses entry price as an explicit mark proxy",
        },
        "margin_usd": _decimal_text(margin),
        "margin_basis": "recorded leg margin; hedge half-margin is not split again",
        "margin_weight_recorded": leg.get("margin_weight"),
        "leverage": _decimal_text(leverage_value),
        "leverage_source": "frozen_trial_definitions",
        "raw_notional_usd": _decimal_text(raw_notional),
        "raw_quantity": _decimal_text(raw_quantity),
        "floored_quantity": None,
        "floored_notional_usd": None,
        "filter_status": {},
        "filter_checks": {},
        "quantity_check": {"status": STATUS_UNKNOWN},
        "notional_check": {"status": STATUS_UNKNOWN, "price_proxy": "entry_price"},
        "reason_codes": [],
    }

    if symbol_entry is None:
        result["filter_status"] = {
            "LOT_SIZE": STATUS_UNKNOWN,
            "MARKET_LOT_SIZE": STATUS_UNKNOWN,
            "MIN_NOTIONAL": STATUS_UNKNOWN,
        }
        result["filter_checks"] = {
            "LOT_SIZE": {"status": STATUS_UNKNOWN, "reason": "missing_symbol"},
            "MARKET_LOT_SIZE": {"status": STATUS_UNKNOWN, "reason": "missing_symbol"},
            "MIN_NOTIONAL": {"status": STATUS_UNKNOWN, "reason": "missing_symbol"},
        }
        result["reason_codes"] = ["missing_symbol"]
        return result

    filters, duplicates, filter_list_error = _filter_map(symbol_entry)
    if filter_list_error:
        result["filter_status"] = {
            "LOT_SIZE": STATUS_UNKNOWN,
            "MARKET_LOT_SIZE": STATUS_UNKNOWN,
            "MIN_NOTIONAL": STATUS_UNKNOWN,
        }
        result["filter_checks"] = {
            name: {"status": STATUS_UNKNOWN, "reason": filter_list_error}
            for name in ("LOT_SIZE", "MARKET_LOT_SIZE", "MIN_NOTIONAL")
        }
        result["reason_codes"] = [filter_list_error]
        return result

    lot_parsed: dict[str, dict[str, Any] | None] = {}
    lot_reasons: dict[str, str | None] = {}
    for name in ("LOT_SIZE", "MARKET_LOT_SIZE"):
        if name in duplicates:
            lot_parsed[name] = None
            lot_reasons[name] = f"duplicate_filter:{name}"
        elif name not in filters:
            lot_parsed[name] = None
            lot_reasons[name] = f"missing_filter:{name}"
        else:
            lot_parsed[name], lot_reasons[name] = _parse_lot_filter(filters[name], name)

    if "MIN_NOTIONAL" in duplicates:
        min_notional, min_notional_reason = None, "duplicate_filter:MIN_NOTIONAL"
    elif "MIN_NOTIONAL" not in filters:
        min_notional, min_notional_reason = None, "missing_filter:MIN_NOTIONAL"
    else:
        min_notional, min_notional_reason = _parse_min_notional(filters["MIN_NOTIONAL"])

    for name in ("LOT_SIZE", "MARKET_LOT_SIZE"):
        result["filter_status"][name] = (
            "valid" if lot_parsed[name] is not None else STATUS_UNKNOWN
        )
        result["filter_checks"][name] = _public_lot_filter(
            lot_parsed[name], lot_reasons[name]
        )
    result["filter_status"]["MIN_NOTIONAL"] = (
        "valid" if min_notional is not None else STATUS_UNKNOWN
    )
    result["filter_checks"]["MIN_NOTIONAL"] = _public_min_notional(
        min_notional, min_notional_reason
    )

    unknown_reasons: list[str] = []
    fail_reasons: list[str] = []
    for reason in lot_reasons.values():
        if reason:
            _unique_append(unknown_reasons, reason)
    if min_notional_reason:
        _unique_append(unknown_reasons, min_notional_reason)

    common_step: Decimal | None = None
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    if lot_parsed["LOT_SIZE"] is not None and lot_parsed["MARKET_LOT_SIZE"] is not None:
        first = lot_parsed["LOT_SIZE"]
        second = lot_parsed["MARKET_LOT_SIZE"]
        assert first is not None and second is not None
        common_step = compatible_step([first["step_size"], second["step_size"]])
        active_mins = [item["min_qty"] for item in (first, second) if item["min_qty"] != 0]
        minimum = max(active_mins) if active_mins else Decimal("0")
        maximum = min(item["max_qty"] for item in (first, second))
        if maximum is not None and minimum > maximum:
            common_step = None
            _unique_append(unknown_reasons, "incompatible_lot_bounds")
    else:
        _unique_append(unknown_reasons, "lot_size_filter_unknown")

    result["lot_size_compatibility"] = {
        "status": "valid" if common_step is not None else STATUS_UNKNOWN,
        "applicable_filters": ["LOT_SIZE", "MARKET_LOT_SIZE"],
        "common_step_size": _decimal_text(common_step),
        "effective_min_qty": _decimal_text(minimum),
        "effective_max_qty": _decimal_text(maximum),
        "note": "market quantity must be compatible with both applicable filters",
    }

    floored_quantity: Decimal | None = None
    if common_step is not None:
        floored_quantity = floor_to_step(raw_quantity, common_step)
        result["floored_quantity"] = _decimal_text(floored_quantity)
        floored_notional = floored_quantity * entry_price
        result["floored_notional_usd"] = _decimal_text(floored_notional)
        quantity_failures: list[str] = []
        if floored_quantity <= 0:
            quantity_failures.append("quantity_zero_after_step_floor")
        if minimum is not None and floored_quantity < minimum:
            quantity_failures.append("quantity_below_min_qty")
        if maximum is not None and floored_quantity > maximum:
            quantity_failures.append("quantity_above_max_qty")
        if quantity_failures:
            result["quantity_check"] = {
                "status": STATUS_REJECTED,
                "raw_quantity": _decimal_text(raw_quantity),
                "floored_quantity": _decimal_text(floored_quantity),
                "effective_min_qty": _decimal_text(minimum),
                "effective_max_qty": _decimal_text(maximum),
                "common_step_size": _decimal_text(common_step),
                "reason_codes": quantity_failures,
            }
            for reason in quantity_failures:
                _unique_append(fail_reasons, reason)
        else:
            result["quantity_check"] = {
                "status": "pass",
                "raw_quantity": _decimal_text(raw_quantity),
                "floored_quantity": _decimal_text(floored_quantity),
                "effective_min_qty": _decimal_text(minimum),
                "effective_max_qty": _decimal_text(maximum),
                "common_step_size": _decimal_text(common_step),
            }
    else:
        _unique_append(unknown_reasons, "quantity_step_unknown")

    if min_notional is None:
        result["notional_check"] = {
            "status": STATUS_UNKNOWN,
            "price_proxy": "entry_price",
            "reason": min_notional_reason or "unknown_filter:MIN_NOTIONAL",
        }
    elif floored_quantity is None:
        result["notional_check"] = {
            "status": STATUS_UNKNOWN,
            "price_proxy": "entry_price",
            "reason": "quantity_unknown",
        }
        _unique_append(unknown_reasons, "notional_quantity_unknown")
    elif min_notional.get("apply_to_market") is False:
        result["notional_check"] = {
            "status": "not_applicable",
            "price_proxy": "entry_price",
            "min_notional": _decimal_text(min_notional["notional"]),
            "reason": "MIN_NOTIONAL applyToMarket=false",
        }
    else:
        actual_notional = floored_quantity * entry_price
        required = min_notional["notional"]
        if actual_notional < required:
            result["notional_check"] = {
                "status": STATUS_REJECTED,
                "price_proxy": "entry_price",
                "entry_price": _decimal_text(entry_price),
                "actual_notional": _decimal_text(actual_notional),
                "min_notional": _decimal_text(required),
                "reason_codes": ["notional_below_min_notional"],
            }
            _unique_append(fail_reasons, "notional_below_min_notional")
        else:
            result["notional_check"] = {
                "status": "pass",
                "price_proxy": "entry_price",
                "entry_price": _decimal_text(entry_price),
                "actual_notional": _decimal_text(actual_notional),
                "min_notional": _decimal_text(required),
            }

    result["reason_codes"] = unknown_reasons + [
        reason for reason in fail_reasons if reason not in unknown_reasons
    ]
    if unknown_reasons:
        result["status"] = STATUS_UNKNOWN
    elif fail_reasons:
        result["status"] = STATUS_REJECTED
    else:
        result["status"] = STATUS_FEASIBLE
    return result


def _trade_status(leg_audits: Sequence[Mapping[str, Any]]) -> tuple[str, list[str]]:
    statuses = [audit.get("status") for audit in leg_audits]
    reasons: list[str] = []
    for audit in leg_audits:
        for reason in audit.get("reason_codes", []):
            _unique_append(reasons, str(reason))
    if STATUS_UNKNOWN in statuses:
        return STATUS_UNKNOWN, reasons
    if STATUS_REJECTED in statuses:
        return STATUS_REJECTED, reasons
    return STATUS_FEASIBLE, reasons


def audit_trade(
    legs: Sequence[Mapping[str, Any]],
    leverage: Decimal | str | int | float,
    symbols: Mapping[str, Mapping[str, Any]],
    *,
    hedge: bool = False,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    """Audit all legs in one executed record and require all hedge legs."""

    if not legs:
        raise AuditInputError("executed record has no legs")
    if hedge and len(legs) != 2:
        raise AuditInputError(
            f"hedge executed record must contain exactly two legs; got {len(legs)}"
        )
    audits = []
    for leg in legs:
        if not isinstance(leg, Mapping):
            raise AuditInputError("executed record contains a non-object leg")
        symbol = leg.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise AuditInputError("executed record contains a leg without a symbol")
        audits.append(audit_leg(leg, leverage, symbols.get(symbol)))
    status, reasons = _trade_status(audits)
    return audits, status, reasons


def _output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "audit": output_dir / AUDIT_JSON,
        "legs": output_dir / LEG_JSONL,
        "report": output_dir / REPORT_MD,
        "raw_snapshot": output_dir / RAW_SNAPSHOT,
        "raw_provenance": output_dir / RAW_PROVENANCE,
    }


def _check_output_paths(
    paths: Mapping[str, Path],
    *,
    force: bool,
    raw_sha256: str,
    raw_provenance_sha256: str | None = None,
) -> None:
    if force:
        return
    for name in ("audit", "legs", "report"):
        if paths[name].exists():
            raise OutputExistsError(
                f"refusing to overwrite existing result {paths[name]}; use --force to replace it"
            )
    raw = paths["raw_snapshot"]
    if raw.exists():
        if not raw.is_file() or _sha256_file(raw) != raw_sha256:
            raise OutputExistsError(
                f"refusing to overwrite existing raw snapshot {raw}; use --force to replace it"
            )
    provenance = paths["raw_provenance"]
    if provenance.exists():
        if raw_provenance_sha256 is None:
            raise OutputExistsError(
                f"refusing to overwrite existing raw provenance {provenance}; use --force to replace it"
            )
        if not provenance.is_file() or _sha256_file(provenance) != raw_provenance_sha256:
            raise OutputExistsError(
                f"refusing to overwrite existing raw provenance {provenance}; use --force to replace it"
            )


def _write_atomic(path: Path, payload: bytes, *, force: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
        if not force and path.exists():
            raise OutputExistsError(f"refusing to overwrite existing result {path}")
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _increment_status(bucket: dict[str, int], status: str) -> None:
    if status not in STATUSES:
        raise AuditInputError(f"unexpected audit status: {status}")
    bucket[status] += 1


def _new_status_counts() -> dict[str, int]:
    return {status: 0 for status in STATUSES}


def _strategy_bucket() -> dict[str, Any]:
    return {
        "executed_records": 0,
        "executed_legs": 0,
        "hedge_records": 0,
        "leg_status_counts": _new_status_counts(),
        "record_status_counts": _new_status_counts(),
    }


def _margin_sensitivity() -> dict[str, Any]:
    return {
        "diagnostic_only": True,
        "not_exchange_rules": True,
        "thresholds_usd": ["5", "20"],
        "leg_counts": {"margin_lt_5": 0, "margin_lt_20": 0},
        "record_counts_any_leg": {"margin_lt_5": 0, "margin_lt_20": 0},
        "hedge_record_counts_all_legs": {"margin_lt_5": 0, "margin_lt_20": 0},
    }


def _update_margin_sensitivity(
    summary: dict[str, Any],
    margins: Sequence[Decimal],
    *,
    hedge: bool,
) -> None:
    below_five = [margin < Decimal("5") for margin in margins]
    below_twenty = [margin < Decimal("20") for margin in margins]
    if any(below_five):
        summary["margin_sensitivity"]["record_counts_any_leg"]["margin_lt_5"] += 1
    if any(below_twenty):
        summary["margin_sensitivity"]["record_counts_any_leg"]["margin_lt_20"] += 1
    if hedge and margins and all(below_five):
        summary["margin_sensitivity"]["hedge_record_counts_all_legs"]["margin_lt_5"] += 1
    if hedge and margins and all(below_twenty):
        summary["margin_sensitivity"]["hedge_record_counts_all_legs"]["margin_lt_20"] += 1
    for is_below_five, is_below_twenty in zip(below_five, below_twenty):
        if is_below_five:
            summary["margin_sensitivity"]["leg_counts"]["margin_lt_5"] += 1
        if is_below_twenty:
            summary["margin_sensitivity"]["leg_counts"]["margin_lt_20"] += 1


def _make_summary(
    *,
    source_files: dict[str, Any],
    snapshot: Mapping[str, Any],
    snapshot_payload: bytes,
    snapshot_path: Path,
    snapshot_provenance: Mapping[str, Any] | None,
    snapshot_provenance_path: Path | None,
    accounts_metadata: Mapping[str, Any],
    trial_definitions: Mapping[str, Mapping[str, Any]],
    executed_path: Path,
    output_dir: Path,
    invocation: str | None,
) -> dict[str, Any]:
    snapshot_times = _snapshot_timestamp(snapshot_path, snapshot, snapshot_provenance)
    trial_leverages = {
        trial_id: _decimal_text(record["leverage_decimal"])
        for trial_id, record in sorted(trial_definitions.items())
    }
    snapshot_metadata: dict[str, Any] = {
        "input_path": _path_label(snapshot_path),
        "raw_snapshot_path": _path_label(output_dir / RAW_SNAPSHOT),
        "sha256": _sha256_bytes(snapshot_payload),
        "futures_type": snapshot.get("futuresType"),
        "timezone": snapshot.get("timezone"),
        "symbol_count": len(snapshot.get("symbols", [])),
        **snapshot_times,
    }
    if snapshot_provenance is not None:
        snapshot_metadata["provenance"] = dict(snapshot_provenance)
        snapshot_metadata["raw_provenance_path"] = _path_label(output_dir / RAW_PROVENANCE)
    if snapshot_provenance_path is not None:
        snapshot_metadata["provenance_path"] = _path_label(snapshot_provenance_path)
    return {
        "artifact": "annual_execution_feasibility_audit",
        "artifact_version": "1.0",
        "status": "complete",
        "audit_scope": {
            "executed_leg_details_only": True,
            "current_exchange_info_rules_only": True,
            "historical_attestation": False,
            "actual_execution_attested": False,
            "pnl_recomputed": False,
            "capital_replayed": False,
            "trades_dropped_or_reused": False,
            "network_access": False,
            "both_hedge_legs_required": True,
        },
        "rules": {
            "order_type": "MARKET quantity feasibility proxy",
            "lot_filters": ["MARKET_LOT_SIZE", "LOT_SIZE"],
            "quantity_rounding": "Decimal floor to the common compatible step",
            "min_notional_filter": "MIN_NOTIONAL",
            "min_notional_price_proxy": "entry_price",
            "missing_or_invalid_filter_status": STATUS_UNKNOWN,
            "missing_symbol_status": STATUS_UNKNOWN,
            "leverage_source": "frozen trial_definitions.json by trial_id",
            "hedge_margin_basis": "recorded margin_usd per leg; no second half split",
        },
        "source_files": source_files,
        "source_hashes": {
            name: details["sha256"] for name, details in source_files.items()
        },
        "baseline": {
            "executed_leg_details": _path_label(executed_path),
            "accounts_metadata": dict(accounts_metadata),
            "trial_definition_count": len(trial_definitions),
            "trial_leverages": trial_leverages,
        },
        "exchange_info_snapshot": snapshot_metadata,
        "counts": {
            "executed_records": 0,
            "executed_legs": 0,
            "hedge_records": 0,
            "leg_status_counts": _new_status_counts(),
            "record_status_counts": _new_status_counts(),
            "hedge_record_status_counts": _new_status_counts(),
            "hedge_records_both_legs_feasible": 0,
        },
        "unknowns": {
            "reason_counts": {},
            "missing_symbols": [],
            "missing_or_invalid_filter_counts": {},
        },
        "rejections": {"reason_counts": {}},
        "margin_sensitivity": _margin_sensitivity(),
        "by_strategy": {},
        "by_trial": {},
        "invocation": invocation,
        "notes": [
            "This is a current-rules feasibility audit, not a historical exchange-rules attestation.",
            "A feasible result means only that the recorded entry quantity passes the supplied snapshot's known filters.",
            "Unknown is not treated as feasible and is not silently converted into rejection.",
            "The <$5 and <$20 margin counts are fixed diagnostic scenarios, not exchange rules.",
            "No actual P&L improvement, trade removal, trade reuse, or account-capital conclusion is inferred.",
        ],
    }


def _report_markdown(summary: Mapping[str, Any]) -> str:
    counts = summary["counts"]
    snapshot = summary["exchange_info_snapshot"]
    margin = summary["margin_sensitivity"]
    retrieval_timestamp = snapshot.get("retrieved_at_utc") or "unavailable"
    retrieval_source = snapshot.get("retrieval_timestamp_source") or "unavailable"
    lines = [
        "# Annual execution-feasibility audit",
        "",
        "This artifact audits already executed annual-baseline legs against the supplied **current** Binance USD-M exchangeInfo snapshot. It is not a historical-rules attestation, live-execution proof, backtest, or account-capital rerun.",
        "",
        "## Inputs",
        "",
        f"- ExchangeInfo SHA-256: `{snapshot['sha256']}`",
        f"- Snapshot retrieval timestamp: `{retrieval_timestamp}` ({retrieval_source})",
        f"- Exchange server time: `{snapshot.get('server_time_utc', 'not supplied')}`",
        f"- Symbols in snapshot: {snapshot['symbol_count']}",
        f"- Raw snapshot copy: `{snapshot['raw_snapshot_path']}`",
        f"- Provenance sidecar: `{snapshot.get('provenance_path', 'not supplied')}`",
        "",
        "## Results",
        "",
        f"- Executed records audited: {counts['executed_records']}",
        f"- Executed legs audited: {counts['executed_legs']}",
        f"- Hedge records: {counts['hedge_records']}; both-leg feasible: {counts['hedge_records_both_legs_feasible']}",
        f"- Leg status counts: `{json.dumps(counts['leg_status_counts'], sort_keys=True)}`",
        f"- Record status counts: `{json.dumps(counts['record_status_counts'], sort_keys=True)}`",
        f"- Rejection reason counts: `{json.dumps(summary['rejections']['reason_counts'], sort_keys=True)}`",
        "",
        "The quantity is derived from `margin_usd × frozen trial leverage ÷ entry_price`, then Decimal-floored to a step compatible with both `MARKET_LOT_SIZE` and `LOT_SIZE`. `MIN_NOTIONAL` uses entry price explicitly as the mark proxy. A missing symbol or missing/invalid filter is `unknown`; it is never a pass.",
        "",
        "## Margin diagnostics",
        "",
        "These are fixed diagnostic scenarios only; they are not Binance rules and do not remove or reuse any trade.",
        f"- Legs with margin < $5: {margin['leg_counts']['margin_lt_5']}; records with any: {margin['record_counts_any_leg']['margin_lt_5']}",
        f"- Legs with margin < $20: {margin['leg_counts']['margin_lt_20']}; records with any: {margin['record_counts_any_leg']['margin_lt_20']}",
        "",
        "## Limitations",
        "",
        "- This uses current snapshot filters against historical recorded entries; it does not attest that those rules existed at the historical entry time.",
        "- Feasibility does not imply fill quality, mark-price behavior, liquidity, maintenance tiers, liquidation behavior, or P&L improvement.",
        "- Unknown inputs remain explicitly unknown so the audit does not overstate execution feasibility.",
        "",
    ]
    return "\n".join(lines)


def run_audit(
    *,
    exchange_info_path: Path | str,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    executed_legs_path: Path | str = DEFAULT_EXECUTED_LEGS,
    accounts_path: Path | str = DEFAULT_ACCOUNTS,
    trial_definitions_path: Path | str = DEFAULT_TRIAL_DEFINITIONS,
    protocol_path: Path | str = DEFAULT_PROTOCOL,
    findings_path: Path | str = DEFAULT_FINDINGS,
    force: bool = False,
    invocation: str | None = None,
) -> dict[str, Any]:
    """Run the offline audit and write an immutable result set by default."""

    exchange_path = Path(exchange_info_path)
    output = Path(output_dir)
    executed_path = Path(executed_legs_path)
    accounts_file = Path(accounts_path)
    trial_file = Path(trial_definitions_path)
    protocol_file = Path(protocol_path)
    findings_file = Path(findings_path)

    snapshot_payload, snapshot = _read_json(exchange_path)
    if not isinstance(snapshot, dict):
        raise AuditInputError("exchange-info snapshot must contain an object")
    snapshot_sha256 = _sha256_bytes(snapshot_payload)
    snapshot_provenance, snapshot_provenance_payload, snapshot_provenance_path = (
        _load_exchange_info_provenance(exchange_path, snapshot_sha256)
    )
    symbols = _symbol_index(snapshot)
    trial_definitions, trial_payload = _load_trial_definitions(trial_file)
    accounts_metadata, accounts_payload = _load_accounts(accounts_file)
    if not executed_path.is_file():
        raise AuditInputError(f"input file does not exist: {executed_path}")

    account_trials = accounts_metadata
    # Validate the optional accounts trial topology without using its capital or P&L.
    _, accounts_data = _read_json(accounts_file)
    if isinstance(accounts_data.get("trials"), list):
        for index, account_trial in enumerate(accounts_data["trials"]):
            if not isinstance(account_trial, dict):
                raise AuditInputError(f"accounts.trials[{index}] is not an object")
            trial_id = account_trial.get("trial_id")
            if trial_id is not None and trial_id not in trial_definitions:
                raise AuditInputError(
                    f"accounts.trials[{index}] references trial without frozen definition: {trial_id}"
                )

    source_files = {
        "executed_leg_details": _source_file(executed_path),
        "accounts": _source_file(accounts_file, payload=accounts_payload),
        "trial_definitions": _source_file(trial_file, payload=trial_payload),
        "exchange_info": _source_file(exchange_path, payload=snapshot_payload),
    }
    if snapshot_provenance_path is not None and snapshot_provenance_payload is not None:
        source_files["exchange_info_provenance"] = _source_file(
            snapshot_provenance_path, payload=snapshot_provenance_payload
        )
    if protocol_file.is_file():
        source_files["protocol"] = _source_file(protocol_file)
    if findings_file.is_file():
        source_files["mechanism_findings"] = _source_file(findings_file)

    output.mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output)
    _check_output_paths(
        paths,
        force=force,
        raw_sha256=source_files["exchange_info"]["sha256"],
        raw_provenance_sha256=(
            source_files.get("exchange_info_provenance", {}).get("sha256")
            if snapshot_provenance_payload is not None
            else None
        ),
    )

    summary = _make_summary(
        source_files=source_files,
        snapshot=snapshot,
        snapshot_payload=snapshot_payload,
        snapshot_path=exchange_path,
        snapshot_provenance=snapshot_provenance,
        snapshot_provenance_path=snapshot_provenance_path,
        accounts_metadata=account_trials,
        trial_definitions=trial_definitions,
        executed_path=executed_path,
        output_dir=output,
        invocation=invocation,
    )
    summary["accounts_source_hash"] = source_files["accounts"]["sha256"]

    unknown_reasons: Counter[str] = Counter()
    rejection_reasons: Counter[str] = Counter()
    missing_symbols: set[str] = set()
    missing_filter_counts: Counter[str] = Counter()
    temporary_legs: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output,
            prefix=f".{LEG_JSONL}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_legs = Path(handle.name)
            for row_number, line in enumerate(executed_path.open(encoding="utf-8"), start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AuditInputError(
                        f"malformed executed-leg JSON at line {row_number}: {exc}"
                    ) from exc
                if not isinstance(record, dict):
                    raise AuditInputError(f"executed-leg line {row_number} is not an object")
                trial_id = record.get("trial_id")
                if not isinstance(trial_id, str) or not trial_id:
                    raise AuditInputError(f"executed-leg line {row_number} has no trial_id")
                if trial_id not in trial_definitions:
                    raise AuditInputError(
                        f"executed-leg line {row_number} has no frozen leverage: {trial_id}"
                    )
                legs = record.get("legs")
                if not isinstance(legs, list) or not legs:
                    raise AuditInputError(f"executed-leg line {row_number} has no non-empty legs list")
                trial = trial_definitions[trial_id]
                strategy_id = record.get("strategy_id", trial.get("strategy_id"))
                if not isinstance(strategy_id, str) or not strategy_id:
                    raise AuditInputError(f"executed-leg line {row_number} has no strategy_id")
                hedge = bool(trial.get("hedge_btc", False))
                audits, trade_status, trade_reasons = audit_trade(
                    legs,
                    trial["leverage_decimal"],
                    symbols,
                    hedge=hedge,
                )

                summary["counts"]["executed_records"] += 1
                summary["counts"]["executed_legs"] += len(audits)
                strategy_summary = summary["by_strategy"].setdefault(
                    strategy_id, _strategy_bucket()
                )
                strategy_summary["executed_records"] += 1
                strategy_summary["executed_legs"] += len(audits)
                if hedge:
                    summary["counts"]["hedge_records"] += 1
                    summary["counts"]["hedge_record_status_counts"][trade_status] += 1
                    strategy_summary["hedge_records"] += 1
                    if trade_status == STATUS_FEASIBLE:
                        summary["counts"]["hedge_records_both_legs_feasible"] += 1
                _increment_status(summary["counts"]["record_status_counts"], trade_status)
                _increment_status(strategy_summary["record_status_counts"], trade_status)
                _update_margin_sensitivity(
                    summary,
                    [
                        _decimal(leg.get("margin_usd"), "leg.margin_usd")
                        for leg in legs
                    ],
                    hedge=hedge,
                )
                trial_summary = summary["by_trial"].setdefault(
                    trial_id,
                    {
                        "strategy_id": strategy_id,
                        "leverage": _decimal_text(trial["leverage_decimal"]),
                        "hedge_btc": hedge,
                        "executed_records": 0,
                        "executed_legs": 0,
                        "leg_status_counts": _new_status_counts(),
                        "record_status_counts": _new_status_counts(),
                    },
                )
                trial_summary["executed_records"] += 1
                trial_summary["executed_legs"] += len(audits)
                _increment_status(trial_summary["record_status_counts"], trade_status)

                for leg_index, (leg, audit) in enumerate(zip(legs, audits)):
                    _increment_status(summary["counts"]["leg_status_counts"], audit["status"])
                    _increment_status(strategy_summary["leg_status_counts"], audit["status"])
                    _increment_status(trial_summary["leg_status_counts"], audit["status"])
                    for reason in audit["reason_codes"]:
                        if audit["status"] == STATUS_UNKNOWN:
                            unknown_reasons[reason] += 1
                        elif audit["status"] == STATUS_REJECTED:
                            rejection_reasons[reason] += 1
                        if reason == "missing_symbol":
                            missing_symbols.add(audit["symbol"])
                        if reason.startswith(("missing_filter:", "invalid_filter:", "duplicate_filter:")):
                            missing_filter_counts[reason] += 1
                    output_record = {
                        "source_line": row_number,
                        "candidate_id": record.get("candidate_id"),
                        "trial_id": trial_id,
                        "strategy_id": strategy_id,
                        "entry_time": record.get("entry_time"),
                        "trade_leg_count": len(audits),
                        "hedge_btc": hedge,
                        "trade_status": trade_status,
                        "trade_reason_codes": trade_reasons,
                        "leg_index": leg_index,
                        "audit": audit,
                    }
                    handle.write(json.dumps(output_record, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError as exc:
        raise AuditInputError(f"cannot stream executed-leg input {executed_path}: {exc}") from exc
    except Exception:
        if temporary_legs is not None and temporary_legs.exists():
            temporary_legs.unlink()
        raise

    summary["unknowns"]["reason_counts"] = dict(sorted(unknown_reasons.items()))
    summary["unknowns"]["missing_symbols"] = sorted(missing_symbols)
    summary["unknowns"]["missing_or_invalid_filter_counts"] = dict(
        sorted(missing_filter_counts.items())
    )
    summary["rejections"]["reason_counts"] = dict(sorted(rejection_reasons.items()))

    if temporary_legs is None:
        raise AuditInputError("audit did not produce a leg result")
    try:
        if not force and paths["legs"].exists():
            raise OutputExistsError(f"refusing to overwrite existing result {paths['legs']}")
        temporary_legs.replace(paths["legs"])
    finally:
        if temporary_legs.exists():
            temporary_legs.unlink()

    raw_existing = paths["raw_snapshot"]
    if not (raw_existing.exists() and not force):
        _write_atomic(raw_existing, snapshot_payload)
    if snapshot_provenance_payload is not None:
        raw_provenance_existing = paths["raw_provenance"]
        if not (raw_provenance_existing.exists() and not force):
            _write_atomic(raw_provenance_existing, snapshot_provenance_payload)
    _write_atomic(paths["audit"], _json_bytes(summary))
    _write_atomic(paths["report"], _report_markdown(summary).encode("utf-8"))
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit frozen annual-profit executed legs against a supplied current "
            "Binance USD-M exchangeInfo JSON snapshot. Offline only; no backtest or P&L rerun."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--exchange-info",
        required=True,
        type=Path,
        help="Path to the supplied raw Binance USD-M exchangeInfo JSON snapshot.",
    )
    parser.add_argument(
        "--executed-legs",
        type=Path,
        default=DEFAULT_EXECUTED_LEGS,
        help="Frozen executed_leg_details.jsonl input.",
    )
    parser.add_argument(
        "--accounts",
        type=Path,
        default=DEFAULT_ACCOUNTS,
        help="Frozen accounts.json input used for provenance/topology validation only.",
    )
    parser.add_argument(
        "--trial-definitions",
        type=Path,
        default=DEFAULT_TRIAL_DEFINITIONS,
        help="Frozen trial_definitions.json; leverage is read by trial_id and never guessed.",
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=DEFAULT_PROTOCOL,
        help="Protocol document to hash into the audit provenance.",
    )
    parser.add_argument(
        "--findings",
        type=Path,
        default=DEFAULT_FINDINGS,
        help="Mechanism-findings document to hash into the audit provenance.",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for audit JSON, per-leg JSONL, Markdown report, and raw snapshot copy.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow replacement of existing audit result files and raw snapshot copy.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    invocation = " ".join([sys.executable, "-X", "utf8", *sys.argv[1:]])
    try:
        summary = run_audit(
            exchange_info_path=args.exchange_info,
            output_dir=args.output_dir,
            executed_legs_path=args.executed_legs,
            accounts_path=args.accounts,
            trial_definitions_path=args.trial_definitions,
            protocol_path=args.protocol,
            findings_path=args.findings,
            force=args.force,
            invocation=invocation,
        )
    except (AuditInputError, OutputExistsError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": summary["status"],
                "audit": str(args.output_dir / AUDIT_JSON),
                "legs": str(args.output_dir / LEG_JSONL),
                "report": str(args.output_dir / REPORT_MD),
                "counts": summary["counts"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
