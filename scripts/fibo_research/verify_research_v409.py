"""Independent source, fill, funding and cash-event reconciliation."""
from collections import defaultdict
import argparse
import gzip
import json
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import research_v409 as z

r=z.r;ART=z.ART


def close(a,b):
    assert np.allclose(a,b,atol=1e-8,rtol=0),"Independent reconciliation failed"


def inputs():
    z.verify_sources();funding=z.load_funding()
    old=r.read(z.BASE/"CHECKPOINT.json")
    for relative,digest in old["files"].items():assert r.sha(z.BASE/relative)==digest,relative
    for relative,digest in old["additional_sources"].items():assert r.sha(r.ROOT/relative)==digest,relative
    manifest=r.read(ART/"funding/MANIFEST.json");total=0;prices=defaultdict(int);files=0;local=0;matches=0;diffs=0
    for symbol,record in manifest["symbols"].items():
        rates={};marks={}
        for relative,digest in record["raw_responses"].items():
            path=ART/relative;assert r.sha(path)==digest
            with gzip.open(path,"rt",encoding="utf8") as f:raw=json.load(f)
            params=raw["params"]
            assert z.f.START_MS<=params["startTime"]<=params["endTime"]<z.f.LIMIT_MS
            if raw["url"]==z.f.FUNDING_URL:
                for item in raw["data"]:
                    assert params["startTime"]<=item["fundingTime"]<=params["endTime"]
                    assert item["symbol"]==symbol
                    rates[int(item["fundingTime"])]=item
            elif raw["url"]==z.f.MARK_URL:
                assert params["interval"]=="1h"
                for item in raw["data"]:
                    assert params["startTime"]<=item[0]<=params["endTime"]
                    marks[item[0]]=float(item[1])
            else:raise AssertionError("Unexpected data source")
            files+=1
        pack=funding[symbol]
        assert set(rates)==set(pack["times"])
        for event in pack["events"]:
            t=event["funding_ts_ms"];raw=rates[t]
            close(event["funding_rate"],float(raw["fundingRate"]))
            if event["price_source"]=="funding_api_settlement_mark":
                close(event["mark_price"],float(raw["markPrice"]))
                assert event["mark_reference_ts_ms"]==t
            else:
                assert not raw["markPrice"] or float(raw["markPrice"])<=0
                m=event["mark_reference_ts_ms"]
                assert 0<=t-m<=15000 and m%3600000==0
                close(event["mark_price"],marks[m])
            prices[event["price_source"]]+=1;total+=1
        local+=record["local_rows"];matches+=record["local_matches"];diffs+=len(record["local_differences_ms"])
    output={"all_checks_passed":True,"funding_symbols":len(funding),"funding_events":total,"price_sources":dict(prices),
        "raw_responses_verified":files,"local_rows_compared":local,"local_rates_matching":matches,"local_differences":diffs,
        "previous_checkpoint_files_preserved":len(old["files"]),"post_2025_backtest_observations":0,
        "funding_manifest_sha256":r.sha(ART/"funding/MANIFEST.json"),"price_quality":"historical settlement marks where available; explicit official mark-candle OPEN proxy otherwise"}
    r.save(ART/"INPUT_VERIFICATION.json",output);print(json.dumps(output),flush=True)


def results():
    z.verify_sources();funding=z.load_funding()
    evidence=r.read(ART/"INPUT_VERIFICATION.json")
    assert evidence["funding_manifest_sha256"]==r.sha(ART/"funding/MANIFEST.json")
    result=r.read(ART/"RESULTS.json")
    with gzip.open(ART/"LEDGERS.json.gz","rt",encoding="utf8") as f:ledgers=json.load(f)
    assert len(ledgers)==72
    z.q.setup_context();original=r.load_candidates("history")
    candidates={c["id"]:c for c in original}
    transformed={s["id"]:{c["id"]:c for c in z.q.transformed(original,s)} if "hours" in s else candidates for s in z.q.FAMILY}
    count=0;trades=0;fills=0;payments=0;proxy=0;proxy_amount=0.;proxy_abs=0.
    for key,node in ledgers.items():
        year,vid,name=key.split("/");scenario=z.x.SCENARIOS[name]
        metric=result["annual"][year][vid][name];rows=node["ledger"]
        curve=np.asarray(node["curve"]);start=int(r.utc(f"{year}-01-01").timestamp()*1000);end=int(r.utc(f"{int(year)+1}-01-01").timestamp()*1000)
        events=defaultdict(float);events[start]=0.;events[end]=0.
        assert len({p["id"] for p in rows})==len(rows)==metric["trades"]
        for p in rows:
            c=transformed[vid][p["id"]];path=c["paths"]["ladder"]
            assert start<=p["entry_ts_ms"]<end-5*86400000 and p["exit_ts_ms"]<=end
            assert p["entry_ts_ms"]==c["entry_ts"]*1000 and p["exit_ts_ms"]==path["exit_ts"]*1000
            close(p["reference_notional"],p["qty"]*p["entry"])
            fee=0.;slip=0.;actual_gross=0.;sellqty=0.;buyqty=0.
            for fill in p["fills"]:
                direction=-1 if fill["side"]=="SELL" else 1
                close(fill["execution_price"],fill["reference_price"]*(1+direction*scenario["slippage_bps"]/10000))
                close(fill["notional"],fill["qty"]*fill["execution_price"])
                close(fill["fee"],fill["notional"]*scenario["fee_bps"]/10000)
                close(fill["slippage_cost"],fill["qty"]*fill["reference_price"]*scenario["slippage_bps"]/10000)
                actual_gross+=(-direction)*fill["notional"]
                fee+=fill["fee"];slip+=fill["slippage_cost"]
                events[fill["timestamp_ms"]]-=fill["fee"]+fill["slippage_cost"]
                if fill["side"]=="SELL":sellqty+=fill["qty"]
                else:buyqty+=fill["qty"]
            close(sellqty,p["qty"]);close(buyqty,p["qty"]);close(fee,p["fees"]);close(slip,p["slippage"])
            if vid!="reference_m6_fixed":assert p["stop_risk_with_execution_costs"]<=.005*p["equity_at_entry"]+1e-8
            for step in path["trace"]:events[step[0]*1000]+=p["reference_notional"]*step[5]
            pack=funding[p["symbol"]]
            times=pack["times"]
            left=np.searchsorted(times,p["entry_ts_ms"],side="right");right=np.searchsorted(times,p["exit_ts_ms"],side="right")
            expected=pack["events"][left:right]
            assert [e["funding_ts_ms"] for e in expected]==[e["funding_ts_ms"] for e in p["funding_events"]]
            funding_sum=0.
            for actual,source in zip(p["funding_events"],expected):
                assert all(actual[k]==v for k,v in source.items())
                t=actual["funding_ts_ms"]
                # At equality, funding precedes that bar's closing executions.
                past=[s for s in path["trace"] if s[0]*1000<t]
                rem=past[-1][3] if past else 1.
                close(actual["remaining_qty"],p["qty"]*rem)
                cash=p["qty"]*rem*source["mark_price"]*source["funding_rate"]
                close(actual["cashflow"],cash);funding_sum+=cash;events[t]+=cash
                if source["price_source"]!="funding_api_settlement_mark":proxy+=1;proxy_amount+=cash;proxy_abs+=abs(cash)
            close(funding_sum,p["funding"]);close(actual_gross-fee+funding_sum,p["pnl"])
            close(p["reference_notional"]*p["gross_reference_return"]-fee-slip+funding_sum,p["pnl"])
            fills+=len(p["fills"]);payments+=len(p["funding_events"])
        stamps=sorted(events);cash=100+np.cumsum([events[t] for t in stamps])
        observed=pd.Series(curve[:,1],index=curve[:,0]).groupby(level=0).last()
        assert stamps==observed.index.tolist();close(cash,observed.to_numpy());close(metric["return_pct"],cash[-1]-100)
        close(metric["curve_values"],curve[:,1])
        close(100+sum(p["pnl"] for p in rows),cash[-1])
        close(metric["max_dd_pct"],np.max(1-curve[:,1]/np.maximum.accumulate(curve[:,1]))*100)
        for name_,field in [("fees_pct","fees"),("slippage_pct","slippage"),("funding_pct","funding")]:close(metric[name_],sum(p[field] for p in rows))
        assert metric["funding_events"]==sum(len(p["funding_events"]) for p in rows)
        count+=1;trades+=len(rows)
    locks={}
    for year in range(2022,2026):
        calculated=z.choose(result["annual"],year);locked=r.read(ART/f"LOCK_TEST_{year}.json")
        assert all(locked[k]==v for k,v in calculated.items())
        assert locked==result["walk_forward_locks"][str(year)]
        locks[str(year)]=locked["selected"]
    for vid,scenarios in result["fixed_policy_six_year"].items():
        for name,node in scenarios.items():assert node==z.linked([result["annual"][str(y)][vid] for y in range(2020,2026)],name)
    for scenario in z.x.SCENARIOS:
        nodes=[]
        for year in range(2022,2026):
            choice=locks[str(year)]
            if choice=="CASH":
                weeks=[0.]*len(result["annual"][str(year)]["m6_risk"][scenario]["weekly_returns"])
                nodes.append({scenario:{"return_pct":0.,"curve_values":[100.,100.],"trades":0,"accepted_missing_execution_bars":0,"weekly_returns":weeks}})
            else:nodes.append(result["annual"][str(year)][choice])
        assert result["walk_forward_oos"][scenario]==z.linked(nodes,scenario)
    suites=list(ET.parse(ART/"EXECUTION_TESTS.xml").getroot().iter("testsuite"))
    tests={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ("tests","errors","failures","skipped")}
    assert tests["errors"]==tests["failures"]==tests["skipped"]==0
    out={"all_checks_passed":True,"scenario_nodes_verified":count,"scenario_trade_records":trades,"execution_fill_groups":fills,
        "funding_payments_verified":payments,"proxy_mark_payments":proxy,"proxy_cashflow_sum_across_scenarios":proxy_amount,
        "proxy_absolute_cashflow_sum_across_scenarios":proxy_abs,"chronological_selections":locks,"new_tests":tests,
        "results_sha256":r.sha(ART/"RESULTS.json"),"ledgers_sha256":r.sha(ART/"LEDGERS.json.gz"),"input_verification_sha256":r.sha(ART/"INPUT_VERIFICATION.json"),
        "fresh_oos":False,"live_signoff":"NOT_GRANTED","goal_complete":False}
    r.save(ART/"INDEPENDENT_VERIFICATION.json",out);print(json.dumps(out),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=["inputs","results"]);a=p.parse_args()
    inputs() if a.action=="inputs" else results()
