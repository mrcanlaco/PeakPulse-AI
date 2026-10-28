import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"scripts"))
from altcoin_short_signals import hourly_features
from prepare_flow_research import hourly_flow
from short_funding_flow_signals import conditions, definitions, generate, known_funding


def test_flow_is_volume_weighted_and_incomplete_hours_are_missing():
    raw = pd.DataFrame(dict(open_time=pd.date_range("2025-01-01",periods=72,freq="5min",tz="UTC"),
                            volume=[100.]*12+[1.]*60,taker_buy_volume=[90.]*12+[0.]*60))
    f=hourly_flow(raw)
    assert abs(f.buy_fraction6.iloc[-1] - 1080/1260)<1e-12
    assert abs(f.buy_fraction6.iloc[-1] - f.buy_fraction1.mean())>0.5
    missing=hourly_flow(raw.drop(index=0))
    assert pd.isna(missing.buy_fraction1.iloc[0])
    assert pd.isna(missing.buy_fraction6.iloc[-1])


def test_zero_volume_is_not_neutral_or_sell_pressure():
    raw=pd.DataFrame(dict(open_time=pd.date_range("2025-01-01",periods=72,freq="5min",tz="UTC"),volume=0.,taker_buy_volume=0.))
    f=hourly_flow(raw)
    assert f.buy_fraction1.isna().all() and f.buy_fraction6.isna().all()


def test_new_settlement_not_known_before_sixty_seconds():
    index=pd.to_datetime([28800000,28859000,28860000],unit="ms",utc=True)
    r=known_funding(index,[(0,.0001,100),(28800000,.9,100)])
    assert r.last_funding.tolist()==[.0001,.0001,.9]


def test_funding_uses_actual_variable_cadence_and_excludes_future():
    hours=[0,8,16,20,24,28,29,30]
    schedule=[(h*3600000,.0001,100) for h in hours]
    stamp=pd.to_datetime([30*3600000+60000],unit="ms",utc=True)
    r=known_funding(stamp,schedule)
    assert abs(r.funding24.iloc[0]-.0007)<1e-12
    pd.testing.assert_frame_equal(r,known_funding(stamp,schedule+[(31*3600000,100.,100)]))


def test_stale_or_short_funding_history_stays_missing():
    r=known_funding(pd.to_datetime([3600000,40*3600000],unit="ms",utc=True),[(0,.1,100)])
    assert r.funding24.isna().all()
    assert pd.isna(r.last_funding.iloc[-1])


def test_absorption_requires_price_failure_not_buying_alone():
    h=pd.DataFrame(dict(buy6=[.6,.6,.4],ret6=[-.01,.01,-.01],close=[99.,99.,99.],
                        open=[100.]*3,ema20=[100.]*3,ema60=[101.]*3,ready=[True]*3))
    hit,_=conditions(h,dict(family="buyer_absorption",strength="loose",regime="any"))
    assert hit.tolist()==[True,False,False]


def test_all_signal_families_are_causal_and_cooldown_enforced():
    rng=np.random.default_rng(10)
    n=6000
    close=100*np.exp(np.cumsum(rng.normal(-.0002,.005,n)))
    raw=pd.DataFrame(dict(open_time=pd.date_range("2025-08-01",periods=n,freq="5min",tz="UTC"),
                          open=close*1.001,high=close*1.015,low=close*.985,close=close,
                          quote_volume=50000.,volume=100.,taker_buy_volume=60.))
    h=hourly_features(raw); f=hourly_flow(raw)
    first=int(raw.open_time.iloc[0].timestamp()*1000)
    funding=[(first+i*3600000,.0001,100) for i in range(0,600,4)]
    cut=h.index[350]; at=int(cut.timestamp()*1000)
    full=generate({"X":h,"BTCUSDT":h},{"X":f},{"X":funding})
    prefix=generate({"X":h.loc[:cut],"BTCUSDT":h.loc[:cut]},{"X":f.loc[:cut]},
                    {"X":[r for r in funding if r[0]<=at]})
    assert any(full.values())
    assert {k:[r for r in rows if r["at"]<=at] for k,rows in full.items()}==prefix
    for spec in definitions():
        rows=full[spec["id"]]
        assert all(b["at"]-a["at"]>=spec["cooldown_hours"]*3600000 for a,b in zip(rows,rows[1:]))
    h["ready"]=False
    assert not any(generate({"X":h,"BTCUSDT":h},{"X":f},{"X":funding}).values())
