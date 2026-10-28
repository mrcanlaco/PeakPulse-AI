"""Causal virtual entry watches; no resting exchange orders or live access."""

import math
from collections import Counter

STEP = 300000


def definitions():
    result = [dict(id="immediate", mode="immediate", label="Vào ngay")]
    result += [
        dict(id=f"delay{m}", mode="delay", minutes=m, label=f"Chờ {m} phút")
        for m in [15, 60, 180]
    ]
    names = {
        "rebound": "Chờ hồi lên",
        "breakdown": "Chờ giảm tiếp",
        "rejection": "Hồi lên rồi giảm lại",
    }
    for mode in names:
        for atr in [0.25, 0.5, 1]:
            result.append(
                dict(
                    id=f"{mode}{atr:g}",
                    mode=mode,
                    atr=atr,
                    ttl_hours=6,
                    retrace_atr=0.25,
                    label=f"{names[mode]} {atr:g} ATR",
                )
            )
    return result


def transform(signals, prices, start, end, spec):
    """One trigger attempt per source event. Price decisions see completed closes.

    Watches consume no funds/slots: they are local predicates, not limit orders.
    Capacity and minimum size are checked by the replay only at trigger time.
    ATR and score stay frozen at original signal; next-bar open never filters it.
    """
    output, audit = [], []
    for signal in signals:
        origin = signal["at"]
        if not start <= origin < end:
            continue
        record = dict(
            event_id=signal["event_id"], symbol=signal["symbol"], original_at=origin
        )
        mode = spec["mode"]
        if mode == "immediate":
            output.append(dict(signal))
            audit.append(
                dict(
                    record,
                    status="triggered",
                    trigger_at=origin,
                    wait_minutes=0,
                    improvement_atr=0,
                )
            )
            continue
        quotes = prices.get(signal["symbol"], {})
        anchor = quotes.get(origin, {}).get("execution_close", math.nan)
        atr = signal["atr"]
        if (
            not math.isfinite(anchor)
            or anchor <= 0
            or not math.isfinite(atr)
            or atr <= 0
        ):
            audit.append(dict(record, status="missing_data"))
            continue
        expiry = origin + (
            spec["minutes"] * 60000 if mode == "delay" else spec["ttl_hours"] * 3600000
        )
        armed, peak, previous = False, anchor, anchor
        status = "end_pending" if expiry >= end else "expired"
        for at in range(origin + STEP, min(expiry, end - STEP) + 1, STEP):
            close = quotes.get(at, {}).get("execution_close", math.nan)
            if not math.isfinite(close) or close <= 0:
                status = "missing_data"
                break
            if mode == "delay":
                hit = at >= expiry
            elif mode == "rebound":
                hit = close >= anchor + spec["atr"] * atr
            elif mode == "breakdown":
                hit = close <= anchor - spec["atr"] * atr
            elif mode == "rejection":
                # Arm and trigger on different completed bars.
                hit = (
                    armed
                    and close < previous
                    and close <= peak - spec["retrace_atr"] * atr
                )
                if close >= anchor + spec["atr"] * atr:
                    armed = True
                peak = max(peak, close)
            else:
                raise ValueError("unknown_entry_timing")
            previous = close
            if hit:
                output.append(dict(signal, at=at, original_signal_at=origin))
                audit.append(
                    dict(
                        record,
                        status="triggered",
                        trigger_at=at,
                        wait_minutes=(at - origin) / 60000,
                        improvement_atr=(close - anchor) / atr,
                    )
                )
                break
        else:
            audit.append(dict(record, status=status))
            continue
        if status == "missing_data":
            audit.append(dict(record, status=status))
    return output, dict(
        counts=dict(Counter(r["status"] for r in audit)),
        source_events=len(audit),
        events=audit,
    )
