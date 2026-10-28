import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("alpha_combine", Path(__file__).resolve().parents[3] / "scripts/research_branches_20261013/combine_branches.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)
CONTRACT = {"start_date": "2026-01-01", "end_date": "2026-01-03", "valuation_convention": "daily_close_utc", "normalization": "first_daily_close_10000"}


def curve(branch, values):
    return {"branch": branch, "is_baseline": True, "metric_basis": "account_equity", "diagnostic_combination_eligible": True,
            "eligible_for_combination": False, "funding_coverage_verified": False,
            "valuation_convention": "daily_close_utc", "normalization": "first_daily_close_10000",
            "rows": [{"date": f"2026-01-0{i+1}", "equity": v} for i, v in enumerate(values)]}


def test_static_capital_not_daily_rebalanced():
    a, b = curve("trend", [10000, 20000, 10000]), curve("flow", [10000, 10000, 20000])
    result = mod.mix({"trend": a, "flow": b}, {"trend": .5, "flow": .5}, CONTRACT)
    assert [r["equity"] for r in result["rows"]] == [10000, 15000, 15000]
    assert result["metrics"]["total_return"] == .5
    assert not result["financial_inputs_verified"]
    assert not result["independent_alpha_verified"]


@pytest.mark.parametrize("field,value,error", [
    ("metric_basis", "mean_event_return", "not_account_equity"),
    ("diagnostic_combination_eligible", False, "not_diagnostic"),
    ("is_baseline", False, "not_predeclared"),
    ("valuation_convention", "daily_open", "incompatible"),
    ("branch", "v3", "identity"),
])
def test_contract_fail_closed(field, value, error):
    a = curve("trend", [10000, 11000, 12000])
    a[field] = value
    with pytest.raises(ValueError, match=error):
        mod.validate_curve(a, "trend", CONTRACT)


def test_missing_date_is_not_imputed():
    a = curve("trend", [10000, 11000, 12000])
    a["rows"].pop(1)
    with pytest.raises(ValueError, match="calendar"):
        mod.validate_curve(a, "trend", CONTRACT)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0, -10, True, "10000"])
def test_bad_equity_requires_audit(value):
    a = curve("trend", [10000, value, 12000])
    with pytest.raises(ValueError):
        mod.validate_curve(a, "trend", CONTRACT)


def test_constant_sleeve_correlation_is_unknown_not_zero():
    result = mod.mix({"trend": curve("trend", [10000, 10000, 10000]), "flow": curve("flow", [10000, 11000, 12000])}, {"trend": .5, "flow": .5}, CONTRACT)
    assert result["daily_return_correlations"]["trend__flow"] is None


def test_weights_cannot_create_extra_capital():
    with pytest.raises(ValueError, match="weights"):
        mod.mix({}, {"trend": .7, "flow": .7}, CONTRACT)
