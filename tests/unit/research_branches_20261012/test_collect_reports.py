import importlib.util
import json
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts/research_branches_20261012/collect_reports.py"
SPEC = importlib.util.spec_from_file_location("branch_collector", MODULE_PATH)
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


@pytest.fixture
def workspace(tmp_path):
    protocol = tmp_path / collector.PROTOCOL
    protocol.parent.mkdir(parents=True)
    protocol.write_text('{"promotion":{"enabled":false}}', encoding="utf-8")
    (tmp_path / collector.PROTOCOL_LOCK).write_text(json.dumps({
        "protocol_path": collector.PROTOCOL.as_posix(),
        "sha256": collector.sha256(protocol),
    }), encoding="utf-8")
    return tmp_path


def write_report(root, branch="v3", **changes):
    source = root / "source.json"
    source.write_text('{"evidence":1}', encoding="utf-8")
    report = {
        "branch": branch, "status": "exploratory", "evidence": [],
        "limitations": ["Historical sample"], "next_experiment": {},
        "source_hashes": {"source.json": collector.sha256(source)},
    }
    report.update(changes)
    path = root / collector.OUTPUT_ROOT / branch / "report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding="utf-8")


def test_missing_reports_are_pending_not_success(workspace):
    result = collector.collect(workspace)
    assert not result["all_reports_integrity_verified"]
    assert all(r["evidence_integrity"] == "pending" for r in result["branches"])


def test_hashes_do_not_prove_profitability(workspace):
    for branch in collector.BRANCHES:
        write_report(workspace, branch)
    result = collector.collect(workspace)
    assert result["all_reports_integrity_verified"]
    assert not result["profitability_verified"]
    assert not result["auto_promotion_allowed"]


def test_changed_source_is_rejected(workspace):
    write_report(workspace)
    (workspace / "source.json").write_text("changed", encoding="utf-8")
    report = collector.collect(workspace)["branches"][0]
    assert report["evidence_integrity"] == "invalid"
    assert "source_hash_mismatch:source.json" in report["issues"]


@pytest.mark.parametrize("changes", [
    {"source_hashes": {}}, {"evidence": "claimed win"},
])
def test_bad_schema_is_rejected(workspace, changes):
    write_report(workspace, **({"status": "test"} | changes))
    assert not collector.collect(workspace)["all_reports_integrity_verified"]


def test_wrong_branch_identity_is_rejected(workspace):
    write_report(workspace)
    path = workspace / collector.OUTPUT_ROOT / "v3/report.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["branch"] = "flow"
    path.write_text(json.dumps(report), encoding="utf-8")
    result = collector.collect(workspace)["branches"][0]
    assert "branch_identity_mismatch" in result["issues"]


def test_external_source_is_rejected(workspace):
    write_report(workspace, source_hashes={"../outside": "0" * 64})
    result = collector.collect(workspace)["branches"][0]
    assert "source_outside_workspace:../outside" in result["issues"]


def test_invalid_json_is_reported(workspace):
    write_report(workspace)
    path = workspace / collector.OUTPUT_ROOT / "v3/report.json"
    path.write_text("{broken", encoding="utf-8")
    assert collector.collect(workspace)["branches"][0]["status"] == "invalid_report"


def test_protocol_mutation_fails_lock(workspace):
    for branch in collector.BRANCHES:
        write_report(workspace, branch)
    (workspace / collector.PROTOCOL).write_text("{}", encoding="utf-8")
    result = collector.collect(workspace)
    assert not result["protocol_lock_verified"]
    assert not result["all_reports_integrity_verified"]
