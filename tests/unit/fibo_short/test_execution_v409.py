import copy
from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"scripts/fibo_research"))
import execution_v409 as e
import funding_v409 as f
import research_v409 as research

T=int(e.r.utc("2024-01-01 00:05").timestamp())


def candidate(bars=None):
    bars=bars or [(T,100,105,95,100)]
    path=e.r.simulate_path(bars,100,110,[90,80,70])
    return {"id":"TEST:4h:entry","symbol":"TEST","tf":"4h","wave_key":"wave","entry_ts":T,"entry":100.,"stop":110.,"targets":[90.,80.,70.],
        "score":70.,"milestones":["m6_f4_sniper"],"paths":{"ladder":path},"missing_execution_bars":0}


def funding(events=()):
    rows=[{"funding_ts_ms":t,"funding_rate":rate,"mark_price":mark,"price_source":"funding_api_settlement_mark","mark_reference_ts_ms":t} for t,rate,mark in events]
    return {"TEST":{"times":np.array([x["funding_ts_ms"] for x in rows]),"events":rows}}


def run(c,scenario,events=()):
    return e.portfolio([c],{"gate":"expanded","sizing":"fixed"},"2024-01-01","2024-02-01",scenario,funding(events))


def partial_candidate():
    return candidate([(T,100,105,95,95),(T+300,95,96,89,89),(T+600,89,89,79,79),(T+900,79,79,69,75)])


@pytest.mark.parametrize("name,expected",[("standard_vip6",-.05),("stress_regular",-.22)])
def test_flat_roundtrip_charges_fee_and_slip_on_each_actual_fill(name,expected):
    result=run(candidate(),e.SCENARIOS[name])
    assert result["return_pct"]==pytest.approx(expected)
    p=result["ledger"][0]
    assert p["fills"][0]["execution_price"]<100<p["fills"][1]["execution_price"]
    assert sum(x["fee"] for x in p["fills"])==pytest.approx(result["fees_pct"])


def test_partial_exit_costs_follow_actual_reduced_quantity_and_turnover():
    c=partial_candidate()
    result=run(c,e.SCENARIOS["standard_vip6"])
    p=result["ledger"][0];fills=p["fills"]
    assert [x["qty"] for x in fills]==pytest.approx([.2,.1,.06,.04])
    assert [x["execution_price"] for x in fills]==pytest.approx([99.9,90.09,80.08,70.07])
    assert result["fees_pct"]==pytest.approx((19.98+9.009+4.8048+2.8028)*.00025)
    assert result["slippage_pct"]==pytest.approx(.0366)
    assert result["return_pct"]==pytest.approx(3.4-result["fees_pct"]-.0366)


def test_multiple_exits_same_bar_preserve_total_cost_via_weighted_price():
    c=candidate([(T,100,105,85,95)])
    # TP1 half at90, then stop remaining half at100: weighted reference95.
    rows=e.execution_steps(c)
    assert rows[0][-1]==pytest.approx(95.)
    result=run(c,e.SCENARIOS["standard_vip6"])
    assert result["ledger"][0]["fills"][1]["notional"]==pytest.approx(.1*90*1.001+.1*100*1.001)


def test_funding_sign_variable_intervals_and_partial_exposure():
    c=partial_candidate()
    events=[((T+100)*1000,.001,100.),((T+700)*1000,-.002,90.),((T+1000)*1000,.003,80.)]
    result=run(c,e.SCENARIOS["standard_vip6"],events)
    assert result["funding_pct"]==pytest.approx(.2*100*.001-.1*90*.002+.04*80*.003)
    assert [x["remaining_qty"] for x in result["ledger"][0]["funding_events"]]==pytest.approx([.2,.1,.04])


def test_exact_millisecond_funding_at_exit_before_fill_but_after_exit_excluded():
    c=candidate();end=(T+300)*1000
    result=run(c,e.SCENARIOS["standard_vip6"],[(T*1000,.001,100.),(end,.002,100.),(end+1,.1,100.)])
    assert result["funding_events"]==1
    assert result["funding_pct"]==pytest.approx(.04)


def test_cost_aware_stop_sizing_limits_modelled_loss_without_gap():
    for scenario in e.SCENARIOS.values():
        qty=e.quantity(100.,100.,102.,"risk",scenario)
        assert qty*e.stop_loss_per_unit(100.,102.,scenario)<=.5+1e-12
        assert qty*100<=20
    assert e.quantity(100.,100.,102.,"risk",e.SCENARIOS["stress_regular"])<e.quantity(100.,100.,102.,"risk",e.SCENARIOS["standard_vip6"])


def test_future_funding_changes_cannot_change_an_already_closed_trade():
    c=candidate();before=run(c,e.SCENARIOS["standard_vip6"])
    after=run(c,e.SCENARIOS["standard_vip6"],[((T+600)*1000,-.9,1000.)])
    assert before==after


def test_missing_funding_pack_fails_closed():
    with pytest.raises(KeyError):e.portfolio([candidate()],{"gate":"expanded","sizing":"fixed"},"2024-01-01","2024-02-01",e.SCENARIOS["standard_vip6"],{})


def test_funding_download_guard_forbids_2026_before_network(tmp_path):
    with pytest.raises(AssertionError):f.get_json(None,f.FUNDING_URL,{"startTime":f.START_MS,"endTime":f.LIMIT_MS},tmp_path)


def test_exit_turnover_reconciliation_rejects_corrupted_trace():
    c=candidate();c["paths"]["ladder"]["gross_return"]+=.01
    with pytest.raises(AssertionError):e.execution_steps(c)


def test_zero_cost_cash_matches_original_path_randomized():
    rng=np.random.default_rng(409)
    for _ in range(50):
        marks=100+np.cumsum(rng.normal(0,3,20));bars=[];prior=100.
        for i,mark in enumerate(marks):
            bars.append((T+i*300,prior,max(prior,mark)+2,min(prior,mark)-2,mark));prior=mark
        c=candidate(bars)
        result=run(c,{"fee_bps":0.,"slippage_bps":0.})
        assert result["return_pct"]==pytest.approx(20*c["paths"]["ladder"]["gross_return"])


def moved(symbol,t):
    c=candidate([(t,100,105,95,100),(t+300,100,105,95,100)])
    c.update(id=f"{symbol}:{t}",symbol=symbol,entry_ts=t)
    return c


def test_funding_changes_next_admission_quantity_not_just_final_pnl():
    a=moved("A",T);b=moved("B",T+200)
    no={s:{"times":np.array([]),"events":[]} for s in ("A","B")}
    credit=copy.deepcopy(no)
    credit["A"]=funding([((T+100)*1000,.01,100.)])["TEST"]
    args=([a,b],{"gate":"expanded","sizing":"fixed"},"2024-01-01","2024-02-01",e.SCENARIOS["standard_vip6"])
    first=e.portfolio(*args,no);second=e.portfolio(*args,credit)
    qty1=next(p["qty"] for p in first["ledger"] if p["symbol"]=="B")
    qty2=next(p["qty"] for p in second["ledger"] if p["symbol"]=="B")
    assert qty2>qty1
    assert qty2-qty1==pytest.approx(.0004)


def test_same_time_cap_and_rejected_wave_remains_available(monkeypatch):
    monkeypatch.setattr(e,"quantity",lambda *args:.1)
    source=[moved(s,T) for s in "ABCDEF"]+[moved("F",T+600)]
    pack={s:{"times":np.array([]),"events":[]} for s in "ABCDEF"}
    result=e.portfolio(source,{"gate":"expanded","sizing":"fixed"},"2024-01-01","2024-02-01",e.SCENARIOS["standard_vip6"],pack)
    assert result["rejected"]["portfolio_cap"]==1
    assert len(result["ledger"])==6
    assert next(p for p in result["ledger"] if p["symbol"]=="F")["entry_ts_ms"]==(T+600)*1000


def annual_fixture():
    metric={"return_pct":5.,"max_dd_pct":2.,"trades":35,"accepted_missing_execution_bars":0,"curve_values":[100.,98.,105.],
        "weekly_returns":[.01]*10,"gross_reference_pnl_pct":5.,"fees_pct":0.,"slippage_pct":0.,"funding_pct":0.}
    return {str(y):{s["id"]:{name:copy.deepcopy(metric) for name in e.SCENARIOS} for s in research.q.FAMILY} for y in range(2020,2026)}


def test_new_cost_selection_cannot_see_test_or_future_years():
    annual=annual_fixture();before=research.choose(annual,2022)
    for y in range(2022,2026):annual[str(y)]={"future":999999}
    assert research.choose(annual,2022)==before
    assert before["selected"]=="elite_sniper_risk"


def test_linked_fee_slippage_funding_attribution_reconciles_with_compounding():
    node={"standard_vip6":{"return_pct":5.,"max_dd_pct":0.,"trades":1,"accepted_missing_execution_bars":0,"curve_values":[100.,105.],
        "weekly_returns":[.05],"gross_reference_pnl_pct":8.,"fees_pct":1.,"slippage_pct":3.,"funding_pct":1.}}
    result=research.linked([node,node],"standard_vip6")
    assert result["return_pct"]==pytest.approx(10.25)
    assert result["gross_reference_pnl_pct"]-result["fees_pct"]-result["slippage_pct"]+result["funding_pct"]==pytest.approx(10.25)
