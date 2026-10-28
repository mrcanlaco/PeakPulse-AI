"""Post-selection execution-cost sensitivity; not a new holdout or calibrated fill model."""

from __future__ import annotations

import json
from collections import defaultdict
from types import SimpleNamespace

import pandas as pd
from account_backtest_replay import simulate
from backtest_without_ake import cached_inputs
from compare_account_risk import exchange_rules, summarize, write
from prepare_altcoin_search import OUT, RULE_PATH, SOURCE
from search_account_strategies import add_lows
from search_altcoin_families import WINDOWS, daily_interval

from dao_vang.config.settings import ExecutionConfig


def main():
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    primary = summary["primary"]
    if primary is None:
        return
    spec = next(r["spec"] for r in summary["finalists"] if r["strategy_id"] == primary)
    universe = summary["protocol"]["universe"]["symbols"]
    rules = exchange_rules(RULE_PATH)
    prices, funding, proofs = cached_inputs(
        SOURCE, OUT / "cache", [dict(symbol=s) for s in universe], rules
    )
    add_lows(prices, proofs, SOURCE)
    signals = json.loads((OUT / "signals.json").read_text(encoding="utf-8"))[
        spec["signal"]["id"]
    ]
    rows = []
    for period in ["validation", "holdout", "full"]:
        start, end = [
            int(pd.Timestamp(t, tz="UTC").timestamp() * 1000) for t in WINDOWS[period]
        ]
        times = list(range(start, end + 1, 300000))
        groups = defaultdict(list)
        for s in signals:
            if start <= s["at"] < end:
                groups[s["at"]].append(s)
        for batch in groups.values():
            batch.sort(key=lambda s: (-s["probability"], s["symbol"]))
        for slip in [2, 5, 10, 20, 50]:
            for fill in ["close", "bar_low"]:
                settings = ExecutionConfig(
                    max_open_positions=spec["cap"],
                    fee_rate=0.0005,
                    max_slippage_bps=slip,
                ).model_dump()
                settings.update(spec["settings"])
                result = simulate(
                    times,
                    groups,
                    lambda s: prices.get(s, {}),
                    rules,
                    lambda s: funding[s],
                    SimpleNamespace(**settings),
                    research_policy=dict(spec["policy"], tp_fill=fill),
                )
                row = summarize(
                    result,
                    primary,
                    spec["label"],
                    spec["policy"],
                    spec["cap"],
                    f"{slip}bps",
                    period,
                )
                row.update(
                    id=f"{period}_{fill}_{slip}bps",
                    fill=fill,
                    slippage_bps=slip,
                    commission_per_side=0.0005,
                )
                if period == "holdout" and result["ending_equity"] is not None:
                    row["daily_bootstrap"] = daily_interval(result["curve"])
                if slip == 20:
                    original = next(
                        r
                        for r in summary["results"]
                        if r["strategy_id"] == primary
                        and r["window"] == period
                        and r["fill"] == fill
                        and r["cost"] == "base"
                    )
                    assert row["ending_equity"] == original["ending_equity"]
                rows.append(row)
    write(
        OUT / "cost_sensitivity.json",
        dict(
            primary=primary,
            caveat="Post-selection sensitivity of the same locked strategy. Low slippage is hypothetical, not demonstrated from historical order books. Does not alter primary gate or prove profitable executable returns. Commission held at .05% per side; 50bps here is not original stress fee .10%.",
            results=rows,
        ),
    )
    for r in rows:
        if r["window"] == "holdout":
            print(
                r["slippage_bps"],
                r["fill"],
                r["pnl"],
                r.get("daily_bootstrap", {}).get("ci95_daily"),
            )


if __name__ == "__main__":
    main()
