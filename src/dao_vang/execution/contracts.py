"""Versioned, finite inputs shared by simulation and exchange execution."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical(value) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str
    )


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def floor_step(value: float, step: str) -> float:
    size = Decimal(step)
    if not size.is_finite() or size <= 0 or not math.isfinite(value) or value < 0:
        raise ValueError("invalid_precision")
    return float(
        (Decimal(str(value)) / size).to_integral_value(rounding=ROUND_DOWN) * size
    )


class ClosedBar(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    closed_at: datetime
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)

    @field_validator("closed_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("timezone_required")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def prices(self):
        if not self.low <= self.close <= self.high:
            raise ValueError("invalid_bar")
        return self


def atr14(bars: list[ClosedBar], at: datetime) -> float:
    # Wilder ATR seeded with the first 14 true ranges; exactly 15 closed bars.
    bars = bars[-15:]
    if len(bars) != 15 or any(b.closed_at > at for b in bars):
        raise ValueError("atr_requires_15_closed_bars")
    if bars[-1].closed_at != at.replace(minute=0, second=0, microsecond=0):
        raise ValueError("atr_stale")
    ranges = []
    for prev, current in zip(bars, bars[1:]):
        if (current.closed_at - prev.closed_at).total_seconds() != 3600:
            raise ValueError("atr_gap")
        ranges.append(
            max(
                current.high - current.low,
                abs(current.high - prev.close),
                abs(current.low - prev.close),
            )
        )
    return sum(ranges) / 14


class TradeSignal(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    event_id: str = Field(min_length=1, max_length=160)
    symbol: str = Field(pattern=r"^[A-Z0-9]{2,30}USDT$")
    manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: str = Field(min_length=1)
    side: Literal["SHORT"] = "SHORT"
    observed_at: datetime
    expires_at: datetime
    reference_price: float = Field(gt=0)
    atr: float = Field(gt=0)
    eligible: bool
    reasons: list[str] = Field(default_factory=list)

    @field_validator("observed_at", "expires_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("timezone_required")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def timing(self):
        if not 0 < (self.expires_at - self.observed_at).total_seconds() <= 900:
            raise ValueError("invalid_signal_lifetime")
        return self


def target_profit(qty: float, price: float, atr: float, config) -> float:
    cost = qty * price * (2 * config.fee_rate + config.max_slippage_bps / 10000)
    target = min(config.tp_max_usdt, qty * config.atr_multiplier * atr - cost)
    if not math.isfinite(target) or target < config.tp_min_usdt:
        raise ValueError("target_below_minimum")
    return target


def tp_price(
    qty: float,
    entry: float,
    target: float,
    entry_fee: float,
    funding_received: float,
    exit_fee_rate: float,
    tick: str,
) -> float:
    # short PnL = q*(entry-exit) - entry_fee - q*exit*fee + funding.
    price = (qty * entry - target - entry_fee + funding_received) / (
        qty * (1 + exit_fee_rate)
    )
    price = floor_step(price, tick)
    if price <= 0 or price >= entry:
        raise ValueError("invalid_take_profit_price")
    return price


class StrategyManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["cross_short_atr_v1"] = "cross_short_atr_v1"
    frozen_at: datetime
    model_id: str
    label_version: str
    threshold: float = Field(ge=0, le=1, allow_inf_nan=False)
    files: dict[str, str]
    policy: dict
    source_policy: dict = Field(default_factory=dict)

    @field_validator("frozen_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("timezone_required")
        return value.astimezone(timezone.utc)

    @property
    def identity(self):
        return digest(self.model_dump(mode="json"))

    def verify(self, root: Path, config) -> None:
        if not self.files:
            raise ValueError("manifest_without_files")
        for relative, checksum in self.files.items():
            path = (root / relative).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                raise ValueError("manifest_file_missing")
            if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
                raise ValueError("manifest_checksum_mismatch")
        if self.policy != policy_contract(config):
            raise ValueError("execution_policy_mismatch")


def policy_contract(config) -> dict:
    names = (
        "initial_equity",
        "margin_per_position",
        "leverage",
        "margin_type",
        "max_position_usd",
        "entry_pause_drawdown",
        "tp_min_usdt",
        "tp_max_usdt",
        "atr_period",
        "atr_multiplier",
        "fee_rate",
        "max_spread_bps",
        "max_slippage_bps",
        "signal_ttl_seconds",
    )
    return {name: getattr(config, name) for name in names}


def source_contract(config) -> dict:
    names = (
        "frozen_model_id",
        "scan_mode",
        "max_coins",
        "min_volume_usd",
        "min_price_change_pct",
        "exclude_stablecoins",
        "max_feature_age_minutes",
        "min_data_quality_score",
        "threshold_policy_version",
    )
    return {name: getattr(config, name) for name in names}
