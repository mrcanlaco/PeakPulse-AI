"""Explain legacy readiness flags without altering any saved replay or lock."""

import copy
import json
import numpy as np
import pandas as pd
from compare_account_risk import sha,write
from frozen_extension_inputs import load
from short_entry_guards import features
from search_retest_entries import OUT,select


def main():
    original=json.loads((OUT/"summary.json").read_text(encoding="utf-8"))
    before=sha(OUT/"summary.json");_,funding,frames=load();enriched=features(frames,funding)
    findings=[];affected=set()
    for path in sorted((OUT/"entries").glob("*.json")):
        entry=json.loads(path.read_text(encoding="utf-8"))
        if entry["data_complete"]:continue
        assert not entry["watch"]["counts"].get("missing_data",0)
        problematic=[r for r in entry["observations"] if r["status"]!="observed"]
        assert problematic
        for r in problematic:
            assert r["status"]=="stale_features"
            at=pd.Timestamp(r["at"],unit="ms",tz="UTC");history=frames[r["symbol"]].loc[:at]
            stamp=history.index[-1];h=history.iloc[-1];f=enriched[r["symbol"]].loc[stamp]
            assert 0<=(at-stamp).total_seconds()<3600
            assert len(history)>=120 and history.tail(120).bars.eq(12).all()
            assert np.isfinite(h.atr) and h.atr>0 and 0<=h.volume24<2_000_000 and not h.ready
            assert all(np.isfinite(f[k]) for k in ["ret24","ret6","funding24","atr","close"])
            findings.append(dict(file=path.name,sha256=sha(path),event_id=r["event_id"],symbol=r["symbol"],trigger_at=r["at"],
                feature_at=int(stamp.timestamp()*1000),volume24=float(h.volume24),last120hours_complete=True,features_finite=True,
                cause="liquidity_below_2m_USDT_not_missing_or_stale_price"))
        affected.add(path.stem)
    hypothetical=copy.deepcopy(original)
    for r in hypothetical["results"]:
        if f"{r['window']}_mask{r['mask']:02d}_{r['timing']['id']}" in affected:r["data_complete"]=True
    after_selection=select(hypothetical["specs"],hypothetical["results"])
    assert after_selection==original["selected"]
    assert sha(OUT/"summary.json")==before
    write(OUT/"readiness_diagnosis.json",dict(summary_sha256=before,original_files_unchanged=True,records=findings,
        unique_source_events=len({r["event_id"] for r in findings}),affected_entry_files=len(affected),affected_account_paths=original["data_incomplete_paths"],
        actual_missing_price_or_feature_cases=0,liquidity_rejection_preserved=True,selection_unchanged_if_reclassified=True,
        explanation="Legacy ready combines complete data, positiveATR and24hvolume>=2m. Its stale_features label conflates liquidity rejection with data problems. All flagged cases here have complete fresh finite data but volume belowthreshold. No fills, balances, filters or candidate locks were changed."))
    print("DIAGNOSED",len(findings),"records; selection unchanged",flush=True)


if __name__=="__main__":main()
