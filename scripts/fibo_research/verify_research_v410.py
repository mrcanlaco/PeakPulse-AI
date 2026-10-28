"""Independent market-input and cash reconstruction for the matched study."""
from collections import Counter, defaultdict
import gzip
import json
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import research_v410 as v

r=v.r;ART=v.ART


def close(a,b,tol=1e-9):
    assert np.allclose(a,b,atol=tol,rtol=0),(a,b)


def verify_features_and_matching():
    v.verify_sources();record=r.read(ART/'MATCHES.json')
    assert record['features_sha256']==r.sha(ART/'FEATURES.parquet')
    features=pd.read_parquet(ART/'FEATURES.parquet');checked=0
    for symbol,rows in features.groupby('symbol'):
        bars=v.load_bars(symbol);stamps=r.epoch_seconds(bars.index);prices=bars.close.to_numpy()
        logs=np.log(prices);squared=np.r_[0,np.diff(logs)**2];cumulative=np.cumsum(squared)
        indices=np.searchsorted(stamps,rows.decision_ts.to_numpy()-300)
        assert np.all(indices>=288) and np.all(indices<len(stamps))
        assert np.array_equal(stamps[indices]+300,rows.decision_ts.to_numpy())
        assert np.all(stamps[indices]-stamps[indices-288]==86400)
        close(logs[indices]-logs[indices-288],rows.momentum.to_numpy())
        close(np.sqrt(np.maximum(0,cumulative[indices]-cumulative[indices-288])),rows.volatility.to_numpy(),1e-8)
        checked+=len(rows)
    lookup={(p.symbol,int(p.decision_ts)):p for p in features.itertuples()}
    membership=r.read(v.q.ART/'history/MEMBERSHIP.json')
    v.q.setup_context();sampled,rejected,raw=v.sample_events(r.load_candidates('history'))
    assert len(sampled)==record['sampled_events'] and rejected==record['sampling_rejections']
    active=defaultdict(set)
    for c in raw:active[c['decision_ts']].add(c['symbol'])
    outputs={p['id']:p for p in record['pairs']+record['unmatched']}
    assert len(outputs)==len(sampled)
    for c in sampled:
        out=outputs[c['id']];t=c['decision_ts'];target=lookup.get((c['symbol'],t))
        if target is None:assert out['reason']=='treated_past_feature_missing';continue
        if target.momentum>=0:assert out['reason']=='treated_nonnegative_momentum';continue
        month=pd.Timestamp(t,unit='s',tz='UTC').strftime('%Y-%m')
        pool=[lookup[(p['symbol'],t)] for p in membership[month] if p['symbol']!=c['symbol'] and p['symbol'] not in active[t]
            and (p['symbol'],t) in lookup and lookup[(p['symbol'],t)].momentum<0]
        if len(pool)<3:assert out['reason']=='fewer_than_three_negative_controls';continue
        matrix=np.array([[p.momentum,p.volatility] for p in pool]);sd=matrix.std(axis=0)
        if np.any(sd<=1e-12):assert out['reason']=='degenerate_control_dispersion';continue
        diff=(matrix-np.array([target.momentum,target.volatility]))/sd
        options=sorted((float(np.dot(d,d)),p.symbol,i) for i,(d,p) in enumerate(zip(diff,pool)) if np.all(np.abs(d)<=.5))
        if not options:assert out['reason']=='outside_fixed_caliper';continue
        best=options[0];assert out['control']['symbol']==best[1]
        close(out['squared_distance'],best[0]);close(out['standardized_difference'],diff[best[2]])
        assert out['entry_ts']==t+300 and out['exit_ts']==t+86700
    return {'past_feature_rows_recomputed':checked,'sampled_events_reconciled':len(sampled),'matches_reconciled':len(record['pairs'])}


def verify_funding():
    manifest=r.read(ART/'funding/MANIFEST.json');assert manifest['all_passed']
    total=0;raw_count=0;output={}
    for symbol,meta in manifest['symbols'].items():
        assert r.sha(meta['path'])==meta['sha256']
        frame=pd.read_parquet(meta['path']);n=meta['requirements']
        assert frame.funding_ts_ms.min()<=n['first_entry_ms']<=n['last_exit_ms']<=frame.funding_ts_ms.max()
        assert v.f.START_MS<=frame.funding_ts_ms.min()<=frame.funding_ts_ms.max()<v.f.LIMIT_MS
        assert frame.funding_ts_ms.is_unique and frame.funding_ts_ms.is_monotonic_increasing
        if meta['mode']=='new_official_download':
            rates={};marks={}
            for relative,digest in meta['record']['raw_responses'].items():
                path=ART/relative;assert r.sha(path)==digest
                with gzip.open(path,'rt',encoding='utf8') as fh:source=json.load(fh)
                params=source['params'];assert v.f.START_MS<=params['startTime']<=params['endTime']<v.f.LIMIT_MS
                if source['url']==v.f.FUNDING_URL:
                    for row in source['data']:
                        assert row['symbol']==symbol and params['startTime']<=row['fundingTime']<=params['endTime']
                        rates[row['fundingTime']]=row
                elif source['url']==v.f.MARK_URL:
                    for row in source['data']:
                        assert params['startTime']<=row[0]<=params['endTime'];marks[row[0]]=float(row[1])
                else:raise AssertionError('Unexpected funding source')
                raw_count+=1
            assert set(rates)==set(frame.funding_ts_ms)
            for event in frame.itertuples():
                raw=rates[event.funding_ts_ms];close(event.funding_rate,float(raw['fundingRate']))
                if event.price_source=='funding_api_settlement_mark':
                    close(event.mark_price,float(raw['markPrice']));assert event.mark_reference_ts_ms==event.funding_ts_ms
                else:
                    assert not raw['markPrice'] or float(raw['markPrice'])<=0
                    assert 0<=event.funding_ts_ms-event.mark_reference_ts_ms<=15000
                    close(event.mark_price,marks[event.mark_reference_ts_ms])
        output[symbol]=frame;total+=len(frame)
    return output,{'funding_snapshot_events_verified':total,'new_raw_responses_verified':raw_count,'reused_symbols':manifest['reused_symbols'],'new_symbols':manifest['newly_acquired_symbols']}


def verify_outcomes(funding):
    results=r.read(ART/'RESULTS.json')
    assert results['ledger_sha256']==r.sha(ART/'EVENT_LEDGER.json.gz')
    assert results['matches_sha256']==r.sha(ART/'MATCHES.json')
    with gzip.open(ART/'EVENT_LEDGER.json.gz','rt',encoding='utf8') as fh:ledger=json.load(fh)
    matches=r.read(ART/'MATCHES.json')['pairs'];needed=defaultdict(set)
    for p in matches:
        for s in (p['symbol'],p['control']['symbol']):needed[s].add(p['entry_ts'])
    market={}
    for symbol,times in needed.items():
        bars=v.load_bars(symbol)
        for t in times:
            selected=bars.loc[(bars.index>=pd.Timestamp(t,unit='s',tz='UTC'))&(bars.index<pd.Timestamp(t+86400,unit='s',tz='UTC'))]
            if len(selected)!=288 or not np.array_equal(r.epoch_seconds(selected.index),np.arange(t,t+86400,300)):
                market[(symbol,t)]=None;continue
            market[(symbol,t)]=(float(selected.iloc[0]['open']),float(selected.iloc[-1]['close']))
    incomplete={p['id'] for p in matches if market[(p['symbol'],p['entry_ts'])] is None or market[(p['control']['symbol'],p['entry_ts'])] is None}
    assert incomplete=={p['id'] for p in ledger['incomplete']}=={p['id'] for p in results['incomplete_pairs']}
    pairmap={p['id']:p for p in matches};legs=0;payments=0;proxy=0;exact_request={}
    for name,rows in ledger['scenarios'].items():
        scenario=v.x.SCENARIOS[name];slip=scenario['slippage_bps']/10000;fee=scenario['fee_bps']/10000
        assert {p['id'] for p in rows}==set(pairmap)-incomplete
        for row in rows:
            match=pairmap[row['id']];assert row['entry_ts']==match['entry_ts']
            for side,symbol in [('treated',match['symbol']),('control',match['control']['symbol'])]:
                p=row[side];t=row['entry_ts'];entry,exit=market[(symbol,t)];qty=1/entry
                close(p['qty'],qty);assert len(p['fills'])==2
                gross=1-exit/entry;fees=(entry*(1-slip)+exit*(1+slip))*qty*fee
                slippage=(entry+exit)*qty*slip;frame=funding[symbol]
                selected=frame.loc[(frame.funding_ts_ms>t*1000)&(frame.funding_ts_ms<=(t+86400)*1000)]
                expected_funding=float(np.sum(selected.mark_price*selected.funding_rate)*qty)
                close([p['gross_reference_return'],p['fees'],p['slippage'],p['funding'],p['net_return']],
                    [gross,fees,slippage,expected_funding,gross-fees-slippage+expected_funding])
                assert len(p['funding_events'])==len(selected)
                for actual,expected in zip(p['funding_events'],selected.to_dict('records')):
                    for k,value in expected.items():assert actual[k]==value
                    close(actual['remaining_qty'],qty);close(actual['cashflow'],qty*expected['mark_price']*expected['funding_rate'])
                    if expected['price_source']!='funding_api_settlement_mark':
                        proxy+=1
                        if expected['funding_rate']!=0:exact_request[(symbol,expected['funding_ts_ms'])]={'symbol':symbol,**expected}
                for out,direction,reference,execution,stamp in zip(p['fills'],['SELL','BUY'],[entry,exit],[entry*(1-slip),exit*(1+slip)],[t*1000,(t+86400)*1000]):
                    assert out['side']==direction and out['timestamp_ms']==stamp
                    close([out['reference_price'],out['execution_price'],out['qty'],out['notional'],out['fee'],out['slippage_cost']],
                        [reference,execution,qty,execution*qty,execution*qty*fee,abs(execution-reference)*qty])
                legs+=1;payments+=len(selected)
        periods={**{str(y):(f'{y}-01-01',f'{y+1}-01-01') for y in range(2020,2026)},
            'development_2020_2022':('2020-01-01','2023-01-01'),'validation_2023':('2023-01-01','2024-01-01'),
            'retrospective_oos_2024_2025':('2024-01-01','2026-01-01'),'all_2020_2025':('2020-01-01','2026-01-01')}
        for label,(start,end) in periods.items():
            saved=results['results'][name]['annual' if label.isdigit() else 'splits'][label]
            rows_in=[p for p in rows if r.utc(start).timestamp()<=p['entry_ts']<r.utc(end).timestamp()]
            assert saved['pairs']==len(rows_in)
            if rows_in:
                mean=np.mean([[p['treated']['net_return'],p['control']['net_return']] for p in rows_in],axis=0)*10000
                close([saved['mean_fibo_bps'],saved['mean_control_bps'],saved['mean_difference_bps']],[*mean,mean[0]-mean[1]])
            assert saved==v.paired_statistics(rows,start,end),'Bootstrap reproducibility failed'
    primary=[p['splits']['retrospective_oos_2024_2025'] for p in results['results'].values()]
    expected=not incomplete and all(p.get('pairs',0)>=200 and p['paired_difference_ci95_bps'][0]>0 for p in primary)
    assert results['incremental_diagnostic_support']==expected
    r.save(ART/'EXACT_MARK_DATA_REQUEST.json',{'scope':'Nonzero funding cashflows in this matched event study; not a data purchase or verified vendor quote',
        'unique_events':len(exact_request),'symbols':len({k[0] for k in exact_request}),'events':list(exact_request.values())})
    return {'scenario_leg_outcomes_recomputed':legs,'scenario_funding_payments_recomputed':payments,'scenario_proxy_payments':proxy,
        'incomplete_pairs':len(incomplete),'nonzero_proxy_events_requiring_exact_mark':len(exact_request),'bootstrap':'Reproducibility checked; mean cash independently recomputed'}


def main():
    inputs=verify_features_and_matching();funding,provenance=verify_funding();outcomes=verify_outcomes(funding)
    old=r.read(v.z.ART/'CHECKPOINT.json')
    for relative,digest in old['files'].items():assert r.sha(v.z.ART/relative)==digest,relative
    for relative,digest in old.get('additional_sources',{}).items():assert r.sha(r.ROOT/relative)==digest,relative
    for path,digest in old.get('additional_artifacts',{}).items():assert r.sha(path)==digest,path
    root=ET.parse(ART/'TESTS.xml').getroot();suites=list(root.iter('testsuite'))
    counts={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','errors','failures','skipped')}
    assert counts['tests']>=13 and counts['errors']==counts['failures']==counts['skipped']==0
    out={'all_checks_passed':True,**inputs,**provenance,**outcomes,'tests':counts,
        'previous_v409_files_preserved':len(old['files']),'post_2025_backtest_observations':0,
        'results_sha256':r.sha(ART/'RESULTS.json'),'funding_price_quality':'PARTIAL_EXPLICIT_PROXY','goal_complete':False,'live_signoff':'NOT_GRANTED'}
    r.save(ART/'INDEPENDENT_VERIFICATION.json',out);print(json.dumps(out),flush=True)


if __name__=='__main__':main()
