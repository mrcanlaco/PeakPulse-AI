"""Gated evaluation harness + parallel sweeps."""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from .data import load_panel
from .engine import (
    RunResult,
    cost_matrix,
    daily_returns,
    metrics,
    simulate,
    split_range,
)
from .registry import authorize, record_access, spec_id
from .signals import Ctx, build


class Lab:
    def __init__(self) -> None:
        self.panel = load_panel()
        self.ctx = Ctx(self.panel)
        self.cost = cost_matrix(self.panel)
        self.cost_stress = cost_matrix(self.panel, stress=2.0)
        self._w: dict = {}

    def weights(self, spec: dict):
        sid = spec_id(spec)
        if sid not in self._w:
            if len(self._w) > 6:
                self._w.pop(next(iter(self._w)))
            self._w[sid] = build(self.ctx, spec)
        return self._w[sid]

    def run(self, spec: dict, split: str, stress: bool = False) -> tuple[dict, RunResult]:
        authorize(spec, split)
        W, reb = self.weights(spec)
        k0, k1 = split_range(self.panel, split)
        res = simulate(self.panel, W, reb, k0, k1, self.cost_stress if stress else self.cost)
        return metrics(res), res

    def daily(self, spec: dict, split: str) -> pd.Series:
        _, res = self.run(spec, split)
        return daily_returns(res)


_LAB: Lab | None = None


def _init() -> None:
    global _LAB
    _LAB = Lab()


def _work(args):
    spec, split, stress = args
    assert _LAB is not None
    try:
        m, _ = _LAB.run(spec, split, stress)
        return spec_id(spec), m
    except Exception as exc:  # noqa: BLE001 - report per spec, keep sweep going
        return spec_id(spec), {"error": repr(exc)}


def sweep(specs: list[dict], split: str = "train", stress: bool = False, workers: int | None = None):
    """Evaluate many specs in parallel.  Returns {spec_id: metrics}."""
    workers = workers or min(6, os.cpu_count() or 2)
    if split != "train":
        # gate in the parent so a rejection is immediate
        for s in specs:
            authorize(s, split)
        record_access(split, [spec_id(s) for s in specs], "sweep")
    # group by family so each worker reuses cached features
    order = sorted(range(len(specs)), key=lambda i: (specs[i]["family"], canonical_key(specs[i])))
    chunks = [(specs[i], split, stress) for i in order]
    out = {}
    with ProcessPoolExecutor(max_workers=workers, initializer=_init) as ex:
        for sid, m in ex.map(_work, chunks, chunksize=8):
            out[sid] = m
    return out


def canonical_key(spec: dict) -> str:
    return str(sorted(spec["params"].items()))


def corr_matrix(lab: Lab, specs: list[dict], split: str) -> pd.DataFrame:
    cols = {}
    for s in specs:
        cols[spec_id(s)] = lab.daily(s, split)
    df = pd.DataFrame(cols).fillna(0.0)
    return df.corr()


def pass_flags(m: dict, min_calmar: float = 1.0) -> bool:
    return (
        "error" not in m
        and not m["ruined"]
        and np.isfinite(m["calmar"])
        and m["calmar"] > min_calmar
    )
