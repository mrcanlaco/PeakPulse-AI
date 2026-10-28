"""Causal portfolio simulator for no-stop-loss target-weight strategies.

Timing contract (no lookahead)
    * A decision made at the CLOSE of bar ``t`` uses only data with index <= t.
    * It is executed at the OPEN of bar ``t+1`` (cost = fee + liquidity-tiered slippage).
    * Positions earn open[k] -> open[k+1] (last bar of the panel marks to close).
    * Funding settled at the start of bar k (00/08/16 UTC) is charged to the
      positions held through the settlement, before any rebalance at that open.

No-stop-loss contract
    * The engine NEVER closes or reduces a position because of its own PnL, entry
      price, drawdown, or margin level.  The only forced event is liquidation:
      cross margin, maintenance 2% of gross notional, tested against the bar's
      adverse extreme (low for longs, high for shorts, all assets simultaneously =
      conservative).  Liquidation zeroes the account and ends the run (ruin).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data import BARS_PER_DAY, Panel

MAINT_MARGIN = 0.02
MAX_GROSS = 3.0
FEE_BPS = 5.0

SPLITS = {
    "train": ("2020-01-01 00:00", "2023-12-31 20:00"),
    "val": ("2024-01-01 00:00", "2025-12-31 20:00"),
    "test": ("2026-01-01 00:00", "2026-08-31 20:00"),
}


def split_range(panel: Panel, name: str) -> tuple[int, int]:
    a, b = SPLITS[name]
    ia = int(panel.index.searchsorted(pd.Timestamp(a, tz="UTC"), side="left"))
    ib = int(panel.index.searchsorted(pd.Timestamp(b, tz="UTC"), side="right")) - 1
    return ia, ib


def cost_matrix(panel: Panel, stress: float = 1.0) -> np.ndarray:
    """One-way cost (fraction) per bar/symbol: fee + slippage by liquidity rank."""
    qv = pd.DataFrame(panel.qvol).rolling(
        30 * BARS_PER_DAY, min_periods=BARS_PER_DAY
    ).mean()
    rank = qv.rank(axis=1, ascending=False).to_numpy()
    slip = np.full(rank.shape, 15.0)
    slip[rank <= 30] = 8.0
    slip[rank <= 10] = 3.0
    slip[np.isnan(rank)] = 15.0
    return (FEE_BPS + slip) * 1e-4 * stress


@dataclass
class RunResult:
    equity: np.ndarray  # equity at each bar start (len = bars + 1), starts at 1.0
    worst: np.ndarray  # intrabar worst equity per bar (conservative)
    gross: np.ndarray  # gross exposure per bar (fraction of equity)
    index: pd.DatetimeIndex  # timestamps of bar starts (+ final mark)
    fees: float
    funding: float
    turnover: float
    ruined: bool
    pos: np.ndarray | None = None  # (bars, N) notional positions after the bar-open rebalance
    trades: list | None = None  # (bar_index, symbol_index, notional_delta, one_way_cost)


def simulate(
    panel: Panel,
    W: np.ndarray,
    reb: np.ndarray,
    k0: int,
    k1: int,
    cost: np.ndarray,
    keep_pos: bool = False,
) -> RunResult:
    """Run bars k0..k1 inclusive. ``W[t]`` is the target (fraction of equity per
    symbol) decided at close of bar t and applied at the open of t+1 when
    ``reb[t]``.  Between rebalances positions simply drift (no stops, no trims).
    """
    n = panel.shape[1]
    op, hi, lo, cl = panel.open, panel.high, panel.low, panel.close
    nxt_open = np.empty_like(op)
    nxt_open[:-1] = op[1:]
    nxt_open[-1] = cl[-1]
    fund = panel.funding

    nb = k1 - k0 + 1
    equity = np.empty(nb + 1)
    worst = np.empty(nb)
    gross_hist = np.zeros(nb)
    equity[0] = 1.0
    e = 1.0
    pos = np.zeros(n)
    fees = 0.0
    fund_pnl = 0.0
    turn = 0.0
    pos_hist = np.zeros((nb, n)) if keep_pos else None
    trades: list | None = [] if keep_pos else None
    ruined = False

    for i in range(nb):
        k = k0 + i
        o = op[k]
        ok = np.isfinite(o) & np.isfinite(nxt_open[k])
        # funding settled at this open on positions held through it
        fk = fund[k]
        if fk.any():
            fp = -float(np.dot(pos, fk))
            e += fp
            fund_pnl += fp
            if e <= 0:
                ruined = True
        # rebalance decided at close of bar k-1
        if not ruined and k >= 1 and reb[k - 1]:
            wrow = W[k - 1]
            hold = np.isnan(wrow)  # NaN = leave that position untouched
            tw = np.where(ok & ~hold, np.nan_to_num(wrow), 0.0)
            target = np.where(hold, pos, tw * e)
            g = np.abs(target).sum() / max(e, 1e-12)
            if g > MAX_GROSS:
                target = target * (MAX_GROSS / g)
            trade = target - pos
            # cannot trade unavailable symbols
            trade = np.where(ok, trade, 0.0)
            c = float(np.dot(np.abs(trade), np.nan_to_num(cost[k - 1], nan=0.0015)))
            fees += c
            turn += float(np.abs(trade).sum()) / max(e, 1e-12)
            e -= c
            pos = pos + trade
            if trades is not None:
                for j in np.flatnonzero(np.abs(trade) > 1e-12):
                    trades.append((k, int(j), float(trade[j]), float(cost[k - 1][j])))
        if ruined:
            equity[i + 1 :] = 0.0
            worst[i:] = 0.0
            gross_hist[i:] = 0.0
            break
        gross_hist[i] = np.abs(pos).sum() / max(e, 1e-12)
        if pos_hist is not None:
            pos_hist[i] = pos
        r = np.where(ok, nxt_open[k] / np.where(ok, o, 1.0) - 1.0, 0.0)
        # adverse intrabar extreme for each held position
        adv_l = np.where(ok & (pos > 0), lo[k] / np.where(ok, o, 1.0) - 1.0, 0.0)
        adv_s = np.where(ok & (pos < 0), hi[k] / np.where(ok, o, 1.0) - 1.0, 0.0)
        adv_l = np.nan_to_num(adv_l)
        adv_s = np.nan_to_num(adv_s)
        e_worst = e + float(np.dot(pos, adv_l + adv_s))
        gross_now = float(np.abs(pos).sum())
        if gross_now > 0 and e_worst <= MAINT_MARGIN * gross_now:
            ruined = True
            e = 0.0
            equity[i + 1 :] = 0.0
            worst[i:] = 0.0
            break
        worst[i] = e_worst
        pnl = pos * r
        e += float(pnl.sum())
        pos = pos * (1.0 + r)
        equity[i + 1] = e
        if e <= 0:
            ruined = True
            equity[i + 1 :] = 0.0
            break

    idx = panel.index[k0 : k1 + 1]
    idx = idx.append(idx[-1:] + pd.Timedelta("4h"))
    return RunResult(
        equity=equity,
        worst=worst,
        gross=gross_hist,
        index=idx,
        fees=fees,
        funding=fund_pnl,
        turnover=turn,
        ruined=ruined,
        pos=pos_hist,
        trades=trades,
    )


def metrics(res: RunResult) -> dict:
    eq = res.equity
    years = (len(eq) - 1) / (BARS_PER_DAY * 365.25)
    total = float(eq[-1] - 1.0)
    if eq[-1] <= 0:
        cagr = -1.0
    else:
        cagr = float(eq[-1] ** (1.0 / years) - 1.0)
    peak = np.maximum.accumulate(eq)
    dd = 1.0 - eq / np.where(peak > 0, peak, 1.0)
    maxdd = float(dd.max())
    # intrabar-conservative drawdown
    pk = peak[:-1]
    ddw = 1.0 - np.minimum(res.worst, eq[:-1]) / np.where(pk > 0, pk, 1.0)
    maxdd_intra = float(max(ddw.max() if len(ddw) else 0.0, maxdd))
    calmar = cagr / maxdd if maxdd > 1e-9 else 0.0
    calmar_intra = cagr / maxdd_intra if maxdd_intra > 1e-9 else 0.0
    rets = np.diff(eq) / np.where(eq[:-1] > 0, eq[:-1], 1.0)
    sd = rets.std()
    sharpe = float(rets.mean() / sd * np.sqrt(BARS_PER_DAY * 365.25)) if sd > 0 else 0.0
    # yearly / monthly returns on calendar basis
    stamp = res.index.delete(-1).append(res.index[-1:] - pd.Timedelta("1s"))
    s = pd.Series(eq, index=stamp)
    first_year_start = s.iloc[0]
    yr_last = s.resample("YS").last()
    yr = {}
    prev = first_year_start
    for ts, v in yr_last.items():
        yr[int(ts.year)] = float(v / prev - 1.0) if prev > 0 else -1.0
        prev = v
    mo_last = s.resample("MS").last()
    prevm = first_year_start
    mo = []
    for v in mo_last.values:
        mo.append(float(v / prevm - 1.0) if prevm > 0 else -1.0)
        prevm = v
    mo = np.array(mo)
    return {
        "cagr": cagr,
        "maxdd": maxdd,
        "calmar": float(calmar),
        "maxdd_intra": maxdd_intra,
        "calmar_intra": float(calmar_intra),
        "total_return": total,
        "sharpe": sharpe,
        "gross_avg": float(res.gross.mean()) if len(res.gross) else 0.0,
        "turnover_per_year": float(res.turnover / years) if years > 0 else 0.0,
        "fees": float(res.fees),
        "funding": float(res.funding),
        "ruined": bool(res.ruined),
        "years": float(years),
        "yearly": yr,
        "month_win": float((mo > 0).mean()) if len(mo) else 0.0,
        "pos_years": int(sum(v > 0 for v in yr.values())),
        "n_years": len(yr),
    }


def daily_returns(res: RunResult) -> pd.Series:
    s = pd.Series(res.equity, index=res.index).resample("1D").last().dropna()
    return s.pct_change().dropna()
