"""PeakPulse AI - Advanced Alpha Structures Research Engine.
Systematic empirical exploration of new quantitative alpha structures:
1. Cross-Sectional Residual Momentum (Beta-adjusted idiosyncratic momentum)
2. Volume-Confirmed Breakout (Liquidity Absorption Filter)
3. Parabolic Dynamic ATR Ratchet Trailing Stop
4. Parkinson Volatility & Regime Modulation
5. Multi-Timeframe Trend Alignment

Data: 2020-01-01 to 2026-09-29
Splits:
- Train: 2020-2023 (4 years)
- Validation: 2024-2025 (2 years)
- Test: 2026-01-01 to 2026-09-29 (9 months)
"""

from __future__ import annotations
import json
import logging
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("alpha.research")

DATA_DIR = Path("D:/SharedMarketData/multiyear_2020_2026")
KLINES_DIR = DATA_DIR / "klines_1h"
FUNDING_DIR = DATA_DIR / "funding_8h"
UNIVERSE = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "BCHUSDT", "LTCUSDT"]
INITIAL_CAPITAL = 100_000.0
COST_RATE = 0.0010  # 10 bps one way


def load_dataset() -> Tuple[Dict[str, pd.DataFrame], Dict[str, pd.Series]]:
    """Load and resample 1h klines to 4H bars, and align 8h funding rates."""
    dfs_4h = {}
    funding_series = {}

    for sym in UNIVERSE:
        # Load klines
        kf = KLINES_DIR / f"{sym}_1h.parquet"
        if not kf.exists():
            continue
        df = pd.read_parquet(kf)
        if not isinstance(df.index, pd.DatetimeIndex):
            if "open_time" in df.columns:
                df.index = pd.to_datetime(df["open_time"], unit="ms", utc=True)
            else:
                df.index = pd.to_datetime(df.index, utc=True)
        df = df[["open", "high", "low", "close", "volume"]].astype(float)
        
        # Parkinson Volatility calculation on 1h bars before 4h resample:
        # sigma_parkinson = sqrt( (ln(H/L))^2 / (4 * ln(2)) )
        df["hl_ratio"] = np.log(df["high"] / np.maximum(df["low"], 1e-8))
        df["parkinson_var"] = (df["hl_ratio"] ** 2) / (4.0 * np.log(2.0))

        # Resample to 4H
        df_4h = df.resample("4h").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "parkinson_var": "mean",
        }).dropna()
        
        df_4h["parkinson_vol"] = np.sqrt(df_4h["parkinson_var"] * 365.25 * 6)
        dfs_4h[sym] = df_4h

        # Load funding
        ff = FUNDING_DIR / f"{sym}_funding.parquet"
        if ff.exists():
            f_df = pd.read_parquet(ff)
            if not isinstance(f_df.index, pd.DatetimeIndex):
                if "funding_time" in f_df.columns:
                    f_df.index = pd.to_datetime(f_df["funding_time"], unit="ms", utc=True)
                else:
                    f_df.index = pd.to_datetime(f_df.index, utc=True)
            col = "last_funding_rate" if "last_funding_rate" in f_df.columns else "funding_rate"
            s_fund = f_df[col].astype(float)
            funding_series[sym] = s_fund

    return dfs_4h, funding_series


def compute_metrics(equity_series: pd.Series, trades: list) -> dict:
    if len(equity_series) < 2:
        return {"cagr_pct": 0.0, "maxdd_pct": 100.0, "calmar": 0.0, "sharpe": 0.0}

    start_val = equity_series.iloc[0]
    end_val = equity_series.iloc[-1]
    days = (equity_series.index[-1] - equity_series.index[0]).total_seconds() / 86400.0
    years = max(days / 365.25, 0.01)

    cagr = (math.pow(end_val / max(start_val, 1e-6), 1.0 / years) - 1.0) * 100.0

    # Drawdown
    cummax = equity_series.cummax()
    dd = (cummax - equity_series) / cummax * 100.0
    maxdd = float(dd.max()) if len(dd) > 0 else 0.0
    maxdd = max(maxdd, 1e-4)

    calmar = cagr / maxdd

    # Daily Sharpe
    eq_daily = equity_series.resample("1d").last().dropna()
    d_rets = eq_daily.pct_change().dropna()
    sharpe = float((d_rets.mean() / max(d_rets.std(), 1e-6)) * np.sqrt(365.25)) if len(d_rets) > 10 else 0.0

    wins = [t for t in trades if t["pnl"] > 0]
    win_rate = len(wins) / max(len(trades), 1) * 100.0

    gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    pf = gross_profit / max(gross_loss, 1e-6)

    return {
        "cagr_pct": round(cagr, 2),
        "maxdd_pct": round(maxdd, 2),
        "calmar": round(calmar, 3),
        "sharpe": round(sharpe, 2),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(pf, 3),
        "total_trades": len(trades),
        "final_equity": round(end_val, 2),
    }


def simulate_strategy(
    dfs: Dict[str, pd.DataFrame],
    funding: Dict[str, pd.Series],
    macro_ema_span: int = 600,
    donch_len: int = 40,
    trail_atr_mult: float = 2.5,
    be_atr_mult: float = 1.8,
    tighten_atr_mult: float = 99.0,
    target_annual_vol: float = 0.32,
    use_breadth: bool = True,
    # New Alpha Switches:
    use_residual_momentum: bool = False,
    volume_surge_mult: float = 0.0,  # e.g. 1.2 or 1.5, 0.0 to disable
    parabolic_ratchet: bool = False,
    use_parkinson_sizing: bool = False,
    max_slots: int = 2,
) -> Tuple[pd.Series, list, dict]:
    """Causal vector simulation on common 4H timestamps."""
    common_idx = dfs["BTCUSDT"].index
    for sym in UNIVERSE:
        if sym in dfs:
            common_idx = common_idx.intersection(dfs[sym].index)
    common_idx = common_idx.sort_values()

    # Precompute indicators
    btc_close = dfs["BTCUSDT"].loc[common_idx, "close"]
    btc_macro_ema = btc_close.ewm(span=macro_ema_span).mean()

    # Precompute coin indicators
    c_map = {}
    h_map = {}
    l_map = {}
    v_map = {}
    dh_map = {}
    atr_map = {}
    ann_vol_map = {}
    ema40_map = {}
    v_sma20_map = {}

    for sym in UNIVERSE:
        df = dfs[sym].loc[common_idx]
        c = df["close"]
        h = df["high"]
        l = df["low"]
        v = df["volume"]

        c_map[sym] = c.values
        h_map[sym] = h.values
        l_map[sym] = l.values
        v_map[sym] = v.values

        # Donchian High on previous bars (shift 1 for strict causality)
        dh = h.rolling(donch_len).max().shift(1).values
        dh_map[sym] = dh

        # ATR 14
        tr = np.maximum(h - l, np.maximum(np.abs(h - c.shift(1)), np.abs(l - c.shift(1))))
        atr_map[sym] = tr.rolling(14).mean().values

        # Annualized Volatility (close-to-close or parkinson)
        if use_parkinson_sizing and "parkinson_vol" in df.columns:
            ann_vol_map[sym] = df["parkinson_vol"].rolling(60).mean().clip(0.15, 2.50).values
        else:
            log_ret = np.log(np.maximum(c / np.maximum(c.shift(1), 1e-8), 1e-8))
            ann_vol_map[sym] = (log_ret.rolling(60).std() * np.sqrt(365.25 * 6)).clip(0.15, 2.50).values

        ema40_map[sym] = c.ewm(span=40).mean().values
        v_sma20_map[sym] = v.rolling(20).mean().values

    # Precompute Residual Momentum if enabled
    # Rolling regression: R_alt = alpha + beta * R_btc over 120 bars (20 days)
    res_mom_map = {}
    if use_residual_momentum:
        btc_ret = np.log(np.maximum(btc_close / np.maximum(btc_close.shift(1), 1e-8), 1e-8))
        for sym in UNIVERSE:
            if sym == "BTCUSDT":
                res_mom_map[sym] = np.zeros(len(common_idx))
                continue
            alt_c = dfs[sym].loc[common_idx, "close"]
            alt_ret = np.log(np.maximum(alt_c / np.maximum(alt_c.shift(1), 1e-8), 1e-8))
            
            rolling_cov = (alt_ret * btc_ret).rolling(120).mean() - alt_ret.rolling(120).mean() * btc_ret.rolling(120).mean()
            rolling_var_btc = btc_ret.rolling(120).var().replace(0, np.nan)
            beta = (rolling_cov / rolling_var_btc).clip(0.2, 3.0).fillna(1.0)
            
            # Idiosyncratic return: epsilon = R_alt - beta * R_btc
            epsilon = alt_ret - beta * btc_ret
            # Cumulative 15-bar residual momentum score
            res_mom = epsilon.rolling(15).sum().fillna(0.0).values
            res_mom_map[sym] = res_mom

    # Funding rate map
    fund_aligned = {}
    for sym in UNIVERSE:
        if sym in funding:
            fund_aligned[sym] = funding[sym].reindex(common_idx, method="ffill").fillna(0.0).values
        else:
            fund_aligned[sym] = np.zeros(len(common_idx))

    # Simulation loop
    n = len(common_idx)
    cash = INITIAL_CAPITAL
    equity_hist = np.zeros(n)
    trades = []
    positions = {}  # sym -> {qty, entry_price, peak_price, entry_idx}

    btc_c_arr = btc_close.values
    btc_m_arr = btc_macro_ema.values

    for t in range(60, n):
        curr_dt = common_idx[t]
        macro_bull = btc_c_arr[t] > btc_m_arr[t]

        # Market breadth factor
        breadth_factor = 1.0
        if use_breadth:
            bull_cnt = sum(1 for sym in UNIVERSE if c_map[sym][t] > ema40_map[sym][t])
            if bull_cnt < len(UNIVERSE) / 2:
                breadth_factor = 0.70

        # 1. Update mark price & check exits
        symbols_to_close = []
        for sym, pos in positions.items():
            cp = c_map[sym][t]
            atr = atr_map[sym][t]
            pos["peak_price"] = max(pos["peak_price"], cp)
            peak_p = pos["peak_price"]
            entry_p = pos["entry_price"]

            # Compute Dynamic Trailing Stop
            gain_atr = (peak_p - entry_p) / max(atr, 1e-6)

            if parabolic_ratchet:
                # Parabolic ratcheting logic
                if gain_atr >= 5.0:
                    stop_p = peak_p - 1.5 * atr  # aggressively protect monster runners
                elif gain_atr >= 3.0:
                    stop_p = max(entry_p + 1.0 * atr, peak_p - 1.8 * atr)  # lock in +1.0 ATR
                elif gain_atr >= be_atr_mult:
                    stop_p = max(entry_p + 0.2 * atr, peak_p - trail_atr_mult * atr)  # lock BE
                else:
                    stop_p = peak_p - 2.5 * atr
            else:
                if gain_atr >= tighten_atr_mult:
                    stop_p = max(entry_p + 1.5 * atr, peak_p - 1.5 * atr)
                elif gain_atr >= be_atr_mult:
                    stop_p = max(entry_p, peak_p - trail_atr_mult * atr)
                else:
                    stop_p = peak_p - 2.5 * atr

            exit_sig = (cp < stop_p) or (cp < ema40_map[sym][t]) or (not macro_bull)
            if exit_sig:
                symbols_to_close.append((sym, cp, stop_p))

        # Execute exits
        for sym, exec_p, st_p in symbols_to_close:
            pos = positions.pop(sym)
            qty = pos["qty"]
            fee = qty * exec_p * COST_RATE
            pnl = qty * (exec_p - pos["entry_price"]) - fee
            cash += (qty * exec_p - fee)
            holding_bars = t - pos["entry_idx"]
            trades.append({
                "symbol": sym,
                "entry_price": pos["entry_price"],
                "exit_price": exec_p,
                "pnl": pnl,
                "holding_bars": holding_bars,
                "exit_time": curr_dt,
            })

        # 2. Check entries if macro bull
        if macro_bull and len(positions) < max_slots:
            avail = max_slots - len(positions)
            candidates = []

            for sym in UNIVERSE:
                if sym in positions:
                    continue

                cp = c_map[sym][t]
                dh = dh_map[sym][t]
                e40 = ema40_map[sym][t]

                if cp >= dh and cp > e40:
                    # Volume confirmation check
                    if volume_surge_mult > 0.0:
                        v_curr = v_map[sym][t]
                        v_sma = v_sma20_map[sym][t]
                        if v_curr < (volume_surge_mult * v_sma):
                            continue  # skip weak volume breakout

                    # Rank score: Residual Momentum or Raw Price Momentum
                    if use_residual_momentum:
                        score = res_mom_map[sym][t]
                    else:
                        score = (cp / c_map[sym][t - 15] - 1.0) if t >= 15 else 0.0

                    if score > 0:
                        candidates.append((sym, score, cp))

            candidates.sort(key=lambda x: x[1], reverse=True)

            # Mark total equity for sizing
            pos_val = sum(pos["qty"] * c_map[sym][t] for sym, pos in positions.items())
            curr_equity = cash + pos_val

            for sym, score, exec_p in candidates[:avail]:
                ann_vol = ann_vol_map[sym][t]
                v_scale = np.clip(target_annual_vol / ann_vol, 0.20, 1.10)
                alloc = (curr_equity / max_slots) * v_scale * breadth_factor
                fee = alloc * COST_RATE

                if cash >= (alloc + fee):
                    qty = alloc / exec_p
                    cash -= (alloc + fee)
                    positions[sym] = {
                        "qty": qty,
                        "entry_price": exec_p,
                        "peak_price": exec_p,
                        "entry_idx": t,
                    }

        # 3. Apply funding rate deduction (every 8h: at 00:00, 08:00, 16:00 UTC)
        if curr_dt.hour in [0, 8, 16]:
            for sym, pos in positions.items():
                fr = fund_aligned[sym][t]
                funding_cost = pos["qty"] * c_map[sym][t] * fr
                cash -= funding_cost

        # Calculate equity at bar end
        pos_val = sum(pos["qty"] * c_map[sym][t] for sym, pos in positions.items())
        equity_hist[t] = cash + pos_val

    # Fill warmup bars
    equity_hist[:60] = INITIAL_CAPITAL
    equity_series = pd.Series(equity_hist, index=common_idx)

    # Slice splits
    train_mask = (common_idx >= "2020-01-01") & (common_idx <= "2023-12-31")
    val_mask = (common_idx >= "2024-01-01") & (common_idx <= "2025-12-31")
    test_mask = (common_idx >= "2026-01-01")

    train_eq = equity_series.loc[train_mask]
    val_eq = equity_series.loc[val_mask]
    test_eq = equity_series.loc[test_mask]

    train_trades = [t for t in trades if t["exit_time"] <= pd.Timestamp("2023-12-31 23:59:59", tz="UTC")]
    val_trades = [t for t in trades if pd.Timestamp("2024-01-01", tz="UTC") <= t["exit_time"] <= pd.Timestamp("2025-12-31 23:59:59", tz="UTC")]
    test_trades = [t for t in trades if t["exit_time"] >= pd.Timestamp("2026-01-01", tz="UTC")]

    metrics = {
        "train": compute_metrics(train_eq, train_trades),
        "val": compute_metrics(val_eq, val_trades),
        "test": compute_metrics(test_eq, test_trades),
        "full": compute_metrics(equity_series, trades),
    }

    return equity_series, trades, metrics


def main():
    logger.info("Loading 2020-2026 multiyear data...")
    dfs_4h, funding_series = load_dataset()
    logger.info(f"Loaded {len(dfs_4h)} symbols with {len(dfs_4h['BTCUSDT'])} bars each.")

    experiments = [
        # Baseline Champion
        {
            "name": "BASE_ALPHA01_D40_BE1.8",
            "desc": "Baseline Champion (Donch 40, EMA600, BE 1.8)",
            "params": dict(macro_ema_span=600, donch_len=40, be_atr_mult=1.8, target_annual_vol=0.32),
        },
        # Experiment 1: Residual Momentum
        {
            "name": "EXP1_RESIDUAL_MOMENTUM_D40",
            "desc": "Idiosyncratic Residual Momentum against BTC Beta",
            "params": dict(macro_ema_span=600, donch_len=40, be_atr_mult=1.8, target_annual_vol=0.32, use_residual_momentum=True),
        },
        # Experiment 2: Volume Surge Filter 1.2x
        {
            "name": "EXP2_VOLUME_SURGE_1.2X",
            "desc": "Breakout confirmed by Volume > 1.2x 20SMA",
            "params": dict(macro_ema_span=600, donch_len=40, be_atr_mult=1.8, target_annual_vol=0.32, volume_surge_mult=1.2),
        },
        # Experiment 3: Volume Surge Filter 1.5x
        {
            "name": "EXP3_VOLUME_SURGE_1.5X",
            "desc": "Breakout confirmed by Volume > 1.5x 20SMA",
            "params": dict(macro_ema_span=600, donch_len=40, be_atr_mult=1.8, target_annual_vol=0.32, volume_surge_mult=1.5),
        },
        # Experiment 4: Parabolic Ratchet Trailing
        {
            "name": "EXP4_PARABOLIC_RATCHET",
            "desc": "Dynamic Parabolic Ratchet Trailing Stop (staged protection)",
            "params": dict(macro_ema_span=600, donch_len=40, be_atr_mult=1.8, target_annual_vol=0.32, parabolic_ratchet=True),
        },
        # Experiment 5: Parkinson Volatility Sizing
        {
            "name": "EXP5_PARKINSON_VOL_SIZING",
            "desc": "Intra-bar High-Low Parkinson Volatility Sizing",
            "params": dict(macro_ema_span=600, donch_len=40, be_atr_mult=1.8, target_annual_vol=0.32, use_parkinson_sizing=True),
        },
        # Experiment 6: Combo Synergy (Residual Mom + Parabolic Ratchet)
        {
            "name": "EXP6_SYNERGY_RESMOM_RATCHET",
            "desc": "Synergy: Residual Momentum + Parabolic Ratchet",
            "params": dict(macro_ema_span=600, donch_len=40, be_atr_mult=1.8, target_annual_vol=0.32, use_residual_momentum=True, parabolic_ratchet=True),
        },
        # Experiment 7: Combo Synergy (Residual Mom + Volume 1.2x + Parabolic Ratchet)
        {
            "name": "EXP7_SUPER_SYNERGY_ALL",
            "desc": "Super Synergy: Residual Momentum + Vol Surge 1.2x + Parabolic Ratchet",
            "params": dict(macro_ema_span=600, donch_len=40, be_atr_mult=1.8, target_annual_vol=0.32, use_residual_momentum=True, volume_surge_mult=1.2, parabolic_ratchet=True),
        },
        # Experiment 8: Volatility Target Tuning with Ratchet (TV 0.35)
        {
            "name": "EXP8_TV035_RATCHET",
            "desc": "Vol Target 0.35 + Parabolic Ratchet",
            "params": dict(macro_ema_span=600, donch_len=40, be_atr_mult=1.8, target_annual_vol=0.35, parabolic_ratchet=True),
        },
        # Experiment 9: Volatility Target Tuning with Ratchet (TV 0.28 - Super Conservative)
        {
            "name": "EXP9_TV028_SUPER_CONSERVATIVE",
            "desc": "Vol Target 0.28 + Parabolic Ratchet (Ultra low MaxDD)",
            "params": dict(macro_ema_span=600, donch_len=40, be_atr_mult=1.8, target_annual_vol=0.28, parabolic_ratchet=True),
        },
    ]

    results = []
    print("\n" + "=" * 115)
    print(f"{'EXPERIMENT':<28} | {'TRAIN CALMAR':<12} | {'VAL CALMAR':<10} | {'TEST 2026':<10} | {'FULL CAGR':<10} | {'FULL MAXDD':<10} | {'FULL CALMAR':<11} | {'PF':<5}")
    print("=" * 115)

    for exp in experiments:
        name = exp["name"]
        params = exp["params"]
        eq, trades, m = simulate_strategy(dfs_4h, funding_series, **params)

        train_c = m["train"]["calmar"]
        val_c = m["val"]["calmar"]
        test_c = m["test"]["cagr_pct"]
        full_cagr = m["full"]["cagr_pct"]
        full_mdd = m["full"]["maxdd_pct"]
        full_c = m["full"]["calmar"]
        full_pf = m["full"]["profit_factor"]

        print(f"{name:<28} | {train_c:<12.3f} | {val_c:<10.3f} | {test_c:>+7.2f}%   | {full_cagr:>7.2f}%   | {full_mdd:>7.2f}%   | {full_c:<11.3f} | {full_pf:<5.2f}")

        results.append({
            "name": name,
            "desc": exp["desc"],
            "params": params,
            "metrics": m,
        })

    print("=" * 115)

    # Save artifact
    out_file = Path("artifacts/walkforward_2020_2026/alpha_expansions_results.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Results saved to {out_file}")


if __name__ == "__main__":
    main()
