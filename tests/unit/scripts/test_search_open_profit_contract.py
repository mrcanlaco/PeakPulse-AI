"""Core price-path contract tests for the open-profit search runner."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dao_vang.experiments.open_profit_account import CandidateTrade

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/search_open_profit.py"
UTC = timezone.utc
START = datetime(2026, 2, 1, tzinfo=UTC)


def _load_helper():
    spec = importlib.util.spec_from_file_location(
        "test_search_open_profit_impl",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _path(
    helper,
    *,
    symbol: str = "ALTUSDT",
    direction: str = "long",
    signal_time: datetime = START,
    effective_minutes: int = 5,
    scheduled_minutes: int | None = None,
    status: str = "time_exit",
    entry_price: float = 100.0,
    exit_price: float | None = 100.0,
    bars=(),
    funding=(),
):
    effective_end = signal_time + timedelta(minutes=effective_minutes)
    scheduled_end = signal_time + timedelta(
        minutes=scheduled_minutes
        if scheduled_minutes is not None
        else effective_minutes
    )
    return helper.PricePath(
        symbol=symbol,
        direction=direction,
        signal_time=signal_time,
        entry_time=signal_time,
        scheduled_end=scheduled_end,
        effective_end=effective_end,
        status=status,
        reason=None,
        entry_price=entry_price,
        exit_price=exit_price,
        bars=tuple(bars),
        funding=tuple(funding),
        expected_bars=len(bars),
        observed_bars=len(bars),
        first_missing_bar=None,
        funding_missing=False,
        funding_expected=0,
        funding_observed=len(funding),
    )


def test_flat_price_round_trip_cost_is_twenty_bps_at_one_x() -> None:
    helper = _load_helper()
    bar = helper.Bar(START, 100.0, 100.0, 100.0, 100.0)
    path = _path(helper, bars=(bar,))

    leg = helper._scenario_leg(path, leverage=1, cost_bps=20)

    assert leg["gross_price_return_on_margin"] == pytest.approx(0.0)
    assert leg["fee_return_on_margin"] == pytest.approx(0.002)
    assert leg["net_return_on_margin"] == pytest.approx(-0.002)


def test_funding_settlement_uses_mark_to_entry_price_ratio() -> None:
    helper = _load_helper()
    bar = helper.Bar(START, 100.0, 100.0, 100.0, 100.0)
    funding = helper.FundingPoint(
        START + helper.BAR_STEP,
        rate=0.01,
        mark_price=150.0,
    )
    path = _path(helper, bars=(bar,), funding=(funding,))

    leg = helper._scenario_leg(path, leverage=1, cost_bps=0)

    assert leg["observed_funding_return_on_margin"] == pytest.approx(-0.015)
    assert leg["net_return_on_margin"] == pytest.approx(-0.015)


def test_settlement_at_bar_end_is_not_charged_before_prior_bar_adverse() -> None:
    helper = _load_helper()
    first = helper.Bar(START, 100.0, 100.0, 99.0, 100.0)
    second = helper.Bar(
        START + helper.BAR_STEP,
        100.0,
        100.0,
        100.0,
        100.0,
    )
    settlement = helper.FundingPoint(
        START + helper.BAR_STEP,
        # Use a non-boundary amount so the expected liquidation is not
        # sensitive to floating-point equality at maintenance margin.
        rate=1.0,
        mark_price=100.0,
    )
    path = _path(
        helper,
        effective_minutes=10,
        bars=(first, second),
        funding=(settlement,),
    )

    leg = helper._scenario_leg(path, leverage=1, cost_bps=0)

    assert leg["status"] == "liquidated_proxy"
    assert leg["exit_time"] == START + 2 * helper.BAR_STEP


def test_liquidation_timestamp_is_bar_end_not_bar_start() -> None:
    helper = _load_helper()
    bar = helper.Bar(START, 100.0, 100.0, 0.0, 100.0)
    path = _path(helper, bars=(bar,))

    leg = helper._scenario_leg(path, leverage=1, cost_bps=0)

    assert leg["status"] == "liquidated_proxy"
    assert leg["exit_time"] == START + helper.BAR_STEP


def test_cutoff_mtm_does_not_charge_an_exit_fee() -> None:
    helper = _load_helper()
    bar = helper.Bar(START, 100.0, 110.0, 110.0, 110.0)
    path = _path(
        helper,
        effective_minutes=5,
        scheduled_minutes=60,
        status="open_at_cutoff",
        exit_price=110.0,
        bars=(bar,),
    )

    leg = helper._scenario_leg(path, leverage=1, cost_bps=20)

    assert leg["status"] == "open_at_cutoff"
    assert leg["fee_return_on_margin"] == pytest.approx(0.001)
    assert leg["net_return_on_margin"] == pytest.approx(0.099)


def test_hedge_uses_max_leg_exit_and_combines_mtm_with_liquidation() -> None:
    helper = _load_helper()
    coin_bar = helper.Bar(START, 100.0, 100.0, 100.0, 100.0)
    liquidation_bar = helper.Bar(
        START + timedelta(minutes=15),
        100.0,
        100.0,
        0.0,
        100.0,
    )
    coin_path = _path(
        helper,
        symbol="ALTUSDT",
        direction="short",
        effective_minutes=5,
        scheduled_minutes=60,
        status="open_at_cutoff",
        bars=(coin_bar,),
    )
    btc_path = _path(
        helper,
        symbol="BTCUSDT",
        direction="long",
        effective_minutes=15,
        status="time_exit",
        bars=(liquidation_bar,),
    )
    signal = START
    opportunity = {
        "candidate_id": "hedge:ALTUSDT",
        "source_row_number": 1,
        "family": "hedged_fade",
        "symbol": "ALTUSDT",
        "direction": "hedge",
        "signal_time": signal,
        "feature_time": signal,
        "price_ret_24h": 0.30,
        "market_four": False,
    }
    paths = {
        ("ALTUSDT", signal, "short", 12): coin_path,
        ("BTCUSDT", signal, "long", 12): btc_path,
    }

    trades, details = helper._build_trial_trades(
        helper.TrialSpec("hedged_fade", 12, 1, 0),
        [opportunity],
        paths,
        CandidateTrade,
    )

    assert len(details) == 1
    assert len(trades) == 1
    assert details[0]["terminal_status"] == "open_at_cutoff"
    assert details[0]["exit_time"] == helper.WINDOW_END
    assert details[0]["legs"][1]["terminal_status"] == "liquidated_proxy"
    assert details[0]["legs"][1]["exit_time"] == START + timedelta(minutes=20)
    assert max(leg["exit_time"] for leg in details[0]["legs"]) == START + timedelta(minutes=20)
    assert trades[0].exit_time == helper.WINDOW_END
    assert trades[0].net_return_on_margin == pytest.approx(-0.5)


def test_funding_stress_can_change_liquidation_chronologically() -> None:
    helper = _load_helper()
    bars = tuple(
        helper.Bar(
            START + index * helper.BAR_STEP,
            100.0,
            100.0,
            0.1,
            0.1,
        )
        for index in range(97)
    )
    path = _path(
        helper,
        effective_minutes=8 * 60,
        bars=bars,
        entry_price=100.0,
        exit_price=0.1,
    )

    base = helper._scenario_leg(path, leverage=1, cost_bps=0, funding_stress=False)
    stress = helper._scenario_leg(path, leverage=1, cost_bps=0, funding_stress=True)

    assert base["status"] == "time_exit"
    assert stress["status"] == "liquidated_proxy"
    assert stress["liquidation_proxy"] is True
