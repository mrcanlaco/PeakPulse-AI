"""Đảo Chiều: three locked, entry-time micro-alpha filter ablations.

Offline only. Reuses audited Compact outcomes without changing their exits.
Opportunity-normalized returns retain rejected known-funded events at zero
allocation, but NEVER zero-fill unknown funding or missing outcome evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
from scripts.research_branches_20261012 import v3_branch as previous
from scripts import research_v3_mechanisms as mechanisms

OUT = ROOT / "artifacts/research_branches_20261013/v3"
PRIOR = ROOT / "artifacts/research_branches_20261012/v3/report.json"
BASE = previous.BASELINE
PIT = mechanisms.DEFAULT_PIT_DB
VARIANTS = ("compact_baseline", "A_reversal_1h", "B_crowded_funding", "AB_reversal_and_funding")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def source_hashes():
    sources = dict(load(PRIOR)["source_hashes"])
    for path in (Path(__file__), PRIOR, BASE, PIT, Path(mechanisms.__file__)):
        sources[str(path)] = previous.replay.sha256_file(path)
    return sources


def verify_hashes(hashes):
    for name, expected in hashes.items():
        if previous.replay.sha256_file(Path(name)) != expected:
            raise RuntimeError("Source hash mismatch: " + name)


def freeze():
    path = OUT / "experiment_lock.json"
    if path.exists():
        raise RuntimeError("Existing experiment lock must not be overwritten")
    hashes = source_hashes()
    verify_hashes(hashes)
    previous.write_json(path, {
        "branch": "v3", "name": "Đảo Chiều", "frozen_at_utc": previous.now(),
        "source_hashes": hashes, "variants": {
            "compact_baseline": "Accept every frozen source event; unchanged Compact execution.",
            "A_reversal_1h": "Entry-time price_ret_1h < 0; zero threshold expresses negative recent direction, not optimized.",
            "B_crowded_funding": "Entry-time funding_percentile_30d >= 0.80; reuse established research threshold, not optimized.",
            "AB_reversal_and_funding": "Logical A AND B; missing/nonfinite required features reject, not impute.",
        },
        "primary_population": "Champion historical lane; runtime-reference lane separately, never pooled",
        "secondary_population": "All original frozen events within each lane, diagnostic only",
        "primary_metric": "Mean net planned-notional return per common funded opportunity; rejected opportunities allocate zero, unknown financial evidence is excluded for every variant.",
        "secondary_metrics": ["accepted-count", "funding-excluded-count", "selected-only mean", "paired difference vs baseline", "AB-A and AB-B ablations"],
        "promotion_rule": "No promotion from reused history; assess whether candidate deserves untouched future paired evaluation.",
        "account_equity": "Not constructed from event averages; no marked collateral engine in this bounded iteration.",
        "no_new_holdout": True, "no_live_changes": True,
    })
    print(json.dumps({"lock": str(path), "sha256": previous.replay.sha256_file(path)}))


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def gates(features):
    r = features.get("price_ret_1h")
    f = features.get("funding_percentile_30d")
    a = finite(r) and r < 0
    b = finite(f) and 0 <= f <= 1 and f >= .8
    return dict(zip(VARIANTS, (True, a, b, a and b)))


def summary(rows):
    funded = [row for row in rows if row["financially_eligible"]]
    result = {"frozen_rows": len(rows), "unique_source_events": len({r["source_event_id"] for r in rows}),
              "common_funded_opportunities": len(funded), "funding_or_financial_excluded_rows": len(rows)-len(funded),
              "variants": {}, "ablations": {}}
    baseline_mean = statistics.mean(r["net_return_planned"] for r in funded) if funded else None
    for variant in VARIANTS:
        selected = [r for r in funded if r["gates"][variant]]
        opportunity = [r["net_return_planned"] if r["gates"][variant] else 0.0 for r in funded]
        result["variants"][variant] = {
            "accepted_rows_all_evidence": sum(r["gates"][variant] for r in rows),
            "accepted_funded_rows": len(selected),
            "accepted_but_financially_excluded_rows": sum(r["gates"][variant] and not r["financially_eligible"] for r in rows),
            "rejected_funded_rows_zero_allocation": len(funded)-len(selected),
            "selected_only_mean_net_return_planned": statistics.mean(r["net_return_planned"] for r in selected) if selected else None,
            "opportunity_normalized_mean_net_return_planned": statistics.mean(opportunity) if opportunity else None,
            "paired_mean_difference_vs_baseline": statistics.mean(opportunity)-baseline_mean if opportunity else None,
            "accepted_status_counts": dict(Counter(r["status"] for r in selected)),
            "missing_required_feature_rows": sum((variant in ("A_reversal_1h", "AB_reversal_and_funding") and not finite(r["features"].get("price_ret_1h"))) or
                (variant in ("B_crowded_funding", "AB_reversal_and_funding") and not finite(r["features"].get("funding_percentile_30d"))) for r in rows),
        }
    for single in ("A_reversal_1h", "B_crowded_funding"):
        differences = [(r["net_return_planned"] if r["gates"]["AB_reversal_and_funding"] else 0.0) -
                       (r["net_return_planned"] if r["gates"][single] else 0.0) for r in funded]
        result["ablations"]["AB_minus_"+single] = {
            "common_n": len(differences), "mean_opportunity_difference": statistics.mean(differences) if differences else None,
            "changed_decision_count": sum(r["gates"][single] != r["gates"]["AB_reversal_and_funding"] for r in funded)}
    return result


def run():
    lock_path = OUT / "experiment_lock.json"
    lock = load(lock_path)
    verify_hashes(lock["source_hashes"])
    original = load(BASE)["events"]
    prior = {r["lane_event_key"]: r for r in load(PRIOR)["events"]}
    specs = [{"source_event_id": r["source_event_id"], "symbol": r["symbol"],
              "feature_time": mechanisms._parse_utc(r["feature_time_utc"])} for r in original]
    features, join = mechanisms._load_exact_pit_features(PIT, specs)
    rows = []
    seen = set()
    for original_row in original:
        key = original_row["lane_event_key"]
        if key in seen:
            raise RuntimeError("Duplicate lane event")
        seen.add(key)
        r = prior[key]
        source_id = r["source_event_id"]
        if source_id != original_row["source_event_id"] or r["lane"] != original_row["lane"]:
            raise RuntimeError("Source cohort identity changed")
        feature_time = mechanisms._parse_utc(original_row["feature_time_utc"])
        signal_time = mechanisms._parse_utc(original_row["signal_time_utc"])
        if feature_time + timedelta(milliseconds=1) != signal_time:
            raise RuntimeError("Entry-time feature timestamp mismatch")
        f = {name: features[source_id]["features"][name] for name in ("price_ret_1h", "funding_percentile_30d")}
        eligible = r["eligible"] and original_row["financial_outcome_eligible"]
        net = r["variants"]["compact"]["net_return_planned"] if eligible else None
        if eligible and (not finite(net) or abs(net-original_row["actual_net_return_planned"]) > 1e-12):
            raise RuntimeError("Audited Compact outcome mismatch")
        rows.append({"lane_event_key": key, "lane": r["lane"], "source_event_id": source_id,
            "symbol": r["symbol"], "feature_time_utc": original_row["feature_time_utc"], "signal_time_utc": r["signal_time_utc"],
            "champion": r["champion"], "features": f, "gates": gates(f), "financially_eligible": eligible,
            "financial_exclusions": original_row["exclusions"] if not eligible else [],
            "net_return_planned": net, "status": original_row["actual_status"] if eligible else None})
    summaries = {lane: {"champion": summary([r for r in rows if r["lane"] == lane and r["champion"]]),
                         "all_frozen_diagnostic": summary([r for r in rows if r["lane"] == lane])}
                 for lane in sorted({r["lane"] for r in rows})}
    verify_hashes(lock["source_hashes"])
    report = {"branch": "v3", "name": "Đảo Chiều", "status": "completed_locked_microalpha_ablation_exploratory_only",
        "generated_at_utc": previous.now(), "source_hashes": {**lock["source_hashes"], str(lock_path): previous.replay.sha256_file(lock_path)},
        "evidence": [{"kind": "exact_entry_time_feature_join", **join},
            {"kind": "paired_microalpha_filters", "by_lane": summaries,
             "metric_basis": "net_return_planned_per_frozen_funded_opportunity_not_account_equity"}],
        "limitations": ["Historical data already researched; no new independent holdout or profitability claim.",
            "Unknown funding/outcomes excluded from every variant, not zero-filled; exclusions may be non-random.",
            "Rejected known-funded opportunities allocate zero only in opportunity-normalized comparisons; this is not daily cash NAV.",
            "Tiny primary funded samples, overlapping lanes and correlated coin/episode outcomes prohibit pooled independence claims.",
            "Existing Compact outcomes use OHLC and modeled costs, not actual execution; account collateral, capacity and marked open positions absent.",
            "Funding percentile indicates relative crowding, not necessarily a positive cash funding payment.",
            "Only two pre-entry features tested with fixed thresholds; no parameter sweep or automatic best-variant selection."],
        "eligible_for_combination": False, "equity_artifact": None,
        "combination_blockers": ["No complete daily marked account-equity ledger with collateral and concurrency limits.",
            "Event evidence does not provide complete January-August opportunity coverage; financially excluded events cannot become flat days."],
        "next_experiment": {"description": "Freeze surviving hypotheses for future paired evidence, then build/review a shared marked-account sleeve before portfolio combination.",
            "account_contract_required": {"initial_capital": 10000, "max_short_notional_to_equity": 1.0,
                "leverage": 1, "daily_marks_and_open_positions": True, "verified_funding": True,
                "explicit_collateral_reservation_for_unfilled_legs": True}, "live_changes_performed": False},
        "events": rows}
    previous.write_json(OUT / "report.json", report)
    print(json.dumps({"status": report["status"], "by_lane": summaries}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--freeze", action="store_true")
    modes.add_argument("--run", action="store_true")
    args = parser.parse_args()
    freeze() if args.freeze else run()
