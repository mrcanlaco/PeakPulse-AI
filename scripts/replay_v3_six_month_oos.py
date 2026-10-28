"""Replay exported V3 OOS events against local price paths only.

The event cohort and both timing lanes are selected upstream by
``export_v3_oos_reference.py``.  This worker deliberately does not apply a
second cooldown or select a new cohort.  It reuses the six-month study's
read-only ``MarketFiles``, ``_replay_event`` and ``_metrics`` helpers so that
the backend receives the actual price-path and post-stop diagnostics without
silently turning missing funding attestation into compact wins.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

DEFAULT_SOURCE = REPO_ROOT / "artifacts/v3_six_month_20260915/oos_reference_events.json"
DEFAULT_MARKET_DB = Path(r"D:\Quant-trading\data_lake\quant_master.duckdb")
DEFAULT_OUTPUT = REPO_ROOT / "artifacts/v3_six_month_20260915/oos_price_replay.json"
LANES = ("locked_parent_oos", "current_timing_runtime_reference")


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _path_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, pd.Timestamp)):
        if isinstance(value, pd.Timestamp):
            value = value.to_pydatetime()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _load_research_helper():
    path = REPO_ROOT / "scripts/research_v3_six_months.py"
    name = "_v3_six_month_replay_research_helper"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load research helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _source_rows(payload: dict[str, Any], helper) -> pd.DataFrame:
    lanes = payload.get("lanes")
    if not isinstance(lanes, dict):
        raise ValueError("OOS reference has no lanes object")
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for lane in LANES:
        lane_payload = lanes.get(lane)
        if not isinstance(lane_payload, dict) or not isinstance(lane_payload.get("events"), list):
            raise ValueError(f"OOS reference lane missing events: {lane}")
        for event in lane_payload["events"]:
            if not isinstance(event, dict):
                raise ValueError(f"invalid event in lane: {lane}")
            feature_time = pd.Timestamp(event["feature_time_utc"])
            if feature_time.tzinfo is None:
                raise ValueError("feature_time_utc must be timezone-aware")
            feature_time = feature_time.tz_convert("UTC")
            source_signal = pd.Timestamp(event["signal_time_utc"])
            if source_signal.tzinfo is None:
                raise ValueError("signal_time_utc must be timezone-aware")
            source_signal = source_signal.tz_convert("UTC")
            normalized = helper._normalise_boundary(feature_time.to_pydatetime())
            if normalized != source_signal.to_pydatetime():
                raise ValueError(
                    f"source signal boundary mismatch for {event.get('event_id')}: "
                    f"{normalized.isoformat()} != {source_signal.isoformat()}"
                )
            event_id = str(event["event_id"])
            key = (lane, event_id)
            if key in seen:
                raise ValueError(f"duplicate source event: {key}")
            seen.add(key)
            records.append(
                {
                    "event_id": event_id,
                    "source_event_id": str(event.get("source_event_id") or ""),
                    "lane": lane,
                    "champion": bool(event["champion_gate"]["accepted"]),
                    "symbol": str(event["symbol"]),
                    "feature_time": feature_time,
                    "feature_time_utc": feature_time.isoformat(),
                    "signal_time_utc": source_signal.isoformat(),
                    "episode_id": str(event.get("timing_episode_id") or event["source_episode_id"]),
                    "source_episode_id": str(event["source_episode_id"]),
                    "timing_episode_id": event.get("timing_episode_id"),
                    "fold": int(event["fold"]),
                    "score": float(event["score"]),
                    "raw_score": float(event["raw_score"]),
                    "fold_threshold": float(event["fold_threshold"]),
                    "label_value": event.get("label_value"),
                    "price_ret_24h": float(event["price_ret_24h"]),
                    "distance_from_high_24h": float(event["distance_from_high_24h"]),
                    "funding_percentile_30d": event["pit"].get("funding_percentile_30d"),
                    "funding_persistence_7d": event["pit"].get("funding_persistence_7d"),
                    "funding_change_8h": event["pit"].get("funding_change_8h"),
                    # These are already-selected events.  They are retained for
                    # compatibility with the shared metrics helper only; this
                    # worker never reapplies either cooldown.
                    "selected_24h": True,
                    "selected_48h": True,
                }
            )
    frame = pd.DataFrame(records)
    if frame.empty:
        raise ValueError("OOS reference contains no events")
    if frame["event_id"].duplicated().any():
        raise ValueError("event_id is not globally unique across lanes")
    return frame.sort_values(["feature_time", "symbol", "lane"], kind="mergesort").reset_index(
        drop=True
    )


def _replay_rows(frame: pd.DataFrame, market_db: Path, helper) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    source_reads: list[dict[str, Any]] = []
    market = helper.MarketFiles(market_db)
    try:
        for symbol, indices in frame.groupby("symbol", sort=True).groups.items():
            rows = frame.loc[indices].sort_values("feature_time", kind="mergesort")
            signal_times = [
                helper._normalise_boundary(pd.Timestamp(value).to_pydatetime())
                for value in rows["feature_time"]
            ]
            first_signal = min(signal_times)
            last_horizon = max(signal_times) + helper.HORIZON
            bar_times, bars, bar_meta = market.bars_for(
                str(symbol), first_signal - helper.BAR_STEP, last_horizon + helper.BAR_STEP
            )
            funding, funding_meta = market.funding_for(
                str(symbol), first_signal - helper.FUNDING_STEP, last_horizon + helper.FUNDING_STEP
            )
            source_reads.append(
                {
                    "symbol": str(symbol),
                    "event_rows": int(len(rows)),
                    "bar_source": bar_meta,
                    "funding_source": funding_meta,
                }
            )
            for _, row in rows.iterrows():
                replay = helper._replay_event(row, bars, bar_times, funding, funding_meta)
                replay["event_id"] = str(row["event_id"])
                replay["source_event_id"] = str(row["source_event_id"])
                replay["lane"] = str(row["lane"])
                replay["champion"] = bool(row["champion"])
                replay["feature_time_utc"] = str(row["feature_time_utc"])
                replay["signal_time_utc"] = str(row["signal_time_utc"])
                replay["episode_id"] = str(row["episode_id"])
                replay["source_episode_id"] = str(row["source_episode_id"])
                replay["timing_episode_id"] = row["timing_episode_id"]
                replay["fold"] = int(row["fold"])
                replay["source_score"] = float(row["score"])
                replay["source_raw_score"] = float(row["raw_score"])
                replay["source_fold_threshold"] = float(row["fold_threshold"])
                replay["normalized_signal_matches_source"] = (
                    replay["signal_time_normalized"] == replay["signal_time_utc"]
                )
                replay["selection_already_applied"] = True
                replay["additional_cooldown_applied"] = False
                replay["compact_funding_eligibility"] = "withheld_no_provider_attestation"
                # The compact weighted-average fill and post-stop diagnostic
                # were actually replayed. Financial eligibility remains
                # withheld because no provider funding attestation is present.
                replay["compact_execution_path_replayed"] = True
                replay["compact_financial_outcome_eligible"] = False
                replay["bar_source_meta"] = bar_meta
                replay["funding_source_meta"] = funding_meta
                if not replay["normalized_signal_matches_source"]:
                    raise RuntimeError(f"normalized/source signal mismatch: {replay['event_id']}")
                records.append(replay)
    finally:
        market.close()
    records.sort(key=lambda item: (item["signal_time_normalized"], item["symbol"], item["lane"]))
    return records, {
        "unique_symbols_read_once": len(source_reads),
        "event_rows_replayed": len(records),
        "source_reads": source_reads,
    }


def _status_counts(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(str(record.get(field)) for record in records).items()))


def _price_summary(records: list[dict[str, Any]], helper, name: str) -> dict[str, Any]:
    frame = pd.DataFrame(records)
    if frame.empty:
        return {
            "name": name,
            "rows": 0,
            "price_path_resolved": 0,
            "price_targets": 0,
            "price_target_rate": None,
            "actual_status_counts": {},
            "post_stop_status_counts": {},
            "funding_verified_rows": 0,
            "compact_funding_eligibility": "withheld_no_provider_attestation",
            "compact_execution_path_replayed": True,
            "compact_financial_outcome_eligible": False,
            "engine_metrics": helper._metrics(frame, name),
        }
    resolved = frame["price_path_resolved"].fillna(False).astype(bool)
    targets = resolved & frame["actual_status"].eq("target")
    funding_verified = frame["funding_verified"].fillna(False).astype(bool)
    return {
        "name": name,
        "rows": int(len(frame)),
        "price_path_resolved": int(resolved.sum()),
        "price_targets": int(targets.sum()),
        "price_target_rate": float(targets.sum() / resolved.sum()) if resolved.any() else None,
        "actual_status_counts": _status_counts(records, "actual_status"),
        "post_stop_status_counts": _status_counts(records, "post_stop_status"),
        "funding_verified_rows": int(funding_verified.sum()),
        "funding_cadence_heuristic_rows": int(
            frame["funding_cadence_heuristic_ok"].fillna(False).astype(bool).sum()
        ),
        "compact_funding_eligibility": "withheld_no_provider_attestation",
        "compact_execution_path_replayed": True,
        "compact_financial_outcome_eligible": False,
        "engine_metrics": helper._metrics(frame, name),
    }


def _monthly_summary(records: list[dict[str, Any]], helper, name: str) -> list[dict[str, Any]]:
    if not records:
        return []
    frame = pd.DataFrame(records)
    months = pd.to_datetime(frame["feature_time"], utc=True).dt.strftime("%Y-%m")
    return [
        _price_summary(
            [record for record, month in zip(records, months, strict=True) if month == period],
            helper,
            f"{name}:{period}",
        )
        for period in sorted(months.unique())
    ]


def _lane_summary(lane: str, records: list[dict[str, Any]], helper) -> dict[str, Any]:
    champion = [record for record in records if record["champion"]]
    return {
        "lane": lane,
        "source_selected_count": len(records),
        "source_champion_subset_count": len(champion),
        "all_selected": _price_summary(records, helper, lane),
        "champion_subset": _price_summary(champion, helper, f"{lane}:champion_subset"),
        "monthly_all_selected": _monthly_summary(records, helper, lane),
        "monthly_champion_subset": _monthly_summary(champion, helper, f"{lane}:champion_subset"),
    }


def run(
    *,
    source: Path = DEFAULT_SOURCE,
    market_db: Path = DEFAULT_MARKET_DB,
    output: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    source, market_db, output = _resolve(source), _resolve(market_db), _resolve(output)
    payload = json.loads(source.read_text(encoding="utf-8"))
    helper = _load_research_helper()
    frame = _source_rows(payload, helper)
    records, coverage = _replay_rows(frame, market_db, helper)
    source_event_lane_counts = frame.groupby("source_event_id")["lane"].nunique()
    coverage.update(
        {
            "lane_event_rows": int(len(frame)),
            "unique_source_event_ids": int(frame["source_event_id"].nunique()),
            "source_events_in_both_lanes": int((source_event_lane_counts > 1).sum()),
            "lanes_are_not_independent": True,
        }
    )
    lane_reports = {
        lane: _lane_summary(lane, [record for record in records if record["lane"] == lane], helper)
        for lane in LANES
    }
    result = {
        "artifact": "v3_six_month_oos_price_replay",
        "artifact_version": "v3_six_month_oos_price_replay_v1",
        "generated_at_utc": datetime.now(timezone.utc),
        "status": "retrospective_price_path_replay_research_only",
        "window_utc": payload.get("window_utc"),
        "missing_oos_months": ["2026-02"],
        "source": {
            "reference_artifact": _path_label(source),
            "reference_artifact_sha256": _sha256_file(source),
            "source_event_rows": len(frame),
            "source_unique_event_ids": int(frame["source_event_id"].nunique()),
            "source_events_in_both_lanes": int((source_event_lane_counts > 1).sum()),
            "source_unique_symbols": int(frame["symbol"].nunique()),
            "market_db": _path_label(market_db),
            "market_db_sha256": _sha256_file(market_db) if market_db.is_file() else None,
        },
        "replay_contract": {
            "engine_source": "scripts/research_v3_six_months.py:MarketFiles,_replay_event,_metrics",
            "price_path_replay": True,
            "retrospective_close_fill": True,
            "selection_already_applied": True,
            "additional_cooldown_applied": False,
            "funding_attestation": "not supplied; cadence is retained as a diagnostic heuristic only",
            "compact_funding_eligibility": "withheld_no_provider_attestation",
            "compact_execution_path_replayed": True,
            "compact_financial_outcome_eligible": False,
            "causal_or_policy_advantage_claim": False,
        },
        "coverage": coverage,
        "lanes": lane_reports,
        "events": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--market-db", type=Path, default=DEFAULT_MARKET_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run(source=args.source, market_db=args.market_db, output=args.output)
    print(
        json.dumps(
            {
                "output": _path_label(_resolve(args.output)),
                "events": len(result["events"]),
                "lanes": {
                    lane: {
                        "selected": value["source_selected_count"],
                        "champion_subset": value["source_champion_subset_count"],
                    }
                    for lane, value in result["lanes"].items()
                },
                "symbols_read_once": result["coverage"]["unique_symbols_read_once"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
