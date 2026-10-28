"""Batch15: failed hourly rallies, frozen before account results are observed."""
import json
import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import utilization
from compare_account_risk import ROOT,exchange_rules,sha,summarize,write
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from search_frozen_exits import DATA,WINDOWS,BOUNDARIES,COSTS,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from short_failed_rally import definitions as sources,prepare,generate
from dao_vang.config.settings import ExecutionConfig

OUT=ROOT/"artifacts/failed_rally_20260925"
PRIOR=ROOT/"artifacts/market_breadth_20260925"


def definitions(old):
    result=[]
    for n in [25,100]:
        base=next(s for s in old["specs"] if s["id"]==f"benchmark_mask2_n{n}")
        result.append(dict(base))
        for src in sources():
            for hold in ["hold","time48"]:
                policy=dict(base["policy"])
                if hold=="time48":policy["max_hold_hours"]=48
                result.append(dict(id=f"{src['id']}_n{n}_{hold}",source=src,notional=n,holding=hold,policy=policy,baseline=False))
    return result


def select(specs,rows):
    chosen=[]
    for n in [25,100]:
        for holding in ["hold","time48"]:
            pool=[]
            for s in specs:
                if s["baseline"] or (s["notional"],s["holding"])!=(n,holding):continue
                rs=[r for r in rows if r["strategy_id"]==s["id"] and r["window"]=="development"]
                if len(rs)==2 and all(r["ending_equity"] is not None and r["monthly"]["complete"] and r["max_drawdown"]<.2 and r["exits"]>=20 for r in rs):
                    pool.append((min(r["monthly"]["min_monthly_return"] for r in rs),min(r["ending_equity"] for r in rs),s["id"]))
            if pool:chosen.append(max(pool)[2])
    return chosen


def main():
    OUT.mkdir(exist_ok=True);(OUT/"runs").mkdir(exist_ok=True)
    old=json.loads((PRIOR/"summary.json").read_text(encoding="utf-8"));specs=definitions(old)
    protocol=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),specs=specs,windows=WINDOWS,costs=COSTS,
        previous_turn_classification="progress:126 cost paths audited, zero execution cost did not repair weak later price edge;62tests.",
        hypothesis="Wait for a distinct rebound and its failure after a downside impulse, rather than immediately shorting weakness.",
        signal="Completed hourly bars only. Arm on close below preceding12 hourly lows, in completed4hEMA20<EMA60/close<EMA20/ret24<0 regime. 72 finitehourlybars,4hready,volume24>=2m. Freeze14hATR atarm. Subsequently observe closing-price rebound1or2frozenhourATR above lowestclose sincearm; on a strictly later hour require redclose below previoushourlow. 4htrend andoptionalBTC4hbear must hold throughout; invaliddata/gaps cancelwatch. TTL6or24h inclusive fromarm; expire beyondTTL. Percoin24h cooldown from emitted event. No intrabar ordering assumptions. Signals atbarclose execute next5mopen. Entry ATR for exits remains completed4hATR.",
        account="500USDT,Crossx5,cap5,25/100notional(total3parts),adds on favorable0.25ATR steps,6hexpiry,trail3ATR/1%,persistent20%DDpauseopennew. NoSL and indefiniteholding control; alternative48hmarketexit can realize losses and is research-only. No coin exclusions.",
        selection="8sources x2sizes x2holding plus2 frozenreversalcontrols=34policies,3windows,2cost=204paths. Choose one per(size,holding) on development:complete,DD<20%,>=20closedbothcost; maximizeworstcostminmonth thenending. Lock before later inthisbatch; reusedhistory is NOT pristineOOS.",
        target="50%netMTM in EVERY consecutive calendar month, nottotal/average/bestmonth. Future profitability not established by historical fit.",
        limitations=old["protocol"]["limitations"],live_config_sha256=sha(ROOT/"configs/live.yaml"),data_sha256=sha(DATA/"reconciled_manifest.json"),prior_sha256=sha(PRIOR/"summary.json"),signals_sha256=sha(PRIOR/"signals.json"),
        source_sha256={n:sha(ROOT/"scripts"/n) for n in ["short_failed_rally.py","search_failed_rally.py","account_scaled_replay.py","short_multitimeframe_signals.py","frozen_extension_inputs.py","monthly_account_metrics.py","capital_research_metrics.py"]})
    write(OUT/"protocol.json",protocol)
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);prepared=prepare(frames);signals=generate(prepared)
    prior_signals=json.loads((PRIOR/"signals.json").read_text(encoding="utf-8"));signals["benchmark_mask2"]=prior_signals["benchmark_mask2"]
    write(OUT/"signals.json",signals);results=[];selected=[]
    for window,(start,end) in WINDOWS.items():
        groups={k:grouped_signals(v,start,end) for k,v in signals.items()}
        for i,spec in enumerate(specs,1):
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),groups[spec["source"]["id"]],lambda c:prices.get(c,{}),rules,lambda c:funding[c],ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
                r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                row=summarize(r,spec["id"],spec["id"],spec["policy"],5,cost,window)
                row.update(id=f"{window}_{cost}_{spec['id']}",strategy_id=spec["id"],baseline=spec["baseline"],source=spec["source"],notional=spec["notional"],holding=spec["holding"],utilization=utilization(r["curve"],r,spec["notional"]),exit_diagnostics=exit_diagnostics(r),monthly=monthly_metrics(r["curve"],boundaries=[t for t in BOUNDARIES if start<=t<=end]))
                row["target_met"]=r["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                write(OUT/"runs"/f"{row['id']}.json",{k:v for k,v in r.items() if k!="curve"});pd.DataFrame(r["curve"]).to_parquet(OUT/"runs"/f"{row['id']}_equity.parquet",index=False);results.append(row)
            write(OUT/"progress.json",dict(window=window,finished=i,total=len(specs),runs=len(results)))
            if i%8==0 or i==len(specs):print(window,i,"/",len(specs),flush=True)
        if window=="development":
            selected=select(specs,results);write(OUT/"candidate_lock.json",dict(selected=selected,locked_at=pd.Timestamp.now(tz="UTC").isoformat(),later_not_run_in_batch=True,pristine_oos=False));print("LOCKED",selected,flush=True)
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    write(OUT/"summary.json",dict(protocol=protocol,specs=specs,selected=selected,results=results,target_met_rows=sum(r["target_met"] for r in results),incomplete_paths=sum(r["ending_equity"] is None for r in results)))
    pd.DataFrame(results).to_csv(OUT/"comparison.csv",index=False);print("COMPLETE",len(results),flush=True)


if __name__=="__main__":main()
