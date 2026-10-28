"""Binance USD-M adapter. Unknown submission outcomes must be reconciled."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from .contracts import floor_step


class ExchangeError(RuntimeError):
    def __init__(self, code: int, uncertain: bool = False):
        super().__init__(f"binance_error_{code}")
        self.code = code
        self.uncertain = uncertain


def format_to_step(value: float, step_size: str) -> str:
    exponent = Decimal(step_size).as_tuple().exponent
    if not isinstance(exponent, int):
        raise ValueError("invalid_precision")
    decimals = max(0, -exponent)
    return f"{floor_step(value, step_size):.{decimals}f}"


class BinanceExecutionClient:
    def __init__(self, config):
        self.config = config
        self.base_url = (
            "https://demo-fapi.binance.com"
            if config.environment == "demo"
            else "https://fapi.binance.com"
        )
        self.api_key = (
            config.live_api_key if config.environment == "live" else config.api_key
        )
        self.api_secret = (
            config.live_api_secret
            if config.environment == "live"
            else config.api_secret
        )
        self.timeout_seconds = 10
        self.clock_offset = 0
        self.retry_after_monotonic = 0.0

    def _request(self, method, endpoint, params=None, auth=True, key_only=False, _retry=False):
        if time.monotonic() < self.retry_after_monotonic:
            raise ExchangeError(429)
        params = dict(params or {})
        if auth or key_only:
            if self.config.environment == "simulation":
                raise ValueError("simulation_cannot_use_private_exchange_api")
            if not self.api_key or (auth and not self.api_secret):
                raise ValueError("execution_credentials_missing")
            if (
                self.config.environment == "live"
                and method != "GET"
                and not self.config.live_activated
            ):
                raise ValueError("live_not_activated")
            if auth:
                params.update(
                    timestamp=int(time.time() * 1000) + self.clock_offset, recvWindow=15000
                )
        query = urlencode({k: v for k, v in params.items() if v is not None})
        if auth:
            signature = hmac.new(
                self.api_secret.encode(), query.encode(), hashlib.sha256
            ).hexdigest()
            query += "&signature=" + signature
        url = self.base_url + endpoint
        data = None
        if method == "GET":
            url += "?" + query
        else:
            data = query.encode()
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        if auth or key_only:
            req.add_header("X-MBX-APIKEY", self.api_key)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in (418, 429):
                try:
                    delay = float(
                        exc.headers.get("Retry-After", 900 if exc.code == 418 else 60)
                    )
                except (ValueError, TypeError):
                    delay = 60
                self.retry_after_monotonic = time.monotonic() + max(1, delay)
            try:
                payload = json.loads(exc.read())
                code = int(payload.get("code", exc.code))
            except (ValueError, TypeError):
                code = exc.code
            if code == -1021 and auth and not _retry:
                try:
                    self.synchronize_clock()
                    clean_params = {k: v for k, v in params.items() if k not in ("timestamp", "recvWindow", "signature")}
                    return self._request(method, endpoint, params=clean_params, auth=auth, key_only=key_only, _retry=True)
                except Exception:
                    pass
            raise ExchangeError(
                code,
                exc.code >= 500 or exc.code == 408 or code in {-1006, -1007, -4116},
            ) from None
        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ):
            raise ExchangeError(0, True) from None

    def synchronize_clock(self):
        self.clock_offset = int(
            self._request("GET", "/fapi/v1/time", auth=False)["serverTime"]
        ) - int(time.time() * 1000)

    def listen_key(self, method):
        return self._request(method, "/fapi/v1/listenKey", auth=False, key_only=True)

    def preflight(self):
        self.synchronize_clock()
        mode = self._request("GET", "/fapi/v1/positionSide/dual")
        assets = self._request("GET", "/fapi/v1/multiAssetsMargin")
        if (
            mode["dualSidePosition"] is not False
            or assets["multiAssetsMargin"] is not False
        ):
            raise ValueError("requires_one_way_single_asset")

    def get_symbol_rules(self, symbol):
        data = self._request("GET", "/fapi/v1/exchangeInfo", auth=False)
        for item in data["symbols"]:
            if item["symbol"] != symbol:
                continue
            if (
                item["status"] != "TRADING"
                or item["contractType"] != "PERPETUAL"
                or item["marginAsset"] != "USDT"
            ):
                raise ValueError("symbol_not_eligible")
            filters = {f["filterType"]: f for f in item["filters"]}
            lot, market, price, notional = (
                filters[k]
                for k in ("LOT_SIZE", "MARKET_LOT_SIZE", "PRICE_FILTER", "MIN_NOTIONAL")
            )
            return {
                "step_size": lot["stepSize"],
                "market_step": market["stepSize"],
                "min_qty": float(lot["minQty"]),
                "max_qty": float(lot["maxQty"]),
                "market_min_qty": float(market["minQty"]),
                "market_max_qty": float(market["maxQty"]),
                "tick_size": price["tickSize"],
                "min_notional": float(notional["notional"]),
            }
        raise ValueError("symbol_rules_missing")

    def quote(self, symbol):
        depth = self._request(
            "GET", "/fapi/v1/depth", {"symbol": symbol, "limit": 20}, auth=False
        )
        return {
            "bid": float(depth["bids"][0][0]),
            "ask": float(depth["asks"][0][0]),
            "bids": [[float(p), float(q)] for p, q in depth["bids"]],
            "asks": [[float(p), float(q)] for p, q in depth["asks"]],
        }

    def prepare_symbol(self, symbol):
        try:
            self._request(
                "POST",
                "/fapi/v1/marginType",
                {"symbol": symbol, "marginType": "CROSSED"},
            )
        except ExchangeError as exc:
            if exc.code != -4046:
                raise
        self._request("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": 5})
        rows = self._request("GET", "/fapi/v1/symbolConfig", {"symbol": symbol})
        if (
            not rows
            or rows[0]["marginType"] != "CROSSED"
            or int(rows[0]["leverage"]) != 5
        ):
            raise ValueError("cross_leverage_verification_failed")

    def account(self) -> dict[str, Any]:
        value = self._request("GET", "/fapi/v3/account")
        if not any(asset["asset"] == "USDT" for asset in value["assets"]):
            raise ValueError("usdt_collateral_missing")
        if any(
            asset["asset"] != "USDT" and float(asset["walletBalance"]) != 0
            for asset in value["assets"]
        ):
            raise ValueError("account_has_other_collateral")
        return {
            "wallet": float(value["totalWalletBalance"]),
            "equity": float(value["totalMarginBalance"]),
            "available": float(value["availableBalance"]),
            "unrealized": float(value["totalUnrealizedProfit"]),
            "maintenance_margin": float(value["totalMaintMargin"]),
        }

    def get_open_positions(self):
        rows = self._request("GET", "/fapi/v3/positionRisk")
        return [r for r in rows if float(r["positionAmt"]) != 0]

    def open_orders(self):
        return self._request("GET", "/fapi/v1/openOrders")

    def algo_orders(self):
        result = self._request("GET", "/fapi/v1/openAlgoOrders")
        return result if isinstance(result, list) else result.get("orders", [])

    def order(self, symbol, client_id):
        try:
            return self._request(
                "GET",
                "/fapi/v1/order",
                {"symbol": symbol, "origClientOrderId": client_id},
            )
        except ExchangeError as exc:
            if exc.code == -2013:
                return None
            raise

    def submit(self, symbol, client_id, side, qty, *, price=None, reduce_only=False):
        params = {
            "symbol": symbol,
            "newClientOrderId": client_id,
            "side": side,
            "quantity": qty,
            "positionSide": "BOTH",
            "newOrderRespType": "RESULT",
            "type": "LIMIT" if price is not None else "MARKET",
        }
        if price is not None:
            params.update(price=price, timeInForce="GTC")
        if reduce_only:
            params["reduceOnly"] = "true"
        return self._request("POST", "/fapi/v1/order", params)

    def cancel(self, symbol, client_id):
        return self._request(
            "DELETE",
            "/fapi/v1/order",
            {"symbol": symbol, "origClientOrderId": client_id},
        )

    def fills(self, symbol, order_id):
        rows = self._request(
            "GET",
            "/fapi/v1/userTrades",
            {"symbol": symbol, "orderId": order_id, "limit": 1000},
        )
        if len(rows) >= 1000:
            raise ValueError("fill_history_truncated")
        return rows

    def income(self, start_ms, end_ms):
        result = []
        page = 1
        while True:
            rows = self._request(
                "GET",
                "/fapi/v1/income",
                {"startTime": start_ms, "endTime": end_ms, "limit": 1000, "page": page},
            )
            result.extend(rows)
            if len(rows) < 1000:
                return result
            page += 1
            if page > 100:
                raise ValueError("income_history_truncated")
