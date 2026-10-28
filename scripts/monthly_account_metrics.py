"""Measure consecutive monthly marked returns, not closed-trade profits."""

import pandas as pd

BOUNDARIES = [
    int(pd.Timestamp(t, tz="UTC").timestamp() * 1000)
    for t in ["2026-06-24", "2026-07-24", "2026-08-24", "2026-09-24"]
]


def monthly_metrics(curve, initial=500, boundaries=None):
    boundaries = BOUNDARIES if boundaries is None else boundaries
    points = {p["at"]: p["equity"] for p in curve}
    equity = initial
    months = []
    for start, end in zip(boundaries, boundaries[1:]):
        if end not in points or equity <= 0:
            return dict(
                complete=False,
                months=months,
                all_months_50pct=False,
                min_monthly_return=None,
            )
        finish = points[end]
        ret = finish / equity - 1
        months.append(
            dict(
                start=start,
                end=end,
                start_equity=equity,
                end_equity=finish,
                pnl=finish - equity,
                return_fraction=ret,
                required_end_equity=equity * 1.5,
            )
        )
        equity = finish
    return dict(
        complete=True,
        months=months,
        all_months_50pct=all(m["return_fraction"] >= 0.5 for m in months),
        min_monthly_return=min(m["return_fraction"] for m in months),
    )
