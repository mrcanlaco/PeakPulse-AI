"""Recover unavailable historical mark OPENs from checksum-verified archives."""
from datetime import datetime,timezone
from pathlib import Path
import argparse
import gzip
import hashlib
import io
import json
import shutil
import zipfile
import numpy as np
import pandas as pd
import requests
import research_v415 as v

r=v.r;ART=v.ART;OUT=ART/'funding/archive_recovery'


def parse_archive(content,symbol,month):
    if not '2020-01'<=month<='2025-12':raise ValueError('Forbidden archive month')
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        name=f'{symbol}-1h-{month}.csv';assert archive.namelist()==[name]
        raw=pd.read_csv(archive.open(name),header=None,dtype=str)
    if raw.iloc[0,0] in ('open_time','openTime'):raw=raw.iloc[1:].reset_index(drop=True)
    assert raw.shape[1]==12
    ts=pd.to_numeric(raw.iloc[:,0],errors='raise').to_numpy(dtype='int64');price=pd.to_numeric(raw.iloc[:,1],errors='raise').to_numpy(float)
    time=pd.to_datetime(ts,unit='ms',utc=True);start=r.utc(month+'-01');end=start+pd.offsets.MonthBegin(1)
    assert np.all((time>=start)&(time<end)) and np.all(ts%3600000==0) and np.all(np.diff(ts)>0)
    assert np.isfinite(price).all() and (price>0).all()
    return dict(zip(map(int,ts),map(float,price)))


def register():
    v.verify_sources()
    if (OUT/'PROTOCOL.json').exists():raise FileExistsError('Archive recovery already registered')
    OUT.mkdir(parents=True,exist_ok=True)
    sources=[Path(__file__),v.ROOT/'tests/unit/fibo_short/test_funding_archive_v415.py']
    for p in sources:shutil.copy2(p,OUT/p.name)
    r.save(OUT/'PROTOCOL.json',{'registered_at_utc':datetime.now(timezone.utc).isoformat(),'sources':{str(p.relative_to(v.ROOT)):r.sha(p) for p in sources},
        'purpose':'Recover only missing official historical mark OPENs after bounded REST acquisition. Never substitute spot/trade prices or zero funding.',
        'archive_base':'https://data.binance.vision/data/futures/um/monthly/markPriceKlines',
        'integrity':'Each ZIP checked against official CHECKSUM, filename, UTC month/hour grid, unique timestamps and positive finite OPEN.',
        'price_semantics':'Use only the preceding hour OPEN for a funding event at most15seconds later. Explicit proxy; not an exact historical settlement mark.',
        'reconciliation':'Rebuild all rates from retained REST payloads, verify local overlap, coverage and gaps, preserve initial manifest before repair.',
        'post_2025_market_data_allowed':False,'parent_source_manifest_sha256':r.sha(ART/'SOURCE_MANIFEST.json')})


def verify_sources():
    v.verify_sources();m=r.read(OUT/'PROTOCOL.json')
    for p,h in m['sources'].items():assert r.sha(v.ROOT/p)==h,p
    assert m['parent_source_manifest_sha256']==r.sha(ART/'SOURCE_MANIFEST.json')


def archive_month(session,symbol,month):
    url=f'https://data.binance.vision/data/futures/um/monthly/markPriceKlines/{symbol}/1h/{symbol}-1h-{month}.zip'
    folder=OUT/'raw'/symbol;folder.mkdir(parents=True,exist_ok=True);p=folder/f'{symbol}-1h-{month}.zip';check=p.with_suffix('.zip.CHECKSUM')
    if not p.exists():
        response=session.get(url,timeout=30);response.raise_for_status();p.write_bytes(response.content)
    if not check.exists():
        response=session.get(url+'.CHECKSUM',timeout=30);response.raise_for_status();check.write_bytes(response.content)
    parts=check.read_text(encoding='utf8').split();assert len(parts)==2 and parts[1].lstrip('*')==p.name
    assert r.sha(p)==parts[0].lower(),'Official archive checksum mismatch'
    return parse_archive(p.read_bytes(),symbol,month),{'path':str(p),'sha256':r.sha(p),'checksum_path':str(check),'checksum_sha256':r.sha(check),'url':url,'month':month}


def recover(symbol,need):
    rates={};marks={};raw_sources={}
    for p in sorted((ART/'funding/raw'/symbol).glob('*.json.gz')):
        with gzip.open(p,'rt',encoding='utf8') as fh:raw=json.load(fh)
        params=raw['params'];assert v.funding.START_MS<=params['startTime']<=params['endTime']<v.funding.LIMIT_MS
        assert params['symbol']==symbol;raw_sources[str(p.relative_to(ART))]=r.sha(p)
        if raw['url']==v.funding.FUNDING_URL:
            for a in raw['data']:
                assert a['symbol']==symbol and params['startTime']<=int(a['fundingTime'])<=params['endTime']
                if int(a['fundingTime']) in rates:assert rates[int(a['fundingTime'])]==a
                rates[int(a['fundingTime'])]=a
        elif raw['url']==v.funding.MARK_URL:
            for a in raw['data']:
                assert params['startTime']<=int(a[0])<=params['endTime'];marks[int(a[0])]=float(a[1])
        else:raise ValueError('Unexpected cached endpoint')
    if not rates:raise ValueError('No official funding rates cached; archive OPEN cannot replace missing rates')
    timestamps=sorted(rates);assert timestamps[0]<=need['first_entry_ms'] and timestamps[-1]>=need['last_exit_ms']
    required_hours=set()
    for t,a in rates.items():
        price=float(a.get('markPrice') or 0)
        if not np.isfinite(price) or price<=0:
            hour=t//3600000*3600000;assert t-hour<=15000
            if hour not in marks or marks[hour]<=0:required_hours.add(hour)
    month_names=sorted({pd.Timestamp(t,unit='ms',tz='UTC').strftime('%Y-%m') for t in required_hours});archive_sources=[];archive_marks={};session=requests.Session()
    for month in month_names:
        values,source=archive_month(session,symbol,month);archive_marks.update(values);archive_sources.append(source)
        print(f'Historical mark archive {symbol} {month}',flush=True)
    rows=[]
    for t,a in sorted(rates.items()):
        price=float(a.get('markPrice') or 0);source='funding_api_settlement_mark';reference=t
        if not np.isfinite(price) or price<=0:
            reference=t//3600000*3600000
            if reference in required_hours:price=archive_marks.get(reference);source='official_mark_archive_open_proxy'
            else:price=marks[reference];source='official_mark_candle_open_proxy'
        assert price is not None and np.isfinite(price) and price>0,(symbol,t)
        rows.append({'funding_ts_ms':t,'funding_rate':float(a['fundingRate']),'mark_price':price,'price_source':source,'mark_reference_ts_ms':reference})
    frame=pd.DataFrame(rows);assert np.isfinite(frame[['funding_rate','mark_price']]).all().all()
    stamps=frame.funding_ts_ms.to_numpy();gaps=[{'start_ms':int(a),'end_ms':int(b)} for a,b in zip(stamps[:-1],stamps[1:]) if b-a>8*3600000+15000 and a<need['last_exit_ms'] and b>need['first_entry_ms']]
    assert not gaps,'Unresolved historical funding-rate gap'
    local=ART/'funding/local_snapshots'/f'{symbol}.parquet';matches=0;differences=[];local_rows=0
    if local.exists():
        prior=pd.read_parquet(local);local_rows=len(prior);lookup=dict(zip(frame.funding_ts_ms,frame.funding_rate))
        for a in prior.itertuples():
            t=int(pd.Timestamp(a.funding_time).timestamp()*1000)
            if t in lookup and abs(lookup[t]-a.funding_rate)<1e-12:matches+=1
            else:differences.append(t)
    assert not differences,'Funding-rate mismatch against local data'
    target=ART/'funding/snapshots'/f'{symbol}.parquet';frame.to_parquet(target,index=False)
    record={'requirements':need,'rows':len(frame),'sha256':r.sha(target),'price_sources':frame.price_source.value_counts().to_dict(),
        'first_event_ms':int(stamps[0]),'last_event_ms':int(stamps[-1]),'gaps_over_8h':[],'left_edge_uncovered':False,'right_edge_uncovered':False,
        'local_rows':local_rows,'local_matches':matches,'local_differences_ms':[],'raw_responses':raw_sources,'archive_sources':archive_sources}
    r.save(OUT/f'{symbol}_RECORD.json',record)
    return {'mode':'official_archive_mark_recovery','source_root':str(ART),'path':str(target),'sha256':record['sha256'],'record':record,'requirements':need}


def run():
    verify_sources();initial=OUT/'INITIAL_ACQUISITION_MANIFEST.json';current=ART/'funding/MANIFEST.json'
    if not initial.exists():shutil.copy2(current,initial)
    manifest=r.read(current);needs=r.read(ART/'funding/REQUIREMENTS.json');errors={}
    for s in sorted(manifest['errors']):
        try:manifest['symbols'][s]=recover(s,needs[s])
        except Exception as exc:errors[s]=str(exc);print(f'Archive recovery unresolved {s}: {exc}',flush=True)
    manifest.update(errors=errors,all_passed=not errors and len(manifest['symbols'])==len(needs),archive_recovery_protocol_sha256=r.sha(OUT/'PROTOCOL.json'),initial_acquisition_manifest_sha256=r.sha(initial))
    r.save(current,manifest);print({'complete':len(manifest['symbols']),'total':len(needs),'errors':errors},flush=True)
    if errors:raise RuntimeError(errors)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['register','run']);a=p.parse_args()
    {'register':register,'run':run}[a.action]()
