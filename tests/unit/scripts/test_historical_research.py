import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from historical_research_inputs import QuoteSeries
from prepare_historical_research import grid_audit, ms


def frame(times):
    return pd.DataFrame(dict(open_time=times, open=100., high=102., low=99., close=101.))


def test_units_ms_us_and_ns_produce_same_epoch():
    source = pd.Series(pd.to_datetime(["2025-09-01T00:00:00Z"]))
    expected = [1756684800000]
    for unit in ["ms", "us", "ns"]:
        assert ms(source.dt.as_unit(unit)).tolist() == expected


def test_grid_rejects_equal_count_with_missing_duplicate_or_offgrid():
    begin = pd.Timestamp(0, unit="ms", tz="UTC")
    end = pd.Timestamp(900000, unit="ms", tz="UTC")
    assert grid_audit(frame([0, 300000, 600000]), begin, end)["complete"]
    for times in [[0, 300000, 300000], [0, 300000, 600001]]:
        assert not grid_audit(frame(times), begin, end)["complete"]


def test_bad_ohlc_invalidates_grid_even_when_timestamps_complete():
    begin = pd.Timestamp(0, unit="ms", tz="UTC")
    end = pd.Timestamp(300000, unit="ms", tz="UTC")
    raw = frame([0])
    raw.loc[0, "close"] = 200
    assert not grid_audit(raw, begin, end)["complete"]
    raw.loc[0, "close"] = np.nan
    assert not grid_audit(raw, begin, end)["complete"]


def test_quote_separates_closed_information_from_next_open():
    trade, mark = frame([0, 300000, 600000]), frame([0, 300000, 600000])
    trade["open"] = [100, 200, 300]
    trade["close"] = [101, 201, 301]
    mark["close"] = [99, 199, 299]
    quote = QuoteSeries(trade, mark)
    assert quote[300000] == dict(execution_close=101., mark=99., entry_open=200.)
    assert quote.get(0) is None
    assert np.isnan(quote[900000]["entry_open"])
    assert quote[900000]["mark"] == 299


def test_missing_previous_candle_not_silently_forward_filled():
    quote = QuoteSeries(frame([0, 600000]), frame([0, 600000]))
    assert np.isnan(quote[300000]["entry_open"])
    assert quote.get(600000) is None
    with pytest.raises(KeyError):
        quote[600000]


def test_duplicate_prices_rejected():
    with pytest.raises(ValueError):
        QuoteSeries(frame([0, 0]), frame([0, 300000]))
