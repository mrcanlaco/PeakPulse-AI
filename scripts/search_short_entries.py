"""Entry timing research with fixed exits, staged budget and locked selection."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from types import SimpleNamespace

import pandas as pd
from account_scaled_replay import simulate
from backtest_without_ake import cached_inputs
from compare_account_risk import ROOT, exchange_rules, sha, summarize, write
from prepare_altcoin_search import OUT as DATA
from prepare_altcoin_search import RULE_PATH, SOURCE
from search_account_strategies import aggregate
from search_altcoin_families import FAMILY_NAMES, WINDOWS, daily_interval
from search_staged_trailing import CASES
from short_entry_timing import definitions, transform

from dao_vang.config.settings import ExecutionConfig

OUT = ROOT / "artifacts/short_entry_search_20260925"
PRIOR = ROOT / "artifacts/staged_trailing_20260925_25"


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "runs").mkdir(exist_ok=True)
    old = json.loads((PRIOR / "summary.json").read_text(encoding="utf-8"))
    sources = old["protocol"]["sources"]
    specs = []
    for source in sources:
        for timing in definitions():
            for exit_mode in ["fixed", "trailing"]:
                policy = dict(
                    source["policy"],
                    position_notional=25,
                    entry_parts=3,
                    entry_mode="favorable",
                    entry_step_atr=0.5,
                    add_expiry_hours=6,
                    require_split_eligibility=True,
                    trailing=exit_mode == "trailing",
                )
                if exit_mode == "trailing":
                    policy.update(activation_atr=3, callback_fraction=0.01)
                specs.append(
                    dict(
                        id=f"{source['family']}_{timing['id']}_{exit_mode}",
                        family=source["family"],
                        timing=timing,
                        exit=exit_mode,
                        policy=policy,
                        settings=source["settings"],
                        cap=source["cap"],
                        signal_id=source["signal"]["id"],
                        label=f"{FAMILY_NAMES[source['family']]} · {timing['label']} · {'TP cố định' if exit_mode == 'fixed' else 'Trailing 3 ATR / 1%'}",
                    )
                )
    protocol = dict(
        created_at=pd.Timestamp.now(tz="UTC").isoformat(),
        variants=specs,
        windows=WINDOWS,
        cases=CASES,
        total_notional=25,
        margin_budget=5,
        initial_equity=500,
        leverage=5,
        timing="13 entry rules: immediate; delay 15/60/180 minutes; rebound, continuation breakdown, rebound then rejection at 0.25/0.5/1 ATR. Anchor = completed contract close at source event; original ATR and score frozen. Rejection needs a prior completed bar to arm, then decline 0.25 ATR from running peak. Six-hour expiry; no intrabar high/low or next-open decisions. Trigger at completed close, replay fills next 5m open plus adverse slippage. Untriggered events are reported; no forced entries. At most one attempt per event.",
        capital="Virtual watches are not exchange orders and reserve no funds or slots. Replay enforces capacity, budgets and market minima when a watch triggers; failed capacity attempt is not retried. Each position still has 25 USDT maximum total across three parts, add at 0.5/1 ATR from first fill, expire adds after 6h. No change to real account.",
        controls="Within each signal family and exit, vary only first-entry timing. Preserve source SL/time limit/cap, add rules and two cost cases. Fixed TP uses source policy; trailing fixed at 3 ATR activation, 1% callback, observed every 5/15m. ATR/filter/score stay from source time even after waiting (up to six hours); do not claim refreshed signal validity. Baseline immediate fixed for all four families and weak-rank immediate trailing reproduce prior runs.",
        selection="Development Jun24-Jul24: up to two non-immediate candidates per family/exit, all four cases complete, DD<20%, >=20 closes; rank worst-case PnL and deduplicate decision fingerprints. Lock before validation. Choose primary by worst validation PnL only among same eligibility criteria, then lock before final period. Never select using final/full results. Dates and signal sources previously inspected, so exploratory rather than untouched OOS.",
        gate="All four cases positive PnL/DD<20% in validation and final with >=20 closes each; full positive PnL/DD<20%. Daily seven-day block bootstrap reported separately, no multiplicity adjustment. No live promotion.",
        limitations=old["protocol"]["limitations"],
        live_config_sha256=sha(ROOT / "configs/live.yaml"),
        engine_sha256=sha(ROOT / "scripts/account_scaled_replay.py"),
        timing_sha256=sha(ROOT / "scripts/short_entry_timing.py"),
        runner_sha256=sha(ROOT / "scripts/search_short_entries.py"),
        signal_sha256=sha(DATA / "signals.json"),
    )
    write(OUT / "protocol.json", protocol)
    signals = json.loads((DATA / "signals.json").read_text(encoding="utf-8"))
    universe = json.loads((DATA / "summary.json").read_text(encoding="utf-8"))[
        "protocol"
    ]["universe"]["symbols"]
    rules = exchange_rules(RULE_PATH)
    prices, funding, proofs = cached_inputs(
        SOURCE, DATA / "cache", [dict(symbol=s) for s in universe], rules
    )
    write(OUT / "input_evidence.json", proofs)
    groups, audits, times = {}, {}, {}
    for window, span in WINDOWS.items():
        start, end = [int(pd.Timestamp(t, tz="UTC").timestamp() * 1000) for t in span]
        times[window] = list(range(start, end + 1, 300000))
        for source in sources:
            for timing in definitions():
                key = (window, source["signal"]["id"], timing["id"])
                transformed, audit = transform(
                    signals[source["signal"]["id"]], prices, start, end, timing
                )
                groups[key] = defaultdict(list)
                for signal in transformed:
                    groups[key][signal["at"]].append(signal)
                for group in groups[key].values():
                    group.sort(key=lambda r: (-r["probability"], r["symbol"]))
                audits[key] = audit
    write(OUT / "entry_watches.json", {"|".join(k): v for k, v in audits.items()})
    regressions, results = [], []

    def run(spec, window, case, persist=False):
        obs, cost, fee, slip = case
        config = ExecutionConfig(
            max_open_positions=spec["cap"], fee_rate=fee, max_slippage_bps=slip
        ).model_dump()
        config.update(spec["settings"])
        key = (window, spec["signal_id"], spec["timing"]["id"])
        r = simulate(
            times[window],
            groups[key],
            lambda coin: prices.get(coin, {}),
            rules,
            lambda coin: funding[coin],
            SimpleNamespace(**config),
            research_policy=dict(spec["policy"], observation_minutes=obs),
        )
        audit = audits[key]
        if audit["counts"].get("missing_data"):
            r["ending_equity"] = r["pnl"] = None
            r["errors"].append("entry_watch_missing_data")
        notionals, active = defaultdict(float), {}
        for j in r["journal"]:
            if j["kind"] in ["entry", "entry_add"]:
                if j["kind"] == "entry":
                    assert j["symbol"] not in active
                    active[j["symbol"]] = j["event_id"]
                else:
                    assert active[j["symbol"]] == j["event_id"]
                notionals[j["event_id"]] += j["qty"] * j["price"]
                assert len(active) <= spec["cap"]
            elif "net" in j:
                assert active.pop(j["symbol"]) == j["event_id"]
        assert max(notionals.values(), default=0) <= 25 + 1e-8
        assert len(active) == len(r["open_positions"])
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
            r, spec["id"], spec["label"], spec["policy"], spec["cap"], cost, window
        )
        row.update(
            id=f"{window}_{obs}m_{cost}_{spec['id']}",
            strategy_id=spec["id"],
            observation_minutes=obs,
            adds=sum(j["kind"] == "entry_add" for j in r["journal"]),
            mean_deployed_notional=sum(notionals.values()) / len(notionals)
            if notionals
            else 0,
            watch_counts=audit["counts"],
            source_events=audit["source_events"],
            decision_fingerprint=hashlib.sha256(
                json.dumps(
                    [j for j in r["journal"] if j["kind"] != "funding"], sort_keys=True
                ).encode()
            ).hexdigest(),
        )
        if persist:
            write(
                OUT / "runs" / f"{row['id']}.json",
                {k: v for k, v in r.items() if k != "curve"},
            )
            pd.DataFrame(r["curve"]).to_parquet(
                OUT / "runs" / f"{row['id']}_equity.parquet", index=False
            )
            if window == "holdout" and r["ending_equity"] is not None:
                row["daily_bootstrap"] = daily_interval(r["curve"])
        if spec["timing"]["mode"] == "immediate" and "nostop" not in spec["id"]:
            previous_id = f"{spec['family']}_favor0_5_{'fixed' if spec['exit'] == 'fixed' else 'trail_a3_c1'}"
            prior = next(
                (
                    x
                    for x in old["results"]
                    if x["strategy_id"] == previous_id
                    and x["window"] == window
                    and x["cost"] == cost
                    and x["observation_minutes"] == obs
                ),
                None,
            )
            if prior:
                assert all(
                    row[k] == prior[k]
                    for k in [
                        "ending_equity",
                        "max_drawdown",
                        "entries",
                        "exits",
                        "fees",
                        "funding",
                    ]
                )
                regressions.append(row["id"])
        return row

    for i, spec in enumerate(specs, 1):
        results += [run(spec, "development", c) for c in CASES]
        if i % 13 == 0:
            print(f"Development {i}/{len(specs)}", flush=True)
    dev = aggregate(results, specs)
    write(OUT / "development_summary.json", dev)
    chosen = []
    for family in FAMILY_NAMES:
        for exit_mode in ["fixed", "trailing"]:
            pool = [
                r
                for r in dev
                if r["spec"]["family"] == family
                and r["spec"]["exit"] == exit_mode
                and r["spec"]["timing"]["mode"] != "immediate"
                and r["complete"]
                and r["worst_dd"] < 0.2
                and r["min_closed"] >= 20
            ]
            pool.sort(key=lambda r: (-r["worst_pnl"], r["worst_dd"], r["strategy_id"]))
            fingerprints = set()
            for row in pool:
                fingerprint = tuple(row["fingerprints"])
                if fingerprint not in fingerprints:
                    chosen.append(row["strategy_id"])
                    fingerprints.add(fingerprint)
                if len(fingerprints) == 2:
                    break
    checked = [
        s for s in specs if s["id"] in chosen or s["timing"]["mode"] == "immediate"
    ]
    write(
        OUT / "shortlist_lock.json",
        dict(selected=chosen, locked_at=pd.Timestamp.now(tz="UTC").isoformat()),
    )
    for spec in checked:
        results += [run(spec, "validation", c, True) for c in CASES]
    val = aggregate([r for r in results if r["window"] == "validation"], checked)
    pool = [
        r
        for r in val
        if r["strategy_id"] in chosen
        and r["complete"]
        and r["worst_dd"] < 0.2
        and r["min_closed"] >= 20
    ]
    primary = max(pool, key=lambda r: r["worst_pnl"])["strategy_id"] if pool else None
    write(
        OUT / "primary_lock.json",
        dict(
            primary=primary,
            locked_at=pd.Timestamp.now(tz="UTC").isoformat(),
            holdout_not_run=True,
        ),
    )
    print("PRIMARY", primary, flush=True)
    for spec in checked:
        for window in ["holdout", "full"]:
            results += [run(spec, window, c, True) for c in CASES]
    summaries = {
        w: {
            r["strategy_id"]: r
            for r in aggregate([r for r in results if r["window"] == w], checked)
        }
        for w in ["validation", "holdout", "full"]
    }
    finalists = []
    for spec in checked:
        windows = {w: summaries[w][spec["id"]] for w in summaries}
        passed = (
            all(
                r["complete"] and r["worst_pnl"] > 0 and r["worst_dd"] < 0.2
                for r in windows.values()
            )
            and min(windows[w]["min_closed"] for w in ["validation", "holdout"]) >= 20
        )
        finalists.append(
            dict(
                strategy_id=spec["id"],
                spec=spec,
                **windows,
                primary=spec["id"] == primary,
                shortlisted=spec["id"] in chosen,
                diagnostic_passed=passed,
            )
        )
    extra_specs, extra_rows = [], []
    if primary:
        winner = next(s for s in checked if s["id"] == primary)
        baseline = next(
            s
            for s in checked
            if s["family"] == winner["family"]
            and s["exit"] == winner["exit"]
            and s["timing"]["mode"] == "immediate"
        )
        for spec in [winner, baseline]:
            for cap in [1, 5]:
                p = {
                    k: v
                    for k, v in spec["policy"].items()
                    if k
                    not in [
                        "loss_usdt",
                        "max_hold_hours",
                        "stop_atr",
                        "flatten_drawdown",
                    ]
                }
                extra_specs.append(
                    dict(
                        spec,
                        id=spec["id"] + f"_nostop_n{cap}",
                        cap=cap,
                        policy=p,
                        label=spec["label"] + f" · Không SL/thời hạn · {cap} vị thế",
                    )
                )
        write(
            OUT / "no_stop_protocol.json",
            dict(
                specs=extra_specs,
                purpose="Paired post-selection sensitivity only; do not reselect primary.",
            ),
        )
        for spec in extra_specs:
            for window in ["validation", "holdout", "full"]:
                extra_rows += [run(spec, window, c, True) for c in CASES]
    assert sha(ROOT / "configs/live.yaml") == protocol["live_config_sha256"]
    write(
        OUT / "summary.json",
        dict(
            protocol=protocol,
            results=results,
            finalists=finalists,
            primary=primary,
            shortlist=chosen,
            runs=len(results),
            original_regressions=regressions,
            no_stop_specs=extra_specs,
            no_stop_results=extra_rows,
            diagnostic_pass_count=sum(f["diagnostic_passed"] for f in finalists),
            live_config_unchanged=True,
        ),
    )
    pd.DataFrame(results + extra_rows).to_csv(OUT / "comparison.csv", index=False)
    print(
        "COMPLETE",
        len(results),
        "+",
        len(extra_rows),
        "runs; passed",
        sum(f["diagnostic_passed"] for f in finalists),
        flush=True,
    )


if __name__ == "__main__":
    main()
