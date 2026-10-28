"""Attribution must reconcile fills, held inventory and signed funding."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
spec=importlib.util.spec_from_file_location("cost_legacy_examples",Path(__file__).with_name("test_account_scaled_replay.py"))
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
from execution_cost_attribution import attribute
from account_scaled_replay import simulate


def test_market_exit_decomposition_includes_actual_slippage_and_funding():
    r,args=legacy.run([100,97,99],legacy.trail(),funding=[(300000,-.001,97)])
    a=attribute(r,args[2]);q=next(j["qty"] for j in r["journal"] if j["kind"]=="entry")
    assert a["price_pnl_at_reference"]==pytest.approx(q*(100-99))
    assert a["slippage_paid"]==pytest.approx(q*(100+99)*.002)
    assert a["funding"]==pytest.approx(-q*97*.001)
    assert a["net_marked_pnl"]==pytest.approx(r["ending_equity"]-500)


def test_open_position_stays_marked_without_invented_exit_fee():
    r,args=legacy.run([100,102],legacy.trail(),funding=[(300000,.001,102)])
    a=attribute(r,args[2]);q=r["open_positions"][0]["qty"]
    assert a["price_pnl_at_reference"]==pytest.approx(-2*q)
    assert a["slippage_paid"]==pytest.approx(100*q*.002)
    assert a["reference_turnover"]==pytest.approx(100*q)
    assert a["commissions"]==pytest.approx(r["open_positions"][0]["entry_fee"])


def test_staged_quantities_and_funding_are_not_assumed_full_size():
    r,args=legacy.run([100,99,98,97],dict(dict(legacy.split(),**legacy.trail()),activation_atr=3),funding=[(300000,.001,99)])
    a=attribute(r,args[2])
    assert r["open_positions"][0]["filled_parts"]==3
    assert a["slippage_paid"]==pytest.approx(a["reference_turnover"]*.002)
    assert a["net_marked_pnl"]==pytest.approx(r["pnl"])


def test_zero_execution_cost_keeps_real_funding():
    _,args=legacy.run([100,97,99],legacy.trail(),funding=[(300000,-.001,97)])
    cfg=SimpleNamespace(**dict(args[-1].model_dump(),fee_rate=0,max_slippage_bps=0))
    r=simulate(*args[:-1],cfg,research_policy=legacy.trail())
    a=attribute(r,args[2]);assert a["slippage_paid"]==0 and a["commissions"]==0 and a["funding"]<0
    assert a["net_marked_pnl"]==pytest.approx(a["price_pnl_at_reference"]+a["funding"])


def test_incomplete_path_does_not_get_fictional_attributed_ending():
    r,args=legacy.run([100,10000],legacy.trail())
    assert r["ending_equity"] is None
    a=attribute(r,args[2]);assert not a["complete"] and a["net_marked_pnl"] is None


def test_limit_fills_are_not_mislabeled_as_market_slippage():
    r,args=legacy.run([100,50],dict(fixed_tp_usdt=1))
    with pytest.raises(ValueError,match="limit_exit"):
        attribute(r,args[2])
