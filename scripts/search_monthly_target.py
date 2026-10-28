"""Batch one for the persistent >=50% monthly research objective, offline only."""

import hashlib
import json
from collections import defaultdict

import pandas as pd
from account_scaled_replay import simulate
from altcoin_short_signals import load_frames
from backtest_without_ake import cached_inputs
from compare_account_risk import ROOT, exchange_rules, sha, summarize, write
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import OUT as DATA
from prepare_altcoin_search import RULE_PATH, SOURCE
from search_altcoin_families import WINDOWS, daily_interval
from short_regime_signals import definitions, generate

from dao_vang.config.settings import ExecutionConfig

OUT = ROOT / "artifacts/monthly_target_batch01_20260925"
CASES = [("base", 0.0005, 20), ("stress", 0.001, 50)]
NAMES = dict(
    failed_high="Phá đỉnh thất bại",
    exhaustion="Tăng mạnh bị bán xuống",
    ema_reject="Hồi EMA rồi bị từ chối",
    acceleration="Giảm mạnh kèm khối lượng",
)


def specs_for(signals):
    exits = [
        ("tp05", dict(fixed_tp_usdt=0.5, loss_usdt=0.5, max_hold_hours=12)),
        ("tp1", dict(fixed_tp_usdt=1, loss_usdt=1, max_hold_hours=24)),
        ("atr2", dict(loss_usdt=1, max_hold_hours=24)),
        (
            "trail2",
            dict(
                trailing=True,
                activation_atr=2,
                callback_fraction=0.01,
                loss_usdt=1,
                max_hold_hours=48,
            ),
        ),
    ]
    specs = []
    for source in signals:
        for mode, exit_policy in exits:
            for cap in [1, 5]:
                for parts in [1, 3]:
                    policy = dict(
                        exit_policy,
                        position_notional=25,
                        entry_parts=parts,
                        entry_mode="single" if parts == 1 else "favorable",
                        entry_step_atr=0.5,
                        add_expiry_hours=6,
                        require_split_eligibility=True,
                    )
                    specs.append(
                        dict(
                            id=f"{source['id']}_{mode}_n{cap}_p{parts}",
                            signal_id=source["id"],
                            family=source["family"],
                            source=source,
                            cap=cap,
                            parts=parts,
                            exit=mode,
                            policy=policy,
                            anchor=False,
                            label=f"{NAMES[source['family']]} · {source['regime']} · {source['cooldown_hours']}h · {mode} · {cap} vị thế · {parts} phần",
                        )
                    )
        if source["regime"] == "any" and source["cooldown_hours"] == 6:
            for parts in [1, 3]:
                policy = dict(
                    fixed_tp_usdt=1,
                    position_notional=25,
                    entry_parts=parts,
                    entry_mode="single" if parts == 1 else "favorable",
                    entry_step_atr=0.5,
                    add_expiry_hours=6,
                    require_split_eligibility=True,
                )
                specs.append(
                    dict(
                        id=f"{source['id']}_nostop_n5_p{parts}",
                        signal_id=source["id"],
                        family=source["family"],
                        source=source,
                        cap=5,
                        parts=parts,
                        exit="nostop",
                        policy=policy,
                        anchor=True,
                        label=f"{NAMES[source['family']]} · Không SL/thời hạn · 5 vị thế · {parts} phần",
                    )
                )
    return specs


def aggregate(rows, specs):
    output = []
    for spec in specs:
        rr = [r for r in rows if r["strategy_id"] == spec["id"]]
        complete = len(rr) == 2 and all(r["ending_equity"] is not None for r in rr)
        output.append(
            dict(
                spec=spec,
                strategy_id=spec["id"],
                complete=complete,
                worst_pnl=min(r["pnl"] for r in rr) if complete else None,
                best_pnl=max(r["pnl"] for r in rr) if complete else None,
                worst_dd=max(r["max_drawdown"] for r in rr),
                min_closed=min(r["exits"] for r in rr),
                fingerprints=[r["fingerprint"] for r in rr],
            )
        )
    return output


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "runs").mkdir(exist_ok=True)
    signal_specs = definitions()
    specs = specs_for(signal_specs)
    protocol = dict(
        objective="At least 50% in every consecutive monthly account interval, net of costs/funding including marked open positions. Compounded target 500 -> 750 -> 1125 -> 1687.5; not just +250 every month or one winning month.",
        created_at=pd.Timestamp.now(tz="UTC").isoformat(),
        variants=specs,
        windows=WINDOWS,
        cases=CASES,
        initial_equity=500,
        total_notional=25,
        leverage=5,
        selection="Development Jun24-Jul24, top two distinct non-anchor candidates per new signal family by worst net PnL, both cases complete, DD<20%, >=20 closes. Keep eight no-SL anchors irrespective of result. Lock before validation; select primary among same sample/DD conditions on validation worst PnL; lock before final period. Full path monthly marks determine >=50% each month. Do not promote from retrospective positive result alone.",
        execution="Short only, total planned margin5 at x5 per position, max1/5, single or3 entries. All candidates require split-minimum eligibility for matched coin filters. Costs base .05% fees/20bps slippage, stress .1%/50bps. Same 20% entry-pause latch; no forced account flattening. SL/time exits are research variants; no-stop anchors retain no loss/time exits. Trailing2ATR/1% observed5m, not native continuous trailing. ATR locked at entry; require target eligibility >=.5 as before.",
        signals=signal_specs,
        source_code_sha256={
            p: sha(ROOT / "scripts" / p)
            for p in [
                "short_regime_signals.py",
                "monthly_account_metrics.py",
                "account_scaled_replay.py",
                "search_monthly_target.py",
            ]
        },
        live_config_sha256=sha(ROOT / "configs/live.yaml"),
        limitations="Already-inspected 2026 dates. Thirty-coin preperiod turnover universe with current listing/filter survivorship bias. No delisted-complete universe, historical books or exchange maintenance tiers; maintenance1% proxy. Multiple tested rules and no new unseen forward evidence. This batch cannot establish dependable 50% monthly returns.",
    )
    write(OUT / "protocol.json", protocol)
    universe = json.loads((DATA / "universe.json").read_text(encoding="utf-8"))[
        "symbols"
    ]
    frames, frame_audit = load_frames(universe)
    signals = generate(frames)
    write(OUT / "signals.json", signals)
    write(OUT / "frame_audit.json", frame_audit)
    for coin, frame in frames.items():
        frame.to_parquet(OUT / f"features_{coin}.parquet")
    write(
        OUT / "features_manifest.json",
        {p.name: sha(p) for p in sorted(OUT.glob("features_*.parquet"))},
    )
    rules = exchange_rules(RULE_PATH)
    prices, funding, proof = cached_inputs(
        SOURCE, DATA / "cache", [dict(symbol=s) for s in universe], rules
    )
    write(OUT / "input_evidence.json", proof)
    groups, times = {}, {}
    for window, bounds in WINDOWS.items():
        start, end = [int(pd.Timestamp(t, tz="UTC").timestamp() * 1000) for t in bounds]
        times[window] = list(range(start, end + 1, 300000))
        for sid, events in signals.items():
            grouped = defaultdict(list)
            for event in events:
                if start <= event["at"] < end:
                    grouped[event["at"]].append(event)
            for group in grouped.values():
                group.sort(key=lambda s: (-s["probability"], s["symbol"]))
            groups[window, sid] = grouped

    def run(spec, window, case, persist=False):
        cost, fee, slip = case
        config = ExecutionConfig(
            max_open_positions=spec["cap"],
            fee_rate=fee,
            max_slippage_bps=slip,
            atr_multiplier=2,
        )
        r = simulate(
            times[window],
            groups[window, spec["signal_id"]],
            lambda c: prices.get(c, {}),
            rules,
            lambda c: funding[c],
            config,
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
            r, spec["id"], spec["label"], spec["policy"], spec["cap"], cost, window
        )
        row.update(
            id=f"{window}_{cost}_{spec['id']}",
            strategy_id=spec["id"],
            source_events=sum(
                len(g) for g in groups[window, spec["signal_id"]].values()
            ),
            adds=sum(j["kind"] == "entry_add" for j in r["journal"]),
            mean_deployed_notional=sum(notions.values()) / len(notions)
            if notions
            else 0,
            fingerprint=hashlib.sha256(
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
        if window == "full":
            row["monthly"] = monthly_metrics(r["curve"])
            row["goal_backtest_pass"] = (
                r["ending_equity"] is not None
                and row["monthly"]["all_months_50pct"]
                and r["sampled_max_drawdown"] < 0.2
            )
        if persist and window == "holdout" and r["ending_equity"] is not None:
            row["daily_bootstrap"] = daily_interval(r["curve"])
        return row

    rows = []
    for i, spec in enumerate(specs, 1):
        rows += [run(spec, "development", c) for c in CASES]
        if i % 24 == 0:
            print("Development", i, "/", len(specs), flush=True)
    dev = aggregate(rows, specs)
    write(OUT / "development.json", dev)
    chosen = []
    for family in NAMES:
        pool = [
            r
            for r in dev
            if r["spec"]["family"] == family
            and not r["spec"]["anchor"]
            and r["complete"]
            and r["worst_dd"] < 0.2
            and r["min_closed"] >= 20
        ]
        pool.sort(key=lambda r: (-r["worst_pnl"], r["worst_dd"], r["strategy_id"]))
        seen = set()
        for r in pool:
            fingerprint = tuple(r["fingerprints"])
            if fingerprint not in seen:
                seen.add(fingerprint)
                chosen.append(r["strategy_id"])
            if len(seen) == 2:
                break
    checked = [s for s in specs if s["id"] in chosen or s["anchor"]]
    write(
        OUT / "shortlist_lock.json",
        dict(selected=chosen, locked_at=pd.Timestamp.now(tz="UTC").isoformat()),
    )
    for spec in checked:
        rows += [run(spec, "validation", c, True) for c in CASES]
    val = aggregate([r for r in rows if r["window"] == "validation"], checked)
    eligible = [
        r
        for r in val
        if r["strategy_id"] in chosen
        and r["complete"]
        and r["worst_dd"] < 0.2
        and r["min_closed"] >= 20
    ]
    primary = (
        max(eligible, key=lambda r: r["worst_pnl"])["strategy_id"] if eligible else None
    )
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
            rows += [run(spec, window, c, True) for c in CASES]
        print("Final", spec["id"], flush=True)
    finalists = []
    for spec in checked:
        rr = [
            r for r in rows if r["strategy_id"] == spec["id"] and r["window"] == "full"
        ]
        finalists.append(
            dict(
                spec=spec,
                primary=spec["id"] == primary,
                selected=spec["id"] in chosen,
                goal_backtest_pass=all(r["goal_backtest_pass"] for r in rr),
                promotion_eligible=False,
            )
        )
    assert sha(ROOT / "configs/live.yaml") == protocol["live_config_sha256"]
    write(
        OUT / "summary.json",
        dict(
            protocol=protocol,
            results=rows,
            finalists=finalists,
            primary=primary,
            shortlist=chosen,
            runs=len(rows),
            live_config_unchanged=True,
            goal_backtest_pass_count=sum(f["goal_backtest_pass"] for f in finalists),
        ),
    )
    pd.DataFrame(rows).to_csv(OUT / "comparison.csv", index=False)
    write(
        OUT / "goal_progress.json",
        dict(
            objective=protocol["objective"],
            achieved=False,
            completed_batch="new price-volume and BTC regime signals; cadence6/24h; cap1/5; entry1/3; four exits plus no-stop controls",
            next_work="Audit batch, compare monthly capacity and regime stability; extend evidence beyond the repeatedly inspected period and test causal signal/execution improvements. Do not enlarge live risk or select retrospective winners as verified strategies.",
        ),
    )
    print(
        "COMPLETE",
        len(rows),
        "runs, >=50pct all months:",
        sum(f["goal_backtest_pass"] for f in finalists),
        flush=True,
    )


if __name__ == "__main__":
    main()
