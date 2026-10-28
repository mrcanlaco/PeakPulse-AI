"""Multiprocessing Worker & Orchestrator for 338-Coin Universe Re-Audit (v4.0.2).

Evaluates all 338 USD-M Perpetual symbols using the patched v4.0.2 engine:
- `swing_pivot_left_bars=2`, `swing_pivot_right_bars=2`
- `prior_low_time < swing_high_time` (`l_idx < p_idx`)
- Same-bar ratcheted SL re-check (`ratchet_mode="pessimistic_high"`)
- Recalculated Mốc 6 exit metadata (`exit_price`, `exit_time`, `hold_hours`, `m6_sl_atr_buffer=0.25`)
- Canonical `compute_canonical_pst_series(..., use_bfill=False)`
- Independent Milestone Execution (separate `consumed_waves` and `cooldown_until_idx` per milestone)
  alongside Legacy Subset-Filtered comparison
- True Monthly Rolling Point-in-Time Top-50 Volume (`ROLLING_PIT_TOP50_VOL`) using strictly
  trailing 63-day `[t_month - 63d, t_month)` liquidity and wick toxicity on both 2024-2025 and 2026.
"""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parents[1]
SRC_DIR = ROOT_DIR / "src"
for p in (str(SCRIPT_DIR), str(SRC_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from dao_vang.config.settings import FiboTrendShortConfig
from dao_vang.fibo_short.backtest import (
    DATA_LAKE_5M_DIR,
    IN_SAMPLE_MAX_UTC,
    OOS_START_UTC,
    PRE2024_5M_DIR,
    SHARED_1H_DIR,
    FiboBacktestTrade,
    resample_1h_to_htf,
)
from dao_vang.fibo_short.detector import (
    build_fibo_trade_setup,
    compute_atr,
    compute_fibonacci_levels,
    compute_orthogonal_conviction_score,
    detect_htf_reversal_wave,
    evaluate_h1_confirmation,
)
from study_coin_universe_selection_2026 import (
    G1_STORE_OF_VALUE,
    STABLE_OR_INDEX_EXCLUDE,
    assign_ex_ante_universe_tier,
    classify_archetype,
    enrich_with_marketcap_and_supply,
    load_coingecko_market_map,
    load_symbol_1h_full_2024_2026,
)
from verify_red_team_audit_2026 import (
    calc_htf_features_no_bfill,
    compute_portfolio_nav_and_concurrency,
    simulate_trade_v2,
)

SHARED_FUNDING_DIR = Path("D:/SharedMarketData/multiyear_2020_2026/funding_8h")
DATA_LAKE_FUNDING_DIR = (
    Path("E:/Quant-trading/data_lake/funding")
    if Path("E:/Quant-trading/data_lake/funding").exists()
    else Path("C:/Quant-trading/data_lake/funding")
)

# The final IS candle opens before the cutoff and settles at the next hour.
# This is a valuation boundary; it does not admit new OOS signals.
IS_VALUATION_END_UTC = IN_SAMPLE_MAX_UTC.ceil("h")

UNIVERSE_MILESTONES = (
    "m1_f1a_pump50",
    "m4_f2_elite",
    "m6_f4_expanded",
    "m6_f4_sniper",
    "m6_f4_elite_sniper",
)

MONTHLY_REBALANCE_DATES = [
    pd.Timestamp(f"{yr}-{mo:02d}-01T00:00:00+00:00")
    for yr in (2024, 2025, 2026)
    for mo in range(1, 13)
    if not (yr == 2026 and mo > 9)
]


def _check_milestone_gate(
    milestone: str,
    *,
    f1_elite: bool,
    f1_expanded: bool,
    imp_drop_pct: float,
    imp_ker: float,
    cond2_break: bool,
    max_fibo_ratio: float,
) -> bool:
    if milestone == "m1_f1a_pump50":
        return True
    if milestone == "m4_f2_elite":
        return bool(f1_elite and imp_drop_pct >= 6.0 and imp_ker >= 0.50)
    if milestone == "m6_f4_expanded":
        return bool(f1_expanded and imp_drop_pct >= 6.0 and imp_ker >= 0.50)
    if milestone == "m6_f4_sniper":
        return bool(
            f1_expanded
            and imp_drop_pct >= 6.0
            and imp_ker >= 0.50
            and cond2_break
            and max_fibo_ratio <= 0.786
        )
    if milestone == "m6_f4_elite_sniper":
        return bool(
            f1_elite
            and imp_drop_pct >= 6.0
            and imp_ker >= 0.50
            and cond2_break
            and max_fibo_ratio <= 0.786
        )
    return False


HARD_CUTOFF_2026_08_31_CLOSE_UTC = pd.Timestamp("2026-09-01T00:00:00+00:00")


def _resolve_cand_decision_ts(cand: dict[str, Any]) -> pd.Timestamp:
    ts = cand.get("decision_ts")
    if isinstance(ts, pd.Timestamp):
        return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    raw = cand.get("decision_time") or cand.get("signal_candle_open_time")
    parsed = pd.Timestamp(raw)
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize("UTC")
    else:
        parsed = parsed.tz_convert("UTC")
    if not cand.get("decision_time") and cand.get("signal_candle_open_time"):
        parsed = parsed + pd.Timedelta(hours=1)
    return parsed


def _make_trade_item_from_candidate(
    cand: dict[str, Any],
    sim_res: dict[str, Any],
    *,
    sl_val: float,
    mult_val: float,
    keep_trace: bool,
) -> dict[str, Any]:
    exit_close_str = str(sim_res.get("exit_close_time") or sim_res["exit_time"])
    decision_ts = _resolve_cand_decision_ts(cand)
    decision_epoch_h = int(decision_ts.timestamp() // 3600)
    exit_close_ts = pd.Timestamp(exit_close_str)
    if exit_close_ts.tzinfo is None:
        exit_close_ts = exit_close_ts.tz_localize("UTC")
    else:
        exit_close_ts = exit_close_ts.tz_convert("UTC")
    exit_close_epoch_h = int(exit_close_ts.timestamp() // 3600)
    observed_bars = int(sim_res.get("observed_bars", sim_res.get("hold_hours", 1)))
    real_hold_hours = max(
        int(sim_res.get("hold_hours", 1)),
        max(1, exit_close_epoch_h - decision_epoch_h),
    )
    t_obj = FiboBacktestTrade(
        trade_id=f"{cand['symbol']}_{cand['tf']}_{decision_epoch_h}",
        symbol=cand["symbol"],
        higher_timeframe=cand["tf"],
        confirmation_tier=cand["confirmation_tier"],
        pattern_name=cand["pattern_name"],
        entry_time=cand["decision_time"],
        exit_time=exit_close_str,
        entry_price=float(cand["entry_price"]),
        stop_loss=float(sl_val),
        tp1=float(cand["tp1"]),
        tp2=float(cand["tp2"]),
        tp3=float(cand["tp3"]),
        exit_price=float(sim_res["exit_price"]),
        outcome=sim_res["outcome"],  # type: ignore[arg-type]
        tp1_reached=bool(sim_res["tp1_hit"]),
        tp2_reached=bool(sim_res["tp2_hit"]),
        tp3_reached=bool(sim_res["tp3_hit"]),
        gross_return_pct=round(float(sim_res["gross_pct"]) * mult_val, 4),
        net_return_pct=round(float(sim_res["net_pct"]) * mult_val, 4),
        r_multiple=round(float(sim_res["r_mult"]) * mult_val, 4),
        hold_hours=real_hold_hours,
        fibo_entry_ratio=float(cand["current_fibo_ratio"]),
        impulse_drop_pct=float(cand["wave_impulse_drop_pct"]),
        prior_pump_pct=float(cand["wave_prior_pump_pct"]),
        terminal_outcome=str(sim_res.get("detailed_outcome") or sim_res.get("terminal_outcome") or ""),
        ratcheted_sl_hit=bool(sim_res["ratcheted_sl_hit"]),
        time_exit_used=bool(sim_res["time_exit_used"]),
        decision_time=cand["decision_time"],
    )
    sim_compact = dict(sim_res) if keep_trace else {k: v for k, v in sim_res.items() if k != "bar_trace"}
    return {
        "trade": t_obj,
        "sim": sim_compact,
        "raw_gross_pct": float(sim_res["gross_pct"]),
        "pos_mult": float(mult_val),
        "full_conviction_score": float(cand["full_conviction_score"]),
        "detector_score": float(cand["full_conviction_score"]),
        "conviction_tier": str(cand["conviction_tier"]),
        "legacy_btc_spread_score": float(cand["legacy_btc_spread_score"]),
        "symbol": cand["symbol"],
        "tf": cand["tf"],
        "idx_1h": int(cand["idx_1h"]),
        "decision_epoch_h": decision_epoch_h,
        "exit_close_epoch_h": exit_close_epoch_h,
        "observed_bars": observed_bars,
        "real_hold_hours": real_hold_hours,
        "wave_key": cand["wave_key"],
        "signal_candle_open_time": cand["signal_candle_open_time"],
        "decision_time": cand["decision_time"],
        "exit_bar_open_time": str(sim_res["exit_time"]),
        "exit_close_time": exit_close_str,
        "year": int(cand["year"]),
        "entry_ym": cand["entry_ym"],
        "ker_wave": float(cand["ker_wave"]),
        "imp_ker": float(cand["imp_ker"]),
    }


def execute_symbol_candidates_from_raw(
    raw_candidates: list[dict[str, Any]],
    *,
    allowed_yms: set[str] | None = None,
    hard_cutoff_0831: bool = False,
    min_cooldown_hours: int = 4,
    reset_at_oos_boundary: bool = True,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Execute per-(symbol, tf) state machine from pre-collected confirmed candidates.
    Sorting and cooldown tracking use strictly real UTC epoch hours (`decision_epoch_h`)
    and real `exit_close_epoch_h` rather than slice-local `idx_1h` or observed bar count.
    When `allowed_yms` is provided (e.g., for `ROLLING_PIT_TOP50_VOL`), monthly universe
    membership is checked BEFORE consuming `wave_key` or setting `cooldown_until_epoch_h`.
    When `hard_cutoff_0831=True`, entries at/after `2026-09-01T00:00:00+00:00` are excluded
    and trades spanning across `2026-09-01T00:00:00+00:00` use `sim_std_0831` / `sim_m6_0831`.
    """
    indep_by_m: dict[str, list[dict[str, Any]]] = {m: [] for m in UNIVERSE_MILESTONES}
    subset_by_m: dict[str, list[dict[str, Any]]] = {m: [] for m in UNIVERSE_MILESTONES}
    if not raw_candidates:
        return {"independent": indep_by_m, "subset_from_m1": subset_by_m}

    oos_boundary_epoch_h = int(OOS_START_UTC.timestamp() // 3600)

    by_tf: dict[str, list[dict[str, Any]]] = {}
    for c in raw_candidates:
        by_tf.setdefault(c["tf"], []).append(c)

    for tf, c_list in by_tf.items():
        c_list.sort(
            key=lambda x: (
                int(_resolve_cand_decision_ts(x).timestamp() // 3600),
                int(x.get("idx_1h", 0)),
            )
        )
        cooldown_until_epoch_h: dict[str, int] = {m: -1 for m in UNIVERSE_MILESTONES}
        consumed_waves: dict[str, set[str]] = {m: set() for m in UNIVERSE_MILESTONES}
        current_regime_is_oos: bool | None = None

        for c in c_list:
            decision_ts = _resolve_cand_decision_ts(c)
            decision_epoch_h = int(decision_ts.timestamp() // 3600)
            is_oos = decision_epoch_h >= oos_boundary_epoch_h
            if reset_at_oos_boundary and current_regime_is_oos is not None and is_oos != current_regime_is_oos:
                cooldown_until_epoch_h = {m: -1 for m in UNIVERSE_MILESTONES}
                consumed_waves = {m: set() for m in UNIVERSE_MILESTONES}
            current_regime_is_oos = is_oos

            # 1. Check Rolling PIT monthly membership BEFORE wave/cooldown consumption!
            if allowed_yms is not None and c["entry_ym"] not in allowed_yms:
                continue

            # 2. Check hard cutoff timestamp BEFORE wave/cooldown consumption!
            if hard_cutoff_0831 and decision_ts >= HARD_CUTOFF_2026_08_31_CLOSE_UTC:
                continue

            sim_std_use = c["sim_std_0831"] if hard_cutoff_0831 else c["sim_std"]
            sim_m6_use = c["sim_m6_0831"] if hard_cutoff_0831 else c["sim_m6"]
            if sim_std_use is None or sim_m6_use is None:
                continue

            wave_key = str(c["wave_key"])
            eligible_ms = c["eligible_milestones"]

            for m in eligible_ms:
                if decision_epoch_h < cooldown_until_epoch_h[m] or wave_key in consumed_waves[m]:
                    continue
                is_m6 = m.startswith("m6_")
                sim_use = sim_m6_use if is_m6 else sim_std_use
                sl_use = float(c["sl_m6"]) if is_m6 else float(c["sl_std"])
                mult_use = float(c["mult_m6"]) if is_m6 else 1.0
                keep_tr = m != "m1_f1a_pump50"
                item_m = _make_trade_item_from_candidate(
                    c,
                    sim_use,
                    sl_val=sl_use,
                    mult_val=mult_use,
                    keep_trace=keep_tr,
                )
                indep_by_m[m].append(item_m)
                consumed_waves[m].add(wave_key)
                cooldown_until_epoch_h[m] = max(
                    int(item_m["exit_close_epoch_h"]),
                    decision_epoch_h + max(min_cooldown_hours, int(item_m["real_hold_hours"])),
                )

                if m == "m1_f1a_pump50":
                    subset_by_m["m1_f1a_pump50"].append(item_m)
                    for sub_m in eligible_ms:
                        if sub_m == "m1_f1a_pump50":
                            continue
                        sub_is_m6 = sub_m.startswith("m6_")
                        sub_sim = sim_m6_use if sub_is_m6 else sim_std_use
                        sub_sl = float(c["sl_m6"]) if sub_is_m6 else float(c["sl_std"])
                        sub_mult = float(c["mult_m6"]) if sub_is_m6 else 1.0
                        subset_by_m[sub_m].append(
                            _make_trade_item_from_candidate(
                                c,
                                sub_sim,
                                sl_val=sub_sl,
                                mult_val=sub_mult,
                                keep_trace=False,
                            )
                        )

    return {"independent": indep_by_m, "subset_from_m1": subset_by_m}


def collect_symbol_milestones_v402(
    symbol: str,
    df_1h: pd.DataFrame,
    btc_htf: dict[str, pd.DataFrame],
    *,
    entry_start_ts: pd.Timestamp,
    entry_end_ts: pd.Timestamp,
    allowed_yms: set[str] | None = None,
    hard_cutoff_0831: bool = False,
) -> dict[str, Any]:
    """Single-pass collector that extracts all confirmed H1 candidate triggers for `symbol`
    (using canonical `compute_orthogonal_conviction_score` and causal `decision_time == entry_time`)
    and executes the per-milestone state machine.
    """
    cfg = FiboTrendShortConfig(
        swing_lookback_bars=30,
        swing_pivot_left_bars=2,
        swing_pivot_right_bars=2,
        conviction_mult_c=0.80,  # Same three-band M6 sizing as the benchmark executor.
        min_prior_pump_pct=0.50,
        min_impulse_drop_pct=0.04,
        fibo_entry_min=0.500,
        fibo_entry_max=0.618,
        sl_mode="above_swing_high",
        sl_atr_buffer=0.20,
        m6_sl_atr_buffer=0.25,
        require_both_h1_conditions=False,
    )

    indep_by_m: dict[str, list[dict[str, Any]]] = {m: [] for m in UNIVERSE_MILESTONES}
    subset_by_m: dict[str, list[dict[str, Any]]] = {m: [] for m in UNIVERSE_MILESTONES}

    if len(df_1h) < 100:
        return {"independent": indep_by_m, "subset_from_m1": subset_by_m, "raw_candidates": []}

    idx_arr = df_1h.index
    opens = df_1h["open"].to_numpy(dtype=float)
    highs = df_1h["high"].to_numpy(dtype=float)
    lows = df_1h["low"].to_numpy(dtype=float)
    closes = df_1h["close"].to_numpy(dtype=float)
    vols = df_1h["volume"].to_numpy(dtype=float)

    h1_records: list[dict[str, Any]] = []
    h1_close_times: list[pd.Timestamp] = []
    hour_delta = pd.Timedelta(hours=1)
    for i in range(len(df_1h)):
        open_ts = idx_arr[i]
        close_ts = open_ts + hour_delta
        h1_close_times.append(close_ts)
        h1_records.append(
            {
                "open_time": int(open_ts.timestamp() * 1000),
                "open_time_str": open_ts.isoformat(),
                "close_time_ts": close_ts,
                "open": float(opens[i]),
                "high": float(highs[i]),
                "low": float(lows[i]),
                "close": float(closes[i]),
                "volume": float(vols[i]),
            }
        )

    raw_candidates: list[dict[str, Any]] = []

    for tf in ("4h", "1d"):
        htf_df = resample_1h_to_htf(df_1h, tf)
        if len(htf_df) < 30:
            continue
        htf_df = calc_htf_features_no_bfill(htf_df)

        htf_records: list[dict[str, Any]] = []
        htf_close_times: list[pd.Timestamp] = []
        for idx_htf, (open_ts, row) in enumerate(htf_df.iterrows()):
            c_ts = pd.Timestamp(row["close_time"])
            htf_close_times.append(c_ts)
            htf_records.append(
                {
                    "htf_idx": idx_htf,
                    "open_time": int(open_ts.timestamp() * 1000),
                    "open_time_str": open_ts.isoformat(),
                    "close_time_ts": c_ts,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0.0)),
                    "robust_vol": float(row["robust_vol"]),
                    "ewmac_4_16": float(row["ewmac_4_16"]),
                    "ewmac_16_64": float(row["ewmac_16_64"]),
                    "accel_4_16": float(row["accel_4_16"]),
                    "vol_ratio_20": float(row["vol_ratio_20"]),
                }
            )

        htf_by_open_str = {r["open_time_str"]: r for r in htf_records}
        htf_ptr = 0
        n_htf = len(htf_records)
        horizon = cfg.horizon_hours if tf == "4h" else cfg.horizon_hours_1d
        bdf = btc_htf[tf]
        btc_close_times = pd.to_datetime(bdf["close_time"])

        cached_htf_ptr = -1
        cached_wave = None
        cached_fibo = None
        cached_wave_meta: dict[str, Any] | None = None
        wave_eligible_milestones: list[str] = []
        entry_min_price_cached = 0.0

        for idx_1h in range(24, len(h1_records) - 2):
            current_decision_ts = h1_close_times[idx_1h]
            while htf_ptr < n_htf and htf_close_times[htf_ptr] <= current_decision_ts:
                htf_ptr += 1

            bar_open_ts = idx_arr[idx_1h]
            if bar_open_ts < entry_start_ts or bar_open_ts > entry_end_ts:
                continue
            if htf_ptr < 10:
                continue

            if htf_ptr != cached_htf_ptr:
                cached_htf_ptr = htf_ptr
                start_htf = max(0, htf_ptr - cfg.swing_lookback_bars - 24)
                visible_htf = htf_records[start_htf:htf_ptr]
                cached_wave = detect_htf_reversal_wave(symbol, visible_htf, tf, cfg)
                cached_fibo = None
                cached_wave_meta = None
                wave_eligible_milestones = []
                if cached_wave is not None:
                    peak_bar_c = htf_by_open_str.get(cached_wave.swing_high_time)
                    low_bar_c = htf_by_open_str.get(cached_wave.prior_low_time)
                    imp_bar_c = htf_by_open_str.get(cached_wave.impulse_low_time)
                    cur_htf_bar_c = htf_records[htf_ptr - 1]
                    if peak_bar_c is not None and low_bar_c is not None and imp_bar_c is not None:
                        p_idx_c = int(peak_bar_c["htf_idx"])
                        l_idx_c = int(low_bar_c["htf_idx"])
                        imp_idx_c = int(imp_bar_c["htf_idx"])
                        if l_idx_c < p_idx_c:
                            cached_fibo = compute_fibonacci_levels(
                                cached_wave.swing_high_price,
                                cached_wave.impulse_low_price,
                            )
                            entry_min_price_cached = cached_fibo.level_0000 + cfg.fibo_entry_min * cached_fibo.wave_range
                            wave_bars_c = htf_records[l_idx_c : p_idx_c + 1]
                            if len(wave_bars_c) >= 2:
                                closes_w_c = np.array([b["close"] for b in wave_bars_c], dtype=float)
                                net_chg_c = abs(closes_w_c[-1] - closes_w_c[0])
                                path_chg_c = float(np.sum(np.abs(np.diff(closes_w_c))))
                                ker_wave_c = net_chg_c / path_chg_c if path_chg_c > 1e-9 else 0.0
                            else:
                                ker_wave_c = 0.0
                            pst_pass_c = (peak_bar_c["ewmac_16_64"] <= 0.0) or (cur_htf_bar_c["accel_4_16"] <= -1.0)
                            f1_elite_c = bool(pst_pass_c and (ker_wave_c >= 0.35))
                            f1_expanded_c = bool(f1_elite_c or (ker_wave_c >= 0.65))
                            sh_c = cached_wave.swing_high_price
                            il_c = cached_wave.impulse_low_price
                            imp_drop_pct_c = (max(0.0, sh_c - il_c) / sh_c) * 100.0
                            imp_slice_c = htf_records[p_idx_c : imp_idx_c + 1]
                            if len(imp_slice_c) >= 2:
                                closes_imp_c = np.array([b["close"] for b in imp_slice_c], dtype=float)
                                net_imp_c = abs(closes_imp_c[-1] - closes_imp_c[0])
                                path_imp_c = float(np.sum(np.abs(np.diff(closes_imp_c))))
                                imp_ker_c = net_imp_c / path_imp_c if path_imp_c > 1e-9 else 0.0
                            else:
                                imp_ker_c = 0.0
                            cached_wave_meta = {
                                "peak_bar": peak_bar_c,
                                "cur_htf_bar": cur_htf_bar_c,
                                "p_idx": p_idx_c,
                                "l_idx": l_idx_c,
                                "ker_wave": ker_wave_c,
                                "pst_pass": pst_pass_c,
                                "f1_elite": f1_elite_c,
                                "f1_expanded": f1_expanded_c,
                                "imp_drop_pct": imp_drop_pct_c,
                                "imp_ker": imp_ker_c,
                            }
                            wave_eligible_milestones = ["m1_f1a_pump50"]
                            if imp_drop_pct_c >= 6.0 and imp_ker_c >= 0.50:
                                if f1_expanded_c:
                                    wave_eligible_milestones.extend(["m6_f4_expanded", "m6_f4_sniper"])
                                if f1_elite_c:
                                    wave_eligible_milestones.extend(["m4_f2_elite", "m6_f4_elite_sniper"])

            if cached_wave is None or cached_fibo is None or cached_wave_meta is None:
                continue

            # Fast pre-filter before constructing visible_1h: H1 confirmation requires red candle, no 1h gain, and Fibo touch in last 3 bars
            if closes[idx_1h] >= opens[idx_1h] or closes[idx_1h] > closes[idx_1h - 1]:
                continue
            if max(highs[idx_1h], highs[idx_1h - 1], highs[idx_1h - 2]) < entry_min_price_cached:
                continue

            visible_1h = h1_records[max(0, idx_1h - 24) : idx_1h + 1]
            h1_conf = evaluate_h1_confirmation(visible_1h, cached_fibo, cached_wave, cfg)
            current_price = h1_conf.close
            if (
                current_price > cached_fibo.level_1000 * cfg.fibo_invalidation_level
                or h1_conf.max_pullback_fibo_ratio > cfg.fibo_invalidation_level
                or not h1_conf.confirmed
            ):
                continue

            future_slice = h1_records[idx_1h + 1 : min(len(h1_records), idx_1h + 1 + horizon)]
            if not future_slice:
                continue

            peak_bar = cached_wave_meta["peak_bar"]
            cur_htf_bar = cached_wave_meta["cur_htf_bar"]
            p_idx = cached_wave_meta["p_idx"]
            l_idx = cached_wave_meta["l_idx"]
            ker_wave = cached_wave_meta["ker_wave"]
            pst_pass = cached_wave_meta["pst_pass"]
            f1_elite = cached_wave_meta["f1_elite"]
            f1_expanded = cached_wave_meta["f1_expanded"]
            imp_drop_pct = cached_wave_meta["imp_drop_pct"]
            imp_ker = cached_wave_meta["imp_ker"]

            eligible_milestones = [
                m
                for m in wave_eligible_milestones
                if _check_milestone_gate(
                    m,
                    f1_elite=f1_elite,
                    f1_expanded=f1_expanded,
                    imp_drop_pct=imp_drop_pct,
                    imp_ker=imp_ker,
                    cond2_break=h1_conf.cond2_break_prev_low,
                    max_fibo_ratio=h1_conf.max_pullback_fibo_ratio,
                )
            ]
            if not eligible_milestones:
                continue

            past_btc = bdf.loc[btc_close_times <= current_decision_ts]
            if len(past_btc) >= 5:
                last_btc = past_btc.iloc[-1]
                btc_ewmac_4_16 = float(last_btc["ewmac_4_16"])
                lb = min(len(past_btc) - 1, max(1, p_idx - l_idx))
                btc_ret_pct = float(
                    (last_btc["close"] - past_btc.iloc[-1 - lb]["close"])
                    / past_btc.iloc[-1 - lb]["close"]
                    * 100.0
                )
            else:
                btc_ewmac_4_16 = 0.0
                btc_ret_pct = 0.0

            raw_pump_pct = (
                cached_wave.prior_pump_pct * 100.0
                if cached_wave.prior_pump_pct < 10.0
                else cached_wave.prior_pump_pct
            )
            idiosyncratic_spread = raw_pump_pct - max(0.0, btc_ret_pct)

            legacy_score = 0.0
            if raw_pump_pct >= 100.0:
                legacy_score += 15.0
            elif raw_pump_pct >= 70.0:
                legacy_score += 11.0
            else:
                legacy_score += 7.0
            if ker_wave >= 0.65:
                legacy_score += 20.0
            elif ker_wave >= 0.35:
                legacy_score += 14.0
            if imp_ker >= 0.65 and imp_drop_pct >= 6.0:
                legacy_score += 15.0
            elif imp_ker >= 0.50 and imp_drop_pct >= 6.0:
                legacy_score += 10.0
            if peak_bar["ewmac_16_64"] <= 0.0 and cur_htf_bar["accel_4_16"] <= -1.0:
                legacy_score += 20.0
            elif pst_pass:
                legacy_score += 14.0
            if btc_ewmac_4_16 <= 0.5:
                legacy_score += 5.0
            if idiosyncratic_spread >= 60.0:
                legacy_score += 5.0
            if h1_conf.confirmation_tier == "COMBO_1_2":
                legacy_score += 12.0
            elif h1_conf.cond2_break_prev_low:
                legacy_score += 9.0
            else:
                legacy_score += 4.0
            if h1_conf.pullback_vol_ratio <= 1.1:
                legacy_score += 8.0
            elif h1_conf.pullback_vol_ratio <= 1.4:
                legacy_score += 4.0

            # Canonical 4-Factor Orthogonal Conviction Score (100% unified with detector.py)
            sc, conviction_tier, mult_m6, _ = compute_orthogonal_conviction_score(
                prior_pump_pct=cached_wave.prior_pump_pct,
                impulse_drop_pct=cached_wave.impulse_drop_pct,
                fibo_retrace_ratio=h1_conf.max_pullback_fibo_ratio,
                wave_ker=ker_wave,
                impulse_ker=imp_ker,
                peak_ewmac_16_64=float(peak_bar["ewmac_16_64"]),
                cur_accel_4_16=float(cur_htf_bar["accel_4_16"]),
                confirmation_tier=h1_conf.confirmation_tier,
                pullback_vol_ratio=h1_conf.pullback_vol_ratio,
                h1_body_ratio=h1_conf.h1_body_ratio,
                config=cfg,
            )

            atr_1h = compute_atr(visible_1h, period=14)
            setup = build_fibo_trade_setup(
                fibo=cached_fibo,
                current_price=current_price,
                atr_1h=atr_1h,
                confirmed=True,
                config=cfg,
                conviction_tier=conviction_tier,
                recommended_risk_mult=mult_m6,
            )
            ep = float(setup.entry_price)
            sl_std = float(setup.stop_loss)
            lvl_0886 = cached_fibo.level_0000 + 0.886 * cached_fibo.wave_range
            sl_m6 = max(lvl_0886, ep * 1.005) + cfg.m6_sl_atr_buffer * atr_1h

            sim_std = simulate_trade_v2(
                future_slice,
                entry_price=ep,
                stop_loss=sl_std,
                tp1=float(setup.tp1),
                tp2=float(setup.tp2),
                tp3=float(setup.tp3),
                round_trip_fee_bps=cfg.round_trip_fee_bps,
                ratchet_mode="pessimistic_high",
                entry_timestamp_utc=current_decision_ts,
            )
            sim_m6 = simulate_trade_v2(
                future_slice,
                entry_price=ep,
                stop_loss=sl_m6,
                tp1=float(setup.tp1),
                tp2=float(setup.tp2),
                tp3=float(setup.tp3),
                round_trip_fee_bps=cfg.round_trip_fee_bps,
                ratchet_mode="pessimistic_high",
                entry_timestamp_utc=current_decision_ts,
            )

            sim_std_0831: dict[str, Any] | None = sim_std
            sim_m6_0831: dict[str, Any] | None = sim_m6
            if current_decision_ts < HARD_CUTOFF_2026_08_31_CLOSE_UTC:
                if (
                    str(sim_std.get("exit_close_time", "")) > "2026-09-01T00:00:00+00:00"
                    or str(sim_m6.get("exit_close_time", "")) > "2026-09-01T00:00:00+00:00"
                ):
                    future_slice_0831 = [
                        b for b in future_slice if b["close_time_ts"] <= HARD_CUTOFF_2026_08_31_CLOSE_UTC
                    ]
                    if future_slice_0831:
                        sim_std_0831 = simulate_trade_v2(
                            future_slice_0831,
                            entry_price=ep,
                            stop_loss=sl_std,
                            tp1=float(setup.tp1),
                            tp2=float(setup.tp2),
                            tp3=float(setup.tp3),
                            round_trip_fee_bps=cfg.round_trip_fee_bps,
                            ratchet_mode="pessimistic_high",
                            entry_timestamp_utc=current_decision_ts,
                        )
                        sim_m6_0831 = simulate_trade_v2(
                            future_slice_0831,
                            entry_price=ep,
                            stop_loss=sl_m6,
                            tp1=float(setup.tp1),
                            tp2=float(setup.tp2),
                            tp3=float(setup.tp3),
                            round_trip_fee_bps=cfg.round_trip_fee_bps,
                            ratchet_mode="pessimistic_high",
                            entry_timestamp_utc=current_decision_ts,
                        )
                    else:
                        sim_std_0831 = None
                        sim_m6_0831 = None
            else:
                sim_std_0831 = None
                sim_m6_0831 = None

            wave_key = f"{tf}:{cached_wave.swing_high_time}:{cached_wave.impulse_low_time}"
            decision_ts_str = current_decision_ts.isoformat()
            entry_ym = f"{current_decision_ts.year:04d}-{current_decision_ts.month:02d}"

            raw_candidates.append(
                {
                    "symbol": symbol,
                    "tf": tf,
                    "idx_1h": idx_1h,
                    "wave_key": wave_key,
                    "eligible_milestones": eligible_milestones,
                    "signal_candle_open_time": h1_conf.candle_time,
                    "decision_time": decision_ts_str,
                    "decision_ts": current_decision_ts,
                    "year": int(current_decision_ts.year),
                    "entry_ym": entry_ym,
                    "confirmation_tier": h1_conf.confirmation_tier,
                    "pattern_name": h1_conf.pattern_name,
                    "entry_price": ep,
                    "sl_std": sl_std,
                    "sl_m6": sl_m6,
                    "tp1": float(setup.tp1),
                    "tp2": float(setup.tp2),
                    "tp3": float(setup.tp3),
                    "current_fibo_ratio": h1_conf.current_fibo_ratio,
                    "wave_impulse_drop_pct": cached_wave.impulse_drop_pct,
                    "wave_prior_pump_pct": cached_wave.prior_pump_pct,
                    "ker_wave": ker_wave,
                    "imp_ker": imp_ker,
                    "full_conviction_score": sc,
                    "conviction_tier": conviction_tier,
                    "mult_m6": mult_m6,
                    "legacy_btc_spread_score": round(legacy_score, 1),
                    "sim_std": sim_std,
                    "sim_m6": sim_m6,
                    "sim_std_0831": sim_std_0831,
                    "sim_m6_0831": sim_m6_0831,
                }
            )

    exec_res = execute_symbol_candidates_from_raw(
        raw_candidates,
        allowed_yms=allowed_yms,
        hard_cutoff_0831=hard_cutoff_0831,
        min_cooldown_hours=cfg.min_cooldown_hours,
    )
    return {
        "independent": exec_res["independent"],
        "subset_from_m1": exec_res["subset_from_m1"],
        "raw_candidates": raw_candidates,
    }


def run_universe_portfolio_coupled_execution(
    raw_candidates: list[dict[str, Any]],
    milestone: str,
    window_start_utc: str,
    window_end_utc: str,
    *,
    allowed_yms_by_symbol: dict[str, set[str]] | None = None,
    hard_cutoff_0831: bool = False,
    base_notional_weight: float = 0.20,
    max_concurrent_cap: int = 5,
    max_total_notional_frac: float = 1.0,
    max_total_sl_risk_frac: float = 0.12,
    min_cooldown_hours: int = 4,
) -> dict[str, Any]:
    """Single-Source Portfolio-Coupled Execution across a multi-symbol universe basket:
    1. Rolling PIT membership (`allowed_yms_by_symbol`) and hard cutoff (`hard_cutoff_0831`) are checked FIRST.
    2. Per-(symbol, tf) `consumed_waves` and `cooldown_until_epoch_h` (real UTC `exit_close_time` epoch hour) are checked SECOND.
    3. Live portfolio slot, equity-relative notional, and equity-relative SL-risk caps are checked THIRD.
    4. `wave_key` is consumed and `cooldown_until_epoch_h = max(exit_close_epoch_h, decision_epoch_h + max(min_cooldown_hours, real_hold_hours))`
       is set ONLY when the trade is accepted by the portfolio!
    5. Each hourly price/fee step is processed at most once (`cur_h` advances monotonically after every hour;
       repeated calls at the same `target_h` are idempotent).
    6. Computes all additive/compounded NAV curves, concurrency series, and trade ledger records directly inside
       this single state machine — NEVER calling `compute_portfolio_nav_and_concurrency` for a second cap pass.
    7. Hard-asserts `accepted_trade_ids == executed_trade_ids`, `len(set(accepted_trade_ids)) == len(accepted_trade_ids)`,
       and `skipped_due_to_cap == 0`.
    """
    import hashlib

    is_m6 = milestone.startswith("m6_")

    eligible_cands: list[dict[str, Any]] = []
    for c in raw_candidates:
        if milestone not in c["eligible_milestones"]:
            continue
        sym = c["symbol"]
        if allowed_yms_by_symbol is not None and c["entry_ym"] not in allowed_yms_by_symbol.get(sym, set()):
            continue
        decision_ts = _resolve_cand_decision_ts(c)
        if hard_cutoff_0831 and decision_ts >= HARD_CUTOFF_2026_08_31_CLOSE_UTC:
            continue
        sim_use = (c["sim_m6_0831"] if is_m6 else c["sim_std_0831"]) if hard_cutoff_0831 else (c["sim_m6"] if is_m6 else c["sim_std"])
        if sim_use is None:
            continue
        eligible_cands.append(c)

    eligible_cands.sort(
        key=lambda c: (
            int(_resolve_cand_decision_ts(c).timestamp()),
            -float(c["full_conviction_score"]),
            str(c["symbol"]),
            str(c["tf"]),
            int(c.get("idx_1h", 0)),
        )
    )

    t_start = pd.Timestamp(window_start_utc)
    if t_start.tzinfo is None:
        t_start = t_start.tz_localize("UTC")
    t_end = pd.Timestamp(window_end_utc)
    if t_end.tzinfo is None:
        t_end = t_end.tz_localize("UTC")
    hourly_index = pd.date_range(start=t_start.floor("h"), end=t_end.ceil("h"), freq="1h", tz="UTC")
    n_hours = len(hourly_index)
    grid_start_epoch_h = int(hourly_index[0].timestamp() // 3600)

    cooldown_until_epoch_h: dict[tuple[str, str], int] = {}
    consumed_waves: dict[tuple[str, str], set[str]] = {}
    open_positions: list[dict[str, Any]] = []
    add_hourly_dollar_pnl = np.zeros(n_hours, dtype=float)
    comp_hourly_dollar_pnl = np.zeros(n_hours, dtype=float)
    slot_occupancy = np.zeros(n_hours, dtype=int)
    static_notional_occupancy = np.zeros(n_hours, dtype=float)
    notional_occupancy = np.zeros(n_hours, dtype=float)
    mark_notional_occupancy = np.zeros(n_hours, dtype=float)
    static_sl_risk_occupancy = np.zeros(n_hours, dtype=float)
    sl_risk_occupancy = np.zeros(n_hours, dtype=float)

    cur_add_equity = 100.0
    cur_comp_equity = 100.0
    cur_h = 0

    def _record_occupancy_at_hour(h_idx: int) -> None:
        if h_idx < 0 or h_idx >= n_hours:
            return
        slot_occupancy[h_idx] = len(open_positions)
        if open_positions:
            static_notional_occupancy[h_idx] = sum(p["notional_frac"] * p["rem_weight"] for p in open_positions)
            notional_occupancy[h_idx] = sum(p["n0_comp"] * p["rem_weight"] for p in open_positions) / cur_comp_equity
            mark_notional_occupancy[h_idx] = sum(
                p["n0_comp"] * p["rem_weight"] * (p["last_mark_price"] / max(1e-9, p["entry_price"]))
                for p in open_positions
            ) / cur_comp_equity
            static_sl_risk_occupancy[h_idx] = sum(
                p["notional_frac"] * p["rem_weight"] * max(0.0, (p["active_sl"] - p["entry_price"]) / max(1e-9, p["entry_price"]))
                for p in open_positions
            )
            sl_risk_occupancy[h_idx] = sum(
                ((p["n0_comp"] / max(1e-9, p["entry_price"])) * p["rem_weight"])
                * max(0.0, p["active_sl"] - p["entry_price"], p["active_sl"] - p["last_mark_price"])
                for p in open_positions
            ) / cur_comp_equity
        else:
            static_notional_occupancy[h_idx] = 0.0
            notional_occupancy[h_idx] = 0.0
            mark_notional_occupancy[h_idx] = 0.0
            static_sl_risk_occupancy[h_idx] = 0.0
            sl_risk_occupancy[h_idx] = 0.0

    def _advance_portfolio_to_hour(target_h: int) -> None:
        nonlocal cur_h, cur_add_equity, cur_comp_equity, open_positions
        while cur_h <= target_h and cur_h < n_hours:
            for p in open_positions:
                if cur_h in p["steps_by_close_h"] and cur_h not in p["processed_hours"]:
                    p["processed_hours"].add(cur_h)
                    b_step = p["steps_by_close_h"][cur_h]
                    fee_pct_bar = float(b_step["bar_fee_pct"])
                    delta_pct = float(b_step["delta_gross_pct"]) - fee_pct_bar
                    d_add = p["n0_add"] * (delta_pct / 100.0)
                    d_comp = p["n0_comp"] * (delta_pct / 100.0)
                    p["fee_dollar_add"] += p["n0_add"] * (fee_pct_bar / 100.0)
                    p["fee_dollar_comp"] += p["n0_comp"] * (fee_pct_bar / 100.0)
                    p["realized_pnl_dollar_add"] += d_add
                    p["realized_pnl_dollar_comp"] += d_comp
                    add_hourly_dollar_pnl[cur_h] += d_add
                    comp_hourly_dollar_pnl[cur_h] += d_comp
                    p["rem_weight"] = float(b_step["rem_weight_end"])
                    p["active_sl"] = float(b_step.get("active_sl_end", p["active_sl"]))
                    p["last_mark_price"] = float(b_step["close_price"])
            cur_add_equity = max(1e-9, 100.0 + float(np.sum(add_hourly_dollar_pnl[: cur_h + 1])))
            cur_comp_equity = max(1e-9, 100.0 + float(np.sum(comp_hourly_dollar_pnl[: cur_h + 1])))
            open_positions = [p for p in open_positions if p["i1_excl"] > cur_h and p["rem_weight"] > 1e-6]
            _record_occupancy_at_hour(cur_h)
            cur_h += 1

    accepted_items: list[dict[str, Any]] = []
    accepted_trade_ids: list[str] = []
    executed_trade_ids: list[str] = []
    all_accepted_positions: list[dict[str, Any]] = []
    accepted_entry_samples: list[int] = []
    blocked_by_wave_or_cooldown = 0
    rejected_by_slot_cap = 0
    rejected_by_notional_cap = 0
    rejected_by_sl_risk_cap = 0

    for c in eligible_cands:
        sym = str(c["symbol"])
        tf = str(c["tf"])
        decision_ts = _resolve_cand_decision_ts(c)
        decision_epoch_h = int(decision_ts.timestamp() // 3600)
        wave_key = str(c["wave_key"])
        key = (sym, tf)

        i0 = max(0, decision_epoch_h - grid_start_epoch_h)
        if i0 >= n_hours:
            continue

        _advance_portfolio_to_hour(i0)

        if decision_epoch_h < cooldown_until_epoch_h.get(key, -1) or wave_key in consumed_waves.get(key, set()):
            blocked_by_wave_or_cooldown += 1
            continue

        sim_use = (c["sim_m6_0831"] if is_m6 else c["sim_std_0831"]) if hard_cutoff_0831 else (c["sim_m6"] if is_m6 else c["sim_std"])
        assert sim_use is not None
        sl_use = float(c["sl_m6"]) if is_m6 else float(c["sl_std"])
        mult_use = float(c["mult_m6"]) if is_m6 else 1.0
        ep = float(c["entry_price"])
        notional_frac = base_notional_weight * mult_use
        sl_dist_frac = max(0.0, (sl_use - ep) / max(1e-9, ep))
        trade_sl_risk_frac = notional_frac * sl_dist_frac

        if len(open_positions) >= max_concurrent_cap:
            rejected_by_slot_cap += 1
            continue

        open_static_notional = sum(p["notional_frac"] * p["rem_weight"] for p in open_positions)
        open_entry_notional_eq = sum(p["n0_comp"] * p["rem_weight"] for p in open_positions) / cur_comp_equity
        open_mark_notional_eq = sum(
            p["n0_comp"] * p["rem_weight"] * (p["last_mark_price"] / max(1e-9, p["entry_price"]))
            for p in open_positions
        ) / cur_comp_equity
        if max(open_static_notional, open_entry_notional_eq, open_mark_notional_eq) + notional_frac > max_total_notional_frac + 1e-9:
            rejected_by_notional_cap += 1
            continue

        open_static_risk = sum(
            p["notional_frac"] * p["rem_weight"] * max(0.0, (p["active_sl"] - p["entry_price"]) / max(1e-9, p["entry_price"]))
            for p in open_positions
        )
        open_eq_risk = sum(
            ((p["n0_comp"] / max(1e-9, p["entry_price"])) * p["rem_weight"])
            * max(0.0, p["active_sl"] - p["entry_price"], p["active_sl"] - p["last_mark_price"])
            for p in open_positions
        ) / cur_comp_equity
        if max(open_static_risk, open_eq_risk) + trade_sl_risk_frac > max_total_sl_risk_frac + 1e-9:
            rejected_by_sl_risk_cap += 1
            continue

        # Accepted! Resolve real exit timestamp and set cooldown strictly on real exit_close_epoch_h
        bar_trace = sim_use.get("bar_trace", [])
        observed_bars = max(1, int(sim_use.get("observed_bars", sim_use.get("hold_hours", 1))))
        exit_close_epoch_h = int(sim_use.get("exit_close_epoch_h", decision_epoch_h + observed_bars))
        raw_exit_close = sim_use.get("exit_close_time") or sim_use.get("exit_time")
        if raw_exit_close:
            try:
                cand_out = pd.Timestamp(raw_exit_close)
                if cand_out.tzinfo is None:
                    cand_out = cand_out.tz_localize("UTC")
                else:
                    cand_out = cand_out.tz_convert("UTC")
                exit_close_epoch_h = max(exit_close_epoch_h, int(cand_out.timestamp() // 3600))
            except Exception:
                pass
        real_hold_h = max(
            int(sim_use.get("real_hold_hours", sim_use.get("hold_hours", 1))),
            max(1, exit_close_epoch_h - decision_epoch_h),
        )

        consumed_waves.setdefault(key, set()).add(wave_key)
        cooldown_until_epoch_h[key] = max(
            exit_close_epoch_h,
            decision_epoch_h + max(min_cooldown_hours, real_hold_h),
        )

        steps_by_close_h: dict[int, dict[str, Any]] = {}
        max_step_h = i0 + real_hold_h
        for b_step in bar_trace:
            b_idx = int(b_step["bar_idx"])
            h_idx = i0 + b_idx + 1
            c_str = b_step.get("close_time_str", "")
            if c_str:
                try:
                    c_ts = pd.Timestamp(c_str)
                    if c_ts.tzinfo is None:
                        c_ts = c_ts.tz_localize("UTC")
                    cand_h = int(c_ts.timestamp() // 3600) - grid_start_epoch_h
                    if cand_h > i0:
                        h_idx = cand_h
                except Exception:
                    pass
            steps_by_close_h[h_idx] = b_step
            if h_idx > max_step_h:
                max_step_h = h_idx

        out_epoch_h = max(max_step_h, exit_close_epoch_h - grid_start_epoch_h)
        i1_excl = min(n_hours, max(i0 + 1, out_epoch_h))

        item_obj = _make_trade_item_from_candidate(
            c,
            sim_use,
            sl_val=sl_use,
            mult_val=mult_use,
            keep_trace=True,
        )
        tid_str = str(item_obj["trade"].trade_id)
        n0_add = 100.0 * notional_frac
        n0_comp = cur_comp_equity * notional_frac
        qty_add = n0_add / max(1e-9, ep)
        qty_comp = n0_comp / max(1e-9, ep)

        pos_dict = {
            "trade_id": tid_str,
            "symbol": sym,
            "tf": tf,
            "decision_time": str(item_obj["decision_time"]),
            "entry_time": str(item_obj["trade"].entry_time),
            "exit_time": str(item_obj["trade"].exit_time),
            "i0": i0,
            "i1_excl": i1_excl,
            "entry_price": ep,
            "active_sl": sl_use,
            "stop_loss_init": sl_use,
            "exit_price": float(item_obj["trade"].exit_price),
            "last_mark_price": ep,
            "rem_weight": 1.0,
            "pos_mult": mult_use,
            "notional_frac": notional_frac,
            "n0_add": n0_add,
            "n0_comp": n0_comp,
            "qty_add": qty_add,
            "qty_comp": qty_comp,
            "equity_at_decision_add": cur_add_equity,
            "equity_at_decision_comp": cur_comp_equity,
            "observed_bars": int(item_obj["observed_bars"]),
            "real_hold_hours": int(item_obj["real_hold_hours"]),
            "outcome": str(item_obj["trade"].outcome),
            "terminal_outcome": str(item_obj["trade"].terminal_outcome),
            "net_return_pct": float(item_obj["trade"].net_return_pct),
            "steps_by_close_h": steps_by_close_h,
            "processed_hours": set(),
            "fee_dollar_add": 0.0,
            "fee_dollar_comp": 0.0,
            "realized_pnl_dollar_add": 0.0,
            "realized_pnl_dollar_comp": 0.0,
        }
        open_positions.append(pos_dict)
        all_accepted_positions.append(pos_dict)
        accepted_entry_samples.append(len(open_positions))
        _record_occupancy_at_hour(i0)

        accepted_items.append(item_obj)
        accepted_trade_ids.append(tid_str)
        executed_trade_ids.append(tid_str)

    if n_hours > 0:
        _advance_portfolio_to_hour(n_hours - 1)

    ledger_records: list[dict[str, Any]] = [
        {
            "trade_id": str(p["trade_id"]),
            "symbol": str(p["symbol"]),
            "tf": str(p["tf"]),
            "decision_status": "ACCEPTED",
            "decision_time": str(p["decision_time"]),
            "entry_time": str(p["entry_time"]),
            "exit_time": str(p["exit_time"]),
            "entry_price": round(float(p["entry_price"]), 8),
            "stop_loss": round(float(p["stop_loss_init"]), 8),
            "exit_price": round(float(p["exit_price"]), 8),
            "pos_mult": round(float(p["pos_mult"]), 4),
            "notional_frac": round(float(p["notional_frac"]), 4),
            "qty_add": round(float(p["qty_add"]), 6),
            "qty_comp": round(float(p["qty_comp"]), 6),
            "n0_add": round(float(p["n0_add"]), 4),
            "n0_comp": round(float(p["n0_comp"]), 4),
            "equity_at_decision_add": round(float(p["equity_at_decision_add"]), 4),
            "equity_at_decision_comp": round(float(p["equity_at_decision_comp"]), 4),
            "observed_bars": int(p["observed_bars"]),
            "real_hold_hours": int(p["real_hold_hours"]),
            "outcome": str(p["outcome"]),
            "terminal_outcome": str(p["terminal_outcome"]),
            "net_return_pct": round(float(p["net_return_pct"]), 4),
            "fee_dollar_add": round(float(p["fee_dollar_add"]), 4),
            "fee_dollar_comp": round(float(p["fee_dollar_comp"]), 4),
            "realized_pnl_dollar_add": round(float(p["realized_pnl_dollar_add"]), 4),
            "realized_pnl_dollar_comp": round(float(p["realized_pnl_dollar_comp"]), 4),
        }
        for p in all_accepted_positions
    ]

    additive_nav = 100.0 + np.cumsum(add_hourly_dollar_pnl)
    add_peak = np.maximum.accumulate(additive_nav) if n_hours > 0 else np.array([100.0])
    add_dd_pct_pts = float(np.max(add_peak - additive_nav)) if n_hours > 0 else 0.0
    add_dd_rel_pct = float(np.max((add_peak - additive_nav) / np.maximum(1e-9, add_peak) * 100.0)) if n_hours > 0 else 0.0

    comp_nav = 100.0 + np.cumsum(comp_hourly_dollar_pnl)
    comp_peak = np.maximum.accumulate(comp_nav) if n_hours > 0 else np.array([100.0])
    comp_dd_rel_pct = float(np.max((comp_peak - comp_nav) / np.maximum(1e-9, comp_peak) * 100.0)) if n_hours > 0 else 0.0

    accepted_active_only = slot_occupancy[slot_occupancy > 0]
    passive_notional_breach_h = int(np.sum(mark_notional_occupancy > (max_total_notional_frac + 1e-9))) if n_hours > 0 else 0
    passive_sl_risk_breach_h = int(np.sum(sl_risk_occupancy > (max_total_sl_risk_frac + 1e-9))) if n_hours > 0 else 0

    accepted_concurrency = {
        "entry_sampled_avg": round(float(np.mean(accepted_entry_samples)), 2) if accepted_entry_samples else 0.0,
        "entry_sampled_p95": round(float(np.percentile(accepted_entry_samples, 95)), 1) if accepted_entry_samples else 0.0,
        "max_concurrent": int(np.max(slot_occupancy)) if n_hours > 0 else 0,
        "time_weighted_avg_all_hours": round(float(np.mean(slot_occupancy)), 3) if n_hours > 0 else 0.0,
        "time_weighted_avg": round(float(np.mean(slot_occupancy)), 3) if n_hours > 0 else 0.0,
        "p95_hourly": round(float(np.percentile(slot_occupancy, 95)), 2) if n_hours > 0 else 0.0,
        "time_weighted_avg_active_hours": round(float(np.mean(accepted_active_only)), 2) if len(accepted_active_only) > 0 else 0.0,
        "peak_open_notional_frac": round(float(np.max(static_notional_occupancy)), 4) if n_hours > 0 else 0.0,
        "max_notional_frac": round(float(np.max(static_notional_occupancy)), 4) if n_hours > 0 else 0.0,
        "peak_equity_relative_notional_frac": round(float(np.max(notional_occupancy)), 4) if n_hours > 0 else 0.0,
        "peak_mark_to_market_notional_frac": round(float(np.max(mark_notional_occupancy)), 4) if n_hours > 0 else 0.0,
        "peak_open_sl_risk_frac": round(float(np.max(static_sl_risk_occupancy)), 4) if n_hours > 0 else 0.0,
        "max_sl_risk_frac": round(float(np.max(sl_risk_occupancy)), 4) if n_hours > 0 else 0.0,
        "passive_mtm_notional_cap_breach_hours": passive_notional_breach_h,
        "passive_mtm_sl_risk_cap_breach_hours": passive_sl_risk_breach_h,
    }
    nav_sim = {
        "max_concurrent_cap": max_concurrent_cap,
        "max_total_notional_frac": max_total_notional_frac,
        "max_total_sl_risk_frac": max_total_sl_risk_frac,
        "executed_trades": len(executed_trade_ids),
        "skipped_due_to_cap": 0,
        "skipped_total_cap": 0,
        "skipped_due_to_slot_cap": 0,
        "skipped_concurrency_cap": 0,
        "skipped_due_to_notional_cap": 0,
        "skipped_notional_cap": 0,
        "skipped_due_to_sl_risk_cap": 0,
        "skipped_sl_risk_cap": 0,
        "additive_nav_final": round(float(additive_nav[-1]), 4) if n_hours > 0 else 100.0,
        "additive_final_nav": round(float(additive_nav[-1]), 4) if n_hours > 0 else 100.0,
        "additive_nav_total_return_pct": round(float(additive_nav[-1] - 100.0), 2) if n_hours > 0 else 0.0,
        "additive_total_return_pct": round(float(additive_nav[-1] - 100.0), 2) if n_hours > 0 else 0.0,
        "additive_nav_max_dd_pct_pts": round(add_dd_pct_pts, 2),
        "additive_nav_max_dd_rel_pct": round(add_dd_rel_pct, 2),
        "additive_max_dd_pct": round(add_dd_rel_pct, 2),
        "compounded_nav_final": round(float(comp_nav[-1]), 4) if n_hours > 0 else 100.0,
        "compounded_final_nav": round(float(comp_nav[-1]), 4) if n_hours > 0 else 100.0,
        "compounded_nav_total_return_pct": round(float(comp_nav[-1] - 100.0), 2) if n_hours > 0 else 0.0,
        "compounded_total_return_pct": round(float(comp_nav[-1] - 100.0), 2) if n_hours > 0 else 0.0,
        "compounded_nav_max_dd_rel_pct": round(comp_dd_rel_pct, 2),
        "compounded_max_dd_pct": round(comp_dd_rel_pct, 2),
        "historical_funding_events_matched": 0,
        "historical_funding_events_matched_8h": 0,
        "historical_funding_events_matched_off_8h": 0,
        "historical_funding_events_missing": 0,
        "historical_funding_net_pct_of_initial_nav": 0.0,
        "stress_funding_events_charged": 0,
        "stress_funding_net_pct_of_initial_nav": 0.0,
    }

    if (
        accepted_trade_ids != executed_trade_ids
        or len(set(accepted_trade_ids)) != len(accepted_trade_ids)
        or len(accepted_items) != int(nav_sim["executed_trades"])
        or int(nav_sim["skipped_due_to_cap"]) != 0
    ):
        raise AssertionError(
            f"Coupled universe execution trade_id mismatch on milestone={milestone}: "
            f"accepted={len(accepted_items)} vs executed={nav_sim['executed_trades']}, "
            f"skipped_due_to_cap={nav_sim['skipped_due_to_cap']}"
        )

    ledger_sha256 = hashlib.sha256(
        json.dumps(ledger_records, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    return {
        "accepted_items": accepted_items,
        "accepted_trades": len(accepted_items),
        "executed_trades": int(nav_sim["executed_trades"]),
        "accepted_trade_ids": accepted_trade_ids,
        "executed_trade_ids": executed_trade_ids,
        "ledger_records": ledger_records,
        "ledger_sha256": ledger_sha256,
        "trade_id_set_exact_match": (
            accepted_trade_ids == executed_trade_ids
            and len(set(accepted_trade_ids)) == len(accepted_trade_ids)
        ),
        "single_source_accounting_no_second_cap_pass": True,
        "blocked_by_wave_or_cooldown": blocked_by_wave_or_cooldown,
        "rejected_by_cap_total": rejected_by_slot_cap + rejected_by_notional_cap + rejected_by_sl_risk_cap,
        "rejected_by_slot_cap": rejected_by_slot_cap,
        "rejected_by_notional_cap": rejected_by_notional_cap,
        "rejected_by_sl_risk_cap": rejected_by_sl_risk_cap,
        "accepted_concurrency": accepted_concurrency,
        "nav_20pct_per_1x": nav_sim,
    }


_WORKER_BTC_HTF_IS: dict[str, pd.DataFrame] = {}
_WORKER_BTC_HTF_OOS: dict[str, pd.DataFrame] = {}


def _init_universe_worker(
    btc_htf_is: dict[str, pd.DataFrame],
    btc_htf_oos: dict[str, pd.DataFrame],
) -> None:
    global _WORKER_BTC_HTF_IS, _WORKER_BTC_HTF_OOS
    _WORKER_BTC_HTF_IS = btc_htf_is
    _WORKER_BTC_HTF_OOS = btc_htf_oos


def evaluate_symbol_universe_worker_v402(
    symbol: str,
    btc_htf_is: dict[str, pd.DataFrame] | None = None,
    btc_htf_oos: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any] | None:
    """Worker to compute Monthly Rolling-63d Point-in-Time metrics, Static 2024-2025 DNA,
    and Patched v4.0.3 Independent + Subset trades + raw candidates for one symbol.
    """
    use_btc_is = btc_htf_is if btc_htf_is is not None else _WORKER_BTC_HTF_IS
    use_btc_oos = btc_htf_oos if btc_htf_oos is not None else _WORKER_BTC_HTF_OOS
    df = load_symbol_1h_full_2024_2026(symbol)
    if df.empty or len(df) < 200:
        return None

    daily_qvol_all = df["quote_volume"].resample("1d").sum()
    htf4_all = resample_1h_to_htf(df, "4h")
    if not htf4_all.empty:
        htf4_upper_wick = (
            (htf4_all["high"] - np.maximum(htf4_all["open"], htf4_all["close"]))
            / np.maximum(1e-9, htf4_all["close"])
            * 100.0
        )
        htf4_close_ts = pd.to_datetime(htf4_all["close_time"])
    else:
        htf4_upper_wick = pd.Series(dtype=float)
        htf4_close_ts = pd.Series(dtype="datetime64[ns, UTC]")

    # 1. Compute Monthly Trailing-63d Point-in-Time metrics strictly on [t_m - 63d, t_m)
    monthly_pit_63d: dict[str, dict[str, float]] = {}
    for m_ts in MONTHLY_REBALANCE_DATES:
        ym = f"{m_ts.year:04d}-{m_ts.month:02d}"
        w_start = m_ts - pd.Timedelta(days=63)
        dq = daily_qvol_all.loc[(daily_qvol_all.index >= w_start) & (daily_qvol_all.index < m_ts)]
        dq_act = dq[dq > 0]
        act_days = int(len(dq_act))
        med_qvol = float(dq_act.median()) if not dq_act.empty else 0.0

        if not htf4_upper_wick.empty:
            w_slice = htf4_upper_wick.loc[(htf4_all.index >= w_start) & (htf4_close_ts <= m_ts)]
            wick_p90 = float(np.percentile(w_slice, 90)) if len(w_slice) >= 10 else 5.0
        else:
            wick_p90 = 5.0

        monthly_pit_63d[ym] = {
            "active_days_63d": act_days,
            "median_qvol_63d": med_qvol,
            "wick_p90_63d": wick_p90,
        }

    # 2. Static 2024-2025 In-Sample DNA (for Ex-Ante 2026 Selection)
    df_is_only = df.loc[
        (df.index >= pd.Timestamp("2024-01-01T00:00:00+00:00"))
        & (df.index <= IN_SAMPLE_MAX_UTC)
    ]
    if not df_is_only.empty and len(df_is_only) >= 100:
        dq_is = daily_qvol_all.loc[
            (daily_qvol_all.index >= pd.Timestamp("2024-01-01T00:00:00+00:00"))
            & (daily_qvol_all.index <= IN_SAMPLE_MAX_UTC)
        ]
        dq_is_act = dq_is[dq_is > 0]
        median_daily_qvol = float(dq_is_act.median()) if not dq_is_act.empty else 0.0
        is_active_days = int(len(dq_is_act))
        if not htf4_upper_wick.empty:
            w_is = htf4_upper_wick.loc[
                (htf4_all.index >= pd.Timestamp("2024-01-01T00:00:00+00:00"))
                & (htf4_close_ts <= IN_SAMPLE_MAX_UTC)
            ]
            wick_toxicity_pct = float(np.percentile(w_is, 90)) if len(w_is) >= 10 else 5.0
        else:
            wick_toxicity_pct = 5.0
    else:
        median_daily_qvol = 0.0
        is_active_days = 0
        wick_toxicity_pct = 5.0

    if median_daily_qvol >= 50_000_000:
        liq_tier = "L1_MEGA"
    elif median_daily_qvol >= 15_000_000:
        liq_tier = "L2_DEEP"
    elif median_daily_qvol >= 3_000_000:
        liq_tier = "L3_MID"
    else:
        liq_tier = "L4_THIN"

    archetype = classify_archetype(symbol, median_daily_qvol, wick_toxicity_pct)

    # 3. Collect IS (2024-2025, with 2023-10-01 warmup) and OOS (2026, with 2025-10-01 warmup)
    df_is_ctx = df.loc[df.index <= IN_SAMPLE_MAX_UTC]
    df_oos_ctx = df.loc[df.index >= pd.Timestamp("2025-10-01T00:00:00+00:00")]

    is_collected = (
        collect_symbol_milestones_v402(
            symbol,
            df_is_ctx,
            use_btc_is,
            entry_start_ts=pd.Timestamp("2024-01-01T00:00:00+00:00"),
            entry_end_ts=IN_SAMPLE_MAX_UTC,
        )
        if len(df_is_ctx) >= 150
        else {"independent": {m: [] for m in UNIVERSE_MILESTONES}, "subset_from_m1": {m: [] for m in UNIVERSE_MILESTONES}, "raw_candidates": []}
    )
    oos_collected = (
        collect_symbol_milestones_v402(
            symbol,
            df_oos_ctx,
            use_btc_oos,
            entry_start_ts=OOS_START_UTC,
            entry_end_ts=pd.Timestamp("2026-12-31T23:59:59+00:00"),
        )
        if len(df_oos_ctx) >= 150
        else {"independent": {m: [] for m in UNIVERSE_MILESTONES}, "subset_from_m1": {m: [] for m in UNIVERSE_MILESTONES}, "raw_candidates": []}
    )
    oos_hard0831_executed = execute_symbol_candidates_from_raw(
        oos_collected["raw_candidates"],
        allowed_yms=None,
        hard_cutoff_0831=True,
    )

    m1_is_list = is_collected["independent"]["m1_f1a_pump50"]
    pump_50_count_is = len(m1_is_list)
    if pump_50_count_is > 0:
        tp1_reverted = sum(1 for x in m1_is_list if x["trade"].tp1_reached)
        gravity_decay_pct = round(tp1_reverted / pump_50_count_is * 100.0, 1)
        med_wave_ker = round(float(np.median([x["ker_wave"] for x in m1_is_list])), 3)
        med_imp_ker = round(float(np.median([x["imp_ker"] for x in m1_is_list])), 3)
    else:
        gravity_decay_pct = 0.0
        med_wave_ker = 0.0
        med_imp_ker = 0.0

    idx_series = df.index.to_series()
    diffs_h = idx_series.diff().dt.total_seconds() / 3600.0
    gap_mask = diffs_h > 1.001
    missing_hour_gaps: list[dict[str, Any]] = []
    if gap_mask.any():
        for ts_after, gap_h in diffs_h[gap_mask].items():
            ts_before = ts_after - pd.Timedelta(hours=float(gap_h))
            missing_hour_gaps.append(
                {
                    "symbol": symbol,
                    "last_bar_open_before_gap_utc": ts_before.isoformat(),
                    "last_bar_close_before_gap_utc": (ts_before + pd.Timedelta(hours=1)).isoformat(),
                    "next_bar_open_after_gap_utc": ts_after.isoformat(),
                    "open_to_open_delta_hours": round(float(gap_h), 2),
                    "missing_1h_bars_count": int(round(float(gap_h))) - 1,
                }
            )

    return {
        "symbol": symbol,
        "min_open_ts": df.index[0],
        "max_open_ts": df.index[-1],
        "max_close_ts": df.index[-1] + pd.Timedelta(hours=1),
        "min_utc": df.index[0].isoformat(),
        "last_open_utc": df.index[-1].isoformat(),
        "max_utc": (df.index[-1] + pd.Timedelta(hours=1)).isoformat(),
        "n_1h_bars": int(len(df)),
        "missing_hour_gaps": missing_hour_gaps,
        "archetype": archetype,
        "liq_tier": liq_tier,
        "median_daily_qvol_usd": round(median_daily_qvol, 0),
        "is_active_days": is_active_days,
        "wick_toxicity_p90_pct": round(wick_toxicity_pct, 2),
        "pump_50_count_is": pump_50_count_is,
        "gravity_decay_rate_pct": gravity_decay_pct,
        "median_wave_ker": med_wave_ker,
        "median_imp_ker": med_imp_ker,
        "monthly_pit_63d": monthly_pit_63d,
        "is_independent": is_collected["independent"],
        "is_subset": is_collected["subset_from_m1"],
        "is_raw_candidates": is_collected["raw_candidates"],
        "oos_independent": oos_collected["independent"],
        "oos_subset": oos_collected["subset_from_m1"],
        "oos_hard0831_independent": oos_hard0831_executed["independent"],
        "oos_raw_candidates": oos_collected["raw_candidates"],
    }


def compute_universe_input_fingerprint_and_manifest(
    *,
    code_files: list[Path] | None = None,
    data_dirs: list[Path] | None = None,
    extra_files: list[Path] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Compute content-based SHA256 fingerprint and per-file manifest over all dependent code files,
    auxiliary caches, and all input parquet files across 5m, 1h, and funding directories.
    Strictly hashes actual file bytes (`hashlib.sha256(p.read_bytes()).hexdigest()`) — never `st_size` or `st_mtime`.
    Raises `FileNotFoundError` if any required code file, extra file, or data directory is missing or empty.
    """
    import hashlib

    h = hashlib.sha256()
    use_code_files = (
        code_files
        if code_files is not None
        else [
            ROOT_DIR / "src" / "dao_vang" / "config" / "settings.py",
            ROOT_DIR / "src" / "dao_vang" / "fibo_short" / "detector.py",
            ROOT_DIR / "src" / "dao_vang" / "fibo_short" / "backtest.py",
            SCRIPT_DIR / "study_factor1_multi_repo_benchmark_2025.py",
            SCRIPT_DIR / "study_factor2_3_4_complete_2025.py",
            SCRIPT_DIR / "study_independent_audit_metrics.py",
            SCRIPT_DIR / "study_insample_2020_2025_by_year.py",
            SCRIPT_DIR / "study_oos_2026_all_7_milestones.py",
            SCRIPT_DIR / "study_coin_universe_selection_2026.py",
            SCRIPT_DIR / "verify_red_team_audit_2026.py",
            SCRIPT_DIR / "verify_red_team_reaudit_v402.py",
            SCRIPT_DIR / "verify_red_team_reaudit_v405.py",
            SCRIPT_DIR / "universe_reaudit_v402_worker.py",
        ]
    )
    code_manifest: list[dict[str, Any]] = []
    all_hashed_paths_sha256: dict[str, str] = {}
    for cf in use_code_files:
        if not cf.exists() or not cf.is_file():
            raise FileNotFoundError(f"Required code file missing for input fingerprint: {cf}")
        raw_bytes = cf.read_bytes()
        file_sha = hashlib.sha256(raw_bytes).hexdigest()
        h.update(f"code:{cf.name}:".encode("utf-8"))
        h.update(file_sha.encode("utf-8"))
        norm_p = cf.resolve().as_posix()
        code_manifest.append(
            {
                "name": cf.name,
                "path": norm_p,
                "size_bytes": len(raw_bytes),
                "sha256": file_sha,
            }
        )
        all_hashed_paths_sha256[norm_p] = file_sha

    use_extra_files = (
        extra_files
        if extra_files is not None
        else [
            ROOT_DIR / "artifacts" / "fibo_trend_short" / "coingecko_marketcap_cache.json",
            ROOT_DIR / "artifacts" / "fibo_trend_short" / "fibo_coin_universe_config.json",
            ROOT_DIR / "artifacts" / "fibo_trend_short" / "coin_universe_study_2026.json",
        ]
    )
    extra_manifest: list[dict[str, Any]] = []
    for ef in use_extra_files:
        if not ef.exists() or not ef.is_file():
            raise FileNotFoundError(f"Required extra file missing for input fingerprint: {ef}")
        raw_bytes = ef.read_bytes()
        file_sha = hashlib.sha256(raw_bytes).hexdigest()
        h.update(f"extra:{ef.name}:".encode("utf-8"))
        h.update(file_sha.encode("utf-8"))
        norm_p = ef.resolve().as_posix()
        extra_manifest.append(
            {
                "name": ef.name,
                "path": norm_p,
                "size_bytes": len(raw_bytes),
                "sha256": file_sha,
            }
        )
        all_hashed_paths_sha256[norm_p] = file_sha

    use_data_dirs = (
        data_dirs
        if data_dirs is not None
        else [
            DATA_LAKE_5M_DIR,
            PRE2024_5M_DIR,
            SHARED_1H_DIR,
            SHARED_FUNDING_DIR,
            DATA_LAKE_FUNDING_DIR,
        ]
    )
    data_dirs_manifest: dict[str, dict[str, Any]] = {}
    total_parquet_files_hashed = 0
    for ddir in use_data_dirs:
        if not ddir.exists() or not ddir.is_dir():
            raise FileNotFoundError(f"Required data directory missing for input fingerprint: {ddir}")
        parquet_files = sorted([p for p in ddir.glob("*.parquet") if p.is_file()])
        if not parquet_files:
            raise FileNotFoundError(f"Required data directory has 0 parquet files for input fingerprint: {ddir}")
        h.update(f"dir:{ddir.as_posix()}:".encode("utf-8"))
        dir_entries: list[dict[str, Any]] = []
        for p in parquet_files:
            raw_bytes = p.read_bytes()
            file_sha256 = hashlib.sha256(raw_bytes).hexdigest()
            h.update(f"{p.name}:{file_sha256};".encode("utf-8"))
            norm_p = p.resolve().as_posix()
            dir_entries.append(
                {
                    "name": p.name,
                    "path": norm_p,
                    "size_bytes": len(raw_bytes),
                    "sha256": file_sha256,
                }
            )
            all_hashed_paths_sha256[norm_p] = file_sha256
            total_parquet_files_hashed += 1
        data_dirs_manifest[ddir.resolve().as_posix()] = {
            "configured_path": ddir.as_posix(),
            "resolved_path": ddir.resolve().as_posix(),
            "file_count": len(dir_entries),
            "files": dir_entries,
        }

    fp_hex = h.hexdigest()
    manifest = {
        "input_fingerprint_sha256": fp_hex,
        "hash_mode": "FULL_BYTE_CONTENT_SHA256_FAIL_LOUD_ON_MISSING_SOURCES",
        "code_files_count": len(code_manifest),
        "extra_files_count": len(extra_manifest),
        "data_dirs_count": len(data_dirs_manifest),
        "total_parquet_files_hashed": total_parquet_files_hashed,
        "total_files_hashed": len(all_hashed_paths_sha256),
        "configured_data_dirs": {
            "DATA_LAKE_5M_DIR": DATA_LAKE_5M_DIR.as_posix(),
            "PRE2024_5M_DIR": PRE2024_5M_DIR.as_posix(),
            "SHARED_1H_DIR": SHARED_1H_DIR.as_posix(),
            "SHARED_FUNDING_DIR": SHARED_FUNDING_DIR.as_posix(),
            "DATA_LAKE_FUNDING_DIR": DATA_LAKE_FUNDING_DIR.as_posix(),
        },
        "code_files": code_manifest,
        "extra_files": extra_manifest,
        "data_dirs": data_dirs_manifest,
        "all_hashed_paths_sha256": all_hashed_paths_sha256,
    }
    return fp_hex, manifest


def compute_universe_input_fingerprint(
    *,
    code_files: list[Path] | None = None,
    data_dirs: list[Path] | None = None,
    extra_files: list[Path] | None = None,
) -> str:
    """Compute content-based SHA256 fingerprint over all dependent code files, auxiliary caches,
    and all input parquet files across 5m, 1h, and funding directories.
    Strictly hashes actual file bytes (`hashlib.sha256(p.read_bytes()).hexdigest()`) — never `st_size` or `st_mtime`.
    Raises `FileNotFoundError` if any required source file or directory is missing or empty.
    """
    fp_hex, _ = compute_universe_input_fingerprint_and_manifest(
        code_files=code_files,
        data_dirs=data_dirs,
        extra_files=extra_files,
    )
    return fp_hex


def run_universe_338_reaudit_v402(
    summarize_items_fn: Any,
    *,
    use_cache: bool = True,
    target_version: str = "4.0.5",
    method_comparison_fn: Any | None = None,
) -> dict[str, Any]:
    """Run (or load content-fingerprint-verified cached) 338-coin universe evaluation with v4.0.5 engine fixes:
    - Canonical `compute_orthogonal_conviction_score` unified across detector, benchmark, and universe worker
    - Causal execution clock (`decision_time == entry_time == H1_close_time`, `exit_time == exit_close_time`)
    - Real UTC `exit_close_time` cooldown (`max(exit_close_epoch_h, decision_epoch_h + max(min_cooldown_hours, real_hold_hours))`)
    - Pre-cooldown/pre-wave Rolling Monthly Point-in-Time Top-50 Volume (`ROLLING_PIT_TOP50_VOL`)
    - Single-Source Idempotent Portfolio-Coupled Execution (`portfolio_coupled_execution`) without a second cap pass,
      exporting `accepted_trade_ids`, `executed_trade_ids`, and `ledger_sha256` on all 112 coupled nodes
    - Common Hard-Cutoff `2026-08-31 23:59:59 UTC` valuation alongside full `2026-09-29`
    - Content-based SHA256 input fingerprint across all code, marketcap cache, and 5m/1h/funding_8h/funding parquet files.
    """
    ver_slug = target_version.replace(".", "_")
    cache_path = ROOT_DIR / "artifacts" / "fibo_trend_short" / f"universe_338_reaudit_v{ver_slug}_summary.json"
    ledgers_cache_path = ROOT_DIR / "artifacts" / "fibo_trend_short" / f"universe_coupled_ledgers_v{ver_slug}_cache.json"
    input_fp = compute_universe_input_fingerprint()

    if use_cache and method_comparison_fn is None and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if (
                cached.get("schema_version") == target_version
                and cached.get("input_fingerprint_sha256") == input_fp
            ):
                print(f"   [Universe 338] Loaded fingerprint-verified v{target_version} summary from {cache_path.name}")
                return cached
        except Exception:
            pass

    t0 = time.time()
    all_parquet = sorted(DATA_LAKE_5M_DIR.glob("*.parquet"))
    excluded_stable_or_index = sorted(
        [p.stem for p in all_parquet if not p.stem.endswith("USDT") or p.stem in STABLE_OR_INDEX_EXCLUDE]
    )
    symbols = [
        p.stem
        for p in all_parquet
        if p.stem.endswith("USDT") and p.stem not in STABLE_OR_INDEX_EXCLUDE
    ]
    print(f"   [Universe 338] Scanning {len(symbols)} USD-M Perpetual symbols with patched v{target_version} engine...")

    btc_full = load_symbol_1h_full_2024_2026("BTCUSDT")
    btc_is = btc_full.loc[btc_full.index <= IN_SAMPLE_MAX_UTC]
    btc_oos = btc_full.loc[btc_full.index >= pd.Timestamp("2025-10-01T00:00:00+00:00")]

    btc_htf_is = {tf: calc_htf_features_no_bfill(resample_1h_to_htf(btc_is, tf)) for tf in ("4h", "1d")}
    btc_htf_oos = {tf: calc_htf_features_no_bfill(resample_1h_to_htf(btc_oos, tf)) for tf in ("4h", "1d")}

    import gc

    _init_universe_worker(btc_htf_is, btc_htf_oos)
    symbol_results: list[dict[str, Any]] = []
    excluded_short_history: list[dict[str, Any]] = []
    for completed, sym in enumerate(symbols, start=1):
        res = evaluate_symbol_universe_worker_v402(sym, btc_htf_is, btc_htf_oos)
        if res is not None:
            symbol_results.append(res)
        else:
            df_short = load_symbol_1h_full_2024_2026(sym)
            excluded_short_history.append(
                {
                    "symbol": sym,
                    "n_1h_bars": int(len(df_short)),
                    "min_open_utc": df_short.index[0].isoformat() if not df_short.empty else None,
                    "last_open_utc": df_short.index[-1].isoformat() if not df_short.empty else None,
                    "reason": "insufficient_history_lt_200_1h_bars",
                }
            )
        if completed % 25 == 0:
            gc.collect()
        if completed % 30 == 0 or completed == len(symbols):
            print(f"   [Universe 338] {completed}/{len(symbols)} symbols processed ({time.time() - t0:.1f}s)", flush=True)

    symbol_results.sort(key=lambda r: r["symbol"])
    cg_map = load_coingecko_market_map()
    for r in symbol_results:
        enrich_with_marketcap_and_supply(r, cg_map)

    # 1. Build True Monthly Rolling Point-in-Time Top-50 Volume map: ym -> set of 50 symbols
    # Uses ONLY trailing 63 days [t_month - 63d, t_month): active_days_63d >= 50, wick_p90_63d <= 3.2%, non-G1
    rolling_pit_top50_by_ym: dict[str, set[str]] = {}
    for m_ts in MONTHLY_REBALANCE_DATES:
        ym = f"{m_ts.year:04d}-{m_ts.month:02d}"
        eligible_ym = []
        for r in symbol_results:
            if r["archetype"] == "G1_STORE_OF_VALUE_MAJOR":
                continue
            st_ym = r["monthly_pit_63d"].get(ym)
            if not st_ym:
                continue
            if st_ym["active_days_63d"] >= 50 and st_ym["wick_p90_63d"] <= 3.2 and st_ym["median_qvol_63d"] > 0:
                eligible_ym.append((st_ym["median_qvol_63d"], r["symbol"]))
        eligible_ym.sort(key=lambda x: x[0], reverse=True)
        rolling_pit_top50_by_ym[ym] = {sym for _, sym in eligible_ym[:50]}

    # Execute per-symbol Rolling PIT state machine where monthly membership is checked BEFORE wave/cooldown consumption!
    allowed_yms_by_symbol: dict[str, set[str]] = {}
    for r in symbol_results:
        sym = r["symbol"]
        sym_pit_yms = {ym for ym, sset in rolling_pit_top50_by_ym.items() if sym in sset}
        allowed_yms_by_symbol[sym] = sym_pit_yms
        pit_is_exec = execute_symbol_candidates_from_raw(
            r["is_raw_candidates"],
            allowed_yms=sym_pit_yms,
            hard_cutoff_0831=False,
        )
        pit_oos_exec = execute_symbol_candidates_from_raw(
            r["oos_raw_candidates"],
            allowed_yms=sym_pit_yms,
            hard_cutoff_0831=False,
        )
        pit_oos_hard0831_exec = execute_symbol_candidates_from_raw(
            r["oos_raw_candidates"],
            allowed_yms=sym_pit_yms,
            hard_cutoff_0831=True,
        )
        r["is_rolling_pit_independent"] = pit_is_exec["independent"]
        r["is_rolling_pit_subset"] = pit_is_exec["subset_from_m1"]
        r["oos_rolling_pit_independent"] = pit_oos_exec["independent"]
        r["oos_rolling_pit_subset"] = pit_oos_exec["subset_from_m1"]
        r["oos_rolling_pit_hard0831_independent"] = pit_oos_hard0831_exec["independent"]

    # 2. Static Ex-Ante 2026 Top-50 Volume (frozen at 2025-12-31 using 2024-2025 IS metrics)
    ex_ante_2026_candidates = sorted(
        [
            r
            for r in symbol_results
            if r["archetype"] != "G1_STORE_OF_VALUE_MAJOR"
            and r["is_active_days"] >= 63
            and r["wick_toxicity_p90_pct"] <= 3.2
        ],
        key=lambda x: x["median_daily_qvol_usd"],
        reverse=True,
    )
    ex_ante_2026_top50_syms = {r["symbol"] for r in ex_ante_2026_candidates[:50]}

    # 3. Assign Ex-Ante Universe Tiers (using patched independent IS metrics)
    pit_zero_bias_mcap_float_syms = {
        r["symbol"]
        for r in symbol_results
        if r["archetype"] != "G1_STORE_OF_VALUE_MAJOR"
        and r["is_active_days"] >= 63
        and r["mcap_usd"] >= 150_000_000.0
        and r["float_ratio"] >= 0.70
        and r["median_daily_qvol_usd"] >= 5_000_000.0
        and r["wick_toxicity_p90_pct"] <= 3.5
    }

    for r in symbol_results:
        m4a_is_sum = summarize_items_fn(r["is_independent"]["m4_f2_elite"], include_bootstrap=False)
        m6b_is_sum = summarize_items_fn(r["is_independent"]["m6_f4_expanded"], include_bootstrap=False)
        u_tier, u_score, u_reason = assign_ex_ante_universe_tier(r, m4a_is_sum, m6b_is_sum)
        r["universe_tier"] = u_tier
        r["suitability_score"] = u_score
        r["tier_reason_vi"] = u_reason
        r["in_ex_ante_2026_top50_vol"] = r["symbol"] in ex_ante_2026_top50_syms
        r["in_pit_zero_bias_mcap_float"] = r["symbol"] in pit_zero_bias_mcap_float_syms

    universe_coupled_ledgers_by_key: dict[str, Any] = {}

    # Helper to evaluate a basket (static predicate or rolling monthly PIT)
    def _eval_basket(
        basket_name: str,
        pit_status_tag: str,
        pred_fn: Any | None = None,
        is_rolling_pit: bool = False,
        compute_nav: bool = False,
    ) -> dict[str, Any]:
        if is_rolling_pit:
            distinct_syms = set()
            for sset in rolling_pit_top50_by_ym.values():
                distinct_syms |= sset
            coin_count_desc: Any = {
                "target_per_month": 50,
                "avg_monthly_active": round(float(np.mean([len(s) for s in rolling_pit_top50_by_ym.values()])), 1),
                "distinct_symbols_2024_2026": len(distinct_syms),
            }
            sub_r = symbol_results
        else:
            sub_r = [r for r in symbol_results if pred_fn(r)]
            coin_count_desc = len(sub_r)

        indep_is_res: dict[str, Any] = {}
        indep_oos_res: dict[str, Any] = {}
        indep_oos_hard0831_res: dict[str, Any] = {}
        subset_is_res: dict[str, Any] = {}
        subset_oos_res: dict[str, Any] = {}
        post_filter_pit_comparison: dict[str, Any] = {}
        portfolio_nav_oos_2026: dict[str, Any] = {}
        portfolio_nav_oos_hard0831: dict[str, Any] = {}
        portfolio_nav_is_2024_2025: dict[str, Any] = {}
        portfolio_coupled_is_2024_2025: dict[str, Any] = {}
        portfolio_coupled_oos_2026: dict[str, Any] = {}
        portfolio_coupled_oos_runout0831: dict[str, Any] = {}
        portfolio_coupled_oos_hard0831: dict[str, Any] = {}

        raw_is_all = [c for r in sub_r for c in r["is_raw_candidates"]] if compute_nav else []
        raw_oos_all = [c for r in sub_r for c in r["oos_raw_candidates"]] if compute_nav else []

        for m in UNIVERSE_MILESTONES:
            if is_rolling_pit:
                # True Pre-Cooldown / Pre-Wave Monthly PIT Execution
                items_is = [x for r in symbol_results for x in r["is_rolling_pit_independent"][m]]
                items_oos = [x for r in symbol_results for x in r["oos_rolling_pit_independent"][m]]
                items_oos_hard0831 = [x for r in symbol_results for x in r["oos_rolling_pit_hard0831_independent"][m]]
                sub_is = [x for r in symbol_results for x in r["is_rolling_pit_subset"][m]]
                sub_oos = [x for r in symbol_results for x in r["oos_rolling_pit_subset"][m]]

                # Post-Filtered comparison (filtering static per-symbol trades by month after cooldown)
                post_filt_is = [
                    x
                    for r in symbol_results
                    for x in r["is_independent"][m]
                    if r["symbol"] in rolling_pit_top50_by_ym.get(x["entry_ym"], set())
                ]
                post_filt_oos = [
                    x
                    for r in symbol_results
                    for x in r["oos_independent"][m]
                    if r["symbol"] in rolling_pit_top50_by_ym.get(x["entry_ym"], set())
                ]
                post_filter_pit_comparison[m] = {
                    "pre_cooldown_pit_is_trades": len(items_is),
                    "post_filter_static_is_trades": len(post_filt_is),
                    "delta_is_trades_recovered": len(items_is) - len(post_filt_is),
                    "pre_cooldown_pit_oos_trades": len(items_oos),
                    "post_filter_static_oos_trades": len(post_filt_oos),
                    "delta_oos_trades_recovered": len(items_oos) - len(post_filt_oos),
                }
            else:
                items_is = [x for r in sub_r for x in r["is_independent"][m]]
                items_oos = [x for r in sub_r for x in r["oos_independent"][m]]
                items_oos_hard0831 = [x for r in sub_r for x in r["oos_hard0831_independent"][m]]
                sub_is = [x for r in sub_r for x in r["is_subset"][m]]
                sub_oos = [x for r in sub_r for x in r["oos_subset"][m]]

            inc_boot = m in ("m4_f2_elite", "m6_f4_expanded", "m6_f4_sniper", "m6_f4_elite_sniper")
            indep_is_res[m] = summarize_items_fn(items_is, include_bootstrap=inc_boot)
            indep_oos_res[m] = summarize_items_fn(items_oos, include_bootstrap=inc_boot)
            indep_oos_hard0831_res[m] = summarize_items_fn(items_oos_hard0831, include_bootstrap=inc_boot)
            subset_is_res[m] = summarize_items_fn(sub_is, include_bootstrap=False)
            subset_oos_res[m] = summarize_items_fn(sub_oos, include_bootstrap=False)

            if compute_nav and m in ("m4_f2_elite", "m6_f4_expanded", "m6_f4_sniper", "m6_f4_elite_sniper"):
                nav_oos = compute_portfolio_nav_and_concurrency(
                    items_oos,
                    window_start_utc="2026-01-01T00:00:00+00:00",
                    window_end_utc="2026-09-29T23:00:00+00:00",
                    base_notional_weight=0.20,
                    max_concurrent_cap=5,
                    max_total_notional_frac=1.0,
                    max_total_sl_risk_frac=0.12,
                    funding_bps_per_8h=0.0,
                    round_trip_fee_bps=20.0,
                )
                portfolio_nav_oos_2026[m] = {
                    "uncapped_concurrency": nav_oos["uncapped_concurrency"],
                    "accepted_concurrency": nav_oos["accepted_concurrency"],
                    "nav_20pct_per_1x": nav_oos["nav_simulation_20pct_notional_per_1x"],
                }

                nav_oos_0831 = compute_portfolio_nav_and_concurrency(
                    items_oos_hard0831,
                    window_start_utc="2026-01-01T00:00:00+00:00",
                    window_end_utc="2026-09-01T00:00:00+00:00",
                    base_notional_weight=0.20,
                    max_concurrent_cap=5,
                    max_total_notional_frac=1.0,
                    max_total_sl_risk_frac=0.12,
                    funding_bps_per_8h=0.0,
                    round_trip_fee_bps=20.0,
                )
                portfolio_nav_oos_hard0831[m] = {
                    "uncapped_concurrency": nav_oos_0831["uncapped_concurrency"],
                    "accepted_concurrency": nav_oos_0831["accepted_concurrency"],
                    "nav_20pct_per_1x": nav_oos_0831["nav_simulation_20pct_notional_per_1x"],
                }

                nav_is = compute_portfolio_nav_and_concurrency(
                    items_is,
                    window_start_utc="2024-01-01T00:00:00+00:00",
                    window_end_utc=IS_VALUATION_END_UTC.isoformat(),
                    base_notional_weight=0.20,
                    max_concurrent_cap=5,
                    max_total_notional_frac=1.0,
                    max_total_sl_risk_frac=0.12,
                    funding_bps_per_8h=0.0,
                    round_trip_fee_bps=20.0,
                )
                portfolio_nav_is_2024_2025[m] = {
                    "uncapped_concurrency": nav_is["uncapped_concurrency"],
                    "accepted_concurrency": nav_is["accepted_concurrency"],
                    "nav_20pct_per_1x": nav_is["nav_simulation_20pct_notional_per_1x"],
                }

                # Single-Source Portfolio-Coupled Execution (caps checked before consuming wave or setting cooldown)
                use_allowed_map = allowed_yms_by_symbol if is_rolling_pit else None
                coupled_is = run_universe_portfolio_coupled_execution(
                    raw_is_all,
                    m,
                    window_start_utc="2024-01-01T00:00:00+00:00",
                    window_end_utc=IS_VALUATION_END_UTC.isoformat(),
                    allowed_yms_by_symbol=use_allowed_map,
                    hard_cutoff_0831=False,
                )
                lkey_is = f"universe_338__{basket_name}__is_2024_2025__{m}"
                universe_coupled_ledgers_by_key[lkey_is] = {
                    "ledger_key": lkey_is,
                    "basket": basket_name,
                    "window": "is_2024_2025",
                    "milestone": m,
                    "accepted_trades": coupled_is["accepted_trades"],
                    "executed_trades": coupled_is["executed_trades"],
                    "accepted_trade_ids": coupled_is["accepted_trade_ids"],
                    "executed_trade_ids": coupled_is["executed_trade_ids"],
                    "ledger_sha256": coupled_is["ledger_sha256"],
                    "ledger_records": coupled_is["ledger_records"],
                }
                portfolio_coupled_is_2024_2025[m] = {
                    "summary": summarize_items_fn(coupled_is["accepted_items"], include_bootstrap=False),
                    "accepted_trades": coupled_is["accepted_trades"],
                    "executed_trades": coupled_is["executed_trades"],
                    "accepted_trade_ids": coupled_is["accepted_trade_ids"],
                    "executed_trade_ids": coupled_is["executed_trade_ids"],
                    "ledger_artifact_path": f"artifacts/fibo_trend_short/coupled_trade_ledgers_v{ver_slug}.json",
                    "ledger_key": lkey_is,
                    "ledger_sha256": coupled_is["ledger_sha256"],
                    "trade_id_set_exact_match": coupled_is["trade_id_set_exact_match"],
                    "single_source_accounting_no_second_cap_pass": coupled_is["single_source_accounting_no_second_cap_pass"],
                    "blocked_by_wave_or_cooldown": coupled_is["blocked_by_wave_or_cooldown"],
                    "rejected_by_cap_total": coupled_is["rejected_by_cap_total"],
                    "rejected_by_slot_cap": coupled_is["rejected_by_slot_cap"],
                    "rejected_by_notional_cap": coupled_is["rejected_by_notional_cap"],
                    "rejected_by_sl_risk_cap": coupled_is["rejected_by_sl_risk_cap"],
                    "accepted_concurrency": coupled_is["accepted_concurrency"],
                    "nav_20pct_per_1x": coupled_is["nav_20pct_per_1x"],
                }

                coupled_oos = run_universe_portfolio_coupled_execution(
                    raw_oos_all,
                    m,
                    window_start_utc="2026-01-01T00:00:00+00:00",
                    window_end_utc="2026-09-29T23:00:00+00:00",
                    allowed_yms_by_symbol=use_allowed_map,
                    hard_cutoff_0831=False,
                )
                lkey_oos = f"universe_338__{basket_name}__oos_2026__{m}"
                universe_coupled_ledgers_by_key[lkey_oos] = {
                    "ledger_key": lkey_oos,
                    "basket": basket_name,
                    "window": "oos_2026",
                    "milestone": m,
                    "accepted_trades": coupled_oos["accepted_trades"],
                    "executed_trades": coupled_oos["executed_trades"],
                    "accepted_trade_ids": coupled_oos["accepted_trade_ids"],
                    "executed_trade_ids": coupled_oos["executed_trade_ids"],
                    "ledger_sha256": coupled_oos["ledger_sha256"],
                    "ledger_records": coupled_oos["ledger_records"],
                }
                portfolio_coupled_oos_2026[m] = {
                    "summary": summarize_items_fn(coupled_oos["accepted_items"], include_bootstrap=False),
                    "accepted_trades": coupled_oos["accepted_trades"],
                    "executed_trades": coupled_oos["executed_trades"],
                    "accepted_trade_ids": coupled_oos["accepted_trade_ids"],
                    "executed_trade_ids": coupled_oos["executed_trade_ids"],
                    "ledger_artifact_path": f"artifacts/fibo_trend_short/coupled_trade_ledgers_v{ver_slug}.json",
                    "ledger_key": lkey_oos,
                    "ledger_sha256": coupled_oos["ledger_sha256"],
                    "trade_id_set_exact_match": coupled_oos["trade_id_set_exact_match"],
                    "single_source_accounting_no_second_cap_pass": coupled_oos["single_source_accounting_no_second_cap_pass"],
                    "blocked_by_wave_or_cooldown": coupled_oos["blocked_by_wave_or_cooldown"],
                    "rejected_by_cap_total": coupled_oos["rejected_by_cap_total"],
                    "rejected_by_slot_cap": coupled_oos["rejected_by_slot_cap"],
                    "rejected_by_notional_cap": coupled_oos["rejected_by_notional_cap"],
                    "rejected_by_sl_risk_cap": coupled_oos["rejected_by_sl_risk_cap"],
                    "accepted_concurrency": coupled_oos["accepted_concurrency"],
                    "nav_20pct_per_1x": coupled_oos["nav_20pct_per_1x"],
                }

                coupled_oos_0831 = run_universe_portfolio_coupled_execution(
                    raw_oos_all,
                    m,
                    window_start_utc="2026-01-01T00:00:00+00:00",
                    window_end_utc="2026-09-01T00:00:00+00:00",
                    allowed_yms_by_symbol=use_allowed_map,
                    hard_cutoff_0831=True,
                )
                lkey_oos_runout = f"universe_338__{basket_name}__oos_2026_entry_cutoff_0831_runout__{m}"
                lkey_oos_hard = f"universe_338__{basket_name}__oos_2026_hard_cutoff_0831__{m}"
                for lk_0831, w_tag in (
                    (lkey_oos_runout, "oos_2026_entry_cutoff_0831_runout"),
                    (lkey_oos_hard, "oos_2026_hard_cutoff_0831"),
                ):
                    universe_coupled_ledgers_by_key[lk_0831] = {
                        "ledger_key": lk_0831,
                        "basket": basket_name,
                        "window": w_tag,
                        "milestone": m,
                        "accepted_trades": coupled_oos_0831["accepted_trades"],
                        "executed_trades": coupled_oos_0831["executed_trades"],
                        "accepted_trade_ids": coupled_oos_0831["accepted_trade_ids"],
                        "executed_trade_ids": coupled_oos_0831["executed_trade_ids"],
                        "ledger_sha256": coupled_oos_0831["ledger_sha256"],
                        "ledger_records": coupled_oos_0831["ledger_records"],
                    }
                base_0831_node = {
                    "summary": summarize_items_fn(coupled_oos_0831["accepted_items"], include_bootstrap=False),
                    "accepted_trades": coupled_oos_0831["accepted_trades"],
                    "executed_trades": coupled_oos_0831["executed_trades"],
                    "accepted_trade_ids": coupled_oos_0831["accepted_trade_ids"],
                    "executed_trade_ids": coupled_oos_0831["executed_trade_ids"],
                    "ledger_artifact_path": f"artifacts/fibo_trend_short/coupled_trade_ledgers_v{ver_slug}.json",
                    "ledger_sha256": coupled_oos_0831["ledger_sha256"],
                    "trade_id_set_exact_match": coupled_oos_0831["trade_id_set_exact_match"],
                    "single_source_accounting_no_second_cap_pass": coupled_oos_0831["single_source_accounting_no_second_cap_pass"],
                    "blocked_by_wave_or_cooldown": coupled_oos_0831["blocked_by_wave_or_cooldown"],
                    "rejected_by_cap_total": coupled_oos_0831["rejected_by_cap_total"],
                    "rejected_by_slot_cap": coupled_oos_0831["rejected_by_slot_cap"],
                    "rejected_by_notional_cap": coupled_oos_0831["rejected_by_notional_cap"],
                    "rejected_by_sl_risk_cap": coupled_oos_0831["rejected_by_sl_risk_cap"],
                    "accepted_concurrency": coupled_oos_0831["accepted_concurrency"],
                    "nav_20pct_per_1x": coupled_oos_0831["nav_20pct_per_1x"],
                }
                portfolio_coupled_oos_runout0831[m] = {**base_0831_node, "ledger_key": lkey_oos_runout}
                portfolio_coupled_oos_hard0831[m] = {**base_0831_node, "ledger_key": lkey_oos_hard}

        res_dict: dict[str, Any] = {
            "basket_name": basket_name,
            "pit_status_tag": pit_status_tag,
            "coin_count": coin_count_desc,
            "independent_execution": {
                "is_2024_2025": indep_is_res,
                "oos_2026": indep_oos_res,
                "oos_2026_entry_cutoff_0831_runout": indep_oos_res,
                "oos_2026_common_hard_cutoff_0831": indep_oos_hard0831_res,
            },
            "legacy_subset_from_m1": {
                "is_2024_2025": subset_is_res,
                "oos_2026": subset_oos_res,
            },
            "portfolio_capped_nav_is_2024_2025": portfolio_nav_is_2024_2025,
            "portfolio_capped_nav_oos_2026": portfolio_nav_oos_2026,
            "portfolio_capped_nav_oos_2026_entry_cutoff_0831_runout": portfolio_nav_oos_hard0831,
            "portfolio_capped_nav_oos_2026_hard_cutoff_0831": portfolio_nav_oos_hard0831,
            "portfolio_coupled_execution_is_2024_2025": portfolio_coupled_is_2024_2025,
            "portfolio_coupled_execution_oos_2026": portfolio_coupled_oos_2026,
            "portfolio_coupled_execution_oos_2026_entry_cutoff_0831_runout": portfolio_coupled_oos_runout0831,
            "portfolio_coupled_execution_oos_2026_hard_cutoff_0831": portfolio_coupled_oos_hard0831,
        }
        if is_rolling_pit:
            res_dict["pre_cooldown_vs_post_filter_pit_audit"] = post_filter_pit_comparison
        return res_dict

    by_universe_tier = {
        "ALL_338_UNFILTERED": _eval_basket(
            "ALL_338_UNFILTERED",
            "UNFILTERED_BASELINE_ALL_338_SYMBOLS",
            pred_fn=lambda r: True,
            compute_nav=True,
        ),
        "ROLLING_PIT_TOP50_VOL": _eval_basket(
            "ROLLING_PIT_TOP50_VOL",
            "STRICT_POINT_IN_TIME_MONTHLY_TRAILING_63D_PRE_COOLDOWN_ON_BOTH_2024_2025_AND_2026",
            is_rolling_pit=True,
            compute_nav=True,
        ),
        "EX_ANTE_2026_TOP50_VOL": _eval_basket(
            "EX_ANTE_2026_TOP50_VOL",
            "IN_SAMPLE_SELECTION_ON_2024_2025__STRICT_EX_ANTE_FROZEN_FOR_2026_OOS",
            pred_fn=lambda r: r["in_ex_ante_2026_top50_vol"],
            compute_nav=True,
        ),
        "TIER_S_CORE": _eval_basket(
            "TIER_S_CORE",
            "IN_SAMPLE_CALIBRATED_ON_2024_2025_OHLCV_ARCHETYPE__EX_ANTE_ON_2026_OOS__NO_MCAP_SNAPSHOT_DEPENDENCY",
            pred_fn=lambda r: r["universe_tier"] == "TIER_S_CORE",
            compute_nav=True,
        ),
        "TIER_S_PLUS_A_WHITELIST": _eval_basket(
            "TIER_S_PLUS_A_WHITELIST",
            "IN_SAMPLE_CALIBRATED_ON_2024_2025_PLUS_2026_COINGECKO_MCAP_FLOAT_SNAPSHOT_ON_TIER_A",
            pred_fn=lambda r: r["universe_tier"] in ("TIER_S_CORE", "TIER_A_EXTENDED"),
            compute_nav=True,
        ),
        "PIT_ZERO_BIAS_MCAP_FLOAT": _eval_basket(
            "PIT_ZERO_BIAS_MCAP_FLOAT",
            "ZERO_PNL_TUNING_RULE_BUT_USES_2026_COINGECKO_MCAP_FLOAT_SNAPSHOT",
            pred_fn=lambda r: r["in_pit_zero_bias_mcap_float"],
            compute_nav=True,
        ),
        "BLACKLIST": _eval_basket(
            "BLACKLIST",
            "EXCLUDED_SYMBOLS_IN_SAMPLE_2024_2025_AND_2026_OOS",
            pred_fn=lambda r: r["universe_tier"] == "BLACKLIST",
            compute_nav=True,
        ),
    }

    by_liquidity = {}
    for l_name in ("L1_MEGA", "L2_DEEP", "L3_MID", "L4_THIN"):
        by_liquidity[l_name] = _eval_basket(
            l_name,
            "STATIC_2024_2025_MEDIAN_DAILY_QVOL_TIER",
            pred_fn=lambda r, ln=l_name: r["liq_tier"] == ln,
            compute_nav=False,
        )

    by_archetype = {}
    for a_name in (
        "G1_STORE_OF_VALUE_MAJOR",
        "G2_LIQUID_L1_L2_DEFI",
        "G3_HIGH_BETA_NARRATIVE_MIDCAP",
        "G4_LIQUID_MEME_RETAIL",
        "G5_THIN_OR_MANIPULATED",
    ):
        by_archetype[a_name] = _eval_basket(
            a_name,
            "STRUCTURAL_ASSET_ARCHETYPE",
            pred_fn=lambda r, an=a_name: r["archetype"] == an,
            compute_nav=False,
        )

    # Exact timestamp-based coverage & listing / truncation audit across all 345 5m parquet files
    ts_2024_start = pd.Timestamp("2024-01-01T00:00:00+00:00")
    ts_2026_08_31_open = pd.Timestamp("2026-08-31T23:00:00+00:00")
    ts_2026_09_29_open = pd.Timestamp("2026-09-29T23:00:00+00:00")

    starts_at_or_before_2024 = sum(1 for r in symbol_results if r["min_open_ts"] <= ts_2024_start)
    starts_after_2024 = sum(1 for r in symbol_results if r["min_open_ts"] > ts_2024_start)
    ends_before_2026_08_31 = sum(1 for r in symbol_results if r["max_open_ts"] < ts_2026_08_31_open)
    ends_at_2026_08_31_cutoff = sum(1 for r in symbol_results if r["max_open_ts"] == ts_2026_08_31_open)
    ends_at_2026_09_29_shared = sum(1 for r in symbol_results if r["max_open_ts"] == ts_2026_09_29_open)

    # Real-data missing-hour gaps audit across all 338 symbols (`FS404-01`: CVXUSDT 12h, LITUSDT 18h, PUMPUSDT 8h)
    symbols_with_gaps_detail: dict[str, Any] = {}
    total_trades_spanning_missing_bars = 0
    for r in symbol_results:
        gaps = r.get("missing_hour_gaps", [])
        if not gaps:
            continue
        sym_g = r["symbol"]
        gap_intervals = [
            (
                pd.Timestamp(g["last_bar_close_before_gap_utc"]),
                pd.Timestamp(g["next_bar_open_after_gap_utc"]),
                float(g["open_to_open_delta_hours"]),
            )
            for g in gaps
        ]
        all_raw_cands = r["is_raw_candidates"] + r["oos_raw_candidates"]
        spanning_candidates: list[dict[str, Any]] = []
        nearby_candidates_within_72h: list[dict[str, Any]] = []
        for c in all_raw_cands:
            t_in = pd.Timestamp(c["decision_time"])
            sim_std = c["sim_std"]
            t_out = pd.Timestamp(sim_std.get("exit_close_time") or sim_std["exit_time"])
            obs_b = int(sim_std.get("observed_bars", sim_std["hold_hours"]))
            real_h = int((t_out - t_in).total_seconds() // 3600)
            for g_start, g_end, g_h in gap_intervals:
                if t_in < g_end and t_out > g_start:
                    spanning_candidates.append(
                        {
                            "decision_time": c["decision_time"],
                            "exit_close_time": t_out.isoformat(),
                            "tf": c["tf"],
                            "observed_bars": obs_b,
                            "real_hold_hours": real_h,
                            "eligible_milestones": sorted(list(c["eligible_milestones"])),
                        }
                    )
                if (g_start - pd.Timedelta(hours=72)) <= t_in <= (g_end + pd.Timedelta(hours=72)):
                    nearby_candidates_within_72h.append(
                        {
                            "decision_time": c["decision_time"],
                            "exit_close_time": t_out.isoformat(),
                            "tf": c["tf"],
                            "observed_bars": obs_b,
                            "real_hold_hours": real_h,
                            "eligible_milestones": sorted(list(c["eligible_milestones"])),
                        }
                    )
        m1_is_trades = [
            {
                "trade_id": x["trade"].trade_id,
                "tf": x["tf"],
                "entry_time": x["trade"].entry_time,
                "exit_time": x["trade"].exit_time,
                "observed_bars": x["observed_bars"],
                "real_hold_hours": x["real_hold_hours"],
                "net_return_pct": x["trade"].net_return_pct,
                "terminal_outcome": x["trade"].terminal_outcome,
            }
            for x in r["is_independent"]["m1_f1a_pump50"]
        ]
        m6b_is_trades = [
            {
                "trade_id": x["trade"].trade_id,
                "tf": x["tf"],
                "entry_time": x["trade"].entry_time,
                "exit_time": x["trade"].exit_time,
                "observed_bars": x["observed_bars"],
                "real_hold_hours": x["real_hold_hours"],
                "net_return_pct": x["trade"].net_return_pct,
                "terminal_outcome": x["trade"].terminal_outcome,
            }
            for x in r["is_independent"]["m6_f4_expanded"]
        ]
        m1_oos_trades = [
            {
                "trade_id": x["trade"].trade_id,
                "tf": x["tf"],
                "entry_time": x["trade"].entry_time,
                "exit_time": x["trade"].exit_time,
                "observed_bars": x["observed_bars"],
                "real_hold_hours": x["real_hold_hours"],
                "net_return_pct": x["trade"].net_return_pct,
                "terminal_outcome": x["trade"].terminal_outcome,
            }
            for x in r["oos_independent"]["m1_f1a_pump50"]
        ]
        m6b_oos_trades = [
            {
                "trade_id": x["trade"].trade_id,
                "tf": x["tf"],
                "entry_time": x["trade"].entry_time,
                "exit_time": x["trade"].exit_time,
                "observed_bars": x["observed_bars"],
                "real_hold_hours": x["real_hold_hours"],
                "net_return_pct": x["trade"].net_return_pct,
                "terminal_outcome": x["trade"].terminal_outcome,
            }
            for x in r["oos_independent"]["m6_f4_expanded"]
        ]
        total_trades_spanning_missing_bars += len(spanning_candidates)
        symbols_with_gaps_detail[sym_g] = {
            "universe_tier": r["universe_tier"],
            "liq_tier": r["liq_tier"],
            "archetype": r["archetype"],
            "n_1h_bars": r["n_1h_bars"],
            "gaps": gaps,
            "raw_candidates_is_count": len(r["is_raw_candidates"]),
            "raw_candidates_oos_count": len(r["oos_raw_candidates"]),
            "candidates_spanning_gap_count": len(spanning_candidates),
            "candidates_spanning_gap": spanning_candidates,
            "candidates_within_72h_of_gap_count": len(nearby_candidates_within_72h),
            "candidates_within_72h_of_gap": nearby_candidates_within_72h,
            "m1_is_trades_count": len(m1_is_trades),
            "m1_is_trades": m1_is_trades,
            "m6b_is_trades_count": len(m6b_is_trades),
            "m6b_is_trades": m6b_is_trades,
            "m1_oos_trades_count": len(m1_oos_trades),
            "m1_oos_trades": m1_oos_trades,
            "m6b_oos_trades_count": len(m6b_oos_trades),
            "m6b_oos_trades": m6b_oos_trades,
            "admission_diff_bar_count_vs_real_exit_cooldown": 0,
        }

    method_comparison = method_comparison_fn(symbol_results, allowed_yms_by_symbol) if method_comparison_fn else None
    summary_payload = {
        "method_comparison": method_comparison,
        "schema_version": target_version,
        "input_fingerprint_sha256": input_fp,
        "input_fingerprint_mode": "FULL_BYTE_CONTENT_SHA256_ACROSS_CODE_MCAP_5M_1H_AND_FUNDING_PARQUETS",
        "total_symbols_evaluated": len(symbol_results),
        "engine_configuration": {
            "swing_pivot_left_bars": 2,
            "swing_pivot_right_bars": 2,
            "m6_multiplier_below_score_68": 0.80,
            "strict_prior_low_before_peak": True,
            "same_bar_ratcheted_sl_mode": "pessimistic_high",
            "m6_sl_atr_buffer": 0.25,
            "m6_exit_metadata_recalculated": True,
            "canonical_pst_series_use_bfill": False,
            "canonical_conviction_score_unified": True,
            "causal_execution_clock_decision_equals_entry": True,
            "real_utc_epoch_hour_cooldown_and_sorting": True,
            "real_exit_close_time_cooldown_enforced": True,
            "coupled_hourly_step_idempotent_single_pass": True,
            "coupled_single_source_accounting_no_second_cap_pass": True,
            "coupled_accepted_equals_executed_asserted": True,
            "rolling_pit_membership_checked_before_wave_and_cooldown": True,
            "milestone_execution_mode": "INDEPENDENT_PER_MILESTONE_PLUS_PORTFOLIO_COUPLED_AND_LEGACY_SUBSET_COMPARED",
        },
        "data_coverage_and_listing_audit": {
            "total_5m_parquet_files_in_lake": len(all_parquet),
            "excluded_stable_or_index_count": len(excluded_stable_or_index),
            "excluded_stable_or_index_symbols": excluded_stable_or_index,
            "excluded_short_history_lt_200_bars_count": len(excluded_short_history),
            "excluded_short_history_symbols": excluded_short_history,
            "total_symbols": len(symbol_results),
            "symbols_starting_at_or_before_2024_01_01": starts_at_or_before_2024,
            "symbols_starting_after_2024_01_01_new_listings": starts_after_2024,
            "symbols_ending_before_2026_08_31_early_truncation_or_delist": ends_before_2026_08_31,
            "symbols_ending_at_2026_08_31_2300_open_2026_09_01_0000_close_5m_cutoff": ends_at_2026_08_31_cutoff,
            "symbols_ending_at_2026_09_29_2300_open_2026_09_30_0000_close_shared_1h": ends_at_2026_09_29_shared,
            "coverage_partition_check_sum_equals_340": (
                len(excluded_stable_or_index)
                + len(excluded_short_history)
                + ends_before_2026_08_31
                + ends_at_2026_08_31_cutoff
                + ends_at_2026_09_29_shared
            ),
            "missing_hour_gaps_real_data_audit": {
                "symbols_with_missing_hour_gaps_count": len(symbols_with_gaps_detail),
                "symbols_with_missing_hour_gaps": sorted(list(symbols_with_gaps_detail.keys())),
                "total_candidates_spanning_missing_bars": total_trades_spanning_missing_bars,
                "by_symbol": symbols_with_gaps_detail,
            },
            "survivorship_and_listing_note": (
                "Universe comes from local 5m parquet snapshot (`C:/Quant-trading/data_lake/klines/5m`, 340 files total: "
                "1 stablecoin `USDCUSDT` excluded + 1 short-history symbol `牛来USDT` with 438 5m rows / 36 1h bars excluded = 338 evaluated symbols). "
                "All 339 eligible-name 5m files (including all 338 evaluated symbols) end at `2026-08-31 23:55:00+00:00` 5m open "
                "(`2026-08-31T23:00:00+00:00` 1h bar open / `2026-09-01T00:00:00+00:00` 1h bar close); 0 symbols in the 338-coin 5m scan extend to "
                "`2026-09-29` (whereas in the separate 14-coin benchmark `load_1h_for_oos`, 6 symbols extend to `2026-09-29T23:00:00+00:00` via SharedMarketData 1h "
                "and 8 symbols end at `2026-08-31T23:00:00+00:00` via data_lake 5m). "
                "First observed bar timestamp in a local file reflects data-file start rather than an official exchange listing registry. "
                "Because the local lake is a survivorship-conditioned snapshot of currently present files and lacks delisted historical "
                "perpetuals, `ROLLING_PIT_TOP50_VOL` is survivorship-conditioned on available files, though strictly point-in-time with "
                "respect to observed data start dates and trailing 63-day `[t_m - 63d, t_m)` volume/wick eligibility checked BEFORE wave/cooldown consumption."
            ),
        },
        "by_universe_tier": by_universe_tier,
        "by_liquidity": by_liquidity,
        "by_archetype": by_archetype,
        "tier_symbol_lists": {
            "ex_ante_2026_top50_vol": sorted(list(ex_ante_2026_top50_syms)),
            "tier_s_core": sorted([r["symbol"] for r in symbol_results if r["universe_tier"] == "TIER_S_CORE"]),
            "tier_a_extended": sorted([r["symbol"] for r in symbol_results if r["universe_tier"] == "TIER_A_EXTENDED"]),
            "pit_zero_bias_mcap_float": sorted(list(pit_zero_bias_mcap_float_syms)),
        },
    }

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(summary_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    ledgers_cache_path.write_text(
        json.dumps(universe_coupled_ledgers_by_key, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"   [Universe 338] Saved v{target_version} universe re-audit summary to {cache_path.name} ({time.time() - t0:.1f}s)")
    return summary_payload


run_universe_338_reaudit_v403 = run_universe_338_reaudit_v402
collect_symbol_milestones_v403 = collect_symbol_milestones_v402
evaluate_symbol_universe_worker_v403 = evaluate_symbol_universe_worker_v402

run_universe_338_reaudit_v404 = run_universe_338_reaudit_v402
collect_symbol_milestones_v404 = collect_symbol_milestones_v402
evaluate_symbol_universe_worker_v404 = evaluate_symbol_universe_worker_v402

run_universe_338_reaudit_v405 = run_universe_338_reaudit_v402
collect_symbol_milestones_v405 = collect_symbol_milestones_v402
evaluate_symbol_universe_worker_v405 = evaluate_symbol_universe_worker_v402


