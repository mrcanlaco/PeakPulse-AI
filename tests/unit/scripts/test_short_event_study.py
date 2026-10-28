import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from short_event_study import event_return, outcomes, statistics  # noqa: E402


def test_short_costs_and_funding_have_correct_sign():
    assert event_return(100, 90, 1, 0, 0) == pytest.approx(0.11)
    assert event_return(100, 100, 0, 0.001, 0) == pytest.approx(-0.002)
    assert event_return(100, 100, 0, 0, 20) < -0.004


def test_window_censoring_and_funding_boundaries():
    signals = [
        dict(at=0, symbol="X", event_id="a"),
        dict(at=3600000, symbol="X", event_id="b"),
    ]
    prices = {"X": {0: dict(entry_open=100), 3600000: dict(entry_open=90)}}
    funding = {"X": [(0, 1, 100), (3600000, 0.01, 90)]}
    rows, counts = outcomes(signals, prices, funding, 0, 7200000, 1)
    assert counts == dict(source=2, complete=1, censored=1, missing=0)
    assert rows[0]["funding_per_unit"] == pytest.approx(0.9)


def test_missing_exit_is_reported_not_replaced():
    rows, counts = outcomes(
        [dict(at=0, symbol="X", event_id="a")],
        {"X": {0: dict(entry_open=100)}},
        {"X": []},
        0,
        7200000,
        1,
    )
    assert not rows and counts["missing"] == 1


def test_cluster_bootstrap_constant_zero_edge_and_empty():
    rows = [
        dict(at=i * 86400000, entry_open=100, exit_open=100, funding_per_unit=0)
        for i in range(30)
    ]
    result = statistics(rows, 0, 30 * 86400000, 0, 0)
    assert result["ci95"] == [0, 0]
    assert result["events"] == 30
    assert statistics([], 0, 30 * 86400000, 0, 0)["mean_net_return"] is None
