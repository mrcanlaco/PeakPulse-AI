"""Deploy committed code & built frontend to Oracle Cloud (OCI Dokploy stack) safely.

Preserves live runtime secrets, DuckDB/SQLite state, Cloudflare tunnel, and the
long-running `daovang-oracle-paper_oos` container without interruption.
"""

from __future__ import annotations

import argparse
import io
import os
import shlex
import subprocess
import tarfile
from pathlib import Path

DEFAULT_RUNTIME_DIR = "/etc/dokploy/compose/daovang-daovang-beta-bw9sz2/files/runtime"
SYNC_PATHS = (
    "CHANGELOG.md",
    "configs/live.yaml",
    "configs/dev.yaml",
    "configs/default.example.yaml",
    "docs/PRODUCTION_DEPLOYMENT_GUIDE.md",
    "docs/DEPLOYMENT_ENVIRONMENT.md",
    "docs/OPERATIONS_RUNBOOK.md",
    "docs/PRODUCTION_MODEL.md",
    "docs/ARCHITECTURE.md",
    "docs/DEV_LIVE_SETUP.md",
    "scripts/fibo_research/run_paper_oos_daemon.py",
    "scripts/shadow_hourly_watchdog.py",
    "src/dao_vang/config/settings.py",
    "src/dao_vang/execution/engine.py",
    "src/dao_vang/execution/paper.py",
    "src/dao_vang/execution/sources.py",
    "src/dao_vang/fibo_short/scanner_lane.py",
    "src/dao_vang/scanner/daemon.py",
    "src/dao_vang/scanner/healthcheck.py",
    "src/dao_vang/web/api_server.py",
    "src/dao_vang/web/execution_api.py",
    "frontend/dist",
)

REMOTE_DEPLOY_TEMPLATE = """
set -eu
RT=__RUNTIME_DIR__
REV=__REVISION__
TS="$(date -u +%Y%m%dT%H%M%SZ)"
BK="/var/backups/dao-vang/prod-2tier-$TS"
sudo mkdir -p "$BK"
sudo cp -a "$RT/configs/msi-production.yaml" "$RT/configs/live.yaml" "$RT/CHANGELOG.md" "$BK/" 2>/dev/null || true
sudo cp -a "$RT/frontend/dist" "$BK/frontend_dist" 2>/dev/null || true
for rel in src/dao_vang/config/settings.py src/dao_vang/execution/engine.py src/dao_vang/execution/paper.py src/dao_vang/execution/sources.py src/dao_vang/fibo_short/scanner_lane.py src/dao_vang/scanner/daemon.py src/dao_vang/scanner/healthcheck.py src/dao_vang/web/api_server.py src/dao_vang/web/execution_api.py; do
  if sudo test -f "$RT/$rel"; then
    sudo mkdir -p "$BK/$(dirname "$rel")"
    sudo cp -a "$RT/$rel" "$BK/$rel"
  fi
done
sudo rm -rf "$RT/frontend/dist"
sudo mkdir -p "$RT/frontend/dist"
sudo tar -xzf - -C "$RT"
sudo chown -R root:root "$RT/src" "$RT/scripts" "$RT/frontend/dist" "$RT/docs" "$RT/CHANGELOG.md" "$RT/configs/live.yaml" "$RT/configs/dev.yaml" "$RT/configs/default.example.yaml"
sudo python3 - "$RT/configs/msi-production.yaml" <<'PY'
import os
import pathlib
import sys
import yaml

p = pathlib.Path(sys.argv[1])
if p.exists():
    st = p.stat()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    web_cfg = data.setdefault("web", {})
    if isinstance(web_cfg, dict):
        web_cfg["public_url"] = "https://pulse.freqpilot.dev"
        web_cfg["allowed_origins"] = [
            "https://pulse.freqpilot.dev",
            "https://daovang.comaygiauco.com",
        ]
    if isinstance(data.get("scanner"), dict):
        data["scanner"]["shadow_telegram_enabled"] = False
    if isinstance(data.get("fibo_trend_short"), dict):
        data["fibo_trend_short"]["enabled"] = True
        data["fibo_trend_short"]["universe_mode"] = "rolling_pit_top50"
        data["fibo_trend_short"]["higher_timeframes"] = ["4h", "1d"]
        data["fibo_trend_short"]["confirm_timeframe"] = "1h"
        data["fibo_trend_short"]["max_candidates"] = 50
        data["fibo_trend_short"]["telegram_enabled"] = True
        data["fibo_trend_short"]["telegram_require_qualified_short"] = True
        data["fibo_trend_short"]["telegram_min_prior_pump_pct"] = 0.05
        data["fibo_trend_short"]["telegram_allowed_policies"] = [
            "elite_sniper_risk",
            "sniper_rr1_horizon24",
            "sniper_risk",
            "sniper_horizon24",
        ]
    acct_mon = data.setdefault("account_monitor", {})
    if isinstance(acct_mon, dict):
        acct_mon["enabled"] = False
    exec_cfg = data.setdefault("execution", {})
    if isinstance(exec_cfg, dict):
        exec_cfg["enabled"] = True
        exec_cfg["paper_trading"] = True
        exec_cfg["live_activated"] = False
        exec_cfg["environment"] = "simulation"
        exec_cfg["signal_source"] = "fibo_short"
        exec_cfg["manifest_path"] = None
        exec_cfg["initial_equity"] = 10000.0
        exec_cfg["margin_per_position"] = 200.0
        exec_cfg["leverage"] = 5
        exec_cfg["margin_type"] = "CROSSED"
        exec_cfg["max_position_usd"] = 1000.0
        exec_cfg["max_open_positions"] = 5
        exec_cfg["entry_pause_drawdown"] = 0.20
        exec_cfg["tp_min_usdt"] = 5.0
        exec_cfg["tp_max_usdt"] = 250.0
        exec_cfg["signal_ttl_seconds"] = 900
        exec_cfg["poll_seconds"] = 10
        exec_cfg["enable_stop_loss"] = True
        exec_cfg["sl_max_loss_usdt"] = 50.0
        exec_cfg["sl_atr_multiplier"] = 3.0
        exec_cfg["stop_loss_pct"] = 0.12
        exec_cfg["enable_trailing_tp"] = True
        exec_cfg["trailing_trigger_atr"] = 1.5
        exec_cfg["trailing_callback_atr"] = 1.0
        exec_cfg["max_hold_hours"] = 72
        exec_cfg["require_price_confirmation"] = True
    tmp = p.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    os.chown(tmp, st.st_uid, st.st_gid)
    os.chmod(tmp, st.st_mode & 0o777)
    os.replace(tmp, p)
PY
sudo python3 - "$(dirname "$(dirname "$RT")")/code/docker-compose.yml" <<'PY'
import json
import pathlib
import sys

cp = pathlib.Path(sys.argv[1])
if cp.is_file():
    doc = json.loads(cp.read_text(encoding="utf-8"))
    services = doc.setdefault("services", {})
    scanner_svc = services.get("scanner", {})
    if scanner_svc and "execution" not in services:
        services["execution"] = {
            "restart": "unless-stopped",
            "cpus": 1,
            "mem_limit": "536870912",
            "user": scanner_svc.get("user", "1001:1004"),
            "image": scanner_svc.get("image", "dao-vang-oracle:v4.0.21-20261026"),
            "pull_policy": "never",
            "container_name": "daovang-oracle-execution",
            "command": [
                "dao-vang",
                "execution",
                "start",
                "--config",
                "configs/msi-production.yaml",
            ],
            "env_file": scanner_svc.get("env_file", ["../files/runtime/.runtime-scanner.env"]),
            "logging": scanner_svc.get("logging", {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}}),
            "volumes": scanner_svc.get("volumes", []),
        }
        cp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
PY
sudo python3 - "$RT/cloudflared/config.yml" <<'PY'
import os
import pathlib
import sys
import yaml

cf = pathlib.Path(sys.argv[1])
if cf.is_file():
    st = cf.stat()
    doc = yaml.safe_load(cf.read_text(encoding="utf-8")) or {}
    ingress = doc.get("ingress")
    if isinstance(ingress, list):
        hosts = {item.get("hostname") for item in ingress if isinstance(item, dict)}
        if "pulse.freqpilot.dev" not in hosts:
            doc["ingress"] = [
                {"hostname": "pulse.freqpilot.dev", "service": "http://127.0.0.1:18000"},
                *ingress,
            ]
            tmp = cf.with_suffix(".yml.tmp")
            tmp.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
            os.chown(tmp, st.st_uid, st.st_gid)
            os.chmod(tmp, st.st_mode & 0o777)
            os.replace(tmp, cf)
            pathlib.Path("/tmp/daovang_tunnel_changed").write_text("1", encoding="utf-8")
PY
if sudo test -f /tmp/daovang_tunnel_changed; then
  sudo rm -f /tmp/daovang_tunnel_changed
  sudo docker restart daovang-oracle-tunnel >/dev/null || true
fi
if sudo test -d /etc/dokploy/traefik/dynamic; then
  sudo tee /etc/dokploy/traefik/dynamic/peakpulse.yml >/dev/null <<'YML'
http:
  routers:
    peakpulse-http:
      rule: Host(`pulse.freqpilot.dev`)
      service: peakpulse-svc
      entryPoints:
        - web
    peakpulse-https:
      rule: Host(`pulse.freqpilot.dev`)
      service: peakpulse-svc
      entryPoints:
        - websecure
      tls:
        certResolver: letsencrypt
  services:
    peakpulse-svc:
      loadBalancer:
        servers:
          - url: http://daovang-oracle-web:8000
        passHostHeader: true
YML
fi
echo "$REV" | sudo tee "$RT/.git/refs/heads/main" >/dev/null
sudo docker exec daovang-oracle-scanner python -c "from pathlib import Path; from dao_vang.config.settings import AppSettings; s = AppSettings.from_yaml(Path('/app/configs/msi-production.yaml')); assert s.scanner.shadow_telegram_enabled is False and s.execution.enabled is True and s.execution.initial_equity == 10000.0 and s.execution.live_activated is False"
sudo docker restart daovang-oracle-scanner daovang-oracle-web >/dev/null
sudo docker network connect dokploy-network daovang-oracle-web 2>/dev/null || true
COMPOSE_DIR="$(dirname "$(dirname "$RT")")/code"
if sudo docker ps -a --format '{{.Names}}' | grep -qx 'daovang-oracle-execution'; then
  sudo docker restart daovang-oracle-execution >/dev/null
else
  (cd "$COMPOSE_DIR" && sudo docker compose up -d --no-recreate execution)
fi
(sudo crontab -l 2>/dev/null | grep -v 'shadow_hourly_watchdog.py' || true; echo "0 * * * * python3 $RT/scripts/shadow_hourly_watchdog.py --apply --runtime-dir $RT >> /var/log/daovang-shadow-watchdog.log 2>&1") | sudo crontab -
for i in $(seq 1 36); do
  if curl --fail --silent http://127.0.0.1:18000/api/health >/dev/null && curl --fail --silent http://127.0.0.1:18000/api/ready >/dev/null; then
    echo "DEPLOY_READY_OK (backup=$BK)"
    curl --silent http://127.0.0.1:18000/api/ready
    echo
    exit 0
  fi
  sleep 5
done
echo "ERROR: /api/ready did not stabilize within 180s" >&2
curl --silent http://127.0.0.1:18000/api/ready || true
exit 1
"""


def _build_tar_bytes(root: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for rel in SYNC_PATHS:
            src = root / rel
            if not src.exists():
                raise FileNotFoundError(f"Required deploy artifact missing: {src}")
            files = (
                [src]
                if src.is_file()
                else sorted(p for p in src.rglob("*") if p.is_file())
            )
            for fpath in files:
                arcname = fpath.relative_to(root).as_posix()
                raw = fpath.read_bytes()
                if fpath.suffix in {
                    ".py",
                    ".sh",
                    ".yaml",
                    ".yml",
                    ".md",
                    ".json",
                    ".html",
                    ".css",
                    ".js",
                }:
                    raw = raw.replace(b"\r\n", b"\n")
                info = tarfile.TarInfo(name=arcname)
                info.size = len(raw)
                info.mode = 0o755 if fpath.suffix == ".sh" else 0o644
                tf.addfile(info, io.BytesIO(raw))
    return buf.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        default=os.environ.get("DAO_VANG_ORACLE_HOST", "opc@161.118.250.182"),
        help="SSH user@host for Oracle Cloud (default: opc@161.118.250.182)",
    )
    parser.add_argument(
        "--key",
        default=os.environ.get("DAO_VANG_ORACLE_SSH_KEY", ""),
        help="Explicit SSH private key path (uses IdentitiesOnly=yes when provided)",
    )
    parser.add_argument(
        "--runtime-dir",
        default=os.environ.get("DAO_VANG_ORACLE_RUNTIME_DIR", DEFAULT_RUNTIME_DIR),
        help=f"Dokploy bind-mounted runtime root (default: {DEFAULT_RUNTIME_DIR})",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Upload bundle, update 2-tier policy in msi-production.yaml, and restart scanner + web",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()

    if not (root / "frontend" / "dist" / "index.html").is_file():
        parser.error(
            "frontend/dist/index.html missing — run `cd frontend && npm run build` first"
        )

    ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
    if args.key:
        key_path = Path(args.key).expanduser()
        if not key_path.is_file():
            parser.error(f"SSH key not found: {key_path}")
        ssh_cmd.extend(["-i", str(key_path), "-o", "IdentitiesOnly=yes"])

    bundle = _build_tar_bytes(root)
    print(
        f"Oracle Cloud (OCI Dokploy): {args.host} -> {args.runtime_dir}\n"
        f"Revision: {revision} | Bundle size: {len(bundle) / 1024:.1f} KiB"
    )
    if not args.apply:
        print("Dry-run complete. Re-run with --apply to deploy to Oracle Cloud.")
        return 0

    remote_script = REMOTE_DEPLOY_TEMPLATE.replace(
        "__RUNTIME_DIR__", shlex.quote(args.runtime_dir)
    ).replace("__REVISION__", shlex.quote(revision))
    proc = subprocess.run(
        [*ssh_cmd, args.host, remote_script],
        input=bundle,
        check=False,
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
