import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"scripts"))
from monthly_strategy_selection import choose,route,bounded_prices


def rows(source="a",profit=5,floor=.01):
    return [dict(source_id=source,cost=c,ending_equity=500+profit,max_drawdown=.1,exits=5,monthly=dict(complete=True,min_monthly_return=floor)) for c in ["base","stress"]]


def test_profit_and_floor_have_distinct_objectives():
    r=rows("a",10,-.05)+rows("b",5,.01)
    assert choose(r,"profit")=="a" and choose(r,"floor")=="b"


@pytest.mark.parametrize("field,value",[("ending_equity",None),("ending_equity",500),("max_drawdown",.2),("exits",4)])
def test_both_costs_must_qualify(field,value):
    r=rows();r[1][field]=value
    assert choose(r,"profit") is None


def test_missing_cost_or_monthly_data_rejected():
    r=rows();assert choose(r[:1],"profit") is None
    r[1]["monthly"]["complete"]=False;assert choose(r,"profit") is None


def test_monthly_routes_require_delay_and_preserve_events():
    sigs={"a":[dict(at=t,symbol="X",atr=1.,probability=1.,event_id=str(t)) for t in [1000000,1300000,1900000,2000000]],"b":[]}
    choices=[dict(start=1000000,end=2000000,training_end=700000,source_id="a"),dict(start=2000000,end=3000000,training_end=1700000,source_id=None)]
    r=route(sigs,choices)
    assert [x["at"] for x in r]==[1300000,1900000]
    assert all(x["event_id"]!=str(x["at"]) for x in r)
    assert r==route(sigs,choices)


def test_future_training_or_calendar_gap_rejected():
    with pytest.raises(ValueError,match="future_training"):route({},[dict(start=100,end=200,training_end=100,source_id=None)])
    with pytest.raises(ValueError,match="noncontiguous"):route({},[dict(start=100,end=200),dict(start=201,end=300)])


def test_future_price_read_is_blocked():
    get=bounded_prices({"X":{10:{"mark":1},11:{"mark":999}}},10)
    assert get("X").get(10)=={"mark":1}
    assert get("X")[10]=={"mark":1}
    with pytest.raises(ValueError,match="future_price_access"):get("X").get(11)
    with pytest.raises(ValueError,match="future_price_access"):get("X")[11]
