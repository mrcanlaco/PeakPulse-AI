"""Cash-coupled per-fill costs and signed historical funding for short positions."""
from collections import Counter
import heapq
import numpy as np
import pandas as pd
import research_v407 as r

SCENARIOS={"standard_vip6":{"fee_bps":2.5,"slippage_bps":10.},
           "stress_regular":{"fee_bps":5.,"slippage_bps":50.}}


def fill(direction,reference,quantity,fee_bps,slippage_bps):
    if direction not in ("SELL","BUY"):raise ValueError("Invalid direction")
    if not all(np.isfinite([reference,quantity,fee_bps,slippage_bps])) or reference<=0 or quantity<0 or min(fee_bps,slippage_bps)<0 or slippage_bps>=10000:raise ValueError("Invalid fill inputs")
    price=reference*(1+(-1 if direction=="SELL" else 1)*slippage_bps/10000)
    notional=quantity*price
    return {"side":direction,"reference_price":reference,"execution_price":price,"qty":quantity,"notional":notional,
        "fee":notional*fee_bps/10000,"slippage_cost":quantity*abs(price-reference)}


def execution_steps(candidate):
    """Recover exit turnover from an audited fixed-quantity mark-to-market path.

    Multiple executions in one 5m bar have the same fee/slippage rates; their
    quantity-weighted average price preserves their exact total costs. This is
    an accounting group, never represented as a known individual exchange fill.
    """
    previous=candidate["entry"];path=candidate["paths"]["ladder"]
    rows=[];gross=0.;remaining=1.
    for t,mark,before,after,active,delta,done in path["trace"]:
        if abs(before-remaining)>1e-10:raise AssertionError("Quantity discontinuity")
        closed=before-after
        if closed<-1e-10:raise AssertionError("Increasing position quantity")
        exit_price=None
        if closed>1e-10:
            exit_price=(before*previous-after*mark-delta*candidate["entry"])/closed
            if not np.isfinite(exit_price) or exit_price<=0:raise AssertionError("Invalid reconstructed exit turnover")
            gross+=closed*(candidate["entry"]-exit_price)/candidate["entry"]
        elif abs(delta*candidate["entry"]-before*(previous-mark))>1e-7*max(1.,candidate["entry"]):
            raise AssertionError("Invalid mark-to-market movement")
        rows.append((t*1000,mark,before,after,active,delta,done,closed,exit_price))
        previous=mark;remaining=after
    if remaining!=0 or abs(gross-path["gross_return"])>1e-9:raise AssertionError("Exit cash does not match original trace")
    return rows


def stop_loss_per_unit(entry,stop,scenario):
    entering=fill("SELL",entry,1.,**scenario)
    exiting=fill("BUY",stop,1.,**scenario)
    return exiting["execution_price"]-entering["execution_price"]+entering["fee"]+exiting["fee"]


def quantity(equity,entry,stop,sizing,scenario):
    if equity<=0 or not stop>entry>0:raise ValueError("Invalid position")
    limit=.20*equity/entry
    if sizing=="fixed":return limit
    if sizing!="risk":raise ValueError("Unknown sizing")
    return min(limit,.005*equity/stop_loss_per_unit(entry,stop,scenario))


def portfolio(candidates,variant,start,end,scenario,funding,prepared=None):
    start=int(r.utc(start).timestamp()*1000);end=int(r.utc(end).timestamp()*1000)
    assert end<=int(r.LIMIT.timestamp()*1000)
    selected=sorted((c for c in candidates if start<=c["entry_ts"]*1000<end-5*86400000 and r.passes(c,variant["gate"])),
        key=lambda c:(c["entry_ts"],-c["score"],c["symbol"],c["tf"]))
    equity=100.;positions={};heap=[];ledger=[];curve=[(start,100.)];waves=set();cooldown={};rejected=Counter();serial=0
    riskcap=.12 if variant["sizing"]=="fixed" else .02

    def advance(target):
        nonlocal equity
        while heap and heap[0][0]<=target:
            stamp=heap[0][0]
            while heap and heap[0][0]==stamp:
                _,priority,_,cid,data=heapq.heappop(heap)
                p=positions[cid]
                if priority==0:
                    event=data
                    amount=p["qty"]*p["rem"]*event["mark_price"]*event["funding_rate"]
                    record={**event,"remaining_qty":p["qty"]*p["rem"],"cashflow":amount}
                    p["funding_events"].append(record);p["funding"]+=amount;p["pnl"]+=amount;equity+=amount
                else:
                    t,mark,before,after,active,delta,done,closed,exit_price=data
                    assert abs(before-p["rem"])<1e-9
                    change=p["reference_notional"]*delta
                    if closed>1e-10:
                        out=fill("BUY",exit_price,p["qty"]*closed,**scenario)
                        out.update(timestamp_ms=t,aggregation="quantity_weighted_exit_group_within_5m")
                        p["fills"].append(out)
                        change-=out["slippage_cost"]+out["fee"]
                        p["fees"]+=out["fee"];p["slippage"]+=out["slippage_cost"]
                    equity+=change;p["pnl"]+=change
                    p.update(rem=after,mark=mark,active=active)
                    if done:
                        p["exit_ts_ms"]=stamp;ledger.append(p);del positions[cid]
            curve.append((stamp,equity))

    for c in selected:
        t=c["entry_ts"]*1000;advance(t)
        key=(c["symbol"],c["tf"]);wave=(*key,c["wave_key"])
        if wave in waves or t<cooldown.get(key,0):rejected["wave_or_cooldown"]+=1;continue
        if equity<=0:rejected["insolvent"]+=1;continue
        qty=quantity(equity,c["entry"],c["stop"],variant["sizing"],scenario)
        entryfill=fill("SELL",c["entry"],qty,**scenario)
        entrycost=entryfill["fee"]+entryfill["slippage_cost"]
        aftercost=equity-entrycost
        current_notional=sum(p["qty"]*p["rem"]*max(p["entry"],p["mark"]) for p in positions.values())
        current_risk=0.
        for p in positions.values():
            exit_at_stop=fill("BUY",p["active"],p["qty"]*p["rem"],**scenario)
            current_risk+=max(0.,exit_at_stop["notional"]-p["qty"]*p["rem"]*min(p["entry"],p["mark"])+exit_at_stop["fee"])
        proposed_risk=qty*stop_loss_per_unit(c["entry"],c["stop"],scenario)
        if len(positions)>=5 or current_notional+qty*c["entry"]>aftercost+1e-9 or current_risk+proposed_risk>aftercost*riskcap+1e-9:
            rejected["portfolio_cap"]+=1;continue
        path=c["paths"]["ladder"];exit_ms=path["exit_ts"]*1000
        assert exit_ms<=end
        steps=prepared[c["id"]] if prepared is not None else execution_steps(c)
        entryfill.update(timestamp_ms=t,aggregation="single_entry")
        p={"id":c["id"],"symbol":c["symbol"],"tf":c["tf"],"entry_ts_ms":t,"entry":c["entry"],"stop":c["stop"],
           "qty":qty,"reference_notional":qty*c["entry"],"equity_at_entry":equity,"rem":1.,"mark":c["entry"],"active":c["stop"],
           "gross_reference_return":path["gross_return"],"pnl":-entrycost,"fees":entryfill["fee"],"slippage":entryfill["slippage_cost"],
           "funding":0.,"fills":[entryfill],"funding_events":[],"missing_execution_bars":c["missing_execution_bars"],"exit_reason":path["exit_reason"],
           "stop_risk_with_execution_costs":proposed_risk}
        equity=aftercost;positions[c["id"]]=p;curve.append((t,equity))
        for step in steps:
            serial+=1;heapq.heappush(heap,(step[0],1,serial,c["id"],step))
        pack=funding[c["symbol"]];stamps=pack["times"]
        left=np.searchsorted(stamps,t,side="right");right=np.searchsorted(stamps,exit_ms,side="right")
        for event in pack["events"][left:right]:
            serial+=1;heapq.heappush(heap,(event["funding_ts_ms"],0,serial,c["id"],event))
        waves.add(wave);cooldown[key]=max(exit_ms,t+4*3600000)
    advance(end)
    assert not positions
    curve.append((end,equity))
    for p in ledger:
        sells=sum(f["notional"] for f in p["fills"] if f["side"]=="SELL")
        buys=sum(f["notional"] for f in p["fills"] if f["side"]=="BUY")
        assert abs(sells-buys-p["fees"]+p["funding"]-p["pnl"])<1e-8
        assert abs(sum(f["qty"] for f in p["fills"] if f["side"]=="BUY")-p["qty"])<1e-9
    assert abs(equity-100-sum(p["pnl"] for p in ledger))<1e-8
    values=np.array([v for _,v in curve]);dd=float(np.max(1-values/np.maximum.accumulate(values))*100)
    series=pd.Series(values,index=pd.to_datetime([t for t,_ in curve],unit="ms",utc=True)).groupby(level=0).last()
    grid=pd.date_range(pd.Timestamp(start,unit="ms",tz="UTC"),pd.Timestamp(end,unit="ms",tz="UTC"),freq="7D")
    if grid[-1]!=pd.Timestamp(end,unit="ms",tz="UTC"):grid=grid.append(pd.DatetimeIndex([pd.Timestamp(end,unit="ms",tz="UTC")]))
    nav=series.reindex(series.index.union(grid)).sort_index().ffill().loc[grid]
    weeks=nav.pct_change().dropna().tolist()
    return {"return_pct":equity-100,"max_dd_pct":dd,"trades":len(ledger),"rejected":dict(rejected),"weekly_returns":weeks,"weekly_ci":r.block_ci(weeks),
        "gross_reference_pnl_pct":sum(p["reference_notional"]*p["gross_reference_return"] for p in ledger),
        "fees_pct":sum(p["fees"] for p in ledger),"slippage_pct":sum(p["slippage"] for p in ledger),"funding_pct":sum(p["funding"] for p in ledger),
        "funding_events":sum(len(p["funding_events"]) for p in ledger),"proxy_mark_funding_events":sum(e["price_source"]!="funding_api_settlement_mark" for p in ledger for e in p["funding_events"]),
        "accepted_missing_execution_bars":sum(p["missing_execution_bars"] for p in ledger),"ledger":ledger,"curve":curve}
