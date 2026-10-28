from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from dao_vang.config.settings import FiboTrendShortConfig
from dao_vang.fibo_short.backtest import (
    IN_SAMPLE_MAX_UTC,
    backtest_symbol_1h_dataframe,
    enforce_in_sample_cutoff,
    resample_1h_to_htf,
    summarize_trades,
)
from dao_vang.fibo_short.detector import (
    build_fibo_trade_setup,
    compute_fibonacci_levels,
    detect_htf_reversal_wave,
    evaluate_h1_confirmation,
    evaluate_symbol_timeframe,
)


def _make_htf_reversal_candles(
    base_time: datetime,
    step_hours: int = 4,
) -> list[dict]:
    """Build a deterministic sequence of closed H4 candles showing:
    1) Prior uptrend from 100 -> 130 (+30% pump)
    2) Bearish reversal candle at Swing High = 130.0
    3) Downward impulse wave down to Impulse Low = 100.0 (-23.08% drop)
    4) Pullback into Fibo 0.500 - 0.618 (115.0 - 118.54) without breaking 130.0
    """
    candles: list[dict] = []
    t = base_time

    # Phase 1: 12 bars rising from 100 to 125
    price = 100.0
    for i in range(12):
        o = price
        c = price + 2.0
        h = c + 0.5
        l = o - 0.4
        candles.append(
            {
                "open_time": (t + timedelta(hours=i * step_hours)).isoformat(),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 1000.0,
            }
        )
        price = c

    # Bar 12: Swing High at 130.0 with Shooting Star / Bearish Reversal (open=125, high=130, low=121, close=122)
    candles.append(
        {
            "open_time": (t + timedelta(hours=12 * step_hours)).isoformat(),
            "open": 125.0,
            "high": 130.0,
            "low": 121.0,
            "close": 122.0,
            "volume": 2500.0,
        }
    )

    # Phase 2: Downward impulse wave from 122 down to 100.0 (Impulse Low = 100.0)
    down_steps = [
        (122.0, 122.5, 114.0, 115.0),
        (115.0, 116.0, 107.0, 108.0),
        (108.0, 109.0, 100.0, 101.5),  # Impulse low = 100.0
    ]
    for idx, (o, h, l, c) in enumerate(down_steps, start=13):
        candles.append(
            {
                "open_time": (t + timedelta(hours=idx * step_hours)).isoformat(),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 1800.0,
            }
        )

    # Phase 3: Pullback bars rising toward Golden Pocket (115.0 - 118.54)
    pullback_steps = [
        (101.5, 108.0, 101.0, 107.5),
        (107.5, 114.0, 107.0, 113.5),
        (113.5, 118.2, 113.0, 116.0),  # Inside Golden Pocket [115.0, 118.54]
    ]
    for idx, (o, h, l, c) in enumerate(pullback_steps, start=16):
        candles.append(
            {
                "open_time": (t + timedelta(hours=idx * step_hours)).isoformat(),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 1200.0,
            }
        )

    return candles


def test_compute_fibonacci_levels_and_trade_setup() -> None:
    """Verify exact Fibonacci retracement & extension math and SL/TP R:R setup."""
    fibo = compute_fibonacci_levels(swing_high=130.0, impulse_low=100.0)
    # Range = 30.0
    assert fibo.level_1000 == pytest.approx(130.0)
    assert fibo.level_0000 == pytest.approx(100.0)
    assert fibo.level_0500 == pytest.approx(115.0)
    assert fibo.level_0618 == pytest.approx(118.54)
    assert fibo.level_0786 == pytest.approx(123.58)
    assert fibo.level_0382 == pytest.approx(111.46)
    assert fibo.ext_1272 == pytest.approx(100.0 - 0.272 * 30.0)
    assert fibo.ext_1618 == pytest.approx(100.0 - 0.618 * 30.0)

    cfg = FiboTrendShortConfig()
    setup = build_fibo_trade_setup(
        fibo=fibo,
        current_price=116.0,
        atr_1h=1.5,
        confirmed=True,
        config=cfg,
    )
    assert setup is not None
    assert setup.stop_loss == pytest.approx(130.0 + 0.2 * 1.5)
    assert setup.tp1 == pytest.approx(100.0)
    assert setup.tp2 == pytest.approx(fibo.ext_1272)
    assert setup.tp3 == pytest.approx(fibo.ext_1618)
    assert setup.rr_tp1 > 1.0
    assert setup.rr_tp2 > setup.rr_tp1
    assert setup.rr_tp3 > setup.rr_tp2


def test_detect_htf_reversal_wave_valid_and_invalidated() -> None:
    """Verify H4 reversal wave detection and structure invalidation when Swing High is broken."""
    cfg = FiboTrendShortConfig(min_prior_pump_pct=0.08, min_impulse_drop_pct=0.04)
    base_time = datetime(2025, 5, 1, 0, 0, tzinfo=timezone.utc)
    htf_candles = _make_htf_reversal_candles(base_time, step_hours=4)

    wave = detect_htf_reversal_wave("SOLUSDT", htf_candles, timeframe="4h", config=cfg)
    assert wave is not None
    assert wave.reversal_candle_bearish is True
    assert wave.swing_high_price == pytest.approx(130.0)
    assert wave.impulse_low_price == pytest.approx(100.0)
    assert wave.prior_pump_pct >= 0.20
    assert wave.impulse_drop_pct >= 0.20

    # If a subsequent candle breaks above Swing High (130.0 * 1.005), the wave must be invalidated
    broken_candles = list(htf_candles) + [
        {
            "open_time": (base_time + timedelta(hours=20 * 4)).isoformat(),
            "open": 116.0,
            "high": 133.5,
            "low": 115.5,
            "close": 133.0,
            "volume": 2000.0,
        }
    ]
    invalidated = detect_htf_reversal_wave("SOLUSDT", broken_candles, timeframe="4h", config=cfg)
    assert invalidated is None


def test_evaluate_h1_confirmation_rule_1_plus_2() -> None:
    """Verify H1 confirmation requires:
    - Base rule: Red H1 candle (close < open) + price_ret_1h <= 0 in Fibo zone
    - Condition 1: Bearish reversal candle pattern (Engulfing / Shooting Star / Strong Rejection)
    - Condition 2: Close breaks below previous H1 low OR closes below Fibo 0.500 after Golden Pocket test
    """
    cfg = FiboTrendShortConfig(min_prior_pump_pct=0.08, min_impulse_drop_pct=0.04)
    base_time = datetime(2025, 5, 1, 0, 0, tzinfo=timezone.utc)
    htf_candles = _make_htf_reversal_candles(base_time, step_hours=4)
    wave = detect_htf_reversal_wave("SOLUSDT", htf_candles, timeframe="4h", config=cfg)
    assert wave is not None
    fibo = compute_fibonacci_levels(swing_high=wave.swing_high_price, impulse_low=wave.impulse_low_price)

    # Build H1 candles pulling back into Golden Pocket [115.0, 118.54]
    h1_candles = [
        {"open_time": "2025-05-03T08:00:00+00:00", "open": 112.0, "high": 114.5, "low": 111.8, "close": 114.0, "volume": 500.0},
        {"open_time": "2025-05-03T09:00:00+00:00", "open": 114.0, "high": 116.2, "low": 113.8, "close": 115.8, "volume": 600.0},
        # Previous H1 candle inside Golden Pocket: open=115.8, high=117.5, low=115.4, close=117.0 (green)
        {"open_time": "2025-05-03T10:00:00+00:00", "open": 115.8, "high": 117.5, "low": 115.4, "close": 117.0, "volume": 700.0},
        # Closed H1 confirmation candle: tests 118.2 (Golden Pocket), closes at 114.6 (red, engulfs prev body, breaks prev low 115.4 & Fibo 0.5=115.0)
        {"open_time": "2025-05-03T11:00:00+00:00", "open": 117.2, "high": 118.2, "low": 114.4, "close": 114.6, "volume": 1200.0},
    ]

    res = evaluate_h1_confirmation(h1_candles, fibo=fibo, wave=wave, config=cfg)
    assert res.is_red_candle is True
    assert res.no_gain_1h is True
    assert res.price_ret_1h <= 0.0
    assert res.touched_fibo_zone is True
    assert res.cond1_bearish_pattern is True
    assert res.pattern_name == "BEARISH_ENGULFING"
    assert res.cond2_break_prev_low is True
    assert res.confirmed is True
    assert res.confirmation_tier == "COMBO_1_2"

    # Green H1 candle must NEVER confirm
    green_h1 = list(h1_candles[:-1]) + [
        {"open_time": "2025-05-03T11:00:00+00:00", "open": 115.5, "high": 118.0, "low": 115.0, "close": 117.5, "volume": 900.0}
    ]
    res_green = evaluate_h1_confirmation(green_h1, fibo=fibo, wave=wave, config=cfg)
    assert res_green.is_red_candle is False
    assert res_green.confirmed is False


def test_strict_oos_2025_cutoff_guard() -> None:
    """Ensure backtest engine strictly rejects any end_utc > 2025-12-31 23:59:59 UTC (preserving 2026+ for OOS)."""
    valid_dt = enforce_in_sample_cutoff("2025-12-31T23:59:59+00:00")
    assert valid_dt == IN_SAMPLE_MAX_UTC

    with pytest.raises(ValueError, match="OOS_PROTECTION_VIOLATION"):
        enforce_in_sample_cutoff("2026-01-01T00:00:00+00:00")

    with pytest.raises(ValueError, match="OOS_PROTECTION_VIOLATION"):
        enforce_in_sample_cutoff("2026-06-15T12:00:00+00:00")


def test_point_in_time_no_lookahead_causality() -> None:
    """Verify that perturbing future candles after t0 does NOT change the signal at t0."""
    cfg = FiboTrendShortConfig(min_prior_pump_pct=0.08, min_impulse_drop_pct=0.04, min_rr_ratio=0.5)
    base_time = datetime(2025, 5, 1, 0, 0, tzinfo=timezone.utc)
    htf_candles = _make_htf_reversal_candles(base_time, step_hours=4)

    h1_at_t0 = [
        {"open_time": "2025-05-03T20:00:00+00:00", "open": 112.0, "high": 114.5, "low": 111.8, "close": 114.0, "volume": 500.0},
        {"open_time": "2025-05-03T21:00:00+00:00", "open": 114.0, "high": 116.2, "low": 113.8, "close": 115.8, "volume": 600.0},
        {"open_time": "2025-05-03T22:00:00+00:00", "open": 115.8, "high": 117.5, "low": 115.4, "close": 117.0, "volume": 700.0},
        {"open_time": "2025-05-03T23:00:00+00:00", "open": 117.2, "high": 118.2, "low": 114.4, "close": 114.6, "volume": 1200.0},
    ]

    sig_at_t0 = evaluate_symbol_timeframe(
        symbol="SOLUSDT",
        timeframe="4h",
        klines_htf=htf_candles,
        klines_1h=h1_at_t0,
        config=cfg,
    )
    assert sig_at_t0 is not None
    assert sig_at_t0.stage == "FIRED_CONFIRMED_SHORT"

    # Perturb future candles after t0 and slice up to t0
    future_crash = h1_at_t0 + [
        {"open_time": "2025-05-04T00:00:00+00:00", "open": 114.6, "high": 115.0, "low": 80.0, "close": 82.0, "volume": 9999.0}
    ]
    future_moon = h1_at_t0 + [
        {"open_time": "2025-05-04T00:00:00+00:00", "open": 114.6, "high": 200.0, "low": 114.0, "close": 195.0, "volume": 9999.0}
    ]

    sig_from_crash_prefix = evaluate_symbol_timeframe(
        symbol="SOLUSDT",
        timeframe="4h",
        klines_htf=htf_candles,
        klines_1h=future_crash[:-1],
        config=cfg,
    )
    sig_from_moon_prefix = evaluate_symbol_timeframe(
        symbol="SOLUSDT",
        timeframe="4h",
        klines_htf=htf_candles,
        klines_1h=future_moon[:-1],
        config=cfg,
    )

    assert sig_from_crash_prefix is not None
    assert sig_from_moon_prefix is not None
    assert sig_from_crash_prefix.to_dict() == sig_at_t0.to_dict()
    assert sig_from_moon_prefix.to_dict() == sig_at_t0.to_dict()


def test_backtest_symbol_1h_dataframe_and_summary() -> None:
    """Verify point-in-time backtest simulation on 1h dataframe strictly within 2025."""
    rows: list[dict] = []
    t0 = datetime(2025, 3, 1, 0, 0, tzinfo=timezone.utc)

    # 1) 48 hours flat/accumulation around 100
    price = 100.0
    for h in range(48):
        rows.append(
            {
                "open_time": t0 + timedelta(hours=h),
                "open": price,
                "high": price + 0.5,
                "low": price - 0.5,
                "close": price + 0.1,
                "volume": 500.0,
            }
        )

    # 2) 48 hours pump from 100 -> 130
    for h in range(48, 96):
        o = price
        c = price + 0.625
        rows.append(
            {
                "open_time": t0 + timedelta(hours=h),
                "open": o,
                "high": c + 0.3,
                "low": o - 0.2,
                "close": c,
                "volume": 1000.0,
            }
        )
        price = c

    # 3) 4 hours peak + shooting star reversal on 4h boundary (hours 96..99)
    peak_bars = [
        (130.0, 136.0, 129.5, 134.0),
        (134.0, 138.0, 128.0, 129.0),
        (129.0, 130.0, 125.0, 126.0),
        (126.0, 126.5, 122.0, 123.0),  # 4h bar open=130, high=138, low=122, close=123 (Shooting star + red)
    ]
    for offset, (o, h_val, l_val, c) in enumerate(peak_bars):
        rows.append(
            {
                "open_time": t0 + timedelta(hours=96 + offset),
                "open": o,
                "high": h_val,
                "low": l_val,
                "close": c,
                "volume": 2500.0,
            }
        )
    price = 123.0

    # 4) 16 hours downward impulse from 123 -> 100
    for h in range(100, 116):
        o = price
        c = max(100.5, price - 1.45)
        rows.append(
            {
                "open_time": t0 + timedelta(hours=h),
                "open": o,
                "high": o + 0.3,
                "low": min(100.0, c - 0.3),
                "close": c,
                "volume": 1500.0,
            }
        )
        price = c

    # 5) Pullback into Golden Pocket [119.0, 123.48] (for Swing High=138, Impulse Low=100)
    pullback_prices = [102, 105, 108, 111, 114, 116, 118, 120.5, 121.8, 122.5]
    for offset, target_c in enumerate(pullback_prices):
        o = price
        c = float(target_c)
        rows.append(
            {
                "open_time": t0 + timedelta(hours=116 + offset),
                "open": o,
                "high": c + 0.4,
                "low": o - 0.2,
                "close": c,
                "volume": 900.0,
            }
        )
        price = c

    # Trigger H1 Bearish Engulfing bar at hour 126
    rows.append(
        {
            "open_time": t0 + timedelta(hours=126),
            "open": 122.6,
            "high": 123.4,
            "low": 118.0,
            "close": 118.4,
            "volume": 2200.0,
        }
    )
    price = 118.4

    # 6) Subsequent 40 hours downtrend hitting TP1 (100.0) and TP2 (89.66)
    for h in range(127, 167):
        o = price
        c = max(82.0, price - 1.1)
        rows.append(
            {
                "open_time": t0 + timedelta(hours=h),
                "open": o,
                "high": o + 0.2,
                "low": c - 0.4,
                "close": c,
                "volume": 1600.0,
            }
        )
        price = c

    df_1h = pd.DataFrame(rows)
    htf_df = resample_1h_to_htf(df_1h, "4h")
    assert len(htf_df) > 20

    cfg = FiboTrendShortConfig(
        higher_timeframes=["4h"],
        min_prior_pump_pct=0.08,
        min_impulse_drop_pct=0.04,
        min_rr_ratio=0.6,
    )
    trades = backtest_symbol_1h_dataframe("TESTUSDT", df_1h, config=cfg)
    assert len(trades) >= 1
    first_trade = trades[0]
    assert first_trade.tp1_reached is True
    assert first_trade.net_return_pct > 0

    summary = summarize_trades(trades)
    assert summary["total_trades"] >= 1
    assert summary["win_rate_pct"] > 0


def test_four_factor_orthogonal_alpha_and_conviction_scoring() -> None:
    """Verify Factor 1-4 metrics (wave_ker, impulse_ker, level_0886 SL, conviction_tier, risk_mult)."""
    cfg = FiboTrendShortConfig(
        min_prior_pump_pct=0.08,
        min_impulse_drop_pct=0.04,
        min_wave_ker=0.35,
        min_impulse_ker=0.50,
        sl_mode="above_0886",
        dynamic_conviction_sizing=True,
    )
    base_time = datetime(2025, 5, 1, 0, 0, tzinfo=timezone.utc)
    htf_candles = _make_htf_reversal_candles(base_time, step_hours=4)
    h1_candles = [
        {"open_time": "2025-05-03T08:00:00+00:00", "open": 108.0, "high": 108.5, "low": 101.0, "close": 102.0, "volume": 1500.0},
        {"open_time": "2025-05-03T09:00:00+00:00", "open": 102.0, "high": 114.5, "low": 101.8, "close": 114.0, "volume": 500.0},
        {"open_time": "2025-05-03T10:00:00+00:00", "open": 114.0, "high": 117.5, "low": 113.8, "close": 117.0, "volume": 600.0},
        {"open_time": "2025-05-03T11:00:00+00:00", "open": 117.2, "high": 118.2, "low": 114.4, "close": 114.6, "volume": 700.0},
    ]

    sig = evaluate_symbol_timeframe(
        symbol="SOLUSDT",
        timeframe="4h",
        klines_htf=htf_candles,
        klines_1h=h1_candles,
        config=cfg,
    )
    assert sig is not None
    assert sig.stage == "FIRED_CONFIRMED_SHORT"
    assert sig.wave.wave_ker >= 0.35
    assert sig.wave.impulse_ker >= 0.50
    assert sig.fibo_levels.level_0886 == pytest.approx(100.0 + 0.886 * 30.0)
    assert sig.trade_setup.stop_loss < sig.fibo_levels.level_1000
    assert sig.conviction_tier in ("S", "A", "B")
    assert sig.recommended_risk_mult in (0.80, 1.15, 1.50)
    assert "L1_pump_exhaustion_pts" in sig.alpha_layers
    assert "L2_wave_impulse_physics_pts" in sig.alpha_layers


def test_coin_universe_tiered_selection_and_blacklist() -> None:
    """Verify select_candidate_symbols enforces Blacklist (BTC/ETH/BNB/PAXG/toxic) and prioritizes Tier S & Tier A."""
    from dao_vang.config.settings import AppSettings
    from dao_vang.fibo_short.scanner_lane import (
        load_fibo_universe_config,
        select_candidate_symbols,
    )

    u_cfg = load_fibo_universe_config()
    assert u_cfg.get("schema_version") == "1.2.0"
    assert len(u_cfg.get("tier_s_core", [])) == 40
    assert len(u_cfg.get("tier_a_extended", [])) == 28
    assert len(u_cfg.get("pit_zero_bias_mcap_float", [])) == 64
    assert "BTCUSDT" in u_cfg.get("blacklist_do_not_short", [])
    assert "ETHUSDT" in u_cfg.get("blacklist_do_not_short", [])
    assert "BNBUSDT" in u_cfg.get("blacklist_do_not_short", [])
    # Low-Float VC unlock traps (<64% float) and Small-Cap traps (<$150M MCap) must be blacklisted in v1.2
    assert "WLDUSDT" in u_cfg.get("blacklist_do_not_short", [])
    assert "AEROUSDT" in u_cfg.get("blacklist_do_not_short", [])
    assert "PUMPUSDT" in u_cfg.get("blacklist_do_not_short", [])
    assert "MINAUSDT" in u_cfg.get("blacklist_do_not_short", [])

    fake_tickers = [
        {"symbol": "BTCUSDT", "priceChangePercent": "15.0", "quoteVolume": "5000000000"},
        {"symbol": "ETHUSDT", "priceChangePercent": "12.0", "quoteVolume": "2500000000"},
        {"symbol": "SOLUSDT", "priceChangePercent": "-8.5", "quoteVolume": "800000000"},
        {"symbol": "1000PEPEUSDT", "priceChangePercent": "25.0", "quoteVolume": "600000000"},
        {"symbol": "1000SHIBUSDT", "priceChangePercent": "18.0", "quoteVolume": "750000000"},
        {"symbol": "DOGEUSDT", "priceChangePercent": "14.0", "quoteVolume": "900000000"},
    ]

    settings_s = AppSettings(
        fibo_trend_short=FiboTrendShortConfig(universe_mode="tier_s_only", max_candidates=25)
    )
    cands_s = select_candidate_symbols(settings_s, tickers_override=fake_tickers)
    assert "BTCUSDT" not in cands_s
    assert "ETHUSDT" not in cands_s
    assert "BNBUSDT" not in cands_s
    assert "1000PEPEUSDT" in cands_s
    assert "1000SHIBUSDT" in cands_s
    assert "SOLUSDT" in cands_s
    assert "DOGEUSDT" not in cands_s  # DOGEUSDT is in Tier A Extended
    # Top volatile Tier S symbols should rank first
    assert cands_s[0] == "1000PEPEUSDT"
    assert cands_s[1] == "1000SHIBUSDT"

    settings_sa = AppSettings(
        fibo_trend_short=FiboTrendShortConfig(universe_mode="tiered_whitelist", max_candidates=90)
    )
    cands_sa = select_candidate_symbols(settings_sa, tickers_override=fake_tickers)
    assert "BTCUSDT" not in cands_sa
    assert "WLDUSDT" not in cands_sa
    assert "DOGEUSDT" in cands_sa

    settings_pit = AppSettings(
        fibo_trend_short=FiboTrendShortConfig(universe_mode="pit_zero_bias_mcap_float", max_candidates=70)
    )
    cands_pit = select_candidate_symbols(settings_pit, tickers_override=fake_tickers)
    assert len(cands_pit) == 64
    assert "BTCUSDT" not in cands_pit
    assert "1000PEPEUSDT" in cands_pit
    assert "SOLUSDT" in cands_pit


def test_same_bar_ratcheted_sl_recheck_regression() -> None:
    """Regression test for Red-Team Audit Item 1.1:
    Short at 100, SL=110, TP=90/80/70.
    Bar 1: O=100, H=105, L=89, C=102 (hits TP1=90 for 50% -> +5% gross, ratchets SL to 100,
    and since H=105 >= 100 and C=102 >= 100, the remaining 50% must be stopped out at 100 in Bar 1).
    Bar 2: O=99, H=99, L=69, C=72 (must NOT be reached because trade already closed in Bar 1).
    """
    from dao_vang.fibo_short.backtest import _simulate_trade_outcome

    bars = [
        {"open": 100.0, "high": 105.0, "low": 89.0, "close": 102.0, "open_time_str": "2025-01-01T01:00:00+00:00"},
        {"open": 99.0, "high": 99.0, "low": 69.0, "close": 72.0, "open_time_str": "2025-01-01T02:00:00+00:00"},
    ]
    (
        outcome,
        exit_price,
        exit_time,
        hold_hours,
        tp1_hit,
        tp2_hit,
        tp3_hit,
        gross_pct,
        net_pct,
        r_mult,
    ) = _simulate_trade_outcome(
        bars,
        entry_price=100.0,
        stop_loss=110.0,
        tp1=90.0,
        tp2=80.0,
        tp3=70.0,
        round_trip_fee_bps=20.0,
    )
    assert outcome == "TP1_HIT"
    assert tp1_hit is True
    assert tp2_hit is False
    assert tp3_hit is False
    assert hold_hours == 1
    assert exit_price == pytest.approx(100.0)
    assert exit_time == "2025-01-01T01:00:00+00:00"
    assert gross_pct == pytest.approx(5.0)
    assert net_pct == pytest.approx(4.8)  # 5.0% - 0.20% (20 bps round-trip)


def test_prior_low_strictly_before_swing_high_and_ker_zero_on_single_bar() -> None:
    """Regression test for Red-Team Audit Item 2.2:
    1) _compute_ker_from_closes must return 0.0 (not 1.0) on <2 closes.
    2) prior_low must be selected strictly before swing_high (t_low < t_high), never on the swing_high bar itself.
    """
    from dao_vang.fibo_short.detector import _compute_ker_from_closes

    assert _compute_ker_from_closes([]) == 0.0
    assert _compute_ker_from_closes([100.0]) == 0.0
    assert _compute_ker_from_closes([100.0, 100.0]) == 0.0

    base_time = datetime(2025, 5, 1, 0, 0, tzinfo=timezone.utc)
    candles: list[dict] = []
    for i in range(12):
        candles.append(
            {
                "open_time": (base_time + timedelta(hours=i * 4)).isoformat(),
                "open": 95.5,
                "high": 96.0,
                "low": 95.0,
                "close": 95.5,
                "volume": 1000.0,
            }
        )
    # Bar 12: same-bar low=50, high=100, close=94 (red)
    candles.append(
        {
            "open_time": (base_time + timedelta(hours=12 * 4)).isoformat(),
            "open": 96.0,
            "high": 100.0,
            "low": 50.0,
            "close": 94.0,
            "volume": 2000.0,
        }
    )
    for idx, (o, h, l, c) in enumerate(
        [
            (94.0, 94.2, 88.0, 89.0),
            (89.0, 89.2, 84.0, 85.0),
            (85.0, 85.2, 80.0, 81.0),
            (81.0, 83.0, 80.5, 82.5),
        ],
        start=13,
    ):
        candles.append(
            {
                "open_time": (base_time + timedelta(hours=idx * 4)).isoformat(),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 1500.0,
            }
        )

    cfg = FiboTrendShortConfig(min_prior_pump_pct=0.50, min_impulse_drop_pct=0.06)
    wave = detect_htf_reversal_wave("FAKEUSDT", candles, timeframe="4h", config=cfg)
    assert wave is None


def test_reaudit_same_timestamp_cap_and_notional_risk_caps() -> None:
    """Regression test for Red-Team Re-Audit Item 3.1/3.2 (same_timestamp_cap & notional/risk caps):
    1) 6 trades arriving at the exact same timestamp with max_concurrent_cap=5 must accept 5 and reject 1.
    2) 5 trades with pos_mult=1.5 (notional=30% each) and max_total_notional_frac=1.0 must accept 3 (90% <= 100%) and reject 2.
    3) SL risk cap enforced simultaneously with slot and notional caps.
    """
    import sys
    from pathlib import Path

    scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts" / "fibo_research")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    from dao_vang.fibo_short.backtest import FiboBacktestTrade
    from verify_red_team_audit_2026 import compute_portfolio_nav_and_concurrency

    future_bars = [
        {"open": 100.0, "high": 101.0, "low": 98.0, "close": 99.0, "open_time_str": "2025-01-01T00:00:00+00:00"},
        {"open": 99.0, "high": 100.0, "low": 97.0, "close": 98.0, "open_time_str": "2025-01-01T01:00:00+00:00"},
    ]

    items_6 = []
    for k in range(6):
        t = FiboBacktestTrade(
            trade_id=f"T_{k}",
            symbol=f"SYM{k}USDT",
            higher_timeframe="4h",
            confirmation_tier="COMBO_1_2",
            pattern_name="ENGULFING",
            entry_time="2025-01-01T00:00:00+00:00",
            exit_time="2025-01-01T02:00:00+00:00",
            entry_price=100.0,
            stop_loss=110.0,
            tp1=80.0,
            tp2=70.0,
            tp3=60.0,
            exit_price=98.0,
            outcome="TIME_EXIT",
            tp1_reached=False,
            tp2_reached=False,
            tp3_reached=False,
            gross_return_pct=2.0,
            net_return_pct=1.8,
            r_multiple=0.18,
            hold_hours=2,
            fibo_entry_ratio=0.55,
            impulse_drop_pct=10.0,
            prior_pump_pct=60.0,
        )
        items_6.append({"trade": t, "future_slice": future_bars, "pos_mult": 1.0})

    res_cap5 = compute_portfolio_nav_and_concurrency(
        items_6,
        window_start_utc="2025-01-01T00:00:00+00:00",
        window_end_utc="2025-01-01T05:00:00+00:00",
        base_notional_weight=0.20,
        max_concurrent_cap=5,
    )
    nav_sim = res_cap5["nav_simulation_20pct_notional_per_1x"]
    assert nav_sim["executed_trades"] == 5
    assert nav_sim["skipped_due_to_cap"] == 1
    assert res_cap5["max_concurrent"] == 6  # Uncapped concurrency
    assert res_cap5["accepted_concurrency"]["max_concurrent"] == 5  # Accepted concurrency

    # Now test with pos_mult=1.5 (notional=0.30 per trade) and max_total_notional_frac=1.0
    items_mult15 = [{**x, "pos_mult": 1.5} for x in items_6[:5]]
    res_notional = compute_portfolio_nav_and_concurrency(
        items_mult15,
        window_start_utc="2025-01-01T00:00:00+00:00",
        window_end_utc="2025-01-01T05:00:00+00:00",
        base_notional_weight=0.20,
        max_concurrent_cap=5,
        max_total_notional_frac=1.0,
    )
    nav_notional = res_notional["nav_simulation_20pct_notional_per_1x"]
    assert nav_notional["executed_trades"] == 3  # 3 * 0.30 = 0.90 <= 1.0
    assert nav_notional["skipped_due_to_notional_cap"] == 2
    assert res_notional["accepted_concurrency"]["peak_open_notional_frac"] == pytest.approx(0.90)


def test_reaudit_round_trip_price_fixed_quantity_nav() -> None:
    """Regression test for Red-Team Re-Audit Item 3.1/3.2 (round_trip_price_fixed_quantity_nav):
    Initial NAV = 100, short at 100 with notional = 20 (base_notional_weight=0.20, pos_mult=1.0).
    Closes go 100 -> 50 -> 100 without hitting SL (150) or TP (10/8/5), round-trip fee = 20 bps.
    Trade gross return is 0%; fee on 20 notional is 0.04; final NAV must be 99.96 (-0.04%) for both
    Additive and Compounded NAV (no mid-trade rebalancing).
    """
    import sys
    from pathlib import Path

    scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts" / "fibo_research")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    from dao_vang.fibo_short.backtest import FiboBacktestTrade
    from verify_red_team_audit_2026 import compute_portfolio_nav_and_concurrency

    bars = [
        {"open": 100.0, "high": 100.0, "low": 50.0, "close": 50.0, "open_time_str": "2025-01-01T00:00:00+00:00"},
        {"open": 50.0, "high": 100.0, "low": 50.0, "close": 100.0, "open_time_str": "2025-01-01T01:00:00+00:00"},
    ]
    t = FiboBacktestTrade(
        trade_id="RT_1",
        symbol="SOLUSDT",
        higher_timeframe="4h",
        confirmation_tier="COMBO_1_2",
        pattern_name="ENGULFING",
        entry_time="2025-01-01T00:00:00+00:00",
        exit_time="2025-01-01T02:00:00+00:00",
        entry_price=100.0,
        stop_loss=150.0,
        tp1=10.0,
        tp2=8.0,
        tp3=5.0,
        exit_price=100.0,
        outcome="TIME_EXIT",
        tp1_reached=False,
        tp2_reached=False,
        tp3_reached=False,
        gross_return_pct=0.0,
        net_return_pct=-0.20,
        r_multiple=-0.004,
        hold_hours=2,
        fibo_entry_ratio=0.55,
        impulse_drop_pct=10.0,
        prior_pump_pct=60.0,
    )
    res = compute_portfolio_nav_and_concurrency(
        [{"trade": t, "future_slice": bars, "pos_mult": 1.0}],
        window_start_utc="2025-01-01T00:00:00+00:00",
        window_end_utc="2025-01-01T04:00:00+00:00",
        base_notional_weight=0.20,
        max_concurrent_cap=5,
        round_trip_fee_bps=20.0,
    )
    nav = res["nav_simulation_20pct_notional_per_1x"]
    assert nav["additive_nav_final"] == pytest.approx(99.96)
    assert nav["additive_nav_total_return_pct"] == pytest.approx(-0.04)
    assert nav["compounded_nav_final"] == pytest.approx(99.96)
    assert nav["compounded_nav_total_return_pct"] == pytest.approx(-0.04)


def test_reaudit_swing_pivot_right_bars_and_fee_bps_and_isolated_bfill() -> None:
    """Regression test for Red-Team Re-Audit Items 1.5, 2.1, 2.3, 2.4:
    1) FiboTrendShortConfig(swing_pivot_right_bars=2) is persisted on the Pydantic model and changes wave detection when peak has only 1 right bar.
    2) fee_bps=10.0 deducts 0.10% in both _simulate_trade_outcome and simulate_custom_trade.
    3) compute_canonical_pst_series(use_bfill=False) vs use_bfill=True isolates .bfill() vs .ffill() with zero divergence from bar index 2 onward.
    """
    import sys
    from pathlib import Path

    scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts" / "fibo_research")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    from dao_vang.fibo_short.backtest import _simulate_trade_outcome
    from dao_vang.fibo_short.detector import compute_canonical_pst_series
    from study_factor2_3_4_complete_2025 import simulate_custom_trade

    # 1. swing_pivot_right_bars in FiboTrendShortConfig
    cfg1 = FiboTrendShortConfig(min_prior_pump_pct=0.08, min_impulse_drop_pct=0.04, swing_pivot_right_bars=1)
    cfg2 = FiboTrendShortConfig(min_prior_pump_pct=0.08, min_impulse_drop_pct=0.04, swing_pivot_right_bars=2)
    assert cfg1.swing_pivot_right_bars == 1
    assert cfg2.swing_pivot_right_bars == 2

    # Construct candles where Swing High=130 is at index -2 (only 1 bar to the right, which is Impulse Low=100)
    base_time = datetime(2025, 5, 1, 0, 0, tzinfo=timezone.utc)
    full_candles = _make_htf_reversal_candles(base_time, step_hours=4)
    # Slice up to bar 13 (bar 12 is Swing High=130, bar 13 has low=100 so only 1 bar to the right of bar 12)
    short_right_candles = list(full_candles[:13]) + [
        {
            "open_time": (base_time + timedelta(hours=13 * 4)).isoformat(),
            "open": 122.0,
            "high": 122.5,
            "low": 100.0,
            "close": 116.0,
            "volume": 1800.0,
        }
    ]
    w_right1 = detect_htf_reversal_wave("SOLUSDT", short_right_candles, timeframe="4h", config=cfg1)
    w_right2 = detect_htf_reversal_wave("SOLUSDT", short_right_candles, timeframe="4h", config=cfg2)
    assert w_right1 is not None
    assert w_right2 is None  # Rejected when 2 right bars are required!

    # 2. fee_bps=10.0 unification
    bars = [
        {"open": 100.0, "high": 101.0, "low": 95.0, "close": 96.0, "open_time_str": "2025-01-01T00:00:00+00:00"},
    ]
    res_base = _simulate_trade_outcome(
        bars,
        entry_price=100.0,
        stop_loss=110.0,
        tp1=80.0,
        tp2=70.0,
        tp3=60.0,
        fee_bps=10.0,
    )
    res_cust = simulate_custom_trade(
        bars,
        entry_price=100.0,
        stop_loss=110.0,
        tp1=80.0,
        tp2=70.0,
        tp3=60.0,
        fee_bps=10.0,
        return_exit_meta=True,
    )
    # Gross is +4.0%, fee is 10 bps = 0.10%, so net is +3.90% in both!
    assert res_base[7] == pytest.approx(4.0)
    assert res_base[8] == pytest.approx(3.90)
    assert res_cust[1] == pytest.approx(4.0)
    assert res_cust[2] == pytest.approx(3.90)

    # 3. Isolated .bfill() vs .ffill() on canonical Carver series
    closes = [100.0 + (i * 1.5 if i % 2 == 0 else -0.8 * i) for i in range(40)]
    rvol_no, ew4_no, ew16_no, acc_no = compute_canonical_pst_series(closes, use_bfill=False)
    rvol_bf, ew4_bf, ew16_bf, acc_bf = compute_canonical_pst_series(closes, use_bfill=True)
    # From index 2 onward, raw_vol has >=2 diff observations so .bfill() and .ffill() are 100% identical
    for idx in range(2, len(closes)):
        assert rvol_no[idx] == pytest.approx(rvol_bf[idx], abs=1e-12)
        assert ew4_no[idx] == pytest.approx(ew4_bf[idx], abs=1e-12)
        assert ew16_no[idx] == pytest.approx(ew16_bf[idx], abs=1e-12)
    for idx in range(6, len(closes)):
        assert acc_no[idx] == pytest.approx(acc_bf[idx], abs=1e-12)


def test_v403_funding_loader_both_schemas_and_14_symbols(tmp_path) -> None:
    """Verify v4.0.3 fix for F-19b:
    1) parse_funding_dataframe handles both DatetimeIndex (SharedMarketData) and Series (data_lake) schemas,
       positive/negative funding rates, duplicate timestamps, sub-second jitter, and explicit error classifications.
    2) load_historical_funding_lookup loads all 14/14 benchmark symbols from disk with zero silent exceptions.
    """
    import sys
    from pathlib import Path
    import pandas as pd

    scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts" / "fibo_research")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    from verify_red_team_reaudit_v402 import load_historical_funding_lookup, parse_funding_dataframe

    # Schema A: DatetimeIndex (SharedMarketData style) with positive, negative, and duplicate timestamps
    idx_a = pd.DatetimeIndex(
        [
            "2025-01-01T00:00:00Z",
            "2025-01-01T08:00:00Z",
            "2025-01-01T08:00:00Z",  # duplicate
            "2025-01-01T16:00:00Z",
        ]
    )
    df_a = pd.DataFrame({"funding_rate": [0.0001, -0.0002, -0.0003, 0.00015], "symbol": "BTCUSDT"}, index=idx_a)
    diag_a = parse_funding_dataframe(df_a, source_label="schema_a_test")
    assert diag_a["status"] == "OK"
    assert diag_a["valid_unique_hours"] == 3
    assert diag_a["duplicate_timestamps"] == 1
    assert diag_a["positive_rates"] == 2
    assert diag_a["negative_rates"] == 1
    assert diag_a["missing_8h_slots_in_span"] == 0

    # Schema B: 'timestamp' column Series with sub-second jitter and missing 8h slot (08:00 missing)
    df_b = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2025-01-01T00:00:00.005Z", "2025-01-01T16:00:00.002Z"]),
            "funding_rate": [0.0001, -0.00005],
        }
    )
    diag_b = parse_funding_dataframe(df_b, source_label="schema_b_test")
    assert diag_b["status"] == "OK"
    assert diag_b["valid_unique_hours"] == 2
    assert diag_b["missing_8h_slots_in_span"] == 1  # 08:00 UTC slot missing between 00:00 and 16:00

    # Schema error classification
    df_bad = pd.DataFrame({"wrong_col": [1, 2, 3]})
    diag_bad = parse_funding_dataframe(df_bad, source_label="bad_schema")
    assert diag_bad["status"] == "SCHEMA_ERROR"

    # Empty dataframe classification
    df_empty = pd.DataFrame({"timestamp": pd.Series([], dtype="datetime64[ns, UTC]"), "funding_rate": pd.Series([], dtype=float)})
    diag_empty = parse_funding_dataframe(df_empty, source_label="empty_df")
    assert diag_empty["status"] == "NO_VALID_RECORDS"

    # Real 14-symbol historical funding lookup (when 5y research cache is mounted)
    benchmark_14 = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "LTCUSDT", "BCHUSDT",
        "1000PEPEUSDT", "1000BONKUSDT", "1000SHIBUSDT", "AAVEUSDT",
        "ADAUSDT", "1INCHUSDT", "ACEUSDT", "AKTUSDT",
    ]
    lookup, cov = load_historical_funding_lookup(benchmark_14)
    assert cov["read_errors_count"] == 0
    assert cov["schema_errors_count"] == 0
    if cov["total_files_found"] > 0:
        assert cov["symbols_with_funding_files"] == 14
        assert cov["total_files_found"] == 20
        assert cov["total_files_loaded_ok"] == 20
        assert cov["total_settlement_records_loaded"] > 50000


def test_v403_funding_schedule_no_settlement_between_8h_boundaries() -> None:
    """Reproduce audit counterexample `funding_no_settlement`:
    A short trade opened at 01:00 UTC and closed at 03:00 UTC (bars closing at 02:00 and 03:00 UTC)
    does NOT cross any 8h funding boundary (00:00, 08:00, 16:00 UTC).
    Even under stress funding (+1.0 bps/8h), funding charged must be 0.0 and final NAV = 100.0.
    Conversely, a trade spanning 07:00 -> 09:00 UTC (crossing 08:00 UTC) pays exactly 1 settlement.
    """
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    import pandas as pd

    scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts" / "fibo_research")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    from verify_red_team_audit_2026 import compute_portfolio_nav_and_concurrency, simulate_trade_v2

    # Case 1: 01:00 -> 03:00 UTC (no 8h boundary crossed)
    t_entry_1 = "2025-05-01T01:00:00+00:00"
    f_slice_1 = [
        {
            "open_time": int(pd.Timestamp("2025-05-01T01:00:00+00:00").timestamp() * 1000),
            "open_time_str": "2025-05-01T01:00:00+00:00",
            "close_time_ts": pd.Timestamp("2025-05-01T02:00:00+00:00"),
            "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000.0,
        },
        {
            "open_time": int(pd.Timestamp("2025-05-01T02:00:00+00:00").timestamp() * 1000),
            "open_time_str": "2025-05-01T02:00:00+00:00",
            "close_time_ts": pd.Timestamp("2025-05-01T03:00:00+00:00"),
            "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000.0,
        },
    ]
    sim_1 = simulate_trade_v2(
        f_slice_1, entry_price=100.0, stop_loss=150.0, tp1=10.0, tp2=8.0, tp3=5.0,
        round_trip_fee_bps=0.0, entry_timestamp_utc=pd.Timestamp(t_entry_1),
    )
    t_obj_1 = SimpleNamespace(
        trade_id="NO_SETTLE_1", symbol="SOLUSDT", higher_timeframe="4h",
        decision_time=t_entry_1, entry_time=t_entry_1, exit_time=sim_1["exit_close_time"],
        entry_price=100.0, stop_loss=150.0, hold_hours=sim_1["hold_hours"], net_return_pct=0.0,
    )
    res_1 = compute_portfolio_nav_and_concurrency(
        [{"trade": t_obj_1, "sim": sim_1, "pos_mult": 1.0, "full_conviction_score": 80.0}],
        window_start_utc="2025-05-01T00:00:00+00:00",
        window_end_utc="2025-05-01T05:00:00+00:00",
        base_notional_weight=0.20,
        funding_bps_per_8h=1.0,
        round_trip_fee_bps=0.0,
    )
    nav_1 = res_1["nav_simulation_20pct_notional_per_1x"]
    assert nav_1["stress_funding_events_charged"] == 0
    assert nav_1["stress_funding_net_pct_of_initial_nav"] == pytest.approx(0.0, abs=1e-12)
    assert nav_1["additive_final_nav"] == pytest.approx(100.0, abs=1e-12)
    assert nav_1["compounded_final_nav"] == pytest.approx(100.0, abs=1e-12)

    # Case 2: 07:00 -> 09:00 UTC (crosses 08:00 UTC settlement boundary once)
    t_entry_2 = "2025-05-01T07:00:00+00:00"
    f_slice_2 = [
        {
            "open_time": int(pd.Timestamp("2025-05-01T07:00:00+00:00").timestamp() * 1000),
            "open_time_str": "2025-05-01T07:00:00+00:00",
            "close_time_ts": pd.Timestamp("2025-05-01T08:00:00+00:00"),
            "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000.0,
        },
        {
            "open_time": int(pd.Timestamp("2025-05-01T08:00:00+00:00").timestamp() * 1000),
            "open_time_str": "2025-05-01T08:00:00+00:00",
            "close_time_ts": pd.Timestamp("2025-05-01T09:00:00+00:00"),
            "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000.0,
        },
    ]
    sim_2 = simulate_trade_v2(
        f_slice_2, entry_price=100.0, stop_loss=150.0, tp1=10.0, tp2=8.0, tp3=5.0,
        round_trip_fee_bps=0.0, entry_timestamp_utc=pd.Timestamp(t_entry_2),
    )
    t_obj_2 = SimpleNamespace(
        trade_id="SETTLE_08", symbol="SOLUSDT", higher_timeframe="4h",
        decision_time=t_entry_2, entry_time=t_entry_2, exit_time=sim_2["exit_close_time"],
        entry_price=100.0, stop_loss=150.0, hold_hours=sim_2["hold_hours"], net_return_pct=0.0,
    )
    res_2 = compute_portfolio_nav_and_concurrency(
        [{"trade": t_obj_2, "sim": sim_2, "pos_mult": 1.0, "full_conviction_score": 80.0}],
        window_start_utc="2025-05-01T06:00:00+00:00",
        window_end_utc="2025-05-01T10:00:00+00:00",
        base_notional_weight=0.20,
        funding_bps_per_8h=1.0,
        round_trip_fee_bps=0.0,
    )
    nav_2 = res_2["nav_simulation_20pct_notional_per_1x"]
    # 1 settlement of 1.0 bps (0.01%) on 20% notional = -0.002% of NAV -> 99.998
    assert nav_2["stress_funding_events_charged"] == 1
    assert nav_2["stress_funding_net_pct_of_initial_nav"] == pytest.approx(-0.002, abs=1e-9)
    assert nav_2["additive_final_nav"] == pytest.approx(99.998, abs=1e-6)


def test_v403_missing_bar_gap_retains_slot_until_real_exit_timestamp() -> None:
    """Reproduce audit counterexample `gap_releases_slot_early` (RT2-C1):
    Trade 1 enters at 00:00 UTC and has 2 bars in future_slice: [00:00->01:00] and [03:00->04:00]
    (missing bars from 01:00 to 03:00). Although hold_hours == 2 bars, real exit_close_time is 04:00 UTC.
    Trade 2 arrives at 02:00 UTC with max_concurrent_cap=1.
    Trade 2 MUST be rejected because Trade 1 occupies the slot until 04:00 UTC.
    """
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    import pandas as pd

    scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts" / "fibo_research")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    from verify_red_team_audit_2026 import compute_portfolio_nav_and_concurrency, simulate_trade_v2

    f_slice_gap = [
        {
            "open_time": int(pd.Timestamp("2025-05-01T00:00:00+00:00").timestamp() * 1000),
            "open_time_str": "2025-05-01T00:00:00+00:00",
            "close_time_ts": pd.Timestamp("2025-05-01T01:00:00+00:00"),
            "open": 100.0, "high": 101.0, "low": 98.0, "close": 99.0, "volume": 1000.0,
        },
        {
            "open_time": int(pd.Timestamp("2025-05-01T03:00:00+00:00").timestamp() * 1000),
            "open_time_str": "2025-05-01T03:00:00+00:00",
            "close_time_ts": pd.Timestamp("2025-05-01T04:00:00+00:00"),
            "open": 99.0, "high": 100.0, "low": 95.0, "close": 96.0, "volume": 1000.0,
        },
    ]
    sim_gap = simulate_trade_v2(
        f_slice_gap, entry_price=100.0, stop_loss=150.0, tp1=10.0, tp2=8.0, tp3=5.0,
        round_trip_fee_bps=20.0, entry_timestamp_utc=pd.Timestamp("2025-05-01T00:00:00+00:00"),
    )
    assert sim_gap["observed_bars"] == 2
    assert sim_gap["real_hold_hours"] == 4
    assert sim_gap["hold_hours"] == 4
    assert sim_gap["exit_close_time"] == "2025-05-01T04:00:00+00:00"

    t1 = SimpleNamespace(
        trade_id="GAP_T1", symbol="ACEUSDT", higher_timeframe="4h",
        decision_time="2025-05-01T00:00:00+00:00", entry_time="2025-05-01T00:00:00+00:00",
        exit_time=sim_gap["exit_close_time"], entry_price=100.0, stop_loss=150.0,
        hold_hours=sim_gap["hold_hours"], net_return_pct=sim_gap["net_pct"],
    )

    f_slice_t2 = [
        {
            "open_time": int(pd.Timestamp("2025-05-01T02:00:00+00:00").timestamp() * 1000),
            "open_time_str": "2025-05-01T02:00:00+00:00",
            "close_time_ts": pd.Timestamp("2025-05-01T03:00:00+00:00"),
            "open": 100.0, "high": 101.0, "low": 95.0, "close": 96.0, "volume": 1000.0,
        }
    ]
    sim_t2 = simulate_trade_v2(
        f_slice_t2, entry_price=100.0, stop_loss=150.0, tp1=10.0, tp2=8.0, tp3=5.0,
        round_trip_fee_bps=20.0, entry_timestamp_utc=pd.Timestamp("2025-05-01T02:00:00+00:00"),
    )
    t2 = SimpleNamespace(
        trade_id="GAP_T2", symbol="SOLUSDT", higher_timeframe="4h",
        decision_time="2025-05-01T02:00:00+00:00", entry_time="2025-05-01T02:00:00+00:00",
        exit_time=sim_t2["exit_close_time"], entry_price=100.0, stop_loss=150.0,
        hold_hours=sim_t2["hold_hours"], net_return_pct=sim_t2["net_pct"],
    )

    res = compute_portfolio_nav_and_concurrency(
        [
            {"trade": t1, "sim": sim_gap, "pos_mult": 1.0, "full_conviction_score": 80.0},
            {"trade": t2, "sim": sim_t2, "pos_mult": 1.0, "full_conviction_score": 80.0},
        ],
        window_start_utc="2025-05-01T00:00:00+00:00",
        window_end_utc="2025-05-01T05:00:00+00:00",
        base_notional_weight=0.20,
        max_concurrent_cap=1,
    )
    nav = res["nav_simulation_20pct_notional_per_1x"]
    assert nav["executed_trades"] == 1
    assert nav["skipped_concurrency_cap"] == 1
    assert res["accepted_concurrency"]["max_concurrent"] == 1


def test_v403_notional_cap_current_equity_mtm_and_tiebreak_invariance() -> None:
    """Reproduce audit counterexample `notional_cap_current_equity` (RT2-C1/C2):
    4 short positions open at 00:00 UTC with notional=20 each (total 80 on NAV=100).
    At 01:00 UTC, price rises 100 -> 120 (-20% adverse move), so MTM exposure is 4 * 24 = 96
    while current equity is 100 - 16 = 84 (96 / 84 = 1.1429x > 1.0x).
    A 5th candidate arriving at 01:00 UTC MUST be rejected by the equity-relative MTM notional cap.
    Also verify tie-breaking permutation invariance.
    """
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    import pandas as pd

    scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts" / "fibo_research")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    from verify_red_team_audit_2026 import compute_portfolio_nav_and_concurrency, simulate_trade_v2

    items_mtm = []
    for i in range(4):
        f_slice = [
            {
                "open_time": int(pd.Timestamp("2025-05-01T00:00:00+00:00").timestamp() * 1000),
                "open_time_str": "2025-05-01T00:00:00+00:00",
                "close_time_ts": pd.Timestamp("2025-05-01T01:00:00+00:00"),
                "open": 100.0, "high": 120.0, "low": 100.0, "close": 120.0, "volume": 1000.0,
            },
            {
                "open_time": int(pd.Timestamp("2025-05-01T01:00:00+00:00").timestamp() * 1000),
                "open_time_str": "2025-05-01T01:00:00+00:00",
                "close_time_ts": pd.Timestamp("2025-05-01T02:00:00+00:00"),
                "open": 120.0, "high": 121.0, "low": 115.0, "close": 118.0, "volume": 1000.0,
            },
        ]
        sim = simulate_trade_v2(
            f_slice, entry_price=100.0, stop_loss=200.0, tp1=10.0, tp2=8.0, tp3=5.0,
            round_trip_fee_bps=0.0, entry_timestamp_utc=pd.Timestamp("2025-05-01T00:00:00+00:00"),
        )
        t_obj = SimpleNamespace(
            trade_id=f"MTM_{i}", symbol=f"SYM{i}USDT", higher_timeframe="4h",
            decision_time="2025-05-01T00:00:00+00:00", entry_time="2025-05-01T00:00:00+00:00",
            exit_time=sim["exit_close_time"], entry_price=100.0, stop_loss=200.0,
            hold_hours=sim["hold_hours"], net_return_pct=sim["net_pct"],
        )
        items_mtm.append({"trade": t_obj, "sim": sim, "pos_mult": 1.0, "full_conviction_score": 80.0 - i})

    # 5th candidate at 01:00 UTC
    f_slice_5 = [
        {
            "open_time": int(pd.Timestamp("2025-05-01T01:00:00+00:00").timestamp() * 1000),
            "open_time_str": "2025-05-01T01:00:00+00:00",
            "close_time_ts": pd.Timestamp("2025-05-01T02:00:00+00:00"),
            "open": 100.0, "high": 101.0, "low": 90.0, "close": 92.0, "volume": 1000.0,
        }
    ]
    sim_5 = simulate_trade_v2(
        f_slice_5, entry_price=100.0, stop_loss=200.0, tp1=10.0, tp2=8.0, tp3=5.0,
        round_trip_fee_bps=0.0, entry_timestamp_utc=pd.Timestamp("2025-05-01T01:00:00+00:00"),
    )
    t_5 = SimpleNamespace(
        trade_id="MTM_5", symbol="SYM5USDT", higher_timeframe="4h",
        decision_time="2025-05-01T01:00:00+00:00", entry_time="2025-05-01T01:00:00+00:00",
        exit_time=sim_5["exit_close_time"], entry_price=100.0, stop_loss=200.0,
        hold_hours=sim_5["hold_hours"], net_return_pct=sim_5["net_pct"],
    )
    items_mtm.append({"trade": t_5, "sim": sim_5, "pos_mult": 1.0, "full_conviction_score": 85.0})

    res_mtm = compute_portfolio_nav_and_concurrency(
        items_mtm,
        window_start_utc="2025-05-01T00:00:00+00:00",
        window_end_utc="2025-05-01T03:00:00+00:00",
        base_notional_weight=0.20,
        max_concurrent_cap=5,
        max_total_notional_frac=1.0,
        max_total_sl_risk_frac=1.0,
        round_trip_fee_bps=0.0,
    )
    nav_mtm = res_mtm["nav_simulation_20pct_notional_per_1x"]
    assert nav_mtm["executed_trades"] == 4
    assert nav_mtm["skipped_notional_cap"] == 1

    # Permutation invariance test: reverse order of input items
    res_mtm_rev = compute_portfolio_nav_and_concurrency(
        list(reversed(items_mtm)),
        window_start_utc="2025-05-01T00:00:00+00:00",
        window_end_utc="2025-05-01T03:00:00+00:00",
        base_notional_weight=0.20,
        max_concurrent_cap=5,
        max_total_notional_frac=1.0,
        max_total_sl_risk_frac=1.0,
        round_trip_fee_bps=0.0,
    )
    assert res_mtm_rev["nav_simulation_20pct_notional_per_1x"]["compounded_final_nav"] == pytest.approx(
        nav_mtm["compounded_final_nav"], abs=1e-12
    )


def test_v403_unified_conviction_score_and_pit_pre_consumption_and_terminal_outcome() -> None:
    """Verify v4.0.3 fixes for RT2-M3, RT2-H3, and F-04a:
    1) Canonical 4-Factor Orthogonal Conviction Score returns 79.0 (1.15x) across detector.py and research scripts.
    2) execute_symbol_candidates_from_raw checks allowed_yms (Rolling PIT membership) BEFORE consuming wave_key or cooldown.
    3) FiboBacktestTrade automatically populates canonical terminal_outcome (e.g., TP1_THEN_SL_AT_BE).
    """
    import sys
    from pathlib import Path
    import pandas as pd

    scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts" / "fibo_research")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    from dao_vang.fibo_short.backtest import FiboBacktestTrade
    from dao_vang.fibo_short.detector import compute_orthogonal_conviction_score
    from universe_reaudit_v402_worker import execute_symbol_candidates_from_raw

    # 1. Canonical conviction score on audit's exact score_counterexample vector (returns 79.0 / Tier A / 1.15x)
    score, tier, mult, breakdown = compute_orthogonal_conviction_score(
        prior_pump_pct=80.0,
        impulse_drop_pct=7.0,
        fibo_retrace_ratio=0.55,
        wave_ker=0.50,
        impulse_ker=0.60,
        peak_ewmac_16_64=-1.0,
        cur_accel_4_16=-1.2,
        confirmation_tier="COMBO_1_2",
        pullback_vol_ratio=1.0,
        h1_body_ratio=0.50,
    )
    assert score == pytest.approx(79.0, abs=1e-9)
    assert tier == "A"
    assert mult == pytest.approx(1.15, abs=1e-9)
    assert breakdown["L1_pump_exhaustion_pts"] == pytest.approx(19.0)
    assert breakdown["L2_wave_impulse_physics_pts"] == pytest.approx(21.0)
    assert breakdown["L3_pst_momentum_collapse_pts"] == pytest.approx(21.0)
    assert breakdown["L4_fibo_h1_trigger_pts"] == pytest.approx(18.0)

    # 2. Rolling PIT membership checked BEFORE consuming wave_key
    sim_mock = {
        "hold_hours": 10,
        "net_pct": 5.0,
        "gross_pct": 5.2,
        "r_mult": 1.0,
        "detailed_outcome": "TP1_THEN_TIME_EXIT",
        "outcome": "TP1_HIT",
        "tp1_hit": True,
        "tp2_hit": False,
        "tp3_hit": False,
        "ratcheted_sl_hit": False,
        "time_exit_used": True,
        "exit_price": 95.0,
        "exit_time": "2026-02-01T05:00:00+00:00",
        "exit_close_time": "2026-02-01T06:00:00+00:00",
    }
    c1 = {
        "symbol": "TESTUSDT",
        "tf": "4h",
        "wave_key": "TESTUSDT_4h_2026-01-25T00:00:00+00:00",
        "idx_1h": 100,
        "signal_candle_open_time": "2026-01-31T19:00:00+00:00",
        "decision_time": "2026-01-31T20:00:00+00:00",
        "decision_ts": pd.Timestamp("2026-01-31T20:00:00+00:00"),
        "year": 2026,
        "entry_ym": "2026-01",
        "confirmation_tier": "COMBO_1_2",
        "pattern_name": "ENGULFING",
        "entry_price": 100.0,
        "sl_std": 110.0,
        "sl_m6": 111.0,
        "tp1": 90.0,
        "tp2": 80.0,
        "tp3": 70.0,
        "current_fibo_ratio": 0.55,
        "wave_impulse_drop_pct": 0.08,
        "wave_prior_pump_pct": 0.65,
        "ker_wave": 0.55,
        "imp_ker": 0.68,
        "full_conviction_score": 79.0,
        "conviction_tier": "A",
        "legacy_btc_spread_score": 85.0,
        "mult_m6": 1.15,
        "eligible_milestones": ["m1_f1a_pump50", "m4_f2_elite", "m6_f4_expanded"],
        "sim_std": sim_mock,
        "sim_m6": sim_mock,
        "sim_std_0831": sim_mock,
        "sim_m6_0831": sim_mock,
    }
    c2 = {
        **c1,
        "idx_1h": 106,
        "signal_candle_open_time": "2026-02-01T01:00:00+00:00",
        "decision_time": "2026-02-01T02:00:00+00:00",
        "decision_ts": pd.Timestamp("2026-02-01T02:00:00+00:00"),
        "entry_ym": "2026-02",
        "sim_std": {**sim_mock, "exit_close_time": "2026-02-01T12:00:00+00:00"},
        "sim_m6": {**sim_mock, "exit_close_time": "2026-02-01T12:00:00+00:00"},
    }
    # When allowed_yms only includes "2026-02", c1 (in 2026-01) must NOT consume wave_key or cooldown,
    # allowing c2 (in 2026-02 on the same wave_key) to execute!
    res_pit = execute_symbol_candidates_from_raw([c1, c2], allowed_yms={"2026-02"})
    ind_pit = res_pit["independent"]
    assert len(ind_pit["m6_f4_expanded"]) == 1
    assert ind_pit["m6_f4_expanded"][0]["entry_ym"] == "2026-02"

    # 3. FiboBacktestTrade auto-populates canonical terminal_outcome
    t_be = FiboBacktestTrade(
        trade_id="T_BE", symbol="SOLUSDT", higher_timeframe="4h", confirmation_tier="COMBO_1_2",
        pattern_name="ENGULFING", entry_time="2026-01-01T01:00:00+00:00", exit_time="2026-01-01T05:00:00+00:00",
        entry_price=100.0, stop_loss=110.0, tp1=90.0, tp2=80.0, tp3=70.0, exit_price=100.0,
        outcome="TP1_HIT", tp1_reached=True, tp2_reached=False, tp3_reached=False,
        gross_return_pct=5.0, net_return_pct=4.8, r_multiple=0.48, hold_hours=4,
        fibo_entry_ratio=0.55, impulse_drop_pct=10.0, prior_pump_pct=60.0,
    )
    assert t_be.terminal_outcome == "TP1_THEN_SL_AT_BE"


def test_v404_coupled_engines_idempotent_same_hour_and_ledger_equality() -> None:
    """Verify v4.0.4 fixes for FS403-01 and FS403-02:
    Reproduce the exact audit counterexample where an open position at h=0 experiences
    a -10.10% step at h=1 (reducing equity from 100.0 to 96.97 on 0.30x notional), while multiple
    candidates arrive at h=1 (including one blocked by wave/cooldown) and another arrives at h=2.
    Verify on BOTH coupled engines (`run_portfolio_coupled_execution` and
    `run_universe_portfolio_coupled_execution`) that:
    1) Calling `_advance_to_hour(1)` / `_advance_portfolio_to_hour(1)` multiple times at h=1
       never double-deducts the h=1 PnL (equity stays 96.97, never 93.94).
    2) All 3 valid candidates at h=0 and h=1 are accepted under `max_total_notional_frac=0.92`
       (`33/96.97 + 0.56 = 0.9003 <= 0.92`), whereas double-counting would drop equity to 93.94
       and falsely reject the 3rd candidate.
    3) Advancing to h=2 properly accounts for entry fees of the newly opened h=1 positions once.
    4) `accepted_trades == executed_trades` and `set(accepted_trade_ids) == set(executed_trade_ids)`.
    """
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    import pandas as pd

    scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts" / "fibo_research")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    from verify_red_team_audit_2026 import simulate_trade_v2
    from verify_red_team_reaudit_v402 import run_portfolio_coupled_execution
    from universe_reaudit_v402_worker import run_universe_portfolio_coupled_execution

    # Position 0 enters at h=0 (2025-05-01T00:00:00+00:00), score=90 -> mult=1.50 -> notional_frac = 0.20 * 1.50 = 0.30 ($30 on $100).
    # Bar 0 [00:00 -> 01:00 UTC]: price moves 100 -> 110 (-10.0% gross, -0.10% entry fee = -10.10%), dollar PnL = -$3.03 -> equity = 96.97.
    # MTM exposure of Pos 0 at h=1 is $30 * (110/100) = $33.00 -> 33.00 / 96.97 = 0.340311.
    # Bar 1 [01:00 -> 02:00 UTC]: price stays 110 (0.0% gross, -0.10% exit fee), closes at 02:00 UTC.
    f_slice_pos0 = [
        {
            "open_time": int(pd.Timestamp("2025-05-01T00:00:00+00:00").timestamp() * 1000),
            "open_time_str": "2025-05-01T00:00:00+00:00",
            "close_time_ts": pd.Timestamp("2025-05-01T01:00:00+00:00"),
            "open": 100.0,
            "high": 110.0,
            "low": 100.0,
            "close": 110.0,
            "volume": 1000.0,
        },
        {
            "open_time": int(pd.Timestamp("2025-05-01T01:00:00+00:00").timestamp() * 1000),
            "open_time_str": "2025-05-01T01:00:00+00:00",
            "close_time_ts": pd.Timestamp("2025-05-01T02:00:00+00:00"),
            "open": 110.0,
            "high": 110.0,
            "low": 110.0,
            "close": 110.0,
            "volume": 1000.0,
        },
    ]
    sim_pos0 = simulate_trade_v2(
        f_slice_pos0,
        entry_price=100.0,
        stop_loss=150.0,
        tp1=50.0,
        tp2=40.0,
        tp3=30.0,
        round_trip_fee_bps=20.0,
        entry_timestamp_utc=pd.Timestamp("2025-05-01T00:00:00+00:00"),
    )

    # Candidates at h=1 (2025-05-01T01:00:00+00:00), score=85 -> mult=1.50 -> notional_frac = 0.30 each.
    # With max_total_notional_frac = 0.945:
    # Single-pass equity at h=1 is 96.97 -> open_mark_notional_eq = 33.0 / 96.97 = 0.340311.
    # After 1st h=1 candidate (+0.30) and 2nd h=1 candidate (+0.30): 0.340311 + 0.60 = 0.940311 <= 0.945 (accepted!).
    # Under the old double-advance bug, equity was deducted twice at h=1 (100 - 6.06 = 93.94),
    # so open_mark_notional_eq became 33.0 / 93.94 = 0.351288, and 0.351288 + 0.60 = 0.951288 > 0.945 (falsely rejected!).
    f_slice_pos1 = [
        {
            "open_time": int(pd.Timestamp("2025-05-01T01:00:00+00:00").timestamp() * 1000),
            "open_time_str": "2025-05-01T01:00:00+00:00",
            "close_time_ts": pd.Timestamp("2025-05-01T02:00:00+00:00"),
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 1000.0,
        }
    ]
    sim_pos1 = simulate_trade_v2(
        f_slice_pos1,
        entry_price=100.0,
        stop_loss=150.0,
        tp1=50.0,
        tp2=40.0,
        tp3=30.0,
        round_trip_fee_bps=20.0,
        entry_timestamp_utc=pd.Timestamp("2025-05-01T01:00:00+00:00"),
    )

    f_slice_pos2 = [
        {
            "open_time": int(pd.Timestamp("2025-05-01T02:00:00+00:00").timestamp() * 1000),
            "open_time_str": "2025-05-01T02:00:00+00:00",
            "close_time_ts": pd.Timestamp("2025-05-01T03:00:00+00:00"),
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 1000.0,
        }
    ]
    sim_pos2 = simulate_trade_v2(
        f_slice_pos2,
        entry_price=100.0,
        stop_loss=150.0,
        tp1=50.0,
        tp2=40.0,
        tp3=30.0,
        round_trip_fee_bps=20.0,
        entry_timestamp_utc=pd.Timestamp("2025-05-01T02:00:00+00:00"),
    )

    def _make_14coin_cand(
        sym: str,
        tf: str,
        dec_time: str,
        idx_1h: int,
        wave_key: str,
        score: float,
        f_slice: list[dict],
    ) -> dict:
        sig = SimpleNamespace(
            id=f"{sym}_{tf}",
            symbol=sym,
            timeframe=tf,
            signal_time=dec_time,
            h1_confirmation=SimpleNamespace(
                confirmation_tier="COMBO_1_2",
                pattern_name="ENGULFING",
                current_fibo_ratio=0.55,
            ),
            wave=SimpleNamespace(
                impulse_drop_pct=0.08,
                prior_pump_pct=0.65,
            ),
        )
        setup = SimpleNamespace(
            entry_price=100.0,
            stop_loss=150.0,
            tp1=50.0,
            tp2=40.0,
            tp3=30.0,
        )
        fibo_levels = SimpleNamespace(
            level_0000=100.0,
            wave_range=50.0,
        )
        return {
            "symbol": sym,
            "tf": tf,
            "idx_1h": idx_1h,
            "wave_key": wave_key,
            "sig": sig,
            "setup": setup,
            "fibo_levels": fibo_levels,
            "atr_1h": 22.88,  # so 100 + 0.886*50 + 0.25*22.88 = 150.0
            "future_slice": f_slice,
            "decision_time": dec_time,
            "decision_ts": pd.Timestamp(dec_time),
            "full_conviction_score": score,
            "detector_score": score,
            "conviction_tier": "S" if score >= 80 else "A",
            "legacy_btc_spread_score": score,
            "pst_pass": True,
            "f1_elite": True,
            "f1_expanded": True,
            "imp_drop_pct": 8.0,
            "imp_ker": 0.65,
            "cond2_break": True,
            "max_fibo_ratio": 0.55,
            "ker_wave": 0.55,
        }

    c_14 = [
        _make_14coin_cand("SOLUSDT", "4h", "2025-05-01T00:00:00+00:00", 10, "W0", 90.0, f_slice_pos0),
        _make_14coin_cand("ETHUSDT", "4h", "2025-05-01T01:00:00+00:00", 11, "W1", 85.0, f_slice_pos1),
        # Blocked by wave/cooldown on ETHUSDT 4h at the same timestamp h=1:
        _make_14coin_cand("ETHUSDT", "4h", "2025-05-01T01:00:00+00:00", 11, "W1", 82.0, f_slice_pos1),
        # 2nd valid candidate at h=1:
        _make_14coin_cand("BNBUSDT", "4h", "2025-05-01T01:00:00+00:00", 11, "W2", 80.0, f_slice_pos1),
        # Candidate at h=2 (after h=0 and h=1 positions close at 02:00 UTC):
        _make_14coin_cand("ADAUSDT", "4h", "2025-05-01T02:00:00+00:00", 12, "W3", 80.0, f_slice_pos2),
    ]

    res_14 = run_portfolio_coupled_execution(
        c_14,
        "m6_f4_expanded",
        window_start_utc="2025-05-01T00:00:00+00:00",
        window_end_utc="2025-05-01T04:00:00+00:00",
        base_notional_weight=0.20,
        max_concurrent_cap=5,
        max_total_notional_frac=0.945,
        max_total_sl_risk_frac=0.80,
    )
    assert res_14["accepted_trades"] == 4
    assert res_14["executed_trades"] == 4
    assert res_14["trade_id_set_exact_match"] is True
    assert res_14["blocked_by_wave_or_cooldown"] == 1
    assert res_14["rejected_notional_cap"] == 0

    # Verify fee and PnL math at end of window:
    # Pos 0 (h=0..2): $30 * (-10.20%) = -3.06 (h=1: -3.03 -> equity=96.97; h=2: -0.03)
    # Pos 1 & Pos 2 (entered at h=1 when equity=96.97, notional_frac=0.30 -> n0_comp = 29.091 each):
    # Each pays -0.20% round-trip fee = 29.091 * (-0.002) = -0.058182 -> both = -0.116364
    # Equity at h=2 = 96.97 - 0.03 - 0.116364 = 96.823636
    # Pos 3 (entered at h=2 when equity=96.823636, notional_frac=0.30 -> n0_comp = 29.0470908):
    # Pays -0.20% round-trip fee = -0.05809418 -> final compounded NAV = 96.7655418 -> 96.7655
    assert res_14["nav_ex_funding"]["compounded_final_nav"] == pytest.approx(96.7655, abs=1e-3)

    # Now test the same scenario on `run_universe_portfolio_coupled_execution`
    def _make_univ_cand(
        sym: str,
        tf: str,
        dec_time: str,
        idx_1h: int,
        wave_key: str,
        score: float,
        mult: float,
        sim_d: dict,
        sl: float,
    ) -> dict:
        return {
            "symbol": sym,
            "tf": tf,
            "idx_1h": idx_1h,
            "wave_key": wave_key,
            "eligible_milestones": ["m6_f4_expanded"],
            "signal_candle_open_time": dec_time,
            "decision_time": dec_time,
            "decision_ts": pd.Timestamp(dec_time),
            "year": 2025,
            "entry_ym": "2025-05",
            "confirmation_tier": "COMBO_1_2",
            "pattern_name": "ENGULFING",
            "entry_price": 100.0,
            "sl_std": sl,
            "sl_m6": sl,
            "tp1": 50.0,
            "tp2": 40.0,
            "tp3": 30.0,
            "current_fibo_ratio": 0.55,
            "wave_impulse_drop_pct": 0.08,
            "wave_prior_pump_pct": 0.65,
            "ker_wave": 0.55,
            "imp_ker": 0.65,
            "full_conviction_score": score,
            "conviction_tier": "S",
            "mult_m6": mult,
            "legacy_btc_spread_score": score,
            "sim_std": sim_d,
            "sim_m6": sim_d,
            "sim_std_0831": sim_d,
            "sim_m6_0831": sim_d,
        }

    c_univ = [
        _make_univ_cand("SOLUSDT", "4h", "2025-05-01T00:00:00+00:00", 10, "W0", 90.0, 1.50, sim_pos0, 150.0),
        _make_univ_cand("ETHUSDT", "4h", "2025-05-01T01:00:00+00:00", 11, "W1", 85.0, 1.50, sim_pos1, 150.0),
        _make_univ_cand("ETHUSDT", "4h", "2025-05-01T01:00:00+00:00", 11, "W1", 82.0, 1.50, sim_pos1, 150.0),
        _make_univ_cand("BNBUSDT", "4h", "2025-05-01T01:00:00+00:00", 11, "W2", 80.0, 1.50, sim_pos1, 150.0),
        _make_univ_cand("ADAUSDT", "4h", "2025-05-01T02:00:00+00:00", 12, "W3", 80.0, 1.50, sim_pos2, 150.0),
    ]
    res_univ = run_universe_portfolio_coupled_execution(
        c_univ,
        "m6_f4_expanded",
        window_start_utc="2025-05-01T00:00:00+00:00",
        window_end_utc="2025-05-01T04:00:00+00:00",
        base_notional_weight=0.20,
        max_concurrent_cap=5,
        max_total_notional_frac=0.945,
        max_total_sl_risk_frac=0.80,
    )
    assert res_univ["accepted_trades"] == 4
    assert res_univ["executed_trades"] == 4
    assert res_univ["trade_id_set_exact_match"] is True
    assert res_univ["blocked_by_wave_or_cooldown"] == 1
    assert res_univ["rejected_by_notional_cap"] == 0
    assert res_univ["nav_20pct_per_1x"]["compounded_final_nav"] == pytest.approx(96.7655, abs=1e-3)


def test_v404_real_utc_timestamp_cooldown_and_is_oos_concatenation_invariance() -> None:
    """Verify v4.0.4 fix for FS403-03:
    1) Shifting local `idx_1h` by +50000 does not change trade selection or `trade_id` in
       `execute_configuration` or `execute_symbol_candidates_from_raw`.
    2) Concatenating IS (`2025-08-31T18:00:00+00:00`, `idx_1h=2422`, `hold_hours=290`) and
       OOS (`2026-05-09T10:00:00+00:00`, `idx_1h=2433`) candidates on `ACEUSDT` `1d` does NOT
       allow the IS local index cooldown (`2422 + 290 = 2712 > 2433`) to suppress the 2026 OOS trade.
    """
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    import pandas as pd

    scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts" / "fibo_research")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    from verify_red_team_audit_2026 import execute_configuration

    f_slice_is = [
        {
            "open_time": int((pd.Timestamp("2025-08-31T18:00:00+00:00") + pd.Timedelta(hours=h)).timestamp() * 1000),
            "open_time_str": (pd.Timestamp("2025-08-31T18:00:00+00:00") + pd.Timedelta(hours=h)).isoformat(),
            "close_time_ts": pd.Timestamp("2025-08-31T18:00:00+00:00") + pd.Timedelta(hours=h + 1),
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 1000.0,
        }
        for h in range(290)
    ]
    f_slice_oos = [
        {
            "open_time": int((pd.Timestamp("2026-05-09T10:00:00+00:00") + pd.Timedelta(hours=h)).timestamp() * 1000),
            "open_time_str": (pd.Timestamp("2026-05-09T10:00:00+00:00") + pd.Timedelta(hours=h)).isoformat(),
            "close_time_ts": pd.Timestamp("2026-05-09T10:00:00+00:00") + pd.Timedelta(hours=h + 1),
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 1000.0,
        }
        for h in range(24)
    ]

    def _mk_exec_cand(dec_time: str, idx_1h: int, wave_key: str, f_slice: list[dict]) -> dict:
        sig = SimpleNamespace(
            id="ACEUSDT_1d",
            symbol="ACEUSDT",
            timeframe="1d",
            signal_time=dec_time,
            h1_confirmation=SimpleNamespace(
                confirmation_tier="COMBO_1_2",
                pattern_name="ENGULFING",
                current_fibo_ratio=0.55,
            ),
            wave=SimpleNamespace(
                impulse_drop_pct=0.08,
                prior_pump_pct=0.65,
            ),
        )
        setup = SimpleNamespace(
            entry_price=100.0,
            stop_loss=150.0,
            tp1=50.0,
            tp2=40.0,
            tp3=30.0,
        )
        fibo_levels = SimpleNamespace(
            level_0000=100.0,
            wave_range=50.0,
        )
        return {
            "symbol": "ACEUSDT",
            "tf": "1d",
            "idx_1h": idx_1h,
            "wave_key": wave_key,
            "sig": sig,
            "setup": setup,
            "fibo_levels": fibo_levels,
            "atr_1h": 10.0,
            "future_slice": f_slice,
            "decision_time": dec_time,
            "decision_ts": pd.Timestamp(dec_time),
            "full_conviction_score": 80.0,
            "detector_score": 80.0,
            "conviction_tier": "S",
            "legacy_btc_spread_score": 80.0,
            "pst_pass": True,
            "f1_elite": True,
            "f1_expanded": True,
            "imp_drop_pct": 8.0,
            "imp_ker": 0.65,
            "cond2_break": True,
            "max_fibo_ratio": 0.55,
            "ker_wave": 0.55,
        }

    c_is = _mk_exec_cand("2025-08-31T18:00:00+00:00", 2422, "W_IS_2025", f_slice_is)
    c_oos = _mk_exec_cand("2026-05-09T10:00:00+00:00", 2433, "W_OOS_2026", f_slice_oos)
    c_oos_shifted = _mk_exec_cand("2026-05-09T10:00:00+00:00", 52433, "W_OOS_2026", f_slice_oos)

    # 1. Standalone OOS vs shifted idx_1h (+50000) produce identical trade_id and selection
    res_oos_only = execute_configuration([c_oos], "m1_f1a_pump50")
    res_oos_shifted = execute_configuration([c_oos_shifted], "m1_f1a_pump50")
    assert len(res_oos_only) == 1
    assert len(res_oos_shifted) == 1
    assert res_oos_only[0]["trade"].trade_id == res_oos_shifted[0]["trade"].trade_id

    # 2. Concatenating IS (idx_1h=2422, hold=290) + OOS (idx_1h=2433) preserves both trades!
    res_concat = execute_configuration([c_is, c_oos], "m1_f1a_pump50")
    assert len(res_concat) == 2
    assert [x["decision_time"] for x in res_concat] == [
        "2025-08-31T18:00:00+00:00",
        "2026-05-09T10:00:00+00:00",
    ]


def test_v404_funding_loader_numeric_unit_contract_and_variable_cadence() -> None:
    """Verify v4.0.4 fix for FS403-04:
    1) Explicit numeric millisecond (`1735689600000`) and numeric second (`1735689600`) timestamps
       are parsed via the explicit unit contract (`ms` vs `s`) into `2025-01-01T00:00:00+00:00`.
    2) Out-of-range numeric timestamps (`12345`) or excessive sub-hour jitter (`>300s`) return `SCHEMA_ERROR`.
    3) Variable-cadence historical funding (`4h` settlements at `00:00, 04:00, 08:00, 12:00 UTC`)
       separately reports `standard_8h_records` vs `off_8h_records` and settles both in
       `compute_time_weighted_concurrency_and_nav` (`historical_funding_events_matched_8h` and
       `historical_funding_events_matched_off_8h`).
    """
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    import pandas as pd

    scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts" / "fibo_research")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    from verify_red_team_reaudit_v402 import parse_funding_dataframe
    from verify_red_team_audit_2026 import compute_portfolio_nav_and_concurrency, simulate_trade_v2

    # 1. Numeric milliseconds & seconds
    df_ms = pd.DataFrame({"timestamp": [1735689600000, 1735718400000], "funding_rate": [0.0001, 0.0002]})
    diag_ms = parse_funding_dataframe(df_ms, source_label="numeric_ms")
    assert diag_ms["status"] == "OK"
    assert diag_ms["detected_timestamp_unit"] == "ms"
    assert diag_ms["min_utc"] == "2025-01-01T00:00:00+00:00"

    df_sec = pd.DataFrame({"timestamp": [1735689600, 1735718400], "funding_rate": [0.0001, 0.0002]})
    diag_sec = parse_funding_dataframe(df_sec, source_label="numeric_s")
    assert diag_sec["status"] == "OK"
    assert diag_sec["detected_timestamp_unit"] == "s"
    assert diag_sec["min_utc"] == "2025-01-01T00:00:00+00:00"

    # 2. Out-of-range numeric timestamp -> SCHEMA_ERROR (never silently 1970-01-01)
    df_bad_num = pd.DataFrame({"timestamp": [12345, 67890], "funding_rate": [0.0001, 0.0002]})
    diag_bad_num = parse_funding_dataframe(df_bad_num, source_label="bad_numeric")
    assert diag_bad_num["status"] == "SCHEMA_ERROR"

    # Excessive sub-hour jitter (00:15:00 UTC -> 900s > 300s) -> SCHEMA_ERROR
    df_jitter = pd.DataFrame(
        {"timestamp": pd.to_datetime(["2025-01-01T00:15:00Z"]), "funding_rate": [0.0001]}
    )
    diag_jitter = parse_funding_dataframe(df_jitter, source_label="excess_jitter")
    assert diag_jitter["status"] == "SCHEMA_ERROR"

    # 3. Variable 4h cadence (00:00, 04:00, 08:00, 12:00 UTC)
    df_4h = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2025-05-01T00:00:00Z",
                    "2025-05-01T04:00:00Z",
                    "2025-05-01T08:00:00Z",
                    "2025-05-01T12:00:00Z",
                ]
            ),
            "funding_rate": [0.0001, 0.0001, 0.0001, 0.0001],
        }
    )
    diag_4h = parse_funding_dataframe(df_4h, source_label="var_4h")
    assert diag_4h["status"] == "OK"
    assert diag_4h["standard_8h_records"] == 2
    assert diag_4h["off_8h_records"] == 2
    assert diag_4h["inferred_local_cadence_missing_slots"] == 0

    # Settle across 03:00 -> 09:00 UTC (crosses 04:00 off-8h and 08:00 standard-8h)
    bars_4h = [
        {
            "open_time": int(pd.Timestamp(f"2025-05-01T{h:02d}:00:00+00:00").timestamp() * 1000),
            "open_time_str": f"2025-05-01T{h:02d}:00:00+00:00",
            "close_time_ts": pd.Timestamp(f"2025-05-01T{h+1:02d}:00:00+00:00"),
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 1000.0,
        }
        for h in range(3, 9)
    ]
    sim_4h = simulate_trade_v2(
        bars_4h,
        entry_price=100.0,
        stop_loss=150.0,
        tp1=10.0,
        tp2=8.0,
        tp3=5.0,
        round_trip_fee_bps=0.0,
        entry_timestamp_utc=pd.Timestamp("2025-05-01T03:00:00+00:00"),
    )
    t_4h = SimpleNamespace(
        trade_id="ACE_4H_FUND",
        symbol="ACEUSDT",
        higher_timeframe="4h",
        decision_time="2025-05-01T03:00:00+00:00",
        entry_time="2025-05-01T03:00:00+00:00",
        exit_time=sim_4h["exit_close_time"],
        entry_price=100.0,
        stop_loss=150.0,
        hold_hours=sim_4h["hold_hours"],
        net_return_pct=0.0,
    )
    res_nav = compute_portfolio_nav_and_concurrency(
        [{"trade": t_4h, "sim": sim_4h, "pos_mult": 1.0, "full_conviction_score": 80.0}],
        window_start_utc="2025-05-01T02:00:00+00:00",
        window_end_utc="2025-05-01T10:00:00+00:00",
        base_notional_weight=0.20,
        funding_bps_per_8h=0.0,
        round_trip_fee_bps=0.0,
        funding_lookup={"ACEUSDT": diag_4h["records_map"]},
    )
    nav_d = res_nav["nav_simulation_20pct_notional_per_1x"]
    assert nav_d["historical_funding_events_matched"] == 2
    assert nav_d["historical_funding_events_matched_8h"] == 1
    assert nav_d["historical_funding_events_matched_off_8h"] == 1


def test_v404_content_sha256_fingerprint_detects_same_size_same_mtime_mutation(tmp_path) -> None:
    """Verify v4.0.4 fix for FS403-06:
    Modifying file bytes while keeping `st_size` and `st_mtime` identical MUST change
    the SHA256 fingerprint returned by `compute_universe_input_fingerprint`.
    """
    import os
    import sys
    from pathlib import Path

    scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts" / "fibo_research")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    from universe_reaudit_v402_worker import compute_universe_input_fingerprint

    data_dir = tmp_path / "data_5m"
    data_dir.mkdir(parents=True, exist_ok=True)
    p_file = data_dir / "TESTUSDT.parquet"
    p_file.write_bytes(b"PARQUET_CONTENT_VERSION_AAAA_12345678")
    fixed_mtime = 1700000000
    os.utime(p_file, (fixed_mtime, fixed_mtime))
    st1 = p_file.stat()

    fp1 = compute_universe_input_fingerprint(code_files=[], extra_files=[], data_dirs=[data_dir])

    # Mutate content with exact same byte length and restore identical mtime
    p_file.write_bytes(b"PARQUET_CONTENT_VERSION_BBBB_12345678")
    os.utime(p_file, (fixed_mtime, fixed_mtime))
    st2 = p_file.stat()

    assert st1.st_size == st2.st_size
    assert int(st1.st_mtime) == int(st2.st_mtime)

    fp2 = compute_universe_input_fingerprint(code_files=[], extra_files=[], data_dirs=[data_dir])
    assert fp1 != fp2


def test_v404_dataclass_replace_synchronizes_terminal_outcome() -> None:
    """Verify v4.0.4 fix for FS403-07:
    Calling `dataclasses.replace(t0, outcome='TP3_HIT', exit_price=t0.tp3)` on a trade
    previously initialized with `outcome='STOP_LOSS'` (`terminal_outcome='INITIAL_STOP_LOSS'`)
    must automatically synchronize `terminal_outcome` to `'TP3_FULL'` and set
    `tp1_reached=True, tp2_reached=True, tp3_reached=True`.
    """
    from dataclasses import replace
    from dao_vang.fibo_short.backtest import FiboBacktestTrade

    t0 = FiboBacktestTrade(
        trade_id="T_SL_0",
        symbol="SOLUSDT",
        higher_timeframe="4h",
        confirmation_tier="COMBO_1_2",
        pattern_name="ENGULFING",
        entry_time="2025-05-01T00:00:00+00:00",
        exit_time="2025-05-01T04:00:00+00:00",
        entry_price=100.0,
        stop_loss=110.0,
        tp1=90.0,
        tp2=80.0,
        tp3=70.0,
        exit_price=110.0,
        outcome="STOP_LOSS",
        tp1_reached=False,
        tp2_reached=False,
        tp3_reached=False,
        gross_return_pct=-10.0,
        net_return_pct=-10.2,
        r_multiple=-1.02,
        hold_hours=4,
        fibo_entry_ratio=0.55,
        impulse_drop_pct=8.0,
        prior_pump_pct=60.0,
    )
    assert t0.terminal_outcome == "INITIAL_STOP_LOSS"
    assert t0.tp3_reached is False

    t1 = replace(
        t0,
        outcome="TP3_HIT",
        exit_price=70.0,
        gross_return_pct=20.0,
        net_return_pct=19.8,
        r_multiple=1.98,
    )
    assert t1.terminal_outcome == "TP3_FULL"
    assert t1.tp1_reached is True
    assert t1.tp2_reached is True
    assert t1.tp3_reached is True
    assert t1.ratcheted_sl_hit is False
    assert t1.time_exit_used is False


def test_v405_fs404_01_real_exit_close_time_cooldown_across_missing_bars() -> None:
    """Verify v4.0.5 fix for FS404-01 across all 4 execution engines:
    Reproduce the exact audit counterexample:
    - Trade 1 enters at 2025-05-01T00:00:00+00:00.
    - Future slice has only 2 observed 1h bars: bar 0 opening 00:00 (closing 01:00) and
      bar 1 opening 09:00 (closing 10:00) due to an 8-hour missing-bar gap.
    - Thus `observed_bars == 2`, `exit_close_time == 2025-05-01T10:00:00+00:00`, `real_hold_hours == 10`.
    - Candidate 2 on the same (symbol, tf) at 2025-05-01T05:00:00+00:00 MUST BE REJECTED because the
      first position is still open until 10:00 UTC.
    - Candidate 3 on the same (symbol, tf) at 2025-05-01T10:00:00+00:00 MUST BE ACCEPTED at exit_close_time.
    """
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    import pandas as pd

    scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts" / "fibo_research")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    from verify_red_team_audit_2026 import execute_configuration, simulate_trade_v2
    from verify_red_team_reaudit_v402 import run_portfolio_coupled_execution
    from universe_reaudit_v402_worker import (
        execute_symbol_candidates_from_raw,
        run_universe_portfolio_coupled_execution,
    )

    # 2 observed bars spanning 00:00 -> 10:00 UTC (missing bars 01:00..08:00)
    f_slice_gapped = [
        {
            "open_time": int(pd.Timestamp("2025-05-01T00:00:00+00:00").timestamp() * 1000),
            "open_time_str": "2025-05-01T00:00:00+00:00",
            "close_time_ts": pd.Timestamp("2025-05-01T01:00:00+00:00"),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1000.0,
        },
        {
            "open_time": int(pd.Timestamp("2025-05-01T09:00:00+00:00").timestamp() * 1000),
            "open_time_str": "2025-05-01T09:00:00+00:00",
            "close_time_ts": pd.Timestamp("2025-05-01T10:00:00+00:00"),
            "open": 100.0,
            "high": 101.0,
            "low": 89.0,
            "close": 95.0,
            "volume": 1000.0,
        },
    ]
    sim_gap = simulate_trade_v2(
        f_slice_gapped,
        entry_price=100.0,
        stop_loss=110.0,
        tp1=90.0,
        tp2=80.0,
        tp3=70.0,
        round_trip_fee_bps=20.0,
        entry_timestamp_utc=pd.Timestamp("2025-05-01T00:00:00+00:00"),
    )
    assert sim_gap["observed_bars"] == 2
    assert sim_gap["exit_close_time"] == "2025-05-01T10:00:00+00:00"
    assert sim_gap["real_hold_hours"] == 10
    assert sim_gap["hold_hours"] == 10

    f_slice_later = [
        {
            "open_time": int(pd.Timestamp("2025-05-01T10:00:00+00:00").timestamp() * 1000),
            "open_time_str": "2025-05-01T10:00:00+00:00",
            "close_time_ts": pd.Timestamp("2025-05-01T11:00:00+00:00"),
            "open": 100.0,
            "high": 101.0,
            "low": 95.0,
            "close": 96.0,
            "volume": 1000.0,
        }
    ]
    sim_later = simulate_trade_v2(
        f_slice_later,
        entry_price=100.0,
        stop_loss=110.0,
        tp1=90.0,
        tp2=80.0,
        tp3=70.0,
        round_trip_fee_bps=20.0,
        entry_timestamp_utc=pd.Timestamp("2025-05-01T10:00:00+00:00"),
    )

    def _mk_14_cand(dec_time: str, idx_1h: int, wave_key: str, f_slice: list[dict]) -> dict:
        sig = SimpleNamespace(
            id="CVXUSDT_4h",
            symbol="CVXUSDT",
            timeframe="4h",
            signal_time=dec_time,
            h1_confirmation=SimpleNamespace(
                confirmation_tier="COMBO_1_2",
                pattern_name="ENGULFING",
                current_fibo_ratio=0.55,
            ),
            wave=SimpleNamespace(impulse_drop_pct=0.08, prior_pump_pct=0.65),
        )
        setup = SimpleNamespace(entry_price=100.0, stop_loss=110.0, tp1=90.0, tp2=80.0, tp3=70.0)
        fibo_levels = SimpleNamespace(level_0000=100.0, wave_range=10.0)
        return {
            "symbol": "CVXUSDT",
            "tf": "4h",
            "idx_1h": idx_1h,
            "wave_key": wave_key,
            "sig": sig,
            "setup": setup,
            "fibo_levels": fibo_levels,
            "atr_1h": 4.0,
            "future_slice": f_slice,
            "decision_time": dec_time,
            "decision_ts": pd.Timestamp(dec_time),
            "full_conviction_score": 80.0,
            "detector_score": 80.0,
            "conviction_tier": "S",
            "legacy_btc_spread_score": 80.0,
            "pst_pass": True,
            "f1_elite": True,
            "f1_expanded": True,
            "imp_drop_pct": 8.0,
            "imp_ker": 0.65,
            "cond2_break": True,
            "max_fibo_ratio": 0.55,
            "ker_wave": 0.55,
        }

    c14_list = [
        _mk_14_cand("2025-05-01T00:00:00+00:00", 0, "W_00", f_slice_gapped),
        _mk_14_cand("2025-05-01T05:00:00+00:00", 1, "W_05", f_slice_later),
        _mk_14_cand("2025-05-01T10:00:00+00:00", 2, "W_10", f_slice_later),
    ]

    # 1. Benchmark standalone & subset execution
    res_ind = execute_configuration(c14_list, "m6_f4_expanded", execution_mode="standalone_independent")
    assert [x["decision_time"] for x in res_ind] == [
        "2025-05-01T00:00:00+00:00",
        "2025-05-01T10:00:00+00:00",
    ]
    res_sub = execute_configuration(c14_list, "m6_f4_expanded", execution_mode="subset_from_m1")
    assert [x["decision_time"] for x in res_sub] == [
        "2025-05-01T00:00:00+00:00",
        "2025-05-01T10:00:00+00:00",
    ]

    # 2. Benchmark coupled execution
    res_coupled_14 = run_portfolio_coupled_execution(
        c14_list,
        "m6_f4_expanded",
        window_start_utc="2025-05-01T00:00:00+00:00",
        window_end_utc="2025-05-01T12:00:00+00:00",
    )
    assert res_coupled_14["accepted_trades"] == 2
    assert res_coupled_14["blocked_by_wave_or_cooldown"] == 1
    assert [r["decision_time"] for r in res_coupled_14["ledger_records"]] == [
        "2025-05-01T00:00:00+00:00",
        "2025-05-01T10:00:00+00:00",
    ]

    # 3. Universe standalone/subset & coupled execution (even if legacy fixture sets hold_hours=2)
    sim_legacy_fixture = {**sim_gap, "hold_hours": 2}

    def _mk_univ_cand(dec_time: str, idx_1h: int, wave_key: str, sim_d: dict) -> dict:
        return {
            "symbol": "CVXUSDT",
            "tf": "4h",
            "idx_1h": idx_1h,
            "wave_key": wave_key,
            "eligible_milestones": ["m1_f1a_pump50", "m6_f4_expanded"],
            "signal_candle_open_time": dec_time,
            "decision_time": dec_time,
            "decision_ts": pd.Timestamp(dec_time),
            "year": 2025,
            "entry_ym": "2025-05",
            "confirmation_tier": "COMBO_1_2",
            "pattern_name": "ENGULFING",
            "entry_price": 100.0,
            "sl_std": 110.0,
            "sl_m6": 110.0,
            "tp1": 90.0,
            "tp2": 80.0,
            "tp3": 70.0,
            "current_fibo_ratio": 0.55,
            "wave_impulse_drop_pct": 0.08,
            "wave_prior_pump_pct": 0.65,
            "ker_wave": 0.55,
            "imp_ker": 0.65,
            "full_conviction_score": 80.0,
            "conviction_tier": "S",
            "mult_m6": 1.50,
            "legacy_btc_spread_score": 80.0,
            "sim_std": sim_d,
            "sim_m6": sim_d,
            "sim_std_0831": sim_d,
            "sim_m6_0831": sim_d,
        }

    c_univ_list = [
        _mk_univ_cand("2025-05-01T00:00:00+00:00", 0, "W_00", sim_legacy_fixture),
        _mk_univ_cand("2025-05-01T05:00:00+00:00", 1, "W_05", sim_later),
        _mk_univ_cand("2025-05-01T10:00:00+00:00", 2, "W_10", sim_later),
    ]
    res_univ_sym = execute_symbol_candidates_from_raw(c_univ_list)
    assert [x["decision_time"] for x in res_univ_sym["independent"]["m6_f4_expanded"]] == [
        "2025-05-01T00:00:00+00:00",
        "2025-05-01T10:00:00+00:00",
    ]
    assert [x["decision_time"] for x in res_univ_sym["subset_from_m1"]["m6_f4_expanded"]] == [
        "2025-05-01T00:00:00+00:00",
        "2025-05-01T10:00:00+00:00",
    ]

    res_coupled_univ = run_universe_portfolio_coupled_execution(
        c_univ_list,
        "m6_f4_expanded",
        window_start_utc="2025-05-01T00:00:00+00:00",
        window_end_utc="2025-05-01T12:00:00+00:00",
    )
    assert res_coupled_univ["accepted_trades"] == 2
    assert res_coupled_univ["blocked_by_wave_or_cooldown"] == 1
    assert [it["decision_time"] for it in res_coupled_univ["accepted_items"]] == [
        "2025-05-01T00:00:00+00:00",
        "2025-05-01T10:00:00+00:00",
    ]


def test_v405_fs404_02_single_source_coupled_and_mutation_rejection(monkeypatch) -> None:
    """Verify v4.0.5 fix for FS404-02:
    1) Neither `run_portfolio_coupled_execution` nor `run_universe_portfolio_coupled_execution`
       calls `compute_portfolio_nav_and_concurrency` (proven by monkeypatching it to raise RuntimeError).
    2) Both engines return explicit `accepted_trade_ids`, `executed_trade_ids`, `ledger_records`,
       `ledger_sha256`, and `single_source_accounting_no_second_cap_pass=True`.
    """
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    import pandas as pd

    scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts" / "fibo_research")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    import verify_red_team_reaudit_v402 as mod_14
    import universe_reaudit_v402_worker as mod_univ
    from verify_red_team_audit_2026 import simulate_trade_v2

    def _forbidden_second_pass(*args, **kwargs):
        raise RuntimeError("SECOND_CAP_PASS_FORBIDDEN_IN_COUPLED_ENGINE")

    monkeypatch.setattr(mod_14, "compute_portfolio_nav_and_concurrency", _forbidden_second_pass)
    monkeypatch.setattr(mod_univ, "compute_portfolio_nav_and_concurrency", _forbidden_second_pass)

    f_slice = [
        {
            "open_time": int(pd.Timestamp("2025-05-01T00:00:00+00:00").timestamp() * 1000),
            "open_time_str": "2025-05-01T00:00:00+00:00",
            "close_time_ts": pd.Timestamp("2025-05-01T01:00:00+00:00"),
            "open": 100.0,
            "high": 100.0,
            "low": 90.0,
            "close": 92.0,
            "volume": 1000.0,
        }
    ]
    sim_d = simulate_trade_v2(
        f_slice,
        entry_price=100.0,
        stop_loss=110.0,
        tp1=95.0,
        tp2=85.0,
        tp3=75.0,
        round_trip_fee_bps=20.0,
        entry_timestamp_utc=pd.Timestamp("2025-05-01T00:00:00+00:00"),
    )

    sig = SimpleNamespace(
        id="SOLUSDT_4h",
        symbol="SOLUSDT",
        timeframe="4h",
        signal_time="2025-05-01T00:00:00+00:00",
        h1_confirmation=SimpleNamespace(
            confirmation_tier="COMBO_1_2",
            pattern_name="ENGULFING",
            current_fibo_ratio=0.55,
        ),
        wave=SimpleNamespace(impulse_drop_pct=0.08, prior_pump_pct=0.65),
    )
    setup = SimpleNamespace(entry_price=100.0, stop_loss=110.0, tp1=95.0, tp2=85.0, tp3=75.0)
    fibo_levels = SimpleNamespace(level_0000=100.0, wave_range=10.0)
    c14 = [
        {
            "symbol": "SOLUSDT",
            "tf": "4h",
            "idx_1h": 0,
            "wave_key": "W0",
            "sig": sig,
            "setup": setup,
            "fibo_levels": fibo_levels,
            "atr_1h": 4.0,
            "future_slice": f_slice,
            "decision_time": "2025-05-01T00:00:00+00:00",
            "decision_ts": pd.Timestamp("2025-05-01T00:00:00+00:00"),
            "full_conviction_score": 80.0,
            "detector_score": 80.0,
            "conviction_tier": "S",
            "legacy_btc_spread_score": 80.0,
            "pst_pass": True,
            "f1_elite": True,
            "f1_expanded": True,
            "imp_drop_pct": 8.0,
            "imp_ker": 0.65,
            "cond2_break": True,
            "max_fibo_ratio": 0.55,
            "ker_wave": 0.55,
        }
    ]
    res14 = mod_14.run_portfolio_coupled_execution(
        c14,
        "m6_f4_expanded",
        window_start_utc="2025-05-01T00:00:00+00:00",
        window_end_utc="2025-05-01T02:00:00+00:00",
    )
    assert res14["single_source_accounting_no_second_cap_pass"] is True
    assert res14["accepted_trade_ids"] == res14["executed_trade_ids"]
    assert len(res14["accepted_trade_ids"]) == 1
    assert len(res14["ledger_sha256"]) == 64

    c_univ = [
        {
            "symbol": "SOLUSDT",
            "tf": "4h",
            "idx_1h": 0,
            "wave_key": "W0",
            "eligible_milestones": ["m6_f4_expanded"],
            "signal_candle_open_time": "2025-05-01T00:00:00+00:00",
            "decision_time": "2025-05-01T00:00:00+00:00",
            "decision_ts": pd.Timestamp("2025-05-01T00:00:00+00:00"),
            "year": 2025,
            "entry_ym": "2025-05",
            "confirmation_tier": "COMBO_1_2",
            "pattern_name": "ENGULFING",
            "entry_price": 100.0,
            "sl_std": 110.0,
            "sl_m6": 110.0,
            "tp1": 95.0,
            "tp2": 85.0,
            "tp3": 75.0,
            "current_fibo_ratio": 0.55,
            "wave_impulse_drop_pct": 0.08,
            "wave_prior_pump_pct": 0.65,
            "ker_wave": 0.55,
            "imp_ker": 0.65,
            "full_conviction_score": 80.0,
            "conviction_tier": "S",
            "mult_m6": 1.50,
            "legacy_btc_spread_score": 80.0,
            "sim_std": sim_d,
            "sim_m6": sim_d,
            "sim_std_0831": sim_d,
            "sim_m6_0831": sim_d,
        }
    ]
    res_u = mod_univ.run_universe_portfolio_coupled_execution(
        c_univ,
        "m6_f4_expanded",
        window_start_utc="2025-05-01T00:00:00+00:00",
        window_end_utc="2025-05-01T02:00:00+00:00",
    )
    assert res_u["single_source_accounting_no_second_cap_pass"] is True
    assert res_u["accepted_trade_ids"] == res_u["executed_trade_ids"]
    assert len(res_u["accepted_trade_ids"]) == 1
    assert len(res_u["ledger_sha256"]) == 64

    # 3. Verify that verify_zero_accepted_vs_executed_mismatches rejects CORRUPTED_TRADE_ID, missing list, duplicate IDs, and bad SHA256
    import copy
    import pytest
    import verify_red_team_reaudit_v405 as mod_v405

    mock_payload = {"bench": {"execution_coupled_portfolio": copy.deepcopy(res14)}}
    mock_univ = {
        "by_universe_tier": {
            "ALL_338_UNFILTERED": {
                f"portfolio_coupled_execution_w{i}": {f"m{j}": copy.deepcopy(res_u) for j in range(4)}
                for i in range(28)
            }
        }
    }
    chk_ok = mod_v405.verify_zero_accepted_vs_executed_mismatches(mock_payload, mock_univ)
    assert chk_ok["all_equal"] is True
    assert chk_ok["universe_coupled_nodes_with_trade_ids_checked"] == 112

    # Mutate executed_trade_ids[0] = "CORRUPTED_TRADE_ID" while keeping trade_id_set_exact_match=True
    bad_corrupt = copy.deepcopy(mock_payload)
    bad_corrupt["bench"]["execution_coupled_portfolio"]["executed_trade_ids"][0] = "CORRUPTED_TRADE_ID"
    with pytest.raises(AssertionError, match="accepted_trade_ids_ne_executed_trade_ids"):
        mod_v405.verify_zero_accepted_vs_executed_mismatches(bad_corrupt, mock_univ)

    # Delete accepted_trade_ids from a universe node
    bad_missing = copy.deepcopy(mock_univ)
    del bad_missing["by_universe_tier"]["ALL_338_UNFILTERED"]["portfolio_coupled_execution_w0"]["m0"]["accepted_trade_ids"]
    with pytest.raises(AssertionError, match="missing_trade_id_list"):
        mod_v405.verify_zero_accepted_vs_executed_mismatches(mock_payload, bad_missing)

    # Duplicate trade_ids with unchanged count=2
    bad_dup = copy.deepcopy(mock_payload)
    c_dup = bad_dup["bench"]["execution_coupled_portfolio"]
    c_dup["accepted_trades"] = 2
    c_dup["executed_trades"] = 2
    c_dup["nav_ex_funding"]["executed_trades"] = 2
    c_dup["nav_with_historical_funding"]["executed_trades"] = 2
    c_dup["nav_stress_1bp_8h_funding"]["executed_trades"] = 2
    c_dup["accepted_trade_ids"] = ["DUP_ID", "DUP_ID"]
    c_dup["executed_trade_ids"] = ["DUP_ID", "DUP_ID"]
    with pytest.raises(AssertionError, match="duplicate_trade_id_detected"):
        mod_v405.verify_zero_accepted_vs_executed_mismatches(bad_dup, mock_univ)


def test_v405_fs404_03_default_wiring_funding_8h_fingerprint_and_missing_dir_error(tmp_path, monkeypatch) -> None:
    """Verify v4.0.5 fix for FS404-03:
    1) `universe_reaudit_v402_worker.SHARED_FUNDING_DIR` and `verify_red_team_reaudit_v402.SHARED_FUNDING_DIR`
       both point to `D:/SharedMarketData/multiyear_2020_2026/funding_8h`.
    2) Integration test on a temporary replica of the directory structure using DEFAULT wiring
       (no manual `data_dirs=[...]` passed): mutating `funding_8h/BTCUSDT_funding.parquet` with
       identical byte length and `st_mtime` changes the fingerprint returned by
       `compute_universe_input_fingerprint()`.
    3) Missing `funding_8h` directory (e.g. if renamed to `funding_rate`) raises `FileNotFoundError`.
    """
    import os
    import sys
    from pathlib import Path
    import pytest

    scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts" / "fibo_research")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    import universe_reaudit_v402_worker as mod_univ
    import verify_red_team_reaudit_v402 as mod_14

    assert mod_univ.SHARED_FUNDING_DIR == Path("D:/SharedMarketData/multiyear_2020_2026/funding_8h")
    assert mod_14.SHARED_FUNDING_DIR == Path("D:/SharedMarketData/multiyear_2020_2026/funding_8h")
    assert mod_univ.SHARED_FUNDING_DIR == mod_14.SHARED_FUNDING_DIR

    # Build temporary replica of the real directory structure
    fake_root = tmp_path / "dao_vang"
    fake_script_dir = fake_root / "scripts" / "fibo_research"
    (fake_root / "src" / "dao_vang" / "config").mkdir(parents=True)
    (fake_root / "src" / "dao_vang" / "fibo_short").mkdir(parents=True)
    fake_script_dir.mkdir(parents=True)
    (fake_root / "artifacts" / "fibo_trend_short").mkdir(parents=True)

    for rel in [
        Path("src/dao_vang/config/settings.py"),
        Path("src/dao_vang/fibo_short/detector.py"),
        Path("src/dao_vang/fibo_short/backtest.py"),
        Path("artifacts/fibo_trend_short/coingecko_marketcap_cache.json"),
        Path("artifacts/fibo_trend_short/fibo_coin_universe_config.json"),
        Path("artifacts/fibo_trend_short/coin_universe_study_2026.json"),
    ]:
        (fake_root / rel).write_bytes(b"FAKE_CODE_OR_CACHE")

    for sname in [
        "study_factor1_multi_repo_benchmark_2025.py",
        "study_factor2_3_4_complete_2025.py",
        "study_independent_audit_metrics.py",
        "study_insample_2020_2025_by_year.py",
        "study_oos_2026_all_7_milestones.py",
        "study_coin_universe_selection_2026.py",
        "verify_red_team_audit_2026.py",
        "verify_red_team_reaudit_v402.py",
        "verify_red_team_reaudit_v405.py",
        "universe_reaudit_v402_worker.py",
    ]:
        (fake_script_dir / sname).write_bytes(b"FAKE_SCRIPT")

    d_5m = tmp_path / "Quant-trading" / "data_lake" / "klines" / "5m"
    d_pre = tmp_path / "SharedMarketData" / "binance_futures_5m_2020_2023"
    d_1h = tmp_path / "SharedMarketData" / "multiyear_2020_2026" / "klines_1h"
    d_f8h = tmp_path / "SharedMarketData" / "multiyear_2020_2026" / "funding_8h"
    d_flk = tmp_path / "Quant-trading" / "data_lake" / "funding"
    for d in (d_5m, d_pre, d_1h, d_f8h, d_flk):
        d.mkdir(parents=True, exist_ok=True)
        (d / "DUMMY.parquet").write_bytes(b"DUMMY_PARQUET_BYTES_0000")

    btc_f8h = d_f8h / "BTCUSDT_funding.parquet"
    btc_f8h.write_bytes(b"BTC_FUNDING_8H_CONTENT_VERSION_AAAA_1234")
    fixed_mtime = 1700000000
    os.utime(btc_f8h, (fixed_mtime, fixed_mtime))

    monkeypatch.setattr(mod_univ, "ROOT_DIR", fake_root)
    monkeypatch.setattr(mod_univ, "SCRIPT_DIR", fake_script_dir)
    monkeypatch.setattr(mod_univ, "DATA_LAKE_5M_DIR", d_5m)
    monkeypatch.setattr(mod_univ, "PRE2024_5M_DIR", d_pre)
    monkeypatch.setattr(mod_univ, "SHARED_1H_DIR", d_1h)
    monkeypatch.setattr(mod_univ, "SHARED_FUNDING_DIR", d_f8h)
    monkeypatch.setattr(mod_univ, "DATA_LAKE_FUNDING_DIR", d_flk)

    # Call with NO arguments (default wiring!)
    fp1, manifest1 = mod_univ.compute_universe_input_fingerprint_and_manifest()
    assert btc_f8h.resolve().as_posix() in manifest1["all_hashed_paths_sha256"]

    # Same-size, same-mtime mutation of BTCUSDT_funding.parquet inside funding_8h
    st1 = btc_f8h.stat()
    btc_f8h.write_bytes(b"BTC_FUNDING_8H_CONTENT_VERSION_BBBB_1234")
    os.utime(btc_f8h, (fixed_mtime, fixed_mtime))
    st2 = btc_f8h.stat()
    assert st1.st_size == st2.st_size
    assert int(st1.st_mtime) == int(st2.st_mtime)

    fp2 = mod_univ.compute_universe_input_fingerprint()
    assert fp1 != fp2

    # If a required directory (such as funding_8h) is missing, default wiring must raise FileNotFoundError
    monkeypatch.setattr(mod_univ, "SHARED_FUNDING_DIR", tmp_path / "SharedMarketData" / "multiyear_2020_2026" / "funding_rate")
    with pytest.raises(FileNotFoundError):
        mod_univ.compute_universe_input_fingerprint()


def test_v405_fs404_04_preserve_simulator_exit_flags_near_stop_price() -> None:
    """Verify v4.0.5 fix for FS404-04:
    1) `TP1_THEN_TIME_EXIT` with `exit_price=99.9995` near `entry_price=100.0` (breakeven stop)
       preserves `terminal_outcome='TP1_THEN_TIME_EXIT'`, `ratcheted_sl_hit=False`, `time_exit_used=True`.
    2) `TP2_THEN_TIME_EXIT` with `exit_price=89.9995` near `tp1=90.0` (ratcheted stop)
       preserves `terminal_outcome='TP2_THEN_TIME_EXIT'`, `ratcheted_sl_hit=False`, `time_exit_used=True`.
    3) Genuine `TP1_THEN_SL_AT_BE` (`ratcheted_sl_hit=True, time_exit_used=False`) preserves
       `terminal_outcome='TP1_THEN_SL_AT_BE'`.
    4) Small-price token (`entry_price=0.00001234, exit_price=0.00001233`) preserves `TP1_THEN_TIME_EXIT`.
    5) `_simulate_trade_outcome(..., return_exit_flags=True)` returns authoritative flags on a near-BE time exit.
    """
    from dataclasses import replace
    from types import SimpleNamespace
    from dao_vang.fibo_short.backtest import FiboBacktestTrade, _simulate_trade_outcome

    # 1. Exact audit counterexample: TP1_THEN_TIME_EXIT at exit_price=99.9995 vs entry_price=100.0
    t_tp1_time = FiboBacktestTrade(
        trade_id="T_NEAR_BE",
        symbol="SOLUSDT",
        higher_timeframe="4h",
        confirmation_tier="COMBO_1_2",
        pattern_name="ENGULFING",
        entry_time="2025-05-01T00:00:00+00:00",
        exit_time="2025-05-03T00:00:00+00:00",
        entry_price=100.0,
        stop_loss=110.0,
        tp1=90.0,
        tp2=80.0,
        tp3=70.0,
        exit_price=99.9995,
        outcome="TP1_HIT",
        tp1_reached=True,
        tp2_reached=False,
        tp3_reached=False,
        gross_return_pct=5.0,
        net_return_pct=4.8,
        r_multiple=0.48,
        hold_hours=48,
        fibo_entry_ratio=0.55,
        impulse_drop_pct=8.0,
        prior_pump_pct=60.0,
        terminal_outcome="TP1_THEN_TIME_EXIT",
        ratcheted_sl_hit=False,
        time_exit_used=True,
    )
    assert t_tp1_time.terminal_outcome == "TP1_THEN_TIME_EXIT"
    assert t_tp1_time.ratcheted_sl_hit is False
    assert t_tp1_time.time_exit_used is True

    # 2. TP2_THEN_TIME_EXIT near tp1=90.0
    t_tp2_time = FiboBacktestTrade(
        trade_id="T_NEAR_TP1",
        symbol="SOLUSDT",
        higher_timeframe="4h",
        confirmation_tier="COMBO_1_2",
        pattern_name="ENGULFING",
        entry_time="2025-05-01T00:00:00+00:00",
        exit_time="2025-05-03T00:00:00+00:00",
        entry_price=100.0,
        stop_loss=110.0,
        tp1=90.0,
        tp2=80.0,
        tp3=70.0,
        exit_price=89.9995,
        outcome="TP2_HIT",
        tp1_reached=True,
        tp2_reached=True,
        tp3_reached=False,
        gross_return_pct=11.5,
        net_return_pct=11.3,
        r_multiple=1.13,
        hold_hours=48,
        fibo_entry_ratio=0.55,
        impulse_drop_pct=8.0,
        prior_pump_pct=60.0,
        terminal_outcome="TP2_THEN_TIME_EXIT",
        ratcheted_sl_hit=False,
        time_exit_used=True,
    )
    assert t_tp2_time.terminal_outcome == "TP2_THEN_TIME_EXIT"
    assert t_tp2_time.ratcheted_sl_hit is False
    assert t_tp2_time.time_exit_used is True

    # 3. Genuine ratcheted SL at BE
    t_tp1_be = FiboBacktestTrade(
        trade_id="T_REAL_BE",
        symbol="SOLUSDT",
        higher_timeframe="4h",
        confirmation_tier="COMBO_1_2",
        pattern_name="ENGULFING",
        entry_time="2025-05-01T00:00:00+00:00",
        exit_time="2025-05-01T05:00:00+00:00",
        entry_price=100.0,
        stop_loss=110.0,
        tp1=90.0,
        tp2=80.0,
        tp3=70.0,
        exit_price=100.0,
        outcome="TP1_HIT",
        tp1_reached=True,
        tp2_reached=False,
        tp3_reached=False,
        gross_return_pct=5.0,
        net_return_pct=4.8,
        r_multiple=0.48,
        hold_hours=5,
        fibo_entry_ratio=0.55,
        impulse_drop_pct=8.0,
        prior_pump_pct=60.0,
        terminal_outcome="TP1_THEN_SL_AT_BE",
        ratcheted_sl_hit=True,
        time_exit_used=False,
    )
    assert t_tp1_be.terminal_outcome == "TP1_THEN_SL_AT_BE"
    assert t_tp1_be.ratcheted_sl_hit is True
    assert t_tp1_be.time_exit_used is False

    # 4. Small-price token (0.00001234 vs 0.00001233)
    t_small = FiboBacktestTrade(
        trade_id="T_MEME_SMALL",
        symbol="PEPEUSDT",
        higher_timeframe="4h",
        confirmation_tier="COMBO_1_2",
        pattern_name="ENGULFING",
        entry_time="2025-05-01T00:00:00+00:00",
        exit_time="2025-05-03T00:00:00+00:00",
        entry_price=0.00001234,
        stop_loss=0.00001350,
        tp1=0.00001100,
        tp2=0.00001000,
        tp3=0.00000900,
        exit_price=0.00001233,
        outcome="TP1_HIT",
        tp1_reached=True,
        tp2_reached=False,
        tp3_reached=False,
        gross_return_pct=5.4,
        net_return_pct=5.2,
        r_multiple=0.55,
        hold_hours=48,
        fibo_entry_ratio=0.55,
        impulse_drop_pct=8.0,
        prior_pump_pct=60.0,
        terminal_outcome="TP1_THEN_TIME_EXIT",
        ratcheted_sl_hit=False,
        time_exit_used=True,
    )
    assert t_small.terminal_outcome == "TP1_THEN_TIME_EXIT"
    assert t_small.ratcheted_sl_hit is False
    assert t_small.time_exit_used is True

    # 5. dataclasses.replace from TP1_THEN_TIME_EXIT to TP3_HIT synchronizes properly
    t_rep = replace(t_tp1_time, outcome="TP3_HIT", exit_price=70.0)
    assert t_rep.terminal_outcome == "TP3_FULL"
    assert t_rep.ratcheted_sl_hit is False
    assert t_rep.time_exit_used is False

    # 6. End-to-end _simulate_trade_outcome(..., return_exit_flags=True) near BE
    future_bars = [
        {"open": 99.5, "high": 99.5, "low": 89.5, "close": 92.0, "open_time_str": "2025-05-01T00:00:00+00:00"},
        {"open": 92.0, "high": 99.9995, "low": 91.0, "close": 99.9995, "open_time_str": "2025-05-01T01:00:00+00:00"},
    ]
    (
        outcome,
        exit_p,
        exit_t,
        hold_h,
        tp1_r,
        tp2_r,
        tp3_r,
        gross_ret,
        net_ret,
        r_mult,
        ratcheted_sl,
        time_exit,
    ) = _simulate_trade_outcome(
        future_bars,
        entry_price=100.0,
        stop_loss=110.0,
        tp1=90.0,
        tp2=80.0,
        tp3=70.0,
        fee_bps=20.0,
        return_exit_flags=True,
    )
    assert outcome == "TP1_HIT"
    assert tp1_r is True
    assert exit_p == pytest.approx(99.9995)
    assert ratcheted_sl is False
    assert time_exit is True


def test_v421_policy_family_and_risk_sizing_in_detector() -> None:
    """Verify v4.0.21 6-policy family admission, Mốc 6 Fibo 0.886 SL, and 0.5% NAV risk sizing."""
    cfg = FiboTrendShortConfig(min_prior_pump_pct=0.08, min_impulse_drop_pct=0.04)
    base_time = datetime(2025, 5, 1, 0, 0, tzinfo=timezone.utc)
    htf_candles = _make_htf_reversal_candles(base_time, step_hours=4)
    h1_candles = [
        {"open_time": "2025-05-03T20:00:00+00:00", "open": 112.0, "high": 114.5, "low": 111.8, "close": 114.0, "volume": 500.0},
        {"open_time": "2025-05-03T21:00:00+00:00", "open": 114.0, "high": 116.2, "low": 113.8, "close": 115.8, "volume": 600.0},
        {"open_time": "2025-05-03T22:00:00+00:00", "open": 115.8, "high": 117.5, "low": 115.4, "close": 117.0, "volume": 700.0},
        {"open_time": "2025-05-03T23:00:00+00:00", "open": 117.2, "high": 118.2, "low": 114.4, "close": 114.6, "volume": 600.0},
    ]

    sig = evaluate_symbol_timeframe("SOLUSDT", "4h", htf_candles, h1_candles, cfg)
    assert sig is not None
    assert sig.stage == "FIRED_CONFIRMED_SHORT"
    assert sig.trade_setup.sl_m6 < sig.trade_setup.stop_loss
    assert sig.trade_setup.sl_m6_pct < sig.trade_setup.stop_loss_pct
    assert sig.trade_setup.rr_m6_tp1 > sig.trade_setup.rr_tp1
    assert 0.0 < sig.trade_setup.recommended_notional_pct <= 20.0
    assert "m1_f1a_pump50" in sig.eligible_milestones
    assert "m6_f4_sniper" in sig.eligible_milestones
    assert "sniper_risk" in sig.matched_policies
    assert "sniper_rr1_horizon24" in sig.matched_policies
    assert sig.primary_policy == "sniper_rr1_horizon24"


def test_v421_rolling_pit_top50_universe_selection() -> None:
    """Verify rolling_pit_top50 universe mode loads the 50-coin PIT membership and excludes BTCUSDT."""
    from dao_vang.config.settings import AppSettings
    from dao_vang.fibo_short.scanner_lane import (
        load_latest_pit_top50_membership,
        select_candidate_symbols,
    )

    pit = load_latest_pit_top50_membership()
    assert pit["month"] is not None
    assert len(pit["members"]) >= 45
    assert all(m["wick_p90_pct"] <= 3.2 for m in pit["members"])

    settings_pit50 = AppSettings(
        fibo_trend_short=FiboTrendShortConfig(universe_mode="rolling_pit_top50", max_candidates=50)
    )
    syms = select_candidate_symbols(settings_pit50, tickers_override=[])
    assert "BTCUSDT" not in syms
    assert "SOLUSDT" in syms
    assert len(syms) == 50


def test_v421_parallel_shadow_comparison_ledger(tmp_path: Path) -> None:
    """Verify parallel shadow tracking comparing Legacy M1 Raw vs v4.0.21 Policies (ratcheted SL & noise filtering)."""
    from dao_vang.fibo_short.scanner_lane import FiboStateStore

    cfg = FiboTrendShortConfig(min_prior_pump_pct=0.08, min_impulse_drop_pct=0.04)
    base_time = datetime(2025, 5, 1, 0, 0, tzinfo=timezone.utc)
    htf_candles = _make_htf_reversal_candles(base_time, step_hours=4)
    h1_candles = [
        {"open_time": "2025-05-03T20:00:00+00:00", "open": 112.0, "high": 114.5, "low": 111.8, "close": 114.0, "volume": 500.0},
        {"open_time": "2025-05-03T21:00:00+00:00", "open": 114.0, "high": 116.2, "low": 113.8, "close": 115.8, "volume": 600.0},
        {"open_time": "2025-05-03T22:00:00+00:00", "open": 115.8, "high": 117.5, "low": 115.4, "close": 117.0, "volume": 700.0},
        {"open_time": "2025-05-03T23:00:00+00:00", "open": 117.2, "high": 118.2, "low": 114.4, "close": 114.6, "volume": 600.0},
    ]

    sig = evaluate_symbol_timeframe("SOLUSDT", "4h", htf_candles, h1_candles, cfg)
    assert sig is not None
    store = FiboStateStore(tmp_path / "shadow_state.sqlite3")
    store.upsert_signal(sig, "2025-05-03T23:05:00+00:00")

    # Simulate price dropping to TP1 first, then bouncing back to entry_price (Breakeven)
    tp1_px = sig.trade_setup.tp1
    entry_px = sig.trade_setup.entry_price
    summary1 = store.refresh_and_build_shadow_comparison({"SOLUSDT": tp1_px * 0.999}, "2025-05-04T02:00:00+00:00")
    assert summary1["total_fired_signals"] == 1
    row1 = summary1["signals_ledger"][0]
    assert row1["legacy"]["tp1_hit"] is True
    assert row1["v4"]["tp1_hit"] is True
    assert row1["v4"]["status"] == "TP1_HIT_RATCHET_BE"

    # Now price bounces back to entry_price: v4 ratcheted stop locks BE on remaining legs, while Legacy stays open!
    summary2 = store.refresh_and_build_shadow_comparison({"SOLUSDT": entry_px * 1.001}, "2025-05-04T04:00:00+00:00")
    row2 = summary2["signals_ledger"][0]
    assert row2["v4"]["be_stop_hit"] is True
    assert row2["v4"]["status"] == "TP1_LOCKED_BE_STOP"
    assert len(summary2["tracks"]) == 5


def test_v421_telegram_only_dispatches_qualified_short_signals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that only FIRED_CONFIRMED_SHORT signals meeting v4.0.21 Short standards are dispatched to Telegram."""
    import dataclasses
    import json
    import sqlite3
    from dao_vang.config.settings import AppSettings, PathsConfig, TelegramConfig, WebConfig
    from dao_vang.fibo_short import scanner_lane as sl_mod
    from dao_vang.fibo_short.scanner_lane import (
        format_fibo_telegram_message,
        is_qualified_short_for_telegram,
        run_cycle,
    )

    cfg = FiboTrendShortConfig(
        higher_timeframes=["4h"],
        min_prior_pump_pct=0.08,
        min_impulse_drop_pct=0.04,
        telegram_enabled=True,
        telegram_require_qualified_short=True,
    )
    base_time = datetime(2025, 5, 1, 0, 0, tzinfo=timezone.utc)
    htf_candles = _make_htf_reversal_candles(base_time, step_hours=4)
    h1_candles = [
        {"open_time": "2025-05-03T20:00:00+00:00", "open": 112.0, "high": 114.5, "low": 111.8, "close": 114.0, "volume": 500.0},
        {"open_time": "2025-05-03T21:00:00+00:00", "open": 114.0, "high": 116.2, "low": 113.8, "close": 115.8, "volume": 600.0},
        {"open_time": "2025-05-03T22:00:00+00:00", "open": 115.8, "high": 117.5, "low": 115.4, "close": 117.0, "volume": 700.0},
        {"open_time": "2025-05-03T23:00:00+00:00", "open": 117.2, "high": 118.2, "low": 114.4, "close": 114.6, "volume": 600.0},
    ]

    sig_qualified = evaluate_symbol_timeframe("SOLUSDT", "4h", htf_candles, h1_candles, cfg)
    assert sig_qualified is not None
    assert sig_qualified.stage == "FIRED_CONFIRMED_SHORT"
    assert is_qualified_short_for_telegram(sig_qualified, cfg) is True

    # Build a raw M1/M6-only signal (like JASMYUSDT without H1 structure break) that failed Sniper gates
    sig_unqualified = dataclasses.replace(
        sig_qualified,
        id="fibo_noise_m6_only",
        symbol="DOGEUSDT",
        eligible_milestones=["m1_f1a_pump50", "m6_f4_expanded"],
        matched_policies=["reference_m6_fixed", "m6_risk"],
        primary_policy="m6_risk",
    )
    assert sig_unqualified.stage == "FIRED_CONFIRMED_SHORT"
    assert is_qualified_short_for_telegram(sig_unqualified, cfg) is False

    # Verify minimalist Telegram message formatting includes concise v4.0.21 Short setup details
    msg = format_fibo_telegram_message(sig_qualified, public_url="https://daovang.comaygiauco.com")
    assert "🔻 <b>SHORT SOLUSDT</b>" in msg
    assert "SL (0.886):" in msg
    assert "dời SL hòa vốn" in msg
    assert "dời SL về TP1" in msg
    assert "% NAV" in msg
    assert len(msg.splitlines()) <= 10

    # Verify run_cycle dispatches ONLY the qualified signal to Telegram
    sent_messages: list[str] = []

    class FakeNotifier:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
            sent_messages.append(text)
            return True

    import dao_vang.alerts.telegram as tg_mod

    monkeypatch.setattr(tg_mod, "TelegramNotifier", FakeNotifier)
    monkeypatch.setattr(
        sl_mod,
        "_scan_single_symbol",
        lambda sym, base_url, c: [sig_qualified] if sym == "SOLUSDT" else ([sig_unqualified] if sym == "DOGEUSDT" else []),
    )
    monkeypatch.setattr(sl_mod, "fetch_all_tickers", lambda base_url: [])

    settings = AppSettings(
        paths=PathsConfig(data_dir=tmp_path),
        telegram=TelegramConfig(bot_token="fake_token", chat_id="fake_chat_id"),
        web=WebConfig(public_url="https://daovang.comaygiauco.com"),
        fibo_trend_short=cfg,
    )
    result = run_cycle(settings, symbols=["SOLUSDT", "DOGEUSDT"])
    assert result["fired_count"] == 2
    assert result["qualified_fired_count"] == 1
    assert result["telegram_sent_this_cycle"] == 1
    assert len(sent_messages) == 1
    assert "SOLUSDT" in sent_messages[0]
    assert "DOGEUSDT" not in sent_messages[0]

    # Verify SQLite persistence of telegram_sent in both column and payload_json
    conn = sqlite3.connect(tmp_path / "fibo_trend_short" / "state.sqlite3")
    conn.row_factory = sqlite3.Row
    sol_row = conn.execute("SELECT telegram_sent, payload_json FROM fibo_signals WHERE symbol = 'SOLUSDT'").fetchone()
    doge_row = conn.execute("SELECT telegram_sent, payload_json FROM fibo_signals WHERE symbol = 'DOGEUSDT'").fetchone()
    conn.close()
    assert sol_row["telegram_sent"] == 1
    assert json.loads(sol_row["payload_json"])["telegram_sent"] is True
    assert doge_row["telegram_sent"] == 0
    assert json.loads(doge_row["payload_json"])["telegram_sent"] is False









