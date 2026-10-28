"""Predeclared fee/slippage frontier of the unchanged v415 portfolio."""
from datetime import datetime,timezone
from pathlib import Path
import argparse,gzip,json,shutil
import numpy as np
import pandas as pd
import evaluate_universe_resolved_v415 as source

b=source.base;r=b.r;x=b.x;ROOT=b.v.ROOT;PRIOR=ROOT/'artifacts/fibo_trend_short/research_v4_0_17';ART=ROOT/'artifacts/fibo_trend_short/research_v4_0_18'
SCENARIOS={f'{tier}_slip{slip}':{'fee_bps':fee,'slippage_bps':float(slip)} for tier,fee in [('vip6',2.5),('regular',5.)] for slip in (10,20,30,40,50)}
ENDPOINTS={'vip6_slip10':'standard_vip6','regular_slip50':'stress_regular'}
SPLITS={'development_context_2020_2023':list(range(2020,2024)),'retrospective_oos_2024_2025':[2024,2025],'all_2020_2025':list(range(2020,2026))}
load_candidates=source.load_candidates;load_funding=b.load_funding


def register():
    source.verify_sources()
    if (ART/'PROTOCOL.json').exists():raise FileExistsError('Already frozen')
    p=r.read(PRIOR/'NEXT_COST_FRONTIER_PROTOCOL.json');p.update(version='4.0.18',registered_at_utc=datetime.now(timezone.utc).isoformat(),scenarios=SCENARIOS,splits=SPLITS,
        source_hypothesis_sha256=r.sha(PRIOR/'NEXT_COST_FRONTIER_PROTOCOL.json'),
        qualification='Use every grid point, do not choose an execution setting as evidence of alpha. Bracket a sign change only between adjacent actually evaluated points. Cash-dependent admission may produce nonmonotone returns; do not interpolate.',
        uncertainty='Unadjusted95percent mean calendar-week return intervals,4week circular block bootstrap10000 seed412. Same v415 interval convention and annual state resets; no fresh holdout claims.')
    r.save(ART/'PROTOCOL.json',p)
    sources=[Path(__file__),ROOT/'scripts/fibo_research/verify_research_v418.py',ROOT/'tests/unit/fibo_short/test_research_v418.py',
        ROOT/'tests/unit/fibo_short/test_execution_v409.py',Path(source.__file__),Path(b.__file__),Path(b.statistics.__file__),Path(b.original.__file__),Path(x.__file__)]
    for path in sources:
        target=ART/'source_snapshot'/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    paths=[PRIOR/'CHECKPOINT.json',PRIOR/'NEXT_COST_FRONTIER_PROTOCOL.json',b.ART/'CHECKPOINT.json',b.ART/'RESULTS.json',b.ART/'INPUT_VERIFICATION.json',b.ART/'INDEPENDENT_VERIFICATION.json',
        b.ART/'CANDIDATE_MANIFEST.json',b.ART/'PRIMARY_CANDIDATES.pkl.gz',b.ART/'funding/MANIFEST.json']
    r.save(ART/'SOURCE_MANIFEST.json',{'sources':{str(p):r.sha(p) for p in sources},'inputs':{str(p):r.sha(p) for p in paths},'protocol_sha256':r.sha(ART/'PROTOCOL.json')})
    print('Ten cost conditions frozen; two endpoints must reconcile exactly.',flush=True)


def verify_sources():
    source.verify_sources();p=r.read(ART/'SOURCE_MANIFEST.json');assert p['protocol_sha256']==r.sha(ART/'PROTOCOL.json')
    for group in ('sources','inputs'):
        for path,h in p[group].items():assert r.sha(path)==h,path
    assert r.read(ART/'PROTOCOL.json')['scenarios']==SCENARIOS


def fingerprint():return {'protocol_sha256':r.sha(ART/'PROTOCOL.json'),'source_manifest_sha256':r.sha(ART/'SOURCE_MANIFEST.json'),'parent_input_verification_sha256':r.sha(b.ART/'INPUT_VERIFICATION.json')}


def ledger(year,scenario):
    with gzip.open(ART/'runs'/f'{year}_{scenario}.json.gz','rt',encoding='utf8') as fh:return json.load(fh)


def run_node(raw,prepared,fund,year,scenario):
    folder=ART/'runs';folder.mkdir(exist_ok=True);key=f'{year}_{scenario}';receipt=folder/f'{key}.json';path=folder/f'{key}.json.gz';fp=fingerprint()
    if receipt.exists():
        saved=r.read(receipt);assert all(saved[k]==a for k,a in fp.items()) and saved['ledger_sha256']==r.sha(path);return saved['metric']
    metric=x.portfolio(raw,{'gate':'elite_sniper','sizing':'risk'},f'{year}-01-01',f'{year+1}-01-01',SCENARIOS[scenario],fund,prepared)
    detail={'ledger':metric.pop('ledger'),'curve':metric.pop('curve')};metric['curve_values']=[a[1] for a in detail['curve']]
    with gzip.open(path,'wt',encoding='utf8') as fh:json.dump(detail,fh,separators=(',',':'),allow_nan=False)
    r.save(receipt,{'metric':metric,'ledger_sha256':r.sha(path),**fp})
    print(f'Cost frontier {year}/{scenario}: {metric["return_pct"]:+.3f}%, N={metric["trades"]}',flush=True)
    return metric


def curve(years,scenario):
    points=[];cash=100.
    for year in years:
        node=ledger(year,scenario);points.extend((int(t),float(value*cash/100)) for t,value in node['curve']);cash*=node['curve'][-1][1]/100
    return pd.Series([a[1] for a in points],index=pd.to_datetime([a[0] for a in points],unit='ms',utc=True)).groupby(level=0).last().sort_index()


def observed_sign_changes(rows):
    """Adjacent observed signs only; no interpolation or monotonicity assumption."""
    out=[]
    for a,c in zip(rows[:-1],rows[1:]):
        if (a['return_pct']>0)!=(c['return_pct']>0):out.append({'left_slippage_bps':a['slippage_bps'],'right_slippage_bps':c['slippage_bps'],
            'left_return_pct':a['return_pct'],'right_return_pct':c['return_pct'],'direction':'positive_to_nonpositive' if a['return_pct']>0 else 'nonpositive_to_positive'})
    return out


def evaluate():
    verify_sources()
    if (ART/'RESULTS.json').exists():raise FileExistsError('Results frozen')
    checked=r.read(b.ART/'INPUT_VERIFICATION.json');assert checked['all_passed'] and all(checked[k]==a for k,a in source.fingerprint().items())
    raw=load_candidates();fund=load_funding();prepared={c['id']:x.execution_steps(c) for c in raw};annual={str(y):{} for y in range(2020,2026)};baseline=r.read(b.ART/'RESULTS.json');reconciled=[]
    for scenario,old in ENDPOINTS.items():
        for year in range(2020,2026):
            metric=run_node(raw,prepared,fund,year,scenario);assert metric==baseline['annual'][str(year)][old]
            assert ledger(year,scenario)==b.ledger(year,old);annual[str(year)][scenario]=metric;reconciled.append({'year':year,'scenario':scenario,'original':old})
    r.save(ART/'BASELINE_RECONCILIATION.json',{'all_passed':True,'exact_nodes':reconciled,'original_results_sha256':r.sha(b.ART/'RESULTS.json'),**fingerprint()})
    for scenario in SCENARIOS:
        if scenario in ENDPOINTS:continue
        for year in range(2020,2026):annual[str(year)][scenario]=run_node(raw,prepared,fund,year,scenario)
    periods={};signs={};admission={}
    for label,years in SPLITS.items():
        periods[label]={};signs[label]={};admission[label]={}
        for scenario in SCENARIOS:
            summary=b.original.linked([annual[str(y)] for y in years],scenario)
            weekly,grid=b.statistics.calendar_returns(curve(years,scenario),f'{years[0]}-01-01',f'{years[-1]+1}-01-01');summary['calendar_weekly_ci95']=b.statistics.interval(weekly)
            periods[label][scenario]=summary;ids={(y,a['id']) for y in years for a in ledger(y,scenario)['ledger']}
            ref={(y,a['id']) for y in years for a in ledger(y,'vip6_slip10')['ledger']}
            admission[label][scenario]={'added_vs_standard':len(ids-ref),'removed_vs_standard':len(ref-ids),'symmetric_difference':len(ids^ref)}
        for tier in ('vip6','regular'):
            rows=[{'slippage_bps':slip,'return_pct':periods[label][f'{tier}_slip{slip}']['return_pct']} for slip in (10,20,30,40,50)]
            signs[label][tier]={'adjacent_sign_changes':observed_sign_changes(rows),'point_returns_monotone_nonincreasing':all(a['return_pct']>=c['return_pct'] for a,c in zip(rows[:-1],rows[1:]))}
    r.save(ART/'RESULTS.json',{'version':'4.0.18','annual':annual,'periods':periods,'scenarios':SCENARIOS,'sign_diagnostics':signs,'admission_changes':admission,
        'baseline_reconciliation_sha256':r.sha(ART/'BASELINE_RECONCILIATION.json'),'post_2025_observations':0,'fresh_oos':False,'goal_complete':False,'live_signoff':'NOT_GRANTED',**fingerprint()})
    r.save(ART/'INPUT_VERIFICATION.json',{'all_passed':True,'source':'Frozen v415 independently verified candidate paths and funding source records, all selected snapshot hashes rechecked by loaders.',
        'candidates':len(raw),'funding_symbols':len(fund),'parent_input_verification_sha256':r.sha(b.ART/'INPUT_VERIFICATION.json'),**fingerprint()})
    print({'nodes':60,'baseline_nodes_exact':len(reconciled),'signs':signs},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['register','evaluate']);{'register':register,'evaluate':evaluate}[p.parse_args().action]()
