import sys
from pathlib import Path
import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"scripts"))
import directional_trend_signals as strategy


def frame(side="LONG", periods=1):
    long=side=="LONG"
    return pd.DataFrame(dict(open=104 if long else 96,close=105 if long else 95,high=106 if long else 101,
        low=99 if long else 94,ema20=100,ema60=95 if long else 105,ret24=.05 if long else -.05,
        atr=2.,ready=True,volume_ratio=1.5,prior_high20=104,prior_low20=96),
        index=pd.date_range("2026-01-01",periods=periods,freq="4h",tz="UTC"))


@pytest.mark.parametrize("side",["LONG","SHORT"])
@pytest.mark.parametrize("family",["breakout","pullback"])
def test_trend_candle_volume_and_regime_all_required(side,family):
    f=frame(side);state=pd.DataFrame(dict(long_allowed=True,short_allowed=True),index=f.index)
    hit,score=strategy.conditions(f,state,family,"breadth60_btc",side)
    assert hit.iloc[0] and score.iloc[0]==pytest.approx(.05/(2/f.close.iloc[0]))
    state.loc[:,side.lower()+"_allowed"]=False
    assert not strategy.conditions(f,state,family,"breadth60_btc",side)[0].iloc[0]
    assert strategy.conditions(f,state,family,"any",side)[0].iloc[0]
    f.loc[:,"volume_ratio"]=.99
    assert not strategy.conditions(f,state,family,"any",side)[0].iloc[0]


def test_breakout_requires_close_beyond_prior_level_not_just_wick():
    f=frame();state=pd.DataFrame(dict(long_allowed=True,short_allowed=True),index=f.index)
    f["prior_high20"]=105.5
    assert f.high.iloc[0]>f.prior_high20.iloc[0]
    assert not strategy.conditions(f,state,"breakout","any","LONG")[0].iloc[0]


@pytest.mark.parametrize("coins,above,allow",[(23,23,False),(24,14,False),(24,15,True)])
def test_market_gate_needs_coverage_and_breadth(monkeypatch,coins,above,allow):
    monkeypatch.setattr(strategy,"features",lambda h:h.copy())
    inputs={"BTCUSDT":frame()}
    for i in range(coins):inputs[str(i)]=frame("LONG" if i<above else "SHORT")
    _,state=strategy.prepare(inputs)
    assert state.coverage.iloc[0]==coins
    assert bool(state.long_allowed.iloc[0]) is allow
    assert not state.short_allowed.iloc[0]  # BTC is bullish


def test_equal_ema_does_not_count_as_either_direction(monkeypatch):
    monkeypatch.setattr(strategy,"features",lambda h:h.copy())
    inputs={"BTCUSDT":frame()}
    for i in range(24):
        f=frame();f.loc[:,"close"]=95;inputs[str(i)]=f
    _,state=strategy.prepare(inputs)
    assert state.coverage.iloc[0]==24 and state.above.iloc[0]==state.below.iloc[0]==0
    assert not state.long_allowed.iloc[0] and not state.short_allowed.iloc[0]


def test_signal_identity_cooldown_and_hybrid_priority():
    f=frame(periods=7);state=pd.DataFrame(dict(long_allowed=True,short_allowed=True),index=f.index)
    at=int(f.index[0].timestamp()*1000)
    frozen=[dict(symbol="X",at=at,event_id="original",side="SHORT",atr=3.,probability=999.)]
    out=strategy.generate({"X":f},state,frozen)
    longs=out["breakout_any_long"]
    assert [r["at"] for r in longs]==[at,at+86400000]
    assert [r for r in out["breakout_any_both_trend"] if r["side"]=="LONG"]==longs
    event=next(r for r in out["breakout_any_hybrid"] if r["side"]=="SHORT")
    assert event["event_id"]=="original" and event["atr"]==3.
    assert event["probability"]==pytest.approx(.05/(2/105)) and event["family"]=="reversal"
