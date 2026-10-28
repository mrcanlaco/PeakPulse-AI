"""Batch20: trend-following Long and market-gated two-way portfolios."""
import json
from collections import Counter
import pandas as pd
from account_directional_replay import simulate
from directional_trend_signals import prepare, generate, definitions as source_definitions
from capital_research_metrics import utilization
from compare_account_risk import ROOT, sha, write, summarize, exchange_rules
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from search_frozen_exits import DATA, WINDOWS, BOUNDARIES, COSTS, exit_diagnostics
from search_multitimeframe_rolling import grouped_signals

OUT = ROOT/"artifacts/directional_trend_20260925"
PRIOR = ROOT/"artifacts/directional_reversal_20260925"


def definitions(previous):
    base = next(p for p in previous["specs"] if p["id"]=="short_mask2_n25_hold_cap5")["policy"]
    specs = []
    for source in source_definitions():
        for n in [25,100]:
            for hold in ["hold","time168"]:
                policy = dict(base,position_notional=n)
                if hold=="time168": policy["max_hold_hours"] = 168
                specs.append(dict(id=f"{source['id']}_n{n}_{hold}",source=source,mode=source["mode"],
                    notional=n,holding=hold,cap=5,policy=policy,baseline=False))
    for mode in ["short","long","both"]:
        ref = next(p for p in previous["specs"] if p["id"]==f"{mode}_mask2_n25_hold_cap5")
        specs.append(dict(ref,id="control_"+mode,reference_id=ref["id"],source=dict(id="control_"+mode),baseline=True))
    return specs


def select(specs, results):
    selected = []
    for mode in ["long","both_trend","hybrid"]:
        for n in [25,100]:
            candidates = []
            for sp in specs:
                if sp["baseline"] or sp["mode"]!=mode or sp["notional"]!=n: continue
                rs = [r for r in results if r["strategy_id"]==sp["id"] and r["window"]=="development"]
                if len(rs)!=2 or any(r["ending_equity"] is None or r["ending_equity"]<=500
                    or r["max_drawdown"]>=.20 or not r["monthly"]["complete"] or r["exits"]<20 for r in rs): continue
                candidates.append((min(r["monthly"]["min_monthly_return"] for r in rs),min(r["ending_equity"] for r in rs),sp["id"]))
            selected.append(dict(mode=mode,notional=n,strategy_id=max(candidates)[2] if candidates else None))
    return selected


def main():
    OUT.mkdir(exist_ok=True); (OUT/"runs").mkdir(exist_ok=True)
    previous = json.loads((PRIOR/"summary.json").read_text(encoding="utf-8")); specs = definitions(previous)
    protocol = dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),specs=specs,windows=WINDOWS,costs=COSTS,
        previous_turn_classification="progress:144directionalreversalpaths,78tests,48exactShortcontrols;Longreversaltrappedinventoryandbothsidesdidnotimproveyear.",
        hypothesis="ReplaceoversoldLongcatchingwithtrendcontinuation;gatenewentrydirectionbyclosedBTCandbroadmarketstate. Testwhetheritavoidslong-heldwrong-wayinventory.",
        signals="4hEMA20>60,close>EMA20,ret24>0,green forLong; mirrorforShort. Breakout:closebeyondprior20barhigh/low,volume>=1.5xprior20mean. Pullback:touchEMA20intrabarandclosebackontrendside,volume>=1x.72complete4hbars/ATR14>0/24hturnover>=2m.24hcooldownpercoinanddirection AFTERregimegate. Rankabs24hreturn/(ATR/close).",
        regime="Any vs>=24eligiblecoins,>=60%aboveEMA60andBTCuptrendforLong;>=60%belowEMA60andBTCdowntrendforShort. BTCtrendusesownEMA20/60,close,ret24andreadiness. Equalitynotcountedasaboveorbelow. Onlyclosed4hdata. No automaticexitwhenregimechanges.",
        modes="Longtrendonly;mirrorLong+Shorttrend;hybridLongtrend+frozenret6Shortreversal. HybridShortretainsfrozenevent/ATR/cooldownbutcommonpriorityreplacesoldzscore;gatedhybridShortneedsonlymarketbearstate,notcointrend. Samecoinoppositesblocked,sharedwallet/capacity,nonewshortlivefeature.",
        account="500USDT Crossx5,5slots,3favorableparts0.25ATRspace,6hexpiry,total25/100notional(5/20plannedmargin). Trail3ATR/1%,5mclosedobservation,nextopenadverseslip. OriginalnoSL/unlimitedhold vs168hforcedcloseincludinglosersresearchalternative. DD20%persistentopeningpause;oldpositionscontinue.No topups/compounding.",
        selection="48newpolicies+3frozencontrols=51x3windowsx2cost=306paths. Selectonepermode/notionalonSep-May:bothcostending>500,DD<20%,>=20closed,complete;rankworstminmonthlythenworstending. LockbeforeJune-Aug,nolaterreselection. Thisisretrospectivehistoryalreadyinspected,notpristineOOS.",
        target="Atleast50%netMTM EVERYcalendar month,notaverage,totalorbestmonth.",
        limitations=previous["protocol"]["limitations"],
        live_config_sha256=sha(ROOT/"configs/live.yaml"),rules_sha256=sha(RULE_PATH),data_sha256=sha(DATA/"reconciled_manifest.json"),
        prior_sha256=sha(PRIOR/"summary.json"),signals_sha256=sha(PRIOR/"signals.json"),
        source_sha256={n:sha(ROOT/"scripts"/n) for n in ["directional_trend_signals.py","search_directional_trend.py",
            "account_directional_replay.py","short_multitimeframe_signals.py","frozen_extension_inputs.py","monthly_account_metrics.py","research_capacity_config.py"]})
    write(OUT/"protocol.json",protocol)
    prices,funding,frames = load(); rules = exchange_rules(RULE_PATH)
    old_signals = json.loads((PRIOR/"signals.json").read_text(encoding="utf-8"))
    enriched,state = prepare(frames); signals = generate(enriched,state,old_signals["short_mask2"])
    for mode in ["short","long","both"]: signals["control_"+mode] = old_signals[f"{mode}_mask2"]
    write(OUT/"signals.json",signals); state.reset_index().to_parquet(OUT/"market_state.parquet",index=False)
    print("SIGNALS",{k:len(v) for k,v in signals.items()},flush=True)
    results = []; selected = []
    for window,(start,end) in WINDOWS.items():
        groups = {k:grouped_signals(v,start,end) for k,v in signals.items()}
        for i,sp in enumerate(specs,1):
            for cost,fee,slip in COSTS:
                r = simulate(list(range(start,end+1,300000)),groups[sp["source"]["id"]],lambda c:prices.get(c,{}),rules,
                    lambda c:funding[c],configuration(5,fee,slip),research_policy=sp["policy"])
                r["liquidation_status"] = "verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                row = summarize(r,sp["id"],sp["id"],sp["policy"],5,cost,window)
                row.update(id=f"{window}_{cost}_{sp['id']}",strategy_id=sp["id"],source=sp["source"],mode=sp["mode"],notional=sp["notional"],
                    holding=sp["holding"],baseline=sp["baseline"],utilization=utilization(r["curve"],r,sp["notional"]),
                    exit_diagnostics=exit_diagnostics(r),monthly=monthly_metrics(r["curve"],boundaries=[t for t in BOUNDARIES if start<=t<=end]),
                    side_entries=dict(Counter(j["side"] for j in r["journal"] if j["kind"]=="entry")))
                row["target_met"] = r["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                write(OUT/"runs"/f"{row['id']}.json",{k:v for k,v in r.items() if k!="curve"})
                pd.DataFrame(r["curve"]).to_parquet(OUT/"runs"/f"{row['id']}_equity.parquet",index=False); results.append(row)
            write(OUT/"progress.json",dict(window=window,finished=i,total=len(specs),runs=len(results)))
            if i%6==0 or i==len(specs): print(window,i,"/",len(specs),flush=True)
        if window=="development":
            selected = select(specs,results)
            write(OUT/"candidate_lock.json",dict(selected=selected,locked_at=pd.Timestamp.now(tz="UTC").isoformat(),later_not_run_in_batch=True,pristine_oos=False))
            print("LOCKED",selected,flush=True)
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    write(OUT/"summary.json",dict(protocol=protocol,specs=specs,selected=selected,results=results,
        target_met_rows=sum(r["target_met"] for r in results),incomplete_paths=sum(r["ending_equity"] is None for r in results)))
    pd.DataFrame(results).to_csv(OUT/"comparison.csv",index=False)
    print("COMPLETE",len(results),flush=True)


if __name__=="__main__":main()
