"""Verify entry oracles, causal prefixes, full account ledgers and exit timing."""
from collections import Counter
import pandas as pd
from account_net_trailing_replay import simulate
from compare_account_risk import ROOT,sha,write,exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from research_directional_audit import audit_directional
from monthly_account_metrics import monthly_metrics
from cross_sectional_signals import enrich,rank_state,generate,definitions as source_specs
from cross_sectional_audit import audit_features,audit_ranks_and_signals,audit_exits
from search_cross_sectional import OUT,PRIOR,read,definitions,select,scaling,WINDOWS,BOUNDARIES,COSTS,DATA
from search_multitimeframe_rolling import grouped_signals


def main():
    s=read(OUT/'summary.json');p=s['protocol'];previous=read(PRIOR/'summary.json');base=definitions(previous)
    assert s['selected']==select(base,s['results'])
    assert s['specs']==base+scaling(base,s['selected'])
    lock=read(OUT/'candidate_lock.json');assert lock['selected']==s['selected'] and lock['scaled_specs']==scaling(base,s['selected'])
    assert sha(PRIOR/'summary.json')==p['prior_sha256'] and sha(PRIOR/'signals.json')==p['prior_signals_sha256']
    assert sha(ROOT/'configs/live.yaml')==p['live_config_sha256'] and sha(RULE_PATH)==p['rules_sha256'] and sha(DATA/'reconciled_manifest.json')==p['data_sha256']
    for n,d in p['source_sha256'].items():assert sha(ROOT/'scripts'/n)==d
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH)
    enriched={c:pd.read_parquet(OUT/'features'/f'{c}.parquet') for c in frames if c!='BTCUSDT'}
    state=pd.read_parquet(OUT/'market.parquet');ranks={f'{key}{n}':pd.read_parquet(OUT/f'ranks_{key}{n}.parquet') for n in [24,72,168] for key in ['raw','risk_adjusted']}
    signals=read(OUT/'signals.json');totals=Counter(feature_snapshots=audit_features(frames,enriched))
    a,b=audit_ranks_and_signals(enriched,state,ranks,source_specs(),signals);totals.update(rank_cells=a,independent_signals=b)
    old_signals=read(PRIOR/'signals.json')
    for sp in base:
        if sp['baseline']:assert signals[sp['source']]==old_signals[sp['source'].removeprefix('control_')]
    for cutoff in [pd.Timestamp(t,tz='UTC') for t in ['2025-12-01','2026-04-01','2026-07-01']]:
        f=enrich({c:h.loc[:cutoff] for c,h in frames.items()});st,r=rank_state(f);es=generate(f,st,r)
        ms=int(cutoff.timestamp()*1000)
        for key,events in es.items():assert [e for e in events if e['at']<=ms]==[e for e in signals[key] if e['at']<=ms]
        totals['causal_prefixes']+=1
    specs={sp['id']:sp for sp in s['specs']};windows=dict(WINDOWS,**p['quarters']);unique={e['event_id']:e for events in signals.values() for e in events}
    for i,row in enumerate(s['results']):
        sp=specs[row['strategy_id']];_,fee,slip=next(c for c in COSTS if c[0]==row['cost'])
        raw=read(OUT/'runs'/f'{row["id"]}.json');curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet')
        a,b,c=audit_directional(raw,curve,prices,funding,fee,slip,5,sp['notional'])
        n,m,t=audit_exits(raw,curve,prices,sp['policy'],unique,fee,slip)
        totals.update(journals=1,funding=a,fills=b,equity_states=c,exit_lifecycles=n,exit_observations=m,time_exits=t)
        start,end=windows[row['window']]
        assert row['monthly']==monthly_metrics(curve.to_dict('records'),boundaries=[t for t in BOUNDARIES if start<=t<=end])
        assert row['target_met']==(raw['ending_equity'] is not None and row['monthly']['all_months_50pct'])
        assert row['ending_equity']==raw['ending_equity']
        if sp['baseline'] and row['window'] in WINDOWS:
            key=f'{row["window"]}_{row["cost"]}_{sp["reference"]}'
            assert raw==read(PRIOR/'runs'/f'{key}.json')
            pd.testing.assert_frame_equal(curve,pd.read_parquet(PRIOR/'runs'/f'{key}_equity.parquet'),check_exact=True);totals['baseline_paths_exact']+=1
        if (i+1)%40==0:print('AUDITED',i+1,flush=True)
    # Eight fixed72h raw full-year cases plus all selected scaled full-yearbase cases.
    replay_specs=[sp for sp in s['specs'] if (not sp['baseline'] and not sp['scaled'] and sp['source'] in ['momentum_72h_raw','reversion_72h_raw']) or sp['scaled']]
    for sp in replay_specs:
        start,end=WINDOWS['year'];cost,fee,slip=COSTS[0]
        r=simulate(list(range(start,end+1,300000)),grouped_signals(signals[sp['source']],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(5,fee,slip),research_policy=sp['policy'])
        r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct';key=f'year_{cost}_{sp["id"]}'
        assert {k:v for k,v in r.items() if k!='curve'}==read(OUT/'runs'/f'{key}.json')
        pd.testing.assert_frame_equal(pd.DataFrame(r['curve']),pd.read_parquet(OUT/'runs'/f'{key}_equity.parquet'),check_exact=True);totals['replayed_paths_exact']+=1
    write(OUT/'verification.json',dict(totals=totals,hashes_match=True,live_config_unchanged=True,not_new_holdout=True,financially_verified=False))
    print('VERIFIED',dict(totals),flush=True)


if __name__=='__main__':main()
