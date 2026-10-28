"""Frozen six-policy replay under user-specified standard/stress execution costs."""
from datetime import datetime,timezone
import argparse
import gzip
import json
from pathlib import Path
import shutil
import numpy as np
import pandas as pd

import execution_v409 as x
import funding_v409 as f
import research_v408 as q

r=q.r;ART=f.ART;BASE=q.ART


def initialize():
    ART.mkdir(parents=True,exist_ok=True)
    if (ART/"PROTOCOL.json").exists():raise FileExistsError("Protocol is already registered")
    r.save(ART/"PROTOCOL.json",{
        "version":"4.0.9-research","registered_at_utc":datetime.now(timezone.utc).isoformat(),
        "user_instruction":"Standard Binance VIP6 with10bps slippage; stress Regular with50bps slippage; user explicitly confirmed slippage PER FILL including partial exits. Include actual historical funding; acquire missing data or disclose need for purchased data.",
        "scenarios":x.SCENARIOS,"fee_product":"Binance USDT-margined perpetual futures; taker for all executions; no BNB discount or rebates",
        "fee_source":"https://www.binance.com/en/fee/futureFee","fee_table_observed_on":"2026-10-18",
        "fee_basis":"Current benchmark tiers fixed across2020-2025; not a reconstructed history of changing exchange fee schedules or an assertion of account VIP eligibility.",
        "family":q.FAMILY,"new_signal_parameter_variants":0,"prior_adaptive_trials_at_least":24,
        "data_window":{"start_inclusive":"2020-01-01","end_exclusive":"2026-01-01"},
        "execution":"Frozen v408 reference-price signals, stops, targets and ratchet levels. Short entry sells reference*(1-slip); all exits buy reference*(1+slip). Fee charged on each actual execution notional. Exits within one5m bar may be stored as a quantity-weighted turnover group; linear per-fill costs are algebraically identical. Slippage is not charged twice in PnL.",
        "risk_sizing":"Fixed reference uses20% NAV reference notional. Risk policies use min(20% reference notional,0.5% NAV divided by modelled stop loss including both execution slippages and fees). Replaces v408's fixed60bps sizing buffer. No stop-gap loss guarantee. Portfolio limit5 positions,100% reference/current notional,2% stop risk (12% reference policy), evaluated after entry costs. Costs/funding enter equity before subsequent admissions; cap rejections do not consume wave/cooldown.",
        "funding":"Short cashflow=remaining quantity*historical mark*historical signed rate. Exact reported event milliseconds; entry<funding_time<=exit. At identical timestamps funding precedes bar-close exits, and entries follow both. 5m bar-close execution cannot resolve real intrabar ordering or Binance's settlement timing uncertainty.",
        "funding_prices":"Use markPrice from official funding response where present. Otherwise use official mark-price candle OPEN at preceding hour boundary, max15seconds prior. This is explicitly a proxy, not an exact settlement tick. Never use future candle close/high/low or silently set funding to zero.",
        "evaluation":"Six annual resets2020..2025 with five-day year-end entry embargo; link annual NAV. Expanding-window selection2022..2025 using only prior annual metrics; not a continuous-state multi-year simulation.",
        "selection":"At least2 prior years and60 trades, every prior year standard return>0, aggregate stress return>=0, annual DD<=15% both, no accepted missing execution bars. Exclude fixed reference. Rank stress linked return minus stress linked DD. Otherwise CASH. Lock before computing each test year.",
        "oos_disclosure":"Policy family already developed on2024 and inspected on2025. Retrospective chronological replay; fresh_oos=false.",
        "preserved_v408_checkpoint":{"path":str(BASE/"CHECKPOINT.json"),"sha256":r.sha(BASE/"CHECKPOINT.json")},"live_signoff":"NOT_GRANTED"})
    sources=[Path(__file__),Path(x.__file__),Path(f.__file__),Path(q.__file__),Path(r.__file__),
        r.ROOT/"scripts/fibo_research/research_round02_v407.py",r.ROOT/"tests/unit/fibo_short/test_execution_v409.py"]
    for p in sources:
        target=ART/"source_snapshot"/p.relative_to(r.ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    r.save(ART/"SOURCE_MANIFEST.json",{str(p.relative_to(r.ROOT)):r.sha(p) for p in sources})
    r.save(ART/"PROGRESS.json",{"stage":"cost_and_funding_protocol_registered","goal_complete":False})


def verify_sources():
    for path,digest in r.read(ART/"SOURCE_MANIFEST.json").items():assert r.sha(r.ROOT/path)==digest,path
    protocol=r.read(ART/"PROTOCOL.json")
    assert r.sha(BASE/"CHECKPOINT.json")==protocol["preserved_v408_checkpoint"]["sha256"]


def load_funding():
    metadata=r.read(ART/"funding/MANIFEST.json")
    assert metadata["all_symbols_downloaded"] and not metadata["errors"],"Incomplete funding acquisition"
    assert metadata["fetch_source_sha256"]==r.sha(f.__file__)
    output={};issues=[]
    for symbol,record in metadata["symbols"].items():
        p=ART/"funding/snapshots"/f"{symbol}.parquet"
        assert r.sha(p)==record["sha256"]
        frame=pd.read_parquet(p)
        assert frame.funding_ts_ms.min()>=f.START_MS and frame.funding_ts_ms.max()<f.LIMIT_MS
        assert frame.funding_ts_ms.is_unique and frame.funding_ts_ms.is_monotonic_increasing
        assert np.isfinite(frame[["funding_rate","mark_price"]].to_numpy()).all() and (frame.mark_price>0).all()
        if record["gaps_over_8h"] or record["left_edge_uncovered"] or record["right_edge_uncovered"]:
            issues.append({"symbol":symbol,"gaps":record["gaps_over_8h"],"left":record["left_edge_uncovered"],"right":record["right_edge_uncovered"]})
        output[symbol]={"times":frame.funding_ts_ms.to_numpy(),"events":frame.to_dict("records")}
    r.save(ART/"FUNDING_COVERAGE_CHECK.json",{"all_passed":not issues,"symbols":len(output),"issues":issues,
        "scope":"All candidate entry/exit ranges with16h context; official event stream no gaps>8h+15s and both edges bracketed. This does not certify exact settlement tick prices.",
        "funding_manifest_sha256":r.sha(ART/"funding/MANIFEST.json")})
    if issues:raise ValueError("Funding coverage requires review before performance evaluation")
    return output


def linked(nodes,scenario):
    equity=100.;curve=[100.];weeks=[];count=0;gaps=0
    components={k:0. for k in ("gross_reference_pnl_pct","fees_pct","slippage_pct","funding_pct")}
    for node in nodes:
        m=node[scenario];scale=equity/100
        curve.extend(scale*np.asarray(m["curve_values"])[1:])
        for k in components:components[k]+=scale*m.get(k,0.)
        equity*=1+m["return_pct"]/100
        count+=m["trades"];gaps+=m["accepted_missing_execution_bars"];weeks.extend(m["weekly_returns"])
    values=np.asarray(curve)
    assert abs(components["gross_reference_pnl_pct"]-components["fees_pct"]-components["slippage_pct"]+components["funding_pct"]-(equity-100))<1e-7
    return {"return_pct":equity-100,"max_dd_pct":float(np.max(1-values/np.maximum.accumulate(values))*100),"trades":count,
        "accepted_missing_execution_bars":gaps,"weekly_ci":r.block_ci(weeks),**components}


def choose(annual,year):
    past=[str(y) for y in range(2020,year)]
    if len(past)<2 or any(y not in annual for y in past):raise ValueError("Incomplete training years")
    audit={};scores=[]
    for spec in q.FAMILY:
        vid=spec["id"]
        if vid=="reference_m6_fixed":continue
        nodes=[annual[y][vid] for y in past]
        a=linked(nodes,"standard_vip6");b=linked(nodes,"stress_regular")
        positive=all(n["standard_vip6"]["return_pct"]>0 for n in nodes)
        worst=max(n[s]["max_dd_pct"] for n in nodes for s in x.SCENARIOS)
        valid=a["trades"]>=60 and positive and b["return_pct"]>=0 and worst<=15 and a["accepted_missing_execution_bars"]==b["accepted_missing_execution_bars"]==0
        audit[vid]={"standard":a,"stress":b,"all_prior_standard_years_positive":positive,"worst_annual_dd":worst,"eligible":bool(valid)}
        if valid:scores.append((b["return_pct"]-b["max_dd_pct"],vid))
    scores.sort(key=lambda v:(-v[0],v[1]))
    return {"test_year":year,"training_years":past,"selected":scores[0][1] if scores else "CASH","audit":audit,"uses_test_results":False}


def evaluate():
    verify_sources()
    if (ART/"RESULTS.json").exists():raise FileExistsError("Results already frozen")
    funding=load_funding();q.setup_context();candidates=r.load_candidates("history")
    sources={s["id"]:q.transformed(candidates,s) if "hours" in s else candidates for s in q.FAMILY}
    prepared={"full":{c["id"]:x.execution_steps(c) for c in candidates},
        "h24":{c["id"]:x.execution_steps(c) for c in sources["sniper_horizon24"]}}
    annual={};locks={};ledgers={}
    fingerprint={"protocol_sha256":r.sha(ART/"PROTOCOL.json"),"funding_manifest_sha256":r.sha(ART/"funding/MANIFEST.json"),
        "candidate_manifest_sha256":r.sha(BASE/"history/CANDIDATE_MANIFEST.json")}
    for year in range(2020,2026):
        if year>=2022:
            lock=choose(annual,year);p=ART/f"LOCK_TEST_{year}.json"
            if p.exists():
                saved=r.read(p);assert all(saved[k]==v for k,v in lock.items())
                assert all(saved[k]==v for k,v in fingerprint.items());lock=saved
            else:
                lock.update(locked_at_utc=datetime.now(timezone.utc).isoformat(),**fingerprint);r.save(p,lock)
            locks[str(year)]=lock
        complete=ART/f"YEAR_{year}.json";ledgerpath=ART/f"YEAR_{year}_LEDGERS.json.gz"
        if complete.exists():
            checkpoint=r.read(complete);assert all(checkpoint[k]==v for k,v in fingerprint.items())
            assert checkpoint["ledger_sha256"]==r.sha(ledgerpath)
            annual[str(year)]=checkpoint["results"]
            with gzip.open(ledgerpath,"rt",encoding="utf8") as fh:ledgers.update(json.load(fh))
            continue
        annual[str(year)]={}
        for spec in q.FAMILY:
            vid=spec["id"];row={}
            for name,scenario in x.SCENARIOS.items():
                result=x.portfolio(sources[vid],spec,f"{year}-01-01",f"{year+1}-01-01",scenario,funding,prepared["h24" if "hours" in spec else "full"])
                ledgers[f"{year}/{vid}/{name}"]={"ledger":result.pop("ledger"),"curve":result.pop("curve")}
                result["curve_values"]=[v for _,v in ledgers[f"{year}/{vid}/{name}"]["curve"]]
                row[name]=result
            annual[str(year)][vid]=row
            print(f"{year}/{vid} standard={row['standard_vip6']['return_pct']:.3f}% stress={row['stress_regular']['return_pct']:.3f}%",flush=True)
        with gzip.open(ledgerpath,"wt",encoding="utf8") as fh:json.dump({k:v for k,v in ledgers.items() if k.startswith(f"{year}/")},fh,separators=(",",":"),allow_nan=False)
        r.save(complete,{"results":annual[str(year)],"ledger_sha256":r.sha(ledgerpath),**fingerprint})
    oos={}
    for scenario in x.SCENARIOS:
        nodes=[]
        for year in range(2022,2026):
            vid=locks[str(year)]["selected"]
            if vid=="CASH":
                weeks=[0.]*len(annual[str(year)]["m6_risk"][scenario]["weekly_returns"])
                nodes.append({scenario:{"return_pct":0.,"curve_values":[100.,100.],"trades":0,"accepted_missing_execution_bars":0,"weekly_returns":weeks}})
            else:nodes.append(annual[str(year)][vid])
        oos[scenario]=linked(nodes,scenario)
    with gzip.open(ART/"LEDGERS.json.gz","wt",encoding="utf8") as fh:json.dump(ledgers,fh,separators=(",",":"),allow_nan=False)
    r.save(ART/"RESULTS.json",{"annual":annual,"walk_forward_locks":locks,"walk_forward_oos":oos,
        "fixed_policy_six_year":{s["id"]:{scenario:linked([annual[str(y)][s['id']] for y in range(2020,2026)],scenario) for scenario in x.SCENARIOS} for s in q.FAMILY},
        "scenarios":x.SCENARIOS,"fresh_oos":False,"post_2025_backtest_observations":0,"funding":"historical events with explicit mark-price proxy where API settlement mark unavailable",**fingerprint,"live_signoff":"NOT_GRANTED"})
    r.save(ART/"PROGRESS.json",{"stage":"dual_cost_historical_funding_evaluated","goal_complete":False,"next_action":"independent reconciliation and report"})


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=["init","evaluate"]);a=p.parse_args()
    initialize() if a.action=="init" else evaluate()
