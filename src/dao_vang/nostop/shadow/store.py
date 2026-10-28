"""Registry + state files for the shadows (plain JSON, atomic writes, no database)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from ..data import ROOT
from .feed import _atomic_write

DATA_DIR = ROOT / "data" / "nostop_shadow"
STATUSES = ("running", "paused", "stopped")


def describe_spec(spec: dict) -> str:
    p = spec["params"]
    if spec["family"] == "mkt_flow":
        return f"mkt_flow L{p['L']} z{p['zwin']} thr{p['thr']} {p['asset']} {p['mode']}"
    tier = " tier-neutral" if p.get("tier_neutral") else ""
    sm = f" smooth{p['smooth_days']}d" if p.get("smooth_days") else ""
    return (
        f"{p.get('factors', spec['family'])} · q{p.get('q')} K{p.get('K')} "
        f"rebal{p.get('rebal')}d buf{p.get('buffer', 0)}{sm}{tier}{' ivol' if p.get('wt') == 'ivol' else ''}"
    )


class Store:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.dir = data_dir
        (self.dir / "state").mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ---- registry --------------------------------------------------------------
    @property
    def reg_path(self) -> Path:
        return self.dir / "shadows.json"

    def shadows(self) -> list[dict]:
        if not self.reg_path.exists():
            return []
        return json.loads(self.reg_path.read_text(encoding="utf-8"))["shadows"]

    def _save(self, shadows: list[dict]) -> None:
        _atomic_write(self.reg_path, json.dumps({"version": 1, "shadows": shadows}, indent=1).encode())

    def add(self, sid: str, spec: dict, start_ms: int, capital: float, research: dict) -> bool:
        with self._lock:
            sh = self.shadows()
            if any(s["id"] == sid for s in sh):
                return False
            sh.append(
                {
                    "id": sid,
                    "spec": spec,
                    "desc": describe_spec(spec),
                    "status": "running",
                    "capital": capital,
                    "start_ms": int(start_ms),
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "research": research,
                }
            )
            self._save(sh)
            return True

    def set_status(self, sid: str, status: str) -> bool:
        if status not in STATUSES:
            raise ValueError(status)
        with self._lock:
            sh = self.shadows()
            hit = False
            for s in sh:
                if s["id"] == sid or sid == "*":
                    s["status"] = status
                    hit = True
            if hit:
                self._save(sh)
            return hit

    def running(self) -> list[dict]:
        return [s for s in self.shadows() if s["status"] == "running"]

    # ---- state files ---------------------------------------------------------------
    def write_state(self, sid: str, state: dict) -> None:
        _atomic_write(self.dir / "state" / f"{sid}.json", json.dumps(state).encode())

    def read_state(self, sid: str) -> dict | None:
        p = self.dir / "state" / f"{sid}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def write_json(self, name: str, obj: dict) -> None:
        _atomic_write(self.dir / name, json.dumps(obj).encode())

    def read_json(self, name: str) -> dict:
        p = self.dir / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    # ---- profiles (mechanism / parameters / backtest evidence) ---------------------
    def write_profiles(self, profiles: dict) -> None:
        _atomic_write(self.dir / "profiles.json", json.dumps(profiles).encode())

    def read_profile(self, sid: str) -> dict | None:
        p = self.dir / "profiles.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8")).get(sid)
