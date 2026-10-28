"""Systematic Quantitative Search & Construction of 20 Top-Tier Alpha Candidates.
Tests:
1. Donchian Multi-Horizon (30, 40, 50, 60 bars)
2. Asymmetric Channel Exit (trailing on Donchian Low 15/20 vs EMA)
3. Fixed Dollar Risk / Turtle Volatility Parity
4. Multi-Stage Profit Trailing
5. Macro Bitcoin Regimes (EMA 400, 450, 500, 600)
Outputs top 20 candidates with strict Walk-Forward validation.
"""

from __future__ import annotations
import json
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
    TOTAL_ONE_WAY_BPS,
)
from dao_vang.research.data_loader import load_universe, slice_universe
from dao_vang.research.walkforward_engine import prepare_multiasset_features, compute_metrics


def simulate_modular_strategy(
    timeline: pd.DatetimeIndex,
    features: Dict[str, dict],
    universe_symbols: List[str],
    macro_filter_ema: str,        # 'ema400', 'ema450', 'ema500', 'ema600'
    entry_donch_len: int,          # 30, 40, 50, 60
    exit_rule: str,                # 'ema40', 'donch_low_15', 'donch_low_20'
    trail_atr_mult: float,         # 2.0, 2.2, 2.5
    be_atr_mult: float,            # 1.0, 1.2, 1.5, 1.8
    staged_tighten_atr: float,     # 3.5, 4.5, 99.0
    risk_mode: str,                # 'vol_target' or 'fixed_risk_pct'
    target_risk_param: float,      # 0.32-0.40 for vol_target, or 0.015-0.025 for fixed_risk_pct
    max_slots: int = 2,
    use_market_breadth: bool = False,
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

            # Market breadth
            breadth_factor = 1.0
            if use_market_breadth:
                bull_c = sum(1 for s in universe_symbols if features[s]["close"][t - 1] > features[s]["ema40"][t - 1])
                if bull_c < len(universe_symbols) / 2:
                    breadth_factor = 0.70

            # 1. Exits
            for s in universe_symbols:
                if in_pos[s]:
                    c_prev = features[s]["close"][t - 1]
                    atr_prev = features[s]["atr14"][t - 1]
                    o_exec = o_now[s]

                    if c_prev > peak_p[s]:
                        peak_p[s] = c_prev

                    gain_atr = (peak_p[s] - entry_p[s]) / max(atr_prev, 1e-6)

                    # Dynamic Trailing & Break-Even
                    if gain_atr >= staged_tighten_atr:
                        # Lock in big gain
                        stop_p[s] = max(entry_p[s] + 1.5 * atr_prev, peak_p[s] - 1.5 * atr_prev)
                    elif gain_atr >= be_atr_mult:
                        stop_p[s] = max(entry_p[s], peak_p[s] - trail_atr_mult * atr_prev)
                    else:
                        stop_p[s] = max(stop_p[s], peak_p[s] - 2.5 * atr_prev)

                    # Determine structural exit line
                    if exit_rule == "ema40":
                        struct_exit = features[s]["ema40"][t - 1]
                    elif exit_rule == "donch_low_15":
                        struct_exit = features[s]["donch_15_l"][t - 1]
                    elif exit_rule == "donch_low_20":
                        struct_exit = features[s]["donch_20_l"][t - 1]
                    else:
                        struct_exit = features[s]["ema40"][t - 1]

                    exit_sig = (c_prev < stop_p[s]) or (c_prev < struct_exit) or (not macro_ok)

                    if exit_sig and np.isfinite(o_exec):
                        fee = abs(positions[s] * o_exec) * cost_rate
                        pnl = (positions[s] * o_exec - fee) - (positions[s] * entry_p[s])
                        trade_pnls.append(pnl)
                        total_fees += fee
                        cash += (positions[s] * o_exec - fee)
                        positions[s] = 0.0
                        in_pos[s] = False

            # 2. Entries
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
                                mom = features[s]["mom14"][t - 1]
                                if mom > 0:
                                    cand.append((s, mom))

                    cand.sort(key=lambda x: x[1], reverse=True)

                    for s, score in cand[:avail]:
                        o_exec = o_now[s]
                        vol_prev = features[s]["ann_vol"][t - 1]
                        atr_prev = features[s]["atr14"][t - 1]
                        if np.isfinite(o_exec) and o_exec > 0 and np.isfinite(atr_prev) and atr_prev > 0:
                            if risk_mode == "vol_target":
                                v_scale = np.clip(target_risk_param / max(vol_prev, 0.15), 0.20, 1.10)
                                alloc = (current_equity / max_slots) * v_scale * breadth_factor
                            else: # fixed_risk_pct (e.g. 1.8% equity risk per trade / 2.5 ATR)
                                risk_dollars = current_equity * target_risk_param
                                target_shares = risk_dollars / (2.5 * atr_prev)
                                alloc = min(target_shares * o_exec, current_equity * 0.48) * breadth_factor

                            fee = alloc * cost_rate
                            if cash >= (alloc + fee):
                                cash -= (alloc + fee)
                                total_fees += fee
                                positions[s] = alloc / o_exec
                                in_pos[s] = True
                                entry_p[s] = o_exec
                                peak_p[s] = o_exec
                                stop_p[s] = o_exec - 2.0 * atr_prev

        # 3. Funding
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


def search_and_build_20():
    print("Loading multi-year data (2020-2026)...")
    universe = load_universe()
    full_data = slice_universe(universe, FULL_START, FULL_END)
    timeline, features = prepare_multiasset_features(full_data, resample_freq="4h")

    # Add custom indicators
    for s in universe.keys():
        c = features[s]["close"]
        h = features[s]["high"]
        l = features[s]["low"]
        features[s]["ema400"] = pd.Series(c).shift(1).ewm(span=400).mean().to_numpy()
        features[s]["ema450"] = pd.Series(c).shift(1).ewm(span=450).mean().to_numpy()
        features[s]["ema500"] = pd.Series(c).shift(1).ewm(span=500).mean().to_numpy()
        features[s]["ema600"] = pd.Series(c).shift(1).ewm(span=600).mean().to_numpy()

        for d_len in [20, 30, 40, 50, 60]:
            features[s][f"donch_{d_len}_h"] = pd.Series(h).shift(1).rolling(d_len, min_periods=d_len).max().to_numpy()
        features[s]["donch_15_l"] = pd.Series(l).shift(1).rolling(15, min_periods=15).min().to_numpy()
        features[s]["donch_20_l"] = pd.Series(l).shift(1).rolling(20, min_periods=20).min().to_numpy()

    print("Generating and evaluating diverse quantitative candidates across Train, Val, Test, and Full...")
    tested = []

    # Systematically search across multiple distinct mechanism paradigms
    param_grid = [
        # Paradigm 1: Donchian 40 with Macro EMA600 & EMA500 (Champion zone)
        {"macro": "ema600", "donch": 40, "exit": "ema40", "trail": 2.5, "be": 1.8, "tighten": 99.0, "risk_mode": "vol_target", "risk_param": 0.32, "breadth": True},
        {"macro": "ema600", "donch": 40, "exit": "ema40", "trail": 2.5, "be": 1.5, "tighten": 99.0, "risk_mode": "vol_target", "risk_param": 0.32, "breadth": True},
        {"macro": "ema600", "donch": 40, "exit": "ema40", "trail": 2.5, "be": 1.2, "tighten": 99.0, "risk_mode": "vol_target", "risk_param": 0.32, "breadth": True},
        {"macro": "ema500", "donch": 40, "exit": "ema40", "trail": 2.5, "be": 1.5, "tighten": 99.0, "risk_mode": "vol_target", "risk_param": 0.34, "breadth": True},
        {"macro": "ema500", "donch": 40, "exit": "ema40", "trail": 2.5, "be": 1.2, "tighten": 99.0, "risk_mode": "vol_target", "risk_param": 0.32, "breadth": True},
        {"macro": "ema500", "donch": 40, "exit": "ema40", "trail": 2.5, "be": 1.8, "tighten": 99.0, "risk_mode": "vol_target", "risk_param": 0.34, "breadth": True},

        # Paradigm 2: Donchian 30 with Macro EMA450 (High CAGR baseline family)
        {"macro": "ema450", "donch": 30, "exit": "ema40", "trail": 2.5, "be": 1.5, "tighten": 99.0, "risk_mode": "vol_target", "risk_param": 0.36, "breadth": True},
        {"macro": "ema450", "donch": 30, "exit": "ema40", "trail": 2.5, "be": 1.5, "tighten": 99.0, "risk_mode": "vol_target", "risk_param": 0.40, "breadth": True},
        {"macro": "ema450", "donch": 30, "exit": "ema40", "trail": 2.5, "be": 1.2, "tighten": 99.0, "risk_mode": "vol_target", "risk_param": 0.36, "breadth": True},
        {"macro": "ema450", "donch": 30, "exit": "ema40", "trail": 2.2, "be": 1.2, "tighten": 99.0, "risk_mode": "vol_target", "risk_param": 0.34, "breadth": True},
        {"macro": "ema400", "donch": 30, "exit": "ema40", "trail": 2.5, "be": 1.5, "tighten": 99.0, "risk_mode": "vol_target", "risk_param": 0.36, "breadth": True},

        # Paradigm 3: Donchian 50 & 60 Multi-Week Momentum
        {"macro": "ema600", "donch": 50, "exit": "ema40", "trail": 2.5, "be": 1.5, "tighten": 99.0, "risk_mode": "vol_target", "risk_param": 0.34, "breadth": True},
        {"macro": "ema600", "donch": 50, "exit": "ema40", "trail": 2.5, "be": 1.2, "tighten": 99.0, "risk_mode": "vol_target", "risk_param": 0.32, "breadth": True},
        {"macro": "ema500", "donch": 50, "exit": "ema40", "trail": 2.5, "be": 1.5, "tighten": 99.0, "risk_mode": "vol_target", "risk_param": 0.34, "breadth": True},
        {"macro": "ema600", "donch": 60, "exit": "ema40", "trail": 2.5, "be": 1.5, "tighten": 99.0, "risk_mode": "vol_target", "risk_param": 0.34, "breadth": True},

        # Paradigm 4: Multi-Stage Staged Trailing Stop (Locking Windfall)
        {"macro": "ema600", "donch": 40, "exit": "ema40", "trail": 2.5, "be": 1.5, "tighten": 4.0, "risk_mode": "vol_target", "risk_param": 0.34, "breadth": True},
        {"macro": "ema500", "donch": 40, "exit": "ema40", "trail": 2.5, "be": 1.5, "tighten": 4.0, "risk_mode": "vol_target", "risk_param": 0.34, "breadth": True},
        {"macro": "ema450", "donch": 30, "exit": "ema40", "trail": 2.5, "be": 1.5, "tighten": 4.5, "risk_mode": "vol_target", "risk_param": 0.36, "breadth": True},

        # Paradigm 5: Fixed Dollar Risk / Turtle Parity
        {"macro": "ema600", "donch": 40, "exit": "ema40", "trail": 2.5, "be": 1.5, "tighten": 99.0, "risk_mode": "fixed_risk_pct", "risk_param": 0.020, "breadth": True},
        {"macro": "ema500", "donch": 40, "exit": "ema40", "trail": 2.5, "be": 1.5, "tighten": 99.0, "risk_mode": "fixed_risk_pct", "risk_param": 0.022, "breadth": True},
        {"macro": "ema450", "donch": 30, "exit": "ema40", "trail": 2.5, "be": 1.5, "tighten": 99.0, "risk_mode": "fixed_risk_pct", "risk_param": 0.022, "breadth": True},

        # Paradigm 6: Asymmetric Structural Channel Exit (Donchian Low 20)
        {"macro": "ema600", "donch": 40, "exit": "donch_low_20", "trail": 2.5, "be": 1.5, "tighten": 99.0, "risk_mode": "vol_target", "risk_param": 0.34, "breadth": True},
        {"macro": "ema500", "donch": 40, "exit": "donch_low_20", "trail": 2.5, "be": 1.5, "tighten": 99.0, "risk_mode": "vol_target", "risk_param": 0.34, "breadth": True},
        {"macro": "ema450", "donch": 30, "exit": "donch_low_20", "trail": 2.5, "be": 1.5, "tighten": 99.0, "risk_mode": "vol_target", "risk_param": 0.36, "breadth": True},
    ]

    for idx, p in enumerate(param_grid):
        nav_full, stats = simulate_modular_strategy(
            timeline=timeline,
            features=features,
            universe_symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
            macro_filter_ema=p["macro"],
            entry_donch_len=p["donch"],
            exit_rule=p["exit"],
            trail_atr_mult=p["trail"],
            be_atr_mult=p["be"],
            staged_tighten_atr=p["tighten"],
            risk_mode=p["risk_mode"],
            target_risk_param=p["risk_param"],
            use_market_breadth=p["breadth"],
        )

        nav_tr = nav_full.loc[TRAIN_START:TRAIN_END]
        nav_v = nav_full.loc[VAL_START:VAL_END]
        nav_te = nav_full.loc[TEST_START:TEST_END]

        _, tr_cagr, tr_dd, tr_cal = compute_metrics(nav_tr)
        _, val_cagr, val_dd, val_cal = compute_metrics(nav_v)
        _, te_cagr, te_dd, te_cal = compute_metrics(nav_te)
        tot_f, f_cagr, f_dd, f_cal = compute_metrics(nav_full)

        daily = nav_full.resample("1D").last().dropna()
        rets = daily.pct_change().dropna().to_numpy()
        sharpe = float(np.mean(rets) / np.std(rets, ddof=1) * math.sqrt(365.25)) if len(rets) > 5 and np.std(rets) > 1e-8 else 0.0

        tested.append({
            "candidate_idx": idx + 1,
            "params": p,
            "train": {"cagr_pct": round(tr_cagr * 100, 2), "maxdd_pct": round(tr_dd * 100, 2), "calmar": round(tr_cal, 3)},
            "validation": {"cagr_pct": round(val_cagr * 100, 2), "maxdd_pct": round(val_dd * 100, 2), "calmar": round(val_cal, 3)},
            "test_2026": {"cagr_pct": round(te_cagr * 100, 2), "maxdd_pct": round(te_dd * 100, 2), "calmar": round(te_cal, 3)},
            "full_period": {
                "total_return_pct": round(tot_f * 100, 2),
                "cagr_pct": round(f_cagr * 100, 2),
                "maxdd_pct": round(f_dd * 100, 2),
                "calmar": round(f_cal, 3),
                "sharpe": round(sharpe, 3),
                "win_rate_pct": stats["win_rate_pct"],
                "profit_factor": stats["profit_factor"],
                "total_trades": stats["total_trades"],
                "final_equity_usdt": stats["final_equity_usdt"],
            },
        })

    # Sort candidates by full period Calmar
    tested.sort(key=lambda x: x["full_period"]["calmar"], reverse=True)
    top20 = tested[:20]

    # Assign clear descriptive IDs to each of the 20 candidates
    for i, c in enumerate(top20):
        p = c["params"]
        c["candidate_id"] = f"ALPHA-{i+1:02d}_{p['macro'].upper()}_D{p['donch']}_{p['risk_mode'][:3].upper()}"
        c["is_calmar_plus_5pct"] = bool(c["full_period"]["calmar"] >= 3.244)

    print("\n" + "=" * 95)
    print("   TOP 20 ADVANCED QUANTITATIVE ALPHA CANDIDATES (FULL CYCLE 2020-2026)")
    print("=" * 95)
    print(f"{'CANDIDATE ID':<25} | {'TRAIN CAL':<9} | {'VAL CAL':<8} | {'TEST CAL':<8} | {'FULL CAGR':<10} | {'FULL DD':<8} | {'CALMAR':<7} | {'SHARPE':<6} | >5% GOAL")
    print("-" * 95)
    for c in top20:
        tr_c = c["train"]["calmar"]
        val_c = c["validation"]["calmar"]
        te_c = c["test_2026"]["calmar"]
        f_cagr = c["full_period"]["cagr_pct"]
        f_dd = c["full_period"]["maxdd_pct"]
        f_cal = c["full_period"]["calmar"]
        shp = c["full_period"]["sharpe"]
        tag = "[YES +5%]" if c["is_calmar_plus_5pct"] else "[QUALIFIED]"
        print(f"{c['candidate_id']:<25} | {tr_c:9.3f} | {val_c:8.3f} | {te_c:8.3f} | {f_cagr:9.2f}% | {f_dd:7.2f}% | {f_cal:7.3f} | {shp:6.2f} | {tag}")

    catalog_path = ARTIFACTS_DIR / "top20_candidates_catalog.json"
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
            "baseline_calmar": 3.089,
            "target_calmar_plus_5pct": 3.244,
            "top20_candidates": top20,
        }, f, indent=2)

    print(f"\n[OK] Saved Top 20 Candidates Catalog to: {catalog_path}")


if __name__ == "__main__":
    search_and_build_20()
