"""Behavior checks for the repository-owned cron installer."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="The production cron installer runs on Linux",
)
ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "scripts" / "install_production_cron.sh"


def test_installer_preserves_unrelated_jobs_and_removes_legacy_reset(
    tmp_path: Path,
):
    project = tmp_path / "project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "backup_to_gdrive.sh").write_text("# test\n", encoding="utf-8")

    state = tmp_path / "crontab.txt"
    state.write_text(
        "5 1 * * * echo unrelated\n"
        "0 0 * * * /home/ubuntu/dao_vang/scripts/backup_to_gdrive.sh\n"
        "*/5 * * * * git reset --hard origin/main # auto_update\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_crontab = fake_bin / "crontab"
    fake_crontab.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"-l\" ]; then\n"
        "  cat \"$CRONTAB_STATE\"\n"
        "else\n"
        "  cp \"$1\" \"$CRONTAB_STATE\"\n"
        "fi\n",
        encoding="utf-8",
    )
    fake_crontab.chmod(0o755)

    env = os.environ.copy()
    env["DAO_VANG_PROJECT_DIR"] = str(project)
    env["CRONTAB_STATE"] = str(state)
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        ["bash", str(INSTALLER), "--apply"],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    installed = state.read_text(encoding="utf-8")
    assert "echo unrelated" in installed
    assert "auto_update" not in installed
    assert "reset --hard" not in installed
    assert installed.count("# BEGIN DAO_VANG_MANAGED") == 1
    assert installed.count("backup_to_gdrive.sh") == 1
    assert installed.count("prune_old_data.sh --apply") == 1
    assert installed.count("production_watchdog.py --apply") == 1
    assert list((project / "backups" / "crontab").glob("crontab-*.txt"))
