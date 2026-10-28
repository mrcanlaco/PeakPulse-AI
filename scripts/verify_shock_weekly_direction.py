"""Independent signal, capital and marked-wallet audits for batch44."""
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
from account_capital_trace import simulate
from cross_sectional_audit import audit_exits,audit_features,audit_ranks_and_signals
from cross_sectional_signals import enrich,rank_state
from capital_commitment_audit import audit as audit_capital
from cross_halt_audit import reconstruct
from research_directional_audit import audit_directional
from compare_account_risk import ROOT,sha,write,exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from directional_capacity_metrics import side_metrics
from monthly_account_metrics import monthly_metrics
from shock_weekly_alignment import states
from shock_weekly_direction import transform,MODES,opposite
from search_shock_weekly_direction import OUT,PRIOR,TIMING_PRIOR,SIGNALS,read,definitions,select,BOUNDARIES,COSTS,DATA,SOURCES,ROOT
from search_multitimeframe_rolling import grouped_signals
from search_side_capacity import robustness


def main():
    s=read(OUT/'summary.json');p=s['protocol'];specs={sp['id']:sp for sp in s['specs']}
    assert s['specs']==definitions(read(PRIOR/'summary.json'))
    assert s['selected']==select(s['specs'],s['results'])==read(OUT/'candidate_lock.json')['selected']
    for path,key in [(PRIOR/'summary.json','prior_sha256'),(SIGNALS,'signals_sha256'),(ROOT/'configs/live.yaml','live_config_sha256'),(RULE_PATH,'rules_sha256'),(DATA/'reconciled_manifest.json','data_sha256'),(ROOT/'artifacts/cross_sectional_20260925/signals.json','frozen_weekly_signals_sha256')]:assert sha(path)==p[key]
    for n,d in p['source_sha256'].items():assert sha(ROOT/'scripts'/n)==d
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);all_signals=read(OUT/'signals.json');source=read(SIGNALS)
    origin=source['shock_follow_a15'];fade=source['shock_fade_a15'];state=states(frames)
    weekly=read(ROOT/'artifacts/cross_sectional_20260925/signals.json')
    daily_membership={(e['at'],e['symbol']):e['side'] for e in weekly['momentum_168h_raw']}
    assert len(daily_membership)==len(weekly['momentum_168h_raw'])
    enriched=enrich(frames);ranked,ranks=rank_state(enriched)
    feature_checks=audit_features(frames,enriched)
    rank_checks,weekly_signals_checked=audit_ranks_and_signals(enriched,ranked,ranks,
        [dict(id='momentum_168h_raw')],weekly)
    for coin in enriched:
        pd.testing.assert_frame_equal(state[coin][['eligible','raw168']],enriched[coin][['eligible','raw168']],check_exact=True)
    counts=read(OUT/'gate_counts.json');decisions=read(OUT/'gate_decisions.json')
    assert all_signals['weekly_control']==source['control']
    assert all_signals['follow']==origin and all_signals['fade']==fade
    assert len(origin)==len(fade)==3704
    for a,b in zip(origin,fade):
        assert (a['at'],a['symbol'],a['atr'],a['probability'])==(b['at'],b['symbol'],b['atr'],b['probability'])
        assert a['side']==opposite(b['side'])
    for gate in MODES:
        emitted,count,details=transform(origin,state,gate)
        assert emitted==all_signals[gate] and count==counts[gate] and details==decisions[gate]
        assert not count.get('missing_state') and sum(count.values())==len(origin)
        assert len({e['event_id'] for e in emitted})==len(emitted)
        by_origin={e['origin_event_id']:e for e in emitted}
        assert len(by_origin)==len(emitted)
        for e,record in zip(origin,details):
            day=pd.Timestamp(e['at'],unit='ms',tz='UTC').floor('D')
            at=int(day.timestamp()*1000);h=frames[e['symbol']]
            assert record['snapshot_at']==at and at<=e['at']<at+86400000
            if not bool(enriched[e['symbol']].at[day,'eligible']):
                assert record['reason']=='ineligible' and e['event_id'] not in by_origin
                continue
            assert bool(ranked.at[day,'ready'])
            # Direct return uses 168 completed hourly closes ending at the daily snapshot.
            raw=float(np.log(h.at[day,'close']/h.at[day-pd.Timedelta(hours=168),'close']))
            assert abs(raw-record['raw168'])<1e-12
            daily=daily_membership.get((at,e['symbol']))
            assert record['weekly_side']==daily
            side=(daily if gate.endswith('extreme') else
                  'LONG' if raw>0 else 'SHORT' if raw<0 else None)
            if side is not None and gate.startswith('anti_'):side=opposite(side)
            assert record['selected_side']==side
            if side is None:
                assert record['reason']=='no_direction' and e['event_id'] not in by_origin
            else:
                q=by_origin[e['event_id']]
                assert record['reason']=='accepted' and q['side']==side
                assert (q['at'],q['symbol'],q['atr'],q['probability'])==(e['at'],e['symbol'],e['atr'],e['probability'])
                assert q['event_id']!=e['event_id']
    ids=lambda gate:{e['origin_event_id'] for e in all_signals[gate]}
    assert ids('weekly_sign')==ids('anti_sign')
    assert ids('weekly_extreme')==ids('anti_extreme')
    assert ids('weekly_extreme')<=ids('weekly_sign')
    for first,second in [('weekly_sign','anti_sign'),('weekly_extreme','anti_extreme')]:
        for a,b in zip(all_signals[first],all_signals[second]):
            assert a['origin_event_id']==b['origin_event_id'] and a['side']==opposite(b['side'])
    totals=Counter(independent_signal_sets=4,emissions=sum(len(all_signals[g]) for g in MODES),partition_checks=4,
                   daily_feature_checks=feature_checks,daily_rank_checks=rank_checks,frozen_weekly_events=weekly_signals_checked)
    for index in [500,1800,3000]:
        at=origin[index]['at']+17*60000;t=pd.Timestamp(at,unit='ms',tz='UTC');limited=[e for e in origin if e['at']<=at]
        prefix=states({c:f.loc[:t] for c,f in frames.items()})
        for gate in MODES:
            assert transform(limited,prefix,gate)[0]==[e for e in all_signals[gate] if e['at']<=at]
            totals['causal_prefixes']+=1
    print('DAILY DIRECTION CHOICES AND PREFIXES VERIFIED',flush=True)
    unique={e['event_id']:e for es in all_signals.values() for e in es};failures=[]
    for i,row in enumerate(s['results']):
        sp=specs[row['strategy_id']];_,fee,slip=next(c for c in COSTS if c[0]==row['cost'])
        raw=read(OUT/'runs'/f'{row["id"]}.json');curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet')
        a,b,c=audit_directional(raw,curve,prices,funding,fee,slip,sp['cap'],sp['notional']);n,m,t=audit_exits(raw,curve,prices,sp['policy'],unique,fee,slip)
        checks,denied,cancelled=audit_capital(raw,prices,fee,sp['notional'],rules=rules,slip=slip)
        totals.update(journals=1,funding=a,fills=b,equity_states=c,exit_lifecycles=n,exit_observations=m,capital_checks=checks,capital_denied=denied,cancellations=cancelled)
        assert denied==row['margin_rejections']
        assert row['risk_exits']==sum(j['kind']=='atr_stop' for j in raw['journal'])
        assert row['time_exits']==sum(j['kind']=='time_exit' for j in raw['journal'])
        assert t==row['time_exits']==0
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
            ident=f'hour_n{sp["notional"]}_{"control" if sp["gate"]=="weekly_control" else "shock_fade_a15" if sp["gate"]=="fade" else "shock_follow_a15"}_hold'
            control=PRIOR/'runs'/f'{row["window"]}_{row["cost"]}_{ident}'
            assert raw==read(Path(str(control)+'.json'))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(str(control)+'_equity.parquet'),check_exact=True);totals['baseline_paths_exact']+=1
        if raw['ending_equity'] is None:
            assert raw['stop_event'] and all(e.startswith('maintenance_proxy_breached:') for e in raw['errors'])
            failures.append(dict(id=row['id'],errors=raw['errors'],stop_event=raw['stop_event'],reconstruction=reconstruct(raw,fee,prices)))
        if (i+1)%40==0:print('AUDITED',i+1,flush=True)
    assert totals['baseline_paths_exact']==144 and s['robustness']==robustness(s['results'])
    # Two predefined weekly-sign full-year paths; exact replay.
    for sp in s['specs']:
        if sp['gate']!='weekly_sign':continue
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
        for mode in ['fade',*MODES]:
            for cost in ['base','stress']:
                details=[]
                for window in [w for w in p['windows'] if w.startswith('roll_') or w=='later']:
                    control=lookup[(budget,'follow',window,cost)];candidate=lookup[(budget,mode,window,cost)]
                    a,b=control['ending_equity'],candidate['ending_equity']
                    details.append(dict(window=window,control=a,candidate=b,delta=b-a if a is not None and b is not None else None))
                assert len(details)==10
                deltas=[d['delta'] for d in details if d['delta'] is not None]
                pairs.append(dict(notional=budget,gate=mode,cost=cost,complete_pairs=len(deltas),improved=sum(d>1e-8 for d in deltas),worsened=sum(d< -1e-8 for d in deltas),median_delta=float(np.median(deltas)) if deltas else None,details=details,note='Same originating shocks, finite wallet and execution. Direction choice changes later wallet inventory; whole-account comparison, not isolated per-event causality. Reused overlapping history.'))
    write(OUT/'paired_effect.json',pairs)
    write(OUT/'verification.json',dict(totals=totals,hashes_match=True,live_config_unchanged=True,not_new_holdout=True,financially_verified=False));print('VERIFIED',dict(totals),flush=True)


if __name__=='__main__':main()
