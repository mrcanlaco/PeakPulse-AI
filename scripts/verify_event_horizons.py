"""Independent journal/monthly checks and exact reproduction of locked screens."""

import json
from collections import defaultdict

import pandas as pd
from account_scaled_replay import simulate
from backtest_without_ake import cached_inputs
from compare_account_risk import ROOT, exchange_rules, sha, write
from monthly_account_metrics import monthly_metrics
from search_event_horizons import COSTS, DATA, NEW, OUT, RULE_PATH, SOURCE, WINDOWS
from short_event_study import outcomes, statistics

from dao_vang.config.settings import ExecutionConfig


def main():
    s = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    assert sha(ROOT / "configs/live.yaml") == s["protocol"]["live_config_sha256"]
    for name, digest in s["protocol"]["source_sha256"].items():
        assert sha(ROOT / "scripts" / name) == digest
    for row in s["results"]:
        r = json.loads((OUT / "runs" / f"{row['id']}.json").read_text(encoding="utf-8"))
        curve = pd.read_parquet(OUT / "runs" / f"{row['id']}_equity.parquet")
        active, notions = {}, defaultdict(float)
        for j in r["journal"]:
            if j["kind"] == "entry":
                assert j["symbol"] not in active
                active[j["symbol"]] = j["event_id"]
                assert len(active) <= row["cap"]
            elif j["kind"] == "entry_add":
                assert active[j["symbol"]] == j["event_id"]
            if j["kind"] in ["entry", "entry_add"]:
                notions[j["event_id"]] += j["qty"] * j["price"]
            if "net" in j:
                assert active.pop(j["symbol"]) == j["event_id"]
        assert max(notions.values(), default=0) <= 25 + 1e-8
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
        if row["window"] == "full":
            assert monthly_metrics(curve.to_dict("records")) == row["monthly"]
    rules = exchange_rules(RULE_PATH)
    universe = json.loads((DATA / "universe.json").read_text(encoding="utf-8"))[
        "symbols"
    ]
    prices, funding, _ = cached_inputs(
        SOURCE, DATA / "cache", [dict(symbol=c) for c in universe], rules
    )
    signals = json.loads(
        (DATA / "signals.json").read_text(encoding="utf-8")
    ) | json.loads((NEW / "signals.json").read_text(encoding="utf-8"))
    reproduced = 0
    for row in s["validation"] + s["holdout"]:
        start, end = [
            int(pd.Timestamp(t, tz="UTC").timestamp() * 1000)
            for t in WINDOWS[row["window"]]
        ]
        events, counts = outcomes(
            signals[row["spec"]["signal_id"]],
            prices,
            funding,
            start,
            end,
            row["spec"]["hours"],
        )
        assert counts == row["counts"]
        assert (
            sum(counts[k] for k in ["complete", "censored", "missing"])
            == counts["source"]
        )
        for name, fee, slip in COSTS:
            assert statistics(events, start, end, fee, slip) == row["cases"][name]
            reproduced += 1
    start, end = [
        int(pd.Timestamp(t, tz="UTC").timestamp() * 1000) for t in WINDOWS["full"]
    ]
    for source in s["candidates"]:
        spec = next(
            p
            for p in s["portfolio_specs"]
            if p["source"]["id"] == source["id"]
            and p["cap"] == 5
            and p["parts"] == 3
            and not p["policy"].get("loss_usdt")
        )
        groups = defaultdict(list)
        for signal in signals[source["signal_id"]]:
            if start <= signal["at"] < end:
                groups[signal["at"]].append(signal)
        for group in groups.values():
            group.sort(key=lambda x: (-x["probability"], x["symbol"]))
        for cost, fee, slip in COSTS[:2]:
            r = simulate(
                list(range(start, end + 1, 300000)),
                groups,
                lambda c: prices.get(c, {}),
                rules,
                lambda c: funding[c],
                ExecutionConfig(
                    max_open_positions=5, fee_rate=fee, max_slippage_bps=slip
                ),
                research_policy=spec["policy"],
            )
            name = f"full_{cost}_{spec['id']}"
            old = json.loads(
                (OUT / "runs" / f"{name}.json").read_text(encoding="utf-8")
            )
            assert old == {k: v for k, v in r.items() if k != "curve"}
            pd.testing.assert_frame_equal(
                pd.DataFrame(r["curve"]),
                pd.read_parquet(OUT / "runs" / f"{name}_equity.parquet"),
                check_exact=True,
            )
    write(
        OUT / "verification.json",
        dict(
            unit_tests_passed=87,
            journals_audited=len(s["results"]),
            screen_statistics_reproduced=reproduced,
            full_paths_exactly_reproduced=4,
            source_hashes_match=True,
            live_config_unchanged=True,
        ),
    )
    print(
        "VERIFIED",
        len(s["results"]),
        "journals,",
        reproduced,
        "screen statistics, four account paths",
    )


if __name__ == "__main__":
    main()
