"""Post-selection sensitivity: remove loss/time exits without reselecting winner."""

from __future__ import annotations

import json
from collections import defaultdict
from types import SimpleNamespace

import pandas as pd
from account_scaled_replay import simulate
from backtest_without_ake import cached_inputs
from compare_account_risk import ROOT, exchange_rules, sha, summarize, write
from prepare_altcoin_search import OUT as PREVIOUS
from prepare_altcoin_search import RULE_PATH, SOURCE
from search_altcoin_families import FAMILY_NAMES, WINDOWS, daily_interval
from search_staged_trailing import CASES

from dao_vang.config.settings import ExecutionConfig

OUT = ROOT / "artifacts/staged_trailing_20260925_25"


def main():
    s = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    chosen = []
    for family in FAMILY_NAMES:
        pool = [
            f
            for f in s["finalists"]
            if f["shortlisted"] and f["spec"]["family"] == family
        ]
        chosen.append(max(pool, key=lambda f: f["validation"]["worst_pnl"])["spec"])
    primary = next(f["spec"] for f in s["finalists"] if f["primary"])
    for entry, exit_mode in [("single", primary["exit"]), (primary["entry"], "fixed")]:
        chosen.append(
            next(
                f["spec"]
                for f in s["finalists"]
                if f["spec"]["family"] == primary["family"]
                and f["spec"]["entry"] == entry
                and f["spec"]["exit"] == exit_mode
            )
        )
    specs = []
    for spec in chosen:
        for cap in [1, 5]:
            policy = {
                k: v
                for k, v in spec["policy"].items()
                if k
                not in ["loss_usdt", "stop_atr", "max_hold_hours", "flatten_drawdown"]
            }
            specs.append(
                dict(spec, id=spec["id"] + f"_nostop_n{cap}", cap=cap, policy=policy)
            )
    write(
        OUT / "no_stop_protocol.json",
        dict(
            specs=specs,
            purpose="Post-selection sensitivity only. No loss or time exits; 20% persistent entry pause retained. Fixed TP controls retain target cap. Trailing has no fixed cap. Never select a replacement primary from these results.",
            engine_sha256=sha(ROOT / "scripts/account_scaled_replay.py"),
        ),
    )
    previous = json.loads((PREVIOUS / "summary.json").read_text(encoding="utf-8"))
    signals = json.loads((PREVIOUS / "signals.json").read_text(encoding="utf-8"))
    rules = exchange_rules(RULE_PATH)
    prices, funding, _ = cached_inputs(
        SOURCE,
        PREVIOUS / "cache",
        [dict(symbol=s) for s in previous["protocol"]["universe"]["symbols"]],
        rules,
    )
    rows = []
    for spec in specs:
        for period in ["validation", "holdout", "full"]:
            start, end = [
                int(pd.Timestamp(t, tz="UTC").timestamp() * 1000)
                for t in WINDOWS[period]
            ]
            groups = defaultdict(list)
            for signal in signals[spec["signal_id"]]:
                if start <= signal["at"] < end:
                    groups[signal["at"]].append(signal)
            for group in groups.values():
                group.sort(key=lambda r: (-r["probability"], r["symbol"]))
            for obs, cost, fee, slip in CASES:
                settings = ExecutionConfig(
                    max_open_positions=spec["cap"], fee_rate=fee, max_slippage_bps=slip
                ).model_dump()
                settings.update(spec["settings"])
                result = simulate(
                    list(range(start, end + 1, 300000)),
                    groups,
                    lambda coin: prices.get(coin, {}),
                    rules,
                    lambda coin: funding[coin],
                    SimpleNamespace(**settings),
                    research_policy=dict(spec["policy"], observation_minutes=obs),
                )
                assert not any(
                    j["kind"] in ["loss_stop", "atr_stop", "time_exit", "account_stop"]
                    for j in result["journal"]
                )
                row = summarize(
                    result,
                    spec["id"],
                    spec["label"],
                    spec["policy"],
                    spec["cap"],
                    cost,
                    period,
                )
                row.update(
                    id=f"{period}_{obs}m_{cost}_{spec['id']}",
                    strategy_id=spec["id"],
                    observation_minutes=obs,
                    adds=sum(j["kind"] == "entry_add" for j in result["journal"]),
                    completed_parts=[
                        j["filled_parts"] for j in result["journal"] if "net" in j
                    ],
                )
                write(
                    OUT / "runs" / f"{row['id']}.json",
                    {k: v for k, v in result.items() if k != "curve"},
                )
                pd.DataFrame(result["curve"]).to_parquet(
                    OUT / "runs" / f"{row['id']}_equity.parquet", index=False
                )
                if period == "holdout" and result["ending_equity"] is not None:
                    row["daily_bootstrap"] = daily_interval(result["curve"])
                rows.append(row)
        print(spec["id"], flush=True)
    assert sha(ROOT / "configs/live.yaml") == s["protocol"]["live_config_sha256"]
    write(
        OUT / "no_stop_results.json",
        dict(
            specs=specs,
            results=rows,
            primary_unchanged=s["primary"],
            live_config_unchanged=True,
        ),
    )
    pd.DataFrame(rows).to_csv(OUT / "no_stop_comparison.csv", index=False)
    print("COMPLETE", len(rows), flush=True)


if __name__ == "__main__":
    main()
