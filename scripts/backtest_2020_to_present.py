#!/usr/bin/env python3
"""PeakPulse AI - Deep Multi-Year (2020 to Present) Backtest Engine.

Tự động kiểm tra dữ liệu Binance có sẵn trên máy (D:\\SharedMarketData\\multiyear_2020_2026\\).
Tự động tải phần còn thiếu từ Binance API cho đến thời điểm hiện tại.
Thực thi backtest không có lookahead bias, tính toán chi phí trượt giá và funding carry.
Xuất kết quả chi tiết từng năm (CAGR, MaxDD, Win Rate, Trades) từ 2020 đến nay.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Dynamic catalog import from local research snapshots
SNAPSHOT_DIR = Path(r"D:\QuantResearch\point72_cubist_deep_20261001\source_snapshots")
if str(SNAPSHOT_DIR) not in sys.path and SNAPSHOT_DIR.is_dir():
    sys.path.insert(0, str(SNAPSHOT_DIR))

import strategies_catalog_impl as sci

# Data directories on machine
DATA_DIR_1H = Path(r"D:\SharedMarketData\multiyear_2020_2026\klines_1h")
FUNDING_DIR_8H = Path(r"D:\SharedMarketData\multiyear_2020_2026\funding_8h")
REPORT_OUTPUT_DIR = REPO_ROOT / "artifacts"
REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

COST_SCENARIOS = {
    "standard": {
        "tier": "Binance VIP6 Institutional",
        "fee_bps": 1.5,
        "slippage_bps": 10.0,
        "total_bps": 11.5,
    },
    "stress": {
        "tier": "Binance VIP0 Retail / High Vol",
        "fee_bps": 5.0,
        "slippage_bps": 50.0,
        "total_bps": 55.0,
    },
}

REGIME_NOTES = {
    2020: "Bull Run Halving / DeFi Summer",
    2021: "Bull Market Peak / 19-May Crash",
    2022: "Deep Bear Market / Luna & FTX Collapse",
    2023: "Low-Vol Choppy Recovery",
    2024: "ETF Institutional Momentum",
    2025: "Late Cycle Altcoin Expansion",
    2026: "Current OOS Market Period",
}


# ==============================================================================
# 1. AUTO-DOWNLOADER (Tự động tải nến và funding thiếu từ Binance API)
# ==============================================================================

def fetch_binance_klines_since(symbol: str, start_time_ms: int) -> pd.DataFrame:
    """Tải các nến 1h từ Binance Futures API từ start_time_ms đến nay."""
    all_bars: List[List[Any]] = []
    current_start = start_time_ms
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    while current_start < now_ms:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1h&startTime={current_start}&limit=1000"
        req = urllib.request.Request(url, headers={"User-Agent": "PeakPulse-Backtest/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                batch = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            print(f"    [WARN] Loi tai Binance API klines {symbol}: {exc}")
            break

        if not batch:
            break

        all_bars.extend(batch)
        last_open_time = batch[-1][0]
        if len(batch) < 1000 or last_open_time <= current_start:
            break
        current_start = last_open_time + 3600000
        time.sleep(0.1)

    if not all_bars:
        return pd.DataFrame()

    df = pd.DataFrame(
        all_bars,
        columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "count", "taker_buy_volume",
            "taker_buy_quote_volume", "ignore"
        ]
    )
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df.index = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df[~df.index.duplicated(keep="last")]
    return df[["open", "high", "low", "close", "volume"]]


def fetch_binance_funding_since(symbol: str, start_time_ms: int) -> pd.DataFrame:
    """Tải funding rate từ Binance Futures API từ start_time_ms đến nay."""
    all_funding: List[Dict[str, Any]] = []
    current_start = start_time_ms
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    while current_start < now_ms:
        url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&startTime={current_start}&limit=1000"
        req = urllib.request.Request(url, headers={"User-Agent": "PeakPulse-Backtest/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                batch = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            print(f"    [WARN] Loi tai Binance API funding {symbol}: {exc}")
            break

        if not batch:
            break

        all_funding.extend(batch)
        last_funding_time = batch[-1]["fundingTime"]
        if len(batch) < 1000 or last_funding_time <= current_start:
            break
        current_start = last_funding_time + 1
        time.sleep(0.1)

    if not all_funding:
        return pd.DataFrame()

    df = pd.DataFrame(all_funding)
    df["funding_rate"] = df["fundingRate"].astype(float)
    df.index = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df = df[~df.index.duplicated(keep="last")]
    return df[["funding_rate"]]


def get_complete_1h_data(symbol: str) -> pd.DataFrame:
    """Đọc dữ liệu 1h từ ổ cứng và tự động tải bổ sung phần còn thiếu từ Binance API."""
    path = DATA_DIR_1H / f"{symbol}_1h.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"Khong tim thay file gia goc tren may: {path}")

    df_local = pd.read_parquet(path)
    if not isinstance(df_local.index, pd.DatetimeIndex):
        if "open_time" in df_local.columns:
            df_local.index = pd.to_datetime(df_local["open_time"], unit="ms", utc=True)
        elif "timestamp_utc" in df_local.columns:
            df_local.index = pd.to_datetime(df_local["timestamp_utc"], utc=True)

    df_local = df_local.sort_index()
    df_local = df_local[~df_local.index.duplicated(keep="first")]
    cols = ["open", "high", "low", "close", "volume"]
    df_local = df_local[cols]

    last_ts = df_local.index.max()
    now_utc = datetime.now(timezone.utc)
    gap_hours = (now_utc - last_ts).total_seconds() / 3600.0

    if gap_hours > 2.0:
        print(f"  [DATA] {symbol}: Du lieu tren may den {last_ts}. Dang tu dong tai them {gap_hours:.1f}h tu Binance...")
        start_ms = int(last_ts.timestamp() * 1000)
        df_missing = fetch_binance_klines_since(symbol, start_ms)
        if not df_missing.empty:
            df_combined = pd.concat([df_local, df_missing])
            df_combined = df_combined.sort_index()
            df_combined = df_combined[~df_combined.index.duplicated(keep="last")]
            print(f"  [DATA] {symbol}: Da dong bo thanh cong den {df_combined.index.max()} (Tong {len(df_combined):,} nến)")
            return df_combined

    return df_local


def get_complete_funding_data(symbol: str) -> pd.DataFrame:
    """Đọc funding rate từ ổ cứng và tải bổ sung nếu thiếu."""
    path = FUNDING_DIR_8H / f"{symbol}_funding.parquet"
    if not path.is_file():
        path = FUNDING_DIR_8H / "BTCUSDT_funding.parquet"

    df_local = pd.read_parquet(path)
    if not isinstance(df_local.index, pd.DatetimeIndex):
        if "timestamp_utc" in df_local.columns:
            df_local.index = pd.to_datetime(df_local["timestamp_utc"], utc=True)
        elif "calc_time" in df_local.columns:
            df_local.index = pd.to_datetime(df_local["calc_time"], unit="ms", utc=True)

    df_local = df_local.sort_index()
    df_local = df_local[~df_local.index.duplicated(keep="first")]
    rate_col = "last_funding_rate" if "last_funding_rate" in df_local.columns else df_local.columns[0]
    df_local = df_local[[rate_col]].rename(columns={rate_col: "funding_rate"})

    last_ts = df_local.index.max()
    now_utc = datetime.now(timezone.utc)
    gap_hours = (now_utc - last_ts).total_seconds() / 3600.0

    if gap_hours > 9.0:
        start_ms = int(last_ts.timestamp() * 1000)
        df_missing = fetch_binance_funding_since(symbol, start_ms)
        if not df_missing.empty:
            df_combined = pd.concat([df_local, df_missing])
            df_combined = df_combined.sort_index()
            df_combined = df_combined[~df_combined.index.duplicated(keep="last")]
            return df_combined

    return df_local


# ==============================================================================
# 2. SIMULATION ENGINE (Khớp lệnh Zero-Lookahead, Tính Phí và Funding Carry)
# ==============================================================================

def simulate_backtest(
    df: pd.DataFrame,
    target_pos: pd.Series,
    funding_df: Optional[pd.DataFrame] = None,
    start_dt: Optional[str] = None,
    end_dt: Optional[str] = None,
    initial_equity: float = 10000.0,
) -> Dict[str, Any]:
    """Mo phong backtest tuan thu nghiem ngat quy tac zero-lookahead.
    Tin hieu tai Close t duoc khop tai Open t+1."""
    df = df.copy()
    idx = df.index
    if start_dt:
        idx = idx[idx >= pd.to_datetime(start_dt, utc=True)]
    if end_dt:
        idx = idx[idx <= pd.to_datetime(end_dt, utc=True)]

    if len(idx) < 2:
        return {}

    exec_pos = target_pos.reindex(df.index).ffill().fillna(0.0).shift(1).fillna(0.0)
    bar_returns = df["close"].pct_change().fillna(0.0)

    funding_cost = pd.Series(0.0, index=df.index)
    if funding_df is not None and not funding_df.empty:
        f_floored = funding_df.copy()
        f_floored.index = f_floored.index.floor("h")
        f_floored = f_floored[~f_floored.index.duplicated(keep="first")]
        common_idx = f_floored.index.intersection(df.index)
        funding_cost.loc[common_idx] = f_floored.loc[common_idx, "funding_rate"].values

    eval_pos = exec_pos.loc[idx]
    eval_ret = bar_returns.loc[idx]
    eval_fund = funding_cost.loc[idx]

    days = max((idx[-1] - idx[0]).total_seconds() / 86400.0, 1.0)
    year_fraction = days / 365.25

    scenario_results: Dict[str, Any] = {}

    for sc_name, sc_params in COST_SCENARIOS.items():
        cost_rate = sc_params["total_bps"] / 10000.0
        pos_prev = eval_pos.shift(1).fillna(0.0)
        turnover = (eval_pos - pos_prev).abs()
        turnover_costs = turnover * cost_rate
        funding_payments = eval_pos * eval_fund

        net_ret = (eval_pos * eval_ret) - turnover_costs - funding_payments
        equity_curve = initial_equity * (1.0 + net_ret).cumprod()
        running_max = equity_curve.cummax()
        drawdown = (equity_curve - running_max) / running_max
        max_dd = float(drawdown.min())

        total_return = float((equity_curve.iloc[-1] / initial_equity) - 1.0)
        cagr = float(((1.0 + max(total_return, -0.9999)) ** (1.0 / max(year_fraction, 0.05))) - 1.0)
        calmar = cagr / abs(max_dd) if abs(max_dd) > 1e-6 else 0.0

        mean_h = net_ret.mean()
        std_h = net_ret.std()
        sharpe = float((mean_h / std_h * np.sqrt(8766.0)) if std_h > 1e-8 else 0.0)

        neg_rets = net_ret[net_ret < 0]
        downside_std = neg_rets.std() if len(neg_rets) > 0 else 0.0
        sortino = float((mean_h / downside_std * np.sqrt(8766.0)) if downside_std > 1e-8 else 0.0)

        # Parse individual trade outcomes
        trades: List[Dict[str, Any]] = []
        in_trade = False
        trade_start = None
        trade_rets: List[float] = []
        pos_vals = eval_pos.values
        ret_vals = net_ret.values
        ts_vals = eval_pos.index

        for i in range(len(pos_vals)):
            p = pos_vals[i]
            r = ret_vals[i]
            if not in_trade:
                if p > 0.01:
                    in_trade = True
                    trade_start = ts_vals[i]
                    trade_rets = [r]
            else:
                trade_rets.append(r)
                if p <= 0.01:
                    in_trade = False
                    dur_hours = (ts_vals[i] - trade_start).total_seconds() / 3600.0
                    trade_pnl = float(np.prod([1.0 + x for x in trade_rets]) - 1.0)
                    trades.append({
                        "start": trade_start,
                        "end": ts_vals[i],
                        "duration_hours": max(dur_hours, 1.0),
                        "pnl": trade_pnl,
                        "win": trade_pnl > 0.0,
                    })

        if in_trade:
            dur_hours = (ts_vals[-1] - trade_start).total_seconds() / 3600.0
            trade_pnl = float(np.prod([1.0 + x for x in trade_rets]) - 1.0)
            trades.append({
                "start": trade_start,
                "end": ts_vals[-1],
                "duration_hours": max(dur_hours, 1.0),
                "pnl": trade_pnl,
                "win": trade_pnl > 0.0,
            })

        trade_count = len(trades)
        wins = sum(1 for t in trades if t["win"])
        win_rate = (wins / trade_count * 100.0) if trade_count > 0 else 0.0
        avg_holding = float(np.mean([t["duration_hours"] for t in trades])) if trade_count > 0 else 0.0

        pos_pnls = [t["pnl"] for t in trades if t["pnl"] > 0]
        neg_pnls = [abs(t["pnl"]) for t in trades if t["pnl"] < 0]
        profit_factor = (sum(pos_pnls) / sum(neg_pnls)) if sum(neg_pnls) > 1e-8 else (99.0 if sum(pos_pnls) > 0 else 0.0)

        scenario_results[sc_name] = {
            "cagr": cagr,
            "total_return": total_return,
            "max_dd": max_dd,
            "calmar": calmar,
            "sharpe": sharpe,
            "sortino": sortino,
            "profit_factor": profit_factor,
            "win_rate": win_rate,
            "trades": trade_count,
            "avg_holding_hours": avg_holding,
            "final_equity": float(equity_curve.iloc[-1]),
        }

    return {
        "days": days,
        "start_dt": str(idx[0]),
        "end_dt": str(idx[-1]),
        "standard": scenario_results["standard"],
        "stress": scenario_results["stress"],
    }


def evaluate_yearly_breakdown(
    df: pd.DataFrame,
    target_pos: pd.Series,
    funding_df: Optional[pd.DataFrame] = None,
    initial_equity: float = 10000.0,
) -> List[Dict[str, Any]]:
    """Phan tich ket qua chi tiet tung nam tu 2020 den 2026."""
    years = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
    year_results: List[Dict[str, Any]] = []

    for y in years:
        start_y = f"{y}-01-01 00:00:00+00:00"
        end_y = f"{y+1}-01-01 00:00:00+00:00" if y < 2026 else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00")

        mask = (df.index >= pd.to_datetime(start_y, utc=True)) & (df.index <= pd.to_datetime(end_y, utc=True))
        if not mask.any() or mask.sum() < 240:
            year_results.append({
                "year": y,
                "available": False,
                "standard_return": None,
                "standard_max_dd": None,
                "standard_calmar": None,
                "standard_trades": None,
                "standard_win_rate": None,
                "standard_profit_factor": None,
                "stress_return": None,
                "stress_max_dd": None,
                "regime_note": "Chua niem yet / Khong du nến",
            })
            continue

        res_y = simulate_backtest(df, target_pos, funding_df, start_dt=start_y, end_dt=end_y, initial_equity=initial_equity)
        std = res_y["standard"]
        stress = res_y["stress"]

        year_results.append({
            "year": y,
            "available": True,
            "standard_return": std["total_return"],
            "standard_max_dd": std["max_dd"],
            "standard_calmar": std["calmar"],
            "standard_trades": std["trades"],
            "standard_win_rate": std["win_rate"],
            "standard_profit_factor": std["profit_factor"],
            "stress_return": stress["total_return"],
            "stress_max_dd": stress["max_dd"],
            "regime_note": REGIME_NOTES.get(y, "Market Cycle"),
        })

    return year_results


# ==============================================================================
# 3. CHIẾN LƯỢC BỔ SUNG: PEAKPULSE ALTCOIN DISTRIBUTION SHORT
# ==============================================================================

def generate_peakpulse_distribution_short(df: pd.DataFrame) -> pd.Series:
    """PeakPulse AI Core - Altcoin Distribution Short with ATR Risk Guard."""
    close = df["close"]
    high = df["high"]
    low = df["low"]

    ret24h = close / close.shift(24) - 1.0
    ret1h = close.pct_change(1)
    high24h = high.rolling(24).max()
    dist_high = close / high24h - 1.0

    tr = np.maximum(high - low, np.maximum((high - close.shift(1)).abs(), (low - close.shift(1)).abs()))
    atr14 = tr.rolling(14).mean()

    entry_short = (ret24h >= 0.15) & (dist_high <= -0.02) & (ret1h < 0.0)

    pos = pd.Series(0.0, index=df.index)
    in_short = False
    entry_price = 0.0
    entry_atr = 0.0
    hold_hours = 0
    min_seen = 0.0

    for i in range(len(close)):
        c = close.iloc[i]
        h = high.iloc[i]
        l = low.iloc[i]
        atr = atr14.iloc[i] if not pd.isna(atr14.iloc[i]) else 0.0

        if not in_short:
            if entry_short.iloc[i] and atr > 0:
                in_short = True
                entry_price = c
                entry_atr = atr
                hold_hours = 0
                min_seen = c
                pos.iloc[i] = 1.0
        else:
            hold_hours += 1
            min_seen = min(min_seen, l)
            loss_usdt_pct = (h - entry_price) / entry_price
            favorable_drop = (entry_price - min_seen) / entry_atr if entry_atr > 0 else 0.0
            bounce_from_bottom = (c - min_seen) / entry_atr if entry_atr > 0 else 0.0

            # 1. Stop loss (12% or 3 ATR)
            sl_triggered = (loss_usdt_pct >= 0.12) or ((h - entry_price) >= 3.0 * entry_atr)
            # 2. Trailing TP (favorable drop >= 1.5 ATR & callback >= 1.0 ATR)
            trailing_triggered = (favorable_drop >= 1.5) and (bounce_from_bottom >= 1.0)
            # 3. Max hold (72h)
            time_exit = hold_hours >= 72

            if sl_triggered or trailing_triggered or time_exit:
                in_short = False
                pos.iloc[i] = 0.0
            else:
                pos.iloc[i] = 1.0

    return pos


# ==============================================================================
# 4. CHƯƠNG TRÌNH ĐIỀU KHIỂN CHÍNH (MAIN ORCHESTRATION)
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Multi-Year Backtest (2020-Present)")
    parser.add_argument("--save-report", action="store_true", default=True, help="Luu ket qua ra file Markdown")
    args = parser.parse_args()

    print("=" * 80)
    print("   PEAKPULSE AI - MULTI-YEAR QUANTITATIVE BACKTEST (2020 - 2026)")
    print("   Du lieu: Binance USD-M Futures 1H | Mo phong phi: VIP6 Standard & Stress")
    print("=" * 80)

    # 1. Load and sync data
    print("\n[BƯỚC 1/3] Kiem tra du lieu tren may & Tu dong dong bo phan con thieu...")
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "LTCUSDT", "BCHUSDT"]
    data: Dict[str, pd.DataFrame] = {}
    funding: Dict[str, pd.DataFrame] = {}

    for sym in symbols:
        data[sym] = get_complete_1h_data(sym)
        funding[sym] = get_complete_funding_data(sym)

    # 2. Define Pods / Strategies
    print("\n[BƯỚC 2/3] Khoi chay Backtest Zero-Lookahead tu 2020 den 2026...")
    strategies_to_run = [
        {
            "id": "point72_cubist_eth_btc",
            "name": "Point72 Cubist Factor-Neutral Pair Arbitrage (ETH/BTC)",
            "symbol": "ETHUSDT",
            "benchmark": "BTCUSDT",
            "gen_func": lambda: sci.generate_strat9_point72_cubist(data["ETHUSDT"], data["BTCUSDT"]),
            "df": data["ETHUSDT"],
            "funding": funding["ETHUSDT"],
        },
        {
            "id": "langlois_cokurtosis_sol_btc",
            "name": "Langlois Co-Kurtosis Aligned Tail Protection (SOL/BTC)",
            "symbol": "SOLUSDT",
            "benchmark": "BTCUSDT",
            "gen_func": lambda: sci.generate_strat3_langlois_cokurt_sol(data["SOLUSDT"], data["BTCUSDT"]),
            "df": data["SOLUSDT"],
            "funding": funding["SOLUSDT"],
        },
        {
            "id": "fcvar_equilibrium_bch_btc",
            "name": "Johansen FCVAR Equilibrium Error Correction (BCH/BTC)",
            "symbol": "BCHUSDT",
            "benchmark": "BTCUSDT",
            "gen_func": lambda: sci.generate_strat2_fcvar_bch(data["BCHUSDT"], data["BTCUSDT"]),
            "df": data["BCHUSDT"],
            "funding": funding["BCHUSDT"],
        },
        {
            "id": "wavelet_cross_scale_eth_btc",
            "name": "Wavelet Cross-Scale Coherence (ETH/BTC)",
            "symbol": "ETHUSDT",
            "benchmark": "BTCUSDT",
            "gen_func": lambda: sci.generate_strat8_wavelet_eth(data["ETHUSDT"], data["BTCUSDT"]),
            "df": data["ETHUSDT"],
            "funding": funding["ETHUSDT"],
        },
        {
            "id": "rfsv_rough_scaling_ltc",
            "name": "RFSV Rough Volatility Scaling (LTC)",
            "symbol": "LTCUSDT",
            "benchmark": "BTCUSDT",
            "gen_func": lambda: sci.generate_strat1_rfsv_ltc(data["LTCUSDT"]),
            "df": data["LTCUSDT"],
            "funding": funding["LTCUSDT"],
        },
        {
            "id": "smart_money_dex_flow_bnb",
            "name": "Smart Money DEX Flow Gating (BNB)",
            "symbol": "BNBUSDT",
            "benchmark": "BTCUSDT",
            "gen_func": lambda: sci.generate_strat7_smart_money_dex_flow(data["BNBUSDT"]),
            "df": data["BNBUSDT"],
            "funding": funding["BNBUSDT"],
        },
        {
            "id": "peakpulse_distribution_short_sol",
            "name": "PeakPulse AI Altcoin Distribution Short + Trailing TP (SOL)",
            "symbol": "SOLUSDT",
            "benchmark": "BTCUSDT",
            "gen_func": lambda: generate_peakpulse_distribution_short(data["SOLUSDT"]),
            "df": data["SOLUSDT"],
            "funding": funding["SOLUSDT"],
        },
    ]

    all_results = []

    for strat in strategies_to_run:
        s_id = strat["id"]
        s_name = strat["name"]
        print(f"\n>> Dang tinh toan chien luoc: {s_name} ({strat['symbol']})...")
        t0 = time.time()
        pos = strat["gen_func"]()
        df_target = strat["df"]
        fund_target = strat["funding"]

        overall = simulate_backtest(df_target, pos, fund_target, start_dt="2020-01-01")
        yearly = evaluate_yearly_breakdown(df_target, pos, fund_target)
        elapsed = time.time() - t0

        std = overall["standard"]
        stress = overall["stress"]
        print(f"   [XONG in {elapsed:.2f}s] CAGR: {std['cagr']*100:+.2f}% | MaxDD: {std['max_dd']*100:.2f}% | Sharpe: {std['sharpe']:.2f} | WinRate: {std['win_rate']:.1f}%")

        all_results.append({
            "id": s_id,
            "name": s_name,
            "symbol": strat["symbol"],
            "overall": overall,
            "yearly": yearly,
        })

    # 3. Display Results
    print("\n" + "=" * 80)
    print("   [BƯỚC 3/3] BẢNG HIỂN THỊ KẾT QUẢ THEO TỪNG NĂM (2020 - 2026)")
    print("=" * 80)

    for item in all_results:
        std = item["overall"]["standard"]
        stress = item["overall"]["stress"]
        print(f"\n{'='*75}")
        print(f"CHIẾN LƯỢC: {item['name'].upper()} ({item['symbol']})")
        print(f"TỔNG THỂ (2020-2026):")
        print(f"  * Standard (VIP6) : CAGR = {std['cagr']*100:+.2f}% | MaxDD = {std['max_dd']*100:.2f}% | Sharpe = {std['sharpe']:.2f} | Calmar = {std['calmar']:.2f} | Trades = {std['trades']}")
        print(f"  * Stress (Retail) : CAGR = {stress['cagr']*100:+.2f}% | MaxDD = {stress['max_dd']*100:.2f}% | Sharpe = {stress['sharpe']:.2f} | Calmar = {stress['calmar']:.2f}")
        print(f"{'-'*75}")
        print(f"{'NĂM':<6} | {'STANDARD RETURN':<16} | {'STANDARD MAXDD':<15} | {'CALMAR':<7} | {'TRADES':<7} | {'STRESS RETURN':<15} | BỐI CẢNH THỊ TRƯỜNG")
        print(f"{'-'*75}")
        for yb in item["yearly"]:
            y = yb["year"]
            if not yb["available"]:
                print(f"{y:<6} | {'N/A (Chưa niêm yết)':<16} | {'-':<15} | {'-':<7} | {'-':<7} | {'-':<15} | {yb['regime_note']}")
            else:
                std_ret = f"{yb['standard_return']*100:+.2f}%"
                std_dd = f"{yb['standard_max_dd']*100:.2f}%"
                calm = f"{yb['standard_calmar']:.2f}"
                trd = f"{yb['standard_trades']}"
                str_ret = f"{yb['stress_return']*100:+.2f}%"
                print(f"{y:<6} | {std_ret:<16} | {std_dd:<15} | {calm:<7} | {trd:<7} | {str_ret:<15} | {yb['regime_note']}")
        print(f"{'='*75}")

    # Generate Markdown Report
    report_file = REPORT_OUTPUT_DIR / "backtest_2020_2026_annual_report.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# BÁO CÁO TOÀN DIỆN: BACKTEST TỪ 2020 ĐẾN NAY TRÊN DỮ LIỆU BINANCE\n\n")
        f.write(f"- **Thời điểm kiểm định:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
        f.write("- **Nguồn dữ liệu:** Binance USD-M Futures 1H (Đồng bộ từ 2020-01-01 đến 10/2026 liên tục)\n")
        f.write("- **Kiểm thử chi phí kép:** Standard (VIP6 Institutional - 11.5 bps) và Stress Test (VIP0 Retail - 55 bps + Funding Carry)\n\n")

        for item in all_results:
            std = item["overall"]["standard"]
            stress = item["overall"]["stress"]
            f.write(f"## {item['name']} ({item['symbol']})\n\n")
            f.write("### Hiệu Suất Tổng Thể Toàn Chu Kỳ (2020 - 2026)\n\n")
            f.write("| Chỉ Số Đo Lường | Phiên Bản Tiêu Chuẩn (VIP6) | Phiên Bản Stress Test (VIP0 Retail) |\n")
            f.write("|---|:---:|:---:|\n")
            f.write(f"| **CAGR (%/năm)** | **{std['cagr']*100:+.2f}%** | **{stress['cagr']*100:+.2f}%** |\n")
            f.write(f"| **Tổng Lợi Nhuận (Total Return)** | **{std['total_return']*100:+.2f}%** | **{stress['total_return']*100:+.2f}%** |\n")
            f.write(f"| **Max Drawdown (%)** | **{std['max_dd']*100:.2f}%** | **{stress['max_dd']*100:.2f}%** |\n")
            f.write(f"| **Calmar Ratio** | {std['calmar']:.2f} | {stress['calmar']:.2f} |\n")
            f.write(f"| **Sharpe Ratio** | {std['sharpe']:.2f} | {stress['sharpe']:.2f} |\n")
            f.write(f"| **Sortino Ratio** | {std['sortino']:.2f} | {stress['sortino']:.2f} |\n")
            f.write(f"| **Profit Factor** | {std['profit_factor']:.2f} | {stress['profit_factor']:.2f} |\n")
            f.write(f"| **Tỷ Lệ Thắng (Win Rate %)** | {std['win_rate']:.1f}% | {stress['win_rate']:.1f}% |\n")
            f.write(f"| **Tổng Số Lệnh (Trades)** | {std['trades']} | {stress['trades']} |\n")
            f.write(f"| **Thời Gian Giữ Lệnh TB** | {std['avg_holding_hours']:.1f} giờ / lệnh | {std['avg_holding_hours']:.1f} giờ / lệnh |\n\n")

            f.write("### Bảng Chi Tiết Từng Năm (Year-by-Year Breakdown)\n\n")
            f.write("| Năm | Lợi Nhuận Standard (%) | Max Drawdown (%) | Calmar | Số Lệnh | Lợi Nhuận Stress (%) | Bối Cảnh Chu Kỳ Thị Trường |\n")
            f.write("|:---:|:---:|:---:|:---:|:---:|:---:|---|\n")
            for yb in item["yearly"]:
                y = yb["year"]
                if not yb["available"]:
                    f.write(f"| **{y}** | *Chưa niêm yết* | - | - | - | - | {yb['regime_note']} |\n")
                else:
                    f.write(f"| **{y}** | **{yb['standard_return']*100:+.2f}%** | {yb['standard_max_dd']*100:.2f}% | {yb['standard_calmar']:.2f} | {yb['standard_trades']} | {yb['stress_return']*100:+.2f}% | {yb['regime_note']} |\n")
            f.write("\n---\n\n")

    print(f"\n[HOÀN THÀNH] Báo cáo chi tiết đã được xuất ra file: {report_file}")


if __name__ == "__main__":
    main()
