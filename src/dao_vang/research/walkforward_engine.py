"""Walk-Forward Backtesting Engine for Macro Regime + Donchian Breakout + Chandelier Trailing.
Zero-lookahead, causal execution: signals at bar close t, executed at bar open t+1.
Includes 10 bps one-way transaction costs and realistic 8h funding rates.
"""

from __future__ import annotations
import math
from typing import Dict, List, Tuple, Optional
import numpy as np
import pandas as pd
from dao_vang.research.data_loader import AssetMarketData
from dao_vang.research.protocol import TOTAL_ONE_WAY_BPS


def compute_metrics(nav_series: pd.Series) -> Tuple[float, float, float, float]:
    """Calculate Total Return, CAGR, MaxDD, Calmar from equity series."""
    vals = nav_series.to_numpy(dtype=float)
    if len(vals) < 2 or vals[0] <= 0:
        return 0.0, 0.0, 1.0, 0.0
    tot_ret = (vals[-1] / vals[0]) - 1.0
    days = max((nav_series.index[-1] - nav_series.index[0]).total_seconds() / 86400.0, 1.0)
    years = days / 365.25
    cagr = ((1.0 + max(tot_ret, -0.999)) ** (1.0 / max(years, 0.1))) - 1.0
    peaks = np.maximum.accumulate(vals)
    dd = 1.0 - vals / peaks
    maxdd = float(np.max(dd))
    calmar = cagr / maxdd if maxdd > 1e-6 else 0.0
    return tot_ret, cagr, maxdd, calmar


def prepare_multiasset_features(
    universe_data: Dict[str, AssetMarketData],
    resample_freq: str = "4h",
) -> Tuple[pd.DatetimeIndex, Dict[str, dict]]:
    """Resample and precompute causal indicators for all assets."""
    symbols = list(universe_data.keys())
    resampled = {}
    funding_resampled = {}

    for s in symbols:
        df = universe_data[s].klines.resample(resample_freq).agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
        }).dropna()
        resampled[s] = df

        # Sum funding rate over the 4h bar
        f_series = universe_data[s].funding_series.resample(resample_freq).sum().reindex(df.index).fillna(0.0)
        funding_resampled[s] = f_series

    timeline = resampled["BTCUSDT"].index
    n = len(timeline)

    features = {}
    for s in symbols:
        df = resampled[s].reindex(timeline).ffill()
        c = df["close"].to_numpy(dtype=float)
        h = df["high"].to_numpy(dtype=float)
        l = df["low"].to_numpy(dtype=float)
        o = df["open"].to_numpy(dtype=float)
        f_rates = funding_resampled[s].reindex(timeline).fillna(0.0).to_numpy(dtype=float)

        # True Range and ATR14
        tr = np.zeros(n, dtype=float)
        tr[0] = h[0] - l[0]
        for i in range(1, n):
            tr[i] = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
        atr14 = pd.Series(tr).shift(1).rolling(14, min_periods=14).mean().to_numpy()

        # Realized Annualized Volatility
        log_ret = np.zeros(n, dtype=float)
        log_ret[1:] = np.log(np.maximum(c[1:] / np.maximum(c[:-1], 1e-8), 1e-8))
        ann_vol = pd.Series(log_ret).shift(1).rolling(60, min_periods=30).std(ddof=1).to_numpy() * np.sqrt(365.25 * 6)
        ann_vol = np.clip(ann_vol, 0.15, 2.50)

        # EMAs
        ema40 = pd.Series(c).shift(1).ewm(span=40).mean().to_numpy()
        ema200 = pd.Series(c).shift(1).ewm(span=200).mean().to_numpy()
        ema300 = pd.Series(c).shift(1).ewm(span=300).mean().to_numpy()
        ema600 = pd.Series(c).shift(1).ewm(span=600).mean().to_numpy()

        # Donchian Breakout Highs
        donch20 = pd.Series(h).shift(1).rolling(20, min_periods=20).max().to_numpy()
        donch30 = pd.Series(h).shift(1).rolling(30, min_periods=30).max().to_numpy()

        # Momentum (14 bars lookback)
        mom14 = (pd.Series(c).shift(1) / pd.Series(c).shift(15) - 1.0).to_numpy()

        v = df["volume"].to_numpy(dtype=float)

        features[s] = {
            "open": o, "high": h, "low": l, "close": c, "volume": v,
            "funding_rate": f_rates,
            "atr14": atr14, "ann_vol": ann_vol,
            "ema40": ema40, "ema200": ema200, "ema300": ema300, "ema600": ema600,
            "donchian_20": donch20, "donchian_30": donch30,
            "mom14": mom14,
        }

    return timeline, features


def simulate_candidate(
    timeline: pd.DatetimeIndex,
    features: Dict[str, dict],
    candidate_spec: dict,
    initial_capital: float = 100_000.0,
    cost_rate_bps: float = TOTAL_ONE_WAY_BPS,
) -> Tuple[pd.Series, dict]:
    """Execute strategy simulation with exact cost and funding accounting."""
    cost_rate = cost_rate_bps / 10_000.0
    symbols = candidate_spec["universe"]
    macro_filter = candidate_spec["macro_btc_filter"]
    entry_signal = candidate_spec["entry_signal"]
    trail_atr_mult = candidate_spec["trail_atr_mult"]
    be_atr_mult = candidate_spec["break_even_atr_mult"]
    tighten_atr_mult = candidate_spec.get("tighten_atr_mult", 99.0)
    target_vol = candidate_spec["target_annual_vol"]
    max_slots = candidate_spec["slots"]

    btc_f = features["BTCUSDT"]
    btc_macro = btc_f[macro_filter]
    btc_close = btc_f["close"]

    n = len(timeline)
    cash = initial_capital
    positions = {s: 0.0 for s in symbols}
    entry_p = {s: 0.0 for s in symbols}
    peak_p = {s: 0.0 for s in symbols}
    stop_p = {s: 0.0 for s in symbols}
    in_pos = {s: False for s in symbols}

    navs = np.zeros(n, dtype=float)
    total_fees = 0.0
    total_funding = 0.0
    trade_pnls = []
    trade_count = 0

    warmup = 300

    for t in range(n):
        o_now = {s: features[s]["open"][t] for s in symbols}
        open_val = sum(positions[s] * o_now[s] for s in symbols if in_pos[s] and np.isfinite(o_now[s]))
        current_equity = cash + open_val

        if t >= warmup and current_equity > 0:
            btc_prev_c = btc_close[t - 1]
            btc_prev_m = btc_macro[t - 1]
            macro_ok = btc_prev_c > btc_prev_m

            # 1. Exit Evaluation
            for s in symbols:
                if in_pos[s]:
                    c_prev = features[s]["close"][t - 1]
                    atr_prev = features[s]["atr14"][t - 1]
                    o_exec = o_now[s]

                    if c_prev > peak_p[s]:
                        peak_p[s] = c_prev

                    gain_atr = (peak_p[s] - entry_p[s]) / max(atr_prev, 1e-6)

                    # Staged trailing stop
                    if gain_atr >= tighten_atr_mult:
                        curr_trail = min(trail_atr_mult, 1.5)
                        stop_p[s] = max(entry_p[s] + 1.0 * atr_prev, peak_p[s] - curr_trail * atr_prev)
                    elif gain_atr >= be_atr_mult:
                        stop_p[s] = max(entry_p[s], peak_p[s] - trail_atr_mult * atr_prev)
                    else:
                        stop_p[s] = max(stop_p[s], peak_p[s] - 2.5 * atr_prev)

                    exit_sig = (c_prev < stop_p[s]) or (c_prev < features[s]["ema40"][t - 1]) or (not macro_ok)

                    if exit_sig and np.isfinite(o_exec):
                        fee = abs(positions[s] * o_exec) * cost_rate
                        pnl = (positions[s] * o_exec - fee) - (positions[s] * entry_p[s])
                        trade_pnls.append(pnl)
                        trade_count += 1
                        total_fees += fee
                        cash += (positions[s] * o_exec - fee)
                        positions[s] = 0.0
                        in_pos[s] = False

            # 2. Entry Evaluation
            if macro_ok:
                open_count = sum(1 for s in symbols if in_pos[s])
                avail = max_slots - open_count
                if avail > 0:
                    cand = []
                    for s in symbols:
                        if not in_pos[s]:
                            c_prev = features[s]["close"][t - 1]
                            ema40_prev = features[s]["ema40"][t - 1]
                            sig_thresh = features[s][entry_signal][t - 1]

                            if c_prev >= sig_thresh and c_prev > ema40_prev:
                                mom = features[s]["mom14"][t - 1]
                                if mom > 0:
                                    cand.append((s, mom))

                    cand.sort(key=lambda x: x[1], reverse=True)
                    for s, score in cand[:avail]:
                        o_exec = o_now[s]
                        vol_prev = features[s]["ann_vol"][t - 1]
                        atr_prev = features[s]["atr14"][t - 1]
                        if np.isfinite(o_exec) and o_exec > 0 and np.isfinite(vol_prev) and vol_prev > 0:
                            v_scale = np.clip(target_vol / vol_prev, 0.20, 1.10)
                            alloc = (current_equity / max_slots) * v_scale
                            fee = alloc * cost_rate
                            if cash >= (alloc + fee):
                                cash -= (alloc + fee)
                                total_fees += fee
                                positions[s] = alloc / o_exec
                                in_pos[s] = True
                                entry_p[s] = o_exec
                                peak_p[s] = o_exec
                                stop_p[s] = o_exec - 2.0 * atr_prev

        # 3. Apply funding rate fees
        for s in symbols:
            if in_pos[s]:
                f_rate = features[s]["funding_rate"][t]
                if f_rate != 0.0:
                    c_bar = features[s]["close"][t]
                    f_cost = positions[s] * c_bar * f_rate
                    cash -= f_cost
                    total_funding += f_cost

        # Mark NAV at bar close
        c_now = {s: features[s]["close"][t] for s in symbols}
        close_val = sum(positions[s] * c_now[s] for s in symbols if in_pos[s] and np.isfinite(c_now[s]))
        navs[t] = cash + close_val

    nav_series = pd.Series(navs, index=timeline, name="nav")
    tot_ret, cagr, maxdd, calmar = compute_metrics(nav_series)

    # Trade stats
    wins = [p for p in trade_pnls if p > 0]
    losses = [abs(p) for p in trade_pnls if p < 0]
    win_rate = (len(wins) / len(trade_pnls)) if trade_pnls else 0.0
    profit_factor = (sum(wins) / sum(losses)) if losses and sum(losses) > 1e-6 else (99.0 if wins else 0.0)

    stats = {
        "total_return_pct": round(tot_ret * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "maxdd_pct": round(maxdd * 100, 2),
        "calmar": round(calmar, 4),
        "win_rate_pct": round(win_rate * 100, 2),
        "profit_factor": round(profit_factor, 3),
        "total_trades": trade_count,
        "total_fees_usdt": round(total_fees, 2),
        "total_funding_usdt": round(total_funding, 2),
        "final_equity_usdt": round(float(navs[-1]), 2),
    }

    return nav_series, stats
