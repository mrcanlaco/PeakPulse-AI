"""Independent accounting, admissions, quality, selection and calendar NAV audit."""
from collections import Counter, defaultdict
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import evaluate_family_v421 as e
import verify_research_v419 as stats
import verify_research_review_v420 as selection

v = e.v
r = v.r
ART = v.ART


def close(a, b):
    assert np.allclose(a, b, atol=1e-7, rtol=0), (a, b)


def check_node(year, spec, scenario, node, metric, raw, funding, flags, counts, exact):
    assumption = v.SCENARIOS[scenario]
    fee = assumption['fee_bps'] / 10000
    slip = assumption['slippage_bps'] / 10000
    lo = int(r.utc(f'{year}-01-01').timestamp()*1000)
    hi = int(r.utc(f'{year+1}-01-01').timestamp()*1000)
    events = defaultdict(float, {lo: 0., hi: 0.})
    non_entry = defaultdict(float)
    assert len({p['id'] for p in node['ledger']}) == len(node['ledger']) == metric['trades']
    for p in node['ledger']:
        c = raw[p['id']]
        path = c['paths']['ladder']
        trace = np.asarray(path['trace'])
        assert p['entry_ts_ms'] == c['entry_ts']*1000 and p['exit_ts_ms'] == path['exit_ts']*1000
        assert lo <= p['entry_ts_ms'] < hi-5*86400000 and p['exit_ts_ms'] <= hi
        loss = c['stop']*(1+slip) - c['entry']*(1-slip) + fee*(c['stop']*(1+slip)+c['entry']*(1-slip))
        expected_qty = .20*p['equity_at_entry']/c['entry']
        if spec['sizing'] == 'risk':
            expected_qty = min(expected_qty, .005*p['equity_at_entry']/loss)
        close([p['qty'], p['reference_notional'], p['stop_risk_with_execution_costs']],
              [expected_qty, expected_qty*c['entry'], expected_qty*loss])
        cash = fees = slips = sold = bought = 0.
        for i, fill in enumerate(p['fills']):
            assert fill['side'] == ('SELL' if i == 0 else 'BUY')
            direction = -1 if i == 0 else 1
            price = fill['reference_price']*(1+direction*slip)
            close([fill['execution_price'], fill['notional'], fill['fee'], fill['slippage_cost']],
                  [price, price*fill['qty'], price*fill['qty']*fee, fill['reference_price']*fill['qty']*slip])
            cash -= direction*fill['notional']
            fees += fill['fee']
            slips += fill['slippage_cost']
            cost = fill['fee']+fill['slippage_cost']
            events[fill['timestamp_ms']] -= cost
            if i:
                bought += fill['qty']
                non_entry[fill['timestamp_ms']] -= cost
            else:
                sold += fill['qty']
        close([fees, slips, sold, bought], [p['fees'], p['slippage'], p['qty'], p['qty']])
        for step in path['trace']:
            change = p['reference_notional']*step[5]
            events[step[0]*1000] += change
            non_entry[step[0]*1000] += change
        pack = funding[p['symbol']]
        a = np.searchsorted(pack['times'], p['entry_ts_ms'], side='right')
        b = np.searchsorted(pack['times'], p['exit_ts_ms'], side='right')
        expected = pack['events'][a:b]
        assert len(expected) == len(p['funding_events'])
        fc = 0.
        for actual, source in zip(p['funding_events'], expected):
            assert all(actual[k] == val for k, val in source.items())
            j = np.searchsorted(trace[:,0]*1000, source['funding_ts_ms'], side='left')-1
            qty = p['qty']*(trace[j,3] if j >= 0 else 1.)
            amount = qty*source['mark_price']*source['funding_rate']
            close([actual['remaining_qty'], actual['cashflow']], [qty, amount])
            fc += amount
            events[source['funding_ts_ms']] += amount
            non_entry[source['funding_ts_ms']] += amount
            if source['price_source'] != 'funding_api_settlement_mark':
                counts['proxy_funding_payments'] += 1
                if amount:
                    exact[(p['symbol'], source['funding_ts_ms'])] = {'symbol': p['symbol'], **source}
        close([fc, cash-fees+fc, p['reference_notional']*path['gross_return']-fees-slips+fc],
              [p['funding'], p['pnl'], p['pnl']])
        counts['fills'] += len(p['fills'])
        counts['funding_payments'] += len(expected)
    curve = np.asarray(node['curve'])
    times = sorted(events)
    balance = 100+np.cumsum([events[t] for t in times])
    observed = pd.Series(curve[:,1], index=curve[:,0]).groupby(level=0).last()
    assert observed.index.tolist() == times
    close(observed.to_numpy(), balance)
    close(metric['return_pct'], balance[-1]-100)
    close(metric['max_dd_pct'], np.max(1-curve[:,1]/np.maximum.accumulate(curve[:,1]))*100)
    close(balance[-1], 100+sum(p['pnl'] for p in node['ledger']))
    for name, key in [('fees_pct','fees'), ('slippage_pct','slippage'), ('funding_pct','funding')]:
        close(metric[name], sum(p[key] for p in node['ledger']))
    active = []
    waves = set()
    cooldown = {}
    paid = 0.
    nt = np.array(sorted(non_entry))
    nc = np.cumsum([non_entry[t] for t in nt])
    for p in sorted(node['ledger'], key=lambda a: (a['entry_ts_ms'], -raw[a['id']]['score'], a['symbol'], a['tf'])):
        t = p['entry_ts_ms']
        j = np.searchsorted(nt, t, side='right')-1
        equity = 100+(nc[j] if j >= 0 else 0)-paid
        close(equity, p['equity_at_entry'])
        c = raw[p['id']]
        key = (p['symbol'], p['tf'])
        wave = (*key, c['wave_key'])
        assert wave not in waves and t >= cooldown.get(key, 0)
        active = [a for a in active if a['exit_ts_ms'] > t]
        notional = risk = 0.
        for a in active:
            tr = np.asarray(raw[a['id']]['paths']['ladder']['trace'])
            k = np.searchsorted(tr[:,0]*1000, t, side='right')-1
            rem, mark, stop = (tr[k,3], tr[k,1], tr[k,4]) if k >= 0 else (1., a['entry'], a['stop'])
            qty = a['qty']*rem
            notional += qty*max(a['entry'], mark)
            cost = qty*stop*(1+slip)
            risk += max(0., cost-qty*min(a['entry'], mark)+cost*fee)
        fill = p['fills'][0]
        cost = fill['fee']+fill['slippage_cost']
        after = equity-cost
        riskcap = .12 if spec['sizing'] == 'fixed' else .02
        assert len(active) < 5 and notional+p['reference_notional'] <= after+1e-8
        assert risk+p['stop_risk_with_execution_costs'] <= riskcap*after+1e-8
        active.append(p)
        waves.add(wave)
        cooldown[key] = max(p['exit_ts_ms'], t+4*3600000)
        paid += cost
        counts['entry_cap_checks'] += 1
    mode = 'h24' if 'hours' in spec else 'full'
    bad = [p['id'] for p in node['ledger'] if (p['id'], mode) in flags]
    assert bad == metric['accepted_execution_issue_ids'] and metric['execution_qualified'] == (not bad)
    counts['accepted_execution_issue_records'] += len(bad)
    counts['nodes'] += 1
    counts['scenario_trades'] += len(node['ledger'])


def verify_period(rawcurve, start, end, metric):
    lo, hi = [int(r.utc(t).timestamp()*1000) for t in (start, end)]
    curve = np.asarray(rawcurve)
    first = curve[curve[:,0] <= lo][-1,1]
    last = curve[curve[:,0] <= hi][-1,1]
    values = np.r_[first, curve[(curve[:,0] > lo) & (curve[:,0] <= hi),1], last]
    close([metric['start_nav'], metric['end_nav'], metric['return_pct'], metric['max_dd_pct']],
          [first, last, (last/first-1)*100, np.max(1-values/np.maximum.accumulate(values))*100])
    series = pd.Series(curve[:,1], index=pd.to_datetime(curve[:,0].astype('int64'), unit='ms', utc=True)).groupby(level=0).last().sort_index()
    grid = pd.DatetimeIndex(sorted({r.utc(start), r.utc(end), *pd.date_range(r.utc(start), r.utc(end), freq='W-MON')}))
    marked = series.asof(grid).to_numpy()
    returns = marked[1:]/marked[:-1]-1
    close(metric['calendar_weekly_ci95']['ci_pct'], stats.interval(returns))
    close(metric['calendar_weekly_ci95']['mean_weekly_pct'], returns.mean()*100)
    assert metric['calendar_weekly_ci95']['intervals'] == len(returns)


def main():
    e.verify_sources()
    result = r.read(ART / 'RESULTS.json')
    assert all(result[k] == val for k, val in e.fingerprint().items())
    pack = v.load_paths()
    lookup = {mode: {c['id']: c for c in rows} for mode, rows in pack.items()}
    funding = v.load_funding()
    flags = {(a['id'], a['mode']) for a in r.read(ART / 'PATH_MANIFEST.json')['quality_issues']}
    counts = Counter()
    exact = {}
    annual = {}
    curves = {}
    for year in range(2020, 2026):
        annual[str(year)] = {}
        for spec in v.FAMILY:
            pid = spec['id']
            annual[str(year)][pid] = {}
            for scenario in v.SCENARIOS:
                node = e.ledger(year, pid, scenario)
                receipt_path = ART / 'runs' / f'{year}_{pid}_{scenario}.json'
                receipt = r.read(receipt_path)
                assert receipt['ledger_sha256'] == r.sha(receipt_path.with_suffix('.json.gz'))
                assert all(receipt[k] == val for k, val in e.fingerprint().items())
                metric = result['annual'][str(year)][pid][scenario]
                assert metric == {k: a for k, a in receipt['metric'].items() if k not in ('curve_values','weekly_returns','weekly_ci')}
                close(receipt['metric']['curve_values'], np.asarray(node['curve'])[:,1])
                annual[str(year)][pid][scenario] = receipt['metric']
                check_node(year, spec, scenario, node, metric, lookup['h24' if 'hours' in spec else 'full'], funding, flags, counts, exact)
                curves[(year, pid, scenario)] = node['curve']
                if pid == 'elite_sniper_risk':
                    assert node == v.previous.b.ledger(year, scenario)
                    counts['exact_v415_nodes'] += 1
        print(f'Independent {year}: {counts["nodes"]} nodes, {counts["scenario_trades"]} records', flush=True)
    for year in range(2022, 2026):
        actual = result['walk_forward_locks'][str(year)]
        _, audit = selection.independent_audit(annual, year, [s['id'] for s in v.FAMILY])
        qualified = []
        for pid, a in audit.items():
            quality = all(annual[str(y)][pid][s]['execution_qualified'] for y in range(2020, year) for s in v.SCENARIOS)
            eligible = a['eligible'] and quality
            assert actual['audit'][pid]['eligible'] == eligible
            cash = 100.
            points = [cash]
            for y in range(2020, year):
                values = annual[str(y)][pid]['stress_regular']['curve_values']
                points.extend(np.asarray(values)[1:]*cash/100)
                cash *= 1+annual[str(y)][pid]['stress_regular']['return_pct']/100
            points = np.asarray(points)
            stress_dd = float(np.max(1-points/np.maximum.accumulate(points))*100)
            close(actual['audit'][pid]['stress']['max_dd_pct'], stress_dd)
            if eligible:
                saved = actual['audit'][pid]['stress']
                close(saved['return_pct'], a['stress_return'])
                qualified.append((a['stress_return']-stress_dd, pid))
        qualified.sort(key=lambda a: (-a[0], a[1]))
        assert actual['selected'] == (qualified[0][1] if qualified else 'CASH')
        assert actual['training_years'] == [str(y) for y in range(2020, year)]
        assert not actual['uses_test_year_metrics']
        assert actual == r.read(ART / f'LOCK_TEST_{year}.json')
        counts['selection_locks'] += 1
    for spec in v.FAMILY:
        pid = spec['id']
        for scenario in v.SCENARIOS:
            curve = []
            cash = 100.
            for year in range(2020, 2026):
                a = curves[(year, pid, scenario)]
                factor = cash/100
                curve.extend((t, val*factor) for t, val in a)
                cash = a[-1][1]*factor
            for label, (start, end) in e.SPLITS.items():
                saved = result['fixed_policy_periods'][label][pid][scenario]
                verify_period(curve, start, end, saved)
                years = range(int(start[:4]), int(end[:4]))
                assert saved['trades'] == sum(annual[str(y)][pid][scenario]['trades'] for y in years)
                assert saved['execution_qualified'] == all(annual[str(y)][pid][scenario]['execution_qualified'] for y in years)
                counts['periods_verified'] += 1
    for scenario in v.SCENARIOS:
        curve = []
        cash = 100.
        for year in range(2022, 2026):
            pid = result['walk_forward_locks'][str(year)]['selected']
            a = curves[(year, pid, scenario)] if pid != 'CASH' else [(int(r.utc(f'{year}-01-01').timestamp()*1000),100.), (int(r.utc(f'{year+1}-01-01').timestamp()*1000),100.)]
            factor = cash/100
            curve.extend((t, val*factor) for t, val in a)
            cash = a[-1][1]*factor
        for start in (2022, 2024):
            saved = result['walk_forward_oos'][scenario][f'{start}_2025']
            verify_period(curve, f'{start}-01-01', '2026-01-01', saved)
            nodes = [annual[str(y)][result['walk_forward_locks'][str(y)]['selected']][scenario] for y in range(start,2026) if result['walk_forward_locks'][str(y)]['selected'] != 'CASH']
            assert saved['trades'] == sum(a['trades'] for a in nodes)
            assert saved['execution_qualified'] == all(a['execution_qualified'] for a in nodes)
            counts['periods_verified'] += 1
    suites = list(ET.parse(ART / 'ECONOMIC_TESTS.xml').getroot().iter('testsuite'))
    tests = {k: sum(int(a.get(k,0)) for a in suites) for k in ('tests','errors','failures','skipped')}
    assert tests['tests'] >= 3 and tests['errors'] == tests['failures'] == tests['skipped'] == 0
    r.save(ART / 'EXACT_MARK_DATA_REQUEST.json', {'unique_events': len(exact), 'events': list(exact.values()), 'purchase_made': False})
    r.save(ART / 'INDEPENDENT_VERIFICATION.json', {'all_passed': True, **dict(counts), 'tests': tests,
        'results_sha256': r.sha(ART / 'RESULTS.json'), 'exact_mark_unique_events_needed': len(exact),
        'goal_complete': False, 'live_signoff': 'NOT_GRANTED',
        'qualification': 'Accounting and reported quality flags reconciled; this is not approval of nodes with unsupported fills.'})
    print({'all_passed': True, **dict(counts), 'tests': tests}, flush=True)


if __name__ == '__main__':
    main()
