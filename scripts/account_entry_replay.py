"""Offline entry allocation research, forked from account_scaled_replay.

Legacy policies retain exact behavior. New policies explicitly allow keeping
planned adds after trail activation, or waiting for a favorable move and bounce.
The frozen earlier engine is unchanged so previous experiments remain auditable.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections import Counter

from dao_vang.execution.contracts import floor_step, target_profit


def simulate(
    times,
    signals,
    prices,
    rules,
    funding_loader,
    config,
    *,
    maintenance_ratio=0.01,
    research_policy=None,
):
    """prices(symbol) -> {time: {mark, entry_open}}; funding_loader -> rows.

    All times are integer epoch milliseconds. A funding row is (time,rate,mark).
    Missing a held position's current mark invalidates the remaining path.
    """
    policy = research_policy or {}
    parts = policy.get("entry_parts", 1)
    entry_mode = policy.get("entry_mode", "single")
    trailing = policy.get("trailing", False)
    budget = policy.get("position_notional", config.max_position_usd)
    if parts not in [1, 3] or entry_mode not in ["single", "time", "favorable", "pullback"]:
        raise ValueError("invalid_staged_entry_policy")
    if (parts == 1) != (entry_mode == "single"):
        raise ValueError("entry_mode_parts_mismatch")
    cancel_on_activation = policy.get("cancel_adds_on_trail_activation", True)
    if not isinstance(cancel_on_activation, bool):
        raise ValueError("invalid_cancel_adds_on_trail_activation")
    if entry_mode == "pullback" and not (
        math.isfinite(policy.get("entry_step_atr", 0))
        and policy.get("entry_step_atr", 0) > 0
        and math.isfinite(policy.get("pullback_atr", 0))
        and policy.get("pullback_atr", 0) > 0
    ):
        raise ValueError("invalid_pullback_parameters")
    if not math.isfinite(budget) or budget <= 0:
        raise ValueError("invalid_position_budget")
    if trailing and not (
        0.001 <= policy.get("callback_fraction", 0) <= 0.10
        and policy.get("activation_atr", 0) > 0
        and policy.get("observation_minutes", 5) in [5, 15]
    ):
        raise ValueError("invalid_trailing_policy")
    fixed_tp = policy.get("fixed_tp_usdt")
    unrepresentable_tp_action = policy.get("unrepresentable_tp_action", "invalidate")
    if unrepresentable_tp_action not in ["invalidate", "pause_hold"]:
        raise ValueError("invalid_unrepresentable_tp_action")
    research_tp_limit = policy.get("research_tp_limit", 5)
    if not math.isfinite(research_tp_limit) or not 5 <= research_tp_limit <= 15:
        raise ValueError("research_tp_limit_outside_5_to_15")
    if fixed_tp is not None and (
        not math.isfinite(fixed_tp) or not 0.5 <= fixed_tp <= research_tp_limit
    ):
        raise ValueError("research_fixed_tp_outside_registered_range")
    wallet = peak = config.initial_equity
    positions, seen, schedules, funding_seen = {}, set(), {}, set()
    curve, journal, errors = [], [], []
    rejected = Counter()
    paused, max_dd = False, 0.0
    total_fees = total_funding = realized = 0.0
    stop_event = None
    funding_index = {}

    def pending_notional(pos):
        return (
            0
            if pos.get("adds_cancelled")
            else (parts - pos["filled_parts"]) * budget / parts
        )

    def capital_reserved(marks, exclude=None):
        return sum(
            p["qty"] * marks[s] / config.leverage
            + pending_notional(p) / config.leverage
            + 2 * config.fee_rate * pending_notional(p)
            for s, p in positions.items()
            if s != exclude
        )

    def order_size(symbol, reference):
        rule = rules[symbol]
        slip = config.max_slippage_bps / 10000
        price = reference * (1 - slip)
        qty = floor_step(budget / parts / (reference * (1 + slip)), rule["market_step"])
        qty = floor_step(qty, rule["step_size"])
        valid = (
            max(rule["min_qty"], rule["market_min_qty"])
            <= qty
            <= min(rule["max_qty"], rule["market_max_qty"])
            and qty * price >= rule["min_notional"]
        )
        return qty, price, valid

    for at in times:
        marks = {}
        for symbol in positions:
            point = prices(symbol).get(at)
            if not point or not math.isfinite(point["mark"]) or point["mark"] <= 0:
                errors.append(f"missing_held_price:{symbol}:{at}")
                break
            if "execution_close" in point and not math.isfinite(
                point["execution_close"]
            ):
                errors.append(f"missing_held_trade_price:{symbol}:{at}")
                break
            marks[symbol] = point["mark"]
        if errors:
            break
        funding_before_step = {s: p["funding"] for s, p in positions.items()}
        for symbol, pos in positions.items():
            schedule = schedules[symbol]
            index = funding_index[symbol]
            while index < len(schedule) and schedule[index][0] <= at:
                settled, rate, mark = schedule[index]
                index += 1
                key = (symbol, settled)
                if pos["opened_at"] < settled <= at and key not in funding_seen:
                    if not all(math.isfinite(x) for x in [rate, mark]) or mark <= 0:
                        errors.append(f"invalid_funding:{symbol}:{settled}")
                        break
                    funding_seen.add(key)
                    amount = pos["qty"] * mark * rate
                    wallet += amount
                    pos["funding"] += amount
                    total_funding += amount
                    journal.append(
                        dict(at=settled, kind="funding", symbol=symbol, amount=amount)
                    )
            funding_index[symbol] = index
        if errors:
            break
        equity = wallet + sum(
            p["qty"] * (p["entry"] - marks[s]) for s, p in positions.items()
        )
        peak = max(peak, equity)
        max_dd = max(max_dd, 1 - equity / peak)
        if (
            config.entry_pause_drawdown is not None
            and equity <= peak * (1 - config.entry_pause_drawdown) + 1e-10
        ):
            paused = True
        if paused:
            for pos in positions.values():
                pos["adds_cancelled"] = True
        required = sum(
            p["qty"] * marks[s] * maintenance_ratio for s, p in positions.items()
        )
        if positions and equity <= required:
            errors.append(f"maintenance_proxy_breached:{at}")
            stop_event = dict(
                at=at,
                equity=equity,
                maintenance_proxy=required,
                maintenance_ratio=maintenance_ratio,
                marks=dict(marks),
            )
            # Do not invent a liquidation fill, fee, or a surviving balance.
            break
        flatten = bool(
            policy.get("flatten_drawdown")
            and equity <= peak * (1 - policy["flatten_drawdown"])
        )
        if flatten:
            paused = True
        closed_this_step = set()
        for symbol, pos in list(positions.items()):
            point = prices(symbol)[at]
            net_mark = (
                pos["qty"] * (pos["entry"] - marks[symbol])
                - pos["entry_fee"]
                + pos["funding"]
                - pos["qty"] * marks[symbol] * config.fee_rate
            )
            reason = None
            if flatten:
                reason = "account_stop"
            elif (
                policy.get("loss_usdt")
                and net_mark <= -policy["loss_usdt"] * pos["filled_parts"] / parts
            ):
                reason = "loss_stop"
            elif (
                policy.get("stop_atr")
                and marks[symbol] >= pos["entry"] + policy["stop_atr"] * pos["atr"]
            ):
                reason = "atr_stop"
            elif (
                policy.get("max_hold_hours")
                and at - pos["opened_at"] >= policy["max_hold_hours"] * 3600000
            ):
                reason = "time_exit"
            if (
                reason is None
                and trailing
                and (at - pos["opened_at"])
                % (policy.get("observation_minutes", 5) * 60000)
                == 0
            ):
                observed = point.get("execution_close", math.nan)
                if not math.isfinite(observed) or observed <= 0:
                    errors.append(f"missing_trailing_price:{symbol}:{at}")
                    break
                pos["trail_low"] = min(pos["trail_low"], observed)
                if not pos["trail_active"] and observed <= pos["activation_price"]:
                    pos["trail_active"] = True
                    if cancel_on_activation:
                        pos["adds_cancelled"] = True
                    journal.append(
                        dict(
                            at=at,
                            kind="trail_activated",
                            symbol=symbol,
                            event_id=pos["event_id"],
                            price=observed,
                            qty=pos["qty"],
                        )
                    )
                if pos["trail_active"] and observed >= pos["trail_low"] * (
                    1 + policy["callback_fraction"]
                ):
                    reason = "trailing_exit"
            if reason:
                # Observe the completed Mark bar, then buy at the next trade
                # bar's open plus adverse slippage. Never fill at the stop level.
                reference = point.get("entry_open", math.nan)
                if not math.isfinite(reference) or reference <= 0:
                    if at == times[-1]:
                        pos["pending_exit"] = reason
                        continue  # terminal inventory stays marked, not fictionally closed
                    errors.append(f"missing_exit_price:{symbol}:{at}")
                    break
                exit_price = reference * (1 + config.max_slippage_bps / 10000)
                fee = pos["qty"] * exit_price * config.fee_rate
                gross = pos["qty"] * (pos["entry"] - exit_price)
                net = gross - fee - pos["entry_fee"] + pos["funding"]
                wallet += gross - fee
                total_fees += fee
                realized += net
                journal.append(
                    dict(
                        at=at,
                        kind=reason,
                        symbol=symbol,
                        price=exit_price,
                        qty=pos["qty"],
                        net=net,
                        held_hours=(at - pos["opened_at"]) / 3600000,
                        event_id=pos["event_id"],
                        filled_parts=pos["filled_parts"],
                        entry_notional=pos["entry_notional"],
                    )
                )
                del positions[symbol]
                closed_this_step.add(symbol)
                remaining_equity = wallet + sum(
                    p["qty"] * (p["entry"] - marks[s]) for s, p in positions.items()
                )
                if remaining_equity <= 0:
                    # A market gap can exhaust equity before the requested exit.
                    # Do not present an impossible negative cash balance as a
                    # successfully executed stop that rescued the account.
                    errors.append(f"risk_exit_equity_exhausted:{symbol}:{at}")
                    break
        if errors:
            break
        for symbol, pos in [] if trailing else list(positions.items()):
            tp_funding = (
                funding_before_step[symbol]
                if policy.get("tp_fill") == "bar_low"
                else pos["funding"]
            )
            raw_target = (
                pos["qty"] * pos["entry"]
                - pos["target"]
                - pos["entry_fee"]
                + tp_funding
            ) / (pos["qty"] * (1 + config.fee_rate))
            if math.isfinite(raw_target) and raw_target <= 0 and unrepresentable_tp_action == "pause_hold":
                paused = True
                if "tp_unrepresentable_since" not in pos:
                    pos["tp_unrepresentable_since"] = at
                    journal.append(dict(at=at, kind="tp_unrepresentable", symbol=symbol,
                                        event_id=pos["event_id"], raw_target=raw_target,
                                        reason="accumulated_costs_exceed_representable_net_target"))
                continue
            if not math.isfinite(raw_target) or raw_target <= 0:
                errors.append(f"tp_price_unrepresentable:{symbol}:{at}")
                break
            target = floor_step(
                raw_target,
                pos["tick"],
            )
            if target <= 0:
                if unrepresentable_tp_action == "pause_hold":
                    paused = True
                    if "tp_unrepresentable_since" not in pos:
                        pos["tp_unrepresentable_since"] = at
                        journal.append(dict(at=at, kind="tp_unrepresentable", symbol=symbol,
                                            event_id=pos["event_id"], raw_target=raw_target,
                                            reason="target_below_tick"))
                    continue
                errors.append(f"tp_price_unrepresentable:{symbol}:{at}")
                break
            if "tp_unrepresentable_since" in pos:
                since = pos.pop("tp_unrepresentable_since")
                journal.append(dict(at=at, kind="tp_representable_again", symbol=symbol,
                                    event_id=pos["event_id"], unavailable_since=since, target=target))
            # A close crossing is a research fill convention, not a proven fill.
            execution_close = prices(symbol)[at].get("execution_close", marks[symbol])
            if policy.get("tp_fill") == "bar_low":
                # Sensitivity only: a previously resting TP may be touched
                # inside the completed bar. Do not use end-of-bar funding to
                # retroactively move that order; assume funding through the
                # bar end, with unknown actual fill/settlement ordering.
                execution_close = prices(symbol)[at].get("execution_low", math.nan)
                if not math.isfinite(execution_close) or execution_close <= 0:
                    errors.append(f"missing_trade_low:{symbol}:{at}")
                    break
            if execution_close <= target:
                fee = pos["qty"] * target * config.fee_rate
                gross = pos["qty"] * (pos["entry"] - target)
                wallet += gross - fee
                total_fees += fee
                net = gross - fee - pos["entry_fee"] + pos["funding"]
                realized += net
                journal.append(
                    dict(
                        at=at,
                        kind="tp",
                        symbol=symbol,
                        price=target,
                        net=net,
                        held_hours=(at - pos["opened_at"]) / 3600000,
                        event_id=pos["event_id"],
                        filled_parts=pos["filled_parts"],
                        entry_notional=pos["entry_notional"],
                    )
                )
                del positions[symbol]
        if errors:
            break
        # Add at most one tranche per step, based only on the completed close.
        # A gap at next open may worsen the fill; never inspect that future price
        # to decide whether the signal to add was favorable.
        for symbol, pos in list(positions.items()):
            if (
                parts == 1
                or pos["filled_parts"] >= parts
                or pos["adds_cancelled"]
                or paused
            ):
                continue
            if at - pos["opened_at"] > policy.get("add_expiry_hours", 6) * 3600000:
                pos["adds_cancelled"] = True
                journal.append(
                    dict(
                        at=at,
                        kind="adds_expired",
                        symbol=symbol,
                        event_id=pos["event_id"],
                    )
                )
                continue
            point = prices(symbol)[at]
            observed = point.get("execution_close", math.nan)
            if entry_mode == "pullback" and math.isfinite(observed):
                pos["pullback_low"] = min(pos["pullback_low"], observed)
            if not math.isfinite(observed) or observed > pos["entry"]:
                continue
            if entry_mode == "time":
                eligible = (
                    at - pos["opened_at"]
                    >= pos["filled_parts"]
                    * policy.get("entry_interval_minutes", 30)
                    * 60000
                )
            elif entry_mode == "pullback":
                # Completed prices only: first require a new favorable move,
                # then a bounce that remains below the current average entry.
                eligible = (
                    pos["pullback_low"] <= pos["first_entry"]
                    - pos["filled_parts"] * policy["entry_step_atr"] * pos["atr"]
                    and observed >= pos["pullback_low"] + policy["pullback_atr"] * pos["atr"]
                )
            else:
                eligible = (
                    observed
                    <= pos["first_entry"]
                    - pos["filled_parts"]
                    * policy.get("entry_step_atr", 0.5)
                    * pos["atr"]
                )
            if not eligible or at == times[-1]:
                continue
            reference = point.get("entry_open", math.nan)
            if not math.isfinite(reference) or reference <= 0:
                errors.append(f"missing_add_price:{symbol}:{at}")
                break
            qty, entry, valid = order_size(symbol, reference)
            if not valid:
                rejected["add_exchange_minimum_or_precision"] += 1
                pos["adds_cancelled"] = True
                continue
            fee = qty * entry * config.fee_rate
            eq_now = wallet + sum(
                p["qty"] * (p["entry"] - marks[s]) for s, p in positions.items()
            )
            other = capital_reserved(marks, exclude=symbol)
            existing_margin = pos["qty"] * marks[symbol] / config.leverage
            future = (parts - pos["filled_parts"] - 1) * budget / parts
            if (
                eq_now - other - existing_margin
                < qty * entry / config.leverage
                + 2 * fee
                + future / config.leverage
                + 2 * config.fee_rate * future
            ):
                rejected["add_insufficient_margin"] += 1
                pos["adds_cancelled"] = True
                continue
            pos["entry"] = (pos["qty"] * pos["entry"] + qty * entry) / (
                pos["qty"] + qty
            )
            pos["qty"] += qty
            pos["entry_fee"] += fee
            pos["entry_notional"] += qty * entry
            pos["filled_parts"] += 1
            if entry_mode == "pullback":
                # A second add requires another favorable excursion and bounce.
                pos["pullback_low"] = observed
            pos["target"] = pos["planned_target"] * pos["filled_parts"] / parts
            wallet -= fee
            total_fees += fee
            journal.append(
                dict(
                    at=at,
                    kind="entry_add",
                    symbol=symbol,
                    event_id=pos["event_id"],
                    price=entry,
                    qty=qty,
                    notional=qty * entry,
                    fee=fee,
                    part=pos["filled_parts"],
                )
            )
        if errors:
            break
        for signal in signals.get(at, []):
            symbol, event = signal["symbol"], signal["event_id"]
            if event in seen:
                rejected["duplicate_episode"] += 1
                continue
            seen.add(event)
            if paused:
                rejected["drawdown_paused"] += 1
                continue
            if symbol in closed_this_step:
                rejected["same_step_risk_exit"] += 1
                continue
            if symbol in positions or len(positions) >= config.max_open_positions:
                rejected["position_limit"] += 1
                continue
            rule = rules.get(symbol)
            point = prices(symbol).get(at)
            if (
                not rule
                or not point
                or not math.isfinite(point.get("entry_open", math.nan))
                or not math.isfinite(point.get("mark", math.nan))
                or point["mark"] <= 0
            ):
                rejected["entry_price_or_rules_missing"] += 1
                continue
            reference = point["entry_open"]
            if reference <= 0:
                rejected["entry_price_invalid"] += 1
                continue
            slip = config.max_slippage_bps / 10000
            entry = reference * (1 - slip)
            qty, entry, valid = order_size(symbol, reference)
            if not valid:
                rejected["exchange_minimum_or_precision"] += 1
                continue
            if policy.get("require_split_eligibility") and parts == 1:
                probe = floor_step(
                    budget / 3 / (reference * (1 + slip)), rule["market_step"]
                )
                probe = floor_step(probe, rule["step_size"])
                if (
                    not max(rule["min_qty"], rule["market_min_qty"])
                    <= probe
                    <= min(rule["max_qty"], rule["market_max_qty"])
                    or probe * entry < rule["min_notional"]
                ):
                    rejected["split_eligibility_filter"] += 1
                    continue
            try:
                planned_qty = floor_step(
                    budget / (reference * (1 + slip)), rule["market_step"]
                )
                planned_qty = floor_step(planned_qty, rule["step_size"])
                target = (
                    fixed_tp
                    if fixed_tp is not None
                    else target_profit(planned_qty, entry, signal["atr"], config)
                )
            except ValueError:
                rejected["target_below_minimum"] += 1
                continue
            eq_now = wallet + sum(
                p["qty"] * (p["entry"] - marks[s]) for s, p in positions.items()
            )
            if trailing and entry - policy["activation_atr"] * signal["atr"] <= 0:
                rejected["activation_price_invalid"] += 1
                continue
            reserved = capital_reserved(marks)
            fee = qty * entry * config.fee_rate
            future = (parts - 1) * budget / parts
            if (
                eq_now - reserved
                < qty * entry / config.leverage
                + 2 * fee
                + future / config.leverage
                + 2 * config.fee_rate * future
            ):
                rejected["insufficient_margin"] += 1
                continue
            if symbol not in schedules:
                try:
                    schedules[symbol] = funding_loader(symbol)
                except Exception as exc:
                    errors.append(f"funding_unavailable:{symbol}:{type(exc).__name__}")
                    break
            funding_index[symbol] = bisect_right(
                [row[0] for row in schedules[symbol]], at
            )
            if not math.isfinite(point.get("mark", math.nan)) or point["mark"] <= 0:
                errors.append(f"entry_mark_missing:{symbol}:{at}")
                break
            wallet -= fee
            total_fees += fee
            positions[symbol] = dict(
                qty=qty,
                entry=entry,
                target=target / parts,
                planned_target=target,
                filled_parts=1,
                entry_notional=qty * entry,
                adds_cancelled=parts == 1,
                first_entry=entry,
                activation_price=entry
                - policy.get("activation_atr", 0) * signal["atr"],
                trail_low=entry,
                trail_active=False,
                entry_fee=fee,
                funding=0.0,
                tick=rule["tick_size"],
                opened_at=at,
                event_id=event,
                atr=signal["atr"],
            )
            if entry_mode == "pullback":
                positions[symbol]["pullback_low"] = entry
            marks[symbol] = point["mark"]
            journal.append(
                dict(
                    at=at,
                    kind="entry",
                    symbol=symbol,
                    price=entry,
                    qty=qty,
                    target=target / parts,
                    event_id=event,
                    margin=qty * entry / config.leverage,
                )
            )
        if errors:
            break
        unrealized = sum(
            p["qty"] * (p["entry"] - marks[s]) for s, p in positions.items()
        )
        equity = wallet + unrealized
        peak = max(peak, equity)
        max_dd = max(max_dd, 1 - equity / peak)
        if (
            config.entry_pause_drawdown is not None
            and equity <= peak * (1 - config.entry_pause_drawdown) + 1e-10
        ):
            paused = True
        curve.append(
            dict(
                at=at,
                equity=equity,
                wallet=wallet,
                unrealized=unrealized,
                positions=len(positions),
                paused=paused,
                committed_margin=capital_reserved(marks),
            )
        )
    ending = (
        curve[-1]["equity"]
        if curve and curve[-1]["at"] == times[-1] and not errors
        else None
    )
    opened = []
    for symbol, pos in positions.items():
        last = curve[-1]["at"] if curve else times[0]
        point = prices(symbol).get(last)
        opened.append(
            dict(
                symbol=symbol,
                **pos,
                last_mark=point["mark"] if point else None,
                held_days=(last - pos["opened_at"]) / 86400000,
                unrealized=pos["qty"] * (pos["entry"] - point["mark"])
                if point
                else None,
            )
        )
    return dict(
        financially_verified=False,
        promotion_eligible=False,
        method="reconstructed_signals_close_price_diagnostic",
        max_positions=config.max_open_positions,
        initial_equity=config.initial_equity,
        ending_equity=ending,
        pnl=ending - config.initial_equity if ending is not None else None,
        sampled_max_drawdown=max_dd,
        entries=sum(x["kind"] == "entry" for x in journal),
        tp_exits=sum(x["kind"] == "tp" for x in journal),
        fees=total_fees,
        funding=total_funding,
        closed_trade_net=realized,
        entry_paused=paused,
        errors=errors,
        stop_event=stop_event,
        rejections=dict(rejected),
        open_positions=opened,
        curve=curve,
        journal=journal,
        liquidation_status="unknown_historical_brackets_and_marks_missing",
    )
