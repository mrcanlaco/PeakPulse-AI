"""Deploy a committed revision to Oracle Cloud (OCI) without discarding server changes."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--revision",
        help="Full 40-character Git commit; defaults to local HEAD",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("DAO_VANG_ORACLE_HOST", "oracle-daovang"),
        help="SSH host alias or user@host (default: oracle-daovang / opc@161.118.250.182)",
    )
    parser.add_argument(
        "--key",
        default=os.environ.get("DAO_VANG_ORACLE_SSH_KEY", ""),
        help="Optional explicit SSH private key path (otherwise resolved by ~/.ssh/config)",
    )
    parser.add_argument(
        "--app-dir",
        default=os.environ.get("DAO_VANG_ORACLE_APP_DIR", "$HOME/dao_vang"),
        help="Application directory on Oracle Cloud (default: $HOME/dao_vang)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply after reviewing the target",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    revision = (
        args.revision
        or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    )
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        parser.error("revision must be a full Git commit hash")

    ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
    if args.key:
        key_path = Path(args.key).expanduser()
        if not key_path.is_file():
            parser.error(f"SSH key not found: {key_path}")
        ssh_cmd.extend(["-i", str(key_path)])

    print(f"Oracle Cloud (OCI): {args.host} ({args.app_dir}); revision: {revision}")
    if not args.apply:
        print(
            "Chay lai voi --apply de trien khai revision nay. Thay doi local chua commit se khong duoc gui."
        )
        return 0

    app_dir_expr = (
        '"$HOME/dao_vang"'
        if args.app_dir == "$HOME/dao_vang"
        else shlex.quote(args.app_dir)
    )
    command = f"""
set -eu
APP_DIR={app_dir_expr}
cd "$APP_DIR"
export DAO_VANG_PROJECT_DIR="$APP_DIR"
test "$(git branch --show-current)" = "main" || {{
  echo "Deployment stopped: server checkout is not on main."
  exit 1
}}
test -z "$(git status --porcelain --untracked-files=no)" || {{
  echo "Deployment stopped: preserve and review tracked local changes first."
  exit 1
}}
git fetch origin main --prune
git merge --ff-only {shlex.quote(revision)}
test "$(git rev-parse HEAD)" = {shlex.quote(revision)}
test -z "$(git status --porcelain)" || {{
  echo "Deployment stopped: unexpected untracked files remain after update."
  exit 1
}}
docker compose stop
export DAO_VANG_RUNTIME_UID="$(id -u)"
export DAO_VANG_RUNTIME_GID="$(id -g)"
bash scripts/prepare_runtime_permissions.sh --apply
docker compose build
docker compose up -d --no-build --wait --wait-timeout 180
curl --fail --silent --show-error http://localhost:8000/api/health
curl --fail --silent --show-error http://localhost:8000/api/ready
bash scripts/install_production_cron.sh --apply
"""
    ssh_cmd.extend([args.host, command])
    return subprocess.run(ssh_cmd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
