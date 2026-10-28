"""Four-hour/daily short mechanisms and predeclared rolling-start robustness."""

import json
from collections import defaultdict

import pandas as pd
from account_scaled_replay import simulate
from compare_account_risk import ROOT,exchange_rules,sha,summarize,write
from historical_research_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from prepare_historical_research import OUT as DATA
from search_historical_entries import BOUNDARIES,COSTS,SPANS,WINDOWS,audit_account
from short_event_study import outcomes,statistics
from short_multitimeframe_signals import definitions,generate

from dao_vang.config.settings import ExecutionConfig

OUT=ROOT/"artifacts/multitimeframe_rolling_20260925"
PRIOR=ROOT/"artifacts/funding_flow_search_20260925"


def rolling_windows():
    result={"full":SPANS["full"]}
    for start in pd.date_range("2025-09-01","2026-03-01",freq="MS",tz="UTC"):
        end=start+pd.DateOffset(months=3)
        result["start_"+start.strftime("%Y_%m")]=(int(start.timestamp()*1000),int(end.timestamp()*1000))
    return result


def grouped_signals(signals,start,end):
    grouped=defaultdict(list)
    for signal in signals:
        if start<=signal["at"]<end:grouped[signal["at"]].append(signal)
    for group in grouped.values():group.sort(key=lambda r:(-r["probability"],r["symbol"]))
    return grouped


def main():
    OUT.mkdir(exist_ok=True);(OUT/"runs").mkdir(exist_ok=True)
    hypotheses=[dict(id=f"{s['id']}_hold{h}",source=s,hours=h) for s in definitions() for h in [24,72,168]]
    prior=json.loads((PRIOR/"summary.json").read_text(encoding="utf-8"))
    control=next(s for s in prior["portfolio_specs"] if s["source"]["family"]=="seller_pressure" and s["cap"]==5 and s["parts"]==3 and s["exit"]=="trail_noSL")
    protocol=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),hypotheses=hypotheses,
                  screening_windows=WINDOWS,account_windows=rolling_windows(),costs=COSTS,
                  bars="Resample already-closed hourly candles into right-closed4h bars and24h UTC days. Incomplete bins are missing. Use only completed daily context as of signal; ATR14 measured on4h bars, not earlier1h ATR. 72 complete4h candles required plus>=2m rolling24h turnover.",
                  signals="Four4h families x loose/strict x BTC daily bear/any =16 rules, cooldown24h/coin. Mean/std band reversal2/3sigma after prior24h+5/10%; high breakout failure of prior20/40bars with wick>=40/60% and volume>=1.5/2x; EMA20 rejection in completed daily EMA10<EMA20/negative7day trend; break below prior12bar low after prior range width in lowest30/20% of60bar history plus1.5/2x volume.",
                  selection="48 event screens24/72/168h. Per family select development worst base/stress95%lowerCI then worst mean among>=50 complete/no missing events. Predeclared50 is exploratory due lower frequency, NOT a reduction of100-event forward/live requirement. Lock family rules before validation; pick up to2 by worst validation mean amongsame50/no missing; lock before final. Negative candidates may be evaluated diagnostically. No selection on final/full/rolling returns.",
                  account="Chosen rules x parts1/3 x fixedTP2/noSL, trailing3ATR/1%/noSL, same trailing withSL1 and72h time exit. All equity500, leverage5, max5 positions,total25notional per position. Add only favorable0.5ATR steps,expire6h,common split-minimum eligibility. Pause at20%peakDD or unrepresentable netTP; keep existing positions and funding, no auto resume. Trailing observed5m, nextopen market fill; fixedTP close-cross proxy.",
                  rolling="FullSep2025-Jun2026 plus seven independently initialized3month accounts starting each monthSep2025-Mar2026. Overlapping rolling windows are NOT independent evidence. Retain every result; no selective start-date promotion. Compare prior seller-pressure cap5/parts3/trailing/noSL as frozen baseline.",
                  control=control,target="At least50% net marked growth in EACH consecutive month, including open positions; not just totalperiod return.",
                  limitations="Retrospective history already inspected, warehouse survival/listing bias, current filters, MMR1% proxy without historical tiers, close-sampled exits and assumed slippage. Block-bootstrap CI unadjusted for multiple trials. No live promotion.",
                  data_sha256=sha(DATA/"manifest.json"),control_signal_sha256=sha(PRIOR/"signals.json"),
                  live_config_sha256=sha(ROOT/"configs/live.yaml"),
                  source_sha256={n:sha(ROOT/"scripts"/n) for n in ["short_multitimeframe_signals.py","search_multitimeframe_rolling.py","account_scaled_replay.py","short_event_study.py","historical_research_inputs.py","monthly_account_metrics.py"]})
    write(OUT/"protocol.json",protocol)
    prices,funding,frames=load();signals=generate(frames)
    print("SIGNALS",{k:len(v) for k,v in signals.items()},flush=True)
    old_signals=json.loads((PRIOR/"signals.json").read_text(encoding="utf-8"))
    signals[control["source"]["id"]]=old_signals[control["source"]["id"]]
    write(OUT/"signals.json",signals)

    def screen(spec,window):
        events,counts=outcomes(signals[spec["source"]["id"]],prices,funding,*SPANS[window],spec["hours"])
        cases={cost:statistics(events,*SPANS[window],fee,slip) for cost,fee,slip in COSTS}
        eligible=counts["complete"]>=50 and counts["missing"]==0
        return dict(id=spec["id"],spec=spec,window=window,counts=counts,cases=cases,eligible=eligible,
                    worst_lower=min(cases[c]["ci95"][0] for c,_,_ in COSTS) if eligible else None,
                    worst_mean=min(cases[c]["mean_net_return"] for c,_,_ in COSTS) if eligible else None)

    development=[screen(spec,"development") for spec in hypotheses]
    write(OUT/"development.json",development)
    selected=[]
    for family in sorted({s["family"] for s in definitions()}):
        pool=[r for r in development if r["spec"]["source"]["family"]==family and r["eligible"]]
        if pool:selected.append(max(pool,key=lambda r:(r["worst_lower"],r["worst_mean"]))["spec"])
    write(OUT/"family_lock.json",dict(locked_at=pd.Timestamp.now(tz="UTC").isoformat(),selected=selected))
    validation=[screen(spec,"validation") for spec in selected]
    ordered=sorted([r for r in validation if r["eligible"]],key=lambda r:-r["worst_mean"])
    chosen=[r["spec"] for r in ordered[:2]]
    write(OUT/"portfolio_lock.json",dict(locked_at=pd.Timestamp.now(tz="UTC").isoformat(),chosen=chosen,final_not_run=True))
    print("LOCKED",[s["id"] for s in chosen],flush=True)
    holdout=[screen(spec,"holdout") for spec in selected]
    write(OUT/"screen_summary.json",dict(development=development,validation=validation,holdout=holdout,chosen=chosen))
    specs=[]
    for candidate in chosen:
        for parts in [1,3]:
            for exit_mode in ["tp2_noSL","trail_noSL","trail_sl1_h72"]:
                policy=dict(position_notional=25,entry_parts=parts,entry_mode="single" if parts==1 else "favorable",
                            entry_step_atr=.5,add_expiry_hours=6,require_split_eligibility=True,
                            unrepresentable_tp_action="pause_hold")
                if exit_mode=="tp2_noSL":policy.update(fixed_tp_usdt=2)
                else:policy.update(trailing=True,activation_atr=3,callback_fraction=.01,observation_minutes=5)
                if exit_mode=="trail_sl1_h72":policy.update(loss_usdt=1,max_hold_hours=72)
                specs.append(dict(id=f"{candidate['source']['family']}_p{parts}_{exit_mode}",source=candidate["source"],parts=parts,
                                  exit=exit_mode,policy=policy,baseline=False))
    specs.append(dict(id="prior_seller_pressure_p3_trail_noSL",source=control["source"],parts=3,exit="trail_noSL",
                      policy=control["policy"],baseline=True))
    write(OUT/"portfolio_specs.json",specs)
    windows=rolling_windows();rules=exchange_rules(RULE_PATH);assert not set(prices)-set(rules)
    results=[]
    for i,spec in enumerate(specs,1):
        for window,(start,end) in windows.items():
            groups=grouped_signals(signals[spec["source"]["id"]],start,end)
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),groups,lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                           ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
                r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                audit=audit_account(r,5)
                row=summarize(r,spec["id"],spec["id"],spec["policy"],5,cost,window)
                bounds=[t for t in BOUNDARIES if start<=t<=end]
                row.update(id=f"{window}_{cost}_{spec['id']}",strategy_id=spec["id"],parts=spec["parts"],exit=spec["exit"],
                           family=spec["source"]["family"],baseline=spec["baseline"],audit=audit,
                           monthly=monthly_metrics(r["curve"],boundaries=bounds))
                row["target_met"]=r["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                write(OUT/"runs"/f"{row['id']}.json",{k:v for k,v in r.items() if k!="curve"})
                pd.DataFrame(r["curve"]).to_parquet(OUT/"runs"/f"{row['id']}_equity.parquet",index=False)
                results.append(row)
        write(OUT/"progress.json",dict(finished=i,total=len(specs),runs=len(results)))
        print("PORTFOLIO",i,"/",len(specs),spec["id"],flush=True)
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    write(OUT/"summary.json",dict(protocol=protocol,development=development,validation=validation,holdout=holdout,chosen=chosen,
                                 portfolio_specs=specs,results=results,target_met_rows=sum(r["target_met"] for r in results),
                                 full_monthly_passes=sum(r["target_met"] and r["window"]=="full" for r in results),live_config_unchanged=True))
    pd.DataFrame(results).to_csv(OUT/"comparison.csv",index=False)
    print("COMPLETE",len(development),"screens",len(results),"accounts",flush=True)


if __name__=="__main__":main()
