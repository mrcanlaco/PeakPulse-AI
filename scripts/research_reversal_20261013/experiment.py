"""Bounded offline reversal filters; no downloads, selection rerun, or live imports.

Freeze before run. Reuse audited same-entry Compact cash flows, never replay
delayed entries with an old outcome. All output stays in this research folder.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/research_reversal_20261013"
PRIOR = ROOT / "artifacts/research_branches_20261013/v3/report.json"
SPACING = ROOT / "artifacts/research_branches_20261012/v3/report.json"
MANIFEST = ROOT / "artifacts/annual_profit_20260918/prices/price_manifest.json"
VARIANTS = ("baseline", "A_negative_1h", "F_failed_retest", "R_weaker_BTC_1h", "AF", "AR")
STEP = pd.Timedelta(minutes=5)

RULES = {
    "A_negative_1h": "Inherited exact entry-time PIT price_ret_1h < 0; unchanged control.",
    "F_failed_retest": {
        "window": "73 exact closes t-6h through t, inclusive; blocks exclude first endpoint",
        "anchor": "bars 1..24 (t-6h,t-4h], H=max(high)",
        "selloff": "bars 25..48 (t-4h,t-2h], last close < anchor last close",
        "rebound": "bars 49..60 (t-2h,t-1h], max(high) > max(high of bars 37..48) AND max(high) < H",
        "rejection": "bars 61..72 (t-1h,t], max(high) < H AND last close < rebound last close",
        "thresholds": "Strict comparisons, fixed 2h/2h/1h/1h partitions; no peak search or sweep.",
    },
    "R_weaker_BTC_1h": "coin(close_t/close_t-1h-1) - BTC(close_t/close_t-1h-1) < 0; beta fixed 1, no fit; BTC only, no future basket membership.",
    "AF_AR": "Intersections test incremental information beyond A; no further combinations.",
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def now():
    return datetime.now(timezone.utc).isoformat()


def finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def verify(hashes):
    for path, expected in hashes.items():
        if digest(Path(path)) != expected:
            raise RuntimeError("Frozen source changed: " + path)


def freeze():
    lock = OUT / "experiment_lock.json"
    if lock.exists():
        raise RuntimeError("Existing lock must not be overwritten")
    old = read(PRIOR)
    hashes = dict(old["source_hashes"])
    verify(hashes)
    manifest = read(MANIFEST)
    price_root = Path(manifest["price_root"])
    paths = [Path(__file__), PRIOR, SPACING, MANIFEST, OUT / "protocol.md"]
    paths += [price_root / (s + ".parquet") for s in sorted({e["symbol"] for e in old["events"]} | {"BTCUSDT"})]
    available, missing = {}, []
    for path in paths:
        if path.exists():
            hashes[str(path)] = digest(path)
            if path.suffix == ".parquet":
                available[path.stem] = str(path)
        elif path.suffix == ".parquet":
            missing.append(str(path))
        else:
            raise FileNotFoundError(path)
    write(lock, {"frozen_at_utc": now(), "rules": RULES, "variants": list(VARIANTS),
        "source_hashes": hashes, "price_paths": available, "missing_price_paths": missing,
        "primary_population": "Champion within each lane, historical primary; runtime reference never pooled",
        "secondary_population": "All frozen events within each lane, diagnostic only",
        "denominator": "Common financially certified AND all-candidate-feature-complete opportunities. Rejections zero allocation; missing finance/features excluded from EVERY variant and counted separately.",
        "execution": "Same-entry Compact 0/3/6%, weights 20/30/50, TP20/SL16, six-hour adds, 48h exit. Reuse timestamped fees/funding and compact_cost2x; no execution changes.",
        "history_status": "Previously inspected development/exploratory history, never a new holdout",
        "falsification": "Do not advance a hypothesis on historical profitability. Nonpositive paired opportunity difference vs A, no changed decisions, or <10 feature-complete funded selections means no support in this round; sparse means uninformative, not proof of no effect.",
        "selection_rule": "No winning threshold selection or expansion after results",
        "account_equity": None, "eligible_for_combination": False, "live_changes_allowed": False})
    print(json.dumps({"lock": str(lock), "sha256": digest(lock), "price_files": len(available)}))


def validate_window(frame, t, hours=6):
    """Observe completed bars only. t is close+1ms, never bar open."""
    t = pd.Timestamp(t)
    if t.tzinfo is None:
        raise ValueError("UTC-aware decision timestamp required")
    t = t.tz_convert("UTC")
    x = frame.copy()
    x["boundary"] = pd.to_datetime(x["close_time"], utc=True) + pd.Timedelta(milliseconds=1)
    x = x[(x.boundary >= t - pd.Timedelta(hours=hours)) & (x.boundary <= t)].sort_values("boundary")
    expected = pd.date_range(t - pd.Timedelta(hours=hours), t, freq=STEP)
    if len(x) != len(expected) or list(x.boundary) != list(expected):
        return None, "missing_duplicate_or_noncanonical_closes"
    values = x[["open", "high", "low", "close"]]
    if not all(finite(float(v)) and v > 0 for v in values.to_numpy().flat):
        return None, "invalid_ohlc"
    if not ((x.high >= x[["open", "close", "low"]].max(axis=1)) &
            (x.low <= x[["open", "close", "high"]].min(axis=1))).all():
        return None, "inconsistent_ohlc"
    return x.reset_index(drop=True), None


def load_window(path, t, hours):
    if path is None:
        return None, "price_file_unavailable"
    t = pd.Timestamp(t)
    lo = t - pd.Timedelta(hours=hours) - pd.Timedelta(milliseconds=1)
    hi = t - pd.Timedelta(milliseconds=1)
    x = pd.read_parquet(path, columns=["close_time", "open", "high", "low", "close"],
        filters=[("close_time", ">=", lo.to_pydatetime()), ("close_time", "<=", hi.to_pydatetime())])
    return validate_window(x, t, hours)


def failed_retest(x):
    anchor, sell, rebound, reject = x.iloc[1:25], x.iloc[25:49], x.iloc[49:61], x.iloc[61:73]
    h = float(anchor.high.max())
    return bool(sell.close.iloc[-1] < anchor.close.iloc[-1] and
        rebound.high.max() > sell.iloc[-12:].high.max() and rebound.high.max() < h and
        reject.high.max() < h and reject.close.iloc[-1] < rebound.close.iloc[-1])


def measure(coin, btc, pit_return):
    rcoin = float(coin.close.iloc[-1] / coin.close.iloc[-13] - 1) if coin is not None else None
    rbtc = float(btc.close.iloc[-1] / btc.close.iloc[0] - 1) if btc is not None else None
    f = failed_retest(coin) if coin is not None else None
    r = rcoin - rbtc if rcoin is not None and rbtc is not None else None
    a = pit_return < 0 if finite(pit_return) else None
    gates = {"baseline": True, "A_negative_1h": a, "F_failed_retest": f,
        "R_weaker_BTC_1h": r < 0 if r is not None else None,
        "AF": a and f if a is not None and f is not None else None,
        "AR": a and r < 0 if a is not None and r is not None else None}
    return {"coin_return_1h": rcoin, "btc_return_1h": rbtc, "relative_return_1h": r,
        "pit_return_1h": pit_return, "raw_minus_pit_return": rcoin - pit_return if rcoin is not None and finite(pit_return) else None}, gates


def aggregate(rows):
    funded = [r for r in rows if r["financially_eligible"]]
    common = [r for r in funded if r["features_complete"]]
    out = {"frozen_rows": len(rows), "unique_source_events": len({r["source_event_id"] for r in rows}),
        "financially_eligible": len(funded), "financially_excluded": len(rows)-len(funded),
        "funded_feature_excluded": len(funded)-len(common), "common_opportunities": len(common),
        "unique_symbols_common": len({r["symbol"] for r in common}),
        "feature_missing_reasons": dict(Counter(x for r in rows for x in r["feature_exclusions"])),
        "variants": {}, "incremental_vs_A": {}}
    for variant in VARIANTS:
        chosen = [r for r in common if r["gates"][variant]]
        scores = [r["net"] if r["gates"][variant] else 0. for r in common]
        diffs = [s-r["net"] for s,r in zip(scores,common)]
        # Symbol/episode observations remain dependent; no iid standard error.
        loo = [statistics.mean(diffs[:i]+diffs[i+1:]) for i in range(len(diffs))] if len(diffs)>1 else []
        by_symbol = {s: statistics.mean([d for d,r in zip(diffs,common) if r["symbol"] != s])
            for s in sorted({r["symbol"] for r in common}) if any(r["symbol"] != s for r in common)}
        out["variants"][variant] = {
            "selected": len(chosen), "selected_unique_symbols": len({r["symbol"] for r in chosen}),
            "rejected_zero_allocation": len(common)-len(chosen),
            "accepted_financially_excluded": sum(r["gates"][variant] is True and not r["financially_eligible"] for r in rows),
            "selected_only_mean": statistics.mean(r["net"] for r in chosen) if chosen else None,
            "opportunity_mean": statistics.mean(scores) if scores else None,
            "opportunity_mean_cost2x": statistics.mean(r["net_cost2x"] if r["gates"][variant] else 0. for r in common) if common else None,
            "paired_vs_baseline": statistics.mean(diffs) if diffs else None,
            "status_counts": dict(Counter(r["status"] for r in chosen)),
            "leave_one_event_out_paired_range": [min(loo),max(loo)] if loo else None,
            "leave_one_symbol_out_paired": by_symbol,
        }
    for v in ("F_failed_retest", "R_weaker_BTC_1h", "AF", "AR"):
        ds = [(r["net"] if r["gates"][v] else 0.) - (r["net"] if r["gates"]["A_negative_1h"] else 0.) for r in common]
        out["incremental_vs_A"][v] = {"common_n": len(common),
            "mean_difference": statistics.mean(ds) if ds else None,
            "changed_decisions": sum(r["gates"][v] != r["gates"]["A_negative_1h"] for r in common)}
    return out


def check_cashflows(event, expected_net):
    base = event["variants"]["compact"]
    stress = event["variants"]["compact_cost2x"]
    for x in (base, stress):
        if not x["eligible"]:
            raise RuntimeError("Inherited outcome not eligible")
        if not all(finite(x[k]) for k in ("gross_return_planned", "costs_planned", "funding_planned", "net_return_planned")):
            raise RuntimeError("Nonfinite inherited finance")
        if abs(x["gross_return_planned"] - x["costs_planned"] + x["funding_planned"] - x["net_return_planned"]) > 1e-12:
            raise RuntimeError("Cash flow identity broken")
        if abs(sum(p["cash_flow"] for p in x["funding_payments"]) - x["funding_planned"]) > 1e-12:
            raise RuntimeError("Funding sum broken")
        entry, exit_ = pd.Timestamp(x["fills"][0]["timestamp"]), pd.Timestamp(x["exit_time"])
        for p in x["funding_payments"]:
            ts = pd.Timestamp(p["timestamp"])
            if not entry < ts <= exit_:
                raise RuntimeError("Funding outside held interval")
            q = sum(f["quantity"] for f in x["fills"] if pd.Timestamp(f["timestamp"]) < ts)
            if abs(q-p["quantity"]) > 1e-9 * max(1., q):
                raise RuntimeError("Future leg used for funding")
            if abs(q*p["mark_price"]*p["rate"]-p["cash_flow"]) > 1e-12:
                raise RuntimeError("Funding cash flow mismatch")
    if abs(base["net_return_planned"]-expected_net) > 1e-12:
        raise RuntimeError("Baseline finance differs from prior round")
    return stress["net_return_planned"]


def run():
    lock_path = OUT / "experiment_lock.json"
    lock = read(lock_path)
    if lock["rules"] != RULES or lock["variants"] != list(VARIANTS):
        raise RuntimeError("Rules differ from lock")
    verify(lock["source_hashes"])
    old = read(PRIOR)
    spacing = {r["lane_event_key"]: r for r in read(SPACING)["events"]}
    rows, cache = [], {}
    seen = set()
    for event in old["events"]:
        key = event["lane_event_key"]
        if key in seen:
            raise RuntimeError("Duplicate lane event")
        seen.add(key)
        t = pd.Timestamp(event["signal_time_utc"])
        if pd.Timestamp(event["feature_time_utc"]) + pd.Timedelta(milliseconds=1) != t:
            raise RuntimeError("Decision boundary mismatch")
        sid = event["source_event_id"]
        if sid not in cache:
            coin, ce = load_window(lock["price_paths"].get(event["symbol"]), t, 6)
            btc, be = load_window(lock["price_paths"].get("BTCUSDT"), t, 1)
            measures, gates = measure(coin, btc, event["features"]["price_ret_1h"])
            reasons = (["coin:"+ce] if ce else []) + (["BTC:"+be] if be else [])
            if not finite(event["features"]["price_ret_1h"]):
                reasons.append("missing_PIT_control")
            cache[sid] = (event["symbol"], str(t), measures, gates, reasons)
        symbol, time_, measures, gates, reasons = cache[sid]
        if symbol != event["symbol"] or time_ != str(t):
            raise RuntimeError("Source ID collision")
        ref = spacing[key]
        if ref["source_event_id"] != sid or ref["eligible"] != event["financially_eligible"]:
            raise RuntimeError("Cohort finance identity changed")
        stress = check_cashflows(ref, event["net_return_planned"]) if event["financially_eligible"] else None
        rows.append({**{k:event[k] for k in ("lane_event_key", "source_event_id", "symbol", "lane", "champion", "signal_time_utc", "financially_eligible", "financial_exclusions", "status")},
            "features": measures, "gates": gates, "feature_exclusions": reasons,
            "features_complete": not reasons, "net": event["net_return_planned"], "net_cost2x": stress})
    summary = {lane: {"champion": aggregate([r for r in rows if r["lane"]==lane and r["champion"]]),
        "all_frozen_diagnostic": aggregate([r for r in rows if r["lane"]==lane])} for lane in sorted({r["lane"] for r in rows})}
    verify(lock["source_hashes"])
    write(OUT / "report.json", {"completed_at_utc": now(), "status": "exploratory_no_promotion",
        "lock_sha256": digest(lock_path), "source_hashes": lock["source_hashes"], "by_lane": summary,
        "cohort": {"rows":len(rows), "unique_source_events":len(cache), "funded_rows":sum(r["financially_eligible"] for r in rows),
            "feature_complete_rows":sum(r["features_complete"] for r in rows),
            "max_abs_raw_minus_pit_return":max(abs(r["features"]["raw_minus_pit_return"]) for r in rows if r["features"]["raw_minus_pit_return"] is not None)},
        "eligible_for_combination": False, "daily_equity": None,
        "limitations": ["Dependent symbols/episodes and overlapping lanes; no iid sample or confidence claim.",
            "No delayed entry tested. Same-entry filters do not prove benefit from waiting for confirmation.",
            "OHLC fills and modeled costs inherited; no queue/partial fills, historical low/midcap universe audit, or complete marked account.",
            "Missing finance not zero; common-feature restriction can introduce nonrandom exclusions.",
            "Beta-one BTC difference is a rough comparison, not beta-neutral residual alpha.",
            "Leave-one-out diagnostics are sensitivity checks on reused history, not holdouts."], "events":rows})
    print(json.dumps({"cohort":read(OUT / "report.json")["cohort"], "by_lane":summary},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    m = p.add_mutually_exclusive_group(required=True)
    m.add_argument("--freeze", action="store_true")
    m.add_argument("--run", action="store_true")
    a = p.parse_args()
    freeze() if a.freeze else run()
