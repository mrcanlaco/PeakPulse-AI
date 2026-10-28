import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from dao_vang.data.normalization.normalizers import (
    normalize_funding,
    normalize_global_ratio,
    normalize_kline,
    normalize_open_interest,
    normalize_taker_volume,
    normalize_top_ratio,
)
from dao_vang.data.schemas import QualityStatus


def get_base_envelope(payload_json: str, endpoint: str) -> dict[str, str | int]:
    return {
        "collection_run_id": "test_run",
        "request_id": "req-1",
        "provider": "Binance",
        "product": "USD-M Futures",
        "endpoint": endpoint,
        "request_params_json": '{"symbol": "BTCUSDT", "period": "5m"}',
        "requested_at": "2020-09-13T12:26:40+00:00",
        "received_at": "2020-09-13T12:26:41+00:00",
        "http_status": 200,
        "response_hash_sha256": "hash",
        "source_version": "v1_1.0.0",
        "collector_version": "1.0.0",
        "payload_json": payload_json,
    }


def test_normalize_kline() -> None:
    raw = [
        [
            1600000000000,
            "10000.0",
            "10100.0",
            "9900.0",
            "10050.0",
            "10.5",
            1600000299999,
            "100500.0",
            150,
            "5.2",
            "50250.0",
            "0",
        ]
    ]
    envelope = get_base_envelope(json.dumps(raw), "/fapi/v1/klines")
    results = normalize_kline(envelope)

    assert len(results) == 1
    norm = results[0]
    assert norm.symbol == "BTCUSDT"
    assert norm.data_type == "klines"
    assert norm.quality_status == QualityStatus.VALID
    assert norm.open == Decimal("10000.0")
    assert norm.volume_base == Decimal("10.5")
    assert norm.event_time == datetime(
        2020, 9, 13, 12, 31, 39, 999000, tzinfo=timezone.utc
    )


def test_normalize_funding() -> None:
    raw = [
        {
            "symbol": "BTCUSDT",
            "fundingTime": 1600000000000,
            "fundingRate": "0.0001",
            "markPrice": "10000.0",
        }
    ]
    envelope = get_base_envelope(json.dumps(raw), "/fapi/v1/fundingRate")
    envelope["request_params_json"] = '{"symbol": "BTCUSDT"}'
    results = normalize_funding(envelope)

    assert len(results) == 1
    norm = results[0]
    assert norm.symbol == "BTCUSDT"
    assert norm.data_type == "funding"
    assert norm.funding_rate == Decimal("0.0001")


def test_normalize_funding_available_time_is_event_time_not_collected_at() -> None:
    """Regression test: available_time must be event_time-based, not collected_at.

    Historical backfill must not set available_time to collection time — that
    would violate point-in-time (CONSTITUTION §2.4) and break ASOF joins.
    """
    # event_time = 2020-09-13 12:26:40 UTC (fundingTime 1600000000000)
    # collected_at = 2026-08-01 (received_at in envelope, much later)
    raw = [
        {
            "symbol": "BTCUSDT",
            "fundingTime": 1600000000000,
            "fundingRate": "0.0001",
        }
    ]
    envelope = get_base_envelope(json.dumps(raw), "/fapi/v1/fundingRate")
    envelope["request_params_json"] = '{"symbol": "BTCUSDT"}'
    # received_at is 2020-09-13T12:26:41 — close to event_time, normal case
    results = normalize_funding(envelope)
    norm = results[0]
    event_time = datetime(2020, 9, 13, 12, 26, 40, tzinfo=timezone.utc)
    expected_available = event_time + timedelta(milliseconds=1000)
    assert norm.available_time == expected_available
    # available_time must NOT be collected_at (2020-09-13T12:26:41 happens to
    # match here, but the point is it's derived from event_time, not received_at)
    assert norm.event_time == event_time


def test_normalize_open_interest() -> None:
    raw = [
        {
            "symbol": "BTCUSDT",
            "sumOpenInterest": "1000.5",
            "sumOpenInterestValue": "10005000.0",
            "timestamp": 1600000000000,
        }
    ]
    envelope = get_base_envelope(json.dumps(raw), "/futures/data/openInterestHist")
    results = normalize_open_interest(envelope)

    assert len(results) == 1
    norm = results[0]
    assert norm.open_interest_contracts == Decimal("1000.5")


def test_normalize_taker_volume() -> None:
    raw = [
        {
            "buySellRatio": "1.2",
            "buyVol": "120.5",
            "sellVol": "100.4",
            "timestamp": 1600000000000,
        }
    ]
    envelope = get_base_envelope(json.dumps(raw), "/futures/data/takerlongshortRatio")
    results = normalize_taker_volume(envelope)

    assert len(results) == 1
    norm = results[0]
    assert norm.buy_volume == Decimal("120.5")


def test_normalize_global_ratio() -> None:
    raw = [
        {
            "symbol": "BTCUSDT",
            "longShortRatio": "1.5",
            "longAccount": "0.6",
            "shortAccount": "0.4",
            "timestamp": 1600000000000,
        }
    ]
    envelope = get_base_envelope(
        json.dumps(raw), "/futures/data/globalLongShortAccountRatio"
    )
    results = normalize_global_ratio(envelope)

    assert len(results) == 1
    norm = results[0]
    assert norm.long_short_ratio == Decimal("1.5")


def test_normalize_top_ratio() -> None:
    raw = [
        {
            "symbol": "BTCUSDT",
            "longShortRatio": "1.5",
            "longAccount": "0.6",
            "shortAccount": "0.4",
            "timestamp": 1600000000000,
        }
    ]
    envelope = get_base_envelope(
        json.dumps(raw), "/futures/data/topLongShortAccountRatio"
    )
    results = normalize_top_ratio(envelope)

    assert len(results) == 1
    norm = results[0]
    assert norm.population == "top_trader_accounts"


def test_normalize_global_ratio_handles_infinity() -> None:
    raw = [
        {
            "symbol": "BTCUSDT",
            "longShortRatio": "Infinity",
            "longAccount": "1.0",
            "shortAccount": "0.0",
            "timestamp": 1600000000000,
        }
    ]
    envelope = get_base_envelope(
        json.dumps(raw), "/futures/data/globalLongShortAccountRatio"
    )
    results = normalize_global_ratio(envelope)
    assert len(results) == 1
    norm = results[0]
    assert norm.long_short_ratio.is_finite()
    assert norm.long_short_ratio == Decimal("9999.0")
    assert "infinite_long_short_ratio_clamped" in norm.quality_flags

