"""Verifier-only tuple/list normalization, preserving frozen economic code."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import evaluate_family_v421 as e

r = e.r
ART = e.ART


def engine_form(node):
    return {**node, 'curve': [tuple(p) for p in node['curve']]}


def register():
    e.verify_sources()
    diagnostic = r.read(ART / 'ELITE_RECONCILIATION_DIAGNOSTIC.json')
    assert diagnostic['ledger_equal'] and diagnostic['curve_array_equal']
    assert diagnostic['new_curve_point_type'] == 'tuple' and diagnostic['old_curve_point_type'] == 'list'
    path = ART / 'RECONCILIATION_ADAPTER_PROTOCOL.json'
    if path.exists():
        raise FileExistsError('Adapter already registered')
    r.save(path, {'registered_at_utc': datetime.now(timezone.utc).isoformat(),
        'reason': 'In-memory engine curves are tuples; JSON readback curves are lists. Direct Python container equality failed despite identical ledger and numeric curve.',
        'change': 'Normalize only the reference curve point containers to tuples in the economic evaluator process. Preserve every value and ledger. Independent final verifier compares JSON with JSON without this adapter.',
        'strategy_or_data_changed': False,
        'original_economic_protocol_sha256': r.sha(ART / 'ECONOMIC_PROTOCOL.json'),
        'diagnostic_sha256': r.sha(ART / 'ELITE_RECONCILIATION_DIAGNOSTIC.json'),
        'source_sha256': r.sha(__file__),
        'tests_source_sha256': r.sha(e.v.ROOT / 'tests/unit/fibo_short/test_family_reconciliation_v421.py'),
        'existing_receipts': {str(p.relative_to(ART)): r.sha(p) for p in sorted((ART / 'runs').glob('*.json'))},
        'existing_ledgers': {str(p.relative_to(ART)): r.sha(p) for p in sorted((ART / 'runs').glob('*.json.gz'))}})


def verify():
    e.verify_sources()
    p = r.read(ART / 'RECONCILIATION_ADAPTER_PROTOCOL.json')
    assert p['source_sha256'] == r.sha(__file__)
    assert p['tests_source_sha256'] == r.sha(e.v.ROOT / 'tests/unit/fibo_short/test_family_reconciliation_v421.py')
    assert p['original_economic_protocol_sha256'] == r.sha(ART / 'ECONOMIC_PROTOCOL.json')
    assert p['diagnostic_sha256'] == r.sha(ART / 'ELITE_RECONCILIATION_DIAGNOSTIC.json')
    for group in ('existing_receipts', 'existing_ledgers'):
        for path, digest in p[group].items():
            assert r.sha(ART / path) == digest


def evaluate():
    verify()
    original = e.v.previous.b.ledger
    def adapted(*args):
        return engine_form(original(*args))
    e.v.previous.b.ledger = adapted
    e.evaluate()
    r.save(ART / 'RECONCILIATION_ADAPTER_COMPLETION.json', {
        'all_passed': True, 'results_sha256': r.sha(ART / 'RESULTS.json'),
        'adapter_protocol_sha256': r.sha(ART / 'RECONCILIATION_ADAPTER_PROTOCOL.json'),
        'prior_four_nodes_preserved': True, 'strategy_or_data_changed': False})


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['register', 'evaluate', 'verify'])
    {'register': register, 'evaluate': evaluate, 'verify': verify}[p.parse_args().action]()
