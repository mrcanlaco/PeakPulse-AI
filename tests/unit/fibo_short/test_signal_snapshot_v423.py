from pathlib import Path
import sys
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/fibo_research'))
import signal_snapshot_v423 as s
import verify_signal_readiness_v423 as verify


def frames(n=120, unit='ns'):
    index = pd.date_range('2025-01-01', periods=n, freq='h', tz='UTC').as_unit(unit)
    h = pd.DataFrame({'open': 100., 'high': 101., 'low': 99., 'close': 100.,
                       'volume': 10., 'quote_volume': 1000.}, index=index)
    b = {tf: s.calc_htf_features_no_bfill(s.resample_1h_to_htf(h, tf)) for tf in ('4h','1d')}
    return h, b, index[-1]+pd.Timedelta(hours=1)


@pytest.mark.parametrize('index_unit', ['ns','us','ms'])
@pytest.mark.parametrize('timestamp_unit', ['ns','us','ms'])
def test_exact_time_resolution_equivalence(monkeypatch, index_unit, timestamp_unit):
    h,b,t = frames(unit=index_unit)
    before = h.copy(deep=True)
    monkeypatch.setattr(s, '_collect_closed', lambda *a, **k: [{'decision_time': t.isoformat()}])
    assert s.closed_signal_snapshots('X',h,b,as_of=t.as_unit(timestamp_unit)) == [{'decision_time':t.isoformat()}]
    pd.testing.assert_frame_equal(h,before)


@pytest.mark.parametrize('hours, expected', [(36,[]),(40,[10]),(61,[15])])
def test_early_episode_uses_available_htf_history(monkeypatch, hours, expected):
    h,b,t = frames(n=hours)
    seen = []
    def detector(symbol, bars, tf, config):
        seen.append(len(bars))
        return None
    monkeypatch.setattr(s, 'detect_htf_reversal_wave', detector)
    assert s.closed_signal_snapshots('X',h,b,as_of=t) == []
    assert seen == expected


def test_future_h1_is_rejected():
    h,b,t = frames()
    with pytest.raises(ValueError, match='future H1'):
        s.closed_signal_snapshots('X',h,b,as_of=t-pd.Timedelta(hours=1))


def test_future_btc_context_is_rejected():
    h,b,t = frames()
    b['4h'].loc[b['4h'].index[-1], 'close_time'] = t+pd.Timedelta(hours=1)
    with pytest.raises(ValueError, match='future BTC'):
        s.closed_signal_snapshots('X',h,b,as_of=t)


def test_off_grid_nanosecond_is_not_rounded_away():
    h,b,t = frames()
    times = list(h.index)
    times[-1] += pd.Timedelta(nanoseconds=1)
    h.index = pd.DatetimeIndex(times)
    with pytest.raises(ValueError, match='off the hourly grid'):
        s.closed_signal_snapshots('X',h,b,as_of=t)


def test_missing_past_bar_blocks_detection(monkeypatch):
    h,b,t = frames()
    h = h.drop(h.index[-4])
    monkeypatch.setattr(s, '_collect_closed', lambda *a, **k: pytest.fail('gap reached detector'))
    assert s.closed_signal_snapshots('X',h,b,as_of=t) == []


def test_generated_source_has_only_the_registered_changes():
    assert Path(s.__file__).read_text(encoding='utf8') == verify.generated_source()
