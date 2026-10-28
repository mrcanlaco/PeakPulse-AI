"""Build the annual-profit research price cache.

The raw five-minute lake is never modified by this module.  It freezes the
local ``*.parquet`` universe, audits each file's observed lifecycle, downloads
only month archives that cover an actual missing bar in the requested window,
and writes a separate runner-compatible cache under ``prices/klines/5m``.

The implementation is intentionally small and price-only.  It does not know
anything about signals, funding, strategies, or account outcomes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import sys
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote

import httpx
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    # A test runner or embedded interpreter may expose plain file-like
    # objects.  The normal Windows CLI path has reconfigure().
    pass


PROTOCOL_ID = "annual_profit_20260918"
UTC = timezone.utc
BAR_INTERVAL_MS = 5 * 60 * 1000
BAR_INTERVAL = timedelta(minutes=5)
DEFAULT_WARMUP_START = datetime(2025, 8, 1, tzinfo=UTC)
DEFAULT_WINDOW_START = datetime(2025, 9, 1, tzinfo=UTC)
DEFAULT_CUTOFF = datetime(2026, 9, 1, tzinfo=UTC)
DEFAULT_SOURCE_DIR = Path(r"D:\Quant-trading\data_lake\klines\5m")
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTOCOL_PATH = REPO_ROOT / "docs" / "ANNUAL_PROFIT_PROTOCOL_20260918.md"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / PROTOCOL_ID / "prices"

VISION_KLINE_BASE = "https://data.binance.vision/data/futures/um/monthly/klines"
BINANCE_KLINES_ENDPOINT = "https://fapi.binance.com/fapi/v1/klines"

CANONICAL_COLUMNS = (
    "symbol",
    "open_time",
    "close_time",
    "open",
    "high",
    "low",
    "close",
)
RETAINED_VOLUME_COLUMNS = ("volume", "quote_volume", "taker_buy_volume")
REQUIRED_INPUT_COLUMNS = set(CANONICAL_COLUMNS)
OHLC_COLUMNS = ("open", "high", "low", "close")
CHECKSUM_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")

LIFECYCLE_POLICY_SCHEMA = "annual_profit_price_lifecycle_v1"
DEFAULT_LIFECYCLE_POLICY_ID = "observed_source_lifecycle_v1"
LITUSDT_LIFECYCLE_POLICY = {
    "policy_id": "lit_current_underlying_launch_binance_v1",
    "policy_type": "documented_reused_ticker",
    "symbol": "LITUSDT",
    "underlying_identity": "Lighter Protocol LITUSDT current underlying; prior Litentry LIT segment excluded",
    "launch_time_utc": "2025-12-23T17:30:00Z",
    "source_url": (
        "https://www.binance.com/en-AE/support/announcement/"
        "detail/6a33be00231c4539b3a4a625538e4d1e"
    ),
    "related_source_url": (
        "https://www.binance.com/en/support/announcement/"
        "detail/2a9feaa556f74dcdaa2192366f0e247c"
    ),
    "source_description": (
        "Binance official announcement records the Lighter Protocol LITUSDT "
        "pre-market launch at 2025-12-23 17:30 UTC."
    ),
    "clip_rule": "exclude every source row with open_time before launch_time_utc",
    "minimum_contiguous_closes": 289,
    "rolling_scope": "current_lifecycle_only",
    "cross_contract_rolling": False,
}


def _lifecycle_policy_registry() -> dict[str, Any]:
    return {
        "schema": LIFECYCLE_POLICY_SCHEMA,
        "default_policy_id": DEFAULT_LIFECYCLE_POLICY_ID,
        "default": {
            "policy_id": DEFAULT_LIFECYCLE_POLICY_ID,
            "policy_type": "observed_source_lifecycle",
            "minimum_contiguous_closes": 289,
            "rolling_scope": "single_observed_lifecycle",
            "cross_contract_rolling": False,
        },
        "overrides": {"LITUSDT": dict(LITUSDT_LIFECYCLE_POLICY)},
    }


def lifecycle_policy_identity() -> str:
    payload = json.dumps(
        _lifecycle_policy_registry(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def lifecycle_policy_for(symbol: str) -> dict[str, Any]:
    policy = _lifecycle_policy_registry()["default"]
    if str(symbol).upper() == "LITUSDT":
        policy = LITUSDT_LIFECYCLE_POLICY
    return dict(policy)


class PricePreparationError(RuntimeError):
    """Base error for an input or cache preparation failure."""


class SnapshotChangedError(PricePreparationError):
    """Raised when a frozen source universe no longer matches the checkpoint."""


class ChecksumError(PricePreparationError):
    """Raised when an archive checksum is absent or does not match."""


class ArchiveUnavailable(PricePreparationError):
    """Raised when a checksum-gated Vision archive cannot be obtained."""

    def __init__(self, message: str, *, source_record: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.source_record = dict(source_record or {})


class PriceConflictError(PricePreparationError):
    """Raised for conflicting OHLC values at the same UTC open timestamp."""

    def __init__(self, message: str, conflicts: Sequence[Mapping[str, Any]]):
        super().__init__(message)
        self.conflicts = tuple(dict(item) for item in conflicts)


class NormalizationStats:
    __slots__ = ("duplicate_identical_rows",)

    def __init__(self, duplicate_identical_rows: int = 0) -> None:
        self.duplicate_identical_rows = int(duplicate_identical_rows)


class RatePacer:
    """A small monotonic pacer shared by all REST pages in this process."""

    def __init__(
        self,
        interval_seconds: float = 1.0,
        *,
        sleeper: Any = time.sleep,
        clock: Any = time.monotonic,
    ) -> None:
        self.interval_seconds = max(0.0, float(interval_seconds))
        self.sleeper = sleeper
        self.clock = clock
        self._next_allowed = 0.0

    def wait(self) -> None:
        now = float(self.clock())
        delay = self._next_allowed - now
        if delay > 0:
            self.sleeper(delay)
            now = float(self.clock())
        self._next_allowed = max(self._next_allowed, now) + self.interval_seconds

    def defer(self, seconds: float) -> None:
        self._next_allowed = max(
            self._next_allowed,
            float(self.clock()) + max(0.0, float(seconds)),
        )


def parse_utc(value: datetime | pd.Timestamp | str) -> datetime:
    """Parse an aware timestamp and normalize it to UTC."""

    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timezone-aware datetime required")
        return value.astimezone(UTC)
    if isinstance(value, pd.Timestamp):
        if value.tzinfo is None:
            raise ValueError("timezone-aware timestamp required")
        return value.tz_convert("UTC").to_pydatetime()
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        raise ValueError("timezone-aware datetime required")
    return parsed.tz_convert("UTC").to_pydatetime()


def utc_iso(value: datetime | pd.Timestamp | str | None) -> str | None:
    if value is None:
        return None
    return (
        parse_utc(value)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def epoch_ms(value: datetime | pd.Timestamp | str) -> int:
    return int(pd.Timestamp(parse_utc(value)).value // 1_000_000)


def canonical_close_time_ms(open_time_ms: int) -> int:
    return int(open_time_ms) + BAR_INTERVAL_MS - 1


def _timestamp_series_to_ms(values: pd.Series) -> np.ndarray:
    """Convert integer-ms or timezone-aware datetime values to UTC epoch ms."""

    if len(values) == 0:
        return np.empty(0, dtype=np.int64)

    is_datetime = pd.api.types.is_datetime64_any_dtype(values.dtype) or isinstance(
        values.dtype, pd.DatetimeTZDtype
    )
    if not is_datetime:
        numeric: pd.Series | None = None
        try:
            numeric = pd.to_numeric(values, errors="coerce")
        except (TypeError, ValueError):
            numeric = None
        if numeric is not None and bool(numeric.notna().all()):
            numbers = numeric.to_numpy(dtype=float)
            if not np.isfinite(numbers).all() or not np.equal(numbers, np.floor(numbers)).all():
                raise ValueError("timestamp values must be integer milliseconds")
            return numbers.astype(np.int64)

    parsed = pd.to_datetime(values, utc=True, errors="coerce")
    if bool(parsed.isna().any()):
        raise ValueError("invalid UTC timestamp")
    backing = parsed.array.asi8
    unit = getattr(parsed.array, "unit", "ns")
    if unit == "s":
        return backing.astype(np.int64) * 1_000
    if unit == "ms":
        return backing.astype(np.int64)
    if unit == "us":
        return backing.astype(np.int64) // 1_000
    return backing.astype(np.int64) // 1_000_000


def _utc_datetime_series(milliseconds: Sequence[int]) -> pd.Series:
    return pd.Series(pd.to_datetime(np.asarray(milliseconds, dtype=np.int64), unit="ms", utc=True))


def _json_value(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp, datetime)):
        return utc_iso(value)
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _row_payload(row: pd.Series, columns: Sequence[str]) -> dict[str, Any]:
    return {column: _json_value(row[column]) for column in columns if column in row}


def _cell_equal(left: Any, right: Any) -> bool:
    if left is None or left is pd.NA or right is None or right is pd.NA:
        try:
            return bool(pd.isna(left)) and bool(pd.isna(right))
        except (TypeError, ValueError):
            return left is right
    try:
        if bool(pd.isna(left)) or bool(pd.isna(right)):
            return bool(pd.isna(left)) and bool(pd.isna(right))
    except (TypeError, ValueError):
        pass
    return bool(left == right)


def _validate_duplicate_rows(frame: pd.DataFrame, symbol: str) -> tuple[pd.DataFrame, NormalizationStats]:
    if not frame["open_time"].duplicated(keep=False).any():
        return frame, NormalizationStats()

    compare_columns = tuple(column for column in frame.columns if column != "symbol")
    keep_indices: list[int] = []
    conflicts: list[dict[str, Any]] = []
    duplicate_identical = 0
    for timestamp, group in frame.groupby("open_time", sort=True, dropna=False):
        records = group.reset_index()
        first = records.iloc[0]
        for index in records["index"].iloc[1:].tolist():
            candidate = frame.loc[index]
            if all(_cell_equal(first[column], candidate[column]) for column in compare_columns):
                duplicate_identical += 1
            else:
                conflicts.append(
                    {
                        "open_time": utc_iso(timestamp),
                        "symbol": symbol,
                        "kind": "duplicate_local_timestamp",
                        "first": _row_payload(first, compare_columns),
                        "other": _row_payload(candidate, compare_columns),
                    }
                )
        keep_indices.append(int(first["index"]))
    if conflicts:
        raise PriceConflictError(
            f"{symbol}: conflicting duplicate timestamp(s) in price source",
            conflicts,
        )
    return frame.loc[keep_indices].reset_index(drop=True), NormalizationStats(duplicate_identical)


def _normalize_with_stats(
    frame: pd.DataFrame,
    symbol: str,
) -> tuple[pd.DataFrame, NormalizationStats]:
    missing = sorted(REQUIRED_INPUT_COLUMNS - set(frame.columns))
    if missing:
        raise PricePreparationError(f"{symbol}: missing price columns: {', '.join(missing)}")

    source = frame.copy()
    if len(source) == 0:
        empty = pd.DataFrame({column: pd.Series(dtype="object") for column in CANONICAL_COLUMNS})
        for column in RETAINED_VOLUME_COLUMNS:
            if column in source.columns:
                empty[column] = pd.Series(dtype="float64")
        return empty, NormalizationStats()

    symbols = source["symbol"].astype("string")
    bad_symbols = symbols.isna() | (symbols.str.upper() != symbol.upper())
    if bool(bad_symbols.any()):
        examples = symbols[bad_symbols].head(3).tolist()
        raise PricePreparationError(f"{symbol}: symbol column mismatch: {examples}")

    open_ms = _timestamp_series_to_ms(source["open_time"])
    close_ms = _timestamp_series_to_ms(source["close_time"])
    if bool((open_ms % BAR_INTERVAL_MS != 0).any()):
        raise PricePreparationError(f"{symbol}: open_time is not aligned to 5-minute UTC bars")
    expected_close = open_ms + BAR_INTERVAL_MS - 1
    if bool((close_ms != expected_close).any()):
        raise PricePreparationError(f"{symbol}: close_time is not open_time + 5m - 1ms")

    values: dict[str, np.ndarray] = {}
    for column in OHLC_COLUMNS:
        numeric = pd.to_numeric(source[column], errors="coerce").to_numpy(dtype=float)
        values[column] = numeric
    ohlc = np.column_stack([values[column] for column in OHLC_COLUMNS])
    bad_ohlc = ~np.isfinite(ohlc).all(axis=1)
    bad_ohlc |= (ohlc <= 0).any(axis=1)
    bad_ohlc |= ohlc[:, 1] < np.maximum.reduce((ohlc[:, 0], ohlc[:, 2], ohlc[:, 3]))
    bad_ohlc |= ohlc[:, 2] > np.minimum.reduce((ohlc[:, 0], ohlc[:, 1], ohlc[:, 3]))
    if bool(bad_ohlc.any()):
        first_bad = int(np.flatnonzero(bad_ohlc)[0])
        raise PricePreparationError(
            f"{symbol}: invalid OHLC at {utc_iso(pd.Timestamp(open_ms[first_bad], unit='ms', tz=UTC))}"
        )

    normalized = pd.DataFrame(
        {
            "symbol": pd.Series([symbol] * len(source), dtype="string"),
            "open_time": _utc_datetime_series(open_ms),
            "close_time": _utc_datetime_series(expected_close),
            "open": values["open"],
            "high": values["high"],
            "low": values["low"],
            "close": values["close"],
        }
    )
    for column in RETAINED_VOLUME_COLUMNS:
        if column in source.columns:
            normalized[column] = pd.to_numeric(source[column], errors="coerce").astype(float)
    normalized, stats = _validate_duplicate_rows(normalized, symbol)
    return normalized.sort_values("open_time", kind="mergesort").reset_index(drop=True), stats


def normalize_price_frame(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Return canonical UTC-ms price rows, collapsing identical duplicates."""

    return _normalize_with_stats(frame, symbol)[0]


def _compare_overlap_rows(
    existing: pd.DataFrame,
    incoming: pd.DataFrame,
    symbol: str,
) -> list[dict[str, Any]]:
    if existing.empty or incoming.empty:
        return []
    left = existing.set_index("open_time", drop=False)
    right = incoming.set_index("open_time", drop=False)
    common = left.index.intersection(right.index)
    conflicts: list[dict[str, Any]] = []
    for timestamp in common:
        left_row = left.loc[timestamp]
        right_row = right.loc[timestamp]
        if isinstance(left_row, pd.DataFrame) or isinstance(right_row, pd.DataFrame):
            raise PricePreparationError(f"{symbol}: duplicate timestamp reached overlap comparison")
        columns = ("close_time",) + OHLC_COLUMNS
        if any(not _cell_equal(left_row[column], right_row[column]) for column in columns):
            conflicts.append(
                {
                    "open_time": utc_iso(timestamp),
                    "symbol": symbol,
                    "kind": "raw_archive_overlap_conflict",
                    "local": _row_payload(left_row, columns),
                    "incoming": _row_payload(right_row, columns),
                }
            )
    return conflicts


def merge_price_frames(
    existing: pd.DataFrame,
    incoming: pd.DataFrame,
    symbol: str,
) -> pd.DataFrame:
    """Merge normalized price rows, rejecting every conflicting overlap."""

    left = normalize_price_frame(existing, symbol)
    right = normalize_price_frame(incoming, symbol)
    conflicts = _compare_overlap_rows(left, right, symbol)
    if conflicts:
        raise PriceConflictError(
            f"{symbol}: {len(conflicts)} conflicting raw/archive OHLC timestamp(s)",
            conflicts,
        )

    columns = list(CANONICAL_COLUMNS)
    for column in RETAINED_VOLUME_COLUMNS:
        if column in left.columns or column in right.columns:
            columns.append(column)
    merged = pd.concat(
        [left.reindex(columns=columns), right.reindex(columns=columns)],
        ignore_index=True,
    )
    # Existing rows are retained on identical overlaps.  No value is selected
    # using price, return, or any other favorable criterion.
    merged = merged.drop_duplicates(subset=["open_time"], keep="first")
    return merged.sort_values("open_time", kind="mergesort").reset_index(drop=True)


def _missing_runs(milliseconds: np.ndarray) -> list[tuple[int, int, int]]:
    if len(milliseconds) == 0:
        return []
    starts = [0]
    for index in range(1, len(milliseconds)):
        if int(milliseconds[index]) != int(milliseconds[index - 1]) + BAR_INTERVAL_MS:
            starts.append(index)
    ends = starts[1:] + [len(milliseconds)]
    return [
        (int(milliseconds[start]), int(milliseconds[end - 1]) + BAR_INTERVAL_MS, end - start)
        for start, end in zip(starts, ends)
    ]


def _month_key(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, tz=UTC).strftime("%Y-%m")


def _next_month(month: str) -> str:
    year, month_number = (int(value) for value in month.split("-"))
    if month_number == 12:
        return f"{year + 1:04d}-01"
    return f"{year:04d}-{month_number + 1:02d}"


def _month_bounds(month: str) -> tuple[int, int]:
    year, month_number = (int(value) for value in month.split("-"))
    start = datetime(year, month_number, 1, tzinfo=UTC)
    end_month = _next_month(month)
    end_year, end_number = (int(value) for value in end_month.split("-"))
    end = datetime(end_year, end_number, 1, tzinfo=UTC)
    return epoch_ms(start), epoch_ms(end)


def _all_observed_gap_months(times: np.ndarray) -> tuple[list[str], int]:
    if len(times) < 2:
        return [], 0
    months: set[str] = set()
    missing_count = 0
    deltas = np.diff(times)
    for index in np.flatnonzero(deltas > BAR_INTERVAL_MS):
        start = int(times[index]) + BAR_INTERVAL_MS
        end = int(times[index + 1])
        missing_count += max(0, (end - start) // BAR_INTERVAL_MS)
        if end > start:
            months.update(_month_key(value) for value in np.arange(start, end, BAR_INTERVAL_MS))
    return sorted(months), int(missing_count)


def _policy_launch_ms(policy: Mapping[str, Any]) -> int | None:
    launch = policy.get("launch_time_utc")
    return epoch_ms(str(launch)) if launch else None


def _audit_normalized_frame(
    frame: pd.DataFrame,
    *,
    symbol: str,
    warmup_start: datetime,
    cutoff: datetime,
    lifecycle_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    policy = dict(lifecycle_policy or lifecycle_policy_for(symbol))
    policy_id = str(policy["policy_id"])
    policy_identity = lifecycle_policy_identity()
    warmup_ms = epoch_ms(warmup_start)
    cutoff_ms = epoch_ms(cutoff)
    times = _timestamp_series_to_ms(frame["open_time"])
    times = np.unique(np.sort(times))
    if len(times) == 0:
        return {
            "symbol": symbol,
            "observed_start_utc": None,
            "observed_end_open_utc": None,
            "observed_end_exclusive_utc": None,
            "coverage_start_utc": None,
            "coverage_end_exclusive_utc": None,
            "expected_bar_count": 0,
            "observed_bar_count": 0,
            "missing_bar_count": 0,
            "missing_ranges": [],
            "gap_months": [],
            "lifecycle_gap_months": [],
            "lifecycle_missing_bar_count": 0,
            "leading_missing_bar_count": 0,
            "trailing_missing_bar_count": 0,
            "internal_missing_bar_count": 0,
            "prelisting_bars_not_expected": 0,
            "post_lifecycle_bars_not_expected": 0,
            "requested_range_start_ms": warmup_ms,
            "requested_cutoff_ms": cutoff_ms,
            "lifecycle_policy_id": policy_id,
            "lifecycle_policy_identity": policy_identity,
            "lifecycle_start_utc": policy.get("launch_time_utc"),
            "excluded_prelaunch_row_count": 0,
            "excluded_prelaunch_rows_in_requested_range": 0,
            "launch_day_prelaunch_bars_not_expected": 0,
        }

    observed_start = int(times[0])
    observed_end_open = int(times[-1])
    configured_lifecycle_start = _policy_launch_ms(policy)
    fixed_lifecycle = configured_lifecycle_start is not None
    lifecycle_start = (
        configured_lifecycle_start if configured_lifecycle_start is not None else observed_start
    )
    lifecycle_times = times[times >= lifecycle_start]
    current_observed_start = int(lifecycle_times[0]) if len(lifecycle_times) else None
    current_observed_end = int(lifecycle_times[-1]) if len(lifecycle_times) else None
    lifecycle_end = (
        current_observed_end + BAR_INTERVAL_MS
        if current_observed_end is not None
        else lifecycle_start
    )
    coverage_start = max(warmup_ms, lifecycle_start)
    coverage_end = min(cutoff_ms, lifecycle_end)
    if coverage_start < coverage_end:
        expected = np.arange(coverage_start, coverage_end, BAR_INTERVAL_MS, dtype=np.int64)
        present = np.isin(expected, lifecycle_times, assume_unique=True)
        missing = expected[~present]
    else:
        expected = np.empty(0, dtype=np.int64)
        missing = np.empty(0, dtype=np.int64)

    ranges = _missing_runs(missing)
    leading_enabled = (
        bool(fixed_lifecycle and current_observed_start is not None and current_observed_start > coverage_start)
        if fixed_lifecycle
        else observed_start <= warmup_ms
    )
    trailing_enabled = lifecycle_end >= cutoff_ms
    leading = 0
    trailing = 0
    internal = 0
    missing_range_payload: list[dict[str, Any]] = []
    for start, end, count in ranges:
        if start == coverage_start and leading_enabled:
            kind = "leading"
            leading += count
        elif end == coverage_end and trailing_enabled:
            kind = "trailing"
            trailing += count
        else:
            kind = "internal"
            internal += count
        missing_range_payload.append(
            {
                "kind": kind,
                "start_utc": utc_iso(pd.Timestamp(start, unit="ms", tz=UTC)),
                "end_exclusive_utc": utc_iso(pd.Timestamp(end, unit="ms", tz=UTC)),
                "bar_count": count,
                "month_keys": sorted(
                    {_month_key(value) for value in np.arange(start, end, BAR_INTERVAL_MS)}
                ),
            }
        )
    lifecycle_gap_months, lifecycle_missing = _all_observed_gap_months(lifecycle_times)
    gap_months = sorted(
        {
            month
            for item in missing_range_payload
            for month in item["month_keys"]
        }
    )
    expected_count = len(expected)
    observed_count = int(np.isin(lifecycle_times, expected, assume_unique=True).sum())
    excluded_prelaunch = int(np.count_nonzero(times < lifecycle_start)) if fixed_lifecycle else 0
    excluded_prelaunch_window = (
        int(np.count_nonzero((times >= warmup_ms) & (times < min(cutoff_ms, lifecycle_start))))
        if fixed_lifecycle
        else 0
    )
    if fixed_lifecycle:
        prelisting_bars = max(0, (min(cutoff_ms, lifecycle_start) - warmup_ms) // BAR_INTERVAL_MS)
        launch_day_start = datetime.fromtimestamp(lifecycle_start / 1000, tz=UTC).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        launch_day_prelaunch = max(
            0, (lifecycle_start - epoch_ms(launch_day_start)) // BAR_INTERVAL_MS
        )
    else:
        prelisting_bars = max(0, (coverage_start - warmup_ms) // BAR_INTERVAL_MS)
        launch_day_prelaunch = 0
    return {
        "symbol": symbol,
        "observed_start_utc": utc_iso(pd.Timestamp(observed_start, unit="ms", tz=UTC)),
        "observed_end_open_utc": utc_iso(pd.Timestamp(observed_end_open, unit="ms", tz=UTC)),
        "observed_end_exclusive_utc": utc_iso(pd.Timestamp(lifecycle_end, unit="ms", tz=UTC)),
        "current_observed_start_utc": (
            utc_iso(pd.Timestamp(current_observed_start, unit="ms", tz=UTC))
            if current_observed_start is not None
            else None
        ),
        "current_observed_end_open_utc": (
            utc_iso(pd.Timestamp(current_observed_end, unit="ms", tz=UTC))
            if current_observed_end is not None
            else None
        ),
        "coverage_start_utc": utc_iso(pd.Timestamp(coverage_start, unit="ms", tz=UTC)),
        "coverage_end_exclusive_utc": utc_iso(pd.Timestamp(coverage_end, unit="ms", tz=UTC)),
        "coverage_start_ms": coverage_start,
        "coverage_end_exclusive_ms": coverage_end,
        "requested_range_start_ms": warmup_ms,
        "requested_cutoff_ms": cutoff_ms,
        "expected_bar_count": expected_count,
        "observed_bar_count": observed_count,
        "current_segment_observed_bar_count": int(len(lifecycle_times)),
        "missing_bar_count": len(missing),
        "missing_ranges": missing_range_payload,
        "gap_months": gap_months,
        "lifecycle_gap_months": lifecycle_gap_months,
        "lifecycle_missing_bar_count": lifecycle_missing,
        "leading_missing_bar_count": leading,
        "trailing_missing_bar_count": trailing,
        "internal_missing_bar_count": internal,
        "prelisting_bars_not_expected": prelisting_bars,
        "post_lifecycle_bars_not_expected": max(0, (cutoff_ms - coverage_end) // BAR_INTERVAL_MS),
        "lifecycle_policy_id": policy_id,
        "lifecycle_policy_identity": policy_identity,
        "lifecycle_start_utc": utc_iso(pd.Timestamp(lifecycle_start, unit="ms", tz=UTC)),
        "excluded_prelaunch_row_count": excluded_prelaunch,
        "excluded_prelaunch_rows_in_requested_range": excluded_prelaunch_window,
        "launch_day_prelaunch_bars_not_expected": launch_day_prelaunch,
    }


def audit_lifecycle(
    frame: pd.DataFrame,
    *,
    symbol: str,
    warmup_start: datetime = DEFAULT_WARMUP_START,
    cutoff: datetime = DEFAULT_CUTOFF,
    lifecycle_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit the observed lifecycle, with documented symbol overrides when present."""

    normalized = normalize_price_frame(frame, symbol)
    return _audit_normalized_frame(
        normalized,
        symbol=symbol,
        warmup_start=parse_utc(warmup_start),
        cutoff=parse_utc(cutoff),
        lifecycle_policy=lifecycle_policy,
    )


def read_local_price_file(path: Path, symbol: str) -> tuple[pd.DataFrame, NormalizationStats]:
    """Read one raw Parquet symbol without touching or rewriting the lake."""

    parquet = pq.ParquetFile(path)
    available = set(parquet.schema_arrow.names)
    missing = sorted(REQUIRED_INPUT_COLUMNS - available)
    if missing:
        raise PricePreparationError(f"{symbol}: missing raw parquet columns: {', '.join(missing)}")
    columns = list(CANONICAL_COLUMNS)
    columns.extend(column for column in RETAINED_VOLUME_COLUMNS if column in available)
    batches = [batch.to_pandas() for batch in parquet.iter_batches(columns=columns, batch_size=100_000)]
    raw = pd.concat(batches, ignore_index=True) if batches else pd.DataFrame(columns=columns)
    return _normalize_with_stats(raw, symbol)


def parse_checksum(text: str, expected_filename: str | None = None) -> str:
    """Extract one SHA-256 from a Vision ``.CHECKSUM`` response."""

    matching_lines = []
    for line in text.splitlines():
        if expected_filename and expected_filename not in line:
            continue
        match = CHECKSUM_RE.search(line)
        if match:
            matching_lines.append(match.group(0).lower())
    if not matching_lines:
        matching_lines = [match.group(0).lower() for match in CHECKSUM_RE.finditer(text)]
    unique = sorted(set(matching_lines))
    if len(unique) != 1:
        raise ChecksumError("checksum response did not contain exactly one SHA-256")
    return unique[0]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksum(source: bytes | bytearray | Path, expected_sha256: str) -> str:
    actual = sha256_bytes(bytes(source)) if isinstance(source, (bytes, bytearray)) else sha256_file(Path(source))
    expected = expected_sha256.strip().lower()
    if not CHECKSUM_RE.fullmatch(expected):
        raise ChecksumError("expected checksum is not a SHA-256 digest")
    if actual != expected:
        raise ChecksumError(f"SHA-256 mismatch: expected {expected}, got {actual}")
    return actual


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_parquet(path: Path, frame: pd.DataFrame) -> None:
    """Write a complete Parquet file then atomically publish it."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        frame.to_parquet(temporary, index=False, compression="zstd")
        with temporary.open("r+b") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _header_key(value: str) -> str:
    return value.strip().lstrip("\ufeff").lower().replace(" ", "_")


def _csv_header_indices(header: Sequence[str]) -> dict[str, int] | None:
    normalized = {_header_key(value): index for index, value in enumerate(header)}
    aliases = {
        "open_time": ("open_time", "opentime"),
        "open": ("open",),
        "high": ("high",),
        "low": ("low",),
        "close": ("close",),
        "volume": ("volume",),
        "close_time": ("close_time", "closetime"),
        "quote_volume": ("quote_volume", "quote_asset_volume", "quoteassetvolume"),
        "taker_buy_volume": (
            "taker_buy_volume",
            "taker_buy_base_asset_volume",
            "takerbuybaseassetvolume",
        ),
    }
    if not any(alias in normalized for names in aliases.values() for alias in names):
        return None
    result: dict[str, int] = {}
    for canonical, names in aliases.items():
        for name in names:
            if name in normalized:
                result[canonical] = normalized[name]
                break
    required = {"open_time", "open", "high", "low", "close", "close_time"}
    if not required.issubset(result):
        raise PricePreparationError("Binance kline CSV header is missing required columns")
    return result


def _row_at(row: Sequence[str], index: int, field: str) -> str:
    try:
        return row[index]
    except IndexError as exc:
        raise PricePreparationError(f"Binance kline row is missing {field}") from exc


def _parse_kline_rows(
    rows: Iterable[Sequence[Any]],
    symbol: str,
    *,
    indices: Mapping[str, int] | None = None,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=1):
        if len(row) < 12 and indices is None:
            raise PricePreparationError(f"{symbol}: Binance kline row {row_number} has fewer than 12 fields")
        if indices is None:
            row_indices = {
                "open_time": 0,
                "open": 1,
                "high": 2,
                "low": 3,
                "close": 4,
                "volume": 5,
                "close_time": 6,
                "quote_volume": 7,
                "taker_buy_volume": 9,
            }
        else:
            row_indices = indices
        try:
            open_time = int(float(_row_at(row, row_indices["open_time"], "open_time")))
            close_time = int(float(_row_at(row, row_indices["close_time"], "close_time")))
            values = {
                "open": float(_row_at(row, row_indices["open"], "open")),
                "high": float(_row_at(row, row_indices["high"], "high")),
                "low": float(_row_at(row, row_indices["low"], "low")),
                "close": float(_row_at(row, row_indices["close"], "close")),
            }
        except (TypeError, ValueError) as exc:
            raise PricePreparationError(f"{symbol}: invalid Binance kline row {row_number}") from exc
        if close_time != canonical_close_time_ms(open_time):
            raise PricePreparationError(f"{symbol}: non-canonical close_time in Binance row {row_number}")
        record: dict[str, Any] = {
            "symbol": symbol,
            "open_time": open_time,
            "close_time": close_time,
            **values,
        }
        for column in RETAINED_VOLUME_COLUMNS:
            index = row_indices.get(column)
            if index is not None and index < len(row):
                try:
                    record[column] = float(row[index])
                except (TypeError, ValueError) as exc:
                    raise PricePreparationError(
                        f"{symbol}: invalid {column} in Binance row {row_number}"
                    ) from exc
        records.append(record)
    columns = list(CANONICAL_COLUMNS)
    for column in RETAINED_VOLUME_COLUMNS:
        if any(column in item for item in records):
            columns.append(column)
    return normalize_price_frame(pd.DataFrame(records, columns=columns), symbol)


def parse_klines_csv(stream: Any, symbol: str) -> pd.DataFrame:
    """Parse a Binance 12-field CSV with or without a header."""

    close_stream = False
    if isinstance(stream, (bytes, bytearray)):
        stream = io.BytesIO(bytes(stream))
    if isinstance(stream, str):
        stream = io.StringIO(stream)
    if hasattr(stream, "read") and not isinstance(stream, io.TextIOBase):
        stream = io.TextIOWrapper(stream, encoding="utf-8")
        close_stream = True
    reader = csv.reader(stream)
    first: list[str] | None = None
    for row in reader:
        if any(value.strip() for value in row):
            first = row
            break
    if first is None:
        return normalize_price_frame(pd.DataFrame(columns=CANONICAL_COLUMNS), symbol)
    indices = _csv_header_indices(first)
    data_rows: Iterable[Sequence[str]] = reader if indices is not None else [first, *reader]
    try:
        return _parse_kline_rows(data_rows, symbol, indices=indices)
    finally:
        if close_stream:
            stream.detach()


def parse_binance_zip(source: bytes | bytearray | Path, symbol: str) -> pd.DataFrame:
    """Parse the single CSV member in a monthly Binance Vision archive."""

    archive = io.BytesIO(bytes(source)) if isinstance(source, (bytes, bytearray)) else Path(source)
    with zipfile.ZipFile(archive) as handle:
        members = [name for name in handle.namelist() if name.lower().endswith(".csv")]
        if len(members) != 1:
            raise PricePreparationError(f"{symbol}: expected one CSV member, found {len(members)}")
        with handle.open(members[0], "r") as member:
            return parse_klines_csv(member, symbol)


def parse_binance_klines(rows: Sequence[Sequence[Any]], symbol: str) -> pd.DataFrame:
    """Parse canonical 12-field rows returned by the Binance REST endpoint."""

    return _parse_kline_rows(rows, symbol)


def _retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        try:
            target = parsedate_to_datetime(raw)
            if target.tzinfo is None:
                target = target.replace(tzinfo=UTC)
            return max(0.0, (target.astimezone(UTC) - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def _response_content(response: Any) -> bytes:
    content = getattr(response, "content", b"")
    if isinstance(content, bytes):
        return content
    return bytes(content)


class VisionArchiveClient:
    """Checksum-gated monthly archive downloader."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
        sleeper: Any = time.sleep,
    ) -> None:
        self.client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=True)
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, int(max_retries))
        self.sleeper = sleeper
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _get(self, url: str) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.get(url, timeout=self.timeout_seconds)
            except (httpx.HTTPError, OSError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise ArchiveUnavailable(f"GET failed for {url}: {exc}") from exc
                self.sleeper(min(30.0, 2.0**attempt))
                continue
            status = int(getattr(response, "status_code", 0))
            if status == 200:
                return response
            if status in (418, 429, 500, 502, 503, 504) and attempt < self.max_retries:
                retry_after = _retry_after_seconds(getattr(response, "headers", {}))
                self.sleeper(retry_after if retry_after is not None else min(30.0, 2.0**attempt))
                continue
            detail = _response_content(response)[:200].decode("utf-8", "replace")
            raise ArchiveUnavailable(f"HTTP {status} for {url}: {detail}")
        raise ArchiveUnavailable(f"GET failed for {url}: {last_error}")

    def fetch_month(
        self,
        symbol: str,
        month: str,
        archive_dir: Path,
        *,
        cached_source: Mapping[str, Any] | None = None,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        encoded = quote(symbol, safe="")
        archive_name = f"{symbol}-5m-{month}.zip"
        archive_url = f"{VISION_KLINE_BASE}/{encoded}/5m/{quote(archive_name, safe='') }"
        checksum_url = f"{archive_url}.CHECKSUM"
        archive_path = archive_dir / archive_name
        record: dict[str, Any] = {
            "symbol": symbol,
            "month": month,
            "method": "vision_archive",
            "url": archive_url,
            "checksum_url": checksum_url,
            "requested_range_utc": {
                "start": utc_iso(pd.Timestamp(_month_bounds(month)[0], unit="ms", tz=UTC)),
                "end_exclusive": utc_iso(pd.Timestamp(_month_bounds(month)[1], unit="ms", tz=UTC)),
            },
            "archive_path": str(archive_path.resolve()),
        }
        expected: str | None = None
        if cached_source:
            cached_checksum = str(cached_source.get("checksum_sha256") or "").lower()
            if archive_path.is_file() and CHECKSUM_RE.fullmatch(cached_checksum):
                try:
                    verify_checksum(archive_path, cached_checksum)
                    expected = cached_checksum
                    record["checksum_source"] = "checkpoint"
                except ChecksumError:
                    expected = None
        if expected is None:
            try:
                checksum_response = self._get(checksum_url)
            except ArchiveUnavailable as exc:
                exc.source_record.update(record)
                raise
            expected = parse_checksum(
                _response_content(checksum_response).decode("utf-8", "replace"),
                expected_filename=archive_name,
            )
            record["checksum_source"] = checksum_url
        record["checksum_sha256"] = expected

        if not archive_path.is_file() or sha256_file(archive_path) != expected:
            try:
                response = self._get(archive_url)
            except ArchiveUnavailable as exc:
                exc.source_record.update(record)
                raise
            payload = _response_content(response)
            verify_checksum(payload, expected)
            _atomic_bytes(archive_path, payload)
            record["downloaded"] = True
        else:
            record["downloaded"] = False
        record["archive_sha256"] = sha256_file(archive_path)
        frame = parse_binance_zip(archive_path, symbol)
        record["archive_rows"] = len(frame)
        if len(frame):
            record["coverage_start_utc"] = utc_iso(frame["open_time"].min())
            record["coverage_end_open_utc"] = utc_iso(frame["open_time"].max())
        record["status"] = "ok"
        return frame, record


class BinanceRestClient:
    """Optional, bounded REST fallback for one missing month range."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
        sleeper: Any = time.sleep,
        pacer: RatePacer | None = None,
    ) -> None:
        self.client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=True)
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, int(max_retries))
        self.sleeper = sleeper
        self.pacer = pacer or RatePacer(1.0, sleeper=sleeper)
        self._owns_client = client is None
        self.request_count = 0

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _get(self, params: Mapping[str, Any]) -> Any:
        for attempt in range(self.max_retries + 1):
            self.pacer.wait()
            self.request_count += 1
            try:
                response = self.client.get(
                    BINANCE_KLINES_ENDPOINT,
                    params=dict(params),
                    timeout=self.timeout_seconds,
                )
            except (httpx.HTTPError, OSError) as exc:
                if attempt >= self.max_retries:
                    raise PricePreparationError(f"REST request failed: {exc}") from exc
                self.pacer.defer(min(30.0, 2.0**attempt))
                continue
            status = int(getattr(response, "status_code", 0))
            if status == 200:
                return response
            if status in (418, 429) and attempt < self.max_retries:
                retry_after = _retry_after_seconds(getattr(response, "headers", {}))
                self.pacer.defer(retry_after if retry_after is not None else min(60.0, 2.0**attempt))
                continue
            if status >= 500 and attempt < self.max_retries:
                self.pacer.defer(min(30.0, 2.0**attempt))
                continue
            detail = _response_content(response)[:300].decode("utf-8", "replace")
            raise PricePreparationError(f"REST HTTP {status}: {detail}")
        raise PricePreparationError("REST request exhausted retries")

    def fetch_range(
        self,
        symbol: str,
        start_ms: int,
        end_ms: int,
        *,
        requested_month: str,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        if start_ms >= end_ms:
            return normalize_price_frame(pd.DataFrame(columns=CANONICAL_COLUMNS), symbol), {
                "symbol": symbol,
                "month": requested_month,
                "method": "binance_rest",
                "status": "empty_range",
                "requested_range_ms": {"start": start_ms, "end_exclusive": end_ms},
                "page_count": 0,
                "request_count": 0,
            }
        cursor = int(start_ms)
        pages: list[pd.DataFrame] = []
        page_count = 0
        fixed_end = end_ms - 1
        while cursor < end_ms:
            response = self._get(
                {
                    "symbol": symbol,
                    "interval": "5m",
                    "startTime": cursor,
                    "endTime": fixed_end,
                    "limit": 1000,
                }
            )
            try:
                payload = response.json()
            except (TypeError, ValueError) as exc:
                raise PricePreparationError(f"{symbol}: REST response was not JSON") from exc
            if not isinstance(payload, list):
                raise PricePreparationError(f"{symbol}: REST kline response was not a list")
            if not payload:
                raise PricePreparationError(
                    f"{symbol}: empty REST page before requested range was exhausted"
                )
            page = parse_binance_klines(payload, symbol)
            page_times = _timestamp_series_to_ms(page["open_time"])
            if bool((page_times < start_ms).any()) or bool((page_times >= end_ms).any()):
                raise PricePreparationError(
                    f"{symbol}: REST page returned an out-of-bounds timestamp"
                )
            pages.append(page)
            page_count += 1
            last_time = int(page_times.max())
            if last_time < cursor:
                raise PricePreparationError(f"{symbol}: REST pagination did not advance")
            cursor = last_time + BAR_INTERVAL_MS
            if page_count > 10_000:
                raise PricePreparationError(f"{symbol}: REST pagination exceeded safety bound")
        merged = pages[0]
        for page in pages[1:]:
            merged = merge_price_frames(merged, page, symbol)
        record = {
            "symbol": symbol,
            "month": requested_month,
            "method": "binance_rest",
            "url": BINANCE_KLINES_ENDPOINT,
            "requested_range_ms": {"start": start_ms, "end_exclusive": end_ms},
            "requested_range_utc": {
                "start": utc_iso(pd.Timestamp(start_ms, unit="ms", tz=UTC)),
                "end_exclusive": utc_iso(pd.Timestamp(end_ms, unit="ms", tz=UTC)),
            },
            "page_count": page_count,
            "request_count": self.request_count,
            "rows": len(merged),
            "coverage_start_utc": utc_iso(merged["open_time"].min()),
            "coverage_end_open_utc": utc_iso(merged["open_time"].max()),
            "status": "ok",
        }
        return merged, record


def _archive_path_for_rest(archive_dir: Path, symbol: str, month: str) -> Path:
    return archive_dir / "rest" / f"{symbol}-5m-{month}.parquet"


def _safe_output_relation(source_dir: Path, output_root: Path) -> None:
    source = source_dir.resolve()
    output = output_root.resolve()
    if output == source:
        raise ValueError("price output must not be the raw data-lake directory")
    try:
        output.relative_to(source)
    except ValueError:
        return
    raise ValueError("price output must not be inside the raw data-lake directory")


def _discover_sources(source_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    descriptors: list[dict[str, Any]] = []
    excluded: list[str] = []
    seen: set[str] = set()
    for path in sorted(source_dir.glob("*.parquet"), key=lambda item: item.name.upper()):
        symbol = path.stem.upper()
        if not symbol.endswith("USDT"):
            excluded.append(path.name)
            continue
        if symbol in seen:
            raise PricePreparationError(f"duplicate source symbol: {symbol}")
        seen.add(symbol)
        descriptors.append(
            {
                "symbol": symbol,
                "file_name": path.name,
                "path": str(path.resolve()),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    if not descriptors:
        raise FileNotFoundError(f"no USDT Parquet files found under {source_dir}")
    return descriptors, excluded


def _configuration_payload(
    *,
    protocol_sha256: str,
    source_dir: Path,
    output_root: Path,
    warmup_start: datetime,
    window_start: datetime,
    cutoff: datetime,
    descriptors: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": protocol_sha256,
        "source_dir": str(source_dir.resolve()),
        "output_root": str(output_root.resolve()),
        "warmup_start_utc": utc_iso(warmup_start),
        "window_start_utc": utc_iso(window_start),
        "cutoff_utc_exclusive": utc_iso(cutoff),
        "bar_interval_ms": BAR_INTERVAL_MS,
        "canonical_columns": list(CANONICAL_COLUMNS),
        "retained_volume_columns": list(RETAINED_VOLUME_COLUMNS),
        "lifecycle_policy_schema": LIFECYCLE_POLICY_SCHEMA,
        "lifecycle_policy_identity": lifecycle_policy_identity(),
        "lifecycle_policies": _lifecycle_policy_registry(),
        "source_file_hashes": [
            {"symbol": item["symbol"], "file_name": item["file_name"], "sha256": item["sha256"]}
            for item in descriptors
        ],
    }


def _configuration_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _configuration_without_lifecycle(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "lifecycle_policy_schema",
            "lifecycle_policy_identity",
            "lifecycle_policies",
        }
    }


def _is_lifecycle_only_configuration_upgrade(
    existing: Mapping[str, Any], fresh: Mapping[str, Any]
) -> bool:
    return _configuration_without_lifecycle(existing) == _configuration_without_lifecycle(fresh)


def _configuration_without_lifecycle_or_source_hashes(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    result = _configuration_without_lifecycle(payload)
    result.pop("source_file_hashes", None)
    return result


def _same_source_universe_shape(
    existing_files: Sequence[Mapping[str, Any]],
    fresh_files: Sequence[Mapping[str, Any]],
) -> bool:
    fields = ("symbol", "file_name", "path")
    existing_shape = [tuple(item.get(field) for field in fields) for item in existing_files]
    fresh_shape = [tuple(item.get(field) for field in fields) for item in fresh_files]
    return existing_shape == fresh_shape


def _current_source_rows_match_research_cache(
    *,
    source_dir: Path,
    output_root: Path,
    warmup_start: datetime,
    cutoff: datetime,
) -> list[dict[str, Any]]:
    """Check current raw rows against cached rows before rebasing byte hashes.

    A source Parquet may legitimately gain rows after the frozen research
    cutoff while its bytes change.  This check permits that narrow rebase only
    when every current raw row that can affect this research cache is already
    present with identical OHLC/volume values.  It never edits the raw lake.
    """

    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - project dependency is pinned
        raise SnapshotChangedError(
            "raw source hashes changed; duckdb is required to verify an out-of-window snapshot rebase"
        ) from exc

    raw_glob = (Path(source_dir) / "*.parquet").as_posix()
    output_glob = (Path(output_root) / "klines" / "5m" / "*.parquet").as_posix()
    query = r"""
        WITH raw AS (
            SELECT symbol, open_time, close_time, open, high, low, close,
                   volume, quote_volume, taker_buy_volume
            FROM read_parquet(?, union_by_name=true)
            WHERE open_time >= CAST(? AS TIMESTAMPTZ)
              AND open_time < CAST(? AS TIMESTAMPTZ)
              AND (
                    symbol <> 'LITUSDT'
                    OR open_time >= CAST(? AS TIMESTAMPTZ)
              )
        ), cached AS (
            SELECT symbol, open_time, close_time, open, high, low, close,
                   volume, quote_volume, taker_buy_volume
            FROM read_parquet(?, union_by_name=true)
            WHERE open_time >= CAST(? AS TIMESTAMPTZ)
              AND open_time < CAST(? AS TIMESTAMPTZ)
        )
        SELECT raw.symbol,
               COUNT(*) AS raw_rows,
               COUNT(cached.open_time) AS matched_rows,
               COUNT(CASE WHEN cached.open_time IS NULL THEN 1 END) AS missing_rows,
               COUNT(CASE WHEN cached.open_time IS NOT NULL AND NOT (
                   raw.close_time IS NOT DISTINCT FROM cached.close_time AND
                   raw.open IS NOT DISTINCT FROM cached.open AND
                   raw.high IS NOT DISTINCT FROM cached.high AND
                   raw.low IS NOT DISTINCT FROM cached.low AND
                   raw.close IS NOT DISTINCT FROM cached.close AND
                   raw.volume IS NOT DISTINCT FROM cached.volume AND
                   raw.quote_volume IS NOT DISTINCT FROM cached.quote_volume AND
                   raw.taker_buy_volume IS NOT DISTINCT FROM cached.taker_buy_volume
               ) THEN 1 END) AS mismatch_rows
        FROM raw
        LEFT JOIN cached USING (symbol, open_time)
        GROUP BY raw.symbol
        HAVING missing_rows > 0 OR mismatch_rows > 0
        ORDER BY raw.symbol
    """
    connection = duckdb.connect()
    try:
        rows = connection.execute(
            query,
            [
                raw_glob,
                utc_iso(warmup_start),
                utc_iso(cutoff),
                LITUSDT_LIFECYCLE_POLICY["launch_time_utc"],
                output_glob,
                utc_iso(warmup_start),
                utc_iso(cutoff),
            ],
        ).fetchall()
    finally:
        connection.close()
    return [
        {
            "symbol": str(row[0]),
            "raw_rows": int(row[1]),
            "matched_rows": int(row[2]),
            "missing_rows": int(row[3]),
            "mismatch_rows": int(row[4]),
        }
        for row in rows
    ]


def _new_manifest(
    *,
    protocol_path: Path,
    source_dir: Path,
    output_root: Path,
    warmup_start: datetime,
    window_start: datetime,
    cutoff: datetime,
    descriptors: list[dict[str, Any]],
    excluded: list[str],
) -> dict[str, Any]:
    protocol_sha = sha256_file(protocol_path)
    config = _configuration_payload(
        protocol_sha256=protocol_sha,
        source_dir=source_dir,
        output_root=output_root,
        warmup_start=warmup_start,
        window_start=window_start,
        cutoff=cutoff,
        descriptors=descriptors,
    )
    return {
        "manifest_version": "annual_profit_prices_v2",
        "protocol_id": PROTOCOL_ID,
        "protocol_path": str(protocol_path.resolve()),
        "protocol_sha256": protocol_sha,
        "created_at_utc": utc_iso(datetime.now(UTC)),
        "updated_at_utc": utc_iso(datetime.now(UTC)),
        "status": "running",
        "configuration": config,
        "configuration_sha256": _configuration_hash(config),
        "source_root": str(source_dir.resolve()),
        "price_root": str((output_root / "klines" / "5m").resolve()),
        "archive_root": str((output_root / "archives").resolve()),
        "quarantine_root": str((output_root / "quarantine").resolve()),
        "lifecycle_root": str((output_root / "lifecycle").resolve()),
        "lifecycle_policy": {
            "schema": LIFECYCLE_POLICY_SCHEMA,
            "identity": lifecycle_policy_identity(),
            "registry": _lifecycle_policy_registry(),
        },
        "input_identity": {
            "venue": "Binance USD-M",
            "contract_identity": "local USDT contract identity not attested",
            "lifecycle_policy_identity": lifecycle_policy_identity(),
            "timestamp_timezone": "UTC",
            "open_time_unit": "UTC epoch milliseconds represented as timestamp[ms, tz=UTC]",
            "close_time_rule": "open_time + 5m - 1ms",
            "duplicate_policy": "identical duplicates collapsed; conflicting timestamps invalid",
            "raw_source_read_only": True,
        },
        "requested_ranges": {
            "warmup_start_utc": utc_iso(warmup_start),
            "window_start_utc": utc_iso(window_start),
            "cutoff_utc_exclusive": utc_iso(cutoff),
            "output_clip_start_utc": utc_iso(warmup_start),
            "output_clip_end_exclusive_utc": utc_iso(cutoff),
        },
        "universe": {
            "selection": "all local *.parquet files with a USDT symbol stem at freeze",
            "survivorship_bias": (
                "Local-file universe only; absent, delisted, or never-collected contracts are not represented. "
                "Per-symbol observed lifecycle and gap decisions are retained below."
            ),
            "file_count": len(descriptors),
            "excluded_non_usdt_files": excluded,
            "files": descriptors,
        },
        "source_file_hash_manifest": {item["symbol"]: item["sha256"] for item in descriptors},
        "symbols": {},
        "failures": [],
        "summary": {
            "source_file_count": len(descriptors),
            "ready_symbol_count": 0,
            "missing_bars_remaining": 0,
            "failure_count": 0,
        },
    }


def _load_or_freeze_manifest(
    manifest_path: Path,
    *,
    protocol_path: Path,
    source_dir: Path,
    output_root: Path,
    warmup_start: datetime,
    window_start: datetime,
    cutoff: datetime,
    descriptors: list[dict[str, Any]],
    excluded: list[str],
    resume: bool,
) -> dict[str, Any]:
    fresh = _new_manifest(
        protocol_path=protocol_path,
        source_dir=source_dir,
        output_root=output_root,
        warmup_start=warmup_start,
        window_start=window_start,
        cutoff=cutoff,
        descriptors=descriptors,
        excluded=excluded,
    )
    if not resume or not manifest_path.is_file():
        atomic_write_json(manifest_path, fresh)
        return fresh
    with manifest_path.open("r", encoding="utf-8") as handle:
        existing = json.load(handle)
    if existing.get("configuration_sha256") != fresh["configuration_sha256"]:
        existing_configuration = existing.get("configuration", {})
        existing_files = existing.get("universe", {}).get("files", [])
        fresh_files = fresh["universe"]["files"]
        if not isinstance(existing_configuration, Mapping):
            raise SnapshotChangedError(
                "price checkpoint parameters or raw source hashes changed; refusing to mix snapshots"
            )

        lifecycle_only = _is_lifecycle_only_configuration_upgrade(
            existing_configuration, fresh["configuration"]
        )
        source_refresh = not lifecycle_only and (
            _configuration_without_lifecycle_or_source_hashes(existing_configuration)
            == _configuration_without_lifecycle_or_source_hashes(fresh["configuration"])
            and _same_source_universe_shape(existing_files, fresh_files)
        )
        if not lifecycle_only and not source_refresh:
            raise SnapshotChangedError(
                "price checkpoint parameters or raw source hashes changed; refusing to mix snapshots"
            )

        if source_refresh:
            changed_symbols = {
                str(new_item["symbol"])
                for old_item, new_item in zip(existing_files, fresh_files)
                if old_item.get("sha256") != new_item.get("sha256")
            }
            incompatibilities = _current_source_rows_match_research_cache(
                source_dir=source_dir,
                output_root=output_root,
                warmup_start=warmup_start,
                cutoff=cutoff,
            )
            if incompatibilities:
                raise SnapshotChangedError(
                    "raw source hashes changed and current research-interval rows do not match "
                    f"the cached snapshot: {incompatibilities[:3]}"
                )
            previous_configuration_sha256 = existing.get("configuration_sha256")
            existing["universe"].update(
                {
                    "file_count": fresh["universe"]["file_count"],
                    "files": fresh_files,
                    "excluded_non_usdt_files": fresh["universe"]["excluded_non_usdt_files"],
                }
            )
            existing["source_file_hash_manifest"] = fresh["source_file_hash_manifest"]
            existing["source_snapshot_rebase"] = {
                "status": "verified_out_of_window_refresh",
                "verified_at_utc": utc_iso(datetime.now(UTC)),
                "previous_configuration_sha256": previous_configuration_sha256,
                "changed_source_file_count": len(changed_symbols),
                "research_interval_rows_checked": True,
                "scope": "current raw rows from effective lifecycle start through cutoff",
                "raw_source_read_only": True,
            }

        # The lifecycle registry is an input identity change.  Upgrade only
        # checkpoint metadata; the per-symbol resumability check below still
        # forces an old LIT output through the new policy.
        existing["manifest_version"] = fresh["manifest_version"]
        existing["configuration"] = fresh["configuration"]
        existing["configuration_sha256"] = fresh["configuration_sha256"]
        existing["lifecycle_root"] = fresh["lifecycle_root"]
        existing["lifecycle_policy"] = fresh["lifecycle_policy"]
        existing["input_identity"] = fresh["input_identity"]
        fresh_by_symbol = {str(item["symbol"]): item for item in fresh_files}
        for symbol, entry in existing.get("symbols", {}).items():
            if str(symbol).upper() == "LITUSDT":
                # Do not bless a cache produced before the documented LIT
                # override.  Its output must be rebuilt and independently
                # checked against the launch boundary.
                entry.pop("lifecycle_policy_id", None)
                entry.pop("lifecycle_policy_identity", None)
            else:
                entry.setdefault("lifecycle_policy_id", DEFAULT_LIFECYCLE_POLICY_ID)
                entry.setdefault("lifecycle_policy_identity", lifecycle_policy_identity())
            if source_refresh and str(symbol) in fresh_by_symbol:
                entry["source_path"] = fresh_by_symbol[str(symbol)]["path"]
                entry["source_sha256"] = fresh_by_symbol[str(symbol)]["sha256"]
        atomic_write_json(manifest_path, existing)
    existing_files = existing.get("universe", {}).get("files", [])
    if existing_files != fresh["universe"]["files"]:
        raise SnapshotChangedError("frozen price source file manifest changed")
    existing["updated_at_utc"] = utc_iso(datetime.now(UTC))
    existing.setdefault("symbols", {})
    existing.setdefault("failures", [])
    return existing


def _quarantine_output(output_path: Path, quarantine_root: Path, symbol: str) -> str | None:
    if not output_path.is_file():
        return None
    quarantine_root.mkdir(parents=True, exist_ok=True)
    destination = quarantine_root / f"{symbol}.stale.{uuid.uuid4().hex}.parquet"
    os.replace(output_path, destination)
    return str(destination.resolve())


def _write_conflict_quarantine(
    quarantine_root: Path,
    symbol: str,
    conflicts: Sequence[Mapping[str, Any]],
) -> str:
    path = quarantine_root / f"{symbol}.conflicts.json"
    atomic_write_json(
        path,
        {
            "symbol": symbol,
            "status": "quarantined_conflict",
            "conflict_count": len(conflicts),
            "conflicts": list(conflicts),
        },
    )
    return str(path.resolve())


def _lifecycle_sidecar_path(output_root: Path, symbol: str) -> Path:
    return Path(output_root) / "lifecycle" / f"{symbol}.json"


def _is_documented_lifecycle(policy: Mapping[str, Any]) -> bool:
    return _policy_launch_ms(policy) is not None


def _lifecycle_entry_fields(policy: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lifecycle_policy_id": str(policy["policy_id"]),
        "lifecycle_policy_identity": lifecycle_policy_identity(),
    }


def _build_lifecycle_metadata(
    *,
    symbol: str,
    policy: Mapping[str, Any],
    raw_frame: pd.DataFrame,
    raw_audit: Mapping[str, Any],
    final_audit: Mapping[str, Any],
    output_frame: pd.DataFrame,
    descriptor: Mapping[str, Any],
) -> dict[str, Any] | None:
    launch_ms = _policy_launch_ms(policy)
    if launch_ms is None:
        return None

    raw_times = _timestamp_series_to_ms(raw_frame["open_time"])
    prelaunch = raw_times < launch_ms
    warmup_ms = int(raw_audit["requested_range_start_ms"])
    cutoff_ms = int(raw_audit["requested_cutoff_ms"])
    requested_prelaunch = prelaunch & (raw_times >= warmup_ms) & (raw_times < cutoff_ms)
    stale_flat_zero = np.zeros(len(raw_frame), dtype=bool)
    if len(raw_frame):
        flat_ohlc = (
            raw_frame["open"].to_numpy(dtype=float)
            == raw_frame["high"].to_numpy(dtype=float)
        ) & (
            raw_frame["open"].to_numpy(dtype=float)
            == raw_frame["low"].to_numpy(dtype=float)
        ) & (
            raw_frame["open"].to_numpy(dtype=float)
            == raw_frame["close"].to_numpy(dtype=float)
        )
        if "volume" in raw_frame.columns:
            volume = pd.to_numeric(raw_frame["volume"], errors="coerce").to_numpy(dtype=float)
            stale_flat_zero = flat_ohlc & np.isfinite(volume) & (volume == 0)

    output_times = _timestamp_series_to_ms(output_frame["open_time"])
    return {
        "policy_id": str(policy["policy_id"]),
        "policy_identity": lifecycle_policy_identity(),
        "symbol": symbol,
        "underlying_identity": policy["underlying_identity"],
        "launch_time_utc": policy["launch_time_utc"],
        "source_url": policy["source_url"],
        "related_source_url": policy.get("related_source_url"),
        "clip_rule": policy["clip_rule"],
        "minimum_contiguous_closes": int(policy["minimum_contiguous_closes"]),
        "rolling_scope": policy["rolling_scope"],
        "cross_contract_rolling": bool(policy["cross_contract_rolling"]),
        "excluded_prelaunch_row_count": int(prelaunch.sum()),
        "excluded_prelaunch_rows_in_requested_range": int(requested_prelaunch.sum()),
        "excluded_stale_flat_zero_volume_row_count": int((prelaunch & stale_flat_zero).sum()),
        "excluded_prior_or_nonstale_prelaunch_row_count": int(
            prelaunch.sum() - (prelaunch & stale_flat_zero).sum()
        ),
        "prelaunch_bars_not_expected": int(raw_audit["prelisting_bars_not_expected"]),
        "launch_day_prelaunch_bars_not_expected": int(
            raw_audit["launch_day_prelaunch_bars_not_expected"]
        ),
        "raw_source_sha256": descriptor["sha256"],
        "raw_observed_start_utc": raw_audit["observed_start_utc"],
        "raw_current_segment_start_utc": raw_audit["current_observed_start_utc"],
        "raw_current_segment_end_open_utc": raw_audit["current_observed_end_open_utc"],
        "output_rows": int(len(output_frame)),
        "output_first_open_utc": (
            utc_iso(pd.Timestamp(output_times.min(), unit="ms", tz=UTC))
            if len(output_times)
            else None
        ),
        "output_last_open_utc": (
            utc_iso(pd.Timestamp(output_times.max(), unit="ms", tz=UTC))
            if len(output_times)
            else None
        ),
        "output_first_time_matches_launch": bool(
            len(output_times) and int(output_times.min()) == launch_ms
        ),
        "raw_audit_missing_actual_bars": int(raw_audit["missing_bar_count"]),
        "final_audit_missing_actual_bars": int(final_audit["missing_bar_count"]),
        "final_audit_contiguous_current_segment": int(final_audit["current_segment_observed_bar_count"]),
    }


def _write_lifecycle_sidecar(
    *,
    output_root: Path,
    symbol: str,
    policy: Mapping[str, Any],
    metadata: Mapping[str, Any],
    status: str,
    output_sha256: str,
) -> tuple[Path, str]:
    path = _lifecycle_sidecar_path(output_root, symbol)
    payload = {
        "protocol_id": PROTOCOL_ID,
        "symbol": symbol,
        "status": status,
        "policy_id": str(policy["policy_id"]),
        "policy_identity": lifecycle_policy_identity(),
        "source_url": policy["source_url"],
        "launch_time_utc": policy["launch_time_utc"],
        "raw_source_sha256": metadata["raw_source_sha256"],
        "output_sha256": output_sha256,
        "lifecycle": dict(metadata),
    }
    atomic_write_json(path, payload)
    return path, sha256_file(path)


def _attach_lifecycle_entry(
    entry: dict[str, Any],
    *,
    output_root: Path,
    symbol: str,
    policy: Mapping[str, Any],
    raw_frame: pd.DataFrame,
    raw_audit: Mapping[str, Any],
    final_audit: Mapping[str, Any],
    output_frame: pd.DataFrame,
) -> None:
    entry.update(_lifecycle_entry_fields(policy))
    metadata = _build_lifecycle_metadata(
        symbol=symbol,
        policy=policy,
        raw_frame=raw_frame,
        raw_audit=raw_audit,
        final_audit=final_audit,
        output_frame=output_frame,
        descriptor={"sha256": entry["source_sha256"]},
    )
    if metadata is None:
        return
    entry["lifecycle"] = metadata
    sidecar_path, sidecar_sha256 = _write_lifecycle_sidecar(
        output_root=output_root,
        symbol=symbol,
        policy=policy,
        metadata=metadata,
        status=str(entry["status"]),
        output_sha256=str(entry["output_sha256"]),
    )
    entry["lifecycle_sidecar_path"] = str(sidecar_path.resolve())
    entry["lifecycle_sidecar_sha256"] = sidecar_sha256


def _clip_to_lifecycle(frame: pd.DataFrame, audit: Mapping[str, Any], symbol: str) -> pd.DataFrame:
    if frame.empty or audit.get("coverage_start_ms") is None:
        return frame.iloc[0:0].copy()
    times = _timestamp_series_to_ms(frame["open_time"])
    mask = (times >= int(audit["coverage_start_ms"])) & (times < int(audit["coverage_end_exclusive_ms"]))
    return frame.loc[mask].reset_index(drop=True)


def _clip_output_frame(
    frame: pd.DataFrame,
    *,
    warmup_start: datetime,
    cutoff: datetime,
    lifecycle_policy: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Clip rows to the immutable cache range without filling any gaps."""

    if frame.empty:
        return frame.iloc[0:0].copy()
    times = _timestamp_series_to_ms(frame["open_time"])
    policy = lifecycle_policy or lifecycle_policy_for(str(frame["symbol"].iloc[0]))
    configured_start = _policy_launch_ms(policy)
    clip_start_ms = epoch_ms(warmup_start)
    if configured_start is not None:
        clip_start_ms = max(clip_start_ms, configured_start)
    clipped = frame.loc[
        (times >= clip_start_ms) & (times < epoch_ms(cutoff))
    ].reset_index(drop=True)
    columns = [
        column
        for column in CANONICAL_COLUMNS + RETAINED_VOLUME_COLUMNS
        if column in clipped.columns
    ]
    return clipped[columns]


def _entry_is_resumable(
    entry: Mapping[str, Any] | None,
    descriptor: Mapping[str, Any],
    output_path: Path,
    *,
    lifecycle_policy: Mapping[str, Any] | None = None,
    lifecycle_sidecar_path: Path | None = None,
) -> bool:
    policy = lifecycle_policy or lifecycle_policy_for(str(descriptor["symbol"]))
    if not entry or entry.get("status") != "ready" or entry.get("source_sha256") != descriptor["sha256"]:
        return False
    if entry.get("lifecycle_policy_id") != policy["policy_id"]:
        return False
    if entry.get("lifecycle_policy_identity") != lifecycle_policy_identity():
        return False
    output_sha = entry.get("output_sha256")
    if not output_path.is_file() or not isinstance(output_sha, str):
        return False
    try:
        if sha256_file(output_path) != output_sha:
            return False
        if not _is_documented_lifecycle(policy):
            return True
        sidecar_path = lifecycle_sidecar_path or output_path.parent.parent.parent / "lifecycle" / f"{descriptor['symbol']}.json"
        if not sidecar_path.is_file():
            return False
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        if not isinstance(sidecar, Mapping):
            return False
        if sidecar.get("policy_id") != policy["policy_id"]:
            return False
        if sidecar.get("policy_identity") != lifecycle_policy_identity():
            return False
        if sidecar.get("symbol") != descriptor["symbol"]:
            return False
        if sidecar.get("raw_source_sha256") != descriptor["sha256"]:
            return False
        if sidecar.get("output_sha256") != output_sha:
            return False
        if entry.get("lifecycle_sidecar_sha256"):
            if sha256_file(sidecar_path) != entry["lifecycle_sidecar_sha256"]:
                return False
        output = normalize_price_frame(
            pd.read_parquet(output_path, columns=list(CANONICAL_COLUMNS)),
            str(descriptor["symbol"]),
        )
        output_times = _timestamp_series_to_ms(output["open_time"])
        launch_ms = _policy_launch_ms(policy)
        return bool(
            len(output_times)
            and int(output_times.min()) == launch_ms
            and bool((output_times >= launch_ms).all())
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, pd.errors.ParserError):
        return False


def _assert_source_hash_unchanged(descriptor: Mapping[str, Any]) -> None:
    current = sha256_file(Path(str(descriptor["path"])))
    if current != descriptor["sha256"]:
        raise SnapshotChangedError(
            f"{descriptor['symbol']}: raw source changed after price snapshot freeze"
        )


def _failure_entry(
    *,
    symbol: str,
    descriptor: Mapping[str, Any],
    raw_audit: Mapping[str, Any] | None,
    status: str,
    error: str,
    source_records: Sequence[Mapping[str, Any]],
    missing_before: int | None,
    missing_remaining: int | None,
    quarantine_path: str | None = None,
    lifecycle_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    policy = lifecycle_policy or lifecycle_policy_for(symbol)
    entry: dict[str, Any] = {
        "symbol": symbol,
        "source_path": descriptor["path"],
        "source_sha256": descriptor["sha256"],
        "status": status,
        "error": error,
        "sources": list(source_records),
        "coverage": {
            "missing_actual_bars_before": missing_before,
            "missing_actual_bars_remaining": missing_remaining,
            "raw_audit": raw_audit,
        },
    }
    entry.update(_lifecycle_entry_fields(policy))
    if quarantine_path:
        entry["quarantine_path"] = quarantine_path
    return entry


def _recompute_summary(manifest: dict[str, Any]) -> None:
    entries = list(manifest.get("symbols", {}).values())
    ready = [entry for entry in entries if entry.get("status") == "ready"]
    remaining = 0
    for entry in entries:
        value = entry.get("coverage", {}).get("missing_actual_bars_remaining")
        if isinstance(value, int):
            remaining += value
    manifest["summary"] = {
        "source_file_count": manifest.get("universe", {}).get("file_count", 0),
        "processed_symbol_count": len(entries),
        "ready_symbol_count": len(ready),
        "missing_bars_remaining": remaining,
        "failure_count": sum(entry.get("status") != "ready" for entry in entries),
    }
    manifest["status"] = (
        "complete"
        if len(ready) == manifest.get("universe", {}).get("file_count", 0)
        else "incomplete"
    )
    manifest["updated_at_utc"] = utc_iso(datetime.now(UTC))


def prepare_prices(
    *,
    source_dir: Path = DEFAULT_SOURCE_DIR,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    protocol_path: Path = DEFAULT_PROTOCOL_PATH,
    warmup_start: datetime = DEFAULT_WARMUP_START,
    window_start: datetime = DEFAULT_WINDOW_START,
    cutoff: datetime = DEFAULT_CUTOFF,
    resume: bool = True,
    use_rest_fallback: bool = True,
    timeout_seconds: float = 60.0,
    max_retries: int = 3,
    archive_client: VisionArchiveClient | None = None,
    rest_client: BinanceRestClient | None = None,
) -> dict[str, Any]:
    """Audit and prepare every frozen local USDT price file."""

    source_dir = Path(source_dir)
    output_root = Path(output_root)
    protocol_path = Path(protocol_path)
    warmup_start = parse_utc(warmup_start)
    window_start = parse_utc(window_start)
    cutoff = parse_utc(cutoff)
    if not warmup_start < window_start < cutoff:
        raise ValueError("expected warmup_start < window_start < cutoff")
    _safe_output_relation(source_dir, output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    price_root = output_root / "klines" / "5m"
    archive_root = output_root / "archives"
    quarantine_root = output_root / "quarantine"
    manifest_path = output_root / "price_manifest.json"
    descriptors, excluded = _discover_sources(source_dir)
    manifest = _load_or_freeze_manifest(
        manifest_path,
        protocol_path=protocol_path,
        source_dir=source_dir,
        output_root=output_root,
        warmup_start=warmup_start,
        window_start=window_start,
        cutoff=cutoff,
        descriptors=descriptors,
        excluded=excluded,
        resume=resume,
    )
    archive = archive_client or VisionArchiveClient(
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )
    rest = rest_client or (
        BinanceRestClient(timeout_seconds=timeout_seconds, max_retries=max_retries)
        if use_rest_fallback
        else None
    )
    try:
        for index, descriptor in enumerate(descriptors, start=1):
            symbol = str(descriptor["symbol"])
            lifecycle_policy = lifecycle_policy_for(symbol)
            lifecycle_sidecar = _lifecycle_sidecar_path(output_root, symbol)
            output_path = price_root / f"{symbol}.parquet"
            existing_entry = manifest.get("symbols", {}).get(symbol)
            _assert_source_hash_unchanged(descriptor)
            if resume and _entry_is_resumable(
                existing_entry,
                descriptor,
                output_path,
                lifecycle_policy=lifecycle_policy,
                lifecycle_sidecar_path=lifecycle_sidecar,
            ):
                print(f"PRICE [{index}/{len(descriptors)}] {symbol} resume=ready", flush=True)
                continue

            source_records: list[dict[str, Any]] = []
            raw_audit: dict[str, Any] | None = None
            try:
                raw_frame, normalization_stats = read_local_price_file(
                    Path(descriptor["path"]), symbol
                )
                _assert_source_hash_unchanged(descriptor)
                raw_audit = _audit_normalized_frame(
                    raw_frame,
                    symbol=symbol,
                    warmup_start=warmup_start,
                    cutoff=cutoff,
                    lifecycle_policy=lifecycle_policy,
                )
                raw_audit["duplicate_identical_rows_collapsed"] = normalization_stats.duplicate_identical_rows
                combined = raw_frame
                fetched_rows = 0
                cached_sources = {
                    str(item.get("month")): item
                    for item in (existing_entry or {}).get("sources", [])
                }
                for month in raw_audit["gap_months"]:
                    try:
                        incoming, source_record = archive.fetch_month(
                            symbol,
                            month,
                            archive_root,
                            cached_source=cached_sources.get(month),
                        )
                    except ArchiveUnavailable as archive_error:
                        if rest is None:
                            raise
                        month_start, month_end = _month_bounds(month)
                        incoming, source_record = rest.fetch_range(
                            symbol,
                            month_start,
                            month_end,
                            requested_month=month,
                        )
                        source_record["archive_probe"] = archive_error.source_record or {
                            "month": month,
                            "status": "unavailable",
                        }
                        rest_path = _archive_path_for_rest(archive_root, symbol, month)
                        atomic_write_parquet(rest_path, incoming)
                        source_record["cache_path"] = str(rest_path.resolve())
                        source_record["cache_sha256"] = sha256_file(rest_path)
                    incoming = _clip_to_lifecycle(incoming, raw_audit, symbol)
                    fetched_rows += len(incoming)
                    source_records.append(source_record)
                    combined = merge_price_frames(combined, incoming, symbol)

                final_frame = normalize_price_frame(combined, symbol)
                final_audit = _audit_normalized_frame(
                    final_frame,
                    symbol=symbol,
                    warmup_start=warmup_start,
                    cutoff=cutoff,
                    lifecycle_policy=lifecycle_policy,
                )
                missing_remaining = int(final_audit["missing_bar_count"])
                coverage = {
                    "raw_audit": raw_audit,
                    "after_backfill_audit": final_audit,
                    "missing_actual_bars_before": int(raw_audit["missing_bar_count"]),
                    "missing_actual_bars_remaining": missing_remaining,
                    "fetched_rows_in_lifecycle": fetched_rows,
                    "output_clip_start_utc": raw_audit.get("coverage_start_utc") or utc_iso(warmup_start),
                    "output_clip_end_exclusive_utc": utc_iso(cutoff),
                    "output_rows": 0,
                }
                if missing_remaining:
                    # An unresolved real gap is not a source conflict.  Publish
                    # the honest, clipped partial cache so the runner can audit
                    # all frozen symbols; the manifest status remains
                    # ``incomplete`` and no missing row is fabricated.
                    output_frame = _clip_output_frame(
                        final_frame,
                        warmup_start=warmup_start,
                        cutoff=cutoff,
                        lifecycle_policy=lifecycle_policy,
                    )
                    atomic_write_parquet(output_path, output_frame)
                    entry = _failure_entry(
                        symbol=symbol,
                        descriptor=descriptor,
                        raw_audit=raw_audit,
                        status="incomplete",
                        error=f"{missing_remaining} actual bars remain missing after backfill",
                        source_records=source_records,
                        missing_before=int(raw_audit["missing_bar_count"]),
                        missing_remaining=missing_remaining,
                        lifecycle_policy=lifecycle_policy,
                    )
                    entry["coverage"] = coverage
                    coverage["output_rows"] = len(output_frame)
                    entry["output_path"] = str(output_path.resolve())
                    entry["output_sha256"] = sha256_file(output_path)
                    entry["output_columns"] = list(output_frame.columns)
                else:
                    output_frame = _clip_output_frame(
                        final_frame,
                        warmup_start=warmup_start,
                        cutoff=cutoff,
                        lifecycle_policy=lifecycle_policy,
                    )
                    atomic_write_parquet(output_path, output_frame)
                    coverage["output_rows"] = len(output_frame)
                    entry = {
                        "symbol": symbol,
                        "source_path": descriptor["path"],
                        "source_sha256": descriptor["sha256"],
                        "status": "ready",
                        "output_path": str(output_path.resolve()),
                        "output_sha256": sha256_file(output_path),
                        "output_columns": list(output_frame.columns),
                        "sources": source_records,
                        "coverage": coverage,
                    }
                _attach_lifecycle_entry(
                    entry,
                    output_root=output_root,
                    symbol=symbol,
                    policy=lifecycle_policy,
                    raw_frame=raw_frame,
                    raw_audit=raw_audit,
                    final_audit=final_audit,
                    output_frame=output_frame,
                )
                manifest["symbols"][symbol] = entry
                manifest["failures"] = [
                    item for item in manifest["failures"] if item.get("symbol") != symbol
                ]
                if entry["status"] != "ready":
                    manifest["failures"].append(
                        {
                            "symbol": symbol,
                            "status": entry["status"],
                            "error": entry.get("error"),
                        }
                    )
                _recompute_summary(manifest)
                atomic_write_json(manifest_path, manifest)
                print(
                    f"PRICE [{index}/{len(descriptors)}] {symbol} "
                    f"status={entry['status']} missing={entry['coverage']['missing_actual_bars_remaining']}",
                    flush=True,
                )
            except SnapshotChangedError:
                raise
            except PriceConflictError as conflict:
                quarantine_path = _write_conflict_quarantine(
                    quarantine_root, symbol, conflict.conflicts
                )
                stale = _quarantine_output(output_path, quarantine_root, symbol)
                entry = _failure_entry(
                    symbol=symbol,
                    descriptor=descriptor,
                    raw_audit=raw_audit,
                    status="quarantined_conflict",
                    error=str(conflict),
                    source_records=source_records,
                    missing_before=(
                        int(raw_audit["missing_bar_count"]) if raw_audit else None
                    ),
                    missing_remaining=None,
                    quarantine_path=quarantine_path,
                    lifecycle_policy=lifecycle_policy,
                )
                if stale:
                    entry["stale_output_quarantine_path"] = stale
                entry["conflict_count"] = len(conflict.conflicts)
                manifest["symbols"][symbol] = entry
                manifest["failures"] = [
                    item for item in manifest["failures"] if item.get("symbol") != symbol
                ]
                manifest["failures"].append(
                    {"symbol": symbol, "status": entry["status"], "error": str(conflict)}
                )
                _recompute_summary(manifest)
                atomic_write_json(manifest_path, manifest)
                print(f"PRICE [{index}/{len(descriptors)}] {symbol} status=quarantined_conflict", flush=True)
            except Exception as exc:
                stale = _quarantine_output(output_path, quarantine_root, symbol)
                entry = _failure_entry(
                    symbol=symbol,
                    descriptor=descriptor,
                    raw_audit=raw_audit,
                    status="failed",
                    error=f"{type(exc).__name__}: {exc}",
                    source_records=source_records,
                    missing_before=(
                        int(raw_audit["missing_bar_count"]) if raw_audit else None
                    ),
                    missing_remaining=(
                        int(raw_audit["missing_bar_count"]) if raw_audit else None
                    ),
                    quarantine_path=stale,
                    lifecycle_policy=lifecycle_policy,
                )
                manifest["symbols"][symbol] = entry
                manifest["failures"] = [
                    item for item in manifest["failures"] if item.get("symbol") != symbol
                ]
                manifest["failures"].append(
                    {"symbol": symbol, "status": "failed", "error": entry["error"]}
                )
                _recompute_summary(manifest)
                atomic_write_json(manifest_path, manifest)
                print(
                    f"PRICE [{index}/{len(descriptors)}] {symbol} status=failed error={entry['error']}",
                    flush=True,
                )
        _recompute_summary(manifest)
        atomic_write_json(manifest_path, manifest)
        return manifest
    finally:
        if archive_client is None:
            archive.close()
        if rest is not None and rest_client is None:
            rest.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL_PATH)
    parser.add_argument("--warmup-start", default=utc_iso(DEFAULT_WARMUP_START))
    parser.add_argument("--window-start", default=utc_iso(DEFAULT_WINDOW_START))
    parser.add_argument("--cutoff", default=utc_iso(DEFAULT_CUTOFF))
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--no-rest-fallback", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--max-retries", type=int, default=3)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    manifest = prepare_prices(
        source_dir=args.source_dir,
        output_root=args.output_root,
        protocol_path=args.protocol,
        warmup_start=parse_utc(args.warmup_start),
        window_start=parse_utc(args.window_start),
        cutoff=parse_utc(args.cutoff),
        resume=not args.no_resume,
        use_rest_fallback=not args.no_rest_fallback,
        timeout_seconds=args.timeout_seconds,
        max_retries=args.max_retries,
    )
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "ready_symbol_count": manifest["summary"]["ready_symbol_count"],
                "source_file_count": manifest["summary"]["source_file_count"],
                "missing_bars_remaining": manifest["summary"]["missing_bars_remaining"],
                "manifest": str((args.output_root / "price_manifest.json").resolve()),
                "price_root": str((args.output_root / "klines" / "5m").resolve()),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0 if manifest["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
