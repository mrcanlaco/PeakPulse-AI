import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"scripts"))
from short_multitimeframe_signals import aggregate,daily_features,features,generate


def sample(n=3000):
    rng=np.random.default_rng(75)
    c=100*np.exp(np.cumsum(rng.normal(-.0003,.02,n)))
    return pd.DataFrame(dict(open=c*1.001,high=c*1.02,low=c*.98,close=c,
                             quote_volume=rng.uniform(100000,900000,n)),
                        index=pd.date_range("2025-08-01T01:00:00Z",periods=n,freq="1h"))


def test_four_hour_context_uses_only_hours_already_closed():
    h=sample(10);a=aggregate(h,"4h",4)
    first=pd.Timestamp("2025-08-01T04:00:00Z")
    assert a.at[first,"close"]==h.iloc[3].close
    assert a.at[first,"high"]==h.iloc[:4].high.max()
    assert a.at[first,"hours"]==4
    assert pd.isna(a.iloc[-1].close)


def test_daily_context_not_available_before_midnight_completion():
    h=sample(25);d=daily_features(h)
    assert d.iloc[0].close==h.iloc[23].close
    assert pd.isna(d.iloc[1].close)
    assert not d.ready.any()


def test_features_and_signals_prefix_invariant_inside_four_hour_candle():
    h=sample();cut=h.index[1700]
    full=features(h);prefix=features(h.loc[:cut])
    pd.testing.assert_frame_equal(full.loc[:cut],prefix.loc[:cut])
    a=generate({"X":h,"BTCUSDT":h});b=generate({"X":h.loc[:cut],"BTCUSDT":h.loc[:cut]})
    at=int(cut.timestamp()*1000)
    assert any(a.values())
    assert {k:[r for r in v if r["at"]<=at] for k,v in a.items()}==b
    assert not any(r["at"]>at for v in b.values() for r in v)


def test_missing_hour_invalidates_higher_timeframe_bar():
    h=sample(100);damaged=h.drop(h.index[2])
    a=aggregate(damaged,"4h",4)
    assert a.iloc[0].hours==3 and pd.isna(a.iloc[0].close)


def test_signals_are_24h_spaced_with_frozen_four_hour_atr():
    h=sample();f=features(h)
    generated=generate({"X":h,"BTCUSDT":h})
    for rows in generated.values():
        assert all(b["at"]-a["at"]>=86400000 for a,b in zip(rows,rows[1:]))
        for row in rows:
            t=pd.Timestamp(row["at"],unit="ms",tz="UTC")
            assert row["atr"]==f.at[t,"atr"] and row["at"]%14400000==0
