"""Qualified scanner predictions, not Telegram alerts, feed execution."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dao_vang.data.storage.duckdb import open_read_only_connection
from dao_vang.domain.time import SYSTEM_TIMEZONE

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


def fibo_paper_manifest(root: Path, app_settings) -> StrategyManifest:
    """Build a deterministic StrategyManifest pinned to Fibo Short v4.0.21 & execution policy."""
    rel_files = (
        "src/dao_vang/fibo_short/detector.py",
        "src/dao_vang/fibo_short/scanner_lane.py",
        "src/dao_vang/execution/engine.py",
        "src/dao_vang/execution/paper.py",
    )
    files = {
        rel: hashlib.sha256((root / rel).read_bytes()).hexdigest()
        for rel in rel_files
        if (root / rel).is_file()
    }
    return StrategyManifest(
        frozen_at=datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc),
        model_id="fibo_trend_short_v4_0_21",
        label_version="fibo_short_4factor_v4_0_21",
        threshold=0.5,
        files=files,
        policy=policy_contract(app_settings.execution),
        source_policy={
            "signal_source": "fibo_short",
            "universe_mode": str(app_settings.fibo_trend_short.universe_mode),
            "allowed_policies": sorted(
                str(p) for p in app_settings.fibo_trend_short.telegram_allowed_policies
            ),
        },
    )


def _parse_fibo_candle_open_utc(raw: Any) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.isdigit():
        val = int(text)
        ts_sec = val / 1000.0 if val > 10_000_000_000 else float(val)
        return datetime.fromtimestamp(ts_sec, tz=timezone.utc)
    try:
        return (
            datetime.strptime(text, "%Y-%m-%d %H:%M")
            .replace(tzinfo=SYSTEM_TIMEZONE)
            .astimezone(timezone.utc)
        )
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=SYSTEM_TIMEZONE)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def fibo_short_signals(
    data_dir: Path,
    manifest: StrategyManifest,
    app_settings,
    now: datetime | None = None,
):
    """Yield TradeSignal items from fresh, 4-gate qualified Fibo Short v4.0.21 confirmations."""
    now = now or utc_now()
    if now < manifest.frozen_at:
        raise ValueError("manifest_from_future")
    snapshot_path = Path(data_dir) / "fibo_trend_short" / "snapshot.json"
    if not snapshot_path.is_file():
        return
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("status") not in {"ok", "waiting"}:
        raise ValueError("fibo_snapshot_unavailable")
    updated_raw = payload.get("updated_at")
    if not updated_raw:
        return
    updated_at = datetime.fromisoformat(str(updated_raw).replace("Z", "+00:00"))
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    max_age = max(900.0, float(app_settings.scanner.poll_interval_minutes * 180))
    if (now - updated_at).total_seconds() > max_age:
        raise ValueError("fibo_snapshot_stale")

    fibo_cfg = app_settings.fibo_trend_short
    exec_cfg = app_settings.execution
    allowed_policies = {
        str(p).strip() for p in fibo_cfg.telegram_allowed_policies if str(p).strip()
    }
    min_pump = float(fibo_cfg.telegram_min_prior_pump_pct)
    ttl = min(900, max(60, int(exec_cfg.signal_ttl_seconds)))

    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        if item.get("stage") != "FIRED_CONFIRMED_SHORT":
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        sig_id = str(item.get("id") or "").strip()
        if not symbol or not sig_id:
            continue
        h1 = item.get("h1_confirmation") or {}
        wave = item.get("wave") or {}
        ts = item.get("trade_setup") or {}
        candle_open_utc = _parse_fibo_candle_open_utc(h1.get("candle_time"))
        if candle_open_utc is None:
            continue
        observed_at = candle_open_utc + timedelta(hours=1)
        expires_at = observed_at + timedelta(seconds=ttl)
        if not (observed_at <= now < expires_at):
            continue

        reasons: list[str] = []
        raw_pump = float(wave.get("prior_pump_pct") or 0.0)
        pump_frac = raw_pump / 100.0 if raw_pump > 5.0 else raw_pump
        if pump_frac < min_pump:
            reasons.append("prior_pump_below_50pct")
        raw_drop = float(wave.get("impulse_drop_pct") or 0.0)
        drop_frac = raw_drop / 100.0 if raw_drop > 2.0 else raw_drop
        if drop_frac < 0.06 or float(wave.get("impulse_ker") or 0.0) < 0.50:
            reasons.append("impulse_ker_failed")
        if not (
            bool(h1.get("no_gain_1h"))
            and bool(h1.get("cond2_break_prev_low"))
            and float(h1.get("max_pullback_fibo_ratio") or 1.0) <= 0.786
        ):
            reasons.append("h1_break_failed")

        entry_px = float(ts.get("entry_price") or item.get("current_price") or 0.0)
        sl_m6 = float(ts.get("sl_m6") or ts.get("stop_loss") or 0.0)
        tp1 = float(ts.get("tp1") or 0.0)
        tp2 = float(ts.get("tp2") or 0.0)
        tp3 = float(ts.get("tp3") or 0.0)
        if not (
            sl_m6 > entry_px > tp1 > tp2 > tp3 > 0
            and bool(ts.get("sl_within_cap", True))
        ):
            reasons.append("invalid_sl_tp_ladder")

        matched = {str(p).strip() for p in (item.get("matched_policies") or []) if str(p).strip()}
        if allowed_policies and not matched.intersection(allowed_policies):
            reasons.append("policy_not_in_sniper_allowlist")

        atr_val = float(ts.get("atr_1h") or 0.0)
        if atr_val <= 0 and entry_px > 0:
            atr_val = max(entry_px * 0.015, 1e-8)

        if entry_px <= 0 or atr_val <= 0:
            continue

        yield TradeSignal(
            event_id=sig_id,
            source_id=sig_id,
            symbol=symbol,
            manifest_id=manifest.identity,
            observed_at=observed_at,
            expires_at=expires_at,
            reference_price=entry_px,
            atr=atr_val,
            eligible=not reasons,
            reasons=reasons,
        )
