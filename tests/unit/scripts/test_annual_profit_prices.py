"""Focused contracts for the annual-profit price backfill helper."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "annual_profit_prices.py"
UTC = timezone.utc


def _load_helper():
    spec = importlib.util.spec_from_file_location("test_annual_profit_prices_impl", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Dataclass-free is intentional in the helper, but registering the module
    # also mirrors normal import semantics for future annotations/importers.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _kline_row(helper, timestamp: datetime, close: float = 100.0) -> list[str]:
    open_ms = helper.epoch_ms(timestamp)
    close_ms = helper.canonical_close_time_ms(open_ms)
    return [
        str(open_ms),
        "99",
        "101",
        "98",
        str(close),
        "12.5",
        str(close_ms),
        "1250",
        "42",
        "6.25",
        "625",
        "0",
    ]


def _price_frame(helper, symbol: str, times: list[datetime], values: list[float] | None = None):
    values = values or [100.0] * len(times)
    rows = []
    for timestamp, close in zip(times, values):
        open_ms = helper.epoch_ms(timestamp)
        rows.append(
            {
                "symbol": symbol,
                "open_time": timestamp,
                "close_time": datetime.fromtimestamp(
                    helper.canonical_close_time_ms(open_ms) / 1000, tz=UTC
                ),
                "open": close - 1,
                "high": close + 1,
                "low": close - 2,
                "close": close,
                "volume": 1.0,
                "quote_volume": 2.0,
                "taker_buy_volume": 0.5,
            }
        )
    return pd.DataFrame(rows)


def test_parser_accepts_header_and_no_header_rows_as_utc_ms():
    helper = _load_helper()
    symbol = "AAAUSDT"
    timestamp = datetime(2026, 8, 1, tzinfo=UTC)
    row = _kline_row(helper, timestamp)

    no_header = helper.parse_klines_csv(io.StringIO(",".join(row) + "\n"), symbol)
    assert list(no_header.columns) == [
        "symbol",
        "open_time",
        "close_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "taker_buy_volume",
    ]
    assert no_header.loc[0, "open_time"] == pd.Timestamp(timestamp)
    assert str(no_header["open_time"].dtype).endswith(", UTC]")
    assert no_header.loc[0, "close_time"] == pd.Timestamp(
        "2026-08-01T00:04:59.999Z"
    )

    header = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base_asset_volume",
        "taker_buy_quote_asset_volume",
        "ignore",
    ]
    with_header = helper.parse_klines_csv(
        io.StringIO(",".join(header) + "\n" + ",".join(row) + "\n"), symbol
    )
    assert with_header.loc[0, "volume"] == 12.5
    assert with_header.loc[0, "quote_volume"] == 1250.0
    assert with_header.loc[0, "taker_buy_volume"] == 6.25


def test_zip_parser_reads_binary_member_and_requires_canonical_close_time():
    helper = _load_helper()
    symbol = "AAAUSDT"
    row = _kline_row(helper, datetime(2026, 8, 1, tzinfo=UTC))
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("AAAUSDT-5m-2026-08.csv", ",".join(row) + "\n")
    parsed = helper.parse_binance_zip(payload.getvalue(), symbol)
    assert len(parsed) == 1
    assert parsed.loc[0, "open_time"].tzinfo is not None

    bad = row.copy()
    bad[6] = str(int(bad[6]) + 1)
    with pytest.raises(helper.PricePreparationError, match="close_time"):
        helper.parse_klines_csv(io.StringIO(",".join(bad) + "\n"), symbol)


def test_merge_collapses_identical_overlap_but_rejects_conflicting_ohlc():
    helper = _load_helper()
    symbol = "AAAUSDT"
    timestamp = datetime(2026, 8, 1, tzinfo=UTC)
    left = _price_frame(helper, symbol, [timestamp], [100.0])
    identical = _price_frame(helper, symbol, [timestamp], [100.0])
    merged = helper.merge_price_frames(left, identical, symbol)
    assert len(merged) == 1
    assert merged.loc[0, "close"] == 100.0

    conflicting = _price_frame(helper, symbol, [timestamp], [101.0])
    with pytest.raises(helper.PriceConflictError) as error:
        helper.merge_price_frames(left, conflicting, symbol)
    assert error.value.conflicts[0]["kind"] == "raw_archive_overlap_conflict"
    assert error.value.conflicts[0]["open_time"].startswith("2026-08-01")


def test_lifecycle_gap_does_not_invent_leading_or_trailing_listing_bars():
    helper = _load_helper()
    symbol = "NEWUSDT"
    start = datetime(2025, 10, 2, 12, 30, tzinfo=UTC)
    times = [start + timedelta(minutes=5 * index) for index in range(4)]
    frame = _price_frame(helper, symbol, times)
    audit = helper.audit_lifecycle(
        frame,
        symbol=symbol,
        warmup_start=datetime(2025, 8, 1, tzinfo=UTC),
        cutoff=datetime(2025, 10, 2, 13, 0, tzinfo=UTC),
    )
    assert audit["missing_bar_count"] == 0
    assert audit["gap_months"] == []
    assert audit["prelisting_bars_not_expected"] > 0
    assert audit["post_lifecycle_bars_not_expected"] > 0


def test_lifecycle_audit_classifies_internal_leading_and_trailing_gaps():
    helper = _load_helper()
    symbol = "AAAUSDT"
    warmup = datetime(2025, 8, 1, tzinfo=UTC)
    cutoff = datetime(2025, 8, 1, 0, 50, tzinfo=UTC)
    times = [
        warmup - timedelta(minutes=5),
        warmup + timedelta(minutes=5),
        warmup + timedelta(minutes=10),
        warmup + timedelta(minutes=20),
        warmup + timedelta(minutes=25),
        warmup + timedelta(minutes=30),
        warmup + timedelta(minutes=40),
        cutoff,
    ]
    audit = helper.audit_lifecycle(
        _price_frame(helper, symbol, times),
        symbol=symbol,
        warmup_start=warmup,
        cutoff=cutoff,
    )
    assert audit["missing_bar_count"] == 4
    assert audit["leading_missing_bar_count"] == 1
    assert audit["trailing_missing_bar_count"] == 1
    assert audit["internal_missing_bar_count"] == 2
    assert audit["gap_months"] == ["2025-08"]


def test_lit_reused_ticker_clips_to_documented_launch_and_revalidates_resume(tmp_path, monkeypatch):
    helper = _load_helper()
    source = tmp_path / "lake"
    output = tmp_path / "prices"
    source.mkdir()
    protocol = tmp_path / "protocol.md"
    protocol.write_text("frozen protocol", encoding="utf-8")

    warmup = datetime(2025, 12, 23, 0, 0, tzinfo=UTC)
    launch = datetime(2025, 12, 23, 17, 30, tzinfo=UTC)
    cutoff = launch + timedelta(minutes=15)
    times = [
        warmup,
        launch - timedelta(minutes=5),
        launch,
        launch + timedelta(minutes=5),
        launch + timedelta(minutes=10),
    ]
    frame = _price_frame(helper, "LITUSDT", times)
    frame.loc[:1, ["open", "high", "low", "close"]] = 0.592
    frame.loc[:1, "volume"] = 0.0
    frame.to_parquet(source / "LITUSDT.parquet", index=False)

    audit = helper.audit_lifecycle(
        frame,
        symbol="LITUSDT",
        warmup_start=warmup,
        cutoff=cutoff,
    )
    assert audit["lifecycle_start_utc"] == "2025-12-23T17:30:00.000Z"
    assert audit["missing_bar_count"] == 0
    assert audit["prelisting_bars_not_expected"] == 210
    assert audit["launch_day_prelaunch_bars_not_expected"] == 210
    assert audit["excluded_prelaunch_row_count"] == 2
    assert audit["excluded_prelaunch_rows_in_requested_range"] == 2

    class NoArchiveCalls:
        def fetch_month(self, *_args, **_kwargs):
            raise AssertionError("the contiguous post-launch fixture needs no archive")

    read_calls = []
    original_reader = helper.read_local_price_file

    def tracked_reader(path, symbol):
        read_calls.append((path, symbol))
        return original_reader(path, symbol)

    monkeypatch.setattr(helper, "read_local_price_file", tracked_reader)
    first = helper.prepare_prices(
        source_dir=source,
        output_root=output,
        protocol_path=protocol,
        warmup_start=warmup,
        window_start=warmup + timedelta(minutes=5),
        cutoff=cutoff,
        use_rest_fallback=False,
        archive_client=NoArchiveCalls(),
    )
    entry = first["symbols"]["LITUSDT"]
    price_path = output / "klines" / "5m" / "LITUSDT.parquet"
    sidecar_path = output / "lifecycle" / "LITUSDT.json"
    output_frame = pd.read_parquet(price_path)
    assert first["status"] == "complete"
    assert entry["status"] == "ready"
    assert len(output_frame) == 3
    assert output_frame["open_time"].min() == pd.Timestamp(launch)
    assert entry["lifecycle"]["excluded_prelaunch_row_count"] == 2
    assert entry["lifecycle"]["excluded_stale_flat_zero_volume_row_count"] == 2
    assert entry["lifecycle"]["launch_day_prelaunch_bars_not_expected"] == 210
    assert entry["lifecycle"]["output_first_time_matches_launch"] is True
    assert entry["lifecycle"]["minimum_contiguous_closes"] == 289
    assert entry["lifecycle"]["cross_contract_rolling"] is False
    assert sidecar_path.exists()
    assert json.loads(sidecar_path.read_text(encoding="utf-8"))["launch_time_utc"] == (
        "2025-12-23T17:30:00Z"
    )

    read_calls.clear()
    second = helper.prepare_prices(
        source_dir=source,
        output_root=output,
        protocol_path=protocol,
        warmup_start=warmup,
        window_start=warmup + timedelta(minutes=5),
        cutoff=cutoff,
        use_rest_fallback=False,
        archive_client=NoArchiveCalls(),
    )
    assert second["status"] == "complete"
    assert read_calls == []

    manifest_path = output / "price_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["symbols"]["LITUSDT"]["lifecycle_policy_id"] = "stale_policy"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    third = helper.prepare_prices(
        source_dir=source,
        output_root=output,
        protocol_path=protocol,
        warmup_start=warmup,
        window_start=warmup + timedelta(minutes=5),
        cutoff=cutoff,
        use_rest_fallback=False,
        archive_client=NoArchiveCalls(),
    )
    assert third["status"] == "complete"
    assert len(read_calls) == 1
    assert third["symbols"]["LITUSDT"]["lifecycle_policy_id"] == (
        "lit_current_underlying_launch_binance_v1"
    )


def test_checksum_parser_and_verifier_reject_wrong_archive():
    helper = _load_helper()
    payload = b"archive bytes"
    digest = hashlib.sha256(payload).hexdigest()
    text = f"{digest}  AAAUSDT-5m-2026-08.zip\n"
    assert helper.parse_checksum(text, "AAAUSDT-5m-2026-08.zip") == digest
    assert helper.verify_checksum(payload, digest) == digest
    with pytest.raises(helper.ChecksumError):
        helper.verify_checksum(payload, "0" * 64)
    with pytest.raises(helper.ChecksumError):
        helper.parse_checksum("not-a-checksum")


def test_prepare_resume_uses_frozen_source_and_skips_ready_file(tmp_path):
    helper = _load_helper()
    source = tmp_path / "lake"
    output = tmp_path / "prices"
    source.mkdir()
    protocol = tmp_path / "protocol.md"
    protocol.write_text("frozen protocol", encoding="utf-8")
    symbol = "AAAUSDT"
    start = datetime(2025, 8, 1, tzinfo=UTC)
    times = [start + timedelta(minutes=5 * index) for index in range(5)]
    _price_frame(helper, symbol, times).to_parquet(source / f"{symbol}.parquet", index=False)

    class NoArchiveCalls:
        def fetch_month(self, *_args, **_kwargs):
            raise AssertionError("complete source must not download an archive")

    first = helper.prepare_prices(
        source_dir=source,
        output_root=output,
        protocol_path=protocol,
        warmup_start=start,
        window_start=start + timedelta(minutes=5),
        cutoff=start + timedelta(minutes=25),
        use_rest_fallback=False,
        archive_client=NoArchiveCalls(),
    )
    assert first["status"] == "complete"
    price_path = output / "klines" / "5m" / f"{symbol}.parquet"
    assert price_path.exists()
    manifest_before = (output / "price_manifest.json").read_bytes()

    second = helper.prepare_prices(
        source_dir=source,
        output_root=output,
        protocol_path=protocol,
        warmup_start=start,
        window_start=start + timedelta(minutes=5),
        cutoff=start + timedelta(minutes=25),
        use_rest_fallback=False,
        archive_client=NoArchiveCalls(),
    )
    assert second["status"] == "complete"
    assert second["summary"]["ready_symbol_count"] == 1
    assert price_path.exists()
    assert (output / "price_manifest.json").read_bytes() != manifest_before
    assert not list((output / "klines" / "5m").glob("*.tmp"))


def test_prepare_publishes_partial_cache_but_marks_unresolved_gap(tmp_path):
    helper = _load_helper()
    source = tmp_path / "lake"
    output = tmp_path / "prices"
    source.mkdir()
    protocol = tmp_path / "protocol.md"
    protocol.write_text("frozen protocol", encoding="utf-8")
    symbol = "AAAUSDT"
    start = datetime(2025, 8, 1, tzinfo=UTC)
    times = [start, start + timedelta(minutes=10)]
    _price_frame(helper, symbol, times).to_parquet(source / f"{symbol}.parquet", index=False)

    class EmptyArchive:
        def fetch_month(self, *_args, **_kwargs):
            return pd.DataFrame(columns=helper.CANONICAL_COLUMNS), {
                "symbol": symbol,
                "month": "2025-08",
                "method": "test_archive",
                "status": "ok",
            }

    result = helper.prepare_prices(
        source_dir=source,
        output_root=output,
        protocol_path=protocol,
        warmup_start=start,
        window_start=start + timedelta(minutes=5),
        cutoff=start + timedelta(minutes=15),
        use_rest_fallback=False,
        archive_client=EmptyArchive(),
    )
    entry = result["symbols"][symbol]
    assert result["status"] == "incomplete"
    assert entry["status"] == "incomplete"
    assert entry["coverage"]["missing_actual_bars_remaining"] == 1
    assert entry["output_path"]
    assert Path(entry["output_path"]).exists()
    assert len(pd.read_parquet(entry["output_path"])) == 2


def test_rest_fallback_paginates_fixed_end_with_global_pacer():
    helper = _load_helper()
    symbol = "AAAUSDT"
    start = datetime(2026, 8, 1, tzinfo=UTC)
    end = start + timedelta(minutes=15)

    class Response:
        status_code = 200
        headers: dict[str, str] = {}

        def __init__(self, payload):
            self.payload = payload
            self.content = b"[]"

        def json(self):
            return self.payload

    class Client:
        def __init__(self):
            self.responses = [
                Response([
                    _kline_row(helper, start),
                    _kline_row(helper, start + timedelta(minutes=5)),
                ]),
                Response([_kline_row(helper, start + timedelta(minutes=10))]),
            ]
            self.calls = []

        def get(self, _url, params=None, **_kwargs):
            self.calls.append(dict(params or {}))
            return self.responses.pop(0)

    client = Client()
    rest = helper.BinanceRestClient(
        client=client,
        max_retries=0,
        pacer=helper.RatePacer(interval_seconds=0, sleeper=lambda _seconds: None),
    )
    frame, record = rest.fetch_range(
        symbol,
        helper.epoch_ms(start),
        helper.epoch_ms(end),
        requested_month="2026-08",
    )
    assert len(frame) == 3
    assert record["page_count"] == 2
    assert client.calls[0]["endTime"] == helper.epoch_ms(end) - 1
    assert client.calls[1]["endTime"] == client.calls[0]["endTime"]
    assert client.calls[1]["startTime"] == helper.epoch_ms(start + timedelta(minutes=10))
    assert client.calls[0]["limit"] == 1000
