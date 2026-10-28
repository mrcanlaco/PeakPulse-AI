"""Audit stored research accounting and replay the locked primary exactly."""

import json
from collections import defaultdict
from types import SimpleNamespace

import pandas as pd
from account_scaled_replay import simulate
from backtest_without_ake import cached_inputs
from check_staged_without_stops import OUT, PREVIOUS, ROOT, RULE_PATH, SOURCE
from compare_account_risk import exchange_rules, sha, write
from search_altcoin_families import WINDOWS
from search_staged_trailing import CASES

from dao_vang.config.settings import ExecutionConfig


def main():
    s = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    extra = json.loads((OUT / "no_stop_results.json").read_text(encoding="utf-8"))
    rows = [r for r in s["results"] if r["window"] != "development"] + extra["results"]
    for row in rows:
        r = json.loads((OUT / "runs" / f"{row['id']}.json").read_text(encoding="utf-8"))
        active, notionals, quantities = {}, defaultdict(float), defaultdict(float)
        for j in r["journal"]:
            if j["kind"] in ["entry", "entry_add"]:
                if j["kind"] == "entry":
                    assert j["symbol"] not in active
                    active[j["symbol"]] = j["event_id"]
                    assert len(active) <= row["cap"]
                else:
                    assert active[j["symbol"]] == j["event_id"]
                notionals[j["event_id"]] += j["qty"] * j["price"]
                quantities[j["event_id"]] += j["qty"]
            elif "net" in j:
                assert active.pop(j["symbol"]) == j["event_id"]
                if "qty" in j:
                    assert abs(quantities[j["event_id"]] - j["qty"]) < 1e-8
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
            marked = (
                500
                + r["closed_trade_net"]
                + sum(
                    p["unrealized"] - p["entry_fee"] + p["funding"]
                    for p in r["open_positions"]
                )
            )
            assert abs(marked - r["ending_equity"]) < 1e-7
            assert row["ending_equity"] == r["ending_equity"]
        for p in r["open_positions"]:
            assert abs(quantities[p["event_id"]] - p["qty"]) < 1e-8
    protocol = s["protocol"]
    for key, path in [
        ("engine_sha256", ROOT / "scripts/account_scaled_replay.py"),
        ("runner_sha256", ROOT / "scripts/search_staged_trailing.py"),
        ("signal_sha256", PREVIOUS / "signals.json"),
        ("live_config_sha256", ROOT / "configs/live.yaml"),
    ]:
        assert sha(path) == protocol[key]
    primary = next(f["spec"] for f in s["finalists"] if f["primary"])
    prior = json.loads((PREVIOUS / "summary.json").read_text(encoding="utf-8"))
    rules = exchange_rules(RULE_PATH)
    prices, funding, _ = cached_inputs(
        SOURCE,
        PREVIOUS / "cache",
        [dict(symbol=x) for x in prior["protocol"]["universe"]["symbols"]],
        rules,
    )
    signals = json.loads((PREVIOUS / "signals.json").read_text(encoding="utf-8"))[
        primary["signal_id"]
    ]
    start, end = [
        int(pd.Timestamp(t, tz="UTC").timestamp() * 1000) for t in WINDOWS["full"]
    ]
    groups = defaultdict(list)
    for signal in signals:
        if start <= signal["at"] < end:
            groups[signal["at"]].append(signal)
    for group in groups.values():
        group.sort(key=lambda r: (-r["probability"], r["symbol"]))
    for obs, cost, fee, slip in CASES:
        settings = ExecutionConfig(
            max_open_positions=primary["cap"], fee_rate=fee, max_slippage_bps=slip
        ).model_dump()
        settings.update(primary["settings"])
        r = simulate(
            list(range(start, end + 1, 300000)),
            groups,
            lambda coin: prices.get(coin, {}),
            rules,
            lambda coin: funding[coin],
            SimpleNamespace(**settings),
            research_policy=dict(primary["policy"], observation_minutes=obs),
        )
        name = f"full_{obs}m_{cost}_{primary['id']}"
        old = json.loads((OUT / "runs" / f"{name}.json").read_text(encoding="utf-8"))
        assert {k: v for k, v in r.items() if k != "curve"} == old
        pd.testing.assert_frame_equal(
            pd.DataFrame(r["curve"]),
            pd.read_parquet(OUT / "runs" / f"{name}_equity.parquet"),
            check_exact=True,
        )
    write(
        OUT / "verification.json",
        dict(
            main_runs=s["runs"],
            no_stop_runs=len(extra["results"]),
            journals_audited=len(rows),
            primary_exact_replays=4,
            original_exact_regressions=len(s["original_regressions"]),
            source_hashes_match=True,
            live_config_unchanged=True,
            primary_unchanged=True,
        ),
    )
    print("VERIFIED", len(rows), "journals and four exact primary replays")


if __name__ == "__main__":
    main()
