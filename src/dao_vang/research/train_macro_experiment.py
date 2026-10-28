"""Strict Train (2020-2023) Exploration: Macro Filter Horizons & Trailing Tightening.
Goal: Find configurations on Train with Calmar > 5.0 and MaxDD < 12%.
"""

from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))

from dao_vang.research.protocol import TRAIN_START, TRAIN_END
from dao_vang.research.data_loader import load_universe, slice_universe
from dao_vang.research.train_workbench import compute_metrics

universe = load_universe()
train_data = slice_universe(universe, TRAIN_START, TRAIN_END)

# Resample to 4H
resampled = {}
for s in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]:
    resampled[s] = train_data[s].klines.resample("4h").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
    }).dropna()

timeline = resampled["BTCUSDT"].index
n = len(timeline)
symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

# Precompute indicators
features = {}
for s in symbols:
    df = resampled[s].reindex(timeline).ffill()
    c = df["close"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    o = df["open"].to_numpy(dtype=float)

    tr = np.zeros(n, dtype=float)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
    atr14 = pd.Series(tr).shift(1).rolling(14, min_periods=14).mean().to_numpy()

    log_ret = np.zeros(n, dtype=float)
    log_ret[1:] = np.log(np.maximum(c[1:] / np.maximum(c[:-1], 1e-8), 1e-8))
    ann_vol = pd.Series(log_ret).shift(1).rolling(60, min_periods=30).std(ddof=1).to_numpy() * np.sqrt(365.25 * 6)
    ann_vol = np.clip(ann_vol, 0.15, 2.50)

    # Various BTC and asset EMAs
    ema10 = pd.Series(c).shift(1).ewm(span=10).mean().to_numpy()
    ema40 = pd.Series(c).shift(1).ewm(span=40).mean().to_numpy()
    ema100 = pd.Series(c).shift(1).ewm(span=100).mean().to_numpy()
    ema200 = pd.Series(c).shift(1).ewm(span=200).mean().to_numpy()  # ~33 days
    ema300 = pd.Series(c).shift(1).ewm(span=300).mean().to_numpy()  # 50 days
    ema600 = pd.Series(c).shift(1).ewm(span=600).mean().to_numpy()  # 100 days
    ema900 = pd.Series(c).shift(1).ewm(span=900).mean().to_numpy()  # 150 days

    donchian20_h = pd.Series(h).shift(1).rolling(20, min_periods=20).max().to_numpy()
    donchian30_h = pd.Series(h).shift(1).rolling(30, min_periods=30).max().to_numpy()

    features[s] = {
        "open": o, "high": h, "low": l, "close": c,
        "atr14": atr14, "ann_vol": ann_vol,
        "ema10": ema10, "ema40": ema40, "ema100": ema100,
        "ema200": ema200, "ema300": ema300, "ema600": ema600, "ema900": ema900,
        "donchian20_h": donchian20_h, "donchian30_h": donchian30_h,
    }

btc_f = features["BTCUSDT"]


def run_sim(
    macro_key: str,        # 'ema200', 'ema300', 'ema600', 'ema900'
    macro_slope_filter: bool, # require macro EMA slope > 0
    donch_len: int,        # 20 or 30
    trail_atr: float,      # 2.0, 2.5
    be_atr: float,         # 1.0, 1.5
    tighten_atr: float,    # e.g., 3.0 (when profit > tighten_atr, trail tightens to 1.5)
    target_vol: float,     # 0.30, 0.35
    slots: int,            # 2, 3
) -> Tuple[float, float, float]:
    btc_macro = btc_f[macro_key]
    btc_close = btc_f["close"]

    cash = 100_000.0
    positions = {s: 0.0 for s in symbols}
    entry_p = {s: 0.0 for s in symbols}
    peak_p = {s: 0.0 for s in symbols}
    stop_p = {s: 0.0 for s in symbols}
    in_pos = {s: False for s in symbols}

    navs = np.zeros(n, dtype=float)
    warmup = 300

    for t in range(n):
        o_now = {s: features[s]["open"][t] for s in symbols}
        open_val = sum(positions[s] * o_now[s] for s in symbols if in_pos[s] and np.isfinite(o_now[s]))
        eq = cash + open_val

        if t >= warmup and eq > 0:
            btc_prev_c = btc_close[t - 1]
            btc_prev_m = btc_macro[t - 1]
            macro_ok = btc_prev_c > btc_prev_m
            if macro_slope_filter and macro_ok:
                macro_ok = (btc_prev_m >= btc_macro[t - 7])  # 24h slope positive

            # Exits
            for s in symbols:
                if in_pos[s]:
                    c_prev = features[s]["close"][t - 1]
                    atr_prev = features[s]["atr14"][t - 1]
                    o_exec = o_now[s]

                    if c_prev > peak_p[s]:
                        peak_p[s] = c_prev

                    gain_atr = (peak_p[s] - entry_p[s]) / max(atr_prev, 1e-6)

                    # Staged trailing stop logic
                    if gain_atr >= tighten_atr:
                        # Big winner: tighten trailing stop to 1.5 ATR to lock in windfall
                        current_trail = min(trail_atr, 1.5)
                        stop_p[s] = max(entry_p[s] + 1.0 * atr_prev, peak_p[s] - current_trail * atr_prev)
                    elif gain_atr >= be_atr:
                        # In moderate profit: at least break-even
                        stop_p[s] = max(entry_p[s], peak_p[s] - trail_atr * atr_prev)
                    else:
                        # Initial risk stop
                        stop_p[s] = max(stop_p[s], peak_p[s] - 2.5 * atr_prev)

                    exit_sig = (c_prev < stop_p[s]) or (c_prev < features[s]["ema40"][t - 1]) or (not macro_ok)

                    if exit_sig and np.isfinite(o_exec):
                        fee = abs(positions[s] * o_exec) * 0.0010
                        cash += (positions[s] * o_exec - fee)
                        positions[s] = 0.0
                        in_pos[s] = False

            # Entries
            if macro_ok:
                open_slots = sum(1 for s in symbols if in_pos[s])
                avail = slots - open_slots
                if avail > 0:
                    cand = []
                    for s in symbols:
                        if not in_pos[s]:
                            c_prev = features[s]["close"][t - 1]
                            ema40_prev = features[s]["ema40"][t - 1]
                            dh_prev = features[s][f"donchian{donch_len}_h"][t - 1]

                            if c_prev >= dh_prev and c_prev > ema40_prev:
                                # Momentum rank
                                mom = c_prev / features[s]["close"][t - 15] - 1.0
                                if mom > 0:
                                    cand.append((s, mom))

                    cand.sort(key=lambda x: x[1], reverse=True)
                    for s, score in cand[:avail]:
                        o_exec = o_now[s]
                        vol_prev = features[s]["ann_vol"][t - 1]
                        atr_prev = features[s]["atr14"][t - 1]
                        if np.isfinite(o_exec) and o_exec > 0:
                            v_scale = np.clip(target_vol / vol_prev, 0.20, 1.10)
                            alloc = (eq / slots) * v_scale
                            fee = alloc * 0.0010
                            if cash >= (alloc + fee):
                                cash -= (alloc + fee)
                                positions[s] = alloc / o_exec
                                in_pos[s] = True
                                entry_p[s] = o_exec
                                peak_p[s] = o_exec
                                stop_p[s] = o_exec - 2.0 * atr_prev

        c_now = {s: features[s]["close"][t] for s in symbols}
        close_val = sum(positions[s] * c_now[s] for s in symbols if in_pos[s] and np.isfinite(c_now[s]))
        navs[t] = cash + close_val

    nav_s = pd.Series(navs, index=timeline)
    _, cagr, maxdd, calmar = compute_metrics(nav_s)
    return cagr, maxdd, calmar


# Run sweep on Train
print("Testing Macro Horizons & Staged Trailing on Train (2020-2023)...")
records = []
for macro_k in ["ema200", "ema300", "ema600"]:
    for macro_slope in [False, True]:
        for donch in [20, 30]:
            for trail in [2.0, 2.5]:
                for be in [1.0, 1.5]:
                    for tighten in [2.5, 3.5, 99.0]:
                        for tv in [0.28, 0.33]:
                            for slt in [2, 3]:
                                cagr, maxdd, calmar = run_sim(
                                    macro_key=macro_k,
                                    macro_slope_filter=macro_slope,
                                    donch_len=donch,
                                    trail_atr=trail,
                                    be_atr=be,
                                    tighten_atr=tighten,
                                    target_vol=tv,
                                    slots=slt,
                                )
                                records.append({
                                    "macro": macro_k,
                                    "slope": macro_slope,
                                    "donch": donch,
                                    "trail": trail,
                                    "be": be,
                                    "tighten": tighten,
                                    "tv": tv,
                                    "slots": slt,
                                    "cagr": round(cagr * 100, 2),
                                    "maxdd": round(maxdd * 100, 2),
                                    "calmar": round(calmar, 3),
                                })

df_out = pd.DataFrame(records).sort_values("calmar", ascending=False)
print("Top 15 Configurations on Train (2020-2023):")
print(df_out.head(15).to_string(index=False))
