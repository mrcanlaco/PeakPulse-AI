"""Registered historical-universe audit; no strategy outcomes or post-2025 rows."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import research_v408 as q

r=q.r
ROOT=r.ROOT
ART=ROOT/'artifacts/fibo_trend_short/research_v4_0_13'
PRIOR=ROOT/'artifacts/fibo_trend_short/research_v4_0_12'
EXTERNAL=Path('E:/Quant-trading/research/projects/alpha_factory') if Path('E:/Quant-trading/research/projects/alpha_factory').exists() else Path('C:/Quant-trading/research/projects/alpha_factory')
START=q.START; END=q.END
VALUE_COLS=['open','high','low','close','volume','quote_volume']
MONTHS=pd.date_range(START,END-pd.Timedelta(days=1),freq='MS')
EVIDENCE_NAMES=[
    'binance-usdm-gap-backfill-2020-2023.json',
    'binance-usdm-gap-backfill-2020-2025.json',
    'binance-usdm-gap-backfill-2020-2025-lifecycle.json',
    'binance-usdm-gap-availability-2020-2023.json',
    'binance-usdm-gap-availability-2020-2025.json',
    'binance-usdm-archive-universe-gap-2020-2025.json',
]


def freeze():
    if (ART/'SOURCE_MANIFEST.json').exists():raise FileExistsError('Protocol already frozen')
    ART.mkdir(parents=True,exist_ok=True)
    old=r.read(q.ART/'history/DATA_MANIFEST.json')
    inventory=r.read(PRIOR/'HISTORICAL_UNIVERSE_INVENTORY.json')
    protocol=r.read(PRIOR/'NEXT_UNIVERSE_AUDIT_PROTOCOL.json')
    protocol.update(version='4.0.13-data-audit',registered_at_utc=datetime.now(timezone.utc).isoformat(),
        stage='Data validation and membership only; no strategy returns in this stage',
        data_rules={
            'window':'[2020-01-01T00:00:00Z, 2026-01-01T00:00:00Z)',
            'loader':'Arrow predicate filtering before dataframe materialization, UTC timestamps on the exact 300-second grid',
            'canonical_fields':VALUE_COLS,
            'merge':'Union exact symbol identities and observed timestamps. Exact duplicate values deduplicated. Any conflicting OHLCV blocks the symbol and blocks expanded-universe performance until resolved. No symbol renaming or token-unit conversion.',
            'missing':'Retain all observed valid rows, disclose internal gaps and zero-volume spans separately. Do not fill missing prices or exclude a symbol on future completeness. Existing acquisition omissions remain a coverage limitation until recovered.',
            'quality':'Finite positive OHLC with proper ranges; finite nonnegative volumes; base and quote volume must be zero together. Additional files must match filename symbol and expected close-time duration.',
            'lifecycle':'First/last positive volume and zero-volume runs are descriptive as-of-cutoff evidence, never future eligibility filters. Historical archive presence is not complete contract-lifecycle certification.',
            'universe':'Exactly reproduce frozen v408 monthly rule; complete hours only, prior63days, >=50 positive-volume days, complete H4 wick p90<=3.2%, top50 median daily quote volume, original exclusions and alphabetical ties.',
            'controls':'Recompute old250-symbol membership and require exact equality before interpreting expanded membership. Independently recompute union membership from five-minute snapshots.',
            'source_validation':'Hash every local source and declared sidecar; trace monthly archive URLs. Independently redownload the second available month (or only month), preferring the full-history source, for every additional symbol. Verify official SHA256 CHECKSUM and compare OHLCV. This is a sample provenance check, not verification of every archive.',
            'previous_uses':'Preserve evidence that these folders were used by other projects. Default fresh_oos=false; never relabel new-to-this-snapshot symbols as globally untouched OOS.',
        },
        primary_policy='original elite-sniper ladder frozen in v409; independent of v412 exit outcomes',
        scenarios={'standard_vip6':{'fee_bps_per_fill':2.5,'slippage_bps_per_fill':10.},'stress_regular':{'fee_bps_per_fill':5.,'slippage_bps_per_fill':50.}},
        funding='Actual signed historical funding; explicit mark-price proxies. Funding acquisition follows candidate coverage, before any portfolio run.',
        fresh_oos=False,goal_complete=False,live_signoff='NOT_GRANTED')
    r.save(ART/'PROTOCOL.json',protocol)
    evidence={}
    for name in EVIDENCE_NAMES:
        p=EXTERNAL/'datasets'/name
        target=ART/'source_evidence'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
        evidence[str(p)]={'snapshot':str(target.relative_to(ART)),'sha256':r.sha(p)}
    for name in ['backfill_broad_pre2024_klines.py','backfill_broad_development_klines.py']:
        p=EXTERNAL/'tools'/name;target=ART/'source_evidence'/name;shutil.copy2(p,target)
        evidence[str(p)]={'snapshot':str(target.relative_to(ART)),'sha256':r.sha(p)}
    # Coverage manifests show that the added sources were already inventoried by
    # another research project. They do not certify unseen symbols or outcomes.
    lineage=list(Path('C:/Quant-trading/research/projects/factor-statarb/outputs/daily-rotation-2020-2025').glob('*/coverage.json'))
    r.save(ART/'PRIOR_USE_LINEAGE.json',{'scope':'Known prior inventories; not an exhaustive exposure audit','fresh_oos':False,
        'evidence':[{'path':str(p),'sha256':r.sha(p)} for p in sorted(lineage)],
        'acquisition_reports':evidence})
    catalog=[]
    for symbol,item in old['inputs'].items():
        catalog.append({'symbol':symbol,'kind':'v408_snapshot','path':str(q.ART/'history/bars_5m'/f'{symbol}.parquet'),'expected_sha256':item['snapshot_sha256']})
    available={}
    for name in EVIDENCE_NAMES:
        if '-availability-' in name:
            p=ART/'source_evidence'/name;available[r.sha(p)]=r.read(p)
    for row in inventory['files']:
        path=Path(row['path']);sidecar_path=path.with_suffix('.json');sidecar=r.read(sidecar_path)
        assert sidecar['symbol']==row['symbol'] and Path(sidecar['path'])==path
        availability=available[sidecar['availability_sha256']]
        assert availability['source']=='https://data.binance.vision/data/futures/um/monthly/klines'
        months=sorted(sidecar['months']);assert all('2020-01'<=m<='2025-12' for m in months)
        records={a['month']:a for a in availability['months'] if a['symbol']==row['symbol'] and a['status']=='AVAILABLE'}
        for month in months:
            expected=f"{availability['source']}/{row['symbol']}/5m/{row['symbol']}-5m-{month}.zip"
            assert records[month]['url']==expected
        target=ART/'source_evidence/sidecars'/path.parents[2].name/sidecar_path.name
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(sidecar_path,target)
        catalog.append({'symbol':row['symbol'],'kind':'additional_archive','path':str(path),
            'expected_sha256':sidecar['parquet_sha256'],'sidecar':str(target.relative_to(ART)),
            'sidecar_sha256':r.sha(sidecar_path),'availability_sha256':sidecar['availability_sha256'],
            'months':months,'archive_sha256':sidecar['archive_sha256'],'gap_repairs':sidecar['gap_repairs']})
    r.save(ART/'SOURCE_CATALOG.json',{'files':catalog,'symbols':len({x['symbol'] for x in catalog}),
        'additional_symbols':len({x['symbol'] for x in catalog if x['kind']=='additional_archive'}),
        'inventory_sha256':r.sha(PRIOR/'HISTORICAL_UNIVERSE_INVENTORY.json')})
    samples=[]
    for symbol in sorted({x['symbol'] for x in catalog if x['kind']=='additional_archive'}):
        choices=[x for x in catalog if x['symbol']==symbol and x['kind']=='additional_archive']
        choice=sorted(choices,key=lambda x:('development_historical_gap_2020_2025' not in x['path'],x['path']))[0]
        month=choice['months'][min(1,len(choice['months'])-1)]
        samples.append({'symbol':symbol,'month':month,'local_path':choice['path'],
            'local_parquet_sha256':choice['expected_sha256'],'local_archive_sha256':choice['archive_sha256'][month],
            'url':f'https://data.binance.vision/data/futures/um/monthly/klines/{symbol}/5m/{symbol}-5m-{month}.zip'})
    r.save(ART/'OFFICIAL_SAMPLE_PLAN.json',{'rule':'Second available month, else first; prefer full-history source; all additional symbols','samples':samples,'selected_before_new_price_reads':True})
    failures=[]
    for name in EVIDENCE_NAMES[:2]:
        for a in r.read(ART/'source_evidence'/name)['symbols']:
            if a['status'] not in ('DOWNLOADED','SKIPPED_VERIFIED'):
                failures.append({'report':name,**a,'already_in_v408':a['symbol'] in old['inputs']})
    r.save(ART/'ACQUISITION_OMISSIONS.json',{'records':failures,'unique_symbols':sorted({x['symbol'] for x in failures}),'resolved':False,
        'policy':'These prior quality exclusions do not justify dropping entire historical instruments. Recover observed archives separately before declaring coverage complete.'})
    sources=[Path(__file__),ROOT/'scripts/fibo_research/verify_universe_v413.py',ROOT/'scripts/fibo_research/sample_archives_v413.py',ROOT/'tests/unit/fibo_short/test_universe_v413.py']
    sources += [ROOT/p for p in r.read(q.ART/'SOURCE_MANIFEST.json')]
    sources=list(dict.fromkeys(sources))
    for p in sources:
        target=ART/'source_snapshot'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    r.save(ART/'SOURCE_MANIFEST.json',{'sources':{str(p.relative_to(ROOT)):r.sha(p) for p in sources},
        'protocol_sha256':r.sha(ART/'PROTOCOL.json'),'catalog_sha256':r.sha(ART/'SOURCE_CATALOG.json'),
        'sample_plan_sha256':r.sha(ART/'OFFICIAL_SAMPLE_PLAN.json'),'prior_checkpoint_sha256':r.sha(PRIOR/'CHECKPOINT.json'),
        'v408_data_manifest_sha256':r.sha(q.ART/'history/DATA_MANIFEST.json')})
    print(f'Frozen audit of {len(catalog)} files / {len({x["symbol"] for x in catalog})} symbols.',flush=True)


def verify_sources():
    m=r.read(ART/'SOURCE_MANIFEST.json')
    for p,h in m['sources'].items():assert r.sha(ROOT/p)==h,p
    for k,p in [('protocol_sha256',ART/'PROTOCOL.json'),('catalog_sha256',ART/'SOURCE_CATALOG.json'),
                ('sample_plan_sha256',ART/'OFFICIAL_SAMPLE_PLAN.json'),('prior_checkpoint_sha256',PRIOR/'CHECKPOINT.json'),
                ('v408_data_manifest_sha256',q.ART/'history/DATA_MANIFEST.json')]:assert m[k]==r.sha(p),p


def bounded_read(path,start=START,end=END,with_identity=False):
    start,end=r.utc(start),r.utc(end)
    if start<START or end>END or start>=end:raise ValueError('Forbidden date range')
    cols=['open_time',*VALUE_COLS]+(['symbol','close_time'] if with_identity else [])
    table=pq.read_table(path,columns=cols,filters=[('open_time','>=',start),('open_time','<',end)])
    df=table.to_pandas(ignore_metadata=True)
    df['open_time']=pd.to_datetime(df.open_time,utc=True)
    assert ((df.open_time>=start)&(df.open_time<end)).all()
    if with_identity:
        assert df.symbol.eq(Path(path).stem).all(),'Contract symbol mismatch'
        duration=pd.to_datetime(df.close_time,utc=True)-df.open_time
        assert duration.eq(pd.Timedelta(milliseconds=299999)).all(),'Unexpected candle close time'
    return df[['open_time',*VALUE_COLS]]


def normalize(df):
    frame=df[['open_time',*VALUE_COLS]].copy()
    times=pd.DatetimeIndex(pd.to_datetime(frame.open_time,utc=True)).as_unit('ns')
    if len(frame) and (times.min()<START or times.max()>=END):raise ValueError('Out-of-range rows')
    if times.isna().any() or np.any(times.asi8 % (300*10**9)):raise ValueError('Off-grid timestamp')
    frame['open_time']=times
    if frame.duplicated('open_time').any():
        dup=frame[frame.duplicated('open_time',keep=False)]
        if (dup.groupby('open_time')[VALUE_COLS].nunique(dropna=False)>1).any().any():raise ValueError('Conflicting duplicate candles')
    frame=frame.drop_duplicates('open_time').set_index('open_time').sort_index().astype(float)
    if not np.isfinite(frame.to_numpy()).all():raise ValueError('Non-finite OHLCV')
    if (frame[['open','high','low','close']]<=0).any().any():raise ValueError('Nonpositive price')
    if ((frame.high<frame[['open','close','low']].max(axis=1))|(frame.low>frame[['open','close']].min(axis=1))).any():raise ValueError('Invalid OHLC range')
    if (frame[['volume','quote_volume']]<0).any().any():raise ValueError('Negative volume')
    if ((frame.volume==0)!=(frame.quote_volume==0)).any():raise ValueError('Inconsistent zero base/quote volume')
    return frame


def merge_frames(parts):
    merged=None;comparisons=[]
    for label,frame in parts:
        if merged is None:merged=frame.copy();continue
        common=merged.index.intersection(frame.index)
        conflicts=(merged.loc[common,VALUE_COLS].to_numpy()!=frame.loc[common,VALUE_COLS].to_numpy()).any(axis=1)
        record={'incoming':label,'overlapping_rows':len(common),'conflicting_rows':int(conflicts.sum())}
        if conflicts.any():
            record['examples']=[{'open_time':t.isoformat(),'previous':merged.loc[t].to_dict(),'incoming':frame.loc[t].to_dict()} for t in common[conflicts][:20]]
        comparisons.append(record)
        merged=pd.concat([merged,frame.loc[~frame.index.isin(merged.index)]]).sort_index()
    return merged,comparisons


def quality(frame):
    ts=frame.index;delta=np.diff(ts.as_unit('ns').asi8)//10**9
    gaps=[{'last_before':ts[i].isoformat(),'first_after':ts[i+1].isoformat(),'missing_bars':int(d//300-1)} for i,d in enumerate(delta) if d>300]
    zero=frame.volume.eq(0).to_numpy();boundaries=np.flatnonzero(np.r_[True,zero[1:]!=zero[:-1],True])
    runs=[{'start':ts[a].isoformat(),'end':ts[b-1].isoformat(),'bars':int(b-a)} for a,b in zip(boundaries[:-1],boundaries[1:]) if zero[a]] if len(frame) else []
    positive=ts[~zero]
    return {'rows_5m':len(frame),'first_open':ts.min().isoformat(),'last_open':ts.max().isoformat(),
        'internal_gap_count':len(gaps),'missing_bars_inside_span':sum(x['missing_bars'] for x in gaps),'gaps':gaps,
        'zero_volume_rows':int(zero.sum()),'zero_volume_runs':runs,'maximum_zero_volume_run_bars':max((x['bars'] for x in runs),default=0),
        'first_positive_volume':positive.min().isoformat() if len(positive) else None,'last_positive_volume':positive.max().isoformat() if len(positive) else None}


def worker(symbol,records):
    parts=[];source_rows=[];old_membership={};old_rows=0
    for record in records:
        path=Path(record['path']);assert r.sha(path)==record['expected_sha256'],str(path)
        if record['kind']=='additional_archive':assert r.sha(ART/record['sidecar'])==record['sidecar_sha256']
        raw=bounded_read(path,with_identity=record['kind']=='additional_archive');frame=normalize(raw)
        source_rows.append({'path':str(path),'sha256':record['expected_sha256'],'selected_rows':len(raw),'deduplicated_rows':len(raw)-len(frame)})
        if record['kind']=='v408_snapshot':old_membership=r.monthly_rows(symbol,r.h1_frame(frame),MONTHS);old_rows=len(frame)
        parts.append((str(path),frame))
    union,comparisons=merge_frames(parts)
    item={'symbol':symbol,'sources':source_rows,'overlap_comparisons':comparisons,'old_rows':old_rows,'added_rows':len(union)-old_rows,'old_monthly_rows':old_membership}
    if any(c['conflicting_rows'] for c in comparisons):
        item.update(status='CONFLICT_REQUIRES_RESOLUTION',monthly_rows={})
    else:
        path=ART/'history/bars_5m'/f'{symbol}.parquet';path.parent.mkdir(parents=True,exist_ok=True);union.to_parquet(path)
        hourly=r.h1_frame(union)
        item.update(status='VALID_OBSERVED_ROWS',snapshot_sha256=r.sha(path),quality=quality(union),complete_hours=len(hourly),
                    monthly_rows=r.monthly_rows(symbol,hourly,MONTHS))
    out=ART/'symbol_audits'/f'{symbol}.json';r.save(out,item)
    return symbol,r.sha(out),item['status']


def rank(all_rows):
    out={m.strftime('%Y-%m'):[] for m in MONTHS}
    for rows in all_rows:
        for month,row in rows.items():out[month].append(row)
    return {month:sorted(rows,key=lambda x:(-x['median_quote_volume'],x['symbol']))[:50] for month,rows in out.items()}


def prepare(workers=4):
    verify_sources()
    if (ART/'history/DATA_MANIFEST.json').exists():raise FileExistsError('Data already prepared')
    catalog=r.read(ART/'SOURCE_CATALOG.json')['files'];symbols=sorted({a['symbol'] for a in catalog})
    progress_path=ART/'PREPARATION_PROGRESS.json';fingerprint={'source_manifest_sha256':r.sha(ART/'SOURCE_MANIFEST.json')}
    progress=r.read(progress_path) if progress_path.exists() else {'symbols':{},**fingerprint}
    assert all(progress[k]==value for k,value in fingerprint.items())
    for symbol,digest in progress['symbols'].items():assert r.sha(ART/'symbol_audits'/f'{symbol}.json')==digest
    pending=[s for s in symbols if s not in progress['symbols']]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(worker,s,[a for a in catalog if a['symbol']==s]):s for s in pending}
        for f in as_completed(futures):
            symbol,digest,status=f.result();progress['symbols'][symbol]=digest;r.save(progress_path,progress)
            if len(progress['symbols'])%20==0 or status!='VALID_OBSERVED_ROWS':print(f'Universe audit {len(progress["symbols"])}/{len(symbols)} {symbol}: {status}',flush=True)
    items={s:r.read(ART/'symbol_audits'/f'{s}.json') for s in symbols}
    baseline=rank([a['old_monthly_rows'] for a in items.values()]);original=r.read(q.ART/'history/MEMBERSHIP.json')
    assert baseline==original,'Old-universe membership failed exact replay'
    expanded=rank([a['monthly_rows'] for a in items.values()])
    r.save(ART/'history/MEMBERSHIP_OLD_REPLAY.json',baseline);r.save(ART/'history/MEMBERSHIP.json',expanded)
    comparisons={}
    old_symbols=set(r.read(q.ART/'history/DATA_MANIFEST.json')['inputs'])
    for month,rows in expanded.items():
        old={a['symbol'] for a in baseline[month]};new={a['symbol'] for a in rows}
        comparisons[month]={'old_count':len(old),'union_count':len(new),'retained':sorted(old&new),'removed':sorted(old-new),'added':sorted(new-old),
            'added_from_previously_absent_symbols':sorted(new-old_symbols),'jaccard':len(old&new)/len(old|new) if old|new else 1.}
    r.save(ART/'history/MEMBERSHIP_COMPARISON.json',comparisons)
    valid={s:a for s,a in items.items() if a['status']=='VALID_OBSERVED_ROWS'}
    summary={'source_files':len(catalog),'symbols':len(symbols),'valid_symbols':len(valid),'conflicted_symbols':[s for s,a in items.items() if a['status']!='VALID_OBSERVED_ROWS'],
        'old_symbols':len(old_symbols),'new_symbols':len(set(valid)-old_symbols),'rows_5m':sum(a['quality']['rows_5m'] for a in valid.values()),
        'new_rows':sum(a['added_rows'] for a in valid.values()),'overlap_rows_compared':sum(c['overlapping_rows'] for a in items.values() for c in a['overlap_comparisons']),
        'internal_gap_count':sum(a['quality']['internal_gap_count'] for a in valid.values()),
        'symbols_with_internal_gaps':sum(a['quality']['internal_gap_count']>0 for a in valid.values()),
        'symbols_with_zero_volume_rows':sum(a['quality']['zero_volume_rows']>0 for a in valid.values()),
        'zero_volume_rows':sum(a['quality']['zero_volume_rows'] for a in valid.values()),
        'old_membership_exact':True,'changed_months':sum(bool(a['removed'] or a['added']) for a in comparisons.values()),
        'old_membership_slots':sum(len(a) for a in baseline.values()),'union_membership_slots':sum(len(a) for a in expanded.values()),
        'union_unique_members':len({a['symbol'] for rows in expanded.values() for a in rows}),
        'new_symbol_member_slots':sum(len(a['added_from_previously_absent_symbols']) for a in comparisons.values()),
        'post_2025_observations_loaded':0,'fresh_oos':False,'strategy_returns_evaluated':False,'goal_complete':False}
    r.save(ART/'history/DATA_MANIFEST.json',{'summary':summary,'symbol_audit_sha256':progress['symbols'],
        'inputs':{s:{'snapshot_sha256':a['snapshot_sha256'],'rows_5m':a['quality']['rows_5m']} for s,a in valid.items()},
        'membership_sha256':r.sha(ART/'history/MEMBERSHIP.json'),**fingerprint})
    r.save(ART/'DATA_SUMMARY.json',summary);print(summary,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','prepare']);parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    freeze() if args.action=='freeze' else prepare(args.workers)
