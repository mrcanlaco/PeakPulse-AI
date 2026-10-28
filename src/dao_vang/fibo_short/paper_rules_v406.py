"""Frozen M6B paper-order rules. Pure calculations; no exchange/order side effects.

Input candidates must come from the audited closed-candle M6B collector. This
module checks portfolio admission and quantity feasibility; it is not a second
signal detector or an exchange order adapter. Account-specific filters must be
supplied by the caller. Historical results use continuous quantities; these
extra paper checks may reject trades and must be measured prospectively.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Any


@dataclass(frozen=True)
class PaperPolicy:
    version: str = "4.0.6"
    sizing_mode: str = "fixed_1x"
    base_notional_frac: float = .20
    max_positions: int = 5
    max_total_notional_frac: float = 1.0
    max_total_sl_risk_frac: float = .12
    cost_budget_bps: float = 40.0
    max_signal_age_seconds: int = 300


def _d(value: Any) -> Decimal:
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("Nonfinite price, balance or quantity")
    return number


def _utc(value: str | datetime) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if dt.tzinfo is None:
        raise ValueError("Explicit UTC offset required")
    return dt.astimezone(timezone.utc)


def plan_paper_entry(candidate: dict, state: dict, filters: dict, *, now: str | datetime,
                     policy: PaperPolicy = PaperPolicy()) -> dict:
    """Return a paper proposal or an explicit rejection; never consume a wave.

    state: equity, positions, allowed_symbols (current monthly PIT membership),
    consumed_waves and cooldown_until keyed by 'symbol|tf', plus paused.
    Each open position supplies remaining_qty, entry_price, mark_price,
    active_stop and static_notional_frac_remaining.
    filters: step_size, min_qty, max_qty, min_notional and tick_size. Caller must
    use the applicable market/limit filters, not quantityPrecision/pricePrecision.
    """
    def reject(reason: str) -> dict:
        return {"status": "REJECTED", "reason": reason, "paper_only": True}

    if policy.sizing_mode not in ("fixed_1x", "conviction_150_115_080"):
        raise ValueError("Unknown sizing policy")
    decision, clock = _utc(candidate["decision_time"]), _utc(now)
    age = (clock - decision).total_seconds()
    if age < 0 or age > policy.max_signal_age_seconds:
        return reject("FUTURE_OR_STALE_SIGNAL")
    if state["paused"]:
        return reject("PAPER_SESSION_PAUSED")
    if state["universe_month"] != decision.strftime("%Y-%m"):
        return reject("STALE_MONTHLY_UNIVERSE")
    if not candidate["closed_candles_complete"]:
        return reject("INCOMPLETE_CANDLE_DATA")
    if candidate["symbol"] not in state["allowed_symbols"]:
        return reject("OUTSIDE_MONTHLY_PIT_UNIVERSE")
    if "m6_f4_expanded" not in candidate["eligible_milestones"]:
        return reject("M6B_GATE_NOT_PASSED")
    key = candidate["symbol"] + "|" + candidate["tf"]
    if candidate["wave_key"] in state.get("consumed_waves", {}).get(key, []):
        return reject("WAVE_ALREADY_CONSUMED")
    until = state.get("cooldown_until", {}).get(key)
    if until and decision < _utc(until):
        return reject("COOLDOWN")
    positions = state["positions"]
    if len(positions) >= policy.max_positions:
        return reject("SLOT_CAP")
    equity = _d(state["equity"])
    if equity <= 0:
        return reject("NONPOSITIVE_EQUITY")
    step, tick = _d(filters["step_size"]), _d(filters["tick_size"])
    if step <= 0 or tick <= 0:
        raise ValueError("Positive step_size and tick_size required")
    lo, hi, minimum = _d(filters["min_qty"]), _d(filters["max_qty"]), _d(filters["min_notional"])
    if lo <= 0 or hi < lo or minimum < 0:
        raise ValueError("Invalid quantity/notional filters")
    entry = (_d(candidate["entry_price"]) / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
    stop = (_d(candidate["sl_m6"]) / tick).to_integral_value(rounding=ROUND_CEILING) * tick
    targets = [(_d(candidate[k]) / tick).to_integral_value(rounding=ROUND_CEILING) * tick
               for k in ("tp1", "tp2", "tp3")]
    if not stop > entry > targets[0] > targets[1] > targets[2] > 0:
        return reject("INVALID_SHORT_PRICE_LADDER")
    score = _d(candidate["full_conviction_score"])
    mult = Decimal(1) if policy.sizing_mode == "fixed_1x" else (
        Decimal("1.50") if score >= 80 else Decimal("1.15") if score >= 68 else Decimal(".80"))
    qty = (equity * _d(policy.base_notional_frac) * mult / entry / step).to_integral_value(rounding=ROUND_FLOOR) * step
    if not lo <= qty <= hi or qty * entry < minimum:
        return reject("ENTRY_FILTERS")
    legs = [(qty * w / step).to_integral_value(rounding=ROUND_FLOOR) * step for w in (Decimal(".50"), Decimal(".30"))]
    legs.append(qty - sum(legs))
    if any(q < lo or q > hi or q * price < minimum for q, price in zip(legs, targets)):
        return reject("PARTIAL_EXIT_FILTERS")
    entry_notional, mark_notional, static_frac, open_risk, static_risk = [Decimal(0) for _ in range(5)]
    for pos in positions:
        rem, ep, mark, sl, static = [_d(pos[k]) for k in (
            "remaining_qty", "entry_price", "mark_price", "active_stop", "static_notional_frac_remaining")]
        if rem < 0 or min(ep, mark, sl) <= 0 or static < 0:
            raise ValueError("Invalid open position")
        entry_notional += rem * ep
        mark_notional += rem * mark
        static_frac += static
        open_risk += rem * max(Decimal(0), sl - ep, sl - mark)
        static_risk += static * max(Decimal(0), (sl - ep) / ep)
    new_frac = qty * entry / equity
    if max(static_frac, entry_notional / equity, mark_notional / equity) + new_frac > _d(policy.max_total_notional_frac):
        return reject("NOTIONAL_CAP")
    risk_frac = qty * (stop - entry) / equity
    if max(static_risk, open_risk / equity) + risk_frac > _d(policy.max_total_sl_risk_frac):
        return reject("STOP_RISK_CAP")
    return {"status": "PAPER_PROPOSAL", "paper_only": True, "policy_version": policy.version,
            "symbol": candidate["symbol"], "tf": candidate["tf"], "wave_key": candidate["wave_key"],
            "decision_time": decision.isoformat(), "sizing_mode": policy.sizing_mode,
            "entry_reference": str(entry), "initial_stop": str(stop), "quantity": str(qty),
            "target_prices": list(map(str, targets)), "target_quantities": list(map(str, legs)),
            "stop_after_tp1": str(entry), "stop_after_tp2": str(targets[0]),
            "notional_fraction": float(new_frac), "initial_stop_risk_fraction": float(risk_frac),
            "cost_budget_bps": policy.cost_budget_bps,
            "state_commit_rule": "Consume wave and occupy slot only after confirmed simulated fill; cooldown until actual exit and at least 4h since entry",
            "limitations": "Not an exchange order; stop gaps, actual fees/funding and partial fills require paper event accounting"}
