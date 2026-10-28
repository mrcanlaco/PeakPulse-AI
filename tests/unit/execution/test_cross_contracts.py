import copy
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from dao_vang.config.settings import ExecutionConfig
from dao_vang.execution.contracts import (
    ClosedBar,
    StrategyManifest,
    atr14,
    policy_contract,
    tp_price,
)
from dao_vang.execution.evidence import evaluate_evidence, live_gate
from dao_vang.execution.funding import funding_window
from dao_vang.execution.replay import compare_replay, maintenance, replay

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
MID = "a" * 64
RULES = {
    "step_size": ".001",
    "market_step": ".001",
    "tick_size": ".01",
    "min_qty": 0.001,
    "market_min_qty": 0.001,
    "max_qty": 10000,
    "market_max_qty": 10000,
    "min_notional": 5,
}


def frame(at, price=100, signal=False, eligible=True):
    return {
        "at": at.isoformat(),
        "coverage_verified": True,
        "market": {
            "ABCUSDT": {
                "mark": price,
                "bid": price,
                "ask": price + 0.001,
                "trading": True,
                "rules": dict(RULES),
                "bid_depth_qty": 100,
                "tiers": [{"floor": 0, "cap": 1e9, "rate": 0.005, "deduction": 0}],
                "liquidation_fee_rate": 0.005,
            }
        },
        "signals": [
            {
                "event_id": "one",
                "source_id": "one",
                "symbol": "ABCUSDT",
                "manifest_id": MID,
                "observed_at": at.isoformat(),
                "expires_at": (at + timedelta(minutes=5)).isoformat(),
                "reference_price": 100,
                "atr": 2,
                "eligible": eligible,
            }
        ]
        if signal
        else [],
        "funding": [],
    }


def test_atr_only_closed_contiguous_hourly_bars():
    bars = [
        ClosedBar(closed_at=NOW - timedelta(hours=14 - i), high=102, low=98, close=100)
        for i in range(15)
    ]
    assert atr14(bars, NOW) == 4
    with pytest.raises(ValueError, match="closed_bars"):
        atr14(bars, NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="stale"):
        atr14(bars, NOW + timedelta(hours=2))
    bars[5].closed_at += timedelta(minutes=5)
    with pytest.raises(ValueError, match="gap"):
        atr14(bars, NOW)


def test_tp_formula_accounts_for_signed_funding_and_both_fees():
    plain = tp_price(0.25, 100, 1, 0.0125, 0, 0.0005, ".0001")
    paid = tp_price(0.25, 100, 1, 0.0125, -0.2, 0.0005, ".0001")
    received = tp_price(0.25, 100, 1, 0.0125, 0.2, 0.0005, ".0001")
    assert paid < plain < received
    assert 0.25 * (100 - plain) - 0.0125 - 0.25 * plain * 0.0005 >= 1


def test_manifest_change_blocks_execution(tmp_path):
    source = tmp_path / "model"
    source.write_bytes(b"model")
    config = ExecutionConfig()
    manifest = StrategyManifest(
        frozen_at=NOW,
        model_id="m",
        label_version="v",
        threshold=0.5,
        files={"model": hashlib.sha256(b"model").hexdigest()},
        policy=policy_contract(config),
    )
    manifest.verify(tmp_path, config)
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        manifest.verify(tmp_path, config)


def test_cross_loss_not_capped_at_initial_margin_and_marked_at_cutoff():
    data = [frame(NOW, signal=True), frame(NOW + timedelta(hours=1), 150)]
    result = replay(data, ExecutionConfig(), MID)
    assert result["ending_equity"] < 490
    assert not result["liquidated"]
    assert len(result["open_positions"]) == 1
    assert result["curve"][-1]["unrealized"] < -5


def test_liquidation_uses_shared_wallet_and_tiers():
    assert (
        maintenance(100, [{"floor": 0, "cap": 1000, "rate": 0.005, "deduction": 0}])
        == 0.5
    )
    result = replay(
        [frame(NOW, signal=True), frame(NOW + timedelta(hours=1), 2500)],
        ExecutionConfig(),
        MID,
    )
    assert result["liquidated"]
    assert not result["open_positions"]
    assert any(r["kind"] == "liquidation" for r in result["journal"])
    assert result["financially_verified"] is False


def test_drawdown_latches_but_does_not_close_losing_position():
    data = [
        frame(NOW, signal=True),
        frame(NOW + timedelta(hours=1), 600),
        frame(NOW + timedelta(hours=2), 110),
    ]
    result = replay(data, ExecutionConfig(), MID)
    assert result["curve"][-1]["paused"]
    assert result["open_positions"]
    assert not result["liquidated"]


def test_funding_signed_and_not_double_counted():
    a, b, c = (
        frame(NOW, signal=True),
        frame(NOW + timedelta(hours=8)),
        frame(NOW + timedelta(hours=9)),
    )
    event = {"id": "f1", "at": b["at"], "symbol": "ABCUSDT", "mark": 100, "rate": -0.01}
    b["funding"] = [event]
    c["funding"] = [event]
    result = replay([a, b, c], ExecutionConfig(), MID)
    funded = [r for r in result["journal"] if r["kind"] == "funding"]
    assert len(funded) == 1 and funded[0]["amount"] < 0


def test_price_gap_locks_capital_and_disqualifies():
    missing = frame(NOW + timedelta(hours=1))
    missing["market"] = {}
    result = replay([frame(NOW, signal=True), missing], ExecutionConfig(), MID)
    assert "open_position_price_gap" in result["coverage_failures"]
    assert result["open_positions"]
    assert result["open_positions_marked"] is False


def test_tp_closed_profit_and_model_baseline_share_one_wallet_each():
    result = compare_replay(
        [frame(NOW, signal=True), frame(NOW + timedelta(hours=1), 90)],
        ExecutionConfig(),
        MID,
    )
    assert result["model"]["ending_equity"] > 500
    assert result["baseline"]["ending_equity"] == result["model"]["ending_equity"]
    assert result["cash_baseline"] == 500


def test_real_funding_window_caches_complete_provider_response(tmp_path):
    client = Mock()
    at = int((NOW + timedelta(hours=8)).timestamp() * 1000)
    client.get.return_value = [
        {
            "symbol": "ABCUSDT",
            "fundingTime": at,
            "markPrice": "100",
            "fundingRate": "-0.001",
        }
    ]
    args = (tmp_path / "funding.sqlite3", "ABCUSDT", NOW, NOW + timedelta(hours=10))
    first = funding_window(*args, client=client)
    second = funding_window(*args, client=client)
    assert first == second
    assert first[0][0].rate == -0.001
    assert client.get.call_count == 1


def test_funding_provider_error_does_not_certify_coverage(tmp_path):
    client = Mock()
    client.get.side_effect = RuntimeError("unavailable")
    with pytest.raises(RuntimeError):
        funding_window(
            tmp_path / "f.sqlite",
            "ABCUSDT",
            NOW,
            NOW + timedelta(hours=10),
            client=client,
        )


def forward_report():
    end = NOW + timedelta(days=35)
    return {
        "manifest_id": MID,
        "kind": "forward_observed",
        "financially_verified": True,
        "source_verified": True,
        "started_at": NOW.isoformat(),
        "ended_at": end.isoformat(),
        "frozen_at": NOW.isoformat(),
        "events": [
            {
                "event_id": str(i),
                "source_id": str(i),
                "symbol": "ABCUSDT",
                "manifest_id": MID,
                "observed_at": (NOW + timedelta(hours=6 * i)).isoformat(),
            }
            for i in range(100)
        ],
        "daily_equity": [
            {"at": (NOW + timedelta(days=i)).isoformat(), "equity": 500 + i}
            for i in range(36)
        ],
        "intraday_max_drawdown": 0.01,
        "critical_incidents": 0,
        "external_cashflows": 0,
        "open_positions_marked": True,
    }


def test_gate_rejects_history_missing_costs_and_unrealized_losses():
    report = forward_report()
    assert evaluate_evidence(report, MID)["eligible"]
    for key, value in (
        ("kind", "historical_replay"),
        ("financially_verified", False),
        ("open_positions_marked", False),
        ("critical_incidents", 1),
        ("intraday_max_drawdown", 0.2),
    ):
        bad = copy.deepcopy(report)
        bad[key] = value
        assert not evaluate_evidence(bad, MID)["eligible"]
    assert not evaluate_evidence(report, "b" * 64)["eligible"]
    assert not evaluate_evidence(report, MID, 3)["eligible"]
    assert not live_gate(ExecutionConfig(environment="live"), MID)["eligible"]


def test_gate_does_not_call_duplicate_rows_independent_events():
    report = forward_report()
    report["events"][1]["event_id"] = "0"
    assert not evaluate_evidence(report, MID)["eligible"]
