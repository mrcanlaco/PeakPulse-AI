"""Tests pin audit semantics, including documented weaknesses in the old engine."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("trend_branch", ROOT / "scripts/research_branches_20261012/trend_branch.py")
branch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(branch)


def test_future_close_does_not_change_prior_nav():
    assert branch.causal_probes()["future_close_mutation_preserves_prior_nav"]


def test_intrabar_stop_is_not_a_hard_stop():
    assert branch.causal_probes()["intrabar_low_below_stop_ignored_when_close_recovers"]


def test_funding_valuation_uses_bar_close_not_settlement_price():
    probes = branch.causal_probes()
    assert probes["funding_same_open_base_close_100"] == 500
    assert probes["funding_at_open_100_but_close_200"] == 1000


def test_warmup_means_no_positions_first_300_bars():
    timeline, features, spec = branch.synthetic_features()
    nav, _ = branch.simulate_candidate(timeline, features, spec)
    assert np.all(nav.iloc[:300] == 100_000)
    assert nav.iloc[300] == 99_950


def test_audit_artifacts_are_write_once(tmp_path):
    path = tmp_path / "lock.json"
    branch.write_once(path, {"x": 1})
    with pytest.raises(FileExistsError):
        branch.write_once(path, {"x": 2})
