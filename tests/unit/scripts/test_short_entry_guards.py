import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"scripts"))
from short_entry_guards import filter_entries


def fixture():
    index=pd.date_range("2025-01-01",periods=3,freq="h",tz="UTC")
    f=pd.DataFrame(dict(close=100.,atr=2.,ret6=-.01,ret24=.02,ema20=99.,ema60=101.,
                        ready=True,funding24=.001,btc_ret24=-.01,btc_ready=True),index=index)
    s=dict(event_id="x",symbol="X",at=int(index[0].timestamp()*1000)+30*60000,atr=2.,probability=1.)
    return s,f


def test_guard_only_sees_latest_completed_hour():
    s,f=fixture();f.loc[f.index[1]:,"funding24"]=-1
    assert filter_entries([s],{"X":f},"nonnegative_carry")[0]==[s]
    s["at"]+=30*60000
    assert not filter_entries([s],{"X":f},"nonnegative_carry")[0]


def test_missing_and_stale_fail_closed_but_none_preserves_control():
    s,f=fixture();s["at"]+=180*60000
    assert filter_entries([s],{"X":f},"anti_squeeze")[1]["counts"]=={"stale_features":1}
    assert filter_entries([s],{},"none")[0]==[s]
    assert filter_entries([s],{},"anti_squeeze")[1]["counts"]=={"missing_features":1}


@pytest.mark.parametrize("field,value",[("ret24",.11),("ret6",.01),("funding24",-.0011),("atr",6.)])
def test_anti_squeeze_rejects_observed_warning(field,value):
    s,f=fixture();f.loc[:,field]=value
    assert not filter_entries([s],{"X":f},"anti_squeeze")[0]


def test_future_changes_do_not_change_gate_and_score_atr_are_frozen():
    s,f=fixture();a=filter_entries([s],{"X":f},"trend_confirmation")
    f.loc[f.index[1]:,"ret6"]=999
    assert a==filter_entries([s],{"X":f},"trend_confirmation")
    assert a[0]==[s]


def test_nan_features_are_not_treated_as_safe():
    s,f=fixture();f.loc[:,"funding24"]=float("nan")
    assert filter_entries([s],{"X":f},"nonnegative_carry")[1]["counts"]=={"missing_features":1}
