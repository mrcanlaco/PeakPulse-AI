"""Freeze / validation / lock / test gates with auditable SHA-256 seals.

Protocol
    1. develop + tune on TRAIN only (``Lab.run(spec, "train")`` has no gate).
    2. ``freeze_round`` writes the exact specs to ``rounds/<name>/frozen.json`` + sha256.
       Frozen files are immutable (refuse to overwrite).
    3. VALIDATION may only be evaluated for spec ids present in a sealed frozen file.
    4. ``lock_candidates`` seals the selected ids (+ the frozen file hash) in
       ``candidate_lock.json`` BEFORE any test data is touched.
    5. TEST may only be evaluated for locked spec ids; every val/test access is
       appended to ``access_log.jsonl``.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .data import OUT_DIR

ROUNDS_DIR = OUT_DIR / "rounds"
LOCK_PATH = OUT_DIR / "candidate_lock.json"
LOCK_SHA = OUT_DIR / "candidate_lock.sha256"
ACCESS_LOG = OUT_DIR / "access_log.jsonl"


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def spec_id(spec: dict) -> str:
    h = hashlib.sha1(canonical({"f": spec["family"], "p": spec["params"]}).encode()).hexdigest()
    return f"{spec['family']}-{h[:8]}"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _log(split: str, ids: list[str], note: str = "") -> None:
    ACCESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ACCESS_LOG.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "split": split, "ids": ids, "note": note})
            + "\n"
        )


def freeze_round(name: str, specs: list[dict], meta: dict) -> Path:
    d = ROUNDS_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    path = d / "frozen.json"
    if path.exists():
        raise FileExistsError(f"round {name} already frozen; frozen files are immutable")
    payload = {
        "round": name,
        "meta": meta,
        "specs": [{"id": spec_id(s), **s} for s in specs],
    }
    path.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    (d / "frozen.sha256").write_text(sha256_file(path), encoding="utf-8")
    _log("freeze", [spec_id(s) for s in specs], name)
    return path


def load_frozen(name: str) -> dict:
    d = ROUNDS_DIR / name
    path = d / "frozen.json"
    if sha256_file(path) != (d / "frozen.sha256").read_text(encoding="utf-8").strip():
        raise ValueError(f"frozen seal mismatch for round {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def frozen_ids() -> set[str]:
    ids: set[str] = set()
    if not ROUNDS_DIR.exists():
        return ids
    for d in ROUNDS_DIR.iterdir():
        if (d / "frozen.json").exists():
            ids |= {s["id"] for s in load_frozen(d.name)["specs"]}
    return ids


def lock_candidates(selected: list[dict], note: str) -> Path:
    if LOCK_PATH.exists():
        raise FileExistsError("candidate_lock.json exists; test list is already locked")
    fz = frozen_ids()
    for s in selected:
        if spec_id(s) not in fz:
            raise PermissionError(f"{spec_id(s)} was never frozen")
    payload = {
        "note": note,
        "locked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "specs": [{"id": spec_id(s), **s} for s in selected],
        "rounds": {
            d.name: sha256_file(d / "frozen.json")
            for d in sorted(ROUNDS_DIR.iterdir())
            if (d / "frozen.json").exists()
        },
    }
    LOCK_PATH.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    LOCK_SHA.write_text(sha256_file(LOCK_PATH), encoding="utf-8")
    _log("lock", [spec_id(s) for s in selected], note)
    return LOCK_PATH


def locked_ids() -> set[str]:
    if not LOCK_PATH.exists():
        return set()
    if sha256_file(LOCK_PATH) != LOCK_SHA.read_text(encoding="utf-8").strip():
        raise ValueError("candidate_lock seal mismatch")
    return {s["id"] for s in json.loads(LOCK_PATH.read_text(encoding="utf-8"))["specs"]}


def load_lock() -> dict:
    locked_ids()
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))


def authorize(spec: dict, split: str) -> None:
    sid = spec_id(spec)
    if split == "train":
        return
    if split == "val":
        if sid not in frozen_ids():
            raise PermissionError(f"validation requires a frozen spec: {sid}")
        return
    if split == "test":
        if sid not in locked_ids():
            raise PermissionError(f"test requires a locked spec: {sid}")
        return
    raise KeyError(split)


def record_access(split: str, ids: list[str], note: str = "") -> None:
    if split in ("val", "test"):
        _log(split, ids, note)


def access_summary() -> str:
    """One-line digest of access_log.jsonl (freeze / val / lock / test events)."""
    if not ACCESS_LOG.exists():
        return "no log"
    counts: dict[str, int] = {}
    ids: dict[str, set] = {}
    for line in ACCESS_LOG.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        counts[e["split"]] = counts.get(e["split"], 0) + 1
        ids.setdefault(e["split"], set()).update(e["ids"])
    return ", ".join(f"{k}: {counts[k]} lần/{len(ids[k])} spec" for k in sorted(counts))
