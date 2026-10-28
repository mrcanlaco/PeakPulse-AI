"""Versioned supplement: separate ten officially delisted/relaunched contracts.

This is a scoped data-identity correction, not a complete exchange lifecycle
calendar or an executable portfolio. The frozen legacy collector is untouched.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import shutil
import numpy as np
import pandas as pd
import lifecycle_research_v414 as v
import universe_audit_v413 as u
import verify_universe_v413 as independent

r=v.r; OUT=v.ART/'contract_episodes'
URL='https://www.binance.com/en/support/announcement/detail/'


def records():
    # Facts transcribed from Binance announcements; no returns were consulted.
    rows=[
        ('CTKUSDT','2024-03-25','2024-04-01 08:30','2024-04-01 09:00','2025-04-30 10:15','ce74360a3fd444b2b35da7186f8dd0ad','63155163bce541f5856d416efa71c6e8','Shentu','Shentu','relaunch'),
        ('CVCUSDT','2022-11-28',None,'2022-11-29 09:00','2025-05-16 08:30','3188e26f14a1464b91487abad452c04f','bbe829426ad844b9b9dac62f878d1e67','Civic','Civic','relaunch'),
        ('CVXUSDT','2024-05-06','2024-05-14 08:30','2024-05-14 09:00','2025-07-23 11:30','a58cc13f78a34fbba11f00ff7144e9ee','b7b3a116013145569a9850f197c8cbe4','Convex Finance','Convex Finance','relaunch'),
        ('SLPUSDT','2024-05-08','2024-05-15 08:30','2024-05-15 09:00','2025-07-23 11:45','cb525a5fbb954935afc77630fc5bd0cc','b7b3a116013145569a9850f197c8cbe4','Smooth Love Potion','Smooth Love Potion','relaunch'),
        ('AERGOUSDT','2025-03-21','2025-03-27 08:30','2025-03-27 09:00','2025-04-16 11:00','db7ad1c7aa6248cda735102cdcdc4b8d','82f730b7ef444a38b323ab7a2e56b757','Aergo','Aergo','relaunch'),
        ('MAVIAUSDT','2024-12-06','2024-12-16 08:30','2024-12-16 09:00','2025-03-26 17:00','27eac260521b4f40ab331e1a345887a7','864b8bd112a44a8cae14db4dcea159a1','Heroes of Mavia','Heroes of Mavia','relaunch_postponed'),
        ('TLMUSDT','2022-06-02',None,'2022-06-09 09:00','2023-03-30 12:30','af469aeeab074738bb4a276070a9d11b','bd18df283ead40d09fd60c8eab984e41','Alien Worlds','Alien Worlds','relaunch'),
        ('BNXUSDT','2023-02-10','2023-02-10 14:00','2023-02-11 04:00','2023-02-22 14:45','4d23ada51a2e4fa182835c77d51ba1a9','940d0e48493e4627889c3f46371df70b','BinaryX before token split','BinaryX after token split','redenomination_relaunch'),
        ('PUMPUSDT','2025-06-10','2025-06-13 08:30','2025-06-13 09:00','2025-07-10 07:30','38a74ee47cdc43ebbc672e1dc6968358','4bc8b483d10d4619babb2015066b2d89','PumpBTC','Pump.fun','ticker_reused_for_different_asset'),
        ('LITUSDT','2025-01-22','2025-01-31 08:30','2025-01-31 09:00','2025-12-23 17:30','2a9feaa556f74dcdaa2192366f0e247c','6a33be00231c4539b3a4a625538e4d1e','Litentry','Lighter Protocol','ticker_reused_for_different_asset'),
    ]
    events=[]
    for s,p,c,d,a,old,new,under_old,under_new,kind in rows:
        events.append({'symbol':s,'publication_date':p,'known_from_utc':(r.utc(p)+pd.Timedelta(days=1)).isoformat(),
            'close_only_from':r.utc(c).isoformat() if c else None,'settlement_at':r.utc(d).isoformat(),'relaunch_at':r.utc(a).isoformat(),
            'old_underlying':under_old,'new_underlying':under_new,'kind':kind,'settlement_source':URL+old,'launch_source':URL+new})
    return events


def split_observed(frame,event):
    """Preserve original prices; exclude confirmed inactive interval, reset state."""
    settle=r.utc(event['settlement_at']);launch=r.utc(event['relaunch_at'])
    if settle>=launch:raise ValueError('Lifecycle times out of order')
    if frame.index.min()<v.START or frame.index.max()>=v.END:raise ValueError('Forbidden observations')
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing:raise ValueError('Unsorted/duplicate bars')
    return [('old',frame.loc[frame.index<settle].copy()),('relaunched',frame.loc[frame.index>=launch].copy())]


def episode_monthly(frame,event):
    result={};s=event['symbol'];settle=r.utc(event['settlement_at']);launch=r.utc(event['relaunch_at'])
    cutoff=r.utc(event['close_only_from']) if event['close_only_from'] else settle
    for phase,part in split_observed(frame,event):
        if part.empty:continue
        rows=r.monthly_rows(s,r.h1_frame(part),u.MONTHS)
        for month,row in rows.items():
            t=r.utc(month+'-01')
            if phase=='old' and t<cutoff or phase=='relaunched' and t>=launch:
                assert month not in result
                result[month]=row
    return result


def candidate_state(c,event):
    entry=c['entry_ts'];exit=c['paths']['ladder']['exit_ts']
    settle=int(r.utc(event['settlement_at']).timestamp());launch=int(r.utc(event['relaunch_at']).timestamp())
    known=int(r.utc(event['known_from_utc']).timestamp())
    cutoff=int(r.utc(event['close_only_from']).timestamp()) if event['close_only_from'] else settle
    return {'phase':'old' if entry<settle else 'inactive' if entry<launch else 'relaunched',
        'entry_blocked_by_known_event':known<=entry and cutoff<=entry<launch,
        'crosses_known_automatic_settlement':known<=settle and entry<settle<=exit,
        'requires_indicator_reset_comparison':entry>=launch}


def register():
    v.verify_sources()
    if (OUT/'PROTOCOL.json').exists():raise FileExistsError('Episode supplement already frozen')
    OUT.mkdir(parents=True,exist_ok=True)
    r.save(OUT/'EVENTS.json',{'events':records(),'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'Only the ten internal-gap symbols. All supplied events precede2026. Other lifecycle events remain to be certified.',
        'limitations':['Current article snapshots can include later edits; only explicitly dated contract identity/settlement/launch facts are used.',
            'Publication date plus one midnight UTC is a conservative known-from date for old-contract entry cutoffs.',
            'New observed trading starts a new identity at the official launch, regardless of later article edits.',
            'No assumption that the relaunched contract survives to2025-end; later delistings still require their own records.',
            'BNX old-contract REST alias BNXUSDTSETTLED; no token split ratio is used to splice perpetual prices.',
            'PUMP.fun starts as pre-market. Conversion and funding-rule changes need separate accounting before portfolio outcomes.',
            'MAVIA relaunch uses the postponed17:00 time, not the superseded16:15 time.']})
    sources=[Path(__file__),v.ROOT/'tests/unit/fibo_short/test_contract_episodes_v414.py']
    for p in sources:
        dest=OUT/'source_snapshot'/p.name;dest.parent.mkdir(exist_ok=True);shutil.copy2(p,dest)
    r.save(OUT/'PROTOCOL.json',{'registered_at_utc':datetime.now(timezone.utc).isoformat(),
        'sources':{str(p.relative_to(v.ROOT)):r.sha(p) for p in sources},'events_sha256':r.sha(OUT/'EVENTS.json'),
        'parent_source_manifest_sha256':r.sha(v.ART/'SOURCE_MANIFEST.json'),
        'union_data_manifest_sha256':r.sha(v.UNION/'DATA_MANIFEST.json'),
        'primary_correction':'Separate old and relaunched instrument histories; never pass pre-settlement bars or inactive placeholders into new indicators/ranking.',
        'rank_policy':'Original63day/50active-day/3.2percent wick/top50 rules unchanged; only known contract-episode boundaries and active-at-month-start eligibility change.',
        'diagnostic_only':True,'expanded_nav_allowed':False,'fresh_oos':False,'goal_complete':False})


def verify_sources():
    v.verify_sources();m=r.read(OUT/'PROTOCOL.json')
    for p,h in m['sources'].items():assert r.sha(v.ROOT/p)==h,p
    assert m['events_sha256']==r.sha(OUT/'EVENTS.json')
    assert m['parent_source_manifest_sha256']==r.sha(v.ART/'SOURCE_MANIFEST.json')
    assert m['union_data_manifest_sha256']==r.sha(v.UNION/'DATA_MANIFEST.json')


def run():
    verify_sources();events=r.read(OUT/'EVENTS.json')['events'];manifest=r.read(v.UNION/'DATA_MANIFEST.json')
    initial=r.read(v.PRIOR/'history/DATA_MANIFEST.json');monthly={}
    for s,a in initial['symbol_audit_sha256'].items():
        p=v.PRIOR/'symbol_audits'/f'{s}.json';assert r.sha(p)==a;monthly[s]=r.read(p)['monthly_rows']
    corrected=dict(monthly);details=[];prices={}
    for event in events:
        s=event['symbol'];item=manifest['inputs'][s];p=Path(item['path']);assert r.sha(p)==item['sha256'];frame=pd.read_parquet(p);prices[s]=frame
        monthly[s]=r.monthly_rows(s,r.h1_frame(frame),u.MONTHS)
        actual=episode_monthly(frame,event);expected={}
        cutoff=r.utc(event['close_only_from'] or event['settlement_at']);settle=r.utc(event['settlement_at']);launch=r.utc(event['relaunch_at'])
        # Independent implementation: source-row slice + raw5m grouped H1/H4.
        for lo,hi,eligible_lo,eligible_hi in [(v.START,settle,v.START,cutoff),(launch,v.END,launch,v.END)]:
            part=frame.loc[(frame.index>=lo)&(frame.index<hi)].reset_index()
            direct=independent.independent_monthly(s,part)
            expected.update({m:a for m,a in direct.items() if eligible_lo<=r.utc(m+'-01')<eligible_hi})
        independent.check_row(actual,expected);corrected[s]=actual
        inactive=frame.loc[(frame.index>=settle)&(frame.index<launch)]
        seconds=r.epoch_seconds(frame.index);gaps=np.flatnonzero(np.diff(seconds)>300);gap_rows=[]
        for i in gaps:
            begin=pd.Timestamp(seconds[i]+300,unit='s',tz='UTC');end=pd.Timestamp(seconds[i+1],unit='s',tz='UTC')
            inside=settle<=begin<end<=launch
            assert inside and end==launch,(s,begin,end)
            gap_rows.append({'first_missing_open':begin.isoformat(),'end_exclusive':end.isoformat(),'missing_cells':int((end-begin).total_seconds()/300),'inside_confirmed_inactive_interval':inside,'next_observed_open_equals_official_launch':end==launch})
        views=[]
        for phase,part in split_observed(frame,event):
            dest=OUT/'episode_bars'/f'{s}__{phase}.parquet';dest.parent.mkdir(exist_ok=True);part.to_parquet(dest)
            ref=frame.loc[frame.index<settle] if phase=='old' else frame.loc[frame.index>=launch]
            pd.testing.assert_frame_equal(pd.read_parquet(dest),ref,check_exact=True)
            views.append({'phase':phase,'path':str(dest),'sha256':r.sha(dest),'rows':len(part),'first_open':part.index.min().isoformat(),'last_open':part.index.max().isoformat()})
        details.append({'symbol':s,'kind':event['kind'],'old_underlying':event['old_underlying'],'new_underlying':event['new_underlying'],
            'settlement_at':event['settlement_at'],'relaunch_at':event['relaunch_at'],'source_sha256':item['sha256'],
            'inactive_observed_rows':len(inactive),'inactive_positive_volume_rows':int(inactive.volume.gt(0).sum()),
            'inactive_positive_volume_timestamps':[t.isoformat() for t in inactive.index[inactive.volume.gt(0)]],
            'gaps':gap_rows,'episode_views':views,'legacy_monthly_rows':monthly[s],'corrected_monthly_rows':actual})
    assert set(monthly)==set(manifest['inputs'])
    old=u.rank(monthly.values());assert old==r.read(v.UNION/'MEMBERSHIP.json')
    new=u.rank(corrected.values());r.save(OUT/'MEMBERSHIP.json',new)
    delta={m:{'added':sorted({a['symbol'] for a in new[m]}-{a['symbol'] for a in old[m]}),
              'removed':sorted({a['symbol'] for a in old[m]}-{a['symbol'] for a in new[m]})} for m in old}
    r.save(OUT/'RESULTS.json',{'symbols':details,'membership_delta':delta,'summary':{
        'source_symbols':len(monthly),'corrected_symbols':len(details),'episode_views':sum(len(a['episode_views']) for a in details),
        'gaps_explained_by_inactive_lifecycle':sum(len(a['gaps']) for a in details),
        'missing_cells_inside_inactive_intervals':sum(g['missing_cells'] for a in details for g in a['gaps']),
        'months_changed':sum(bool(a['added'] or a['removed']) for a in delta.values()),
        'member_slots_before':sum(map(len,old.values())),'member_slots_after':sum(map(len,new.values())),
        'inactive_observed_rows':sum(a['inactive_observed_rows'] for a in details),
        'inactive_positive_volume_rows':sum(a['inactive_positive_volume_rows'] for a in details)},
        'baseline_monthly_membership_exact':True,'independent_monthly_calculations_passed':True,
        'episode_price_readback_exact':True,'protocol_sha256':r.sha(OUT/'PROTOCOL.json'),
        'corrected_membership_sha256':r.sha(OUT/'MEMBERSHIP.json'),'post_2025_observations_loaded':0,
        'expanded_nav_allowed':False,'fresh_oos':False,'goal_complete':False})
    print(r.read(OUT/'RESULTS.json')['summary'],flush=True)


def candidate_audit():
    verify_sources();source=v.ART/'expanded/history';manifest=r.read(source/'CANDIDATE_MANIFEST.json');events=r.read(OUT/'EVENTS.json')['events'];new=r.read(OUT/'MEMBERSHIP.json')
    details=[]
    for event in events:
        s=event['symbol'];item=manifest['symbols'].get(s)
        if not item:continue
        p=source/'candidates'/f'{s}.pkl.gz';assert r.sha(p)==item['sha256']
        for c in v.load_rows(p):
            state=candidate_state(c,event);month=pd.Timestamp(c['entry_ts'],unit='s',tz='UTC').strftime('%Y-%m')
            details.append({'id':c['id'],'symbol':s,'entry_ts':c['entry_ts'],**state,
                'primary_elite_annual_eligible':r.passes(c,'elite_sniper') and v.annual_eligible(c),
                'absent_from_corrected_monthly_membership':s not in {a['symbol'] for a in new[month]}})
    def counts(rows):
        return {'candidates':len(rows),**{k:sum(bool(a[k]) for a in rows) for k in ['entry_blocked_by_known_event','crosses_known_automatic_settlement','requires_indicator_reset_comparison','absent_from_corrected_monthly_membership']}}
    r.save(OUT/'CANDIDATE_IMPACT.json',{'all':counts(details),'primary':counts([a for a in details if a['primary_elite_annual_eligible']]),'records':details,
        'qualification':'Legacy candidates diagnosed only; corrected indicators and full monthly membership must be recollected. No candidate removed by future path outcome.',
        'candidate_manifest_sha256':r.sha(source/'CANDIDATE_MANIFEST.json'),'episode_results_sha256':r.sha(OUT/'RESULTS.json'),'economic_results_evaluated':False})
    print({'all':counts(details),'primary':counts([a for a in details if a['primary_elite_annual_eligible']])},flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['register','run','candidates']);args=parser.parse_args()
    {'register':register,'run':run,'candidates':candidate_audit}[args.action]()
