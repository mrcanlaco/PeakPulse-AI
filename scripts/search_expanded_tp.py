"""Expanded offline search with explicit TP opt-in and locked later-period checks."""

from __future__ import annotations

import hashlib
import itertools
import json
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from account_backtest_replay import simulate
from backtest_without_ake import cached_inputs
from compare_account_risk import ROOT, exchange_rules, sha, summarize, write
from search_account_strategies import CASES, add_lows, aggregate, filter_signals

from dao_vang.config.settings import ExecutionConfig

OUT = ROOT / "artifacts/account_expanded_tp_20260924"
WINDOWS = dict(
    development=("2026-06-24", "2026-07-29"),
    validation=("2026-07-29", "2026-09-08"),
    full=("2026-06-24", "2026-09-24"),
    v1=("2026-07-29", "2026-08-12"),
    v2=("2026-08-12", "2026-08-26"),
    v3=("2026-08-26", "2026-09-08"),
)


def variants(capacity):
    targets = [
        (f"fixed{x:g}", {"fixed_tp_usdt": x}, {}, f"TP {x:g}$")
        for x in [0.5, 1, 2, 3, 5, 8, 10, 15]
    ]
    targets += [
        (
            f"atr{m}_cap{c}",
            {},
            dict(atr_multiplier=m, tp_max_usdt=c),
            f"TP {m} ATR, trần {c}$",
        )
        for m, c in [(2, 5), (2, 10), (4, 10)]
    ]
    exits = [
        ("nostop", {}, "không SL, không hạn giữ"),
        ("hold168", dict(max_hold_hours=168), "không SL, giữ ≤168h"),
        ("sl2_5", dict(loss_usdt=2.5), "SL 2,5$"),
        ("sl5", dict(loss_usdt=5), "SL 5$"),
        ("sl10", dict(loss_usdt=10), "SL 10$"),
        (
            "sl5_h72_dd10",
            dict(loss_usdt=5, max_hold_hours=72, flatten_drawdown=0.10),
            "SL 5$, ≤72h, đóng danh mục DD10%",
        ),
    ]
    result = []
    for (tp, target, settings, tp_label), (
        risk,
        policy,
        risk_label,
    ), cap, entry in itertools.product(
        targets, exits, [1, 3, 5, 10, capacity], ["original", "down_bar"]
    ):
        result.append(
            dict(
                id=f"{tp}_{risk}_n{cap}_{entry}",
                tp=tp,
                risk=risk,
                cap=cap,
                entry=entry,
                policy=dict(policy, **target, research_tp_limit=15),
                settings=settings,
                label=f"{tp_label} · {risk_label} · {'không giới hạn số vị thế' if cap == capacity else str(cap) + ' vị thế'} · {'tín hiệu gốc' if entry == 'original' else 'nến giảm'}",
                control=False,
                anchor=risk == "nostop"
                and cap in [1, 5, capacity]
                and entry == "original",
            )
        )
    return result


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "runs").mkdir(exist_ok=True)
    source = ROOT / "artifacts/account_backtest_20260924_3m/warehouse"
    cache = ROOT / "artifacts/account_risk_comparison_20260924"
    rule_path = ROOT / "artifacts/annual_execution_20260918/exchange_info_current.json"
    signals = json.loads((source / "signals.json").read_text(encoding="utf-8"))
    capacity = len({s["symbol"] for s in signals}) + 1
    definitions = variants(capacity)
    assert len(definitions) == 660 and len({s["id"] for s in definitions}) == 660
    protocol = dict(
        created_at=pd.Timestamp.now(tz="UTC").isoformat(),
        variants=definitions,
        cases=CASES,
        windows=WINDOWS,
        coins=["all_coins", "no_ake"],
        unlimited_cap=capacity,
        selected_per_scenario=10,
        selection="Development only: all 4 runs complete, worst DD<20%, >=10 closed trades in each. Rank worst PnL, then lower DD, then shorter observed holding duration. Retain up to 10 different decision fingerprints per coin scenario. Lock before validation. Always audit all 33 original-entry/no-stop TP x capacity (1,5,unlimited) anchors, regardless of poor development results.",
        gate="All 4 validation and full cases complete, PnL>0, DD<20%; >=20 closed trades in every validation case. Not live eligibility, not an untouched OOS test, no multiplicity-adjusted confidence.",
        fixed="500 USDT Cross x5, ~25 USDT notional, one coin one position, no DCA, no scaling order size, original 20% entry pause except explicit 10% portfolio close policy. Unlimited count still requires available margin; only finite observed universe.",
        exclusion="no_ake excludes all 7 known AKE signals retrospectively; not simulated manual intervention or an implementable anomaly filter. Exclusions applied before replay; other coins can use freed slots.",
        limitations="Previously inspected history; trained through July 28/frozen Sep6; signals only through Sep7, later manage inventory. MMR1% proxy, current filters, missing PIT delisted universe. bar_low is possible TP touch, not proven fill. Risk exits sampled every 5m, slippage/gaps can exceed intended loss. No manual intervention modeled.",
        input_sha256=sha(source / "signals.json"),
        rules_sha256=sha(rule_path),
        engine_sha256=sha(Path(__file__).with_name("account_backtest_replay.py")),
        runner_sha256=sha(Path(__file__)),
        loader_sha256=sha(Path(__file__).with_name("backtest_without_ake.py")),
        live_config_sha256=sha(ROOT / "configs/live.yaml"),
    )
    write(OUT / "protocol.json", protocol)
    rules = exchange_rules(rule_path)
    prices, funding, proof = cached_inputs(source, cache, signals, rules)
    add_lows(prices, proof, source)
    write(OUT / "data_evidence.json", proof)
    selected, audit = {}, {}
    for coin in protocol["coins"]:
        ss = [s for s in signals if coin == "all_coins" or s["symbol"] != "AKEUSDT"]
        for entry in ["original", "down_bar"]:
            selected[coin, entry], reasons = filter_signals(ss, prices, funding, entry)
            audit[f"{coin}_{entry}"] = dict(
                remaining=len(selected[coin, entry]), reasons=reasons
            )
    write(OUT / "filter_audit.json", audit)
    times, groups = {}, {}
    for period, span in WINDOWS.items():
        start, end = [int(pd.Timestamp(s, tz="UTC").timestamp() * 1000) for s in span]
        times[period] = list(range(start, end + 1, 300000))
        for key, values in selected.items():
            grouped = defaultdict(list)
            for s in values:
                if start <= s["at"] < end:
                    grouped[s["at"]].append(s)
            for batch in grouped.values():
                batch.sort(key=lambda s: (-s["probability"], s["symbol"]))
            groups[*key, period] = grouped
    results = []
    checks = 0

    def run(spec, coin, period, fill, cost, fee, slip, persist=False):
        nonlocal checks
        settings = ExecutionConfig(fee_rate=fee, max_slippage_bps=slip).model_dump()
        settings.update(max_open_positions=spec["cap"], **spec["settings"])
        policy = dict(spec["policy"], tp_fill=fill)
        result = simulate(
            times[period],
            groups[coin, spec["entry"], period],
            lambda s: prices.get(s, {}),
            rules,
            lambda s: funding[s],
            SimpleNamespace(**settings),
            research_policy=policy,
        )
        active, peak = set(), 0
        for j in result["journal"]:
            if coin == "no_ake":
                assert j.get("symbol") != "AKEUSDT"
            if j["kind"] == "entry":
                assert j["symbol"] not in active
                active.add(j["symbol"])
                peak = max(peak, len(active))
            elif "net" in j:
                assert j["symbol"] in active
                active.remove(j["symbol"])
        assert peak <= spec["cap"] and len(active) == len(result["open_positions"])
        if result["ending_equity"] is not None:
            expected = (
                500
                + result["closed_trade_net"]
                + sum(
                    p["unrealized"] - p["entry_fee"] + p["funding"]
                    for p in result["open_positions"]
                )
            )
            assert abs(result["ending_equity"] - expected) < 1e-7
        row = summarize(
            result, spec["id"], spec["label"], policy, spec["cap"], cost, period
        )
        row.update(
            id=f"{coin}_{period}_{fill}_{cost}_{spec['id']}",
            strategy_id=spec["id"],
            coins=coin,
            fill=fill,
            peak_positions=peak,
            signal_count=sum(map(len, groups[coin, spec["entry"], period].values())),
            decision_fingerprint=hashlib.sha256(
                json.dumps(
                    [j for j in result["journal"] if j["kind"] != "funding"],
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
        )
        if persist:
            write(
                OUT / "runs" / f"{row['id']}.json",
                {k: v for k, v in result.items() if k != "curve"},
            )
            pd.DataFrame(result["curve"]).to_parquet(
                OUT / "runs" / f"{row['id']}_equity.parquet", index=False
            )
        checks += 1
        return row

    shortlists, development = {}, {}
    for coin in protocol["coins"]:
        rows = []
        for n, spec in enumerate(definitions, 1):
            rows.extend(run(spec, coin, "development", *case) for case in CASES)
            if n % 30 == 0:
                print(f"Development {coin}: {n}/660 ({checks} runs)", flush=True)
        development[coin] = aggregate(rows, definitions)
        eligible = [
            r
            for r in development[coin]
            if r["complete"] and r["worst_dd"] < 0.20 and r["min_closed"] >= 10
        ]
        eligible.sort(
            key=lambda r: (
                -r["worst_pnl"],
                r["worst_dd"],
                r["max_hold_days"],
                r["strategy_id"],
            )
        )
        shortlists[coin], seen = [], set()
        for r in eligible:
            fp = tuple(r["fingerprints"])
            if fp not in seen:
                shortlists[coin].append(r["strategy_id"])
                seen.add(fp)
            if len(shortlists[coin]) == protocol["selected_per_scenario"]:
                break
        results.extend(rows)
        write(OUT / f"development_{coin}.json", development[coin])
        write(OUT / f"development_runs_{coin}.json", rows)
    lock = dict(
        locked_at=pd.Timestamp.now(tz="UTC").isoformat(),
        selected=shortlists,
        development_only=True,
        protocol_sha256=sha(OUT / "protocol.json"),
    )
    write(OUT / "shortlist_lock.json", lock)
    print("LOCKED", shortlists, flush=True)
    finalists = []
    for coin in protocol["coins"]:
        chosen = [s for s in definitions if s["id"] in shortlists[coin] or s["anchor"]]
        rows = []
        for n, spec in enumerate(chosen, 1):
            for period in ["validation", "full", "v1", "v2", "v3"]:
                for case in CASES:
                    if (
                        period.startswith("v")
                        and period != "validation"
                        and case[1] != "base"
                    ):
                        continue
                    rows.append(
                        run(
                            spec,
                            coin,
                            period,
                            *case,
                            persist=period in ["full", "validation"],
                        )
                    )
            print(f"Validation {coin}: {n}/{len(chosen)} {spec['id']}", flush=True)
        val = aggregate([r for r in rows if r["window"] == "validation"], chosen)
        full = aggregate([r for r in rows if r["window"] == "full"], chosen)
        for v in val:
            f = next(r for r in full if r["strategy_id"] == v["strategy_id"])
            passed = (
                all(
                    r["complete"] and r["worst_pnl"] > 0 and r["worst_dd"] < 0.20
                    for r in [v, f]
                )
                and v["min_closed"] >= 20
            )
            finalists.append(
                dict(
                    coins=coin,
                    strategy_id=v["strategy_id"],
                    spec=v["spec"],
                    validation=v,
                    full=f,
                    shortlisted=v["strategy_id"] in shortlists[coin],
                    diagnostic_passed=passed,
                    promotion_eligible=False,
                )
            )
        results.extend(rows)
    assert sha(ROOT / "configs/live.yaml") == protocol["live_config_sha256"]
    write(
        OUT / "summary.json",
        dict(
            protocol=protocol,
            shortlists=shortlists,
            finalists=finalists,
            results=results,
            runs=checks,
            diagnostic_pass_count=sum(f["diagnostic_passed"] for f in finalists),
            live_config_unchanged=True,
            status="EXPLORATORY_NOT_LIVE_ELIGIBLE",
        ),
    )
    pd.DataFrame(results).to_csv(OUT / "comparison.csv", index=False)
    print(
        "COMPLETE",
        checks,
        "runs; diagnostic passes",
        sum(f["diagnostic_passed"] for f in finalists),
        flush=True,
    )


if __name__ == "__main__":
    main()
