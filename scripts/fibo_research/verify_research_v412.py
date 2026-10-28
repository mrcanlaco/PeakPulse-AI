"""Independent exit-path, historical funding and portfolio cash verification."""
from collections import defaultdict
import gzip
import json
import pickle
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import research_v412 as v

r=v.r;ART=v.ART


def close(a,b,tol=1e-8):
    assert np.allclose(a,b,atol=tol,rtol=0),f'Numerical mismatch: {a} / {b}'


def independent_single_exit(c,epochs,prices,arm):
    t=c['entry_ts'];end=t+(72 if c['tf']=='4h' else 120)*3600
    i=np.searchsorted(epochs,t);j=np.searchsorted(epochs,end);ts=epochs[i:j];p=prices[i:j]
    assert len(ts) and ts[0]==t
    triggers=p[:,1]>=c['stop']
    if arm==v.ARMS[2]:triggers|=p[:,2]<=c['targets'][0]
    hits=np.flatnonzero(triggers);k=int(hits[0]) if len(hits) else len(ts)-1
    if p[k,1]>=c['stop']:exit_price=max(c['stop'],p[k,0]);reason='stop'
    elif arm==v.ARMS[2] and p[k,2]<=c['targets'][0]:exit_price=c['targets'][0];reason='tp1'
    else:exit_price=p[k,3];reason='horizon' if ts[k]+300==end or arm==v.ARMS[2] else 'data_boundary_before_horizon'
    after=np.ones(k+1);after[-1]=0
    cumulative=1-p[:k+1,3]/c['entry'];cumulative[-1]=1-exit_price/c['entry']
    deltas=np.diff(np.r_[0,cumulative])
    expected=np.column_stack((ts[:k+1]+300,p[:k+1,3],np.ones(k+1),after,np.full(k+1,c['stop']),deltas,1-after))
    return expected,float(cumulative[-1]),reason,int(ts[k]+300)


def inputs():
    v.verify_sources();manifest=r.read(ART/'PATH_MANIFEST.json');original_manifest=r.read(v.q.ART/'history/CANDIDATE_MANIFEST.json')
    paths=0;candidates=0;issues=0
    for symbol,item in manifest['symbols'].items():
        source=v.q.ART/'history/candidates'/f'{symbol}.pkl.gz';assert r.sha(source)==original_manifest['symbols'][symbol]['sha256']
        with gzip.open(source,'rb') as fh:original={c['id']:c for c in pickle.load(fh)}
        path=ART/'paths'/f'{symbol}.pkl.gz';assert r.sha(path)==item['sha256']
        with gzip.open(path,'rb') as fh:rows=pickle.load(fh)
        frame=v.prev.load_bars(symbol);epochs=r.epoch_seconds(frame.index);prices=frame[['open','high','low','close']].to_numpy()
        for c in rows:
            assert {k:val for k,val in c.items() if k not in ('research_paths','research_quality')}==original[c['id']]
            assert c['research_paths'][v.ARMS[0]]==c['paths']['ladder'] and c['research_paths'][v.ARMS[2]]==c['paths']['tp1']
            for arm in v.ARMS[1:]:
                trace,gross,reason,exit_ts=independent_single_exit(c,epochs,prices,arm);p=c['research_paths'][arm]
                close(trace,np.asarray(p['trace']));close(gross,p['gross_return'])
                assert reason==p['exit_reason'] and exit_ts==p['exit_ts'];paths+=1
            for arm,p in c['research_paths'].items():
                quality=c['research_quality'][arm];end=quality['nominal_horizon_end'] if p['exit_reason'] in ('horizon','data_boundary_before_horizon') else p['exit_ts']
                observed=epochs[(epochs>=c['entry_ts'])&(epochs<end)]
                assert quality['missing_bars']==(end-c['entry_ts'])//300-len(observed)
                issues+=quality['missing_bars']>0
            candidates+=1
    funding,overlap=v.load_funding();fmeta=r.read(ART/'funding/MANIFEST.json');sources=0;new_events=0
    for symbol,item in fmeta['symbols'].items():
        if item['mode']!='new_official_download':continue
        rates={};marks={}
        for relative,digest in item['record']['raw_responses'].items():
            path=ART/relative;assert r.sha(path)==digest
            with gzip.open(path,'rt',encoding='utf8') as fh:raw=json.load(fh)
            params=raw['params'];assert v.f.START_MS<=params['startTime']<=params['endTime']<v.f.LIMIT_MS
            if raw['url']==v.f.FUNDING_URL:
                for event in raw['data']:
                    assert event['symbol']==symbol and params['startTime']<=event['fundingTime']<=params['endTime'];rates[event['fundingTime']]=event
            elif raw['url']==v.f.MARK_URL:
                for bar in raw['data']:
                    assert params['startTime']<=bar[0]<=params['endTime'];marks[bar[0]]=float(bar[1])
            else:raise AssertionError('Unexpected source')
            sources+=1
        assert set(rates)==set(funding[symbol]['times'])
        for event in funding[symbol]['events']:
            source=rates[event['funding_ts_ms']];close(event['funding_rate'],float(source['fundingRate']))
            if event['price_source']=='funding_api_settlement_mark':
                close(event['mark_price'],float(source['markPrice']));assert event['mark_reference_ts_ms']==event['funding_ts_ms']
            else:
                assert not source['markPrice'] or float(source['markPrice'])<=0
                assert 0<=event['funding_ts_ms']-event['mark_reference_ts_ms']<=15000
                close(event['mark_price'],marks[event['mark_reference_ts_ms']])
            new_events+=1
    r.save(ART/'INPUT_VERIFICATION.json',{'all_passed':True,'candidates_verified':candidates,'new_arm_paths_independently_recomputed':paths,
        'candidate_path_quality_issues':issues,'v409_funding_overlap_records_exact':overlap,'new_raw_responses_verified':sources,'new_funding_events_verified':new_events,
        'post_2025_backtest_observations':0,**v.fingerprint()})
    print(json.dumps(r.read(ART/'INPUT_VERIFICATION.json')),flush=True)


def results():
    v.verify_sources();inputs_check=r.read(ART/'INPUT_VERIFICATION.json')
    assert inputs_check['all_passed'] and all(inputs_check[k]==value for k,value in v.fingerprint().items())
    result=r.read(ART/'RESULTS.json');funding,_=v.load_funding();raw={c['id']:c for c in v.load_candidates()}
    nodes=0;trades=0;fills=0;payments=0;proxy=0;accepted_issues=[];exact_required={};cap_checks=0
    for year in range(2020,2026):
        for arm in v.ARMS:
            for scenario,assumptions in v.SCENARIOS.items():
                node=v.node_ledger(year,arm,scenario);metric=result['annual'][str(year)][arm][scenario]
                receipt=r.read(ART/'runs'/f'{year}_{arm}_{scenario}.json')
                assert receipt['metric']==metric and receipt['ledger_sha256']==r.sha(ART/'runs'/f'{year}_{arm}_{scenario}.json.gz')
                assert all(receipt[k]==value for k,value in v.fingerprint().items())
                start=int(r.utc(f'{year}-01-01').timestamp()*1000);end=int(r.utc(f'{year+1}-01-01').timestamp()*1000)
                events=defaultdict(float);non_entry=defaultdict(float);events[start]=0;events[end]=0
                fee_rate=assumptions['fee_bps']/10000;slip_rate=assumptions['slippage_bps']/10000
                assert len({p['id'] for p in node['ledger']})==len(node['ledger'])==metric['trades']
                for p in node['ledger']:
                    c=raw[p['id']];path=c['research_paths'][arm];trace=np.asarray(path['trace'],dtype=float)
                    assert start<=p['entry_ts_ms']<end-5*86400000 and p['exit_ts_ms']==path['exit_ts']*1000<=end
                    assert p['entry_ts_ms']==c['entry_ts']*1000
                    close(p['entry'],c['entry']);close(p['stop'],c['stop']);close(p['reference_notional'],p['qty']*p['entry'])
                    assert p['reference_notional']<=.20*p['equity_at_entry']+1e-8
                    stop_loss=c['stop']*(1+slip_rate)-c['entry']*(1-slip_rate)+fee_rate*(c['stop']*(1+slip_rate)+c['entry']*(1-slip_rate))
                    close(p['qty'],min(.20*p['equity_at_entry']/c['entry'],.005*p['equity_at_entry']/stop_loss))
                    close(p['stop_risk_with_execution_costs'],p['qty']*stop_loss)
                    actual_cash=0;fees=0;slips=0;sellqty=0;buyqty=0
                    for fill in p['fills']:
                        direction=-1 if fill['side']=='SELL' else 1
                        execution=fill['reference_price']*(1+direction*slip_rate)
                        close(fill['execution_price'],execution);close(fill['notional'],execution*fill['qty'])
                        close(fill['fee'],execution*fill['qty']*fee_rate);close(fill['slippage_cost'],fill['reference_price']*fill['qty']*slip_rate)
                        actual_cash-=direction*fill['notional'];fees+=fill['fee'];slips+=fill['slippage_cost']
                        cost=fill['fee']+fill['slippage_cost'];events[fill['timestamp_ms']]-=cost
                        if direction==1:buyqty+=fill['qty'];non_entry[fill['timestamp_ms']]-=cost
                        else:sellqty+=fill['qty']
                    close([fees,slips,sellqty,buyqty],[p['fees'],p['slippage'],p['qty'],p['qty']])
                    for step in path['trace']:
                        change=p['reference_notional']*step[5];events[step[0]*1000]+=change;non_entry[step[0]*1000]+=change
                    pack=funding[p['symbol']];lo=np.searchsorted(pack['times'],p['entry_ts_ms'],side='right');hi=np.searchsorted(pack['times'],p['exit_ts_ms'],side='right')
                    expected=pack['events'][lo:hi];assert len(expected)==len(p['funding_events'])
                    total_funding=0
                    for actual,source in zip(p['funding_events'],expected):
                        assert all(actual[k]==value for k,value in source.items())
                        k=np.searchsorted(trace[:,0]*1000,source['funding_ts_ms'],side='left')-1
                        quantity=p['qty']*(trace[k,3] if k>=0 else 1.)
                        cash=quantity*source['mark_price']*source['funding_rate']
                        close(actual['remaining_qty'],quantity);close(actual['cashflow'],cash)
                        total_funding+=cash;events[source['funding_ts_ms']]+=cash;non_entry[source['funding_ts_ms']]+=cash
                        if source['price_source']!='funding_api_settlement_mark':
                            proxy+=1
                            if cash!=0:exact_required[(p['symbol'],source['funding_ts_ms'])]={'symbol':p['symbol'],**source}
                    close(total_funding,p['funding']);close(actual_cash-fees+total_funding,p['pnl'])
                    close(p['reference_notional']*path['gross_return']-fees-slips+total_funding,p['pnl'])
                    if c['research_quality'][arm]['missing_bars']:accepted_issues.append({'year':year,'arm':arm,'scenario':scenario,'id':p['id'],**c['research_quality'][arm]})
                    fills+=len(p['fills']);payments+=len(expected)
                curve=np.asarray(node['curve']);timestamps=sorted(events);cash=100+np.cumsum([events[t] for t in timestamps])
                observed=pd.Series(curve[:,1],index=curve[:,0]).groupby(level=0).last()
                assert observed.index.tolist()==timestamps;close(observed.to_numpy(),cash)
                close(curve[:,1],metric['curve_values']);close(metric['return_pct'],cash[-1]-100)
                close(metric['max_dd_pct'],np.max(1-curve[:,1]/np.maximum.accumulate(curve[:,1]))*100)
                close(100+sum(p['pnl'] for p in node['ledger']),cash[-1])
                for m,k in [('fees_pct','fees'),('slippage_pct','slippage'),('funding_pct','funding')]:close(metric[m],sum(p[k] for p in node['ledger']))
                # Reconstruct pre-entry equity and check actual admissions against
                # the registered wave, cooldown, notional and initial-risk rules.
                entries=sorted(node['ledger'],key=lambda p:(p['entry_ts_ms'],-raw[p['id']]['score'],p['symbol'],p['tf']))
                non_times=np.array(sorted(non_entry),dtype='int64');non_cash=np.cumsum([non_entry[t] for t in non_times])
                paid_entry=0.;active=[];waves=set();cooldown={}
                for p in entries:
                    t=p['entry_ts_ms'];idx=np.searchsorted(non_times,t,side='right')-1
                    equity=100+(non_cash[idx] if idx>=0 else 0)-paid_entry;close(equity,p['equity_at_entry'])
                    c=raw[p['id']];wave=(p['symbol'],p['tf'],c['wave_key']);key=(p['symbol'],p['tf'])
                    assert wave not in waves and t>=cooldown.get(key,0)
                    active=[a for a in active if a['exit_ts_ms']>t];notional=0.;risk=0.
                    for a in active:
                        tr=np.asarray(raw[a['id']]['research_paths'][arm]['trace']);j=np.searchsorted(tr[:,0]*1000,t,side='right')-1
                        rem,mark,stop=(tr[j,3],tr[j,1],tr[j,4]) if j>=0 else (1.,a['entry'],a['stop'])
                        qty=a['qty']*rem;notional+=qty*max(a['entry'],mark)
                        stop_value=qty*stop*(1+slip_rate);risk+=max(0.,stop_value-qty*min(a['entry'],mark)+stop_value*fee_rate)
                    entryfill=p['fills'][0];cost=entryfill['fee']+entryfill['slippage_cost'];after=equity-cost
                    assert len(active)<5 and notional+p['reference_notional']<=after+1e-8
                    assert risk+p['stop_risk_with_execution_costs']<=.02*after+1e-8
                    active.append(p);waves.add(wave);cooldown[key]=max(p['exit_ts_ms'],t+4*3600000);paid_entry+=cost;cap_checks+=1
                nodes+=1;trades+=len(node['ledger'])
    periods={'reference_2020_2022':[2020,2021,2022],'validation_2023':[2023],'retrospective_2024_2025':[2024,2025],'all_2020_2025':list(range(2020,2026))}
    for name,years in periods.items():
        for scenario in v.SCENARIOS:
            weekly={}
            for arm in v.ARMS:
                saved=result['periods'][name][scenario][arm]
                base=v.z.linked([result['annual'][str(y)][arm] for y in years],scenario)
                assert {k:val for k,val in saved.items() if k!='calendar_weekly_ci95'}==base
                weekly[arm],_=v.calendar_returns(v.linked_curve(years,arm,scenario),f'{years[0]}-01-01',f'{years[-1]+1}-01-01')
                assert saved['calendar_weekly_ci95']==v.interval(weekly[arm])
                close(np.prod(1+weekly[arm])*100-100,saved['return_pct'])
            for arm in v.ARMS[1:]:
                expected=v.interval(weekly[v.ARMS[0]]-weekly[arm],alpha=.025)
                assert result['comparisons'][name][scenario][arm]['paired_calendar_weekly_interval']==expected
    preserved={}
    for folder in [v.z.ART,v.prev.PRIOR,v.PRIOR]:
        prior=r.read(folder/'CHECKPOINT.json')
        for path,digest in prior['files'].items():assert r.sha(folder/path)==digest,path
        for path,digest in prior.get('additional_sources',{}).items():assert r.sha(r.ROOT/path)==digest,path
        for path,digest in prior.get('additional_artifacts',{}).items():assert r.sha(path)==digest,path
        preserved[folder.name]=len(prior['files'])
    suites=list(ET.parse(ART/'TESTS.xml').getroot().iter('testsuite'));tests={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','errors','failures','skipped')}
    assert tests['tests']>=9 and tests['errors']==tests['failures']==tests['skipped']==0
    r.save(ART/'EXACT_MARK_DATA_REQUEST.json',{'unique_events':len(exact_required),'symbols':len({k[0] for k in exact_required}),
        'events':list(exact_required.values()),'scope':'Nonzero proxy-priced funding in accepted exit-policy portfolios','purchase_made':False})
    output={'all_accounting_checks_passed':True,'complete_execution_coverage':not accepted_issues,'accepted_execution_issues':accepted_issues,
        'scenario_nodes':nodes,'scenario_trade_records':trades,'fill_groups':fills,'funding_payments':payments,'proxy_funding_payments':proxy,
        'entry_cap_and_equity_checks':cap_checks,'tests':tests,'preserved_checkpoints':preserved,'results_sha256':r.sha(ART/'RESULTS.json'),
        'new_path_verification_sha256':r.sha(ART/'INPUT_VERIFICATION.json'),'post_2025_backtest_observations':0,'goal_complete':False,'live_signoff':'NOT_GRANTED'}
    r.save(ART/'INDEPENDENT_VERIFICATION.json',output);print(json.dumps(output),flush=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['inputs','results']);args=parser.parse_args()
    inputs() if args.action=='inputs' else results()
