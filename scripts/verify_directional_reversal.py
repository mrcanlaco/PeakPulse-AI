"""Independent directional journal accounting, causal signal oracle and parity."""
import json
import numpy as np
import pandas as pd
from account_directional_replay import simulate
from capital_research_metrics import audit_account, utilization
from compare_account_risk import ROOT, sha, write, exchange_rules
from directional_reversal_signals import generate
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from search_directional_reversal import OUT, PRIOR, SIGNALS, DATA, WINDOWS, BOUNDARIES, COSTS, definitions, select, exit_diagnostics
from search_multitimeframe_rolling import grouped_signals


def strip_side(value):
    if isinstance(value, list): return [strip_side(x) for x in value]
    if isinstance(value, dict): return {k: strip_side(v) for k, v in value.items() if k != "side"}
    return value


def long_oracle(hourly):
    # Independently enumerate completed blocks and explicit rolling windows.
    bars = hourly.resample("4h", closed="right", label="right", origin="epoch").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("quote_volume", "sum"), count=("close", "count"))
    bars.loc[bars["count"].ne(4), ["open", "high", "low", "close", "volume"]] = np.nan
    a = bars.to_dict("records"); last = -(10**18); rows = []
    for i in range(71, len(a)):
        b = a[i]; prev = a[i-1]
        if any(q["count"] != 4 for q in a[i-71:i+1]): continue
        if sum(q["volume"] for q in a[i-5:i+1]) < 2_000_000: continue
        prior_closes = [q["close"] for q in a[i-20:i]]
        mean, std = float(np.mean(prior_closes)), float(np.std(prior_closes))
        lower = mean - 2 * std
        if not (std > 0 and prev["close"] < lower and b["close"] >= lower
                and b["close"] > b["open"] and prev["close"] / a[i-7]["close"] - 1 <= -.05): continue
        at = int(bars.index[i].timestamp() * 1000)
        if at - last < 86400000: continue
        atr = sum(max(a[k]["high"]-a[k]["low"], abs(a[k]["high"]-a[k-1]["close"]),
                      abs(a[k]["low"]-a[k-1]["close"])) for k in range(i-13, i+1)) / 14
        if not np.isfinite(atr) or atr <= 0: continue
        last = at; rows.append((at, atr, (mean-prev["close"])/std))
    return rows


def audit_directional(raw, curve, prices, funding, fee, slip, cap):
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
                pending = 2 * 25/3
                assert equity - used + 1e-7 >= j["qty"]*j["price"]/5 + 2*f + pending/5 + 2*fee*pending
                active[coin] = dict(qty=0., basis=0., direction=direction, side=j["side"], entry_fee=0.,
                                    funding=0., event=j["event_id"], since=j["at"], opened=j["at"])
            else:
                inventory(coin, active[coin], j["at"])
            p = active[coin]; assert p["side"] == j["side"] and p["event"] == j["event_id"]
            p["qty"] += j["qty"]; p["basis"] += j["qty"]*j["price"]; p["entry_fee"] += f; p["since"] = j["at"]
            wallet -= f; fees += f; cash(j["at"], -f); fills += 1
            assert len(active) <= cap and p["basis"] <= 25 + 1e-7
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


def main():
    s = json.loads((OUT/"summary.json").read_text(encoding="utf-8")); p = s["protocol"]
    assert sha(ROOT/"configs/live.yaml") == p["live_config_sha256"] and sha(RULE_PATH) == p["rules_sha256"]
    assert sha(DATA/"reconciled_manifest.json") == p["data_sha256"] and sha(PRIOR/"summary.json") == p["prior_sha256"] and sha(SIGNALS) == p["signals_sha256"]
    for name, digest in p["source_sha256"].items(): assert sha(ROOT/"scripts"/name) == digest
    assert definitions(json.loads((PRIOR/"summary.json").read_text(encoding="utf-8"))) == s["specs"]
    assert select(s["specs"], s["results"]) == s["selected"] == json.loads((OUT/"candidate_lock.json").read_text())["selected"]
    prices, funding, frames = load(); rules = exchange_rules(RULE_PATH)
    shorts = json.loads(SIGNALS.read_text(encoding="utf-8")); saved = json.loads((OUT/"signals.json").read_text(encoding="utf-8"))
    fresh, obs = generate(frames, funding, shorts); assert fresh == saved
    checked = 0
    for coin, frame in frames.items():
        if coin == "BTCUSDT": continue
        expected = long_oracle(frame); actual = [r for r in saved["long_mask0"] if r["symbol"] == coin]
        assert [q[0] for q in expected] == [r["at"] for r in actual], coin
        for (_, atr, score), row in zip(expected, actual):
            assert abs(atr-row["atr"]) < 1e-8 and abs(score-row["probability"]) < 1e-6
            checked += 1
    prefixes = 0
    for cut in ["2025-11-15 13:00", "2026-03-01 17:00", "2026-07-15 10:00"]:
        t = pd.Timestamp(cut, tz="UTC"); ms = int(t.timestamp()*1000)
        result, _ = generate({c:f.loc[:t] for c,f in frames.items()},
                             {c:[r for r in rows if r[0]<=ms] for c,rows in funding.items()}, shorts)
        for key in ["long_mask0", "long_mask2"]:
            assert result[key] == [r for r in saved[key] if r["at"] <= ms]; prefixes += 1
    print("SIGNALS", checked, "PREFIXES", prefixes, flush=True)
    specs = {r["id"]: r for r in s["specs"]}; baselines = fc = fills = curve_checks = 0; incomplete = []
    for row in s["results"]:
        raw = json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"))
        curve = pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet")
        start, end = WINDOWS[row["window"]]; sp = specs[row["strategy_id"]]
        _, fee, slip = next(v for v in COSTS if v[0] == row["cost"])
        audit_account(raw, 25, sp["cap"])
        assert utilization(curve, raw, 25, sp["cap"]) == row["utilization"]
        assert exit_diagnostics(raw) == row["exit_diagnostics"]
        assert monthly_metrics(curve.to_dict("records"), boundaries=[t for t in BOUNDARIES if start<=t<=end]) == row["monthly"]
        assert row["target_met"] == (raw["ending_equity"] is not None and row["monthly"]["all_months_50pct"])
        a,b,c = audit_directional(raw, curve, prices, funding, fee, slip, sp["cap"]); fc+=a; fills+=b; curve_checks+=c
        if raw["ending_equity"] is None:
            assert raw["errors"] and not row["target_met"]; incomplete.append(row["id"])
        else: assert curve["at"].iloc[-1] == end and abs(curve.equity.iloc[-1]-raw["ending_equity"]) < 1e-8
        if curve.paused.any():
            first = curve.loc[curve.paused, "at"].iloc[0]
            assert curve.loc[curve["at"]>=first, "paused"].all()
            assert not any(j["kind"] in ["entry", "entry_add"] and j["at"]>first for j in raw["journal"])
        if row["baseline"]:
            ref = f"{row['window']}_{row['cost']}_{sp['reference_id']}"
            assert strip_side(raw) == json.loads((PRIOR/"runs"/f"{ref}.json").read_text(encoding="utf-8")), row["id"]
            pd.testing.assert_frame_equal(curve, pd.read_parquet(PRIOR/"runs"/f"{ref}_equity.parquet"), check_exact=True); baselines += 1
    print("AUDITED", len(s["results"]), "BASELINES", baselines, flush=True)
    cases = {(r["strategy_id"], "later") for r in s["selected"] if r["strategy_id"]}
    cases |= {("both_mask2_n25_hold_cap5", "year"), ("long_mask0_n25_hold_cap5", "year")}
    exact = 0
    for ident, window in sorted(cases):
        sp = specs[ident]; start,end = WINDOWS[window]
        for cost, fee, slip in COSTS:
            r = simulate(list(range(start,end+1,300000)), grouped_signals(saved[sp["source"]["id"]],start,end),
                lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(sp["cap"],fee,slip),research_policy=sp["policy"])
            r["liquidation_status"] = "verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
            key = f"{window}_{cost}_{ident}"
            assert {k:v for k,v in r.items() if k!="curve"} == json.loads((OUT/"runs"/f"{key}.json").read_text(encoding="utf-8"))
            pd.testing.assert_frame_equal(pd.DataFrame(r["curve"]),pd.read_parquet(OUT/"runs"/f"{key}_equity.parquet"),check_exact=True); exact+=1
    write(OUT/"verification.json", dict(journals_audited=len(s["results"]),baseline_paths_exact=baselines,
        independent_long_signals=checked,causal_prefixes=prefixes,funding_quantities_checked=fc,
        directional_fills_checked=fills,equity_states_reconstructed=curve_checks,replayed_paths_exact=exact,
        incomplete_paths=incomplete,hashes_match=True,live_config_unchanged=True))
    print("VERIFIED", flush=True)


if __name__ == "__main__": main()
