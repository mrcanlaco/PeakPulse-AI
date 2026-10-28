"""Prepare the frozen data inputs for the 2025-08-01--2026-09-01 study.

This script deliberately has no strategy or trading code.  It only audits the
local 5-minute universe and builds a separate, resumable funding cache for the
annual-profit protocol.

The funding API uses an inclusive ``endTime``.  The protocol window is
half-open, so requests use ``endTime = requested_end - 1ms`` and keep that
value fixed for every page.  The default funding-cache end is one millisecond
after the trading cutoff so the exact cutoff settlement is retained.
Pagination advances with the greatest ``fundingTime`` returned by the
previous page plus one millisecond.
"""

import argparse
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
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import httpx
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

PROTOCOL_ID = "annual_profit_20260918"
UTC = timezone.utc
BAR_INTERVAL_MS = 5 * 60 * 1000
FUNDING_LIMIT = 1000
FUNDING_ENDPOINT = "https://fapi.binance.com/fapi/v1/fundingRate"
VISION_FUNDING_BASE = (
    "https://data.binance.vision/data/futures/um/monthly/fundingRate"
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KLINE_DIR = Path(r"D:\Quant-trading\data_lake\klines\5m")
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / PROTOCOL_ID / "data"
DEFAULT_FUNDING_START = datetime(2025, 8, 1, tzinfo=UTC)
# The price/trading window remains half-open at 2026-09-01T00:00:00Z.  The
# funding cache extends one millisecond beyond that boundary so the exact
# cutoff settlement is available for the protocol's MTM step.
DEFAULT_PRICE_END = datetime(2026, 9, 1, tzinfo=UTC)
DEFAULT_FUNDING_END = DEFAULT_PRICE_END + timedelta(milliseconds=1)
PROTOCOL_DOCUMENT = "docs/ANNUAL_PROFIT_PROTOCOL_20260918.md"

KLINE_REQUIRED_COLUMNS = {
    "symbol",
    "open_time",
    "open",
    "high",
    "low",
    "close",
}
FUNDING_COLUMNS = ("symbol", "funding_time", "funding_rate", "mark_price")
FUNDING_COLUMN_SET = set(FUNDING_COLUMNS)
_SHA256_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")


def parse_utc(value: datetime | pd.Timestamp | str) -> datetime:
    """Parse a timezone-aware value and return a UTC ``datetime``.

    Naive values are rejected so a local-machine timezone can never silently
    change the frozen protocol window.
    """

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
        raise ValueError("timezone-aware timestamp required")
    return parsed.tz_convert("UTC").to_pydatetime()


def utc_iso(value: datetime | pd.Timestamp | str | None) -> str | None:
    """Format a timestamp as an unambiguous UTC ISO-8601 string."""

    if value is None:
        return None
    parsed = parse_utc(value)
    return parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _epoch_ms(value: datetime | pd.Timestamp | str) -> int:
    return int(parse_utc(value).timestamp() * 1000)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _progress(message: str) -> None:
    """Print progress even when a Windows console uses a narrow code page."""

    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe, flush=True)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        frame.to_csv(tmp, index=False)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _atomic_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        frame.to_parquet(tmp, index=False, compression="zstd")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Hash a file without loading it into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _protocol_document_path() -> Path:
    return REPO_ROOT / PROTOCOL_DOCUMENT


def _protocol_document_sha256() -> str | None:
    path = _protocol_document_path()
    return sha256_file(path) if path.exists() else None


def _funding_end_for_price_end(price_end: datetime) -> datetime:
    return parse_utc(price_end) + timedelta(milliseconds=1)


def _source_snapshot_sha256(records: Sequence[Mapping[str, Any]]) -> str:
    entries = [
        {
            "file_name": str(record.get("file_name") or ""),
            "file_sha256": str(record.get("file_sha256") or ""),
            "symbol": str(record.get("symbol") or ""),
        }
        for record in sorted(records, key=lambda item: str(item.get("file_name") or ""))
    ]
    return _sha256_json(entries)


def _timestamp_ms_array(values: pd.Series) -> tuple[np.ndarray, int]:
    parsed = pd.to_datetime(values, utc=True, errors="coerce")
    valid = parsed.notna().to_numpy()
    if not valid.any():
        return np.empty(0, dtype=np.int64), int((~valid).sum())
    # Pandas 3 can retain seconds/milliseconds resolution instead of always
    # using nanoseconds, so scale the backing integer according to its unit.
    values = parsed.array.asi8
    unit = getattr(parsed.array, "unit", "ns")
    scale_to_ms = {"s": 1_000, "ms": 1, "us": 1 / 1_000, "ns": 1 / 1_000_000}
    scale = scale_to_ms.get(unit, 1 / 1_000_000)
    if scale >= 1:
        epoch_ms = values.astype(np.int64, copy=False) * int(scale)
    else:
        epoch_ms = values.astype(np.int64, copy=False) // int(round(1 / scale))
    return epoch_ms[valid].astype(np.int64, copy=False), int((~valid).sum())


def _record_gap_statistics(
    deltas: np.ndarray,
    record: dict[str, Any],
) -> None:
    if deltas.size == 0:
        return
    positive = deltas > 0
    gaps = deltas > BAR_INTERVAL_MS
    record["gap_count"] += int(gaps.sum())
    if gaps.any():
        record["missing_bar_count"] += int(
            np.maximum(deltas[gaps] // BAR_INTERVAL_MS - 1, 0).sum()
        )
    record["out_of_order_count"] += int((deltas < 0).sum())
    record["irregular_interval_count"] += int(
        (positive & ((deltas % BAR_INTERVAL_MS) != 0)).sum()
    )


def _numeric_ohlc_bad(frame: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    values: list[np.ndarray] = []
    for column in ("open", "high", "low", "close"):
        values.append(pd.to_numeric(frame[column], errors="coerce").astype(float).to_numpy())
    ohlc = np.column_stack(values)
    bad = ~np.isfinite(ohlc).all(axis=1)
    bad |= (ohlc <= 0).any(axis=1)
    bad |= ohlc[:, 1] < np.maximum.reduce((ohlc[:, 0], ohlc[:, 2], ohlc[:, 3]))
    bad |= ohlc[:, 2] > np.minimum.reduce((ohlc[:, 0], ohlc[:, 1], ohlc[:, 3]))
    examples: list[str] = []
    if bad.any():
        times = pd.to_datetime(frame["open_time"], utc=True, errors="coerce")
        for value in times[bad].head(5).tolist():
            if pd.isna(value):
                examples.append("invalid_time")
            else:
                examples.append(utc_iso(pd.Timestamp(value)) or "invalid_time")
    return bad, examples


def _ohlc_fingerprint(values: Sequence[Any]) -> str:
    """Return a compact, deterministic fingerprint for one OHLC tuple."""

    tokens: list[str] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            tokens.append("invalid")
            continue
        tokens.append(number.hex() if math.isfinite(number) else str(number))
    return hashlib.sha256("|".join(tokens).encode("ascii")).hexdigest()[:24]


def audit_kline_file(
    path: Path,
    *,
    batch_size: int = 100_000,
    protocol_start: datetime = DEFAULT_FUNDING_START,
    protocol_end: datetime = DEFAULT_PRICE_END,
) -> dict[str, Any]:
    """Audit one Parquet file batch-by-batch.

    The per-file timestamp set is bounded to one symbol, while Parquet row
    groups are converted and discarded incrementally.  This catches duplicate
    timestamps even when they are separated by a row-group boundary.
    """

    path = Path(path)
    symbol = path.stem.upper()
    record: dict[str, Any] = {
        "symbol": symbol,
        "file_name": path.name,
        "file_path": str(path.resolve()),
        "file_sha256": None,
        "row_count": 0,
        "open_time_min_utc": None,
        "open_time_max_utc": None,
        "close_time_min_utc": None,
        "close_time_max_utc": None,
        "gap_count": 0,
        "missing_bar_count": 0,
        "irregular_interval_count": 0,
        "out_of_order_count": 0,
        "duplicate_open_time_count": 0,
        "duplicate_timestamp_count": 0,
        "duplicate_ohlc_conflict_count": 0,
        "duplicate_ohlc_conflict_examples": [],
        "invalid_ohlc_count": 0,
        "invalid_time_count": 0,
        "symbol_mismatch_count": 0,
        "gap_examples": [],
        "invalid_ohlc_examples": [],
        "protocol_window_rows": 0,
        "warmup_rows": 0,
        "status": "ok",
        "error": None,
    }
    previous_time: int | None = None
    seen_times: set[int] = set()
    ohlc_fingerprints: dict[int, str] = {}

    try:
        record["file_sha256"] = sha256_file(path)
        parquet = pq.ParquetFile(path)
        available = set(parquet.schema_arrow.names)
        missing = sorted(KLINE_REQUIRED_COLUMNS - available)
        if missing:
            raise ValueError(f"missing required columns: {', '.join(missing)}")

        start_ms = _epoch_ms(protocol_start)
        end_ms = _epoch_ms(protocol_end)
        columns = sorted(KLINE_REQUIRED_COLUMNS | {"close_time"})
        columns = [column for column in columns if column in available]

        for batch in parquet.iter_batches(columns=columns, batch_size=batch_size):
            frame = batch.to_pandas()
            row_count = len(frame)
            record["row_count"] += row_count

            symbols = frame["symbol"].astype("string").str.upper()
            record["symbol_mismatch_count"] += int((symbols != symbol).fillna(True).sum())

            open_ms, invalid_times = _timestamp_ms_array(frame["open_time"])
            record["invalid_time_count"] += invalid_times
            if open_ms.size:
                min_ms = int(open_ms.min())
                max_ms = int(open_ms.max())
                old_min = record["open_time_min_utc"]
                old_max = record["open_time_max_utc"]
                if old_min is None or min_ms < old_min:
                    record["open_time_min_utc"] = min_ms
                if old_max is None or max_ms > old_max:
                    record["open_time_max_utc"] = max_ms

                if previous_time is not None:
                    _record_gap_statistics(
                        np.asarray([int(open_ms[0]) - previous_time], dtype=np.int64),
                        record,
                    )
                _record_gap_statistics(np.diff(open_ms), record)
                previous_time = int(open_ms[-1])

                for timestamp in open_ms.tolist():
                    timestamp_int = int(timestamp)
                    if timestamp_int in seen_times:
                        record["duplicate_open_time_count"] += 1
                    else:
                        seen_times.add(timestamp_int)
                record["duplicate_timestamp_count"] = len(seen_times) - (
                    record["row_count"] - record["invalid_time_count"]
                )
                # The expression above is only a convenient running estimate;
                # the definitive count is corrected after all batches below.

                record["protocol_window_rows"] += int(
                    ((open_ms >= start_ms) & (open_ms < end_ms)).sum()
                )
                record["warmup_rows"] += int(
                    ((open_ms >= start_ms - 31 * 24 * 60 * 60 * 1000) & (open_ms < end_ms)).sum()
                )

            bad_ohlc, examples = _numeric_ohlc_bad(frame)
            record["invalid_ohlc_count"] += int(bad_ohlc.sum())
            if examples and len(record["invalid_ohlc_examples"]) < 5:
                record["invalid_ohlc_examples"].extend(
                    examples[: 5 - len(record["invalid_ohlc_examples"])]
                )

            numeric_ohlc = [
                pd.to_numeric(frame[column], errors="coerce").astype(float).to_numpy()
                for column in ("open", "high", "low", "close")
            ]
            if open_ms.size:
                valid_time_indices = np.flatnonzero(
                    pd.to_datetime(frame["open_time"], utc=True, errors="coerce")
                    .notna()
                    .to_numpy()
                )
                for row_index, timestamp in zip(valid_time_indices.tolist(), open_ms.tolist()):
                    values = [column[row_index] for column in numeric_ohlc]
                    fingerprint = _ohlc_fingerprint(values)
                    previous_fingerprint = ohlc_fingerprints.get(int(timestamp))
                    if previous_fingerprint is None:
                        ohlc_fingerprints[int(timestamp)] = fingerprint
                    elif previous_fingerprint != fingerprint:
                        record["duplicate_ohlc_conflict_count"] += 1
                        if len(record["duplicate_ohlc_conflict_examples"]) < 5:
                            record["duplicate_ohlc_conflict_examples"].append(
                                {
                                    "open_time_utc": utc_iso(
                                        datetime.fromtimestamp(int(timestamp) / 1000, UTC)
                                    ),
                                    "first_fingerprint": previous_fingerprint,
                                    "conflicting_fingerprint": fingerprint,
                                }
                            )

            if "close_time" in frame:
                close_ms, _ = _timestamp_ms_array(frame["close_time"])
                if close_ms.size:
                    close_min = int(close_ms.min())
                    close_max = int(close_ms.max())
                    if (
                        record["close_time_min_utc"] is None
                        or close_min < record["close_time_min_utc"]
                    ):
                        record["close_time_min_utc"] = close_min
                    if (
                        record["close_time_max_utc"] is None
                        or close_max > record["close_time_max_utc"]
                    ):
                        record["close_time_max_utc"] = close_max

        valid_timestamp_count = len(seen_times)
        valid_row_count = record["row_count"] - record["invalid_time_count"]
        record["duplicate_timestamp_count"] = max(0, valid_row_count - valid_timestamp_count)
        for field in (
            "open_time_min_utc",
            "open_time_max_utc",
            "close_time_min_utc",
            "close_time_max_utc",
        ):
            if record[field] is not None:
                record[field] = utc_iso(datetime.fromtimestamp(record[field] / 1000, UTC))

    except Exception as exc:  # one broken file should not hide the other 327
        record["status"] = "error"
        record["error"] = f"{type(exc).__name__}: {exc}"

    return record


def _json_ready_audit_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items()}


def _audit_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def _min_iso(field: str) -> str | None:
        values = [record[field] for record in records if record.get(field)]
        return min(values) if values else None

    def _max_iso(field: str) -> str | None:
        values = [record[field] for record in records if record.get(field)]
        return max(values) if values else None

    numeric_fields = (
        "row_count",
        "gap_count",
        "missing_bar_count",
        "irregular_interval_count",
        "out_of_order_count",
        "duplicate_open_time_count",
        "duplicate_ohlc_conflict_count",
        "invalid_ohlc_count",
        "invalid_time_count",
        "symbol_mismatch_count",
        "protocol_window_rows",
        "warmup_rows",
    )
    return {
        "file_count": len(records),
        "ok_file_count": sum(record.get("status") == "ok" for record in records),
        "error_file_count": sum(record.get("status") != "ok" for record in records),
        "total_rows": sum(int(record.get(field, 0) or 0) for record in records for field in ("row_count",)),
        "total_gap_count": sum(int(record.get("gap_count", 0) or 0) for record in records),
        "total_missing_bar_count": sum(
            int(record.get("missing_bar_count", 0) or 0) for record in records
        ),
        "total_duplicate_open_time_count": sum(
            int(record.get("duplicate_open_time_count", 0) or 0) for record in records
        ),
        "total_duplicate_ohlc_conflict_count": sum(
            int(record.get("duplicate_ohlc_conflict_count", 0) or 0) for record in records
        ),
        "total_invalid_ohlc_count": sum(
            int(record.get("invalid_ohlc_count", 0) or 0) for record in records
        ),
        "total_invalid_time_count": sum(
            int(record.get("invalid_time_count", 0) or 0) for record in records
        ),
        "total_symbol_mismatch_count": sum(
            int(record.get("symbol_mismatch_count", 0) or 0) for record in records
        ),
        "numeric_fields_audited": list(numeric_fields),
        "earliest_open_time_utc": _min_iso("open_time_min_utc"),
        "latest_open_time_utc": _max_iso("open_time_max_utc"),
        "earliest_close_time_utc": _min_iso("close_time_min_utc"),
        "latest_close_time_utc": _max_iso("close_time_max_utc"),
        "errors": [
            {"symbol": record.get("symbol"), "error": record.get("error")}
            for record in records
            if record.get("status") != "ok"
        ],
    }


def _universe_csv_frame(records: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    columns = [
        "symbol",
        "file_name",
        "file_path",
        "file_sha256",
        "row_count",
        "open_time_min_utc",
        "open_time_max_utc",
        "close_time_min_utc",
        "close_time_max_utc",
        "gap_count",
        "missing_bar_count",
        "irregular_interval_count",
        "out_of_order_count",
        "duplicate_open_time_count",
        "duplicate_timestamp_count",
        "duplicate_ohlc_conflict_count",
        "duplicate_ohlc_conflict_examples",
        "invalid_ohlc_count",
        "invalid_time_count",
        "symbol_mismatch_count",
        "protocol_window_rows",
        "warmup_rows",
        "status",
        "error",
    ]
    frame = pd.DataFrame(list(records))
    for column in columns:
        if column not in frame:
            frame[column] = None
    return frame[columns].sort_values("symbol").reset_index(drop=True)


def _assert_audit_output_is_separate(source_dir: Path, output_dir: Path) -> None:
    source = source_dir.resolve()
    output = output_dir.resolve()
    if output == source:
        raise ValueError("audit output must not be the raw data-lake directory")
    try:
        output.relative_to(source)
    except ValueError:
        return
    raise ValueError("audit output must not be inside the raw data-lake directory")


def audit_klines(
    source_dir: Path = DEFAULT_KLINE_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    batch_size: int = 100_000,
    protocol_start: datetime = DEFAULT_FUNDING_START,
    protocol_end: datetime = DEFAULT_PRICE_END,
) -> dict[str, Any]:
    """Freeze and audit the local file universe, writing ``universe.csv`` and
    ``manifest.json`` under the research artifact directory.
    """

    source_dir = Path(source_dir)
    output_dir = Path(output_dir)
    _assert_audit_output_is_separate(source_dir, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(source_dir.glob("*.parquet"))
    freeze_time = utc_iso(_now_utc())
    records: list[dict[str, Any]] = []

    _progress(f"AUDIT start source={source_dir} files={len(files)}")
    for index, path in enumerate(files, start=1):
        record = audit_kline_file(
            path,
            batch_size=batch_size,
            protocol_start=protocol_start,
            protocol_end=protocol_end,
        )
        records.append(_json_ready_audit_record(record))
        _progress(
            f"AUDIT [{index}/{len(files)}] {record['symbol']} "
            f"rows={record['row_count']} status={record['status']}",
        )

    universe_frame = _universe_csv_frame(records)
    universe_path = output_dir / "universe.csv"
    manifest_path = output_dir / "manifest.json"
    _atomic_csv(universe_path, universe_frame)

    summary = _audit_summary(records)
    symbols = [str(record["symbol"]) for record in records]
    protocol_document_sha256 = _protocol_document_sha256()
    source_snapshot_sha256 = _source_snapshot_sha256(records)
    manifest: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "protocol_document": PROTOCOL_DOCUMENT,
        "protocol_document_sha256": protocol_document_sha256,
        "generated_at_utc": freeze_time,
        "audit": {
            "source_path": str(source_dir.resolve()),
            "source_glob": "*.parquet",
            "freeze_time_utc": freeze_time,
            "file_count": len(files),
            "files": records,
            "summary": summary,
            "batch_size": batch_size,
            "source_snapshot_sha256": source_snapshot_sha256,
        },
        "universe": {
            "path": str(universe_path.resolve()),
            "sha256": None,
            "symbols": symbols,
            "file_count": len(files),
            "selection": "Every local *.parquet file present at manifest freeze time; no prior performance or label filter.",
            "survivorship_bias": (
                "This is a local-file universe only. Symbols absent from the local lake, "
                "including potentially delisted or never-collected contracts, cannot be "
                "recovered and are not represented. Per-symbol start/end coverage and gaps "
                "are recorded above; new listings may enter after their local warmup."
            ),
            "coverage_start_utc": summary["earliest_open_time_utc"],
            "coverage_end_utc": summary["latest_open_time_utc"],
            "requested_price_warmup_start_utc": utc_iso(protocol_start),
            "requested_price_end_exclusive_utc": utc_iso(protocol_end),
        },
        "funding": {
            "status": "not_run",
            "requested_window": {
                "start_utc": utc_iso(protocol_start),
                "end_exclusive_utc": utc_iso(_funding_end_for_price_end(protocol_end)),
            },
            "symbols": {},
        },
    }
    manifest["universe"]["sha256"] = sha256_file(universe_path)
    _atomic_json(manifest_path, manifest)
    _progress(
        f"AUDIT complete files={summary['file_count']} rows={summary['total_rows']} "
        f"gaps={summary['total_gap_count']} duplicates={summary['total_duplicate_open_time_count']} "
        f"invalid_ohlc={summary['total_invalid_ohlc_count']}",
    )
    return manifest


def _frozen_universe_matches(
    manifest: Mapping[str, Any],
    source_dir: Path,
    output_dir: Path,
    protocol_start: datetime,
    protocol_end: datetime,
) -> bool:
    """Verify every input used to freeze the universe before reuse."""

    try:
        if manifest.get("protocol") != PROTOCOL_ID:
            return False
        document_name = str(manifest.get("protocol_document") or PROTOCOL_DOCUMENT)
        document_path = Path(document_name)
        if not document_path.is_absolute():
            document_path = REPO_ROOT / document_path
        if not document_path.exists():
            return False
        if manifest.get("protocol_document_sha256") != sha256_file(document_path):
            return False

        audit = manifest.get("audit", {})
        if audit.get("source_path") != str(Path(source_dir).resolve()):
            return False
        if audit.get("source_glob") != "*.parquet":
            return False
        if audit.get("file_count") != len(list(Path(source_dir).glob("*.parquet"))):
            return False
        universe = manifest.get("universe", {})
        if _coerce_epoch_ms(universe.get("requested_price_warmup_start_utc")) != _epoch_ms(protocol_start):
            return False
        if _coerce_epoch_ms(universe.get("requested_price_end_exclusive_utc")) != _epoch_ms(protocol_end):
            return False

        universe_path = Path(output_dir) / "universe.csv"
        if not universe_path.exists() or universe.get("sha256") != sha256_file(universe_path):
            return False
        universe_frame = pd.read_csv(universe_path, usecols=["symbol"])
        actual_symbols = sorted(
            {
                str(value).strip().upper()
                for value in universe_frame["symbol"].tolist()
                if str(value).strip() and str(value).strip().upper() != "NAN"
            }
        )
        expected_symbols = sorted(
            {str(value).strip().upper() for value in universe.get("symbols", []) if str(value).strip()}
        )
        if actual_symbols != expected_symbols or len(actual_symbols) != int(universe.get("file_count", -1)):
            return False

        expected_records = audit.get("files", [])
        expected_by_name = {
            str(record.get("file_name")): record
            for record in expected_records
            if isinstance(record, Mapping)
        }
        actual_paths = sorted(Path(source_dir).glob("*.parquet"), key=lambda item: item.name)
        if sorted(expected_by_name) != [path.name for path in actual_paths]:
            return False
        actual_records: list[dict[str, Any]] = []
        for path in actual_paths:
            expected = expected_by_name[path.name]
            actual_hash = sha256_file(path)
            if actual_hash != expected.get("file_sha256"):
                return False
            actual_records.append(
                {
                    "file_name": path.name,
                    "file_sha256": actual_hash,
                    "symbol": str(expected.get("symbol") or path.stem).upper(),
                }
            )
        return _source_snapshot_sha256(actual_records) == audit.get("source_snapshot_sha256")
    except (OSError, KeyError, TypeError, ValueError, pd.errors.ParserError):
        return False


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def load_or_audit_universe(
    source_dir: Path,
    output_dir: Path,
    *,
    protocol_start: datetime = DEFAULT_FUNDING_START,
    protocol_end: datetime = DEFAULT_PRICE_END,
    batch_size: int = 100_000,
    force_audit: bool = False,
) -> dict[str, Any]:
    """Load the frozen audit when it matches the source, otherwise create it."""

    _assert_audit_output_is_separate(Path(source_dir), Path(output_dir))
    manifest_path = Path(output_dir) / "manifest.json"
    manifest = _load_json(manifest_path)
    frozen_identity = bool(
        manifest
        and manifest.get("protocol") == PROTOCOL_ID
        and manifest.get("audit", {}).get("source_path")
        == str(Path(source_dir).resolve())
    )
    has_snapshot_hashes = bool(
        manifest
        and manifest.get("protocol_document_sha256")
        and manifest.get("universe", {}).get("sha256")
        and manifest.get("audit", {}).get("source_snapshot_sha256")
    )
    source_matches = bool(
        manifest
        and _frozen_universe_matches(
            manifest,
            Path(source_dir),
            Path(output_dir),
            parse_utc(protocol_start),
            parse_utc(protocol_end),
        )
    )
    if frozen_identity and has_snapshot_hashes and not source_matches and not force_audit:
        raise RuntimeError(
            "frozen universe/source snapshot changed; stop and create an explicit new audit"
        )
    if force_audit or not source_matches:
        return audit_klines(
            source_dir,
            output_dir,
            batch_size=batch_size,
            protocol_start=protocol_start,
            protocol_end=protocol_end,
        )
    return manifest or {}


def load_universe_symbols(output_dir: Path, manifest: Mapping[str, Any]) -> list[str]:
    csv_path = Path(output_dir) / "universe.csv"
    if csv_path.exists():
        frame = pd.read_csv(csv_path, usecols=["symbol"])
        symbols = [str(value).strip().upper() for value in frame["symbol"].tolist()]
        return sorted({value for value in symbols if value and value != "NAN"})
    values = manifest.get("universe", {}).get("symbols", [])
    return sorted({str(value).strip().upper() for value in values if str(value).strip()})


def _coerce_epoch_ms(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return None
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, float):
        return int(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return None
        return int(value.timestamp() * 1000)
    text = str(value).strip()
    if not text:
        return None
    try:
        if re.fullmatch(r"[-+]?\d+(?:\.0+)?", text):
            return int(float(text))
    except ValueError:
        return None
    try:
        parsed = pd.Timestamp(text)
        if parsed.tzinfo is None:
            return None
        return int(parsed.tz_convert("UTC").timestamp() * 1000)
    except (TypeError, ValueError, OverflowError):
        return None


def _pick(mapping: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def _funding_row_sha256(
    symbol: str,
    funding_time_ms: int,
    funding_rate: float,
    mark_price: float | None,
) -> str:
    canonical = {
        "funding_rate": float(funding_rate).hex(),
        "funding_time_ms": int(funding_time_ms),
        "mark_price": None if mark_price is None else float(mark_price).hex(),
        "symbol": str(symbol).strip().upper(),
    }
    return _sha256_json(canonical)


def _funding_source_id(
    source_identifier: str,
    symbol: str,
    funding_time_ms: int,
    source_row_sha256: str,
) -> str:
    return (
        f"{source_identifier}:{str(symbol).strip().upper()}:{int(funding_time_ms)}:"
        f"{source_row_sha256[:16]}"
    )


def _normalise_funding_payload(
    payload: Sequence[Any],
    symbol: str,
    start_ms: int,
    end_exclusive_ms: int,
    *,
    source_identifier: str = "Binance USD-M Futures public REST",
    strict_window: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int | None, int]:
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    max_raw_time: int | None = None
    out_of_window_count = 0
    for index, item in enumerate(payload):
        if not isinstance(item, Mapping):
            errors.append({"kind": "invalid_record", "index": index, "message": "record is not an object"})
            continue
        timestamp_ms = _coerce_epoch_ms(_pick(item, "fundingTime", "funding_time", "calc_time"))
        if timestamp_ms is None:
            errors.append({"kind": "invalid_record", "index": index, "message": "invalid funding time"})
            continue
        max_raw_time = timestamp_ms if max_raw_time is None else max(max_raw_time, timestamp_ms)
        if timestamp_ms < start_ms or timestamp_ms >= end_exclusive_ms:
            out_of_window_count += 1
            if strict_window:
                errors.append(
                    {
                        "kind": "out_of_window_record",
                        "index": index,
                        "message": "funding time is outside the requested window",
                        "funding_time_ms": timestamp_ms,
                    }
                )
            continue

        raw_symbol = _pick(item, "symbol", "pair")
        if raw_symbol is not None and str(raw_symbol).strip().upper() != symbol:
            errors.append(
                {
                    "kind": "invalid_record",
                    "index": index,
                    "message": "record symbol does not match requested symbol",
                    "record_symbol": str(raw_symbol),
                }
            )
            continue

        rate_raw = _pick(item, "fundingRate", "funding_rate", "last_funding_rate")
        try:
            rate = float(rate_raw)
        except (TypeError, ValueError):
            rate = math.nan
        if not math.isfinite(rate):
            errors.append({"kind": "invalid_record", "index": index, "message": "invalid funding rate"})
            continue

        mark_raw = _pick(item, "markPrice", "mark_price")
        mark_price: float | None
        try:
            mark_is_missing = (
                mark_raw is None
                or str(mark_raw).strip() == ""
                or bool(pd.isna(mark_raw))
            )
        except (TypeError, ValueError):
            mark_is_missing = mark_raw is None or str(mark_raw).strip() == ""
        if mark_is_missing:
            mark_price = None
            invalid_mark = False
        else:
            try:
                candidate = float(mark_raw)
                mark_price = candidate if math.isfinite(candidate) and candidate > 0 else None
                invalid_mark = mark_price is None
                if mark_price is None:
                    errors.append(
                        {
                            "kind": "invalid_mark_price",
                            "index": index,
                            "message": "mark price must be finite and positive",
                        }
                    )
            except (TypeError, ValueError):
                mark_price = None
                invalid_mark = True
                errors.append(
                    {"kind": "invalid_mark_price", "index": index, "message": "mark price is not numeric"}
                )

        if invalid_mark:
            # A nonpositive/nonfinite mark cannot safely support a funding
            # notional.  Keep the event in the audit error stream, but do not
            # put an unusable row into the canonical cache.
            continue

        row_hash = _funding_row_sha256(symbol, timestamp_ms, rate, mark_price)
        rows.append(
            {
                "symbol": symbol,
                "funding_time_ms": timestamp_ms,
                "funding_rate": rate,
                "mark_price": mark_price,
                "source_id": _funding_source_id(
                    source_identifier,
                    symbol,
                    timestamp_ms,
                    row_hash,
                ),
                "source_row_sha256": row_hash,
            }
        )
    return rows, errors, max_raw_time, out_of_window_count


def _frame_to_funding_rows(
    frame: pd.DataFrame,
    symbol: str,
    start_ms: int,
    end_exclusive_ms: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    missing = sorted(FUNDING_COLUMN_SET - set(frame.columns))
    if missing:
        raise ValueError(f"funding cache missing required columns: {', '.join(missing)}")
    if list(frame.columns) != list(FUNDING_COLUMNS):
        raise ValueError(
            "funding cache schema must be exactly " + ", ".join(FUNDING_COLUMNS)
        )
    payload = frame.to_dict(orient="records")
    rows, errors, _, _ = _normalise_funding_payload(
        payload,
        symbol,
        start_ms,
        end_exclusive_ms,
        source_identifier="cache-reconstructed",
        strict_window=True,
    )
    return rows, errors


def read_funding_cache(
    path: Path,
    symbol: str,
    start: datetime,
    end: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read and validate an existing cache without treating it as complete."""

    frame = pd.read_parquet(path)
    return _frame_to_funding_rows(frame, symbol, _epoch_ms(start), _epoch_ms(end))


def _empty_funding_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": pd.Series(dtype="string"),
            "funding_time": pd.Series(dtype="datetime64[ns, UTC]"),
            "funding_rate": pd.Series(dtype="float64"),
            "mark_price": pd.Series(dtype="float64"),
        }
    )


def funding_rows_frame(rows: Sequence[Mapping[str, Any]], symbol: str) -> pd.DataFrame:
    """Convert internal rows to the exact four-column cache schema."""

    if not rows:
        return _empty_funding_frame()
    frame = pd.DataFrame(
        {
            "symbol": [symbol for _ in rows],
            "funding_time": pd.to_datetime(
                [int(row["funding_time_ms"]) for row in rows], unit="ms", utc=True
            ),
            "funding_rate": [float(row["funding_rate"]) for row in rows],
            "mark_price": [row.get("mark_price") for row in rows],
        }
    )
    frame["funding_rate"] = pd.to_numeric(frame["funding_rate"], errors="coerce").astype(float)
    frame["mark_price"] = pd.to_numeric(frame["mark_price"], errors="coerce").astype(float)
    return frame[list(FUNDING_COLUMNS)].sort_values("funding_time").reset_index(drop=True)


@dataclass
class RequestPacer:
    """One aggregate request-start limiter shared by all symbols and retries."""

    interval_seconds: float = 1.0
    clock: Callable[[], float] = time.monotonic
    sleeper: Callable[[float], None] = time.sleep
    _last_start: float | None = None
    _retry_not_before: float | None = None

    def defer_for(self, seconds: float | None) -> None:
        """Publish a server-mandated deadline to every later request."""

        if seconds is None:
            return
        try:
            delay = max(0.0, float(seconds))
        except (TypeError, ValueError):
            return
        deadline = self.clock() + delay
        self._retry_not_before = max(self._retry_not_before or deadline, deadline)

    def wait(self) -> None:
        now = self.clock()
        deadlines = []
        if self._last_start is not None:
            deadlines.append(self._last_start + self.interval_seconds)
        if self._retry_not_before is not None:
            deadlines.append(self._retry_not_before)
        if deadlines:
            delay = max(deadlines) - now
            if delay > 0:
                self.sleeper(delay)
        self._last_start = self.clock()
        if self._retry_not_before is not None and self._last_start >= self._retry_not_before:
            self._retry_not_before = None


@dataclass
class PageFetch:
    ok: bool
    status_code: int | None
    payload: Any = None
    error: str | None = None
    attempts: int = 0
    retry_after_seconds: float | None = None
    transport_status: str = "success"


def _retry_after_seconds(headers: Mapping[str, Any] | None, now: datetime | None = None) -> float | None:
    if not headers:
        return None
    raw: Any = None
    for key, value in headers.items():
        if str(key).lower() == "retry-after":
            raw = value
            break
    if raw is None:
        return None
    try:
        seconds = float(str(raw).strip())
        return max(0.0, seconds)
    except (TypeError, ValueError):
        pass
    try:
        retry_at = parsedate_to_datetime(str(raw))
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        reference = now or _now_utc()
        return max(0.0, (retry_at.astimezone(UTC) - reference).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def _client_get(client: Any, url: str, params: Mapping[str, Any], timeout: float) -> Any:
    try:
        return client.get(url, params=dict(params), timeout=timeout)
    except TypeError as exc:
        # Small fake clients used by unit tests often omit ``timeout``.
        if "timeout" not in str(exc):
            raise
        return client.get(url, params=dict(params))


def _request_json(
    client: Any,
    params: Mapping[str, Any],
    *,
    pacer: RequestPacer,
    sleeper: Callable[[float], None],
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
    timeout: float = 20.0,
) -> PageFetch:
    """Request one page, retrying transient failures and honoring Retry-After."""

    last_status: int | None = None
    last_error: str | None = None
    last_retry_after: float | None = None
    for attempt in range(max_retries + 1):
        pacer.wait()
        try:
            response = _client_get(client, FUNDING_ENDPOINT, params, timeout)
        except Exception as exc:  # network and client transport failures
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt >= max_retries:
                return PageFetch(
                    ok=False,
                    status_code=None,
                    error=last_error,
                    attempts=attempt + 1,
                    transport_status="network_error",
                )
            sleeper(backoff_seconds * (2**attempt))
            continue

        last_status = int(getattr(response, "status_code", 0) or 0)
        headers = getattr(response, "headers", {})
        if last_status == 200:
            try:
                payload = response.json()
            except Exception as exc:
                return PageFetch(
                    ok=False,
                    status_code=last_status,
                    error=f"invalid JSON: {type(exc).__name__}: {exc}",
                    attempts=attempt + 1,
                    transport_status="invalid_response",
                )
            return PageFetch(ok=True, status_code=last_status, payload=payload, attempts=attempt + 1)

        last_retry_after = _retry_after_seconds(headers)
        retryable = last_status in {418, 429} or last_status >= 500
        if retryable and attempt < max_retries:
            delay = backoff_seconds * (2**attempt)
            if last_retry_after is not None:
                delay = max(delay, last_retry_after)
            pacer.defer_for(delay)
            continue

        transport_status = "rate_limited" if last_status in {418, 429} else "http_error"
        last_error = f"HTTP {last_status}"
        if last_status in {418, 429}:
            pacer.defer_for(last_retry_after)
        return PageFetch(
            ok=False,
            status_code=last_status,
            error=last_error,
            attempts=attempt + 1,
            retry_after_seconds=last_retry_after,
            transport_status=transport_status,
        )

    return PageFetch(
        ok=False,
        status_code=last_status,
        error=last_error or "request failed",
        attempts=max_retries + 1,
        retry_after_seconds=last_retry_after,
        transport_status="http_error",
    )


def _new_funding_metadata(
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    source: str = "Binance USD-M Futures public REST",
    snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    start_ms = _epoch_ms(start)
    end_ms = _epoch_ms(end)
    return {
        "protocol": PROTOCOL_ID,
        "symbol": symbol,
        "snapshot": dict(snapshot) if snapshot is not None else None,
        "status": "running",
        "transport_status": "not_started",
        "data_status": "not_observed",
        "coverage_status": "not_started",
        "requested_window": {
            "start_utc": utc_iso(start),
            "end_exclusive_utc": utc_iso(end),
            "start_ms": start_ms,
            "end_exclusive_ms": end_ms,
            "api_end_time_ms_inclusive": end_ms - 1,
        },
        "provenance": {
            "source": source,
            "endpoint": FUNDING_ENDPOINT,
            "method": "GET",
            "credentials": "none",
            "page_limit": FUNDING_LIMIT,
            "pagination": "startTime = greatest returned fundingTime + 1ms",
            "end_time_policy": "fixed API endTime = requested exclusive end - 1ms",
            "row_provenance": "deterministic SHA-256 sidecar keyed by funding observation",
        },
        "page_count": 0,
        "request_count": 0,
        "page_provenance": [],
        "range": {
            "first_funding_time_utc": None,
            "last_funding_time_utc": None,
            "row_count": 0,
        },
        "completion_basis": None,
        "final_page_status": None,
        "rest_final_page_status": None,
        "errors": [],
        "duplicate_timestamp_count": 0,
        "duplicate_timestamp_conflict_count": 0,
        "duplicate_timestamp_conflict_samples": [],
        "mark_price_conflict_count": 0,
        "mark_price_conflict_samples": [],
        "out_of_window_count": 0,
        "invalid_record_count": 0,
        "resume": {
            "existing_rows": 0,
            "resume_start_ms": start_ms,
            "used_existing_provenance": False,
        },
        "network_attempted": False,
        "created_at_utc": utc_iso(_now_utc()),
        "updated_at_utc": None,
    }


def _same_requested_window(metadata: Mapping[str, Any], start: datetime, end: datetime) -> bool:
    requested = metadata.get("requested_window", {})
    return (
        requested.get("start_ms") == _epoch_ms(start)
        and requested.get("end_exclusive_ms") == _epoch_ms(end)
    )


def _requested_window_bounds(metadata: Mapping[str, Any]) -> tuple[int, int] | None:
    requested = metadata.get("requested_window", {})
    start_ms = _coerce_epoch_ms(requested.get("start_ms"))
    end_ms = _coerce_epoch_ms(requested.get("end_exclusive_ms"))
    if start_ms is None:
        start_ms = _coerce_epoch_ms(requested.get("start_utc"))
    if end_ms is None:
        end_ms = _coerce_epoch_ms(requested.get("end_exclusive_utc"))
    if start_ms is not None and end_ms is not None:
        return start_ms, end_ms
    return None


def _is_prefix_window(metadata: Mapping[str, Any], start: datetime, end: datetime) -> bool:
    bounds = _requested_window_bounds(metadata)
    if bounds is None:
        return False
    return bounds[0] == _epoch_ms(start) and _epoch_ms(start) < bounds[1] <= _epoch_ms(end)


def _validate_page_bounds(
    payload: Sequence[Any],
    requested_start_ms: int,
    requested_end_ms: int,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, Mapping):
            continue
        timestamp_ms = _coerce_epoch_ms(_pick(item, "fundingTime", "funding_time", "calc_time"))
        if timestamp_ms is None:
            continue
        if timestamp_ms < requested_start_ms or timestamp_ms > requested_end_ms:
            errors.append(
                {
                    "kind": "page_out_of_requested_bounds",
                    "index": index,
                    "funding_time_ms": timestamp_ms,
                    "requested_start_ms": requested_start_ms,
                    "requested_end_ms": requested_end_ms,
                }
            )
    return errors


def _merge_funding_rows(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]], int]:
    """Deduplicate exact observations and retain conflicting observations.

    A same-time/same-rate duplicate is harmless and removed.  A same-time
    differing-rate observation is never silently selected: every observation
    is retained, and a conflict sample is returned so the caller cannot mark
    the cache complete.  A mark-price conflict invalidates the whole timestamp
    so downstream code cannot accidentally select the first mark.
    """

    by_time: dict[int, list[dict[str, Any]]] = {}
    duplicate_count = 0
    mark_price_conflict_count = 0
    conflicts: list[dict[str, Any]] = []
    invalid_mark_times: set[int] = set()
    for source_row in rows:
        symbol = str(source_row.get("symbol") or "").upper()
        funding_time_ms = int(source_row["funding_time_ms"])
        funding_rate = float(source_row["funding_rate"])
        mark_price = source_row.get("mark_price")
        if mark_price is not None:
            try:
                mark_price = float(mark_price)
            except (TypeError, ValueError):
                mark_price = None
            if mark_price is not None and (not math.isfinite(mark_price) or mark_price <= 0):
                mark_price = None
        source_row_sha256 = str(source_row.get("source_row_sha256") or "")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", source_row_sha256):
            source_row_sha256 = _funding_row_sha256(
                symbol,
                funding_time_ms,
                funding_rate,
                mark_price,
            )
        row = {
            "symbol": symbol,
            "funding_time_ms": funding_time_ms,
            "funding_rate": funding_rate,
            "mark_price": mark_price,
            "source_id": str(source_row.get("source_id") or "")
            or _funding_source_id("reconstructed", symbol, funding_time_ms, source_row_sha256),
            "source_row_sha256": source_row_sha256,
        }
        candidates = by_time.setdefault(row["funding_time_ms"], [])
        matching_rate = next(
            (candidate for candidate in candidates if candidate["funding_rate"] == row["funding_rate"]),
            None,
        )
        for candidate in candidates:
            if (
                candidate.get("mark_price") is not None
                and row.get("mark_price") is not None
                and candidate.get("mark_price") != row.get("mark_price")
            ):
                mark_price_conflict_count += 1
                invalid_mark_times.add(row["funding_time_ms"])
                if len(conflicts) < 10:
                    conflicts.append(
                        {
                            "kind": "mark_price_conflict",
                            "funding_time_utc": utc_iso(
                                datetime.fromtimestamp(row["funding_time_ms"] / 1000, UTC)
                            ),
                            "mark_prices": sorted(
                                {
                                    float(candidate["mark_price"]),
                                    float(row["mark_price"]),
                                }
                            ),
                        }
                    )
        if matching_rate is not None:
            duplicate_count += 1
            if (
                matching_rate.get("mark_price") is None
                and row.get("mark_price") is not None
                and row["funding_time_ms"] not in invalid_mark_times
            ):
                matching_rate["mark_price"] = row["mark_price"]
            continue
        if candidates:
            sample = {
                "kind": "funding_rate_conflict",
                "funding_time_utc": utc_iso(
                    datetime.fromtimestamp(row["funding_time_ms"] / 1000, UTC)
                ),
                "rates": sorted(
                    {float(candidate["funding_rate"]) for candidate in candidates}
                    | {row["funding_rate"]}
                ),
            }
            if len(conflicts) < 10:
                conflicts.append(sample)
        candidates.append(row)

    merged = [
        candidate
        for timestamp, candidates in by_time.items()
        if timestamp not in invalid_mark_times
        for candidate in candidates
    ]
    merged.sort(key=lambda value: (int(value["funding_time_ms"]), float(value["funding_rate"])))
    return merged, duplicate_count, conflicts, mark_price_conflict_count


def _metadata_range(metadata: dict[str, Any], rows: Sequence[Mapping[str, Any]]) -> None:
    metadata["range"]["row_count"] = len(rows)
    if rows:
        times = [int(row["funding_time_ms"]) for row in rows]
        metadata["range"]["first_funding_time_utc"] = utc_iso(
            datetime.fromtimestamp(min(times) / 1000, UTC)
        )
        metadata["range"]["last_funding_time_utc"] = utc_iso(
            datetime.fromtimestamp(max(times) / 1000, UTC)
        )


def fetch_funding_for_symbol(
    symbol: str,
    start: datetime | str = DEFAULT_FUNDING_START,
    end: datetime | str = DEFAULT_FUNDING_END,
    *,
    client: Any,
    pacer: RequestPacer | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
    timeout: float = 20.0,
    page_limit: int = FUNDING_LIMIT,
    existing_rows: Sequence[Mapping[str, Any]] = (),
    existing_metadata: Mapping[str, Any] | None = None,
    snapshot: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch all REST funding pages for one symbol and return rows + metadata."""

    canonical_symbol = str(symbol).strip().upper()
    start_dt = parse_utc(start)
    end_dt = parse_utc(end)
    if end_dt <= start_dt:
        raise ValueError("funding end must be after funding start")
    if page_limit < 1 or page_limit > FUNDING_LIMIT:
        raise ValueError(f"page_limit must be between 1 and {FUNDING_LIMIT}")
    start_ms = _epoch_ms(start_dt)
    end_exclusive_ms = _epoch_ms(end_dt)
    api_end_ms = end_exclusive_ms - 1
    limiter = pacer or RequestPacer(sleeper=sleeper)
    metadata = _new_funding_metadata(
        canonical_symbol,
        start_dt,
        end_dt,
        snapshot=snapshot,
    )
    metadata["provenance"]["page_limit"] = page_limit
    merged_input, existing_duplicates, existing_conflicts, mark_conflicts = _merge_funding_rows(
        existing_rows
    )
    all_rows = list(merged_input)
    metadata["duplicate_timestamp_count"] = existing_duplicates
    metadata["duplicate_timestamp_conflict_count"] = len(existing_conflicts)
    metadata["duplicate_timestamp_conflict_samples"] = existing_conflicts
    metadata["mark_price_conflict_count"] = mark_conflicts
    metadata["mark_price_conflict_samples"] = [
        value for value in existing_conflicts if value.get("kind") == "mark_price_conflict"
    ]
    metadata["resume"]["existing_rows"] = len(all_rows)

    prior_window = _requested_window_bounds(existing_metadata or {}) if existing_metadata else None
    prior_page_count = int(existing_metadata.get("page_count", 0) or 0) if existing_metadata else 0
    prior_request_count = int(existing_metadata.get("request_count", 0) or 0) if existing_metadata else 0
    metadata["page_count"] = prior_page_count
    metadata["request_count"] = prior_request_count
    prior_page_provenance = (
        list(existing_metadata.get("page_provenance", []))
        if existing_metadata and isinstance(existing_metadata.get("page_provenance"), list)
        else []
    )
    metadata["page_provenance"] = prior_page_provenance
    if existing_metadata:
        metadata["resume"]["previous_page_count"] = prior_page_count
        metadata["resume"]["previous_request_count"] = prior_request_count
        metadata["resume"]["previous_run"] = {
            "created_at_utc": existing_metadata.get("created_at_utc"),
            "updated_at_utc": existing_metadata.get("updated_at_utc"),
            "requested_window": existing_metadata.get("requested_window"),
            "provenance": existing_metadata.get("provenance"),
            "page_count": prior_page_count,
            "request_count": prior_request_count,
            "page_provenance": prior_page_provenance,
            "final_page_status": existing_metadata.get("final_page_status"),
            "completion_basis": existing_metadata.get("completion_basis"),
            "artifact_sha256": existing_metadata.get("artifact_sha256"),
        }

    prior_integrity_issue = bool(
        existing_metadata
        and (
            int(existing_metadata.get("invalid_record_count", 0) or 0) > 0
            or int(existing_metadata.get("duplicate_timestamp_conflict_count", 0) or 0) > 0
            or int(existing_metadata.get("mark_price_conflict_count", 0) or 0) > 0
        )
    )
    resume_start_ms = start_ms
    if (
        existing_metadata
        and _is_prefix_window(existing_metadata, start_dt, end_dt)
        and not prior_integrity_issue
    ):
        previous_end_ms = prior_window[1] if prior_window else start_ms
        if all_rows:
            resume_start_ms = max(
                start_ms,
                max(int(row["funding_time_ms"]) for row in all_rows) + 1,
            )
        else:
            resume_start_ms = previous_end_ms
        if existing_metadata.get("status") in {"complete", "reused"}:
            resume_start_ms = max(resume_start_ms, previous_end_ms)
        resume_start_ms = min(api_end_ms + 1, resume_start_ms)
        metadata["resume"]["used_existing_provenance"] = True
        metadata["resume"]["prefix_end_exclusive_ms"] = previous_end_ms
    metadata["resume"]["resume_start_ms"] = resume_start_ms

    if existing_metadata:
        metadata["resume"]["previous_error_count"] = len(existing_metadata.get("errors", []))
        metadata["resume"]["previous_errors"] = list(existing_metadata.get("errors", []))[:20]
        metadata["resume"]["previous_integrity_issue"] = prior_integrity_issue

    current_start_ms = resume_start_ms
    final_status: str | None = None
    completion_basis: str | None = None
    while current_start_ms <= api_end_ms:
        params = {
            "symbol": canonical_symbol,
            "startTime": current_start_ms,
            "endTime": api_end_ms,
            "limit": page_limit,
        }
        metadata["network_attempted"] = True
        page = _request_json(
            client,
            params,
            pacer=limiter,
            sleeper=sleeper,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            timeout=timeout,
        )
        metadata["request_count"] += page.attempts
        page_record: dict[str, Any] = {
            "page": metadata["page_count"] + 1,
            "requested_start_ms": current_start_ms,
            "requested_end_ms": api_end_ms,
            "limit": page_limit,
            "attempts": page.attempts,
            "status_code": page.status_code,
            "transport_status": page.transport_status,
        }
        if page.retry_after_seconds is not None:
            page_record["retry_after_seconds"] = page.retry_after_seconds
        if not page.ok:
            page_record["response_count"] = None
            metadata["page_provenance"].append(page_record)
            metadata["transport_status"] = page.transport_status
            metadata["status"] = "failed" if not all_rows else "partial"
            metadata["data_status"] = "partial" if all_rows else "not_observed"
            final_status = (
                "network_error"
                if page.transport_status == "network_error"
                else "http_" + str(page.status_code)
                if page.status_code is not None
                else "request_failed"
            )
            error: dict[str, Any] = {
                "kind": page.transport_status,
                "page": metadata["page_count"] + 1,
                "request_start_ms": current_start_ms,
                "request_start_utc": utc_iso(datetime.fromtimestamp(current_start_ms / 1000, UTC)),
                "status_code": page.status_code,
                "message": page.error,
                "attempts": page.attempts,
            }
            if page.retry_after_seconds is not None:
                error["retry_after_seconds"] = page.retry_after_seconds
            metadata["errors"].append(error)
            break

        metadata["transport_status"] = "success"
        metadata["page_count"] += 1
        payload = page.payload
        page_record["page"] = metadata["page_count"]
        if not isinstance(payload, list):
            page_record["response_count"] = None
            metadata["page_provenance"].append(page_record)
            final_status = "invalid_payload"
            metadata["status"] = "failed" if not all_rows else "partial"
            metadata["errors"].append(
                {
                    "kind": "invalid_payload",
                    "page": metadata["page_count"],
                    "message": "funding response is not a JSON list",
                }
            )
            break
        if not payload:
            page_record["response_count"] = 0
            page_record["min_raw_time_ms"] = None
            page_record["max_raw_time_ms"] = None
            metadata["page_provenance"].append(page_record)
            final_status = "empty_response"
            completion_basis = "empty_response"
            break

        page_bound_errors = _validate_page_bounds(payload, current_start_ms, api_end_ms)
        raw_page_times = [
            timestamp
            for item in payload
            if isinstance(item, Mapping)
            for timestamp in [_coerce_epoch_ms(_pick(item, "fundingTime", "funding_time", "calc_time"))]
            if timestamp is not None
        ]
        page_record["response_count"] = len(payload)
        page_record["min_raw_time_ms"] = min(raw_page_times) if raw_page_times else None
        page_record["max_raw_time_ms"] = max(raw_page_times) if raw_page_times else None
        metadata["page_provenance"].append(page_record)

        page_rows, page_errors, max_raw_time, out_of_window = _normalise_funding_payload(
            payload,
            canonical_symbol,
            start_ms,
            end_exclusive_ms,
        )
        metadata["errors"].extend(
            {"page": metadata["page_count"], **error} for error in page_errors[:20]
        )
        metadata["invalid_record_count"] += sum(
            error.get("kind") in {"invalid_record", "invalid_mark_price"} for error in page_errors
        )
        metadata["out_of_window_count"] += out_of_window
        all_rows.extend(page_rows)

        if page_bound_errors:
            metadata["errors"].extend(
                {"page": metadata["page_count"], **error}
                for error in page_bound_errors[:20]
            )
            final_status = "page_out_of_requested_bounds"
            metadata["status"] = "partial" if all_rows else "failed"
            metadata["coverage_status"] = "partial" if all_rows else "not_observed"
            break

        if max_raw_time is None:
            final_status = "invalid_payload"
            metadata["status"] = "failed" if not all_rows else "partial"
            metadata["errors"].append(
                {
                    "kind": "invalid_payload",
                    "page": metadata["page_count"],
                    "message": "non-empty page contained no valid fundingTime",
                }
            )
            break
        if max_raw_time >= api_end_ms or len(payload) < page_limit:
            final_status = "complete"
            completion_basis = (
                "end_time_reached" if max_raw_time >= api_end_ms else "page_shorter_than_limit"
            )
            break
        next_start_ms = max_raw_time + 1
        if next_start_ms <= current_start_ms:
            final_status = "pagination_non_progress"
            metadata["status"] = "partial"
            metadata["errors"].append(
                {
                    "kind": "pagination_non_progress",
                    "page": metadata["page_count"],
                    "current_start_ms": current_start_ms,
                    "max_returned_time_ms": max_raw_time,
                }
            )
            break
        current_start_ms = next_start_ms

    if final_status is None:
        final_status = "complete"
        completion_basis = "requested_end_bound"

    merged, duplicate_count, conflicts, mark_conflicts = _merge_funding_rows(all_rows)
    metadata["duplicate_timestamp_count"] = duplicate_count
    # ``conflicts`` is calculated over all retained rows, including conflicts
    # already present in an old partial cache.
    metadata["duplicate_timestamp_conflict_count"] = len(conflicts)
    metadata["duplicate_timestamp_conflict_samples"] = conflicts[:10]
    metadata["mark_price_conflict_count"] = mark_conflicts
    metadata["mark_price_conflict_samples"] = [
        value for value in conflicts if value.get("kind") == "mark_price_conflict"
    ][:10]
    metadata["rest_final_page_status"] = final_status
    metadata["final_page_status"] = final_status
    metadata["completion_basis"] = completion_basis
    metadata["errors"] = metadata["errors"][:100]

    has_conflict = (
        metadata["duplicate_timestamp_conflict_count"] > 0
        or metadata["mark_price_conflict_count"] > 0
    )
    if has_conflict:
        metadata["final_page_status"] = "conflicting_duplicate_timestamp"
        metadata["status"] = "partial"
        metadata["coverage_status"] = "partial"
    elif final_status == "complete":
        metadata["status"] = "complete"
        metadata["coverage_status"] = "complete" if merged else "empty_range"
    elif final_status == "empty_response":
        metadata["status"] = "complete"
        metadata["coverage_status"] = "complete" if merged else "empty_range"
        metadata["completion_basis"] = "empty_terminal_page"
    else:
        metadata["status"] = "partial" if merged else "failed"
        metadata["coverage_status"] = "partial" if merged else "not_observed"
    if metadata["invalid_record_count"] and metadata["status"] == "complete":
        metadata["status"] = "partial"
        metadata["coverage_status"] = "partial"
    metadata["data_status"] = "present" if merged else (
        "absent_in_requested_window"
        if metadata["transport_status"] == "success" and metadata["status"] == "complete"
        else metadata["data_status"]
    )
    _metadata_range(metadata, merged)
    metadata["updated_at_utc"] = utc_iso(_now_utc())
    return merged, metadata


def _month_starts(start: datetime, end: datetime) -> list[date]:
    current = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    values: list[date] = []
    # Include the containing month whenever the exclusive end is even one
    # millisecond into it; this is required for the exact protocol-cutoff
    # funding event at 2026-09-01T00:00:00Z.
    include_last = end > datetime(last.year, last.month, 1, tzinfo=UTC)
    while current < last or (current == last and include_last):
        values.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return values


def _vision_month_url(symbol: str, month: date) -> str:
    return (
        f"{VISION_FUNDING_BASE}/{symbol}/{symbol}-fundingRate-"
        f"{month.year:04d}-{month.month:02d}.zip"
    )


def _verified_vision_month(
    client: Any,
    url: str,
    *,
    pacer: RequestPacer,
    sleeper: Callable[[float], None],
    max_retries: int,
    backoff_seconds: float,
    timeout: float,
) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    """Download one Vision archive only after verifying its SHA-256 checksum."""

    checksum_page = _request_bytes(
        client,
        url + ".CHECKSUM",
        pacer=pacer,
        sleeper=sleeper,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
        timeout=timeout,
    )
    if not checksum_page.ok:
        return None, {
            "url": url,
            "status": "missing" if checksum_page.status_code == 404 else "error",
            "checksum_status_code": checksum_page.status_code,
            "error": checksum_page.error,
        }
    checksum_text = checksum_page.content.decode("utf-8", errors="replace")
    match = _SHA256_RE.search(checksum_text)
    if not match:
        return None, {"url": url, "status": "error", "error": "checksum file has no SHA-256"}
    expected = match.group(0).lower()
    archive_page = _request_bytes(
        client,
        url,
        pacer=pacer,
        sleeper=sleeper,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
        timeout=timeout,
    )
    if not archive_page.ok:
        return None, {
            "url": url,
            "status": "error",
            "checksum_sha256": expected,
            "archive_status_code": archive_page.status_code,
            "error": archive_page.error,
        }
    actual = hashlib.sha256(archive_page.content).hexdigest().lower()
    if actual != expected:
        return None, {
            "url": url,
            "status": "checksum_mismatch",
            "checksum_sha256": expected,
            "archive_sha256": actual,
            "error": "archive checksum mismatch",
        }
    try:
        with zipfile.ZipFile(io.BytesIO(archive_page.content)) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not csv_names:
                raise ValueError("archive has no CSV")
            csv_bytes = archive.read(csv_names[0])
        frame = pd.read_csv(io.BytesIO(csv_bytes))
    except Exception as exc:
        return None, {
            "url": url,
            "status": "error",
            "checksum_sha256": expected,
            "archive_sha256": actual,
            "error": f"invalid archive: {type(exc).__name__}: {exc}",
        }
    return frame, {
        "url": url,
        "status": "ok",
        "checksum_sha256": expected,
        "archive_sha256": actual,
        "csv_name": csv_names[0],
        "row_count": len(frame),
    }


@dataclass
class ByteFetch:
    ok: bool
    status_code: int | None
    content: bytes = b""
    error: str | None = None


def _request_bytes(
    client: Any,
    url: str,
    *,
    pacer: RequestPacer,
    sleeper: Callable[[float], None],
    max_retries: int,
    backoff_seconds: float,
    timeout: float,
) -> ByteFetch:
    for attempt in range(max_retries + 1):
        pacer.wait()
        try:
            response = _client_get(client, url, {}, timeout)
        except Exception as exc:
            if attempt >= max_retries:
                return ByteFetch(False, None, error=f"{type(exc).__name__}: {exc}")
            sleeper(backoff_seconds * (2**attempt))
            continue
        status = int(getattr(response, "status_code", 0) or 0)
        if status == 200:
            return ByteFetch(True, status, content=bytes(getattr(response, "content", b"")))
        retry_after = _retry_after_seconds(getattr(response, "headers", {}))
        if status in {418, 429} or status >= 500:
            if attempt < max_retries:
                delay = backoff_seconds * (2**attempt)
                if retry_after is not None:
                    delay = max(delay, retry_after)
                pacer.defer_for(delay)
                continue
        if status in {418, 429}:
            pacer.defer_for(retry_after)
        return ByteFetch(False, status, error=f"HTTP {status}")
    return ByteFetch(False, None, error="request failed")


def fetch_funding_from_vision(
    symbol: str,
    start: datetime | str = DEFAULT_FUNDING_START,
    end: datetime | str = DEFAULT_FUNDING_END,
    *,
    client: Any,
    pacer: RequestPacer | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
    timeout: float = 30.0,
    snapshot: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Optional checksum-verified monthly Vision fallback."""

    canonical_symbol = str(symbol).strip().upper()
    start_dt = parse_utc(start)
    end_dt = parse_utc(end)
    start_ms = _epoch_ms(start_dt)
    end_ms = _epoch_ms(end_dt)
    limiter = pacer or RequestPacer(sleeper=sleeper)
    metadata: dict[str, Any] = {
        "source": "Binance Vision monthly archives",
        "symbol": canonical_symbol,
        "snapshot": dict(snapshot) if snapshot is not None else None,
        "requested_window": {
            "start_utc": utc_iso(start_dt),
            "end_exclusive_utc": utc_iso(end_dt),
        },
        "months": [],
        "archive_count": 0,
        "missing_month_count": 0,
        "errors": [],
        "checksum_verified": True,
        "status": "running",
    }
    all_rows: list[dict[str, Any]] = []
    for month in _month_starts(start_dt, end_dt):
        url = _vision_month_url(canonical_symbol, month)
        frame, month_meta = _verified_vision_month(
            client,
            url,
            pacer=limiter,
            sleeper=sleeper,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            timeout=timeout,
        )
        metadata["months"].append(month_meta)
        if month_meta["status"] == "missing":
            metadata["missing_month_count"] += 1
            continue
        if month_meta["status"] != "ok":
            metadata["errors"].append(month_meta)
            continue
        metadata["archive_count"] += 1
        payload = frame.to_dict(orient="records") if frame is not None else []
        page_rows, page_errors, _, out_of_window = _normalise_funding_payload(
            payload,
            canonical_symbol,
            start_ms,
            end_ms,
            source_identifier=str(month_meta.get("url") or "Binance Vision monthly archives"),
        )
        all_rows.extend(page_rows)
        metadata.setdefault("invalid_record_count", 0)
        metadata["invalid_record_count"] += len(page_errors)
        metadata.setdefault("out_of_window_count", 0)
        metadata["out_of_window_count"] += out_of_window
        metadata["errors"].extend(page_errors[:20])

    merged, duplicate_count, conflicts, mark_conflicts = _merge_funding_rows(all_rows)
    metadata["row_count"] = len(merged)
    metadata["duplicate_timestamp_count"] = duplicate_count
    metadata["duplicate_timestamp_conflict_count"] = len(conflicts)
    metadata["duplicate_timestamp_conflict_samples"] = conflicts
    metadata["mark_price_conflict_count"] = mark_conflicts
    metadata["range"] = {
        "first_funding_time_utc": None,
        "last_funding_time_utc": None,
    }
    if merged:
        _metadata_range(metadata, merged)
    if metadata["errors"]:
        metadata["status"] = "failed"
    else:
        metadata["status"] = "complete"
        metadata["data_status"] = "present" if merged else "absent_in_requested_window"
    if metadata["missing_month_count"]:
        metadata["status"] = "partial"
        metadata["coverage_status"] = "partial"
        metadata["errors"].append(
            {
                "kind": "missing_required_archive_month",
                "count": metadata["missing_month_count"],
            }
        )
    elif metadata["status"] == "complete":
        metadata["coverage_status"] = "complete" if merged else "empty_range"
    if conflicts or mark_conflicts:
        metadata["status"] = "conflict"
        metadata["coverage_status"] = "partial"
    metadata["final_page_status"] = "complete_archives" if metadata["status"] == "complete" else "archive_error"
    return merged, metadata


def _snapshot_matches(
    metadata: Mapping[str, Any] | None,
    expected_snapshot: Mapping[str, Any] | None,
) -> bool:
    if expected_snapshot is None:
        return True
    return metadata is not None and metadata.get("snapshot") == dict(expected_snapshot)


def _cache_is_complete(
    metadata: Mapping[str, Any] | None,
    start: datetime,
    end: datetime,
    *,
    parquet_path: Path | None = None,
    expected_snapshot: Mapping[str, Any] | None = None,
) -> bool:
    if not metadata or not _same_requested_window(metadata, start, end):
        return False
    # A sidecar from this preparation flow is required.  A bare 500-row file
    # has no completion evidence and must be re-queried.
    complete = bool(
        metadata.get("status") in {"complete", "reused"}
        and metadata.get("final_page_status") in {"complete", "complete_archives", "empty_response"}
        and metadata.get("coverage_status") in {"complete", "empty_range"}
        and not metadata.get("errors")
        and metadata.get("protocol") == PROTOCOL_ID
        and metadata.get("schema") == list(FUNDING_COLUMNS)
        and isinstance(metadata.get("artifact_sha256"), str)
        and _snapshot_matches(metadata, expected_snapshot)
    )
    if not complete:
        return False
    range_meta = metadata.get("range", {})
    try:
        if int(range_meta.get("row_count", -1)) < 0:
            return False
    except (TypeError, ValueError):
        return False
    if parquet_path is not None:
        if not parquet_path.exists() or sha256_file(parquet_path) != metadata.get("artifact_sha256"):
            return False
    provenance_sha = metadata.get("row_provenance_artifact_sha256")
    provenance_path = metadata.get("row_provenance_artifact_path")
    if expected_snapshot is not None and not provenance_sha:
        return False
    if provenance_sha:
        if not provenance_path:
            return False
        path = Path(str(provenance_path))
        if not path.exists() or sha256_file(path) != provenance_sha:
            return False
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if int(payload.get("row_count", -1)) != int(range_meta.get("row_count", -2)):
                return False
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return False
    return True


def _failure_group(metadata: Mapping[str, Any]) -> str | None:
    transport = metadata.get("transport_status")
    final = str(metadata.get("final_page_status") or "")
    if transport == "network_error" or final == "network_error":
        return "network"
    status_codes = {
        error.get("status_code")
        for error in metadata.get("errors", [])
        if isinstance(error, Mapping)
    }
    if 403 in status_codes or 401 in status_codes or 451 in status_codes:
        return "blocked"
    if transport == "rate_limited" or any(code in {418, 429} for code in status_codes):
        return "rate_limited"
    return None


def _blocked_metadata(
    symbol: str,
    start: datetime,
    end: datetime,
    reason: str,
    *,
    snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = _new_funding_metadata(symbol, start, end, snapshot=snapshot)
    metadata.update(
        {
            "status": "blocked",
            "transport_status": "systematic_network_block",
            "data_status": "not_observed",
            "coverage_status": "not_observed",
            "final_page_status": "systematic_network_block",
            "rest_final_page_status": "systematic_network_block",
            "errors": [{"kind": "systematic_network_block", "message": reason}],
            "updated_at_utc": utc_iso(_now_utc()),
        }
    )
    return metadata


def _refresh_funding_summary(
    manifest: dict[str, Any],
    output_dir: Path,
    *,
    requested_start: datetime,
    requested_end: datetime,
    expected_symbols: Sequence[str],
    snapshot_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    funding = manifest.setdefault("funding", {})
    symbols = funding.setdefault("symbols", {})
    expected = sorted({str(value).strip().upper() for value in expected_symbols if str(value).strip()})
    missing_symbols = [symbol for symbol in expected if symbol not in symbols]
    statuses = [symbols[symbol] for symbol in expected if symbol in symbols]
    complete_count = 0
    for symbol in expected:
        value = symbols.get(symbol)
        if not isinstance(value, Mapping):
            continue
        path = Path(output_dir) / "funding" / f"{symbol}.parquet"
        if value.get("status") in {"complete", "reused"} and _cache_is_complete(
            value,
            requested_start,
            requested_end,
            parquet_path=path,
            expected_snapshot=(snapshot_by_symbol or {}).get(symbol),
        ):
            complete_count += 1
    funding["summary"] = {
        "symbol_count": len(expected),
        "complete_count": complete_count,
        "partial_count": sum(value.get("status") == "partial" for value in statuses),
        "failed_count": sum(value.get("status") in {"failed", "blocked"} for value in statuses),
        "conflict_count": sum(value.get("status") == "conflict" for value in statuses),
        "rows": sum(int(value.get("range", {}).get("row_count", 0) or 0) for value in statuses),
        "missing_symbols": missing_symbols,
        "extra_symbol_count": max(0, len(symbols) - len(expected)),
    }


def _update_funding_manifest(
    manifest: dict[str, Any],
    output_dir: Path,
    *,
    metadata: Mapping[str, Any],
    requested_start: datetime,
    requested_end: datetime,
    network: Mapping[str, Any],
    expected_symbols: Sequence[str] | None = None,
    snapshot_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    funding = manifest.setdefault("funding", {})
    funding["status"] = "running"
    funding["requested_window"] = {
        "start_utc": utc_iso(requested_start),
        "end_exclusive_utc": utc_iso(requested_end),
    }
    funding["network"] = dict(network)
    symbols = funding.setdefault("symbols", {})
    symbols[str(metadata["symbol"])] = dict(metadata)
    _refresh_funding_summary(
        manifest,
        output_dir,
        requested_start=requested_start,
        requested_end=requested_end,
        expected_symbols=expected_symbols or list(symbols),
        snapshot_by_symbol=snapshot_by_symbol,
    )
    manifest["generated_at_utc"] = utc_iso(_now_utc())
    _atomic_json(Path(output_dir) / "manifest.json", manifest)


def _prepare_existing(
    symbol: str,
    funding_dir: Path,
    start: datetime,
    end: datetime,
    *,
    expected_snapshot: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[dict[str, Any]]]:
    parquet_path = funding_dir / f"{symbol}.parquet"
    sidecar_path = funding_dir / f"{symbol}.json"
    sidecar = _load_json(sidecar_path)
    if not parquet_path.exists():
        if sidecar is None:
            return [], None, []
        return [], sidecar, [{"kind": "missing_existing_artifact", "path": str(parquet_path)}]
    if sidecar is None:
        return [], None, [{"kind": "missing_existing_sidecar", "path": str(sidecar_path)}]

    errors: list[dict[str, Any]] = []
    if sidecar.get("protocol") != PROTOCOL_ID:
        errors.append({"kind": "incompatible_existing_protocol"})
    bounds = _requested_window_bounds(sidecar)
    target_start_ms = _epoch_ms(start)
    target_end_ms = _epoch_ms(end)
    if bounds is None or bounds[0] != target_start_ms or not (bounds[0] < bounds[1] <= target_end_ms):
        errors.append(
            {
                "kind": "incompatible_existing_window",
                "existing_window": sidecar.get("requested_window"),
                "requested_start_ms": target_start_ms,
                "requested_end_exclusive_ms": target_end_ms,
            }
        )
    if (
        expected_snapshot is not None
        and sidecar.get("snapshot") is not None
        and sidecar.get("snapshot") != dict(expected_snapshot)
    ):
        # A funding artifact is independent of the local price files, so a
        # verified prefix can be migrated explicitly to a newly frozen price
        # snapshot.  Keep the old snapshot in private in-memory state until
        # _process_symbol records the migration in durable provenance.
        sidecar["_snapshot_migration_from"] = sidecar.get("snapshot")
    expected_hash = sidecar.get("artifact_sha256")
    if not isinstance(expected_hash, str):
        errors.append({"kind": "missing_existing_artifact_sha256"})
    else:
        actual_hash = sha256_file(parquet_path)
        if actual_hash != expected_hash:
            errors.append(
                {
                    "kind": "existing_artifact_hash_mismatch",
                    "expected": expected_hash,
                    "actual": actual_hash,
                }
            )
    if errors:
        return [], sidecar, errors

    try:
        assert bounds is not None
        cache_start = datetime.fromtimestamp(bounds[0] / 1000, UTC)
        cache_end = datetime.fromtimestamp(bounds[1] / 1000, UTC)
        rows, read_errors = read_funding_cache(parquet_path, symbol, cache_start, cache_end)
        errors.extend(read_errors)
        expected_rows = sidecar.get("range", {}).get("row_count")
        if expected_rows is None or int(expected_rows) != len(rows):
            errors.append(
                {
                    "kind": "existing_row_count_mismatch",
                    "expected": expected_rows,
                    "actual": len(rows),
                }
            )
        provenance_sha = sidecar.get("row_provenance_artifact_sha256")
        provenance_path = sidecar.get("row_provenance_artifact_path")
        if provenance_sha or provenance_path:
            if not provenance_sha or not provenance_path:
                errors.append({"kind": "invalid_row_provenance_sidecar"})
            else:
                provenance_file = Path(str(provenance_path))
                if not provenance_file.exists() or sha256_file(provenance_file) != provenance_sha:
                    errors.append({"kind": "row_provenance_hash_mismatch"})
                else:
                    try:
                        with provenance_file.open("r", encoding="utf-8") as handle:
                            provenance_payload = json.load(handle)
                        if int(provenance_payload.get("row_count", -1)) != len(rows):
                            errors.append({"kind": "row_provenance_row_count_mismatch"})
                    except (OSError, TypeError, ValueError, json.JSONDecodeError):
                        errors.append({"kind": "invalid_row_provenance_sidecar"})
        if errors:
            return [], sidecar, errors
        artifact_hash = str(expected_hash)
        for row in rows:
            row_hash = _funding_row_sha256(
                symbol,
                int(row["funding_time_ms"]),
                float(row["funding_rate"]),
                row.get("mark_price"),
            )
            row["source_id"] = (
                f"legacy-cache-artifact:{artifact_hash}:{int(row['funding_time_ms'])}:"
                f"{row_hash[:16]}"
            )
            row["source_row_sha256"] = row_hash
        return rows, sidecar, []
    except Exception as exc:
        return [], sidecar, [
            {"kind": "invalid_existing_cache", "message": f"{type(exc).__name__}: {exc}"}
        ]


def _save_symbol_cache(
    symbol: str,
    funding_dir: Path,
    rows: Sequence[Mapping[str, Any]],
    metadata: dict[str, Any],
    *,
    successful_no_data: bool,
) -> None:
    parquet_path = funding_dir / f"{symbol}.parquet"
    provenance_path = funding_dir / f"{symbol}.provenance.json"
    if rows or successful_no_data:
        _atomic_parquet(parquet_path, funding_rows_frame(rows, symbol))
        metadata["artifact_path"] = str(parquet_path.resolve())
        metadata["artifact_sha256"] = sha256_file(parquet_path)
        metadata["schema"] = list(FUNDING_COLUMNS)
        provenance_rows = [
            {
                "funding_time_ms": int(row["funding_time_ms"]),
                "funding_time_utc": utc_iso(
                    datetime.fromtimestamp(int(row["funding_time_ms"]) / 1000, UTC)
                ),
                "source_id": str(row.get("source_id") or ""),
                "source_row_sha256": str(
                    row.get("source_row_sha256")
                    or _funding_row_sha256(
                        symbol,
                        int(row["funding_time_ms"]),
                        float(row["funding_rate"]),
                        row.get("mark_price"),
                    )
                ),
            }
            for row in sorted(rows, key=lambda value: (int(value["funding_time_ms"]), float(value["funding_rate"])))
        ]
        provenance_payload = {
            "format": "annual_profit_funding_row_provenance_v1",
            "protocol": PROTOCOL_ID,
            "symbol": symbol,
            "row_count": len(provenance_rows),
            "rows": provenance_rows,
        }
        _atomic_json(provenance_path, provenance_payload)
        metadata["row_provenance_artifact_path"] = str(provenance_path.resolve())
        metadata["row_provenance_artifact_sha256"] = sha256_file(provenance_path)
        metadata["row_provenance_count"] = len(provenance_rows)
        metadata["row_provenance_format"] = provenance_payload["format"]
    metadata["updated_at_utc"] = utc_iso(_now_utc())
    _atomic_json(funding_dir / f"{symbol}.json", metadata)


def _funding_snapshot_for_symbol(
    manifest: Mapping[str, Any],
    symbol: str,
) -> dict[str, Any]:
    audit_files = manifest.get("audit", {}).get("files", [])
    source_record = next(
        (
            record
            for record in audit_files
            if isinstance(record, Mapping) and str(record.get("symbol") or "").upper() == symbol
        ),
        {},
    )
    return {
        "protocol": PROTOCOL_ID,
        "protocol_document": manifest.get("protocol_document", PROTOCOL_DOCUMENT),
        "protocol_document_sha256": manifest.get("protocol_document_sha256"),
        "universe_sha256": manifest.get("universe", {}).get("sha256"),
        "source_snapshot_sha256": manifest.get("audit", {}).get("source_snapshot_sha256"),
        "source_file_name": source_record.get("file_name"),
        "source_file_sha256": source_record.get("file_sha256"),
    }


def _process_symbol(
    symbol: str,
    funding_dir: Path,
    start: datetime,
    end: datetime,
    *,
    client: Any,
    pacer: RequestPacer,
    sleeper: Callable[[float], None],
    max_retries: int,
    backoff_seconds: float,
    timeout: float,
    use_archives: bool,
    snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    existing_rows, existing_metadata, existing_read_errors = _prepare_existing(
        symbol,
        funding_dir,
        start,
        end,
        expected_snapshot=snapshot,
    )
    parquet_path = funding_dir / f"{symbol}.parquet"
    metadata_errors = [
        error
        for error in (existing_metadata or {}).get("errors", [])
        if isinstance(error, Mapping)
    ]
    only_snapshot_repair_errors = bool(metadata_errors) and all(
        error.get("kind") == "incompatible_existing_snapshot" for error in metadata_errors
    )
    snapshot_migration_from = (existing_metadata or {}).get("_snapshot_migration_from")
    final_page = str(
        (existing_metadata or {}).get("rest_final_page_status")
        or (existing_metadata or {}).get("final_page_status")
        or ""
    )
    if (
        snapshot is not None
        and existing_metadata
        and existing_rows
        and not existing_read_errors
        and _same_requested_window(existing_metadata, start, end)
        and (
            snapshot_migration_from is not None
            or only_snapshot_repair_errors
        )
        and final_page in {"complete", "empty_response", "complete_archives"}
        and int(existing_metadata.get("invalid_record_count", 0) or 0) == 0
        and int(existing_metadata.get("duplicate_timestamp_conflict_count", 0) or 0) == 0
        and int(existing_metadata.get("mark_price_conflict_count", 0) or 0) == 0
    ):
        metadata = dict(existing_metadata)
        old_snapshot = snapshot_migration_from
        if old_snapshot is not None:
            history = list(metadata.get("snapshot_history", []))
            history.append(
                {
                    "snapshot": old_snapshot,
                    "migrated_at_utc": utc_iso(_now_utc()),
                    "reason": "verified funding artifact retained across a newly frozen price snapshot",
                }
            )
            metadata["snapshot_history"] = history[-5:]
        metadata["snapshot"] = dict(snapshot)
        metadata.pop("_snapshot_migration_from", None)
        metadata["errors"] = []
        metadata["rest_errors"] = []
        metadata["status"] = "complete"
        metadata["coverage_status"] = "complete" if existing_rows else "empty_range"
        metadata["data_status"] = "present" if existing_rows else "absent_in_requested_window"
        metadata["resume_action"] = (
            "migrated_snapshot_reused"
            if old_snapshot is not None
            else "repaired_snapshot_provenance"
        )
        metadata.setdefault("provenance", {})["snapshot_migration"] = {
            "from_snapshot": old_snapshot,
            "to_snapshot": dict(snapshot),
            "verified_artifact_reused": True,
        }
        _save_symbol_cache(
            symbol,
            funding_dir,
            existing_rows,
            metadata,
            successful_no_data=not existing_rows,
        )
        return metadata
    if (
        _cache_is_complete(
            existing_metadata,
            start,
            end,
            parquet_path=parquet_path,
            expected_snapshot=snapshot,
        )
        and not existing_read_errors
    ):
        metadata = dict(existing_metadata)
        metadata["status"] = "complete"
        metadata["resume_action"] = "reused_complete_cache"
        metadata["range"] = dict(metadata.get("range", {}))
        metadata["snapshot"] = dict(snapshot) if snapshot is not None else metadata.get("snapshot")
        _save_symbol_cache(symbol, funding_dir, existing_rows, metadata, successful_no_data=not existing_rows)
        return metadata

    metadata_for_resume = (
        existing_metadata
        if existing_metadata
        and not existing_read_errors
        and _is_prefix_window(existing_metadata, start, end)
        else None
    )
    rows, metadata = fetch_funding_for_symbol(
        symbol,
        start,
        end,
        client=client,
        pacer=pacer,
        sleeper=sleeper,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
        timeout=timeout,
        existing_rows=existing_rows,
        existing_metadata=metadata_for_resume,
        snapshot=snapshot,
    )
    if existing_read_errors:
        metadata["errors"].extend(existing_read_errors)
        metadata["status"] = "partial" if rows else "failed"
        metadata["coverage_status"] = "partial" if rows else "not_observed"

    rest_failure = _failure_group(metadata)
    rest_errors = list(metadata.get("errors", []))
    metadata["rest_errors"] = rest_errors
    metadata["rest_transport_status"] = metadata.get("transport_status")
    if use_archives and rest_failure:
        archive_rows, archive_meta = fetch_funding_from_vision(
            symbol,
            start,
            end,
            client=client,
            pacer=pacer,
            sleeper=sleeper,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            timeout=max(timeout, 30.0),
            snapshot=snapshot,
        )
        combined, duplicate_count, conflicts, mark_conflicts = _merge_funding_rows(
            [*rows, *archive_rows]
        )
        rows = combined
        metadata["archive_fallback"] = archive_meta
        if (
            archive_meta.get("status") == "complete"
            and not conflicts
            and not mark_conflicts
            and not archive_meta.get("errors")
        ):
            # The REST failure remains provenance, but is not a data-quality
            # error for a complete, checksum-verified archive replacement.
            metadata["errors"] = []
            metadata["status"] = "complete"
            metadata["transport_status"] = "archive_fallback"
            metadata["coverage_status"] = "complete" if rows else "empty_range"
            metadata["data_status"] = "present" if rows else "absent_in_requested_window"
            metadata["rest_final_page_status"] = metadata.get("final_page_status")
            metadata["final_page_status"] = "complete_archives"
            metadata["completion_basis"] = "checksum_verified_monthly_archives"
        else:
            metadata["status"] = "partial" if rows else "failed"
            metadata["coverage_status"] = "partial" if rows else "not_observed"
            metadata["final_page_status"] = "archive_error"
            metadata["errors"].extend(
                {"kind": "archive_fallback", **error}
                for error in archive_meta.get("errors", [])[:20]
            )
        metadata["duplicate_timestamp_count"] = duplicate_count
        metadata["duplicate_timestamp_conflict_count"] = len(conflicts)
        metadata["duplicate_timestamp_conflict_samples"] = conflicts[:10]
        metadata["mark_price_conflict_count"] = mark_conflicts
        metadata["mark_price_conflict_samples"] = [
            value for value in conflicts if value.get("kind") == "mark_price_conflict"
        ][:10]
        _metadata_range(metadata, rows)

    successful_no_data = bool(
        metadata.get("status") in {"complete", "reused"}
        and metadata.get("coverage_status") == "empty_range"
        and not existing_read_errors
    )
    _save_symbol_cache(
        symbol,
        funding_dir,
        rows,
        metadata,
        successful_no_data=successful_no_data,
    )
    return metadata


def _process_symbol_archives_only(
    symbol: str,
    funding_dir: Path,
    start: datetime,
    end: datetime,
    *,
    client: Any,
    pacer: RequestPacer,
    sleeper: Callable[[float], None],
    max_retries: int,
    backoff_seconds: float,
    timeout: float,
    rest_block_reason: str,
    snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Use Vision after a REST probe block without issuing more REST calls."""

    existing_rows, existing_metadata, existing_read_errors = _prepare_existing(
        symbol,
        funding_dir,
        start,
        end,
        expected_snapshot=snapshot,
    )
    parquet_path = funding_dir / f"{symbol}.parquet"
    if (
        _cache_is_complete(
            existing_metadata,
            start,
            end,
            parquet_path=parquet_path,
            expected_snapshot=snapshot,
        )
        and not existing_read_errors
    ):
        metadata = dict(existing_metadata)
        metadata["status"] = "complete"
        metadata["resume_action"] = "reused_complete_cache"
        _save_symbol_cache(symbol, funding_dir, existing_rows, metadata, successful_no_data=not existing_rows)
        return metadata

    archive_rows, archive_meta = fetch_funding_from_vision(
        symbol,
        start,
        end,
        client=client,
        pacer=pacer,
        sleeper=sleeper,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
        timeout=max(timeout, 30.0),
        snapshot=snapshot,
    )
    rows, duplicate_count, conflicts, mark_conflicts = _merge_funding_rows(
        [*existing_rows, *archive_rows]
    )
    metadata = _new_funding_metadata(symbol, start, end, snapshot=snapshot)
    metadata["transport_status"] = "archive_fallback"
    metadata["rest_transport_status"] = "systematic_network_block"
    metadata["rest_final_page_status"] = "systematic_network_block"
    metadata["rest_errors"] = [
        {"kind": "systematic_network_block", "message": rest_block_reason}
    ]
    metadata["archive_fallback"] = archive_meta
    metadata["network_attempted"] = False
    metadata["duplicate_timestamp_count"] = duplicate_count
    metadata["duplicate_timestamp_conflict_count"] = len(conflicts)
    metadata["duplicate_timestamp_conflict_samples"] = conflicts[:10]
    metadata["mark_price_conflict_count"] = mark_conflicts
    _metadata_range(metadata, rows)
    if (
        archive_meta.get("status") == "complete"
        and not conflicts
        and not mark_conflicts
        and not archive_meta.get("errors")
        and not existing_read_errors
    ):
        metadata["status"] = "complete"
        metadata["coverage_status"] = "complete" if rows else "empty_range"
        metadata["data_status"] = "present" if rows else "absent_in_requested_window"
        metadata["final_page_status"] = "complete_archives"
        metadata["completion_basis"] = "checksum_verified_monthly_archives"
    else:
        metadata["status"] = "partial" if rows else "failed"
        metadata["coverage_status"] = "partial" if rows else "not_observed"
        metadata["data_status"] = "partial" if rows else "not_observed"
        metadata["final_page_status"] = "archive_error"
        metadata["errors"] = list(existing_read_errors)
        metadata["errors"].extend(
            {"kind": "archive_fallback", **error}
            for error in archive_meta.get("errors", [])[:20]
        )
    _save_symbol_cache(
        symbol,
        funding_dir,
        rows,
        metadata,
        successful_no_data=metadata.get("status") == "complete" and not rows,
    )
    return metadata


def _archive_fallback_is_usable(metadata: Mapping[str, Any]) -> bool:
    archive = metadata.get("archive_fallback")
    return bool(
        isinstance(archive, Mapping)
        and archive.get("status") == "complete"
        and not archive.get("errors")
    )


def _probe_is_systematically_blocked(results: Sequence[Mapping[str, Any]]) -> tuple[bool, str]:
    attempted = [result for result in results if result.get("network_attempted")]
    if not attempted or any(result.get("transport_status") == "success" for result in attempted):
        return False, ""
    groups = [_failure_group(result) for result in attempted]
    if not groups or any(group is None for group in groups):
        return False, ""
    if all(group in {"network", "blocked", "rate_limited"} for group in groups):
        reason = "; ".join(
            f"{result.get('symbol')}: {result.get('final_page_status')}"
            for result in attempted
        )
        return True, f"REST probe failures indicate a systematic block ({reason})"
    return False, ""


def download_funding(
    output_dir: Path,
    manifest: dict[str, Any],
    *,
    start: datetime = DEFAULT_FUNDING_START,
    end: datetime = DEFAULT_FUNDING_END,
    probe_count: int = 3,
    use_archives: bool = False,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
    timeout: float = 20.0,
    client: Any | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Populate the separate funding cache with bounded probing and resume."""

    output_dir = Path(output_dir)
    funding_dir = output_dir / "funding"
    funding_dir.mkdir(parents=True, exist_ok=True)
    symbols = load_universe_symbols(output_dir, manifest)
    if not symbols:
        manifest.setdefault("funding", {})["status"] = "no_symbols"
        _atomic_json(output_dir / "manifest.json", manifest)
        return manifest
    start_dt = parse_utc(start)
    end_dt = parse_utc(end)
    snapshot_by_symbol = {
        symbol: _funding_snapshot_for_symbol(manifest, symbol) for symbol in symbols
    }
    probe_count = max(1, min(3, int(probe_count)))
    limiter = RequestPacer(sleeper=sleeper)
    own_client = client is None
    http_client = client or httpx.Client(timeout=timeout, headers={"User-Agent": "annual-profit-data/1.0"})
    network: dict[str, Any] = {
        "endpoint": FUNDING_ENDPOINT,
        "credentials": "none",
        "aggregate_request_interval_seconds": 1.0,
        "probe_count": 0,
        "probe_symbols": [],
        "rest_available": None,
        "systematically_blocked": False,
        "blocked_reason": None,
        "archives_fallback_enabled": bool(use_archives),
    }
    previous_network = manifest.get("funding", {}).get("network", {})
    if isinstance(previous_network, Mapping) and previous_network:
        network["previous_run"] = {
            "probe_count": previous_network.get("probe_count", 0),
            "probe_symbols": list(previous_network.get("probe_symbols", [])),
            "rest_available": previous_network.get("rest_available"),
            "systematically_blocked": previous_network.get("systematically_blocked"),
            "blocked_reason": previous_network.get("blocked_reason"),
        }
    try:
        # Complete sidecars are not sent over the network; probe the first few
        # symbols still needing evidence so a stale/bare cache is not mistaken
        # for a successful connectivity probe.
        pending: list[str] = []
        for symbol in symbols:
            sidecar = _load_json(funding_dir / f"{symbol}.json")
            cache_path = funding_dir / f"{symbol}.parquet"
            if not _cache_is_complete(
                sidecar,
                start_dt,
                end_dt,
                parquet_path=cache_path,
                expected_snapshot=snapshot_by_symbol[symbol],
            ):
                pending.append(symbol)
        probe_symbols = pending[:probe_count]
        network["probe_count"] = len(probe_symbols)
        network["probe_symbols"] = probe_symbols
        probe_results: list[dict[str, Any]] = []
        for index, symbol in enumerate(probe_symbols, start=1):
            metadata = _process_symbol(
                symbol,
                funding_dir,
                start_dt,
                end_dt,
                client=http_client,
                pacer=limiter,
                sleeper=sleeper,
                max_retries=max_retries,
                backoff_seconds=backoff_seconds,
                timeout=timeout,
                use_archives=use_archives,
                snapshot=snapshot_by_symbol[symbol],
            )
            probe_results.append(metadata)
            _update_funding_manifest(
                manifest,
                output_dir,
                metadata=metadata,
                requested_start=start_dt,
                requested_end=end_dt,
                network=network,
                expected_symbols=symbols,
                snapshot_by_symbol=snapshot_by_symbol,
            )
            _progress(
                f"FUNDING probe [{index}/{len(probe_symbols)}] {symbol} "
                f"status={metadata.get('status')} pages={metadata.get('page_count', 0)} "
                f"rows={metadata.get('range', {}).get('row_count', 0)}",
            )

        systematically_blocked, reason = _probe_is_systematically_blocked(probe_results)
        if probe_results:
            network["rest_available"] = not systematically_blocked
        else:
            network["rest_available"] = "cached"
            if isinstance(previous_network, Mapping):
                network["probe_count"] = previous_network.get("probe_count", 0)
                network["probe_symbols"] = list(previous_network.get("probe_symbols", []))
            network["resumed_from_complete_cache"] = True
        network["systematically_blocked"] = systematically_blocked
        network["blocked_reason"] = reason or None
        if systematically_blocked:
            _progress(f"FUNDING REST stopped after probe: {reason}")
            archive_probe_usable = use_archives and any(
                _archive_fallback_is_usable(result) for result in probe_results
            )
            for symbol in symbols:
                if symbol in probe_symbols:
                    continue
                sidecar = _load_json(funding_dir / f"{symbol}.json")
                cache_path = funding_dir / f"{symbol}.parquet"
                if _cache_is_complete(
                    sidecar,
                    start_dt,
                    end_dt,
                    parquet_path=cache_path,
                    expected_snapshot=snapshot_by_symbol[symbol],
                ):
                    continue
                if archive_probe_usable:
                    metadata = _process_symbol_archives_only(
                        symbol,
                        funding_dir,
                        start_dt,
                        end_dt,
                        client=http_client,
                        pacer=limiter,
                        sleeper=sleeper,
                        max_retries=max_retries,
                        backoff_seconds=backoff_seconds,
                        timeout=timeout,
                        rest_block_reason=reason,
                        snapshot=snapshot_by_symbol[symbol],
                    )
                else:
                    metadata = _blocked_metadata(
                        symbol,
                        start_dt,
                        end_dt,
                        reason,
                        snapshot=snapshot_by_symbol[symbol],
                    )
                    _save_symbol_cache(symbol, funding_dir, [], metadata, successful_no_data=False)
                _update_funding_manifest(
                    manifest,
                    output_dir,
                    metadata=metadata,
                    requested_start=start_dt,
                    requested_end=end_dt,
                    network=network,
                    expected_symbols=symbols,
                    snapshot_by_symbol=snapshot_by_symbol,
                )
                _progress(f"FUNDING blocked {symbol} (no request)")
        else:
            processed = set(probe_symbols)
            for index, symbol in enumerate((value for value in symbols if value not in processed), start=1):
                metadata = _process_symbol(
                    symbol,
                    funding_dir,
                    start_dt,
                    end_dt,
                    client=http_client,
                    pacer=limiter,
                    sleeper=sleeper,
                    max_retries=max_retries,
                    backoff_seconds=backoff_seconds,
                    timeout=timeout,
                    use_archives=use_archives,
                    snapshot=snapshot_by_symbol[symbol],
                )
                _update_funding_manifest(
                    manifest,
                    output_dir,
                    metadata=metadata,
                    requested_start=start_dt,
                    requested_end=end_dt,
                    network=network,
                    expected_symbols=symbols,
                    snapshot_by_symbol=snapshot_by_symbol,
                )
                _progress(
                    f"FUNDING [{index}/{max(1, len(symbols) - len(processed))}] {symbol} "
                    f"status={metadata.get('status')} pages={metadata.get('page_count', 0)} "
                    f"rows={metadata.get('range', {}).get('row_count', 0)}",
                )

        funding_symbols = manifest.setdefault("funding", {}).setdefault("symbols", {})
        all_cached_complete = len(funding_symbols) == len(symbols) and all(
            _cache_is_complete(
                funding_symbols.get(symbol),
                start_dt,
                end_dt,
                parquet_path=funding_dir / f"{symbol}.parquet",
                expected_snapshot=snapshot_by_symbol[symbol],
            )
            for symbol in symbols
        )
        if systematically_blocked:
            final_funding_status = (
                "complete_archives" if all_cached_complete and use_archives else "blocked"
            )
        else:
            final_funding_status = "complete" if all_cached_complete else "partial"
        manifest.setdefault("funding", {})["status"] = final_funding_status
        _refresh_funding_summary(
            manifest,
            output_dir,
            requested_start=start_dt,
            requested_end=end_dt,
            expected_symbols=symbols,
            snapshot_by_symbol=snapshot_by_symbol,
        )
        manifest["funding"]["network"] = network
        manifest["generated_at_utc"] = utc_iso(_now_utc())
        _atomic_json(output_dir / "manifest.json", manifest)
        return manifest
    finally:
        if own_client:
            http_client.close()


def prepare(
    source_dir: Path = DEFAULT_KLINE_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    audit_only: bool = False,
    funding: bool = False,
    protocol_start: datetime = DEFAULT_FUNDING_START,
    protocol_end: datetime = DEFAULT_PRICE_END,
    funding_end: datetime | None = None,
    batch_size: int = 100_000,
    force_audit: bool = False,
    probe_count: int = 3,
    use_archives: bool = False,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Callable entry point used by the CLI and tests."""

    if not audit_only and not funding:
        raise ValueError("choose audit_only=True or funding=True")
    output_dir = Path(output_dir)
    _assert_audit_output_is_separate(Path(source_dir), output_dir)
    manifest = load_or_audit_universe(
        Path(source_dir),
        output_dir,
        protocol_start=parse_utc(protocol_start),
        protocol_end=parse_utc(protocol_end),
        batch_size=batch_size,
        force_audit=force_audit or audit_only,
    )
    if audit_only and not funding:
        return manifest
    price_end_dt = parse_utc(protocol_end)
    funding_end_dt = (
        parse_utc(funding_end)
        if funding_end is not None
        else _funding_end_for_price_end(price_end_dt)
    )
    return download_funding(
        output_dir,
        manifest,
        start=parse_utc(protocol_start),
        end=funding_end_dt,
        probe_count=probe_count,
        use_archives=use_archives,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
        timeout=timeout,
    )


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--audit-only", action="store_true", help="audit local 5m files and freeze universe")
    mode.add_argument("--funding", action="store_true", help="audit/reuse universe and download funding cache")
    parser.add_argument("--kline-dir", type=Path, default=DEFAULT_KLINE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--start", default=utc_iso(DEFAULT_FUNDING_START))
    parser.add_argument("--end", default=utc_iso(DEFAULT_PRICE_END))
    parser.add_argument(
        "--funding-end",
        default=None,
        help="funding cache exclusive end; defaults to --end plus 1ms for cutoff MTM",
    )
    parser.add_argument("--batch-size", type=int, default=100_000)
    parser.add_argument("--probe-count", type=int, default=3)
    parser.add_argument("--archives", action="store_true", help="enable checksum-verified Vision fallback")
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--backoff-seconds", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    manifest = prepare(
        audit_only=args.audit_only,
        funding=args.funding,
        source_dir=args.kline_dir,
        output_dir=args.output_dir,
        protocol_start=parse_utc(args.start),
        protocol_end=parse_utc(args.end),
        funding_end=parse_utc(args.funding_end) if args.funding_end else None,
        batch_size=args.batch_size,
        probe_count=args.probe_count,
        use_archives=args.archives,
        max_retries=args.max_retries,
        backoff_seconds=args.backoff_seconds,
        timeout=args.timeout,
    )
    if args.funding:
        funding = manifest.get("funding", {})
        _progress(
            "FUNDING complete status="
            f"{funding.get('status')} summary={json.dumps(funding.get('summary', {}), sort_keys=True)}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
