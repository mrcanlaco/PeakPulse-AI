"""PeakPulse Quantitative Research Workbench - Train Period Exploration (2020-2023).
Strictly adheres to scientific protocol: Only uses data from 2020-01-01 to 2023-12-31.
"""

from __future__ import annotations
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))

from dao_vang.research.protocol import TRAIN_START, TRAIN_END, UNIVERSE
from dao_vang.research.data_loader import load_universe, slice_universe, AssetMarketData


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


def prepare_train_features(
    universe_train: Dict[str, AssetMarketData],
    resample_freq: str = "4h",
) -> Tuple[pd.DatetimeIndex, Dict[str, dict]]:
    """Resample and precompute causal indicators on Train slice."""
    symbols = list(universe_train.keys())
    resampled = {}
    for s in symbols:
        df = universe_train[s].klines.resample(resample_freq).agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
        }).dropna()
        resampled[s] = df

    timeline = resampled["BTCUSDT"].index
    n = len(timeline)

    features = {}
    for s in symbols:
        df = resampled[s].reindex(timeline).ffill()
        c = df["close"].to_numpy(dtype=float)
        h = df["high"].to_numpy(dtype=float)
        l = df["low"].to_numpy(dtype=float)
        o = df["open"].to_numpy(dtype=float)
        v = df["volume"].to_numpy(dtype=float)

        # True Range & ATR 14
        tr = np.zeros(n, dtype=float)
        tr[0] = h[0] - l[0]
        for i in range(1, n):
            tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        atr14 = pd.Series(tr).shift(1).rolling(14, min_periods=14).mean().to_numpy()

        # Realized Volatility (rolling 60 periods of resample_freq)
        log_ret = np.zeros(n, dtype=float)
        log_ret[1:] = np.log(np.maximum(c[1:] / np.maximum(c[:-1], 1e-8), 1e-8))
        ann_factor = np.sqrt(365.25 * (24 if resample_freq == "1h" else 6))
        realized_vol = pd.Series(log_ret).shift(1).rolling(60, min_periods=30).std(ddof=1).to_numpy() * ann_factor
        realized_vol = np.clip(realized_vol, 0.15, 2.50)

        # EMAs
        ema10 = pd.Series(c).shift(1).ewm(span=10).mean().to_numpy()
        ema20 = pd.Series(c).shift(1).ewm(span=20).mean().to_numpy()
        ema40 = pd.Series(c).shift(1).ewm(span=40).mean().to_numpy()
        ema60 = pd.Series(c).shift(1).ewm(span=60).mean().to_numpy()
        ema100 = pd.Series(c).shift(1).ewm(span=100).mean().to_numpy()
        ema200 = pd.Series(c).shift(1).ewm(span=200).mean().to_numpy()

        # Donchian High / Low
        donchian_high_20 = pd.Series(h).shift(1).rolling(20, min_periods=20).max().to_numpy()
        donchian_low_10 = pd.Series(l).shift(1).rolling(10, min_periods=10).min().to_numpy()
        donchian_high_40 = pd.Series(h).shift(1).rolling(40, min_periods=40).max().to_numpy()
        donchian_low_20 = pd.Series(l).shift(1).rolling(20, min_periods=20).min().to_numpy()

        # Momentum (return over last 14 and 30 bars)
        mom14 = (pd.Series(c).shift(1) / pd.Series(c).shift(15) - 1.0).to_numpy()
        mom30 = (pd.Series(c).shift(1) / pd.Series(c).shift(31) - 1.0).to_numpy()

        features[s] = {
            "open": o, "high": h, "low": l, "close": c, "volume": v,
            "atr14": atr14, "realized_vol": realized_vol,
            "ema10": ema10, "ema20": ema20, "ema40": ema40, "ema60": ema60,
            "ema100": ema100, "ema200": ema200,
            "donchian_high_20": donchian_high_20, "donchian_low_10": donchian_low_10,
            "donchian_high_40": donchian_high_40, "donchian_low_20": donchian_low_20,
            "mom14": mom14, "mom30": mom30,
        }

    return timeline, features


def simulate_train_strategy(
    timeline: pd.DatetimeIndex,
    features: Dict[str, dict],
    universe_symbols: List[str],
    macro_filter_ema: str,  # 'ema100' or 'ema200' on BTC
    entry_signal_type: str, # 'ema_cross' (10>40) or 'donchian_20' or 'donchian_40'
    trail_atr_mult: float,  # 1.5, 2.0, 2.5, 3.0
    be_atr_mult: float,     # 1.0, 1.5, 2.0 (move stop to entry when gain >= be * atr)
    target_annual_vol: float,# 0.25, 0.30, 0.35, 0.40
    max_portfolio_slots: int,# 2, 3, 4
    require_relative_strength: bool = False, # True: only enter if mom14 > BTC mom14
    cost_rate: float = 0.0010, # 10 bps one way
) -> pd.Series:
    """Fast causal simulation on train."""
    n = len(timeline)
    btc_f = features["BTCUSDT"]
    btc_macro_ema = btc_f[macro_filter_ema]
    btc_close = btc_f["close"]

    cash = 100_000.0
    positions = {s: 0.0 for s in universe_symbols}  # qty
    entry_prices = {s: 0.0 for s in universe_symbols}
    peak_prices = {s: 0.0 for s in universe_symbols}
    stop_prices = {s: 0.0 for s in universe_symbols}
    in_position = {s: False for s in universe_symbols}

    navs = np.zeros(n, dtype=float)
    warmup = 200

    for t in range(n):
        o_now = {s: features[s]["open"][t] for s in universe_symbols}
        
        # Portfolio value at start of bar
        open_val = sum(positions[s] * o_now[s] for s in universe_symbols if in_position[s] and np.isfinite(o_now[s]))
        current_equity = cash + open_val

        if t >= warmup and current_equity > 0:
            # Check BTC macro filter from completed bar t-1
            btc_prev_close = btc_close[t - 1]
            btc_prev_ema = btc_macro_ema[t - 1]
            macro_ok = btc_prev_close > btc_prev_ema

            # 1. Exit Evaluation
            for s in universe_symbols:
                if in_position[s]:
                    c_prev = features[s]["close"][t - 1]
                    atr_prev = features[s]["atr14"][t - 1]
                    o_exec = o_now[s]

                    if c_prev > peak_prices[s]:
                        peak_prices[s] = c_prev

                    # Check break-even progression
                    gain_atr = (peak_prices[s] - entry_prices[s]) / max(atr_prev, 1e-6)
                    if gain_atr >= be_atr_mult:
                        # Break-even stop locked: at least entry price or trailing
                        stop_prices[s] = max(entry_prices[s], peak_prices[s] - trail_atr_mult * atr_prev)
                    else:
                        stop_prices[s] = max(stop_prices[s], peak_prices[s] - 2.5 * atr_prev)

                    # Exit conditions: stop hit, or trend breakdown (close < slow ema), or macro regime breakdown
                    exit_triggered = False
                    if c_prev < stop_prices[s]:
                        exit_triggered = True
                    elif c_prev < features[s]["ema40"][t - 1]:
                        exit_triggered = True
                    elif not macro_ok:
                        exit_triggered = True

                    if exit_triggered and np.isfinite(o_exec):
                        fee = abs(positions[s] * o_exec) * cost_rate
                        cash += (positions[s] * o_exec - fee)
                        positions[s] = 0.0
                        in_position[s] = False

            # 2. Entry Evaluation
            if macro_ok:
                open_slots = sum(1 for s in universe_symbols if in_position[s])
                avail_slots = max_portfolio_slots - open_slots

                if avail_slots > 0:
                    candidates = []
                    for s in universe_symbols:
                        if not in_position[s]:
                            c_prev = features[s]["close"][t - 1]
                            ema10_prev = features[s]["ema10"][t - 1]
                            ema40_prev = features[s]["ema40"][t - 1]
                            dh_prev = features[s]["donchian_high_20"][t - 1] if entry_signal_type == "donchian_20" else features[s]["donchian_high_40"][t - 1]

                            # Check entry trigger
                            signal_fire = False
                            if entry_signal_type == "ema_cross":
                                signal_fire = (c_prev > ema10_prev) and (ema10_prev > ema40_prev)
                            elif entry_signal_type.startswith("donchian"):
                                signal_fire = (c_prev >= dh_prev) and (c_prev > ema40_prev)

                            if signal_fire:
                                mom = features[s]["mom14"][t - 1]
                                btc_mom = btc_f["mom14"][t - 1]
                                if require_relative_strength:
                                    if mom > btc_mom and mom > 0:
                                        candidates.append((s, mom))
                                else:
                                    if mom > 0:
                                        candidates.append((s, mom))

                    # Sort candidates by momentum score
                    candidates.sort(key=lambda x: x[1], reverse=True)

                    for s, score in candidates[:avail_slots]:
                        o_exec = o_now[s]
                        atr_prev = features[s]["atr14"][t - 1]
                        vol_prev = features[s]["realized_vol"][t - 1]
                        if np.isfinite(o_exec) and o_exec > 0 and np.isfinite(vol_prev) and vol_prev > 0:
                            # Volatility targeting weight
                            vol_scale = np.clip(target_annual_vol / vol_prev, 0.20, 1.20)
                            base_slot_equity = current_equity / max_portfolio_slots
                            target_alloc = base_slot_equity * vol_scale

                            fee = target_alloc * cost_rate
                            if cash >= (target_alloc + fee):
                                cash -= (target_alloc + fee)
                                positions[s] = target_alloc / o_exec
                                in_position[s] = True
                                entry_prices[s] = o_exec
                                peak_prices[s] = o_exec
                                stop_prices[s] = o_exec - 2.0 * atr_prev

        # Mark equity at bar close
        c_now = {s: features[s]["close"][t] for s in universe_symbols}
        close_val = sum(positions[s] * c_now[s] for s in universe_symbols if in_position[s] and np.isfinite(c_now[s]))
        navs[t] = cash + close_val

    return pd.Series(navs, index=timeline)


def main():
    print("Loading data...")
    universe = load_universe()
    train_data = slice_universe(universe, TRAIN_START, TRAIN_END)
    print("Train slice loaded:", TRAIN_START, "to", TRAIN_END)

    for freq in ["4h", "1h"]:
        print(f"\n--- Testing frequency {freq} ---")
        timeline, features = prepare_train_features(train_data, resample_freq=freq)
        print(f"Timeline: {len(timeline)} bars from {timeline[0]} to {timeline[-1]}")

        grid = []
        for uni_choice, sym_list in [
            ("all6", UNIVERSE),
            ("top4_liquid", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]),
            ("btc_eth_sol", ["BTCUSDT", "ETHUSDT", "SOLUSDT"]),
            ("btc_sol", ["BTCUSDT", "SOLUSDT"]),
        ]:
            for macro_ema in ["ema100", "ema200"]:
                for sig_type in ["ema_cross", "donchian_20"]:
                    for slots in [2, 3]:
                        for tv in [0.30, 0.35, 0.40]:
                            for trail in [2.0, 2.5, 3.0]:
                                for be in [1.0, 1.5]:
                                    for req_rs in [False, True]:
                                        nav = simulate_train_strategy(
                                            timeline=timeline,
                                            features=features,
                                            universe_symbols=sym_list,
                                            macro_filter_ema=macro_ema,
                                            entry_signal_type=sig_type,
                                            trail_atr_mult=trail,
                                            be_atr_mult=be,
                                            target_annual_vol=tv,
                                            max_portfolio_slots=slots,
                                            require_relative_strength=req_rs,
                                        )
                                        tot, cagr, maxdd, calmar = compute_metrics(nav)
                                        grid.append({
                                            "freq": freq,
                                            "uni": uni_choice,
                                            "macro": macro_ema,
                                            "sig": sig_type,
                                            "slots": slots,
                                            "tv": tv,
                                            "trail": trail,
                                            "be": be,
                                            "rs": req_rs,
                                            "cagr": cagr,
                                            "maxdd": maxdd,
                                            "calmar": calmar,
                                        })

        df_res = pd.DataFrame(grid).sort_values("calmar", ascending=False)
        print(f"Total configurations tested on {freq}: {len(df_res)}")
        print("\nTop 15 on Train:")
        print(df_res.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
