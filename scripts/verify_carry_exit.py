"""Full committed-capital, fill, funding and marked wallet audits of scale variants."""
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
from account_carry_exit_replay import simulate
from carry_exit_audit import audit_exits
from capital_commitment_audit import audit as audit_capital
from cross_halt_audit import reconstruct
from research_directional_audit import audit_directional
from compare_account_risk import ROOT,sha,write,exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from directional_capacity_metrics import side_metrics
from monthly_account_metrics import monthly_metrics
from search_carry_exit import OUT,PRIOR,DIAG,TIMING_PRIOR,SIGNALS,read,definitions,select,BOUNDARIES,COSTS,DATA
from search_multitimeframe_rolling import grouped_signals
from search_side_capacity import robustness


def main():
    s=read(OUT/'summary.json');p=s['protocol'];specs={sp['id']:sp for sp in s['specs']}
    assert s['specs']==definitions(read(PRIOR/'summary.json'),read(DIAG/'summary.json'))
    assert s['selected']==select(s['specs'],s['results'])==read(OUT/'candidate_lock.json')['selected']
    for path,key in [(PRIOR/'summary.json','prior_sha256'),(DIAG/'summary.json','diagnostic_sha256'),(DIAG/'signals.json','diagnostic_signals_sha256'),(SIGNALS,'signals_sha256'),(ROOT/'configs/live.yaml','live_config_sha256'),(RULE_PATH,'rules_sha256'),(DATA/'reconciled_manifest.json','data_sha256')]:assert sha(path)==p[key]
    for n,d in p['source_sha256'].items():assert sha(ROOT/'scripts'/n)==d
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);all_signals=read(OUT/'signals.json')
    for sp in s['specs']:assert all_signals[sp['reference']]==read((PRIOR if sp['source_kind']=='carry' else DIAG)/'signals.json')[sp['source_key']]
    totals=Counter()
    unique={e['event_id']:e for es in all_signals.values() for e in es};failures=[]
    for i,row in enumerate(s['results']):
        sp=specs[row['strategy_id']];_,fee,slip=next(c for c in COSTS if c[0]==row['cost'])
        raw=read(OUT/'runs'/f'{row["id"]}.json');curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet')
        a,b,c=audit_directional(raw,curve,prices,funding,fee,slip,sp['cap'],sp['notional']);n,m,t=audit_exits(raw,curve,prices,sp['policy'],unique,fee,slip)
        checks,denied,cancelled=audit_capital(raw,prices,fee,sp['notional'],rules=rules,slip=slip)
        totals.update(journals=1,funding=a,fills=b,equity_states=c,exit_lifecycles=n,exit_observations=m,carry_exit_oracle_hits=t,capital_checks=checks,capital_denied=denied,cancellations=cancelled)
        assert denied==row['margin_rejections']
        exits=[j for j in raw['journal'] if j['kind']=='carry_exit']
        assert t==len(exits)
        assert row['carry_diagnostics']==dict(count=len(exits),negative=sum(j['net']<0 for j in exits),total_net=sum(j['net'] for j in exits),worst_net=min((j['net'] for j in exits),default=None),limit=sp['notional']*sp['carry_fraction'] if sp['carry_fraction'] is not None else None,max_observed_cost_ratio=max((-j['known_funding']/j['funding_limit'] for j in exits),default=None))
        if raw['ending_equity'] is not None and sp['carry_fraction'] is not None:
            for pos in raw['open_positions']:
                receipts=[j for j in raw['journal'] if j['symbol']==pos['symbol'] and j['kind']=='funding' and j['at']>pos['opened_at']]
                known=sum(j['amount'] for j in receipts if j['at']<=int(curve['at'].iloc[-1])-60000)
                pending=[[j['at'],j['amount']] for j in receipts if j['at']>int(curve['at'].iloc[-1])-60000]
                assert abs(pos['funding_known']-known)<1e-8 and pos['funding_pending']==pending
        assert row['side_metrics']==side_metrics(raw,curve)
        start,end=p['windows'][row['window']]
        candidates={e['event_id']:e for e in all_signals[sp['reference']] if start<=e.get('source_at',e['at']) and e['at']<end}
        assert row['candidates']==len(candidates)
        for j in raw['journal']:
            if j['kind']=='entry':
                e=candidates[j['event_id']];assert (j['at'],j['symbol'],j['side'])==(e['at'],e['symbol'],e['side'])
        assert row['monthly']==monthly_metrics(curve.to_dict('records'),boundaries=[t for t in BOUNDARIES if start<=t<=end])
        assert row['ending_equity']==raw['ending_equity'] and row['target_met']==(raw['ending_equity'] is not None and row['monthly']['all_months_50pct'])
        if sp['baseline']:
            folder=PRIOR if sp['source_kind']=='carry' else DIAG
            control=folder/'runs'/f'{row["window"]}_{row["cost"]}_{sp["parent_id"]}'
            assert raw==read(Path(str(control)+'.json'))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(str(control)+'_equity.parquet'),check_exact=True);totals['baseline_paths_exact']+=1
        if raw['ending_equity'] is None:
            assert raw['stop_event'] and all(e.startswith('maintenance_proxy_breached:') for e in raw['errors'])
            failures.append(dict(id=row['id'],errors=raw['errors'],stop_event=raw['stop_event'],reconstruction=reconstruct(raw,fee,prices)))
        if (i+1)%40==0:print('AUDITED',i+1,flush=True)
    assert totals['baseline_paths_exact']==72 and s['robustness']==robustness(s['results'])
    # Three predefined strictest carry-budget full-year base paths, exact replay.
    for sp in s['specs']:
        if sp['carry_rule']!='f005':continue
        signals=all_signals[sp['reference']]
        start,end=p['windows']['year'];cost,fee,slip=COSTS[0]
        r=simulate(list(range(start,end+1,300000)),grouped_signals([e for e in signals if e.get('source_at',e['at'])>=start],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(sp['cap'],fee,slip),research_policy=sp['policy'])
        r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct';key=f'year_{cost}_{sp["id"]}'
        assert {k:v for k,v in r.items() if k!='curve'}==read(OUT/'runs'/f'{key}.json')
        pd.testing.assert_frame_equal(pd.DataFrame(r['curve']),pd.read_parquet(OUT/'runs'/f'{key}_equity.parquet'),check_exact=True);totals['replayed_paths_exact']+=1
    assert len(s['results'])==288 and len({r['id'] for r in s['results']})==288
    assert s['target_met_rows']==sum(r['target_met'] for r in s['results'])
    assert len(failures)==s['incomplete_paths'];write(OUT/'incomplete_paths.json',failures)
    write(OUT/'verification.json',dict(totals=totals,hashes_match=True,live_config_unchanged=True,not_new_holdout=True,financially_verified=False));print('VERIFIED',dict(totals),flush=True)


if __name__=='__main__':main()
