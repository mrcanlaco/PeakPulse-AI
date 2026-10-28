"""Independent full-period cash/cap reconstruction and marked subperiod audit."""
from collections import Counter,defaultdict
import argparse,gzip,json,math
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import research_v419 as v
import verify_research_v416 as funding_source
import verify_research_v417 as path_source
r=v.r;ART=v.ART


def close(a,b):assert np.allclose(a,b,atol=1e-7,rtol=0),(a,b)


def results():
    v.verify_sources();fp=v.fingerprint();check=r.read(ART/'INPUT_VERIFICATION.json');assert check['all_passed'] and all(check[k]==a for k,a in fp.items())
    result=r.read(ART/'RESULTS.json');assert all(result[k]==a for k,a in fp.items());fund,_=v.load_funding();raw={c['id']:c for c in v.load_candidates()}
    counts=Counter();exact={};by_year={}
    for arm in v.ARMS:
        for scenario,assumption in v.SCENARIOS.items():
            node=v.ledger(arm,scenario);metric=result['metrics'][arm][scenario];receipt=r.read(ART/'runs'/f'{arm}_{scenario}.json')
            assert receipt['metric']==metric and receipt['ledger_sha256']==r.sha(ART/'runs'/f'{arm}_{scenario}.json.gz') and all(receipt[k]==a for k,a in fp.items())
            start=int(r.utc(v.START).timestamp()*1000);end=int(r.utc(v.END).timestamp()*1000);fee=assumption['fee_bps']/10000;slip=assumption['slippage_bps']/10000
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
            by_year[f'{arm}/{scenario}']={'proxy_funding_payments':proxy_count,'proxy_absolute_cashflow_at_start100':proxy_abs,'proxy_net_cashflow_at_start100':proxy_signed}
            counts['nodes']+=1;counts['scenario_trades']+=len(node['ledger']);counts['proxy_funding_payments']+=proxy_count
    finish(result,counts,exact,by_year)


def inputs():
    v.verify_sources();raw=v.load_candidates();annual=v.load_candidates('annual_eligible_continuous');meta=r.read(ART/'CANDIDATE_AUDIT.json');annual_ids={p['id'] for p in annual};extra=[c for c in raw if c['id'] not in annual_ids]
    assert len(extra)==meta['extra_candidates'] and {c['id'] for c in extra}=={p['id'] for p in meta['extra']};events=r.read(v.b.ART/'EVENTS.json')['events'];checked=0
    for s in sorted({c['symbol'] for c in extra}):
        frame=v.data.load_bars(s)
        for c in (c for c in extra if c['symbol']==s):
            t=c['entry_ts'];exit=c['paths']['ladder']['exit_ts'];end=t+(72 if c['tf']=='4h' else 120)*3600
            independent=path_source.independent_exits(frame,{**c,'horizon_end':end})
            close(np.asarray(independent['trace']),np.asarray(c['paths']['ladder']['trace']));close(independent['gross_return'],c['paths']['ladder']['gross_return']);assert independent['exit_ts']==exit and independent['exit_reason']==c['paths']['ladder']['exit_reason']
            used=frame.loc[(frame.index>=pd.Timestamp(t,unit='s',tz='UTC'))&(frame.index<pd.Timestamp(exit,unit='s',tz='UTC'))]
            assert np.array_equal(r.epoch_seconds(used.index),np.arange(t,exit,300)) and used.iloc[0].volume>0
            for group in independent['groups']:assert frame.at[pd.Timestamp(group['timestamp_ms']/1000-300,unit='s',tz='UTC'),'volume']>0
            assert independent['exit_reason']!='horizon' or exit==end
            for e in events:
                if e['symbol']!=s:continue
                settle=r.utc(e['settlement_at']).timestamp();assert not t<settle<=exit
                if r.utc(e['known_from_utc']).timestamp()<=t and (not e.get('relaunch_at') or t<r.utc(e['relaunch_at']).timestamp()):assert t<r.utc(e['entry_close_only_from'] or e['settlement_at']).timestamp()
            checked+=1
    funded,overlap=v.load_funding();funding_source.v=v;funding_source.ART=ART;_,provenance=funding_source.funding()
    record={'all_passed':True,'annual_candidates':len(annual),'all_candidates':len(raw),'extra_paths_independently_recomputed':checked,'funding_overlap_v415_exact':overlap,**provenance,**v.fingerprint()}
    r.save(ART/'INPUT_VERIFICATION.json',record);print(record,flush=True)


def interval(values,alpha=.05):
    n=len(values);rng=np.random.default_rng(412);starts=rng.integers(0,n,(10000,math.ceil(n/4)));means=[]
    for row in starts:
        ix=[(int(a)+j)%n for a in row for j in range(4)][:n];weights=np.bincount(ix,minlength=n);means.append(float(weights@values/n*100))
    return np.quantile(means,[alpha/2,1-alpha/2])


def finish(result,counts,exact,by_year):
    nodes={(arm,s):v.ledger(arm,s) for arm in v.ARMS for s in v.SCENARIOS};extra_ids={p['id'] for p in r.read(ART/'CANDIDATE_AUDIT.json')['extra']}
    for s in v.SCENARIOS:
        assert result['accepted_year_end_extra'][s]==[p['id'] for p in nodes[('all_continuous',s)]['ledger'] if p['id'] in extra_ids]
        assert not any(p['id'] in extra_ids for p in nodes[('annual_eligible_continuous',s)]['ledger'])
    for label,(start,end) in v.SPLITS.items():
        lo=int(r.utc(start).timestamp()*1000);hi=int(r.utc(end).timestamp()*1000);grid=pd.DatetimeIndex(sorted({r.utc(start),r.utc(end),*pd.date_range(r.utc(start),r.utc(end),freq='W-MON')}))
        for scenario in v.SCENARIOS:
            baseline=[];cash=100.
            for y in range(2020,2026):
                old=v.b.ledger(y,scenario);scale=cash/100;baseline.extend((t,val*scale) for t,val in old['curve']);cash=old['curve'][-1][1]*scale
            curves={'annual_reset_baseline':baseline,**{arm:nodes[(arm,scenario)]['curve'] for arm in v.ARMS}};returns={}
            for arm,rawcurve in curves.items():
                curve=np.asarray(rawcurve);first=curve[curve[:,0]<=lo][-1,1];last=curve[curve[:,0]<=hi][-1,1];within=curve[(curve[:,0]>lo)&(curve[:,0]<=hi),1];values=np.r_[first,within,last]
                saved=result['periods'][label][scenario][arm];close([saved['start_nav'],saved['end_nav'],saved['return_pct'],saved['max_dd_pct']],
                    [first,last,(last/first-1)*100,np.max(1-values/np.maximum.accumulate(values))*100])
                series=pd.Series(curve[:,1],index=pd.to_datetime(curve[:,0].astype('int64'),unit='ms',utc=True)).groupby(level=0).last().sort_index();nav=series.asof(grid).to_numpy();assert np.isfinite(nav).all()
                weekly=nav[1:]/nav[:-1]-1;returns[arm]=weekly;close(saved['calendar_weekly_ci95']['ci_pct'],interval(weekly));close(saved['calendar_weekly_ci95']['mean_weekly_pct'],np.mean(weekly)*100)
                assert saved['calendar_weekly_ci95']['intervals']==len(weekly);close(np.prod(1+weekly),last/first);counts['marked_subperiods_verified']+=1
                if arm!='annual_reset_baseline':
                    ledger=nodes[(arm,scenario)]['ledger'];expected={'entered_in_period':sum(lo<=p['entry_ts_ms']<hi for p in ledger),
                        'carried_in_ids':[p['id'] for p in ledger if p['entry_ts_ms']<lo<p['exit_ts_ms']],
                        'carried_out_ids':[p['id'] for p in ledger if p['entry_ts_ms']<hi<p['exit_ts_ms']]}
                    assert expected==result['carry'][label][scenario][arm]
            for arm in v.ARMS:
                delta=returns[arm]-returns['annual_reset_baseline'];saved=result['paired_differences'][label][scenario][arm+'_minus_annual']
                close(saved['ci_pct'],interval(delta,alpha=.025));close(saved['mean_weekly_pct'],delta.mean()*100);counts['paired_comparisons_verified']+=1
            delta=returns['all_continuous']-returns['annual_eligible_continuous'];saved=result['paired_differences'][label][scenario]['all_minus_annual_eligible_continuous']
            close(saved['ci_pct'],interval(delta,alpha=.025));close(saved['mean_weekly_pct'],delta.mean()*100);counts['paired_comparisons_verified']+=1
    suites=list(ET.parse(ART/'TESTS.xml').getroot().iter('testsuite'));tests={k:sum(int(a.get(k,0)) for a in suites) for k in ('tests','errors','failures','skipped')};assert tests['tests']>=8 and tests['errors']==tests['failures']==tests['skipped']==0
    old=r.read(v.PRIOR/'CHECKPOINT.json')
    for p,h in old['files'].items():assert r.sha(v.PRIOR/p)==h,p
    for p,h in old['additional_sources'].items():assert r.sha(v.ROOT/p)==h,p
    r.save(ART/'EXACT_MARK_DATA_REQUEST.json',{'unique_events':len(exact),'events':list(exact.values()),'purchase_made':False})
    r.save(ART/'FUNDING_EXPOSURE.json',{'arms':by_year,'qualification':'Proxy funding notional exposure; not empirical mark error.'})
    record={'all_passed':True,**dict(counts),'tests':tests,'previous_files_preserved':len(old['files']),'results_sha256':r.sha(ART/'RESULTS.json'),
        'input_verification_sha256':r.sha(ART/'INPUT_VERIFICATION.json'),'exact_mark_unique_events_needed':len(exact),'goal_complete':False,'live_signoff':'NOT_GRANTED'}
    r.save(ART/'INDEPENDENT_VERIFICATION.json',record);print(record,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['inputs','results']);{'inputs':inputs,'results':results}[p.parse_args().action]()
