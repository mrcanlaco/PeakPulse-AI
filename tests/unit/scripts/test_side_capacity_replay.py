import sys
from pathlib import Path
import pytest
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"scripts"))
from account_side_quota_replay import simulate
from account_directional_replay import simulate as original
from directional_capacity_metrics import side_metrics
from dao_vang.config.settings import ExecutionConfig

RULE=dict(market_step="0.001",step_size="0.001",min_qty=.001,market_min_qty=.001,max_qty=100000,market_max_qty=100000,min_notional=5,tick_size="0.001")


def replay(caps=None,*,closes=(100,101,102,103),signals=None,extra=None):
    events=[dict(symbol=f"{side}{i}",side=side,event_id=f"{side}{i}",atr=2) for side in ["LONG","SHORT"] for i in range(5)]
    signals={0:events} if signals is None else signals
    times=[i*300000 for i in range(len(closes))]
    points={t:dict(mark=p,execution_close=p,entry_open=p) for t,p in zip(times,closes)}
    rules={j["symbol"]:RULE for batch in signals.values() for j in batch}
    args=(times,signals,lambda c:points,rules,lambda c:[],ExecutionConfig(max_open_positions=5))
    policy=dict(entry_parts=3,entry_mode="favorable",entry_step_atr=.25,fixed_tp_usdt=5)
    if caps is not None:policy["side_caps"]=caps
    policy.update(extra or {})
    return simulate(*args,research_policy=policy),args,policy


def test_shared_mode_preserves_full_original_output():
    r,args,p=replay()
    assert r==original(*args,research_policy=p)


@pytest.mark.parametrize("long",[1,2,3,4])
def test_fixed_caps_count_positions_not_tranches(long):
    caps=dict(LONG=long,SHORT=5-long);r,_,_=replay(caps)
    m=side_metrics(r,r["curve"],caps)
    assert r["entries"]==5
    assert m["sides"]["LONG"]["peak_positions"]==long
    assert m["sides"]["SHORT"]["peak_positions"]==5-long
    assert sum(j["kind"]=="entry_add" for j in r["journal"])==2*long
    assert r["rejections"]["side_capacity_long"]==5-long
    assert r["curve"][0]["committed_margin"]>24


def test_empty_reserved_short_slots_cannot_be_borrowed_by_longs():
    signals={0:[dict(symbol=f"X{i}",side="LONG",event_id=str(i),atr=2) for i in range(5)]}
    r,_,_=replay(dict(LONG=2,SHORT=3),signals=signals)
    assert r["entries"]==2 and r["rejections"]["side_capacity_long"]==3


def test_slot_freed_by_exit_can_admit_new_event_without_retrying_rejected_old_one():
    signals={0:[dict(symbol="X",side="LONG",event_id="x",atr=2),dict(symbol="Z",side="LONG",event_id="z",atr=2)],
             300000:[dict(symbol="Y",side="LONG",event_id="y",atr=2)]}
    r,_,_=replay(dict(LONG=1,SHORT=4),signals=signals,extra=dict(max_hold_hours=1/12))
    assert [j["event_id"] for j in r["journal"] if j["kind"]=="entry"]==["x","y"]
    assert any(j["kind"]=="time_exit" for j in r["journal"])
    side_metrics(r,r["curve"],dict(LONG=1,SHORT=4))


def test_shared_drawdown_blocks_other_direction_despite_free_quota():
    signals={0:[dict(symbol="X",side="LONG",event_id="x",atr=2)],600000:[dict(symbol="Y",side="SHORT",event_id="y",atr=2)]}
    r,_,_=replay(dict(LONG=1,SHORT=4),closes=(100,60,50),signals=signals,extra=dict(position_notional=1000))
    assert r["entry_paused"] and r["entries"]==1 and r["rejections"]["drawdown_paused"]==1
    assert len(r["open_positions"])==1 and r["open_positions"][0]["unrealized"]<0


@pytest.mark.parametrize("caps",[{},dict(LONG=2,SHORT=2),dict(LONG=-1,SHORT=6),dict(LONG=2.,SHORT=3),dict(LONG=True,SHORT=4),dict(LONG=5),[2,3]])
def test_invalid_caps_fail_before_simulation(caps):
    with pytest.raises(ValueError,match="invalid_side_capacity"):replay(caps)


def test_opposite_side_signal_does_not_bypass_single_coin_rule():
    signals={0:[dict(symbol="X",side="LONG",event_id="x",atr=2),dict(symbol="X",side="SHORT",event_id="s",atr=2)]}
    r,_,_=replay(dict(LONG=2,SHORT=3),signals=signals)
    assert r["entries"]==1 and r["rejections"]["position_limit"]==1


def test_direction_metrics_weight_duration_and_include_open_costs():
    r,_,_=replay(dict(LONG=2,SHORT=3))
    m=side_metrics(r,pd.DataFrame(r["curve"]),dict(LONG=2,SHORT=3))
    assert m["sides"]["LONG"]["mean_positions"]==2 and m["sides"]["SHORT"]["mean_positions"]==3
    assert m["fraction_time_both_sides"]==m["fraction_time_all_slots"]==1
    assert sum(v["total_contribution"] for v in m["sides"].values())==pytest.approx(r["ending_equity"]-500)
