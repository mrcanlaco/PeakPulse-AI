"""Deterministic replay of one shadow from its start bar over the shared panel.

The shadow is not an incremental account: its whole state (equity curve, positions,
trades) is recomputed from (spec, start bar, shared panel) with the SAME engine and cost
model as the research backtest.  Restart-safe, no per-shadow database, no drift.
"""

from __future__ import annotations

import numpy as np

from ..data import Panel
from ..engine import cost_matrix, simulate
from ..signals import Ctx, build

MAX_TRADES = 60
MAX_POINTS = 700


def shared_context(panel: Panel):
    """Computed once per bar and reused by every shadow (features cache + cost model)."""
    return Ctx(panel), cost_matrix(panel)


def shadow_state(panel: Panel, ctx: Ctx, cost: np.ndarray, spec: dict, start_idx: int,
                 capital: float, init_target: bool = True) -> dict:
    """``init_target``: a bot that had been running would already hold the target of its last
    decision, so the shadow opens that portfolio at the start bar (daily/weekly strategies would
    otherwise sit in cash for days).  Only decisions made strictly before the start are used."""
    W, reb = build(ctx, spec)
    reb_all = reb
    reb = reb.copy()
    reb[:start_idx] = False  # decisions strictly before the shadow existed are void
    if init_target and start_idx >= 1:
        prev = np.flatnonzero(reb_all[:start_idx] & (np.abs(np.nan_to_num(W[:start_idx])).sum(axis=1) > 0))
        if len(prev) and not np.isnan(W[prev[-1]]).any():
            W = W.copy()
            W[start_idx - 1] = W[prev[-1]]
            reb[start_idx - 1] = True
    k1 = panel.shape[0] - 1
    res = simulate(panel, W, reb, start_idx, k1, cost, keep_pos=True)
    eq = res.equity * capital
    n_bars = len(res.index)
    times = res.index.as_unit("ms").asi8.astype(np.int64)  # ms
    step = max(1, n_bars // MAX_POINTS)
    pick = list(range(0, n_bars, step))
    if pick[-1] != n_bars - 1:
        pick.append(n_bars - 1)
    curve = [[int(times[i]), round(float(eq[i]), 2)] for i in pick]

    peak = np.maximum.accumulate(eq)
    dd = 1.0 - eq / np.where(peak > 0, peak, 1.0)

    # average-cost positions + realised PnL from the recorded trades
    qty = np.zeros(panel.shape[1])
    avg = np.zeros(panel.shape[1])
    realized = 0.0
    trade_log = []
    for (k, j, dn, c) in res.trades or []:
        price = float(panel.open[k, j])
        if not np.isfinite(price) or price <= 0:
            continue
        dq = dn / price
        q = qty[j]
        if q == 0 or np.sign(q) == np.sign(dq):
            tot = abs(q) + abs(dq)
            avg[j] = (avg[j] * abs(q) + price * abs(dq)) / tot if tot > 0 else price
            qty[j] = q + dq
        else:
            closed = min(abs(dq), abs(q))
            realized += closed * (price - avg[j]) * np.sign(q)
            newq = q + dq
            if np.sign(newq) != np.sign(q) and newq != 0:
                avg[j] = price
            qty[j] = newq
            if abs(newq) < 1e-15:
                qty[j] = 0.0
        trade_log.append(
            {
                "t": int(times[k - start_idx]) if 0 <= k - start_idx < n_bars else int(times[-1]),
                "symbol": panel.symbols[j],
                "side": "BUY" if dn > 0 else "SELL",
                "notional": round(abs(dn) * capital, 2),
                "price": price,
                "fee": round(abs(dn) * c * capital, 4),
            }
        )

    last_pos = res.pos[-1] if res.pos is not None and len(res.pos) else np.zeros(panel.shape[1])
    open_px = panel.open[k1]
    positions = []
    for j in np.flatnonzero(np.abs(last_pos) > 1e-12):
        positions.append(
            {
                "symbol": panel.symbols[j],
                "side": "LONG" if last_pos[j] > 0 else "SHORT",
                "notional": round(float(last_pos[j]) * capital, 2),
                "open_price": float(open_px[j]),
                "avg_entry": float(avg[j]),
                "qty": float(qty[j]) * capital,
            }
        )
    positions.sort(key=lambda p: -abs(p["notional"]))
    gross = float(np.abs(last_pos).sum())
    net = float(last_pos.sum())

    day_ms = 86_400_000
    t_now = int(times[-1])
    day_start = t_now // day_ms * day_ms
    j0 = int(np.searchsorted(times, day_start, side="left"))
    eq_day0 = float(eq[min(j0, n_bars - 1)]) if j0 > 0 else float(eq[0])
    days = max((times[-1] - times[0]) / day_ms, 1e-9)
    return {
        "start_ts": int(times[0]),
        "asof_ts": t_now,
        "capital": capital,
        "equity": round(float(eq[-1]), 2),
        "pnl": round(float(eq[-1] - capital), 2),
        "return": float(eq[-1] / capital - 1.0),
        "pnl_today": round(float(eq[-1] - eq_day0), 2),
        "max_dd": float(dd.max()),
        "dd_now": float(dd[-1]),
        "days": float(days),
        "gross": gross,
        "net": net,
        "n_positions": len(positions),
        "fees": round(float(res.fees) * capital, 2),
        "funding": round(float(res.funding) * capital, 2),
        "realized": round(float(realized) * capital, 2),
        "turnover": float(res.turnover),
        "ruined": bool(res.ruined),
        "positions": positions,
        "trades": trade_log[-MAX_TRADES:][::-1],
        "curve": curve,
    }
