"""Frozen full-universe evaluation under the original coupled portfolio policy."""
from datetime import datetime,timezone
from pathlib import Path
import argparse
import gzip
import json
import pickle
import shutil
import numpy as np
import pandas as pd
import research_v415 as v
import research_v412 as statistics
import research_v409 as original

r=v.r;ART=v.ART;x=v.v.x;SCENARIOS=x.SCENARIOS


def register():
    v.verify_sources()
    if (ART/'ECONOMIC_PROTOCOL.json').exists():raise FileExistsError('Economic protocol frozen')
    sources=[Path(__file__),Path(statistics.__file__),Path(original.__file__),Path(x.__file__)]
    for p in sources:
        dest=ART/'economic_source_snapshot'/p.name;dest.parent.mkdir(exist_ok=True);shutil.copy2(p,dest)
    r.save(ART/'ECONOMIC_PROTOCOL.json',{'registered_at_utc':datetime.now(timezone.utc).isoformat(),'sources':{str(p.relative_to(v.ROOT)):r.sha(p) for p in sources},
        'parent_protocol_sha256':r.sha(ART/'PROTOCOL.json'),'original_results_sha256':r.sha(original.ART/'RESULTS.json'),
        'old_baseline_reconciliation_sha256':r.sha(statistics.ART/'BASELINE_RECONCILIATION.json'),
        'policy':'Exactly frozen elite_sniper risk sizing and original50/30/20 exits. No new gate or selection among winners.',
        'splits':{'development_context_2020_2023':[2020,2021,2022,2023],'retrospective_oos_2024_2025':[2024,2025],'all_2020_2025':list(range(2020,2026))},
        'inference':'Common Monday calendar plus partial boundary weeks; four-week circular block bootstrap10000 draws seed412.95percent absolute weekly intervals;97.5percent paired old-vs-expanded difference intervals per cost. Historical multiple testing not globally adjusted.',
        'admissibility':'Require zero primary execution-data/known-settlement issues and complete historical funding coverage before outcomes. Flat zero-volume holding bars remain qualified observed-last-price marks.',
        'funding':'Actual signed event rates. API mark when available; old mark1hOPEN proxies explicitly identified and tested with conservative funding-notional sensitivity.',
        'decision':'No live approval from a positive point estimate. Need credible OOS, stress profitability, uncertainty and execution evidence. Negative results retained.',
        'fresh_oos':False,'goal_complete':False})


def verify_sources():
    v.verify_sources();m=r.read(ART/'ECONOMIC_PROTOCOL.json')
    for p,h in m['sources'].items():assert r.sha(v.ROOT/p)==h,p
    assert m['parent_protocol_sha256']==r.sha(ART/'PROTOCOL.json')
    assert m['original_results_sha256']==r.sha(original.ART/'RESULTS.json')
    assert m['old_baseline_reconciliation_sha256']==r.sha(statistics.ART/'BASELINE_RECONCILIATION.json')


def load_candidates():
    audit=r.read(ART/'CANDIDATE_AUDIT.json')
    assert audit['candidate_manifest_sha256']==r.sha(ART/'CANDIDATE_MANIFEST.json')
    assert not audit['primary_execution_issues'],'Resolve primary execution data before economic results'
    assert not audit['primary_boundary_overlaps'],'Resolve candidate boundary overlaps before economics'
    assert not r.read(ART/'MEMBERSHIP_CORRECTION.json')['remaining_stale_member_months']
    with gzip.open(ART/'PRIMARY_CANDIDATES.pkl.gz','rb') as fh:rows=pickle.load(fh)
    assert len(rows)==audit['primary_candidates']
    return rows


def load_funding():
    manifest=r.read(ART/'funding/MANIFEST.json');assert manifest['all_passed'] and not manifest['errors']
    assert manifest['requirements_sha256']==r.sha(ART/'funding/REQUIREMENTS.json')
    out={}
    for s,a in manifest['symbols'].items():
        assert r.sha(a['path'])==a['sha256'];frame=pd.read_parquet(a['path']);stamps=frame.funding_ts_ms.to_numpy();need=a['requirements']
        assert v.funding.START_MS<=stamps[0]<=need['first_entry_ms']<=need['last_exit_ms']<=stamps[-1]<v.funding.LIMIT_MS
        assert np.all(np.diff(stamps)>0) and np.isfinite(frame[['funding_rate','mark_price']]).all().all() and (frame.mark_price>0).all()
        relevant=stamps[(stamps>=need['first_entry_ms']-8*3600000-15000)&(stamps<=need['last_exit_ms']+8*3600000+15000)]
        assert len(relevant)>1 and np.diff(relevant).max()<=8*3600000+15000,(s,'funding gap')
        out[s]={'times':stamps,'events':frame.to_dict('records')}
    return out


def fingerprint():
    return {k:r.sha(ART/p) for k,p in [('economic_protocol_sha256','ECONOMIC_PROTOCOL.json'),('candidate_manifest_sha256','CANDIDATE_MANIFEST.json'),
        ('primary_candidates_sha256','PRIMARY_CANDIDATES.pkl.gz'),('funding_manifest_sha256','funding/MANIFEST.json')]}


def ledger(year,scenario):
    with gzip.open(ART/'runs'/f'{year}_{scenario}.json.gz','rt',encoding='utf8') as fh:return json.load(fh)


def run_node(candidates,prepared,year,scenario,fund):
    folder=ART/'runs';folder.mkdir(exist_ok=True);key=f'{year}_{scenario}';receipt=folder/f'{key}.json';path=folder/f'{key}.json.gz';fp=fingerprint()
    if receipt.exists():
        a=r.read(receipt);assert all(a[k]==val for k,val in fp.items()) and a['ledger_sha256']==r.sha(path);return a['metric']
    result=x.portfolio(candidates,{'gate':'elite_sniper','sizing':'risk'},f'{year}-01-01',f'{year+1}-01-01',SCENARIOS[scenario],fund,prepared)
    detail={'ledger':result.pop('ledger'),'curve':result.pop('curve')};result['curve_values']=[p[1] for p in detail['curve']]
    with gzip.open(path,'wt',encoding='utf8') as fh:json.dump(detail,fh,separators=(',',':'),allow_nan=False)
    r.save(receipt,{'metric':result,'ledger_sha256':r.sha(path),**fp})
    print(f'Expanded {year}/{scenario}: {result["return_pct"]:+.3f}%, DD {result["max_dd_pct"]:.3f}%, N={result["trades"]}',flush=True)
    return result


def linked_curve(years,scenario,baseline=False):
    points=[];cash=100.
    for year in years:
        if baseline:
            with gzip.open(original.ART/f'YEAR_{year}_LEDGERS.json.gz','rt',encoding='utf8') as fh:detail=json.load(fh)[f'{year}/elite_sniper_risk/{scenario}']
        else:detail=ledger(year,scenario)
        curve=np.asarray(detail['curve']);points.extend((int(t),float(value*cash/100)) for t,value in curve);cash*=curve[-1,1]/100
    return pd.Series([p[1] for p in points],index=pd.to_datetime([p[0] for p in points],unit='ms',utc=True)).groupby(level=0).last().sort_index()


def evaluate():
    verify_sources()
    if (ART/'RESULTS.json').exists():raise FileExistsError('Results already frozen')
    assert r.read(ART/'INPUT_VERIFICATION.json')['all_passed']
    candidates=load_candidates();fund=load_funding();prepared={c['id']:x.execution_steps(c) for c in candidates}
    annual={str(y):{scenario:run_node(candidates,prepared,y,scenario,fund) for scenario in SCENARIOS} for y in range(2020,2026)}
    prior=r.read(original.ART/'RESULTS.json');baseline={str(y):prior['annual'][str(y)]['elite_sniper_risk'] for y in range(2020,2026)}
    periods={};compare={};split=r.read(ART/'ECONOMIC_PROTOCOL.json')['splits']
    for name,years in split.items():
        periods[name]={};compare[name]={}
        for scenario in SCENARIOS:
            a=original.linked([annual[str(y)] for y in years],scenario);b=original.linked([baseline[str(y)] for y in years],scenario)
            ca,ga=statistics.calendar_returns(linked_curve(years,scenario),f'{years[0]}-01-01',f'{years[-1]+1}-01-01')
            cb,gb=statistics.calendar_returns(linked_curve(years,scenario,True),f'{years[0]}-01-01',f'{years[-1]+1}-01-01');assert ga==gb
            a['calendar_weekly_ci95']=statistics.interval(ca);b['calendar_weekly_ci95']=statistics.interval(cb)
            periods[name][scenario]={'corrected_expanded':a,'old_snapshot':b}
            compare[name][scenario]={'expanded_minus_old':statistics.interval(ca-cb,alpha=.025)}
    r.save(ART/'RESULTS.json',{'version':'4.0.15','annual':annual,'periods':periods,'paired_comparisons':compare,
        'scenarios':SCENARIOS,'historical_reuse_disclosed':True,'fresh_oos':False,'post_2025_observations':0,'goal_complete':False,'live_signoff':'NOT_GRANTED',**fingerprint()})
    print(json.dumps({'primary':periods['retrospective_oos_2024_2025'],'full':periods['all_2020_2025']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['register','evaluate']);a=p.parse_args()
    {'register':register,'evaluate':evaluate}[a.action]()
