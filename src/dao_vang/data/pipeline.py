import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from dao_vang.config.settings import AppSettings
from dao_vang.data.normalization.normalizers import (
    normalize_funding,
    normalize_global_ratio,
    normalize_kline,
    normalize_open_interest,
    normalize_taker_volume,
    normalize_top_position_ratio,
    normalize_top_ratio,
)
from dao_vang.data.quality import compute_data_quality
from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.data.storage.parquet import write_normalized_to_parquet
from dao_vang.data.timeline import align_exact_5m, align_funding_asof

logger = logging.getLogger(__name__)

# Timestamp field/extraction per data type for incremental download
_TIMESTAMP_SPECS: Dict[str, Any] = {
    "klines": {"field": None, "index": 6},  # close_time at index 6 in kline list
    "funding": {"field": "fundingTime"},
    "open_interest": {"field": "timestamp"},
    "taker_ratio": {"field": "timestamp"},
    "global_ratio": {"field": "timestamp"},
    "top_ratio": {"field": "timestamp"},
    "top_position_ratio": {"field": "timestamp"},
}

_LATEST_INDEX_NAME = ".latest_timestamps.json"
_LATEST_INDEX_LOCK = threading.Lock()
_LATEST_INDEX_CACHE: Dict[str, Dict[str, int]] = {}


def _latest_index_key(data_dir: Path) -> str:
    return str(data_dir.resolve())


def _timestamp_from_envelope(
    envelope: dict[str, Any], spec: dict[str, Any]
) -> tuple[str, int] | None:
    request_params = json.loads(envelope.get("request_params_json", "{}"))
    symbol = str(request_params.get("symbol", ""))
    if not symbol:
        return None
    payload = json.loads(envelope.get("payload_json", "null"))
    if not isinstance(payload, list) or not payload:
        return None
    last_item = payload[-1]
    if spec["field"] is None:
        timestamp = int(last_item[spec["index"]])
    else:
        timestamp = int(last_item[spec["field"]])
    return symbol, timestamp


def _write_latest_index(data_dir: Path, index: Dict[str, int]) -> None:
    index_path = data_dir / "raw" / _LATEST_INDEX_NAME
    index_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = index_path.with_name(f".{index_path.name}.tmp")
    temporary.write_text(
        json.dumps(index, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, index_path)


def _build_latest_index(data_dir: Path) -> Dict[str, int]:
    """Build the raw timestamp index once instead of rescanning per symbol."""

    latest: Dict[str, int] = {}
    raw_dir = data_dir / "raw"
    if not raw_dir.exists():
        return latest

    for data_type, spec in _TIMESTAMP_SPECS.items():
        dtype_dir = raw_dir / data_type
        if not dtype_dir.exists():
            continue
        for jsonl_file in dtype_dir.rglob("*.jsonl"):
            try:
                with jsonl_file.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        if not line.strip():
                            continue
                        parsed = _timestamp_from_envelope(json.loads(line), spec)
                        if parsed is None:
                            continue
                        symbol, timestamp = parsed
                        key = f"{data_type}:{symbol}"
                        latest[key] = max(timestamp, latest.get(key, 0))
            except (OSError, json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError):
                continue
    return latest


def _get_latest_index(data_dir: Path) -> Dict[str, int]:
    key = _latest_index_key(data_dir)
    with _LATEST_INDEX_LOCK:
        cached = _LATEST_INDEX_CACHE.get(key)
        if cached is not None:
            return cached

        index_path = data_dir / "raw" / _LATEST_INDEX_NAME
        loaded: Dict[str, int] = {}
        try:
            raw = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                loaded = {
                    str(item_key): int(item_value)
                    for item_key, item_value in raw.items()
                    if int(item_value) > 0
                }
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            loaded = _build_latest_index(data_dir)

        _LATEST_INDEX_CACHE[key] = loaded
        if loaded and not index_path.exists():
            try:
                _write_latest_index(data_dir, loaded)
            except OSError:
                pass
        return loaded


def get_latest_data_timestamp(
    data_dir: Path, data_type: str, symbol: str
) -> Optional[datetime]:
    """
    Scan existing raw JSONL files for the given data_type and symbol,
    and return the latest data timestamp (UTC).

    Returns None if no matching data is found.
    """
    spec = _TIMESTAMP_SPECS.get(data_type)
    if spec is None:
        return None

    latest_ts_ms = _get_latest_index(data_dir).get(f"{data_type}:{symbol}", 0)

    if latest_ts_ms > 0:
        return datetime.fromtimestamp(latest_ts_ms / 1000.0, tz=timezone.utc)
    return None


def get_incremental_start(
    data_dir: Path, data_type: str, symbol: str, requested_start: datetime
) -> datetime:
    """
    Return the effective start time for incremental collection.
    If existing data covers up to a later timestamp, start from there (+1ms).
    Otherwise, start from the requested_start.
    """
    latest = get_latest_data_timestamp(data_dir, data_type, symbol)
    if latest is not None and latest >= requested_start:
        return latest + timedelta(milliseconds=1)
    return requested_start


def scan_downloaded_data(data_dir: Path) -> Dict[str, Dict[str, Any]]:
    """
    Scan all raw JSONL files and return a summary of downloaded data
    organized by symbol and data_type.

    Returns:
        {
            "BTCUSDT": {
                "klines": {"rows": 12345, "files": 5, "first_date": "2026-07-01", "last_date": "2026-07-31"},
                "funding": {...},
                ...
            },
            ...
        }
    """
    raw_dir = data_dir / "raw"
    if not raw_dir.exists():
        return {}

    result: Dict[str, Dict[str, Any]] = {}

    for data_type, spec in _TIMESTAMP_SPECS.items():
        dtype_dir = raw_dir / data_type
        if not dtype_dir.exists():
            continue

        for jsonl in sorted(dtype_dir.rglob("*.jsonl")):
            date_str = jsonl.parent.name.replace("date=", "")
            try:
                with open(jsonl, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        envelope = json.loads(line)
                        req = json.loads(envelope.get("request_params_json", "{}"))
                        sym = req.get("symbol", "")
                        if not sym:
                            continue

                        if sym not in result:
                            result[sym] = {}
                        if data_type not in result[sym]:
                            result[sym][data_type] = {
                                "rows": 0,
                                "files": set(),
                                "first_date": date_str,
                                "last_date": date_str,
                            }

                        entry = result[sym][data_type]
                        entry["files"].add(jsonl.name)
                        if date_str < entry["first_date"]:
                            entry["first_date"] = date_str
                        if date_str > entry["last_date"]:
                            entry["last_date"] = date_str

                        payload = json.loads(envelope["payload_json"])
                        if isinstance(payload, list):
                            entry["rows"] += len(payload)
            except (json.JSONDecodeError, KeyError, IndexError, ValueError):
                continue

    # Convert file sets to counts
    for sym in result:
        for dt in result[sym]:
            result[sym][dt]["files"] = len(result[sym][dt]["files"])

    return result


# Map collector types to their normalization functions
NORMALIZER_MAP: Dict[str, Callable[[Dict[str, Any], str], list[Any]]] = {
    "klines": normalize_kline,
    "funding": normalize_funding,
    "open_interest": normalize_open_interest,
    "taker_ratio": normalize_taker_volume,
    "global_ratio": normalize_global_ratio,
    "top_ratio": normalize_top_ratio,
    "top_position_ratio": normalize_top_position_ratio,
}


def process_raw_to_parquet(settings: AppSettings, dataset_version: str = "1.0.0") -> int:
    """
    Reads raw JSONL files from all collectors, normalizes them, and writes to Parquet.
    """
    raw_dir = settings.paths.data_dir / "raw"
    normalized_dir = settings.paths.data_dir / "normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)

    latest_index = _get_latest_index(settings.paths.data_dir)
    index_dirty = False
    created_files = 0
    normalized_names: dict[Path, set[str]] = {}

    for collector_type, normalizer_func in NORMALIZER_MAP.items():
        collector_raw_dir = raw_dir / collector_type
        if not collector_raw_dir.exists():
            continue

        for jsonl_file in collector_raw_dir.rglob("*.jsonl"):
            # We construct a matching parquet file name
            # Incorporate parent directory name (e.g. date=2026-08-01) to avoid conflicts if same run_id across dates
            date_dir = jsonl_file.parent.name
            target_dir = normalized_dir / collector_type / date_dir
            if target_dir not in normalized_names:
                target_dir.mkdir(parents=True, exist_ok=True)
                with os.scandir(target_dir) as entries:
                    normalized_names[target_dir] = {entry.name for entry in entries}
            
            parquet_file = target_dir / f"{jsonl_file.stem}.parquet"
            if parquet_file.name in normalized_names[target_dir]:
                # Skip already processed
                continue

            normalized_items = []
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    envelope = json.loads(line)
                    items = normalizer_func(envelope, dataset_version)
                    normalized_items.extend(items)

            if normalized_items:
                write_normalized_to_parquet(parquet_file, normalized_items)
                normalized_names[target_dir].add(parquet_file.name)
                created_files += 1

            spec = _TIMESTAMP_SPECS.get(collector_type)
            if spec is not None:
                try:
                    with jsonl_file.open("r", encoding="utf-8") as handle:
                        for line in handle:
                            if not line.strip():
                                continue
                            parsed = _timestamp_from_envelope(json.loads(line), spec)
                            if parsed is None:
                                continue
                            symbol, timestamp = parsed
                            key = f"{collector_type}:{symbol}"
                            if timestamp > latest_index.get(key, 0):
                                latest_index[key] = timestamp
                                index_dirty = True
                except (OSError, json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError):
                    pass

    if index_dirty:
        with _LATEST_INDEX_LOCK:
            _LATEST_INDEX_CACHE[_latest_index_key(settings.paths.data_dir)] = latest_index
            try:
                _write_latest_index(settings.paths.data_dir, latest_index)
            except OSError:
                logger.warning("latest_timestamp_index_write_failed")

    return created_files


def _get_recent_parquet_patterns(normalized_dir: Path, subdir: str, days: int = 3) -> list[str]:
    """Return parquet glob patterns restricted to the recent N days to prevent full-disk I/O scans."""
    now_utc = datetime.now(timezone.utc)
    date_patterns = []
    for i in range(days):
        d_str = (now_utc - timedelta(days=i)).strftime("%Y-%m-%d")
        d_path = normalized_dir / subdir / f"date={d_str}"
        if d_path.exists():
            date_patterns.append(str(d_path / "*.parquet").replace("\\", "/"))
    # Fallback to general subdir glob if no dated directories found
    if not date_patterns:
        sub_path = normalized_dir / subdir
        if sub_path.exists():
            date_patterns.append(str(sub_path / "**/*.parquet").replace("\\", "/"))
    return date_patterns


def build_raw_timeline(db: DuckDBQueryLayer, settings: AppSettings, *, materialize_sources: bool = False):
    """
    Mounts parquet files into DuckDB views and stitches them into the raw_timeline.
    Restricted to a recent 3-day rolling window to bound query I/O.
    """
    normalized_dir = settings.paths.data_dir / "normalized"

    # Map duckdb view names to (subdir, time_col) for deduplication
    views = {
        "kline": ("klines", "close_time"),
        "open_interest": ("open_interest", "period_end"),
        "taker_volume": ("taker_ratio", "period_end"),
        "global_ratio": ("global_ratio", "period_end"),
        "top_ratio": ("top_ratio", "period_end"),
        "top_position_ratio": ("top_position_ratio", "period_end"),
        "funding": ("funding", "event_time"),
    }

    lookbacks = {
        "klines": 3,
        "funding": 30,
        "open_interest": 7,
        "taker_ratio": 7,
        "global_ratio": 7,
        "top_ratio": 7,
        "top_position_ratio": 7,
    }

    # Create base views over parquet files with rolling window
    for view_name, (subdir, time_col) in views.items():
        days = lookbacks.get(subdir, 3)
        patterns = _get_recent_parquet_patterns(normalized_dir, subdir, days=days)
        patterns_sql = ", ".join(f"'{p}'" for p in patterns)
        
        has_files = any(next(Path(p.replace("*.parquet", "")).glob("*.parquet"), None) is not None for p in patterns)
        if not has_files:
            has_files = next((normalized_dir / subdir).rglob("*.parquet"), None) is not None
            if has_files:
                patterns = [str(normalized_dir / subdir / '**/*.parquet').replace(chr(92), '/')]
                patterns_sql = f"'{patterns[0]}'"

        if has_files:
            if materialize_sources:
                from dao_vang.data.source_cache import materialize_source

                materialize_source(db.conn, view_name, patterns, time_col)
                continue
            for kind in ("VIEW", "TABLE"):
                try:
                    db.conn.execute(f"DROP {kind} {view_name}")
                except Exception:
                    pass

            # Scanner queries each source many times (alignment, scoring,
            # telemetry). Materialize the SAME deduped rows once per cycle
            # instead of re-reading/re-ranking the Parquet lake each time.
            relation_kind = "TABLE" if materialize_sources else "VIEW"
            db.conn.execute(f"""
                CREATE OR REPLACE {relation_kind} {view_name} AS
                SELECT * FROM read_parquet([{patterns_sql}], union_by_name=true)
                QUALIFY row_number() OVER (PARTITION BY symbol, {time_col} ORDER BY available_time DESC) = 1
            """)
        else:
            logger.warning(f"No parquet files found for {view_name} at {patterns_sql}")

    # Build the intermediate exact 5m alignment
    position_view = "top_position_ratio" if next(
        (normalized_dir / "top_position_ratio").rglob("*.parquet"), None
    ) is not None else None
    align_exact_5m(
        db,
        output_view="aligned_5m",
        top_position_view=position_view,
    )

    # Build the final raw_timeline by adding funding asof
    align_funding_asof(db, output_view="raw_timeline_pre_quality", aligned_view="aligned_5m")

    # Compute data quality
    compute_data_quality(
        db,
        input_view="raw_timeline_pre_quality",
        output_table="raw_timeline",
    )
