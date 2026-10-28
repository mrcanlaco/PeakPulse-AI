import sys
from pathlib import Path
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"scripts"))
from short_failed_rally import scan,prepare


def fixture():
    f=pd.DataFrame(dict(open=[101,99,99,102,100,99],close=[100,98,101,100,99,97.5],
        low=[99,97,98,99,98,97],high=[102,100,102,103,101,100],prior_low12=[99]*6,
        hour_atr=2.,atr=5.,ready=True,bear=True,btc_bear=True),index=pd.date_range("2026-01-01",periods=6,freq="h",tz="UTC"))
    return f,dict(id="test",bounce_atr=1,ttl_hours=6,regime="any",cooldown_hours=24)


def test_three_distinct_closed_bars_and_previous_low_confirmation():
    f,s=fixture();r=scan("X",f,s)
    assert len(r)==1
    assert r[0]["arm_at"]==int(f.index[1].timestamp()*1000)
    assert r[0]["bounce_at"]==int(f.index[2].timestamp()*1000)
    assert r[0]["at"]==int(f.index[5].timestamp()*1000)
    assert r[0]["atr"]==5 and r[0]["frozen_hour_atr"]==2


def test_later_atr_does_not_move_bounce_threshold():
    f,s=fixture();f.loc[f.index[2]:,"hour_atr"]=200
    assert len(scan("X",f,s))==1


def test_decimal_price_level_touch_is_not_lost_by_subtraction():
    from verify_failed_rally import oracle
    f,s=fixture();f=f.iloc[:4].copy()
    f["close"]=[3.2,3.119,3.14,3.10];f["open"]=[3.21,3.13,3.13,3.14]
    f["low"]=[3.19,3.11,3.13,3.09];f["hour_atr"]=.021;f["prior_low12"]=3.12
    assert 3.14-3.119<.021 and 3.119+.021==3.14
    a=scan("X",f,s);b=oracle(f,s)
    assert len(a)==len(b)==1
    assert a[0]["bounce_at"]==b[0][1]==int(f.index[2].timestamp()*1000)


@pytest.mark.parametrize("column",["ready","bear","btc_bear"])
def test_bad_data_or_lost_regime_cancels_watch(column):
    f,s=fixture();s["regime"]="btc_bear";f.loc[f.index[3],column]=False
    assert scan("X",f,s)==[]


def test_expiry_does_not_allow_delayed_confirmation():
    f,s=fixture();s["ttl_hours"]=3
    assert scan("X",f,s)==[]


def test_missing_hour_cancels_watch():
    f,s=fixture();assert scan("X",f.drop(f.index[3]),s)==[]


def test_future_rows_do_not_change_emitted_signals():
    f,s=fixture()
    for i in range(1,len(f)):
        before=int(f.index[i].timestamp()*1000)
        assert scan("X",f.iloc[:i+1],s)==[r for r in scan("X",f,s) if r["at"]<=before]


def test_four_hour_features_do_not_read_unclosed_hourly_future():
    import numpy as np
    idx=pd.date_range("2025-08-01",periods=400,freq="h",tz="UTC");x=100+np.sin(np.arange(400)/4)-np.arange(400)*.04
    h=pd.DataFrame(dict(open=x+.1,high=x+.2,low=x-.2,close=x,quote_volume=300000.),index=idx)
    fs={"BTCUSDT":h,"XUSDT":h.copy()};cut=idx[350]
    a=prepare(fs)["XUSDT"].loc[:cut];b=prepare({c:f.loc[:cut] for c,f in fs.items()})["XUSDT"]
    pd.testing.assert_frame_equal(a,b)
