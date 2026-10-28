"""Batch21: fixed direction slots and monthly-start robustness of frozen picks."""
import json
import pandas as pd
from account_side_quota_replay import simulate
from capital_research_metrics import utilization
from compare_account_risk import ROOT,sha,write,summarize,exchange_rules
from directional_capacity_metrics import side_metrics
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from search_frozen_exits import DATA,WINDOWS as ORIGINAL_WINDOWS,BOUNDARIES,COSTS,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals

OUT=ROOT/"artifacts/side_capacity_20260925"
PRIOR=ROOT/"artifacts/directional_trend_20260925"
REFERENCES=["breakout_any_both_trend_n25_hold","breakout_breadth60_btc_both_trend_n100_hold","pullback_any_hybrid_n25_hold"]


def windows():
    result=dict(ORIGINAL_WINDOWS)
    for i in range(9):
        label=pd.Timestamp(BOUNDARIES[i],unit="ms",tz="UTC").strftime("%Y_%m")
        result["roll_"+label]=(BOUNDARIES[i],BOUNDARIES[i+3])
    return result


def definitions(previous):
    assert {x["strategy_id"] for x in previous["selected"] if x["strategy_id"]}==set(REFERENCES)
    specs=[]
    for ref in REFERENCES:
        old=next(p for p in previous["specs"] if p["id"]==ref)
        for long in [None,1,2,3,4]:
            allocation="shared" if long is None else f"L{long}S{5-long}"
            policy=dict(old["policy"])
            if long is not None:policy["side_caps"]={"LONG":long,"SHORT":5-long}
            specs.append(dict(old,id=f"{ref}_{allocation}",allocation=allocation,reference_id=ref,policy=policy,baseline=long is None))
    old=next(p for p in previous["specs"] if p["id"]=="control_short")
    specs.append(dict(old,id="short_control",reference_id="control_short",allocation="shared",baseline=True))
    return specs


def select(specs,results):
    selected=[]
    for reference in REFERENCES:
        candidates=[]
        for sp in specs:
            if sp["reference_id"]!=reference:continue
            rs=[r for r in results if r["strategy_id"]==sp["id"] and r["window"]=="development"]
            if len(rs)!=2 or any(r["ending_equity"] is None or r["ending_equity"]<=500 or r["max_drawdown"]>=.20
                or not r["monthly"]["complete"] or r["exits"]<20 for r in rs):continue
            candidates.append((min(r["monthly"]["min_monthly_return"] for r in rs),min(r["ending_equity"] for r in rs),sp["id"]))
        selected.append(dict(reference_id=reference,strategy_id=max(candidates)[2] if candidates else None))
    return selected


def robustness(results):
    output=[]
    for ident in sorted({r["strategy_id"] for r in results}):
        for cost in ["base","stress"]:
            rs=[r for r in results if r["strategy_id"]==ident and r["cost"]==cost and (r["window"].startswith("roll_") or r["window"]=="later")]
            assert len(rs)==10
            complete=[r for r in rs if r["ending_equity"] is not None]
            nonoverlap=[r for r in rs if r["window"] in ["roll_2025_09","roll_2025_12","roll_2026_03","later"]]
            output.append(dict(strategy_id=ident,cost=cost,windows=10,complete=len(complete),profitable=sum(r["ending_equity"]>500 for r in complete),
                worst_ending=min((r["ending_equity"] for r in complete),default=None),best_ending=max((r["ending_equity"] for r in complete),default=None),
                median_ending=float(pd.Series([r["ending_equity"] for r in complete]).median()) if complete else None,
                worst_drawdown=max(r["max_drawdown"] for r in rs),all_starts_profitable=len(complete)==10 and all(r["ending_equity"]>500 for r in complete),
                each_month_50pct_all_starts=all(r["target_met"] for r in rs),
                nonoverlapping_profitable=sum(r["ending_equity"] is not None and r["ending_equity"]>500 for r in nonoverlap),
                nonoverlapping_complete=sum(r["ending_equity"] is not None for r in nonoverlap),
                note="Overlapping3monthstartsarenotindependentsamples;allretrospective. Missingpathsnotexcludedfromdenominator."))
    return output


def main():
    OUT.mkdir(exist_ok=True);(OUT/"runs").mkdir(exist_ok=True)
    previous=json.loads((PRIOR/"summary.json").read_text(encoding="utf-8"));specs=definitions(previous);spans=windows()
    protocol=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),specs=specs,windows=spans,costs=COSTS,
        previous_turn_classification="progress:306trendpaths/88tests/18exactcontrols;smalltrendbothprofitablelaterbutnegativeJuly,andgated100candidatefilledonlyShort.",
        hypothesis="Doesone-sidedslotcapturehideusefuloppositesignals? ReservedLong/Shortquotaspreventone-sidedcapture;monthlystartsmeasuredependenceoninitialinventory.",
        account="Same500Crossx5,cap5,3favorableparts0.25ATR/6hexpiry,trail3ATR/1%,noSL/notimeexit,20%persistentopeningpause. Frozen3sourcesandnotional25/100;totalnotionalnotpertranche. Sharedwallet,onepositionpercoin,fee/funding/MTM unchanged. 100notionalofflinealternative only.",
        allocation="Shared5slotsvsL1S4,L2S3,L3S2,L4S1hardcaps. Emptyoppositeslotscannotbeborrowed;noforcedclose/rebalance/resumewhenquotabinds. Quotasapplypositionsnottranches;addsuseoriginalposition. Deniedeventsnotretriedlater.",
        evaluation="Exactly3previousprelockedcandidatesx5allocations+frozenShortcontrol=16policies. Originaldevelopment/later/yearplus9additional3monthstartsSep2025-May2026:12windowsx2cost=384paths. Jun2026startislater,notduplicated. 24sharedoriginalwindowcontrols mustmatchexactly.",
        selection="ChooseoneallocationperreferenceusingSep-Mayalone;bothcostending>500,DD<20%,20closedtrades,complete. Rankworstminmonthlythenworstending,lockbeforelater/rolling. Sourcesalreadyselectedonthishistory,rollingwindowsmixtrainingandpreviouslyinspectedhistory. No pristineOOS/independenceclaim.",
        target="50%netMTM EVERYcalendar month;allstartrobustnessreportedseparately,notreplacegoalwithprofitabletotals.",
        limitations=previous["protocol"]["limitations"],live_config_sha256=sha(ROOT/"configs/live.yaml"),rules_sha256=sha(RULE_PATH),
        data_sha256=sha(DATA/"reconciled_manifest.json"),prior_sha256=sha(PRIOR/"summary.json"),signals_sha256=sha(PRIOR/"signals.json"),
        source_sha256={n:sha(ROOT/"scripts"/n) for n in ["account_side_quota_replay.py","account_directional_replay.py","directional_capacity_metrics.py",
            "search_side_capacity.py","research_directional_audit.py","frozen_extension_inputs.py","monthly_account_metrics.py"]})
    write(OUT/"protocol.json",protocol)
    original=json.loads((PRIOR/"signals.json").read_text(encoding="utf-8"))
    signals={k:original[k] for k in {s["source"]["id"] for s in specs}};write(OUT/"signals.json",signals)
    prices,funding,_=load();rules=exchange_rules(RULE_PATH);results=[];selected=[]
    for window,(start,end) in spans.items():
        grouped={k:grouped_signals(v,start,end) for k,v in signals.items()}
        for sp in specs:
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),grouped[sp["source"]["id"]],lambda c:prices.get(c,{}),rules,
                    lambda c:funding[c],configuration(5,fee,slip),research_policy=sp["policy"])
                r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                row=summarize(r,sp["id"],sp["id"],sp["policy"],5,cost,window)
                row.update(id=f"{window}_{cost}_{sp['id']}",strategy_id=sp["id"],source=sp["source"],notional=sp["notional"],baseline=sp["baseline"],
                    reference_id=sp["reference_id"],allocation=sp["allocation"],utilization=utilization(r["curve"],r,sp["notional"]),
                    side_metrics=side_metrics(r,r["curve"],sp["policy"].get("side_caps")),exit_diagnostics=exit_diagnostics(r),
                    monthly=monthly_metrics(r["curve"],boundaries=[t for t in BOUNDARIES if start<=t<=end]),
                    side_entries={side:sum(j["kind"]=="entry" and j["side"]==side for j in r["journal"]) for side in ["LONG","SHORT"]})
                row["target_met"]=r["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                write(OUT/"runs"/f"{row['id']}.json",{k:v for k,v in r.items() if k!="curve"})
                pd.DataFrame(r["curve"]).to_parquet(OUT/"runs"/f"{row['id']}_equity.parquet",index=False);results.append(row)
            write(OUT/"progress.json",dict(window=window,finished=sp["id"],runs=len(results)))
        print(window,"COMPLETE",len(results),flush=True)
        if window=="development":
            selected=select(specs,results);write(OUT/"candidate_lock.json",dict(selected=selected,locked_at=pd.Timestamp.now(tz="UTC").isoformat(),later_not_run_in_batch=True,pristine_oos=False))
            print("LOCKED",selected,flush=True)
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    write(OUT/"summary.json",dict(protocol=protocol,specs=specs,selected=selected,results=results,robustness=robustness(results),
        target_met_rows=sum(r["target_met"] for r in results),incomplete_paths=sum(r["ending_equity"] is None for r in results)))
    pd.DataFrame(results).to_csv(OUT/"comparison.csv",index=False);print("COMPLETE",len(results),flush=True)


if __name__=="__main__":main()
