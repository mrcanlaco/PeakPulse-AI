"""Bounded pre-2026 research with separately gated chronological evaluation.

No 2026 observations are loaded. Earlier versions remain read-only. Historical
OOS here describes this procedure, not a claim that 2025 was never seen before.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import heapq
import json
from pathlib import Path
import pickle
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(Path(__file__).resolve().parent)]
from dao_vang.fibo_short.backtest import resample_1h_to_htf
from universe_reaudit_v402_worker import collect_symbol_milestones_v402
from verify_red_team_audit_2026 import calc_htf_features_no_bfill

ART = ROOT / "artifacts/fibo_trend_short/research_v4_0_7"
LAKE = Path("E:/Quant-trading/data_lake/klines/5m") if Path("E:/Quant-trading/data_lake/klines/5m").exists() else Path("C:/Quant-trading/data_lake/klines/5m")
LIMIT = pd.Timestamp("2026-01-01T00:00:00Z")
WINDOWS = {
    "development": ("2024-01-01", "2025-01-01"),
    "validation": ("2025-01-01", "2025-07-01"),
    "final_oos": ("2025-07-01", "2026-01-01"),
}
EXCLUDE = {"USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "DAIUSDT", "BUSDUSDT", "EURUSDT",
           "BTCUSDT", "ETHUSDT", "BNBUSDT", "PAXGUSDT", "XAUTUSDT", "BTCDOMUSDT", "DEFIUSDT"}
VARIANTS = [
    {"id": "reference_m6_fixed", "gate": "expanded", "sizing": "fixed", "exit": "ladder"},
    {"id": "m6_risk", "gate": "expanded", "sizing": "risk", "exit": "ladder"},
    {"id": "elite_risk", "gate": "elite", "sizing": "risk", "exit": "ladder"},
    {"id": "sniper_risk", "gate": "sniper", "sizing": "risk", "exit": "ladder"},
    {"id": "elite_sniper_risk", "gate": "elite_sniper", "sizing": "risk", "exit": "ladder"},
    {"id": "btc_weak_risk", "gate": "btc_weak", "sizing": "risk", "exit": "ladder"},
    {"id": "score68_risk", "gate": "score68", "sizing": "risk", "exit": "ladder"},
    {"id": "rr1_risk", "gate": "rr1", "sizing": "risk", "exit": "ladder"},
    {"id": "tp1_risk", "gate": "expanded", "sizing": "risk", "exit": "tp1"},
    {"id": "elite_tp1_risk", "gate": "elite", "sizing": "risk", "exit": "tp1"},
    {"id": "sniper_tp1_risk", "gate": "sniper", "sizing": "risk", "exit": "tp1"},
    {"id": "btc_weak_tp1_risk", "gate": "btc_weak", "sizing": "risk", "exit": "tp1"},
]


def utc(value):
    t = pd.Timestamp(value)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def epoch_seconds(index):
    # Parquet timestamps may retain ms/us resolution; asi8 is not always ns.
    return pd.DatetimeIndex(index).as_unit("ns").asi8 // 10**9


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def init():
    ART.mkdir(parents=True, exist_ok=True)
    p = ART / "PROTOCOL.json"
    if p.exists():
        raise FileExistsError("A registered protocol must not be silently overwritten")
    protocol = {
        "version": "4.0.7-research-01", "registered_at_utc": datetime.now(timezone.utc).isoformat(),
        "objective": "Improve the short strategy using data through 2025; retain chronological OOS and a mini-alpha evidence registry",
        "hard_data_end_exclusive": LIMIT.isoformat(), "windows": WINDOWS,
        "oos_disclosure": "2025 has been inspected by historical project research. These are retrospective chronological OOS windows for the new procedure, not globally virgin data. No fresh-OOS or live approval is implied.",
        "data_policy": "Parquet predicate pushdown before materialization. Each stage loads only its own end plus trailing context; no 2026 price/funding observations. Complete 12x5m H1 and complete HTF bars only.",
        "universe": "Monthly PIT top 50 by trailing 63-day median daily quote volume; >=50 active days, H4 upper-wick p90<=3.2%; predefined exclusions. Available-file survivorship limitation remains.",
        "variants": VARIANTS, "max_candidates_this_round": len(VARIANTS),
        "execution": "H1 signal close, enter at the next 5-minute bar open five minutes later. Reject entry if already beyond initial stop or TP1. 5-minute stop-first simulation, ratchet recheck, adverse gap fills; 72/120 wall-clock hour horizon. Force-close at split end; 5-day entry embargo at each split end.",
        "costs_bps_round_trip": [40, 60],
        "funding": "Primary selection uses adverse short funding 1 bp per standard 8h settlement, alongside ex-funding diagnostics. These are scenarios, not claimed historical funding.",
        "risk": {"equity_risk_per_trade": .005, "max_entry_notional": .20, "max_total_notional": 1.0, "max_positions": 5, "max_total_stop_risk": .02,
                 "sizing": "min(20% equity, 0.5% equity/(stop distance + 60bps cost budget)); fixed reference retains historical 20%/12% aggregate stop-risk cap"},
        "selection": "Use development only. Candidate (excluding fixed reference) must have >=40 trades, positive return at 40bps+funding stress, nonnegative at 60bps+stress, drawdown<=15%, and positive reset-H1 and reset-H2 development returns at 40bps+stress. Rank qualified candidates by return minus max drawdown at 60bps+stress; ties by ID. Freeze at most two before validation. Cash if none qualify.",
        "validation_gate": "Evaluate only frozen shortlist and fixed reference. Require >=20 trades, positive 40bps+stress and nonnegative 60bps+stress, drawdown<=15%. Rank passing shortlist by 60bps return minus drawdown; freeze ONE before final OOS. Cash if none qualify. Never open final OOS for a failed shortlist.",
        "final_gate": "Frozen winner only versus frozen reference; >=20 trades, positive 40bps+stress, nonnegative 60bps+stress, drawdown<=15%, positive lower 95% four-week block-bootstrap mean weekly return at 40bps+stress. Also disclose concentration and execution/funding limitations. Failure cannot be repaired on final OOS.",
        "inference": "5000 circular block-bootstrap samples of four consecutive weekly portfolio returns, including zero-activity weeks. Development intervals descriptive after multiple selection; no false p-value or virgin-data claim.",
        "iteration_policy": "Retain every trial, including rejection. Further hypotheses can iterate on development; validation/final exposure is irrevocably recorded and cannot be renamed fresh. Final-OOS failure requires genuinely new evidence before a new sign-off.",
        "live_signoff": "NOT_GRANTED",
    }
    save(p, protocol)
    baseline = {}
    for f in (ROOT / "artifacts/fibo_trend_short").rglob("*"):
        if f.is_file() and ART not in f.parents:
            baseline[str(f.relative_to(ROOT))] = sha(f)
    save(ART / "HISTORICAL_PRESERVATION.json", baseline)
    save(ART / "PROGRESS.json", {"stage": "protocol_registered", "goal_complete": False,
         "protocol_sha256": sha(p), "next_action": "prepare development and verify the new execution engine before evaluating candidates"})
    print("Protocol registered; historical files protected:", len(baseline), flush=True)


def bounded_5m(path, end):
    end = utc(end)
    if end > LIMIT:
        raise ValueError("2026 observations are forbidden")
    start = utc("2023-10-01")
    cols = ["open_time", "open", "high", "low", "close", "volume", "quote_volume"]
    df = pd.read_parquet(path, columns=cols, filters=[("open_time", ">=", start), ("open_time", "<", end)])
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    if df.duplicated("open_time").any():
        duplicates = df[df.duplicated("open_time", keep=False)]
        if (duplicates.groupby("open_time")[cols[1:]].nunique() > 1).any().any():
            raise ValueError(f"Conflicting candles in {path}")
        df = df.drop_duplicates("open_time")
    df = df.set_index("open_time").sort_index()
    if len(df) and (df.index.max() >= end or df.index.min() < start):
        raise AssertionError("Loader boundary violated")
    if len(df) and (not np.isfinite(df.to_numpy()).all() or (df[["open", "high", "low", "close"]] <= 0).any().any()):
        raise ValueError("Invalid prices")
    return df


def h1_frame(df):
    g = df.resample("1h")
    out = g.agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "quote_volume": "sum"})
    # Counting alone is insufficient if timestamps are not on the exchange grid.
    aligned = df.index.minute % 5 == 0
    if not aligned.all() or (df.index.second != 0).any():
        raise ValueError("Off-grid five-minute candle")
    return out.loc[g["open"].count() == 12].dropna()


def monthly_rows(symbol, frame, months):
    if symbol in EXCLUDE or frame.empty:
        return {}
    daily = frame["quote_volume"].resample("1D").sum()
    h4 = resample_1h_to_htf(frame, "4h")
    wick = (h4.high - h4[["open", "close"]].max(axis=1)) / h4.close * 100
    result = {}
    for month in months:
        lower = month - pd.Timedelta(days=63)
        active = daily.loc[(daily.index >= lower) & (daily.index < month)]
        active = active[active > 0]
        w = wick.loc[(h4.index >= lower) & (h4.close_time <= month)]
        if len(active) >= 50 and len(w) >= 10:
            p90 = float(np.percentile(w, 90))
            if p90 <= 3.2 and float(active.median()) > 0:
                result[month.strftime("%Y-%m")] = {"symbol": symbol, "median_quote_volume": float(active.median()), "active_days": len(active), "wick_p90_pct": p90}
    return result


def stage_permission(stage):
    if stage == "validation" and not (ART / "SHORTLIST_LOCK.json").exists():
        raise ValueError("Freeze the development shortlist before loading validation")
    if stage == "final_oos" and not (ART / "WINNER_LOCK.json").exists():
        raise ValueError("Freeze the validation winner before loading final OOS")


def prepare(stage):
    stage_permission(stage)
    start, end = map(utc, WINDOWS[stage])
    directory = ART / stage
    if (directory / "DATA_MANIFEST.json").exists():
        raise FileExistsError("Stage already prepared; reuse its frozen snapshots")
    directory.mkdir(exist_ok=True)
    (directory / "bars_5m").mkdir(exist_ok=True)
    months = pd.date_range(start, end - pd.Timedelta(days=1), freq="MS")
    member_rows = {m.strftime("%Y-%m"): [] for m in months}
    inputs = {}
    files = sorted(p for p in LAKE.glob("*USDT.parquet"))
    for i, path in enumerate(files, 1):
        df = bounded_5m(path, end)
        frame = h1_frame(df)
        if len(frame) < 200:
            continue
        symbol = path.stem
        destination = directory / "bars_5m" / path.name
        df.to_parquet(destination)
        inputs[symbol] = {"snapshot_sha256": sha(destination), "source": str(path), "rows_5m": len(df),
                          "complete_hours": len(frame), "first_open": df.index.min().isoformat(), "last_open": df.index.max().isoformat()}
        for ym, row in monthly_rows(symbol, frame, months).items():
            member_rows[ym].append(row)
        if i % 50 == 0:
            print(f"{stage}: bounded data {i}/{len(files)}", flush=True)
    members = {m: sorted(rows, key=lambda r: (-r["median_quote_volume"], r["symbol"]))[:50] for m, rows in member_rows.items()}
    save(directory / "MEMBERSHIP.json", members)
    save(directory / "DATA_MANIFEST.json", {"stage": stage, "protocol_sha256": sha(ART / "PROTOCOL.json"),
         "start": start.isoformat(), "end_exclusive": end.isoformat(), "inputs": inputs,
         "symbols": len(inputs), "membership_sha256": sha(directory / "MEMBERSHIP.json"),
         "post_2025_observations_loaded": 0, "future_stages_loaded": False})
    print(f"{stage}: {len(inputs)} bounded symbols; {len(set(r['symbol'] for rows in members.values() for r in rows))} PIT members", flush=True)


def simulate_path(bars, entry, stop, targets, exit_mode="ladder"):
    """Pure 5-minute fixed-quantity path, no fees/funding and no portfolio state.

    Each tuple: close epoch seconds, close mark, remaining start/end, active stop,
    change in total gross return, terminal flag. Missing bars are reported rather
    than using future completeness to silently select profitable observations.
    """
    if exit_mode not in {"ladder", "tp1"}:
        raise ValueError("Unknown exit mode")
    if not stop > entry > targets[0] > targets[1] > targets[2] > 0:
        raise ValueError("Invalid short ladder")
    rem, realized, previous, active = 1.0, 0.0, 0.0, stop
    hit = [False, False, False]
    trace = []
    reason = "horizon"
    for i, (opened, o, high, low, close) in enumerate(bars):
        before = rem
        done = False
        if high >= active:
            realized += rem * (entry - max(active, o)) / entry
            rem, done, reason = 0.0, True, "stop" if not hit[0] else "ratchet"
        if not done:
            for j, target in enumerate(targets):
                if hit[j] or low > target:
                    continue
                weight = 1.0 if exit_mode == "tp1" else (.5, .3, .2)[j]
                weight = min(weight, rem)
                realized += weight * (entry - target) / entry
                rem -= weight
                hit[j] = True
                if rem < 1e-12:
                    rem, done, reason = 0.0, True, f"tp{j+1}"
                    break
                active = entry if j == 0 else targets[0]
                if high >= active:
                    realized += rem * (entry - active) / entry
                    rem, done, reason = 0.0, True, "ratchet"
                    break
        if not done and i == len(bars) - 1:
            realized += rem * (entry - close) / entry
            rem, done, reason = 0.0, True, "horizon"
        total = realized + rem * (entry - close) / entry
        trace.append((int(opened + 300), float(close), before, rem, active, total - previous, done))
        previous = total
        if done:
            break
    if not trace:
        raise ValueError("No execution bars")
    return {"trace": trace, "gross_return": realized, "exit_reason": reason, "exit_ts": trace[-1][0]}


def collect_one(stage, symbol):
    directory = ART / stage
    member = read(directory / "MEMBERSHIP.json")
    allowed = {ym for ym, rows in member.items() if symbol in {r["symbol"] for r in rows}}
    frame5 = pd.read_parquet(directory / "bars_5m" / f"{symbol}.parquet")
    frame = h1_frame(frame5)
    btc = h1_frame(pd.read_parquet(directory / "bars_5m/BTCUSDT.parquet"))
    bhtf = {tf: calc_htf_features_no_bfill(resample_1h_to_htf(btc, tf)) for tf in ("4h", "1d")}
    start, end = map(utc, WINDOWS[stage])
    # Avoid labeling entries whose full maximum holding window crosses a split.
    entry_end = end - pd.Timedelta(days=5)
    raw = collect_symbol_milestones_v402(symbol, frame, bhtf, entry_start_ts=start,
            entry_end_ts=entry_end - pd.Timedelta(hours=1))["raw_candidates"]
    epochs = epoch_seconds(frame5.index)
    prices = frame5[["open", "high", "low", "close"]].to_numpy()
    output, skipped = [], Counter()
    for c in raw:
        if c["entry_ym"] not in allowed or "m6_f4_expanded" not in c["eligible_milestones"]:
            continue
        decision = utc(c["decision_time"])
        if not start <= decision < entry_end:
            continue
        # Only pre-signal continuity controls can veto an entry.
        past = frame.loc[(frame.index >= decision - pd.Timedelta(hours=24)) & (frame.index < decision)]
        if len(past) != 24:
            skipped["incomplete_past_24h"] += 1
            continue
        fill_time = decision + pd.Timedelta(minutes=5)
        ts = int(fill_time.timestamp())
        idx = int(np.searchsorted(epochs, ts))
        if idx == len(epochs) or epochs[idx] != ts:
            skipped["missing_scheduled_entry_bar"] += 1
            continue
        entry = float(prices[idx, 0])
        stop = float(c["sl_m6"])
        targets = [float(c[k]) for k in ("tp1", "tp2", "tp3")]
        if not stop > entry > targets[0] > targets[1] > targets[2] > 0:
            skipped["gap_invalidated_ladder"] += 1
            continue
        horizon = 72 if c["tf"] == "4h" else 120
        stop_ts = min(int(end.timestamp()), ts + horizon * 3600)
        j = int(np.searchsorted(epochs, stop_ts))
        bars = [(int(t), *map(float, row)) for t, row in zip(epochs[idx:j], prices[idx:j])]
        paths = {mode: simulate_path(bars, entry, stop, targets, mode) for mode in ("ladder", "tp1")}
        used_end = max(p["exit_ts"] for p in paths.values())
        used = epochs[idx:int(np.searchsorted(epochs, used_end))]
        missing = int(np.sum(np.maximum(0, np.diff(used) // 300 - 1)))
        bdf = bhtf[c["tf"]]
        visible = bdf.loc[bdf.close_time <= decision]
        output.append({"id": f"{symbol}:{c['tf']}:{ts}", "symbol": symbol, "tf": c["tf"], "wave_key": c["wave_key"],
            "decision_ts": int(decision.timestamp()), "entry_ts": ts, "entry": entry, "signal_entry": c["entry_price"],
            "stop": stop, "targets": targets, "score": float(c["full_conviction_score"]),
            "milestones": c["eligible_milestones"], "rr1": (entry-targets[0])/(stop-entry),
            "btc_weak": bool(len(visible) and visible.iloc[-1].ewmac_16_64 <= 0),
            "missing_execution_bars": missing, "paths": paths})
    destination = directory / "candidates" / f"{symbol}.pkl.gz"
    with gzip.open(destination, "wb") as fh:
        pickle.dump(output, fh, protocol=5)
    return symbol, len(output), dict(skipped), sha(destination)


def collect(stage, workers):
    stage_permission(stage)
    directory = ART / stage
    manifest = read(directory / "DATA_MANIFEST.json")
    for symbol, row in manifest["inputs"].items():
        if sha(directory / "bars_5m" / f"{symbol}.parquet") != row["snapshot_sha256"]:
            raise AssertionError("Bounded input was changed")
    members = read(directory / "MEMBERSHIP.json")
    symbols = sorted({r["symbol"] for rows in members.values() for r in rows})
    (directory / "candidates").mkdir(exist_ok=True)
    results = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        fs = [pool.submit(collect_one, stage, s) for s in symbols]
        for i, future in enumerate(as_completed(fs), 1):
            s, count, skipped, digest = future.result()
            results[s] = {"candidates": count, "rejections": skipped, "sha256": digest}
            print(f"{stage} candidates {i}/{len(symbols)}: {s}={count}", flush=True)
    save(directory / "CANDIDATE_MANIFEST.json", {"protocol_sha256": sha(ART / "PROTOCOL.json"),
         "source_sha256": sha(__file__), "data_manifest_sha256": sha(directory / "DATA_MANIFEST.json"), "symbols": results})


def passes(c, gate):
    if gate == "expanded": return True
    if gate == "elite": return "m4_f2_elite" in c["milestones"]
    if gate == "sniper": return "m6_f4_sniper" in c["milestones"]
    if gate == "elite_sniper": return "m6_f4_elite_sniper" in c["milestones"]
    if gate == "btc_weak": return c["btc_weak"]
    if gate == "score68": return c["score"] >= 68
    if gate == "rr1": return c["rr1"] >= 1.0
    raise ValueError("Unknown gate")


def position_fraction(entry, stop, mode):
    if entry <= 0 or stop <= entry:
        raise ValueError("Invalid risk inputs")
    if mode == "fixed": return .20
    if mode != "risk": raise ValueError("Unknown sizing")
    return min(.20, .005 / ((stop-entry)/entry + .006))


def portfolio(candidates, variant, start, end, cost_bps=40, funding_stress=True):
    """Event-coupled cash/MTM engine, fixed quantities and deterministic tie order."""
    start, end = int(utc(start).timestamp()), int(utc(end).timestamp())
    selected = sorted((c for c in candidates if start <= c["entry_ts"] < end-5*86400 and passes(c, variant["gate"])),
                      key=lambda c: (c["entry_ts"], -c["score"], c["symbol"], c["tf"]))
    equity = 100.0
    open_pos, heap, ledger, curve = {}, [], [], [(start, 100.0)]
    waves, cooldown, rejected = set(), {}, Counter()
    serial = 0
    fee_rate = cost_bps / 10000
    maxrisk = .12 if variant["sizing"] == "fixed" else .02

    def advance(target):
        nonlocal equity
        while heap and heap[0][0] <= target:
            t = heap[0][0]
            while heap and heap[0][0] == t:
                _, _, pid, step = heapq.heappop(heap)
                p = open_pos[pid]
                _, price, rem_start, rem_end, active, delta, done = step
                funding = 0.0
                if funding_stress and t % (8*3600) == 0 and p["entry_ts"] < t:
                    # Conservative boundary convention: exposure at start of the
                    # final 5m interval is charged using its close-price proxy.
                    funding = -p["qty"] * rem_start * price * .0001
                exit_fee = p["notional"] * fee_rate * .5 if done else 0.0
                pnl = p["notional"] * delta + funding - exit_fee
                equity += pnl
                p["pnl"] += pnl
                p["funding"] += funding
                p["fees"] += exit_fee
                p.update(rem=rem_end, mark=price, active=active)
                if done:
                    p["exit_ts"] = t
                    ledger.append(dict(p))
                    del open_pos[pid]
            curve.append((t, equity))

    for c in selected:
        t = c["entry_ts"]
        advance(t)
        key = (c["symbol"], c["tf"])
        wave = (*key, c["wave_key"])
        if wave in waves or t < cooldown.get(key, 0):
            rejected["wave_or_cooldown"] += 1
            continue
        if equity <= 0:
            rejected["insolvent"] += 1
            continue
        frac = position_fraction(c["entry"], c["stop"], variant["sizing"])
        notional = equity * frac
        qty = notional / c["entry"]
        current_notional = sum(p["qty"]*p["rem"]*max(p["mark"], p["entry"]) for p in open_pos.values())
        current_risk = sum(p["qty"]*p["rem"]*max(0, p["active"]-p["mark"], p["active"]-p["entry"]) for p in open_pos.values())
        if len(open_pos) >= 5 or current_notional+notional > equity+1e-9 or current_risk+qty*(c["stop"]-c["entry"]) > equity*maxrisk+1e-9:
            rejected["portfolio_cap"] += 1
            continue
        path = c["paths"][variant["exit"]]
        if path["exit_ts"] > end:
            raise AssertionError("Outcome crossed evaluation boundary")
        fee = notional*fee_rate*.5
        p = {"id": c["id"], "symbol": c["symbol"], "tf": c["tf"], "entry_ts": t,
             "entry": c["entry"], "stop": c["stop"], "qty": qty, "notional": notional,
             "equity_at_entry": equity, "rem": 1.0, "mark": c["entry"], "active": c["stop"],
             "gross_return": path["gross_return"], "pnl": -fee, "fees": fee, "funding": 0.0,
             "missing_execution_bars": c["missing_execution_bars"], "exit_reason": path["exit_reason"]}
        equity -= fee
        open_pos[c["id"]] = p
        curve.append((t, equity))
        for step in path["trace"]:
            serial += 1
            heapq.heappush(heap, (step[0], serial, c["id"], step))
        waves.add(wave)
        cooldown[key] = max(path["exit_ts"], t+4*3600)
    advance(end)
    if open_pos:
        raise AssertionError("Unsettled positions")
    curve.append((end, equity))
    assert len({r["id"] for r in ledger}) == len(ledger)
    for p in ledger:
        expected = p["notional"]*p["gross_return"]-p["fees"]+p["funding"]
        if abs(expected-p["pnl"]) > 1e-8:
            raise AssertionError("Trade cash reconciliation failed")
    if abs(equity-100-sum(p["pnl"] for p in ledger)) > 1e-8:
        raise AssertionError("Portfolio cash reconciliation failed")
    values = np.array([v for _, v in curve])
    peak = np.maximum.accumulate(values)
    dd = float(np.max(1-values/peak)*100)
    series = pd.Series([v for _, v in curve], index=pd.to_datetime([t for t, _ in curve], unit="s", utc=True))
    series = series.groupby(level=0).last()
    grid = pd.date_range(utc(pd.Timestamp(start, unit="s")), utc(pd.Timestamp(end, unit="s")), freq="7D")
    if grid[-1] != pd.Timestamp(end, unit="s", tz="UTC"):
        grid = grid.append(pd.DatetimeIndex([pd.Timestamp(end, unit="s", tz="UTC")]))
    weekly_nav = series.reindex(series.index.union(grid)).sort_index().ffill().loc[grid]
    weekly = weekly_nav.pct_change().dropna().to_numpy()
    # A partial final week is retained and explicitly disclosed.
    return {"return_pct": (equity-100), "max_dd_pct": dd, "trades": len(ledger),
            "fees_pct_initial": sum(p["fees"] for p in ledger), "funding_pct_initial": sum(p["funding"] for p in ledger),
            "rejected": dict(rejected), "weekly_returns": weekly.tolist(), "weekly_grid_includes_partial_last_week": True,
            "ledger": ledger, "curve": curve, "all_cash_reconciled": True,
            "accepted_missing_execution_bars": sum(p["missing_execution_bars"] for p in ledger)}


def block_ci(weekly, seed=407, samples=5000):
    x = np.asarray(weekly, dtype=float)
    if len(x) < 8:
        return {"available": False, "weeks": len(x)}
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, len(x), size=(samples, (len(x)+3)//4))
    indices = (starts[:, :, None]+np.arange(4)) % len(x)
    means = x[indices.reshape(samples, -1)[:, :len(x)]].mean(axis=1)*100
    return {"available": True, "weeks": len(x), "mean_weekly_return_pct": float(x.mean()*100),
            "ci95_pct": np.quantile(means, [.025, .975]).tolist(), "block_weeks": 4,
            "samples": samples, "selection_adjusted": False}


def load_candidates(stage):
    directory = ART / stage
    manifest = read(directory / "CANDIDATE_MANIFEST.json")
    if manifest["protocol_sha256"] != sha(ART / "PROTOCOL.json"):
        raise AssertionError("Protocol changed")
    output = []
    for symbol, row in sorted(manifest["symbols"].items()):
        path = directory / "candidates" / f"{symbol}.pkl.gz"
        if sha(path) != row["sha256"]:
            raise AssertionError("Candidate cache changed")
        with gzip.open(path, "rb") as fh:
            output.extend(pickle.load(fh))
    return output


def evaluate(stage):
    stage_permission(stage)
    directory = ART / stage
    if (directory / "RESULTS.json").exists():
        raise FileExistsError("Results are append-only by experiment version")
    candidates = load_candidates(stage)
    variants = VARIANTS
    if stage != "development":
        lock = read(ART / ("SHORTLIST_LOCK.json" if stage == "validation" else "WINNER_LOCK.json"))
        keep = set(lock["variant_ids"]) | {"reference_m6_fixed"}
        variants = [v for v in VARIANTS if v["id"] in keep]
    start, end = WINDOWS[stage]
    rows, ledgers = {}, {}
    for variant in variants:
        vid = variant["id"]
        rows[vid] = {}
        for cost in (40, 60):
            for stress in (False, True):
                key = f"{cost}bps_{'stress' if stress else 'ex_funding'}"
                result = portfolio(candidates, variant, start, end, cost, stress)
                result["weekly_ci"] = block_ci(result["weekly_returns"])
                ledgers[f"{vid}/{key}"] = {"ledger": result.pop("ledger"), "curve": result.pop("curve")}
                rows[vid][key] = result
        if stage == "development":
            halves = []
            for a, b in [("2024-01-01", "2024-07-01"), ("2024-07-01", "2025-01-01")]:
                r = portfolio(candidates, variant, a, b, 40, True)
                halves.append({"start": a, "end": b, "return_pct": r["return_pct"], "trades": r["trades"], "max_dd_pct": r["max_dd_pct"]})
            rows[vid]["reset_half_year_checks"] = halves
        r = rows[vid]["40bps_stress"]
        print(f"{stage}/{vid}: N={r['trades']} NAV={r['return_pct']:.3f}% DD={r['max_dd_pct']:.3f}%", flush=True)
    save(directory / "RESULTS.json", {"stage": stage, "protocol_sha256": sha(ART / "PROTOCOL.json"),
         "candidate_manifest_sha256": sha(directory / "CANDIDATE_MANIFEST.json"), "source_sha256": sha(__file__),
         "results": rows, "fresh_oos": False, "live_signoff": "NOT_GRANTED"})
    with gzip.open(directory / "LEDGERS.json.gz", "wt", encoding="utf-8") as fh:
        json.dump(ledgers, fh, separators=(",", ":"), allow_nan=False)
    qualified = []
    for vid, row in rows.items():
        a, b = row["40bps_stress"], row["60bps_stress"]
        ok = vid != "reference_m6_fixed" and a["trades"] >= (40 if stage == "development" else 20)
        ok = ok and a["return_pct"] > 0 and b["return_pct"] >= 0 and max(a["max_dd_pct"], b["max_dd_pct"]) <= 15
        ok = ok and a["accepted_missing_execution_bars"] == 0 and b["accepted_missing_execution_bars"] == 0
        if stage == "development":
            ok = ok and all(h["return_pct"] > 0 for h in row["reset_half_year_checks"])
        if stage == "final_oos":
            ci = a["weekly_ci"]
            ok = ok and ci["available"] and ci["ci95_pct"][0] > 0
        row["qualifies"] = bool(ok)
        if ok:
            qualified.append((b["return_pct"]-b["max_dd_pct"], vid))
    qualified.sort(key=lambda p: (-p[0], p[1]))
    # Save the qualification flags with the same result; no later result tuning.
    saved = read(directory / "RESULTS.json")
    saved["results"] = rows
    save(directory / "RESULTS.json", saved)
    if stage in {"development", "validation"} and qualified:
        name = "SHORTLIST_LOCK.json" if stage == "development" else "WINNER_LOCK.json"
        count = 2 if stage == "development" else 1
        save(ART / name, {"variant_ids": [v for _, v in qualified[:count]], "locked_at_utc": datetime.now(timezone.utc).isoformat(),
             "protocol_sha256": sha(ART / "PROTOCOL.json"), "selection_results_sha256": sha(directory / "RESULTS.json"),
             "unopened_next_stage": "validation" if stage == "development" else "final_oos"})
    save(ART / "PROGRESS.json", {"stage": stage+"_evaluated", "goal_complete": False,
         "qualified_variants": [v for _, v in qualified], "final_oos_opened": (ART / "final_oos/DATA_MANIFEST.json").exists(),
         "next_action": "inspect evidence, record mini alphas, and continue the registered research process",
         "live_signoff": "NOT_GRANTED"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init", "prepare", "collect", "evaluate"])
    parser.add_argument("--stage", choices=WINDOWS, default="development")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.action == "init": init()
    elif args.action == "prepare": prepare(args.stage)
    elif args.action == "collect": collect(args.stage, args.workers)
    else: evaluate(args.stage)


if __name__ == "__main__":
    main()
