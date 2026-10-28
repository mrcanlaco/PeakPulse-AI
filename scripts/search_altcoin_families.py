"""Search fresh short signal families on a frozen pre-period liquidity universe."""

from __future__ import annotations

import hashlib
import itertools
import json
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from account_backtest_replay import simulate
from altcoin_short_signals import definitions, generate, load_frames
from backtest_without_ake import cached_inputs
from compare_account_risk import ROOT, exchange_rules, sha, summarize, write
from prepare_altcoin_search import OUT, RULE_PATH, SOURCE
from search_account_strategies import CASES, add_lows, aggregate

from dao_vang.config.settings import ExecutionConfig

WINDOWS = dict(
    development=("2026-06-24", "2026-07-24"),
    validation=("2026-07-24", "2026-08-24"),
    holdout=("2026-08-24", "2026-09-24"),
    full=("2026-06-24", "2026-09-24"),
)
FAMILY_NAMES = dict(
    breakdown="Phá đáy trong xu hướng giảm",
    pullback="Hồi lên rồi giảm lại",
    weak_rank="Coin yếu hơn nhóm",
    failed_pump="Nhịp tăng thất bại",
)


def variants():
    exits = [
        (
            "tp0_5_sl0_5_h24",
            dict(fixed_tp_usdt=0.5, loss_usdt=0.5, max_hold_hours=24),
            {},
            "TP 0,5$ / SL 0,5$ / 24h",
        ),
        (
            "tp1_sl0_5_h24",
            dict(fixed_tp_usdt=1, loss_usdt=0.5, max_hold_hours=24),
            {},
            "TP 1$ / SL 0,5$ / 24h",
        ),
        (
            "tp2_sl1_h72",
            dict(fixed_tp_usdt=2, loss_usdt=1, max_hold_hours=72),
            {},
            "TP 2$ / SL 1$ / 72h",
        ),
        (
            "atr3_sl1_h48",
            dict(loss_usdt=1, max_hold_hours=48),
            dict(atr_multiplier=3),
            "TP 3 ATR / SL 1$ / 48h",
        ),
        (
            "atr2_nostop",
            {},
            dict(atr_multiplier=2, tp_max_usdt=10),
            "TP 2 ATR trần 10$ / không SL, không hạn giữ",
        ),
    ]
    result = []
    for signal, (exit_id, policy, settings, desc), cap in itertools.product(
        definitions(), exits, [1, 5]
    ):
        name = (
            FAMILY_NAMES[signal["family"]]
            + " · "
            + ("chặt" if signal["strength"] == "strict" else "rộng")
            + " · "
            + ("BTC giảm" if signal["btc"] == "bear" else "mọi trạng thái BTC")
            + " · "
            + (
                "funding không âm"
                if signal["funding"] == "nonnegative"
                else "không lọc funding"
            )
        )
        result.append(
            dict(
                id=f"{signal['id']}_{exit_id}_n{cap}",
                family=signal["family"],
                signal=signal,
                policy=policy,
                settings=settings,
                cap=cap,
                control=False,
                label=f"{name} · {desc} · {cap} vị thế",
                anchor=exit_id == "atr2_nostop"
                and cap == 5
                and signal["strength"] == "loose"
                and signal["btc"] == "any"
                and signal["funding"] == "any",
            )
        )
    return result


def daily_interval(curve):
    if len(curve) < 2:
        return None
    f = pd.DataFrame(curve)
    f.index = pd.to_datetime(f["at"], unit="ms", utc=True)
    # Difference from initial equity; final midnight belongs to the prior day.
    f.index = f.index - pd.Timedelta(milliseconds=1)
    daily = f.equity.resample("1D").last().dropna()
    if (
        len(daily) > 1
        and daily.index[0]
        < pd.to_datetime(curve[0]["at"], unit="ms", utc=True).normalize()
    ):
        daily = daily.iloc[1:]
    changes = np.diff(np.r_[500.0, daily.to_numpy()])
    rng = np.random.default_rng(20260925)
    n = len(changes)
    starts = rng.integers(0, n, size=(10000, (n + 6) // 7))
    indices = ((starts[:, :, None] + np.arange(7)) % n).reshape(10000, -1)[:, :n]
    means = changes[indices].mean(axis=1)
    return dict(
        days=n,
        total=float(changes.sum()),
        mean_daily=float(changes.mean()),
        ci95_daily=[float(x) for x in np.quantile(means, [0.025, 0.975])],
        method="circular 7-day block bootstrap of marked daily account PnL, 10000 samples; exploratory, not multiple-testing corrected",
    )


def main():
    (OUT / "runs").mkdir(exist_ok=True)
    universe = json.loads((OUT / "universe.json").read_text(encoding="utf-8"))
    specs = variants()
    assert len(specs) == 320
    protocol = dict(
        created_at=pd.Timestamp.now(tz="UTC").isoformat(),
        variants=specs,
        windows=WINDOWS,
        cases=CASES,
        universe=universe,
        initial_equity=500,
        notional=25,
        leverage=5,
        rules="Hourly completed candles only; 120 consecutive complete hours, ATR14, EMA20/60, pre-entry 24h turnover >=2m USDT. 24h signal cooldown per symbol and signal rule. Score named probability only for replay compatibility is a ranking score, NOT a calibrated probability. No look-ahead ML labels.",
        selection="Development: require four complete cases, DD<20%, >=20 closed trades each; top two per family by worst net PnL, deduplicated decision paths within family. Lock before validation; also four predeclared no-SL anchors. Validation: lock primary by worst PnL before looking at holdout; negative winner remains diagnostic only.",
        gate="All four validation and holdout cases complete with PnL>0, DD<20%, >=20 closed trades per case. Full continuous cases also PnL>0/DD<20%. Additional evidence flag requires lower 95% daily PnL block bootstrap >0 in all four holdout cases; even that is exploratory and not live qualification.",
        limitations="Current exchange universe/filters has survivorship bias; historical delisted universe and maintenance brackets unavailable (MMR1% proxy). History already inspected. TP bar_low not proven fills; 5m risk observation has gap risk. Fixed 25 notional, no DCA, persistent 20% opening pause, positions remain marked at end. Not simulated manual intervention.",
        references=[
            "https://www.nber.org/papers/w24877",
            "https://www.nber.org/papers/w25882",
            "https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf",
            "https://www.binance.com/en/support/faq/detail/360033525031",
        ],
        engine_sha256=sha(Path(__file__).with_name("account_backtest_replay.py")),
        signal_code_sha256=sha(Path(__file__).with_name("altcoin_short_signals.py")),
        runner_sha256=sha(Path(__file__)),
        live_config_sha256=sha(ROOT / "configs/live.yaml"),
    )
    write(OUT / "protocol.json", protocol)
    rules = exchange_rules(RULE_PATH)
    prices, funding, proofs = cached_inputs(
        SOURCE, OUT / "cache", [dict(symbol=s) for s in universe["symbols"]], rules
    )
    add_lows(prices, proofs, SOURCE)
    frames, audit = load_frames(universe["symbols"])
    signals = generate(frames, funding)
    write(OUT / "signals.json", signals)
    write(OUT / "hourly_audit.json", audit)
    write(OUT / "input_evidence.json", proofs)
    print("SIGNALS", {k: len(v) for k, v in signals.items()}, flush=True)
    times, groups = {}, {}
    for period, span in WINDOWS.items():
        start, end = [int(pd.Timestamp(t, tz="UTC").timestamp() * 1000) for t in span]
        times[period] = list(range(start, end + 1, 300000))
        for sid, events in signals.items():
            grouped = defaultdict(list)
            for e in events:
                if start <= e["at"] < end:
                    grouped[e["at"]].append(e)
            for batch in grouped.values():
                batch.sort(key=lambda s: (-s["probability"], s["symbol"]))
            groups[sid, period] = grouped
    results = []

    def run(spec, period, case, persist=False):
        fill, cost, fee, slip = case
        settings = ExecutionConfig(
            fee_rate=fee, max_slippage_bps=slip, max_open_positions=spec["cap"]
        ).model_dump()
        settings.update(spec["settings"])
        policy = dict(spec["policy"], tp_fill=fill)
        r = simulate(
            times[period],
            groups[spec["signal"]["id"], period],
            lambda s: prices.get(s, {}),
            rules,
            lambda s: funding[s],
            SimpleNamespace(**settings),
            research_policy=policy,
        )
        active, peak = set(), 0
        for j in r["journal"]:
            if j["kind"] == "entry":
                assert j["symbol"] not in active
                active.add(j["symbol"])
                peak = max(peak, len(active))
            elif "net" in j:
                assert j["symbol"] in active
                active.remove(j["symbol"])
        assert peak <= spec["cap"] and len(active) == len(r["open_positions"])
        if r["ending_equity"] is not None:
            expected = (
                500
                + r["closed_trade_net"]
                + sum(
                    p["unrealized"] - p["entry_fee"] + p["funding"]
                    for p in r["open_positions"]
                )
            )
            assert abs(expected - r["ending_equity"]) < 1e-7
        row = summarize(r, spec["id"], spec["label"], policy, spec["cap"], cost, period)
        row.update(
            id=f"{period}_{fill}_{cost}_{spec['id']}",
            strategy_id=spec["id"],
            fill=fill,
            peak_positions=peak,
            signal_count=sum(map(len, groups[spec["signal"]["id"], period].values())),
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
            if period == "holdout" and r["ending_equity"] is not None:
                row["daily_bootstrap"] = daily_interval(r["curve"])
        return row

    for n, spec in enumerate(specs, 1):
        results.extend(run(spec, "development", case) for case in CASES)
        if n % 16 == 0:
            print(f"Development {n}/320", flush=True)
    dev = aggregate(results, specs)
    write(OUT / "development_summary.json", dev)
    write(OUT / "development_runs.json", results)
    shortlist = []
    for family in FAMILY_NAMES:
        eligible = [
            r
            for r in dev
            if r["spec"]["family"] == family
            and r["complete"]
            and r["worst_dd"] < 0.2
            and r["min_closed"] >= 20
        ]
        eligible.sort(key=lambda r: (-r["worst_pnl"], r["worst_dd"], r["strategy_id"]))
        selected, seen = [], set()
        for row in eligible:
            fp = tuple(row["fingerprints"])
            if fp not in seen:
                selected.append(row["strategy_id"])
                seen.add(fp)
            if len(selected) == 2:
                break
        shortlist.extend(selected)
    write(
        OUT / "shortlist_lock.json",
        dict(
            locked_at=pd.Timestamp.now(tz="UTC").isoformat(),
            selected=shortlist,
            protocol_sha256=sha(OUT / "protocol.json"),
        ),
    )
    checked = [s for s in specs if s["id"] in shortlist or s["anchor"]]
    print("LOCKED", shortlist, flush=True)
    for spec in checked:
        results.extend(run(spec, "validation", case, True) for case in CASES)
        print("Validation", spec["id"], flush=True)
    val = aggregate([r for r in results if r["window"] == "validation"], checked)
    eligible = [v for v in val if v["strategy_id"] in shortlist and v["complete"]]
    eligible.sort(key=lambda r: (-r["worst_pnl"], r["worst_dd"], r["strategy_id"]))
    primary = eligible[0]["strategy_id"] if eligible else None
    write(
        OUT / "primary_lock.json",
        dict(
            locked_at=pd.Timestamp.now(tz="UTC").isoformat(),
            primary=primary,
            ranking=eligible,
            holdout_not_run=True,
        ),
    )
    print("PRIMARY LOCKED", primary, flush=True)
    for spec in checked:
        for period in ["holdout", "full"]:
            results.extend(run(spec, period, case, True) for case in CASES)
        print("Final checks", spec["id"], flush=True)
    hold = aggregate([r for r in results if r["window"] == "holdout"], checked)
    full = aggregate([r for r in results if r["window"] == "full"], checked)
    finalists = []
    for v in val:
        h = next(r for r in hold if r["strategy_id"] == v["strategy_id"])
        f = next(r for r in full if r["strategy_id"] == v["strategy_id"])
        gate = (
            all(
                r["complete"] and r["worst_pnl"] > 0 and r["worst_dd"] < 0.2
                for r in [v, h, f]
            )
            and min(v["min_closed"], h["min_closed"]) >= 20
        )
        confidence = all(
            r.get("daily_bootstrap", {}).get("ci95_daily", [-1])[0] > 0
            for r in results
            if r["window"] == "holdout" and r["strategy_id"] == v["strategy_id"]
        )
        finalists.append(
            dict(
                strategy_id=v["strategy_id"],
                spec=v["spec"],
                validation=v,
                holdout=h,
                full=f,
                diagnostic_passed=gate,
                confidence_positive=gate and confidence,
                primary=v["strategy_id"] == primary,
                shortlisted=v["strategy_id"] in shortlist,
                promotion_eligible=False,
            )
        )
    assert sha(ROOT / "configs/live.yaml") == protocol["live_config_sha256"]
    write(
        OUT / "summary.json",
        dict(
            protocol=protocol,
            results=results,
            finalists=finalists,
            shortlist=shortlist,
            primary=primary,
            runs=len(results),
            diagnostic_pass_count=sum(f["diagnostic_passed"] for f in finalists),
            live_config_unchanged=True,
            promotion_eligible=False,
        ),
    )
    pd.DataFrame(results).to_csv(OUT / "comparison.csv", index=False)
    print(
        "COMPLETE",
        len(results),
        "runs; passed",
        sum(f["diagnostic_passed"] for f in finalists),
        flush=True,
    )


if __name__ == "__main__":
    main()
