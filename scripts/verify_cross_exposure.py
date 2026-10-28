"""Independent commitment reconstruction and inherited full financial audits."""
from collections import Counter
import pandas as pd
from account_exposure_replay import simulate
from exposure_admission import audit
from exposure_profile import profile
from compare_account_risk import ROOT,sha,write,exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from research_directional_audit import audit_directional
from cross_sectional_audit import audit_exits
from directional_capacity_metrics import side_metrics
from monthly_account_metrics import monthly_metrics
from search_cross_exposure import OUT,PRIOR,SIGNALS,read,definitions,select,BOUNDARIES,COSTS,DATA
from search_multitimeframe_rolling import grouped_signals
from search_side_capacity import robustness


def main():
    s=read(OUT/'summary.json');p=s['protocol'];specs={sp['id']:sp for sp in s['specs']}
    assert s['specs']==definitions(read(PRIOR/'summary.json'))
    assert s['selected']==select(s['specs'],s['results'])==read(OUT/'candidate_lock.json')['selected']
    for path,key in [(PRIOR/'summary.json','prior_sha256'),(SIGNALS,'signals_sha256'),(ROOT/'configs/live.yaml','live_config_sha256'),(RULE_PATH,'rules_sha256'),(DATA/'reconciled_manifest.json','data_sha256')]:assert sha(path)==p[key]
    for n,d in p['source_sha256'].items():assert sha(ROOT/'scripts'/n)==d
    prices,funding,_=load();rules=exchange_rules(RULE_PATH);signals=read(SIGNALS)
    unique={e['event_id']:e for events in signals.values() for e in events};totals=Counter();failures=[];profiles={}
    for i,row in enumerate(s['results']):
        sp=specs[row['strategy_id']];_,fee,slip=next(c for c in COSTS if c[0]==row['cost'])
        raw=read(OUT/'runs'/f'{row["id"]}.json');curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet')
        a,b,c=audit_directional(raw,curve,prices,funding,fee,slip,5,sp['notional']);n,m,t=audit_exits(raw,curve,prices,sp['policy'],unique,fee,slip)
        totals.update(journals=1,funding=a,fills=b,equity_states=c,exit_lifecycles=n,exit_observations=m,time_exits=t)
        profiles[row['id']]=profile(raw,curve,prices,sp['policy'].get('max_net_commitment'))
        if not sp['baseline']:
            a,b=audit(raw,prices,sp['notional'],sp['policy']['max_net_commitment'],rules)
            assert row['exposure_checks']==a and row['exposure_rejected']==b
            totals.update(exposure_decisions=a,exposure_rejected=b)
        assert row['side_metrics']==side_metrics(raw,curve)
        start,end=p['windows'][row['window']]
        assert row['monthly']==monthly_metrics(curve.to_dict('records'),boundaries=[t for t in BOUNDARIES if start<=t<=end])
        assert row['ending_equity']==raw['ending_equity'] and row['target_met']==(raw['ending_equity'] is not None and row['monthly']['all_months_50pct'])
        if sp['baseline']:
            assert raw==read(PRIOR/'runs'/f'{row["id"]}.json')
            pd.testing.assert_frame_equal(curve,pd.read_parquet(PRIOR/'runs'/f'{row["id"]}_equity.parquet'),check_exact=True);totals['baseline_paths_exact']+=1
        if raw['ending_equity'] is None:
            # Keep failures explicit; no fabricated liquidation fill or ending.
            assert raw['stop_event'] and all(e.startswith('maintenance_proxy_breached:') for e in raw['errors'])
            from verify_cross_regime_failures import reconstruct
            failures.append(dict(id=row['id'],**reconstruct(raw,fee,prices)))
        if (i+1)%40==0:print('AUDITED',i+1,flush=True)
    assert totals['baseline_paths_exact']==96
    assert s['results']==read(OUT/'pre_instrumentation_summary.json')['results']
    assert s['robustness']==robustness(s['results'])
    for sp in s['specs']:
        if sp['gate']!='net1':continue
        start,end=p['windows']['year'];cost,fee,slip=COSTS[0]
        r=simulate(list(range(start,end+1,300000)),grouped_signals(signals[sp['source']],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(5,fee,slip),research_policy=sp['policy'])
        r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct';key=f'year_{cost}_{sp["id"]}'
        assert {k:v for k,v in r.items() if k!='curve'}==read(OUT/'runs'/f'{key}.json')
        pd.testing.assert_frame_equal(pd.DataFrame(r['curve']),pd.read_parquet(OUT/'runs'/f'{key}_equity.parquet'),check_exact=True);totals['replayed_paths_exact']+=1
    assert len(failures)==s['incomplete_paths']
    write(OUT/'failure_verification.json',dict(checked_paths=len(failures),rows=failures,exact_historical_liquidation_unknown=True))
    write(OUT/'exposure_profiles.json',profiles)
    write(OUT/'verification.json',dict(totals=totals,hashes_match=True,live_config_unchanged=True,not_new_holdout=True,financially_verified=False));print('VERIFIED',dict(totals),flush=True)


if __name__=='__main__':main()
