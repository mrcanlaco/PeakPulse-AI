"""Event-driven independent bracket replay and direct execution cash checks."""
from collections import Counter,defaultdict
import argparse,gzip,json
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import research_v417 as v
import verify_research_v416 as provenance
import report_research_v416 as statistics
r=v.r;ART=v.ART


def close(a,b,tol=1e-8):assert np.allclose(a,b,atol=tol,rtol=0),(a,b)


def independent_exits(frame,leg):
    start=leg['entry_ts'];end=leg['horizon_end'];stamps=r.epoch_seconds(frame.index)
    left=np.searchsorted(stamps,start);right=np.searchsorted(stamps,end);ts=stamps[left:right];prices=frame.iloc[left:right][['open','high','low','close']].to_numpy()
    if not len(ts) or ts[0]!=start:return None
    rem=1.;active=leg['stop'];target=0;cursor=0;fills=[];updates={};reason=None
    while rem>1e-12:
        hit=np.flatnonzero((prices[cursor:,1]>=active)|(prices[cursor:,2]<=leg['targets'][target]))
        if not len(hit):
            k=len(ts)-1;fills.append((k,rem,float(prices[k,3])));rem=0.;reason='horizon';updates[k]=active;break
        k=cursor+int(hit[0]);o,high,low,mark=prices[k]
        if high>=active:
            fills.append((k,rem,float(max(active,o))));rem=0.;reason='stop' if target==0 else 'ratchet'
        else:
            while target<3 and low<=leg['targets'][target] and rem>1e-12:
                amount=min(rem,[.5,.3,.2][target]);fills.append((k,amount,leg['targets'][target]));rem-=amount;target+=1
                if rem<=1e-12:rem=0.;reason=f'tp{target}';break
                active=leg['entry'] if target==1 else leg['targets'][0]
                if high>=active:fills.append((k,rem,active));rem=0.;reason='ratchet';break
        updates[k]=active
        if rem and k==len(ts)-1:fills.append((k,rem,float(mark)));rem=0.;reason='horizon'
        cursor=k+1
    last=max(a[0] for a in fills);groups=defaultdict(list)
    for k,q,p in fills:groups[k].append((q,p))
    trace=[];remaining=1.;realized=0.;last_nav=0.;stop=leg['stop'];turnover=[]
    for k in range(last+1):
        before=remaining
        if k in groups:
            qty=sum(q for q,p in groups[k]);notional=sum(q*p for q,p in groups[k]);realized+=qty-notional/leg['entry'];remaining=max(0.,remaining-qty)
            turnover.append({'timestamp_ms':int(ts[k]+300)*1000,'fraction':qty,'reference_price':notional/qty})
        if k in updates:stop=updates[k]
        total=realized+remaining*(1-float(prices[k,3])/leg['entry'])
        trace.append((int(ts[k]+300),float(prices[k,3]),before,remaining,stop,total-last_nav,k==last));last_nav=total
    return {'trace':trace,'gross_return':realized,'exit_reason':reason,'exit_ts':int(ts[last]+300),'groups':turnover,'fills':fills}


def inputs():
    v.verify_sources();legs=v.load_paths();original=v.originals();pairs=r.read(v.PRIOR/'MATCHES.json')['pairs'];events=r.read(v.prev.PRIOR/'EVENTS.json')['events'];path_meta=r.read(ART/'PATH_MANIFEST.json')
    expected={p['id']+'/'+side for p in pairs for side in ('treated','control')};assert set(legs)==expected;pairmap={p['id']:p for p in pairs};count=0;issues=[];holding_zero=0;original_exact=0;direct={}
    for s in sorted({a['symbol'] for a in legs.values()}):
        frame=v.prev.load_bars(s);stamps=r.epoch_seconds(frame.index)
        for key,leg in ((k,a) for k,a in legs.items() if a['symbol']==s):
            c=original[leg['id']];pair=pairmap[leg['id']];assert leg['symbol']==(pair['symbol'] if leg['side']=='treated' else pair['control']['symbol'])
            assert leg['entry_ts']==pair['entry_ts'] and leg['horizon_end']==pair['entry_ts']+(72 if c['tf']=='4h' else 120)*3600
            i=int(np.searchsorted(stamps,leg['entry_ts']))
            if i==len(stamps) or stamps[i]!=leg['entry_ts']:
                assert leg['status']=='NOT_EVALUABLE';issues.append({'key':key,'status':leg['status'],'quality':{}});continue
            entry=float(frame.iloc[i]['open']);close(leg['entry'],entry);close(leg['stop']/entry,c['stop']/c['entry']);close(np.array(leg['targets'])/entry,np.array(c['targets'])/c['entry'])
            independent=independent_exits(frame,leg);path=leg['paths']['ladder'];close(np.array(independent['trace']),np.array(path['trace']));close(independent['gross_return'],path['gross_return'])
            assert independent['exit_reason']==path['exit_reason'] and independent['exit_ts']==path['exit_ts']
            if leg['side']=='treated':assert path==c['paths']['ladder'];original_exact+=1
            used=frame.loc[(frame.index>=pd.Timestamp(leg['entry_ts'],unit='s',tz='UTC'))&(frame.index<pd.Timestamp(path['exit_ts'],unit='s',tz='UTC'))]
            last=leg['horizon_end'] if path['exit_reason']=='horizon' else path['exit_ts'];missing=(last-leg['entry_ts'])//300-len(used);truncated=path['exit_reason']=='horizon' and path['exit_ts']<leg['horizon_end']
            q={'missing_bars':missing,'horizon_truncated':truncated,'zero_volume_entry':bool(used.iloc[0].volume<=0),
               'zero_volume_exit_groups':sum(bool(frame.loc[pd.Timestamp(a['timestamp_ms']/1000-300,unit='s',tz='UTC')].volume<=0) for a in independent['groups']),
               'zero_volume_holding_bars':int((used.volume<=0).sum()),
               'settlement_overlaps':[e['settlement_at'] for e in events if e['symbol']==s and leg['entry_ts']<r.utc(e['settlement_at']).timestamp()<=path['exit_ts']]}
            assert q==leg['quality'] and (leg['status']=='COMPLETE')==(not missing and not truncated)
            if leg['status']!='COMPLETE' or q['zero_volume_entry'] or q['zero_volume_exit_groups'] or q['settlement_overlaps']:issues.append({'key':key,'status':leg['status'],'quality':q})
            holding_zero+=q['zero_volume_holding_bars']>0;count+=1;direct[key]={'groups':independent['groups'],'exit_reason':independent['exit_reason'],'exit_ts':independent['exit_ts']}
    assert sorted(issues,key=lambda a:a['key'])==sorted(path_meta['issues'],key=lambda a:a['key'])
    assert holding_zero==path_meta['holding_zero_volume_legs'] and original_exact==path_meta['treated_original_paths_exact']
    provenance.v=v;provenance.ART=ART;funded,source=provenance.funding()
    r.save(ART/'INDEPENDENT_EXIT_GROUPS.json',direct)
    out={'all_passed':True,'legs_recomputed':count,'treated_original_paths_exact':original_exact,'issues':len(issues),'holding_zero_volume_legs':holding_zero,
        **source,'path_manifest_sha256':r.sha(ART/'PATH_MANIFEST.json'),'funding_manifest_sha256':r.sha(ART/'funding/MANIFEST.json'),
        'independent_exit_groups_sha256':r.sha(ART/'INDEPENDENT_EXIT_GROUPS.json')}
    r.save(ART/'INPUT_VERIFICATION.json',out);print(out,flush=True)


def results():
    v.verify_sources();checked=r.read(ART/'INPUT_VERIFICATION.json');result=r.read(ART/'RESULTS.json');legs=v.load_paths();direct=r.read(ART/'INDEPENDENT_EXIT_GROUPS.json')
    assert checked['all_passed'] and checked['path_manifest_sha256']==result['path_manifest_sha256']==r.sha(ART/'PATH_MANIFEST.json')
    assert checked['funding_manifest_sha256']==result['funding_manifest_sha256']==r.sha(ART/'funding/MANIFEST.json')
    assert checked['independent_exit_groups_sha256']==r.sha(ART/'INDEPENDENT_EXIT_GROUPS.json') and result['ledger_sha256']==r.sha(ART/'EVENT_LEDGER.json.gz')
    fund={}
    for s,a in r.read(ART/'funding/MANIFEST.json')['symbols'].items():assert r.sha(a['path'])==a['sha256'];fund[s]=pd.read_parquet(a['path'])
    with gzip.open(ART/'EVENT_LEDGER.json.gz','rt',encoding='utf8') as fh:ledger=json.load(fh)
    pairs=r.read(v.PRIOR/'MATCHES.json')['pairs'];incomplete={p['id'] for p in pairs if any(legs[p['id']+'/'+s]['status']!='COMPLETE' for s in ('treated','control'))}
    assert incomplete=={a['id'] for a in ledger['incomplete']}=={a['id'] for a in result['incomplete_pairs']}
    counts=Counter();exact={};exposure={}
    for name,rows in ledger['scenarios'].items():
        scenario=v.SCENARIOS[name];fee=scenario['fee_bps']/10000;slip=scenario['slippage_bps']/10000
        assert {p['id'] for p in rows}=={p['id'] for p in pairs}-incomplete
        for row in rows:
            for side in ('treated','control'):
                leg=legs[row['id']+'/'+side];out=row[side];groups=direct[row['id']+'/'+side]['groups'];qty=1/leg['entry'];entry_cash=1-slip
                assert row['entry_ts']==leg['entry_ts'] and out['exit_ts']==direct[row['id']+'/'+side]['exit_ts'] and out['exit_reason']==direct[row['id']+'/'+side]['exit_reason']
                close(out['hold_hours'],(out['exit_ts']-leg['entry_ts'])/3600);close(out['qty'],qty)
                expected_fills=[('SELL',leg['entry_ts']*1000,leg['entry'],qty)]+[('BUY',a['timestamp_ms'],a['reference_price'],qty*a['fraction']) for a in groups]
                assert len(out['fills'])==len(expected_fills);fee_sum=0.;slip_sum=0.;buy=0.
                for actual,(direction,t,reference,q) in zip(out['fills'],expected_fills):
                    execution=reference*(1-slip if direction=='SELL' else 1+slip);notional=execution*q;cost=reference*q*slip
                    assert actual['side']==direction and actual['timestamp_ms']==t
                    close([actual['reference_price'],actual['execution_price'],actual['qty'],actual['notional'],actual['fee'],actual['slippage_cost']],[reference,execution,q,notional,notional*fee,cost])
                    fee_sum+=notional*fee;slip_sum+=cost
                    if direction=='BUY':buy+=notional
                    counts['scenario_fill_groups']+=1
                frame=fund[leg['symbol']];events=frame.loc[(frame.funding_ts_ms>leg['entry_ts']*1000)&(frame.funding_ts_ms<=out['exit_ts']*1000)];assert len(events)==len(out['funding_events']);fc=0.;proxy=0
                for actual,source in zip(out['funding_events'],events.to_dict('records')):
                    assert all(actual[k]==a for k,a in source.items());remaining=qty*(1-sum(a['fraction'] for a in groups if a['timestamp_ms']<source['funding_ts_ms']))
                    cash=remaining*source['mark_price']*source['funding_rate'];close(actual['remaining_qty'],remaining);close(actual['cashflow'],cash);fc+=cash
                    counts['scenario_funding_payments']+=1
                    if source['price_source']!='funding_api_settlement_mark':
                        proxy+=1;counts['scenario_proxy_payments']+=1
                        if source['funding_rate']!=0:exact[(leg['symbol'],source['funding_ts_ms'])]={'symbol':leg['symbol'],**source}
                assert proxy==out['proxy_payments'];gross=1-sum(a['fraction']*a['reference_price']*qty for a in groups)
                close([out['gross_reference_return'],out['fees'],out['slippage'],out['funding'],out['net_return']],[gross,fee_sum,slip_sum,fc,entry_cash-buy-fee_sum+fc]);counts['scenario_leg_outcomes']+=1
                assert abs(sum(a['fraction'] for a in groups)-1)<1e-10
        for period,(start,end) in v.SPLITS.items():
            statistics.independent_statistics(rows,start,end,result['results'][name]['splits'][period]);counts['independent_bootstrap_periods']+=1
        for year,a in result['results'][name]['annual'].items():statistics.independent_statistics(rows,f'{year}-01-01',f'{int(year)+1}-01-01',a);counts['independent_bootstrap_periods']+=1
    primary=[a['splits']['retrospective_oos_2024_2025'] for a in result['results'].values()]
    support=not incomplete and not result['quality_issues'] and all(a.get('pairs',0)>=200 and a['paired_difference_ci95_bps'][0]>0 for a in primary);assert support==result['incremental_diagnostic_support']
    root=ET.parse(ART/'TESTS.xml').getroot();suites=list(root.iter('testsuite'));tests={k:sum(int(a.get(k,0)) for a in suites) for k in ('tests','errors','failures','skipped')};assert tests['tests']>=10 and tests['errors']==tests['failures']==tests['skipped']==0
    old=r.read(v.PRIOR/'CHECKPOINT.json')
    for p,h in old['files'].items():assert r.sha(v.PRIOR/p)==h,p
    for p,h in old['additional_sources'].items():assert r.sha(v.ROOT/p)==h,p
    r.save(ART/'EXACT_MARK_DATA_REQUEST.json',{'unique_events':len(exact),'events':list(exact.values()),'purchase_authorized':False})
    out={'all_passed':True,**dict(counts),'tests':tests,'previous_files_preserved':len(old['files']),'input_verification_sha256':r.sha(ART/'INPUT_VERIFICATION.json'),
        'results_sha256':r.sha(ART/'RESULTS.json'),'exact_mark_unique_events_needed':len(exact),'goal_complete':False,'live_signoff':'NOT_GRANTED'}
    r.save(ART/'INDEPENDENT_VERIFICATION.json',out);print(out,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['inputs','results']);{'inputs':inputs,'results':results}[p.parse_args().action]()
