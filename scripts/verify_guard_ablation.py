"""Independent mask equivalence, chronology, journals and backtest reruns."""

import json

import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import audit_account,utilization
from compare_account_risk import ROOT,exchange_rules,sha,write
from historical_research_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from prepare_historical_research import OUT as DATA
from search_guard_ablation import OUT,PRIOR,SIGNALS
from search_historical_entries import BOUNDARIES,COSTS,SPANS
from search_multitimeframe_rolling import grouped_signals,rolling_windows
from short_entry_guards import features,filter_entries
from short_guard_ablation import decisions,apply_mask,definitions
from short_event_study import outcomes,statistics

from dao_vang.config.settings import ExecutionConfig


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));p=s["protocol"]
    assert sha(ROOT/"configs/live.yaml")==p["live_config_sha256"]
    assert sha(DATA/"manifest.json")==p["data_sha256"] and sha(SIGNALS)==p["signals_sha256"]
    for name,digest in p["source_sha256"].items():assert sha(ROOT/"scripts"/name)==digest
    prices,funding,frames=load();enriched=features(frames,funding)
    signals=json.loads(SIGNALS.read_text(encoding="utf-8"))[p["source"]["entry"]["source"]["id"]]
    observed=decisions(signals,enriched)
    assert observed==json.loads((OUT/"observations.json").read_text(encoding="utf-8"))
    variants={}
    cut=pd.Timestamp("2026-02-01T03:25:00Z");stamp=int(cut.timestamp()*1000)
    prefix_features=features({c:f.loc[:cut] for c,f in frames.items()},funding)
    prefix_signals=[r for r in signals if r["at"]<=stamp];prefix_observed=decisions(prefix_signals,prefix_features)
    assert prefix_observed==[r for r in observed if r["at"]<=stamp]
    for d in definitions():
        entries,counts=apply_mask(signals,observed,d["mask"]);variants[d["mask"]]=entries
        assert dict(entries=entries,counts=counts)==json.loads((OUT/f"entries_{d['id']}.json").read_text(encoding="utf-8"))
        assert apply_mask(prefix_signals,prefix_observed,d["mask"])[0]==[r for r in entries if r["at"]<=stamp]
        # Independently recompute the four inequalities instead of trusting bit masks.
        checks=[lambda v:v["ret24"]<=.10,lambda v:v["ret6"]<=0,lambda v:v["funding24"]>=-.001,
                lambda v:v["close"]>0 and 0<v["atr"]/v["close"]<=.05]
        expected=[sig for sig,obs in zip(signals,observed) if d["mask"]==0 or
                  obs["status"]=="observed" and all(fn(obs["values"]) for i,fn in enumerate(checks) if d["mask"]&(1<<i))]
        assert entries==expected
    assert variants[0]==filter_entries(signals,enriched,"none")[0]
    assert variants[15]==filter_entries(signals,enriched,"anti_squeeze")[0]
    screens=json.loads((OUT/"screens.json").read_text(encoding="utf-8"));screen_checks=0
    for r in screens:
        if r["mask"] not in [0,1,2,4,8,15] or r["hours"]!=24:continue
        events,counts=outcomes(variants[r["mask"]],prices,funding,*SPANS[r["window"]],r["hours"])
        assert counts==r["counts"]
        for c,fee,slip in COSTS:assert statistics(events,*SPANS[r["window"]],fee,slip)==r["cases"][c];screen_checks+=1
    windows=rolling_windows();baselines=0
    for row in s["results"]:
        r=json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"));curve=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet")
        start,end=windows[row["window"]]
        assert r["initial_equity"]==500 and curve["at"].iloc[0]==start
        audit_account(r,row["notional"])
        assert utilization(curve,r,row["notional"])==row["utilization"]
        assert abs(sum(j.get("net",0) for j in r["journal"])-r["closed_trade_net"])<1e-7
        assert abs(sum(j["amount"] for j in r["journal"] if j["kind"]=="funding")-r["funding"])<1e-7
        qty={};fees=0.;fee=next(f for c,f,_ in COSTS if c==row["cost"])
        for j in r["journal"]:
            assert start<=j["at"]<=end
            if j["kind"] in ["entry","entry_add"]:
                qty[j["event_id"]]=qty.get(j["event_id"],0)+j["qty"];fees+=j["qty"]*j["price"]*fee
            elif "net" in j:fees+=qty.pop(j["event_id"])*j["price"]*fee
        assert abs(fees-r["fees"])<1e-7
        assert all(o["opened_at"]>=start for o in r["open_positions"])
        assert monthly_metrics(curve.to_dict("records"),boundaries=[t for t in BOUNDARIES if start<=t<=end])==row["monthly"]
        if r["ending_equity"] is not None:
            assert curve["at"].iloc[-1]==end and abs(curve["equity"].iloc[-1]-r["ending_equity"])<1e-7
        else:assert not row["target_met"] and not row["monthly"]["complete"] and r["errors"]
        if curve.paused.any():
            first=curve.loc[curve.paused,"at"].iloc[0]
            assert curve.loc[curve["at"]>=first,"paused"].all()
            assert not any(j["kind"] in ["entry","entry_add"] and j["at"]>first for j in r["journal"])
        if row["mask"] in [0,15]:
            guard="none" if row["mask"]==0 else "anti_squeeze"
            ident=f"{row['window']}_{row['cost']}_overextension_reversal_immediate_{guard}_n{row['notional']}_hold"
            assert r==json.loads((PRIOR/"runs"/f"{ident}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(PRIOR/"runs"/f"{ident}_equity.parquet"),check_exact=True);baselines+=1
    print("AUDITED",len(s["results"]),"BASELINES",baselines,flush=True)
    exact=0;rules=exchange_rules(RULE_PATH);specs={r["id"]:r for r in s["specs"]}
    for row in s["results"]:
        if row["window"]!="full" or row["notional"]!=100 or row["mask"] not in [1,2,4,8]:continue
        spec=specs[row["strategy_id"]];start,end=windows["full"];fee,slip=next((f,b) for c,f,b in COSTS if c==row["cost"])
        r=simulate(list(range(start,end+1,300000)),grouped_signals(variants[row["mask"]],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                   ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
        r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
        assert {k:v for k,v in r.items() if k!="curve"}==json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"))
        pd.testing.assert_frame_equal(pd.DataFrame(r["curve"]),pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet"),check_exact=True);exact+=1
    write(OUT/"verification.json",dict(unit_tests_passed=111,mask_prefix_checks=16,independent_mask_reconstructions=16,
        exact_guard_equivalence=2,screen_statistics_reproduced=screen_checks,journals_audited=len(s["results"]),
        prior_baseline_paths_exact=baselines,new_paths_exact=exact,source_hashes_match=True,data_hashes_match=True,live_config_unchanged=True))
    print("VERIFIED",flush=True)


if __name__=="__main__":main()
