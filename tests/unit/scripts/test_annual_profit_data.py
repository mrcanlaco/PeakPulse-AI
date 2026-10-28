"""Contract tests for the annual-profit data preparation helper."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "annual_profit_data.py"
UTC = timezone.utc


def _load_helper():
    spec = importlib.util.spec_from_file_location("test_annual_profit_data_impl", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, status_code: int, payload: Any = None, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.content = b""

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url, params=None, **_kwargs):
        self.calls.append((url, dict(params or {})))
        response = self.responses.pop(0)
        if callable(response):
            return response(url, params or {})
        return response


def _funding_row(helper, timestamp: datetime, rate: float = 0.001):
    return {
        "symbol": "AAAUSDT",
        "funding_time_ms": int(timestamp.timestamp() * 1000),
        "funding_rate": rate,
        "mark_price": 100.0,
    }


def test_parse_utc_rejects_naive_and_normalises_offsets():
    helper = _load_helper()

    assert helper.utc_iso("2026-09-01T07:00:00+07:00") == "2026-09-01T00:00:00.000Z"
    with pytest.raises(ValueError, match="timezone-aware"):
        helper.parse_utc("2026-09-01T00:00:00")


def test_audit_streams_row_groups_and_counts_quality_issues(tmp_path):
    helper = _load_helper()
    path = tmp_path / "AAAUSDT.parquet"
    start = datetime(2025, 8, 1, tzinfo=UTC)
    frame = pd.DataFrame(
        {
            "symbol": ["AAAUSDT"] * 5,
            "open_time": [
                start,
                start + timedelta(minutes=5),
                start + timedelta(minutes=15),
                start + timedelta(minutes=15),
                start + timedelta(minutes=20),
            ],
            "close_time": [
                start + timedelta(minutes=5) - timedelta(milliseconds=1),
                start + timedelta(minutes=10) - timedelta(milliseconds=1),
                start + timedelta(minutes=20) - timedelta(milliseconds=1),
                start + timedelta(minutes=20) - timedelta(milliseconds=1),
                start + timedelta(minutes=25) - timedelta(milliseconds=1),
            ],
            "open": [100, 101, 102, 102, 104],
                "high": [101, 102, 103, 103, 105],
            "low": [99, 100, 101, 101, 103],
            "close": [100, 101, 102, 102, 104],
        }
    )
    frame.loc[4, "high"] = 102
    frame.to_parquet(path, index=False, row_group_size=2)

    result = helper.audit_kline_file(path, batch_size=2)

    assert result["status"] == "ok"
    assert result["row_count"] == 5
    assert result["gap_count"] == 1
    assert result["missing_bar_count"] == 1
    assert result["duplicate_open_time_count"] == 1
    assert result["duplicate_timestamp_count"] == 1
    assert result["invalid_ohlc_count"] == 1
    assert result["file_sha256"]
    assert result["open_time_min_utc"] == "2025-08-01T00:00:00.000Z"


def test_audit_writes_local_universe_and_survivorship_manifest(tmp_path):
    helper = _load_helper()
    source = tmp_path / "lake"
    output = tmp_path / "artifact"
    source.mkdir()
    for symbol in ("BBB", "AAA"):
        timestamp = pd.Timestamp("2025-08-01T00:00:00Z")
        pd.DataFrame(
            {
                "symbol": [symbol + "USDT"],
                "open_time": [timestamp],
                "close_time": [timestamp + pd.Timedelta(minutes=5) - pd.Timedelta(milliseconds=1)],
                "open": [1.0],
                "high": [1.1],
                "low": [0.9],
                "close": [1.0],
            }
        ).to_parquet(source / f"{symbol}USDT.parquet", index=False)

    manifest = helper.audit_klines(source, output, batch_size=1)

    assert (output / "universe.csv").exists()
    assert (output / "manifest.json").exists()
    assert manifest["audit"]["file_count"] == 2
    assert manifest["universe"]["symbols"] == ["AAAUSDT", "BBBUSDT"]
    assert "local-file universe only" in manifest["universe"]["survivorship_bias"]
    assert manifest["protocol_document_sha256"]
    assert manifest["universe"]["sha256"]
    assert manifest["audit"]["source_snapshot_sha256"]
    assert helper._frozen_universe_matches(
        manifest,
        source,
        output,
        helper.DEFAULT_FUNDING_START,
        helper.DEFAULT_PRICE_END,
    )
    changed = pd.read_parquet(source / "AAAUSDT.parquet")
    changed.loc[0, "close"] = 2.0
    changed.to_parquet(source / "AAAUSDT.parquet", index=False)
    with pytest.raises(RuntimeError, match="frozen universe/source snapshot changed"):
        helper.load_or_audit_universe(source, output)


def test_funding_pagination_uses_last_time_plus_one_and_fixed_end():
    helper = _load_helper()
    start = datetime(2025, 8, 1, tzinfo=UTC)
    end = start + timedelta(days=10)
    first_page = [
        {
            "symbol": "AAAUSDT",
            "fundingTime": int((start + timedelta(hours=index)).timestamp() * 1000),
            "fundingRate": "0.001",
            "markPrice": "100",
        }
        for index in range(2)
    ]
    second_page = [
        {
            "symbol": "AAAUSDT",
            "fundingTime": int((start + timedelta(hours=3)).timestamp() * 1000),
            "fundingRate": "-0.002",
            "markPrice": "101",
        }
    ]
    client = FakeClient([FakeResponse(200, first_page), FakeResponse(200, second_page)])

    rows, metadata = helper.fetch_funding_for_symbol(
        "AAAUSDT",
        start,
        end,
        client=client,
        page_limit=2,
        pacer=helper.RequestPacer(interval_seconds=0, sleeper=lambda _seconds: None),
        sleeper=lambda _seconds: None,
    )

    assert len(rows) == 3
    assert metadata["page_count"] == 2
    assert client.calls[0][1]["endTime"] == client.calls[1][1]["endTime"]
    assert client.calls[0][1]["limit"] == 2
    assert client.calls[1][1]["startTime"] == first_page[-1]["fundingTime"] + 1
    assert metadata["final_page_status"] == "complete"


def test_retry_after_is_honoured_for_rate_limit():
    helper = _load_helper()
    start = datetime(2025, 8, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    sleeps: list[float] = []
    client = FakeClient(
        [
            FakeResponse(429, headers={"Retry-After": "7"}),
            FakeResponse(200, []),
        ]
    )

    _rows, metadata = helper.fetch_funding_for_symbol(
        "AAAUSDT",
        start,
        end,
        client=client,
        max_retries=1,
        pacer=helper.RequestPacer(interval_seconds=0, sleeper=lambda seconds: sleeps.append(seconds)),
        sleeper=lambda seconds: sleeps.append(seconds),
    )

    assert metadata["status"] == "complete"
    assert metadata["request_count"] == 2
    assert any(seconds >= 7 for seconds in sleeps)


def test_http_failure_is_not_data_absence_or_success():
    helper = _load_helper()
    start = datetime(2025, 8, 1, tzinfo=UTC)
    client = FakeClient([FakeResponse(403, {"code": -1, "msg": "blocked"})])

    rows, metadata = helper.fetch_funding_for_symbol(
        "AAAUSDT",
        start,
        start + timedelta(hours=1),
        client=client,
        max_retries=0,
        pacer=helper.RequestPacer(interval_seconds=0, sleeper=lambda _seconds: None),
        sleeper=lambda _seconds: None,
    )

    assert rows == []
    assert metadata["status"] == "failed"
    assert metadata["data_status"] == "not_observed"
    assert metadata["final_page_status"] == "http_403"
    assert metadata["errors"][0]["status_code"] == 403


def test_funding_schema_is_exact_and_missing_mark_price_is_null(tmp_path):
    helper = _load_helper()
    timestamp = datetime(2025, 8, 1, tzinfo=UTC)
    frame = helper.funding_rows_frame(
        [_funding_row(helper, timestamp, rate=0.0)],
        "AAAUSDT",
    )
    assert list(frame.columns) == ["symbol", "funding_time", "funding_rate", "mark_price"]
    assert str(frame["funding_time"].dtype).endswith(", UTC]")
    assert frame.loc[0, "funding_rate"] == 0.0

    path = tmp_path / "AAAUSDT.parquet"
    frame.to_parquet(path, index=False)
    loaded = pd.read_parquet(path)
    assert list(loaded.columns) == list(helper.FUNDING_COLUMNS)
    assert str(loaded["funding_time"].dtype).endswith(", UTC]")


def test_conflicting_duplicate_rates_are_retained_and_flagged():
    helper = _load_helper()
    timestamp = datetime(2025, 8, 1, tzinfo=UTC)
    payload = [
        {"fundingTime": int(timestamp.timestamp() * 1000), "fundingRate": "0.001"},
        {"fundingTime": int(timestamp.timestamp() * 1000), "fundingRate": "0.002"},
    ]
    client = FakeClient([FakeResponse(200, payload)])

    rows, metadata = helper.fetch_funding_for_symbol(
        "AAAUSDT",
        timestamp,
        timestamp + timedelta(hours=1),
        client=client,
        pacer=helper.RequestPacer(interval_seconds=0, sleeper=lambda _seconds: None),
        sleeper=lambda _seconds: None,
    )

    assert len(rows) == 2
    assert metadata["status"] == "partial"
    assert metadata["final_page_status"] == "conflicting_duplicate_timestamp"
    assert metadata["duplicate_timestamp_conflict_count"] == 1


def test_download_stops_after_three_systematically_blocked_probes(tmp_path):
    helper = _load_helper()
    source = tmp_path / "lake"
    output = tmp_path / "artifact"
    source.mkdir()
    start = pd.Timestamp("2025-08-01T00:00:00Z")
    for symbol in ("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT"):
        pd.DataFrame(
            {
                "symbol": [symbol],
                "open_time": [start],
                "close_time": [start + pd.Timedelta(minutes=5) - pd.Timedelta(milliseconds=1)],
                "open": [1.0],
                "high": [1.1],
                "low": [0.9],
                "close": [1.0],
            }
        ).to_parquet(source / f"{symbol}.parquet", index=False)
    manifest = helper.audit_klines(source, output, batch_size=1)
    client = FakeClient([FakeResponse(403)] * 3)

    result = helper.download_funding(
        output,
        manifest,
        max_retries=0,
        client=client,
        sleeper=lambda _seconds: None,
    )

    assert len(client.calls) == 3
    assert result["funding"]["status"] == "blocked"
    assert result["funding"]["network"]["systematically_blocked"] is True
    assert len(result["funding"]["symbols"]) == 4
    assert result["funding"]["symbols"]["DDDUSDT"]["final_page_status"] == "systematic_network_block"


def test_cache_prefix_requires_exact_symbol_schema_rowcount_and_digest(tmp_path):
    helper = _load_helper()
    start = datetime(2025, 8, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    funding_dir = tmp_path / "funding"
    funding_dir.mkdir()
    path = funding_dir / "AAAUSDT.parquet"
    wrong_symbol = helper.funding_rows_frame([_funding_row(helper, start)], "BBBUSDT")
    wrong_symbol.to_parquet(path, index=False)
    metadata = helper._new_funding_metadata("AAAUSDT", start, end)
    metadata.update(
        {
            "status": "complete",
            "final_page_status": "complete",
            "coverage_status": "complete",
            "schema": list(helper.FUNDING_COLUMNS),
            "artifact_sha256": helper.sha256_file(path),
            "range": {"row_count": 2},
        }
    )
    helper._atomic_json(funding_dir / "AAAUSDT.json", metadata)

    rows, _sidecar, errors = helper._prepare_existing("AAAUSDT", funding_dir, start, end)

    assert rows == []
    assert any(error["kind"] == "invalid_record" for error in errors)

    metadata["artifact_sha256"] = "0" * 64
    metadata["range"] = {"row_count": 1}
    helper._atomic_json(funding_dir / "AAAUSDT.json", metadata)
    _rows, _sidecar, errors = helper._prepare_existing("AAAUSDT", funding_dir, start, end)
    assert any(error["kind"] == "existing_artifact_hash_mismatch" for error in errors)


def test_invalid_existing_cache_is_not_replaced_by_empty_success(tmp_path):
    helper = _load_helper()
    start = datetime(2025, 8, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    funding_dir = tmp_path / "funding"
    funding_dir.mkdir()
    path = funding_dir / "AAAUSDT.parquet"
    helper.funding_rows_frame([_funding_row(helper, start)], "BBBUSDT").to_parquet(path, index=False)
    original_bytes = path.read_bytes()
    metadata = helper._new_funding_metadata("AAAUSDT", start, end)
    metadata.update(
        {
            "status": "complete",
            "final_page_status": "complete",
            "coverage_status": "complete",
            "schema": list(helper.FUNDING_COLUMNS),
            "artifact_sha256": helper.sha256_file(path),
            "range": {"row_count": 1},
        }
    )
    helper._atomic_json(funding_dir / "AAAUSDT.json", metadata)
    client = FakeClient([FakeResponse(200, [])])

    result = helper._process_symbol(
        "AAAUSDT",
        funding_dir,
        start,
        end,
        client=client,
        pacer=helper.RequestPacer(interval_seconds=0, sleeper=lambda _seconds: None),
        sleeper=lambda _seconds: None,
        max_retries=0,
        backoff_seconds=0,
        timeout=1,
        use_archives=False,
    )

    assert result["status"] == "failed"
    assert path.read_bytes() == original_bytes


def test_page_outside_requested_cursor_blocks_completion():
    helper = _load_helper()
    start = datetime(2025, 8, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    old_row = {
        "fundingTime": int((start - timedelta(hours=1)).timestamp() * 1000),
        "fundingRate": "0.001",
        "markPrice": "100",
    }
    client = FakeClient([FakeResponse(200, [old_row])])

    rows, metadata = helper.fetch_funding_for_symbol(
        "AAAUSDT",
        start,
        end,
        client=client,
        max_retries=0,
        pacer=helper.RequestPacer(interval_seconds=0, sleeper=lambda _seconds: None),
        sleeper=lambda _seconds: None,
    )

    assert rows == []
    assert metadata["status"] == "failed"
    assert metadata["final_page_status"] == "page_out_of_requested_bounds"
    assert any(error["kind"] == "page_out_of_requested_bounds" for error in metadata["errors"])


def test_empty_terminal_page_after_retained_rows_is_complete():
    helper = _load_helper()
    start = datetime(2025, 8, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    row = {
        "fundingTime": int(start.timestamp() * 1000),
        "fundingRate": "0.001",
        "markPrice": "100",
    }
    client = FakeClient([FakeResponse(200, [row]), FakeResponse(200, [])])

    rows, metadata = helper.fetch_funding_for_symbol(
        "AAAUSDT",
        start,
        end,
        client=client,
        page_limit=1,
        max_retries=0,
        pacer=helper.RequestPacer(interval_seconds=0, sleeper=lambda _seconds: None),
        sleeper=lambda _seconds: None,
    )

    assert len(rows) == 1
    assert metadata["status"] == "complete"
    assert metadata["coverage_status"] == "complete"
    assert metadata["final_page_status"] == "empty_response"
    assert metadata["completion_basis"] == "empty_terminal_page"


def test_nonpositive_and_conflicting_marks_are_not_verified():
    helper = _load_helper()
    start = datetime(2025, 8, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    nonpositive_client = FakeClient(
        [FakeResponse(200, [{"fundingTime": int(start.timestamp() * 1000), "fundingRate": "0.001", "markPrice": "0"}])]
    )
    _rows, metadata = helper.fetch_funding_for_symbol(
        "AAAUSDT",
        start,
        end,
        client=nonpositive_client,
        max_retries=0,
        pacer=helper.RequestPacer(interval_seconds=0, sleeper=lambda _seconds: None),
        sleeper=lambda _seconds: None,
    )
    assert metadata["status"] == "partial"
    assert metadata["invalid_record_count"] == 1

    conflict_client = FakeClient(
        [
            FakeResponse(
                200,
                [
                    {"fundingTime": int(start.timestamp() * 1000), "fundingRate": "0.001", "markPrice": "100"},
                    {"fundingTime": int(start.timestamp() * 1000), "fundingRate": "0.001", "markPrice": "101"},
                ],
            )
        ]
    )
    rows, metadata = helper.fetch_funding_for_symbol(
        "AAAUSDT",
        start,
        end,
        client=conflict_client,
        max_retries=0,
        pacer=helper.RequestPacer(interval_seconds=0, sleeper=lambda _seconds: None),
        sleeper=lambda _seconds: None,
    )
    assert rows == []
    assert metadata["status"] == "partial"
    assert metadata["mark_price_conflict_count"] == 1
    assert metadata["final_page_status"] == "conflicting_duplicate_timestamp"


def test_audit_flags_conflicting_duplicate_ohlc(tmp_path):
    helper = _load_helper()
    timestamp = pd.Timestamp("2025-08-01T00:00:00Z")
    frame = pd.DataFrame(
        {
            "symbol": ["AAAUSDT", "AAAUSDT"],
            "open_time": [timestamp, timestamp],
            "close_time": [timestamp + pd.Timedelta(minutes=5) - pd.Timedelta(milliseconds=1)] * 2,
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
        }
    )
    path = tmp_path / "AAAUSDT.parquet"
    frame.to_parquet(path, index=False, row_group_size=1)

    result = helper.audit_kline_file(path, batch_size=1)

    assert result["duplicate_timestamp_count"] == 1
    assert result["duplicate_ohlc_conflict_count"] == 1
    assert result["duplicate_ohlc_conflict_examples"]


def test_vision_missing_required_month_is_partial_and_cutoff_month_is_requested():
    helper = _load_helper()
    end = datetime(2026, 9, 1, 0, 0, 0, 1000, tzinfo=UTC)
    assert datetime(2026, 9, 1).date() in helper._month_starts(
        datetime(2025, 8, 1, tzinfo=UTC), end
    )
    client = FakeClient([FakeResponse(404), FakeResponse(404)])

    rows, metadata = helper.fetch_funding_from_vision(
        "AAAUSDT",
        datetime(2026, 8, 1, tzinfo=UTC),
        end,
        client=client,
        max_retries=0,
        pacer=helper.RequestPacer(interval_seconds=0, sleeper=lambda _seconds: None),
        sleeper=lambda _seconds: None,
    )

    assert rows == []
    assert metadata["missing_month_count"] == 2
    assert metadata["status"] == "partial"
    assert metadata["final_page_status"] == "archive_error"


def test_terminal_retry_after_sets_global_pacer_deadline():
    helper = _load_helper()
    now = [0.0]
    sleeps: list[float] = []

    def clock():
        return now[0]

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    pacer = helper.RequestPacer(interval_seconds=0, clock=clock, sleeper=sleep)
    client = FakeClient([FakeResponse(429, headers={"Retry-After": "7"}), FakeResponse(200, [])])
    first = helper._request_json(
        client,
        {"symbol": "AAAUSDT"},
        pacer=pacer,
        sleeper=sleep,
        max_retries=0,
    )
    second = helper._request_json(
        client,
        {"symbol": "BBBUSDT"},
        pacer=pacer,
        sleeper=sleep,
        max_retries=0,
    )

    assert first.transport_status == "rate_limited"
    assert second.ok is True
    assert any(seconds >= 7 for seconds in sleeps)


def test_resume_preserves_prior_page_provenance_and_counts():
    helper = _load_helper()
    start = datetime(2025, 8, 1, tzinfo=UTC)
    old_end = start + timedelta(hours=2)
    new_end = old_end + timedelta(hours=2)
    existing_metadata = helper._new_funding_metadata("AAAUSDT", start, old_end)
    existing_metadata.update(
        {
            "status": "complete",
            "final_page_status": "complete",
            "coverage_status": "complete",
            "page_count": 2,
            "request_count": 3,
            "range": {"row_count": 1},
            "page_provenance": [{"page": 1, "requested_start_ms": int(start.timestamp() * 1000)}],
        }
    )
    client = FakeClient([FakeResponse(200, [])])

    rows, metadata = helper.fetch_funding_for_symbol(
        "AAAUSDT",
        start,
        new_end,
        client=client,
        existing_rows=[_funding_row(helper, start)],
        existing_metadata=existing_metadata,
        max_retries=0,
        pacer=helper.RequestPacer(interval_seconds=0, sleeper=lambda _seconds: None),
        sleeper=lambda _seconds: None,
    )

    assert len(rows) == 1
    assert metadata["page_count"] == 3
    assert metadata["request_count"] == 4
    assert len(metadata["page_provenance"]) == 2
    assert metadata["resume"]["previous_page_count"] == 2
    assert metadata["resume"]["previous_run"]["final_page_status"] == "complete"
    assert client.calls[0][1]["startTime"] == int(old_end.timestamp() * 1000)
