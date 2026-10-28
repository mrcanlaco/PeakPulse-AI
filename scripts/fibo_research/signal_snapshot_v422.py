"""Closed-bar signal snapshots; no simulated exits and no order submission.

Signal equations/configuration are extracted from the frozen v402 batch
collector. This is a research component, not a running paper-trading system.
PIT membership, lifecycle eligibility, scheduled fills and portfolio admission
remain separate decisions, made using information available at their time.
"""
from typing import Any
import numpy as np
import pandas as pd
from universe_reaudit_v402_worker import (
    FiboTrendShortConfig, UNIVERSE_MILESTONES, _check_milestone_gate,
    resample_1h_to_htf, calc_htf_features_no_bfill, detect_htf_reversal_wave,
    compute_fibonacci_levels, evaluate_h1_confirmation,
    compute_orthogonal_conviction_score, compute_atr, build_fibo_trade_setup,
)

BATCH_SOURCE_SHA256 = "4a37c395bf3d4aa24f20ce7f3525c4b313da0f639e70d9927f9fc3ef730a2deb"


def _collect_closed(
    symbol: str,
    df_1h: pd.DataFrame,
    btc_htf: dict[str, pd.DataFrame],
    *,
    entry_start_ts: pd.Timestamp,
    entry_end_ts: pd.Timestamp,
) -> list[dict[str, Any]]:
    """Same signal equations as the historical collector, including last H1."""
    cfg = FiboTrendShortConfig(
        swing_lookback_bars=30,
        swing_pivot_left_bars=2,
        swing_pivot_right_bars=2,
        conviction_mult_c=0.80,  # Same three-band M6 sizing as the benchmark executor.
        min_prior_pump_pct=0.50,
        min_impulse_drop_pct=0.04,
        fibo_entry_min=0.500,
        fibo_entry_max=0.618,
        sl_mode="above_swing_high",
        sl_atr_buffer=0.20,
        m6_sl_atr_buffer=0.25,
        require_both_h1_conditions=False,
    )

    if len(df_1h) < 100:
        return []

    idx_arr = df_1h.index
    opens = df_1h["open"].to_numpy(dtype=float)
    highs = df_1h["high"].to_numpy(dtype=float)
    lows = df_1h["low"].to_numpy(dtype=float)
    closes = df_1h["close"].to_numpy(dtype=float)
    vols = df_1h["volume"].to_numpy(dtype=float)

    h1_records: list[dict[str, Any]] = []
    h1_close_times: list[pd.Timestamp] = []
    hour_delta = pd.Timedelta(hours=1)
    for i in range(len(df_1h)):
        open_ts = idx_arr[i]
        close_ts = open_ts + hour_delta
        h1_close_times.append(close_ts)
        h1_records.append(
            {
                "open_time": int(open_ts.timestamp() * 1000),
                "open_time_str": open_ts.isoformat(),
                "close_time_ts": close_ts,
                "open": float(opens[i]),
                "high": float(highs[i]),
                "low": float(lows[i]),
                "close": float(closes[i]),
                "volume": float(vols[i]),
            }
        )

    raw_candidates: list[dict[str, Any]] = []

    for tf in ("4h", "1d"):
        htf_df = resample_1h_to_htf(df_1h, tf)
        if len(htf_df) < 30:
            continue
        htf_df = calc_htf_features_no_bfill(htf_df)

        htf_records: list[dict[str, Any]] = []
        htf_close_times: list[pd.Timestamp] = []
        for idx_htf, (open_ts, row) in enumerate(htf_df.iterrows()):
            c_ts = pd.Timestamp(row["close_time"])
            htf_close_times.append(c_ts)
            htf_records.append(
                {
                    "htf_idx": idx_htf,
                    "open_time": int(open_ts.timestamp() * 1000),
                    "open_time_str": open_ts.isoformat(),
                    "close_time_ts": c_ts,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0.0)),
                    "robust_vol": float(row["robust_vol"]),
                    "ewmac_4_16": float(row["ewmac_4_16"]),
                    "ewmac_16_64": float(row["ewmac_16_64"]),
                    "accel_4_16": float(row["accel_4_16"]),
                    "vol_ratio_20": float(row["vol_ratio_20"]),
                }
            )

        htf_by_open_str = {r["open_time_str"]: r for r in htf_records}
        htf_ptr = 0
        n_htf = len(htf_records)
        bdf = btc_htf[tf]
        btc_close_times = pd.to_datetime(bdf["close_time"])

        cached_htf_ptr = -1
        cached_wave = None
        cached_fibo = None
        cached_wave_meta: dict[str, Any] | None = None
        wave_eligible_milestones: list[str] = []
        entry_min_price_cached = 0.0

        for idx_1h in range(24, len(h1_records)):
            current_decision_ts = h1_close_times[idx_1h]
            while htf_ptr < n_htf and htf_close_times[htf_ptr] <= current_decision_ts:
                htf_ptr += 1

            bar_open_ts = idx_arr[idx_1h]
            if bar_open_ts < entry_start_ts or bar_open_ts > entry_end_ts:
                continue
            if htf_ptr < 10:
                continue

            if htf_ptr != cached_htf_ptr:
                cached_htf_ptr = htf_ptr
                start_htf = max(0, htf_ptr - cfg.swing_lookback_bars - 24)
                visible_htf = htf_records[start_htf:htf_ptr]
                cached_wave = detect_htf_reversal_wave(symbol, visible_htf, tf, cfg)
                cached_fibo = None
                cached_wave_meta = None
                wave_eligible_milestones = []
                if cached_wave is not None:
                    peak_bar_c = htf_by_open_str.get(cached_wave.swing_high_time)
                    low_bar_c = htf_by_open_str.get(cached_wave.prior_low_time)
                    imp_bar_c = htf_by_open_str.get(cached_wave.impulse_low_time)
                    cur_htf_bar_c = htf_records[htf_ptr - 1]
                    if peak_bar_c is not None and low_bar_c is not None and imp_bar_c is not None:
                        p_idx_c = int(peak_bar_c["htf_idx"])
                        l_idx_c = int(low_bar_c["htf_idx"])
                        imp_idx_c = int(imp_bar_c["htf_idx"])
                        if l_idx_c < p_idx_c:
                            cached_fibo = compute_fibonacci_levels(
                                cached_wave.swing_high_price,
                                cached_wave.impulse_low_price,
                            )
                            entry_min_price_cached = cached_fibo.level_0000 + cfg.fibo_entry_min * cached_fibo.wave_range
                            wave_bars_c = htf_records[l_idx_c : p_idx_c + 1]
                            if len(wave_bars_c) >= 2:
                                closes_w_c = np.array([b["close"] for b in wave_bars_c], dtype=float)
                                net_chg_c = abs(closes_w_c[-1] - closes_w_c[0])
                                path_chg_c = float(np.sum(np.abs(np.diff(closes_w_c))))
                                ker_wave_c = net_chg_c / path_chg_c if path_chg_c > 1e-9 else 0.0
                            else:
                                ker_wave_c = 0.0
                            pst_pass_c = (peak_bar_c["ewmac_16_64"] <= 0.0) or (cur_htf_bar_c["accel_4_16"] <= -1.0)
                            f1_elite_c = bool(pst_pass_c and (ker_wave_c >= 0.35))
                            f1_expanded_c = bool(f1_elite_c or (ker_wave_c >= 0.65))
                            sh_c = cached_wave.swing_high_price
                            il_c = cached_wave.impulse_low_price
                            imp_drop_pct_c = (max(0.0, sh_c - il_c) / sh_c) * 100.0
                            imp_slice_c = htf_records[p_idx_c : imp_idx_c + 1]
                            if len(imp_slice_c) >= 2:
                                closes_imp_c = np.array([b["close"] for b in imp_slice_c], dtype=float)
                                net_imp_c = abs(closes_imp_c[-1] - closes_imp_c[0])
                                path_imp_c = float(np.sum(np.abs(np.diff(closes_imp_c))))
                                imp_ker_c = net_imp_c / path_imp_c if path_imp_c > 1e-9 else 0.0
                            else:
                                imp_ker_c = 0.0
                            cached_wave_meta = {
                                "peak_bar": peak_bar_c,
                                "cur_htf_bar": cur_htf_bar_c,
                                "p_idx": p_idx_c,
                                "l_idx": l_idx_c,
                                "ker_wave": ker_wave_c,
                                "pst_pass": pst_pass_c,
                                "f1_elite": f1_elite_c,
                                "f1_expanded": f1_expanded_c,
                                "imp_drop_pct": imp_drop_pct_c,
                                "imp_ker": imp_ker_c,
                            }
                            wave_eligible_milestones = ["m1_f1a_pump50"]
                            if imp_drop_pct_c >= 6.0 and imp_ker_c >= 0.50:
                                if f1_expanded_c:
                                    wave_eligible_milestones.extend(["m6_f4_expanded", "m6_f4_sniper"])
                                if f1_elite_c:
                                    wave_eligible_milestones.extend(["m4_f2_elite", "m6_f4_elite_sniper"])

            if cached_wave is None or cached_fibo is None or cached_wave_meta is None:
                continue

            # Fast pre-filter before constructing visible_1h: H1 confirmation requires red candle, no 1h gain, and Fibo touch in last 3 bars
            if closes[idx_1h] >= opens[idx_1h] or closes[idx_1h] > closes[idx_1h - 1]:
                continue
            if max(highs[idx_1h], highs[idx_1h - 1], highs[idx_1h - 2]) < entry_min_price_cached:
                continue

            visible_1h = h1_records[max(0, idx_1h - 24) : idx_1h + 1]
            h1_conf = evaluate_h1_confirmation(visible_1h, cached_fibo, cached_wave, cfg)
            current_price = h1_conf.close
            if (
                current_price > cached_fibo.level_1000 * cfg.fibo_invalidation_level
                or h1_conf.max_pullback_fibo_ratio > cfg.fibo_invalidation_level
                or not h1_conf.confirmed
            ):
                continue

            peak_bar = cached_wave_meta["peak_bar"]
            cur_htf_bar = cached_wave_meta["cur_htf_bar"]
            p_idx = cached_wave_meta["p_idx"]
            l_idx = cached_wave_meta["l_idx"]
            ker_wave = cached_wave_meta["ker_wave"]
            pst_pass = cached_wave_meta["pst_pass"]
            f1_elite = cached_wave_meta["f1_elite"]
            f1_expanded = cached_wave_meta["f1_expanded"]
            imp_drop_pct = cached_wave_meta["imp_drop_pct"]
            imp_ker = cached_wave_meta["imp_ker"]

            eligible_milestones = [
                m
                for m in wave_eligible_milestones
                if _check_milestone_gate(
                    m,
                    f1_elite=f1_elite,
                    f1_expanded=f1_expanded,
                    imp_drop_pct=imp_drop_pct,
                    imp_ker=imp_ker,
                    cond2_break=h1_conf.cond2_break_prev_low,
                    max_fibo_ratio=h1_conf.max_pullback_fibo_ratio,
                )
            ]
            if not eligible_milestones:
                continue

            past_btc = bdf.loc[btc_close_times <= current_decision_ts]
            if len(past_btc) >= 5:
                last_btc = past_btc.iloc[-1]
                btc_ewmac_4_16 = float(last_btc["ewmac_4_16"])
                lb = min(len(past_btc) - 1, max(1, p_idx - l_idx))
                btc_ret_pct = float(
                    (last_btc["close"] - past_btc.iloc[-1 - lb]["close"])
                    / past_btc.iloc[-1 - lb]["close"]
                    * 100.0
                )
            else:
                btc_ewmac_4_16 = 0.0
                btc_ret_pct = 0.0

            raw_pump_pct = (
                cached_wave.prior_pump_pct * 100.0
                if cached_wave.prior_pump_pct < 10.0
                else cached_wave.prior_pump_pct
            )
            idiosyncratic_spread = raw_pump_pct - max(0.0, btc_ret_pct)

            legacy_score = 0.0
            if raw_pump_pct >= 100.0:
                legacy_score += 15.0
            elif raw_pump_pct >= 70.0:
                legacy_score += 11.0
            else:
                legacy_score += 7.0
            if ker_wave >= 0.65:
                legacy_score += 20.0
            elif ker_wave >= 0.35:
                legacy_score += 14.0
            if imp_ker >= 0.65 and imp_drop_pct >= 6.0:
                legacy_score += 15.0
            elif imp_ker >= 0.50 and imp_drop_pct >= 6.0:
                legacy_score += 10.0
            if peak_bar["ewmac_16_64"] <= 0.0 and cur_htf_bar["accel_4_16"] <= -1.0:
                legacy_score += 20.0
            elif pst_pass:
                legacy_score += 14.0
            if btc_ewmac_4_16 <= 0.5:
                legacy_score += 5.0
            if idiosyncratic_spread >= 60.0:
                legacy_score += 5.0
            if h1_conf.confirmation_tier == "COMBO_1_2":
                legacy_score += 12.0
            elif h1_conf.cond2_break_prev_low:
                legacy_score += 9.0
            else:
                legacy_score += 4.0
            if h1_conf.pullback_vol_ratio <= 1.1:
                legacy_score += 8.0
            elif h1_conf.pullback_vol_ratio <= 1.4:
                legacy_score += 4.0

            # Canonical 4-Factor Orthogonal Conviction Score (100% unified with detector.py)
            sc, conviction_tier, mult_m6, _ = compute_orthogonal_conviction_score(
                prior_pump_pct=cached_wave.prior_pump_pct,
                impulse_drop_pct=cached_wave.impulse_drop_pct,
                fibo_retrace_ratio=h1_conf.max_pullback_fibo_ratio,
                wave_ker=ker_wave,
                impulse_ker=imp_ker,
                peak_ewmac_16_64=float(peak_bar["ewmac_16_64"]),
                cur_accel_4_16=float(cur_htf_bar["accel_4_16"]),
                confirmation_tier=h1_conf.confirmation_tier,
                pullback_vol_ratio=h1_conf.pullback_vol_ratio,
                h1_body_ratio=h1_conf.h1_body_ratio,
                config=cfg,
            )

            atr_1h = compute_atr(visible_1h, period=14)
            setup = build_fibo_trade_setup(
                fibo=cached_fibo,
                current_price=current_price,
                atr_1h=atr_1h,
                confirmed=True,
                config=cfg,
                conviction_tier=conviction_tier,
                recommended_risk_mult=mult_m6,
            )
            ep = float(setup.entry_price)
            sl_std = float(setup.stop_loss)
            lvl_0886 = cached_fibo.level_0000 + 0.886 * cached_fibo.wave_range
            sl_m6 = max(lvl_0886, ep * 1.005) + cfg.m6_sl_atr_buffer * atr_1h

            wave_key = f"{tf}:{cached_wave.swing_high_time}:{cached_wave.impulse_low_time}"
            decision_ts_str = current_decision_ts.isoformat()
            entry_ym = f"{current_decision_ts.year:04d}-{current_decision_ts.month:02d}"

            raw_candidates.append(
                {
                    "symbol": symbol,
                    "tf": tf,
                    "idx_1h": idx_1h,
                    "wave_key": wave_key,
                    "eligible_milestones": eligible_milestones,
                    "signal_candle_open_time": h1_conf.candle_time,
                    "decision_time": decision_ts_str,
                    "decision_ts": current_decision_ts,
                    "year": int(current_decision_ts.year),
                    "entry_ym": entry_ym,
                    "confirmation_tier": h1_conf.confirmation_tier,
                    "pattern_name": h1_conf.pattern_name,
                    "entry_price": ep,
                    "sl_std": sl_std,
                    "sl_m6": sl_m6,
                    "tp1": float(setup.tp1),
                    "tp2": float(setup.tp2),
                    "tp3": float(setup.tp3),
                    "current_fibo_ratio": h1_conf.current_fibo_ratio,
                    "wave_impulse_drop_pct": cached_wave.impulse_drop_pct,
                    "wave_prior_pump_pct": cached_wave.prior_pump_pct,
                    "ker_wave": ker_wave,
                    "imp_ker": imp_ker,
                    "full_conviction_score": sc,
                    "conviction_tier": conviction_tier,
                    "mult_m6": mult_m6,
                    "legacy_btc_spread_score": round(legacy_score, 1),
                }
            )

    return raw_candidates


def _aware(value):
    value = pd.Timestamp(value)
    if value.tzinfo is None:
        raise ValueError('An explicit UTC-aware decision timestamp is required')
    return value.tz_convert('UTC')


def closed_signal_snapshots(symbol, hourly, btc_htf, *, as_of):
    """Evaluate only the latest completed H1; reject future/stale input.

    Output prices are signal references, never claimed executable fills. No
    portfolio/wave state is consumed here. All input frames must already be
    restricted to this timestamp and to one contract identity/episode.
    """
    t = _aware(as_of)
    if t != t.floor('h'):
        raise ValueError('Decision timestamp must be an H1 close boundary')
    if not isinstance(hourly.index, pd.DatetimeIndex) or hourly.index.tz is None:
        raise ValueError('H1 input requires a timezone-aware DatetimeIndex')
    if not hourly.index.is_unique or not hourly.index.is_monotonic_increasing:
        raise ValueError('H1 candles must be unique and chronological')
    if not (hourly.index == hourly.index.floor('h')).all():
        raise ValueError('H1 candles are off the hourly grid')
    if len(hourly) and (hourly.index + pd.Timedelta(hours=1) > t).any():
        raise ValueError('Unclosed or future H1 candle')
    for tf in ('4h', '1d'):
        b = btc_htf[tf]
        closed = pd.DatetimeIndex(b['close_time'])
        if len(closed) and (closed.tz is None or (closed > t).any()):
            raise ValueError('Unclosed or future BTC context')
    if not len(hourly) or hourly.index[-1] + pd.Timedelta(hours=1) != t:
        raise ValueError('Latest completed H1 is missing')
    values = hourly[['open', 'high', 'low', 'close', 'volume']].to_numpy()
    if not np.isfinite(values).all() or (values[:, :4] <= 0).any() or (values[:, 4] < 0).any():
        raise ValueError('Invalid H1 prices or volume')
    if ((hourly.high < hourly[['open', 'close', 'low']].max(axis=1)) |
        (hourly.low > hourly[['open', 'close', 'high']].min(axis=1))).any():
        raise ValueError('Invalid H1 OHLC ordering')
    expected = pd.date_range(t - pd.Timedelta(hours=24), periods=24, freq='h')
    if not hourly.index[-24:].equals(expected):
        return []
    raw = _collect_closed(symbol, hourly, btc_htf,
                          entry_start_ts=t-pd.Timedelta(hours=1),
                          entry_end_ts=t-pd.Timedelta(hours=1))
    assert all(pd.Timestamp(a['decision_time']) == t for a in raw)
    return raw
