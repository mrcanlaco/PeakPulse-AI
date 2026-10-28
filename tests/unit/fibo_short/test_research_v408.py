"""Boundaries and chronological policy selection for the six-year replay."""
import copy
from pathlib import Path
import sys
import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"scripts/fibo_research"))
import research_v408 as q


def candles(times,values):
    return pd.DataFrame({"open_time":pd.to_datetime(times,utc=True,format="mixed"),
        **{k:values for k in ["open","high","low","close","volume","quote_volume"]}})


def test_six_year_loader_preserves_join_and_excludes_2026(tmp_path):
    old=tmp_path/"old.parquet";new=tmp_path/"new.parquet"
    candles(["2019-12-31","2020-01-01","2023-12-31 23:55","2024-01-01"],[999.,1.,2.,999.]).to_parquet(old,index=False)
    candles(["2023-12-31 23:55","2024-01-01","2025-12-31 23:55","2026-01-01"],[999.,3.,4.,999.]).to_parquet(new,index=False)
    merged=q.validate_frame([q.load_segment(old,q.START,q.JOIN),q.load_segment(new,q.JOIN,q.END)])
    assert merged.close.tolist()==[1.,2.,3.,4.]
    assert merged.index.min()==q.START and merged.index.max()<q.END
    with pytest.raises(ValueError):q.load_segment(new,q.START,"2026-01-02")


def test_merge_rejects_conflicts_but_deduplicates_identical_observations():
    first=candles(["2020-01-01"],[10.])
    assert len(q.validate_frame([first,first]))==1
    with pytest.raises(ValueError,match="Conflicting"):
        q.validate_frame([first,candles(["2020-01-01"],[20.])])


def test_early_universe_needs_observed_past_and_cannot_see_next_month():
    ix=pd.date_range("2020-01-01",periods=24*100,freq="h",tz="UTC")
    frame=pd.DataFrame(1.,index=ix,columns=["open","high","low","close","volume","quote_volume"])
    months=pd.to_datetime(["2020-01-01","2020-02-01","2020-03-01"],utc=True)
    baseline=q.r.monthly_rows("TESTUSDT",frame,months)
    assert list(baseline)==["2020-03"]
    frame.loc[frame.index>=months[-1],"quote_volume"]=1e15
    assert q.r.monthly_rows("TESTUSDT",frame,months)==baseline


def annual_fixture():
    metric={"return_pct":5.,"max_dd_pct":2.,"trades":35,"accepted_missing_execution_bars":0,"curve_values":[100.,98.,105.]}
    return {str(y):{s["id"]:{f"{c}bps_stress":copy.deepcopy(metric) for c in (40,60)} for s in q.FAMILY} for y in range(2020,2026)}


def test_selection_is_unchanged_by_test_year_and_future_results():
    annual=annual_fixture();before=q.choose_from_past(annual,2022)
    assert before["selected"]=="elite_sniper_risk"  # Stable tie order.
    for year in range(2022,2026):annual[str(year)]={"future":-1e100}
    assert q.choose_from_past(annual,2022)==before
    assert before["training_years"]==["2020","2021"]


@pytest.mark.parametrize("reason",["losing_year","few_trades","gaps","drawdown","cost"])
def test_cash_fallback_when_no_risky_policy_qualifies(reason):
    annual=annual_fixture()
    for s in q.FAMILY:
        node=annual["2021"][s["id"]]
        if reason=="losing_year":node["40bps_stress"]["return_pct"]=-1.
        if reason=="few_trades":node["40bps_stress"]["trades"]=1
        if reason=="gaps":node["60bps_stress"]["accepted_missing_execution_bars"]=1
        if reason=="drawdown":node["60bps_stress"]["max_dd_pct"]=15.01
        if reason=="cost":node["60bps_stress"].update(return_pct=-10.,curve_values=[100.,90.])
    assert q.choose_from_past(annual,2022)["selected"]=="CASH"


def test_selection_needs_complete_two_year_training():
    with pytest.raises(ValueError):q.choose_from_past(annual_fixture(),2021)
    annual=annual_fixture();del annual["2020"]
    with pytest.raises(ValueError):q.choose_from_past(annual,2022)


def test_linking_compounds_nav_and_preserves_cross_year_drawdown():
    a={"40bps_stress":{"return_pct":10.,"curve_values":[100.,120.,110.],"trades":2,"accepted_missing_execution_bars":0}}
    b={"40bps_stress":{"return_pct":-10.,"curve_values":[100.,90.],"trades":3,"accepted_missing_execution_bars":1}}
    linked=q.linked_summary([a,b],40)
    assert linked["return_pct"]==pytest.approx(-1.)
    assert linked["max_dd_pct"]==pytest.approx((1-99/120)*100)
    assert linked["trades"]==5 and linked["accepted_missing_execution_bars"]==1
