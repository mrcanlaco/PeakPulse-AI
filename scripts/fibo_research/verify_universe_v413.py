"""Independent direct-five-minute validation of historical snapshots and PIT ranking."""
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import universe_audit_v413 as v

r=v.r;ART=v.ART


def read_raw(path):
    frame=pq.read_table(path,columns=['open_time',*v.VALUE_COLS],filters=[('open_time','>=',v.START),('open_time','<',v.END)]).to_pandas(ignore_metadata=True)
    frame['open_time']=pd.to_datetime(frame.open_time,utc=True)
    assert frame.open_time.ge(v.START).all() and frame.open_time.lt(v.END).all()
    return frame


def independent_monthly(symbol,raw):
    if symbol in r.EXCLUDE:return {}
    frame=raw.sort_values('open_time').set_index('open_time')
    assert frame.index.is_unique and (frame.index.as_unit('ns').asi8%(300*10**9)==0).all()
    # Direct aggregation from 5m observations, independent of production H1/H4 helpers.
    h1g=frame.groupby(frame.index.floor('h'))
    hourly=h1g.quote_volume.sum().loc[h1g.size().eq(12)]
    daily=hourly.groupby(hourly.index.floor('D')).sum();daily=daily[daily>0]
    h4g=frame.groupby(frame.index.floor('4h'))
    h4=h4g.agg({'open':'first','high':'max','close':'last'}).loc[h4g.size().eq(48)]
    wick=(h4.high-h4[['open','close']].max(axis=1))/h4.close*100
    rows={}
    for month in v.MONTHS:
        lower=month-pd.Timedelta(days=63)
        active=daily.loc[(daily.index>=lower)&(daily.index<month)]
        w=wick.loc[(wick.index>=lower)&(wick.index+pd.Timedelta(hours=4)<=month)]
        if len(active)<50 or len(w)<10:continue
        p90=float(np.quantile(w,.9));median=float(active.median())
        if p90<=3.2 and median>0:rows[month.strftime('%Y-%m')]={'symbol':symbol,'median_quote_volume':median,'active_days':len(active),'wick_p90_pct':p90}
    return rows


def check_row(a,b):
    assert set(a)==set(b)
    for month in a:
        assert a[month]['symbol']==b[month]['symbol'] and a[month]['active_days']==b[month]['active_days']
        for key in ('median_quote_volume','wick_p90_pct'):
            assert np.isclose(a[month][key],b[month][key],rtol=1e-12,atol=1e-12),(month,key,a[month],b[month])


def main():
    v.verify_sources();manifest=r.read(ART/'history/DATA_MANIFEST.json');catalog=r.read(ART/'SOURCE_CATALOG.json')['files']
    assert not manifest['summary']['conflicted_symbols'],'Resolve every duplicate conflict before validating an expanded universe'
    assert manifest['source_manifest_sha256']==r.sha(ART/'SOURCE_MANIFEST.json')
    monthly=[];source_count=0;row_count=0;zero_count=0;gap_count=0
    for i,(symbol,item) in enumerate(sorted(manifest['inputs'].items()),1):
        audit_path=ART/'symbol_audits'/f'{symbol}.json';assert r.sha(audit_path)==manifest['symbol_audit_sha256'][symbol]
        audit=r.read(audit_path);path=ART/'history/bars_5m'/f'{symbol}.parquet';assert r.sha(path)==item['snapshot_sha256']
        sources=[]
        for source in [a for a in catalog if a['symbol']==symbol]:
            assert r.sha(source['path'])==source['expected_sha256'];sources.append(read_raw(source['path']));source_count+=1
        combined=pd.concat(sources,ignore_index=True)
        dup=combined[combined.duplicated('open_time',keep=False)]
        assert not (dup.groupby('open_time')[v.VALUE_COLS].nunique(dropna=False)>1).any().any()
        expected=combined.drop_duplicates('open_time').set_index('open_time').sort_index()[v.VALUE_COLS].astype(float)
        raw=read_raw(path);observed=raw.set_index('open_time').sort_index()[v.VALUE_COLS]
        pd.testing.assert_frame_equal(expected,observed,check_dtype=False,check_index_type=False,check_exact=True)
        assert np.isfinite(observed.to_numpy()).all() and observed.index.is_unique
        delta=np.diff(observed.index.as_unit('ns').asi8)//10**9
        missing=int(np.sum(delta//300-1));zeros=int(observed.volume.eq(0).sum())
        assert missing==audit['quality']['missing_bars_inside_span'] and zeros==audit['quality']['zero_volume_rows']
        rows=independent_monthly(symbol,raw);check_row(rows,audit['monthly_rows']);monthly.append(rows)
        row_count+=len(raw);zero_count+=zeros;gap_count+=int((delta>300).sum())
        if i%30==0:print(f'Independent universe verification {i}/{len(manifest["inputs"])}',flush=True)
    independent=v.rank(monthly);saved=r.read(ART/'history/MEMBERSHIP.json')
    assert r.sha(ART/'history/MEMBERSHIP.json')==manifest['membership_sha256']
    for month in saved:
        assert [x['symbol'] for x in independent[month]]==[x['symbol'] for x in saved[month]],month
        for a,b in zip(independent[month],saved[month]):check_row({month:a},{month:b})
    assert r.read(ART/'history/MEMBERSHIP_OLD_REPLAY.json')==r.read(v.q.ART/'history/MEMBERSHIP.json')
    assert row_count==manifest['summary']['rows_5m'] and gap_count==manifest['summary']['internal_gap_count'] and zero_count==manifest['summary']['zero_volume_rows']
    previous=r.read(v.PRIOR/'CHECKPOINT.json')
    for p,h in previous['files'].items():assert r.sha(v.PRIOR/p)==h,p
    for p,h in previous.get('additional_sources',{}).items():assert r.sha(v.ROOT/p)==h,p
    suites=list(ET.parse(ART/'TESTS.xml').getroot().iter('testsuite'));tests={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','errors','failures','skipped')}
    assert tests['tests']>=8 and tests['errors']==tests['failures']==tests['skipped']==0
    result={'all_passed':True,'source_files_rechecked':source_count,'symbols_independently_remerged':len(manifest['inputs']),
        'rows_independently_reconciled':row_count,'monthly_rankings_independently_recomputed':len(saved),'old_membership_exact':True,
        'previous_v412_files_preserved':len(previous['files']),'tests':tests,'data_manifest_sha256':r.sha(ART/'history/DATA_MANIFEST.json'),
        'post_2025_observations_loaded':0,'fresh_oos':False,'strategy_returns_evaluated':False,'goal_complete':False,
        'qualification':'Verifies the supplied observed-row union and causal rankings; does not certify omitted instruments, continuous tradability, archive samples, or future gap-free execution.'}
    r.save(ART/'INDEPENDENT_VERIFICATION.json',result);print(result,flush=True)


if __name__=='__main__':main()
