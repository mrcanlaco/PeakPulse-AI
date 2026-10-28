"""Capital/slot diagnostics and allocation-aware journal checks for research."""

from collections import defaultdict

import numpy as np
import pandas as pd


def audit_account(result,notional,cap=5):
    active={};invested=defaultdict(float)
    for j in result["journal"]:
        if j["kind"]=="entry":
            assert j["symbol"] not in active
            active[j["symbol"]]=j["event_id"]
            assert len(active)<=cap
        if j["kind"] in ["entry","entry_add"]:
            assert active[j["symbol"]]==j["event_id"]
            invested[j["event_id"]]+=j["qty"]*j["price"]
        if "net" in j:assert active.pop(j["symbol"])==j["event_id"]
    assert max(invested.values(),default=0)<=notional+1e-7
    assert len(active)==len(result["open_positions"])
    if result["ending_equity"] is not None:
        difference=result["ending_equity"]-result["initial_equity"]-result["closed_trade_net"]-sum(
            p["unrealized"]-p["entry_fee"]+p["funding"] for p in result["open_positions"])
        assert abs(difference)<1e-6
    return dict(max_entry_notional=max(invested.values(),default=0),
                mean_entry_notional=float(np.mean(list(invested.values()))) if invested else 0,
                total_entry_notional=sum(invested.values()),episodes=len(invested))


def utilization(curve,result,notional,cap=5):
    """Each recorded state holds until next timestamp; exclude zero-duration end."""
    frame=pd.DataFrame(curve)
    audited=audit_account(result,notional,cap)
    if len(frame)<2:return dict(complete=False,**audited)
    duration=frame["at"].shift(-1)-frame["at"]
    duration=duration.iloc[:-1].to_numpy(dtype=float)
    observed=frame.iloc[:-1]
    total=duration.sum()
    avg=lambda v:float(np.average(v,weights=duration))
    holds=[float(j["held_hours"])/24 for j in result["journal"] if "net" in j]
    open_holds=[float(p["held_days"]) for p in result["open_positions"]]
    entry_turnover=audited["total_entry_notional"]
    return dict(complete=result["ending_equity"] is not None,**audited,
                observed_days=total/86400000,
                mean_positions=avg(observed.positions),
                fraction_time_all_slots_used=avg(observed.positions.eq(cap)),
                fraction_time_paused=avg(observed.paused),
                mean_committed_margin=avg(observed.committed_margin),
                peak_committed_margin=float(frame.committed_margin.max()),
                mean_committed_to_initial_equity=avg(observed.committed_margin)/result["initial_equity"],
                closed_hold_median_days=float(np.median(holds)) if holds else None,
                closed_hold_p90_days=float(np.quantile(holds,.9)) if holds else None,
                open_hold_max_days=max(open_holds) if open_holds else None,
                entry_turnover_multiple=entry_turnover/result["initial_equity"],
                net_pnl_to_entry_turnover=result["pnl"]/entry_turnover if result["pnl"] is not None and entry_turnover else None,
                rejected_capacity=result["rejections"].get("position_limit",0),
                rejected_paused=result["rejections"].get("drawdown_paused",0),
                note="Committed margin includes marked position margin, unfilled-part reserves and estimated reserve fees. It is NOT account loss-at-risk. Means cover the observed path, possibly truncated at a proxy margin breach; complete flag controls interpretation.")
