import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("flow_branch", ROOT / "scripts/research_branches_20261012/flow_branch.py")
flow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(flow)


def test_funding_two_distinct_events_are_not_duplicate_data():
    rows = pd.DataFrame({"funding_time": pd.to_datetime(["2026-01-01T00:00Z", "2026-01-01T01:00Z", "2026-01-01T02:00Z", "2026-01-01T04:00Z"]), "funding_rate": [.001, .002, .003, .004]})
    audit = flow.funding_diagnostics(rows)
    assert audit["distinct_events_collapsed"] == 2
    assert audit["distinct_hour_settlements_collapsed"] == 2
    assert audit["same_hour_timestamp_duplicates"] == 0
    assert audit["off_4h_boundary_events"] == 2
    assert audit["shifted_earlier_more_than_60_seconds"] == 2
    assert audit["rate_sum_raw"] == pytest.approx(.01)
    assert audit["rate_sum_loader"] == pytest.approx(.007)
    assert audit["max_seconds_shifted_earlier"] == 7200


def test_protocol_cannot_be_overwritten(tmp_path):
    flow.freeze_protocol(tmp_path)
    with pytest.raises(FileExistsError):
        flow.freeze_protocol(tmp_path)


def test_selection_does_not_use_test_performance():
    rows = pd.DataFrame([
        {"id": "a", "family": "composite", "val_calmar": 3, "test_calmar": -99, "params": "{}"},
        {"id": "b", "family": "composite", "val_calmar": 2, "test_calmar": 99, "params": "{}"},
        {"id": "c", "family": "mkt_flow", "val_calmar": 1, "test_calmar": -1, "params": "{}"},
    ])
    assert [row["id"] for row in flow.select_representatives(rows, {"a", "b", "c"})] == ["a", "c"]


def make_panel(funding):
    from dao_vang.nostop.data import Panel
    one = np.ones((4, 1))
    return Panel(pd.date_range("2026-01-01", periods=4, freq="4h", tz="UTC"), ["TEST"], one, one, one, one, one, one, one, np.array(funding).reshape(4, 1))


def test_actual_engine_next_open_and_funding_before_rebalance():
    from dao_vang.nostop.engine import simulate
    panel = make_panel([0, .1, .1, 0])
    weights = np.array([[.5], [0], [0], [0]])
    result = simulate(panel, weights, np.ones(4, dtype=bool), 0, 3, np.zeros((4, 1)), keep_pos=True)
    assert result.pos[:, 0].tolist() == [0, .5, 0, 0]
    # Open at 04h: does not pay settlement before entry; closes 08h after paying.
    assert result.funding == pytest.approx(-.05)
    assert result.equity[-1] == pytest.approx(.95)


def test_missing_coverage_is_not_claimed_complete():
    rows = pd.DataFrame({"funding_time": pd.to_datetime([], utc=True), "funding_rate": []})
    assert flow.funding_diagnostics(rows)["events"] == 0


def test_engine_future_availability_changes_current_execution():
    from dao_vang.nostop.engine import simulate
    weights = np.array([[.5], [0], [0], [0]])
    rebalance = np.ones(4, dtype=bool)
    baseline = simulate(make_panel([0, 0, 0, 0]), weights, rebalance, 0, 3, np.zeros((4, 1)), keep_pos=True)
    missing_future = make_panel([0, 0, 0, 0])
    # Copy because helper shares OHLC; change ONLY future open, keeping all else.
    missing_future.open = missing_future.open.copy()
    missing_future.open[2, 0] = np.nan
    changed = simulate(missing_future, weights, rebalance, 0, 3, np.zeros((4, 1)), keep_pos=True)
    assert baseline.pos[1, 0] == .5
    assert changed.pos[1, 0] == 0


def test_engine_missing_future_marks_held_position_flat():
    from dao_vang.nostop.engine import simulate
    panel = make_panel([0, 0, 0, 0])
    panel.open = panel.open.copy()
    panel.open[3, 0] = np.nan
    weights = np.full((4, 1), .5)
    rebalance = np.array([True, False, False, False])
    result = simulate(panel, weights, rebalance, 0, 3, np.zeros((4, 1)), keep_pos=True)
    assert result.pos[2, 0] == .5
    assert result.equity[-1] == 1.0


def test_timestamp_milliseconds_do_not_count_as_material_shift():
    rows = pd.DataFrame({"funding_time": pd.to_datetime(["2026-01-01T00:00:00.003Z"]), "funding_rate": [.001]})
    audit = flow.funding_diagnostics(rows)
    assert audit["off_4h_boundary_events"] == 1
    assert audit["shifted_earlier_more_than_60_seconds"] == 0
