"""Comprehensive 340-Coin Universe Research & Tiered Whitelist/Blacklist Selection (2024-2025 IS -> 2026 OOS).

Methodology (Zero Cross-Sectional Overfitting / Walk-Forward Validation):
1. Scans all 340 Binance USD-M Perpetual symbols in C:/Quant-trading/data_lake/klines/5m.
2. Extracts 5 Ex-Ante Structural DNA metrics strictly on In-Sample (2024-01-01 -> 2025-12-31):
   - Liquidity Tier (Median Daily USD Quote Volume)
   - Pump Frequency (>=50% H4/D1 waves per year)
   - Gravity Decay Ratio (% of >=50% pumps that revert to Fibo 0.0 before breaking Fibo 1.0)
   - Structural Wave Cleanliness (Median Wave KER & Impulse KER)
   - Wick Toxicity Index (P90 Upper Wick Ratio on H4 bars)
3. Classifies all symbols into 5 Asset Archetypes (G1 Store-of-Value, G2 Liquid L1/L2/DeFi,
   G3 High-Beta Narrative/AI/Gaming, G4 Liquid Meme/Retail Mania, G5 Thin/Manipulated).
4. Evaluates locked 4-Factor Milestones (Mốc 1, Mốc 4A, Mốc 6B, Mốc 6A, Mốc 6S) separately on:
   - In-Sample Calibration Window: 2024-01-01 -> 2025-12-31
   - True Forward Out-of-Sample Window: 2026-01-01 -> 2026-09-29
5. Freezes Tier S Core Whitelist, Tier A Extended Whitelist, and Blacklist using ONLY In-Sample (<=2025)
   criteria, then validates out-of-sample performance on 2026 OOS.
"""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parents[1]
SRC_DIR = ROOT_DIR / "src"
for p in (str(SCRIPT_DIR), str(SRC_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from study_factor1_multi_repo_benchmark_2025 import calc_multi_repo_htf_features
from study_factor2_3_4_complete_2025 import simulate_custom_trade
from dao_vang.config.settings import FiboTrendShortConfig
from dao_vang.fibo_short.backtest import (
    DATA_LAKE_5M_DIR,
    IN_SAMPLE_MAX_UTC,
    OOS_START_UTC,
    SHARED_1H_DIR,
    FiboBacktestTrade,
    _simulate_trade_outcome,
    resample_1h_to_htf,
    summarize_trades,
)
from dao_vang.fibo_short.detector import (
    build_fibo_trade_setup,
    compute_atr,
    compute_fibonacci_levels,
    detect_htf_reversal_wave,
    evaluate_h1_confirmation,
)

STABLE_OR_INDEX_EXCLUDE = {
    "USDCUSDT",
    "FDUSDUSDT",
    "TUSDUSDT",
    "DAIUSDT",
    "BUSDUSDT",
    "EURUSDT",
}

G1_STORE_OF_VALUE = {
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "PAXGUSDT",
    "XAUTUSDT",
    "BTCDOMUSDT",
    "DEFIUSDT",
}

G4_LIQUID_MEME = {
    "1000PEPEUSDT",
    "1000BONKUSDT",
    "1000SHIBUSDT",
    "DOGEUSDT",
    "WIFUSDT",
    "1000FLOKIUSDT",
    "FLOKIUSDT",
    "BOMEUSDT",
    "MEMEUSDT",
    "PEOPLEUSDT",
    "TURBOUSDT",
    "NEIROUSDT",
    "1000NEIROCTOUSDT",
    "NEIROETHUSDT",
    "PENGUUSDT",
    "TRUMPUSDT",
    "MELANIAUSDT",
    "FARTCOINUSDT",
    "PNUTUSDT",
    "ACTUSDT",
    "GOATUSDT",
    "MOODENGUSDT",
    "1000RATSUSDT",
    "1000SATSUSDT",
    "ORDIUSDT",
    "1000CATUSDT",
    "1000CHEEMSUSDT",
    "1000WHYUSDT",
    "1000MOGUSDT",
    "MOGUSDT",
    "POPCATUSDT",
    "BRETTUSDT",
    "MEWUSDT",
    "DOGSUSDT",
    "HMSTRUSDT",
    "NOTUSDT",
    "BABYDOGEUSDT",
    "1MBABYDOGEUSDT",
    "1000LUNCUSDT",
    "LUNA2USDT",
    "USTCUSDT",
    "PONKEUSDT",
    "BANUSDT",
    "CHILLGUYUSDT",
    "HIPPOUSDT",
    "SLERFUSDT",
    "DEGENUSDT",
    "MYROUSDT",
}

G2_LIQUID_L1_L2_DEFI = {
    "SOLUSDT",
    "AVAXUSDT",
    "SUIUSDT",
    "APTUSDT",
    "SEIUSDT",
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
    "ATOMUSDT",
    "LTCUSDT",
    "BCHUSDT",
    "XRPUSDT",
    "TRXUSDT",
    "TONUSDT",
    "ETCUSDT",
    "FILUSDT",
    "ICPUSDT",
    "HBARUSDT",
    "ALGOUSDT",
    "FTMUSDT",
    "MATICUSDT",
    "POLUSDT",
    "MKRUSDT",
    "LDOUSDT",
    "CRVUSDT",
    "COMPUSDT",
    "SNXUSDT",
    "DYDXUSDT",
    "GMXUSDT",
    "RUNEUSDT",
    "STXUSDT",
    "KASUSDT",
    "EGLDUSDT",
    "XTZUSDT",
    "EOSUSDT",
    "NEOUSDT",
    "VETUSDT",
    "XLMUSDT",
    "XMRUSDT",
    "ZECUSDT",
    "DASHUSDT",
    "SUSHIUSDT",
    "1INCHUSDT",
    "CAKEUSDT",
    "JTOUSDT",
    "JUPUSDT",
    "PENDLEUSDT",
    "ENAUSDT",
    "ETHFIUSDT",
    "EIGENUSDT",
    "STRKUSDT",
    "ZKUSDT",
    "ZROUSDT",
    "WUSDT",
    "ONDOUSDT",
}


def load_symbol_1h_full_2024_2026(symbol: str) -> pd.DataFrame:
    """Load 1h OHLCV + quote_volume from 2023-10-01 through 2026-09-29 for a symbol."""
    p_5m = DATA_LAKE_5M_DIR / f"{symbol}.parquet"
    if p_5m.exists():
        try:
            df5 = pd.read_parquet(
                p_5m,
                columns=["open_time", "open", "high", "low", "close", "volume", "quote_volume"],
            )
        except Exception:
            df5 = pd.read_parquet(
                p_5m,
                columns=["open_time", "open", "high", "low", "close", "volume"],
            )
            df5["quote_volume"] = df5["close"] * df5["volume"]

        df5["open_time"] = pd.to_datetime(df5["open_time"], utc=True)
        df5 = df5[df5["open_time"] >= pd.Timestamp("2023-10-01T00:00:00+00:00")]
        if df5.empty:
            return pd.DataFrame()
        df5 = df5.drop_duplicates(subset=["open_time"]).set_index("open_time").sort_index()
        g = df5.resample("1h", label="left", closed="left")
        df1h = pd.DataFrame(
            {
                "open": g["open"].first(),
                "high": g["high"].max(),
                "low": g["low"].min(),
                "close": g["close"].last(),
                "volume": g["volume"].sum(),
                "quote_volume": g["quote_volume"].sum(),
                "n5": g["open"].count(),
            }
        )
        df1h = df1h[df1h["n5"] >= 10].drop(columns=["n5"]).dropna()
        return df1h.astype(float)

    p_1h = SHARED_1H_DIR / f"{symbol}_1h.parquet"
    if p_1h.exists():
        df = pd.read_parquet(p_1h)
        if not isinstance(df.index, pd.DatetimeIndex):
            tcol = "open_time" if "open_time" in df.columns else "timestamp"
            df[tcol] = pd.to_datetime(df[tcol], utc=True)
            df = df.set_index(tcol)
        else:
            df.index = pd.to_datetime(df.index, utc=True)
        df = df.sort_index()
        df = df[df.index >= pd.Timestamp("2023-10-01T00:00:00+00:00")].copy()
        if "quote_volume" not in df.columns:
            df["quote_volume"] = df["close"] * df["volume"]
        return df[["open", "high", "low", "close", "volume", "quote_volume"]].astype(float)

    return pd.DataFrame()


def classify_archetype(symbol: str, median_daily_qvol: float, wick_toxicity_pct: float) -> str:
    if symbol in G1_STORE_OF_VALUE:
        return "G1_STORE_OF_VALUE_MAJOR"
    if symbol in G4_LIQUID_MEME:
        return "G4_LIQUID_MEME_RETAIL"
    if symbol in G2_LIQUID_L1_L2_DEFI:
        return "G2_LIQUID_L1_L2_DEFI"
    if median_daily_qvol < 2_500_000.0 or wick_toxicity_pct > 4.5:
        return "G5_THIN_OR_MANIPULATED"
    return "G3_HIGH_BETA_NARRATIVE_MIDCAP"


def fast_collect_symbol_trades(
    symbol: str,
    df_1h: pd.DataFrame,
    btc_htf: dict[str, pd.DataFrame],
    *,
    entry_start_ts: pd.Timestamp,
    entry_end_ts: pd.Timestamp,
    min_pump: float = 0.50,
) -> list[dict[str, Any]]:
    """Fast point-in-time trade collector for a single symbol using HTF pointer caching."""
    cfg = FiboTrendShortConfig(
        min_prior_pump_pct=min_pump,
        min_impulse_drop_pct=0.04,
        fibo_entry_min=0.500,
        fibo_entry_max=0.618,
        sl_mode="above_swing_high",
        require_both_h1_conditions=False,
    )

    if len(df_1h) < 100:
        return []

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

    enriched: list[dict[str, Any]] = []

    for tf in ("4h", "1d"):
        htf_df = resample_1h_to_htf(df_1h, tf)
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

        # Cache HTF wave detection per htf_ptr since visible_htf only changes when htf_ptr changes
        cached_htf_ptr = -1
        cached_wave = None
        cached_fibo = None

        for idx_1h in range(24, len(h1_records) - 2):
            if idx_1h < cooldown_until_idx:
                continue

            current_decision_ts = h1_close_times[idx_1h]
            if current_decision_ts < entry_start_ts or current_decision_ts > entry_end_ts:
                while htf_ptr < n_htf and htf_close_times[htf_ptr] <= current_decision_ts:
                    htf_ptr += 1
                continue

            while htf_ptr < n_htf and htf_close_times[htf_ptr] <= current_decision_ts:
                htf_ptr += 1

            if htf_ptr < 10:
                continue

            if htf_ptr != cached_htf_ptr:
                cached_htf_ptr = htf_ptr
                start_htf = max(0, htf_ptr - cfg.swing_lookback_bars - 24)
                visible_htf = htf_records[start_htf:htf_ptr]
                cached_wave = detect_htf_reversal_wave(symbol, visible_htf, tf, cfg)
                if cached_wave is not None:
                    cached_fibo = compute_fibonacci_levels(
                        cached_wave.swing_high_price,
                        cached_wave.impulse_low_price,
                    )
                else:
                    cached_fibo = None

            if cached_wave is None or cached_fibo is None:
                continue

            wave_key = f"{tf}:{cached_wave.swing_high_time}:{cached_wave.impulse_low_time}"
            if wave_key in consumed_waves:
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

            atr_1h = compute_atr(visible_1h, period=14)
            setup = build_fibo_trade_setup(
                fibo=cached_fibo,
                current_price=current_price,
                atr_1h=atr_1h,
                confirmed=True,
                config=cfg,
            )

            future_slice = h1_records[idx_1h + 1 : min(len(h1_records), idx_1h + 1 + horizon)]
            if not future_slice:
                continue

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

            entry_dt = pd.Timestamp(h1_conf.candle_time)
            year = int(entry_dt.year)

            trade_obj = FiboBacktestTrade(
                trade_id=f"{symbol}_{tf}_{idx_1h}",
                symbol=symbol,
                higher_timeframe=tf,
                confirmation_tier=h1_conf.confirmation_tier,
                pattern_name=h1_conf.pattern_name,
                entry_time=h1_conf.candle_time,
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
                fibo_entry_ratio=h1_conf.current_fibo_ratio,
                impulse_drop_pct=cached_wave.impulse_drop_pct,
                prior_pump_pct=cached_wave.prior_pump_pct,
            )

            peak_bar = htf_by_open_str.get(cached_wave.swing_high_time)
            low_bar = htf_by_open_str.get(cached_wave.prior_low_time)
            imp_bar = htf_by_open_str.get(cached_wave.impulse_low_time)
            cur_htf_bar = htf_records[htf_ptr - 1]
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

            swing_high = cached_wave.swing_high_price
            impulse_low = cached_wave.impulse_low_price
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

            raw_pump_pct = (
                cached_wave.prior_pump_pct * 100.0
                if cached_wave.prior_pump_pct < 10.0
                else cached_wave.prior_pump_pct
            )
            idiosyncratic_spread = raw_pump_pct - max(0.0, btc_ret_pct)

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

            if h1_conf.confirmation_tier == "COMBO_1_2":
                score += 12.0
            elif h1_conf.cond2_break_prev_low:
                score += 9.0
            else:
                score += 4.0

            if pullback_vol_ratio_1h <= 1.1:
                score += 8.0
            elif pullback_vol_ratio_1h <= 1.4:
                score += 4.0

            # Also pre-compute Mốc 6 trade (SL 0.886 + 0.25 ATR + Conviction Sizing)
            ep = trade_obj.entry_price
            lvl_0886 = cached_fibo.level_0000 + 0.886 * cached_fibo.wave_range
            sl_price = max(lvl_0886, ep * 1.005) + 0.25 * atr_1h
            out_m6, g_m6, n_m6, r_m6, tp1_m6, tp2_m6, tp3_m6, ex_p_m6, ex_t_m6, hold_h_m6 = simulate_custom_trade(
                future_slice,
                entry_price=ep,
                stop_loss=sl_price,
                tp1=trade_obj.tp1,
                tp2=trade_obj.tp2,
                tp3=trade_obj.tp3,
                return_exit_meta=True,
            )
            sc = round(score, 1)
            mult = 1.50 if sc >= 80 else (1.15 if sc >= 68 else 0.80)
            trade_m6 = replace(
                trade_obj,
                stop_loss=sl_price,
                exit_price=round(ex_p_m6, 8),
                exit_time=ex_t_m6,
                hold_hours=hold_h_m6,
                outcome=out_m6,  # type: ignore[arg-type]
                gross_return_pct=round(g_m6 * mult, 4),
                net_return_pct=round(n_m6 * mult, 4),
                r_multiple=round(r_m6 * mult, 4),
                tp1_reached=tp1_m6,
                tp2_reached=tp2_m6,
                tp3_reached=tp3_m6,
            )

            enriched.append(
                {
                    "trade": trade_obj,
                    "trade_m6": trade_m6,
                    "year": year,
                    "symbol": symbol,
                    "tf": tf,
                    "tier": h1_conf.confirmation_tier,
                    "cond2_break": h1_conf.cond2_break_prev_low,
                    "prior_pump_pct": raw_pump_pct,
                    "ker_wave": ker_wave,
                    "pst_pass": pst_pass,
                    "f1_elite": f1_elite,
                    "f1_expanded": f1_expanded,
                    "imp_drop_pct": imp_drop_pct,
                    "imp_ker": imp_ker,
                    "max_fibo_ratio": h1_conf.max_pullback_fibo_ratio,
                    "pullback_vol_ratio_1h": pullback_vol_ratio_1h,
                    "full_conviction_score": sc,
                }
            )

    return enriched


def evaluate_single_symbol_worker(
    symbol: str,
    btc_htf_is: dict[str, pd.DataFrame],
    btc_htf_oos: dict[str, pd.DataFrame],
) -> dict[str, Any] | None:
    """Worker to compute Ex-Ante Structural DNA + IS (2024-2025) & OOS (2026) trades for one symbol."""
    df = load_symbol_1h_full_2024_2026(symbol)
    if df.empty or len(df) < 200:
        return None

    df_is = df.loc[
        (df.index >= pd.Timestamp("2024-01-01T00:00:00+00:00"))
        & (df.index <= IN_SAMPLE_MAX_UTC)
    ]
    df_oos_ctx = df.loc[df.index >= pd.Timestamp("2025-10-01T00:00:00+00:00")]

    # Ex-Ante Structural DNA on In-Sample (<= 2025-12-31)
    if not df_is.empty and len(df_is) >= 100:
        daily_qvol = df_is["quote_volume"].resample("1d").sum()
        daily_qvol_active = daily_qvol[daily_qvol > 0]
        median_daily_qvol = float(daily_qvol_active.median()) if not daily_qvol_active.empty else 0.0
        is_active_days = int(len(daily_qvol_active))

        htf4_is = resample_1h_to_htf(df_is, "4h")
        if not htf4_is.empty:
            upper_wick = (
                htf4_is["high"] - np.maximum(htf4_is["open"], htf4_is["close"])
            ) / np.maximum(1e-9, htf4_is["close"]) * 100.0
            wick_toxicity_pct = float(np.percentile(upper_wick, 90))
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

    # Collect IS (2024-2025) and OOS (2026) Mốc 1 trades
    is_items = (
        fast_collect_symbol_trades(
            symbol,
            df_is,
            btc_htf_is,
            entry_start_ts=pd.Timestamp("2024-01-01T00:00:00+00:00"),
            entry_end_ts=IN_SAMPLE_MAX_UTC,
            min_pump=0.50,
        )
        if len(df_is) >= 150
        else []
    )

    oos_items = (
        fast_collect_symbol_trades(
            symbol,
            df_oos_ctx,
            btc_htf_oos,
            entry_start_ts=OOS_START_UTC,
            entry_end_ts=pd.Timestamp("2026-12-31T23:59:59+00:00"),
            min_pump=0.50,
        )
        if len(df_oos_ctx) >= 150
        else []
    )

    # Compute Ex-Ante Gravity Decay Ratio & Median Wave/Impulse KER from Mốc 1 raw pump waves in IS
    pump_50_count_is = len(is_items)
    if pump_50_count_is > 0:
        tp1_reverted = sum(1 for x in is_items if x["trade"].tp1_reached)
        gravity_decay_pct = round(tp1_reverted / pump_50_count_is * 100.0, 1)
        med_wave_ker = round(float(np.median([x["ker_wave"] for x in is_items])), 3)
        med_imp_ker = round(float(np.median([x["imp_ker"] for x in is_items])), 3)
    else:
        gravity_decay_pct = 0.0
        med_wave_ker = 0.0
        med_imp_ker = 0.0

    return {
        "symbol": symbol,
        "archetype": archetype,
        "liq_tier": liq_tier,
        "median_daily_qvol_usd": round(median_daily_qvol, 0),
        "is_active_days": is_active_days,
        "wick_toxicity_p90_pct": round(wick_toxicity_pct, 2),
        "pump_50_count_is": pump_50_count_is,
        "gravity_decay_rate_pct": gravity_decay_pct,
        "median_wave_ker": med_wave_ker,
        "median_imp_ker": med_imp_ker,
        "is_items": is_items,
        "oos_items": oos_items,
    }


def filter_milestone_trades(items: list[dict[str, Any]], milestone: str) -> list[FiboBacktestTrade]:
    if milestone == "m1_f1a_pump50":
        return [x["trade"] for x in items]
    if milestone == "m4_f2_elite":
        return [
            x["trade"]
            for x in items
            if x["f1_elite"] and x["imp_drop_pct"] >= 6.0 and x["imp_ker"] >= 0.50
        ]
    if milestone == "m6_f4_expanded":
        return [
            x["trade_m6"]
            for x in items
            if x["f1_expanded"] and x["imp_drop_pct"] >= 6.0 and x["imp_ker"] >= 0.50
        ]
    if milestone == "m6_f4_sniper":
        return [
            x["trade_m6"]
            for x in items
            if x["f1_expanded"]
            and x["imp_drop_pct"] >= 6.0
            and x["imp_ker"] >= 0.50
            and x["cond2_break"]
            and x["max_fibo_ratio"] <= 0.786
        ]
    if milestone == "m6_f4_elite_sniper":
        return [
            x["trade_m6"]
            for x in items
            if x["f1_elite"]
            and x["imp_drop_pct"] >= 6.0
            and x["imp_ker"] >= 0.50
            and x["cond2_break"]
            and x["max_fibo_ratio"] <= 0.786
        ]
    raise ValueError(f"Unknown milestone: {milestone}")


def load_coingecko_market_map() -> dict[str, dict[str, Any]]:
    """Load cached CoinGecko market cap, FDV, and circulating/total supply records."""
    cg_cache = ROOT_DIR / "artifacts" / "fibo_trend_short" / "coingecko_marketcap_cache.json"
    if not cg_cache.exists():
        return {}
    try:
        all_cg = json.loads(cg_cache.read_text(encoding="utf-8"))
    except Exception:
        return {}
    cg_map: dict[str, dict[str, Any]] = {}
    for item in all_cg:
        sym = str(item.get("symbol", "")).upper()
        if sym not in cg_map or (item.get("market_cap") or 0) > (cg_map[sym].get("market_cap") or 0):
            cg_map[sym] = item
    return cg_map


def enrich_with_marketcap_and_supply(r: dict[str, Any], cg_map: dict[str, dict[str, Any]]) -> None:
    """Attach Circulating Market Cap, FDV, Circulating/Total Supply Float Ratio & Turnover."""
    raw_sym = r["symbol"].replace("USDT", "")
    base_sym = raw_sym[4:] if raw_sym.startswith("1000") else raw_sym
    cg = cg_map.get(base_sym) or cg_map.get(raw_sym)
    qvol = float(r.get("median_daily_qvol_usd", 0.0))

    if cg and (cg.get("market_cap") or 0) > 0:
        mcap = float(cg["market_cap"])
        fdv = float(cg.get("fully_diluted_valuation") or mcap)
        circ = float(cg.get("circulating_supply") or 0.0)
        tot = float(cg.get("total_supply") or cg.get("max_supply") or circ)
        float_ratio = min(1.0, circ / tot) if tot > 0 else 1.0
        turnover_pct = (qvol / mcap) * 100.0 if mcap > 0 else 0.0
        mcap_rank = int(cg.get("market_cap_rank") or 999)
    else:
        mcap = 0.0
        fdv = 0.0
        circ = 0.0
        tot = 0.0
        float_ratio = 1.0
        turnover_pct = 999.0 if qvol > 0 else 0.0
        mcap_rank = 9999

    if mcap >= 2_000_000_000:
        mcap_tier = "MC1_LARGE_CAP_2B_PLUS"
    elif mcap >= 500_000_000:
        mcap_tier = "MC2_UPPER_MID_500M_2B"
    elif mcap >= 150_000_000:
        mcap_tier = "MC3_LOWER_MID_150M_500M"
    elif mcap >= 50_000_000:
        mcap_tier = "MC4_SMALL_CAP_50M_150M"
    else:
        mcap_tier = "MC5_MICRO_UNDER_50M"

    if float_ratio >= 0.75:
        float_tier = "FLOAT_HIGH_75_PLUS"
    elif float_ratio >= 0.40:
        float_tier = "FLOAT_MED_40_75"
    else:
        float_tier = "FLOAT_LOW_UNDER_40"

    r["mcap_usd"] = round(mcap, 0)
    r["fdv_usd"] = round(fdv, 0)
    r["circulating_supply"] = circ
    r["total_supply"] = tot
    r["float_ratio"] = round(float_ratio, 3)
    r["futures_to_mcap_turnover_pct"] = round(turnover_pct, 2)
    r["mcap_rank"] = mcap_rank
    r["mcap_tier"] = mcap_tier
    r["float_tier"] = float_tier


def assign_ex_ante_universe_tier(
    sym_meta: dict[str, Any],
    m4a_is: dict[str, Any],
    m6b_is: dict[str, Any],
) -> tuple[str, float, str]:
    """Assign Universe Tier v1.2.0 (TIER_S_CORE, TIER_A_EXTENDED, DYNAMIC_POOL, BLACKLIST)
    combining:
    - Reference `a1e6ca7d` Point-in-Time 63-day Warm-up (`is_active_days >= 63`)
    - Circulating Market Cap (`mcap_usd >= $150M`) & Supply Float Ratio (`float_ratio >= 64%`)
    - Ex-Ante Structural Archetype, Liquidity, Wick Toxicity & In-Sample (<= 2025) alignment.
    """
    arch = sym_meta["archetype"]
    qvol = sym_meta["median_daily_qvol_usd"]
    wick = sym_meta["wick_toxicity_p90_pct"]
    grav = sym_meta["gravity_decay_rate_pct"]
    is_days = sym_meta["is_active_days"]
    mcap = sym_meta.get("mcap_usd", 0.0)
    float_ratio = sym_meta.get("float_ratio", 1.0)

    # 1. Hard Exclusions: Secular Store-of-Value / Institutional Bid Assets
    if arch == "G1_STORE_OF_VALUE_MAJOR":
        return (
            "BLACKLIST",
            10.0,
            "Tài sản Tích trữ Vĩ mô / Institutional Bid (Chỉ dùng làm bộ lọc Regime, cấm Short)",
        )

    n6 = m6b_is["total_trades"]
    net6 = m6b_is["total_net_return_pct"]
    pf6 = m6b_is["profit_factor"]
    wr6 = m6b_is["win_rate_pct"]

    n4 = m4a_is["total_trades"]
    net4 = m4a_is["total_net_return_pct"]

    # Compute Ex-Ante Suitability Score [0..100] from Archetype + MarketCap/Float + DNA + IS metrics
    score = 0.0
    # DNA 0: Structural Archetype + Tokenomics Float Bonus (max 25)
    if arch == "G4_LIQUID_MEME_RETAIL":
        score += 20.0
    elif arch == "G2_LIQUID_L1_L2_DEFI":
        score += 17.0
    elif arch == "G3_HIGH_BETA_NARRATIVE_MIDCAP" and mcap >= 150_000_000 and float_ratio >= 0.64:
        score += 13.0
    elif arch == "G3_HIGH_BETA_NARRATIVE_MIDCAP":
        score += 4.0

    if mcap >= 150_000_000 and float_ratio >= 0.75:
        score += 5.0
    elif mcap < 150_000_000 or float_ratio < 0.50:
        score -= 8.0

    # DNA 1: Liquidity (max 20)
    if qvol >= 30_000_000:
        score += 20.0
    elif qvol >= 10_000_000:
        score += 16.0
    elif qvol >= 5_000_000:
        score += 12.0
    elif qvol >= 2_500_000:
        score += 7.0

    # DNA 2: Natural Gravity Decay after >=50% Pump (max 15)
    if grav >= 60.0:
        score += 15.0
    elif grav >= 45.0:
        score += 12.0
    elif grav >= 35.0:
        score += 8.0
    else:
        score += 2.0

    # DNA 3: Low Wick Manipulation (max 15)
    if wick <= 2.2:
        score += 15.0
    elif wick <= 3.2:
        score += 11.0
    elif wick <= 4.2:
        score += 6.0

    # DNA 4: In-Sample Structural Alignment on Mốc 6B & Mốc 4A (max 25)
    if n6 >= 3 and pf6 >= 1.8 and net6 >= 25.0 and wr6 >= 75.0:
        score += 25.0
    elif n6 >= 2 and pf6 >= 1.35 and net6 >= 15.0:
        score += 20.0
    elif net6 >= 0.0 and (n6 >= 1 or n4 >= 1):
        score += 12.0
    elif n6 == 0 and n4 == 0:
        score += 5.0
    else:
        score -= 15.0

    score = round(max(0.0, min(99.0, score)), 1)

    # 2. Tier S Core Whitelist (40 Core Symbols):
    # Liquid Meme (G4) or Liquid L1/L2/DeFi (G2) with >= 63d warmup (a1e6ca7d rule), >= $5M/day liquidity and verified IS structural alignment
    is_tier_s = (
        arch in ("G2_LIQUID_L1_L2_DEFI", "G4_LIQUID_MEME_RETAIL")
        and is_days >= 63
        and qvol >= 5_000_000.0
        and (
            (net6 >= 15.0 and pf6 >= 1.35)
            or (arch == "G4_LIQUID_MEME_RETAIL" and net6 >= 0.0)
        )
    )
    if is_tier_s:
        return (
            "TIER_S_CORE",
            max(score, 82.0),
            f"Siêu phẩm Chủ lực ({arch.split('_')[0]}-{arch.split('_')[1]} | MCap ${mcap/1e6:.0f}M, Float {float_ratio*100:.0f}%, Vol ${qvol/1e6:.1f}M/d | IS Mốc 6B: {n6} lệnh, {net6:+.1f}%)",
        )

    # 3. Tier A Extended Whitelist v1.2 (28 High-Float Mid/Large-Cap Symbols):
    # Upgraded with a1e6ca7d 63-day Warmup + Circulating Market Cap >= $150M + Supply Float Ratio >= 64%
    is_tier_a = (
        is_days >= 63
        and (
            (
                arch in ("G2_LIQUID_L1_L2_DEFI", "G4_LIQUID_MEME_RETAIL")
                and net6 >= -5.0
            )
            or (
                arch == "G3_HIGH_BETA_NARRATIVE_MIDCAP"
                and mcap >= 150_000_000.0
                and float_ratio >= 0.64
                and qvol >= 10_000_000.0
                and wick <= 3.5
                and net6 >= 12.0
                and pf6 >= 1.40
            )
        )
    )
    if is_tier_a:
        return (
            "TIER_A_EXTENDED",
            max(score, 68.0),
            f"Mã Mở rộng Chuẩn v1.2 ({arch.split('_')[0]} | MCap ${mcap/1e6:.0f}M, Float {float_ratio*100:.0f}%, Vol ${qvol/1e6:.1f}M/d | IS Mốc 6B: {n6} lệnh, {net6:+.1f}%)",
        )

    # 4. Blacklist toxic / illiquid / low-float VC unlock / cornered small-cap traps
    if arch == "G5_THIN_OR_MANIPULATED":
        return (
            "BLACKLIST",
            min(score, 35.0),
            f"Thanh khoản mỏng (${qvol/1e6:.2f}M/d) hoặc Râu nến thao túng cao ({wick:.1f}%) — Bẫy quét SL",
        )

    if arch == "G3_HIGH_BETA_NARRATIVE_MIDCAP" and (mcap < 150_000_000.0 or float_ratio < 0.64):
        return (
            "BLACKLIST",
            min(score, 42.0),
            f"Loại bởi Quy tắc Vốn hóa & Cung lưu hành v1.2 (MCap ${mcap/1e6:.0f}M < $150M hoặc Float {float_ratio*100:.0f}% < 64% — Bẫy VC Unlock / Đội lái gom cung)",
        )

    if net6 < 0.0 or net4 < 0.0:
        return (
            "BLACKLIST",
            min(score, 40.0),
            f"Cấu trúc Bẫy Squeeze / Âm kỳ vọng trong IS (Mốc 6B Net {net6:+.1f}%, PF {pf6:.2f})",
        )

    # 5. Dynamic Pool: New listings (<120 active days in IS) that satisfy MCap >= $150M, Float >= 64%, Vol >= $5M, Wick <= 3.8%
    if is_days < 120 and mcap >= 150_000_000.0 and float_ratio >= 0.64 and qvol >= 5_000_000.0 and wick <= 3.8:
        return (
            "DYNAMIC_POOL",
            score,
            f"Nhóm Quan sát Động Chuẩn v1.2 (MCap ${mcap/1e6:.0f}M >= $150M, Float {float_ratio*100:.0f}% >= 64%, Vol ${qvol/1e6:.1f}M/d)",
        )

    return (
        "BLACKLIST",
        min(score, 45.0),
        f"Mid/Low-Cap thiếu vốn hóa lưu hành (${mcap/1e6:.0f}M) hoặc thanh khoản sâu (${qvol/1e6:.1f}M/d)",
    )


def main() -> None:
    t0 = time.time()
    all_parquet = sorted(DATA_LAKE_5M_DIR.glob("*.parquet"))
    symbols = [
        p.stem
        for p in all_parquet
        if p.stem.endswith("USDT") and p.stem not in STABLE_OR_INDEX_EXCLUDE
    ]
    print(f"1. Discovered {len(symbols)} USD-M Perpetual symbols in {DATA_LAKE_5M_DIR}")

    print("2. Preparing BTCUSDT H4/D1 macro reference frames (IS & OOS)...")
    btc_full = load_symbol_1h_full_2024_2026("BTCUSDT")
    btc_is = btc_full.loc[
        (btc_full.index >= pd.Timestamp("2024-01-01T00:00:00+00:00"))
        & (btc_full.index <= IN_SAMPLE_MAX_UTC)
    ]
    btc_oos = btc_full.loc[btc_full.index >= pd.Timestamp("2025-10-01T00:00:00+00:00")]

    btc_htf_is = {
        tf: calc_multi_repo_htf_features(resample_1h_to_htf(btc_is, tf))
        for tf in ("4h", "1d")
    }
    btc_htf_oos = {
        tf: calc_multi_repo_htf_features(resample_1h_to_htf(btc_oos, tf))
        for tf in ("4h", "1d")
    }

    max_workers = min(8, os.cpu_count() or 4)
    print(f"3. Scanning all {len(symbols)} symbols across IS (2024-2025) & OOS (2026) using {max_workers} workers...")

    symbol_results: list[dict[str, Any]] = []
    completed = 0
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(evaluate_single_symbol_worker, sym, btc_htf_is, btc_htf_oos): sym
            for sym in symbols
        }
        for fut in as_completed(futures):
            completed += 1
            res = fut.result()
            if res is not None:
                symbol_results.append(res)
            if completed % 50 == 0 or completed == len(symbols):
                print(f"   Progress: {completed}/{len(symbols)} symbols processed ({time.time() - t0:.1f}s)")

    symbol_results.sort(key=lambda r: r["symbol"])
    print(f"4. Valid symbols evaluated: {len(symbol_results)}")

    cg_map = load_coingecko_market_map()
    print(f"5. Enriching {len(symbol_results)} symbols with CoinGecko Market Cap, FDV & Circulating Supply ({len(cg_map)} records)...")
    for r in symbol_results:
        enrich_with_marketcap_and_supply(r, cg_map)

    milestones = [
        "m1_f1a_pump50",
        "m4_f2_elite",
        "m6_f4_expanded",
        "m6_f4_sniper",
        "m6_f4_elite_sniper",
    ]

    # Identify a1e6ca7d Top-50 Volume Point-in-Time set & Pure Zero-Bias MarketCap+Float set
    non_g1_pit_candidates = sorted(
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
    pit_a1e6ca7d_top50_syms = {r["symbol"] for r in non_g1_pit_candidates[:50]}

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

    # Evaluate each symbol and assign Ex-Ante Universe Tier v1.2 (using ONLY IS <= 2025 + Ex-Ante MCap/Float)
    symbol_profiles: list[dict[str, Any]] = []
    for r in symbol_results:
        is_items = r["is_items"]
        oos_items = r["oos_items"]

        m4a_is = summarize_trades(filter_milestone_trades(is_items, "m4_f2_elite"))
        m6b_is = summarize_trades(filter_milestone_trades(is_items, "m6_f4_expanded"))
        m6a_is = summarize_trades(filter_milestone_trades(is_items, "m6_f4_sniper"))
        m6s_is = summarize_trades(filter_milestone_trades(is_items, "m6_f4_elite_sniper"))

        m4a_oos = summarize_trades(filter_milestone_trades(oos_items, "m4_f2_elite"))
        m6b_oos = summarize_trades(filter_milestone_trades(oos_items, "m6_f4_expanded"))
        m6a_oos = summarize_trades(filter_milestone_trades(oos_items, "m6_f4_sniper"))
        m6s_oos = summarize_trades(filter_milestone_trades(oos_items, "m6_f4_elite_sniper"))

        u_tier, u_score, u_reason = assign_ex_ante_universe_tier(r, m4a_is, m6b_is)
        r["universe_tier"] = u_tier
        r["suitability_score"] = u_score
        r["tier_reason_vi"] = u_reason
        r["in_pit_zero_bias_mcap_float"] = r["symbol"] in pit_zero_bias_mcap_float_syms
        r["in_pit_a1e6ca7d_top50"] = r["symbol"] in pit_a1e6ca7d_top50_syms

        # Flag whether symbol was in Tier A v1.1 (Volume-only G3) but filtered out in v1.2 by MCap/Float
        was_v11_g3_trap = (
            r["archetype"] == "G3_HIGH_BETA_NARRATIVE_MIDCAP"
            and r["median_daily_qvol_usd"] >= 10_000_000.0
            and r["wick_toxicity_p90_pct"] <= 3.5
            and m6b_is["total_net_return_pct"] >= 12.0
            and m6b_is["profit_factor"] >= 1.40
            and (r["mcap_usd"] < 150_000_000.0 or r["float_ratio"] < 0.64 or r["is_active_days"] < 63)
        )
        r["was_v11_low_float_or_small_mcap_trap"] = was_v11_g3_trap

        symbol_profiles.append(
            {
                "symbol": r["symbol"],
                "universe_tier": u_tier,
                "suitability_score": u_score,
                "tier_reason_vi": u_reason,
                "archetype": r["archetype"],
                "liq_tier": r["liq_tier"],
                "mcap_tier": r["mcap_tier"],
                "float_tier": r["float_tier"],
                "mcap_usd": r["mcap_usd"],
                "fdv_usd": r["fdv_usd"],
                "float_ratio": r["float_ratio"],
                "futures_to_mcap_turnover_pct": r["futures_to_mcap_turnover_pct"],
                "mcap_rank": r["mcap_rank"],
                "in_pit_zero_bias_mcap_float": r["in_pit_zero_bias_mcap_float"],
                "in_pit_a1e6ca7d_top50": r["in_pit_a1e6ca7d_top50"],
                "median_daily_qvol_usd": r["median_daily_qvol_usd"],
                "is_active_days": r["is_active_days"],
                "wick_toxicity_p90_pct": r["wick_toxicity_p90_pct"],
                "pump_50_count_is": r["pump_50_count_is"],
                "gravity_decay_rate_pct": r["gravity_decay_rate_pct"],
                "median_wave_ker": r["median_wave_ker"],
                "median_imp_ker": r["median_imp_ker"],
                "is_2024_2025": {
                    "m4_f2_elite": m4a_is,
                    "m6_f4_expanded": m6b_is,
                    "m6_f4_sniper": m6a_is,
                    "m6_f4_elite_sniper": m6s_is,
                },
                "oos_2026": {
                    "m4_f2_elite": m4a_oos,
                    "m6_f4_expanded": m6b_oos,
                    "m6_f4_sniper": m6a_oos,
                    "m6_f4_elite_sniper": m6s_oos,
                },
            }
        )

    # Aggregate performance by Universe Tier & Point-in-Time Methodology (Walk-Forward Validation: IS vs OOS)
    tier_groups = {
        "ALL_340_UNFILTERED": lambda r: True,
        "PIT_A1E6CA7D_TOP50_VOL": lambda r: r["in_pit_a1e6ca7d_top50"],
        "PIT_ZERO_BIAS_MCAP_FLOAT": lambda r: r["in_pit_zero_bias_mcap_float"],
        "TIER_S_CORE": lambda r: r["universe_tier"] == "TIER_S_CORE",
        "TIER_S_PLUS_A_WHITELIST": lambda r: r["universe_tier"] in ("TIER_S_CORE", "TIER_A_EXTENDED"),
        "TIER_A_EXTENDED": lambda r: r["universe_tier"] == "TIER_A_EXTENDED",
        "LOW_FLOAT_OR_SMALL_MCAP_G3_TRAPS": lambda r: r["was_v11_low_float_or_small_mcap_trap"],
        "DYNAMIC_POOL": lambda r: r["universe_tier"] == "DYNAMIC_POOL",
        "BLACKLIST": lambda r: r["universe_tier"] == "BLACKLIST",
    }

    by_universe_tier: dict[str, Any] = {}
    for t_name, pred in tier_groups.items():
        sub = [r for r in symbol_results if pred(r)]
        is_all = [x for r in sub for x in r["is_items"]]
        oos_all = [x for r in sub for x in r["oos_items"]]
        by_universe_tier[t_name] = {
            "coin_count": len(sub),
            "is_2024_2025": {
                m: summarize_trades(filter_milestone_trades(is_all, m)) for m in milestones
            },
            "oos_2026": {
                m: summarize_trades(filter_milestone_trades(oos_all, m)) for m in milestones
            },
        }

    # Aggregate performance by 5 Asset Archetypes (G1..G5)
    archetype_names = [
        "G1_STORE_OF_VALUE_MAJOR",
        "G2_LIQUID_L1_L2_DEFI",
        "G3_HIGH_BETA_NARRATIVE_MIDCAP",
        "G4_LIQUID_MEME_RETAIL",
        "G5_THIN_OR_MANIPULATED",
    ]
    by_archetype: dict[str, Any] = {}
    for a_name in archetype_names:
        sub = [r for r in symbol_results if r["archetype"] == a_name]
        is_all = [x for r in sub for x in r["is_items"]]
        oos_all = [x for r in sub for x in r["oos_items"]]
        avg_grav = (
            round(float(np.mean([r["gravity_decay_rate_pct"] for r in sub if r["pump_50_count_is"] > 0])), 1)
            if any(r["pump_50_count_is"] > 0 for r in sub)
            else 0.0
        )
        by_archetype[a_name] = {
            "coin_count": len(sub),
            "avg_gravity_decay_pct": avg_grav,
            "is_2024_2025": {
                m: summarize_trades(filter_milestone_trades(is_all, m)) for m in milestones
            },
            "oos_2026": {
                m: summarize_trades(filter_milestone_trades(oos_all, m)) for m in milestones
            },
        }

    # Aggregate performance by Liquidity Tier (L1..L4)
    by_liquidity: dict[str, Any] = {}
    for l_name in ("L1_MEGA", "L2_DEEP", "L3_MID", "L4_THIN"):
        sub = [r for r in symbol_results if r["liq_tier"] == l_name]
        is_all = [x for r in sub for x in r["is_items"]]
        oos_all = [x for r in sub for x in r["oos_items"]]
        by_liquidity[l_name] = {
            "coin_count": len(sub),
            "is_2024_2025": {
                m: summarize_trades(filter_milestone_trades(is_all, m)) for m in milestones
            },
            "oos_2026": {
                m: summarize_trades(filter_milestone_trades(oos_all, m)) for m in milestones
            },
        }

    # Aggregate performance by Circulating Market Cap Tier (Non-G1)
    mcap_groups = {
        "MC1_LARGE_CAP_2B_PLUS": lambda r: r["archetype"] != "G1_STORE_OF_VALUE_MAJOR" and r["mcap_tier"] == "MC1_LARGE_CAP_2B_PLUS",
        "MC2_UPPER_MID_500M_2B": lambda r: r["archetype"] != "G1_STORE_OF_VALUE_MAJOR" and r["mcap_tier"] == "MC2_UPPER_MID_500M_2B",
        "MC3_LOWER_MID_150M_500M": lambda r: r["archetype"] != "G1_STORE_OF_VALUE_MAJOR" and r["mcap_tier"] == "MC3_LOWER_MID_150M_500M",
        "MC4_SMALL_CAP_50M_150M": lambda r: r["archetype"] != "G1_STORE_OF_VALUE_MAJOR" and r["mcap_tier"] == "MC4_SMALL_CAP_50M_150M",
        "MC5_MICRO_UNDER_50M": lambda r: r["archetype"] != "G1_STORE_OF_VALUE_MAJOR" and r["mcap_tier"] == "MC5_MICRO_UNDER_50M",
        "MCAP_150M_PLUS_SAFE": lambda r: r["archetype"] != "G1_STORE_OF_VALUE_MAJOR" and r["mcap_usd"] >= 150_000_000.0,
        "MCAP_UNDER_150M_CORNERED": lambda r: r["archetype"] != "G1_STORE_OF_VALUE_MAJOR" and r["mcap_usd"] < 150_000_000.0,
    }
    by_market_cap: dict[str, Any] = {}
    for mc_name, pred in mcap_groups.items():
        sub = [r for r in symbol_results if pred(r)]
        is_all = [x for r in sub for x in r["is_items"]]
        oos_all = [x for r in sub for x in r["oos_items"]]
        by_market_cap[mc_name] = {
            "coin_count": len(sub),
            "is_2024_2025": {
                m: summarize_trades(filter_milestone_trades(is_all, m)) for m in milestones
            },
            "oos_2026": {
                m: summarize_trades(filter_milestone_trades(oos_all, m)) for m in milestones
            },
        }

    # Aggregate performance by Supply Float Ratio (Circulating / Total Supply) among MCap >= $150M
    float_groups = {
        "FLOAT_HIGH_75_PLUS": lambda r: r["archetype"] != "G1_STORE_OF_VALUE_MAJOR" and r["mcap_usd"] >= 150_000_000.0 and r["float_ratio"] >= 0.75,
        "FLOAT_MED_40_75": lambda r: r["archetype"] != "G1_STORE_OF_VALUE_MAJOR" and r["mcap_usd"] >= 150_000_000.0 and 0.40 <= r["float_ratio"] < 0.75,
        "FLOAT_LOW_UNDER_40": lambda r: r["archetype"] != "G1_STORE_OF_VALUE_MAJOR" and r["mcap_usd"] >= 150_000_000.0 and r["float_ratio"] < 0.40,
    }
    by_float_ratio: dict[str, Any] = {}
    for fl_name, pred in float_groups.items():
        sub = [r for r in symbol_results if pred(r)]
        is_all = [x for r in sub for x in r["is_items"]]
        oos_all = [x for r in sub for x in r["oos_items"]]
        by_float_ratio[fl_name] = {
            "coin_count": len(sub),
            "is_2024_2025": {
                m: summarize_trades(filter_milestone_trades(is_all, m)) for m in milestones
            },
            "oos_2026": {
                m: summarize_trades(filter_milestone_trades(oos_all, m)) for m in milestones
            },
        }

    # Sort symbol profiles by suitability_score descending, then IS Mốc 6B Net Return
    symbol_profiles.sort(
        key=lambda p: (
            p["universe_tier"] == "TIER_S_CORE",
            p["universe_tier"] == "TIER_A_EXTENDED",
            p["suitability_score"],
            p["is_2024_2025"]["m6_f4_expanded"]["total_net_return_pct"],
        ),
        reverse=True,
    )

    tier_s_symbols = [p["symbol"] for p in symbol_profiles if p["universe_tier"] == "TIER_S_CORE"]
    tier_a_symbols = [p["symbol"] for p in symbol_profiles if p["universe_tier"] == "TIER_A_EXTENDED"]
    pit_zero_bias_symbols = [p["symbol"] for p in symbol_profiles if p["in_pit_zero_bias_mcap_float"]]
    dynamic_symbols = [p["symbol"] for p in symbol_profiles if p["universe_tier"] == "DYNAMIC_POOL"]
    blacklist_symbols = sorted(
        list(
            set([p["symbol"] for p in symbol_profiles if p["universe_tier"] == "BLACKLIST"])
            | G1_STORE_OF_VALUE
            | STABLE_OR_INDEX_EXCLUDE
        )
    )

    study_payload = {
        "metadata": {
            "title": "340-Coin Universe Structural DNA, Market Cap / Float Ratio & Out-of-Sample Walk-Forward Selection Study (v1.2.0)",
            "total_symbols_scanned": len(symbol_results),
            "in_sample_window": "2024-01-01 -> 2025-12-31 (Strict Ex-Ante Selection Window)",
            "out_of_sample_window": "2026-01-01 -> 2026-09-29 (Blind Forward Validation Window)",
            "tier_counts": {
                "TIER_S_CORE": len(tier_s_symbols),
                "TIER_A_EXTENDED": len(tier_a_symbols),
                "PIT_ZERO_BIAS_MCAP_FLOAT": len(pit_zero_bias_symbols),
                "DYNAMIC_POOL": len(dynamic_symbols),
                "BLACKLIST": len(blacklist_symbols),
            },
        },
        "by_universe_tier": by_universe_tier,
        "by_archetype": by_archetype,
        "by_liquidity": by_liquidity,
        "by_market_cap": by_market_cap,
        "by_float_ratio": by_float_ratio,
        "lists": {
            "tier_s_core": tier_s_symbols,
            "tier_a_extended": tier_a_symbols,
            "pit_zero_bias_mcap_float": pit_zero_bias_symbols,
            "dynamic_pool": dynamic_symbols,
            "blacklist_do_not_short": blacklist_symbols,
        },
        "symbol_profiles": symbol_profiles,
    }

    out_dir = ROOT_DIR / "artifacts" / "fibo_trend_short"
    out_dir.mkdir(parents=True, exist_ok=True)
    study_path = out_dir / "coin_universe_study_2026.json"
    study_path.write_text(json.dumps(study_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    config_payload = {
        "schema_version": "1.2.0",
        "updated_at": "2026-10-16",
        "selection_methodology": "Hybrid v1.2: Reference a1e6ca7d 63-Day Warmup + Circulating Market Cap >= $150M + Supply Float Ratio (Circulating/Total) >= 64% + Structural Archetype (G2/G4 Core + High-Float G3) + 2024-2025 IS Alignment (Validated on 2026 OOS)",
        "dynamic_new_listing_rules": {
            "min_listing_age_days": 63,
            "min_circulating_market_cap_usd": 150_000_000.0,
            "min_circulating_float_ratio": 0.64,
            "min_24h_quote_volume_usd": 10_000_000.0,
            "max_upper_wick_p90_pct": 3.5,
            "exclude_archetypes": ["G1_STORE_OF_VALUE_MAJOR", "G5_THIN_OR_MANIPULATED"],
        },
        "tier_s_core": tier_s_symbols,
        "tier_a_extended": tier_a_symbols,
        "pit_zero_bias_mcap_float": pit_zero_bias_symbols,
        "dynamic_pool": dynamic_symbols,
        "blacklist_do_not_short": blacklist_symbols,
    }
    config_path = out_dir / "fibo_coin_universe_config.json"
    config_path.write_text(json.dumps(config_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n================ UNIVERSE TIER WALK-FORWARD SUMMARY v1.2.0 (Mốc 6B Toàn Diện) ================")
    for t_name, t_data in by_universe_tier.items():
        is_m6 = t_data["is_2024_2025"]["m6_f4_expanded"]
        oos_m6 = t_data["oos_2026"]["m6_f4_expanded"]
        print(
            f"{t_name:34s} ({t_data['coin_count']:3d} coins) | "
            f"IS 24-25: N={is_m6['total_trades']:4d}, WR={is_m6['win_rate_pct']:5.1f}%, Net={is_m6['total_net_return_pct']:+8.1f}%, PF={is_m6['profit_factor']:4.2f}, DD={is_m6['max_drawdown_pct']:5.1f}% | "
            f"OOS 2026: N={oos_m6['total_trades']:3d}, WR={oos_m6['win_rate_pct']:5.1f}%, Net={oos_m6['total_net_return_pct']:+7.1f}%, PF={oos_m6['profit_factor']:4.2f}, DD={oos_m6['max_drawdown_pct']:4.1f}%"
        )

    print("\n================ CIRCULATING MARKET CAP SUMMARY (Mốc 6B Toàn Diện) ================")
    for mc_name, mc_data in by_market_cap.items():
        is_m6 = mc_data["is_2024_2025"]["m6_f4_expanded"]
        oos_m6 = mc_data["oos_2026"]["m6_f4_expanded"]
        print(
            f"{mc_name:34s} ({mc_data['coin_count']:3d} coins) | "
            f"IS 24-25: N={is_m6['total_trades']:4d}, Net={is_m6['total_net_return_pct']:+8.1f}%, PF={is_m6['profit_factor']:4.2f} | "
            f"OOS 2026: N={oos_m6['total_trades']:3d}, Net={oos_m6['total_net_return_pct']:+7.1f}%, PF={oos_m6['profit_factor']:4.2f}, DD={oos_m6['max_drawdown_pct']:4.1f}%"
        )

    print("\n================ SUPPLY FLOAT RATIO SUMMARY (Trên MCap >= $150M, Mốc 6B Toàn Diện) ================")
    for fl_name, fl_data in by_float_ratio.items():
        is_m6 = fl_data["is_2024_2025"]["m6_f4_expanded"]
        oos_m6 = fl_data["oos_2026"]["m6_f4_expanded"]
        print(
            f"{fl_name:34s} ({fl_data['coin_count']:3d} coins) | "
            f"IS 24-25: N={is_m6['total_trades']:4d}, Net={is_m6['total_net_return_pct']:+8.1f}%, PF={is_m6['profit_factor']:4.2f} | "
            f"OOS 2026: N={oos_m6['total_trades']:3d}, Net={oos_m6['total_net_return_pct']:+7.1f}%, PF={oos_m6['profit_factor']:4.2f}, DD={oos_m6['max_drawdown_pct']:4.1f}%"
        )

    print(f"\nSaved full study to: {study_path}")
    print(f"Saved universe config to: {config_path}")


if __name__ == "__main__":
    main()

