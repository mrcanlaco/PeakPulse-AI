import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"scripts"))
from short_guard_ablation import apply_mask,decisions,definitions
from short_entry_guards import filter_entries


def fixture():
    idx=pd.date_range("2025-01-01",periods=3,freq="h",tz="UTC")
    f=pd.DataFrame(dict(close=100.,atr=2.,ret24=.05,ret6=-.01,funding24=.001,ready=True),index=idx)
    s=[dict(symbol="X",event_id=str(i),at=int(t.timestamp()*1000),atr=3.,probability=.7) for i,t in enumerate(idx)]
    return s,{"X":f}


def test_full_and_empty_masks_reproduce_existing_guards():
    s,f=fixture();f["X"].iloc[1,f["X"].columns.get_loc("ret6")]=.01
    obs=decisions(s,f)
    assert apply_mask(s,obs,0)[0]==filter_entries(s,f,"none")[0]
    assert apply_mask(s,obs,15)[0]==filter_entries(s,f,"anti_squeeze")[0]
    assert len(definitions())==16


@pytest.mark.parametrize("field,value,bit",[("ret24",.11,1),("ret6",.01,2),("funding24",-.0011,4),("atr",6.,8)])
def test_leave_one_out_removes_only_its_predicate(field,value,bit):
    s,f=fixture();f["X"].loc[:,field]=value;obs=decisions(s,f)
    assert not apply_mask(s,obs,15)[0]
    assert apply_mask(s,obs,15^bit)[0]==s
    assert not apply_mask(s,obs,bit)[0]


def test_future_hour_cannot_change_past_decision():
    s,f=fixture();s[0]["at"]+=30*60000
    a=decisions(s[:1],f);f["X"].iloc[1:,f["X"].columns.get_loc("ret24")]=99
    assert a==decisions(s[:1],f)


def test_missing_data_is_not_a_passing_partial_guard():
    s,f=fixture();f["X"].loc[:,"atr"]=float("nan");obs=decisions(s,f)
    assert apply_mask(s,obs,1)[1]=={"missing_features":3}
    assert apply_mask(s,obs,0)[0]==s


def test_misaligned_observations_rejected():
    s,f=fixture();obs=decisions(s,f)
    with pytest.raises(ValueError,match="unaligned"):apply_mask(s,list(reversed(obs)),15)
