import sys
from pathlib import Path
from collections import Counter
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
from account_trace_replay import simulate
from account_side_quota_replay import simulate as original
from research_capacity_config import configuration

RULE = dict(market_step='0.001', step_size='0.001', min_qty=.001,
            market_min_qty=.001, max_qty=100000, market_max_qty=100000,
            min_notional=5, tick_size='0.001')


def run(events, *, caps=None, closes=(100, 101, 102), funding=None, policy=None):
    times = [i * 300000 for i in range(len(closes))]
    points = {t: dict(mark=p, execution_close=p, entry_open=p) for t, p in zip(times, closes)}
    rules = {x['symbol']: RULE for batch in events.values() for x in batch}
    p = dict(entry_parts=3, entry_mode='favorable', entry_step_atr=.25, fixed_tp_usdt=5)
    if caps is not None: p['side_caps'] = caps
    p.update(policy or {})
    args = (times, events, lambda _: points, rules, funding or (lambda _: []), configuration(5, .0005, 20))
    old = original(*args, research_policy=p)
    new = simulate(*args, research_policy=p)
    assert {k: v for k, v in new.items() if k != 'decisions'} == old
    return new


def event(symbol, key=None, side='SHORT'):
    return dict(symbol=symbol, event_id=key or symbol, side=side, atr=2)


@pytest.mark.parametrize('side', ['LONG', 'SHORT'])
@pytest.mark.parametrize('caps', [None, dict(LONG=2, SHORT=3)])
def test_trace_does_not_change_fills_or_money(side, caps):
    r = run({0: [event(str(i), side=side) for i in range(7)]}, caps=caps)
    d = r['decisions']
    assert sum(x['status'] == 'accepted' for x in d) == r['entries']
    assert Counter(x['reason'] for x in d if x['status'] == 'rejected') == r['rejections']


def test_duplicate_and_same_coin_are_separate_and_snapshot_is_before_admission():
    r = run({0: [event('X'), event('X'), event('X', 'opposite', 'LONG'), event('Y')]})
    d = r['decisions']
    assert [x['reason'] for x in d] == ['accepted', 'duplicate_episode', 'position_limit', 'accepted']
    assert d[0]['occupied'] == [] and d[2]['same_coin'] and not d[2]['full']
    assert [x['event_id'] for x in d[3]['occupied']] == ['X']


def test_exit_releases_coin_before_next_trace():
    r = run({0: [event('X')], 300000: [event('Y')]}, policy=dict(max_hold_hours=1/12))
    assert r['decisions'][1]['occupied'] == []


def test_funding_error_marks_failed_and_unprocessed_signals():
    def fail(_): raise OSError('fixture')
    r = run({0: [event('X'), event('Y')], 300000: [event('Z')]}, funding=fail)
    assert [x['status'] for x in r['decisions']] == ['error', 'not_processed', 'not_processed']
    assert r['ending_equity'] is None


def test_drawdown_rejection_keeps_losing_position_visible():
    r = run({0: [event('X', side='LONG')], 600000: [event('Y')]},
            closes=(100, 60, 50), policy=dict(position_notional=1000))
    d = r['decisions'][1]
    assert d['reason'] == 'drawdown_paused' and d['paused']
    assert d['occupied'][0]['net_mark'] < 0


def test_signal_outside_time_grid_is_not_invented_as_rejection():
    r = run({1: [event('X')]})
    assert r['decisions'][0]['status'] == 'not_processed' and not r['rejections']


def test_open_and_invalid_singletons_are_not_counted_as_closed_winners():
    from diagnose_signal_opportunities import outcome, statistics
    e = dict(event('X', side='LONG'), at=0)
    r = run({0: [e]}, closes=(100, 90, 80))
    o = outcome(r, e, 600000)
    assert o['state'] == 'open' and o['net_mtm'] < 0 and o['closed_net'] is None
    rejected = run({0: [e]}, policy=dict(position_notional=1))
    no = outcome(rejected, e, 600000)
    assert no['state'] == 'not_entered' and no['net_mtm'] is None
    stats = statistics([o, no])
    assert stats['events'] == 2 and stats['evaluated_entries'] == 1
    assert stats['positive_mtm'] == 0 and stats['states'] == dict(open=1, not_entered=1)


def test_incomplete_singleton_is_not_reported_as_terminal_mark():
    from diagnose_signal_opportunities import outcome
    e = dict(event('X'), at=0)
    r = run({0: [e]}, closes=(100, 101, 102))
    r.update(ending_equity=None, pnl=None, errors=['fixture_missing_mark'])
    o = outcome(r, e, 600000)
    assert o['state'] == 'incomplete' and o['net_mtm'] is None
