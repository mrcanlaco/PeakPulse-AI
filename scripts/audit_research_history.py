"""Read-only long-history coverage and independent Binance archive spot checks."""

import hashlib
import io
import json
import zipfile
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from compare_account_risk import ROOT, sha, write
from search_event_horizons import OUT


def download_verified(url, folder):
    r = httpx.get(url, timeout=30)
    r.raise_for_status()
    c = httpx.get(url + ".CHECKSUM", timeout=30)
    c.raise_for_status()
    digest = hashlib.sha256(r.content).hexdigest()
    if c.text.split()[0].lower() != digest:
        raise ValueError("public_archive_checksum_mismatch")
    path = folder / url.rsplit("/", 1)[-1]
    path.write_bytes(r.content)
    path.with_suffix(path.suffix + ".CHECKSUM").write_text(c.text, encoding="utf-8")
    archive = zipfile.ZipFile(io.BytesIO(r.content))
    files = archive.namelist()
    if len(files) != 1:
        raise ValueError("unexpected_archive_members")
    frame = pd.read_csv(archive.open(files[0]))
    return frame, dict(
        url=url, sha256=digest, checksum_verified=True, saved_file=str(path)
    )


def main():
    OUT.mkdir(exist_ok=True)
    folder = OUT / "independent_archive_checks"
    folder.mkdir(exist_ok=True)
    universe = json.loads(
        (ROOT / "artifacts/altcoin_short_search_20260925/universe.json").read_text(
            encoding="utf-8"
        )
    )["symbols"]
    start, end = (
        pd.Timestamp("2025-09-01", tz="UTC"),
        pd.Timestamp("2026-06-01", tz="UTC"),
    )
    expected = int((end - start).total_seconds() / 300)
    expected_grid = pd.date_range(start, end, freq="5min", inclusive="left")
    history = []
    root = Path("D:/Quant-trading/data_lake/klines/5m")
    for coin in universe:
        p = root / f"{coin}.parquet"
        if not p.exists():
            history.append(dict(symbol=coin, available=False))
            continue
        frame = pd.read_parquet(
            p, columns=["open_time", "open", "high", "low", "close"]
        )
        window = frame[(frame.open_time >= start) & (frame.open_time < end)]
        unique = window.open_time.nunique()
        history.append(
            dict(
                symbol=coin,
                available=True,
                first=str(frame.open_time.min()),
                last=str(frame.open_time.max()),
                expected_bars=expected,
                window_unique_bars=unique,
                missing_window_bars=len(
                    expected_grid.difference(pd.DatetimeIndex(window.open_time))
                ),
                off_grid_bars=int((~window.open_time.isin(expected_grid)).sum()),
                duplicate_window_bars=len(window) - unique,
                finite_positive_ohlc=bool(
                    np.isfinite(window[["open", "high", "low", "close"]]).all().all()
                    and (window[["open", "high", "low", "close"]] > 0).all().all()
                ),
                source_file=str(p),
            )
        )
    checks = []
    for coin in ["SOLUSDT", "BNBUSDT", "1000PEPEUSDT"]:
        result = dict(symbol=coin, month="2025-09")
        try:
            url = f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{coin}/{coin}-fundingRate-2025-09.zip"
            public, evidence = download_verified(url, folder)
            local_path = (
                ROOT / f"artifacts/annual_profit_20260918/data/funding/{coin}.parquet"
            )
            local = pd.read_parquet(local_path)
            local["second"] = (
                pd.to_datetime(local.funding_time, utc=True)
                .dt.as_unit("s")
                .astype("int64")
            )
            public["second"] = public.calc_time.astype("int64") // 1000
            joined = public.merge(local, on="second", how="left", validate="one_to_one")
            missing = joined.funding_rate.isna()
            diffs = (joined.last_funding_rate - joined.funding_rate).abs()
            result["funding"] = dict(
                **evidence,
                local_sha256=sha(local_path),
                public_rows=len(public),
                missing_rows=int(missing.sum()),
                different_rates=int((diffs > 1e-10).sum()),
                max_rate_difference=float(diffs.max()) if diffs.notna().any() else None,
                timestamp_matching="Floor to seconds, one-to-one; venue millisecond jitter retained in source files.",
            )
            url = f"https://data.binance.vision/data/futures/um/monthly/klines/{coin}/5m/{coin}-5m-2025-09.zip"
            public, evidence = download_verified(url, folder)
            stamp = public.open_time.astype("int64")
            if stamp.max() > 10**14:
                stamp = stamp // 1000
            public["time_key"] = stamp
            local_path = root / f"{coin}.parquet"
            local = pd.read_parquet(
                local_path, columns=["open_time", "open", "high", "low", "close"]
            )
            local["time_key"] = (
                pd.to_datetime(local.open_time, utc=True)
                .dt.as_unit("ms")
                .astype("int64")
            )
            joined = public.merge(
                local,
                on="time_key",
                how="left",
                suffixes=("_public", "_local"),
                validate="one_to_one",
            )
            missing = joined.close_local.isna()
            different = np.zeros(len(joined), dtype=bool)
            for field in ["open", "high", "low", "close"]:
                different |= ~np.isclose(
                    joined[f"{field}_public"],
                    joined[f"{field}_local"],
                    rtol=1e-7,
                    atol=1e-12,
                )
            result["prices"] = dict(
                **evidence,
                local_sha256=sha(local_path),
                public_rows=len(public),
                missing_rows=int(missing.sum()),
                differing_ohlc_rows=int((different & ~missing).sum()),
                max_relative_close_difference=float(
                    ((joined.close_local / joined.close_public) - 1).abs().max()
                ),
            )
        except Exception as exc:
            result["error"] = type(exc).__name__ + ":" + str(exc)[:200]
        checks.append(result)
    write(
        OUT / "long_history_audit.json",
        dict(
            period=[str(start), str(end)],
            coverage=history,
            independent_checks=checks,
            limits="Sampled three symbols/one older month. Not a full audit or proof of all historical venues/funding, and not a preperiod-selected historical universe. Mark-price bars and historical maintenance tiers still require separate verification. Do not use current top30 as a hindsight-free historical selection.",
            current_live_config_sha256=sha(ROOT / "configs/live.yaml"),
        ),
    )
    print(
        "COVERAGE",
        sum(r.get("missing_window_bars") == 0 for r in history),
        "/",
        len(history),
    )
    for r in checks:
        print(
            r["symbol"],
            "funding",
            r.get("funding", {}).get("different_rates"),
            "price",
            r.get("prices", {}).get("differing_ohlc_rows"),
            "error",
            r.get("error"),
        )


if __name__ == "__main__":
    main()
