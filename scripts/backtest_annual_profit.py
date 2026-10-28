"""Frozen one-year Luna Max account backtest.

This module is deliberately split into a read-only input audit and an explicit
``--run`` path.  The default CLI action is the audit; no outcome path is read
until the caller supplies ``--run``.  The runner uses the local Binance
USD-M-shaped Parquet files only, never calls a network service, and never
submits orders.

The implementation follows ``docs/ANNUAL_PROFIT_PROTOCOL_20260918.md``.  In
particular, hourly features are calculated from closed five-minute candles,
the decision is followed by a five-minute entry latency, funding features use
the 60-second observation delay, and the account engine is imported from the
tested ``open_profit_account`` module without changing it.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import sys
from bisect import bisect_right
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

UTC = timezone.utc
PROTOCOL_ID = "annual_profit_20260918"
WINDOW_START = datetime(2025, 9, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 9, 1, tzinfo=UTC)
WARMUP_START = datetime(2025, 8, 1, tzinfo=UTC)
BAR_STEP = timedelta(minutes=5)
HOUR_STEP = timedelta(hours=1)
ENTRY_LATENCY = BAR_STEP
COOLDOWN = timedelta(hours=24)
FUNDING_INTERVAL = timedelta(hours=8)
FUNDING_OBSERVATION_DELAY = timedelta(seconds=60)
FUNDING_MAX_AGE = FUNDING_INTERVAL + FUNDING_OBSERVATION_DELAY
MAINTENANCE_RATIO = 0.01
INITIAL_CAPITAL = 10_000.0
TRANCHE_COUNT = 10
TRANCHE_SEED = INITIAL_CAPITAL / TRANCHE_COUNT
COST_BPS = (20, 60)
EXPECTED_PRICE_FILE_COUNT = 328

DEFAULT_PROTOCOL = REPO_ROOT / "docs/ANNUAL_PROFIT_PROTOCOL_20260918.md"
RAW_PRICE_ROOT = Path(r"D:\Quant-trading\data_lake\klines\5m")
DEFAULT_PRICE_ROOT = RAW_PRICE_ROOT
DEFAULT_PRICE_CACHE_ROOT = REPO_ROOT / "artifacts/annual_profit_20260918/prices/klines/5m"
DEFAULT_FUNDING_ROOT = REPO_ROOT / "artifacts/annual_profit_20260918/data/funding"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts/annual_profit_20260918/backtest"
DEFAULT_REPORT = REPO_ROOT / "docs/ANNUAL_PROFIT_RESULTS_20260918.md"
BTC_REPAIR_START = datetime(2026, 8, 1, tzinfo=UTC)
BTC_REPAIR_END = datetime(2026, 8, 25, tzinfo=UTC)
LIT_CURRENT_CONTRACT_START = datetime(2025, 12, 23, 17, 30, tzinfo=UTC)
LIT_LIFECYCLE_POLICY_ID = "lit_current_underlying_launch_binance_v1"

PROTOCOL_MARKERS = (
    "Một năm đầy đủ",
    "Entry trễ một nến",
    "Funding chỉ dùng settlement đã xảy ra",
    "M48_1",
    "PHASE48_1",
    "C=10.000",
    "Khóa thứ tự sự kiện",
    "Duplicate xung đột",
    "Hash protocol",
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

EVENT_ORDER = {
    "risk_check_closed_candle": 10,
    "time_exit_fill": 20,
    "phase_exit_fill": 20,
    "funding_settlement": 30,
    "decision": 40,
    "entry_fill": 50,
}


class SnapshotChangedError(RuntimeError):
    """Raised when an input file changes after the manifest was frozen."""


@dataclass(frozen=True, slots=True)
class StrategySpec:
    strategy_id: str
    entry_rule: str
    side: str
    horizon_hours: int
    leverage: int
    funding_rule: str | None = None
    phase_exit: bool = False
    hedge_btc: bool = False


@dataclass(frozen=True, slots=True)
class TrialSpec:
    strategy_id: str
    cost_bps: int
    withdraw_profits: bool

    @property
    def trial_id(self) -> str:
        withdrawal = "withdraw" if self.withdraw_profits else "retain"
        return f"{self.strategy_id}__c{self.cost_bps}__{withdrawal}"


@dataclass(frozen=True, slots=True)
class Bar:
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    close_time: datetime | None = None
    source_row_number: int = 0

    @property
    def timestamp(self) -> datetime:
        """Compatibility spelling used by older helper code."""

        return self.open_time

    @property
    def canonical_close_time(self) -> datetime:
        return self.open_time + BAR_STEP - timedelta(milliseconds=1)


@dataclass(frozen=True, slots=True)
class FundingPoint:
    event_time: datetime
    rate: float
    mark_price: float | None = None
    source_row_number: int = 0
    source_row_hash: str = ""
    source_file: str = ""

    @property
    def timestamp(self) -> datetime:
        return self.event_time

    @property
    def available_time(self) -> datetime:
        return self.event_time + FUNDING_OBSERVATION_DELAY


@dataclass(frozen=True, slots=True)
class FundingFeature:
    last: FundingPoint | None
    prior: FundingPoint | None
    last_rate: float | None
    change_8h: float | None
    missing_reason: str | None


@dataclass(frozen=True, slots=True)
class FeatureRow:
    symbol: str
    feature_cutoff: datetime
    decision_time: datetime
    entry_time: datetime
    current_close: float
    ret24h: float
    ret1h: float
    high24h: float
    distance_high24h: float
    source_row_number: int
    funding: FundingFeature

    @property
    def price_ret_24h(self) -> float:
        return self.ret24h

    @property
    def price_ret_1h(self) -> float:
        return self.ret1h

    @property
    def distance_from_high_24h(self) -> float:
        return self.distance_high24h


@dataclass(frozen=True, slots=True)
class BarAudit:
    source_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_identical_rows: int
    duplicate_conflict_timestamps: int
    out_of_window_rows: int


@dataclass(frozen=True, slots=True)
class FeatureAudit:
    expected_decisions: int
    valid_decisions: int
    missing_decisions: int
    missing_cutoff_bar: int
    missing_rolling_bar: int
    first_missing_decision: datetime | None


@dataclass(frozen=True, slots=True)
class LegResult:
    symbol: str
    direction: str
    entry_time: datetime
    scheduled_exit_time: datetime
    effective_exit_time: datetime
    terminal_status: str
    reason: str | None
    entry_price: float | None
    exit_price: float | None
    expected_bars: int
    observed_bars: int
    first_missing_bar: datetime | None
    net_return_on_margin: float | None
    gross_price_return_on_margin: float | None
    funding_return_on_margin: float
    fee_return_on_margin: float | None
    funding_fee_count: int
    funding_missing: bool
    funding_expected: int
    funding_observed: int
    funding_events: tuple[dict[str, Any], ...]
    liquidation_proxy: bool
    intrabar_order_proxy: bool
    censored_unrealized: bool
    phase_decision_time: datetime | None
    gap_lock: bool
    event_order_flags: dict[str, bool]


@dataclass(frozen=True, slots=True)
class Candidate:
    candidate_id: str
    strategy_id: str
    symbol: str
    direction: str
    feature: FeatureRow


STRATEGIES: tuple[StrategySpec, ...] = (
    StrategySpec("M48_1", "M", "long", 48, 1),
    StrategySpec("M48_2", "M", "long", 48, 2),
    StrategySpec("M168_2", "M", "long", 168, 2),
    StrategySpec("NEG48_1", "M", "long", 48, 1, "last_funding_negative"),
    StrategySpec("E48_1", "E", "short", 48, 1),
    StrategySpec("E48_2", "E", "short", 48, 2),
    StrategySpec(
        "POS48_2",
        "E",
        "short",
        48,
        2,
        "last_funding_positive_and_change8h_positive",
    ),
    StrategySpec("SWITCH48_1", "SWITCH", "long_or_short", 48, 1),
    StrategySpec("HEDGE48_2", "E_EX_BTC", "hedge", 48, 2, hedge_btc=True),
    StrategySpec("PHASE48_1", "M", "long", 48, 1, phase_exit=True),
)

TRIAL_SPECS: tuple[TrialSpec, ...] = tuple(
    TrialSpec(strategy.strategy_id, cost_bps, withdraw)
    for strategy in STRATEGIES
    for cost_bps in COST_BPS
    for withdraw in (True, False)
)
STRATEGY_BY_ID = {strategy.strategy_id: strategy for strategy in STRATEGIES}


def _trial_definition(spec: TrialSpec) -> dict[str, Any]:
    strategy = STRATEGY_BY_ID[spec.strategy_id]
    return {
        "trial_id": spec.trial_id,
        "strategy_id": spec.strategy_id,
        "entry_rule": strategy.entry_rule,
        "side": strategy.side,
        "horizon_hours": strategy.horizon_hours,
        "leverage": strategy.leverage,
        "funding_rule": strategy.funding_rule,
        "phase_exit": strategy.phase_exit,
        "hedge_btc": strategy.hedge_btc,
        "cost_bps_roundtrip": spec.cost_bps,
        "withdraw_profits": spec.withdraw_profits,
    }


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _utc(value: Any) -> datetime:
    """Normalize a timestamp, rejecting timezone-naive values."""

    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        result = datetime.fromisoformat(text)
    if result.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware UTC")
    return result.astimezone(UTC)


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted(_jsonable(item) for item in value)
    if hasattr(value, "item"):
        return value.item()
    return value


def _json_dump(value: Any) -> str:
    return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _path_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _resolve_price_root(price_root: Path) -> Path:
    """Use the separately frozen repair snapshot when it has been prepared."""

    price_root = Path(price_root)
    if price_root.resolve() == RAW_PRICE_ROOT.resolve() and DEFAULT_PRICE_CACHE_ROOT.is_dir():
        return DEFAULT_PRICE_CACHE_ROOT
    return price_root


def _protocol_check(protocol_path: Path) -> dict[str, Any]:
    if not protocol_path.is_file():
        raise FileNotFoundError(f"protocol is required: {protocol_path}")
    text = protocol_path.read_text(encoding="utf-8")
    missing = [marker for marker in PROTOCOL_MARKERS if marker not in text]
    if missing:
        raise RuntimeError(f"protocol is not the updated annual protocol; missing {missing}")
    return {
        "path": _path_label(protocol_path),
        "sha256": _sha256(protocol_path),
        "markers": list(PROTOCOL_MARKERS),
        "verified_before_outcomes": True,
    }


def _canonical_row_hash(row: Mapping[str, Any]) -> str:
    normalized: dict[str, Any] = {}
    for key in sorted(row):
        value = row[key]
        if isinstance(value, datetime):
            value = _jsonable(value)
        elif isinstance(value, float) and not math.isfinite(value):
            value = str(value)
        normalized[str(key)] = value
    return hashlib.sha256(_json_dump(normalized).encode("utf-8")).hexdigest()


def _close_time(open_time: datetime) -> datetime:
    return open_time + BAR_STEP - timedelta(milliseconds=1)


def _decision_times() -> tuple[datetime, ...]:
    result: list[datetime] = []
    cursor = WINDOW_START
    while cursor < WINDOW_END:
        result.append(cursor)
        cursor += HOUR_STEP
    return tuple(result)


def iter_decision_times() -> Iterator[datetime]:
    """Yield the fixed 365-day annual decision boundaries."""

    yield from _decision_times()


def _expected_bar_times(start: datetime, end: datetime) -> tuple[datetime, ...]:
    result: list[datetime] = []
    cursor = start
    while cursor < end:
        result.append(cursor)
        cursor += BAR_STEP
    return tuple(result)


def _scheduled_funding_times(
    start: datetime, end: datetime, *, include_end: bool
) -> tuple[datetime, ...]:
    """Return reporting boundaries only; cashflow uses exact event timestamps."""

    first = datetime.combine(start.date(), time(0), tzinfo=UTC)
    while first <= start:
        first += FUNDING_INTERVAL
    result: list[datetime] = []
    cursor = first
    while cursor < end or (include_end and cursor <= end):
        result.append(cursor)
        cursor += FUNDING_INTERVAL
    return tuple(result)


def _funding_feature_from_index(
    decision_time: datetime,
    ordered: Sequence[FundingPoint],
    event_times: Sequence[datetime],
) -> FundingFeature:
    latest_allowed_time = decision_time - FUNDING_OBSERVATION_DELAY
    current_index = bisect_right(event_times, latest_allowed_time) - 1
    current = ordered[current_index] if current_index >= 0 else None
    if current is not None and decision_time - current.event_time > FUNDING_MAX_AGE:
        current = None
    prior_cutoff = decision_time - FUNDING_INTERVAL
    prior_allowed_time = prior_cutoff - FUNDING_OBSERVATION_DELAY
    prior_index = bisect_right(event_times, prior_allowed_time) - 1
    prior = ordered[prior_index] if prior_index >= 0 else None
    if prior is not None and prior_cutoff - prior.event_time > FUNDING_MAX_AGE:
        prior = None
    if current is None:
        reason = "missing_or_stale_last_settlement"
    elif prior is None:
        reason = "missing_or_stale_8h_comparison_settlement"
    else:
        reason = None
    return FundingFeature(
        last=current,
        prior=prior,
        last_rate=None if current is None else current.rate,
        change_8h=(None if current is None or prior is None else current.rate - prior.rate),
        missing_reason=reason,
    )


def _funding_feature(
    decision_time: datetime, funding: Sequence[FundingPoint]
) -> FundingFeature:
    ordered = tuple(sorted(funding, key=lambda point: point.event_time))
    event_times = tuple(point.event_time for point in ordered)
    return _funding_feature_from_index(decision_time, ordered, event_times)


def _feature_for_decision(
    symbol: str,
    decision_time: datetime,
    bars: Mapping[datetime, Bar],
    funding: Sequence[FundingPoint] = (),
) -> FeatureRow | None:
    """Calculate one feature row using only candles closed before ``decision``."""

    current_time = decision_time - BAR_STEP
    required = tuple(current_time - i * BAR_STEP for i in range(289))
    if any(timestamp not in bars for timestamp in required):
        return None
    current = bars[current_time]
    previous_24h = bars[current_time - 288 * BAR_STEP]
    ret24h = current.close / previous_24h.close - 1.0
    previous_1h = bars[current_time - 12 * BAR_STEP]
    ret1h = current.close / previous_1h.close - 1.0
    high24h = max(bars[current_time - i * BAR_STEP].high for i in range(288))
    return FeatureRow(
        symbol=symbol,
        feature_cutoff=current.canonical_close_time,
        decision_time=decision_time,
        entry_time=decision_time + ENTRY_LATENCY,
        current_close=current.close,
        ret24h=ret24h,
        ret1h=ret1h,
        high24h=high24h,
        distance_high24h=current.close / high24h - 1.0,
        source_row_number=current.source_row_number,
        funding=_funding_feature(decision_time, funding),
    )


def hourly_features(
    symbol: str,
    bars: Mapping[datetime, Bar],
    funding: Sequence[FundingPoint] = (),
) -> tuple[list[FeatureRow], FeatureAudit]:
    """Build the causal hourly feature stream and its missing-decision audit."""

    features: list[FeatureRow] = []
    missing_cutoff = 0
    missing_rolling = 0
    first_missing: datetime | None = None
    decisions = _decision_times()
    decision_by_cutoff = {decision - BAR_STEP: decision for decision in decisions}
    sorted_bars = sorted(bars.values(), key=lambda item: item.open_time)
    funding_index = tuple(sorted(funding, key=lambda point: point.event_time))
    funding_times = tuple(point.event_time for point in funding_index)
    valid_by_decision: dict[datetime, FeatureRow] = {}
    high_window: deque[tuple[int, float]] = deque()
    contiguous_run = 0
    previous_time: datetime | None = None
    for index, current in enumerate(sorted_bars):
        if previous_time is not None and current.open_time == previous_time + BAR_STEP:
            contiguous_run += 1
        else:
            contiguous_run = 1
            high_window.clear()
        previous_time = current.open_time
        while high_window and high_window[-1][1] <= current.high:
            high_window.pop()
        high_window.append((index, current.high))
        while high_window and high_window[0][0] <= index - 288:
            high_window.popleft()
        decision = decision_by_cutoff.get(current.open_time)
        if decision is None or contiguous_run < 289:
            continue
        previous_24h = sorted_bars[index - 288]
        previous_1h = sorted_bars[index - 12]
        high24h = high_window[0][1]
        valid_by_decision[decision] = FeatureRow(
            symbol=symbol,
            feature_cutoff=current.canonical_close_time,
            decision_time=decision,
            entry_time=decision + ENTRY_LATENCY,
            current_close=current.close,
            ret24h=current.close / previous_24h.close - 1.0,
            ret1h=current.close / previous_1h.close - 1.0,
            high24h=high24h,
            distance_high24h=current.close / high24h - 1.0,
            source_row_number=current.source_row_number,
            funding=_funding_feature_from_index(decision, funding_index, funding_times),
        )
    for decision in decisions:
        cutoff_bar_time = decision - BAR_STEP
        row = valid_by_decision.get(decision)
        if row is not None:
            features.append(row)
        elif cutoff_bar_time not in bars:
            missing_cutoff += 1
            if first_missing is None:
                first_missing = decision
        else:
            missing_rolling += 1
            if first_missing is None:
                first_missing = decision
    return features, FeatureAudit(
        expected_decisions=len(decisions),
        valid_decisions=len(features),
        missing_decisions=len(decisions) - len(features),
        missing_cutoff_bar=missing_cutoff,
        missing_rolling_bar=missing_rolling,
        first_missing_decision=first_missing,
    )


def _entry_m(row: FeatureRow) -> bool:
    return row.ret24h >= 0.15 and row.ret1h > 0.0


def _entry_e(row: FeatureRow) -> bool:
    return (
        row.ret24h >= 0.25
        and row.distance_high24h <= -0.02
        and row.ret1h < 0.0
    )


def _strategy_direction(strategy: StrategySpec, row: FeatureRow) -> str | None:
    if strategy.entry_rule == "M":
        eligible = _entry_m(row)
        direction = "long"
    elif strategy.entry_rule == "E":
        eligible = _entry_e(row)
        direction = "short"
    elif strategy.entry_rule == "E_EX_BTC":
        eligible = _entry_e(row) and row.symbol != "BTCUSDT"
        direction = "hedge"
    elif strategy.entry_rule == "SWITCH":
        eligible = row.ret24h >= 0.25 and (_entry_e(row) or row.ret1h > 0.0)
        if _entry_e(row):
            direction = "short"
        elif row.ret1h > 0.0:
            direction = "long"
        else:
            return None
    else:
        raise ValueError(f"unknown strategy entry rule: {strategy.entry_rule}")
    if not eligible:
        return None
    funding = row.funding
    if strategy.funding_rule == "last_funding_negative":
        if funding.last_rate is None or funding.last_rate >= 0:
            return None
    if strategy.funding_rule == "last_funding_positive_and_change8h_positive":
        if (
            funding.last_rate is None
            or funding.last_rate <= 0
            or funding.change_8h is None
            or funding.change_8h <= 0
        ):
            return None
    return direction


def _cooldown_select(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Filter conditions first, then apply the per-symbol 24-hour gate."""

    ordered = sorted(
        candidates,
        key=lambda item: (
            item.feature.decision_time,
            -item.feature.ret24h,
            item.symbol,
            item.feature.source_row_number,
            item.candidate_id,
        ),
    )
    last_decision: dict[str, datetime] = {}
    selected: list[Candidate] = []
    for candidate in ordered:
        previous = last_decision.get(candidate.symbol)
        if previous is not None and candidate.feature.decision_time - previous < COOLDOWN:
            continue
        selected.append(candidate)
        last_decision[candidate.symbol] = candidate.feature.decision_time
    return selected


def strategy_candidates(
    strategy: StrategySpec, features: Sequence[FeatureRow]
) -> tuple[list[Candidate], dict[str, int]]:
    """Create one strategy's condition-then-cooldown opportunity stream."""

    raw: list[Candidate] = []
    for row in features:
        direction = _strategy_direction(strategy, row)
        if direction is None:
            continue
        candidate_id = (
            f"{strategy.strategy_id}:{row.symbol}:{row.decision_time.isoformat()}"
            f":r{row.source_row_number}"
        )
        raw.append(Candidate(candidate_id, strategy.strategy_id, row.symbol, direction, row))
    selected = _cooldown_select(raw)
    return selected, {
        "raw_condition_matches": len(raw),
        "selected_after_24h_cooldown": len(selected),
        "selected_symbols": len({candidate.symbol for candidate in selected}),
    }


def find_phase_exit(
    entry_time: datetime,
    scheduled_exit_time: datetime,
    features: Sequence[FeatureRow],
) -> tuple[datetime, datetime] | None:
    """Find the first strictly-later phase signal and its delayed fill."""

    for row in features:
        if row.decision_time <= entry_time:
            continue
        phase_fill = row.entry_time
        if phase_fill >= scheduled_exit_time or phase_fill >= WINDOW_END:
            continue
        if row.ret1h < 0.0 and row.distance_high24h <= -0.05:
            return phase_fill, row.decision_time
    return None


def _normalise_price_rows(
    rows: Iterable[Sequence[Any]], symbol: str
) -> tuple[dict[datetime, Bar], BarAudit]:
    """Validate OHLC rows, collapsing identical duplicates and rejecting conflicts."""

    grouped: dict[datetime, list[tuple[int, Sequence[Any]]]] = defaultdict(list)
    source_rows = 0
    out_of_window = 0
    invalid_time = 0
    for row_number, row in enumerate(rows, start=1):
        source_rows += 1
        try:
            timestamp = _utc(row[0])
        except (IndexError, TypeError, ValueError, OverflowError):
            invalid_time += 1
            continue
        if timestamp < WARMUP_START or timestamp >= WINDOW_END:
            out_of_window += 1
            continue
        grouped[timestamp].append((row_number, row))
    bars: dict[datetime, Bar] = {}
    invalid = 0
    identical_duplicates = 0
    conflict_timestamps = 0
    for timestamp in sorted(grouped):
        candidates = grouped[timestamp]
        valid_values: list[tuple[int, float, float, float, float]] = []
        for row_number, row in candidates:
            try:
                open_price = float(row[2])
                high = float(row[3])
                low = float(row[4])
                close = float(row[5])
                close_time = _utc(row[1])
            except (IndexError, TypeError, ValueError, OverflowError):
                invalid += 1
                continue
            valid = (
                timestamp.minute % 5 == 0
                and timestamp.second == 0
                and timestamp.microsecond == 0
                and close_time == _close_time(timestamp)
                and all(math.isfinite(value) for value in (open_price, high, low, close))
                and min(open_price, high, low, close) > 0
                and high >= max(open_price, close)
                and low <= min(open_price, close)
            )
            if not valid:
                invalid += 1
                continue
            valid_values.append((row_number, open_price, high, low, close))
        if not valid_values:
            continue
        shapes = {(item[1], item[2], item[3], item[4]) for item in valid_values}
        if len(shapes) > 1:
            conflict_timestamps += 1
            invalid += len(valid_values)
            continue
        if len(valid_values) > 1:
            identical_duplicates += len(valid_values) - 1
        first = valid_values[0]
        bars[timestamp] = Bar(
            open_time=timestamp,
            open=first[1],
            high=first[2],
            low=first[3],
            close=first[4],
            close_time=_close_time(timestamp),
            source_row_number=first[0],
        )
    return bars, BarAudit(
        source_rows=source_rows,
        valid_rows=len(bars),
        invalid_rows=invalid + invalid_time,
        duplicate_identical_rows=identical_duplicates,
        duplicate_conflict_timestamps=conflict_timestamps,
        out_of_window_rows=out_of_window,
    )


def _funding_column(columns: Sequence[str], aliases: Sequence[str]) -> str | None:
    lookup = {column.lower(): column for column in columns}
    for alias in aliases:
        if alias.lower() in lookup:
            return lookup[alias.lower()]
    return None


def _funding_from_rows(
    rows: Sequence[Mapping[str, Any]], columns: Sequence[str], source_file: str
) -> tuple[tuple[FundingPoint, ...], dict[str, Any]]:
    event_column = _funding_column(
        columns,
        (
            "event_time",
            "funding_time",
            "settlement_time",
            "timestamp",
            "time",
        ),
    )
    rate_column = _funding_column(
        columns, ("funding_rate", "fundingRate", "rate", "value")
    )
    mark_column = _funding_column(
        columns, ("mark_price", "markPrice", "mark", "index_price")
    )
    if event_column is None or rate_column is None:
        raise ValueError(
            f"funding cache {source_file} needs event_time/funding_time and funding_rate/rate"
        )
    by_event: dict[datetime, list[FundingPoint]] = defaultdict(list)
    invalid = 0
    for row_number, row in enumerate(rows, start=1):
        try:
            event_time = _utc(row[event_column])
            rate = float(row[rate_column])
            mark = _finite(row.get(mark_column)) if mark_column else None
            if not math.isfinite(rate) or (mark is not None and mark <= 0):
                raise ValueError("invalid funding value")
        except (KeyError, TypeError, ValueError, OverflowError):
            invalid += 1
            continue
        by_event[event_time].append(
            FundingPoint(
                event_time=event_time,
                rate=rate,
                mark_price=mark,
                source_row_number=row_number,
                source_row_hash=str(row.get("source_row_hash") or _canonical_row_hash(row)),
                source_file=source_file,
            )
        )
    points: list[FundingPoint] = []
    conflict_timestamps = 0
    identical_duplicates = 0
    for event_time in sorted(by_event):
        grouped = by_event[event_time]
        shapes = {(point.rate, point.mark_price) for point in grouped}
        if len(shapes) > 1:
            conflict_timestamps += 1
            invalid += len(grouped)
            continue
        if len(grouped) > 1:
            identical_duplicates += len(grouped) - 1
        points.append(grouped[0])
    return tuple(points), {
        "source_file": source_file,
        "source_rows": len(rows),
        "valid_rows": len(points),
        "invalid_rows": invalid,
        "duplicate_identical_rows": identical_duplicates,
        "duplicate_conflict_timestamps": conflict_timestamps,
        "event_column": event_column,
        "rate_column": rate_column,
        "mark_column": mark_column,
    }


def _funding_event_price(
    point: FundingPoint, bars: Mapping[datetime, Bar]
) -> tuple[float, str]:
    if point.mark_price is not None and point.mark_price > 0:
        return point.mark_price, "settlement_mark_price"
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    elapsed = point.event_time - epoch
    elapsed_ms = (
        elapsed.days * 86_400_000
        + elapsed.seconds * 1_000
        + elapsed.microseconds // 1_000
    )
    bar_ms = (elapsed_ms // int(BAR_STEP.total_seconds() * 1_000)) * int(
        BAR_STEP.total_seconds() * 1_000
    )
    bar_start = epoch + timedelta(milliseconds=bar_ms)
    intrabar = bars.get(bar_start)
    if intrabar is not None:
        return intrabar.open, "intrabar_open_proxy"
    previous = bars.get(bar_start - BAR_STEP)
    if previous is not None:
        return previous.close, "previous_close_proxy"
    following = bars.get(bar_start + BAR_STEP)
    if following is not None:
        return following.open, "following_open_proxy"
    # This is only a malformed/gapped-data fallback.  Normal funding rows
    # carry mark_price, and a complete 5m path takes the O(1) branch above.
    previous_candidates = [bar for timestamp, bar in bars.items() if timestamp < point.event_time]
    if previous_candidates:
        return max(previous_candidates, key=lambda bar: bar.open_time).close, "previous_close_proxy"
    following_candidates = [bar for timestamp, bar in bars.items() if timestamp > point.event_time]
    if following_candidates:
        return min(following_candidates, key=lambda bar: bar.open_time).open, "following_open_proxy"
    return 1.0, "entry_price_fallback_proxy"


def _funding_event_is_in_holding(
    event_time: datetime,
    entry_time: datetime,
    exit_time: datetime,
    *,
    cutoff_mtm: bool,
) -> bool:
    """Funding is in (entry, exit), except a cutoff MTM includes the cutoff."""

    if event_time <= entry_time:
        return False
    if cutoff_mtm:
        return event_time <= exit_time
    return event_time < exit_time


def event_order_key(event_type: str) -> int:
    if event_type not in EVENT_ORDER:
        raise ValueError(f"unknown event type: {event_type}")
    return EVENT_ORDER[event_type]


def _maintenance_touched(
    *,
    direction: str,
    adverse_price: float,
    entry_price: float,
    leverage: int,
    funding_return: float,
    entry_fee: float,
) -> bool:
    sign = 1.0 if direction == "long" else -1.0
    unrealized = sign * (adverse_price / entry_price - 1.0) * leverage
    equity = 1.0 + unrealized + funding_return - entry_fee
    maintenance = MAINTENANCE_RATIO * (adverse_price / entry_price) * leverage
    return equity <= maintenance + 1e-12


def _funding_schedule_coverage(
    entry_time: datetime,
    exit_time: datetime,
    points: Sequence[FundingPoint],
    *,
    cutoff_mtm: bool,
) -> tuple[bool, int, int]:
    expected = _scheduled_funding_times(entry_time, exit_time, include_end=cutoff_mtm)
    observed = [
        point.event_time
        for point in points
        if _funding_event_is_in_holding(
            point.event_time,
            entry_time,
            exit_time,
            cutoff_mtm=cutoff_mtm,
        )
    ]
    matched = sum(
        any(abs((observed_time - expected_time).total_seconds()) <= 60 for observed_time in observed)
        for expected_time in expected
    )
    return matched < len(expected), len(expected), len(observed)


def _leg_flags(
    *,
    cutoff_mtm: bool,
    intrabar_order_proxy: bool = False,
    phase_decision_time: datetime | None = None,
    liquidation_proxy: bool = False,
) -> dict[str, bool]:
    return {
        "risk_check_before_boundary_fill": True,
        "time_or_phase_fill_before_funding_at_same_timestamp": True,
        "funding_at_entry_excluded": True,
        "funding_at_exit_excluded": not cutoff_mtm,
        "cutoff_mtm_includes_cutoff_settlement": cutoff_mtm,
        "phase_time_tie_resolved_to_time_exit": phase_decision_time is None,
        "liquidation_precedes_boundary_fill": liquidation_proxy,
        "intrabar_order_proxy": intrabar_order_proxy,
    }


def evaluate_leg(
    *,
    symbol: str,
    direction: str,
    entry_time: datetime,
    scheduled_exit_time: datetime,
    bars: Mapping[datetime, Bar],
    funding: Sequence[FundingPoint] = (),
    leverage: int,
    cost_bps: int,
    phase_exit_time: datetime | None = None,
    phase_decision_time: datetime | None = None,
) -> LegResult:
    """Evaluate one isolated leg with conservative OHLC/funding ordering.

    ``scheduled_exit_time`` is the horizon boundary.  A phase exit may shorten
    it only when its delayed fill is strictly earlier; equality is a time-exit
    tie.  A horizon at or beyond ``WINDOW_END`` is a cutoff MTM, not a close
    fill and has no exit fee.
    """

    entry_time = _utc(entry_time)
    scheduled_exit_time = _utc(scheduled_exit_time)
    if phase_exit_time is not None:
        phase_exit_time = _utc(phase_exit_time)
    if phase_decision_time is not None:
        phase_decision_time = _utc(phase_decision_time)
    if direction not in {"long", "short"}:
        raise ValueError("direction must be long or short")
    if leverage <= 0:
        raise ValueError("leverage must be positive")
    if cost_bps <= 0:
        raise ValueError("cost_bps must be positive")

    chosen_phase = (
        phase_exit_time is not None
        and phase_exit_time < scheduled_exit_time
        and phase_exit_time < WINDOW_END
    )
    target_exit = phase_exit_time if chosen_phase else scheduled_exit_time
    cutoff_mtm = target_exit >= WINDOW_END
    effective_exit = WINDOW_END if cutoff_mtm else target_exit
    entry_bar = bars.get(entry_time)

    empty_coverage = _funding_schedule_coverage(
        entry_time,
        effective_exit,
        (),
        cutoff_mtm=cutoff_mtm,
    )
    flags = _leg_flags(
        cutoff_mtm=cutoff_mtm,
        phase_decision_time=phase_decision_time if chosen_phase else None,
    )
    if entry_bar is None:
        return LegResult(
            symbol=symbol,
            direction=direction,
            entry_time=entry_time,
            scheduled_exit_time=scheduled_exit_time,
            effective_exit_time=effective_exit,
            terminal_status="rejected_at_entry",
            reason="missing_entry_bar",
            entry_price=None,
            exit_price=None,
            expected_bars=0,
            observed_bars=0,
            first_missing_bar=entry_time,
            net_return_on_margin=None,
            gross_price_return_on_margin=None,
            funding_return_on_margin=0.0,
            fee_return_on_margin=None,
            funding_fee_count=0,
            funding_missing=empty_coverage[0],
            funding_expected=empty_coverage[1],
            funding_observed=0,
            funding_events=(),
            liquidation_proxy=False,
            intrabar_order_proxy=False,
            censored_unrealized=False,
            phase_decision_time=None,
            gap_lock=False,
            event_order_flags=flags,
        )

    holding_times = _expected_bar_times(entry_time, effective_exit)
    missing_times = [timestamp for timestamp in holding_times if timestamp not in bars]
    exit_bar = None if cutoff_mtm else bars.get(target_exit)
    if exit_bar is None and not cutoff_mtm:
        missing_times.append(target_exit)
    first_missing = min(missing_times) if missing_times else None
    # Evaluate the contiguous known prefix before deciding that a later gap
    # makes the path unresolved.  A terminal risk event in that prefix is
    # deterministic and must not be erased by a future missing candle.
    known_holding_times = tuple(
        timestamp
        for timestamp in holding_times
        if first_missing is None or timestamp < first_missing
    )
    held_bars = tuple(bars[timestamp] for timestamp in known_holding_times)
    held_points = tuple(
        sorted(
            (
                point
                for point in funding
                if first_missing is None or point.event_time < first_missing
                if _funding_event_is_in_holding(
                    point.event_time,
                    entry_time,
                    effective_exit,
                    cutoff_mtm=cutoff_mtm,
                )
            ),
            key=lambda point: (point.event_time, point.source_row_number),
        )
    )
    funding_missing, funding_expected, funding_observed = _funding_schedule_coverage(
        entry_time,
        effective_exit,
        held_points,
        cutoff_mtm=cutoff_mtm,
    )
    entry_price = entry_bar.open
    sign = 1.0 if direction == "long" else -1.0
    side_fee = cost_bps / 2.0 / 10_000.0
    entry_fee = side_fee * leverage
    event_amounts: dict[datetime, tuple[float, dict[str, Any]]] = {}
    for point in held_points:
        settlement_price, price_source = _funding_event_price(point, bars)
        amount = -sign * (settlement_price / entry_price) * point.rate * leverage
        event_amounts[point.event_time] = (
            amount,
            _funding_record(point, amount, settlement_price, price_source),
        )

    funding_return = 0.0
    funding_records: list[dict[str, Any]] = []
    liquidation_bar: Bar | None = None
    intrabar_proxy = False
    terminal_cutoff_liquidation = False

    def check_adverse(bar: Bar, accumulated: float) -> bool:
        adverse = bar.low if sign > 0 else bar.high
        return _maintenance_touched(
            direction=direction,
            adverse_price=adverse,
            entry_price=entry_price,
            leverage=leverage,
            funding_return=accumulated,
            entry_fee=entry_fee,
        )

    for bar in held_bars:
        bar_start = bar.open_time
        bar_end = bar.open_time + BAR_STEP
        bar_points = [
            point
            for point in held_points
            if bar_start <= point.event_time < bar_end
        ]
        at_open = [point for point in bar_points if point.event_time == bar_start]
        intrabar = [point for point in bar_points if point.event_time > bar_start]
        for point in at_open:
            amount, record = event_amounts[point.event_time]
            funding_return += amount
            funding_records.append(record)
        touched = check_adverse(bar, funding_return)
        if intrabar:
            # OHLC cannot establish whether the adverse extreme preceded or
            # followed a settlement inside this candle.  Test both orders.
            if touched:
                intrabar_proxy = True
            for point in intrabar:
                amount, record = event_amounts[point.event_time]
                funding_return += amount
                funding_records.append(record)
                if check_adverse(bar, funding_return):
                    touched = True
                    intrabar_proxy = True
        if touched:
            liquidation_bar = bar
            break

    # A cutoff settlement at exactly WINDOW_END is observed after the last
    # closed candle and before the cutoff MTM.  Actual fills exclude the
    # settlement at their exact exit timestamp by construction above.
    if liquidation_bar is None:
        assigned = {point.event_time for point in held_points if point.event_time < effective_exit}
        remaining = [point for point in held_points if point.event_time not in assigned]
        for point in remaining:
            amount, record = event_amounts[point.event_time]
            funding_return += amount
            funding_records.append(record)
        if cutoff_mtm and first_missing is None and held_bars:
            terminal_price = held_bars[-1].close
            if _maintenance_touched(
                direction=direction,
                adverse_price=terminal_price,
                entry_price=entry_price,
                leverage=leverage,
                funding_return=funding_return,
                entry_fee=entry_fee,
            ):
                liquidation_bar = held_bars[-1]
                terminal_cutoff_liquidation = True

    if liquidation_bar is not None:
        adverse = liquidation_bar.low if sign > 0 else liquidation_bar.high
        liquidation_exit = (
            WINDOW_END
            if terminal_cutoff_liquidation
            else liquidation_bar.canonical_close_time
        )
        applied_event_times = {
            record["event_time"] for record in funding_records
        }
        applied_points = tuple(
            point for point in held_points if point.event_time in applied_event_times
        )
        liquidation_funding_missing, liquidation_funding_expected, liquidation_funding_observed = (
            _funding_schedule_coverage(
                entry_time,
                liquidation_exit,
                applied_points,
                cutoff_mtm=terminal_cutoff_liquidation,
            )
        )
        flags = _leg_flags(
            cutoff_mtm=terminal_cutoff_liquidation,
            intrabar_order_proxy=intrabar_proxy,
            phase_decision_time=phase_decision_time if chosen_phase else None,
            liquidation_proxy=True,
        )
        return LegResult(
            symbol=symbol,
            direction=direction,
            entry_time=entry_time,
            scheduled_exit_time=scheduled_exit_time,
            effective_exit_time=liquidation_exit,
            terminal_status="liquidated_proxy",
            reason=("intrabar_order_proxy" if intrabar_proxy else "maintenance_touched_ohlc_proxy"),
            entry_price=entry_price,
            exit_price=adverse,
            expected_bars=len(holding_times),
            observed_bars=len(held_bars),
            first_missing_bar=first_missing,
            net_return_on_margin=-1.0,
            gross_price_return_on_margin=sign * (adverse / entry_price - 1.0) * leverage,
            funding_return_on_margin=funding_return,
            fee_return_on_margin=entry_fee,
            funding_fee_count=len(funding_records),
            funding_missing=liquidation_funding_missing,
            funding_expected=liquidation_funding_expected,
            funding_observed=liquidation_funding_observed,
            funding_events=tuple(funding_records),
            liquidation_proxy=True,
            intrabar_order_proxy=intrabar_proxy,
            censored_unrealized=False,
            phase_decision_time=phase_decision_time if chosen_phase else None,
            gap_lock=False,
            event_order_flags=flags,
        )

    if first_missing is not None:
        coverage = _funding_schedule_coverage(
            entry_time,
            effective_exit,
            held_points,
            cutoff_mtm=cutoff_mtm,
        )
        return LegResult(
            symbol=symbol,
            direction=direction,
            entry_time=entry_time,
            scheduled_exit_time=scheduled_exit_time,
            effective_exit_time=effective_exit,
            terminal_status="unresolved",
            reason="missing_future_bar",
            entry_price=entry_bar.open,
            exit_price=None,
            expected_bars=len(holding_times),
            observed_bars=len(held_bars),
            first_missing_bar=first_missing,
            net_return_on_margin=None,
            gross_price_return_on_margin=None,
            # Funding events in the known prefix have been applied in event
            # order.  The residual price/fee path remains explicitly unknown.
            funding_return_on_margin=funding_return,
            fee_return_on_margin=None,
            funding_fee_count=len(funding_records),
            funding_missing=coverage[0],
            funding_expected=coverage[1],
            funding_observed=coverage[2],
            funding_events=tuple(funding_records),
            liquidation_proxy=False,
            intrabar_order_proxy=intrabar_proxy,
            censored_unrealized=False,
            phase_decision_time=phase_decision_time if chosen_phase else None,
            gap_lock=True,
            event_order_flags={**flags, "gap_lock_blocks_capital_reuse": True},
        )

    if cutoff_mtm:
        exit_price = held_bars[-1].close
        gross = sign * (exit_price / entry_price - 1.0) * leverage
        fee = entry_fee
        status = "open_at_cutoff"
        censored = True
        realized = False
    else:
        assert exit_bar is not None
        exit_price = exit_bar.open
        gross = sign * (exit_price / entry_price - 1.0) * leverage
        fee = entry_fee + side_fee * (exit_price / entry_price) * leverage
        status = "phase_exit" if chosen_phase else "time_exit"
        censored = False
        realized = True
    net = gross + funding_return - fee
    flags = _leg_flags(
        cutoff_mtm=cutoff_mtm,
        intrabar_order_proxy=False,
        phase_decision_time=phase_decision_time if chosen_phase else None,
    )
    flags["realized_close_fill"] = realized
    return LegResult(
        symbol=symbol,
        direction=direction,
        entry_time=entry_time,
        scheduled_exit_time=scheduled_exit_time,
        effective_exit_time=effective_exit,
        terminal_status=status,
        reason=None,
        entry_price=entry_price,
        exit_price=exit_price,
        expected_bars=len(holding_times),
        observed_bars=len(held_bars),
        first_missing_bar=None,
        net_return_on_margin=net,
        gross_price_return_on_margin=gross,
        funding_return_on_margin=funding_return,
        fee_return_on_margin=fee,
        funding_fee_count=len(funding_records),
        funding_missing=funding_missing,
        funding_expected=funding_expected,
        funding_observed=funding_observed,
        funding_events=tuple(funding_records),
        liquidation_proxy=False,
        intrabar_order_proxy=False,
        censored_unrealized=censored,
        phase_decision_time=phase_decision_time if chosen_phase else None,
        gap_lock=False,
        event_order_flags=flags,
    )


def _funding_record(
    point: FundingPoint,
    amount_return_on_margin: float,
    settlement_price: float | None,
    price_source: str,
) -> dict[str, Any]:
    return {
        "event_time": point.event_time,
        "available_time": point.available_time,
        "rate": point.rate,
        "settlement_price": settlement_price,
        "settlement_price_source": price_source,
        "amount_return_on_margin": amount_return_on_margin,
        "source_row_number": point.source_row_number,
        "source_row_hash": point.source_row_hash,
        "source_file": point.source_file,
    }


def _leg_record(leg: LegResult, *, margin_usd: float | None = None) -> dict[str, Any]:
    record = _jsonable(leg)
    if margin_usd is not None:
        record["margin_usd"] = margin_usd
        record["funding_fee_usd"] = margin_usd * leg.funding_return_on_margin
        record["fee_usd"] = (
            None if leg.fee_return_on_margin is None else margin_usd * leg.fee_return_on_margin
        )
    return record


def _leg_component_accounting(leg: LegResult) -> dict[str, Any]:
    """Classify one leg without turning an unknown amount into zero."""

    status = str(leg.terminal_status)
    if status == "rejected_at_entry":
        return {
            "state": "not_entered",
            "known_realized_return_on_margin": 0.0,
            "known_unrealized_return_on_margin": 0.0,
            "unknown_return_on_margin": 0.0,
            "unknown_margin_weight": 0.0,
        }
    if status == "unresolved" or leg.net_return_on_margin is None:
        return {
            "state": "unknown",
            "known_realized_return_on_margin": 0.0,
            "known_unrealized_return_on_margin": 0.0,
            "unknown_return_on_margin": None,
            "unknown_margin_weight": 1.0,
        }
    if status == "open_at_cutoff" or leg.censored_unrealized:
        return {
            "state": "known_unrealized",
            "known_realized_return_on_margin": 0.0,
            "known_unrealized_return_on_margin": float(leg.net_return_on_margin),
            "unknown_return_on_margin": 0.0,
            "unknown_margin_weight": 0.0,
        }
    return {
        "state": "known_realized",
        "known_realized_return_on_margin": float(leg.net_return_on_margin),
        "known_unrealized_return_on_margin": 0.0,
        "unknown_return_on_margin": 0.0,
        "unknown_margin_weight": 0.0,
    }


def combine_legs(
    candidate: Candidate,
    legs: Sequence[LegResult],
) -> dict[str, Any]:
    """Combine normal or two-leg hedge outcomes on the pair's margin."""

    if not legs:
        raise ValueError("at least one leg is required")
    statuses = [leg.terminal_status for leg in legs]
    margin_weight = 1.0 / len(legs)
    component_rows: list[dict[str, Any]] = []
    known_realized = 0.0
    known_unrealized = 0.0
    unknown_margin_weight = 0.0
    for leg in legs:
        accounting = _leg_component_accounting(leg)
        known_realized += margin_weight * float(
            accounting["known_realized_return_on_margin"]
        )
        known_unrealized += margin_weight * float(
            accounting["known_unrealized_return_on_margin"]
        )
        unknown_margin_weight += margin_weight * float(
            accounting["unknown_margin_weight"]
        )
        component_rows.append(
            {
                "symbol": leg.symbol,
                "direction": leg.direction,
                "margin_weight": margin_weight,
                "terminal_status": leg.terminal_status,
                "accounting": accounting,
            }
        )
    fully_known = unknown_margin_weight <= 1e-12
    unknown_return = 0.0 if fully_known else None
    if "rejected_at_entry" in statuses:
        terminal = "rejected_at_entry"
        net = None
        effective_exit = WINDOW_END
    elif "unresolved" in statuses:
        terminal = "unresolved"
        net = None
        effective_exit = WINDOW_END
    else:
        # A hedge can lose one half at liquidation while its other half
        # remains open through the cutoff.  Keep that pair censored until the
        # remaining leg ends; otherwise the account engine could sweep an
        # unrealized pair result as realized profit.
        if "open_at_cutoff" in statuses:
            terminal = "open_at_cutoff"
        elif "liquidated_proxy" in statuses:
            terminal = "liquidated_proxy"
        elif "phase_exit" in statuses:
            terminal = "phase_exit"
        else:
            terminal = "time_exit"
        net = known_realized + known_unrealized if fully_known else None
        effective_exit = max(leg.effective_exit_time for leg in legs)
    leg_records = []
    for leg, component in zip(legs, component_rows):
        record = _leg_record(leg)
        record["margin_weight"] = component["margin_weight"]
        record["accounting"] = component["accounting"]
        leg_records.append(record)
    return {
        "candidate_id": candidate.candidate_id,
        "strategy_id": candidate.strategy_id,
        "symbol": candidate.symbol,
        "direction": candidate.direction,
        "entry_time": candidate.feature.entry_time,
        "decision_time": candidate.feature.decision_time,
        "feature_cutoff": candidate.feature.feature_cutoff,
        "exit_time": effective_exit,
        "terminal_status": terminal,
        "net_return_on_margin": net,
        "month": candidate.feature.entry_time.strftime("%Y-%m"),
        "gap_lock": any(leg.gap_lock for leg in legs),
        "funding_missing": any(leg.funding_missing for leg in legs),
        "funding_fee_return_on_margin": sum(
            leg.funding_return_on_margin for leg in legs
        ) / len(legs),
        "unrealized_return_on_margin": (
            known_unrealized
        ),
        "censored_unrealized": terminal == "open_at_cutoff",
        "component_accounting": {
            "fully_known": fully_known,
            "known_realized_return_on_margin": known_realized,
            "known_unrealized_return_on_margin": known_unrealized,
            "unknown_return_on_margin": unknown_return,
            "unknown_margin_weight": unknown_margin_weight,
            "components": component_rows,
        },
        "feature_values": {
            "pump24h": candidate.feature.ret24h,
            "ret1h": candidate.feature.ret1h,
            "high24h": candidate.feature.high24h,
            "distance_high24h": candidate.feature.distance_high24h,
        },
        "funding_feature": {
            "last_rate": candidate.feature.funding.last_rate,
            "change8h": candidate.feature.funding.change_8h,
            "missing_reason": candidate.feature.funding.missing_reason,
            "last": candidate.feature.funding.last,
            "prior": candidate.feature.funding.prior,
        },
        "event_order_flags": {
            key: all(leg.event_order_flags.get(key, False) for leg in legs)
            for key in {
                key for leg in legs for key in leg.event_order_flags
            }
        },
        "legs": leg_records,
    }


def _duckdb_connection():
    import duckdb

    connection = duckdb.connect(":memory:")
    connection.execute("SET memory_limit='512MB'")
    connection.execute("SET threads=2")
    return connection


def _parquet_columns(connection: Any, path: Path) -> tuple[str, ...]:
    rows = connection.execute(
        "DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]
    ).fetchall()
    return tuple(str(row[0]) for row in rows)


def _read_price_file(
    connection: Any, path: Path
) -> tuple[dict[datetime, Bar], BarAudit, tuple[str, ...]]:
    columns = _parquet_columns(connection, path)
    required = {"open_time", "close_time", "open", "high", "low", "close"}
    missing = sorted(required - set(columns))
    if missing:
        raise ValueError(f"price file {path} is missing columns: {missing}")
    rows = connection.execute(
        """
        SELECT open_time, close_time, open, high, low, close
        FROM read_parquet(?)
        WHERE open_time >= ? AND open_time < ?
        ORDER BY open_time
        """,
        [str(path), WARMUP_START, WINDOW_END],
    ).fetchall()
    return _normalise_price_rows(rows, path.stem.upper()) + (columns,)


def _read_funding_file(
    connection: Any, path: Path, symbol: str
) -> tuple[tuple[FundingPoint, ...], dict[str, Any], tuple[str, ...]]:
    if not path.is_file():
        return (), {
            "symbol": symbol,
            "exists": False,
            "source_file": _path_label(path),
            "source_rows": 0,
            "valid_rows": 0,
            "invalid_rows": 0,
        }, ()
    columns = _parquet_columns(connection, path)
    rows = connection.execute("SELECT * FROM read_parquet(?)", [str(path)]).fetchall()
    mappings = [dict(zip(columns, row)) for row in rows]
    points, meta = _funding_from_rows(mappings, columns, _path_label(path))
    meta = {
        "symbol": symbol,
        "exists": True,
        "sha256": _sha256(path),
        **meta,
        "parquet_metadata": _parquet_metadata(path),
        "sidecar_path": str(path.with_suffix(".json").resolve()),
        "sidecar_exists": path.with_suffix(".json").is_file(),
        "sidecar": _funding_sidecar_summary(
            _load_sidecar(path.with_suffix(".json"))
            if path.with_suffix(".json").is_file()
            else {}
        ),
    }
    return points, meta, columns


def _parquet_metadata(path: Path) -> dict[str, str]:
    try:
        import pyarrow.parquet as parquet

        metadata = parquet.ParquetFile(path).metadata.metadata or {}
        result: dict[str, str] = {}
        for key, value in metadata.items():
            label = key.decode("utf-8", "replace") if isinstance(key, bytes) else str(key)
            # Arrow embeds a large serialized schema in every Parquet file.
            # It is not provenance needed by the audit and would be copied
            # into every candidate detail through the funding metadata.
            if label.lower() in {"arrow:schema", "pandas"}:
                continue
            result[label] = (
                value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)
            )
        return result
    except Exception as exc:  # metadata is provenance enrichment, not price data
        return {"read_error": type(exc).__name__}


def _discover_price_files(price_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    if not price_root.is_dir():
        raise FileNotFoundError(f"price root is required: {price_root}")
    all_files = sorted(price_root.glob("*.parquet"), key=lambda item: item.name.upper())
    descriptors: list[dict[str, Any]] = []
    excluded: list[str] = []
    seen_symbols: set[str] = set()
    for path in all_files:
        symbol = path.stem.upper()
        if not symbol.endswith("USDT"):
            excluded.append(path.name)
            continue
        if symbol in seen_symbols:
            raise ValueError(f"duplicate universe symbol filenames: {symbol}")
        seen_symbols.add(symbol)
        descriptors.append(
            {
                "symbol": symbol,
                "file_name": path.name,
                "path": str(path.resolve()),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "columns": [],
            }
        )
    return descriptors, excluded


def _price_snapshot_provenance(price_root: Path) -> dict[str, Any]:
    if price_root.resolve() == RAW_PRICE_ROOT.resolve():
        return {
            "kind": "raw_data_lake",
            "manifest_path": None,
            "manifest_sha256": None,
            "metadata": {},
            "provenance_error": "raw price root has no research price manifest",
        }
    snapshot_root = price_root.resolve().parent.parent
    candidates = (
        snapshot_root / "manifest.json",
        snapshot_root / "price_manifest.json",
        snapshot_root / "metadata.json",
    )
    for path in candidates:
        if path.is_file():
            return {
                "kind": "research_repair_snapshot",
                "manifest_path": str(path),
                "manifest_sha256": _sha256(path),
                "metadata": _load_sidecar(path),
            }
    return {
        "kind": "research_repair_snapshot",
        "manifest_path": None,
        "manifest_sha256": None,
        "metadata": {},
        "provenance_error": "research price snapshot has no manifest/metadata sidecar",
    }


def _load_sidecar(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"read_error": "not_object"}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"read_error": f"{type(exc).__name__}: {exc}"}


def _stored_price_symbols(connection: Any, path: Path) -> tuple[str, ...]:
    """Read the stored symbol identity without loading the OHLC path."""

    columns = _parquet_columns(connection, path)
    if "symbol" not in columns:
        return ()
    rows = connection.execute(
        "SELECT DISTINCT CAST(symbol AS VARCHAR) FROM read_parquet(?) WHERE symbol IS NOT NULL",
        [str(path)],
    ).fetchall()
    return tuple(sorted({str(row[0]).strip().upper() for row in rows if row[0] is not None}))


def _validate_price_snapshot_semantics(
    *,
    price_root: Path,
    price_files: Sequence[Mapping[str, Any]],
    provenance: Mapping[str, Any],
    connection: Any,
) -> dict[str, Any]:
    """Validate the producer manifest against the executable price files."""

    errors: list[str] = []
    metadata = provenance.get("metadata", {})
    if not isinstance(metadata, Mapping):
        metadata = {}
    manifest_universe = metadata.get("universe", {})
    if not isinstance(manifest_universe, Mapping):
        manifest_universe = {}
    manifest_files = manifest_universe.get("files", [])
    if not isinstance(manifest_files, Sequence) or isinstance(manifest_files, (str, bytes)):
        manifest_files = []
    manifest_by_symbol = {
        str(item.get("symbol", "")).upper(): item
        for item in manifest_files
        if isinstance(item, Mapping) and item.get("symbol")
    }
    symbol_entries = metadata.get("symbols", {})
    if not isinstance(symbol_entries, Mapping):
        symbol_entries = {}
    entry_by_symbol = {str(key).upper(): value for key, value in symbol_entries.items()}
    actual_by_symbol = {
        str(item.get("symbol", "")).upper(): item
        for item in price_files
        if item.get("symbol")
    }
    actual_symbols = set(actual_by_symbol)
    manifest_universe_symbols = set(manifest_by_symbol)
    manifest_entry_symbols = set(entry_by_symbol)
    if metadata.get("status") != "complete":
        errors.append(f"manifest_status:{metadata.get('status')}")
    if len(manifest_files) != EXPECTED_PRICE_FILE_COUNT:
        errors.append(
            f"manifest_universe_entries:{len(manifest_files)} != {EXPECTED_PRICE_FILE_COUNT}"
        )
    if len(manifest_by_symbol) != len(manifest_files):
        errors.append("manifest_universe_duplicate_or_invalid_entries")
    if manifest_universe.get("file_count") != EXPECTED_PRICE_FILE_COUNT:
        errors.append(
            "manifest_universe_file_count:"
            f"{manifest_universe.get('file_count')} != {EXPECTED_PRICE_FILE_COUNT}"
        )
    if len(actual_symbols) != EXPECTED_PRICE_FILE_COUNT:
        errors.append(f"actual_price_file_count:{len(actual_symbols)} != {EXPECTED_PRICE_FILE_COUNT}")
    if actual_symbols != manifest_universe_symbols:
        errors.append(
            "manifest_file_universe_mismatch:"
            f"missing={sorted(manifest_universe_symbols - actual_symbols)};"
            f"extra={sorted(actual_symbols - manifest_universe_symbols)}"
        )
    manifest_file_names = {
        str(item.get("file_name", "")).upper()
        for item in manifest_files
        if isinstance(item, Mapping)
    }
    actual_file_names = {
        str(item.get("file_name", "")).upper()
        for item in price_files
        if item.get("file_name")
    }
    if manifest_file_names != actual_file_names:
        errors.append(
            "manifest_file_names_mismatch:"
            f"missing={sorted(manifest_file_names - actual_file_names)};"
            f"extra={sorted(actual_file_names - manifest_file_names)}"
        )
    if actual_symbols != manifest_entry_symbols:
        errors.append(
            "manifest_symbol_entries_mismatch:"
            f"missing={sorted(manifest_entry_symbols - actual_symbols)};"
            f"extra={sorted(actual_symbols - manifest_entry_symbols)}"
        )

    stored_symbols: dict[str, list[str]] = {}
    actual_output_hashes: dict[str, str] = {}
    for symbol in sorted(actual_symbols):
        descriptor = actual_by_symbol[symbol]
        actual_output_hashes[symbol] = str(descriptor.get("sha256", ""))
        entry = entry_by_symbol.get(symbol)
        if not isinstance(entry, Mapping):
            errors.append(f"manifest_symbol_missing:{symbol}")
        else:
            if str(entry.get("symbol", symbol)).upper() != symbol:
                errors.append(f"manifest_symbol_key_mismatch:{symbol}")
            if entry.get("status") != "ready":
                errors.append(f"lifecycle_status:{symbol}:{entry.get('status')}")
            expected_hash = entry.get("output_sha256")
            if not isinstance(expected_hash, str):
                errors.append(f"output_hash_missing:{symbol}")
            elif expected_hash != descriptor.get("sha256"):
                errors.append(f"output_hash_mismatch:{symbol}")
        try:
            stored = _stored_price_symbols(connection, Path(str(descriptor["path"])))
        except Exception as exc:
            stored = ()
            errors.append(f"stored_symbol_read_error:{symbol}:{type(exc).__name__}")
        stored_symbols[symbol] = list(stored)
        if stored != (symbol,):
            errors.append(f"stored_symbol_mismatch:{symbol}:{list(stored)}")

    lit_entry = entry_by_symbol.get("LITUSDT")
    lit_lifecycle = lit_entry.get("lifecycle", {}) if isinstance(lit_entry, Mapping) else {}
    if not isinstance(lit_lifecycle, Mapping):
        lit_lifecycle = {}
    lit_start = lit_lifecycle.get("launch_time_utc") or lit_lifecycle.get(
        "lifecycle_start_utc"
    )
    expected_lit_start = _jsonable(LIT_CURRENT_CONTRACT_START)

    def is_lit_start(value: Any) -> bool:
        try:
            return _utc(value) == LIT_CURRENT_CONTRACT_START
        except (TypeError, ValueError, OverflowError):
            return False

    actual_lit_first_open: str | None = None
    actual_lit_prelaunch_rows = 0
    lit_descriptor = actual_by_symbol.get("LITUSDT")
    if lit_descriptor is not None:
        try:
            lit_row = connection.execute(
                """
                SELECT MIN(open_time),
                       SUM(CASE WHEN open_time < ? THEN 1 ELSE 0 END)
                FROM read_parquet(?)
                """,
                [LIT_CURRENT_CONTRACT_START, str(lit_descriptor["path"])],
            ).fetchone()
            if lit_row and lit_row[0] is not None:
                actual_lit_first_open = _jsonable(_utc(lit_row[0]))
            actual_lit_prelaunch_rows = int(lit_row[1] or 0) if lit_row else 0
        except Exception as exc:
            errors.append(f"lit_segment_read_error:{type(exc).__name__}")
    else:
        errors.append("lit_file_missing:LITUSDT")
    if lit_entry is None:
        errors.append("lit_lifecycle_missing:LITUSDT")
    else:
        if lit_entry.get("status") != "ready":
            errors.append(f"lit_lifecycle_status:{lit_entry.get('status')}")
        if lit_entry.get("lifecycle_policy_id") != LIT_LIFECYCLE_POLICY_ID:
            errors.append(
                f"lit_lifecycle_policy:{lit_entry.get('lifecycle_policy_id')}"
            )
        if not is_lit_start(lit_start):
            errors.append(f"lit_current_contract_start:{lit_start}")
        if actual_lit_first_open != expected_lit_start:
            errors.append(f"lit_actual_first_open:{actual_lit_first_open}")
        if actual_lit_prelaunch_rows:
            errors.append(f"lit_actual_prelaunch_rows:{actual_lit_prelaunch_rows}")
        if not is_lit_start(lit_lifecycle.get("output_first_open_utc")):
            errors.append(
                "lit_output_first_open:"
                f"{lit_lifecycle.get('output_first_open_utc')}"
            )
        if lit_lifecycle.get("output_first_time_matches_launch") is not True:
            errors.append("lit_output_first_time_not_launch")
        lit_missing_bars = lit_lifecycle.get("final_audit_missing_actual_bars")
        try:
            lit_missing_bars_value = int(lit_missing_bars)
        except (TypeError, ValueError):
            lit_missing_bars_value = None
        if lit_missing_bars_value != 0:
            errors.append(
                "lit_lifecycle_missing_bars:"
                f"{lit_missing_bars}"
            )
        if lit_lifecycle.get("clip_rule") != (
            "exclude every source row with open_time before launch_time_utc"
        ):
            errors.append("lit_lifecycle_clip_rule_mismatch")

    return {
        "validated_root": str(price_root.resolve()),
        "manifest_status": metadata.get("status"),
        "actual_symbols": sorted(actual_symbols),
        "manifest_universe_symbols": sorted(manifest_universe_symbols),
        "manifest_symbol_entries": sorted(manifest_entry_symbols),
        "actual_output_hashes": actual_output_hashes,
        "stored_symbols": stored_symbols,
        "lit_actual_first_open_utc": actual_lit_first_open,
        "lit_actual_prelaunch_rows": actual_lit_prelaunch_rows,
        "lit_current_contract_start_utc": expected_lit_start,
        "errors": sorted(set(errors)),
        "validated": not errors,
    }


def _funding_sidecar_summary(sidecar: Mapping[str, Any]) -> dict[str, Any]:
    """Keep the downloader's provenance while avoiding a second raw payload."""

    keys = (
        "protocol",
        "symbol",
        "status",
        "transport_status",
        "data_status",
        "coverage_status",
        "requested_window",
        "range",
        "page_count",
        "request_count",
        "completion_basis",
        "final_page_status",
        "rest_final_page_status",
        "rest_transport_status",
        "errors",
        "invalid_record_count",
        "out_of_window_count",
        "duplicate_timestamp_count",
        "duplicate_timestamp_conflict_count",
        "mark_price_conflict_count",
        "provenance",
        "archive_fallback",
        "checksum_verified",
        "artifact_sha256",
    )
    return {key: _jsonable(sidecar.get(key)) for key in keys if key in sidecar}


def _funding_readiness_errors(descriptor: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not descriptor.get("exists"):
        return ["missing_parquet"]
    if not descriptor.get("sidecar_exists"):
        errors.append("missing_provenance_sidecar")
        return errors
    sidecar = descriptor.get("sidecar", {})
    if sidecar.get("protocol") != PROTOCOL_ID:
        errors.append("sidecar_protocol_mismatch")
    if sidecar.get("symbol") not in {None, descriptor.get("symbol")}:
        errors.append("sidecar_symbol_mismatch")
    if sidecar.get("status") not in {"complete", "reused"}:
        errors.append(f"sidecar_status:{sidecar.get('status')}")
    if sidecar.get("coverage_status") not in {"complete", "empty_range"}:
        errors.append(f"sidecar_coverage:{sidecar.get('coverage_status')}")
    if sidecar.get("final_page_status") not in {
        "complete",
        "complete_archives",
        "empty_response",
    }:
        errors.append(f"sidecar_final_page:{sidecar.get('final_page_status')}")
    if sidecar.get("errors"):
        errors.append("sidecar_has_errors")
    if int(sidecar.get("duplicate_timestamp_conflict_count", 0) or 0):
        errors.append("sidecar_duplicate_conflict")
    requested = sidecar.get("requested_window", {})
    start_ms = int(WARMUP_START.timestamp() * 1000)
    cutoff_plus_one_ms = int(WINDOW_END.timestamp() * 1000) + 1
    if requested.get("start_ms") != start_ms:
        errors.append("sidecar_start_is_not_warmup")
    if int(requested.get("end_exclusive_ms", -1) or -1) < cutoff_plus_one_ms:
        errors.append("sidecar_end_does_not_include_cutoff_boundary")
    artifact_hash = sidecar.get("artifact_sha256")
    if artifact_hash and artifact_hash != descriptor.get("sha256"):
        errors.append("sidecar_artifact_hash_mismatch")
    return errors


def _btc_repair_audit(
    connection: Any,
    price_descriptor: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if price_descriptor is None:
        return {
            "required": True,
            "ready": False,
            "symbol": "BTCUSDT",
            "error": "BTCUSDT is absent from the frozen price universe",
        }
    try:
        bars, audit, _ = _read_price_file(connection, Path(str(price_descriptor["path"])))
    except Exception as exc:
        return {
            "required": True,
            "ready": False,
            "symbol": "BTCUSDT",
            "error": f"{type(exc).__name__}: {exc}",
        }
    expected = _expected_bar_times(BTC_REPAIR_START, BTC_REPAIR_END)
    missing = [timestamp for timestamp in expected if timestamp not in bars]
    return {
        "required": True,
        "ready": not missing,
        "symbol": "BTCUSDT",
        "interval_start_utc": BTC_REPAIR_START,
        "interval_end_utc": BTC_REPAIR_END,
        "expected_bars": len(expected),
        "missing_bars": len(missing),
        "first_missing_bar": missing[0] if missing else None,
        "last_missing_bar": missing[-1] if missing else None,
        "price_duplicate_conflict_timestamps": audit.duplicate_conflict_timestamps,
        "price_invalid_rows": audit.invalid_rows,
        "source_root_kind": (
            "research_repair_snapshot"
            if Path(str(price_descriptor["path"])).resolve().parent != RAW_PRICE_ROOT.resolve()
            else "raw_data_lake"
        ),
    }


def _funding_descriptor(funding_root: Path, symbol: str) -> dict[str, Any]:
    path = funding_root / f"{symbol}.parquet"
    sidecar_path = funding_root / f"{symbol}.json"
    sidecar = _load_sidecar(sidecar_path) if sidecar_path.is_file() else {}
    descriptor: dict[str, Any] = {
        "symbol": symbol,
        "file_name": path.name,
        "path": str(path.resolve()),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else 0,
        "sha256": _sha256(path) if path.is_file() else None,
        "columns": [],
        "parquet_metadata": _parquet_metadata(path) if path.is_file() else {},
        "sidecar_path": str(sidecar_path.resolve()),
        "sidecar_exists": sidecar_path.is_file(),
        "sidecar_sha256": _sha256(sidecar_path) if sidecar_path.is_file() else None,
        "sidecar": _funding_sidecar_summary(sidecar),
    }
    descriptor["readiness_errors"] = _funding_readiness_errors(descriptor)
    return descriptor


def freeze_input_manifest(
    *,
    protocol_path: Path = DEFAULT_PROTOCOL,
    price_root: Path = DEFAULT_PRICE_ROOT,
    funding_root: Path = DEFAULT_FUNDING_ROOT,
) -> dict[str, Any]:
    """Hash protocol, universe, price files and funding cache before outcomes."""

    price_root = _resolve_price_root(Path(price_root))
    funding_root = Path(funding_root)
    protocol = _protocol_check(protocol_path)
    price_files, excluded = _discover_price_files(price_root)
    price_provenance = _price_snapshot_provenance(price_root)
    funding_files = [
        _funding_descriptor(funding_root, item["symbol"]) for item in price_files
    ]
    try:
        connection = _duckdb_connection()
        try:
            for item in price_files:
                item["columns"] = list(_parquet_columns(connection, Path(item["path"])))
            price_provenance["semantic_validation"] = _validate_price_snapshot_semantics(
                price_root=price_root,
                price_files=price_files,
                provenance=price_provenance,
                connection=connection,
            )
            for item in funding_files:
                if item["exists"]:
                    item["columns"] = list(
                        _parquet_columns(connection, Path(item["path"]))
                    )
        finally:
            connection.close()
    except Exception as exc:
        raise RuntimeError(f"could not inspect Parquet schemas: {exc}") from exc

    base = {
        "manifest_version": "annual_profit_manifest_v1",
        "protocol": protocol,
        "input_identity": {
            "venue": "Binance USD-M",
            "contract_identity": "local USDT contract identity not attested",
            "timestamp_timezone": "UTC",
            "price_open_time": "Parquet open_time",
            "price_close_time": "open_time + 5m - 1ms",
            "duplicate_policy": "identical duplicates collapsed; conflicting timestamps invalid",
        },
        "price_root": str(price_root.resolve()),
        "price_root_kind": (
            "research_repair_snapshot"
            if price_root.resolve() != RAW_PRICE_ROOT.resolve()
            else "raw_data_lake"
        ),
        "price_repair_requirement": {
            "symbol": "BTCUSDT",
            "required_interval_start_utc": BTC_REPAIR_START,
            "required_interval_end_utc": BTC_REPAIR_END,
            "source_policy": "supplemental research cache only; never edit raw lake",
        },
        "price_snapshot_provenance": price_provenance,
        "funding_root": str(funding_root.resolve()),
        "universe": {
            "selection": "all local *.parquet files with USDT symbol stem at manifest freeze",
            "price_file_count": len(price_files),
            "expected_price_file_count": EXPECTED_PRICE_FILE_COUNT,
            "excluded_non_usdt_files": excluded,
            "files": price_files,
        },
        "funding": {
            "cache_pattern": "{SYMBOL}.parquet",
            "files": funding_files,
            "present_count": sum(bool(item["exists"]) for item in funding_files),
            "missing_symbols": [item["symbol"] for item in funding_files if not item["exists"]],
            "incomplete_symbols": [
                item["symbol"] for item in funding_files if item.get("readiness_errors")
            ],
            "coverage_attested": False,
            "provenance_required": [
                "source",
                "requested_range_utc",
                "page_count",
                "errors",
                "checksum_if_supplied",
            ],
        },
        "window": {
            "warmup_start_utc": WARMUP_START,
            "start_utc": WINDOW_START,
            "end_utc_exclusive": WINDOW_END,
            "calendar_days": (WINDOW_END - WINDOW_START).days,
            "hourly_decisions_expected": len(_decision_times()),
        },
        "trial_defs": [_trial_definition(spec) for spec in TRIAL_SPECS],
    }
    snapshot_payload = _jsonable(base)
    base["snapshot_id"] = hashlib.sha256(_json_dump(snapshot_payload).encode("utf-8")).hexdigest()
    base["created_at_utc"] = datetime.now(UTC)
    return base


def verify_input_manifest(
    manifest: Mapping[str, Any],
    *,
    protocol_path: Path,
    price_root: Path,
    funding_root: Path,
) -> None:
    """Rehash the frozen inputs and stop rather than mixing snapshots."""

    current = freeze_input_manifest(
        protocol_path=protocol_path,
        price_root=price_root,
        funding_root=funding_root,
    )
    if current["snapshot_id"] != manifest.get("snapshot_id"):
        raise SnapshotChangedError(
            "input snapshot changed after manifest freeze; no outcome files were written"
        )


def audit_inputs(
    *,
    protocol_path: Path = DEFAULT_PROTOCOL,
    price_root: Path = DEFAULT_PRICE_ROOT,
    funding_root: Path = DEFAULT_FUNDING_ROOT,
) -> dict[str, Any]:
    """Inspect and hash inputs without building candidates or account outcomes."""

    try:
        manifest = freeze_input_manifest(
            protocol_path=protocol_path,
            price_root=price_root,
            funding_root=funding_root,
        )
    except Exception as exc:
        return {
            "audit_only": True,
            "outcome_paths_read": False,
            "ready_for_run": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    required_price_columns = {"open_time", "close_time", "open", "high", "low", "close"}
    schema_errors = [
        {
            "symbol": item["symbol"],
            "missing": sorted(required_price_columns - set(item["columns"])),
        }
        for item in manifest["universe"]["files"]
        if required_price_columns - set(item["columns"])
    ]
    missing_funding = manifest["funding"]["missing_symbols"]
    funding_schema_errors = []
    for item in manifest["funding"]["files"]:
        if not item["exists"]:
            continue
        columns = set(item["columns"])
        has_event = bool(
            columns
            & {"event_time", "funding_time", "settlement_time", "timestamp", "time"}
        )
        has_rate = bool(columns & {"funding_rate", "fundingRate", "rate", "value"})
        if not has_event or not has_rate:
            funding_schema_errors.append({"symbol": item["symbol"], "columns": item["columns"]})
    funding_readiness = [
        {"symbol": item["symbol"], "errors": list(item.get("readiness_errors", []))}
        for item in manifest["funding"]["files"]
        if item.get("readiness_errors")
    ]
    connection = _duckdb_connection()
    try:
        btc_descriptor = next(
            (item for item in manifest["universe"]["files"] if item["symbol"] == "BTCUSDT"),
            None,
        )
        btc_repair = _btc_repair_audit(connection, btc_descriptor)
    finally:
        connection.close()
    price_provenance = manifest.get("price_snapshot_provenance", {})
    if price_provenance.get("provenance_error"):
        btc_repair["ready"] = False
        btc_repair["provenance_error"] = price_provenance["provenance_error"]
    static_readiness_errors = _run_static_readiness_errors(manifest)
    ready = (
        not static_readiness_errors
        and bool(btc_repair.get("ready"))
    )
    return {
        "audit_only": True,
        "outcome_paths_read": False,
        "ready_for_run": ready,
        "outcome_run_allowed": ready,
        "full_funding_coverage_ready": (
            ready and not funding_readiness and not funding_schema_errors
        ),
        "price_ready": not static_readiness_errors and bool(btc_repair.get("ready")),
        "funding_cache_complete": not funding_readiness and not funding_schema_errors,
        "price_file_count": manifest["universe"]["price_file_count"],
        "expected_price_file_count": EXPECTED_PRICE_FILE_COUNT,
        "funding_file_count": manifest["funding"]["present_count"],
        "funding_missing_symbols": missing_funding,
        "funding_readiness_errors": funding_readiness,
        "price_schema_errors": schema_errors,
        "funding_schema_errors": funding_schema_errors,
        "static_readiness_errors": static_readiness_errors,
        "btc_repair": btc_repair,
        "price_snapshot_provenance": price_provenance,
        "price_root": manifest["price_root"],
        "snapshot_id": manifest["snapshot_id"],
        "protocol_sha256": manifest["protocol"]["sha256"],
        "manifest": manifest,
    }


def _run_static_readiness_errors(manifest: Mapping[str, Any]) -> list[str]:
    """Return preflight failures that must stop an outcome run."""

    errors: list[str] = []
    universe = manifest.get("universe", {})
    if not isinstance(universe, Mapping):
        universe = {}
    raw_files = universe.get("files", [])
    files = (
        list(raw_files)
        if isinstance(raw_files, Sequence) and not isinstance(raw_files, (str, bytes))
        else []
    )
    if universe.get("price_file_count") != EXPECTED_PRICE_FILE_COUNT:
        errors.append(
            f"price_file_count:{universe.get('price_file_count')} != {EXPECTED_PRICE_FILE_COUNT}"
        )
    required_price_columns = {"open_time", "close_time", "open", "high", "low", "close"}
    for item in files:
        missing = sorted(required_price_columns - set(item.get("columns", [])))
        if missing:
            errors.append(f"price_schema:{item.get('symbol')}:{','.join(missing)}")
    provenance = manifest.get("price_snapshot_provenance", {})
    if not isinstance(provenance, Mapping):
        provenance = {}
    if provenance.get("provenance_error"):
        errors.append(f"price_provenance:{provenance['provenance_error']}")
    metadata = provenance.get("metadata", {})
    if not isinstance(metadata, Mapping):
        metadata = {}
    if metadata.get("status") != "complete":
        errors.append(f"price_snapshot_status:{metadata.get('status')}")
    semantic = provenance.get("semantic_validation", {})
    if isinstance(semantic, Mapping):
        for error in semantic.get("errors", []):
            errors.append(f"price_semantic:{error}")
    else:
        errors.append("price_semantic:missing_validation")
    return errors


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


def _load_symbol_data(
    connection: Any,
    descriptor: Mapping[str, Any],
    funding_root: Path,
) -> tuple[dict[datetime, Bar], BarAudit, tuple[FundingPoint, ...], dict[str, Any], list[FeatureRow], FeatureAudit]:
    price_path = Path(str(descriptor["path"]))
    bars, bar_audit, _ = _read_price_file(connection, price_path)
    funding_path = funding_root / f"{descriptor['symbol']}.parquet"
    try:
        funding, funding_meta, _ = _read_funding_file(
            connection, funding_path, str(descriptor["symbol"])
        )
    except (OSError, ValueError, RuntimeError) as exc:
        # A malformed or incomplete separately prepared cache is a coverage
        # issue, not permission to infer a rate.  Price paths remain usable;
        # funding-dependent signals simply see missing funding features.
        funding = ()
        funding_meta = {
            "symbol": str(descriptor["symbol"]),
            "exists": funding_path.is_file(),
            "source_file": _path_label(funding_path),
            "source_rows": 0,
            "valid_rows": 0,
            "invalid_rows": 0,
            "read_error": f"{type(exc).__name__}: {exc}",
            "parquet_metadata": {},
        }
    features, feature_audit = hourly_features(
        str(descriptor["symbol"]), bars, funding
    )
    return bars, bar_audit, funding, funding_meta, features, feature_audit


def _phase_parameters(
    strategy: StrategySpec,
    candidate: Candidate,
    features: Sequence[FeatureRow],
) -> tuple[datetime | None, datetime | None]:
    if not strategy.phase_exit:
        return None, None
    scheduled = candidate.feature.entry_time + timedelta(hours=strategy.horizon_hours)
    found = find_phase_exit(candidate.feature.entry_time, scheduled, features)
    if found is None:
        return None, None
    return found


def _candidate_outcome(
    *,
    strategy: StrategySpec,
    candidate: Candidate,
    cost_bps: int,
    bars: Mapping[datetime, Bar],
    funding: Sequence[FundingPoint],
    features: Sequence[FeatureRow],
    btc_bars: Mapping[datetime, Bar] | None = None,
    btc_funding: Sequence[FundingPoint] = (),
) -> dict[str, Any]:
    scheduled = candidate.feature.entry_time + timedelta(hours=strategy.horizon_hours)
    phase_exit_time, phase_decision_time = _phase_parameters(strategy, candidate, features)
    if candidate.direction == "hedge":
        coin = evaluate_leg(
            symbol=candidate.symbol,
            direction="short",
            entry_time=candidate.feature.entry_time,
            scheduled_exit_time=scheduled,
            bars=bars,
            funding=funding,
            leverage=strategy.leverage,
            cost_bps=cost_bps,
        )
        btc = evaluate_leg(
            symbol="BTCUSDT",
            direction="long",
            entry_time=candidate.feature.entry_time,
            scheduled_exit_time=scheduled,
            bars=btc_bars or {},
            funding=btc_funding,
            leverage=strategy.leverage,
            cost_bps=cost_bps,
        )
        legs = (coin, btc)
    else:
        leg = evaluate_leg(
            symbol=candidate.symbol,
            direction=candidate.direction,
            entry_time=candidate.feature.entry_time,
            scheduled_exit_time=scheduled,
            bars=bars,
            funding=funding,
            leverage=strategy.leverage,
            cost_bps=cost_bps,
            phase_exit_time=phase_exit_time,
            phase_decision_time=phase_decision_time,
        )
        legs = (leg,)
    return combine_legs(candidate, legs)


def _add_source_provenance(
    outcome: dict[str, Any],
    *,
    price_descriptor: Mapping[str, Any],
    funding_meta: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(outcome)
    result["price_source"] = {
        "symbol": price_descriptor["symbol"],
        "file_name": price_descriptor["file_name"],
        "sha256": price_descriptor["sha256"],
        "open_time_column": "open_time",
        "close_time_rule": "open_time + 5m - 1ms",
    }
    result["funding_source"] = {
        "symbol": funding_meta.get("symbol"),
        "file": funding_meta.get("source_file"),
        "sha256": funding_meta.get("sha256"),
        "exists": bool(funding_meta.get("exists")),
        "source_rows": funding_meta.get("source_rows", 0),
        "valid_rows": funding_meta.get("valid_rows", 0),
        "invalid_rows": funding_meta.get("invalid_rows", 0),
        "read_error": funding_meta.get("read_error"),
        "parquet_metadata": funding_meta.get("parquet_metadata", {}),
        "sidecar": funding_meta.get("sidecar", {}),
    }
    return result


def _trigger_funding_provenance(
    candidate: Candidate,
    strategy: StrategySpec,
    funding_meta: Mapping[str, Any],
    price_descriptor: Mapping[str, Any],
    *,
    btc_funding_meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist the funding evidence attached to each selected trigger."""

    result: dict[str, Any] = {
        "candidate_id": candidate.candidate_id,
        "strategy_id": strategy.strategy_id,
        "entry_rule": strategy.entry_rule,
        "funding_rule": strategy.funding_rule,
        "symbol": candidate.symbol,
        "direction": candidate.direction,
        "feature_cutoff": candidate.feature.feature_cutoff,
        "decision_time": candidate.feature.decision_time,
        "entry_time": candidate.feature.entry_time,
        "feature_values": {
            "pump24h": candidate.feature.ret24h,
            "ret1h": candidate.feature.ret1h,
            "high24h": candidate.feature.high24h,
            "distance_high24h": candidate.feature.distance_high24h,
        },
        "funding_feature": candidate.feature.funding,
        "funding_source": {
            "file": funding_meta.get("source_file"),
            "sha256": funding_meta.get("sha256"),
            "source_rows": funding_meta.get("source_rows", 0),
            "valid_rows": funding_meta.get("valid_rows", 0),
            "invalid_rows": funding_meta.get("invalid_rows", 0),
            "read_error": funding_meta.get("read_error"),
            "sidecar": funding_meta.get("sidecar", {}),
        },
        "price_source": {
            "file": price_descriptor["file_name"],
            "sha256": price_descriptor["sha256"],
        },
        "selected_after_cooldown": True,
    }
    if btc_funding_meta is not None:
        result["hedge_btc_funding_source"] = {
            "file": btc_funding_meta.get("source_file"),
            "sha256": btc_funding_meta.get("sha256"),
            "source_rows": btc_funding_meta.get("source_rows", 0),
            "valid_rows": btc_funding_meta.get("valid_rows", 0),
            "invalid_rows": btc_funding_meta.get("invalid_rows", 0),
            "read_error": btc_funding_meta.get("read_error"),
            "sidecar": btc_funding_meta.get("sidecar", {}),
        }
    return result


def _create_work_table(connection: Any) -> None:
    connection.execute(
        """
        CREATE TABLE candidate_outcomes (
            strategy_id VARCHAR,
            cost_bps INTEGER,
            candidate_id VARCHAR,
            symbol VARCHAR,
            direction VARCHAR,
            decision_time TIMESTAMPTZ,
            entry_time TIMESTAMPTZ,
            exit_time TIMESTAMPTZ,
            pump24h DOUBLE,
            source_row_number BIGINT,
            terminal_status VARCHAR,
            net_return DOUBLE,
            details_json VARCHAR
        )
        """
    )


def _insert_outcomes(connection: Any, rows: Sequence[tuple[Any, ...]]) -> None:
    if rows:
        connection.executemany(
            "INSERT INTO candidate_outcomes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def _account_compact(account: Any) -> dict[str, Any]:
    """Serialize the tested account without its duplicate aliases/lists."""

    def field(name: str, default: Any = None) -> Any:
        return getattr(account, name, default)

    records = []
    for record in field("executed_records", ()):
        trade = record.trade
        records.append(
            {
                "candidate_id": trade.candidate_id,
                "symbol": trade.symbol,
                "tranche_id": record.tranche_id,
                "margin_before": record.margin_before,
                "net_return_on_margin": record.net_return_on_margin,
                "pnl": record.pnl,
                "margin_after": record.margin_after,
                "withdrawn_profit": record.withdrawn_profit,
                "terminal_status": record.terminal_status,
                "realized": record.realized,
                "locked": record.locked,
            }
        )
    cashflows = [
        {
            "timestamp": item.timestamp,
            "flow_type": item.flow_type,
            "amount": item.amount,
            "source": item.source,
            "destination": item.destination,
            "candidate_id": item.candidate_id,
            "tranche_id": item.tranche_id,
            "reason": item.reason,
        }
        for item in field("cashflows", ())
    ]
    events = [
        {
            "timestamp": item.timestamp,
            "event_type": item.event_type,
            "vault": item.vault,
            "reserve": item.reserve,
            "active_equity": item.active_equity,
            "wealth": item.wealth,
            "profit": item.profit,
            "candidate_id": item.candidate_id,
            "symbol": item.symbol,
            "tranche_id": item.tranche_id,
            "terminal_status": item.terminal_status,
            "reason": item.reason,
            "amount": item.amount,
            "realized": item.realized,
            "locked": item.locked,
            "active_trade_exit": item.active_trade_exit,
        }
        for item in field("events", ())
    ]
    vault = float(field("vault", 0.0))
    reserve = float(field("reserve", 0.0))
    active = float(field("active_equity", 0.0))
    return {
        "initial_capital": field("initial_capital"),
        "tranche_count": field("tranche_count"),
        "tranche_seed": field("tranche_seed"),
        "withdraw_profits": field("withdraw_profits"),
        "external_contributions": field("external_contributions"),
        "vault": vault,
        "reserve": reserve,
        "active_equity": active,
        "known_bucket_total": vault + reserve + active,
        "ending_wealth": field("final_wealth"),
        "profit": field("final_profit"),
        "rankable": field("rankable", not field("non_rankable", True)),
        "non_rankable": field("non_rankable"),
        "unresolved_after_entry": field("unresolved_after_entry"),
        "locked_mark_to_cutoff": field("locked_mark_to_cutoff"),
        "capital_occupied_to_cutoff": field("capital_occupied_to_cutoff"),
        "opportunities": field("opportunities"),
        "executed": field("executed"),
        "skipped_overlap": field("skipped_overlap"),
        "skipped_incomplete": field("skipped_incomplete"),
        "skipped_no_capital": field("skipped_no_capital"),
        "skipped_blocked": field("skipped_blocked"),
        "tranches_allocated": field("tranches_allocated"),
        "tranche_burns": list(field("tranche_burns", ())),
        "operating_exhaustion": field("operating_exhaustion"),
        "wealth_ruin": field("wealth_ruin"),
        "closed_event_drawdown": list(field("closed_event_drawdown", ())),
        "max_closed_event_drawdown": field("max_closed_event_drawdown"),
        "drawdown_basis": field("drawdown_basis"),
        "executed_records": records,
        "cashflows": cashflows,
        "events": events,
    }


def _period_label(timestamp: datetime) -> str:
    if timestamp < datetime(2026, 2, 1, tzinfo=UTC):
        return "09/2025-01/2026"
    if timestamp < datetime(2026, 8, 1, tzinfo=UTC):
        return "02/2026-07/2026"
    return "08/2026"


def _group_attribution(rows: Sequence[dict[str, Any]], key: str) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        group = str(row.get(key, "unknown"))
        item = grouped.setdefault(
            group,
            {
                "trades": 0,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "unknown_pnl": 0.0,
                "unknown_margin_usd": 0.0,
                "funding_cashflow_usd": 0.0,
                "fees_usd": 0.0,
            },
        )
        item["trades"] += 1
        item["realized_pnl"] += float(row.get("realized_pnl", 0.0))
        item["unrealized_pnl"] += float(row.get("unrealized_pnl", 0.0))
        unknown = row.get("unknown_pnl", 0.0)
        if unknown is None:
            item["unknown_pnl"] = None
        elif item["unknown_pnl"] is not None:
            item["unknown_pnl"] += float(unknown)
        item["unknown_margin_usd"] += float(row.get("unknown_margin_usd", 0.0) or 0.0)
        item["funding_cashflow_usd"] += float(row.get("funding_cashflow_usd", 0.0))
        item["fees_usd"] += float(row.get("fees_usd", 0.0))
    return {group: grouped[group] for group in sorted(grouped)}


def _attribution(
    account: Any,
    executed_details: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    by_id = {str(item["candidate_id"]): item for item in executed_details}
    pair_rows: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []
    for record in getattr(account, "executed_records", ()):
        candidate_id = record.trade.candidate_id
        detail = by_id.get(candidate_id, {})
        detail_entry_time = detail.get("entry_time")
        if isinstance(detail_entry_time, str):
            try:
                detail_entry_time = _utc(detail_entry_time)
            except (TypeError, ValueError, OverflowError):
                detail_entry_time = None
        funding_usd = 0.0
        fees_usd = 0.0
        for leg in detail.get("legs", []):
            funding_usd += float(leg.get("funding_cashflow_usd", 0.0) or 0.0)
            fees_usd += float(leg.get("fee_usd", 0.0) or 0.0)
        month = detail.get("month", "unknown")
        period = (
            _period_label(detail_entry_time)
            if isinstance(detail_entry_time, datetime)
            else detail.get("period", "unknown")
        )
        pair_accounting = detail.get("component_accounting", {})
        margin_before = float(record.margin_before)
        if pair_accounting:
            realized_pnl = margin_before * float(
                pair_accounting.get("known_realized_return_on_margin", 0.0) or 0.0
            )
            unrealized_pnl = margin_before * float(
                pair_accounting.get("known_unrealized_return_on_margin", 0.0) or 0.0
            )
            unknown_margin_usd = margin_before * float(
                pair_accounting.get("unknown_margin_weight", 0.0) or 0.0
            )
            unknown_pnl = (
                None
                if unknown_margin_usd > 1e-12
                else margin_before
                * float(pair_accounting.get("unknown_return_on_margin", 0.0) or 0.0)
            )
        else:
            pnl = float(record.pnl or 0.0)
            realized_pnl = pnl if record.realized else 0.0
            unrealized_pnl = pnl if not record.realized else 0.0
            unknown_pnl = None if record.locked and record.pnl is None else 0.0
            unknown_margin_usd = margin_before if unknown_pnl is None else 0.0
        pair_row = {
            "candidate_id": candidate_id,
            "symbol": detail.get("symbol", record.trade.symbol),
            "month": month,
            "period": period,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "unknown_pnl": unknown_pnl,
            "unknown_margin_usd": unknown_margin_usd,
            "funding_cashflow_usd": funding_usd,
            "fees_usd": fees_usd,
            "terminal_status": record.terminal_status,
        }
        pair_rows.append(pair_row)

        legs = detail.get("legs", [])
        default_weight = 1.0 / len(legs) if legs else 1.0
        for leg in legs or [{}]:
            accounting = leg.get("accounting", {})
            weight = float(leg.get("margin_weight", default_weight) or 0.0)
            leg_margin = margin_before * weight
            leg_realized = leg_margin * float(
                accounting.get("known_realized_return_on_margin", 0.0) or 0.0
            )
            leg_unrealized = leg_margin * float(
                accounting.get("known_unrealized_return_on_margin", 0.0) or 0.0
            )
            leg_unknown_weight = float(
                accounting.get("unknown_margin_weight", 0.0) or 0.0
            )
            leg_unknown_margin = margin_before * weight * leg_unknown_weight
            leg_unknown = (
                None
                if leg_unknown_margin > 1e-12
                else leg_margin
                * float(accounting.get("unknown_return_on_margin", 0.0) or 0.0)
            )
            component_rows.append(
                {
                    "candidate_id": candidate_id,
                    "symbol": leg.get("symbol", pair_row["symbol"]),
                    "month": month,
                    "period": period,
                    "realized_pnl": leg_realized,
                    "unrealized_pnl": leg_unrealized,
                    "unknown_pnl": leg_unknown,
                    "unknown_margin_usd": leg_unknown_margin,
                    "funding_cashflow_usd": leg.get("funding_cashflow_usd", 0.0) or 0.0,
                    "fees_usd": leg.get("fee_usd", 0.0) or 0.0,
                    "terminal_status": leg.get("terminal_status", record.terminal_status),
                }
            )
    top = sorted(
        pair_rows,
        key=lambda item: (
            -abs(float(item["realized_pnl"] + item["unrealized_pnl"])),
            item["candidate_id"],
        ),
    )[:10]
    realized_total = sum(float(item["realized_pnl"]) for item in pair_rows)
    unrealized_total = sum(float(item["unrealized_pnl"]) for item in pair_rows)
    unknown_margin_total = sum(float(item["unknown_margin_usd"]) for item in pair_rows)
    fully_known = all(item["unknown_pnl"] is not None for item in pair_rows)
    unknown_total = (
        sum(float(item["unknown_pnl"]) for item in pair_rows)
        if fully_known
        else None
    )
    initial_capital = float(getattr(account, "initial_capital", INITIAL_CAPITAL))
    vault = float(getattr(account, "vault", 0.0))
    reserve = float(getattr(account, "reserve", 0.0))
    active_equity = float(getattr(account, "active_equity", 0.0))
    account_bucket_pnl = vault + reserve + active_equity - initial_capital
    component_pnl = realized_total + unrealized_total
    conservation_delta = account_bucket_pnl - component_pnl if fully_known else None
    known_active_equity = active_equity
    if unknown_margin_total > 1e-12:
        unresolved_known_pnl = sum(
            float(item["realized_pnl"] + item["unrealized_pnl"])
            for item in pair_rows
            if item["unknown_pnl"] is None
        )
        known_active_equity = max(
            0.0, active_equity - unknown_margin_total + unresolved_known_pnl
        )
    component_accounting = {
        "fully_known": fully_known,
        "known_realized_pnl": realized_total,
        "known_unrealized_pnl": unrealized_total,
        "unknown_pnl": unknown_total,
        "unknown_margin_usd": unknown_margin_total,
        "known_bucket_total_excluding_unknown_margin": vault
        + reserve
        + known_active_equity,
        "account_bucket_pnl": account_bucket_pnl if fully_known else None,
        "component_pnl": component_pnl if fully_known else None,
        "conservation_delta": conservation_delta,
        "equation": "W+U+E-C = realized_pnl + unrealized_pnl"
        if fully_known
        else "not_evaluable_until_unknown_components_resolve",
    }
    return {
        "month_entry_attribution": _group_attribution(pair_rows, "month"),
        "coin_entry_attribution_static": _group_attribution(component_rows, "symbol"),
        "period_entry_attribution": _group_attribution(pair_rows, "period"),
        "pair_entry_attribution": _group_attribution(pair_rows, "symbol"),
        "largest_absolute_pnl_events": top,
        "attribution_note": "Static entry-month/coin/event attribution; not a coin backtest or causal claim.",
        "realized_pnl": realized_total,
        "unrealized_pnl": unrealized_total,
        "unknown_pnl": unknown_total,
        "unknown_margin_usd": unknown_margin_total,
        "funding_cashflow_usd": sum(float(item["funding_cashflow_usd"]) for item in pair_rows),
        "fees_usd": sum(float(item["fees_usd"]) for item in pair_rows),
        "component_accounting": component_accounting,
    }


def _decorate_executed_detail(
    detail: dict[str, Any],
    record: Any,
) -> dict[str, Any]:
    """Add account-margin USD amounts only after the account selected a path."""

    result = dict(detail)
    margin_before = float(record.margin_before)
    legs = list(result.get("legs", []))
    default_weight = 1.0 / len(legs) if legs else 0.0
    decorated_legs: list[dict[str, Any]] = []
    for leg in legs:
        item = dict(leg)
        margin_weight = float(item.get("margin_weight", default_weight) or 0.0)
        leg_margin = margin_before * margin_weight
        item["margin_usd"] = leg_margin
        funding_return = float(item.get("funding_return_on_margin", 0.0) or 0.0)
        fee_return = item.get("fee_return_on_margin")
        item["funding_cashflow_usd"] = leg_margin * funding_return
        item["fee_usd"] = None if fee_return is None else leg_margin * float(fee_return)
        event_rows = []
        for event in item.get("funding_events", []):
            event_copy = dict(event)
            event_copy["amount_usd"] = leg_margin * float(
                event_copy.get("amount_return_on_margin", 0.0) or 0.0
            )
            event_rows.append(event_copy)
        item["funding_events"] = event_rows
        accounting = dict(item.get("accounting", {}))
        unknown_margin = leg_margin * float(
            accounting.get("unknown_margin_weight", 0.0) or 0.0
        )
        item["accounting_usd"] = {
            "known_realized_pnl": leg_margin
            * float(accounting.get("known_realized_return_on_margin", 0.0) or 0.0),
            "known_unrealized_pnl": leg_margin
            * float(accounting.get("known_unrealized_return_on_margin", 0.0) or 0.0),
            "unknown_pnl": (
                None
                if unknown_margin > 1e-12
                else leg_margin
                * float(accounting.get("unknown_return_on_margin", 0.0) or 0.0)
            ),
            "unknown_margin_usd": unknown_margin,
        }
        decorated_legs.append(item)
    result["legs"] = decorated_legs
    pair_accounting = dict(result.get("component_accounting", {}))
    unknown_margin = margin_before * float(
        pair_accounting.get("unknown_margin_weight", 0.0) or 0.0
    )
    pair_accounting.update(
        {
            "known_realized_pnl": margin_before
            * float(pair_accounting.get("known_realized_return_on_margin", 0.0) or 0.0),
            "known_unrealized_pnl": margin_before
            * float(pair_accounting.get("known_unrealized_return_on_margin", 0.0) or 0.0),
            "unknown_pnl": (
                None
                if unknown_margin > 1e-12
                else margin_before
                * float(pair_accounting.get("unknown_return_on_margin", 0.0) or 0.0)
            ),
            "unknown_margin_usd": unknown_margin,
            "pair_margin_usd": margin_before,
        }
    )
    result["component_accounting"] = pair_accounting
    result["account"] = {
        "tranche_id": record.tranche_id,
        "margin_before": record.margin_before,
        "margin_after": record.margin_after,
        "pnl": record.pnl,
        "withdrawn_profit": record.withdrawn_profit,
        "realized": record.realized,
        "locked": record.locked,
    }
    return result


def _run_trial(
    connection: Any,
    trial: TrialSpec,
    candidate_trade_type: Any,
    simulate_account: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = connection.execute(
        """
        SELECT candidate_id, symbol, entry_time, exit_time, terminal_status,
               net_return, details_json
        FROM candidate_outcomes
        WHERE strategy_id = ? AND cost_bps = ?
        ORDER BY entry_time, pump24h DESC NULLS LAST, symbol,
                 source_row_number, candidate_id
        """,
        [trial.strategy_id, trial.cost_bps],
    ).fetchall()
    trades: list[Any] = []
    detail_by_id: dict[str, dict[str, Any]] = {}
    for candidate_id, symbol, entry_time, exit_time, status, net_return, details_json in rows:
        candidate_id = str(candidate_id)
        detail_by_id[candidate_id] = json.loads(str(details_json))
        trades.append(
            candidate_trade_type(
                signal_time=entry_time,
                exit_time=exit_time,
                symbol=str(symbol),
                net_return_on_margin=(None if net_return is None else float(net_return)),
                terminal_status=str(status),
                candidate_id=candidate_id,
            )
        )
    account = simulate_account(
        trades,
        initial_capital=INITIAL_CAPITAL,
        tranche_count=TRANCHE_COUNT,
        withdraw_profits=trial.withdraw_profits,
    )
    executed_details: list[dict[str, Any]] = []
    for record in getattr(account, "executed_records", ()):
        candidate_id = str(record.trade.candidate_id)
        base = detail_by_id.get(candidate_id)
        if base is not None:
            executed_details.append(_decorate_executed_detail(base, record))
    status_counts = Counter(str(row[4]) for row in rows)
    compact = _account_compact(account)
    attribution = _attribution(account, executed_details)
    compact["component_accounting"] = attribution["component_accounting"]
    return {
        "trial_id": trial.trial_id,
        "strategy_id": trial.strategy_id,
        "cost_bps_roundtrip": trial.cost_bps,
        "withdraw_profits": trial.withdraw_profits,
        "provisional": True,
        "selected_candidate_rows": len(rows),
        "status_counts_before_account_overlap": dict(sorted(status_counts.items())),
        "entry_rejected_rows": status_counts.get("rejected_at_entry", 0),
        "future_gap_unresolved_rows": status_counts.get("unresolved", 0),
        "censored_open_at_cutoff_rows": status_counts.get("open_at_cutoff", 0),
        "funding_missing_rows": sum(
            1 for detail in detail_by_id.values() if bool(detail.get("funding_missing"))
        ),
        "account": compact,
        "attribution": attribution,
        "rankable": bool(compact["rankable"]),
    }, executed_details


def _coverage_counts(connection: Any) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT terminal_status, COUNT(*)
        FROM candidate_outcomes
        WHERE cost_bps = 20
        GROUP BY terminal_status
        ORDER BY terminal_status
        """
    ).fetchall()
    return {
        "candidate_outcome_rows_at_cost20": sum(int(row[1]) for row in rows),
        "candidate_path_status_counts_at_cost20": {str(row[0]): int(row[1]) for row in rows},
        "candidate_outcome_rows_all_costs": int(
            connection.execute("SELECT COUNT(*) FROM candidate_outcomes").fetchone()[0]
        ),
    }


def _cash_baseline() -> dict[str, Any]:
    return {
        "trial_id": "cash_baseline",
        "initial_capital": INITIAL_CAPITAL,
        "vault": 0.0,
        "reserve": INITIAL_CAPITAL,
        "active_equity": 0.0,
        "ending_wealth": INITIAL_CAPITAL,
        "profit": 0.0,
        "trades": 0,
        "note": "Cash is a zero-profit comparator, not an outcome path.",
    }


def _render_report(result: Mapping[str, Any]) -> str:
    lines = [
        "# Luna Max annual profit results — PROVISIONAL",
        "",
        "This artifact is a research-only OHLC/MMR proxy. It is not verified profit, "
        "a causal claim, live execution evidence, or a promotion signal.",
        "",
        "## Frozen scope and provenance",
        "",
        f"- Protocol SHA256: `{result['protocol_sha256']}`.",
        f"- Input snapshot: `{result['snapshot_id']}`.",
        f"- Window: `{WINDOW_START.isoformat()}` through `{WINDOW_END.isoformat()}` exclusive; warmup `{WARMUP_START.isoformat()}`.",
        f"- Universe: {result['coverage']['price_file_count']} local USDT price files; "
        "survivorship/selection bias and local delistings are not resolved.",
        "- Venue label: Binance USD-M; local USDT contract identity is not attested.",
        "- Features are streamed from closed 5m candles only; no future labels, MFE, MAE, or max-return input is used.",
        "- All outcomes are provisional OHLC/MMR 1% proxies; there are no live orders.",
        "",
        "## Registered 40 trials",
        "",
        "Every row below was registered before account simulation: ten fixed strategies × 20/60 bps round-trip cost × withdraw/retain profits.",
        "",
        "| Trial | Profit | Ending wealth | Rankable | Executed | Gap locks | Censored |",
        "|---|---:|---:|:---:|---:|---:|---:|",
    ]
    for trial in result["trials"]:
        account = trial["account"]
        profit = account["profit"]
        wealth = account["ending_wealth"]
        lines.append(
            f"| {trial['trial_id']} | {profit if profit is not None else '—'} | "
            f"{wealth if wealth is not None else '—'} | "
            f"{'yes' if trial['rankable'] else 'no'} | {account['executed']} | "
            f"{trial['future_gap_unresolved_rows']} | {trial['censored_open_at_cutoff_rows']} |"
        )
    lines.extend(
        [
            "",
            "## Cash baseline",
            "",
            "Cash baseline profit is 0. It is kept separate from the 40 strategy paths.",
            "",
            "## Coverage and accounting notes",
            "",
            f"- Price rows valid/invalid/duplicate-conflict: {result['coverage']['price_valid_rows']} / {result['coverage']['price_invalid_rows']} / {result['coverage']['price_duplicate_conflict_timestamps']}.",
            f"- Hourly decisions expected/valid/missing: {result['coverage']['hourly_decisions_expected']} / {result['coverage']['hourly_decisions_valid']} / {result['coverage']['hourly_decisions_missing']}.",
            f"- Funding files present: {result['coverage']['funding_file_count']}; missing: {len(result['coverage']['funding_missing_symbols'])}; funding coverage is not attested.",
            "- A price gap after a known entry locks capital and makes the affected account non-rankable; it is not silently changed into a loss or a reusable exit.",
            "- Funding cashflow is signed by side, uses exact settlement timestamps, excludes settlements at entry/actual exit ties, and is reported separately from feature lag/provenance.",
            "- Monthly, period, coin, and largest-event figures are static entry attribution; they are not isolated coin backtests or causal tests.",
            "- The 02/2026–07/2026 segment is recycled exploratory history; it is not a fresh holdout. No claim is made that the other segments were previously unseen.",
            "- Closed-event drawdown excludes the full intratrade path; censored/unrealized MTM is reported separately.",
            "",
            "## Outcome claims",
            "",
            "No verified-profit, causal-advantage, historical-tier, continuous-mark, true-liquidation, or live-execution claim is made.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(_jsonable(value), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def run_annual(
    *,
    protocol_path: Path = DEFAULT_PROTOCOL,
    price_root: Path = DEFAULT_PRICE_ROOT,
    funding_root: Path = DEFAULT_FUNDING_ROOT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    report_path: Path = DEFAULT_REPORT,
    force: bool = False,
) -> dict[str, Any]:
    """Run the explicit 40-trial annual batch after freezing all inputs."""

    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()) and not force:
        raise FileExistsError(
            f"output directory is non-empty: {output_dir}; use --force only for an intentional new snapshot"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = freeze_input_manifest(
        protocol_path=Path(protocol_path),
        price_root=Path(price_root),
        funding_root=Path(funding_root),
    )
    _write_json(output_dir / "manifest.json", manifest)
    # Rehash immediately after the manifest is written and again before the
    # account engine is called.  A changed source aborts the run.
    verify_input_manifest(
        manifest,
        protocol_path=Path(protocol_path),
        price_root=Path(price_root),
        funding_root=Path(funding_root),
    )
    static_readiness_errors = _run_static_readiness_errors(manifest)
    if static_readiness_errors:
        raise RuntimeError(
            "annual outcome run requires a ready frozen input snapshot: "
            f"{_json_dump(static_readiness_errors)}"
        )

    candidate_counts = {
        strategy.strategy_id: {
            "raw_condition_matches": 0,
            "selected_after_24h_cooldown": 0,
            "selected_symbols": set(),
        }
        for strategy in STRATEGIES
    }
    symbol_audits: list[dict[str, Any]] = []
    btc_data: tuple[dict[datetime, Bar], tuple[FundingPoint, ...]] | None = None
    btc_audit_bundle: dict[str, Any] | None = None
    descriptors = list(manifest["universe"]["files"])
    descriptor_by_symbol = {str(item["symbol"]): item for item in descriptors}
    connection = _duckdb_connection()
    _create_work_table(connection)
    btc_repair = _btc_repair_audit(
        connection, descriptor_by_symbol.get("BTCUSDT")
    )
    if manifest.get("price_snapshot_provenance", {}).get("provenance_error"):
        btc_repair["ready"] = False
        btc_repair["provenance_error"] = manifest["price_snapshot_provenance"][
            "provenance_error"
        ]
    if not btc_repair.get("ready"):
        connection.close()
        raise RuntimeError(
            "BTC research-price repair is required before the annual run: "
            f"{_json_dump(btc_repair)}"
        )
    trigger_path = output_dir / "trigger_funding_provenance.jsonl"
    trigger_temp_path = output_dir / ".trigger_funding_provenance.jsonl.tmp"
    trigger_handle = trigger_temp_path.open("w", encoding="utf-8", newline="\n")
    try:
        if "BTCUSDT" in descriptor_by_symbol:
            btc_descriptor = descriptor_by_symbol["BTCUSDT"]
            btc_bars, btc_bar_audit, btc_funding, btc_funding_meta, btc_features, btc_feature_audit = _load_symbol_data(
                connection, btc_descriptor, Path(funding_root)
            )
            btc_data = (btc_bars, btc_funding)
            btc_audit_bundle = {
                "symbol": "BTCUSDT",
                "price": btc_bar_audit,
                "funding": btc_funding_meta,
                "features": btc_feature_audit,
            }
            symbol_audits.append(btc_audit_bundle)
            btc_features_for_processing = btc_features
        else:
            btc_features_for_processing = []

        for index, descriptor in enumerate(descriptors, start=1):
            symbol = str(descriptor["symbol"])
            if symbol == "BTCUSDT" and btc_data is not None:
                bars, funding = btc_data
                feature_rows = btc_features_for_processing
                assert btc_audit_bundle is not None
                bar_audit = btc_audit_bundle["price"]
                funding_meta = btc_audit_bundle["funding"]
                feature_audit = btc_audit_bundle["features"]
            else:
                bars, bar_audit, funding, funding_meta, feature_rows, feature_audit = _load_symbol_data(
                    connection, descriptor, Path(funding_root)
                )
                symbol_audits.append(
                    {
                        "symbol": symbol,
                        "price": bar_audit,
                        "funding": funding_meta,
                        "features": feature_audit,
                    }
                )
            insert_rows: list[tuple[Any, ...]] = []
            for strategy in STRATEGIES:
                selected, counts = strategy_candidates(strategy, feature_rows)
                aggregate = candidate_counts[strategy.strategy_id]
                aggregate["raw_condition_matches"] += counts["raw_condition_matches"]
                aggregate["selected_after_24h_cooldown"] += counts["selected_after_24h_cooldown"]
                aggregate["selected_symbols"].update(candidate.symbol for candidate in selected)
                for candidate in selected:
                    trigger = _trigger_funding_provenance(
                        candidate,
                        strategy,
                        funding_meta,
                        descriptor,
                        btc_funding_meta=(
                            None
                            if candidate.direction != "hedge" or btc_audit_bundle is None
                            else btc_audit_bundle["funding"]
                        ),
                    )
                    trigger_handle.write(_json_dump(trigger) + "\n")
                    for cost_bps in COST_BPS:
                        outcome = _candidate_outcome(
                            strategy=strategy,
                            candidate=candidate,
                            cost_bps=cost_bps,
                            bars=bars,
                            funding=funding,
                            features=feature_rows,
                            btc_bars=None if btc_data is None else btc_data[0],
                            btc_funding=() if btc_data is None else btc_data[1],
                        )
                        outcome = _add_source_provenance(
                            outcome,
                            price_descriptor=descriptor,
                            funding_meta=funding_meta,
                        )
                        if candidate.direction == "hedge" and "BTCUSDT" in descriptor_by_symbol:
                            btc_meta = symbol_audits[0]["funding"]
                            outcome["hedge_btc_source"] = {
                                "price_file": descriptor_by_symbol["BTCUSDT"]["file_name"],
                                "price_sha256": descriptor_by_symbol["BTCUSDT"]["sha256"],
                                "funding_file": btc_meta.get("source_file"),
                                "funding_metadata": btc_meta.get("parquet_metadata", {}),
                                "funding_sidecar": btc_meta.get("sidecar", {}),
                            }
                        insert_rows.append(
                            (
                                strategy.strategy_id,
                                cost_bps,
                                outcome["candidate_id"],
                                outcome["symbol"],
                                outcome["direction"],
                                outcome["decision_time"],
                                outcome["entry_time"],
                                outcome["exit_time"],
                                outcome["feature_values"]["pump24h"],
                                candidate.feature.source_row_number,
                                outcome["terminal_status"],
                                outcome["net_return_on_margin"],
                                _json_dump(outcome),
                            )
                        )
            _insert_outcomes(connection, insert_rows)
            del bars, funding, feature_rows, insert_rows
            print(
                f"[annual-profit] price_symbol {index}/{len(descriptors)} {symbol}",
                flush=True,
            )
    except Exception:
        trigger_handle.close()
        trigger_temp_path.unlink(missing_ok=True)
        connection.close()
        raise
    trigger_handle.close()

    try:
        verify_input_manifest(
            manifest,
            protocol_path=Path(protocol_path),
            price_root=Path(price_root),
            funding_root=Path(funding_root),
        )
    except Exception:
        trigger_temp_path.unlink(missing_ok=True)
        connection.close()
        raise
    trigger_temp_path.replace(trigger_path)
    CandidateTrade, simulate_account = _load_account_api()
    coverage = _coverage_counts(connection)
    price_valid_rows = sum(int(item["price"].valid_rows) for item in symbol_audits)
    price_invalid_rows = sum(int(item["price"].invalid_rows) for item in symbol_audits)
    price_conflict_rows = sum(
        int(item["price"].duplicate_conflict_timestamps) for item in symbol_audits
    )
    hourly_expected = sum(int(item["features"].expected_decisions) for item in symbol_audits)
    hourly_valid = sum(int(item["features"].valid_decisions) for item in symbol_audits)
    coverage.update(
        {
            "price_file_count": len(descriptors),
            "funding_file_count": int(manifest["funding"]["present_count"]),
            "funding_missing_symbols": list(manifest["funding"]["missing_symbols"]),
            "price_valid_rows": price_valid_rows,
            "price_invalid_rows": price_invalid_rows,
            "price_duplicate_conflict_timestamps": price_conflict_rows,
            "price_duplicate_identical_rows": sum(
                int(item["price"].duplicate_identical_rows) for item in symbol_audits
            ),
            "hourly_decisions_expected": hourly_expected,
            "hourly_decisions_valid": hourly_valid,
            "hourly_decisions_missing": hourly_expected - hourly_valid,
            "hourly_decision_missing_by_symbol": {
                item["symbol"]: int(item["features"].missing_decisions)
                for item in symbol_audits
            },
            "btc_repair": btc_repair,
            "price_snapshot_provenance": manifest.get("price_snapshot_provenance", {}),
            "symbol_audits": symbol_audits,
        }
    )
    _write_json(output_dir / "coverage.json", coverage)
    _write_json(
        output_dir / "trial_definitions.json",
        [_trial_definition(item) for item in TRIAL_SPECS],
    )

    trial_records: list[dict[str, Any]] = []
    executed_path = output_dir / "executed_leg_details.jsonl"
    with executed_path.open("w", encoding="utf-8", newline="\n") as handle:
        for trial in TRIAL_SPECS:
            record, executed_details = _run_trial(
                connection, trial, CandidateTrade, simulate_account
            )
            trial_records.append(record)
            for detail in executed_details:
                handle.write(_json_dump({"trial_id": trial.trial_id, **detail}) + "\n")
    connection.close()
    final = {
        "artifact": "luna_max_annual_profit_backtest",
        "artifact_version": "annual_profit_v1",
        "status": "provisional_research_only",
        "protocol_sha256": manifest["protocol"]["sha256"],
        "snapshot_id": manifest["snapshot_id"],
        "window_start_utc": WINDOW_START,
        "window_end_utc_exclusive": WINDOW_END,
        "warmup_start_utc": WARMUP_START,
        "initial_capital": INITIAL_CAPITAL,
        "tranche_count": TRANCHE_COUNT,
        "tranche_seed": TRANCHE_SEED,
        "maintenance_ratio_assumed": MAINTENANCE_RATIO,
        "strategy_count": len(STRATEGIES),
        "trial_count": len(trial_records),
        "all_40_trials_included": len(trial_records) == 40,
        "artifact_files": [
            "manifest.json",
            "coverage.json",
            "trial_definitions.json",
            "trigger_funding_provenance.jsonl",
            "executed_leg_details.jsonl",
            "accounts.json",
        ],
        "cash_baseline": _cash_baseline(),
        "candidate_counts": {
            key: {
                "raw_condition_matches": value["raw_condition_matches"],
                "selected_after_24h_cooldown": value["selected_after_24h_cooldown"],
                "selected_symbols": len(value["selected_symbols"]),
            }
            for key, value in candidate_counts.items()
        },
        "coverage": coverage,
        "trials": trial_records,
        "outcome_claims": {
            "verified_profit": False,
            "causal_advantage": False,
            "live_trading": False,
            "historical_liquidation_attestation": False,
            "all_results_provisional": True,
        },
    }
    _write_json(output_dir / "accounts.json", final)
    final_report = dict(final)
    final_report["protocol_sha256"] = manifest["protocol"]["sha256"]
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_report(final_report), encoding="utf-8")
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="explicitly execute the 40 outcome trials")
    parser.add_argument("--audit-inputs", action="store_true", help="audit and hash inputs only")
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--price-root", type=Path, default=DEFAULT_PRICE_ROOT)
    parser.add_argument("--funding-root", type=Path, default=DEFAULT_FUNDING_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--force", action="store_true", help="overwrite an existing backtest output directory")
    args = parser.parse_args()
    if args.run and args.audit_inputs:
        parser.error("choose --run or --audit-inputs, not both")
    if args.run:
        result = run_annual(
            protocol_path=args.protocol,
            price_root=args.price_root,
            funding_root=args.funding_root,
            output_dir=args.output_dir,
            report_path=args.report,
            force=args.force,
        )
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "output_dir": _path_label(args.output_dir),
                    "report": _path_label(args.report),
                    "trial_count": result["trial_count"],
                    "all_40_trials_included": result["all_40_trials_included"],
                    "snapshot_id": result["snapshot_id"],
                },
                sort_keys=True,
            )
        )
        return 0
    audit = audit_inputs(
        protocol_path=args.protocol,
        price_root=args.price_root,
        funding_root=args.funding_root,
    )
    print(json.dumps(_jsonable(audit), indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
