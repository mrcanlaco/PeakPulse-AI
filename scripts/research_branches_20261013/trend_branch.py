"""Thuan Song: isolated hourly-accounting adapter, three predeclared comparisons.

Funding records are event-timed, but settlement MARK prices are unavailable.
Never edits historical research or live configuration. Reused history is exploratory.
"""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from dao_vang.research.data_loader import AssetMarketData
from dao_vang.research.walkforward_engine import prepare_multiasset_features

OUT = ROOT / "artifacts/research_branches_20261013/trend"
DATA = Path("D:/SharedMarketData/multiyear_2020_2026")
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
START = pd.Timestamp("2026-01-01", tz="UTC")
END = pd.Timestamp("2026-08-31 23:00", tz="UTC")
VARIANTS = {
    "baseline_corrected": {"delay_hours": 0, "positive_macro_slope": False},
    "delay_4h": {"delay_hours": 4, "positive_macro_slope": False},
    "macro_slope": {"delay_hours": 0, "positive_macro_slope": True},
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    text = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False,
                      default=lambda x: x.item() if isinstance(x, np.generic) else str(x))
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(text + "\n")


def load():
    hourly, funding, market = {}, {}, {}
    history = pd.Timestamp("2025-01-01", tz="UTC")
    for symbol in SYMBOLS:
        prices = pd.read_parquet(DATA / "klines_1h" / f"{symbol}_1h.parquet").loc[history:END].copy()
        rates = pd.read_parquet(DATA / "funding_8h" / f"{symbol}_funding.parquet")
        if not isinstance(rates.index, pd.DatetimeIndex):
            raise ValueError("Funding requires original event timestamps")
        rates.index = pd.to_datetime(rates.index, utc=True)
        rates = rates.loc[START:END + pd.Timedelta(hours=1)]
        if rates.index.duplicated().any():
            raise ValueError(f"Duplicate funding events: {symbol}")
        rate_column = "last_funding_rate" if "last_funding_rate" in rates else "funding_rate"
        funding[symbol] = rates[rate_column].astype(float)
        if not np.isfinite(funding[symbol]).all():
            raise ValueError(f"Invalid funding: {symbol}")
        expected = pd.date_range(START, END, freq="8h")
        # These four instruments are audited against the conventional 8h calendar.
        # This does not assert independent verification of historical interval rules.
        actual_hours = funding[symbol].index.floor("h")
        if set(expected) - set(actual_hours):
            raise ValueError(f"Missing expected 8h funding events: {symbol}")
        prices = prices.reindex(pd.date_range(history, END, freq="h"))
        if prices[["open", "high", "low", "close"]].isna().any().any():
            raise ValueError(f"Missing price in warmup/trading range: {symbol}")
        hourly[symbol] = prices
        market[symbol] = AssetMarketData(symbol, prices, pd.Series(0.0, index=prices.index))
    timeline, features = prepare_multiasset_features(market)
    for feature in features.values():
        feature["ema450"] = pd.Series(feature["close"]).shift(1).ewm(span=450).mean().to_numpy()
    return hourly, timeline, features, funding


def simulate(hourly, bar_index, features, funding, start, end, variant, cost_bps=10):
    """Long-only cash-collateralized sleeve. Funding before orders at exact ties.

    Within-hour records after an opening trade apply to the post-trade position.
    Their valuation remains the hour's OPEN proxy, not future close or true mark.
    """
    symbols = list(hourly)
    hours = pd.date_range(start, end, freq="h")
    prices = {s: hourly[s].reindex(hours) for s in symbols}
    for s, frame in prices.items():
        if not np.isfinite(frame[["open", "close"]].to_numpy()).all() or (frame[["open", "close"]] <= 0).any().any():
            raise ValueError(f"Missing or invalid execution/valuation prices: {s}")
    funds = {}
    for s in symbols:
        for stamp, rate in funding[s].items():
            hour = stamp.floor("h")
            if start <= hour <= end:
                funds.setdefault(hour, []).append((stamp, s, float(rate)))
    qty, entry, peak, stop = ({s: 0.0 for s in symbols} for _ in range(4))
    cash, fees, funding_paid = 10000.0, 0.0, 0.0
    pending, ledger, nav = [], [], []
    cost = cost_bps / 10000

    for hour in hours:
        opens = {s: float(prices[s].at[hour, "open"]) for s in symbols}
        events = sorted(funds.get(hour, []))

        def settle(records):
            nonlocal cash, funding_paid
            for stamp, symbol, rate in records:
                amount = qty[symbol] * opens[symbol] * rate
                cash -= amount
                funding_paid += amount
                if qty[symbol]:
                    ledger.append(dict(time=str(stamp), kind="funding", symbol=symbol,
                                       quantity=qty[symbol], price_proxy=opens[symbol], cashflow=-amount))

        settle([event for event in events if event[0] == hour])
        if hour in bar_index:
            j = int(bar_index.get_loc(hour)) - 1
            if j >= 6:
                btc = features["BTCUSDT"]
                macro_ok = btc["close"][j] > btc["ema450"][j]
                slope_ok = not variant["positive_macro_slope"] or btc["ema450"][j] > btc["ema450"][j - 6]
                pending_symbols = {order[2] for order in pending}
                for s in symbols:
                    if qty[s] and s not in pending_symbols:
                        f = features[s]
                        previous, atr = f["close"][j], f["atr14"][j]
                        peak[s] = max(peak[s], previous)
                        if (peak[s] - entry[s]) / max(atr, 1e-6) >= 1.5:
                            stop[s] = max(entry[s], peak[s] - 2.5 * atr)
                        else:
                            stop[s] = max(stop[s], peak[s] - 2.5 * atr)
                        if previous < stop[s] or previous < f["ema40"][j] or not macro_ok:
                            pending.append((hour + pd.Timedelta(hours=variant["delay_hours"]), "exit", s, None))
                occupied = sum(bool(qty[s]) for s in symbols) + sum(order[1] == "entry" for order in pending)
                # Same-open exits free slots at execution; avoid re-entering just-exited names.
                occupied -= sum(order[1] == "exit" and order[0] == hour for order in pending)
                candidates = []
                pending_symbols = {order[2] for order in pending}
                if macro_ok and slope_ok:
                    for s in symbols:
                        f = features[s]
                        if qty[s] or s in pending_symbols:
                            continue
                        if f["close"][j] >= f["donchian_30"][j] and f["close"][j] > f["ema40"][j] and f["mom14"][j] > 0:
                            candidates.append((float(f["mom14"][j]), s, float(f["ann_vol"][j]), float(f["atr14"][j])))
                candidates.sort(reverse=True)
                for _, s, vol, atr in candidates[:max(0, 2 - occupied)]:
                    if np.isfinite(vol) and vol > 0 and np.isfinite(atr) and atr > 0:
                        pending.append((hour + pd.Timedelta(hours=variant["delay_hours"]), "entry", s, (vol, atr)))
        due = sorted([order for order in pending if order[0] <= hour], key=lambda order: order[1] == "entry")
        pending = [order for order in pending if order[0] > hour]
        for _, kind, s, sizing in due:
            if kind == "exit" and qty[s]:
                value = qty[s] * opens[s]
                fee = value * cost
                cash += value - fee
                fees += fee
                ledger.append(dict(time=str(hour), kind=kind, symbol=s, quantity=qty[s], price=opens[s], fee=fee))
                qty[s] = 0.0
            elif kind == "entry" and not qty[s] and sum(bool(qty[x]) for x in symbols) < 2:
                equity = cash + sum(qty[x] * opens[x] for x in symbols)
                vol, atr = sizing
                allocation = equity / 2 * float(np.clip(.36 / vol, .20, 1.10))
                fee = allocation * cost
                if cash >= allocation + fee:
                    cash -= allocation + fee
                    fees += fee
                    qty[s] = allocation / opens[s]
                    entry[s] = peak[s] = opens[s]
                    stop[s] = opens[s] - 2 * atr
                    ledger.append(dict(time=str(hour), kind=kind, symbol=s, quantity=qty[s], price=opens[s], fee=fee))
        settle([event for event in events if event[0] > hour])
        nav.append(cash + sum(qty[s] * float(prices[s].at[hour, "close"]) for s in symbols))
    return pd.Series(nav, index=hours), dict(fees=fees, funding_paid=funding_paid, ledger=ledger,
                                            pending_orders_at_end=len(pending), positions_at_end=qty)


def summarize(nav, accounting):
    values = np.r_[10000.0, nav.to_numpy()]
    return dict(total_return_pct=(values[-1] / 10000 - 1) * 100,
                max_drawdown_pct=float(np.max(1 - values / np.maximum.accumulate(values))) * 100,
                fees=accounting["fees"], funding_paid=accounting["funding_paid"],
                entries=sum(row["kind"] == "entry" for row in accounting["ledger"]),
                exits=sum(row["kind"] == "exit" for row in accounting["ledger"]),
                final_equity=float(values[-1]))


def export_equity(nav, variant):
    daily = nav.resample("D").last()
    daily = daily / daily.iloc[0] * 10000
    return dict(branch="trend", name="Thuận Sóng", variant=variant, metric_basis="account_equity",
                is_baseline=variant == "baseline_corrected",
                eligible_for_combination=False, diagnostic_combination_eligible=True, funding_coverage_verified=False,
                valuation_convention="daily_close_utc", normalization="first_daily_close_10000",
                combination_scope="diagnostic segregated sleeves only; funding open-price proxy",
                timestamp_basis="UTC daily CLOSE; normalized first daily close to 10000",
                rows=[dict(date=str(date.date()), equity=float(value)) for date, value in daily.items()],
                limitations=["Missing verified settlement marks: funding uses event-hour open proxy.",
                             "Independent historical funding interval schedule not verified; expected 8h records checked.",
                             "Historical exploratory paper account, no cross-margin or liquidation simulation."])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    paths = [Path(__file__), ROOT / "tests/unit/research_branches_20261013/test_trend_branch.py",
             ROOT / "src/dao_vang/research/walkforward_engine.py", ROOT / "src/dao_vang/research/data_loader.py"]
    paths += [DATA / folder / f"{s}{suffix}.parquet" for s in SYMBOLS
              for folder, suffix in [("klines_1h", "_1h"), ("funding_8h", "_funding")]]
    hashes = {str(path.resolve()): sha(path) for path in paths}
    save(OUT / "experiment_lock.json", dict(branch="trend", name="Thuận Sóng", frozen_at=pd.Timestamp.now(tz="UTC").isoformat(),
         source_hashes=hashes, variants=VARIANTS, costs_bps=[10, 20], period=[str(START), str(END)],
         initial_state="flat 10000 each; identical indicators from 2025-01-01; original double-lag preserved",
         funding="Original timestamps; settlement before orders at exact ties; after orders for within-hour stamps. Hour-open proxy, no mark data.",
         new_oos=False, selection="No winner promoted. Baseline for fixed diagnostic combination; variants report incremental deltas only."))
    hourly, bars, features, rates = load()
    evidence = []
    for name, variant in VARIANTS.items():
        for cost in [10, 20]:
            nav, account = simulate(hourly, bars, features, rates, START, END, variant, cost)
            summary = summarize(nav, account)
            evidence.append(dict(variant=name, one_way_cost_bps=cost, **summary))
            suffix = name if cost == 10 else name + "_cost2x"
            save(OUT / f"equity_{suffix}.json", export_equity(nav, suffix))
            save(OUT / f"ledger_{suffix}.json", account)
            if name == "baseline_corrected" and cost == 10:
                save(OUT / "equity.json", export_equity(nav, name))
            print(json.dumps(evidence[-1]), flush=True)
    assert all(sha(path) == expected for path, expected in hashes.items())
    save(OUT / "report.json", dict(branch="trend", name="Thuận Sóng", status="bounded_exploratory_comparisons_complete",
         source_hashes=hashes, experiment_lock_sha256=sha(OUT / "experiment_lock.json"), evidence=evidence,
         funding_coverage_verified=False, new_oos=False, adapter_changes=[
         "Hourly open/close accounting; original signal lag and close-confirmed stop policy retained.",
         "Funding uses actual record timing and hour-open proxy; never the future 4h close.",
         "No forward-filled execution prices; required price gaps and missing conventional8h funding events abort.",
         "Avoid same-open exit/re-entry in same symbol; size orders from equity at actual fill time."],
         limitations=["No actual settlement mark data; funding amounts not fully verified.",
         "Four assets expected 8h schedule checked, not authoritative historical schedule; records may have millisecond settlement stamps.",
         "Same historical data reused. Three variants and cost stress do not establish new OOS alpha.",
         "No intrabar protective stop, no orderbook/partial fills. Added4h delay queues unmodified signals, not a realistic exchange queue.",
         "Positive EMA slope filter is one predeclared entry-only hypothesis; positions still exit under baseline policy.",
         "Daily exports are close samples; drawdown in summary uses hourly samples and may be larger.",
         "Daily curves start at Jan1 CLOSE=10000; first day's PnL is omitted from normalized diagnostic comparison, retained in account summary."],
         next_experiment=dict(name="verified_settlement_marks_and_prospective_paper", no_live_promotion=True,
         required=["Settlement mark prices and historical interval coverage", "Independent ledger reconciliation", "Future frozen paper comparison without reselection"])))


if __name__ == "__main__":
    main()
