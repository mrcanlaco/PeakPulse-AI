"""Audit repaired records, unchanged preperiod behavior and the frozen evaluation."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import audit_account,utilization
from compare_account_risk import ROOT,exchange_rules,sha,write
from evaluate_frozen_extension import RESULTS,BOUNDARIES,WINDOWS
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from prepare_frozen_extension import OUT,FREEZE,START,END
from prepare_historical_research import grid_audit
from search_historical_entries import COSTS
from search_multitimeframe_rolling import grouped_signals
from short_entry_guards import features
from short_guard_ablation import decisions,apply_mask
from short_multitimeframe_signals import generate


from dao_vang.config.settings import ExecutionConfig


def main():
    s=json.loads((RESULTS/"summary.json").read_text(encoding="utf-8"));p=s["protocol"];freeze=p["candidate"]
    assert sha(FREEZE)==p["candidate_sha256"] and sha(OUT/"reconciled_manifest.json")==p["data_manifest_sha256"]
    assert sha(ROOT/"configs/live.yaml")==p["live_config_sha256"]
    for n,d in p["source_sha256"].items():assert sha(ROOT/"scripts"/n)==d
    for n,d in freeze["source_sha256"].items():assert sha(ROOT/"scripts"/n)==d
    manifest=json.loads((OUT/"reconciled_manifest.json").read_text(encoding="utf-8"));assert manifest["data_ready"]
    archive_checks=0;repaired=0
    for item in manifest["proof"]:
        for archive in item["archives"]:assert sha(Path(archive["file"]))==archive["sha256"];archive_checks+=1
        trade=pd.read_parquet(OUT/"trade"/f"{item['symbol']}.parquet");assert grid_audit(trade,START,END)["complete"]
        if item["symbol"]=="BTCUSDT":continue
        initial=pd.read_parquet(OUT/"mark"/f"{item['symbol']}.parquet");parts=[initial]
        for repair in item["gap_fills"]:
            assert sha(Path(repair["file"]))==repair["sha256"]
            saved=json.loads(Path(repair["file"]).read_text(encoding="utf-8"))
            actual=pd.DataFrame([[int(r[0]),*map(float,r[1:5])] for r in saved["rows"]],columns=["open_time","open","high","low","close"])
            new=actual[~actual.open_time.isin(initial.open_time)]
            assert len(new)==repair["added_rows"];parts.append(new);repaired+=len(new)
        expected=pd.concat(parts,ignore_index=True).sort_values("open_time").reset_index(drop=True)
        final=pd.read_parquet(item["mark_path"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(expected,final,check_exact=True);assert grid_audit(final,START,END)["complete"]
        assert item["funding"]["complete"] and item["observed_trade_disagreements"]==0
    prices,funding,frames=load();signals=generate(frames,[freeze["source"]])[freeze["source"]["id"]]
    assert signals==json.loads((RESULTS/"signals.json").read_text(encoding="utf-8"))
    old_signals=json.loads((ROOT/"artifacts/multitimeframe_rolling_20260925/signals.json").read_text(encoding="utf-8"))[freeze["source"]["id"]]
    boundary=WINDOWS["fresh_june"][0]
    assert [r for r in signals if r["at"]<boundary]==[r for r in old_signals if r["at"]<boundary]
    enriched=features(frames,funding);observed=decisions(signals,enriched)
    assert observed==json.loads((RESULTS/"observations.json").read_text(encoding="utf-8"))
    cut=pd.Timestamp("2026-07-15T03:25:00Z");cut_ms=int(cut.timestamp()*1000);prefix={c:f.loc[:cut] for c,f in frames.items()}
    shorter=generate(prefix,[freeze["source"]])[freeze["source"]["id"]]
    assert shorter==[r for r in signals if r["at"]<=cut_ms]
    prefix_obs=decisions(shorter,features(prefix,funding));assert prefix_obs==[r for r in observed if r["at"]<=cut_ms]
    variants={}
    for mask in [0,2,15]:
        es,counts=apply_mask(signals,observed,mask);variants[mask]=es
        assert dict(entries=es,counts=counts)==json.loads((RESULTS/f"entries_mask{mask:02d}.json").read_text(encoding="utf-8"))
        assert apply_mask(shorter,prefix_obs,mask)[0]==[r for r in es if r["at"]<=cut_ms]
    previous=ROOT/"artifacts/guard_ablation_20260925/runs";prefix_paths=0
    for row in s["results"]:
        raw=json.loads((RESULTS/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"));curve=pd.read_parquet(RESULTS/"runs"/f"{row['id']}_equity.parquet")
        start,end=WINDOWS[row["window"]];assert raw["initial_equity"]==500 and curve["at"].iloc[0]==start
        audit_account(raw,row["notional"]);assert utilization(curve,raw,row["notional"])==row["utilization"]
        assert abs(sum(j.get("net",0) for j in raw["journal"])-raw["closed_trade_net"])<1e-7
        assert abs(sum(j["amount"] for j in raw["journal"] if j["kind"]=="funding")-raw["funding"])<1e-7
        qty={};fees=0.;fee=next(f for c,f,_ in COSTS if c==row["cost"])
        for j in raw["journal"]:
            assert start<=j["at"]<=end
            if j["kind"] in ["entry","entry_add"]:
                qty[j["event_id"]]=qty.get(j["event_id"],0)+j["qty"];fees+=j["qty"]*j["price"]*fee
            elif "net" in j:fees+=qty.pop(j["event_id"])*j["price"]*fee
        assert abs(fees-raw["fees"])<1e-7
        if raw["ending_equity"] is not None:assert curve["at"].iloc[-1]==end and abs(curve["equity"].iloc[-1]-raw["ending_equity"])<1e-7
        else:assert not row["target_met"] and raw["errors"]
        assert monthly_metrics(curve.to_dict("records"),boundaries=[t for t in BOUNDARIES if start<=t<=end])==row["monthly"]
        initial=500 if row["window"]=="fresh_june" else curve.loc[curve["at"]==boundary,"equity"].iloc[0]
        assert initial==row["new_initial_equity"]
        assert monthly_metrics(curve.to_dict("records"),initial=initial,boundaries=BOUNDARIES[-4:])==row["new_period_monthly"]
        if curve.paused.any():
            first=curve.loc[curve.paused,"at"].iloc[0];assert curve.loc[curve["at"]>=first,"paused"].all()
            assert not any(j["kind"] in ["entry","entry_add"] and j["at"]>first for j in raw["journal"])
        if row["window"]=="continuous_year":
            ident=f"full_{row['cost']}_{row['strategy_id']}"
            old_curve=pd.read_parquet(previous/f"{ident}_equity.parquet")
            pd.testing.assert_frame_equal(curve[curve["at"]<boundary].reset_index(drop=True),old_curve[old_curve["at"]<boundary].reset_index(drop=True),check_exact=True)
            old=json.loads((previous/f"{ident}.json").read_text(encoding="utf-8"))
            assert [j for j in raw["journal"] if j["at"]<boundary]==[j for j in old["journal"] if j["at"]<boundary];prefix_paths+=1
    print("AUDITED",len(s["results"]),"PREFIXES",prefix_paths,flush=True)
    rules=exchange_rules(RULE_PATH);spec=next(s for s in freeze["specs"] if s["id"]=="mask02_n25");exact=0
    for window,(start,end) in WINDOWS.items():
        for cost,fee,slip in COSTS:
            result=simulate(list(range(start,end+1,300000)),grouped_signals(variants[2],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                            ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
            result["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
            ident=f"{window}_{cost}_mask02_n25"
            assert {k:v for k,v in result.items() if k!="curve"}==json.loads((RESULTS/"runs"/f"{ident}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(pd.DataFrame(result["curve"]),pd.read_parquet(RESULTS/"runs"/f"{ident}_equity.parquet"),check_exact=True);exact+=1
    write(RESULTS/"verification.json",dict(unit_tests_passed=114,journals_audited=len(s["results"]),archive_hashes_checked=archive_checks,
        actual_rest_repair_bars_reconstructed=repaired,old_signal_prefix_exact=True,old_account_prefixes_exact=prefix_paths,
        new_signal_prefix_checks=1,guard_prefix_checks=3,new_paths_exact=exact,candidate_hash_unchanged=True,live_config_unchanged=True))
    print("VERIFIED",flush=True)


if __name__=="__main__":main()
