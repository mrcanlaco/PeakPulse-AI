import pytest

from scripts.research_reversal_20261013 import risk_extension as r


def test_short_boundary_solves_equity_equals_maintenance():
    collateral,notional,mmr,funding,fee=100.,2000.,.005,-12.,.001
    move=r.short_boundary(collateral,notional,mmr,funding,fee)
    mark_ratio=1+move
    equity=collateral-notional*fee+funding-notional*move
    assert equity==pytest.approx(mmr*notional*mark_ratio)


def test_more_negative_funding_moves_liquidation_closer():
    assert r.short_boundary(100,2000,signed_funding=-12)<r.short_boundary(100,2000)


def test_wallet_collateral_vs_isolated_margin_gives_different_boundary():
    assert r.short_boundary(1000,2000)==pytest.approx(.4925373134328359)
    assert r.short_boundary(100,2000)==pytest.approx(.044776119402985204)
    assert r.short_boundary(100,2000)<r.short_boundary(1000,2000)


def test_high_leverage_funding_stops_at_first_breach_without_fake_nav():
    x=r.constant_mark_carry(50,-.01,1)
    assert x['first_modeled_breach_hour']==2
    assert len(x['payments'])==2 and x['ending_equity'] is None
    assert x['status']=='margin_breach_unresolved'


def test_positive_funding_received_by_short_and_no_entry_time_charge():
    x=r.constant_mark_carry(20,.001,8)
    assert len(x['payments'])==6 and x['payments'][0]['hour']==8
    assert x['funding_cost_to_stop']==pytest.approx(-12.)
    assert x['ending_equity']==pytest.approx(110.)


def test_negative_funding_0p1pct_8h_costs30pct_of50x_initial_margin():
    x=r.constant_mark_carry(50,-.001,8)
    assert x['funding_cost_fraction_of_initial_margin']==pytest.approx(.30)
    assert x['first_modeled_breach_hour'] is None


def test_missing_finance_does_not_become_zero_cost():
    assert r.carry_to_horizon({'eligible':False},48) is None


def test_funding_capped_at_actual_exit_and_horizon_boundary_included():
    x={'eligible':True,'fills':[{'timestamp':'2026-01-01T00:00:00Z'}],
       'exit_time':'2026-01-01T08:00:00Z','funding_payments':[
           {'timestamp':'2026-01-01T00:00:00Z','cash_flow':-99.},
           {'timestamp':'2026-01-01T04:00:00Z','cash_flow':-.01},
           {'timestamp':'2026-01-01T08:00:00Z','cash_flow':-.02},
           {'timestamp':'2026-01-01T12:00:00Z','cash_flow':-88.}]}
    assert r.carry_to_horizon(x,6)==pytest.approx(.01)
    assert r.carry_to_horizon(x,48)==pytest.approx(.03)


@pytest.mark.parametrize('collateral,notional',[(0,100),(100,0),(-1,100)])
def test_invalid_margin_inputs_rejected(collateral,notional):
    with pytest.raises(ValueError): r.short_boundary(collateral,notional)
