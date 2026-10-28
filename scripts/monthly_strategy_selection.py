"""Select next month's signal source using strictly earlier marked results."""
import hashlib


def choose(rows,method):
    if method not in ["profit","floor"]:raise ValueError("unknown_selection_method")
    by_source={}
    for row in rows:by_source.setdefault(row["source_id"],[]).append(row)
    pool=[]
    for source,rs in by_source.items():
        if len(rs)!=2 or {r["cost"] for r in rs}!={"base","stress"}:continue
        if not all(r["ending_equity"] is not None and r["ending_equity"]>500 and r["max_drawdown"]<.2 and r["exits"]>=5 and r["monthly"]["complete"] for r in rs):continue
        floor=min(r["monthly"]["min_monthly_return"] for r in rs)
        profit=min(r["ending_equity"]-500 for r in rs)
        key=(profit,floor) if method=="profit" else (floor,profit)
        pool.append((*key,source))
    return max(pool)[-1] if pool else None


def route(signals,choices):
    result=[]
    ordered=sorted(choices,key=lambda c:c["start"])
    for a,b in zip(ordered,ordered[1:]):
        if a["end"]!=b["start"]:raise ValueError("noncontiguous_selection_calendar")
    for c in ordered:
        if c["training_end"]>=c["start"]:raise ValueError("future_training_boundary")
        if c["source_id"] is None:continue
        for r in signals[c["source_id"]]:
            # One completed5m interval is reserved for producing the decision.
            if c["start"]+300000<=r["at"]<c["end"]:
                row=dict(r)
                row["event_id"]=hashlib.sha256(f"monthly:{c['source_id']}:{r['event_id']}".encode()).hexdigest()[:24]
                result.append(row)
    return sorted(result,key=lambda r:(r["at"],-r["probability"],r["symbol"]))


def bounded_prices(prices,end):
    def getter(coin):
        original=prices.get(coin)
        if original is None:return {}
        class Past:
            def get(self,at,default=None):
                if at>end:raise ValueError("future_price_access")
                return original.get(at,default)
            def __getitem__(self,at):
                value=self.get(at)
                if value is None:raise KeyError(at)
                return value
        return Past()
    return getter
