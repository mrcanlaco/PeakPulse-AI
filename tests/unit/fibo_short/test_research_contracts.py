"""Behavioral contracts for comparing sizing policies without changing signals."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RESEARCH_DIR = Path(__file__).resolve().parents[3] / "scripts" / "fibo_research"
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

from verify_red_team_audit_2026 import run_standalone_config


def sizing_candidate(score: float) -> dict:
    timestamp = "2025-01-01T00:00:00+00:00"
    return {
        "symbol": "TESTUSDT", "tf": "4h", "idx_1h": 0,
        "wave_key": "test-wave", "decision_time": timestamp,
        "sig": SimpleNamespace(
            id="sizing-contract", signal_time=timestamp,
            h1_confirmation=SimpleNamespace(
                confirmation_tier="COMBO_1_2", pattern_name="ENGULFING",
                current_fibo_ratio=0.55,
            ),
            wave=SimpleNamespace(impulse_drop_pct=0.1, prior_pump_pct=0.8),
        ),
        "setup": SimpleNamespace(
            entry_price=100.0, stop_loss=120.0, tp1=90.0, tp2=80.0, tp3=70.0,
        ),
        "fibo_levels": SimpleNamespace(level_0000=50.0, wave_range=80.0),
        "atr_1h": 1.0, "full_conviction_score": score,
        "f1_expanded": True, "imp_drop_pct": 10.0, "imp_ker": 0.7,
        "future_slice": [{
            "open_time_str": timestamp, "open": 100.0,
            "high": 101.0, "low": 94.0, "close": 95.0,
        }],
    }


@pytest.mark.parametrize("score,mult", [(80.0, 1.50), (68.0, 1.15), (55.0, 0.80), (30.0, 0.80)])
def test_fixed_sizing_changes_exposure_without_changing_trade(score, mult):
    candidate = sizing_candidate(score)
    fixed = run_standalone_config([candidate], "m6_f4_expanded", sizing_mode="fixed_1x")[0]
    sized = run_standalone_config([candidate], "m6_f4_expanded", sizing_mode="conviction_150_115_080")[0]
    assert fixed["pos_mult"] == 1.0
    assert sized["pos_mult"] == mult
    assert fixed["trade"].trade_id == sized["trade"].trade_id
    assert fixed["sim"] == sized["sim"]
    assert fixed["trade"].gross_return_pct == pytest.approx(5.0)
    assert fixed["trade"].net_return_pct == pytest.approx(4.8)
    assert sized["trade"].net_return_pct == pytest.approx(4.8 * mult)


def test_unknown_sizing_policy_is_rejected():
    with pytest.raises(ValueError, match="sizing_mode"):
        run_standalone_config([sizing_candidate(80)], "m6_f4_expanded", sizing_mode="typo")


def test_is_valuation_includes_final_candle_settlement():
    import pandas as pd
    from verify_red_team_audit_2026 import compute_portfolio_nav_and_concurrency
    from universe_reaudit_v402_worker import IS_VALUATION_END_UTC

    candidate = sizing_candidate(80)
    entry = "2025-12-31T23:00:00+00:00"
    candidate["decision_time"] = entry
    candidate["future_slice"][0]["open_time_str"] = entry
    items = run_standalone_config([candidate], "m6_f4_expanded", sizing_mode="fixed_1x")
    result = compute_portfolio_nav_and_concurrency(
        items, window_start_utc=entry,
        window_end_utc=IS_VALUATION_END_UTC.isoformat(),
    )["nav_simulation_20pct_notional_per_1x"]
    # Short 20 notional gains 1 dollar on 100->95, and pays .04 dollars.
    assert pd.Timestamp(items[0]["trade"].exit_time) == IS_VALUATION_END_UTC
    assert result["compounded_final_nav"] == pytest.approx(100.96)


def test_reconciliation_catches_missing_final_settlement_and_duplicate_ids():
    from ledger_reconciliation import reconcile_settled_ledger

    record = {"trade_id": "closed", "pos_mult": 1.5, "net_return_pct": 7.2,
              "n0_add": 30.0, "n0_comp": 33.0,
              "funding_dollar_add": -0.01, "funding_dollar_comp": -0.011,
              "realized_pnl_dollar_add": 1.43, "realized_pnl_dollar_comp": 1.573}
    assert reconcile_settled_ledger([record])["all_passed"]
    bad = {**record, "realized_pnl_dollar_comp": 1.3}
    assert not reconcile_settled_ledger([bad])["all_passed"]
    assert not reconcile_settled_ledger([record, record])["all_passed"]


@pytest.mark.parametrize("fee_bps", [0.0, 20.0, 40.0, 60.0])
def test_summary_uses_actual_cost_for_unscaled_comparison(fee_bps):
    from verify_red_team_reaudit_v402 import summarize_audit_items_v402

    items = run_standalone_config(
        [sizing_candidate(80)], "m6_f4_expanded", round_trip_fee_bps=fee_bps,
        sizing_mode="conviction_150_115_080",
    )
    summary = summarize_audit_items_v402(items, include_bootstrap=False)
    expected_1x = 5.0 - fee_bps / 100.0
    assert summary["unscaled_1x_avg_net_pct"] == pytest.approx(expected_1x)
    assert summary["avg_net_return_pct"] == pytest.approx(expected_1x * 1.5)


def test_benchmark_pivot_contract_matches_universe(monkeypatch):
    import pandas as pd
    import verify_red_team_audit_2026 as research

    configs = []
    real_config = research.FiboTrendShortConfig

    def capture_config(**kwargs):
        config = real_config(**kwargs)
        configs.append(config)
        return config

    monkeypatch.setattr(research, "FiboTrendShortConfig", capture_config)
    research.collect_candidates_and_run_modes(
        {}, {}, entry_start_ts=pd.Timestamp("2024-01-01T00:00:00Z"),
        entry_end_ts=pd.Timestamp("2025-12-31T23:59:59Z"),
        swing_right_bars=2,
    )
    # These are the frozen universe policy's two-sided confirmed pivot rules.
    assert configs[0].swing_pivot_left_bars == 2
    assert configs[0].swing_pivot_right_bars == 2
    assert configs[0].conviction_mult_c == .80


def test_universe_low_score_sizing_matches_declared_three_tier_method(monkeypatch):
    import pandas as pd
    import universe_reaudit_v402_worker as worker
    configs = []
    real = worker.FiboTrendShortConfig

    def capture(**kwargs):
        cfg = real(**kwargs)
        configs.append(cfg)
        return cfg

    monkeypatch.setattr(worker, "FiboTrendShortConfig", capture)
    worker.collect_symbol_milestones_v402("TESTUSDT", pd.DataFrame(), {},
        entry_start_ts=pd.Timestamp("2024-01-01T00:00:00Z"),
        entry_end_ts=pd.Timestamp("2025-12-31T23:59:59Z"))
    assert configs[0].conviction_mult_c == .80


def test_short_stop_gap_uses_first_available_open_across_simulators():
    from dao_vang.fibo_short.backtest import _simulate_trade_outcome
    from study_factor2_3_4_complete_2025 import simulate_custom_trade
    from verify_red_team_audit_2026 import simulate_trade_v2

    bars = [{"open_time_str": "2025-01-01T01:00:00+00:00", "open": 120.0,
             "high": 125.0, "low": 118.0, "close": 121.0}]
    kwargs = dict(entry_price=100.0, stop_loss=110.0, tp1=90.0, tp2=80.0,
                  tp3=70.0, round_trip_fee_bps=20.0)
    result = simulate_trade_v2(bars, **kwargs)
    assert result["exit_price"] == 120.0
    assert result["net_pct"] == pytest.approx(-20.2)
    base = _simulate_trade_outcome(bars, **kwargs)
    legacy = simulate_custom_trade(bars, **kwargs, return_exit_meta=True)
    assert base[1] == 120.0
    # Custom simulator returns metrics followed by exit metadata.
    assert legacy[-3] == 120.0


@pytest.mark.parametrize("cost", [0, 20, 40, 60])
def test_repriced_trace_matches_fresh_simulation(cost):
    from pit_method_v406 import with_cost
    from verify_red_team_audit_2026 import simulate_trade_v2

    bars = [
        {"open_time_str": "2025-01-01T00:00:00Z", "open": 95, "high": 99, "low": 89, "close": 92},
        {"open_time_str": "2025-01-01T01:00:00Z", "open": 98, "high": 101, "low": 97, "close": 100},
    ]
    args = dict(entry_price=100, stop_loss=110, tp1=90, tp2=80, tp3=70)
    baseline = simulate_trade_v2(bars, **args, round_trip_fee_bps=20)
    fresh = simulate_trade_v2(bars, **args, round_trip_fee_bps=cost)
    adjusted = with_cost(baseline, cost, risk_pct=10)
    assert adjusted["net_pct"] == pytest.approx(fresh["net_pct"])
    assert adjusted["r_mult"] == pytest.approx(fresh["r_mult"])
    assert adjusted["exit_price"] == fresh["exit_price"]
    assert sum(x["bar_fee_pct"] for x in adjusted["bar_trace"]) == pytest.approx(cost / 100)
    for actual, expected in zip(adjusted["bar_trace"], fresh["bar_trace"], strict=True):
        assert actual["bar_fee_pct"] == pytest.approx(expected["bar_fee_pct"])
        assert actual["delta_gross_pct"] == expected["delta_gross_pct"]
