import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"scripts"))
from frozen_extension_inputs import join_funding


def frame(rows):return pd.DataFrame(rows,columns=["fundingTime","fundingRate","markPrice"])


def test_boundary_duplicate_settlement_not_double_charged():
    old=frame([(1,.01,100),(2,-.02,99)])
    new=frame([(2,-.02,99),(3,.03,101)])
    assert join_funding(old,new).to_dict("records")==frame([(1,.01,100),(2,-.02,99),(3,.03,101)]).to_dict("records")


@pytest.mark.parametrize("row",[(2,-.03,99),(2,-.02,98)])
def test_conflicting_funding_never_silently_deduplicated(row):
    with pytest.raises(ValueError,match="conflicting"):join_funding(frame([(2,-.02,99)]),frame([row]))
