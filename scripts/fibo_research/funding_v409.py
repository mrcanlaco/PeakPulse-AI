"""Bounded historical funding acquisition, with explicit mark-price provenance."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime,timezone
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import pickle
import threading
import time

import numpy as np
import pandas as pd
import requests
import research_v408 as q

r=q.r
ART=r.ROOT/"artifacts/fibo_trend_short/research_v4_0_9"
BASE=q.ART
LIMIT_MS=int(q.END.timestamp()*1000)
START_MS=int(q.START.timestamp()*1000)
FUNDING_URL="https://fapi.binance.com/fapi/v1/fundingRate"
MARK_URL="https://fapi.binance.com/fapi/v1/markPriceKlines"
_lock=threading.Lock();_next={}


def throttle(kind):
    with _lock:
        now=time.monotonic();slot=max(now,_next.get(kind,now))
        _next[kind]=slot+(.75 if kind=="funding" else .55)
    delay=slot-now
    if delay>0:time.sleep(delay)


def get_json(session,url,params,directory):
    assert START_MS<=params["startTime"]<=params["endTime"]<LIMIT_MS
    key=hashlib.sha256(json.dumps([url,params],sort_keys=True).encode()).hexdigest()
    path=directory/f"{key}.json.gz"
    if path.exists():
        with gzip.open(path,"rt",encoding="utf8") as f:saved=json.load(f)
        assert saved["url"]==url and saved["params"]==params
        return saved["data"]
    for attempt in range(4):
        throttle("funding" if url==FUNDING_URL else "mark")
        response=session.get(url,params=params,timeout=30)
        if response.status_code in (418,429):
            time.sleep(max(5,float(response.headers.get("Retry-After",30))))
            continue
        if response.status_code>=500:
            time.sleep(2**attempt);continue
        response.raise_for_status();data=response.json()
        if not isinstance(data,list):raise ValueError(f"Unexpected response: {data}")
        payload={"url":url,"params":params,"retrieved_at_utc":datetime.now(timezone.utc).isoformat(),"data":data}
        directory.mkdir(parents=True,exist_ok=True)
        with gzip.open(path,"wt",encoding="utf8") as f:json.dump(payload,f,separators=(",",":"),allow_nan=False)
        return data
    raise RuntimeError(f"Request failed after retries: {url} {params}")


def requirements():
    manifest=r.read(BASE/"history/CANDIDATE_MANIFEST.json")
    out={}
    for symbol,record in manifest["symbols"].items():
        path=BASE/"history/candidates"/f"{symbol}.pkl.gz"
        assert r.sha(path)==record["sha256"]
        with gzip.open(path,"rb") as f:candidates=pickle.load(f)
        if not candidates:continue
        start=min(c["entry_ts"] for c in candidates)*1000
        end=max(c["paths"]["ladder"]["exit_ts"] for c in candidates)*1000
        out[symbol]={"first_entry_ms":start,"last_exit_ms":end,
            "start_ms":max(START_MS,start-16*3600000),"end_ms":min(LIMIT_MS-1,end+16*3600000),"candidates":len(candidates)}
    return out


def fetch_symbol(symbol,required):
    folder=ART/"funding";output=folder/"snapshots"/f"{symbol}.parquet"
    done=folder/"completed"/f"{symbol}.json"
    if done.exists():
        record=r.read(done)
        assert record["requirements"]==required and r.sha(output)==record["sha256"]
        return symbol,record
    local_dir = Path("E:/Quant-trading/data_lake/funding") if Path("E:/Quant-trading/data_lake/funding").exists() else Path("C:/Quant-trading/data_lake/funding")
    local=local_dir/f"{symbol}_funding.parquet"
    lo=pd.Timestamp(required["start_ms"],unit="ms",tz="UTC")
    hi=pd.Timestamp(required["end_ms"],unit="ms",tz="UTC")
    local_frame=pd.read_parquet(local,filters=[("funding_time",">=",lo),("funding_time","<=",hi)]) if local.exists() else pd.DataFrame()
    if len(local_frame):
        (folder/"local_snapshots").mkdir(parents=True,exist_ok=True)
        local_frame.to_parquet(folder/"local_snapshots"/f"{symbol}.parquet",index=False)
    session=requests.Session();raw=[];cursor=required["start_ms"]
    rawdir=folder/"raw"/symbol
    while cursor<=required["end_ms"]:
        data=get_json(session,FUNDING_URL,{"symbol":symbol,"startTime":cursor,"endTime":required["end_ms"],"limit":1000},rawdir)
        if not data:break
        assert all(cursor<=int(x["fundingTime"])<=required["end_ms"] and x["symbol"]==symbol for x in data)
        raw.extend(data)
        nxt=max(int(x["fundingTime"]) for x in data)+1
        assert nxt>cursor;cursor=nxt
        if len(data)<1000:break
    if not raw:raise ValueError(f"No historical funding returned: {symbol}")
    f=pd.DataFrame(raw)
    if "rateType" in f:assert f.rateType.fillna("Regular").eq("Regular").all()
    f=pd.DataFrame({"funding_ts_ms":f.fundingTime.astype('int64'),"funding_rate":pd.to_numeric(f.fundingRate),"mark_price":pd.to_numeric(f.markPrice,errors="coerce")})
    duplicates=f[f.duplicated("funding_ts_ms",keep=False)]
    if len(duplicates) and (duplicates.groupby("funding_ts_ms").nunique()>1).any().any():raise ValueError("Conflicting official funding records")
    f=f.drop_duplicates("funding_ts_ms").sort_values("funding_ts_ms").reset_index(drop=True)
    assert np.isfinite(f.funding_rate).all()
    f["price_source"]="funding_api_settlement_mark"
    f["mark_reference_ts_ms"]=f.funding_ts_ms
    missing=~np.isfinite(f.mark_price)|(f.mark_price<=0)
    # Binance omits settlement markPrice in old funding responses. Its historic
    # mark-price candle OPEN is a nearby public proxy, explicitly not an exact
    # settlement tick. Never use the candle's future high/low/close.
    if missing.any():
        hours=(f.loc[missing,"funding_ts_ms"]//3600000)*3600000
        assert ((f.loc[missing,"funding_ts_ms"]-hours)<=15000).all(),"Non-hour funding requires a finer price source"
        start=int(hours.min());end=int(hours.max());marks={}
        cursor=start
        while cursor<=end:
            upper=min(end+3599999,LIMIT_MS-1,cursor+1500*3600000-1)
            data=get_json(session,MARK_URL,{"symbol":symbol,"interval":"1h","startTime":cursor,"endTime":upper,"limit":1500},rawdir)
            for x in data:
                assert cursor<=int(x[0])<=upper
                marks[int(x[0])]=float(x[1])
            cursor=upper+1
        for idx in f.index[missing]:
            t=int(f.at[idx,"funding_ts_ms"]//3600000*3600000)
            price=marks.get(t)
            if price is None or not np.isfinite(price) or price<=0:raise ValueError(f"Missing historical mark OPEN: {symbol} {t}")
            f.at[idx,"mark_price"]=price;f.at[idx,"price_source"]="official_mark_candle_open_proxy"
            f.at[idx,"mark_reference_ts_ms"]=t
    gaps=[]
    stamps=f.funding_ts_ms.to_numpy()
    for i,delta in enumerate(np.diff(stamps)):
        if delta>8*3600000+15000 and stamps[i]<required["last_exit_ms"] and stamps[i+1]>required["first_entry_ms"]:
            gaps.append({"start_ms":int(stamps[i]),"end_ms":int(stamps[i+1]),"hours":float(delta/3600000)})
    edge_start=stamps[0]>required["first_entry_ms"]
    edge_end=stamps[-1]<required["last_exit_ms"]
    local_matches=0;local_mismatches=[]
    if len(local_frame):
        local_frame["t"]=pd.DatetimeIndex(local_frame.funding_time).as_unit("ms").asi8
        lookup=dict(zip(f.funding_ts_ms,f.funding_rate))
        for row in local_frame.itertuples():
            if row.t in lookup and abs(row.funding_rate-lookup[row.t])<1e-12:local_matches+=1
            else:local_mismatches.append(int(row.t))
    (folder/"snapshots").mkdir(parents=True,exist_ok=True)
    f.to_parquet(output,index=False)
    record={"requirements":required,"rows":len(f),"sha256":r.sha(output),"price_sources":f.price_source.value_counts().to_dict(),
        "first_event_ms":int(stamps[0]),"last_event_ms":int(stamps[-1]),"gaps_over_8h":gaps,"left_edge_uncovered":bool(edge_start),"right_edge_uncovered":bool(edge_end),
        "local_rows":len(local_frame),"local_matches":local_matches,"local_differences_ms":local_mismatches,
        "raw_responses":{str(p.relative_to(ART)):r.sha(p) for p in sorted(rawdir.glob('*.json.gz'))}}
    r.save(done,record)
    return symbol,record


def main(workers=4):
    ART.mkdir(parents=True,exist_ok=True)
    needpath=ART/"funding/REQUIREMENTS.json"
    if needpath.exists():need=r.read(needpath)
    else:
        need=requirements();r.save(needpath,need)
    results={};errors={}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        fs={pool.submit(fetch_symbol,s,v):s for s,v in need.items()}
        for future in as_completed(fs):
            symbol=fs[future]
            try:
                symbol,record=future.result();results[symbol]=record
                print(f"Historical funding {len(results)}/{len(need)} {symbol}: {record['rows']} events",flush=True)
            except Exception as exc:
                errors[symbol]=str(exc);print(f"Funding issue {symbol}: {exc}",flush=True)
            r.save(ART/"funding/PROGRESS.json",{"completed":len(results),"total":len(need),"errors":errors})
    r.save(ART/"funding/MANIFEST.json",{"symbols":results,"errors":errors,"requirements_sha256":r.sha(needpath),"fetch_source_sha256":r.sha(__file__),
        "source":"Binance public USD-M REST endpoints; locally available rates cross-checked against a fresh bounded history query", "data_ceiling":"2025-12-31",
        "price_proxy_disclosure":"Old REST funding responses omit settlement markPrice. The official mark-price candle OPEN at the preceding hour boundary (<=15s before recorded funding timestamp) is used where necessary. Exact historical settlement ticks are not claimed.",
        "all_symbols_downloaded":not errors and len(results)==len(need)})


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--workers",type=int,default=4);a=p.parse_args();main(a.workers)
