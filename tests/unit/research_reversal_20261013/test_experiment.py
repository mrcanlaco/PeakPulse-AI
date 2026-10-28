"""Synthetic adversarial checks for the bounded offline reversal experiment."""
import copy

import pandas as pd
import pytest

from scripts.research_reversal_20261013 import experiment_corrected as e


T = pd.Timestamp("2026-01-01T12:00:00Z")


def frame(hours=6):
    ts = pd.date_range(T-pd.Timedelta(hours=hours), T, freq="5min")
    return pd.DataFrame({"close_time": ts-pd.Timedelta(milliseconds=1),
        "open": 100., "high": 101., "low": 99., "close": 100.})


def retest_frame():
    x = frame()
    x.loc[1:24, ["open", "close", "high", "low"]] = [110.,110.,120.,109.]
    x.loc[25:48, ["open", "close", "high", "low"]] = [100.,100.,102.,99.]
    x.loc[49:60, ["open", "close", "high", "low"]] = [105.,105.,108.,104.]
    x.loc[61:72, ["open", "close", "high", "low"]] = [103.,103.,106.,102.]
    return x


def test_window_uses_closed_bars_and_future_mutation_cannot_change_gate():
    x = retest_frame()
    future = frame().iloc[[-1]].copy()
    future["close_time"] += pd.Timedelta(minutes=5)
    future["high"] = 99999.
    first, error = e.validate_window(x, T)
    second, error2 = e.validate_window(pd.concat([future,x]), T)
    assert error is error2 is None
    assert e.failed_retest(first) is True
    pd.testing.assert_frame_equal(first,second)


@pytest.mark.parametrize("failure", ["gap", "duplicate", "nan", "negative", "inconsistent", "offgrid"])
def test_invalid_windows_are_missing_not_flat(failure):
    x = frame()
    if failure == "gap":
        x = x.drop(index=35)
    elif failure == "duplicate":
        x = pd.concat([x,x.iloc[[35]]])
    elif failure == "nan":
        x.loc[35,"high"] = float("nan")
    elif failure == "negative":
        x.loc[35,"low"] = -1.
    elif failure == "inconsistent":
        x.loc[35,"high"] = 90.
    else:
        x.loc[35,"close_time"] += pd.Timedelta(seconds=1)
    observed, error = e.validate_window(x,T)
    assert observed is None and error


def test_last_open_bar_cannot_be_read_as_closed():
    x = frame()
    x.loc[72,"close_time"] += pd.Timedelta(minutes=5)
    assert e.validate_window(x,T)[0] is None


def test_anchor_fixed_and_equal_high_is_not_failed_retest():
    x, _ = e.validate_window(retest_frame(),T)
    assert e.failed_retest(x)
    x.loc[55,"high"] = 120.
    assert not e.failed_retest(x)


def test_btc_weakness_can_differ_from_negative_absolute_return():
    coin,_ = e.validate_window(frame(),T)
    btc,_ = e.validate_window(frame(1),T,1)
    coin.loc[72,"close"] = 100.5
    btc.loc[12,"close"] = 101.
    measures,g = e.measure(coin,btc,.005)
    assert not g["A_negative_1h"] and g["R_weaker_BTC_1h"]
    assert not g["AR"] and measures["relative_return_1h"] < 0


def test_equality_not_weakness_and_missing_btc_stays_unknown():
    coin,_ = e.validate_window(frame(),T)
    btc,_ = e.validate_window(frame(1),T,1)
    assert e.measure(coin,btc,0.)[1]["R_weaker_BTC_1h"] is False
    assert e.measure(coin,None,0.)[1]["R_weaker_BTC_1h"] is None


def row(sid, net, selected=True, funded=True, complete=True):
    return {"source_event_id":sid, "symbol":sid, "financially_eligible":funded,
        "features_complete":complete, "feature_exclusions":[] if complete else ["BTC:gap"],
        "gates":{v:True if v=="baseline" else selected for v in e.VARIANTS},
        "net":net, "net_cost2x":net-.001 if funded else None, "status":"stop" if net and net < 0 else "target"}


def test_same_opportunity_denominator_and_unknown_finance_not_zero_filled():
    out = e.aggregate([row("a",.1),row("b",-.2,False),row("c",None,funded=False),row("d",.5,complete=False)])
    assert out["common_opportunities"]==2
    assert out["financially_excluded"]==1 and out["funded_feature_excluded"]==1
    assert out["variants"]["baseline"]["opportunity_mean"]==pytest.approx(-.05)
    assert out["variants"]["A_negative_1h"]["opportunity_mean"]==pytest.approx(.05)
    assert out["variants"]["A_negative_1h"]["selected_only_mean"]==.1


def cashflow_event():
    base = {"eligible":True,"gross_return_planned":.1,"costs_planned":.001,
        "funding_planned":.01,"net_return_planned":.109,
        "fills":[{"timestamp":"2026-01-01T01:00:00Z","quantity":1.},
            {"timestamp":"2026-01-01T02:05:00Z","quantity":2.}],
        "exit_time":"2026-01-01T03:00:00Z",
        "funding_payments":[{"timestamp":"2026-01-01T02:00:00Z","quantity":1.,"mark_price":100.,"rate":.0001,"cash_flow":.01}]}
    return {"variants":{"compact":base,"compact_cost2x":copy.deepcopy(base)}}


def test_funding_excludes_next_candle_add():
    assert e.check_cashflows(cashflow_event(),.109)==.109


@pytest.mark.parametrize("mutation",["future_quantity","after_exit","entry_funding","wrong_net","wrong_cash"])
def test_bad_financial_evidence_aborts(mutation):
    x = cashflow_event()
    b = x["variants"]["compact"]
    if mutation == "future_quantity": b["funding_payments"][0]["quantity"] = 3.
    elif mutation == "after_exit": b["funding_payments"][0]["timestamp"] = "2026-01-01T04:00:00Z"
    elif mutation == "entry_funding": b["funding_payments"][0]["timestamp"] = "2026-01-01T01:00:00Z"
    elif mutation == "wrong_net": b["net_return_planned"] = .2
    else: b["funding_payments"][0]["cash_flow"] = .02
    with pytest.raises(RuntimeError): e.check_cashflows(x,.109)


def test_hash_change_aborts(tmp_path):
    path = tmp_path/"source.json"
    path.write_text("old")
    hashes = {str(path):e.digest(path)}
    e.verify(hashes)
    path.write_text("changed")
    with pytest.raises(RuntimeError): e.verify(hashes)


def test_missing_data_no_selected_mean_and_no_false_flat_NAV():
    out = e.aggregate([row("x",None,funded=False)])
    assert out["common_opportunities"]==0
    assert out["variants"]["baseline"]["opportunity_mean"] is None
    assert out["variants"]["baseline"]["selected_only_mean"] is None
