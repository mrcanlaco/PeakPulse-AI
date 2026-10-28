"""PeakPulse AI - Alpha Frontier Quantitative Discovery Engine.
Explores new mathematical alpha structures built on top of the robust Walk-Forward framework:
1. Volume-Absorption Confirmed Breakout
2. Idiosyncratic Residual Momentum (BTC Beta-Neutralized Relative Strength)
3. Breadth-Adaptive Convex Volatility Targeting
4. Multi-Horizon Donchian Ensembles
"""

from __future__ import annotations
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
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
    TOTAL_ONE_WAY_BPS,
)
from dao_vang.research.data_loader import load_universe, slice_universe
from dao_vang.research.walkforward_engine import prepare_multiasset_features, compute_metrics


def simulate_frontier_strategy(
    timeline: pd.DatetimeIndex,
    features: Dict[str, dict],
    universe_symbols: List[str],
    macro_filter_ema: str = "ema600",
    entry_donch_len: int = 40,
    exit_rule: str = "ema40",
    trail_atr_mult: float = 2.5,
    be_atr_mult: float = 1.8,
    target_risk_param: float = 0.32,
    max_slots: int = 2,
    use_market_breadth: bool = True,
    # Frontier Alpha Enhancements:
    volume_surge_mult: float = 0.0,       # 0.0: off, 1.15, 1.25, 1.35
    use_residual_momentum: bool = False,   # Beta-adjusted idiosyncratic momentum
    adaptive_breadth_convex: bool = False, # Scale 0.6x if <50% breadth, 1.15x if >80% breadth
    cost_rate_bps: float = TOTAL_ONE_WAY_BPS,
    initial_capital: float = 100_000.0,
) -> Tuple[pd.Series, dict]:
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

    entry_key = f"donch_{entry_donch_len}_h"

    for t in range(n):
        o_now = {s: features[s]["open"][t] for s in universe_symbols}
        open_val = sum(positions[s] * o_now[s] for s in universe_symbols if in_pos[s] and np.isfinite(o_now[s]))
        current_equity = cash + open_val

        if t >= warmup and current_equity > 0:
            btc_prev_c = btc_close[t - 1]
            btc_prev_m = btc_macro[t - 1]
            macro_ok = btc_prev_c > btc_prev_m

            # Market breadth evaluation
            breadth_factor = 1.0
            if use_market_breadth:
                bull_c = sum(1 for s in universe_symbols if features[s]["close"][t - 1] > features[s]["ema40"][t - 1])
                bull_ratio = bull_c / len(universe_symbols)

                if adaptive_breadth_convex:
                    if bull_ratio >= 0.80:
                        breadth_factor = 1.15
                    elif bull_ratio >= 0.50:
                        breadth_factor = 1.00
                    else:
                        breadth_factor = 0.60
                else:
                    if bull_ratio < 0.50:
                        breadth_factor = 0.70

            # 1. Check Exits
            for s in universe_symbols:
                if in_pos[s]:
                    c_prev = features[s]["close"][t - 1]
                    atr_prev = features[s]["atr14"][t - 1]
                    o_exec = o_now[s]

                    if c_prev > peak_p[s]:
                        peak_p[s] = c_prev

                    gain_atr = (peak_p[s] - entry_p[s]) / max(atr_prev, 1e-6)

                    # Dynamic Break-Even & Trailing Stop
                    if gain_atr >= be_atr_mult:
                        stop_p[s] = max(entry_p[s], peak_p[s] - trail_atr_mult * atr_prev)
                    else:
                        stop_p[s] = max(stop_p[s], peak_p[s] - 2.5 * atr_prev)

                    # Structural Exit Line
                    struct_exit = features[s]["ema40"][t - 1] if exit_rule == "ema40" else features[s]["donch_15_l"][t - 1]

                    exit_sig = (c_prev < stop_p[s]) or (c_prev < struct_exit) or (not macro_ok)

                    if exit_sig and np.isfinite(o_exec):
                        fee = abs(positions[s] * o_exec) * cost_rate
                        pnl = (positions[s] * o_exec - fee) - (positions[s] * entry_p[s])
                        trade_pnls.append(pnl)
                        total_fees += fee
                        cash += (positions[s] * o_exec - fee)
                        positions[s] = 0.0
                        in_pos[s] = False

            # 2. Check Entries
            if macro_ok:
                open_c = sum(1 for s in universe_symbols if in_pos[s])
                avail = max_slots - open_c
                if avail > 0:
                    cand = []
                    for s in universe_symbols:
                        if not in_pos[s]:
                            c_prev = features[s]["close"][t - 1]
                            ema40_prev = features[s]["ema40"][t - 1]
                            sig_thresh = features[s][entry_key][t - 1]

                            if c_prev >= sig_thresh and c_prev > ema40_prev:
                                # Volume surge check
                                if volume_surge_mult > 0.0:
                                    v_prev = features[s]["volume"][t - 1]
                                    v_sma = features[s]["vol_sma20"][t - 1]
                                    if v_prev < (volume_surge_mult * v_sma):
                                        continue

                                # Score: Residual Momentum or Raw Momentum
                                if use_residual_momentum:
                                    score = features[s]["res_mom15"][t - 1]
                                else:
                                    score = features[s]["mom14"][t - 1]

                                if score > 0:
                                    cand.append((s, score))

                    cand.sort(key=lambda x: x[1], reverse=True)

                    for s, score in cand[:avail]:
                        o_exec = o_now[s]
                        vol_prev = features[s]["ann_vol"][t - 1]
                        atr_prev = features[s]["atr14"][t - 1]
                        if np.isfinite(o_exec) and o_exec > 0 and np.isfinite(atr_prev) and atr_prev > 0:
                            v_scale = np.clip(target_risk_param / max(vol_prev, 0.15), 0.20, 1.10)
                            alloc = (current_equity / max_slots) * v_scale * breadth_factor

                            fee = alloc * cost_rate
                            if cash >= (alloc + fee):
                                cash -= (alloc + fee)
                                total_fees += fee
                                positions[s] = alloc / o_exec
                                in_pos[s] = True
                                entry_p[s] = o_exec
                                peak_p[s] = o_exec
                                stop_p[s] = o_exec - 2.0 * atr_prev

        # 3. Apply funding rate deduction
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


def run_discovery():
    print("Loading multiyear market data 2020-2026...")
    universe = load_universe()
    full_data = slice_universe(universe, FULL_START, FULL_END)
    timeline, features = prepare_multiasset_features(full_data, resample_freq="4h")
    symbols = list(universe.keys())

    # Precompute custom indicators on 4h bars
    btc_c = features["BTCUSDT"]["close"]
    btc_ret = pd.Series(btc_c).pct_change().fillna(0.0)

    for s in symbols:
        c = features[s]["close"]
        h = features[s]["high"]
        l = features[s]["low"]
        v = features[s]["volume"]

        features[s]["ema450"] = pd.Series(c).shift(1).ewm(span=450).mean().to_numpy()
        features[s]["ema500"] = pd.Series(c).shift(1).ewm(span=500).mean().to_numpy()
        features[s]["ema600"] = pd.Series(c).shift(1).ewm(span=600).mean().to_numpy()

        for d_len in [30, 40, 50]:
            features[s][f"donch_{d_len}_h"] = pd.Series(h).shift(1).rolling(d_len, min_periods=d_len).max().to_numpy()
        features[s]["donch_15_l"] = pd.Series(l).shift(1).rolling(15, min_periods=15).min().to_numpy()

        # Volume SMA 20
        features[s]["vol_sma20"] = pd.Series(v).shift(1).rolling(20, min_periods=10).mean().to_numpy()

        # Residual Momentum: R_s - Beta * R_btc over 120 bars (20 days)
        s_ret = pd.Series(c).pct_change().fillna(0.0)
        cov = s_ret.rolling(120).cov(btc_ret)
        var_btc = btc_ret.rolling(120).var().replace(0, np.nan)
        beta = (cov / var_btc).clip(0.2, 3.0).fillna(1.0)
        idiosyncratic_ret = s_ret - beta * btc_ret
        features[s]["res_mom15"] = idiosyncratic_ret.shift(1).rolling(15).sum().fillna(0.0).to_numpy()

    # Define Frontier Experiment Configurations
    frontier_configs = [
        # 1. Baseline Alpha-01 Champion
        {
            "id": "FRONTIER-00_ALPHA01_BASELINE",
            "desc": "Baseline Champion (Donch40, EMA600, BE1.8, Vol0.32)",
            "macro": "ema600", "donch": 40, "be": 1.8, "vol": 0.32,
            "vol_surge": 0.0, "res_mom": False, "breadth_convex": False,
        },
        # 2. Volume Absorption Filter 1.15x
        {
            "id": "FRONTIER-01_VOL_SURGE_1.15X",
            "desc": "Volume Surge > 1.15x 20SMA",
            "macro": "ema600", "donch": 40, "be": 1.8, "vol": 0.32,
            "vol_surge": 1.15, "res_mom": False, "breadth_convex": False,
        },
        # 3. Volume Absorption Filter 1.25x
        {
            "id": "FRONTIER-02_VOL_SURGE_1.25X",
            "desc": "Volume Surge > 1.25x 20SMA",
            "macro": "ema600", "donch": 40, "be": 1.8, "vol": 0.32,
            "vol_surge": 1.25, "res_mom": False, "breadth_convex": False,
        },
        # 4. Residual Momentum
        {
            "id": "FRONTIER-03_RESIDUAL_MOMENTUM",
            "desc": "Idiosyncratic Residual Momentum against BTC Beta",
            "macro": "ema600", "donch": 40, "be": 1.8, "vol": 0.32,
            "vol_surge": 0.0, "res_mom": True, "breadth_convex": False,
        },
        # 5. Adaptive Breadth Convex Sizing
        {
            "id": "FRONTIER-04_BREADTH_CONVEX",
            "desc": "Breadth Convex: 1.15x when >80% bull, 0.6x when <50%",
            "macro": "ema600", "donch": 40, "be": 1.8, "vol": 0.32,
            "vol_surge": 0.0, "res_mom": False, "breadth_convex": True,
        },
        # 6. Combo: Volume Surge 1.15x + Breadth Convex
        {
            "id": "FRONTIER-05_VOL_SURGE_BREADTH_CONVEX",
            "desc": "Combo: Vol Surge 1.15x + Breadth Convex",
            "macro": "ema600", "donch": 40, "be": 1.8, "vol": 0.32,
            "vol_surge": 1.15, "res_mom": False, "breadth_convex": True,
        },
        # 7. Donchian 40 with BE 1.5 + Vol Surge 1.15x
        {
            "id": "FRONTIER-06_D40_BE1.5_VOL_SURGE",
            "desc": "Donch 40, BE 1.5 + Vol Surge 1.15x",
            "macro": "ema600", "donch": 40, "be": 1.5, "vol": 0.32,
            "vol_surge": 1.15, "res_mom": False, "breadth_convex": False,
        },
        # 8. Donchian 30 with Macro EMA500 + Breadth Convex (Fast Agile)
        {
            "id": "FRONTIER-07_D30_EMA500_BREADTH_CONVEX",
            "desc": "Donch 30, EMA500 + Breadth Convex",
            "macro": "ema500", "donch": 30, "be": 1.5, "vol": 0.34,
            "vol_surge": 0.0, "res_mom": False, "breadth_convex": True,
        },
        # 9. Super Conservative Vol 0.28 + Vol Surge 1.20x (Target Min Drawdown)
        {
            "id": "FRONTIER-08_CONSERVATIVE_MIN_DD",
            "desc": "Vol 0.28 + Vol Surge 1.20x (Ultra Low Drawdown)",
            "macro": "ema600", "donch": 40, "be": 1.8, "vol": 0.28,
            "vol_surge": 1.20, "res_mom": False, "breadth_convex": False,
        },
        # 10. Multi-Asset 3-Slots Expansion (Slots = 3, Vol = 0.30)
        {
            "id": "FRONTIER-09_3SLOTS_DIVERSIFICATION",
            "desc": "3-Slots Multi-Asset Diversification",
            "macro": "ema600", "donch": 40, "be": 1.8, "vol": 0.30,
            "vol_surge": 0.0, "res_mom": False, "breadth_convex": True,
            "slots": 3,
        },
    ]

    print("\n" + "=" * 120)
    print(f"{'CANDIDATE ID':<33} | {'TRAIN CALMAR':<12} | {'VAL CALMAR':<10} | {'TEST 2026':<10} | {'FULL CAGR':<10} | {'FULL MAXDD':<10} | {'FULL CALMAR':<11} | {'PF':<5}")
    print("=" * 120)

    train_mask = (timeline >= TRAIN_START) & (timeline <= TRAIN_END)
    val_mask = (timeline >= VAL_START) & (timeline <= VAL_END)
    test_mask = (timeline >= TEST_START) & (timeline <= TEST_END)

    results = []

    for cfg in frontier_configs:
        c_id = cfg["id"]
        slots = cfg.get("slots", 2)
        nav_series, full_stats = simulate_frontier_strategy(
            timeline=timeline,
            features=features,
            universe_symbols=symbols,
            macro_filter_ema=cfg["macro"],
            entry_donch_len=cfg["donch"],
            be_atr_mult=cfg["be"],
            target_risk_param=cfg["vol"],
            volume_surge_mult=cfg["vol_surge"],
            use_residual_momentum=cfg["res_mom"],
            adaptive_breadth_convex=cfg["breadth_convex"],
            max_slots=slots,
        )

        # Compute train, val, test
        train_nav = nav_series.loc[train_mask]
        val_nav = nav_series.loc[val_mask]
        test_nav = nav_series.loc[test_mask]

        _, tr_cagr, tr_mdd, tr_calmar = compute_metrics(train_nav)
        _, val_cagr, val_mdd, val_calmar = compute_metrics(val_nav)
        _, test_cagr, test_mdd, test_calmar = compute_metrics(test_nav)

        f_cagr = full_stats["cagr_pct"]
        f_mdd = full_stats["maxdd_pct"]
        f_calmar = full_stats["calmar"]
        f_pf = full_stats["profit_factor"]

        print(f"{c_id:<33} | {tr_calmar:<12.3f} | {val_calmar:<10.3f} | {test_cagr*100:>+7.2f}%   | {f_cagr:>7.2f}%   | {f_mdd:>7.2f}%   | {f_calmar:<11.3f} | {f_pf:<5.2f}")

        results.append({
            "candidate_id": c_id,
            "description": cfg["desc"],
            "config": cfg,
            "train": {"cagr_pct": round(tr_cagr * 100, 2), "maxdd_pct": round(tr_mdd * 100, 2), "calmar": round(tr_calmar, 3)},
            "validation": {"cagr_pct": round(val_cagr * 100, 2), "maxdd_pct": round(val_mdd * 100, 2), "calmar": round(val_calmar, 3)},
            "test_2026": {"cagr_pct": round(test_cagr * 100, 2), "maxdd_pct": round(test_mdd * 100, 2), "calmar": round(test_calmar, 3)},
            "full_period": full_stats,
        })

    print("=" * 120)

    # Save results
    out_file = ARTIFACTS_DIR / "alpha_frontier_discovery_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nAll frontier discovery results saved to: {out_file}")


if __name__ == "__main__":
    run_discovery()
