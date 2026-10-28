import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from short_entry_timing import definitions, transform  # noqa: E402


def run(values, ident, end=None):
    signals = [dict(at=0, symbol="X", event_id="one", atr=2, probability=0.7)]
    prices = {
        "X": {
            i * 300000: dict(execution_close=v, entry_open=99999)
            for i, v in enumerate(values)
        }
    }
    spec = next(s for s in definitions() if s["id"] == ident)
    return transform(signals, prices, 0, end or len(values) * 300000, spec)


def test_immediate_preserves_source_contract():
    signals, audit = run([100], "immediate")
    assert signals == [dict(at=0, symbol="X", event_id="one", atr=2, probability=0.7)]
    assert audit["counts"] == {"triggered": 1}


def test_rebound_uses_closed_price_not_future_open():
    signals, audit = run([100, 100.5, 101], "rebound0.5")
    assert signals[0]["at"] == 600000
    assert signals[0]["atr"] == 2
    assert audit["events"][0]["improvement_atr"] == 0.5


def test_breakdown_waits_for_threshold():
    signals, _ = run([100, 99.5, 99, 98], "breakdown1")
    assert signals[0]["at"] == 900000


def test_rejection_requires_prior_arm_and_drop_from_running_peak():
    signals, _ = run([100, 101, 102, 101.75, 101.5], "rejection0.5")
    assert signals[0]["at"] == 1200000


def test_delay_does_not_choose_favorable_future_open():
    signals, _ = run([100, 120, 150, 200], "delay15")
    assert signals[0]["at"] == 900000


def test_window_boundary_does_not_fabricate_entry():
    signals, audit = run([100, 100, 100, 101], "rebound0.5", end=900000)
    assert not signals
    assert audit["counts"] == {"end_pending": 1}


def test_expired_watches_and_missing_data_are_distinct():
    assert run([100] * 75, "rebound1")[1]["counts"] == {"expired": 1}
    assert run([100, float("nan"), 102], "rebound1")[1]["counts"] == {"missing_data": 1}


def test_future_changes_do_not_change_earlier_triggers():
    a, _ = run([100, 101, 100.5, 70, 150], "rejection0.5")
    b, _ = run([100, 101, 100.5, 200, 10], "rejection0.5")
    assert a == b
