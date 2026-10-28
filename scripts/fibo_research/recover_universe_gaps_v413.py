"""Recover historically omitted contracts without discarding valid rows for gaps."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import shutil
import time
import requests
import pandas as pd
import universe_audit_v413 as v
import sample_archives_v413 as sample

r=v.r;ART=v.ART;OUT=ART/'recovery'


def freeze():
    v.verify_sources()
    if (OUT/'SOURCE_MANIFEST.json').exists():raise FileExistsError('Recovery already registered')
    full=r.read(ART/'source_evidence/binance-usdm-gap-backfill-2020-2025.json')
    omitted={a['symbol']:a for a in full['symbols'] if a['status']=='QUALITY_FAILED'}
    availability=r.read(ART/'source_evidence/binance-usdm-gap-availability-2020-2025.json')
    records=[a for a in availability['months'] if a['symbol'] in omitted and a['status']=='AVAILABLE']
    for a in records:
        assert '2020-01'<=a['month']<='2025-12'
        assert a['url']==f"https://data.binance.vision/data/futures/um/monthly/klines/{a['symbol']}/5m/{a['symbol']}-5m-{a['month']}.zip"
        a['prior_download_sha256']=omitted[a['symbol']]['archive_sha256'][a['month']]
    protocol={'registered_at_utc':datetime.now(timezone.utc).isoformat(),'version':'4.0.13-recovery-supplement',
        'reason':'Previous acquisition excluded ten entire symbols because each retained a historical gap. Preserve all valid observed bars and explicit gaps instead.',
        'symbols':sorted(omitted),'monthly_archives':len(records),'monthly_compressed_bytes_declared':sum(a.get('content_length',0) or 0 for a in records),
        'source':'Official Binance USD-M monthly and daily klines archives, with SHA256 CHECKSUM for each downloaded archive',
        'window':'2020-01-01 inclusive through 2026-01-01 exclusive',
        'daily_repairs':'After monthly merge, request every date containing an internal missing 5m timestamp. An unavailable daily archive stays missing. Retain the actual HTTP response. Never interpolate, forward-fill, or remove an entire symbol because gaps persist.',
        'duplicates':'Exact canonical OHLCV equality required across monthly/daily overlaps; any differing value blocks merged output and is retained as a conflict.',
        'preservation':'Initial633-symbol audit remains intact. Recovery snapshots and later union comparison are separate artifacts, never overwrites.',
        'interpretation':'Recovery removes a whole-symbol acquisition selection filter; it does not resolve execution through gaps, contract migrations, zero-volume periods or fresh OOS.',
        'strategies':'No outcomes calculated or thresholds changed. Same frozen original elite-sniper primary remains preregistered.',
        'fresh_oos':False,'goal_complete':False,'live_signoff':'NOT_GRANTED'}
    r.save(OUT/'PROTOCOL.json',protocol);r.save(OUT/'DOWNLOAD_PLAN.json',{'records':records,'prior_omission_records':omitted})
    sources=[Path(__file__),v.ROOT/'tests/unit/fibo_short/test_recovery_v413.py',Path(sample.__file__),Path(v.__file__)]
    for p in sources:
        target=OUT/'source_snapshot'/p.relative_to(v.ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    r.save(OUT/'SOURCE_MANIFEST.json',{'sources':{str(p.relative_to(v.ROOT)):r.sha(p) for p in sources},
        'parent_source_manifest_sha256':r.sha(ART/'SOURCE_MANIFEST.json'),'protocol_sha256':r.sha(OUT/'PROTOCOL.json'),'plan_sha256':r.sha(OUT/'DOWNLOAD_PLAN.json')})
    print(f'Recovery frozen for {len(omitted)} contracts and {len(records)} monthly archives.',flush=True)


def verify_sources():
    v.verify_sources();m=r.read(OUT/'SOURCE_MANIFEST.json')
    for p,h in m['sources'].items():assert r.sha(v.ROOT/p)==h,p
    for k,p in [('parent_source_manifest_sha256',ART/'SOURCE_MANIFEST.json'),('protocol_sha256',OUT/'PROTOCOL.json'),('plan_sha256',OUT/'DOWNLOAD_PLAN.json')]:assert m[k]==r.sha(p)


def missing_dates(frame):
    dates=set()
    for a,b in zip(frame.index[:-1],frame.index[1:]):
        if b-a>pd.Timedelta(minutes=5):
            first=a+pd.Timedelta(minutes=5);last=b-pd.Timedelta(minutes=5)
            dates.update(t.strftime('%Y-%m-%d') for t in pd.date_range(first.normalize(),last.normalize(),freq='D'))
    assert all('2020-01-01'<=d<='2025-12-31' for d in dates)
    return sorted(dates)


def archive(url,target,month,expected_hash=None,allow_missing=False):
    target.parent.mkdir(parents=True,exist_ok=True);receipt=target.with_suffix('.receipt.json');checksum_path=target.with_suffix('.zip.CHECKSUM')
    if receipt.exists():
        saved=r.read(receipt);assert saved['url']==url
        if saved['status']=='UNAVAILABLE':return None,saved
        assert r.sha(target)==saved['sha256'] and r.sha(checksum_path)==saved['checksum_file_sha256']
        return sample.parse(target.read_bytes(),month),saved
    if not target.exists():
        for attempt in range(3):
            try:
                response=requests.get(url,timeout=45)
                if allow_missing and response.status_code==404:
                    body=target.with_suffix('.http404.txt');body.write_bytes(response.content)
                    saved={'url':url,'status':'UNAVAILABLE','http_status':404,'body_sha256':r.sha(body),'retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
                    r.save(receipt,saved);return None,saved
                response.raise_for_status();target.write_bytes(response.content);break
            except requests.RequestException:
                if attempt==2:raise
                time.sleep(.5*(attempt+1))
    if not checksum_path.exists():checksum_path.write_bytes(sample.download(url+'.CHECKSUM'))
    content=target.read_bytes();digest=hashlib.sha256(content).hexdigest();official=checksum_path.read_text(encoding='utf8').split()[0]
    assert digest==official,'Official checksum mismatch'
    if expected_hash is not None:assert digest==expected_hash,'Monthly archive changed since original acquisition; reconcile explicitly'
    frame=sample.parse(content,month)
    saved={'url':url,'status':'VERIFIED_CHECKSUM','sha256':digest,'checksum_file_sha256':r.sha(checksum_path),'rows':len(frame),'retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
    r.save(receipt,saved);return frame,saved


def recover_symbol(symbol,records):
    result_path=OUT/'symbols'/f'{symbol}.json'
    if result_path.exists():
        saved=r.read(result_path)
        if saved['status']=='RECOVERED_OBSERVED_ROWS':assert r.sha(OUT/'bars_5m'/f'{symbol}.parquet')==saved['snapshot_sha256'];return saved
    parts=[];receipts=[]
    for item in records:
        path=OUT/'raw/monthly'/f'{symbol}-{item["month"]}.zip'
        frame,receipt=archive(item['url'],path,item['month'],item['prior_download_sha256'])
        parts.append((str(path.relative_to(OUT)),frame));receipts.append(receipt)
    monthly,conflicts=v.merge_frames(parts)
    assert not any(x['conflicting_rows'] for x in conflicts),'Monthly overlap conflict'
    before=v.quality(monthly);dates=missing_dates(monthly);daily=[]
    for day in dates:
        url=f'https://data.binance.vision/data/futures/um/daily/klines/{symbol}/5m/{symbol}-5m-{day}.zip'
        path=OUT/'raw/daily'/f'{symbol}-{day}.zip';frame,receipt=archive(url,path,day[:7],allow_missing=True);receipts.append(receipt)
        if frame is not None:
            assert frame.index.normalize().eq(r.utc(day)).all() if hasattr(frame.index.normalize(),'eq') else (frame.index.normalize()==r.utc(day)).all()
            daily.append((str(path.relative_to(OUT)),frame))
    combined,comparisons=v.merge_frames([('monthly_union',monthly),*daily])
    result={'symbol':symbol,'monthly_rows':len(monthly),'daily_dates_requested':dates,'archive_receipts':receipts,
        'missing_before':before['missing_bars_inside_span'],'overlap_comparisons':comparisons,'source_manifest_sha256':r.sha(OUT/'SOURCE_MANIFEST.json')}
    if any(x['conflicting_rows'] for x in comparisons):result.update(status='CONFLICT_REQUIRES_RESOLUTION')
    else:
        path=OUT/'bars_5m'/f'{symbol}.parquet';path.parent.mkdir(parents=True,exist_ok=True);combined.to_parquet(path)
        result.update(status='RECOVERED_OBSERVED_ROWS',snapshot_sha256=r.sha(path),quality=v.quality(combined))
    r.save(result_path,result);return result


def run():
    verify_sources();plan=r.read(OUT/'DOWNLOAD_PLAN.json');symbols=sorted(plan['prior_omission_records']);results=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(recover_symbol,s,[a for a in plan['records'] if a['symbol']==s]):s for s in symbols}
        for future in as_completed(futures):
            try:item=future.result()
            except Exception as exc:item={'symbol':futures[future],'status':'ERROR','error':f'{type(exc).__name__}: {exc}'}
            results.append(item);print(f'Recovery {len(results)}/{len(symbols)} {item["symbol"]}: {item["status"]}',flush=True)
    results.sort(key=lambda a:a['symbol']);summary={'symbols':len(results),'recovered':sum(a['status']=='RECOVERED_OBSERVED_ROWS' for a in results),
        'rows':sum(a.get('quality',{}).get('rows_5m',0) for a in results),'remaining_missing_bars':sum(a.get('quality',{}).get('missing_bars_inside_span',0) for a in results),
        'source_manifest_sha256':r.sha(OUT/'SOURCE_MANIFEST.json'),'post_2025_observations_loaded':0,'fresh_oos':False}
    r.save(OUT/'RESULTS.json',{'summary':summary,'symbols':results});print(summary,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','run']);args=parser.parse_args()
    freeze() if args.action=='freeze' else run()
