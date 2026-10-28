"""Run the finite, pre-registered open-profit search.

This is a research-only runner for OPEN_PROFIT_BATCH_01. It freezes and
hashes the registry before opening any market outcome data, builds the five
registered opportunity families from the pre-outcome cohort, and evaluates
the fixed 120-trial grid through open_profit_account. Price, funding and
liquidation are explicitly provisional proxy inputs; this script never
submits orders or calls a network service.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
DEFAULT_REGISTRY = REPO_ROOT / "docs/OPEN_PROFIT_BATCH_01_20260916.md"
DEFAULT_SOURCE = REPO_ROOT / "artifacts/v3_six_month_20260915/cohort_pre_outcome.csv"
DEFAULT_MARKET_DB = Path(r"D:\Quant-trading\data_lake\quant_master.duckdb")
DEFAULT_OUTPUT = REPO_ROOT / "artifacts/open_profit_20260916/search_results.json"
DEFAULT_REPORT = REPO_ROOT / "docs/OPEN_PROFIT_SEARCH_20260916.md"

UTC = timezone.utc
WINDOW_START = datetime(2026, 2, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 8, 1, tzinfo=UTC)
BAR_STEP = timedelta(minutes=5)
COOLDOWN = timedelta(hours=24)
MAINTENANCE_RATIO = 0.01
FUNDING_STRESS_BPS = 10.0
FUNDING_INTERVAL_HOURS = 8.0
INITIAL_CAPITAL = 10_000.0
TRANCHE_COUNT = 10
TRANCHE_SEED = INITIAL_CAPITAL / TRANCHE_COUNT
HORIZONS_HOURS = (12, 48, 168)
LEVERAGES = (1, 2, 5, 10)
COST_BPS = (20, 60)
FAMILIES = (
    "momentum_long",
    "exhaustion_short",
    "funding_fade_short",
    "regime_switch",
    "hedged_fade",
)
STABLECOINS = {
    "BUSDUSDT",
    "DAIUSDT",
    "EURUSDT",
    "FDUSDUSDT",
    "TUSDUSDT",
    "USDCUSDT",
    "USDEUSDT",
    "USDPUSDT",
    "USTCUSDT",
}


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class FundingPoint:
    timestamp: datetime
    rate: float
    mark_price: float | None


@dataclass(frozen=True)
class PricePath:
    symbol: str
    direction: str
    signal_time: datetime
    entry_time: datetime
    scheduled_end: datetime
    effective_end: datetime
    status: str
    reason: str | None
    entry_price: float | None
    exit_price: float | None
    bars: tuple[Bar, ...]
    funding: tuple[FundingPoint, ...]
    expected_bars: int
    observed_bars: int
    first_missing_bar: datetime | None
    funding_missing: bool
    funding_expected: int
    funding_observed: int


@dataclass(frozen=True)
class TrialSpec:
    family: str
    horizon_hours: int
    leverage: int
    cost_bps: int

    @property
    def trial_id(self) -> str:
        return f"{self.family}__h{self.horizon_hours}__l{self.leverage}__c{self.cost_bps}"


def _utc(value: Any) -> datetime:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return stamp.tz_convert("UTC").to_pydatetime()


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, pd.Timestamp)):
        return _utc(value).isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _path_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _registry_provenance(registry: Path, source: Path) -> dict[str, Any]:
    """Require the frozen registry before any outcome-path read."""
    if not registry.is_file():
        raise FileNotFoundError(f"frozen registry is required: {registry}")
    text = registry.read_text(encoding="utf-8")
    required_markers = (
        "120 cấu hình cố định",
        "Làm rõ trước kết quả",
        "withdraw_profits=False",
        "Funding vắng mặt được giả định bằng 0",
    )
    missing = [marker for marker in required_markers if marker not in text]
    if missing:
        raise RuntimeError(f"registry is not final/frozen; missing markers: {missing}")
    if not source.is_file():
        raise FileNotFoundError(f"pre-outcome source is required: {source}")
    mtime = datetime.fromtimestamp(registry.stat().st_mtime, tz=UTC)
    return {
        "registry_path": _path_label(registry),
        "registry_sha256": _sha256(registry),
        "registry_mtime_utc": mtime.isoformat(),
        "source_path": _path_label(source),
        "source_sha256": _sha256(source),
        "frozen_before_outcomes": True,
        "required_markers": list(required_markers),
    }


def _load_source(source: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = pd.read_csv(source)
    required = {
        "feature_time",
        "symbol",
        "price_ret_24h",
        "distance_from_high_24h",
        "funding_percentile_30d",
        "funding_change_8h",
        "funding_persistence_7d",
        "price_ret_1h",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"cohort source is missing columns: {missing}")
    frame.insert(0, "source_row_number", range(1, len(frame) + 1))
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
    frame["symbol"] = frame["symbol"].astype(str)
    for column in (
        "price_ret_24h",
        "distance_from_high_24h",
        "funding_percentile_30d",
        "funding_change_8h",
        "funding_persistence_7d",
        "price_ret_1h",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    in_window = frame["feature_time"].between(
        pd.Timestamp(WINDOW_START), pd.Timestamp(WINDOW_END), inclusive="left"
    )
    nonstable = ~frame["symbol"].isin(STABLECOINS)
    pump = frame["price_ret_24h"].ge(0.15)
    candidates = frame.loc[in_window & nonstable & pump].copy()
    candidates["signal_time"] = candidates["feature_time"] + pd.Timedelta(milliseconds=1)
    candidates = candidates.sort_values(
        ["feature_time", "price_ret_24h", "symbol", "source_row_number"],
        ascending=[True, False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    source_meta = {
        "source_rows": int(len(frame)),
        "source_symbols": int(frame["symbol"].nunique()),
        "window_rows": int(in_window.sum()),
        "nonstable_pump_rows": int(len(candidates)),
        "candidate_symbols": int(candidates["symbol"].nunique()),
        "window_start_utc": WINDOW_START.isoformat(),
        "window_end_utc": WINDOW_END.isoformat(),
    }
    return candidates, source_meta


def _has(frame: pd.DataFrame, column: str, op: str, value: float) -> pd.Series:
    values = pd.to_numeric(frame[column], errors="coerce")
    if op == "gt":
        return values.gt(value).fillna(False)
    if op == "ge":
        return values.ge(value).fillna(False)
    if op == "le":
        return values.le(value).fillna(False)
    if op == "lt":
        return values.lt(value).fillna(False)
    raise ValueError(op)


def _cooldown_select(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply the registered 24-hour same-symbol gate before outcomes."""
    if frame.empty:
        return frame.copy()
    ordered = frame.sort_values(
        ["feature_time", "price_ret_24h", "symbol", "source_row_number"],
        ascending=[True, False, True, True],
        kind="mergesort",
    )
    last_signal: dict[str, datetime] = {}
    kept: list[int] = []
    for index, row in ordered.iterrows():
        symbol = str(row["symbol"])
        signal = _utc(row["signal_time"])
        previous = last_signal.get(symbol)
        if previous is not None and signal - previous < COOLDOWN:
            continue
        kept.append(index)
        last_signal[symbol] = signal
    return ordered.loc[kept].sort_values(
        ["feature_time", "price_ret_24h", "symbol", "source_row_number"],
        ascending=[True, False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)


def _family_candidates(frame: pd.DataFrame) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    exhaustion = (
        _has(frame, "price_ret_24h", "ge", 0.25)
        & _has(frame, "distance_from_high_24h", "le", -0.02)
        & _has(frame, "price_ret_1h", "lt", 0.0)
    )
    family_frames: dict[str, pd.DataFrame] = {
        "momentum_long": frame.loc[_has(frame, "price_ret_1h", "gt", 0.0)].copy(),
        "exhaustion_short": frame.loc[exhaustion].copy(),
        "funding_fade_short": frame.loc[
            exhaustion
            & _has(frame, "funding_percentile_30d", "ge", 0.8)
            & _has(frame, "funding_change_8h", "gt", 0.0)
            & _has(frame, "funding_persistence_7d", "gt", 0.0)
        ].copy(),
        "regime_switch": frame.loc[
            _has(frame, "price_ret_24h", "ge", 0.25)
            & (
                (
                    _has(frame, "distance_from_high_24h", "le", -0.02)
                    & _has(frame, "price_ret_1h", "lt", 0.0)
                )
                | _has(frame, "price_ret_1h", "gt", 0.0)
            )
        ].copy(),
        "hedged_fade": frame.loc[exhaustion & ~frame["symbol"].eq("BTCUSDT")].copy(),
    }
    all_candidates: dict[str, list[dict[str, Any]]] = {}
    counts: dict[str, dict[str, int]] = {}
    for family in FAMILIES:
        selected = _cooldown_select(family_frames[family])
        family_records: list[dict[str, Any]] = []
        for _, row in selected.iterrows():
            if family == "momentum_long":
                direction = "long"
            elif family in {"exhaustion_short", "funding_fade_short"}:
                direction = "short"
            elif family == "hedged_fade":
                direction = "hedge"
            elif (
                float(row["distance_from_high_24h"]) <= -0.02
                and float(row["price_ret_1h"]) < 0.0
            ):
                direction = "short"
            elif float(row["price_ret_1h"]) > 0.0:
                direction = "long"
            else:
                direction = "flat"
            if direction == "flat":
                continue
            signal = _utc(row["signal_time"])
            symbol = str(row["symbol"])
            family_records.append(
                {
                    "candidate_id": (
                        f"{family}:{symbol}:{signal.isoformat()}:"
                        f"r{int(row['source_row_number'])}"
                    ),
                    "source_row_number": int(row["source_row_number"]),
                    "family": family,
                    "symbol": symbol,
                    "direction": direction,
                    "signal_time": signal,
                    "feature_time": _utc(row["feature_time"]),
                    "episode_id": str(row.get("episode_id", "")),
                    "price_ret_24h": _finite(row["price_ret_24h"]),
                    "distance_from_high_24h": _finite(row["distance_from_high_24h"]),
                    "price_ret_1h": _finite(row["price_ret_1h"]),
                    "funding_percentile_30d": _finite(row["funding_percentile_30d"]),
                    "funding_change_8h": _finite(row["funding_change_8h"]),
                    "funding_persistence_7d": _finite(row["funding_persistence_7d"]),
                    "market_four": bool(row.get("market_four", False)),
                }
            )
        all_candidates[family] = family_records
        counts[family] = {
            "raw_pre_cooldown": int(len(family_frames[family])),
            "selected_after_24h_cooldown": int(len(family_records)),
            "selected_symbols": len({item["symbol"] for item in family_records}),
        }
    return all_candidates, counts


def _expected_times(entry_time: datetime, end_time: datetime) -> list[datetime]:
    if end_time <= entry_time:
        return []
    seconds = (end_time - entry_time).total_seconds()
    count = int(round(seconds / BAR_STEP.total_seconds()))
    if count <= 0 or not math.isclose(
        seconds, count * BAR_STEP.total_seconds(), abs_tol=0.001
    ):
        raise ValueError(f"non-5m-aligned path: {entry_time} -> {end_time}")
    return [entry_time + i * BAR_STEP for i in range(count)]


def _funding_schedule(entry_time: datetime, end_time: datetime) -> list[datetime]:
    """Return the registered UTC 8-hour settlement boundaries."""
    first_day = entry_time.replace(hour=0, minute=0, second=0, microsecond=0)
    candidate = first_day
    while candidate <= entry_time:
        candidate += timedelta(hours=int(FUNDING_INTERVAL_HOURS))
    expected: list[datetime] = []
    while candidate <= end_time:
        expected.append(candidate)
        candidate += timedelta(hours=int(FUNDING_INTERVAL_HOURS))
    return expected


def _funding_coverage(
    entry_time: datetime,
    end_time: datetime,
    funding: Iterable[FundingPoint],
) -> tuple[bool, int, int]:
    expected = _funding_schedule(entry_time, end_time)
    actual = [item.timestamp for item in funding if entry_time < item.timestamp <= end_time]
    matched = 0
    for target in expected:
        if any(abs((point - target).total_seconds()) <= 60 for point in actual):
            matched += 1
    return matched < len(expected), len(expected), len(actual)


def _build_path(
    symbol: str,
    direction: str,
    signal_time: datetime,
    scheduled_end: datetime,
    bars: dict[datetime, Bar],
    funding: tuple[FundingPoint, ...],
) -> PricePath:
    entry_time = signal_time
    effective_end = min(scheduled_end, WINDOW_END)
    entry = bars.get(entry_time)
    if entry is None:
        return PricePath(
            symbol,
            direction,
            signal_time,
            entry_time,
            scheduled_end,
            effective_end,
            "rejected_at_entry",
            "missing_entry_bar",
            None,
            None,
            (),
            (),
            0,
            0,
            entry_time,
            *_funding_coverage(entry_time, effective_end, ()),
        )
    expected = _expected_times(entry_time, effective_end)
    missing = next((timestamp for timestamp in expected if timestamp not in bars), None)
    observed_times = [timestamp for timestamp in expected if timestamp in bars]
    observed_bars = tuple(bars[timestamp] for timestamp in observed_times)
    relevant_funding = tuple(
        item for item in funding if entry_time < item.timestamp <= effective_end
    )
    funding_missing, funding_expected, funding_observed = _funding_coverage(
        entry_time, effective_end, relevant_funding
    )
    if missing is not None:
        return PricePath(
            symbol,
            direction,
            signal_time,
            entry_time,
            scheduled_end,
            effective_end,
            "unresolved",
            "missing_future_bar",
            entry.open,
            None,
            observed_bars,
            relevant_funding,
            len(expected),
            len(observed_bars),
            missing,
            funding_missing,
            funding_expected,
            funding_observed,
        )
    exit_bar = observed_bars[-1]
    status = "open_at_cutoff" if scheduled_end > WINDOW_END else "time_exit"
    return PricePath(
        symbol,
        direction,
        signal_time,
        entry_time,
        scheduled_end,
        effective_end,
        status,
        None,
        entry.open,
        exit_bar.close,
        observed_bars,
        relevant_funding,
        len(expected),
        len(observed_bars),
        None,
        funding_missing,
        funding_expected,
        funding_observed,
    )


class MarketReader:
    """Read one local Parquet file per symbol through an in-memory DuckDB."""

    def __init__(self, market_db: Path) -> None:
        import duckdb

        root = market_db.parent
        self.price_root = root / "klines" / "5m"
        self.funding_root = root / "funding"
        self.conn = duckdb.connect(":memory:")
        self.conn.execute("SET memory_limit='512MB'")
        self.conn.execute("SET threads=2")

    def close(self) -> None:
        self.conn.close()

    def _query(
        self, path: Path, columns: str, time_column: str, start: datetime, end: datetime
    ) -> list[tuple[Any, ...]]:
        if not path.is_file():
            return []
        return self.conn.execute(
            f"""
            SELECT {columns}
            FROM read_parquet(?)
            WHERE {time_column} >= ? AND {time_column} < ?
            ORDER BY {time_column}
            """,
            [str(path), start, end],
        ).fetchall()

    def read_symbol(
        self, symbol: str
    ) -> tuple[dict[datetime, Bar], tuple[FundingPoint, ...], dict[str, Any]]:
        price_path = self.price_root / f"{symbol}.parquet"
        funding_path = self.funding_root / f"{symbol}_funding.parquet"
        price_rows = self._query(
            price_path,
            "open_time, open, high, low, close",
            "open_time",
            WINDOW_START - BAR_STEP,
            WINDOW_END,
        )
        bars: dict[datetime, Bar] = {}
        invalid_bars = 0
        for timestamp, open_price, high, low, close in price_rows:
            try:
                bar = Bar(
                    _utc(timestamp),
                    float(open_price),
                    float(high),
                    float(low),
                    float(close),
                )
                if (
                    not all(
                        math.isfinite(value)
                        for value in (bar.open, bar.high, bar.low, bar.close)
                    )
                    or min(bar.open, bar.high, bar.low, bar.close) <= 0
                    or bar.high < max(bar.open, bar.close)
                    or bar.low > min(bar.open, bar.close)
                ):
                    raise ValueError("invalid OHLC")
            except (TypeError, ValueError, OverflowError):
                invalid_bars += 1
                continue
            bars.setdefault(bar.timestamp, bar)
        funding_rows = self._query(
            funding_path,
            "funding_time, funding_rate, mark_price",
            "funding_time",
            WINDOW_START - timedelta(hours=8),
            WINDOW_END + timedelta(milliseconds=1),
        )
        funding_map: dict[datetime, FundingPoint] = {}
        invalid_funding = 0
        for timestamp, rate, mark in funding_rows:
            try:
                rate_value = float(rate)
                mark_value = _finite(mark)
                point = FundingPoint(_utc(timestamp), rate_value, mark_value)
                if not math.isfinite(rate_value):
                    raise ValueError("invalid funding rate")
                funding_map.setdefault(point.timestamp, point)
            except (TypeError, ValueError, OverflowError):
                invalid_funding += 1
        meta = {
            "symbol": symbol,
            "price_path": str(price_path),
            "price_exists": price_path.is_file(),
            "funding_path": str(funding_path),
            "funding_exists": funding_path.is_file(),
            "price_source_rows": len(price_rows),
            "price_valid_rows": len(bars),
            "price_invalid_rows": invalid_bars,
            "funding_source_rows": len(funding_rows),
            "funding_valid_rows": len(funding_map),
            "funding_invalid_rows": invalid_funding,
        }
        return bars, tuple(funding_map[key] for key in sorted(funding_map)), meta


def _funding_ratio(
    point: FundingPoint, path: PricePath, entry_price: float
) -> tuple[float, str]:
    if point.mark_price is not None and point.mark_price > 0:
        return point.mark_price / entry_price, "settlement_mark"
    following = next(
        (bar for bar in path.bars if bar.timestamp >= point.timestamp), None
    )
    if following is not None and following.open > 0:
        return following.open / entry_price, "following_bar_open_proxy"
    previous = next(
        (bar for bar in reversed(path.bars) if bar.timestamp < point.timestamp), None
    )
    if previous is not None and previous.close > 0:
        return previous.close / entry_price, "previous_bar_close_proxy"
    return 1.0, "entry_price_fallback_proxy"


def _scenario_leg(
    path: PricePath,
    leverage: int,
    cost_bps: int,
    funding_stress: bool = False,
) -> dict[str, Any]:
    base = {
        "symbol": path.symbol,
        "direction": path.direction,
        "status": path.status,
        "reason": path.reason,
        "signal_time": path.signal_time,
        "scheduled_end": path.scheduled_end,
        "entry_price": path.entry_price,
        "exit_price": path.exit_price,
        "expected_bars": path.expected_bars,
        "observed_bars": path.observed_bars,
        "first_missing_bar": path.first_missing_bar,
        "funding_missing": path.funding_missing,
        "funding_expected": path.funding_expected,
        "funding_observed": path.funding_observed,
        "funding_rate_sum": sum(item.rate for item in path.funding),
        "funding_coverage_attested": False,
        "funding_8h_cadence_heuristic": True,
        "funding_mark_proxy_count": 0,
        "funding_unpriced_count": 0,
        "funding_stress_applied": funding_stress,
        "leverage": leverage,
        "cost_bps_roundtrip": cost_bps,
        "terminal_status": path.status,
        "exit_time": path.effective_end,
        "net_return_on_margin": None,
        "liquidation_proxy": False,
    }
    if path.status in {"rejected_at_entry", "unresolved"}:
        return base
    if path.entry_price is None or path.exit_price is None or not path.bars:
        base["status"] = "unresolved"
        base["terminal_status"] = "unresolved"
        base["reason"] = "missing_entry_or_exit_price"
        return base

    sign = 1.0 if path.direction == "long" else -1.0
    entry_price = float(path.entry_price)
    side_bps = cost_bps / 2.0
    entry_fee = (side_bps / 10_000.0) * leverage
    observed_by_bar: dict[datetime, float] = defaultdict(float)
    observed_final = 0.0
    stress_by_bar: dict[datetime, float] = defaultdict(float)
    stress_final = 0.0
    mark_proxy_count = 0
    unpriced_count = 0

    for point in path.funding:
        ratio, source = _funding_ratio(point, path, entry_price)
        if source == "settlement_mark":
            mark_proxy_count += 1
        else:
            unpriced_count += 1
        amount = -sign * ratio * point.rate * leverage
        following = next(
            (bar for bar in path.bars if bar.timestamp >= point.timestamp), None
        )
        if following is None:
            observed_final += amount
        else:
            observed_by_bar[following.timestamp] += amount

    if funding_stress:
        for timestamp in _funding_schedule(path.entry_time, path.effective_end):
            following = next(
                (bar for bar in path.bars if bar.timestamp >= timestamp), None
            )
            if following is not None:
                ratio = following.open / entry_price
                amount = -(FUNDING_STRESS_BPS / 10_000.0) * ratio * leverage
                stress_by_bar[following.timestamp] += amount
            else:
                previous = next(
                    (bar for bar in reversed(path.bars) if bar.timestamp < timestamp),
                    None,
                )
                ratio = previous.close / entry_price if previous is not None else 1.0
                stress_final -= (
                    FUNDING_STRESS_BPS / 10_000.0
                ) * ratio * leverage

    running_observed = 0.0
    running_stress = 0.0
    liquidation: Bar | None = None
    for bar in path.bars:
        # Settlement/stress at this bar's boundary is charged before this
        # bar's OHLC extremum is observed, never to the prior bar.
        running_observed += observed_by_bar.get(bar.timestamp, 0.0)
        running_stress += stress_by_bar.get(bar.timestamp, 0.0)
        adverse = bar.low if sign > 0 else bar.high
        unrealized = sign * ((adverse / entry_price) - 1.0) * leverage
        exit_fee = (side_bps / 10_000.0) * (adverse / entry_price) * leverage
        equity = 1.0 + unrealized + running_observed + running_stress
        equity -= entry_fee + exit_fee
        maintenance = MAINTENANCE_RATIO * (adverse / entry_price) * leverage
        if equity <= maintenance:
            liquidation = bar
            break
    if liquidation is not None:
        adverse = liquidation.low if sign > 0 else liquidation.high
        base.update(
            {
                "status": "liquidated_proxy",
                "terminal_status": "liquidated_proxy",
                "exit_time": liquidation.timestamp + BAR_STEP,
                "exit_price": adverse,
                "net_return_on_margin": -1.0,
                "liquidation_proxy": True,
                "gross_price_return_on_margin": sign
                * ((adverse / entry_price) - 1.0)
                * leverage,
                "observed_funding_return_on_margin": running_observed,
                "funding_stress_return_on_margin": running_stress,
                "fee_return_on_margin": entry_fee + exit_fee,
                "funding_mark_proxy_count": mark_proxy_count,
                "funding_unpriced_count": unpriced_count,
            }
        )
        return base

    observed_total = running_observed + observed_final
    stress_total = running_stress + stress_final
    price_return = sign * ((float(path.exit_price) / entry_price) - 1.0) * leverage
    # An open-at-cutoff MTM has no exit fee because it has not closed.
    exit_fee = (
        (side_bps / 10_000.0)
        * (float(path.exit_price) / entry_price)
        * leverage
        if path.status != "open_at_cutoff"
        else 0.0
    )
    final_equity = (
        1.0
        + price_return
        + observed_total
        + stress_total
        - entry_fee
        - exit_fee
    )
    final_maintenance = (
        MAINTENANCE_RATIO
        * (float(path.exit_price) / entry_price)
        * leverage
    )
    # A settlement exactly at the terminal boundary is observed before the
    # account is marked. It can trigger the proxy at the cutoff even though
    # there is no following OHLC bar to inspect.
    if final_equity <= final_maintenance + 1e-12:
        base.update(
            {
                "status": "liquidated_proxy",
                "terminal_status": "liquidated_proxy",
                "exit_time": path.effective_end,
                "net_return_on_margin": -1.0,
                "liquidation_proxy": True,
                "gross_price_return_on_margin": price_return,
                "observed_funding_return_on_margin": observed_total,
                "funding_stress_return_on_margin": stress_total,
                "fee_return_on_margin": entry_fee + exit_fee,
                "funding_mark_proxy_count": mark_proxy_count,
                "funding_unpriced_count": unpriced_count,
            }
        )
        return base
    fee_return = entry_fee + exit_fee
    base.update(
        {
            "net_return_on_margin": price_return + observed_total + stress_total - fee_return,
            "gross_price_return_on_margin": price_return,
            "observed_funding_return_on_margin": observed_total,
            "fee_return_on_margin": fee_return,
            "funding_stress_return_on_margin": stress_total,
            "funding_mark_proxy_count": mark_proxy_count,
            "funding_unpriced_count": unpriced_count,
        }
    )
    return base


def _load_account_api() -> tuple[Any, Any]:
    try:
        module = importlib.import_module("dao_vang.experiments.open_profit_account")
    except ImportError as exc:
        raise RuntimeError(
            "account backend missing: expected dao_vang.experiments.open_profit_account"
        ) from exc
    try:
        return module.CandidateTrade, module.simulate_account
    except AttributeError as exc:
        raise RuntimeError("account backend lacks CandidateTrade/simulate_account") from exc


def _make_trade(
    candidate_trade: Any,
    item: dict[str, Any],
    net_return: float | None,
    status: str,
) -> Any:
    return candidate_trade(
        signal_time=item["entry_time"],
        exit_time=item["exit_time"],
        symbol=item["symbol"],
        net_return_on_margin=net_return,
        terminal_status=status,
        candidate_id=item["candidate_id"],
    )


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, (datetime, pd.Timestamp)):
        return _utc(value).isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def _account_metric(account: Any, *names: str) -> float | None:
    if not isinstance(account, dict):
        return None
    for name in names:
        value = _finite(account.get(name))
        if value is not None:
            return value
    return None


def _path_for(
    opportunity: dict[str, Any],
    horizon_hours: int,
    paths: dict[tuple[str, datetime, str, int], PricePath],
) -> tuple[PricePath, PricePath | None]:
    key = (
        opportunity["symbol"],
        opportunity["signal_time"],
        "short" if opportunity["direction"] == "hedge" else opportunity["direction"],
        horizon_hours,
    )
    coin = paths[key]
    if opportunity["direction"] != "hedge":
        return coin, None
    btc_key = ("BTCUSDT", opportunity["signal_time"], "long", horizon_hours)
    return coin, paths[btc_key]


def _build_trial_trades(
    spec: TrialSpec,
    opportunities: list[dict[str, Any]],
    paths: dict[tuple[str, datetime, str, int], PricePath],
    candidate_trade: Any,
    funding_stress: bool = False,
) -> tuple[list[Any], list[dict[str, Any]]]:
    trades: list[Any] = []
    details: list[dict[str, Any]] = []
    ordered_opportunities = sorted(
        opportunities,
        key=lambda item: (
            item["signal_time"],
            -(item["price_ret_24h"] or float("-inf")),
            item["symbol"],
            item["candidate_id"],
        ),
    )
    for opportunity in ordered_opportunities:
        coin_path, btc_path = _path_for(opportunity, spec.horizon_hours, paths)
        coin = _scenario_leg(coin_path, spec.leverage, spec.cost_bps, funding_stress)
        legs = [coin]
        if btc_path is not None:
            legs.append(_scenario_leg(btc_path, spec.leverage, spec.cost_bps, funding_stress))
        statuses = [leg["terminal_status"] for leg in legs]
        if any(status == "rejected_at_entry" for status in statuses):
            terminal = "rejected_at_entry"
            net_return = None
            entry_time = opportunity["signal_time"]
            exit_time = WINDOW_END
        elif any(status == "unresolved" for status in statuses):
            terminal = "unresolved"
            net_return = None
            entry_time = opportunity["signal_time"]
            exit_time = WINDOW_END
        else:
            has_cutoff_mtm = "open_at_cutoff" in statuses
            terminal = (
                "open_at_cutoff"
                if has_cutoff_mtm
                else (
                    "liquidated_proxy"
                    if "liquidated_proxy" in statuses
                    else coin["terminal_status"]
                )
            )
            net_return = sum(float(leg["net_return_on_margin"]) for leg in legs) / len(legs)
            entry_time = opportunity["signal_time"]
            exit_time = (
                WINDOW_END
                if has_cutoff_mtm
                else max(_utc(leg["exit_time"]) for leg in legs)
            )
        item = {
            "candidate_id": opportunity["candidate_id"],
            "source_row_number": opportunity["source_row_number"],
            "family": opportunity["family"],
            "symbol": opportunity["symbol"],
            "direction": opportunity["direction"],
            "entry_time": entry_time,
            "exit_time": exit_time,
            "terminal_status": terminal,
            "net_return_on_margin": net_return,
            "legs": legs,
            "month": opportunity["feature_time"].strftime("%Y-%m"),
            "market_four": opportunity["market_four"],
            "funding_missing": any(bool(leg["funding_missing"]) for leg in legs),
        }
        details.append(item)
        if terminal != "rejected_at_entry":
            trade_symbol = (
                f"{opportunity['symbol']}+BTCUSDT"
                if opportunity["direction"] == "hedge"
                else opportunity["symbol"]
            )
            trade_item = {**item, "symbol": trade_symbol}
            trades.append(_make_trade(candidate_trade, trade_item, net_return, terminal))
    return trades, details


def _status_counts(details: Iterable[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(item["terminal_status"] for item in details).items()))


def _month_summary(details: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in details:
        grouped[item["month"]].append(item)
    result: dict[str, dict[str, Any]] = {}
    for month in sorted(grouped):
        rows = grouped[month]
        resolved = [row for row in rows if row["net_return_on_margin"] is not None]
        result[month] = {
            "selected": len(rows),
            "resolved": len(resolved),
            "unresolved_or_rejected": len(rows) - len(resolved),
            "status_counts": _status_counts(rows),
            "mean_net_return_on_margin": (
                sum(float(row["net_return_on_margin"]) for row in resolved) / len(resolved)
                if resolved
                else None
            ),
        }
    return result


def _mechanism_summary(details: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in details:
        funding = "funding_missing" if item["funding_missing"] else "funding_observed"
        market = "market_four" if item["market_four"] else "market_four_false_or_unknown"
        groups[f"{item['direction']}:{funding}:{market}"].append(item)
    return {
        name: {
            "selected": len(rows),
            "resolved": sum(row["net_return_on_margin"] is not None for row in rows),
            "status_counts": _status_counts(rows),
        }
        for name, rows in sorted(groups.items())
    }


def _concentration(details: Iterable[dict[str, Any]]) -> dict[str, Any]:
    symbol_sum: dict[str, float] = defaultdict(float)
    for item in details:
        if item["net_return_on_margin"] is not None:
            symbol_sum[item["symbol"]] += float(item["net_return_on_margin"])
    ranked = sorted(symbol_sum.items(), key=lambda pair: pair[1], reverse=True)
    total_abs = sum(abs(value) for value in symbol_sum.values())
    by_abs = sorted(symbol_sum.items(), key=lambda pair: abs(pair[1]), reverse=True)
    return {
        "top_symbols_by_path_return": [
            {"symbol": symbol, "net_return_on_margin_sum": value}
            for symbol, value in ranked[:10]
        ],
        "symbol_count_with_resolved_path": len(symbol_sum),
        "top_5_abs_share": (
            sum(abs(value) for _, value in by_abs[:5]) / total_abs
            if total_abs
            else None
        ),
    }


def _trial_record(
    spec: TrialSpec,
    details: list[dict[str, Any]],
    account: Any,
    *,
    funding_stress: bool = False,
    withdraw_profits: bool = True,
) -> dict[str, Any]:
    account_json = _to_jsonable(account)
    profit = _account_metric(account_json, "final_profit", "total_profit", "profit")
    ending = _account_metric(account_json, "final_wealth", "ending_wealth", "wealth")
    if profit is None and ending is not None:
        profit = ending - INITIAL_CAPITAL
    non_rankable = bool(account_json.get("non_rankable", True)) if isinstance(account_json, dict) else True
    return {
        "trial_id": spec.trial_id,
        "family": spec.family,
        "horizon_hours": spec.horizon_hours,
        "leverage": spec.leverage,
        "cost_bps": spec.cost_bps,
        "funding_stress": funding_stress,
        "withdraw_profits": withdraw_profits,
        "provisional": True,
        "candidate_rows_selected": len(details),
        "trade_rows_submitted": sum(
            row["terminal_status"] != "rejected_at_entry" for row in details
        ),
        "status_counts_before_account_nonoverlap": _status_counts(details),
        "month_summary": _month_summary(details),
        "mechanism_summary": _mechanism_summary(details),
        "concentration": _concentration(details),
        "censored_open_at_cutoff": sum(
            row["terminal_status"] == "open_at_cutoff" for row in details
        ),
        "future_gap_unresolved": sum(
            row["terminal_status"] == "unresolved" for row in details
        ),
        "entry_rejected_missing": sum(
            row["terminal_status"] == "rejected_at_entry" for row in details
        ),
        "account": account_json,
        "account_total_profit": profit,
        "account_ending_wealth": ending,
        "rankable": not non_rankable,
    }


def _executed_candidate_ids(account: Any) -> set[str]:
    payload = _to_jsonable(account)
    if not isinstance(payload, dict):
        return set()
    records = payload.get("executed_records", [])
    identifiers: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        trade = record.get("trade", {})
        if isinstance(trade, dict) and trade.get("candidate_id"):
            identifiers.add(str(trade["candidate_id"]))
    return identifiers


def _audit_details(
    details: list[dict[str, Any]], account: Any
) -> list[dict[str, Any]]:
    """Keep auditable paths only for account-executed candidate IDs."""
    identifiers = _executed_candidate_ids(account)
    audit: list[dict[str, Any]] = []
    for item in details:
        if item["candidate_id"] not in identifiers:
            continue
        audit.append(
            {
                key: item[key]
                for key in (
                    "candidate_id",
                    "source_row_number",
                    "family",
                    "symbol",
                    "direction",
                    "entry_time",
                    "exit_time",
                    "terminal_status",
                    "net_return_on_margin",
                    "month",
                    "market_four",
                    "funding_missing",
                )
            }
            | {"legs": item["legs"]}
        )
    return audit


def _trial_grid() -> list[TrialSpec]:
    return [
        TrialSpec(family, horizon, leverage, cost)
        for family in FAMILIES
        for horizon in HORIZONS_HOURS
        for leverage in LEVERAGES
        for cost in COST_BPS
    ]


def _prepare_paths(
    opportunities_by_family: dict[str, list[dict[str, Any]]],
    reader: MarketReader,
) -> tuple[dict[tuple[str, datetime, str, int], PricePath], dict[str, Any]]:
    opportunities = [
        item for family in FAMILIES for item in opportunities_by_family[family]
    ]
    symbols = {item["symbol"] for item in opportunities}
    if any(item["direction"] == "hedge" for item in opportunities):
        symbols.add("BTCUSDT")
    requested: dict[str, set[tuple[datetime, str, int]]] = defaultdict(set)
    for opportunity in opportunities:
        directions = (
            ["short", "long"]
            if opportunity["direction"] == "hedge"
            else [opportunity["direction"]]
        )
        for horizon in HORIZONS_HOURS:
            for direction in directions:
                symbol = (
                    "BTCUSDT"
                    if direction == "long" and opportunity["direction"] == "hedge"
                    else opportunity["symbol"]
                )
                requested[symbol].add(
                    (opportunity["signal_time"], direction, horizon)
                )
    paths: dict[tuple[str, datetime, str, int], PricePath] = {}
    source_reads: list[dict[str, Any]] = []
    for symbol in sorted(symbols):
        bars, funding, meta = reader.read_symbol(symbol)
        source_reads.append(meta)
        for signal_time, direction, horizon in sorted(requested[symbol]):
            key = (symbol, signal_time, direction, horizon)
            end = signal_time + timedelta(hours=horizon)
            if key not in paths:
                paths[key] = _build_path(
                    symbol,
                    direction,
                    signal_time,
                    end,
                    bars,
                    funding,
                )
        del bars, funding
    coverage = {
        "symbols_requested": len(symbols),
        "symbols_read_once": len(source_reads),
        "price_files_missing": sum(not meta["price_exists"] for meta in source_reads),
        "funding_files_missing": sum(
            not meta["funding_exists"] for meta in source_reads
        ),
        "price_source_rows": sum(meta["price_source_rows"] for meta in source_reads),
        "price_valid_rows": sum(meta["price_valid_rows"] for meta in source_reads),
        "funding_source_rows": sum(
            meta["funding_source_rows"] for meta in source_reads
        ),
        "funding_valid_rows": sum(meta["funding_valid_rows"] for meta in source_reads),
        "source_reads": source_reads,
        "path_status_counts": dict(
            sorted(Counter(path.status for path in paths.values()).items())
        ),
        "future_gap_paths": sum(path.status == "unresolved" for path in paths.values()),
        "missing_entry_paths": sum(
            path.status == "rejected_at_entry" for path in paths.values()
        ),
    }
    return paths, coverage


def _run_account(
    simulate_account: Any,
    trades: list[Any],
    *,
    withdraw_profits: bool,
) -> Any:
    return simulate_account(
        trades,
        initial_capital=INITIAL_CAPITAL,
        tranche_count=TRANCHE_COUNT,
        withdraw_profits=withdraw_profits,
    )


def _render_report(result: dict[str, Any]) -> str:
    trials = result["trials"]
    ranked = [
        trial
        for trial in trials
        if trial.get("account_total_profit") is not None and trial.get("rankable")
    ]
    ranked.sort(key=lambda trial: trial["account_total_profit"], reverse=True)
    lines = [
        "# Open-profit search batch 01 — kết quả provisional (2026-09-16)",
        "",
        "Đây là tìm kiếm hữu hạn trên recycled history, không phải holdout và "
        "không phải bằng chứng lợi nhuận đã xác minh. Mọi trial đều mang nhãn "
        "PROVISIONAL.",
        "",
        "## Contract và provenance",
        "",
        f"- Registry SHA256: {result['freeze']['registry_sha256']}.",
        f"- Source SHA256: {result['freeze']['source_sha256']}.",
        f"- Grid: {len(trials)} strategy trials + 1 cash comparator; "
        f"source rows sau gate: {result['source']['nonstable_pump_rows']}.",
        "- Entry là open của nến 5m kế tiếp; OHLC adverse chỉ được dùng sau "
        "entry. Exit là time/cutoff, không TP/SL chủ động.",
        "- Trade OHLC là mark proxy, maintenance ratio giả định 1%, funding "
        "observed cộng đúng dấu khi có, funding thiếu giả định 0 ở base và "
        "gắn cờ. Không phải liquidation/execution/PIT evidence của sàn.",
        "- Future price gap sau entry giữ vốn tới cutoff và đánh dấu "
        "unresolved/non-rankable; không đổi thành loss 0 và không tái dùng vốn.",
        "",
        "## Candidate counts",
        "",
        "| Family | Raw | Sau cooldown 24h |",
        "|---|---:|---:|",
    ]
    for family in FAMILIES:
        count = result["candidate_counts"][family]
        lines.append(
            f"| {family} | {count['raw_pre_cooldown']} | "
            f"{count['selected_after_24h_cooldown']} |"
        )
    lines.extend(
        [
            "",
            "## Trial ranking (khám phá, không IID)",
            "",
            "| Trial | Profit account | Ending wealth | Rankable |",
            "|---|---:|---:|:---:|",
        ]
    )
    for trial in ranked[:12]:
        lines.append(
            f"| {trial['trial_id']} | "
            f"{trial['account_total_profit']:.4f} | "
            f"{trial['account_ending_wealth'] if trial['account_ending_wealth'] is not None else '—'} | "
            f"{'yes' if trial['rankable'] else 'no'} |"
        )
    if not ranked:
        lines.append("| Không có trial rankable | — | — | no |")
    cash_profit = result["cash_comparator"]["account_total_profit"]
    lines.extend(
        [
            "",
            f"Cash comparator: profit {cash_profit:.4f}; đây là mốc 0, không "
            "phải một trade path.",
        ]
    )
    if ranked:
        top = ranked[0]
        if top["account_total_profit"] <= cash_profit:
            lines.append(
                "Không có strategy trial nào beat cash comparator trong các "
                "trial rankable; không gọi đây là winner."
            )
        else:
            lines.append(
                f"Top provisional trial (không phải winner xác minh): {top['trial_id']}."
            )
        lines.extend(
            [
                "",
                "### Sensitivity đã đăng ký cho top provisional trial",
                "",
                "| Comparison | Profit | Rankable |",
                "|---|---:|:---:|",
            ]
        )
        family = top["family"]
        horizon = top["horizon_hours"]
        leverage = top["leverage"]
        cost = top["cost_bps"]
        comparisons = [
            ("top base", top),
            (
                "same family/horizon, 1x same cost",
                next(
                    (
                        trial
                        for trial in trials
                        if trial["family"] == family
                        and trial["horizon_hours"] == horizon
                        and trial["leverage"] == 1
                        and trial["cost_bps"] == cost
                    ),
                    None,
                ),
            ),
            (
                "same family/horizon, 60bps",
                next(
                    (
                        trial
                        for trial in trials
                        if trial["family"] == family
                        and trial["horizon_hours"] == horizon
                        and trial["leverage"] == leverage
                        and trial["cost_bps"] == 60
                    ),
                    None,
                ),
            ),
        ]
        for other_horizon in HORIZONS_HOURS:
            comparisons.append(
                (
                    f"same family/{other_horizon}h",
                    next(
                        (
                            trial
                            for trial in trials
                            if trial["family"] == family
                            and trial["horizon_hours"] == other_horizon
                            and trial["leverage"] == leverage
                            and trial["cost_bps"] == cost
                        ),
                        None,
                    ),
                )
            )
        seen_comparisons: set[str] = set()
        for label, comparison in comparisons:
            if comparison is None or comparison["trial_id"] in seen_comparisons:
                continue
            seen_comparisons.add(comparison["trial_id"])
            lines.append(
                f"| {label} ({comparison['trial_id']}) | "
                f"{comparison['account_total_profit']} | "
                f"{'yes' if comparison['rankable'] else 'no'} |"
            )
        lines.extend(
            [
                "",
                f"- Top opportunity-path status counts before account overlap "
                f"(not account realized PnL): "
                f"{top['status_counts_before_account_nonoverlap']}.",
                f"- Top opportunity-path month summary (not account realized "
                f"PnL): {top['month_summary']}.",
                f"- Top opportunity-path symbol concentration (not account "
                f"realized PnL): {top['concentration']}.",
                f"- Top opportunity-path future-gap unresolved: "
                f"{top['future_gap_unresolved']}; "
                f"open-at-cutoff: {top['censored_open_at_cutoff']}; "
                f"entry rejected: {top['entry_rejected_missing']}.",
                "Các dòng trên là sensitivity/context đã đăng ký, không phải "
                "reselection hoặc causal test.",
            ]
        )
    lines.extend(
        [
            "",
            "Các trial khác nhau không phải account paths độc lập; bảng trên chỉ "
            "xếp hạng trong batch đã đăng ký và không chọn lại sau stress.",
            "",
            "## Coverage và giới hạn",
            "",
            f"- Symbols đọc một lần: {result['coverage']['symbols_read_once']}; "
            f"price files thiếu: {result['coverage']['price_files_missing']}; "
            f"funding files thiếu: {result['coverage']['funding_files_missing']}.",
            f"- Price paths thiếu entry: {result['coverage']['missing_entry_paths']}; "
            f"paths có future gap: {result['coverage']['future_gap_paths']}.",
            "- Funding, maintenance tiers, venue leverage/borrow, continuous "
            "mark, fills và liquidation thật chưa được attested. Không gọi "
            "10x là được sàn chấp nhận.",
            "- Universe chỉ gồm coin đã pump >=15% và kế thừa caveat của PIT "
            "cohort cũ; Feb–Jul là recycled history.",
        ]
    )
    if result.get("winner_diagnostics"):
        lines.extend(["", "## Diagnostic cố định của winner", ""])
        for name, value in result["winner_diagnostics"].items():
            lines.append(
                f"- {name}: trial {value.get('trial_id')}, "
                f"profit {value.get('account_total_profit')}; "
                "không dùng để chọn lại winner."
            )
    if result.get("executed_path_audit"):
        lines.extend(
            [
                "",
                "Executed-path audit được lưu trong JSON cho candidate IDs "
                "thực sự account engine thực thi (kèm cả hai legs hedge):",
            ]
        )
        for name, rows in result["executed_path_audit"].items():
            lines.append(f"- {name}: {len(rows)} executed candidate paths.")
    lines.extend(
        [
            "",
            "Kết luận: đây là proxy account-path research. Không có câu "
            "verified-profit, causal advantage hoặc promotion nào từ artifact.",
            "",
        ]
    )
    return "\n".join(lines)


def run(
    *,
    registry: Path = DEFAULT_REGISTRY,
    source: Path = DEFAULT_SOURCE,
    market_db: Path = DEFAULT_MARKET_DB,
    output: Path = DEFAULT_OUTPUT,
    report: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    registry = registry if registry.is_absolute() else REPO_ROOT / registry
    source = source if source.is_absolute() else REPO_ROOT / source
    market_db = market_db if market_db.is_absolute() else REPO_ROOT / market_db
    output = output if output.is_absolute() else REPO_ROOT / output
    report = report if report.is_absolute() else REPO_ROOT / report

    # This must happen before source outcome paths are read.
    freeze = _registry_provenance(registry, source)
    source_frame, source_meta = _load_source(source)
    opportunities_by_family, candidate_counts = _family_candidates(source_frame)
    CandidateTrade, simulate_account = _load_account_api()
    reader = MarketReader(market_db)
    try:
        paths, coverage = _prepare_paths(opportunities_by_family, reader)
    finally:
        reader.close()

    trials: list[dict[str, Any]] = []
    trial_contexts: dict[str, tuple[TrialSpec, list[dict[str, Any]]]] = {}
    for spec in _trial_grid():
        selected = opportunities_by_family[spec.family]
        trades, details = _build_trial_trades(
            spec, selected, paths, CandidateTrade, funding_stress=False
        )
        account = _run_account(simulate_account, trades, withdraw_profits=True)
        trials.append(_trial_record(spec, details, account))
        trial_contexts[spec.trial_id] = (spec, selected)

    cash = {
        "trial_id": "cash_comparator",
        "family": "cash",
        "horizon_hours": None,
        "leverage": 0,
        "cost_bps": 0,
        "provisional": True,
        "account": {
            "initial_capital": INITIAL_CAPITAL,
            "ending_wealth": INITIAL_CAPITAL,
            "total_profit": 0.0,
            "positive_end_wealth": False,
            "rankable": True,
            "trades": 0,
        },
        "account_total_profit": 0.0,
        "account_ending_wealth": INITIAL_CAPITAL,
        "rankable": True,
        "note": "No-trade comparator; no outcome path read.",
    }
    ranked = [
        trial
        for trial in trials
        if trial["account_total_profit"] is not None and trial["rankable"]
    ]
    winner_diagnostics: dict[str, Any] = {}
    executed_path_audit: dict[str, list[dict[str, Any]]] = {}
    if ranked:
        winner = max(ranked, key=lambda trial: trial["account_total_profit"])
        spec, selected = trial_contexts[winner["trial_id"]]
        _, top_details = _build_trial_trades(
            spec, selected, paths, CandidateTrade, funding_stress=False
        )
        executed_path_audit["top_base"] = _audit_details(
            top_details, winner["account"]
        )
        for name, stress, withdraw in (
            ("withdrawal_control", False, False),
            ("funding_stress_control", True, True),
        ):
            trades, details = _build_trial_trades(
                spec, selected, paths, CandidateTrade, funding_stress=stress
            )
            account = _run_account(
                simulate_account, trades, withdraw_profits=withdraw
            )
            diagnostic = _trial_record(
                spec,
                details,
                account,
                funding_stress=stress,
                withdraw_profits=withdraw,
            )
            diagnostic["diagnostic_of_fixed_winner"] = winner["trial_id"]
            winner_diagnostics[name] = diagnostic
            executed_path_audit[name] = _audit_details(details, account)

    result = {
        "artifact": "open_profit_search_batch_01",
        "artifact_version": "open_profit_search_v1",
        "status": "provisional_research_only",
        "generated_at_utc": datetime.now(UTC),
        "freeze": freeze,
        "source": source_meta,
        "parameters": {
            "window_start_utc": WINDOW_START,
            "window_end_utc": WINDOW_END,
            "initial_capital": INITIAL_CAPITAL,
            "tranche_count": TRANCHE_COUNT,
            "tranche_seed": TRANCHE_SEED,
            "cooldown_hours": 24,
            "horizons_hours": list(HORIZONS_HOURS),
            "leverages": list(LEVERAGES),
            "cost_bps_roundtrip": list(COST_BPS),
            "maintenance_ratio_assumed": MAINTENANCE_RATIO,
            "funding_stress_bps_per_8h": FUNDING_STRESS_BPS,
            "entry_rule": "next_5m_bar_open",
            "exit_rule": "time_exit_or_cutoff; no_active_tp_sl",
            "future_gap_rule": "unresolved_non_rankable_hold_capital_to_cutoff",
            "funding_coverage_attested": False,
            "funding_cadence_8h_is_heuristic": True,
        },
        "candidate_counts": candidate_counts,
        "coverage": coverage,
        "trials": trials,
        "cash_comparator": cash,
        "winner_diagnostics": winner_diagnostics,
        "executed_path_audit": executed_path_audit,
        "all_trial_count": len(trials),
        "all_trial_records_included": len(trials) == 120,
        "outcome_claims": {
            "verified_profit_evidence": False,
            "causal_or_policy_advantage": False,
            "live_or_promotion_eligible": False,
            "all_results_provisional": True,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(_render_report(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--market-db", type=Path, default=DEFAULT_MARKET_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    result = run(
        registry=args.registry,
        source=args.source,
        market_db=args.market_db,
        output=args.output,
        report=args.report,
    )
    print(
        json.dumps(
            {
                "output": _path_label(Path(args.output).resolve()),
                "report": _path_label(Path(args.report).resolve()),
                "trials": result["all_trial_count"],
                "cash_comparator": True,
                "candidate_counts": result["candidate_counts"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
