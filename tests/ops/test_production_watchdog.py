import importlib.util
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("watchdog", ROOT / "scripts/production_watchdog.py")
watchdog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watchdog)


@pytest.fixture
def project(tmp_path):
    health = tmp_path / "src/dao_vang/scanner/healthcheck.py"
    health.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "src/dao_vang/scanner/healthcheck.py", health)
    data = tmp_path / "data"
    data.mkdir()
    now = datetime.now(timezone.utc)
    (data / "scanner_heartbeat.json").write_text(json.dumps({"status": "running", "timestamp": now.isoformat()}))
    (data / "candidate_snapshot.json").write_text(json.dumps({"rows": [], "generated_at": (now - timedelta(hours=2)).isoformat()}))
    return tmp_path


@pytest.mark.parametrize("running,expected", [("scanner\nweb\n", "restart_scanner"), ("web\n", "service_stopped")])
def test_only_stalled_running_service_is_restarted(project, monkeypatch, running, expected):
    monkeypatch.setattr("sys.argv", ["watchdog", "--project", str(project), "--apply"])
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout=running)
    monkeypatch.setattr(watchdog.subprocess, "run", run)
    assert watchdog.main() == 1
    state = json.loads((project / "data/watchdog_state.json").read_text())
    assert state["action"] == expected
    assert sum("restart" in cmd for cmd in calls) == (expected == "restart_scanner")
    if expected == "restart_scanner":
        calls.clear()
        assert watchdog.main() == 1
        assert not calls  # Cooldown survives subsequent invocations.


def test_maintenance_and_dry_run_do_not_mutate(project, monkeypatch):
    monkeypatch.setattr("sys.argv", ["watchdog", "--project", str(project)])
    monkeypatch.setattr(watchdog.subprocess, "run", lambda *a, **k: pytest.fail("No recovery allowed"))
    assert watchdog.main() == 1
    assert not (project / "data/watchdog_state.json").exists()
    (project / "data/maintenance.flag").touch()
    monkeypatch.setattr("sys.argv", ["watchdog", "--project", str(project), "--apply"])
    assert watchdog.main() == 0


def test_restart_budget():
    now = 50000
    assert not watchdog.recovery_allowed({"last_restart": now - 60}, now)
    assert not watchdog.recovery_allowed({"restarts": [now - 3600, now - 7200, now - 10800]}, now)
    assert watchdog.recovery_allowed({"restarts": [now - 21601]}, now)


def test_restart_does_not_interrupt_first_scan(project, monkeypatch):
    now = datetime.now(timezone.utc)
    path = project / "data/scanner_heartbeat.json"
    payload = {"timestamp": now.isoformat(), "status": "running", "cycle": 1,
               "last_cycle_status": "running", "last_cycle_started_at": now.isoformat()}
    path.write_text(json.dumps(payload))
    monkeypatch.setattr("sys.argv", ["watchdog", "--project", str(project), "--apply"])
    monkeypatch.setattr(watchdog.subprocess, "run", lambda *a, **k: pytest.fail("First scan needs grace"))
    assert watchdog.main() == 1
    assert json.loads((project / "data/watchdog_state.json").read_text())["action"] == "startup_grace"
    assert not watchdog.startup_grace(project / "data", now.timestamp() + 301)
