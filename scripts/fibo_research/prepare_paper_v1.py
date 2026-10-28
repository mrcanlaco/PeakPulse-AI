"""Collect unscored warmup and lock the initial prospective universe."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import json
import paper_data_v1 as d


def prepare():
    authorization = d.read(d.ART/'AUTHORIZATION.json')
    assert authorization['orders_allowed'] is False
    prior = d.ROOT/'artifacts/fibo_trend_short/research_v4_0_25'
    cp = d.read(prior/'CHECKPOINT.json')
    for name, digest in cp['additional_sources'].items():
        assert d.sha(d.ROOT/name) == digest, name
    protocol = d.ART/'PREPARATION_PROTOCOL.json'
    if not protocol.exists():
        offset, clock = d.server_clock()
        now = d.now_ms()+offset
        d.save(protocol, {'registered_at_utc': datetime.now(timezone.utc).isoformat(),
            'authorization_sha256': d.sha(d.ART/'AUTHORIZATION.json'),
            'sources': {str(p): d.sha(p) for p in (Path(__file__), Path(d.__file__))},
            'prior_sources': cp['additional_sources'],
            'ranking_cutoff_ms': now//d.DAY*d.DAY, 'hourly_cutoff_ms': now//d.HOUR*d.HOUR,
            'clock_receipt': clock, 'purpose': 'Unscored warmup only; no post2025 backtest, optimization or PnL.',
            'ranking': 'Initial partial-month ranking uses prior63 complete UTC days ending at current day start. Future refreshes use calendar month boundaries; effective only after the ranking is recorded.',
            'signal_history': '2020 onward, bounded by current contract onboardDate. Reuse frozen pre2026 H1 aggregates and append public closed H1 warmup. Never combine relaunch identities.',
            'universe': 'Currently trading COIN USDT-margin perpetuals with original fixed exclusions. At least50 positive quote-volume days, H4 upper-wick p90<=3.2%; top50 median daily quote volume.',
            'orders_allowed': False, 'paper_scoring_started': False})
    p = d.read(protocol)
    for name, digest in p['sources'].items(): assert d.sha(name) == digest
    membership = d.prepare_membership(p['ranking_cutoff_ms'], initial=True)
    info, info_ref = d.request('exchangeInfo')
    contracts = {a['symbol']: a for a in info['symbols']}
    symbols = sorted({a['symbol'] for a in membership['members']} | {'BTCUSDT'})
    completed = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(d.prepare_hourly, s, contracts[s], p['hourly_cutoff_ms']): s for s in symbols}
        for future in as_completed(jobs):
            symbol = jobs[future]; frame = future.result()
            completed[symbol] = {'rows': len(frame), 'last_closed_ms': int(frame.index[-1].timestamp()*1000)+d.HOUR,
                'receipt_sha256': d.sha(d.ART/'hourly'/f'{symbol}.json')}
            d.save(d.ART/'PREPARATION_PROGRESS.json', {'complete': len(completed), 'required': len(symbols), 'symbols': completed})
            print(f'Warmup {len(completed)}/{len(symbols)} {symbol}: {len(frame)} closed H1 bars', flush=True)
    d.save(d.ART/'PREPARATION_COMPLETE.json', {'all_passed': True, 'protocol_sha256': d.sha(protocol),
        'membership_month': membership['month'], 'members': len(membership['members']), 'hourly_symbols': completed,
        'exchange_info': info_ref, 'completed_at_ms': d.now_ms(), 'scored_observations': 0, 'orders_allowed': False})
    print(json.dumps({'complete': True, 'members': len(membership['members']), 'warmup_symbols': len(completed)}), flush=True)


if __name__ == '__main__': prepare()
