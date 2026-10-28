"""Provider-complete funding windows with cached raw evidence and checksums."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dao_vang.data.collectors.binance_client import BinanceClient

from .contracts import canonical, digest, utc_now


@dataclass(frozen=True)
class Funding:
    timestamp: datetime
    rate: float
    mark_price: float


def funding_window(
    path: Path, symbol: str, start: datetime, end: datetime, *, client=None
):
    if start.tzinfo is None or end.tzinfo is None or start > end or end > utc_now():
        raise ValueError("invalid_funding_window")
    first, last = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    try:
        db.execute(
            "CREATE TABLE IF NOT EXISTS windows(symbol TEXT,start INTEGER,end INTEGER,payload TEXT,checksum TEXT, PRIMARY KEY(symbol,start,end))"
        )
        cached = db.execute(
            "SELECT payload,checksum FROM windows WHERE symbol=? AND start<=? AND end>=? ORDER BY end-start LIMIT 1",
            (symbol, first, last),
        ).fetchone()
        if cached:
            payload = json.loads(cached[0])
            if digest(payload) != cached[1]:
                raise ValueError("funding_checksum_mismatch")
        else:
            client = client or BinanceClient(timeout_seconds=5, max_retries=0)
            cursor, rows = first, []
            while cursor <= last:
                page = client.get(
                    "/fapi/v1/fundingRate",
                    {
                        "symbol": symbol,
                        "startTime": cursor,
                        "endTime": last,
                        "limit": 1000,
                    },
                )
                if not isinstance(page, list):
                    raise ValueError("funding_response_invalid")
                seen = cursor - 1
                for row in page:
                    at = int(row["fundingTime"])
                    if (
                        row["symbol"] != symbol
                        or not cursor <= at <= last
                        or at <= seen
                    ):
                        raise ValueError("funding_order_or_window_invalid")
                    if (
                        not math.isfinite(float(row["fundingRate"]))
                        or not math.isfinite(float(row["markPrice"]))
                        or float(row["markPrice"]) <= 0
                    ):
                        raise ValueError("funding_value_invalid")
                    seen = at
                rows.extend(page)
                if len(page) < 1000:
                    break
                cursor = seen + 1
            payload = {
                "symbol": symbol,
                "start": first,
                "end": last,
                "retrieved_at": utc_now().isoformat(),
                "rows": rows,
                "source": "binance_fundingRate_complete_pagination",
            }
            db.execute(
                "INSERT OR REPLACE INTO windows VALUES (?,?,?,?,?)",
                (symbol, first, last, canonical(payload), digest(payload)),
            )
            db.commit()
        selected = [
            r for r in payload["rows"] if first <= int(r["fundingTime"]) <= last
        ]
        funding = [
            Funding(
                datetime.fromtimestamp(int(r["fundingTime"]) / 1000, timezone.utc),
                float(r["fundingRate"]),
                float(r["markPrice"]),
            )
            for r in selected
        ]
        return funding, end, digest(payload)
    finally:
        db.close()
