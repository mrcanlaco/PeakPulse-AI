"""Read-only research audit. Writes only new, branch-owned artifacts, never shadow state."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/research_branches_20261012/flow"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def freeze_protocol(out: Path) -> dict:
    """Exclusive creation: cannot quietly change the protocol after viewing results."""
    protocol = {
        "branch": "flow", "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "stage": "correctness_audit_not_profitability_test",
        "selection_rule": "Highest locked validation Calmar composite plus highest validation Calmar non-composite control; no test or postlock ranking.",
        "max_representatives": 2,
        "selection_bias": "Validation was adaptively reused; these representatives are not independently validated winners.",
        "audit": ["Raw report counts", "Actual funding settlement timestamps versus four-hour aggregation", "Missing funding coverage is not zero", "Survivorship", "Decision/execution timing fixtures"],
        "future_experiment": {
            "name": "Event-time funding and point-in-time universe paired replay",
            "variants": ["Frozen composite", "Same composite with taker factor removed", "Same composite with funding factor removed", "Frozen non-composite mechanism control"],
            "rules": "Hold sizing, universe and execution constant. Funding charged at actual event time to holdings existing immediately before event. Missing coverage fails eligibility. Same-time settlement precedes rebalance. Include delisted contracts. No parameter sweep.",
            "primary_metrics": ["Net account return including open positions", "Maximum intrabar drawdown", "Funding contribution", "Turnover", "Concentration by coin/month"],
            "stress": ["Double modeled execution costs", "One 4h-bar additional delay", "Rerun account excluding largest contributor"],
            "holdout": "2020-2026 through 2026-10-12 are development evidence, not new holdout. Freeze corrected implementation and explicit UTC start before any future observation. Do not retroactively label existing shadow days fresh.",
            "gate": "No deployment or profitability claim until funding coverage and point-in-time membership checks pass; minimum 90 future calendar days across different market regimes is a review floor, not automatic statistical acceptance.",
            "launch_status": "not_started; does not touch 28 existing shadows",
        },
    }
    out.mkdir(parents=True, exist_ok=True)
    with (out / "protocol.json").open("x", encoding="utf-8") as stream:
        json.dump(protocol, stream, indent=2, ensure_ascii=False)
    return protocol


def funding_diagnostics(frame: pd.DataFrame) -> dict:
    """Mirror current loader's floor+keep-last loss without estimating trading PnL."""
    times = pd.to_datetime(frame.funding_time, utc=True)
    rates = pd.to_numeric(frame.funding_rate)
    bins = times.dt.floor("4h")
    keep = ~bins.duplicated(keep="last")
    delays = (times - bins).dt.total_seconds()
    exact_duplicates = int(times.duplicated(keep="last").sum())
    return {
        "events": len(frame),
        "off_4h_boundary_events": int((delays != 0).sum()),
        "shifted_earlier_more_than_60_seconds": int((delays > 60).sum()),
        "outside_00_08_16_events": int(((times.dt.hour % 8 != 0) | (times.dt.minute != 0) | (times.dt.second != 0)).sum()),
        "dropped_by_floor_keep_last": int((~keep).sum()),
        "exact_duplicate_timestamps": exact_duplicates,
        "distinct_events_collapsed": int((~keep).sum()) - exact_duplicates,
        "distinct_hour_settlements_collapsed": int(times.dt.floor("h").nunique() - bins.nunique()),
        "same_hour_timestamp_duplicates": int(times.dt.floor("h").duplicated(keep="last").sum()),
        "rate_sum_raw": float(rates.sum()),
        "rate_sum_loader": float(rates[keep].sum()),
        "absolute_rate_mass_dropped": float(rates[~keep].abs().sum()),
        "max_seconds_shifted_earlier": float(delays.max()) if len(frame) else 0.0,
    }


def select_representatives(rows: pd.DataFrame, locked_ids: set[str]) -> list[dict]:
    frame = rows[rows.id.isin(locked_ids)]
    selected = []
    for kind, mask in [("composite", frame.family == "composite"), ("mechanism_control", frame.family != "composite")]:
        group = frame[mask].sort_values(["val_calmar", "id"], ascending=[False, True])
        if len(group):
            row = group.iloc[0]
            selected.append({"role": kind, "id": str(row.id), "val_calmar": float(row.val_calmar), "params": json.loads(row.params)})
    return selected


def run_audit(root: Path, out: Path, lake: Path) -> dict:
    protocol_path = out / "protocol.json"
    if not protocol_path.exists():
        raise RuntimeError("Freeze protocol before running the audit")
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    source_hashes = {}

    def source(path: Path) -> Path:
        source_hashes[str(path.resolve())] = sha256(path)
        return path

    source(protocol_path)
    source(Path(__file__).resolve())
    source(root / "tests/unit/research_branches_20261012/test_flow_branch.py")
    base = root / "artifacts/nostop"
    lock_path = source(base / "candidate_lock.json")
    lock = json.loads(lock_path.read_text())
    expected_hash = source(base / "candidate_lock.sha256").read_text().strip().split()[0]
    lock_valid = sha256(lock_path) == expected_hash
    if not lock_valid:
        raise RuntimeError("Candidate lock hash mismatch")
    locked_ids = {spec["id"] for spec in lock["specs"]}
    rows = pd.read_csv(source(base / "final_results.csv"))
    robust = pd.read_csv(source(base / "robustness.csv"))
    meta = json.loads(source(base / "panel_4h_meta.json").read_text())
    corr = json.loads(source(base / "robustness_meta.json").read_text())
    source(root / "src/dao_vang/nostop/data.py")
    source(root / "src/dao_vang/nostop/engine.py")
    with np.load(source(base / "panel_4h.npz")) as panel:
        symbols = panel["symbols"].tolist()
    if set(rows.id) != locked_ids or set(robust.id) != locked_ids:
        raise RuntimeError("Report candidate membership mismatch")
    audits, missing = {}, []
    start, end = pd.Timestamp(meta["start"]), pd.Timestamp(meta["end"]) + pd.Timedelta("4h")
    for symbol in symbols:
        path = lake / "funding" / f"{symbol}_funding.parquet"
        if not path.exists():
            missing.append(symbol)
            continue
        frame = pd.read_parquet(source(path), columns=["funding_time", "funding_rate"])
        times = pd.to_datetime(frame.funding_time, utc=True)
        frame = frame[(times >= start) & (times < end)]
        audits[symbol] = funding_diagnostics(frame)
    total_fields = ["events", "off_4h_boundary_events", "shifted_earlier_more_than_60_seconds", "outside_00_08_16_events", "dropped_by_floor_keep_last", "exact_duplicate_timestamps", "distinct_events_collapsed", "distinct_hour_settlements_collapsed", "same_hour_timestamp_duplicates"]
    totals = {key: sum(row[key] for row in audits.values()) for key in total_fields}
    affected = {symbol: values for symbol, values in audits.items() if values["distinct_events_collapsed"] or values["off_4h_boundary_events"]}
    evidence = [
        {"finding": "Archived result counts reproduced, not new backtest", "locked_count": len(locked_ids), "lock_hash_valid": lock_valid,
         "test_calmar_gt1": int((rows.test_calmar > 1).sum()), "positive_test_return": int((rows.test_total_return > 0).sum()),
         "all_splits_calmar_gt1": int(((rows.train_calmar > 1) & (rows.val_calmar > 1) & (rows.test_calmar > 1)).sum()),
         "test_double_cost_calmar_gt1": int((rows.test_stress_calmar > 1).sum()),
         "test_delay1_calmar_gt1": int((robust.test_delay1_calmar > 1).sum()), "test_delay3_calmar_gt1": int((robust.test_delay3_calmar > 1).sum())},
        {"finding": "Frozen representative selection", "selection": select_representatives(rows, locked_ids)},
        {"finding": "Funding timestamp audit of actual archived raw files", "period_start": str(start), "period_end_exclusive": str(end),
         "totals": totals, "affected_symbols_count": len(affected), "affected_symbols": affected, "missing_files": missing,
         "materially_affected_symbols_count": sum(value["shifted_earlier_more_than_60_seconds"] > 0 or value["distinct_hour_settlements_collapsed"] > 0 for value in audits.values()),
         "interpretation": "Loader floors events to 4h and keeps only last per bucket. Millisecond exchange timestamp offsets affect116 symbols but are separated from >60-second shifts. Distinct-hour collapse is not explained by millisecond duplicates. Trading PnL impact magnitude AND SIGN are unknown until event-time paired replay; these are data-integrity findings, NOT corrected returns."},
        {"finding": "Known survivorship and redundant variants", "symbols": meta["symbols"], "survivorship_bias": meta["survivorship_bias"],
         "reported_test_daily_return_correlation_median": corr["test_corr_median"], "correlation_status": "Archived statistic only; not independently recomputed from daily returns"},
        {"finding": "Execution depends on future price availability", "verification": "Actual engine synthetic regression: identical current open and decision except next open set NaN changes executed position from 0.5 to 0.0. Existing position with missing next price receives zero return rather than explicit unresolved valuation.", "risk": "Lookahead through availability mask; delisting or missing-price paths can suppress entry and hide losses. Separate trade eligibility and unresolved valuations before profitability replay."},
    ]
    report = {
        "branch": "flow", "status": "audit_complete_replay_blocked_pending_event_time_funding_and_point_in_time_universe",
        "created_at": datetime.now(timezone.utc).isoformat(), "evidence": evidence,
        "limitations": ["No new strategy PnL or live execution measured", "Historical test and September-October extension already seen", "Validation selection adaptively reused", "Raw funding files are local archive snapshots; this audit does not independently verify exchange completeness or price at funding time", "No causal per-position funding PnL correction from rate sums", "Survivor-only universe remains uncorrected", "Existing 28 shadows were not read, modified, started or paused"],
        "next_experiment": protocol["future_experiment"], "source_hashes": source_hashes,
    }
    with (out / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--lake", type=Path, default=Path("C:/Quant-trading/data_lake"))
    args = parser.parse_args()
    if args.freeze:
        freeze_protocol(OUT)
        print("Protocol frozen; no results computed")
    else:
        result = run_audit(ROOT, OUT, args.lake)
        print(json.dumps({"status": result["status"], "counts": result["evidence"][0], "funding_totals": result["evidence"][2]["totals"], "affected_symbols": result["evidence"][2]["affected_symbols_count"]}, indent=2))
