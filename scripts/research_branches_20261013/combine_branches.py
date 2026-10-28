"""Fail-closed, fixed-initial-capital diagnostic sleeve comparison.

No trading APIs, no parameter search, no promotion of a backtest winner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "configs/research_branches_20261013.json"
LOCK = ROOT / "configs/research_branches_20261013.lock.json"
CASH_CONTROL = ROOT / "configs/research_branches_20261013.cash_control.json"
OUT = ROOT / "artifacts/research_branches_20261013"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_curve(curve, branch, contract):
    if not isinstance(curve, dict) or curve.get("branch") != branch:
        raise ValueError("branch_identity_mismatch")
    if curve.get("metric_basis") != "account_equity":
        raise ValueError("not_account_equity")
    if curve.get("diagnostic_combination_eligible") is not True:
        raise ValueError("not_diagnostic_combination_eligible")
    if curve.get("is_baseline") is not True:
        raise ValueError("not_predeclared_baseline")
    for field in ("valuation_convention", "normalization"):
        if curve.get(field) != contract[field]:
            raise ValueError(f"incompatible_{field}")
    rows = curve.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("no_equity_rows")
    start, end = date.fromisoformat(contract["start_date"]), date.fromisoformat(contract["end_date"])
    expected = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    if [row.get("date") for row in rows] != expected:
        raise ValueError("calendar_mismatch_or_duplicate_dates")
    values = []
    for row in rows:
        value = row.get("equity")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("invalid_equity_type")
        if not math.isfinite(value) or value <= 0:
            raise ValueError("nonfinite_or_nonpositive_equity_requires_separate_ruin_audit")
        values.append(value)
    if not math.isclose(values[0], 10000, rel_tol=1e-9, abs_tol=1e-6):
        raise ValueError("normalization_mismatch")
    return np.array(values, dtype=float)


def metrics(values):
    return {
        "total_return": float(values[-1] / values[0] - 1),
        "max_drawdown_daily_close": float(np.max(1 - values / np.maximum.accumulate(values))),
        "initial_equity": float(values[0]), "final_equity": float(values[-1]),
        "observations": len(values),
    }


def mix(curves, weights, contract):
    if not weights or any(w <= 0 for w in weights.values()) or not math.isclose(sum(weights.values()), 1):
        raise ValueError("weights_must_be_positive_and_sum_to_one")
    arrays = {branch: validate_curve(curves[branch], branch, contract) for branch in weights}
    nav = sum(arrays[branch] * weight for branch, weight in weights.items())
    correlations = {}
    names = list(weights)
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            a, b = arrays[left], arrays[right]
            ra, rb = np.diff(a) / a[:-1], np.diff(b) / b[:-1]
            correlations[f"{left}__{right}"] = (
                float(np.corrcoef(ra, rb)[0, 1])
                if np.std(ra) > 1e-12 and np.std(rb) > 1e-12 else None
            )
    financially_verified = all(
        curves[b].get("eligible_for_combination") is True
        and curves[b].get("funding_coverage_verified") is True for b in weights
    )
    return {
        "status": "diagnostic_mix_computed",
        "weights_at_start": weights,
        "portfolio_model": "segregated capital, no rebalancing or capital sharing",
        "financial_inputs_verified": financially_verified,
        "independent_alpha_verified": False,
        "metrics": metrics(nav),
        "standalone_same_slice": {b: metrics(v) for b, v in arrays.items()},
        "ending_capital_contribution": {b: float(weights[b] * a[-1]) for b, a in arrays.items()},
        "daily_return_correlations": correlations,
        "rows": [{"date": row["date"], "equity": float(nav[i])} for i, row in enumerate(curves[names[0]]["rows"])],
        "limitations": [
            "Previously seen history, not independent validation.",
            "Daily drawdown omits intraday excursions and liquidation risk.",
            "Not a shared-margin trading-account execution replay.",
            "Each sleeve keeps its own modeled costs; no assumption that opposing trades can be netted without cost.",
            "First daily close normalization omits the first day's return.",
        ] + [f"{b}: {item}" for b in weights for item in curves[b].get("limitations", [])],
    }


def collect(protocol_path=PROTOCOL, lock_path=LOCK, artifact_root=OUT):
    protocol = json.loads(protocol_path.read_text(encoding="utf-8-sig"))
    lock = json.loads(lock_path.read_text(encoding="utf-8-sig"))
    if lock.get("sha256") != digest(protocol_path):
        raise ValueError("common_protocol_lock_mismatch")
    contract = protocol["combination"]
    curves, sources, issues = {}, {}, {}
    for branch in protocol["names"]:
        path = artifact_root / branch / "equity.json"
        if not path.exists():
            issues[branch] = "equity_artifact_missing"
            continue
        sources[str(path)] = digest(path)
        try:
            report_path = artifact_root / branch / "report.json"
            if not report_path.is_file():
                raise ValueError("branch_report_missing")
            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
            if not isinstance(report, dict) or report.get("branch") != branch:
                raise ValueError("branch_report_identity_mismatch")
            if not isinstance(report.get("source_hashes"), dict) or not report["source_hashes"]:
                raise ValueError("branch_report_missing_source_provenance")
            sources[str(report_path)] = digest(report_path)
            curve = json.loads(path.read_text(encoding="utf-8-sig"))
            validate_curve(curve, branch, contract)
            curves[branch] = curve
        except (ValueError, KeyError, TypeError) as exc:
            issues[branch] = str(exc)
    results = {}
    for name in ("two_branch_weights", "three_branch_weights"):
        weights = contract[name]
        missing = {b: issues.get(b, "unavailable") for b in weights if b not in curves}
        results[name] = (
            {"status": "blocked_missing_eligible_curves", "reasons": missing}
            if missing else mix(curves, weights, contract)
        )
    if "flow" in curves:
        control = json.loads(CASH_CONTROL.read_text(encoding="utf-8"))
        if control["weights"] != {"flow": 0.5, "cash": 0.5}:
            raise ValueError("cash_control_weights_changed")
        cash = {
            "branch": "cash", "metric_basis": "account_equity", "is_baseline": True,
            "diagnostic_combination_eligible": True, "eligible_for_combination": True,
            "funding_coverage_verified": True,
            "valuation_convention": contract["valuation_convention"],
            "normalization": contract["normalization"],
            "rows": [{"date": r["date"], "equity": 10000} for r in curves["flow"]["rows"]],
            "limitations": [control["cash_assumption"]],
        }
        cash_result = mix({"flow": curves["flow"], "cash": cash}, control["weights"], contract)
        cash_result["timing_disclosure"] = control["timing_disclosure"]
        results["flow_cash_control"] = cash_result
        sources[str(CASH_CONTROL)] = digest(CASH_CONTROL)
    sources[str(Path(__file__).resolve())] = digest(Path(__file__).resolve())
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "names": protocol["names"], "protocol_sha256": digest(protocol_path),
        "source_hashes": sources, "results": results, "promotion_allowed": False,
    }


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = collect()
    encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        target = args.output.resolve()
        if not target.is_relative_to(OUT.resolve()):
            raise ValueError("output_must_stay_in_round2_artifacts")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
    else:
        print(encoded)


if __name__ == "__main__":
    main()
