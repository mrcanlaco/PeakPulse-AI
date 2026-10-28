"""Independent bounded-input, ledger, selection-lock and report evidence audit."""
import gzip
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import research_v407 as r
from research_round02_v407 import ART, BASE


def main():
    output={"stages":{},"selection_locks":{},"historical_files_unchanged":0,"post_2025_observations_loaded":0}
    protected=r.read(BASE/"HISTORICAL_PRESERVATION.json")
    for relative,digest in protected.items():
        assert r.sha(r.ROOT/relative)==digest, relative
    output["historical_files_unchanged"]=len(protected)
    for stage,folder in [("development",BASE/"development"),("validation",ART/"validation"),("final_oos",ART/"final_oos")]:
        if not (folder/"DATA_MANIFEST.json").exists(): continue
        metadata=r.read(folder/"DATA_MANIFEST.json")
        count=0; total=0
        for sym,record in metadata["inputs"].items():
            path=folder/"bars_5m"/f"{sym}.parquet"
            assert r.sha(path)==record["snapshot_sha256"]
            df=pd.read_parquet(path)
            assert df.index.max()<r.utc(metadata["end_exclusive"])<=r.LIMIT
            assert df.index.is_monotonic_increasing and df.index.is_unique
            assert np.isfinite(df.to_numpy()).all()
            assert (df.high+1e-12>=df[["open","close"]].max(axis=1)).all(),sym
            assert (df.low-1e-12<=df[["open","close"]].min(axis=1)).all(),sym
            assert (df.high>=df.low).all() and (df.low>0).all()
            assert (df[["volume","quote_volume"]]>=0).all().all()
            count+=1;total+=len(df)
        output["stages"][stage]={"bounded_snapshots_valid":count,"bars_5m":total,"end_exclusive":metadata["end_exclusive"]}
        print(f"Verified {stage}: {count} bounded inputs, {total} five-minute candles",flush=True)
    for lock_name,previous,next_stage in [("SHORTLIST_LOCK.json","development","validation"),("WINNER_LOCK.json","validation","final_oos")]:
        p=ART/lock_name
        if not p.exists():continue
        lock=r.read(p)
        assert lock["selection_results_sha256"]==r.sha(ART/previous/"RESULTS.json")
        assert lock["protocol_sha256"]==r.sha(ART/"PROTOCOL.json")
        selected=lock["variant_ids"]
        result_path=ART/next_stage/"RESULTS.json"
        if result_path.exists():
            evaluated=r.read(result_path)["results"]
            assert set(evaluated)==set(selected)|{"reference_m6_fixed"}
        output["selection_locks"][lock_name]={"verified":True,"variant_ids":selected}
    nodes=0;records=0
    for folder in [BASE/"development",ART/"development",ART/"validation",ART/"final_oos",BASE/"round03_funding"]:
        if not (folder/"RESULTS.json").exists():continue
        results=r.read(folder/"RESULTS.json")["results"]
        with gzip.open(folder/"LEDGERS.json.gz","rt",encoding="utf8") as f:ledgers=json.load(f)
        for key,node in ledgers.items():
            vid,scenario=key.split("/")
            cost=int(scenario.split("bps")[0])/10000
            rows=node["ledger"];curve=np.asarray(node["curve"],dtype=float)
            assert len({p["id"] for p in rows})==len(rows)
            assert (np.diff(curve[:,0])>=0).all()
            expected=100.
            for trade in rows:
                assert abs(trade["fees"]-cost*trade["notional"])<1e-8
                assert abs(trade["qty"]*trade["entry"]-trade["notional"])<1e-8
                expected_pnl=trade["qty"]*trade["entry"]*trade["gross_return"]-trade["fees"]+trade["funding"]
                assert abs(expected_pnl-trade["pnl"])<1e-8
                expected+=expected_pnl
                if vid!="reference_m6_fixed":
                    # Include the fixed 60bp risk buffer used at admission.
                    risk=trade["qty"]*(trade["stop"]-trade["entry"])+.006*trade["notional"]
                    assert risk <= .005*trade["equity_at_entry"]+1e-8
            assert abs(expected-curve[-1,1])<1e-8
            assert abs(results[vid][scenario]["return_pct"]-(expected-100))<1e-8
            dd=float(np.max(1-curve[:,1]/np.maximum.accumulate(curve[:,1]))*100)
            assert abs(results[vid][scenario]["max_dd_pct"]-dd)<1e-8
            nodes+=1;records+=len(rows)
    output["ledger_nodes_verified"]=nodes
    output["scenario_trade_records_verified"]=records
    funding_dir=BASE/"round03_funding"
    if (funding_dir/"FEATURES.json").exists():
        metadata=r.read(funding_dir/"DATA_MANIFEST.json")
        features=r.read(funding_dir/"FEATURES.json")
        candidates={c["id"]:c for c in r.load_candidates("development")}
        source_frames={}
        for symbol,source in metadata["sources"].items():
            path=funding_dir/"funding_snapshots"/f"{symbol}_funding.parquet"
            assert r.sha(path)==source["snapshot_sha256"]
            f=pd.read_parquet(path)
            assert f.empty or f.funding_time.max()<r.utc("2025-01-01")
            source_frames[symbol]=f
        for cid,feature in features.items():
            c=candidates[cid]
            cutoff=pd.Timestamp(c["decision_ts"]-300,unit="s",tz="UTC")
            known=source_frames[c["symbol"]].loc[lambda f:f.funding_time<=cutoff]
            assert len(known)>0
            latest=known.iloc[-1]
            assert feature["last_rate"]==float(latest.funding_rate)
            assert feature["last_event_ts"]==int(latest.funding_time.timestamp())
            assert feature["feature_available_ts"]<=c["decision_ts"]
            assert 0<=c["decision_ts"]-feature["last_event_ts"]<=12*3600
            expected_mean=None
            if len(known)>=3 and c["decision_ts"]-int(known.iloc[-3].funding_time.timestamp())<=24*3600:
                expected_mean=float(known.iloc[-3:].funding_rate.mean())
            if expected_mean is None:
                assert feature["last3_mean"] is None
            else:
                assert abs(feature["last3_mean"]-expected_mean)<1e-12
        output["causal_funding_features_verified"]=len(features)
        output["funding_snapshot_files_verified"]=len(source_frames)
    root=ET.parse(BASE/"ALL_TESTS.xml").getroot()
    testsuites=list(root.iter("testsuite"))
    output["tests"]={name:sum(int(x.attrib.get(name,0)) for x in testsuites) for name in ["tests","failures","errors","skipped"]}
    assert output["tests"]["failures"]==output["tests"]["errors"]==0
    output["all_executed_checks_passed"]=True
    output["goal_complete"]=False
    r.save(BASE/"INDEPENDENT_VERIFICATION.json",output)
    print(json.dumps(output,ensure_ascii=False))


if __name__=="__main__":main()
