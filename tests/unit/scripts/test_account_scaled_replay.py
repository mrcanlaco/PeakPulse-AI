"""Economic invariants for split orders, funding and sampled trailing exits."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from account_backtest_replay import simulate as original  # noqa: E402
from account_scaled_replay import simulate  # noqa: E402

from dao_vang.config.settings import ExecutionConfig  # noqa: E402

RULE = dict(
    market_step="0.001",
    step_size="0.001",
    min_qty=0.001,
    market_min_qty=0.001,
    max_qty=100000,
    market_max_qty=100000,
    min_notional=5,
    tick_size="0.001",
)


def run(
    closes, policy, funding=(), openings=None, rule=None, config=None, signals=None
):
    times = [i * 300000 for i in range(len(closes))]
    quotes = {
        t: dict(mark=c, execution_close=c, entry_open=(openings[i] if openings else c))
        for i, (t, c) in enumerate(zip(times, closes))
    }
    args = (
        times,
        signals or {0: [dict(symbol="X", event_id="one", atr=2)]},
        lambda _: quotes,
        {"X": rule or RULE, "Y": rule or RULE},
        lambda _: funding,
        config or ExecutionConfig(),
    )
    return simulate(*args, research_policy=policy), args


def split(**extra):
    return dict(
        entry_parts=3,
        entry_mode="time",
        entry_interval_minutes=5,
        add_expiry_hours=6,
        fixed_tp_usdt=5,
        **extra,
    )


def trail(**extra):
    return dict(
        trailing=True,
        activation_atr=1,
        callback_fraction=0.01,
        fixed_tp_usdt=5,
        **extra,
    )


def test_one_entry_fixed_exit_reproduces_original_economic_path():
    r, args = run(
        [100, 102, 96, 90], dict(fixed_tp_usdt=2), funding=[(1000, -0.001, 102)]
    )
    old = original(*args, research_policy=dict(fixed_tp_usdt=2))
    for key in [
        "ending_equity",
        "fees",
        "funding",
        "closed_trade_net",
        "entries",
        "tp_exits",
        "errors",
        "rejections",
    ]:
        assert r[key] == old[key]
    assert [c["equity"] for c in r["curve"]] == [c["equity"] for c in old["curve"]]


def test_unrepresentable_tp_default_still_invalidates_legacy_replay():
    r,_=run([100,100,110],dict(fixed_tp_usdt=1),funding=[(300000,-2,100)])
    assert r["ending_equity"] is None
    assert r["errors"][0].startswith("tp_price_unrepresentable")


def test_unrepresentable_tp_pauses_but_keeps_funding_and_marked_loss():
    signals={0:[dict(symbol="X",event_id="one",atr=2)],600000:[dict(symbol="Y",event_id="two",atr=2)]}
    r,_=run([100,100,110,120],dict(fixed_tp_usdt=1,unrepresentable_tp_action="pause_hold"),
            funding=[(300000,-2,100),(900000,-.1,120)],signals=signals)
    assert r["ending_equity"] is not None and not r["errors"]
    assert r["entries"]==1 and r["entry_paused"] and len(r["open_positions"])==1
    assert sum(j["kind"]=="tp_unrepresentable" for j in r["journal"])==1
    assert r["curve"][-1]["equity"]<r["curve"][1]["equity"]
    assert r["ending_equity"]==pytest.approx(500-r["fees"]+r["funding"]+r["open_positions"][0]["unrealized"])


def test_tp_can_recover_without_resuming_entries_automatically():
    signals={0:[dict(symbol="X",event_id="one",atr=2)],1200000:[dict(symbol="Y",event_id="two",atr=2)]}
    r,_=run([100,100,101,90,80],dict(fixed_tp_usdt=1,unrepresentable_tp_action="pause_hold"),
            funding=[(300000,-2,100),(900000,2,100)],signals=signals)
    assert r["tp_exits"]==1 and r["entry_paused"] and r["entries"]==1
    assert sum(j["kind"]=="tp_representable_again" for j in r["journal"])==1
    assert not r["open_positions"] and not r["errors"]


def test_three_legs_conserve_budget_weighted_price_and_funding_quantity():
    r, _ = run(
        [100, 99, 98, 97], split(), funding=[(300000, 0.01, 99), (600000, -0.02, 98)]
    )
    fills = [j for j in r["journal"] if j["kind"] in ["entry", "entry_add"]]
    assert len(fills) == 3
    assert sum(j["qty"] * j["price"] for j in fills) <= 25
    p = r["open_positions"][0]
    assert p["qty"] == pytest.approx(sum(j["qty"] for j in fills))
    assert p["entry"] == pytest.approx(
        sum(j["qty"] * j["price"] for j in fills) / p["qty"]
    )
    expected = (
        fills[0]["qty"] * 99 * 0.01 - (fills[0]["qty"] + fills[1]["qty"]) * 98 * 0.02
    )
    assert r["funding"] == pytest.approx(expected)
    assert r["ending_equity"] == pytest.approx(
        500 - r["fees"] + expected + p["qty"] * (p["entry"] - 97)
    )
    assert r["curve"][0]["committed_margin"] > 4.9


def test_losing_close_does_not_trigger_averaging_up():
    r, _ = run([100, 101, 102, 103], split())
    assert not any(j["kind"] == "entry_add" for j in r["journal"])
    assert r["open_positions"][0]["filled_parts"] == 1


def test_next_open_gap_does_not_retroactively_filter_add_signal():
    r, _ = run([100, 99, 98], split(), openings=[100, 105, 98])
    add = next(j for j in r["journal"] if j["kind"] == "entry_add")
    assert add["price"] > 100


def test_exchange_minimum_checked_per_tranche_without_upsizing():
    r, _ = run([100, 99, 98], split(), rule=dict(RULE, min_notional=20))
    assert r["entries"] == 0
    assert r["rejections"]["exchange_minimum_or_precision"] == 1


def test_trailing_never_closes_before_activation_and_uses_market_gap_price():
    r, _ = run([100, 102, 97, 98.5], trail(), openings=[100, 102, 97, 110])
    exit = next(j for j in r["journal"] if j["kind"] == "trailing_exit")
    assert exit["at"] == 900000
    assert exit["price"] == pytest.approx(110 * 1.002)
    assert exit["net"] < 0  # activating in profit is not a profit guarantee


def test_trailing_activation_cancels_remaining_entries_and_releases_reserve():
    r, _ = run([100, 97, 96, 95], dict(split(), **trail()))
    p = r["open_positions"][0]
    assert p["trail_active"] and p["adds_cancelled"] and p["filled_parts"] == 1
    assert not any(j["kind"] == "entry_add" for j in r["journal"])
    assert r["curve"][1]["committed_margin"] < 2


def test_drawdown_pause_blocks_pending_adds():
    r, _ = run([100, 1400, 90, 89], split())
    assert r["entry_paused"]
    assert not any(j["kind"] == "entry_add" for j in r["journal"])


def test_one_position_slot_covers_all_three_parts():
    signals = {
        0: [
            dict(symbol="X", event_id="one", atr=2),
            dict(symbol="Y", event_id="two", atr=2),
        ]
    }
    r, _ = run(
        [100, 99, 98],
        split(),
        config=ExecutionConfig(max_open_positions=1),
        signals=signals,
    )
    assert r["entries"] == 1 and len(r["open_positions"]) == 1
    assert r["rejections"]["position_limit"] == 1


def test_trailing_exit_cannot_fill_without_terminal_next_open():
    r, _ = run([100, 97, 99], trail(), openings=[100, 97, float("nan")])
    assert not r["errors"] and r["ending_equity"] is not None
    assert r["open_positions"][0]["pending_exit"] == "trailing_exit"


def test_cancelled_partial_position_risk_limit_scales_with_exposure():
    r, _ = run([100, 105], split(loss_usdt=1))
    assert any(j["kind"] == "loss_stop" for j in r["journal"])
