"""Independent side-aware accounting from batch19, parameterized total budget.

Reconstructs every sampled wallet and marked equity state from signed fills.
Entry capital checks are necessary conditions; pending reserves on other
positions are checked by the engine and focused tests, not reconstructed here.
"""
import numpy as np


def audit_directional(raw, curve, prices, funding, fee, slip, cap, notional=25):
    active = {}; wallet = 500.; fees = carry = net = 0.; funding_checks = fills = 0
    at = curve["at"].to_numpy(); delta = np.zeros(len(at)); unrealized = np.zeros(len(at))
    schedules = {c: {t: (r, m) for t, r, m in rows} for c, rows in funding.items()}

    def cash(time, amount):
        index = int(np.searchsorted(at, time))
        if index < len(at): delta[index] += amount

    def inventory(coin, p, until):
        lo, hi = np.searchsorted(at, [p["since"], until])
        if hi <= lo: return
        q = prices[coin]; indices = np.searchsorted(q.mark_times, at[lo:hi] - 300000)
        assert np.all(q.mark_times[indices] == at[lo:hi] - 300000)
        unrealized[lo:hi] += p["direction"] * (p["qty"] * q.marks[indices] - p["basis"])

    for j in raw["journal"]:
        coin = j["symbol"]; direction = 1 if j["side"] == "LONG" else -1
        if j["kind"] in ["entry", "entry_add"]:
            ref = prices[coin].get(j["at"])["entry_open"]
            assert abs(j["price"] - ref * (1 + direction * slip/10000)) < 1e-8
            f = j["qty"] * j["price"] * fee
            if j["kind"] == "entry":
                assert coin not in active
                marks = {c: prices[c].get(j["at"])["mark"] for c in active}
                equity = wallet + sum(p["direction"] * (p["qty"] * marks[c] - p["basis"]) for c, p in active.items())
                used = sum(p["qty"] * marks[c] / 5 for c, p in active.items())
                # Necessary condition; does not claim reconstructing all other
                # coins' pending-tranche reserves (covered by engine tests).
                pending = 2 * notional/3
                assert equity - used + 1e-7 >= j["qty"]*j["price"]/5 + 2*f + pending/5 + 2*fee*pending
                active[coin] = dict(qty=0., basis=0., direction=direction, side=j["side"], entry_fee=0.,
                                    funding=0., event=j["event_id"], since=j["at"], opened=j["at"])
            else:
                inventory(coin, active[coin], j["at"])
            p = active[coin]; assert p["side"] == j["side"] and p["event"] == j["event_id"]
            p["qty"] += j["qty"]; p["basis"] += j["qty"]*j["price"]; p["entry_fee"] += f; p["since"] = j["at"]
            wallet -= f; fees += f; cash(j["at"], -f); fills += 1
            assert len(active) <= cap and p["basis"] <= notional + 1e-7
        elif j["kind"] == "funding":
            p = active[coin]; rate, mark = schedules[coin][j["at"]]
            assert p["opened"] < j["at"] and p["side"] == j["side"]
            assert abs(-p["direction"] * p["qty"] * mark * rate - j["amount"]) < 1e-8
            p["funding"] += j["amount"]; carry += j["amount"]; wallet += j["amount"]; cash(j["at"], j["amount"])
            funding_checks += 1
        elif "net" in j:
            p = active.pop(coin); assert p["side"] == j["side"] and p["event"] == j["event_id"]
            inventory(coin, p, j["at"])
            ref = prices[coin].get(j["at"])["entry_open"]
            assert abs(j["price"] - ref*(1-direction*slip/10000)) < 1e-8
            f = p["qty"] * j["price"] * fee
            gross = direction * (p["qty"]*j["price"] - p["basis"])
            expected = gross - f - p["entry_fee"] + p["funding"]
            assert abs(j["net"] - expected) < 1e-7
            wallet += gross-f; fees += f; net += expected; cash(j["at"], gross-f); fills += 1
    for coin, p in active.items():
        inventory(coin, p, int(at[-1])+1)
        saved = next(x for x in raw["open_positions"] if x["symbol"] == coin)
        assert saved["side"] == p["side"] and abs(saved["qty"]-p["qty"]) < 1e-8
        assert abs(saved["unrealized"] - p["direction"] * (p["qty"]*saved["last_mark"]-p["basis"])) < 1e-7
    np.testing.assert_allclose(500+np.cumsum(delta), curve.wallet, rtol=0, atol=1e-6)
    np.testing.assert_allclose(unrealized, curve.unrealized, rtol=0, atol=1e-6)
    np.testing.assert_allclose(500+np.cumsum(delta)+unrealized, curve.equity, rtol=0, atol=1e-6)
    assert abs(fees-raw["fees"]) < 1e-7 and abs(carry-raw["funding"]) < 1e-7
    assert abs(net-raw["closed_trade_net"]) < 1e-6
    return funding_checks, fills, len(at)
