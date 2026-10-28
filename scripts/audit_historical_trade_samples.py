"""Independent public trade-OHLC samples for every frozen historical coin."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
import numpy as np
import pandas as pd
from compare_account_risk import write
from prepare_historical_research import OUT, archive


def check(symbol):
    local = pd.read_parquet(OUT / "trade" / f"{symbol}.parquet")
    checks = []
    with httpx.Client(timeout=45, follow_redirects=True) as client:
        for month in ["2025-09", "2025-12", "2026-03"]:
            public, proof = archive(client, symbol, month, "klines")
            stamps = public.open_time.astype("int64")
            public["open_time"] = stamps // 1000 if stamps.max() > 10**14 else stamps
            joined = public.merge(local, on="open_time", how="left", validate="one_to_one", suffixes=("_public", "_local"))
            missing = joined.close_local.isna()
            different = np.zeros(len(joined), dtype=bool)
            for field in ["open", "high", "low", "close", "quote_volume"]:
                different |= ~np.isclose(joined[field + "_public"], joined[field + "_local"], rtol=1e-7, atol=1e-10)
            checks.append(dict(symbol=symbol, month=month, evidence=proof, public_rows=len(public),
                               missing_rows=int(missing.sum()), differing_rows=int((different & ~missing).sum())))
    return checks


def main():
    universe = json.loads((OUT / "universe.json").read_text(encoding="utf-8"))["symbols"]
    checks, errors = [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(check,s):s for s in universe}
        for future in as_completed(jobs):
            try:
                rows = future.result()
                checks.extend(rows)
                print("TRADE AUDIT", jobs[future], sum(r["differing_rows"]+r["missing_rows"] for r in rows), flush=True)
            except Exception as exc:
                errors.append(dict(symbol=jobs[future], error=str(exc)))
    write(OUT / "trade_sample_audit.json", dict(checks=checks, errors=errors,
        complete=not errors and all(r["missing_rows"]==0 and r["differing_rows"]==0 for r in checks),
        limits="OHLC and quote-volume spotchecks: three predeclared months per selected coin, not every local bar or delisted-universe proof."))
    print("COMPLETE", len(checks), "months", len(errors), "errors", flush=True)


if __name__ == "__main__":
    main()
