"""Point-in-Time Backtest Engine for the Confirmed Reversal & Fibonacci Short branch.

IMPORTANT OOS PROTECTION RULE:
In-sample development backtests MUST end on or before ``2025-12-31T23:59:59+00:00``.
All data from ``2026-01-01T00:00:00+00:00`` onward is reserved strictly for
Out-of-Sample (OOS) validation.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Sequence

import pandas as pd

from dao_vang.config.settings import FiboTrendShortConfig
from dao_vang.fibo_short.detector import evaluate_symbol_timeframe

IN_SAMPLE_MAX_UTC = pd.Timestamp("2025-12-31 23:59:59+00:00")
OOS_START_UTC = pd.Timestamp("2026-01-01 00:00:00+00:00")

SHARED_1H_DIR = Path("D:/SharedMarketData/multiyear_2020_2026/klines_1h")
DATA_LAKE_5M_DIR = (
    Path("E:/Quant-trading/data_lake/klines/5m")
    if Path("E:/Quant-trading/data_lake/klines/5m").exists()
    else Path("C:/Quant-trading/data_lake/klines/5m")
)
PRE2024_5M_DIR = (
    Path("E:/Quant-trading/data_lake/development_pre2024/klines/5m")
    if Path("E:/Quant-trading/data_lake/development_pre2024/klines/5m").exists()
    else Path("C:/Quant-trading/data_lake/development_pre2024/klines/5m")
)


TerminalOutcomeLiteral = Literal[
    "TP3_FULL",
    "TP2_THEN_SL_AT_TP1",
    "TP2_THEN_TIME_EXIT",
    "TP1_THEN_SL_AT_BE",
    "TP1_THEN_TIME_EXIT",
    "INITIAL_STOP_LOSS",
    "NO_TP_TIME_EXIT",
    "TP3_FULL_EXIT",
    "RATCHETED_SL_AT_TP1_AFTER_TP2",
    "RATCHETED_SL_AT_BE_AFTER_TP1",
    "TIME_EXIT_AFTER_TP2",
    "TIME_EXIT_AFTER_TP1",
    "TIME_EXIT_NO_TP",
]


def derive_canonical_terminal_outcome(
    *,
    tp1_hit: bool,
    tp2_hit: bool,
    tp3_hit: bool,
    ratcheted_sl_hit: bool,
    time_exit_used: bool,
    outcome: str = "",
) -> TerminalOutcomeLiteral:
    """Return canonical terminal outcome string matching simulate_trade_v2."""
    if tp3_hit or outcome == "TP3_HIT":
        return "TP3_FULL"
    if tp2_hit:
        return "TP2_THEN_SL_AT_TP1" if ratcheted_sl_hit else "TP2_THEN_TIME_EXIT"
    if tp1_hit:
        return "TP1_THEN_SL_AT_BE" if ratcheted_sl_hit else "TP1_THEN_TIME_EXIT"
    if outcome == "STOP_LOSS" or (not tp1_hit and not time_exit_used):
        return "INITIAL_STOP_LOSS"
    return "NO_TP_TIME_EXIT"


@dataclass(slots=True)
class FiboBacktestTrade:
    """Single simulated trade from the Fibonacci Trend Short backtest."""

    trade_id: str
    symbol: str
    higher_timeframe: Literal["4h", "1d"]
    confirmation_tier: str
    pattern_name: str
    entry_time: str
    exit_time: str
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    exit_price: float
    outcome: Literal["TP3_HIT", "TP2_HIT", "TP1_HIT", "STOP_LOSS", "TIME_EXIT"]
    tp1_reached: bool
    tp2_reached: bool
    tp3_reached: bool
    gross_return_pct: float
    net_return_pct: float
    r_multiple: float
    hold_hours: int
    fibo_entry_ratio: float
    impulse_drop_pct: float
    prior_pump_pct: float = 0.0
    terminal_outcome: TerminalOutcomeLiteral = "NO_TP_TIME_EXIT"
    ratcheted_sl_hit: bool = False
    time_exit_used: bool = False
    decision_time: str = ""

    def __post_init__(self) -> None:
        if not self.decision_time:
            self.decision_time = self.entry_time
        if self.outcome == "TP3_HIT":
            self.tp1_reached = True
            self.tp2_reached = True
            self.tp3_reached = True
            self.ratcheted_sl_hit = False
            self.time_exit_used = False
        elif self.outcome == "STOP_LOSS":
            self.tp1_reached = False
            self.tp2_reached = False
            self.tp3_reached = False
            self.ratcheted_sl_hit = False
            self.time_exit_used = False
        elif self.outcome == "TIME_EXIT":
            self.tp1_reached = False
            self.tp2_reached = False
            self.tp3_reached = False
            self.ratcheted_sl_hit = False
            self.time_exit_used = True
        elif self.outcome == "TP2_HIT":
            self.tp1_reached = True
            self.tp2_reached = True
            self.tp3_reached = False
            if self.ratcheted_sl_hit != self.time_exit_used and self.terminal_outcome in (
                "TP2_THEN_SL_AT_TP1",
                "TP2_THEN_TIME_EXIT",
                "NO_TP_TIME_EXIT",
            ):
                pass
            elif self.terminal_outcome in ("TP2_THEN_SL_AT_TP1", "TP2_THEN_TIME_EXIT"):
                self.ratcheted_sl_hit = self.terminal_outcome == "TP2_THEN_SL_AT_TP1"
                self.time_exit_used = not self.ratcheted_sl_hit
            else:
                self.ratcheted_sl_hit = bool(self.exit_price == self.tp1)
                self.time_exit_used = not self.ratcheted_sl_hit
        elif self.outcome == "TP1_HIT":
            self.tp1_reached = True
            self.tp2_reached = False
            self.tp3_reached = False
            if self.ratcheted_sl_hit != self.time_exit_used and self.terminal_outcome in (
                "TP1_THEN_SL_AT_BE",
                "TP1_THEN_TIME_EXIT",
                "NO_TP_TIME_EXIT",
            ):
                pass
            elif self.terminal_outcome in ("TP1_THEN_SL_AT_BE", "TP1_THEN_TIME_EXIT"):
                self.ratcheted_sl_hit = self.terminal_outcome == "TP1_THEN_SL_AT_BE"
                self.time_exit_used = not self.ratcheted_sl_hit
            else:
                self.ratcheted_sl_hit = bool(self.exit_price == self.entry_price)
                self.time_exit_used = not self.ratcheted_sl_hit

        self.terminal_outcome = derive_canonical_terminal_outcome(
            tp1_hit=self.tp1_reached,
            tp2_hit=self.tp2_reached,
            tp3_hit=self.tp3_reached,
            ratcheted_sl_hit=self.ratcheted_sl_hit,
            time_exit_used=self.time_exit_used,
            outcome=self.outcome,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def enforce_in_sample_cutoff(
    end_ts: pd.Timestamp | str | datetime | None,
    *,
    strict: bool = True,
) -> pd.Timestamp:
    """Ensure backtest end timestamp never crosses into 2026+ OOS period."""
    if end_ts is None:
        return IN_SAMPLE_MAX_UTC
    parsed = pd.Timestamp(end_ts)
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize("UTC")
    else:
        parsed = parsed.tz_convert("UTC")

    if parsed > IN_SAMPLE_MAX_UTC:
        if strict:
            raise ValueError(
                f"OOS_PROTECTION_VIOLATION: Backtest end_date ({parsed.isoformat()}) "
                f"exceeds In-Sample cutoff ({IN_SAMPLE_MAX_UTC.isoformat()}). "
                "Data from 2026+ is reserved strictly for Out-of-Sample (OOS) testing."
            )
        return IN_SAMPLE_MAX_UTC
    return parsed


def resample_1h_to_htf(
    df_1h: pd.DataFrame,
    timeframe: Literal["4h", "1d"],
) -> pd.DataFrame:
    """Resample 1h OHLCV dataframe (indexed by UTC open_time) to complete 4h or 1d bars."""
    if df_1h.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "close_time"])

    df = df_1h
    if not isinstance(df.index, pd.DatetimeIndex):
        time_col = "open_time" if "open_time" in df.columns else "timestamp"
        df = df.copy()
        df[time_col] = pd.to_datetime(df[time_col], utc=True)
        df = df.set_index(time_col).sort_index()

    rule = "4h" if timeframe == "4h" else "1D"
    expected_bars = 4 if timeframe == "4h" else 24
    grouped = df.resample(rule, label="left", closed="left")
    agg = pd.DataFrame(
        {
            "open": grouped["open"].first(),
            "high": grouped["high"].max(),
            "low": grouped["low"].min(),
            "close": grouped["close"].last(),
            "volume": grouped["volume"].sum() if "volume" in df.columns else 0.0,
            "bar_count": grouped["open"].count(),
        }
    )
    # Keep only complete higher-timeframe bars to prevent intra-bar lookahead
    agg = agg[agg["bar_count"] == expected_bars].drop(columns=["bar_count"]).dropna()
    delta = pd.Timedelta(hours=expected_bars)
    agg["close_time"] = agg.index + delta
    return agg


def load_historical_1h_frame(
    symbol: str,
    *,
    start_utc: pd.Timestamp | str = "2024-01-01T00:00:00+00:00",
    end_utc: pd.Timestamp | str = IN_SAMPLE_MAX_UTC,
    strict_in_sample: bool = True,
) -> pd.DataFrame:
    """Load 1h historical OHLCV for a symbol, strictly clipped to <= 2025-12-31."""
    cutoff = enforce_in_sample_cutoff(end_utc, strict=strict_in_sample)
    start_ts = pd.Timestamp(start_utc)
    if start_ts.tzinfo is None:
        start_ts = start_ts.tz_localize("UTC")
    else:
        start_ts = start_ts.tz_convert("UTC")

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
        df = df.loc[(df.index >= start_ts) & (df.index <= cutoff)].copy()
        return df[["open", "high", "low", "close", "volume"]].astype(float)

    parts_5m: list[pd.DataFrame] = []
    if start_ts < pd.Timestamp("2024-01-01T00:00:00+00:00"):
        p_pre = PRE2024_5M_DIR / f"{symbol}.parquet"
        if p_pre.exists():
            d_pre = pd.read_parquet(
                p_pre,
                columns=["open_time", "open", "high", "low", "close", "volume"],
            )
            d_pre["open_time"] = pd.to_datetime(d_pre["open_time"], utc=True)
            d_pre = d_pre[(d_pre["open_time"] >= start_ts) & (d_pre["open_time"] <= cutoff)]
            if not d_pre.empty:
                parts_5m.append(d_pre)

    p_5m = DATA_LAKE_5M_DIR / f"{symbol}.parquet"
    if p_5m.exists() and cutoff >= pd.Timestamp("2024-01-01T00:00:00+00:00"):
        d_cur = pd.read_parquet(
            p_5m,
            columns=["open_time", "open", "high", "low", "close", "volume"],
        )
        d_cur["open_time"] = pd.to_datetime(d_cur["open_time"], utc=True)
        d_cur = d_cur[(d_cur["open_time"] >= start_ts) & (d_cur["open_time"] <= cutoff)]
        if not d_cur.empty:
            parts_5m.append(d_cur)

    if parts_5m:
        df5 = (
            pd.concat(parts_5m, ignore_index=True)
            .drop_duplicates(subset=["open_time"])
            .set_index("open_time")
            .sort_index()
        )
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

    raise FileNotFoundError(f"Historical data not found for {symbol} in SharedMarketData or data_lake")


def _simulate_trade_outcome(
    future_1h: Sequence[dict[str, Any]],
    *,
    entry_price: float,
    stop_loss: float,
    tp1: float,
    tp2: float,
    tp3: float,
    fee_bps: float = 10.0,
    round_trip_fee_bps: float | None = None,
    ratchet_mode: Literal["pessimistic_high", "close_rebound", "legacy"] = "pessimistic_high",
    return_exit_flags: bool = False,
) -> Any:
    """Simulate realistic staged short exit on subsequent 1h bars.

    Staged TP allocation:
    - 50% closed at TP1 (Fibo 0.0), stop loss moved to breakeven (entry_price).
    - 30% closed at TP2 (Fibo Ext 1.272), stop loss moved to TP1.
    - 20% closed at TP3 (Fibo Ext 1.618).
    Conservative intrabar rule:
    - Active SL is checked before any new TP touch on each bar.
    - When TP1 or TP2 is touched and active_sl is ratcheted down, `ratchet_mode="pessimistic_high"`
      immediately verifies whether `b_high >= active_sl` in the same bar (stopping out the
      remaining weight at the ratcheted SL rather than carrying it into subsequent bars).
    - `fee_bps` / `round_trip_fee_bps` are both expressed in total round-trip basis points
      (e.g., 10.0 = 0.10% round-trip, 20.0 = 0.20% round-trip).
    """
    effective_fee_bps = round_trip_fee_bps if round_trip_fee_bps is not None else fee_bps
    sl_risk = max(1e-9, stop_loss - entry_price)
    tp1_hit = False
    tp2_hit = False
    tp3_hit = False
    ratcheted_sl_hit = False
    time_exit_used = False
    remaining_weight = 1.0
    realized_gross_pct = 0.0
    active_sl = stop_loss
    exit_price = entry_price
    exit_time = str(future_1h[0].get("open_time_str") if future_1h else "")
    hold_hours = 0

    for idx, bar in enumerate(future_1h, start=1):
        b_high = float(bar["high"])
        b_low = float(bar["low"])
        b_close = float(bar["close"])
        b_time = str(bar.get("open_time_str") or bar.get("open_time"))
        hold_hours = idx

        # 1. Check active Stop Loss first (conservative)
        if b_high >= active_sl:
            stop_fill = max(active_sl, float(bar.get("open", active_sl)))
            loss_pct = (entry_price - stop_fill) / entry_price * 100.0
            realized_gross_pct += remaining_weight * loss_pct
            exit_price = stop_fill
            exit_time = b_time
            remaining_weight = 0.0
            if tp1_hit:
                ratcheted_sl_hit = True
            break

        # 2. Check TP1 (50% position, ratchet SL to breakeven = entry_price)
        if not tp1_hit and b_low <= tp1:
            tp1_hit = True
            gain1 = (entry_price - tp1) / entry_price * 100.0
            realized_gross_pct += 0.50 * gain1
            remaining_weight -= 0.50
            active_sl = entry_price  # Move SL to breakeven after TP1
            exit_price = tp1
            exit_time = b_time

            if (ratchet_mode == "pessimistic_high" and b_high >= active_sl) or (
                ratchet_mode == "close_rebound" and b_close >= active_sl
            ):
                loss_pct = (entry_price - active_sl) / entry_price * 100.0
                realized_gross_pct += remaining_weight * loss_pct
                exit_price = active_sl
                exit_time = b_time
                remaining_weight = 0.0
                ratcheted_sl_hit = True
                break

        # 3. Check TP2 (30% position, ratchet SL to TP1)
        if tp1_hit and not tp2_hit and b_low <= tp2:
            tp2_hit = True
            gain2 = (entry_price - tp2) / entry_price * 100.0
            realized_gross_pct += 0.30 * gain2
            remaining_weight -= 0.30
            active_sl = tp1  # Lock SL at TP1
            exit_price = tp2
            exit_time = b_time

            if (ratchet_mode == "pessimistic_high" and b_high >= active_sl) or (
                ratchet_mode == "close_rebound" and b_close >= active_sl
            ):
                loss_pct = (entry_price - active_sl) / entry_price * 100.0
                realized_gross_pct += remaining_weight * loss_pct
                exit_price = active_sl
                exit_time = b_time
                remaining_weight = 0.0
                ratcheted_sl_hit = True
                break

        # 4. Check TP3 (final 20% position)
        if tp2_hit and not tp3_hit and b_low <= tp3:
            tp3_hit = True
            gain3 = (entry_price - tp3) / entry_price * 100.0
            realized_gross_pct += 0.20 * gain3
            remaining_weight = 0.0
            exit_price = tp3
            exit_time = b_time
            break

    if remaining_weight > 0.0 and future_1h:
        last_bar = future_1h[-1]
        last_close = float(last_bar["close"])
        exit_price = last_close
        exit_time = str(last_bar.get("open_time_str") or last_bar.get("open_time"))
        realized_gross_pct += remaining_weight * ((entry_price - last_close) / entry_price * 100.0)
        time_exit_used = True

    fee_pct = effective_fee_bps / 100.0
    net_return_pct = realized_gross_pct - fee_pct
    sl_risk_pct = (sl_risk / entry_price) * 100.0
    r_multiple = net_return_pct / sl_risk_pct if sl_risk_pct > 0 else 0.0

    if tp3_hit:
        outcome: Literal["TP3_HIT", "TP2_HIT", "TP1_HIT", "STOP_LOSS", "TIME_EXIT"] = "TP3_HIT"
    elif tp2_hit:
        outcome = "TP2_HIT"
    elif tp1_hit:
        outcome = "TP1_HIT"
    elif remaining_weight == 0.0:
        outcome = "STOP_LOSS"
    else:
        outcome = "TIME_EXIT"

    if return_exit_flags:
        return (
            outcome,
            exit_price,
            exit_time,
            hold_hours,
            tp1_hit,
            tp2_hit,
            tp3_hit,
            realized_gross_pct,
            net_return_pct,
            r_multiple,
            ratcheted_sl_hit,
            time_exit_used,
        )
    return (
        outcome,
        exit_price,
        exit_time,
        hold_hours,
        tp1_hit,
        tp2_hit,
        tp3_hit,
        realized_gross_pct,
        net_return_pct,
        r_multiple,
    )


def classify_terminal_outcome(
    *,
    tp1_hit: bool,
    tp2_hit: bool,
    tp3_hit: bool,
    exit_price: float,
    entry_price: float,
    tp1_price: float,
    hold_hours: int,
    max_horizon_bars: int,
    ratcheted_sl_hit: bool | None = None,
    time_exit_used: bool | None = None,
) -> tuple[TerminalOutcomeLiteral, bool, bool]:
    """Classify the exact terminal exit reason separately from highest TP milestone reached."""
    if tp3_hit:
        return "TP3_FULL", False, False
    if tp2_hit:
        if ratcheted_sl_hit is not None and time_exit_used is not None and ratcheted_sl_hit != time_exit_used:
            return ("TP2_THEN_SL_AT_TP1" if ratcheted_sl_hit else "TP2_THEN_TIME_EXIT"), ratcheted_sl_hit, time_exit_used
        if exit_price == tp1_price:
            return "TP2_THEN_SL_AT_TP1", True, False
        return "TP2_THEN_TIME_EXIT", False, True
    if tp1_hit:
        if ratcheted_sl_hit is not None and time_exit_used is not None and ratcheted_sl_hit != time_exit_used:
            return ("TP1_THEN_SL_AT_BE" if ratcheted_sl_hit else "TP1_THEN_TIME_EXIT"), ratcheted_sl_hit, time_exit_used
        if exit_price == entry_price:
            return "TP1_THEN_SL_AT_BE", True, False
        return "TP1_THEN_TIME_EXIT", False, True
    if hold_hours < max_horizon_bars and exit_price > entry_price:
        return "INITIAL_STOP_LOSS", False, False
    return "NO_TP_TIME_EXIT", False, True


def backtest_symbol_1h_dataframe(
    symbol: str,
    df_1h: pd.DataFrame,
    config: FiboTrendShortConfig | None = None,
    *,
    strict_in_sample: bool = True,
) -> list[FiboBacktestTrade]:
    """Run Point-in-Time backtest on a 1h DataFrame for both H4 and D1 structures."""
    cfg = config or FiboTrendShortConfig()
    if df_1h.empty:
        return []

    df = df_1h.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        if "open_time" in df.columns:
            df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
            df = df.set_index("open_time")
        elif "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df = df.set_index("timestamp")
        else:
            raise ValueError("df_1h must have a UTC DatetimeIndex or open_time column")
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    max_ts = df.index.max()
    enforce_in_sample_cutoff(max_ts, strict=strict_in_sample)
    df = df.loc[df.index <= IN_SAMPLE_MAX_UTC].sort_index()
    if len(df) < 60:
        return []

    # Pre-build 1h records with close_time = open_time + 1h
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

    trades: list[FiboBacktestTrade] = []

    for tf in cfg.higher_timeframes:
        htf_df = resample_1h_to_htf(df, tf)
        if len(htf_df) < 8:
            continue

        htf_records: list[dict[str, Any]] = []
        htf_close_times: list[pd.Timestamp] = []
        for open_ts, row in htf_df.iterrows():
            c_ts = pd.Timestamp(row["close_time"])
            htf_close_times.append(c_ts)
            htf_records.append(
                {
                    "open_time": int(open_ts.timestamp() * 1000),
                    "open_time_str": open_ts.isoformat(),
                    "close_time_ts": c_ts,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0.0)),
                }
            )

        htf_ptr = 0
        n_htf = len(htf_records)
        cooldown_until_epoch_h = -1
        consumed_waves: set[str] = set()
        horizon = cfg.horizon_hours if tf == "4h" else max(cfg.horizon_hours, getattr(cfg, "horizon_hours_1d", 120))
        min_cd = getattr(cfg, "min_cooldown_hours", 4)

        for idx_1h in range(24, len(h1_records) - 2):
            current_decision_ts = h1_close_times[idx_1h]
            decision_epoch_h = int(current_decision_ts.timestamp() // 3600)
            if decision_epoch_h < cooldown_until_epoch_h:
                continue

            # Advance HTF pointer strictly to completed HTF bars with close_time <= current_decision_ts
            while htf_ptr < n_htf and htf_close_times[htf_ptr] <= current_decision_ts:
                htf_ptr += 1

            if htf_ptr < 6:
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
            if sig is None or sig.stage != "FIRED_CONFIRMED_SHORT":
                continue

            wave_key = f"{tf}:{sig.wave.swing_high_time}:{sig.wave.impulse_low_time}"
            if wave_key in consumed_waves:
                continue

            future_slice = h1_records[idx_1h + 1 : min(len(h1_records), idx_1h + 1 + horizon)]
            if not future_slice:
                continue

            (
                outcome,
                exit_price,
                exit_time,
                observed_bars,
                tp1_hit,
                tp2_hit,
                tp3_hit,
                gross_ret,
                net_ret,
                r_mult,
                sim_ratcheted_sl,
                sim_time_exit,
            ) = _simulate_trade_outcome(
                future_slice,
                entry_price=sig.trade_setup.entry_price,
                stop_loss=sig.trade_setup.stop_loss,
                tp1=sig.trade_setup.tp1,
                tp2=sig.trade_setup.tp2,
                tp3=sig.trade_setup.tp3,
                return_exit_flags=True,
            )

            if outcome == "STOP_LOSS":
                term_outcome: TerminalOutcomeLiteral = "INITIAL_STOP_LOSS"
                ratcheted_sl_hit = False
                time_exit_used = False
            elif outcome == "TIME_EXIT":
                term_outcome = "NO_TP_TIME_EXIT"
                ratcheted_sl_hit = False
                time_exit_used = True
            else:
                term_outcome, ratcheted_sl_hit, time_exit_used = classify_terminal_outcome(
                    tp1_hit=tp1_hit,
                    tp2_hit=tp2_hit,
                    tp3_hit=tp3_hit,
                    exit_price=exit_price,
                    entry_price=sig.trade_setup.entry_price,
                    tp1_price=sig.trade_setup.tp1,
                    hold_hours=observed_bars,
                    max_horizon_bars=len(future_slice),
                    ratcheted_sl_hit=sim_ratcheted_sl,
                    time_exit_used=sim_time_exit,
                )

            exit_bar_idx = max(0, min(len(future_slice) - 1, observed_bars - 1))
            exit_bar = future_slice[exit_bar_idx]
            exit_close_ts = (
                pd.Timestamp(exit_bar["close_time_ts"])
                if "close_time_ts" in exit_bar
                else (pd.Timestamp(exit_time) + pd.Timedelta(hours=1))
            )
            if exit_close_ts.tzinfo is None:
                exit_close_ts = exit_close_ts.tz_localize("UTC")
            else:
                exit_close_ts = exit_close_ts.tz_convert("UTC")
            exit_close_ts_str = exit_close_ts.isoformat()
            exit_close_epoch_h = int(exit_close_ts.timestamp() // 3600)
            real_hold_hours = max(1, exit_close_epoch_h - decision_epoch_h)

            consumed_waves.add(wave_key)
            cooldown_until_epoch_h = max(exit_close_epoch_h, decision_epoch_h + min_cd)

            trades.append(
                FiboBacktestTrade(
                    trade_id=f"{sig.id}_{decision_epoch_h}",
                    symbol=symbol,
                    higher_timeframe=tf,
                    confirmation_tier=sig.h1_confirmation.confirmation_tier,
                    pattern_name=sig.h1_confirmation.pattern_name,
                    entry_time=current_decision_ts.isoformat(),
                    exit_time=exit_close_ts_str,
                    entry_price=round(sig.trade_setup.entry_price, 8),
                    stop_loss=round(sig.trade_setup.stop_loss, 8),
                    tp1=round(sig.trade_setup.tp1, 8),
                    tp2=round(sig.trade_setup.tp2, 8),
                    tp3=round(sig.trade_setup.tp3, 8),
                    exit_price=round(exit_price, 8),
                    outcome=outcome,
                    tp1_reached=tp1_hit,
                    tp2_reached=tp2_hit,
                    tp3_reached=tp3_hit,
                    gross_return_pct=round(gross_ret, 4),
                    net_return_pct=round(net_ret, 4),
                    r_multiple=round(r_mult, 3),
                    hold_hours=real_hold_hours,
                    fibo_entry_ratio=sig.h1_confirmation.current_fibo_ratio,
                    impulse_drop_pct=round(sig.wave.impulse_drop_pct * 100.0, 2),
                    prior_pump_pct=round(sig.wave.prior_pump_pct * 100.0, 2),
                    terminal_outcome=term_outcome,
                    ratcheted_sl_hit=ratcheted_sl_hit,
                    time_exit_used=time_exit_used,
                    decision_time=current_decision_ts.isoformat(),
                )
            )

    return trades


def summarize_trades(trades: Sequence[FiboBacktestTrade]) -> dict[str, Any]:
    """Compute portfolio & breakdown metrics for a collection of FiboBacktestTrades."""
    total = len(trades)
    if total == 0:
        return {
            "total_trades": 0,
            "win_rate_pct": 0.0,
            "tp1_hit_rate_pct": 0.0,
            "tp2_hit_rate_pct": 0.0,
            "tp3_hit_rate_pct": 0.0,
            "avg_net_return_pct": 0.0,
            "total_net_return_pct": 0.0,
            "avg_r_multiple": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "outcomes": {},
            "terminal_outcomes": {},
            "ratcheted_sl_exit_count": 0,
            "time_exit_used_count": 0,
        }

    wins = [t for t in trades if t.net_return_pct > 0]
    losses = [t for t in trades if t.net_return_pct <= 0]
    gross_profit = sum(t.net_return_pct for t in wins)
    gross_loss = abs(sum(t.net_return_pct for t in losses))
    pf = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    # Calculate cumulative equity curve & max drawdown (assuming 1x per trade sequentially)
    ordered = sorted(trades, key=lambda x: x.entry_time)
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in ordered:
        cum += t.net_return_pct
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd

    outcomes_count: dict[str, int] = {}
    terminal_outcomes_count: dict[str, int] = {}
    ratcheted_count = 0
    time_exit_count = 0
    for t in trades:
        outcomes_count[t.outcome] = outcomes_count.get(t.outcome, 0) + 1
        t_out = getattr(t, "terminal_outcome", "TIME_EXIT_NO_TP")
        terminal_outcomes_count[t_out] = terminal_outcomes_count.get(t_out, 0) + 1
        if getattr(t, "ratcheted_sl_hit", False):
            ratcheted_count += 1
        if getattr(t, "time_exit_used", False):
            time_exit_count += 1

    return {
        "total_trades": total,
        "win_rate_pct": round(len(wins) / total * 100.0, 2),
        "tp1_hit_rate_pct": round(sum(1 for t in trades if t.tp1_reached) / total * 100.0, 2),
        "tp2_hit_rate_pct": round(sum(1 for t in trades if t.tp2_reached) / total * 100.0, 2),
        "tp3_hit_rate_pct": round(sum(1 for t in trades if t.tp3_reached) / total * 100.0, 2),
        "avg_net_return_pct": round(sum(t.net_return_pct for t in trades) / total, 3),
        "total_net_return_pct": round(sum(t.net_return_pct for t in trades), 2),
        "avg_r_multiple": round(sum(t.r_multiple for t in trades) / total, 3),
        "profit_factor": round(pf, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "outcomes": outcomes_count,
        "terminal_outcomes": terminal_outcomes_count,
        "ratcheted_sl_exit_count": ratcheted_count,
        "time_exit_used_count": time_exit_count,
    }


def run_in_sample_backtest_2025(
    symbols: Sequence[str] | None = None,
    *,
    start_utc: str = "2024-01-01T00:00:00+00:00",
    end_utc: str = "2025-12-31T23:59:59+00:00",
    config: FiboTrendShortConfig | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Run the multi-symbol In-Sample Backtest strictly up to 2025-12-31 (preserving 2026+ OOS)."""
    cfg = config or FiboTrendShortConfig()
    cutoff = enforce_in_sample_cutoff(end_utc, strict=True)

    if symbols is None:
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

    all_trades: list[FiboBacktestTrade] = []
    tested_symbols: list[str] = []

    for sym in symbols:
        try:
            df_1h = load_historical_1h_frame(
                sym,
                start_utc=start_utc,
                end_utc=cutoff,
                strict_in_sample=True,
            )
            if df_1h.empty:
                continue
            tested_symbols.append(sym)
            sym_trades = backtest_symbol_1h_dataframe(
                sym,
                df_1h,
                cfg,
                strict_in_sample=True,
            )
            all_trades.extend(sym_trades)
        except Exception:
            continue

    overall = summarize_trades(all_trades)
    by_timeframe = {
        tf: summarize_trades([t for t in all_trades if t.higher_timeframe == tf])
        for tf in ("4h", "1d")
    }
    by_confirmation_tier = {
        tier: summarize_trades([t for t in all_trades if t.confirmation_tier == tier])
        for tier in ("COMBO_1_2", "CANDLE_PATTERN_1", "BREAK_STRUCTURE_2")
    }
    by_symbol = {
        sym: summarize_trades([t for t in all_trades if t.symbol == sym])
        for sym in tested_symbols
    }

    report = {
        "strategy_branch": "fibo_trend_short",
        "strategy_name": "Xác Nhận Đảo Chiều & Short Theo Xu Hướng Mới (Fibonacci H4/D1 -> H1)",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "in_sample_window": {
            "start_utc": pd.Timestamp(start_utc).isoformat(),
            "end_utc": cutoff.isoformat(),
            "oos_reserved_from_utc": OOS_START_UTC.isoformat(),
            "oos_touched": False,
            "note": "Chỉ kiểm định In-Sample tới hết 31/12/2025. Toàn bộ dữ liệu từ 01/01/2026 trở đi được khóa hoàn toàn để dành làm Out-of-Sample (OOS).",
        },
        "config": cfg.model_dump(),
        "symbols_count": len(tested_symbols),
        "symbols": tested_symbols,
        "overall": overall,
        "by_timeframe": by_timeframe,
        "by_confirmation_tier": by_confirmation_tier,
        "by_symbol": by_symbol,
        "recent_trades": [
            t.to_dict()
            for t in sorted(all_trades, key=lambda x: x.entry_time, reverse=True)[:100]
        ],
    }

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return report
