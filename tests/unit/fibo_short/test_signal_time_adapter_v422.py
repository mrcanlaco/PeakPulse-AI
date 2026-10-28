from pathlib import Path
import sys
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/fibo_research'))
import signal_time_adapter_v422 as a


def frames(unit):
    index = pd.date_range('2025-01-01', periods=120, freq='h', tz='UTC').as_unit(unit)
    h = pd.DataFrame({'open': 100., 'high': 101., 'low': 99., 'close': 100.,
                       'volume': 10., 'quote_volume': 1000.}, index=index)
    b = {tf: a.original.calc_htf_features_no_bfill(a.original.resample_1h_to_htf(h, tf))
         for tf in ('4h', '1d')}
    return h, b, index[-1] + pd.Timedelta(hours=1)


@pytest.mark.parametrize('index_unit', ['ns', 'us', 'ms'])
@pytest.mark.parametrize('decision_unit', ['ns', 'us', 'ms'])
def test_same_instants_reach_detector_for_all_storage_units(monkeypatch, index_unit, decision_unit):
    h, b, t = frames(index_unit)
    before = h.copy(deep=True)
    def detector(*args, **kwargs):
        return [{'decision_time': t.isoformat(), 'proof': 'detector_reached'}]
    monkeypatch.setattr(a.original, '_collect_closed', detector)
    result = a.closed_signal_snapshots('X', h, b, as_of=t.as_unit(decision_unit))
    assert result == [{'decision_time': t.isoformat(), 'proof': 'detector_reached'}]
    pd.testing.assert_frame_equal(h, before)


def test_normalization_does_not_round_away_off_grid_nanoseconds():
    h, b, t = frames('ns')
    changed = list(h.index)
    changed[-1] += pd.Timedelta(nanoseconds=1)
    h.index = pd.DatetimeIndex(changed)
    with pytest.raises(ValueError, match='off the hourly grid'):
        a.closed_signal_snapshots('X', h, b, as_of=t)
