from datetime import datetime, timedelta, timezone

from dao_vang.config.settings import ExecutionConfig
from dao_vang.execution.contracts import StrategyManifest, TradeSignal, policy_contract
from dao_vang.execution.evidence import evaluate_evidence
from dao_vang.execution.forward_report import export_forward
from dao_vang.execution.store import ExecutionStore


def test_forward_export_discloses_gaps_and_never_promotes_simulation(tmp_path):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    manifest = StrategyManifest(
        frozen_at=start,
        model_id="m",
        label_version="v",
        threshold=0.5,
        files={"model": "a" * 64},
        policy=policy_contract(ExecutionConfig()),
    )
    store = ExecutionStore(tmp_path / "state.sqlite3")
    empty = export_forward(store, manifest)
    assert empty["status"] == "waiting_for_account_observations"
    assert not evaluate_evidence(empty, manifest.identity)["eligible"]
    for day in (0, 2):
        store.record(
            "equity",
            {
                "at": (start + timedelta(days=day)).isoformat(),
                "equity": 500 + day,
                "drawdown": 0,
            },
        )
    for source, event, hours, eligible in [
        ("first", "episode", 0, True),
        ("duplicate", "episode", 6, True),
        ("overlap", "other", 1, True),
        ("rejected", "reject", 12, False),
        ("next", "next", 24, True),
    ]:
        at = start + timedelta(hours=hours)
        store.signal(
            TradeSignal(
                event_id=event,
                source_id=source,
                manifest_id=manifest.identity,
                symbol="ABCUSDT",
                observed_at=at,
                expires_at=at + timedelta(minutes=5),
                reference_price=100,
                atr=2,
                eligible=eligible,
            )
        )
    report = export_forward(store, manifest)
    assert report["daily_gaps"] == [(start + timedelta(days=1)).isoformat()]
    assert [row["event_id"] for row in report["events"]] == ["episode", "next"]
    assert report["excluded_overlapping_observations"] == 2
    assert not report["financially_verified"]
    assert not report["source_verified"]
    assert not report["open_positions_marked"]
    assert (
        "account_observation_gaps"
        in evaluate_evidence(report, manifest.identity)["reasons"]
    )
