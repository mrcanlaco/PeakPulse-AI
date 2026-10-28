"""Re-execute PIT candidates with funding-coupled equity and scenario ledgers."""
from pathlib import Path
import hashlib
import json
import sys
from types import SimpleNamespace
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(Path(__file__).resolve().parent)]
import pandas as pd
from dao_vang.fibo_short.backtest import resample_1h_to_htf
from study_coin_universe_selection_2026 import load_symbol_1h_full_2024_2026
from universe_reaudit_v402_worker import collect_symbol_milestones_v402
from verify_red_team_audit_2026 import calc_htf_features_no_bfill
from verify_red_team_reaudit_v402 import load_historical_funding_lookup, run_portfolio_coupled_execution
from method_provenance_v406 import verify
from ledger_reconciliation import reconcile_ledger_tree
ART = ROOT / "artifacts/fibo_trend_short"


def convert(c, future):
    """Adapt audited universe candidates to the funding-aware coupled engine.

    Preserve the exact M6 stop using the algebraic inverse of its ATR formula;
    admissibility was already evaluated by the canonical universe collector.
    """
    low = c["tp1"]
    wave_range = (low - c["tp2"]) / .272
    atr = (c["sl_m6"] - max(low + .886 * wave_range, c["entry_price"] * 1.005)) / .25
    return {"symbol": c["symbol"], "tf": c["tf"], "idx_1h": c["idx_1h"], "wave_key": c["wave_key"],
            "decision_time": c["decision_time"], "full_conviction_score": c["full_conviction_score"],
            "f1_expanded": True, "imp_drop_pct": 6.0, "imp_ker": c["imp_ker"],
            "fibo_levels": SimpleNamespace(level_0000=low, wave_range=wave_range), "atr_1h": atr,
            "setup": SimpleNamespace(entry_price=c["entry_price"], stop_loss=c["sl_std"], tp1=c["tp1"], tp2=c["tp2"], tp3=c["tp3"]),
            "sig": SimpleNamespace(id=f"{c['symbol']}_{c['tf']}", signal_time=c["decision_time"],
                h1_confirmation=SimpleNamespace(confirmation_tier=c["confirmation_tier"], pattern_name=c["pattern_name"], current_fibo_ratio=c["current_fibo_ratio"]),
                wave=SimpleNamespace(impulse_drop_pct=c["wave_impulse_drop_pct"], prior_pump_pct=c["wave_prior_pump_pct"])),
            "future_slice": future}


def main():
    source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    verify()
    source = json.loads((ART / "METHOD_SOURCE_CHECKS_v4_0_6.json").read_text())
    members = {ym: {r["symbol"] for r in rows} for ym, rows in source["monthly_membership"].items()}
    symbols = sorted(set().union(*members.values()))
    funding, coverage = load_historical_funding_lookup(symbols)
    btc = load_symbol_1h_full_2024_2026("BTCUSDT")
    windows = {
        "calibration_2024_2025": ("2023-10-01T00:00:00Z", "2024-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        "reused_validation_hard_0831": ("2025-10-01T00:00:00Z", "2026-01-01T00:00:00Z", "2026-09-01T00:00:00Z"),
    }
    raw = {name: [] for name in windows}
    bhtf = {}
    for name, (context, start, end) in windows.items():
        bframe = btc.loc[(btc.index >= pd.Timestamp(context)) & (btc.index < pd.Timestamp(end))]
        bhtf[name] = {tf: calc_htf_features_no_bfill(resample_1h_to_htf(bframe, tf)) for tf in ("4h", "1d")}
    for i, symbol in enumerate(symbols, 1):
        df = load_symbol_1h_full_2024_2026(symbol)
        for name, (context, start, end) in windows.items():
            frame = df.loc[(df.index >= pd.Timestamp(context)) & (df.index < pd.Timestamp(end))]
            if len(frame) < 200: continue
            candidates = collect_symbol_milestones_v402(symbol, frame, bhtf[name], entry_start_ts=pd.Timestamp(start), entry_end_ts=pd.Timestamp(end) - pd.Timedelta(seconds=1))["raw_candidates"]
            bars = [{"open_time_str": ts.isoformat(), "open": float(row.open), "high": float(row.high), "low": float(row.low), "close": float(row.close)} for ts, row in frame.iterrows()]
            for c in candidates:
                if "m6_f4_expanded" not in c["eligible_milestones"] or symbol not in members[c["entry_ym"]]: continue
                idx = int(c["idx_1h"]) + 1
                future = bars[idx:idx + (72 if c["tf"] == "4h" else 120)]
                raw[name].append(convert(c, future))
        if i % 30 == 0 or i == len(symbols):
            print(f"PIT funding candidates {i}/{len(symbols)}", flush=True)
    results, ledgers = {}, {}
    for name, (_, start, end) in windows.items():
        results[name] = {}
        for sizing in ("fixed_1x", "conviction_150_115_080"):
            results[name][sizing] = {}
            for cost in (20, 40, 60):
                print(f"PIT funding execution {name}/{sizing}/{cost}", flush=True)
                result = run_portfolio_coupled_execution(raw[name], "m6_f4_expanded", start, end,
                    round_trip_fee_bps=cost, sizing_mode=sizing, funding_lookup=funding)
                key = f"pit_funded/{name}/{sizing}/{cost}bps"
                ledgers[key] = {"ledger_records": result.pop("ledger_records"), "decision_ledger_records": result.pop("decision_ledger_records")}
                for scenario, node in result["scenario_specific_coupled_ledgers"].items():
                    ledgers[f"{key}/{scenario}"] = {"ledger_records": node.pop("ledger_records"), "decision_ledger_records": node.pop("decision_ledger_records")}
                results[name][sizing][str(cost)] = {"ledger_key": key, "coupled": result}
    reconciliation = reconcile_ledger_tree(ledgers)
    payload = {"version": "4.0.6", "fresh_oos": False, "source_sha256": source_hash, "inputs_unchanged": verify(),
               "symbols_requested_for_funding": symbols, "funding_coverage": coverage, "results": results, "monetary_reconciliation": reconciliation}
    (ART / "METHOD_PIT_FUNDING_v4_0_6.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (ART / "METHOD_PIT_FUNDING_LEDGERS_v4_0_6.json").write_text(json.dumps({"ledgers_by_key": ledgers}, indent=2), encoding="utf-8")
    assert reconciliation["all_passed"]
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == source_hash
    print("PIT funding complete", flush=True)


if __name__ == "__main__":
    main()
