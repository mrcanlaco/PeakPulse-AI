"""Economic and causal invariants for the offline entry allocation fork."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("entry_legacy_examples", Path(__file__).with_name("test_account_scaled_replay.py"))
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
from account_entry_replay import simulate


@pytest.mark.parametrize("example", [n for n in vars(legacy) if n.startswith("test_")])
def test_legacy_economic_examples_are_unchanged(monkeypatch, example):
    monkeypatch.setattr(legacy, "simulate", simulate)
    getattr(legacy, example)()


def run(closes, policy, **kwargs):
    _, args = legacy.run(closes, dict(fixed_tp_usdt=5), **kwargs)
    return simulate(*args, research_policy=policy)


def policy(**kw):
    return dict(dict(entry_parts=3, entry_mode="favorable", entry_step_atr=.5,
                     add_expiry_hours=6, trailing=True, activation_atr=.5,
                     callback_fraction=.01, fixed_tp_usdt=5,
                     cancel_adds_on_trail_activation=False), **kw)


def test_keep_planned_adds_after_activation_conserves_budget_and_funding():
    r = run([100,98,96,95],policy(),funding=[(300000,.01,98),(600000,-.02,96)])
    fills=[j for j in r["journal"] if j["kind"] in ["entry","entry_add"]]
    assert len(fills)==3 and sum(j["price"]*j["qty"] for j in fills)<=25
    assert r["open_positions"][0]["trail_active"]
    assert r["funding"]==pytest.approx(fills[0]["qty"]*98*.01-(fills[0]["qty"]+fills[1]["qty"])*96*.02)
    assert r["curve"][1]["committed_margin"]>r["open_positions"][0]["qty"]*95/5*.6


def test_pause_blocks_adds_even_when_keep_after_activation_enabled():
    r=run([100,1400,98,96],policy())
    assert r["entry_paused"] and not any(j["kind"]=="entry_add" for j in r["journal"])


def test_trailing_exit_takes_priority_over_addition():
    r=run([100,98,96,97],policy())
    exit=next(j for j in r["journal"] if j["kind"]=="trailing_exit")
    assert exit["at"]==900000
    assert not any(j["kind"]=="entry_add" and j["at"]==exit["at"] for j in r["journal"])
    assert not r["open_positions"]


def test_expired_plan_does_not_add_after_activation():
    r=run([100,98,96],policy(add_expiry_hours=.01))
    assert not any(j["kind"]=="entry_add" for j in r["journal"])
    assert r["open_positions"][0]["adds_cancelled"]


def test_pullback_requires_favorable_move_then_bounce_for_each_part():
    r=run([100,98,98.6,97,97.6,97.6],policy(entry_mode="pullback",pullback_atr=.25,activation_atr=3))
    adds=[j for j in r["journal"] if j["kind"]=="entry_add"]
    assert [j["at"] for j in adds]==[600000,1200000]
    assert r["open_positions"][0]["filled_parts"]==3


def test_same_bounce_does_not_fill_two_parts():
    r=run([100,97,98,98,98,98],policy(entry_mode="pullback",pullback_atr=.25,activation_atr=3))
    assert sum(j["kind"]=="entry_add" for j in r["journal"])==1


def test_pullback_above_average_entry_does_not_add_to_losing_position():
    r=run([100,98,101,101],policy(entry_mode="pullback",pullback_atr=.25,activation_atr=3))
    assert not any(j["kind"]=="entry_add" for j in r["journal"])


def test_gap_cannot_be_used_to_reject_an_already_triggered_pullback():
    r=run([100,98,98.6,98],policy(entry_mode="pullback",pullback_atr=.25,activation_atr=3),openings=[100,98,105,98])
    add=next(j for j in r["journal"] if j["kind"]=="entry_add")
    assert add["price"]==pytest.approx(105*.998)


def test_terminal_pullback_keeps_inventory_without_missing_fill():
    r=run([100,98,98.6],policy(entry_mode="pullback",pullback_atr=.25,activation_atr=3),openings=[100,98,float("nan")])
    assert not r["errors"] and r["ending_equity"] is not None
    assert not any(j["kind"]=="entry_add" for j in r["journal"])


def test_future_prices_cannot_change_earlier_entries():
    p=policy(entry_mode="pullback",pullback_atr=.25,activation_atr=3)
    a=run([100,98,98.6,97,97.6,80],p);b=run([100,98,98.6,97,97.6,120],p)
    assert [j for j in a["journal"] if j["at"]<1500000]==[j for j in b["journal"] if j["at"]<1500000]
    assert a["curve"][:-1]==b["curve"][:-1]


@pytest.mark.parametrize("extra",[dict(pullback_atr=0),dict(pullback_atr=float("nan")),dict(entry_step_atr=-1),dict(cancel_adds_on_trail_activation="false")])
def test_reject_ambiguous_new_policy(extra):
    with pytest.raises(ValueError):
        run([100,98],policy(**dict(dict(entry_mode="pullback",pullback_atr=.25),**extra)))
