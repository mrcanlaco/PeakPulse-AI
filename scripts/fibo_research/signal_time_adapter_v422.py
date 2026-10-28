"""Normalize timestamp representation before the frozen closed-bar wrapper.

Pandas can represent identical hourly timestamps as ns/us/ms. The registered
wrapper's Index.equals check also compares that storage unit. Converting both
the index and decision timestamp to ns preserves values, including sub-us
off-grid data which must still be rejected. No signal or market values change.
"""
import pandas as pd
import signal_snapshot_v422 as original


def closed_signal_snapshots(symbol, hourly, btc_htf, *, as_of):
    t = pd.Timestamp(as_of).as_unit('ns')
    normalized = hourly.copy(deep=False)
    if isinstance(normalized.index, pd.DatetimeIndex):
        normalized.index = normalized.index.as_unit('ns')
    return original.closed_signal_snapshots(symbol, normalized, btc_htf, as_of=t)
