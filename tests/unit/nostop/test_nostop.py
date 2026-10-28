"""Engine + signal invariants for the no-stop-loss research harness."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dao_vang.nostop.data import Panel
from dao_vang.nostop.engine import MAINT_MARGIN, simulate
from dao_vang.nostop.signals import Ctx, build


def make_panel(n_days: int = 520, n_sym: int = 26, seed: int = 7) -> Panel:
    rng = np.random.default_rng(seed)
    bars = n_days * 6
    idx = pd.date_range("2021-01-01", periods=bars, freq="4h", tz="UTC")
    symbols = ["BTCUSDT", "ETHUSDT"] + [f"S{i:02d}USDT" for i in range(n_sym - 2)]
    r = rng.normal(0.0, 0.012, size=(bars, n_sym))
    r[:, 0] += 0.0002
    close = 100.0 * np.exp(np.cumsum(r, axis=0))
    open_ = np.empty_like(close)
    open_[0] = close[0]
    open_[1:] = close[:-1]
    hi = np.maximum(open_, close) * 1.004
    lo = np.minimum(open_, close) * 0.996
    qvol = rng.uniform(1e6, 5e7, size=(bars, n_sym)) * np.linspace(1.0, 3.0, n_sym)
    vol = qvol / close
    taker = vol * rng.uniform(0.4, 0.6, size=(bars, n_sym))
    funding = np.zeros((bars, n_sym))
    funding[idx.hour % 8 == 0] = rng.normal(1e-4, 5e-5, size=(int((idx.hour % 8 == 0).sum()), n_sym))
    return Panel(idx, symbols, open_, hi, lo, close, qvol, taker, vol, funding)


def _cost(p: Panel, bps: float = 0.0) -> np.ndarray:
    return np.full(p.shape, bps * 1e-4)


SPECS = [
    {"family": "xs_mom", "params": {"L": 14, "q": 0.25, "K": 20, "rebal": 3, "mode": "ls", "tv": 0.3}},
    {"family": "xs_rev", "params": {"L": 2, "q": 0.25, "K": 20, "rebal": 1, "mode": "ls", "wt": "ivol"}},
    {"family": "xs_mom", "params": {"L": 30, "q": 0.25, "K": 20, "rebal": 7, "mode": "regime_ls", "regime_days": 50}},
    {"family": "low_vol", "params": {"L": 30, "q": 0.25, "K": 20, "rebal": 7, "tv": 0.3}},
    {"family": "funding_xs", "params": {"L": 7, "q": 0.25, "K": 20, "rebal": 7}},
    {"family": "resid_mom", "params": {"L": 14, "q": 0.25, "K": 20, "rebal": 7}},
    {"family": "btc_ratio", "params": {"L": 30, "q": 0.25, "K": 20, "rebal": 7}},
    {"family": "taker", "params": {"L": 7, "q": 0.25, "K": 20, "rebal": 7}},
    {"family": "vol_shock", "params": {"q": 0.25, "K": 20, "rebal": 3}},
    {"family": "lottery", "params": {"L": 30, "q": 0.25, "K": 20, "rebal": 7}},
    {"family": "btc_trend", "params": {"n": 40, "asset": "BTCETH", "tv": 0.4}},
    {"family": "ts_mom_basket", "params": {"L": 14, "K": 20, "rebal": 3}},
    {"family": "alt_vs_btc", "params": {"gate": "down", "regime_days": 40, "K": 20, "rebal": 7}},
    {"family": "pump_fade", "params": {"L": 5, "thr": 0.05, "H": 5, "tp": 0.04, "size": 0.05, "max_pos": 6, "K": 20}},
    {"family": "dump_bounce", "params": {"L": 5, "thr": 0.05, "H": 5, "size": 0.05, "max_pos": 6, "K": 20}},
    {"family": "composite", "params": {"factors": "mom14+taker7+fund7", "q": 0.25, "K": 20, "rebal": 3, "mode": "ls", "tv": 0.3}},
    {"family": "composite", "params": {"factors": "resid14+tchg7+fz7", "q": 0.25, "K": 20, "rebal": 1, "mode": "ls"}},
    {"family": "composite", "params": {"factors": "mom30+taker7+fund7", "q": 0.2, "K": 20, "rebal": 3, "mode": "ls", "tv": 0.3, "buffer": 0.2, "smooth_days": 2}},
    {"family": "composite", "params": {"factors": "taker7+fund7", "q": 0.2, "K": 20, "rebal": 3, "mode": "ls", "tv": 0.3, "beta_neutral": True, "wt": "ivol"}},
    {"family": "composite", "params": {"factors": "mom30+taker7+fund7+lot30", "q": 0.25, "K": 24, "rebal": 3, "mode": "ls", "tv": 0.3, "tier_neutral": True, "buffer": 0.1}},
    {"family": "composite", "params": {"factors": "taker7+fund14+illiq30+lot30+vsurge14", "q": 0.2, "K": 20, "rebal": 3, "mode": "ls", "tv": 0.3, "buffer": 0.1}},
    {"family": "composite", "params": {"factors": "taker7+liq30+vcalm14+small1+big1", "q": 0.2, "K": 20, "rebal": 3, "mode": "long", "tv": 0.4, "regime_days": 60}},
    {"family": "mkt_flow", "params": {"L": 3, "zwin": 60, "thr": 0.5, "asset": "BTCETH", "mode": "ls", "K": 20, "tv": 0.4}},
    {"family": "tchg", "params": {"L": 3, "sign": -1, "q": 0.25, "K": 20, "rebal": 1, "mode": "ls"}},
    {"family": "fz", "params": {"L": 7, "sign": 1, "q": 0.25, "K": 20, "rebal": 3, "mode": "ls"}},
    {"family": "taker", "params": {"L": 1, "sign": 1, "q": 0.25, "K": 20, "rebal": 0.5, "mode": "ls"}},
    {"family": "blend", "params": {"tv": 0.3, "parts": [
        {"family": "taker", "params": {"L": 7, "q": 0.25, "K": 20, "rebal": 3, "mode": "ls", "tv": 0.3}},
        {"family": "funding_xs", "params": {"L": 7, "q": 0.25, "K": 20, "rebal": 7, "mode": "ls", "tv": 0.3}},
    ]}},
]


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s["family"])
def test_weights_do_not_look_ahead(spec):
    """Rows < cut must be identical when the future is removed from the panel."""
    full = make_panel()
    cut = 380 * 6
    part = Panel(
        full.index[:cut],
        full.symbols,
        *(getattr(full, f)[:cut] for f in ("open", "high", "low", "close", "qvol", "taker", "volume", "funding")),
    )
    W_full, reb_full = build(Ctx(full), spec)
    W_part, reb_part = build(Ctx(part), spec)
    # last row may use features that need bar t+1 only through shift; compare strictly before cut-1
    m = cut - 2
    assert np.array_equal(reb_full[:m], reb_part[:m])
    a, b = W_full[:m], W_part[:m]
    assert np.allclose(np.nan_to_num(a, nan=-9.9), np.nan_to_num(b, nan=-9.9), atol=1e-12)
    assert np.abs(np.nan_to_num(W_part[:m])).sum() > 0, "spec produced no positions; test would be vacuous"


def test_execution_is_next_open_and_pnl_matches_hand_calc():
    p = make_panel(n_days=60, n_sym=4)
    p.funding[:] = 0.0
    T, N = p.shape
    W = np.zeros((T, N))
    reb = np.zeros(T, dtype=bool)
    t = 100
    W[t, 2] = 1.0
    reb[t] = True
    reb[t + 6] = True  # flatten later (W row stays zero)
    res = simulate(p, W, reb, 90, 140, _cost(p, 10.0))
    ratio = p.open[t + 7, 2] / p.open[t + 1, 2]
    fee = 10e-4
    # engine sizes on pre-cost equity: notional 1.0, entry fee on 1.0, exit fee on drifted notional
    e_final = (1.0 - fee) + (ratio - 1.0) - fee * ratio
    got = res.equity[t + 7 - 90 + 1]
    assert got == pytest.approx(e_final, rel=1e-9)


def _rescale_coin(p: Panel, j: int, factor: np.ndarray) -> None:
    """Multiply coin j's whole price path by a per-bar factor, keeping bars consistent."""
    p.open[:, j] *= factor
    p.close[:-1, j] = p.open[1:, j]
    p.close[-1, j] = p.open[-1, j]
    p.high[:, j] = np.maximum(p.open[:, j], p.close[:, j]) * 1.002
    p.low[:, j] = np.minimum(p.open[:, j], p.close[:, j]) * 0.998


def test_losing_position_is_never_closed_by_the_engine():
    p = make_panel(n_days=40, n_sym=3)
    T, _ = p.shape
    k = 50
    fac = np.ones(T)
    fac[k + 2 : k + 8] = 0.85 ** np.arange(1, 7)
    fac[k + 8 :] = 0.85**6  # coin never recovers: -62%
    _rescale_coin(p, 1, fac)
    W = np.zeros((T, 3))
    reb = np.zeros(T, dtype=bool)
    W[k, 1] = 0.5
    reb[k] = True
    res = simulate(p, W, reb, k - 5, k + 60, _cost(p))
    assert not res.ruined
    assert res.equity[-1] < 0.75  # the loss was taken in full, never cut
    assert res.gross[-1] > 0.0  # and the position is still on the book


def test_unlimited_short_squeeze_liquidates_cross_account():
    p = make_panel(n_days=40, n_sym=3)
    T, _ = p.shape
    k = 50
    fac = np.ones(T)
    fac[k + 3 :] = 25.0  # coin 1 jumps 25x and stays there
    _rescale_coin(p, 1, fac)
    W = np.zeros((T, 3))
    reb = np.zeros(T, dtype=bool)
    W[k, 1] = -1.0
    reb[k] = True
    res = simulate(p, W, reb, k - 5, T - 2, _cost(p))
    assert res.ruined
    assert res.equity[-1] == 0.0
    assert MAINT_MARGIN > 0


def test_funding_sign_long_pays_short_receives():
    p = make_panel(n_days=30, n_sym=3)
    p.funding[:] = 0.0
    T, _ = p.shape
    p.open[:, 1] = 100.0
    p.close[:, 1] = 100.0
    p.high[:, 1] = 100.0
    p.low[:, 1] = 100.0
    settle = np.flatnonzero(p.index.hour % 8 == 0)
    p.funding[settle, 1] = 0.001
    W = np.zeros((T, 3))
    reb = np.zeros(T, dtype=bool)
    W[40, 1] = 1.0
    reb[40] = True
    long_res = simulate(p, W, reb, 30, 120, _cost(p))
    W2 = W.copy()
    W2[40, 1] = -1.0
    short_res = simulate(p, W2, reb, 30, 120, _cost(p))
    assert long_res.funding < 0 < short_res.funding

def test_factor_matrix_small_big_vcalm():
    from dao_vang.nostop.signals import factor_matrix
    p = make_panel(n_days=40, n_sym=3)
    # Manually set rolling mean of quote volume at the end to guarantee rank
    # We know K-days rolling mean determines the rank.
    p.qvol[-30*6:, 0] = 1e8  # Highest volume
    p.qvol[-30*6:, 1] = 5e7
    p.qvol[-30*6:, 2] = 1e6  # Lowest volume
    
    ctx = Ctx(p)
    
    small = factor_matrix(ctx, "small1")
    assert small[-1, 0] > small[-1, 2]  # Favoring big caps (-1 > -3)
    
    big = factor_matrix(ctx, "big1")
    assert big[-1, 0] < big[-1, 2]  # Favoring small caps (1 < 3)

    vcalm = factor_matrix(ctx, "vcalm3")
    assert np.all(vcalm[-1] <= 0) # ratio is always >= 0, so -ratio <= 0

def test_long_short_is_dollar_neutral_but_not_beta_neutral():
    p = make_panel(n_days=300, n_sym=26)
    # give coins very different sensitivity to BTC so the legs cannot cancel by accident
    rng = np.random.default_rng(3)
    betas = rng.uniform(0.2, 1.8, size=p.shape[1])
    betas[0] = 1.0
    r_btc = np.diff(np.log(p.close[:, 0]), prepend=np.log(p.close[0, 0]))
    own = np.diff(np.log(p.close), axis=0, prepend=np.log(p.close[:1]))
    px = np.exp(np.cumsum(own + (betas[None, :] - 1.0) * r_btc[:, None] * (np.arange(p.shape[1]) > 0), axis=0)) * 100.0
    for k in ("open", "high", "low", "close"):
        scale = px / p.close
        setattr(p, k, getattr(p, k) * scale)
    spec = {"family": "composite", "params": {"factors": "taker7+fund7", "q": 0.2, "K": 24, "rebal": 1,
                                              "mode": "ls", "tv": 0.3}}
    ctx = Ctx(p)
    W, reb = build(ctx, spec)
    rows = [t for t in np.flatnonzero(reb) if np.abs(W[t]).sum() > 0]
    assert len(rows) > 20
    beta = ctx.beta(60)
    net = np.array([W[t].sum() for t in rows])
    bexp = np.array([np.nansum(W[t] * beta[t]) for t in rows])
    assert np.abs(net).max() < 1e-9  # dollar-neutral at every rebalance
    assert np.abs(bexp).max() > 0.02  # but not beta-neutral
