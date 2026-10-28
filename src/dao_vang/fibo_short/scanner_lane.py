"""Live/Shadow Scanner Lane for the Confirmed Reversal & Fibonacci Short branch (H4/D1 -> H1)."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Sequence

import httpx

from dao_vang.config.settings import AppSettings, FiboTrendShortConfig
from dao_vang.domain.time import as_system_timezone
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


def fetch_closed_klines(
    symbol: str,
    interval: Literal["1h", "4h", "1d"],
    *,
    base_url: str = "https://fapi.binance.com",
    limit: int = 60,
    now_ms: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch closed klines from Binance USD-M Futures, excluding the currently forming bar."""
    current_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    try:
        resp = _HTTP_CLIENT.get(
            f"{base_url.rstrip('/')}/fapi/v1/klines",
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
    return closed_bars[-limit:]


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

    # --- 1. Legacy Track (M1 Raw, SL 1.0, No Ratchet, Fixed 20% NAV) ---
    tp1_hit = bool(prev.get("tp1_hit", False))
    tp2_hit = bool(prev.get("tp2_hit", False))
    tp3_hit = bool(prev.get("tp3_hit", False))
    sl_hit = bool(prev.get("sl_hit", False))
    status = str(prev.get("status") or "ACTIVE")
    if status == "PENDING_CONFIRMATION":
        status = "ACTIVE"

    if not sl_hit and not tp3_hit:
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

    leg1_px = tp1 if tp1_hit else (sl_leg if sl_hit else cp)
    leg2_px = tp2 if tp2_hit else (sl_leg if sl_hit else cp)
    leg3_px = tp3 if tp3_hit else (sl_leg if sl_hit else cp)
    legacy_gross_pct = (
        0.40 * (entry - leg1_px) + 0.40 * (entry - leg2_px) + 0.20 * (entry - leg3_px)
    ) / max(1e-9, entry) * 100.0
    legacy_net_pct = round(legacy_gross_pct - cost_rt_pct, 4)
    legacy_nav_pnl_pct = round(legacy_net_pct * (legacy_notional_pct / 100.0), 4)

    # --- 2. Upgraded v4.0.21 Track (SL 0.886 + Ratcheted BE/TP1 Stop + Risk 0.5% NAV) ---
    prev_v4 = (prev.get("shadow_tracks") or {}).get("v4_execution") or {}
    v4_tp1_hit = bool(prev_v4.get("tp1_hit", False))
    v4_tp2_hit = bool(prev_v4.get("tp2_hit", False))
    v4_tp3_hit = bool(prev_v4.get("tp3_hit", False))
    v4_sl_hit = bool(prev_v4.get("sl_hit", False))
    v4_be_stop_hit = bool(prev_v4.get("be_stop_hit", False))
    v4_tp1_trail_hit = bool(prev_v4.get("tp1_trail_hit", False))
    v4_status = str(prev_v4.get("status") or "ACTIVE")

    if not v4_sl_hit and not v4_be_stop_hit and not v4_tp1_trail_hit and not v4_tp3_hit:
        # Check TP hits first if price dropped to targets
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

        # Check Ratcheted Stop-Loss if not TP3
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

    active_v4_sl = tp1 if v4_tp2_hit else (entry if v4_tp1_hit else sl_m6)
    v4_p1 = tp1 if v4_tp1_hit else (sl_m6 if v4_sl_hit else cp)
    v4_p2 = tp2 if v4_tp2_hit else (entry if v4_be_stop_hit else (sl_m6 if v4_sl_hit else cp))
    v4_p3 = (
        tp3
        if v4_tp3_hit
        else (
            tp1
            if v4_tp1_trail_hit
            else (entry if v4_be_stop_hit else (sl_m6 if v4_sl_hit else cp))
        )
    )
    v4_gross_pct = (
        0.40 * (entry - v4_p1) + 0.40 * (entry - v4_p2) + 0.20 * (entry - v4_p3)
    ) / max(1e-9, entry) * 100.0
    v4_net_pct = round(v4_gross_pct - cost_rt_pct, 4)
    v4_exec_nav_pnl_pct = round(v4_net_pct * (rec_notional_pct / 100.0), 4)

    diag = _build_v421_filter_diagnostics(payload)

    return {
        "status": status,
        "tp1_hit": tp1_hit,
        "tp2_hit": tp2_hit,
        "tp3_hit": tp3_hit,
        "sl_hit": sl_hit,
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
                # Preserve the original fired payload setup/policies if current candle reverted to ARMED/WATCHING
                eval_payload = prev_payload if signal.stage != "FIRED_CONFIRMED_SHORT" and prev_payload else sig_dict
                eval_payload["current_price"] = signal.current_price
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
        ledger: list[dict[str, Any]] = []
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

                ledger.append(
                    {
                        "id": r["id"],
                        "symbol": sym,
                        "higher_timeframe": r["higher_timeframe"],
                        "confirmation_tier": r["confirmation_tier"],
                        "signal_time": r["signal_time"],
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

        def _summarize_track(
            track_id: str,
            label_vi: str,
            accept_fn: Any,
            nav_pnl_fn: Any,
            trade_ret_fn: Any,
            status_fn: Any,
        ) -> dict[str, Any]:
            total_m1 = len(ledger)
            accepted_items = [item for item in ledger if accept_fn(item)]
            rejected_count = total_m1 - len(accepted_items)
            active_count = 0
            closed_count = 0
            win_count = 0
            loss_count = 0
            trade_rets: list[float] = []
            nav_pnls: list[float] = []

            # Chronological order for cumulative NAV & drawdown
            eq = 100.0
            peak = 100.0
            max_dd = 0.0
            for item in reversed(accepted_items):
                st_str = str(status_fn(item))
                t_ret = float(trade_ret_fn(item))
                n_pnl = float(nav_pnl_fn(item))
                trade_rets.append(t_ret)
                nav_pnls.append(n_pnl)
                if st_str in ("STOPPED_OUT", "STOPPED_M6_0886", "TP3_HIT", "TP1_LOCKED_BE_STOP", "TP2_LOCKED_TP1_STOP"):
                    closed_count += 1
                else:
                    active_count += 1
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

        legacy_summary = _summarize_track(
            "legacy_m1_raw",
            "Hệ Thống Cũ · M1 Raw (Vốn Cố Định 20% · SL Đỉnh 1.0)",
            lambda x: True,
            lambda x: x["legacy"]["nav_pnl_pct"],
            lambda x: x["legacy"]["net_return_pct"],
            lambda x: x["legacy"]["status"],
        )
        m6_summary = _summarize_track(
            "m6_risk",
            "v4.0.21 · M6 Expanded (SL 0.886 Ratchet · Risk 0.5% NAV)",
            lambda x: bool(x["v4"]["accepted_m6"]),
            lambda x: x["v4"]["m6_nav_pnl_pct"],
            lambda x: x["v4"]["raw_net_return_pct"],
            lambda x: x["v4"]["status"],
        )
        sniper_summary = _summarize_track(
            "sniper_risk",
            "v4.0.21 · M6 Sniper (Phá Đáy H1 + KER ≥ 0.50 · Risk 0.5%)",
            lambda x: bool(x["v4"]["accepted_sniper"]),
            lambda x: x["v4"]["sniper_nav_pnl_pct"],
            lambda x: x["v4"]["raw_net_return_pct"],
            lambda x: x["v4"]["status"],
        )
        elite_summary = _summarize_track(
            "elite_sniper_risk",
            "v4.0.21 · Elite Sniper (Carver PST + Phá Đáy H1 · Risk 0.5%)",
            lambda x: bool(x["v4"]["accepted_elite_sniper"]),
            lambda x: x["v4"]["elite_sniper_nav_pnl_pct"],
            lambda x: x["v4"]["raw_net_return_pct"],
            lambda x: x["v4"]["status"],
        )
        rr1_summary = _summarize_track(
            "sniper_rr1_horizon24",
            "v4.0.21 · Sniper RR≥1 · 24h (Top Return/MaxDD 5.74x)",
            lambda x: bool(x["v4"]["accepted_sniper_rr1_24h"]),
            lambda x: x["v4"]["sniper_rr1_nav_pnl_pct"],
            lambda x: x["v4"]["raw_net_return_pct"],
            lambda x: x["v4"]["status"],
        )

        base_nav = legacy_summary["cum_nav_pnl_pct"]
        for s in (legacy_summary, m6_summary, sniper_summary, elite_summary, rr1_summary):
            s["delta_nav_vs_legacy_pct"] = round(s["cum_nav_pnl_pct"] - base_nav, 4)

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
    """Return True only when a signal is FIRED_CONFIRMED_SHORT and passes the Short qualification standard."""
    if signal.stage != "FIRED_CONFIRMED_SHORT" or not signal.h1_confirmation.confirmed:
        return False
    active_cfg = cfg or FiboTrendShortConfig()
    if not active_cfg.telegram_require_qualified_short:
        return True
    ts = signal.trade_setup
    valid_ladder = bool(
        ts.sl_m6 > ts.entry_price > ts.tp1 > ts.tp2 > ts.tp3 > 0
        and ts.sl_within_cap
    )
    if not valid_ladder:
        return False
    allowed = {str(p).strip() for p in active_cfg.telegram_allowed_policies if str(p).strip()}
    matched = {str(p).strip() for p in (signal.matched_policies or []) if str(p).strip()}
    return bool(matched.intersection(allowed))


def format_fibo_telegram_message(signal: FiboShortSignal, public_url: str = "") -> str:
    """Format an ultra-concise, minimalist Vietnamese Telegram notification for a Qualified Fibo Short signal (v4.0.21)."""
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
        f"🔻 <b>SHORT {signal.symbol}</b> (<code>{signal.higher_timeframe.upper()} → H1</code>)",
        f"🛡 <b>{std_tag}</b> | Điểm: <code>{signal.score:.0f}</code> (Hạng <b>{signal.conviction_tier}</b>)",
        f"🟡 <b>Entry:</b> <code>${ts.entry_price:.5g}</code> (Fibo <code>{c.current_fibo_ratio:.3f}</code>)",
        f"🛑 <b>SL (0.886):</b> <code>${ts.sl_m6:.5g}</code> (<code>+{ts.sl_m6_pct:.2f}%</code>)",
        f"🟢 <b>TP1 (40%):</b> <code>${ts.tp1:.5g}</code> (<code>-{ts.tp1_pct:.2f}%</code>) · <i>dời SL hòa vốn</i>",
        f"🎯 <b>TP2 (40%):</b> <code>${ts.tp2:.5g}</code> (<code>-{ts.tp2_pct:.2f}%</code>) · <i>dời SL về TP1</i>",
        f"🚀 <b>TP3 (20%):</b> <code>${ts.tp3:.5g}</code> (<code>-{ts.tp3_pct:.2f}%</code>)",
        f"⚖️ <b>R:R:</b> <code>1:{ts.rr_m6_tp2:.2f}</code> | <b>Vốn:</b> <code>{ts.recommended_notional_pct:.1f}% NAV</code> (Risk {ts.risk_budget_pct:.1f}%) | <b>Giữ:</b> <code>{horizon_h}h</code>",
    ]
    if public_url:
        url = f"{public_url.rstrip('/')}/#coin={signal.symbol}"
        lines.append(f"🔗 <a href=\"{url}\">Chart {signal.symbol}</a>")
    return "\n".join(lines)


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


def run_cycle(
    settings: AppSettings,
    *,
    symbols: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Execute one full scan cycle of the Confirmed Reversal & Fibonacci Short branch."""
    cfg = settings.fibo_trend_short
    storage_dir = settings.paths.data_dir / "fibo_trend_short"
    snapshot_path = storage_dir / "snapshot.json"
    store = FiboStateStore(storage_dir / "state.sqlite3")

    now = datetime.now(timezone.utc)
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
    for sig in signals:
        store.upsert_signal(sig, now_iso)
        if sig.stage == "FIRED_CONFIRMED_SHORT" and not is_qualified_short_for_telegram(sig, cfg):
            logger.info(
                "fibo_telegram_skipped_unqualified_short",
                symbol=sig.symbol,
                timeframe=sig.higher_timeframe,
                primary_policy=sig.primary_policy,
                matched_policies=sig.matched_policies,
            )
            continue
        if (
            is_qualified_short_for_telegram(sig, cfg)
            and cfg.telegram_enabled
            and not sig.telegram_sent
            and settings.telegram.bot_token
            and settings.telegram.chat_id
            and store.can_send_telegram(sig.symbol, cfg.telegram_cooldown_minutes, now)
        ):
            try:
                from dao_vang.alerts.telegram import TelegramNotifier

                notifier = TelegramNotifier(
                    settings.telegram,
                    web_base_url=settings.web.public_url,
                )
                msg = format_fibo_telegram_message(sig, public_url=settings.web.public_url)
                if notifier.send_message(msg, parse_mode="HTML"):
                    sig.telegram_sent = True
                    store.mark_telegram_sent(sig.id, now_iso)
                    telegram_sent_this_cycle += 1
                    logger.info(
                        "fibo_telegram_qualified_short_sent",
                        symbol=sig.symbol,
                        timeframe=sig.higher_timeframe,
                        primary_policy=sig.primary_policy,
                        matched_policies=sig.matched_policies,
                        score=sig.score,
                    )
            except Exception as exc:
                logger.warning("fibo_telegram_send_failed", symbol=sig.symbol, error=str(exc))

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
        "armed_count": armed_count,
        "watching_count": watching_count,
        "policy_counts": {
            "sniper_risk": sniper_count,
            "elite_sniper_risk": elite_sniper_count,
            "sniper_rr1_horizon24": rr1_24h_count,
            "m6_risk": m6_count,
        },
        "pit_universe": {
            "month": pit_meta.get("month"),
            "ranking_interval": pit_meta.get("ranking_interval"),
            "member_count": len(pit_meta.get("members", [])),
            "wick_p90_max_pct": 3.2,
            "min_active_days": 50,
        },
        "shadow_comparison": shadow_comparison,
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
            "telegram_allowed_policies": cfg.telegram_allowed_policies,
        },
        "items": [s.to_dict() for s in signals],
    }
    _atomic_json_write(snapshot_path, payload)
    return payload
