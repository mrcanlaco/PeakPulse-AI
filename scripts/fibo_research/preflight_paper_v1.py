"""Read-only warmup/schema checks. No trades, PnL, or scored OOS samples."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json
import pandas as pd
import paper_data_v1 as d
from paper_runner_v1 import funding_rows
import signal_snapshot_v423 as signals


def run():
    ready = d.read(d.ART/'PREPARATION_COMPLETE.json'); assert ready['all_passed']
    protocol = d.read(d.ART/'PREPARATION_PROTOCOL.json'); cutoff = protocol['hourly_cutoff_ms']
    frames = {}; sources = {}
    for symbol, record in ready['hourly_symbols'].items():
        path = d.ART/'hourly'/f'{symbol}.parquet'; meta = d.read(path.with_suffix('.json'))
        assert d.sha(path) == meta['sha256'] and d.sha(path.with_suffix('.json')) == record['receipt_sha256']
        frame = pd.read_parquet(path)
        assert int((frame.index[-1]+pd.Timedelta(hours=1)).timestamp()*1000) == cutoff, symbol
        frames[symbol] = frame; sources[symbol] = meta['sha256']
    btc = {tf: d.history.calc_htf_features_no_bfill(d.history.resample_1h_to_htf(frames['BTCUSDT'], tf)) for tf in ('4h','1d')}
    signal_counts = {}
    for symbol, frame in frames.items():
        if symbol == 'BTCUSDT': continue
        rows = signals.closed_signal_snapshots(symbol, frame, btc, as_of=d.utc(cutoff))
        assert all(pd.Timestamp(a['decision_time']) == d.utc(cutoff) for a in rows)
        signal_counts[symbol] = len(rows)
    settlement = {}
    def one(symbol):
        rows, receipt = d.request('fundingRate', {'symbol': symbol, 'startTime': cutoff-d.DAY, 'endTime': cutoff-1, 'limit':100})
        parsed = funding_rows(symbol, rows, cutoff-d.DAY, cutoff-1)
        if not parsed: raise ValueError('No recent realized funding: '+symbol)
        return symbol, {'events':len(parsed),'all_marks_exact':True,'receipt':receipt}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(one,s) for s in sorted(signal_counts)]
        for future in as_completed(futures):
            symbol, value = future.result(); settlement[symbol] = value
    result = {'all_passed':True,'checked_at_ms':d.now_ms(),'warmup_cutoff_ms':cutoff,
        'source_sha256':d.sha(Path(__file__)),'hourly_sha256':sources,
        'signal_feed_symbols':len(signal_counts),'unscored_signal_counts':signal_counts,
        'funding':settlement,'orders_allowed':False,'scored_trades':0,'historical_post2025_pnl':False}
    d.save(d.ART/'PREFLIGHT.json',result)
    print(json.dumps({'all_passed':True,'signal_symbols':len(signal_counts),'funding_symbols':len(settlement),'unscored_signals':sum(signal_counts.values()),'scored_trades':0}),flush=True)


if __name__ == '__main__':run()
