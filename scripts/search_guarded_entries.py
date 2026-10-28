"""Chronologically locked entry timing and causal guard experiment, batch07."""

import json

import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import utilization
from compare_account_risk import ROOT,exchange_rules,sha,summarize,write
from historical_research_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from prepare_historical_research import OUT as DATA
from search_historical_entries import BOUNDARIES,COSTS,SPANS,WINDOWS
from search_multitimeframe_rolling import grouped_signals,rolling_windows
from short_entry_guards import definitions as guards,features,filter_entries
from short_entry_timing import definitions as timings,transform
from short_event_study import outcomes,statistics

from dao_vang.config.settings import ExecutionConfig

OUT=ROOT/"artifacts/guarded_entries_20260925"
PRIOR=ROOT/"artifacts/multitimeframe_rolling_20260925"


def entry_set(signals,prices,enriched,spec,start,end):
    triggers,watch=transform(signals[spec["source"]["id"]],prices,start,end,spec["timing"])
    entries,guard=filter_entries(triggers,enriched,spec["guard"])
    return entries,dict(watch=watch,guard=guard)


def main():
    OUT.mkdir(exist_ok=True)
    for name in ["runs","entries"]:(OUT/name).mkdir(exist_ok=True)
    prior=json.loads((PRIOR/"summary.json").read_text(encoding="utf-8"))
    sources=[next(s for s in prior["portfolio_specs"] if s["id"]==ident) for ident in
             ["prior_seller_pressure_p3_trail_noSL","overextension_reversal_p3_trail_noSL"]]
    choices=[t for t in timings() if t["id"] in ["immediate","delay60","rejection0.5","breakdown0.5"]]
    specs=[dict(id=f"{s['source']['family']}_{t['id']}_{g}",source=s["source"],timing=t,guard=g)
           for s in sources for t in choices for g in guards()]
    hypotheses=[dict(**s,hours=h,screen_id=f"{s['id']}_h{h}") for s in specs for h in [4,24,72]]
    protocol=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),hypotheses=hypotheses,specs=specs,
        windows=WINDOWS,costs=COSTS,previous_turn="progress: 512 allocation/holding paths established size is not robust to start date",
        entry="Four rules: immediate; fixed60min delay; closed-price breakdown0.5 frozen ATR; rebound0.5ATR then fall0.25ATR from running peak on later closed bar, expiry6h. No future open used for trigger; market next5mopen with slippage. Virtual watches have no reserved margin until triggered.",
        guards="At trigger, latest closed hourly bar with age<1h: none; settled24h funding sum>=0; anti_squeeze(ret24<=10%,ret6<=0,funding24>=-0.1%,0<ATR1h/close<=5%); trend_confirmation(BTCret24<0,altEMA20<EMA60,altret6<0). Funding settlements only known after60s. Failed guard discards event, no later retry. No coin blacklist, all thresholds fixed before run.",
        selection="96 screens:2sources x4entry x4guard x3horizons. On Sep-Nov development, lock one non-control per source with>=50completeevents/no missing by highest worst-cost95%CI lower then mean. On Dec-Feb validation, evaluate locked candidates without switching rules, even negative. Mar-May final never selects candidates. The50 minimum is exploratory and does not replace live100event/28day gate. If none eligible, do not relax threshold.",
        portfolio="Each locked candidate plus immediate/no-guard control per source; notional25/100, equity500,x5,cap5,3favorableparts,0.5ATRspacing,6hexpiry. Exits: trailing3ATR/1% noSL/no time, or same plus4%notionalSL scaled by filled parts and72htimeclose. Sizes20margin and SL/time research only. Full9months +7overlapping fresh3month starts,2costs. Persistent20%DD opening pause, mark old positions, unrepresentable TP pause_hold.",
        target="At least50% net marked growth EACH consecutive calendar month, not average or a chosen best month. No promotion on this repeatedly inspected history.",
        inference="7day aligned crosscoin cluster bootstrap2000, intervals not adjusted for96 screens/earlier searches. Event return on notional is not account return; actual portfolio enforces capital/capacity.",
        limitations="Repeatedly inspected historical universe may omit delisted coins; current exchange filters,1% maintenance proxy,5m sampling and assumed slippage/no orderbook. Thresholds diagnostic, not established safeguards against squeezes. No live eligibility.",
        source_sha256={n:sha(ROOT/"scripts"/n) for n in ["search_guarded_entries.py","short_entry_guards.py","short_entry_timing.py","short_funding_flow_signals.py","account_scaled_replay.py","short_event_study.py"]},
        data_sha256=sha(DATA/"manifest.json"),signals_sha256=sha(PRIOR/"signals.json"),live_config_sha256=sha(ROOT/"configs/live.yaml"))
    write(OUT/"protocol.json",protocol)
    prices,funding,frames=load();enriched=features(frames,funding)
    signals=json.loads((PRIOR/"signals.json").read_text(encoding="utf-8"))
    cache={};windows=dict(SPANS,**rolling_windows())

    def entries(s,window):
        key=(s["id"],window)
        if key not in cache:
            es,au=entry_set(signals,prices,enriched,s,*windows[window]);cache[key]=(es,au)
            write(OUT/"entries"/f"{window}_{s['id']}.json",dict(entries=es,audit=au))
        return cache[key]

    def screen(s,window):
        es,au=entries(s,window)
        events,counts=outcomes(es,prices,funding,*windows[window],s["hours"])
        cases={c:statistics(events,*windows[window],fee,slip) for c,fee,slip in COSTS}
        ready=(counts["complete"]>=50 and counts["missing"]==0 and not au["watch"]["counts"].get("missing_data")
               and not any(au["guard"]["counts"].get(k) for k in ["missing_features","stale_features"]))
        return dict(id=s["screen_id"],spec=s,window=window,counts=counts,cases=cases,eligible=ready,
                    watch_counts=au["watch"]["counts"],guard_counts=au["guard"]["counts"],
                    worst_lower=min(cases[c]["ci95"][0] for c,_,_ in COSTS) if ready else None,
                    worst_mean=min(cases[c]["mean_net_return"] for c,_,_ in COSTS) if ready else None)
    development=[]
    for i,s in enumerate(hypotheses,1):
        development.append(screen(s,"development"))
        if i%24==0:print("SCREEN",i,"/",len(hypotheses),flush=True)
    write(OUT/"development.json",development)
    selected=[]
    for source in sources:
        pool=[r for r in development if r["spec"]["source"]["id"]==source["source"]["id"] and r["eligible"]
              and not (r["spec"]["timing"]["id"]=="immediate" and r["spec"]["guard"]=="none")]
        if pool:selected.append(max(pool,key=lambda r:(r["worst_lower"],r["worst_mean"]))["spec"])
    write(OUT/"candidate_lock.json",dict(locked_at=pd.Timestamp.now(tz="UTC").isoformat(),selected=selected,final_not_evaluated=True))
    print("LOCKED",[s["screen_id"] for s in selected],flush=True)
    validation=[screen(s,"validation") for s in selected]
    holdout=[screen(s,"holdout") for s in selected]
    controls=[];port_specs=[]
    for candidate in selected:
        control=next(s for s in specs if s["source"]["id"]==candidate["source"]["id"] and s["timing"]["id"]=="immediate" and s["guard"]=="none")
        for window in ["development","validation","holdout"]:
            controls.append(screen(dict(control,hours=candidate["hours"],screen_id=f"{control['id']}_h{candidate['hours']}"),window))
        source=next(s for s in sources if s["source"]["id"]==candidate["source"]["id"])
        for variant in [candidate,control]:
            for notional in [25,100]:
                for risk in ["hold","risk4pct_time72"]:
                    policy=dict(source["policy"],position_notional=notional)
                    if risk!="hold":policy.update(loss_usdt=.04*notional,max_hold_hours=72)
                    port_specs.append(dict(id=f"{variant['id']}_n{notional}_{risk}",entry=variant,policy=policy,
                                           baseline=variant["id"]==control["id"],notional=notional,management=risk))
    write(OUT/"screens.json",dict(development=development,validation=validation,holdout=holdout,controls=controls))
    rules=exchange_rules(RULE_PATH);assert not set(prices)-set(rules);results=[]
    for i,s in enumerate(port_specs,1):
        for window,(start,end) in rolling_windows().items():
            es,au=entries(s["entry"],window);groups=grouped_signals(es,start,end)
            for cost,fee,slip in COSTS:
                result=simulate(list(range(start,end+1,300000)),groups,lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                                ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=s["policy"])
                result["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                r=summarize(result,s["id"],s["id"],s["policy"],5,cost,window)
                r.update(id=f"{window}_{cost}_{s['id']}",strategy_id=s["id"],notional=s["notional"],baseline=s["baseline"],
                         source=s["entry"]["source"]["family"],management=s["management"],timing=s["entry"]["timing"]["id"],guard=s["entry"]["guard"],
                         utilization=utilization(result["curve"],result,s["notional"]),
                         monthly=monthly_metrics(result["curve"],boundaries=[t for t in BOUNDARIES if start<=t<=end]))
                r["target_met"]=result["ending_equity"] is not None and r["monthly"]["all_months_50pct"]
                write(OUT/"runs"/f"{r['id']}.json",{k:v for k,v in result.items() if k!="curve"})
                pd.DataFrame(result["curve"]).to_parquet(OUT/"runs"/f"{r['id']}_equity.parquet",index=False);results.append(r)
        write(OUT/"progress.json",dict(finished=i,total=len(port_specs),runs=len(results)))
        print("PORTFOLIO",i,"/",len(port_specs),flush=True)
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    write(OUT/"summary.json",dict(protocol=protocol,selected=selected,portfolio_specs=port_specs,
          development=development,validation=validation,holdout=holdout,controls=controls,results=results,
          target_met_rows=sum(r["target_met"] for r in results),live_config_unchanged=True))
    pd.DataFrame(results).to_csv(OUT/"comparison.csv",index=False)
    print("COMPLETE",len(results),flush=True)


if __name__=="__main__":main()
