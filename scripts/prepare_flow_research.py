"""Audit base-unit taker buy volume and retain weighted hourly flow inputs."""

import json

import httpx
import numpy as np
import pandas as pd
from compare_account_risk import ROOT, sha, write
from prepare_historical_research import END, LAKE, OUT as DATA, START, archive, ms

OUT = ROOT / "artifacts/funding_flow_search_20260925"


def hourly_flow(raw):
    indexed = raw.set_index("open_time")
    result = indexed.resample("1h", closed="left", label="right").agg(
        volume=("volume", "sum"), taker_buy_volume=("taker_buy_volume", "sum"),
        bars=("volume", "count"))
    valid = result.bars.eq(12) & result.volume.gt(0)
    result.loc[~valid, ["volume", "taker_buy_volume"]] = np.nan
    result["buy_fraction1"] = result.taker_buy_volume / result.volume
    result["buy_fraction6"] = (result.taker_buy_volume.rolling(6, min_periods=6).sum()
                                / result.volume.rolling(6, min_periods=6).sum())
    return result


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "flow").mkdir(exist_ok=True)
    prior = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    symbols = prior["universe"]["symbols"]
    audits = []
    for symbol in symbols:
        source = LAKE / f"{symbol}.parquet"
        expected = next(r["source_sha256"] for r in prior["local"] if r["symbol"]==symbol)
        if sha(source) != expected:
            raise ValueError("Source changed since historical preparation: " + symbol)
        raw = pd.read_parquet(source, columns=["open_time", "volume", "taker_buy_volume"])
        raw.open_time = pd.to_datetime(raw.open_time, utc=True)
        raw = raw[(raw.open_time >= START) & (raw.open_time < END)].sort_values("open_time")
        values = raw[["volume", "taker_buy_volume"]].to_numpy(dtype=float)
        sane = bool(np.isfinite(values).all() and (values>=0).all() and
                    (raw.taker_buy_volume <= raw.volume + 1e-8).all())
        assert sane and not raw.open_time.duplicated().any()
        local = raw.assign(open_time=ms(raw.open_time))
        checks = []
        with httpx.Client(timeout=45, follow_redirects=True) as client:
            for month in ["2025-09", "2025-12", "2026-03"]:
                public, evidence = archive(client, symbol, month, "klines")
                stamps = public.open_time.astype("int64")
                public["open_time"] = stamps//1000 if stamps.max()>10**14 else stamps
                joined = public.merge(local, on="open_time", how="left", validate="one_to_one", suffixes=("_public", "_local"))
                missing = joined.volume_local.isna()
                differences = np.zeros(len(joined), dtype=bool)
                for field in ["volume", "taker_buy_volume"]:
                    differences |= ~np.isclose(joined[field+"_public"], joined[field+"_local"], rtol=1e-7, atol=1e-8)
                checks.append(dict(month=month, rows=len(joined), missing=int(missing.sum()),
                                   different=int((differences & ~missing).sum()), archive_sha256=evidence["sha256"]))
        result = hourly_flow(raw)
        target = OUT / "flow" / f"{symbol}.parquet"
        result.to_parquet(target)
        audits.append(dict(symbol=symbol, source_sha256=expected, flow_sha256=sha(target),
                           finite_nonnegative_and_buy_le_total=sane, checks=checks,
                           complete=sane and all(c["missing"]==0 and c["different"]==0 for c in checks)))
        print("FLOW", symbol, audits[-1]["complete"], flush=True)
    write(OUT / "flow_evidence.json", dict(audits=audits, ready=all(r["complete"] for r in audits),
        units="Volume and taker_buy_volume are base-asset units. Six-hour fraction=sum(taker buy base)/sum(total base), not mean of hourly fractions. Zero-volume and incomplete hours are missing, not neutral. No claim of signed inventory/open interest.",
        primary_documentation="https://github.com/binance/binance-public-data#klines-1",
        scope="90 public coin-month comparisons, same30 preperiod-selected coins. Other months checked for range/coherence but not independently every flow row.",
        historical_manifest_sha256=sha(DATA / "manifest.json"), source_sha256=sha(ROOT / "scripts/prepare_flow_research.py"),
        live_config_sha256=sha(ROOT / "configs/live.yaml")))


if __name__ == "__main__":
    main()
