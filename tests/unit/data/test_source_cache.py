from decimal import Decimal

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from dao_vang.data.source_cache import materialize_source


def write(path, value, available=1):
    pq.write_table(pa.Table.from_pylist([dict(symbol="BTCUSDT", close_time=1,
        available_time=available, close=value)]), path)


def test_incremental_replacement_expiration_and_restart(tmp_path):
    p1, p2 = tmp_path / "one.parquet", tmp_path / "two.parquet"
    write(p1, 1)
    pattern = [str(tmp_path / "*.parquet")]
    dbpath = str(tmp_path / "test.duckdb")
    with duckdb.connect(dbpath) as conn:
        materialize_source(conn, "kline", pattern, "close_time")
        assert conn.execute("SELECT close FROM kline").fetchone() == (1,)
    write(p2, 2, 2)
    with duckdb.connect(dbpath) as conn:
        materialize_source(conn, "kline", pattern, "close_time")
        assert conn.execute("SELECT close FROM kline").fetchone() == (2,)
        # No-change cycles do not duplicate the source.
        materialize_source(conn, "kline", pattern, "close_time")
        assert conn.execute("SELECT count(*) FROM _source_kline").fetchone() == (2,)
        write(p2, 3, 3)
        materialize_source(conn, "kline", pattern, "close_time")
        assert conn.execute("SELECT close FROM kline").fetchone() == (3,)
        p2.unlink()
        materialize_source(conn, "kline", pattern, "close_time")
        assert conn.execute("SELECT close FROM kline").fetchone() == (1,)
        p2.write_text("corrupt parquet")
        with pytest.raises(duckdb.Error):
            materialize_source(conn, "kline", pattern, "close_time")
        assert conn.execute("SELECT close FROM kline").fetchone() == (1,)
        assert conn.execute("SELECT count(*) FROM _source_kline_files").fetchone() == (1,)


def test_decimal_precision_and_nullable_schema_evolve_losslessly(tmp_path):
    def decimal_file(name, amount, optional):
        pq.write_table(pa.Table.from_pylist([dict(symbol=name, close_time=1,
            available_time=1, volume=Decimal(amount), optional=optional)]), tmp_path / f"{name}.parquet")
    pattern = [str(tmp_path / "*.parquet")]
    with duckdb.connect() as conn:
        decimal_file("small", "1.000", None)
        materialize_source(conn, "kline", pattern, "close_time")
        decimal_file("big", "1341096435.12345678", "now-present")
        materialize_source(conn, "kline", pattern, "close_time")
        assert conn.execute("SELECT volume, optional FROM kline WHERE symbol='big'").fetchone() == (
            Decimal("1341096435.12345678"), "now-present")


def test_interrupted_warmup_resumes_without_publishing_partial_source(tmp_path):
    for i in range(257):
        write(tmp_path / f"{i:04}.parquet", i, i + 1)
    dbpath = str(tmp_path / "warmup.duckdb")
    with duckdb.connect(dbpath) as conn:
        conn.execute("CREATE TABLE kline AS SELECT 'OLD' AS symbol")
        class Interrupted:
            def __getattr__(self, name):
                return getattr(conn, name)
            def execute(self, sql, *args):
                if sql.startswith("INSERT INTO _source_kline BY NAME"):
                    raise RuntimeError("simulated interruption")
                return conn.execute(sql, *args)
        with pytest.raises(RuntimeError, match="interruption"):
            materialize_source(Interrupted(), "kline", [str(tmp_path / "*.parquet")], "close_time")
        assert conn.execute("SELECT * FROM kline").fetchone() == ("OLD",)
        assert conn.execute("SELECT count(*) FROM _source_kline_files").fetchone() == (256,)
    with duckdb.connect(dbpath) as conn:
        materialize_source(conn, "kline", [str(tmp_path / "*.parquet")], "close_time")
        assert conn.execute("SELECT close FROM kline").fetchone() == (256,)
        assert conn.execute("SELECT count(*) FROM _source_kline").fetchone() == (257,)
