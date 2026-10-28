"""Regression contracts for the bounded annual execution-feasibility audit."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "audit_annual_execution.py"


def _load_helper():
    spec = importlib.util.spec_from_file_location("test_audit_annual_execution_impl", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _symbol(
    helper,
    *,
    symbol: str = "ALTUSDT",
    lot_min: str = "1",
    lot_max: str = "10",
    lot_step: str = "0.1",
    market_min: str | None = None,
    market_max: str | None = None,
    market_step: str | None = None,
    min_notional: str = "1",
    filters_override: list[dict[str, str]] | None = None,
):
    market_min = market_min or lot_min
    market_max = market_max or lot_max
    market_step = market_step or lot_step
    filters = filters_override or [
        {
            "filterType": "LOT_SIZE",
            "minQty": lot_min,
            "maxQty": lot_max,
            "stepSize": lot_step,
        },
        {
            "filterType": "MARKET_LOT_SIZE",
            "minQty": market_min,
            "maxQty": market_max,
            "stepSize": market_step,
        },
        {"filterType": "MIN_NOTIONAL", "notional": min_notional},
    ]
    return {"symbol": symbol, "filters": filters}


def _leg(*, symbol: str = "ALTUSDT", margin: str = "5", price: str = "1"):
    return {
        "symbol": symbol,
        "direction": "long",
        "entry_price": price,
        "margin_usd": margin,
        "margin_weight": 1,
    }


def test_decimal_floor_accepts_fractional_and_scientific_steps():
    helper = _load_helper()

    assert helper.floor_to_step(Decimal("1.2345"), Decimal("1e-3")) == Decimal("1.234")
    assert helper.compatible_step([Decimal("0.1"), Decimal("6e-2")]) == Decimal("0.3")
    assert helper.floor_to_step(Decimal("1.01"), helper.compatible_step(["0.1", "6e-2"])) == Decimal(
        "0.9"
    )


def test_minimum_boundary_zero_and_upper_bound_are_not_silently_passed():
    helper = _load_helper()
    symbol = _symbol(helper)

    minimum = helper.audit_leg(_leg(margin="1"), Decimal("1"), symbol)
    below_minimum = helper.audit_leg(_leg(margin="0.9"), Decimal("1"), symbol)
    zero = helper.audit_leg(_leg(margin="0"), Decimal("1"), symbol)
    maximum = helper.audit_leg(_leg(margin="10"), Decimal("1"), symbol)
    above_maximum = helper.audit_leg(_leg(margin="10.1"), Decimal("1"), symbol)

    assert minimum["status"] == helper.STATUS_FEASIBLE
    assert minimum["floored_quantity"] == "1"
    assert below_minimum["status"] == helper.STATUS_REJECTED
    assert "quantity_below_min_qty" in below_minimum["reason_codes"]
    assert zero["status"] == helper.STATUS_REJECTED
    assert zero["floored_quantity"] == "0"
    assert "quantity_zero_after_step_floor" in zero["reason_codes"]
    assert maximum["status"] == helper.STATUS_FEASIBLE
    assert above_maximum["status"] == helper.STATUS_REJECTED
    assert "quantity_above_max_qty" in above_maximum["reason_codes"]


def test_market_lot_and_lot_size_are_both_enforced_with_common_step():
    helper = _load_helper()
    symbol = _symbol(
        helper,
        lot_min="0.1",
        lot_max="100",
        lot_step="0.1",
        market_min="0.18",
        market_max="100",
        market_step="0.06",
        min_notional="0.1",
    )

    audit = helper.audit_leg(_leg(margin="1.01"), Decimal("1"), symbol)

    assert audit["status"] == helper.STATUS_FEASIBLE
    assert audit["lot_size_compatibility"]["common_step_size"] == "0.3"
    assert audit["floored_quantity"] == "0.9"
    assert audit["filter_status"] == {
        "LOT_SIZE": "valid",
        "MARKET_LOT_SIZE": "valid",
        "MIN_NOTIONAL": "valid",
    }


def test_shifted_min_qty_grid_is_unknown():
    helper = _load_helper()
    symbol = _symbol(
        helper,
        lot_min="0.05",
        lot_max="10",
        lot_step="0.1",
        market_min="0.05",
        market_max="10",
        market_step="0.1",
        min_notional="0.1",
    )

    audit = helper.audit_leg(_leg(margin="0.2"), Decimal("1"), symbol)

    assert audit["status"] == helper.STATUS_UNKNOWN
    assert audit["filter_status"]["LOT_SIZE"] == helper.STATUS_UNKNOWN
    assert audit["filter_status"]["MARKET_LOT_SIZE"] == helper.STATUS_UNKNOWN
    assert "unsupported_shifted_grid:LOT_SIZE" in audit["reason_codes"]
    assert "unsupported_shifted_grid:MARKET_LOT_SIZE" in audit["reason_codes"]


@pytest.mark.parametrize("max_qty", ["0", "-1"])
def test_non_positive_max_qty_is_unknown(max_qty):
    helper = _load_helper()
    symbol = _symbol(helper, lot_max=max_qty, market_max="10")

    audit = helper.audit_leg(_leg(), Decimal("1"), symbol)

    assert audit["status"] == helper.STATUS_UNKNOWN
    assert audit["filter_status"]["LOT_SIZE"] == helper.STATUS_UNKNOWN
    assert "invalid_filter:LOT_SIZE" in audit["reason_codes"]


def test_missing_symbol_and_missing_or_invalid_filters_are_unknown_not_pass():
    helper = _load_helper()
    leg = _leg()

    missing_symbol = helper.audit_leg(leg, Decimal("1"), None)
    missing_filter = helper.audit_leg(leg, Decimal("1"), {"symbol": "ALTUSDT", "filters": []})
    invalid_filter = helper.audit_leg(
        leg,
        Decimal("1"),
        _symbol(
            helper,
            filters_override=[
                {
                    "filterType": "LOT_SIZE",
                    "minQty": "1",
                    "maxQty": "10",
                    "stepSize": "0",
                },
                {
                    "filterType": "MARKET_LOT_SIZE",
                    "minQty": "1",
                    "maxQty": "10",
                    "stepSize": "0.1",
                },
                {"filterType": "MIN_NOTIONAL", "notional": "1"},
            ],
        ),
    )

    assert missing_symbol["status"] == helper.STATUS_UNKNOWN
    assert "missing_symbol" in missing_symbol["reason_codes"]
    assert missing_filter["status"] == helper.STATUS_UNKNOWN
    assert "missing_filter:LOT_SIZE" in missing_filter["reason_codes"]
    assert "missing_filter:MIN_NOTIONAL" in missing_filter["reason_codes"]
    assert invalid_filter["status"] == helper.STATUS_UNKNOWN
    assert "invalid_filter:LOT_SIZE" in invalid_filter["reason_codes"]


def test_hedge_uses_recorded_half_margin_and_requires_both_legs():
    helper = _load_helper()
    symbols = {
        "ALTUSDT": _symbol(helper, min_notional="1"),
        "BTCUSDT": _symbol(
            helper,
            symbol="BTCUSDT",
            lot_min="0.001",
            lot_max="100",
            lot_step="0.001",
            min_notional="1",
        ),
    }
    legs = [
        _leg(symbol="ALTUSDT", margin="5", price="1"),
        _leg(symbol="BTCUSDT", margin="5", price="100"),
    ]

    audits, status, _ = helper.audit_trade(legs, Decimal("2"), symbols, hedge=True)

    assert status == helper.STATUS_FEASIBLE
    assert [audit["margin_usd"] for audit in audits] == ["5", "5"]
    assert [audit["raw_notional_usd"] for audit in audits] == ["10", "10"]
    assert [audit["margin_basis"] for audit in audits] == [
        "recorded leg margin; hedge half-margin is not split again",
        "recorded leg margin; hedge half-margin is not split again",
    ]

    missing_btc, hedge_status, _ = helper.audit_trade(
        legs,
        Decimal("2"),
        {"ALTUSDT": symbols["ALTUSDT"]},
        hedge=True,
    )
    assert len(missing_btc) == 2
    assert hedge_status == helper.STATUS_UNKNOWN
    assert missing_btc[1]["status"] == helper.STATUS_UNKNOWN


def test_audit_leg_does_not_mutate_input():
    helper = _load_helper()
    leg = _leg(margin="5.00")
    symbol = _symbol(helper)
    original_leg = copy.deepcopy(leg)
    original_symbol = copy.deepcopy(symbol)

    helper.audit_leg(leg, Decimal("2"), symbol)

    assert leg == original_leg
    assert symbol == original_symbol


def test_run_audit_preserves_inputs_writes_raw_snapshot_and_refuses_overwrite(tmp_path):
    helper = _load_helper()
    exchange_info = {
        "timezone": "UTC",
        "serverTime": 1789689661605,
        "futuresType": "U_MARGINED",
        "symbols": [_symbol(helper)],
    }
    executed = {
        "candidate_id": "T:ALTUSDT:1",
        "trial_id": "T__c20__withdraw",
        "strategy_id": "T",
        "entry_time": "2026-09-01T00:05:00Z",
        "legs": [_leg(margin="5")],
    }
    trial_definitions = [
        {
            "trial_id": "T__c20__withdraw",
            "strategy_id": "T",
            "leverage": 2,
            "hedge_btc": False,
        }
    ]
    accounts = {"trials": [{"trial_id": "T__c20__withdraw"}], "status": "provisional"}
    exchange_path = tmp_path / "exchange_info.json"
    executed_path = tmp_path / "executed.jsonl"
    trials_path = tmp_path / "trials.json"
    accounts_path = tmp_path / "accounts.json"
    output_dir = tmp_path / "audit"
    exchange_bytes = json.dumps(exchange_info, separators=(",", ":")).encode("utf-8")
    executed_bytes = (json.dumps(executed) + "\n").encode("utf-8")
    trial_bytes = json.dumps(trial_definitions).encode("utf-8")
    account_bytes = json.dumps(accounts).encode("utf-8")
    exchange_path.write_bytes(exchange_bytes)
    provenance = {
        "retrieved_at_utc": "2026-09-18T02:16:27.6921243Z",
        "sha256": hashlib.sha256(exchange_bytes).hexdigest(),
        "purpose": "current-rule audit only",
    }
    provenance_bytes = json.dumps(provenance).encode("utf-8")
    exchange_path.with_suffix(".provenance.json").write_bytes(provenance_bytes)
    executed_path.write_bytes(executed_bytes)
    trials_path.write_bytes(trial_bytes)
    accounts_path.write_bytes(account_bytes)

    summary = helper.run_audit(
        exchange_info_path=exchange_path,
        output_dir=output_dir,
        executed_legs_path=executed_path,
        accounts_path=accounts_path,
        trial_definitions_path=trials_path,
        protocol_path=tmp_path / "missing_protocol.md",
        findings_path=tmp_path / "missing_findings.md",
    )

    assert summary["counts"]["executed_records"] == 1
    assert summary["counts"]["executed_legs"] == 1
    assert summary["counts"]["leg_status_counts"][helper.STATUS_FEASIBLE] == 1
    assert summary["exchange_info_snapshot"]["retrieved_at_utc"] == "2026-09-18T02:16:27.6921243Z"
    assert (output_dir / helper.RAW_SNAPSHOT).read_bytes() == exchange_bytes
    assert (output_dir / helper.RAW_PROVENANCE).read_bytes() == provenance_bytes
    assert executed_path.read_bytes() == executed_bytes
    assert trials_path.read_bytes() == trial_bytes
    assert accounts_path.read_bytes() == account_bytes

    with pytest.raises(helper.OutputExistsError):
        helper.run_audit(
            exchange_info_path=exchange_path,
            output_dir=output_dir,
            executed_legs_path=executed_path,
            accounts_path=accounts_path,
            trial_definitions_path=trials_path,
            protocol_path=tmp_path / "missing_protocol.md",
            findings_path=tmp_path / "missing_findings.md",
        )


def test_missing_retrieval_timestamp_is_unavailable_not_file_mtime(tmp_path):
    helper = _load_helper()
    snapshot_path = tmp_path / "exchange_info.json"
    snapshot_path.write_text("{}", encoding="utf-8")

    metadata = helper._snapshot_timestamp(snapshot_path, {}, None)

    assert metadata["retrieved_at_utc"] is None
    assert metadata["retrieval_timestamp_source"] == "unavailable"


def test_missing_leverage_fails_closed(tmp_path):
    helper = _load_helper()
    trial_path = tmp_path / "trials.json"
    trial_path.write_text(json.dumps([{"trial_id": "T"}]), encoding="utf-8")
    with pytest.raises(helper.AuditInputError, match="leverage"):
        helper._load_trial_definitions(trial_path)
