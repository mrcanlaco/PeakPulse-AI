"""Cross-platform 24/7 daemon wrapper for Prospective Paper OOS v1 (Windows & Linux/WSL).

Preserves PROTOCOL.json and paper_runner_v1.py byte-for-byte while:
1. Executing with frozen source_snapshot modules first on sys.path.
2. Resolving cross-platform artifact/source_snapshot paths (Windows <-> Linux).
3. Enforcing single-instance file lock via fcntl (POSIX) or msvcrt (Windows).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
ART = ROOT / "artifacts" / "fibo_trend_short" / "paper_oos_v1"
SNAP_ROOT = ART / "source_snapshot"

# Put frozen source_snapshot first on sys.path so Paper OOS always runs the locked equations
for p in (
    SNAP_ROOT / "scripts" / "fibo_research",
    SNAP_ROOT / "src",
    SCRIPT_DIR,
    ROOT / "src",
):
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

import paper_data_v1 as d  # noqa: E402
import paper_runner_v1 as runner  # noqa: E402


def _resolve_cross_platform_path(raw_path: str | Path, prefer_snapshot: bool = False) -> Path:
    p = Path(raw_path)
    if not prefer_snapshot and p.exists():
        return p
    norm = str(raw_path).replace("\\", "/")
    marker = "dao_vang/"
    idx = norm.find(marker)
    rel = norm[idx + len(marker) :] if idx >= 0 else norm.lstrip("/")
    if prefer_snapshot:
        snap_candidate = SNAP_ROOT / rel
        if snap_candidate.exists():
            return snap_candidate
    root_candidate = ROOT / rel
    if root_candidate.exists():
        return root_candidate
    snap_fallback = SNAP_ROOT / rel
    if snap_fallback.exists():
        return snap_fallback
    return p


def _patched_read(path: str | Path):
    resolved = _resolve_cross_platform_path(path, prefer_snapshot=False)
    return json.loads(resolved.read_text(encoding="utf8"))


def _patched_sha(path: str | Path) -> str:
    resolved = _resolve_cross_platform_path(path, prefer_snapshot=False)
    return hashlib.sha256(resolved.read_bytes()).hexdigest()


def _patched_protocol():
    path = ART / "PROTOCOL.json"
    p = _patched_read(path)
    for file_key, digest in p["sources"].items():
        snap_file = _resolve_cross_platform_path(file_key, prefer_snapshot=True)
        if hashlib.sha256(snap_file.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Frozen paper source_snapshot changed: {file_key}")
    p["protocol_sha256"] = _patched_sha(path)
    return p


d.ROOT = ROOT
d.ART = ART
d.read = _patched_read
d.sha = _patched_sha
runner.protocol = _patched_protocol


class CrossPlatformLock:
    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self.fh = None

    def __enter__(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.lock_path, "a+b")
        if self.fh.tell() == 0:
            self.fh.write(b"1")
            self.fh.flush()
        self.fh.seek(0)
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("Another paper observer already holds the lock") from exc
        else:
            import fcntl

            try:
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError("Another paper observer already holds the lock") from exc
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fh is not None:
            try:
                self.fh.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
            finally:
                self.fh.close()
                self.fh = None


def _run_live_fibo_telegram_scan() -> None:
    """Run live Fibo Trend Short scanner lane in an isolated subprocess to update snapshot & dispatch qualified Short Telegram alerts."""
    import subprocess

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        subprocess.run(
            [sys.executable, "-m", "dao_vang.cli.main", "fibo-scan"],
            cwd=str(ROOT),
            env=env,
            timeout=180,
            check=False,
        )
    except Exception as exc:
        print(f"FiboTelegramScanWarning: {type(exc).__name__}: {exc}", flush=True)


def run_daemon(once: bool = False) -> None:
    with CrossPlatformLock(ART / "RUNNER.lock"):
        observer = runner.Observer()
        st0 = observer.status()
        last_seen_signal_ms = int(st0.get("last_signal_ms") or 0)
        last_fibo_scan_mono = 0.0
        if once:
            observer.tick()
            observer.status()
            _run_live_fibo_telegram_scan()
            return
        while True:
            try:
                if not observer.tick():
                    status = observer.status()
                    status["status"] = "HORIZON_COMPLETE_AWAITING_REVIEW"
                    d.save(ART / "STATUS.json", status)
                    break
                cur_status = d.read(ART / "STATUS.json")
                cur_sig_ms = int(cur_status.get("last_signal_ms") or 0)
                now_mono = time.monotonic()
                if cur_sig_ms > last_seen_signal_ms or (now_mono - last_fibo_scan_mono) >= 300.0:
                    last_seen_signal_ms = max(last_seen_signal_ms, cur_sig_ms)
                    last_fibo_scan_mono = now_mono
                    _run_live_fibo_telegram_scan()
            except Exception as exc:
                err_msg = f"{type(exc).__name__}: {exc}"
                observer.status(err_msg)
                print(err_msg, flush=True)
            time.sleep(5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["run", "tick", "status"], default="run", nargs="?")
    args = parser.parse_args()
    if args.action == "status":
        print(json.dumps(d.read(ART / "STATUS.json"), indent=2), flush=True)
    elif args.action == "tick":
        run_daemon(once=True)
    else:
        run_daemon(once=False)
