"""Full committed-capital, fill, funding and marked wallet audits of scale variants."""
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
from account_capital_trace import simulate
from cross_sectional_audit import audit_exits
from capital_commitment_audit import audit as audit_capital
from cross_halt_audit import reconstruct
from research_directional_audit import audit_directional
from compare_account_risk import ROOT,sha,write,exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from directional_capacity_metrics import side_metrics
from monthly_account_metrics import monthly_metrics
from residual_momentum_signals import enrich,generate
from residual_momentum_oracle import feature_oracle,event_oracle
from momentum_timing_audit import expected as timing_oracle
from momentum_entry_timing import transform
from search_residual_momentum import OUT,PRIOR,TIMING_PRIOR,SIGNALS,read,definitions,select,BOUNDARIES,COSTS,DATA,GATES
from search_multitimeframe_rolling import grouped_signals
from search_side_capacity import robustness


def main():
    s=read(OUT/'summary.json');p=s['protocol'];specs={sp['id']:sp for sp in s['specs']}
    assert s['specs']==definitions(read(PRIOR/'summary.json'))
    assert s['selected']==select(s['specs'],s['results'])==read(OUT/'candidate_lock.json')['selected']
    for path,key in [(PRIOR/'summary.json','prior_sha256'),(SIGNALS,'signals_sha256'),(ROOT/'configs/live.yaml','live_config_sha256'),(RULE_PATH,'rules_sha256'),(DATA/'reconciled_manifest.json','data_sha256')]:assert sha(path)==p[key]
    for n,d in p['source_sha256'].items():assert sha(ROOT/'scripts'/n)==d
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);all_signals=read(OUT/'signals.json');source=read(SIGNALS)
    oracle_features=feature_oracle(frames);actual_features=enrich(frames)
    for coin,f in actual_features.items():
        expected=oracle_features[coin].reindex(f.index)
        assert np.array_equal(f.eligible,expected.eligible), coin
        for col in ['beta','atr','raw24','raw72','raw168','risk_adjusted24','risk_adjusted72','risk_adjusted168']:
            np.testing.assert_allclose(f[col],expected[col],atol=1e-9,rtol=1e-8,equal_nan=True,err_msg=coin+col)
    oracle=event_oracle(oracle_features)
    oracle={key:[e for e in es if BOUNDARIES[0]<=e['at']<BOUNDARIES[-1]] for key,es in oracle.items()}
    origins=read(OUT/'origin_signals.json');counts=read(OUT/'timing_counts.json');diagnostics=read(OUT/'timing_diagnostics.json')
    assert all_signals['control']==source
    for key,events in origins.items():
        assert len(events)==len(oracle[key])
        for a,b in zip(events,oracle[key]):
            assert {k:v for k,v in a.items() if k!='atr'}=={k:v for k,v in b.items() if k!='atr'}
            assert abs(a['atr']-b['atr'])<=1e-9+abs(a['atr'])*1e-8
        assert all_signals[key]==timing_oracle(events,frames,'pull05')
        emitted,count,details=transform(events,frames,'pull05')
        assert (emitted,count,details)==(all_signals[key],counts[key],diagnostics[key])
        assert not count.get('data_error') and not count.get('right_censored')
        assert len({e['event_id'] for e in emitted})==len(emitted)
    coverage=read(OUT/'coverage.json')
    assert len(coverage)==365
    for row in coverage:
        t=pd.Timestamp(row['at'],unit='ms',tz='UTC')
        count=sum(bool(f.loc[t,'eligible']) for f in oracle_features.values() if t in f.index)
        assert count==row['eligible'] and row['ready']==(count>=24) and row['ready']
    totals=Counter(independent_signal_sets=6,emissions=sum(len(es) for es in all_signals.values()),feature_coins=len(actual_features))
    for cutoff in ['2025-12-01 01:00','2026-04-01 19:00','2026-07-01 14:00']:
        t=pd.Timestamp(cutoff,tz='UTC');at=int(t.value//1000000)
        prefix=generate(enrich({c:f.loc[:t] for c,f in frames.items()}))
        for key in origins:
            assert [e for e in prefix[key] if BOUNDARIES[0]<=e['at']<=at]==[e for e in origins[key] if e['at']<=at]
            totals['causal_prefixes']+=1
    print('FEATURES SIGNALS TIMING AND PREFIXES VERIFIED',flush=True)
    unique={e['event_id']:e for es in all_signals.values() for e in es};failures=[]
    for i,row in enumerate(s['results']):
        sp=specs[row['strategy_id']];_,fee,slip=next(c for c in COSTS if c[0]==row['cost'])
        raw=read(OUT/'runs'/f'{row["id"]}.json');curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet')
        a,b,c=audit_directional(raw,curve,prices,funding,fee,slip,sp['cap'],sp['notional']);n,m,t=audit_exits(raw,curve,prices,sp['policy'],unique,fee,slip)
        checks,denied,cancelled=audit_capital(raw,prices,fee,sp['notional'],rules=rules,slip=slip)
        totals.update(journals=1,funding=a,fills=b,equity_states=c,exit_lifecycles=n,exit_observations=m,capital_checks=checks,capital_denied=denied,cancellations=cancelled)
        assert denied==row['margin_rejections']
        assert row['side_metrics']==side_metrics(raw,curve)
        start,end=p['windows'][row['window']]
        candidates={e['event_id']:e for e in all_signals[sp['gate']] if start<=e.get('source_at',e['at']) and e['at']<end}
        assert len(candidates)==row['candidates']
        for j in raw['journal']:
            if j['kind']=='entry':
                e=candidates[j['event_id']];assert (j['at'],j['symbol'],j['side'])==(e['at'],e['symbol'],e['side'])
                totals['executed_candidates']+=1
        assert row['monthly']==monthly_metrics(curve.to_dict('records'),boundaries=[t for t in BOUNDARIES if start<=t<=end])
        assert row['ending_equity']==raw['ending_equity'] and row['target_met']==(raw['ending_equity'] is not None and row['monthly']['all_months_50pct'])
        if sp['baseline']:
            ident=f'pull05_cap5_n{sp["notional"]}'
            control=PRIOR/'runs'/f'{row["window"]}_{row["cost"]}_{ident}'
            assert raw==read(Path(str(control)+'.json'))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(str(control)+'_equity.parquet'),check_exact=True);totals['baseline_paths_exact']+=1
        if raw['ending_equity'] is None:
            assert raw['stop_event'] and all(e.startswith('maintenance_proxy_breached:') for e in raw['errors'])
            failures.append(dict(id=row['id'],errors=raw['errors'],stop_event=raw['stop_event'],reconstruction=reconstruct(raw,fee,prices)))
        if (i+1)%40==0:print('AUDITED',i+1,flush=True)
    assert totals['baseline_paths_exact']==48 and s['robustness']==robustness(s['results'])
    # Two predefined 72-hour risk-adjusted full-year paths; exact replay.
    for sp in s['specs']:
        if sp['gate']!='residual_72h_risk_adjusted':continue
        signals=all_signals[sp['gate']]
        start,end=p['windows']['year'];cost,fee,slip=COSTS[0]
        r=simulate(list(range(start,end+1,300000)),grouped_signals([e for e in signals if e.get('source_at',e['at'])>=start],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(sp['cap'],fee,slip),research_policy=sp['policy'])
        r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct';key=f'year_{cost}_{sp["id"]}'
        assert {k:v for k,v in r.items() if k!='curve'}==read(OUT/'runs'/f'{key}.json')
        pd.testing.assert_frame_equal(pd.DataFrame(r['curve']),pd.read_parquet(OUT/'runs'/f'{key}_equity.parquet'),check_exact=True);totals['replayed_paths_exact']+=1
    assert len(s['results'])==336 and len({r['id'] for r in s['results']})==336
    assert s['target_met_rows']==sum(r['target_met'] for r in s['results'])
    assert len(failures)==s['incomplete_paths'];write(OUT/'incomplete_paths.json',failures)
    pairs=[]
    lookup={(r['notional'],r['gate'],r['window'],r['cost']):r for r in s['results']}
    for budget in [25,100]:
        for gate in GATES[1:]:
            for cost in ['base','stress']:
                details=[]
                for window in [w for w in p['windows'] if w.startswith('roll_') or w=='later']:
                    control=lookup[(budget,'control',window,cost)];candidate=lookup[(budget,gate,window,cost)]
                    a,b=control['ending_equity'],candidate['ending_equity']
                    details.append(dict(window=window,control=a,candidate=b,delta=b-a if a is not None and b is not None else None))
                assert len(details)==10
                deltas=[d['delta'] for d in details if d['delta'] is not None]
                pairs.append(dict(notional=budget,gate=gate,cost=cost,complete_pairs=len(deltas),improved=sum(d>1e-8 for d in deltas),worsened=sum(d< -1e-8 for d in deltas),median_delta=float(np.median(deltas)) if deltas else None,details=details,note='Same finite wallet and execution, different candidate sources. Changed admissions and inventory are part of portfolio results; not an isolated per-signal treatment estimate. Overlapping history, not independent future evidence.'))
    write(OUT/'paired_effect.json',pairs)
    write(OUT/'verification.json',dict(totals=totals,hashes_match=True,live_config_unchanged=True,not_new_holdout=True,financially_verified=False));print('VERIFIED',dict(totals),flush=True)


if __name__=='__main__':main()
