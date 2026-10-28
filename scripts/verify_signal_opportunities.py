"""Reconstruct signed ledgers, trace occupancy and all singleton outcome labels."""
from collections import Counter
from pathlib import Path
import pandas as pd
from account_side_quota_replay import simulate
from diagnose_signal_opportunities import OUT, read, references, outcome, category, statistics, singleton_config
from compare_account_risk import ROOT, sha, write, exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from research_directional_audit import audit_directional
from search_frozen_exits import COSTS, WINDOWS


def verify_trace(raw):
    entries={j['event_id']:j for j in raw['journal'] if j['kind']=='entry'}
    exits={j['event_id']:j['at'] for j in raw['journal'] if 'net' in j}
    admitted=set(); counts=Counter()
    for d in raw['decisions']:
        if d['status']=='not_processed': continue
        active={key for key in admitted if exits.get(key,float('inf'))>d['at']}
        assert active=={o['event_id'] for o in d['occupied']}
        assert d['same_coin']==any(entries[e]['symbol']==d['symbol'] for e in active)
        assert d['full']==(len(active)>=5)
        for o in d['occupied']:
            j=entries[o['event_id']]
            assert (o['symbol'],o['side'],o['opened_at'])==(j['symbol'],j['side'],j['at'])
            assert o['held_days']==(d['at']-j['at'])/86400000
        if d['status']=='accepted':
            assert d['event_id'] in entries and entries[d['event_id']]['at']==d['at']
            assert not d['same_coin'] and not d['full'] and not d['paused']
            admitted.add(d['event_id'])
        elif d['status']=='rejected':
            counts[d['reason']]+=1
            if d['reason']=='position_limit': assert d['same_coin'] or d['full']
            if d['reason']=='drawdown_paused': assert d['paused']
    assert admitted==set(entries)
    assert counts=={k:v for k,v in raw['rejections'].items() if not k.startswith('add_')}
    return len(raw['decisions'])


def actual_outcomes(raw, fee):
    result={j['event_id']:dict(net_mtm=j['net'],state='closed',filled_parts=j['filled_parts']) for j in raw['journal'] if 'net' in j}
    for p in raw['open_positions']:
        result[p['event_id']]=dict(net_mtm=p['unrealized']-p['entry_fee']+p['funding'],state='open',filled_parts=p['filled_parts'])
    assert abs(sum(r['net_mtm'] for r in result.values())-raw['pnl'])<1e-6
    return result


def main():
    s=read(OUT/'summary.json'); p=s['protocol']; events=read(OUT/'events.json'); rows=read(OUT/'outcomes.json')
    for rel,digest in p['input_sha256'].items(): assert sha(ROOT/rel)==digest
    for n,digest in p['source_sha256'].items(): assert sha(ROOT/'scripts'/n)==digest
    assert sha(ROOT/'configs/live.yaml')==p['live_config_sha256']
    refs,source=references(); start,end=WINDOWS['year']
    assert events==sorted([e for e in source if start<=e['at']<end],key=lambda e:(e['at'],e['event_id']))
    assert len(rows)==2*len(events) and len({(r['event_id'],r['cost']) for r in rows})==len(rows)
    prices,funding,_=load(); rules=exchange_rules(RULE_PATH)
    totals=Counter(); comparisons=[]; lookup={(r['event_id'],r['cost']):r for r in rows}
    for pr in s['portfolios']:
        raw=read(OUT/'portfolios'/f'{pr["id"]}.json'); curve=pd.read_parquet(OUT/'portfolios'/f'{pr["id"]}_equity.parquet')
        ref=next(r for r in refs if r['id']==pr['strategy']); parent=Path(ref['parent'])/'runs'/f'{pr["window"]}_{pr["cost"]}_{ref["baseline"]}'
        assert {k:v for k,v in raw.items() if k!='decisions'}==read(parent.with_suffix('.json'))
        pd.testing.assert_frame_equal(curve,pd.read_parquet(str(parent)+'_equity.parquet'),check_exact=True)
        totals['exact_controls']+=1; totals['decisions']+=verify_trace(raw)
        lo,hi=p['windows'][pr['window']]
        expected=[(t,i,e['event_id']) for t,b in __import__('search_multitimeframe_rolling').grouped_signals(ref['signals'],lo,hi).items() for i,e in enumerate(b)]
        assert sorted(expected)==sorted((d['at'],d['signal_index'],d['event_id']) for d in raw['decisions'])
        _,fee,slip=next(c for c in COSTS if c[0]==pr['cost'])
        a,b,c=audit_directional(raw,curve,prices,funding,fee,slip,5)
        totals.update(journals=1,funding=a,fills=b,states=c)
        actual=actual_outcomes(raw,fee)
        comparisons.append(dict(portfolio=pr['id'],accepted=len(actual),
            different_net=sum(abs(v['net_mtm']-lookup[(key,pr['cost'])]['net_mtm'])>1e-7 for key,v in actual.items()),
            different_parts=sum(v['filled_parts']!=lookup[(key,pr['cost'])]['filled_parts'] for key,v in actual.items())))
        assert pr['admission_counts']==dict(Counter(category(d) for d in raw['decisions']))
    for i,e in enumerate(events):
        for cost,fee,slip in COSTS:
            key=f'{i:04d}_{cost}'; raw=read(OUT/'singletons'/f'{key}.json'); curve=pd.read_parquet(OUT/'singletons'/f'{key}_equity.parquet')
            assert raw['max_positions']==1 and curve.positions.max()<=1
            assert curve['at'].iloc[0]==e['at'] and (raw['ending_equity'] is None or curve['at'].iloc[-1]==end)
            a,b,c=audit_directional(raw,curve,{e['symbol']:prices[e['symbol']]},{e['symbol']:funding[e['symbol']]},fee,slip,1)
            totals.update(journals=1,funding=a,fills=b,states=c)
            assert lookup[(e['event_id'],cost)]==dict(id=key,cost=cost,**outcome(dict(raw,curve=curve.to_dict('records')),e,end))
        if (i+1)%100==0: print('AUDITED',i+1,flush=True)
    # Independently regenerate report grouping from all saved decisions and outcomes.
    for g in s['groups']:
        pr=next(r for r in s['portfolios'] if r['id']==g['portfolio'])
        ds=[d for d in read(OUT/'portfolios'/f'{pr["id"]}.json')['decisions'] if d['side']==g['side'] and category(d)==g['category']]
        assert all(g[k]==v for k,v in statistics([lookup[(d['event_id'],pr['cost'])] for d in ds]).items())
    for cost,_,_ in COSTS:
        for side in ['LONG','SHORT']:
            g=next(r for r in s['isolated'] if r['cost']==cost and r['side']==side)
            assert all(g[k]==v for k,v in statistics([r for r in rows if r['cost']==cost and r['side']==side]).items())
    # Predefined reproducibility sample: first/last Long/Short at both cost settings.
    indexes=sorted({next(i for i,e in enumerate(events) if e['side']==side) for side in ['LONG','SHORT']} |
        {max(i for i,e in enumerate(events) if e['side']==side) for side in ['LONG','SHORT']})
    for i in indexes:
        e=events[i]
        for cost,fee,slip in COSTS:
            r=simulate(list(range(e['at'],end+1,300000)),{e['at']:[e]},lambda c:prices.get(c,{}),rules,lambda c:funding[c],singleton_config(fee,slip),research_policy=p['policy'])
            key=f'{i:04d}_{cost}'
            assert {k:v for k,v in r.items() if k!='curve'}==read(OUT/'singletons'/f'{key}.json')
            pd.testing.assert_frame_equal(pd.DataFrame(r['curve']),pd.read_parquet(OUT/'singletons'/f'{key}_equity.parquet'),check_exact=True)
            totals['replayed_singletons']+=1
    assert {k:totals[k] for k in s['audits']}==s['audits']
    write(OUT/'verification.json',dict(totals=totals,accepted_vs_isolated=comparisons,hashes_match=True,
        live_config_unchanged=True,independent_wallets_not_additive=True,not_independent_holdout=True))
    print('VERIFIED',dict(totals),flush=True)


if __name__=='__main__': main()
