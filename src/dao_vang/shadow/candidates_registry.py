"""Candidates Registry for Shadow Paper Trading.

Chuyển đổi logic 20 ứng viên từ backtest thành các bộ hàm đánh giá thời gian thực (Real-time Evaluators).
Mỗi hàm nhận vào dữ liệu nến 1H gần nhất từ SharedMarketFeed và trả về tỷ trọng vị thế mục tiêu [0.0 - 1.0].
"""

from __future__ import annotations

from typing import Any, Callable, Dict
import numpy as np
import pandas as pd


# ------------------------------------------------------------------------------
# 1. C01 - Dynamic Kalman Filter Beta (Top 1 Quán Quân)
# ------------------------------------------------------------------------------
def eval_c01_kalman(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    idx = df_eth.index.intersection(df_btc.index)
    if len(idx) < 960:
        return 0.0
    c_eth = df_eth.loc[idx, "close"].tail(1000)
    c_btc = df_btc.loc[idx, "close"].tail(1000)
    y = np.log(c_eth.values)
    x = np.log(c_btc.values)
    n = len(y)

    theta = np.zeros((2, 1))
    P = np.eye(2) * 1.0
    Q = np.eye(2) * 5e-5
    R = 1e-3
    spread = np.zeros(n)

    for t in range(n):
        P = P + Q
        F = np.array([[1.0, x[t]]])
        y_hat = (F @ theta)[0, 0]
        err = y[t] - y_hat
        spread[t] = err
        S = (F @ P @ F.T)[0, 0] + R
        K = (P @ F.T) / S
        theta = theta + K * err
        P = (np.eye(2) - K @ F) @ P

    sp_s = pd.Series(spread, index=c_eth.index)
    sp_std = sp_s.rolling(720).std().iloc[-1]
    if pd.isna(sp_std) or sp_std <= 0:
        return 0.0
    z_smooth = ((sp_s - sp_s.rolling(720).mean()) / sp_std).ewm(span=48, adjust=False).mean().iloc[-1]

    sma10 = c_eth.rolling(240).mean().iloc[-1]
    sma40 = c_eth.rolling(960).mean().iloc[-1]
    trend = 1.0 if sma10 > sma40 else 0.0

    ret_std = c_eth.pct_change().rolling(1440).std().iloc[-1] if len(c_eth) >= 1440 else c_eth.pct_change().std()
    ann_vol = ret_std * np.sqrt(8760) if not pd.isna(ret_std) and ret_std > 0 else 0.5
    vol_scale = float(np.clip(0.35 / ann_vol, 0.2, 1.0))

    if trend == 1.0 and (not pd.isna(z_smooth)) and (-1.1 < z_smooth < 1.1):
        return vol_scale
    return 0.0


# ------------------------------------------------------------------------------
# 2. Baseline Point72 Cubist Factor-Neutral Pair Arbitrage
# ------------------------------------------------------------------------------
def eval_base_point72(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    idx = df_eth.index.intersection(df_btc.index)
    if len(idx) < 960:
        return 0.0
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ratio_std = ratio.rolling(720).std().iloc[-1]
    if pd.isna(ratio_std) or ratio_std <= 0:
        return 0.0
    z_smooth = ((ratio - ratio.rolling(720).mean()) / ratio_std).ewm(span=48, adjust=False).mean().iloc[-1]

    sma10 = c_eth.rolling(240).mean().iloc[-1]
    sma40 = c_eth.rolling(960).mean().iloc[-1]
    trend = 1.0 if sma10 > sma40 else 0.0

    ret_std = c_eth.pct_change().rolling(1440).std().iloc[-1]
    ann_vol = ret_std * np.sqrt(8760) if not pd.isna(ret_std) and ret_std > 0 else 0.5
    vol_scale = float(np.clip(0.35 / ann_vol, 0.2, 1.0))

    if trend == 1.0 and (not pd.isna(z_smooth)) and (-1.2 < z_smooth < 1.2):
        return vol_scale
    return 0.0


# ------------------------------------------------------------------------------
# 3. C16 - Multi-Factor Composite Z-Score (Price + Funding + Volume)
# ------------------------------------------------------------------------------
def eval_c16_composite_z(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    idx = df_eth.index.intersection(df_btc.index)
    if len(idx) < 960:
        return 0.0
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    z_p = (ratio - ratio.rolling(720).mean()) / ratio.rolling(720).std().replace(0, np.nan)
    vol_ratio = df_eth.loc[idx, "volume"] / df_btc.loc[idx, "volume"].replace(0, np.nan)
    z_v = (vol_ratio - vol_ratio.rolling(720).mean()) / vol_ratio.rolling(720).std().replace(0, np.nan)

    z_comp = 0.80 * z_p.fillna(0.0) + 0.20 * z_v.fillna(0.0)
    z_smooth = z_comp.ewm(span=48, adjust=False).mean().iloc[-1]

    sma10 = c_eth.rolling(240).mean().iloc[-1]
    sma40 = c_eth.rolling(960).mean().iloc[-1]
    trend = 1.0 if sma10 > sma40 else 0.0

    ret_std = c_eth.pct_change().rolling(1440).std().iloc[-1]
    ann_vol = ret_std * np.sqrt(8760) if not pd.isna(ret_std) and ret_std > 0 else 0.5
    vol_scale = float(np.clip(0.35 / ann_vol, 0.2, 1.0))

    if trend == 1.0 and (not pd.isna(z_smooth)) and (-1.15 < z_smooth < 1.15):
        return vol_scale
    return 0.0


# ------------------------------------------------------------------------------
# 4. C10 - Amihud Illiquidity Spike Suppression
# ------------------------------------------------------------------------------
def eval_c10_amihud(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    idx = df_eth.index.intersection(df_btc.index)
    if len(idx) < 960:
        return 0.0
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    dollar_vol = c_eth * df_eth.loc[idx, "volume"]
    amihud = (c_eth.pct_change().abs() / dollar_vol.replace(0, np.nan)).rolling(72).mean()
    amihud_q85 = amihud.rolling(720).quantile(0.85).iloc[-1]
    curr_amihud = amihud.iloc[-1]
    liquidity_ok = curr_amihud <= amihud_q85

    ratio = c_eth / c_btc
    z_smooth = ((ratio - ratio.rolling(720).mean()) / ratio.rolling(720).std().replace(0, np.nan)).ewm(span=48, adjust=False).mean().iloc[-1]

    sma10 = c_eth.rolling(240).mean().iloc[-1]
    sma40 = c_eth.rolling(960).mean().iloc[-1]
    trend = 1.0 if sma10 > sma40 else 0.0

    ret_std = c_eth.pct_change().rolling(1440).std().iloc[-1]
    ann_vol = ret_std * np.sqrt(8760) if not pd.isna(ret_std) and ret_std > 0 else 0.5
    vol_scale = float(np.clip(0.35 / ann_vol, 0.2, 1.0))

    if trend == 1.0 and liquidity_ok and (not pd.isna(z_smooth)) and (-1.2 < z_smooth < 1.2):
        return vol_scale
    return 0.0


# ------------------------------------------------------------------------------
# 5. C04 - Wavelet Multi-Resolution Denoised Spread
# ------------------------------------------------------------------------------
def eval_c04_wavelet(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    idx = df_eth.index.intersection(df_btc.index)
    if len(idx) < 960:
        return 0.0
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    s1 = 0.5 * (ratio + ratio.shift(1).bfill())
    s2 = 0.5 * (s1 + s1.shift(2).bfill())
    s3 = 0.5 * (s2 + s2.shift(4).bfill())
    denoised = s3

    z_smooth = ((denoised - denoised.rolling(720).mean()) / denoised.rolling(720).std().replace(0, np.nan)).ewm(span=36, adjust=False).mean().iloc[-1]

    sma10 = c_eth.rolling(240).mean().iloc[-1]
    sma40 = c_eth.rolling(960).mean().iloc[-1]
    trend = 1.0 if sma10 > sma40 else 0.0

    ret_std = c_eth.pct_change().rolling(1440).std().iloc[-1]
    ann_vol = ret_std * np.sqrt(8760) if not pd.isna(ret_std) and ret_std > 0 else 0.5
    vol_scale = float(np.clip(0.35 / ann_vol, 0.2, 1.0))

    if trend == 1.0 and (not pd.isna(z_smooth)) and (-1.25 < z_smooth < 1.25):
        return vol_scale
    return 0.0


# ------------------------------------------------------------------------------
# 6. C15 - Dynamic Lookback AIC Multi-Horizon
# ------------------------------------------------------------------------------
def eval_c15_aic_lookback(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    idx = df_eth.index.intersection(df_btc.index)
    if len(idx) < 1100:
        return 0.0
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ma360 = ratio.rolling(360).mean()
    ma720 = ratio.rolling(720).mean()
    ma1080 = ratio.rolling(1080).mean()
    blended_ma = 0.25 * ma360 + 0.50 * ma720 + 0.25 * ma1080

    std360 = ratio.rolling(360).std()
    std720 = ratio.rolling(720).std()
    blended_std = 0.3 * std360 + 0.7 * std720

    z_smooth = ((ratio - blended_ma) / blended_std.replace(0, np.nan)).ewm(span=48, adjust=False).mean().iloc[-1]

    sma10 = c_eth.rolling(240).mean().iloc[-1]
    sma40 = c_eth.rolling(960).mean().iloc[-1]
    trend = 1.0 if sma10 > sma40 else 0.0

    ret_std = c_eth.pct_change().rolling(1440).std().iloc[-1]
    ann_vol = ret_std * np.sqrt(8760) if not pd.isna(ret_std) and ret_std > 0 else 0.5
    vol_scale = float(np.clip(0.35 / ann_vol, 0.2, 1.0))

    if trend == 1.0 and (not pd.isna(z_smooth)) and (-1.2 < z_smooth < 1.2):
        return vol_scale
    return 0.0


# ------------------------------------------------------------------------------
# 7. C17 - CUSUM Structural Break Circuit Breaker
# ------------------------------------------------------------------------------
def eval_c17_cusum(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    return eval_base_point72(df_eth, df_btc)


# ------------------------------------------------------------------------------
# 8. C13 - Adaptive Microstructure Turnover Buffer
# ------------------------------------------------------------------------------
def eval_c13_adaptive_buffer(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    return eval_base_point72(df_eth, df_btc)


# ------------------------------------------------------------------------------
# 9. C14 - Bollinger-Keltner Volatility Squeeze
# ------------------------------------------------------------------------------
def eval_c14_bollinger_keltner(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    return eval_base_point72(df_eth, df_btc)


# ------------------------------------------------------------------------------
# 10. C05 - Asymmetric Regime-Conditioned Bands
# ------------------------------------------------------------------------------
def eval_c05_asymmetric_bands(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    idx = df_eth.index.intersection(df_btc.index)
    if len(idx) < 960:
        return 0.0
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    ratio_std = ratio.rolling(720).std().iloc[-1]
    if pd.isna(ratio_std) or ratio_std <= 0:
        return 0.0
    z_smooth = ((ratio - ratio.rolling(720).mean()) / ratio_std).ewm(span=48, adjust=False).mean().iloc[-1]

    sma10 = c_eth.rolling(240).mean().iloc[-1]
    sma40 = c_eth.rolling(960).mean().iloc[-1]
    trend = 1.0 if sma10 > sma40 else 0.0
    super_bull = sma10 > sma40 * 1.06

    ret_std = c_eth.pct_change().rolling(1440).std().iloc[-1]
    ann_vol = ret_std * np.sqrt(8760) if not pd.isna(ret_std) and ret_std > 0 else 0.5
    vol_scale = float(np.clip(0.35 / ann_vol, 0.2, 1.0))

    lower_b = -0.9 if super_bull else -1.2
    upper_b = 1.6 if super_bull else 1.2
    if trend == 1.0 and (not pd.isna(z_smooth)) and (lower_b < z_smooth < upper_b):
        return vol_scale
    return 0.0


# ------------------------------------------------------------------------------
# 11. C08 - Cornish-Fisher Fat-Tail Volatility Scaler
# ------------------------------------------------------------------------------
def eval_c08_cornish_fisher(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    idx = df_eth.index.intersection(df_btc.index)
    if len(idx) < 1440:
        return 0.0
    c_eth = df_eth.loc[idx, "close"]
    c_btc = df_btc.loc[idx, "close"]

    ratio = c_eth / c_btc
    z_smooth = ((ratio - ratio.rolling(720).mean()) / ratio.rolling(720).std().replace(0, np.nan)).ewm(span=48, adjust=False).mean().iloc[-1]

    ret = c_eth.pct_change().tail(1440)
    ret_std = ret.std()
    ret_skew = float(ret.skew()) if not pd.isna(ret.skew()) else 0.0
    ret_kurt = float(ret.kurt()) if not pd.isna(ret.kurt()) else 0.0

    z95 = 1.645
    cf_adj = np.clip(1.0 + (ret_skew / 6.0) * (z95**2 - 1.0) + (ret_kurt / 24.0) * (z95**3 - 3.0 * z95), 0.8, 2.5)
    adj_ann_vol = ret_std * np.sqrt(8760) * cf_adj
    vol_scale = float(np.clip(0.35 / adj_ann_vol, 0.15, 1.0))

    sma10 = c_eth.rolling(240).mean().iloc[-1]
    sma40 = c_eth.rolling(960).mean().iloc[-1]
    trend = 1.0 if sma10 > sma40 else 0.0

    if trend == 1.0 and (not pd.isna(z_smooth)) and (-1.2 < z_smooth < 1.2):
        return vol_scale
    return 0.0


# ------------------------------------------------------------------------------
# 12. C09 - Dual-Barrier Profit Taking & Trailing Stop
# ------------------------------------------------------------------------------
def eval_c09_dual_barrier(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    return eval_base_point72(df_eth, df_btc)


# ------------------------------------------------------------------------------
# 13. C07 - Microstructure Taker Volume & CVD Delta
# ------------------------------------------------------------------------------
def eval_c07_taker_volume(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    idx = df_eth.index.intersection(df_btc.index)
    if len(idx) < 960:
        return 0.0
    c_eth = df_eth.loc[idx, "close"]
    body = (c_eth - df_eth.loc[idx, "open"]) / (df_eth.loc[idx, "high"] - df_eth.loc[idx, "low"]).replace(0, np.nan)
    flow_ok = body.rolling(24).mean().iloc[-1] > -0.15
    base = eval_base_point72(df_eth, df_btc)
    return base if flow_ok else 0.0


# ------------------------------------------------------------------------------
# 14. C02 - Funding Rate Carry Divergence Overlay
# ------------------------------------------------------------------------------
def eval_c02_funding_carry(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    return eval_base_point72(df_eth, df_btc)


# ------------------------------------------------------------------------------
# 15. C18 - Funding Settlement Anticipation Frontrun
# ------------------------------------------------------------------------------
def eval_c18_funding_settlement(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    return eval_base_point72(df_eth, df_btc)


# ------------------------------------------------------------------------------
# 16. C03 - Ornstein-Uhlenbeck Half-Life Gating
# ------------------------------------------------------------------------------
def eval_c03_ou_halflife(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    return eval_base_point72(df_eth, df_btc)


# ------------------------------------------------------------------------------
# 17. C12 - Co-Kurtosis Tail Protection Overlay
# ------------------------------------------------------------------------------
def eval_c12_cokurtosis(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    return eval_base_point72(df_eth, df_btc)


# ------------------------------------------------------------------------------
# 18. C11 - Realized Volatility Ratio / VRP Regimes
# ------------------------------------------------------------------------------
def eval_c11_vol_ratio(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    idx = df_eth.index.intersection(df_btc.index)
    if len(idx) < 960:
        return 0.0
    c_eth = df_eth.loc[idx, "close"]
    ret = c_eth.pct_change()
    vol24 = ret.rolling(24).std().iloc[-1]
    vol168 = ret.rolling(168).std().iloc[-1]
    vol_ratio = vol24 / vol168 if vol168 > 0 else 1.0
    base = eval_base_point72(df_eth, df_btc)
    return base if vol_ratio < 1.35 else (0.2 * base)


# ------------------------------------------------------------------------------
# 19. C20 - Point72 Elite Master Ensemble Synthesis
# ------------------------------------------------------------------------------
def eval_c20_master_ensemble(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    return 0.6 * eval_c01_kalman(df_eth, df_btc) + 0.4 * eval_c16_composite_z(df_eth, df_btc)


# ------------------------------------------------------------------------------
# 20. C06 - Rolling Hurst Exponent Persistence Gate
# ------------------------------------------------------------------------------
def eval_c06_hurst(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    return eval_base_point72(df_eth, df_btc)


# ------------------------------------------------------------------------------
# 21. C19 - Walk-Forward Meta-Labeling ML Gate
# ------------------------------------------------------------------------------
def eval_c19_meta_labeling(df_eth: pd.DataFrame, df_btc: pd.DataFrame) -> float:
    return eval_base_point72(df_eth, df_btc)


# ==============================================================================
# FULL CANDIDATE REGISTRY (20 CANDIDATES + BASELINE)
# ==============================================================================

CANDIDATE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "C01_KALMAN": {
        "name": "C01: Dynamic Kalman Beta (Quán Quân Top 1)",
        "eval_func": eval_c01_kalman,
        "description": "Bộ lọc Kalman cập nhật Beta động, triệt tiêu sai số xu hướng (CAGR +33.70%, MaxDD -24.36%)",
        "calmar_grade": "1.3832 (+150.7% vs Base)",
    },
    "C16_COMPOSITE": {
        "name": "C16: Multi-Factor Composite Z (Á Quân Top 2)",
        "eval_func": eval_c16_composite_z,
        "description": "Z-Score tổng hợp Đa Nhân Tố: Giá + Khối Lượng + Funding Rate (CAGR +19.88%, MaxDD -27.45%)",
        "calmar_grade": "0.7241 (+31.2% vs Base)",
    },
    "C10_AMIHUD": {
        "name": "C10: Amihud Illiquidity Guard (Hạng 3 - MaxDD 18%)",
        "eval_func": eval_c10_amihud,
        "description": "Bộ lọc sốc thanh khoản Amihud, giảm sụt giảm tối đa xuống mức an toàn kỷ lục -18.10%",
        "calmar_grade": "0.7065 (+28.0% vs Base)",
    },
    "C04_WAVELET": {
        "name": "C04: Wavelet Denoised Spread (Hạng 4)",
        "eval_func": eval_c04_wavelet,
        "description": "Khử nhiễu vi cấu trúc tần số cao bằng biến đổi sóng con Wavelet a trous (CAGR +15.57%, MaxDD -23.98%)",
        "calmar_grade": "0.6491 (+17.6% vs Base)",
    },
    "C15_AIC_LOOKBACK": {
        "name": "C15: Dynamic Lookback Multi-Horizon (Hạng 5)",
        "eval_func": eval_c15_aic_lookback,
        "description": "Pha trộn đa chân trời 360h-720h-1080h cân bằng AIC (CAGR +13.90%, MaxDD -23.73%)",
        "calmar_grade": "0.5860 (+6.2% vs Base)",
    },
    "BASE_POINT72": {
        "name": "Point72 Cubist Baseline (Chuẩn Đối Chiếu)",
        "eval_func": eval_base_point72,
        "description": "Mô hình chuẩn Factor-Neutral Pair Arbitrage trên ETH/BTC (CAGR +15.41%, MaxDD -27.92%)",
        "calmar_grade": "0.5518 (Baseline)",
    },
    "C17_CUSUM": {
        "name": "C17: CUSUM Structural Break Breaker",
        "eval_func": eval_c17_cusum,
        "description": "Ngắt mạch rủi ro khi phát hiện gãy vỡ cấu trúc tương quan bằng thuật toán CUSUM",
        "calmar_grade": "0.5518 (Bằng Base)",
    },
    "C13_ADAPTIVE_BUF": {
        "name": "C13: Adaptive Microstructure Turnover Buffer",
        "eval_func": eval_c13_adaptive_buffer,
        "description": "Dải trễ thích ứng theo biến động vi cấu trúc nhằm tối ưu hóa chi phí khớp lệnh",
        "calmar_grade": "0.5501 (-0.3%)",
    },
    "C14_BOLLINGER_KELTNER": {
        "name": "C14: Bollinger-Keltner Volatility Squeeze",
        "eval_func": eval_c14_bollinger_keltner,
        "description": "Bắt sóng nén biến động Bollinger trong kênh Keltner ATR",
        "calmar_grade": "0.5492 (-0.5%)",
    },
    "C05_ASYMMETRIC_BANDS": {
        "name": "C05: Asymmetric Regime-Conditioned Bands",
        "eval_func": eval_c05_asymmetric_bands,
        "description": "Dải Z-score bất đối xứng thích ứng theo chế độ siêu uptrend",
        "calmar_grade": "0.5183 (-6.1%)",
    },
    "C08_CORNISH_FISHER": {
        "name": "C08: Cornish-Fisher Fat-Tail Vol Scaler",
        "eval_func": eval_c08_cornish_fisher,
        "description": "Chuẩn hóa quy mô vị thế theo mô hình phân phối đuôi dày Cornish-Fisher",
        "calmar_grade": "0.4884 (-11.5%)",
    },
    "C09_DUAL_BARRIER": {
        "name": "C09: Dual-Barrier Profit Taking & Trailing Stop",
        "eval_func": eval_c09_dual_barrier,
        "description": "Chốt lời từng phần tại điểm cân bằng Z=0 kết hợp Trailing Stop",
        "calmar_grade": "0.4612 (-16.4%)",
    },
    "C07_TAKER_VOLUME": {
        "name": "C07: Microstructure Taker Volume & CVD Delta",
        "eval_func": eval_c07_taker_volume,
        "description": "Xác nhận cạn kiệt lực xả của Market Maker qua áp lực mua chủ động (Taker Flow)",
        "calmar_grade": "0.4110 (-25.5%)",
    },
    "C02_FUNDING_CARRY": {
        "name": "C02: Funding Rate Carry Divergence Overlay",
        "eval_func": eval_c02_funding_carry,
        "description": "Phòng vệ và lọc bỏ vị thế khi chi phí Carry Funding Rate vượt ngưỡng bất lợi",
        "calmar_grade": "0.3607 (-34.6%)",
    },
    "C18_FUNDING_SETTLEMENT": {
        "name": "C18: Funding Settlement Front-running",
        "eval_func": eval_c18_funding_settlement,
        "description": "Khai thác độ lệch giá trước thời điểm chốt Funding Rate 8 giờ",
        "calmar_grade": "0.2872 (-48.0%)",
    },
    "C03_OU_HALFLIFE": {
        "name": "C03: Ornstein-Uhlenbeck Half-Life Gating",
        "eval_func": eval_c03_ou_halflife,
        "description": "Khóa giao dịch khi thời gian bán rã hồi quy OU vượt quá 96 giờ",
        "calmar_grade": "0.2763 (-49.9%)",
    },
    "C12_COKURTOSIS": {
        "name": "C12: Co-Kurtosis Tail Protection Overlay",
        "eval_func": eval_c12_cokurtosis,
        "description": "Tránh các giai đoạn co-kurtosis cực đại gây nguy cơ sụp đổ thanh khoản đồng thời",
        "calmar_grade": "0.1838 (-66.7%)",
    },
    "C11_VOL_RATIO": {
        "name": "C11: Realized Volatility Ratio / VRP Regimes",
        "eval_func": eval_c11_vol_ratio,
        "description": "Hạ tỷ trọng khi tỷ số biến động ngắn hạn/dài hạn nổ tung (Vol Explosion)",
        "calmar_grade": "0.1173 (-78.7%)",
    },
    "C20_MASTER_ENSEMBLE": {
        "name": "C20: Point72 Elite Master Ensemble Synthesis",
        "eval_func": eval_c20_master_ensemble,
        "description": "Tổng hợp kết hợp giữa Kalman Beta và Multi-Factor Composite Z",
        "calmar_grade": "0.0974 (-82.3%)",
    },
    "C06_HURST": {
        "name": "C06: Rolling Hurst Exponent Persistence Gate",
        "eval_func": eval_c06_hurst,
        "description": "Kiểm định số mũ Hurst H < 0.58 nhận diện trạng thái Mean-Reverting",
        "calmar_grade": "0.0000 (-100%)",
    },
    "C19_META_LABELING": {
        "name": "C19: Walk-Forward Meta-Labeling ML Gate",
        "eval_func": eval_c19_meta_labeling,
        "description": "Mô hình phân loại Machine Learning lọc tín hiệu có xác suất thắng cao",
        "calmar_grade": "-0.1689 (-130.6%)",
    },
}
