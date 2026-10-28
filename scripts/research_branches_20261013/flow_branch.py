"""Isolated Dòng Tiền replay. Never writes donor engines or shadow ledgers."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import replace
import numpy as np
import pandas as pd
from dao_vang.nostop.data import load_panel
from dao_vang.nostop.engine import cost_matrix, simulate, split_range
from dao_vang.nostop.signals import Ctx, build

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/research_branches_20261013/flow'
LAKE = Path('C:/Quant-trading/data_lake')

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''): h.update(block)
    return h.hexdigest()

def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    with (OUT / name).open('x', encoding='utf-8') as f:
        f.write(serialized)

def freeze():
    save('protocol.json', {
        'created_at': datetime.now(timezone.utc).isoformat(), 'branch': 'flow', 'name': 'Dòng Tiền',
        'baseline': 'composite-2a753a0b', 'variants': ['baseline_corrected', 'remove_taker', 'remove_funding'],
        'factors': ['taker7+fz7', 'fz7', 'taker7'],
        'attribution': 'Old baseline plus corrected cashflow engine with OLD donor weights, then corrected funding feature weights; do not confuse execution correction with signal ablation.',
        'period': '2026-01-01 through 2026-08-31 UTC, identical full-panel warmup; already seen development history, NOT fresh OOS',
        'funding': 'Preserve every raw event. Normalize timestamps <=60 seconds after whole hour to that hour as exchange timestamp jitter. Settlement at open before rebalance. Intrabar settlement uses post-rebalance holdings. Actual positive finite mark_price else explicitly flagged bar-open proxy. Raw file presence is NOT proof of funding completeness.',
        'execution': 'Trade eligibility uses current open only. Missing current/next valuation on HELD positions stops result as unknown. No flat fill for missing valuation. Fee+slippage donor cost_matrix, donor3xmax gross, donor2%maintenance and conservative intrabar extremes retained.',
        'universe': 'Same116 end-2025 survivors; not point-in-time complete. No delisting correction claims.',
        'selection': 'Two predeclared single-factor removals only. Same parameters and universe rules; positions may change as rankings/vol targeting respond.',
        'combination': 'Export normalized10000 UTC daily account equity for diagnostics only. funding_coverage_verified=false and eligible_for_combination=false until independently reconciled.',
        'stop': 'No parameter sweep; no existing shadow mutation; unresolved prices reported, not invented.',
    })

def normalize_event_times(times):
    times = pd.to_datetime(times, utc=True)
    hours = times.dt.floor('h')
    return times.where((times - hours).dt.total_seconds() > 60, hours)

def load_events(panel, hashes):
    by_bar = {}
    summed = np.zeros(panel.shape)
    audit = {'raw_events': 0, 'missing_files': [], 'invalid_rates': 0, 'events_without_actual_mark': 0}
    for j, symbol in enumerate(panel.symbols):
        path = LAKE / 'funding' / f'{symbol}_funding.parquet'
        if not path.exists():
            audit['missing_files'].append(symbol); continue
        hashes[str(path.resolve())] = digest(path)
        f = pd.read_parquet(path)
        times = normalize_event_times(f.funding_time)
        mask = (times >= panel.index[0]) & (times < panel.index[-1] + pd.Timedelta('4h'))
        for timestamp, rate, mark in zip(times[mask], f.loc[mask, 'funding_rate'], f.loc[mask, 'mark_price']):
            k = int(panel.index.searchsorted(timestamp, side='right') - 1)
            audit['raw_events'] += 1
            if not np.isfinite(rate): audit['invalid_rates'] += 1; continue
            actual_mark = float(mark) if np.isfinite(mark) and mark > 0 else None
            if actual_mark is None: audit['events_without_actual_mark'] += 1
            by_bar.setdefault(k, []).append((timestamp, j, float(rate), actual_mark))
            summed[k, j] += float(rate)
    for events in by_bar.values(): events.sort(key=lambda event: event[0])
    return by_bar, summed, audit

def replay(panel, weights, rebalance, events, costs, k0, k1):
    qty = np.zeros(panel.shape[1]); equity = 1.0
    curve = [equity]; fees = funding = 0.0; trades = 0
    proxy_count = paid_count = 0; status = 'complete'; reason = None
    min_intrabar_equity = 1.0
    for k in range(k0, k1 + 1):
        opened = panel.open[k]
        held = abs(qty) > 1e-14
        if np.any(held & (~np.isfinite(opened) | (opened <= 0))):
            status = 'unknown'; reason = f'missing_current_held_price:{panel.index[k]}'; break
        def pay(event):
            timestamp, j, rate, mark = event
            if abs(qty[j]) <= 1e-14: return 0.0, 0, 0
            price = mark if mark is not None else opened[j]
            if not np.isfinite(price) or price <= 0: raise ValueError('Missing funding valuation')
            return -qty[j] * price * rate, int(mark is None), 1
        bar_events = events.get(k, [])
        for event in bar_events:
            if event[0] == panel.index[k]:
                paid, proxy, count = pay(event); equity += paid; funding += paid; proxy_count += proxy; paid_count += count
        if k >= 1 and rebalance[k - 1]:
            valid = np.isfinite(opened) & (opened > 0)
            old_notional = np.where(valid, qty * opened, 0)
            wanted = np.where(np.isnan(weights[k - 1]), old_notional, np.nan_to_num(weights[k - 1]) * equity)
            # Reject only currently untradeable targets, never consult next open.
            target = np.where(valid, wanted, old_notional)
            gross = abs(target).sum()
            if gross > 3 * max(equity, 0): target *= 3 * max(equity, 0) / gross
            delta = target - old_notional
            fee = float(np.dot(abs(delta), np.nan_to_num(costs[k - 1], nan=.0015)))
            fees += fee; equity -= fee; trades += int((abs(delta) > 1e-14).sum())
            qty = np.divide(target, opened, out=qty.copy(), where=valid)
        # A credit late in the bar cannot finance an earlier price extreme.
        # Intrabar extrema have no timestamps: use a conservative debit-only
        # bound, not an invented favorable cashflow/extreme ordering.
        pending_funding = [pay(event) for event in bar_events if event[0] > panel.index[k]]
        intrabar_debits = sum(min(paid, 0.0) for paid, _, _ in pending_funding)
        held = abs(qty) > 1e-14
        nxt = panel.open[k + 1] if k + 1 < len(panel.index) else panel.close[k]
        if np.any(held & (~np.isfinite(nxt) | (nxt <= 0))):
            status = 'unknown'; reason = f'missing_future_held_valuation:{panel.index[k]}'; break
        adverse = np.where(qty > 0, panel.low[k], panel.high[k])
        if np.any(held & ~np.isfinite(adverse)):
            status = 'unknown'; reason = f'missing_held_extreme:{panel.index[k]}'; break
        worst = equity + intrabar_debits + float(np.dot(qty[held], adverse[held] - opened[held]))
        min_intrabar_equity = min(min_intrabar_equity, worst)
        if worst <= .02 * float(np.abs(qty[held] * opened[held]).sum()) and held.any():
            status = 'liquidated'; equity = 0; curve.append(0.0); break
        for paid, proxy, count in pending_funding:
            equity += paid; funding += paid; proxy_count += proxy; paid_count += count
        equity += float(np.dot(qty[held], nxt[held] - opened[held]))
        curve.append(equity)
    return {'status': status, 'unknown_reason': reason, 'equity': curve, 'fees_initial_equity': fees,
            'funding_initial_equity': funding, 'funding_paid_events': paid_count,
            'funding_proxy_paid_events': proxy_count, 'trades': trades, 'minimum_intrabar_equity': min_intrabar_equity,
            'positions_rule': 'Fixed quantities between donor rebalance dates; target weights endogenous to signal/vol targeting. Cashflow changes capital and therefore later notional sizes.'}

def export_equity(panel, k0, result, variant):
    times = pd.date_range(panel.index[k0], periods=len(result['equity']), freq='4h')
    # Midnight AFTER day d is day d's closing valuation. Exclude starting seed.
    closing = [(t - pd.Timedelta('1D'), value) for t, value in zip(times[1:], result['equity'][1:]) if t.hour == 0]
    denominator = closing[0][1] if closing else 1.0
    rows = [{'date': t.strftime('%Y-%m-%d'), 'equity': float(value / denominator * 10000)} for t, value in closing]
    return {'branch': 'flow', 'variant': variant, 'metric_basis': 'account_equity', 'eligible_for_combination': False,
            'is_baseline': variant == 'baseline_corrected',
            'diagnostic_combination_eligible': result['status'] == 'complete' and bool(rows),
            'valuation_convention': 'daily_close_utc', 'normalization': 'first_daily_close_10000',
            'funding_coverage_verified': False, 'rows': rows,
            'limitations': ['Diagnostic historical replay, not verified profits', '116 survivor universe', 'Raw funding completeness not independently verified', 'Funding mark proxy if flagged; see report', 'Already-seen history, not fresh holdout'], 'replay_status': result['status']}

def main():
    protocol = json.loads((OUT / 'protocol.json').read_text(encoding='utf-8'))
    sources = [Path(__file__), OUT / 'protocol.json', OUT / 'export_convention_addendum.json', ROOT / 'tests/unit/research_branches_20261013/test_flow_branch.py', ROOT / 'src/dao_vang/nostop/data.py', ROOT / 'src/dao_vang/nostop/signals.py', ROOT / 'src/dao_vang/nostop/engine.py', ROOT / 'artifacts/nostop/candidate_lock.json', ROOT / 'artifacts/nostop/panel_4h.npz']
    hashes = {str(p.resolve()): digest(p) for p in sources}
    repair_dir = OUT / 'pre_funding_order_repair'
    for path in [OUT / 'funding_order_repair.json', *repair_dir.iterdir()]:
        if path.is_file(): hashes[str(path.resolve())] = digest(path)
    panel = load_panel(); k0, k1 = split_range(panel, 'test'); costs = cost_matrix(panel)
    lock = json.loads((ROOT / 'artifacts/nostop/candidate_lock.json').read_text())
    spec = next(s for s in lock['specs'] if s['id'] == protocol['baseline'])
    Wold, rebold = build(Ctx(panel), spec)
    legacy = simulate(panel, Wold, rebold, k0, k1, costs)
    events, summed, audit = load_events(panel, hashes)
    corrected_panel = replace(panel, funding=summed)
    results = {'old_baseline': {'status': 'legacy_complete', 'equity': legacy.equity.tolist(), 'fees_initial_equity': legacy.fees, 'funding_initial_equity': legacy.funding}}
    results['cashflow_only_old_weights'] = replay(panel, Wold, rebold, events, costs, k0, k1)
    for name, factors in zip(protocol['variants'], protocol['factors']):
        variant = {'family': 'composite', 'params': {**spec['params'], 'factors': factors}}
        weights, rebalance = build(Ctx(corrected_panel), variant)
        results[name] = replay(corrected_panel, weights, rebalance, events, costs, k0, k1)
        save('equity.json' if name == 'baseline_corrected' else f'equity_{name}.json', export_equity(panel, k0, results[name], name))
    summaries = {}
    for name, result in results.items():
        arr = np.array(result['equity']); complete = result['status'] in {'complete', 'legacy_complete'}
        summaries[name] = {k: v for k, v in result.items() if k != 'equity'}
        summaries[name].update({'final_equity_diagnostic': float(arr[-1]) * 10000 if complete else None,
                                'total_return_diagnostic': float(arr[-1] - 1) if complete else None,
                                'maxdd_boundary_diagnostic': float(np.max(1 - arr / np.maximum.accumulate(arr))), 'marks': len(arr)})
    old_report = json.loads((repair_dir / 'report.json').read_text(encoding='utf-8'))
    old_results = old_report['evidence'][0]['results']
    comparison = {}
    for name, result in summaries.items():
        old = old_results[name]
        comparison[name] = {key: {'before': old.get(key), 'after': result.get(key), 'changed': bool(old.get(key) != result.get(key))} for key in ['status', 'total_return_diagnostic', 'maxdd_boundary_diagnostic', 'minimum_intrabar_equity']}
    daily_changes = {}
    for filename in ['equity.json', 'equity_remove_taker.json', 'equity_remove_funding.json']:
        before = json.loads((repair_dir / filename).read_text(encoding='utf-8'))['rows']
        after = json.loads((OUT / filename).read_text(encoding='utf-8'))['rows']
        daily_changes[filename] = {'before_rows': len(before), 'after_rows': len(after), 'changed_rows': sum(a != b for a, b in zip(before, after)) + abs(len(before) - len(after))}
    save('report.json', {'branch': 'flow', 'name': 'Dòng Tiền', 'status': 'isolated_diagnostic_replay_complete_not_financially_verified',
        'evidence': [{'finding': 'Frozen representative and <=2 ablations', 'results': summaries}, {'finding': 'All raw funding events retained', 'audit': audit}, {'finding': 'Conservative funding/event-order repair, no retuning', 'comparisons': comparison, 'daily_equity_changes': daily_changes}],
        'limitations': ['Funding completeness not proved; no verified profitability or combination eligibility', 'Funding positive mark_price preferred; missing mark uses declared bar-open proxy', 'Same end2025 survivor universe excludes delistings', 'Vol-target donor algorithm unchanged and not independently revalidated', 'Conservative liquidation bound: adverse extrema plus all intrabar debits before any intrabar credits; not exact exchange event chronology', 'Attribution path dependent: corrected funding changes later capital and position sizes', 'Historical window already used; not fresh OOS', 'No actual executions, no existing28shadow modifications'],
        'next_experiment': {'name': 'Independent funding and delisting reconciliation before capital combination', 'promote': False}, 'source_hashes': hashes})
    print(json.dumps(summaries, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--freeze', action='store_true'); args = parser.parse_args()
    freeze() if args.freeze else main()
