"""Reconcile real public records; preserve the failed initial completeness audit."""

import hashlib
import json

import httpx
import numpy as np
import pandas as pd
from compare_account_risk import ROOT,sha,write
from prepare_frozen_extension import OUT,START,END
from prepare_historical_research import get,grid_audit


def main():
    initial=json.loads((OUT/"manifest.json").read_text(encoding="utf-8"))
    if initial["errors"] or len(initial["proof"])!=31:raise ValueError("initial_acquisition_unfinished_or_failed")
    directory=OUT/"reconciled";directory.mkdir(exist_ok=True)
    for d in ["mark","rest"]:(directory/d).mkdir(exist_ok=True)
    write(directory/"protocol.json",dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),initial_manifest_sha256=sha(OUT/"manifest.json"),
        reason="Initial audit found localtrade omissions and archiveMark day omissions. Use complete verified official trade archives; require all overlapping localvalues agree. Fill Mark gaps from publicREST actual candles only, verify neighboring archive bars. Preserve original files/audit. No interpolated/model-generated bars.",
        rules="No symbol drops. No overwrite archive marks. REST range must include missing timestamps and one adjacent5mbar each side; compare overlaps. All final grids complete and original funding evidence complete; otherwise data_ready false."))
    expected=np.arange(int(START.timestamp()*1000),int(END.timestamp()*1000),300000);proof=[]
    with httpx.Client(timeout=45,follow_redirects=True) as client:
        for old in initial["proof"]:
            coin=old["symbol"];p=dict(old)
            comparison=p["local_comparison"]
            # The initial outer-merge counted absent local bars as different.
            # Every unmatched row is absent locally because official grid is complete.
            if not old["trade"]["complete"] or comparison["different"]!=comparison["unmatched"]:
                raise ValueError("observed_trade_disagreement_or_incomplete_archive:"+coin)
            p["trade_basis"]="Complete checksum-verified officialtradearchive; overlapping localprices all match, absent localbars explicitly retained as missing in initialaudit. Publicdata is authoritative, not an inferred fill."
            p["observed_trade_disagreements"]=comparison["different"]-comparison["unmatched"]
            if coin=="BTCUSDT":p["complete"]=True;proof.append(p);continue
            mark_path=OUT/"mark"/f"{coin}.parquet";mark=pd.read_parquet(mark_path)
            assert sha(mark_path)==old["mark_sha256"]
            gaps=np.setdiff1d(expected,mark.open_time);evidence=[];additions=[]
            groups=np.split(gaps,np.where(np.diff(gaps)!=300000)[0]+1) if len(gaps) else []
            for block in groups:
                left=max(int(expected[0]),int(block[0])-300000);right=min(int(expected[-1]),int(block[-1])+300000)
                path=directory/"rest"/f"{coin}_{left}_{right}.json"
                if path.exists():saved=json.loads(path.read_text(encoding="utf-8"));rows=saved["rows"]
                else:
                    cursor=left;rows=[];pages=[]
                    while cursor<=right:
                        params=dict(symbol=coin,interval="5m",startTime=cursor,endTime=right+299999,limit=1500)
                        response=get(client,"https://fapi.binance.com/fapi/v1/markPriceKlines",params=params);page=response.json()
                        if not isinstance(page,list):raise ValueError("invalid_mark_response")
                        if any(not cursor<=int(r[0])<=right or int(r[6])+1-int(r[0])!=300000 for r in page):raise ValueError("mark_response_bounds")
                        pages.append(dict(params=params,rows=len(page),sha256=hashlib.sha256(response.content).hexdigest()));rows.extend(page)
                        if not page or len(page)<1500:break
                        cursor=max(int(r[0]) for r in page)+300000
                    write(path,dict(source="https://fapi.binance.com/fapi/v1/markPriceKlines",rows=rows,pages=pages,retrieved_at=pd.Timestamp.now(tz="UTC").isoformat()))
                frame=pd.DataFrame([[int(r[0]),*map(float,r[1:5])] for r in rows],columns=["open_time","open","high","low","close"])
                audit=grid_audit(frame,pd.Timestamp(left,unit="ms",tz="UTC"),pd.Timestamp(right+300000,unit="ms",tz="UTC"))
                if not audit["complete"]:raise ValueError("rest_mark_gap_not_complete:"+coin)
                overlap=frame.merge(mark,on="open_time",suffixes=("_rest","_archive"),validate="one_to_one")
                for field in ["open","high","low","close"]:
                    if not np.isclose(overlap[field+"_rest"],overlap[field+"_archive"],rtol=1e-7,atol=1e-10).all():raise ValueError("mark_overlap_disagreement:"+coin)
                added=frame[frame.open_time.isin(block)]
                if len(added)!=len(block):raise ValueError("missing_actual_repair_bars")
                additions.append(added);evidence.append(dict(file=str(path),sha256=sha(path),added_rows=len(added),overlap_checked=len(overlap),audit=audit))
            completed=pd.concat([mark,*additions],ignore_index=True).sort_values("open_time")
            final_audit=grid_audit(completed,START,END);path=directory/"mark"/f"{coin}.parquet";completed.to_parquet(path,index=False)
            p.update(mark_original=old["mark"],mark=final_audit,mark_sha256=sha(path),mark_path=str(path),gap_fills=evidence,
                     complete=final_audit["complete"] and old["funding"]["complete"])
            proof.append(p);print("RECONCILED",coin,"added",len(gaps),"complete",p["complete"],flush=True)
    ready=len(proof)==31 and all(r["complete"] for r in proof)
    assert sha(ROOT/"configs/live.yaml")==initial["protocol"]["live_config_sha256"]
    write(OUT/"reconciled_manifest.json",dict(protocol=initial["protocol"],initial_manifest_sha256=sha(OUT/"manifest.json"),
          reconciliation_protocol_sha256=sha(directory/"protocol.json"),proof=proof,data_ready=ready,live_config_unchanged=True))
    print("COMPLETE data_ready",ready,flush=True)


if __name__=="__main__":main()
