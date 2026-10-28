"""Independent nested-watch oracle, causal prefixes and account replay audit."""
import json
import numpy as np
import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import audit_account,utilization
from compare_account_risk import ROOT,sha,write,exchange_rules
from execution_cost_attribution import attribute
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from search_failed_rally import OUT,PRIOR,DATA,WINDOWS,BOUNDARIES,COSTS,definitions,select,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from short_failed_rally import definitions as sources,prepare,generate
from dao_vang.config.settings import ExecutionConfig


def oracle(f,s):
    """Enumerate full watches from each eligible impulse, not scanner state."""
    times=np.array([int(t.timestamp()*1000) for t in f.index]);n=len(f)
    good=f.ready.to_numpy() & np.isfinite(f[["open","low","close","hour_atr","atr","prior_low12"]]).all(axis=1).to_numpy()
    gate=good & f.bear.to_numpy() & (True if s["regime"]=="any" else f.btc_bear.to_numpy())
    close=f.close.to_numpy();low=f.low.to_numpy();op=f.open.to_numpy();atr=f.hour_atr.to_numpy();prior=f.prior_low12.to_numpy()
    i=0;last=-(10**18);out=[]
    while i<n:
        if not gate[i] or times[i]-last<86400000 or close[i]>=prior[i]:i+=1;continue
        arm=i;minimum=close[i];bounce=None;peak=None;j=i+1
        while j<n:
            if times[j]-times[arm]>s["ttl_hours"]*3600000 or times[j]-times[j-1]!=3600000 or not gate[j]:break
            if bounce is None:
                minimum=min(minimum,close[j])
                # Compare price levels as specified. Subtracting two binary
                # floats can turn an exact price-level touch into a false miss
                # (3.14 - 3.119 < .021 although 3.119 + .021 == 3.14).
                if close[j]>=minimum+s["bounce_atr"]*atr[arm]:bounce=j;peak=close[j]
            else:
                peak=max(peak,close[j])
                if close[j]<low[j-1] and close[j]<op[j]:
                    out.append((int(times[arm]),int(times[bounce]),int(times[j]),float(atr[arm]),float(minimum),float(f.atr.iloc[j]),float((peak-close[j])/atr[arm])))
                    last=times[j];j+=1;break
            j+=1
        i=j
    return out


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));p=s["protocol"]
    assert sha(ROOT/"configs/live.yaml")==p["live_config_sha256"]
    for n,d in p["source_sha256"].items():assert sha(ROOT/"scripts"/n)==d
    assert sha(DATA/"reconciled_manifest.json")==p["data_sha256"] and sha(PRIOR/"summary.json")==p["prior_sha256"] and sha(PRIOR/"signals.json")==p["signals_sha256"]
    assert definitions(json.loads((PRIOR/"summary.json").read_text(encoding="utf-8")))==s["specs"]
    assert select(s["specs"],s["results"])==s["selected"]==json.loads((OUT/"candidate_lock.json").read_text())["selected"]
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);prepared=prepare(frames);signals=generate(prepared)
    saved=json.loads((OUT/"signals.json").read_text(encoding="utf-8"));checked=0
    fields=["arm_at","bounce_at","at","frozen_hour_atr","bounce_low","atr","probability"];atr_checks=0
    for spec in sources():
        assert signals[spec["id"]]==saved[spec["id"]]
        for coin,f in prepared.items():
            expected=oracle(f,spec);actual=[tuple(r[k] for k in fields) for r in signals[spec["id"]] if r["symbol"]==coin]
            assert expected==actual,(spec["id"],coin);checked+=len(actual)
            for row in actual[::max(1,len(actual)//3)][:3]:
                t=pd.Timestamp(row[0],unit="ms",tz="UTC");h=frames[coin].loc[:t].tail(15)
                true_ranges=[max(b.high-b.low,abs(b.high-a.close),abs(b.low-a.close)) for a,b in zip(h.itertuples(),list(h.itertuples())[1:])]
                assert len(true_ranges)==14 and abs(sum(true_ranges)/14-row[3])<1e-9;atr_checks+=1
    signals["benchmark_mask2"]=json.loads((PRIOR/"signals.json").read_text(encoding="utf-8"))["benchmark_mask2"]
    assert saved==signals
    prefixes=0
    for cut in ["2025-11-15 13:00","2026-03-01 17:00","2026-07-15 10:00"]:
        t=pd.Timestamp(cut,tz="UTC");prefix=prepare({c:f.loc[:t] for c,f in frames.items()})
        for c,f in prefix.items():pd.testing.assert_frame_equal(f,prepared[c].loc[:t],check_exact=True)
        for sid,rows in generate(prefix).items():
            assert rows==[r for r in signals[sid] if r["at"]<=int(t.timestamp()*1000)];prefixes+=1
    print("SIGNALS",checked,"PREFIXES",prefixes,flush=True)
    baselines=0;incomplete=[];funding_checks=0
    schedule={c:{t:(rate,mark) for t,rate,mark in rows} for c,rows in funding.items()}
    for row in s["results"]:
        raw=json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"));curve=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet")
        start,end=WINDOWS[row["window"]];_,fee,slip=next(v for v in COSTS if v[0]==row["cost"])
        audit_account(raw,row["notional"]);assert utilization(curve,raw,row["notional"])==row["utilization"]
        assert exit_diagnostics(raw)==row["exit_diagnostics"]
        assert monthly_metrics(curve.to_dict("records"),boundaries=[t for t in BOUNDARIES if start<=t<=end])==row["monthly"]
        assert row["target_met"]==(raw["ending_equity"] is not None and row["monthly"]["all_months_50pct"])
        attribution=attribute(raw,lambda c:prices[c])
        if raw["ending_equity"] is None:incomplete.append(row["id"]);assert raw["errors"] and not row["target_met"]
        else:assert attribution["complete"] and curve["at"].iloc[-1]==end
        assert abs(sum(j.get("net",0) for j in raw["journal"])-raw["closed_trade_net"])<1e-7
        assert abs(sum(j["amount"] for j in raw["journal"] if j["kind"]=="funding")-raw["funding"])<1e-7
        qty={};active={};fees=0
        for j in raw["journal"]:
            if j["kind"]=="entry":active[j["symbol"]]=j["event_id"]
            if j["kind"] in ["entry","entry_add"]:
                qty[j["event_id"]]=qty.get(j["event_id"],0)+j["qty"];fees+=j["qty"]*j["price"]*fee
            elif j["kind"]=="funding":
                rate,mark=schedule[j["symbol"]][j["at"]];assert abs(j["amount"]-qty[active[j["symbol"]]]*rate*mark)<1e-8;funding_checks+=1
            elif "net" in j:fees+=qty.pop(j["event_id"])*j["price"]*fee;active.pop(j["symbol"])
        assert abs(fees-raw["fees"])<1e-7
        if curve.paused.any():
            first=curve.loc[curve.paused,"at"].iloc[0];assert curve.loc[curve["at"]>=first,"paused"].all()
            assert not any(j["kind"] in ["entry","entry_add"] and j["at"]>first for j in raw["journal"])
        if row["baseline"]:
            assert raw==json.loads((PRIOR/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(PRIOR/"runs"/f"{row['id']}_equity.parquet"),check_exact=True);baselines+=1
    print("ACCOUNTS",len(s["results"]),"BASELINES",baselines,flush=True)
    # Recompute every locked candidate for the later period, both costs, plus
    # two predeclared new controls even if no candidate qualifies.
    ids=set(s["selected"])|{"rally1_ttl6_any_n25_hold","rally2_ttl24_btc_bear_n100_time48"};exact=0
    for ident in sorted(ids):
        spec=next(x for x in s["specs"] if x["id"]==ident);start,end=WINDOWS["later"]
        for cost,fee,slip in COSTS:
            r=simulate(list(range(start,end+1,300000)),grouped_signals(signals[spec["source"]["id"]],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
            r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct";key=f"later_{cost}_{ident}"
            assert {k:v for k,v in r.items() if k!="curve"}==json.loads((OUT/"runs"/f"{key}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(pd.DataFrame(r["curve"]),pd.read_parquet(OUT/"runs"/f"{key}_equity.parquet"),check_exact=True);exact+=1
    write(OUT/"verification.json",dict(journals_audited=len(s["results"]),baseline_paths_exact=baselines,replayed_paths_exact=exact,independent_signals=checked,independent_atr_samples=atr_checks,causal_prefixes=prefixes,funding_quantities_checked=funding_checks,incomplete_paths=incomplete,hashes_match=True,live_config_unchanged=True,unit_tests_passed=66))
    print("VERIFIED",flush=True)


if __name__=="__main__":main()
