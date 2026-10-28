"""Direction-sensitive economic checks, not just mirrored price fixtures."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from account_directional_replay import simulate
from account_scaled_replay import simulate as short_engine
from dao_vang.config.settings import ExecutionConfig

RULE = dict(market_step="0.001", step_size="0.001", min_qty=.001,
            market_min_qty=.001, max_qty=100000, market_max_qty=100000,
            min_notional=5, tick_size="0.001")


def replay(closes, *, side="LONG", funding=(), openings=None, policy=None, signals=None, config=None):
    times = [i * 300000 for i in range(len(closes))]
    points = {t: dict(mark=c, execution_close=c, entry_open=c if openings is None else openings[i])
              for i, (t, c) in enumerate(zip(times, closes))}
    args = (times, signals or {0: [dict(symbol="X", event_id="one", side=side, atr=2)]},
            lambda _: points, {"X": RULE, "Y": RULE}, lambda _: funding, config or ExecutionConfig(max_open_positions=5))
    policy = policy or dict(trailing=True, activation_atr=1, callback_fraction=.01, fixed_tp_usdt=5)
    return simulate(*args, research_policy=policy), args, policy


def strip_side(result):
    if isinstance(result, list):
        return [strip_side(x) for x in result]
    if isinstance(result, dict):
        return {k: strip_side(v) for k, v in result.items() if k != "side"}
    return result


@pytest.mark.parametrize("policy", [dict(fixed_tp_usdt=2), dict(trailing=True, activation_atr=1, callback_fraction=.01, fixed_tp_usdt=5),
    dict(entry_parts=3, entry_mode="favorable", entry_step_atr=.25, fixed_tp_usdt=5)])
def test_short_complete_economic_parity(policy):
    r, args, p = replay([100, 102, 97, 98.5, 90], side="SHORT", policy=policy, funding=[(300000, -.001, 102)])
    assert strip_side(r) == short_engine(*args, research_policy=p)


def test_long_trailing_has_correct_activation_rebound_and_adverse_exit_gap():
    r, _, _ = replay([100, 98, 104, 102], openings=[100, 98, 104, 90])
    entry = r["journal"][0]
    activation = next(j for j in r["journal"] if j["kind"] == "trail_activated")
    exit = next(j for j in r["journal"] if "net" in j)
    assert entry["price"] == pytest.approx(100.2)
    assert activation["at"] == 600000 and exit["at"] == 900000
    assert exit["price"] == pytest.approx(89.82)
    assert exit["net"] == pytest.approx(entry["qty"] * (89.82 - 100.2) - entry["qty"] * (100.2 + 89.82) * .0005)
    assert exit["net"] < 0 and not r["errors"]


@pytest.mark.parametrize("rate", [.01, -.01])
def test_long_funding_uses_signed_actual_tranches_and_marks(rate):
    p = dict(entry_parts=3, entry_mode="favorable", entry_step_atr=.25, fixed_tp_usdt=5)
    r, _, _ = replay([100, 101, 102, 103], policy=p, funding=[(300000, rate, 101), (600000, -rate, 102)])
    fills = [j for j in r["journal"] if j["kind"] in ["entry", "entry_add"]]
    assert len(fills) == 3
    expected = -fills[0]["qty"] * 101 * rate + sum(j["qty"] for j in fills[:2]) * 102 * rate
    assert r["funding"] == pytest.approx(expected)
    basis = sum(j["qty"] * j["price"] for j in fills)
    qty = sum(j["qty"] for j in fills)
    assert basis <= 25
    assert r["ending_equity"] == pytest.approx(500 - basis * .0005 + expected + qty * 103 - basis)


def test_long_never_adds_into_falling_price():
    r, _, _ = replay([100, 99, 98, 97], policy=dict(entry_parts=3, entry_mode="time", entry_interval_minutes=5, fixed_tp_usdt=5))
    assert r["open_positions"][0]["filled_parts"] == 1
    assert r["open_positions"][0]["unrealized"] < 0


def test_long_add_signal_uses_closed_price_not_future_open():
    r, _, _ = replay([100, 101, 102], openings=[100, 110, 102], policy=dict(entry_parts=3, entry_mode="favorable", entry_step_atr=.25, fixed_tp_usdt=5))
    add = next(j for j in r["journal"] if j["kind"] == "entry_add")
    assert add["price"] == pytest.approx(110.22)


def test_both_share_coin_slots_and_wallet():
    signals = {0: [dict(symbol="X", event_id="l", side="LONG", atr=2),
                   dict(symbol="X", event_id="opposite", side="SHORT", atr=2),
                   dict(symbol="Y", event_id="s", side="SHORT", atr=2)]}
    r, _, _ = replay([100, 100], signals=signals, config=ExecutionConfig(max_open_positions=1))
    assert r["entries"] == 1 and r["rejections"]["position_limit"] == 2
    r, _, _ = replay([100, 101], signals=signals, funding=[(300000, .01, 100)])
    assert r["entries"] == 2 and r["rejections"]["position_limit"] == 1
    assert r["funding"] == pytest.approx(0)  # equal qty, opposite carry
    assert all(j["side"] in ["LONG", "SHORT"] for j in r["journal"])
    assert r["ending_equity"] < 500  # shared wallet pays both spreads/fees


def test_long_fixed_tp_solves_net_target_and_rounds_up():
    r, _, _ = replay([100, 120], policy=dict(fixed_tp_usdt=2), funding=[(300000, .01, 110)])
    exit = next(j for j in r["journal"] if j["kind"] == "tp")
    assert exit["net"] >= 2 and exit["net"] < 2.001
    assert r["ending_equity"] == pytest.approx(500 + exit["net"])


def test_long_atr_stop_is_below_entry():
    r, _, _ = replay([100, 101, 97], policy=dict(stop_atr=1, fixed_tp_usdt=5))
    exit = next(j for j in r["journal"] if j["kind"] == "atr_stop")
    assert exit["at"] == 600000 and exit["net"] < 0


def test_long_terminal_exit_stays_marked_if_next_open_missing():
    r, _, _ = replay([100, 104, 102], openings=[100, 104, float("nan")])
    assert not r["errors"] and r["open_positions"][0]["pending_exit"] == "trailing_exit"
    assert r["ending_equity"] == pytest.approx(500 - r["fees"] + r["open_positions"][0]["unrealized"])


def test_invalid_side_and_unsupported_intrabar_fill_are_rejected():
    with pytest.raises(ValueError, match="invalid_signal_side"):
        replay([100, 101], side="INVALID")
    with pytest.raises(ValueError, match="long_bar_low"):
        replay([100, 101], policy=dict(fixed_tp_usdt=2, tp_fill="bar_low"))


def test_long_drawdown_pause_keeps_open_loss_and_never_resumes():
    policy = dict(position_notional=1000, trailing=True, activation_atr=1, callback_fraction=.01, fixed_tp_usdt=5)
    signals = {0: [dict(symbol="X", event_id="l", side="LONG", atr=2)],
               600000: [dict(symbol="Y", event_id="s", side="SHORT", atr=2)]}
    r, _, _ = replay([100, 89, 80], policy=policy, signals=signals)
    assert r["entry_paused"] and r["entries"] == 1 and len(r["open_positions"]) == 1
    assert r["curve"][-1]["equity"] < r["curve"][1]["equity"] < 400


def test_duplicate_id_cannot_change_recorded_entry_side():
    signals = {0: [dict(symbol="X", event_id="same", side="LONG", atr=2)],
               300000: [dict(symbol="X", event_id="same", side="SHORT", atr=2)]}
    r, _, _ = replay([100, 100], signals=signals)
    assert r["journal"][0]["side"] == "LONG" and r["rejections"]["duplicate_episode"] == 1


def test_opposite_coins_do_not_create_free_margin_or_net_maintenance_credit():
    signals = {0: [dict(symbol="X", event_id="l", side="LONG", atr=2),
                   dict(symbol="Y", event_id="s", side="SHORT", atr=2)]}
    r, _, _ = replay([100, 100], signals=signals, policy=dict(position_notional=1400, fixed_tp_usdt=5))
    assert r["entries"] == 1 and r["rejections"]["insufficient_margin"] == 1
    _, args, policy = replay([100, 100], signals=signals, policy=dict(position_notional=1000, fixed_tp_usdt=5))
    r = simulate(*args, research_policy=policy, maintenance_ratio=.3)
    assert r["entries"] == 2 and r["ending_equity"] is None
    assert r["stop_event"]["maintenance_proxy"] == pytest.approx(598.8)
    assert r["errors"][0].startswith("maintenance_proxy_breached")
