"""Batch27: finite shared-wallet exposure admission, frozen momentum sources."""
import pandas as pd
from account_exposure_replay import simulate
from compare_account_risk import ROOT,sha,write,summarize,exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from capital_research_metrics import utilization
from directional_capacity_metrics import side_metrics
from monthly_account_metrics import monthly_metrics
from search_side_capacity import windows,robustness
from search_frozen_exits import WINDOWS,BOUNDARIES,COSTS,DATA,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from search_net_trailing import read
from search_cross_regime import select

OUT=ROOT/'artifacts/cross_exposure_20260925'
PRIOR=ROOT/'artifacts/cross_regime_20260925'
SIGNALS=ROOT/'artifacts/cross_sectional_20260925/signals.json'


def definitions(previous):
    result=[]
    for old in previous['specs']:
        if old['gate']!='none' or not old['source'].startswith('momentum'):continue
        for cap in [None,1,2]:
            policy=dict(old['policy']);tag='none' if cap is None else f'net{cap}'
            if cap is not None:policy['max_net_commitment']=cap*old['notional']
            result.append(dict(old,id=old['reference']+'_'+tag,reference=old['reference'],gate=tag,
                exposure_multiple=cap,policy=policy,baseline=cap is None))
    assert len(result)==12
    return result


def main():
    OUT.mkdir(exist_ok=True);(OUT/'runs').mkdir(exist_ok=True)
    previous=read(PRIOR/'summary.json');specs=definitions(previous);spans=windows()
    protocol=dict(created_at=pd.Timestamp.now(tz='UTC').isoformat(),previous_turn_classification='progress:288market-gatepaths,25tests,18proxyhalts independently reconstructed; gates removed Longs and worsened freshJune7dmomentum100.',
        hypothesis='Dynamic signed dollar commitment admission may avoid one-sided capture without permanently reserving fixed side slots. Test frozen7dayrawmomentumhold and3dayriskadjustedmomentumtime168,at25/100totalnotional.',
        intervention='At entry only, compute Long/Short sum(qty*lastclosedMark+remainingplannedtranches). Add full candidate budget to candidate side. Allow if abs(projectednet)<=1or2positionbudgets, OR abs(projectednet) strictly decreases. None control bypasses guard. Preserve daily priority/order/event/ATR; no retry/rerank/opposite synthetic orders. Guard before price/lot/target checks; passing guard does not promise a fill. Onecoinoneposition,5sharedslots. Drift, exits and favorable adds can exceed entry bound; no forced rebalancing. Dollarbalance is notbeta/riskneutrality.',
        account='500USDT Crossx5,3favorableparts,totalnotional25(default5margin) or100(research20margin),noSL,3ATR/1%price trailing,actualfees/funding/MTM,persistent20%DDentrypause. Hold retains losers; time168 is research loss-close alternative. No live edits.',
        evaluation='12policies x12windows x2cost=288paths. DevelopmentSep-May first; pickonecapperreference usingbothcostprofit,DD<20,20closed,complete,maxworstmonthlythenworstending. Lockbeforelater. Everypolicy also runat10three-monthstartsSep2025-Jun2026; overlapping,alreadyinspectedhistory,notfreshOOS. 96nonecontrols must exactlymatch batch26.',
        target='Atleast50%netMTM EVERYcalendar month. Positiveyearorwindowdoesnotpass.',limitations=previous['protocol']['limitations'],
        specs=specs,windows=spans,costs=COSTS,prior_sha256=sha(PRIOR/'summary.json'),signals_sha256=sha(SIGNALS),
        data_sha256=sha(DATA/'reconciled_manifest.json'),rules_sha256=sha(RULE_PATH),live_config_sha256=sha(ROOT/'configs/live.yaml'),
        source_sha256={n:sha(ROOT/'scripts'/n) for n in ['search_cross_exposure.py','account_exposure_replay.py','exposure_admission.py','account_net_trailing_replay.py','directional_capacity_metrics.py','frozen_extension_inputs.py']})
    write(OUT/'protocol.json',protocol)
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH);signals=read(SIGNALS);results=[]
    for window,(start,end) in spans.items():
        for sp in specs:
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),grouped_signals(signals[sp['source']],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(5,fee,slip),research_policy=sp['policy'])
                r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct'
                row=summarize(r,sp['id'],sp['id'],sp['policy'],5,cost,window);sides=side_metrics(r,r['curve'])
                row.update(id=f'{window}_{cost}_{sp["id"]}',strategy_id=sp['id'],reference=sp['reference'],gate=sp['gate'],notional=sp['notional'],baseline=sp['baseline'],source=sp['source'],holding=sp['holding'],
                    utilization=utilization(r['curve'],r,sp['notional'],5),exit_diagnostics=exit_diagnostics(r),side_metrics=sides,
                    side_entries={side:rs['entries'] for side,rs in sides['sides'].items()},monthly=monthly_metrics(r['curve'],boundaries=[t for t in BOUNDARIES if start<=t<=end]),
                    exposure_checks=len(r.get('exposure_checks',[])),exposure_rejected=r['rejections'].get('exposure_imbalance',0))
                row['target_met']=r['ending_equity'] is not None and row['monthly']['all_months_50pct']
                write(OUT/'runs'/f'{row["id"]}.json',{k:v for k,v in r.items() if k!='curve'});pd.DataFrame(r['curve']).to_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet',index=False);results.append(row)
            write(OUT/'progress.json',dict(window=window,runs=len(results)))
        print(window,'COMPLETE',len(results),flush=True)
        if window=='development':
            selected=select(specs,results);write(OUT/'candidate_lock.json',dict(selected=selected,locked_at=pd.Timestamp.now(tz='UTC').isoformat(),later_not_run_in_batch=True,pristine_oos=False));print('LOCKED',selected,flush=True)
    assert sha(ROOT/'configs/live.yaml')==protocol['live_config_sha256']
    write(OUT/'summary.json',dict(protocol=protocol,specs=specs,selected=selected,rolling_specs=[sp['id'] for sp in specs],results=results,robustness=robustness(results),
        target_met_rows=sum(r['target_met'] for r in results),incomplete_paths=sum(r['ending_equity'] is None for r in results)))
    pd.DataFrame(results).to_csv(OUT/'comparison.csv',index=False);print('COMPLETE',len(results),flush=True)


if __name__=='__main__':main()
