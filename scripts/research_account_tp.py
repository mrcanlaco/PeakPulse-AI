"""Predeclared TP sensitivity grid on cached data; no production policy changes."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import median
from types import SimpleNamespace

import duckdb
import pandas as pd
from account_backtest_replay import simulate
from backtest_without_ake import cached_inputs
from compare_account_risk import ROOT, exchange_rules, sha, summarize, write

from dao_vang.config.settings import ExecutionConfig

POLICIES = [
    ("atr2", "Gốc: 2 ATR, trần 5 USDT", {}, {}),
    ("atr1", "1 ATR, trần 5 USDT", {"atr_multiplier": 1.0}, {}),
    ("atr1_5", "1,5 ATR, trần 5 USDT", {"atr_multiplier": 1.5}, {}),
    ("atr3", "3 ATR, trần 5 USDT", {"atr_multiplier": 3.0}, {}),
    ("atr2_cap1", "2 ATR, trần 1 USDT", {"tp_max_usdt": 1.0}, {}),
    ("atr2_cap2", "2 ATR, trần 2 USDT", {"tp_max_usdt": 2.0}, {}),
    ("fixed0_5", "TP ròng cố định 0,5 USDT", {}, {"fixed_tp_usdt": 0.5}),
    ("fixed1", "TP ròng cố định 1 USDT", {}, {"fixed_tp_usdt": 1}),
    ("fixed2", "TP ròng cố định 2 USDT", {}, {"fixed_tp_usdt": 2}),
    ("fixed3", "TP ròng cố định 3 USDT", {}, {"fixed_tp_usdt": 3}),
    ("fixed5", "TP ròng cố định 5 USDT", {}, {"fixed_tp_usdt": 5}),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fill", choices=["close", "bar_low"], default="close")
    args = parser.parse_args()
    source = ROOT / "artifacts/account_backtest_20260924_3m/warehouse"
    cache = ROOT / "artifacts/account_risk_comparison_20260924"
    out = ROOT / (
        "artifacts/account_tp_research_20260924"
        + ("_touch" if args.fill == "bar_low" else "")
    )
    out.mkdir(exist_ok=True)
    (out / "runs").mkdir(exist_ok=True)
    signals = json.loads((source / "signals.json").read_text(encoding="utf-8"))
    rule_path = ROOT / "artifacts/annual_execution_20260918/exchange_info_current.json"
    rules = exchange_rules(rule_path)
    capacity = len({s["symbol"] for s in signals}) + 1
    windows = [
        ("full", "2026-06-24T00:00:00Z", "2026-09-24T00:00:00Z"),
        ("w1", "2026-06-24T00:00:00Z", "2026-07-24T00:00:00Z"),
        ("w2", "2026-07-24T00:00:00Z", "2026-08-24T00:00:00Z"),
        ("w3", "2026-08-24T00:00:00Z", "2026-09-08T00:00:00Z"),
    ]
    protocol = dict(
        fill_assumption=args.fill,
        touch_limitations="bar_low is a sensitivity only: uses previously resting TP before this bar's funding update; funding is charged through the bar end. Actual fill timing, funding ordering, queue and liquidation ordering remain unknown. It is not a proven executable return or a formal upper bound.",
        created_at=pd.Timestamp.now(tz="UTC").isoformat(),
        policies=POLICIES,
        caps=[5, capacity],
        windows=windows,
        coins=["all_coins", "no_ake"],
        costs={
            "base": dict(fee=0.0005, slip_bps=20),
            "stress": dict(fee=0.001, slip_bps=50),
        },
        source_signals_sha256=sha(source / "signals.json"),
        rules_sha256=sha(rule_path),
        engine_sha256=sha(Path(__file__).with_name("account_backtest_replay.py")),
        runner_sha256=sha(Path(__file__)),
        cache_loader_sha256=sha(Path(__file__).with_name("backtest_without_ake.py")),
        live_config_sha256=sha(ROOT / "configs/live.yaml"),
        fixed_rules="500 USDT, Cross x5, 25 USDT notional; no DCA, no SL, no time exit; one coin one position; pause new entries at 20% drawdown; keep open positions marked to market.",
        target_rules="Lock net cash target at entry; adjust TP price only for actual entry and settled funding/fees. ATR targets below 0.50 are rejected. Fixed targets can change eligibility versus ATR; same input signals, not identical trades.",
        selection_rules="Exploratory grid, all results retained; no automatic promotion. Separate time windows restart at 500 and are sensitivity tests, not valid OOS. Do not call maximum realized in-sample return an optimal deployable strategy.",
        limitations=json.loads((source / "report.json").read_text(encoding="utf-8"))[
            "limitations"
        ],
    )
    write(out / "protocol.json", protocol)
    prices, funding, proof = cached_inputs(source, cache, signals, rules)
    if args.fill == "bar_low":
        db = duckdb.connect(str(source / "working.duckdb"), read_only=True)
        for symbol, points in prices.items():
            for at, low in db.execute(
                "SELECT epoch_ms(close_time)+1,low FROM prices WHERE symbol=?", [symbol]
            ).fetchall():
                points.setdefault(at, {})["execution_low"] = float(low)
            supplement = proof[symbol]["trade_prices"]
            if "path" in supplement:
                for row in json.loads(
                    Path(supplement["path"]).read_text(encoding="utf-8")
                )["rows"]:
                    points.setdefault(int(row[6]) + 1, {}).setdefault(
                        "execution_low", float(row[3])
                    )
        db.close()
    write(out / "data_evidence.json", proof)
    previous = json.loads(
        (ROOT / "artifacts/account_uncapped_20260924/summary.json").read_text(
            encoding="utf-8"
        )
    )["results"]
    results, regressions = [], []
    for window, begin, end in windows:
        first, last = (
            int(pd.Timestamp(begin).timestamp() * 1000),
            int(pd.Timestamp(end).timestamp() * 1000),
        )
        times = list(range(first, last + 1, 300000))
        for coins in ("all_coins", "no_ake"):
            grouped = defaultdict(list)
            for s in signals:
                if first <= s["at"] < last and (
                    coins == "all_coins" or s["symbol"] != "AKEUSDT"
                ):
                    grouped[s["at"]].append(s)
            for rows in grouped.values():
                rows.sort(key=lambda x: (-x["probability"], x["symbol"]))
            for cap in [5, capacity]:
                for cost, costs in protocol["costs"].items():
                    if window != "full" and cost != "base":
                        continue
                    for pid, label, overrides, policy in POLICIES:
                        settings = ExecutionConfig(
                            fee_rate=costs["fee"], max_slippage_bps=costs["slip_bps"]
                        ).model_dump()
                        settings.update(max_open_positions=cap, **overrides)
                        result = simulate(
                            times,
                            grouped,
                            lambda s: prices.get(s, {}),
                            rules,
                            lambda s: funding[s],
                            SimpleNamespace(**settings),
                            research_policy=dict(policy, tp_fill=args.fill),
                        )
                        result.update(
                            method="historical_mark_prices_tp_sensitivity",
                            liquidation_status="unknown_historical_brackets_and_intrabar_path",
                        )
                        row = summarize(
                            result,
                            pid,
                            label,
                            dict(overrides=overrides, **policy),
                            cap,
                            cost,
                            window,
                        )
                        row["id"] = f"{window}_{coins}_{cap}_{cost}_{pid}"
                        closed = [j for j in result["journal"] if "net" in j]
                        active = set()
                        peak_slots = 0
                        for j in result["journal"]:
                            if j["kind"] == "entry":
                                assert j["symbol"] not in active
                                active.add(j["symbol"])
                                peak_slots = max(peak_slots, len(active))
                            elif "net" in j:
                                assert j["symbol"] in active
                                active.remove(j["symbol"])
                        assert peak_slots <= cap and len(active) == len(
                            result["open_positions"]
                        )
                        assert coins != "no_ake" or not any(
                            j.get("symbol") == "AKEUSDT" for j in result["journal"]
                        )
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
                        row.update(
                            coins=coins,
                            peak_concurrent_positions=peak_slots,
                            closed_trade_net=result["closed_trade_net"],
                            median_closed_hours=median(j["held_hours"] for j in closed)
                            if closed
                            else None,
                            open_over_7_days=sum(
                                p["held_days"] > 7 for p in result["open_positions"]
                            ),
                        )
                        if window == "full":
                            write(
                                out / "runs" / f"{row['id']}.json",
                                {k: v for k, v in result.items() if k != "curve"},
                            )
                            pd.DataFrame(result["curve"]).to_parquet(
                                out / "runs" / f"{row['id']}_equity.parquet",
                                index=False,
                            )
                        if window == "full" and pid == "atr2" and args.fill == "close":
                            old = next(
                                r
                                for r in previous
                                if r["exclude_ake"] == (coins == "no_ake")
                                and r["variant"]
                                == ("cap5" if cap == 5 else "uncapped_pause")
                                and r["cost"] == cost
                            )
                            assert (
                                row["entries"] == old["entries"]
                                and row["ending_equity"] == old["ending_equity"]
                                and row["stop_event"] == old["stop_event"]
                            )
                            regressions.append(row["id"])
                        results.append(row)
                        print(
                            f"{row['id']}: equity={row['ending_equity']} DD={row['max_drawdown']:.3f} entries={row['entries']} open={row['open_count']} errors={row['errors']}",
                            flush=True,
                        )
        write(
            out / "summary.json",
            dict(
                status="EXPLORATORY_NOT_LIVE_ELIGIBLE",
                protocol=protocol,
                results=results,
                baseline_regressions=regressions,
            ),
        )
        pd.DataFrame(results).to_csv(out / "comparison.csv", index=False)
    assert sha(ROOT / "configs/live.yaml") == protocol["live_config_sha256"]
    assert len(results) == 220 and len(regressions) == (
        8 if args.fill == "close" else 0
    )
    write(
        out / "validation.json",
        dict(
            run_count=len(results),
            baseline_matches=len(regressions),
            all_ledgers_reconciled=True,
            capacity_and_no_duplicate_coin_checks=True,
            live_config_unchanged=True,
        ),
    )


if __name__ == "__main__":
    main()
