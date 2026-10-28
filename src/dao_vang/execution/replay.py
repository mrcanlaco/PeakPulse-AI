"""Chronological, shared-wallet Cross replay; all open PnL stays in equity.

Input frames require point-in-time marks, rules and maintenance tiers. This is
a sampled-mark simulation, not an assertion of exact exchange liquidations.
"""

from __future__ import annotations

import math
from datetime import datetime

from .contracts import TradeSignal, digest, floor_step, target_profit, tp_price


def maintenance(notional: float, tiers: list[dict]) -> float:
    for tier in tiers:
        if tier["floor"] <= notional < tier["cap"]:
            value = notional * tier["rate"] - tier["deduction"]
            if not math.isfinite(value) or value < 0:
                raise ValueError("invalid_maintenance_tier")
            return value
    raise ValueError("maintenance_tier_missing")


def replay(frames: list[dict], config, manifest_id: str, *, selector="model") -> dict:
    cash, peak, max_dd = 500.0, 500.0, 0.0
    positions, seen, funding_ids = {}, set(), set()
    journal, curve, failures = [], [], set()
    paused, liquidated = False, False
    previous = None
    for frame in frames:
        at = datetime.fromisoformat(frame["at"])
        if at.tzinfo is None or (previous is not None and at <= previous):
            raise ValueError("replay_time_order")
        previous = at
        market = frame["market"]
        for symbol, item in market.items():
            for key in ("mark", "bid", "ask"):
                if not math.isfinite(item[key]) or item[key] <= 0:
                    raise ValueError("replay_price_invalid")
            if item["bid"] > item["ask"]:
                raise ValueError("replay_crossed_book")
        if not frame.get("coverage_verified"):
            failures.add("source_coverage_unverified")
        if set(positions) - set(market):
            failures.add("open_position_price_gap")
            journal.append({"at": frame["at"], "kind": "capital_locked_missing_price"})
            continue
        for funding in frame.get("funding", []):
            identity = funding["id"]
            if identity in funding_ids:
                continue
            funding_ids.add(identity)
            pos = positions.get(funding["symbol"])
            settlement = datetime.fromisoformat(funding["at"])
            if settlement > at:
                raise ValueError("future_funding")
            if pos and pos["opened_at"] < settlement:
                amount = pos["qty"] * funding["mark"] * funding["rate"]
                if not math.isfinite(amount):
                    raise ValueError("invalid_funding")
                cash += amount
                pos["funding"] += amount
                journal.append(
                    {
                        "at": funding["at"],
                        "kind": "funding",
                        "amount": amount,
                        "symbol": funding["symbol"],
                    }
                )
        unrealized = sum(
            p["qty"] * (p["entry"] - market[s]["mark"]) for s, p in positions.items()
        )
        equity = cash + unrealized
        required = 0.0
        try:
            required = sum(
                maintenance(p["qty"] * market[s]["mark"], market[s]["tiers"])
                for s, p in positions.items()
            )
        except (KeyError, ValueError):
            failures.add("maintenance_coverage_missing")
        if (
            positions
            and equity <= required
            and "maintenance_coverage_missing" not in failures
        ):
            # Account-level liquidation, not an artificial per-position stop.
            for symbol, pos in list(positions.items()):
                price = market[symbol]["ask"] * (1 + config.max_slippage_bps / 10000)
                if "liquidation_fee_rate" not in market[symbol]:
                    failures.add("liquidation_fee_missing")
                fee = (
                    pos["qty"]
                    * price
                    * (config.fee_rate + market[symbol].get("liquidation_fee_rate", 0))
                )
                cash += pos["qty"] * (pos["entry"] - price) - fee
                journal.append(
                    {
                        "at": frame["at"],
                        "kind": "liquidation",
                        "symbol": symbol,
                        "fee": fee,
                    }
                )
            positions.clear()
            liquidated, paused = True, True
        # TP only executes on an observed executable ask, not an OHLC touch.
        for symbol, pos in list(positions.items()):
            info = market[symbol]
            target = tp_price(
                pos["qty"],
                pos["entry"],
                pos["target"],
                pos["entry_fee"],
                pos["funding"],
                config.fee_rate,
                pos["tick"],
            )
            settlement = info.get("settlement_price")
            if settlement is not None or info["ask"] <= target:
                price = float(settlement) if settlement is not None else target
                pnl = (
                    pos["qty"] * (pos["entry"] - price)
                    - pos["qty"] * price * config.fee_rate
                )
                cash += pnl
                journal.append(
                    {
                        "at": frame["at"],
                        "kind": "settlement" if settlement is not None else "tp",
                        "symbol": symbol,
                        "net_pnl": pnl - pos["entry_fee"] + pos["funding"],
                        "holding_hours": (at - pos["opened_at"]).total_seconds() / 3600,
                    }
                )
                del positions[symbol]
        equity = cash + sum(
            p["qty"] * (p["entry"] - market[s]["mark"]) for s, p in positions.items()
        )
        peak = max(peak, equity)
        dd = 1 - equity / peak
        max_dd = max(max_dd, dd)
        if dd >= 0.20 - 1e-12:
            paused = True
        for raw in frame.get("signals", []):
            signal = TradeSignal.model_validate(raw)
            if signal.event_id in seen:
                continue
            seen.add(signal.event_id)
            reason = None
            info = market.get(signal.symbol)
            if signal.manifest_id != manifest_id:
                reason = "manifest_mismatch"
            elif not signal.observed_at <= at < signal.expires_at:
                reason = "signal_not_current"
            elif not signal.eligible and (
                selector == "model"
                or not signal.reasons
                or not set(signal.reasons)
                <= {"below_frozen_threshold", "signal_not_confirmed"}
            ):
                reason = "model_rejected"
            elif paused or liquidated or failures:
                reason = "entries_paused_or_unverified"
            elif (
                signal.symbol in positions
                or len(positions) >= config.max_open_positions
            ):
                reason = "position_limit"
            elif info is None or not info.get("trading"):
                reason = "symbol_unavailable"
            if reason:
                journal.append(
                    {
                        "at": frame["at"],
                        "kind": "rejected",
                        "event_id": signal.event_id,
                        "reason": reason,
                    }
                )
                continue
            assert info is not None
            try:
                rules = info["rules"]
                bid, ask = info["bid"], info["ask"]
                if (ask - bid) / bid * 10000 > config.max_spread_bps:
                    raise ValueError("spread_too_wide")
                qty = floor_step(
                    25 / (ask * (1 + config.max_slippage_bps / 10000)),
                    rules["market_step"],
                )
                qty = floor_step(qty, rules["step_size"])
                price = bid * (1 - config.max_slippage_bps / 10000)
                if (
                    not max(rules["min_qty"], rules["market_min_qty"])
                    <= qty
                    <= min(rules["max_qty"], rules["market_max_qty"])
                    or qty * price < rules["min_notional"]
                ):
                    raise ValueError("exchange_minimum_or_precision")
                if info.get("bid_depth_qty", 0) < qty:
                    raise ValueError("insufficient_depth")
                reserved = sum(
                    p["qty"] * market[s]["mark"] / 5 for s, p in positions.items()
                )
                if (
                    equity - reserved
                    < qty * price / 5 + qty * price * config.fee_rate * 2
                ):
                    raise ValueError("insufficient_margin")
                target = target_profit(qty, price, signal.atr, config)
                fee = qty * price * config.fee_rate
                cash -= fee
                equity -= fee
                positions[signal.symbol] = {
                    "qty": qty,
                    "entry": price,
                    "target": target,
                    "entry_fee": fee,
                    "funding": 0.0,
                    "tick": rules["tick_size"],
                    "opened_at": at,
                    "event_id": signal.event_id,
                }
                journal.append(
                    {
                        "at": frame["at"],
                        "kind": "entry",
                        "symbol": signal.symbol,
                        "qty": qty,
                        "price": price,
                        "target": target,
                    }
                )
            except (ValueError, KeyError) as exc:
                journal.append(
                    {
                        "at": frame["at"],
                        "kind": "rejected",
                        "event_id": signal.event_id,
                        "reason": str(exc),
                    }
                )
        equity = cash + sum(
            p["qty"] * (p["entry"] - market[s]["mark"]) for s, p in positions.items()
        )
        max_dd = max(max_dd, 1 - equity / peak)
        curve.append(
            {
                "at": frame["at"],
                "equity": equity,
                "wallet": cash,
                "unrealized": equity - cash,
                "maintenance_margin": required,
                "positions": len(positions),
                "paused": paused,
            }
        )
    return {
        "manifest_id": manifest_id,
        "input_checksum": digest(frames),
        "kind": "historical_replay",
        "method": "sampled_mark_cross_account",
        "financially_verified": False,
        "promotion_eligible": False,
        "coverage_failures": sorted(failures),
        "selector": selector,
        "curve": curve,
        "journal": journal,
        "ending_equity": curve[-1]["equity"]
        if curve and curve[-1]["at"] == frames[-1]["at"]
        else None,
        "max_drawdown": max_dd,
        "liquidated": liquidated,
        "open_positions": positions,
        "open_positions_marked": bool(curve) and not failures,
    }


def compare_replay(frames, config, manifest_id):
    return {
        "model": replay(frames, config, manifest_id),
        "baseline": replay(
            frames, config, manifest_id, selector="all_qualified_opportunities"
        ),
        "cash_baseline": 500.0,
    }
