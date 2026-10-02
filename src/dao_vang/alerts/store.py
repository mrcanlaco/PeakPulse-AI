"""Alert history store — persists every signal to DuckDB for audit + review.

Schema (table: alert_history):
    signal_time        TIMESTAMP   — feature_time of the signal candle
    symbol             VARCHAR     — coin symbol
    probability        DOUBLE      — model probability
    risk_level         VARCHAR     — CAO / TRUNG BÌNH / THẤP / RẤT THẤP
    threshold          DOUBLE      — decision threshold from frozen model
    close_price        DOUBLE      — close at signal time (nullable)
    model_id           VARCHAR     — frozen model ID
    invalidation_time  TIMESTAMP   — signal_time + 24h
    telegram_sent      BOOLEAN     — whether Telegram alert was sent
    telegram_sent_at   TIMESTAMP   — when Telegram was sent (nullable)
    hit                BOOLEAN     — label materialized as positive (nullable)
    hit_time           TIMESTAMP   — when hit was determined (nullable)
    dismissed          BOOLEAN     — user dismissed in web UI
    dismissed_at       TIMESTAMP   — when dismissed (nullable)
    created_at         TIMESTAMP   — row insert time

Cooldown logic: before sending Telegram, check if there's a recent
alert for the same symbol within cooldown_minutes. If yes, skip.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import duckdb

from dao_vang.data.storage.duckdb import (
    configure_connection,
    open_read_only_connection,
)
from dao_vang.domain.time import system_now
from dao_vang.logging import get_logger

logger = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS alert_history (
    signal_time        TIMESTAMP NOT NULL,
    symbol             VARCHAR NOT NULL,
    probability        DOUBLE NOT NULL,
    risk_level         VARCHAR NOT NULL,
    threshold          DOUBLE NOT NULL,
    close_price        DOUBLE,
    model_id           VARCHAR NOT NULL,
    invalidation_time  TIMESTAMP NOT NULL,
    telegram_sent      BOOLEAN NOT NULL DEFAULT FALSE,
    telegram_sent_at   TIMESTAMP,
    hit                BOOLEAN,
    hit_time           TIMESTAMP,
    dismissed          BOOLEAN NOT NULL DEFAULT FALSE,
    dismissed_at       TIMESTAMP,
    created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    components_json    VARCHAR,
    evidence_precision DOUBLE,
    evidence_n_judged  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_alert_symbol_time
    ON alert_history(symbol, signal_time DESC);
CREATE INDEX IF NOT EXISTS idx_alert_risk
    ON alert_history(risk_level, signal_time DESC);
CREATE TABLE IF NOT EXISTS alert_lanes (
    lane_id VARCHAR PRIMARY KEY,
    symbol VARCHAR NOT NULL,
    horizon_hours INTEGER NOT NULL,
    state VARCHAR NOT NULL,
    current_episode_id VARCHAR,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS alert_episodes (
    episode_id VARCHAR PRIMARY KEY,
    lane_id VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    close_reason VARCHAR,
    flap_count INTEGER NOT NULL DEFAULT 0,
    last_valid_observation_at TIMESTAMPTZ,
    last_processed_time TIMESTAMPTZ,
    start_time TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
-- Status changes frequently. A secondary ART index rewrites entire episode
-- rows on close and has caused fatal index corruption on the live database.
-- Episode lookups already use the primary key; this index is unnecessary.
DROP INDEX IF EXISTS idx_alert_episodes_status;
"""

# Columns added after the initial release — applied via ALTER TABLE so that
# existing DuckDB files (created before this change) keep working without a
# manual migration step. Safe to run repeatedly (idempotent, errors ignored).
_MIGRATIONS: list[str] = [
    "ALTER TABLE alert_history ADD COLUMN components_json VARCHAR",
    "ALTER TABLE alert_history ADD COLUMN evidence_precision DOUBLE",
    "ALTER TABLE alert_history ADD COLUMN evidence_n_judged INTEGER",
    "ALTER TABLE alert_history ADD COLUMN heuristic_score DOUBLE",
    "ALTER TABLE alert_history ADD COLUMN calibrated_probability DOUBLE",
    "ALTER TABLE alert_history ADD COLUMN data_quality_score DOUBLE",
    "ALTER TABLE alert_history ADD COLUMN horizon_hours INTEGER",
    "ALTER TABLE alert_history ADD COLUMN model_probability DOUBLE",
    "ALTER TABLE alert_history ADD COLUMN cooldown_key VARCHAR",
    # DuckDB versions used in development reject NOT NULL columns in an ALTER
    # statement; nullable is equivalent for legacy rows and keeps migration
    # idempotent.
    "ALTER TABLE alert_history ADD COLUMN shadow_mode BOOLEAN",
    "ALTER TABLE alert_history ADD COLUMN reason_codes_json VARCHAR",
    "ALTER TABLE alert_history ADD COLUMN threshold_policy_version VARCHAR",
    "ALTER TABLE alert_history ADD COLUMN alert_episode_id VARCHAR",
]


@dataclass
class AlertEpisodeResult:
    episode_id: str | None
    role: str       # 'FIRST', 'UPDATE', 'NONE'
    transition: str # 'OPENED', 'CONTINUED', 'CLOSED', 'REARMED', 'NONE'


@dataclass
class AlertRecord:
    """One row in alert_history."""

    signal_time: datetime
    symbol: str
    probability: float
    risk_level: str
    threshold: float
    close_price: float | None
    model_id: str
    invalidation_time: datetime
    model_probability: float | None = None
    heuristic_score: float | None = None
    calibrated_probability: float | None = None
    data_quality_score: float | None = None
    horizon_hours: int | None = None
    telegram_sent: bool = False
    telegram_sent_at: datetime | None = None
    hit: bool | None = None
    hit_time: datetime | None = None
    dismissed: bool = False
    dismissed_at: datetime | None = None
    components_json: str | None = None
    evidence_precision: float | None = None
    evidence_n_judged: int | None = None
    cooldown_key: str | None = None
    shadow_mode: bool = False
    reason_codes_json: str | None = None
    threshold_policy_version: str | None = None
    alert_episode_id: str | None = None


class AlertStore:
    """DuckDB-backed alert history with cooldown + query helpers.

    Args:
        db_path: Path to DuckDB file.
    """

    def __init__(
        self,
        db_path: str,
        read_only: bool = False,
        prefer_snapshot: bool = False,
    ) -> None:
        self._db_path = db_path
        self._read_only = read_only
        self._prefer_snapshot = prefer_snapshot
        try:
            if not self._read_only:
                self._init_schema()
        except duckdb.IOException:
            self._read_only = True
        except duckdb.CatalogException:
            self._read_only = True

    def _conn(self) -> duckdb.DuckDBPyConnection:
        if self._read_only:
            return open_read_only_connection(
                self._db_path,
                prefer_snapshot=self._prefer_snapshot,
            )
        conn = duckdb.connect(self._db_path, read_only=self._read_only)
        configure_connection(conn, self._db_path)
        return conn
    def get_episode_tracking_symbols(self) -> list[str]:
        """Return symbols that have an ACTIVE lane or recently COOLING_DOWN (within 24h)."""
        if self._read_only:
            return []
        try:
            with self._conn() as conn:
                rows = conn.execute("""
                    SELECT DISTINCT symbol 
                    FROM alert_lanes 
                    WHERE state = 'ACTIVE' 
                       OR (state = 'COOLING_DOWN' AND updated_at >= CURRENT_TIMESTAMP - INTERVAL 24 HOUR)
                """).fetchall()
                return [r[0] for r in rows]
        except Exception as e:
            logger.error("get_episode_tracking_symbols_failed", error=str(e))
            return []

    def process_snapshot(
        self,
        symbol: str,
        horizon_hours: int,
        probability: float | None,
        threshold: float,
        is_usable: bool,
        timestamp: datetime,
        flap_limit: int = 3,
        alert_rearm_probability: float = 0.4,
    ) -> AlertEpisodeResult:
        """Process state machine for an alert episode."""
        if self._read_only:
            return AlertEpisodeResult(None, "NONE", "NONE")

        import uuid
        from datetime import timezone

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        lane_id = f"{symbol}:{horizon_hours}"

        try:
            with self._conn() as conn:
                conn.begin()
                try:
                    row = conn.execute(
                        "SELECT state, current_episode_id FROM alert_lanes WHERE lane_id = ?",
                        [lane_id]
                    ).fetchone()

                    if not row:
                        conn.execute(
                            "INSERT INTO alert_lanes (lane_id, symbol, horizon_hours, state, updated_at) VALUES (?, ?, ?, 'ARMED', ?)",
                            [lane_id, symbol, horizon_hours, timestamp]
                        )
                        state, current_episode_id = 'ARMED', None
                    else:
                        state, current_episode_id = row[0], row[1]

                    role = "NONE"
                    transition = "NONE"
                    out_ep_id = current_episode_id
                    
                    # Pre-fetch episode details if ACTIVE
                    if state == 'ACTIVE' and current_episode_id:
                        ep_row = conn.execute(
                            "SELECT flap_count, last_processed_time FROM alert_episodes WHERE episode_id = ?",
                            [current_episode_id]
                        ).fetchone()
                        
                        if ep_row:
                            flap_count, last_processed_time = ep_row[0], ep_row[1]
                            if last_processed_time:
                                if last_processed_time.tzinfo is None:
                                    last_processed_time = last_processed_time.replace(tzinfo=timezone.utc)
                                if timestamp <= last_processed_time:
                                    conn.rollback()
                                    return AlertEpisodeResult(current_episode_id, "NONE", "NONE")
                            
                            if not is_usable or probability is None:
                                pass # UNKNOWN/STALE
                            elif probability >= threshold:
                                conn.execute(
                                    "UPDATE alert_episodes SET flap_count = 0, last_valid_observation_at = ?, last_processed_time = ?, updated_at = ? WHERE episode_id = ?",
                                    [timestamp, timestamp, timestamp, current_episode_id]
                                )
                                role = "UPDATE"
                                transition = "CONTINUED"
                            else:
                                flap_count += 1
                                if flap_count >= flap_limit:
                                    conn.execute(
                                        "UPDATE alert_episodes SET status = 'CLOSED', close_reason = 'HYSTERESIS', flap_count = ?, last_valid_observation_at = ?, last_processed_time = ?, updated_at = ? WHERE episode_id = ?",
                                        [flap_count, timestamp, timestamp, timestamp, current_episode_id]
                                    )
                                    state = 'COOLING_DOWN'
                                    current_episode_id = None
                                    role = "UPDATE"
                                    transition = "CLOSED"
                                else:
                                    conn.execute(
                                        "UPDATE alert_episodes SET flap_count = ?, last_valid_observation_at = ?, last_processed_time = ?, updated_at = ? WHERE episode_id = ?",
                                        [flap_count, timestamp, timestamp, timestamp, current_episode_id]
                                    )
                                    role = "UPDATE"
                                    transition = "NONE"
                                    
                    elif state == 'ARMED':
                        if is_usable and probability is not None and probability >= threshold:
                            ep_id = f"ep-{uuid.uuid4().hex[:12]}"
                            conn.execute(
                                """INSERT INTO alert_episodes 
                                   (episode_id, lane_id, status, flap_count, last_valid_observation_at, last_processed_time, start_time, updated_at) 
                                   VALUES (?, ?, 'OPEN', 0, ?, ?, ?, ?)""",
                                [ep_id, lane_id, timestamp, timestamp, timestamp, timestamp]
                            )
                            state = 'ACTIVE'
                            current_episode_id = ep_id
                            out_ep_id = ep_id
                            role = "FIRST"
                            transition = "OPENED"

                    elif state == 'COOLING_DOWN':
                        if is_usable and probability is not None and probability < alert_rearm_probability:
                            state = 'ARMED'
                            role = "NONE"
                            transition = "REARMED"

                    conn.execute(
                        "UPDATE alert_lanes SET state = ?, current_episode_id = ?, updated_at = ? WHERE lane_id = ?",
                        [state, current_episode_id, timestamp, lane_id]
                    )
                    conn.commit()
                    return AlertEpisodeResult(out_ep_id, role, transition)
                except Exception as inner_e:
                    conn.rollback()
                    raise inner_e
        except Exception as e:
            logger.error("process_snapshot_failed", symbol=symbol, error=str(e))
            return AlertEpisodeResult(None, "NONE", "NONE")
    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(_SCHEMA)
            for stmt in _MIGRATIONS:
                try:
                    conn.execute(stmt)
                except duckdb.Error:
                    # Column already exists — migration already applied.
                    pass

    def is_in_cooldown(self, symbol: str, cooldown_minutes: int) -> bool:
        """Check if symbol was alerted recently within cooldown window."""
        if cooldown_minutes <= 0:
            return False
        cutoff = system_now() - timedelta(minutes=cooldown_minutes)
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM alert_history
                WHERE symbol = ?
                  AND telegram_sent = TRUE
                  AND telegram_sent_at IS NOT NULL
                  AND telegram_sent_at >= ?
                LIMIT 1
                """,
                [symbol, cutoff],
            ).fetchone()
        return row is not None

    def is_in_cooldown_key(self, cooldown_key: str | None, cooldown_minutes: int) -> bool:
        """Event-aware cooldown used by canary policy.

        A missing key deliberately does not match anything; callers can fall
        back to the symbol cooldown for legacy records.
        """

        if not cooldown_key or cooldown_minutes <= 0:
            return False
        cutoff = system_now() - timedelta(minutes=cooldown_minutes)
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM alert_history
                WHERE cooldown_key = ?
                  AND telegram_sent = TRUE
                  AND telegram_sent_at IS NOT NULL
                  AND telegram_sent_at >= ?
                LIMIT 1
                """,
                [cooldown_key, cutoff],
            ).fetchone()
        return row is not None

    def get_daily_alert_count(self, symbol: str | None = None) -> int:
        """Get number of Telegram alerts sent in the last 24h. 
        If symbol provided, counts only for that coin. Otherwise, counts globally."""
        cutoff = system_now() - timedelta(hours=24)
        
        query = (
            "SELECT count(*) FROM alert_history "
            "WHERE telegram_sent = TRUE "
            "AND COALESCE(shadow_mode, FALSE) = FALSE "
            "AND telegram_sent_at >= ?"
        )
        params = [cutoff]
        
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
            
        with self._conn() as conn:
            row = conn.execute(query, params).fetchone()
            
        return int(row[0]) if row else 0

    def save(self, record: AlertRecord) -> None:
        """Insert a new alert record."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO alert_history (
                    signal_time, symbol, probability, risk_level, threshold,
                    close_price, model_id, invalidation_time,
                    telegram_sent, telegram_sent_at, dismissed,
                    components_json, evidence_precision, evidence_n_judged,
                    heuristic_score, calibrated_probability, data_quality_score, horizon_hours, model_probability,
                    cooldown_key, shadow_mode, reason_codes_json, threshold_policy_version, alert_episode_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    record.signal_time,
                    record.symbol,
                    record.probability,
                    record.risk_level,
                    record.threshold,
                    record.close_price,
                    record.model_id,
                    record.invalidation_time,
                    record.telegram_sent,
                    record.telegram_sent_at,
                    record.dismissed,
                    record.components_json,
                    record.evidence_precision,
                    record.evidence_n_judged,
                    record.heuristic_score,
                    record.calibrated_probability,
                    record.data_quality_score,
                    record.horizon_hours,
                    record.model_probability,
                    record.cooldown_key,
                    record.shadow_mode,
                    record.reason_codes_json,
                    record.threshold_policy_version,
                    record.alert_episode_id,

                ],
            )

    def mark_telegram_sent(self, signal_time: datetime, symbol: str) -> None:
        """Mark an alert as successfully sent via Telegram."""
        now = system_now()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE alert_history
                SET telegram_sent = TRUE, telegram_sent_at = ?
                WHERE signal_time = ? AND symbol = ?
                """,
                [now, signal_time, symbol],
            )

    def dismiss(self, signal_time: datetime, symbol: str) -> None:
        """Mark an alert as dismissed by user."""
        now = system_now()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE alert_history
                SET dismissed = TRUE, dismissed_at = ?
                WHERE signal_time = ? AND symbol = ?
                """,
                [now, signal_time, symbol],
            )

    def update_hits(self, labels: dict[tuple[str, datetime], bool]) -> int:
        """Update hit/miss for alerts whose 24h horizon has completed.

        Args:
            labels: Map of (symbol, signal_time) -> is_distribution.

        Returns number of rows updated.
        """
        if not labels:
            return 0
        now = system_now()
        updated: int = 0
        with self._conn() as conn:
            for (sym, sig_time), is_dist in labels.items():
                # Count rows that will be updated (hit IS NULL)
                count_row = conn.execute(
                    """
                    SELECT count(*) FROM alert_history
                    WHERE symbol = ? AND signal_time = ? AND hit IS NULL
                    """,
                    [sym, sig_time],
                ).fetchone()
                n_before: int = int(count_row[0]) if count_row else 0
                if n_before > 0:
                    conn.execute(
                        """
                        UPDATE alert_history
                        SET hit = ?, hit_time = ?
                        WHERE symbol = ? AND signal_time = ? AND hit IS NULL
                        """,
                        [is_dist, now, sym, sig_time],
                    )
                    updated += n_before
        return updated

    def query(
        self,
        symbol: str | None = None,
        risk_levels: list[str] | None = None,
        days: int = 7,
        include_dismissed: bool = True,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Query alert history with filters.

        Returns list of dicts (newest first).
        """
        cutoff = system_now() - timedelta(days=days)
        conditions = ["signal_time >= ?"]
        params: list[Any] = [cutoff]
        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol)
        if risk_levels:
            placeholders = ",".join("?" for _ in risk_levels)
            conditions.append(f"risk_level IN ({placeholders})")
            params.extend(risk_levels)
        if not include_dismissed:
            conditions.append("dismissed = FALSE")
        where = " AND ".join(conditions)
        sql = f"""
            SELECT signal_time, symbol, probability, risk_level, threshold,
                   close_price, model_id, invalidation_time,
                   telegram_sent, telegram_sent_at, hit, hit_time,
                   dismissed, dismissed_at,
                   components_json, evidence_precision, evidence_n_judged,
                   heuristic_score, calibrated_probability, data_quality_score, horizon_hours, model_probability,
                   cooldown_key, shadow_mode, reason_codes_json, threshold_policy_version

            FROM alert_history
            WHERE {where}
            ORDER BY signal_time DESC
            LIMIT ?
        """
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            cols = [
                "signal_time",
                "symbol",
                "probability",
                "risk_level",
                "threshold",
                "close_price",
                "model_id",
                "invalidation_time",
                "telegram_sent",
                "telegram_sent_at",
                "hit",
                "hit_time",
                "dismissed",
                "dismissed_at",
                "components_json",
                "evidence_precision",
                "evidence_n_judged",
                "heuristic_score",
                "calibrated_probability",
                "data_quality_score",
                "horizon_hours",
                "model_probability",
                "cooldown_key",
                "shadow_mode",
                "reason_codes_json",
                "threshold_policy_version",

            ]
        return [dict(zip(cols, r)) for r in rows]

    def pending_outcomes(self, as_of: datetime | None = None) -> list[dict[str, Any]]:
        """Alerts whose 24h horizon has completed but outcome not yet judged.

        Used by the outcome-resolution job (self-learning feedback loop):
        once ``invalidation_time`` has passed, the real Distribution Label
        can be computed from materialized price data and back-filled via
        ``update_hits``.
        """
        cutoff = as_of or system_now()
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT symbol, signal_time
                FROM alert_history
                WHERE hit IS NULL AND invalidation_time <= ?
                """,
                [cutoff],
            ).fetchall()
        return [{"symbol": r[0], "signal_time": r[1]} for r in rows]

    def precision_by_risk_level(self, days: int = 30) -> dict[str, dict[str, Any]]:
        """Empirical precision per risk level over a lookback window.

        This is the core "self-learning feedback" signal: as more alerts get
        resolved via ``update_hits``, the historical precision shown to the
        user (and attached to new alerts as ``evidence_precision``) reflects
        real outcomes rather than a static, unvalidated heuristic score.
        """
        cutoff = system_now() - timedelta(days=days)
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    risk_level,
                    count(*) FILTER (WHERE hit IS NOT NULL) AS n_judged,
                    count(*) FILTER (WHERE hit = TRUE) AS n_hit
                FROM alert_history
                WHERE signal_time >= ?
                GROUP BY risk_level
                """,
                [cutoff],
            ).fetchall()
        result: dict[str, dict[str, Any]] = {}
        for risk_level, n_judged, n_hit in rows:
            n_judged = int(n_judged or 0)
            n_hit = int(n_hit or 0)
            result[risk_level] = {
                "n_judged": n_judged,
                "n_hit": n_hit,
                "precision": (n_hit / n_judged) if n_judged > 0 else None,
            }
        return result

    def lead_time_stats(self, days: int = 30) -> dict[str, Any]:
        """Lead time stats (hours) for alerts that hit, over a lookback window.

        Lead time = hit_time - signal_time. Only alerts where hit = TRUE
        and both timestamps are present are counted.
        """
        cutoff = system_now() - timedelta(days=days)
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    EXTRACT(EPOCH FROM (hit_time - signal_time)) / 3600.0 AS lead_hours
                FROM alert_history
                WHERE signal_time >= ?
                  AND hit = TRUE
                  AND hit_time IS NOT NULL
                """,
                [cutoff],
            ).fetchall()
        lead_hours = [float(r[0]) for r in rows if r[0] is not None]
        if not lead_hours:
            return {
                "mean_hours": None,
                "median_hours": None,
                "min_hours": None,
                "max_hours": None,
                "n_samples": 0,
            }
        lead_sorted = sorted(lead_hours)
        n = len(lead_sorted)
        median = lead_sorted[n // 2] if n % 2 == 1 else (lead_sorted[n // 2 - 1] + lead_sorted[n // 2]) / 2
        return {
            "mean_hours": round(sum(lead_sorted) / n, 1),
            "median_hours": round(median, 1),
            "min_hours": round(lead_sorted[0], 1),
            "max_hours": round(lead_sorted[-1], 1),
            "n_samples": n,
        }

    def stats(self, days: int = 7) -> dict[str, Any]:
        """Summary stats for dashboard."""
        cutoff = system_now() - timedelta(days=days)
        with self._conn() as conn:
            total_row = conn.execute(
                "SELECT count(*) FROM alert_history WHERE signal_time >= ?",
                [cutoff],
            ).fetchone()
            total: int = int(total_row[0]) if total_row else 0
            by_risk = conn.execute(
                """
                SELECT risk_level, count(*) as n
                FROM alert_history WHERE signal_time >= ?
                GROUP BY risk_level
                """,
                [cutoff],
            ).fetchall()
            hit_rate_row = conn.execute(
                """
                SELECT
                    count(*) FILTER (WHERE hit IS NOT NULL) as n_judged,
                    count(*) FILTER (WHERE hit = TRUE) as n_hit
                FROM alert_history
                WHERE signal_time >= ? AND telegram_sent = TRUE
                """,
                [cutoff],
            ).fetchone()
        n_judged: int = int(hit_rate_row[0]) if hit_rate_row and hit_rate_row[0] else 0
        n_hit: int = int(hit_rate_row[1]) if hit_rate_row and hit_rate_row[1] else 0
        return {
            "total": total,
            "by_risk": {r: n for r, n in by_risk},
            "hit_rate": (n_hit / n_judged) if n_judged > 0 else None,
            "n_judged": n_judged,
            "n_hit": n_hit,
            "days": days,
        }
