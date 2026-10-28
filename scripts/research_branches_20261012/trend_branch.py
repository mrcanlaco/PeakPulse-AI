"""Bounded, frozen audit of the existing trend champion; never changes live state.

All history was previously inspected: none of these comparisons is new OOS.
Run from repository root with .venv/Scripts/python.exe.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from dao_vang.research.data_loader import load_universe, slice_universe
from dao_vang.research.protocol import FULL_START, FULL_END, VAL_START, VAL_END, TEST_START, TEST_END, KLINES_DIR, FUNDING_DIR
from dao_vang.research.walkforward_engine import prepare_multiasset_features, simulate_candidate, compute_metrics

OUT = ROOT / "artifacts/research_branches_20261012/trend"
OLD = ROOT / "artifacts/walkforward_2020_2026"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_once(path, obj):
    text = json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False,
                      default=lambda value: value.item() if isinstance(value, np.generic) else str(value))
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(text + "\n")


def prepare(data):
    timeline, features = prepare_multiasset_features(data)
    for feature in features.values():
        feature["ema450"] = pd.Series(feature["close"]).shift(1).ewm(span=450).mean().to_numpy()
    return timeline, features


def metrics(nav):
    total, cagr, dd, calmar = compute_metrics(nav)
    return dict(total_return_pct=total * 100, cagr_pct=cagr * 100, maxdd_pct=dd * 100, calmar=calmar)


def synthetic_features(n=305):
    feature = {key: np.full(n, value, dtype=float) for key, value in {
        "open": 100, "high": 101, "low": 99, "close": 100,
        "funding_rate": 0, "atr14": 2, "ann_vol": .36,
        "ema40": 80, "ema450": 80, "donchian_30": 90, "mom14": .1,
    }.items()}
    timeline = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
    spec = dict(universe=["BTCUSDT"], macro_btc_filter="ema450", entry_signal="donchian_30",
                trail_atr_mult=2.5, break_even_atr_mult=1.5, target_annual_vol=.36, slots=2)
    return timeline, {"BTCUSDT": feature}, spec


def causal_probes():
    timeline, features, spec = synthetic_features()
    baseline, _ = simulate_candidate(timeline, features, spec)
    features["BTCUSDT"]["close"][302:] = 200
    changed, _ = simulate_candidate(timeline, features, spec)
    prefix_identical = bool(np.array_equal(baseline.iloc[:302], changed.iloc[:302]))

    timeline, features, spec = synthetic_features()
    features["BTCUSDT"]["low"][301] = 1
    wick, _ = simulate_candidate(timeline, features, spec)

    timeline, features, spec = synthetic_features()
    features["BTCUSDT"]["funding_rate"][300] = .01
    _, funding_base = simulate_candidate(timeline, features, spec)
    features["BTCUSDT"]["close"][300] = 200
    _, funding_changed = simulate_candidate(timeline, features, spec)
    return {
        "future_close_mutation_preserves_prior_nav": prefix_identical,
        "intrabar_low_below_stop_ignored_when_close_recovers": bool(np.array_equal(baseline, wick)),
        "new_entry_at_settlement_bar_charged_funding": funding_base["total_funding_usdt"],
        "funding_at_open_100_but_close_200": funding_changed["total_funding_usdt"],
        "funding_same_open_base_close_100": funding_base["total_funding_usdt"],
        "interpretation": "Synthetic causal checks only. Funding uses bar-close not settlement mark; timestamp ordering for fills vs settlement is unresolved. Stops are close-confirmed next-open exits, not intrabar protective orders.",
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lock = json.loads((OLD / "candidate_lock.json").read_text(encoding="utf-8"))
    spec = lock["champion_candidate"]["spec"]
    source_paths = [Path(__file__), ROOT / "tests/unit/research_branches_20261012/test_trend_branch.py"]
    source_paths += [ROOT / "src/dao_vang/research" / name for name in
                     ["walkforward_engine.py", "data_loader.py", "protocol.py", "run_full_strict_pipeline.py"]]
    source_paths += [OLD / name for name in ["candidate_lock.json", "candidate_lock.sha256", "full_evaluation_results.json", "champion_equity_curve.parquet"]]
    source_paths += [folder / f"{symbol}{suffix}.parquet" for symbol in spec["universe"]
                     for folder, suffix in [(KLINES_DIR, "_1h"), (FUNDING_DIR, "_funding")]]
    hashes = {str(path.resolve()): digest(path) for path in source_paths}
    frozen = {
        "branch": "trend", "frozen_at": datetime.now(timezone.utc).isoformat(), "candidate": spec,
        "historical_reuse": True, "new_oos": False, "source_hashes": hashes,
        "experiments": ["original full continuous 10bps", "cold-start validation 10bps", "warm-indicator flat-start validation 10bps", "full continuous 20bps"],
        "causal_tests": ["future close mutation", "intrabar stop wick", "funding settlement valuation"],
        "selection_rule": "No parameter selection; reproduce only existing locked champion.",
    }
    if (OUT / "experiment_lock.json").exists():
        prior = json.loads((OUT / "experiment_lock.json").read_text(encoding="utf-8"))
        assert prior["candidate"] == frozen["candidate"]
        assert prior["experiments"] == frozen["experiments"]
        changed = [path for path, old_hash in prior["source_hashes"].items() if digest(path) != old_hash]
        assert changed == [str(Path(__file__).resolve())], changed
        repair_number = len(list(OUT.glob("serialization_repair*.json"))) + 1
        write_once(OUT / f"serialization_repair_{repair_number}.json", {
            "at": datetime.now(timezone.utc).isoformat(), "changed_sources": changed,
            "reason": "First replay finished but report serialization rejected numpy.bool_. Convert comparison to builtin bool; retain original experiment lock and rerun identical comparisons.",
            "source_hashes": hashes, "experiment_lock_sha256": digest(OUT / "experiment_lock.json")})
    else:
        write_once(OUT / "experiment_lock.json", frozen)
        write_once(OUT / "experiment_lock_hash.json", {"sha256": digest(OUT / "experiment_lock.json")})
    print("Frozen single-candidate audit before replay", flush=True)
    universe = load_universe(spec["universe"])
    timeline, features = prepare(slice_universe(universe, FULL_START, FULL_END))
    nav_full, stats_full = simulate_candidate(timeline, features, spec)
    print("Continuous replay complete", flush=True)
    val_timeline, val_features = prepare(slice_universe(universe, VAL_START, VAL_END))
    nav_cold, stats_cold = simulate_candidate(val_timeline, val_features, spec)
    # Preserve 300 bars of causal indicators, forbid entries during those bars via the engine's fixed warmup.
    # At the validation boundary positions and cash start flat while indicators retain pre-boundary history.
    boundary = int(timeline.searchsorted(VAL_START))
    end = int(timeline.searchsorted(VAL_END, side="right"))
    start = boundary - 300
    warm_features = {symbol: {key: values[start:end].copy() for key, values in feature.items()}
                     for symbol, feature in features.items()}
    nav_warm, _ = simulate_candidate(timeline[start:end], warm_features, spec)
    nav_stress, stats_stress = simulate_candidate(timeline, features, spec, cost_rate_bps=20)
    historical = json.loads((OLD / "full_evaluation_results.json").read_text(encoding="utf-8"))
    historical = next(row for row in historical["evaluations"] if row["id"] == spec["id"])
    saved_nav = pd.read_parquet(OLD / "champion_equity_curve.parquet")["nav"]
    comparable = nav_full.index.intersection(saved_nav.index)
    max_error = float(np.max(np.abs(nav_full.loc[comparable] - saved_nav.loc[comparable])))
    probes = causal_probes()
    data_audit = {}
    for symbol, data in universe.items():
        prices = data.klines
        funding = pd.read_parquet(FUNDING_DIR / f"{symbol}_funding.parquet")
        hours = (prices.index.to_series().diff() / pd.Timedelta(hours=1)).dropna()
        data_audit[symbol] = {
            "hourly_rows": len(prices), "first": str(prices.index.min()), "last": str(prices.index.max()),
            "hour_gaps_over_1h": int((hours > 1).sum()), "duplicate_price_timestamps": int(prices.index.duplicated().sum()),
            "funding_source_rows": len(funding), "funding_columns": list(funding.columns),
        }
    checks = {
        "cold_validation_matches_lock_rounded": bool(stats_cold["calmar"] == lock["champion_candidate"]["val_calmar"]),
        "continuous_validation_matches_report_rounded": bool(round(metrics(nav_full.loc[VAL_START:VAL_END])["calmar"], 3) == historical["validation"]["calmar"]),
        "all_saved_nav_timestamps_reproduced": len(comparable) == len(saved_nav) == len(nav_full),
        "saved_nav_reproduction_max_absolute_usdt_error": max_error,
        "source_hashes_unchanged_after_replay": all(digest(path) == expected for path, expected in hashes.items()),
    }
    report = {
        "branch": "trend", "status": "historical_reproduction_complete_not_live_ready",
        "generated_at": datetime.now(timezone.utc).isoformat(), "source_hashes": hashes,
        "lock_sha256": digest(OUT / "experiment_lock.json"), "new_oos": False,
        "evidence": [
            {"finding": "Validation discrepancy is reset-state versus continuation-state, not the same experiment.",
             "old_locked_cold_start": lock["champion_candidate"]["val_calmar"],
             "reproduced_cold_validation": metrics(nav_cold),
             "old_continuation_validation": historical["validation"],
             "reproduced_continuation_validation": metrics(nav_full.loc[VAL_START:VAL_END]),
             "warm_indicators_flat_positions_validation": metrics(nav_warm.loc[VAL_START:VAL_END]),
             "cold_start_warmup_bars": 300, "warmup_days": 50},
            {"finding": "Original full-period account replay", "metrics": stats_full, "verification": checks,
             "test_2026_continuation": metrics(nav_full.loc[TEST_START:TEST_END])},
            {"finding": "Execution-cost stress without changing strategy", "one_way_bps": 20,
             "full_period": stats_stress, "test_2026_continuation": metrics(nav_stress.loc[TEST_START:TEST_END])},
            {"finding": "Causal engine probes", "results": probes},
            {"finding": "Input coverage audit", "symbols": data_audit},
        ],
        "limitations": [
            "All historical periods reused; positive reproduction is not independent alpha validation.",
            "Only the existing engine was replayed, not an independent trading simulator.",
            "Funding uses four-hour close rather than settlement mark and charges after new entries at the same timestamp; missing aligned funding defaults to zero.",
            "Stops check previous close and execute next open, so intrabar losses/gaps are not bounded by the quoted ATR stop.",
            "Trade win-rate/profit-factor excludes entry fees and funding in per-trade PnL; account NAV does include these modeled costs.",
            "Asset candles are forward-filled on BTC timeline; audit gaps before execution use. No liquidation, order-book capacity or partial-fill model.",
            "Indicator arrays are already lagged and evaluated at t-1, producing an extra indicator lag, not future-information leakage.",
            "Only four large assets; evidence cannot be transferred to low-cap short strategy.",
        ],
        "next_experiment": {
            "name": "fixed_champion_execution_audit", "locked_parameters": spec,
            "comparisons": ["original close-confirmed exits", "event-time funding with verified marks and consistent fill ordering", "one additional 4h execution delay"],
            "funding_fail_closed": True, "no_parameter_sweep": True,
            "historical_status": "exploratory until genuinely new prospective data",
            "promotion_requirements": ["independent NAV and fees reconciliation", "no missing funding coverage", "close-confirmed risk and gap losses disclosed", "frozen prospective paper test before live use"],
        },
    }
    write_once(OUT / "report.json", report)
    print(json.dumps({"checks": checks, "cold_val": metrics(nav_cold), "warm_flat_val": metrics(nav_warm.loc[VAL_START:VAL_END]),
                      "continuous_val": metrics(nav_full.loc[VAL_START:VAL_END]), "stress_test": metrics(nav_stress.loc[TEST_START:TEST_END]), "probes": probes}, indent=2))


if __name__ == "__main__":
    main()
