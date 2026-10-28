"""Out-of-Sample (OOS 2026: 2026-01-01 -> 2026-09-29) Validation of all 7 Milestone Configurations
(Mốc 0 -> Mốc 1 -> Mốc 2 -> Mốc 3 -> Mốc 4 -> Mốc 5 -> Mốc 6) with ZERO parameter changes.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from study_factor1_multi_repo_benchmark_2025 import calc_multi_repo_htf_features
from study_factor2_3_4_complete_2025 import simulate_custom_trade
from dao_vang.config.settings import FiboTrendShortConfig
from dao_vang.fibo_short.backtest import (
    DATA_LAKE_5M_DIR,
    OOS_START_UTC,
    SHARED_1H_DIR,
    FiboBacktestTrade,
    _simulate_trade_outcome,
    resample_1h_to_htf,
    summarize_trades,
)
from dao_vang.fibo_short.detector import evaluate_symbol_timeframe


def load_1h_for_oos(
    symbol: str,
    warmup_start_utc: str = "2025-09-01T00:00:00+00:00",
    end_utc: str = "2026-10-01T00:00:00+00:00",
) -> pd.DataFrame:
    """Load 1h OHLCV including late-2025 warmup so 2026 indicators have full lookback."""
    start_ts = pd.Timestamp(warmup_start_utc)
    end_ts = pd.Timestamp(end_utc)

    p_1h = SHARED_1H_DIR / f"{symbol}_1h.parquet"
    if p_1h.exists():
        df = pd.read_parquet(p_1h)
        if not isinstance(df.index, pd.DatetimeIndex):
            time_col = "open_time" if "open_time" in df.columns else "timestamp"
            df[time_col] = pd.to_datetime(df[time_col], utc=True)
            df = df.set_index(time_col)
        else:
            df.index = pd.to_datetime(df.index, utc=True)
        df = df.sort_index()
        df = df.loc[(df.index >= start_ts) & (df.index <= end_ts)].copy()
        return df[["open", "high", "low", "close", "volume"]].astype(float)

    p_5m = DATA_LAKE_5M_DIR / f"{symbol}.parquet"
    if p_5m.exists():
        df5 = pd.read_parquet(
            p_5m,
            columns=["open_time", "open", "high", "low", "close", "volume"],
        )
        df5["open_time"] = pd.to_datetime(df5["open_time"], utc=True)
        df5 = df5[(df5["open_time"] >= start_ts) & (df5["open_time"] <= end_ts)]
        df5 = df5.set_index("open_time").sort_index()
        if df5.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        g = df5.resample("1h", label="left", closed="left")
        df1h = pd.DataFrame(
            {
                "open": g["open"].first(),
                "high": g["high"].max(),
                "low": g["low"].min(),
                "close": g["close"].last(),
                "volume": g["volume"].sum(),
                "n5": g["open"].count(),
            }
        )
        df1h = df1h[df1h["n5"] == 12].drop(columns=["n5"]).dropna()
        return df1h.astype(float)

    raise FileNotFoundError(f"Historical data not found for {symbol}")


def collect_oos_trades(
    frames: dict[str, pd.DataFrame],
    btc_htf: dict[str, pd.DataFrame],
    min_pump: float = 0.50,
) -> list[dict[str, Any]]:
    cfg = FiboTrendShortConfig(
        min_prior_pump_pct=min_pump,
        min_impulse_drop_pct=0.04,
        fibo_entry_min=0.500,
        fibo_entry_max=0.618,
        sl_mode="above_swing_high",
        require_both_h1_conditions=False,
    )

    enriched: list[dict[str, Any]] = []

    for symbol, df in frames.items():
        df = df.sort_index()
        if len(df) < 100:
            continue

        h1_records: list[dict[str, Any]] = []
        h1_close_times: list[pd.Timestamp] = []
        for open_ts, row in df.iterrows():
            close_ts = open_ts + pd.Timedelta(hours=1)
            h1_close_times.append(close_ts)
            h1_records.append(
                {
                    "open_time": int(open_ts.timestamp() * 1000),
                    "open_time_str": open_ts.isoformat(),
                    "close_time_ts": close_ts,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0.0)),
                }
            )

        for tf in ("4h", "1d"):
            htf_df = resample_1h_to_htf(df, tf)
            if len(htf_df) < 30:
                continue
            htf_df = calc_multi_repo_htf_features(htf_df)

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
            cooldown_until_idx = -1
            consumed_waves: set[str] = set()
            horizon = cfg.horizon_hours if tf == "4h" else max(cfg.horizon_hours, 120)

            for idx_1h in range(24, len(h1_records) - 2):
                if idx_1h < cooldown_until_idx:
                    continue

                current_decision_ts = h1_close_times[idx_1h]
                while htf_ptr < n_htf and htf_close_times[htf_ptr] <= current_decision_ts:
                    htf_ptr += 1

                # Strictly evaluate only decisions inside OOS (>= 2026-01-01 00:00:00 UTC)
                if pd.Timestamp(h1_records[idx_1h]["open_time_str"]) < OOS_START_UTC:
                    continue

                if htf_ptr < 10:
                    continue

                start_htf = max(0, htf_ptr - cfg.swing_lookback_bars - 24)
                visible_htf = htf_records[start_htf:htf_ptr]
                visible_1h = h1_records[max(0, idx_1h - 24) : idx_1h + 1]

                sig = evaluate_symbol_timeframe(
                    symbol=symbol,
                    timeframe=tf,
                    klines_htf=visible_htf,
                    klines_1h=visible_1h,
                    config=cfg,
                )
                if sig is None or sig.stage != "FIRED_CONFIRMED_SHORT" or sig.trade_setup is None:
                    continue

                wave_key = f"{tf}:{sig.wave.swing_high_time}:{sig.wave.impulse_low_time}"
                if wave_key in consumed_waves:
                    continue

                future_slice = h1_records[idx_1h + 1 : min(len(h1_records), idx_1h + 1 + horizon)]
                if not future_slice:
                    continue

                setup = sig.trade_setup
                (
                    outcome,
                    exit_price,
                    exit_time,
                    hold_hours,
                    tp1_hit,
                    tp2_hit,
                    tp3_hit,
                    gross_pct,
                    net_pct,
                    r_mult,
                ) = _simulate_trade_outcome(
                    future_slice,
                    entry_price=setup.entry_price,
                    stop_loss=setup.stop_loss,
                    tp1=setup.tp1,
                    tp2=setup.tp2,
                    tp3=setup.tp3,
                )

                consumed_waves.add(wave_key)
                cooldown_until_idx = idx_1h + max(4, hold_hours)

                trade_obj = FiboBacktestTrade(
                    trade_id=f"{sig.id}_{idx_1h}",
                    symbol=symbol,
                    higher_timeframe=tf,
                    confirmation_tier=sig.h1_confirmation.confirmation_tier,
                    pattern_name=sig.h1_confirmation.pattern_name,
                    entry_time=sig.signal_time,
                    exit_time=exit_time,
                    entry_price=setup.entry_price,
                    stop_loss=setup.stop_loss,
                    tp1=setup.tp1,
                    tp2=setup.tp2,
                    tp3=setup.tp3,
                    exit_price=exit_price,
                    outcome=outcome,
                    tp1_reached=tp1_hit,
                    tp2_reached=tp2_hit,
                    tp3_reached=tp3_hit,
                    gross_return_pct=round(gross_pct, 4),
                    net_return_pct=round(net_pct, 4),
                    r_multiple=round(r_mult, 4),
                    hold_hours=hold_hours,
                    fibo_entry_ratio=sig.h1_confirmation.current_fibo_ratio,
                    impulse_drop_pct=sig.wave.impulse_drop_pct,
                    prior_pump_pct=sig.wave.prior_pump_pct,
                )

                if min_pump < 0.40:
                    enriched.append({"trade": trade_obj, "symbol": symbol, "tf": tf})
                    continue

                peak_bar = htf_by_open_str.get(sig.wave.swing_high_time)
                low_bar = htf_by_open_str.get(sig.wave.prior_low_time)
                imp_bar = htf_by_open_str.get(sig.wave.impulse_low_time)
                cur_htf_bar = visible_htf[-1]
                if peak_bar is None or low_bar is None or imp_bar is None:
                    continue

                p_idx = peak_bar["htf_idx"]
                l_idx = low_bar["htf_idx"]
                imp_idx = imp_bar["htf_idx"]

                wave_bars = htf_records[l_idx : p_idx + 1]
                if len(wave_bars) >= 2:
                    closes_w = np.array([b["close"] for b in wave_bars], dtype=float)
                    net_chg = abs(closes_w[-1] - closes_w[0])
                    path_chg = float(np.sum(np.abs(np.diff(closes_w))))
                    ker_wave = net_chg / path_chg if path_chg > 1e-9 else 1.0
                else:
                    ker_wave = 1.0

                pst_pass = (peak_bar["ewmac_16_64"] <= 0.0) or (cur_htf_bar["accel_4_16"] <= -1.0)
                f1_elite = pst_pass and (ker_wave >= 0.35)
                f1_expanded = f1_elite or (ker_wave >= 0.65)

                swing_high = sig.wave.swing_high_price
                impulse_low = sig.wave.impulse_low_price
                impulse_range = max(0.0, swing_high - impulse_low)
                imp_drop_pct = (impulse_range / swing_high) * 100.0
                imp_slice = htf_records[p_idx : imp_idx + 1]
                if len(imp_slice) >= 2:
                    closes_imp = np.array([b["close"] for b in imp_slice], dtype=float)
                    net_imp = abs(closes_imp[-1] - closes_imp[0])
                    path_imp = float(np.sum(np.abs(np.diff(closes_imp))))
                    imp_ker = net_imp / path_imp if path_imp > 1e-9 else 1.0
                else:
                    imp_ker = 1.0

                recent_1h = visible_1h[-16:]
                min_1h_idx = min(range(len(recent_1h)), key=lambda i: float(recent_1h[i]["low"]))
                pb_1h_leg = recent_1h[min_1h_idx + 1 :] or [recent_1h[-1]]
                drop_1h_leg = recent_1h[: min_1h_idx + 1] or [recent_1h[0]]
                pb_1h_vol = float(np.mean([b["volume"] for b in pb_1h_leg]))
                drop_1h_vol = float(np.mean([b["volume"] for b in drop_1h_leg]))
                pullback_vol_ratio_1h = pb_1h_vol / max(1e-9, drop_1h_vol)

                bdf = btc_htf[tf]
                entry_ts = pd.Timestamp(trade_obj.entry_time)
                past_btc = bdf.loc[pd.to_datetime(bdf["close_time"]) <= entry_ts]
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

                raw_pump_pct = sig.wave.prior_pump_pct * 100.0 if sig.wave.prior_pump_pct < 10.0 else sig.wave.prior_pump_pct
                idiosyncratic_spread = raw_pump_pct - max(0.0, btc_ret_pct)

                # Compute locked 0-100 Conviction Score
                score = 0.0
                if raw_pump_pct >= 100.0:
                    score += 15.0
                elif raw_pump_pct >= 70.0:
                    score += 11.0
                else:
                    score += 7.0

                if ker_wave >= 0.65:
                    score += 20.0
                elif ker_wave >= 0.35:
                    score += 14.0

                if imp_ker >= 0.65 and imp_drop_pct >= 6.0:
                    score += 15.0
                elif imp_ker >= 0.50 and imp_drop_pct >= 6.0:
                    score += 10.0

                if peak_bar["ewmac_16_64"] <= 0.0 and cur_htf_bar["accel_4_16"] <= -1.0:
                    score += 20.0
                elif pst_pass:
                    score += 14.0

                if btc_ewmac_4_16 <= 0.5:
                    score += 5.0
                if idiosyncratic_spread >= 60.0:
                    score += 5.0

                if sig.h1_confirmation.confirmation_tier == "COMBO_1_2":
                    score += 12.0
                elif sig.h1_confirmation.cond2_break_prev_low:
                    score += 9.0
                else:
                    score += 4.0

                if pullback_vol_ratio_1h <= 1.1:
                    score += 8.0
                elif pullback_vol_ratio_1h <= 1.4:
                    score += 4.0

                enriched.append(
                    {
                        "trade": trade_obj,
                        "future_slice": future_slice,
                        "fibo_levels": sig.fibo_levels,
                        "atr_1h": setup.atr_1h,
                        "symbol": symbol,
                        "tf": tf,
                        "tier": sig.h1_confirmation.confirmation_tier,
                        "cond2_break": sig.h1_confirmation.cond2_break_prev_low,
                        "prior_pump_pct": raw_pump_pct,
                        "ker_wave": ker_wave,
                        "pst_pass": pst_pass,
                        "f1_elite": f1_elite,
                        "f1_expanded": f1_expanded,
                        "imp_drop_pct": imp_drop_pct,
                        "imp_ker": imp_ker,
                        "max_fibo_ratio": sig.h1_confirmation.max_pullback_fibo_ratio,
                        "pullback_vol_ratio_1h": pullback_vol_ratio_1h,
                        "full_conviction_score": round(score, 1),
                    }
                )

    return enriched


def show(label: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    trades = [x["trade"] for x in items]
    s = summarize_trades(trades)
    avg_r = float(np.mean([t.r_multiple for t in trades])) if trades else 0.0
    sum_r = float(np.sum([t.r_multiple for t in trades])) if trades else 0.0
    s["avg_r"] = round(avg_r, 3)
    s["sum_r"] = round(sum_r, 2)
    print(
        f"  {label:64s} | N={s['total_trades']:4d} | WR={s['win_rate_pct']:5.2f}% | "
        f"TP1={s['tp1_hit_rate_pct']:5.2f}% | Avg={s['avg_net_return_pct']:+6.3f}% | "
        f"Tot={s['total_net_return_pct']:+7.2f}% | PF={s['profit_factor']:4.2f} | "
        f"AvgR={avg_r:+.2f}R | DD={s['max_drawdown_pct']:5.1f}%"
    )
    return s


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
    symbols = [
        s
        for s in default_syms + alt_syms
        if (SHARED_1H_DIR / f"{s}_1h.parquet").exists()
        or (DATA_LAKE_5M_DIR / f"{s}.parquet").exists()
    ]
    frames = {sym: load_1h_for_oos(sym) for sym in symbols}

    btc_df = frames["BTCUSDT"].sort_index()
    btc_htf = {
        tf: calc_multi_repo_htf_features(resample_1h_to_htf(btc_df, tf))
        for tf in ("4h", "1d")
    }

    print("\n================================================================================================================")
    print("KIỂM THỬ OUT-OF-SAMPLE (OOS 2026: 01/01/2026 -> 29/09/2026) CHO CẢ 7 CẤP ĐỘ CẤU HÌNH (MỐC 0 -> MỐC 6)")
    print("================================================================================================================")

    oos_json_path = Path("artifacts/fibo_trend_short/oos_2026_7_milestones_study.json")
    cached_oos_m0 = None
    if oos_json_path.exists():
        try:
            cached_oos_m0 = json.loads(oos_json_path.read_text(encoding="utf-8"))["oos_2026_milestones"]["m0_baseline_pump5"]
        except Exception:
            cached_oos_m0 = None

    oos_m0 = None if cached_oos_m0 is not None else collect_oos_trades(frames, btc_htf, min_pump=0.05)
    oos_m1 = collect_oos_trades(frames, btc_htf, min_pump=0.50)

    m2_f1b = [x for x in oos_m1 if x["pst_pass"]]
    m3_f1_exp = [x for x in oos_m1 if x["f1_expanded"]]
    m3_f1_eli = [x for x in oos_m1 if x["f1_elite"]]
    m4_f2_exp = [x for x in m3_f1_exp if x["imp_drop_pct"] >= 6.0 and x["imp_ker"] >= 0.50]
    m4_f2_eli = [x for x in m3_f1_eli if x["imp_drop_pct"] >= 6.0 and x["imp_ker"] >= 0.50]
    m5_f3_exp = [x for x in m4_f2_exp if x["cond2_break"] and x["max_fibo_ratio"] <= 0.786]
    m5_f3_eli = [x for x in m4_f2_eli if x["cond2_break"] and x["max_fibo_ratio"] <= 0.786]

    # Simulate SL above_0886 + Dynamic Conviction Sizing on m4_f2_exp and m5_f3_exp
    m6_f4_exp = []
    for x in m4_f2_exp:
        t0: FiboBacktestTrade = x["trade"]
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
        m6_f4_exp.append({**x, "trade": t_m6})

    m6_f4_sniper = [x for x in m6_f4_exp if x["cond2_break"] and x["max_fibo_ratio"] <= 0.786]
    m6_f4_elite_sniper = [
        x for x in m6_f4_exp if x["f1_elite"] and x["cond2_break"] and x["max_fibo_ratio"] <= 0.786
    ]

    report: dict[str, Any] = {}
    report["oos_2026_milestones"] = {
        "m0_baseline_pump5": cached_oos_m0 if cached_oos_m0 is not None else show("Mốc 0 [Baseline]: Sóng bơm >= 5% (Chưa lọc)", oos_m0),
        "m1_f1a_pump50": show("Mốc 1 [F1A]: Sóng bơm >= 50%", oos_m1),
        "m2_f1b_pst": show("Mốc 2 [+F1B]: + pysystemtrade (ewmac<=0 OR accel<=-1)", m2_f1b),
        "m3_f1c_expanded": show("Mốc 3B [+F1C Mở Rộng]: (PST & KER>=0.35) OR (KER>=0.65)", m3_f1_exp),
        "m3_f1c_elite": show("Mốc 3A [+F1C Tinh Hoa]: PST & KER >= 0.35", m3_f1_eli),
        "m4_f2_expanded": show("Mốc 4B [+F2 Mở Rộng]: + Nhịp sập >= 6% & imp_ker >= 0.50", m4_f2_exp),
        "m4_f2_elite": show("Mốc 4A [+F2 Tinh Hoa]: + Nhịp sập >= 6% & imp_ker >= 0.50", m4_f2_eli),
        "m5_f3_expanded": show("Mốc 5B [+F3 Mở Rộng]: + Fibo 0.5-0.786 & H1 Phá Cấu Trúc (ĐK2)", m5_f3_exp),
        "m5_f3_elite": show("Mốc 5A [+F3 Tinh Hoa]: + Fibo 0.5-0.786 & H1 Phá Cấu Trúc (ĐK2)", m5_f3_eli),
        "m6_f4_expanded": show("★ Mốc 6B [+F4 Toàn Diện]: F1+F2 + SL 0.886 + Đi Vốn Conviction", m6_f4_exp),
        "m6_f4_sniper": show("★ Mốc 6A [+F4 Sniper Mở Rộng]: F1_Exp+F2+F3 + SL 0.886 + Đi Vốn", m6_f4_sniper),
        "m6_f4_elite_sniper": show("👑 Mốc 6S [+F4 Sniper Tinh Hoa]: F1_Elite+F2+F3 + SL 0.886 + Đi Vốn", m6_f4_elite_sniper),
    }

    print("\n--- Phân Tích Thang Điểm Hội Tụ 4 Tầng (`0–100 Conviction Score`) Trên Tập OOS 2026 ---")
    report["oos_2026_conviction_tiers"] = {
        "reject_lt_55": show("OOS Tier D/C (< 55 điểm — Đứng ngoài / Bỏ qua)", [x for x in oos_m1 if x["full_conviction_score"] < 55]),
        "tier_b_55_69": show("OOS Tier B (55 – 69 điểm — Chuẩn: 0.75R)", [x for x in oos_m1 if 55 <= x["full_conviction_score"] < 70]),
        "tier_a_70_84": show("OOS Tier A (70 – 84 điểm — Tinh Hoa: 1.25R)", [x for x in oos_m1 if 70 <= x["full_conviction_score"] < 85]),
        "tier_s_ge_85": show("OOS Tier S (>= 85 điểm — Siêu Hội Tụ: 2.00R)", [x for x in oos_m1 if x["full_conviction_score"] >= 85]),
    }

    oos_json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nSaved OOS 2026 7-milestones study to artifacts/fibo_trend_short/oos_2026_7_milestones_study.json")


if __name__ == "__main__":
    main()
