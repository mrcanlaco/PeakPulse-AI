"""Checksummed runtime recovery including nested SQLite state and model files."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path

from .contracts import canonical, utc_now


def capture_runtime(data: Path, artifacts: Path, destination: Path):
    """Caller must quiesce scanner, web and executor for a common snapshot."""
    if not data.is_dir() or not artifacts.is_dir():
        raise FileNotFoundError("runtime_source_missing")
    if destination.resolve().is_relative_to(
        data.resolve()
    ) or destination.resolve().is_relative_to(artifacts.resolve()):
        raise ValueError("snapshot_destination_inside_source")
    if destination.exists():
        raise FileExistsError("snapshot_destination_exists")
    destination.mkdir(parents=True)
    inventory = {}
    for prefix, root in (("data", data), ("artifacts", artifacts)):
        for source in sorted(root.rglob("*")):
            if not source.is_file() or source.is_symlink():
                continue
            relative = source.relative_to(root)
            if prefix == "data" and (
                relative.parts[0] in {"raw", "normalized", "duckdb_temp"}
                or source.suffix not in {".json", ".sqlite", ".sqlite3", ".duckdb"}
            ):
                continue
            # Secrets and temporary/lock files are never part of the archive.
            if source.name.startswith(".") or source.suffix in {".lock", ".log"}:
                continue
            target = destination / prefix / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix in {".sqlite", ".sqlite3"}:
                db = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)
                out = sqlite3.connect(target)
                try:
                    db.backup(out)
                finally:
                    out.close()
                    db.close()
            else:
                shutil.copy2(source, target)
            inventory[target.relative_to(destination).as_posix()] = hashlib.sha256(
                target.read_bytes()
            ).hexdigest()
    (destination / "manifest.json").write_text(
        canonical({"version": 1, "created_at": utc_now(), "files": inventory}),
        encoding="utf-8",
    )
    return inventory


def verify_runtime(snapshot: Path):
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    for name, checksum in manifest["files"].items():
        path = (snapshot / name).resolve()
        if (
            not path.is_relative_to(snapshot.resolve())
            or not path.is_file()
            or path.is_symlink()
        ):
            raise ValueError("snapshot_path_invalid")
        if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            raise ValueError("snapshot_checksum_mismatch")
    return manifest


def restore_runtime(snapshot: Path, destination: Path):
    """Restore into a NEW directory for inspection before replacing a service."""
    manifest = verify_runtime(snapshot)
    if destination.exists():
        raise FileExistsError("restore_requires_new_directory")
    destination.mkdir(parents=True)
    for name in manifest["files"]:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snapshot / name, target)
    return manifest


def install_runtime(snapshot: Path, data: Path, artifacts: Path, rollback: Path):
    """Install a verified, quiesced snapshot and retain each replaced file."""
    manifest = verify_runtime(snapshot)
    roots = {"data": data.resolve(), "artifacts": artifacts.resolve()}
    targets = []
    for name in manifest["files"]:
        relative = Path(name)
        if len(relative.parts) < 2 or relative.parts[0] not in roots:
            raise ValueError("unsupported_snapshot_root")
        root = roots[relative.parts[0]]
        target = root.joinpath(*relative.parts[1:])
        if (
            not target.resolve().is_relative_to(root)
            or target.is_symlink()
            or target.is_dir()
        ):
            raise ValueError("restore_target_escape")
        targets.append((name, target))
    if rollback.exists():
        raise FileExistsError("rollback_destination_exists")
    rollback.mkdir(parents=True)
    actions = []
    journal = rollback / "restore_actions.json"
    try:
        for name, target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            paths = [target]
            if target.suffix in {".sqlite", ".sqlite3"}:
                paths += [Path(str(target) + suffix) for suffix in ("-wal", "-shm")]
            if target.suffix == ".duckdb":
                paths += [Path(str(target) + ".wal")]
            for path in paths:
                backup = rollback / "originals" / name
                if path != target:
                    backup = Path(str(backup) + str(path)[len(str(target)) :])
                action = {
                    "target": str(path),
                    "backup": str(backup),
                    "existed": path.exists(),
                }
                actions.append(action)
                journal.write_text(canonical(actions), encoding="utf-8")
                if path.exists():
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(path, backup)
            temporary = target.with_name(target.name + ".restore.tmp")
            shutil.copy2(snapshot / name, temporary)
            os.replace(temporary, target)
        # Restoring an older journal must never silently resume new orders.
        from .store import ExecutionStore

        for state in data.glob("execution/*/state.sqlite3"):
            ExecutionStore(state).set(
                "pause",
                {
                    "paused": True,
                    "reason": "restored_requires_review",
                    "at": utc_now().isoformat(),
                },
            )
    except Exception:
        rollback_runtime(rollback, data, artifacts)
        raise
    return manifest


def rollback_runtime(rollback: Path, data: Path, artifacts: Path):
    if (rollback / "rolled_back").exists():
        return
    roots = (data.resolve(), artifacts.resolve())
    actions = json.loads(
        (rollback / "restore_actions.json").read_text(encoding="utf-8")
    )
    for action in reversed(actions):
        target, backup = Path(action["target"]), Path(action["backup"])
        if not any(
            target.resolve().is_relative_to(root) for root in roots
        ) or not backup.resolve().is_relative_to(rollback.resolve()):
            raise ValueError("rollback_path_escape")
        if backup.exists():
            os.replace(backup, target)
        elif not action["existed"]:
            target.unlink(missing_ok=True)
    (rollback / "rolled_back").write_text(utc_now().isoformat(), encoding="utf-8")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["capture", "install", "rollback"])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--rollback", type=Path)
    args = parser.parse_args()
    if args.action == "capture":
        capture_runtime(args.data, args.artifacts, args.snapshot)
    elif args.rollback is None:
        parser.error("--rollback is required")
    elif args.action == "install":
        install_runtime(args.snapshot, args.data, args.artifacts, args.rollback)
    else:
        rollback_runtime(args.rollback, args.data, args.artifacts)
