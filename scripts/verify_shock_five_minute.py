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
from shock_five_minute_entry import transform,MODES
from shock_five_minute_oracle import expected
from types import SimpleNamespace
from search_shock_five_minute import OUT,PRIOR,TIMING_PRIOR,SIGNALS,read,definitions,select,BOUNDARIES,COSTS,DATA,SOURCES
from search_multitimeframe_rolling import grouped_signals
from search_side_capacity import robustness


def main():
    s=read(OUT/'summary.json');p=s['protocol'];specs={sp['id']:sp for sp in s['specs']}
    assert s['specs']==definitions(read(PRIOR/'summary.json'))
    assert s['selected']==select(s['specs'],s['results'])==read(OUT/'candidate_lock.json')['selected']
    for path,key in [(PRIOR/'summary.json','prior_sha256'),(SIGNALS,'signals_sha256'),(ROOT/'configs/live.yaml','live_config_sha256'),(RULE_PATH,'rules_sha256'),(DATA/'reconciled_manifest.json','data_sha256')]:assert sha(path)==p[key]
    for n,d in p['source_sha256'].items():assert sha(ROOT/'scripts'/n)==d
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);all_signals=read(OUT/'signals.json');source=read(SIGNALS)
    origin=read(OUT/'origin_signals.json');assert origin==source['shock_follow_a15']
    assert all_signals['weekly_control']==source['control']
    counts=read(OUT/'timing_counts.json');details=read(OUT/'timing_diagnostics.json')
    for mode in MODES:
        assert expected(origin,prices,mode)==all_signals[mode]
        emitted,count,records=transform(origin,prices,mode)
        assert (emitted,count,records)==(all_signals[mode],counts[mode],details[mode])
        assert not count.get('data_error') and not count.get('right_censored') and sum(count.values())==len(origin)
        assert len({e['event_id'] for e in emitted})==len(emitted)
    totals=Counter(independent_signal_sets=5,emissions=sum(len(es) for es in all_signals.values()))
    for index in [500,1800,3000]:
        at=origin[index]['at']+17*60000
        prefix_prices={c:SimpleNamespace(trade_times=q.trade_times[q.trade_times<=at-300000],closes=q.closes[q.trade_times<=at-300000]) for c,q in prices.items()}
        limited=[e for e in origin if e['at']<=at]
        for mode in MODES:
            emitted=transform(origin,prices,mode,asof=at)[0]
            prefix=transform(limited,prefix_prices,mode)[0]
            assert emitted==prefix==[e for e in all_signals[mode] if e['at']<=at]
            totals['causal_prefixes']+=1
    print('FIRST PASSAGE AND TRUNCATED FIVE MINUTE PREFIXES VERIFIED',flush=True)
    unique={e['event_id']:e for es in all_signals.values() for e in es};failures=[];entry_timing={}
    for i,row in enumerate(s['results']):
        sp=specs[row['strategy_id']];_,fee,slip=next(c for c in COSTS if c[0]==row['cost'])
        raw=read(OUT/'runs'/f'{row["id"]}.json');curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet')
        a,b,c=audit_directional(raw,curve,prices,funding,fee,slip,sp['cap'],sp['notional']);n,m,t=audit_exits(raw,curve,prices,sp['policy'],unique,fee,slip)
        checks,denied,cancelled=audit_capital(raw,prices,fee,sp['notional'],rules=rules,slip=slip)
        totals.update(journals=1,funding=a,fills=b,equity_states=c,exit_lifecycles=n,exit_observations=m,capital_checks=checks,capital_denied=denied,cancellations=cancelled)
        assert denied==row['margin_rejections']
        assert row['risk_exits']==t==sum(j['kind']=='atr_stop' for j in raw['journal'])
        assert row['time_exits']==sum(j['kind']=='time_exit' for j in raw['journal'])
        totals.update(risk_exits=t,time_exits=row['time_exits'])
        assert row['side_metrics']==side_metrics(raw,curve)
        start,end=p['windows'][row['window']]
        candidates={e['event_id']:e for e in all_signals[sp['gate']] if start<=e.get('source_at',e['at']) and e['at']<end}
        assert len(candidates)==row['candidates']
        entry_observations=[]
        for j in raw['journal']:
            if j['kind']=='entry':
                e=candidates[j['event_id']];assert (j['at'],j['symbol'],j['side'])==(e['at'],e['symbol'],e['side'])
                origin_at=e.get('source_at',e['at']);direction=1 if e['side']=='LONG' else -1
                q=prices[e['symbol']];ix=np.searchsorted(q.trade_times,origin_at-300000)
                assert q.trade_times[ix]==origin_at-300000
                reference=float(q.closes[ix]);observed=float(e.get('trigger_close',reference))
                if 'reference_close' in e:assert abs(reference-e['reference_close'])<1e-10
                entry_observations.append(dict(event_id=e['event_id'],at=j['at'],wait_minutes=(j['at']-origin_at)/60000,
                    observed_favorable_atr=-direction*(observed-reference)/e['atr'],
                    filled_favorable_atr=-direction*(j['price']-reference)/e['atr']))
                totals['executed_candidates']+=1
        entry_timing[row['id']]=dict(entries=len(entry_observations),
            median_wait_minutes=float(np.median([e['wait_minutes'] for e in entry_observations])) if entry_observations else None,
            median_observed_favorable_atr=float(np.median([e['observed_favorable_atr'] for e in entry_observations])) if entry_observations else None,
            median_filled_favorable_atr=float(np.median([e['filled_favorable_atr'] for e in entry_observations])) if entry_observations else None,
            favorable_fills=sum(e['filled_favorable_atr']>0 for e in entry_observations),observations=entry_observations,
            note='First actual fills relative to origin close in frozen ATR units; positive is favorable for either side. Admitted events differ, so this is descriptive and does not isolate timing causality.')
        assert row['monthly']==monthly_metrics(curve.to_dict('records'),boundaries=[t for t in BOUNDARIES if start<=t<=end])
        assert row['ending_equity']==raw['ending_equity'] and row['target_met']==(raw['ending_equity'] is not None and row['monthly']['all_months_50pct'])
        if sp['baseline']:
            ident=f'hour_n{sp["notional"]}_{"control" if sp["gate"]=="weekly_control" else "shock_follow_a15"}_hold'
            control=PRIOR/'runs'/f'{row["window"]}_{row["cost"]}_{ident}'
            assert raw==read(Path(str(control)+'.json'))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(str(control)+'_equity.parquet'),check_exact=True);totals['baseline_paths_exact']+=1
        if raw['ending_equity'] is None:
            assert raw['stop_event'] and all(e.startswith('maintenance_proxy_breached:') for e in raw['errors'])
            failures.append(dict(id=row['id'],errors=raw['errors'],stop_event=raw['stop_event'],reconstruction=reconstruct(raw,fee,prices)))
        if (i+1)%40==0:print('AUDITED',i+1,flush=True)
    assert totals['baseline_paths_exact']==96 and s['robustness']==robustness(s['results'])
    # Two predefined five-minute retest full-year paths; exact replay.
    for sp in s['specs']:
        if sp['gate']!='retest50':continue
        signals=all_signals[sp['gate']]
        start,end=p['windows']['year'];cost,fee,slip=COSTS[0]
        r=simulate(list(range(start,end+1,300000)),grouped_signals([e for e in signals if e.get('source_at',e['at'])>=start],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(sp['cap'],fee,slip),research_policy=sp['policy'])
        r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct';key=f'year_{cost}_{sp["id"]}'
        assert {k:v for k,v in r.items() if k!='curve'}==read(OUT/'runs'/f'{key}.json')
        pd.testing.assert_frame_equal(pd.DataFrame(r['curve']),pd.read_parquet(OUT/'runs'/f'{key}_equity.parquet'),check_exact=True);totals['replayed_paths_exact']+=1
    assert len(s['results'])==288 and len({r['id'] for r in s['results']})==288
    assert s['target_met_rows']==sum(r['target_met'] for r in s['results'])
    assert len(failures)==s['incomplete_paths'];write(OUT/'incomplete_paths.json',failures)
    pairs=[]
    lookup={(r['notional'],r['gate'],r['window'],r['cost']):r for r in s['results']}
    for budget in [25,100]:
        for mode in ['pull25','pull50','retest50','break25']:
            for cost in ['base','stress']:
                details=[]
                for window in [w for w in p['windows'] if w.startswith('roll_') or w=='later']:
                    control=lookup[(budget,'immediate',window,cost)];candidate=lookup[(budget,mode,window,cost)]
                    a,b=control['ending_equity'],candidate['ending_equity']
                    details.append(dict(window=window,control=a,candidate=b,delta=b-a if a is not None and b is not None else None))
                assert len(details)==10
                deltas=[d['delta'] for d in details if d['delta'] is not None]
                pairs.append(dict(notional=budget,gate=mode,cost=cost,complete_pairs=len(deltas),improved=sum(d>1e-8 for d in deltas),worsened=sum(d< -1e-8 for d in deltas),median_delta=float(np.median(deltas)) if deltas else None,details=details,note='Same finite wallet and frozen originating shocks. Delay changes timing, eligibility and admitted inventory; whole-account comparison, not isolated fill improvement. Reused overlapping history.'))
    write(OUT/'paired_effect.json',pairs);write(OUT/'entry_timing_metrics.json',entry_timing)
    write(OUT/'verification.json',dict(totals=totals,hashes_match=True,live_config_unchanged=True,not_new_holdout=True,financially_verified=False));print('VERIFIED',dict(totals),flush=True)


if __name__=='__main__':main()
