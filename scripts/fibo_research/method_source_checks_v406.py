"""Independent cross-engine, future perturbation and PIT membership checks."""
from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(Path(__file__).resolve().parent)]
import numpy as np
import pandas as pd
from dao_vang.fibo_short.backtest import DATA_LAKE_5M_DIR, resample_1h_to_htf
from study_coin_universe_selection_2026 import load_symbol_1h_full_2024_2026, STABLE_OR_INDEX_EXCLUDE, G1_STORE_OF_VALUE
from verify_red_team_audit_2026 import collect_candidates_and_run_modes, calc_htf_features_no_bfill, passes_milestone_gate
from universe_reaudit_v402_worker import collect_symbol_milestones_v402

ART = ROOT / "artifacts/fibo_trend_short"


def candidate_map(candidates, universe=False, before=None):
    result = {}
    for c in candidates:
        if before is not None and pd.Timestamp(c["decision_time"]) >= before:
            continue
        eligible = "m6_f4_expanded" in c["eligible_milestones"] if universe else passes_milestone_gate(c, "m6_f4_expanded")
        if not eligible:
            continue
        key = (c["symbol"], c["tf"], c["decision_time"], c["wave_key"])
        result[key] = (round(float(c["full_conviction_score"]), 6), round(float(c["entry_price"] if universe else c["setup"].entry_price), 8),
                       float(c["mult_m6"] if universe else c["recommended_risk_mult"]))
    return result


def main():
    btc = load_symbol_1h_full_2024_2026("BTCUSDT")
    btc = btc.loc[btc.index < pd.Timestamp("2026-01-01T00:00:00Z")]
    bhtf = {tf: calc_htf_features_no_bfill(resample_1h_to_htf(btc, tf)) for tf in ("4h", "1d")}
    checks = {}
    for symbol in ("ACEUSDT", "AAVEUSDT"):
        print(f"Cross-engine and causal checks: {symbol}", flush=True)
        df = load_symbol_1h_full_2024_2026(symbol)
        df = df.loc[df.index < pd.Timestamp("2026-01-01T00:00:00Z")]
        opts = dict(entry_start_ts=pd.Timestamp("2024-01-01T00:00:00Z"), entry_end_ts=pd.Timestamp("2025-12-31T23:59:59Z"))
        def collect(frame):
            return collect_candidates_and_run_modes({symbol: frame}, bhtf, **opts,
                strict_prior_low_before_peak=True, no_bfill=True, swing_right_bars=2, swing_left_bars=2)
        benchmark = candidate_map(collect(df))
        universe = candidate_map(collect_symbol_milestones_v402(symbol, df, bhtf, **opts)["raw_candidates"], True)
        cutoff = pd.Timestamp("2025-06-01T00:00:00Z")
        perturbed = df.copy()
        perturbed.loc[perturbed.index >= cutoff, ["open", "high", "low", "close"]] *= 7
        before = {k: v for k, v in benchmark.items() if pd.Timestamp(k[2]) < cutoff}
        changed_future = candidate_map(collect(perturbed), before=cutoff)
        checks[symbol] = {"benchmark_candidates": len(benchmark), "universe_candidates": len(universe),
                          "same_candidate_keys_and_features": benchmark == universe,
                          "future_perturbation_prefix_unchanged": before == changed_future,
                          "prefix_candidates_checked": len(before),
                          "benchmark_only": [list(k) for k in benchmark.keys() - universe.keys()],
                          "universe_only": [list(k) for k in universe.keys() - benchmark.keys()]}
    months = pd.date_range("2024-01-01", "2026-09-01", freq="MS", tz="UTC")
    eligible = {t.strftime("%Y-%m"): [] for t in months}
    symbols = sorted(p.stem for p in DATA_LAKE_5M_DIR.glob("*.parquet")
                     if p.stem.endswith("USDT") and p.stem not in STABLE_OR_INDEX_EXCLUDE)
    evaluated = 0
    for symbol in symbols:
        df = load_symbol_1h_full_2024_2026(symbol)
        if len(df) < 200:
            continue
        evaluated += 1
        if symbol in G1_STORE_OF_VALUE:
            continue
        daily = df["quote_volume"].resample("1D").sum()
        h4 = resample_1h_to_htf(df, "4h")
        wick = (h4["high"] - h4[["open", "close"]].max(axis=1)) / h4["close"].clip(lower=1e-9) * 100
        close = pd.to_datetime(h4["close_time"])
        for month in months:
            start = month - pd.Timedelta(days=63)
            active = daily.loc[(daily.index >= start) & (daily.index < month)]
            active = active[active > 0]
            wicks = wick.loc[(h4.index >= start) & (close <= month)]
            p90 = float(np.percentile(wicks, 90)) if len(wicks) >= 10 else 5.0
            if len(active) >= 50 and p90 <= 3.2 and float(active.median()) > 0:
                eligible[month.strftime("%Y-%m")].append({"symbol": symbol, "median_qvol": float(active.median()),
                                                        "active_days": len(active), "wick_p90_pct": p90})
        if evaluated % 60 == 0:
            print(f"Independent monthly membership: {evaluated} symbols", flush=True)
    selected = {m: sorted(rows, key=lambda r: (-r["median_qvol"], r["symbol"]))[:50] for m, rows in eligible.items()}
    result = {"version": "4.0.6", "cross_engine_and_causality": checks,
              "symbols_evaluated_for_pit": evaluated, "monthly_membership": selected,
              "all_passed": all(c["same_candidate_keys_and_features"] and c["future_perturbation_prefix_unchanged"]
                                and c["prefix_candidates_checked"] > 0 for c in checks.values())}
    (ART / "METHOD_SOURCE_CHECKS_v4_0_6.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if not result["all_passed"]:
        raise AssertionError("Source checks failed; inspect saved evidence")
    print("Source checks passed", flush=True)


if __name__ == "__main__":
    main()
