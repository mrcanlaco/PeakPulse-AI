"""Financial and time-boundary controls for the pre-2026 research branch."""
import copy
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts/fibo_research"))
import research_v407 as r

START = "2024-01-01"
END = "2024-02-01"
T = int(r.utc(START).timestamp())


def candidate(symbol="TEST", when=T, bars=None, stop=110):
    if bars is None:
        bars = [(when, 100, 105, 95, 100)]
    paths = {mode: r.simulate_path(bars, 100, stop, [90, 80, 70], mode) for mode in ("ladder", "tp1")}
    return {"id": f"{symbol}:{when}", "symbol": symbol, "tf": "4h", "wave_key": "wave",
            "entry_ts": when, "decision_ts": when-300, "entry": 100, "stop": stop,
            "score": 70, "milestones": ["m4_f2_elite", "m6_f4_sniper"], "btc_weak": True,
            "rr1": 1, "missing_execution_bars": 0, "paths": paths}


def variant(mode="fixed", exit_mode="ladder"):
    return {"gate": "expanded", "sizing": mode, "exit": exit_mode}


def test_loader_never_materializes_2026(tmp_path):
    times = pd.to_datetime(["2024-01-01", "2025-12-31 23:55:00", "2026-01-01"], utc=True, format="mixed")
    frame = pd.DataFrame({"open_time": times, **{k: [1., 2., 999.] for k in ["open", "high", "low", "close", "volume", "quote_volume"]}})
    p = tmp_path / "bars.parquet"
    frame.to_parquet(p, index=False)
    bounded = r.bounded_5m(p, "2026-01-01")
    assert len(bounded) == 2
    assert bounded.close.max() == 2
    assert len(r.bounded_5m(p, "2025-01-01")) == 1
    with pytest.raises(ValueError, match="forbidden"):
        r.bounded_5m(p, "2026-01-02")


def test_conflicting_duplicate_is_not_silently_selected(tmp_path):
    frame = pd.DataFrame({"open_time": [r.utc(START)]*2, **{k: [1., 2.] for k in ["open", "high", "low", "close", "volume", "quote_volume"]}})
    p = tmp_path / "bars.parquet"
    frame.to_parquet(p, index=False)
    with pytest.raises(ValueError, match="Conflicting"):
        r.bounded_5m(p, "2025-01-01")


def test_incomplete_hour_is_not_a_signal_candle():
    ix = pd.date_range(START, periods=24, freq="5min", tz="UTC")
    df = pd.DataFrame(1., index=ix, columns=["open", "high", "low", "close", "volume", "quote_volume"])
    assert len(r.h1_frame(df)) == 2
    assert len(r.h1_frame(df.drop(ix[3]))) == 1


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_timestamp_resolution_does_not_change_execution_lookup(unit):
    index = pd.DatetimeIndex([r.utc(START), r.utc(START)+pd.Timedelta(minutes=5)]).as_unit(unit)
    assert r.epoch_seconds(index).tolist() == [T, T+300]


def test_stop_gap_uses_first_available_adverse_price():
    path = r.simulate_path([(T, 120, 125, 85, 90)], 100, 110, [90,80,70])
    assert path["gross_return"] == pytest.approx(-.20)
    assert path["exit_reason"] == "stop"


def test_same_bar_stop_dominates_profit():
    path = r.simulate_path([(T, 100, 111, 60, 80)], 100, 110, [90,80,70])
    assert path["gross_return"] == pytest.approx(-.10)


def test_tp1_only_closes_all_quantity_immediately():
    path = r.simulate_path([(T, 100, 105, 85, 95), (T+300,95,120,80,115)], 100, 110, [90,80,70], "tp1")
    assert path["gross_return"] == pytest.approx(.10)
    assert path["exit_ts"] == T+300
    assert path["trace"][-1][3] == 0


def test_ladder_ratchet_checks_same_bar_high():
    path = r.simulate_path([(T, 100, 105, 85, 95)], 100, 110, [90,80,70])
    assert path["gross_return"] == pytest.approx(.05)
    assert path["exit_reason"] == "ratchet"


def test_round_trip_fixed_quantity_has_only_cost_loss():
    c = candidate(stop=110, bars=[(T,100,101,95,97),(T+300,97,101,95,100)])
    result = r.portfolio([c], variant(), START, END, 20, False)
    assert result["return_pct"] == pytest.approx(-.04)
    assert result["ledger"][0]["qty"] == pytest.approx(.2)


@pytest.mark.parametrize("cost", [0,20,40,60])
def test_actual_cost_is_charged_once(cost):
    result = r.portfolio([candidate()], variant(), START, END, cost, False)
    assert result["return_pct"] == pytest.approx(-20*cost/10000)
    assert result["fees_pct_initial"] == pytest.approx(20*cost/10000)
    assert result["all_cash_reconciled"]


def test_same_timestamp_admission_obeys_total_notional():
    result = r.portfolio([candidate(str(i)) for i in range(6)], variant(), START, END, 0, False)
    assert result["trades"] == 5
    assert result["rejected"]["portfolio_cap"] == 1


def test_risk_sizing_includes_prespecified_stress_cost():
    frac = r.position_fraction(100, 120, "risk")
    assert frac*(.20+.006) == pytest.approx(.005)
    assert r.position_fraction(100,100.5,"risk") == .2


def test_cap_rejection_does_not_consume_wave():
    initial = [candidate(f"A{i}", bars=[(T,100,105,95,100)]) for i in range(5)]
    rejected = candidate("ZZ", when=T)
    retried = candidate("ZZ", when=T+300)
    result = r.portfolio(initial+[rejected,retried], variant(), START, END, 0, False)
    assert result["trades"] == 6
    assert retried["id"] in {p["id"] for p in result["ledger"]}


def test_funding_debit_uses_quantity_and_boundary_exposure():
    c = candidate(when=T+8*3600-300)
    result = r.portfolio([c], variant(), START, END, 0, True)
    assert result["funding_pct_initial"] == pytest.approx(-.002)
    assert result["return_pct"] == pytest.approx(-.002)


def test_tail_embargo_prevents_cross_split_labels():
    t = int(r.utc(END).timestamp())-86400
    assert r.portfolio([candidate(when=t)], variant(), START, END)["trades"] == 0


def test_future_candidates_cannot_change_prefix_nav():
    early = candidate()
    late = candidate("LATE", when=T+10*86400)
    a = r.portfolio([early], variant(), START, END)
    b = r.portfolio([early,late], variant(), START, END)
    assert [p for p in a["curve"] if p[0] < late["entry_ts"]] == [p for p in b["curve"] if p[0] < late["entry_ts"]]


def test_tampered_trace_fails_independent_cash_reconciliation():
    c = candidate()
    trace = c["paths"]["ladder"]["trace"]
    step = list(trace[0]); step[5] += .1; trace[0] = tuple(step)
    with pytest.raises(AssertionError, match="cash reconciliation"):
        r.portfolio([c], variant(), START, END)


def test_gate_permissions_require_frozen_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(r, "ART", tmp_path)
    with pytest.raises(ValueError, match="shortlist"):
        r.stage_permission("validation")
    with pytest.raises(ValueError, match="winner"):
        r.stage_permission("final_oos")


def test_monthly_membership_excludes_future_volume():
    ix = pd.date_range("2023-10-01", "2024-02-01", freq="1h", tz="UTC", inclusive="left")
    frame = pd.DataFrame(100., index=ix, columns=["open", "high", "low", "close", "volume", "quote_volume"])
    month = [r.utc("2024-01-01")]
    before = r.monthly_rows("TEST", frame, month)
    changed = frame.copy()
    changed.loc[changed.index >= month[0], "quote_volume"] *= 100000
    assert r.monthly_rows("TEST", changed, month) == before


def test_statistical_interval_includes_inactive_weeks():
    x = [0.]*50 + [.01, -.01]
    result = r.block_ci(x)
    assert result["weeks"] == 52
    assert result["ci95_pct"][0] <= 0 <= result["ci95_pct"][1]


def test_invalid_policy_fails_closed():
    with pytest.raises(ValueError): r.position_fraction(100,110,"typo")
    with pytest.raises(ValueError): r.passes({}, "typo")
    with pytest.raises(ValueError): r.simulate_path([(T,100,110,80,100)],100,110,[90,80,70],"typo")


def test_new_ladder_agrees_with_previously_audited_engine_on_random_paths():
    from verify_red_team_audit_2026 import simulate_trade_v2
    rng = np.random.default_rng(407)
    for _ in range(80):
        bars, old_bars = [], []
        price = 100.
        for i in range(24):
            opened = T+i*300
            close = max(20., price+float(rng.normal(0, 4)))
            high = max(price, close)+float(rng.uniform(0,4))
            low = min(price, close)-float(rng.uniform(0,4))
            bars.append((opened, price, high, low, close))
            old_bars.append({"open_time_str": pd.Timestamp(opened,unit="s",tz="UTC").isoformat(),
                "close_time_ts": pd.Timestamp(opened+300,unit="s",tz="UTC"),
                "open": price, "high": high, "low": low, "close": close})
            price = close
        new = r.simulate_path(bars, 100, 110, [90,80,70])
        old = simulate_trade_v2(old_bars,entry_price=100,stop_loss=110,tp1=90,tp2=80,tp3=70,
                               round_trip_fee_bps=0,entry_timestamp_utc=r.utc(START))
        assert new["gross_return"]*100 == pytest.approx(old["gross_pct"])
        assert new["exit_ts"] == int(r.utc(old["exit_close_time"]).timestamp())


def test_24h_exit_matches_fresh_simulation_to_that_boundary():
    from research_round02_v407 import truncate_path
    bars = [(T+i*300, 100., 102., 95., 97.+i*.001) for i in range(400)]
    original = r.simulate_path(bars, 100, 110, [90,80,70])
    deadline=T+24*3600
    truncated=truncate_path(original,deadline)
    fresh=r.simulate_path(bars[:288],100,110,[90,80,70])
    assert truncated["gross_return"] == pytest.approx(fresh["gross_return"])
    assert truncated["exit_ts"] == fresh["exit_ts"] == deadline
    assert truncated["trace"] == fresh["trace"]


def test_24h_exit_missing_boundary_invalidates_instead_of_selecting_trade():
    from research_round02_v407 import truncate_path
    bars=[(T+i*300,100.,102.,95.,97.) for i in range(400) if i != 287]
    path=r.simulate_path(bars,100,110,[90,80,70])
    with pytest.raises(ValueError,match="Missing"):
        truncate_path(path,T+24*3600)


def test_funding_signal_observes_publication_lag_and_never_future_rate():
    from research_funding_v407 import funding_features
    times=np.array([T,T+8*3600,T+16*3600])
    rates=np.array([.0001,-.01,.02])
    before=funding_features(times,rates,T+8*3600)
    after=funding_features(times,rates,T+8*3600+300)
    assert before["last_rate"] == .0001
    assert after["last_rate"] == -.01
    changed=rates.copy(); changed[-1]=100
    assert funding_features(times,changed,T+8*3600)==before


def test_funding_staleness_and_three_event_window():
    from research_funding_v407 import funding_features
    times=np.array([T,T+8*3600,T+16*3600]);rates=np.array([.01,-.02,.03])
    known=funding_features(times,rates,T+16*3600+300)
    assert known["last3_mean"] == pytest.approx(.02/3)
    assert funding_features(times,rates,T+29*3600) is None
    assert funding_features(times,rates,T+120) is None


def test_funding_loader_is_development_only(tmp_path):
    from research_funding_v407 import read_funding
    p=tmp_path/"funding.parquet"
    pd.DataFrame({"funding_time":pd.to_datetime(["2024-12-31","2025-01-01","2026-01-01"],utc=True),
                  "funding_rate":[.01,9.,99.]}).to_parquet(p,index=False)
    out=read_funding(p)
    assert len(out)==1 and out.funding_rate.iloc[0]==.01


def test_funding_filter_does_not_fill_missing_feature():
    from research_funding_v407 import passes_feature
    assert not passes_feature(None,"last_nonnegative")
    assert not passes_feature({"last_rate":.001,"last3_mean":None},"last3_nonnegative")
