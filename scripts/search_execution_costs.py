"""Batch14: frozen strategies under explicit hypothetical cost scenarios."""

import json
from types import SimpleNamespace
import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import utilization
from compare_account_risk import ROOT,sha,write,summarize,exchange_rules
from execution_cost_attribution import attribute
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from search_market_breadth import OUT as PRIOR
from search_frozen_exits import DATA,WINDOWS,BOUNDARIES,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from dao_vang.config.settings import ExecutionConfig

OUT=ROOT/"artifacts/execution_costs_20260925"
PROFILES=[dict(id="no_cost_no_funding",fee=0,slip=0,funding=False,label="Giả định không phí, trượt giá và funding"),
          dict(id="no_execution_cost",fee=0,slip=0,funding=True,label="Không phí/trượt giá; funding thực"),
          dict(id="fee_only",fee=.0005,slip=0,funding=True,label="Phí 0,05%; không trượt giá"),
          dict(id="slip1",fee=.0005,slip=1,funding=True,label="Phí 0,05%; trượt 0,01%"),
          dict(id="slip5",fee=.0005,slip=5,funding=True,label="Phí 0,05%; trượt 0,05%"),
          dict(id="base",fee=.0005,slip=20,funding=True,label="Cơ sở: phí 0,05%; trượt 0,20%"),
          dict(id="stress",fee=.001,slip=50,funding=True,label="Cao: phí 0,10%; trượt 0,50%")]


def definitions(previous):
    ids=[]
    for n in [25,100]:ids += [f"benchmark_mask2_n{n}",f"raw7d_any_scheduled_n{n}_hold",f"beta7d_breadth75_btc_scheduled_n{n}_time168"]
    return [next(p for p in previous["specs"] if p["id"]==i) for i in ids]


def configuration(profile):
    # Offline diagnostic zero-slip scenarios are intentionally outside the live
    # config validator's gt=0 restriction. Never write this object to live YAML.
    return SimpleNamespace(**dict(ExecutionConfig(max_open_positions=5).model_dump(),fee_rate=profile["fee"],max_slippage_bps=profile["slip"]))


def main():
    OUT.mkdir(exist_ok=True);(OUT/"runs").mkdir(exist_ok=True)
    old=json.loads((PRIOR/"summary.json").read_text(encoding="utf-8"));specs=definitions(old)
    protocol=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),specs=specs,profiles=PROFILES,windows=WINDOWS,
        previous_turn_classification="progress:312 breadth/momentum paths verified; threechosen lateraccountslose,69tests. Needdistinguish poorpriceedge from execution/funding drag.",
        scope="Sixfrozenpolicies: reversalret6,raw7dweaknesswithoutmarketfilter/indefinitehold,beta7dweakness75percentbreadth+BTCbear/168hexit; notional25/100,500equity,x5,cap5. Same3favorabletranches0.25ATR andtrail3ATR/1%. No newstrategyselection. Original indefinitehold preserved;168hpolicyexplicitresearchalternative.",
        profile_description="7hypotheticalscenarios:zeroalltradingcostandfunding;zerofee/slipwithactualfunding;fee0.05percent/noslip;fee0.05percent/slip1,5,20bps;fee0.10percent/slip50bps. Fee/slip are perfill. Lowcostsnotcalibratedtohistoricdepth. No live/privateAPI/config change.",
        replay="6specs x3windows x7profiles=126paths. Fullreplaychanges quantity,eligibility,activation,capacity andDDpause. Lowercosts neednotmonotonicallyimprove realized path. Zero-costscenario is NOT a mathematical upperbound onallalternative strategies/paths. Purepricecase also removesfunding fromaccountcash, but signalshistory staysfrozen.",
        attribution="For sameactualfills: markedpricePnLatunslippednextopens +actualfunding -entry/exitadverseslippage -commissions =netMTMPnl. Keepactualquantitiesandexitdecisions. OpeninventoryusesfinalMark,no fictionalexitfee. Incompletepaths getno endingdecomposition. Fixed-pathbeforecost is conditional accounting,not executablecounterfactual. Costbudgetbps=(pricePnL+funding)/referencefilledturnover*10000;not calibratedfeasiblespread.",
        target="50% netmarkedgrowth EVERYconsecutivecalendar month. Zero-costresults cannotqualifylivepromotion. Not average,totalorbestmonth. No cherry-pickedcoinremoval.",
        limitations=old["protocol"]["limitations"],prior_sha256=sha(PRIOR/"summary.json"),signals_sha256=sha(PRIOR/"signals.json"),data_sha256=sha(DATA/"reconciled_manifest.json"),live_config_sha256=sha(ROOT/"configs/live.yaml"),
        source_sha256={n:sha(ROOT/"scripts"/n) for n in ["search_execution_costs.py","execution_cost_attribution.py","account_scaled_replay.py","frozen_extension_inputs.py","capital_research_metrics.py","monthly_account_metrics.py"]})
    write(OUT/"protocol.json",protocol)
    prices,funding,_=load();rules=exchange_rules(RULE_PATH);signals=json.loads((PRIOR/"signals.json").read_text(encoding="utf-8"));results=[]
    for i,spec in enumerate(specs,1):
        for window,(start,end) in WINDOWS.items():
            groups=grouped_signals(signals[spec["source"]["id"]],start,end)
            for profile in PROFILES:
                r=simulate(list(range(start,end+1,300000)),groups,lambda c:prices.get(c,{}),rules,lambda c:funding[c] if profile["funding"] else [],configuration(profile),research_policy=spec["policy"])
                r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                row=summarize(r,spec["id"],spec["id"],spec["policy"],5,profile["id"],window)
                row.update(id=f"{window}_{profile['id']}_{spec['id']}",strategy_id=spec["id"],source=spec["source"],notional=spec["notional"],holding=spec["holding"],cost_profile=profile,
                    attribution=attribute(r,lambda c:prices[c]),utilization=utilization(r["curve"],r,spec["notional"]),exit_diagnostics=exit_diagnostics(r),
                    monthly=monthly_metrics(r["curve"],boundaries=[t for t in BOUNDARIES if start<=t<=end]))
                row["target_met"]=r["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                write(OUT/"runs"/f"{row['id']}.json",{k:v for k,v in r.items() if k!="curve"});pd.DataFrame(r["curve"]).to_parquet(OUT/"runs"/f"{row['id']}_equity.parquet",index=False);results.append(row)
        write(OUT/"progress.json",dict(finished=i,total=len(specs),runs=len(results)));print("POLICY",i,"/",len(specs),flush=True)
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    write(OUT/"summary.json",dict(protocol=protocol,specs=specs,profiles=PROFILES,results=results,target_met_rows=sum(r["target_met"] for r in results),incomplete_paths=sum(r["ending_equity"] is None for r in results),live_config_unchanged=True))
    pd.DataFrame(results).to_csv(OUT/"comparison.csv",index=False);print("COMPLETE",len(results),flush=True)


if __name__=="__main__":main()
