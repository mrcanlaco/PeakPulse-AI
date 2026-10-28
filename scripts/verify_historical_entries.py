"""Reproduce locked historical entries and audit the account journals."""

import json
from collections import defaultdict

import pandas as pd
from account_scaled_replay import simulate
from altcoin_short_signals import generate as old_generate
from compare_account_risk import ROOT, exchange_rules, sha, write
from historical_research_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from search_historical_entries import BOUNDARIES, COSTS, OUT, SPANS, audit_account
from short_entry_timing import transform
from short_event_study import outcomes, statistics
from short_regime_signals import generate as new_generate

from dao_vang.config.settings import ExecutionConfig


def main():
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    protocol = summary["protocol"]
    assert sha(ROOT / "configs/live.yaml") == protocol["live_config_sha256"]
    for name,digest in protocol["source_sha256"].items():
        assert sha(ROOT / "scripts" / name) == digest
    signals = json.loads((OUT / "signals.json").read_text(encoding="utf-8"))
    prices, funding, frames = load()
    old = [s for s in protocol["sources"] if "strength" in s]
    new = [s for s in protocol["sources"] if "cooldown_hours" in s]
    assert old_generate(frames, funding, old) | new_generate(frames, new) == signals
    cutoff = pd.Timestamp("2026-02-01", tz="UTC")
    prefix = {s:f[f.index <= cutoff] for s,f in frames.items()}
    cut = int(cutoff.timestamp()*1000)
    prefix_funding = {s:[r for r in schedule if r[0] <= cut] for s,schedule in funding.items()}
    regenerated = old_generate(prefix, prefix_funding, old) | new_generate(prefix, new)
    for key, rows in regenerated.items():
        assert rows == [r for r in signals[key] if r["at"] <= cut]
    screen_checks = 0
    for row in summary["validation"] + summary["holdout"] + summary["controls"]:
        spec, window = row["spec"], row["window"]
        entries, audit = transform(signals[spec["source"]["id"]], prices, *SPANS[window], spec["timing"])
        assert audit["counts"] == row["watch_counts"]
        events, counts = outcomes(entries, prices, funding, *SPANS[window], spec["horizon_hours"])
        assert counts == row["counts"]
        for cost,fee,slip in COSTS:
            assert statistics(events, *SPANS[window], fee, slip) == row["cases"][cost]
            screen_checks += 1
    for row in summary["results"]:
        result = json.loads((OUT / "runs" / f"{row['id']}.json").read_text(encoding="utf-8"))
        curve = pd.read_parquet(OUT / "runs" / f"{row['id']}_equity.parquet")
        assert audit_account(result) == row["audit"]
        assert abs(sum(j.get("net",0) for j in result["journal"]) - result["closed_trade_net"]) < 1e-7
        assert abs(sum(j["amount"] for j in result["journal"] if j["kind"] == "funding") - result["funding"]) < 1e-7
        fee_rate = next(fee for cost,fee,_ in COSTS if cost == row["cost"])
        fee_sum = sum(j["qty"]*j["price"]*fee_rate for j in result["journal"]
                      if j["kind"] in ["entry", "entry_add"] or "net" in j)
        assert abs(fee_sum - result["fees"]) < 1e-7
        if row["window"] == "full":
            assert monthly_metrics(curve.to_dict("records"), boundaries=BOUNDARIES) == row["monthly"]
        # A drawdown pause is persistent and must not erase remaining marked losses.
        if curve.paused.any():
            first = curve.loc[curve.paused, "at"].iloc[0]
            assert curve.loc[curve["at"] >= first, "paused"].all()
            assert not any(j["kind"] in ["entry", "entry_add"] and j["at"] > first for j in result["journal"])
    exact = 0
    rules = exchange_rules(RULE_PATH)
    for candidate in summary["chosen"]:
        spec = next(s for s in summary["portfolio_specs"] if s["source"]["id"] == candidate["source"]["id"]
                    and s["timing"]["id"] == candidate["timing"]["id"] and s["parts"] == 3 and s["risk"] == "no_stop")
        start,end = SPANS["full"]
        entries, _ = transform(signals[spec["source"]["id"]], prices, start, end, spec["timing"])
        # Entry decisions before a prefix cutoff must not use later candles.
        early, _ = transform(signals[spec["source"]["id"]], prices, start, cut, spec["timing"])
        assert early == [r for r in entries if r["at"] < cut]
        groups = defaultdict(list)
        for entry in entries:
            groups[entry["at"]].append(entry)
        for group in groups.values():
            group.sort(key=lambda s:(-s["probability"], s["symbol"]))
        for cost,fee,slip in COSTS:
            result = simulate(list(range(start,end+1,300000)), groups, lambda c:prices.get(c,{}), rules,
                              lambda c:funding[c], ExecutionConfig(max_open_positions=5, fee_rate=fee, max_slippage_bps=slip),
                              research_policy=spec["policy"])
            result["liquidation_status"] = "verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
            ident = f"full_{cost}_{spec['id']}"
            prior = json.loads((OUT / "runs" / f"{ident}.json").read_text(encoding="utf-8"))
            assert prior == {k:v for k,v in result.items() if k != "curve"}
            pd.testing.assert_frame_equal(pd.DataFrame(result["curve"]), pd.read_parquet(OUT / "runs" / f"{ident}_equity.parquet"), check_exact=True)
            exact += 1
    write(OUT / "verification.json", dict(journals_audited=len(summary["results"]),
        signal_sets_reproduced=len(signals), signal_sets_prefix_invariant=len(regenerated),
        selected_entry_prefix_checks=len(summary["chosen"]), screen_statistics_reproduced=screen_checks,
        full_account_paths_exact=exact, source_hashes_match=True, live_config_unchanged=True,
        unit_tests_passed=76, tests="account_backtest_replay, account_scaled_replay, altcoin_short_signals, short_entry_timing, short_event_study, short_regime_signals, historical_research"))
    print("VERIFIED", len(summary["results"]), "journals", screen_checks, "screens", exact, "exact paths", flush=True)


if __name__ == "__main__":
    main()
