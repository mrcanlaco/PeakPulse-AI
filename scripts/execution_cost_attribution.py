"""Same-fill price/funding/cost identity; not a counterfactual trade strategy."""

import math


def attribute(result,prices):
    """Use exact executed quantities; do not assume a different cost path agrees.

    Every supported exit is a market exit at next trade open plus slippage.
    A pending exit remains open at final Mark. No invented close commission.
    """
    if result["ending_equity"] is None:
        return dict(complete=False,price_pnl_at_reference=None,slippage_paid=None,commissions=result["fees"],
                    funding=result["funding"],net_marked_pnl=None,fixed_path_before_execution_cost=None,reference_turnover=None,fixed_path_cost_budget_bps=None)
    reference_cash=0.;slip=0.;turnover=0.;quantities={}
    for j in result["journal"]:
        if j["kind"] in ["entry","entry_add"]:
            ref=prices(j["symbol"]).get(j["at"])["entry_open"]
            assert math.isfinite(ref) and ref>0
            q=j["qty"];quantities[j["event_id"]]=quantities.get(j["event_id"],0)+q
            reference_cash+=q*ref;slip+=q*(ref-j["price"]);turnover+=q*ref
        elif "net" in j:
            if j["kind"]=="tp":raise ValueError("limit_exit_not_supported_for_market_cost_attribution")
            ref=prices(j["symbol"]).get(j["at"])["entry_open"];q=quantities.pop(j["event_id"])
            assert math.isfinite(ref) and ref>0
            reference_cash-=q*ref;slip+=q*(j["price"]-ref);turnover+=q*ref
    for p in result["open_positions"]:
        assert abs(quantities.pop(p["event_id"])-p["qty"])<1e-9
        reference_cash-=p["qty"]*p["last_mark"]
    assert not quantities
    net=reference_cash-slip-result["fees"]+result["funding"]
    assert abs(net-result["pnl"])<1e-6
    return dict(complete=True,price_pnl_at_reference=reference_cash,slippage_paid=slip,commissions=result["fees"],funding=result["funding"],
                net_marked_pnl=net,fixed_path_before_execution_cost=reference_cash+result["funding"],reference_turnover=turnover,
                fixed_path_cost_budget_bps=(reference_cash+result["funding"])/turnover*10000 if turnover else None)
