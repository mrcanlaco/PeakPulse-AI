"""Older-period entry timing experiment; retrospective, never live promotion."""

import json
from collections import defaultdict

import numpy as np
import pandas as pd
from account_scaled_replay import simulate
from altcoin_short_signals import definitions as old_definitions
from altcoin_short_signals import generate as old_generate
from compare_account_risk import ROOT, exchange_rules, sha, summarize, write
from historical_research_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from prepare_historical_research import OUT as DATA
from short_entry_timing import definitions as entry_definitions
from short_entry_timing import transform
from short_event_study import outcomes, statistics
from short_regime_signals import definitions as new_definitions
from short_regime_signals import generate as new_generate

from dao_vang.config.settings import ExecutionConfig

OUT = ROOT / "artifacts/historical_entry_search_20260925"
WINDOWS = dict(development=["2025-09-01", "2025-12-01"],
               validation=["2025-12-01", "2026-03-01"],
               holdout=["2026-03-01", "2026-06-01"],
               full=["2025-09-01", "2026-06-01"])
SPANS = {k: tuple(int(pd.Timestamp(t, tz="UTC").timestamp()*1000) for t in v) for k,v in WINDOWS.items()}
BOUNDARIES = [int(t.timestamp()*1000) for t in pd.date_range("2025-09-01", "2026-06-01", freq="MS", tz="UTC")]
COSTS = [("base", 0.0005, 20), ("stress", 0.001, 50)]


def audit_account(result, cap=5):
    active, notionals = {}, defaultdict(float)
    for j in result["journal"]:
        if j["kind"] == "entry":
            assert j["symbol"] not in active
            active[j["symbol"]] = j["event_id"]
            assert len(active) <= cap
        if j["kind"] in ["entry", "entry_add"]:
            assert active[j["symbol"]] == j["event_id"]
            notionals[j["event_id"]] += j["qty"] * j["price"]
        if "net" in j:
            assert active.pop(j["symbol"]) == j["event_id"]
    assert max(notionals.values(), default=0) <= 25 + 1e-8
    assert len(active) == len(result["open_positions"])
    if result["ending_equity"] is not None:
        difference = result["ending_equity"] - 500 - result["closed_trade_net"] - sum(
            p["unrealized"] - p["entry_fee"] + p["funding"] for p in result["open_positions"])
        assert abs(difference) < 1e-7
    return dict(max_total_notional=max(notionals.values(), default=0),
                mean_total_notional=float(np.mean(list(notionals.values()))) if notionals else 0,
                accounting_checked=True)


def main():
    OUT.mkdir(exist_ok=True)
    for directory in ["runs", "watches"]:
        (OUT / directory).mkdir(exist_ok=True)
    old = [s for s in old_definitions() if s["strength"] == "loose" and s["btc"] == "any" and s["funding"] == "any"]
    new = [s for s in new_definitions() if s["regime"] == "any" and s["cooldown_hours"] == 24]
    sources = old + new
    hypotheses = [dict(id=f"{source['id']}_{timing['id']}_h{h}", source=source,
                       timing=timing, horizon_hours=h)
                  for source in sources for timing in entry_definitions() for h in [4,24,48]]
    protocol = dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),
                    hypotheses=hypotheses, windows=WINDOWS, costs=COSTS,
                    sources=sources, target="At least50% marked equity growth EACH calendar month, with costs and open losses included.",
                    predeclared_selection="312 development screens:8 families x13 entries x3 horizons. Per family lock one non-immediate rule with >=100 complete events, no missing outcomes, rank worst base/stress95% lower CI then worst mean. Validation: rank locked rules by worst mean with >=100 events; lock up to2 diagnostic candidates even if nonpositive. Compare their immediate controls at the same horizon. Final period never selects winners.",
                    screen="Overlapping independent hypothetical shorts; fixed horizon from entry, no intermediate liquidation/capacity. Not portfolio returns. Same fractional notional and costs per event; original ATR frozen. 7day aligned cross-coin cluster bootstrap, unadjusted for312 comparisons.",
                    portfolio="Each of two candidates and matched immediate control: parts1/3; cap5; total notional25, leverage5, equity500; trailing3ATR activation,1% callback observed5m. Parts3 add only after0.5ATR favorable movement,6h expiry. Compare noSL/no time exit with research SL1USDT scaled by filled parts plus48h time exit. All simulated, no live changes. Twenty-percent peak drawdown pauses entries, not positions/TP.",
                    limits="Older history already inspected by earlier annual research; not untouched OOS. Frozen preperiod liquidity universe can still have warehouse survivor bias. Current exchange filters,1%MMR proxy, no historic depth/tiers, close-sampled trailing can miss intrabar events. No historical exact liquidation claim; no50% monthly promise.",
                    data_manifest_sha256=sha(DATA / "manifest.json"),
                    live_config_sha256=sha(ROOT / "configs/live.yaml"),
                    source_sha256={name:sha(ROOT / "scripts" / name) for name in [
                        "search_historical_entries.py", "historical_research_inputs.py", "short_entry_timing.py",
                        "account_scaled_replay.py", "short_event_study.py", "monthly_account_metrics.py"]})
    write(OUT / "protocol.json", protocol)
    prices, funding, frames = load()
    rules = exchange_rules(RULE_PATH)
    missing_rules = sorted(set(prices) - set(rules))
    if missing_rules:
        raise ValueError("Selected symbols have missing current-rule proxy; do not drop: " + repr(missing_rules))
    signals = old_generate(frames, funding, old) | new_generate(frames, new)
    write(OUT / "signals.json", signals)
    print("SIGNALS", {s:len(v) for s,v in signals.items()}, flush=True)
    transformed, watches = {}, {}

    def entry_set(source_id, timing, window):
        key = (source_id, timing["id"], window)
        if key not in transformed:
            entries, audit = transform(signals[source_id], prices, *SPANS[window], timing)
            transformed[key], watches[key] = entries, audit
            write(OUT / "watches" / ("_".join(key) + ".json"), audit)
        return transformed[key], watches[key]

    def screen(spec, window):
        source_id, timing = spec["source"]["id"], spec["timing"]
        entries, audit = entry_set(source_id, timing, window)
        rows, counts = outcomes(entries, prices, funding, *SPANS[window], spec["horizon_hours"])
        cases = {name:statistics(rows, *SPANS[window], fee, slip) for name,fee,slip in COSTS}
        complete = counts["missing"] == 0 and not audit["counts"].get("missing_data") and counts["complete"] >= 100
        pairs = []
        for entry in entries:
            origin = entry.get("original_signal_at", entry["at"])
            before = prices[entry["symbol"]][origin]["entry_open"]
            after = prices[entry["symbol"]][entry["at"]]["entry_open"]
            if np.isfinite(before) and np.isfinite(after):
                pairs.append((after/before - 1)*10000)
        return dict(id=spec["id"], spec=spec, window=window, counts=counts,
                    watch_counts=audit["counts"], source_events=audit["source_events"],
                    cases=cases, complete=complete,
                    worst_lower=min(cases[c]["ci95"][0] for c,_,_ in COSTS) if complete else None,
                    worst_mean=min(cases[c]["mean_net_return"] for c,_,_ in COSTS) if complete else None,
                    paired_entry=dict(events=len(pairs), mean_improvement_bps=float(np.mean(pairs)) if pairs else None,
                                      higher_short_entry_fraction=float(np.mean(np.array(pairs)>0)) if pairs else None))

    development = []
    for i, spec in enumerate(hypotheses, 1):
        development.append(screen(spec, "development"))
        if i % 39 == 0:
            print("DEVELOPMENT", i, "/", len(hypotheses), flush=True)
    write(OUT / "development.json", development)
    selected = []
    for source in sources:
        pool = [r for r in development if r["spec"]["source"]["id"] == source["id"]
                and r["spec"]["timing"]["id"] != "immediate" and r["complete"]]
        if pool:
            selected.append(max(pool, key=lambda r:(r["worst_lower"], r["worst_mean"]))["spec"])
    write(OUT / "family_lock.json", dict(locked_at=pd.Timestamp.now(tz="UTC").isoformat(), selected=selected))
    validation = [screen(spec, "validation") for spec in selected]
    ordered = sorted([r for r in validation if r["complete"]], key=lambda r:-r["worst_mean"])
    chosen = [r["spec"] for r in ordered[:2]]
    write(OUT / "portfolio_lock.json", dict(locked_at=pd.Timestamp.now(tz="UTC").isoformat(), chosen=chosen, final_not_run=True))
    print("LOCKED", [s["id"] for s in chosen], flush=True)
    holdout = [screen(spec, "holdout") for spec in selected]
    controls = []
    for spec in chosen:
        immediate = dict(spec, timing=entry_definitions()[0], id=spec["source"]["id"] + f"_immediate_h{spec['horizon_hours']}")
        for window in ["validation", "holdout"]:
            controls.append(screen(immediate, window))
    write(OUT / "screen_summary.json", dict(development=development, validation=validation, holdout=holdout,
                                            immediate_controls=controls, chosen=chosen))
    portfolio_specs = []
    for candidate in chosen:
        for timing in [candidate["timing"], entry_definitions()[0]]:
            for parts in [1,3]:
                for risk in ["no_stop", "sl1_h48"]:
                    policy = dict(position_notional=25, entry_parts=parts,
                                  entry_mode="single" if parts == 1 else "favorable",
                                  entry_step_atr=0.5, add_expiry_hours=6,
                                  require_split_eligibility=True, trailing=True,
                                  activation_atr=3, callback_fraction=0.01, observation_minutes=5)
                    if risk == "sl1_h48":
                        policy.update(loss_usdt=1, max_hold_hours=48)
                    portfolio_specs.append(dict(id=f"{candidate['source']['family']}_{timing['id']}_p{parts}_{risk}",
                                                source=candidate["source"], timing=timing, parts=parts, risk=risk, policy=policy))
    write(OUT / "portfolio_specs.json", portfolio_specs)
    results = []
    for i, spec in enumerate(portfolio_specs, 1):
        for window in ["validation", "holdout", "full"]:
            entries, audit = entry_set(spec["source"]["id"], spec["timing"], window)
            assert not audit["counts"].get("missing_data")
            grouped = defaultdict(list)
            for signal in entries:
                grouped[signal["at"]].append(signal)
            for group in grouped.values():
                group.sort(key=lambda s:(-s["probability"], s["symbol"]))
            start, end = SPANS[window]
            for cost, fee, slip in COSTS:
                result = simulate(list(range(start, end+1, 300000)), grouped, lambda c:prices.get(c, {}),
                                  rules, lambda c:funding[c],
                                  ExecutionConfig(max_open_positions=5, fee_rate=fee, max_slippage_bps=slip),
                                  research_policy=spec["policy"])
                # Shared engine's legacy label says marks missing; these marks ARE audited.
                result["liquidation_status"] = "verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                audit_result = audit_account(result)
                row = summarize(result, spec["id"], spec["id"], spec["policy"], 5, cost, window)
                row.update(id=f"{window}_{cost}_{spec['id']}", strategy_id=spec["id"],
                           audit=audit_result, parts=spec["parts"], risk=spec["risk"],
                           timing=spec["timing"]["id"], source=spec["source"]["family"])
                if window == "full":
                    row["monthly"] = monthly_metrics(result["curve"], boundaries=BOUNDARIES)
                    row["target_met"] = result["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                write(OUT / "runs" / f"{row['id']}.json", {k:v for k,v in result.items() if k != "curve"})
                pd.DataFrame(result["curve"]).to_parquet(OUT / "runs" / f"{row['id']}_equity.parquet", index=False)
                results.append(row)
        write(OUT / "portfolio_progress.json", dict(finished=i, total=len(portfolio_specs), runs=len(results)))
        print("PORTFOLIO", i, "/", len(portfolio_specs), spec["id"], flush=True)
    assert sha(ROOT / "configs/live.yaml") == protocol["live_config_sha256"]
    write(OUT / "summary.json", dict(protocol=protocol, development=development, validation=validation,
                                     holdout=holdout, controls=controls, chosen=chosen, portfolio_specs=portfolio_specs,
                                     results=results, target_met_rows=sum(r.get("target_met", False) for r in results),
                                     live_config_unchanged=True))
    pd.DataFrame(results).to_csv(OUT / "comparison.csv", index=False)
    write(OUT / "goal_progress.json", dict(status="active", achieved=False, progress_classification="progress",
                                          next="Audit the long-history screens and portfolio paths. Test different causal signal mechanisms if entry timing is not robust; retain original sizing pending optional preference."))
    print("COMPLETE", len(development), "screens", len(results), "account runs", flush=True)


if __name__ == "__main__":
    main()
