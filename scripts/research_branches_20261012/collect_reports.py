"""Collect separate research evidence; never infer a profitable winner."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

BRANCHES = ("v3", "trend", "flow")
PROTOCOL = Path("configs/research_branches_20261012.json")
PROTOCOL_LOCK = Path("configs/research_branches_20261012.lock.json")
OUTPUT_ROOT = Path("artifacts/research_branches_20261012")
AUTHORIZED_DATA_ROOTS = (
    Path("C:/Quant-trading/data_lake"),
    Path("D:/SharedMarketData/multiyear_2020_2026"),
    Path("D:/ProjectColdStorage/dao_vang/annual_profit_20260918"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect(root: Path) -> dict:
    root = root.resolve()
    protocol_path = root / PROTOCOL
    protocol = json.loads(protocol_path.read_text(encoding="utf-8-sig"))
    protocol_hash = sha256(protocol_path)
    lock_path = root / PROTOCOL_LOCK
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8-sig"))
        protocol_lock_verified = (
            isinstance(lock, dict)
            and lock.get("protocol_path") == PROTOCOL.as_posix()
            and lock.get("sha256") == protocol_hash
        )
    except (OSError, ValueError, UnicodeError):
        protocol_lock_verified = False
    records = []
    for branch in BRANCHES:
        report_path = root / OUTPUT_ROOT / branch / "report.json"
        record = {"branch": branch, "report_path": str(report_path), "issues": []}
        if not report_path.is_file():
            record.update(evidence_integrity="pending", status="report_missing")
            records.append(record)
            continue
        record["report_sha256"] = sha256(report_path)
        try:
            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
            if not isinstance(report, dict):
                raise ValueError("Report must be a JSON object")
        except (ValueError, UnicodeError) as exc:
            record.update(evidence_integrity="invalid", status="invalid_report")
            record["issues"].append(str(exc))
            records.append(record)
            continue
        if report.get("branch") != branch:
            record["issues"].append("branch_identity_mismatch")
        for field, expected in (
            ("status", str), ("evidence", list), ("limitations", list),
            ("next_experiment", dict), ("source_hashes", dict),
        ):
            if not isinstance(report.get(field), expected):
                record["issues"].append(f"missing_or_invalid_{field}")
        hashes = report.get("source_hashes")
        verified = 0
        if isinstance(hashes, dict):
            if not hashes:
                record["issues"].append("no_source_hashes")
            for name, digest in hashes.items():
                source = Path(name)
                if not source.is_absolute():
                    source = root / source
                # External data access is limited to the explicitly known research lake.
                source = source.resolve()
                allowed = source.is_relative_to(root) or any(
                    source.is_relative_to(data_root.resolve())
                    for data_root in AUTHORIZED_DATA_ROOTS
                )
                if not allowed:
                    record["issues"].append(f"source_outside_workspace:{name}")
                elif not source.is_file():
                    record["issues"].append(f"source_missing:{name}")
                elif sha256(source) != digest:
                    record["issues"].append(f"source_hash_mismatch:{name}")
                else:
                    verified += 1
        record.update(
            status=report.get("status"),
            evidence=report.get("evidence"),
            limitations=report.get("limitations"),
            next_experiment=report.get("next_experiment"),
            verified_source_count=verified,
            evidence_integrity="verified" if not record["issues"] else "invalid",
        )
        records.append(record)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": protocol,
        "protocol_sha256": protocol_hash,
        "protocol_lock_verified": protocol_lock_verified,
        "branches": records,
        "all_reports_integrity_verified": protocol_lock_verified and all(
            r["evidence_integrity"] == "verified" for r in records
        ),
        "profitability_verified": False,
        "auto_promotion_allowed": False,
        "interpretation": "Integrity verifies source bytes and report structure only, not financial correctness. No cross-branch performance ranking is inferred.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    # stdout only: existing evidence files can never be overwritten by collection.
    print(json.dumps(collect(args.root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
