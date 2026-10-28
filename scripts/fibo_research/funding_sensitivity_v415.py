"""Predeclared adverse proxy-price sensitivities, fully coupled portfolio reruns."""
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import argparse,gzip,json
import numpy as np
import evaluate_universe_resolved_v415 as resolved

b=resolved.base;v=b.v;r=b.r;ART=b.ART;OUT=ART/'funding_sensitivity'


def stressed_event(event,fraction):
    if not 0<=fraction<1:raise ValueError('Invalid mark perturbation')
    a=dict(event)
    if a['price_source']!='funding_api_settlement_mark':
        a['mark_price']=a['mark_price']*(1-np.sign(a['funding_rate'])*fraction)
    return a


def register():
    resolved.verify_sources()
    if (OUT/'PROTOCOL.json').exists():raise FileExistsError('Sensitivity already registered')
    OUT.mkdir(parents=True,exist_ok=True)
    r.save(OUT/'PROTOCOL.json',{'registered_at_utc':datetime.now(timezone.utc).isoformat(),'source_sha256':r.sha(__file__),
        'tests_sha256':r.sha(v.ROOT/'tests/unit/fibo_short/test_funding_sensitivity_v415.py'),
        'levels':[.01,.05],'rule':'Only proxy-priced events: lower mark by1/5percent for positive short income; raise mark for negative short costs. Exact API settlement marks unchanged.',
        'coupling':'Rerun all admissions, quantities, caps, fees and cash with altered funding; do not subtract a fixed haircut from an accepted ledger.',
        'interpretation':'Scenario assumptions, not statistical bounds on exact funding-mark error. No new selection or optimization.',
        'economic_results_existed_at_registration':(ART/'RESULTS.json').exists(),'post_2025_observations':0})


def verify_sources():
    resolved.verify_sources();p=r.read(OUT/'PROTOCOL.json');assert p['source_sha256']==r.sha(__file__)
    assert p['tests_sha256']==r.sha(v.ROOT/'tests/unit/fibo_short/test_funding_sensitivity_v415.py')
    assert not p['economic_results_existed_at_registration']


def run():
    verify_sources();assert r.read(ART/'INDEPENDENT_VERIFICATION.json')['all_accounting_checks_passed']
    raw=resolved.load_candidates();by_id={c['id']:c for c in raw};original=b.load_funding();prepared={c['id']:b.x.execution_steps(c) for c in raw};baseline=r.read(ART/'RESULTS.json');levels={};checks=0;payments=0;admission_changes=0
    for fraction in r.read(OUT/'PROTOCOL.json')['levels']:
        level=f'{fraction:.0%}';fund={s:{'times':a['times'],'events':[stressed_event(ev,fraction) for ev in a['events']]} for s,a in original.items()};annual={}
        for year in range(2020,2026):
            annual[str(year)]={}
            for scenario in b.SCENARIOS:
                result=b.x.portfolio(raw,{'gate':'elite_sniper','sizing':'risk'},f'{year}-01-01',f'{year+1}-01-01',b.SCENARIOS[scenario],fund,prepared)
                detail={'ledger':result.pop('ledger'),'curve':result.pop('curve')};result['curve_values']=[a[1] for a in detail['curve']]
                # Independent fund/payment and complete cash-event reconciliation.
                start=int(r.utc(f'{year}-01-01').timestamp()*1000);end=int(r.utc(f'{year+1}-01-01').timestamp()*1000);changes=defaultdict(float);changes[start]=0.;changes[end]=0.
                for trade in detail['ledger']:
                    c=by_id[trade['id']];trace=c['paths']['ladder']['trace'];fc=0.;pack=original[trade['symbol']]
                    expected=[ev for ev in pack['events'] if trade['entry_ts_ms']<ev['funding_ts_ms']<=trade['exit_ts_ms']];assert len(expected)==len(trade['funding_events'])
                    for actual,source in zip(trade['funding_events'],expected):
                        factor=1 if source['price_source']=='funding_api_settlement_mark' else 1+fraction if source['funding_rate']<0 else 1-fraction if source['funding_rate']>0 else 1
                        assert abs(actual['mark_price']-source['mark_price']*factor)<1e-8
                        prior=[row for row in trace if row[0]*1000<source['funding_ts_ms']];rem=prior[-1][3] if prior else 1.
                        cash=trade['qty']*rem*source['mark_price']*factor*source['funding_rate'];assert abs(cash-actual['cashflow'])<1e-8
                        fc+=cash;changes[source['funding_ts_ms']]+=cash;payments+=1
                    cash=sum(a['notional']*(1 if a['side']=='SELL' else -1) for a in trade['fills'])-trade['fees']+fc
                    assert abs(cash-trade['pnl'])<1e-8
                    for fill in trade['fills']:changes[fill['timestamp_ms']]-=fill['fee']+fill['slippage_cost']
                    for row in trace:changes[row[0]*1000]+=trade['reference_notional']*row[5]
                times=sorted(changes);cash=100+np.cumsum([changes[t] for t in times]);last={int(t):a for t,a in detail['curve']}
                assert sorted(last)==times and np.allclose([last[t] for t in times],cash,atol=1e-8,rtol=0)
                assert abs(cash[-1]-100-result['return_pct'])<1e-8
                prior_ids={a['id'] for a in b.ledger(year,scenario)['ledger']};new_ids={a['id'] for a in detail['ledger']};admission_changes+=len(prior_ids^new_ids)
                target=OUT/f'{year}_{scenario}_{level}.json.gz'
                with gzip.open(target,'wt',encoding='utf8') as fh:json.dump(detail,fh,separators=(',',':'),allow_nan=False)
                annual[str(year)][scenario]=result;checks+=1
            print(f'Proxy sensitivity {level}: {year}',flush=True)
        summaries={name:{scenario:b.original.linked([annual[str(y)] for y in years],scenario) for scenario in b.SCENARIOS} for name,years in r.read(ART/'ECONOMIC_PROTOCOL.json')['splits'].items()}
        levels[level]={'annual':annual,'periods':summaries}
    r.save(OUT/'RESULTS.json',{'levels':levels,'independent_cash_checks_passed':True,'scenario_nodes_checked':checks,'funding_payments_checked':payments,
        'admission_symmetric_difference_sum':admission_changes,'protocol_sha256':r.sha(OUT/'PROTOCOL.json'),'baseline_results_sha256':r.sha(ART/'RESULTS.json'),
        'qualification':'Adverse assumed proxy-mark perturbations, not measured errors or confidence bounds; full cost/funding/cap coupling rerun.',
        'fresh_oos':False,'goal_complete':False})
    print({'nodes':checks,'funding_payments':payments,'changed_admissions':admission_changes},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['register','run']);a=p.parse_args();{'register':register,'run':run}[a.action]()
