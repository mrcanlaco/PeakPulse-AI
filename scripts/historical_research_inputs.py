"""Memory-bounded, closed-bar quotes for the frozen historical research set."""

import json
import math

import numpy as np
import pandas as pd
from compare_account_risk import sha
from prepare_historical_research import OUT, STEP


class QuoteSeries:
    """Map a decision time to last closed trade/mark and next trade open.

    Missing timestamps are not filled. Arrays avoid millions of nested dicts.
    """

    def __init__(self, trade, mark):
        self.trade_times = trade.open_time.to_numpy(dtype=np.int64)
        self.mark_times = mark.open_time.to_numpy(dtype=np.int64)
        if np.any(np.diff(self.trade_times) <= 0) or np.any(np.diff(self.mark_times) <= 0):
            raise ValueError("unordered_or_duplicate_prices")
        self.opens = trade.open.to_numpy(dtype=float)
        self.closes = trade.close.to_numpy(dtype=float)
        self.marks = mark.close.to_numpy(dtype=float)
        self.trade_regular = bool(len(self.trade_times) and np.all(np.diff(self.trade_times) == STEP))
        self.mark_regular = bool(len(self.mark_times) and np.all(np.diff(self.mark_times) == STEP))
        self.trade_start = int(self.trade_times[0]) if len(self.trade_times) else 0
        self.mark_start = int(self.mark_times[0]) if len(self.mark_times) else 0

    def get(self, at, default=None):
        i = (at - STEP - self.trade_start) // STEP if self.trade_regular else int(np.searchsorted(self.trade_times, at - STEP))
        j = (at - STEP - self.mark_start) // STEP if self.mark_regular else int(np.searchsorted(self.mark_times, at - STEP))
        if (i < 0 or j < 0 or i >= len(self.trade_times) or self.trade_times[i] != at - STEP or
                j >= len(self.mark_times) or self.mark_times[j] != at - STEP):
            return default
        next_open = self.opens[i+1] if i+1 < len(self.trade_times) and self.trade_times[i+1] == at else math.nan
        return dict(execution_close=float(self.closes[i]), mark=float(self.marks[j]), entry_open=float(next_open))

    def __getitem__(self, at):
        result = self.get(at)
        if result is None:
            raise KeyError(at)
        return result


def load():
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    if not manifest["data_ready"]:
        raise ValueError("historical_data_not_verified")
    symbols = manifest["universe"]["symbols"]
    local = {r["symbol"]: r for r in manifest["local"]}
    public = {r["symbol"]: r for r in manifest["public"]}
    prices, funding, frames = {}, {}, {}
    for s in [*symbols, "BTCUSDT"]:
        feature = OUT / "features" / f"{s}.parquet"
        assert sha(feature) == local[s]["features_sha256"]
        frames[s] = pd.read_parquet(feature)
        if s == "BTCUSDT":
            continue
        for directory, proof, field in [("trade", local[s], "trade_sha256"),
                                         ("mark", public[s], "mark_sha256"),
                                         ("funding", public[s], "funding_sha256")]:
            assert sha(OUT / directory / f"{s}.parquet") == proof[field]
        prices[s] = QuoteSeries(pd.read_parquet(OUT / "trade" / f"{s}.parquet"),
                                pd.read_parquet(OUT / "mark" / f"{s}.parquet"))
        rows = pd.read_parquet(OUT / "funding" / f"{s}.parquet")
        funding[s] = [(int(t), float(r), float(m)) for t,r,m in rows.itertuples(index=False, name=None)]
    return prices, funding, frames
