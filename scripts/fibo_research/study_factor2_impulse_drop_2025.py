"""Stage 3.1: Execute & Review Factor #2 (`ALPHA-F2` — First Structural Crack / Impulse Breakdown)
under strict Ceteris Paribus on In-Sample 2024-2025 (<= 2025-12-31T23:59:59+00:00).

Also performs the Collinearity Review Gate for ALPHA-F1D (Cross-Sectional BTC Context).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from study_factor1_multi_repo_benchmark_2025 import calc_multi_repo_htf_features
from dao_vang.config.settings import FiboTrendShortConfig
from dao_vang.fibo_short.backtest import (
    DATA_LAKE_5M_DIR,
    IN_SAMPLE_MAX_UTC,
    SHARED_1H_DIR,
    FiboBacktestTrade,
    _simulate_trade_outcome,
    load_historical_1h_frame,
    resample_1h_to_htf,
    summarize_trades,
)
from dao_vang.fibo_short.detector import evaluate_symbol_timeframe


def collect_f1_f2_trades(
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
        df = df.loc[df.index <= IN_SAMPLE_MAX_UTC].sort_index()
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

                peak_bar = htf_by_open_str.get(sig.wave.swing_high_time)
                low_bar = htf_by_open_str.get(sig.wave.prior_low_time)
                imp_bar = htf_by_open_str.get(sig.wave.impulse_low_time)
                cur_htf_bar = visible_htf[-1]
                if peak_bar is None or low_bar is None or imp_bar is None:
                    continue

                p_idx = peak_bar["htf_idx"]
                l_idx = low_bar["htf_idx"]
                imp_idx = imp_bar["htf_idx"]

                # Factor #1 metrics
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

                # Factor #2 (Impulse Drop) metrics: from peak_bar (p_idx) to imp_bar (imp_idx)
                swing_high = sig.wave.swing_high_price
                prior_low = sig.wave.prior_low_price
                impulse_low = sig.wave.impulse_low_price

                pump_range = max(1e-9, swing_high - prior_low)
                impulse_range = max(0.0, swing_high - impulse_low)

                # 2A: Absolute impulse drop %
                imp_drop_pct = (impulse_range / swing_high) * 100.0

                # 2B: Impulse retracement of the prior pump wave (%)
                # How much of the prior upward pump (prior_low -> swing_high) was wiped out by the impulse drop?
                imp_retrace_of_pump_pct = (impulse_range / pump_range) * 100.0

                # 2C: Impulse drop in Carver Volatility Units (robust_vol at peak)
                r_vol = max(1e-9, peak_bar["robust_vol"])
                imp_vol_units = impulse_range / r_vol

                # 2D: Impulse duration (bars & days) and Impulse KER (straightness of the drop)
                imp_bars = max(1, imp_idx - p_idx)
                imp_days_equiv = imp_bars * (4.0 / 24.0 if tf == "4h" else 1.0)
                imp_slice = htf_records[p_idx : imp_idx + 1]
                if len(imp_slice) >= 2:
                    closes_imp = np.array([b["close"] for b in imp_slice], dtype=float)
                    net_imp = abs(closes_imp[-1] - closes_imp[0])
                    path_imp = float(np.sum(np.abs(np.diff(closes_imp))))
                    imp_ker = net_imp / path_imp if path_imp > 1e-9 else 1.0
                else:
                    imp_ker = 1.0

                # 2E: Impulse Volume vs Prior Pump Volume
                pump_mean_vol = float(np.mean([b["volume"] for b in wave_bars])) if wave_bars else 1.0
                drop_only_bars = htf_records[p_idx + 1 : imp_idx + 1] or [imp_bar]
                imp_mean_vol = float(np.mean([b["volume"] for b in drop_only_bars]))
                imp_vol_ratio = imp_mean_vol / max(1e-9, pump_mean_vol)

                # Cross-sectional BTC context
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

                enriched.append(
                    {
                        "trade": trade_obj,
                        "symbol": symbol,
                        "tf": tf,
                        "tier": sig.h1_confirmation.confirmation_tier,
                        "prior_pump_pct": raw_pump_pct,
                        "ker_wave": ker_wave,
                        "pst_pass": pst_pass,
                        "f1_elite": f1_elite,
                        "f1_expanded": f1_expanded,
                        "peak_ewmac_16_64": peak_bar["ewmac_16_64"],
                        "cur_accel_4_16": cur_htf_bar["accel_4_16"],
                        "btc_ewmac_4_16": btc_ewmac_4_16,
                        "idiosyncratic_spread": idiosyncratic_spread,
                        # Factor #2 features
                        "imp_drop_pct": imp_drop_pct,
                        "imp_retrace_of_pump_pct": imp_retrace_of_pump_pct,
                        "imp_vol_units": imp_vol_units,
                        "imp_bars": imp_bars,
                        "imp_days_equiv": imp_days_equiv,
                        "imp_ker": imp_ker,
                        "imp_vol_ratio": imp_vol_ratio,
                    }
                )

    return enriched


def show(label: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    s = summarize_trades([x["trade"] for x in items])
    print(
        f"  {label:66s} | N={s['total_trades']:3d} | WR={s['win_rate_pct']:5.2f}% | "
        f"TP1={s['tp1_hit_rate_pct']:5.2f}% | Avg={s['avg_net_return_pct']:+6.3f}% | "
        f"Tot={s['total_net_return_pct']:+7.2f}% | PF={s['profit_factor']:4.2f} | DD={s['max_drawdown_pct']:5.1f}%"
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
    frames = {
        sym: load_historical_1h_frame(
            sym,
            start_utc="2024-01-01T00:00:00+00:00",
            end_utc=IN_SAMPLE_MAX_UTC,
            strict_in_sample=True,
        )
        for sym in symbols
    }

    btc_df = frames["BTCUSDT"].loc[frames["BTCUSDT"].index <= IN_SAMPLE_MAX_UTC].sort_index()
    btc_htf = {
        tf: calc_multi_repo_htf_features(resample_1h_to_htf(btc_df, tf))
        for tf in ("4h", "1d")
    }

    items = collect_f1_f2_trades(frames, btc_htf, min_pump=0.50)
    f1_elite_items = [x for x in items if x["f1_elite"]]
    f1_exp_items = [x for x in items if x["f1_expanded"]]

    df_all = pd.DataFrame(items)

    print("\n======================================================================================================")
    print("PHẦN 1 — REVIEW GATE CHO ALPHA-F1D (KIỂM TRA ĐỘ ĐỘC LẬP TƯƠNG QUAN VỚI F1B & F1C)")
    print("======================================================================================================")
    corr_f1 = df_all[
        ["prior_pump_pct", "peak_ewmac_16_64", "cur_accel_4_16", "ker_wave", "btc_ewmac_4_16", "idiosyncratic_spread"]
    ].corr(method="spearman")
    print(corr_f1.round(3).to_string())

    print("\n======================================================================================================")
    print("PHẦN 2 — THỰC NGHIỆM FACTOR #2 (NHỊP SẬP MỞ MÀN) TRÊN NỀN FACTOR #1 ĐÃ KHÓA")
    print("======================================================================================================")
    report: dict[str, Any] = {"f1_corr": corr_f1.round(3).to_dict()}

    print("\n--- 2A. Quét Độ Sâu Tuyệt Đối Nhịp Sập (`imp_drop_pct`) trên Tập Mở Rộng (198 lệnh) & Tinh Hoa (130 lệnh) ---")
    report["f2_abs_drop_on_expanded"] = {}
    for thr in [4, 6, 8, 10, 12, 14, 16, 18, 20, 25]:
        report["f2_abs_drop_on_expanded"][f">= {thr}%"] = show(
            f"[F1 Mở Rộng] Nhịp sập đầu tiên >= {thr:2d}%",
            [x for x in f1_exp_items if x["imp_drop_pct"] >= thr],
        )

    print("\n--- 2A-2. Phân vùng Độ Sâu Nhịp Sập (`imp_drop_pct` quá nông vs vừa đủ vs quá sâu) ---")
    report["f2_abs_drop_buckets"] = {
        "shallow_4_to_12": show("[F1 Mở Rộng] Sập nông 4% – 12% (Cờ tăng / Chưa ai đau)", [x for x in f1_exp_items if 4.0 <= x["imp_drop_pct"] < 12.0]),
        "mid_12_to_25": show("[F1 Mở Rộng] Sập vừa 12% – 25% (Nhốt đội mua đỉnh)", [x for x in f1_exp_items if 12.0 <= x["imp_drop_pct"] < 25.0]),
        "deep_25_to_45": show("[F1 Mở Rộng] Sập mạnh 25% – 45% (Gãy cấu trúc rõ rệt)", [x for x in f1_exp_items if 25.0 <= x["imp_drop_pct"] < 45.0]),
        "extreme_ge_45": show("[F1 Mở Rộng] Sập quá sâu >= 45% (Xả gần hết biên độ nhịp 1)", [x for x in f1_exp_items if x["imp_drop_pct"] >= 45.0]),
    }

    print("\n--- 2B. Tỷ Lệ Xóa Bỏ Sóng Bơm Trước Đó (`imp_retrace_of_pump_pct = Drop / Pump_Range`) ---")
    print("    (Đo xem cú sập đầu tiên xóa sổ bao nhiêu % thành quả của con sóng tăng trước đó)")
    report["f2_retrace_of_pump"] = {
        "lt_25pct_of_pump": show("[F1 Mở Rộng] Xóa < 25% sóng bơm (Chỉnh quá nhẹ so với sóng tăng)", [x for x in f1_exp_items if x["imp_retrace_of_pump_pct"] < 25.0]),
        "25_to_50pct_of_pump": show("[F1 Mở Rộng] Xóa 25% – 50% sóng bơm (Bẻ gãy cấu trúc vừa đẹp)", [x for x in f1_exp_items if 25.0 <= x["imp_retrace_of_pump_pct"] < 50.0]),
        "50_to_80pct_of_pump": show("[F1 Mở Rộng] Xóa 50% – 80% sóng bơm (Nhốt chặt toàn bộ đỉnh)", [x for x in f1_exp_items if 50.0 <= x["imp_retrace_of_pump_pct"] < 80.0]),
        "ge_80pct_of_pump": show("[F1 Mở Rộng] Xóa >= 80% sóng bơm (Đã sập về tận chân sóng!)", [x for x in f1_exp_items if x["imp_retrace_of_pump_pct"] >= 80.0]),
        "sweetspot_25_to_80": show("★ [F1 Mở Rộng] Nhịp sập xóa từ 25% – 80% sóng bơm", [x for x in f1_exp_items if 25.0 <= x["imp_retrace_of_pump_pct"] < 80.0]),
        "elite_sweetspot_25_to_80": show("★ [F1 Tinh Hoa] Nhịp sập xóa từ 25% – 80% sóng bơm", [x for x in f1_elite_items if 25.0 <= x["imp_retrace_of_pump_pct"] < 80.0]),
    }

    print("\n--- 2C. Biên Độ Sập Chuẩn Hóa Biến Động (`imp_vol_units = Drop / robust_vol_35`) ---")
    report["f2_vol_units"] = {
        "vu_lt_25": show("[F1 Mở Rộng] Nhịp sập < 2.5x robust_vol (Sập yếu hơn biến động chuẩn)", [x for x in f1_exp_items if x["imp_vol_units"] < 2.5]),
        "vu_25_to_60": show("[F1 Mở Rộng] Nhịp sập 2.5x – 6.0x robust_vol (Gãy chuẩn xác)", [x for x in f1_exp_items if 2.5 <= x["imp_vol_units"] <= 6.0]),
        "vu_gt_60": show("[F1 Mở Rộng] Nhịp sập > 6.0x robust_vol (Sập hoảng loạn quá đà nhịp 1)", [x for x in f1_exp_items if x["imp_vol_units"] > 6.0]),
    }

    print("\n--- 2D. Độ Thẳng Nhịp Sập (`imp_ker`) & Thời Gian Nhịp Sập (`imp_days_equiv`) & Volume Xả (`imp_vol_ratio`) ---")
    report["f2_ker_and_vol"] = {
        "imp_ker_ge_050": show("[F1 Mở Rộng] Nhịp sập dứt khoát (imp_ker >= 0.50)", [x for x in f1_exp_items if x["imp_ker"] >= 0.50]),
        "imp_ker_lt_050": show("[F1 Mở Rộng] Nhịp sập cưa chân bàn zíc-zắc (imp_ker < 0.50)", [x for x in f1_exp_items if x["imp_ker"] < 0.50]),
        "imp_fast_le_3d": show("[F1 Mở Rộng] Nhịp sập diễn ra nhanh <= 3 ngày", [x for x in f1_exp_items if x["imp_days_equiv"] <= 3.0]),
        "imp_slow_gt_3d": show("[F1 Mở Rộng] Nhịp sập kéo dài > 3 ngày", [x for x in f1_exp_items if x["imp_days_equiv"] > 3.0]),
        "imp_vol_ratio_ge_08": show("[F1 Mở Rộng] Volume nhịp sập >= 80% Volume nhịp bơm", [x for x in f1_exp_items if x["imp_vol_ratio"] >= 0.80]),
        "imp_vol_ratio_lt_08": show("[F1 Mở Rộng] Volume nhịp sập < 80% Volume nhịp bơm", [x for x in f1_exp_items if x["imp_vol_ratio"] < 0.80]),
    }

    print("\n======================================================================================================")
    print("PHẦN 3 — REVIEW GATE CHO FACTOR #2 (MA TRẬN TƯƠNG QUAN & CHỐNG TRÙNG LẶP GIỮA CÁC BIẾN FACTOR #2)")
    print("======================================================================================================")
    df_exp = pd.DataFrame(f1_exp_items)
    corr_f2 = df_exp[
        ["imp_drop_pct", "imp_retrace_of_pump_pct", "imp_vol_units", "imp_ker", "imp_days_equiv", "imp_vol_ratio", "ker_wave"]
    ].corr(method="spearman")
    print(corr_f2.round(3).to_string())
    report["f2_corr"] = corr_f2.round(3).to_dict()

    Path("artifacts/fibo_trend_short/factor2_impulse_study_2025.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nSaved Factor #2 study to artifacts/fibo_trend_short/factor2_impulse_study_2025.json")


if __name__ == "__main__":
    main()
