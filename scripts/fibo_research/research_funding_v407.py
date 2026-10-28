"""Development-only funding hypotheses after the failed final test.

Never reopens or optimizes on the final OOS outcomes. Last-known funding is a
signal feature; portfolio funding remains the prespecified adverse scenario.
"""
from datetime import datetime, timezone
import argparse
import gzip
import json
from pathlib import Path
import numpy as np
import pandas as pd

import research_v407 as r
from research_round02_v407 import transformed

BASE=r.ART
ART=BASE/"round03_funding"
FUNDING=Path("E:/Quant-trading/data_lake/funding") if Path("E:/Quant-trading/data_lake/funding").exists() else Path("C:/Quant-trading/data_lake/funding")
VARIANTS=[
    {"id":"m6_funding_nonnegative","sniper":False,"funding_rule":"last_nonnegative"},
    {"id":"sniper_funding_nonnegative","sniper":True,"funding_rule":"last_nonnegative"},
    {"id":"sniper24_funding_nonnegative","sniper":True,"hours":24,"funding_rule":"last_nonnegative"},
    {"id":"sniper_rr1_24_funding_nonnegative","sniper":True,"hours":24,"rr_min":1.,"funding_rule":"last_nonnegative"},
    {"id":"sniper_rr1_24_funding_1bp","sniper":True,"hours":24,"rr_min":1.,"funding_rule":"last_at_least_1bp"},
    {"id":"sniper_rr1_24_funding_mean3","sniper":True,"hours":24,"rr_min":1.,"funding_rule":"last3_nonnegative"},
]


def init():
    ART.mkdir(exist_ok=True)
    if (ART/"PROTOCOL.json").exists():raise FileExistsError("Protocol already registered")
    r.save(ART/"PROTOCOL.json",{
        "registered_at_utc":datetime.now(timezone.utc).isoformat(),"experiment":"v407_round03_funding",
        "data_window":["2024-01-01","2025-01-01"],"new_variants":6,"cumulative_variants":24,"variants":VARIANTS,
        "hypothesis":"Negative recent funding can indicate crowded shorts and squeeze/carry risk. Test requiring last known funding nonnegative or at least 1bp; alternative mean of last three known settlements nonnegative.",
        "availability":"Only settlements at least five minutes before H1 signal close; latest must be no more than 12 hours old; three-event mean requires three settlements within 24h. Missing/stale features rejected as known at signal, never imputed using future data.",
        "execution_and_risk":"Unchanged v407 fixed-quantity engine, 40/60bps costs, adverse short 1bp/8h portfolio funding. Historical funding is used ONLY for past-known features, not substituted silently for PnL funding.",
        "gate":"Exploratory development: >=40 trades, positive 40bps+stress, nonnegative 60bps+stress, each reset half positive, maxDD<=15%, no execution gaps. This is not final sign-off.",
        "oos_status":"The 2025 final OOS in round02 has been consumed and failed its statistical gate. Do not reuse it as a fresh test for these adaptive hypotheses.",
        "selection_approval":"No automatic validation/final release from this script; preserve evidence for the next separately specified chronological evaluation procedure.",
        "post_2025_data_allowed":False,"live_signoff":"NOT_GRANTED"})


def funding_features(times,rates,decision):
    # Include a publication/availability lag instead of assuming instantaneous
    # knowledge of a settlement rate at the exact event timestamp.
    known=int(np.searchsorted(times,decision-300,side="right"))
    if not known or decision-times[known-1]>12*3600:
        return None
    last=float(rates[known-1]); mean3=None
    if known>=3 and decision-times[known-3]<=24*3600:
        mean3=float(np.mean(rates[known-3:known]))
    return {"last_rate":last,"last3_mean":mean3,"last_event_ts":int(times[known-1]),"feature_available_ts":int(times[known-1]+300)}


def read_funding(path):
    end=r.utc("2025-01-01")
    frame=pd.read_parquet(path,columns=["funding_time","funding_rate"],filters=[("funding_time",">=",r.utc("2023-10-01")),("funding_time","<",end)])
    frame["funding_time"]=pd.to_datetime(frame.funding_time,utc=True)
    if frame.duplicated("funding_time").any():
        counts=frame.groupby("funding_time").funding_rate.nunique()
        if (counts>1).any():raise ValueError("Conflicting funding values")
        frame=frame.drop_duplicates("funding_time")
    frame=frame.sort_values("funding_time")
    assert np.isfinite(frame.funding_rate.to_numpy()).all()
    assert frame.empty or frame.funding_time.max()<end
    return frame


def prepare():
    if (ART/"FEATURES.json").exists():raise FileExistsError("Feature snapshot already captured")
    candidates=r.load_candidates("development")
    features={}; sources={}; missing=[]
    (ART/"funding_snapshots").mkdir(exist_ok=True)
    for symbol in sorted({c["symbol"] for c in candidates}):
        path=FUNDING/f"{symbol}_funding.parquet"
        if not path.exists():missing.append(symbol);continue
        frame=read_funding(path)
        target=ART/"funding_snapshots"/path.name;frame.to_parquet(target,index=False)
        sources[symbol]={"path":str(path),"snapshot_sha256":r.sha(target),"records":len(frame),
                         "last_event":frame.funding_time.max().isoformat() if len(frame) else None}
        times=r.epoch_seconds(pd.DatetimeIndex(frame.funding_time)); rates=frame.funding_rate.to_numpy()
        for c in candidates:
            if c["symbol"]!=symbol:continue
            feature=funding_features(times,rates,c["decision_ts"])
            if feature is not None:features[c["id"]]=feature
    r.save(ART/"FEATURES.json",features)
    r.save(ART/"DATA_MANIFEST.json",{"sources":sources,"missing_files":missing,"candidates":len(candidates),"candidates_with_known_funding":len(features),"post_2024_observations_loaded":0,"protocol_sha256":r.sha(ART/"PROTOCOL.json")})
    print(f"Funding features: {len(features)}/{len(candidates)}; source files {len(sources)}, missing {len(missing)}",flush=True)


def passes_feature(feature,rule):
    if feature is None:return False
    if rule=="last_nonnegative":return feature["last_rate"]>=0
    if rule=="last_at_least_1bp":return feature["last_rate"]>=.0001
    if rule=="last3_nonnegative":return feature["last3_mean"] is not None and feature["last3_mean"]>=0
    raise ValueError("Unknown funding rule")


def evaluate():
    if (ART/"RESULTS.json").exists():raise FileExistsError("Results already recorded")
    candidates=r.load_candidates("development");features=r.read(ART/"FEATURES.json")
    results={};ledgers={}
    for spec in VARIANTS:
        source=[c for c in candidates if passes_feature(features.get(c["id"]),spec["funding_rule"])]
        if spec["sniper"]:source=transformed(source,spec)
        policy={"gate":"expanded","exit":"ladder","sizing":"risk"}
        row={}
        for cost in (40,60):
            out=r.portfolio(source,policy,"2024-01-01","2025-01-01",cost,True)
            out["weekly_ci"]=r.block_ci(out["weekly_returns"])
            key=f"{spec['id']}/{cost}bps_stress"
            ledgers[key]={"ledger":out.pop("ledger"),"curve":out.pop("curve")};row[f"{cost}bps_stress"]=out
        halves=[]
        for start,end in [("2024-01-01","2024-07-01"),("2024-07-01","2025-01-01")]:
            out=r.portfolio(source,policy,start,end,40,True)
            halves.append({"start":start,"end":end,"return_pct":out["return_pct"],"trades":out["trades"]})
        row["reset_half_year_checks"]=halves
        a,b=row["40bps_stress"],row["60bps_stress"]
        row["qualifies_development"]=bool(a["trades"]>=40 and a["return_pct"]>0 and b["return_pct"]>=0 and max(a["max_dd_pct"],b["max_dd_pct"])<=15 and all(h["return_pct"]>0 for h in halves) and a["accepted_missing_execution_bars"]==b["accepted_missing_execution_bars"]==0)
        results[spec["id"]]=row
        print(f"funding/{spec['id']}: N={a['trades']} NAV40={a['return_pct']:.3f}% NAV60={b['return_pct']:.3f}% DD={a['max_dd_pct']:.3f}% qualified={row['qualifies_development']}",flush=True)
    r.save(ART/"RESULTS.json",{"results":results,"data_window":["2024-01-01","2025-01-01"],"protocol_sha256":r.sha(ART/"PROTOCOL.json"),"source_sha256":r.sha(__file__),"features_sha256":r.sha(ART/"FEATURES.json"),"oos_evaluated":False,"fresh_oos":False,"live_signoff":"NOT_GRANTED"})
    with gzip.open(ART/"LEDGERS.json.gz","wt",encoding="utf8") as f:json.dump(ledgers,f,separators=(",",":"),allow_nan=False)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=["init","prepare","evaluate"]);a=p.parse_args()
    {"init":init,"prepare":prepare,"evaluate":evaluate}[a.action]()
