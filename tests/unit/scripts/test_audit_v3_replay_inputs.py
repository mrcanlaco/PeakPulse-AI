"""Synthetic fail-closed contracts for the V3 replay-input audit."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "audit_v3_replay_inputs.py"
UTC = timezone.utc


def _load_helper():
    spec = importlib.util.spec_from_file_location("test_audit_v3_replay_inputs_impl", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _event(
    *,
    event_id: str,
    lane: str,
    source_event_id: str,
    symbol: str = "AAAUSDT",
    signal: datetime = datetime(2026, 3, 1, 0, 5, tzinfo=UTC),
):
    feature = signal - timedelta(milliseconds=1)
    return {
        "accepted": True,
        "champion_gate": {"accepted": True},
        "distance_from_high_24h": -0.03,
        "event_id": event_id,
        "feature_time_utc": feature.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "fold": 1,
        "fold_threshold": 0.25,
        "label_contract": "legacy_entry1_48h_oos_label; not compact weighted-average execution outcome",
        "label_value": 0,
        "lane": lane,
        "model_provenance": {
            "fold": 1,
            "fold_model_hash_available": False,
            "fold_model_sha256": None,
            "score_field": "probability",
            "score_kind": "persisted calibrated fold OOS score",
            "selection_threshold": None,
            "threshold_is_row_fold_threshold": True,
        },
        "pit": {"exact_join_matched": True},
        "price_ret_24h": 0.3,
        "raw_score": 0.4,
        "reason": "selected",
        "score": 0.35,
        "signal_time_utc": signal.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": {
            "artifact": "synthetic.csv",
            "sha256": "a" * 64,
            "source_key": f"{symbol}|{feature.isoformat()}|fold=1|episode=synthetic",
        },
        "source_episode_id": f"1:{symbol}:0",
        "source_event_id": source_event_id,
        "source_row_number": 1,
        "symbol": symbol,
        "timing_episode_id": f"1:{symbol}:0",
    }


def _replay_event(reference_event):
    return {
        "event_id": reference_event["event_id"],
        "lane": reference_event["lane"],
        "source_event_id": reference_event["source_event_id"],
        "source_episode_id": reference_event["source_episode_id"],
        "symbol": reference_event["symbol"],
        "feature_time_utc": reference_event["feature_time_utc"],
        "signal_time_utc": reference_event["signal_time_utc"],
        "fold": reference_event["fold"],
        "source_score": reference_event["score"],
        "source_raw_score": reference_event["raw_score"],
        "replay_status": "resolved_path",
        "price_path_resolved": True,
        "compact_financial_outcome_eligible": False,
        "compact_funding_eligibility": "synthetic",
    }


def _funding_rows(helper, symbol: str, signal: datetime, interval_hours: int = 4):
    rows = []
    for index in range(1, (48 // interval_hours) + 1):
        timestamp = signal + timedelta(hours=interval_hours * index)
        timestamp_ms = int(timestamp.timestamp() * 1000)
        rate = 0.001
        mark = 100.0
        rows.append(
            {
                "symbol": symbol,
                "funding_time": timestamp,
                "funding_rate": rate,
                "mark_price": mark,
                "funding_time_ms": timestamp_ms,
                "source_row_sha256": helper._funding_row_sha256(symbol, timestamp_ms, rate, mark),
            }
        )
    return rows


def _fixture(
    tmp_path: Path,
    helper,
    *,
    funding_mode: str = "complete",
    funding_window: tuple[datetime, datetime] | None = None,
    tamper_funding: bool = False,
    missing_price_bar: bool = False,
    omit_funding_entry: bool = False,
    funding_interval_hours: int = 4,
):
    reference_path = tmp_path / "reference.json"
    replay_path = tmp_path / "replay.json"
    data_root = tmp_path / "data"
    funding_root = data_root / "funding"
    price_root = tmp_path / "prices"
    funding_root.mkdir(parents=True)
    price_root.mkdir(parents=True)

    first = _event(event_id="event-a", lane="locked_parent_oos", source_event_id="source-overlap")
    second = _event(event_id="event-b", lane="current_timing_runtime_reference", source_event_id="source-overlap")
    reference = {
        "artifact": "synthetic_reference",
        "coverage": {"source_events_in_both_lanes": 1},
        "events": [first, second],
        "model_provenance": {"fold_model_hashes_available": False},
        "source": {},
    }
    replay = {
        "artifact": "synthetic_replay",
        "coverage": {"source_events_in_both_lanes": 1},
        "events": [_replay_event(first), _replay_event(second)],
        "source": {},
    }
    reference_path.write_text(json.dumps(reference), encoding="utf-8")
    replay_path.write_text(json.dumps(replay), encoding="utf-8")

    signal = datetime(2026, 3, 1, 0, 5, tzinfo=UTC)
    # The signal is the normalized close boundary of the preceding candle.
    # Include that entry candle, then 576 forward candles through the horizon.
    price_times = [signal - timedelta(minutes=5) + timedelta(minutes=5 * index) for index in range(577)]
    if missing_price_bar:
        price_times.pop(100)
    price_frame = pd.DataFrame(
        {
            "symbol": ["AAAUSDT"] * len(price_times),
            "open_time": price_times,
            "close_time": [value + timedelta(minutes=5) - timedelta(milliseconds=1) for value in price_times],
            "open": [100.0] * len(price_times),
            "high": [101.0] * len(price_times),
            "low": [99.0] * len(price_times),
            "close": [100.0] * len(price_times),
        }
    )
    price_path = price_root / "AAAUSDT.parquet"
    price_frame.to_parquet(price_path, index=False)
    price_manifest = {
        "manifest_version": "annual_profit_prices_v2",
        "status": "complete",
        "price_root": str(price_root),
        "requested_ranges": {
            "warmup_start_utc": "2026-01-01T00:00:00Z",
            "output_clip_start_utc": "2026-01-01T00:00:00Z",
            "cutoff_utc_exclusive": "2026-04-01T00:00:00Z",
            "output_clip_end_exclusive_utc": "2026-04-01T00:00:00Z",
        },
        "configuration": {
            "protocol_id": "synthetic",
            "protocol_sha256": "b" * 64,
            "source_dir": str(tmp_path / "raw"),
            "output_root": str(tmp_path),
            "warmup_start_utc": "2026-01-01T00:00:00.000Z",
            "window_start_utc": "2026-01-01T00:00:00.000Z",
            "cutoff_utc_exclusive": "2026-04-01T00:00:00.000Z",
            "bar_interval_ms": helper.BAR_INTERVAL_MS,
            "canonical_columns": list(helper.PRICE_COLUMNS),
            "retained_volume_columns": [],
            "source_file_hashes": [],
        },
        "symbols": {},
    }
    price_manifest["configuration_sha256"] = helper._canonical_sha256(price_manifest["configuration"])
    price_manifest["symbols"]["AAAUSDT"] = {
        "symbol": "AAAUSDT",
        "status": "ready",
        "output_path": str(price_path),
        "output_sha256": _sha256(price_path),
        "output_columns": list(price_frame.columns),
        "coverage": {
            "after_backfill_audit": {
                "requested_range_start_ms": int(datetime(2026, 1, 1, tzinfo=UTC).timestamp() * 1000),
                "requested_cutoff_ms": int(datetime(2026, 4, 1, tzinfo=UTC).timestamp() * 1000),
                "coverage_start_ms": int(datetime(2026, 1, 1, tzinfo=UTC).timestamp() * 1000),
                "coverage_end_exclusive_ms": int(datetime(2026, 4, 1, tzinfo=UTC).timestamp() * 1000),
                "missing_bar_count": 0,
                "internal_missing_bar_count": 0,
                "leading_missing_bar_count": 0,
                "trailing_missing_bar_count": 0,
            }
        },
    }
    price_manifest_path = tmp_path / "price_manifest.json"
    price_manifest_path.write_text(json.dumps(price_manifest), encoding="utf-8")

    funding_rows = _funding_rows(helper, "AAAUSDT", signal, funding_interval_hours)
    funding_frame = pd.DataFrame(
        [
            {key: row[key] for key in ("symbol", "funding_time", "funding_rate", "mark_price")}
            for row in funding_rows
        ]
    )
    funding_path = funding_root / "AAAUSDT.parquet"
    funding_frame.to_parquet(funding_path, index=False)
    manifest_funding_sha = _sha256(funding_path)
    if tamper_funding:
        tampered = pd.read_parquet(funding_path)
        tampered.loc[0, "funding_rate"] = 0.002
        tampered.to_parquet(funding_path, index=False)

    sidecar = {
        "format": "annual_profit_funding_row_provenance_v1",
        "protocol": "synthetic",
        "symbol": "AAAUSDT",
        "row_count": len(funding_rows),
        "rows": [
            {
                "funding_time_ms": row["funding_time_ms"],
                "funding_time_utc": row["funding_time"].isoformat().replace("+00:00", "Z"),
                "source_id": f"synthetic:{row['funding_time_ms']}",
                "source_row_sha256": row["source_row_sha256"],
            }
            for row in funding_rows
        ],
    }
    sidecar_path = funding_root / "AAAUSDT.provenance.json"
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")

    requested_start = datetime(2026, 1, 1, tzinfo=UTC)
    requested_end = datetime(2026, 4, 1, tzinfo=UTC)
    if funding_window is not None:
        requested_start, requested_end = funding_window
    universe_path = tmp_path / "universe.csv"
    universe_path.write_text("symbol\nAAAUSDT\n", encoding="utf-8")
    source_files = [{"symbol": "AAAUSDT", "file_name": "AAAUSDT.parquet", "file_sha256": "c" * 64}]
    protocol_path = tmp_path / "protocol.md"
    protocol_path.write_text("synthetic protocol", encoding="utf-8")
    data_manifest = {
        "protocol": "synthetic",
        "protocol_document": str(protocol_path),
        "protocol_document_sha256": _sha256(protocol_path),
        "audit": {
            "files": source_files,
            "source_snapshot_sha256": helper._source_snapshot_sha256(source_files),
        },
        "universe": {"path": str(universe_path), "sha256": _sha256(universe_path)},
        "funding": {
            "status": "partial" if funding_mode == "partial" else "complete",
            "requested_window": {
                "start_utc": requested_start.isoformat().replace("+00:00", "Z"),
                "end_exclusive_utc": requested_end.isoformat().replace("+00:00", "Z"),
            },
            "symbols": {},
        },
    }
    if not omit_funding_entry:
        funding_manifest_entry = {
            "symbol": "AAAUSDT",
            "status": funding_mode,
            "transport_status": "success",
            "final_page_status": "complete",
            "completion_basis": "page_shorter_than_limit",
            "coverage_status": funding_mode,
            "data_status": "present",
            "schema": list(helper.FUNDING_COLUMNS),
            "artifact_path": str(funding_path),
            "artifact_sha256": manifest_funding_sha,
            "requested_window": {
                "start_ms": int(requested_start.timestamp() * 1000),
                "end_exclusive_ms": int(requested_end.timestamp() * 1000),
                "start_utc": requested_start.isoformat().replace("+00:00", "Z"),
                "end_exclusive_utc": requested_end.isoformat().replace("+00:00", "Z"),
                "api_end_time_ms_inclusive": int(requested_end.timestamp() * 1000) - 1,
            },
            "provenance": {
                "source": "Synthetic provider",
                "endpoint": "https://example.invalid/funding",
                "page_limit": 1000,
                "pagination": "startTime = greatest returned fundingTime + 1ms",
                "end_time_policy": "fixed API endTime = requested exclusive end - 1ms",
            },
            "page_count": 1,
            "request_count": 1,
            "page_provenance": [
                {
                    "page": 1,
                    "requested_start_ms": int(requested_start.timestamp() * 1000),
                    "requested_end_ms": int(requested_end.timestamp() * 1000) - 1,
                    "limit": 1000,
                    "attempts": 1,
                    "status_code": 200,
                    "transport_status": "success",
                    "response_count": len(funding_rows),
                    "min_raw_time_ms": funding_rows[0]["funding_time_ms"],
                    "max_raw_time_ms": funding_rows[-1]["funding_time_ms"],
                }
            ],
            "invalid_record_count": 1 if funding_mode == "partial" else 0,
            "duplicate_timestamp_conflict_count": 0,
            "mark_price_conflict_count": 0,
            "errors": [{"kind": "invalid_mark_price"}] if funding_mode == "partial" else [],
            "range": {
                "first_funding_time_utc": funding_rows[0]["funding_time"].isoformat().replace("+00:00", "Z"),
                "last_funding_time_utc": funding_rows[-1]["funding_time"].isoformat().replace("+00:00", "Z"),
                "row_count": len(funding_rows),
            },
            "row_provenance_artifact_path": str(sidecar_path),
            "row_provenance_artifact_sha256": _sha256(sidecar_path),
            "row_provenance_count": len(funding_rows),
            "snapshot": {
                "source_snapshot_sha256": data_manifest["audit"]["source_snapshot_sha256"],
                "universe_sha256": data_manifest["universe"]["sha256"],
                "protocol_document_sha256": data_manifest["protocol_document_sha256"],
                "source_file_sha256": source_files[0]["file_sha256"],
            },
        }
        data_manifest["funding"]["symbols"]["AAAUSDT"] = funding_manifest_entry
    data_manifest_path = tmp_path / "data_manifest.json"
    data_manifest_path.write_text(json.dumps(data_manifest), encoding="utf-8")

    return {
        "reference": reference_path,
        "replay": replay_path,
        "data_manifest": data_manifest_path,
        "funding_root": funding_root,
        "price_manifest": price_manifest_path,
        "price_root": price_root,
    }


def _audit(tmp_path, **kwargs):
    helper = _load_helper()
    paths = _fixture(tmp_path, helper, **kwargs)
    return helper.build_audit(
        reference_path=paths["reference"],
        price_replay_path=paths["replay"],
        data_manifest_path=paths["data_manifest"],
        funding_root=paths["funding_root"],
        price_manifest_path=paths["price_manifest"],
        price_root=paths["price_root"],
    )


def _provider_entry(completion_basis: str):
    start_ms = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp() * 1000)
    end_exclusive_ms = int(datetime(2026, 4, 1, tzinfo=UTC).timestamp() * 1000)
    api_end_ms = end_exclusive_ms - 1
    limit = 1000
    first_max = start_ms + 999
    second_start = first_max + 1
    pages = [
        {
            "page": 1,
            "requested_start_ms": start_ms,
            "requested_end_ms": api_end_ms,
            "limit": limit,
            "attempts": 1,
            "status_code": 200,
            "transport_status": "success",
            "response_count": limit,
            "min_raw_time_ms": start_ms,
            "max_raw_time_ms": first_max,
        },
        {
            "page": 2,
            "requested_start_ms": second_start,
            "requested_end_ms": api_end_ms,
            "limit": limit,
            "attempts": 1,
            "status_code": 200,
            "transport_status": "success",
            "response_count": 3,
            "min_raw_time_ms": second_start,
            "max_raw_time_ms": second_start + 2,
        },
    ]
    if completion_basis == "empty_terminal_page":
        pages = [
            {
                "page": 1,
                "requested_start_ms": start_ms,
                "requested_end_ms": api_end_ms,
                "limit": limit,
                "attempts": 1,
                "status_code": 200,
                "transport_status": "success",
                "response_count": 0,
                "min_raw_time_ms": None,
                "max_raw_time_ms": None,
            }
        ]
    elif completion_basis == "end_time_reached":
        pages = [
            {
                "page": 1,
                "requested_start_ms": start_ms,
                "requested_end_ms": api_end_ms,
                "limit": limit,
                "attempts": 1,
                "status_code": 200,
                "transport_status": "success",
                "response_count": limit,
                "min_raw_time_ms": start_ms,
                "max_raw_time_ms": api_end_ms,
            }
        ]
    entry = {
        "transport_status": "success",
        "final_page_status": "empty_response" if completion_basis == "empty_terminal_page" else "complete",
        "completion_basis": completion_basis,
        "page_count": len(pages),
        "request_count": len(pages),
        "page_provenance": pages,
        "requested_window": {
            "start_ms": start_ms,
            "end_exclusive_ms": end_exclusive_ms,
            "api_end_time_ms_inclusive": api_end_ms,
        },
        "provenance": {
            "page_limit": limit,
            "pagination": "startTime = greatest returned fundingTime + 1ms",
            "end_time_policy": "fixed API endTime = requested exclusive end - 1ms",
        },
    }
    if completion_basis == "requested_end_bound":
        entry["resume"] = {
            "used_existing_provenance": True,
            "resume_start_ms": end_exclusive_ms,
            "prefix_end_exclusive_ms": end_exclusive_ms,
        }
    return entry, {"start_ms": start_ms, "end_exclusive_ms": end_exclusive_ms}


def test_provider_pagination_accepts_valid_empty_short_end_and_resume_bound_cases():
    helper = _load_helper()

    for basis in (
        "empty_terminal_page",
        "page_shorter_than_limit",
        "end_time_reached",
        "requested_end_bound",
    ):
        entry, requested = _provider_entry(basis)
        checks, reasons = helper._funding_extraction_provenance_check(entry, requested)

        assert checks["complete_request_certified"] is True, (basis, reasons)
        assert reasons == [], (basis, reasons)


@pytest.mark.parametrize(
    ("status_code", "certified"),
    [
        pytest.param(200, True, id="integer-200"),
        pytest.param(200.0, False, id="float-200"),
        pytest.param("200", False, id="string-200"),
        pytest.param(True, False, id="bool-true"),
    ],
)
def test_provider_pagination_requires_strict_integer_status_code(status_code, certified):
    helper = _load_helper()
    entry, requested = _provider_entry("page_shorter_than_limit")
    entry["page_provenance"][0]["status_code"] = status_code

    checks, reasons = helper._funding_extraction_provenance_check(entry, requested)

    assert checks["complete_request_certified"] is certified
    if certified:
        assert reasons == []
    else:
        assert "funding_provider_page_status_code_invalid" in reasons


def test_provider_pagination_rejects_sol_cursor_gap_mutation():
    helper = _load_helper()
    entry, requested = _provider_entry("page_shorter_than_limit")
    entry["page_provenance"][1]["requested_start_ms"] += 123

    checks, reasons = helper._funding_extraction_provenance_check(entry, requested)

    assert checks["complete_request_certified"] is False
    assert "funding_provider_page_cursor_mismatch" in reasons


def test_provider_pagination_rejects_sol_short_terminal_count_mutation():
    helper = _load_helper()
    entry, requested = _provider_entry("page_shorter_than_limit")
    entry["page_provenance"][-1]["response_count"] = entry["page_provenance"][-1]["limit"]

    checks, reasons = helper._funding_extraction_provenance_check(entry, requested)

    assert checks["complete_request_certified"] is False
    assert "funding_provider_terminal_short_page_evidence_mismatch" in reasons


def test_provider_pagination_rejects_missing_and_contradictory_metadata():
    helper = _load_helper()
    entry, requested = _provider_entry("page_shorter_than_limit")
    missing = deepcopy(entry)
    missing["page_provenance"][0].pop("transport_status")
    missing["page_provenance"][1].pop("response_count")
    checks, reasons = helper._funding_extraction_provenance_check(missing, requested)
    assert checks["complete_request_certified"] is False
    assert "funding_provider_page_transport_not_success" in reasons
    assert "funding_provider_page_response_count_missing_or_invalid" in reasons

    contradictory = deepcopy(entry)
    contradictory["page_provenance"][1]["page"] = 4
    contradictory["page_provenance"][1]["requested_end_ms"] += 1
    checks, reasons = helper._funding_extraction_provenance_check(contradictory, requested)
    assert checks["complete_request_certified"] is False
    assert "funding_provider_page_index_mismatch" in reasons
    assert "funding_provider_page_end_policy_mismatch" in reasons


def test_provider_pagination_rejects_unknown_completion_basis():
    helper = _load_helper()
    entry, requested = _provider_entry("page_shorter_than_limit")
    entry["completion_basis"] = "provider_said_done"

    checks, reasons = helper._funding_extraction_provenance_check(entry, requested)

    assert checks["complete_request_certified"] is False
    assert "funding_provider_completion_basis_unknown" in reasons


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        pytest.param("start_ms", 1767225600000.0, id="start-float"),
        pytest.param("start_ms", "1767225600000", id="start-string"),
        pytest.param("start_ms", True, id="start-bool"),
        pytest.param("end_exclusive_ms", 1775001600000.0, id="end-float"),
        pytest.param("end_exclusive_ms", "1775001600000", id="end-string"),
        pytest.param("end_exclusive_ms", True, id="end-bool"),
        pytest.param("api_end_time_ms_inclusive", 1775001599999.0, id="api-end-float"),
        pytest.param("api_end_time_ms_inclusive", "1775001599999", id="api-end-string"),
        pytest.param("api_end_time_ms_inclusive", True, id="api-end-bool"),
    ],
)
def test_funding_requested_window_rejects_non_integer_fields(tmp_path, field, bad_value):
    helper = _load_helper()
    paths = _fixture(tmp_path, helper)
    manifest = json.loads(paths["data_manifest"].read_text(encoding="utf-8"))
    manifest["funding"]["symbols"]["AAAUSDT"]["requested_window"][field] = bad_value

    result = helper._audit_funding_symbol(
        "AAAUSDT",
        [_event(event_id="event-1", lane="lane-a", source_event_id="source-1")],
        manifest,
        paths["data_manifest"],
        paths["funding_root"],
        [],
    )

    assert result["validation"]["status"] == "failed"
    assert "funding_requested_window_invalid" in result["validation"]["reasons"]


def test_funding_requested_window_accepts_valid_integer_fields(tmp_path):
    helper = _load_helper()
    paths = _fixture(tmp_path, helper)
    manifest = json.loads(paths["data_manifest"].read_text(encoding="utf-8"))

    result = helper._audit_funding_symbol(
        "AAAUSDT",
        [_event(event_id="event-1", lane="lane-a", source_event_id="source-1")],
        manifest,
        paths["data_manifest"],
        paths["funding_root"],
        [],
    )

    assert result["requested_window"]["match"] is True
    assert result["validation"]["status"] == "ok"
    assert "funding_requested_window_invalid" not in result["validation"]["reasons"]


def test_missing_funding_manifest_entry_fails_closed(tmp_path):
    report = _audit(tmp_path, omit_funding_entry=True)

    assert report["summary"]["valid_48h_price_path_count"] == 2
    assert report["summary"]["funding_input_ready_count"] == 0
    assert all(
        "funding_manifest_symbol_entry_missing" in event["exclusions"]
        for event in report["events"]
    )


def test_partial_funding_is_retained_but_never_eligible(tmp_path):
    report = _audit(tmp_path, funding_mode="partial")

    funding = report["events"][0]["funding"]
    assert funding["settlement_rows_in_window"] == 12
    assert funding["cadence_heuristic"]["ok"] is True
    assert funding["raw_funding_coverage_certified"] is False
    assert funding["funding_input_ready"] is False
    assert "funding_manifest_symbol_not_complete" in funding["reasons"]


def test_out_of_range_funding_request_fails_closed(tmp_path):
    report = _audit(
        tmp_path,
        funding_window=(
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        ),
    )

    funding = report["events"][0]["funding"]
    assert funding["funding_requested_range_covers_event"] is False
    assert funding["funding_input_ready"] is False
    assert "funding_request_does_not_cover_event" in funding["reasons"]


def test_tampered_funding_artifact_fails_checksum_closed(tmp_path):
    report = _audit(tmp_path, tamper_funding=True)

    funding = report["events"][0]["funding"]
    symbol_funding = report["symbols"]["AAAUSDT"]["funding"]
    assert "funding_artifact_sha256_mismatch" in symbol_funding["validation"]["reasons"]
    assert funding["settlement_rows_in_window"] == 0
    assert funding["funding_input_ready"] is False


def test_missing_price_candle_fails_exact_48h_path_closed(tmp_path):
    report = _audit(tmp_path, missing_price_bar=True)

    price = report["events"][0]["price"]
    assert price["entry_bar_valid"] is True
    assert price["valid_forward_bar_count"] == 575
    assert price["missing_forward_bar_count"] == 1
    assert price["price_path_ready"] is False
    assert "missing_forward_price_bars" in price["reasons"]


def test_overlapping_lane_rows_remain_distinct_source_observations(tmp_path):
    report = _audit(tmp_path)

    assert report["summary"]["lane_event_rows"] == 2
    assert report["summary"]["unique_source_event_ids"] == 1
    assert report["summary"]["overlapping_source_event_id_count"] == 1
    assert len({event["lane_event_key"] for event in report["events"]}) == 2
    assert all(event["source_event_overlaps_lanes"] for event in report["events"])


def test_render_markdown_reports_provider_provenance_exclusions_without_blocker():
    helper = _load_helper()
    report = {
        "summary": {
            "lane_event_rows": 2,
            "unique_source_event_ids": 2,
            "overlapping_source_event_id_count": 0,
            "exact_entry_bar_count": 2,
            "valid_48h_price_path_count": 2,
            "funding_requested_range_covers_count": 2,
            "funding_settlement_rows_present_count": 2,
            "funding_cadence_heuristic_ok_count": 2,
            "manifest_backed_raw_funding_count": 2,
            "funding_input_ready_count": 2,
            "financial_replay_input_ready_count": 2,
            "exclusion_counts": {
                "funding_manifest_has_errors": 2,
                "funding_provider_page_provenance_incomplete": 2,
            },
            "lane_summary": {},
        },
        "blockers": [],
    }

    markdown = helper.render_markdown(report)

    assert "- None at the artifact/manifest level." in markdown
    assert "| `funding_provider_page_provenance_incomplete` | 2/2 |" in markdown
    assert "| `funding_manifest_has_errors` | 2/2 |" in markdown
    assert "Reasons may overlap on the same row" in markdown
    assert "do not sum to unique excluded rows" in markdown


def test_eight_hour_provider_history_is_not_rejected_by_four_hour_diagnostic(tmp_path):
    report = _audit(tmp_path, funding_interval_hours=8)

    funding = report["events"][0]["funding"]
    assert funding["settlement_rows_in_window"] == 6
    assert funding["cadence_heuristic"]["ok"] is False
    assert funding["cadence_heuristic"]["diagnostic_only"] is True
    assert funding["raw_funding_coverage_certified"] is True
    assert funding["funding_input_ready"] is True
    assert not any(reason.startswith("funding_cadence_") for reason in funding["reasons"])


def test_funding_request_start_must_be_at_or_before_event_signal(tmp_path):
    report = _audit(
        tmp_path,
        funding_window=(
            datetime(2026, 3, 1, 0, 6, tzinfo=UTC),
            datetime(2026, 4, 1, tzinfo=UTC),
        ),
    )

    funding = report["events"][0]["funding"]
    assert funding["funding_requested_range_covers_event"] is False
    assert funding["funding_input_ready"] is False
    assert "funding_request_does_not_cover_event" in funding["reasons"]


def test_protocol_crlf_equivalence_records_raw_and_normalized_digests(tmp_path):
    helper = _load_helper()
    paths = _fixture(tmp_path, helper)
    manifest = json.loads(paths["data_manifest"].read_text(encoding="utf-8"))
    protocol_path = tmp_path / "protocol.md"
    protocol_path.write_bytes(b"synthetic protocol\r\n")
    expected = hashlib.sha256(b"synthetic protocol\n").hexdigest()
    manifest["protocol_document_sha256"] = expected
    for entry in manifest["funding"]["symbols"].values():
        entry["snapshot"]["protocol_document_sha256"] = expected
    paths["data_manifest"].write_text(json.dumps(manifest), encoding="utf-8")

    report = helper.build_audit(
        reference_path=paths["reference"],
        price_replay_path=paths["replay"],
        data_manifest_path=paths["data_manifest"],
        funding_root=paths["funding_root"],
        price_manifest_path=paths["price_manifest"],
        price_root=paths["price_root"],
    )
    checks = report["inputs"]["manifest_checks"]["data"]
    assert checks["protocol_document_digest_method"] == "crlf_to_lf"
    assert checks["protocol_document_sha256_raw"] != expected
    assert checks["protocol_document_sha256_normalized"] == expected
    assert checks["protocol_document_sha256_match"] is True
    assert "data_manifest_protocol_document_sha256_mismatch" not in report["frozen_cohort"]["reasons"]


def test_protocol_content_change_still_fails_closed(tmp_path):
    helper = _load_helper()
    paths = _fixture(tmp_path, helper)
    protocol_path = tmp_path / "protocol.md"
    protocol_path.write_text("synthetic protocol changed", encoding="utf-8")

    report = helper.build_audit(
        reference_path=paths["reference"],
        price_replay_path=paths["replay"],
        data_manifest_path=paths["data_manifest"],
        funding_root=paths["funding_root"],
        price_manifest_path=paths["price_manifest"],
        price_root=paths["price_root"],
    )
    checks = report["inputs"]["manifest_checks"]["data"]
    assert checks["protocol_document_digest_method"] == "none"
    assert "data_manifest_protocol_document_sha256_mismatch" in report["events"][0]["exclusions"]
    assert all(
        "data_manifest_protocol_document_sha256_mismatch" in event["exclusions"]
        for event in report["events"]
    )


def test_global_frozen_identity_failure_suppresses_event_readiness(tmp_path):
    report = _audit(tmp_path)

    assert report["frozen_cohort"]["reasons"]
    assert all(event["eligibility"]["global_identity_verified"] is False for event in report["events"])
    assert all(event["eligibility"]["financial_replay_input_ready"] is False for event in report["events"])
    assert all(
        any(reason.startswith("frozen_source.") for reason in event["exclusions"])
        for event in report["events"]
    )
