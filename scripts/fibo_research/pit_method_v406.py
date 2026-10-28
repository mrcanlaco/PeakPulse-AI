"""Prespecified sizing/cost comparisons on the monthly PIT universe."""

import json
from pathlib import Path

from ledger_reconciliation import reconcile_ledger_tree

ART = Path(__file__).resolve().parents[2] / "artifacts/fibo_trend_short"


def with_cost(sim: dict | None, cost_bps: float, *, risk_pct: float) -> dict | None:
    """Reprice the simulator's flat entry-notional cost, leaving fills unchanged.

    This is a spread/commission/slippage budget, not a claim about exchange fills.
    The simulator allocates half at the first observed close and half at exit.
    """
    if sim is None:
        return None
    result = dict(sim)
    original = float(sim["gross_pct"]) - float(sim["net_pct"])
    delta = cost_bps / 100.0 - original
    result["net_pct"] = float(sim["gross_pct"]) - cost_bps / 100.0
    if risk_pct <= 0 or cost_bps < 0:
        raise ValueError("Positive risk denominator and nonnegative cost required")
    result["r_mult"] = result["net_pct"] / risk_pct
    result["bar_trace"] = [dict(step) for step in sim["bar_trace"]]
    if not result["bar_trace"]:
        raise ValueError("A fully settled trace is required for cost repricing")
    result["bar_trace"][0]["bar_fee_pct"] += delta * 0.5
    result["bar_trace"][-1]["bar_fee_pct"] += delta * 0.5
    return result


def run_comparison(symbol_results: list, allowed_yms_by_symbol: dict) -> dict:
    from universe_reaudit_v402_worker import run_universe_portfolio_coupled_execution
    from verify_red_team_reaudit_v402 import summarize_audit_items_v402

    results, ledgers = {}, {}
    for window, field, start, end, hard in [
        ("calibration_2024_2025", "is_raw_candidates", "2024-01-01T00:00:00Z", "2026-01-01T00:00:00Z", False),
        ("reused_validation_hard_0831", "oos_raw_candidates", "2026-01-01T00:00:00Z", "2026-09-01T00:00:00Z", True),
    ]:
        source = [c for row in symbol_results for c in row[field]
                  if c["entry_ym"] in allowed_yms_by_symbol.get(c["symbol"], set())
                  and "m6_f4_expanded" in c["eligible_milestones"]]
        results[window] = {}
        for sizing in ("fixed_1x", "conviction_150_115_080"):
            results[window][sizing] = {}
            for cost in (20, 40, 60):
                print(f"   [PIT comparison] {window}/{sizing}/{cost}bps", flush=True)
                candidates = []
                for c in source:
                    copy = dict(c)
                    if sizing == "fixed_1x":
                        copy["mult_m6"] = 1.0
                    key = "sim_m6_0831" if hard else "sim_m6"
                    sim = copy[key]
                    if sim is not None:
                        # Derive the R denominator from actual initial prices,
                        # including the simulator's .2% floor.
                        risk_pct = max(.2, (copy["sl_m6"] - copy["entry_price"]) / copy["entry_price"] * 100)
                        copy[key] = with_cost(sim, cost, risk_pct=risk_pct)
                    candidates.append(copy)
                coupled = run_universe_portfolio_coupled_execution(
                    candidates, "m6_f4_expanded", start, end,
                    allowed_yms_by_symbol=allowed_yms_by_symbol, hard_cutoff_0831=hard,
                )
                key = f"pit_method/{window}/{sizing}/{cost}bps"
                ledgers[key] = {"ledger_records": coupled.pop("ledger_records")}
                summary = summarize_audit_items_v402(coupled.pop("accepted_items"))
                ci = summary.get("bootstrap_ci95", {})
                if "p_value_avg_net_le_0" in ci:
                    ci["bootstrap_fraction_mean_le_zero_diagnostic"] = ci.pop("p_value_avg_net_le_0")
                results[window][sizing][str(cost)] = {"ledger_key": key, "summary": summary, "coupled": coupled}
    reconciliation = reconcile_ledger_tree(ledgers)
    payload = {"version": "4.0.6", "fresh_oos": False, "funding": "EXCLUDED",
               "cost_model": "Flat total cost in bps of entry notional; same fill path in all cost scenarios",
               "statistical_scope": "Weekly cluster percentile intervals conditional on the tested candidates; not selection-adjusted hypothesis tests",
               "results": results, "monetary_reconciliation": reconciliation}
    (ART / "METHOD_PIT_COMPARISON_v4_0_6.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (ART / "METHOD_PIT_LEDGERS_v4_0_6.json").write_text(json.dumps({"ledgers_by_key": ledgers}, indent=2), encoding="utf-8")
    if not reconciliation["all_passed"]:
        raise AssertionError("PIT comparison monetary reconciliation failed")
    return {"artifact": "METHOD_PIT_COMPARISON_v4_0_6.json", "all_monetary_checks_passed": True}
