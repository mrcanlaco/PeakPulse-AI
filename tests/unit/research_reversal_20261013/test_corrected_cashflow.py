import copy

import pytest

from scripts.research_reversal_20261013 import experiment_corrected as e


def event(same_boundary=False):
    quantity = 3. if same_boundary else 1.
    funding = quantity*.01
    base = {"eligible":True,"gross_return_planned":.1,"costs_planned":.001,
        "funding_planned":funding,"net_return_planned":.099+funding,
        "fills":[{"timestamp":"2026-01-01T01:00:00Z","quantity":1.},
            {"timestamp":"2026-01-01T02:00:00Z" if same_boundary else "2026-01-01T02:05:00Z","quantity":2.}],
        "exit_time":"2026-01-01T03:00:00Z",
        "funding_payments":[{"timestamp":"2026-01-01T02:00:00Z","quantity":quantity,
            "mark_price":100.,"rate":.0001,"cash_flow":funding}]}
    return {"variants":{"compact":base,"compact_cost2x":copy.deepcopy(base)}}


@pytest.mark.parametrize("same_boundary", [False, True])
def test_settlement_includes_previous_candle_fill_but_excludes_next_candle(same_boundary):
    x = event(same_boundary)
    net = x["variants"]["compact"]["net_return_planned"]
    assert e.check_cashflows(x,net)==net


def test_next_candle_fill_must_not_be_counted_in_earlier_settlement():
    x = event(False)
    x["variants"]["compact"]["funding_payments"][0]["quantity"] = 3.
    with pytest.raises(RuntimeError, match="Funding quantity"):
        e.check_cashflows(x,.109)


def test_corrected_module_preserves_all_hypothesis_definitions():
    from scripts.research_reversal_20261013 import experiment as original
    assert e.RULES == original.RULES
    assert e.VARIANTS == original.VARIANTS
