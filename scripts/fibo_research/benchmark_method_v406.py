"""Frozen M6B comparison: same gates, two sizing policies, three cost assumptions.

2026 is reused validation data, not an untouched holdout. This script does not
select thresholds or enable live trading. All monetary ledgers are exported.
"""

from pathlib import Path
import hashlib
import json
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(Path(__file__).resolve().parent)]
import pandas as pd
from dao_vang.fibo_short.backtest import load_historical_1h_frame, resample_1h_to_htf
from study_oos_2026_all_7_milestones import load_1h_for_oos
from verify_red_team_audit_2026 import calc_htf_features_no_bfill, collect_candidates_and_run_modes, run_standalone_config
from verify_red_team_reaudit_v402 import load_historical_funding_lookup, run_portfolio_coupled_execution, summarize_audit_items_v402
from ledger_reconciliation import reconcile_ledger_tree
from complete_method_v406 import verify_history
from method_provenance_v406 import verify

ART = ROOT / "artifacts/fibo_trend_short"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "LTCUSDT", "BCHUSDT", "1000PEPEUSDT", "1000BONKUSDT", "1000SHIBUSDT", "AAVEUSDT", "ADAUSDT", "1INCHUSDT", "ACEUSDT", "AKTUSDT"]


def collect(frames: dict, start: str, end: str) -> list:
    btc = {tf: calc_htf_features_no_bfill(resample_1h_to_htf(frames["BTCUSDT"], tf)) for tf in ("4h", "1d")}
    return collect_candidates_and_run_modes(
        frames, btc, entry_start_ts=pd.Timestamp(start), entry_end_ts=pd.Timestamp(end),
        strict_prior_low_before_peak=True, no_bfill=True, swing_right_bars=2,
        swing_left_bars=2, lookback_bars=30,
    )


def main() -> None:
    verify_history()
    verify()
    protocol_file = ART / "METHOD_v406_EXPERIMENT_PROTOCOL.json"
    protocol_hash = hashlib.sha256(protocol_file.read_bytes()).hexdigest()
    print("Loading 14-symbol frames and actual funding events", flush=True)
    is_frames = {s: load_historical_1h_frame(s, start_utc="2020-01-01T00:00:00Z", end_utc="2025-12-31T23:59:59Z", strict_in_sample=True) for s in SYMBOLS}
    full_frames = {s: load_1h_for_oos(s) for s in SYMBOLS}
    hard_frames = {s: f.loc[f.index < pd.Timestamp("2026-09-01T00:00:00Z")].copy() for s, f in full_frames.items()}
    funding, coverage = load_historical_funding_lookup(SYMBOLS)
    raw_is = collect(is_frames, "2020-01-01T00:00:00Z", "2025-12-31T23:59:59Z")
    raw_hard = collect(hard_frames, "2026-01-01T00:00:00Z", "2026-08-31T23:59:59Z")
    raw_full = collect(full_frames, "2026-01-01T00:00:00Z", "2026-09-29T23:59:59Z")
    data_coverage = {s: {"is_last_open_utc": is_frames[s].index.max().isoformat(), "full_validation_last_open_utc": full_frames[s].index.max().isoformat()} for s in SYMBOLS}
    windows = [
        ("is_2020_2025", raw_is, "2020-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        ("calibration_2024_2025", raw_is, "2024-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        ("reused_validation_hard_0831", raw_hard, "2026-01-01T00:00:00Z", "2026-09-01T00:00:00Z"),
        ("reused_validation_available_0929", raw_full, "2026-01-01T00:00:00Z", "2026-09-30T00:00:00Z"),
    ]
    results = {}
    ledgers = {}
    for name, source, start, end in windows:
        candidates = [c for c in source if pd.Timestamp(start) <= pd.Timestamp(c["decision_time"]) < pd.Timestamp(end)]
        results[name] = {}
        for sizing in ("fixed_1x", "conviction_150_115_080"):
            results[name][sizing] = {}
            for cost_bps in (20, 40, 60):
                print(f"Benchmark {name} / {sizing} / {cost_bps} bps", flush=True)
                independent = run_standalone_config(candidates, "m6_f4_expanded", round_trip_fee_bps=cost_bps, sizing_mode=sizing)
                coupled = run_portfolio_coupled_execution(
                    candidates, "m6_f4_expanded", start, end,
                    round_trip_fee_bps=cost_bps, sizing_mode=sizing,
                    base_notional_weight=0.20, max_concurrent_cap=5,
                    max_total_notional_frac=1.0, max_total_sl_risk_frac=0.12,
                    funding_lookup=funding,
                )
                key = f"benchmark_method/{name}/{sizing}/{cost_bps}bps"
                ledgers[key] = {
                    "ledger_records": coupled.pop("ledger_records"),
                    "decision_ledger_records": coupled.pop("decision_ledger_records"),
                }
                for scenario, value in coupled["scenario_specific_coupled_ledgers"].items():
                    ledgers[f"{key}/{scenario}"] = {
                        "ledger_records": value.pop("ledger_records"),
                        "decision_ledger_records": value.pop("decision_ledger_records"),
                    }
                results[name][sizing][str(cost_bps)] = {
                    "ledger_key": key,
                    "independent": summarize_audit_items_v402(independent),
                    "coupled": coupled,
                }
    reconciliation = reconcile_ledger_tree(ledgers)
    payload = {
        "version": "4.0.6", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": protocol_hash, "symbols": SYMBOLS,
        "entry_windows_half_open": True, "valuation_includes_final_candle_close": True,
        "window_state_reset": True, "fresh_oos": False,
        "source_coverage": data_coverage, "historical_funding_coverage": coverage,
        "results": results, "monetary_reconciliation": reconciliation,
        "historical_artifacts_unchanged": verify_history(),
        "inputs_unchanged": verify(),
    }
    (ART / "METHOD_BENCHMARK_v4_0_6.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (ART / "METHOD_BENCHMARK_LEDGERS_v4_0_6.json").write_text(json.dumps({"version": "4.0.6", "ledgers_by_key": ledgers}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not reconciliation["all_passed"]:
        raise AssertionError("Monetary reconciliation failed; inspect benchmark evidence")
    print("Benchmark complete; monetary reconciliation passed", flush=True)


if __name__ == "__main__":
    main()
