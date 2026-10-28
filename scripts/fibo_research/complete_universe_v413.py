"""Independently verify official archives, recover omitted histories, and seal union."""
import argparse
from datetime import datetime,timezone
import io
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import zipfile
import numpy as np
import pandas as pd
import universe_audit_v413 as v
import verify_universe_v413 as independent
import recover_universe_gaps_v413 as recovery

r=v.r;ART=v.ART;OUT=ART/'completed_union'
CSV=['open_time','open','high','low','close','volume','close_time','quote_volume','count','buy_volume','buy_quote','ignore']


def register():
    v.verify_sources();recovery.verify_sources()
    if (OUT/'PROTOCOL.json').exists():raise FileExistsError('Completion registered')
    r.save(OUT/'PROTOCOL.json',{'registered_at_utc':datetime.now(timezone.utc).isoformat(),
        'purpose':'Complete the already registered universe audit by retaining all observed rows from the ten previously excluded histories.',
        'merge_rule':'Union initial633-symbol snapshots with all ten recovered symbols. Exact overlap equality required. Preserve initial audit and recovery artifacts; new snapshots only for the affected symbols.',
        'verification':'Independently parse each official sample archive and every recovery archive; verify current official checksums and recorded download digests. Compare sample OHLCV to local source and recovered raw union to recovered snapshots. Independently rerank modified symbols and preserve independent verification of all unchanged symbols.',
        'lifecycle':'For each monthly membership, compute last positive-volume candle closed strictly by that month boundary using only earlier candles. Report stale memberships and zero-volume tails; do not automatically delete them or alter the frozen portfolio.',
        'performance_gate':'No expanded-universe portfolio results until lifecycle, contract identity and execution-gap implications have been audited. Historical data quality findings do not establish alpha or fresh OOS.',
        'self_sha256':r.sha(__file__),'tests_sha256':r.sha(v.ROOT/'tests/unit/fibo_short/test_universe_completion_v413.py'),'parent_source_manifest_sha256':r.sha(ART/'SOURCE_MANIFEST.json'),
        'recovery_source_manifest_sha256':r.sha(ART/'recovery/SOURCE_MANIFEST.json'),
        'initial_data_manifest_sha256':r.sha(ART/'history/DATA_MANIFEST.json'),
        'fresh_oos':False,'post_2025_observations_permitted':False,'goal_complete':False})
    target=OUT/'source_snapshot'/Path(__file__).name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(__file__,target)
    shutil.copy2(v.ROOT/'tests/unit/fibo_short/test_universe_completion_v413.py',OUT/'source_snapshot/test_universe_completion_v413.py')


def archive_frame(path):
    """Separate CSV path: retain explicit headers, validate close times and volumes."""
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        names=z.namelist();assert len(names)==1
        data=z.read(names[0])
    first=data.splitlines()[0].split(b',')[0]
    skip=0 if first.isdigit() else 1
    if skip:assert first==b'open_time'
    df=pd.read_csv(io.BytesIO(data),skiprows=skip,header=None,names=CSV)
    opened=pd.to_datetime(df.open_time.astype('int64'),unit='ms',utc=True).dt.as_unit('ns')
    closed=pd.to_datetime(df.close_time.astype('int64'),unit='ms',utc=True)
    assert opened.ge(v.START).all() and opened.lt(v.END).all()
    assert (pd.DatetimeIndex(opened).asi8%(300*10**9)==0).all()
    assert closed.sub(opened).eq(pd.Timedelta(milliseconds=299999)).all()
    df['open_time']=opened
    out=df.set_index('open_time')[v.VALUE_COLS].astype(float).sort_index()
    assert np.isfinite(out.to_numpy()).all() and out.index.is_unique
    assert (out[['open','high','low','close']]>0).all().all() and (out[['volume','quote_volume']]>=0).all().all()
    assert (out.high>=out[['open','close','low']].max(axis=1)).all() and (out.low<=out[['open','close']].min(axis=1)).all()
    return out


def verify_samples():
    saved=r.read(ART/'OFFICIAL_SAMPLE_RESULTS.json');plan=r.read(ART/'OFFICIAL_SAMPLE_PLAN.json')['samples']
    assert saved['summary']['all_passed'] and saved['summary']['samples']==len(plan)
    rows=0;extra=0
    for i,item in enumerate(plan,1):
        symbol=item['symbol'];month=item['month'];path=ART/'official_samples'/f'{symbol}-{month}.zip'
        receipt=r.read(path.with_suffix('.json'));checksum=path.with_suffix('.zip.CHECKSUM')
        assert r.sha(path)==receipt['download_sha256']==item['local_archive_sha256']==checksum.read_text(encoding='utf8').split()[0]
        assert r.sha(checksum)==receipt['checksum_file_sha256'] and r.sha(item['local_path'])==item['local_parquet_sha256']
        frame=archive_frame(path);start=r.utc(month+'-01');end=start+pd.offsets.MonthBegin()
        assert (frame.index>=start).all() and (frame.index<end).all()
        local=v.bounded_read(item['local_path'],start,end,with_identity=True).set_index('open_time').sort_index()[v.VALUE_COLS]
        assert not len(frame.index.difference(local.index))
        assert np.allclose(frame.to_numpy(),local.loc[frame.index].to_numpy(),rtol=1e-12,atol=0)
        rows+=len(frame);extra+=len(local.index.difference(frame.index))
        if i%60==0:print(f'Independent official monthly samples {i}/{len(plan)}',flush=True)
    assert rows==saved['summary']['rows_compared'] and extra==saved['summary']['local_extra_rows']
    return {'samples':len(plan),'rows_recompared':rows,'local_extra_rows_not_certified_by_monthly_archive':extra,'all_official_checksums_and_prior_archive_hashes_match':True}


def verify_recovery():
    recovery.verify_sources();result=r.read(ART/'recovery/RESULTS.json');plan=r.read(ART/'recovery/DOWNLOAD_PLAN.json')
    assert result['summary']['recovered']==len(plan['prior_omission_records'])
    sources=0;missing=0;verified={}
    for item in result['symbols']:
        symbol=item['symbol'];parts=[];declared={x['url']:x for x in item['archive_receipts']}
        monthly=[a for a in plan['records'] if a['symbol']==symbol]
        specs=[(a['url'],ART/'recovery/raw/monthly'/f'{symbol}-{a["month"]}.zip',a['prior_download_sha256']) for a in monthly]
        specs += [(f'https://data.binance.vision/data/futures/um/daily/klines/{symbol}/5m/{symbol}-5m-{day}.zip',ART/'recovery/raw/daily'/f'{symbol}-{day}.zip',None) for day in item['daily_dates_requested']]
        assert set(declared)=={url for url,_,_ in specs}
        for url,path,prior_hash in specs:
            receipt=r.read(path.with_suffix('.receipt.json'));assert receipt==declared[url]
            if receipt['status']=='UNAVAILABLE':
                assert receipt['http_status']==404 and r.sha(path.with_suffix('.http404.txt'))==receipt['body_sha256'];missing+=1;continue
            checksum=path.with_suffix('.zip.CHECKSUM');digest=r.sha(path)
            assert digest==receipt['sha256']==checksum.read_text(encoding='utf8').split()[0]
            assert r.sha(checksum)==receipt['checksum_file_sha256']
            if prior_hash:assert digest==prior_hash
            frame=archive_frame(path)
            token=path.stem[len(symbol)+1:]
            if len(token)==7:assert (frame.index.strftime('%Y-%m')==token).all()
            else:assert (frame.index.strftime('%Y-%m-%d')==token).all()
            parts.append(frame);sources+=1
        all_rows=pd.concat(parts).reset_index()
        dup=all_rows[all_rows.duplicated('open_time',keep=False)]
        assert not (dup.groupby('open_time')[v.VALUE_COLS].nunique()>1).any().any()
        expected=all_rows.drop_duplicates('open_time').set_index('open_time').sort_index()[v.VALUE_COLS]
        path=ART/'recovery/bars_5m'/f'{symbol}.parquet';assert r.sha(path)==item['snapshot_sha256']
        actual=independent.read_raw(path).set_index('open_time').sort_index()[v.VALUE_COLS]
        # Different independent decimal parsers may differ below 1e-12 relative.
        assert expected.index.equals(actual.index)
        assert np.allclose(expected.to_numpy(),actual.to_numpy(),rtol=1e-12,atol=0)
        verified[symbol]=item
    return verified,{'raw_archives_independently_reparsed':sources,'unavailable_daily_archives':missing,'symbols':len(verified)}


def assemble():
    v.verify_sources();protocol=r.read(OUT/'PROTOCOL.json')
    assert protocol['self_sha256']==r.sha(__file__) and protocol['initial_data_manifest_sha256']==r.sha(ART/'history/DATA_MANIFEST.json')
    assert protocol['tests_sha256']==r.sha(v.ROOT/'tests/unit/fibo_short/test_universe_completion_v413.py')
    assert protocol['parent_source_manifest_sha256']==r.sha(ART/'SOURCE_MANIFEST.json') and protocol['recovery_source_manifest_sha256']==r.sha(ART/'recovery/SOURCE_MANIFEST.json')
    if (OUT/'DATA_MANIFEST.json').exists():raise FileExistsError('Completed union already frozen')
    initial=r.read(ART/'history/DATA_MANIFEST.json');check=r.read(ART/'INDEPENDENT_VERIFICATION.json')
    assert check['all_passed'] and check['data_manifest_sha256']==r.sha(ART/'history/DATA_MANIFEST.json')
    official=verify_samples();recovered,recovery_check=verify_recovery()
    entries={};rows_by_symbol={};quality_by_symbol={};comparisons={}
    for symbol,a in initial['inputs'].items():
        path=ART/'history/bars_5m'/f'{symbol}.parquet';assert r.sha(path)==a['snapshot_sha256']
        audit=r.read(ART/'symbol_audits'/f'{symbol}.json')
        entries[symbol]={'path':str(path),'sha256':a['snapshot_sha256'],'rows_5m':a['rows_5m'],'origin':'initial_verified_union'}
        rows_by_symbol[symbol]=audit['monthly_rows'];quality_by_symbol[symbol]=audit['quality']
    for symbol,item in recovered.items():
        path=ART/'recovery/bars_5m'/f'{symbol}.parquet';frame=independent.read_raw(path).set_index('open_time').sort_index()[v.VALUE_COLS]
        parts=[]
        if symbol in entries:parts.append(('initial_union',independent.read_raw(entries[symbol]['path']).set_index('open_time').sort_index()[v.VALUE_COLS]))
        parts.append(('recovered_official_archives',frame));merged,conflicts=v.merge_frames(parts)
        assert not any(c['conflicting_rows'] for c in conflicts),symbol
        comparisons[symbol]={'initial_rows':entries.get(symbol,{}).get('rows_5m',0),'recovered_rows':len(frame),'union_rows':len(merged),'overlap_comparisons':conflicts}
        destination=OUT/'bars_5m'/f'{symbol}.parquet';destination.parent.mkdir(parents=True,exist_ok=True);merged.to_parquet(destination)
        entries[symbol]={'path':str(destination),'sha256':r.sha(destination),'rows_5m':len(merged),'origin':'initial_plus_recovered_observed_rows'}
        production=r.monthly_rows(symbol,r.h1_frame(merged),v.MONTHS);direct=independent.independent_monthly(symbol,merged.reset_index());independent.check_row(production,direct)
        rows_by_symbol[symbol]=production;quality_by_symbol[symbol]=v.quality(merged)
    membership=v.rank(rows_by_symbol.values());r.save(OUT/'MEMBERSHIP.json',membership)
    r.save(OUT/'RECOVERY_MERGE_COMPARISON.json',comparisons)
    initial_membership=r.read(ART/'history/MEMBERSHIP.json');old=r.read(v.q.ART/'history/MEMBERSHIP.json')
    membership_delta={}
    for month,current in membership.items():
        a={x['symbol'] for x in old[month]};b={x['symbol'] for x in initial_membership[month]};c={x['symbol'] for x in current}
        membership_delta[month]={'old_members':len(a),'initial_union_members':len(b),'completed_union_members':len(c),
            'added_vs_old':sorted(c-a),'removed_vs_old':sorted(a-c),'added_after_recovery':sorted(c-b),'removed_after_recovery':sorted(b-c)}
    r.save(OUT/'MEMBERSHIP_COMPARISON.json',membership_delta)
    member_months={}
    for month,rows in membership.items():
        for row in rows:member_months.setdefault(row['symbol'],[]).append(month)
    stale=[]
    for symbol,months in member_months.items():
        raw=independent.read_raw(entries[symbol]['path']);positive=pd.DatetimeIndex(raw.loc[raw.volume>0,'open_time']).sort_values()
        for month in months:
            boundary=r.utc(month+'-01');i=positive.searchsorted(boundary-pd.Timedelta(minutes=5),side='right')-1
            last=positive[i] if i>=0 else None
            age=(boundary-last-pd.Timedelta(minutes=5)).total_seconds()/3600 if last is not None else None
            if age is None or age>=24:stale.append({'symbol':symbol,'month':month,'last_positive_volume_bar_open':last.isoformat() if last is not None else None,'hours_since_last_positive_volume_bar_close':age})
    summary={'symbols':len(entries),'new_symbols_vs_v408':len(set(entries)-set(r.read(v.q.ART/'history/DATA_MANIFEST.json')['inputs'])),
        'rows_5m':sum(x['rows_5m'] for x in entries.values()),'recovered_symbols':len(recovered),
        'additional_rows_from_recovery':sum(x['rows_5m'] for x in entries.values())-initial['summary']['rows_5m'],
        'internal_gap_count':sum(x['internal_gap_count'] for x in quality_by_symbol.values()),
        'missing_bars_inside_observed_spans':sum(x['missing_bars_inside_span'] for x in quality_by_symbol.values()),
        'zero_volume_rows':sum(x['zero_volume_rows'] for x in quality_by_symbol.values()),
        'changed_months_vs_v408':sum(bool(x['added_vs_old'] or x['removed_vs_old']) for x in membership_delta.values()),
        'changed_months_due_to_recovery':sum(bool(x['added_after_recovery'] or x['removed_after_recovery']) for x in membership_delta.values()),
        'monthly_member_slots':sum(len(x) for x in membership.values()),'unique_members':len(member_months),
        'memberships_with_last_positive_volume_at_least24h_old':len(stale),
        'strategy_returns_evaluated':False,'fresh_oos':False,'post_2025_observations_loaded':0,'goal_complete':False,'live_signoff':'NOT_GRANTED'}
    r.save(OUT/'QUALITY.json',quality_by_symbol);r.save(OUT/'STALE_MEMBERSHIP_AUDIT.json',{'records':stale,'method':'Only bars closed by each monthly boundary; descriptive, not a new eligibility filter'})
    r.save(OUT/'DATA_MANIFEST.json',{'inputs':entries,'summary':summary,'protocol_sha256':r.sha(OUT/'PROTOCOL.json'),
        'membership_sha256':r.sha(OUT/'MEMBERSHIP.json'),'initial_data_manifest_sha256':r.sha(ART/'history/DATA_MANIFEST.json'),
        'recovery_results_sha256':r.sha(ART/'recovery/RESULTS.json')})
    suites=list(ET.parse(ART/'recovery/TESTS.xml').getroot().iter('testsuite'));tests={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','errors','failures','skipped')}
    assert tests['tests']==3 and tests['errors']==tests['failures']==tests['skipped']==0
    completion_suites=list(ET.parse(OUT/'TESTS.xml').getroot().iter('testsuite'));completion_tests={k:sum(int(s.get(k,0)) for s in completion_suites) for k in ('tests','errors','failures','skipped')}
    assert completion_tests['tests']==2 and completion_tests['errors']==completion_tests['failures']==completion_tests['skipped']==0
    output={'all_data_reconciliation_checks_passed':True,'official_sample_validation':official,'recovery_validation':recovery_check,
        'initial_independent_verification_sha256':r.sha(ART/'INDEPENDENT_VERIFICATION.json'),'recovery_tests':tests,'completion_tests':completion_tests,
        'data_manifest_sha256':r.sha(OUT/'DATA_MANIFEST.json'),'membership_sha256':r.sha(OUT/'MEMBERSHIP.json'),
        'strategy_execution_certified':False,'fresh_oos':False,'post_2025_observations_loaded':0}
    r.save(OUT/'INDEPENDENT_VERIFICATION.json',output);print(summary,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['register','assemble']);args=parser.parse_args()
    register() if args.action=='register' else assemble()
