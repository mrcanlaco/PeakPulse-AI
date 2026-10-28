"""Independent feature availability, matching, source and cash reconstruction."""
from collections import Counter,defaultdict
from pathlib import Path
import csv,gzip,io,json,zipfile
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import research_v416 as v
import verify_research_v411 as previous
r=v.r;ART=v.ART


def close(a,b,tol=1e-8):assert np.allclose(a,b,atol=tol,rtol=0),(a,b)


def inputs():
    v.verify_sources();record=r.read(ART/'MATCHES.json');features=pd.read_parquet(ART/'FEATURES.parquet')
    assert record['features_sha256']==r.sha(ART/'FEATURES.parquet') and record['protocol_sha256']==r.sha(ART/'PROTOCOL.json')
    candidates=v.load_candidates();elite=sorted((c for c in candidates if 'm6_f4_elite_sniper' in c['milestones']),key=lambda c:(c['entry_ts'],-c['score'],c['symbol'],c['tf']))
    sampled=[];rejected=Counter();waves=set();next_time={};year=None
    for c in elite:
        y=pd.Timestamp(c['entry_ts'],unit='s',tz='UTC').year
        if y!=year:year=y;waves=set();next_time={}
        if c['entry_ts']>=int(r.utc(f'{y+1}-01-01').timestamp())-432000:rejected['year_end_embargo']+=1;continue
        key=(c['symbol'],c['tf'],c['wave_key'])
        if key in waves or c['entry_ts']<next_time.get(c['symbol'],0):rejected['wave_or_24h_cooldown']+=1;continue
        waves.add(key);next_time[c['symbol']]=c['entry_ts']+86400;sampled.append(c)
    assert len(sampled)==record['sampled_events'] and dict(rejected)==record['sampling_rejections'] and len(elite)==record['raw_elite_candidates']
    decisions=np.array(sorted({c['decision_ts'] for c in sampled}));membership=r.read(v.PRIOR/'MEMBERSHIP.json');symbols={a['symbol'] for rr in membership.values() for a in rr};checked=0
    for s in sorted(symbols):
        bars=v.load_bars(s);stamps=r.epoch_seconds(bars.index);rows=features.loc[features.symbol==s];prices=bars.close.to_numpy()
        idx=np.searchsorted(stamps,decisions-300);valid=(idx>=288)&(idx<len(stamps));expected=[]
        for i,t in zip(idx[valid],decisions[valid]):
            if stamps[i]==t-300 and stamps[i]-stamps[i-288]==86400 and np.isfinite(prices[i-288:i+1]).all() and (prices[i-288:i+1]>0).all():expected.append(t)
        assert sorted(rows.decision_ts)==expected,(s,'Feature availability mismatch')
        indices=np.searchsorted(stamps,rows.decision_ts.to_numpy()-300);logs=np.log(prices);cum=np.cumsum(np.r_[0,np.diff(logs)**2])
        close(logs[indices]-logs[indices-288],rows.momentum);close(np.sqrt(np.maximum(0,cum[indices]-cum[indices-288])),rows.volatility);checked+=len(rows)
    lookup={(p.symbol,int(p.decision_ts)):p for p in features.itertuples()};active=defaultdict(set)
    for c in elite:active[c['decision_ts']].add(c['symbol'])
    events=r.read(v.PRIOR/'EVENTS.json')['events']
    def available(s,t):
        for e in events:
            if s!=e['symbol'] or t<r.utc(e['known_from_utc']).timestamp():continue
            if r.utc(e['entry_close_only_from'] or e['settlement_at']).timestamp()<=t and (not e.get('relaunch_at') or t<r.utc(e['relaunch_at']).timestamp()):return False
        return True
    out={p['id']:p for p in record['pairs']+record['unmatched']};assert len(out)==len(sampled);exclusions=[]
    for c in sampled:
        t=c['decision_ts'];a=out[c['id']];target=lookup.get((c['symbol'],t));assert available(c['symbol'],c['entry_ts'])
        for k in ('id','symbol','tf','wave_key','score','decision_ts','entry_ts'):assert a[k]==c[k]
        if target is None:assert a['reason']=='treated_past_feature_missing';continue
        month=pd.Timestamp(t,unit='s',tz='UTC').strftime('%Y-%m');pool=[]
        for p in membership[month]:
            s=p['symbol']
            if s==c['symbol'] or s in active[t] or (s,t) not in lookup or lookup[(s,t)].momentum<=0:continue
            if not available(s,c['entry_ts']):exclusions.append({'treated_id':c['id'],'symbol':s,'entry_ts':c['entry_ts']});continue
            pool.append(lookup[(s,t)])
        if target.momentum<=0:assert a['reason']=='treated_nonpositive_momentum';continue
        if len(pool)<3:assert a['reason']=='fewer_than_three_positive_controls';continue
        matrix=np.array([[p.momentum,p.volatility] for p in pool]);sd=matrix.std(axis=0)
        if np.any(sd<=1e-12):assert a['reason']=='degenerate_control_dispersion';continue
        diff=(matrix-np.array([target.momentum,target.volatility]))/sd
        options=sorted((float(np.dot(d,d)),p.symbol,i) for i,(d,p) in enumerate(zip(diff,pool)) if np.all(np.abs(d)<=.5))
        if not options:assert a['reason']=='outside_fixed_caliper';continue
        best=options[0];assert a['control']['symbol']==best[1] and a['control_pool_size']==len(pool)
        close(a['squared_distance'],best[0]);close(a['standardized_difference'],diff[best[2]]);close(a['feature_sd'],sd)
        assert a['entry_ts']==t+300 and a['exit_ts']==t+86700
    assert exclusions==record['known_lifecycle_control_exclusions']
    audit=r.read(ART/'PATH_AUDIT.json');assert audit['matches_sha256']==r.sha(ART/'MATCHES.json');path_count=0
    for s in sorted({p['symbol'] for p in audit['all_legs']}):
        bars=v.load_bars(s)
        for p in (p for p in audit['all_legs'] if p['symbol']==s):
            t=p['entry_ts'];selected=bars.loc[(bars.index>=pd.Timestamp(t,unit='s',tz='UTC'))&(bars.index<pd.Timestamp(t+86400,unit='s',tz='UTC'))]
            complete=len(selected)==288 and np.array_equal(r.epoch_seconds(selected.index),np.arange(t,t+86400,300));assert (p['status']=='COMPLETE')==complete
            if complete:
                close([p['entry_reference'],p['exit_reference']],[selected.iloc[0]['open'],selected.iloc[-1]['close']])
                assert p['zero_volume_entry']==bool(selected.iloc[0].volume<=0) and p['zero_volume_exit']==bool(selected.iloc[-1].volume<=0)
                assert p['zero_volume_holding_bars']==int((selected.volume<=0).sum())
                assert p['settlement_overlaps']==[e['settlement_at'] for e in events if e['symbol']==s and t<r.utc(e['settlement_at']).timestamp()<=t+86400]
            path_count+=1
    result={'past_feature_rows_recomputed':checked,'sampled_events_reconciled':len(sampled),'matches_reconciled':len(record['pairs']),'unique_paths_recomputed':path_count,'path_issues':len(audit['issues'])}
    r.save(ART/'MATCH_VERIFICATION.json',{'all_passed':True,**result,'matches_sha256':r.sha(ART/'MATCHES.json'),'path_audit_sha256':r.sha(ART/'PATH_AUDIT.json')});print(result,flush=True)
    return result


def funding():
    manifest=r.read(ART/'funding/MANIFEST.json');assert manifest['all_passed'] and not manifest['errors'];output={};raw_count=0;archive_count=0;counts=Counter()
    assert manifest['requirements_sha256']==r.sha(ART/'funding/REQUIREMENTS.json')
    for s,item in sorted(manifest['symbols'].items()):
        assert r.sha(item['path'])==item['sha256'];frame=pd.read_parquet(item['path']);record=item['record'];root=Path(item['path']).parents[2];n=item['requirements']
        assert frame.funding_ts_ms.is_unique and frame.funding_ts_ms.is_monotonic_increasing
        assert v.f.START_MS<=frame.funding_ts_ms.min()<=n['first_entry_ms']<=n['last_exit_ms']<=frame.funding_ts_ms.max()<v.f.LIMIT_MS
        rates={};marks={};archive_marks={}
        for relative,h in record['raw_responses'].items():
            path=root/relative;assert r.sha(path)==h
            with gzip.open(path,'rt',encoding='utf8') as fh:raw=json.load(fh)
            params=raw['params'];assert v.f.START_MS<=params['startTime']<=params['endTime']<v.f.LIMIT_MS and params['symbol']==s
            if raw['url']==v.f.FUNDING_URL:
                for a in raw['data']:assert a['symbol']==s and params['startTime']<=a['fundingTime']<=params['endTime'];rates[int(a['fundingTime'])]=a
            elif raw['url']==v.f.MARK_URL:
                assert params['interval']=='1h'
                for a in raw['data']:assert params['startTime']<=a[0]<=params['endTime'];marks[int(a[0])]=float(a[1])
            else:raise AssertionError('Unexpected endpoint')
            raw_count+=1
        for a in record.get('archive_sources',[]):
            path=Path(a['path']);checksum=Path(a['checksum_path']);assert r.sha(path)==a['sha256'] and r.sha(checksum)==a['checksum_sha256']
            digest,name=checksum.read_text(encoding='utf8').split();assert digest.lower()==r.sha(path) and name.lstrip('*')==path.name
            with zipfile.ZipFile(path) as z:
                assert z.namelist()==[path.stem+'.csv']
                with z.open(path.stem+'.csv') as fh:
                    for row in csv.reader(io.TextIOWrapper(fh,encoding='utf8')):
                        if row[0] in ('open_time','openTime'):continue
                        t=int(row[0]);assert v.f.START_MS<=t<v.f.LIMIT_MS and t%3600000==0;archive_marks[t]=float(row[1])
            archive_count+=1
        assert set(rates)==set(frame.funding_ts_ms)
        for p in frame.itertuples():
            a=rates[p.funding_ts_ms];close(p.funding_rate,float(a['fundingRate']))
            if p.price_source=='funding_api_settlement_mark':close(p.mark_price,float(a['markPrice']));assert p.mark_reference_ts_ms==p.funding_ts_ms
            else:
                assert not a.get('markPrice') or float(a['markPrice'])<=0
                assert 0<=p.funding_ts_ms-p.mark_reference_ts_ms<=15000
                lookup=archive_marks if p.price_source=='official_mark_archive_open_proxy' else marks;close(p.mark_price,lookup[p.mark_reference_ts_ms])
            counts[p.price_source]+=1
        output[s]=frame
    return output,{'funding_symbols':len(output),'funding_snapshot_events_verified':sum(counts.values()),'funding_price_sources':dict(counts),'raw_responses_verified':raw_count,'archives_verified':archive_count}


def main(action):
    if action=='inputs':inputs();return
    v.verify_sources();matchcheck=r.read(ART/'MATCH_VERIFICATION.json');assert matchcheck['all_passed'] and matchcheck['matches_sha256']==r.sha(ART/'MATCHES.json')
    funded,provenance=funding()
    # Reuse independently coded cash/formula verifier from v411; no original file changes.
    previous.v=v;previous.ART=ART;cash=previous.verify_outcomes(funded)
    root=ET.parse(ART/'TESTS.xml').getroot();suites=list(root.iter('testsuite'));tests={k:sum(int(a.get(k,0)) for a in suites) for k in ('tests','errors','failures','skipped')}
    assert tests['tests']>=8 and tests['errors']==tests['failures']==tests['skipped']==0
    prior=r.read(v.PRIOR/'CHECKPOINT.json')
    for p,h in prior['files'].items():assert r.sha(v.PRIOR/p)==h,p
    for p,h in prior['additional_sources'].items():assert r.sha(v.ROOT/p)==h,p
    result={'all_checks_passed':True,**matchcheck,**provenance,**cash,'tests':tests,'previous_files_preserved':len(prior['files']),
            'results_sha256':r.sha(ART/'RESULTS.json'),'post_2025_observations':0,'goal_complete':False,'live_signoff':'NOT_GRANTED'}
    r.save(ART/'INDEPENDENT_VERIFICATION.json',result);print(result,flush=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=['inputs','results']);main(p.parse_args().action)
