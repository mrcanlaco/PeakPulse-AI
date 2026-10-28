"""Shared market feed: ONE rolling 4h panel serves every shadow.

* seeded from the research panel (no API cost), then topped up with public klines;
* steady state per 4h bar: one kline call per symbol (limit ~3) + one premiumIndex call
  every 8h for funding, plus an optional all-symbol ticker call per minute for marks;
* persisted to ``bars.npz`` so restarts only fetch the missing bars.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ..data import PANEL_PATH, Panel
from .binance import ApiError, PublicClient

BAR_MS = 4 * 3600 * 1000
FUND_MS = 8 * 3600 * 1000
WINDOW = 1800  # bars kept (300 days): decisions need >= 720 bars of history
FIELDS = ("open", "high", "low", "close", "volume", "qvol", "taker")


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class SharedFeed:
    def __init__(self, data_dir: Path, client: PublicClient, window: int = WINDOW,
                 seed_path: Path = PANEL_PATH):
        self.dir = data_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.client = client
        self.window = window
        self.seed_path = seed_path
        self.index = np.zeros(0, dtype=np.int64)  # bar open time, ms
        self.symbols: list[str] = []
        self.a: dict[str, np.ndarray] = {}
        self.funding = np.zeros((0, 0))
        self.funding_through = 0
        self.last_sync = 0.0
        self.last_error = ""
        self.skipped_symbols: dict[str, str] = {}

    # ---- persistence -------------------------------------------------------
    @property
    def path(self) -> Path:
        return self.dir / "bars.npz"

    def load(self) -> None:
        if self.path.exists():
            z = np.load(self.path, allow_pickle=False)
            self.index = z["index"].astype(np.int64)
            self.symbols = [str(s) for s in z["symbols"]]
            self.a = {k: z[k] for k in FIELDS}
            self.funding = z["funding"]
            self.funding_through = int(z["funding_through"])
            return
        z = np.load(self.seed_path, allow_pickle=False)
        idx = pd.DatetimeIndex(pd.to_datetime(z["index"], unit="ns", utc=True))
        sl = slice(max(len(idx) - self.window, 0), len(idx))
        self.index = (idx[sl].as_unit("ms").asi8).astype(np.int64)
        self.symbols = [str(s) for s in z["symbols"]]
        self.a = {k: z[k][sl].copy() for k in FIELDS}
        self.funding = z["funding"][sl].copy()
        settle = self.index[(self.index % FUND_MS) == 0]
        self.funding_through = int(settle[-1])

    def save(self) -> None:
        import io

        buf = io.BytesIO()
        np.savez_compressed(
            buf,
            index=self.index,
            symbols=np.array(self.symbols),
            funding=self.funding,
            funding_through=np.int64(self.funding_through),
            **self.a,
        )
        _atomic_write(self.path, buf.getvalue())
        _atomic_write(
            self.dir / "feed_meta.json",
            json.dumps(
                {
                    "last_bar_open_ms": int(self.index[-1]),
                    "bars": int(len(self.index)),
                    "symbols": len(self.symbols),
                    "funding_through_ms": self.funding_through,
                    "last_sync": self.last_sync,
                    "skipped_symbols": self.skipped_symbols,
                }
            ).encode(),
        )

    # ---- panel growth ------------------------------------------------------
    def _ensure_rows(self, upto_ms: int) -> None:
        if upto_ms <= self.index[-1]:
            return
        add = int((upto_ms - self.index[-1]) // BAR_MS)
        n = len(self.symbols)
        self.index = np.concatenate([self.index, self.index[-1] + BAR_MS * np.arange(1, add + 1)])
        for k in FIELDS:
            self.a[k] = np.vstack([self.a[k], np.full((add, n), np.nan)])
        self.funding = np.vstack([self.funding, np.zeros((add, n))])

    def _row(self, open_ms: int) -> int:
        return int((open_ms - self.index[0]) // BAR_MS)

    def _apply_klines(self, j: int, rows: list, now_ms: int) -> int:
        closed = 0
        for r in rows:
            open_ms, close_ms = int(r[0]), int(r[6])
            if open_ms < self.index[0]:
                continue
            self._ensure_rows(open_ms)
            i = self._row(open_ms)
            self.a["open"][i, j] = float(r[1])
            if close_ms < now_ms:  # complete bar
                self.a["high"][i, j] = float(r[2])
                self.a["low"][i, j] = float(r[3])
                self.a["close"][i, j] = float(r[4])
                self.a["volume"][i, j] = float(r[5])
                self.a["qvol"][i, j] = float(r[7])
                self.a["taker"][i, j] = float(r[9])
                closed += 1
        return closed

    # ---- sync ----------------------------------------------------------------
    def sync(self, now_ms: int | None = None, keep_from_ms: int | None = None) -> dict:
        now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        cur_bar = now_ms // BAR_MS * BAR_MS
        before = int(self.index[-1])
        start = int(self.index[max(len(self.index) - 3, 0)])
        errors: dict[str, str] = {}
        new_closed = 0
        for j, sym in enumerate(self.symbols):
            s = start
            try:
                while True:
                    limit = int(min(1000, max((now_ms - s) // BAR_MS + 2, 2)))
                    rows = self.client.klines(sym, s, limit)
                    new_closed += self._apply_klines(j, rows, now_ms)
                    if len(rows) < 1000:
                        break
                    s = int(rows[-1][0]) + BAR_MS
            except ApiError as exc:
                errors[sym] = str(exc)[:100]
        self._ensure_rows(cur_bar)
        self._sync_funding(now_ms)
        self.skipped_symbols = errors
        self._trim(keep_from_ms)
        self.last_sync = time.time()
        self.save()
        return {"new_rows": int((self.index[-1] - before) // BAR_MS), "errors": len(errors),
                "bar": int(self.index[-1])}

    def _sync_funding(self, now_ms: int) -> None:
        last_settle = (now_ms - 60_000) // FUND_MS * FUND_MS
        if last_settle <= self.funding_through:
            return
        missing = (last_settle - self.funding_through) // FUND_MS
        self._ensure_rows(last_settle)
        done = False
        if missing == 1:
            try:
                prem = {p["symbol"]: p for p in self.client.premium_all()}
                ok = sum(1 for p in prem.values() if int(p["nextFundingTime"]) - FUND_MS == last_settle)
                if ok >= 0.5 * len(prem):
                    i = self._row(last_settle)
                    for j, sym in enumerate(self.symbols):
                        p = prem.get(sym)
                        if p and int(p["nextFundingTime"]) - FUND_MS == last_settle and p["lastFundingRate"] != "":
                            self.funding[i, j] = float(p["lastFundingRate"])
                    done = True
            except ApiError as exc:
                self.last_error = f"premiumIndex: {exc}"
        if not done:
            for j, sym in enumerate(self.symbols):
                try:
                    for f in self.client.funding_history(sym, self.funding_through + 1, 1000):
                        t = int(f["fundingTime"]) // BAR_MS * BAR_MS
                        if t >= self.index[0] and t <= self.index[-1]:
                            self.funding[self._row(t), j] = float(f["fundingRate"])
                except ApiError as exc:
                    self.skipped_symbols[sym] = f"funding: {exc}"[:100]
        self.funding_through = int(last_settle)

    def _trim(self, keep_from_ms: int | None = None) -> None:
        """Drop old bars beyond the window, but never bars the oldest running shadow needs
        (its start bar minus ~1000 bars of feature warm-up)."""
        if len(self.index) <= self.window:
            return
        cut = len(self.index) - self.window
        if keep_from_ms is not None:
            need = int(np.searchsorted(self.index, keep_from_ms - 1000 * BAR_MS, side="left"))
            cut = min(cut, need)
        if cut <= 0:
            return
        self.index = self.index[cut:]
        for k in FIELDS:
            self.a[k] = self.a[k][cut:]
        self.funding = self.funding[cut:]

    # ---- snapshot for the engine ---------------------------------------------
    def panel(self) -> tuple[Panel, int]:
        """Panel whose last row is the forming bar (only its open is real; the rest is a
        flat placeholder so decisions made at the previous close execute at that open).
        Returns (panel, index_of_last_closed_bar)."""
        a = {k: v.copy() for k, v in self.a.items()}
        last = len(self.index) - 1
        forming = np.isnan(a["close"][last]) & np.isfinite(a["open"][last])
        closed_row = last - 1 if forming.any() else last
        for k in ("high", "low", "close"):
            a[k][last, forming] = a["open"][last, forming]
        idx = pd.DatetimeIndex(pd.to_datetime(self.index, unit="ms", utc=True)).as_unit("ns")
        p = Panel(idx, list(self.symbols), a["open"], a["high"], a["low"], a["close"], a["qvol"],
                  a["taker"], a["volume"], self.funding.copy())
        return p, closed_row
