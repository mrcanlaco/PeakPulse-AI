"""Filter frozen reversal events using completed, volume-weighted taker flow."""
import json
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd
from compare_account_risk import ROOT,sha
from prepare_flow_research import hourly_flow,OUT as OLD_FLOW
from prepare_frozen_extension import OUT as DATA


def four_hour_flow(hourly):
    h=hourly[["volume","taker_buy_volume"]].copy()
    if h.index.has_duplicates or not h.index.is_monotonic_increasing:raise ValueError("ambiguous_flow_time")
    valid=np.isfinite(h).all(axis=1)&h.volume.gt(0)&h.taker_buy_volume.ge(0)&h.taker_buy_volume.le(h.volume+1e-8)
    h["valid"]=valid
    f=h.resample("4h",closed="right",label="right",origin="epoch").agg(volume=("volume","sum"),buy=("taker_buy_volume","sum"),valid_hours=("valid","sum"))
    f["ratio"]= (f.buy/f.volume).where(f.valid_hours.eq(4)&f.volume.gt(0))
    f["previous_ratio"]=f.ratio.shift()
    return f


def load_flow():
    old=json.loads((OLD_FLOW/"flow_evidence.json").read_text(encoding="utf-8"))
    manifest=json.loads((DATA/"reconciled_manifest.json").read_text(encoding="utf-8"))
    assert old["ready"] and manifest["data_ready"]
    proof={r["symbol"]:r for r in manifest["proof"]};result={};evidence=[]
    for a in old["audits"]:
        coin=a["symbol"];path=OLD_FLOW/"flow"/f"{coin}.parquet"
        assert sha(path)==a["flow_sha256"]
        older=pd.read_parquet(path);parts=[];archives=[]
        for z in proof[coin]["archives"]:
            if "/klines/" not in z["url"]:continue
            path=Path(z["file"]);assert z["checksum_verified"] and sha(path)==z["sha256"]
            with zipfile.ZipFile(path) as archive:
                assert len(archive.namelist())==1
                raw=pd.read_csv(archive.open(archive.namelist()[0]))
            stamps=raw.open_time.astype("int64");raw.open_time=stamps//1000 if stamps.max()>10**14 else stamps
            parts.append(raw);archives.append(dict(file=str(path),sha256=z["sha256"]))
        assert len(parts)==3
        raw=pd.concat(parts,ignore_index=True).sort_values("open_time")
        assert not raw.open_time.duplicated().any()
        ref=DATA/"trade"/f"{coin}.parquet";assert sha(ref)==proof[coin]["trade_sha256"]
        reference=pd.read_parquet(ref)
        pd.testing.assert_frame_equal(raw[reference.columns].reset_index(drop=True),reference,check_exact=True)
        v=raw[["volume","taker_buy_volume"]]
        assert np.isfinite(v).all().all() and v.ge(0).all().all() and raw.taker_buy_volume.le(raw.volume+1e-8).all()
        raw.open_time=pd.to_datetime(raw.open_time,unit="ms",utc=True)
        fresh=hourly_flow(raw[["open_time","volume","taker_buy_volume"]])
        joined=pd.concat([older,fresh]);result[coin]=four_hour_flow(joined)
        evidence.append(dict(symbol=coin,old_hourly_sha256=a["flow_sha256"],archives=archives,new_rows=len(raw),reference_prices_exact=True,
            new_hours=len(fresh),missing_four_hour_ratios=int(result[coin].ratio.isna().sum())))
    return result,dict(ready=True,old_evidence_sha256=sha(OLD_FLOW/"flow_evidence.json"),extension_manifest_sha256=sha(DATA/"reconciled_manifest.json"),proof=evidence,
        scope="Oldhourlyflow fromprevious90coin-monthspotcomparisons. Extension90officialZIPs checksumverified;everynewOHLC/quotevolrowmatches frozenpriceinputs. Baseunits,sum buy /sumtotal;missing/incomplete/zero-volume notneutral. Not openinterest or signed inventory.",
        documentation="https://github.com/binance/binance-public-data#klines-1")


def definitions():
    return [dict(id=f"mask{mask}_{gate}",mask=mask,gate=gate) for mask in [0,2] for gate in ["none","seller","drop5","exhaust","absorbed"]]


def accepts(current,previous,gate):
    if gate=="none":return True
    if not np.isfinite([current,previous]).all():return False
    if gate=="seller":return current<=.50
    if gate=="drop5":return current<=previous-.05
    if gate=="exhaust":return previous>=.55 and current<=.50
    if gate=="absorbed":return current>=.55
    raise ValueError("unknown_flow_gate")


def generate(original,flow):
    signals={};counts=[]
    for spec in definitions():
        rows=[];missing=0
        for r in original[f"benchmark_mask{spec['mask']}"]:
            t=pd.Timestamp(r["at"],unit="ms",tz="UTC");f=flow[r["symbol"]]
            if t in f.index:current,previous=f.loc[t,["ratio","previous_ratio"]]
            else:current,previous=np.nan,np.nan
            if not np.isfinite([current,previous]).all():missing+=1
            if accepts(current,previous,spec["gate"]):rows.append(dict(r))
        signals[spec["id"]]=rows;counts.append(dict(source_id=spec["id"],input_events=len(original[f"benchmark_mask{spec['mask']}"]),kept=len(rows),missing_flow=missing))
    return signals,counts
