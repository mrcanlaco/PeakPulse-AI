"""Independent retained-source, funding, fill and cash checks for the new universe."""
from collections import Counter,defaultdict
from pathlib import Path
import argparse,csv,gzip,io,json,zipfile
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import evaluate_universe_resolved_v415 as resolved

b=resolved.base;v=b.v;r=b.r;ART=b.ART


def close(a,c):assert np.allclose(a,c,atol=1e-8,rtol=0),(a,c)


def inputs():
    resolved.verify_sources();candidates=resolved.load_candidates();fund=b.load_funding();manifest=r.read(ART/'CANDIDATE_MANIFEST.json');old=r.read(v.replay.OUT/'CANDIDATE_MANIFEST.json')
    members=r.read(ART/'MEMBERSHIP.json');primary={};total=0;unchanged=0
    for s,item in manifest['symbols'].items():
        assert r.sha(item['path'])==item['sha256'];rows=v.v.load_rows(item['path'])
        assert r.sha(old['symbols'][s]['path'])==old['symbols'][s]['sha256'];prior=v.v.load_rows(old['symbols'][s]['path'])
        normalize=lambda rows:{c['id']:{k:a for k,a in c.items() if k!='contract_episode_id'} for c in rows}
        assert normalize(rows)==normalize(prior),'Unexpected unregistered signal change';unchanged+=len(rows)
        for c in rows:
            total+=1;entry=pd.Timestamp(c['entry_ts'],unit='s',tz='UTC');assert c['symbol']==s and s in {a['symbol'] for a in members[entry.strftime('%Y-%m')]}
            if 'm6_f4_elite_sniper' in c['milestones'] and entry<r.utc(f'{entry.year+1}-01-01')-pd.Timedelta(days=5):primary[c['id']]=c
    assert {c['id']:c for c in candidates}==primary
    data=r.read(ART/'DATA_MANIFEST.json');union=r.read(v.v.UNION/'DATA_MANIFEST.json');trimmed=0
    for event in r.read(ART/'EVENTS.json')['initial_five']:
        s=event['symbol'];source=union['inputs'][s];assert r.sha(source['path'])==source['sha256']
        frame=pd.read_parquet(source['path']);item=data['views'][s][0];assert r.sha(item['path'])==item['sha256']
        pd.testing.assert_frame_equal(pd.read_parquet(item['path']),frame.loc[frame.index<pd.Timestamp(event['settlement_at'])],check_exact=True);trimmed+=1
        for month,rows in members.items():
            if pd.Timestamp(month+'-01',tz='UTC')>=pd.Timestamp(event['settlement_at']):assert s not in {a['symbol'] for a in rows}
    # Rebuild full-pool ranking from preserved per-symbol eligibility, then verify replacements.
    initial=r.read(v.v.PRIOR/'history/DATA_MANIFEST.json');monthly={}
    for s,h in initial['symbol_audit_sha256'].items():
        p=v.v.PRIOR/'symbol_audits'/f'{s}.json';assert r.sha(p)==h;monthly[s]=r.read(p)['monthly_rows']
    for a in r.read(v.e.OUT/'RESULTS.json')['symbols']:monthly[a['symbol']]=a['corrected_monthly_rows']
    for event in r.read(ART/'EVENTS.json')['initial_five']:
        s=event['symbol'];frame=pd.read_parquet(data['views'][s][0]['path'])
        rows=v.e.independent.independent_monthly(s,frame.reset_index());cut=pd.Timestamp(event['entry_close_only_from'] or event['settlement_at'])
        monthly[s]={m:a for m,a in rows.items() if pd.Timestamp(m+'-01',tz='UTC')<cut}
    for month in members:
        pool=[rows[month] for rows in monthly.values() if month in rows];pool.sort(key=lambda a:(-a['median_quote_volume'],a['symbol']))
        assert [a['symbol'] for a in pool[:50]]==[a['symbol'] for a in members[month]]
        for actual,expected in zip(members[month],pool[:50]):
            assert actual['active_days']==expected['active_days'];close(actual['median_quote_volume'],expected['median_quote_volume']);close(actual['wick_p90_pct'],expected['wick_p90_pct'])
    meta=r.read(ART/'funding/MANIFEST.json');source_files=0;source_events=0;archive_count=0;prices=Counter();overlap=0
    for i,(s,item) in enumerate(sorted(meta['symbols'].items()),1):
        record=item['record'];root=Path(item['path']).parents[2];rates={};marks={};archive_marks={}
        for relative,h in record['raw_responses'].items():
            path=root/relative;assert r.sha(path)==h
            with gzip.open(path,'rt',encoding='utf8') as fh:raw=json.load(fh)
            params=raw['params'];assert v.funding.START_MS<=params['startTime']<=params['endTime']<v.funding.LIMIT_MS and params['symbol']==s
            if raw['url']==v.funding.FUNDING_URL:
                for a in raw['data']:
                    assert a['symbol']==s and params['startTime']<=a['fundingTime']<=params['endTime'];rates[int(a['fundingTime'])]=a
            elif raw['url']==v.funding.MARK_URL:
                assert params['interval']=='1h'
                for a in raw['data']:assert params['startTime']<=a[0]<=params['endTime'];marks[int(a[0])]=float(a[1])
            else:raise AssertionError('Unknown raw funding source')
            source_files+=1
        for a in record.get('archive_sources',[]):
            p=Path(a['path']);check=Path(a['checksum_path']);assert r.sha(p)==a['sha256'] and r.sha(check)==a['checksum_sha256']
            digest,name=check.read_text(encoding='utf8').split();assert digest.lower()==r.sha(p) and name.lstrip('*')==p.name
            with zipfile.ZipFile(p) as archive:
                assert archive.namelist()==[p.stem+'.csv']
                with archive.open(p.stem+'.csv') as fh:
                    for row in csv.reader(io.TextIOWrapper(fh,encoding='utf8')):
                        if row[0] in ('open_time','openTime'):continue
                        t=int(row[0]);assert pd.Timestamp(t,unit='ms',tz='UTC').strftime('%Y-%m')==a['month'] and t%3600000==0
                        assert v.funding.START_MS<=t<v.funding.LIMIT_MS and np.isfinite(float(row[1])) and float(row[1])>0;archive_marks[t]=float(row[1])
            archive_count+=1
        assert set(rates)==set(fund[s]['times'])
        for a in fund[s]['events']:
            t=a['funding_ts_ms'];raw=rates[t];close(a['funding_rate'],float(raw['fundingRate']))
            if a['price_source']=='funding_api_settlement_mark':close(a['mark_price'],float(raw['markPrice']));assert a['mark_reference_ts_ms']==t
            else:
                assert not raw.get('markPrice') or float(raw['markPrice'])<=0
                ref=a['mark_reference_ts_ms'];assert 0<=t-ref<=15000 and ref%3600000==0
                lookup=archive_marks if a['price_source']=='official_mark_archive_open_proxy' else marks
                close(a['mark_price'],lookup[ref])
            prices[a['price_source']]+=1;source_events+=1
        old_path=b.original.ART/'funding/snapshots'/f'{s}.parquet'
        if old_path.exists():
            prior=pd.read_parquet(old_path);current=pd.read_parquet(item['path']);lo=max(prior.funding_ts_ms.min(),current.funding_ts_ms.min());hi=min(prior.funding_ts_ms.max(),current.funding_ts_ms.max())
            aa=prior.loc[prior.funding_ts_ms.between(lo,hi)].reset_index(drop=True);bb=current.loc[current.funding_ts_ms.between(lo,hi)].reset_index(drop=True)
            pd.testing.assert_frame_equal(aa,bb,check_dtype=False,check_exact=True);overlap+=len(aa)
        if i%30==0:print(f'Independent funding sources {i}/{len(meta["symbols"])}',flush=True)
    for a in r.read(ART/'BOUNDARY_RESOLUTION.json')['resolved']:
        c=primary[a['id']];assert pd.Timestamp(c['paths']['ladder']['exit_ts'],unit='s',tz='UTC')<pd.Timestamp(a['official_settlement_at'])
    check={'all_passed':True,'candidate_objects_verified':total,'signals_unchanged_vs_v414':unchanged,'primary_candidates_verified':len(candidates),
        'five_delisting_views_checked':trimmed,'monthly_rankings_checked':len(members),'funding_symbols':len(meta['symbols']),'funding_events':source_events,
        'funding_price_sources':dict(prices),'raw_api_responses_verified':source_files,'official_mark_archives_independently_parsed':archive_count,
        'overlapping_v409_funding_records_equal':overlap,'source_sha256':r.sha(__file__),'post_2025_observations':0,**resolved.fingerprint()}
    r.save(ART/'INPUT_VERIFICATION.json',check);print(check,flush=True)


def results():
    resolved.verify_sources();fp=resolved.fingerprint();check=r.read(ART/'INPUT_VERIFICATION.json');assert check['all_passed'] and all(check[k]==a for k,a in fp.items())
    result=r.read(ART/'RESULTS.json');assert all(result[k]==a for k,a in fp.items());fund=b.load_funding();raw={c['id']:c for c in resolved.load_candidates()}
    counts=Counter();exact={};by_year={}
    for year in range(2020,2026):
        for scenario,assumption in b.SCENARIOS.items():
            node=b.ledger(year,scenario);metric=result['annual'][str(year)][scenario];receipt=r.read(ART/'runs'/f'{year}_{scenario}.json')
            assert receipt['metric']==metric and receipt['ledger_sha256']==r.sha(ART/'runs'/f'{year}_{scenario}.json.gz') and all(receipt[k]==a for k,a in fp.items())
            start=int(r.utc(f'{year}-01-01').timestamp()*1000);end=int(r.utc(f'{year+1}-01-01').timestamp()*1000);fee=assumption['fee_bps']/10000;slip=assumption['slippage_bps']/10000
            events=defaultdict(float);non_entry=defaultdict(float);events[start]=0;events[end]=0
            assert len({a['id'] for a in node['ledger']})==len(node['ledger'])==metric['trades'];proxy_count=0;proxy_abs=0.;proxy_signed=0.
            for p in node['ledger']:
                c=raw[p['id']];path=c['paths']['ladder'];trace=np.asarray(path['trace']);assert p['entry_ts_ms']==c['entry_ts']*1000 and p['exit_ts_ms']==path['exit_ts']*1000
                assert start<=p['entry_ts_ms']<end-5*86400000 and p['exit_ts_ms']<=end
                loss=c['stop']*(1+slip)-c['entry']*(1-slip)+fee*(c['stop']*(1+slip)+c['entry']*(1-slip))
                close(p['qty'],min(.20*p['equity_at_entry']/c['entry'],.005*p['equity_at_entry']/loss));close(p['reference_notional'],p['qty']*c['entry']);close(p['stop_risk_with_execution_costs'],p['qty']*loss)
                cash=0.;fees=0.;slips=0.;sold=0.;bought=0.
                for fill in p['fills']:
                    direction=-1 if fill['side']=='SELL' else 1;price=fill['reference_price']*(1+direction*slip)
                    close(fill['execution_price'],price);close(fill['notional'],price*fill['qty']);close(fill['fee'],fill['notional']*fee);close(fill['slippage_cost'],fill['reference_price']*fill['qty']*slip)
                    cash-=direction*fill['notional'];fees+=fill['fee'];slips+=fill['slippage_cost'];cost=fill['fee']+fill['slippage_cost'];events[fill['timestamp_ms']]-=cost
                    if direction==1:bought+=fill['qty'];non_entry[fill['timestamp_ms']]-=cost
                    else:sold+=fill['qty']
                close([fees,slips,sold,bought],[p['fees'],p['slippage'],p['qty'],p['qty']])
                for step in path['trace']:change=p['reference_notional']*step[5];events[step[0]*1000]+=change;non_entry[step[0]*1000]+=change
                pack=fund[p['symbol']];lo=np.searchsorted(pack['times'],p['entry_ts_ms'],side='right');hi=np.searchsorted(pack['times'],p['exit_ts_ms'],side='right');expected=pack['events'][lo:hi]
                assert len(expected)==len(p['funding_events']);fc=0.
                for actual,source in zip(p['funding_events'],expected):
                    assert all(actual[k]==a for k,a in source.items());idx=np.searchsorted(trace[:,0]*1000,source['funding_ts_ms'],side='left')-1
                    qty=p['qty']*(trace[idx,3] if idx>=0 else 1.);amount=qty*source['mark_price']*source['funding_rate'];close(actual['remaining_qty'],qty);close(actual['cashflow'],amount)
                    fc+=amount;events[source['funding_ts_ms']]+=amount;non_entry[source['funding_ts_ms']]+=amount
                    if source['price_source']!='funding_api_settlement_mark':
                        proxy_count+=1;proxy_abs+=abs(amount);proxy_signed+=amount
                        if amount:exact[(p['symbol'],source['funding_ts_ms'])]={'symbol':p['symbol'],**source}
                close(fc,p['funding']);close(cash-fees+fc,p['pnl']);close(p['reference_notional']*path['gross_return']-fees-slips+fc,p['pnl'])
                counts['fills']+=len(p['fills']);counts['funding_payments']+=len(expected)
            curve=np.asarray(node['curve']);times=sorted(events);balance=100+np.cumsum([events[t] for t in times]);observed=pd.Series(curve[:,1],index=curve[:,0]).groupby(level=0).last()
            assert observed.index.tolist()==times;close(observed.to_numpy(),balance);close(metric['return_pct'],balance[-1]-100);close(metric['curve_values'],curve[:,1]);close(metric['max_dd_pct'],np.max(1-curve[:,1]/np.maximum.accumulate(curve[:,1]))*100)
            close(balance[-1],100+sum(p['pnl'] for p in node['ledger']))
            for metric_key,trade_key in [('fees_pct','fees'),('slippage_pct','slippage'),('funding_pct','funding')]:close(metric[metric_key],sum(p[trade_key] for p in node['ledger']))
            active=[];waves=set();cooldown={};paid=0.;nt=np.array(sorted(non_entry));nc=np.cumsum([non_entry[t] for t in nt])
            for p in sorted(node['ledger'],key=lambda a:(a['entry_ts_ms'],-raw[a['id']]['score'],a['symbol'],a['tf'])):
                t=p['entry_ts_ms'];i=np.searchsorted(nt,t,side='right')-1;equity=100+(nc[i] if i>=0 else 0)-paid;close(equity,p['equity_at_entry'])
                c=raw[p['id']];key=(p['symbol'],p['tf']);wave=(*key,c['wave_key']);assert wave not in waves and t>=cooldown.get(key,0)
                active=[a for a in active if a['exit_ts_ms']>t];notional=0.;risk=0.
                for a in active:
                    tr=np.asarray(raw[a['id']]['paths']['ladder']['trace']);j=np.searchsorted(tr[:,0]*1000,t,side='right')-1;rem,mark,stop=(tr[j,3],tr[j,1],tr[j,4]) if j>=0 else (1.,a['entry'],a['stop'])
                    qty=a['qty']*rem;notional+=qty*max(a['entry'],mark);cost=qty*stop*(1+slip);risk+=max(0.,cost-qty*min(a['entry'],mark)+cost*fee)
                entry=p['fills'][0];cost=entry['fee']+entry['slippage_cost'];after=equity-cost;assert len(active)<5 and notional+p['reference_notional']<=after+1e-8 and risk+p['stop_risk_with_execution_costs']<=.02*after+1e-8
                active.append(p);waves.add(wave);cooldown[key]=max(p['exit_ts_ms'],t+4*3600000);paid+=cost;counts['entry_cap_checks']+=1
            by_year[f'{year}/{scenario}']={'proxy_funding_payments':proxy_count,'proxy_absolute_cashflow_at_start100':proxy_abs,'proxy_net_cashflow_at_start100':proxy_signed}
            counts['nodes']+=1;counts['scenario_trades']+=len(node['ledger']);counts['proxy_funding_payments']+=proxy_count
    for name,years in r.read(ART/'ECONOMIC_PROTOCOL.json')['splits'].items():
        for scenario in b.SCENARIOS:
            a=b.original.linked([result['annual'][str(y)] for y in years],scenario);saved=result['periods'][name][scenario]['corrected_expanded']
            assert {k:x for k,x in saved.items() if k!='calendar_weekly_ci95'}==a
            wa,ga=b.statistics.calendar_returns(b.linked_curve(years,scenario),f'{years[0]}-01-01',f'{years[-1]+1}-01-01');wb,gb=b.statistics.calendar_returns(b.linked_curve(years,scenario,True),f'{years[0]}-01-01',f'{years[-1]+1}-01-01')
            assert ga==gb and saved['calendar_weekly_ci95']==b.statistics.interval(wa) and result['paired_comparisons'][name][scenario]['expanded_minus_old']==b.statistics.interval(wa-wb,alpha=.025)
            close(np.prod(1+wa)*100-100,saved['return_pct'])
    r.save(ART/'EXACT_MARK_DATA_REQUEST.json',{'unique_events':len(exact),'symbols':len({s for s,t in exact}),'events':list(exact.values()),'purchase_made':False})
    r.save(ART/'FUNDING_EXPOSURE.json',{'annual':by_year,'qualification':'Absolute proxy cashflow measures funding-notional exposure; not a bound on exact mark error or an execution-coupled sensitivity result.'})
    checks={'all_accounting_checks_passed':True,**dict(counts),'exact_mark_unique_events_needed':len(exact),'results_sha256':r.sha(ART/'RESULTS.json'),
        'input_verification_sha256':r.sha(ART/'INPUT_VERIFICATION.json'),'source_sha256':r.sha(__file__),'post_2025_observations':0,'fresh_oos':False,'goal_complete':False,'live_signoff':'NOT_GRANTED'}
    r.save(ART/'INDEPENDENT_VERIFICATION.json',checks);print(checks,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['inputs','results']);a=p.parse_args();{'inputs':inputs,'results':results}[a.action]()
