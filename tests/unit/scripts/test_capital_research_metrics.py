import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"scripts"))
from capital_research_metrics import audit_account,utilization


def sample():
    return dict(initial_equity=500,ending_equity=498,pnl=-2,closed_trade_net=-2,
                journal=[dict(at=0,kind="entry",symbol="X",event_id="e",qty=2,price=50),
                         dict(at=100,kind="tp",symbol="X",event_id="e",price=51,net=-2,held_hours=24)],
                open_positions=[],rejections={"position_limit":3,"drawdown_paused":1})


def test_allocation_aware_budget_does_not_assume_25():
    assert audit_account(sample(),100)["max_entry_notional"]==100
    with pytest.raises(AssertionError):audit_account(sample(),25)


def test_staged_budget_counts_all_fills_and_rejects_duplicate_coin():
    r=sample()
    r["journal"].insert(1,dict(at=50,kind="entry_add",symbol="X",event_id="e",qty=1,price=50))
    with pytest.raises(AssertionError):audit_account(r,100)
    r=sample()
    r["journal"].insert(1,dict(at=50,kind="entry",symbol="X",event_id="f",qty=1,price=50))
    with pytest.raises(AssertionError):audit_account(r,200)


def test_utilization_is_duration_weighted_and_ignores_terminal_state():
    curve=[dict(at=0,positions=1,paused=False,committed_margin=20),
           dict(at=100,positions=5,paused=True,committed_margin=40),
           dict(at=400,positions=0,paused=False,committed_margin=0)]
    r=utilization(curve,sample(),100)
    assert r["mean_positions"]==4
    assert r["fraction_time_all_slots_used"]==.75
    assert r["fraction_time_paused"]==.75
    assert r["mean_committed_margin"]==35
    assert r["entry_turnover_multiple"]==.2


def test_truncated_paths_cannot_be_reported_as_complete_returns():
    r=sample();r.update(ending_equity=None,pnl=None)
    curve=[dict(at=0,positions=1,paused=False,committed_margin=20),
           dict(at=100,positions=1,paused=True,committed_margin=40)]
    m=utilization(curve,r,100)
    assert not m["complete"] and m["net_pnl_to_entry_turnover"] is None
