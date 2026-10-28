"""Fixed-horizon short event returns, explicitly not portfolio backtest returns."""

from bisect import bisect_right

import numpy as np

DAY = 86400000


def event_return(entry_open, exit_open, funding_per_unit, fee, slip_bps):
    entry = entry_open * (1 - slip_bps / 10000)
    exit_price = exit_open * (1 + slip_bps / 10000)
    return (entry - exit_price + funding_per_unit - fee * (entry + exit_price)) / entry


def outcomes(signals, prices, funding, start, end, hours):
    """Screen return after fixed horizon, no intervening SL/MMR or capacity model.

    Censor events whose scheduled exit is outside the assessment window.
    Funding at entry excluded, funding at exit included, as in account replay.
    """
    prefixes = {}
    for coin, schedule in funding.items():
        stamps = [row[0] for row in schedule]
        cumulative = np.r_[0, np.cumsum([row[1] * row[2] for row in schedule])]
        prefixes[coin] = stamps, cumulative
    rows = []
    counts = dict(source=0, complete=0, censored=0, missing=0)
    for signal in signals:
        at = signal["at"]
        if not start <= at < end:
            continue
        counts["source"] += 1
        finish = at + hours * 3600000
        if finish >= end:
            counts["censored"] += 1
            continue
        coin = signal["symbol"]
        entry = prices.get(coin, {}).get(at, {}).get("entry_open", float("nan"))
        exit_price = (
            prices.get(coin, {}).get(finish, {}).get("entry_open", float("nan"))
        )
        if (
            not np.isfinite(entry)
            or not np.isfinite(exit_price)
            or min(entry, exit_price) <= 0
            or coin not in prefixes
        ):
            counts["missing"] += 1
            continue
        stamps, sums = prefixes[coin]
        funding_per_unit = (
            sums[bisect_right(stamps, finish)] - sums[bisect_right(stamps, at)]
        )
        counts["complete"] += 1
        rows.append(
            dict(
                event_id=signal["event_id"],
                symbol=coin,
                at=at,
                exit_at=finish,
                entry_open=entry,
                exit_open=exit_price,
                funding_per_unit=float(funding_per_unit),
            )
        )
    return rows, counts


def statistics(rows, start, end, fee, slip, samples=2000):
    if not rows:
        return dict(events=0, mean_net_return=None, ci95=None, positive_fraction=None)
    n_days = int(np.ceil((end - start) / DAY))
    totals, counts = np.zeros(n_days), np.zeros(n_days)
    values = []
    for row in rows:
        value = event_return(
            row["entry_open"], row["exit_open"], row["funding_per_unit"], fee, slip
        )
        day = (row["at"] - start) // DAY
        totals[day] += value
        counts[day] += 1
        values.append(value)
    rng = np.random.default_rng(20260925)
    origins = rng.integers(0, n_days, size=(samples, int(np.ceil(n_days / 7))))
    indices = ((origins[:, :, None] + np.arange(7)) % n_days).reshape(samples, -1)[
        :, :n_days
    ]
    denominators = counts[indices].sum(axis=1)
    estimates = (
        totals[indices].sum(axis=1)[denominators > 0] / denominators[denominators > 0]
    )
    return dict(
        events=len(values),
        mean_net_return=float(np.mean(values)),
        ci95=np.quantile(estimates, [0.025, 0.975]).tolist(),
        positive_fraction=float(np.mean(np.array(values) > 0)),
        bootstrap_valid_samples=len(estimates),
        bootstrap_method="Aligned cross-coin daily event clusters, circular7-day blocks, 2000 resamples; unadjusted for multiple testing. Overlapping positions are not an account.",
    )
