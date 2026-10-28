"""Offline, pre-locked paired V3 entry-spacing experiment on reused history.

Run --freeze first, then --run. Nothing changes production or source data.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, replace
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT, ROOT / "src"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from scripts import replay_v3_verified_inputs as replay
from dao_vang.labels.specs.distribution_short_v3 import SPEC

OUT = ROOT / "artifacts/research_branches_20261012/v3"
AUDIT = ROOT / "artifacts/v3_improvement_20260922/input_audit_numeric_fix/input_audit.json"
BASELINE = ROOT / "artifacts/v3_improvement_20260922/verified_replay_numeric_fix/verified_replay.json"
ENGINE = ROOT / "src/dao_vang/labels/engine_v3.py"


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(replay._json_safe(value), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def locked_specs():
    return {
        "compact": asdict(SPEC),
        "wide": asdict(replace(SPEC, offsets=(0.0, 0.08, 0.14))),
        "compact_cost2x": asdict(replace(SPEC, cost_per_side=SPEC.cost_per_side * 2)),
        "wide_cost2x": asdict(replace(SPEC, offsets=(0.0, 0.08, 0.14), cost_per_side=SPEC.cost_per_side * 2)),
    }


def source_hashes():
    paths = [Path(__file__), AUDIT, BASELINE, ENGINE, Path(replay.__file__), Path(replay.audit.__file__),
             ROOT / "src/dao_vang/labels/specs/distribution_short_v3.py",
             replay.DEFAULT_REFERENCE, replay.DEFAULT_PRICE_REPLAY, replay.DEFAULT_DATA_MANIFEST,
             replay.DEFAULT_PRICE_MANIFEST]
    return {str(p): replay.sha256_file(p) for p in paths}


def freeze():
    path = OUT / "experiment_lock.json"
    if path.exists():
        raise RuntimeError("Lock already exists; no adaptive overwrite allowed")
    lock = {
        "branch": "v3", "frozen_at_utc": now(), "source_hashes": source_hashes(),
        "hypothesis": "Wider scale-in spacing changes adverse-path exposure and net planned-notional return relative to Compact; direction is not assumed.",
        "specs": locked_specs(), "selection_reapplied": False,
        "primary_population": "source_champion_gate_accepted within each lane, never pooled",
        "secondary_population": "all frozen rows within each lane; diagnostic only",
        "primary_metric": "paired mean net_return_planned difference wide minus compact on funding-certified common events",
        "secondary_metrics": ["target_count", "stop_count", "timeout_count", "deployed_notional", "cost2x sensitivity"],
        "decision": "No production promotion. Any observed improvement is exploratory and requires untouched future evidence.",
        "history_status": "previously viewed/adaptively researched; not an independent holdout",
        "scope": "Fixed 48h horizon; no delay or post-outcome filtering; no stop removal or leverage/account ROI.",
    }
    write_json(path, lock)
    print(json.dumps({"frozen": str(path), "sha256": replay.sha256_file(path)}))


def isolated_engine():
    # Separate module globals: replacing its frozen SPEC never changes imported
    # application modules, their source files, or running services.
    name = "_v3_branch_isolated_engine"
    spec = importlib.util.spec_from_file_location(name, ENGINE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def summarize(rows):
    eligible = [r for r in rows if r["eligible"]]
    result = {"row_count": len(rows), "unique_source_events": len({r["source_event_id"] for r in rows}),
              "financially_eligible_count": len(eligible), "excluded_count": len(rows) - len(eligible),
              "exclusions": dict(Counter(reason for r in rows if not r["eligible"] for reason in r["exclusions"])),
              "variants": {}, "paired": {}}
    for name in locked_specs():
        outcomes = [r["variants"][name] for r in eligible]
        result["variants"][name] = {
            "n": len(outcomes), "status_counts": dict(Counter(o["status"] for o in outcomes)),
            "mean_net_return_planned": statistics.mean(o["net_return_planned"] for o in outcomes) if outcomes else None,
            "median_net_return_planned": statistics.median(o["net_return_planned"] for o in outcomes) if outcomes else None,
            "mean_deployed_notional": statistics.mean(o["deployed_notional"] for o in outcomes) if outcomes else None,
        }
    for wide, compact in [("wide", "compact"), ("wide_cost2x", "compact_cost2x")]:
        diffs = [r["variants"][wide]["net_return_planned"] - r["variants"][compact]["net_return_planned"] for r in eligible]
        result["paired"][wide + "_minus_" + compact] = {
            "n": len(diffs), "mean_difference": statistics.mean(diffs) if diffs else None,
            "median_difference": statistics.median(diffs) if diffs else None,
            "improved_count": sum(d > 1e-12 for d in diffs), "worsened_count": sum(d < -1e-12 for d in diffs),
            "unchanged_count": sum(abs(d) <= 1e-12 for d in diffs),
        }
    return result


def assert_lock(lock):
    if lock["source_hashes"] != source_hashes():
        raise RuntimeError("Locked source hash changed; abort rather than silently refreeze")
    if json.loads(json.dumps(locked_specs())) != lock["specs"]:
        raise RuntimeError("Experiment parameters differ from frozen lock")


def run():
    lock_path = OUT / "experiment_lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    assert_lock(lock)
    started = now()
    stored = json.loads(AUDIT.read_text(encoding="utf-8"))
    fresh = replay._fresh_audit(stored=stored, reference_path=replay.DEFAULT_REFERENCE,
        price_replay_path=replay.DEFAULT_PRICE_REPLAY, data_manifest_path=replay.DEFAULT_DATA_MANIFEST,
        funding_root=replay.DEFAULT_FUNDING_ROOT, price_manifest_path=replay.DEFAULT_PRICE_MANIFEST,
        price_root=replay.DEFAULT_PRICE_ROOT)
    write_json(OUT / "fresh_input_audit.json", fresh)
    old_rows = {r["lane_event_key"]: r for r in json.loads(BASELINE.read_text(encoding="utf-8"))["events"]}
    engine = isolated_engine()
    prices, funds, rows, data_hashes = {}, {}, [], {}
    for event in fresh["events"]:
        eligible = bool(event["eligibility"]["financial_replay_input_ready"] and event["funding"]["funding_input_ready"])
        row = {k: event[k] for k in ("lane_event_key", "source_event_id", "symbol", "lane", "signal_time_utc")}
        row.update(champion=event["reference"]["champion_gate_accepted"] is True,
                   eligible=eligible, exclusions=event["exclusions"], variants={})
        if eligible:
            symbol = event["symbol"]
            if symbol not in prices:
                symbol_info = fresh["symbols"][symbol]
                price_path = Path(symbol_info["price"]["artifact"]["resolved_path"])
                funding_path = Path(symbol_info["funding"]["artifact"]["resolved_path"])
                prices[symbol] = replay._read_normalized_price_rows(price_path, symbol)
                funds[symbol] = replay._read_funding_rows(funding_path, symbol)
                for path in (price_path, funding_path):
                    data_hashes[str(path)] = replay.sha256_file(path)
            path, bars = replay._price_path(event, prices[symbol])
            _, funding, coverage = replay._funding_path(event, funds[symbol])
            if coverage is None:
                raise RuntimeError("Eligible event lacks certified funding coverage")
            for name, params in lock["specs"].items():
                params["offsets"] = tuple(params["offsets"])
                params["notional_weights"] = tuple(params["notional_weights"])
                engine.SPEC = type(SPEC)(**params)
                result = engine.evaluate(signal_time=replay.parse_utc(event["signal_time_utc"]),
                    signal_price=path["entry_price"], bars=bars, funding=funding,
                    funding_coverage_through=coverage)
                if not result.eligible or result.net_return_planned is None:
                    raise RuntimeError("Paired event not financially eligible for all variants")
                row["variants"][name] = result.to_dict()
            actual = row["variants"]["compact"]
            old = old_rows[event["lane_event_key"]]
            if actual["status"] != old["actual_status"] or abs(actual["net_return_planned"] - old["actual_net_return_planned"]) > 1e-12:
                raise RuntimeError("Compact baseline does not reproduce frozen result")
        rows.append(row)
    lanes = sorted({r["lane"] for r in rows})
    summary = {lane: {"all_frozen": summarize([r for r in rows if r["lane"] == lane]),
                      "champion": summarize([r for r in rows if r["lane"] == lane and r["champion"]])} for lane in lanes}
    assert_lock(json.loads(lock_path.read_text(encoding="utf-8")))
    report = {
        "branch": "v3", "status": "completed_exploratory_paired_replay_no_promotion",
        "started_at_utc": started, "completed_at_utc": now(),
        "experiment_lock_sha256": replay.sha256_file(lock_path),
        "source_hashes": {**source_hashes(), **data_hashes, str(lock_path): replay.sha256_file(lock_path)},
        "evidence": [{"kind": "cohort_audit", "rows": len(rows),
                      "unique_source_events": len({r["source_event_id"] for r in rows}),
                      "financially_eligible_rows": sum(r["eligible"] for r in rows),
                      "baseline_reproduced_for_all_eligible_rows": True},
                     {"kind": "paired_replay", "by_lane": summary}],
        "limitations": ["Reused historical data, not an independent holdout or future performance claim.",
            "Missing funding is excluded, never zero-filled; excluded events may differ systematically.",
            "Different lanes overlap and must not be pooled as independent trades; symbols/episodes may also be dependent.",
            "5-minute OHLC execution uses inherited conservative ordering, not order-book/queue/partial-fill proof.",
            "Returns are fractions of planned notional, not account ROI; margin, portfolio overlap and liquidation are not simulated.",
            "Only spacing and fixed cost sensitivity tested; timing/selection/48h horizon unchanged.",
            "No winner is automatically selected; fixed small hypotheses prevent a broad parameter search but cannot undo prior historical reuse."],
        "next_experiment": {"status": "requires_new_data", "description": "Collect future same-event Compact/Wide paper outcomes with complete funding, locked signal/model/universe versions, and portfolio capital/margin simulation; predefine evaluation windows and do not promote from this historical run.",
                            "live_changes_authorized_or_performed": False},
        "events": rows,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps({"status": report["status"], "summary": summary}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--freeze", action="store_true")
    modes.add_argument("--run", action="store_true")
    args = parser.parse_args()
    freeze() if args.freeze else run()
