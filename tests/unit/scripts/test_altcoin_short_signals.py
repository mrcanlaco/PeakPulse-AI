"""Prevent future candles, funding, and missing bars from creating fake signals."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from altcoin_short_signals import generate, hourly_features  # noqa: E402
from search_altcoin_families import daily_interval  # noqa: E402


def raw_bars(hours=180):
    at = pd.date_range("2026-06-01", periods=hours * 12, freq="5min", tz="UTC")
    price = 100 + np.sin(np.arange(len(at)) / 27) * 8 - np.arange(len(at)) / 200
    return pd.DataFrame(
        dict(
            open_time=at,
            open=price + 0.1,
            high=price + 0.4,
            low=price - 0.4,
            close=price,
            quote_volume=50000.0,
        )
    )


def test_hourly_features_do_not_change_when_future_prices_are_appended():
    raw = raw_bars()
    cutoff = raw.open_time.iloc[150 * 12]
    prefix = hourly_features(raw[raw.open_time < cutoff])
    raw.loc[raw.open_time >= cutoff, ["open", "high", "low", "close"]] *= 100
    full = hourly_features(raw)
    pd.testing.assert_frame_equal(prefix, full.loc[prefix.index], check_freq=False)


def test_partial_hour_and_recent_gap_are_not_trade_ready():
    raw = raw_bars(160)
    missing_at = raw.open_time.iloc[145 * 12 + 3]
    h = hourly_features(raw[raw.open_time != missing_at])
    assert h.ready.iloc[140]
    assert not h.ready.iloc[145:].any()
    partial = hourly_features(raw.iloc[:-1])
    assert not partial.ready.iloc[-1]
    assert pd.isna(partial.close.iloc[-1])


def toy_frames(index):
    x = pd.DataFrame(
        dict(
            close=100.0,
            open=110.0,
            prior_close=105.0,
            ema20=102.0,
            ema60=103.0,
            prior_ema20=102.0,
            ret24=0.2,
            ret6=0.1,
            wick=0.6,
            atr=2.0,
            ready=True,
            volume24=3e6,
            low24=90.0,
            low48=85.0,
        ),
        index=index,
    )
    btc = x.copy()
    btc["ret24"] = -0.1
    return {"TESTUSDT": x, "BTCUSDT": btc}


def spec(funding="any"):
    return dict(
        id="test", family="failed_pump", strength="loose", btc="any", funding=funding
    )


def test_funding_settled_just_before_signal_is_not_known_yet():
    at = pd.Timestamp("2026-06-24T12:00:00Z")
    ms = int(at.timestamp() * 1000)
    frames = toy_frames(pd.DatetimeIndex([at]))
    funding = {
        "TESTUSDT": [
            (ms - 7200000, -0.001, 100),
            (ms - 1, 0.01, 100),
            (ms + 1000, 0.02, 100),
        ]
    }
    assert generate(frames, funding, [spec("nonnegative")])["test"] == []
    funding["TESTUSDT"][0] = (ms - 7200000, 0.001, 100)
    assert len(generate(frames, funding, [spec("nonnegative")])["test"]) == 1


def test_cross_section_and_signals_are_prefix_invariant():
    index = pd.date_range("2026-06-24", periods=60, freq="1h", tz="UTC")
    frames = toy_frames(index)
    funding = {"TESTUSDT": []}
    full = generate(frames, funding, [spec()])["test"]
    prefix = generate({k: f.iloc[:30] for k, f in frames.items()}, funding, [spec()])[
        "test"
    ]
    cutoff = int(index[30].timestamp() * 1000)
    assert prefix == [s for s in full if s["at"] < cutoff]
    assert len(full) == 3
    assert all(b["at"] - a["at"] >= 86400000 for a, b in zip(full, full[1:]))


def test_daily_block_bootstrap_preserves_account_pnl():
    start = int(pd.Timestamp("2026-06-24T00:00:00Z").timestamp() * 1000)
    curve = [dict(at=start + i * 86400000, equity=500.0 + i) for i in range(32)]
    interval = daily_interval(curve)
    assert interval["days"] == 31
    assert interval["total"] == pytest.approx(31)
    assert interval["ci95_daily"] == pytest.approx([1, 1])
