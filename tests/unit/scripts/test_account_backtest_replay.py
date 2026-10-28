import importlib.util
from pathlib import Path

import pytest

from dao_vang.config.settings import ExecutionConfig

MODULE = Path(__file__).resolve().parents[3] / "scripts/account_backtest_replay.py"
SPEC = importlib.util.spec_from_file_location("account_backtest_replay", MODULE)
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


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


def run(marks, signals=None, funding=(), cap=1, policy=None):
    times = [i * 300000 for i in range(len(marks))]
    quotes = {
        t: dict(mark=p, entry_open=p) for t, p in zip(times, marks) if p is not None
    }
    if signals is None:
        signals = {0: [dict(symbol="TESTUSDT", event_id="first", atr=4)]}
    return replay.simulate(
        times,
        signals,
        lambda _: quotes,
        {"TESTUSDT": RULE, "NEXTUSDT": RULE},
        lambda _: funding,
        ExecutionConfig(max_open_positions=cap),
        research_policy=policy,
    )


def test_short_funding_and_unrealized_are_in_equity():
    result = run([100, 110, 120], funding=[(1000, 0.01, 105), (310000, -0.02, 115)])
    p = result["open_positions"][0]
    expected_funding = p["qty"] * (105 * 0.01 - 115 * 0.02)
    assert result["funding"] == pytest.approx(expected_funding)
    assert result["ending_equity"] == pytest.approx(
        500 - result["fees"] + expected_funding + p["qty"] * (p["entry"] - 120)
    )
    assert result["tp_exits"] == 0


def test_drawdown_latches_without_closing_losers_or_resetting_peak():
    signals = {
        0: [dict(symbol="TESTUSDT", event_id="first", atr=4)],
        900000: [dict(symbol="NEXTUSDT", event_id="second", atr=4)],
    }
    result = run([100, 505, 550, 500], signals, cap=5)
    assert result["sampled_max_drawdown"] >= 0.20
    assert result["entry_paused"]
    assert result["entries"] == 1
    assert result["tp_exits"] == 0
    assert len(result["open_positions"]) == 1
    assert result["rejections"]["drawdown_paused"] == 1


def test_tp_target_is_net_and_does_not_scale_with_later_volatility():
    result = run([100, 95, 90])
    entry = next(j for j in result["journal"] if j["kind"] == "entry")
    tp = next(j for j in result["journal"] if j["kind"] == "tp")
    assert 0.5 <= entry["target"] <= 5
    assert tp["net"] == pytest.approx(entry["target"], abs=0.001)
    assert result["ending_equity"] == pytest.approx(500 + tp["net"])


def test_missing_open_position_price_never_becomes_zero_return():
    result = run([100, None, 90])
    assert result["ending_equity"] is None
    assert result["pnl"] is None
    assert result["errors"][0].startswith("missing_held_price")
    assert len(result["open_positions"]) == 1


def test_no_duplicate_position_and_no_promotion():
    signal = dict(symbol="TESTUSDT", event_id="first", atr=4)
    result = run(
        [100, 105], {0: [signal, signal], 300000: [dict(signal, event_id="next")]}
    )
    assert result["entries"] == 1
    assert result["rejections"] == {"duplicate_episode": 1, "position_limit": 1}
    assert not result["financially_verified"]
    assert not result["promotion_eligible"]


def test_small_position_does_not_liquidate_on_twenty_percent_price_rise():
    result = run([100, 120])
    assert result["ending_equity"] > 490
    assert result["errors"] == []
    assert len(result["open_positions"]) == 1


def test_unknown_cross_liquidation_cannot_report_a_fictional_balance():
    result = run([100, 3000])
    assert result["ending_equity"] is None
    assert result["errors"][0].startswith("maintenance_proxy_breached")


def test_funding_failure_invalidates_run_instead_of_assuming_zero():
    def fail(_):
        raise ConnectionError("unavailable")

    result = replay.simulate(
        [0],
        {0: [dict(symbol="TESTUSDT", event_id="first", atr=4)]},
        lambda _: {0: dict(mark=100, entry_open=100)},
        {"TESTUSDT": RULE},
        fail,
        ExecutionConfig(),
    )
    assert result["ending_equity"] is None
    assert result["entries"] == 0
    assert result["errors"][0].startswith("funding_unavailable")


def test_mark_price_values_equity_but_does_not_trigger_trade_price_tp():
    result = replay.simulate(
        [0, 300000],
        {0: [dict(symbol="TESTUSDT", event_id="first", atr=4)]},
        lambda _: {
            0: dict(mark=100, entry_open=100, execution_close=100),
            300000: dict(mark=90, entry_open=110, execution_close=110),
        },
        {"TESTUSDT": RULE},
        lambda _: [],
        ExecutionConfig(),
    )
    assert result["ending_equity"] > 500
    assert result["tp_exits"] == 0
    assert len(result["open_positions"]) == 1


def test_research_stop_loss_can_overshoot_threshold_on_price_jump():
    result = run([100, 150, 200], policy={"loss_usdt": 5})
    exit_row = next(j for j in result["journal"] if j["kind"] == "loss_stop")
    assert exit_row["price"] == pytest.approx(150 * 1.002)
    assert exit_row["net"] < -10
    assert result["ending_equity"] == pytest.approx(500 + exit_row["net"])
    assert result["open_positions"] == []


def test_account_stop_closes_inventory_and_stays_paused_after_recovery():
    signals = {
        0: [dict(symbol="TESTUSDT", event_id="first", atr=4)],
        600000: [dict(symbol="NEXTUSDT", event_id="next", atr=4)],
    }
    result = run(
        [100, 350, 90], signals=signals, cap=5, policy={"flatten_drawdown": 0.10}
    )
    assert result["entry_paused"]
    assert result["entries"] == 1
    assert len([j for j in result["journal"] if j["kind"] == "account_stop"]) == 1
    assert result["open_positions"] == []
    assert result["rejections"]["drawdown_paused"] == 1


def test_time_exit_counts_funding_once_and_can_close_a_loser():
    result = run(
        [100, 101, 103, 104],
        funding=[(310000, -0.01, 102)],
        policy={"max_hold_hours": 1 / 6},
    )
    exit_row = next(j for j in result["journal"] if j["kind"] == "time_exit")
    assert exit_row["at"] == 600000
    assert exit_row["net"] < 0
    assert len([j for j in result["journal"] if j["kind"] == "funding"]) == 1
    assert result["ending_equity"] == pytest.approx(500 + exit_row["net"])


def test_atr_stop_locks_distance_at_entry():
    result = run([100, 105, 109], policy={"stop_atr": 2})
    exit_row = next(j for j in result["journal"] if j["kind"] == "atr_stop")
    assert exit_row["at"] == 600000


def test_research_half_size_keeps_real_exchange_minimum():
    base = run([100, 110])
    reduced = run([100, 110], policy={"position_notional": 12.5})
    assert reduced["open_positions"][0]["qty"] == pytest.approx(
        base["open_positions"][0]["qty"] / 2, abs=0.001
    )
    tiny = run([100, 110], policy={"position_notional": 2})
    assert tiny["entries"] == 0
    assert tiny["rejections"]["exchange_minimum_or_precision"] == 1


def test_stop_uses_next_trade_open_not_mark_or_stop_price():
    result = replay.simulate(
        [0, 300000],
        {0: [dict(symbol="TESTUSDT", event_id="first", atr=4)]},
        lambda _: {
            0: dict(mark=100, entry_open=100, execution_close=100),
            300000: dict(mark=130, entry_open=160, execution_close=129),
        },
        {"TESTUSDT": RULE},
        lambda _: [],
        ExecutionConfig(),
        research_policy={"loss_usdt": 5},
    )
    exit_row = next(j for j in result["journal"] if j["kind"] == "loss_stop")
    assert exit_row["price"] == pytest.approx(160 * 1.002)


def test_terminal_stop_without_next_open_is_marked_not_invented():
    result = replay.simulate(
        [0, 300000],
        {0: [dict(symbol="TESTUSDT", event_id="first", atr=4)]},
        lambda _: {
            0: dict(mark=100, entry_open=100, execution_close=100),
            300000: dict(mark=130, execution_close=130),
        },
        {"TESTUSDT": RULE},
        lambda _: [],
        ExecutionConfig(),
        research_policy={"loss_usdt": 5},
    )
    assert result["ending_equity"] is not None
    assert result["open_positions"][0]["pending_exit"] == "loss_stop"
    assert not [j for j in result["journal"] if j["kind"] == "loss_stop"]


def test_missing_trade_close_is_not_silently_replaced_by_mark_for_tp():
    result = replay.simulate(
        [0, 300000],
        {0: [dict(symbol="TESTUSDT", event_id="first", atr=4)]},
        lambda _: {
            0: dict(mark=100, entry_open=100, execution_close=100),
            300000: dict(mark=90, entry_open=90, execution_close=float("nan")),
        },
        {"TESTUSDT": RULE},
        lambda _: [],
        ExecutionConfig(),
    )
    assert result["ending_equity"] is None
    assert result["errors"][0].startswith("missing_held_trade_price")
    assert result["tp_exits"] == 0


def test_funding_cursor_resets_on_reentry_without_replaying_old_settlements():
    signals = {
        0: [dict(symbol="TESTUSDT", event_id="first", atr=4)],
        600000: [dict(symbol="TESTUSDT", event_id="second", atr=4)],
    }
    result = run(
        [100, 120, 100, 105, 120],
        signals=signals,
        funding=[(200000, 0.01, 115), (700000, -0.01, 103)],
        policy={"loss_usdt": 2.5},
    )
    settled = [j for j in result["journal"] if j["kind"] == "funding"]
    exits = [j for j in result["journal"] if "net" in j]
    assert len(settled) == 2
    assert result["entries"] == 2
    assert len(exits) == 2
    assert result["ending_equity"] == pytest.approx(500 + sum(j["net"] for j in exits))


def test_market_gap_that_exhausts_equity_cannot_report_successful_stop():
    result = replay.simulate(
        [0, 300000],
        {0: [dict(symbol="TESTUSDT", event_id="first", atr=4)]},
        lambda _: {
            0: dict(mark=100, entry_open=100, execution_close=100),
            300000: dict(mark=130, entry_open=3000, execution_close=130),
        },
        {"TESTUSDT": RULE},
        lambda _: [],
        ExecutionConfig(),
        research_policy={"loss_usdt": 5},
    )
    assert result["ending_equity"] is None
    assert result["errors"][0].startswith("risk_exit_equity_exhausted")


def test_funding_can_make_locked_net_target_unrepresentable_without_crashing():
    result = run([100, 120], funding=[(1000, -1, 120)])
    assert result["ending_equity"] is None
    assert result["errors"] == ["tp_price_unrepresentable:TESTUSDT:300000"]
    assert result["tp_exits"] == 0
    assert result["funding"] < -25


def test_research_no_pause_does_not_disable_insolvency_check():
    from types import SimpleNamespace

    settings = ExecutionConfig().model_dump()
    settings["entry_pause_drawdown"] = None
    result = replay.simulate(
        [0, 300000],
        {0: [dict(symbol="TESTUSDT", event_id="first", atr=4)]},
        lambda _: {
            0: dict(mark=100, entry_open=100),
            300000: dict(mark=3000, entry_open=3000),
        },
        {"TESTUSDT": RULE},
        lambda _: [],
        SimpleNamespace(**settings),
    )
    assert not result["entry_paused"]
    assert result["ending_equity"] is None
    assert result["errors"][0].startswith("maintenance_proxy_breached")


@pytest.mark.parametrize("target", [0.5, 1, 2, 3, 5])
def test_fixed_tp_is_locked_net_cash_target_including_settled_funding(target):
    result = run(
        [100, 110, 70],
        funding=[(310000, -0.005, 105)],
        policy={"fixed_tp_usdt": target},
    )
    entry = next(j for j in result["journal"] if j["kind"] == "entry")
    tp = next(j for j in result["journal"] if j["kind"] == "tp")
    assert entry["target"] == target
    assert tp["net"] == pytest.approx(target, abs=0.001)
    assert result["ending_equity"] == pytest.approx(500 + tp["net"])


@pytest.mark.parametrize("target", [0, 0.49, 5.1, float("nan")])
def test_research_fixed_tp_rejects_unregistered_target_range(target):
    with pytest.raises(ValueError, match="research_fixed_tp_outside"):
        run([100, 90], policy={"fixed_tp_usdt": target})


@pytest.mark.parametrize("target", [8, 10, 15])
def test_expanded_research_tp_requires_opt_in_and_accounts_for_costs(target):
    with pytest.raises(ValueError, match="research_fixed_tp_outside"):
        run([100, 30], policy={"fixed_tp_usdt": target})
    result = run(
        [100, 110, 30],
        funding=[(310000, -0.005, 105)],
        policy={"fixed_tp_usdt": target, "research_tp_limit": 15},
    )
    tp = next(j for j in result["journal"] if j["kind"] == "tp")
    assert tp["net"] == pytest.approx(target, abs=0.001)
    assert result["ending_equity"] == pytest.approx(500 + tp["net"])
    assert ExecutionConfig().tp_max_usdt == 5
    assert not result["promotion_eligible"]


@pytest.mark.parametrize("limit", [4, 16, float("nan"), float("inf")])
def test_expanded_research_tp_limit_is_bounded(limit):
    with pytest.raises(ValueError, match="research_tp_limit_outside"):
        run([100, 30], policy={"fixed_tp_usdt": 10, "research_tp_limit": limit})


def test_touch_sensitivity_uses_low_but_never_end_bar_funding_to_move_resting_tp():
    quotes = {
        0: dict(mark=100, entry_open=100, execution_close=100, execution_low=100),
        300000: dict(mark=105, entry_open=105, execution_close=105, execution_low=97),
    }
    args = (
        [0, 300000],
        {0: [dict(symbol="TESTUSDT", event_id="one", atr=4)]},
        lambda _: quotes,
        {"TESTUSDT": RULE},
        lambda _: [(1000, -0.01, 100)],
        ExecutionConfig(),
    )
    base = replay.simulate(*args, research_policy={"fixed_tp_usdt": 0.5})
    touched = replay.simulate(
        *args, research_policy={"fixed_tp_usdt": 0.5, "tp_fill": "bar_low"}
    )
    assert base["tp_exits"] == 0
    assert touched["tp_exits"] == 1
    exit_row = next(j for j in touched["journal"] if j["kind"] == "tp")
    assert 97 < exit_row["price"] < 98
    assert exit_row["net"] < 0.5  # funding charged through bar end in this sensitivity
    assert touched["ending_equity"] == pytest.approx(500 + exit_row["net"])
