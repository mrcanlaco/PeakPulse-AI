"""Data loader for multi-asset 1h klines and 8h funding rates (2020-2026)."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Tuple
import numpy as np
import pandas as pd
from dao_vang.research.protocol import (
    KLINES_DIR,
    FUNDING_DIR,
    UNIVERSE,
    TRAIN_START,
    TRAIN_END,
    VAL_START,
    VAL_END,
    TEST_START,
    TEST_END,
)


@dataclass
class AssetMarketData:
    symbol: str
    klines: pd.DataFrame  # index: DatetimeIndex (UTC), columns: open, high, low, close, volume
    funding_series: pd.Series  # aligned to klines index: funding rate at each hour (0 where no settlement)


def load_single_asset(symbol: str) -> AssetMarketData:
    kline_path = KLINES_DIR / f"{symbol}_1h.parquet"
    funding_path = FUNDING_DIR / f"{symbol}_funding.parquet"

    df_k = pd.read_parquet(kline_path)
    if not isinstance(df_k.index, pd.DatetimeIndex):
        if "open_time" in df_k.columns:
            df_k["open_time"] = pd.to_datetime(df_k["open_time"], utc=True)
            df_k = df_k.set_index("open_time")
        else:
            df_k.index = pd.to_datetime(df_k.index, utc=True)
    df_k = df_k.sort_index()

    # Reindex or verify hourly continuous grid
    df_k = df_k[["open", "high", "low", "close", "volume"]].astype(float)

    # Load funding
    df_f = pd.read_parquet(funding_path)
    if not isinstance(df_f.index, pd.DatetimeIndex):
        if "calc_time" in df_f.columns:
            df_f.index = pd.to_datetime(df_f["calc_time"], unit="ms", utc=True)
        elif "funding_time" in df_f.columns:
            df_f.index = pd.to_datetime(df_f["funding_time"], utc=True)
        else:
            df_f.index = pd.to_datetime(df_f.index, utc=True)
    df_f = df_f.sort_index()

    # Map funding onto hourly bars
    funding_col = "last_funding_rate" if "last_funding_rate" in df_f.columns else "funding_rate"
    funding_rates = df_f[funding_col].astype(float)

    # Floor funding index to nearest hour to align with klines
    funding_rates.index = funding_rates.index.floor("1h")
    # In case of duplicate timestamps within the same hour, take the last one
    funding_rates = funding_rates[~funding_rates.index.duplicated(keep="last")]

    aligned_funding = pd.Series(0.0, index=df_k.index)
    common_idx = df_k.index.intersection(funding_rates.index)
    aligned_funding.loc[common_idx] = funding_rates.loc[common_idx]

    return AssetMarketData(
        symbol=symbol,
        klines=df_k,
        funding_series=aligned_funding,
    )


def load_universe(symbols: list[str] = UNIVERSE) -> Dict[str, AssetMarketData]:
    data = {}
    for sym in symbols:
        data[sym] = load_single_asset(sym)
    return data


def slice_asset_data(
    asset_data: AssetMarketData, start: pd.Timestamp, end: pd.Timestamp
) -> AssetMarketData:
    mask = (asset_data.klines.index >= start) & (asset_data.klines.index <= end)
    return AssetMarketData(
        symbol=asset_data.symbol,
        klines=asset_data.klines.loc[mask].copy(),
        funding_series=asset_data.funding_series.loc[mask].copy(),
    )


def slice_universe(
    universe_data: Dict[str, AssetMarketData], start: pd.Timestamp, end: pd.Timestamp
) -> Dict[str, AssetMarketData]:
    return {
        sym: slice_asset_data(adata, start, end)
        for sym, adata in universe_data.items()
    }
