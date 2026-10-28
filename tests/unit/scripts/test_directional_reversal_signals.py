import sys
from pathlib import Path
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from directional_reversal_signals import long_conditions


@pytest.mark.parametrize("mutation", [None, "prior_not_oversold", "not_reentered", "not_green", "not_down5", "not_ready"])
def test_long_requires_prior_oversold_and_current_completed_recovery(mutation):
    h = pd.DataFrame(dict(open=[100., 95.], close=[94., 97.], mean20=[100., 100.], std20=[2., 2.],
                          ret24=[-.06, -.01], ready=[True, True]))
    if mutation == "prior_not_oversold": h.loc[0, "close"] = 96.
    if mutation == "not_reentered": h.loc[1, "close"] = 95.5
    if mutation == "not_green": h.loc[1, "open"] = 98.
    if mutation == "not_down5": h.loc[0, "ret24"] = -.04
    if mutation == "not_ready": h.loc[1, "ready"] = False
    hit, score = long_conditions(h)
    assert not hit.iloc[0]
    assert bool(hit.iloc[1]) == (mutation is None)
    if mutation is None: assert score.iloc[1] == 3.
