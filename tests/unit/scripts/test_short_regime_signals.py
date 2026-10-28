import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from altcoin_short_signals import hourly_features  # noqa: E402
from monthly_account_metrics import monthly_metrics  # noqa: E402
from short_regime_signals import features, generate  # noqa: E402


def sample():
    rng = np.random.default_rng(91)
    n = 6000
    close = 100 * np.exp(np.cumsum(rng.normal(-0.0002, 0.005, n)))
    raw = pd.DataFrame(
        dict(
            open_time=pd.date_range("2026-06-01", periods=n, freq="5min", tz="UTC"),
            open=close * 1.001,
            high=close * 1.015,
            low=close * 0.985,
            close=close,
            quote_volume=rng.uniform(10000, 50000, n),
        )
    )
    return hourly_features(raw)


def test_features_and_all_signals_are_prefix_invariant():
    h = sample()
    cut = h.index[350]
    pd.testing.assert_frame_equal(features(h).loc[:cut], features(h.loc[:cut]))
    full = generate({"X": h, "BTCUSDT": h})
    prefix = generate({"X": h.loc[:cut], "BTCUSDT": h.loc[:cut]})
    assert any(full.values())
    at = int(cut.timestamp() * 1000)
    assert {k: [r for r in v if r["at"] <= at] for k, v in full.items()} == prefix


def test_cooldown_and_readiness_enforced():
    h = sample()
    output = generate({"X": h, "BTCUSDT": h})
    for key, rows in output.items():
        hours = int(key.rsplit("h", 1)[1])
        assert all(b["at"] - a["at"] >= hours * 3600000 for a, b in zip(rows, rows[1:]))
    h["ready"] = False
    assert not any(generate({"X": h, "BTCUSDT": h}).values())


def test_fifty_percent_means_compounded_monthly_return():
    good = monthly_metrics(
        [dict(at=t, equity=e) for t, e in [(1, 750), (2, 1125), (3, 1687.5)]],
        boundaries=[0, 1, 2, 3],
    )
    assert good["all_months_50pct"]
    flat_dollars = monthly_metrics(
        [dict(at=t, equity=e) for t, e in [(1, 750), (2, 1000), (3, 1250)]],
        boundaries=[0, 1, 2, 3],
    )
    assert not flat_dollars["all_months_50pct"]


def test_open_losses_and_missing_boundary_cannot_pass():
    result = monthly_metrics(
        [dict(at=1, equity=400), dict(at=2, equity=1000)], boundaries=[0, 1, 2]
    )
    assert not result["all_months_50pct"]
    assert result["min_monthly_return"] < 0
    assert not monthly_metrics([dict(at=1, equity=750)], boundaries=[0, 1, 2])[
        "complete"
    ]
