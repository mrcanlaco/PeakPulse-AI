"""Target-weight generators (no stop-loss) for the 4h perpetual panel.

Every generator returns ``(W, reb)``:
    W   (T, N)  target weights (fraction of equity, signed), decided at close of bar t
    reb (T,)    True where a decision is taken (executed at open of t+1)
NaN in W on a rebalance row means "leave that position untouched" (used by the
event families which hold for a fixed horizon).

Causality: row t only uses data with index <= t (shifts/rolling windows only look
back).  ``tests/unit/nostop`` truncates the panel and checks W is unchanged.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .data import BARS_PER_DAY, Panel

ANN = BARS_PER_DAY * 365.25  # 4h bars per year
MIN_AGE = 90 * BARS_PER_DAY
MIN_NAMES = 8


def _shift(a: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(a, np.nan)
    if n <= 0:
        return a.copy()
    out[n:] = a[:-n]
    return out


class Ctx:
    """Feature cache shared by all strategy builds on one panel."""

    def __init__(self, panel: Panel):
        self.p = panel
        self.T, self.N = panel.shape
        self.close = panel.close
        self.open = panel.open
        self.sym = {s: i for i, s in enumerate(panel.symbols)}
        self.btc = self.sym["BTCUSDT"]
        self.eth = self.sym["ETHUSDT"]
        self._c: dict = {}
        r1 = self.close / _shift(self.close, 1) - 1.0
        self.r1 = r1
        self.r1z = np.nan_to_num(r1)
        self.age = np.cumsum(np.isfinite(self.close), axis=0)
        qv = pd.DataFrame(panel.qvol).rolling(30 * BARS_PER_DAY, min_periods=BARS_PER_DAY).mean()
        self.qv30 = qv.to_numpy()
        self.liq_rank = qv.rank(axis=1, ascending=False).to_numpy()
        hour = panel.index.hour
        self.day_end = hour == 20  # close of the day's last 4h bar
        self.day_no = panel.index.normalize().as_unit("ns").asi8 // 86_400_000_000_000
        self.dow = panel.index.dayofweek.to_numpy()

    # ---- cached features -------------------------------------------------
    _CACHE_MAX = 24

    def _get(self, key, fn):
        c = self._c
        if key in c:
            c[key] = c.pop(key)  # LRU touch
            return c[key]
        val = fn()
        c[key] = val
        while len(c) > self._CACHE_MAX:
            c.pop(next(iter(c)))
        return val

    def ret(self, days: float, skip: float = 0.0) -> np.ndarray:
        n, s = int(days * BARS_PER_DAY), int(skip * BARS_PER_DAY)
        return self._get(
            ("ret", n, s), lambda: _shift(self.close, s) / _shift(self.close, s + n) - 1.0
        )

    def vol(self, days: float) -> np.ndarray:
        n = int(days * BARS_PER_DAY)
        return self._get(
            ("vol", n),
            lambda: pd.DataFrame(self.r1).rolling(n, min_periods=max(n // 2, 6)).std().to_numpy()
            * math.sqrt(ANN),
        )

    def sma(self, days: float) -> np.ndarray:
        n = int(days * BARS_PER_DAY)
        return self._get(
            ("sma", n),
            lambda: pd.DataFrame(self.close).rolling(n, min_periods=n).mean().to_numpy(),
        )

    def ema(self, days: float) -> np.ndarray:
        n = int(days * BARS_PER_DAY)
        return self._get(
            ("ema", n),
            lambda: pd.DataFrame(self.close).ewm(span=n, adjust=False, min_periods=n).mean().to_numpy(),
        )

    def rolling_mean(self, a: np.ndarray, days: float, key: str) -> np.ndarray:
        n = int(days * BARS_PER_DAY)
        return self._get(
            (key, n),
            lambda: pd.DataFrame(a).rolling(n, min_periods=max(n // 2, 1)).mean().to_numpy(),
        )

    def universe(self, k: int) -> np.ndarray:
        def f():
            return (self.age >= MIN_AGE) & (self.liq_rank <= k) & np.isfinite(self.close)

        return self._get(("uni", k), f)

    def reb_mask(self, every_days: float, offset: int = 0) -> np.ndarray:
        if every_days < 1:
            nb = max(int(round(every_days * BARS_PER_DAY)), 1)
            m = (np.arange(self.T) % nb) == (nb - 1)
        else:
            ed = int(every_days)
            m = self.day_end & ((self.day_no % ed) == (offset % ed))
        m = m.copy()
        m[: MIN_AGE + 30 * BARS_PER_DAY] = False
        return m

    def beta(self, days: float) -> np.ndarray:
        """Rolling beta of each asset to BTC (4h returns), known at bar close."""
        n = int(days * BARS_PER_DAY)

        def f():
            rb = pd.Series(self.r1z[:, self.btc])
            var = rb.rolling(n, min_periods=n // 2).var().to_numpy()
            cov = pd.DataFrame(self.r1z).rolling(n, min_periods=n // 2).cov(rb).to_numpy()
            return cov / var[:, None]

        return self._get(("beta", n), f)

    def btc_up(self, days: float, kind: str = "sma") -> np.ndarray:
        ma = self.sma(days) if kind == "sma" else self.ema(days)
        b = self.close[:, self.btc]
        with np.errstate(invalid="ignore"):
            return b > ma[:, self.btc]


# ---------------------------------------------------------------------------
def _pick(score: np.ndarray, valid: np.ndarray, q: float):
    """Return (long_idx, short_idx) = top q / bottom q of finite scores."""
    ok = valid & np.isfinite(score)
    n = int(ok.sum())
    if n < MIN_NAMES:
        return None, None
    idx = np.flatnonzero(ok)
    order = idx[np.argsort(score[idx], kind="stable")]
    m = max(int(math.ceil(q * n)), 1)
    return order[-m:], order[:m]


def _leg(idx: np.ndarray, w_total: float, ivol: np.ndarray | None) -> np.ndarray:
    if ivol is None:
        return np.full(len(idx), w_total / len(idx))
    v = ivol[idx]
    v = np.where(np.isfinite(v) & (v > 0), 1.0 / v, 0.0)
    s = v.sum()
    if s <= 0:
        return np.full(len(idx), w_total / len(idx))
    return w_total * v / s


def _vol_target(ctx: Ctx, W: np.ndarray, reb: np.ndarray, tv: float, lb_days: int, max_lev: float) -> np.ndarray:
    """Scale each rebalance row so the *back-cast* vol of that portfolio (from past
    market returns only, never from the strategy's own PnL) equals ``tv``."""
    n = lb_days * BARS_PER_DAY
    rows = np.flatnonzero(reb)
    out = W.copy()
    for t in rows:
        if t < n:
            out[t] = 0.0
            continue
        w = np.nan_to_num(W[t])
        if not w.any():
            continue
        hist = ctx.r1z[t - n + 1 : t + 1] @ w
        est = float(hist.std() * math.sqrt(ANN))
        if est <= 1e-9:
            out[t] = 0.0
            continue
        out[t] = W[t] * min(tv / est, max_lev)
    return out


def _finish(ctx: Ctx, W: np.ndarray, reb: np.ndarray, p: dict):
    tv = p.get("tv")
    if tv:
        W = _vol_target(ctx, W, reb, float(tv), int(p.get("vol_lb", 60)), float(p.get("max_lev", 2.0)))
    else:
        W = W * float(p.get("gross", 1.0))
    return W, reb


# ---------------------------------------------------------------------------
# cross-sectional score based long/short families
def _xs_scores(ctx: Ctx, fam: str, p: dict) -> np.ndarray:
    if fam == "xs_mom":
        return ctx.ret(p["L"], p.get("skip", 0))
    if fam == "xs_rev":
        return -ctx.ret(p["L"])
    if fam == "low_vol":
        return -ctx.vol(p["L"])
    if fam == "high_vol":
        return ctx.vol(p["L"])
    if fam == "funding_xs":
        return -ctx.rolling_mean(ctx.p.funding * 3.0, p["L"], "fund")  # short high funding
    if fam == "lottery":
        # short coins with the highest single-day return in the window
        d = ctx.ret(1.0)
        mx = ctx._get(
            ("max1d", int(p["L"])),
            lambda: pd.DataFrame(d).rolling(int(p["L"] * BARS_PER_DAY), min_periods=BARS_PER_DAY).max().to_numpy(),
        )
        return -mx
    if fam == "vol_shock":
        short = ctx.rolling_mean(ctx.p.qvol, p.get("s", 3), "qv_s")
        long_ = ctx.rolling_mean(ctx.p.qvol, p.get("l", 30), "qv_l")
        with np.errstate(divide="ignore", invalid="ignore"):
            surge = short / long_
        direction = np.sign(ctx.ret(p.get("dir_days", 3)))
        return surge * direction * p.get("sign", 1.0)
    if fam == "taker":
        tb = ctx.rolling_mean(ctx.p.taker, p["L"], "tk")
        vv = ctx.rolling_mean(ctx.p.volume, p["L"], "vv")
        with np.errstate(divide="ignore", invalid="ignore"):
            return (tb / vv) * p.get("sign", 1.0)
    if fam == "resid_mom":
        be = ctx.beta(p.get("beta_days", 60))
        rb = ctx.r1z[:, ctx.btc]
        key = ("beta", int(p.get("beta_days", 60) * BARS_PER_DAY))
        resid = ctx.r1z - be * rb[:, None]
        resid = _shift(resid, 1)  # use beta known one bar earlier
        L = int(p["L"] * BARS_PER_DAY)
        return ctx._get(
            ("resid", key, L), lambda: pd.DataFrame(resid).rolling(L, min_periods=L).sum().to_numpy()
        )
    if fam == "btc_ratio":
        lr = np.log(ctx.close / ctx.close[:, [ctx.btc]])
        L = int(p["L"] * BARS_PER_DAY)

        def z():
            df = pd.DataFrame(lr)
            return ((df - df.rolling(L, min_periods=L).mean()) / df.rolling(L, min_periods=L).std()).to_numpy()

        return -ctx._get(("ratio_z", L), z)  # long very cheap vs BTC, short very rich
    if fam == "size":
        return -ctx.liq_rank * p.get("sign", 1.0)
    if fam == "composite":
        uni = ctx.universe(p.get("K", 40))
        ranks = [_pct_rank(factor_matrix(ctx, t), uni) for t in p["factors"].split("+")]
        stack = np.stack(ranks)
        out = np.where(np.isfinite(stack).all(axis=0), stack.mean(axis=0), np.nan)
        sd = float(p.get("smooth_days", 0))
        if sd > 0:
            n = int(sd * BARS_PER_DAY)
            out = pd.DataFrame(out).rolling(n, min_periods=max(n // 2, 1)).mean().to_numpy()
        return out
    if fam == "tchg":
        return factor_matrix(ctx, f"tchg{p['L']}") * p.get("sign", 1.0)
    if fam == "fz":
        return factor_matrix(ctx, f"fz{p['L']}") * p.get("sign", 1.0)
    raise KeyError(fam)


def _pct_rank(a: np.ndarray, mask: np.ndarray) -> np.ndarray:
    return pd.DataFrame(np.where(mask, a, np.nan)).rank(axis=1, pct=True).to_numpy()


def _taker_ratio(ctx: Ctx, days: float) -> np.ndarray:
    tb = ctx.rolling_mean(ctx.p.taker, days, "tk")
    vv = ctx.rolling_mean(ctx.p.volume, days, "vv")
    with np.errstate(divide="ignore", invalid="ignore"):
        return tb / vv


def factor_matrix(ctx: Ctx, token: str) -> np.ndarray:
    """Cross-sectional factor (higher = more attractive to be LONG), e.g. 'mom30'."""
    name = token.rstrip("0123456789.")
    days = float(token[len(name) :])
    if name == "mom":
        return ctx.ret(days)
    if name == "rev":
        return -ctx.ret(days)
    if name == "taker":
        return _taker_ratio(ctx, days)
    if name == "tchg":
        return _taker_ratio(ctx, days) - _taker_ratio(ctx, 30)
    if name == "fund":
        return -ctx.rolling_mean(ctx.p.funding * 3.0, days, "fund")
    if name == "fz":
        short = ctx.rolling_mean(ctx.p.funding * 3.0, days, "fund")
        long_ = ctx.rolling_mean(ctx.p.funding * 3.0, 30, "fund")
        sd = ctx._get(
            ("fsd", 30),
            lambda: pd.DataFrame(ctx.p.funding * 3.0).rolling(30 * BARS_PER_DAY, min_periods=BARS_PER_DAY).std().to_numpy(),
        )
        with np.errstate(divide="ignore", invalid="ignore"):
            return -(short - long_) / sd
    if name == "resid":
        return _xs_scores(ctx, "resid_mom", {"L": days, "beta_days": 60})
    if name == "lvol":
        return -ctx.vol(days)
    if name in ("illiq", "liq"):
        a = np.abs(ctx.r1z) / np.where(ctx.p.qvol > 0, ctx.p.qvol, np.nan)
        m = ctx.rolling_mean(np.nan_to_num(a, nan=0.0), days, "amihud")
        return m if name == "illiq" else -m
    if name == "lot":
        return _xs_scores(ctx, "lottery", {"L": days})
    if name in ("vsurge", "vcalm"):
        s = ctx.rolling_mean(ctx.p.qvol, 3, "qv_s3")
        l_ = ctx.rolling_mean(ctx.p.qvol, days, "qv_l")
        with np.errstate(divide="ignore", invalid="ignore"):
            r = s / l_
        return r if name == "vsurge" else -r
    if name == "small":
        return -ctx.liq_rank
    if name == "big":
        return ctx.liq_rank
    raise KeyError(token)


XS_FAMILIES = {
    "xs_mom",
    "xs_rev",
    "low_vol",
    "high_vol",
    "funding_xs",
    "lottery",
    "vol_shock",
    "taker",
    "resid_mom",
    "btc_ratio",
    "size",
    "composite",
    "tchg",
    "fz",
}


def _pick_buffered(score, valid, q, buffer, prev_long, prev_short):
    """Top/bottom q with hysteresis: incumbents stay while inside the wider q+buffer band."""
    ok = valid & np.isfinite(score)
    n = int(ok.sum())
    if n < MIN_NAMES:
        return None, None
    idx = np.flatnonzero(ok)
    order = idx[np.argsort(score[idx], kind="stable")]
    m = max(int(math.ceil(q * n)), 1)
    bm = max(int(math.ceil((q + buffer) * n)), m)
    top_band, bot_band = set(order[-bm:].tolist()), set(order[:bm].tolist())
    pos_in = {int(j): r for r, j in enumerate(order)}
    keep_l = sorted((j for j in prev_long if j in top_band), key=lambda j: -pos_in[j])[:m]
    keep_s = sorted((j for j in prev_short if j in bot_band), key=lambda j: pos_in[j])[:m]
    longs = list(keep_l)
    for j in order[::-1]:
        if len(longs) >= m:
            break
        if int(j) not in longs and int(j) not in keep_s:
            longs.append(int(j))
    shorts = list(keep_s)
    for j in order:
        if len(shorts) >= m:
            break
        if int(j) not in shorts and int(j) not in longs:
            shorts.append(int(j))
    return np.array(longs), np.array(shorts)


def _ls_tiered(ctx: Ctx, score: np.ndarray, uni: np.ndarray, reb: np.ndarray, p: dict) -> np.ndarray:
    """Long/short inside each of 3 liquidity tiers (equal gross per tier) so the book has
    no liquidity/size tilt; hysteresis is tracked per tier."""
    q = float(p.get("q", 0.2))
    buffer = float(p.get("buffer", 0.0))
    prev = {k: ([], []) for k in range(3)}
    W = np.zeros((ctx.T, ctx.N))
    for t in np.flatnonzero(reb):
        valid = uni[t] & np.isfinite(score[t])
        idx = np.flatnonzero(valid)
        if len(idx) < 3 * MIN_NAMES:
            continue
        idx = idx[np.argsort(ctx.liq_rank[t, idx], kind="stable")]  # most liquid first
        for k, chunk in enumerate(np.array_split(idx, 3)):
            mask = np.zeros(ctx.N, dtype=bool)
            mask[chunk] = True
            if buffer > 0:
                longs, shorts = _pick_buffered(score[t], mask, q, buffer, prev[k][0], prev[k][1])
            else:
                longs, shorts = _pick(score[t], mask, q)
            if longs is None:
                continue
            prev[k] = (longs.tolist(), shorts.tolist())
            W[t, longs] = _leg(longs, 0.5 / 3, None)
            W[t, shorts] = -_leg(shorts, 0.5 / 3, None)
    return W


def build_xs(ctx: Ctx, spec: dict):
    fam, p = spec["family"], spec["params"]
    score = _xs_scores(ctx, fam, p)
    uni = ctx.universe(p.get("K", 40))
    if p.get("rebal_bars"):
        nb = int(p["rebal_bars"])
        reb = (np.arange(ctx.T) % nb) == (nb - 1)
        reb[: MIN_AGE + 30 * BARS_PER_DAY] = False
    else:
        reb = ctx.reb_mask(int(p.get("rebal", 7)), int(p.get("offset", 0)))
    if p.get("tier_neutral") and p.get("mode", "ls") == "ls":
        return _finish(ctx, _ls_tiered(ctx, score, uni, reb, p), reb, p)
    ivol = ctx.vol(30) if p.get("wt") == "ivol" else None
    mode = p.get("mode", "ls")
    reg = None
    if p.get("regime_days"):
        reg = ctx.btc_up(p["regime_days"], p.get("regime_kind", "sma"))
    beta = ctx.beta(p.get("beta_days", 60)) if p.get("beta_neutral") else None
    buffer = float(p.get("buffer", 0.0))
    prev_l: list[int] = []
    prev_s: list[int] = []
    W = np.zeros((ctx.T, ctx.N))
    q = float(p.get("q", 0.2))
    for t in np.flatnonzero(reb):
        if buffer > 0:
            longs, shorts = _pick_buffered(score[t], uni[t], q, buffer, prev_l, prev_s)
        else:
            longs, shorts = _pick(score[t], uni[t], q)
        if longs is None:
            continue
        prev_l, prev_s = longs.tolist(), shorts.tolist()
        iv = ivol[t] if ivol is not None else None
        if mode == "ls":
            wl = _leg(longs, 0.5, iv)
            ws = _leg(shorts, 0.5, iv)
            if beta is not None:
                bl = float(np.nansum(wl * np.nan_to_num(beta[t, longs], nan=1.0)))
                bs = float(np.nansum(ws * np.nan_to_num(beta[t, shorts], nan=1.0)))
                if bs > 1e-6 and bl > 1e-6:
                    ws = ws * float(np.clip(bl / bs, 0.5, 2.0))
            W[t, longs] = wl
            W[t, shorts] = -ws
        elif mode == "long":
            if reg is None or reg[t]:
                W[t, longs] = _leg(longs, 1.0, iv)
        elif mode == "short":
            if reg is None or not reg[t]:
                W[t, shorts] = -_leg(shorts, 1.0, iv)
        elif mode == "regime_ls":
            # up-trend: long the strong; down-trend: short the weak
            if reg is None:
                continue
            if reg[t]:
                W[t, longs] = _leg(longs, 1.0, iv)
            else:
                W[t, shorts] = -_leg(shorts, 1.0, iv)
        else:
            raise KeyError(mode)
    return _finish(ctx, W, reb, p)


# ---------------------------------------------------------------------------
def build_btc_trend(ctx: Ctx, spec: dict):
    """Time-series trend on BTC/ETH: long while price > MA(n) else flat (or short)."""
    p = spec["params"]
    assets = {"BTC": [ctx.btc], "ETH": [ctx.eth], "BTCETH": [ctx.btc, ctx.eth]}[p.get("asset", "BTC")]
    reb = ctx.reb_mask(int(p.get("rebal", 1)))
    ma = ctx.sma(p["n"]) if p.get("kind", "sma") == "sma" else ctx.ema(p["n"])
    W = np.zeros((ctx.T, ctx.N))
    for j in assets:
        up = ctx.close[:, j] > ma[:, j]
        w = np.where(up, 1.0, -1.0 if p.get("short") else 0.0) / len(assets)
        W[:, j] = np.where(reb & np.isfinite(ma[:, j]), w, 0.0)
    return _finish(ctx, W, reb, p)


def build_ts_mom_basket(ctx: Ctx, spec: dict):
    p = spec["params"]
    uni = ctx.universe(p.get("K", 20))
    reb = ctx.reb_mask(int(p.get("rebal", 3)))
    r = ctx.ret(p["L"])
    iv = ctx.vol(30)
    W = np.zeros((ctx.T, ctx.N))
    short_scale = float(p.get("short_scale", 1.0))
    for t in np.flatnonzero(reb):
        ok = uni[t] & np.isfinite(r[t]) & np.isfinite(iv[t]) & (iv[t] > 0)
        if ok.sum() < MIN_NAMES:
            continue
        s = np.sign(r[t])
        w = np.where(ok, s / iv[t], 0.0)
        w = np.where(w < 0, w * short_scale, w)
        tot = np.abs(w).sum()
        if tot > 0:
            W[t] = w / tot
    return _finish(ctx, W, reb, p)


def build_mkt_flow(ctx: Ctx, spec: dict):
    """Time-series timing of BTC/ETH by aggregate taker-flow z-score of the liquid universe."""
    p = spec["params"]
    uni = ctx.universe(p.get("K", 40))
    tq = np.where(uni, np.nan_to_num(ctx.p.taker) * np.nan_to_num(ctx.close), 0.0).sum(axis=1)
    vq = np.where(uni, np.nan_to_num(ctx.p.qvol), 0.0).sum(axis=1)
    n = int(p["L"] * BARS_PER_DAY)
    zn = int(p.get("zwin", 90) * BARS_PER_DAY)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = pd.Series(np.where(vq > 0, tq / vq, np.nan)).rolling(n, min_periods=n // 2).mean()
    z = ((ratio - ratio.rolling(zn, min_periods=zn // 2).mean()) / ratio.rolling(zn, min_periods=zn // 2).std()).to_numpy()
    assets = {"BTC": [ctx.btc], "ETH": [ctx.eth], "BTCETH": [ctx.btc, ctx.eth]}[p.get("asset", "BTC")]
    reb = ctx.reb_mask(1)
    thr = float(p.get("thr", 0.0))
    W = np.zeros((ctx.T, ctx.N))
    long_ = np.nan_to_num(z, nan=-9.0) > thr
    short_ = np.nan_to_num(z, nan=9.0) < -thr
    side = np.where(long_, 1.0, np.where(short_ & (p.get("mode", "long") == "ls"), -1.0, 0.0))
    for j in assets:
        W[:, j] = np.where(reb, side / len(assets), 0.0)
    return _finish(ctx, W, reb, p)


def build_alt_vs_btc(ctx: Ctx, spec: dict):
    """Long BTC / short an alt basket (dollar neutral) gated by BTC regime."""
    p = spec["params"]
    uni = ctx.universe(p.get("K", 30)).copy()
    uni[:, ctx.btc] = False
    reb = ctx.reb_mask(int(p.get("rebal", 7)))
    reg = ctx.btc_up(p.get("regime_days", 100), p.get("regime_kind", "sma"))
    gate = p.get("gate", "always")
    sel = p.get("sel", "all")  # 'all' or 'weak'
    score = ctx.ret(p.get("L", 30)) if sel == "weak" else None
    W = np.zeros((ctx.T, ctx.N))
    for t in np.flatnonzero(reb):
        if gate == "down" and reg[t]:
            continue
        if gate == "up" and not reg[t]:
            continue
        ok = uni[t]
        if sel == "weak":
            ok = ok & np.isfinite(score[t])
            idx = np.flatnonzero(ok)
            if len(idx) < MIN_NAMES:
                continue
            m = max(int(math.ceil(p.get("q", 0.5) * len(idx))), 1)
            idx = idx[np.argsort(score[t][idx])][:m]
        else:
            idx = np.flatnonzero(ok)
            if len(idx) < MIN_NAMES:
                continue
        W[t, idx] = -0.5 / len(idx)
        W[t, ctx.btc] = 0.5
    return _finish(ctx, W, reb, p)


# ---------------------------------------------------------------------------
def build_event(ctx: Ctx, spec: dict):
    """Fixed-horizon event baskets with optional TP (take profit, not a stop).

    pump_fade : short coins whose r(L) > thr (top ranks), hold H days
    dump_bounce: long coins whose r(L) < -thr, hold H days
    Position size is a fixed fraction of equity at entry (``size``); at most
    ``max_pos`` concurrent.  Exit = horizon or TP only.
    """
    fam, p = spec["family"], spec["params"]
    side = -1.0 if fam == "pump_fade" else 1.0
    r = ctx.ret(p["L"])
    uni = ctx.universe(p.get("K", 60))
    H = int(p["H"] * BARS_PER_DAY)
    tp = p.get("tp")
    size = float(p.get("size", 0.1))
    max_pos = int(p.get("max_pos", 8))
    thr = float(p["thr"])
    vs = p.get("vol_surge")
    surge = None
    if vs:
        s = ctx.rolling_mean(ctx.p.qvol, 1, "qv_s1")
        l_ = ctx.rolling_mean(ctx.p.qvol, 30, "qv_l")
        with np.errstate(divide="ignore", invalid="ignore"):
            surge = s / l_
    reg = ctx.btc_up(p["regime_days"], "sma") if p.get("regime_days") else None
    regime_need = p.get("regime_need")  # 'up' | 'down' | None

    T, N = ctx.T, ctx.N
    W = np.full((T, N), np.nan)
    reb = np.zeros(T, dtype=bool)
    open_: dict[int, tuple[int, float]] = {}  # sym -> (entry_decision_bar, entry_price)
    start = MIN_AGE + 30 * BARS_PER_DAY
    cl = ctx.close
    for t in range(start, T - 1):
        changed = False
        # exits first (decided at close of bar t, executed at next open)
        for j in list(open_.keys()):
            tb, ep = open_[j]
            age = t - tb
            hit_tp = False
            if tp and np.isfinite(cl[t, j]) and ep > 0:
                pnl = side * (cl[t, j] / ep - 1.0)
                hit_tp = pnl >= tp
            if age >= H or hit_tp:
                W[t, j] = 0.0
                del open_[j]
                changed = True
        # entries evaluated once per day at day end
        if ctx.day_end[t] and len(open_) < max_pos:
            if regime_need == "up" and not (reg is not None and reg[t]):
                pass
            elif regime_need == "down" and not (reg is not None and not reg[t]):
                pass
            else:
                cand = uni[t] & np.isfinite(r[t])
                if side < 0:
                    cand &= r[t] > thr
                else:
                    cand &= r[t] < -thr
                if surge is not None:
                    cand &= np.nan_to_num(surge[t]) > vs
                idx = np.flatnonzero(cand)
                if len(idx):
                    key = r[t][idx] * (-side)  # most extreme first
                    idx = idx[np.argsort(key)]
                    for j in idx:
                        if int(j) in open_ or len(open_) >= max_pos or not np.isnan(W[t, j]):
                            continue
                        open_[int(j)] = (t, cl[t, j])
                        W[t, j] = side * size
                        changed = True
        if changed:
            reb[t] = True
    # position size is held; the engine only sets the NaN-masked entries
    return W, reb


# ---------------------------------------------------------------------------
def build_blend(ctx: Ctx, spec: dict):
    """Fixed-weight sum of non-event sleeves.  Each sleeve keeps its own sizing; at every
    decision row of any sleeve all sleeves are re-targeted to their last decided weights."""
    p = spec["params"]
    parts = p["parts"]
    wts = p.get("weights") or [1.0 / len(parts)] * len(parts)
    T = ctx.T
    W = np.zeros((T, ctx.N))
    reb = np.zeros(T, dtype=bool)
    ar = np.arange(T)
    for part, w in zip(parts, wts):
        Wp, rp = build(ctx, part)
        last = np.maximum.accumulate(np.where(rp, ar, -1))
        ff = np.where((last >= 0)[:, None], np.nan_to_num(Wp[np.maximum(last, 0)]), 0.0)
        W += w * ff
        reb |= rp
    return _finish(ctx, W, reb, p)


BUILDERS = {
    "btc_trend": build_btc_trend,
    "ts_mom_basket": build_ts_mom_basket,
    "alt_vs_btc": build_alt_vs_btc,
    "pump_fade": build_event,
    "dump_bounce": build_event,
    "blend": build_blend,
    "mkt_flow": build_mkt_flow,
}
for _f in XS_FAMILIES:
    BUILDERS[_f] = build_xs


def build(ctx: Ctx, spec: dict):
    return BUILDERS[spec["family"]](ctx, spec)
