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
from pullback_carry_gates import observations,filtered,decision,GATES
from pullback_carry_oracle import expected
from search_pullback_carry import OUT,PRIOR,TIMING_PRIOR,SIGNALS,read,definitions,select,BOUNDARIES,COSTS,DATA
from search_multitimeframe_rolling import grouped_signals
from search_side_capacity import robustness


def main():
    s=read(OUT/'summary.json');p=s['protocol'];specs={sp['id']:sp for sp in s['specs']}
    assert s['specs']==definitions(read(PRIOR/'summary.json'))
    assert s['selected']==select(s['specs'],s['results'])==read(OUT/'candidate_lock.json')['selected']
    for path,key in [(PRIOR/'summary.json','prior_sha256'),(SIGNALS,'signals_sha256'),(ROOT/'configs/live.yaml','live_config_sha256'),(RULE_PATH,'rules_sha256'),(DATA/'reconciled_manifest.json','data_sha256')]:assert sha(path)==p[key]
    for n,d in p['source_sha256'].items():assert sha(ROOT/'scripts'/n)==d
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);all_signals=read(OUT/'signals.json');source=read(SIGNALS)
    oracle,oracle_obs=expected(source['none'],funding);obs=read(OUT/'funding_observations.json')
    assert observations(source['none'],funding)==obs
    for event,o in oracle_obs.items():
        assert o['complete']
        for key,value in o.items():
            actual=obs[event][key]
            if isinstance(value,float):assert abs(actual-value)<1e-12
            else:assert actual==value
    totals=Counter();counts=read(OUT/'gate_counts.json')
    for source_gate in sorted({sp['source_gate'] for sp in s['specs']}):
        ids={e['event_id'] for e in source[source_gate]}
        for gate in GATES:
            key=source_gate+'__'+gate;expected_events=[e for e in oracle[gate] if e['event_id'] in ids]
            actual,count=filtered(source[source_gate],obs,gate)
            assert actual==all_signals[key]==expected_events and count==counts[key]
            assert sum(count.values())==len(ids) and count.get('missing_or_stale_funding',0)==0
            totals['independent_signal_sets']+=1;totals['emissions']+=len(actual)
    for cutoff in ['2025-12-01 01:00','2026-04-01 19:00','2026-07-01 14:00']:
        at=int(pd.Timestamp(cutoff,tz='UTC').value//1000000)
        limited=[e for e in source['none'] if e['at']<=at]
        prefix=observations(limited,{c:[r for r in rows if r[0]<=at] for c,rows in funding.items()})
        assert prefix=={e['event_id']:obs[e['event_id']] for e in limited}
        for source_gate in sorted({sp['source_gate'] for sp in s['specs']}):
            events=[e for e in source[source_gate] if e['at']<=at]
            for gate in GATES:
                assert filtered(events,prefix,gate)[0]==[e for e in all_signals[source_gate+'__'+gate] if e['at']<=at]
                totals['causal_prefixes']+=1
    diagnostic=read(PRIOR/'cost_diagnostic.json')['worst'];o=obs[diagnostic['event_id']]
    write(OUT/'diagnostic_entry.json',dict(prior_trade=diagnostic,known_at_entry=o,decisions={g:decision(o,g) for g in GATES},note='Eligibility only,not a simulated manual exclusion or a promise that later funding stays unchanged;account admission depends on occupied slots.'))
    print('FUNDING SIGNALS AND PREFIXES VERIFIED',flush=True)
    unique={e['event_id']:e for e in source['none']};failures=[]
    for i,row in enumerate(s['results']):
        sp=specs[row['strategy_id']];_,fee,slip=next(c for c in COSTS if c[0]==row['cost'])
        raw=read(OUT/'runs'/f'{row["id"]}.json');curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet')
        a,b,c=audit_directional(raw,curve,prices,funding,fee,slip,sp['cap'],sp['notional']);n,m,t=audit_exits(raw,curve,prices,sp['policy'],unique,fee,slip)
        checks,denied,cancelled=audit_capital(raw,prices,fee,sp['notional'],rules=rules,slip=slip)
        totals.update(journals=1,funding=a,fills=b,equity_states=c,exit_lifecycles=n,exit_observations=m,capital_checks=checks,capital_denied=denied,cancellations=cancelled)
        assert denied==row['margin_rejections']
        assert row['side_metrics']==side_metrics(raw,curve)
        start,end=p['windows'][row['window']]
        candidates={e['event_id']:e for e in all_signals[sp['source_gate']+'__'+sp['gate']] if start<=e.get('source_at',e['at']) and e['at']<end}
        assert len(candidates)==row['candidates']
        for j in raw['journal']:
            if j['kind']=='entry':
                e=candidates[j['event_id']];assert (j['at'],j['symbol'],j['side'])==(e['at'],e['symbol'],e['side'])
                totals['executed_candidates']+=1
        assert row['monthly']==monthly_metrics(curve.to_dict('records'),boundaries=[t for t in BOUNDARIES if start<=t<=end])
        assert row['ending_equity']==raw['ending_equity'] and row['target_met']==(raw['ending_equity'] is not None and row['monthly']['all_months_50pct'])
        if sp['baseline']:
            ident=sp['reference']
            control=PRIOR/'runs'/f'{row["window"]}_{row["cost"]}_{ident}'
            assert raw==read(Path(str(control)+'.json'))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(str(control)+'_equity.parquet'),check_exact=True);totals['baseline_paths_exact']+=1
        if raw['ending_equity'] is None:
            assert raw['stop_event'] and all(e.startswith('maintenance_proxy_breached:') for e in raw['errors'])
            failures.append(dict(id=row['id'],errors=raw['errors'],stop_event=raw['stop_event'],reconstruction=reconstruct(raw,fee,prices)))
        if (i+1)%40==0:print('AUDITED',i+1,flush=True)
    assert totals['baseline_paths_exact']==48 and s['robustness']==robustness(s['results'])
    # Two predefined ATR10 funding-gate full-year paths, both sizes; exact replay.
    for sp in s['specs']:
        if sp['gate']!='atr10':continue
        signals=all_signals[sp['source_gate']+'__'+sp['gate']]
        start,end=p['windows']['year'];cost,fee,slip=COSTS[0]
        r=simulate(list(range(start,end+1,300000)),grouped_signals([e for e in signals if e.get('source_at',e['at'])>=start],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(sp['cap'],fee,slip),research_policy=sp['policy'])
        r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct';key=f'year_{cost}_{sp["id"]}'
        assert {k:v for k,v in r.items() if k!='curve'}==read(OUT/'runs'/f'{key}.json')
        pd.testing.assert_frame_equal(pd.DataFrame(r['curve']),pd.read_parquet(OUT/'runs'/f'{key}_equity.parquet'),check_exact=True);totals['replayed_paths_exact']+=1
    assert len(s['results'])==240 and len({r['id'] for r in s['results']})==240
    assert s['target_met_rows']==sum(r['target_met'] for r in s['results'])
    assert len(failures)==s['incomplete_paths'];write(OUT/'incomplete_paths.json',failures)
    pairs=[]
    lookup={(r['notional'],r['gate'],r['window'],r['cost']):r for r in s['results']}
    for budget in [25,100]:
        for gate in GATES[1:]:
            for cost in ['base','stress']:
                details=[]
                for window in [w for w in p['windows'] if w.startswith('roll_') or w=='later']:
                    control=lookup[(budget,'none',window,cost)];candidate=lookup[(budget,gate,window,cost)]
                    a,b=control['ending_equity'],candidate['ending_equity']
                    details.append(dict(window=window,control=a,candidate=b,delta=b-a if a is not None and b is not None else None))
                assert len(details)==10
                deltas=[d['delta'] for d in details if d['delta'] is not None]
                pairs.append(dict(notional=budget,gate=gate,cost=cost,complete_pairs=len(deltas),improved=sum(d>1e-8 for d in deltas),worsened=sum(d< -1e-8 for d in deltas),median_delta=float(np.median(deltas)) if deltas else None,details=details,note='Same finite wallet and original candidates. Filters change admitted inventory; not an isolated causal estimate of signal quality. Overlapping history, not independent future evidence.'))
    write(OUT/'paired_effect.json',pairs)
    write(OUT/'verification.json',dict(totals=totals,hashes_match=True,live_config_unchanged=True,not_new_holdout=True,financially_verified=False));print('VERIFIED',dict(totals),flush=True)


if __name__=='__main__':main()
