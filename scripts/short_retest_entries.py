"""Causal first-entry watches: breakdown, recovery, then renewed weakness."""

import math
from collections import Counter
from short_entry_timing import definitions as legacy_definitions, transform as legacy_transform

STEP=300000


def definitions():
    controls=[dict(s) for s in legacy_definitions() if s["id"] in ["immediate","delay60","breakdown0.5","rejection0.5"]]
    new=[dict(id=f"retest_d{d:g}_b{b:g}_ttl{ttl}",mode="retest",down_atr=d,bounce_atr=b,fall_atr=.25,ttl_hours=ttl,
              label=f"Giảm {d:g} ATR → hồi {b:g} ATR → giảm lại 0,25 ATR; chờ {ttl}h")
         for d in [.25,.5] for b in [.25,.5] for ttl in [6,24]]
    return controls+new


def transform(signals,prices,start,end,spec):
    if spec["mode"]!="retest":return legacy_transform(signals,prices,start,end,spec)
    if any(not math.isfinite(spec.get(k,0)) or spec.get(k,0)<=0 for k in ["down_atr","bounce_atr","fall_atr","ttl_hours"]):
        raise ValueError("invalid_retest_policy")
    if spec["ttl_hours"]*3600000%STEP:raise ValueError("unaligned_retest_expiry")
    output=[];audit=[]
    for signal in signals:
        origin=signal["at"]
        if not start<=origin<end:continue
        record=dict(event_id=signal["event_id"],symbol=signal["symbol"],original_at=origin)
        quotes=prices.get(signal["symbol"],{})
        anchor=quotes.get(origin,{}).get("execution_close",math.nan);atr=signal["atr"]
        if not all(math.isfinite(x) and x>0 for x in [anchor,atr]):
            audit.append(dict(record,status="missing_data"));continue
        expiry=origin+int(spec["ttl_hours"]*3600000)
        status="end_pending" if expiry>=end else "expired"
        state="waiting_down";low=peak=previous=anchor;down_at=bounce_at=None
        for at in range(origin+STEP,min(expiry,end-STEP)+1,STEP):
            close=quotes.get(at,{}).get("execution_close",math.nan)
            if not math.isfinite(close) or close<=0:
                status="missing_data";break
            # Exactly one state transition per completed bar. No future open,
            # intrabar high/low, or eventual outcome participates in the watch.
            if state=="waiting_down":
                if close<=anchor-spec["down_atr"]*atr:
                    state="waiting_bounce";low=close;down_at=at
            elif state=="waiting_bounce":
                low=min(low,close)
                if close>=low+spec["bounce_atr"]*atr:
                    state="waiting_failure";peak=close;bounce_at=at
            else:
                if close<previous and close<=peak-spec["fall_atr"]*atr:
                    output.append(dict(signal,at=at,original_signal_at=origin))
                    audit.append(dict(record,status="triggered",trigger_at=at,wait_minutes=(at-origin)/60000,
                                      improvement_atr=(close-anchor)/atr,down_at=down_at,bounce_at=bounce_at,
                                      anchor=anchor,recovery_low=low,recovery_peak=peak,trigger_close=close))
                    status="triggered";break
                peak=max(peak,close)
            previous=close
        if status!="triggered":audit.append(dict(record,status=status,state=state,down_at=down_at,bounce_at=bounce_at))
    return output,dict(counts=dict(Counter(r["status"] for r in audit)),source_events=len(audit),events=audit)
