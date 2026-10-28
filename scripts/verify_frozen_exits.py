"""Verify exit-grid accounting, locked selection and unchanged baseline paths."""

import json

import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import audit_account,utilization
from compare_account_risk import ROOT,exchange_rules,sha,write
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from prepare_frozen_extension import FREEZE
from search_frozen_exits import OUT,PRIOR,DATA,BOUNDARIES,WINDOWS,COSTS,definitions,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from short_entry_guards import features
from short_guard_ablation import decisions,apply_mask
from short_multitimeframe_signals import generate

from dao_vang.config.settings import ExecutionConfig


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));p=s["protocol"]
    assert sha(ROOT/"configs/live.yaml")==p["live_config_sha256"]
    assert sha(FREEZE)==p["candidate_sha256"] and sha(DATA/"reconciled_manifest.json")==p["data_sha256"]
    assert sha(PRIOR/"signals.json")==p["signals_sha256"]
    for n,d in p["source_sha256"].items():assert sha(ROOT/"scripts"/n)==d
    freeze=json.loads(FREEZE.read_text(encoding="utf-8"));assert definitions(freeze)==s["specs"]
    prices,funding,frames=load();source=generate(frames,[freeze["source"]])[freeze["source"]["id"]]
    assert source==json.loads((PRIOR/"signals.json").read_text(encoding="utf-8"))
    observations=decisions(source,features(frames,funding));variants={}
    for mask in [0,2]:
        es,counts=apply_mask(source,observations,mask)
        assert dict(entries=es,counts=counts)==json.loads((PRIOR/f"entries_mask{mask:02d}.json").read_text(encoding="utf-8"));variants[mask]=es
    baselines=0;prefixes=0;incomplete=[]
    for row in s["results"]:
        raw=json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"));curve=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet")
        start,end=WINDOWS[row["window"]]
        assert raw["initial_equity"]==500 and curve["at"].iloc[0]==start
        audit_account(raw,row["notional"]);assert utilization(curve,raw,row["notional"])==row["utilization"]
        assert exit_diagnostics(raw)==row["exit_diagnostics"]
        assert abs(sum(j.get("net",0) for j in raw["journal"])-raw["closed_trade_net"])<1e-7
        assert abs(sum(j["amount"] for j in raw["journal"] if j["kind"]=="funding")-raw["funding"])<1e-7
        qty={};fees=0.;fee=next(f for c,f,_ in COSTS if c==row["cost"])
        for j in raw["journal"]:
            assert start<=j["at"]<=end
            if j["kind"] in ["entry","entry_add"]:
                qty[j["event_id"]]=qty.get(j["event_id"],0)+j["qty"];fees+=j["qty"]*j["price"]*fee
            elif "net" in j:fees+=qty.pop(j["event_id"])*j["price"]*fee
        assert abs(fees-raw["fees"])<1e-7
        assert monthly_metrics(curve.to_dict("records"),boundaries=[t for t in BOUNDARIES if start<=t<=end])==row["monthly"]
        if raw["ending_equity"] is not None:assert curve["at"].iloc[-1]==end and abs(curve["equity"].iloc[-1]-raw["ending_equity"])<1e-7
        else:
            assert not row["target_met"] and not row["monthly"]["complete"] and raw["errors"]
            incomplete.append(dict(id=row["id"],errors=raw["errors"],stop_event=raw["stop_event"]))
        if curve.paused.any():
            first=curve.loc[curve.paused,"at"].iloc[0];assert curve.loc[curve["at"]>=first,"paused"].all()
            assert not any(j["kind"] in ["entry","entry_add"] and j["at"]>first for j in raw["journal"])
        if row["baseline"]:
            if row["window"]=="development":
                directory=ROOT/"artifacts/guard_ablation_20260925/runs";ident=f"full_{row['cost']}_mask{row['mask']:02d}_n{row['notional']}"
                old=json.loads((directory/f"{ident}.json").read_text(encoding="utf-8"));oldcurve=pd.read_parquet(directory/f"{ident}_equity.parquet")
                pd.testing.assert_frame_equal(curve[curve["at"]<end].reset_index(drop=True),oldcurve[oldcurve["at"]<end].reset_index(drop=True),check_exact=True)
                assert [j for j in raw["journal"] if j["at"]<end]==[j for j in old["journal"] if j["at"]<end];prefixes+=1
            else:
                oldwindow="continuous_year" if row["window"]=="year" else "fresh_june"
                ident=f"{oldwindow}_{row['cost']}_mask{row['mask']:02d}_n{row['notional']}"
                assert raw==json.loads((PRIOR/"runs"/f"{ident}.json").read_text(encoding="utf-8"))
                pd.testing.assert_frame_equal(curve,pd.read_parquet(PRIOR/"runs"/f"{ident}_equity.parquet"),check_exact=True);baselines+=1
    selected=[]
    for mask in [0,2]:
        for n in [25,100]:
            pool=[]
            for spec in s["specs"]:
                if spec["mask"]!=mask or spec["notional"]!=n:continue
                rs=[r for r in s["results"] if r["strategy_id"]==spec["id"] and r["window"]=="development"]
                if len(rs)==2 and all(r["ending_equity"] is not None and r["monthly"]["complete"] for r in rs):
                    pool.append((min(r["monthly"]["min_monthly_return"] for r in rs),min(r["ending_equity"] for r in rs),spec["id"]))
            if pool:selected.append(max(pool)[2])
    assert selected==s["selected"]==json.loads((OUT/"candidate_lock.json").read_text(encoding="utf-8"))["selected"]
    print("AUDITED",len(s["results"]),"BASELINES",baselines,"PREFIXES",prefixes,flush=True)
    rules=exchange_rules(RULE_PATH);specs={r["id"]:r for r in s["specs"]};exact=0
    for ident in selected:
        spec=specs[ident];start,end=WINDOWS["year"]
        for cost,fee,slip in COSTS:
            result=simulate(list(range(start,end+1,300000)),grouped_signals(variants[spec["mask"]],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                            ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
            result["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
            key=f"year_{cost}_{ident}"
            assert {k:v for k,v in result.items() if k!="curve"}==json.loads((OUT/"runs"/f"{key}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(pd.DataFrame(result["curve"]),pd.read_parquet(OUT/"runs"/f"{key}_equity.parquet"),check_exact=True);exact+=1
    write(OUT/"verification.json",dict(journals_audited=len(s["results"]),unchanged_signals_verified=True,prior_baseline_paths_exact=baselines,
        prior_baseline_prefixes_exact=prefixes,new_selected_paths_exact=exact,locked_selection_reproduced=True,
        incomplete_paths=incomplete,source_hashes_match=True,data_hashes_match=True,live_config_unchanged=True))
    print("VERIFIED",flush=True)


if __name__=="__main__":main()
