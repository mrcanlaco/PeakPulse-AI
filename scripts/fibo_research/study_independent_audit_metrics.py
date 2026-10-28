"""Comprehensive Independent Audit Metrics Generator (2020-2025 IS & 2026 OOS).

Generates all quantitative audit tables required by an independent AI Red-Team Auditor (e.g., ChatGPT o1/o3/GPT-4o):
1. Fee & Slippage Sensitivity Stress Test (0, 10, 20, 30, 40 bps round-trip + Break-even bps).
2. Trade Outcome & Tail-Risk Distribution (% TP1/TP2/TP3/SL/TimeExit, AvgWin, AvgLoss, Payoff, Median, Skew, Max Losing Streak, Hold Hours).
3. Portfolio Concurrency & Chronological Time-Aligned Equity Drawdown vs Sequential Drawdown.
4. Cross-Asset (14 Symbols) & Cross-Timeframe (H4 vs D1) Breakdown across locked milestones (Mốc 1, Mốc 4A, Mốc 6B, Mốc 6A, Mốc 6S).
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRATCH_DIR = Path(__file__).resolve().parent
if str(SCRATCH_DIR) not in sys.path:
    sys.path.insert(0, str(SCRATCH_DIR))

from study_factor1_multi_repo_benchmark_2025 import calc_multi_repo_htf_features
from study_factor2_3_4_complete_2025 import simulate_custom_trade
from study_insample_2020_2025_by_year import collect_2020_2025_trades
from study_oos_2026_all_7_milestones import collect_oos_trades, load_1h_for_oos
from dao_vang.fibo_short.backtest import (
    FiboBacktestTrade,
    load_historical_1h_frame,
    resample_1h_to_htf,
    summarize_trades,
)


def compute_detailed_audit_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute deep distribution, tail risk, concurrency, and fee sensitivity for a milestone item list."""
    n = len(items)
    if n == 0:
        return {
            "total_trades": 0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "avg_net_return_pct": 0.0,
            "total_net_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "chronological_max_dd_pct": 0.0,
            "outcomes": {},
            "distribution": {},
            "concurrency": {},
            "fee_stress_test": {},
        }

    trades: list[FiboBacktestTrade] = [x["trade"] for x in items]
    base_summary = summarize_trades(trades)

    # Sort chronologically by entry_time for true portfolio-level drawdown and streak analysis
    chrono_items = sorted(items, key=lambda x: str(x["trade"].entry_time))
    chrono_trades = [x["trade"] for x in chrono_items]

    # Chronological drawdown
    c_eq = 0.0
    c_peak = 0.0
    c_max_dd = 0.0
    for t in chrono_trades:
        c_eq += t.net_return_pct
        if c_eq > c_peak:
            c_peak = c_eq
        dd = c_peak - c_eq
        if dd > c_max_dd:
            c_max_dd = dd

    # Outcome counts
    tp3_cnt = sum(1 for t in trades if t.outcome == "TP3_HIT")
    tp2_cnt = sum(1 for t in trades if t.outcome == "TP2_HIT")
    tp1_cnt = sum(1 for t in trades if t.outcome == "TP1_HIT")
    sl_cnt = sum(1 for t in trades if t.outcome == "STOP_LOSS")
    te_cnt = sum(1 for t in trades if t.outcome == "TIME_EXIT")

    # Returns array
    net_arr = np.array([t.net_return_pct for t in chrono_trades], dtype=float)
    wins = net_arr[net_arr > 0]
    losses = net_arr[net_arr <= 0]

    avg_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
    avg_loss = float(np.mean(losses)) if len(losses) > 0 else 0.0
    payoff_ratio = abs(avg_win / avg_loss) if abs(avg_loss) > 1e-9 else 99.9
    median_net = float(np.median(net_arr))
    std_net = float(np.std(net_arr))
    best_trade = float(np.max(net_arr))
    worst_trade = float(np.min(net_arr))

    # Skewness
    if std_net > 1e-9 and n >= 3:
        skew = float(np.mean(((net_arr - np.mean(net_arr)) / std_net) ** 3))
    else:
        skew = 0.0

    # Consecutive wins / losses (Chronological)
    max_win_streak = 0
    max_loss_streak = 0
    max_loss_streak_pct = 0.0
    cur_w = 0
    cur_l = 0
    cur_l_pct = 0.0
    for val in net_arr:
        if val > 0:
            cur_w += 1
            if cur_w > max_win_streak:
                max_win_streak = cur_w
            cur_l = 0
            cur_l_pct = 0.0
        else:
            cur_l += 1
            cur_l_pct += float(val)
            if cur_l > max_loss_streak:
                max_loss_streak = cur_l
            if abs(cur_l_pct) > max_loss_streak_pct:
                max_loss_streak_pct = abs(cur_l_pct)
            cur_w = 0

    hold_arr = np.array([t.hold_hours for t in trades], dtype=float)
    avg_hold_h = float(np.mean(hold_arr))
    med_hold_h = float(np.median(hold_arr))

    # Concurrency analysis using interval events
    events: list[tuple[pd.Timestamp, int, str]] = []
    for t in chrono_trades:
        t_in = pd.Timestamp(t.entry_time)
        t_out = pd.Timestamp(t.exit_time) if t.exit_time else (t_in + pd.Timedelta(hours=max(1, t.hold_hours)))
        if t_out <= t_in:
            t_out = t_in + pd.Timedelta(hours=max(1, t.hold_hours))
        events.append((t_in, +1, t.symbol))
        events.append((t_out, -1, t.symbol))

    # Sort events by timestamp; process exits (-1) before entries (+1) at identical timestamp
    events.sort(key=lambda e: (e[0], e[1]))
    active_count = 0
    max_concurrent = 0
    active_samples: list[int] = []
    for _, delta, _ in events:
        active_count += delta
        if active_count > max_concurrent:
            max_concurrent = active_count
        if delta == +1:
            active_samples.append(active_count)

    avg_concurrent = float(np.mean(active_samples)) if active_samples else 1.0
    p95_concurrent = float(np.percentile(active_samples, 95)) if active_samples else 1.0

    # Fee & Slippage Stress Test (0, 10, 20, 30, 40 bps round-trip)
    # Note: each item stores raw_gross_pct (unscaled gross %) and pos_mult (1.0 or conviction multiplier)
    raw_gross = np.array([float(x.get("raw_gross_pct", x["trade"].gross_return_pct)) for x in chrono_items], dtype=float)
    pos_mult = np.array([float(x.get("pos_mult", 1.0)) for x in chrono_items], dtype=float)

    fee_stress: dict[str, Any] = {}
    for bps in (0, 10, 20, 30, 40):
        cost_pct = bps / 100.0
        adj_net = (raw_gross - cost_pct) * pos_mult
        w_cnt = int(np.sum(adj_net > 0))
        wr = (w_cnt / n) * 100.0
        g_profit = float(np.sum(adj_net[adj_net > 0]))
        g_loss = abs(float(np.sum(adj_net[adj_net <= 0])))
        pf = g_profit / g_loss if g_loss > 1e-9 else (99.9 if g_profit > 0 else 0.0)
        tot_net = float(np.sum(adj_net))
        avg_net = float(np.mean(adj_net))

        # Chronological DD at this fee level
        eq = 0.0
        pk = 0.0
        mdd = 0.0
        for v in adj_net:
            eq += float(v)
            if eq > pk:
                pk = eq
            if pk - eq > mdd:
                mdd = pk - eq

        fee_stress[f"{bps}_bps"] = {
            "fee_bps": bps,
            "fee_pct": round(cost_pct, 3),
            "win_rate_pct": round(wr, 2),
            "avg_net_pct": round(avg_net, 3),
            "total_net_pct": round(tot_net, 2),
            "profit_factor": round(pf, 2),
            "chrono_max_dd_pct": round(mdd, 1),
        }

    # Break-even round-trip fee in bps: where sum((raw_gross - fee_pct) * pos_mult) == 0
    denom = float(np.sum(pos_mult))
    breakeven_pct = float(np.sum(raw_gross * pos_mult)) / denom if denom > 1e-9 else 0.0
    breakeven_bps = round(breakeven_pct * 100.0, 1)

    return {
        **base_summary,
        "chronological_max_dd_pct": round(c_max_dd, 2),
        "outcomes": {
            "tp3_hit_count": tp3_cnt,
            "tp3_hit_pct": round(tp3_cnt / n * 100.0, 2),
            "tp2_hit_count": tp2_cnt,
            "tp2_hit_pct": round(tp2_cnt / n * 100.0, 2),
            "tp1_breakeven_count": tp1_cnt,
            "tp1_breakeven_pct": round(tp1_cnt / n * 100.0, 2),
            "stop_loss_count": sl_cnt,
            "stop_loss_pct": round(sl_cnt / n * 100.0, 2),
            "time_exit_count": te_cnt,
            "time_exit_pct": round(te_cnt / n * 100.0, 2),
        },
        "distribution": {
            "avg_win_pct": round(avg_win, 3),
            "avg_loss_pct": round(avg_loss, 3),
            "payoff_ratio": round(payoff_ratio, 2),
            "median_net_pct": round(median_net, 3),
            "std_net_pct": round(std_net, 3),
            "skewness": round(skew, 2),
            "best_trade_pct": round(best_trade, 2),
            "worst_trade_pct": round(worst_trade, 2),
            "max_consecutive_wins": max_win_streak,
            "max_consecutive_losses": max_loss_streak,
            "max_losing_streak_cum_pct": round(max_loss_streak_pct, 2),
            "avg_hold_hours": round(avg_hold_h, 1),
            "median_hold_hours": round(med_hold_h, 1),
        },
        "concurrency": {
            "max_concurrent_trades": max_concurrent,
            "avg_concurrent_when_active": round(avg_concurrent, 2),
            "p95_concurrent_trades": round(p95_concurrent, 1),
        },
        "fee_stress_test": fee_stress,
        "breakeven_fee_bps": breakeven_bps,
    }


def compute_cross_section_breakdown(
    items: list[dict[str, Any]],
    all_symbols: list[str],
) -> dict[str, Any]:
    """Compute per-symbol and per-timeframe (H4 vs D1) breakdown for a milestone."""
    by_tf: dict[str, Any] = {}
    for tf in ("4h", "1d"):
        tf_items = [x for x in items if x["tf"] == tf]
        by_tf[tf] = compute_detailed_audit_stats(tf_items)

    by_symbol: dict[str, Any] = {}
    profitable_syms = 0
    active_syms = 0
    sym_profits: list[tuple[str, float]] = []

    for sym in all_symbols:
        s_items = [x for x in items if x["symbol"] == sym]
        st = summarize_trades([x["trade"] for x in s_items])
        by_symbol[sym] = st
        if st["total_trades"] > 0:
            active_syms += 1
            if st["total_net_return_pct"] > 0:
                profitable_syms += 1
            sym_profits.append((sym, st["total_net_return_pct"]))

    total_pos_profit = sum(max(0.0, p) for _, p in sym_profits)
    sym_profits.sort(key=lambda kv: kv[1], reverse=True)
    top1_sym = sym_profits[0][0] if sym_profits else "N/A"
    top1_share_pct = (
        round(max(0.0, sym_profits[0][1]) / total_pos_profit * 100.0, 1)
        if sym_profits and total_pos_profit > 1e-9
        else 0.0
    )

    return {
        "by_timeframe": by_tf,
        "by_symbol": by_symbol,
        "active_symbols_count": active_syms,
        "profitable_symbols_count": profitable_syms,
        "profitable_symbols_ratio_pct": round(profitable_syms / max(1, active_syms) * 100.0, 1),
        "top1_symbol": top1_sym,
        "top1_positive_pnl_share_pct": top1_share_pct,
    }


def build_milestones_from_m1(m1_items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Build Mốc 1 -> Mốc 6S enriched lists with raw_gross_pct and pos_mult attached."""
    prepared_m1 = []
    for x in m1_items:
        t0: FiboBacktestTrade = x["trade"]
        prepared_m1.append({**x, "raw_gross_pct": t0.gross_return_pct, "pos_mult": 1.0, "default_fee_bps": 10})

    m2_f1b = [x for x in prepared_m1 if x["pst_pass"]]
    m3_f1_exp = [x for x in prepared_m1 if x["f1_expanded"]]
    m3_f1_eli = [x for x in prepared_m1 if x["f1_elite"]]
    m4_f2_exp = [x for x in m3_f1_exp if x["imp_drop_pct"] >= 6.0 and x["imp_ker"] >= 0.50]
    m4_f2_eli = [x for x in m3_f1_eli if x["imp_drop_pct"] >= 6.0 and x["imp_ker"] >= 0.50]
    m5_f3_exp = [x for x in m4_f2_exp if x["cond2_break"] and x["max_fibo_ratio"] <= 0.786]
    m5_f3_eli = [x for x in m4_f2_eli if x["cond2_break"] and x["max_fibo_ratio"] <= 0.786]

    m6_f4_exp = []
    for x in m4_f2_exp:
        t0 = x["trade"]
        fibo = x["fibo_levels"]
        atr = x["atr_1h"]
        ep = t0.entry_price
        lvl_0886 = fibo.level_0000 + 0.886 * fibo.wave_range
        sl_price = max(lvl_0886, ep * 1.005) + 0.25 * atr
        out, g_pct, n_pct, r_m, tp1_h, tp2_h, tp3_h, ex_p, ex_t, hold_h = simulate_custom_trade(
            x["future_slice"],
            entry_price=ep,
            stop_loss=sl_price,
            tp1=t0.tp1,
            tp2=t0.tp2,
            tp3=t0.tp3,
            return_exit_meta=True,
        )
        sc = x["full_conviction_score"]
        mult = 1.50 if sc >= 80 else (1.15 if sc >= 68 else 0.80)
        t_m6 = replace(
            t0,
            stop_loss=sl_price,
            exit_price=round(ex_p, 8),
            exit_time=ex_t,
            hold_hours=hold_h,
            outcome=out,  # type: ignore[arg-type]
            gross_return_pct=round(g_pct * mult, 4),
            net_return_pct=round(n_pct * mult, 4),
            r_multiple=round(r_m * mult, 4),
            tp1_reached=tp1_h,
            tp2_reached=tp2_h,
            tp3_reached=tp3_h,
        )
        m6_f4_exp.append(
            {
                **x,
                "trade": t_m6,
                "raw_gross_pct": g_pct,
                "pos_mult": mult,
                "default_fee_bps": 20,
            }
        )

    m6_f4_sniper = [x for x in m6_f4_exp if x["cond2_break"] and x["max_fibo_ratio"] <= 0.786]
    m6_f4_elite_sniper = [
        x for x in m6_f4_exp if x["f1_elite"] and x["cond2_break"] and x["max_fibo_ratio"] <= 0.786
    ]

    return {
        "m1_f1a_pump50": prepared_m1,
        "m2_f1b_pst": m2_f1b,
        "m3_f1c_expanded": m3_f1_exp,
        "m3_f1c_elite": m3_f1_eli,
        "m4_f2_expanded": m4_f2_exp,
        "m4_f2_elite": m4_f2_eli,
        "m5_f3_expanded": m5_f3_exp,
        "m5_f3_elite": m5_f3_eli,
        "m6_f4_expanded": m6_f4_exp,
        "m6_f4_sniper": m6_f4_sniper,
        "m6_f4_elite_sniper": m6_f4_elite_sniper,
    }


def main() -> None:
    default_syms = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "LTCUSDT", "BCHUSDT"]
    alt_syms = [
        "1000PEPEUSDT",
        "1000BONKUSDT",
        "1000SHIBUSDT",
        "AAVEUSDT",
        "ADAUSDT",
        "1INCHUSDT",
        "ACEUSDT",
        "AKTUSDT",
    ]
    symbols = default_syms + alt_syms

    print("1. Loading 2020-2025 In-Sample 1h frames...")
    is_frames: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        try:
            df = load_historical_1h_frame(
                sym,
                start_utc="2020-01-01T00:00:00+00:00",
                end_utc="2025-12-31T23:59:59+00:00",
                strict_in_sample=True,
            )
            if not df.empty:
                is_frames[sym] = df
        except Exception as e:
            print(f"   Skip IS {sym}: {e}")

    btc_is = is_frames["BTCUSDT"].sort_index()
    btc_htf_is = {
        tf: calc_multi_repo_htf_features(resample_1h_to_htf(btc_is, tf))
        for tf in ("4h", "1d")
    }

    print("2. Collecting 2020-2025 Mốc 1..6S trades...")
    m1_is_all = collect_2020_2025_trades(is_frames, btc_htf_is, min_pump=0.50)
    m1_is_2425 = [x for x in m1_is_all if 2024 <= x["year"] <= 2025]

    milestones_is_2020_2025 = build_milestones_from_m1(m1_is_all)
    milestones_is_2024_2025 = build_milestones_from_m1(m1_is_2425)

    print("3. Loading 2026 OOS 1h frames...")
    oos_frames: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        try:
            df = load_1h_for_oos(sym)
            if not df.empty:
                oos_frames[sym] = df
        except Exception as e:
            print(f"   Skip OOS {sym}: {e}")

    btc_oos = oos_frames["BTCUSDT"].sort_index()
    btc_htf_oos = {
        tf: calc_multi_repo_htf_features(resample_1h_to_htf(btc_oos, tf))
        for tf in ("4h", "1d")
    }
    print("4. Collecting 2026 OOS Mốc 1..6S trades...")
    m1_oos = collect_oos_trades(oos_frames, btc_htf_oos, min_pump=0.50)
    milestones_oos_2026 = build_milestones_from_m1(m1_oos)

    # Compute comprehensive audit statistics for each horizon
    audit_is_2020_2025 = {
        k: compute_detailed_audit_stats(v) for k, v in milestones_is_2020_2025.items()
    }
    audit_is_2024_2025 = {
        k: compute_detailed_audit_stats(v) for k, v in milestones_is_2024_2025.items()
    }
    audit_oos_2026 = {
        k: compute_detailed_audit_stats(v) for k, v in milestones_oos_2026.items()
    }

    # Cross-Asset (14 symbols) & Cross-Timeframe (H4 vs D1) breakdown for key milestones
    key_cross_milestones = [
        "m1_f1a_pump50",
        "m3_f1c_elite",
        "m4_f2_elite",
        "m6_f4_expanded",
        "m6_f4_sniper",
        "m6_f4_elite_sniper",
    ]
    cross_section = {
        "is_2020_2025": {
            k: compute_cross_section_breakdown(milestones_is_2020_2025[k], symbols)
            for k in key_cross_milestones
        },
        "is_2024_2025": {
            k: compute_cross_section_breakdown(milestones_is_2024_2025[k], symbols)
            for k in key_cross_milestones
        },
        "oos_2026": {
            k: compute_cross_section_breakdown(milestones_oos_2026[k], symbols)
            for k in key_cross_milestones
        },
    }

    out_data = {
        "metadata": {
            "generated_for": "Independent Quantitative Red-Team Audit (ChatGPT o1/o3/GPT-4o)",
            "horizons": {
                "is_2020_2025": "Full 6-Year Multi-Cycle In-Sample (2020-01-01 -> 2025-12-31)",
                "is_2024_2025": "2-Year Calibration In-Sample (2024-01-01 -> 2025-12-31)",
                "oos_2026": "True Forward Out-of-Sample (2026-01-01 -> 2026-09-29)",
            },
            "fee_accounting_note": (
                "Default reported Net PnL deducts 10 bps (0.10%) round-trip on Mốc 0..5 "
                "and 20 bps (0.20%) round-trip on Mốc 6A/6B/6S. Full 0..40 bps stress test included."
            ),
        },
        "audit_is_2020_2025": audit_is_2020_2025,
        "audit_is_2024_2025": audit_is_2024_2025,
        "audit_oos_2026": audit_oos_2026,
        "cross_section": cross_section,
    }

    out_path = Path(__file__).resolve().parents[2] / "artifacts/fibo_trend_short/independent_audit_study.json"
    out_path.write_text(json.dumps(out_data, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n================ AUDIT METRICS SUMMARY (2020-2025 IS) ================")
    for k, st in audit_is_2020_2025.items():
        d = st["distribution"]
        c = st["concurrency"]
        o = st["outcomes"]
        print(
            f"{k:20s}: N={st['total_trades']:4d} | WR={st['win_rate_pct']:5.2f}% | PF={st['profit_factor']:4.2f} | "
            f"SeqDD={st['max_drawdown_pct']:5.1f}% | ChronoDD={st['chronological_max_dd_pct']:5.1f}% | "
            f"Payoff={d['payoff_ratio']:4.2f} | MaxLStreak={d['max_consecutive_losses']:2d} | "
            f"MaxConc={c['max_concurrent_trades']:2d} | BE_Fee={st['breakeven_fee_bps']:5.1f}bps | "
            f"TP3/2/1/SL/TE={o['tp3_hit_pct']:.0f}/{o['tp2_hit_pct']:.0f}/{o['tp1_breakeven_pct']:.0f}/{o['stop_loss_pct']:.0f}/{o['time_exit_pct']:.0f}%"
        )

    print("\n================ AUDIT METRICS SUMMARY (2026 OOS) ================")
    for k, st in audit_oos_2026.items():
        d = st["distribution"]
        c = st["concurrency"]
        o = st["outcomes"]
        print(
            f"{k:20s}: N={st['total_trades']:4d} | WR={st['win_rate_pct']:5.2f}% | PF={st['profit_factor']:4.2f} | "
            f"SeqDD={st['max_drawdown_pct']:5.1f}% | ChronoDD={st['chronological_max_dd_pct']:5.1f}% | "
            f"Payoff={d['payoff_ratio']:4.2f} | MaxLStreak={d['max_consecutive_losses']:2d} | "
            f"MaxConc={c['max_concurrent_trades']:2d} | BE_Fee={st['breakeven_fee_bps']:5.1f}bps | "
            f"TP3/2/1/SL/TE={o['tp3_hit_pct']:.0f}/{o['tp2_hit_pct']:.0f}/{o['tp1_breakeven_pct']:.0f}/{o['stop_loss_pct']:.0f}/{o['time_exit_pct']:.0f}%"
        )

    print(f"\nSaved independent audit metrics to: {out_path}")


if __name__ == "__main__":
    main()
