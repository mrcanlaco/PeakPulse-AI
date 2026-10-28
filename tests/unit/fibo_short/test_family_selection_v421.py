from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/fibo_research'))
import evaluate_family_v421 as e


def annual():
    return {str(y): {s['id']: {cost: {'return_pct': 1., 'max_dd_pct': 2.,
             'curve_values': [100., 101.], 'trades': 30, 'accepted_missing_execution_bars': 0,
             'execution_qualified': True} for cost in e.v.SCENARIOS} for s in e.v.FAMILY} for y in range(2020,2026)}


def test_prior_execution_issue_disqualifies_only_affected_policy():
    a = annual()
    best = e.choose(a, 2022)['selected']
    a['2021'][best]['standard_vip6']['execution_qualified'] = False
    choice = e.choose(a, 2022)
    assert choice['selected'] not in ('CASH', best)
    assert choice['audit'][best]['failed_rules'] == ['no_unresolved_accepted_execution_issues']


def test_current_and_future_quality_do_not_change_prior_selection():
    a = annual()
    before = e.choose(a, 2022)
    a.update({str(y): None for y in range(2022,2026)})
    assert e.choose(a, 2022) == before


def test_all_invalid_means_cash_without_relaxing_economic_rules():
    a = annual()
    for row in a['2020'].values():
        row['stress_regular']['execution_qualified'] = False
    choice = e.choose(a, 2022)
    assert choice['selected'] == 'CASH'
    assert all(x['rules']['linked_stress_nonnegative'] for x in choice['audit'].values())
