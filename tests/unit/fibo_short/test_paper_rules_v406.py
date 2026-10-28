from copy import deepcopy
from decimal import Decimal

import pytest

from dao_vang.fibo_short.paper_rules_v406 import plan_paper_entry


def inputs():
    candidate = dict(symbol="TESTUSDT", tf="4h", wave_key="w1", decision_time="2026-10-18T01:00:00Z",
                     eligible_milestones=["m6_f4_expanded"], closed_candles_complete=True,
                     entry_price=100, sl_m6=110, tp1=90, tp2=80, tp3=70, full_conviction_score=90)
    state = dict(equity=10000, positions=[], allowed_symbols=["TESTUSDT"],
                 universe_month="2026-10", paused=False, consumed_waves={}, cooldown_until={})
    filters = dict(step_size=".1", tick_size=".01", min_qty=".1", max_qty="1000", min_notional="5")
    return candidate, state, filters


def plan(c, s, f):
    return plan_paper_entry(c, s, f, now="2026-10-18T01:01:00Z")


def test_fixed_paper_proposal_keeps_quantity_conserved_and_state_unmodified():
    c, s, f = inputs()
    before = deepcopy((c, s, f))
    p = plan(c, s, f)
    assert p["status"] == "PAPER_PROPOSAL"
    assert Decimal(p["quantity"]) == 20
    assert sum(map(Decimal, p["target_quantities"])) == Decimal(p["quantity"])
    assert p["initial_stop_risk_fraction"] == pytest.approx(.02)
    assert (c, s, f) == before


@pytest.mark.parametrize("problem,reason", [
    ("month", "STALE_MONTHLY_UNIVERSE"), ("gap", "INCOMPLETE_CANDLE_DATA"),
    ("stale", "FUTURE_OR_STALE_SIGNAL"), ("wave", "WAVE_ALREADY_CONSUMED"),
    ("cooldown", "COOLDOWN"), ("dust", "PARTIAL_EXIT_FILTERS"),
    ("notional", "NOTIONAL_CAP"), ("risk", "STOP_RISK_CAP"),
])
def test_paper_entry_rejects_unexecutable_or_blocked_state(problem, reason):
    c, s, f = inputs()
    if problem == "month": s["universe_month"] = "2026-09"
    if problem == "gap": c["closed_candles_complete"] = False
    if problem == "stale": c["decision_time"] = "2026-10-18T00:00:00Z"
    if problem == "wave": s["consumed_waves"] = {"TESTUSDT|4h": ["w1"]}
    if problem == "cooldown": s["cooldown_until"] = {"TESTUSDT|4h": "2026-10-18T02:00:00Z"}
    if problem == "dust": s["equity"] = 100
    if problem == "notional":
        s["positions"] = [dict(remaining_qty=85, entry_price=100, mark_price=101, active_stop=105, static_notional_frac_remaining=.85)]
    if problem == "risk": c["sl_m6"] = 170
    assert plan(c, s, f)["reason"] == reason


def test_nonfinite_input_cannot_produce_a_paper_proposal():
    c, s, f = inputs()
    s["equity"] = float("nan")
    with pytest.raises(ValueError, match="Nonfinite"):
        plan(c, s, f)
