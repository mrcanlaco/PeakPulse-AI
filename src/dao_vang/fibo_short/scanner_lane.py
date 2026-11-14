"""Live/Shadow Scanner Lane for the Confirmed Reversal & Fibonacci Short branch (H4/D1 -> H1)."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Sequence

import httpx

from dao_vang.config.settings import AppSettings, FiboTrendShortConfig
from dao_vang.domain.time import SYSTEM_TIMEZONE, as_system_timezone
from dao_vang.fibo_short.detector import evaluate_symbol_timeframe
from dao_vang.fibo_short.models import FiboShortSignal
from dao_vang.logging import get_logger
from dao_vang.scanner.watchlist import fetch_all_tickers, load_manual_watchlist

logger = get_logger(__name__)


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    os.replace(tmp, path)


_HTTP_CLIENT = httpx.Client(
    timeout=8.0,
    limits=httpx.Limits(max_keepalive_connections=12, max_connections=16),
)

_INTERVAL_MS: dict[str, int] = {
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}
_CLOSED_KLINE_LOCK = threading.Lock()
_CLOSED_KLINE_CACHE: dict[tuple[str, str, str], tuple[int, int, list[dict[str, Any]]]] = {}


def clear_closed_kline_cache() -> None:
    """Clear the in-memory closed-kline cache (used in tests or manual resets)."""
    with _CLOSED_KLINE_LOCK:
        _CLOSED_KLINE_CACHE.clear()


def fetch_closed_klines(
    symbol: str,
    interval: Literal["1h", "4h", "1d"],
    *,
    base_url: str = "https://fapi.binance.com",
    limit: int = 60,
    now_ms: int | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Fetch closed klines from Binance USD-M Futures, excluding the currently forming bar.

    Closed H1/H4/D1 bars are immutable within the current interval bucket. Caching
    by ``(base_url, symbol, interval)`` verified against the expected latest closed
    ``open_time`` eliminates redundant 5-minute REST calls while auto-refreshing
    the instant a new candle boundary closes.
    """
    current_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    norm_url = base_url.rstrip("/")
    interval_ms = _INTERVAL_MS.get(interval)
    expected_last_open_ms = (
        ((current_ms // interval_ms) - 1) * interval_ms if interval_ms else None
    )
    cache_key = (norm_url, symbol.upper(), interval)
    if use_cache and expected_last_open_ms is not None:
        with _CLOSED_KLINE_LOCK:
            cached = _CLOSED_KLINE_CACHE.get(cache_key)
            if (
                cached is not None
                and cached[0] == expected_last_open_ms
                and cached[1] >= limit
            ):
                return [dict(bar) for bar in cached[2][-limit:]]

    try:
        resp = _HTTP_CLIENT.get(
            f"{norm_url}/fapi/v1/klines",
            params={
                "symbol": symbol,
                "interval": interval,
                "limit": min(500, limit + 2),
            },
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception as exc:
        logger.warning(
            "fibo_kline_fetch_failed",
            symbol=symbol,
            interval=interval,
            error=str(exc),
        )
        return []

    closed_bars: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, list) or len(row) < 7:
            continue
        open_ms = int(row[0])
        close_ms = int(row[6])
        # Exclude incomplete bar if close_time is in the future
        if close_ms > current_ms:
            continue
        dt_utc = datetime.fromtimestamp(open_ms / 1000.0, tz=timezone.utc)
        closed_bars.append(
            {
                "open_time": open_ms,
                "close_time": close_ms,
                "open_time_str": as_system_timezone(dt_utc).strftime("%Y-%m-%d %H:%M"),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
        )
    if use_cache and closed_bars:
        last_open_ms = int(closed_bars[-1]["open_time"])
        with _CLOSED_KLINE_LOCK:
            if len(_CLOSED_KLINE_CACHE) >= 1024 and cache_key not in _CLOSED_KLINE_CACHE:
                _CLOSED_KLINE_CACHE.pop(next(iter(_CLOSED_KLINE_CACHE)))
            _CLOSED_KLINE_CACHE[cache_key] = (
                last_open_ms,
                limit,
                [dict(bar) for bar in closed_bars],
            )
    return [dict(bar) for bar in closed_bars[-limit:]]


DEFAULT_BLACKLIST_SYMBOLS: frozenset[str] = frozenset(
    {
        "BTCUSDT",
        "ETHUSDT",
        "BNBUSDT",
        "PAXGUSDT",
        "USDCUSDT",
        "FDUSDUSDT",
        "TUSDUSDT",
        "DAIUSDT",
        "BUSDUSDT",
        "BTCDOMUSDT",
        "DEFIUSDT",
    }
)

DEFAULT_TIER_S_CORE: tuple[str, ...] = (
    "SOLUSDT",
    "DOGEUSDT",
    "1000PEPEUSDT",
    "1000BONKUSDT",
    "1000SHIBUSDT",
    "WIFUSDT",
    "AVAXUSDT",
    "SUIUSDT",
    "APTUSDT",
    "NEARUSDT",
    "INJUSDT",
    "AAVEUSDT",
    "UNIUSDT",
    "LINKUSDT",
    "ARBUSDT",
    "OPUSDT",
    "TIAUSDT",
    "ADAUSDT",
    "DOTUSDT",
    "BOMEUSDT",
    "FLOKIUSDT",
    "PENGUUSDT",
    "TRUMPUSDT",
    "ORDIUSDT",
)


def load_fibo_universe_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load the Ex-Ante Tiered Coin Universe configuration JSON (Tier S, Tier A, Blacklist)."""
    candidates: list[Path] = []
    if config_path is not None:
        candidates.append(config_path)
    candidates.extend([
        Path("artifacts/fibo_trend_short/fibo_coin_universe_config.json"),
        Path(__file__).resolve().parents[3] / "artifacts" / "fibo_trend_short" / "fibo_coin_universe_config.json",
    ])
    for path in candidates:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception as exc:
                logger.warning("fibo_universe_config_load_failed", path=str(path), error=str(exc))
    return {
        "schema_version": "1.2.0-fallback",
        "dynamic_new_listing_rules": {
            "min_listing_age_days": 63,
            "min_circulating_market_cap_usd": 150_000_000.0,
            "min_circulating_float_ratio": 0.64,
            "min_24h_quote_volume_usd": 10_000_000.0,
            "max_upper_wick_p90_pct": 3.5,
        },
        "tier_s_core": list(DEFAULT_TIER_S_CORE),
        "tier_a_extended": [],
        "pit_zero_bias_mcap_float": list(DEFAULT_TIER_S_CORE),
        "dynamic_pool": [],
        "blacklist_do_not_short": sorted(DEFAULT_BLACKLIST_SYMBOLS),
    }


def load_latest_pit_top50_membership(base_dir: Path | None = None) -> dict[str, Any]:
    """Load the latest monthly Rolling Point-in-Time Top-50 Volume + Wick p90<=3.2% membership."""
    candidates: list[Path] = []
    if base_dir is not None:
        candidates.append(base_dir)
    candidates.extend([
        Path("artifacts/fibo_trend_short/paper_oos_v1/membership"),
        Path(__file__).resolve().parents[3] / "artifacts" / "fibo_trend_short" / "paper_oos_v1" / "membership",
    ])
    for folder in candidates:
        if folder.exists() and folder.is_dir():
            files = sorted(folder.glob("*.json"))
            if files:
                try:
                    raw = json.loads(files[-1].read_text(encoding="utf-8"))
                    members = raw.get("members", [])
                    by_sym: dict[str, dict[str, Any]] = {}
                    for idx, m in enumerate(members, start=1):
                        sym = str(m.get("symbol", "")).strip().upper()
                        if sym and sym not in DEFAULT_BLACKLIST_SYMBOLS:
                            by_sym[sym] = {
                                "rank": idx,
                                "symbol": sym,
                                "median_quote_volume": float(m.get("median_quote_volume", 0.0) or 0.0),
                                "active_days": int(m.get("active_days", 0) or 0),
                                "wick_p90_pct": float(m.get("wick_p90_pct", 0.0) or 0.0),
                            }
                    return {
                        "month": str(raw.get("month", files[-1].stem)),
                        "ranking_interval": str(raw.get("ranking_interval", "[cutoff-63d,cutoff)")),
                        "eligible_contracts": int(raw.get("eligible_contracts", 0) or 0),
                        "members": list(by_sym.values()),
                        "by_symbol": by_sym,
                    }
                except Exception as exc:
                    logger.warning("fibo_pit_membership_load_failed", path=str(files[-1]), error=str(exc))
    return {"month": None, "ranking_interval": "[cutoff-63d,cutoff)", "eligible_contracts": 0, "members": [], "by_symbol": {}}


def select_candidate_symbols(
    settings: AppSettings,
    *,
    explicit_symbols: Sequence[str] | None = None,
    tickers_override: Sequence[dict[str, Any]] | None = None,
) -> list[str]:
    """Select candidate symbols for the Fibo Short scanner using the Ex-Ante Tiered Universe."""
    if explicit_symbols:
        return list(dict.fromkeys(s.strip().upper() for s in explicit_symbols if s.strip()))

    cfg = settings.fibo_trend_short
    max_candidates = cfg.max_candidates
    universe_cfg = load_fibo_universe_config(cfg.universe_config_path)

    blacklist: set[str] = set(DEFAULT_BLACKLIST_SYMBOLS)
    blacklist.update(s.strip().upper() for s in cfg.blacklist_symbols if s.strip())
    blacklist.update(
        str(s).strip().upper()
        for s in universe_cfg.get("blacklist_do_not_short", [])
        if str(s).strip()
    )

    tier_s: list[str] = [
        str(s).strip().upper()
        for s in universe_cfg.get("tier_s_core", DEFAULT_TIER_S_CORE)
        if str(s).strip().upper() not in blacklist
    ]
    tier_a: list[str] = [
        str(s).strip().upper()
        for s in universe_cfg.get("tier_a_extended", [])
        if str(s).strip().upper() not in blacklist
    ]
    pit_zero_bias: list[str] = [
        str(s).strip().upper()
        for s in universe_cfg.get("pit_zero_bias_mcap_float", DEFAULT_TIER_S_CORE)
        if str(s).strip().upper() not in DEFAULT_BLACKLIST_SYMBOLS
    ]

    manual: list[str] = []
    try:
        manual = [
            s.strip().upper()
            for s in load_manual_watchlist(settings.scanner.watchlist_path)
            if s.strip().upper() not in blacklist
        ]
    except Exception:
        manual = []

    tickers: list[dict[str, Any]] = []
    if tickers_override is not None:
        tickers = list(tickers_override)
    else:
        try:
            tickers = fetch_all_tickers(str(settings.binance.base_url).rstrip("/"))
        except Exception as exc:
            logger.warning("fibo_tickers_fetch_failed", error=str(exc))

    ticker_map: dict[str, dict[str, Any]] = {
        str(t.get("symbol", "")).upper(): t
        for t in tickers
        if str(t.get("symbol", "")).upper().endswith("USDT")
    }

    def _vol_rank_key(sym: str) -> tuple[float, float]:
        t = ticker_map.get(sym)
        if not t:
            return (0.0, 0.0)
        return (
            abs(float(t.get("priceChangePercent", 0.0) or 0.0)),
            float(t.get("quoteVolume", 0.0) or 0.0),
        )

    # Sort Tier S, Tier A, and PIT Zero-Bias by live 24h volatility/activity when ticker data is available
    if ticker_map:
        tier_s_sorted = sorted(tier_s, key=_vol_rank_key, reverse=True)
        tier_a_sorted = sorted(tier_a, key=_vol_rank_key, reverse=True)
        pit_sorted = sorted(pit_zero_bias, key=_vol_rank_key, reverse=True)
    else:
        tier_s_sorted = tier_s
        tier_a_sorted = tier_a
        pit_sorted = pit_zero_bias

    if cfg.universe_mode == "tier_s_only":
        deduped_s = list(dict.fromkeys(s for s in tier_s_sorted if s.endswith("USDT")))
        return deduped_s[:max_candidates]

    if cfg.universe_mode == "pit_zero_bias_mcap_float":
        deduped_pit = list(dict.fromkeys(s for s in pit_sorted if s.endswith("USDT")))
        return deduped_pit[:max_candidates]

    pit_meta = load_latest_pit_top50_membership()
    pit_top50_syms = [
        m["symbol"]
        for m in pit_meta.get("members", [])
        if str(m.get("symbol", "")).endswith("USDT") and m["symbol"] not in DEFAULT_BLACKLIST_SYMBOLS
    ]
    if ticker_map and pit_top50_syms:
        pit_top50_sorted = sorted(pit_top50_syms, key=_vol_rank_key, reverse=True)
    else:
        pit_top50_sorted = pit_top50_syms

    if cfg.universe_mode == "rolling_pit_top50":
        merged_pit = list(dict.fromkeys([*pit_top50_sorted, *tier_s_sorted]))
        return merged_pit[:max_candidates]

    ordered: list[str] = []
    if cfg.universe_mode == "tiered_whitelist":
        ordered.extend(tier_s_sorted)
        ordered.extend(s for s in pit_top50_sorted if s not in blacklist)
        ordered.extend(tier_a_sorted)
        ordered.extend(manual)

        # Allow newly listed / dynamic symbols that are NOT blacklisted and meet strict volume gate
        dyn_rules = universe_cfg.get("dynamic_new_listing_rules", {})
        dyn_min_vol = float(dyn_rules.get("min_24h_quote_volume_usd", 10_000_000.0))
        dyn_candidates = [
            t
            for sym, t in ticker_map.items()
            if sym not in blacklist
            and float(t.get("quoteVolume", 0.0) or 0.0) >= dyn_min_vol
        ]
        dyn_by_change = sorted(
            dyn_candidates,
            key=lambda t: abs(float(t.get("priceChangePercent", 0.0) or 0.0)),
            reverse=True,
        )
        for item in dyn_by_change[:15]:
            ordered.append(str(item["symbol"]).upper())
    else:
        # dynamic_all mode (still enforces blacklist)
        min_vol = max(2_500_000.0, float(settings.scanner.min_volume_usd * 0.5))
        valid_tickers = [
            t
            for sym, t in ticker_map.items()
            if sym not in blacklist
            and float(t.get("quoteVolume", 0.0) or 0.0) >= min_vol
        ]
        by_abs_change = sorted(
            valid_tickers,
            key=lambda t: abs(float(t.get("priceChangePercent", 0.0) or 0.0)),
            reverse=True,
        )
        by_volume = sorted(
            valid_tickers,
            key=lambda t: float(t.get("quoteVolume", 0.0) or 0.0),
            reverse=True,
        )
        ordered.extend(tier_s_sorted[:15])
        ordered.extend(manual)
        for item in by_abs_change[: max_candidates // 2 + 5]:
            ordered.append(str(item["symbol"]).upper())
        for item in by_volume[: max_candidates // 2 + 5]:
            ordered.append(str(item["symbol"]).upper())

    deduped = list(
        dict.fromkeys(s for s in ordered if s.endswith("USDT") and s not in blacklist)
    )
    return deduped[:max_candidates]



def _build_v421_filter_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    """Explain in Vietnamese which v4.0.21 gates accepted or filtered out a fired M1 signal."""
    wave = payload.get("wave") or {}
    h1_conf = payload.get("h1_confirmation") or {}
    setup = payload.get("trade_setup") or {}
    matched = list(payload.get("matched_policies") or [])
    milestones = list(payload.get("eligible_milestones") or [])
    primary_policy = str(payload.get("primary_policy") or "watch_only")

    imp_drop = float(wave.get("impulse_drop_pct") or 0.0)
    imp_drop_pct = imp_drop * 100.0 if imp_drop < 2.0 else imp_drop
    imp_ker = float(wave.get("impulse_ker") or 0.0)
    wave_ker = float(wave.get("wave_ker") or 0.0)
    pst_pass = bool(wave.get("pst_pass"))
    cond2_break = bool(h1_conf.get("cond2_break_prev_low"))
    max_fibo = float(h1_conf.get("max_pullback_fibo_ratio") or 0.0)
    rr_m6_tp1 = float(setup.get("rr_m6_tp1") or setup.get("rr_tp1") or 0.0)
    sl_within_cap = bool(setup.get("sl_within_cap", True))

    reasons_m6: list[str] = []
    if imp_drop_pct < 6.0:
        reasons_m6.append(f"Biên độ nhịp sập {imp_drop_pct:.1f}% < 6.0%")
    if imp_ker < 0.50:
        reasons_m6.append(f"Impulse KER {imp_ker:.2f} < 0.50 (Nhịp sập thiếu dứt khoát)")
    f1_elite = bool(pst_pass and wave_ker >= 0.35)
    f1_expanded = bool(f1_elite or wave_ker >= 0.65)
    if not f1_expanded:
        reasons_m6.append(f"Wave KER {wave_ker:.2f} < 0.65 & chưa đạt Carver PST")
    if not sl_within_cap:
        reasons_m6.append("Khoảng cách SL Mốc 6 vượt trần 12%")

    reasons_sniper: list[str] = list(reasons_m6)
    if not cond2_break:
        reasons_sniper.append("Mới có nến mẫu hình ĐK1, chưa phá đáy cấu trúc H1 (ĐK2)")
    if max_fibo > 0.786:
        reasons_sniper.append(f"Nhịp hồi vượt Fibo 0.786 ({max_fibo:.3f})")

    reasons_rr1: list[str] = list(reasons_sniper)
    if rr_m6_tp1 < 1.0:
        reasons_rr1.append(f"R:R(TP1) = 1:{rr_m6_tp1:.2f} < 1.0")

    return {
        "accepted_m6": "m6_risk" in matched,
        "accepted_sniper": "sniper_risk" in matched,
        "accepted_elite_sniper": "elite_sniper_risk" in matched,
        "accepted_sniper_rr1_24h": "sniper_rr1_horizon24" in matched,
        "primary_policy": primary_policy,
        "matched_policies": matched,
        "eligible_milestones": milestones,
        "m6_rejection_reasons_vi": reasons_m6,
        "sniper_rejection_reasons_vi": reasons_sniper,
        "rr1_rejection_reasons_vi": reasons_rr1,
    }


def _parse_fibo_signal_dt(raw: Any) -> datetime | None:
    txt = str(raw or "").strip()
    if not txt:
        return None
    try:
        dt = datetime.fromisoformat(txt.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=SYSTEM_TIMEZONE)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        return (
            datetime.strptime(txt, "%Y-%m-%d %H:%M")
            .replace(tzinfo=SYSTEM_TIMEZONE)
            .astimezone(timezone.utc)
        )
    except Exception:
        return None


def _evaluate_dual_shadow_outcome(
    *,
    payload: dict[str, Any],
    entry_price: float,
    stop_loss_legacy: float,
    tp1: float,
    tp2: float,
    tp3: float,
    current_price: float,
    prev_outcome: dict[str, Any] | None,
    now_iso: str,
) -> dict[str, Any]:
    """Evaluate parallel shadow outcomes: Legacy (M1 Raw Fixed 20% SL 1.0) vs v4.0.21 (SL 0.886 Ratchet + Risk 0.5%)."""
    prev = prev_outcome or {}
    setup = payload.get("trade_setup") or {}
    fibo = payload.get("fibo_levels") or {}
    entry = float(entry_price or setup.get("entry_price") or current_price or 1.0)
    cp = float(current_price or payload.get("current_price") or entry)
    sl_leg = float(stop_loss_legacy or setup.get("stop_loss") or entry * 1.05)

    # Compute M6 Stop Loss (Fibo 0.886 + 0.15 ATR)
    lvl_0886 = float(
        fibo.get("level_0886")
        or (float(fibo.get("level_0000", tp1)) + 0.886 * float(fibo.get("wave_range", max(0.0, sl_leg - tp1))))
    )
    atr_1h = float(setup.get("atr_1h") or (0.005 * entry))
    sl_m6 = float(setup.get("sl_m6") or max(lvl_0886, entry * 1.005) + 0.15 * atr_1h)
    if sl_m6 <= entry:
        sl_m6 = max(sl_leg, entry * 1.01)
    sl_m6_pct = float(setup.get("sl_m6_pct") or ((sl_m6 - entry) / max(1e-9, entry) * 100.0))
    sl_leg_pct = (sl_leg - entry) / max(1e-9, entry) * 100.0

    # Risk sizing: min(20% NAV, 0.5% NAV / (sl_m6_pct + 0.25%))
    rec_notional_pct = float(
        setup.get("recommended_notional_pct")
        or min(20.0, 50.0 / max(0.25, sl_m6_pct + 0.25))
    )
    legacy_notional_pct = 20.0
    cost_rt_pct = 0.25  # Standard VIP6 round-trip (2.5 bps fee + 10 bps slip per side)

    hold_hours = float(
        setup.get("max_hold_hours")
        or (120.0 if str(payload.get("higher_timeframe")) == "1d" else 72.0)
    )
    sig_dt = _parse_fibo_signal_dt(payload.get("signal_time"))
    now_dt = _parse_fibo_signal_dt(now_iso)
    expiry_dt = (sig_dt + timedelta(hours=hold_hours + 1.0)) if sig_dt is not None else None
    is_past_horizon = bool(
        expiry_dt is not None
        and now_dt is not None
        and now_dt > expiry_dt
    )
    # --- 1. Legacy Track (M1 Raw, SL 1.0, No Ratchet, Fixed 20% NAV) ---
    tp1_hit = bool(prev.get("tp1_hit", False))
    tp2_hit = bool(prev.get("tp2_hit", False))
    tp3_hit = bool(prev.get("tp3_hit", False))
    sl_hit = bool(prev.get("sl_hit", False))
    status = str(prev.get("status") or "ACTIVE")
    if status in ("PENDING_CONFIRMATION", "TIME_EXIT"):
        status = "EXPIRED_UNRESOLVED" if status == "TIME_EXIT" else "ACTIVE"
    closed_price: float | None = (
        float(prev["closed_price"]) if prev.get("closed_price") is not None else None
    )
    leg_terminal = status in ("STOPPED_OUT", "TP3_HIT", "EXPIRED_UNRESOLVED")

    if not leg_terminal and not sl_hit and not tp3_hit:
        if is_past_horizon:
            closed_price = entry
            status = "EXPIRED_UNRESOLVED"
        else:
            if cp >= sl_leg:
                sl_hit = True
                status = "STOPPED_OUT"
            else:
                if cp <= tp1:
                    tp1_hit = True
                    if status == "ACTIVE":
                        status = "TP1_HIT"
                if cp <= tp2:
                    tp2_hit = True
                    if status in ("ACTIVE", "TP1_HIT"):
                        status = "TP2_HIT"
                if cp <= tp3:
                    tp3_hit = True
                    status = "TP3_HIT"

    eff_leg_cp = closed_price if closed_price is not None else cp
    leg1_px = tp1 if tp1_hit else (sl_leg if sl_hit else eff_leg_cp)
    leg2_px = tp2 if tp2_hit else (sl_leg if sl_hit else eff_leg_cp)
    leg3_px = tp3 if tp3_hit else (sl_leg if sl_hit else eff_leg_cp)
    legacy_gross_pct = (
        0.40 * (entry - leg1_px) + 0.40 * (entry - leg2_px) + 0.20 * (entry - leg3_px)
    ) / max(1e-9, entry) * 100.0
    legacy_net_pct = 0.0 if status == "EXPIRED_UNRESOLVED" else round(legacy_gross_pct - cost_rt_pct, 4)
    legacy_nav_pnl_pct = 0.0 if status == "EXPIRED_UNRESOLVED" else round(legacy_net_pct * (legacy_notional_pct / 100.0), 4)

    # --- 2. Upgraded v4.0.21 Track (SL 0.886 + Ratcheted BE/TP1 Stop + Risk 0.5% NAV) ---
    prev_v4 = (prev.get("shadow_tracks") or {}).get("v4_execution") or {}
    v4_tp1_hit = bool(prev_v4.get("tp1_hit", False))
    v4_tp2_hit = bool(prev_v4.get("tp2_hit", False))
    v4_tp3_hit = bool(prev_v4.get("tp3_hit", False))
    v4_sl_hit = bool(prev_v4.get("sl_hit", False))
    v4_be_stop_hit = bool(prev_v4.get("be_stop_hit", False))
    v4_tp1_trail_hit = bool(prev_v4.get("tp1_trail_hit", False))
    v4_status = str(prev_v4.get("status") or "ACTIVE")
    if v4_status in ("FILTERED_OUT", "TIME_EXIT"):
        v4_status = "EXPIRED_UNRESOLVED" if v4_status == "TIME_EXIT" else "ACTIVE"
    v4_closed_price: float | None = (
        float(prev_v4["closed_price"]) if prev_v4.get("closed_price") is not None else None
    )
    v4_terminal = v4_status in (
        "STOPPED_M6_0886",
        "TP3_HIT",
        "TP1_LOCKED_BE_STOP",
        "TP2_LOCKED_TP1_STOP",
        "EXPIRED_UNRESOLVED",
    )

    if not v4_terminal and not v4_sl_hit and not v4_be_stop_hit and not v4_tp1_trail_hit and not v4_tp3_hit:
        if is_past_horizon:
            v4_closed_price = entry
            v4_status = "EXPIRED_UNRESOLVED"
        else:
            if cp <= tp1:
                v4_tp1_hit = True
                if v4_status == "ACTIVE":
                    v4_status = "TP1_HIT_RATCHET_BE"
            if cp <= tp2:
                v4_tp2_hit = True
                if v4_status in ("ACTIVE", "TP1_HIT_RATCHET_BE"):
                    v4_status = "TP2_HIT_RATCHET_TP1"
            if cp <= tp3:
                v4_tp3_hit = True
                v4_status = "TP3_HIT"

            if not v4_tp3_hit:
                if v4_tp2_hit and cp >= tp1:
                    v4_tp1_trail_hit = True
                    v4_status = "TP2_LOCKED_TP1_STOP"
                elif v4_tp1_hit and cp >= entry:
                    v4_be_stop_hit = True
                    v4_status = "TP1_LOCKED_BE_STOP"
                elif not v4_tp1_hit and cp >= sl_m6:
                    v4_sl_hit = True
                    v4_status = "STOPPED_M6_0886"

    eff_v4_cp = v4_closed_price if v4_closed_price is not None else cp
    active_v4_sl = tp1 if v4_tp2_hit else (entry if v4_tp1_hit else sl_m6)
    v4_p1 = tp1 if v4_tp1_hit else (sl_m6 if v4_sl_hit else eff_v4_cp)
    v4_p2 = tp2 if v4_tp2_hit else (entry if v4_be_stop_hit else (sl_m6 if v4_sl_hit else eff_v4_cp))
    v4_p3 = (
        tp3
        if v4_tp3_hit
        else (
            tp1
            if v4_tp1_trail_hit
            else (entry if v4_be_stop_hit else (sl_m6 if v4_sl_hit else eff_v4_cp))
        )
    )
    v4_gross_pct = (
        0.40 * (entry - v4_p1) + 0.40 * (entry - v4_p2) + 0.20 * (entry - v4_p3)
    ) / max(1e-9, entry) * 100.0
    v4_net_pct = 0.0 if v4_status == "EXPIRED_UNRESOLVED" else round(v4_gross_pct - cost_rt_pct, 4)
    v4_exec_nav_pnl_pct = 0.0 if v4_status == "EXPIRED_UNRESOLVED" else round(v4_net_pct * (rec_notional_pct / 100.0), 4)

    diag = _build_v421_filter_diagnostics(payload)
    return {
        "status": status,
        "tp1_hit": tp1_hit,
        "tp2_hit": tp2_hit,
        "tp3_hit": tp3_hit,
        "sl_hit": sl_hit,
        "closed_price": closed_price,
        "updated_at": now_iso,
        "shadow_tracks": {
            "legacy_m1_raw": {
                "accepted": True,
                "status": status,
                "stop_loss": round(sl_leg, 8),
                "stop_loss_pct": round(sl_leg_pct, 3),
                "notional_pct": legacy_notional_pct,
                "tp1_hit": tp1_hit,
                "tp2_hit": tp2_hit,
                "tp3_hit": tp3_hit,
                "sl_hit": sl_hit,
                "closed_price": closed_price,
                "net_return_pct": legacy_net_pct,
                "nav_pnl_pct": legacy_nav_pnl_pct,
            },
            "v4_execution": {
                "accepted_m6": diag["accepted_m6"],
                "accepted_sniper": diag["accepted_sniper"],
                "accepted_elite_sniper": diag["accepted_elite_sniper"],
                "accepted_sniper_rr1_24h": diag["accepted_sniper_rr1_24h"],
                "primary_policy": diag["primary_policy"],
                "matched_policies": diag["matched_policies"],
                "m6_rejection_reasons_vi": diag["m6_rejection_reasons_vi"],
                "sniper_rejection_reasons_vi": diag["sniper_rejection_reasons_vi"],
                "rr1_rejection_reasons_vi": diag["rr1_rejection_reasons_vi"],
                "status": v4_status if diag["accepted_m6"] else "FILTERED_OUT",
                "sl_m6": round(sl_m6, 8),
                "sl_m6_pct": round(sl_m6_pct, 3),
                "active_ratchet_sl": round(active_v4_sl, 8),
                "notional_pct": round(rec_notional_pct, 2),
                "tp1_hit": v4_tp1_hit,
                "tp2_hit": v4_tp2_hit,
                "tp3_hit": v4_tp3_hit,
                "sl_hit": v4_sl_hit,
                "be_stop_hit": v4_be_stop_hit,
                "tp1_trail_hit": v4_tp1_trail_hit,
                "closed_price": v4_closed_price,
                "raw_net_return_pct": v4_net_pct,
                "m6_nav_pnl_pct": v4_exec_nav_pnl_pct if diag["accepted_m6"] else 0.0,
                "sniper_nav_pnl_pct": v4_exec_nav_pnl_pct if diag["accepted_sniper"] else 0.0,
                "elite_sniper_nav_pnl_pct": v4_exec_nav_pnl_pct if diag["accepted_elite_sniper"] else 0.0,
                "sniper_rr1_nav_pnl_pct": v4_exec_nav_pnl_pct if diag["accepted_sniper_rr1_24h"] else 0.0,
                "delta_m6_vs_legacy_nav_pct": round(
                    (v4_exec_nav_pnl_pct if diag["accepted_m6"] else 0.0) - legacy_nav_pnl_pct,
                    4,
                ),
                "delta_sniper_vs_legacy_nav_pct": round(
                    (v4_exec_nav_pnl_pct if diag["accepted_sniper"] else 0.0) - legacy_nav_pnl_pct,
                    4,
                ),
            },
        },
    }


class FiboStateStore:
    """SQLite state store for tracking fired Fibonacci Short signals and their TP/SL outcomes."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fibo_signals (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    higher_timeframe TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    confirmation_tier TEXT NOT NULL,
                    signal_time TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    tp1 REAL NOT NULL,
                    tp2 REAL NOT NULL,
                    tp3 REAL NOT NULL,
                    outcome_status TEXT NOT NULL DEFAULT 'ACTIVE',
                    tp1_hit INTEGER NOT NULL DEFAULT 0,
                    tp2_hit INTEGER NOT NULL DEFAULT 0,
                    tp3_hit INTEGER NOT NULL DEFAULT 0,
                    sl_hit INTEGER NOT NULL DEFAULT 0,
                    telegram_sent INTEGER NOT NULL DEFAULT 0,
                    telegram_sent_at TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # Repair any rows that transitioned to FIRED_CONFIRMED_SHORT while retaining PENDING_CONFIRMATION
            rows = conn.execute(
                "SELECT id, stage, outcome_status, entry_price, stop_loss, tp1, tp2, tp3, payload_json FROM fibo_signals WHERE stage = 'FIRED_CONFIRMED_SHORT' AND outcome_status = 'PENDING_CONFIRMATION'"
            ).fetchall()
            for r in rows:
                try:
                    p = json.loads(r["payload_json"])
                    ts = p.get("trade_setup") or {}
                    ep = float(ts.get("entry_price") or r["entry_price"])
                    sl = float(ts.get("stop_loss") or r["stop_loss"])
                    t1 = float(ts.get("tp1") or r["tp1"])
                    t2 = float(ts.get("tp2") or r["tp2"])
                    t3 = float(ts.get("tp3") or r["tp3"])
                    conn.execute(
                        "UPDATE fibo_signals SET outcome_status = 'ACTIVE', entry_price = ?, stop_loss = ?, tp1 = ?, tp2 = ?, tp3 = ? WHERE id = ?",
                        (ep, sl, t1, t2, t3, r["id"]),
                    )
                except Exception:
                    pass
            # Also reset unconfirmed ARMED rows that had outcome_status='ACTIVE' with confirmation_tier='UNCONFIRMED'
            conn.execute(
                "UPDATE fibo_signals SET outcome_status = 'PENDING_CONFIRMATION' WHERE stage != 'FIRED_CONFIRMED_SHORT' AND confirmation_tier = 'UNCONFIRMED' AND outcome_status = 'ACTIVE'"
            )

    def upsert_signal(self, signal: FiboShortSignal, now_iso: str) -> dict[str, Any]:
        """Store or update a signal and evaluate its live outcome against current price."""
        sig_dict = signal.to_dict()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM fibo_signals WHERE id = ?",
                (signal.id,),
            ).fetchone()

            if row is None:
                if signal.stage == "FIRED_CONFIRMED_SHORT":
                    outcome = _evaluate_dual_shadow_outcome(
                        payload=sig_dict,
                        entry_price=signal.trade_setup.entry_price,
                        stop_loss_legacy=signal.trade_setup.stop_loss,
                        tp1=signal.trade_setup.tp1,
                        tp2=signal.trade_setup.tp2,
                        tp3=signal.trade_setup.tp3,
                        current_price=signal.current_price,
                        prev_outcome=None,
                        now_iso=now_iso,
                    )
                else:
                    outcome = {
                        "status": "PENDING_CONFIRMATION",
                        "tp1_hit": False,
                        "tp2_hit": False,
                        "tp3_hit": False,
                        "sl_hit": False,
                        "updated_at": now_iso,
                    }
                signal.outcome = outcome
                sig_dict["outcome"] = outcome
                conn.execute(
                    """
                    INSERT INTO fibo_signals (
                        id, symbol, higher_timeframe, stage, confirmation_tier,
                        signal_time, entry_price, stop_loss, tp1, tp2, tp3,
                        outcome_status, tp1_hit, tp2_hit, tp3_hit, sl_hit,
                        telegram_sent, payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                    """,
                    (
                        signal.id,
                        signal.symbol,
                        signal.higher_timeframe,
                        signal.stage,
                        signal.h1_confirmation.confirmation_tier,
                        signal.signal_time,
                        signal.trade_setup.entry_price,
                        signal.trade_setup.stop_loss,
                        signal.trade_setup.tp1,
                        signal.trade_setup.tp2,
                        signal.trade_setup.tp3,
                        outcome["status"],
                        int(bool(outcome.get("tp1_hit"))),
                        int(bool(outcome.get("tp2_hit"))),
                        int(bool(outcome.get("tp3_hit"))),
                        int(bool(outcome.get("sl_hit"))),
                        json.dumps(sig_dict, ensure_ascii=False),
                        now_iso,
                        now_iso,
                    ),
                )
                return outcome

            # Existing signal: check if it was already fired or is newly firing now
            signal.telegram_sent = bool(row["telegram_sent"])
            sig_dict["telegram_sent"] = signal.telegram_sent
            prev_payload: dict[str, Any] = {}
            try:
                prev_payload = json.loads(row["payload_json"])
            except Exception:
                prev_payload = {}

            was_fired = bool(
                row["stage"] == "FIRED_CONFIRMED_SHORT"
                or (
                    row["outcome_status"] != "PENDING_CONFIRMATION"
                    and row["confirmation_tier"] != "UNCONFIRMED"
                )
            )
            newly_fired = (not was_fired) and (signal.stage == "FIRED_CONFIRMED_SHORT")
            if newly_fired:
                locked_entry = signal.trade_setup.entry_price
                locked_sl = signal.trade_setup.stop_loss
                locked_tp1 = signal.trade_setup.tp1
                locked_tp2 = signal.trade_setup.tp2
                locked_tp3 = signal.trade_setup.tp3
                locked_time = signal.signal_time
                locked_tier = signal.h1_confirmation.confirmation_tier
                locked_stage = "FIRED_CONFIRMED_SHORT"
                eval_payload = sig_dict
                prev_outcome = None
            elif was_fired:
                locked_entry = float(row["entry_price"])
                locked_sl = float(row["stop_loss"])
                locked_tp1 = float(row["tp1"])
                locked_tp2 = float(row["tp2"])
                locked_tp3 = float(row["tp3"])
                locked_time = str(row["signal_time"])
                locked_tier = str(row["confirmation_tier"])
                locked_stage = "FIRED_CONFIRMED_SHORT"
                # Preserve the original fired payload setup/policies & outcome across subsequent H1 candles
                eval_payload = dict(prev_payload) if prev_payload else dict(sig_dict)
                eval_payload["current_price"] = signal.current_price
                if (
                    not eval_payload.get("matched_policies")
                    and signal.stage == "FIRED_CONFIRMED_SHORT"
                    and signal.matched_policies
                ):
                    eval_payload["matched_policies"] = list(signal.matched_policies)
                    eval_payload["primary_policy"] = signal.primary_policy
                    eval_payload["eligible_milestones"] = list(signal.eligible_milestones)
                prev_outcome = prev_payload.get("outcome") if isinstance(prev_payload.get("outcome"), dict) else {
                    "status": str(row["outcome_status"]),
                    "tp1_hit": bool(row["tp1_hit"]),
                    "tp2_hit": bool(row["tp2_hit"]),
                    "tp3_hit": bool(row["tp3_hit"]),
                    "sl_hit": bool(row["sl_hit"]),
                }
            else:
                locked_entry = signal.trade_setup.entry_price
                locked_sl = signal.trade_setup.stop_loss
                locked_tp1 = signal.trade_setup.tp1
                locked_tp2 = signal.trade_setup.tp2
                locked_tp3 = signal.trade_setup.tp3
                locked_time = signal.signal_time
                locked_tier = signal.h1_confirmation.confirmation_tier
                locked_stage = signal.stage
                eval_payload = sig_dict
                prev_outcome = None

            if locked_stage == "FIRED_CONFIRMED_SHORT":
                outcome = _evaluate_dual_shadow_outcome(
                    payload=eval_payload,
                    entry_price=locked_entry,
                    stop_loss_legacy=locked_sl,
                    tp1=locked_tp1,
                    tp2=locked_tp2,
                    tp3=locked_tp3,
                    current_price=signal.current_price,
                    prev_outcome=prev_outcome,
                    now_iso=now_iso,
                )
            else:
                outcome = {
                    "status": "PENDING_CONFIRMATION",
                    "tp1_hit": False,
                    "tp2_hit": False,
                    "tp3_hit": False,
                    "sl_hit": False,
                    "updated_at": now_iso,
                }

            signal.outcome = outcome
            eval_payload["outcome"] = outcome
            eval_payload["telegram_sent"] = signal.telegram_sent
            conn.execute(
                """
                UPDATE fibo_signals
                SET stage = ?, confirmation_tier = ?, signal_time = ?,
                    entry_price = ?, stop_loss = ?, tp1 = ?, tp2 = ?, tp3 = ?,
                    outcome_status = ?, tp1_hit = ?, tp2_hit = ?, tp3_hit = ?, sl_hit = ?,
                    payload_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    locked_stage,
                    locked_tier,
                    locked_time,
                    locked_entry,
                    locked_sl,
                    locked_tp1,
                    locked_tp2,
                    locked_tp3,
                    outcome["status"],
                    int(bool(outcome.get("tp1_hit"))),
                    int(bool(outcome.get("tp2_hit"))),
                    int(bool(outcome.get("tp3_hit"))),
                    int(bool(outcome.get("sl_hit"))),
                    json.dumps(eval_payload, ensure_ascii=False),
                    now_iso,
                    signal.id,
                ),
            )
            return outcome

    def refresh_and_build_shadow_comparison(
        self,
        live_prices: dict[str, float],
        now_iso: str,
    ) -> dict[str, Any]:
        """Refresh all fired signals against live prices and compute side-by-side Shadow Comparison (Legacy vs v4.0.21)."""
        raw_ledger: list[dict[str, Any]] = []
        try:
            now_dt = datetime.fromisoformat(str(now_iso).replace("Z", "+00:00"))
            if now_dt.tzinfo is None:
                now_dt = now_dt.replace(tzinfo=timezone.utc)
            else:
                now_dt = now_dt.astimezone(timezone.utc)
        except Exception:
            now_dt = datetime.now(timezone.utc)

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM fibo_signals
                WHERE stage = 'FIRED_CONFIRMED_SHORT'
                ORDER BY signal_time DESC, updated_at DESC
                """
            ).fetchall()

            for r in rows:
                try:
                    payload = json.loads(r["payload_json"])
                except Exception:
                    continue
                sym = str(r["symbol"]).upper()
                cp = float(live_prices.get(sym) or payload.get("current_price") or r["entry_price"])
                payload["current_price"] = cp
                prev_outcome = payload.get("outcome") if isinstance(payload.get("outcome"), dict) else {
                    "status": str(r["outcome_status"]),
                    "tp1_hit": bool(r["tp1_hit"]),
                    "tp2_hit": bool(r["tp2_hit"]),
                    "tp3_hit": bool(r["tp3_hit"]),
                    "sl_hit": bool(r["sl_hit"]),
                }
                outcome = _evaluate_dual_shadow_outcome(
                    payload=payload,
                    entry_price=float(r["entry_price"]),
                    stop_loss_legacy=float(r["stop_loss"]),
                    tp1=float(r["tp1"]),
                    tp2=float(r["tp2"]),
                    tp3=float(r["tp3"]),
                    current_price=cp,
                    prev_outcome=prev_outcome,
                    now_iso=now_iso,
                )
                payload["outcome"] = outcome
                conn.execute(
                    """
                    UPDATE fibo_signals
                    SET outcome_status = ?, tp1_hit = ?, tp2_hit = ?, tp3_hit = ?, sl_hit = ?,
                        payload_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        outcome["status"],
                        int(bool(outcome.get("tp1_hit"))),
                        int(bool(outcome.get("tp2_hit"))),
                        int(bool(outcome.get("tp3_hit"))),
                        int(bool(outcome.get("sl_hit"))),
                        json.dumps(payload, ensure_ascii=False),
                        now_iso,
                        r["id"],
                    ),
                )

                st = outcome.get("shadow_tracks") or {}
                leg = st.get("legacy_m1_raw") or {}
                v4 = st.get("v4_execution") or {}
                wave = payload.get("wave") or {}
                entry_px = float(r["entry_price"])
                price_move_pct = ((cp - entry_px) / max(1e-9, entry_px)) * 100.0

                raw_ledger.append(
                    {
                        "id": r["id"],
                        "symbol": sym,
                        "higher_timeframe": r["higher_timeframe"],
                        "confirmation_tier": r["confirmation_tier"],
                        "signal_time": r["signal_time"],
                        "swing_high_time": str(wave.get("swing_high_time") or r["id"]),
                        "score": float(payload.get("score") or 0.0),
                        "entry_price": entry_px,
                        "current_price": cp,
                        "price_move_pct": round(price_move_pct, 3),
                        "tp1": float(r["tp1"]),
                        "tp2": float(r["tp2"]),
                        "tp3": float(r["tp3"]),
                        "wave_ker": round(float(wave.get("wave_ker") or 0.0), 3),
                        "impulse_ker": round(float(wave.get("impulse_ker") or 0.0), 3),
                        "legacy": leg,
                        "v4": v4,
                    }
                )

        # Deduplicate overlapping impulse_low updates on the same (symbol, timeframe, swing_high_time), keeping earliest confirmation
        seen_waves: set[tuple[str, str, str]] = set()
        dedup_chronological: list[dict[str, Any]] = []
        for item in reversed(raw_ledger):
            wkey = (
                str(item["symbol"]),
                str(item["higher_timeframe"]),
                str(item.get("swing_high_time") or item["id"]),
            )
            if wkey in seen_waves:
                continue
            seen_waves.add(wkey)
            dedup_chronological.append(item)
        ledger = list(reversed(dedup_chronological))

        def _parse_sig_dt(sig_time_str: str) -> datetime:
            txt = str(sig_time_str or "").strip()
            try:
                dt = datetime.fromisoformat(txt.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=SYSTEM_TIMEZONE)
                return dt.astimezone(timezone.utc)
            except Exception:
                pass
            try:
                return (
                    datetime.strptime(txt, "%Y-%m-%d %H:%M")
                    .replace(tzinfo=SYSTEM_TIMEZONE)
                    .astimezone(timezone.utc)
                )
            except Exception:
                return now_dt


        def _summarize_track(
            track_id: str,
            label_vi: str,
            accept_fn: Any,
            nav_pnl_fn: Any,
            trade_ret_fn: Any,
            status_fn: Any,
            horizon_fn: Any,
        ) -> dict[str, Any]:
            total_m1 = len(ledger)
            accepted_items = [item for item in dedup_chronological if accept_fn(item)]
            rejected_count = total_m1 - len(accepted_items)
            active_count = 0
            closed_count = 0
            win_count = 0
            loss_count = 0
            trade_rets: list[float] = []
            nav_pnls: list[float] = []

            eq = 100.0
            peak = 100.0
            max_dd = 0.0
            terminal_states = (
                "STOPPED_OUT",
                "STOPPED_M6_0886",
                "TP3_HIT",
                "TP1_LOCKED_BE_STOP",
                "TP2_LOCKED_TP1_STOP",
                "TIME_EXIT",
                "EXPIRED_UNRESOLVED",
            )
            for item in accepted_items:
                st_str = str(status_fn(item))
                if st_str in terminal_states:
                    closed_count += 1
                else:
                    active_count += 1
                if st_str == "EXPIRED_UNRESOLVED":
                    continue
                t_ret = float(trade_ret_fn(item))
                n_pnl = float(nav_pnl_fn(item))
                trade_rets.append(t_ret)
                nav_pnls.append(n_pnl)
                if t_ret > 0:
                    win_count += 1
                elif t_ret < 0:
                    loss_count += 1
                eq += n_pnl
                if eq > peak:
                    peak = eq
                dd = (peak - eq) / max(1e-9, peak) * 100.0
                if dd > max_dd:
                    max_dd = dd


            judged = win_count + loss_count
            win_rate = round((win_count / judged) * 100.0, 2) if judged > 0 else 0.0
            avg_ret = round(sum(trade_rets) / len(trade_rets), 3) if trade_rets else 0.0
            cum_nav = round(sum(nav_pnls), 4)
            return {
                "track_id": track_id,
                "label_vi": label_vi,
                "total_m1_signals": total_m1,
                "accepted_count": len(accepted_items),
                "rejected_noise_count": rejected_count,
                "active_count": active_count,
                "closed_count": closed_count,
                "win_count": win_count,
                "loss_count": loss_count,
                "win_rate_pct": win_rate,
                "avg_trade_return_pct": avg_ret,
                "cum_nav_pnl_pct": cum_nav,
                "simulated_equity": round(100.0 + cum_nav, 4),
                "max_dd_pct": round(max_dd, 4),
            }

        def _std_horizon(item: dict[str, Any]) -> float:
            return 120.0 if str(item.get("higher_timeframe")) == "1d" else 72.0

        legacy_summary = _summarize_track(
            "legacy_m1_raw",
            "Hệ Thống Cũ · M1 Raw (Vốn Cố Định 20% · SL Đỉnh 1.0)",
            lambda x: True,
            lambda x: x["legacy"]["nav_pnl_pct"],
            lambda x: x["legacy"]["net_return_pct"],
            lambda x: x["legacy"]["status"],
            _std_horizon,
        )
        m6_summary = _summarize_track(
            "m6_risk",
            "v4.0.21 · M6 Expanded (SL 0.886 Ratchet · Risk 0.5% NAV)",
            lambda x: bool(x["v4"]["accepted_m6"]),
            lambda x: x["v4"]["m6_nav_pnl_pct"],
            lambda x: x["v4"]["raw_net_return_pct"],
            lambda x: x["v4"]["status"],
            _std_horizon,
        )
        sniper_summary = _summarize_track(
            "sniper_risk",
            "v4.0.21 · M6 Sniper (Phá Đáy H1 + KER ≥ 0.50 · Risk 0.5%)",
            lambda x: bool(x["v4"]["accepted_sniper"]),
            lambda x: x["v4"]["sniper_nav_pnl_pct"],
            lambda x: x["v4"]["raw_net_return_pct"],
            lambda x: x["v4"]["status"],
            _std_horizon,
        )
        elite_summary = _summarize_track(
            "elite_sniper_risk",
            "v4.0.21 · Elite Sniper (Carver PST + Phá Đáy H1 · Risk 0.5%)",
            lambda x: bool(x["v4"]["accepted_elite_sniper"]),
            lambda x: x["v4"]["elite_sniper_nav_pnl_pct"],
            lambda x: x["v4"]["raw_net_return_pct"],
            lambda x: x["v4"]["status"],
            _std_horizon,
        )
        rr1_summary = _summarize_track(
            "sniper_rr1_horizon24",
            "v4.0.21 · Sniper RR≥1 · 24h (Top Return/MaxDD 5.74x)",
            lambda x: bool(x["v4"]["accepted_sniper_rr1_24h"]),
            lambda x: x["v4"]["sniper_rr1_nav_pnl_pct"],
            lambda x: x["v4"]["raw_net_return_pct"],
            lambda x: x["v4"]["status"],
            lambda x: 24.0,
        )

        base_nav = legacy_summary["cum_nav_pnl_pct"]
        base_wr = legacy_summary["win_rate_pct"]
        base_avg_ret = legacy_summary["avg_trade_return_pct"]
        base_dd = legacy_summary["max_dd_pct"]
        for s in (legacy_summary, m6_summary, sniper_summary, elite_summary, rr1_summary):
            s["delta_nav_vs_legacy_pct"] = round(s["cum_nav_pnl_pct"] - base_nav, 4)
            s["delta_win_rate_vs_legacy_pct"] = round(s["win_rate_pct"] - base_wr, 2)
            s["delta_avg_return_vs_legacy_pct"] = round(s["avg_trade_return_pct"] - base_avg_ret, 3)
            s["delta_max_dd_vs_legacy_pct"] = round(s["max_dd_pct"] - base_dd, 4)
        return {
            "updated_at": now_iso,
            "total_fired_signals": len(ledger),
            "tracks": [
                legacy_summary,
                m6_summary,
                sniper_summary,
                elite_summary,
                rr1_summary,
            ],
            "signals_ledger": ledger[:50],
        }

    def is_already_fired(
        self,
        sig_id: str,
        *,
        signal: FiboShortSignal | None = None,
        cfg: FiboTrendShortConfig | None = None,
    ) -> bool:
        """Return True if this wave ID was already persisted in FIRED_CONFIRMED_SHORT state."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT stage, outcome_status, confirmation_tier, signal_time, telegram_sent, payload_json FROM fibo_signals WHERE id = ?",
                (sig_id,),
            ).fetchone()
            if row is None:
                return False
            was_fired = bool(
                row["stage"] == "FIRED_CONFIRMED_SHORT"
                or (
                    row["outcome_status"] != "PENDING_CONFIRMATION"
                    and row["confirmation_tier"] != "UNCONFIRMED"
                )
            )
            if not was_fired:
                return False
            if (
                signal is not None
                and not bool(row["telegram_sent"])
                and signal.stage == "FIRED_CONFIRMED_SHORT"
            ):
                prev_status = str(row["outcome_status"] or "").strip().upper()
                if prev_status in ("ACTIVE", "PENDING_CONFIRMATION") and is_qualified_short_for_telegram(signal, cfg):
                    try:
                        prev_payload = json.loads(row["payload_json"])
                    except Exception:
                        prev_payload = {}
                    active_cfg = cfg or FiboTrendShortConfig()
                    allowed = {
                        str(p).strip()
                        for p in active_cfg.telegram_allowed_policies
                        if str(p).strip()
                    }
                    prev_matched = {
                        str(p).strip()
                        for p in (prev_payload.get("matched_policies") or [])
                        if str(p).strip()
                    }
                    prev_wave = prev_payload.get("wave") or {}
                    prev_pump_ok = float(prev_wave.get("prior_pump_pct") or 0.0) >= float(
                        active_cfg.telegram_min_prior_pump_pct
                    )
                    if not prev_matched.intersection(allowed) or not prev_pump_ok:
                        return False
            return True

    def count_telegram_sent_since(self, cutoff_iso: str) -> int:
        """Count Fibo Short signals sent to Telegram since cutoff_iso (rolling 24h flood cap)."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM fibo_signals
                WHERE telegram_sent = 1 AND telegram_sent_at IS NOT NULL AND telegram_sent_at >= ?
                """,
                (cutoff_iso,),
            ).fetchone()
            return int(row["cnt"] if row else 0)

    def can_send_telegram(self, symbol: str, cooldown_minutes: int, now: datetime) -> bool:
        cutoff = (now - timedelta(minutes=cooldown_minutes)).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM fibo_signals
                WHERE symbol = ? AND telegram_sent = 1 AND telegram_sent_at >= ?
                """,
                (symbol, cutoff),
            ).fetchone()
            return (row["cnt"] if row else 0) == 0

    def is_new_telegram_signal(
        self,
        sig_id: str,
        start_after: datetime | None,
        now: datetime,
    ) -> bool:
        """Gate on the first confirmed candle persisted in the ledger, not a rescan."""
        if start_after is None or start_after.tzinfo is None or now.tzinfo is None:
            return False
        with self._connect() as conn:
            row = conn.execute(
                "SELECT stage, telegram_sent, signal_time FROM fibo_signals WHERE id = ?",
                (sig_id,),
            ).fetchone()
        if row is None or row["stage"] != "FIRED_CONFIRMED_SHORT" or row["telegram_sent"]:
            return False
        try:
            candle_open = datetime.fromisoformat(str(row["signal_time"]).replace("Z", "+00:00"))
            if candle_open.tzinfo is None:
                candle_open = candle_open.replace(tzinfo=SYSTEM_TIMEZONE)
            confirmed_at = candle_open.astimezone(timezone.utc) + timedelta(hours=1)
        except (ValueError, TypeError, OverflowError):
            return False
        return start_after.astimezone(timezone.utc) < confirmed_at <= now.astimezone(timezone.utc)

    def mark_telegram_sent(self, sig_id: str, now_iso: str) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM fibo_signals WHERE id = ?",
                (sig_id,),
            ).fetchone()
            updated_payload_json: str | None = None
            if row and row["payload_json"]:
                try:
                    payload = json.loads(row["payload_json"])
                    if isinstance(payload, dict):
                        payload["telegram_sent"] = True
                        updated_payload_json = json.dumps(payload, ensure_ascii=False)
                except Exception:
                    updated_payload_json = None
            if updated_payload_json is not None:
                conn.execute(
                    "UPDATE fibo_signals SET telegram_sent = 1, telegram_sent_at = ?, payload_json = ? WHERE id = ?",
                    (now_iso, updated_payload_json, sig_id),
                )
            else:
                conn.execute(
                    "UPDATE fibo_signals SET telegram_sent = 1, telegram_sent_at = ? WHERE id = ?",
                    (now_iso, sig_id),
                )


POLICY_LABELS_VI: dict[str, str] = {
    "elite_sniper_risk": "👑 Elite + Sniper (0.5% NAV Risk)",
    "sniper_rr1_horizon24": "🎯 Sniper RR≥1 · 24h",
    "sniper_risk": "⚡ Sniper (0.5% NAV Risk)",
    "sniper_horizon24": "⏱ Sniper · 24h",
    "m6_risk": "✅ Mốc 6 Chuẩn (Fibo 0.886 Risk)",
    "reference_m6_fixed": "📐 Mốc 6 Tham chiếu (Fixed)",
}


def is_qualified_short_for_telegram(
    signal: FiboShortSignal,
    cfg: FiboTrendShortConfig | None = None,
) -> bool:
    """Return True only when a signal is FIRED_CONFIRMED_SHORT, active, and passes all 4 v4.0.21 Short gates."""
    if signal.stage != "FIRED_CONFIRMED_SHORT" or not signal.h1_confirmation.confirmed:
        return False
    if isinstance(signal.outcome, dict) and signal.outcome:
        if any(
            bool(signal.outcome.get(k))
            for k in ("tp1_hit", "tp2_hit", "tp3_hit", "sl_hit")
        ):
            return False
        outcome_status = str(signal.outcome.get("status") or "").strip().upper()
        if outcome_status and outcome_status not in ("ACTIVE", "PENDING_CONFIRMATION"):
            return False

    active_cfg = cfg or FiboTrendShortConfig()
    if not active_cfg.telegram_require_qualified_short:
        return True

    # Gate 1 (F1A): Prior HTF pump must meet minimum exhaustion threshold (default >= +50%)
    w = signal.wave
    if float(w.prior_pump_pct or 0.0) < float(active_cfg.telegram_min_prior_pump_pct):
        return False

    # Gate 2 (F1B / F1C): Carver PST momentum collapse + Wave KER >= 0.35, or Wave KER >= 0.65
    f1_elite = bool(w.pst_pass and float(w.wave_ker or 0.0) >= 0.35)
    f1_expanded = bool(f1_elite or float(w.wave_ker or 0.0) >= 0.65)
    if not f1_expanded:
        return False

    # Gate 3 (F2): Decisive downward impulse drop >= 6% and Impulse KER >= 0.50
    raw_drop = float(w.impulse_drop_pct or 0.0)
    imp_drop_frac = raw_drop / 100.0 if raw_drop >= 2.0 else raw_drop
    if imp_drop_frac < 0.06 or float(w.impulse_ker or 0.0) < 0.50:
        return False

    # Gate 4 (F3 / F4): H1 structure break (cond2), pullback <= 0.786, valid M6 SL <= 12% cap, and Sniper policy
    c = signal.h1_confirmation
    if not (
        c.no_gain_1h
        and c.cond2_break_prev_low
        and float(c.max_pullback_fibo_ratio) <= 0.786
    ):
        return False

    ts = signal.trade_setup
    valid_ladder = bool(
        ts.sl_m6 > ts.entry_price > ts.tp1 > ts.tp2 > ts.tp3 > 0
        and ts.sl_within_cap
        and ts.recommended_notional_pct > 0.0
    )
    if not valid_ladder:
        return False
    allowed = {str(p).strip() for p in active_cfg.telegram_allowed_policies if str(p).strip()}
    matched = {str(p).strip() for p in (signal.matched_policies or []) if str(p).strip()}
    return bool(matched.intersection(allowed))


def format_fibo_telegram_message(signal: FiboShortSignal, public_url: str = "") -> str:
    """Format an ultra-concise, minimalist Vietnamese Telegram notification for a Qualified Fibo Short signal (v4.0.21)."""
    from html import escape
    from urllib.parse import quote

    sym_safe = escape(signal.symbol)
    tf_safe = escape(signal.higher_timeframe.upper())
    tier_safe = escape(str(signal.conviction_tier))
    ts = signal.trade_setup
    c = signal.h1_confirmation
    matched = set(signal.matched_policies or [])

    if "elite_sniper_risk" in matched and "sniper_rr1_horizon24" in matched:
        std_tag = "👑🎯 Elite + Sniper RR≥1"
    elif "elite_sniper_risk" in matched:
        std_tag = "👑 Elite + Sniper"
    elif "sniper_rr1_horizon24" in matched:
        std_tag = "🎯 Sniper RR≥1 · 24h"
    elif "sniper_risk" in matched:
        std_tag = "⚡ Sniper Short"
    elif "m6_risk" in matched:
        std_tag = "✅ Mốc 6 · Fibo 0.886"
    else:
        std_tag = "🎯 Fibo Short"

    horizon_h = (
        24
        if ("sniper_horizon24" in matched or "sniper_rr1_horizon24" in matched)
        else ts.max_hold_hours
    )

    lines = [
        f"🔻 <b>SHORT {sym_safe}</b> (<code>{tf_safe} → H1</code>)",
        f"🛡 <b>{std_tag}</b> | Điểm: <code>{signal.score:.0f}</code> (Hạng <b>{tier_safe}</b>)",
        f"🟡 <b>Entry:</b> <code>${ts.entry_price:.5g}</code> (Fibo <code>{c.current_fibo_ratio:.3f}</code>)",
        f"🛑 <b>SL (0.886):</b> <code>${ts.sl_m6:.5g}</code> (<code>+{ts.sl_m6_pct:.2f}%</code>)",
        f"🟢 <b>TP1 (40%):</b> <code>${ts.tp1:.5g}</code> (<code>-{ts.tp1_pct:.2f}%</code>) · <i>dời SL hòa vốn</i>",
        f"🎯 <b>TP2 (40%):</b> <code>${ts.tp2:.5g}</code> (<code>-{ts.tp2_pct:.2f}%</code>) · <i>dời SL về TP1</i>",
        f"🚀 <b>TP3 (20%):</b> <code>${ts.tp3:.5g}</code> (<code>-{ts.tp3_pct:.2f}%</code>)",
        f"⚖️ <b>R:R:</b> <code>1:{ts.rr_m6_tp2:.2f}</code> | <b>Vốn:</b> <code>{ts.recommended_notional_pct:.1f}% NAV</code> (Risk {ts.risk_budget_pct:.1f}%) | <b>Giữ:</b> <code>{horizon_h}h</code>",
    ]
    if public_url:
        url = f"{public_url.rstrip('/')}/#coin={quote(signal.symbol, safe='')}"
        lines.append(f"🔗 <a href=\"{escape(url, quote=True)}\">Chart {sym_safe}</a>")
    return "\n".join(lines)


def dispatch_fibo_telegram_signal(
    settings: AppSettings,
    store: FiboStateStore,
    signal: FiboShortSignal,
    now: datetime,
    *,
    newly_fired: bool | None = None,
    sent_this_cycle: int = 0,
    sent_last_24h: int | None = None,
) -> str:
    """Dispatch an already-upserted signal only when operating_mode, kill-switch, and all 4 v4.0.21 Short gates pass."""
    cfg = settings.fibo_trend_short
    if not cfg.telegram_enabled:
        return "disabled"
    operating_mode = (
        str(getattr(settings.scanner, "operating_mode", "research") or "research")
        .strip()
        .lower()
    )
    if operating_mode == "research":
        return "research_mode_blocked"
    ks_path = getattr(settings.scanner, "kill_switch_path", None)
    if ks_path:
        from dao_vang.scanner.operations import KillSwitch

        if KillSwitch(ks_path).active:
            return "kill_switch_active"
    if signal.stage != "FIRED_CONFIRMED_SHORT" or not signal.h1_confirmation.confirmed:
        return "not_confirmed"
    if not is_qualified_short_for_telegram(signal, cfg):
        return "unqualified_short"
    if cfg.telegram_start_after_utc is not None:
        if not store.is_new_telegram_signal(signal.id, cfg.telegram_start_after_utc, now) or (newly_fired is False):
            return "old_or_already_sent"
    else:
        if signal.telegram_sent or (newly_fired is False):
            return "old_or_already_sent"
    if not settings.telegram.bot_token or not settings.telegram.chat_id:
        return "not_configured"
    if sent_this_cycle >= cfg.telegram_max_per_cycle:
        return "cycle_cap"
    daily_cutoff_dt = now.astimezone(timezone.utc) - timedelta(hours=24)
    if cfg.telegram_start_after_utc is not None:
        daily_cutoff_dt = max(daily_cutoff_dt, cfg.telegram_start_after_utc.astimezone(timezone.utc))
    active_24h = (
        sent_last_24h
        if sent_last_24h is not None
        else store.count_telegram_sent_since(daily_cutoff_dt.isoformat())
    )
    if active_24h >= cfg.telegram_daily_limit:
        return "daily_cap"
    if not store.can_send_telegram(signal.symbol, cfg.telegram_cooldown_minutes, now):
        return "cooldown"
    try:
        from dao_vang.alerts.telegram import TelegramNotifier

        notifier = TelegramNotifier(
            settings.telegram,
            web_base_url=settings.web.public_url,
        )
        msg = format_fibo_telegram_message(signal, public_url=settings.web.public_url)
        if not notifier.send_message(msg, parse_mode="HTML"):
            return "failed"
        signal.telegram_sent = True
        store.mark_telegram_sent(signal.id, now.isoformat())
        logger.info(
            "fibo_telegram_qualified_short_sent",
            symbol=signal.symbol,
            timeframe=signal.higher_timeframe,
            prior_pump_pct=round(float(signal.wave.prior_pump_pct or 0.0), 4),
            primary_policy=signal.primary_policy,
            matched_policies=signal.matched_policies,
            score=signal.score,
        )
        return "sent"
    except Exception as exc:
        logger.warning("fibo_telegram_send_failed", symbol=signal.symbol, error=str(exc))
        return "failed"


def _scan_single_symbol(
    symbol: str,
    base_url: str,
    cfg: FiboTrendShortConfig,
) -> list[FiboShortSignal]:
    """Fetch H1 + H4/D1 klines for a symbol and evaluate Fibonacci Short setups."""
    klines_1h = fetch_closed_klines(symbol, "1h", base_url=base_url, limit=48)
    if len(klines_1h) < 15:
        return []

    results: list[FiboShortSignal] = []
    for tf in cfg.higher_timeframes:
        klines_htf = fetch_closed_klines(
            symbol,
            tf,
            base_url=base_url,
            limit=max(120, cfg.swing_lookback_bars + 64),
        )
        if len(klines_htf) < 8:
            continue
        sig = evaluate_symbol_timeframe(
            symbol=symbol,
            timeframe=tf,
            klines_htf=klines_htf,
            klines_1h=klines_1h,
            config=cfg,
        )
        if sig is not None and sig.stage != "INVALIDATED":
            results.append(sig)
    return results


def format_shadow_daily_telegram_report(
    shadow_comparison: dict[str, Any],
    monitor_state: dict[str, Any],
    paper_oos_summary: dict[str, Any],
    now: datetime,
    public_url: str = "",
) -> str:
    """Format a concise 6-line Vietnamese daily Telegram digest for Shadow Live & Paper OOS."""
    from html import escape

    vn_dt = as_system_timezone(now)
    date_str = vn_dt.strftime("%d/%m/%Y")
    tracks_by_id = {
        str(t.get("track_id")): t for t in (shadow_comparison.get("tracks") or []) if isinstance(t, dict)
    }
    sniper = tracks_by_id.get("sniper_risk") or {}
    elite = tracks_by_id.get("elite_sniper_risk") or {}
    healthy_h = int(monitor_state.get("healthy_hours_last_24h", 1))
    total_h = max(1, int(monitor_state.get("checked_hours_last_24h", 1)))
    oos_status = escape(str(paper_oos_summary.get("status") or "OBSERVING"))
    oos_rev = int(paper_oos_summary.get("revision") or 0)
    oos_closed = int(paper_oos_summary.get("closed_trades") or 0)
    oos_open = int(paper_oos_summary.get("open_positions") or 0)
    sniper_wr = float(sniper.get("win_rate_pct") or 0.0)
    sniper_wr_delta = float(sniper.get("delta_win_rate_vs_legacy_pct") or 0.0)
    sniper_avg = float(sniper.get("avg_trade_return_pct") or 0.0)
    sniper_dd = float(sniper.get("max_dd_pct") or 0.0)
    elite_wr = float(elite.get("win_rate_pct") or 0.0)
    elite_avg = float(elite.get("avg_trade_return_pct") or 0.0)
    elite_open = int(elite.get("active_count") or 0)
    elite_closed = int(elite.get("closed_count") or 0)

    lines = [
        f"📊 <b>BÁO CÁO SHADOW HÀNG NGÀY ({date_str})</b>",
        f"✅ <b>Ổn định:</b> <code>{healthy_h}/{total_h}h</code> xanh · Paper OOS <code>{oos_status}</code> (rev <code>#{oos_rev}</code>)",
        f"🎯 <b>Sniper v4.0.21:</b> WR <code>{sniper_wr:.1f}%</code> (<code>{sniper_wr_delta:+.1f}%</code> vs Cũ) · TB <code>{sniper_avg:+.2f}%/lệnh</code> · MaxDD <code>{sniper_dd:.2f}%</code>",
        f"👑 <b>Elite Sniper:</b> WR <code>{elite_wr:.1f}%</code> · TB <code>{elite_avg:+.2f}%/lệnh</code> · Mở <code>{elite_open}</code> / Đóng <code>{elite_closed}</code>",
        f"🧪 <b>Paper OOS (12 TK):</b> Đang mở <code>{oos_open}</code> · Đã đóng <code>{oos_closed}</code> lệnh",
    ]
    if public_url:
        url = f"{public_url.rstrip('/')}/#shadow"
        lines.append(f"🔗 <a href=\"{escape(url, quote=True)}\">Bảng Đối Chiếu Shadow Live</a>")
    return "\n".join(lines)


def evaluate_and_report_shadow_health(
    settings: AppSettings,
    storage_dir: Path,
    shadow_comparison: dict[str, Any],
    now: datetime,
    *,
    paper_oos_dir: Path | None = None,
    force_daily_report: bool = False,
) -> dict[str, Any]:
    """Run hourly Shadow stability checks, auto-heal missing artifacts, and send concise daily Telegram report."""
    monitor_path = storage_dir / "shadow_monitor_state.json"
    now_utc = now.astimezone(timezone.utc)
    now_iso = now_utc.isoformat()
    hour_bucket = now_utc.strftime("%Y-%m-%dT%H")
    today_vn = as_system_timezone(now_utc).strftime("%Y-%m-%d")
    vn_hour = as_system_timezone(now_utc).hour

    is_initial_boot = not monitor_path.exists()
    state: dict[str, Any] = {}
    if not is_initial_boot:
        try:
            state = json.loads(monitor_path.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                state = {}
        except Exception:
            state = {}

    history: list[dict[str, Any]] = [
        h for h in (state.get("hourly_checks") or []) if isinstance(h, dict)
    ]
    last_daily_report_date = str(state.get("last_daily_report_date") or (today_vn if is_initial_boot else ""))
    last_daily_report_at = state.get("last_daily_report_at")

    # Auto-heal OBSERVED_VIEWS.json fallback if paper_oos_v1 exists
    active_oos_dir = paper_oos_dir or Path("artifacts/fibo_trend_short/paper_oos_v1")
    if paper_oos_dir is None and not active_oos_dir.exists():
        active_oos_dir = Path(__file__).resolve().parents[3] / "artifacts" / "fibo_trend_short" / "paper_oos_v1"
    obs_views_path = active_oos_dir.parent / "research_v4_0_21" / "OBSERVED_VIEWS.json"
    if active_oos_dir.exists() and not obs_views_path.exists():
        try:
            obs_views_path.parent.mkdir(parents=True, exist_ok=True)
            obs_views_path.write_text("{}", encoding="utf-8")
        except OSError:
            pass

    # Default Paper OOS v1 to unhealthy until STATUS.json is verified fresh and valid
    paper_oos_summary: dict[str, Any] = {
        "status": "MISSING",
        "revision": 0,
        "open_positions": 0,
        "closed_trades": 0,
        "healthy": False,
    }
    status_file = active_oos_dir / "STATUS.json"
    now_ms = now_utc.timestamp() * 1000.0
    if status_file.is_file():
        try:
            st_raw = json.loads(status_file.read_text(encoding="utf-8"))
            hb_ms = int(st_raw.get("heartbeat_ms") or 0)
            last_bar_ms = int(st_raw.get("last_bar_ms") or 0)
            last_sig_ms = int(st_raw.get("last_signal_ms") or 0)
            hb_age_s = max(0.0, (now_ms - hb_ms) / 1000.0) if hb_ms > 0 else 999999.0
            bar_lag_s = max(0.0, (now_ms - last_bar_ms) / 1000.0) if last_bar_ms > 0 else 999999.0
            sig_lag_s = max(0.0, (now_ms - last_sig_ms) / 1000.0) if last_sig_ms > 0 else 999999.0
            closed_map = st_raw.get("closed_trades") or {}
            total_closed = sum(int(v or 0) for v in closed_map.values()) if isinstance(closed_map, dict) else 0
            st_name = str(st_raw.get("status") or "UNKNOWN")
            paper_oos_summary = {
                "status": st_name,
                "revision": int(st_raw.get("revision") or 0),
                "open_positions": int(st_raw.get("open_positions") or 0),
                "closed_trades": total_closed,
                "heartbeat_age_sec": round(hb_age_s, 1),
                "bar_lag_sec": round(bar_lag_s, 1),
                "signal_lag_sec": round(sig_lag_s, 1),
                "healthy": bool(
                    st_name in ("OBSERVING", "ARMED")
                    and st_raw.get("error") is None
                    and int(st_raw.get("critical_incidents") or 0) == 0
                    and hb_age_s <= 600.0
                    and bar_lag_s <= 900.0
                    and sig_lag_s <= 5400.0
                ),
            }
        except Exception:
            paper_oos_summary["status"] = "MALFORMED"

    # Perform hourly stability check when entering a new hour bucket (or on first check)
    issues: list[str] = []
    sc_updated_dt = _parse_fibo_signal_dt(shadow_comparison.get("updated_at"))
    if sc_updated_dt is None or abs((now_utc - sc_updated_dt).total_seconds()) > 900.0:
        issues.append("shadow_snapshot_stale")

    tracks = shadow_comparison.get("tracks") or []
    if len(tracks) < 5:
        issues.append("missing_shadow_tracks")
    for tr in tracks:
        if not isinstance(tr, dict):
            continue
        if int(tr.get("accepted_count", 0)) + int(tr.get("rejected_noise_count", 0)) != int(tr.get("total_m1_signals", 0)):
            issues.append(f"count_mismatch:{tr.get('track_id')}")
        if int(tr.get("active_count", 0)) + int(tr.get("closed_count", 0)) != int(tr.get("accepted_count", 0)):
            issues.append(f"lifecycle_mismatch:{tr.get('track_id')}")
    if not paper_oos_summary.get("healthy", False):
        issues.append(f"paper_oos_unhealthy:{paper_oos_summary.get('status')}")

    is_healthy = len(issues) == 0
    if not history or history[-1].get("hour_utc") != hour_bucket:
        sniper_tr = next((t for t in tracks if isinstance(t, dict) and t.get("track_id") == "sniper_risk"), {})
        history.append(
            {
                "hour_utc": hour_bucket,
                "checked_at": now_iso,
                "healthy": is_healthy,
                "issues": issues,
                "paper_oos_revision": paper_oos_summary.get("revision", 0),
                "sniper_win_rate_pct": sniper_tr.get("win_rate_pct", 0.0),
                "sniper_avg_return_pct": sniper_tr.get("avg_trade_return_pct", 0.0),
            }
        )
        history = history[-48:]

    recent_24 = history[-24:]
    healthy_24 = sum(1 for h in recent_24 if h.get("healthy"))
    summary = {
        "status": "healthy" if is_healthy else "degraded",
        "last_hourly_check_utc": history[-1]["checked_at"] if history else now_iso,
        "current_hour_utc": hour_bucket,
        "checked_hours_last_24h": len(recent_24),
        "healthy_hours_last_24h": healthy_24,
        "issues": issues,
        "paper_oos": paper_oos_summary,
        "last_daily_report_date": last_daily_report_date or None,
        "last_daily_report_at": last_daily_report_at,
        "daily_report_sent_this_cycle": False,
    }

    # Send concise Daily Shadow Report once per day (>= 08:00 Vietnam time) when healthy
    cfg = settings.fibo_trend_short
    operating_mode = (
        str(getattr(settings.scanner, "operating_mode", "research") or "research")
        .strip()
        .lower()
    )
    should_send_daily = bool(
        force_daily_report
        or (
            not is_initial_boot
            and is_healthy
            and last_daily_report_date
            and today_vn > last_daily_report_date
            and vn_hour >= 8
        )
    )
    if (
        should_send_daily
        and cfg.telegram_enabled
        and operating_mode != "research"
        and settings.telegram.bot_token
        and settings.telegram.chat_id
    ):
        ks_active = False
        ks_path = getattr(settings.scanner, "kill_switch_path", None)
        if ks_path:
            from dao_vang.scanner.operations import KillSwitch

            ks_active = KillSwitch(ks_path).active
        if not ks_active:
            try:
                from dao_vang.alerts.telegram import TelegramNotifier

                notifier = TelegramNotifier(
                    settings.telegram,
                    web_base_url=settings.web.public_url,
                )
                msg = format_shadow_daily_telegram_report(
                    shadow_comparison=shadow_comparison,
                    monitor_state=summary,
                    paper_oos_summary=paper_oos_summary,
                    now=now_utc,
                    public_url=settings.web.public_url,
                )
                if notifier.send_message(msg, parse_mode="HTML"):
                    last_daily_report_date = today_vn
                    last_daily_report_at = now_iso
                    summary["last_daily_report_date"] = last_daily_report_date
                    summary["last_daily_report_at"] = last_daily_report_at
                    summary["daily_report_sent_this_cycle"] = True
                    logger.info("shadow_daily_telegram_report_sent", date_vn=today_vn)
            except Exception as exc:
                logger.warning("shadow_daily_telegram_report_failed", error=str(exc))

    persisted = {
        "updated_at": now_iso,
        "last_daily_report_date": last_daily_report_date,
        "last_daily_report_at": last_daily_report_at,
        "hourly_checks": history,
    }
    _atomic_json_write(monitor_path, persisted)
    return summary


def run_cycle(
    settings: AppSettings,
    *,
    symbols: Sequence[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Execute one full scan cycle of the Confirmed Reversal & Fibonacci Short branch."""
    cfg = settings.fibo_trend_short
    storage_dir = settings.paths.data_dir / "fibo_trend_short"
    snapshot_path = storage_dir / "snapshot.json"
    store = FiboStateStore(storage_dir / "state.sqlite3")

    now = now or datetime.now(timezone.utc)
    now_iso = now.isoformat()

    if not cfg.enabled:
        payload = {
            "status": "disabled",
            "branch": "fibo_trend_short",
            "updated_at": now_iso,
            "items": [],
        }
        _atomic_json_write(snapshot_path, payload)
        return payload

    candidate_symbols = select_candidate_symbols(settings, explicit_symbols=symbols)
    pit_meta = load_latest_pit_top50_membership()
    pit_by_sym = pit_meta.get("by_symbol", {})
    universe_cfg = load_fibo_universe_config(cfg.universe_config_path)
    tier_s_set = {str(s).strip().upper() for s in universe_cfg.get("tier_s_core", DEFAULT_TIER_S_CORE)}
    tier_a_set = {str(s).strip().upper() for s in universe_cfg.get("tier_a_extended", [])}
    base_url = str(settings.binance.base_url).rstrip("/")

    signals: list[FiboShortSignal] = []
    max_workers = max(1, min(6, int(settings.collection.max_concurrency)))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_scan_single_symbol, sym, base_url, cfg): sym
            for sym in candidate_symbols
        }
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                sym_signals = fut.result()
                for sig in sym_signals:
                    p_info = pit_by_sym.get(sig.symbol)
                    if p_info:
                        sig.alpha_layers["universe_tier"] = "PIT_TOP50"
                        sig.alpha_layers["pit_top50_rank"] = p_info["rank"]
                        sig.alpha_layers["median_quote_vol_63d"] = round(p_info["median_quote_volume"], 2)
                        sig.alpha_layers["wick_p90_pct"] = round(p_info["wick_p90_pct"], 3)
                        sig.alpha_layers["active_days_63d"] = p_info["active_days"]
                    elif sig.symbol in tier_s_set:
                        sig.alpha_layers["universe_tier"] = "TIER_S"
                    elif sig.symbol in tier_a_set:
                        sig.alpha_layers["universe_tier"] = "TIER_A"
                    else:
                        sig.alpha_layers["universe_tier"] = "DYNAMIC"
                signals.extend(sym_signals)
            except Exception as exc:
                logger.warning("fibo_symbol_scan_error", symbol=sym, error=str(exc))

    # Persist outcomes and optionally dispatch Telegram notifications for FIRED signals
    stage_priority = {
        "FIRED_CONFIRMED_SHORT": 0,
        "ARMED_IN_FIBO_ZONE": 1,
        "WATCHING_PULLBACK": 2,
        "INVALIDATED": 3,
    }
    signals.sort(
        key=lambda s: (
            stage_priority.get(s.stage, 9),
            -s.score,
            -s.trade_setup.rr_tp2,
        )
    )

    telegram_sent_this_cycle = 0
    daily_cutoff_dt = now.astimezone(timezone.utc) - timedelta(hours=24)
    if cfg.telegram_start_after_utc is not None:
        daily_cutoff_dt = max(daily_cutoff_dt, cfg.telegram_start_after_utc.astimezone(timezone.utc))
    daily_cutoff_iso = daily_cutoff_dt.isoformat()
    telegram_sent_last_24h = store.count_telegram_sent_since(daily_cutoff_iso)
    telegram_dispatch_counts: dict[str, int] = {}

    for sig in signals:
        was_already_fired = store.is_already_fired(sig.id, signal=sig, cfg=cfg)
        store.upsert_signal(sig, now_iso)
        newly_fired = (not was_already_fired) and (sig.stage == "FIRED_CONFIRMED_SHORT")
        dispatch_status = dispatch_fibo_telegram_signal(
            settings,
            store,
            sig,
            now,
            newly_fired=newly_fired,
            sent_this_cycle=telegram_sent_this_cycle,
            sent_last_24h=telegram_sent_last_24h,
        )
        telegram_dispatch_counts[dispatch_status] = telegram_dispatch_counts.get(dispatch_status, 0) + 1
        if dispatch_status == "sent":
            telegram_sent_this_cycle += 1
            telegram_sent_last_24h += 1

    if cfg.telegram_enabled:
        logger.info("fibo_telegram_dispatch_summary", counts=telegram_dispatch_counts)

    live_prices: dict[str, float] = {s.symbol: float(s.current_price) for s in signals if s.current_price > 0}
    try:
        for t in fetch_all_tickers(base_url):
            sym_t = str(t.get("symbol", "")).upper()
            px_t = float(t.get("lastPrice", 0.0) or 0.0)
            if sym_t and px_t > 0 and sym_t not in live_prices:
                live_prices[sym_t] = px_t
    except Exception:
        pass

    shadow_comparison = store.refresh_and_build_shadow_comparison(live_prices, now_iso)

    shadow_health_monitor = evaluate_and_report_shadow_health(
        settings=settings,
        storage_dir=storage_dir,
        shadow_comparison=shadow_comparison,
        now=now,
    )
    fired_count = sum(1 for s in signals if s.stage == "FIRED_CONFIRMED_SHORT")
    qualified_fired_count = sum(1 for s in signals if is_qualified_short_for_telegram(s, cfg))
    armed_count = sum(1 for s in signals if s.stage == "ARMED_IN_FIBO_ZONE")
    watching_count = sum(1 for s in signals if s.stage == "WATCHING_PULLBACK")
    sniper_count = sum(1 for s in signals if "sniper_risk" in s.matched_policies)
    elite_sniper_count = sum(1 for s in signals if "elite_sniper_risk" in s.matched_policies)
    rr1_24h_count = sum(1 for s in signals if "sniper_rr1_horizon24" in s.matched_policies)
    m6_count = sum(1 for s in signals if "m6_risk" in s.matched_policies)

    payload = {
        "status": "ok",
        "branch": "fibo_trend_short",
        "branch_title_vi": "Xác Nhận Đảo Chiều & Short Theo Xu Hướng Mới (Fibonacci H4/D1 → H1 · v4.0.21)",
        "updated_at": now_iso,
        "scanned_symbols_count": len(candidate_symbols),
        "total_signals": len(signals),
        "fired_count": fired_count,
        "qualified_fired_count": qualified_fired_count,
        "telegram_sent_this_cycle": telegram_sent_this_cycle,
        "telegram_sent_last_24h": telegram_sent_last_24h,
        "armed_count": armed_count,
        "watching_count": watching_count,
        "policy_counts": {
            "sniper_risk": sniper_count,
            "elite_sniper_risk": elite_sniper_count,
            "sniper_rr1_horizon24": rr1_24h_count,
            "m6_risk": m6_count,
        },
        "telegram": {
            "enabled": cfg.telegram_enabled,
            "operating_mode": str(getattr(settings.scanner, "operating_mode", "research")),
            "start_after_utc": cfg.telegram_start_after_utc.isoformat() if cfg.telegram_start_after_utc else None,
            "cooldown_minutes": cfg.telegram_cooldown_minutes,
            "require_qualified_short": cfg.telegram_require_qualified_short,
            "min_prior_pump_pct": cfg.telegram_min_prior_pump_pct,
            "max_per_cycle": cfg.telegram_max_per_cycle,
            "daily_limit": cfg.telegram_daily_limit,
            "dispatch_counts": telegram_dispatch_counts,
        },
        "pit_universe": {
            "month": pit_meta.get("month"),
            "ranking_interval": pit_meta.get("ranking_interval"),
            "member_count": len(pit_meta.get("members", [])),
            "wick_p90_max_pct": 3.2,
            "min_active_days": 50,
        },
        "shadow_comparison": shadow_comparison,
        "shadow_health_monitor": shadow_health_monitor,
        "config": {
            "higher_timeframes": cfg.higher_timeframes,
            "confirm_timeframe": cfg.confirm_timeframe,
            "fibo_entry_min": cfg.fibo_entry_min,
            "fibo_entry_max": cfg.fibo_entry_max,
            "tp1_fibo_level": cfg.tp1_fibo_level,
            "tp2_extension_level": cfg.tp2_extension_level,
            "tp3_extension_level": cfg.tp3_extension_level,
            "in_sample_end_utc": cfg.in_sample_end_utc,
            "universe_mode": cfg.universe_mode,
            "telegram_enabled": cfg.telegram_enabled,
            "telegram_require_qualified_short": cfg.telegram_require_qualified_short,
            "telegram_min_prior_pump_pct": cfg.telegram_min_prior_pump_pct,
            "telegram_max_per_cycle": cfg.telegram_max_per_cycle,
            "telegram_daily_limit": cfg.telegram_daily_limit,
            "telegram_allowed_policies": cfg.telegram_allowed_policies,
        },
        "items": [s.to_dict() for s in signals],
    }
    _atomic_json_write(snapshot_path, payload)
    return payload
