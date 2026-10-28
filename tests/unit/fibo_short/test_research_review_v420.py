from copy import deepcopy
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/fibo_research'))
from research_review_v420 import select_from_past


def annual():
    def metric(ret):
        return {'return_pct': ret, 'max_dd_pct': 15., 'curve_values': [100., 100. + ret],
                'trades': 30, 'accepted_missing_execution_bars': 0}
    return {str(y): {'A': {'standard_vip6': metric(1), 'stress_regular': metric(0)}} for y in range(2020, 2026)}


def test_selection_cannot_observe_test_or_future_years():
    a = annual()
    expected = select_from_past(a, 2022, ['A'])
    a.update({str(y): None for y in range(2022, 2026)})
    assert select_from_past(a, 2022, ['A']) == expected
    assert expected['selected'] == 'A'


def test_incomplete_past_is_rejected():
    a = annual()
    del a['2021']
    with pytest.raises(ValueError):
        select_from_past(a, 2022, ['A'])
    with pytest.raises(ValueError):
        select_from_past(annual(), 2021, ['A'])


def test_stress_loss_disqualifies_positive_standard_candidate():
    a = annual()
    a['2021']['A']['stress_regular'].update(return_pct=-1., curve_values=[100., 99.])
    result = select_from_past(a, 2022, ['A'])
    assert result['selected'] == 'CASH'
    assert result['audit']['A']['failed_rules'] == ['linked_stress_nonnegative']


def test_exact_thresholds_and_deterministic_tie():
    a = annual()
    for row in a.values():
        row['B'] = deepcopy(row['A'])
    result = select_from_past(a, 2022, ['B', 'A'])
    assert result['selected'] == 'A'
    a['2020']['A']['standard_vip6']['max_dd_pct'] = 15.00001
    assert select_from_past(a, 2022, ['A', 'B'])['selected'] == 'B'


def test_any_missing_execution_bar_blocks_candidate():
    a = annual()
    a['2020']['A']['stress_regular']['accepted_missing_execution_bars'] = 1
    assert select_from_past(a, 2022, ['A'])['selected'] == 'CASH'
