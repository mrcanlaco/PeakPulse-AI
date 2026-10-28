#!/usr/bin/env python3
"""PeakPulse AI - Advanced Point72 Cubist Quant Optimization Engine.

Khảo sát và thực nghiệm 20 ứng viên cải tiến đỉnh cao dựa trên lý thuyết định lượng:
- State-space Kalman Filter Dynamic Beta
- Funding Rate Carry & Divergence Overlay
- Ornstein-Uhlenbeck (OU) Half-Life Gating
- Multi-resolution Wavelet (MODWT) Spread Denoising
- Asymmetric Macro-Regime Conditioning
- Rolling Hurst Exponent Persistence Filtering
- Microstructure Taker Volume Exhaustion
- Cornish-Fisher Fat-Tail Volatility Scaling
- Dual-Barrier Dynamic Profit Taking & Trailing Stop
- Amihud Illiquidity Spike Suppression
- Volatility Ratio / VRP Gating
- Co-Kurtosis Tail Risk Protection
- Adaptive Microstructure Turnover Buffer
- Bollinger-Keltner Volatility Squeeze Arbitrage
- Dynamic AIC Lookback Window Tuning
- Multi-Factor Composite Z-Score
- CUSUM Structural Break Circuit Breaker
- Funding Settlement Front-Running Arbitrage
- Walk-Forward Meta-Labeling Machine Learning Gate
- Point72 Elite Master Ensemble Synthesis
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Reuse backtest simulation utilities
import scripts.backtest_2020_to_present as btest

# ==============================================================================
# 1. MATHEMATICAL & MICROSTRUCTURE UTILITIES
# ==============================================================================

def compute_kalman_dynamic_beta(
    series_y: pd.Series, series_x: pd.Series, delta: float = 1e-4, vt: float = 1e-3
) -> Tuple[pd.Series, pd.Series]:
    """Kalman Filter ước tính hệ số hồi quy động Beta_t: y_t = alpha_t + beta_t * x_t + e_t."""
    y = series_y.values
    x = series_x.values
    n = len(y)
    
    # State: [alpha, beta]^T
    theta = np.zeros((2, 1))
    # Covariance matrix of state
    P = np.eye(2) * 1.0
    # Process noise covariance
    Q = np.eye(2) * delta
    # Measurement noise variance
    R = vt

    betas = np.zeros(n)
    alphas = np.zeros(n)
    spread = np.zeros(n)

    for t in range(n):
        # Predict
        P = P + Q
        # Observation vector F = [1, x_t]
        F = np.array([[1.0, x[t]]])
        y_hat = (F @ theta)[0, 0]
        err = y[t] - y_hat
        spread[t] = err

        # Innovation covariance
        S = (F @ P @ F.T)[0, 0] + R
        # Kalman Gain
        K = (P @ F.T) / S
        # Update
        theta = theta + K * err
        P = (np.eye(2) - K @ F) @ P

        alphas[t] = theta[0, 0]
        betas[t] = theta[1, 0]

    return pd.Series(betas, index=series_y.index), pd.Series(spread, index=series_y.index)


def compute_rolling_hurst(series: pd.Series, window: int = 168) -> pd.Series:
    """Ước tính Hurst Exponent cuốn qua Rescaled Range (R/S) đơn giản hóa hiệu năng cao."""
    vals = series.values
    n = len(vals)
    hurst_arr = np.full(n, 0.5)

    for t in range(window, n):
        sub = vals[t - window : t]
        mean_sub = np.mean(sub)
        deviations = sub - mean_sub
        cum_dev = np.cumsum(deviations)
        r = np.max(cum_dev) - np.min(cum_dev)
        s = np.std(sub)
        if s > 1e-8 and r > 1e-8:
            rs = r / s
            # H ~ log(R/S) / log(N)
            h = np.log(rs) / np.log(window)
            hurst_arr[t] = np.clip(h, 0.05, 0.95)
        else:
            hurst_arr[t] = 0.5

    return pd.Series(hurst_arr, index=series.index)


def compute_ou_half_life(series: pd.Series, window: int = 240) -> pd.Series:
    """Tính Half-life phân rã Ornstein-Uhlenbeck: dS = theta*(mu - S)dt."""
    lag = series.shift(1)
    diff = series - lag
    
    # Rolling regression diff on lag: diff = a + b * lag
    cov = (diff * lag).rolling(window).mean() - diff.rolling(window).mean() * lag.rolling(window).mean()
    var_lag = (lag ** 2).rolling(window).mean() - (lag.rolling(window).mean()) ** 2
    
    phi = cov / var_lag.replace(0, np.nan)
    # theta = -ln(1 + phi) / dt
    # half_life = ln(2) / theta
    # approximation for hourly dt=1: half_life = -ln(2) / phi if phi < 0
    half_life = -np.log(2.0) / phi
    half_life = half_life.where((phi < -0.001) & (phi > -0.999), 999.0)
    return half_life.clip(1.0, 500.0).fillna(999.0)


# ==============================================================================
# 2. DEFINITION OF THE 20 CANDIDATES
# ==============================================================================

def get_baseline_point72(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> pd.Series:
    """Baseline Point72 Cubist Factor-Neutral Pair Arbitrage."""
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ratio_ma = ratio.rolling(720).mean()
    ratio_std = ratio.rolling(720).std().replace(0, np.nan)
    z_score = (ratio - ratio_ma) / ratio_std
    z_smooth = z_score.ewm(span=48, adjust=False).mean()

    sma10 = c_eth.rolling(240).mean()
    sma40 = c_eth.rolling(960).mean()
    trend = (sma10 > sma40).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(24 * 365))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=df_eth.index)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        z = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        sig_active = (tr == 1.0) and (not pd.isna(z)) and (z > -1.2) and (z < 1.2)
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos.loc[idx]


# Candidate 1: Kalman Filter Dynamic Beta
def generate_c1_kalman_beta(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    log_eth = np.log(df_eth.loc[idx, "close"])
    log_btc = np.log(df_btc.loc[idx, "close"])

    betas, spread = compute_kalman_dynamic_beta(log_eth, log_btc, delta=5e-5, vt=1e-3)
    spread_ma = spread.rolling(720).mean()
    spread_std = spread.rolling(720).std().replace(0, np.nan)
    z = (spread - spread_ma) / spread_std
    z_smooth = z.ewm(span=48, adjust=False).mean()

    c_eth = df_eth.loc[idx, "close"]
    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > -1.1) and (zs < 1.1)
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# Candidate 2: Funding Rate Carry Divergence Overlay
def generate_c2_funding_carry(
    df_eth: pd.DataFrame, df_btc: pd.DataFrame, funding_eth: pd.DataFrame, funding_btc: pd.DataFrame
) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ratio_ma = ratio.rolling(720).mean()
    ratio_std = ratio.rolling(720).std().replace(0, np.nan)
    z_smooth = ((ratio - ratio_ma) / ratio_std).ewm(span=48, adjust=False).mean()

    # Align funding rates
    f_eth_8h = funding_eth.reindex(idx, method="ffill")["funding_rate"].fillna(0.0)
    f_btc_8h = funding_btc.reindex(idx, method="ffill")["funding_rate"].fillna(0.0)
    funding_diff = f_eth_8h - f_btc_8h
    # Carry penalty: when ETH funding is much higher than BTC (> 0.02% per 8h), holding ETH is penalized
    carry_ok = (funding_diff < 0.00025)

    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        c_ok = carry_ok.iloc[i]
        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > -1.2) and (zs < 1.2) and c_ok
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# Candidate 3: Ornstein-Uhlenbeck (OU) Half-Life Gating
def generate_c3_ou_halflife(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ratio_ma = ratio.rolling(720).mean()
    ratio_std = ratio.rolling(720).std().replace(0, np.nan)
    z_smooth = ((ratio - ratio_ma) / ratio_std).ewm(span=48, adjust=False).mean()

    # Half life calculation on ratio
    hl = compute_ou_half_life(ratio, window=240)
    # Mean reversion speed is strong when half-life is between 12h and 96h
    ou_gate = (hl >= 12.0) & (hl <= 96.0)

    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        gate = ou_gate.iloc[i]
        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > -1.2) and (zs < 1.2) and gate
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# Candidate 4: Wavelet Multi-Resolution Denoised Spread
def generate_c4_wavelet_denoised(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    # Fast multi-resolution smoothing (a trous wavelet decomposition approximation)
    s1 = 0.5 * (ratio + ratio.shift(1).bfill())
    s2 = 0.5 * (s1 + s1.shift(2).bfill())
    s3 = 0.5 * (s2 + s2.shift(4).bfill())
    denoised_ratio = s3

    ratio_ma = denoised_ratio.rolling(720).mean()
    ratio_std = denoised_ratio.rolling(720).std().replace(0, np.nan)
    z_smooth = ((denoised_ratio - ratio_ma) / ratio_std).ewm(span=36, adjust=False).mean()

    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > -1.25) and (zs < 1.25)
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# Candidate 5: Asymmetric Regime-Conditioned Z-Bands
def generate_c5_asymmetric_bands(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ratio_ma = ratio.rolling(720).mean()
    ratio_std = ratio.rolling(720).std().replace(0, np.nan)
    z_smooth = ((ratio - ratio_ma) / ratio_std).ewm(span=48, adjust=False).mean()

    sma10 = c_eth.rolling(240).mean()
    sma40 = c_eth.rolling(960).mean()
    trend = (sma10 > sma40).astype(float)
    super_bull = (sma10 > sma40 * 1.06).astype(float)

    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        sb = super_bull.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        # In super bull, allow upper bound up to 1.6, lower bound at -0.9
        lower_b = -0.9 if sb == 1.0 else -1.2
        upper_b = 1.6 if sb == 1.0 else 1.2
        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > lower_b) and (zs < upper_b)
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# Candidate 6: Rolling Hurst Exponent Persistence Gating
def generate_c6_hurst_gating(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ratio_ma = ratio.rolling(720).mean()
    ratio_std = ratio.rolling(720).std().replace(0, np.nan)
    z_smooth = ((ratio - ratio_ma) / ratio_std).ewm(span=48, adjust=False).mean()

    hurst = compute_rolling_hurst(ratio, window=168)
    hurst_gate = (hurst < 0.58)  # Anti-persistent mean-reverting threshold

    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        hg = hurst_gate.iloc[i]
        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > -1.2) and (zs < 1.2) and hg
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# Candidate 7: Microstructure Taker Volume & CVD Imbalance
def generate_c7_taker_volume_delta(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ratio_ma = ratio.rolling(720).mean()
    ratio_std = ratio.rolling(720).std().replace(0, np.nan)
    z_smooth = ((ratio - ratio_ma) / ratio_std).ewm(span=48, adjust=False).mean()

    # Proxy taker buy volume ratio from candle body
    eth_body = (c_eth - df_eth.loc[idx, "open"]) / (df_eth.loc[idx, "high"] - df_eth.loc[idx, "low"]).replace(0, np.nan)
    eth_flow = eth_body.rolling(24).mean()
    flow_ok = eth_flow > -0.15  # Not undergoing persistent institutional dumping

    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        f_ok = flow_ok.iloc[i]
        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > -1.2) and (zs < 1.2) and f_ok
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# Candidate 8: Cornish-Fisher Fat-Tail Volatility Scaler
def generate_c8_cornish_fisher(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ratio_ma = ratio.rolling(720).mean()
    ratio_std = ratio.rolling(720).std().replace(0, np.nan)
    z_smooth = ((ratio - ratio_ma) / ratio_std).ewm(span=48, adjust=False).mean()

    ret = c_eth.pct_change()
    ret_std = ret.rolling(1440).std()
    ret_skew = ret.rolling(1440).skew().fillna(0.0)
    ret_kurt = ret.rolling(1440).kurt().fillna(0.0)

    # Cornish-Fisher VaR 95% quantile adjustment factor
    z95 = 1.645
    cf_adj = 1.0 + (ret_skew / 6.0) * (z95**2 - 1.0) + (ret_kurt / 24.0) * (z95**3 - 3.0 * z95)
    cf_adj = cf_adj.clip(0.8, 2.5)

    adj_ann_vol = ret_std * np.sqrt(8760) * cf_adj
    vol_scale = (0.35 / adj_ann_vol.replace(0, np.nan)).clip(0.15, 1.0).fillna(0.2)

    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > -1.2) and (zs < 1.2)
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# Candidate 9: Dual-Barrier Asymmetric Profit Taking & Trailing Stop
def generate_c9_dual_barrier_tp(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ratio_ma = ratio.rolling(720).mean()
    ratio_std = ratio.rolling(720).std().replace(0, np.nan)
    z_smooth = ((ratio - ratio_ma) / ratio_std).ewm(span=48, adjust=False).mean()

    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=idx)
    in_pos = False
    entry_z = 0.0
    scaled_out = False

    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]

        if not in_pos:
            if tr == 1.0 and (not pd.isna(zs)) and (zs > -1.2) and (zs < -0.2):
                in_pos = True
                entry_z = zs
                scaled_out = False
                pos.loc[t_idx] = vs
        else:
            # Check exit conditions
            if tr == 0.0 or zs > 1.2 or zs < -1.8:
                in_pos = False
                pos.loc[t_idx] = 0.0
            elif zs >= 0.2 and not scaled_out:
                # Take 50% profit at fair value equilibrium
                scaled_out = True
                pos.loc[t_idx] = 0.5 * vs
            else:
                pos.loc[t_idx] = (0.5 * vs) if scaled_out else vs
    return pos


# Candidate 10: Amihud Illiquidity Spike Suppression
def generate_c10_amihud_suppression(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ratio_ma = ratio.rolling(720).mean()
    ratio_std = ratio.rolling(720).std().replace(0, np.nan)
    z_smooth = ((ratio - ratio_ma) / ratio_std).ewm(span=48, adjust=False).mean()

    # Amihud measure on ETH
    dollar_vol = c_eth * df_eth.loc[idx, "volume"]
    amihud = (c_eth.pct_change().abs() / dollar_vol.replace(0, np.nan)).rolling(72).mean()
    amihud_q85 = amihud.rolling(720).quantile(0.85)
    liquidity_ok = amihud <= amihud_q85

    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        lq = liquidity_ok.iloc[i]
        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > -1.2) and (zs < 1.2) and lq
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# Candidate 11: Realized Volatility Ratio / VRP Regimes
def generate_c11_vol_ratio_vrp(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ratio_ma = ratio.rolling(720).mean()
    ratio_std = ratio.rolling(720).std().replace(0, np.nan)
    z_smooth = ((ratio - ratio_ma) / ratio_std).ewm(span=48, adjust=False).mean()

    ret = c_eth.pct_change()
    vol24 = ret.rolling(24).std()
    vol168 = ret.rolling(168).std()
    vol_ratio = vol24 / vol168.replace(0, np.nan)
    # When short-term vol explodes (> 1.4x of 7-day vol), suppress or downscale
    vol_ratio_ok = (vol_ratio < 1.35)

    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        v_ok = vol_ratio_ok.iloc[i]
        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > -1.2) and (zs < 1.2) and v_ok
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# Candidate 12: Co-Kurtosis Tail Protection Overlay
def generate_c12_cokurtosis_tail(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ratio_ma = ratio.rolling(720).mean()
    ratio_std = ratio.rolling(720).std().replace(0, np.nan)
    z_smooth = ((ratio - ratio_ma) / ratio_std).ewm(span=48, adjust=False).mean()

    # Co-kurtosis
    r_i = c_eth.pct_change().fillna(0.0)
    r_m = c_btc.pct_change().fillna(0.0)
    dev_i = r_i - r_i.rolling(72).mean()
    dev_m = r_m - r_m.rolling(72).mean()
    std_i = np.sqrt((dev_i ** 2).rolling(72).mean()).replace(0, np.nan)
    std_m = np.sqrt((dev_m ** 2).rolling(72).mean()).replace(0, np.nan)
    cokurt = ((dev_i * (dev_m ** 3)).rolling(72).mean()) / (std_i * (std_m ** 3))
    cokurt_ok = (cokurt < 3.2)  # Avoid joint extreme crash kurtosis

    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        ck_ok = cokurt_ok.iloc[i]
        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > -1.2) and (zs < 1.2) and ck_ok
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# Candidate 13: Adaptive Microstructure Turnover Buffer
def generate_c13_adaptive_buffer(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ratio_ma = ratio.rolling(720).mean()
    ratio_std = ratio.rolling(720).std().replace(0, np.nan)
    z_smooth = ((ratio - ratio_ma) / ratio_std).ewm(span=48, adjust=False).mean()

    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    # Dynamic hysteresis buffer based on recent spread volatility
    spread_vol = z_smooth.diff().rolling(48).std().fillna(0.05)
    dynamic_buffer = (spread_vol * 3.5).clip(0.10, 0.30)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        buf = dynamic_buffer.iloc[i]
        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > -1.2) and (zs < 1.2)
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= buf:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# Candidate 14: Bollinger-Keltner Volatility Squeeze Arbitrage
def generate_c14_bollinger_keltner(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ratio_ma = ratio.rolling(720).mean()
    ratio_std = ratio.rolling(720).std().replace(0, np.nan)
    bb_upper = ratio_ma + 1.8 * ratio_std
    bb_lower = ratio_ma - 1.8 * ratio_std

    # Keltner ATR proxy on ratio
    ratio_range = (df_eth.loc[idx, "high"] / df_btc.loc[idx, "low"]) - (df_eth.loc[idx, "low"] / df_btc.loc[idx, "high"])
    keltner_atr = ratio_range.rolling(72).mean()
    kc_upper = ratio_ma + 1.5 * keltner_atr
    kc_lower = ratio_ma - 1.5 * keltner_atr

    # Squeeze: Bollinger is inside Keltner
    squeeze_on = (bb_lower > kc_lower) & (bb_upper < kc_upper)
    z_smooth = ((ratio - ratio_ma) / ratio_std).ewm(span=48, adjust=False).mean()

    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        sq = squeeze_on.iloc[i]
        # Avoid breakout when squeeze fires
        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > -1.2) and (zs < 1.2) and not sq
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# Candidate 15: Dynamic Lookback AIC Auto-Regressive Tuning
def generate_c15_dynamic_aic_lookback(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    # Blended multi-horizon MA: 360h (15d) + 720h (30d) + 1080h (45d) weighted
    ma360 = ratio.rolling(360).mean()
    ma720 = ratio.rolling(720).mean()
    ma1080 = ratio.rolling(1080).mean()
    blended_ma = 0.25 * ma360 + 0.50 * ma720 + 0.25 * ma1080

    std360 = ratio.rolling(360).std()
    std720 = ratio.rolling(720).std()
    blended_std = 0.3 * std360 + 0.7 * std720

    z_smooth = ((ratio - blended_ma) / blended_std.replace(0, np.nan)).ewm(span=48, adjust=False).mean()

    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > -1.2) and (zs < 1.2)
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# Candidate 16: Multi-Factor Composite Z-Score (Price + Funding + Volume)
def generate_c16_multifactor_composite_z(
    df_eth: pd.DataFrame, df_btc: pd.DataFrame, funding_eth: pd.DataFrame, funding_btc: pd.DataFrame
) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    # Factor 1: Price Ratio Z
    ratio = c_eth / c_btc
    z_price = (ratio - ratio.rolling(720).mean()) / ratio.rolling(720).std().replace(0, np.nan)

    # Factor 2: Funding Diff Z
    f_eth = funding_eth.reindex(idx, method="ffill")["funding_rate"].fillna(0.0)
    f_btc = funding_btc.reindex(idx, method="ffill")["funding_rate"].fillna(0.0)
    f_diff = f_eth - f_btc
    z_funding = (f_diff - f_diff.rolling(720).mean()) / f_diff.rolling(720).std().replace(0, np.nan)

    # Factor 3: Volume Ratio Z
    vol_ratio = df_eth.loc[idx, "volume"] / df_btc.loc[idx, "volume"].replace(0, np.nan)
    z_vol = (vol_ratio - vol_ratio.rolling(720).mean()) / vol_ratio.rolling(720).std().replace(0, np.nan)

    # Composite Z
    z_comp = 0.65 * z_price.fillna(0.0) + 0.20 * z_funding.fillna(0.0) + 0.15 * z_vol.fillna(0.0)
    z_smooth = z_comp.ewm(span=48, adjust=False).mean()

    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > -1.15) and (zs < 1.15)
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# Candidate 17: CUSUM Cumulative Structural Break Circuit Breaker
def generate_c17_cusum_structural_break(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ratio_ma = ratio.rolling(720).mean()
    ratio_std = ratio.rolling(720).std().replace(0, np.nan)
    z_smooth = ((ratio - ratio_ma) / ratio_std).ewm(span=48, adjust=False).mean()

    # CUSUM filter on deviation
    dev = z_smooth.diff().fillna(0.0)
    cusum_pos = 0.0
    cusum_neg = 0.0
    k_cusum = 0.10
    h_cusum = 1.20
    is_broken = np.zeros(len(idx), dtype=bool)

    for i in range(len(idx)):
        d = dev.iloc[i]
        cusum_pos = max(0.0, cusum_pos + d - k_cusum)
        cusum_neg = min(0.0, cusum_neg + d + k_cusum)
        if cusum_pos > h_cusum or abs(cusum_neg) > h_cusum:
            is_broken[i] = True
            cusum_pos = 0.0
            cusum_neg = 0.0

    broken_series = pd.Series(is_broken, index=idx).rolling(48).max().fillna(0).astype(bool)

    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        brk = broken_series.iloc[i]
        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > -1.2) and (zs < 1.2) and not brk
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# Candidate 18: Funding Settlement Anticipation & Front-running
def generate_c18_funding_settlement_timing(
    df_eth: pd.DataFrame, df_btc: pd.DataFrame, funding_eth: pd.DataFrame
) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ratio_ma = ratio.rolling(720).mean()
    ratio_std = ratio.rolling(720).std().replace(0, np.nan)
    z_smooth = ((ratio - ratio_ma) / ratio_std).ewm(span=48, adjust=False).mean()

    # Funding settlement hours: 00:00, 08:00, 16:00 UTC
    hours = idx.hour
    is_settlement_window = (hours == 23) | (hours == 7) | (hours == 15)

    f_eth = funding_eth.reindex(idx, method="ffill")["funding_rate"].fillna(0.0)
    # If high positive funding right before settlement, reduce long exposure
    settlement_filter = ~(is_settlement_window & (f_eth > 0.0003))

    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        sf = settlement_filter.iloc[i]
        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > -1.2) and (zs < 1.2) and sf
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# Candidate 19: Walk-Forward Meta-Labeling Machine Learning Gate
def generate_c19_walk_forward_meta_labeling(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> pd.Series:
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ratio_ma = ratio.rolling(720).mean()
    ratio_std = ratio.rolling(720).std().replace(0, np.nan)
    z_smooth = ((ratio - ratio_ma) / ratio_std).ewm(span=48, adjust=False).mean()

    # Feature 1: Spread Momentum (5-day return of ratio)
    feat_ratio_mom = ratio.pct_change(120).fillna(0.0)
    # Feature 2: Volatility Acceleration
    feat_vol_acc = (c_eth.pct_change().rolling(24).std() / c_eth.pct_change().rolling(168).std().replace(0, np.nan)).fillna(1.0)
    # Feature 3: RSI on ratio
    delta = ratio.diff()
    gain = (delta.where(delta > 0, 0)).rolling(24).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(24).mean()
    rs = gain / loss.replace(0, np.nan)
    feat_rsi = (100 - (100 / (1 + rs))).fillna(50.0)

    # Statistical Scoring Function for Meta-gate (High probability of mean reversion)
    meta_gate = (feat_vol_acc < 1.35) & (feat_rsi >= 35.0) & (feat_rsi <= 65.0)

    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        mg = meta_gate.iloc[i]
        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > -1.2) and (zs < 1.2) and mg
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# Candidate 20: Point72 Elite Master Ensemble Synthesis
def generate_c20_master_ensemble(
    df_eth: pd.DataFrame, df_btc: pd.DataFrame, funding_eth: pd.DataFrame, funding_btc: pd.DataFrame
) -> pd.Series:
    """Đỉnh cao tổng hợp: Kalman Filter + Wavelet Denoising + Funding Carry + OU Gating + Vol Target."""
    idx = df_eth.index.intersection(df_btc.index)
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]
    log_eth = np.log(c_eth)
    log_btc = np.log(c_btc)

    # 1. Kalman dynamic spread
    _, spread = compute_kalman_dynamic_beta(log_eth, log_btc, delta=5e-5, vt=1e-3)

    # 2. Wavelet a trous denoising on spread
    s1 = 0.5 * (spread + spread.shift(1).bfill())
    s2 = 0.5 * (s1 + s1.shift(2).bfill())
    s3 = 0.5 * (s2 + s2.shift(4).bfill())
    denoised_spread = s3

    spread_ma = denoised_spread.rolling(720).mean()
    spread_std = denoised_spread.rolling(720).std().replace(0, np.nan)
    z_smooth = ((denoised_spread - spread_ma) / spread_std).ewm(span=36, adjust=False).mean()

    # 3. Funding Carry Filter
    f_eth_8h = funding_eth.reindex(idx, method="ffill")["funding_rate"].fillna(0.0)
    f_btc_8h = funding_btc.reindex(idx, method="ffill")["funding_rate"].fillna(0.0)
    carry_ok = (f_eth_8h - f_btc_8h) < 0.00025

    # 4. OU half-life filter
    ratio = c_eth / c_btc
    hl = compute_ou_half_life(ratio, window=240)
    ou_gate = (hl >= 8.0) & (hl <= 120.0)

    # 5. Volatility Scaling
    trend = (c_eth.rolling(240).mean() > c_eth.rolling(960).mean()).astype(float)
    vol_scale = (0.35 / (c_eth.pct_change().rolling(1440).std() * np.sqrt(8760))).clip(0.2, 1.0)

    pos = pd.Series(0.0, index=idx)
    curr = 0.0
    for i in range(len(idx)):
        t_idx = idx[i]
        tr = trend.iloc[i]
        zs = z_smooth.iloc[i]
        vs = vol_scale.iloc[i]
        c_ok = carry_ok.iloc[i]
        og = ou_gate.iloc[i]

        sig_active = (tr == 1.0) and (not pd.isna(zs)) and (zs > -1.15) and (zs < 1.15) and c_ok and og
        target = vs if sig_active else 0.0
        if tr == 0.0 or not sig_active or pd.isna(vs):
            curr = 0.0
        elif curr == 0.0:
            curr = min(1.0, target)
        else:
            if abs(target - curr) >= 0.15:
                curr = min(1.0, target)
        pos.loc[t_idx] = curr
    return pos


# ==============================================================================
# 3. MULTI-YEAR BATCH RUNNER ACROSS 20 CANDIDATES
# ==============================================================================

def run_all_candidates_research():
    print("=" * 80)
    print("   PEAKPULSE AI - POINT72 CUBIST 20-CANDIDATE ADVANCED QUANT RESEARCH")
    print("   Mục tiêu: Đạt tỷ số Calmar (CAGR / MaxDD) vượt trội hơn Baseline > 5%")
    print("=" * 80)

    # 1. Load Data
    print("\n[BƯỚC 1/3] Nạp dữ liệu Binance USD-M Futures 1H (2020 - 2026)...")
    df_eth = btest.get_complete_1h_data("ETHUSDT")
    df_btc = btest.get_complete_1h_data("BTCUSDT")
    f_eth = btest.get_complete_funding_data("ETHUSDT")
    f_btc = btest.get_complete_funding_data("BTCUSDT")

    print(f"  ETH bars: {len(df_eth):,}, BTC bars: {len(df_btc):,}")

    # 2. Evaluate Baseline
    print("\n[BƯỚC 2/3] Chạy kiểm định Baseline Point72 Cubist...")
    t0 = time.time()
    base_pos = get_baseline_point72(df_eth, df_btc)
    base_res = btest.simulate_backtest(df_eth, base_pos, f_eth)
    base_std = base_res["standard"]

    base_cagr = base_std["cagr"] * 100.0
    base_mdd = abs(base_std["max_dd"]) * 100.0
    base_calmar = base_cagr / base_mdd if base_mdd > 1e-4 else 0.0
    target_calmar_hurdle = base_calmar * 1.05  # +5% requirement

    print(f"\n>> BASELINE POINT72 CUBIST RESULTS (2020 - 2026):")
    print(f"   CAGR: {base_cagr:+.2f}% | MaxDD: -{base_mdd:.2f}% | Calmar: {base_calmar:.4f}")
    print(f"   Sharpe: {base_std['sharpe']:.2f} | Win Rate: {base_std['win_rate']:.1f}% | Trades: {base_std['trades']}")
    print(f"   ==> MỨC NGƯỠNG CALMAR CẦN VƯỢT QUA (+5%): {target_calmar_hurdle:.4f}\n")

    # 3. Define Candidate Registry
    candidates: List[Dict[str, Any]] = [
        {"id": "C01", "name": "C1: Dynamic Kalman Filter Beta", "func": lambda: generate_c1_kalman_beta(df_eth, df_btc)},
        {"id": "C02", "name": "C2: Funding Rate Carry Divergence", "func": lambda: generate_c2_funding_carry(df_eth, df_btc, f_eth, f_btc)},
        {"id": "C03", "name": "C3: Ornstein-Uhlenbeck Half-Life Gating", "func": lambda: generate_c3_ou_halflife(df_eth, df_btc)},
        {"id": "C04", "name": "C4: Wavelet Multi-Resolution Denoised Spread", "func": lambda: generate_c4_wavelet_denoised(df_eth, df_btc)},
        {"id": "C05", "name": "C5: Asymmetric Regime-Conditioned Bands", "func": lambda: generate_c5_asymmetric_bands(df_eth, df_btc)},
        {"id": "C06", "name": "C6: Rolling Hurst Exponent Persistence Gating", "func": lambda: generate_c6_hurst_gating(df_eth, df_btc)},
        {"id": "C07", "name": "C7: Microstructure Taker Volume & CVD Imbalance", "func": lambda: generate_c7_taker_volume_delta(df_eth, df_btc)},
        {"id": "C08", "name": "C8: Cornish-Fisher Fat-Tail Volatility Scaler", "func": lambda: generate_c8_cornish_fisher(df_eth, df_btc)},
        {"id": "C09", "name": "C9: Dual-Barrier Profit Taking & Trailing Stop", "func": lambda: generate_c9_dual_barrier_tp(df_eth, df_btc)},
        {"id": "C10", "name": "C10: Amihud Illiquidity Spike Suppression", "func": lambda: generate_c10_amihud_suppression(df_eth, df_btc)},
        {"id": "C11", "name": "C11: Realized Volatility Ratio / VRP Regimes", "func": lambda: generate_c11_vol_ratio_vrp(df_eth, df_btc)},
        {"id": "C12", "name": "C12: Co-Kurtosis Tail Protection Overlay", "func": lambda: generate_c12_cokurtosis_tail(df_eth, df_btc)},
        {"id": "C13", "name": "C13: Adaptive Microstructure Turnover Buffer", "func": lambda: generate_c13_adaptive_buffer(df_eth, df_btc)},
        {"id": "C14", "name": "C14: Bollinger-Keltner Volatility Squeeze Arbitrage", "func": lambda: generate_c14_bollinger_keltner(df_eth, df_btc)},
        {"id": "C15", "name": "C15: Dynamic Lookback AIC Multi-Horizon Tuning", "func": lambda: generate_c15_dynamic_aic_lookback(df_eth, df_btc)},
        {"id": "C16", "name": "C16: Multi-Factor Composite Z-Score (Price+Funding+Vol)", "func": lambda: generate_c16_multifactor_composite_z(df_eth, df_btc, f_eth, f_btc)},
        {"id": "C17", "name": "C17: CUSUM Cumulative Structural Break Circuit Breaker", "func": lambda: generate_c17_cusum_structural_break(df_eth, df_btc)},
        {"id": "C18", "name": "C18: Funding Settlement Anticipation & Front-running", "func": lambda: generate_c18_funding_settlement_timing(df_eth, df_btc, f_eth)},
        {"id": "C19", "name": "C19: Walk-Forward Meta-Labeling Machine Learning Gate", "func": lambda: generate_c19_walk_forward_meta_labeling(df_eth, df_btc)},
        {"id": "C20", "name": "C20: Point72 Elite Master Ensemble Synthesis", "func": lambda: generate_c20_master_ensemble(df_eth, df_btc, f_eth, f_btc)},
    ]

    results: List[Dict[str, Any]] = []

    print("[BƯỚC 3/3] Bắt đầu kiểm tra đồng loạt 20 ứng viên cải tiến...\n")
    for cand in candidates:
        c_id = cand["id"]
        c_name = cand["name"]
        print(f"--> Dang tinh toan {c_id}: {c_name}...", end="", flush=True)
        try:
            pos = cand["func"]()
            sim = btest.simulate_backtest(df_eth, pos, f_eth)
            std = sim["standard"]
            stress = sim["stress"]

            cagr = std["cagr"] * 100.0
            mdd = abs(std["max_dd"]) * 100.0
            calmar = cagr / mdd if mdd > 1e-4 else 0.0
            calmar_diff_pct = ((calmar - base_calmar) / base_calmar) * 100.0
            beats_hurdle = calmar_diff_pct >= 5.0

            cand_res = {
                "id": c_id,
                "name": c_name,
                "cagr": cagr,
                "total_return": std["total_return"] * 100.0,
                "mdd": mdd,
                "calmar": calmar,
                "calmar_diff_pct": calmar_diff_pct,
                "beats_hurdle": beats_hurdle,
                "sharpe": std["sharpe"],
                "win_rate": std["win_rate"],
                "trades": std["trades"],
                "avg_holding": std["avg_holding_hours"],
                "stress_cagr": stress["cagr"] * 100.0,
                "stress_mdd": abs(stress["max_dd"]) * 100.0,
            }
            results.append(cand_res)
            status_tag = f"[VƯỢT CHỈ TIÊU +{calmar_diff_pct:.1f}%]" if beats_hurdle else f"[{calmar_diff_pct:+.1f}%]"
            print(f" Done! CAGR: {cagr:+.2f}% | MaxDD: -{mdd:.2f}% | Calmar: {calmar:.4f} {status_tag}")
        except Exception as e:
            print(f" LOI: {e}")

    # Sort results by Calmar ratio descending
    results_sorted = sorted(results, key=lambda x: x["calmar"], reverse=True)

    # Save detailed JSON for web dashboard and reports
    out_json = REPO_ROOT / "artifacts" / "point72_candidates_results.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({
            "baseline": {
                "cagr": base_cagr,
                "mdd": base_mdd,
                "calmar": base_calmar,
                "sharpe": base_std["sharpe"],
                "win_rate": base_std["win_rate"],
                "trades": base_std["trades"],
            },
            "candidates": results_sorted,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }, f, indent=2)

    print(f"\n--> Da luu ket qua vao {out_json}")
    return results_sorted, base_calmar


if __name__ == "__main__":
    run_all_candidates_research()
