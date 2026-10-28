"""Audit monthly-goal batch and measure prior candidates on monthly equity."""

import json
from collections import defaultdict

import pandas as pd
from account_scaled_replay import simulate
from backtest_without_ake import cached_inputs
from compare_account_risk import ROOT, exchange_rules, sha, write
from monthly_account_metrics import monthly_metrics
from search_monthly_target import CASES, DATA, OUT, RULE_PATH, SOURCE, WINDOWS
from short_regime_signals import generate

from dao_vang.config.settings import ExecutionConfig


def main():
    s = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    assert sha(ROOT / "configs/live.yaml") == s["protocol"]["live_config_sha256"]
    for name, digest in s["protocol"]["source_code_sha256"].items():
        assert sha(ROOT / "scripts" / name) == digest
    frames = {
        p.stem.removeprefix("features_"): pd.read_parquet(p)
        for p in OUT.glob("features_*.parquet")
    }
    manifest = json.loads((OUT / "features_manifest.json").read_text(encoding="utf-8"))
    assert all(sha(OUT / name) == digest for name, digest in manifest.items())
    signals = json.loads((OUT / "signals.json").read_text(encoding="utf-8"))
    assert generate(frames) == signals
    cutoff = pd.Timestamp("2026-08-24", tz="UTC")
    prefix = generate({coin: h.loc[h.index < cutoff] for coin, h in frames.items()})
    assert prefix == {
        key: [r for r in rows if r["at"] < cutoff.timestamp() * 1000]
        for key, rows in signals.items()
    }
    final_rows = [r for r in s["results"] if r["window"] != "development"]
    for row in final_rows:
        r = json.loads((OUT / "runs" / f"{row['id']}.json").read_text(encoding="utf-8"))
        curve = pd.read_parquet(OUT / "runs" / f"{row['id']}_equity.parquet")
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
            assert curve.iloc[-1].equity == row["ending_equity"]
        if row["window"] == "full":
            assert monthly_metrics(curve.to_dict("records")) == row["monthly"]
    universe = json.loads((DATA / "universe.json").read_text(encoding="utf-8"))[
        "symbols"
    ]
    rules = exchange_rules(RULE_PATH)
    prices, funding, _ = cached_inputs(
        SOURCE, DATA / "cache", [dict(symbol=c) for c in universe], rules
    )
    spec = next(f["spec"] for f in s["finalists"] if f["primary"])
    start, end = [
        int(pd.Timestamp(t, tz="UTC").timestamp() * 1000) for t in WINDOWS["full"]
    ]
    grouped = defaultdict(list)
    for signal in signals[spec["signal_id"]]:
        if start <= signal["at"] < end:
            grouped[signal["at"]].append(signal)
    for group in grouped.values():
        group.sort(key=lambda r: (-r["probability"], r["symbol"]))
    for cost, fee, slip in CASES:
        r = simulate(
            list(range(start, end + 1, 300000)),
            grouped,
            lambda c: prices.get(c, {}),
            rules,
            lambda c: funding[c],
            ExecutionConfig(
                max_open_positions=spec["cap"],
                fee_rate=fee,
                max_slippage_bps=slip,
                atr_multiplier=2,
            ),
            research_policy=spec["policy"],
        )
        name = f"full_{cost}_{spec['id']}"
        old = json.loads((OUT / "runs" / f"{name}.json").read_text(encoding="utf-8"))
        assert old == {k: v for k, v in r.items() if k != "curve"}
        pd.testing.assert_frame_equal(
            pd.DataFrame(r["curve"]),
            pd.read_parquet(OUT / "runs" / f"{name}_equity.parquet"),
            check_exact=True,
        )
    benchmarks = []
    prior_path = ROOT / "artifacts/short_entry_search_20260925"
    prior = json.loads((prior_path / "summary.json").read_text(encoding="utf-8"))
    for row in prior["results"]:
        if row["window"] == "full" and row["strategy_id"] in [
            "weak_rank_immediate_fixed",
            "weak_rank_immediate_trailing",
            "weak_rank_delay180_trailing",
        ]:
            curve = pd.read_parquet(prior_path / "runs" / f"{row['id']}_equity.parquet")
            benchmarks.append(
                dict(
                    id=row["id"],
                    label=row["label"],
                    cost=row["cost"],
                    observation_minutes=row["observation_minutes"],
                    ending_equity=row["ending_equity"],
                    monthly=monthly_metrics(curve.to_dict("records")),
                )
            )
    write(OUT / "prior_monthly_benchmarks.json", benchmarks)
    write(
        OUT / "verification.json",
        dict(
            signals_reproduced=len(signals),
            real_data_prefix_invariance=True,
            feature_hashes_verified=len(manifest),
            journals_audited=len(final_rows),
            primary_exact_replays=2,
            monthly_account_metrics_recomputed=True,
            live_config_unchanged=True,
            source_hashes_match=True,
        ),
    )
    print("VERIFIED", len(final_rows), "journals;", len(signals), "signal sets")


if __name__ == "__main__":
    main()
