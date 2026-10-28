"""One-time, reviewable extraction of signal logic from the frozen batch collector.

The generated module is ordinary Python, not a runtime monkey-patch. Historical
sources stay byte-identical. Its API deliberately has no fill or outcome input.
"""
from pathlib import Path
import ast
import hashlib

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'scripts/fibo_research/universe_reaudit_v402_worker.py'
TARGET = ROOT / 'scripts/fibo_research/signal_snapshot_v422.py'

HEADER = '''"""Closed-bar signal snapshots; no simulated exits and no order submission.

Signal equations/configuration are extracted from the frozen v402 batch
collector. This is a research component, not a running paper-trading system.
PIT membership, lifecycle eligibility, scheduled fills and portfolio admission
remain separate decisions, made using information available at their time.
"""
from typing import Any
import numpy as np
import pandas as pd
from universe_reaudit_v402_worker import (
    FiboTrendShortConfig, UNIVERSE_MILESTONES, _check_milestone_gate,
    resample_1h_to_htf, calc_htf_features_no_bfill, detect_htf_reversal_wave,
    compute_fibonacci_levels, evaluate_h1_confirmation,
    compute_orthogonal_conviction_score, compute_atr, build_fibo_trade_setup,
)

'''

WRAPPER = '''

def _aware(value):
    value = pd.Timestamp(value)
    if value.tzinfo is None:
        raise ValueError('An explicit UTC-aware decision timestamp is required')
    return value.tz_convert('UTC')


def closed_signal_snapshots(symbol, hourly, btc_htf, *, as_of):
    """Evaluate only the latest completed H1; reject future/stale input.

    Output prices are signal references, never claimed executable fills. No
    portfolio/wave state is consumed here. All input frames must already be
    restricted to this timestamp and to one contract identity/episode.
    """
    t = _aware(as_of)
    if t != t.floor('h'):
        raise ValueError('Decision timestamp must be an H1 close boundary')
    if not isinstance(hourly.index, pd.DatetimeIndex) or hourly.index.tz is None:
        raise ValueError('H1 input requires a timezone-aware DatetimeIndex')
    if not hourly.index.is_unique or not hourly.index.is_monotonic_increasing:
        raise ValueError('H1 candles must be unique and chronological')
    if not (hourly.index == hourly.index.floor('h')).all():
        raise ValueError('H1 candles are off the hourly grid')
    if len(hourly) and (hourly.index + pd.Timedelta(hours=1) > t).any():
        raise ValueError('Unclosed or future H1 candle')
    for tf in ('4h', '1d'):
        b = btc_htf[tf]
        closed = pd.DatetimeIndex(b['close_time'])
        if len(closed) and (closed.tz is None or (closed > t).any()):
            raise ValueError('Unclosed or future BTC context')
    if not len(hourly) or hourly.index[-1] + pd.Timedelta(hours=1) != t:
        raise ValueError('Latest completed H1 is missing')
    values = hourly[['open', 'high', 'low', 'close', 'volume']].to_numpy()
    if not np.isfinite(values).all() or (values[:, :4] <= 0).any() or (values[:, 4] < 0).any():
        raise ValueError('Invalid H1 prices or volume')
    if ((hourly.high < hourly[['open', 'close', 'low']].max(axis=1)) |
        (hourly.low > hourly[['open', 'close', 'high']].min(axis=1))).any():
        raise ValueError('Invalid H1 OHLC ordering')
    expected = pd.date_range(t - pd.Timedelta(hours=24), periods=24, freq='h')
    if not hourly.index[-24:].equals(expected):
        return []
    raw = _collect_closed(symbol, hourly, btc_htf,
                          entry_start_ts=t-pd.Timedelta(hours=1),
                          entry_end_ts=t-pd.Timedelta(hours=1))
    assert all(pd.Timestamp(a['decision_time']) == t for a in raw)
    return raw
'''


def render():
    source = SOURCE.read_text(encoding='utf8')
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)
                and n.name == 'collect_symbol_milestones_v402')
    code = ast.get_source_segment(source, node)
    def replace_once(old, new):
        nonlocal code
        assert code.count(old) == 1, old
        code = code.replace(old, new, 1)
    replace_once('def collect_symbol_milestones_v402(', 'def _collect_closed(')
    replace_once(') -> dict[str, Any]:', ') -> list[dict[str, Any]]:')
    replace_once('    allowed_yms: set[str] | None = None,\n    hard_cutoff_0831: bool = False,\n', '')
    start = code.index('    """Single-pass collector')
    end = code.index('    cfg =', start)
    code = code[:start] + '    """Same signal equations as the historical collector, including last H1."""\n' + code[end:]
    replace_once('    indep_by_m: dict[str, list[dict[str, Any]]] = {m: [] for m in UNIVERSE_MILESTONES}\n    subset_by_m: dict[str, list[dict[str, Any]]] = {m: [] for m in UNIVERSE_MILESTONES}\n\n', '')
    replace_once('return {"independent": indep_by_m, "subset_from_m1": subset_by_m, "raw_candidates": []}', 'return []')
    replace_once('range(24, len(h1_records) - 2)', 'range(24, len(h1_records))')
    replace_once('        horizon = cfg.horizon_hours if tf == "4h" else cfg.horizon_hours_1d\n', '')
    start = code.index('            future_slice =')
    end = code.index('            peak_bar =', start)
    code = code[:start] + code[end:]
    start = code.index('            sim_std = simulate_trade_v2(')
    end = code.index('            wave_key =', start)
    code = code[:start] + code[end:]
    for name in ('sim_std', 'sim_m6', 'sim_std_0831', 'sim_m6_0831'):
        replace_once(f'                    "{name}": {name},\n', '')
    code = code[:code.index('    exec_res =')] + '    return raw_candidates\n'
    for forbidden in ('future_slice', 'simulate_trade_v2', 'execute_symbol_candidates_from_raw', 'sim_std', 'sim_m6'):
        assert forbidden not in code
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    result = HEADER + f'BATCH_SOURCE_SHA256 = "{digest}"\n\n\n' + code + WRAPPER
    ast.parse(result)
    return result


if __name__ == '__main__':
    if TARGET.exists():
        raise FileExistsError('Generated source already exists; verify rather than overwrite')
    TARGET.write_text(render(), encoding='utf8')
    print(TARGET)
