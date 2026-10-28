from pathlib import Path
import math
from statistics import NormalDist
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
from oos_planning_v426 import block_sigma, power_plan, weekly_log_returns


def test_nist_one_sided_sample_size_example_and_boundary_power():
    # NIST: delta=sigma, alpha=.05, beta=.10 gives ceil(8.567)=9.
    annual = math.expm1(52*.01)
    out = power_plan(.01, annual, 9, target_power=.9)
    assert out['required_weeks_normal_approx'] == 9
    assert out['power_at_horizon'] >= .9
    assert power_plan(.01, annual, 8, target_power=.9)['power_at_horizon'] < .9


def test_multiple_claims_need_more_observations_and_reduce_power():
    single = power_plan(.01, .10, 52, 1)
    family = power_plan(.01, .10, 52, 12)
    assert family['required_weeks_normal_approx'] > single['required_weeks_normal_approx']
    assert family['power_at_horizon'] < single['power_at_horizon']
    delta = math.log1p(.1)/52
    threshold = NormalDist().inv_cdf(1-.05/12)*.01/math.sqrt(52)
    independent_power = 1-NormalDist(mu=delta, sigma=.01/math.sqrt(52)).cdf(threshold)
    assert family['power_at_horizon'] == pytest.approx(independent_power, abs=1e-14)


def test_block_variance_equals_weighted_circular_autocovariance():
    a = np.array([.01, -.02, .03, .01, -.04, .02, -.01, .02, .01, -.02])
    centered = a-a.mean()
    for b in (1, 4, 8):
        variance = np.mean(centered**2)
        for lag in range(1, b):
            variance += 2*(1-lag/b)*np.mean(centered*np.roll(centered, -lag))
        assert block_sigma(a, b)**2 == pytest.approx(variance, abs=1e-15)
        assert block_sigma(a+7, b) == pytest.approx(block_sigma(a, b))


def test_calendar_omits_partial_weeks_and_uses_only_known_nav():
    grid = pd.date_range('2025-01-01', '2025-01-22', freq='D', tz='UTC')
    curve = [(int(t.timestamp()*1000), 100*math.exp(i*.001)) for i, t in enumerate(grid)]
    returns, boundaries = weekly_log_returns(curve, grid[0], grid[-1])
    assert len(returns) == 2
    assert boundaries == ['2025-01-06T00:00:00+00:00', '2025-01-13T00:00:00+00:00', '2025-01-20T00:00:00+00:00']
    np.testing.assert_allclose(returns, [.007, .007], atol=1e-14)
    curve[-1] = (curve[-1][0], 1000.)
    np.testing.assert_allclose(weekly_log_returns(curve, grid[0], grid[-1])[0], returns)


def test_post2025_observations_and_invalid_nav_rejected():
    times = pd.date_range('2025-01-01', '2026-01-02', freq='D', tz='UTC')
    curve = [(int(t.timestamp()*1000), 100.) for t in times]
    with pytest.raises(ValueError, match='Post-2025'):
        weekly_log_returns(curve, times[0], pd.Timestamp('2026-01-01T00:00:00Z'))
    with pytest.raises(ValueError, match='positive NAV'):
        weekly_log_returns([(curve[0][0], 100.), (curve[1][0], 0.)], times[0], times[1])
