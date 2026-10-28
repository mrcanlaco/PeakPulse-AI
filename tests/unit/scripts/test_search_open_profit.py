from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts/search_open_profit.py"
SPEC = importlib.util.spec_from_file_location("search_open_profit_under_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

UTC = timezone.utc


def _row(
    number: int,
    when: str,
    symbol: str,
    pump: float,
    distance: float,
    ret_1h: float,
    percentile: float | None = None,
    change: float = 0.0,
    persistence: float = 0.0,
) -> dict[str, object]:
    return {
        "source_row_number": number,
        "feature_time": pd.Timestamp(when, tz="UTC"),
        "signal_time": pd.Timestamp(when, tz="UTC") + pd.Timedelta(milliseconds=1),
        "symbol": symbol,
        "price_ret_24h": pump,
        "distance_from_high_24h": distance,
        "price_ret_1h": ret_1h,
        "funding_percentile_30d": percentile,
        "funding_change_8h": change,
        "funding_persistence_7d": persistence,
    }


def _path(
    symbol: str,
    direction: str,
    status: str = "time_exit",
    exit_time: datetime | None = None,
    entry_price: float = 100.0,
    exit_price: float = 110.0,
) -> MODULE.PricePath:
    start = datetime(2026, 2, 1, 0, 5, tzinfo=UTC)
    end = exit_time or start + timedelta(hours=12)
    bar = MODULE.Bar(start, entry_price, max(entry_price, exit_price), min(entry_price, exit_price), exit_price)
    return MODULE.PricePath(
        symbol,
        direction,
        start,
        start,
        end,
        end,
        status,
        None,
        entry_price,
        exit_price,
        (bar,),
        (),
        1,
        1,
        None,
        True,
        1,
        0,
    )


def test_family_selection_cooldown_tie_and_regime_direction_are_row_local():
    frame = pd.DataFrame(
        [
            _row(1, "2026-02-01 00:04:59.999", "AAAUSDT", 0.40, -0.04, -0.10),
            _row(2, "2026-02-01 00:04:59.999", "BBBUSDT", 0.30, -0.04, 0.10),
            _row(3, "2026-02-01 01:04:59.999", "AAAUSDT", 0.90, -0.04, -0.10),
            _row(4, "2026-02-02 00:04:59.999", "AAAUSDT", 0.25, -0.04, 0.10),
            _row(5, "2026-02-01 02:04:59.999", "CCCUSDT", 0.30, -0.03, 0.10, 0.90, 0.01, 0.01),
        ]
    )
    candidates, counts = MODULE._family_candidates(frame)
    assert counts["exhaustion_short"]["selected_after_24h_cooldown"] == 1
    assert candidates["exhaustion_short"][0]["symbol"] == "AAAUSDT"
    regime = {
        (item["symbol"], item["source_row_number"]): item["direction"]
        for item in candidates["regime_switch"]
    }
    assert regime[("AAAUSDT", 1)] == "short"
    assert regime[("AAAUSDT", 4)] == "long"
    assert regime[("BBBUSDT", 2)] == "long"


def test_path_requires_next_bar_and_marks_future_gap_without_prior_close_reuse():
    start = datetime(2026, 2, 1, 0, 5, tzinfo=UTC)
    bars = {
        start: MODULE.Bar(start, 101.0, 103.0, 100.0, 102.0),
        start + MODULE.BAR_STEP: MODULE.Bar(
            start + MODULE.BAR_STEP, 102.0, 104.0, 101.0, 103.0
        ),
    }
    path = MODULE._build_path(
        "AAAUSDT",
        "long",
        start,
        start + 3 * MODULE.BAR_STEP,
        bars,
        (),
    )
    assert path.status == "unresolved"
    assert path.entry_price == 101.0
    assert path.first_missing_bar == start + 2 * MODULE.BAR_STEP


def test_roundtrip_cost_is_split_across_entry_and_exit():
    start = datetime(2026, 2, 1, 0, 5, tzinfo=UTC)
    bars = {
        start: MODULE.Bar(start, 100.0, 101.0, 99.0, 100.0),
        start + MODULE.BAR_STEP: MODULE.Bar(
            start + MODULE.BAR_STEP, 100.0, 111.0, 100.0, 110.0
        ),
    }
    path = MODULE._build_path(
        "AAAUSDT", "long", start, start + 2 * MODULE.BAR_STEP, bars, ()
    )
    result = MODULE._scenario_leg(path, leverage=2, cost_bps=20)
    assert result["fee_return_on_margin"] == pytest.approx(0.0042)
    assert result["net_return_on_margin"] == pytest.approx(0.2 - 0.0042)


def test_observed_funding_uses_settlement_mark_ratio_and_short_sign():
    start = datetime(2026, 2, 1, 0, 5, tzinfo=UTC)
    settlement = start + MODULE.BAR_STEP
    bars = {
        start: MODULE.Bar(start, 100.0, 101.0, 99.0, 100.0),
        settlement: MODULE.Bar(settlement, 120.0, 121.0, 119.0, 120.0),
    }
    funding = (MODULE.FundingPoint(settlement, 0.01, 120.0),)
    path = MODULE._build_path(
        "AAAUSDT", "short", start, start + 2 * MODULE.BAR_STEP, bars, funding
    )
    result = MODULE._scenario_leg(path, leverage=2, cost_bps=0)
    assert result["observed_funding_return_on_margin"] == pytest.approx(0.024)
    assert result["funding_mark_proxy_count"] == 1


def test_hedge_uses_later_leg_exit_and_cutoff_lock():
    start = datetime(2026, 2, 1, 0, 5, tzinfo=UTC)
    cutoff = MODULE.WINDOW_END
    coin = _path("AAAUSDT", "short", "liquidated_proxy", start + timedelta(hours=1))
    btc = _path("BTCUSDT", "long", "open_at_cutoff", cutoff)
    opportunity = {
        "candidate_id": "hedged",
        "source_row_number": 1,
        "family": "hedged_fade",
        "symbol": "AAAUSDT",
        "direction": "hedge",
        "signal_time": start,
        "feature_time": start,
        "price_ret_24h": 0.4,
        "market_four": False,
    }
    paths = {
        ("AAAUSDT", start, "short", 12): coin,
        ("BTCUSDT", start, "long", 12): btc,
    }

    class FakeTrade:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    trades, details = MODULE._build_trial_trades(
        MODULE.TrialSpec("hedged_fade", 12, 1, 20),
        [opportunity],
        paths,
        FakeTrade,
    )
    assert details[0]["terminal_status"] == "open_at_cutoff"
    assert details[0]["exit_time"] == cutoff
    assert trades[0].exit_time == cutoff


def test_grid_is_exactly_registered_120_trials():
    grid = MODULE._trial_grid()
    assert len(grid) == 120
    assert len({item.trial_id for item in grid}) == 120


def test_registry_gate_rejects_unfrozen_document(tmp_path):
    registry = tmp_path / "registry.md"
    source = tmp_path / "cohort.csv"
    registry.write_text("120 cấu hình cố định", encoding="utf-8")
    source.write_text("placeholder", encoding="utf-8")
    with pytest.raises(RuntimeError, match="not final/frozen"):
        MODULE._registry_provenance(registry, source)
