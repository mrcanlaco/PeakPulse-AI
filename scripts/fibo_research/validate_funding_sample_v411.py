"""Free historical tick spot-check; never substitutes projected funding rates."""
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import pandas as pd
import requests
import research_v411 as v

r=v.r;OUT=v.ART/'funding_tick_spotcheck'


def main():
    OUT.mkdir(exist_ok=True)
    source=v.z.ART/'EXACT_MARK_DATA_REQUEST.json';data=r.read(source)
    rows=[e for values in data['events_by_symbol'].values() for e in values]
    selected=[]
    for year in range(2020,2026):
        options=[e for e in rows if pd.Timestamp(e['funding_ts_ms'],unit='ms',tz='UTC').year==year
            and pd.Timestamp(e['funding_ts_ms'],unit='ms',tz='UTC').day==1
            and pd.Timestamp(e['funding_ts_ms'],unit='ms',tz='UTC').hour>0]
        if options:selected.append(min(options,key=lambda e:(e['funding_ts_ms'],e['symbol'])))
    protocol={'source_request_sha256':r.sha(source),'selection':'Earliest needed funding event on day1, after00h, per calendar year2020..2025; symbol tie alphabetical. Selected before reading external ticks.',
        'events':selected,'source':'Tardis free first-day raw Binance markPrice stream; no API key or subscription',
        'cash_rate':'Keep official settled Binance REST rate; do NOT replace it with projected markPrice-stream r field.',
        'claims':'Spot-check only. Last markPrice event at or before settlement is an external observed mark, not certification of exact private settlement pricing. Does not change frozen strategy results.'}
    path=OUT/'PROTOCOL.json'
    if path.exists():assert r.read(path)==protocol
    else:r.save(path,protocol)
    results=[];session=requests.Session()
    for e in selected:
        ts=pd.Timestamp(e['funding_ts_ms'],unit='ms',tz='UTC');minutes=ts.hour*60+ts.minute
        marks=[];sources=[];errors=[]
        for offset in [minutes-1,minutes]:
            params={'from':ts.strftime('%Y-%m-%d'),'filters':json.dumps([{'channel':'markPrice','symbols':[e['symbol'].lower()]}],separators=(',',':')),'offset':offset}
            url='https://api.tardis.dev/v1/data-feeds/binance-futures'
            key=hashlib.sha256(json.dumps(params,sort_keys=True).encode()).hexdigest();raw=OUT/f'{key}.ndjson.gz'
            if raw.exists():
                with gzip.open(raw,'rt',encoding='utf8') as fh:body=fh.read()
            else:
                response=session.get(url,params=params,headers={'Accept-Encoding':'gzip'},timeout=30)
                if response.status_code!=200:
                    errors.append({'params':params,'status_code':response.status_code,'body_excerpt':response.text[:250]});continue
                body=response.text
                if len(body)>2_000_000:raise ValueError('Unexpected minute response size')
                with gzip.open(raw,'wt',encoding='utf8') as fh:fh.write(body)
                r.save(OUT/f'{key}.source.json',{'url':url,'params':params,'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'raw_sha256':r.sha(raw)})
            sources.append(str(raw.relative_to(v.ART)))
            for line in body.splitlines():
                if not line.strip():continue
                first=line.find('{')
                if first<0:raise ValueError('Unexpected raw line format')
                packet=json.loads(line[first:]);message=packet.get('data',packet)
                if message.get('e')!='markPriceUpdate':continue
                assert message['s']==e['symbol']
                event=int(message['E']);assert v.f.START_MS<=event<v.f.LIMIT_MS
                if event<=e['funding_ts_ms']:
                    marks.append({'event_ts_ms':event,'mark_price':float(message['p']),'local_timestamp':line[:first].strip()})
        eligible=[m for m in marks if e['funding_ts_ms']-m['event_ts_ms']<=5000]
        last=max(eligible,key=lambda m:m['event_ts_ms']) if eligible else None
        record={'requested':e,'source_files':sources,'errors':errors,'last_prior_tick':last,
            'status':'OBSERVED_PRIOR_MARK_TICK' if last else 'NO_ELIGIBLE_TICK','exact_settlement_price_certified':False}
        if last:
            record['tick_age_ms']=e['funding_ts_ms']-last['event_ts_ms']
            record['proxy_vs_tick_relative_difference_bps']=(e['current_proxy_mark']/last['mark_price']-1)*10000
        results.append(record)
        print(json.dumps({k:record[k] for k in ('requested','status','last_prior_tick','errors')}),flush=True)
    r.save(OUT/'RESULTS.json',{'protocol_sha256':r.sha(path),'samples':results,'certifies_all_required_events':False,
        'uses_post_2025_data':False,'backtest_inputs_changed':False,'purchase_made':False})


def verify():
    data=r.read(OUT/'RESULTS.json');protocol=r.read(OUT/'PROTOCOL.json')
    assert data['protocol_sha256']==r.sha(OUT/'PROTOCOL.json')
    assert [p['requested'] for p in data['samples']]==protocol['events']
    sources=0;recomputed=[]
    for sample in data['samples']:
        event=sample['requested'];ticks=[]
        for relative in sample['source_files']:
            path=v.ART/relative;meta=r.read(path.with_name(path.name.replace('.ndjson.gz','.source.json')))
            assert r.sha(path)==meta['raw_sha256'] and meta['url']=='https://api.tardis.dev/v1/data-feeds/binance-futures'
            date=pd.Timestamp(meta['params']['from'],tz='UTC')
            assert date.day==1 and 2020<=date.year<=2025
            with gzip.open(path,'rt',encoding='utf8') as fh:
                for line in fh:
                    if '{' not in line:continue
                    m=json.loads(line[line.index('{'):]).get('data',{})
                    if m.get('e')!='markPriceUpdate':continue
                    assert m['s']==event['symbol'] and v.f.START_MS<=m['E']<v.f.LIMIT_MS
                    if 0<=event['funding_ts_ms']-m['E']<=5000:ticks.append((m['E'],float(m['p'])))
            sources+=1
        if ticks:
            latest=max(t[0] for t in ticks);prices={p for t,p in ticks if t==latest};assert len(prices)==1
            price=next(iter(prices));reported=sample['last_prior_tick']
            assert reported['event_ts_ms']==latest and reported['mark_price']==price
            difference=(event['current_proxy_mark']/price-1)*10000
            assert abs(difference-sample['proxy_vs_tick_relative_difference_bps'])<1e-12
            recomputed.append(difference)
    result={'all_checks_passed':True,'samples_recomputed':len(recomputed),'raw_responses_verified':sources,
        'exactly_equal_proxy_and_tick':sum(d==0 for d in recomputed),'max_absolute_relative_difference_bps':max(map(abs,recomputed)),
        'certifies_all_required_events':False,'results_sha256':r.sha(OUT/'RESULTS.json')}
    r.save(OUT/'VERIFICATION.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    verify() if args.verify else main()
