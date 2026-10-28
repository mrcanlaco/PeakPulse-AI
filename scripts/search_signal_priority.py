"""Batch22: rank competing Short events without changing their timing or size."""
import json
import pandas as pd
from account_side_quota_replay import simulate
from capital_research_metrics import utilization
from compare_account_risk import ROOT,sha,write,summarize,exchange_rules
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from search_side_capacity import windows,robustness,BOUNDARIES,COSTS,DATA
from search_frozen_exits import exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from short_signal_priority import RANKS,observe,rank,collisions

OUT=ROOT/"artifacts/signal_priority_20260925"
PRIOR=ROOT/"artifacts/side_capacity_20260925"
SOURCE=ROOT/"artifacts/directional_reversal_20260925/signals.json"


def definitions(previous):
    base=next(s for s in previous["specs"] if s["id"]=="short_control")["policy"]
    specs=[]
    for key in RANKS:
        for cap in [3,5]:
            policy=dict(base)
            if cap==3:policy["side_caps"]={"LONG":2,"SHORT":3}
            specs.append(dict(id=f"{key}_cap{cap}",ranking=key,cap=cap,policy=policy,notional=25,
                baseline=(key,cap) in [("zscore",5),("impulse_atr",3)]))
    return specs


def select(specs,results):
    selected=[]
    for cap in [3,5]:
        candidates=[]
        for sp in specs:
            if sp["cap"]!=cap:continue
            rs=[r for r in results if r["strategy_id"]==sp["id"] and r["window"]=="development"]
            if len(rs)!=2 or any(r["ending_equity"] is None or r["ending_equity"]<=500 or r["max_drawdown"]>=.20
                or r["exits"]<20 or not r["monthly"]["complete"] for r in rs):continue
            candidates.append((min(r["monthly"]["min_monthly_return"] for r in rs),min(r["ending_equity"] for r in rs),sp["id"]))
        selected.append(dict(cap=cap,strategy_id=max(candidates)[2] if candidates else None))
    return selected


def main():
    OUT.mkdir(exist_ok=True);(OUT/"runs").mkdir(exist_ok=True)
    previous=json.loads((PRIOR/"summary.json").read_text(encoding="utf-8"));specs=definitions(previous)
    frozen=json.loads(SOURCE.read_text(encoding="utf-8"))["short_mask2"]
    protocol=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),specs=specs,windows=windows(),costs=COSTS,
        previous_turn_classification="progress:384quota+24Long-removalcontrols,89tests;Longdidnotconsistentlyaddprofit,threeShortslotsprofitable10/10overlappingstarts.",
        question="Canthen-knownqueuepriorityimproveweakmonthswhenmanysimultaneoussignalssharefewslots?",
        intervention="Preserveeveryfrozenret6Shortsignal,eventid,time,ATR,side,cooldownand25totalnotional. ChangeONLYprobabilityfieldusedfordescendingprioritywithcoinascendingtie-break. Never reorderacrosstime,neverreusefutureoutcomes,neverdropcoinsorlosers.",
        ranks="zscore=frozen;impulse_atr=abs4hret24/(ATR4h/close);low_vol=-ATR4h/close;liquidity=closed24hquoteturnover;funding24=sumactualsettledratesfromrolling24hasknown60secondsbeforeevent,rounded12decimalstoavoidcumsumnoiserankingexactties;weak6=-closedhourlyret6;body_atr=(4hopen-close)/ATR4h. Commonfiniteclosed4h/hourlyreadiness;missingfeaturesfailthebatchratherthansilentlyselectfavorablemissingness.",
        account="Same500Crossx5,total25notional/5plannedmargin,3favorabletranches0.25ATR/6hexpiry,trail3ATR/1%,noSL/notimeexit,DD20persistentopeningpause.3vs5actualShortslotswithonecoinposition.3slotsimplementedas2unusedLong/3Shortquotaforexactpriorcontrolparity;financialwalletneverpartitioned.",
        selection="7rankingsx2capacities=14policiesx12windowsx2cost=336paths. OnSep-Maychooseonepercap:bothcostending>500,DD<20%,20closed,complete;rankworstminmonthlythenworstending.Lockbeforelater/rolling. Reportall10overlapping3monthstarts,notindependentOOS. Do notchangeadmissiontimingorsizing.",
        controls="zscore5mustmatchall24previousShortcontrolpaths;impulse3mustmatchall24previousLong-removalcontrolpaths afternoeconomicchanges. Everyrankinghassame497events;existingprioritiesonlyordercollisions.",
        collisions=collisions(frozen),target="50%netMTM inEVERYcalendar month,notprofitabletotalwindows.",limitations=previous["protocol"]["limitations"],
        live_config_sha256=sha(ROOT/"configs/live.yaml"),rules_sha256=sha(RULE_PATH),data_sha256=sha(DATA/"reconciled_manifest.json"),
        prior_sha256=sha(PRIOR/"summary.json"),signals_sha256=sha(SOURCE),
        source_sha256={n:sha(ROOT/"scripts"/n) for n in ["short_signal_priority.py","search_signal_priority.py","account_side_quota_replay.py",
            "short_multitimeframe_signals.py","short_funding_flow_signals.py","research_directional_audit.py","frozen_extension_inputs.py","monthly_account_metrics.py"]})
    write(OUT/"protocol.json",protocol)
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);observations=observe(frozen,frames,funding);signals=rank(frozen,observations)
    write(OUT/"observations.json",observations);write(OUT/"signals.json",signals);print("SIGNALS",protocol["collisions"],flush=True)
    results=[];selected=[]
    for window,(start,end) in windows().items():
        groups={key:grouped_signals(v,start,end) for key,v in signals.items()}
        for sp in specs:
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),groups[sp["ranking"]],lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(5,fee,slip),research_policy=sp["policy"])
                r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                row=summarize(r,sp["id"],sp["id"],sp["policy"],sp["cap"],cost,window)
                row.update(id=f"{window}_{cost}_{sp['id']}",strategy_id=sp["id"],ranking=sp["ranking"],notional=25,baseline=sp["baseline"],
                    utilization=utilization(r["curve"],r,25,sp["cap"]),exit_diagnostics=exit_diagnostics(r),
                    monthly=monthly_metrics(r["curve"],boundaries=[t for t in BOUNDARIES if start<=t<=end]),side_entries=dict(LONG=0,SHORT=r["entries"]))
                row["target_met"]=r["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                write(OUT/"runs"/f"{row['id']}.json",{k:v for k,v in r.items() if k!="curve"});pd.DataFrame(r["curve"]).to_parquet(OUT/"runs"/f"{row['id']}_equity.parquet",index=False)
                results.append(row)
            write(OUT/"progress.json",dict(window=window,strategy=sp["id"],runs=len(results)))
        print(window,"COMPLETE",len(results),flush=True)
        if window=="development":
            selected=select(specs,results);write(OUT/"candidate_lock.json",dict(selected=selected,locked_at=pd.Timestamp.now(tz="UTC").isoformat(),later_not_run_in_batch=True,pristine_oos=False));print("LOCKED",selected,flush=True)
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    write(OUT/"summary.json",dict(protocol=protocol,specs=specs,selected=selected,results=results,robustness=robustness(results),
        target_met_rows=sum(r["target_met"] for r in results),incomplete_paths=sum(r["ending_equity"] is None for r in results)))
    pd.DataFrame(results).to_csv(OUT/"comparison.csv",index=False);print("COMPLETE",len(results),flush=True)


if __name__=="__main__":main()
