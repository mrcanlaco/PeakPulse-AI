"""Hypothetical sizing and holding-time sensitivity, never live configuration."""

import json

import pandas as pd
from account_scaled_replay import simulate
from capital_research_metrics import utilization
from compare_account_risk import ROOT,exchange_rules,sha,summarize,write
from historical_research_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from prepare_historical_research import OUT as DATA
from search_historical_entries import BOUNDARIES,COSTS
from search_multitimeframe_rolling import grouped_signals,rolling_windows

from dao_vang.config.settings import ExecutionConfig

OUT=ROOT/"artifacts/capital_holding_20260925"
PRIOR=ROOT/"artifacts/multitimeframe_rolling_20260925"


def main():
    OUT.mkdir(exist_ok=True);(OUT/"runs").mkdir(exist_ok=True)
    old=json.loads((PRIOR/"summary.json").read_text(encoding="utf-8"))
    sources=[next(s for s in old["portfolio_specs"] if s["id"]==ident)
             for ident in ["prior_seller_pressure_p3_trail_noSL","overextension_reversal_p3_trail_noSL"]]
    specs=[]
    for source in sources:
        for notional in [25,50,100,250]:
            for management in ["hold","time24","time72","risk4pct_time72"]:
                policy=dict(source["policy"],position_notional=notional)
                if management=="time24":policy["max_hold_hours"]=24
                if management in ["time72","risk4pct_time72"]:policy["max_hold_hours"]=72
                if management=="risk4pct_time72":policy["loss_usdt"]=notional*.04
                specs.append(dict(id=f"{source['source']['family']}_n{notional}_{management}",source=source["source"],
                                  reference_id=source["id"],notional=notional,margin=notional/5,
                                  management=management,policy=policy))
    windows=rolling_windows()
    protocol=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),sources=sources,specs=specs,windows=windows,costs=COSTS,
                  purpose="Test whether limited allocation and long slot occupancy explain distance to50% monthly; do not assume increasing size creates edge.",
                  scope="Hypothetical research sizes only: margin5/10/20/50, notional25/50/100/250 per position, all leverage5/equity500/max5positions. Retain5-margin reference. No live/private API/configuration changes. Fixed size per run, no compounding or DCA.",
                  management="All source rules and trailing3ATR/1% frozen. Three favorable tranches with0.5ATR spacing/6h expiry. Four exits: indefinite noSL; trailing plus24h close; trailing plus72h close; trailing plus4%notional SL (scaled by filled parts) and72h close. Time exits may close losing positions and differ from original no-time-exit request; explicitly research alternatives.",
                  execution="Full account replay at each size, not linear scaling of old PnL. Precision, minimum quantities, minimum target eligibility, available funds, position competition, costs and drawdown pause can change actual trades. Increasing size can admit previously ineligible signals; record this instead of pretending identical fills. Persistent20%peakDD pause, continue managing old positions. Unrepresentable TP pauses and holds. Current MMR1% proxy may terminate paths; never invent post-breach liquidation cash or fill missing months with zero.",
                  evaluation="All32 policy scenarios tested at full9month window and7 overlapping independent-start3month windows, each two costs =>512 logical paths. Sources chosen retrospectively for diagnosis; no new clean OOS claim, no selection on favorable result. Rolling windows overlap and are not independent.",
                  target="At least50% net marked growth in EACH consecutive month, not average, total-period profit, or a single best month.",
                  utilization="Time-weight state to next5m step; terminal state gets zero duration. Margin commitment includes marked margin, pending tranches and reserve fees, not the maximum possible cross-account loss. Truncated paths never reported complete.",
                  limits="Previously inspected history and universe survivor bias; current exchange filters and no historical margin tiers/depth. Fixed1%MMR especially limits interpretation at increased exposure. Actual fees/slippage not established by orderbook. No live eligibility.",
                  data_sha256=sha(DATA/"manifest.json"),signals_sha256=sha(PRIOR/"signals.json"),live_config_sha256=sha(ROOT/"configs/live.yaml"),
                  source_sha256={n:sha(ROOT/"scripts"/n) for n in ["search_capital_holding.py","capital_research_metrics.py","account_scaled_replay.py","historical_research_inputs.py","monthly_account_metrics.py"]})
    write(OUT/"protocol.json",protocol)
    signals=json.loads((PRIOR/"signals.json").read_text(encoding="utf-8"))
    prices,funding,_=load();rules=exchange_rules(RULE_PATH)
    assert not set(prices)-set(rules)
    groups={(s["source"]["id"],w):grouped_signals(signals[s["source"]["id"]],start,end)
            for s in sources for w,(start,end) in windows.items()}
    results=[]
    for i,spec in enumerate(specs,1):
        for window,(start,end) in windows.items():
            for cost,fee,slip in COSTS:
                result=simulate(list(range(start,end+1,300000)),groups[(spec["source"]["id"],window)],
                                lambda c:prices.get(c,{}),rules,lambda c:funding[c],
                                ExecutionConfig(max_open_positions=5,fee_rate=fee,max_slippage_bps=slip),research_policy=spec["policy"])
                result["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
                metrics=utilization(result["curve"],result,spec["notional"],5)
                row=summarize(result,spec["id"],spec["id"],spec["policy"],5,cost,window)
                row.update(id=f"{window}_{cost}_{spec['id']}",strategy_id=spec["id"],family=spec["source"]["family"],
                           notional=spec["notional"],margin=spec["margin"],management=spec["management"],utilization=metrics,
                           monthly=monthly_metrics(result["curve"],boundaries=[t for t in BOUNDARIES if start<=t<=end]))
                row["target_met"]=result["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
                write(OUT/"runs"/f"{row['id']}.json",{k:v for k,v in result.items() if k!="curve"})
                pd.DataFrame(result["curve"]).to_parquet(OUT/"runs"/f"{row['id']}_equity.parquet",index=False)
                results.append(row)
        write(OUT/"progress.json",dict(finished=i,total=len(specs),runs=len(results)))
        print("SCENARIO",i,"/",len(specs),spec["id"],flush=True)
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    write(OUT/"summary.json",dict(protocol=protocol,specs=specs,results=results,
        target_met_rows=sum(r["target_met"] for r in results),
        incomplete_paths=sum(r["ending_equity"] is None for r in results),live_config_unchanged=True))
    pd.DataFrame(results).to_csv(OUT/"comparison.csv",index=False)
    print("COMPLETE",len(results),"paths",flush=True)


if __name__=="__main__":main()
