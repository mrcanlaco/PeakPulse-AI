"""Point-in-time checks for research entry filters, independent of profits."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from search_account_strategies import filter_signals  # noqa: E402


def test_confirmation_uses_closed_prices_not_next_open():
    signals = [dict(symbol="X", at=600000, event_id="x")]
    prices = {
        "X": {
            300000: {"execution_close": 100},
            600000: {"execution_close": 99, "entry_open": 150},
        }
    }
    selected, reasons = filter_signals(signals, prices, {}, "down_bar")
    assert selected == signals
    assert reasons == {}


def test_funding_filter_ignores_new_or_future_positive_settlement():
    signals = [dict(symbol="X", at=600000, event_id="x")]
    prices = {"X": {300000: {"execution_close": 100}, 600000: {"execution_close": 99}}}
    funding = {"X": [(300000, -0.001, 100), (599999, 0.001, 99), (900000, 0.01, 95)]}
    selected, reasons = filter_signals(
        signals, prices, funding, "down_bar_nonnegative_funding"
    )
    assert selected == []
    assert reasons == {"last_known_funding_negative": 1}


def test_funding_filter_rejects_stale_settlement_instead_of_filling():
    at = 36_000_000
    signals = [dict(symbol="X", at=at, event_id="x")]
    prices = {"X": {at - 300000: {"execution_close": 100}, at: {"execution_close": 99}}}
    selected, reasons = filter_signals(
        signals, prices, {"X": [(0, 0.01, 100)]}, "down_bar_nonnegative_funding"
    )
    assert selected == []
    assert reasons == {"last_known_funding_missing_or_stale": 1}


def test_missing_previous_candle_does_not_pass_confirmation():
    signals = [dict(symbol="X", at=600000, event_id="x")]
    selected, reasons = filter_signals(
        signals, {"X": {600000: {"execution_close": 99}}}, {}, "down_bar"
    )
    assert selected == []
    assert reasons == {"confirmation_price_missing": 1}
