"""Position occupancy and contribution by side, independent of signal counts."""
import numpy as np


def side_metrics(result, curve, caps=None):
    times=np.asarray(curve["at"] if hasattr(curve,"columns") else [r["at"] for r in curve])
    changes={side:np.zeros(len(times),dtype=int) for side in ["LONG","SHORT"]}
    active={};fills={side:0 for side in changes};closed={side:0. for side in changes}
    for j in result["journal"]:
        side=j["side"];coin=j["symbol"];i=int(np.searchsorted(times,j["at"]))
        if j["kind"]=="entry":
            assert coin not in active;active[coin]=side;fills[side]+=1
            if i<len(times):changes[side][i]+=1
            if caps is not None:assert sum(s==side for s in active.values())<=caps[side]
        elif "net" in j:
            assert active.pop(coin)==side;closed[side]+=j["net"]
            if i<len(times):changes[side][i]-=1
    assert len(active)==len(result["open_positions"])
    held={side:np.cumsum(changes[side]) for side in changes}
    total=held["LONG"]+held["SHORT"]
    reported=np.asarray(curve["positions"] if hasattr(curve,"columns") else [r["positions"] for r in curve])
    np.testing.assert_array_equal(total,reported)
    duration=np.diff(times);mean=lambda a:float(np.average(a[:-1],weights=duration)) if duration.sum() else 0.
    rows={}
    for side in changes:
        opened=[p for p in result["open_positions"] if p["side"]==side]
        open_net=sum(p["unrealized"]-p["entry_fee"]+p["funding"] for p in opened)
        rows[side]=dict(entries=fills[side],peak_positions=int(held[side].max()),mean_positions=mean(held[side]),
            fraction_time_present=mean(held[side]>0),open_count=len(opened),closed_net=closed[side],open_net=open_net,
            total_contribution=closed[side]+open_net if result["ending_equity"] is not None else None,
            side_capacity_rejections=result["rejections"].get("side_capacity_"+side.lower(),0))
    if result["ending_equity"] is not None:
        assert abs(sum(r["total_contribution"] for r in rows.values())-(result["ending_equity"]-500))<1e-6
    return dict(sides=rows,fraction_time_both_sides=mean((held["LONG"]>0)&(held["SHORT"]>0)),
                fraction_time_all_slots=mean(total>=result["max_positions"]))
