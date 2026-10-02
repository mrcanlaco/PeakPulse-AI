# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false
"""24/7 scanner daemon — polls Binance, scores with frozen model, alerts via Telegram.

Architecture (per ADR 0001):
    ┌───────────────────────────────────────┐
    │  Scanner loop (every poll_interval)   │
    │  1. build_scan_list (watchlist+gainers)│
    │  2. for each symbol:                  │
    │     a. collect latest data (incremental)│
    │     b. normalize → timeline → features│
    │     c. score_frozen (frozen model)    │
    │     d. filter by alert_levels         │
    │     e. cooldown check (AlertStore)    │
    │     f. send Telegram if not cooldown  │
    │     g. save to alert_history          │
    │  3. sleep poll_interval_minutes       │
    └───────────────────────────────────────┘

Constraints:
- Frozen model only — no retraining in loop.
- Point-in-time correct — features use available_time <= feature_time.
- Cooldown per symbol to avoid spam.
- No silent fallback — errors logged, not swallowed.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import signal
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from numbers import Real
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[reportMissingTypeStubs]

from dao_vang.alerts.store import AlertRecord, AlertStore
from dao_vang.alerts.telegram import TelegramNotifier, _coin_url
from dao_vang.alpha_lab.meta_labeling import MetaLabelingModel
from dao_vang.alpha_lab.regime_classifier import (
    RegimeState,
    get_current_regime,
)
from dao_vang.config.settings import AppSettings
from dao_vang.data.collectors.binance_client import BinanceClient
from dao_vang.data.collectors.coingecko import cross_reference
from dao_vang.data.collectors.funding import FundingCollector
from dao_vang.data.collectors.klines import KlinesCollector
from dao_vang.data.collectors.liquidations import LiquidationCollector
from dao_vang.data.collectors.open_interest import OpenInterestCollector
from dao_vang.data.collectors.ratios import GlobalRatioCollector, TopRatioCollector
from dao_vang.data.collectors.taker import TakerRatioCollector
from dao_vang.data.collectors.top_position_ratio import TopPositionRatioCollector
from dao_vang.data.pipeline import (
    build_raw_timeline,
    get_incremental_start,
    process_raw_to_parquet,
)
from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.domain.time import (
    SYSTEM_TIMEZONE_NAME,
    system_iso,
    system_now,
)
from dao_vang.execution.policy_router import ExecutionPolicyRouter, PolicyContext
from dao_vang.experiments.forward_test import load_frozen_model
from dao_vang.experiments.self_learning import run_self_learning
from dao_vang.features.builder import build_features
from dao_vang.logging import get_logger
from dao_vang.scanner.anomalies import AnomalyReport, detect_market_anomalies
from dao_vang.scanner.candidate_filter_comparison import (
    CandidateFilterCycleAudit,
    assemble_candidate_filter_audit,
)
from dao_vang.scanner.candidate_filter_store import CandidateFilterStore
from dao_vang.scanner.candidate_filter_v2 import (
    CandidateV2Decision,
    CandidateV2Policy,
    scan_candidate_filter_v2,
)
from dao_vang.scanner.instance_lock import ScannerInstanceLock
from dao_vang.scanner.operations import (
    CanaryDecision,
    KillSwitch,
    RollbackManager,
    _atomic_json_write,
    evaluate_canary_policy,
    verify_bundle_config,
)
from dao_vang.scanner.outcomes import resolve_pending_outcomes
from dao_vang.scanner.pump_filter import PumpCandidate, scan_pumps
from dao_vang.scanner.scan_results_store import (
    PredictionRecord,
    ScanResultRecord,
    ScanResultStore,
)
from dao_vang.scanner.telegram_selection import (
    TelegramSelection,
    select_top_alerts,
)
from dao_vang.scanner.watchlist import (
    build_comparison_universe,
    build_scan_list,
    normalize_scan_modes,
)
from dao_vang.scoring import classify_btc
from dao_vang.scoring.frozen_inference import (
    SnapshotScore,
    assess_snapshot_quality,
    score_snapshot,
)

logger = get_logger(__name__)

_COLLECTORS = [
    ("klines", "Nến 5m", KlinesCollector),
    ("funding", "Funding Rate", FundingCollector),
    ("open_interest", "Open Interest", OpenInterestCollector),
    ("taker_ratio", "Taker Volume", TakerRatioCollector),
    ("global_ratio", "Global L/S", GlobalRatioCollector),
    ("top_ratio", "Top L/S", TopRatioCollector),
    ("top_position_ratio", "Top Position L/S", TopPositionRatioCollector),
    ("liquidations", "Liquidations", LiquidationCollector),
]


def _last_closed_5m_end(now: datetime) -> datetime:
    """Return the latest safe 5-minute candle close timestamp.

    Binance returns the currently forming candle when its open time is before
    ``endTime``. Serving that row makes the feature timestamp appear in the
    future until the candle closes, which correctly fails the alert quality
    gate but leaves the live scanner with no usable report. Bound collection
    and scoring to the previous closed candle instead.
    """

    clock = (
        now.astimezone(timezone.utc)
        if now.tzinfo
        else now.replace(tzinfo=timezone.utc)
    )
    bucket_start = clock.replace(
        minute=(clock.minute // 5) * 5,
        second=0,
        microsecond=0,
    )
    return bucket_start - timedelta(milliseconds=1)


def _horizon_hours(frozen_info: Any) -> int:
    """Read the frozen label horizon without assuming one metadata spelling."""

    spec = getattr(frozen_info, "label_spec", {})
    if not isinstance(spec, dict):
        return 24
    value = spec.get("horizon_hours")
    if value is not None:
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            pass
    minutes = spec.get("horizon_minutes")
    try:
        return max(1, int(math.ceil(float(minutes) / 60.0))) if minutes is not None else 24
    except (TypeError, ValueError):
        return 24


def _risk_level_for_tier(risk_tier: str) -> str:
    """Map the new policy tier to the legacy alert-history vocabulary."""

    return {
        "HIGH_CONFIDENCE": "CAO",
        "WATCH": "TRUNG BÌNH",
        "WAIT": "THẤP",
    }.get(risk_tier, "THẤP")


def _mode_allows_tier(mode: str, tier: str, alert_levels: list[str]) -> bool:
    """Return whether an operating mode permits a Telegram action alert."""

    if mode in {"research", "shadow"}:
        return False
    if tier != "HIGH_CONFIDENCE":
        return False
    configured = {str(level).upper() for level in alert_levels}
    aliases = {
        "HIGH_CONFIDENCE": {"HIGH_CONFIDENCE", "CAO"},
    }
    return bool(configured.intersection(aliases.get(tier, set())))


def _collection_symbols(score_symbols: list[str]) -> list[str]:
    """Deduplicate symbols while preserving order and ensuring BTCUSDT is present."""
    return list(dict.fromkeys(score_symbols + ["BTCUSDT"]))


class ScannerDaemon:
    """24/7 scanner loop using a frozen model + Telegram alerts.

    Args:
        settings: AppSettings with scanner + telegram config.
    """

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._scanner_cfg = settings.scanner
        self._meta_model: MetaLabelingModel | None = None
        self._notifier = TelegramNotifier(
            settings.telegram,
            web_base_url=settings.web.public_url,
        )
        self._running = True
        self._cycle_count = 0
        self._run_id = uuid.uuid4().hex
        self._last_cycle_started_at: str | None = None
        self._last_cycle_completed_at: str | None = None
        self._last_cycle_status = "not_started"
        self._last_cycle_error: str | None = None
        self._last_cycle_n_symbols = 0
        self._last_cycle_n_alerts = 0
        self._web_base_url = str(getattr(self._settings.web, "public_url", "") or "")
        _data_dir = Path(self._settings.paths.data_dir)
        self._heartbeat_path = _data_dir / "scanner_heartbeat.json"
        # The scanner keeps DuckDB's writer connection for its whole process
        # lifetime. On Windows that prevents the web process from opening the
        # live database, so publish the serving rows through an atomic JSON
        # snapshot after each completed scoring pass.
        self._candidate_snapshot_path = _data_dir / "candidate_snapshot.json"
        # Publish the table-health snapshot from the scanner's own DuckDB
        # connection. On Windows the web process cannot always copy/open the
        # live database while this writer is active, so the API needs a
        # current lock-free serving artifact for freshness metrics too.
        self._system_stats_path = _data_dir / "system_data_stats.json"
        comparison_cfg = self._settings.candidate_comparison
        self._candidate_filter_comparison_path = (
            Path(comparison_cfg.snapshot_path)
            if comparison_cfg.snapshot_path is not None
            else _data_dir / "candidate_filter_comparison.json"
        )
        self._candidate_filter_state_path = (
            Path(comparison_cfg.state_path)
            if comparison_cfg.state_path is not None
            else _data_dir / "candidate_filter_v2_state.json"
        )
        self._candidate_filter_store = CandidateFilterStore()
        self._last_candidate_comparison: dict[str, Any] = {
            "enabled": bool(comparison_cfg.enabled),
            "status": (
                "waiting_for_first_cycle" if comparison_cfg.enabled else "disabled"
            ),
        }
        self._trigger_path = _data_dir / "scanner_trigger.flag"
        self._runtime_state_path = _data_dir / "scanner_runtime_state.json"
        self._instance_lock = ScannerInstanceLock(_data_dir / "scanner.lock")
        self._kill_switch = KillSwitch(self._scanner_cfg.kill_switch_path)
        self._rollback = RollbackManager(self._scanner_cfg.rollback_state_path)
        configured_mode = str(self._scanner_cfg.operating_mode)
        rollback_mode = str(self._rollback.state().get("mode", "research")).lower()
        # A persisted rollback-to-shadow pointer is an operational override;
        # an operator must explicitly promote a new bundle before action
        # alerts can resume.
        self._operating_mode = (
            "shadow"
            if rollback_mode == "shadow"
            and configured_mode in {"canary", "production", "production_alerting"}
            else configured_mode
        )
        if self._operating_mode != configured_mode:
            logger.warning(
                "scanner_rollback_override",
                configured_mode=configured_mode,
                effective_mode=self._operating_mode,
            )

        # Validate frozen model
        model_id = self._scanner_cfg.frozen_model_id
        if not model_id:
            raise ValueError(
                "scanner.frozen_model_id not set. "
                "Run `dao-vang experiment freeze` first, then set in config."
            )
        self._frozen_info = load_frozen_model(
            model_id, Path(self._scanner_cfg.artifact_dir)
        )
        self._bundle_valid, self._bundle_reasons = verify_bundle_config(
            self._frozen_info,
            threshold_policy_version=self._scanner_cfg.threshold_policy_version,
            expected_model_id=model_id,
        )
        logger.info(
            "scanner_init",
            model_id=model_id,
            threshold=self._frozen_info.threshold,
            train_cutoff=self._frozen_info.train_cutoff,
        )

        # Acquire the deployment lock before opening any DuckDB-backed store.
        # A stale lock file is harmless: the OS lock is released automatically
        # when a previous process dies.
        self._instance_lock.acquire()
        try:
            self._alert_store = AlertStore(str(self._scanner_cfg.db_path))
            self._scan_result_store = ScanResultStore(str(self._scanner_cfg.db_path))
        except Exception:
            self._instance_lock.release()
            raise

    def stop(self, *_: Any) -> None:
        """Graceful shutdown signal handler."""
        logger.info("scanner_stop_requested")
        self._running = False

    def _write_heartbeat(self, status: str = "running") -> None:
        """Write heartbeat file for web UI to detect scanner status."""
        try:
            self._heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_json_write(
                self._heartbeat_path,
                {
                    "status": status,
                    "cycle": self._cycle_count,
                    "timestamp": system_now().isoformat(),
                    "poll_minutes": self._scanner_cfg.poll_interval_minutes,
                    "model_id": self._scanner_cfg.frozen_model_id,
                    "scan_mode": self._scanner_cfg.scan_mode,
                    "max_coins": self._scanner_cfg.max_coins,
                    "operating_mode": self._operating_mode,
                    "shadow_telegram_enabled": self._scanner_cfg.shadow_telegram_enabled,
                    "kill_switch_active": self._kill_switch.active,
                    "bundle_valid": self._bundle_valid,
                    "bundle_reasons": list(self._bundle_reasons),
                    "pid": os.getpid(),
                    "run_id": self._run_id,
                    "last_cycle_started_at": self._last_cycle_started_at,
                    "last_cycle_completed_at": self._last_cycle_completed_at,
                    "last_cycle_status": self._last_cycle_status,
                    "last_cycle_error": self._last_cycle_error,
                    "last_cycle_n_symbols": self._last_cycle_n_symbols,
                    "last_cycle_n_alerts": self._last_cycle_n_alerts,
                    "candidate_filter_comparison": self._last_candidate_comparison,
                },
            )
        except Exception as e:
            logger.debug(f"Heartbeat failed: {e}")  # heartbeat is best-effort, don't crash scanner

    def run(self) -> None:
        """Main loop — runs until stopped (Ctrl+C or signal)."""
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        logger.info(
            "scanner_start",
            poll_minutes=self._scanner_cfg.poll_interval_minutes,
            max_coins=self._scanner_cfg.max_coins,
            alert_levels=self._scanner_cfg.alert_levels,
            scan_mode=self._scanner_cfg.scan_mode,
            min_change_pct=self._scanner_cfg.min_price_change_pct,
            operating_mode=self._operating_mode,
            shadow_telegram_enabled=self._scanner_cfg.shadow_telegram_enabled,
        )
        self._write_heartbeat("running")

        try:
            while self._running:
                self._cycle_count += 1
                cycle_start = time.perf_counter()
                self._last_cycle_started_at = system_now().isoformat()
                self._last_cycle_status = "running"
                self._last_cycle_error = None
                self._write_heartbeat("running")
                try:
                    self._run_cycle()
                except Exception as exc:
                    self._last_cycle_status = "failed"
                    self._last_cycle_error = str(exc)
                    self._write_heartbeat("degraded")
                    logger.error(
                        "scanner_cycle_error",
                        cycle=self._cycle_count,
                        error=str(exc),
                    )
                    # Let the supervisor restart a clean process instead of
                    # advertising a broken daemon as healthy.
                    raise

                self._last_cycle_status = "ok"
                self._last_cycle_completed_at = system_now().isoformat()

                elapsed = time.perf_counter() - cycle_start
                poll_seconds = self._scanner_cfg.poll_interval_minutes * 60
                # poll_interval is the target start-to-start cadence. Do not
                # add a full extra interval after a long cycle; that made the
                # observed cadence drift to 11-15 minutes.
                sleep_seconds = max(0.0, poll_seconds - elapsed)
                logger.info(
                    "scanner_cycle_done",
                    cycle=self._cycle_count,
                    elapsed_s=round(elapsed, 1),
                    sleep_s=round(sleep_seconds, 1),
                    poll_s=poll_seconds,
                )
                self._write_heartbeat("running")

            # Sleep in small increments so we can respond to stop signal AND
            # an on-demand scan trigger (e.g. "Quét ngay" button in the web UI
            # writes data/scanner_trigger.flag instead of faking a response).
                deadline = time.monotonic() + sleep_seconds
                while self._running and time.monotonic() < deadline:
                    if self._trigger_path.exists():
                        logger.info("scanner_manual_trigger_detected")
                        break
                    time.sleep(min(5, max(0.0, deadline - time.monotonic())))

            self._write_heartbeat("stopped")
            logger.info("scanner_stopped", cycles=self._cycle_count)
        finally:
            self._instance_lock.release()

    def _consume_trigger(self) -> None:
        """Remove the manual-trigger flag file (idempotent, best-effort)."""
        try:
            self._trigger_path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Exception in scanner daemon loop: {e}")

    def _apply_runtime_overrides(self) -> None:
        """Apply scan_mode overrides written by the web UI at runtime.

        The API server cannot mutate the running daemon's in-memory config
        directly (separate process), so it writes desired overrides to
        ``scanner_runtime_state.json`` and this reads them each cycle.
        """
        if not self._runtime_state_path.exists():
            return
        try:
            state = json.loads(self._runtime_state_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("scanner_runtime_state_read_failed", error=str(exc))
            return
        new_mode = ",".join(
            normalize_scan_modes(state.get("scan_modes", state.get("scan_mode")))
        )
        if new_mode and new_mode != self._scanner_cfg.scan_mode:
            logger.info(
                "scanner_scan_mode_override",
                old_mode=self._scanner_cfg.scan_mode,
                new_mode=new_mode,
            )
            self._scanner_cfg.scan_mode = new_mode

    def _select_daily_telegram_alerts(
        self, alerts: list[dict[str, Any]]
    ) -> TelegramSelection:
        """Rank qualified candidates inside the rolling Telegram budget."""

        daily_limit = int(getattr(self._scanner_cfg, "global_daily_alert_limit", 10))
        target_min = int(getattr(self._scanner_cfg, "telegram_daily_target_min", 5))
        max_per_cycle = int(getattr(self._scanner_cfg, "telegram_max_per_cycle", 2))
        coin_daily_limit = int(getattr(self._scanner_cfg, "coin_daily_alert_limit", 1))

        try:
            sent_24h = self._scan_result_store.get_prediction_telegram_count(hours=24)
            coin_sent_counts = (
                self._scan_result_store.get_prediction_telegram_counts_by_symbol(hours=24)
            )
        except Exception as exc:
            # A quota read failure must fail closed.  Sending without knowing
            # the current budget can exceed the operator's daily limit.
            logger.error("scanner_daily_selection_unavailable", error=str(exc))
            sent_24h = max(1, daily_limit)
            coin_sent_counts = {}

        selection = select_top_alerts(
            alerts,
            sent_24h=sent_24h,
            daily_limit=daily_limit,
            max_per_cycle=max_per_cycle,
            target_min=target_min,
            coin_sent_counts=coin_sent_counts,
            coin_daily_limit=coin_daily_limit,
        )
        logger.info(
            "scanner_daily_selection",
            candidate_count=selection.candidate_count,
            eligible_count=selection.eligible_count,
            selected_count=len(selection.selected),
            sent_24h=selection.sent_24h,
            projected_24h=selection.projected_24h,
            daily_limit=selection.daily_limit,
            target_min=selection.target_min,
            max_per_cycle=selection.max_per_cycle,
            symbols=[item["symbol"] for item in selection.selected],
        )
        if selection.target_unmet:
            logger.info(
                "scanner_daily_target_unmet",
                projected_24h=selection.projected_24h,
                target_min=selection.target_min,
                eligible_count=selection.eligible_count,
            )
        return selection

    def _run_cycle(self) -> None:
        """One scan cycle: build list → pump filter → collect → score → alert."""
        self._consume_trigger()
        self._apply_runtime_overrides()

        # 1. Build scan list (watchlist + auto market scan by mode)
        symbols = build_scan_list(self._scanner_cfg)
        if not symbols and not self._settings.research_v3_enabled:
            logger.warning("scanner_no_symbols", scan_mode=self._scanner_cfg.scan_mode)
            return

        logger.info(
            "scanner_cycle_start",
            cycle=self._cycle_count,
            n_symbols=len(symbols),
            scan_mode=self._scanner_cfg.scan_mode,
            max_coins=self._scanner_cfg.max_coins,
            min_change_pct=self._scanner_cfg.min_price_change_pct,
        )

        # Capture the broad comparison universe from the same cached 24h
        # ticker snapshot as the production list. Network evaluation remains
        # deferred until v1 has already scored, published, and sent Telegram.
        comparison_universe: list[dict[str, Any]] = []
        comparison_now = datetime.now(timezone.utc)
        if self._settings.candidate_comparison.enabled:
            try:
                comparison_universe = build_comparison_universe(
                    self._scanner_cfg,
                    pinned_symbols=symbols,
                    limit=self._settings.candidate_comparison.universe_size,
                )
            except Exception as exc:
                logger.warning(
                    "candidate_filter_universe_failed",
                    error=str(exc),
                )

        # 1b. Candidate Filter — V2 Multi-stage Quant Filter or V1 Pump Filter
        pump_candidates = scan_pumps(self._settings.pump_filter, symbols)
        pump_map: dict[str, PumpCandidate] = {c.symbol: c for c in pump_candidates}

        cfg_comparison = self._settings.candidate_comparison
        v2_decisions: list[CandidateV2Decision] = []
        v2_observations: list[Any] = []
        v2_next_state: dict[str, Any] = {}
        is_v2_champion = (
            cfg_comparison.enabled
            and cfg_comparison.champion_version == "candidate_filter_v2"
        )

        if is_v2_champion and comparison_universe:
            try:
                univ_symbols = [
                    str(t.get("symbol", "")).upper()
                    for t in comparison_universe
                    if t.get("symbol")
                ]
                quote_vols = {
                    str(t.get("symbol", "")).upper(): float(t.get("quoteVolume", 0) or 0)
                    for t in comparison_universe
                    if t.get("symbol")
                }
                v2_policy = CandidateV2Policy(
                    version="candidate_filter_v2",
                    max_candidates=cfg_comparison.max_candidates,
                )
                prev_v2_state = {
                    sym: val
                    for sym, val in self._load_candidate_filter_state().items()
                    if isinstance(val, dict)
                    and val.get("filter_version") == "candidate_filter_v2"
                }
                v2_decisions, v2_observations, v2_next_state = scan_candidate_filter_v2(
                    univ_symbols,
                    comparison_now,
                    prev_v2_state,
                    v2_policy,
                    quote_volumes_24h=quote_vols,
                    base_url=str(self._settings.binance.base_url),
                    timeout_seconds=min(10.0, float(self._settings.collection.timeout_seconds)),
                    max_workers=cfg_comparison.max_workers,
                )
                v2_selected = [d for d in v2_decisions if d.selected]
                if v2_selected:
                    score_symbols = [d.symbol for d in v2_selected]
                    for d in v2_selected:
                        if d.symbol not in pump_map:
                            p_pct = max(
                                0.0,
                                ((d.peak_price - d.reference_price) / d.reference_price)
                                if (d.peak_price and d.reference_price and d.reference_price > 0)
                                else float(d.pump_score or 0.0),
                            )
                            p_days = max(1, int((d.peak_age_hours or 24.0) / 24.0))
                            cur_vs_peak = (1.0 - d.drawdown_from_peak) if d.drawdown_from_peak is not None else 1.0
                            pump_map[d.symbol] = PumpCandidate(
                                symbol=d.symbol,
                                pump_pct=p_pct,
                                pump_days=p_days,
                                current_vs_peak=cur_vs_peak,
                                peak_price=d.peak_price or (d.reference_price or 0.0),
                                current_price=d.reference_price or 0.0,
                                quote_volume=float(d.volume_24h_usd or 0.0),
                            )
                else:
                    score_symbols = list(pump_map.keys()) if pump_map else symbols
            except Exception as exc:
                logger.warning("v2_champion_scan_failed_fallback_v1", error=str(exc))
                score_symbols = list(pump_map.keys()) if pump_map else symbols
        else:
            score_symbols = list(pump_map.keys()) if pump_map else symbols
        # Append active/cooling lanes to ensure they are scored for anti-flap and rearm
        try:
            active_symbols = self._alert_store.get_episode_tracking_symbols()
            if active_symbols:
                score_symbols = list(dict.fromkeys(score_symbols + active_symbols))
        except Exception as e:
            logger.error("get_episode_tracking_symbols_failed", error=str(e))


        self._last_cycle_n_symbols = len(score_symbols)
        logger.info(
            "candidate_filter_result",
            champion_version=cfg_comparison.champion_version if cfg_comparison.enabled else "pump_filter_v1",
            n_scanned=len(symbols),
            n_v2_selected=len([d for d in v2_decisions if d.selected]),
            n_pump_candidates=len(pump_candidates),
            n_to_score=len(score_symbols),
            score_symbols=score_symbols[:10],
        )

        # 2. Collect + normalize + timeline + features (shared across symbols)
        now = datetime.now(timezone.utc)
        start_dt = now - timedelta(days=self._scanner_cfg.history_days)
        closed_candle_end = _last_closed_5m_end(now)
        symbols_to_collect = _collection_symbols(score_symbols)
        v3_discovery: dict[str, Any] | None = None
        if self._settings.research_v3_enabled:
            from dao_vang.scanner.research_v3 import atomic_snapshot
            from dao_vang.scanner.research_v3_discovery import (
                discover,
                fetch_tickers,
                retained_entries,
            )

            storage = self._settings.paths.data_dir / "research_v3"
            try:
                v3_discovery = discover(
                    fetch_tickers(str(self._settings.binance.base_url)),
                    storage=storage, now=datetime.now(timezone.utc),
                )
                from dao_vang.scanner.research_v3_backfill import Jobs, attach

                v3_discovery = attach(v3_discovery, Jobs(storage))
                symbols_to_collect = _collection_symbols(symbols_to_collect + v3_discovery["collection_symbols"])
                atomic_snapshot(storage / "discovery.json", v3_discovery)
            except Exception as exc:
                logger.warning("research_v3_discovery_failed", error=str(exc))
                v3_discovery = {"status": "error", "updated_at": datetime.now(timezone.utc),
                                "error_type": type(exc).__name__, "items": [], "collection_symbols": []}
                atomic_snapshot(storage / "discovery.json", v3_discovery)
                # Existing simulated positions still require their future paths.
                try:
                    symbols_to_collect = _collection_symbols(symbols_to_collect + retained_entries(storage, now))
                except Exception as retention_exc:
                    logger.warning("research_v3_retention_failed", error=str(retention_exc))
        self._collect_all(symbols_to_collect, start_dt, closed_candle_end)
        phase_start = time.perf_counter()
        pipeline_changed = self._normalize_and_timeline()
        logger.info("scanner_phase_done", phase="normalize_timeline", elapsed_s=round(time.perf_counter()-phase_start, 3))
        self._write_heartbeat("running")

        # 2b. Resolve legacy alert hits when possible. Full prediction-outcome
        # materialization is intentionally not part of the hot scan loop: it
        # creates up to 1M+ intermediate label rows and can exhaust DuckDB's
        # temp pipeline on Windows before the candidate list is published.
        # Use the dedicated `scanner materialize-outcomes` maintenance command
        # with the scanner stopped for that job.
        db = DuckDBQueryLayer(str(self._scanner_cfg.db_path))
        try:
            n_resolved = resolve_pending_outcomes(self._alert_store, db)
            if n_resolved:
                logger.info("scanner_outcomes_resolved", n_resolved=n_resolved)
        except Exception as exc:
            logger.warning("scanner_outcome_resolution_failed", error=str(exc))

        # Throttled materialization: only run every 12 cycles (~1 hour) to avoid DuckDB OOM on Windows temp pipelines
        if getattr(self, "_cycle_count", 0) % 12 == 1:
            phase_start = time.perf_counter()
            try:
                from dao_vang.scanner.outcomes import materialize_prediction_outcomes
                from dao_vang.scanner.scan_results_store import ScanResultStore
                scan_store = ScanResultStore(str(self._scanner_cfg.db_path))
                n_mat = materialize_prediction_outcomes(scan_store, db)
                if n_mat:
                    logger.info("scanner_predictions_materialized", n_materialized=n_mat)
            except Exception as exc:
                logger.warning("scanner_predictions_materialization_failed", error=str(exc))
            logger.info("scanner_phase_done", phase="prediction_outcomes", elapsed_s=round(time.perf_counter()-phase_start, 3))

        # 3. Build features only when collection produced new normalized data.
        # Rebuilding all rolling windows on every heartbeat was the main RAM
        # and disk-I/O amplifier when a cycle returned no new candles.
        if pipeline_changed:
            phase_start = time.perf_counter()
            build_features(db, "raw_timeline", "feature_results")
            logger.info("scanner_phase_done", phase="features", elapsed_s=round(time.perf_counter()-phase_start, 3))
        self._write_heartbeat("running")

        # 3b. Compute BTC context for this cycle
        btc_context = self._compute_btc_context(db)

        # 3c. Compute regime state (Regime Gate)
        regime_state: RegimeState | None = None
        regime_gate_enabled = getattr(self._scanner_cfg, "regime_gate_enabled", False)
        if regime_gate_enabled:
            try:
                btc_klines = db.conn.execute("""
                    SELECT close_time AS feature_time, open, high, low, close
                    FROM kline
                    WHERE symbol = 'BTCUSDT'
                    ORDER BY close_time DESC
                    LIMIT 300
                """).fetchdf()
                if len(btc_klines) >= 100:
                    btc_klines = btc_klines.sort_values("feature_time")
                    btc_ohlcv = btc_klines.set_index("feature_time")
                    regime_state = get_current_regime(btc_ohlcv)
                    logger.info(
                        "regime_gate_computed",
                        regime=regime_state.regime.value,
                        allow_short=regime_state.allow_short,
                        risk_multiplier=regime_state.risk_multiplier,
                    )
                else:
                    logger.warning("regime_gate_insufficient_data", bars=len(btc_klines))
            except Exception as exc:
                logger.warning("regime_gate_error", error=str(exc))

        # 4. Score with composite scorer + alert (with optional cycle digest)
        n_alerts_sent = 0
        digest_mode = getattr(self._scanner_cfg, "telegram_digest_mode", True)
        qualifying_alerts: list[dict[str, Any]] = []

        for symbol in score_symbols:
            try:
                pump_cand = pump_map.get(symbol)
                res = self._score_and_alert_composite(
                    symbol, db, btc_context, pump_cand,
                    collect_for_digest=digest_mode,
                    regime_state=regime_state,
                )
                if isinstance(res, dict):
                    qualifying_alerts.append(res)
                elif isinstance(res, int):
                    n_alerts_sent += res
            except Exception as exc:
                logger.error("scanner_symbol_error", symbol=symbol, error=str(exc))

        if digest_mode and qualifying_alerts:
            # The per-cycle digest is the only delivery point in digest mode.
            # Rank the complete candidate set here so later cycles cannot be
            # crowded out by whichever symbol happened to be scored first.
            selection = self._select_daily_telegram_alerts(qualifying_alerts)
            selected_alerts = selection.selected
        else:
            selected_alerts = []

        if digest_mode and selected_alerts:
            regime = btc_context.get("regime", "NEUTRAL") if isinstance(btc_context, dict) else "NEUTRAL"
            digest_sent = self._notifier.send_cycle_digest(
                alerts=selected_alerts,
                btc_regime=regime,
                scan_time=datetime.now(timezone.utc).isoformat(),
                operating_mode=self._operating_mode,
            )
            if digest_sent:
                n_alerts_sent = len(selected_alerts)
                for item in selected_alerts:
                    sig_time = item.get("sig_time")
                    sym = item.get("symbol")
                    pred_id = item.get("prediction_id")
                    if sig_time and sym:
                        self._alert_store.mark_telegram_sent(sig_time, sym)
                    if pred_id:
                        self._scan_result_store.mark_prediction_telegram_sent(pred_id)
                logger.info(
                    "scanner_cycle_digest_sent",
                    cycle=self._cycle_count,
                    n_alerts=len(selected_alerts),
                    symbols=[a["symbol"] for a in selected_alerts],
                )

        logger.info(
            "scanner_cycle_summary",
            cycle=self._cycle_count,
            n_symbols=len(score_symbols),
            n_alerts_sent=n_alerts_sent,
        )
        self._last_cycle_n_alerts = n_alerts_sent
        # scan_results is inserted through the cycle's primary DuckDB
        # connection. Commit before publishing the JSON snapshot so the web
        # process and a future scanner restart see the same completed cycle.
        db.conn.commit()
        self._publish_candidate_snapshot(db)

        if self._settings.research_v3_enabled:
            phase_start = time.perf_counter()
            try:
                from dao_vang.scanner.research_v3 import run_cycle

                run_cycle(db.conn, data_dir=self._settings.paths.data_dir,
                          model_path=self._settings.research_v3_model_path,
                          discovery=v3_discovery, settings=self._settings)
            except Exception as exc:
                logger.warning("research_v3_cycle_failed", error=str(exc))
            logger.info("scanner_phase_done", phase="research_v3", elapsed_s=round(time.perf_counter()-phase_start, 3))
            self._write_heartbeat("running")

        phase_start = time.perf_counter()
        self._publish_system_stats(db)
        logger.info("scanner_phase_done", phase="system_stats", elapsed_s=round(time.perf_counter()-phase_start, 3))
        self._write_heartbeat("running")

        # The challenger is observational only. Running it after the champion
        # serving artifacts are published. This ordering isolates the champion
        # report path from challenger errors and slow Binance responses.
        if self._settings.candidate_comparison.enabled and comparison_universe:
            try:
                precomputed = (
                    (v2_decisions, v2_observations, v2_next_state)
                    if v2_decisions
                    else None
                )
                self._run_candidate_filter_comparison(
                    db=db,
                    universe_tickers=comparison_universe,
                    production_symbols=symbols,
                    champion_score_symbols=score_symbols,
                    pump_candidates=pump_candidates,
                    comparison_now=comparison_now,
                    champion_fallback_all=not bool(pump_candidates),
                    precomputed_v2=precomputed,
                )
            except Exception as exc:
                self._last_candidate_comparison = {
                    "enabled": True,
                    "status": "degraded",
                    "error": str(exc),
                }
                logger.warning(
                    "candidate_filter_comparison_failed",
                    cycle=self._cycle_count,
                    error=str(exc),
                )

        # Retraining runs as a guarded batch job only after serving/scoring is
        # complete.  Closing this connection avoids competing with the job for
        # a DuckDB writer lock.  The active champion is never changed here.
        try:
            db.close()
        except Exception as exc:
            logger.debug(
                "scanner_db_close_before_self_learning_failed", error=str(exc)
            )
        self._run_self_learning_if_due()

    def _load_candidate_filter_state(self) -> dict[str, Any]:
        if not self._candidate_filter_state_path.exists():
            return {}
        try:
            payload = json.loads(
                self._candidate_filter_state_path.read_text(encoding="utf-8")
            )
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "candidate_filter_state_read_failed",
                path=str(self._candidate_filter_state_path),
                error=str(exc),
            )
            return {}

    def _run_candidate_filter_comparison(
        self,
        *,
        db: DuckDBQueryLayer,
        universe_tickers: list[dict[str, Any]],
        production_symbols: list[str],
        champion_score_symbols: list[str],
        pump_candidates: list[PumpCandidate],
        comparison_now: datetime,
        champion_fallback_all: bool,
        precomputed_v2: tuple[list[CandidateV2Decision], list[Any], dict[str, Any]] | None = None,
    ) -> None:
        """Evaluate and persist candidate filter comparison audit."""

        cfg = self._settings.candidate_comparison
        symbols = [
            str(ticker.get("symbol", "")).upper()
            for ticker in universe_tickers
            if ticker.get("symbol")
        ]
        quote_volumes = {
            str(ticker.get("symbol", "")).upper(): float(
                ticker.get("quoteVolume", 0) or 0
            )
            for ticker in universe_tickers
            if ticker.get("symbol")
        }
        if precomputed_v2 is not None and precomputed_v2[0]:
            challenger_decisions, challenger_observations, next_state = precomputed_v2
        else:
            target_version = (
                cfg.challenger_version
                if cfg.challenger_version == "candidate_filter_v2"
                else "candidate_filter_v2"
            )
            policy = CandidateV2Policy(
                version=target_version,
                max_candidates=cfg.max_candidates,
            )
            previous_state = {
                symbol: value
                for symbol, value in self._load_candidate_filter_state().items()
                if isinstance(value, dict)
                and value.get("filter_version") == target_version
            }
            challenger_decisions, challenger_observations, next_state = (
                scan_candidate_filter_v2(
                    symbols,
                    comparison_now,
                    previous_state,
                    policy,
                    quote_volumes_24h=quote_volumes,
                    base_url=str(self._settings.binance.base_url),
                    timeout_seconds=min(
                        10.0,
                        float(self._settings.collection.timeout_seconds),
                    ),
                    max_workers=cfg.max_workers,
                )
            )
        audit: CandidateFilterCycleAudit = assemble_candidate_filter_audit(
            universe_tickers=universe_tickers,
            production_symbols=production_symbols,
            champion_score_symbols=champion_score_symbols,
            pump_candidates=pump_candidates,
            challenger_decisions=challenger_decisions,
            challenger_observations=challenger_observations,
            champion_version=cfg.champion_version,
            challenger_version=cfg.challenger_version,
            champion_fallback_all=champion_fallback_all,
        )

        write_counts = self._candidate_filter_store.save_cycle(
            db.conn,
            decisions=audit.decisions,
            observations=audit.observations,
            run_id=self._run_id,
            cycle=self._cycle_count,
            horizon_hours=cfg.horizon_hours,
            target_drawdown=cfg.target_drawdown,
            max_adverse_excursion=cfg.max_adverse_excursion,
            decision_interval_minutes=cfg.decision_interval_minutes,
        )
        resolved_count = 0
        if (
            self._cycle_count == 1
            or self._cycle_count % cfg.outcome_check_interval_cycles == 0
        ):
            resolved_count = self._candidate_filter_store.resolve_due_outcomes(
                db.conn,
                now=datetime.now(timezone.utc),
                gap_tolerance_minutes=cfg.gap_tolerance_minutes,
            )
        comparison = self._candidate_filter_store.comparison_metrics(
            db.conn,
            champion_version=cfg.champion_version,
            challenger_version=cfg.challenger_version,
            days=cfg.metrics_window_days,
            min_resolved=cfg.min_resolved,
            min_positive_events=cfg.min_positive_events,
            min_evaluation_days=cfg.min_evaluation_days,
            truth_event_gap_minutes=cfg.truth_event_gap_minutes,
            min_challenger_event_recall=cfg.min_challenger_event_recall,
            precision10_relative_gain=cfg.precision_at_10_relative_gain,
            max_recall_regression=cfg.max_recall_regression,
        )
        promotion = comparison["promotion"]
        status = (
            "eligible_for_human_review"
            if promotion["ready"] and promotion["passed"]
            else "challenger_not_better"
            if promotion["ready"]
            else "collecting_outcomes"
        )
        payload = {
            "generated_at": system_now().isoformat(),
            "timestamp_timezone": SYSTEM_TIMEZONE_NAME,
            "enabled": True,
            "status": status,
            "cycle": self._cycle_count,
            "run_id": self._run_id,
            "champion_version": cfg.champion_version,
            "challenger_version": cfg.challenger_version,
            "telegram_lane": cfg.champion_version,
            "challenger_telegram_enabled": False,
            **audit.current,
            "write_counts": write_counts,
            "resolved_this_cycle": resolved_count,
            "comparison": comparison,
        }

        # Commit before publishing the lock-free JSON consumed by the API.
        db.conn.commit()
        _atomic_json_write(self._candidate_filter_state_path, next_state)
        _atomic_json_write(self._candidate_filter_comparison_path, payload)
        self._last_candidate_comparison = {
            "enabled": True,
            "status": status,
            "universe_count": audit.current["universe_count"],
            "paired_count": audit.current["paired_count"],
            "champion_selected": audit.current["champion_selected"],
            "challenger_selected": audit.current["challenger_selected"],
            "resolved": comparison["metrics"][cfg.challenger_version]["resolved"],
        }
        logger.info(
            "candidate_filter_comparison_published",
            cycle=self._cycle_count,
            status=status,
            n_universe=audit.current["universe_count"],
            n_paired=audit.current["paired_count"],
            champion_selected=audit.current["champion_selected"],
            challenger_selected=audit.current["challenger_selected"],
            resolved_this_cycle=resolved_count,
        )

    def _publish_candidate_snapshot(self, db: DuckDBQueryLayer) -> None:
        """Publish latest scored rows for the web API without DuckDB locks.

        The live scanner owns DuckDB's writer lock on Windows. The API cannot
        reliably read the database while that process is alive, even though
        the scan rows are committed. An atomic JSON snapshot keeps the serving
        path current and prevents the UI from falling back to an old database
        copy.
        """

        columns = [
            "symbol",
            "scan_time",
            "score",
            "recommendation",
            "close_price",
            "price_change_24h",
            "oi_change_24h",
            "funding_rate",
            "taker_sell_ratio",
            "volume_24h_usd",
            "pump_pct",
            "pump_days",
            "model_probability",
            "heuristic_score",
            "calibrated_probability",
            "data_quality_score",
            "quality_status",
            "max_feature_age_minutes",
            "horizon_hours",
            "anomaly_score",
            "anomaly_level",
            "anomaly_count",
            "anomalies_json",
        ]
        try:
            # ``cycle`` restarts at 1 after a daemon restart, so filtering on
            # the number alone would mix old and new runs. The append-only
            # rowid tail identifies the contiguous block written by the
            # latest cycle without relying on wall-clock timezone history.
            tail = db.conn.execute(
                """
                SELECT rowid, cycle
                FROM scan_results
                ORDER BY rowid DESC
                LIMIT 1000
                """
            ).fetchall()
            latest_cycle_start = None
            if tail:
                latest_cycle = tail[0][1]
                current_cycle_rows = []
                for rowid, cycle in tail:
                    if cycle != latest_cycle:
                        break
                    current_cycle_rows.append(rowid)
                if current_cycle_rows:
                    latest_cycle_start = min(current_cycle_rows)

            if latest_cycle_start is None:
                return
            rows = db.conn.execute(
                """
                SELECT symbol, scan_time, score, recommendation, close_price,
                       price_change_24h, oi_change_24h, funding_rate,
                       taker_sell_ratio, volume_24h_usd, pump_pct, pump_days,
                       model_probability, heuristic_score, calibrated_probability,
                       data_quality_score, quality_status, max_feature_age_minutes,
                       horizon_hours, anomaly_score,
                       anomaly_level, anomaly_count, anomalies_json
                FROM (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY symbol ORDER BY rowid DESC
                    ) AS rn
                    FROM scan_results
                    WHERE rowid >= ?
                )
                WHERE rn = 1
                ORDER BY score DESC
                LIMIT 200
                """,
                [latest_cycle_start],
            ).fetchall()
            payload = {
                "generated_at": system_now().isoformat(),
                "timestamp_timezone": "UTC",
                "cycle": self._cycle_count,
                "rows": [dict(zip(columns, row)) for row in rows],
            }
            _atomic_json_write(self._candidate_snapshot_path, payload)
        except Exception as exc:
            logger.warning(
                "candidate_snapshot_publish_failed",
                path=str(self._candidate_snapshot_path),
                error=str(exc),
            )
            # A loop that cannot publish is not successful. Exit so the
            # supervisor can reopen an invalidated DuckDB connection.
            raise

    def _publish_system_stats(self, db: DuckDBQueryLayer) -> None:
        """Publish current DuckDB table stats without requiring a web lock.

        The live scanner owns DuckDB's writer handle for its process lifetime.
        Windows may therefore reject the web server's read-only snapshot copy
        during an active cycle. Keep the freshness dashboard current by
        querying through the already-open scanner connection and writing a
        small atomic JSON artifact alongside the candidate snapshot. Count
        persistent materialized tables only: telemetry must never execute the
        Parquet price view or re-run temporary feature/alignment work.
        """

        try:
            conn = db.conn
            tables = [
                str(row[0])
                for row in conn.execute(
                    "SELECT table_name FROM duckdb_tables() "
                    "WHERE schema_name='main' AND NOT temporary "
                    "AND NOT starts_with(table_name, 'bf_') "
                    "AND NOT starts_with(table_name, '_source_') ORDER BY table_name"
                ).fetchall()
            ]
            ts_candidates = (
                "signal_time", "scan_time", "feature_time", "close_time",
                "period_end", "event_time", "candle_close_time", "time",
                "created_at",
            )
            stats: list[dict[str, Any]] = []
            for table in tables:
                try:
                    count_row = conn.execute(
                        f"SELECT count(*) FROM {table}"
                    ).fetchone()
                    n_rows = int(count_row[0]) if count_row is not None else 0
                except Exception:
                    n_rows = 0
                columns = [
                    str(row[1])
                    for row in conn.execute(
                        f"PRAGMA table_info('{table}')"
                    ).fetchall()
                ]
                ts_col = next((col for col in ts_candidates if col in columns), None)
                row: dict[str, Any] = {"table": table, "rows": n_rows}
                if ts_col and n_rows > 0:
                    try:
                        if table == "scan_results" and ts_col == "scan_time":
                            min_row = conn.execute(
                                f"SELECT min({ts_col}) FROM {table}"
                            ).fetchone()
                            max_row = conn.execute(
                                f"SELECT {ts_col} FROM {table} ORDER BY rowid DESC LIMIT 1"
                            ).fetchone()
                            min_time = min_row[0] if min_row is not None else None
                            max_time = max_row[0] if max_row is not None else None
                        else:
                            time_range = conn.execute(
                                f"SELECT min({ts_col}), max({ts_col}) FROM {table}"
                            ).fetchone()
                            if time_range is None:
                                min_time = max_time = None
                            else:
                                min_time, max_time = time_range
                        row["ts_column"] = ts_col
                        row["min_time"] = self._system_stats_timestamp(min_time)
                        row["max_time"] = self._system_stats_timestamp(max_time)
                    except Exception:
                        pass
                stats.append(row)

            scan_per_day: list[dict[str, Any]] = []
            if "scan_results" in tables:
                rows = conn.execute(
                    """
                    SELECT CAST((scan_time AT TIME ZONE 'UTC') AT TIME ZONE ? AS DATE) AS day,
                           count(*) AS n_rows,
                           count(DISTINCT cycle) AS n_cycles,
                           count(DISTINCT symbol) AS n_symbols
                    FROM scan_results
                    GROUP BY day
                    ORDER BY day DESC
                    LIMIT 30
                    """, [SYSTEM_TIMEZONE_NAME]
                ).fetchall()
                scan_per_day = [
                    {
                        "day": str(row[0]),
                        "n_rows": int(row[1] or 0),
                        "n_cycles": int(row[2] or 0),
                        "n_symbols": int(row[3] or 0),
                    }
                    for row in rows
                ]

            signals_per_day: list[dict[str, Any]] = []
            if "alert_history" in tables:
                rows = conn.execute(
                    """
                    SELECT CAST((signal_time AT TIME ZONE 'UTC') AT TIME ZONE ? AS DATE) AS day,
                           count(*) AS n_signals,
                           count(*) FILTER (WHERE telegram_sent = TRUE) AS n_telegram,
                           count(*) FILTER (WHERE hit = TRUE) AS n_hit
                    FROM alert_history
                    GROUP BY day
                    ORDER BY day DESC
                    LIMIT 30
                    """, [SYSTEM_TIMEZONE_NAME]
                ).fetchall()
                signals_per_day = [
                    {
                        "day": str(row[0]),
                        "n_signals": int(row[1] or 0),
                        "n_telegram": int(row[2] or 0),
                        "n_hit": int(row[3] or 0),
                    }
                    for row in rows
                ]

            _atomic_json_write(
                self._system_stats_path,
                {
                    "generated_at": system_now().isoformat(),
                    "timestamp_timezone": SYSTEM_TIMEZONE_NAME,
                    "data_stats_scope": "persistent_tables",
                    "data_stats": stats,
                    "scan_per_day": scan_per_day,
                    "signals_per_day": signals_per_day,
                },
            )
        except Exception as exc:
            logger.warning(
                "system_stats_publish_failed",
                path=str(self._system_stats_path),
                error=str(exc),
            )

    @staticmethod
    def _system_stats_timestamp(value: Any) -> str | None:
        return system_iso(value)

    def _run_self_learning_if_due(self) -> None:
        """Create a challenger when the configured outcome threshold is met."""

        config = self._settings.self_learning
        if not config.enabled or self._cycle_count % config.check_interval_cycles != 0:
            return
        champion_model_id = self._scanner_cfg.frozen_model_id
        if not champion_model_id:
            return
        try:
            result = run_self_learning(
                db_path=self._scanner_cfg.db_path,
                artifact_dir=self._scanner_cfg.artifact_dir,
                champion_model_id=champion_model_id,
                state_path=config.state_path,
                report_dir=config.report_dir,
                min_training_outcomes=config.min_training_outcomes,
                min_new_outcomes=config.min_new_outcomes,
                min_positive_events=config.min_positive_events,
                min_precision_improvement=config.min_precision_improvement,
                max_recall_regression=config.max_recall_regression,
                max_brier_regression=config.max_brier_regression,
                recent_window_days=config.recent_window_days,
                recent_sample_weight=config.recent_sample_weight,
                historical_max_rows=config.historical_max_rows,
                seed=config.seed,
            )
            logger.info(
                "scanner_self_learning_check",
                cycle=self._cycle_count,
                status=result.get("status"),
                reason=result.get("reason"),
                challenger_model_id=result.get("challenger_model_id"),
                report_path=result.get("report_path")
                or result.get("last_report_path"),
            )
        except Exception as exc:
            # Self-learning must never stop the serving loop.
            logger.warning("scanner_self_learning_failed", error=str(exc))

    def _compute_btc_context(self, db: DuckDBQueryLayer):
        """Compute BTC context from latest BTC features."""
        try:
            btc_df = db.conn.execute(
                """
                SELECT * FROM feature_results
                WHERE symbol = 'BTCUSDT'
                  AND feature_time <= ?
                ORDER BY feature_time DESC LIMIT 1
                """,
                [_last_closed_5m_end(datetime.now(timezone.utc))],
            ).df()
            if btc_df.empty:
                logger.warning("btc_no_features")
                return classify_btc(0.0, 0.0, 0.0, self._settings.scoring)
            row = btc_df.iloc[0]
            return classify_btc(
                btc_ret_24h=float(row.get("price_ret_24h", 0.0)),
                btc_ret_4h=float(row.get("price_ret_4h", 0.0)),
                btc_ret_1h=float(row.get("price_ret_5m", 0.0)),
                config=self._settings.scoring,
            )
        except Exception as exc:
            logger.warning("btc_context_failed", error=str(exc))
            return classify_btc(0.0, 0.0, 0.0, self._settings.scoring)

    def _collect_all(
        self, symbols: list[str], start_dt: datetime, end_dt: datetime
    ) -> None:
        """Incremental collect for all symbols across all data types.

        Collection is network-bound, so independent symbols run in a bounded
        pool. Each symbol gets a deep-copied settings object and a unique run
        id; this avoids mutating the shared symbol setting and prevents
        concurrent collectors from overwriting the same raw file.
        """
        client = BinanceClient()
        cycle_run_id = f"scan_{int(time.time())}_{self._cycle_count}"
        data_dir = Path(self._settings.paths.data_dir)

        def collect_symbol(symbol: str) -> None:
            symbol_settings = self._settings.model_copy(deep=True)
            symbol_settings.binance.symbol = symbol
            for data_type, _label, collector_cls in _COLLECTORS:
                inc_start = get_incremental_start(
                    data_dir, data_type, symbol, start_dt
                )
                if inc_start > end_dt:
                    continue
                try:
                    collector = collector_cls(client, symbol_settings)
                    collector.collect(
                        inc_start,
                        end_dt,
                        f"{cycle_run_id}_{symbol}",
                    )
                except Exception as exc:
                    logger.warning(
                        "scanner_collect_skip",
                        symbol=symbol,
                        data_type=data_type,
                        error=str(exc),
                    )

        max_workers = max(1, min(int(self._settings.collection.max_concurrency), 8))
        with ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="scanner_collect",
        ) as executor:
            futures = [executor.submit(collect_symbol, symbol) for symbol in symbols]
            for future in as_completed(futures):
                # Per-data-type failures are logged above; this catches a
                # worker-level failure without aborting sibling symbols.
                try:
                    future.result()
                except Exception as exc:
                    logger.warning("scanner_collect_worker_failed error=%s", exc)

    def _normalize_and_timeline(self) -> bool:
        """Normalize raw → parquet → build timeline views."""
        created_files = process_raw_to_parquet(self._settings)
        db = DuckDBQueryLayer(str(self._scanner_cfg.db_path))
        try:
            tables = {
                str(row[0])
                for row in db.conn.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'main'"
                ).fetchall()
            }
            if created_files == 0 and {
                "raw_timeline",
                "feature_results",
            }.issubset(tables):
                return False
            build_raw_timeline(db, self._settings, materialize_sources=True)
            return True
        finally:
            # Explicitly release DuckDB buffers and the writer lock each cycle.
            db.close()

    def _dispatch_shadow_observation(
        self,
        *,
        symbol: str,
        score: Any,
        result: Any,
        pump_pct: float,
        pump_days: int,
        close_price: float | None,
        sig_time: datetime,
        invalidation_time: datetime,
        horizon_hours: int,
        prediction_id: str,
        volume_24h_usd: float = 0.0,
        collect_for_digest: bool = False,
    ) -> bool | dict[str, Any] | None:
        """Evaluate and send (or collect) one Radar observation."""
        cooldown_key = f"{symbol}:{horizon_hours}h"
        telegram_cooldown = getattr(
            self._scanner_cfg, "telegram_cooldown_minutes", self._scanner_cfg.cooldown_minutes
        )
        in_cooldown = bool(
            self._alert_store.is_in_cooldown_key(cooldown_key, telegram_cooldown)
            or self._alert_store.is_in_cooldown(symbol, telegram_cooldown)
            or self._scan_result_store.is_prediction_telegram_in_cooldown(
                symbol, horizon_hours, telegram_cooldown
            )
        )
        min_vol = getattr(self._scanner_cfg, "telegram_min_volume_usd", 500_000.0)
        if min_vol > 0 and (volume_24h_usd <= 0 or volume_24h_usd < min_vol):
            logger.info(
                "scanner_telegram_volume_suppressed",
                symbol=symbol,
                volume=volume_24h_usd,
                min_volume=min_vol,
            )
            return False if not collect_for_digest else None

        # Digest mode applies the quota after all symbols are ranked.  The
        # direct-send path needs the same guard before sending one symbol.
        if not collect_for_digest:
            daily_limit = int(getattr(self._scanner_cfg, "global_daily_alert_limit", 10))
            coin_daily_limit = int(getattr(self._scanner_cfg, "coin_daily_alert_limit", 1))
            try:
                sent_raw = self._scan_result_store.get_prediction_telegram_count(hours=24)
                coin_raw = self._scan_result_store.get_prediction_telegram_count(
                    symbol=symbol, hours=24
                )
            except Exception as exc:
                logger.error("scanner_daily_budget_unavailable", symbol=symbol, error=str(exc))
                return False
            # Treat an unreadable count as exhausted rather than coercing an
            # arbitrary mock/driver value into a number and sending blindly.
            sent_24h = int(sent_raw) if isinstance(sent_raw, Real) else daily_limit
            coin_sent = int(coin_raw) if isinstance(coin_raw, Real) else coin_daily_limit
            if sent_24h >= daily_limit:
                logger.info(
                    "scanner_action_suppressed",
                    symbol=symbol,
                    mode=self._operating_mode,
                    tier=result.risk_tier,
                    reason="global_daily_budget_exhausted",
                )
                return False
            if coin_sent >= coin_daily_limit:
                logger.info(
                    "scanner_action_suppressed",
                    symbol=symbol,
                    mode=self._operating_mode,
                    tier=result.risk_tier,
                    reason="coin_daily_budget_exhausted",
                )
                return False

        allowed_tiers = getattr(self._scanner_cfg, "telegram_tiers", ["HIGH_CONFIDENCE"])
        decision = evaluate_canary_policy(
            mode=self._operating_mode,
            tier=result.risk_tier,
            quality_status=result.quality.status,
            calibrated_probability=result.calibrated_probability,
            threshold=result.threshold,
            in_cooldown=in_cooldown,
            global_count=0,
            coin_count=0,
            global_limit=0,
            coin_limit=0,
            kill_switch_active=self._kill_switch.active,
            bundle_valid=self._bundle_valid,
            allow_shadow_telegram=True,
            telegram_min_probability=self._scanner_cfg.telegram_min_probability,
            allowed_tiers=allowed_tiers,
            enforce_shadow_cooldown=True,
        )
        if not decision.allowed:
            logger.info(
                "scanner_action_suppressed",
                symbol=symbol,
                mode=self._operating_mode,
                tier=result.risk_tier,
                reason=decision.reason,
            )
            return False if not collect_for_digest else None

        alert_item = {
            "symbol": symbol,
            "total_score": score.total_score,
            "recommendation": result.risk_tier,
            "pump_pct": pump_pct,
            "pump_days": pump_days,
            "top_signals": [
                (c.name, c.score, c.weight, c.explanation)
                for c in score.top_signals
            ],
            "btc_regime": score.btc_regime,
            "btc_explanation": score.btc_explanation,
            "close_price": close_price,
            "feature_time": str(sig_time),
            "sig_time": sig_time,
            "invalidation_time": str(invalidation_time),
            "model_probability": result.calibrated_probability,
            "quality_status": result.quality.status,
            "evidence_groups": list(result.evidence_groups),
            "volume_24h_usd": volume_24h_usd,
            "horizon_hours": horizon_hours,
            "data_quality_score": result.quality.score,
            "model_id": self._frozen_info.model_id,
            "label_version": (
                self._frozen_info.label_spec.get("version", "distribution_short_v1")
                if isinstance(self._frozen_info.label_spec, dict)
                else "distribution_short_v1"
            ),
            "operating_mode": self._operating_mode,
            "prediction_id": prediction_id,
            "web_url": _coin_url(self._web_base_url, symbol),
        }

        if collect_for_digest:
            return alert_item

        sent = self._notifier.send_scored_alert(
            symbol=symbol,
            total_score=score.total_score,
            recommendation=result.risk_tier,
            pump_pct=pump_pct,
            pump_days=pump_days,
            top_signals=[
                (c.name, c.score, c.weight, c.explanation)
                for c in score.top_signals
            ],
            btc_regime=score.btc_regime,
            btc_explanation=score.btc_explanation,
            close_price=close_price,
            feature_time=str(sig_time),
            invalidation_time=str(invalidation_time),
            model_probability=result.calibrated_probability,
            horizon_hours=horizon_hours,
            data_quality_score=result.quality.score,
            model_id=self._frozen_info.model_id,
            label_version=self._frozen_info.label_spec.get("version", "distribution_short_v1")
            if isinstance(self._frozen_info.label_spec, dict)
            else "distribution_short_v1",
            operating_mode=self._operating_mode,
        )
        if sent:
            self._scan_result_store.mark_prediction_telegram_sent(prediction_id)
            logger.info(
                "scanner_shadow_observation_sent",
                symbol=symbol,
                tier=result.risk_tier,
                quality_status=result.quality.status,
            )
        else:
            logger.warning(
                "scanner_shadow_observation_failed",
                symbol=symbol,
                tier=result.risk_tier,
            )
        return sent

    def _score_and_alert_composite(
        self,
        symbol: str,
        db: DuckDBQueryLayer,
        btc_context: Any,
        pump_candidate: PumpCandidate | None,
        collect_for_digest: bool = False,
        regime_state: RegimeState | None = None,
    ) -> int | dict[str, Any] | None:
        """Score one symbol with composite scorer, send Telegram if score >= threshold.

        Returns number of alerts sent (0 or 1) or an alert dict if collect_for_digest is True.
        """
        # Get latest features for this symbol — JOIN kline to get close price
        df = db.conn.execute(
            """
            SELECT f.*, k.close, k.volume_quote AS volume_24h
            FROM feature_results f
            LEFT JOIN kline k
                ON k.symbol = f.symbol
                AND k.close_time = f.feature_time
                AND k.interval = '5m'
            WHERE f.symbol = ?
              AND f.feature_time <= ?
            ORDER BY f.feature_time DESC LIMIT 12
            """,
            [symbol, _last_closed_5m_end(datetime.now(timezone.utc))],
        ).df()

        if df.empty:
            logger.debug("scanner_no_features", symbol=symbol)
            return 0 if not collect_for_digest else None

        latest = df.iloc[0]
        feature_dict: dict[str, Any] = {}
        for col in df.columns:
            val = latest[col]
            if pd.notna(val):
                feature_dict[col] = val

        anomaly_report: AnomalyReport = detect_market_anomalies(
            feature_dict,
            self._settings.market_anomalies,
        )
        pump_pct = pump_candidate.pump_pct if pump_candidate else 0.0
        pump_days = pump_candidate.pump_days if pump_candidate else 0
        score_started = time.perf_counter()
        # Evaluate freshness/quality before model inference. Invalid or stale
        # snapshots are retained for observability but cannot alert.
        quality = assess_snapshot_quality(
            feature_dict,
            self._frozen_info,
            now=datetime.now(timezone.utc),
            max_feature_age_minutes=self._scanner_cfg.max_feature_age_minutes,
            min_data_quality_score=self._scanner_cfg.min_data_quality_score,
        )
        result: SnapshotScore = score_snapshot(
            symbol=symbol,
            feature_dict=feature_dict,
            btc_context=btc_context,
            frozen_info=self._frozen_info,
            config=self._settings.scoring,
            threshold_policy=self._settings.threshold,
            pump_pct=pump_pct,
            pump_days=pump_days,
            quality=quality,
            max_feature_age_minutes=self._scanner_cfg.max_feature_age_minutes,
            min_data_quality_score=self._scanner_cfg.min_data_quality_score,
        )
        
        # Meta-labeling filter
        enable_meta = getattr(self._scanner_cfg, "enable_meta_labeling", "disabled")
        if result.alertable and enable_meta != "disabled":
            try:
                meta_path = getattr(self._scanner_cfg, "meta_model_path", None)
                if self._meta_model is None and meta_path:
                    model_path = Path(meta_path)
                    if model_path.exists():
                        self._meta_model = MetaLabelingModel.load(model_path)
                    else:
                        logger.warning("meta_model_not_found", path=str(model_path))
                
                if self._meta_model is not None:
                    # Use real regime classification if available from regime_state
                    if regime_state is not None and hasattr(regime_state, "regime"):
                        regime = regime_state.regime.value if hasattr(regime_state.regime, "value") else str(regime_state.regime)
                    else:
                        regime = btc_context.get("regime", "SIDEWAY_DISTRIBUTION") if isinstance(btc_context, dict) else getattr(btc_context, "regime", "SIDEWAY_DISTRIBUTION")
                    meta_decision = self._meta_model.filter_signal(
                        features=feature_dict,
                        primary_prob=result.calibrated_probability or 0.0,
                        regime=regime,
                        threshold_override=getattr(self._scanner_cfg, "meta_model_min_confidence", 0.5),
                    )
                    logger.info(
                        "meta_labeling_decision",
                        symbol=symbol,
                        primary_probability=result.calibrated_probability,
                        meta_approved=meta_decision.should_execute,
                        meta_confidence=meta_decision.meta_probability,
                        mode=enable_meta,
                    )
                    
                    if enable_meta == "active" and not meta_decision.should_execute:
                        if result.risk_tier == "HIGH_CONFIDENCE":
                            result = dataclasses.replace(result, risk_tier="WATCH")
            except Exception as exc:
                logger.warning("meta_model_error", symbol=symbol, error=str(exc))

        # Regime Gate: filter out signals occurring during disallowed market regimes (e.g. TRENDING_BULL / HIGH_VOL_CHOP)
        regime_gate_enabled = getattr(self._scanner_cfg, "regime_gate_enabled", False)
        if result.alertable and regime_gate_enabled and regime_state is not None:
            allowed_regimes = getattr(
                self._scanner_cfg,
                "regime_gate_allowed",
                ["SIDEWAY_DISTRIBUTION", "TRENDING_BEAR"],
            )
            current_regime_name = (
                regime_state.regime.value
                if hasattr(regime_state.regime, "value")
                else str(regime_state.regime)
            )
            if current_regime_name not in allowed_regimes:
                logger.info(
                    "regime_gate_suppressed",
                    symbol=symbol,
                    current_regime=current_regime_name,
                    allowed_regimes=allowed_regimes,
                    original_tier=result.risk_tier,
                )
                if result.risk_tier == "HIGH_CONFIDENCE":
                    result = dataclasses.replace(result, risk_tier="WATCH")

        score = result.heuristic

        close_price: float | None = None
        if "close" in df.columns and pd.notna(latest.get("close")):
            close_price = float(latest["close"])

        horizon_hours = _horizon_hours(self._frozen_info)
        sig_raw = pd.Timestamp(latest.get("feature_time"))
        if pd.isna(sig_raw):
            logger.warning("scanner_invalid_signal_timestamp", symbol=symbol)
            return 0
        sig_value = sig_raw.to_pydatetime()
        if not isinstance(sig_value, datetime):
            logger.warning("scanner_invalid_signal_timestamp", symbol=symbol)
            return 0
        sig_time = sig_value
        if sig_time.tzinfo is None:
            sig_time = sig_time.replace(tzinfo=timezone.utc)
        else:
            sig_time = sig_time.astimezone(timezone.utc)
        invalidation_time = sig_time + timedelta(hours=horizon_hours)

        # The joined kline row is only the latest 5-minute candle.  It must
        # never be treated as 24-hour volume: doing so suppresses liquid coins
        # whenever that single candle is below the Telegram liquidity floor.
        volume_24h_usd = 0.0
        try:
            volume_row = db.conn.execute(
                """
                SELECT COALESCE(SUM(volume_quote), 0.0)
                FROM kline
                WHERE symbol = ?
                  AND interval = '5m'
                  AND close_time > ?
                  AND close_time <= ?
                """,
                [symbol, sig_time - timedelta(hours=24), sig_time],
            ).fetchone()
            if volume_row:
                volume_24h_usd = float(volume_row[0] or 0.0)
        except Exception as exc:
            logger.warning("scanner_24h_volume_query_failed", symbol=symbol, error=str(exc))

        # Pump candidates carry Binance's latest daily quote volume.  It is a
        # safe fallback when the local 5m history has a gap or is still warm.
        candidate_volume = float(pump_candidate.quote_volume or 0.0) if pump_candidate else 0.0
        if candidate_volume > volume_24h_usd:
            volume_24h_usd = candidate_volume

        # Persist EVERY scored symbol (Constitution Khối 6: record every
        # signal, not just the ones that crossed the alert threshold). This
        # is what powers the real "candidates" list in the UI instead of
        # hardcoded mock data.
        try:
            self._scan_result_store.save_batch(
                [
                    ScanResultRecord(
                        scan_time=datetime.now(timezone.utc),
                        symbol=symbol,
                        score=score.total_score,
                        recommendation=result.risk_tier,
                        model_probability=result.model_probability,
                        heuristic_score=score.total_score,
                        calibrated_probability=result.calibrated_probability,
                        data_quality_score=result.quality.score,
                        quality_status=result.quality.status,
                        max_feature_age_minutes=result.quality.max_feature_age_minutes,
                        horizon_hours=horizon_hours,
                        close_price=close_price,



                        price_change_24h=float(feature_dict.get("price_ret_24h", 0.0) or 0.0),
                        oi_change_24h=float(feature_dict.get("oi_change_24h", 0.0) or 0.0),
                        funding_rate=float(feature_dict.get("funding_rate_raw", 0.0) or 0.0),
                        taker_sell_ratio=1.0
                        - float(feature_dict.get("taker_buy_ratio", 0.5) or 0.5),
                        volume_24h_usd=volume_24h_usd,
                        pump_pct=pump_pct,
                        pump_days=pump_days,
                        anomaly_score=anomaly_report.score,
                        anomaly_level=anomaly_report.level,
                        anomaly_count=len(anomaly_report.anomalies),
                        anomalies_json=json.dumps(
                            anomaly_report.to_dict(),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        cycle=self._cycle_count,
                    )
                ],
                conn=db.conn,
            )
        except Exception as exc:
            logger.warning("scan_result_save_failed", symbol=symbol, error=str(exc))

        # Process state machine for episode lifecycle
        ep_result = None
        episode_allows_delivery = False  # Fail-closed default
        try:
            effective_threshold = result.threshold

            flap_limit = getattr(self._scanner_cfg, "alert_flap_limit", 3)
            rearm_threshold = getattr(self._scanner_cfg, "alert_rearm_probability", 0.4)
            if effective_threshold < rearm_threshold:
                rearm_threshold = effective_threshold * 0.95

            ep_result = self._alert_store.process_snapshot(
                symbol=symbol,
                horizon_hours=horizon_hours,
                probability=result.calibrated_probability,
                threshold=effective_threshold,
                is_usable=result.quality.is_usable,
                timestamp=sig_time,
                flap_limit=flap_limit,
                alert_rearm_probability=rearm_threshold,
            )

            telegram_cooldown = getattr(
                self._scanner_cfg, "telegram_cooldown_minutes", self._scanner_cfg.cooldown_minutes
            )
            cooldown_key = f"{symbol}:{horizon_hours}h"
            in_cooldown = bool(
                self._alert_store.is_in_cooldown_key(cooldown_key, telegram_cooldown)
                or self._alert_store.is_in_cooldown(symbol, telegram_cooldown)
                or self._scan_result_store.is_prediction_telegram_in_cooldown(
                    symbol, horizon_hours, telegram_cooldown
                )
            )

            # Only allow Telegram dispatch if newly opened, or if continued and cooldown has expired
            if ep_result:
                if ep_result.transition == "OPENED":
                    episode_allows_delivery = True
                elif ep_result.transition == "CONTINUED" and not in_cooldown:
                    episode_allows_delivery = True
            else:
                if not in_cooldown:
                    episode_allows_delivery = True
        except Exception as exc:
            logger.warning("episode_tracker_failed", symbol=symbol, error=str(exc))

        # This is separate from alert_history so shadow data cannot disappear
        # merely because a threshold or Telegram policy suppressed it.
        try:
            label_spec = self._frozen_info.label_spec if isinstance(self._frozen_info.label_spec, dict) else {}
            checksum_values = self._frozen_info.checksums or {}
            bundle_checksum = hashlib.sha256(
                json.dumps(checksum_values, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            snapshot_id = hashlib.sha256(
                json.dumps(
                    {"symbol": symbol, "feature_time": str(sig_time), "model_id": self._frozen_info.model_id},
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()[:32]
            execution_policy = None
            if close_price is not None and close_price > 0:
                policy_context = PolicyContext(
                    signal_probability=result.calibrated_probability,
                    label_version=str(
                        label_spec.get("version", "distribution_short_v1")
                    ),
                    signal_score=score.total_score,
                    quality_score=result.quality.score,
                    volume_24h_usd=volume_24h_usd,
                    features=feature_dict,
                    anomalies=tuple(
                        anomaly.to_dict() for anomaly in anomaly_report.anomalies
                    ),
                )
                policy_decision = ExecutionPolicyRouter(
                    self._settings.execution_policy
                ).route(policy_context)
                execution_policy = policy_decision.to_dict(
                    signal_price=close_price,
                    target_drawdown=self._settings.execution_policy.target_drawdown,
                )

            # Use the same independent evidence grouping as frozen inference;
            # correlated indicators must never inflate the audit count.
            groups = tuple(result.evidence_groups)
            state = (
                "invalidated" if not result.quality.is_usable
                else "confirmed_distribution" if result.risk_tier == "HIGH_CONFIDENCE"
                else "early_watch"
            )
            prediction_id = PredictionRecord.stable_id(
                symbol, sig_time, self._frozen_info.model_id, horizon_hours
            )
            self._scan_result_store.save_prediction(
                PredictionRecord(
                    prediction_id=prediction_id,
                    symbol=symbol,
                    signal_time=sig_time,
                    created_at=datetime.now(timezone.utc),
                    horizon_hours=horizon_hours,
                    target_drawdown=float(label_spec.get("target_drawdown", 0.08)),
                    max_adverse_excursion=float(label_spec.get("max_ae", label_spec.get("max_adverse_excursion", 0.04))),
                    label_version=str(label_spec.get("version", "distribution_short_v1")),
                    heuristic_score=float(score.total_score),
                    model_probability=result.model_probability,
                    calibrated_probability=result.calibrated_probability,
                    data_quality_score=result.quality.score,
                    quality_status=result.quality.status,
                    max_feature_age_minutes=result.quality.max_feature_age_minutes,
                    missing_features=result.quality.missing_features,
                    model_id=self._frozen_info.model_id,
                    calibrator_id=result.calibrator_id,
                    threshold_policy_version=result.threshold_policy_version,
                    candidate_passed=result.risk_tier != "WAIT",
                    state=state,
                    tier=result.risk_tier,
                    threshold=result.threshold,
                    reason_codes=result.quality.reason_codes,
                    evidence_groups=groups,
                    shadow_mode=self._operating_mode in {"research", "shadow"},
                    alert_episode_id=ep_result.episode_id if ep_result else None,
                    episode_role=ep_result.role if ep_result else None,
                    episode_transition=ep_result.transition if ep_result else None,
                    execution_policy=execution_policy,
                    cooldown_key=f"{symbol}:{horizon_hours}h",
                    invalidation_time=invalidation_time,
                    snapshot_id=snapshot_id,
                    bundle_checksum=bundle_checksum,
                    latency_ms=(time.perf_counter() - score_started) * 1000.0,
                )
            )
        except Exception as exc:
            logger.warning("prediction_audit_save_failed", symbol=symbol, error=str(exc))


        # Drop out entirely if the episode tracker says NO_ACTION / CLOSE_EPISODE
        if not episode_allows_delivery:
            logger.info("scanner_telegram_suppressed_by_episode_tracker", symbol=symbol, transition=ep_result.transition if ep_result else "UNKNOWN")
            return 0 if not collect_for_digest else None

        # Normal alert history remains restricted to alertable signals. In
        # shadow mode, however, the operator explicitly opted in to labelled
        # observational Telegram messages for Radar detections as well.
        if not result.alertable:
            if self._operating_mode == "shadow" and self._scanner_cfg.shadow_telegram_enabled:
                res = self._dispatch_shadow_observation(
                    symbol=symbol,
                    score=score,
                    result=result,
                    pump_pct=pump_pct,
                    pump_days=pump_days,
                    close_price=close_price,
                    sig_time=sig_time,
                    invalidation_time=invalidation_time,
                    horizon_hours=horizon_hours,
                    prediction_id=PredictionRecord.stable_id(
                        symbol, sig_time, self._frozen_info.model_id, horizon_hours
                    ),
                    volume_24h_usd=volume_24h_usd,
                    collect_for_digest=collect_for_digest,
                )
                if collect_for_digest:
                    return res if isinstance(res, dict) else None
                return 1 if res is True else 0
            logger.info(
                "scanner_alert_suppressed",
                symbol=symbol,
                tier=result.risk_tier,
                quality_status=result.quality.status,
                quality_reasons=list(result.quality.reason_codes),
            )
            return 0 if not collect_for_digest else None

        calibrated_probability = result.calibrated_probability
        if calibrated_probability is None:
            logger.warning("scanner_missing_calibrated_probability", symbol=symbol)
            return 0 if not collect_for_digest else None

        # Cross-reference with CoinGecko if enabled — flagged explicitly
        # (not just logged) so the alert record + UI can surface it.
        price_mismatch = False
        if self._settings.coingecko.enabled and close_price:
            xref = cross_reference(
                binance_price=close_price,
                binance_volume_usd=float(feature_dict.get("volume_base", 0) or 0),
                symbol=symbol,
                config=self._settings.coingecko,
            )
            if xref.flag == "PRICE_MISMATCH":
                price_mismatch = True
                logger.warning(
                    "price_mismatch_detected",
                    symbol=symbol,
                    binance=close_price,
                    coingecko=xref.coingecko_price,
                    diff=xref.price_diff_pct,
                )

        # Self-learning feedback: attach the *empirical* historical precision
        # for this risk level (from resolved outcomes) as evidence quality,
        # instead of only showing the unvalidated heuristic score.
        risk_tier = result.risk_tier
        risk_level = _risk_level_for_tier(risk_tier)
        evidence = self._alert_store.precision_by_risk_level(days=30).get(risk_level, {})
        evidence_precision = evidence.get("precision")
        evidence_n_judged = evidence.get("n_judged", 0)

        components_payload: list[dict[str, Any]] = [
            {
                "name": c.name,
                "raw_value": c.raw_value,
                "score": c.score,
                "weight": c.weight,
                "weighted_score": c.weighted_score,
                "explanation": c.explanation,
            }
            for c in score.components
        ]
        if price_mismatch:
            components_payload.append(
                {
                    "name": "price_cross_reference",
                    "raw_value": None,
                    "score": 0.0,
                    "weight": 0.0,
                    "weighted_score": 0.0,
                    "explanation": "PRICE_MISMATCH: giá Binance lệch đáng kể so với CoinGecko — kiểm tra lại trước khi tin tưởng alert này.",
                }
            )

        # Save to alert history
        record = AlertRecord(
            signal_time=sig_time,
            symbol=symbol,
            probability=float(calibrated_probability),
            risk_level=risk_level,
            threshold=result.threshold,
            close_price=close_price,
            model_id=self._frozen_info.model_id,
            invalidation_time=invalidation_time,
            model_probability=result.model_probability,
            heuristic_score=score.total_score,
            calibrated_probability=result.calibrated_probability,
            data_quality_score=result.quality.score,
            horizon_hours=horizon_hours,
            components_json=json.dumps(components_payload),
            evidence_precision=evidence_precision,
            evidence_n_judged=evidence_n_judged,
            cooldown_key=f"{symbol}:{horizon_hours}h",
            shadow_mode=self._operating_mode in {"research", "shadow"},
            reason_codes_json=json.dumps(list(result.quality.reason_codes)),
            threshold_policy_version=result.threshold_policy_version,
            alert_episode_id=ep_result.episode_id if ep_result else None,
        )
        self._alert_store.save(record)

        # Build top signals for Telegram
        top_signals = [
            (c.name, c.score, c.weight, c.explanation) for c in score.top_signals
        ]

        # Alertable shadow observations use the same filtered delivery path
        if self._operating_mode == "shadow" and self._scanner_cfg.shadow_telegram_enabled:
            res = self._dispatch_shadow_observation(
                symbol=symbol,
                score=score,
                result=result,
                pump_pct=pump_pct,
                pump_days=pump_days,
                close_price=close_price,
                sig_time=sig_time,
                invalidation_time=invalidation_time,
                horizon_hours=horizon_hours,
                prediction_id=PredictionRecord.stable_id(
                    symbol, sig_time, self._frozen_info.model_id, horizon_hours
                ),
                volume_24h_usd=volume_24h_usd,
                collect_for_digest=collect_for_digest,
            )
            if collect_for_digest:
                return res if isinstance(res, dict) else None
            if res is True:
                self._alert_store.mark_telegram_sent(sig_time, symbol)
            return 1 if res is True else 0

        cooldown_key = f"{symbol}:{horizon_hours}h"
        telegram_cooldown = getattr(
            self._scanner_cfg, "telegram_cooldown_minutes", self._scanner_cfg.cooldown_minutes
        )
        in_cooldown = bool(
            self._alert_store.is_in_cooldown_key(cooldown_key, telegram_cooldown)
            or self._alert_store.is_in_cooldown(symbol, telegram_cooldown)
            or self._scan_result_store.is_prediction_telegram_in_cooldown(
                symbol, horizon_hours, telegram_cooldown
            )
        )
        if in_cooldown:
            logger.info(
                "scanner_cooldown_skip",
                symbol=symbol,
                cooldown_minutes=telegram_cooldown,
            )

        min_vol = getattr(self._scanner_cfg, "telegram_min_volume_usd", 500_000.0)
        if min_vol > 0 and (volume_24h_usd <= 0 or volume_24h_usd < min_vol):
            logger.info(
                "scanner_telegram_volume_suppressed",
                symbol=symbol,
                volume=volume_24h_usd,
                min_volume=min_vol,
            )
            return 0 if not collect_for_digest else None

        allowed_tiers = getattr(self._scanner_cfg, "telegram_tiers", ["HIGH_CONFIDENCE"])
        global_daily_limit = getattr(self._scanner_cfg, "global_daily_alert_limit", 15)
        coin_daily_limit = getattr(self._scanner_cfg, "coin_daily_alert_limit", 2)
        global_count = self._alert_store.get_daily_alert_count()
        coin_count = self._alert_store.get_daily_alert_count(symbol)
        configured_high = {str(level).upper() for level in self._scanner_cfg.alert_levels}
        high_enabled = bool(configured_high.intersection({"HIGH_CONFIDENCE", "CAO"}))
        policy_decision = evaluate_canary_policy(
            mode=self._operating_mode,
            tier=result.risk_tier,
            quality_status=result.quality.status,
            calibrated_probability=result.calibrated_probability,
            threshold=result.threshold,
            in_cooldown=in_cooldown,
            global_count=global_count,
            coin_count=coin_count,
            global_limit=global_daily_limit,
            coin_limit=coin_daily_limit,
            kill_switch_active=self._kill_switch.active,
            bundle_valid=self._bundle_valid,
            allow_shadow_telegram=self._scanner_cfg.shadow_telegram_enabled,
            telegram_min_probability=self._scanner_cfg.telegram_min_probability,
            allowed_tiers=allowed_tiers,
            enforce_shadow_cooldown=True,
        )
        if not high_enabled and policy_decision.allowed:
            policy_decision = CanaryDecision(
                False,
                "high_confidence_alert_level_disabled",
                policy_decision.mode,
                policy_decision.tier,
                global_count,
                coin_count,
            )
        if not policy_decision.allowed:
            logger.info(
                "scanner_action_suppressed",
                symbol=symbol,
                mode=self._operating_mode,
                tier=result.risk_tier,
                reason=policy_decision.reason,
            )
            return 0 if not collect_for_digest else None

        prediction_id = PredictionRecord.stable_id(
            symbol, sig_time, self._frozen_info.model_id, horizon_hours
        )
        alert_item = {
            "symbol": symbol,
            "total_score": score.total_score,
            "recommendation": result.risk_tier,
            "pump_pct": pump_pct,
            "pump_days": pump_days,
            "top_signals": top_signals,
            "btc_regime": score.btc_regime,
            "btc_explanation": score.btc_explanation,
            "close_price": close_price,
            "evidence_precision": evidence_precision,
            "evidence_n_judged": evidence_n_judged,
            "feature_time": str(sig_time),
            "sig_time": sig_time,
            "invalidation_time": str(invalidation_time),
            "model_probability": result.calibrated_probability,
            "quality_status": result.quality.status,
            "evidence_groups": list(result.evidence_groups),
            "volume_24h_usd": volume_24h_usd,
            "horizon_hours": horizon_hours,
            "data_quality_score": result.quality.score,
            "model_id": self._frozen_info.model_id,
            "label_version": (
                self._frozen_info.label_spec.get("version", "distribution_short_v1")
                if isinstance(self._frozen_info.label_spec, dict)
                else "distribution_short_v1"
            ),
            "operating_mode": self._operating_mode,
            "prediction_id": prediction_id,
            "web_url": _coin_url(self._web_base_url, symbol),
        }

        if collect_for_digest:
            return alert_item

        sent = self._notifier.send_scored_alert(
            symbol=symbol,
            total_score=score.total_score,
            recommendation=result.risk_tier,
            pump_pct=pump_pct,
            pump_days=pump_days,
            top_signals=top_signals,
            btc_regime=score.btc_regime,
            btc_explanation=score.btc_explanation,
            close_price=close_price,
            evidence_precision=evidence_precision,
            evidence_n_judged=evidence_n_judged,
            feature_time=str(sig_time),
            invalidation_time=str(invalidation_time),
            model_probability=result.calibrated_probability,
            horizon_hours=horizon_hours,
            data_quality_score=result.quality.score,
            model_id=self._frozen_info.model_id,
            label_version=(
                self._frozen_info.label_spec.get("version", "distribution_short_v1")
                if isinstance(self._frozen_info.label_spec, dict)
                else "distribution_short_v1"
            ),
            operating_mode=self._operating_mode,
        )
        if sent:
            self._alert_store.mark_telegram_sent(sig_time, symbol)
            self._scan_result_store.mark_prediction_telegram_sent(prediction_id)
            logger.info(
                "scanner_composite_alert_sent",
                symbol=symbol,
                score=score.total_score,
                recommendation=score.recommendation,
            )
            return 1
        return 0
