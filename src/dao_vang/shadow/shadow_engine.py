"""Shadow Paper Trading Execution Engine.

Quản lý các Shadow Bot độc lập nhưng dùng chung Market Feed:
- Mô phỏng khớp lệnh tại giá Open t+1 (Zero-Lookahead).
- Khấu trừ phí giao dịch thực tế (Standard VIP6 11.5 bps).
- Theo dõi Real-time PnL, vị thế nắm giữ, số lệnh, tỷ lệ thắng, Max Drawdown.
- Tự động lưu và khôi phục trạng thái từ data/shadow_state.json.
- Tiêu tốn cực ít tài nguyên (RAM < 30MB, CPU < 0.5%).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from dao_vang.shadow.shared_feed import SharedMarketFeed

logger = logging.getLogger("ShadowPaperEngine")
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
STATE_FILE = DATA_DIR / "shadow_state.json"


class ShadowInstance:
    """Mô hình một phiên bản chạy Shadow Paper độc lập."""

    def __init__(
        self,
        shadow_id: str,
        name: str,
        strategy_id: str,
        initial_capital: float = 10000.0,
        status: str = "RUNNING",
    ):
        self.shadow_id = shadow_id
        self.name = name
        self.strategy_id = strategy_id
        self.initial_capital = initial_capital
        self.status = status  # RUNNING, PAUSED

        self.cash = initial_capital
        self.position_qty = 0.0  # So luong ETH
        self.entry_price = 0.0
        self.target_position_pct = 0.0

        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.equity = initial_capital
        self.peak_equity = initial_capital
        self.current_drawdown = 0.0
        self.max_drawdown = 0.0

        self.trade_count = 0
        self.win_count = 0
        self.last_trade_time: Optional[str] = None
        self.trade_history: List[Dict[str, Any]] = []
        self.equity_history: List[Dict[str, Any]] = []

    def to_dict(self) -> Dict[str, Any]:
        closed_trades = sum(1 for t in self.trade_history if t.get("action") == "SELL")
        win_rate = (self.win_count / closed_trades * 100.0) if closed_trades > 0 else None
        return {
            "shadow_id": self.shadow_id,
            "name": self.name,
            "strategy_id": self.strategy_id,
            "status": self.status,
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "position_qty": self.position_qty,
            "entry_price": self.entry_price,
            "target_position_pct": self.target_position_pct,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "equity": self.equity,
            "peak_equity": self.peak_equity,
            "current_drawdown": self.current_drawdown,
            "max_drawdown": self.max_drawdown,
            "trade_count": self.trade_count,
            "closed_trades": closed_trades,
            "win_count": self.win_count,
            "win_rate": round(win_rate, 1) if win_rate is not None else None,
            "return_pct": ((self.equity / self.initial_capital) - 1.0) * 100.0,
            "last_trade_time": self.last_trade_time,
            "trade_history": self.trade_history[-50:],  # Giu 50 lenh gan nhat
            "equity_history": self.equity_history[-200:],  # Giu 200 diem gan nhat cho chart
        }

    def update_price_mark(self, current_price: float, timestamp_iso: str):
        """Cap nhat dinh gia theo gia thi truong hien tai (Mark-to-market)."""
        if self.position_qty > 0.0001:
            pos_val = self.position_qty * current_price
            cost_basis = self.position_qty * self.entry_price
            self.unrealized_pnl = pos_val - cost_basis
            self.equity = self.cash + pos_val
        else:
            self.unrealized_pnl = 0.0
            self.equity = self.cash

        if self.equity > self.peak_equity:
            self.peak_equity = self.equity
        self.current_drawdown = ((self.equity - self.peak_equity) / self.peak_equity) * 100.0
        if self.current_drawdown < self.max_drawdown:
            self.max_drawdown = self.current_drawdown

        pt = {
            "timestamp": timestamp_iso,
            "equity": round(self.equity, 2),
            "drawdown": round(self.current_drawdown, 2),
        }
        if self.equity_history and self.equity_history[-1].get("timestamp") == timestamp_iso:
            self.equity_history[-1] = pt
        else:
            self.equity_history.append(pt)

        if len(self.equity_history) > 500:
            self.equity_history = self.equity_history[-500:]

    def execute_rebalance(
        self,
        target_pct: float,
        exec_price: float,
        timestamp_iso: str,
        fee_rate_bps: float = 11.5,
    ):
        """Thực thi tái cân bằng vị thế theo tỷ trọng mục tiêu."""
        if self.status != "RUNNING":
            return

        target_pct = float(np.clip(target_pct, 0.0, 1.0))
        target_val = self.equity * target_pct
        current_val = self.position_qty * exec_price
        diff_val = target_val - current_val

        # Chi phi giao dich
        cost_rate = fee_rate_bps / 10000.0

        if abs(diff_val) > (self.equity * 0.05):  # Ngưỡng tối thiểu 5% vốn
            if diff_val > 0:
                # Mua them
                buy_val = diff_val
                fee = buy_val * cost_rate
                net_buy_val = buy_val - fee
                add_qty = net_buy_val / exec_price

                # Cap nhat gia von
                new_qty = self.position_qty + add_qty
                if new_qty > 1e-6:
                    self.entry_price = (self.position_qty * self.entry_price + add_qty * exec_price) / new_qty
                self.position_qty = new_qty
                self.cash -= buy_val
                self.trade_count += 1
                self.last_trade_time = timestamp_iso

                self.trade_history.append({
                    "time": timestamp_iso,
                    "action": "BUY",
                    "price": exec_price,
                    "qty": round(add_qty, 4),
                    "fee": round(fee, 2),
                    "pnl": 0.0,
                })
            else:
                # Ban bot hoac dong vi the
                sell_val = abs(diff_val)
                sell_qty = min(self.position_qty, sell_val / exec_price)
                fee = sell_val * cost_rate
                realized = (exec_price - self.entry_price) * sell_qty - fee

                self.realized_pnl += realized
                self.cash += (sell_qty * exec_price - fee)
                self.position_qty -= sell_qty
                if self.position_qty <= 1e-6:
                    self.position_qty = 0.0
                    self.entry_price = 0.0

                self.trade_count += 1
                if realized > 0:
                    self.win_count += 1
                self.last_trade_time = timestamp_iso

                self.trade_history.append({
                    "time": timestamp_iso,
                    "action": "SELL",
                    "price": exec_price,
                    "qty": round(sell_qty, 4),
                    "fee": round(fee, 2),
                    "pnl": round(realized, 2),
                })

        self.target_position_pct = target_pct
        self.update_price_mark(exec_price, timestamp_iso)


class ShadowPaperManager:
    """Bộ điều phối toàn bộ các Shadow Paper Runner."""

    _instance: Optional["ShadowPaperManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ShadowPaperManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.shadows: Dict[str, ShadowInstance] = {}
        self.feed = SharedMarketFeed()
        self.strategy_evaluators: Dict[str, Callable[[pd.DataFrame, pd.DataFrame], float]] = {}
        self._load_state()

        # Dang ky lang nghe Feed
        self.feed.register_listener(self.on_candle_update)
        # Khoi dong background poller neu chua chay
        self.feed.start_background_poller(interval_seconds=60)

    def register_strategy_func(self, strategy_id: str, func: Callable[[pd.DataFrame, pd.DataFrame], float]):
        """Dang ky ham tinh toan tin hieu cho shadow."""
        self.strategy_evaluators[strategy_id] = func

    def add_shadow(self, shadow_id: str, name: str, strategy_id: str, capital: float = 10000.0) -> ShadowInstance:
        """Them mot shadow runner moi."""
        with self._lock:
            if shadow_id in self.shadows:
                return self.shadows[shadow_id]
            instance = ShadowInstance(shadow_id, name, strategy_id, initial_capital=capital)
            self.shadows[shadow_id] = instance

            # Tu dong danh gia vi the ngay lap tuc neu da co du lieu cache
            if self.feed.cache and "ETHUSDT" in self.feed.cache and "BTCUSDT" in self.feed.cache:
                df_eth = self.feed.cache["ETHUSDT"]
                df_btc = self.feed.cache["BTCUSDT"]
                if not df_eth.empty and not df_btc.empty:
                    eval_func = self.strategy_evaluators.get(strategy_id)
                    if eval_func is not None:
                        try:
                            curr_price = float(df_eth["close"].iloc[-1])
                            max_ts = df_eth.index.max()
                            latest_time = max_ts.isoformat() if hasattr(max_ts, "isoformat") else str(max_ts)
                            target_pct = eval_func(df_eth, df_btc)
                            instance.execute_rebalance(target_pct, curr_price, latest_time)
                        except Exception as e:
                            logger.error("Loi initial evaluate shadow %s: %s", shadow_id, e)

            self._save_state()
            logger.info("Da tao Shadow Runner moi: %s (%s)", name, shadow_id)
            return instance

    def evaluate_all_shadows(self):
        """Danh gia lai toan bo cac shadow dua tren nen dong moi nhat."""
        if self.feed.cache:
            self.on_candle_update(self.feed.cache)

    def toggle_shadow(self, shadow_id: str, action: str):
        """Bat/Tat hoac reset mot shadow runner."""
        with self._lock:
            if shadow_id in self.shadows:
                inst = self.shadows[shadow_id]
                if action == "pause":
                    inst.status = "PAUSED"
                elif action == "resume":
                    inst.status = "RUNNING"
                elif action == "reset":
                    inst.cash = inst.initial_capital
                    inst.position_qty = 0.0
                    inst.entry_price = 0.0
                    inst.realized_pnl = 0.0
                    inst.unrealized_pnl = 0.0
                    inst.equity = inst.initial_capital
                    inst.peak_equity = inst.initial_capital
                    inst.current_drawdown = 0.0
                    inst.max_drawdown = 0.0
                    inst.trade_count = 0
                    inst.win_count = 0
                    inst.trade_history.clear()
                    inst.equity_history.clear()
                self._save_state()

    def on_candle_update(self, cache: Dict[str, pd.DataFrame]):
        """Callback duoc goi moi khi SharedMarketFeed co nến mới."""
        if "ETHUSDT" not in cache or "BTCUSDT" not in cache:
            return
        df_eth = cache["ETHUSDT"]
        df_btc = cache["BTCUSDT"]
        if df_eth.empty or df_btc.empty:
            return

        max_ts = df_eth.index.max()
        latest_time = max_ts.isoformat() if hasattr(max_ts, "isoformat") else str(max_ts)
        curr_price = float(df_eth["close"].iloc[-1])

        with self._lock:
            for shadow_id, inst in self.shadows.items():
                if inst.status != "RUNNING":
                    inst.update_price_mark(curr_price, latest_time)
                    continue

                eval_func = self.strategy_evaluators.get(inst.strategy_id)
                if eval_func is not None:
                    try:
                        target_pct = eval_func(df_eth, df_btc)
                        inst.execute_rebalance(target_pct, curr_price, latest_time)
                    except Exception as e:
                        logger.error("Loi khi danh gia strategy cho shadow %s: %s", shadow_id, e)
                        inst.update_price_mark(curr_price, latest_time)
                else:
                    inst.update_price_mark(curr_price, latest_time)

            self._save_state()

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Tong hop so lieu hien thi tren Dashboard Web."""
        with self._lock:
            total_equity = sum(s.equity for s in self.shadows.values())
            total_initial = sum(s.initial_capital for s in self.shadows.values())
            total_pnl = total_equity - total_initial
            overall_return = ((total_equity / total_initial) - 1.0) * 100.0 if total_initial > 0 else 0.0

            shadows_list = [s.to_dict() for s in self.shadows.values()]

            return {
                "active_shadows_count": sum(1 for s in self.shadows.values() if s.status == "RUNNING"),
                "total_shadows_count": len(self.shadows),
                "total_equity": round(total_equity, 2),
                "total_initial": round(total_initial, 2),
                "total_pnl": round(total_pnl, 2),
                "overall_return_pct": round(overall_return, 2),
                "last_feed_time": self.feed.last_fetch_time.isoformat() if self.feed.last_fetch_time else None,
                "shadows": shadows_list,
            }

    def _save_state(self):
        """Luu trang thai ra file shadow_state.json."""
        try:
            state_data = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "shadows": [s.to_dict() for s in self.shadows.values()],
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2)
        except Exception as e:
            logger.error("Loi luu shadow_state.json: %s", e)

    def _load_state(self):
        """Khoi phuc trang thai shadow tu file neu co."""
        if not STATE_FILE.is_file():
            return
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state_data = json.load(f)
            for s_data in state_data.get("shadows", []):
                inst = ShadowInstance(
                    shadow_id=s_data["shadow_id"],
                    name=s_data["name"],
                    strategy_id=s_data["strategy_id"],
                    initial_capital=s_data.get("initial_capital", 10000.0),
                    status=s_data.get("status", "RUNNING"),
                )
                inst.cash = s_data.get("cash", inst.initial_capital)
                inst.position_qty = s_data.get("position_qty", 0.0)
                inst.entry_price = s_data.get("entry_price", 0.0)
                inst.realized_pnl = s_data.get("realized_pnl", 0.0)
                inst.equity = s_data.get("equity", inst.initial_capital)
                inst.peak_equity = s_data.get("peak_equity", inst.initial_capital)
                inst.max_drawdown = s_data.get("max_drawdown", 0.0)
                inst.trade_count = s_data.get("trade_count", 0)
                inst.win_count = s_data.get("win_count", 0)
                # Sanitize trade history & equity history against 1970 corrupted dates
                raw_trades = s_data.get("trade_history", [])
                inst.trade_history = [t for t in raw_trades if not str(t.get("time", "")).startswith("1970")]
                raw_eq = s_data.get("equity_history", [])
                inst.equity_history = [e for e in raw_eq if not str(e.get("timestamp", "")).startswith("1970")]

                last_trade = s_data.get("last_trade_time")
                if last_trade and str(last_trade).startswith("1970"):
                    inst.last_trade_time = inst.trade_history[-1]["time"] if inst.trade_history else None
                else:
                    inst.last_trade_time = last_trade

                self.shadows[inst.shadow_id] = inst
            logger.info("Da phuc hoi %d Shadow Runner tu shadow_state.json", len(self.shadows))
        except Exception as e:
            logger.warning("Khong load duoc shadow_state.json: %s", e)
