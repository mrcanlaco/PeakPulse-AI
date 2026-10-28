"""Scheduler: one sync + one shared feature pass per 4h bar, a 60s mark-price poll between."""

from __future__ import annotations

import logging
import sys
import threading
import time
import traceback
from pathlib import Path

import numpy as np

from .binance import ApiError, PublicClient
from .book import shadow_state, shared_context
from .feed import BAR_MS, SharedFeed
from .store import DATA_DIR, Store

log = logging.getLogger("nostop.shadow")
BAR_DELAY_S = 20  # wait after the bar boundary so the exchange has finalised the candle


def rss_mb() -> float:
    """Resident memory of this process in MB (stdlib only)."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            k32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
            k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
            return pmc.WorkingSetSize / 1048576.0
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:  # noqa: BLE001 - diagnostics only
        return -1.0


class ShadowRunner:
    def __init__(self, data_dir: Path = DATA_DIR, client: PublicClient | None = None,
                 feed: SharedFeed | None = None):
        self.store = Store(data_dir)
        self.client = client or PublicClient()
        self.feed = feed or SharedFeed(data_dir, self.client)
        self.stop = threading.Event()
        self.cycle_s = 0.0
        self.cycles = 0
        self.last_error = ""
        self.started = time.time()
        self.last_step_bar = 0
        self._loaded = False
        self.fails = 0
        self.retry_at = 0.0

    # ---- helpers ------------------------------------------------------------------
    def now_ms(self) -> int:
        return self.client.now_ms()

    def current_bar_ms(self) -> int:
        return self.now_ms() // BAR_MS * BAR_MS

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.feed.load()
            self._loaded = True

    # ---- one full cycle -------------------------------------------------------------
    def step(self, now_ms: int | None = None) -> dict:
        t0 = time.time()
        self._ensure_loaded()
        now_ms = int(now_ms if now_ms is not None else self.now_ms())
        running = self.store.running()
        keep = min((s["start_ms"] for s in running), default=None)
        info = self.feed.sync(now_ms, keep_from_ms=keep)
        panel, _closed = self.feed.panel()
        ctx, cost = shared_context(panel)
        ok = 0
        for sh in running:
            try:
                start_idx = int(np.searchsorted(self.feed.index, sh["start_ms"], side="left"))
                state = shadow_state(panel, ctx, cost, sh["spec"], start_idx, float(sh["capital"]))
                state["error"] = ""
                self.store.write_state(sh["id"], state)
                ok += 1
            except Exception as exc:  # noqa: BLE001 - one bad shadow must not stop the others
                log.error("shadow %s failed: %s", sh["id"], exc)
                prev = self.store.read_state(sh["id"]) or {}
                prev["error"] = repr(exc)[:200]
                self.store.write_state(sh["id"], prev)
        self.cycle_s = time.time() - t0
        self.cycles += 1
        self.last_step_bar = int(self.feed.index[-1])
        self.write_system(extra={"last_sync_info": info, "shadows_ok": ok})
        # panel arrays are rebuilt every cycle; drop the feature cache reference
        del ctx, panel
        return info

    def tick_prices(self) -> None:
        rows = self.client.prices_all()
        prices = {r["symbol"]: float(r["price"]) for r in rows}
        self.store.write_json("prices.json", {"ts": self.now_ms(), "prices": prices})

    def write_system(self, extra: dict | None = None) -> None:
        sysinfo = {
            "ts": self.now_ms(),
            "started": self.started,
            "cycles": self.cycles,
            "cycle_seconds": round(self.cycle_s, 2),
            "rss_mb": round(rss_mb(), 1),
            "api_calls": dict(self.client.calls),
            "api_errors": self.client.errors,
            "api_used_weight_1m": self.client.used_weight_1m,
            "clock_offset_ms": round(self.client.time_offset_ms, 1),
            "feed_last_bar_ms": int(self.feed.index[-1]) if len(self.feed.index) else 0,
            "feed_bars": int(len(self.feed.index)),
            "feed_symbols": len(self.feed.symbols),
            "feed_last_sync": self.feed.last_sync,
            "feed_skipped": self.feed.skipped_symbols,
            "last_error": self.last_error,
        }
        if extra:
            sysinfo.update(extra)
        self.store.write_json("system.json", sysinfo)

    # ---- main loop --------------------------------------------------------------------
    def run_forever(self, price_every_s: float = 60.0) -> None:
        try:
            self.client.sync_time()
        except ApiError as exc:
            self.last_error = f"time sync: {exc}"
        self._safe_step()
        last_price = 0.0
        last_time_sync = time.time()
        while not self.stop.is_set():
            now = self.now_ms()
            due_bar = now // BAR_MS * BAR_MS
            if (now - due_bar >= BAR_DELAY_S * 1000 and due_bar > self.last_step_bar
                    and time.time() >= self.retry_at):
                self._safe_step()
            if time.time() - last_price >= price_every_s:
                last_price = time.time()
                try:
                    self.tick_prices()
                except ApiError as exc:
                    self.last_error = f"prices: {exc}"
            if time.time() - last_time_sync > 3600:
                last_time_sync = time.time()
                try:
                    self.client.sync_time()
                except ApiError as exc:
                    self.last_error = f"time sync: {exc}"
            self.stop.wait(1.0)

    def _safe_step(self) -> None:
        try:
            self.step()
            self.last_error = ""
            self.fails = 0
        except Exception as exc:  # noqa: BLE001 - keep the scheduler alive, surface in UI
            self.fails += 1
            self.last_error = f"step: {exc!r}"
            log.error("step failed: %s", traceback.format_exc())
            self.retry_at = time.time() + min(900.0, 30.0 * 2 ** (self.fails - 1))


def main_loop(data_dir: Path = DATA_DIR) -> ShadowRunner:  # pragma: no cover - thin wrapper
    r = ShadowRunner(data_dir)
    threading.Thread(target=r.run_forever, daemon=True, name="shadow-runner").start()
    return r

