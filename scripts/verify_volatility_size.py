"""Full committed-capital, fill, funding and marked wallet audits of scale variants."""
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
from account_volatility_replay import simulate
from volatility_position_size import financial_view
from cross_sectional_audit import audit_exits
from volatility_capital_audit import audit as audit_capital
from cross_halt_audit import reconstruct
from volatility_account_audit import audit_directional
from compare_account_risk import ROOT,sha,write,exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from directional_capacity_metrics import side_metrics
from monthly_account_metrics import monthly_metrics
from search_volatility_size import OUT,PRIOR,TIMING_PRIOR,SIGNALS,read,definitions,select,BOUNDARIES,COSTS,DATA
from search_multitimeframe_rolling import grouped_signals
from search_side_capacity import robustness


def main():
    s=read(OUT/'summary.json');p=s['protocol'];specs={sp['id']:sp for sp in s['specs']}
    assert s['specs']==definitions(read(PRIOR/'summary.json'))
    assert s['selected']==select(s['specs'],s['results'])==read(OUT/'candidate_lock.json')['selected']
    for path,key in [(PRIOR/'summary.json','prior_sha256'),(SIGNALS,'signals_sha256'),(ROOT/'configs/live.yaml','live_config_sha256'),(RULE_PATH,'rules_sha256'),(DATA/'reconciled_manifest.json','data_sha256')]:assert sha(path)==p[key]
    for n,d in p['source_sha256'].items():assert sha(ROOT/'scripts'/n)==d
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);all_signals=read(OUT/'signals.json');source=read(SIGNALS)
    for sp in s['specs']:
        signals=all_signals[sp['sizing_key']];assert len(signals)==len(source)
        for e,o in zip(signals,source):
            assert {k:v for k,v in e.items() if k!='planned_notional'}==o
            origin=pd.Timestamp(o['source_at'],unit='ms',tz='UTC')
            assert abs(frames[o['symbol']].at[origin,'close']-o['reference_close'])<1e-10
            expected=sp['amount'] if sp['sizing']=='fixed' else max(25,min(250,sp['amount']*o['reference_close']/o['atr']))
            assert abs(expected-e['planned_notional'])<1e-10
        assert len({e['event_id'] for e in signals})==len(signals)
    totals=Counter()
    failures=[]
    for i,row in enumerate(s['results']):
        sp=specs[row['strategy_id']];_,fee,slip=next(c for c in COSTS if c[0]==row['cost'])
        signals=all_signals[sp['sizing_key']];unique={e['event_id']:e for e in signals};budgets={e['event_id']:e['planned_notional'] for e in signals}
        raw=read(OUT/'runs'/f'{row["id"]}.json');curve=pd.read_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet')
        a,b,c=audit_directional(raw,curve,prices,funding,fee,slip,sp['cap'],budgets);n,m,t=audit_exits(raw,curve,prices,sp['policy'],unique,fee,slip)
        checks,denied,cancelled=audit_capital(raw,prices,fee,budgets,rules=rules,slip=slip)
        totals.update(journals=1,funding=a,fills=b,equity_states=c,exit_lifecycles=n,exit_observations=m,capital_checks=checks,capital_denied=denied,cancellations=cancelled)
        assert denied==row['margin_rejections']
        admitted={j['event_id'] for j in raw['journal'] if j['kind']=='entry'}
        amounts=[e['planned_notional'] for e in signals if e['event_id'] in admitted]
        atr_values=[e['planned_notional']*e['atr']/e['reference_close'] for e in signals if e['event_id'] in admitted]
        assert row['sizing_metrics']==dict(mean_budget=sum(amounts)/len(amounts) if amounts else None,min_budget=min(amounts,default=None),max_budget=max(amounts,default=None),mean_origin_atr_dollars=sum(atr_values)/len(atr_values) if atr_values else None,floor_entries=sum(a==25 for a in amounts),cap_entries=sum(a==250 for a in amounts))
        for pos in raw['open_positions']:assert pos['planned_notional']==budgets[pos['event_id']]
        assert row['side_metrics']==side_metrics(raw,curve)
        start,end=p['windows'][row['window']]
        assert row['monthly']==monthly_metrics(curve.to_dict('records'),boundaries=[t for t in BOUNDARIES if start<=t<=end])
        assert row['ending_equity']==raw['ending_equity'] and row['target_met']==(raw['ending_equity'] is not None and row['monthly']['all_months_50pct'])
        if sp['baseline']:
            ident=f'pull05_cap{sp["cap"]}_n{sp["notional"]}'
            control=PRIOR/'runs'/f'{row["window"]}_{row["cost"]}_{ident}'
            assert financial_view(raw)==read(Path(str(control)+'.json'))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(str(control)+'_equity.parquet'),check_exact=True);totals['baseline_paths_exact']+=1
        if raw['ending_equity'] is None:
            assert raw['stop_event'] and all(e.startswith('maintenance_proxy_breached:') for e in raw['errors'])
            failures.append(dict(id=row['id'],errors=raw['errors'],stop_event=raw['stop_event'],reconstruction=reconstruct(raw,fee,prices)))
        if (i+1)%40==0:print('AUDITED',i+1,flush=True)
    assert totals['baseline_paths_exact']==96 and s['robustness']==robustness(s['results'])
    # Independent repeat of the two highest ATR-dollar full-year base paths.
    for sp in s['specs']:
        if sp['sizing']!='atr_dollar' or sp['amount']!=5:continue
        signals=all_signals[sp['sizing_key']]
        start,end=p['windows']['year'];cost,fee,slip=COSTS[0]
        r=simulate(list(range(start,end+1,300000)),grouped_signals([e for e in signals if e.get('source_at',e['at'])>=start],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(sp['cap'],fee,slip),research_policy=sp['policy'])
        r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct';key=f'year_{cost}_{sp["id"]}'
        assert {k:v for k,v in r.items() if k!='curve'}==read(OUT/'runs'/f'{key}.json')
        pd.testing.assert_frame_equal(pd.DataFrame(r['curve']),pd.read_parquet(OUT/'runs'/f'{key}_equity.parquet'),check_exact=True);totals['replayed_paths_exact']+=1
    assert len(s['results'])==240 and len(failures)==s['incomplete_paths']
    assert len({r['id'] for r in s['results']})==240
    assert s['target_met_rows']==sum(r['target_met'] for r in s['results'])
    write(OUT/'incomplete_paths.json',failures)
    write(OUT/'verification.json',dict(totals=totals,hashes_match=True,live_config_unchanged=True,not_new_holdout=True,financially_verified=False));print('VERIFIED',dict(totals),flush=True)


if __name__=='__main__':main()
