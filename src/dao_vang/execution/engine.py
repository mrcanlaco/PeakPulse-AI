"""Single-owner execution service with write-ahead intents and reconciliation."""

from __future__ import annotations

import json
import math
import time
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path

from dao_vang.scanner.healthcheck import inspect_heartbeat
from dao_vang.scanner.instance_lock import ScannerInstanceLock

from .binance_api import BinanceExecutionClient, ExchangeError, format_to_step
from .contracts import (
    StrategyManifest,
    TradeSignal,
    digest,
    floor_step,
    source_contract,
    target_profit,
    tp_price,
    utc_now,
)
from .evidence import live_gate
from .paper import PaperBroker
from .sources import scanner_signals
from .store import ExecutionStore

TERMINAL = {"FILLED", "CANCELED", "EXPIRED", "REJECTED", "EXPIRED_IN_MATCH"}


class ExecutionEngine:
    def __init__(self, settings, db_path: Path, *, broker=None):
        self.app_settings = settings
        self.settings = settings.execution
        self.db_path = Path(db_path)
        self.directory = (
            settings.paths.data_dir / "execution" / self.settings.environment
        )
        self.store = ExecutionStore(self.directory / "state.sqlite3")
        self._api_client = broker
        self.manifest = None
        self.stream = None
        self._owns_lock = False
        self.root = Path(__file__).resolve().parents[3]

    def connect(self):
        if self.app_settings.account_monitor.enabled:
            raise ValueError("account_monitor_read_only")
        if self._api_client is None:
            self._api_client = (
                PaperBroker(self.settings, self.store)
                if self.settings.environment == "simulation"
                else BinanceExecutionClient(self.settings)
            )

    @property
    def broker(self) -> BinanceExecutionClient | PaperBroker:
        if self._api_client is None:
            raise ValueError("execution_not_connected")
        return self._api_client

    def pause(self, reason):
        current = self.store.get("pause", {})
        if current.get("reason") != reason or not current.get("paused"):
            self.store.set(
                "pause", {"paused": True, "reason": reason, "at": utc_now().isoformat()}
            )
            self.store.record("paused", {"reason": reason})

    def load_manifest(self):
        if not self.settings.manifest_path:
            raise ValueError("manifest_required")
        self.manifest = StrategyManifest.model_validate_json(
            self.settings.manifest_path.read_text(encoding="utf-8")
        )
        self.manifest.verify(self.root, self.settings)
        if self.manifest.source_policy != source_contract(self.app_settings.scanner):
            raise ValueError("scanner_policy_mismatch")
        self.store.set("manifest_id", self.manifest.identity)
        return self.manifest

    def _account(self):
        account = self.broker.account()
        if self.settings.environment == "live" and not self.store.get(
            "initial_wallet_verified", False
        ):
            if abs(account["wallet"] - 500) > 0.01:
                self.pause("initial_balance_must_be_500_usdt")
            else:
                self.store.set("initial_wallet_verified", True)
        for key in ("wallet", "equity", "available", "unrealized"):
            if not math.isfinite(account[key]):
                raise ValueError("account_not_finite")
        peak = max(
            self.store.get("equity_peak", self.settings.initial_equity),
            account["equity"],
        )
        self.store.set("equity_peak", peak)
        dd = 1 - account["equity"] / peak
        account.update(peak=peak, drawdown=dd, at=utc_now().isoformat())
        self.store.set("account", account)
        self.store.record("equity", account)
        if dd >= self.settings.entry_pause_drawdown - 1e-12:
            self.pause("drawdown_20_percent")
        return account

    def _income(self):
        now = int(time.time() * 1000)
        start = max(0, self.store.get("income_cursor", now) - 60_000)
        rows = self.broker.income(start, now)
        for row in rows:
            identity = f"{row['incomeType']}:{row['tranId']}:{row.get('symbol', '')}"
            self.store.money_event(identity, str(row["time"]), row["incomeType"], row)
            if row.get("incomeType") == "TRANSFER":
                self.pause("external_cashflow_detected")
        self.store.set("income_cursor", now)

    def _funding(self, trade):
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT payload FROM ledger WHERE kind='FUNDING_FEE'"
            ).fetchall()
        result = 0.0
        for row in rows:
            value = json.loads(row[0])
            if value.get("symbol") == trade["symbol"] and int(
                value["time"]
            ) > trade.get("entry_time_ms", 0):
                if value.get("asset") != "USDT":
                    raise ValueError("funding_asset_unsupported")
                result += float(value["income"])
        return result

    def _fills(self, trade, order):
        rows = self.broker.fills(trade["symbol"], order["orderId"])
        for row in rows:
            if row["commissionAsset"] != "USDT":
                raise ValueError("commission_asset_requires_conversion")
            self.store.money_event(
                f"fill:{trade['symbol']}:{row['id']}", str(row["time"]), "fill", row
            )
        if (
            not rows
            or abs(sum(float(r["qty"]) for r in rows) - float(order["executedQty"]))
            > 1e-9
        ):
            raise ValueError("fill_history_incomplete")
        return rows

    def reconcile(self):
        positions = {p["symbol"]: p for p in self.broker.get_open_positions()}
        trades = self.store.trades()
        if set(positions) - {t["symbol"] for t in trades}:
            self.pause("unmanaged_position")
        if self.broker.algo_orders():
            self.pause("unmanaged_algo_orders")
        known = {t.get(k) for t in trades for k in ("entry_id", "tp_id", "close_id")}
        if any(o["clientOrderId"] not in known for o in self.broker.open_orders()):
            self.pause("unmanaged_orders")
        for trade in trades:
            try:
                self._reconcile_trade(trade, positions.get(trade["symbol"]))
            except (ValueError, ExchangeError, KeyError) as exc:
                self.pause("reconciliation_required")
                self.store.record(
                    "reconcile_error", {"trade": trade["id"], "error": str(exc)}
                )
        self.store.set("positions", list(positions.values()))

    def _reconcile_trade(self, trade, position):
        if trade.get("recovered_without_intent"):
            self.pause("recovered_intent_requires_review")
            return
        entry = self.broker.order(trade["symbol"], trade["entry_id"])
        if entry is None:
            self.pause("entry_status_unknown")
            return  # Never resubmit an uncertain entry, including after restart.
        filled = float(entry["executedQty"])
        if entry["status"] not in TERMINAL:
            if filled:
                self.broker.cancel(trade["symbol"], trade["entry_id"])
            self.pause("entry_not_terminal")
            return
        if filled == 0:
            trade["status"] = "rejected"
            self.store.trade(trade)
            return
        fills = self._fills(trade, entry)
        entry_time_ms = trade.get("entry_time_ms")
        if entry_time_ms is None:
            entry_time_ms = min(int(r["time"]) for r in fills)
        trade.update(
            entry_price=sum(float(r["qty"]) * float(r["price"]) for r in fills)
            / filled,
            entry_fee=sum(float(r["commission"]) for r in fills),
            entry_time_ms=entry_time_ms,
            filled_qty=filled,
        )
        if "min_favorable_price" not in trade:
            trade["min_favorable_price"] = trade["entry_price"]
        exit_fills = trade.setdefault("exit_fills", {})
        if trade.get("close_id"):
            closed = self.broker.order(trade["symbol"], trade["close_id"])
            if closed is None or closed["status"] not in TERMINAL:
                self.pause("manual_close_unresolved")
                self.store.trade(trade)
                return
            if float(closed["executedQty"]):
                for fill in self._fills(trade, closed):
                    exit_fills[str(fill["id"])] = fill
        tp = (
            self.broker.order(trade["symbol"], trade["tp_id"])
            if trade.get("tp_id")
            else None
        )
        trade.update(
            last_reconciled_at=utc_now().isoformat(),
            tp_status=tp["status"] if tp else None,
        )
        if tp and float(tp["executedQty"]):
            for fill in self._fills(trade, tp):
                exit_fills[str(fill["id"])] = fill
        exited = sum(float(f["qty"]) for f in exit_fills.values())
        realized_gross = sum(
            float(f["qty"]) * (trade["entry_price"] - float(f["price"]))
            for f in exit_fills.values()
        )
        exit_fee = sum(float(f["commission"]) for f in exit_fills.values())
        trade.update(
            realized_gross=realized_gross,
            exit_fee=exit_fee,
            funding=self._funding(trade),
        )
        if position is None:
            if abs(exited - filled) > 1e-9:
                self.store.trade(trade)
                raise ValueError("position_missing_without_verified_exit")
            if tp and tp["status"] not in TERMINAL:
                self.broker.cancel(trade["symbol"], trade["tp_id"])
            trade.update(
                status="closed",
                closed_at=utc_now().isoformat(),
                net_pnl=realized_gross
                - trade["entry_fee"]
                - exit_fee
                + trade["funding"],
            )
            self.store.trade(trade)
            return
        if (
            float(position["positionAmt"]) >= 0
            or abs(float(position["positionAmt"])) > filled + 1e-9
        ):
            raise ValueError("position_direction_or_size_changed")
        qty = abs(float(position["positionAmt"]))
        if abs(qty - (filled - exited)) > 1e-9:
            self.store.trade(trade)
            raise ValueError("position_quantity_not_reconciled")
        trade.update(status="open", remaining_qty=qty, funding=self._funding(trade))
        self.store.trade(trade)

        # Pending automated risk close from previous cancellation cycle
        if trade.get("auto_close_pending"):
            if tp and tp["status"] not in TERMINAL:
                return
            trade["close_id"] = "dv-c-" + trade["id"][:24]
            trade["manual_close_requested"] = True
            self.store.trade(trade)
            self.broker.submit(
                trade["symbol"],
                trade["close_id"],
                "BUY",
                format_to_step(qty, trade["rules"]["step_size"]),
                reduce_only=True,
            )
            return

        if trade.get("manual_close_requested"):
            return

        # Automated risk exit checks (Stop Loss, Trailing TP, Max Hold Time)
        if self._check_risk_exits(trade, position, tp, qty):
            return
        # A partially filled TP keeps its price and remaining amount. Do not
        # reapply the whole original target to the remaining fraction.
        if tp and tp["status"] == "PARTIALLY_FILLED":
            return
        desired = tp_price(
            qty,
            trade["entry_price"],
            trade["target"] - realized_gross,
            trade["entry_fee"] + exit_fee,
            trade["funding"],
            self.settings.fee_rate,
            trade["rules"]["tick_size"],
        )
        if tp and tp["status"] == "NEW":
            if (
                abs(float(tp["price"]) - desired)
                < float(trade["rules"]["tick_size"]) / 2
            ):
                return
            self.broker.cancel(trade["symbol"], trade["tp_id"])
            # Reconcile again next poll: cancel can race a fill.
            return
        if trade.get("tp_id") and tp is None:
            self.pause("tp_status_unknown")
            return
        if tp and tp["status"] == "FILLED":
            raise ValueError("tp_filled_but_position_remains")
        if trade.get("close_id"):
            raise ValueError("manual_close_partial_requires_review")
        trade["tp_revision"] = trade.get("tp_revision", 0) + 1
        trade["tp_id"] = f"dv-t-{trade['id'][:20]}-{trade['tp_revision']}"
        trade["tp_price"] = desired
        trade["tp_status"] = None
        self.store.trade(trade)  # durable TP intent before network
        try:
            self.broker.submit(
                trade["symbol"],
                trade["tp_id"],
                "BUY",
                format_to_step(qty, trade["rules"]["step_size"]),
                price=str(desired),
                reduce_only=True,
            )
        except ExchangeError as exc:
            if not exc.uncertain:
                trade["tp_id"] = None  # definite rejection allows a new attempt
                self.store.trade(trade)
            raise

    def _check_risk_exits(self, trade, position, tp, qty) -> bool:
        if trade.get("manual_close_requested") or trade.get("close_id"):
            return False
        entry_price = float(trade.get("entry_price", 0.0))
        if entry_price <= 0:
            return False

        mark_price = float(position.get("markPrice") or entry_price)
        atr = float(trade.get("signal", {}).get("atr") or 0.0)
        now_ms = int(time.time() * 1000)
        entry_time_ms = trade.get("entry_time_ms") or now_ms
        age_hours = (now_ms - entry_time_ms) / 3600000.0

        # In a SHORT trade: loss occurs when mark_price > entry_price
        current_loss_usdt = qty * (mark_price - entry_price)
        loss_pct = (mark_price - entry_price) / entry_price

        exit_reason = None

        # 1. Stop-Loss Check (protects against explosive altcoin pumps)
        if getattr(self.settings, "enable_stop_loss", True):
            max_loss_usdt = getattr(self.settings, "sl_max_loss_usdt", 5.0)
            sl_atr_mult = getattr(self.settings, "sl_atr_multiplier", 3.0)
            stop_loss_pct = getattr(self.settings, "stop_loss_pct", 0.12)

            if current_loss_usdt >= max_loss_usdt:
                exit_reason = f"stop_loss_usdt_{round(current_loss_usdt, 2)}"
            elif atr > 0 and (mark_price - entry_price) >= sl_atr_mult * atr:
                exit_reason = f"stop_loss_atr_{round((mark_price - entry_price)/atr, 2)}"
            elif loss_pct >= stop_loss_pct:
                exit_reason = f"stop_loss_pct_{round(loss_pct * 100, 1)}pct"

        # 2. Max Hold Time Check (frees capital and avoids funding drag)
        if not exit_reason:
            max_hold = getattr(self.settings, "max_hold_hours", 72)
            if max_hold and age_hours >= max_hold:
                exit_reason = f"max_hold_hours_{round(age_hours, 1)}"

        # 3. Trailing Take-Profit Check (locks in big dump waves)
        if not exit_reason and getattr(self.settings, "enable_trailing_tp", True) and atr > 0:
            min_seen = min(trade.get("min_favorable_price", entry_price), mark_price)
            if min_seen != trade.get("min_favorable_price"):
                trade["min_favorable_price"] = min_seen
                self.store.trade(trade)
            favorable_drop = entry_price - min_seen
            trigger = getattr(self.settings, "trailing_trigger_atr", 1.5) * atr
            callback = getattr(self.settings, "trailing_callback_atr", 1.0) * atr

            if favorable_drop >= trigger and (mark_price - min_seen) >= callback:
                exit_reason = f"trailing_tp_locked_drop_{round(favorable_drop / atr, 2)}atr"

        if exit_reason:
            trade["auto_close_reason"] = exit_reason
            self.store.record(
                "risk_exit",
                {
                    "trade": trade["id"],
                    "symbol": trade["symbol"],
                    "reason": exit_reason,
                    "entry_price": entry_price,
                    "mark_price": mark_price,
                    "pnl_usdt": -current_loss_usdt,
                },
            )
            if tp and tp.get("status") not in TERMINAL:
                trade["auto_close_pending"] = exit_reason
                self.store.trade(trade)
                self.broker.cancel(trade["symbol"], trade["tp_id"])
                return True

            trade["close_id"] = "dv-c-" + trade["id"][:24]
            trade["manual_close_requested"] = True
            self.store.trade(trade)
            self.broker.submit(
                trade["symbol"],
                trade["close_id"],
                "BUY",
                format_to_step(qty, trade["rules"]["step_size"]),
                reduce_only=True,
            )
            return True

        return False

    def _commands(self):
        for cmd in self.store.commands():
            try:
                payload = json.loads(cmd["payload"])
                if cmd["action"] == "pause":
                    self.pause("user_paused")
                elif cmd["action"] == "resume":
                    account = self.store.get("account", {})
                    if account.get("drawdown", 1) >= 0.20 - 1e-12:
                        raise ValueError("drawdown_still_exceeded")
                    self.store.set("pause", {"paused": False, "reason": None})
                    self.store.record("user_resumed", {"command": cmd["id"]})
                elif cmd["action"] == "close":
                    if payload.get("confirm") is not True:
                        raise ValueError("manual_close_confirmation_required")
                    trade = next(
                        t
                        for t in self.store.trades(False)
                        if t["id"] == payload["trade_id"]
                    )
                    if trade["status"] == "closed":
                        self.store.complete_command(cmd["id"], "done")
                        continue
                    if trade.get("close_id"):
                        raise ValueError("close_already_requested")
                    trade["manual_close_requested"] = True
                    self.store.trade(trade)
                    if trade.get("tp_id"):
                        tp = self.broker.order(trade["symbol"], trade["tp_id"])
                        if tp is None:
                            raise ValueError("tp_status_unknown")
                        if tp["status"] not in TERMINAL:
                            self.broker.cancel(trade["symbol"], trade["tp_id"])
                            # Command remains pending until cancellation is confirmed.
                            continue
                    pos = next(
                        (
                            p
                            for p in self.broker.get_open_positions()
                            if p["symbol"] == trade["symbol"]
                        ),
                        None,
                    )
                    if pos is not None:
                        trade["close_id"] = "dv-c-" + trade["id"][:24]
                        self.store.trade(trade)
                        self.broker.submit(
                            trade["symbol"],
                            trade["close_id"],
                            "BUY",
                            format_to_step(
                                abs(float(pos["positionAmt"])),
                                trade["rules"]["step_size"],
                            ),
                            reduce_only=True,
                        )
                else:
                    raise ValueError("unknown_command")
                self.store.complete_command(cmd["id"], "done")
            except (ValueError, ExchangeError, StopIteration, KeyError) as exc:
                self.store.complete_command(cmd["id"], "failed:" + str(exc))
                self.pause("command_requires_review")

    def _enter(self, signal, account):
        if self.app_settings.account_monitor.enabled:
            return "account_monitor_read_only"
        now = utc_now()
        if not signal.eligible:
            return ",".join(signal.reasons) or "ineligible"
        if not signal.observed_at <= now < signal.expires_at:
            return "expired_or_future_signal"
        if self.manifest is None or signal.manifest_id != self.manifest.identity:
            return "manifest_mismatch"
        if (
            self.settings.environment == "live"
            and not live_gate(self.settings, self.manifest.identity)["eligible"]
        ):
            return "live_gate_failed"
        if self.settings.environment != "simulation":
            stream = self.store.get("user_stream", {})
            try:
                age = (now - datetime.fromisoformat(stream["at"])).total_seconds()
            except (KeyError, ValueError):
                age = 999
            if not stream.get("healthy") or not 0 <= age <= 30:
                return "user_stream_unavailable"
        if self.store.get("pause", {}).get("paused"):
            return "entries_paused"
        if any(
            t["signal"]["event_id"] == signal.event_id
            and t["signal"]["manifest_id"] == signal.manifest_id
            for t in self.store.trades(False)
        ):
            return "event_already_attempted"
        active = self.store.trades()
        if len(active) >= self.settings.max_open_positions:
            return "position_limit"
        if any(t["symbol"] == signal.symbol for t in active):
            return "duplicate_symbol"
        if account["available"] < 5 + 25 * self.settings.fee_rate * 2:
            return "insufficient_margin"
        rules = self.broker.get_symbol_rules(signal.symbol)
        quote = self.broker.quote(signal.symbol)
        bid, ask = quote["bid"], quote["ask"]
        if (
            not 0 < bid <= ask
            or (ask - bid) / bid * 10000 > self.settings.max_spread_bps
        ):
            return "spread_too_wide"
        if getattr(self.settings, "require_price_confirmation", False):
            if ask > signal.reference_price * 1.01:
                return "price_not_confirmed_down"
        # Size against ask plus allowed slippage so rounding never deliberately
        # increases the 25 USDT budget to satisfy an exchange minimum.
        qty = floor_step(
            25 / (ask * (1 + self.settings.max_slippage_bps / 10000)),
            rules["market_step"],
        )
        qty = floor_step(qty, rules["step_size"])
        if (
            not (
                max(rules["min_qty"], rules["market_min_qty"])
                <= qty
                <= min(rules["max_qty"], rules["market_max_qty"])
            )
            or qty * bid < rules["min_notional"]
        ):
            return "exchange_minimum_or_precision"
        acceptable_depth = sum(
            q
            for p, q in quote["bids"]
            if p >= bid * (1 - self.settings.max_slippage_bps / 10000)
        )
        if acceptable_depth < qty:
            return "insufficient_depth"
        target = target_profit(qty, bid, signal.atr, self.settings)
        self.broker.prepare_symbol(signal.symbol)
        identity = digest(
            {
                "signal": signal.event_id,
                "manifest": signal.manifest_id,
                "environment": self.settings.environment,
            }
        )
        trade = {
            "id": identity,
            "symbol": signal.symbol,
            "signal": signal.model_dump(mode="json"),
            "status": "entry_pending",
            "entry_id": "dv-e-" + identity[:24],
            "target": target,
            "requested_qty": qty,
            "rules": rules,
            "created_at": now.isoformat(),
        }
        # After a restored journal, a deterministic client id may already exist
        # on Binance even though the local record was lost.
        previous = self.broker.order(signal.symbol, trade["entry_id"])
        self.store.trade(trade)
        if previous is not None:
            trade["recovered_without_intent"] = True
            self.store.trade(trade)
            self.pause("recovered_exchange_entry")
            return "submitted"
        try:
            self.broker.submit(
                signal.symbol,
                trade["entry_id"],
                "SELL",
                format_to_step(qty, rules["market_step"]),
            )
        except ExchangeError as exc:
            if not exc.uncertain:
                trade["status"] = "rejected"
                self.store.trade(trade)
            self.pause("entry_submission_requires_reconciliation")
        return "submitted"

    def poll_signals(self):
        if not self.settings.enabled:
            return
        with (
            nullcontext()
            if self._owns_lock
            else ScannerInstanceLock(self.directory / "worker.lock")
        ):
            self.connect()
            try:
                self.broker.preflight()
                if isinstance(self.broker, PaperBroker):
                    self.broker.sync()
                self._income()
                self._account()
                self._commands()
                self.reconcile()
                account = self._account()
                manifest = self.load_manifest()
                gate = live_gate(self.settings, manifest.identity)
                self.store.set("live_gate", gate)
                if self.settings.environment == "live" and not gate["eligible"]:
                    self.pause("live_gate_failed")
                try:
                    health = inspect_heartbeat(
                        self.app_settings.paths.data_dir / "scanner_heartbeat.json",
                        max_age_seconds=max(
                            900, self.app_settings.scanner.poll_interval_minutes * 180
                        ),
                    )
                    if not health["healthy"]:
                        raise ValueError("scanner_unhealthy")
                    for signal in scanner_signals(
                        self.db_path, manifest, self.settings
                    ):
                        self.store.signal(signal)
                    self.store.set(
                        "source_health", {"healthy": True, "at": utc_now().isoformat()}
                    )
                except Exception as exc:
                    self.store.set(
                        "source_health",
                        {
                            "healthy": False,
                            "error": type(exc).__name__,
                            "at": utc_now().isoformat(),
                        },
                    )
                    raise ValueError("scanner_source_unavailable") from None
                for item in self.store.pending():
                    signal = TradeSignal.model_validate(item)
                    try:
                        reason = self._enter(signal, account)
                    except ValueError as exc:
                        reason = str(exc)
                    self.store.finish_signal(signal.source_id, reason)
                    if reason == "submitted":
                        self.reconcile()
                        account = self._account()
                self.store.set(
                    "heartbeat", {"at": utc_now().isoformat(), "healthy": True}
                )
            except Exception as exc:
                self.pause("service_error")
                self.store.set(
                    "heartbeat",
                    {
                        "at": utc_now().isoformat(),
                        "healthy": False,
                        "error": str(exc)
                        if isinstance(exc, (ValueError, ExchangeError))
                        else type(exc).__name__,
                    },
                )

    def run_loop(self):
        if not self.settings.enabled:
            return
        lock = ScannerInstanceLock(self.directory / "worker.lock")
        lock.acquire()
        self._owns_lock = True
        try:
            self.connect()
            if self.settings.environment != "simulation":
                from .stream import UserStream

                self.stream = UserStream(self._api_client, self.store)
                self.stream.start()
            while True:
                self.poll_signals()
                if self.stream:
                    self.stream.changed.wait(self.settings.poll_seconds)
                    self.stream.changed.clear()
                else:
                    time.sleep(self.settings.poll_seconds)
        except KeyboardInterrupt:
            pass
        finally:
            if self.stream:
                self.stream.close()
            self._owns_lock = False
            lock.release()
