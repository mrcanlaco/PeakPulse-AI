"""Batch19: shared-account Short/Long/Both comparison; no live imports."""
import json
from collections import Counter
import pandas as pd
from account_directional_replay import simulate
from directional_reversal_signals import generate
from capital_research_metrics import utilization
from compare_account_risk import ROOT, sha, write, summarize, exchange_rules
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from search_frozen_exits import DATA, WINDOWS, BOUNDARIES, COSTS, exit_diagnostics
from search_multitimeframe_rolling import grouped_signals

OUT = ROOT / "artifacts/directional_reversal_20260925"
PRIOR = ROOT / "artifacts/capacity_expansion_20260925"
SIGNALS = ROOT / "artifacts/reversal_flow_20260925/signals.json"


def definitions(previous):
    specs = []
    for mode in ["short", "long", "both"]:
        for mask in [0, 2]:
            for hold in ["hold", "time48"]:
                for cap in [5, 10]:
                    ident = f"mask{mask}_n25_{hold}_cap{cap}"
                    ref = next(p for p in previous["specs"] if p["id"] == ident)
                    specs.append(dict(id=f"{mode}_{ident}", source=dict(id=f"{mode}_mask{mask}", mask=mask),
                        mode=mode, mask=mask, notional=25, holding=hold, cap=cap,
                        policy=dict(ref["policy"]), baseline=mode == "short", reference_id=ident))
    return specs


def select(specs, results):
    selected = []
    for mode in ["short", "long", "both"]:
        for hold in ["hold", "time48"]:
            candidates = []
            for spec in specs:
                if spec["mode"] != mode or spec["holding"] != hold:
                    continue
                rs = [r for r in results if r["strategy_id"] == spec["id"] and r["window"] == "development"]
                if len(rs) != 2 or any(r["ending_equity"] is None or r["ending_equity"] <= 500
                    or r["max_drawdown"] >= .20 or not r["monthly"]["complete"]
                    or r["exit_diagnostics"]["all_exits"] < 20 for r in rs):
                    continue
                candidates.append((min(r["monthly"]["min_monthly_return"] for r in rs),
                                   min(r["ending_equity"] for r in rs), spec["id"]))
            selected.append(dict(mode=mode, holding=hold, strategy_id=max(candidates)[2] if candidates else None))
    return selected


def main():
    OUT.mkdir(exist_ok=True); (OUT / "runs").mkdir(exist_ok=True)
    old = json.loads((PRIOR / "summary.json").read_text(encoding="utf-8"))
    specs = definitions(old)
    protocol = dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(), specs=specs, windows=WINDOWS, costs=COSTS,
        hypothesis="Adding causal oversold Long reversals may complement frozen overbought Shorts. Compare single shared wallets, never add independent account returns.",
        account="500USDT Cross x5. Total25notional/5plannedmargin across3favorableparts0.25ATR/6hexpiry. Trail3ATR/callback1%,5mclosedobservations,nextopenadverseslip. Onepositionpercoin,shared5/10slots,20%persistentDDpause,allopenMTM. HoldnoSL vs48hforcedexitincludinglosses.10slotsresearchonly.",
        long="Prior closed4h close below own20bar mean-2std and prior24hreturn<=-5%;currentgreenclose reenterspriorlowerband. ATR14onclosed4h;72completebars;24hquotevolume>=2m.24hcoin cooldown BEFOREret6filter. Score=(priormean-priorclose)/priorstd. Optionalfresh6hreturn>=0 and same finiteguardreadiness as frozenShortmask2. No futurefunding in signal.",
        short="Preserve frozenmask0/mask2events,ATR,score,order. All48Shortpaths must match previouscapacitybatch exactly after removingaddedside metadata.",
        combined="Unionrankbydescendingzscore,coin,sideatthesametimestamp;Long/Short use common account and slots. Opposite signal onheldcoin is rejected, neverautomaticreversal. No hedgecredit on gross maintenance proxy.",
        selection="24specs x3windows x2cost=144paths. OnSep-May chooseonepermode/holding byhighestworstcostminmonthlyreturn thenworstendingequity,onlyifbothcostprofitable/DD<20%/20closedtrades/complete. LockbeforeJun-Aug. No candidateifnonepass. Historyalreadyinspected,NOTpristineOOS;reportallchoices.",
        target="Atleast50% netmarkedgrowth in EVERYcalendar month,notaggregate orbestmonth.",
        limitations="Repeatedhistoricaltesting,fixed30coinuniverse/survivorship,currentfilters,1%grossmaintenanceproxywithoutpointintimebrackets,sampled5mtrailing,assumedslippageandnohistoricalorderbook. No livepromotion.",
        funding_reference="https://www.binance.com/en/academy/glossary/funding-fees",
        live_config_sha256=sha(ROOT / "configs/live.yaml"), rules_sha256=sha(RULE_PATH),
        data_sha256=sha(DATA / "reconciled_manifest.json"), prior_sha256=sha(PRIOR / "summary.json"), signals_sha256=sha(SIGNALS),
        source_sha256={n: sha(ROOT / "scripts" / n) for n in ["account_directional_replay.py", "directional_reversal_signals.py",
          "search_directional_reversal.py", "account_scaled_replay.py", "short_multitimeframe_signals.py", "short_entry_guards.py",
          "short_guard_ablation.py", "frozen_extension_inputs.py", "research_capacity_config.py", "monthly_account_metrics.py"]})
    write(OUT / "protocol.json", protocol)
    prices, funding, frames = load(); rules = exchange_rules(RULE_PATH)
    signals, observations = generate(frames, funding, json.loads(SIGNALS.read_text(encoding="utf-8")))
    write(OUT / "signals.json", signals); write(OUT / "long_guard_observations.json", observations)
    print("SIGNALS", {k: len(v) for k, v in signals.items()}, flush=True)
    results = []; selected = []
    for window, (start, end) in WINDOWS.items():
        groups = {k: grouped_signals(v, start, end) for k, v in signals.items()}
        for i, spec in enumerate(specs, 1):
            for cost, fee, slip in COSTS:
                r = simulate(list(range(start, end + 1, 300000)), groups[spec["source"]["id"]],
                    lambda c: prices.get(c, {}), rules, lambda c: funding[c], configuration(spec["cap"], fee, slip), research_policy=spec["policy"])
                r["liquidation_status"] = "verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                row = summarize(r, spec["id"], spec["id"], spec["policy"], spec["cap"], cost, window)
                row.update(id=f"{window}_{cost}_{spec['id']}", strategy_id=spec["id"], source=spec["source"],
                    mode=spec["mode"], mask=spec["mask"], notional=25, holding=spec["holding"], baseline=spec["baseline"],
                    utilization=utilization(r["curve"], r, 25, spec["cap"]), exit_diagnostics=exit_diagnostics(r),
                    monthly=monthly_metrics(r["curve"], boundaries=[t for t in BOUNDARIES if start <= t <= end]),
                    peak_positions=max(p["positions"] for p in r["curve"]),
                    side_entries=dict(Counter(j["side"] for j in r["journal"] if j["kind"] == "entry")),
                    side_closed_net={side: sum(j["net"] for j in r["journal"] if "net" in j and j["side"] == side) for side in ["LONG", "SHORT"]})
                row["target_met"] = r["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                write(OUT / "runs" / f"{row['id']}.json", {k: v for k, v in r.items() if k != "curve"})
                pd.DataFrame(r["curve"]).to_parquet(OUT / "runs" / f"{row['id']}_equity.parquet", index=False)
                results.append(row)
            write(OUT / "progress.json", dict(window=window, finished=i, total=len(specs), runs=len(results)))
            if i % 4 == 0: print(window, i, "/", len(specs), flush=True)
        if window == "development":
            selected = select(specs, results)
            write(OUT / "candidate_lock.json", dict(selected=selected, locked_at=pd.Timestamp.now(tz="UTC").isoformat(), later_not_run_in_batch=True, pristine_oos=False))
            print("LOCKED", selected, flush=True)
    assert sha(ROOT / "configs/live.yaml") == protocol["live_config_sha256"]
    write(OUT / "summary.json", dict(protocol=protocol, specs=specs, selected=selected, results=results,
        target_met_rows=sum(r["target_met"] for r in results), incomplete_paths=sum(r["ending_equity"] is None for r in results)))
    pd.DataFrame(results).to_csv(OUT / "comparison.csv", index=False)
    print("COMPLETE", len(results), flush=True)


if __name__ == "__main__": main()
