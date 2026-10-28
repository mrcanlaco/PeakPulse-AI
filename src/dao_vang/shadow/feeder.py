"""Shared Market Feeder for Shadow Trading.
A single shared poller that serves all shadow bots simultaneously with ultra-low API overhead.
"""

from __future__ import annotations
import json
import logging
import time
import urllib.request
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from .models import update_market_quote

logger = logging.getLogger("shadow.feeder")

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "AVAXUSDT", "NEARUSDT", "DOGEUSDT"]


class SharedMarketFeeder:
    """Centralized market data feeder shared across all local shadow instances."""

    def __init__(self, symbols: List[str] = DEFAULT_SYMBOLS):
        self.symbols = symbols
        self.prices: Dict[str, float] = {}
        self.funding_rates: Dict[str, float] = {}
        self.candle_buffers_4h: Dict[str, pd.DataFrame] = {}
        self.last_candle_fetch = 0.0
        self.last_ticker_fetch = 0.0
        self.last_funding_fetch = 0.0
        self.api_call_count = 0
        self.is_healthy = True
        self.error_count = 0

    def fetch_live_tickers(self) -> Dict[str, float]:
        """Fetch all prices in a single API call to Binance Futures."""
        url = "https://fapi.binance.com/fapi/v1/ticker/price"
        req = urllib.request.Request(url, headers={"User-Agent": "PeakPulseShadow/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self.api_call_count += 1
            prices = {}
            for item in data:
                sym = item.get("symbol")
                if sym in self.symbols:
                    prices[sym] = float(item["price"])
                    self.prices[sym] = prices[sym]
                    update_market_quote(sym, prices[sym], self.funding_rates.get(sym, 0.0))
            self.last_ticker_fetch = time.time()
            self.is_healthy = True
            return prices
        except Exception as exc:
            self.error_count += 1
            logger.warning(f"Error fetching ticker prices: {exc}")
            return self.prices

    def fetch_live_funding_rates(self) -> Dict[str, float]:
        """Fetch funding rates in a single API call."""
        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        req = urllib.request.Request(url, headers={"User-Agent": "PeakPulseShadow/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self.api_call_count += 1
            rates = {}
            for item in data:
                sym = item.get("symbol")
                if sym in self.symbols:
                    rate = float(item.get("lastFundingRate", 0.0))
                    rates[sym] = rate
                    self.funding_rates[sym] = rate
                    if sym in self.prices:
                        update_market_quote(sym, self.prices[sym], rate)
            self.last_funding_fetch = time.time()
            return rates
        except Exception as exc:
            self.error_count += 1
            logger.warning(f"Error fetching premium index: {exc}")
            return self.funding_rates

    def warm_up_from_local_storage(self, klines_dir: str = "D:/SharedMarketData/multiyear_2020_2026/klines_1h"):
        """Warm up 4H candle buffers from high-speed local disk to avoid hundreds of REST calls."""
        from pathlib import Path
        p_dir = Path(klines_dir)
        if not p_dir.is_dir():
            return

        for sym in self.symbols:
            f_path = p_dir / f"{sym}_1h.parquet"
            if f_path.is_file():
                try:
                    df_1h = pd.read_parquet(f_path)
                    if not isinstance(df_1h.index, pd.DatetimeIndex):
                        if "open_time" in df_1h.columns:
                            df_1h.index = pd.to_datetime(df_1h["open_time"], unit="ms", utc=True)
                        else:
                            df_1h.index = pd.to_datetime(df_1h.index, utc=True)
                    df_1h = df_1h[["open", "high", "low", "close", "volume"]].astype(float)
                    # Resample to 4H
                    df_4h = df_1h.resample("4h").agg({
                        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
                    }).dropna()
                    # Keep latest 600 candles for warm indicators
                    self.candle_buffers_4h[sym] = df_4h.iloc[-600:].copy()
                    if len(df_4h) > 0 and sym not in self.prices:
                        self.prices[sym] = float(df_4h["close"].iloc[-1])
                        update_market_quote(sym, self.prices[sym], 0.0)
                except Exception as exc:
                    logger.warning(f"Local warm up failed for {sym}: {exc}")

    def fetch_latest_4h_candles(self, limit: int = 5) -> Dict[str, pd.DataFrame]:
        """Fetch only the latest few 4H candles per symbol to update in-memory buffer."""
        now = time.time()
        # Rate limit candle fetch to at most once per 60 seconds
        if now - self.last_candle_fetch < 60.0 and self.candle_buffers_4h:
            return self.candle_buffers_4h

        for sym in self.symbols:
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=4h&limit={limit}"
            req = urllib.request.Request(url, headers={"User-Agent": "PeakPulseShadow/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    bars = json.loads(resp.read().decode("utf-8"))
                self.api_call_count += 1
                if bars:
                    df = pd.DataFrame(bars, columns=[
                        "open_time", "open", "high", "low", "close", "volume",
                        "close_time", "quote_volume", "count", "taker_buy_vol", "taker_buy_quote", "ignore"
                    ])
                    for col in ["open", "high", "low", "close", "volume"]:
                        df[col] = df[col].astype(float)
                    df.index = pd.to_datetime(df["open_time"], unit="ms", utc=True)
                    df = df[["open", "high", "low", "close", "volume"]]

                    if sym in self.candle_buffers_4h:
                        combined = pd.concat([self.candle_buffers_4h[sym], df])
                        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
                        self.candle_buffers_4h[sym] = combined.iloc[-600:].copy()
                    else:
                        self.candle_buffers_4h[sym] = df

                    self.prices[sym] = float(df["close"].iloc[-1])
            except Exception as exc:
                self.error_count += 1
                logger.warning(f"Failed to fetch 4H klines for {sym}: {exc}")
            time.sleep(0.05)  # respectful tiny sleep

        self.last_candle_fetch = now
        return self.candle_buffers_4h

    def get_all_quotes(self) -> Dict[str, dict]:
        res = {}
        for sym in self.symbols:
            price = self.prices.get(sym, 0.0)
            fr = self.funding_rates.get(sym, 0.0)
            res[sym] = {"price": price, "funding_rate": fr}
        return res

    def get_stats(self) -> dict:
        return {
            "api_call_count": self.api_call_count,
            "error_count": self.error_count,
            "is_healthy": self.is_healthy,
            "symbols_tracked": len(self.symbols),
            "prices": self.prices,
            "funding_rates": self.funding_rates,
            "last_ticker_time": self.last_ticker_fetch,
            "last_candle_time": self.last_candle_fetch,
        }
