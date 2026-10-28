"""Retain zero-volume observations separately from fills and lifecycle claims."""
from collections import Counter
import pandas as pd
import lifecycle_research_v414 as v

r=v.r


def main():
    v.verify_sources();audit=r.read(v.ART/'LIFECYCLE_CANDIDATE_AUDIT.json');folder=v.ART/'expanded/history'
    manifest=r.read(folder/'CANDIDATE_MANIFEST.json');data=r.read(folder/'DATA_MANIFEST.json');records=[];unique=set();primary_unique=set()
    for s in sorted({a['symbol'] for a in audit['flags']}):
        price=folder/'bars_5m'/f'{s}.parquet';cache=folder/'candidates'/f'{s}.pkl.gz'
        assert r.sha(price)==data['inputs'][s]['sha256'] and r.sha(cache)==manifest['symbols'][s]['sha256']
        frame=pd.read_parquet(price);candidates={c['id']:c for c in v.load_rows(cache)}
        for flag in [a for a in audit['flags'] if a['symbol']==s]:
            c=candidates[flag['id']];start=pd.Timestamp(c['entry_ts'],unit='s',tz='UTC');end=pd.Timestamp(c['paths']['ladder']['exit_ts'],unit='s',tz='UTC')
            part=frame.loc[(frame.index>=start)&(frame.index<end)&frame.volume.eq(0)]
            assert len(part)==flag['zero_volume_path_bars']
            flat=part[['open','high','low','close']].nunique(axis=1).eq(1)
            keys={(s,t.isoformat()) for t in part.index};unique.update(keys)
            if flag['primary_elite_annual_eligible']:primary_unique.update(keys)
            records.append({'id':c['id'],'symbol':s,'primary':flag['primary_elite_annual_eligible'],'zero_bar_opens':[t.isoformat() for t in part.index],
                'flat_ohlc_zero_bars':int(flat.sum()),'zero_bars':len(part),'zero_volume_exit_groups':flag['zero_volume_exit_groups']})
    result={'records':records,'summary':{'flagged_candidates':len(records),'candidate_zero_bar_observations':sum(a['zero_bars'] for a in records),
        'nonflat_zero_bar_observations':sum(a['zero_bars']-a['flat_ohlc_zero_bars'] for a in records),'unique_symbol_time_zero_bars':len(unique),
        'primary_unique_symbol_time_zero_bars':len(primary_unique),'primary_unique_zero_bars_by_date':dict(sorted(Counter(t[:10] for s,t in primary_unique).items()))},
        'qualification':'Descriptive only. Flat OHLC with zero volume neither proves executable liquidity nor proves an outage. Do not infer settlement marks or drop losing future paths.',
        'source_sha256':r.sha(__file__),'candidate_audit_sha256':r.sha(v.ART/'LIFECYCLE_CANDIDATE_AUDIT.json'),'economic_results_evaluated':False}
    r.save(v.ART/'ZERO_VOLUME_DIAGNOSTIC.json',result);print(result['summary'],flush=True)


if __name__=='__main__':main()
