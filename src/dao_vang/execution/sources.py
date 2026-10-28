"""Qualified scanner predictions, not Telegram alerts, feed execution."""

from __future__ import annotations

import hashlib
from datetime import timedelta, timezone
from pathlib import Path

from dao_vang.data.storage.duckdb import open_read_only_connection

from .contracts import (
    ClosedBar,
    StrategyManifest,
    TradeSignal,
    atr14,
    policy_contract,
    utc_now,
)


def freeze_manifest(
    root: Path,
    model_dir: Path,
    model_id: str,
    label_version: str,
    threshold: float,
    config,
    source_policy=None,
) -> StrategyManifest:
    paths = list(model_dir.rglob("*"))
    for folder in (
        "features",
        "scoring",
        "execution",
        "labels",
        "scanner",
        "data",
        "config",
    ):
        paths += list((root / "src" / "dao_vang" / folder).rglob("*.py"))
    files = {
        p.resolve().relative_to(root.resolve()).as_posix(): hashlib.sha256(
            p.read_bytes()
        ).hexdigest()
        for p in paths
        if p.is_file() and "__pycache__" not in p.parts
    }
    return StrategyManifest(
        frozen_at=utc_now(),
        model_id=model_id,
        label_version=label_version,
        threshold=threshold,
        files=files,
        policy=policy_contract(config),
        source_policy=source_policy or {},
    )


def scanner_signals(db_path: Path, manifest: StrategyManifest, config, now=None):
    now = now or utc_now()
    if now < manifest.frozen_at:
        raise ValueError("manifest_from_future")
    # Use published serving snapshots; source freshness is checked on each row.
    with open_read_only_connection(db_path) as db:
        cursor = db.execute(
            """SELECT * FROM predictions WHERE signal_time>=? AND signal_time<=?
            ORDER BY signal_time, prediction_id""",
            [
                (now - timedelta(seconds=config.signal_ttl_seconds)).replace(
                    tzinfo=None
                ),
                now.replace(tzinfo=None),
            ],
        )
        names = [d[0] for d in cursor.description]
        rows = [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]
        for row in rows:
            at = row["signal_time"].replace(tzinfo=timezone.utc)
            if at < manifest.frozen_at:
                continue
            reasons = []
            if (
                row["model_id"] != manifest.model_id
                or row["label_version"] != manifest.label_version
            ):
                reasons.append("model_or_label_mismatch")
            if (
                row.get("state") != "confirmed_distribution"
                or row.get("tier") != "HIGH_CONFIDENCE"
            ):
                reasons.append("signal_not_confirmed")
            if not (row.get("alert_episode_id") or row.get("event_id")):
                reasons.append("episode_identity_missing")
            if not row["candidate_passed"] or row["quality_status"] != "valid":
                reasons.append("candidate_or_quality_failed")
            probability = row.get("calibrated_probability")
            if probability is None or not manifest.threshold <= probability <= 1:
                reasons.append("below_frozen_threshold")
            age = row.get("max_feature_age_minutes")
            if age is None or not 0 <= age <= 25:
                reasons.append("features_stale")
            if row.get("invalidation_time") is not None:
                reasons.append("signal_invalidated")
            symbol = row["symbol"]
            # Aggregation from complete 5m candles: do not assume an arbitrary
            # last 5m price is an hourly close, or fill missing candles.
            # Binance close_time is interval-end minus 1ms. Bucket by start.
            bars = db.execute(
                """SELECT date_trunc('hour',close_time) + INTERVAL 1 HOUR AS boundary,
                       max(CAST(high AS DOUBLE)),min(CAST(low AS DOUBLE)),
                       arg_max(CAST(close AS DOUBLE),close_time),count(DISTINCT close_time)
                FROM kline WHERE symbol=? AND interval='5m' AND market='USD-M Futures'
                  AND quality_status='valid' AND close_time>=? AND close_time<?
                GROUP BY 1 HAVING count(DISTINCT close_time)=12 ORDER BY 1 DESC LIMIT 15""",
                [
                    symbol,
                    (at - timedelta(hours=17)).replace(tzinfo=None),
                    at.replace(tzinfo=None),
                ],
            ).fetchall()
            values = [
                ClosedBar(
                    closed_at=t.replace(tzinfo=timezone.utc), high=h, low=low, close=c
                )
                for t, h, low, c, _ in reversed(bars)
            ]
            try:
                atr = atr14(values, at)
            except ValueError:
                # Record rejection without pretending a missing ATR is valid.
                reasons.append("atr_unavailable")
                atr = 1.0
            yield TradeSignal(
                event_id=row.get("alert_episode_id")
                or row.get("event_id")
                or row["prediction_id"],
                source_id=row["prediction_id"],
                symbol=symbol,
                manifest_id=manifest.identity,
                observed_at=at,
                expires_at=at + timedelta(seconds=config.signal_ttl_seconds),
                reference_price=values[-1].close if values else 1,
                atr=atr,
                eligible=not reasons,
                reasons=reasons,
            )
