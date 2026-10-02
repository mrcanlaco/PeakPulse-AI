"""Transactional incremental Parquet cache for the scanner's rolling sources.

The archive remains authoritative. File identity is tracked with each row so
expired partitions and replaced files disappear without retaining stale rows.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import duckdb

from dao_vang.logging import get_logger

logger = get_logger(__name__)


def materialize_source(conn, name: str, patterns: list[str], time_col: str) -> None:
    started = time.monotonic()
    # All identifiers originate from the fixed mapping in pipeline.py.
    cache = f"_source_{name}"
    manifest = f"_source_{name}_files"
    files: dict[str, tuple[int, int]] = {}
    for pattern in patterns:
        if "**" in pattern:
            candidates = Path(pattern.split("**")[0]).rglob("*.parquet")
            for path in candidates:
                stat = path.stat()
                files[path.as_posix()] = (stat.st_size, stat.st_mtime_ns)
        else:
            with os.scandir(Path(pattern).parent) as entries:
                for entry in entries:
                    if entry.name.endswith(".parquet") and not entry.name.startswith("."):
                        stat = entry.stat()
                        files[Path(entry.path).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    if not files:
        raise ValueError(f"No source files for {name}")
    conn.execute(f"CREATE TABLE IF NOT EXISTS {manifest} (path VARCHAR PRIMARY KEY, size BIGINT, mtime BIGINT)")
    previous = {row[0]: (row[1], row[2]) for row in conn.execute(f"SELECT * FROM {manifest}").fetchall()}
    changed = [path for path, identity in files.items() if previous.get(path) != identity]
    changed_set = set(changed)
    removed = [path for path in previous if path not in files or path in changed_set]
    logger.info("source_cache_start", source=name, total_files=len(files), new_files=len(changed), expired_files=len(removed))
    conn.begin()
    try:
        if removed:
            conn.execute(f"DELETE FROM {cache} WHERE _pipeline_file IN (SELECT unnest(?))", [removed])
            conn.execute(f"DELETE FROM {manifest} WHERE path IN (SELECT unnest(?))", [removed])
        # Bounded batches avoid opening hundreds of thousands of tiny Parquet
        # readers simultaneously (the former 19-minute live-cycle bottleneck).
        exists = bool(conn.execute("SELECT 1 FROM duckdb_tables() WHERE table_name=?", [cache]).fetchone())
        for offset in range(0, len(changed), 256):
            batch = changed[offset:offset + 256]
            query = "SELECT * FROM read_parquet(?, union_by_name=true, filename='_pipeline_file')"
            if not exists:
                conn.execute(f"CREATE TABLE {cache} AS {query}", [batch])
                exists = True
            else:
                # Decimal precision and nullable columns vary between Parquet
                # files. Preserve the same lossless union schema as a full
                # lake read instead of freezing the first batch's narrow type.
                current = {row[0]: row[1] for row in conn.execute(f"DESCRIBE {cache}").fetchall()}
                unified = conn.execute(
                    f"DESCRIBE SELECT * FROM {cache} UNION ALL BY NAME {query}", [batch]
                ).fetchall()
                for column, sql_type, *_ in unified:
                    quoted = '"' + column.replace('"', '""') + '"'
                    if column not in current:
                        conn.execute(f"ALTER TABLE {cache} ADD COLUMN {quoted} {sql_type}")
                    elif current[column] != sql_type:
                        conn.execute(f"ALTER TABLE {cache} ALTER COLUMN {quoted} TYPE {sql_type}")
                conn.execute(f"INSERT INTO {cache} BY NAME {query}", [batch])
            conn.executemany(f"INSERT INTO {manifest} VALUES (?, ?, ?)", [(p, *files[p]) for p in batch])
            # Commit file rows and their manifest together in bounded batches.
            # One transaction for the entire archive retains all undo/version
            # buffers and can exhaust the production 2GB DuckDB limit. The
            # public source table is replaced only after every batch succeeds;
            # an interrupted warm-up resumes from the last committed batch.
            conn.commit()
            conn.begin()
        kind = conn.execute("SELECT table_type FROM information_schema.tables WHERE table_name=?", [name]).fetchone()
        if kind and kind[0] == "VIEW":
            conn.execute(f"DROP VIEW {name}")
        conn.execute(f"""CREATE OR REPLACE TABLE {name} AS
            SELECT * EXCLUDE (_pipeline_file) FROM {cache}
            QUALIFY row_number() OVER (
                PARTITION BY symbol, {time_col}
                ORDER BY available_time DESC, _pipeline_file DESC
            ) = 1""")
        conn.commit()
        logger.info("source_cache_done", source=name, elapsed_s=round(time.monotonic() - started, 3))
    except BaseException:
        try:
            conn.rollback()
        except duckdb.Error:
            pass
        raise
