import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"scripts"))
from short_reversal_flow import four_hour_flow,accepts,generate


def test_volume_weighted_not_average_fractions():
    idx=pd.date_range("2026-01-01 01:00",periods=8,freq="h",tz="UTC")
    h=pd.DataFrame(dict(volume=[100,1,1,1]*2,taker_buy_volume=[80,0,0,0]*2),index=idx)
    f=four_hour_flow(h)
    assert f.ratio.iloc[0]==pytest.approx(80/103)
    assert f.previous_ratio.iloc[1]==f.ratio.iloc[0]


@pytest.mark.parametrize("fault",["missing","zero","nan","buy_above_total"])
def test_bad_hour_cannot_be_neutral_or_partial_ratio(fault):
    idx=pd.date_range("2026-01-01 01:00",periods=4,freq="h",tz="UTC")
    h=pd.DataFrame(dict(volume=10.,taker_buy_volume=5.),index=idx)
    if fault=="missing":h=h.drop(idx[2])
    elif fault=="zero":h.loc[idx[2],["volume","taker_buy_volume"]]=0
    elif fault=="nan":h.loc[idx[2],"taker_buy_volume"]=np.nan
    else:h.loc[idx[2],"taker_buy_volume"]=11
    assert four_hour_flow(h).ratio.isna().all()


def test_gates_and_missing_data():
    assert accepts(.49,.6,"exhaust") and not accepts(.51,.6,"exhaust")
    assert accepts(.5,.56,"drop5") and not accepts(.52,.56,"drop5")
    assert accepts(.56,.52,"absorbed") and not accepts(.54,.52,"absorbed")
    assert accepts(.5,.45,"seller")
    assert accepts(np.nan,np.nan,"none")
    for gate in ["seller","drop5","exhaust","absorbed"]:assert not accepts(.49,np.nan,gate)


def test_unclosed_future_flow_cannot_change_closed_ratio():
    idx=pd.date_range("2026-01-01 01:00",periods=12,freq="h",tz="UTC")
    h=pd.DataFrame(dict(volume=100.,taker_buy_volume=np.arange(12)*8.),index=idx)
    a=four_hour_flow(h);b=four_hour_flow(h.iloc[:7])
    pd.testing.assert_frame_equal(a.loc[:idx[3]],b.loc[:idx[3]])
    assert pd.isna(b.ratio.iloc[-1])


def test_filter_preserves_original_event_identity_order_and_cooldown():
    idx=pd.date_range("2026-01-01 04:00",periods=2,freq="4h",tz="UTC")
    entries=[dict(at=int(t.timestamp()*1000),symbol="X",event_id=str(i),atr=2.,probability=1.) for i,t in enumerate(idx)]
    flow={"X":pd.DataFrame(dict(ratio=[.49,.6],previous_ratio=[.6,.49]),index=idx)}
    out,_=generate({"benchmark_mask0":entries,"benchmark_mask2":entries},flow)
    assert out["mask0_none"]==entries and out["mask0_exhaust"]==entries[:1] and out["mask0_absorbed"]==entries[1:]
