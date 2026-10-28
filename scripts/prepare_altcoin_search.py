"""Freeze a pre-period liquidity universe, then obtain public replay inputs."""

from __future__ import annotations

import json

import duckdb
import pandas as pd
from compare_account_risk import ROOT, exchange_rules, load_inputs, sha, write

OUT = ROOT / "artifacts/altcoin_short_search_20260925"
SOURCE = ROOT / "artifacts/account_backtest_20260924_3m/warehouse"
RULE_PATH = ROOT / "artifacts/annual_execution_20260918/exchange_info_current.json"


def main():
    OUT.mkdir(exist_ok=True)
    cache = OUT / "cache"
    cache.mkdir(exist_ok=True)
    db = duckdb.connect(str(SOURCE / "working.duckdb"), read_only=True)
    db.execute("SET timezone='UTC'")
    raw = json.loads(RULE_PATH.read_text(encoding="utf-8"))
    allowed = {
        s["symbol"]
        for s in raw["symbols"]
        if s["contractType"] == "PERPETUAL"
        and s["marginAsset"] == "USDT"
        and s.get("underlyingType") == "COIN"
        and s["status"] == "TRADING"
        and s["baseAsset"] not in ["BTC", "ETH", "USDC", "USDE", "TUSD", "FDUSD", "DAI"]
    }
    ranked = db.execute("""SELECT symbol,sum(quote_volume)/7 daily_quote_volume,count(*) bars
        FROM prices WHERE open_time>='2026-06-17T00:00:00Z' AND open_time<'2026-06-24T00:00:00Z'
        GROUP BY symbol HAVING count(*)=2016 AND sum(quote_volume)/7>=2000000
        ORDER BY daily_quote_volume DESC,symbol""").df()
    ranked = ranked[ranked.symbol.isin(allowed)].head(30)
    assert len(ranked) == 30
    symbols = ranked.symbol.tolist()
    protocol = dict(
        created_at=pd.Timestamp.now(tz="UTC").isoformat(),
        symbols=symbols,
        universe_rule="Top 30 crypto altcoin USDT perpetuals by June17-23 UTC quote volume, all 2016 preperiod 5m bars, average >=2m USDT/day. Exclude BTC,ETH and named stablecoins, TradFi. Current exchange listing/filter snapshot is a survivorship limitation; no exclusions by future return, no AKE blacklist.",
        ranked=ranked.to_dict("records"),
        rules_sha256=sha(RULE_PATH),
        live_config_sha256=sha(ROOT / "configs/live.yaml"),
        source_db=str(SOURCE / "working.duckdb"),
        periods=dict(
            development=["2026-06-24", "2026-07-24"],
            validation=["2026-07-24", "2026-08-24"],
            holdout=["2026-08-24", "2026-09-24"],
        ),
        caveat="Already inspected market history; these new rule-based signals do not use the old frozen ML model. Calendar separation is not pristine independent data. No live qualification.",
    )
    write(OUT / "universe.json", protocol)
    db.close()
    print("FROZEN UNIVERSE", symbols, flush=True)
    signals = [dict(symbol=s) for s in symbols]
    quotes, funding, failures = load_inputs(
        SOURCE,
        cache,
        signals,
        pd.Timestamp("2026-06-24T00:00:00Z"),
        pd.Timestamp("2026-09-24T00:00:00Z"),
        exchange_rules(RULE_PATH),
    )
    if failures:
        raise ValueError(f"Public data preparation failed: {failures}")
    print("READY", len(quotes), "symbols", flush=True)


if __name__ == "__main__":
    main()
