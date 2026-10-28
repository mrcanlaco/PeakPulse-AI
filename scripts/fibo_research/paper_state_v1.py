"""Atomic paper-only journal and twelve isolated model portfolios."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3

from stream_execution_v424 import SequentialPortfolio


def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


class Journal:
    def __init__(self, path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=20)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS snapshot(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, previous_hash TEXT NOT NULL, digest TEXT NOT NULL, payload TEXT NOT NULL);
        ''')

    def load(self):
        row = self.db.execute('SELECT revision,payload FROM snapshot WHERE id=1').fetchone()
        return (row[0], json.loads(row[1])) if row else (0, None)

    def commit(self, expected_revision, event_id, state, event):
        state_payload = json.dumps(state, separators=(',', ':'), allow_nan=False)
        payload = canonical({**event, 'state_sha256': hashlib.sha256(state_payload.encode()).hexdigest()})
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            existing = self.db.execute('SELECT payload FROM events WHERE event_id=?', (event_id,)).fetchone()
            if existing:
                if existing[0] != payload: raise ValueError('Conflicting replay of journal event')
                return False
            actual, _ = self.load()
            if actual != expected_revision: raise ValueError('Concurrent/stale state revision')
            row = self.db.execute('SELECT digest FROM events ORDER BY seq DESC LIMIT 1').fetchone()
            previous = row[0] if row else '0'*64
            digest = hashlib.sha256((previous+'\n'+event_id+'\n'+payload).encode()).hexdigest()
            self.db.execute('INSERT INTO events VALUES(?,?,?,?,?)', (actual+1, event_id, previous, digest, payload))
            self.db.execute('INSERT OR REPLACE INTO snapshot VALUES(1,?,?)', (actual+1, state_payload))
        return True

    def verify(self):
        previous = '0'*64; count = 0
        for seq, event_id, prev, digest, payload in self.db.execute('SELECT * FROM events ORDER BY seq'):
            count += 1
            assert seq == count and prev == previous
            assert hashlib.sha256((prev+'\n'+event_id+'\n'+payload).encode()).hexdigest() == digest
            previous = digest
        revision, _ = self.load(); assert revision == count
        if count:
            snapshot = self.db.execute('SELECT payload FROM snapshot WHERE id=1').fetchone()[0]
            assert hashlib.sha256(snapshot.encode()).hexdigest() == json.loads(payload)['state_sha256']
        return {'events': count, 'last_hash': previous, 'all_passed': True}


def new_state(protocol):
    accounts = {}
    for policy in protocol['family']:
        for cost, scenario in protocol['scenarios'].items():
            key = policy['id']+'__'+cost
            accounts[key] = SequentialPortfolio(protocol['start_ms'], protocol['end_ms'], policy, scenario).state()
    return {'protocol_sha256': protocol['protocol_sha256'], 'accounts': accounts,
        'last_bar_ms': protocol['start_ms']-300000, 'last_signal_ms': protocol['start_ms']-3600000,
        'pending': {}, 'funding_due': {}, 'opportunity_incidents': [], 'critical_incidents': [],
        'accepted_trades': {k: 0 for k in accounts}, 'closed_trades': {k: 0 for k in accounts},
        'cum_realized_pnl': {k: 0. for k in accounts}}


def step(state, timestamp, entries, bars, funding):
    """All accounts advance or none; caller commits the returned state atomically."""
    output = deepcopy(state); changes = {}
    for name, saved in output['accounts'].items():
        engine = SequentialPortfolio.restore(saved)
        engine.process(timestamp, entries=entries, bars=bars, funding=funding,
                       funding_complete_through_ms=timestamp)
        new_ids = sorted(set(engine.positions)-set(saved['positions']))
        output['accepted_trades'][name] += len(new_ids)
        output['closed_trades'][name] += len(engine.ledger)
        output['cum_realized_pnl'][name] += sum(a['pnl'] for a in engine.ledger)
        changes[name] = {'equity': engine.equity, 'accepted_ids': new_ids,
            'closed_trades': deepcopy(engine.ledger), 'curve': deepcopy(engine.curve[1:]),
            'open_ids': sorted(engine.positions), 'execution_issues': deepcopy(engine.execution_issues)}
        # Complete realized records and NAV observations live in the append-only
        # journal. Retain only current state here to bound snapshot growth.
        engine.ledger = []; engine.curve = [(timestamp, engine.equity)]
        output['accounts'][name] = engine.state()
        total = output['cum_realized_pnl'][name]+sum(a['pnl'] for a in engine.positions.values())
        if abs(engine.equity-100-total) > 1e-7: raise ValueError('Paper account cash reconciliation failed')
    return output, changes


def held_symbols(state):
    return sorted({p['symbol'] for a in state['accounts'].values() for p in a['positions'].values()})


def engine_clock(state):
    values = {a['clock'] for a in state['accounts'].values()}
    if len(values) != 1: raise ValueError('Paper account clocks diverged')
    return next(iter(values))
