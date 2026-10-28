import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"scripts"))
from account_scaled_replay import simulate
from research_capacity_config import configuration
from capital_research_metrics import audit_account
from dao_vang.config.settings import ExecutionConfig

RULE=dict(market_step=".001",step_size=".001",min_qty=.001,market_min_qty=.001,max_qty=100000,market_max_qty=100000,min_notional=5,tick_size=".001")


def replay(cap,n=25,closes=(100,100),later=False):
    times=[i*300000 for i in range(len(closes))]
    quotes={t:dict(mark=c,execution_close=c,entry_open=c) for t,c in zip(times,closes)}
    entries=[dict(symbol=f"C{i}",event_id=f"event{i}",atr=2.) for i in range(30)]
    entries.append(dict(symbol="C0",event_id="duplicate_coin",atr=2.))
    signals={0:entries}
    if later:signals[times[-1]]=[dict(symbol="LATER",event_id="late",atr=2.)]
    return simulate(times,signals,lambda _:quotes,{**{f"C{i}":RULE for i in range(30)},"LATER":RULE},lambda _:[],configuration(cap),
        research_policy=dict(position_notional=n,entry_parts=3,entry_mode="favorable",entry_step_atr=.25,add_expiry_hours=6,trailing=True,activation_atr=3,callback_fraction=.01,unrepresentable_tp_action="pause_hold"))


@pytest.mark.parametrize("cap",[5,10,20,30])
def test_capacity_and_one_position_per_coin(cap):
    r=replay(cap);assert r["entries"]==cap and len(r["open_positions"])==cap
    assert len({p["symbol"] for p in r["open_positions"]})==cap
    audit_account(r,25,cap)


def test_capacity_does_not_create_margin_and_reserves_unfilled_tranches():
    r=replay(30,100)
    assert 5<r["entries"]<30 and r["rejections"]["insufficient_margin"]>0
    assert all(p["filled_parts"]==1 for p in r["open_positions"])
    point=r["curve"][-1]
    assert point["committed_margin"]>2*sum(p["qty"]*100/5 for p in r["open_positions"])
    assert point["committed_margin"]<=point["equity"]
    audit_account(r,100,30)


def test_drawdown_pause_keeps_thirty_existing_losers():
    r=replay(30,25,(100,160,180,200),later=True)
    assert r["entries"]==30 and len(r["open_positions"])==30
    assert r["entry_paused"] and r["rejections"]["drawdown_paused"]>0
    assert r["ending_equity"]<400 and r["curve"][-1]["equity"]<r["curve"][1]["equity"]
    audit_account(r,25,30)


def test_live_schema_unchanged_and_unregistered_caps_rejected():
    with pytest.raises(ValueError):ExecutionConfig(max_open_positions=30)
    with pytest.raises(ValueError,match="unregistered"):configuration(100)
    assert ExecutionConfig().max_open_positions==1
