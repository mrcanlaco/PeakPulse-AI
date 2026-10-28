"""Freeze an August-2025 universe and verify public historical replay inputs.

Public endpoints only. Resumable archives, no credential/config loading.
"""

from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import duckdb
import httpx
import numpy as np
import pandas as pd
from altcoin_short_signals import hourly_features
from compare_account_risk import ROOT, sha, write
from prepare_altcoin_search import RULE_PATH

OUT = ROOT / "artifacts/monthly_target_history_20260925"
LAKE = Path("D:/Quant-trading/data_lake/klines/5m")
START = pd.Timestamp("2025-08-01", tz="UTC")
END = pd.Timestamp("2026-06-01", tz="UTC")
MONTHS = pd.date_range(START, END, freq="MS", inclusive="left").strftime("%Y-%m").tolist()
STEP = 300000


def ms(values):
    return pd.to_datetime(values, utc=True).dt.as_unit("ms").astype("int64")


def grid_audit(frame, start=START, end=END):
    expected = np.arange(int(start.timestamp()*1000), int(end.timestamp()*1000), STEP)
    stamps = frame.open_time.to_numpy(dtype=np.int64)
    values = frame[["open", "high", "low", "close"]].to_numpy(dtype=float)
    positive = bool(np.isfinite(values).all() and (values > 0).all())
    coherent = bool(((frame.low <= frame[["open", "close"]].min(axis=1)) &
                     (frame.high >= frame[["open", "close"]].max(axis=1))).all())
    result = dict(rows=len(frame), expected=len(expected),
                  missing=int(len(np.setdiff1d(expected, stamps))),
                  off_grid=int(len(np.setdiff1d(stamps, expected))),
                  duplicates=int(frame.open_time.duplicated().sum()),
                  finite_positive_ohlc=positive, coherent_ohlc=coherent)
    result["complete"] = not any(result[k] for k in ["missing", "off_grid", "duplicates"]) and positive and coherent
    return result


def get(client, url, **kwargs):
    for attempt in range(5):
        try:
            response = client.get(url, **kwargs)
            if response.status_code in [429, 418]:
                delay = float(response.headers.get("Retry-After", 60))
                if delay > 120 or response.status_code == 418:
                    raise RuntimeError("public_endpoint_rate_limit_stop")
                time.sleep(max(delay, 2))
                continue
            response.raise_for_status()
            return response
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                raise
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("public_endpoint_retry_exhausted")


def archive(client, symbol, month, kind):
    if kind == "fundingRate":
        tail = f"fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip"
    else:
        tail = f"{kind}/{symbol}/5m/{symbol}-5m-{month}.zip"
    url = "https://data.binance.vision/data/futures/um/monthly/" + tail
    folder = OUT / "archives" / kind / symbol
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / url.rsplit("/", 1)[-1]
    checksum = path.with_suffix(".zip.CHECKSUM")
    if not checksum.exists():
        checksum.write_text(get(client, url + ".CHECKSUM").text, encoding="utf-8")
    expected = checksum.read_text(encoding="utf-8").split()[0].lower()
    if not path.exists():
        data = get(client, url).content
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("archive_checksum_mismatch:" + tail)
        temporary = path.with_suffix(".zip.partial")
        temporary.write_bytes(data)
        temporary.replace(path)
    if sha(path) != expected:
        raise ValueError("cached_archive_checksum_mismatch:" + tail)
    with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as z:
        if len(z.namelist()) != 1:
            raise ValueError("archive_members")
        frame = pd.read_csv(z.open(z.namelist()[0]))
    return frame, dict(url=url, sha256=expected, checksum_verified=True, file=str(path))


def freeze_universe():
    path = OUT / "universe.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    db = duckdb.connect()
    db.execute("SET threads=4")
    ranked = db.execute("""
        SELECT symbol,count(*) bars,count(distinct open_time) unique_bars,
          sum(quote_volume)/31 daily_quote_volume,
          count(*) FILTER(WHERE epoch_ms(open_time)%300000<>0) off_grid,
          count(*) FILTER(WHERE NOT isfinite(open) OR NOT isfinite(high)
             OR NOT isfinite(low) OR NOT isfinite(close) OR low<=0
             OR low>least(open,close) OR high<greatest(open,close)
             OR NOT isfinite(quote_volume) OR quote_volume<0) invalid_rows
        FROM read_parquet(?,union_by_name=true)
        WHERE open_time>=TIMESTAMPTZ '2025-08-01'
          AND open_time<TIMESTAMPTZ '2025-09-01'
        GROUP BY symbol ORDER BY daily_quote_volume DESC,symbol
    """, [str(LAKE / "*.parquet")]).df()
    db.close()
    excluded = {"BTCUSDT", "ETHUSDT", "USDCUSDT", "USDEUSDT", "TUSDUSDT",
                "FDUSDUSDT", "DAIUSDT", "BUSDUSDT", "XAUUSDT", "XAGUSDT",
                "PAXGUSDT", "XAUTUSDT", "TSLAUSDT", "AAPLUSDT", "NVDAUSDT"}
    ranked["eligible"] = (ranked.bars.eq(8928) & ranked.unique_bars.eq(8928)
                          & ranked.off_grid.eq(0) & ranked.invalid_rows.eq(0)
                          & ranked.daily_quote_volume.ge(2_000_000)
                          & ranked.symbol.str.endswith("USDT")
                          & ~ranked.symbol.isin(excluded))
    chosen = ranked[ranked.eligible].head(30).symbol.tolist()
    assert len(chosen) == 30
    ranked.to_csv(OUT / "preperiod_ranking.csv", index=False)
    frozen = dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(), symbols=chosen,
                  preperiod=["2025-08-01", "2025-09-01"],
                  evaluation=["2025-09-01", "2026-06-01"],
                  rule="Top30 by preperiod average quote volume >=2m/day; complete, unique, aligned August5m candles. No current trading-status or future-return filter.",
                  explicit_exclusions=sorted(excluded), available_files=len(list(LAKE.glob("*.parquet"))),
                  ranking_sha256=sha(OUT / "preperiod_ranking.csv"),
                  limitations="Local warehouse may omit delisted contracts. Historical contract identity, filters and maintenance tiers remain unverified; calendar split is not pristine unseen history.",
                  live_config_sha256=sha(ROOT / "configs/live.yaml"))
    write(path, frozen)
    return frozen


def prepare_local(symbol):
    source = LAKE / f"{symbol}.parquet"
    raw = pd.read_parquet(source)
    raw.open_time = pd.to_datetime(raw.open_time, utc=True)
    raw = raw[(raw.open_time >= START) & (raw.open_time < END)].sort_values("open_time")
    trade = raw[["open_time", "open", "high", "low", "close", "quote_volume"]].copy()
    trade.open_time = ms(trade.open_time)
    audit = grid_audit(trade)
    # Never silently deduplicate, forward-fill or drop a selected coin.
    if audit["duplicates"] or audit["off_grid"]:
        raise ValueError("ambiguous_local_timestamps:" + symbol)
    features = hourly_features(raw)
    if "taker_buy_volume" in raw and "volume" in raw:
        flow = raw.set_index("open_time").resample("1h", closed="left", label="right").agg(
            taker_buy_volume=("taker_buy_volume", "sum"), volume=("volume", "sum"))
        features["taker_buy_fraction"] = (flow.taker_buy_volume / flow.volume.replace(0, np.nan)).where(features.bars.eq(12))
    trade.to_parquet(OUT / "trade" / f"{symbol}.parquet", index=False)
    features.to_parquet(OUT / "features" / f"{symbol}.parquet")
    return dict(symbol=symbol, source=str(source), source_sha256=sha(source),
                trade_sha256=sha(OUT / "trade" / f"{symbol}.parquet"),
                features_sha256=sha(OUT / "features" / f"{symbol}.parquet"), **audit)


def prepare_public(symbol):
    marks, rates, evidence = [], [], []
    with httpx.Client(timeout=45, follow_redirects=True) as client:
        for month in MONTHS:
            mark, proof = archive(client, symbol, month, "markPriceKlines")
            stamp = mark.open_time.astype("int64")
            mark["open_time"] = stamp // 1000 if stamp.max() > 10**14 else stamp
            marks.append(mark[["open_time", "open", "high", "low", "close"]])
            evidence.append(proof)
            rate, proof = archive(client, symbol, month, "fundingRate")
            rates.append(rate)
            evidence.append(proof)
        rest_path = OUT / "funding" / f"{symbol}_rest.json"
        if rest_path.exists():
            saved = json.loads(rest_path.read_text(encoding="utf-8"))
            if saved["period"] != [START.isoformat(), END.isoformat()]:
                raise ValueError("rest_cache_period_mismatch")
            rows = saved["rows"]
        else:
            rows, pages = [], []
            cursor, finish = int(START.timestamp()*1000), int(END.timestamp()*1000)
            while cursor <= finish:
                params = dict(symbol=symbol, startTime=cursor, endTime=finish, limit=1000)
                response = get(client, "https://fapi.binance.com/fapi/v1/fundingRate", params=params)
                page = response.json()
                if not isinstance(page, list):
                    raise ValueError("invalid_funding_response")
                pages.append(dict(params=params, rows=len(page), response_sha256=hashlib.sha256(response.content).hexdigest()))
                if not page:
                    break
                if any(r["symbol"] != symbol or not cursor <= r["fundingTime"] <= finish for r in page):
                    raise ValueError("funding_response_outside_requested_range")
                rows.extend(page)
                cursor = max(r["fundingTime"] for r in page) + 1
                if len(page) < 1000:
                    break
                time.sleep(0.25)
            write(rest_path, dict(source="https://fapi.binance.com/fapi/v1/fundingRate",
                                 retrieved_at=pd.Timestamp.now(tz="UTC").isoformat(),
                                 period=[START.isoformat(), END.isoformat()], pages=pages, rows=rows))
    mark = pd.concat(marks, ignore_index=True).sort_values("open_time")
    mark_audit = grid_audit(mark)
    mark.to_parquet(OUT / "mark" / f"{symbol}.parquet", index=False)
    public = pd.concat(rates, ignore_index=True)
    public["second"] = public.calc_time.astype("int64") // 1000
    rest = pd.DataFrame(rows)
    if rest.empty:
        raise ValueError("empty_funding_history:" + symbol)
    rest["second"] = rest.fundingTime.astype("int64") // 1000
    rest["fundingRate"] = rest.fundingRate.astype(float)
    rest["markPrice"] = pd.to_numeric(rest.markPrice, errors="coerce")
    rest_in = rest[rest.fundingTime < int(END.timestamp()*1000)]
    merged = public.merge(rest_in, on="second", how="outer", validate="one_to_one", indicator=True)
    unmatched = int(merged._merge.ne("both").sum())
    different = int(((merged.last_funding_rate - merged.fundingRate).abs() > 1e-10).sum())
    good_mark = bool(np.isfinite(rest.markPrice).all() and rest.markPrice.gt(0).all())
    valid_rates = bool(np.isfinite(rest.fundingRate).all())
    intervals = public.funding_interval_hours.to_numpy(dtype=float)
    # Archive row cadence, including variable funding intervals, is recorded for review.
    funding_audit = dict(archive_rows=len(public), rest_rows=len(rest), unmatched_rows=unmatched,
                         differing_rates=different, settlement_marks_valid=good_mark,
                         finite_rates=valid_rates, interval_hours=sorted(set(intervals.tolist())),
                         max_gap_hours=float(np.diff(np.sort(rest.fundingTime)).max()/3600000) if len(rest)>1 else None,
                         matching="Second-floor one-to-one comparison only; actual REST millisecond settlement timestamps preserved.",
                         complete=unmatched == 0 and different == 0 and good_mark and valid_rates)
    rest[["fundingTime", "fundingRate", "markPrice"]].sort_values("fundingTime").to_parquet(OUT / "funding" / f"{symbol}.parquet", index=False)
    proof = dict(symbol=symbol, mark=mark_audit, funding=funding_audit, archives=evidence,
                 rest_sha256=sha(rest_path), mark_sha256=sha(OUT / "mark" / f"{symbol}.parquet"),
                 funding_sha256=sha(OUT / "funding" / f"{symbol}.parquet"),
                 complete=mark_audit["complete"] and funding_audit["complete"])
    write(OUT / "evidence" / f"{symbol}.json", proof)
    return proof


def main():
    OUT.mkdir(exist_ok=True)
    for directory in ["trade", "mark", "funding", "features", "evidence"]:
        (OUT / directory).mkdir(exist_ok=True)
    universe = freeze_universe()
    print("FROZEN", universe["symbols"], flush=True)
    local = [prepare_local(s) for s in [*universe["symbols"], "BTCUSDT"]]
    write(OUT / "local_evidence.json", local)
    print("LOCAL", sum(r["complete"] for r in local), "/", len(local), flush=True)
    public, errors = [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(prepare_public, s): s for s in universe["symbols"]}
        for future in as_completed(jobs):
            symbol = jobs[future]
            try:
                proof = future.result()
                public.append(proof)
                print("PUBLIC", symbol, proof["complete"], proof["funding"], flush=True)
            except Exception as exc:
                error = dict(symbol=symbol, error=type(exc).__name__ + ": " + str(exc)[:300])
                errors.append(error)
                print("FAILED", error, flush=True)
            write(OUT / "download_progress.json", dict(finished=len(public), errors=errors, total=len(jobs)))
    snapshot = json.loads(RULE_PATH.read_text(encoding="utf-8"))
    identities = {r["symbol"]: r for r in snapshot["symbols"]}
    rules_audit = [dict(symbol=s, present=s in identities, current_status=identities.get(s, {}).get("status"),
                        current_underlying=identities.get(s, {}).get("underlyingType")) for s in universe["symbols"]]
    ready = not errors and all(r["complete"] for r in local) and all(r["complete"] for r in public)
    assert sha(ROOT / "configs/live.yaml") == universe["live_config_sha256"]
    write(OUT / "manifest.json", dict(universe=universe, local=local, public=public, errors=errors,
                                      data_ready=ready, current_rule_snapshot=rules_audit,
                                      rule_sha256=sha(RULE_PATH), live_config_unchanged=True,
                                      limitations=universe["limitations"],
                                      script_sha256=sha(Path(__file__))))
    print("COMPLETE data_ready=", ready, flush=True)


if __name__ == "__main__":
    main()
