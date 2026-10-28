"""New signal mechanisms with locked chronology and actual account controls."""

import json
from collections import defaultdict

import pandas as pd
from account_scaled_replay import simulate
from compare_account_risk import ROOT, exchange_rules, sha, summarize, write
from historical_research_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from prepare_flow_research import OUT
from search_historical_entries import BOUNDARIES, COSTS, SPANS, WINDOWS, audit_account
from short_event_study import outcomes,statistics
from short_funding_flow_signals import definitions,generate

from dao_vang.config.settings import ExecutionConfig


def load_flow():
    evidence=json.loads((OUT/"flow_evidence.json").read_text(encoding="utf-8"))
    assert evidence["ready"]
    result={}
    for coin in evidence["audits"]:
        p=OUT/"flow"/f"{coin['symbol']}.parquet"
        assert sha(p)==coin["flow_sha256"]
        result[coin["symbol"]]=pd.read_parquet(p)
    return result


def main():
    OUT.mkdir(exist_ok=True)
    (OUT/"runs").mkdir(exist_ok=True)
    hypotheses=[dict(id=f"{s['id']}_hold{h}",source=s,hours=h) for s in definitions() for h in [4,24,72]]
    protocol=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),hypotheses=hypotheses,
                  windows=WINDOWS,costs=COSTS,
                  signal_rules={
                      "positive_carry":"Closed downtrend EMA20<EMA60/close<EMA20 and red candle, last known funding>=0, actual settled trailing24h sum >=0.03%/0.10%. All settlements at least60s old; stale>8h5m excluded. No claim of next settlement prediction.",
                      "buyer_absorption":"Weighted6h taker buy base/total base >=55%/60%, return6h<=0, red candle, close<EMA20. Buying fails to advance price; not inferred open interest.",
                      "seller_pressure":"Weighted6h taker buy fraction<=45%/40%, negative6h return, downtrend, close breaks prior12h low, volume>=1/1.5 times prior24h mean.",
                      "relative_weakness":"24h return below BTC by>=3/6 percentage points, EMA downtrend, red candle touches EMA20 from below, current-hour taker buy fraction<=50%."},
                  dimensions="Four families x loose/strict x BTC any/bear x cooldown6/24h =32 rules; each4/24/72h fixed event horizon =>96 development screens.",
                  selection="Development only: per family highest worst base/stress95%CI lower bound among >=100 complete outcomes and no missing. Lock then validation; choose up to2 by worst validation mean among>=100 complete/no missing, even if negative for diagnosis. Lock before final. Never choose on final/full profits.",
                  portfolio="Chosen2 sources x cap1/5 x parts1/3 x exits: fixedTP1 noSL/no time; trailing3ATR/1% noSL/no time; same trailing plus research SL1USDT scaled with parts and48h time limit. Equity500, x5, total notional25, add0.5ATR favorable steps,6h expiry,20%DD entry pause persistent. All controls share split-minimum eligibility. No sizing increase. Amendment: when net TP becomes nonpositive/below tick because of accumulated costs, pause entries persistently, hold and keep marking/funding position; restore representable TP if possible, never resume entries automatically. Prior invalidated runs archived separately; no signal or selection change.",
                  target="At least50% growth in EACH consecutive calendar month after fees/funding/slippage/marked open inventory. Not total-period50% or a favorable single month.",
                  inference="Aligned cross-coin7day bootstrap,2000 samples; unadjusted for96 hypotheses and earlier searches. Event returns are on notional, overlap and are NOT account profit.",
                  limitations="Retrospective repeatedly examined history; warehouse survivor bias; current precision/minimum filters; historical maintenance tiers missing, MMR1% proxy; unknown depth, close-sampled exits. No live qualification, no guaranteed return.",
                  flow_evidence_sha256=sha(OUT/"flow_evidence.json"),live_config_sha256=sha(ROOT/"configs/live.yaml"),
                  source_sha256={name:sha(ROOT/"scripts"/name) for name in ["short_funding_flow_signals.py","search_funding_flow.py","account_scaled_replay.py","short_event_study.py","historical_research_inputs.py","monthly_account_metrics.py"]})
    write(OUT/"protocol.json",protocol)
    prices,funding,frames=load(); flow=load_flow()
    signals=generate(frames,flow,funding)
    write(OUT/"signals.json",signals)
    print("SIGNAL COUNTS",{s:len(v) for s,v in signals.items()},flush=True)

    def screen(spec,window):
        events,counts=outcomes(signals[spec["source"]["id"]],prices,funding,*SPANS[window],spec["hours"])
        cases={cost:statistics(events,*SPANS[window],fee,slip) for cost,fee,slip in COSTS}
        complete=counts["missing"]==0 and counts["complete"]>=100
        return dict(id=spec["id"],spec=spec,window=window,counts=counts,cases=cases,complete=complete,
                    worst_lower=min(cases[c]["ci95"][0] for c,_,_ in COSTS) if complete else None,
                    worst_mean=min(cases[c]["mean_net_return"] for c,_,_ in COSTS) if complete else None)

    development=[]
    for i,spec in enumerate(hypotheses,1):
        development.append(screen(spec,"development"))
        if i%24==0:print("SCREEN",i,"/",len(hypotheses),flush=True)
    write(OUT/"development.json",development)
    selected=[]
    for family in sorted({s["family"] for s in definitions()}):
        pool=[r for r in development if r["spec"]["source"]["family"]==family and r["complete"]]
        if pool:selected.append(max(pool,key=lambda r:(r["worst_lower"],r["worst_mean"]))["spec"])
    write(OUT/"family_lock.json",dict(locked_at=pd.Timestamp.now(tz="UTC").isoformat(),selected=selected))
    validation=[screen(s,"validation") for s in selected]
    ordered=sorted([r for r in validation if r["complete"]],key=lambda r:-r["worst_mean"])
    chosen=[r["spec"] for r in ordered[:2]]
    write(OUT/"portfolio_lock.json",dict(locked_at=pd.Timestamp.now(tz="UTC").isoformat(),chosen=chosen,final_not_run=True))
    print("LOCKED",[s["id"] for s in chosen],flush=True)
    holdout=[screen(s,"holdout") for s in selected]
    write(OUT/"screen_summary.json",dict(development=development,validation=validation,holdout=holdout,chosen=chosen))
    specs=[]
    for candidate in chosen:
        for cap in [1,5]:
            for parts in [1,3]:
                for exit_mode in ["tp1_noSL","trail_noSL","trail_sl1_h48"]:
                    policy=dict(position_notional=25,entry_parts=parts,entry_mode="single" if parts==1 else "favorable",
                                entry_step_atr=0.5,add_expiry_hours=6,require_split_eligibility=True,
                                unrepresentable_tp_action="pause_hold")
                    if exit_mode=="tp1_noSL":policy.update(fixed_tp_usdt=1)
                    else:policy.update(trailing=True,activation_atr=3,callback_fraction=.01,observation_minutes=5)
                    if exit_mode=="trail_sl1_h48":policy.update(loss_usdt=1,max_hold_hours=48)
                    specs.append(dict(id=f"{candidate['source']['family']}_n{cap}_p{parts}_{exit_mode}",
                                      source=candidate["source"],cap=cap,parts=parts,exit=exit_mode,policy=policy))
    write(OUT/"portfolio_specs.json",specs)
    rules=exchange_rules(RULE_PATH)
    assert not set(prices)-set(rules)
    groups={}
    for candidate in chosen:
        for window,(start,end) in SPANS.items():
            grouped=defaultdict(list)
            for signal in signals[candidate["source"]["id"]]:
                if start<=signal["at"]<end:grouped[signal["at"]].append(signal)
            for group in grouped.values():group.sort(key=lambda r:(-r["probability"],r["symbol"]))
            groups[(candidate["source"]["id"],window)]=grouped
    results=[]
    for i,spec in enumerate(specs,1):
        for window in ["validation","holdout","full"]:
            start,end=SPANS[window]
            for cost,fee,slip in COSTS:
                result=simulate(list(range(start,end+1,300000)),groups[(spec["source"]["id"],window)],
                                lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                                ExecutionConfig(max_open_positions=spec["cap"],fee_rate=fee,max_slippage_bps=slip),
                                research_policy=spec["policy"])
                result["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                audited=audit_account(result,spec["cap"])
                row=summarize(result,spec["id"],spec["id"],spec["policy"],spec["cap"],cost,window)
                row.update(id=f"{window}_{cost}_{spec['id']}",strategy_id=spec["id"],audit=audited,
                           parts=spec["parts"],exit=spec["exit"],family=spec["source"]["family"])
                if window=="full":
                    row["monthly"]=monthly_metrics(result["curve"],boundaries=BOUNDARIES)
                    row["target_met"]=result["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                write(OUT/"runs"/f"{row['id']}.json",{k:v for k,v in result.items() if k!="curve"})
                pd.DataFrame(result["curve"]).to_parquet(OUT/"runs"/f"{row['id']}_equity.parquet",index=False)
                results.append(row)
        write(OUT/"portfolio_progress.json",dict(finished=i,total=len(specs),runs=len(results)))
        print("PORTFOLIO",i,"/",len(specs),spec["id"],flush=True)
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    write(OUT/"summary.json",dict(protocol=protocol,development=development,validation=validation,holdout=holdout,
                                 chosen=chosen,portfolio_specs=specs,results=results,
                                 target_met_rows=sum(r.get("target_met",False) for r in results),live_config_unchanged=True))
    pd.DataFrame(results).to_csv(OUT/"comparison.csv",index=False)
    print("COMPLETE",len(development),"screens",len(results),"accounts",flush=True)


if __name__=="__main__":main()
