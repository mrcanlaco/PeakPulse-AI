"""Capture all inputs before the final experiments and verify them afterward."""
from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts/fibo_trend_short"
PATH = ART / "METHOD_INPUT_MANIFEST_v4_0_6.json"


def capture() -> dict:
    from universe_reaudit_v402_worker import compute_universe_input_fingerprint_and_manifest
    fp, manifest = compute_universe_input_fingerprint_and_manifest()
    extra = [
        "scripts/fibo_research/complete_method_v406.py",
        "scripts/fibo_research/benchmark_method_v406.py",
        "scripts/fibo_research/pit_method_v406.py",
        "scripts/fibo_research/ledger_reconciliation.py",
        "scripts/fibo_research/method_provenance_v406.py",
        "scripts/fibo_research/method_source_checks_v406.py",
        "scripts/fibo_research/pit_funding_v406.py",
        "scripts/fibo_research/paper_plan_v406.py",
        "src/dao_vang/fibo_short/paper_rules_v406.py",
        "tests/unit/fibo_short/test_research_contracts.py",
        "tests/unit/fibo_short/test_paper_rules_v406.py",
        "tests/unit/fibo_short/test_fibo_short.py",
        "artifacts/fibo_trend_short/METHOD_v406_EXPERIMENT_PROTOCOL.json",
    ]
    files = dict(manifest["all_hashed_paths_sha256"])
    files.update({str((ROOT / p).resolve()): hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in extra})
    payload = {"captured_before_final_runs_at_utc": datetime.now(timezone.utc).isoformat(),
               "universe_input_fingerprint_sha256": fp, "base_manifest": manifest,
               "files": files, "file_count": len(files)}
    PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def verify() -> dict:
    manifest = json.loads(PATH.read_text(encoding="utf-8"))
    changed = [p for p, digest in manifest["files"].items()
               if hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest]
    if changed:
        raise AssertionError(f"Inputs changed during experiment: {changed}")
    return {"all_unchanged": True, "files_checked": len(manifest["files"]),
            "manifest_sha256": hashlib.sha256(PATH.read_bytes()).hexdigest()}


if __name__ == "__main__":
    print(json.dumps({"file_count": capture()["file_count"]}))
