"""Combined HTTP API + static file server for the React frontend.

Every handler below reads from real state (AlertStore, ScanResultStore,
scanner heartbeat file, Binance ticker API) instead of hardcoded/fabricated
data. There is no synchronous "run a scan inline" endpoint: the scanner
daemon is a separate long-running process, so "trigger scan" / "change scan
mode" write a flag file the daemon polls each cycle (see
ScannerDaemon._consume_trigger / _apply_runtime_overrides in
dao_vang.scanner.daemon) and this server returns a "queued" response rather
than fabricating a fake "48/48 coins scanned" success message.
"""

import base64
import hashlib
import hmac
import json
import logging
import math
import mimetypes
import secrets
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Full, Queue
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from zoneinfo import ZoneInfo

import duckdb

from dao_vang.alerts.store import AlertStore
from dao_vang.alerts.telegram import TelegramNotifier
from dao_vang.config.settings import load_runtime_settings
from dao_vang.data.binance_listing import get_stats_for_today
from dao_vang.data.storage.duckdb import open_read_only_connection
from dao_vang.domain.time import (
    SYSTEM_TIMEZONE_NAME,
    as_system_timezone,
    system_iso,
    system_now,
)
from dao_vang.execution.policy_router import PolicyContext, build_trade_setup
from dao_vang.scanner.anomalies import detect_market_anomalies
from dao_vang.scanner.healthcheck import inspect_heartbeat
from dao_vang.scanner.instance_lock import ScannerAlreadyRunning, ScannerInstanceLock
from dao_vang.scanner.pump_filter import analyze_pump, fetch_daily_klines
from dao_vang.scanner.scan_results_store import ScanResultStore
from dao_vang.scanner.tracking_evidence import market_observation, signal_outcome
from dao_vang.scanner.tracking_market import fetch_funding, reference_price
from dao_vang.scanner.tracking_monitor import start_tracking_monitor
from dao_vang.scanner.tracking_usage import tracking_usage
from dao_vang.scanner.tracking_watchlist import (
    TrackingWatchlistStore,
    calculate_position_metrics,
    normalize_symbol,
)
from dao_vang.scanner.watchlist import (
    _filter_tickers,
    add_to_watchlist,
    fetch_all_tickers,
    fetch_top_gainers,
    fetch_top_losers,
    load_manual_watchlist,
    normalize_scan_modes,
    remove_from_watchlist,
)
from dao_vang.scoring import (
    assess_snapshot_quality,
    classify_btc,
    compute_distribution_score,
    compute_two_tier_distribution_score,
    score_snapshot,
)
from dao_vang.scoring.engine_comparison import evaluate_scoring_engines_comparison
from dao_vang.web.dismissals import SignalDismissals

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dao_vang_api")

REPO_ROOT = Path(__file__).resolve().parents[3]
DIST_DIR = (REPO_ROOT / "frontend" / "dist").resolve()
FORWARD_TEST_PROTOCOL_PATH = REPO_ROOT / "configs" / "forward_test_live_v1.json"
ACTIVE_TARGET_DRAWDOWN = 0.20
ACTIVE_LABEL_VERSION = "distribution_short_v2"

_settings = load_runtime_settings()
_AUTH_FAILURES: dict[str, list[float]] = {}
_AUTH_FAILURE_WINDOW_SECONDS = 300.0
_AUTH_FAILURE_LIMIT = 5
WATCHLIST_PATH = _settings.scanner.watchlist_path


def _current_model_target_drawdown() -> float:
    """Return the active bundle's target, falling back to the new v2 goal.

    Existing v1 predictions must remain visibly tied to their original 8%
    contract until a calibrated v2 bundle is explicitly promoted.
    """

    model_id = _settings.scanner.frozen_model_id
    if model_id:
        metadata_path = (
            REPO_ROOT / "artifacts" / "frozen_models" / model_id / "metadata.json"
        )
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            raw_target = (payload.get("label_spec") or {}).get("target_drawdown")
            if raw_target is None:
                return ACTIVE_TARGET_DRAWDOWN
            value = float(raw_target)
            if 0.0 < value < 1.0:
                return value
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
    return ACTIVE_TARGET_DRAWDOWN

data_dir_path = _settings.paths.data_dir
HEARTBEAT_PATH = data_dir_path / "scanner_heartbeat.json"
CANDIDATE_SNAPSHOT_PATH = data_dir_path / "candidate_snapshot.json"
CANDIDATE_FILTER_COMPARISON_PATH = (
    Path(_settings.candidate_comparison.snapshot_path)
    if _settings.candidate_comparison.snapshot_path is not None
    else data_dir_path / "candidate_filter_comparison.json"
)
SYSTEM_STATS_PATH = data_dir_path / "system_data_stats.json"
TRIGGER_PATH = data_dir_path / "scanner_trigger.flag"
RUNTIME_STATE_PATH = data_dir_path / "scanner_runtime_state.json"
TRACKING_WATCHLIST_PATH = data_dir_path / "tracking_watchlist.json"

_alert_store = AlertStore(
    str(_settings.scanner.db_path),
    read_only=True,
    prefer_snapshot=True,
)
_scan_store = ScanResultStore(
    str(_settings.scanner.db_path),
    read_only=True,
    prefer_snapshot=True,
)
_tracking_store = TrackingWatchlistStore(TRACKING_WATCHLIST_PATH)
_dismissals = SignalDismissals(data_dir_path / "signal_dismissals.json")
_notifier = TelegramNotifier(
    _settings.telegram,
    web_base_url=_settings.web.public_url,
)
_STATUS_CACHE_LOCK = threading.Lock()
_STATUS_CACHE: dict[str, Any] = {}
_STATUS_RESP_CACHE: dict[str, Any] = {}
_STATUS_RESP_TIME: float = 0.0
_SIGNALS_RESP_CACHE: list[dict[str, Any]] = []
_SIGNALS_RESP_TIME: float = 0.0
_MARKET_CAP_CACHE_LOCK = threading.Lock()
_MARKET_CAP_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_MARKET_CAP_FAILURE_TTL_SECONDS = 60.0
_MARKET_CAP_LOOKUP_QUEUE: Queue[tuple[str, float | None]] = Queue(maxsize=200)
_MARKET_CAP_LOOKUP_PENDING: set[str] = set()
_MARKET_CAP_LOOKUP_WORKERS_STARTED = False
_MARKET_CAP_LOOKUP_WORKER_COUNT = 4
_MARKET_CAP_CANDIDATE_PREFETCH_LIMIT = 30
_DISK_CRITICAL_USED_PERCENT = 90.0
_DISK_MIN_FREE_BYTES = 5 * 1024**3


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _disk_readiness(path: Path) -> dict[str, Any]:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        usage = shutil.disk_usage(probe)
    except OSError:
        return {
            "healthy": False,
            "status": "error",
            "reason": "disk_unavailable",
            "used_percent": None,
            "free_bytes": None,
        }
    used_percent = (
        ((usage.total - usage.free) / usage.total) * 100
        if usage.total
        else 100.0
    )
    healthy = (
        used_percent < _DISK_CRITICAL_USED_PERCENT
        and usage.free >= _DISK_MIN_FREE_BYTES
    )
    return {
        "healthy": healthy,
        "status": "ok" if healthy else "error",
        "reason": "ok" if healthy else "disk_space_critical",
        "used_percent": round(used_percent, 1),
        "free_bytes": usage.free,
    }


def _fetch_live_regime(limit: int = 100) -> dict[str, Any]:
    """Return a real BTC regime snapshot or raise when upstream data is unusable."""
    import pandas as pd

    from dao_vang.alpha_lab.regime_classifier import get_current_regime
    from dao_vang.data.collectors.binance_client import BinanceClient

    klines = BinanceClient().get(
        "/fapi/v1/klines",
        {"symbol": "BTCUSDT", "interval": "1h", "limit": limit},
    )
    if not isinstance(klines, list) or len(klines) < 20:
        raise RuntimeError("insufficient_binance_klines")

    frame = pd.DataFrame(
        klines,
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trades",
            "taker_buy_base",
            "taker_buy_quote",
            "ignore",
        ],
    )
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms")
    frame = frame.set_index("open_time")
    for column in ("open", "high", "low", "close"):
        frame[column] = frame[column].astype(float)

    state = get_current_regime(frame)
    timestamp = (
        state.timestamp.isoformat()
        if hasattr(state.timestamp, "isoformat")
        else str(state.timestamp)
    )
    regime = state.regime.value
    label_vi = {
        "SIDEWAY_DISTRIBUTION": "Đi ngang / phân phối",
        "TRENDING_BEAR": "Xu hướng giảm",
        "TRENDING_BULL": "Xu hướng tăng",
        "HIGH_VOLATILITY": "Biến động cao",
    }.get(regime, regime)
    label_en = {
        "SIDEWAY_DISTRIBUTION": "Sideways / Distribution",
        "TRENDING_BEAR": "Trending Bear",
        "TRENDING_BULL": "Trending Bull",
        "HIGH_VOLATILITY": "High Volatility",
    }.get(regime, regime)
    return {
        "available": True,
        "source": "binance_futures_btcusdt_1h",
        "symbol": "BTCUSDT",
        "timestamp": timestamp,
        "regime": regime,
        "regime_label_vi": label_vi,
        "regime_label_en": label_en,
        "adx": round(state.adx, 2),
        "bb_width": round(state.bb_width, 4),
        "trend_slope": round(state.trend_slope, 4),
        "atr_pct": round(state.atr_pct, 4),
        "allow_short": state.allow_short,
        "allow_long": state.allow_long,
        "risk_multiplier": round(state.risk_multiplier, 2),
    }


def _system_history_timestamp(value: Any) -> str | None:
    """Serialize timestamps as unambiguous Vietnam-time ISO strings.

    DuckDB commonly returns naive ``datetime`` objects for TIMESTAMP columns.
    The pipeline stores those values in UTC, so attach UTC explicitly and
    expose the result as ``Asia/Ho_Chi_Minh`` instead of leaving the browser
    to guess a local timezone.
    """
    return system_iso(value)


def _as_utc_datetime(value: Any) -> datetime | None:
    """Normalize a database timestamp for event ordering."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _system_display_datetime(value: Any) -> datetime | None:
    """Return a timestamp as an aware UTC+7 datetime for human display."""
    utc_value = _as_utc_datetime(value)
    return as_system_timezone(utc_value) if utc_value is not None else None


def _anomaly_fields(row: dict[str, Any] | None) -> dict[str, Any]:
    """Return the stable anomaly payload used by candidates and signals.

    The JSON column was added after the first scan schema.  Keep the API
    tolerant of legacy rows so an upgrade can show the existing radar while
    the scanner publishes the first enriched cycle.
    """

    source = row or {}
    report: dict[str, Any] = {}
    raw_report = source.get("anomalies_json")
    if isinstance(raw_report, str):
        try:
            parsed = json.loads(raw_report)
            if isinstance(parsed, dict):
                report = parsed
        except (json.JSONDecodeError, TypeError):
            report = {}
    elif isinstance(raw_report, dict):
        report = raw_report

    raw_items = report.get("anomalies", [])
    anomalies = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
    raw_categories = report.get("categories", [])
    categories = (
        [str(item) for item in raw_categories if item]
        if isinstance(raw_categories, list)
        else []
    )
    if not categories:
        categories = list(dict.fromkeys(str(item.get("category")) for item in anomalies if item.get("category")))

    try:
        anomaly_score = float(source.get("anomaly_score", report.get("score", 0.0)) or 0.0)
    except (TypeError, ValueError):
        anomaly_score = 0.0
    anomaly_level = str(source.get("anomaly_level") or report.get("level") or "NORMAL")
    try:
        anomaly_count = int(source.get("anomaly_count", len(anomalies)) or len(anomalies))
    except (TypeError, ValueError):
        anomaly_count = len(anomalies)
    codes = {str(item.get("code", "")) for item in anomalies}
    return {
        "anomaly_score": anomaly_score,
        "anomaly_level": anomaly_level,
        "anomaly_count": max(0, anomaly_count),
        "anomaly_categories": categories,
        "anomalies": anomalies,
        "is_volume_spike": "volume_spike" in codes,
    }


def _build_market_cap_info(
    symbol: str,
    volume_24h_usd: float | None = None,
    market_cap_usd: float | None = None,
    source: str | None = None,
    updated_at: str | None = None,
    slug: str | None = None,
    name: str | None = None,
    cmc_url: str | None = None,
) -> dict[str, Any]:
    """Build a market-cap payload with CoinMarketCap metadata and NO fabrication."""
    try:
        supplied_mcap = float(market_cap_usd) if market_cap_usd is not None else None
    except (TypeError, ValueError):
        supplied_mcap = None

    from dao_vang.data.collectors.coinmarketcap import resolve_token_meta
    meta = resolve_token_meta(symbol)
    resolved_slug = slug or meta.get("slug")
    resolved_name = name or meta.get("name")
    resolved_url = cmc_url or meta.get("cmc_url")
        
    if supplied_mcap is None or not math.isfinite(supplied_mcap) or supplied_mcap <= 0:
        return {
            "market_cap_usd": None,
            "market_cap_str": "N/A",
            "market_cap_tier": "UNKNOWN",
            "market_cap_source": "unavailable",
            "market_cap_is_estimate": False,
            "market_cap_updated_at": updated_at,
            "cmc_slug": resolved_slug,
            "cmc_name": resolved_name,
            "cmc_url": resolved_url,
        }

    mcap = supplied_mcap
    resolved_source = source or "coinmarketcap"

    if mcap >= 5_000_000_000:
        tier = "LARGE"
    elif mcap >= 1_000_000_000:
        tier = "MID"
    elif mcap >= 10_000_000:
        tier = "SMALL"
    else:
        tier = "MICRO"

    if mcap >= 1_000_000_000_000:
        mcap_str = f"${mcap / 1_000_000_000_000:.2f}T"
    elif mcap >= 1_000_000_000:
        mcap_str = f"${mcap / 1_000_000_000:.1f}B"
    elif mcap >= 1_000_000:
        mcap_str = f"${mcap / 1_000_000:.0f}M"
    else:
        mcap_str = f"${mcap:,.0f}"

    return {
        "market_cap_usd": mcap,
        "market_cap_str": mcap_str,
        "market_cap_tier": tier,
        "market_cap_source": resolved_source,
        "market_cap_is_estimate": False,
        "market_cap_updated_at": updated_at,
        "cmc_slug": resolved_slug,
        "cmc_name": resolved_name,
        "cmc_url": resolved_url,
    }


def _resolve_market_cap_info(
    symbol: str,
    volume_24h_usd: float | None = None,
    *,
    fetch_remote: bool = False,
) -> dict[str, Any]:
    """Return cached CoinMarketCap data or an unavailable payload."""
    fallback = _build_market_cap_info(symbol, volume_24h_usd)
    cache_key = str(symbol or "").upper().replace("USDT", "").replace("BUSD", "").replace("USDC", "").replace("PERP", "").strip()
    now_monotonic = time.monotonic()
    with _MARKET_CAP_CACHE_LOCK:
        cached = _MARKET_CAP_CACHE.get(cache_key)
        if cached and cached[0] > now_monotonic:
            return dict(cached[1])

    cmc_cfg = getattr(_settings, "coinmarketcap", None)
    cmc_enabled = cmc_cfg.enabled if cmc_cfg else False
    agent_os_cfg = getattr(_settings, "binance_agent_os", None)
    agent_os_enabled = agent_os_cfg.enabled if agent_os_cfg else False

    if not fetch_remote or (not cmc_enabled and not agent_os_enabled):
        return fallback

    info = fallback
    ttl_seconds = _MARKET_CAP_FAILURE_TTL_SECONDS
    fetched = False

    if cmc_enabled and cmc_cfg is not None:
        try:
            from dao_vang.data.collectors.coinmarketcap import fetch_market_data

            cmc_data = fetch_market_data(symbol, cmc_cfg)
            if cmc_data and cmc_data.market_cap_usd and cmc_data.market_cap_usd > 0:
                info = _build_market_cap_info(
                    symbol,
                    volume_24h_usd,
                    market_cap_usd=cmc_data.market_cap_usd,
                    source="coinmarketcap",
                    updated_at=_system_history_timestamp(datetime.now(timezone.utc)),
                    slug=cmc_data.slug,
                    name=cmc_data.name,
                    cmc_url=cmc_data.cmc_url,
                )
                ttl_seconds = max(
                    60.0,
                    float(cmc_cfg.cache_minutes) * 60.0,
                )
                fetched = True
            elif cmc_data:
                info = _build_market_cap_info(
                    symbol,
                    volume_24h_usd,
                    slug=cmc_data.slug,
                    name=cmc_data.name,
                    cmc_url=cmc_data.cmc_url,
                )
        except Exception as exc:
            logger.warning("cmc_market_cap_lookup_failed symbol=%s error=%s", symbol, exc)

    if not fetched and agent_os_enabled and agent_os_cfg is not None:
        try:
            from dao_vang.data.collectors.binance_agent_os import fetch_market_cap

            market_cap_usd = fetch_market_cap(symbol, agent_os_cfg)
            if market_cap_usd is not None and market_cap_usd > 0:
                info = _build_market_cap_info(
                    symbol,
                    volume_24h_usd,
                    market_cap_usd=market_cap_usd,
                    source="binance_agent_os",
                    updated_at=_system_history_timestamp(datetime.now(timezone.utc)),
                )
                ttl_seconds = max(
                    60.0,
                    float(agent_os_cfg.cache_minutes) * 60.0,
                )
        except Exception as exc:
            logger.warning("market_cap_lookup_failed symbol=%s error=%s", symbol, exc)

    with _MARKET_CAP_CACHE_LOCK:
        _MARKET_CAP_CACHE[cache_key] = (now_monotonic + ttl_seconds, dict(info))
    return info


def _market_cap_lookup_worker() -> None:
    """Resolve queued market caps without delaying candidate responses."""
    while True:
        symbol, volume_24h_usd = _MARKET_CAP_LOOKUP_QUEUE.get()
        cache_key = str(symbol or "").upper().replace("USDT", "").replace("BUSD", "").replace("USDC", "").replace("PERP", "").strip()
        try:
            _resolve_market_cap_info(
                symbol,
                volume_24h_usd,
                fetch_remote=True,
            )
        except Exception as exc:
            logger.warning("market_cap_background_lookup_failed symbol=%s error=%s", symbol, exc)
        finally:
            with _MARKET_CAP_CACHE_LOCK:
                _MARKET_CAP_LOOKUP_PENDING.discard(cache_key)
            _MARKET_CAP_LOOKUP_QUEUE.task_done()


def _schedule_market_cap_lookup(
    symbol: str,
    volume_24h_usd: float | None = None,
) -> bool:
    """Queue one deduplicated lookup; return whether it was newly queued."""
    global _MARKET_CAP_LOOKUP_WORKERS_STARTED

    cmc_cfg = getattr(_settings, "coinmarketcap", None)
    cmc_enabled = cmc_cfg.enabled if cmc_cfg else False
    agent_os_cfg = getattr(_settings, "binance_agent_os", None)
    agent_os_enabled = agent_os_cfg.enabled if agent_os_cfg else False
    if not cmc_enabled and not agent_os_enabled:
        return False

    cache_key = str(symbol or "").upper().replace("USDT", "").replace("BUSD", "").replace("USDC", "").replace("PERP", "").strip()
    if not cache_key:
        return False

    now_monotonic = time.monotonic()
    start_workers = False
    with _MARKET_CAP_CACHE_LOCK:
        cached = _MARKET_CAP_CACHE.get(cache_key)
        if cached and cached[0] > now_monotonic:
            return False
        if cache_key in _MARKET_CAP_LOOKUP_PENDING:
            return False
        _MARKET_CAP_LOOKUP_PENDING.add(cache_key)
        if not _MARKET_CAP_LOOKUP_WORKERS_STARTED:
            _MARKET_CAP_LOOKUP_WORKERS_STARTED = True
            start_workers = True

    if start_workers:
        for worker_index in range(_MARKET_CAP_LOOKUP_WORKER_COUNT):
            threading.Thread(
                target=_market_cap_lookup_worker,
                name=f"market-cap-{worker_index + 1}",
                daemon=True,
            ).start()

    try:
        _MARKET_CAP_LOOKUP_QUEUE.put_nowait((symbol, volume_24h_usd))
    except Full:
        with _MARKET_CAP_CACHE_LOCK:
            _MARKET_CAP_LOOKUP_PENDING.discard(cache_key)
        return False
    return True


def _build_signal_trade_setup(
    close_price: float,
    prob: float = 0.0,
    components: list[dict[str, Any]] | None = None,
    target_drawdown: float = ACTIVE_TARGET_DRAWDOWN,
    features: dict[str, Any] | None = None,
    anomalies: list[dict[str, Any]] | None = None,
    quality_score: float | None = None,
    signal_score: float | None = None,
    volume_24h_usd: float | None = None,
    label_version: str | None = None,
) -> dict[str, Any]:
    if not close_price or close_price <= 0:
        return {
            "entry_price": 0.0,
            "entry_zone": "$0.00",
            "stop_loss": 0.0,
            "stop_loss_pct": 0.0,
            "tp1": 0.0,
            "tp1_pct": 8.0,
            "tp2": 0.0,
            "tp2_pct": 20.0,
            "tp3": 0.0,
            "tp3_pct": 30.0,
            "rr_ratio": 0.0,
        }
    target_fraction = abs(float(target_drawdown))
    if target_fraction > 1.0:
        target_fraction /= 100.0
    feature_values = dict(features or {})
    if components:
        feature_values["component_count"] = len(components)
    return build_trade_setup(
        signal_price=float(close_price),
        context=PolicyContext(
            signal_probability=prob,
            label_version=label_version,
            signal_score=signal_score,
            quality_score=quality_score,
            volume_24h_usd=volume_24h_usd,
            features=feature_values,
            anomalies=tuple(anomalies or ()),
        ),
        config=_settings.execution_policy,
        target_drawdown=target_fraction,
    )


def _apply_stored_execution_policy(
    trade_setup: dict[str, Any],
    raw_policy: Any,
) -> dict[str, Any]:
    """Prefer the immutable signal-time policy over a config-time recomputation."""

    if not raw_policy:
        return trade_setup
    try:
        policy = (
            json.loads(raw_policy)
            if isinstance(raw_policy, str)
            else dict(raw_policy)
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return trade_setup
    legs = policy.get("entry_legs")
    if not isinstance(legs, list) or not legs:
        return trade_setup
    try:
        average = float(policy["projected_average_entry"])
        target = float(policy["projected_target_price"])
        stop = float(policy["hard_stop_price"])
        target_pct = float(policy["target_drawdown_pct"])
        stop_pct = float(policy["hard_stop_pct"])
    except (KeyError, TypeError, ValueError):
        return trade_setup
    return {
        **trade_setup,
        "entry_price": float(legs[0]["price"]),
        "entry_zone": " / ".join(
            f"${float(leg['price']):.6g}" for leg in legs
        ),
        "stop_loss": stop,
        "stop_loss_pct": stop_pct,
        "tp1": round(average * 0.92, 8),
        "tp1_pct": 8.0,
        "tp2": target,
        "tp2_pct": target_pct,
        "tp3": round(average * 0.70, 8),
        "tp3_pct": 30.0,
        "rr_ratio": policy.get("projected_rr_ratio"),
        "target_basis": "weighted_average_after_each_fill",
        "entry_legs": legs,
        "projected_average_entry": average,
        "projected_stop_risk_pct": policy.get("projected_stop_risk_pct"),
        "execution_policy": policy,
    }


def _build_signal_trigger_pattern(
    components: list[dict[str, Any]],
    anomalies: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    if anomalies:
        for a in anomalies:
            code = a.get("code")
            if code == "funding_trap":
                return "Extreme Funding Rate Trap", "Bẫy Funding Rate Cực Đại"
            if code == "oi_divergence":
                return "Bearish OI Divergence", "Phân kỳ Đảo chiều Open Interest"
            if code == "volume_spike":
                return "Climax Volume Exhaustion", "Bùng nổ Volume Xả Đỉnh"
            if code == "reversal_rsi":
                return "Overbought RSI Divergence", "Phân kỳ RSI Quá mua"
    return "Multi-Factor Distribution Peak", "Cụm Đa Yếu Tố Phân Phối Đỉnh"


def _build_signal_outcomes(
    hit: bool | None,
    validity_hours_left: float,
) -> tuple[str, float | None, float | None]:
    if hit is True:
        return "TARGET_HIT", None, None
    if hit is False:
        return "EXPIRED", None, None
    if validity_hours_left <= 0:
        return "EXPIRED", None, None
    return "ACTIVE", None, None


FundingPoint = tuple[int, float]
DEFAULT_FUNDING_INTERVAL_HOURS = 8.0


def _parse_funding_history(payload: Any) -> list[FundingPoint]:
    """Return valid Binance funding events sorted by funding timestamp."""

    if not isinstance(payload, list):
        return []

    points: dict[int, float] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            funding_time = int(item["fundingTime"])
            funding_rate = float(item["fundingRate"])
        except (KeyError, TypeError, ValueError):
            continue
        if funding_time < 0 or not math.isfinite(funding_rate):
            continue
        points[funding_time] = funding_rate
    return sorted(points.items())


def _parse_live_funding(payload: Any, symbol: str) -> tuple[float | None, int | None, int | None]:
    """Extract the latest rate and next funding time from Binance premiumIndex."""

    item: dict[str, Any] | None = None
    if isinstance(payload, dict):
        payload_symbol = str(payload.get("symbol", "")).upper()
        if not payload_symbol or payload_symbol == symbol.upper():
            item = payload
    elif isinstance(payload, list):
        item = next(
            (
                candidate
                for candidate in payload
                if isinstance(candidate, dict)
                and str(candidate.get("symbol", "")).upper() == symbol.upper()
            ),
            None,
        )
    if item is None:
        return None, None, None

    try:
        rate = float(item["lastFundingRate"])
        if not math.isfinite(rate):
            rate = None
    except (KeyError, TypeError, ValueError):
        rate = None

    def _timestamp(name: str) -> int | None:
        try:
            value = int(item[name])
        except (KeyError, TypeError, ValueError):
            return None
        return value if value >= 0 else None

    return rate, _timestamp("nextFundingTime"), _timestamp("time")


def _parse_funding_interval_info(payload: Any, symbol: str) -> float | None:
    """Read Binance's explicit non-standard funding cadence for a symbol."""

    items: list[Any]
    if isinstance(payload, dict):
        items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        return None

    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("symbol", "")).upper() != symbol.upper():
            continue
        try:
            interval_hours = float(item["fundingIntervalHours"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 < interval_hours <= 24 and math.isfinite(interval_hours):
            return round(interval_hours, 2)
    return None


def _infer_funding_interval_ms(points: list[FundingPoint]) -> int | None:
    """Infer the symbol's funding cadence from observed settlement events."""

    deltas = [current[0] - previous[0] for previous, current in zip(points, points[1:])]
    positive_deltas = sorted(delta for delta in deltas if delta > 0)
    if not positive_deltas:
        return None
    return positive_deltas[len(positive_deltas) // 2]


def _funding_asof(
    points: list[FundingPoint],
    timestamp_ms: int,
    *,
    max_age_ms: int | None = None,
) -> tuple[float, int] | None:
    """Find the most recent funding event known at ``timestamp_ms``.

    Funding must never be taken from a future settlement event.  ``max_age_ms``
    is optional so callers can explicitly mark an old feed as unavailable.
    """

    eligible = [point for point in points if point[0] <= timestamp_ms]
    if not eligible:
        return None
    funding_time, funding_rate = eligible[-1]
    if max_age_ms is not None and timestamp_ms - funding_time > max_age_ms:
        return None
    return funding_rate, funding_time


def _format_funding_rate(rate: float | None) -> str:
    """Format Binance's decimal funding rate as a percentage or N/A."""

    return f"{rate:+.3%}" if rate is not None and math.isfinite(rate) else "N/A"


def _funding_apr(rate: float | None, interval_hours: float | None) -> float | None:
    """Annualize a per-settlement funding rate using a simple APR convention."""

    if rate is None or interval_hours is None or interval_hours <= 0:
        return None
    apr = rate * (365.0 * 24.0 / interval_hours)
    return apr if math.isfinite(apr) else None


def _funding_payer(rate: float | None) -> str:
    """Return the side that pays the funding transfer for a signed rate."""

    if rate is None:
        return "unknown"
    if rate > 0:
        return "long"
    if rate < 0:
        return "short"
    return "none"


def _ro_duckdb_connect(db_path: str) -> duckdb.DuckDBPyConnection:
    """Open a read-only connection with the shared, bounded lock fallback."""

    return open_read_only_connection(db_path, prefer_snapshot=True)


def _self_learning_status() -> dict[str, Any]:
    """Return the read-only progress snapshot used by the HISTORY tab.

    The scanner owns the live DuckDB writer, so this endpoint deliberately
    uses the same read-only/copy fallback as the rest of the API.  Reports are
    small JSON artifacts written atomically by the self-learning runner; a
    partially written or old report is ignored rather than breaking the tab.
    """
    cfg = _settings.self_learning
    state = _read_json(Path(cfg.state_path))
    recent_runs: list[dict[str, Any]] = []

    try:
        report_paths = sorted(
            Path(cfg.report_dir).glob("selflearn_*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )[:10]
        for report_path in report_paths:
            report = _read_json(report_path)
            if report:
                recent_runs.append(report)
    except (OSError, ValueError) as exc:
        logger.debug("self_learning_reports_unavailable error=%s", exc)

    stats = {
        "predictions": 0,
        "outcomes": 0,
        "pending": 0,
        "excluded": 0,
        "materialized_positive": 0,
        "training_outcomes": int(state.get("training_outcomes", 0) or state.get("last_training_outcome_count", 0) or 0),
        "historical_outcomes": int(state.get("historical_outcomes", 0) or 0),
        "live_outcomes": int(state.get("live_outcomes", 0) or 0),
        "training_positive_events": int(state.get("training_positive_events", 0) or 0),
        "recent_outcomes": int(state.get("recent_outcomes", 0) or 0),
        "latest_outcome_time": None,
    }

    if not cfg.enabled:
        return {
            "enabled": False,
            "check_interval_cycles": int(cfg.check_interval_cycles),
            "status": "disabled",
            "champion_model_id": _settings.scanner.frozen_model_id or "",
            "current_scanner_model_id": _settings.scanner.frozen_model_id or "",
            **stats,
            "new_outcomes": 0,
            "min_training_outcomes": int(cfg.min_training_outcomes),
            "min_new_outcomes": int(cfg.min_new_outcomes),
            "min_positive_events": int(cfg.min_positive_events),
            "recent_window_days": int(cfg.recent_window_days),
            "recent_runs": recent_runs,
        }

    horizon_hours = 24
    try:
        from dao_vang.experiments.forward_test import load_frozen_model

        champion = load_frozen_model(
            _settings.scanner.frozen_model_id or "",
            Path(_settings.scanner.artifact_dir),
        )
        horizon_hours = int((champion.label_spec or {}).get("horizon_hours", 24))
    except (FileNotFoundError, OSError, ValueError):
        pass
    conn = None
    try:
        conn = _ro_duckdb_connect(str(_settings.scanner.db_path))
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='main' AND table_type='BASE TABLE'"
            ).fetchall()
        }
        if "predictions" in tables:
            prediction_row = conn.execute(
                "SELECT count(*) FROM predictions"
            ).fetchone()
            stats["predictions"] = (
                int(prediction_row[0] or 0) if prediction_row is not None else 0
            )
        if "prediction_outcomes" in tables:
            outcome_row = conn.execute(
                """
                SELECT count(*),
                       count(*) FILTER (WHERE label_value IS NULL),
                       count(*) FILTER (WHERE outcome_status = 'materialized' AND label_value = 1),
                       max(materialized_at) FILTER (WHERE outcome_status = 'materialized')
                FROM prediction_outcomes
                """
            ).fetchone()
            if outcome_row is not None:
                stats["outcomes"] = int(outcome_row[0] or 0)
                stats["excluded"] = int(outcome_row[1] or 0)
                stats["materialized_positive"] = int(outcome_row[2] or 0)
                stats["latest_outcome_time"] = _system_history_timestamp(
                    outcome_row[3]
                )
                stats["live_outcomes"] = int(outcome_row[0] or 0)
        if {"predictions", "prediction_outcomes"}.issubset(tables):
            pending_row = conn.execute(
                """
                SELECT count(*)
                FROM predictions p
                LEFT JOIN prediction_outcomes o
                  ON o.prediction_id = p.prediction_id
                WHERE p.invalidation_time IS NOT NULL
                  AND p.invalidation_time <= CURRENT_TIMESTAMP
                  AND o.prediction_id IS NULL
                """
            ).fetchone()
            stats["pending"] = (
                int(pending_row[0] or 0) if pending_row is not None else 0
            )
        if "labels" in tables and stats["historical_outcomes"] == 0:
            historical_row = conn.execute(
                "SELECT count(*) FROM labels WHERE horizon_hours = ? AND label_value IN (0, 1)",
                [int(horizon_hours)],
            ).fetchone()
            stats["historical_outcomes"] = (
                int(historical_row[0] or 0) if historical_row is not None else 0
            )
        if stats["training_outcomes"] == 0:
            stats["training_outcomes"] = stats["historical_outcomes"] + stats["live_outcomes"]
        if stats["training_positive_events"] == 0 and "labels" in tables:
            positive_row = conn.execute(
                "SELECT count(*) FROM labels WHERE horizon_hours = ? AND label_value = 1",
                [int(horizon_hours)],
            ).fetchone()
            stats["training_positive_events"] = (
                int(positive_row[0] or 0) if positive_row is not None else 0
            )
    except Exception as exc:
        logger.warning("self_learning_stats_failed error=%s", exc)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    min_training = int(cfg.min_training_outcomes)
    min_positive = int(cfg.min_positive_events)
    min_new = int(cfg.min_new_outcomes)
    last_training_count = int(state.get("last_training_outcome_count", 0) or 0)
    persisted_status = str(state.get("last_status") or "")
    if not cfg.enabled:
        status = "disabled"
    elif persisted_status:
        status = persisted_status
    elif (
        stats["training_outcomes"] < min_training
        or stats["training_positive_events"] < min_positive
    ):
        status = "not_ready"
    else:
        status = "waiting_new_outcomes"

    return {
        "enabled": bool(cfg.enabled),
        "check_interval_cycles": int(cfg.check_interval_cycles),
        "status": status,
        "champion_model_id": _settings.scanner.frozen_model_id or "",
        "current_scanner_model_id": _settings.scanner.frozen_model_id or "",
        **stats,
        "new_outcomes": max(
            0, stats["training_outcomes"] - last_training_count
        ),
        "min_training_outcomes": min_training,
        "min_new_outcomes": min_new,
        "min_positive_events": min_positive,
        "recent_window_days": int(cfg.recent_window_days),
        "recent_sample_weight": float(cfg.recent_sample_weight),
        "historical_max_rows": int(cfg.historical_max_rows),
        "last_run_at": state.get("last_run_at"),
        "last_training_outcome_count": last_training_count or None,
        "last_report_path": state.get("last_report_path"),
        "last_challenger_model_id": state.get("last_challenger_model_id"),
        "latest_run": recent_runs[0] if recent_runs else None,
        "recent_runs": recent_runs,
    }


def _current_scan_modes() -> list[str]:
    state = _read_json(RUNTIME_STATE_PATH)
    raw_modes = state.get("scan_modes", state.get("scan_mode", _settings.scanner.scan_mode))
    return normalize_scan_modes(raw_modes)


def _current_scan_mode() -> str:
    """Return the legacy display form while supporting multiple modes."""
    return ",".join(_current_scan_modes())


def _request_scan(modes: list[str] | None = None) -> dict[str, Any]:
    """Ask the running ScannerDaemon to run a cycle immediately.

    Writes a flag file the daemon polls between cycles instead of running a
    scan inline in this HTTP handler — the daemon is a separate long-running
    process holding the Binance client / DuckDB write connection.

    A plain refresh requested while a healthy cycle is already running is
    coalesced into that cycle.  Otherwise every click during a 1-2 minute scan
    would leave a flag behind and force an unnecessary second cycle (and could
    duplicate Telegram reports).  Mode changes are never coalesced because the
    running cycle cannot observe the new mode until its successor.
    """
    TRIGGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"requested_at": system_now().isoformat()}
    if modes:
        normalized_modes = normalize_scan_modes(modes)
        state = _read_json(RUNTIME_STATE_PATH)
        # Keep both keys during the migration: old daemons read scan_mode,
        # while current clients use the explicit list.
        state["scan_modes"] = normalized_modes
        state["scan_mode"] = ",".join(normalized_modes)
        RUNTIME_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        RUNTIME_STATE_PATH.write_text(json.dumps(state), encoding="utf-8")
        payload["scan_modes"] = normalized_modes
        payload["scan_mode"] = ",".join(normalized_modes)
    elif _scanner_cycle_is_running():
        heartbeat = _read_json(HEARTBEAT_PATH)
        return {
            "status": "in_progress",
            "queued": False,
            "cycle": heartbeat.get("cycle"),
            "started_at": heartbeat.get("last_cycle_started_at"),
        }
    TRIGGER_PATH.write_text(json.dumps(payload), encoding="utf-8")
    return {"status": "queued", "queued": True}


def _scanner_cycle_is_running() -> bool:
    """Return true only for a fresh heartbeat from an active scan cycle."""

    heartbeat = _read_json(HEARTBEAT_PATH)
    if heartbeat.get("last_cycle_status") != "running":
        return False
    heartbeat_at = _as_utc_datetime(heartbeat.get("timestamp"))
    if heartbeat_at is None:
        return False
    freshness_limit = timedelta(
        minutes=max(2 * _settings.scanner.poll_interval_minutes, 10)
    )
    return datetime.now(timezone.utc) - heartbeat_at <= freshness_limit


def _risk_bucket(score: float) -> str:
    if score >= 85:
        return "CRITICAL"
    if score >= 70:
        return "HIGH"
    if score >= 50:
        return "MEDIUM"
    return "SAFE"


def _scan_risk_level(recommendation: Any, probability: float) -> str:
    """Map the scanner's model tier to the Radar UI vocabulary."""

    tier = str(recommendation or "").upper()
    return {
        "HIGH_CONFIDENCE": "HIGH",
        "WATCH": "MEDIUM",
        "WAIT": "SAFE",
    }.get(tier, _risk_bucket(probability * 100.0))


def _component_weighted_score(component: dict[str, Any]) -> float:
    try:
        score = float(component.get("weighted_score", 0.0))
    except (TypeError, ValueError):
        return 0.0
    return score if math.isfinite(score) else 0.0


def _component_feature_drivers(
    components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Expose weighted score components without claiming SHAP attribution."""

    drivers: list[dict[str, Any]] = []
    for component in sorted(
        components,
        key=_component_weighted_score,
        reverse=True,
    ):
        weighted_score = _component_weighted_score(component)
        name = str(component.get("name") or "unknown")
        drivers.append(
            {
                "feature": name.replace("_", " ").title(),
                "impact_score": weighted_score / 100.0,
                "description": str(component.get("explanation") or ""),
            }
        )
    return drivers


class APIHandler(BaseHTTPRequestHandler):
    # NOTE: handlers below send responses without a Content-Length header
    # (and without chunked transfer-encoding). Under HTTP/1.1 the connection
    # stays open (keep-alive) after end_headers(), so a client has no way to
    # know where the body ends -> fetch()/curl hang forever waiting for more
    # bytes, which is why the frontend gets stuck on "loading" with a blank
    # screen. HTTP/1.0 makes the server close the socket after every
    # response, which lets clients detect end-of-body via connection close.
    protocol_version = 'HTTP/1.0'

    def _set_headers(self, status=200, content_type='application/json; charset=utf-8', cache_control='no-store, no-cache, must-revalidate, max-age=0', content_length=None, extra_headers=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        if cache_control:
            self.send_header('Cache-Control', cache_control)
        if content_length is not None:
            self.send_header('Content-Length', str(content_length))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Connection', 'close')
        origin = self.headers.get('Origin', '')
        if origin and origin in _settings.web.allowed_origins:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Credentials', 'true')
            self.send_header('Access-Control-Allow-Methods', 'GET, HEAD, POST, PATCH, DELETE, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.send_header('Vary', 'Origin')
        self.end_headers()

    def _auth_secret(self) -> str:
        return (_settings.web.access_password or '').strip()

    def _make_session_token(self) -> str:
        """Create a short-lived signed token that never contains the password."""

        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(18)
        payload = f'{timestamp}.{nonce}'
        signature = hmac.new(
            self._auth_secret().encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256,
        ).digest()
        encoded_signature = base64.urlsafe_b64encode(signature).decode('ascii').rstrip('=')
        return f'{payload}.{encoded_signature}'

    def _is_valid_session_token(self, token: str) -> bool:
        if not token or not self._auth_secret():
            return False
        parts = token.split('.', 2)
        if len(parts) != 3:
            return False
        timestamp, nonce, supplied_signature = parts
        if not timestamp.isdigit() or not nonce or not supplied_signature:
            return False
        issued_at = int(timestamp)
        now = int(time.time())
        ttl = int(_settings.web.auth_session_ttl_seconds)
        if issued_at > now + 60 or now - issued_at > ttl:
            return False
        payload = f'{timestamp}.{nonce}'
        expected_signature = base64.urlsafe_b64encode(
            hmac.new(
                self._auth_secret().encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256,
            ).digest()
        ).decode('ascii').rstrip('=')
        return hmac.compare_digest(supplied_signature, expected_signature)

    def _auth_client_key(self) -> str:
        client_address = getattr(self, 'client_address', None)
        if isinstance(client_address, tuple) and client_address:
            return str(client_address[0])
        return 'unknown'

    def _auth_rate_limited(self) -> bool:
        now = time.time()
        key = self._auth_client_key()
        attempts = [
            value for value in _AUTH_FAILURES.get(key, [])
            if now - value < _AUTH_FAILURE_WINDOW_SECONDS
        ]
        _AUTH_FAILURES[key] = attempts
        return len(attempts) >= _AUTH_FAILURE_LIMIT

    def _record_auth_failure(self) -> None:
        _AUTH_FAILURES.setdefault(self._auth_client_key(), []).append(time.time())

    def _clear_auth_failures(self) -> None:
        _AUTH_FAILURES.pop(self._auth_client_key(), None)

    def _check_auth(self) -> bool:
        """Verify only a signed, short-lived session cookie.

        Passwords in URLs, arbitrary headers and long-lived plaintext cookies
        are deliberately rejected because they leak through logs, proxies and
        browser storage.
        """

        if not self._auth_secret():
            return False
        try:
            cookie = SimpleCookie(self.headers.get('Cookie', ''))
            session = cookie.get('dao_vang_session')
            return session is not None and self._is_valid_session_token(session.value)
        except Exception:
            return False

    def _send_unauthorized(self):
        err_body = json.dumps({
            "error": "Unauthorized",
            "auth_required": True,
            "message": "Vui lòng nhập mật khẩu hợp lệ để truy cập hệ thống.",
        }, ensure_ascii=False).encode("utf-8")
        self._set_headers(401, content_length=len(err_body))
        self.wfile.write(err_body)

    def get_auth_status(self):
        is_authenticated = self._check_auth()
        resp = {
            "auth_required": True,
            "auth_configured": bool(self._auth_secret()),
            "authenticated": is_authenticated,
        }
        body = json.dumps(resp).encode("utf-8")
        self._set_headers(200, content_length=len(body))
        self.wfile.write(body)

    def verify_auth_password(self, data: dict[str, Any]):
        password = str(data.get("password") or "").strip()
        if not self._auth_secret():
            resp = {
                "ok": False,
                "authenticated": False,
                "error": "Máy chủ chưa cấu hình mật khẩu truy cập.",
            }
            body = json.dumps(resp, ensure_ascii=False).encode("utf-8")
            self._set_headers(503, content_length=len(body))
            self.wfile.write(body)
            return

        if self._auth_rate_limited():
            resp = {
                "ok": False,
                "authenticated": False,
                "error": "Có quá nhiều lần thử. Vui lòng đợi vài phút rồi thử lại.",
            }
            body = json.dumps(resp, ensure_ascii=False).encode("utf-8")
            self._set_headers(429, content_length=len(body))
            self.wfile.write(body)
            return

        if hmac.compare_digest(password.encode('utf-8'), self._auth_secret().encode('utf-8')):
            self._clear_auth_failures()
            resp = {
                "ok": True,
                "authenticated": True,
                "message": "Xác thực thành công",
            }
            body = json.dumps(resp, ensure_ascii=False).encode("utf-8")
            secure = _settings.web.public_url.lower().startswith('https://') or self.headers.get('X-Forwarded-Proto', '').lower() == 'https'
            secure_attr = '; Secure' if secure else ''
            cookie_val = (
                f"dao_vang_session={self._make_session_token()}; Path=/; "
                f"HttpOnly; SameSite=Lax; Max-Age={int(_settings.web.auth_session_ttl_seconds)}{secure_attr}"
            )
            self._set_headers(200, content_length=len(body), extra_headers={"Set-Cookie": cookie_val})
            self.wfile.write(body)
        else:
            self._record_auth_failure()
            resp = {
                "ok": False,
                "authenticated": False,
                "error": "Mật khẩu không chính xác. Vui lòng thử lại.",
            }
            body = json.dumps(resp, ensure_ascii=False).encode("utf-8")
            self._set_headers(401, content_length=len(body))
            self.wfile.write(body)

    def logout_auth(self):
        body = json.dumps({"ok": True, "authenticated": False}).encode("utf-8")
        cookie_val = 'dao_vang_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0'
        self._set_headers(200, content_length=len(body), extra_headers={"Set-Cookie": cookie_val})
        self.wfile.write(body)

    def get_readiness(self):
        max_age_seconds = max(
            900.0,
            float((_settings.scanner.poll_interval_minutes * 2 + 5) * 60),
        )
        scanner = inspect_heartbeat(
            HEARTBEAT_PATH,
            max_age_seconds=max_age_seconds,
            snapshot_path=CANDIDATE_SNAPSHOT_PATH,
            stats_path=SYSTEM_STATS_PATH,
        )
        disk = _disk_readiness(data_dir_path)
        ready = bool(scanner["healthy"] and disk["healthy"])
        payload = {
            "status": "ok" if ready else "not_ready",
            "time": system_now().isoformat(),
            "checks": {
                "web": {"status": "ok"},
                "scanner": {
                    "status": "ok" if scanner["healthy"] else "error",
                    "reason": scanner["reason"],
                    "heartbeat_age_seconds": scanner["age_seconds"],
                    "last_cycle_status": scanner["last_cycle_status"],
                    "snapshot_age_seconds": scanner.get("snapshot_age_seconds"),
                },
                "disk": {
                    "status": disk["status"],
                    "reason": disk["reason"],
                    "used_percent": disk["used_percent"],
                    "free_bytes": disk["free_bytes"],
                },
            },
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._set_headers(200 if ready else 503, content_length=len(body))
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._set_headers(200)

    def do_HEAD(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == '/api/ready':
            max_age_seconds = max(
                900.0,
                float((_settings.scanner.poll_interval_minutes * 2 + 5) * 60),
            )
            scanner = inspect_heartbeat(
                HEARTBEAT_PATH,
                max_age_seconds=max_age_seconds,
            )
            disk = _disk_readiness(data_dir_path)
            self._set_headers(
                200 if scanner["healthy"] and disk["healthy"] else 503
            )
            return
        if path.startswith('/api/') and path not in ('/api/auth/status', '/api/auth/check', '/api/health'):
            if not self._check_auth():
                self._set_headers(401)
                return
        self._set_headers(200)

    def get_research_v3(self):
        snapshot = _settings.paths.data_dir / "research_v3" / "snapshot.json"
        result: dict[str, Any] = {"status": "waiting" if _settings.research_v3_enabled else "disabled",
                                  "items": [], "orders_enabled": False, "promotion_eligible": False}
        if _settings.research_v3_enabled and snapshot.exists():
            try:
                result = json.loads(snapshot.read_text(encoding="utf-8"))
                updated = datetime.fromisoformat(result["updated_at"])
                result["stale"] = (datetime.now(timezone.utc) - updated).total_seconds() > 900
            except (OSError, ValueError, TypeError, KeyError):
                result = {"status": "error", "items": [], "orders_enabled": False}
        discovery_path = snapshot.with_name("discovery.json")
        if _settings.research_v3_enabled and discovery_path.exists():
            try:
                discovery = json.loads(discovery_path.read_text(encoding="utf-8"))
                updated = datetime.fromisoformat(discovery["updated_at"])
                discovery["stale"] = (datetime.now(timezone.utc) - updated).total_seconds() > 900
                result["discovery"] = discovery
            except (OSError, ValueError, TypeError, KeyError):
                result["discovery"] = {"status": "error", "items": []}
        body = json.dumps(result).encode("utf-8")
        self._set_headers(200, content_length=len(body))
        self.wfile.write(body)

    def do_GET(self):
        """Serve GET requests without dropping the TCP connection on errors."""
        try:
            self._do_GET()
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            logger.warning("api_get_failed path=%s error=%s", self.path, exc)
            try:
                err_body = json.dumps({
                    "error": "service temporarily unavailable",
                }).encode("utf-8")
                self._set_headers(503, content_length=len(err_body))
                self.wfile.write(err_body)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    def _do_GET(self):
        parsed = urlparse(self.path)
        # self.path is percent-encoded as sent over the wire (e.g. browsers
        # percent-encode non-ASCII characters in fetch() URLs), but symbols
        # are matched/queried as raw strings below, so decode here or coins
        # with non-ASCII/percent-encoded characters in their symbol resolve
        # to the wrong (or no) DB rows and show mismatched name/data.
        path = unquote(parsed.path)

        if path.startswith('/api/'):
            if path in ('/api/auth/status', '/api/auth/check'):
                self.get_auth_status()
                return
            elif path == '/api/health':
                body = json.dumps({"status": "ok", "time": system_now().isoformat()}).encode('utf-8')
                self._set_headers(200, content_length=len(body))
                self.wfile.write(body)
                return
            elif path == '/api/ready':
                self.get_readiness()
                return
            elif not self._check_auth():
                self._send_unauthorized()
                return

            if path == '/api/status':
                self.get_status()
            elif path == '/api/research/v3':
                self.get_research_v3()
            elif path == '/api/signals':
                self.get_signals()
            elif path == '/api/candidates':
                self.get_candidates()
            elif path in ('/api/candidates/compare', '/api/candidates/comparison'):
                self.get_candidate_filter_comparison()
            elif path.startswith('/api/coin/'):
                parts = path.strip('/').split('/')
                if len(parts) >= 3:
                    symbol = parts[2]
                    if len(parts) >= 4 and parts[3] == 'deep-analysis':
                        self.get_deep_analysis(symbol)
                    elif len(parts) >= 4 and parts[3] == 'shap':
                        self.get_shap_analysis(symbol)
                    elif len(parts) >= 4 and parts[3] == 'chart':
                        self.get_coin_chart(symbol)
                    elif len(parts) >= 4 and parts[3] == 'klines':
                        interval = '5m'
                        limit = 100
                        if parsed.query:
                            query_params = parse_qs(parsed.query)
                            interval = query_params.get('interval', ['5m'])[0]
                            try:
                                limit = int(query_params.get('limit', ['100'])[0])
                            except ValueError:
                                limit = 100
                        self.get_coin_klines(symbol, interval=interval, limit=limit)
                    else:
                        self.get_coin_detail(symbol)
            elif path in ('/api/market-overview', '/api/market'):
                self.get_market()
            elif path == '/api/watchlist-presets':
                self.get_watchlist_presets()
            elif path == '/api/watchlist':
                self.get_watchlist()
            elif path == '/api/tracking-watchlist':
                self.get_tracking_watchlist()
            elif path in ('/api/model-audit', '/api/audit'):
                self.get_audit()
            elif path in ('/api/scanner-telemetry', '/api/scanner/telemetry'):
                self.get_scanner_telemetry()
            elif path in ('/api/scan/multi-coin', '/api/multiscan'):
                self.get_multi_coin_scan()
            elif path == '/api/experiments':
                self.get_experiments()
            elif path.startswith('/api/experiments/'):
                artifact_id = path.replace('/api/experiments/', '')
                self.get_experiment_detail(artifact_id)
            elif path == '/api/forward-test/models':
                self.get_frozen_models()
            elif path.startswith('/api/forward-test/evaluate/'):
                model_id = path.replace('/api/forward-test/evaluate/', '')
                self.evaluate_frozen_model(model_id)
            elif path == '/api/models':
                self.get_models()
            elif path in ('/api/models/comparison-matrix', '/api/scoring/compare', '/api/models/compare'):
                self.get_models_comparison_matrix()
            elif path == '/api/system-history':
                self.get_system_history()
            elif path == '/api/alpha-lab/regime':
                self.get_alpha_lab_regime()
            elif path == '/api/alpha-lab/drift':
                self.get_alpha_lab_drift()
            elif path == '/api/alpha-lab/summary':
                self.get_alpha_lab_summary()
            elif path in ('/api/ai/config', '/api/ai/settings'):
                self.get_ai_config()
            elif path in ('/api/version-history', '/api/updates', '/api/changelog'):
                self.get_version_history()
            elif path in ('/api/research/reports', '/api/research', '/api/research-reports'):
                self.get_research_reports()
            elif path.startswith('/api/research/reports/'):
                report_id = path.replace('/api/research/reports/', '')
                self.get_research_report_detail(report_id)
            elif path in ('/api/system/update-status', '/api/updater/status'):
                self.get_system_update_status()
            elif path in ('/api/system/update-logs', '/api/updater/logs'):
                self.get_system_update_logs()
            else:
                err_body = json.dumps({"error": "API endpoint not found"}).encode('utf-8')
                self._set_headers(404, content_length=len(err_body))
                self.wfile.write(err_body)
        else:
            self.serve_static(path)

    def serve_static(self, req_path):
        if req_path == '/' or req_path == '':
            file_path = DIST_DIR / 'index.html'
        else:
            rel_path = req_path.lstrip('/')
            file_path = DIST_DIR / rel_path

        # Resolve before checking existence or serving the SPA fallback. This
        # also rejects encoded traversal, Windows paths and escaping symlinks.
        try:
            if "\\" in req_path or "\x00" in req_path:
                raise ValueError("Invalid static path")
            file_path = file_path.resolve()
            contained = file_path.is_relative_to(DIST_DIR.resolve())
        except (OSError, ValueError):
            contained = False
        if not contained:
            err = b"Asset not found"
            self._set_headers(404, content_type='text/plain', content_length=len(err))
            self.wfile.write(err)
            return

        if not file_path.exists() or file_path.is_dir():
            # If requesting a missing static asset or chunk, return 404 instead of index.html
            static_exts = ('.js', '.css', '.map', '.png', '.jpg', '.jpeg', '.svg', '.json', '.woff', '.woff2', '.ico', '.webp')
            if req_path.startswith('/assets/') or any(req_path.lower().endswith(ext) for ext in static_exts):
                err = b"Asset not found"
                self._set_headers(404, content_type='text/plain', cache_control='no-cache', content_length=len(err))
                self.wfile.write(err)
                return
            file_path = DIST_DIR / 'index.html'

        if file_path.exists():
            ctype, _ = mimetypes.guess_type(str(file_path))
            if str(file_path).endswith('manifest.json') or str(file_path).endswith('.webmanifest'):
                ctype = 'application/manifest+json; charset=utf-8'
            elif str(file_path).endswith('sw.js'):
                ctype = 'application/javascript; charset=utf-8'
            elif str(file_path).endswith('.svg'):
                ctype = 'image/svg+xml'
            elif str(file_path).endswith('.png'):
                ctype = 'image/png'
            elif not ctype:
                ctype = 'application/octet-stream'

            cache_control = 'no-cache, no-store, must-revalidate, max-age=0' if str(file_path).endswith(('index.html', 'sw.js', 'manifest.json', '.webmanifest')) else 'public, max-age=86400'
            try:
                with open(file_path, 'rb') as f:
                    content = f.read()
                self._set_headers(200, content_type=ctype, cache_control=cache_control, content_length=len(content))
                self.wfile.write(content)
            except Exception as exc:
                logger.warning("serve_static_read_failed error=%s", exc)
                err = b"Internal file read error"
                self._set_headers(500, content_type='text/plain', content_length=len(err))
                self.wfile.write(err)
        else:
            err = b"Dist folder not built yet."
            self._set_headers(404, content_type='text/plain', content_length=len(err))
            self.wfile.write(err)

    def _read_json_body(self) -> dict[str, Any] | None:
        """Bound request memory and reject invalid JSON before changing state."""
        try:
            if self.headers.get('Transfer-Encoding'):
                raise ValueError("Transfer-Encoding is not supported")
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length < 0:
                raise ValueError("Invalid Content-Length")
            if content_length > 1024 * 1024:
                body = b'{"error": "Request body too large"}'
                self._set_headers(413, content_length=len(body))
                self.wfile.write(body)
                return None
            body = self.rfile.read(content_length) if content_length else b'{}'
            if content_length and len(body) != content_length:
                raise ValueError("Incomplete request body")
            data = json.loads(body.decode('utf-8'))
            if not isinstance(data, dict):
                raise ValueError("JSON object required")
            return data
        except (ValueError, UnicodeDecodeError):
            body = b'{"error": "A valid JSON object and Content-Length are required"}'
            self._set_headers(400, content_length=len(body))
            self.wfile.write(body)
            return None

    def do_POST(self):
        parsed = urlparse(self.path)
        public_paths = ('/api/auth/verify', '/api/auth/login', '/api/auth/logout')
        if parsed.path.startswith('/api/') and parsed.path not in public_paths and not self._check_auth():
            self._send_unauthorized()
            return
        data = self._read_json_body()
        if data is None:
            return

        if parsed.path in ('/api/auth/verify', '/api/auth/login'):
            self.verify_auth_password(data)
            return
        if parsed.path == '/api/auth/logout':
            self.logout_auth()
            return

        if parsed.path.startswith('/api/'):
            if not self._check_auth():
                self._send_unauthorized()
                return

        if parsed.path == '/api/ai/ask':
            question = data.get('question', '').strip()
            symbol = data.get('symbol', '').strip().upper() or 'BTCUSDT'
            context = data.get('context', {})
            llm_config = data.get('llm_config', {})
            history = data.get('history', [])
            if not question:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Question is required"}).encode('utf-8'))
                return
            try:
                from dao_vang.web.ai_analyst import ask_ai_analyst
                result = ask_ai_analyst(question, symbol, context, llm_config, history=history)
                self._set_headers(200)
                self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
            except Exception as exc:
                logger.exception("AI ask failed for symbol=%s error=%s", symbol, exc)
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(exc)}).encode('utf-8'))
        elif parsed.path == '/api/telegram/send':
            symbol = data.get('symbol', 'UNKNOWN')
            message = data.get('message') or f"🔔 Kiểm tra thủ công: {symbol}"
            ok = _notifier.send_message(message)
            self._set_headers(200 if ok else 502)
            self.wfile.write(json.dumps({
                "status": "success" if ok else "error",
                "message": "Đã gửi Telegram." if ok else "Gửi Telegram thất bại — kiểm tra bot_token/chat_id trong cấu hình.",
                "timestamp": system_now().isoformat()
            }).encode('utf-8'))
        elif parsed.path == '/api/scanner/trigger':
            trigger = _request_scan()
            self._set_headers(202)
            self.wfile.write(json.dumps({
                **trigger,
                "message": (
                    "Scanner đang quét — bảng sẽ dùng kết quả của chu kỳ hiện tại."
                    if trigger["status"] == "in_progress"
                    else "Đã ghi nhận yêu cầu quét — scanner daemon sẽ chạy trong vài giây (nếu daemon đang chạy)."
                ),
            }).encode('utf-8'))
        elif parsed.path == '/api/watchlist/add':
            raw_symbol = data.get('symbol', '')
            symbol = raw_symbol.strip().upper() if isinstance(raw_symbol, str) else ''
            if symbol:
                updated = add_to_watchlist(WATCHLIST_PATH, symbol)
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "success", "manual_watchlist": updated}).encode('utf-8'))
            else:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Symbol required"}).encode('utf-8'))
        elif parsed.path == '/api/tracking-usage':
            try:
                if not isinstance(data, dict) or not isinstance(data.get("visitor_id"), str):
                    raise ValueError("Anonymous visitor id required")
                stats = tracking_usage(TRACKING_WATCHLIST_PATH.with_suffix('.usage.sqlite3'), data["visitor_id"])
                self._set_headers(200)
                self.wfile.write(json.dumps(stats).encode('utf-8'))
            except ValueError as exc:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": str(exc)}).encode('utf-8'))
        elif parsed.path.startswith('/api/tracking-watchlist/') and parsed.path.endswith('/paper'):
            self.post_tracking_paper(unquote(parsed.path[len('/api/tracking-watchlist/'):-len('/paper')]), data)
        elif parsed.path == '/api/tracking-watchlist':
            try:
                prediction: dict[str, Any] = {}
                if not isinstance(data, dict):
                    raise ValueError("JSON object required")
                if data.get("source_prediction_id"):
                    prediction = _scan_store.prediction(str(data["source_prediction_id"])) or {}
                    if not prediction or normalize_symbol(prediction.get("symbol")) != normalize_symbol(data.get("symbol")):
                        raise ValueError("Prediction does not match the tracked symbol")
                    data = {**data,
                            "source_signal_time": _system_history_timestamp(prediction.get("signal_time")),
                            "source_probability": prediction.get("calibrated_probability"),
                            "source_model_id": prediction.get("model_id"),
                            "source_label_version": prediction.get("label_version"),
                            "source_shadow_mode": prediction.get("shadow_mode"),
                            "source_invalidation_time": _system_history_timestamp(prediction.get("invalidation_time"))}
                else:
                    data = {**data, "source_model_id": None, "source_label_version": None, "source_shadow_mode": None, "source_stop_price": None}
                # Fetch a closed reference candle at signal time; never use the
                # live Radar price as if it were an original prediction price.
                data = {**data, "source_price": None, "source_target_price": None,
                        "source_price_time": None, "source_price_evidence": "unverified_saved_observation"}
                reference_at = _as_utc_datetime(data.get("source_signal_time")) or datetime.now(timezone.utc)
                try:
                    data.update(reference_price(normalize_symbol(data.get("symbol")), reference_at))
                    if data.get("source_prediction_id"):
                        target = prediction.get("target_drawdown")
                        adverse = prediction.get("max_adverse_excursion")
                        data["source_target_price"] = data["source_price"] * (1 - float(target)) if target is not None else None
                        data["source_stop_price"] = data["source_price"] * (1 + float(adverse)) if adverse is not None else None
                except Exception:
                    logger.warning("tracking_reference_price_unavailable")
                entry, created = _tracking_store.add(data)
                self._set_headers(201 if created else 200)
                self.wfile.write(json.dumps({
                    "status": "created" if created else "already_tracking",
                    "item": entry,
                }, ensure_ascii=False).encode('utf-8'))
            except ValueError as exc:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": str(exc)}).encode('utf-8'))
            except OSError as exc:
                logger.warning("tracking_watchlist_write_failed error=%s", exc)
                self._set_headers(503)
                self.wfile.write(json.dumps({"error": "Tracking watchlist unavailable"}).encode('utf-8'))
        elif parsed.path == '/api/watchlist/remove':
            raw_symbol = data.get('symbol', '')
            symbol = raw_symbol.strip().upper() if isinstance(raw_symbol, str) else ''
            if symbol:
                updated = remove_from_watchlist(WATCHLIST_PATH, symbol)
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "success", "manual_watchlist": updated}).encode('utf-8'))
            else:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Symbol required"}).encode('utf-8'))
        elif parsed.path == '/api/watchlist/mode':
            raw_modes = data.get('modes', data.get('mode', 'volatile'))
            if isinstance(raw_modes, str):
                requested_modes = [item.strip().lower() for item in raw_modes.split(',') if item.strip()]
            elif isinstance(raw_modes, list):
                requested_modes = [item.strip().lower() for item in raw_modes if isinstance(item, str) and item.strip()]
            else:
                requested_modes = []
            allowed_modes = {'gainers', 'losers', 'volume', 'volatile', 'all', 'manual'}
            if not requested_modes or any(mode not in allowed_modes for mode in requested_modes):
                self._set_headers(400)
                self.wfile.write(json.dumps({
                    "error": "Invalid scan modes",
                    "allowed_modes": sorted(allowed_modes),
                }).encode('utf-8'))
                return
            new_modes = normalize_scan_modes(requested_modes)
            _request_scan(modes=new_modes)
            self._set_headers(202)
            self.wfile.write(json.dumps({
                "status": "queued",
                "active_scan_modes": new_modes,
                "active_scan_mode": ",".join(new_modes),
                "message": "Chế độ quét sẽ được áp dụng ở chu kỳ tiếp theo của scanner daemon.",
            }).encode('utf-8'))
        elif parsed.path == '/api/alerts/dismiss':
            symbol = data.get('symbol', '').upper()
            signal_time_str = data.get('signal_time', '')
            if not symbol or not signal_time_str:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "symbol and signal_time required"}).encode('utf-8'))
                return
            try:
                sig_time = datetime.fromisoformat(signal_time_str)
                if sig_time.tzinfo is None:
                    sig_time = sig_time.replace(tzinfo=timezone.utc)
                _dismissals.dismiss(symbol, sig_time.isoformat())
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "success", "symbol": symbol, "signal_time": signal_time_str}).encode('utf-8'))
            except Exception as exc:
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(exc)}).encode('utf-8'))
        elif parsed.path == '/api/candidates/refresh':
            try:
                trigger = _request_scan()
                body = json.dumps({
                    **trigger,
                    "message": (
                        "Scanner đang quét; bảng sẽ tự cập nhật khi chu kỳ hoàn tất."
                        if trigger["status"] == "in_progress"
                        else "Đã xếp hàng yêu cầu quét; bảng sẽ tự cập nhật khi có snapshot mới."
                    ),
                }).encode("utf-8")
                self._set_headers(202, content_length=len(body))
                self.wfile.write(body)
            except Exception as exc:
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(exc)}).encode('utf-8'))
        elif parsed.path == '/api/listing/refresh':
            try:
                from dao_vang.data.binance_listing import run_daily_scan
                snapshot = run_daily_scan()
                if snapshot:
                    self._set_headers(200)
                    self.wfile.write(json.dumps({"status": "success", "snapshot": snapshot}, default=str).encode('utf-8'))
                else:
                    self._set_headers(502)
                    self.wfile.write(json.dumps({"status": "error", "message": "Không lấy được dữ liệu từ Binance"}).encode('utf-8'))
            except Exception as exc:
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(exc)}).encode('utf-8'))
        elif parsed.path == '/api/forward-test/freeze':
            hypothesis_id = data.get('hypothesis_id', 'hyp_dashboard_001')
            try:
                import numpy as _np
                from sklearn.impute import SimpleImputer as _SimpleImputer
                from sklearn.linear_model import LogisticRegression as _LR
                from sklearn.pipeline import Pipeline as _Pipeline

                from dao_vang.data.storage.duckdb import DuckDBQueryLayer
                from dao_vang.experiments.forward_test import (
                    freeze_model as _freeze_model,
                )

                settings = _settings
                db = DuckDBQueryLayer(str(settings.scanner.db_path))
                try:
                    ft_df = db.conn.execute(
                        """
                        SELECT f.*, l.label_value AS is_distribution
                        FROM feature_results f
                        INNER JOIN labels l
                            ON f.feature_time = l.signal_time AND f.symbol = l.symbol
                        """
                    ).df()
                finally:
                    db.conn.close()

                if ft_df.empty or len(ft_df) < 200:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"error": f"Cần >=200 dòng (hiện có {len(ft_df)}). Chạy Backtest trước."}).encode('utf-8'))
                    return
                initial_labels = _np.asarray(
                    ft_df.loc[:, "is_distribution"], dtype=int
                ).reshape(-1)
                if _np.unique(initial_labels).size < 2:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"error": "Cần cả 2 loại nhãn (có xả + không xả)"}).encode('utf-8'))
                    return

                ft_df = ft_df.sort_values("feature_time").reset_index(drop=True)
                exclude = ["feature_time", "decision_time", "is_distribution", "quality_status", "symbol", "lead_time_minutes", "invalidation_time"]
                feats = [c for c in ft_df.columns if c not in exclude]

                val_cut = ft_df["feature_time"].quantile(0.8)
                tr = ft_df[ft_df["feature_time"] < val_cut]
                va = ft_df[ft_df["feature_time"] >= val_cut]
                tr_labels = _np.asarray(
                    tr.loc[:, "is_distribution"], dtype=int
                ).reshape(-1)
                va_labels = _np.asarray(
                    va.loc[:, "is_distribution"], dtype=int
                ).reshape(-1)
                if _np.unique(tr_labels).size < 2:
                    self._set_headers(400)
                    self.wfile.write(
                        json.dumps(
                            {"error": "Training partition cần cả 2 loại nhãn"}
                        ).encode("utf-8")
                    )
                    return
                # Fit preprocessing on the training partition only.  Missing
                # values are not silently converted to a semantic zero.
                m = _Pipeline(
                    [
                        ("imputer", _SimpleImputer(strategy="median", add_indicator=True)),
                        ("model", _LR(max_iter=1000, random_state=42, class_weight="balanced")),
                    ]
                )
                m.fit(tr[feats], tr_labels)

                best_t, best_f1 = 0.5, 0.0
                if len(va) > 0 and _np.unique(va_labels).size >= 2:
                    yp = m.predict_proba(va[feats])[:, 1]
                    yv = va_labels
                    for t in _np.arange(0.05, 0.95, 0.05):
                        yp_t = (yp >= t).astype(int)
                        tp = int(((yp_t == 1) & (yv == 1)).sum())
                        fp = int(((yp_t == 1) & (yv == 0)).sum())
                        fn = int(((yp_t == 0) & (yv == 1)).sum())
                        if tp + fp == 0 or tp + fn == 0:
                            continue
                        p = tp / (tp + fp)
                        r = tp / (tp + fn)
                        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
                        if f1 > best_f1:
                            best_f1 = f1
                            best_t = float(t)

                final_m = _Pipeline(
                    [
                        ("imputer", _SimpleImputer(strategy="median", add_indicator=True)),
                        ("model", _LR(max_iter=1000, random_state=42, class_weight="balanced")),
                    ]
                )
                final_labels = _np.asarray(
                    ft_df.loc[:, "is_distribution"], dtype=int
                ).reshape(-1)
                final_m.fit(ft_df[feats], final_labels)

                info = _freeze_model(
                    model=final_m,
                    threshold=float(best_t),
                    feature_cols=feats,
                    config={"hypothesis_id": hypothesis_id, "dataset_version": "v1", "label_version": "v1", "feature_set_version": "v1", "seed": 42},
                    train_cutoff=ft_df["feature_time"].max(),
                    training_stats={
                        "train_size": len(ft_df),
                        "train_positives": int(final_labels.sum()),
                        "threshold": float(best_t),
                        "n_features": len(feats),
                    },
                    artifact_dir=Path("./artifacts"),
                )
                self._set_headers(200)
                self.wfile.write(json.dumps({
                    "status": "success",
                    "model_id": info.model_id,
                    "train_cutoff": info.train_cutoff,
                    "threshold": info.threshold,
                    "n_features": len(info.feature_cols),
                    "train_size": len(ft_df),
                    "train_positives": int(final_labels.sum()),
                }, default=str).encode('utf-8'))
            except Exception as exc:
                logger.warning(f"freeze_model_failed error={exc}")
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(exc)}).encode('utf-8'))
        elif parsed.path in ('/api/version-history/refresh', '/api/updates/refresh'):
            self.post_version_history_refresh()
        elif parsed.path in ('/api/system/update-apply', '/api/updater/apply', '/api/system/update'):
            self.post_system_update_apply()
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode('utf-8'))

    def do_PATCH(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/'):
            if not self._check_auth():
                self._send_unauthorized()
                return

        data = self._read_json_body()
        if data is None:
            return

        prefix = '/api/tracking-watchlist/'
        if not parsed.path.startswith(prefix):
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "API endpoint not found"}).encode('utf-8'))
            return
        entry_id = unquote(parsed.path[len(prefix):]).strip()
        if not entry_id:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Tracking item id required"}).encode('utf-8'))
            return
        if not isinstance(data, dict):
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "JSON object required"}).encode('utf-8'))
            return
        try:
            updated = _tracking_store.update(entry_id, data)
            if updated is None:
                self._set_headers(404)
                self.wfile.write(json.dumps({"error": "Tracking item not found"}).encode('utf-8'))
                return
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "updated", "item": updated}, ensure_ascii=False).encode('utf-8'))
        except ValueError as exc:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": str(exc)}).encode('utf-8'))
        except OSError:
            self._set_headers(503)
            self.wfile.write(json.dumps({"error": "Tracking watchlist unavailable"}).encode('utf-8'))

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/'):
            if not self._check_auth():
                self._send_unauthorized()
                return

        prefix = '/api/tracking-watchlist/'
        if not parsed.path.startswith(prefix):
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "API endpoint not found"}).encode('utf-8'))
            return
        entry_id = unquote(parsed.path[len(prefix):]).strip()
        if not entry_id:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Tracking item id required"}).encode('utf-8'))
            return
        try:
            removed = _tracking_store.remove(entry_id)
            self._set_headers(200 if removed else 404)
            self.wfile.write(json.dumps({
                "status": "removed" if removed else "not_found",
                "id": entry_id,
            }).encode('utf-8'))
        except ValueError as exc:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": str(exc)}).encode('utf-8'))
        except OSError:
            self._set_headers(503)
            self.wfile.write(json.dumps({"error": "Tracking watchlist unavailable"}).encode('utf-8'))

    def get_tracking_watchlist(self):
        """Return user tracking entries enriched with current public market data."""

        entries = _tracking_store.list(include_archived=True)
        if not entries:
            self._set_headers(200)
            self.wfile.write(json.dumps([], ensure_ascii=False).encode('utf-8'))
            return

        try:
            tickers = fetch_all_tickers()
        except Exception as exc:
            logger.warning("tracking_watchlist_tickers_failed error=%s", exc)
            tickers = []
        ticker_by_symbol = {
            normalize_symbol(item.get("symbol")): item
            for item in tickers
            if isinstance(item, dict) and item.get("symbol")
        }

        try:
            alert_rows = _alert_store.query(days=3650, include_dismissed=True, limit=5000)
        except Exception as exc:
            logger.warning("tracking_watchlist_alerts_failed error=%s", exc)
            alert_rows = []
        alerts_by_symbol: dict[str, list[dict[str, Any]]] = {}
        for row in alert_rows:
            alerts_by_symbol.setdefault(normalize_symbol(row.get("symbol")), []).append(row)

        now = datetime.now(timezone.utc)

        def same_instant(left: Any, right: Any) -> bool:
            left_dt = _as_utc_datetime(left)
            right_dt = _as_utc_datetime(right)
            return left_dt is not None and right_dt is not None and abs((left_dt - right_dt).total_seconds()) < 1.0

        def progress(source_price: float | None, target_price: float | None, current_price: float | None) -> float | None:
            if not source_price or not target_price or current_price is None or target_price == source_price:
                return None
            if target_price < source_price:
                value = (source_price - current_price) / (source_price - target_price)
            else:
                value = (current_price - source_price) / (target_price - source_price)
            return round(max(0.0, min(1.0, value)) * 100.0, 1)

        try:
            latest_scans_list = _scan_store.latest_per_symbol(limit=500, max_age_hours=48)
            latest_scans = {s["symbol"]: s for s in latest_scans_list}
        except Exception:
            latest_scans = {}

        enriched: list[dict[str, Any]] = []
        prediction_ids = [entry["source_prediction_id"] for entry in entries if entry.get("source_prediction_id")]
        try:
            prediction_outcomes = _scan_store.get_prediction_outcomes(prediction_ids) if prediction_ids else {}
        except Exception as exc:
            logger.warning("tracking_watchlist_outcomes_failed error=%s", exc)
            prediction_outcomes = {}
        for entry in entries:
            symbol = normalize_symbol(entry.get("symbol"))
            source_signal_time = entry.get("source_signal_time")
            alert = next(
                (
                    row
                    for row in alerts_by_symbol.get(symbol, [])
                    if source_signal_time and same_instant(row.get("signal_time"), source_signal_time)
                ),
                None,
            )

            source_price = entry.get("source_price")
            source_probability = entry.get("source_probability")
            source_risk_level = entry.get("source_risk_level")
            target_price = entry.get("source_target_price")
            invalidation_time = entry.get("source_invalidation_time")
            hit = None
            hit_time = None
            if alert and not entry.get("source_prediction_id"):
                # Saved observations belong to the original signal, never the
                # current model. Only fill gaps from that exact historical alert.
                if source_price is None:
                    source_price = alert.get("close_price")
                if source_probability is None:
                    source_probability = alert.get("probability")
                if invalidation_time is None:
                    invalidation_time = _system_history_timestamp(alert.get("invalidation_time"))
                hit = alert.get("hit")
                hit_time = _system_history_timestamp(alert.get("hit_time"))

            outcome = prediction_outcomes.get(entry.get("source_prediction_id"), {})
            if outcome.get("outcome_status") == "materialized" and outcome.get("label_value") in (0, 1):
                hit = outcome["label_value"] == 1

            latest_scan = latest_scans.get(symbol)
            ticker = ticker_by_symbol.get(symbol, {})
            observation = market_observation(ticker, latest_scan, now=now)
            current_price = observation["current_price"]

            invalidation_dt = _as_utc_datetime(invalidation_time)
            validity_hours_left = (
                max(0.0, (invalidation_dt - now).total_seconds() / 3600.0)
                if invalidation_dt is not None else None
            )
            signal_status = signal_outcome(hit, invalidation_time, now=now)

            signal_change_pct = None
            if source_price and current_price is not None:
                signal_change_pct = round((current_price - float(source_price)) / float(source_price) * 100.0, 2)

            position_metrics = calculate_position_metrics(
                current_price=current_price if observation["market_data_status"] == "FRESH" else None,
                entry_price=entry.get("entry_price"),
                position_side=entry.get("position_side"),
                quantity=entry.get("quantity"),
                notional=entry.get("notional"),
                leverage=entry.get("leverage"),
            )

            current_probability = latest_scan.get("calibrated_probability") if latest_scan else None
            current_risk_level = (
                _scan_risk_level(latest_scan.get("recommendation"), float(current_probability))
                if current_probability is not None and latest_scan else None
            )
            item = {
                **entry,
                "symbol": symbol,
                "source_price": source_price,
                "source_probability": source_probability,
                "source_risk_level": source_risk_level,
                "source_target_price": target_price,
                "source_invalidation_time": invalidation_time,
                "signal_status": signal_status,
                "hit": hit,
                "hit_time": hit_time,
                "outcome_exclusion_reason": outcome.get("exclusion_reason"),
                "validity_hours_left": round(validity_hours_left, 2) if validity_hours_left is not None else None,
                "current_price": current_price,
                "current_probability": current_probability,
                "current_risk_level": current_risk_level,
                "signal_change_pct": signal_change_pct,
                "signal_progress_pct": progress(
                    float(source_price) if source_price is not None else None,
                    float(target_price) if target_price is not None else None,
                    current_price,
                ),
                **position_metrics,
                **observation,
            }
            enriched.append(item)

        enriched.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
        self._set_headers(200)
        self.wfile.write(json.dumps(enriched, ensure_ascii=False, default=str).encode('utf-8'))

    def post_tracking_paper(self, entry_id: str, data: Any):
        try:
            if not isinstance(data, dict):
                raise ValueError("JSON object required")
            entry = _tracking_store.get(entry_id, include_archived=True)
            if entry is None:
                raise ValueError("Tracking item not found")
            action = str(data.get("action") or "")
            trade = entry.get("paper_trade")
            if action == "reconcile" and trade and trade["status"] == "CLOSED":
                closed_at = _as_utc_datetime(trade.get("closed_at"))
                if closed_at is None:
                    raise ValueError("No paper close time")
                updated = _tracking_store.reconcile_funding(entry_id, fetch_funding(entry["symbol"], trade, closed_at), now=datetime.now(timezone.utc))
            elif (action == "open" and trade) or (action == "close" and trade and trade["status"] == "CLOSED"):
                updated = entry
            else:
                tickers = {row["symbol"]: row for row in fetch_all_tickers()}
                now = datetime.now(timezone.utc)
                quote = market_observation(tickers.get(entry["symbol"], {}), None, now=now)
                funding = fetch_funding(entry["symbol"], trade, now) if action == "close" and trade else None
                updated = _tracking_store.paper(entry_id, action=action, quote=quote, now=now,
                                                side=str(data.get("side", "SHORT")), notional=float(data.get("notional", 1000)),
                                                fee_bps=float(data.get("fee_bps", 5)), slippage_bps=float(data.get("slippage_bps", 5)), funding=funding)
            self._set_headers(200)
            self.wfile.write(json.dumps({"item": updated}, ensure_ascii=False).encode('utf-8'))
        except (ValueError, TypeError) as exc:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": str(exc)}).encode('utf-8'))
        except Exception:
            logger.exception("tracking_paper_unavailable")
            self._set_headers(503)
            self.wfile.write(json.dumps({"error": "Paper journal unavailable"}).encode('utf-8'))

    def get_ai_config(self):
        """Return server-configured default AI provider settings."""
        try:
            from dao_vang.config.settings import AppSettings
            _app_settings = AppSettings()
            ai_cfg = {
                "provider": (_app_settings.ai.provider or "openai").lower().strip(),
                "hasApiKey": bool((_app_settings.ai.api_key or "").strip()),
                "modelId": (_app_settings.ai.model_id or "antigravity/gemini-3.7-flash-tiered").strip(),
                "baseUrl": (_app_settings.ai.base_url or "https://proxy-ai.comaygiauco.com/v1").strip(),
                "enabled": bool(_app_settings.ai.enabled),
            }
            self._set_headers(200)
            self.wfile.write(json.dumps(ai_cfg, ensure_ascii=False).encode('utf-8'))
        except Exception as exc:
            logger.warning("ai_config_unavailable error=%s", exc)
            self._set_headers(200)
            self.wfile.write(json.dumps({
                "provider": "unavailable",
                "hasApiKey": False,
                "modelId": "",
                "baseUrl": "",
                "enabled": False,
                "error": "settings_unavailable",
            }).encode('utf-8'))

    def get_status(self):
        global _STATUS_RESP_TIME, _STATUS_RESP_CACHE
        now_monotonic = time.monotonic()
        with _STATUS_CACHE_LOCK:
            if _STATUS_RESP_CACHE and (now_monotonic - _STATUS_RESP_TIME) < 3.0:
                self._set_headers(200)
                self.wfile.write(json.dumps(_STATUS_RESP_CACHE, default=str).encode('utf-8'))
                return

        hb = _read_json(HEARTBEAT_PATH)
        scan_mode = _current_scan_mode()
        now = datetime.now(timezone.utc)
        hb_ts_raw = hb.get("timestamp")
        is_stale = True
        if hb_ts_raw:
            try:
                ts = datetime.fromisoformat(hb_ts_raw)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                is_stale = (now - ts) > timedelta(
                    minutes=max(3 * _settings.scanner.poll_interval_minutes, 15)
                )
            except Exception:
                is_stale = True

        db_read_errors: list[str] = []
        with _STATUS_CACHE_LOCK:
            cached = dict(_STATUS_CACHE)

        top_risk_symbol = cached.get("top_risk_symbol")
        active_signals = int(cached.get("active_signals_count", 0))
        cycle_stats = cached.get("cycle_stats", {})

        # The scanner owns the DuckDB writer. On Windows, a read-only open can
        # fail briefly while a cycle is committing. Status must remain useful
        # during that window, so retain the last successful values and use the
        # heartbeat as the live source of truth for liveness.
        try:
            recent_alerts = _alert_store.query(
                days=1, include_dismissed=False, limit=500
            )
            top_risk_symbol = recent_alerts[0]["symbol"] if recent_alerts else None
            active_signals = len(recent_alerts)
        except Exception as exc:
            db_read_errors.append("alert_history")
            logger.warning("status_alert_history_unavailable error=%s", exc)

        try:
            cycle_stats = _scan_store.latest_cycle_stats()
        except Exception as exc:
            db_read_errors.append("scan_results")
            logger.warning("status_scan_results_unavailable error=%s", exc)

        if not cycle_stats:
            cycle_stats = {
                "cycle": hb.get("cycle"),
                "n_symbols": hb.get("last_cycle_n_symbols", 0),
                "n_alerts": hb.get("last_cycle_n_alerts", 0),
                "last_scan_time": hb.get("last_cycle_completed_at"),
            }

        with _STATUS_CACHE_LOCK:
            _STATUS_CACHE.update(
                {
                    "top_risk_symbol": top_risk_symbol,
                    "active_signals_count": active_signals,
                    "cycle_stats": cycle_stats,
                }
            )

        # Friendly model name for header display
        current_model_id = hb.get("model_id") or _settings.scanner.frozen_model_id
        model_friendly = current_model_id or "Heuristic (chưa cài frozen)"
        if current_model_id:
            try:
                from dao_vang.experiments.forward_test import load_frozen_model
                _fi = load_frozen_model(current_model_id, Path("./artifacts"))
                _spec = _fi.label_spec or {}
                _td = _spec.get("target_drawdown", ACTIVE_TARGET_DRAWDOWN)
                _mae = _spec.get("max_ae", 0.04)
                _hz = _spec.get("horizon_minutes", 1440)
                _lv = _fi.config.get("label_version", "v1")
                _td_s = f"{_td * 100:.0f}%" if isinstance(_td, (int, float)) else str(_td)
                _mae_s = f"{_mae * 100:.0f}%" if isinstance(_mae, (int, float)) else str(_mae)
                _hz_s = f"{_hz // 60:.0f}h" if isinstance(_hz, (int, float)) else str(_hz)
                model_friendly = f"LR {_lv} ({_td_s}/{_mae_s}/{_hz_s})"
            except Exception as exc:
                logger.warning(f"status_load_friendly_model_failed error={exc}")

        res = {
            "scanner_status": "OFFLINE" if (is_stale or hb.get("status") != "running") else "ONLINE",
            "scanner_mode": f"24/7 Scanner ({scan_mode.upper()})",
            "heartbeat": _system_history_timestamp(hb_ts_raw),
            "scanned_coins_count": cycle_stats.get("n_symbols", 0),
            "active_signals_count": active_signals,
            "top_risk_symbol": top_risk_symbol,
            "model_version": model_friendly,
            "model_id": current_model_id,
            "telegram_connected": _notifier.is_configured,
            "threshold": _settings.scoring.alert_score_threshold / 100.0,
            "db_read_status": "degraded" if db_read_errors else "ok",
        }
        with _STATUS_CACHE_LOCK:
            _STATUS_RESP_CACHE = res
            _STATUS_RESP_TIME = now_monotonic
        self._set_headers(200)
        self.wfile.write(json.dumps(res, default=str).encode('utf-8'))

    def get_scanner_telemetry(self):
        hb = _read_json(HEARTBEAT_PATH)
        runtime = _read_json(RUNTIME_STATE_PATH)
        cycle_stats = {}
        try:
            cycle_stats = _scan_store.latest_cycle_stats()
        except Exception as exc:
            logger.warning(f"telemetry_cycle_stats_failed error={exc}")

        recent = []
        try:
            recent = _alert_store.query(days=1, include_dismissed=True, limit=20)
        except Exception as exc:
            logger.warning(f"telemetry_alerts_query_failed error={exc}")

        logs = []
        for r in recent:
            sig_time = r["signal_time"]
            display_time = _system_display_datetime(sig_time)
            ts_str = display_time.strftime("%H:%M:%S") if display_time else str(sig_time)
            logs.append({
                "timestamp": ts_str,
                "symbol": r["symbol"],
                "step": "Composite Scoring",
                "status": "ALERT FIRED" if r.get("telegram_sent") else "SCORED",
                "duration_ms": None,
                "details": f"Score {r['probability'] * 100:.1f}/100, risk={r['risk_level']}",
            })

        # Also add recent scan_results as logs (shows scanner activity even without alerts)
        try:
            conn = _ro_duckdb_connect(str(_settings.scanner.db_path))
            try:
                scan_logs = conn.execute(
                    """
                    SELECT scan_time, symbol, score, recommendation, close_price
                    FROM scan_results
                    WHERE scan_time >= ?
                    ORDER BY scan_time DESC LIMIT 30
                    """,
                    [datetime.now(timezone.utc) - timedelta(hours=24)],
                ).fetchall()
                for scan_time, symbol, score, rec, close_price in scan_logs:
                    display_time = _system_display_datetime(scan_time)
                    ts_str = display_time.strftime("%H:%M:%S") if display_time else str(scan_time)
                    logs.append({
                        "timestamp": ts_str,
                        "symbol": symbol,
                        "step": "Scan + Score",
                        "status": rec.upper() if rec else "SCORED",
                        "duration_ms": None,
                        "details": f"Score {score:.1f}/100, price={close_price}",
                    })
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(f"telemetry_scan_logs_failed error={exc}")

        # Sort logs by timestamp descending
        logs.sort(key=lambda x: x["timestamp"], reverse=True)

        telegram_logs = []
        for r in recent:
            if not r.get("telegram_sent"):
                continue
            sent_at = r.get("telegram_sent_at")
            display_time = _system_display_datetime(sent_at)
            telegram_logs.append({
                "timestamp": display_time.strftime("%Y-%m-%d %H:%M:%S") if display_time else str(sent_at),
                "symbol": r["symbol"],
                "risk_score": f"{r['probability'] * 100:.1f}%",
                "channel": "Telegram",
                "status": "DELIVERED",
            })

        # Heartbeat is also written when a cycle starts.  Prefer the explicit
        # completion timestamp so the UI never calls an in-progress cycle the
        # last successful scan.
        last_scan_time = hb.get("last_cycle_completed_at") or hb.get("timestamp")
        if not last_scan_time and cycle_stats.get("last_scan_time") is not None:
            lst = cycle_stats["last_scan_time"]
            last_scan_time = _system_history_timestamp(lst)
        elif last_scan_time:
            last_scan_time = _system_history_timestamp(last_scan_time)

        # Compute next scan time from heartbeat
        next_scan_in = None
        hb_ts = hb.get("last_cycle_completed_at") or hb.get("timestamp")
        poll_min = hb.get("poll_minutes", _settings.scanner.poll_interval_minutes)
        if hb_ts and poll_min:
            try:
                hb_dt = datetime.fromisoformat(hb_ts.replace("Z", "+00:00"))
                next_dt = hb_dt + timedelta(minutes=poll_min)
                now_dt = datetime.now(timezone.utc)
                next_scan_in = max(0, int((next_dt - now_dt).total_seconds()))
            except Exception as e:
                logger.warning(f"Error processing stats item: {e}")

        telemetry_modes = normalize_scan_modes(
            hb.get("scan_modes", hb.get("scan_mode", _current_scan_mode()))
        )
        res = {
            "scanner_engine_status": "ONLINE" if hb.get("status") == "running" else "OFFLINE",
            "last_scan_timestamp": last_scan_time,
            "next_scan_in_seconds": next_scan_in,
            "poll_interval_minutes": poll_min,
            "api_endpoint": "https://fapi.binance.com/fapi/v1",
            "average_api_latency_ms": None,
            "active_scan_mode": hb.get("scan_mode", _current_scan_mode()),
            "active_scan_modes": telemetry_modes,
            "scanned_pairs_count": cycle_stats.get("n_symbols", 0),
            "signals_triggered_count": cycle_stats.get("n_alerts", 0),
            "stablecoins_excluded_count": None,
            "runtime_state": runtime,
            "model_id": hb.get("model_id"),
            "cycle": hb.get("cycle"),
            "max_coins": hb.get("max_coins"),
            "logs": logs[:30],  # cap at 30
            "telegram_dispatches": telegram_logs,
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(res, default=str).encode('utf-8'))

    def get_watchlist_presets(self):
        self._set_headers(200)
        self.wfile.write(json.dumps({"presets": []}).encode("utf-8"))
    def get_watchlist(self):
        manual = load_manual_watchlist(WATCHLIST_PATH)
        scan_modes = _current_scan_modes()
        scan_mode = ",".join(scan_modes)
        cfg = _settings.scanner

        try:
            tickers = fetch_all_tickers()
        except Exception as exc:
            logger.warning(f"watchlist_tickers_fetch_failed error={exc}")
            tickers = []
        filtered_count = len(
            _filter_tickers(tickers, cfg.min_volume_usd, cfg.min_price_change_pct, cfg.exclude_stablecoins)
        )

        res = {
            "active_scan_mode": scan_mode,
            "active_scan_modes": scan_modes,
            "presets": [
                {
                    "id": "volatile",
                    "name": "⚡ Top Coin Biến Động Nhất (Volatile)",
                    "description": "Quét các coin Futures có biến động giá 24h mạnh nhất.",
                    "count": filtered_count,
                },
                {
                    "id": "volume",
                    "name": "📊 Top Khối Lượng Giao Dịch (Volume)",
                    "description": "Quét Top coin Futures có Volume giao dịch 24h lớn nhất Binance.",
                    "count": filtered_count,
                },
                {
                    "id": "gainers",
                    "name": "📈 Top Coin Tăng Giá Mạnh Nhất 24h (Gainers)",
                    "description": "Top coin tăng giá 24h mạnh nhất — ứng viên tạo đỉnh & bắt đầu xả.",
                    "count": filtered_count,
                },
                {
                    "id": "losers",
                    "name": "📉 Top Coin Giảm Giá Mạnh Nhất 24h (Losers)",
                    "description": "Top coin đã bắt đầu xả mạnh 24h — ứng viên Short tiếp diễn.",
                "count": filtered_count,
                },
                {
                    "id": "manual",
                    "name": "⭐ Watchlist Tùy Chọn (Manual Watchlist)",
                    "description": "Danh sách coin cá nhân do bạn tùy chỉnh lựa chọn.",
                    "count": len(manual),
                },
            ],
            "manual_watchlist": manual,
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(res).encode('utf-8'))

    def get_signals(self):
        global _SIGNALS_RESP_TIME, _SIGNALS_RESP_CACHE
        raw_path = getattr(self, "path", "/api/signals")
        if not isinstance(raw_path, str):
            raw_path = "/api/signals"
        parsed_url = urlparse(raw_path)
        qs = parse_qs(parsed_url.query)
        status_filter = qs.get("status", [None])[0]
        if status_filter:
            status_filter = status_filter.lower()
        dedup_mode = qs.get("dedup", [None])[0]

        now_monotonic = time.monotonic()
        with _STATUS_CACHE_LOCK:
            if _SIGNALS_RESP_CACHE and (now_monotonic - _SIGNALS_RESP_TIME) < 3.0:
                cached_res = _SIGNALS_RESP_CACHE
                if status_filter == "active":
                    cached_res = [s for s in cached_res if s.get("validity_hours_left", 0) > 0]
                elif status_filter == "expired":
                    cached_res = [s for s in cached_res if s.get("validity_hours_left", 0) <= 0]
                if dedup_mode in ("true", "symbol", "1"):
                    deduped: dict[str, Any] = {}
                    for s in cached_res:
                        sym = s.get("symbol")
                        if sym and sym not in deduped:
                            deduped[sym] = s
                    cached_res = list(deduped.values())
                self._set_headers(200)
                self.wfile.write(json.dumps(_dismissals.filter(cached_res), default=str).encode('utf-8'))
                return

        now = datetime.now(timezone.utc)
        rows = _alert_store.query(days=7, include_dismissed=False, limit=100)
        lead_stats = _alert_store.lead_time_stats(days=30)
        latest_scans_list: list[dict[str, Any]] = []
        try:
            latest_scans_list = _scan_store.latest_per_symbol(limit=500, max_age_hours=None)
            latest_scans = {s["symbol"]: s for s in latest_scans_list}
        except Exception:
            latest_scans = {}
        signals = []
        alert_event_times: dict[str, datetime] = {}
        for r in rows:
            sig_time = r["signal_time"]
            inv_time = r["invalidation_time"]

            sig_dt = _as_utc_datetime(sig_time)
            inv_dt = _as_utc_datetime(inv_time)
            event_dt = _as_utc_datetime(r.get("telegram_sent_at")) or sig_dt
            if event_dt is not None:
                previous_event = alert_event_times.get(r["symbol"])
                if previous_event is None or event_dt > previous_event:
                    alert_event_times[r["symbol"]] = event_dt

            components: list[dict[str, Any]] = []
            if r.get("components_json"):
                try:
                    components = json.loads(r["components_json"])
                except (json.JSONDecodeError, TypeError):
                    components = []
            top = sorted(components, key=lambda c: c.get("weighted_score", 0), reverse=True)[:4]
            drivers = [
                {
                    "name": c.get("name", "").replace("_", " ").title(),
                    "impact": "High" if c.get("weighted_score", 0) >= 10 else "Medium",
                    "score": f"{c.get('weighted_score', 0):+.1f}",
                }
                for c in top
            ]

            validity_hours_left = 0.0
            validity_hours_total = 24.0
            if inv_dt is not None:
                validity_hours_left = max(0.0, (inv_dt - now).total_seconds() / 3600.0)
                if sig_dt is not None:
                    validity_hours_total = max(0.0, (inv_dt - sig_dt).total_seconds() / 3600.0)

            close_price = r.get("close_price")

            scan = latest_scans.get(r["symbol"])
            oi_change = scan.get("oi_change_24h") if scan else None
            funding = scan.get("funding_rate") if scan else None
            taker_sell = scan.get("taker_sell_ratio") if scan else None
            anomaly_fields = _anomaly_fields(scan)

            rsi_divergence = any(
                c.get("name", "") in ("momentum_exhaustion", "fake_breakout")
                and c.get("weighted_score", 0) >= 5
                for c in components
            )

            label_target = float(r.get("target_drawdown") or _current_model_target_drawdown())
            target_drawdown = -abs(label_target * 100.0 if abs(label_target) <= 1.0 else label_target)
            target_price = round(close_price * (1 + target_drawdown / 100.0), 8) if close_price else 0.0

            prob_val = float(r.get("probability") or 0.0)
            is_fired = prob_val >= 0.70
            two_tier_state = "FIRED" if is_fired else "ARMED" if prob_val >= 0.35 else "NORMAL"

            trade_setup = _build_signal_trade_setup(
                close_price or 0.0,
                prob=prob_val,
                components=components,
                target_drawdown=abs(target_drawdown),
                features=scan or {},
                anomalies=anomaly_fields.get("anomalies"),
                quality_score=r.get("data_quality_score"),
                signal_score=r.get("heuristic_score"),
                volume_24h_usd=(scan or {}).get("volume_24h_usd"),
            )
            pat_en, pat_vi = _build_signal_trigger_pattern(components, anomaly_fields.get("anomalies"))
            outcome_stat, mfe_val, mae_val = _build_signal_outcomes(r.get("hit"), validity_hours_left)

            signals.append({
                "id": f"{r['symbol']}-{_system_history_timestamp(sig_time)}",
                "symbol": r["symbol"],
                "name": r["symbol"].replace("USDT", ""),
                "probability": r["probability"],
                "risk_level": _risk_bucket(r["probability"] * 100.0),
                "two_tier_state": two_tier_state,
                "signal_time": _system_history_timestamp(sig_time),
                "event_time": _system_history_timestamp(event_dt),
                "telegram_sent_at": _system_history_timestamp(r.get("telegram_sent_at")),
                "signal_price": close_price or 0.0,
                "target_drawdown": target_drawdown,
                "target_price": target_price,
                "validity_hours_left": validity_hours_left,
                "validity_hours_total": validity_hours_total,
                "invalidation_time": _system_history_timestamp(inv_dt),
                "lead_time_avg_hours": lead_stats["mean_hours"],
                "oi_change_24h": f"{oi_change:+.1%}" if oi_change is not None else "N/A",
                "taker_sell_ratio": taker_sell if taker_sell is not None else 0.5,
                "funding_rate": f"{funding:+.3%}" if funding is not None else "N/A",
                "rsi_divergence": rsi_divergence,
                "evidence_precision": r.get("evidence_precision"),
                "evidence_n_judged": r.get("evidence_n_judged"),
                "hit": r.get("hit"),
                "outcome_status": outcome_stat,
                "mfe_pct": mfe_val,
                "mae_pct": mae_val,
                "trigger_pattern": pat_en,
                "trigger_pattern_vi": pat_vi,
                "trade_setup": trade_setup,
                "telegram_sent": r.get("telegram_sent"),
                "drivers": drivers,
                **_resolve_market_cap_info(r["symbol"], scan.get("volume_24h_usd") if scan else None),
                **anomaly_fields,
            })

        # Also include top candidates from scan_results that haven't triggered
        # alerts, so the RADAR shows what the scanner is seeing even when no
        # alert threshold has been crossed.
        # Keep the normal top-score feed compact, but never hide a market
        # anomaly merely because its frozen-model score is below the first
        # 50 rows.  The anomaly filter must be able to discover observations
        # outside the model leaderboard as well.
        scan_rows = list(latest_scans_list[:50])
        scan_symbols = {str(sr.get("symbol", "")) for sr in scan_rows}
        for sr in latest_scans_list[50:]:
            sym = str(sr.get("symbol", ""))
            if sym in scan_symbols:
                continue
            if _anomaly_fields(sr)["anomaly_count"] <= 0:
                continue
            scan_rows.append(sr)
            scan_symbols.add(sym)
            if len(scan_rows) >= 150:
                break
        for sr in scan_rows:
            sym = sr.get("symbol", "")
            calibrated_probability = sr.get("calibrated_probability")
            if calibrated_probability is None:
                # Never expose the heuristic score as a probability.  Legacy
                # rows without a calibrated value remain visible in the raw
                # scan store but are not promoted to the prediction UI.
                continue
            try:
                prob = float(calibrated_probability)
            except (TypeError, ValueError):
                continue
            if not 0.0 <= prob <= 1.0:
                continue
            scan_time = sr.get("scan_time")
            sig_time_str = _system_history_timestamp(scan_time) or str(scan_time)
            scan_dt = _as_utc_datetime(scan_time)
            existing_alert_event = alert_event_times.get(sym)
            if (
                existing_alert_event is not None
                and scan_dt is not None
                and existing_alert_event >= scan_dt
            ):
                continue
            scan_invalidation_dt = scan_dt + timedelta(hours=24) if scan_dt is not None else None
            close_price = sr.get("close_price")
            sym = sr.get("symbol", "")
            calibrated_probability = sr.get("calibrated_probability")
            if calibrated_probability is None:
                continue
            try:
                prob = float(calibrated_probability)
            except (TypeError, ValueError):
                continue
            if not 0.0 <= prob <= 1.0:
                continue
            scan_time = sr.get("scan_time")
            sig_time_str = _system_history_timestamp(scan_time) or str(scan_time)
            scan_dt = _as_utc_datetime(scan_time)
            existing_alert_event = alert_event_times.get(sym)
            if (
                existing_alert_event is not None
                and scan_dt is not None
                and existing_alert_event >= scan_dt
            ):
                continue
            scan_invalidation_dt = scan_dt + timedelta(hours=24) if scan_dt is not None else None
            close_price = sr.get("close_price")
            oi_change = sr.get("oi_change_24h")
            funding = sr.get("funding_rate")
            taker_sell = sr.get("taker_sell_ratio")
            anomaly_fields = _anomaly_fields(sr)
            label_target = float(sr.get("target_drawdown") or _current_model_target_drawdown())
            target_drawdown = -abs(label_target * 100.0 if abs(label_target) <= 1.0 else label_target)
            target_price = round(close_price * (1 + target_drawdown / 100.0), 8) if close_price else 0.0
            tier = str(sr.get("recommendation", "WAIT"))
            risk_level = _scan_risk_level(tier, prob)
            is_scan_fired = prob >= 0.70
            two_tier_state = "FIRED" if is_scan_fired else "ARMED" if prob >= 0.35 else "NORMAL"
            scan_setup = _build_signal_trade_setup(
                close_price or 0.0,
                prob=prob,
                target_drawdown=abs(target_drawdown),
                features=sr,
                anomalies=anomaly_fields.get("anomalies"),
                quality_score=sr.get("data_quality_score"),
                signal_score=sr.get("heuristic_score") or sr.get("score"),
                volume_24h_usd=sr.get("volume_24h_usd"),
            )
            scan_pat_en, scan_pat_vi = _build_signal_trigger_pattern([], anomaly_fields.get("anomalies"))
            scan_v_left = max(0.0, (scan_invalidation_dt - datetime.now(timezone.utc)).total_seconds() / 3600.0) if scan_invalidation_dt else 24.0
            scan_outcome_stat = "UNTRACKED"

            signals.append({
                "id": f"{sym}-scan-{sig_time_str}",
                "symbol": sym,
                "name": sym.replace("USDT", ""),
                "probability": prob,
                "risk_level": risk_level,
                "two_tier_state": two_tier_state,
                "signal_time": sig_time_str,
                "event_time": _system_history_timestamp(scan_dt) if scan_dt is not None else sig_time_str,
                "telegram_sent_at": None,
                "signal_price": close_price or 0.0,
                "target_drawdown": target_drawdown,
                "target_price": target_price,
                "validity_hours_left": scan_v_left,
                "validity_hours_total": 24.0,
                "invalidation_time": _system_history_timestamp(scan_invalidation_dt),
                "lead_time_avg_hours": lead_stats["mean_hours"],
                "oi_change_24h": f"{oi_change:+.1%}" if oi_change is not None else "N/A",
                "taker_sell_ratio": taker_sell if taker_sell is not None else 0.5,
                "funding_rate": f"{funding:+.3%}" if funding is not None else "N/A",
                "rsi_divergence": False,
                "evidence_precision": None,
                "evidence_n_judged": None,
                "hit": None,
                "outcome_status": scan_outcome_stat,
                "mfe_pct": None,
                "mae_pct": None,
                "trigger_pattern": scan_pat_en,
                "trigger_pattern_vi": scan_pat_vi,
                "trade_setup": scan_setup,
                "telegram_sent": False,
                "drivers": [],
                **_resolve_market_cap_info(sym, sr.get("volume_24h_usd")),
                **anomaly_fields,
            })

        # Shadow mode writes every scored observation to ``predictions`` and
        # marks the row after Telegram accepts it.  Include that append-only
        # stream so a delivered observation is visible even when the same coin
        # already has an older alert_history row.
        scan_by_symbol = {str(sr.get("symbol", "")): sr for sr in scan_rows}
        try:
            prediction_rows = _scan_store.recent_predictions_history(
                limit=500,
                max_age_hours=72,
            )
        except Exception as exc:
            logger.debug("signals_prediction_query_unavailable error=%s", exc)
            prediction_rows = []
            
        try:
            resolved_rows = _scan_store.recent_resolved_predictions(limit=100, max_age_hours=72)
        except Exception as exc:
            logger.debug("signals_resolved_query_unavailable error=%s", exc)
            resolved_rows = []

        # Merge and deduplicate by prediction_id
        pred_dict: dict[str, dict[str, Any]] = {}
        for prediction in prediction_rows:
            raw_prediction_id = prediction.get("prediction_id")
            if raw_prediction_id:
                pred_dict[str(raw_prediction_id)] = prediction
        for rr in resolved_rows:
            raw_prediction_id = rr.get("prediction_id")
            if raw_prediction_id:
                pred_dict[str(raw_prediction_id)] = rr
        prediction_rows = list(pred_dict.values())

        pred_ids = list(pred_dict.keys())
        outcomes_map = _scan_store.get_prediction_outcomes(pred_ids)
        
        # Manually seed outcomes_map with data from recent_resolved_predictions to avoid redundant query
        for rr in resolved_rows:
            raw_prediction_id = rr.get("prediction_id")
            pid = str(raw_prediction_id) if raw_prediction_id else ""
            if pid and pid not in outcomes_map:
                outcomes_map[pid] = {
                    "label_value": rr.get("label_value"),
                    "mfe": rr.get("mfe"),
                    "mae": rr.get("mae"),
                    "outcome_status": rr.get("outcome_status"),
                    "exclusion_reason": rr.get("exclusion_reason"),
                }


        for pr in prediction_rows:
            calibrated_probability = pr.get("calibrated_probability")
            if calibrated_probability is None:
                continue
            try:
                prob = float(calibrated_probability)
            except (TypeError, ValueError):
                continue
            if not 0.0 <= prob <= 1.0:
                continue

            sym = str(pr.get("symbol", ""))
            if not sym:
                continue
            signal_dt = _as_utc_datetime(pr.get("signal_time"))
            observed_dt = _as_utc_datetime(pr.get("created_at")) or signal_dt
            scan = scan_by_symbol.get(sym, {})
            close_price = scan.get("close_price")
            oi_change = scan.get("oi_change_24h")
            funding = scan.get("funding_rate")
            taker_sell = scan.get("taker_sell_ratio")
            anomaly_fields = _anomaly_fields(scan)
            label_target = float(pr.get("target_drawdown") or ACTIVE_TARGET_DRAWDOWN)
            target_drawdown = -abs(label_target * 100.0 if abs(label_target) <= 1.0 else label_target)
            target_price = round(close_price * (1 + target_drawdown / 100.0), 8) if close_price else 0.0
            tier = str(pr.get("tier") or "WAIT")
            risk_level = {
                "HIGH_CONFIDENCE": "HIGH",
                "SHORT_CANDIDATE": "HIGH",
                "WATCH": "MEDIUM",
                "WAIT": "SAFE",
            }.get(tier, _risk_bucket(prob * 100.0))
            invalidation_dt = _as_utc_datetime(pr.get("invalidation_time"))
            if invalidation_dt is None and signal_dt is not None:
                invalidation_dt = signal_dt + timedelta(hours=24)
            pred_v_left = max(
                0.0,
                (invalidation_dt - datetime.now(timezone.utc)).total_seconds() / 3600.0,
            ) if invalidation_dt is not None else 24.0
            pred_setup = _build_signal_trade_setup(
                close_price or 0.0,
                prob=prob,
                target_drawdown=abs(target_drawdown),
                features=scan,
                anomalies=anomaly_fields.get("anomalies"),
                quality_score=pr.get("data_quality_score"),
                signal_score=pr.get("heuristic_score"),
                volume_24h_usd=scan.get("volume_24h_usd"),
                label_version=pr.get("label_version"),
            )
            pred_setup = _apply_stored_execution_policy(
                pred_setup,
                pr.get("execution_policy_json"),
            )
            pred_pat_en, pred_pat_vi = _build_signal_trigger_pattern([], anomaly_fields.get("anomalies"))
            
            pred_two_tier = "FIRED" if prob >= 0.70 else "ARMED" if prob >= 0.35 else "NORMAL"
            pid = pr.get("prediction_id")
            out = outcomes_map.get(pid, {}) if pid else {}
            
            raw_status = out.get("outcome_status")
            lbl = out.get("label_value")
            
            pred_hit = None
            pred_outcome_stat = "UNTRACKED"
            pred_mfe = None
            pred_mae = None
            
            if raw_status == "materialized":
                if lbl == 1:
                    pred_hit = True
                    pred_outcome_stat = "TARGET_HIT"
                else:
                    pred_hit = False
                    pred_outcome_stat = "FAILED"
            elif raw_status == "excluded":
                pred_hit = None
                pred_outcome_stat = "EXCLUDED"
            elif pid:
                pred_outcome_stat = "EXPIRED" if pred_v_left <= 0 else "ACTIVE"
            
            raw_mfe = out.get("mfe")
            raw_mae = out.get("mae")
            if raw_mfe is not None:
                pred_mfe = raw_mfe * -100.0
            if raw_mae is not None:
                pred_mae = raw_mae * 100.0

            signals.append({
                "id": f"prediction-{pid or sym}",
                "symbol": sym,
                "name": sym.replace("USDT", ""),
                "probability": prob,
                "risk_level": risk_level,
                "two_tier_state": pred_two_tier,
                "signal_time": _system_history_timestamp(signal_dt) if signal_dt is not None else str(pr.get("signal_time")),
                "event_time": _system_history_timestamp(observed_dt),
                "telegram_sent_at": _system_history_timestamp(observed_dt) if pr.get("telegram_sent") else None,
                "signal_price": close_price or 0.0,
                "target_drawdown": target_drawdown,
                "target_price": target_price,
                "validity_hours_left": pred_v_left,
                "validity_hours_total": max(
                    0.0,
                    (invalidation_dt - signal_dt).total_seconds() / 3600.0,
                ) if invalidation_dt is not None and signal_dt is not None else 24.0,
                "invalidation_time": _system_history_timestamp(invalidation_dt),
                "lead_time_avg_hours": lead_stats["mean_hours"],
                "oi_change_24h": f"{oi_change:+.1%}" if oi_change is not None else "N/A",
                "taker_sell_ratio": taker_sell if taker_sell is not None else 0.5,
                "funding_rate": f"{funding:+.3%}" if funding is not None else "N/A",
                "rsi_divergence": False,
                "evidence_precision": None,
                "evidence_n_judged": None,
                "hit": pred_hit,
                "outcome_status": pred_outcome_stat,
                "mfe_pct": pred_mfe,
                "mae_pct": pred_mae,
                "trigger_pattern": pred_pat_en,
                "trigger_pattern_vi": pred_pat_vi,
                "trade_setup": pred_setup,
                "telegram_sent": bool(pr.get("telegram_sent")),
                "alert_episode_id": pr.get("alert_episode_id"),
                "episode_role": pr.get("episode_role"),
                "episode_transition": pr.get("episode_transition"),
                "drivers": [],
                **_resolve_market_cap_info(sym, scan.get("volume_24h_usd")),
                **anomaly_fields,
            })

        # Collapse duplicate streams prioritizing predictions (appended last)
        unique_signals = {}
        for s in reversed(signals):
            key = f"{s['symbol']}-{s['signal_time']}"
            if key not in unique_signals:
                unique_signals[key] = s
        signals = list(unique_signals.values())

        # The Radar's primary order is the observation/delivery time.  The
        signals.sort(
            key=lambda s: s.get("event_time") or s.get("signal_time") or "",
            reverse=True,
        )
        with _STATUS_CACHE_LOCK:
            _SIGNALS_RESP_CACHE = signals
            _SIGNALS_RESP_TIME = now_monotonic
        res = signals
        if status_filter == "active":
            res = [s for s in res if s.get("validity_hours_left", 0) > 0]
        elif status_filter == "expired":
            res = [s for s in res if s.get("validity_hours_left", 0) <= 0]
        if dedup_mode in ("true", "symbol", "1"):
            deduped = {}
            for s in res:
                sym = s.get("symbol")
                if sym and sym not in deduped:
                    deduped[sym] = s
            res = list(deduped.values())
        self._set_headers(200)
        self.wfile.write(json.dumps(_dismissals.filter(res), default=str).encode('utf-8'))

    def get_candidates(self):
        rows: list[dict[str, Any]] = []
        data_is_stale = False
        stale_after_minutes = max(
            2 * int(_settings.scanner.poll_interval_minutes),
            int(_settings.scanner.max_heartbeat_age_minutes),
        )

        # Prefer the scanner-published snapshot. The scanner owns DuckDB's
        # writer lock for its whole lifetime on Windows, so a read-only API
        # connection may otherwise be stuck on an old ``.ro_copy`` file.
        snapshot = _read_json(CANDIDATE_SNAPSHOT_PATH)
        snapshot_rows = snapshot.get("rows") if isinstance(snapshot, dict) else None
        timestamp_timezone = "Asia/Ho_Chi_Minh"
        if isinstance(snapshot_rows, list):
            rows = [row for row in snapshot_rows if isinstance(row, dict)]
            timestamp_timezone = str(
                snapshot.get("timestamp_timezone") or timestamp_timezone
            )
            generated_at = snapshot.get("generated_at")
            if isinstance(generated_at, str):
                try:
                    generated_dt = datetime.fromisoformat(
                        generated_at.replace("Z", "+00:00")
                    )
                    if generated_dt.tzinfo is None:
                        generated_dt = generated_dt.replace(tzinfo=timezone.utc)
                    data_is_stale = (
                        datetime.now(timezone.utc) - generated_dt
                    ).total_seconds() > stale_after_minutes * 60
                except ValueError:
                    data_is_stale = True
        else:
            # Normal path when the API can read DuckDB directly.
            rows = _scan_store.latest_per_symbol(limit=200)
            if not rows:
                # Keep the table useful during a scanner outage, but mark the
                # result as stale so an old score is never mistaken for live
                # market data.
                rows = _scan_store.latest_per_symbol(
                    limit=200, max_age_hours=None
                )
                data_is_stale = bool(rows)
            # Legacy DuckDB rows were written while the host timezone was
            # Asia/Saigon. They are only used as an explicitly stale fallback.
            timestamp_timezone = "Asia/Ho_Chi_Minh"

        rows.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
        now = datetime.now(timezone.utc)
        candidates = []
        for row_index, r in enumerate(rows):
            scan_time = r.get("scan_time")
            age_str = "N/A"
            scan_dt: datetime | None = None
            if isinstance(scan_time, datetime):
                scan_dt = scan_time
            elif isinstance(scan_time, str):
                try:
                    scan_dt = datetime.fromisoformat(scan_time.replace("Z", "+00:00"))
                except ValueError:
                    scan_dt = None
            if scan_dt is not None and scan_dt.tzinfo is None:
                if timestamp_timezone.upper() in {"UTC", "Z"}:
                    scan_dt = scan_dt.replace(tzinfo=timezone.utc)
                else:
                    try:
                        scan_dt = scan_dt.replace(
                            tzinfo=ZoneInfo(timestamp_timezone)
                        ).astimezone(timezone.utc)
                    except Exception:
                        scan_dt = scan_dt.replace(tzinfo=timezone.utc)
            row_is_stale = data_is_stale
            if scan_dt is not None:
                age_minutes = (now - scan_dt).total_seconds() / 60.0
                row_is_stale = row_is_stale or age_minutes > stale_after_minutes
                display_age = max(0.0, age_minutes)
                age_str = f"{display_age:.0f}m ago" if display_age < 120 else f"{display_age / 60:.1f}h ago"
            recommendation = str(r.get("recommendation") or "").upper()
            calibrated_probability = r.get("calibrated_probability")
            quality_status = r.get("quality_status")
            data_quality_score = r.get("data_quality_score")
            alertable = bool(
                not row_is_stale
                and recommendation in {"HIGH_CONFIDENCE", "WATCH"}
                and calibrated_probability is not None
                and quality_status == "valid"
            )
            risk = (
                _scan_risk_level(
                    recommendation,
                    float(calibrated_probability or 0.0),
                )
                if recommendation
                else _risk_bucket(r["score"])
            )
            market_cap_info = _resolve_market_cap_info(
                r["symbol"],
                r.get("volume_24h_usd"),
            )
            if (
                row_index < _MARKET_CAP_CANDIDATE_PREFETCH_LIMIT
                and market_cap_info["market_cap_usd"] is None
            ):
                _schedule_market_cap_lookup(
                    r["symbol"],
                    r.get("volume_24h_usd"),
                )

            candidates.append({
                "symbol": r["symbol"],
                "scan_time": _system_history_timestamp(scan_dt) if scan_dt is not None else scan_time,
                "price": r.get("close_price") or 0.0,
                "score": r["score"],
                "risk": risk,
                "recommendation": recommendation or None,
                "model_probability": r.get("model_probability"),
                "calibrated_probability": calibrated_probability,
                "data_quality_score": data_quality_score,
                "quality_status": quality_status,
                "max_feature_age_minutes": r.get("max_feature_age_minutes"),
                "horizon_hours": r.get("horizon_hours"),
                "alertable": alertable,
                "oi_24h": f"{r['oi_change_24h']:+.1%}" if r.get("oi_change_24h") is not None else "N/A",
                "funding": f"{r['funding_rate']:+.3%}" if r.get("funding_rate") is not None else "N/A",
                "taker_ratio": r.get("taker_sell_ratio") if r.get("taker_sell_ratio") is not None else 0.5,
                "volume_24h": f"${r['volume_24h_usd'] / 1e6:.1f}M" if r.get("volume_24h_usd") else "N/A",
                "age": age_str,
                "is_stale": row_is_stale,
                **market_cap_info,
                **_anomaly_fields(r),
            })
        candidates.sort(key=lambda c: c["score"], reverse=True)
        self._set_headers(200)
        self.wfile.write(json.dumps(candidates, default=str).encode('utf-8'))

    def get_candidate_filter_comparison(self):
        """Serve the scanner-published paired v1/v2 audit snapshot."""

        payload = _read_json(CANDIDATE_FILTER_COMPARISON_PATH)
        if not isinstance(payload, dict) or not payload:
            comparison_cfg = _settings.candidate_comparison
            payload = {
                "available": False,
                "enabled": bool(comparison_cfg.enabled),
                "status": "awaiting_scanner_snapshot",
                "champion_version": comparison_cfg.champion_version,
                "challenger_version": comparison_cfg.challenger_version,
                "generated_at": None,
                "stale": True,
            }
        else:
            payload["available"] = True
            generated_at = payload.get("generated_at")
            stale = True
            stale_after_minutes = max(
                2 * int(_settings.scanner.poll_interval_minutes),
                int(_settings.scanner.max_heartbeat_age_minutes),
            )
            if isinstance(generated_at, str):
                try:
                    generated_dt = datetime.fromisoformat(
                        generated_at.replace("Z", "+00:00")
                    )
                    if generated_dt.tzinfo is None:
                        generated_dt = generated_dt.replace(tzinfo=timezone.utc)
                    stale = (
                        datetime.now(timezone.utc) - generated_dt
                    ).total_seconds() > stale_after_minutes * 60
                except ValueError:
                    stale = True
            payload["stale"] = stale

        self._set_headers(200)
        self.wfile.write(json.dumps(payload, default=str).encode("utf-8"))

    def get_shap_analysis(self, symbol: str) -> None:
        """Fail closed: this release does not compute per-observation SHAP."""

        payload = {
            "symbol": symbol,
            "available": False,
            "attribution_method": "none",
            "reason": "shap_not_computed",
            "message": (
                "This release exposes weighted score components as "
                "feature_drivers; it does not compute SHAP values."
            ),
        }
        body = json.dumps(payload).encode("utf-8")
        self._set_headers(501, content_length=len(body))
        self.wfile.write(body)

    def get_coin_detail(self, symbol: str):
        chart_points: list[dict[str, Any]] = []
        closes: list[float] = []
        chart_source = "api"
        display_funding_rate: float | None = None
        display_funding_time: int | None = None
        live_funding_observed_at: int | None = None
        next_funding_time: int | None = None
        funding_interval_ms: int | None = None
        funding_interval_hours = DEFAULT_FUNDING_INTERVAL_HOURS
        funding_interval_source = "default_8h"
        funding_apr_value: float | None = None
        funding_cost_per_1000_usdt: float | None = None
        funding_payer = "unknown"
        funding_source = "unavailable"

        try:
            from concurrent.futures import ThreadPoolExecutor

            from dao_vang.data.collectors.binance_client import BinanceClient

            client = BinanceClient(timeout_seconds=2.0, max_retries=1)

            def _fetch_klines() -> list[Any]:
                try:
                    return client.get("fapi/v1/klines", {"symbol": symbol, "interval": "5m", "limit": 96}) or []
                except Exception:
                    try:
                        spot_client = BinanceClient(base_url="https://api.binance.com", timeout_seconds=2.0, max_retries=1)
                        return spot_client.get("api/v3/klines", {"symbol": symbol, "interval": "5m", "limit": 96}) or []
                    except Exception:
                        return []

            def _fetch_funding() -> list[Any]:
                try:
                    return client.get("fapi/v1/fundingRate", {"symbol": symbol, "limit": 200}) or []
                except Exception:
                    return []

            def _fetch_live_funding() -> Any:
                try:
                    return client.get("fapi/v1/premiumIndex", {"symbol": symbol})
                except Exception:
                    return None

            def _fetch_funding_info() -> Any:
                try:
                    return client.get("fapi/v1/fundingInfo")
                except Exception:
                    return None

            def _fetch_oi() -> list[Any]:
                try:
                    return client.get("/futures/data/openInterestHist", {"symbol": symbol, "period": "5m", "limit": 96}) or []
                except Exception:
                    return []

            with ThreadPoolExecutor(max_workers=4) as executor:
                f_k = executor.submit(_fetch_klines)
                f_f = executor.submit(_fetch_funding)
                f_l = executor.submit(_fetch_live_funding)
                f_i = executor.submit(_fetch_funding_info)
                f_o = executor.submit(_fetch_oi)
                try:
                    data = f_k.result(timeout=2.5)
                except Exception:
                    data = []
                try:
                    funding_raw = f_f.result(timeout=2.5)
                except Exception:
                    funding_raw = []
                try:
                    live_funding_raw = f_l.result(timeout=2.5)
                except Exception:
                    live_funding_raw = None
                try:
                    funding_info_raw = f_i.result(timeout=2.5)
                except Exception:
                    funding_info_raw = None
                try:
                    oi_raw = f_o.result(timeout=2.5)
                except Exception:
                    oi_raw = []

            funding_points = _parse_funding_history(funding_raw)
            live_funding_rate, next_funding_time, live_funding_observed_at = _parse_live_funding(
                live_funding_raw,
                symbol,
            )
            funding_info_interval_hours = _parse_funding_interval_info(funding_info_raw, symbol)
            history_interval_ms = _infer_funding_interval_ms(funding_points[-25:])
            history_interval_hours = (
                history_interval_ms / 3_600_000
                if history_interval_ms is not None
                else None
            )
            if funding_info_interval_hours is not None:
                funding_interval_hours = funding_info_interval_hours
                funding_interval_source = "binance_funding_info"
            elif history_interval_hours is not None and 0 < history_interval_hours <= 24:
                funding_interval_hours = round(history_interval_hours, 2)
                funding_interval_source = "history_inferred"
            funding_interval_ms = int(round(funding_interval_hours * 3_600_000))
            # Keep a feed fresh for at most two observed settlement intervals.
            # The fallback covers a newly listed symbol with no adjustment info
            # and keeps the default at Binance's standard eight-hour cadence.
            funding_max_age_ms = max(
                12 * 60 * 60 * 1000,
                funding_interval_ms * 2,
            )
            history_current = _funding_asof(
                funding_points,
                int(time.time() * 1000),
                max_age_ms=funding_max_age_ms,
            )
            display_funding_rate = (
                live_funding_rate
                if live_funding_rate is not None
                else history_current[0]
                if history_current is not None
                else None
            )
            # The settlement timestamp belongs to the history value.  Keep it
            # empty when history is unavailable instead of borrowing an
            # unrelated/future event for the live premium-index value.
            display_funding_time = history_current[1] if history_current else None
            funding_source = (
                "binance_premium_index"
                if live_funding_rate is not None
                else "binance_funding_history"
                if history_current is not None
                else "unavailable"
            )
            funding_apr_value = _funding_apr(display_funding_rate, funding_interval_hours)
            funding_cost_per_1000_usdt = (
                abs(display_funding_rate * 1_000.0)
                if display_funding_rate is not None
                else None
            )
            funding_payer = _funding_payer(display_funding_rate)

            oi_snapshots: list[tuple[int, float]] = []
            for item in oi_raw:
                if isinstance(item, dict) and "timestamp" in item:
                    oi_snapshots.append((int(item["timestamp"]), float(item.get("sumOpenInterest", 0.0))))
            oi_first = oi_snapshots[0][1] if oi_snapshots else 0.0

            for k in data:
                ts = int(k[0])
                dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                display_dt = as_system_timezone(dt)
                c = float(k[4])
                closes.append(c)

                # Funding is a point-in-time settlement observation.  Carry
                # forward only the latest event already known at this candle;
                # never attach a future settlement to an earlier candle.
                funding_point = _funding_asof(
                    funding_points,
                    ts,
                    max_age_ms=funding_max_age_ms,
                )
                funding = funding_point[0] if funding_point is not None else None

                # nearest OI snapshot (within 5m)
                oi_val = 0.0
                if oi_snapshots:
                    nearest_ts = min((t for t, _ in oi_snapshots), key=lambda x: abs(x - ts))
                    if abs(nearest_ts - ts) <= 300_000:
                        oi_val = next(v for t, v in oi_snapshots if t == nearest_ts)
                # Show OI as % change vs first OI in the fetched window
                oi_pct = round((oi_val / oi_first - 1.0) * 100.0, 2) if oi_first > 0 and oi_val > 0 else 0.0

                chart_points.append({
                    "time": display_dt.strftime("%H:%M"),
                    "time_iso": display_dt.isoformat(),
                    "price": c,
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": c,
                    "volume": float(k[5]),
                    "oi": oi_pct,
                    "funding": funding,
                    "taker_ratio": 0.5,
                    "is_signal_point": False,
                })
        except Exception as exc:
            logger.warning(f"coin_detail_api_fetch_failed symbol={symbol} error={exc}")

        # Compute RSI-14 on 5m closes (standard Wilder's RSI)
        rsi_15m: float | None = None
        if len(closes) >= 15:
            gains = []
            losses = []
            for i in range(1, len(closes)):
                diff = closes[i] - closes[i - 1]
                gains.append(max(diff, 0.0))
                losses.append(max(-diff, 0.0))
            avg_gain = sum(gains[:14]) / 14.0
            avg_loss = sum(losses[:14]) / 14.0
            for i in range(14, len(gains)):
                avg_gain = (avg_gain * 13 + gains[i]) / 14.0
                avg_loss = (avg_loss * 13 + losses[i]) / 14.0
            if avg_loss > 0:
                rs = avg_gain / avg_loss
                rsi_15m = round(100.0 - (100.0 / (1.0 + rs)), 1)
            else:
                rsi_15m = 100.0

        # Volume delta: calculate from chart_points if available
        vol_delta_str = "N/A"
        if len(chart_points) >= 2:
            recent_vols = [p["volume"] for p in chart_points[-12:]]  # last 1h
            earlier_vols = [p["volume"] for p in chart_points[:12]]
            if earlier_vols and sum(earlier_vols) > 0:
                v_ratio = (sum(recent_vols) / sum(earlier_vols) - 1.0)
                vol_delta_str = f"{v_ratio:+.0%}"

        alert_rows = _alert_store.query(symbol=symbol, days=2, include_dismissed=True, limit=1)
        latest_alert = alert_rows[0] if alert_rows else None
        latest_scan = _scan_store.latest_for_symbol(symbol, max_age_hours=24)
        market_cap_info = _resolve_market_cap_info(
            symbol,
            latest_scan.get("volume_24h_usd") if latest_scan else None,
            fetch_remote=True,
        )

        current_price = chart_points[-1]["price"] if chart_points else 0.0
        components: list[dict[str, Any]] = []
        if latest_alert and latest_alert.get("components_json"):
            try:
                parsed_components = json.loads(latest_alert["components_json"])
                if isinstance(parsed_components, list):
                    components = [
                        item for item in parsed_components if isinstance(item, dict)
                    ]
            except (json.JSONDecodeError, TypeError):
                components = []
        feature_drivers = _component_feature_drivers(components)

        if latest_alert:
            score_source = "alert"
            score_value = latest_alert["probability"] * 100.0
            risk_level = _risk_bucket(score_value)
            sig_time = latest_alert["signal_time"]
        elif latest_scan:
            score_source = "scan"
            calibrated_probability = latest_scan.get("calibrated_probability")
            if calibrated_probability is not None:
                score_value = float(calibrated_probability) * 100.0
                risk_level = _scan_risk_level(
                    latest_scan.get("recommendation"), float(calibrated_probability)
                )
            else:
                # Legacy scan rows without a model probability must not be
                # presented as if their heuristic score were a probability.
                score_value = None
                risk_level = None
            sig_time = latest_scan["scan_time"]
        else:
            score_source = None
            score_value = None
            risk_level = None
            sig_time = None

        signal_display_time = _system_display_datetime(sig_time) if latest_alert else None
        target_drawdown = -(_current_model_target_drawdown() * 100.0)
        detail = {
            "symbol": symbol,
            "name": market_cap_info.get("cmc_name") or symbol.replace("USDT", ""),
            **market_cap_info,
            "current_price": current_price,
            "chart_source": chart_source,
            "has_alert": bool(latest_alert),
            "score_source": score_source,
            "probability": score_value,
            "risk_level": risk_level,
            "target_drawdown": target_drawdown,
            "target_price": round(current_price * (1 + target_drawdown / 100.0), 8) if current_price else 0.0,
            "signal_timestamp": (
                f"{signal_display_time.strftime('%Y-%m-%d %H:%M:%S')} UTC+7"
                if signal_display_time is not None
                else None
            ),
            "chart_data": chart_points,
            "metrics": {
                "oi_change_24h": f"{chart_points[-1]['oi']:+.1%}" if chart_points else "N/A",
                "taker_sell_ratio": chart_points[-1]["taker_ratio"] if chart_points else 0.5,
                "funding_rate": _format_funding_rate(display_funding_rate),
                "funding_rate_source": funding_source,
                "funding_rate_time": (
                    _system_history_timestamp(
                        datetime.fromtimestamp(display_funding_time / 1000, tz=timezone.utc)
                    )
                    if display_funding_time is not None
                    else None
                ),
                "funding_rate_observed_at": (
                    _system_history_timestamp(
                        datetime.fromtimestamp(live_funding_observed_at / 1000, tz=timezone.utc)
                    )
                    if live_funding_observed_at is not None
                    else None
                ),
                "funding_next_time": (
                    _system_history_timestamp(
                        datetime.fromtimestamp(next_funding_time / 1000, tz=timezone.utc)
                    )
                    if next_funding_time is not None
                    else None
                ),
                "funding_interval_source": funding_interval_source,
                "funding_interval_hours": (
                    round(funding_interval_hours, 2)
                    if funding_interval_hours is not None
                    else None
                ),
                "funding_periods_per_year": (
                    round(365.0 * 24.0 / funding_interval_hours, 2)
                    if funding_interval_hours and funding_interval_hours > 0
                    else None
                ),
                "funding_apr": _format_funding_rate(funding_apr_value),
                "funding_apr_value": funding_apr_value,
                "funding_cost_per_1000_usdt": funding_cost_per_1000_usdt,
                "funding_payer": funding_payer,
                "rsi_15m": rsi_15m,
                "volume_delta_24h": vol_delta_str,
            },
            "attribution_method": (
                "component_weight" if feature_drivers else "none"
            ),
            "feature_drivers": feature_drivers,
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(detail, default=str).encode('utf-8'))

    def get_deep_analysis(self, symbol: str):
        """Deep analysis endpoint — rerun the same serving contract as Radar.

        The frozen model probability is the decision value.  The 8-component
        composite score is returned separately as an explanation/diagnostic
        value, so the UI never compares two different metrics as if they were
        the same probability.
        """
        import pandas as pd

        from dao_vang.experiments.forward_test import load_frozen_model

        now_utc = datetime.now(timezone.utc)
        candle_bucket = now_utc.replace(
            minute=(now_utc.minute // 5) * 5,
            second=0,
            microsecond=0,
        )
        latest_closed_5m_end = candle_bucket - timedelta(milliseconds=1)

        # 1. Fetch latest features for this symbol — JOIN kline for close price
        feature_dict: dict[str, Any] = {}
        close_price: float | None = None
        feature_time: datetime | None = None
        try:
            conn = _ro_duckdb_connect(str(_settings.scanner.db_path))
            try:
                df = conn.execute(
                    """
                    SELECT * FROM feature_results
                    WHERE symbol = ?
                      AND feature_time <= ?
                    ORDER BY feature_time DESC LIMIT 1
                    """,
                    [symbol, latest_closed_5m_end],
                ).df()
                if not df.empty:
                    latest = df.iloc[0]
                    for col in df.columns:
                        val = latest[col]
                        if pd.notna(val):
                            feature_dict[col] = val
                    ft_raw = latest.get("feature_time")
                    if pd.notna(ft_raw):
                        feature_time = _as_utc_datetime(ft_raw)
            finally:
                conn.close()

            # Retrieve price from latest scan or alert store
            latest_scan = _scan_store.latest_for_symbol(symbol, max_age_hours=24)
            if latest_scan and latest_scan.get("close_price"):
                close_price = float(latest_scan["close_price"])
        except Exception as exc:
            logger.warning(f"deep_analysis_feature_query_failed symbol={symbol} error={exc}")

        # 2. Compute BTC context
        btc_context = None
        try:
            conn = _ro_duckdb_connect(str(_settings.scanner.db_path))
            try:
                btc_df = conn.execute(
                    """
                    SELECT * FROM feature_results
                    WHERE symbol = 'BTCUSDT'
                      AND feature_time <= ?
                    ORDER BY feature_time DESC LIMIT 1
                    """,
                    [latest_closed_5m_end],
                ).df()
                if not btc_df.empty:
                    row = btc_df.iloc[0]
                    btc_context = classify_btc(
                        btc_ret_24h=float(row.get("price_ret_24h", 0.0)),
                        btc_ret_4h=float(row.get("price_ret_4h", 0.0)),
                        btc_ret_1h=float(row.get("price_ret_5m", 0.0)),
                        config=_settings.scoring,
                    )
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(f"deep_analysis_btc_context_failed error={exc}")

        if btc_context is None:
            btc_context = classify_btc(0.0, 0.0, 0.0, _settings.scoring)

        # 3. Fetch daily klines for pump analysis
        pump_analysis: dict[str, Any] = {
            "detected": False,
            "pump_pct": 0.0,
            "pump_days": 0,
            "peak_price": 0.0,
            "current_price": 0.0,
            "current_vs_peak": 0.0,
            "quote_volume": 0.0,
        }
        try:
            daily_klines = fetch_daily_klines(symbol, days=7)
            if daily_klines:
                pump_cfg = _settings.pump_filter
                candidate = analyze_pump(
                    daily_klines,
                    min_pump_pct=pump_cfg.min_pump_pct,
                    max_pump_pct=pump_cfg.max_pump_pct,
                    dump_threshold=pump_cfg.dump_threshold,
                )
                if candidate:
                    pump_analysis = {
                        "detected": True,
                        "pump_pct": round(candidate.pump_pct * 100, 1),
                        "pump_days": candidate.pump_days,
                        "peak_price": candidate.peak_price,
                        "current_price": candidate.current_price,
                        "current_vs_peak": round(candidate.current_vs_peak * 100, 1),
                        "quote_volume": candidate.quote_volume,
                    }
        except Exception as exc:
            logger.warning(f"deep_analysis_pump_failed symbol={symbol} error={exc}")

        # 4. Compute the same frozen serving score used by Radar.  Keep the
        # heuristic composite alongside it for the component breakdown.
        anomaly_report = detect_market_anomalies(
            feature_dict,
            _settings.market_anomalies,
        )
        frozen_result = None
        frozen_model_error: str | None = None
        heartbeat = _read_json(HEARTBEAT_PATH)
        frozen_model_id = heartbeat.get("model_id") or _settings.scanner.frozen_model_id
        if frozen_model_id:
            try:
                frozen_info = load_frozen_model(
                    frozen_model_id,
                    Path(_settings.scanner.artifact_dir),
                )
                quality = assess_snapshot_quality(
                    feature_dict,
                    frozen_info,
                    now=now_utc,
                    max_feature_age_minutes=_settings.scanner.max_feature_age_minutes,
                    min_data_quality_score=_settings.scanner.min_data_quality_score,
                )
                frozen_result = score_snapshot(
                    symbol=symbol,
                    feature_dict=feature_dict,
                    btc_context=btc_context,
                    frozen_info=frozen_info,
                    config=_settings.scoring,
                    threshold_policy=_settings.threshold,
                    pump_pct=pump_analysis["pump_pct"] / 100.0
                    if pump_analysis["detected"]
                    else 0.0,
                    pump_days=pump_analysis["pump_days"],
                    quality=quality,
                    max_feature_age_minutes=_settings.scanner.max_feature_age_minutes,
                    min_data_quality_score=_settings.scanner.min_data_quality_score,
                )
            except Exception as exc:
                frozen_model_error = str(exc)
                logger.warning(
                    f"deep_analysis_frozen_score_failed symbol={symbol} error={exc}"
                )

        if frozen_result is not None:
            score = frozen_result.heuristic
        else:
            score = compute_distribution_score(
                symbol=symbol,
                features=feature_dict,
                btc=btc_context,
                config=_settings.scoring,
                pump_pct=pump_analysis["pump_pct"] / 100.0
                if pump_analysis["detected"]
                else 0.0,
                pump_days=pump_analysis["pump_days"],
            )

        model_recommendation = score.recommendation
        if frozen_result is not None:
            model_recommendation = {
                "HIGH_CONFIDENCE": "SHORT_CANDIDATE",
                "WATCH": "WATCH",
                "WAIT": "WAIT",
            }.get(frozen_result.risk_tier, "WAIT")

        # 5. Build component breakdown
        components = [
            {
                "name": c.name.replace("_", " ").title(),
                "raw_name": c.name,
                "raw_value": round(c.raw_value, 4) if isinstance(c.raw_value, (int, float)) else c.raw_value,
                "score": round(c.score, 1),
                "weight": round(c.weight * 100, 1),
                "weighted_score": round(c.weighted_score, 1),
                "explanation": c.explanation,
            }
            for c in score.components
        ]

        # 6. Build RSI multi-timeframe from live closes
        rsi_data: dict[str, Any] = {}
        try:
            from dao_vang.data.collectors.binance_client import BinanceClient
            b_client = BinanceClient(timeout_seconds=3.0, max_retries=1)
            k_data = b_client.get("fapi/v1/klines", {"symbol": symbol, "interval": "5m", "limit": 100}) or []
            if len(k_data) >= 14:
                close_vals = [float(k[4]) for k in k_data]
                if close_price is None and close_vals:
                    close_price = close_vals[-1]
                for period, label in [(14, "rsi_14"), (7, "rsi_7")]:
                    if len(close_vals) >= period:
                        gains = []
                        losses = []
                        for i in range(1, len(close_vals)):
                            diff = close_vals[i] - close_vals[i - 1]
                            gains.append(max(diff, 0))
                            losses.append(max(-diff, 0))
                        avg_gain = sum(gains[-period:]) / period
                        avg_loss = sum(losses[-period:]) / period
                        if avg_loss == 0:
                            rsi_data[label] = 100.0
                        else:
                            rs = avg_gain / avg_loss
                            rsi_data[label] = round(100 - (100 / (1 + rs)), 1)
        except Exception as exc:
            logger.warning(f"deep_analysis_rsi_failed symbol={symbol} error={exc}")

        # 7. Compute Two-Tier Climax & Realtime Order Flow score
        two_tier_score = compute_two_tier_distribution_score(
            symbol=symbol,
            features=feature_dict,
            btc=btc_context,
            config=_settings.scoring,
            pump_pct=pump_analysis["pump_pct"] / 100.0 if pump_analysis["detected"] else 0.0,
            pump_days=pump_analysis["pump_days"],
        )

        # 8. Build result
        result = {
            "symbol": symbol,
            "analysis_time": system_now().isoformat(),
            "feature_time": _system_history_timestamp(feature_time),
            "current_price": close_price,
            "total_score": round(score.total_score, 1),
            "heuristic_score": round(score.total_score, 1),
            "heuristic_recommendation": score.recommendation,
            "recommendation": model_recommendation,
            "model_probability": (
                round(frozen_result.model_probability, 4)
                if (frozen_result is not None and frozen_result.model_probability is not None)
                else None
            ),
            "calibrated_probability": (
                round(frozen_result.calibrated_probability, 4)
                if (frozen_result is not None and frozen_result.calibrated_probability is not None)
                else round(score.total_score / 100.0, 4)
            ),
            "two_tier_analysis": two_tier_score.to_dict(),
            "risk_tier": frozen_result.risk_tier if frozen_result is not None else None,
            "probability_threshold": (
                frozen_result.threshold if frozen_result is not None else None
            ),
            "quality_status": (
                frozen_result.quality.status if frozen_result is not None else None
            ),
            "frozen_model_id": frozen_model_id,
            "frozen_model_error": frozen_model_error,
            "btc_regime": btc_context.regime,
            "btc_explanation": btc_context.explanation,
            "btc_score_adjustment": round(btc_context.score_adjustment, 1),
            "components": components,
            "anomaly_score": anomaly_report.score,
            "anomaly_level": anomaly_report.level,
            "anomaly_count": len(anomaly_report.anomalies),
            "anomaly_categories": list(anomaly_report.categories),
            "anomalies": [item.to_dict() for item in anomaly_report.anomalies],
            "pump_analysis": pump_analysis,
            "rsi": rsi_data,
            "threshold": _settings.scoring.alert_score_threshold,
            "has_features": len(feature_dict) > 0,
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(result, default=str).encode('utf-8'))

    def get_coin_klines(self, symbol, interval='5m', limit=100):
        """Compatibility route sharing the validated chart implementation."""
        self.get_coin_chart(symbol, requested_interval=interval, requested_limit=limit)

    def get_coin_chart(self, symbol: str, requested_interval=None, requested_limit=None):
        """Fetch recent klines for mini chart display.

        Accepts ``interval`` query param (e.g. 1m, 5m, 15m, 1h, 4h, 1d).
        """
        from urllib.parse import parse_qs

        from dao_vang.data.collectors.binance_client import BinanceClient

        query = parse_qs(urlparse(self.path).query)
        raw_interval = requested_interval or query.get('interval', ['1h'])[0]
        valid_intervals = {'1m','3m','5m','15m','30m','1h','2h','4h','6h','8h','12h','1d','3d','1w','1M'}
        interval = raw_interval if raw_interval in valid_intervals else '1h'
        # Target roughly 1-7 days of history depending on interval
        limits = {
            # Keep enough history for the radar's 7-day alert window. Binance
            # accepts up to 1500 klines per request.
            '1m': 1500, '3m': 1500, '5m': 1500, '15m': 672,
            '30m': 336, '1h': 168, '2h': 126, '4h': 126,
            '6h': 120, '8h': 90, '12h': 90, '1d': 90,
        }
        limit = max(1, min(1500, requested_limit)) if requested_limit is not None else limits.get(interval, 168)

        try:
            client = BinanceClient()
            data = client.get("fapi/v1/klines", {
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            })
            klines = [
                {
                    "time": k[0],
                    "time_str": as_system_timezone(
                        datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc)
                    ).strftime("%m-%d %H:%M"),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                }
                for k in data
            ]
            self._set_headers(200)
            self.wfile.write(json.dumps({"symbol": symbol, "interval": interval, "klines": klines}).encode('utf-8'))
        except Exception as exc:
            logger.warning(f"coin_chart_failed symbol={symbol} error={exc}")
            self._set_headers(200)
            self.wfile.write(json.dumps({"symbol": symbol, "interval": interval, "klines": [], "error": str(exc)}).encode('utf-8'))

    def get_audit(self):
        """Expose measured live outcomes and explicitly scoped historical reports."""
        try:
            stats = _alert_store.stats(days=30)
            by_risk = _alert_store.precision_by_risk_level(days=30)
            lead = _alert_store.lead_time_stats(days=30)
        except Exception as exc:
            logger.warning("audit_data_fetch_failed error=%s", exc)
            stats, by_risk, lead = {}, {}, {}

        # stats() limits hit rate to Telegram-sent alerts; the audit covers all
        # alerts, matching the risk breakdown and lead-time queries.
        n_judged = sum(row.get("n_judged", 0) for row in by_risk.values())
        n_hit = sum(row.get("n_hit", 0) for row in by_risk.values())
        report = _read_json(_settings.scanner.artifact_dir / "backtest_report_latest.json")
        report = report if isinstance(report, dict) else {}
        wf = report.get("walk_forward_10_fold", {})
        validation = report.get("validation_checks", {})
        current_model = _settings.scanner.frozen_model_id
        baseline = wf.get("mean_logreg_precision")
        precision = wf.get("mean_lightgbm_precision")
        gain = ((precision / baseline - 1) * 100
                if isinstance(precision, (float, int)) and isinstance(baseline, (float, int)) and baseline > 0
                else None)
        res = {
            "model_name": current_model or "Chưa cấu hình mô hình",
            "horizon": "Theo từng mô hình",
            "target_drawdown": "Theo từng mô hình",
            "mae_allowed": "Theo từng mô hình",
            "sample_size": n_judged,
            "total_alerts": stats.get("total", 0),
            "has_enough_data": n_judged > 0,
            "live_scope": "all_models_last_30_days",
            "report_available": bool(report),
            "report_generated_at": report.get("generated_at"),
            "report_model_id": report.get("model_id"),
            "report_matches_current_model": bool(current_model and report.get("model_id") == current_model),
            "metrics": {
                "precision": n_hit / n_judged if n_judged else None,
                "walk_forward_precision": precision,
                "ci_95_lower": wf.get("ci_95_lower"),
                "ci_95_upper": wf.get("ci_95_upper"),
                "brier_score": wf.get("mean_lightgbm_brier"),
                "ece": wf.get("mean_lightgbm_ece"),
                "logreg_baseline_precision": baseline,
                "relative_gain_pct": gain,
            },
            "precision_by_risk_level": by_risk,
            "lead_time": {key: lead.get(key) for key in ("mean_hours", "median_hours", "min_hours", "max_hours")},
            "regime_performance": {
                key: value for key, value in report.get("regime_performance", {}).items()
                if value.get("samples", value.get("n_eval", 0)) > 0
            },
            "feature_importance_ranking": report.get("feature_importance_ranking", []),
            "stress_test_events": [event for event in report.get("stress_test_events", []) if event.get("samples", 0) > 0],
            "walk_forward_folds": wf.get("folds", []),
            "quality_gates": report.get("quality_gates", {}),
            "validation_checks": {
                "walk_forward_status": validation.get("walk_forward_status", "Chưa có kết luận xác thực"),
                "leakage_test": validation.get("leakage_test", "Chưa có kết quả"),
                "embargo_period": validation.get("embargo_period", "Chưa có kết quả"),
                "point_in_time_verified": validation.get("point_in_time_verified") is True,
            },
        }
        body = json.dumps(res, default=str).encode("utf-8")
        self._set_headers(200, content_length=len(body))
        self.wfile.write(body)

    def get_market(self):
        from dao_vang.data.binance_listing import DEFAULT_HISTORY_PATH as _LISTING_HIST
        from dao_vang.data.binance_listing import load_history as _load_listing_history

        listing = get_stats_for_today(auto_scan=False)
        cycle_stats = _scan_store.latest_cycle_stats()
        latest_scores = _scan_store.latest_per_symbol(limit=500)
        avg_score = (
            sum(r["score"] for r in latest_scores) / len(latest_scores)
            if latest_scores else None
        )

        # Binance listing history for chart
        listing_history: list[dict[str, Any]] = []
        try:
            listing_history = _load_listing_history(_LISTING_HIST)
        except Exception as exc:
            logger.warning(f"market_listing_history_failed error={exc}")

        try:
            gainers = fetch_top_gainers(limit=50)
            losers = fetch_top_losers(limit=50)
        except Exception as exc:
            logger.warning(f"market_tickers_fetch_failed error={exc}")
            gainers, losers = [], []

        if avg_score is None:
            market_regime = "Chưa có dữ liệu"
        elif avg_score >= 60:
            market_regime = "High Distribution Pressure"
        elif avg_score >= 40:
            market_regime = "Moderate Distribution Pressure"
        else:
            market_regime = "Low Distribution Pressure"

        def _ticker_entry(t):
            return {
                "symbol": t["symbol"],
                "change": f"{float(t.get('priceChangePercent', 0)):+.1f}%",
                "price": float(t.get("lastPrice", 0)),
                "volume_24h": float(t.get("quoteVolume", 0)),
            }

        try:
            macro_climate = _fetch_live_regime()
        except Exception as exc:
            logger.warning("market_regime_unavailable error=%s", exc)
            macro_climate = {
                "available": False,
                "source": "binance_futures_btcusdt_1h",
                "regime": "UNKNOWN",
                "regime_label_vi": "Chưa có dữ liệu thời gian thực",
                "regime_label_en": "Live regime unavailable",
            }
        meta_mode = _settings.scanner.enable_meta_labeling
        macro_climate["meta_labeling"] = meta_mode.upper()
        macro_climate["drift_guardian"] = "NOT_EVALUATED"

        res = {
            "binance_listing_total": listing.get("all_coins"),
            "binance_listing": {
                "spot_coins": listing.get("spot_coins", 0),
                "usdm_coins": listing.get("usdm_coins", 0),
                "coinm_coins": listing.get("coinm_coins", 0),
                "futures_coins": listing.get("futures_coins", 0),
                "all_coins": listing.get("all_coins", 0),
                "spot_only": listing.get("spot_only", 0),
                "futures_only": listing.get("futures_only", 0),
                "both": listing.get("both", 0),
                "spot_symbols": listing.get("spot_symbols", 0),
                "spot_usdt_pairs": listing.get("spot_usdt_pairs", 0),
                "usdm_symbols": listing.get("usdm_symbols", 0),
                "usdm_usdt_pairs": listing.get("usdm_usdt_pairs", 0),
                "coinm_symbols": listing.get("coinm_symbols", 0),
                "date": listing.get("date", ""),
                "fetched_at": listing.get("fetched_at", ""),
            },
            "binance_listing_history": [
                {
                    "date": h.get("date", ""),
                    "spot_coins": h.get("spot_coins", 0),
                    "usdm_coins": h.get("usdm_coins", 0),
                    "coinm_coins": h.get("coinm_coins", 0),
                    "futures_coins": h.get("futures_coins", 0),
                    "all_coins": h.get("all_coins", 0),
                    "fetched_at": h.get("fetched_at", ""),
                }
                for h in listing_history
            ],
            "scanned_volatile_top": cycle_stats.get("n_symbols", 0),
            "market_regime": market_regime,
            "distribution_index": round(avg_score, 1) if avg_score is not None else None,
            "macro_climate": macro_climate,
            "top_gainers": [_ticker_entry(t) for t in gainers],
            "top_losers": [_ticker_entry(t) for t in losers],
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(res, default=str).encode('utf-8'))

    def get_alpha_lab_regime(self):
        """Get real-time market regime analysis from Binance Futures."""
        try:
            res = _fetch_live_regime()
            self._set_headers(200)
            self.wfile.write(json.dumps(res, default=str).encode('utf-8'))
        except Exception as exc:
            logger.warning(f"alpha_lab_regime_failed error={exc}")
            res = {
                "available": False,
                "source": "binance_futures_btcusdt_1h",
                "regime": "UNKNOWN",
                "reason": "live_regime_unavailable",
            }
            self._set_headers(503)
            self.wfile.write(json.dumps(res).encode('utf-8'))

    def get_alpha_lab_drift(self):
        """Get Drift Guardian stability and calibration metrics."""
        from dao_vang.alpha_lab.drift_guardian import DriftGuardian

        conn = None
        try:
            conn = open_read_only_connection(str(_settings.scanner.db_path))
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT table_name FROM information_schema.tables"
                ).fetchall()
            }
            if "feature_results" in tables:
                df = conn.execute(
                    "SELECT * FROM feature_results ORDER BY feature_time DESC LIMIT 200"
                ).df()
                if len(df) >= 20:
                    guardian = DriftGuardian()
                    guardian.set_baseline(df.iloc[: len(df) // 2])
                    report = guardian.evaluate_health(df.iloc[len(df) // 2 :])
                    res = report.to_dict()
                    res["available"] = True
                    self._set_headers(200)
                    self.wfile.write(json.dumps(res, default=str).encode('utf-8'))
                    return
        except Exception as exc:
            logger.warning(f"alpha_lab_drift_db_failed error={exc}")
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

        # Never fabricate a healthy status when there is no evaluable sample.
        res = {
            "available": False,
            "status": "UNKNOWN",
            "reason": "insufficient_feature_history",
            "max_psi": None,
            "feature_psi": {},
            "brier_score": None,
            "ece": None,
            "alert_messages": [],
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(res, default=str).encode('utf-8'))

    def get_alpha_lab_summary(self):
        """Get consolidated Alpha Lab dashboard overview."""
        try:
            regime_dict = _fetch_live_regime(limit=50)
        except Exception as exc:
            logger.warning(f"alpha_lab_summary_regime_failed error={exc}")
            regime_dict = {
                "available": False,
                "regime": "UNKNOWN",
                "reason": "live_regime_unavailable",
            }

        meta_mode = _settings.scanner.enable_meta_labeling
        res = {
            "regime": regime_dict,
            "meta_labeling": {
                "enabled": meta_mode != "disabled",
                "mode": meta_mode,
                "threshold": _settings.scanner.meta_model_min_confidence,
                "model_configured": bool(_settings.scanner.meta_model_path),
                "model_status": meta_mode.upper(),
                "estimated_drop_rate": None,
            },
            "drift_guardian": {
                "available": False,
                "status": "NOT_EVALUATED",
                "alpha_decay_risk": None,
                "monitoring_window": None,
            },
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(res, default=str).encode('utf-8'))

    def get_multi_coin_scan(self):
        """Multi-coin scan results — reads volatile experiment artifacts + scan DB.

        Returns scan history (grouped by run), coin list with latest results,
        and per-coin detail (status, AI precision vs baseline, CI, leakage).
        Mirrors the Streamlit multi-coin scan tab logic.
        """
        import duckdb as _duckdb

        from dao_vang.experiments.artifacts import ArtifactRegistry

        scan_db_path = "./data/scan_volatile.duckdb"
        coin_stats: list[dict[str, Any]] = []
        has_db = Path(scan_db_path).exists()
        if has_db:
            try:
                conn = _duckdb.connect(scan_db_path, read_only=True)
                try:
                    label_table_row = conn.execute(
                        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'labels'"
                    ).fetchone()
                    has_labels = bool(
                        label_table_row is not None
                        and int(label_table_row[0] or 0) > 0
                    )
                    if has_labels:
                        rows = conn.execute("""
                            SELECT symbol, count(*) AS total,
                                   sum(CASE WHEN label_value = 1 THEN 1 ELSE 0 END) AS pos,
                                   sum(CASE WHEN label_value = 0 THEN 1 ELSE 0 END) AS neg,
                                   min(signal_time) AS first_ts,
                                   max(signal_time) AS last_ts
                            FROM labels GROUP BY symbol ORDER BY pos DESC
                        """).fetchall()
                        for sym, total, pos, neg, first_ts, last_ts in rows:
                            coin_stats.append({
                                "symbol": sym, "total": total, "pos": pos, "neg": neg,
                                "first_ts": _system_history_timestamp(first_ts),
                                "last_ts": _system_history_timestamp(last_ts),
                            })
                finally:
                    conn.close()
            except Exception as exc:
                logger.warning(f"multi_coin_scan_db_failed error={exc}")

        # Load artifacts
        registry = ArtifactRegistry(Path("./artifacts"))
        all_artifacts = registry.list_artifacts()
        scan_artifacts = [
            a for a in all_artifacts
            if "volatile" in a.get("data", {}).get("config", {}).get("hypothesis_id", "")
        ]

        # Group by run (YYYY-MM-DDTHH)
        scan_runs: dict[str, list[dict]] = {}
        for a in scan_artifacts:
            created_at = system_iso(a.get("created_at")) or ""
            created = created_at[:13]
            scan_runs.setdefault(created, []).append(a)

        # Build run history
        run_history = []
        for run_time, arts in sorted(scan_runs.items(), reverse=True):
            best_p = 0.0
            best_sym = ""
            n_edge = 0
            n_valid = 0
            for a in arts:
                data = a.get("data", {})
                res = data.get("results", {})
                agg = res.get("aggregate", {})
                baselines = res.get("baselines", {})
                leak = res.get("leakage_report", {})
                mp = agg.get("precision_mean", 0)
                bp = max((m.get("precision_mean", 0) for m in baselines.values()), default=0)
                nv = agg.get("n_valid_folds", 0)
                ls = leak.get("status", "?")
                sym = data.get("config", {}).get("hypothesis_id", "").replace("hyp_volatile_", "")
                if nv > 0:
                    n_valid += 1
                if ls == "passed" and mp > bp and mp > 0:
                    n_edge += 1
                if mp > best_p:
                    best_p = mp
                    best_sym = sym
            run_history.append({
                "run_time": run_time.replace("T", " "),
                "n_coins": len(arts),
                "n_valid": n_valid,
                "n_edge": n_edge,
                "best_coin": best_sym,
                "best_precision": round(best_p, 4),
            })

        # Build coin list (latest artifact per coin)
        coin_latest: dict[str, dict] = {}
        coin_all: dict[str, list[dict]] = {}
        for a in scan_artifacts:
            data = a.get("data", {})
            sym = data.get("config", {}).get("hypothesis_id", "").replace("hyp_volatile_", "")
            if not sym:
                continue
            created = a.get("created_at", "")
            if sym not in coin_latest or created > coin_latest[sym].get("created_at", ""):
                coin_latest[sym] = a
            coin_all.setdefault(sym, []).append(a)

        coin_list = []
        for cs in coin_stats:
            sym = cs["symbol"]
            total = cs["total"]
            pos = cs["pos"]
            prev = pos / total if total > 0 else 0
            latest = coin_latest.get(sym)
            if latest:
                data = latest.get("data", {})
                res = data.get("results", {})
                agg = res.get("aggregate", {})
                baselines = res.get("baselines", {})
                leak = res.get("leakage_report", {})
                ci = agg.get("confidence_intervals", {}).get("precision", {})
                mp = agg.get("precision_mean", 0)
                bp = max((m.get("precision_mean", 0) for m in baselines.values()), default=0)
                nv = agg.get("n_valid_folds", 0)
                ls = leak.get("status", "?")
                n_runs = len(coin_all.get(sym, []))

                if ls != "passed":
                    status = "leak"
                elif nv == 0:
                    status = "no_data"
                elif mp > bp and mp > 0:
                    status = "edge"
                else:
                    status = "no_edge"

                coin_list.append({
                    "symbol": sym, "status": status, "pos": pos, "total": total,
                    "prevalence": round(prev, 4),
                    "precision": round(mp, 4), "baseline": round(bp, 4),
                    "ci_lower": ci.get("ci_lower", 0), "ci_upper": ci.get("ci_upper", 0),
                    "n_valid_folds": nv, "leakage": ls, "n_runs": n_runs,
                    "latest_time": system_iso(latest.get("created_at")) or "",
                })
            else:
                coin_list.append({
                    "symbol": sym, "status": "not_run", "pos": pos, "total": total,
                    "prevalence": round(prev, 4),
                    "precision": 0, "baseline": 0, "ci_lower": 0, "ci_upper": 0,
                    "n_valid_folds": 0, "leakage": "?", "n_runs": 0, "latest_time": "",
                })

        res = {
            "has_db": has_db,
            "n_artifacts": len(scan_artifacts),
            "n_runs": len(scan_runs),
            "run_history": run_history,
            "coin_list": coin_list,
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(res, default=str).encode('utf-8'))

    def get_experiments(self):
        """List all experiment artifacts (backtest results).

        Returns compact list of experiments with key metrics for the
        Backtest tab in React frontend.
        """
        from dao_vang.experiments.artifacts import ArtifactRegistry

        registry = ArtifactRegistry(Path("./artifacts"))
        all_artifacts = registry.list_artifacts()

        experiments = []
        for a in all_artifacts:
            data = a.get("data", {})
            config = data.get("config", {})
            results = data.get("results", {})
            agg = results.get("aggregate", {})
            baselines = results.get("baselines", {})
            leak = results.get("leakage_report", {})
            dq = results.get("data_quality", {})

            mp = agg.get("precision_mean", 0)
            bp = max((m.get("precision_mean", 0) for m in baselines.values()), default=0)
            nv = agg.get("n_valid_folds", 0)
            ls = leak.get("status", "?")
            n_pos = dq.get("label_distribution", {}).get("positive", 0)

            if ls != "passed":
                status = "leak"
            elif nv == 0:
                status = "no_data"
            elif mp > bp and mp > 0:
                status = "edge" if n_pos >= 100 else "promising"
            elif mp > 0:
                status = "no_edge"
            else:
                status = "failed"

            experiments.append({
                "artifact_id": a.get("artifact_id", ""),
                "created_at": system_iso(a.get("created_at")) or "",
                "hypothesis_id": config.get("hypothesis_id", ""),
                "symbol": config.get("hypothesis_id", "").replace("hyp_volatile_", "").replace("hyp_dashboard_", ""),
                "status": status,
                "precision": round(mp, 4),
                "baseline": round(bp, 4),
                "recall": round(agg.get("recall_mean", 0), 4),
                "brier": round(agg.get("brier_mean", 0), 4),
                "n_valid_folds": nv,
                "n_skipped_folds": agg.get("n_skipped_folds", 0),
                "n_positive": n_pos,
                "leakage": ls,
                "warning": results.get("warning"),
            })

        self._set_headers(200)
        self.wfile.write(json.dumps({"experiments": experiments, "total": len(experiments)}, default=str).encode('utf-8'))

    def get_experiment_detail(self, artifact_id: str):
        """Full detail of one experiment artifact."""
        from dao_vang.experiments.artifacts import ArtifactRegistry

        registry = ArtifactRegistry(Path("./artifacts"))
        try:
            artifact = registry.load_experiment(artifact_id)
        except FileNotFoundError:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": f"Artifact {artifact_id} not found"}).encode('utf-8'))
            return

        self._set_headers(200)
        self.wfile.write(json.dumps(artifact, default=str).encode('utf-8'))

    def get_frozen_models(self):
        """List all frozen models for Forward Test tab."""
        from dao_vang.experiments.forward_test import list_frozen_models

        try:
            models = list_frozen_models(Path("./artifacts"))
            result = [
                self._frozen_model_dict(m) for m in models
            ]
            self._set_headers(200)
            self.wfile.write(json.dumps({"models": result, "total": len(result)}, default=str).encode('utf-8'))
        except Exception as exc:
            logger.warning(f"frozen_models_list_failed error={exc}")
            self._set_headers(200)
            self.wfile.write(json.dumps({"models": [], "total": 0, "error": str(exc)}, default=str).encode('utf-8'))

    @staticmethod
    def _frozen_model_dict(m) -> dict:
        """Serialize a FrozenModelInfo with friendly name + label spec."""
        spec = m.label_spec or {}
        target = spec.get("target_drawdown", ACTIVE_TARGET_DRAWDOWN)
        mae = spec.get("max_ae", 0.04)
        horizon_min = spec.get("horizon_minutes", 1440)
        target_pct = f"{target * 100:.0f}%" if isinstance(target, (int, float)) else str(target)
        mae_pct = f"{mae * 100:.0f}%" if isinstance(mae, (int, float)) else str(mae)
        horizon_h = f"{horizon_min // 60:.0f}h" if isinstance(horizon_min, (int, float)) else str(horizon_min)
        label_version = m.config.get("label_version", "v1")
        short_id = str(m.model_id).split("_")[-1][:8]
        friendly_name = f"Frozen LR {label_version} ({target_pct}/{mae_pct}/{horizon_h}) - {short_id}"
        description = (
            f"Logistic Regression đóng băng — dự đoán xác suất coin giảm "
            f">={target_pct} trong {horizon_h} (MAE <={mae_pct}). "
            f"Train cutoff {m.train_cutoff[:10]}, ngưỡng quyết định {m.threshold:.2f}."
        )
        return {
            "model_id": m.model_id,
            "freeze_time": system_iso(m.freeze_time) or str(m.freeze_time),
            "train_cutoff": system_iso(m.train_cutoff) or str(m.train_cutoff),
            "threshold": m.threshold,
            "n_features": len(m.feature_cols),
            "hypothesis_id": m.config.get("hypothesis_id", ""),
            "training_stats": m.training_stats,
            "label_spec": {
                "target_drawdown": target,
                "max_ae": mae,
                "horizon_minutes": horizon_min,
                "target_pct": target_pct,
                "mae_pct": mae_pct,
                "horizon_h": horizon_h,
            },
            "label_version": label_version,
            "friendly_name": friendly_name,
            "description": description,
        }

    def get_models(self):
        """Return all selectable models with friendly names + descriptions.

        Used by the UI model selector. Includes the heuristic composite
        scorer, the walk-forward LogReg, and all frozen models.
        """
        from dao_vang.experiments.forward_test import list_frozen_models

        models: list[dict] = [
            {
                "key": "two_tier_climax",
                "label": "2-Tier Climax Engine (HTF Climax + 5m Trigger)",
                "description": (
                    "Kiến trúc 2 tầng chuyên biệt cho coin bơm xả: Tầng 1 Bối cảnh Khung lớn (1h/4h) "
                    "làm điều kiện nền ARMED (không chờ nến đóng), Tầng 2 Cò kích hoạt Thời gian thực 5m "
                    "(OI Unwind, Taker Sell > 60%, Funding Spike, Râu nến xả) kích hoạt Short tức thì."
                ),
                "model_type": "two_tier",
                "frozen_model_id": None,
                "label_spec": {
                    "target_drawdown": ACTIVE_TARGET_DRAWDOWN,
                    "max_ae": 0.16,
                    "horizon_minutes": 1440,
                    "target_pct": "20%",
                    "mae_pct": "16%",
                    "horizon_h": "24h",
                },
            },
            {
                "key": "heuristic_composite",
                "label": "Heuristic 0-100 (Classic V1)",
                "description": (
                    "Chấm điểm tổng hợp 0-100 dựa trên 8 tín hiệu rule-based "
                    "(phân kỳ giá-volume, funding spike, áp lực bán, "
                    "bối cảnh BTC...). Không cần train, dùng được ngay, "
                    "nhưng không học được từ dữ liệu lịch sử."
                ),
                "model_type": "heuristic",
                "frozen_model_id": None,
                "label_spec": {
                    "target_drawdown": ACTIVE_TARGET_DRAWDOWN,
                    "max_ae": 0.16,
                    "horizon_minutes": 1440,
                    "target_pct": "20%",
                    "mae_pct": "16%",
                    "horizon_h": "24h",
                },
            },
            {
                "key": "logreg_walkforward",
                "label": "Logistic Regression Walk-forward",
                "description": (
                    "Huấn luyện Logistic Regression trên từng khung thời gian, "
                    "không dùng dữ liệu tương lai. Phù hợp để backtest "
                    "và so sánh với baseline."
                ),
                "model_type": "walkforward",
                "frozen_model_id": None,
                "label_spec": {
                    "target_drawdown": ACTIVE_TARGET_DRAWDOWN,
                    "max_ae": 0.16,
                    "horizon_minutes": 1440,
                    "target_pct": "20%",
                    "mae_pct": "16%",
                    "horizon_h": "24h",
                },
            },
        ]

        try:
            frozen = list_frozen_models(Path("./artifacts"))
            for m in frozen:
                d = self._frozen_model_dict(m)
                models.append({
                    "key": f"frozen::{m.model_id}",
                    "label": d["friendly_name"],
                    "description": d["description"],
                    "model_type": "frozen",
                    "frozen_model_id": m.model_id,
                    "label_spec": d["label_spec"],
                    "train_cutoff": d["train_cutoff"],
                    "threshold": d["threshold"],
                })
        except Exception as exc:
            logger.warning(f"models_list_frozen_failed error={exc}")

        current_id = _settings.scanner.frozen_model_id or ""
        self._set_headers(200)
        self.wfile.write(json.dumps({
            "models": models,
            "total": len(models),
            "current_scanner_model_id": current_id,
        }, default=str).encode('utf-8'))

    def get_models_comparison_matrix(self):
        """A/B Benchmark Matrix endpoint comparing V1 Heuristic vs V2 2-Tier Climax."""
        try:
            conn = _ro_duckdb_connect(str(_settings.scanner.db_path))
            try:
                res = evaluate_scoring_engines_comparison(conn, _settings.scoring, sample_limit=200)
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(f"models_comparison_matrix_failed error={exc}")
            from dao_vang.scoring.engine_comparison import (
                _unavailable_engine_comparison,
            )
            res = _unavailable_engine_comparison("database_unavailable")

        self._set_headers(200)
        self.wfile.write(json.dumps(res, default=str).encode('utf-8'))

    def evaluate_frozen_model(self, model_id: str):
        """Evaluate only the model covered by the immutable live protocol."""
        from dao_vang.data.storage.duckdb import DuckDBQueryLayer
        from dao_vang.experiments.forward_evidence import (
            evaluate_forward_evidence,
            load_forward_test_protocol,
        )

        try:
            protocol = load_forward_test_protocol(FORWARD_TEST_PROTOCOL_PATH)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.error(
                "forward_protocol_unavailable path=%s error=%s",
                FORWARD_TEST_PROTOCOL_PATH,
                exc,
            )
            self._set_headers(503)
            self.wfile.write(
                json.dumps(
                    {
                        "status": "protocol_unavailable",
                        "message": "Forward-test protocol is unavailable.",
                        "model_id": model_id,
                        "metrics": None,
                    }
                ).encode("utf-8")
            )
            return

        if model_id != protocol.model_id:
            self._set_headers(200)
            self.wfile.write(
                json.dumps(
                    {
                        "status": "protocol_required",
                        "message": (
                            "This model has no approved independent "
                            "forward-test protocol."
                        ),
                        "model_id": model_id,
                        "protocol_model_id": protocol.model_id,
                        "protocol_fingerprint": protocol.fingerprint,
                        "metrics": None,
                    }
                ).encode("utf-8")
            )
            return

        try:
            settings = _settings
            artifact_dir = Path(settings.scanner.artifact_dir)
            if not artifact_dir.is_absolute():
                artifact_dir = REPO_ROOT / artifact_dir
            db = DuckDBQueryLayer(
                str(settings.scanner.db_path),
                read_only=True,
            )
            try:
                df = db.conn.execute(
                    """
                    SELECT
                        f.*,
                        l.label_value AS is_distribution,
                        l.horizon_hours,
                        l.label_version
                    FROM feature_results f
                    INNER JOIN labels l
                        ON f.feature_time = l.signal_time AND f.symbol = l.symbol
                    WHERE l.horizon_hours = ? AND l.label_version = ?
                    """,
                    [
                        protocol.label_horizon_hours,
                        protocol.label_version,
                    ],
                ).df()
            finally:
                db.close()

            if df.empty:
                self._set_headers(200)
                self.wfile.write(json.dumps({
                    "status": "no_forward_data",
                    "message": "No labeled rows match the locked forward-test contract.",
                    "model_id": model_id,
                    "protocol_fingerprint": protocol.fingerprint,
                    "metrics": None,
                }).encode('utf-8'))
                return

            result = evaluate_forward_evidence(
                model_id,
                df,
                protocol,
                artifact_dir=artifact_dir,
            )
            self._set_headers(200)
            self.wfile.write(json.dumps(result, default=str).encode('utf-8'))
        except Exception as exc:
            logger.warning(f"frozen_evaluate_failed model={model_id} error={exc}")
            self._set_headers(500)
            self.wfile.write(
                json.dumps(
                    {
                        "status": "error",
                        "message": "Forward-test evaluation failed.",
                        "model_id": model_id,
                        "metrics": None,
                    }
                ).encode("utf-8")
            )

    def get_system_history(self):
        """System history & data stats for the new SYSTEM HISTORY tab.

        Returns:
            - data_stats: row counts + min/max timestamps per table
            - scanner: heartbeat, last scan cycle, daily scan counts (30d)
            - models: list of frozen models with training stats + label spec
            - experiments: count + latest experiment summary
            - signals_per_day: alert counts per day (30d) for chart
            - self_learning: guarded retraining status + recent gate reports
        """
        from dao_vang.experiments.forward_test import list_frozen_models

        # --- 1. Data stats & scan/signals per day ---
        stats_snapshot = _read_json(SYSTEM_STATS_PATH)
        data_stats: list[dict[str, Any]] = stats_snapshot.get("data_stats", [])
        scan_per_day: list[dict[str, Any]] = stats_snapshot.get("scan_per_day", [])
        signals_per_day: list[dict[str, Any]] = stats_snapshot.get("signals_per_day", [])

        # Fallback to direct read-only query ONLY if snapshot is missing/empty
        if not data_stats or not scan_per_day or not signals_per_day:
            db_path = str(_settings.scanner.db_path)
            conn = None
            try:
                conn = _ro_duckdb_connect(db_path)
                if not data_stats:
                    data_stats = []
                    tables = [r[0] for r in conn.execute(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema='main' ORDER BY table_name"
                    ).fetchall()]
                    ts_candidates = (
                        "signal_time", "scan_time", "feature_time",
                        "close_time", "period_end", "event_time",
                        "candle_close_time", "time", "created_at",
                    )
                    for t in tables:
                        try:
                            count_row = conn.execute(
                                f"SELECT count(*) FROM {t}"
                            ).fetchone()
                            n = (
                                int(count_row[0] or 0)
                                if count_row is not None
                                else 0
                            )
                        except Exception:
                            n = 0
                        cols = [r[1] for r in conn.execute(
                            f"PRAGMA table_info('{t}')"
                        ).fetchall()]
                        ts_col = next((c for c in ts_candidates if c in cols), None)
                        row = {"table": t, "rows": n}
                        if ts_col and n > 0:
                            try:
                                if t == "scan_results" and ts_col == "scan_time":
                                    min_row = conn.execute(
                                        f"SELECT min({ts_col}) FROM {t}"
                                    ).fetchone()
                                    max_row = conn.execute(
                                        f"SELECT {ts_col} FROM {t} ORDER BY rowid DESC LIMIT 1"
                                    ).fetchone()
                                    mn = min_row[0] if min_row is not None else None
                                    mx = max_row[0] if max_row is not None else None
                                else:
                                    range_row = conn.execute(
                                        f"SELECT min({ts_col}), max({ts_col}) FROM {t}"
                                    ).fetchone()
                                    if range_row is None:
                                        mn, mx = None, None
                                    else:
                                        mn, mx = range_row
                                row["ts_column"] = ts_col
                                row["min_time"] = _system_history_timestamp(mn)
                                row["max_time"] = _system_history_timestamp(mx)
                            except Exception:
                                pass
                        data_stats.append(row)

                if not scan_per_day:
                    try:
                        rows = conn.execute("""
                            SELECT CAST((scan_time AT TIME ZONE 'UTC') AT TIME ZONE ? AS DATE) AS day,
                                   count(*) AS n_rows,
                                   count(DISTINCT cycle) AS n_cycles,
                                   count(DISTINCT symbol) AS n_symbols
                            FROM scan_results
                            GROUP BY day
                            ORDER BY day DESC
                            LIMIT 30
                        """, [SYSTEM_TIMEZONE_NAME]).fetchall()
                        scan_per_day = [
                            {"day": str(r[0]), "n_rows": int(r[1] or 0),
                             "n_cycles": int(r[2] or 0), "n_symbols": int(r[3] or 0)}
                            for r in rows
                        ]
                    except Exception:
                        pass

                if not signals_per_day:
                    try:
                        rows = conn.execute("""
                            SELECT CAST((signal_time AT TIME ZONE 'UTC') AT TIME ZONE ? AS DATE) AS day,
                                   count(*) AS n_signals,
                                   count(*) FILTER (WHERE telegram_sent = TRUE) AS n_telegram,
                                   count(*) FILTER (WHERE hit = TRUE) AS n_hit
                            FROM alert_history
                            GROUP BY day
                            ORDER BY day DESC
                            LIMIT 30
                        """, [SYSTEM_TIMEZONE_NAME]).fetchall()
                        signals_per_day = [
                            {"day": str(r[0]), "n_signals": int(r[1] or 0),
                             "n_telegram": int(r[2] or 0), "n_hit": int(r[3] or 0)}
                            for r in rows
                        ]
                    except Exception:
                        pass
            except Exception as exc:
                logger.warning(f"system_history_db_fallback_failed error={exc}")
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

        # --- 2. Scanner status ---
        hb = _read_json(HEARTBEAT_PATH)
        runtime = _read_json(RUNTIME_STATE_PATH)
        scan_mode = runtime.get("scan_mode", _settings.scanner.scan_mode)
        cycle_stats: dict[str, Any] = {}
        try:
            cycle_stats = _scan_store.latest_cycle_stats()
        except Exception as exc:
            logger.warning(f"system_history_cycle_stats_failed error={exc}")
            cycle_stats = {
                "last_scan_time": hb.get("last_cycle_completed_at"),
                "cycle": hb.get("cycle"),
                "n_symbols": hb.get("last_cycle_n_symbols", 0),
                "n_alerts": hb.get("last_cycle_n_alerts", 0),
            }

        # --- 4. Frozen models with progress ---
        models_progress: list[dict[str, Any]] = []
        try:
            frozen = list_frozen_models(Path("./artifacts"))
            for m in frozen:
                d = self._frozen_model_dict(m)
                ts = m.training_stats or {}
                models_progress.append({
                    "model_id": m.model_id,
                    "friendly_name": d["friendly_name"],
                    "description": d["description"],
                    "label_version": d.get("label_version", "v1"),
                    "label_spec": d["label_spec"],
                    "train_cutoff": system_iso(m.train_cutoff) or str(m.train_cutoff),
                    "freeze_time": system_iso(m.freeze_time) or str(m.freeze_time),
                    "threshold": m.threshold,
                    "n_features": len(m.feature_cols),
                    "train_size": ts.get("train_size"),
                    "train_positives": ts.get("train_positives"),
                    "train_precision": ts.get("precision"),
                    "train_recall": ts.get("recall"),
                    "is_scanner_model": (
                        m.model_id == (_settings.scanner.frozen_model_id or "")
                    ),
                })
        except Exception as exc:
            logger.warning(f"system_history_models_failed error={exc}")

        # --- 5. Experiments count + latest ---
        experiments_count = 0
        latest_experiment: dict[str, Any] | None = None
        try:
            import glob
            exp_files = sorted(glob.glob("artifacts/exp_*.json"))
            experiments_count = len(exp_files)
            if exp_files:
                import json as _json
                with open(exp_files[-1], encoding="utf-8") as f:
                    ed = _json.load(f)
                data = ed.get("data", {})
                cfg = data.get("config", {})
                results = data.get("results", {})
                agg = results.get("aggregate", {}) if isinstance(results, dict) else {}
                latest_experiment = {
                    "artifact_id": ed.get("artifact_id"),
                    "created_at": system_iso(ed.get("created_at")),
                    "hypothesis_id": cfg.get("hypothesis_id"),
                    "label_version": cfg.get("label_version"),
                    "precision_mean": agg.get("precision_mean"),
                    "recall_mean": agg.get("recall_mean"),
                    "brier_mean": agg.get("brier_mean"),
                    "n_valid_folds": agg.get("n_valid_folds"),
                }
        except Exception as exc:
            logger.warning(f"system_history_experiments_failed error={exc}")

        stats_snapshot_generated_at = stats_snapshot.get("generated_at")
        res = {
            "generated_at": system_now().isoformat(),
            "stats_snapshot_generated_at": stats_snapshot_generated_at,
            "candidate_comparison_enabled": _settings.candidate_comparison.enabled,
            "db_path": str(_settings.scanner.db_path),
            "data_stats": data_stats,
            "scanner": {
                "heartbeat": hb,
                "runtime_state": runtime,
                "scan_mode": scan_mode,
                "last_cycle": cycle_stats,
                "scan_per_day": scan_per_day,
            },
            "signals_per_day": signals_per_day,
            "models": models_progress,
            "experiments": {
                "total": experiments_count,
                "latest": latest_experiment,
            },
            "current_scanner_model_id": _settings.scanner.frozen_model_id or "",
            "self_learning": _self_learning_status(),
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(res, default=str).encode('utf-8'))

    def get_version_history(self):
        """Serve complete version history, milestones, development velocity, and GitHub commits."""
        from dao_vang.web.version_history import compute_version_history_data
        try:
            repo_root = Path(".").resolve()
            data = compute_version_history_data(repo_root)
            body = json.dumps(data, default=str).encode("utf-8")
            self._set_headers(200, cache_control="public, max-age=60", content_length=len(body))
            self.wfile.write(body)
        except Exception as exc:
            logger.error("get_version_history_failed error=%s", exc)
            err = json.dumps({"error": "Failed to load version history", "detail": str(exc)}).encode("utf-8")
            self._set_headers(500, content_length=len(err))
            self.wfile.write(err)

    def post_version_history_refresh(self):
        """Force refresh version history cache."""
        from dao_vang.web.version_history import refresh_version_history
        try:
            repo_root = Path(".").resolve()
            data = refresh_version_history(repo_root)
            body = json.dumps({
                "status": "success",
                "message": "Đã làm mới lịch sử phiên bản và commits thành công.",
                "data": data,
            }, default=str).encode("utf-8")
            self._set_headers(200, content_length=len(body))
            self.wfile.write(body)
        except Exception as exc:
            logger.error("post_version_history_refresh_failed error=%s", exc)
            err = json.dumps({"error": "Failed to refresh version history", "detail": str(exc)}).encode("utf-8")
            self._set_headers(500, content_length=len(err))
            self.wfile.write(err)

    def get_system_update_status(self):
        """Serve current git update check status."""
        try:
            from dao_vang.updater.manager import get_update_status
            data = get_update_status()
            body = json.dumps(data, default=str).encode("utf-8")
            self._set_headers(200, cache_control="no-cache", content_length=len(body))
            self.wfile.write(body)
        except Exception as exc:
            logger.error("get_system_update_status_failed error=%s", exc)
            err = json.dumps({"error": "Failed to get update status", "detail": str(exc)}).encode("utf-8")
            self._set_headers(500, content_length=len(err))
            self.wfile.write(err)

    def get_system_update_logs(self):
        """Serve live update execution logs."""
        try:
            from dao_vang.updater.manager import (
                _IS_UPDATING,
                _LAST_UPDATE_RESULT,
                get_update_logs,
            )
            data = {
                "logs": get_update_logs(),
                "is_updating": _IS_UPDATING,
                "last_result": _LAST_UPDATE_RESULT,
            }
            body = json.dumps(data, default=str).encode("utf-8")
            self._set_headers(200, cache_control="no-cache", content_length=len(body))
            self.wfile.write(body)
        except Exception as exc:
            logger.error("get_system_update_logs_failed error=%s", exc)
            err = json.dumps({"error": "Failed to get update logs", "detail": str(exc)}).encode("utf-8")
            self._set_headers(500, content_length=len(err))
            self.wfile.write(err)

    def post_system_update_apply(self):
        """Trigger update process in background thread."""
        try:
            from dao_vang.updater.manager import _IS_UPDATING, UpdateManager
            if not _settings.updater.enabled:
                body = json.dumps({
                    "status": "disabled",
                    "message": "Tính năng cập nhật trực tiếp đang bị vô hiệu hóa; hãy triển khai qua release pipeline.",
                }, ensure_ascii=False).encode("utf-8")
                self._set_headers(403, content_length=len(body))
                self.wfile.write(body)
                return
            if _IS_UPDATING:
                body = json.dumps({
                    "status": "in_progress",
                    "message": "Tiến trình cập nhật đang chạy, vui lòng theo dõi log.",
                }).encode("utf-8")
                self._set_headers(409, content_length=len(body))
                self.wfile.write(body)
                return

            manager = UpdateManager()
            thread = threading.Thread(
                target=manager.apply_update,
                kwargs={"force": False, "restart_services": True, "rebuild_frontend": True, "notify_telegram": True},
                daemon=True,
            )
            thread.start()

            body = json.dumps({
                "status": "started",
                "message": "Đã bắt đầu tiến trình cập nhật hệ thống thành công.",
            }).encode("utf-8")
            self._set_headers(200, content_length=len(body))
            self.wfile.write(body)
        except Exception as exc:
            logger.error("post_system_update_apply_failed error=%s", exc)
            err = json.dumps({"error": "Failed to trigger update", "detail": str(exc)}).encode("utf-8")
            self._set_headers(500, content_length=len(err))
            self.wfile.write(err)

    def get_research_reports(self):
        """Returns catalogue of all historical research papers and benchmark reports."""
        try:
            research_dir = REPO_ROOT / "docs" / "research"
            reports: list[dict[str, Any]] = []

            metadata_map = {
                "06_chien_dich_ban_tia_49_7": {
                    "id": "06_chien_dich_ban_tia_49_7",
                    "code": "RES-2026-0906-01",
                    "title": "Nghiên cứu V3.2: Phân kỳ Cá Mập và mô phỏng ROI",
                    "title_en": "V3.2 Research: Whale Divergence and ROI Simulation",
                    "date": "2026-09-06",
                    "category": "QUANT_REPORT",
                    "tags": ["SMART_MONEY", "BACKTEST", "PROFIT_FACTOR"],
                    "key_metric": "Lịch sử: Precision 49.7% | Winrate 49.09% | ROI 302%",
                    "sample_size": "Out-of-sample (Fold 5)",
                    "badge": "Lưu trữ",
                    "badge_color": "slate",
                    "abstract": "Ảnh chụp nghiên cứu lịch sử về lỗi dữ liệu, Cartesian Explosion và Phân kỳ Dòng tiền Cá mập. Kết quả mô phỏng chỉ áp dụng cho cấu hình của báo cáo, không đại diện production hiện tại.",
                },
                "01_so_sanh_heuristic_vs_machine_learning": {
                    "id": "01_so_sanh_heuristic_vs_machine_learning",
                    "code": "RES-2026-0830-01",
                    "title": "So Sánh Đối Đầu: Mô Hình Heuristic 0–100 vs Machine Learning (LightGBM & LogReg)",
                    "title_en": "Benchmark: V1 Heuristic (0-100) vs Machine Learning (LightGBM & LogReg)",
                    "date": "2026-08-30",
                    "category": "BENCHMARK",
                    "tags": ["HEURISTIC", "LIGHTGBM", "ROC_AUC", "FEATURE_IMPORTANCE"],
                    "key_metric": "Lịch sử: LightGBM 36.6% vs Heuristic 13.28%",
                    "sample_size": "160 altcoins, 1.16M rows (1 năm)",
                    "badge": "Lưu trữ",
                    "badge_color": "slate",
                    "abstract": "Ảnh chụp một thử nghiệm lịch sử trên 160 altcoins; các chỉ số chỉ áp dụng cho cấu hình, dữ liệu và thời điểm của báo cáo này.",
                },
                "02_thi_nghiem_8_chien_luoc_giao_dich": {
                    "id": "02_thi_nghiem_8_chien_luoc_giao_dich",
                    "code": "RES-2026-0830-02",
                    "title": "Thí Nghiệm 8 Chiến Lược Giao Dịch Phân Phối Đỉnh Trên 210 Altcoins",
                    "title_en": "Experiment: 8 Short Distribution Strategies on 210 Altcoins",
                    "date": "2026-08-30",
                    "category": "STRATEGY",
                    "tags": ["STRATEGY_TUNING", "REGIME_GATE", "ENSEMBLE", "WALK_FORWARD"],
                    "key_metric": "Lịch sử: Regime Gate giảm 23% tín hiệu thử nghiệm; Ensemble 16.9%",
                    "sample_size": "209 altcoins, 1.35M rows (1 năm)",
                    "badge": "Lưu trữ",
                    "badge_color": "slate",
                    "abstract": "Ảnh chụp thử nghiệm lịch sử về các ngưỡng p98/p99/p99.5, Ensemble và Regime Gate. Kết luận chỉ áp dụng cho dữ liệu và cấu hình của báo cáo.",
                },
                "03_kiem_dinh_altcoins_midcap_210_coins": {
                    "id": "03_kiem_dinh_altcoins_midcap_210_coins",
                    "code": "RES-2026-0830-03",
                    "title": "Kiểm Định Mở Rộng Altcoins Vốn Hóa Vừa & Nhỏ (210 Coins × 1 Năm)",
                    "title_en": "Mid-Cap Expansion: 210 Altcoins Historical Backtest (1 Year)",
                    "date": "2026-08-30",
                    "category": "SCALING",
                    "tags": ["MID_CAP", "DERIVATIVES", "LIGHTGBM", "SCALABILITY"],
                    "key_metric": "Lịch sử: LightGBM 21.23% vs LogReg 14.87% trên 8 folds",
                    "sample_size": "210 altcoins, 19.37M rows thô",
                    "badge": "Lưu trữ",
                    "badge_color": "slate",
                    "abstract": "Ảnh chụp kiểm định lịch sử mở rộng từ 30 lên 210 coin. Kết quả và feature importance chỉ áp dụng cho dữ liệu, folds và cấu hình trong báo cáo.",
                },
                "04_tham_dinh_va_kiem_dinh_toan_dien_2_6_nam": {
                    "id": "04_tham_dinh_va_kiem_dinh_toan_dien_2_6_nam",
                    "code": "RES-2026-0829-04",
                    "title": "Thẩm Định Độc Lập & Kiểm Định Toàn Diện Hệ Thống (30 Coins × 2.6 Năm)",
                    "title_en": "System Audit & Comprehensive 2.6-Year Benchmark (Top 30 Coins)",
                    "date": "2026-08-29",
                    "category": "AUDIT",
                    "tags": ["AUDIT", "BENCHMARK", "REGIME_ANALYSIS", "STRESS_TEST"],
                    "key_metric": "Lịch sử: LogReg 27.84% trên Mega-Cap; Sideway 30.99%",
                    "sample_size": "30 coins, 2.6 năm (413K rows)",
                    "badge": "Lưu trữ",
                    "badge_color": "slate",
                    "abstract": "Ảnh chụp một đợt thẩm định lịch sử đã loại bỏ hai nguồn dữ liệu mô phỏng. Các benchmark còn lại không đại diện hiệu năng production hiện tại.",
                },
                "05_kien_truc_7_cai_tien_do_chinh_xac": {
                    "id": "05_kien_truc_7_cai_tien_do_chinh_xac",
                    "code": "RES-2026-0829-05",
                    "title": "Kiến Trúc 7 Cải Tiến Nâng Cao Độ Chính Xác Hệ Thống",
                    "title_en": "7 Architectural Milestones for Accuracy Enhancement",
                    "date": "2026-08-29",
                    "category": "ARCHITECTURE",
                    "tags": ["CALIBRATION", "META_LABELING", "ARCHITECTURE", "DATA_PIPELINE"],
                    "key_metric": "Lịch sử: ECE trong thử nghiệm calibration giảm 0.03 → 0.0004",
                    "sample_size": "Toàn bộ hệ thống core",
                    "badge": "Lưu trữ",
                    "badge_color": "slate",
                    "abstract": "Tài liệu lịch sử về bảy thay đổi kiến trúc. Một số mô-đun, gồm Meta-labeling, có thể hiện đang tắt; trạng thái live phải lấy từ cấu hình runtime.",
                },
            }

            if research_dir.exists():
                for md_file in sorted(research_dir.glob("*.md")):
                    file_id = md_file.stem
                    content = md_file.read_text(encoding="utf-8")
                    meta = metadata_map.get(file_id, {
                        "id": file_id,
                        "code": f"RES-{file_id[:10]}",
                        "title": file_id.replace("_", " ").title(),
                        "title_en": file_id.replace("_", " ").title(),
                        "date": "2026-08-30",
                        "category": "RESEARCH",
                        "tags": ["RESEARCH"],
                        "key_metric": "N/A",
                        "sample_size": "N/A",
                        "badge": "Nghiên cứu",
                        "badge_color": "slate",
                        "abstract": content[:200] + "...",
                    })
                    meta_copy = dict(meta)
                    meta_copy["content"] = content
                    meta_copy["file_size_bytes"] = len(content.encode("utf-8"))
                    meta_copy["evidence_scope"] = "historical_research"
                    reports.append(meta_copy)

            body = json.dumps({
                "reports": reports,
                "total_count": len(reports),
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "evidence_scope": "historical_research_not_current_production_performance",
            }, ensure_ascii=False).encode("utf-8")
            self._set_headers(200, content_type="application/json; charset=utf-8", content_length=len(body), cache_control="no-cache, no-store, must-revalidate")
            self.wfile.write(body)
        except Exception as exc:
            logger.error("get_research_reports_failed error=%s", exc)
            err = json.dumps({"error": "Failed to load research reports", "detail": str(exc)}).encode("utf-8")
            self._set_headers(500, content_length=len(err))
            self.wfile.write(err)

    def get_research_report_detail(self, report_id: str):
        """Returns single research paper content by id."""
        try:
            clean_id = Path(report_id).name
            research_dir = REPO_ROOT / "docs" / "research"
            target_file = research_dir / f"{clean_id}.md"
            if not target_file.exists():
                # Try finding by prefix
                matches = list(research_dir.glob(f"*{clean_id}*.md"))
                if matches:
                    target_file = matches[0]
                else:
                    err = json.dumps({"error": "Report not found"}).encode("utf-8")
                    self._set_headers(404, content_length=len(err))
                    self.wfile.write(err)
                    return

            content = target_file.read_text(encoding="utf-8")
            body = json.dumps({
                "id": target_file.stem,
                "content": content,
                "file_name": target_file.name,
                "file_size_bytes": len(content.encode("utf-8")),
                "evidence_scope": "historical_research_not_current_production_performance",
            }, ensure_ascii=False).encode("utf-8")
            self._set_headers(200, content_type="application/json; charset=utf-8", content_length=len(body), cache_control="no-cache, no-store, must-revalidate")
            self.wfile.write(body)
        except Exception as exc:
            logger.error("get_research_report_detail_failed error=%s", exc)
            err = json.dumps({"error": "Failed to load report detail", "detail": str(exc)}).encode("utf-8")
            self._set_headers(500, content_length=len(err))
            self.wfile.write(err)

class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

def run_server(port=8000, host='0.0.0.0'):
    server_address = (host, port)
    web_lock = ScannerInstanceLock(Path(_settings.paths.data_dir) / "web.lock")
    try:
        web_lock.acquire()
    except ScannerAlreadyRunning as exc:
        logger.error("web_instance_already_running error=%s", exc)
        raise SystemExit(2) from exc

    httpd = None
    tracking_stop = None
    try:
        httpd = ReusableThreadingHTTPServer(server_address, APIHandler)
        tracking_stop = start_tracking_monitor(_tracking_store)
        logger.info(f"Đảo Vàng Combined Server running on http://{host}:{port}")
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Received exit signal. Shutting down server...")
    finally:
        if tracking_stop is not None:
            tracking_stop.set()
        if httpd is not None:
            httpd.server_close()
        web_lock.release()
        logger.info("Server socket released. Goodbye!")

if __name__ == '__main__':
    run_server()
