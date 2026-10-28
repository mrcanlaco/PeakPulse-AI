"""Causal direction gates, independent rule enumeration and signed accounts."""
import json
import hashlib
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from account_directional_replay import simulate
from capital_research_metrics import audit_account, utilization
from compare_account_risk import ROOT, sha, write, exchange_rules
from directional_trend_signals import prepare, generate, definitions as sources
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from research_directional_audit import audit_directional
from search_directional_trend import OUT, PRIOR, DATA, WINDOWS, BOUNDARIES, COSTS, definitions, select, exit_diagnostics
from search_multitimeframe_rolling import grouped_signals


def oracle_state(enriched, index):
    members=[f.reindex(index) for c,f in enriched.items() if c!="BTCUSDT"]
    ready=np.array([f.ready.fillna(False).to_numpy(dtype=bool) for f in members])
    above=np.array([(f.close>f.ema60).to_numpy() for f in members]) & ready
    below=np.array([(f.close<f.ema60).to_numpy() for f in members]) & ready
    btc=enriched["BTCUSDT"].reindex(index);rows={}
    for i,t in enumerate(index):
        count=int(ready[:,i].sum());up=above[:,i].sum()/count if count else float("nan")
        down=below[:,i].sum()/count if count else float("nan");r=btc.iloc[i]
        good=count>=24 and pd.notna(r.ready) and bool(r.ready)
        rows[t]=dict(coverage=count,above=up,below=down,
            long_allowed=bool(good and up>=.60 and r.ema20>r.ema60 and r.close>r.ema20 and r.ret24>0),
            short_allowed=bool(good and down>=.60 and r.ema20<r.ema60 and r.close<r.ema20 and r.ret24<0))
    return rows


def oracle(enriched, market, frozen, spec):
    output=[]
    for coin,f in enriched.items():
        if coin=="BTCUSDT":continue
        records=list(f.itertuples());sides=["LONG","SHORT"] if spec["mode"]=="both_trend" else ["LONG"]
        for side in sides:
            last=-(10**18);long=side=="LONG"
            for i,r in enumerate(records):
                if not r.ready or i<71:continue
                if spec["regime"]!="any" and not market[r.Index][side.lower()+"_allowed"]:continue
                trend=(r.ema20>r.ema60 and r.close>r.ema20 and r.ret24>0) if long else (r.ema20<r.ema60 and r.close<r.ema20 and r.ret24<0)
                candle=r.close>r.open if long else r.close<r.open
                if not trend or not candle:continue
                volume=r.quote_volume / np.mean([v.quote_volume for v in records[i-20:i]])
                if spec["family"]=="breakout":
                    trigger=r.close>max(v.high for v in records[i-20:i]) if long else r.close<min(v.low for v in records[i-20:i])
                    if not trigger or not volume>=1.5:continue
                elif not ((r.low<=r.ema20 if long else r.high>=r.ema20) and volume>=1):continue
                score=abs(r.ret24)/(r.atr/r.close)
                if not np.isfinite(score):continue
                at=int(r.Index.timestamp()*1000)
                if at-last<86400000:continue
                last=at
                event=hashlib.sha256(f"trend_v1:{spec['family']}:{spec['regime']}:{side}:{coin}:{at}".encode()).hexdigest()[:24]
                output.append(dict(symbol=coin,side=side,at=at,atr=r.atr,probability=score,event_id=event,family=spec["family"]))
    if spec["mode"]=="hybrid":
        for event in frozen:
            t=pd.Timestamp(event["at"],unit="ms",tz="UTC");f=enriched[event["symbol"]]
            if t not in f.index:continue
            if spec["regime"]!="any" and not market[t]["short_allowed"]:continue
            r=f.loc[t];score=abs(r.ret24)/(r.atr/r.close)
            if np.isfinite(score):output.append(dict(event,side="SHORT",probability=float(score),family="reversal"))
    return sorted(output,key=lambda r:(r["at"],-r["probability"],r["symbol"],r["side"]))


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));p=s["protocol"]
    assert sha(ROOT/"configs/live.yaml")==p["live_config_sha256"] and sha(RULE_PATH)==p["rules_sha256"]
    assert sha(DATA/"reconciled_manifest.json")==p["data_sha256"] and sha(PRIOR/"summary.json")==p["prior_sha256"] and sha(PRIOR/"signals.json")==p["signals_sha256"]
    for n,d in p["source_sha256"].items():assert sha(ROOT/"scripts"/n)==d
    assert definitions(json.loads((PRIOR/"summary.json").read_text(encoding="utf-8")))==s["specs"]
    assert select(s["specs"],s["results"])==s["selected"]==json.loads((OUT/"candidate_lock.json").read_text())["selected"]
    tests=ET.parse(ROOT/"tmp/directional_trend_tests.xml").getroot().find("testsuite")
    assert tests is not None and int(tests.attrib["tests"])==88 and int(tests.attrib["failures"])==int(tests.attrib["errors"])==0
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);enriched,state=prepare(frames)
    old=json.loads((PRIOR/"signals.json").read_text(encoding="utf-8"));saved=json.loads((OUT/"signals.json").read_text(encoding="utf-8"))
    signals=generate(enriched,state,old["short_mask2"])
    for mode in ["short","long","both"]:signals["control_"+mode]=old[mode+"_mask2"]
    assert signals==saved
    pd.testing.assert_frame_equal(state.reset_index(),pd.read_parquet(OUT/"market_state.parquet"),check_exact=True)
    market=oracle_state(enriched,state.index)
    for t,r in state.iterrows():
        for k in ["coverage","long_allowed","short_allowed"]:assert r[k]==market[t][k]
        for k in ["above","below"]:assert (pd.isna(r[k]) and pd.isna(market[t][k])) or abs(r[k]-market[t][k])<1e-12
    appearances=0;unique=set()
    for source in sources():
        expected=oracle(enriched,market,old["short_mask2"],source)
        assert expected==signals[source["id"]],source["id"]
        appearances+=len(expected);unique.update(r["event_id"] for r in expected)
    atr_checks=0
    for coin,f in enriched.items():
        if coin=="BTCUSDT":continue
        samples=[r for r in signals["breakout_any_both_trend"]+signals["pullback_any_both_trend"] if r["symbol"]==coin]
        for r in samples[::max(1,len(samples)//8)][:8]:
            t=pd.Timestamp(r["at"],unit="ms",tz="UTC");bars=list(f.loc[:t].tail(15).itertuples())
            atr=sum(max(b.high-b.low,abs(b.high-a.close),abs(b.low-a.close)) for a,b in zip(bars,bars[1:]))/14
            assert len(bars)==15 and abs(atr-r["atr"])<1e-8;atr_checks+=1
    prefixes=0
    for cut in ["2025-11-15 13:00","2026-03-01 17:00","2026-07-15 10:00"]:
        t=pd.Timestamp(cut,tz="UTC");ms=int(t.timestamp()*1000)
        e,m=prepare({c:f.loc[:t] for c,f in frames.items()})
        pd.testing.assert_frame_equal(m.loc[:t],state.loc[:t],check_exact=True)
        for key,rows in generate(e,m,[r for r in old["short_mask2"] if r["at"]<=ms]).items():
            assert rows==[r for r in signals[key] if r["at"]<=ms];prefixes+=1
    print("SIGNALS",len(unique),"APPEARANCES",appearances,"PREFIXES",prefixes,flush=True)
    specs={r["id"]:r for r in s["specs"]};baselines=fc=fills=curves=0;incomplete=[]
    for i,row in enumerate(s["results"],1):
        raw=json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"));curve=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet")
        sp=specs[row["strategy_id"]];start,end=WINDOWS[row["window"]];_,fee,slip=next(v for v in COSTS if v[0]==row["cost"])
        audit_account(raw,sp["notional"]);assert utilization(curve,raw,sp["notional"])==row["utilization"]
        assert exit_diagnostics(raw)==row["exit_diagnostics"]
        assert monthly_metrics(curve.to_dict("records"),boundaries=[t for t in BOUNDARIES if start<=t<=end])==row["monthly"]
        assert row["target_met"]==(raw["ending_equity"] is not None and row["monthly"]["all_months_50pct"])
        a,b,c=audit_directional(raw,curve,prices,funding,fee,slip,5,sp["notional"]);fc+=a;fills+=b;curves+=c
        if raw["ending_equity"] is None:
            assert raw["errors"] and not row["target_met"];incomplete.append(dict(id=row["id"],errors=raw["errors"],stop_event=raw["stop_event"]))
        else:assert curve["at"].iloc[-1]==end and abs(curve.equity.iloc[-1]-raw["ending_equity"])<1e-8
        if curve.paused.any():
            first=curve.loc[curve.paused,"at"].iloc[0];assert curve.loc[curve["at"]>=first,"paused"].all()
            assert not any(j["kind"] in ["entry","entry_add"] and j["at"]>first for j in raw["journal"])
        if row["baseline"]:
            ref=f"{row['window']}_{row['cost']}_{sp['reference_id']}"
            assert raw==json.loads((PRIOR/"runs"/f"{ref}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(curve,pd.read_parquet(PRIOR/"runs"/f"{ref}_equity.parquet"),check_exact=True);baselines+=1
        if i%60==0:print("AUDIT",i,"/",len(s["results"]),flush=True)
    cases={(r["strategy_id"],"later") for r in s["selected"] if r["strategy_id"]}
    cases|={("breakout_breadth60_btc_both_trend_n25_hold","year"),("pullback_any_hybrid_n100_time168","year")}
    exact=0
    for ident,window in sorted(cases):
        sp=specs[ident];start,end=WINDOWS[window]
        for cost,fee,slip in COSTS:
            r=simulate(list(range(start,end+1,300000)),grouped_signals(signals[sp["source"]["id"]],start,end),lambda c:prices.get(c,{}),
                rules,lambda c:funding[c],configuration(5,fee,slip),research_policy=sp["policy"])
            r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct";key=f"{window}_{cost}_{ident}"
            assert {k:v for k,v in r.items() if k!="curve"}==json.loads((OUT/"runs"/f"{key}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(pd.DataFrame(r["curve"]),pd.read_parquet(OUT/"runs"/f"{key}_equity.parquet"),check_exact=True);exact+=1
    write(OUT/"verification.json",dict(journals_audited=len(s["results"]),baseline_paths_exact=baselines,replayed_paths_exact=exact,
        independent_unique_signals=len(unique),signal_appearances=appearances,market_states_checked=len(state),independent_atr_samples=atr_checks,
        causal_prefixes=prefixes,funding_quantities_checked=fc,directional_fills_checked=fills,equity_states_reconstructed=curves,
        incomplete_paths=incomplete,hashes_match=True,live_config_unchanged=True,unit_tests_passed=88,
        junit_sha256=sha(ROOT/"tmp/directional_trend_tests.xml"),audit_source_sha256=sha(ROOT/"scripts/research_directional_audit.py")))
    print("VERIFIED",flush=True)


if __name__=="__main__":main()
