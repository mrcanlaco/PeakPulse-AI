from __future__ import annotations

import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# ``scripts`` is intentionally a collection of executable modules rather than
# an installed package.  Make the repository root importable for this target.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts import backtest_annual_profit as annual_runner
from scripts.backtest_annual_profit import (
    BAR_STEP,
    COOLDOWN,
    COST_BPS,
    FUNDING_INTERVAL,
    STRATEGIES,
    TRIAL_SPECS,
    WINDOW_END,
    WINDOW_START,
    Bar,
    Candidate,
    FeatureRow,
    FundingFeature,
    FundingPoint,
    LegResult,
    _attribution,
    _decorate_executed_detail,
    _feature_for_decision,
    _funding_feature,
    _normalise_price_rows,
    _run_static_readiness_errors,
    _validate_price_snapshot_semantics,
    combine_legs,
    evaluate_leg,
    event_order_key,
    find_phase_exit,
    hourly_features,
    iter_decision_times,
    strategy_candidates,
)

UTC = timezone.utc


def ts(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def make_bars(
    start: datetime,
    count: int,
    *,
    price: float = 100.0,
    high: float | None = None,
    low: float | None = None,
) -> dict[datetime, Bar]:
    result: dict[datetime, Bar] = {}
    for index in range(count):
        open_time = start + index * BAR_STEP
        result[open_time] = Bar(
            open_time=open_time,
            open=price,
            high=price if high is None else high,
            low=price if low is None else low,
            close=price,
            close_time=open_time + BAR_STEP - timedelta(milliseconds=1),
            source_row_number=index + 1,
        )
    return result


def feature(
    decision: datetime,
    *,
    symbol: str = "ALTUSDT",
    ret24: float = 0.20,
    ret1h: float = 0.01,
    distance: float = -0.01,
    rate: float | None = None,
    change: float | None = None,
) -> FeatureRow:
    funding = FundingFeature(None, None, rate, change, None if rate is not None else "missing")
    return FeatureRow(
        symbol=symbol,
        feature_cutoff=decision - timedelta(milliseconds=1),
        decision_time=decision,
        entry_time=decision + BAR_STEP,
        current_close=100.0,
        ret24h=ret24,
        ret1h=ret1h,
        high24h=100.0 / (1.0 + distance),
        distance_high24h=distance,
        source_row_number=1,
        funding=funding,
    )


def test_registry_is_exactly_ten_strategies_and_forty_trials() -> None:
    assert len(STRATEGIES) == 10
    assert [item.strategy_id for item in STRATEGIES] == [
        "M48_1",
        "M48_2",
        "M168_2",
        "NEG48_1",
        "E48_1",
        "E48_2",
        "POS48_2",
        "SWITCH48_1",
        "HEDGE48_2",
        "PHASE48_1",
    ]
    assert len(TRIAL_SPECS) == 40
    assert set(item.cost_bps for item in TRIAL_SPECS) == set(COST_BPS)
    assert {item.withdraw_profits for item in TRIAL_SPECS} == {True, False}


def test_annual_decision_boundary_is_365_days_and_latency_is_five_minutes() -> None:
    decisions = tuple(iter_decision_times())
    assert len(decisions) == 365 * 24
    assert decisions[0] == WINDOW_START
    assert decisions[-1] == WINDOW_END - timedelta(hours=1)
    bars = make_bars(WINDOW_START - timedelta(hours=25), 310)
    row = _feature_for_decision("ALTUSDT", WINDOW_START, bars)
    assert row is not None
    assert row.feature_cutoff == WINDOW_START - timedelta(milliseconds=1)
    assert row.decision_time == WINDOW_START
    assert row.entry_time == WINDOW_START + timedelta(minutes=5)


def test_features_are_causal_and_use_289_closes() -> None:
    decision = ts("2025-09-01T02:00:00")
    bars = make_bars(decision - timedelta(hours=26), 325, price=100.0)
    row_before = _feature_for_decision("ALTUSDT", decision, bars)
    assert row_before is not None
    future_time = decision + BAR_STEP
    bars[future_time] = replace(bars[future_time], high=10_000.0)
    row_after = _feature_for_decision("ALTUSDT", decision, bars)
    assert row_after is not None
    assert row_after.high24h == row_before.high24h
    assert row_after.ret24h == row_before.ret24h

    del bars[decision - 288 * BAR_STEP]
    assert _feature_for_decision("ALTUSDT", decision, bars) is None


def test_feature_stream_reports_missing_warmup_decisions() -> None:
    bars = make_bars(WINDOW_START - timedelta(hours=25), 300)
    features, audit = hourly_features("ALTUSDT", bars)
    assert features
    assert audit.expected_decisions == 365 * 24
    assert audit.missing_decisions > 0
    assert audit.first_missing_decision is not None


def test_funding_feature_observation_delay_and_exact_eight_hour_lag() -> None:
    decision = ts("2025-09-01T12:00:00")
    current = FundingPoint(
        event_time=decision - timedelta(seconds=60),
        rate=0.002,
        source_row_number=2,
        source_row_hash="current",
    )
    prior = FundingPoint(
        event_time=decision - FUNDING_INTERVAL - timedelta(seconds=60),
        rate=-0.001,
        source_row_number=1,
        source_row_hash="prior",
    )
    selected = _funding_feature(decision, [prior, current])
    assert selected.last is current
    assert selected.prior is prior
    assert selected.last_rate == pytest.approx(0.002)
    assert selected.change_8h == pytest.approx(0.003)
    assert selected.last.available_time == decision
    assert selected.prior.available_time == decision - FUNDING_INTERVAL

    not_yet_available = FundingPoint(decision, 0.5)
    assert _funding_feature(decision, [not_yet_available]).last is None


def test_conditions_are_applied_before_cooldown_and_exact_24h_is_allowed() -> None:
    first = feature(ts("2025-09-01T00:00:00"), ret24=0.20, ret1h=0.01)
    non_signal = feature(ts("2025-09-01T01:00:00"), ret24=0.40, ret1h=-0.01)
    second = feature(
        ts("2025-09-02T00:00:00"), ret24=0.30, ret1h=0.02
    )
    selected, counts = strategy_candidates(STRATEGIES[0], [first, non_signal, second])
    assert counts["raw_condition_matches"] == 2
    assert [item.feature.decision_time for item in selected] == [
        first.decision_time,
        second.decision_time,
    ]
    assert COOLDOWN == timedelta(hours=24)


def test_duplicate_policy_collapses_identical_and_invalidates_conflicts() -> None:
    open_time = ts("2025-09-01T00:00:00")
    close_time = open_time + BAR_STEP - timedelta(milliseconds=1)
    rows = [
        (open_time, close_time, 100.0, 101.0, 99.0, 100.5),
        (open_time, close_time, 100.0, 101.0, 99.0, 100.5),
        (open_time + BAR_STEP, close_time + BAR_STEP, 100.0, 102.0, 98.0, 100.0),
        (open_time + BAR_STEP, close_time + BAR_STEP, 100.0, 103.0, 98.0, 100.0),
        (open_time + 2 * BAR_STEP, close_time + 2 * BAR_STEP, -1.0, 1.0, -2.0, 0.0),
    ]
    bars, audit = _normalise_price_rows(rows, "ALTUSDT")
    assert open_time in bars
    assert open_time + BAR_STEP not in bars
    assert audit.duplicate_identical_rows == 1
    assert audit.duplicate_conflict_timestamps == 1
    assert audit.invalid_rows >= 3


def test_funding_at_entry_and_actual_exit_ties_are_excluded() -> None:
    entry = ts("2025-09-01T00:00:00")
    exit_time = entry + BAR_STEP
    bars = make_bars(entry, 2, price=100.0)
    funding = [
        FundingPoint(entry, 0.10, 100.0),
        FundingPoint(exit_time, 0.10, 100.0),
    ]
    result = evaluate_leg(
        symbol="ALTUSDT",
        direction="long",
        entry_time=entry,
        scheduled_exit_time=exit_time,
        bars=bars,
        funding=funding,
        leverage=1,
        cost_bps=20,
    )
    assert result.terminal_status == "time_exit"
    assert result.funding_fee_count == 0
    assert result.funding_return_on_margin == 0.0
    assert result.event_order_flags["funding_at_entry_excluded"]
    assert result.event_order_flags["funding_at_exit_excluded"]


def test_funding_cashflow_uses_holding_interval_not_feature_availability_lag() -> None:
    entry = ts("2025-09-01T00:00:00")
    exit_time = entry + timedelta(minutes=10)
    bars = make_bars(entry, 3, price=100.0)
    settlement = FundingPoint(entry + timedelta(minutes=2), 0.0001, 100.0)
    result = evaluate_leg(
        symbol="ALTUSDT",
        direction="long",
        entry_time=entry,
        scheduled_exit_time=exit_time,
        bars=bars,
        funding=[settlement],
        leverage=1,
        cost_bps=20,
    )
    assert result.funding_fee_count == 1
    assert result.funding_return_on_margin == pytest.approx(-0.0001)
    assert settlement.available_time > entry
    # Cashflow timing is event-time based; the 60s delay is only for features.
    assert result.funding_events[0]["event_time"] == settlement.event_time


def test_cutoff_mtm_has_no_exit_fee_and_includes_cutoff_settlement() -> None:
    entry = WINDOW_END - timedelta(hours=24)
    bars = make_bars(entry, 288, price=100.0)
    cutoff_settlement = FundingPoint(WINDOW_END, 0.01, 100.0)
    result = evaluate_leg(
        symbol="ALTUSDT",
        direction="long",
        entry_time=entry,
        scheduled_exit_time=WINDOW_END,
        bars=bars,
        funding=[cutoff_settlement],
        leverage=1,
        cost_bps=60,
    )
    assert result.terminal_status == "open_at_cutoff"
    assert result.censored_unrealized
    assert result.event_order_flags["cutoff_mtm_includes_cutoff_settlement"]
    assert result.funding_fee_count == 1
    assert result.fee_return_on_margin == pytest.approx(0.003)


def test_intrabar_funding_order_uses_conservative_proxy() -> None:
    entry = ts("2025-09-01T00:00:00")
    exit_time = entry + BAR_STEP
    bars = make_bars(entry, 2, price=100.0, low=51.6)
    funding = [FundingPoint(entry + timedelta(minutes=2), 0.03, 51.6)]
    result = evaluate_leg(
        symbol="ALTUSDT",
        direction="long",
        entry_time=entry,
        scheduled_exit_time=exit_time,
        bars=bars,
        funding=funding,
        leverage=2,
        cost_bps=20,
    )
    assert result.terminal_status == "liquidated_proxy"
    assert result.liquidation_proxy
    assert result.intrabar_order_proxy
    assert result.event_order_flags["intrabar_order_proxy"]


def test_phase_exit_is_first_later_feature_with_its_own_latency() -> None:
    entry_decision = ts("2025-09-01T00:00:00")
    entry_time = entry_decision + BAR_STEP
    later = feature(
        ts("2025-09-01T01:00:00"), ret24=0.20, ret1h=-0.01, distance=-0.06
    )
    found = find_phase_exit(entry_time, entry_time + timedelta(hours=48), [later])
    assert found == (ts("2025-09-01T01:05:00"), ts("2025-09-01T01:00:00"))
    tie = find_phase_exit(entry_time, ts("2025-09-01T01:05:00"), [later])
    assert tie is None


def _dummy_leg(symbol: str, direction: str, value: float) -> LegResult:
    entry = ts("2025-09-01T00:00:00")
    exit_time = entry + timedelta(hours=48)
    return LegResult(
        symbol=symbol,
        direction=direction,
        entry_time=entry,
        scheduled_exit_time=exit_time,
        effective_exit_time=exit_time,
        terminal_status="time_exit",
        reason=None,
        entry_price=100.0,
        exit_price=100.0,
        expected_bars=1,
        observed_bars=1,
        first_missing_bar=None,
        net_return_on_margin=value,
        gross_price_return_on_margin=value,
        funding_return_on_margin=0.0,
        fee_return_on_margin=0.0,
        funding_fee_count=0,
        funding_missing=False,
        funding_expected=0,
        funding_observed=0,
        funding_events=(),
        liquidation_proxy=False,
        intrabar_order_proxy=False,
        censored_unrealized=False,
        phase_decision_time=None,
        gap_lock=False,
        event_order_flags={"risk_check_before_boundary_fill": True},
    )


def test_hedge_pair_is_half_return_per_leg_not_four_x() -> None:
    row = feature(ts("2025-09-01T00:00:00"), symbol="ALTUSDT")
    candidate = Candidate("HEDGE48_2:ALTUSDT:x", "HEDGE48_2", "ALTUSDT", "hedge", row)
    combined = combine_legs(
        candidate,
        [_dummy_leg("ALTUSDT", "short", 0.20), _dummy_leg("BTCUSDT", "long", -0.10)],
    )
    assert combined["net_return_on_margin"] == pytest.approx(0.05)
    assert len(combined["legs"]) == 2


def test_hedge_liquidation_keeps_remaining_cutoff_leg_censored() -> None:
    row = feature(ts("2025-09-01T00:00:00"), symbol="ALTUSDT")
    candidate = Candidate("HEDGE48_2:ALTUSDT:y", "HEDGE48_2", "ALTUSDT", "hedge", row)
    liquidated = replace(
        _dummy_leg("ALTUSDT", "short", -1.0),
        terminal_status="liquidated_proxy",
        net_return_on_margin=-1.0,
    )
    cutoff = replace(
        _dummy_leg("BTCUSDT", "long", 0.10),
        terminal_status="open_at_cutoff",
        effective_exit_time=WINDOW_END,
        censored_unrealized=True,
    )
    combined = combine_legs(candidate, [liquidated, cutoff])
    assert combined["terminal_status"] == "open_at_cutoff"
    assert combined["censored_unrealized"]


def test_hedge_components_split_known_realized_and_cutoff_unrealized() -> None:
    row = feature(ts("2025-09-01T00:00:00"), symbol="ALTUSDT")
    candidate = Candidate("HEDGE48_2:ALTUSDT:components", "HEDGE48_2", "ALTUSDT", "hedge", row)
    liquidated = replace(
        _dummy_leg("ALTUSDT", "short", -1.0),
        terminal_status="liquidated_proxy",
        net_return_on_margin=-1.0,
    )
    cutoff = replace(
        _dummy_leg("BTCUSDT", "long", 0.2),
        terminal_status="open_at_cutoff",
        effective_exit_time=WINDOW_END,
        censored_unrealized=True,
    )

    combined = combine_legs(candidate, [liquidated, cutoff])
    accounting = combined["component_accounting"]

    assert combined["net_return_on_margin"] == pytest.approx(-0.4)
    assert combined["unrealized_return_on_margin"] == pytest.approx(0.1)
    assert accounting["known_realized_return_on_margin"] == pytest.approx(-0.5)
    assert accounting["known_unrealized_return_on_margin"] == pytest.approx(0.1)
    assert accounting["unknown_return_on_margin"] == pytest.approx(0.0)
    assert accounting["unknown_margin_weight"] == pytest.approx(0.0)
    assert [leg["margin_weight"] for leg in combined["legs"]] == [0.5, 0.5]


def test_hedge_components_keep_known_loss_and_unknown_other_leg_locked() -> None:
    row = feature(ts("2025-09-01T00:00:00"), symbol="ALTUSDT")
    candidate = Candidate("HEDGE48_2:ALTUSDT:unknown", "HEDGE48_2", "ALTUSDT", "hedge", row)
    liquidated = replace(
        _dummy_leg("ALTUSDT", "short", -1.0),
        terminal_status="liquidated_proxy",
        net_return_on_margin=-1.0,
    )
    unresolved = replace(
        _dummy_leg("BTCUSDT", "long", 0.0),
        terminal_status="unresolved",
        net_return_on_margin=None,
        gross_price_return_on_margin=None,
        fee_return_on_margin=None,
        effective_exit_time=WINDOW_END,
        gap_lock=True,
    )

    combined = combine_legs(candidate, [liquidated, unresolved])
    accounting = combined["component_accounting"]
    assert combined["terminal_status"] == "unresolved"
    assert combined["net_return_on_margin"] is None
    assert accounting["known_realized_return_on_margin"] == pytest.approx(-0.5)
    assert accounting["known_unrealized_return_on_margin"] == pytest.approx(0.0)
    assert accounting["unknown_return_on_margin"] is None
    assert accounting["unknown_margin_weight"] == pytest.approx(0.5)

    from dao_vang.experiments.open_profit_account import (
        CandidateTrade,
        simulate_account,
    )

    account = simulate_account(
        [
            CandidateTrade(
                row.entry_time,
                combined["exit_time"],
                "ALTUSDT",
                combined["net_return_on_margin"],
                combined["terminal_status"],
                candidate.candidate_id,
            ),
            CandidateTrade(
                row.entry_time + timedelta(hours=1),
                WINDOW_END,
                "LATERUSDT",
                0.2,
                "time_exit",
                "later",
            ),
        ]
    )
    assert account.non_rankable
    assert account.executed == 1
    assert account.skipped_blocked == 1
    detail = _decorate_executed_detail(combined, account.executed_records[0])
    attribution = _attribution(account, [detail])
    assert attribution["realized_pnl"] == pytest.approx(-500.0)
    assert attribution["unrealized_pnl"] == pytest.approx(0.0)
    assert attribution["unknown_pnl"] is None
    assert attribution["unknown_margin_usd"] == pytest.approx(500.0)
    assert attribution["component_accounting"]["known_bucket_total_excluding_unknown_margin"] == pytest.approx(9000.0)


def test_closed_hedge_conserves_account_and_attributes_btc_leg() -> None:
    row = feature(ts("2025-09-01T00:00:00"), symbol="ALTUSDT")
    candidate = Candidate("HEDGE48_2:ALTUSDT:closed", "HEDGE48_2", "ALTUSDT", "hedge", row)
    combined = combine_legs(
        candidate,
        [_dummy_leg("ALTUSDT", "short", 0.20), _dummy_leg("BTCUSDT", "long", -0.10)],
    )

    from dao_vang.experiments.open_profit_account import (
        CandidateTrade,
        simulate_account,
    )

    account = simulate_account(
        [
            CandidateTrade(
                row.entry_time,
                combined["exit_time"],
                "ALTUSDT",
                combined["net_return_on_margin"],
                combined["terminal_status"],
                candidate.candidate_id,
            )
        ],
        withdraw_profits=True,
    )
    detail = _decorate_executed_detail(combined, account.executed_records[0])
    attribution = _attribution(account, [detail])
    coin = attribution["coin_entry_attribution_static"]
    assert coin["ALTUSDT"]["realized_pnl"] == pytest.approx(100.0)
    assert coin["BTCUSDT"]["realized_pnl"] == pytest.approx(-50.0)
    assert attribution["pair_entry_attribution"]["ALTUSDT"]["realized_pnl"] == pytest.approx(50.0)
    assert attribution["component_accounting"]["fully_known"]
    assert attribution["component_accounting"]["conservation_delta"] == pytest.approx(0.0)


def test_liquidation_before_gap_wins_after_known_funding_order() -> None:
    entry = ts("2025-09-01T00:00:00")
    bars = make_bars(entry, 1, price=100.0, high=200.0)
    settlement = FundingPoint(entry + timedelta(minutes=2), 0.01, 200.0)
    result = evaluate_leg(
        symbol="ALTUSDT",
        direction="short",
        entry_time=entry,
        scheduled_exit_time=entry + timedelta(minutes=10),
        bars=bars,
        funding=[settlement],
        leverage=2,
        cost_bps=20,
    )

    assert result.terminal_status == "liquidated_proxy"
    assert result.gap_lock is False
    assert result.first_missing_bar == entry + BAR_STEP
    assert result.funding_fee_count == 1
    assert result.funding_events[0]["event_time"] == settlement.event_time


def test_survival_to_first_unknown_interval_locks_after_known_funding() -> None:
    entry = ts("2025-09-01T00:00:00")
    bars = make_bars(entry, 1, price=100.0)
    settlement = FundingPoint(entry + timedelta(minutes=2), 0.01, 100.0)
    result = evaluate_leg(
        symbol="ALTUSDT",
        direction="long",
        entry_time=entry,
        scheduled_exit_time=WINDOW_END,
        bars=bars,
        funding=[settlement],
        leverage=1,
        cost_bps=20,
    )

    assert result.terminal_status == "unresolved"
    assert result.gap_lock
    assert result.first_missing_bar == entry + BAR_STEP
    assert result.funding_fee_count == 1
    assert result.funding_return_on_margin == pytest.approx(-0.01)
    assert result.funding_events[0]["event_time"] == settlement.event_time


def test_gap_after_entry_locks_capital_and_is_not_reused() -> None:
    entry = ts("2025-09-01T00:00:00")
    bars = make_bars(entry, 1, price=100.0)
    result = evaluate_leg(
        symbol="ALTUSDT",
        direction="long",
        entry_time=entry,
        scheduled_exit_time=entry + timedelta(minutes=10),
        bars=bars,
        leverage=1,
        cost_bps=20,
    )
    assert result.terminal_status == "unresolved"
    assert result.gap_lock
    assert result.first_missing_bar == entry + BAR_STEP

    from dao_vang.experiments.open_profit_account import (
        CandidateTrade,
        simulate_account,
    )

    account = simulate_account(
        [
            CandidateTrade(entry, WINDOW_END, "ALTUSDT", None, "unresolved", "gap"),
            CandidateTrade(entry + timedelta(hours=1), WINDOW_END, "OTHERUSDT", 0.1, "time_exit", "later"),
        ]
    )
    assert account.non_rankable
    assert account.unresolved_after_entry
    assert account.skipped_blocked == 1


def test_account_bucket_conservation_and_cash_baseline() -> None:
    from dao_vang.experiments.open_profit_account import (
        CandidateTrade,
        simulate_account,
    )

    account = simulate_account(
        [
            CandidateTrade(ts("2025-09-01T00:00:00"), ts("2025-09-01T01:00:00"), "A", 0.10, "time_exit", "a"),
            CandidateTrade(ts("2025-09-01T02:00:00"), ts("2025-09-01T03:00:00"), "A", -0.10, "time_exit", "b"),
        ],
        initial_capital=10_000,
        tranche_count=10,
        withdraw_profits=True,
    )
    assert account.rankable
    assert account.final_profit == pytest.approx(0.0)
    assert account.final_wealth == pytest.approx(
        account.vault + account.reserve + account.active_equity
    )
    assert account.external_contributions == 10_000


def test_event_order_priorities_are_locked() -> None:
    assert event_order_key("risk_check_closed_candle") < event_order_key("time_exit_fill")
    assert event_order_key("time_exit_fill") < event_order_key("funding_settlement")
    assert event_order_key("funding_settlement") < event_order_key("decision")
    assert event_order_key("decision") < event_order_key("entry_fill")


class _SemanticFixtureConnection:
    def __init__(self, stored_symbols: dict[str, str]) -> None:
        self.stored_symbols = stored_symbols

    def execute(self, query: str, parameters: list[object]) -> "_SemanticFixtureConnection":
        self.query = query
        self.parameters = parameters
        return self

    def fetchone(self) -> tuple[object, ...]:
        if "MIN(open_time)" in self.query:
            return (LIT_START, 0)
        path = str(self.parameters[0])
        symbol = self.stored_symbols[Path(path).stem.upper()]
        return (symbol,)

    def fetchall(self) -> list[tuple[object, ...]]:
        if "DESCRIBE" in self.query:
            return [("symbol",)]
        return [self.fetchone()]


LIT_START = ts("2025-12-23T17:30:00")


def _semantic_fixture() -> tuple[list[dict[str, object]], dict[str, object]]:
    price_files = [
        {
            "symbol": "ALTUSDT",
            "file_name": "ALTUSDT.parquet",
            "path": "ALTUSDT.parquet",
            "sha256": "alt-output",
        },
        {
            "symbol": "LITUSDT",
            "file_name": "LITUSDT.parquet",
            "path": "LITUSDT.parquet",
            "sha256": "lit-output",
        },
    ]
    manifest_files = [
        {"symbol": item["symbol"], "file_name": f"{item['symbol']}.parquet"}
        for item in price_files
    ]
    lit_lifecycle = {
        "policy_id": "lit_current_underlying_launch_binance_v1",
        "launch_time_utc": "2025-12-23T17:30:00Z",
        "clip_rule": "exclude every source row with open_time before launch_time_utc",
        "output_first_open_utc": "2025-12-23T17:30:00Z",
        "output_first_time_matches_launch": True,
        "final_audit_missing_actual_bars": 0,
    }
    metadata = {
        "status": "complete",
        "universe": {"file_count": 2, "files": manifest_files},
        "symbols": {
            "ALTUSDT": {
                "symbol": "ALTUSDT",
                "status": "ready",
                "output_sha256": "alt-output",
            },
            "LITUSDT": {
                "symbol": "LITUSDT",
                "status": "ready",
                "output_sha256": "lit-output",
                "lifecycle_policy_id": "lit_current_underlying_launch_binance_v1",
                "lifecycle": lit_lifecycle,
            },
        },
    }
    return price_files, metadata


def _run_semantic_fixture(
    monkeypatch: pytest.MonkeyPatch,
    price_files: list[dict[str, object]],
    metadata: dict[str, object],
    stored_symbols: dict[str, str] | None = None,
) -> dict[str, object]:
    monkeypatch.setattr(annual_runner, "EXPECTED_PRICE_FILE_COUNT", 2)
    provenance = {"metadata": metadata}
    stored = stored_symbols or {"ALTUSDT": "ALTUSDT", "LITUSDT": "LITUSDT"}
    return _validate_price_snapshot_semantics(
        price_root=Path("fixture/prices/klines/5m"),
        price_files=price_files,
        provenance=provenance,
        connection=_SemanticFixtureConnection(stored),
    )


def test_price_semantics_accept_complete_manifest_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    price_files, metadata = _semantic_fixture()
    result = _run_semantic_fixture(monkeypatch, price_files, metadata)
    assert result["validated"] is True
    assert result["errors"] == []


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("hash", "output_hash_mismatch:ALTUSDT"),
        ("symbol", "stored_symbol_mismatch:ALTUSDT:['WRONGUSDT']"),
        ("universe", "manifest_file_universe_mismatch"),
        ("lifecycle", "lifecycle_status:ALTUSDT:incomplete"),
    ],
)
def test_price_semantics_reject_manifest_file_hash_symbol_universe_and_lifecycle_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected: str,
) -> None:
    price_files, metadata = _semantic_fixture()
    if mutation == "hash":
        metadata["symbols"]["ALTUSDT"]["output_sha256"] = "wrong-output"
    elif mutation == "symbol":
        result = _run_semantic_fixture(
            monkeypatch,
            price_files,
            metadata,
            {"ALTUSDT": "WRONGUSDT", "LITUSDT": "LITUSDT"},
        )
        assert expected in result["errors"]
        return
    elif mutation == "universe":
        metadata["universe"]["files"] = metadata["universe"]["files"][:-1]
    else:
        metadata["symbols"]["ALTUSDT"]["status"] = "incomplete"

    result = _run_semantic_fixture(monkeypatch, price_files, metadata)
    assert any(expected in error for error in result["errors"])


def test_static_readiness_does_not_trust_top_level_complete_alone() -> None:
    manifest = {
        "universe": {
            "price_file_count": 328,
            "files": [
                {
                    "symbol": "ALTUSDT",
                    "columns": ["open_time", "close_time", "open", "high", "low", "close"],
                }
            ],
        },
        "price_snapshot_provenance": {
            "metadata": {"status": "complete"},
            "semantic_validation": {
                "errors": ["output_hash_mismatch:ALTUSDT"],
            },
        },
    }
    errors = _run_static_readiness_errors(manifest)
    assert "price_semantic:output_hash_mismatch:ALTUSDT" in errors
