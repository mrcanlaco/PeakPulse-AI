"""Durable forward paper broker using public mainnet quotes.

Polling misses intrapoll touches; no exchange queue or historical margin-tier
attestation is claimed. Consequently this broker alone cannot unlock live.
"""

from __future__ import annotations

import time
from typing import Any

from .binance_api import BinanceExecutionClient


class PaperBroker:
    def __init__(self, config, store):
        self.config, self.store = config, store
        self.market = BinanceExecutionClient(config)
        self.data = store.get(
            "paper",
            {
                "wallet": 500.0,
                "positions": {},
                "orders": {},
                "fills": {},
                "income": [],
                "funding_cursor": int(time.time() * 1000),
            },
        )

    def save(self):
        self.store.set("paper", self.data)

    def preflight(self):
        return None

    def prepare_symbol(self, symbol):
        return None

    def quote(self, symbol):
        return self.market.quote(symbol)

    def get_symbol_rules(self, symbol):
        return self.market.get_symbol_rules(symbol)

    def sync(self):
        now = int(time.time() * 1000)
        # Work on a copy: an incomplete provider request must not persist half
        # the funding cursor alongside an already applied cash flow.
        import copy

        before = copy.deepcopy(self.data)
        try:
            for symbol, pos in list(self.data["positions"].items()):
                mark = self.market._request(
                    "GET", "/fapi/v1/premiumIndex", {"symbol": symbol}, auth=False
                )
                pos["markPrice"] = float(mark["markPrice"])
                start = self.data["funding_cursor"] + 1
                while start <= now:
                    rows = self.market._request(
                        "GET",
                        "/fapi/v1/fundingRate",
                        {
                            "symbol": symbol,
                            "startTime": start,
                            "endTime": now,
                            "limit": 1000,
                        },
                        auth=False,
                    )
                    for row in rows:
                        at = int(row["fundingTime"])
                        if at <= pos["opened_at"]:
                            continue
                        amount = (
                            abs(pos["positionAmt"])
                            * float(row["markPrice"])
                            * float(row["fundingRate"])
                        )
                        self.data["wallet"] += amount
                        self.data["income"].append(
                            {
                                "tranId": f"{symbol}:{at}",
                                "incomeType": "FUNDING_FEE",
                                "symbol": symbol,
                                "income": str(amount),
                                "asset": "USDT",
                                "time": at,
                            }
                        )
                    if len(rows) < 1000:
                        break
                    next_start = int(rows[-1]["fundingTime"]) + 1
                    if next_start <= start:
                        raise ValueError("funding_pagination_stalled")
                    start = next_start
            self.data["funding_cursor"] = now
            for order in list(self.data["orders"].values()):
                if order["status"] == "NEW" and self.quote(order["symbol"])[
                    "ask"
                ] <= float(order["price"]):
                    self._fill(order, float(order["price"]))
            self.save()
        except Exception:
            self.data = before
            raise

    def account(self) -> dict[str, Any]:
        unrealized = sum(
            (p["entryPrice"] - p["markPrice"]) * abs(p["positionAmt"])
            for p in self.data["positions"].values()
        )
        reserved = sum(
            abs(p["positionAmt"]) * p["markPrice"] / 5
            for p in self.data["positions"].values()
        )
        equity = self.data["wallet"] + unrealized
        return {
            "wallet": self.data["wallet"],
            "equity": equity,
            "available": equity - reserved,
            "unrealized": unrealized,
            "maintenance_margin": None,
            "financially_verified": False,
        }

    def get_open_positions(self):
        return list(self.data["positions"].values())

    def open_orders(self):
        return [o for o in self.data["orders"].values() if o["status"] == "NEW"]

    def algo_orders(self):
        return []

    def order(self, symbol, client_id):
        return self.data["orders"].get(client_id)

    def _fill(self, order, price):
        symbol = order["symbol"]
        qty = float(order["origQty"])
        if order["side"] == "SELL":
            if symbol in self.data["positions"]:
                raise ValueError("duplicate_position")
            self.data["positions"][symbol] = {
                "symbol": symbol,
                "positionAmt": -qty,
                "entryPrice": price,
                "markPrice": price,
                "opened_at": int(time.time() * 1000),
                "positionSide": "BOTH",
            }
        else:
            position = self.data["positions"].get(symbol)
            if not position or not order["reduceOnly"]:
                order["status"] = "EXPIRED"
                return
            qty = min(qty, abs(position["positionAmt"]))
            self.data["wallet"] += qty * (position["entryPrice"] - price)
            position["positionAmt"] += qty
            if abs(position["positionAmt"]) < 1e-12:
                del self.data["positions"][symbol]
        fee = qty * price * self.config.fee_rate
        self.data["wallet"] -= fee
        order.update(
            status="FILLED",
            executedQty=str(qty),
            avgPrice=str(price),
            updateTime=int(time.time() * 1000),
        )
        self.data["fills"][order["orderId"]] = [
            {
                "id": order["orderId"],
                "qty": str(qty),
                "price": str(price),
                "commission": str(fee),
                "commissionAsset": "USDT",
                "time": int(time.time() * 1000),
            }
        ]

    def submit(self, symbol, client_id, side, qty, *, price=None, reduce_only=False):
        if client_id in self.data["orders"]:
            return self.data["orders"][client_id]
        order = {
            "symbol": symbol,
            "clientOrderId": client_id,
            "orderId": client_id,
            "status": "NEW",
            "side": side,
            "origQty": str(qty),
            "executedQty": "0",
            "price": str(price or 0),
            "reduceOnly": reduce_only,
        }
        self.data["orders"][client_id] = order
        if price is None:
            quote = self.quote(symbol)
            self._fill(order, quote["bid"] if side == "SELL" else quote["ask"])
        self.save()
        return order

    def cancel(self, symbol, client_id):
        order = self.data["orders"][client_id]
        if order["status"] == "NEW":
            order["status"] = "CANCELED"
        self.save()
        return order

    def fills(self, symbol, order_id):
        return self.data["fills"].get(order_id, [])

    def income(self, start_ms, end_ms):
        return [r for r in self.data["income"] if start_ms <= r["time"] <= end_ms]
