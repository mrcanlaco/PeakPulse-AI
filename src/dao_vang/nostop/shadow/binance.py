"""Minimal public Binance USD-M client: no keys, throttled, request accounting."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from collections.abc import Callable

BASE = "https://fapi.binance.com"

Fetch = Callable[[str], tuple[int, dict, bytes]]


def _urllib_fetch(url: str) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "dao-vang-nostop-shadow/1"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 - fixed https host
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()


class ApiError(RuntimeError):
    pass


class PublicClient:
    """GET-only client for public market data.  Counts calls per endpoint and keeps the
    last reported used weight so the dashboard can show the API footprint."""

    def __init__(self, fetch: Fetch | None = None, min_interval: float = 0.15, retries: int = 3):
        self._fetch = fetch or _urllib_fetch
        self._min_interval = min_interval
        self._retries = retries
        self._lock = threading.Lock()
        self._last = 0.0
        self.calls: dict[str, int] = defaultdict(int)
        self.errors = 0
        self.used_weight_1m = 0
        self.banned_until = 0.0
        self.time_offset_ms = 0.0

    def sync_time(self) -> float:
        """Measure server-minus-local clock offset (bar closes must follow exchange time)."""
        t0 = time.time()
        st = self.get("/fapi/v1/time")["serverTime"]
        t1 = time.time()
        self.time_offset_ms = float(st) - (t0 + t1) / 2 * 1000.0
        return self.time_offset_ms

    def now_ms(self) -> int:
        return int(time.time() * 1000 + self.time_offset_ms)

    def get(self, path: str, params: dict | None = None):
        url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
        last_err = ""
        for attempt in range(self._retries):
            if time.time() < self.banned_until:
                raise ApiError(f"rate-limit ban active for {self.banned_until - time.time():.0f}s")
            with self._lock:
                wait = self._min_interval - (time.time() - self._last)
                if wait > 0:
                    time.sleep(wait)
                self._last = time.time()
            try:
                status, headers, body = self._fetch(url)
            except Exception as exc:  # noqa: BLE001 - network error, retry
                last_err = repr(exc)
                self.errors += 1
                time.sleep(1.0 + attempt)
                continue
            self.calls[path] += 1
            w = {k.lower(): v for k, v in headers.items()}.get("x-mbx-used-weight-1m")
            if w is not None:
                self.used_weight_1m = int(w)
            if status == 200:
                return json.loads(body)
            self.errors += 1
            last_err = f"HTTP {status}: {body[:120]!r}"
            if status in (418, 429):
                retry = int({k.lower(): v for k, v in headers.items()}.get("retry-after", "30"))
                self.banned_until = time.time() + retry
                raise ApiError(last_err)
            if status in (400, 404):  # bad/unknown symbol: not retryable
                raise ApiError(last_err)
            time.sleep(1.0 + attempt)
        raise ApiError(last_err or "request failed")

    # ---- endpoints used by the shadows --------------------------------
    def klines(self, symbol: str, start_ms: int, limit: int) -> list:
        return self.get(
            "/fapi/v1/klines",
            {"symbol": symbol, "interval": "4h", "startTime": int(start_ms), "limit": int(limit)},
        )

    def funding_history(self, symbol: str, start_ms: int, limit: int = 1000) -> list:
        return self.get(
            "/fapi/v1/fundingRate",
            {"symbol": symbol, "startTime": int(start_ms), "limit": int(limit)},
        )

    def premium_all(self) -> list:
        return self.get("/fapi/v1/premiumIndex")

    def prices_all(self) -> list:
        return self.get("/fapi/v1/ticker/price")
