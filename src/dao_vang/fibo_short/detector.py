"""Multi-timeframe Confirmed Reversal & Fibonacci Short detector (H4/D1 -> H1).

Strict Point-in-Time (No-Lookahead) rules:
1. Higher Timeframe (H4 or D1):
   - Prior upward impulse creates a Swing High (Fibo 1.0).
   - A bearish reversal candle (close < open) initiates a confirmed downward
     impulse wave to an Impulse Low (Fibo 0.0) with drop >= min_impulse_drop_pct.
   - Subsequent pullback bars must not invalidate above Swing High (Fibo 1.0).
2. Fibonacci Grid:
   - Drawn from Swing High (1.0) down to Impulse Low (0.0).
   - Golden Pocket entry zone: Fibo 0.500 - 0.618 (watch zone: 0.382 - 0.786).
   - Stop Loss: above Swing High (1.0) + ATR buffer (or above 0.786 + ATR).
   - Take Profit: TP1 at Fibo 0.0 (old low), TP2 at Fibo Ext 1.272, TP3 at Fibo Ext 1.618.
3. H1 Confirmation Candle:
   - Price pullback touches/enters the Fibonacci entry zone (0.500 - 0.618 / 0.786).
   - Base rule: H1 closed candle is RED (close < open) AND price did not rise in 1h
     (price_ret_1h <= 0).
   - Condition 1 (Bearish Candle Pattern on H1): Bearish Engulfing, Shooting Star /
     Bearish Pinbar, or Strong Bearish Rejection bar at Fibo zone.
   - Condition 2 (Break of H1 Short-term Structure): H1 close breaks below previous
     H1 candle low (close_t < low_{t-1}) or closes back below Fibo 0.500 after
     testing the Golden Pocket.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Literal, Sequence

from dao_vang.config.settings import FiboTrendShortConfig
from dao_vang.fibo_short.models import (
    ConfirmationTier,
    FibonacciLevels,
    FiboShortSignal,
    FiboTradeSetup,
    H1ConfirmationResult,
    SignalStage,
    SwingImpulseWave,
)


def _format_price(price: float) -> str:
    if price < 0.001:
        return f"${price:.6f}"
    if price < 1.0:
        return f"${price:.5f}"
    if price < 10.0:
        return f"${price:.4f}"
    return f"${price:.2f}"


def compute_atr(klines: Sequence[dict[str, Any]], period: int = 14) -> float:
    """Compute Point-in-Time Average True Range (ATR) on closed klines."""
    if not klines:
        return 0.0
    if len(klines) == 1:
        return max(0.0, float(klines[0]["high"]) - float(klines[0]["low"]))

    trs: list[float] = []
    start = max(1, len(klines) - period)
    for i in range(start, len(klines)):
        high = float(klines[i]["high"])
        low = float(klines[i]["low"])
        prev_close = float(klines[i - 1]["close"])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if not trs:
        return max(0.0, float(klines[-1]["high"]) - float(klines[-1]["low"]))
    return sum(trs) / len(trs)


def _compute_ker_from_closes(closes: Sequence[float]) -> float:
    """Compute Point-in-Time Kaufman Efficiency Ratio (KER) in [0.0, 1.0]."""
    if len(closes) < 2:
        return 0.0
    net_change = abs(float(closes[-1]) - float(closes[0]))
    path_change = sum(abs(float(closes[i]) - float(closes[i - 1])) for i in range(1, len(closes)))
    if path_change <= 1e-12:
        return 0.0
    return max(0.0, min(1.0, net_change / path_change))


def compute_canonical_pst_series(
    closes: Sequence[float],
    *,
    use_bfill: bool = False,
) -> tuple[list[float], list[float], list[float], list[float]]:
    """Canonical Carver (pysystemtrade) robust_vol, ewmac_4_16, ewmac_16_64, and accel_4_16.

    Unified across research scripts and detector/scanner:
    - ``diff = close.diff()``
    - ``vol = diff.ewm(span=35, adjust=True, min_periods=1).std()``
    - When ``use_bfill=False`` (default, strictly causal Point-in-Time):
      ``vol = vol.ffill().fillna(abs(close) * 0.02)``
    - ``robust_vol = max(vol, abs(close) * 0.005, 1e-9)``
    - ``ema_fast = close.ewm(span=fast, adjust=True, min_periods=1).mean()``
    - ``ema_slow = close.ewm(span=slow, adjust=True, min_periods=1).mean()``
    - ``ewmac = (ema_fast - ema_slow) / robust_vol``
    - ``accel_4_16[t] = ewmac_4_16[t] - ewmac_4_16[t - 4]`` (0.0 for ``t < 4``)
    """
    import numpy as np
    import pandas as pd

    n = len(closes)
    if n == 0:
        return [], [], [], []
    s_close = pd.Series([float(x) for x in closes], dtype="float64")
    diff = s_close.diff()
    raw_vol = diff.ewm(span=35, adjust=True, min_periods=1).std()
    if use_bfill:
        filled_vol = raw_vol.bfill().fillna(s_close.abs() * 0.02)
    else:
        filled_vol = raw_vol.ffill().fillna(s_close.abs() * 0.02)
    r_vol = np.maximum(np.maximum(filled_vol, s_close.abs() * 0.005), 1e-9)

    ema4 = s_close.ewm(span=4, adjust=True, min_periods=1).mean()
    ema16 = s_close.ewm(span=16, adjust=True, min_periods=1).mean()
    ema64 = s_close.ewm(span=64, adjust=True, min_periods=1).mean()

    ew4_16 = (ema4 - ema16) / r_vol
    ew16_64 = (ema16 - ema64) / r_vol
    accel_4_16 = ew4_16.diff(4).fillna(0.0)

    return (
        r_vol.tolist(),
        ew4_16.tolist(),
        ew16_64.tolist(),
        accel_4_16.tolist(),
    )


def _compute_pst_ewmac_and_accel(
    klines_htf: Sequence[dict[str, Any]],
    up_to_idx: int,
) -> tuple[float, float, float]:
    """Compute Point-in-Time Carver (pysystemtrade) ewmac_4_16, ewmac_16_64, and accel_4_16 up to up_to_idx."""
    sub = klines_htf[: up_to_idx + 1]
    if len(sub) < 3:
        return 0.0, 0.0, 0.0

    closes = [float(b["close"]) for b in sub]
    _, ew4_16_list, ew16_64_list, accel_list = compute_canonical_pst_series(closes, use_bfill=False)
    return ew4_16_list[-1], ew16_64_list[-1], accel_list[-1]



def compute_fibonacci_levels(
    swing_high: float,
    impulse_low: float,
) -> FibonacciLevels:
    """Compute Fibonacci retracement and extension levels from Swing High (1.0) to Impulse Low (0.0)."""
    if swing_high <= impulse_low or impulse_low <= 0.0:
        raise ValueError("swing_high must be greater than impulse_low > 0")
    delta = swing_high - impulse_low
    return FibonacciLevels(
        level_1000=swing_high,
        level_0886=impulse_low + 0.886 * delta,
        level_0786=impulse_low + 0.786 * delta,
        level_0618=impulse_low + 0.618 * delta,
        level_0500=impulse_low + 0.500 * delta,
        level_0382=impulse_low + 0.382 * delta,
        level_0236=impulse_low + 0.236 * delta,
        level_0000=impulse_low,
        ext_1272=max(impulse_low * 0.05, swing_high - 1.272 * delta),
        ext_1618=max(impulse_low * 0.02, swing_high - 1.618 * delta),
        wave_range=delta,
    )


def detect_htf_reversal_wave(
    symbol: str,
    klines_htf: Sequence[dict[str, Any]],
    timeframe: Literal["4h", "1d"],
    config: FiboTrendShortConfig | None = None,
) -> SwingImpulseWave | None:
    """Detect a confirmed bearish reversal impulse wave on H4 or D1 closed klines."""
    cfg = config or FiboTrendShortConfig()
    n = len(klines_htf)
    if n < 6:
        return None

    lookback = min(n, cfg.swing_lookback_bars)
    offset = n - lookback
    window = list(klines_htf[-lookback:])
    w_len = len(window)

    best_wave: SwingImpulseWave | None = None
    if "accel_4_16" in klines_htf[-1]:
        cur_accel_4_16 = float(klines_htf[-1]["accel_4_16"])
    else:
        _, _, cur_accel_4_16 = _compute_pst_ewmac_and_accel(klines_htf, n - 1)

    right_bars = max(1, int(getattr(cfg, "swing_pivot_right_bars", 1)))
    left_bars = max(1, int(getattr(cfg, "swing_pivot_left_bars", 1)))

    for high_idx in range(w_len - 1 - right_bars, max(0, left_bars - 1), -1):
        swing_high = float(window[high_idx]["high"])
        if swing_high <= 0.0 or not math.isfinite(swing_high):
            continue

        if any(swing_high < float(window[high_idx - k]["high"]) for k in range(1, left_bars + 1) if high_idx - k >= 0):
            continue
        if any(swing_high < float(window[high_idx + k]["high"]) for k in range(1, right_bars + 1) if high_idx + k < w_len):
            continue

        abs_high_idx = offset + high_idx
        prior_start_idx = max(0, abs_high_idx - 24)
        # Strictly enforce t_low < t_high (exclude abs_high_idx so prior_low is strictly prior to swing_high)
        prior_slice = klines_htf[prior_start_idx:abs_high_idx]
        if not prior_slice:
            continue
        prior_low_rel = min(range(len(prior_slice)), key=lambda i: float(prior_slice[i]["low"]))
        prior_low_bar = prior_slice[prior_low_rel]
        abs_prior_low_idx = prior_start_idx + prior_low_rel
        prior_low = float(prior_low_bar["low"])
        if prior_low <= 0.0:
            continue
        prior_pump_pct = (swing_high - prior_low) / prior_low
        if prior_pump_pct < cfg.min_prior_pump_pct:
            continue

        post_peak_bars = window[high_idx + 1 :]
        if any(float(b["high"]) > swing_high * cfg.fibo_invalidation_level for b in post_peak_bars):
            continue

        rev_candidates = window[high_idx : min(w_len, high_idx + 3)]
        bearish_rev_bar = next(
            (b for b in rev_candidates if float(b["close"]) < float(b["open"])),
            None,
        )
        if bearish_rev_bar is None:
            continue

        low_idx_rel = min(
            range(high_idx + 1, w_len),
            key=lambda idx: float(window[idx]["low"]),
        )

        impulse_low = float(window[low_idx_rel]["low"])
        if impulse_low <= 0.0 or impulse_low >= swing_high:
            continue

        impulse_drop_pct = (swing_high - impulse_low) / swing_high
        if impulse_drop_pct < cfg.min_impulse_drop_pct:
            continue

        # Compute Factor #1 & Factor #2 Orthogonal Physics (KER & pysystemtrade EWMAC/Accel)
        pump_wave_bars = klines_htf[abs_prior_low_idx : abs_high_idx + 1]
        wave_ker = _compute_ker_from_closes([float(b["close"]) for b in pump_wave_bars])

        abs_imp_low_idx = offset + low_idx_rel
        imp_wave_bars = klines_htf[abs_high_idx : abs_imp_low_idx + 1]
        impulse_ker = _compute_ker_from_closes([float(b["close"]) for b in imp_wave_bars])

        if "ewmac_16_64" in window[high_idx]:
            peak_ewmac_16_64 = float(window[high_idx]["ewmac_16_64"])
        else:
            _, peak_ewmac_16_64, _ = _compute_pst_ewmac_and_accel(klines_htf, abs_high_idx)

        pst_pass = (peak_ewmac_16_64 <= 0.0) or (cur_accel_4_16 <= -1.0)

        # Optional Hard Gates from 4-Factor Architecture
        if cfg.min_wave_ker > 0.0 and wave_ker < cfg.min_wave_ker:
            continue
        if cfg.min_impulse_ker > 0.0 and impulse_ker < cfg.min_impulse_ker:
            continue
        if cfg.enable_pst_gate and not (pst_pass or wave_ker >= 0.65):
            continue

        wave = SwingImpulseWave(
            symbol=symbol,
            timeframe=timeframe,
            prior_low_price=prior_low,
            prior_low_time=str(prior_low_bar.get("open_time_str") or prior_low_bar.get("open_time")),
            prior_pump_pct=round(prior_pump_pct, 6),
            swing_high_price=swing_high,
            swing_high_time=str(window[high_idx].get("open_time_str") or window[high_idx].get("open_time")),
            reversal_candle_time=str(bearish_rev_bar.get("open_time_str") or bearish_rev_bar.get("open_time")),
            reversal_candle_open=float(bearish_rev_bar["open"]),
            reversal_candle_close=float(bearish_rev_bar["close"]),
            reversal_candle_bearish=True,
            impulse_low_price=impulse_low,
            impulse_low_time=str(window[low_idx_rel].get("open_time_str") or window[low_idx_rel].get("open_time")),
            impulse_drop_pct=round(impulse_drop_pct, 6),
            bars_since_swing_high=(w_len - 1) - high_idx,
            bars_since_impulse_low=(w_len - 1) - low_idx_rel,
            wave_ker=round(wave_ker, 4),
            impulse_ker=round(impulse_ker, 4),
            peak_ewmac_16_64=round(peak_ewmac_16_64, 4),
            cur_accel_4_16=round(cur_accel_4_16, 4),
            pst_pass=bool(pst_pass),
        )
        best_wave = wave
        break

    return best_wave


def evaluate_h1_confirmation(
    klines_1h: Sequence[dict[str, Any]],
    fibo: FibonacciLevels,
    wave: SwingImpulseWave,
    config: FiboTrendShortConfig | None = None,
) -> H1ConfirmationResult:
    """Evaluate the latest closed H1 candle for bearish reversal confirmation at Fibonacci levels."""
    cfg = config or FiboTrendShortConfig()
    if len(klines_1h) < 3:
        raise ValueError("At least 3 closed H1 klines are required for confirmation")

    curr = klines_1h[-1]
    prev = klines_1h[-2]

    c_open = float(curr["open"])
    c_high = float(curr["high"])
    c_low = float(curr["low"])
    c_close = float(curr["close"])

    p_open = float(prev["open"])
    p_high = float(prev["high"])
    p_low = float(prev["low"])
    p_close = float(prev["close"])

    recent_1h = list(klines_1h[-16:])
    min_idx = min(range(len(recent_1h)), key=lambda i: float(recent_1h[i]["low"]))
    pullback_leg = recent_1h[min_idx:]
    has_upward_pullback = min_idx < len(recent_1h) - 1

    # Pullback volume ratio (Factor #3C: Liquidity Dry-Up on Pullback)
    pb_bars_only = recent_1h[min_idx + 1 :] or [recent_1h[-1]]
    drop_bars_only = recent_1h[: min_idx + 1] or [recent_1h[0]]
    pb_mean_vol = sum(float(b.get("volume", 0.0)) for b in pb_bars_only) / max(1, len(pb_bars_only))
    drop_mean_vol = sum(float(b.get("volume", 0.0)) for b in drop_bars_only) / max(1, len(drop_bars_only))
    pullback_vol_ratio = pb_mean_vol / drop_mean_vol if drop_mean_vol > 1e-9 else 1.0

    recent_max_high = max(float(b["high"]) for b in pullback_leg)
    recent_last_3_high = max(float(b["high"]) for b in pullback_leg[-3:])

    delta = fibo.wave_range
    current_fibo_ratio = (c_close - fibo.level_0000) / delta if delta > 0 else 0.0
    max_pullback_fibo_ratio = (recent_max_high - fibo.level_0000) / delta if delta > 0 else 0.0
    last_3_fibo_ratio = (recent_last_3_high - fibo.level_0000) / delta if delta > 0 else 0.0

    entry_min_price = fibo.level_0000 + cfg.fibo_entry_min * delta
    watch_max_price = fibo.level_0000 + cfg.fibo_watch_max * delta
    invalidation_price = fibo.level_0000 + cfg.fibo_invalidation_level * delta

    touched_fibo_zone = (
        has_upward_pullback
        and recent_last_3_high >= entry_min_price
        and recent_max_high <= invalidation_price
        and c_close >= fibo.level_0382
        and c_close <= watch_max_price
    )

    is_red_candle = c_close < c_open
    price_ret_1h = (c_close - p_close) / p_close if p_close > 0 else 0.0
    candle_ret_1h = (c_close - c_open) / c_open if c_open > 0 else 0.0
    no_gain_1h = is_red_candle and price_ret_1h <= 0.0 and candle_ret_1h < 0.0

    c_body = abs(c_open - c_close)
    c_range = max(1e-12, c_high - c_low)
    c_upper_wick = c_high - max(c_open, c_close)
    p_body = abs(p_open - p_close)
    h1_body_ratio = c_body / c_range

    is_bearish_engulfing = (
        is_red_candle
        and c_open >= min(p_open, p_close)
        and c_close < min(p_open, p_close)
        and c_body >= 0.8 * p_body
    )
    is_shooting_star = (
        is_red_candle
        and c_upper_wick >= 1.2 * max(c_body, c_range * 0.1)
        and c_upper_wick >= 0.35 * c_range
        and (c_close - c_low) <= 0.55 * c_range
    )
    is_strong_rejection = (
        is_red_candle
        and c_high >= entry_min_price
        and (c_body / c_range) >= 0.55
    )

    cond1_bearish_pattern = bool(
        is_bearish_engulfing or is_shooting_star or is_strong_rejection
    )
    if is_bearish_engulfing:
        pattern_name = "BEARISH_ENGULFING"
        pattern_name_vi = "Nhấn chìm giảm (Bearish Engulfing H1)"
    elif is_shooting_star:
        pattern_name = "SHOOTING_STAR_PINBAR"
        pattern_name_vi = "Pinbar / Shooting Star từ chối Fibo H1"
    elif is_strong_rejection:
        pattern_name = "STRONG_BEARISH_REJECTION"
        pattern_name_vi = "Nến đỏ thân đặc từ chối vùng Fibo H1"
    else:
        pattern_name = "NONE"
        pattern_name_vi = "Chưa có mẫu hình nến đảo chiều H1"

    broke_prev_low = is_red_candle and c_close < p_low
    broke_below_fibo_05 = (
        is_red_candle
        and recent_last_3_high >= entry_min_price
        and c_close < entry_min_price
    )
    cond2_break_prev_low = bool(broke_prev_low or broke_below_fibo_05)
    if broke_prev_low and broke_below_fibo_05:
        break_description_vi = "Đóng nến H1 thủng đáy nến H1 trước & gãy mốc Fibo 0.5"
    elif broke_prev_low:
        break_description_vi = "Đóng nến H1 phá vỡ đáy cây nến H1 liền trước"
    elif broke_below_fibo_05:
        break_description_vi = "Đóng nến H1 gãy xuống dưới ngưỡng Fibo 0.500"
    else:
        break_description_vi = "Chưa phá vỡ đáy nến H1 trước"

    if cfg.require_both_h1_conditions:
        trigger_ok = cond1_bearish_pattern and cond2_break_prev_low
    else:
        trigger_ok = cond1_bearish_pattern or cond2_break_prev_low

    confirmed = bool(touched_fibo_zone and no_gain_1h and trigger_ok)

    if confirmed and cond1_bearish_pattern and cond2_break_prev_low:
        confirmation_tier: ConfirmationTier = "COMBO_1_2"
        reason_vi = (
            f"Xác nhận kép H1 (1+2): {pattern_name_vi} + {break_description_vi}, "
            f"giá không tăng trong 1h ({price_ret_1h * 100:.2f}%)"
        )
    elif confirmed and cond1_bearish_pattern:
        confirmation_tier = "CANDLE_PATTERN_1"
        reason_vi = (
            f"Xác nhận H1 (ĐK1): {pattern_name_vi}, "
            f"giá không tăng trong 1h ({price_ret_1h * 100:.2f}%)"
        )
    elif confirmed and cond2_break_prev_low:
        confirmation_tier = "BREAK_STRUCTURE_2"
        reason_vi = (
            f"Xác nhận H1 (ĐK2): {break_description_vi}, "
            f"giá không tăng trong 1h ({price_ret_1h * 100:.2f}%)"
        )
    else:
        confirmation_tier = "UNCONFIRMED"
        if not touched_fibo_zone:
            reason_vi = (
                f"Giá hiện tại ở Fibo {current_fibo_ratio:.3f} (đỉnh hồi {last_3_fibo_ratio:.3f}), "
                f"chờ chạm vùng Fibo {cfg.fibo_entry_min:.3f}–{cfg.fibo_entry_max:.3f}"
            )
        elif not no_gain_1h:
            reason_vi = (
                f"Đã chạm vùng Fibo nhưng nến H1 chưa đóng đỏ giảm "
                f"(biến động 1h: {price_ret_1h * 100:+.2f}%)"
            )
        else:
            reason_vi = "Nến H1 đóng đỏ nhưng chưa tạo mẫu hình từ chối hoặc phá đáy nến H1 trước"

    return H1ConfirmationResult(
        candle_time=str(curr.get("open_time_str") or curr.get("open_time")),
        open=c_open,
        high=c_high,
        low=c_low,
        close=c_close,
        is_red_candle=is_red_candle,
        no_gain_1h=no_gain_1h,
        price_ret_1h=round(price_ret_1h, 6),
        touched_fibo_zone=touched_fibo_zone,
        max_pullback_fibo_ratio=round(max_pullback_fibo_ratio, 4),
        current_fibo_ratio=round(current_fibo_ratio, 4),
        cond1_bearish_pattern=cond1_bearish_pattern,
        pattern_name=pattern_name,
        pattern_name_vi=pattern_name_vi,
        cond2_break_prev_low=cond2_break_prev_low,
        break_description_vi=break_description_vi,
        confirmed=confirmed,
        confirmation_tier=confirmation_tier,
        reason_vi=reason_vi,
        pullback_vol_ratio=round(pullback_vol_ratio, 4),
        h1_body_ratio=round(h1_body_ratio, 4),
    )


def build_fibo_trade_setup(
    fibo: FibonacciLevels,
    current_price: float,
    atr_1h: float,
    confirmed: bool,
    config: FiboTrendShortConfig | None = None,
    conviction_tier: str = "B",
    recommended_risk_mult: float = 1.0,
) -> FiboTradeSetup:
    """Calculate Entry, Stop Loss, TP1 (0.0), TP2 (Ext 1.272), TP3 (Ext 1.618) and R:R ratios."""
    cfg = config or FiboTrendShortConfig()
    delta = fibo.wave_range
    entry_zone_low = fibo.level_0000 + cfg.fibo_entry_min * delta
    entry_zone_high = fibo.level_0000 + cfg.fibo_entry_max * delta

    entry_price = current_price if confirmed else 0.5 * (entry_zone_low + entry_zone_high)

    safe_atr = atr_1h if atr_1h > 0 else 0.005 * entry_price
    if cfg.sl_mode == "above_0786":
        stop_loss = max(fibo.level_0786, entry_price * 1.005) + cfg.sl_atr_buffer * safe_atr
    elif cfg.sl_mode == "above_0886":
        lvl_0886 = fibo.level_0886 if fibo.level_0886 > 0 else (fibo.level_0000 + 0.886 * delta)
        stop_loss = max(lvl_0886, entry_price * 1.005) + cfg.sl_atr_buffer * safe_atr
    else:
        stop_loss = max(fibo.level_1000, entry_price * 1.005) + cfg.sl_atr_buffer * safe_atr

    tp1 = fibo.level_0000
    tp2 = fibo.ext_1272
    tp3 = fibo.ext_1618

    sl_risk = max(1e-9, stop_loss - entry_price)
    stop_loss_pct = (sl_risk / entry_price) * 100.0
    tp1_pct = max(0.0, (entry_price - tp1) / entry_price * 100.0)
    tp2_pct = max(0.0, (entry_price - tp2) / entry_price * 100.0)
    tp3_pct = max(0.0, (entry_price - tp3) / entry_price * 100.0)

    rr_tp1 = max(0.0, (entry_price - tp1) / sl_risk)
    rr_tp2 = max(0.0, (entry_price - tp2) / sl_risk)
    rr_tp3 = max(0.0, (entry_price - tp3) / sl_risk)

    lvl_0886 = fibo.level_0886 if fibo.level_0886 > 0 else (fibo.level_0000 + 0.886 * delta)
    sl_m6 = max(lvl_0886, entry_price * 1.005) + cfg.m6_sl_atr_buffer * safe_atr
    sl_m6_risk = max(1e-9, sl_m6 - entry_price)
    sl_m6_pct = (sl_m6_risk / entry_price) * 100.0
    rr_m6_tp1 = max(0.0, (entry_price - tp1) / sl_m6_risk)
    rr_m6_tp2 = max(0.0, (entry_price - tp2) / sl_m6_risk)

    # v4.0.21 Risk-Based Position Sizing: min(20% NAV, 0.5% NAV / SL_with_cost%)
    # Standard VIP6 round-trip cost is ~25 bps (2.5 bps fee + 10 bps slip per side) = 0.25%
    effective_sl_pct = max(0.25, sl_m6_pct + 0.25)
    recommended_notional_pct = min(20.0, 50.0 / effective_sl_pct)
    sl_within_cap = bool(sl_m6_pct <= 12.0)

    return FiboTradeSetup(
        entry_price=entry_price,
        entry_zone_low=entry_zone_low,
        entry_zone_high=entry_zone_high,
        entry_zone_str=f"{_format_price(entry_zone_low)} - {_format_price(entry_zone_high)} (Fibo {cfg.fibo_entry_min:.3f}–{cfg.fibo_entry_max:.3f})",
        stop_loss=stop_loss,
        stop_loss_pct=stop_loss_pct,
        tp1=tp1,
        tp1_pct=tp1_pct,
        tp2=tp2,
        tp2_pct=tp2_pct,
        tp3=tp3,
        tp3_pct=tp3_pct,
        rr_tp1=rr_tp1,
        rr_tp2=rr_tp2,
        rr_tp3=rr_tp3,
        atr_1h=safe_atr,
        conviction_tier=conviction_tier,
        recommended_risk_mult=recommended_risk_mult,
        sl_m6=sl_m6,
        sl_m6_pct=sl_m6_pct,
        rr_m6_tp1=rr_m6_tp1,
        rr_m6_tp2=rr_m6_tp2,
        recommended_notional_pct=recommended_notional_pct,
        risk_budget_pct=0.5,
        max_notional_pct=20.0,
        sl_within_cap=sl_within_cap,
        max_hold_hours=cfg.horizon_hours,
    )


def evaluate_policy_family_v421(
    wave: SwingImpulseWave,
    h1_conf: H1ConfirmationResult,
    setup: FiboTradeSetup,
) -> tuple[list[str], list[str], str]:
    """Evaluate v4.0.21 5-milestone progression and 6-policy family admission for a signal."""
    imp_drop_pct = wave.impulse_drop_pct * 100.0 if wave.impulse_drop_pct < 2.0 else wave.impulse_drop_pct
    f1_elite = bool(wave.pst_pass and (wave.wave_ker >= 0.35))
    f1_expanded = bool(f1_elite or (wave.wave_ker >= 0.65))
    cond2_break = bool(h1_conf.cond2_break_prev_low)
    max_fibo_ratio = float(h1_conf.max_pullback_fibo_ratio)

    eligible_milestones: list[str] = ["m1_f1a_pump50"]
    if imp_drop_pct >= 6.0 and wave.impulse_ker >= 0.50:
        if f1_elite:
            eligible_milestones.append("m4_f2_elite")
        if f1_expanded:
            eligible_milestones.append("m6_f4_expanded")
        if f1_expanded and cond2_break and max_fibo_ratio <= 0.786:
            eligible_milestones.append("m6_f4_sniper")
        if f1_elite and cond2_break and max_fibo_ratio <= 0.786:
            eligible_milestones.append("m6_f4_elite_sniper")

    valid_ladder = bool(
        setup.sl_m6 > setup.entry_price > setup.tp1 > setup.tp2 > setup.tp3 > 0
        and setup.sl_within_cap
    )
    matched_policies: list[str] = []
    if valid_ladder and "m6_f4_expanded" in eligible_milestones:
        matched_policies.extend(["reference_m6_fixed", "m6_risk"])
        if "m6_f4_sniper" in eligible_milestones:
            matched_policies.extend(["sniper_risk", "sniper_horizon24"])
            if setup.rr_m6_tp1 >= 1.0:
                matched_policies.append("sniper_rr1_horizon24")
        if "m6_f4_elite_sniper" in eligible_milestones:
            matched_policies.append("elite_sniper_risk")

    if "sniper_rr1_horizon24" in matched_policies:
        primary_policy = "sniper_rr1_horizon24"
    elif "elite_sniper_risk" in matched_policies:
        primary_policy = "elite_sniper_risk"
    elif "sniper_risk" in matched_policies:
        primary_policy = "sniper_risk"
    elif "m6_risk" in matched_policies:
        primary_policy = "m6_risk"
    elif "m4_f2_elite" in eligible_milestones:
        primary_policy = "m4_f2_elite"
    else:
        primary_policy = "watch_only"

    return eligible_milestones, matched_policies, primary_policy


def compute_orthogonal_conviction_score(
    *,
    prior_pump_pct: float,
    impulse_drop_pct: float,
    fibo_retrace_ratio: float,
    wave_ker: float,
    impulse_ker: float,
    peak_ewmac_16_64: float,
    cur_accel_4_16: float,
    confirmation_tier: str,
    pullback_vol_ratio: float,
    h1_body_ratio: float,
    config: FiboTrendShortConfig | None = None,
) -> tuple[float, str, float, dict[str, float]]:
    """Compute canonical 4-Factor Orthogonal Conviction Score [0..100], tier (S/A/B/C), and risk multiplier.

    Unified across specification, research executor, and detector/scanner:
    - Layer 1 (Max 25 pts): Prior Pump Exhaustion (max 20) + Deep Fibo Retracement Bonus (max 5)
    - Layer 2 (Max 30 pts): Wave KER (max 15) + Impulse KER & Drop (max 15)
    - Layer 3 (Max 25 pts): Carver EWMAC(16,64) & Accel(4,16) Momentum Collapse
    - Layer 4 (Max 20 pts): H1 Confirmation Tier (max 12) + Pullback Volume/Body Quality (max 8)
    """
    cfg = config or FiboTrendShortConfig()
    pump_pct_100 = prior_pump_pct * 100.0 if prior_pump_pct < 10.0 else prior_pump_pct
    imp_drop_100 = impulse_drop_pct * 100.0 if impulse_drop_pct < 2.0 else impulse_drop_pct

    # Layer 1: F1A Exhaustion (max 25 pts)
    if pump_pct_100 >= 100.0:
        l1_score = 20.0
    elif pump_pct_100 >= 70.0:
        l1_score = 16.0
    elif pump_pct_100 >= 50.0:
        l1_score = 12.0
    else:
        l1_score = max(0.0, min(10.0, (pump_pct_100 / 50.0) * 10.0))

    if 0.618 <= fibo_retrace_ratio <= 0.786:
        l1_score += 5.0
    elif 0.500 <= fibo_retrace_ratio < 0.618:
        l1_score += 3.0

    # Layer 2: F1C + F2 Wave & Impulse Physics (max 30 pts)
    if wave_ker >= 0.65:
        l2_wave = 15.0
    elif wave_ker >= 0.45:
        l2_wave = 12.0
    elif wave_ker >= 0.35:
        l2_wave = 9.0
    else:
        l2_wave = 3.0

    if impulse_ker >= 0.75 and imp_drop_100 >= 8.0:
        l2_imp = 15.0
    elif impulse_ker >= 0.65 and imp_drop_100 >= 6.0:
        l2_imp = 12.0
    elif impulse_ker >= 0.50 and imp_drop_100 >= 6.0:
        l2_imp = 9.0
    else:
        l2_imp = 3.0

    # Layer 3: F1B Trend & Momentum Collapse (max 25 pts)
    if peak_ewmac_16_64 <= -2.0 and cur_accel_4_16 <= -1.5:
        l3_score = 25.0
    elif peak_ewmac_16_64 <= 0.0 and cur_accel_4_16 <= -1.0:
        l3_score = 21.0
    elif peak_ewmac_16_64 <= 0.0 or cur_accel_4_16 <= -1.0:
        l3_score = 16.0
    elif cur_accel_4_16 <= 0.0:
        l3_score = 8.0
    else:
        l3_score = 2.0

    # Layer 4: F3 Fibo Breakeven Wall & H1 Structure Break (max 20 pts)
    if confirmation_tier == "COMBO_1_2":
        l4_tier = 12.0
    elif confirmation_tier == "BREAK_STRUCTURE_2":
        l4_tier = 10.0
    else:
        l4_tier = 4.0

    if pullback_vol_ratio <= 0.75 and h1_body_ratio >= 0.60:
        l4_vol = 8.0
    elif pullback_vol_ratio <= 1.00 and h1_body_ratio >= 0.45:
        l4_vol = 6.0
    elif pullback_vol_ratio <= 1.25:
        l4_vol = 4.0
    else:
        l4_vol = 1.0

    l4_score = l4_tier + l4_vol
    score = round(min(100.0, max(0.0, l1_score + l2_wave + l2_imp + l3_score + l4_score)), 1)

    if score >= cfg.conviction_tier_s_threshold:
        conviction_tier = "S"
        recommended_risk_mult = cfg.conviction_mult_s if cfg.dynamic_conviction_sizing else 1.0
    elif score >= cfg.conviction_tier_a_threshold:
        conviction_tier = "A"
        recommended_risk_mult = cfg.conviction_mult_a if cfg.dynamic_conviction_sizing else 1.0
    elif score >= cfg.conviction_tier_b_threshold:
        conviction_tier = "B"
        recommended_risk_mult = cfg.conviction_mult_b if cfg.dynamic_conviction_sizing else 1.0
    else:
        conviction_tier = "C"
        if cfg.min_conviction_score >= cfg.conviction_tier_b_threshold:
            recommended_risk_mult = 0.0
        else:
            recommended_risk_mult = cfg.conviction_mult_c if cfg.dynamic_conviction_sizing else 1.0

    layers = {
        "L1_pump_exhaustion_pts": round(l1_score, 1),
        "L2_wave_impulse_physics_pts": round(l2_wave + l2_imp, 1),
        "L3_pst_momentum_collapse_pts": round(l3_score, 1),
        "L4_fibo_h1_trigger_pts": round(l4_score, 1),
        "wave_ker": wave_ker,
        "impulse_ker": impulse_ker,
        "peak_ewmac_16_64": peak_ewmac_16_64,
        "cur_accel_4_16": cur_accel_4_16,
        "pullback_vol_ratio": pullback_vol_ratio,
    }
    return score, conviction_tier, recommended_risk_mult, layers


def evaluate_symbol_timeframe(
    symbol: str,
    timeframe: Literal["4h", "1d"],
    klines_htf: Sequence[dict[str, Any]],
    klines_1h: Sequence[dict[str, Any]],
    config: FiboTrendShortConfig | None = None,
) -> FiboShortSignal | None:
    """Evaluate a symbol on (H4 or D1) + H1 confirmation and return a FiboShortSignal if a wave exists."""
    cfg = config or FiboTrendShortConfig()
    if len(klines_htf) < 6 or len(klines_1h) < 3:
        return None

    wave = detect_htf_reversal_wave(symbol, klines_htf, timeframe, cfg)
    if wave is None:
        return None

    fibo = compute_fibonacci_levels(wave.swing_high_price, wave.impulse_low_price)
    h1_conf = evaluate_h1_confirmation(klines_1h, fibo, wave, cfg)
    current_price = h1_conf.close
    atr_1h = compute_atr(klines_1h, period=14)

    score, conviction_tier, recommended_risk_mult, alpha_layers = compute_orthogonal_conviction_score(
        prior_pump_pct=wave.prior_pump_pct,
        impulse_drop_pct=wave.impulse_drop_pct,
        fibo_retrace_ratio=h1_conf.max_pullback_fibo_ratio,
        wave_ker=wave.wave_ker,
        impulse_ker=wave.impulse_ker,
        peak_ewmac_16_64=wave.peak_ewmac_16_64,
        cur_accel_4_16=wave.cur_accel_4_16,
        confirmation_tier=h1_conf.confirmation_tier,
        pullback_vol_ratio=h1_conf.pullback_vol_ratio,
        h1_body_ratio=h1_conf.h1_body_ratio,
        config=cfg,
    )

    if cfg.min_conviction_score > 0.0 and score < cfg.min_conviction_score:
        return None

    # Determine signal lifecycle stage
    if current_price > fibo.level_1000 * cfg.fibo_invalidation_level or h1_conf.max_pullback_fibo_ratio > cfg.fibo_invalidation_level:
        stage: SignalStage = "INVALIDATED"
    elif h1_conf.confirmed:
        stage = "FIRED_CONFIRMED_SHORT"
    elif (
        cfg.fibo_watch_min <= h1_conf.current_fibo_ratio <= cfg.fibo_watch_max
        or h1_conf.touched_fibo_zone
    ):
        stage = "ARMED_IN_FIBO_ZONE"
    else:
        stage = "WATCHING_PULLBACK"

    trade_setup = build_fibo_trade_setup(
        fibo=fibo,
        current_price=current_price,
        atr_1h=atr_1h,
        confirmed=(stage == "FIRED_CONFIRMED_SHORT"),
        config=cfg,
        conviction_tier=conviction_tier,
        recommended_risk_mult=recommended_risk_mult,
    )
    eligible_milestones, matched_policies, primary_policy = evaluate_policy_family_v421(
        wave=wave,
        h1_conf=h1_conf,
        setup=trade_setup,
    )
    alpha_layers["sl_m6"] = round(trade_setup.sl_m6, 8)
    alpha_layers["sl_m6_pct"] = round(trade_setup.sl_m6_pct, 4)
    alpha_layers["rr_m6_tp1"] = round(trade_setup.rr_m6_tp1, 2)
    alpha_layers["recommended_notional_pct"] = round(trade_setup.recommended_notional_pct, 2)
    alpha_layers["primary_policy"] = primary_policy

    explanation_vi = [
        f"Khung {timeframe.upper()}: Đã tạo đỉnh Swing High {_format_price(wave.swing_high_price)} (sau nhịp tăng +{wave.prior_pump_pct * 100:.1f}%, KER sóng bơm={wave.wave_ker:.2f}) và đóng nến đỏ đảo chiều sập -{wave.impulse_drop_pct * 100:.1f}% (KER nhịp sập={wave.impulse_ker:.2f}) về Impulse Low {_format_price(wave.impulse_low_price)}.",
        f"Fibonacci ({timeframe.upper()}): Golden Pocket (0.500–0.618) tại {_format_price(fibo.level_0500)} – {_format_price(fibo.level_0618)}. Giá hiện tại ở mốc Fibo {h1_conf.current_fibo_ratio:.3f} (đỉnh nhịp hồi đạt Fibo {h1_conf.max_pullback_fibo_ratio:.3f}, Vol hồi/sập={h1_conf.pullback_vol_ratio:.2f}x).",
        f"Xác nhận H1: {h1_conf.reason_vi}. Điểm hội tụ 4 tầng: {score:.1f}/100 (Hạng {conviction_tier} — Chính sách v4.0.21: {primary_policy} | Khối lượng khuyến nghị: {trade_setup.recommended_notional_pct:.1f}% NAV, rủi ro 0.5% NAV).",
        f"Kế hoạch Short: Entry {_format_price(trade_setup.entry_price)} | SL Mốc 6 (0.886) {_format_price(trade_setup.sl_m6)} (+{trade_setup.sl_m6_pct:.2f}%) | SL Đỉnh {_format_price(trade_setup.stop_loss)} (+{trade_setup.stop_loss_pct:.2f}%) | TP1 {_format_price(trade_setup.tp1)} (-{trade_setup.tp1_pct:.2f}%) | TP2 {_format_price(trade_setup.tp2)} (-{trade_setup.tp2_pct:.2f}%) | TP3 {_format_price(trade_setup.tp3)} (-{trade_setup.tp3_pct:.2f}%) | R:R(M6) = 1:{trade_setup.rr_m6_tp2:.2f}.",
    ]

    sig_key = f"{symbol}:{timeframe}:{wave.swing_high_time}:{wave.impulse_low_time}"
    sig_id = "fibo_" + hashlib.sha256(sig_key.encode("utf-8")).hexdigest()[:12]

    return FiboShortSignal(
        id=sig_id,
        symbol=symbol,
        higher_timeframe=timeframe,
        confirm_timeframe="1h",
        stage=stage,
        score=score,
        signal_time=h1_conf.candle_time,
        current_price=current_price,
        wave=wave,
        fibo_levels=fibo,
        h1_confirmation=h1_conf,
        trade_setup=trade_setup,
        explanation_vi=explanation_vi,
        conviction_tier=conviction_tier,
        recommended_risk_mult=recommended_risk_mult,
        alpha_layers=alpha_layers,
        eligible_milestones=eligible_milestones,
        matched_policies=matched_policies,
        primary_policy=primary_policy,
    )
