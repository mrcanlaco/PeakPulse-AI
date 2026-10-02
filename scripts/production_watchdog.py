#!/usr/bin/env python3
"""Host watchdog: inspect real scanner outputs and recover boundedly.

Runs without app dependencies. Cron supplies flock to prevent overlap; a
maintenance marker disables recovery during planned deployment/backup work.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path


def recovery_allowed(state: dict, now: float) -> bool:
    return now - state.get("last_restart", 0) >= 1800 and len([
        t for t in state.get("restarts", []) if now - t < 21600
    ]) < 3


def startup_grace(data: Path, now: float) -> bool:
    """Give the first scan after a restart five minutes to replace old output."""
    try:
        heartbeat = json.loads((data / "scanner_heartbeat.json").read_text())
        started = datetime.fromisoformat(heartbeat["last_cycle_started_at"]).timestamp()
        return (heartbeat.get("cycle") == 1
                and heartbeat.get("last_cycle_status") == "running"
                and not heartbeat.get("last_cycle_completed_at")
                and 0 <= now - started < 300)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.project.resolve()
    data = root / "data"
    if (data / "maintenance.flag").exists():
        print("maintenance: recovery paused")
        return 0
    spec = importlib.util.spec_from_file_location("healthcheck", root / "src/dao_vang/scanner/healthcheck.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    health = module.inspect_heartbeat(data / "scanner_heartbeat.json", snapshot_path=data / "candidate_snapshot.json",
                                      stats_path=data / "system_data_stats.json")
    state_path = data / "watchdog_state.json"
    try:
        state = json.loads(state_path.read_text())
    except (OSError, ValueError):
        state = {}
    now = time.time()
    state["checked_at"] = now
    state["scanner"] = health
    service = None
    if not health["healthy"]:
        service = "scanner"
    else:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=10) as response:
                if response.status != 200:
                    service = "web"
        except Exception:
            service = "web"
    state["action"] = "healthy" if service is None else "recovery_required"
    if service == "scanner" and startup_grace(data, now):
        state["action"] = "startup_grace"
    elif service and args.apply and recovery_allowed(state, now):
        # Do not start an intentionally stopped service (e.g. backup). A dead
        # running container is recovered by Compose's restart policy.
        status = subprocess.run(["docker", "compose", "ps", "--status", "running", "--services"], cwd=root,
                                text=True, capture_output=True, timeout=30, check=True)
        if service in status.stdout.split():
            state["last_restart"] = now
            state["restarts"] = [t for t in state.get("restarts", []) if now - t < 21600] + [now]
            state["action"] = f"restart_{service}"
            # Persist the attempt before restart to bound retries even if it fails.
            temporary = state_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(state, indent=2))
            temporary.replace(state_path)
            subprocess.run(["docker", "compose", "restart", "--timeout", "20", service], cwd=root, timeout=90, check=True)
        else:
            state["action"] = "service_stopped"
    elif service and args.apply:
        state["action"] = "recovery_rate_limited"
    if args.apply:
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2))
        temporary.replace(state_path)
    print(json.dumps(state))
    return 0 if service is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
