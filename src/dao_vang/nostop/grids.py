"""Parameter grids for TRAIN-only tuning.  Values are ordered so neighbours can be
smoothed (plateau check).  Every family runs without any stop-loss."""

from __future__ import annotations

from itertools import product

# (family, fixed params, {param: ordered values})
R1_GRIDS: list[tuple[str, dict, dict]] = [
    (
        "xs_mom",
        {"mode": "ls", "tv": 0.3},
        {"L": [7, 14, 30, 60, 90], "skip": [0, 3], "q": [0.1, 0.2, 0.3], "K": [20, 40, 80],
         "rebal": [3, 7, 14], "wt": ["eq", "ivol"]},
    ),
    (
        "xs_mom",
        {"mode": "long", "tv": 0.4},
        {"L": [14, 30, 60, 90], "q": [0.1, 0.2, 0.3], "K": [20, 40], "rebal": [3, 7],
         "regime_days": [50, 100, 150]},
    ),
    (
        "xs_mom",
        {"mode": "regime_ls", "tv": 0.4},
        {"L": [14, 30, 60], "q": [0.1, 0.2, 0.3], "K": [20, 40], "rebal": [3, 7],
         "regime_days": [50, 100, 150]},
    ),
    (
        "xs_rev",
        {"mode": "ls", "tv": 0.3},
        {"L": [1, 2, 3, 5, 7], "q": [0.1, 0.2, 0.3], "K": [20, 40, 80], "rebal": [1, 2, 3],
         "wt": ["eq", "ivol"]},
    ),
    (
        "low_vol",
        {"mode": "ls", "tv": 0.3},
        {"L": [14, 30, 60, 90], "q": [0.1, 0.2, 0.3], "K": [20, 40, 80], "rebal": [7, 14]},
    ),
    (
        "high_vol",
        {"mode": "ls", "tv": 0.3},
        {"L": [14, 30, 60, 90], "q": [0.1, 0.2, 0.3], "K": [20, 40, 80], "rebal": [7, 14]},
    ),
    (
        "funding_xs",
        {"mode": "ls", "tv": 0.3},
        {"L": [1, 3, 7, 14, 30], "q": [0.1, 0.2, 0.3], "K": [20, 40, 80], "rebal": [3, 7]},
    ),
    (
        "lottery",
        {"mode": "ls", "tv": 0.3},
        {"L": [7, 14, 30], "q": [0.1, 0.2, 0.3], "K": [20, 40, 80], "rebal": [3, 7]},
    ),
    (
        "vol_shock",
        {"mode": "ls", "tv": 0.3},
        {"s": [1, 3], "l": [14, 30], "dir_days": [1, 3], "sign": [1, -1], "q": [0.1, 0.2, 0.3],
         "K": [20, 40], "rebal": [1, 3]},
    ),
    (
        "taker",
        {"mode": "ls", "tv": 0.3},
        {"L": [3, 7, 14, 30], "sign": [1, -1], "q": [0.1, 0.2, 0.3], "K": [20, 40, 80],
         "rebal": [3, 7]},
    ),
    (
        "resid_mom",
        {"mode": "ls", "tv": 0.3, "beta_days": 60},
        {"L": [7, 14, 30, 60], "q": [0.1, 0.2, 0.3], "K": [20, 40, 80], "rebal": [3, 7, 14]},
    ),
    (
        "btc_ratio",
        {"mode": "ls", "tv": 0.3},
        {"L": [14, 30, 60, 90], "q": [0.1, 0.2, 0.3], "K": [20, 40, 80], "rebal": [3, 7]},
    ),
    (
        "size",
        {"mode": "ls", "tv": 0.3},
        {"sign": [1, -1], "q": [0.1, 0.2, 0.3], "K": [40, 80], "rebal": [7, 14, 30]},
    ),
    (
        "btc_trend",
        {},
        {"asset": ["BTC", "ETH", "BTCETH"], "kind": ["sma", "ema"],
         "n": [20, 30, 50, 75, 100, 150, 200], "short": [False, True], "tv": [0.3, 0.5]},
    ),
    (
        "ts_mom_basket",
        {"tv": 0.4},
        {"L": [7, 14, 30, 60, 90], "K": [10, 20, 40], "rebal": [1, 3, 7],
         "short_scale": [0.0, 0.5, 1.0]},
    ),
    (
        "alt_vs_btc",
        {"tv": 0.3, "rebal": 7, "sel": "all"},
        {"gate": ["always", "down", "up"], "regime_days": [50, 100, 150], "K": [20, 40]},
    ),
    (
        "alt_vs_btc",
        {"tv": 0.3, "rebal": 7, "sel": "weak"},
        {"gate": ["always", "down", "up"], "regime_days": [50, 100, 150], "K": [20, 40],
         "L": [14, 30, 60], "q": [0.3, 0.5]},
    ),
    (
        "pump_fade",
        {"size": 0.04, "max_pos": 8, "K": 60},
        {"L": [3, 7, 14], "thr": [0.2, 0.4, 0.6], "H": [3, 7, 14], "tp": [None, 0.1, 0.2, 0.3],
         "vol_surge": [None, 2.0]},
    ),
    (
        "dump_bounce",
        {"size": 0.04, "max_pos": 8, "K": 60},
        {"L": [3, 7, 14], "thr": [0.2, 0.3, 0.4], "H": [3, 7, 14], "tp": [None, 0.1, 0.2, 0.3],
         "vol_surge": [None, 2.0]},
    ),
]


def expand(grids=R1_GRIDS) -> list[dict]:
    """Return specs with a hidden ``group`` + ``idx`` used only for plateau smoothing."""
    out: list[dict] = []
    for gi, (fam, fixed, axes) in enumerate(grids):
        names = list(axes)
        for combo in product(*[range(len(axes[n])) for n in names]):
            params = dict(fixed)
            for n, ci in zip(names, combo):
                v = axes[n][ci]
                if v is not None:
                    params[n] = v
            out.append(
                {
                    "family": fam,
                    "params": params,
                    "_group": f"{gi}:{fam}:{fixed.get('mode', '')}:{fixed.get('sel', '')}",
                    "_idx": list(combo),
                    "_axes": names,
                }
            )
    return out


def strip(spec: dict) -> dict:
    return {"family": spec["family"], "params": spec["params"]}


# ---------------------------------------------------------------------------
# Round 2: flow / carry composites (designed after seeing R1 validation of the
# frozen R1 specs: price momentum decayed, taker-flow and funding held up best)
COMPOSITE_COMBOS = [
    "taker7+fund7",
    "taker3+fund3",
    "taker7+fund14",
    "mom30+taker7",
    "mom14+taker7",
    "mom30+fund7",
    "mom30+taker7+fund7",
    "mom14+taker3+fund7",
    "resid30+taker7+fund7",
    "resid14+taker7",
    "tchg7+fund7",
    "taker7+fz7",
    "mom30+taker7+fz7",
    "mom60+taker14+fund14",
    "rev3+taker7+fund7",
    "taker1+fund3",
    "tchg3+fz3",
    "taker7+lvol30",
]

R2_GRIDS: list[tuple[str, dict, dict]] = (
    [
        (
            "composite",
            {"factors": c, "mode": "ls", "tv": 0.3},
            {"q": [0.1, 0.2, 0.3], "K": [20, 40, 80], "rebal": [1, 3, 7]},
        )
        for c in COMPOSITE_COMBOS
    ]
    + [
        (
            "tchg",
            {"mode": "ls", "tv": 0.3},
            {"L": [1, 3, 7, 14], "sign": [1, -1], "q": [0.1, 0.2, 0.3], "K": [20, 40, 80],
             "rebal": [1, 3, 7]},
        ),
        (
            "fz",
            {"mode": "ls", "tv": 0.3},
            {"L": [3, 7, 14], "sign": [1, -1], "q": [0.1, 0.2, 0.3], "K": [20, 40, 80],
             "rebal": [1, 3, 7]},
        ),
        (
            "taker",
            {"mode": "ls", "tv": 0.3},
            {"L": [1, 2], "sign": [1, -1], "q": [0.1, 0.2, 0.3], "K": [20, 40, 80],
             "rebal": [0.5, 1]},
        ),
        (
            "taker",
            {"mode": "regime_ls", "tv": 0.4},
            {"L": [3, 7, 14], "q": [0.1, 0.2, 0.3], "K": [20, 40], "rebal": [3, 7],
             "regime_days": [50, 100, 150]},
        ),
        (
            "funding_xs",
            {"mode": "short", "tv": 0.4},
            {"L": [3, 7, 14], "q": [0.1, 0.2, 0.3], "K": [20, 40], "rebal": [3, 7],
             "regime_days": [50, 100, 150]},
        ),
    ]
)

GRID_SETS = {"R1": R1_GRIDS, "R2": R2_GRIDS}


# ---------------------------------------------------------------------------
# Round 3: structural improvements applied to ALL composite combos (R2 + new):
# beta-neutral legs, rank hysteresis (turnover control), inverse-vol weights.
NEW_COMBOS = [
    "taker3+taker7+fund7",
    "taker7+taker14+fund14",
    "mom14+mom30+taker7+fund7",
    "mom30+tchg7+fund7",
    "resid30+taker7+fz7",
    "resid14+taker7+fund7",
    "mom14+resid30+taker7",
    "taker7+fund7+fz7",
    "mom30+taker3+taker7+fund7",
    "mom60+taker7+fund7",
    "mom30+taker14+fund7",
    "mom30+taker7+fund14",
    "mom14+taker7+fz7",
    "resid30+tchg7+fund7",
    "mom30+taker7+fund7+fz7",
    "mom7+taker7+fund7",
    "mom90+taker14+fund14",
]

R3_GRIDS: list[tuple[str, dict, dict]] = [
    (
        "composite",
        {"factors": c, "mode": "ls", "tv": 0.3},
        {"q": [0.15, 0.25], "K": [40, 80], "rebal": [1, 3, 7], "beta_neutral": [False, True],
         "buffer": [0.0, 0.1], "wt": ["eq", "ivol"]},
    )
    for c in COMPOSITE_COMBOS + NEW_COMBOS
]

GRID_SETS["R3"] = R3_GRIDS


# ---------------------------------------------------------------------------
# Round 4: refine around the R3 findings.  Combos = top-16 groups by TRAIN-only smoothed
# score in R3 (K=40, buffer 0.1, rebal 3 won on train; beta-neutral and ivol lost on
# train).  New axes: finer K/q/rebal, wider hysteresis band, causal score smoothing.
R4_COMBOS = [
    "taker7+taker14+fund14",
    "mom30+taker3+taker7+fund7",
    "taker3+taker7+fund7",
    "mom30+taker7+fund7",
    "mom30+taker14+fund7",
    "resid30+taker7+fund7",
    "resid14+taker7+fund7",
    "mom30+taker7+fund14",
    "taker7+fund14",
    "resid30+taker7+fz7",
    "mom7+taker7+fund7",
    "mom14+taker3+fund7",
    "mom14+mom30+taker7+fund7",
    "taker7+fund7",
    "mom14+resid30+taker7",
    "mom30+taker7+fz7",
]

R4_GRIDS: list[tuple[str, dict, dict]] = [
    (
        "composite",
        {"factors": c, "mode": "ls", "tv": 0.3},
        {"q": [0.1, 0.15, 0.2], "K": [20, 30, 40, 50], "rebal": [2, 3, 5],
         "buffer": [0.1, 0.2, 0.3], "smooth_days": [0, 2]},
    )
    for c in R4_COMBOS
]

GRID_SETS["R4"] = R4_GRIDS


# ---------------------------------------------------------------------------
# Round 5: new mechanisms.  (A) extra factor tokens on two flow cores (is there any
# incremental information?), (B) long-only composite gated by BTC regime, (C) aggregate
# taker-flow timing of BTC/ETH (time-series, low overlap with the cross-sectional books).
R5_CORES = ["taker7+fund14", "mom30+taker7+fund7"]
R5_EXTRAS = ["illiq30", "liq30", "lot30", "vsurge14", "vcalm14", "small1", "big1", "lvol30"]

R5_GRIDS: list[tuple[str, dict, dict]] = (
    [
        (
            "composite",
            {"factors": f"{core}+{extra}", "mode": "ls", "tv": 0.3},
            {"q": [0.15, 0.2], "K": [30, 40, 50], "rebal": [2, 3], "buffer": [0.1, 0.3],
             "smooth_days": [0, 2]},
        )
        for core in R5_CORES
        for extra in R5_EXTRAS
    ]
    + [
        (
            "composite",
            {"factors": f, "mode": "long", "tv": 0.4, "buffer": 0.1},
            {"q": [0.1, 0.2], "K": [20, 40], "rebal": [3, 7], "regime_days": [50, 100, 150]},
        )
        for f in ["taker7+fund14", "mom30+taker7+fund7", "taker7+taker14+fund14",
                  "mom30+taker14+fund7"]
    ]
    + [
        (
            "mkt_flow",
            {"K": 40, "tv": 0.4},
            {"L": [3, 7, 14], "zwin": [60, 90], "thr": [0.0, 0.5, 1.0],
             "asset": ["BTC", "ETH", "BTCETH"], "mode": ["long", "ls"]},
        )
    ]
)

GRID_SETS["R5"] = R5_GRIDS


# ---------------------------------------------------------------------------
# Round 6: regime-robustness.  R5 showed liquidity/size-type factors flip sign between
# train and validation (illiq30/big1 best on train, worst on val; liq30/small1 the reverse),
# so tilt-dependent books are fragile.  Here every book is long/short INSIDE each of three
# liquidity tiers (no size tilt) and only non-tilt extras are kept.
R6_CORES = [
    "taker7+fund14",
    "mom30+taker7+fund7",
    "taker7+taker14+fund14",
    "mom30+taker3+taker7+fund7",
    "taker3+taker7+fund7",
    "mom30+taker7+fz7",
]
R6_EXTRAS = ["", "vsurge14", "lot30", "lvol30"]

R6_GRIDS: list[tuple[str, dict, dict]] = [
    (
        "composite",
        {"factors": core if not extra else f"{core}+{extra}", "mode": "ls", "tv": 0.3,
         "tier_neutral": True},
        {"q": [0.15, 0.25], "K": [45, 60, 90], "rebal": [2, 3], "buffer": [0.1, 0.3]},
    )
    for core in R6_CORES
    for extra in R6_EXTRAS
]

GRID_SETS["R6"] = R6_GRIDS
