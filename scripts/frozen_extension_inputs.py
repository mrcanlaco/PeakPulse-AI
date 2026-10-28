"""Combine verified old and new records without changing the frozen universe."""

import json

import pandas as pd
from altcoin_short_signals import hourly_features
from compare_account_risk import sha
from historical_research_inputs import QuoteSeries
from prepare_frozen_extension import OUT,FREEZE
from prepare_historical_research import OUT as OLD


def join_funding(old,new):
    combined=pd.concat([old,new],ignore_index=True)
    for _,group in combined.groupby("fundingTime"):
        if len(group)>1 and (group.fundingRate.nunique()!=1 or group.markPrice.nunique()!=1):raise ValueError("conflicting_funding_boundary")
    return combined.drop_duplicates("fundingTime").sort_values("fundingTime")


def load():
    freeze=json.loads(FREEZE.read_text(encoding="utf-8"));old=json.loads((OLD/"manifest.json").read_text(encoding="utf-8"))
    manifest=json.loads((OUT/"reconciled_manifest.json").read_text(encoding="utf-8"))
    assert manifest["data_ready"] and old["data_ready"]
    assert sha(FREEZE)==manifest["protocol"]["candidate_sha256"]
    assert sha(OLD/"manifest.json")==freeze["original_universe_manifest_sha256"]
    local={r["symbol"]:r for r in old["local"]};public={r["symbol"]:r for r in old["public"]};fresh={r["symbol"]:r for r in manifest["proof"]}
    frames={};prices={};funding={}
    for coin in [*old["universe"]["symbols"],"BTCUSDT"]:
        a=OLD/"trade"/f"{coin}.parquet";b=OUT/"trade"/f"{coin}.parquet"
        assert sha(a)==local[coin]["trade_sha256"] and sha(b)==fresh[coin]["trade_sha256"]
        trade=pd.concat([pd.read_parquet(a),pd.read_parquet(b)],ignore_index=True)
        if trade.open_time.duplicated().any() or not trade.open_time.is_monotonic_increasing:raise ValueError("ambiguous_trade_boundary")
        raw=trade.copy();raw.open_time=pd.to_datetime(raw.open_time,unit="ms",utc=True);frames[coin]=hourly_features(raw)
        if coin=="BTCUSDT":continue
        a=OLD/"mark"/f"{coin}.parquet";b=OUT/"reconciled/mark"/f"{coin}.parquet"
        assert sha(a)==public[coin]["mark_sha256"] and sha(b)==fresh[coin]["mark_sha256"]
        mark=pd.concat([pd.read_parquet(a),pd.read_parquet(b)],ignore_index=True)
        prices[coin]=QuoteSeries(trade,mark)
        a=OLD/"funding"/f"{coin}.parquet";b=OUT/"funding"/f"{coin}.parquet"
        assert sha(a)==public[coin]["funding_sha256"] and sha(b)==fresh[coin]["funding_sha256"]
        rows=join_funding(pd.read_parquet(a),pd.read_parquet(b))
        funding[coin]=[(int(t),float(r),float(m)) for t,r,m in rows.itertuples(index=False,name=None)]
    return prices,funding,frames
