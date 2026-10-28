"""Version-isolated implementation and validation of the trading methodology."""

from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(Path(__file__).resolve().parent)]
ART = ROOT / "artifacts/fibo_trend_short"


def verify_history() -> int:
    baseline = json.loads((ART / "HISTORICAL_ARTIFACTS_BASELINE_BEFORE_v4_0_6.json").read_text(encoding="utf-8"))
    changed = [path for path, digest in baseline["files"].items()
               if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest]
    if changed:
        raise AssertionError(f"Historical artifacts changed: {changed}")
    return len(baseline["files"])


def run_universe() -> None:
    from universe_reaudit_v402_worker import run_universe_338_reaudit_v402
    from verify_red_team_reaudit_v402 import summarize_audit_items_v402
    from ledger_reconciliation import reconcile_ledger_tree
    from pit_method_v406 import run_comparison
    from method_provenance_v406 import verify

    verify_history()
    verify()
    run_universe_338_reaudit_v402(summarize_audit_items_v402, use_cache=False, target_version="4.0.6", method_comparison_fn=run_comparison)
    ledgers = json.loads((ART / "universe_coupled_ledgers_v4_0_6_cache.json").read_text(encoding="utf-8"))
    result = reconcile_ledger_tree(ledgers)
    result["historical_artifacts_unchanged"] = verify_history()
    result["inputs_unchanged"] = verify()
    (ART / "UNIVERSE_MONETARY_RECONCILIATION_v4_0_6.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    # Preserve any benchmark ledgers added in a separate stage.
    target = ART / "coupled_trade_ledgers_v4_0_6.json"
    combined = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {"version": "4.0.6", "ledgers_by_key": {}}
    combined["ledgers_by_key"].update(ledgers)
    target.write_text(json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8")
    if not result["all_passed"]:
        raise AssertionError("Universe monetary reconciliation failed; inspect saved evidence")
    print(f"Universe monetary reconciliation passed: {result['ledger_count']} ledgers", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["universe"], required=True)
    parser.parse_args()
    run_universe()
