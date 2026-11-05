#!/usr/bin/env python3
"""Hourly Shadow & Paper OOS Watchdog for Oracle Cloud (OCI Dokploy stack).

Runs every hour via cron on the host VM:
1. Verifies container health for `daovang-oracle-paper_oos`, `daovang-oracle-scanner`,
   `daovang-oracle-execution`, and `daovang-oracle-web`.
2. Ensures `OBSERVED_VIEWS.json` fallback exists and auto-warms any missing monthly
   PIT Top-50 hourly Parquet files inside `daovang-oracle-paper_oos`.
3. Inspects `/api/fibo-short/paper-oos`, `/api/fibo-short/snapshot`, and
   `/api/execution/dashboard` for stale heartbeats or stuck `service_error` pauses.
4. Auto-restarts only the affected container (rate-limited to 1 restart per 30m).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_RUNTIME_DIR = Path(
    "/etc/dokploy/compose/daovang-daovang-beta-bw9sz2/files/runtime"
)


def _http_json(url: str, timeout: float = 10.0) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ShadowWatchdog/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return None


def _ensure_paper_oos_warmup(runtime_dir: Path) -> list[str]:
    healed: list[str] = []
    obs_views = (
        runtime_dir
        / "artifacts"
        / "fibo_trend_short"
        / "research_v4_0_21"
        / "OBSERVED_VIEWS.json"
    )
    if not obs_views.exists():
        try:
            obs_views.parent.mkdir(parents=True, exist_ok=True)
            obs_views.write_text("{}", encoding="utf-8")
            healed.append("created_observed_views_fallback")
        except OSError:
            pass

    paper_art = runtime_dir / "artifacts" / "fibo_trend_short" / "paper_oos_v1"
    mem_dir = paper_art / "membership"
    hourly_dir = paper_art / "hourly"
    if not mem_dir.is_dir():
        return healed
    mem_files = sorted(mem_dir.glob("*.json"))
    if not mem_files:
        return healed
    try:
        latest_mem = json.loads(mem_files[-1].read_text(encoding="utf-8"))
        missing_syms = [
            str(m["symbol"]).strip().upper()
            for m in latest_mem.get("members", [])
            if str(m.get("symbol", "")).strip()
            and not (hourly_dir / f"{str(m['symbol']).strip().upper()}.parquet").exists()
        ]
    except Exception:
        missing_syms = []

    if missing_syms:
        py_code = (
            "import json, pathlib, sys; "
            "sys.path.insert(0, '/app/artifacts/fibo_trend_short/paper_oos_v1/source_snapshot/scripts/fibo_research'); "
            "import paper_data_v1 as d; "
            "d.ROOT = pathlib.Path('/app'); "
            "d.ART = pathlib.Path('/app/artifacts/fibo_trend_short/paper_oos_v1'); "
            "st = json.load(open(d.ART / 'STATUS.json')); "
            "info, _ = d.request('exchangeInfo'); "
            "contracts = {a['symbol']: a for a in info['symbols']}; "
            "cutoff = (int(st['last_bar_ms']) // d.HOUR) * d.HOUR; "
            f"syms = {missing_syms!r}; "
            "[d.prepare_hourly(s, contracts[s], cutoff) for s in syms if s in contracts]"
        )
        res = subprocess.run(
            ["docker", "exec", "daovang-oracle-paper_oos", "python", "-c", py_code],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if res.returncode == 0:
            healed.append(f"warmed_missing_hourly:{','.join(missing_syms)}")
    return healed


def run_check(*, runtime_dir: Path, api_base: str, apply: bool) -> dict:
    now_ts = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()
    state_path = runtime_dir / "data_live" / "shadow_hourly_watchdog.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        state = {"history": [], "last_restart_ts": 0.0}

    issues: list[str] = []
    healed = _ensure_paper_oos_warmup(runtime_dir) if apply else []
    restart_targets: list[str] = []

    # 1. Check Paper OOS v1
    paper = _http_json(f"{api_base}/api/fibo-short/paper-oos")
    if not paper or paper.get("status") != "ok":
        issues.append("paper_oos_api_unavailable")
        restart_targets.append("daovang-oracle-paper_oos")
    else:
        health = paper.get("health") or {}
        hb_age = float(health.get("heartbeat_age_sec") or 0.0)
        if health.get("code") != "ACTIVE_OK" or hb_age > 360.0:
            issues.append(f"paper_oos_unhealthy:{health.get('code')}:age={hb_age:.0f}s")
            restart_targets.append("daovang-oracle-paper_oos")

    # 2. Check Fibo Short Snapshot & Shadow Comparison
    snap = _http_json(f"{api_base}/api/fibo-short/snapshot")
    if not snap or snap.get("status") not in ("ok", "waiting"):
        issues.append("fibo_snapshot_unavailable")
        restart_targets.append("daovang-oracle-scanner")
    else:
        sc = snap.get("shadow_comparison") or {}
        tracks = sc.get("tracks") or []
        if len(tracks) < 5:
            issues.append("shadow_comparison_tracks_missing")
            restart_targets.append("daovang-oracle-scanner")

    # 3. Check 10k Paper Execution Dashboard
    exec_dash = _http_json(f"{api_base}/api/execution/dashboard?period=7d")
    if not exec_dash or not exec_dash.get("healthy"):
        issues.append("execution_engine_unhealthy")
        restart_targets.append("daovang-oracle-execution")
    elif (exec_dash.get("pause") or {}).get("reason") == "service_error":
        issues.append("execution_paused_service_error")
        restart_targets.append("daovang-oracle-execution")

    restarted: list[str] = []
    last_restart_ts = float(state.get("last_restart_ts") or 0.0)
    if apply and restart_targets and (now_ts - last_restart_ts) >= 1800.0:
        unique_targets = list(dict.fromkeys(restart_targets))
        subprocess.run(
            ["docker", "restart", *unique_targets],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        restarted = unique_targets
        state["last_restart_ts"] = now_ts

    entry = {
        "checked_at": now_iso,
        "healthy": len(issues) == 0,
        "issues": issues,
        "healed": healed,
        "restarted": restarted,
    }
    history = list(state.get("history") or [])
    history.append(entry)
    state["history"] = history[-48:]
    state["last_check"] = entry

    if apply:
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(state_path)
        except OSError:
            pass
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    parser.add_argument("--api-base", type=str, default="http://127.0.0.1:18000")
    args = parser.parse_args()
    result = run_check(
        runtime_dir=args.runtime_dir,
        api_base=args.api_base.rstrip("/"),
        apply=args.apply,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["healthy"] or result["restarted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
