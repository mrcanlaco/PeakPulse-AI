"""Predeclared offline risk-policy comparison; no private/execution API access."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import duckdb
import pandas as pd
import structlog

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from account_backtest_replay import simulate  # noqa: E402

from dao_vang.config.settings import ExecutionConfig  # noqa: E402
from dao_vang.data.collectors.binance_client import BinanceClient  # noqa: E402
from dao_vang.execution.funding import funding_window  # noqa: E402

POLICIES = [
    ("baseline", "Gốc: không cắt lỗ", {}),
    ("loss_2_5", "Cắt lỗ 2,5 USDT/lệnh", {"loss_usdt": 2.5}),
    ("loss_5", "Cắt lỗ 5 USDT/lệnh", {"loss_usdt": 5}),
    ("loss_10", "Cắt lỗ 10 USDT/lệnh", {"loss_usdt": 10}),
    ("atr_2", "Cắt lỗ khi giá tăng 2 ATR", {"stop_atr": 2}),
    ("hold_24", "Đóng sau tối đa 24 giờ", {"max_hold_hours": 24}),
    ("hold_72", "Đóng sau tối đa 72 giờ", {"max_hold_hours": 72}),
    ("dd_10", "Đóng danh mục khi giảm 10%", {"flatten_drawdown": 0.10}),
    ("dd_20", "Đóng danh mục khi giảm 20%", {"flatten_drawdown": 0.20}),
    ("half_size", "Nửa vốn/lệnh, không cắt lỗ", {"position_notional": 12.5}),
    (
        "loss_5_hold_72",
        "Lỗ 5 USDT hoặc giữ 72 giờ",
        {"loss_usdt": 5, "max_hold_hours": 72},
    ),
    (
        "loss_2_5_hold_24",
        "Lỗ 2,5 USDT hoặc giữ 24 giờ",
        {"loss_usdt": 2.5, "max_hold_hours": 24},
    ),
]


def write(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, default=str),
        encoding="utf-8",
    )


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def exchange_rules(source):
    result = {}
    for symbol in json.loads(source.read_text(encoding="utf-8"))["symbols"]:
        if (
            symbol["contractType"] != "PERPETUAL"
            or symbol["marginAsset"] != "USDT"
            or symbol["status"] != "TRADING"
        ):
            continue
        f = {v["filterType"]: v for v in symbol["filters"]}
        lot, market = f["LOT_SIZE"], f["MARKET_LOT_SIZE"]
        result[symbol["symbol"]] = dict(
            step_size=lot["stepSize"],
            market_step=market["stepSize"],
            min_qty=float(lot["minQty"]),
            max_qty=float(lot["maxQty"]),
            market_min_qty=float(market["minQty"]),
            market_max_qty=float(market["maxQty"]),
            tick_size=f["PRICE_FILTER"]["tickSize"],
            min_notional=float(f["MIN_NOTIONAL"]["notional"]),
        )
    return result


def load_inputs(source, output, signals, start, end, rules):
    funding_path = output / "funding.sqlite3"
    if not funding_path.exists():
        with sqlite3.connect(
            f"file:{(source / 'funding.sqlite3').as_posix()}?mode=ro", uri=True
        ) as old:
            with sqlite3.connect(funding_path) as new:
                old.backup(new)
    (output / "mark_prices").mkdir(exist_ok=True)
    first, last = (
        int(start.timestamp() * 1000) - 300000,
        int(end.timestamp() * 1000) - 1,
    )
    symbols = sorted({s["symbol"] for s in signals if s["symbol"] in rules})
    evidence, funding, marks, failures = {}, {}, {}, {}

    def mark_data(symbol):
        cached = source / "mark_prices" / f"{symbol}.json"
        path = cached if cached.exists() else output / "mark_prices" / f"{symbol}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload["start"] != first or payload["end"] != last:
                raise ValueError("mark_window_mismatch")
            rows = payload["rows"]
        else:
            client = BinanceClient(timeout_seconds=30, max_retries=2)
            cursor, rows = first, []
            while cursor <= last:
                page = client.get(
                    "/fapi/v1/markPriceKlines",
                    dict(
                        symbol=symbol,
                        interval="5m",
                        startTime=cursor,
                        endTime=last,
                        limit=1500,
                    ),
                )
                if not isinstance(page, list):
                    raise ValueError("invalid_mark_response")
                previous = cursor - 1
                for row in page:
                    if not cursor <= int(row[0]) <= last or int(row[0]) <= previous:
                        raise ValueError("invalid_mark_order")
                    previous = int(row[0])
                rows.extend(page)
                if len(page) < 1500:
                    break
                cursor = int(page[-1][0]) + 300000
            write(
                path,
                dict(
                    start=first, end=last, source="binance_markPriceKlines", rows=rows
                ),
            )
        result = {}
        for row in rows:
            at, value = int(row[6]) + 1, float(row[4])
            if (
                at - int(row[0]) != 300000
                or not math.isfinite(value)
                or value <= 0
                or at in result
            ):
                raise ValueError("invalid_mark_bar")
            result[at] = value
        return symbol, result, dict(path=str(path), sha256=sha(path), bars=len(result))

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(mark_data, s): s for s in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                _, data, proof = future.result()
                marks[symbol], evidence[symbol] = data, {"marks": proof}
                print(f"Mark {symbol}: {len(data)} bars", flush=True)
            except Exception as exc:
                failures[symbol] = f"marks:{type(exc).__name__}:{str(exc)[:160]}"
                print(f"FAILED Mark {symbol}: {type(exc).__name__}", flush=True)
    # Sequential SQLite writes; all calls are public market-data endpoints.
    for symbol in symbols:
        try:
            rows, through, checksum = funding_window(
                funding_path, symbol, start.to_pydatetime(), end.to_pydatetime()
            )
            funding[symbol] = [
                (int(round(r.timestamp.timestamp() * 1000)), r.rate, r.mark_price)
                for r in rows
            ]
            evidence.setdefault(symbol, {})["funding"] = dict(
                through=through, sha256=checksum, rows=len(rows)
            )
        except Exception as exc:
            failures[symbol] = f"funding:{type(exc).__name__}"
        print(f"Funding {symbol}: {len(funding.get(symbol, []))} rows", flush=True)
    db = duckdb.connect(str(source / "working.duckdb"), read_only=True)
    quotes = {}
    (output / "trade_prices").mkdir(exist_ok=True)
    for symbol in symbols:
        frame = db.execute(
            "SELECT epoch_ms(open_time),epoch_ms(close_time),open,close FROM prices WHERE symbol=? ORDER BY open_time",
            [symbol],
        ).fetchall()
        points = {}
        for opened, closed, opened_price, closed_price in frame:
            if closed + 1 - opened != 300000:
                raise ValueError("trade_bar_grid")
            points.setdefault(opened, {})["entry_open"] = opened_price
            points.setdefault(closed + 1, {})["execution_close"] = closed_price
        quotes[symbol] = points
    db.close()

    def repair_trade_prices(symbol):
        points = quotes[symbol]
        path = output / "trade_prices" / f"{symbol}.json"
        records = []

        def apply(rows):
            for row in rows:
                opened, closed = int(row[0]), int(row[6]) + 1
                op, high, low, close = map(float, row[1:5])
                if (
                    closed - opened != 300000
                    or not all(
                        math.isfinite(x) and x > 0 for x in (op, high, low, close)
                    )
                    or low > min(op, close)
                    or high < max(op, close)
                ):
                    raise ValueError("invalid_trade_ohlc")
                # Never overwrite existing warehouse values.
                points.setdefault(opened, {}).setdefault("entry_open", op)
                points.setdefault(closed, {}).setdefault("execution_close", close)

        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload["start"] != first or payload["end"] != last:
                raise ValueError("trade_window_mismatch")
            records = payload["rows"]
            apply(records)
        # For each observed Mark bar, require the corresponding completed
        # trade bar. Exclude pre-listing periods with no observed Mark data.
        missing = sorted(
            at - 300000
            for at in marks.get(symbol, {})
            if at <= last + 1
            and (
                "execution_close" not in points.get(at, {})
                or "entry_open" not in points.get(at - 300000, {})
            )
        )
        before = len(missing)
        if missing:
            spans = []
            a = b = missing[0]
            for value in missing[1:]:
                if value == b + 300000:
                    b = value
                else:
                    spans.append((a, b))
                    a = b = value
            spans.append((a, b))
            client = BinanceClient(timeout_seconds=30, max_retries=2)
            for a, b in spans:
                cursor = a
                while cursor <= b:
                    page = client.get(
                        "/fapi/v1/klines",
                        dict(
                            symbol=symbol,
                            interval="5m",
                            startTime=cursor,
                            endTime=b + 299999,
                            limit=1500,
                        ),
                    )
                    if not isinstance(page, list):
                        raise ValueError("invalid_trade_response")
                    previous = cursor - 1
                    for row in page:
                        if not cursor <= int(row[0]) <= b or int(row[0]) <= previous:
                            raise ValueError("invalid_trade_order")
                        previous = int(row[0])
                    records.extend(page)
                    apply(page)
                    if len(page) < 1500:
                        break
                    cursor = int(page[-1][0]) + 300000
            write(
                path,
                dict(
                    start=first,
                    end=last,
                    source="binance_klines_missing_warehouse_bars_only",
                    rows=records,
                ),
            )
        for at, mark in marks.get(symbol, {}).items():
            points.setdefault(at, {})["mark"] = mark
        for point in points.values():
            point.setdefault("mark", math.nan)
            point.setdefault("execution_close", math.nan)
        remaining = sum(
            not math.isfinite(points[at]["execution_close"])
            for at in marks.get(symbol, {})
            if at <= last + 1
        )
        proof = dict(
            missing_before=before,
            missing_after=remaining,
            supplemental_rows=len(records),
        )
        if path.exists():
            proof.update(path=str(path), sha256=sha(path))
        return symbol, proof

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(repair_trade_prices, s): s for s in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                _, proof = future.result()
                evidence.setdefault(symbol, {})["trade_prices"] = proof
                print(
                    f"Trade {symbol}: supplemented={proof['supplemental_rows']}, gaps={proof['missing_after']}",
                    flush=True,
                )
            except Exception as exc:
                failures[symbol] = f"trade_prices:{type(exc).__name__}:{str(exc)[:160]}"
                print(f"FAILED Trade {symbol}: {type(exc).__name__}", flush=True)
    write(output / "data_evidence.json", dict(symbols=evidence, failures=failures))
    return quotes, funding, failures


def summarize(result, policy_id, label, policy, cap, cost, window):
    closed = [x for x in result["journal"] if "net" in x]
    wins = [x["net"] for x in closed if x["net"] > 0]
    losses = [x["net"] for x in closed if x["net"] < 0]
    opened = result["open_positions"]
    return dict(
        id=f"{window}_{cost}_{cap}_{policy_id}",
        policy_id=policy_id,
        label=label,
        policy=policy,
        cap=cap,
        cost=cost,
        window=window,
        ending_equity=result["ending_equity"],
        pnl=result["pnl"],
        max_drawdown=result["sampled_max_drawdown"],
        entries=result["entries"],
        exits=len(closed),
        tp=result["tp_exits"],
        open_count=len(opened),
        win_rate=len(wins) / len(closed) if closed else None,
        avg_closed_net=sum(x["net"] for x in closed) / len(closed) if closed else None,
        worst_closed_net=min((x["net"] for x in closed), default=None),
        profit_factor=sum(wins) / -sum(losses) if losses else None,
        fees=result["fees"],
        funding=result["funding"],
        open_pnl=sum(x["unrealized"] or 0 for x in opened),
        max_hold_days=max(
            [x["held_hours"] / 24 for x in closed]
            + [x["held_days"] for x in opened]
            + [0]
        ),
        exit_reasons=dict(Counter(x["kind"] for x in closed)),
        paused=result["entry_paused"],
        errors=result["errors"],
        rejections=result["rejections"],
        stop_event=result["stop_event"],
        financially_verified=False,
        promotion_eligible=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "artifacts/account_backtest_20260924_3m/warehouse",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/account_risk_comparison_20260924",
    )
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    out, source = args.output, args.source
    out.mkdir(parents=True, exist_ok=True)
    (out / "runs").mkdir(exist_ok=True)
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(40))
    signals = json.loads((source / "signals.json").read_text(encoding="utf-8"))
    start, end = (
        pd.Timestamp("2026-06-24T00:00:00Z"),
        pd.Timestamp("2026-09-24T00:00:00Z"),
    )
    rules_path = ROOT / "artifacts/annual_execution_20260918/exchange_info_current.json"
    protocol = dict(
        created_at=pd.Timestamp.now(tz="UTC").isoformat(),
        policies=POLICIES,
        caps=[1, 3, 5],
        costs={
            "base": {"fee": 0.0005, "slip_bps": 20},
            "stress": {"fee": 0.001, "slip_bps": 50},
        },
        window=[str(start), str(end)],
        signal_cutoff="2026-09-08T00:00:00Z",
        signals_sha256=sha(source / "signals.json"),
        rules_sha256=sha(rules_path),
        code_sha256=sha(Path(__file__)),
        engine_sha256=sha(Path(__file__).with_name("account_backtest_replay.py")),
        decision="Compare every predeclared policy; no automated promotion or parameter selection.",
        stop_fills="At next trade open plus adverse slippage after 5m Mark-close trigger; no intrabar guarantee.",
        limitations=json.loads((source / "report.json").read_text(encoding="utf-8"))[
            "limitations"
        ],
    )
    write(out / "protocol.json", protocol)
    rules = exchange_rules(rules_path)
    quotes, funding, failures = load_inputs(source, out, signals, start, end, rules)
    if args.prepare_only:
        return

    # A required held-symbol funding/price failure cannot be replaced by zero.
    def funding_for(symbol):
        if symbol in failures or symbol not in funding:
            raise ValueError(f"data_unavailable:{symbol}")
        return funding[symbol]

    windows = [
        ("full", start, end),
        ("w1", start, pd.Timestamp("2026-07-24T00:00:00Z")),
        (
            "w2",
            pd.Timestamp("2026-07-24T00:00:00Z"),
            pd.Timestamp("2026-08-24T00:00:00Z"),
        ),
        (
            "w3",
            pd.Timestamp("2026-08-24T00:00:00Z"),
            pd.Timestamp("2026-09-08T00:00:00Z"),
        ),
    ]
    results, regression = [], []
    for window, begin, finish in windows:
        grouped = defaultdict(list)
        for signal in signals:
            if begin.timestamp() * 1000 <= signal["at"] < finish.timestamp() * 1000:
                grouped[signal["at"]].append(signal)
        for rows in grouped.values():
            rows.sort(key=lambda x: (-x["probability"], x["symbol"]))
        times = [
            int(t.timestamp() * 1000) for t in pd.date_range(begin, finish, freq="5min")
        ]
        for cost, cost_settings in protocol["costs"].items():
            if window != "full" and cost != "base":
                continue
            for cap in protocol["caps"]:
                config = ExecutionConfig(
                    max_open_positions=cap,
                    fee_rate=cost_settings["fee"],
                    max_slippage_bps=cost_settings["slip_bps"],
                )
                for policy_id, label, policy in POLICIES:
                    result = simulate(
                        times,
                        grouped,
                        lambda s: quotes.get(s, {}),
                        rules,
                        funding_for,
                        config,
                        research_policy=policy,
                    )
                    result["method"] = (
                        "historical_mark_prices_reconstructed_signals_risk_comparison"
                    )
                    result["liquidation_status"] = (
                        "unknown_historical_maintenance_brackets_and_intrabar_path"
                    )
                    result["research_policy"] = policy
                    row = summarize(result, policy_id, label, policy, cap, cost, window)
                    results.append(row)
                    if window == "full":
                        write(out / "runs" / f"{row['id']}.json", result)
                        pd.DataFrame(result["journal"]).to_csv(
                            out / "runs" / f"{row['id']}_trades.csv", index=False
                        )
                    if window == "full" and cost == "base" and policy_id == "baseline":
                        old = json.loads(
                            (source / f"positions_{cap}.json").read_text(
                                encoding="utf-8"
                            )
                        )
                        checks = {
                            k: result[k] == old[k]
                            for k in [
                                "entries",
                                "tp_exits",
                                "ending_equity",
                                "stop_event",
                                "closed_trade_net",
                            ]
                        }
                        regression.append(dict(cap=cap, checks=checks))
                    print(
                        f"{row['id']}: equity={row['ending_equity']} DD={row['max_drawdown']:.3f} entries={row['entries']} errors={row['errors']}",
                        flush=True,
                    )
        write(
            out / "summary.json",
            dict(
                status="EXPLORATORY_NOT_LIVE_ELIGIBLE",
                protocol=protocol,
                results=results,
                baseline_regression=regression,
                data_failures=failures,
            ),
        )
        pd.DataFrame(results).to_csv(out / "comparison.csv", index=False)
    if not all(all(r["checks"].values()) for r in regression):
        raise AssertionError(f"Baseline differs: {regression}")


if __name__ == "__main__":
    main()
