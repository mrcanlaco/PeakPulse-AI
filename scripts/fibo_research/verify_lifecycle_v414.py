"""Independent timestamp-grid and event-boundary verification, no portfolio outcomes."""
from collections import Counter
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import lifecycle_research_v414 as v

r=v.r;ART=v.ART


def independent_quality(c,frame,events,positive_index=None):
    entry=pd.Timestamp(c['entry_ts'],unit='s',tz='UTC');path=c['paths']['ladder'];exit=pd.Timestamp(path['exit_ts'],unit='s',tz='UTC')
    active=frame.loc[entry:exit-pd.Timedelta(nanoseconds=1)]
    expected=pd.date_range(entry,exit,freq='5min',inclusive='left');missing=int((frame.index.get_indexer(expected)<0).sum())
    zero_exits=[]
    for row in path['trace']:
        if row[2]-row[3]>1e-10:
            opened=pd.Timestamp(row[0]-300,unit='s',tz='UTC')
            if frame.at[opened,'volume']==0:zero_exits.append(int(row[0]))
    if positive_index is None:positive_index=frame.index[frame.volume>0]
    i=positive_index.searchsorted(entry,side='left')-1
    last=positive_index[i] if i>=0 else None;nominal=entry+pd.Timedelta(hours=72 if c['tf']=='4h' else 120)
    flags=[]
    for event in events:
        if event['symbol']!=c['symbol']:continue
        known=pd.Timestamp(event['known_from_utc']);settle=pd.Timestamp(event['settlement_at']);close=pd.Timestamp(event['entry_close_only_from']) if event['entry_close_only_from'] else None
        if known<=entry and (entry>=settle or close is not None and entry>=close):
            flags.append({'kind':'entry_after_announced_new_position_cutoff','settlement_at':int(settle.timestamp()),'close_only_from':int(close.timestamp()) if close is not None else None,'source_url':event['source_url']})
        if known<=settle and entry<settle<=exit:flags.append({'kind':'position_path_crosses_automatic_settlement','settlement_at':int(settle.timestamp()),'source_url':event['source_url']})
    return {'entry_zero_volume':bool(frame.at[entry,'volume']==0),'zero_volume_path_bars':int(active.volume.eq(0).sum()),'zero_volume_exit_groups':zero_exits,
        'missing_bars_through_modelled_exit':missing,'horizon_truncated':path['exit_reason']=='horizon' and exit<nominal,
        'nominal_horizon_end':int(nominal.timestamp()),'modelled_exit':int(exit.timestamp()),
        'last_positive_volume_bar_before_entry':int(last.timestamp()) if last is not None else None,
        'hours_since_last_positive_volume_bar_close':(entry-last-pd.Timedelta(minutes=5)).total_seconds()/3600 if last is not None else None,
        'official_lifecycle_flags':flags}


def main():
    v.verify_sources();baseline=r.read(ART/'BASELINE_RECONCILIATION.json');assert baseline['all_passed']
    saved=r.read(ART/'LIFECYCLE_CANDIDATE_AUDIT.json');folder=ART/'expanded/history';manifest=r.read(folder/'CANDIDATE_MANIFEST.json')
    assert saved['candidate_manifest_sha256']==r.sha(folder/'CANDIDATE_MANIFEST.json')
    assert saved['source_manifest_sha256']==r.sha(ART/'SOURCE_MANIFEST.json')
    events=r.read(ART/'OFFICIAL_LIFECYCLE_EVENTS.json')['events'];flags={a['id']:a for a in saved['flags']};elite_flags={a['id']:a for a in saved['primary_flags']}
    assert len(flags)==len(saved['flags']) and len(elite_flags)==len(saved['primary_flags'])
    count=0;elite=0;years=Counter();seen=set();seen_elite=set();ranges={};data=r.read(folder/'DATA_MANIFEST.json');members=r.read(folder/'MEMBERSHIP.json')
    for i,(symbol,item) in enumerate(sorted(manifest['symbols'].items()),1):
        path=folder/'candidates'/f'{symbol}.pkl.gz';assert r.sha(path)==item['sha256'];rows=v.load_rows(path)
        price=folder/'bars_5m'/f'{symbol}.parquet';assert r.sha(price)==data['inputs'][symbol]['sha256'];frame=pd.read_parquet(price)
        assert frame.index.min()>=v.START and frame.index.max()<v.END and frame.index.is_unique
        positive_index=frame.index[frame.volume>0]
        allowed={m for m,rr in members.items() if symbol in {a['symbol'] for a in rr}}
        for c in rows:
            count+=1;entry=pd.Timestamp(c['entry_ts'],unit='s',tz='UTC');decision=pd.Timestamp(c['decision_ts'],unit='s',tz='UTC')
            assert entry-decision==pd.Timedelta(minutes=5) and entry.strftime('%Y-%m') in allowed
            assert c['entry']==frame.at[entry,'open'] and c['stop']>c['entry']>c['targets'][0]>c['targets'][1]>c['targets'][2]>0
            assert 'm6_f4_expanded' in c['milestones'] and c['paths']['ladder']['exit_ts']<=int(v.END.timestamp())
            is_elite='m6_f4_elite_sniper' in c['milestones'] and entry<r.utc(f'{entry.year+1}-01-01')-pd.Timedelta(days=5)
            d=independent_quality(c,frame,events,positive_index)
            affected=d['entry_zero_volume'] or d['zero_volume_path_bars'] or d['missing_bars_through_modelled_exit'] or d['horizon_truncated'] or d['official_lifecycle_flags']
            record={'id':c['id'],'symbol':symbol,'tf':c['tf'],'entry_ts':c['entry_ts'],'primary_elite_annual_eligible':is_elite,**d}
            if affected:assert flags[c['id']]==record;seen.add(c['id'])
            else:assert c['id'] not in flags
            if is_elite:
                elite+=1;years[str(entry.year)]+=1
                if affected:assert elite_flags[c['id']]==record;seen_elite.add(c['id'])
                start=max(v.START,entry-pd.Timedelta(hours=16));end=min(v.END-pd.Timedelta(milliseconds=1),pd.Timestamp(d['modelled_exit'],unit='s',tz='UTC')+pd.Timedelta(hours=16))
                a=ranges.setdefault(symbol,{'start_ms':int(start.timestamp()*1000),'end_ms':int(end.timestamp()*1000)})
                a['start_ms']=min(a['start_ms'],int(start.timestamp()*1000));a['end_ms']=max(a['end_ms'],int(end.timestamp()*1000))
        if i%20==0:print(f'Independent candidate tradability checks {i}/{len(manifest["symbols"])}',flush=True)
    assert seen==set(flags) and seen_elite==set(elite_flags)
    assert count==saved['all_candidates'] and elite==saved['primary_elite_candidates'] and dict(sorted(years.items()))==saved['primary_candidates_by_year']
    assert ranges==r.read(ART/'FUNDING_REQUIREMENTS.json')['symbols']
    previous=r.read(v.PRIOR/'CHECKPOINT.json')
    for p,h in previous['files'].items():assert r.sha(v.PRIOR/p)==h,p
    for p,h in previous.get('additional_sources',{}).items():assert r.sha(v.ROOT/p)==h,p
    suites=list(ET.parse(ART/'TESTS.xml').getroot().iter('testsuite'));tests={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','errors','failures','skipped')}
    assert tests['tests']>=9 and tests['errors']==tests['failures']==tests['skipped']==0
    r.save(ART/'INDEPENDENT_VERIFICATION.json',{'all_passed':True,'expanded_candidates_independently_checked':count,'primary_candidates_checked':elite,
        'flags_independently_confirmed':len(flags),'primary_flags_confirmed':len(elite_flags),'baseline_candidates_exact':baseline['candidates_exactly_equal'],
        'previous_v413_files_preserved':len(previous['files']),'tests':tests,'candidate_audit_sha256':r.sha(ART/'LIFECYCLE_CANDIDATE_AUDIT.json'),
        'post_2025_observations_loaded':0,'economic_results_evaluated':False,'fresh_oos':False,'goal_complete':False})
    print(r.read(ART/'INDEPENDENT_VERIFICATION.json'),flush=True)


if __name__=='__main__':main()
