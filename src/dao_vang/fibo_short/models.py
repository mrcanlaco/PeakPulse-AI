"""Data models for the Confirmed Reversal & Fibonacci Short branch (H4/D1 -> H1)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SignalStage = Literal[
    "FIRED_CONFIRMED_SHORT",
    "ARMED_IN_FIBO_ZONE",
    "WATCHING_PULLBACK",
    "INVALIDATED",
]

ConfirmationTier = Literal[
    "COMBO_1_2",
    "CANDLE_PATTERN_1",
    "BREAK_STRUCTURE_2",
    "UNCONFIRMED",
]


@dataclass(frozen=True, slots=True)
class SwingImpulseWave:
    """Confirmed bearish reversal wave on a higher timeframe (H4 or D1)."""

    symbol: str
    timeframe: Literal["4h", "1d"]
    prior_low_price: float
    prior_low_time: str
    prior_pump_pct: float
    swing_high_price: float
    swing_high_time: str
    reversal_candle_time: str
    reversal_candle_open: float
    reversal_candle_close: float
    reversal_candle_bearish: bool
    impulse_low_price: float
    impulse_low_time: str
    impulse_drop_pct: float
    bars_since_swing_high: int
    bars_since_impulse_low: int
    wave_ker: float = 1.0
    impulse_ker: float = 1.0
    peak_ewmac_16_64: float = 0.0
    cur_accel_4_16: float = 0.0
    pst_pass: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FibonacciLevels:
    """Fibonacci retracement and extension price grid (1.0 = Swing High, 0.0 = Impulse Low)."""

    level_1000: float  # Swing High (SL reference)
    level_0786: float
    level_0618: float  # Golden Pocket upper
    level_0500: float  # Golden Pocket lower
    level_0382: float
    level_0236: float
    level_0000: float  # Impulse Low (TP1)
    ext_1272: float    # Fibonacci Extension 1.272 (TP2)
    ext_1618: float    # Fibonacci Extension 1.618 (TP3)
    wave_range: float
    level_0886: float = 0.0  # Optimal tight SL reference (0.886 Fibo)

    def to_dict(self) -> dict[str, float]:
        return {
            "level_1000": round(self.level_1000, 8),
            "level_0886": round(self.level_0886 if self.level_0886 > 0 else (self.level_0000 + 0.886 * self.wave_range), 8),
            "level_0786": round(self.level_0786, 8),
            "level_0618": round(self.level_0618, 8),
            "level_0500": round(self.level_0500, 8),
            "level_0382": round(self.level_0382, 8),
            "level_0236": round(self.level_0236, 8),
            "level_0000": round(self.level_0000, 8),
            "ext_1272": round(self.ext_1272, 8),
            "ext_1618": round(self.ext_1618, 8),
            "wave_range": round(self.wave_range, 8),
        }


@dataclass(frozen=True, slots=True)
class H1ConfirmationResult:
    """H1 confirmation candle evaluation inside the Fibonacci retracement zone."""

    candle_time: str
    open: float
    high: float
    low: float
    close: float
    is_red_candle: bool
    no_gain_1h: bool
    price_ret_1h: float
    touched_fibo_zone: bool
    max_pullback_fibo_ratio: float
    current_fibo_ratio: float
    cond1_bearish_pattern: bool
    pattern_name: str
    pattern_name_vi: str
    cond2_break_prev_low: bool
    break_description_vi: str
    confirmed: bool
    confirmation_tier: ConfirmationTier
    reason_vi: str
    pullback_vol_ratio: float = 1.0
    h1_body_ratio: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FiboTradeSetup:
    """Actionable trade setup derived from Fibonacci levels and H1 confirmation."""

    entry_price: float
    entry_zone_low: float
    entry_zone_high: float
    entry_zone_str: str
    stop_loss: float
    stop_loss_pct: float
    tp1: float
    tp1_pct: float
    tp2: float
    tp2_pct: float
    tp3: float
    tp3_pct: float
    rr_tp1: float
    rr_tp2: float
    rr_tp3: float
    atr_1h: float
    conviction_tier: str = "B"
    recommended_risk_mult: float = 1.0
    sl_m6: float = 0.0
    sl_m6_pct: float = 0.0
    rr_m6_tp1: float = 0.0
    rr_m6_tp2: float = 0.0
    recommended_notional_pct: float = 20.0
    risk_budget_pct: float = 0.5
    max_notional_pct: float = 20.0
    sl_within_cap: bool = True
    max_hold_hours: int = 72

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_price": round(self.entry_price, 8),
            "entry_zone_low": round(self.entry_zone_low, 8),
            "entry_zone_high": round(self.entry_zone_high, 8),
            "entry_zone": self.entry_zone_str,
            "stop_loss": round(self.stop_loss, 8),
            "stop_loss_pct": round(self.stop_loss_pct, 4),
            "sl_m6": round(self.sl_m6 if self.sl_m6 > 0 else self.stop_loss, 8),
            "sl_m6_pct": round(self.sl_m6_pct if self.sl_m6_pct > 0 else self.stop_loss_pct, 4),
            "tp1": round(self.tp1, 8),
            "tp1_pct": round(self.tp1_pct, 4),
            "tp2": round(self.tp2, 8),
            "tp2_pct": round(self.tp2_pct, 4),
            "tp3": round(self.tp3, 8),
            "tp3_pct": round(self.tp3_pct, 4),
            "rr_ratio": round(self.rr_tp2, 2),
            "rr_tp1": round(self.rr_tp1, 2),
            "rr_tp2": round(self.rr_tp2, 2),
            "rr_tp3": round(self.rr_tp3, 2),
            "rr_m6_tp1": round(self.rr_m6_tp1 if self.rr_m6_tp1 > 0 else self.rr_tp1, 2),
            "rr_m6_tp2": round(self.rr_m6_tp2 if self.rr_m6_tp2 > 0 else self.rr_tp2, 2),
            "atr_1h": round(self.atr_1h, 8),
            "conviction_tier": self.conviction_tier,
            "recommended_risk_mult": round(self.recommended_risk_mult, 2),
            "recommended_notional_pct": round(self.recommended_notional_pct, 2),
            "risk_budget_pct": round(self.risk_budget_pct, 2),
            "max_notional_pct": round(self.max_notional_pct, 2),
            "sl_within_cap": bool(self.sl_within_cap),
            "max_hold_hours": int(self.max_hold_hours),
        }


@dataclass(slots=True)
class FiboShortSignal:
    """Complete signal record for the Confirmed Reversal & Fibonacci Short branch."""

    id: str
    symbol: str
    higher_timeframe: Literal["4h", "1d"]
    confirm_timeframe: Literal["1h"]
    stage: SignalStage
    score: float
    signal_time: str
    current_price: float
    wave: SwingImpulseWave
    fibo_levels: FibonacciLevels
    h1_confirmation: H1ConfirmationResult
    trade_setup: FiboTradeSetup
    explanation_vi: list[str] = field(default_factory=list)
    outcome: dict[str, Any] | None = None
    telegram_sent: bool = False
    conviction_tier: str = "B"
    recommended_risk_mult: float = 1.0
    alpha_layers: dict[str, Any] = field(default_factory=dict)
    eligible_milestones: list[str] = field(default_factory=list)
    matched_policies: list[str] = field(default_factory=list)
    primary_policy: str = "watch_only"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "higher_timeframe": self.higher_timeframe,
            "confirm_timeframe": self.confirm_timeframe,
            "stage": self.stage,
            "score": round(self.score, 2),
            "conviction_tier": self.conviction_tier,
            "recommended_risk_mult": round(self.recommended_risk_mult, 2),
            "signal_time": self.signal_time,
            "current_price": round(self.current_price, 8),
            "wave": self.wave.to_dict(),
            "fibo_levels": self.fibo_levels.to_dict(),
            "h1_confirmation": self.h1_confirmation.to_dict(),
            "trade_setup": self.trade_setup.to_dict(),
            "alpha_layers": dict(self.alpha_layers),
            "eligible_milestones": list(self.eligible_milestones),
            "matched_policies": list(self.matched_policies),
            "primary_policy": self.primary_policy,
            "explanation_vi": list(self.explanation_vi),
            "outcome": self.outcome,
            "telegram_sent": self.telegram_sent,
        }
