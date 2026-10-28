"""Prospective paper observer. Public market data only; no order client."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sys
import shutil
import time
import xml.etree.ElementTree as ET

import pandas as pd
import paper_data_v1 as d
from paper_state_v1 import Journal, new_state, step, held_symbols, engine_clock
import paper_state_v1 as store_module
import signal_snapshot_v423 as signals
from decision_feed_v425 import DecisionFeed
from research_v408 import FAMILY


def source_paths():
    previous = d.read(d.ROOT/'artifacts/fibo_trend_short/research_v4_0_25/CHECKPOINT.json')
    paths = [d.ROOT/p for p in previous['additional_sources']]
    paths += [Path(__file__), Path(d.__file__), Path(store_module.__file__),
              d.ROOT/'scripts/fibo_research/prepare_paper_v1.py',
              d.ROOT/'scripts/fibo_research/preflight_paper_v1.py',
              d.ROOT/'scripts/fibo_research/start_paper_v1.ps1',
              d.ROOT/'tests/unit/fibo_short/test_paper_data_v1.py',
              d.ROOT/'tests/unit/fibo_short/test_paper_state_v1.py']
    for module in list(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.suffix == '.py' and (path.is_relative_to(d.ROOT/'src') or path.is_relative_to(d.ROOT/'scripts/fibo_research')):
                paths.append(path)
    return sorted(set(paths))


def environment():
    return {'python': sys.version, **{name: importlib.metadata.version(name) for name in ('numpy','pandas','requests','pydantic')}}


def capture_lineage(symbol):
    """Archive incremental source lineage without duplicating full H1 files."""
    meta_path = d.ART/'hourly'/f'{symbol}.json'; meta = d.read(meta_path)
    folder = d.ART/'hourly_lineage'/symbol; head_path = folder/'HEAD.json'
    head = d.read(head_path) if head_path.exists() else None
    digest = d.sha(meta_path); previous_count = 0
    if head:
        if d.sha(head['path']) != head['sha256']: raise RuntimeError('Hourly lineage changed')
        previous = d.read(head['path'])
        if previous['metadata_sha256'] == digest: return head
        previous_count = previous['source_count']
        prefix = json.dumps(meta['sources'][:previous_count], sort_keys=True, separators=(',', ':')).encode()
        if hashlib.sha256(prefix).hexdigest() != previous['sources_sha256']:
            raise RuntimeError('Hourly source history was rewritten')
    payload = {'symbol': symbol, 'metadata_sha256': digest,
        'metadata_without_sources': {k: v for k, v in meta.items() if k != 'sources'},
        'source_count': len(meta['sources']),
        'sources_sha256': hashlib.sha256(json.dumps(meta['sources'], sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'new_sources': meta['sources'][previous_count:], 'previous': head}
    path = folder/f'{meta["cutoff_ms"]}_{digest[:16]}.json'
    if path.exists():
        if d.read(path) != payload: raise RuntimeError('Conflicting immutable hourly lineage')
    else: d.save(path, payload)
    head = {'path': str(path), 'sha256': d.sha(path)}; d.save(head_path, head)
    return head


def protocol():
    path = d.ART/'PROTOCOL.json'; p = d.read(path)
    for file, digest in p['sources'].items():
        if d.sha(file) != digest: raise RuntimeError('Frozen paper source changed: '+file)
    if p['environment'] != environment(): raise RuntimeError('Frozen paper runtime dependencies changed')
    p['protocol_sha256'] = d.sha(path)
    return p


def activate():
    if (d.ART/'PROTOCOL.json').exists(): raise FileExistsError('Paper protocol is already locked')
    ready = d.read(d.ART/'PREPARATION_COMPLETE.json'); assert ready['all_passed']
    preflight = d.read(d.ART/'PREFLIGHT.json'); assert preflight['all_passed'] and preflight['scored_trades'] == 0
    for xml in ('ALL_TESTS.xml',):
        suites = list(ET.parse(d.ART/xml).getroot().iter('testsuite'))
        assert sum(int(s.get('tests', 0)) for s in suites) >= 14
        assert not sum(int(s.get(k, 0)) for s in suites for k in ('errors', 'failures', 'skipped'))
    offset, clock = d.server_clock(); now = d.now_ms()+offset
    start = ((now+5*60_000+d.HOUR-1)//d.HOUR)*d.HOUR
    first_monday = d.utc(start).normalize()
    if first_monday.weekday() != 0: first_monday += pd.Timedelta(days=7-first_monday.weekday())
    elif first_monday < d.utc(start): first_monday += pd.Timedelta(days=7)
    end = int((first_monday+pd.Timedelta(weeks=104)).timestamp()*1000)
    members = d.read(d.ART/'membership'/f'{ready["membership_month"]}.json')
    assert members['effective_from_ms'] < start
    lineage = {s: capture_lineage(s) for s in ready['hourly_symbols']}
    p = {'version': 'paper_oos_v1', 'locked_at_ms': now, 'start_ms': start, 'end_ms': end,
        'first_full_week_ms': int(first_monday.timestamp()*1000), 'full_weeks': 104,
        'authorization_sha256': d.sha(d.ART/'AUTHORIZATION.json'),
        'preparation_sha256': d.sha(d.ART/'PREPARATION_COMPLETE.json'),
        'preflight_sha256': d.sha(d.ART/'PREFLIGHT.json'),
        'initial_membership_sha256': d.sha(d.ART/'membership'/f'{ready["membership_month"]}.json'),
        'initial_hourly_lineage': lineage,
        'sources': {str(p): d.sha(p) for p in source_paths()}, 'environment': environment(),
        'tests': {name: d.sha(d.ART/name) for name in ('DATA_TESTS.xml', 'STATE_TESTS.xml', 'ALL_TESTS.xml')},
        'clock': clock, 'family': FAMILY,
        'scenarios': d.read(d.ROOT/'artifacts/fibo_trend_short/BACKTEST_COST_STANDARD.json')['scenarios'],
        'execution': 'Twelve isolated normalized NAV100 model portfolios. Original fractional quantity and OHLC exits; planned short entry at next5m OPEN with fixed per-fill cost. Current book quotes retained as diagnostics, not proof of executable liquidity. No lot rounding or exchange orders.',
        'causality': 'Decision uses closed H1 and must be recorded <=240s after close, at least60s before scheduled entry. Entry OPEN observed <=60s after due; late/missing entry is explicitly rejected. No retrospective entry creation after outage.',
        'funding': 'Actual signed fundingRate and positive associated markPrice from public settlement history; no proxy. Expected funding timestamps from archived premiumIndex snapshots. Missing expected settlement blocks accounting until resolved.',
        'universe': 'Initial partial-month rolling63 complete-day ranking from preparation. Thereafter monthly cutoff, current observed COIN USDT-perpetual eligibility, original exclusions, >=50 active days, H4 wick p90<=3.2%, median quote volume top50. New membership only effective after recorded; never backdated.',
        'lifecycle': 'Refresh exchangeInfo every5m. Block entries if not TRADING, onboard identity changed, or known delivery within120h. Missing held-contract valuation halts processing and is an incident; no invented liquidation price.',
        'state_convention': 'Continuous NAV and state, original annual five-day entry embargo retained, no annual reset; final five-day embargo. Journals and checkpoints are transactional and restartable.',
        'statistics': {'primary': 'Mean full-calendar-week log NAV change in each of twelve fixed accounts.',
            'single_final_look': True, 'alpha_family': .05, 'claims': 12,
            'method': 'Paired circular calendar block bootstrap of weekly log returns, block4weeks,100000 draws,seed42601. One-sided lower percentile at alpha/12; block8weeks supplementary and separately labelled.',
            'criteria': 'Account evidence requires lower bound>0, positive total net NAV return, >=60 closed trades and no unresolved critical data/execution incident. Standard/stress conclusions reported separately; stress profit is not imposed as a user requirement.',
            'no_guarantee': '104weeks is a fixed study horizon, not assurance of power or success. Inconclusive outcomes retained. No early success stop, result-selected extension, policy switching or automatic live promotion.'},
        'reporting': 'Operational health and descriptive NAV permitted anytime. No alpha significance decision before the fixed final horizon.',
        'backtest_end_exclusive': '2026-01-01T00:00:00Z', 'post2025_historical_pnl_computed': False,
        'orders_allowed': False, 'goal_complete': False, 'live_signoff': 'NOT_GRANTED'}
    d.save(d.ART/'PROTOCOL.json', p)
    for filename in p['sources']:
        source = Path(filename); target = d.ART/'source_snapshot'/source.relative_to(d.ROOT)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
    active = protocol(); journal = Journal(d.ART/'paper.sqlite3')
    journal.commit(0, 'activation', new_state(active), {'kind': 'activation', 'protocol_sha256': active['protocol_sha256'],
        'recorded_ms': now, 'start_ms': start, 'end_ms': end, 'orders_allowed': False})
    print(json.dumps({'state': 'ARMED', 'start_utc': d.utc(start).isoformat(), 'end_utc': d.utc(end).isoformat(), 'accounts': 12}), flush=True)


def entry_from_metadata(item):
    return {k: v for k, v in item.items() if k not in ('decision_ts', 'entry_ts')} | {
        'decision_ts_ms': item['decision_ts']*1000, 'entry_ts_ms': item['entry_ts']*1000}


def validate_entry_receipt(decision_ms, due_ms, decision_recorded_ms, open_received_ms):
    if due_ms != decision_ms+d.BAR or decision_recorded_ms > decision_ms+240_000:
        raise ValueError('Decision was not sealed before entry')
    if not due_ms <= open_received_ms <= due_ms+60_000:
        raise ValueError('Scheduled entry observation is missing or late')


def funding_rows(symbol, rows, start, end):
    output = []
    for row in rows:
        t = int(row['fundingTime']); rate = float(row['fundingRate']); mark = float(row.get('markPrice') or 0)
        if row['symbol'] != symbol or not start <= t <= end or mark <= 0 or not all(math.isfinite(v) for v in (rate, mark)):
            raise ValueError('Missing/invalid exact funding settlement')
        output.append((t, (symbol, {'funding_ts_ms': t, 'funding_rate': rate, 'mark_price': mark,
            'price_source': 'funding_api_settlement_mark', 'mark_reference_ts_ms': t})))
    if len({t for t, _ in output}) != len(output): raise ValueError('Duplicate funding settlement')
    return output


def signal_universe(membership, contracts):
    active, rejected = [], []
    for row in membership['members']:
        symbol = row['symbol']; current = contracts.get(symbol, {})
        locked = membership['contracts'][symbol]
        if current.get('status') != 'TRADING':
            rejected.append({'symbol': symbol, 'reason': 'currently_inactive_contract', 'critical': False})
        elif int(current['onboardDate']) != int(locked['onboardDate']):
            rejected.append({'symbol': symbol, 'reason': 'contract_identity_changed', 'critical': True})
        else:
            meta_path = d.ART/'hourly'/f'{symbol}.json'
            if meta_path.exists() and d.read(meta_path)['onboard_ms'] != int(current['onboardDate']):
                rejected.append({'symbol': symbol, 'reason': 'new_identity_requires_isolated_warmup', 'critical': True})
            else: active.append(symbol)
    return sorted(set(active) | {'BTCUSDT'}), rejected


class Observer:
    def __init__(self):
        self.p = protocol(); self.j = Journal(d.ART/'paper.sqlite3'); self.j.verify()
        self.offset, _ = d.server_clock()
        self.last_verification = time.monotonic()

    def now(self): return d.now_ms()+self.offset

    def _commit(self, revision, event_id, state, event):
        event.update(recorded_ms=self.now(), protocol_sha256=self.p['protocol_sha256'])
        self.j.commit(revision, event_id, state, event)

    def membership(self, timestamp):
        month = d.utc(timestamp).strftime('%Y-%m'); path = d.ART/'membership'/f'{month}.json'
        if not path.exists():
            cutoff = int(d.utc(timestamp).normalize().replace(day=1).timestamp()*1000)
            d.prepare_membership(cutoff)
        return d.read(path)

    def signal(self, timestamp):
        revision, state = self.j.load()
        if timestamp <= state['last_signal_ms']: return
        state = deepcopy(state); state['last_signal_ms'] = timestamp
        event = {'kind': 'signal_decision', 'decision_ms': timestamp, 'proposals': [], 'rejections': []}
        if self.now() > timestamp+240_000:
            event['rejections'].append({'reason': 'late_signal_no_reconstruction'})
            state['opportunity_incidents'].append({'timestamp_ms': timestamp, 'reason': 'late_signal'})
            self._commit(revision, f'signal:{timestamp}', state, event); return
        membership = self.membership(timestamp)
        if membership['effective_from_ms'] > timestamp:
            event['rejections'].append({'reason': 'membership_not_yet_effective'})
            state['opportunity_incidents'].append({'timestamp_ms': timestamp, 'reason': 'membership_not_ready'})
            self._commit(revision, f'signal:{timestamp}', state, event); return
        info, info_ref = d.request('exchangeInfo'); contracts = {a['symbol']: a for a in info['symbols']}
        symbols, lifecycle_rejections = signal_universe(membership, contracts)
        for rejection in lifecycle_rejections:
            if rejection['critical']:
                state['critical_incidents'].append({'timestamp_ms': timestamp, **rejection})
        frames = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {pool.submit(d.prepare_hourly, s, contracts[s], timestamp): s for s in symbols}
            for job in as_completed(jobs): frames[jobs[job]] = job.result()
        btc = {tf: d.history.calc_htf_features_no_bfill(d.history.resample_1h_to_htf(frames['BTCUSDT'], tf)) for tf in ('4h', '1d')}
        month = d.utc(timestamp).strftime('%Y-%m')
        feed = DecisionFeed({month: membership['members']}, [], d.utc(self.p['start_ms']), d.utc(self.p['end_ms']))
        for symbol in symbols:
            if symbol == 'BTCUSDT': continue
            hourly = frames[symbol]
            raw = signals.closed_signal_snapshots(symbol, hourly, btc, as_of=d.utc(timestamp))
            for snap in raw: feed.signal(snap, as_of=d.utc(timestamp), past_hour_opens=hourly.index[-24:])
        event['rejections'] = [*lifecycle_rejections, *feed.receipts]; event['exchange_info'] = info_ref
        event['membership_sha256'] = d.sha(d.ART/'membership'/f'{month}.json')
        event['warmup_lineage'] = {s: capture_lineage(s) for s in symbols}
        recorded = self.now()
        if recorded <= timestamp+240_000:
            pending = [{'metadata': item, 'decision_recorded_ms': recorded} for item in feed.pending.values()]
            state['pending'][str(timestamp+d.BAR)] = pending; event['proposals'] = pending
        else:
            event['rejections'].append({'reason': 'signal_computation_missed_deadline'})
            state['opportunity_incidents'].append({'timestamp_ms': timestamp, 'reason': 'computation_deadline'})
        self._commit(revision, f'signal:{timestamp}', state, event)

    def bar(self, timestamp):
        revision, state = self.j.load(); state = deepcopy(state)
        if timestamp != state['last_bar_ms']+d.BAR: raise ValueError('Nonconsecutive paper candle')
        event = {'kind': 'paper_batch', 'bar_close_ms': timestamp, 'entry_rejections': [], 'source_receipts': [], 'steps': []}
        info, ref = d.request('exchangeInfo'); event['source_receipts'].append(ref)
        contracts = {a['symbol']: a for a in info['symbols']}
        premium, ref = d.request('premiumIndex'); event['source_receipts'].append(ref)
        for a in premium:
            symbol = a['symbol']; due = int(a.get('nextFundingTime') or 0)
            if due:
                state['funding_due'][symbol] = sorted(set(state['funding_due'].get(symbol, [])) | {due})
        entries = []; pending = state['pending'].pop(str(timestamp), [])
        for proposal in pending:
            item = proposal['metadata']; symbol = item['symbol']; contract = contracts.get(symbol, {})
            try:
                if contract.get('status') != 'TRADING' or int(contract.get('deliveryDate', 0)) <= timestamp+120*d.HOUR:
                    raise ValueError('Contract is not safely tradable through model horizon')
                saved = d.read(d.ART/'hourly'/f'{symbol}.json')
                if saved['onboard_ms'] != int(contract['onboardDate']): raise ValueError('Contract identity changed')
                if self.now() > timestamp+60_000: raise ValueError('Scheduled entry observation is late')
                rows, ref = d.request('klines', {'symbol': symbol, 'interval': '5m', 'startTime': timestamp, 'endTime': timestamp, 'limit': 1})
                event['source_receipts'].append(ref)
                validate_entry_receipt(item['decision_ts']*1000, timestamp, proposal['decision_recorded_ms'], ref['received_ms']+self.offset)
                if not rows or int(rows[0][0]) != timestamp: raise ValueError('Missing current entry OPEN')
                price = float(rows[0][1])
                feed = DecisionFeed({}, [], d.utc(self.p['start_ms']), d.utc(self.p['end_ms']))
                feed.pending[item['id']] = item
                entry = feed.entry_open(item['id'], as_of=d.utc(timestamp), quote={'symbol': symbol, 'open_time_ms': timestamp, 'open': price})
                if entry is None: raise ValueError('Observed OPEN invalidated ladder')
                quote, ref = d.request('ticker/bookTicker', {'symbol': symbol}); event['source_receipts'].append(ref)
                event.setdefault('observed_book_diagnostics', []).append({'symbol': symbol, 'data': quote, 'received_ms': ref['received_ms']})
                entries.append(entry_from_metadata(entry))
            except (ValueError, KeyError) as exc:
                event['entry_rejections'].append({'id': item['id'], 'reason': str(exc)})
        held = held_symbols(state); bars = {}
        for symbol in held:
            rows, ref = d.request('klines', {'symbol': symbol, 'interval': '5m', 'startTime': timestamp-d.BAR, 'endTime': timestamp-1, 'limit': 1})
            event['source_receipts'].append(ref)
            f = d.klines_frame(rows, d.BAR, timestamp-d.BAR, timestamp)
            if len(f) != 1: raise ValueError('Missing required held-contract candle: '+symbol)
            a = f.iloc[0]
            bars[symbol] = {'open_time_ms': timestamp-d.BAR, **{k: float(a[k]) for k in ('open', 'high', 'low', 'close', 'volume')}}
        settlements = {}; last = engine_clock(state); watermark = min(timestamp+15_000, self.p['end_ms'])
        relevant = sorted(set(held) | {a['symbol'] for a in entries})
        for symbol in relevant:
            rows, ref = d.request('fundingRate', {'symbol': symbol, 'startTime': last+1, 'endTime': watermark, 'limit': 1000})
            event['source_receipts'].append(ref)
            values = funding_rows(symbol, rows, last+1, watermark)
            due = [t for t in state['funding_due'].get(symbol, []) if last < t <= watermark]
            if any(not any(abs(t-at) <= 15000 for at, _ in values) for t in due):
                raise ValueError('Expected funding settlement not yet complete: '+symbol)
            for at, value in values: settlements.setdefault(at, []).append(value)
        for at in sorted({timestamp} | set(settlements)):
            state, changes = step(state, at, entries if at == timestamp else [], bars if at == timestamp else {}, settlements.get(at, []))
            event['steps'].append({'timestamp_ms': at, 'accounts': changes})
        state['last_bar_ms'] = timestamp
        # Expired schedules may be removed only after their accounting interval.
        state['funding_due'] = {s: [t for t in times if t > watermark] for s, times in state['funding_due'].items()}
        if self.now()-timestamp > 60_000:
            state['opportunity_incidents'].append({'timestamp_ms': timestamp, 'reason': 'delayed_batch', 'delay_ms': self.now()-timestamp})
        if any(a['execution_issues'] for a in state['accounts'].values()):
            state['critical_incidents'].append({'timestamp_ms': timestamp, 'reason': 'model_execution_quality'})
        self._commit(revision, f'bar:{timestamp}', state, event)

    def status(self, error=None):
        revision, state = self.j.load(); now = self.now()
        output = {'pid': os.getpid(), 'heartbeat_ms': now, 'heartbeat_utc': d.utc(now).isoformat(),
            'status': 'ERROR_RETRYING' if error else 'ARMED' if now < self.p['start_ms'] else 'OBSERVING',
            'error': error, 'revision': revision, 'start_utc': d.utc(self.p['start_ms']).isoformat(),
            'end_utc': d.utc(self.p['end_ms']).isoformat(), 'last_bar_ms': state['last_bar_ms'],
            'last_signal_ms': state['last_signal_ms'], 'open_positions': sum(len(a['positions']) for a in state['accounts'].values()),
            'accepted_trades': state['accepted_trades'], 'closed_trades': state['closed_trades'],
            'nav': {k: a['equity'] for k, a in state['accounts'].items()},
            'opportunity_incidents': len(state['opportunity_incidents']), 'critical_incidents': len(state['critical_incidents']),
            'protocol_sha256': self.p['protocol_sha256'], 'orders_allowed': False, 'goal_complete': False, 'live_signoff': 'NOT_GRANTED'}
        d.save(d.ART/'STATUS.json', output)
        return output

    def tick(self):
        if time.monotonic()-self.last_verification > 1800:
            self.p = protocol(); self.offset, _ = d.server_clock(); self.last_verification = time.monotonic()
        _, state = self.j.load()
        decision = state['last_signal_ms']+d.HOUR
        if decision <= state['last_bar_ms'] and decision < self.p['end_ms']-5*d.DAY:
            self.signal(decision)
            self.status(); return True
        target = state['last_bar_ms']+d.BAR
        if target > self.p['end_ms']: return False
        if target <= self.now()-20_000:
            self.bar(target)
        self.status(); return True


def run():
    import msvcrt
    lock = open(d.ART/'RUNNER.lock', 'a+b')
    if lock.tell() == 0: lock.write(b'1'); lock.flush()
    lock.seek(0)
    try: msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError: raise RuntimeError('Another paper observer already holds the lock')
    observer = Observer(); observer.status()
    try:
        while True:
            try:
                if not observer.tick():
                    status = observer.status(); status['status'] = 'HORIZON_COMPLETE_AWAITING_REVIEW'; d.save(d.ART/'STATUS.json', status); break
            except Exception as exc:
                observer.status(type(exc).__name__+': '+str(exc)); print(type(exc).__name__+': '+str(exc), flush=True)
            time.sleep(5)
    finally:
        lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1); lock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=['activate', 'run', 'status'])
    action = parser.parse_args().action
    if action == 'status': print(json.dumps(d.read(d.ART/'STATUS.json'), indent=2), flush=True)
    else: globals()[action]()
