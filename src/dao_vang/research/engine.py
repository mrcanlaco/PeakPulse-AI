"""High-performance causal portfolio backtesting engine with realistic costs and funding."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
import math
import numpy as np
import pandas as pd
from dao_vang.research.data_loader import AssetMarketData
from dao_vang.research.protocol import INITIAL_CAPITAL, TOTAL_ONE_WAY_BPS


@dataclass
class BacktestMetrics:
    total_return: float
    cagr: float
    maxdd: float
    calmar: float
    sharpe: float
    sortino: float
    win_rate: float
    profit_factor: float
    total_trades: int
    total_fees: float
    net_funding: float
    exposure_avg: float
    days: float
    final_equity: float

    def to_dict(self) -> dict:
        return {
            "total_return_pct": round(self.total_return * 100, 2),
            "cagr_pct": round(self.cagr * 100, 2),
            "maxdd_pct": round(self.maxdd * 100, 2),
            "calmar": round(self.calmar, 4) if self.calmar is not None else None,
            "sharpe": round(self.sharpe, 4) if self.sharpe is not None else None,
            "sortino": round(self.sortino, 4) if self.sortino is not None else None,
            "win_rate_pct": round(self.win_rate * 100, 2),
            "profit_factor": round(self.profit_factor, 4) if self.profit_factor is not None else None,
            "total_trades": self.total_trades,
            "total_fees_usdt": round(self.total_fees, 2),
            "net_funding_usdt": round(self.net_funding, 2),
            "exposure_avg": round(self.exposure_avg, 4),
            "days": round(self.days, 1),
            "final_equity_usdt": round(self.final_equity, 2),
        }


def compute_metrics(
    equity_series: pd.Series,
    trade_pnls: list[float],
    total_fees: float,
    net_funding: float,
    exposure_series: pd.Series,
) -> BacktestMetrics:
    vals = equity_series.to_numpy(dtype=float)
    if len(vals) < 2:
        raise ValueError("equity_series too short")

    initial = vals[0]
    final = vals[-1]
    total_return = final / initial - 1.0

    start_t = equity_series.index[0]
    end_t = equity_series.index[-1]
    days = max((end_t - start_t).total_seconds() / 86400.0, 1.0)
    years = days / 365.25

    if total_return > -1.0:
        cagr = (1.0 + total_return) ** (1.0 / years) - 1.0
    else:
        cagr = -1.0

    peaks = np.maximum.accumulate(vals)
    dds = 1.0 - vals / peaks
    maxdd = float(np.max(dds))

    calmar = float(cagr / maxdd) if maxdd > 1e-6 else 0.0

    # Daily resampled Sharpe & Sortino
    daily_equity = equity_series.resample("1D").last().dropna()
    daily_returns = daily_equity.pct_change().dropna().to_numpy()

    if len(daily_returns) > 5 and np.std(daily_returns) > 1e-8:
        mean_ret = np.mean(daily_returns)
        std_ret = np.std(daily_returns, ddof=1)
        sharpe = float(mean_ret / std_ret * math.sqrt(365.25))

        downside = daily_returns[daily_returns < 0]
        if len(downside) > 0 and np.std(downside) > 1e-8:
            sortino = float(mean_ret / np.std(downside, ddof=1) * math.sqrt(365.25))
        else:
            sortino = sharpe
    else:
        sharpe = 0.0
        sortino = 0.0

    # Trade metrics
    pnls = np.array(trade_pnls) if trade_pnls else np.array([])
    total_trades = len(pnls)
    if total_trades > 0:
        win_rate = float(np.mean(pnls > 0))
        wins = float(np.sum(pnls[pnls > 0]))
        losses = float(-np.sum(pnls[pnls < 0]))
        profit_factor = (wins / losses) if losses > 1e-6 else (999.0 if wins > 0 else 0.0)
    else:
        win_rate = 0.0
        profit_factor = 0.0

    exposure_avg = float(exposure_series.mean()) if len(exposure_series) > 0 else 0.0

    return BacktestMetrics(
        total_return=total_return,
        cagr=cagr,
        maxdd=maxdd,
        calmar=calmar,
        sharpe=sharpe,
        sortino=sortino,
        win_rate=win_rate,
        profit_factor=profit_factor,
        total_trades=total_trades,
        total_fees=total_fees,
        net_funding=net_funding,
        exposure_avg=exposure_avg,
        days=days,
        final_equity=final,
    )


class PortfolioSimulator:
    """Multi-asset portfolio simulator with exact causal execution and cost accounting."""

    def __init__(
        self,
        universe_data: Dict[str, AssetMarketData],
        initial_capital: float = INITIAL_CAPITAL,
        one_way_cost_bps: float = TOTAL_ONE_WAY_BPS,
        max_gross_exposure: float = 1.0,
    ):
        self.universe_data = universe_data
        self.initial_capital = initial_capital
        self.cost_rate = one_way_cost_bps / 10_000.0
        self.max_gross = max_gross_exposure

        # Establish common union timeline
        all_indices = [adata.klines.index for adata in universe_data.values()]
        common_timeline = all_indices[0]
        for idx in all_indices[1:]:
            common_timeline = common_timeline.union(idx)
        self.timeline = common_timeline.sort_values()

    def run(
        self,
        target_weights_df: pd.DataFrame,  # columns = symbols, index = timeline. Value at t is signal from close(t)
    ) -> tuple[pd.Series, pd.DataFrame, BacktestMetrics, list[dict]]:
        """Simulate execution. Target weight at t determines order executed at open(t+1)."""
        timeline = self.timeline
        symbols = list(self.universe_data.keys())

        # Pre-extract numpy matrices for speed
        n_steps = len(timeline)
        cash = self.initial_capital
        positions_qty = {s: 0.0 for s in symbols}
        positions_entry_price = {s: 0.0 for s in symbols}
        trade_pnls: list[float] = []
        trade_records: list[dict] = []

        total_fees = 0.0
        net_funding = 0.0

        equity_records = np.zeros(n_steps, dtype=float)
        exposure_records = np.zeros(n_steps, dtype=float)

        # Pre-align open, high, low, close and funding for each symbol
        opens = {}
        highs = {}
        lows = {}
        closes = {}
        fundings = {}

        for s in symbols:
            df = self.universe_data[s].klines.reindex(timeline)
            opens[s] = df["open"].to_numpy(dtype=float)
            highs[s] = df["high"].to_numpy(dtype=float)
            lows[s] = df["low"].to_numpy(dtype=float)
            closes[s] = df["close"].to_numpy(dtype=float)
            fundings[s] = self.universe_data[s].funding_series.reindex(timeline, fill_value=0.0).to_numpy(dtype=float)

        # Reindex weights
        aligned_weights = target_weights_df.reindex(timeline).fillna(0.0)
        # Cap gross exposure strictly
        weights_arr = aligned_weights.to_numpy(dtype=float)
        gross_weights = np.sum(np.abs(weights_arr), axis=1)
        scale = np.ones(n_steps, dtype=float)
        mask = gross_weights > self.max_gross
        scale[mask] = self.max_gross / gross_weights[mask]
        weights_arr = weights_arr * scale[:, None]

        # Simulation loop
        for t in range(n_steps):
            # 1. Update equity at start of bar t using open prices
            current_equity = cash
            for i, s in enumerate(symbols):
                q = positions_qty[s]
                o = opens[s][t]
                if q != 0.0 and np.isfinite(o):
                    current_equity += q * o

            # 2. Check and process orders from previous bar signal (t-1)
            if t > 0 and current_equity > 0:
                desired_weights = weights_arr[t - 1]  # Signal was from close of t-1
                for i, s in enumerate(symbols):
                    desired_w = desired_weights[i]
                    o = opens[s][t]
                    if not np.isfinite(o) or o <= 0:
                        continue

                    desired_notional = desired_w * current_equity
                    current_q = positions_qty[s]
                    current_notional = current_q * o
                    delta_notional = desired_notional - current_notional

                    # Minimum trade filter to avoid tiny dust rebalancing
                    if abs(delta_notional) > 10.0:  # min 10 USDT
                        desired_q = desired_notional / o
                        trade_q = desired_q - current_q

                        fee = abs(trade_q * o) * self.cost_rate
                        cash -= fee
                        total_fees += fee

                        # If closing or reducing position, record realized PnL
                        if current_q != 0.0:
                            if (current_q > 0 and trade_q < 0) or (current_q < 0 and trade_q > 0):
                                closed_qty = min(abs(current_q), abs(trade_q))
                                pnl = closed_qty * (o - positions_entry_price[s]) * (1.0 if current_q > 0 else -1.0) - fee
                                trade_pnls.append(pnl)
                                trade_records.append({
                                    "time": str(timeline[t]),
                                    "symbol": s,
                                    "exit_price": o,
                                    "closed_qty": closed_qty,
                                    "pnl": pnl,
                                })

                        if abs(desired_q) > 1e-8:
                            # Update entry price for new/expanded position
                            if current_q == 0.0 or (np.sign(desired_q) != np.sign(current_q)):
                                positions_entry_price[s] = o
                            else:
                                # Weighted average entry price
                                positions_entry_price[s] = (positions_entry_price[s] * abs(current_q) + o * abs(trade_q)) / abs(desired_q)
                        else:
                            positions_entry_price[s] = 0.0

                        positions_qty[s] = desired_q
                        cash -= trade_q * o

            # 3. Apply funding fees if settlement occurs at bar t
            for i, s in enumerate(symbols):
                q = positions_qty[s]
                f_rate = fundings[s][t]
                c = closes[s][t]
                if q != 0.0 and f_rate != 0.0 and np.isfinite(c):
                    # Long pays positive funding, receives negative funding
                    # Short receives positive funding, pays negative funding
                    # funding_cost = q * c * f_rate
                    funding_cost = q * c * f_rate
                    cash -= funding_cost
                    net_funding += funding_cost

            # 4. Mark equity at end of bar t using close prices
            end_equity = cash
            total_active_notional = 0.0
            for i, s in enumerate(symbols):
                q = positions_qty[s]
                c = closes[s][t]
                if q != 0.0 and np.isfinite(c):
                    end_equity += q * c
                    total_active_notional += abs(q * c)

            if end_equity <= 0:
                end_equity = 0.0
                cash = 0.0
                positions_qty = {s: 0.0 for s in symbols}

            equity_records[t] = end_equity
            exposure_records[t] = (total_active_notional / end_equity) if end_equity > 0 else 0.0

        equity_series = pd.Series(equity_records, index=timeline, name="equity")
        exposure_series = pd.Series(exposure_records, index=timeline, name="gross_exposure")

        metrics = compute_metrics(
            equity_series,
            trade_pnls,
            total_fees,
            net_funding,
            exposure_series,
        )

        return equity_series, exposure_series, metrics, trade_records
