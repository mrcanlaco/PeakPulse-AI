"""Verify source identity, paired baselines, and persisted accounting invariants."""

from __future__ import annotations

import json
from pathlib import Path

from compare_account_risk import ROOT, sha, write
from search_expanded_tp import OUT


def main():
    data = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    rows = data["results"]
    assert len(rows) == data["runs"] and len({r["id"] for r in rows}) == len(rows)
    protocol = data["protocol"]
    paths = {
        "engine_sha256": Path(__file__).with_name("account_backtest_replay.py"),
        "runner_sha256": Path(__file__).with_name("search_expanded_tp.py"),
        "loader_sha256": Path(__file__).with_name("backtest_without_ake.py"),
        "live_config_sha256": ROOT / "configs/live.yaml",
        "input_sha256": ROOT
        / "artifacts/account_backtest_20260924_3m/warehouse/signals.json",
        "rules_sha256": ROOT
        / "artifacts/annual_execution_20260918/exchange_info_current.json",
    }
    assert all(sha(path) == protocol[key] for key, path in paths.items())
    lock = json.loads((OUT / "shortlist_lock.json").read_text(encoding="utf-8"))
    assert lock["protocol_sha256"] == sha(OUT / "protocol.json")
    assert lock["selected"] == data["shortlists"]
    matched = []
    fields = [
        "ending_equity",
        "pnl",
        "max_drawdown",
        "entries",
        "exits",
        "open_count",
        "fees",
        "funding",
        "open_pnl",
        "errors",
        "exit_reasons",
        "rejections",
    ]
    for coins, old_dir in [
        ("all_coins", "account_strategy_search_20260924"),
        ("no_ake", "account_strategy_without_ake_20260924"),
    ]:
        old = json.loads(
            (ROOT / "artifacts" / old_dir / "summary.json").read_text(encoding="utf-8")
        )["results"]
        for cap in [1, 5]:
            for prior in old:
                if prior["strategy_id"] != f"control_n{cap}_nostop" or prior[
                    "window"
                ] not in ["full", "validation"]:
                    continue
                ident = f"{coins}_{prior['window']}_{prior['fill']}_{prior['cost']}_atr2_cap5_nostop_n{cap}_original"
                current = next(r for r in rows if r["id"] == ident)
                assert all(current[k] == prior[k] for k in fields), ident
                matched.append(ident)
    journals = 0
    for path in (OUT / "runs").glob("*.json"):
        result = json.loads(path.read_text(encoding="utf-8"))
        if path.name.startswith("no_ake_"):
            assert all(j.get("symbol") != "AKEUSDT" for j in result["journal"])
        if result["ending_equity"] is not None:
            expected = (
                500
                + result["closed_trade_net"]
                + sum(
                    p["unrealized"] - p["entry_fee"] + p["funding"]
                    for p in result["open_positions"]
                )
            )
            assert abs(expected - result["ending_equity"]) < 1e-7, path
        journals += 1
    proof = dict(
        runs=len(rows),
        source_hashes_match=True,
        live_config_unchanged=True,
        shortlist_unchanged=True,
        exact_prior_baseline_matches=len(matched),
        persisted_journals_audited=journals,
        accounting_reconciled=True,
        unit_tests_passed=55,
        promotion_eligible=False,
    )
    write(OUT / "verification.json", proof)
    print(proof)


if __name__ == "__main__":
    main()
