from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
import research_v418 as v


def test_exact_user_endpoints_and_entire_grid():
    assert len(v.SCENARIOS)==10
    assert {(a['fee_bps'],a['slippage_bps']) for a in v.SCENARIOS.values()}=={(fee,float(slip)) for fee in (2.5,5.) for slip in (10,20,30,40,50)}
    for a,b in v.ENDPOINTS.items():assert v.SCENARIOS[a]==v.x.SCENARIOS[b]


def test_nonmonotone_returns_keep_both_observed_sign_changes():
    rows=[{'slippage_bps':s,'return_pct':p} for s,p in [(10,2),(20,-1),(30,1),(40,.5),(50,-2)]]
    out=v.observed_sign_changes(rows)
    assert [p['direction'] for p in out]==['positive_to_nonpositive','nonpositive_to_positive','positive_to_nonpositive']
    assert [(a['left_slippage_bps'],a['right_slippage_bps']) for a in out]==[(10,20),(20,30),(40,50)]
    assert all('break_even_bps' not in a for a in out)


def test_no_unobserved_threshold_from_all_positive_or_negative_grid():
    assert v.observed_sign_changes([{'slippage_bps':10,'return_pct':2},{'slippage_bps':50,'return_pct':1}])==[]
    assert v.observed_sign_changes([{'slippage_bps':10,'return_pct':-1},{'slippage_bps':50,'return_pct':-2}])==[]


def test_exact_zero_is_a_nonpositive_observation():
    a=v.observed_sign_changes([{'slippage_bps':10,'return_pct':1},{'slippage_bps':20,'return_pct':0}])
    assert a[0]['right_return_pct']==0 and a[0]['direction']=='positive_to_nonpositive'
