import math
import pytest
from scripts.research_branches_20261013 import v3_branch as branch


def event(net, reversal=True, funding=True, eligible=True):
    features = {"price_ret_1h": -.01 if reversal else .01, "funding_percentile_30d": .9 if funding else .5}
    return {"source_event_id": str(net), "features": features, "gates": branch.gates(features),
            "net_return_planned": net if eligible else None, "financially_eligible": eligible, "status": "target"}


def test_gate_boundaries():
    g = branch.gates({"price_ret_1h": 0, "funding_percentile_30d": .8})
    assert not g["A_reversal_1h"]
    assert g["B_crowded_funding"]
    assert not g["AB_reversal_and_funding"]


@pytest.mark.parametrize("bad", [None, math.nan, math.inf, True])
def test_missing_features_reject_not_impute(bad):
    g = branch.gates({"price_ret_1h": bad, "funding_percentile_30d": bad})
    assert list(g.values()) == [True, False, False, False]


def test_rejected_opportunity_zero_unknown_outcome_not_zero():
    report = branch.summary([event(.2), event(-.1, reversal=False), event(.8, eligible=False)])
    assert report["common_funded_opportunities"] == 2
    assert report["funding_or_financial_excluded_rows"] == 1
    a = report["variants"]["A_reversal_1h"]
    assert a["selected_only_mean_net_return_planned"] == pytest.approx(.2)
    assert a["opportunity_normalized_mean_net_return_planned"] == pytest.approx(.1)
    assert a["paired_mean_difference_vs_baseline"] == pytest.approx(.05)
    assert a["accepted_but_financially_excluded_rows"] == 1


def test_ablation_shares_common_denominator():
    report = branch.summary([event(.2), event(-.1, funding=False)])
    assert report["ablations"]["AB_minus_A_reversal_1h"]["mean_opportunity_difference"] == pytest.approx(.05)
    assert report["ablations"]["AB_minus_A_reversal_1h"]["changed_decision_count"] == 1


def test_no_evidence_is_not_zero_return():
    report = branch.summary([event(.2, eligible=False)])
    for variant in report["variants"].values():
        assert variant["opportunity_normalized_mean_net_return_planned"] is None


def test_hash_change_fails_closed(tmp_path):
    path = tmp_path / "data"
    path.write_text("modified", encoding="utf-8")
    with pytest.raises(RuntimeError, match="hash mismatch"):
        branch.verify_hashes({str(path): "0"*64})
