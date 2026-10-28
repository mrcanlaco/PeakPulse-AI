"""Public-only June-Aug2026 data for the frozen thirty-coin candidate."""

import hashlib
import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor,as_completed

import httpx
import numpy as np
import pandas as pd
from compare_account_risk import ROOT,sha,write
from prepare_historical_research import OUT as OLD,LAKE,get,grid_audit

OUT=ROOT/"artifacts/frozen_extension_20260925"
FREEZE=ROOT/"artifacts/guard_ablation_20260925/candidate_freeze.json"
START=pd.Timestamp("2026-06-01",tz="UTC")
END=pd.Timestamp("2026-09-01",tz="UTC")
MONTHS=["2026-06","2026-07","2026-08"]


def archive(client,symbol,month,kind):
    tail=f"fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip" if kind=="fundingRate" else f"{kind}/{symbol}/5m/{symbol}-5m-{month}.zip"
    url="https://data.binance.vision/data/futures/um/monthly/"+tail
    folder=OUT/"archives"/kind/symbol;folder.mkdir(parents=True,exist_ok=True)
    path=folder/url.rsplit("/",1)[-1];checksum=path.with_suffix(".zip.CHECKSUM")
    if not checksum.exists():checksum.write_text(get(client,url+".CHECKSUM").text,encoding="utf-8")
    digest=checksum.read_text(encoding="utf-8").split()[0].lower()
    if not path.exists():
        data=get(client,url).content
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError("download_checksum_mismatch")
        tmp=path.with_suffix(".zip.partial");tmp.write_bytes(data);tmp.replace(path)
    if sha(path)!=digest:raise ValueError("cached_checksum_mismatch")
    with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as z:
        if len(z.namelist())!=1:raise ValueError("ambiguous_archive")
        frame=pd.read_csv(z.open(z.namelist()[0]))
    if "open_time" in frame:
        stamps=frame.open_time.astype("int64");frame["open_time"]=stamps//1000 if stamps.max()>10**14 else stamps
    return frame,dict(url=url,file=str(path),sha256=digest,checksum_verified=True)


def prepare(symbol):
    trades=[];marks=[];rates=[];proof=[]
    with httpx.Client(timeout=45,follow_redirects=True) as client:
        for month in MONTHS:
            trade,evidence=archive(client,symbol,month,"klines");trades.append(trade);proof.append(evidence)
            if symbol!="BTCUSDT":
                mark,evidence=archive(client,symbol,month,"markPriceKlines");marks.append(mark);proof.append(evidence)
                rate,evidence=archive(client,symbol,month,"fundingRate");rates.append(rate);proof.append(evidence)
        trade=pd.concat(trades,ignore_index=True).sort_values("open_time")
        trade=trade[["open_time","open","high","low","close","quote_volume"]]
        ta=grid_audit(trade,START,END)
        if not np.isfinite(trade.quote_volume).all() or (trade.quote_volume<0).any():raise ValueError("invalid_volume")
        local_path=LAKE/f"{symbol}.parquet";local=pd.read_parquet(local_path)
        local.open_time=pd.to_datetime(local.open_time,utc=True).dt.as_unit("ms").astype("int64")
        local=local[(local.open_time>=int(START.timestamp()*1000))&(local.open_time<int(END.timestamp()*1000))]
        joined=trade.merge(local,on="open_time",how="outer",validate="one_to_one",suffixes=("_public","_local"),indicator=True)
        diff=np.zeros(len(joined),dtype=bool)
        for field in ["open","high","low","close","quote_volume"]:diff|=~np.isclose(joined[field+"_public"],joined[field+"_local"],rtol=1e-7,atol=1e-10)
        same=dict(unmatched=int(joined._merge.ne("both").sum()),different=int(diff.sum()),local_sha256=sha(local_path))
        trade.to_parquet(OUT/"trade"/f"{symbol}.parquet",index=False)
        result=dict(symbol=symbol,trade=ta,local_comparison=same,trade_sha256=sha(OUT/"trade"/f"{symbol}.parquet"),archives=proof,
                    complete=ta["complete"] and same["unmatched"]==0 and same["different"]==0)
        if symbol=="BTCUSDT":write(OUT/"evidence"/f"{symbol}.json",result);return result
        mark=pd.concat(marks,ignore_index=True).sort_values("open_time")[["open_time","open","high","low","close"]]
        ma=grid_audit(mark,START,END);mark.to_parquet(OUT/"mark"/f"{symbol}.parquet",index=False)
        rest_path=OUT/"funding"/f"{symbol}_rest.json"
        if rest_path.exists():
            saved=json.loads(rest_path.read_text(encoding="utf-8"))
            if saved["period"]!=[START.isoformat(),END.isoformat()]:raise ValueError("cached_period_mismatch")
            rows=saved["rows"]
        else:
            rows=[];pages=[];cursor=int(START.timestamp()*1000);finish=int(END.timestamp()*1000)
            while cursor<=finish:
                params=dict(symbol=symbol,startTime=cursor,endTime=finish,limit=1000)
                response=get(client,"https://fapi.binance.com/fapi/v1/fundingRate",params=params);page=response.json()
                if not isinstance(page,list):raise ValueError("invalid_public_funding_response")
                if any(r["symbol"]!=symbol or not cursor<=r["fundingTime"]<=finish for r in page):raise ValueError("funding_outside_range")
                pages.append(dict(params=params,rows=len(page),sha256=hashlib.sha256(response.content).hexdigest()));rows.extend(page)
                if len(page)<1000:break
                cursor=max(r["fundingTime"] for r in page)+1
            write(rest_path,dict(period=[START.isoformat(),END.isoformat()],rows=rows,pages=pages,retrieved_at=pd.Timestamp.now(tz="UTC").isoformat()))
        rest=pd.DataFrame(rows)
        if rest.empty:raise ValueError("empty_funding_history")
        rest["fundingRate"]=rest.fundingRate.astype(float);rest["markPrice"]=pd.to_numeric(rest.markPrice,errors="coerce")
        rest["second"]=rest.fundingTime.astype("int64")//1000
        public=pd.concat(rates,ignore_index=True);public["second"]=public.calc_time.astype("int64")//1000
        joined=public.merge(rest[rest.fundingTime<int(END.timestamp()*1000)],on="second",how="outer",validate="one_to_one",indicator=True)
        fa=dict(archive_rows=len(public),rest_rows=len(rest),unmatched=int(joined._merge.ne("both").sum()),
                differing_rates=int(((joined.last_funding_rate-joined.fundingRate).abs()>1e-10).sum()),
                valid_values=bool(np.isfinite(rest.fundingRate).all() and np.isfinite(rest.markPrice).all() and rest.markPrice.gt(0).all()),
                max_gap_hours=float(np.diff(np.sort(rest.fundingTime)).max()/3600000),interval_hours=sorted(public.funding_interval_hours.unique().tolist()),
                timestamp_rule="Second-floor comparison only; preserve actual REST milliseconds and settlement mark.")
        fa["complete"]=fa["unmatched"]==0 and fa["differing_rates"]==0 and fa["valid_values"]
        rest[["fundingTime","fundingRate","markPrice"]].sort_values("fundingTime").to_parquet(OUT/"funding"/f"{symbol}.parquet",index=False)
        result.update(mark=ma,funding=fa,mark_sha256=sha(OUT/"mark"/f"{symbol}.parquet"),funding_sha256=sha(OUT/"funding"/f"{symbol}.parquet"),rest_sha256=sha(rest_path))
        result["complete"] &= ma["complete"] and fa["complete"]
        write(OUT/"evidence"/f"{symbol}.json",result);return result


def main():
    OUT.mkdir(exist_ok=True)
    for d in ["trade","mark","funding","evidence"]:(OUT/d).mkdir(exist_ok=True)
    freeze=json.loads(FREEZE.read_text(encoding="utf-8"))
    assert sha(OLD/"manifest.json")==freeze["original_universe_manifest_sha256"]
    for n,digest in freeze["source_sha256"].items():assert sha(ROOT/"scripts"/n)==digest
    universe=json.loads((OLD/"universe.json").read_text(encoding="utf-8"))["symbols"]
    protocol=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),start=START.isoformat(),end=END.isoformat(),symbols=universe,
                  candidate_sha256=sha(FREEZE),old_manifest_sha256=sha(OLD/"manifest.json"),live_config_sha256=sha(ROOT/"configs/live.yaml"),
                  requirements="Every selected coin: full3month trade/mark5m grid, officialZIP/CHECKSUM, alltradeOHLC+quotevolume compared to localwarehouse, funding archivevsREST rates with settlementMark. No drop/dedupe/fill on missing data. BTC trade only for sharedfeature interface.",
                  evaluation="Frozen candidates mask0/2/15 xnotional25/100; freshJune1 three months and continuousSep2025 twelve months. Same future segment with/without oldinventory; not pristine history, other strategies examined it before. No tuning based on nextperiod.",
                  script_sha256=sha(ROOT/"scripts/prepare_frozen_extension.py"))
    write(OUT/"data_protocol.json",protocol);proof=[];errors=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs={pool.submit(prepare,c):c for c in [*universe,"BTCUSDT"]}
        for future in as_completed(jobs):
            coin=jobs[future]
            try:
                item=future.result();proof.append(item);print("VERIFIED",coin,item["complete"],flush=True)
            except Exception as exc:errors.append(dict(symbol=coin,error=type(exc).__name__+":"+str(exc)[:250]));print("ERROR",coin,str(exc)[:180],flush=True)
            write(OUT/"download_progress.json",dict(finished=len(proof),errors=errors,total=len(jobs)))
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    ready=not errors and len(proof)==31 and all(r["complete"] for r in proof)
    write(OUT/"manifest.json",dict(protocol=protocol,proof=proof,errors=errors,data_ready=ready))
    print("COMPLETE data_ready",ready,flush=True)


if __name__=="__main__":main()
