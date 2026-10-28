"""Independent monetary checks, beyond equality of trade IDs and hashes."""

from collections import Counter
import math
from typing import Any


def reconcile_settled_ledger(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Check fully settled trades against their standalone net return and funding.

    PnL includes fees and funding. net_return_pct includes fees and position sizing,
    so divide by pos_mult before applying the actual entry notional. A mark of an
    open trade must not be passed off as a fully settled trade in this interface.
    Tolerance accounts for the existing four-decimal artifact serialization.
    """
    errors = []
    ids = [r["trade_id"] for r in records]
    duplicates = [key for key, count in Counter(ids).items() if count > 1]
    for record in records:
        mult = float(record["pos_mult"])
        if not math.isfinite(mult) or mult <= 0:
            errors.append({"trade_id": record["trade_id"], "reason": "invalid_multiplier"})
            continue
        net = float(record["net_return_pct"])
        for basis in ("add", "comp"):
            notional = float(record[f"n0_{basis}"])
            funding = float(record.get(f"funding_dollar_{basis}", 0.0))
            actual = float(record[f"realized_pnl_dollar_{basis}"])
            expected = notional * net / mult / 100.0 + funding
            tolerance = 0.00015 + 0.00005 * (abs(net / mult / 100.0) + abs(notional / mult / 100.0))
            if not all(map(math.isfinite, (net, notional, funding, actual, expected))) or abs(actual - expected) > tolerance:
                errors.append({
                    "trade_id": record["trade_id"], "basis": basis,
                    "actual": actual, "expected": expected,
                    "difference": actual - expected, "tolerance": tolerance,
                })
    return {"records_checked": len(records), "duplicate_ids": duplicates,
            "errors": errors, "all_passed": not errors and not duplicates}


def reconcile_ledger_tree(ledgers: dict[str, Any]) -> dict[str, Any]:
    results = {}

    def visit(node: Any, path: str) -> None:
        if not isinstance(node, dict):
            return
        if "ledger_records" in node:
            results[path] = reconcile_settled_ledger(node["ledger_records"])
        for key, value in node.items():
            if isinstance(value, dict):
                visit(value, f"{path}/{key}")

    visit(ledgers, "")
    return {"ledger_count": len(results), "all_passed": bool(results) and all(r["all_passed"] for r in results.values()), "results": results}
