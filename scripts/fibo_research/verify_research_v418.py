"""Independently verify every grid node and reconstruct linked calendar evidence.

The fixed-quantity cash/cap audit loop is retained verbatim from the verified
v415 auditor except routing its ledger/config to the new grid.
"""
from collections import Counter,defaultdict
import gzip,json,math
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import research_v418 as v
r=v.r;ART=v.ART


def close(a,b):assert np.allclose(a,b,atol=1e-8,rtol=0),(a,b)


def main():
    v.verify_sources();fp=v.fingerprint();check=r.read(ART/'INPUT_VERIFICATION.json');assert check['all_passed'] and all(check[k]==a for k,a in fp.items())
    result=r.read(ART/'RESULTS.json');assert all(result[k]==a for k,a in fp.items());fund=v.load_funding();raw={c['id']:c for c in v.load_candidates()}
    counts=Counter();exact={};by_year={}
    for year in range(2020,2026):
        for scenario,assumption in v.SCENARIOS.items():
            node=v.ledger(year,scenario);metric=result['annual'][str(year)][scenario];receipt=r.read(ART/'runs'/f'{year}_{scenario}.json')
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
    finish(result,counts,exact,by_year)


def independent_interval(values):
    n=len(values);rng=np.random.default_rng(412);starts=rng.integers(0,n,(10000,math.ceil(n/4)));means=[]
    for row in starts:
        ix=[(int(a)+j)%n for a in row for j in range(4)][:n];weights=np.bincount(ix,minlength=n);means.append(float(weights@values/n*100))
    return np.quantile(means,[.025,.975])


def finish(result,counts,exact,by_year):
    nodes={(year,scenario):v.ledger(year,scenario) for year in range(2020,2026) for scenario in v.SCENARIOS}
    for year in range(2020,2026):
        for scenario,old in v.ENDPOINTS.items():
            assert nodes[(year,scenario)]==v.b.ledger(year,old)
            assert result['annual'][str(year)][scenario]==r.read(v.b.ART/'RESULTS.json')['annual'][str(year)][old]
            counts['exact_baseline_nodes']+=1
    for label,years in v.SPLITS.items():
        for scenario in v.SCENARIOS:
            cash=100.;all_values=[100.];points={};components=Counter();trade_count=0;missing=0
            for year in years:
                node=nodes[(year,scenario)];scale=cash/100;vals=np.asarray(node['curve']);all_values.extend(vals[:,1]*scale)
                for t,value in vals:points[int(t)]=float(value*scale)
                for p in node['ledger']:
                    components['gross_reference_pnl_pct']+=scale*p['reference_notional']*p['gross_reference_return']
                    for dest,key in [('fees_pct','fees'),('slippage_pct','slippage'),('funding_pct','funding')]:components[dest]+=scale*p[key]
                    trade_count+=1;missing+=p['missing_execution_bars']
                cash=float(vals[-1,1]*scale)
            saved=result['periods'][label][scenario];close(saved['return_pct'],cash-100)
            close(saved['max_dd_pct'],np.max(1-np.asarray(all_values)/np.maximum.accumulate(all_values))*100)
            assert saved['trades']==trade_count and saved['accepted_missing_execution_bars']==missing
            for key,value in components.items():close(saved[key],value)
            series=pd.Series(list(points.values()),index=pd.to_datetime(list(points),unit='ms',utc=True)).sort_index()
            start=r.utc(f'{years[0]}-01-01');end=r.utc(f'{years[-1]+1}-01-01');grid=pd.DatetimeIndex(sorted({start,end,*pd.date_range(start,end,freq='W-MON')}))
            sampled=series.asof(grid).to_numpy();assert np.isfinite(sampled).all();weekly=sampled[1:]/sampled[:-1]-1
            close(saved['calendar_weekly_ci95']['mean_weekly_pct'],np.mean(weekly)*100);close(saved['calendar_weekly_ci95']['ci_pct'],independent_interval(weekly))
            assert saved['calendar_weekly_ci95']['intervals']==len(weekly);close(np.prod(1+weekly)*100-100,cash-100);counts['linked_periods_verified']+=1
            ids={(year,a['id']) for year in years for a in nodes[(year,scenario)]['ledger']};ref={(year,a['id']) for year in years for a in nodes[(year,'vip6_slip10')]['ledger']}
            assert result['admission_changes'][label][scenario]=={'added_vs_standard':len(ids-ref),'removed_vs_standard':len(ref-ids),'symmetric_difference':len(ids^ref)}
        for tier in ('vip6','regular'):
            rows=[{'slippage_bps':slip,'return_pct':result['periods'][label][f'{tier}_slip{slip}']['return_pct']} for slip in (10,20,30,40,50)]
            changes=[]
            for left,right in zip(rows[:-1],rows[1:]):
                if left['return_pct']>0>=right['return_pct'] or left['return_pct']<=0<right['return_pct']:
                    changes.append({'left_slippage_bps':left['slippage_bps'],'right_slippage_bps':right['slippage_bps'],'left_return_pct':left['return_pct'],'right_return_pct':right['return_pct'],
                        'direction':'positive_to_nonpositive' if left['return_pct']>0 else 'nonpositive_to_positive'})
            assert result['sign_diagnostics'][label][tier]['adjacent_sign_changes']==changes
            assert result['sign_diagnostics'][label][tier]['point_returns_monotone_nonincreasing']==all(left['return_pct']>=right['return_pct'] for left,right in zip(rows[:-1],rows[1:]))
    root=ET.parse(ART/'TESTS.xml').getroot();suites=list(root.iter('testsuite'));tests={k:sum(int(a.get(k,0)) for a in suites) for k in ('tests','errors','failures','skipped')}
    assert tests['tests']>=14 and tests['errors']==tests['failures']==tests['skipped']==0
    previous=r.read(v.PRIOR/'CHECKPOINT.json')
    for path,h in previous['files'].items():assert r.sha(v.PRIOR/path)==h,path
    for path,h in previous['additional_sources'].items():assert r.sha(v.ROOT/path)==h,path
    r.save(ART/'EXACT_MARK_DATA_REQUEST.json',{'unique_events':len(exact),'events':list(exact.values()),'purchase_made':False})
    r.save(ART/'FUNDING_EXPOSURE.json',{'annual':by_year,'qualification':'Proxy-price cashflow exposure, not a measured funding error.'})
    record={'all_passed':True,**dict(counts),'tests':tests,'previous_files_preserved':len(previous['files']),'results_sha256':r.sha(ART/'RESULTS.json'),
        'input_verification_sha256':r.sha(ART/'INPUT_VERIFICATION.json'),'exact_mark_unique_events_needed':len(exact),'post_2025_observations':0,'goal_complete':False,'live_signoff':'NOT_GRANTED'}
    r.save(ART/'INDEPENDENT_VERIFICATION.json',record);print(record,flush=True)


if __name__=='__main__':main()
