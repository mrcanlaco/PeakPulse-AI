"""Offline account-policy diagnostic. Never imports the exchange execution client.

Rebuilds current features from raw data, without joining future labels. Missing
inputs remain disqualifying. This is NOT an attested exchange simulation: the
raw lake lacks historical books, mark-price paths, and maintenance brackets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dao_vang.config.settings import (  # noqa: E402
    ExecutionConfig,
    ScoringConfig,
    ThresholdPolicy,
)
from dao_vang.execution.contracts import ClosedBar, TradeSignal, atr14  # noqa: E402
from dao_vang.execution.funding import funding_window  # noqa: E402
from dao_vang.experiments.batch_evaluator import score_snapshot_batch  # noqa: E402
from dao_vang.experiments.forward_test import load_frozen_model  # noqa: E402
from dao_vang.features.builder import build_features  # noqa: E402
from dao_vang.scoring.btc_context import BtcContext  # noqa: E402
from dao_vang.scoring.distribution_scorer import (  # noqa: E402
    compute_distribution_score,
)
from dao_vang.scoring.evidence import evaluate_evidence  # noqa: E402


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def dump(path, obj):
    Path(path).write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str, allow_nan=False),
        encoding="utf-8",
    )


def prepare(args, out):
    """Use current feature builders, but reject their missing-input fallbacks."""
    db = duckdb.connect(str(out / "working.duckdb"))
    db.execute("SET timezone='UTC'")
    db.execute("SET memory_limit='4GB'")
    db.execute("SET threads=4")
    db.execute(f"SET temp_directory='{(out / 'tmp').as_posix()}'")
    warm = pd.Timestamp(args.start) - pd.Timedelta(days=31)
    end = pd.Timestamp(args.end)
    source = args.lake / "klines/5m"
    files = sorted(source.glob("*USDT.parquet"))
    paths = [str(p) for p in files]
    db.execute(
        """CREATE OR REPLACE TABLE prices AS SELECT * FROM read_parquet(?)
                  WHERE open_time>=? AND close_time<?""",
        [paths, warm, end],
    )
    supplemental_rows = 0
    if args.supplement_lake:
        supplements = [
            str(p)
            for p in sorted((args.supplement_lake / "klines/5m").glob("*USDT.parquet"))
        ]
        # The user-designated warehouse is authoritative on overlapping keys.
        # Supplement only absent keys; never rewrite the immutable source files.
        before = db.execute("SELECT count(*) FROM prices").fetchone()[0]
        db.execute(
            """INSERT INTO prices SELECT a.* FROM read_parquet(?) a
            WHERE a.open_time>=? AND a.close_time<? AND NOT EXISTS
              (SELECT 1 FROM prices p WHERE p.symbol=a.symbol AND p.open_time=a.open_time)""",
            [supplements, warm, end],
        )
        supplemental_rows = (
            db.execute("SELECT count(*) FROM prices").fetchone()[0] - before
        )
    if db.execute(
        "SELECT count(*)-count(DISTINCT (symbol,open_time)) FROM prices"
    ).fetchone()[0]:
        raise ValueError("duplicate_raw_price_keys")
    db.execute(
        f"ATTACH '{(args.lake / 'quant_master.duckdb').as_posix()}' AS lake (READ_ONLY)"
    )
    db.execute(
        """CREATE OR REPLACE TABLE metrics AS SELECT * FROM lake.metrics_5m
                  WHERE timestamp>=? AND timestamp<?""",
        [warm, end],
    )
    db.execute(
        """CREATE OR REPLACE TABLE funding AS SELECT * FROM lake.funding_history
                  WHERE funding_time>=? AND funding_time<?""",
        [warm, end],
    )
    db.execute("DETACH lake")
    if db.execute(
        "SELECT count(*)-count(DISTINCT (symbol,timestamp)) FROM metrics"
    ).fetchone()[0]:
        raise ValueError("duplicate_raw_metric_keys")
    if db.execute(
        "SELECT count(*)-count(DISTINCT (symbol,funding_time)) FROM funding"
    ).fetchone()[0]:
        raise ValueError("duplicate_raw_funding_keys")
    # Global context is calculated over the same universe in every chunk.
    db.execute("""CREATE OR REPLACE TABLE context AS WITH r AS (
        SELECT symbol,close_time,CASE WHEN close_time-lag(close_time,288) OVER w=INTERVAL '24 hours'
          THEN close/nullif(lag(close,288) OVER w,0)-1 END ret
        FROM prices WINDOW w AS (PARTITION BY symbol ORDER BY close_time))
        SELECT close_time,median(ret) AS alt_median FROM r WHERE symbol<>'BTCUSDT' GROUP BY 1""")
    coverage = {
        "requested_start": args.start,
        "requested_end_exclusive": args.end,
        "raw_price_files": len(files),
        "symbols": [],
        "source_hashes": {},
    }
    coverage["primary_warehouse"] = str(args.lake)
    coverage["supplemental_warehouse"] = (
        str(args.supplement_lake) if args.supplement_lake else None
    )
    coverage["supplemental_price_rows"] = supplemental_rows
    for table, col in [
        ("prices", "close_time"),
        ("metrics", "timestamp"),
        ("funding", "funding_time"),
    ]:
        row = db.execute(
            f"SELECT min({col}),max({col}),count(*) FROM {table}"
        ).fetchone()
        coverage[table] = {"min": row[0], "max": row[1], "rows": row[2]}
    info = load_frozen_model(args.model)
    coverage["model"] = {
        "id": info.model_id,
        "train_cutoff": info.train_cutoff,
        "freeze_time": info.freeze_time,
        "threshold": info.threshold,
    }
    for p in [
        info.model_path,
        info.metadata_path,
        info.calibrator_path,
        Path(__file__),
        ROOT / "configs/live.yaml",
    ]:
        if p:
            coverage["source_hashes"][str(p)] = sha(p)
    symbols = [
        r[0]
        for r in db.execute("SELECT DISTINCT symbol FROM prices ORDER BY 1").fetchall()
    ]
    records = []
    for offset in range(0, len(symbols), 12):
        chunk = symbols[offset : offset + 12]
        selected = sorted(set(chunk + ["BTCUSDT"]))
        db.execute(
            """CREATE OR REPLACE TABLE timeline AS WITH k AS (
            SELECT *,close_time AS feature_time,
              sum(quote_volume) OVER (PARTITION BY symbol ORDER BY close_time
                RANGE BETWEEN INTERVAL '1435 minutes' PRECEDING AND CURRENT ROW) volume_24h,
              count(*) OVER (PARTITION BY symbol ORDER BY close_time
                RANGE BETWEEN INTERVAL '1435 minutes' PRECEDING AND CURRENT ROW) bars_24h
            FROM prices WHERE symbol IN (SELECT unnest(?))), km AS (
            SELECT k.*,m.timestamp AS metric_time,m.open_interest AS open_interest_contracts,
              m.open_interest_value,m.top_trader_account_ratio AS top_long_short_ratio,
              m.top_trader_position_ratio AS top_long_short_position_ratio,
              m.global_account_ratio AS global_long_short_ratio,
              m.taker_buy_sell_ratio AS buy_sell_ratio
            FROM k LEFT JOIN metrics m ON k.symbol=m.symbol AND k.open_time=m.timestamp)
            SELECT km.*,f.funding_time,f.funding_rate,f.funding_rate AS funding_rate_last_known,
              f.mark_price,volume AS volume_base,quote_volume AS volume_quote,
              taker_buy_volume AS buy_volume,volume-taker_buy_volume AS sell_volume
            FROM km ASOF LEFT JOIN funding f ON km.symbol=f.symbol
              AND km.feature_time >= f.funding_time + INTERVAL '1 minute'""",
            [selected],
        )
        # All features are computed before selecting opportunities.
        build_features(db, "timeline", "features")
        frame = db.execute(
            """SELECT f.* REPLACE (f.btc_ret_24h-c.alt_median AS btc_dominance_slope_24h),
              t.close,t.volume_24h,t.bars_24h,t.metric_time,t.funding_time,
              t.global_long_short_ratio,t.top_long_short_ratio,t.top_long_short_position_ratio,
              t.buy_volume,t.sell_volume,
              count(t.metric_time) OVER (PARTITION BY f.symbol ORDER BY f.feature_time
                RANGE BETWEEN INTERVAL '235 minutes' PRECEDING AND CURRENT ROW) metric_bars_4h
            FROM features f JOIN timeline t USING(symbol,feature_time)
            LEFT JOIN context c ON c.close_time=f.feature_time
            WHERE f.symbol IN (SELECT unnest(?))
            QUALIFY feature_time>=? AND price_ret_24h>=0.10 AND volume_24h>=1000000
            ORDER BY feature_time,symbol""",
            [chunk, pd.Timestamp(args.start)],
        ).df()
        if not frame.empty:
            score = score_snapshot_batch(frame, info, ThresholdPolicy())
            raw_valid = (
                frame.metric_time.notna()
                & frame.funding_time.notna()
                & (frame.metric_bars_4h == 48)
                & (frame.bars_24h == 288)
                & (
                    (frame.feature_time - frame.funding_time)
                    <= pd.Timedelta(hours=8, minutes=5)
                )
                & frame[
                    [
                        "global_long_short_ratio",
                        "top_long_short_ratio",
                        "top_long_short_position_ratio",
                        "buy_volume",
                        "sell_volume",
                    ]
                ]
                .notna()
                .all(axis=1)
            )
            frame["usable"] = score.is_usable & raw_valid
            frame["probability"] = score.calibrated_probability
            frame["above_threshold"] = frame.usable & (
                frame.probability >= info.threshold
            )
            coverage["symbols"].append(
                {
                    "symbols": chunk,
                    "candidates": len(frame),
                    "usable": int(frame.usable.sum()),
                    "above_threshold": int(frame.above_threshold.sum()),
                }
            )
            records.append(frame)
        print(
            f"features {min(offset + 12, len(symbols))}/{len(symbols)}; candidates={len(frame)}",
            flush=True,
        )
        dump(out / "coverage.json", coverage)
    result = pd.concat(records, ignore_index=True) if records else pd.DataFrame()
    result.to_parquet(out / "candidates.parquet", index=False)
    db.close()
    return coverage


def run(args, out):
    import structlog
    from account_backtest_replay import simulate

    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(40))
    coverage = json.loads((out / "coverage.json").read_text(encoding="utf-8"))
    candidates = pd.read_parquet(out / "candidates.parquet").sort_values(
        ["feature_time", "symbol"]
    )
    # Top 150 gainers at each historical decision, deterministic tie breaking.
    candidates = candidates.sort_values(
        ["feature_time", "price_ret_24h", "symbol"], ascending=[True, False, True]
    )
    candidates = candidates.groupby("feature_time", sort=False).head(150)
    threshold = coverage["model"]["threshold"]
    db = duckdb.connect(str(out / "working.duckdb"), read_only=True)
    db.execute("SET timezone='UTC'")
    candles, hours, funding_evidence = {}, {}, {}

    def prices(symbol):
        if symbol not in candles:
            bars = db.execute(
                "SELECT open_time,close_time,open,high,low,close FROM prices WHERE symbol=? ORDER BY open_time",
                [symbol],
            ).df()
            if not np.isfinite(bars[["open", "high", "low", "close"]].to_numpy()).all():
                raise ValueError("nonfinite_prices:" + symbol)
            valid = (
                (bars.low > 0)
                & (bars.high >= bars[["open", "close"]].max(axis=1))
                & (bars.low <= bars[["open", "close"]].min(axis=1))
            )
            if not valid.all():
                raise ValueError("invalid_ohlc:" + symbol)
            mapping = {}
            for row in bars.itertuples(index=False):
                opened = int(row.open_time.timestamp() * 1000)
                closed = int(round(row.close_time.timestamp() * 1000)) + 1
                if closed - opened != 300000:
                    raise ValueError("irregular_bar:" + symbol)
                mapping.setdefault(opened, {})["entry_open"] = row.open
                mapping.setdefault(closed, {})["mark"] = row.close
            candles[symbol] = mapping
            h = (
                bars.set_index("open_time")
                .resample("1h")
                .agg(
                    high=("high", "max"),
                    low=("low", "min"),
                    close=("close", "last"),
                    count=("close", "count"),
                )
            )
            h.index += pd.Timedelta(hours=1)
            hours[symbol] = h[h["count"] == 12]
        return candles[symbol]

    signals, selected, lanes, exclusions = {}, [], {}, Counter()
    symbol_pattern = TradeSignal.model_json_schema()["properties"]["symbol"]["pattern"]
    neutral = BtcContext(
        0, 0, 0, "NEUTRAL", 50, "BTC score is not an independent evidence group"
    )
    for row in candidates.to_dict("records"):
        symbol = row["symbol"]
        if not re.fullmatch(symbol_pattern, symbol):
            exclusions["signal_contract_symbol"] += 1
            continue
        if not row["usable"]:
            exclusions["raw_or_feature_missing"] += 1
            continue
        state = lanes.setdefault(symbol, {"status": "ARMED", "flap": 0})
        prob = row["probability"]
        if state["status"] == "ACTIVE":
            if prob >= threshold:
                state["flap"] = 0
            else:
                state["flap"] += 1
                if state["flap"] >= 3:
                    state["status"] = "COOLING_DOWN"
            continue
        if state["status"] == "COOLING_DOWN":
            if prob < min(0.4, threshold * 0.95):
                state["status"] = "ARMED"
            continue
        if prob < threshold:
            exclusions["below_threshold"] += 1
            continue
        state["status"] = "ACTIVE"
        score = compute_distribution_score(symbol, dict(row), neutral, ScoringConfig())
        if not evaluate_evidence(score.components, min_groups=2).passed:
            exclusions["independent_evidence"] += 1
            continue
        prices(symbol)
        at = (row["feature_time"] + pd.Timedelta(milliseconds=1)).ceil("5min")
        h = hours[symbol].loc[:at].tail(15)
        try:
            atr = atr14(
                [
                    ClosedBar(
                        closed_at=t.to_pydatetime(),
                        high=r.high,
                        low=r.low,
                        close=r.close,
                    )
                    for t, r in h.iterrows()
                ],
                at.to_pydatetime(),
            )
        except ValueError:
            exclusions["atr_missing"] += 1
            continue
        event = hashlib.sha256(
            f"{args.model}:{symbol}:{at.isoformat()}".encode()
        ).hexdigest()[:24]
        signal = dict(
            symbol=symbol,
            event_id=event,
            atr=atr,
            probability=prob,
            at=int(at.timestamp() * 1000),
        )
        signals.setdefault(signal["at"], []).append(signal)
        selected.append(signal)
    for rows in signals.values():
        rows.sort(key=lambda r: (-r["probability"], r["symbol"]))
    dump(out / "signals.json", selected)
    current = ROOT / "artifacts/annual_execution_20260918/exchange_info_current.json"
    exchange = json.loads(current.read_text(encoding="utf-8"))
    rules = {}
    for s in exchange["symbols"]:
        if (
            s["contractType"] != "PERPETUAL"
            or s["marginAsset"] != "USDT"
            or s["status"] != "TRADING"
        ):
            continue
        f = {x["filterType"]: x for x in s["filters"]}
        lot, market = f["LOT_SIZE"], f["MARKET_LOT_SIZE"]
        rules[s["symbol"]] = dict(
            step_size=lot["stepSize"],
            market_step=market["stepSize"],
            min_qty=float(lot["minQty"]),
            max_qty=float(lot["maxQty"]),
            market_min_qty=float(market["minQty"]),
            market_max_qty=float(market["maxQty"]),
            tick_size=f["PRICE_FILTER"]["tickSize"],
            min_notional=float(f["MIN_NOTIONAL"]["notional"]),
        )
    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)

    def funding(symbol):
        rows, through, checksum = funding_window(
            out / "funding.sqlite3", symbol, start.to_pydatetime(), end.to_pydatetime()
        )
        funding_evidence[symbol] = {
            "through": through,
            "checksum": checksum,
            "settlements": len(rows),
        }
        print(f"funding {symbol}: {len(rows)} settlements", flush=True)
        if args.mark_prices:
            from dao_vang.data.collectors.binance_client import BinanceClient

            folder = out / "mark_prices"
            folder.mkdir(exist_ok=True)
            path = folder / f"{symbol}.json"
            first = int(start.timestamp() * 1000) - 300000
            last = int(end.timestamp() * 1000) - 1
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload["start"] != first or payload["end"] != last:
                    raise ValueError("mark_cache_window_mismatch")
                records = payload["rows"]
            else:
                client = BinanceClient(timeout_seconds=10, max_retries=0)
                cursor, records = first, []
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
                        raise ValueError("mark_response_invalid")
                    previous = cursor - 1
                    for item in page:
                        if (
                            not cursor <= int(item[0]) <= last
                            or int(item[0]) <= previous
                        ):
                            raise ValueError("mark_page_order")
                        previous = int(item[0])
                    records.extend(page)
                    if len(page) < 1500:
                        break
                    cursor = int(page[-1][0]) + 300000
                dump(
                    path,
                    dict(
                        start=first,
                        end=last,
                        source="binance_markPriceKlines",
                        rows=records,
                    ),
                )
            marks = {}
            for item in records:
                if (
                    int(item[6]) + 1 - int(item[0]) != 300000
                    or not np.isfinite(float(item[4]))
                    or float(item[4]) <= 0
                ):
                    raise ValueError("mark_value_or_grid_invalid")
                at = int(item[6]) + 1
                if at in marks:
                    raise ValueError("mark_duplicate")
                marks[at] = float(item[4])
            for at, point in prices(symbol).items():
                point.setdefault("execution_close", point.get("mark", float("nan")))
                point["mark"] = marks.get(at, float("nan"))
            funding_evidence[symbol]["mark_prices"] = {
                "sha256": sha(path),
                "bars": len(marks),
            }
            print(f"mark prices {symbol}: {len(marks)} bars", flush=True)
        return [
            (int(round(r.timestamp.timestamp() * 1000)), r.rate, r.mark_price)
            for r in rows
        ]

    times = [int(t.timestamp() * 1000) for t in pd.date_range(start, end, freq="5min")]
    results = []
    for cap in (1, 3, 5):
        result = simulate(
            times,
            signals,
            prices,
            rules,
            funding,
            ExecutionConfig(max_open_positions=cap),
        )
        if args.mark_prices:
            result["method"] = "historical_mark_prices_reconstructed_signals"
            result["liquidation_status"] = "unknown_historical_maintenance_brackets"
        dump(out / f"positions_{cap}.json", result)
        pd.DataFrame(result["curve"]).to_csv(out / f"equity_{cap}.csv", index=False)
        pd.DataFrame(result["journal"]).to_csv(out / f"trades_{cap}.csv", index=False)
        compact = {k: v for k, v in result.items() if k not in ("curve", "journal")}
        results.append(compact)
        print(json.dumps(compact, default=str), flush=True)
    valid = candidates[candidates.usable]
    coverage["candidate_rows"] = len(candidates)
    coverage["usable_candidate_rows"] = len(valid)
    coverage["usable_start"] = str(valid.feature_time.min())
    coverage["usable_end"] = str(valid.feature_time.max())
    coverage["signal_events"] = len(selected)
    coverage["selection_exclusions"] = dict(exclusions)
    coverage["funding_evidence"] = funding_evidence
    coverage["exchange_rules_sha256"] = sha(current)
    coverage["runner_final_sha256"] = sha(__file__)
    coverage["replay_sha256"] = sha(
        Path(__file__).with_name("account_backtest_replay.py")
    )
    coverage["candidate_sha256"] = sha(out / "candidates.parquet")
    coverage["signals_sha256"] = sha(out / "signals.json")
    coverage["formula_hashes"] = {
        str(p.relative_to(ROOT)): sha(p)
        for subdir in ["features", "scoring"]
        for p in sorted((ROOT / "src/dao_vang" / subdir).rglob("*.py"))
    }
    coverage["mark_prices_used"] = args.mark_prices
    dump(out / "coverage.json", coverage)
    limitations = [
        "Historical current-model signals are reconstructed, not immutable production predictions.",
        "Model training overlaps this window; no out-of-sample or forward-profit claim.",
        "Gainer reconstruction omits production pump-filter fallback and retained-lane discovery; candidate universe and episode history are approximate.",
        "Missing derivative inputs reject opportunities. Unobserved opportunities cannot be treated as zero signals; complete-period strategy return is unavailable.",
        "Raw lake exchange identity and point-in-time delisted universe are not attested.",
        "Candle closes proxy mark prices and limit execution; books, spread, queue and partial fills are unavailable.",
        "Current exchange filters substitute for unavailable historical filters.",
        "Maintenance margin uses a 1% stress proxy; Binance Cross liquidation is NOT verified.",
        "Fee assumption 0.05% each side, entry slippage 20 bps; actual account fee tier not verified.",
    ]
    if args.mark_prices:
        limitations[5] = (
            "Equity uses Binance historical 5m Mark Price closes. TP uses trade closes as a fill convention; books, spread, queue and partial fills remain unavailable in this replay."
        )
    summary = dict(
        status="INCOMPLETE_NOT_ELIGIBLE",
        financially_verified=False,
        promotion_eligible=False,
        window=[args.start, args.end],
        config=dict(
            capital=500,
            margin_per_position=5,
            leverage=5,
            side="SHORT",
            margin_mode="CROSS",
            stop_loss=False,
            dca=False,
            tp="2 x ATR14 closed 1h; net target 0.50 to 5 USDT",
            pause_drawdown=0.20,
        ),
        limitations=limitations,
        coverage=coverage,
        diagnostic_results=results,
    )
    dump(out / "report.json", summary)
    db.close()
    return summary


def repair_btc(args, out):
    """Restore an observed BTC gap from an existing checksum-verified archive.

    This changes only this run's working copy, never the source lake. Recompute
    the dependent BTC features and all scores; never fill feature values with
    averages or carry future values backward.
    """
    manifest_path = ROOT / "artifacts/annual_profit_20260918/prices/price_manifest.json"
    archive_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cache = ROOT / "artifacts/annual_profit_20260918/prices/klines/5m/BTCUSDT.parquet"
    checksum = sha(cache)
    if checksum != archive_manifest["symbols"]["BTCUSDT"]["output_sha256"]:
        raise ValueError("btc_archive_checksum_mismatch")
    db = duckdb.connect(str(out / "working.duckdb"))
    db.execute("SET timezone='UTC'")
    warm = pd.Timestamp(args.start) - pd.Timedelta(days=31)
    before = db.execute(
        "SELECT count(*) FROM prices WHERE symbol='BTCUSDT'"
    ).fetchone()[0]
    db.execute(
        """INSERT INTO prices SELECT a.* FROM read_parquet(?) a
        WHERE a.open_time>=? AND a.close_time<? AND NOT EXISTS
        (SELECT 1 FROM prices p WHERE p.symbol=a.symbol AND p.open_time=a.open_time)""",
        [str(cache), warm, pd.Timestamp(args.end)],
    )
    after = db.execute("SELECT count(*) FROM prices WHERE symbol='BTCUSDT'").fetchone()[
        0
    ]
    btc = db.execute("""WITH r AS (SELECT close_time AS feature_time,
        CASE WHEN close_time-lag(close_time,1) OVER w=INTERVAL '5 minutes'
          THEN close/lag(close,1) OVER w-1 END ret5,
        CASE WHEN close_time-lag(close_time,48) OVER w=INTERVAL '4 hours'
          THEN close/lag(close,48) OVER w-1 END btc_ret_4h,
        CASE WHEN close_time-lag(close_time,288) OVER w=INTERVAL '24 hours'
          THEN close/lag(close,288) OVER w-1 END btc_ret_24h
        FROM prices WHERE symbol='BTCUSDT' WINDOW w AS (ORDER BY close_time))
        SELECT r.* EXCLUDE(ret5), stddev_samp(ret5) OVER
          (ORDER BY feature_time RANGE BETWEEN INTERVAL '1435 minutes' PRECEDING AND CURRENT ROW) btc_volatility_24h,
          c.alt_median FROM r LEFT JOIN context c ON c.close_time=r.feature_time""").df()
    db.close()
    frame = pd.read_parquet(out / "candidates.parquet")
    frame = frame.drop(
        columns=[
            "btc_ret_4h",
            "btc_ret_24h",
            "btc_volatility_24h",
            "btc_dominance_slope_24h",
        ]
    )
    frame = frame.merge(btc, on="feature_time", how="left", validate="many_to_one")
    frame["btc_dominance_slope_24h"] = np.where(
        frame.symbol == "BTCUSDT",
        frame.btc_ret_24h,
        frame.btc_ret_24h - frame.alt_median,
    )
    frame = frame.drop(columns=["alt_median"])
    info = load_frozen_model(args.model)
    score = score_snapshot_batch(frame, info, ThresholdPolicy())
    raw_valid = (
        frame.metric_time.notna()
        & frame.funding_time.notna()
        & (frame.metric_bars_4h == 48)
        & (frame.bars_24h == 288)
        & (
            (frame.feature_time - frame.funding_time)
            <= pd.Timedelta(hours=8, minutes=5)
        )
        & frame[
            [
                "global_long_short_ratio",
                "top_long_short_ratio",
                "top_long_short_position_ratio",
                "buy_volume",
                "sell_volume",
            ]
        ]
        .notna()
        .all(axis=1)
    )
    frame["usable"] = score.is_usable & raw_valid
    frame["probability"] = score.calibrated_probability
    frame["above_threshold"] = frame.usable & (frame.probability >= info.threshold)
    frame.to_parquet(out / "candidates.parquet", index=False)
    coverage = json.loads((out / "coverage.json").read_text(encoding="utf-8"))
    coverage["btc_repair"] = {
        "inserted_bars": after - before,
        "archive": str(cache),
        "sha256": checksum,
        "manifest_sha256": sha(manifest_path),
        "candidate_rows": len(frame),
        "usable_after_repair": int(frame.usable.sum()),
        "above_threshold": int(frame.above_threshold.sum()),
    }
    dump(out / "coverage.json", coverage)
    print("BTC repair", coverage["btc_repair"], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2026-06-24T00:00:00Z")
    parser.add_argument("--end", default="2026-09-24T00:00:00Z")
    parser.add_argument("--lake", type=Path, default=Path("D:/Quant-trading/data_lake"))
    parser.add_argument("--supplement-lake", type=Path)
    parser.add_argument("--model", default="frozen_20260906_105716_bc3c369b")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "artifacts/account_backtest_20260924_3m"
    )
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--repair-btc", action="store_true")
    parser.add_argument("--mark-prices", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.prepare:
        prepare(args, args.output)
    if args.repair_btc:
        repair_btc(args, args.output)
    if args.run:
        run(args, args.output)


if __name__ == "__main__":
    main()
