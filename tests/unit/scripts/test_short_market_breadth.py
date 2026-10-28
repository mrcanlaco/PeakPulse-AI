"""Cross-sectional denominator, ranking, gates and causal beta tests."""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"scripts"))
from short_market_breadth import enrich,market_state,conditions,generate
from altcoin_short_signals import hourly_features


def feature(score=-.1,eligible=True,below=True,bear=True):
    idx=pd.date_range("2026-01-01",periods=8,freq="4h",tz="UTC")
    return pd.DataFrame(dict(eligible=eligible,raw7d=score,beta7d=score,ema20=99.,ema60=101.,close=98. if below else 102.,ret24=-.02,high=100.,open=99.5,btc_bear=bear,atr=2.),index=idx)


def test_ineligible_coins_do_not_change_rank_or_breadth_denominator():
    fs={f"C{i}":feature(-i/100) for i in range(25)};fs["MISSING"]=feature(-999,False)
    state,ranks=market_state(fs)
    assert (state.coverage==25).all() and (state.breadth_below_ema60==1).all()
    assert ranks["raw7d"]["MISSING"].isna().all()
    assert (ranks["raw7d"]["C24"]==1/25).all()


def test_insufficient_universe_coverage_blocks_signals():
    fs={f"C{i}":feature(-i/100) for i in range(23)};state,ranks=market_state(fs)
    s=dict(id="test",ranking="raw7d",regime="any",entry="scheduled",cooldown_hours=24)
    assert not generate(fs,state,ranks,[s])["test"]


def test_breadth_and_btc_must_both_pass_joint_regime():
    fs={f"C{i}":feature(-i/100,below=i<15,bear=False) for i in range(25)}
    state,ranks=market_state(fs);f=fs["C14"];rank=pd.Series(.1,index=f.index)
    base=dict(ranking="raw7d",regime="breadth60",entry="scheduled")
    assert conditions(f,state,rank,base)[0].all()
    assert not conditions(f,state,rank,dict(base,regime="breadth75_btc"))[0].any()


def test_rank_ties_are_not_broken_using_symbol_order():
    fs={f"C{i}":feature(-.1) for i in range(30)};_,ranks=market_state(fs)
    assert not ranks["raw7d"].le(.2).any().any()


def test_pullback_requires_current_closed_candle_rejection():
    fs={f"C{i}":feature(-i/100) for i in range(25)};state,ranks=market_state(fs);f=fs["C24"].copy()
    f["high"]=98.5
    spec=dict(ranking="raw7d",regime="any",entry="scheduled")
    assert conditions(f,state,ranks["raw7d"]["C24"],spec)[0].all()
    assert not conditions(f,state,ranks["raw7d"]["C24"],dict(spec,entry="pullback"))[0].any()


def test_cooldown_one_day_and_deterministic_order():
    fs={f"C{i}":feature(-i/100) for i in range(25)};state,ranks=market_state(fs)
    spec=dict(id="test",ranking="raw7d",regime="any",entry="scheduled",cooldown_hours=24)
    rows=generate(fs,state,ranks,[spec])["test"]
    assert len([r for r in rows if r["symbol"]=="C24"])==2
    assert rows==sorted(rows,key=lambda r:(r["at"],-r["probability"],r["symbol"]))


def frames():
    times=pd.date_range("2025-08-01",periods=500*12,freq="5min",tz="UTC");i=np.arange(len(times));result={}
    for coin,k in [("BTCUSDT",1),("XUSDT",1.5)]:
        close=100*np.exp(k*(.003*np.sin(i/81)+.001*np.cos(i/22))-.00001*i)
        raw=pd.DataFrame(dict(open_time=times,open=close,close=close,high=close*1.002,low=close*.998,quote_volume=200000.))
        result[coin]=hourly_features(raw)
    return result


def test_beta_uses_prior_week_excluding_last_day():
    fs=frames();f=enrich(fs)["XUSDT"];t=f.index[-3];h=fs["XUSDT"];b=fs["BTCUSDT"]
    r=np.log(h.close/h.close.shift());br=np.log(b.close/b.close.shift());endpoint=t-pd.Timedelta(hours=24)
    x=br.loc[:endpoint].tail(168);y=r.loc[x.index]
    beta=np.cov(y,x,ddof=1)[0,1]/np.var(x,ddof=1)
    assert f.loc[t,"beta"]==pytest.approx(beta)
    assert f.loc[t,"beta7d"]==pytest.approx(np.log(h.loc[endpoint,"close"]/h.loc[endpoint-pd.Timedelta(hours=168),"close"])-beta*np.log(b.loc[endpoint,"close"]/b.loc[endpoint-pd.Timedelta(hours=168),"close"]))


def test_appended_future_does_not_change_features_or_ranks():
    fs=frames();cut=fs["BTCUSDT"].index[399]
    full=enrich(fs);past=enrich({c:h.loc[:cut] for c,h in fs.items()})
    pd.testing.assert_frame_equal(full["XUSDT"].loc[:cut],past["XUSDT"].loc[:cut])
    a,ar=market_state(full,min_coverage=1);b,br=market_state(past,min_coverage=1)
    pd.testing.assert_frame_equal(a.loc[:cut],b.loc[:cut])
    pd.testing.assert_frame_equal(ar["beta7d"].loc[:cut],br["beta7d"].loc[:cut])
