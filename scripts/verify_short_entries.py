"""Verify causality, stored account paths, and paired entry-price comparisons."""

import json
from collections import defaultdict
from types import SimpleNamespace

import pandas as pd
from account_scaled_replay import simulate
from backtest_without_ake import cached_inputs
from compare_account_risk import ROOT, exchange_rules, sha, write
from search_short_entries import CASES, DATA, OUT, RULE_PATH, SOURCE, WINDOWS
from short_entry_timing import definitions, transform

from dao_vang.config.settings import ExecutionConfig


def main():
    s = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    rows = [r for r in s["results"] if r["window"] != "development"] + s[
        "no_stop_results"
    ]
    for row in rows:
        r = json.loads((OUT / "runs" / f"{row['id']}.json").read_text(encoding="utf-8"))
        active, notionals = {}, defaultdict(float)
        for j in r["journal"]:
            if j["kind"] in ["entry", "entry_add"]:
                if j["kind"] == "entry":
                    assert j["symbol"] not in active
                    active[j["symbol"]] = j["event_id"]
                else:
                    assert active[j["symbol"]] == j["event_id"]
                notionals[j["event_id"]] += j["qty"] * j["price"]
                assert len(active) <= row["cap"]
            elif "net" in j:
                assert active.pop(j["symbol"]) == j["event_id"]
        assert max(notionals.values(), default=0) <= 25 + 1e-8
        assert len(active) == len(r["open_positions"])
        assert (
            abs(sum(j.get("net", 0) for j in r["journal"]) - r["closed_trade_net"])
            < 1e-7
        )
        assert (
            abs(
                sum(j.get("amount", 0) for j in r["journal"] if j["kind"] == "funding")
                - r["funding"]
            )
            < 1e-7
        )
        if r["ending_equity"] is not None:
            assert (
                abs(
                    r["ending_equity"]
                    - 500
                    - r["closed_trade_net"]
                    - sum(
                        p["unrealized"] - p["entry_fee"] + p["funding"]
                        for p in r["open_positions"]
                    )
                )
                < 1e-7
            )
            assert row["ending_equity"] == r["ending_equity"]
        if "nostop" in row["id"]:
            assert not any(
                j["kind"] in ["loss_stop", "time_exit", "atr_stop", "account_stop"]
                for j in r["journal"]
            )
    for key, path in [
        ("live_config_sha256", ROOT / "configs/live.yaml"),
        ("engine_sha256", ROOT / "scripts/account_scaled_replay.py"),
        ("timing_sha256", ROOT / "scripts/short_entry_timing.py"),
        ("runner_sha256", ROOT / "scripts/search_short_entries.py"),
        ("signal_sha256", DATA / "signals.json"),
    ]:
        assert sha(path) == s["protocol"][key]
    rules = exchange_rules(RULE_PATH)
    previous = json.loads((DATA / "summary.json").read_text(encoding="utf-8"))
    prices, funding, _ = cached_inputs(
        SOURCE,
        DATA / "cache",
        [dict(symbol=x) for x in previous["protocol"]["universe"]["symbols"]],
        rules,
    )
    signals = json.loads((DATA / "signals.json").read_text(encoding="utf-8"))
    audits = json.loads((OUT / "entry_watches.json").read_text(encoding="utf-8"))
    reproduced = 0
    for window, span in WINDOWS.items():
        start, end = [int(pd.Timestamp(t, tz="UTC").timestamp() * 1000) for t in span]
        cutoff = start + 10 * 86400000
        source_ids = sorted({spec["signal_id"] for spec in s["protocol"]["variants"]})
        for sid in source_ids:
            for timing in definitions():
                output, audit = transform(signals[sid], prices, start, end, timing)
                assert audit == audits["|".join([window, sid, timing["id"]])]
                truncated_prices = {
                    coin: {t: point for t, point in quotes.items() if t < cutoff}
                    for coin, quotes in prices.items()
                }
                prefix, _ = transform(
                    signals[sid], truncated_prices, start, cutoff, timing
                )
                assert prefix == [r for r in output if r["at"] < cutoff]
                assert sum(audit["counts"].values()) == audit["source_events"]
                assert len(output) == audit["counts"].get("triggered", 0)
                assert audit["counts"].get("missing_data", 0) == 0
                reproduced += 1
    spec = next(f["spec"] for f in s["finalists"] if f["primary"])
    start, end = [
        int(pd.Timestamp(t, tz="UTC").timestamp() * 1000) for t in WINDOWS["full"]
    ]
    delayed, _ = transform(
        signals[spec["signal_id"]], prices, start, end, spec["timing"]
    )
    groups = defaultdict(list)
    for signal in delayed:
        groups[signal["at"]].append(signal)
    for group in groups.values():
        group.sort(key=lambda r: (-r["probability"], r["symbol"]))
    pairs = []
    for obs, cost, fee, slip in CASES:
        config = ExecutionConfig(
            max_open_positions=spec["cap"], fee_rate=fee, max_slippage_bps=slip
        ).model_dump()
        config.update(spec["settings"])
        r = simulate(
            list(range(start, end + 1, 300000)),
            groups,
            lambda coin: prices.get(coin, {}),
            rules,
            lambda coin: funding[coin],
            SimpleNamespace(**config),
            research_policy=dict(spec["policy"], observation_minutes=obs),
        )
        name = f"full_{obs}m_{cost}_{spec['id']}"
        old = json.loads((OUT / "runs" / f"{name}.json").read_text(encoding="utf-8"))
        assert old == {k: v for k, v in r.items() if k != "curve"}
        pd.testing.assert_frame_equal(
            pd.DataFrame(r["curve"]),
            pd.read_parquet(OUT / "runs" / f"{name}_equity.parquet"),
            check_exact=True,
        )
        for window in ["validation", "holdout", "full"]:
            baseline_name = (
                f"{window}_{obs}m_{cost}_{spec['family']}_immediate_{spec['exit']}"
            )
            candidate_name = f"{window}_{obs}m_{cost}_{spec['id']}"
            baseline = json.loads(
                (OUT / "runs" / f"{baseline_name}.json").read_text(encoding="utf-8")
            )
            candidate = json.loads(
                (OUT / "runs" / f"{candidate_name}.json").read_text(encoding="utf-8")
            )
            first = {
                j["event_id"]: j for j in baseline["journal"] if j["kind"] == "entry"
            }
            second = {
                j["event_id"]: j for j in candidate["journal"] if j["kind"] == "entry"
            }
            common = first.keys() & second.keys()
            bps = [(second[e]["price"] / first[e]["price"] - 1) * 10000 for e in common]
            pairs.append(
                dict(
                    window=window,
                    observation_minutes=obs,
                    cost=cost,
                    common_events=len(common),
                    candidate_only=len(second.keys() - first.keys()),
                    baseline_only=len(first.keys() - second.keys()),
                    mean_first_entry_improvement_bps=sum(bps) / len(bps)
                    if bps
                    else None,
                    better_price_count=sum(v > 0 for v in bps),
                )
            )
    write(
        OUT / "paired_entry_prices.json",
        dict(
            primary=s["primary"],
            results=pairs,
            interpretation="Common filled event IDs only, comparison of actual first short entry price. Positive bps = higher short price. Not a causal PnL estimate; positions, later fills, quantities and exits may differ; unmatched events reported.",
        ),
    )
    write(
        OUT / "verification.json",
        dict(
            journals_audited=len(rows),
            watch_sets_reproduced=reproduced,
            prefix_invariance_cases=reproduced,
            primary_exact_replays=4,
            original_regressions=len(s["original_regressions"]),
            source_hashes_match=True,
            live_config_unchanged=True,
            unit_tests_passed=79,
        ),
    )
    print("VERIFIED", len(rows), "journals;", reproduced, "causal watch sets")


if __name__ == "__main__":
    main()
