"""4h USD-M perpetual panel (2020-01 .. 2026-08) for the no-stop-loss research.

Sources (all read-only, shared data lake):
* 2020-2025: ``development_broad_4h_2020_2025/prices_4h.parquet`` (117 symbols)
* 2026:      ``klines/5m/<sym>.parquet`` resampled to 4h (same symbols)
* funding:   ``funding/<sym>_funding.parquet`` (8h settlements 00/08/16 UTC)

Known limitation: the symbol list is the set alive at end-2025 (survivorship
bias; delisted perpetuals are absent).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

LAKE = Path("C:/Quant-trading/data_lake")
ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "artifacts" / "nostop"
PANEL_PATH = OUT_DIR / "panel_4h.npz"
META_PATH = OUT_DIR / "panel_4h_meta.json"

BARS_PER_DAY = 6
EXCLUDE = {"USDCUSDT"}
FIELDS = ("open", "high", "low", "close", "qvol", "taker")


@dataclass
class Panel:
    index: pd.DatetimeIndex  # bar open times (UTC), 4h grid
    symbols: list[str]
    open: np.ndarray  # (T, N), NaN where symbol not trading
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    qvol: np.ndarray  # quote volume per bar
    taker: np.ndarray  # taker-buy base volume per bar (NaN-safe 0)
    volume: np.ndarray  # base volume per bar
    funding: np.ndarray  # rate settled at the START of bar k (00/08/16 UTC), else 0

    @property
    def shape(self) -> tuple[int, int]:
        return self.close.shape

    def sym_idx(self, sym: str) -> int:
        return self.symbols.index(sym)


def _resample_5m(sym: str, start: pd.Timestamp) -> pd.DataFrame | None:
    df = pd.read_parquet(
        LAKE / "klines" / "5m" / f"{sym}.parquet",
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_volume",
            "taker_buy_volume",
        ],
    )
    df = df[df.open_time >= start].set_index("open_time").sort_index()
    if df.empty:
        return None
    g = df.resample("4h", label="left", closed="left")
    out = pd.DataFrame(
        {
            "open": g.open.first(),
            "high": g.high.max(),
            "low": g.low.min(),
            "close": g.close.last(),
            "volume": g.volume.sum(),
            "quote_volume": g.quote_volume.sum(),
            "taker_buy_volume": g.taker_buy_volume.sum(),
            "n5": g.open.count(),
        }
    )
    # only complete 4h bars (48 five-minute candles)
    return out[out.n5 == 48].drop(columns="n5")


def build_panel() -> Panel:
    base = pd.read_parquet(LAKE / "development_broad_4h_2020_2025" / "prices_4h.parquet")
    base = base[~base.symbol.isin(EXCLUDE)]
    symbols = sorted(base.symbol.unique())
    base_end = base.timestamp.max()
    start26 = base_end + pd.Timedelta("4h")

    frames = []
    for sym in symbols:
        b = base[base.symbol == sym].set_index("timestamp").sort_index()
        b = b[["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_volume"]]
        ext = _resample_5m(sym, start26)
        if ext is not None:
            b = pd.concat([b, ext])
        b = b[~b.index.duplicated(keep="first")]
        b["symbol"] = sym
        frames.append(b)
    allb = pd.concat(frames)
    idx = pd.date_range(
        allb.index.min().floor("4h"), allb.index.max(), freq="4h", tz="UTC"
    )
    arrays = {}
    for name, col in (
        ("open", "open"),
        ("high", "high"),
        ("low", "low"),
        ("close", "close"),
        ("volume", "volume"),
        ("qvol", "quote_volume"),
        ("taker", "taker_buy_volume"),
    ):
        pv = allb.pivot(columns="symbol", values=col).reindex(index=idx, columns=symbols)
        arrays[name] = pv.to_numpy(dtype=np.float64)

    fund = np.zeros((len(idx), len(symbols)))
    missing_symbols = []
    for j, sym in enumerate(symbols):
        path = LAKE / "funding" / f"{sym}_funding.parquet"
        if not path.exists():
            missing_symbols.append(sym)
            continue
        f = pd.read_parquet(path, columns=["funding_time", "funding_rate"])
        t = f.funding_time.dt.floor("4h")
        s = pd.Series(f.funding_rate.to_numpy(dtype=float), index=t)
        s = s[~s.index.duplicated(keep="last")]
        s = s.reindex(idx).fillna(0.0)
        fund[:, j] = s.to_numpy()

    panel = Panel(
        index=idx,
        symbols=symbols,
        open=arrays["open"],
        high=arrays["high"],
        low=arrays["low"],
        close=arrays["close"],
        qvol=arrays["qvol"],
        taker=arrays["taker"],
        volume=arrays["volume"],
        funding=fund,
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        PANEL_PATH,
        index=idx.as_unit("ns").asi8,
        symbols=np.array(symbols),
        **{k: getattr(panel, k) for k in ("open", "high", "low", "close", "qvol", "taker", "volume", "funding")},
    )
    META_PATH.write_text(
        json.dumps(
            {
                "bars": len(idx),
                "symbols": len(symbols),
                "start": str(idx[0]),
                "end": str(idx[-1]),
                "funding_missing_symbols": missing_symbols,
                "survivorship_bias": True,
            },
            indent=2,
        )
    )
    return panel


def load_panel() -> Panel:
    z = np.load(PANEL_PATH, allow_pickle=False)
    idx = pd.DatetimeIndex(pd.to_datetime(z["index"], unit="ns", utc=True))
    return Panel(
        index=idx,
        symbols=[str(s) for s in z["symbols"]],
        open=z["open"],
        high=z["high"],
        low=z["low"],
        close=z["close"],
        qvol=z["qvol"],
        taker=z["taker"],
        volume=z["volume"],
        funding=z["funding"],
    )


if __name__ == "__main__":
    p = build_panel()
    print(p.index[0], p.index[-1], p.shape)
