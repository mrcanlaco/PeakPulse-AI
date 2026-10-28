"""Independent delayed-entry oracle, causal prefixes and finite-wallet audits."""
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
from account_net_trailing_replay import simulate
from cross_sectional_audit import audit_exits
from momentum_entry_timing import transform,MODES
from momentum_timing_audit import expected
from research_directional_audit import audit_directional
from compare_account_risk import ROOT,sha,write,exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from directional_capacity_metrics import side_metrics
from monthly_account_metrics import monthly_metrics
from search_momentum_timing import OUT,PRIOR,SIGNALS,read,definitions,select,BOUNDARIES,COSTS,DATA
from search_multitimeframe_rolling import grouped_signals
from search_side_capacity import robustness


def main():
    s=read(OUT/'summary.json');p=s['protocol'];specs={sp['id']:sp for sp in s['specs']}
    assert s['specs']==definitions(read(PRIOR/'summary.json'))
    assert s['selected']==select(s['specs'],s['results'])==read(OUT/'candidate_lock.json')['selected']
    for path,key in [(PRIOR/'summary.json','prior_sha256'),(SIGNALS,'signals_sha256'),(ROOT/'configs/live.yaml','live_config_sha256'),(RULE_PATH,'rules_sha256'),(DATA/'reconciled_manifest.json','data_sha256')]:assert sha(path)==p[key]
    for n,d in p['source_sha256'].items():assert sha(ROOT/'scripts'/n)==d
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);signals=read(OUT/'signals.json')
    totals=Counter()
    origins=[e for e in read(SIGNALS)['momentum_168h_raw'] if BOUNDARIES[0]<=e['at']<BOUNDARIES[-1]]
    assert origins==read(OUT/'origin_signals.json')
    for mode in MODES:
        assert signals[mode]==expected(origins,frames,mode)
        assert len({e['event_id'] for e in signals[mode]})==len(signals[mode])
        totals['independent_signal_sets']+=1;totals['emissions']+=len(signals[mode])
        counts={'emitted':len(signals[mode])}
        if len(signals[mode])<len(origins):counts['expired']=len(origins)-len(signals[mode])
        assert read(OUT/'timing_counts.json')[mode]==counts
    for cutoff in ['2025-12-01','2026-04-01','2026-07-01']:
        t=pd.Timestamp(cutoff,tz='UTC');at=int(t.value//1000000)
        for mode in MODES:
            prefix=transform([e for e in origins if e['at']<=at],{c:f.loc[:t] for c,f in frames.items()},mode)[0]
            assert prefix==[e for e in signals[mode] if e['at']<=at];totals['causal_prefixes']+=1
    unique={e['event_id']:e for events in signals.values() for e in events};failures=[]
    for i,row in enumerate(s['results']):
        sp=specs[row['strategy_id']];_,fee,slip=next(c for c in COSTS if c[0]==row['cost'])
        raw=read(OUT/'runs'/f'{row["id"]}.json');curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet')
        a,b,c=audit_directional(raw,curve,prices,funding,fee,slip,5,sp['notional']);n,m,t=audit_exits(raw,curve,prices,sp['policy'],unique,fee,slip)
        totals.update(journals=1,funding=a,fills=b,equity_states=c,exit_lifecycles=n,exit_observations=m,time_exits=t)
        assert row['side_metrics']==side_metrics(raw,curve)
        start,end=p['windows'][row['window']]
        candidates={e['event_id']:e for e in signals[sp['timing']] if start<=e.get('source_at',e['at']) and e['at']<end}
        assert row['candidates']==len(candidates)
        for j in raw['journal']:
            if j['kind']=='entry':
                e=candidates[j['event_id']]
                assert (j['at'],j['symbol'],j['side'])==(e['at'],e['symbol'],e['side'])
                totals['executed_candidates']+=1
        assert row['monthly']==monthly_metrics(curve.to_dict('records'),boundaries=[t for t in BOUNDARIES if start<=t<=end])
        assert row['ending_equity']==raw['ending_equity'] and row['target_met']==(raw['ending_equity'] is not None and row['monthly']['all_months_50pct'])
        control=None
        if sp['baseline']:control=PRIOR/'runs'/f'{row["window"]}_{row["cost"]}_{sp["parent_id"]}'
        if control:
            assert raw==read(Path(str(control)+'.json'))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(str(control)+'_equity.parquet'),check_exact=True);totals['baseline_paths_exact']+=1
        if raw['ending_equity'] is None:failures.append(dict(id=row['id'],errors=raw['errors'],stop_event=raw['stop_event']))
        if (i+1)%40==0:print('AUDITED',i+1,flush=True)
    assert totals['baseline_paths_exact']==48 and s['robustness']==robustness(s['results'])
    # Four predetermined full-year replays, two timing families and bothsizes.
    for sp in s['specs']:
        if sp['timing'] not in ['retest05','break1']:continue
        start,end=p['windows']['year'];cost,fee,slip=COSTS[0]
        r=simulate(list(range(start,end+1,300000)),grouped_signals([e for e in signals[sp['timing']] if e.get('source_at',e['at'])>=start],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(5,fee,slip),research_policy=sp['policy'])
        r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct';key=f'year_{cost}_{sp["id"]}'
        assert {k:v for k,v in r.items() if k!='curve'}==read(OUT/'runs'/f'{key}.json')
        pd.testing.assert_frame_equal(pd.DataFrame(r['curve']),pd.read_parquet(OUT/'runs'/f'{key}_equity.parquet'),check_exact=True);totals['replayed_paths_exact']+=1
    assert len(failures)==s['incomplete_paths'];write(OUT/'incomplete_paths.json',failures)
    write(OUT/'verification.json',dict(totals=totals,hashes_match=True,live_config_unchanged=True,not_new_holdout=True,financially_verified=False));print('VERIFIED',dict(totals),flush=True)


if __name__=='__main__':main()
