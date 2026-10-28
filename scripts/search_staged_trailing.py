"""Factor staged entries versus sampled trailing exits on locked signal sources."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from account_scaled_replay import simulate
from backtest_without_ake import cached_inputs
from compare_account_risk import ROOT, exchange_rules, sha, summarize, write
from prepare_altcoin_search import OUT as PREVIOUS
from prepare_altcoin_search import RULE_PATH, SOURCE
from search_account_strategies import aggregate
from search_altcoin_families import FAMILY_NAMES, WINDOWS, daily_interval

from dao_vang.config.settings import ExecutionConfig

CASES = [
    (5, "base", 0.0005, 20),
    (5, "stress", 0.001, 50),
    (15, "base", 0.0005, 20),
    (15, "stress", 0.001, 50),
]


def variants(sources, budget):
    entries = [
        ("single", dict(entry_parts=1, entry_mode="single"), "Vào một lần"),
        (
            "time15",
            dict(entry_parts=3, entry_mode="time", entry_interval_minutes=15),
            "3 phần, cách ≥15 phút",
        ),
        (
            "time60",
            dict(entry_parts=3, entry_mode="time", entry_interval_minutes=60),
            "3 phần, cách ≥60 phút",
        ),
        (
            "favor0_25",
            dict(entry_parts=3, entry_mode="favorable", entry_step_atr=0.25),
            "3 phần, giảm thêm 0,25 ATR",
        ),
        (
            "favor0_5",
            dict(entry_parts=3, entry_mode="favorable", entry_step_atr=0.5),
            "3 phần, giảm thêm 0,5 ATR",
        ),
    ]
    exits = [("fixed", dict(trailing=False), "TP cố định như đối chứng")]
    exits += [
        (
            f"trail_a{a}_c{c:g}",
            dict(trailing=True, activation_atr=a, callback_fraction=c / 100),
            f"Bật sau {a} ATR, hồi {c:g}%",
        )
        for a, c in itertools.product([1, 2, 3], [0.5, 1, 2])
    ]
    result = []
    for source, (entry_id, entry, label), (
        exit_id,
        exit_policy,
        desc,
    ) in itertools.product(sources, entries, exits):
        risk = dict(source["policy"])
        # Retain each source's original guard, TP eligibility and holding limit.
        risk.update(
            entry,
            **exit_policy,
            position_notional=budget,
            add_expiry_hours=6,
            require_split_eligibility=True,
        )
        result.append(
            dict(
                id=f"{source['family']}_{entry_id}_{exit_id}",
                source=source,
                family=source["family"],
                cap=source["cap"],
                policy=risk,
                settings=source["settings"],
                signal_id=source["signal"]["id"],
                entry=entry_id,
                exit=exit_id,
                label=f"{FAMILY_NAMES[source['family']]} · {label} · {desc}",
                control=False,
                anchor=exit_id == "fixed",
            )
        )
    for source in sources:
        result.append(
            dict(
                id=f"{source['family']}_original",
                source=source,
                family=source["family"],
                cap=source["cap"],
                policy=dict(source["policy"], position_notional=budget),
                settings=source["settings"],
                signal_id=source["signal"]["id"],
                entry="single",
                exit="fixed",
                label=FAMILY_NAMES[source["family"]]
                + " · Đối chứng gốc (chưa lọc mức tối thiểu mỗi phần)",
                control=False,
                anchor=True,
            )
        )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--notional", type=float, default=25)
    args = parser.parse_args()
    out = ROOT / f"artifacts/staged_trailing_20260925_{args.notional:g}"
    out.mkdir(exist_ok=True)
    (out / "runs").mkdir(exist_ok=True)
    prior = json.loads((PREVIOUS / "summary.json").read_text(encoding="utf-8"))
    sources = []
    for family in FAMILY_NAMES:
        pool = [
            f
            for f in prior["finalists"]
            if f["spec"]["family"] == family
            and f["shortlisted"]
            and f["validation"]["complete"]
        ]
        sources.append(max(pool, key=lambda f: f["validation"]["worst_pnl"])["spec"])
    specs = variants(sources, args.notional)
    protocol = dict(
        created_at=pd.Timestamp.now(tz="UTC").isoformat(),
        variants=specs,
        cases=CASES,
        windows=WINDOWS,
        sources=sources,
        initial_equity=500,
        total_notional=args.notional,
        leverage=5,
        margin_budget=args.notional / 5,
        tranche_rule="Three equal notional allowances, sum <= total. No upsizing for exchange minima. Reserve unfilled allowances plus entry fee buffer. At most one add per 5m step; add only if completed close <= current VWAP. Time mode waits 15/60m between planned slots; favorable mode waits first fill minus 0.25/0.5 ATR per slot. Six-hour expiry. Gaps may worsen a fill; no look-ahead decision based on next open. Stop adds when paused, closed, expired or trailing activated.",
        trailing_rule="Short: activation fixed at first fill minus 1/2/3 initial ATR. Track minimum sampled contract close since first entry; buy next bar open + adverse slippage after price rebounds 0.5/1/2%. No fixed profit cap when trailing enabled. No peak reset after adds. Risk guards retain source SL/time limit; cash SL and fixed TP scale by filled-parts fraction. ATR/target eligibility based on planned full size. No live execution.",
        observation="5-minute and 15-minute sampled trailing, both executed at next available 5m trade open after observed trigger. NOT native continuous Binance trailing, no asserted intrabar fill ordering. MMR/risk guard observed every 5m. Fixed-TP controls use completed trade close only.",
        matched_control="All factorial configurations require initial 1/3 order to pass filters, even one-entry controls, so minimum notional selection is controlled. Original unfiltered one-entry controls retained separately. Recheck every actual tranche, never enlarge it.",
        selection="Top two combined 3-part + trailing candidates per signal family on development worst-case PnL, 4 complete cases, DD<20%, >=20 closed positions each. No gate relaxation. All fixed-TP controls retained plus corresponding one-entry trailing controls. Lock before validation, then lock primary before final period. These dates were already inspected: this is exploratory, not untouched OOS.",
        gate="All four validation and final cases PnL>0/DD<20% with >=20 closed positions; full-period PnL>0/DD<20%. Bootstrap intervals are exploratory and not multiple-testing adjusted. No live promotion.",
        engine_sha256=sha(Path(__file__).with_name("account_scaled_replay.py")),
        runner_sha256=sha(Path(__file__)),
        signal_sha256=sha(PREVIOUS / "signals.json"),
        live_config_sha256=sha(ROOT / "configs/live.yaml"),
        limitations=prior["protocol"]["limitations"],
        reference="https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade",
    )
    write(out / "protocol.json", protocol)
    signals = json.loads((PREVIOUS / "signals.json").read_text(encoding="utf-8"))
    universe = prior["protocol"]["universe"]["symbols"]
    rules = exchange_rules(RULE_PATH)
    prices, funding, proofs = cached_inputs(
        SOURCE, PREVIOUS / "cache", [dict(symbol=s) for s in universe], rules
    )
    write(out / "input_evidence.json", proofs)
    times, groups = {}, {}
    for period, span in WINDOWS.items():
        start, end = [int(pd.Timestamp(t, tz="UTC").timestamp() * 1000) for t in span]
        times[period] = list(range(start, end + 1, 300000))
        for source in sources:
            sid = source["signal"]["id"]
            grouped = defaultdict(list)
            for s in signals[sid]:
                if start <= s["at"] < end:
                    grouped[s["at"]].append(s)
            for batch in grouped.values():
                batch.sort(key=lambda s: (-s["probability"], s["symbol"]))
            groups[sid, period] = grouped
    results = []
    regressions = []

    def run(spec, period, case, persist=False):
        obs, cost, fee, slip = case
        settings = ExecutionConfig(
            max_open_positions=spec["cap"], fee_rate=fee, max_slippage_bps=slip
        ).model_dump()
        settings.update(spec["settings"])
        r = simulate(
            times[period],
            groups[spec["signal_id"], period],
            lambda s: prices.get(s, {}),
            rules,
            lambda s: funding[s],
            SimpleNamespace(**settings),
            research_policy=dict(spec["policy"], observation_minutes=obs),
        )
        active = set()
        peak = 0
        notionals = {}
        completed_parts = []
        for j in r["journal"]:
            if j["kind"] == "entry":
                assert j["symbol"] not in active
                active.add(j["symbol"])
                peak = max(peak, len(active))
                notionals[j["event_id"]] = j["qty"] * j["price"]
            elif j["kind"] == "entry_add":
                assert j["symbol"] in active
                notionals[j["event_id"]] += j["qty"] * j["price"]
            elif "net" in j:
                active.remove(j["symbol"])
                completed_parts.append(j["filled_parts"])
        assert all(n <= args.notional + 1e-8 for n in notionals.values())
        assert peak <= spec["cap"] and len(active) == len(r["open_positions"])
        if r["ending_equity"] is not None:
            assert (
                abs(
                    r["ending_equity"]
                    - (
                        500
                        + r["closed_trade_net"]
                        + sum(
                            p["unrealized"] - p["entry_fee"] + p["funding"]
                            for p in r["open_positions"]
                        )
                    )
                )
                < 1e-7
            )
        row = summarize(
            r, spec["id"], spec["label"], spec["policy"], spec["cap"], cost, period
        )
        row.update(
            id=f"{period}_{obs}m_{cost}_{spec['id']}",
            strategy_id=spec["id"],
            observation_minutes=obs,
            adds=sum(j["kind"] == "entry_add" for j in r["journal"]),
            completed_parts=completed_parts,
            mean_deployed_notional=sum(notionals.values()) / len(notionals)
            if notionals
            else 0,
            trailing_activations=sum(
                j["kind"] == "trail_activated" for j in r["journal"]
            ),
            decision_fingerprint=hashlib.sha256(
                json.dumps(
                    [j for j in r["journal"] if j["kind"] != "funding"], sort_keys=True
                ).encode()
            ).hexdigest(),
        )
        if persist:
            write(
                out / "runs" / f"{row['id']}.json",
                {k: v for k, v in r.items() if k != "curve"},
            )
            pd.DataFrame(r["curve"]).to_parquet(
                out / "runs" / f"{row['id']}_equity.parquet", index=False
            )
            if period == "holdout" and r["ending_equity"] is not None:
                row["daily_bootstrap"] = daily_interval(r["curve"])
        if spec["id"].endswith("_original") and obs == 5 and args.notional == 25:
            old = next(
                x
                for x in prior["results"]
                if x["strategy_id"] == spec["source"]["id"]
                and x["window"] == period
                and x["fill"] == "close"
                and x["cost"] == cost
            )
            assert all(
                row[k] == old[k]
                for k in [
                    "ending_equity",
                    "fees",
                    "funding",
                    "entries",
                    "exits",
                    "open_count",
                    "max_drawdown",
                ]
            ), (spec["id"], period, cost)
            regressions.append(row["id"])
        return row

    for n, spec in enumerate(specs, 1):
        results.extend(run(spec, "development", c) for c in CASES)
        if n % 20 == 0:
            print(f"Development {n}/{len(specs)}", flush=True)
    dev = aggregate(results, specs)
    write(out / "development_summary.json", dev)
    write(out / "development_runs.json", results)
    shortlist = []
    for family in FAMILY_NAMES:
        eligible = [
            r
            for r in dev
            if r["spec"]["family"] == family
            and r["spec"]["policy"].get("entry_parts") == 3
            and r["spec"]["policy"].get("trailing")
            and r["complete"]
            and r["worst_dd"] < 0.2
            and r["min_closed"] >= 20
        ]
        eligible.sort(key=lambda r: (-r["worst_pnl"], r["worst_dd"], r["strategy_id"]))
        seen = set()
        pick = []
        for r in eligible:
            fp = tuple(r["fingerprints"])
            if fp not in seen:
                pick.append(r["strategy_id"])
                seen.add(fp)
            if len(pick) == 2:
                break
        shortlist += pick
    paired = {
        f"{s['family']}_single_{s['exit']}" for s in specs if s["id"] in shortlist
    }
    checked = [
        s for s in specs if s["id"] in shortlist or s["id"] in paired or s["anchor"]
    ]
    write(
        out / "shortlist_lock.json",
        dict(
            selected=shortlist,
            paired_controls=sorted(paired),
            locked_at=pd.Timestamp.now(tz="UTC").isoformat(),
            protocol_sha256=sha(out / "protocol.json"),
        ),
    )
    print("LOCKED", shortlist, flush=True)
    for spec in checked:
        results.extend(run(spec, "validation", c, True) for c in CASES)
    val = aggregate([r for r in results if r["window"] == "validation"], checked)
    candidates = sorted(
        [r for r in val if r["strategy_id"] in shortlist and r["complete"]],
        key=lambda r: (-r["worst_pnl"], r["worst_dd"]),
    )
    primary = candidates[0]["strategy_id"] if candidates else None
    write(
        out / "primary_lock.json",
        dict(
            primary=primary,
            locked_at=pd.Timestamp.now(tz="UTC").isoformat(),
            holdout_not_run=True,
        ),
    )
    print("PRIMARY", primary, flush=True)
    for n, spec in enumerate(checked, 1):
        for period in ["holdout", "full"]:
            results.extend(run(spec, period, c, True) for c in CASES)
        print(f"Final {n}/{len(checked)} {spec['id']}", flush=True)
    hold = aggregate([r for r in results if r["window"] == "holdout"], checked)
    full = aggregate([r for r in results if r["window"] == "full"], checked)
    finalists = []
    for v in val:
        h = next(r for r in hold if r["strategy_id"] == v["strategy_id"])
        f = next(r for r in full if r["strategy_id"] == v["strategy_id"])
        passed = (
            all(
                r["complete"] and r["worst_pnl"] > 0 and r["worst_dd"] < 0.2
                for r in [v, h, f]
            )
            and min(v["min_closed"], h["min_closed"]) >= 20
        )
        finalists.append(
            dict(
                strategy_id=v["strategy_id"],
                spec=v["spec"],
                validation=v,
                holdout=h,
                full=f,
                shortlisted=v["strategy_id"] in shortlist,
                primary=v["strategy_id"] == primary,
                diagnostic_passed=passed,
                promotion_eligible=False,
            )
        )
    assert sha(ROOT / "configs/live.yaml") == protocol["live_config_sha256"]
    write(
        out / "summary.json",
        dict(
            protocol=protocol,
            results=results,
            finalists=finalists,
            shortlist=shortlist,
            primary=primary,
            runs=len(results),
            original_regressions=regressions,
            live_config_unchanged=True,
            diagnostic_pass_count=sum(f["diagnostic_passed"] for f in finalists),
        ),
    )
    pd.DataFrame(results).to_csv(out / "comparison.csv", index=False)
    print(
        "COMPLETE",
        len(results),
        "runs; passed",
        sum(f["diagnostic_passed"] for f in finalists),
        flush=True,
    )


if __name__ == "__main__":
    main()
