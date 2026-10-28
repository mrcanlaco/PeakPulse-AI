from pathlib import Path
import sys
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/fibo_research'))
import signal_snapshot_v422 as s
import build_signal_snapshot_v422 as build


def frames():
    index = pd.date_range('2025-01-01', periods=120, freq='h', tz='UTC')
    frame = pd.DataFrame({'open': 100., 'high': 101., 'low': 99., 'close': 100.,
                          'volume': 10., 'quote_volume': 1000.}, index=index)
    btc = {tf: s.calc_htf_features_no_bfill(s.resample_1h_to_htf(frame, tf)) for tf in ('4h', '1d')}
    return frame, btc, index[-1] + pd.Timedelta(hours=1)


def test_future_h1_rejected_without_entering_detector(monkeypatch):
    h, b, t = frames()
    monkeypatch.setattr(s, '_collect_closed', lambda *a, **k: pytest.fail('future reached detector'))
    with pytest.raises(ValueError, match='future H1'):
        s.closed_signal_snapshots('X', h, b, as_of=t-pd.Timedelta(hours=1))


def test_future_btc_context_is_rejected(monkeypatch):
    h, b, t = frames()
    b['4h'].loc[b['4h'].index[-1], 'close_time'] = t + pd.Timedelta(hours=1)
    monkeypatch.setattr(s, '_collect_closed', lambda *a, **k: pytest.fail('future BTC reached detector'))
    with pytest.raises(ValueError, match='future BTC'):
        s.closed_signal_snapshots('X', h, b, as_of=t)


def test_missing_latest_bar_is_not_a_current_signal():
    h, b, t = frames()
    with pytest.raises(ValueError, match='Latest completed'):
        s.closed_signal_snapshots('X', h.iloc[:-1], b, as_of=t)


def test_past_hour_gap_blocks_signal_without_filling_it(monkeypatch):
    h, b, t = frames()
    h = h.drop(h.index[-3])
    monkeypatch.setattr(s, '_collect_closed', lambda *a, **k: pytest.fail('gap reached detector'))
    assert s.closed_signal_snapshots('X', h, b, as_of=t) == []


def test_closed_snapshot_leaves_market_inputs_unchanged():
    h, b, t = frames()
    before = h.copy(deep=True)
    btc_before = {k: a.copy(deep=True) for k, a in b.items()}
    assert s.closed_signal_snapshots('X', h, b, as_of=t) == []
    pd.testing.assert_frame_equal(h, before)
    for tf in b:
        pd.testing.assert_frame_equal(b[tf], btc_before[tf])


def test_generated_signal_equations_are_exactly_traceable():
    assert Path(s.__file__).read_text(encoding='utf8') == build.render()
