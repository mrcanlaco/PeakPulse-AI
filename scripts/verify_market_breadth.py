"""Independent beta/rank checks, time prefixes and full account accounting."""

import json
import numpy as np
import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import audit_account,utilization
from compare_account_risk import ROOT,sha,write,exchange_rules
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from search_market_breadth import OUT,PRIOR,DATA,WINDOWS,BOUNDARIES,COSTS,definitions,select,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from short_market_breadth import definitions as source_specs,enrich,market_state,generate
from short_event_study import outcomes,statistics
from dao_vang.config.settings import ExecutionConfig


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));p=s["protocol"]
    assert sha(ROOT/"configs/live.yaml")==p["live_config_sha256"]
    assert sha(PRIOR/"summary.json")==p["prior_sha256"] and sha(DATA/"reconciled_manifest.json")==p["data_sha256"]
    for n,d in p["source_sha256"].items():assert sha(ROOT/"scripts"/n)==d
    assert definitions(json.loads((PRIOR/"summary.json").read_text(encoding="utf-8")))==s["specs"]
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);enriched=enrich(frames);state,ranks=market_state(enriched)
    signals=generate(enriched,state,ranks);saved=json.loads((OUT/"signals.json").read_text(encoding="utf-8"))
    for sid,rows in signals.items():assert rows==saved[sid]
    for m in [0,2]:
        path=DATA/"evaluation"/f"entries_mask{m:02d}.json";assert sha(path)==p["benchmark_hashes"][str(m)]
        signals[f"benchmark_mask{m}"]=json.loads(path.read_text(encoding="utf-8"))["entries"];assert signals[f"benchmark_mask{m}"]==saved[f"benchmark_mask{m}"]
    # Parquet preserves timestamps but not the optional pandas frequency hint.
    pd.testing.assert_frame_equal(state,pd.read_parquet(OUT/"market.parquet"),check_exact=True,check_freq=False)
    beta_checks=0;bt=frames["BTCUSDT"];br=np.log(bt.close/bt.close.shift())
    for coin,f in enriched.items():
        stored=pd.read_parquet(OUT/"features"/f"{coin}.parquet");normalized=f.copy()
        # Arrow normalizes object columns containing only booleans to bool.
        # Assert that exact case before comparing every stored value exactly.
        for column in f:
            if f[column].dtype==object and stored[column].dtype==bool:
                assert f[column].map(lambda x:isinstance(x,(bool,np.bool_))).all()
                normalized[column]=f[column].astype(bool)
        pd.testing.assert_frame_equal(normalized,stored,check_exact=True,check_freq=False)
        available=f.index[f.eligible]
        for i in np.unique(np.linspace(0,len(available)-1,8,dtype=int)):
            t=available[i];end=t-pd.Timedelta(hours=24);h=frames[coin]
            r=np.log(h.close/h.close.shift());x=br.loc[:end].tail(168);y=r.reindex(x.index)
            assert len(x)==168 and np.isfinite(x).all() and np.isfinite(y).all()
            beta=np.cov(y,x,ddof=1)[0,1]/np.var(x,ddof=1)
            raw=np.log(h.at[end,"close"]/h.at[end-pd.Timedelta(hours=168),"close"])
            btc=np.log(bt.at[end,"close"]/bt.at[end-pd.Timedelta(hours=168),"close"])
            assert abs(beta-f.at[t,"beta"])<1e-8 and abs(raw-f.at[t,"raw7d"])<1e-10
            assert abs(raw-beta*btc-f.at[t,"beta7d"])<1e-8;beta_checks+=1
    rank_checks=0
    for spec in source_specs():
        last={}
        for row in signals[spec["id"]]:
            t=pd.Timestamp(row["at"],unit="ms",tz="UTC");f=enriched[row["symbol"]].loc[t]
            eligible=[h.loc[t] for h in enriched.values() if t in h.index and h.at[t,"eligible"]]
            assert len(eligible)>=24 and f.eligible
            values=np.array([v[spec["ranking"]] for v in eligible]);value=f[spec["ranking"]]
            pct=(sum(values<value)+(sum(values==value)+1)/2)/len(values)
            breadth=sum(v.close<v.ema60 for v in eligible)/len(eligible)
            assert pct<=.2 and value<0 and f.ema20<f.ema60 and f.close<f.ema20 and f.ret24<0
            assert row["probability"]==-value and row["atr"]==f.atr
            if spec["regime"]=="breadth60":assert breadth>=.60
            if spec["regime"]=="breadth75_btc":assert breadth>=.75 and f.btc_bear
            if spec["entry"]=="pullback":assert f.high>=f.ema20 and f.close<f.open
            assert row["at"]-last.get(row["symbol"],-(10**18))>=24*3600000
            last[row["symbol"]]=row["at"];rank_checks+=1
    prefixes=0
    for boundary in [BOUNDARIES[3],BOUNDARIES[6],BOUNDARIES[9]]:
        cut=pd.Timestamp(boundary,unit="ms",tz="UTC");small=enrich({c:h[h.index<=cut] for c,h in frames.items()})
        st,rk=market_state(small)
        pd.testing.assert_frame_equal(state.loc[:cut],st.loc[:cut],check_exact=True)
        for coin,f in small.items():pd.testing.assert_frame_equal(enriched[coin].loc[:cut],f.loc[:cut],check_exact=True)
        generated=generate(small,st,rk)
        for sid,rows in generated.items():assert rows==[r for r in signals[sid] if r["at"]<=boundary];prefixes+=1
    print("FACTORS",beta_checks,"SIGNALS",rank_checks,"PREFIXES",prefixes,flush=True)
    screens=json.loads((OUT/"screens.json").read_text(encoding="utf-8"))
    for row in screens:
        es,counts=outcomes(signals[row["source_id"]],prices,funding,*WINDOWS[row["window"]],row["hours"])
        assert counts==row["counts"]
        assert {c:statistics(es,*WINDOWS[row["window"]],fee,slip) for c,fee,slip in COSTS}==row["cases"]
    baseline_count=0;incomplete=[]
    for row in s["results"]:
        raw=json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"));curve=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet")
        start,end=WINDOWS[row["window"]];assert raw["initial_equity"]==500 and curve["at"].iloc[0]==start
        audit_account(raw,row["notional"]);assert utilization(curve,raw,row["notional"])==row["utilization"]
        assert exit_diagnostics(raw)==row["exit_diagnostics"]
        assert monthly_metrics(curve.to_dict("records"),boundaries=[t for t in BOUNDARIES if start<=t<=end])==row["monthly"]
        assert abs(sum(j.get("net",0) for j in raw["journal"])-raw["closed_trade_net"])<1e-7
        assert abs(sum(j["amount"] for j in raw["journal"] if j["kind"]=="funding")-raw["funding"])<1e-7
        fee=next(f for c,f,_ in COSTS if c==row["cost"]);fees=0.;qty={}
        allowed={e["event_id"]:e for e in signals[row["source"]["id"]]}
        for j in raw["journal"]:
            if j["kind"]=="entry":assert j["at"]==allowed[j["event_id"]]["at"]
            if j["kind"] in ["entry","entry_add"]:
                qty[j["event_id"]]=qty.get(j["event_id"],0)+j["qty"];fees+=j["qty"]*j["price"]*fee
            elif "net" in j:
                fees+=qty.pop(j["event_id"])*j["price"]*fee
                if j["kind"]=="time_exit":assert row["holding"]=="time168" and j["held_hours"]>=168
        assert abs(fees-raw["fees"])<1e-7
        if curve.paused.any():
            first=curve.loc[curve.paused,"at"].iloc[0];assert curve.loc[curve["at"]>=first,"paused"].all()
            assert not any(j["kind"] in ["entry","entry_add"] and j["at"]>first for j in raw["journal"])
        if raw["ending_equity"] is None:
            assert raw["errors"] and not row["target_met"] and not row["monthly"]["complete"]
            incomplete.append(dict(id=row["id"],stop_event=raw["stop_event"],errors=raw["errors"]))
        else:assert curve["at"].iloc[-1]==end and abs(curve["equity"].iloc[-1]-raw["ending_equity"])<1e-7
        if row["baseline"]:
            key=f"{row['window']}_{row['cost']}_{row['reference_id']}"
            assert raw==json.loads((PRIOR/"runs"/f"{key}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(PRIOR/"runs"/f"{key}_equity.parquet"),check_exact=True);baseline_count+=1
    assert select(s["specs"],s["results"])==s["selected"]==json.loads((OUT/"candidate_lock.json").read_text(encoding="utf-8"))["selected"]
    print("AUDITED",len(s["results"]),"BASELINES",baseline_count,flush=True)
    specs={r["id"]:r for r in s["specs"]};exact=0
    replay_ids=set(s["selected"])|{"beta7d_breadth75_btc_scheduled_n25_hold","raw7d_breadth60_pullback_n25_time168"}
    for ident in sorted(replay_ids):
        spec=specs[ident];start,end=WINDOWS["year"]
        for cost,fee,slip in COSTS:
            r=simulate(list(range(start,end+1,300000)),grouped_signals(signals[spec["source"]["id"]],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
            r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct";key=f"year_{cost}_{ident}"
            assert {k:v for k,v in r.items() if k!="curve"}==json.loads((OUT/"runs"/f"{key}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(pd.DataFrame(r["curve"]),pd.read_parquet(OUT/"runs"/f"{key}_equity.parquet"),check_exact=True);exact+=1
    write(OUT/"verification.json",dict(journals_audited=len(s["results"]),baseline_paths_exact=baseline_count,replayed_paths_exact=exact,
        independent_beta_samples_checked=beta_checks,independent_rank_signals_checked=rank_checks,signal_prefixes_exact=prefixes,event_screens_recomputed=len(screens),
        locked_selection_reproduced=True,incomplete_paths=incomplete,source_hashes_match=True,data_hashes_match=True,live_config_unchanged=True))
    print("VERIFIED",flush=True)


if __name__=="__main__":main()
