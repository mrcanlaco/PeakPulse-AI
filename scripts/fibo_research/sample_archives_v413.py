"""Independent official monthly archive and checksum sample for every new symbol."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import io
import time
import zipfile
import numpy as np
import pandas as pd
import requests
import universe_audit_v413 as v

r=v.r;ART=v.ART
CSV_COLS=['open_time','open','high','low','close','volume','close_time','quote_volume','count','taker_buy_volume','taker_buy_quote_volume','ignore']


def parse(content,month):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if archive.testzip() is not None:raise ValueError('ZIP CRC failure')
        names=[n for n in archive.namelist() if not n.endswith('/')]
        if len(names)!=1:raise ValueError('Unexpected archive members')
        with archive.open(names[0]) as fh:raw=pd.read_csv(fh,header=None,names=CSV_COLS,dtype=str)
    numeric=pd.to_numeric(raw.open_time,errors='coerce')
    invalid=raw.loc[numeric.isna()]
    if len(invalid)>1 or (len(invalid) and invalid.open_time.iloc[0]!='open_time'):raise ValueError('Unknown nonnumeric archive rows')
    raw=raw.loc[numeric.notna()].copy()
    raw['open_time']=pd.to_datetime(raw.open_time.astype('int64'),unit='ms',utc=True)
    lower=r.utc(month+'-01');upper=lower+pd.offsets.MonthBegin()
    if lower<v.START or upper>v.END or not ((raw.open_time>=lower)&(raw.open_time<upper)).all():raise ValueError('Archive date breach')
    for col in v.VALUE_COLS:raw[col]=pd.to_numeric(raw[col],errors='raise').astype(float)
    return v.normalize(raw)


def download(url):
    error=None
    for attempt in range(3):
        try:
            response=requests.get(url,timeout=45);response.raise_for_status();return response.content
        except requests.RequestException as exc:error=str(exc);time.sleep(.5*(attempt+1))
    raise RuntimeError(error)


def one(plan):
    symbol=plan['symbol'];month=plan['month'];directory=ART/'official_samples';directory.mkdir(exist_ok=True)
    raw_path=directory/f'{symbol}-{month}.zip';check_path=raw_path.with_suffix('.zip.CHECKSUM');result_path=raw_path.with_suffix('.json')
    fingerprint={'sample_plan_sha256':r.sha(ART/'OFFICIAL_SAMPLE_PLAN.json'),'source_manifest_sha256':r.sha(ART/'SOURCE_MANIFEST.json')}
    if result_path.exists():
        item=r.read(result_path)
        assert all(item[k]==h for k,h in fingerprint.items())
        if item['status']=='PASS':
            assert r.sha(raw_path)==item['download_sha256'] and r.sha(check_path)==item['checksum_file_sha256']
            return item
    if not raw_path.exists():raw_path.write_bytes(download(plan['url']))
    if not check_path.exists():check_path.write_bytes(download(plan['url']+'.CHECKSUM'))
    content=raw_path.read_bytes();digest=hashlib.sha256(content).hexdigest()
    checksum=check_path.read_text(encoding='utf8').strip().split()[0]
    result={**plan,**fingerprint,'download_sha256':digest,'checksum_file_sha256':r.sha(check_path),'official_checksum':checksum,
        'acquired_at_utc':datetime.now(timezone.utc).isoformat(),'status':'UNVERIFIED'}
    if digest!=checksum:
        result['status']='CHECKSUM_MISMATCH';r.save(result_path,result);return result
    assert r.sha(plan['local_path'])==plan['local_parquet_sha256']
    frame=parse(content,month);lower=r.utc(month+'-01');upper=lower+pd.offsets.MonthBegin()
    local=v.normalize(v.bounded_read(plan['local_path'],lower,upper,with_identity=True))
    missing=frame.index.difference(local.index);extra=local.index.difference(frame.index);common=frame.index.intersection(local.index)
    a=frame.loc[common].to_numpy();b=local.loc[common].to_numpy()
    matched=np.isclose(a,b,rtol=1e-12,atol=0).all(axis=1)
    max_relative=float(np.max(np.abs(a-b)/np.maximum(np.abs(a),np.finfo(float).tiny))) if len(a) else 0.
    result.update(official_rows=len(frame),local_rows=len(local),rows_compared=len(common),missing_local_rows=len(missing),
        local_extra_rows=len(extra),mismatched_rows=int((~matched).sum()),maximum_relative_numeric_difference=max_relative,
        tolerance='rtol=1e-12, atol=0 for independent decimal parsing; timestamp identity exact',
        same_archive_as_prior_download=digest==plan['local_archive_sha256'],
        local_extra_dates=sorted(set(extra.strftime('%Y-%m-%d'))),
        status='PASS' if len(common) and not len(missing) and matched.all() and digest==plan['local_archive_sha256'] else 'REQUIRES_RECONCILIATION')
    if len(extra):result['qualification']='Local extra rows must be reconciled to declared daily repair archives; not certified by this monthly sample.'
    r.save(result_path,result);return result


def main():
    v.verify_sources();plan=r.read(ART/'OFFICIAL_SAMPLE_PLAN.json');results=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(one,p):p for p in plan['samples']}
        for future in as_completed(futures):
            try:item=future.result()
            except Exception as exc:item={**futures[future],'status':'ERROR','error':f'{type(exc).__name__}: {exc}'}
            results.append(item)
            if len(results)%20==0 or item['status']!='PASS':print(f'Official archive samples {len(results)}/{len(plan["samples"])} {item["symbol"]}: {item["status"]}',flush=True)
    results.sort(key=lambda a:a['symbol'])
    summary={'samples':len(results),'passed':sum(x['status']=='PASS' for x in results),'rows_compared':sum(x.get('rows_compared',0) for x in results),
        'local_extra_rows':sum(x.get('local_extra_rows',0) for x in results),'all_passed':all(x['status']=='PASS' for x in results),
        'post_2025_observations_loaded':0,'scope':'One prespecified monthly sample per additional symbol; not every archive or historical contract lifecycle'}
    r.save(ART/'OFFICIAL_SAMPLE_RESULTS.json',{'summary':summary,'results':results,'source_manifest_sha256':r.sha(ART/'SOURCE_MANIFEST.json')});print(summary,flush=True)


if __name__=='__main__':main()
