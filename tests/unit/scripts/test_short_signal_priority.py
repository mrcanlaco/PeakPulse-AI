import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"scripts"))
from short_signal_priority import RANKS,priorities,rank,collisions


def bar(**kw):return SimpleNamespace(**dict(dict(close=100.,open=101.,atr=2.,ret24=.10,volume24=1e6),**kw))


def test_priority_signs_and_dimensions():
    v=priorities(dict(probability=3.),bar(),SimpleNamespace(ret6=-.01),.001)
    assert v==dict(zscore=3.,impulse_atr=5.,low_vol=-.02,liquidity=1e6,funding24=.001,weak6=.01,body_atr=.5)


@pytest.mark.parametrize("field,value",[("close",0),("atr",0),("ret24",float("nan"))])
def test_bad_inputs_are_not_silently_given_a_favorable_rank(field,value):
    with pytest.raises(ValueError,match="priority_features_missing"):
        priorities(dict(probability=3.),bar(**{field:value}),SimpleNamespace(ret6=-.01),.001)


def test_carry_precision_prevents_history_sum_noise_breaking_true_ties():
    a=priorities(dict(probability=3.),bar(),SimpleNamespace(ret6=0),.0003+1e-16)
    b=priorities(dict(probability=3.),bar(),SimpleNamespace(ret6=0),.0003-1e-16)
    assert a["funding24"]==b["funding24"]==.0003


def test_ranking_preserves_all_events_times_and_tie_breaks_by_coin():
    signals=[dict(event_id="b",symbol="B",at=100,atr=2,side="SHORT",probability=1),
             dict(event_id="a",symbol="A",at=100,atr=3,side="SHORT",probability=1),
             dict(event_id="c",symbol="C",at=200,atr=4,side="SHORT",probability=999)]
    observations=[dict(event_id=s["event_id"],symbol=s["symbol"],at=s["at"],scores={k:s["probability"] for k in RANKS}) for s in signals]
    output=rank(signals,observations)
    for events in output.values():
        assert [s["event_id"] for s in events]==["a","b","c"]
        assert {s["event_id"]:s for s in events}=={s["event_id"]:s for s in signals}
    assert collisions(signals)==dict(events=3,timestamps=2,collision_timestamps=1,events_in_collisions=2,maximum_candidates=2)
    with pytest.raises(ValueError,match="unaligned_priority_inputs"):rank(signals,observations[::-1])
