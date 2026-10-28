"""Batch23: admission tracing and isolated Long/Short staged/trailing lifecycles.

Independent 500-USDT hypothetical wallets are diagnostics, never a portfolio.
Every frozen event is retained, including invalid orders and censored inventory.
"""
import json
from collections import Counter
import pandas as pd
from account_trace_replay import simulate as trace
from account_side_quota_replay import simulate
from compare_account_risk import ROOT, sha, write, exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from research_directional_audit import audit_directional
from search_frozen_exits import WINDOWS, COSTS
from search_multitimeframe_rolling import grouped_signals

OUT = ROOT / 'artifacts/signal_opportunities_20260925'
REV = ROOT / 'artifacts/directional_reversal_20260925'
RANK = ROOT / 'artifacts/signal_priority_20260925'


def read(p): return json.loads(p.read_text(encoding='utf-8'))


def singleton_config(fee, slip):
    config = configuration(5, fee, slip)
    config.max_open_positions = 1
    return config


def references():
    rev, rank = read(REV/'summary.json'), read(RANK/'summary.json')
    sig_rev, sig_rank = read(REV/'signals.json'), read(RANK/'signals.json')
    refs = []
    for side in ['short', 'long', 'both']:
        key = f'{side}_mask2_n25_hold_cap5'
        sp = next(s for s in rev['specs'] if s['id'] == key)
        refs.append(dict(id=side, parent=str(REV), baseline=key, policy=sp['policy'], signals=sig_rev[f'{side}_mask2']))
    sp = next(s for s in rank['specs'] if s['id'] == 'impulse_atr_cap5')
    refs.append(dict(id='short_impulse', parent=str(RANK), baseline=sp['id'], policy=sp['policy'], signals=sig_rank['impulse_atr']))
    # Singleton priority cannot matter; all references share identical economics.
    assert all(r['policy'] == refs[0]['policy'] for r in refs)
    return refs, sig_rev['both_mask2']


def outcome(raw, event, end):
    exits = [j for j in raw['journal'] if 'net' in j]
    entries = [j for j in raw['journal'] if j['kind'] == 'entry']
    assert len(entries) <= 1 and len(exits) <= 1 and len(raw['open_positions']) <= 1
    state = 'incomplete' if raw['ending_equity'] is None else 'closed' if exits else 'open' if entries else 'not_entered'
    until = exits[0]['at'] if exits else raw['curve'][-1]['at'] if raw['curve'] else event['at']
    return dict(event_id=event['event_id'], symbol=event['symbol'], side=event['side'], at=event['at'],
        state=state, net_mtm=raw['pnl'] if entries and state != 'incomplete' else None,
        closed_net=exits[0]['net'] if exits else None, held_days=(until-event['at'])/86400000 if entries else None,
        observation_days=(end-event['at'])/86400000, fees=raw['fees'], funding=raw['funding'],
        filled_parts=sum(j['kind'] in ['entry', 'entry_add'] for j in raw['journal']),
        max_account_drawdown=raw['sampled_max_drawdown'], paused=raw['entry_paused'],
        rejections=raw['rejections'], errors=raw['errors'])


def category(d):
    if d['status'] != 'rejected': return d['status']
    if d['reason'] == 'position_limit': return 'same_coin' if d['same_coin'] else 'full_capacity'
    return d['reason']


def statistics(rows):
    valid = [r for r in rows if r['net_mtm'] is not None]
    net = pd.Series([r['net_mtm'] for r in valid], dtype=float)
    return dict(events=len(rows), states=dict(Counter(r['state'] for r in rows)),
        evaluated_entries=len(valid), positive_mtm=sum(v > 0 for v in net),
        mean_net_usdt=float(net.mean()) if len(net) else None,
        median_net_usdt=float(net.median()) if len(net) else None,
        p05_net_usdt=float(net.quantile(.05)) if len(net) else None,
        worst_net_usdt=float(net.min()) if len(net) else None,
        median_held_days=float(pd.Series([r['held_days'] for r in valid]).median()) if valid else None,
        open_over30days=sum(r['state']=='open' and r['held_days']>30 for r in rows),
        note='Per-event descriptive outcomes in independent wallets; overlapping/dependent, not account PnL.')


def main():
    OUT.mkdir(exist_ok=True)
    for folder in ['portfolios', 'singletons']: (OUT/folder).mkdir(exist_ok=True)
    refs, events = references(); start, end = WINDOWS['year']
    events = sorted([e for e in events if start <= e['at'] < end], key=lambda e:(e['at'],e['event_id']))
    assert len({e['event_id'] for e in events}) == len(events)
    protocol = dict(created_at=pd.Timestamp.now(tz='UTC').isoformat(),
        question='Do Long/Short entry lifecycles fail individually, or does finite capacity block later opportunities?',
        intervention='Observation only: 4 already-frozen portfolios, year/later x base/stress; exact prior parity. No new strategy selected.',
        singleton='Each frozen reversal mask2 event in Sep2025-Sep2026 gets an independent 500USDT wallet, one25USDT position, same3favorable parts,trail3ATR/1%,DDpause,noSL. Run from event toSep1,2026,or retain unknown if errors. No forced terminal exits. Fee/funding/Mark included. Never sum independent wallets as a tradable portfolio.',
        attribution='Trace before each admission including prior same-time accepted events. Same-coin priority over full-capacity for exclusive categories; flags retain both. No retry/resurrection of rejected events. Ineligible standalone entries counted separately.',
        limitations='Retrospective diagnostic, not OOS. Unequal follow-up/right censoring; overlapping dependent signals; admitted and blocked samples differ by date/coin. Singleton shared-DD and tranche cancellation may differ from real portfolio. Current exchange filters, 1% maintenance proxy rather than verified historical brackets. Fixed universe can have survival bias. No profit guarantee or live promotion.',
        policy=refs[0]['policy'], windows={k:WINDOWS[k] for k in ['year','later']}, costs=COSTS,
        singleton_events=len(events), sides=dict(Counter(e['side'] for e in events)),
        target='50%netMTM in every consecutive month; isolated events cannot establish this.',
        input_sha256={str(p.relative_to(ROOT)):sha(p) for p in [REV/'signals.json',REV/'summary.json',RANK/'signals.json',RANK/'summary.json',RULE_PATH,ROOT/'artifacts/frozen_extension_20260925/reconciled_manifest.json']},
        source_sha256={n:sha(ROOT/'scripts'/n) for n in ['account_trace_replay.py','account_side_quota_replay.py','diagnose_signal_opportunities.py','research_directional_audit.py','frozen_extension_inputs.py']},
        live_config_sha256=sha(ROOT/'configs/live.yaml'))
    write(OUT/'protocol.json',protocol); write(OUT/'events.json',events)
    prices, funding, _ = load(); rules = exchange_rules(RULE_PATH)
    portfolios=[]; audits=dict(journals=0,funding=0,fills=0,states=0)
    def save_audit(raw, folder, key, fee, slip, coin=None):
        curve=pd.DataFrame(raw['curve'])
        a,b,c=audit_directional(raw,curve,prices if coin is None else {coin:prices[coin]},
            funding if coin is None else {coin:funding[coin]},fee,slip,5 if coin is None else 1)
        audits['journals']+=1; audits['funding']+=a; audits['fills']+=b; audits['states']+=c
        write(OUT/folder/f'{key}.json',{k:v for k,v in raw.items() if k!='curve'})
        curve.to_parquet(OUT/folder/f'{key}_equity.parquet',index=False)
    for ref in refs:
        parent=read(__import__('pathlib').Path(ref['parent'])/'summary.json')
        for window,(lo,hi) in protocol['windows'].items():
            for cost,fee,slip in COSTS:
                key=f'{window}_{cost}_{ref["id"]}'
                raw=trace(list(range(lo,hi+1,300000)),grouped_signals(ref['signals'],lo,hi),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(5,fee,slip),research_policy=ref['policy'])
                raw['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct'
                original=read(__import__('pathlib').Path(ref['parent'])/'runs'/f'{window}_{cost}_{ref["baseline"]}.json')
                assert {k:v for k,v in raw.items() if k not in ['decisions','curve']} == original
                pd.testing.assert_frame_equal(pd.DataFrame(raw['curve']),pd.read_parquet(__import__('pathlib').Path(ref['parent'])/'runs'/f'{window}_{cost}_{ref["baseline"]}_equity.parquet'),check_exact=True)
                save_audit(raw,'portfolios',key,fee,slip)
                prior=next(r for r in parent['results'] if r['strategy_id']==ref['baseline'] and r['window']==window and r['cost']==cost)
                portfolios.append(dict(id=key,strategy=ref['id'],window=window,cost=cost,ending_equity=raw['ending_equity'],
                    entries=raw['entries'],open_positions=len(raw['open_positions']),max_drawdown=raw['sampled_max_drawdown'],monthly=prior['monthly'],
                    target_met=prior['target_met'],decisions=len(raw['decisions']),admission_counts=dict(Counter(category(d) for d in raw['decisions']))))
        print('PORTFOLIO',ref['id'],flush=True)
    rows=[]
    for i,event in enumerate(events):
        for cost,fee,slip in COSTS:
            key=f'{i:04d}_{cost}'
            raw=simulate(list(range(event['at'],end+1,300000)),{event['at']:[event]},lambda c:prices.get(c,{}),rules,lambda c:funding[c],singleton_config(fee,slip),research_policy=protocol['policy'])
            save_audit(raw,'singletons',key,fee,slip,event['symbol'])
            rows.append(dict(id=key,cost=cost,**outcome(raw,event,end)))
        if (i+1)%25==0:
            write(OUT/'progress.json',dict(events_done=i+1,total=len(events),audits=audits))
            print('EVENTS',i+1,'/',len(events),flush=True)
    write(OUT/'outcomes.json',rows); pd.DataFrame(rows).to_csv(OUT/'outcomes.csv',index=False)
    lookup={(r['event_id'],r['cost']):r for r in rows}; groups=[]
    for p in portfolios:
        raw=read(OUT/'portfolios'/f'{p["id"]}.json')
        for side in ['LONG','SHORT']:
            ds=[d for d in raw['decisions'] if d['side']==side]
            for cat in sorted({category(d) for d in ds}):
                selected=[d for d in ds if category(d)==cat]
                groups.append(dict(portfolio=p['id'],side=side,category=cat,**statistics([lookup[(d['event_id'],p['cost'])] for d in selected]),
                    snapshot_any_losing_position=sum(any(o['net_mark']<0 for o in d.get('occupied',[])) for d in selected),
                    snapshot_any_loser_older30d=sum(any(o['net_mark']<0 and o['held_days']>30 for o in d.get('occupied',[])) for d in selected)))
    overall=[dict(cost=c,side=side,**statistics([r for r in rows if r['cost']==c and r['side']==side])) for c,_,_ in COSTS for side in ['LONG','SHORT']]
    assert sha(ROOT/'configs/live.yaml')==protocol['live_config_sha256']
    write(OUT/'summary.json',dict(protocol=protocol,portfolios=portfolios,groups=groups,isolated=overall,audits=audits,
        exact_historical_controls=len(portfolios),financially_verified=False,promotion_eligible=False))
    print('COMPLETE',audits,flush=True)


if __name__=='__main__': main()
