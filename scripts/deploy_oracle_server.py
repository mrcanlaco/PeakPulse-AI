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
    "src/dao_vang/config/settings.py",
    "src/dao_vang/fibo_short/scanner_lane.py",
    "src/dao_vang/scanner/daemon.py",
    "src/dao_vang/scanner/healthcheck.py",
    "src/dao_vang/web/api_server.py",
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
for rel in src/dao_vang/config/settings.py src/dao_vang/fibo_short/scanner_lane.py src/dao_vang/scanner/daemon.py src/dao_vang/scanner/healthcheck.py src/dao_vang/web/api_server.py; do
  if sudo test -f "$RT/$rel"; then
    sudo mkdir -p "$BK/$(dirname "$rel")"
    sudo cp -a "$RT/$rel" "$BK/$rel"
  fi
done
sudo rm -rf "$RT/frontend/dist"
sudo mkdir -p "$RT/frontend/dist"
sudo tar -xzf - -C "$RT"
sudo chown -R root:root "$RT/src" "$RT/frontend/dist" "$RT/docs" "$RT/CHANGELOG.md" "$RT/configs/live.yaml" "$RT/configs/dev.yaml" "$RT/configs/default.example.yaml"
sudo python3 - "$RT/configs/msi-production.yaml" <<'PY'
import os
import pathlib
import sys
import yaml

p = pathlib.Path(sys.argv[1])
if p.exists():
    st = p.stat()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
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
        data["fibo_trend_short"]["telegram_allowed_policies"] = [
            "elite_sniper_risk",
            "sniper_rr1_horizon24",
        ]
    tmp = p.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    os.chown(tmp, st.st_uid, st.st_gid)
    os.chmod(tmp, st.st_mode & 0o777)
    os.replace(tmp, p)
PY
echo "$REV" | sudo tee "$RT/.git/refs/heads/main" >/dev/null
sudo docker exec daovang-oracle-scanner python -c "from pathlib import Path; from dao_vang.config.settings import AppSettings; s = AppSettings.from_yaml(Path('/app/configs/msi-production.yaml')); assert s.scanner.shadow_telegram_enabled is False and s.fibo_trend_short.telegram_allowed_policies == ['elite_sniper_risk', 'sniper_rr1_horizon24']"
sudo docker restart daovang-oracle-scanner daovang-oracle-web >/dev/null
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
