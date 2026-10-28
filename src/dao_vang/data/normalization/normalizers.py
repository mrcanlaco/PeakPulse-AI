import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from dao_vang.data.schemas import (
    AccountRatioData,
    FundingRateData,
    KlineData,
    NormalizedFunding,
    NormalizedGlobalRatio,
    NormalizedKline,
    NormalizedOpenInterest,
    NormalizedTakerVolume,
    NormalizedTopPositionRatio,
    NormalizedTopRatio,
    OpenInterestData,
    QualityStatus,
    TakerRatioData,
)
from dao_vang.domain.time import system_now


def _safe_ratio_decimal(val: Any) -> tuple[Decimal, list[str]]:
    """Convert ratio value to a finite Decimal, protecting against Infinity/NaN."""
    if val is None:
        return Decimal("1.0"), ["missing_long_short_ratio"]
    try:
        d = Decimal(str(val))
        if not d.is_finite():
            clamped = Decimal("9999.0") if d > 0 else Decimal("0.0")
            return clamped, ["infinite_long_short_ratio_clamped"]
        return d, []
    except Exception:
        return Decimal("1.0"), ["invalid_long_short_ratio"]


def normalize_kline(
    envelope: dict[str, Any], dataset_version: str = "1.0.0"
) -> list[NormalizedKline]:
    payload = json.loads(envelope["payload_json"])
    results: list[NormalizedKline] = []

    collected_at = datetime.fromisoformat(envelope["received_at"])
    source_version = envelope["source_version"]
    params = json.loads(envelope["request_params_json"])
    symbol = params.get("symbol", "BTCUSDT")
    interval = params.get("period", "5m")

    for item in payload:
        raw = KlineData.from_raw_list(item)
        event_time = raw.close_time
        available_time = event_time + timedelta(milliseconds=1000)

        norm = NormalizedKline(
            symbol=symbol,
            market="USD-M Futures",
            data_type="klines",
            interval=interval,
            event_time=event_time,
            available_time=available_time,
            collected_at=collected_at,
            source_version=source_version,
            dataset_version=dataset_version,
            quality_status=QualityStatus.VALID,
            quality_flags=[],
            open_time=raw.open_time,
            close_time=raw.close_time,
            open=Decimal(str(raw.open_price)),
            high=Decimal(str(raw.high_price)),
            low=Decimal(str(raw.low_price)),
            close=Decimal(str(raw.close_price)),
            volume_base=Decimal(str(raw.volume)),
            volume_quote=Decimal(str(raw.quote_volume)),
            trade_count=raw.trades,
            taker_buy_base=Decimal(str(raw.taker_buy_volume)),
            taker_buy_quote=Decimal(str(raw.taker_buy_quote_volume)),
        )
        results.append(norm)
    return results


def normalize_funding(
    envelope: dict[str, Any], dataset_version: str = "1.0.0"
) -> list[NormalizedFunding]:
    payload = json.loads(envelope["payload_json"])
    results: list[NormalizedFunding] = []

    collected_at = datetime.fromisoformat(envelope["received_at"])
    source_version = envelope["source_version"]

    for item in payload:
        raw = FundingRateData.model_validate(item)
        event_time = raw.funding_time
        # Funding rate is published at event_time; available_time must reflect
        # when the data became known, NOT when we collected it. Using collected_at
        # for historical backfill would violate point-in-time (CONSTITUTION §2.4).
        available_time = event_time + timedelta(milliseconds=1000)

        norm = NormalizedFunding(
            symbol=raw.symbol,
            market="USD-M Futures",
            data_type="funding",
            interval=None,
            event_time=event_time,
            available_time=available_time,
            collected_at=collected_at,
            source_version=source_version,
            dataset_version=dataset_version,
            quality_status=QualityStatus.VALID,
            quality_flags=[],
            funding_time=raw.funding_time,
            funding_rate=Decimal(str(raw.funding_rate)),
            mark_price=Decimal(str(raw.mark_price))
            if raw.mark_price is not None
            else None,
        )
        results.append(norm)
    return results


def normalize_open_interest(
    envelope: dict[str, Any], dataset_version: str = "1.0.0"
) -> list[NormalizedOpenInterest]:
    payload = json.loads(envelope["payload_json"])
    results: list[NormalizedOpenInterest] = []

    collected_at = datetime.fromisoformat(envelope["received_at"])
    source_version = envelope["source_version"]
    params = json.loads(envelope["request_params_json"])
    interval = params.get("period", "5m")

    # 5m = 300 seconds
    interval_delta = timedelta(minutes=5)

    for item in payload:
        raw = OpenInterestData.model_validate(item)
        period_start = raw.timestamp
        period_end = period_start + interval_delta
        event_time = period_start
        available_time = period_end + timedelta(milliseconds=1000)

        norm = NormalizedOpenInterest(
            symbol=raw.symbol,
            market="USD-M Futures",
            data_type="open_interest",
            interval=interval,
            event_time=event_time,
            available_time=available_time,
            collected_at=collected_at,
            source_version=source_version,
            dataset_version=dataset_version,
            quality_status=QualityStatus.VALID,
            quality_flags=[],
            period_start=period_start,
            period_end=period_end,
            open_interest_contracts=Decimal(str(raw.sum_open_interest)),
            open_interest_value=Decimal(str(raw.sum_open_interest_value)),
        )
        results.append(norm)
    return results


def normalize_taker_volume(
    envelope: dict[str, Any], dataset_version: str = "1.0.0"
) -> list[NormalizedTakerVolume]:
    payload = json.loads(envelope["payload_json"])
    results: list[NormalizedTakerVolume] = []

    collected_at = datetime.fromisoformat(envelope["received_at"])
    source_version = envelope["source_version"]
    params = json.loads(envelope["request_params_json"])
    symbol = params.get("symbol", "BTCUSDT")
    interval = params.get("period", "5m")

    interval_delta = timedelta(minutes=5)

    for item in payload:
        raw = TakerRatioData.model_validate(item)
        period_start = raw.timestamp
        period_end = period_start + interval_delta
        event_time = period_start
        available_time = period_end + timedelta(milliseconds=1000)

        norm = NormalizedTakerVolume(
            symbol=symbol,
            market="USD-M Futures",
            data_type="taker_volume",
            interval=interval,
            event_time=event_time,
            available_time=available_time,
            collected_at=collected_at,
            source_version=source_version,
            dataset_version=dataset_version,
            quality_status=QualityStatus.VALID,
            quality_flags=[],
            period_start=period_start,
            period_end=period_end,
            buy_volume=Decimal(str(raw.buy_vol)),
            sell_volume=Decimal(str(raw.sell_vol)),
            buy_sell_ratio=Decimal(str(raw.buy_sell_ratio)),
        )
        results.append(norm)
    return results


def normalize_global_ratio(
    envelope: dict[str, Any], dataset_version: str = "1.0.0"
) -> list[NormalizedGlobalRatio]:
    payload = json.loads(envelope["payload_json"])
    results: list[NormalizedGlobalRatio] = []

    collected_at = datetime.fromisoformat(envelope["received_at"])
    source_version = envelope["source_version"]
    params = json.loads(envelope["request_params_json"])
    interval = params.get("period", "5m")

    interval_delta = timedelta(minutes=5)

    for item in payload:
        raw = AccountRatioData.model_validate(item)
        period_start = raw.timestamp
        period_end = period_start + interval_delta
        event_time = period_start
        available_time = period_end + timedelta(milliseconds=1000)

        norm = NormalizedGlobalRatio(
            symbol=raw.symbol,
            market="USD-M Futures",
            data_type="global_ratio",
            interval=interval,
            event_time=event_time,
            available_time=available_time,
            collected_at=collected_at,
            source_version=source_version,
            dataset_version=dataset_version,
            quality_status=QualityStatus.VALID,
            quality_flags=list(_safe_ratio_decimal(raw.long_short_ratio)[1]),
            period_start=period_start,
            period_end=period_end,
            long_account=Decimal(str(raw.long_account)),
            short_account=Decimal(str(raw.short_account)),
            long_short_ratio=_safe_ratio_decimal(raw.long_short_ratio)[0],
        )
        results.append(norm)
    return results


def normalize_top_ratio(
    envelope: dict[str, Any], dataset_version: str = "1.0.0"
) -> list[NormalizedTopRatio]:
    payload = json.loads(envelope["payload_json"])
    results: list[NormalizedTopRatio] = []

    collected_at = datetime.fromisoformat(envelope["received_at"])
    source_version = envelope["source_version"]
    params = json.loads(envelope["request_params_json"])
    interval = params.get("period", "5m")

    interval_delta = timedelta(minutes=5)

    for item in payload:
        raw = AccountRatioData.model_validate(item)
        period_start = raw.timestamp
        period_end = period_start + interval_delta
        event_time = period_start
        available_time = period_end + timedelta(milliseconds=1000)

        norm = NormalizedTopRatio(
            symbol=raw.symbol,
            market="USD-M Futures",
            data_type="top_ratio",
            interval=interval,
            event_time=event_time,
            available_time=available_time,
            collected_at=collected_at,
            source_version=source_version,
            dataset_version=dataset_version,
            quality_status=QualityStatus.VALID,
            quality_flags=list(_safe_ratio_decimal(raw.long_short_ratio)[1]),
            period_start=period_start,
            period_end=period_end,
            long_account=Decimal(str(raw.long_account)),
            short_account=Decimal(str(raw.short_account)),
            long_short_ratio=_safe_ratio_decimal(raw.long_short_ratio)[0],
        )
        results.append(norm)
    return results


def normalize_top_position_ratio(
    envelope_or_payloads: dict[str, Any] | list[dict[str, Any]],
    dataset_version: str = "1.0.0",
) -> list[NormalizedTopPositionRatio]:
    """Normalize Binance top-trader *position* ratio records.

    The collector writes the same envelope format as the other ratio
    collectors.  The previous implementation accepted a bare payload list,
    referenced an undefined timestamp helper and did not populate the
    required :class:`NormalizedBase` fields, so it could never be used by the
    pipeline.  Keep support for a bare list for callers doing small replays,
    while making the envelope form the canonical path.
    """
    if isinstance(envelope_or_payloads, dict):
        envelope = envelope_or_payloads
        payload = json.loads(envelope["payload_json"])
        collected_at = datetime.fromisoformat(envelope["received_at"])
        source_version = str(envelope.get("source_version", "unknown"))
        params = json.loads(envelope.get("request_params_json", "{}"))
        symbol_default = params.get("symbol", "BTCUSDT")
        interval = params.get("period", "5m")
    else:
        # Backward-compatible replay API: a list of payload dictionaries.
        payload = envelope_or_payloads
        collected_at = system_now()
        source_version = "unknown"
        symbol_default = "BTCUSDT"
        interval = "5m"
        # The legacy two-argument form used the second argument as a run id,
        # not a dataset version.  Run ids are not part of NormalizedBase, so
        # retain the canonical default dataset version for that form.
        dataset_version = "1.0.0"

    if not isinstance(payload, list):
        raise ValueError("top position ratio payload must be a list")

    results: list[NormalizedTopPositionRatio] = []
    interval_delta = timedelta(minutes=5)
    for item in payload:
        ts_raw = item.get("timestamp")
        if isinstance(ts_raw, datetime):
            dt = ts_raw if ts_raw.tzinfo else ts_raw.replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromtimestamp(int(ts_raw) / 1000.0, tz=timezone.utc)
        period_end = dt + interval_delta
        long_position = item.get("longPosition")
        short_position = item.get("shortPosition")
        ratio = item.get("longShortRatio")
        if ratio is None and long_position is not None and short_position not in (None, 0, "0"):
            ratio = Decimal(str(long_position)) / Decimal(str(short_position))
        if ratio is None:
            raise ValueError("top position ratio record is missing longShortRatio")

        norm = NormalizedTopPositionRatio(
            symbol=str(item.get("symbol", symbol_default)),
            market="USD-M Futures",
            data_type="top_position_ratio",
            interval=interval,
            event_time=dt,
            available_time=period_end + timedelta(milliseconds=1000),
            collected_at=collected_at,
            source_version=source_version,
            dataset_version=dataset_version,
            quality_status=QualityStatus.VALID,
            quality_flags=list(_safe_ratio_decimal(ratio)[1]),
            period_start=dt,
            period_end=period_end,
            long_position=Decimal(str(long_position)) if long_position is not None else None,
            short_position=Decimal(str(short_position)) if short_position is not None else None,
            long_short_ratio=_safe_ratio_decimal(ratio)[0],
        )
        results.append(norm)
    return results
