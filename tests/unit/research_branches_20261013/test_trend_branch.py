import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("trend_round2", ROOT / "scripts/research_branches_20261013/trend_branch.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture():
    hours = pd.date_range("2026-01-01", periods=96, freq="h", tz="UTC")
    bars = hours[::4]
    prices = {"BTCUSDT": pd.DataFrame({"open": 100., "close": 100.}, index=hours)}
    features = {"BTCUSDT": {key: np.full(len(bars), value) for key, value in {
        "close": 100., "ema450": 80., "atr14": 2., "ema40": 80., "donchian_30": 90.,
        "mom14": .1, "ann_vol": .36}.items()}}
    funding = {"BTCUSDT": pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))}
    return prices, bars, features, funding, hours


def test_future_close_does_not_change_prior_equity_or_funding():
    p, b, f, r, h = fixture()
    r["BTCUSDT"] = pd.Series([.01], index=[h[48]])
    a, aa = m.simulate(p, b, f, r, h[0], h[-1], m.VARIANTS["baseline_corrected"])
    p["BTCUSDT"].loc[h[60]:, "close"] = 200
    z, zz = m.simulate(p, b, f, r, h[0], h[-1], m.VARIANTS["baseline_corrected"])
    assert np.array_equal(a.iloc[:60], z.iloc[:60])
    assert aa["funding_paid"] == zz["funding_paid"] == 50


def test_funding_settlement_before_same_timestamp_entry():
    p, b, f, r, h = fixture()
    r["BTCUSDT"] = pd.Series([.01, .01], index=[h[28], h[28] + pd.Timedelta(milliseconds=3)])
    _, account = m.simulate(p, b, f, r, h[0], h[-1], m.VARIANTS["baseline_corrected"])
    assert account["funding_paid"] == 50
    assert len([row for row in account["ledger"] if row["kind"] == "funding"]) == 1


def test_extra_four_hour_delay_is_actually_executed_later():
    p, b, f, r, h = fixture()
    _, a = m.simulate(p, b, f, r, h[0], h[-1], m.VARIANTS["baseline_corrected"])
    _, z = m.simulate(p, b, f, r, h[0], h[-1], m.VARIANTS["delay_4h"])
    assert pd.Timestamp(z["ledger"][0]["time"]) - pd.Timestamp(a["ledger"][0]["time"]) == pd.Timedelta(hours=4)


def test_missing_execution_price_fails_closed():
    p, b, f, r, h = fixture()
    p["BTCUSDT"].loc[h[30], "open"] = np.nan
    with pytest.raises(ValueError, match="Missing or invalid"):
        m.simulate(p, b, f, r, h[0], h[-1], m.VARIANTS["baseline_corrected"])


def test_flat_macro_slope_blocks_entries_without_future_knowledge():
    p, b, f, r, h = fixture()
    _, a = m.simulate(p, b, f, r, h[0], h[-1], m.VARIANTS["macro_slope"])
    assert not a["ledger"]


def test_daily_export_explicitly_unverified_funding_and_normalization():
    p, b, f, r, h = fixture()
    nav, _ = m.simulate(p, b, f, r, h[0], h[-1], m.VARIANTS["baseline_corrected"])
    result = m.export_equity(nav, "baseline_corrected")
    assert result["rows"][0]["equity"] == 10000
    assert not result["funding_coverage_verified"]
    assert result["metric_basis"] == "account_equity"
    assert result["is_baseline"] is True
    assert m.export_equity(nav, "delay_4h")["is_baseline"] is False
    assert m.export_equity(nav, "baseline_corrected_cost2x")["is_baseline"] is False
