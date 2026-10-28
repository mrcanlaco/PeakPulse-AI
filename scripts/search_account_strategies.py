"""Staged, predeclared account strategy search on cached market data only."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pandas as pd
from account_backtest_replay import simulate
from backtest_without_ake import cached_inputs
from compare_account_risk import ROOT, exchange_rules, sha, summarize, write

from dao_vang.config.settings import ExecutionConfig

CASES = [
    ("close", "base", 0.0005, 20),
    ("close", "stress", 0.001, 50),
    ("bar_low", "base", 0.0005, 20),
    ("bar_low", "stress", 0.001, 50),
]


def variants():
    result = []
    for tp, loss, hours, cap, entry in itertools.product(
        ["fixed0_5", "fixed1", "fixed2", "atr2"],
        [2.5, 5],
        [24, 72],
        [1, 3, 5],
        ["original", "down_bar", "down_bar_nonnegative_funding"],
    ):
        policy = dict(loss_usdt=loss, max_hold_hours=hours, flatten_drawdown=0.10)
        if tp != "atr2":
            policy["fixed_tp_usdt"] = {"fixed0_5": 0.5, "fixed1": 1, "fixed2": 2}[tp]
        result.append(
            dict(
                id=f"{tp}_sl{str(loss).replace('.', '_')}_h{hours}_n{cap}_{entry}",
                tp=tp,
                loss=loss,
                hours=hours,
                cap=cap,
                entry=entry,
                policy=policy,
                control=False,
            )
        )
    for cap in [1, 5]:
        for loss in [None, 2.5]:
            result.append(
                dict(
                    id=f"control_n{cap}_{'nostop' if loss is None else 'sl2_5'}",
                    tp="atr2",
                    loss=loss,
                    hours=None,
                    cap=cap,
                    entry="original",
                    policy={} if loss is None else dict(loss_usdt=loss),
                    control=True,
                )
            )
    return result


def filter_signals(signals, prices, funding, mode):
    selected, reasons = [], Counter()
    for signal in signals:
        at, symbol = signal["at"], signal["symbol"]
        if mode != "original":
            quotes = prices.get(symbol, {})
            now = quotes.get(at, {}).get("execution_close", math.nan)
            before = quotes.get(at - 300000, {}).get("execution_close", math.nan)
            if not all(math.isfinite(x) and x > 0 for x in [now, before]):
                reasons["confirmation_price_missing"] += 1
                continue
            if now >= before:
                reasons["last_closed_bar_not_down"] += 1
                continue
        if mode == "down_bar_nonnegative_funding":
            history = funding.get(symbol, [])
            idx = bisect_right([r[0] for r in history], at - 60000) - 1
            if idx < 0 or at - history[idx][0] > (8 * 60 + 5) * 60000:
                reasons["last_known_funding_missing_or_stale"] += 1
                continue
            if history[idx][1] < 0:
                reasons["last_known_funding_negative"] += 1
                continue
        selected.append(signal)
    return selected, dict(reasons)


def add_lows(prices, proof, source):
    db = duckdb.connect(str(source / "working.duckdb"), read_only=True)
    for symbol, points in prices.items():
        for at, low in db.execute(
            "SELECT epoch_ms(close_time)+1,low FROM prices WHERE symbol=?", [symbol]
        ).fetchall():
            points.setdefault(at, {})["execution_low"] = float(low)
        extra = proof[symbol]["trade_prices"]
        if "path" in extra:
            for r in json.loads(Path(extra["path"]).read_text(encoding="utf-8"))[
                "rows"
            ]:
                points.setdefault(int(r[6]) + 1, {}).setdefault(
                    "execution_low", float(r[3])
                )
    db.close()


def aggregate(rows, definitions):
    results = []
    for spec in definitions:
        matches = [r for r in rows if r["strategy_id"] == spec["id"]]
        if not matches:
            continue
        complete = len(matches) == 4 and all(r["pnl"] is not None for r in matches)
        results.append(
            dict(
                strategy_id=spec["id"],
                spec=spec,
                complete=complete,
                worst_pnl=min(r["pnl"] for r in matches) if complete else None,
                best_pnl=max(r["pnl"] for r in matches) if complete else None,
                worst_dd=max(r["max_drawdown"] for r in matches),
                min_closed=min(r["exits"] for r in matches),
                min_entries=min(r["entries"] for r in matches),
                max_hold_days=max(r["max_hold_days"] for r in matches),
                min_case=matches[0]["id"] if len(matches) == 1 else None,
                fingerprints=[r["decision_fingerprint"] for r in matches],
            )
        )
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/account_strategy_search_20260924",
    )
    parser.add_argument("--exclude-symbol", action="append", default=[])
    parser.add_argument("--shortlist-from", type=Path)
    args = parser.parse_args()
    if (
        args.exclude_symbol or args.shortlist_from
    ) and args.output.resolve() == parser.get_default("output").resolve():
        parser.error(
            "Exclusions or a fixed shortlist require a separate --output directory"
        )
    out = args.output
    out.mkdir(exist_ok=True)
    (out / "runs").mkdir(exist_ok=True)
    source = ROOT / "artifacts/account_backtest_20260924_3m/warehouse"
    cache = ROOT / "artifacts/account_risk_comparison_20260924"
    signals = json.loads((source / "signals.json").read_text(encoding="utf-8"))
    exclusions = sorted(set(s.upper() for s in args.exclude_symbol))
    removed = [s for s in signals if s["symbol"] in exclusions]
    signals = [s for s in signals if s["symbol"] not in exclusions]
    definitions = variants()
    assert len(definitions) == 148 and len({v["id"] for v in definitions}) == 148
    rule_path = ROOT / "artifacts/annual_execution_20260918/exchange_info_current.json"
    protocol = dict(
        created_at=pd.Timestamp.now(tz="UTC").isoformat(),
        variants=definitions,
        cases=CASES,
        development=["2026-06-24T00:00:00Z", "2026-07-29T00:00:00Z"],
        validation=["2026-07-29T00:00:00Z", "2026-09-08T00:00:00Z"],
        full=["2026-06-24T00:00:00Z", "2026-09-24T00:00:00Z"],
        shortlist_size=8,
        ranking="On development only: require 4 completed cost/fill cases, max DD <20%, at least 10 closed trades in each; rank by worst-case net PnL, then lower DD, then shorter max hold. Keep up to 8 distinct decision fingerprints. If fewer meet gate, report that without relaxing it.",
        diagnostic_pass="Shortlisted candidate has positive PnL in all 4 validation cases, DD <20%, >=20 closed trades per validation case, and positive PnL/DD<20% in all 4 continuous full-period cases. This is NOT live eligibility or proof of statistical edge.",
        fixed_policy="500 USDT Cross x5, ~25 USDT notional, no DCA, one coin one position. New combinations flatten and latch at 10% account drawdown; controls preserve original pause-only 20%.",
        no_symbol_exclusions=not exclusions,
        excluded_symbols=exclusions,
        excluded_signal_count=len(removed),
        exclusion_caveat="Retrospective symbol exclusion, NOT simulated manual intervention. Removed trades have no PnL or capital commitment; all remaining signals are replayed chronologically with freed slots.",
        fixed_shortlist_source=str(args.shortlist_from)
        if args.shortlist_from
        else None,
        fixed_shortlist_sha256=sha(args.shortlist_from)
        if args.shortlist_from
        else None,
        signal_events=len(signals),
        funding_filter="Last settled funding known at least 60s before entry, no older than 8h5m, rate >=0; does not predict next settlement.",
        confirmation="Last completed 5m trade close < previous completed close, evaluated at original signal time; no future price or next-open use.",
        fill_caveat="bar_low is a sensitivity, not a proven fill: unknown intrabar order, TP placement latency, queue/partial fills and funding timing. Risk exits retain priority at sampled Mark close, even if TP was touched intrabar.",
        no_untouched_holdout="This history was already inspected in prior turns. Model trained through July 28, frozen Sep 6. Calendar splits do not create a truly untouched OOS sample, and there is no multiple-testing-adjusted confidence claim.",
        input_sha256=sha(source / "signals.json"),
        rules_sha256=sha(rule_path),
        engine_sha256=sha(Path(__file__).with_name("account_backtest_replay.py")),
        runner_sha256=sha(Path(__file__)),
        loader_sha256=sha(Path(__file__).with_name("backtest_without_ake.py")),
        live_config_sha256=sha(ROOT / "configs/live.yaml"),
        limitations=json.loads((source / "report.json").read_text(encoding="utf-8"))[
            "limitations"
        ],
    )
    write(out / "protocol.json", protocol)
    write(out / "excluded_signals.json", removed)
    prices, funding, proof = cached_inputs(
        source, cache, signals, exchange_rules(rule_path)
    )
    rules = exchange_rules(rule_path)
    add_lows(prices, proof, source)
    write(out / "data_evidence.json", proof)
    selected = {}
    filter_audit = {}
    for mode in ["original", "down_bar", "down_bar_nonnegative_funding"]:
        selected[mode], filter_audit[mode] = filter_signals(
            signals, prices, funding, mode
        )
        filter_audit[mode]["remaining_signals"] = len(selected[mode])
    write(out / "entry_filter_audit.json", filter_audit)
    rows = []
    validation_checks = 0

    def run(
        spec, period, span, fill, cost, fee, slip, persist=False, override_policy=None
    ):
        nonlocal validation_checks
        start, end = [int(pd.Timestamp(t).timestamp() * 1000) for t in span]
        times = list(range(start, end + 1, 300000))
        grouped = defaultdict(list)
        for s in selected[spec["entry"]]:
            if start <= s["at"] < end:
                grouped[s["at"]].append(s)
        for values in grouped.values():
            values.sort(key=lambda x: (-x["probability"], x["symbol"]))
        cfg = SimpleNamespace(
            **ExecutionConfig(
                max_open_positions=spec["cap"], fee_rate=fee, max_slippage_bps=slip
            ).model_dump()
        )
        policy = dict(
            spec["policy"] if override_policy is None else override_policy, tp_fill=fill
        )
        result = simulate(
            times,
            grouped,
            lambda s: prices.get(s, {}),
            rules,
            lambda s: funding[s],
            cfg,
            research_policy=policy,
        )
        active = set()
        max_slots = 0
        for j in result["journal"]:
            if j["kind"] == "entry":
                assert j["symbol"] not in active
                active.add(j["symbol"])
                max_slots = max(max_slots, len(active))
            elif "net" in j:
                assert j["symbol"] in active
                active.remove(j["symbol"])
        assert max_slots <= spec["cap"] and len(active) == len(result["open_positions"])
        if result["ending_equity"] is not None:
            expected = (
                500
                + result["closed_trade_net"]
                + sum(
                    p["unrealized"] - p["entry_fee"] + p["funding"]
                    for p in result["open_positions"]
                )
            )
            assert abs(expected - result["ending_equity"]) < 1e-7
        validation_checks += 1
        row = summarize(
            result, spec["id"], spec["id"], policy, spec["cap"], cost, period
        )
        row.update(
            id=f"{period}_{fill}_{cost}_{spec['id']}",
            strategy_id=spec["id"],
            fill=fill,
            peak_positions=max_slots,
            signal_count=sum(map(len, grouped.values())),
            decision_fingerprint=hashlib.sha256(
                json.dumps(
                    [j for j in result["journal"] if j["kind"] != "funding"],
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
        )
        if persist:
            write(
                out / "runs" / f"{row['id']}.json",
                {k: v for k, v in result.items() if k != "curve"},
            )
            pd.DataFrame(result["curve"]).to_parquet(
                out / "runs" / f"{row['id']}_equity.parquet", index=False
            )
        return row

    for index, spec in enumerate([] if args.shortlist_from else definitions):
        for fill, cost, fee, slip in CASES:
            rows.append(
                run(spec, "development", protocol["development"], fill, cost, fee, slip)
            )
        if index % 8 == 0 or index == len(definitions) - 1:
            print(f"Development {index + 1}/{len(definitions)}", flush=True)
    dev = aggregate(rows, definitions)
    eligible = [
        r
        for r in dev
        if r["complete"]
        and r["worst_dd"] < 0.2
        and r["min_closed"] >= 10
        and not r["spec"]["control"]
    ]
    eligible.sort(
        key=lambda r: (
            -r["worst_pnl"],
            r["worst_dd"],
            r["max_hold_days"],
            r["strategy_id"],
        )
    )
    shortlisted = []
    seen = set()
    for row in eligible:
        fingerprint = tuple(row["fingerprints"])
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        shortlisted.append(row)
        if len(shortlisted) == protocol["shortlist_size"]:
            break
    # This file is committed to disk before any later-period simulation.
    lock = dict(
        locked_at=pd.Timestamp.now(tz="UTC").isoformat(),
        development_ranked=eligible,
        selected=[r["strategy_id"] for r in shortlisted],
        development_only=True,
    )
    if args.shortlist_from:
        previous = json.loads(args.shortlist_from.read_text(encoding="utf-8"))
        ids = previous["selected"]
        by_id = {s["id"]: s for s in definitions}
        if any(i not in by_id or by_id[i]["control"] for i in ids):
            raise ValueError("Invalid fixed shortlist")
        shortlisted = [dict(strategy_id=i, spec=by_id[i]) for i in ids]
        lock.update(
            selected=ids,
            development_only=False,
            selection="Reuse prior shortlist unchanged; no retuning after excluding symbols",
            source=str(args.shortlist_from),
            source_sha256=sha(args.shortlist_from),
        )
    write(out / "shortlist_lock.json", lock)
    write(out / "development_summary.json", dev)
    write(out / "development_runs.json", rows)
    print("LOCKED SHORTLIST", lock["selected"], flush=True)
    checks = [r["spec"] for r in shortlisted] + [s for s in definitions if s["control"]]
    slices = [
        ("v1", ["2026-07-29T00:00:00Z", "2026-08-12T00:00:00Z"]),
        ("v2", ["2026-08-12T00:00:00Z", "2026-08-26T00:00:00Z"]),
        ("v3", ["2026-08-26T00:00:00Z", "2026-09-08T00:00:00Z"]),
    ]
    for index, spec in enumerate(checks):
        for period, span in [
            ("validation", protocol["validation"]),
            ("full", protocol["full"]),
            *slices,
        ]:
            for fill, cost, fee, slip in CASES:
                if period in ["v1", "v2", "v3"] and cost != "base":
                    continue
                rows.append(
                    run(
                        spec,
                        period,
                        span,
                        fill,
                        cost,
                        fee,
                        slip,
                        persist=period in ["full", "validation"],
                    )
                )
        print(f"Validation {index + 1}/{len(checks)}: {spec['id']}", flush=True)
    val = aggregate([r for r in rows if r["window"] == "validation"], checks)
    full = aggregate([r for r in rows if r["window"] == "full"], checks)
    finalists = []
    for v in val:
        f = next(x for x in full if x["strategy_id"] == v["strategy_id"])
        passed = (
            not v["spec"]["control"]
            and v["complete"]
            and f["complete"]
            and v["worst_pnl"] > 0
            and f["worst_pnl"] > 0
            and v["worst_dd"] < 0.2
            and f["worst_dd"] < 0.2
            and v["min_closed"] >= 20
        )
        finalists.append(
            dict(
                strategy_id=v["strategy_id"],
                spec=v["spec"],
                validation=v,
                full=f,
                exploratory_gate_passed=passed,
                promotion_eligible=False,
            )
        )
    finalists.sort(
        key=lambda x: (
            not x["exploratory_gate_passed"],
            not x["validation"]["complete"],
            -(
                x["validation"]["worst_pnl"]
                if x["validation"]["worst_pnl"] is not None
                else -1e9
            ),
        )
    )
    assert sha(ROOT / "configs/live.yaml") == protocol["live_config_sha256"]
    write(
        out / "summary.json",
        dict(
            status="EXPLORATORY_NOT_LIVE_ELIGIBLE",
            protocol=protocol,
            entry_filter_audit=filter_audit,
            shortlist=lock["selected"],
            finalists=finalists,
            results=rows,
            diagnostic_pass_count=sum(x["exploratory_gate_passed"] for x in finalists),
            validation_checks=validation_checks,
            live_config_unchanged=True,
        ),
    )
    pd.DataFrame(rows).to_csv(out / "comparison.csv", index=False)
    print(
        "COMPLETE",
        validation_checks,
        "runs; diagnostic pass",
        sum(x["exploratory_gate_passed"] for x in finalists),
        flush=True,
    )


if __name__ == "__main__":
    main()
