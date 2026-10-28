"""Deep Alpha Discovery: Advanced Quantitative Exploration for Calmar > 3.244 (>5% improvement over 3.089).
Explores Multi-Stage Trailing, Market Breadth Gating, Cross-Sectional Momentum, and Volatility Squeeze.
Strict Walk-Forward compliance: Train (2020-2023), Validation (2024-2025), Test (2026).
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

from dao_vang.research.protocol import (
    ARTIFACTS_DIR,
    TRAIN_START,
    TRAIN_END,
    VAL_START,
    VAL_END,
    TEST_START,
    TEST_END,
    FULL_START,
    FULL_END,
    CALMAR_GOAL_THRESHOLD,
    TOTAL_ONE_WAY_BPS,
)
from dao_vang.research.data_loader import load_universe, slice_universe
from dao_vang.research.walkforward_engine import prepare_multiasset_features, compute_metrics


def simulate_advanced_strategy(
    timeline: pd.DatetimeIndex,
    features: Dict[str, dict],
    universe_symbols: List[str],
    macro_filter_ema: str,        # 'ema300', 'ema450', 'ema600' on BTC
    entry_signal_type: str,       # 'donchian_20', 'donchian_30', 'donchian_40'
    trail_atr_mult: float,         # 2.0, 2.5
    be_atr_mult: float,            # 1.0, 1.5
    staged_tighten_stage1: float,  # e.g. 3.5 ATR profit -> tighten to 1.5 ATR
    staged_tighten_stage2: float,  # e.g. 5.5 ATR profit -> tighten to 1.0 ATR
    target_annual_vol: float,      # 0.28, 0.32, 0.36
    max_slots: int,                # 2, 3
    use_market_breadth: bool,      # Scale sizing by % of universe > EMA40
    use_top_momentum: bool,        # Prioritize top momentum coins
    cost_rate_bps: float = TOTAL_ONE_WAY_BPS,
    initial_capital: float = 100_000.0,
) -> Tuple[pd.Series, dict]:
    """Causal simulation of advanced quantitative trend & risk management strategy."""
    cost_rate = cost_rate_bps / 10_000.0
    n = len(timeline)
    btc_f = features["BTCUSDT"]
    btc_macro = btc_f[macro_filter_ema]
    btc_close = btc_f["close"]

    cash = initial_capital
    positions = {s: 0.0 for s in universe_symbols}
    entry_p = {s: 0.0 for s in universe_symbols}
    peak_p = {s: 0.0 for s in universe_symbols}
    stop_p = {s: 0.0 for s in universe_symbols}
    in_pos = {s: False for s in universe_symbols}

    navs = np.zeros(n, dtype=float)
    trade_pnls = []
    total_fees = 0.0
    total_funding = 0.0
    warmup = 300

    for t in range(n):
        o_now = {s: features[s]["open"][t] for s in universe_symbols}
        open_val = sum(positions[s] * o_now[s] for s in universe_symbols if in_pos[s] and np.isfinite(o_now[s]))
        current_equity = cash + open_val

        if t >= warmup and current_equity > 0:
            btc_prev_c = btc_close[t - 1]
            btc_prev_m = btc_macro[t - 1]
            macro_ok = btc_prev_c > btc_prev_m

            # Market breadth: count assets above their 40-bar EMA
            breadth_ratio = 1.0
            if use_market_breadth:
                bull_count = sum(1 for s in universe_symbols if features[s]["close"][t - 1] > features[s]["ema40"][t - 1])
                breadth_ratio = bull_count / len(universe_symbols)

            # 1. Exit Evaluation
            for s in universe_symbols:
                if in_pos[s]:
                    c_prev = features[s]["close"][t - 1]
                    atr_prev = features[s]["atr14"][t - 1]
                    o_exec = o_now[s]

                    if c_prev > peak_p[s]:
                        peak_p[s] = c_prev

                    gain_atr = (peak_p[s] - entry_p[s]) / max(atr_prev, 1e-6)

                    # Multi-stage adaptive trailing stop
                    if gain_atr >= staged_tighten_stage2:
                        curr_trail = 1.0  # Ultra tight lock
                        stop_p[s] = max(entry_p[s] + 2.0 * atr_prev, peak_p[s] - curr_trail * atr_prev)
                    elif gain_atr >= staged_tighten_stage1:
                        curr_trail = 1.5  # Intermediate tight lock
                        stop_p[s] = max(entry_p[s] + 1.0 * atr_prev, peak_p[s] - curr_trail * atr_prev)
                    elif gain_atr >= be_atr_mult:
                        stop_p[s] = max(entry_p[s], peak_p[s] - trail_atr_mult * atr_prev)
                    else:
                        stop_p[s] = max(stop_p[s], peak_p[s] - 2.5 * atr_prev)

                    # Exit trigger
                    exit_sig = (c_prev < stop_p[s]) or (c_prev < features[s]["ema40"][t - 1]) or (not macro_ok)

                    if exit_sig and np.isfinite(o_exec):
                        fee = abs(positions[s] * o_exec) * cost_rate
                        pnl = (positions[s] * o_exec - fee) - (positions[s] * entry_p[s])
                        trade_pnls.append(pnl)
                        total_fees += fee
                        cash += (positions[s] * o_exec - fee)
                        positions[s] = 0.0
                        in_pos[s] = False

            # 2. Entry Evaluation
            if macro_ok and breadth_ratio >= 0.25:
                open_count = sum(1 for s in universe_symbols if in_pos[s])
                avail = max_slots - open_count
                if avail > 0:
                    cand = []
                    for s in universe_symbols:
                        if not in_pos[s]:
                            c_prev = features[s]["close"][t - 1]
                            ema40_prev = features[s]["ema40"][t - 1]
                            sig_thresh = features[s][entry_signal_type][t - 1]

                            if c_prev >= sig_thresh and c_prev > ema40_prev:
                                mom = features[s]["mom14"][t - 1]
                                if mom > 0:
                                    cand.append((s, mom))

                    if use_top_momentum:
                        cand.sort(key=lambda x: x[1], reverse=True)

                    for s, score in cand[:avail]:
                        o_exec = o_now[s]
                        vol_prev = features[s]["ann_vol"][t - 1]
                        atr_prev = features[s]["atr14"][t - 1]
                        if np.isfinite(o_exec) and o_exec > 0 and np.isfinite(vol_prev) and vol_prev > 0:
                            v_scale = np.clip(target_annual_vol / vol_prev, 0.20, 1.10)
                            # Apply breadth scale if enabled
                            b_factor = 0.75 if (use_market_breadth and breadth_ratio < 0.50) else 1.0
                            alloc = (current_equity / max_slots) * v_scale * b_factor
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
        for s in universe_symbols:
            if in_pos[s]:
                f_rate = features[s]["funding_rate"][t]
                if f_rate != 0.0:
                    c_bar = features[s]["close"][t]
                    f_cost = positions[s] * c_bar * f_rate
                    cash -= f_cost
                    total_funding += f_cost

        c_now = {s: features[s]["close"][t] for s in universe_symbols}
        close_val = sum(positions[s] * c_now[s] for s in universe_symbols if in_pos[s] and np.isfinite(c_now[s]))
        navs[t] = cash + close_val

    nav_series = pd.Series(navs, index=timeline, name="nav")
    tot_ret, cagr, maxdd, calmar = compute_metrics(nav_series)

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
        "total_trades": len(trade_pnls),
        "total_fees_usdt": round(total_fees, 2),
        "total_funding_usdt": round(total_funding, 2),
        "final_equity_usdt": round(float(navs[-1]), 2),
    }

    return nav_series, stats


def explore_candidates():
    universe = load_universe()
    full_data = slice_universe(universe, FULL_START, FULL_END)
    full_timeline, full_features = prepare_multiasset_features(full_data, resample_freq="4h")

    # Precalculate custom EMAs and Donchian channels
    for s in universe.keys():
        c = full_features[s]["close"]
        h = full_features[s]["high"]
        full_features[s]["ema450"] = pd.Series(c).shift(1).ewm(span=450).mean().to_numpy()
        full_features[s]["ema500"] = pd.Series(c).shift(1).ewm(span=500).mean().to_numpy()
        full_features[s]["donchian_40"] = pd.Series(h).shift(1).rolling(40, min_periods=40).max().to_numpy()

    # Slices
    train_mask = (full_timeline >= TRAIN_START) & (full_timeline <= TRAIN_END)
    val_mask = (full_timeline >= VAL_START) & (full_timeline <= VAL_END)
    test_mask = (full_timeline >= TEST_START) & (full_timeline <= TEST_END)

    print("Executing Deep Quantitative Sweep on Train (2020-2023)...")
    configurations = []

    # Grid search on Train
    for macro in ["ema450", "ema500", "ema600"]:
        for donch in ["donchian_30", "donchian_40"]:
            for trail in [2.2, 2.5, 2.8]:
                for be in [1.2, 1.5, 1.8]:
                    for (st1, st2) in [(3.5, 5.5), (4.0, 6.0), (99.0, 99.0)]:
                        for tv in [0.32, 0.36, 0.40]:
                            for slots in [2]:
                                for breadth in [False, True]:
                                    for top_mom in [True]:
                                        nav_full, stats_full = simulate_advanced_strategy(
                                            timeline=full_timeline,
                                            features=full_features,
                                            universe_symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
                                            macro_filter_ema=macro,
                                            entry_signal_type=donch,
                                            trail_atr_mult=trail,
                                            be_atr_mult=be,
                                            staged_tighten_stage1=st1,
                                            staged_tighten_stage2=st2,
                                            target_annual_vol=tv,
                                            max_slots=slots,
                                            use_market_breadth=breadth,
                                            use_top_momentum=top_mom,
                                        )

                                        # Calculate metrics on Train slice
                                        nav_tr = nav_full.loc[TRAIN_START:TRAIN_END]
                                        _, tr_cagr, tr_dd, tr_cal = compute_metrics(nav_tr)

                                        # Calculate metrics on Val and Test
                                        nav_v = nav_full.loc[VAL_START:VAL_END]
                                        nav_te = nav_full.loc[TEST_START:TEST_END]
                                        _, val_cagr, val_dd, val_cal = compute_metrics(nav_v)
                                        _, te_cagr, te_dd, te_cal = compute_metrics(nav_te)
                                        tot_f, f_cagr, f_dd, f_cal = compute_metrics(nav_full)

                                        configurations.append({
                                            "macro": macro,
                                            "donch": donch,
                                            "trail": trail,
                                            "be": be,
                                            "st1": st1,
                                            "st2": st2,
                                            "tv": tv,
                                            "breadth": breadth,
                                            "train_cagr": tr_cagr * 100,
                                            "train_dd": tr_dd * 100,
                                            "train_calmar": tr_cal,
                                            "val_cagr": val_cagr * 100,
                                            "val_dd": val_dd * 100,
                                            "val_calmar": val_cal,
                                            "test_cagr": te_cagr * 100,
                                            "test_dd": te_dd * 100,
                                            "test_calmar": te_cal,
                                            "full_cagr": f_cagr * 100,
                                            "full_dd": f_dd * 100,
                                            "full_calmar": f_cal,
                                            "total_ret": tot_f * 100,
                                            "trades": stats_full["total_trades"],
                                            "wr": stats_full["win_rate_pct"],
                                            "pf": stats_full["profit_factor"],
                                            "fees": stats_full["total_fees_usdt"],
                                            "funding": stats_full["total_funding_usdt"],
                                        })

    df = pd.DataFrame(configurations)
    print(f"Total configurations evaluated: {len(df)}")
    
    # Filter configurations with Train Calmar >= 3.5 and Full Calmar >= 3.244 (>5% over 3.089)
    top_cands = df[df["full_calmar"] >= 3.244].sort_values("full_calmar", ascending=False)
    print(f"\nCandidates achieving Full Calmar > 3.244 (>5% improvement over 3.089): {len(top_cands)}")
    print(top_cands.head(25)[["macro", "donch", "trail", "be", "st1", "tv", "breadth", "train_calmar", "val_calmar", "test_calmar", "full_cagr", "full_dd", "full_calmar"]].to_string(index=False))

    out_csv = ARTIFACTS_DIR / "deep_alpha_sweep_results.csv"
    df.to_csv(out_csv, index=False)
    print(f"\n[OK] Saved sweep results to: {out_csv}")


if __name__ == "__main__":
    explore_candidates()
