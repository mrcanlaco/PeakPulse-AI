"""Offline mechanics, data availability, and certified carry attribution only.

No alpha search, account keys, market downloads, or actual liquidation forecast.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/research_reversal_20261013/risk_extension"
PRIOR = ROOT / "artifacts/research_branches_20261013/v3/report.json"
FINANCE = ROOT / "artifacts/research_branches_20261012/v3/report.json"
DB = ROOT / "artifacts/universe_policy_v2_48h.duckdb"
LEVERAGES = (2, 5, 10, 20, 50)
HOURS = (6, 12, 24, 48)
RULES = {
    "marketcap_hypothesis": "10M <= circulating USD marketcap known at signal <= 500M. No today's cap backfill; no performance estimate without certified as-of supply/cap.",
    "leverage_mechanics": "Show zero-equity 1/L and single-short maintenance boundary with fixed illustrative MMR0.5%, no maintenance deduction, other positions, closing/clearance fees, or tier changes. NOT exchange liquidation forecast.",
    "funding_scenarios": "Constant mark, fixed quantity, isolated collateral100, fee0.1% entry; hypothetical signed rates -0.1%/8h, -1%/8h, -1%/1h, +0.1%/8h; stop at first modeled maintenance breach. No probability or estimated typical leverage distribution.",
    "historical_carry": "Only inherited finance-certified Compact payments up to min(exit,entry+h). Signed cost=-cashflow. Unknown remains null. Separate lanes and champion/all diagnostics; same inherited trades, no new entry/exit policy.",
    "data_audit": "Exact symbol/feature_time join149 source IDs. Inspect only named current columns; nonnull does not certify raw provenance/available_at. No OI/ratio alpha test this round.",
}


def read(path):
    return json.loads(path.read_text(encoding="utf8"))


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf8")


def freeze():
    path=OUT/"experiment_lock.json"
    if path.exists():
        raise RuntimeError("Do not overwrite lock")
    hashes=dict(read(PRIOR)["source_hashes"])
    for p in (Path(__file__), PRIOR, FINANCE, DB, OUT/"protocol.md"):
        hashes[str(p)]=sha(p)
    verify(hashes)
    write(path,{"created_at_utc":datetime.now(timezone.utc).isoformat(),"rules":RULES,
        "leverage_values":list(LEVERAGES),"horizon_hours":list(HOURS),"hashes":hashes,
        "eligible_for_combination":False,"historical_alpha_test":False})
    print("Frozen mechanics and carry attribution protocol")


def verify(hashes):
    for p,h in hashes.items():
        if sha(Path(p))!=h:
            raise RuntimeError("Frozen source changed: "+p)


def short_boundary(collateral, notional, mmr=.005, signed_funding=0., entry_fee_rate=0.):
    """q*P0=N; C-fee+F+N*(1-r)=m*N*r, solve for r=P/P0."""
    values=(collateral,notional,mmr,signed_funding,entry_fee_rate)
    if not all(math.isfinite(v) for v in values) or collateral<=0 or notional<=0 or not 0<=mmr<1 or entry_fee_rate<0:
        raise ValueError("Invalid mechanics inputs")
    return (1+collateral/notional-entry_fee_rate+signed_funding/notional)/(1+mmr)-1


def constant_mark_carry(leverage, rate, interval_hours, horizon=48):
    if leverage<=0 or not math.isfinite(rate) or interval_hours<=0 or horizon<0:
        raise ValueError("Invalid carry scenario")
    collateral=100.;notional=collateral*leverage
    cash=collateral-notional*.001
    maintenance=notional*.005
    flow=0.; rows=[]
    breached = cash<=maintenance
    breach_time=0 if breached else None
    # Exclude entry-time settlement. Includes horizon settlement while held.
    for time in range(interval_hours,horizon+1,interval_hours):
        if breached:
            break
        payment=notional*rate
        flow+=payment;cash+=payment
        breached=cash<=maintenance
        rows.append({"hour":time,"funding_cashflow":payment,"cash_before_liquidation":cash,
            "maintenance":maintenance,"margin_breach":breached})
        if breached:
            breach_time=time
    return {"leverage":leverage,"signed_rate_per_settlement":rate,"interval_hours":interval_hours,
        "horizon_hours":horizon,"funding_cost_to_stop":-flow,"funding_cost_fraction_of_initial_margin":-flow/collateral,
        "first_modeled_breach_hour":breach_time,"ending_equity":None if breached else cash,
        "status":"margin_breach_unresolved" if breached else "illustrative_horizon_complete", "payments":rows}


def carry_to_horizon(outcome,hours):
    if not outcome.get("eligible"):
        return None
    start=pd.Timestamp(outcome["fills"][0]["timestamp"])
    deadline=min(pd.Timestamp(outcome["exit_time"]),start+pd.Timedelta(hours=hours))
    return -sum(p["cash_flow"] for p in outcome["funding_payments"] if start<pd.Timestamp(p["timestamp"])<=deadline)


def run():
    lock=read(OUT/"experiment_lock.json")
    if lock["rules"]!=RULES or lock["leverage_values"]!=list(LEVERAGES) or lock["horizon_hours"]!=list(HOURS):
        raise RuntimeError("Rules differ from lock")
    verify(lock["hashes"])
    source=read(PRIOR)["events"]
    specs=pd.DataFrame([{"symbol":r["symbol"],"feature_time":pd.Timestamp(r["feature_time_utc"])} for r in source]).drop_duplicates()
    c=duckdb.connect(str(DB),read_only=True)
    columns=[x[0] for x in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='universe_policy_candidates_v2'").fetchall()]
    c.register("requested",specs)
    names=("funding_rate_raw","oi_change_1h","oi_change_4h","global_ls_ratio","top_ls_ratio")
    df=c.execute("SELECT r.symbol,r.feature_time,p.symbol AS matched_symbol,"+','.join('p.'+n for n in names)+
        " FROM requested r LEFT JOIN universe_policy_candidates_v2 p ON r.symbol=p.symbol AND r.feature_time=p.feature_time").df()
    c.close()
    if len(df)!=len(specs):
        raise RuntimeError("Duplicate exact join")
    audit={"requested":len(specs),"returned":len(df),"exact_matched":int(df.matched_symbol.notna().sum()),
        "non_null":{n:int(df[n].notna().sum()) for n in names},
        "marketcap_columns":[n for n in columns if 'market_cap' in n.lower() or 'marketcap' in n.lower()],
        "top_position_ratio_present":any('position_ratio' in n.lower() for n in columns),
        "available_at_columns":[n for n in columns if 'available' in n.lower()],
        "raw_provenance_certified":False,"can_infer_money_on_each_side":False,
        "cap_filter_outcome":"unavailable_without_asof_marketcap_and_supply"}
    finance=read(FINANCE)["events"]
    details=[]
    for r in finance:
        x=r["variants"].get("compact") if r["eligible"] else None
        details.append({"source_event_id":r["source_event_id"],"lane_event_key":r["lane_event_key"],
            "lane":r["lane"],"symbol":r["symbol"],"champion":r["champion"],"eligible":r["eligible"],
            "funding_cost_by_horizon":{str(h):carry_to_horizon(x,h) if x else None for h in HOURS},
            "hold_hours":(pd.Timestamp(x["exit_time"])-pd.Timestamp(x["fills"][0]["timestamp"])).total_seconds()/3600 if x else None,
            "funding_cost_total":-x["funding_planned"] if x else None})
    summaries={}
    for lane in sorted({r['lane'] for r in details}):
        summaries[lane]={}
        for group in ("champion","all_frozen_diagnostic"):
            rs=[r for r in details if r['lane']==lane and (group=="all_frozen_diagnostic" or r['champion'])]
            known=[r for r in rs if r['eligible']]
            summaries[lane][group]={"rows":len(rs),"eligible":len(known),"unknown":len(rs)-len(known),
                "paying_net_count":sum(r['funding_cost_total']>0 for r in known),
                "receiving_net_count":sum(r['funding_cost_total']<0 for r in known),
                "verified_zero_net_count":sum(r['funding_cost_total']==0 for r in known),
                "mean_total_cost_planned":statistics.mean(r['funding_cost_total'] for r in known) if known else None,
                "max_total_cost_planned":max((r['funding_cost_total'] for r in known),default=None),
                "mean_cost_by_horizon":{str(h):statistics.mean(r['funding_cost_by_horizon'][str(h)] for r in known) if known else None for h in HOURS}}
    boundaries=[{"leverage":l,"zero_equity_adverse_move_without_costs":1/l,
        "maintenance_adverse_move_illustrative":short_boundary(100,100*l),
        "maintenance_move_after_entry_fee_and_funding_cost_0p6pct_notional":short_boundary(100,100*l,signed_funding=-.006*100*l,entry_fee_rate=.001),
        "effective_account_exposure_if_margin_fraction10pct":l*.1} for l in LEVERAGES]
    scenarios=[constant_mark_carry(l,rate,interval) for l in LEVERAGES for rate,interval in ((-.001,8),(-.01,8),(-.01,1),(.001,8))]
    verify(lock["hashes"])
    write(OUT/"report.json",{"status":"mechanics_and_carry_attribution_not_alpha", "rules":RULES,
        "source_hashes":lock["hashes"],"data_audit":audit,"leverage_boundaries":boundaries,
        "synthetic_carry_scenarios":scenarios,"historical_carry_by_lane":summaries,"historical_events":details,
        "marketcap_probability_above1B":None,"typical_trader_leverage_distribution":None,
        "dealer_intent_inferred":False,"eligible_for_combination":False,"daily_equity":None})
    print(json.dumps({"data_audit":audit,"boundaries":boundaries,"historical_carry":summaries},indent=2))


if __name__=="__main__":
    p=argparse.ArgumentParser();m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--freeze',action='store_true');m.add_argument('--run',action='store_true')
    args=p.parse_args();freeze() if args.freeze else run()
