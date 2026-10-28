"""Measure signal edge before new portfolio trials; retain all screening results."""

import json
from collections import defaultdict

import pandas as pd
from account_scaled_replay import simulate
from altcoin_short_signals import definitions as prior_definitions
from backtest_without_ake import cached_inputs
from compare_account_risk import ROOT, exchange_rules, sha, summarize, write
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import OUT as DATA
from prepare_altcoin_search import RULE_PATH, SOURCE
from search_altcoin_families import WINDOWS
from short_event_study import outcomes, statistics
from short_regime_signals import definitions as new_definitions

from dao_vang.config.settings import ExecutionConfig

OUT = ROOT / "artifacts/monthly_target_batch02_20260925"
NEW = ROOT / "artifacts/monthly_target_batch01_20260925"
COSTS = [("base", 0.0005, 20), ("stress", 0.001, 50), ("low_assumed", 0.0005, 2)]


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "runs").mkdir(exist_ok=True)
    source_defs = prior_definitions() + new_definitions()
    signals = json.loads(
        (DATA / "signals.json").read_text(encoding="utf-8")
    ) | json.loads((NEW / "signals.json").read_text(encoding="utf-8"))
    specs = [
        dict(id=f"{s['id']}_horizon{h}", source=s, signal_id=s["id"], hours=h)
        for s in source_defs
        for h in [1, 4, 12, 24, 48]
    ]
    protocol = dict(
        created_at=pd.Timestamp.now(tz="UTC").isoformat(),
        hypotheses=specs,
        cases=COSTS,
        windows=WINDOWS,
        purpose="Screen existing48 signal rules at five forward holding horizons without conflating event return and account profit. Preserve target >=50% every monthly marked account return.",
        event_method="Independent hypothetical short per signal, entry/exit next5m opens plus adverse slippage, settled funding in (entry,exit]. Fractional sizing, no intermediate stops, leverage/liquidation/capacity. Events overlapping in coin/time are NOT independent. Censor if exit reaches or exceeds evaluation-window end, missing prices are invalid not favorable fills. Events with same signal can overlap; never sum these returns as account profit.",
        selection="Development only: select highest worst base/stress CI lower bound per family among >=100 complete events and no missing outcomes. Positive CI lower bounds recorded separately, not required for diagnostic selection. Lock family candidates before validation; then select up to two by worst validation mean among >=100 complete events/no missing. Lock before final. Low2bps is hypothetical sensitivity only and never selects candidates.",
        portfolio="For up to two diagnostic candidates: four cap/parts combinations1/5 x1/3 and SLnone/1USDT, fixed TP cap5USDT per full position and time exit at selected horizon. Total notional25, x5, equity500, same20% entry pause. Funding/market precision/margins and open inventory accounted. Does NOT implement pure event-study no-TP exit. No live modification; no strategy is proved by retrospective results.",
        limitations="Three months repeatedly inspected; no pristine holdout. Current listing/filter survivor bias, no historical orderbook or maintenance tiers, MMR1% proxy. Low slippage not independently observed. Cluster CIs unadjusted for multiple comparisons.",
        live_config_sha256=sha(ROOT / "configs/live.yaml"),
        source_sha256={
            name: sha(ROOT / "scripts" / name)
            for name in [
                "short_event_study.py",
                "search_event_horizons.py",
                "account_scaled_replay.py",
                "monthly_account_metrics.py",
            ]
        },
    )
    write(OUT / "protocol.json", protocol)
    universe = json.loads((DATA / "universe.json").read_text(encoding="utf-8"))[
        "symbols"
    ]
    rules = exchange_rules(RULE_PATH)
    prices, funding, proofs = cached_inputs(
        SOURCE, DATA / "cache", [dict(symbol=s) for s in universe], rules
    )
    write(OUT / "input_evidence.json", proofs)
    spans = {
        w: tuple(int(pd.Timestamp(t, tz="UTC").timestamp() * 1000) for t in bounds)
        for w, bounds in WINDOWS.items()
    }

    def screen(spec, window):
        start, end = spans[window]
        events, counts = outcomes(
            signals[spec["signal_id"]], prices, funding, start, end, spec["hours"]
        )
        cases = {
            name: statistics(events, start, end, fee, slip) for name, fee, slip in COSTS
        }
        complete = counts["missing"] == 0 and counts["complete"] >= 100
        lower = (
            min(cases[c]["ci95"][0] for c in ["base", "stress"]) if complete else None
        )
        mean = (
            min(cases[c]["mean_net_return"] for c in ["base", "stress"])
            if complete
            else None
        )
        return dict(
            id=spec["id"],
            spec=spec,
            window=window,
            counts=counts,
            cases=cases,
            complete=complete,
            worst_lower=lower,
            worst_mean=mean,
            positive_screen=complete and lower > 0,
        )

    development = []
    for i, spec in enumerate(specs, 1):
        development.append(screen(spec, "development"))
        if i % 30 == 0:
            print("Screen", i, "/", len(specs), flush=True)
    write(OUT / "development.json", development)
    selected = []
    for family in sorted({s["source"]["family"] for s in specs}):
        pool = [
            r
            for r in development
            if r["spec"]["source"]["family"] == family and r["complete"]
        ]
        if pool:
            selected.append(
                max(pool, key=lambda r: (r["worst_lower"], r["worst_mean"]))["spec"]
            )
    write(
        OUT / "family_lock.json",
        dict(specs=selected, locked_at=pd.Timestamp.now(tz="UTC").isoformat()),
    )
    validation = [screen(spec, "validation") for spec in selected]
    ordered = sorted(
        [r for r in validation if r["complete"]], key=lambda r: -r["worst_mean"]
    )
    candidates = [r["spec"] for r in ordered[:2]]
    write(
        OUT / "portfolio_lock.json",
        dict(
            candidates=candidates,
            locked_at=pd.Timestamp.now(tz="UTC").isoformat(),
            final_not_run=True,
        ),
    )
    print("LOCKED", [s["id"] for s in candidates], flush=True)
    holdout = [screen(spec, "holdout") for spec in selected]
    portfolio_specs = []
    for source in candidates:
        for cap in [1, 5]:
            for parts in [1, 3]:
                for loss in [None, 1]:
                    policy = dict(
                        fixed_tp_usdt=5,
                        max_hold_hours=source["hours"],
                        position_notional=25,
                        entry_parts=parts,
                        entry_mode="single" if parts == 1 else "favorable",
                        entry_step_atr=0.5,
                        add_expiry_hours=6,
                        require_split_eligibility=True,
                    )
                    if loss:
                        policy["loss_usdt"] = loss
                    portfolio_specs.append(
                        dict(
                            id=f"{source['id']}_n{cap}_p{parts}_sl{loss or 0}",
                            source=source,
                            cap=cap,
                            parts=parts,
                            policy=policy,
                        )
                    )
    write(OUT / "portfolio_protocol.json", portfolio_specs)
    rows = []
    for spec in portfolio_specs:
        for window in ["validation", "holdout", "full"]:
            start, end = spans[window]
            grouped = defaultdict(list)
            for signal in signals[spec["source"]["signal_id"]]:
                if start <= signal["at"] < end:
                    grouped[signal["at"]].append(signal)
            for group in grouped.values():
                group.sort(key=lambda s: (-s["probability"], s["symbol"]))
            for cost, fee, slip in COSTS[:2]:
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
                    ),
                    research_policy=spec["policy"],
                )
                active, notions = set(), defaultdict(float)
                for j in r["journal"]:
                    if j["kind"] == "entry":
                        assert j["symbol"] not in active
                        active.add(j["symbol"])
                        assert len(active) <= spec["cap"]
                    if j["kind"] in ["entry", "entry_add"]:
                        notions[j["event_id"]] += j["qty"] * j["price"]
                    if "net" in j:
                        active.remove(j["symbol"])
                assert max(notions.values(), default=0) <= 25 + 1e-8
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
                row = summarize(
                    r, spec["id"], spec["id"], spec["policy"], spec["cap"], cost, window
                )
                row.update(id=f"{window}_{cost}_{spec['id']}", strategy_id=spec["id"])
                if window == "full":
                    row["monthly"] = monthly_metrics(r["curve"])
                    row["target_met"] = (
                        r["ending_equity"] is not None
                        and row["monthly"]["all_months_50pct"]
                    )
                write(
                    OUT / "runs" / f"{row['id']}.json",
                    {k: v for k, v in r.items() if k != "curve"},
                )
                pd.DataFrame(r["curve"]).to_parquet(
                    OUT / "runs" / f"{row['id']}_equity.parquet", index=False
                )
                rows.append(row)
        print("Portfolio", spec["id"], flush=True)
    assert sha(ROOT / "configs/live.yaml") == protocol["live_config_sha256"]
    write(
        OUT / "summary.json",
        dict(
            protocol=protocol,
            development=development,
            validation=validation,
            holdout=holdout,
            candidates=candidates,
            portfolio_specs=portfolio_specs,
            results=rows,
            target_met_rows=sum(r.get("target_met", False) for r in rows),
            live_config_unchanged=True,
        ),
    )
    pd.DataFrame(rows).to_csv(OUT / "portfolio_comparison.csv", index=False)
    write(
        OUT / "goal_progress.json",
        dict(
            status="active",
            achieved=False,
            progress_classification="progress",
            next="Verify screening and portfolios, inspect historical data coverage, continue causal research beyond already inspected dates. Unanswered sizing preference is optional, not a blocker; preserve current allocation until clarified.",
        ),
    )
    print(
        "COMPLETE",
        len(development),
        "screens,",
        len(rows),
        "portfolio runs; target",
        sum(r.get("target_met", False) for r in rows),
        flush=True,
    )


if __name__ == "__main__":
    main()
