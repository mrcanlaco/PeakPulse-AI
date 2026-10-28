"""Public GET-only data adapter for prospective paper observation."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import threading
import time

import numpy as np
import pandas as pd
import requests
import research_v407 as history

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT/'artifacts/fibo_trend_short/paper_oos_v1'
BASE_URL = 'https://fapi.binance.com'
HOUR = 3_600_000
DAY = 24*HOUR
BAR = 300_000
ALLOWED = {'time', 'exchangeInfo', 'premiumIndex', 'klines', 'fundingRate', 'ticker/bookTicker'}
_lock = threading.Lock()
_next = 0.


def now_ms(): return time.time_ns()//1_000_000
def read(path): return json.loads(Path(path).read_text(encoding='utf8'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def utc(ms): return pd.Timestamp(int(ms), unit='ms', tz='UTC')


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')), encoding='utf8')
    temp.replace(path)


def request(endpoint, params=None, *, cache=False):
    global _next
    if endpoint not in ALLOWED:
        raise ValueError('Only explicitly allowed public market-data GET endpoints')
    params = params or {}
    key = hashlib.sha256(json.dumps([endpoint, params], sort_keys=True).encode()).hexdigest()
    path = ART/'raw'/endpoint.replace('/', '_')/(key+'.json.gz') if cache else None
    if path is not None and path.exists():
        with gzip.open(path, 'rt', encoding='utf8') as fh: saved = json.load(fh)
        if saved['endpoint'] != endpoint or saved['params'] != params: raise ValueError('Raw cache identity mismatch')
        return saved['data'], {'path': str(path), 'sha256': sha(path), 'received_ms': saved['received_ms']}
    limit = int(params.get('limit', 1))
    weight = (1 if limit < 100 else 2 if limit < 500 else 5 if limit <= 1000 else 10) if endpoint == 'klines' else 1
    interval = max(weight/12., .8 if endpoint == 'fundingRate' else .12)
    for attempt in range(4):
        with _lock:
            slot = max(time.monotonic(), _next); _next = slot+interval
        time.sleep(max(0., slot-time.monotonic()))
        sent = now_ms()
        response = requests.get(BASE_URL+'/fapi/v1/'+endpoint, params=params, timeout=25)
        received = now_ms()
        if response.status_code in (418, 429):
            time.sleep(min(60., max(5., float(response.headers.get('Retry-After', 30))))); continue
        if response.status_code >= 500:
            time.sleep(2**attempt); continue
        response.raise_for_status(); data = response.json()
        if path is None:
            path = ART/'raw'/endpoint.replace('/', '_')/(str(received)+'_'+key+'.json.gz')
        path.parent.mkdir(parents=True, exist_ok=True)
        value = {'endpoint': endpoint, 'params': params, 'sent_ms': sent, 'received_ms': received,
                 'data': data, 'http_date': response.headers.get('Date')}
        with gzip.open(path, 'wt', encoding='utf8') as fh: json.dump(value, fh, allow_nan=False, separators=(',', ':'))
        return data, {'path': str(path), 'sha256': sha(path), 'received_ms': received}
    raise RuntimeError('Public endpoint retries exhausted: '+endpoint)


def server_clock():
    before = now_ms(); value, receipt = request('time'); after = now_ms()
    offset = int(value['serverTime'])-(before+after)//2
    if abs(offset) > 5000 or after-before > 10000:
        raise RuntimeError('Clock synchronization outside paper tolerance')
    return offset, receipt


def eligible_contracts(info, at_ms):
    output = {}
    for row in info['symbols']:
        if (row.get('status') == 'TRADING' and row.get('contractType') == 'PERPETUAL'
                and row.get('quoteAsset') == row.get('marginAsset') == 'USDT'
                and row.get('underlyingType') == 'COIN' and row['symbol'] not in history.EXCLUDE
                and int(row['onboardDate']) <= at_ms < int(row['deliveryDate'])):
            output[row['symbol']] = row
    return output


def klines_frame(rows, interval_ms, start_ms, end_ms):
    output = []
    for a in rows:
        t = int(a[0]); close = int(a[6])+1
        if t < start_ms or close > end_ms: raise ValueError('Out-of-range or unclosed market candle')
        if t % interval_ms or close != t+interval_ms: raise ValueError('Off-grid/incomplete candle')
        vals = [float(a[i]) for i in (1, 2, 3, 4, 5, 7)]
        o, h, l, c, v, q = vals
        if not all(math.isfinite(x) for x in vals) or min(o, h, l, c) <= 0 or min(v, q) < 0 or h < max(o, c, l) or l > min(o, c):
            raise ValueError('Invalid OHLCV')
        output.append([t, *vals])
    frame = pd.DataFrame(output, columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'quote_volume'])
    frame['open_time'] = pd.to_datetime(frame.open_time, unit='ms', utc=True)
    frame = frame.set_index('open_time')
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing: raise ValueError('Unordered/duplicate candles')
    return frame


def load_range(symbol, interval, duration, start, end):
    parts = []; receipts = []; cursor = int(start)
    while cursor+duration <= end:
        # Limit each response to the requested closed range, including partial pages.
        rows, receipt = request('klines', {'symbol': symbol, 'interval': interval, 'startTime': cursor,
            'endTime': int(end)-1, 'limit': 1000}, cache=True)
        if not isinstance(rows, list): raise ValueError('Unexpected klines payload')
        receipts.append(receipt)
        if not rows: break
        part = klines_frame(rows, duration, cursor, int(end))
        parts.append(part); cursor = int(rows[-1][0])+duration
        if len(rows) < 1000: break
    return (pd.concat(parts) if parts else klines_frame([], duration, start, end)), receipts


def rank_row(symbol, daily, four_hour, cutoff):
    lower = utc(cutoff-DAY*63); upper = utc(cutoff)
    if len(daily) and (daily.index+pd.Timedelta(days=1) > upper).any(): raise ValueError('Future daily ranking input')
    if len(four_hour) and (four_hour.index+pd.Timedelta(hours=4) > upper).any(): raise ValueError('Future H4 ranking input')
    active = daily.loc[(daily.index >= lower) & (daily.index < upper), 'quote_volume']
    active = active[active > 0]
    h = four_hour.loc[(four_hour.index >= lower) & (four_hour.index+pd.Timedelta(hours=4) <= upper)]
    if len(active) < 50 or len(h) < 10: return None
    wick = (h.high-h[['open', 'close']].max(axis=1))/h.close*100
    p90 = float(np.percentile(wick, 90))
    if p90 > 3.2: return None
    return {'symbol': symbol, 'median_quote_volume': float(active.median()), 'active_days': len(active), 'wick_p90_pct': p90}


def prepare_membership(cutoff, *, initial=False):
    label = utc(cutoff).strftime('%Y-%m')
    output = ART/'membership'/f'{label}.json'
    if output.exists(): return read(output)
    info, receipt = request('exchangeInfo'); contracts = eligible_contracts(info, receipt['received_ms'])
    jobs = ART/'preparation'/f'universe_{cutoff}'; jobs.mkdir(parents=True, exist_ok=True)
    def one(symbol):
        file = jobs/(symbol+'.json')
        if file.exists(): return read(file)
        daily, a = load_range(symbol, '1d', DAY, cutoff-63*DAY, cutoff)
        h4, b = load_range(symbol, '4h', 4*HOUR, cutoff-63*DAY, cutoff)
        value = {'symbol': symbol, 'ranking': rank_row(symbol, daily, h4, cutoff), 'sources': a+b}
        save(file, value); return value
    rows = []; done = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(one, s) for s in sorted(contracts)]
        for future in as_completed(futures):
            value = future.result(); done += 1
            if value['ranking'] is not None: rows.append(value['ranking'])
            if done % 50 == 0: print(f'PIT preparation {done}/{len(contracts)}', flush=True)
    members = sorted(rows, key=lambda a: (-a['median_quote_volume'], a['symbol']))[:50]
    if not members: raise RuntimeError('No eligible paper universe')
    value = {'month': label, 'cutoff_ms': cutoff, 'effective_from_ms': now_ms(), 'initial_partial_month': initial,
        'ranking_interval': '[cutoff-63d,cutoff)', 'exchange_info': receipt, 'eligible_contracts': len(contracts),
        'members': members, 'contracts': {a['symbol']: contracts[a['symbol']] for a in members},
        'ranking_receipts': {p.name: sha(p) for p in jobs.glob('*.json')},
        'warmup_only': True, 'historical_backtest': False}
    save(output, value); return value


def prepare_hourly(symbol, contract, cutoff):
    path = ART/'hourly'/f'{symbol}.parquet'
    receipt = ART/'hourly'/f'{symbol}.json'
    onboard = int(contract['onboardDate'])
    start = max(int(pd.Timestamp('2020-01-01T00:00:00Z').timestamp()*1000), ((onboard+HOUR-1)//HOUR)*HOUR)
    sources = []; parts = []
    if path.exists():
        meta = read(receipt)
        if meta['onboard_ms'] != onboard: raise RuntimeError('Contract identity changed; new episode required')
        if sha(path) != meta['sha256']: raise RuntimeError('Hourly cache changed')
        frame = pd.read_parquet(path); parts.append(frame); sources = meta['sources']
        if len(frame): start = int(frame.index[-1].timestamp()*1000)+HOUR
    else:
        manifest = read(ROOT/'artifacts/fibo_trend_short/research_v4_0_21/OBSERVED_VIEWS.json')
        for view in manifest.get(symbol, []):
            if sha(view['path']) != view['sha256']: raise RuntimeError('Frozen historical source changed')
            end = min(cutoff, int(pd.Timestamp('2026-01-01T00:00:00Z').timestamp()*1000))
            if end <= start: continue
            f = pd.read_parquet(view['path'], filters=[('open_time', '>=', utc(start)), ('open_time', '<', utc(end))])
            if len(f):
                parts.append(history.h1_frame(f)); sources.append({'legacy_path': view['path'], 'sha256': view['sha256']})
        if parts:
            merged = pd.concat(parts).sort_index()
            if not merged.index.is_unique: raise RuntimeError('Overlapping contract views')
            parts = [merged]; start = int(merged.index[-1].timestamp()*1000)+HOUR
    if start < cutoff:
        extra, refs = load_range(symbol, '1h', HOUR, start, cutoff)
        sources.extend(refs)
        if len(extra): parts.append(extra)
    if not parts: raise RuntimeError('No signal warmup: '+symbol)
    frame = pd.concat(parts).sort_index()
    if not frame.index.is_unique or (frame.index+pd.Timedelta(hours=1) > utc(cutoff)).any(): raise RuntimeError('Duplicate/future signal warmup')
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp.parquet'); frame.to_parquet(temp); temp.replace(path)
    save(receipt, {'symbol': symbol, 'onboard_ms': onboard, 'sha256': sha(path), 'sources': sources,
        'cutoff_ms': cutoff, 'last_hour_close_ms': int(frame.index[-1].timestamp()*1000)+HOUR,
        'rows': len(frame), 'purpose': 'Unscored causal indicator warmup, never post2025 historical PnL'})
    return frame
