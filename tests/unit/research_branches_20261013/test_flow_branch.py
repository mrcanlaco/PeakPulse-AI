import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from dao_vang.nostop.data import Panel

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('flow_round2', ROOT / 'scripts/research_branches_20261013/flow_branch.py')
flow = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(flow)

def panel():
    a = np.ones((4, 1))
    return Panel(pd.date_range('2026-01-01', periods=4, freq='4h', tz='UTC'), ['X'], a.copy(), a.copy(), a.copy(), a.copy(), a.copy(), a.copy(), a.copy(), np.zeros_like(a))

def test_all_intrabar_events_preserved_and_entry_does_not_pay_prior_funding():
    p = panel(); w = np.full((4, 1), .5); re = np.array([True, False, False, False])
    events = {1: [(p.index[1], 0, .1, 1), (p.index[1] + pd.Timedelta('1h'), 0, .1, 1), (p.index[1] + pd.Timedelta('2h'), 0, .1, 1)]}
    r = flow.replay(p, w, re, events, np.zeros_like(w), 0, 3)
    assert r['funding_paid_events'] == 2
    assert r['funding_initial_equity'] == pytest.approx(-.1)
    assert r['equity'][-1] == pytest.approx(.9)

def test_future_missing_does_not_skip_current_trade_but_fails_valuation():
    p = panel(); p.open[2, 0] = np.nan
    w = np.full((4, 1), .5)
    r = flow.replay(p, w, np.ones(4, bool), {}, np.zeros_like(w), 0, 3)
    assert r['trades'] == 1
    assert r['status'] == 'unknown'
    assert r['unknown_reason'].startswith('missing_future_held_valuation')

def test_missing_mark_proxy_is_counted_not_silently_verified():
    p = panel(); w = np.full((4, 1), .5)
    r = flow.replay(p, w, np.array([True, False, False, False]), {2: [(p.index[2], 0, .1, None)]}, np.zeros_like(w), 0, 3)
    assert r['funding_proxy_paid_events'] == 1
    exported = flow.export_equity(p, 0, r, 'test')
    assert exported['funding_coverage_verified'] is False
    assert exported['eligible_for_combination'] is False

def test_timestamp_jitter_normalization_preserves_hourly_settlements():
    t = pd.Series(pd.to_datetime(['2026-01-01T00:00:00.003Z', '2026-01-01T01:00:00.001Z']))
    result = flow.normalize_event_times(t)
    assert result.dt.hour.tolist() == [0, 1]
    assert result.dt.microsecond.tolist() == [0, 0]

def test_daily_export_labels_prior_day_close_and_normalizes_first_close():
    p = panel()
    result = {'equity': list(np.linspace(1, 1.12, 13)), 'status': 'complete'}
    exported = flow.export_equity(p, 0, result, 'test')
    assert exported['rows'][0] == {'date': '2026-01-01', 'equity': 10000.0}
    assert exported['rows'][1]['date'] == '2026-01-02'
    assert exported['rows'][1]['equity'] == pytest.approx(1.12 / 1.06 * 10000)

def test_late_funding_credit_cannot_save_earlier_intrabar_liquidation():
    p = panel(); p.low[1, 0] = .01
    w = np.ones((4, 1)); re = np.array([True, False, False, False])
    late_credit = {1: [(p.index[1] + pd.Timedelta('3h'), 0, -.20, 1)]}
    result = flow.replay(p, w, re, late_credit, np.zeros_like(w), 0, 3)
    without_credit = flow.replay(p, w, re, {}, np.zeros_like(w), 0, 3)
    assert result['status'] == without_credit['status'] == 'liquidated'
    assert result['equity'][-1] == 0
    assert result['funding_initial_equity'] == 0
    assert result['minimum_intrabar_equity'] == pytest.approx(.01)

def test_surviving_bar_gets_credit_after_margin_bound():
    p = panel(); p.low[1, 0] = .5
    w = np.ones((4, 1)); re = np.array([True, False, False, False])
    late_credit = {1: [(p.index[1] + pd.Timedelta('3h'), 0, -.20, 1)]}
    result = flow.replay(p, w, re, late_credit, np.zeros_like(w), 0, 3)
    assert result['status'] == 'complete'
    assert result['equity'][-1] == pytest.approx(1.2)
    assert result['minimum_intrabar_equity'] == pytest.approx(.5)

def test_intrabar_debit_is_conservatively_counted_in_margin_bound():
    p = panel(); p.low[1, 0] = .1
    w = np.ones((4, 1)); re = np.array([True, False, False, False])
    late_debit = {1: [(p.index[1] + pd.Timedelta('3h'), 0, .1, 1)]}
    result = flow.replay(p, w, re, late_debit, np.zeros_like(w), 0, 3)
    assert result['status'] == 'liquidated'
