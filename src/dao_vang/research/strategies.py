"""Strategy generator and signal computation for multi-asset crypto portfolios."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from dao_vang.research.data_loader import AssetMarketData


def compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 24) -> np.ndarray:
    n = len(close)
    tr = np.zeros(n, dtype=float)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )
    atr = np.zeros(n, dtype=float)
    if n >= period:
        atr[period - 1] = np.mean(tr[:period])
        alpha = 1.0 / period
        for i in range(period, n):
            atr[i] = atr[i - 1] * (1.0 - alpha) + tr[i] * alpha
    return atr


def compute_ema(series: np.ndarray, span: int) -> np.ndarray:
    alpha = 2.0 / (span + 1.0)
    ema = np.zeros_like(series, dtype=float)
    ema[0] = series[0]
    for i in range(1, len(series)):
        ema[i] = ema[i - 1] * (1.0 - alpha) + series[i] * alpha
    return ema


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    family: str
    ema_fast: int
    ema_slow: int
    atr_period: int
    atr_mult_stop: float
    vol_lookback: int
    target_annual_vol: float
    max_weight_per_asset: float
    use_macro_filter: bool
    mode: str  # 'long_cash' or 'long_short'


def generate_weights_for_strategy(
    universe_data: Dict[str, AssetMarketData],
    spec: StrategySpec,
    timeline: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Generate causal target weights dataframe strictly using close prices at bar t."""
    symbols = list(universe_data.keys())
    n_steps = len(timeline)
    weights_matrix = np.zeros((n_steps, len(symbols)), dtype=float)

    # 1. Macro trend series (using BTCUSDT)
    btc_close = universe_data["BTCUSDT"].klines["close"].reindex(timeline).ffill().bfill().to_numpy(dtype=float)
    btc_macro_ema = compute_ema(btc_close, span=spec.ema_slow)
    macro_bull = btc_close >= btc_macro_ema

    # 2. Compute signals for each symbol
    for col_idx, s in enumerate(symbols):
        kline = universe_data[s].klines.reindex(timeline).ffill()
        c = kline["close"].to_numpy(dtype=float)
        h = kline["high"].to_numpy(dtype=float)
        l = kline["low"].to_numpy(dtype=float)

        ema_fast_arr = compute_ema(c, span=spec.ema_fast)
        ema_slow_arr = compute_ema(c, span=spec.ema_slow)
        atr_arr = compute_atr(h, l, c, period=spec.atr_period)

        # Realized annual volatility
        log_ret = np.zeros_like(c)
        log_ret[1:] = np.log(np.maximum(c[1:], 1e-8) / np.maximum(c[:-1], 1e-8))
        # Rolling std of returns
        vol_arr = np.zeros_like(c)
        for i in range(spec.vol_lookback, n_steps):
            window = log_ret[i - spec.vol_lookback + 1 : i + 1]
            vol_arr[i] = np.std(window, ddof=1) * np.sqrt(365.25 * 24)  # Annualized 1h

        vol_arr = np.maximum(vol_arr, 0.15)  # floor at 15% annual vol

        # State tracking for Chandelier exit
        in_pos = 0  # +1 for long, -1 for short, 0 for flat
        peak_price = 0.0
        trough_price = 1e9

        for t in range(max(spec.ema_slow, spec.vol_lookback), n_steps):
            price = c[t]
            atr = atr_arr[t]
            vol = vol_arr[t]

            # Volatility sizing scalar
            raw_scale = spec.target_annual_vol / vol
            unit_weight = min(spec.max_weight_per_asset, raw_scale * spec.max_weight_per_asset)

            macro_ok = macro_bull[t] if spec.use_macro_filter else True

            # Check trailing exit if in position
            if in_pos == 1:
                peak_price = max(peak_price, price)
                trailing_stop = peak_price - spec.atr_mult_stop * atr
                if price < trailing_stop or price < ema_slow_arr[t]:
                    in_pos = 0

            elif in_pos == -1:
                trough_price = min(trough_price, price)
                trailing_stop = trough_price + spec.atr_mult_stop * atr
                if price > trailing_stop or price > ema_slow_arr[t]:
                    in_pos = 0

            # Check entry if flat
            if in_pos == 0:
                # Long entry condition
                if price > ema_fast_arr[t] and ema_fast_arr[t] > ema_slow_arr[t] and macro_ok:
                    in_pos = 1
                    peak_price = price
                elif spec.mode == "long_short" and price < ema_fast_arr[t] and ema_fast_arr[t] < ema_slow_arr[t] and not macro_ok:
                    in_pos = -1
                    trough_price = price

            # Assign weight
            if in_pos == 1:
                weights_matrix[t, col_idx] = unit_weight
            elif in_pos == -1:
                weights_matrix[t, col_idx] = -unit_weight * 0.5  # Asymmetric smaller short sizing
            else:
                weights_matrix[t, col_idx] = 0.0

    return pd.DataFrame(weights_matrix, index=timeline, columns=symbols)
