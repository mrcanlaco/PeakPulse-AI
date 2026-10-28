"""Small offline research account, with explicit unknown-data termination.

OHLC closes are proxies for mark/ask. A maintenance-ratio stress assumption is
not a historical Binance bracket. Results can never qualify live activation.
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
    fixed_tp = policy.get("fixed_tp_usdt")
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
            elif policy.get("loss_usdt") and net_mark <= -policy["loss_usdt"]:
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
        for symbol, pos in list(positions.items()):
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
            if not math.isfinite(raw_target) or raw_target <= 0:
                errors.append(f"tp_price_unrepresentable:{symbol}:{at}")
                break
            target = floor_step(
                raw_target,
                pos["tick"],
            )
            if target <= 0:
                errors.append(f"tp_price_unrepresentable:{symbol}:{at}")
                break
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
                    )
                )
                del positions[symbol]
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
            qty = floor_step(
                policy.get("position_notional", config.max_position_usd)
                / (reference * (1 + slip)),
                rule["market_step"],
            )
            qty = floor_step(qty, rule["step_size"])
            if (
                not max(rule["min_qty"], rule["market_min_qty"])
                <= qty
                <= min(rule["max_qty"], rule["market_max_qty"])
                or qty * entry < rule["min_notional"]
            ):
                rejected["exchange_minimum_or_precision"] += 1
                continue
            try:
                target = (
                    fixed_tp
                    if fixed_tp is not None
                    else target_profit(qty, entry, signal["atr"], config)
                )
            except ValueError:
                rejected["target_below_minimum"] += 1
                continue
            eq_now = wallet + sum(
                p["qty"] * (p["entry"] - marks[s]) for s, p in positions.items()
            )
            reserved = sum(
                p["qty"] * marks[s] / config.leverage for s, p in positions.items()
            )
            fee = qty * entry * config.fee_rate
            if eq_now - reserved < qty * entry / config.leverage + 2 * fee:
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
                target=target,
                entry_fee=fee,
                funding=0.0,
                tick=rule["tick_size"],
                opened_at=at,
                event_id=event,
                atr=signal["atr"],
            )
            marks[symbol] = point["mark"]
            journal.append(
                dict(
                    at=at,
                    kind="entry",
                    symbol=symbol,
                    price=entry,
                    qty=qty,
                    target=target,
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
                committed_margin=sum(
                    p["qty"] * marks[s] / config.leverage for s, p in positions.items()
                ),
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
